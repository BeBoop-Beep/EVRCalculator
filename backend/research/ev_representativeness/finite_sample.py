"""Parts 11-14, 17 and 22-24: the finite-sample layer.

THE QUESTION THIS MODULE ANSWERS
--------------------------------
Given the empirical one-pack outcome vector ``X`` (1,000,000 exact simulated
packs), what does the average of ``N`` packs actually look like for a real
opener, and how large must ``N`` get before EV stops being a misleading
description of it?

    S_N = X_1 + ... + X_N          (N packs opened)
    Xbar_N = S_N / N               (realized average value per pack)

    realization:   P(Xbar_N >= r * EV)
    convergence:   P(|Xbar_N / EV - 1| <= tau)

WHY BOOTSTRAP RESAMPLING AND NOT FRESH SIMULATION
-------------------------------------------------
``X`` is itself a million i.i.d. draws from the pack model, so drawing from it
WITH REPLACEMENT is an unbiased bootstrap of the true finite-sample distribution
of ``Xbar_N``. With replacement there is no without-replacement variance
deflation at all, and the finite-population artifact is negligible (even at
N = 25,000 the sampling fraction is 2.5%).

The alternative - generating fresh packs from the simulator for every grid point
- costs ~70 s per set per N, and would not be reproducible, because the
authoritative simulation is unseeded (``monteCarloSimV2._to_rng`` returns a bare
``default_rng()``). This is also exactly what the sealed-product layer already
does in ``sealed_product_distribution.build_stage1_product_distributions``.

THE KERNEL, AND WHAT COMMON RANDOM NUMBERS BUY AND COST
--------------------------------------------------------
A ``(n_sessions x N_max)`` matrix is never allocated. One ``float64`` running-sum
vector of shape ``(n_sessions,)`` is carried across the ascending N grid, and
``(N_next - N_prev)`` fresh draws are added at each step in memory-bounded
column blocks. Work is ``n_sessions * N_max`` draws; memory is ``O(n_sessions)``.

That makes the grid share paths - session i's 36-pack opening literally CONTAINS
its 6-pack opening. Common random numbers.

  * BUYS: the estimated curve is far smoother in N than independent estimates
    would be, so a threshold crossing is much less likely to be a sampling
    artifact.
  * COSTS: P_hat(N) and P_hat(N') are positively correlated, so "the threshold
    held at the next three checkpoints" is weaker evidence than three
    independent checks. This is why the CONFIRMATION stage re-estimates from an
    INDEPENDENT seed stream rather than trusting the coarse curve's band.

Each individual P_hat(N) is still a clean binomial proportion over n_sessions
independent sessions, so its Wilson interval is valid marginally.

MONOTONICITY IS MEASURED, NEVER ASSUMED
---------------------------------------
The brief is explicit and correct: these curves need not rise at every integer N.
Nothing here binary-searches. The grid is swept in full, local decreases are
counted and their magnitude recorded, and two DIFFERENT horizon numbers are
reported - the noisy first crossing and the statistically confirmed stable
horizon - rather than one number pretending to be both.
"""

from __future__ import annotations

import hashlib
import math
from dataclasses import dataclass, field
from typing import Any, Dict, Iterable, Iterator, List, Mapping, Optional, Sequence, Tuple

import numpy as np

from .version import (
    CI_METHOD,
    CI_Z,
    CONFIRM_DRAW_BUDGET,
    CONFIRM_SESSION_COUNT,
    SESSION_INDEX_BLOCK_BYTES,
    SESSION_MODEL_VERSION,
    STABILITY_BAND_FACTOR,
    STABILITY_MIN_BAND_POINTS,
    STAGE_COARSE,
    STAGE_CONFIRM,
    STAGE_REFINE,
)

SCOPE_PACK_GRID = "pack_grid"
SCOPE_PRODUCT = "product"

HORIZON_RESOLVED = "resolved"
HORIZON_EXCEEDS_CAP = "exceeds_search_cap"
HORIZON_IMMEDIATE = "resolved_at_minimum_grid_point"
HORIZON_DEGENERATE = "degenerate_ev"


# ---------------------------------------------------------------------------
# Deterministic seeding
# ---------------------------------------------------------------------------

def research_seed(parts: Iterable[Any]) -> int:
    """A process-stable 63-bit seed from SHA-256.

    Python's ``hash()`` is randomized per process (PYTHONHASHSEED), so it cannot
    back a reproducible research result. Same construction the sealed-product
    bootstrap already uses for the same reason.

    63 BITS, NOT 64, and the reason is persistence rather than statistics. An
    unsigned 64-bit value overflows Postgres ``bigint`` (max 2^63 - 1) roughly
    half the time, and every seed here is written to a ``seed`` column so the
    estimate can be reproduced. Masking the sign bit keeps the value
    deterministic, non-negative (``np.random.default_rng`` rejects negatives) and
    always storable. One bit of entropy is irrelevant for seeding; a seed that
    cannot be recorded is not reproducible at all.
    """
    digest = hashlib.sha256("|".join(str(part) for part in parts).encode("utf-8")).digest()
    return int.from_bytes(digest[:8], "big", signed=False) & ((1 << 63) - 1)


# ---------------------------------------------------------------------------
# Binomial-proportion uncertainty (Part 22)
# ---------------------------------------------------------------------------

@dataclass(frozen=True)
class ProportionEstimate:
    successes: int
    trials: int
    estimate: float
    standard_error: float
    ci_lower: float
    ci_upper: float
    ci_method: str = CI_METHOD


def wilson_interval(successes: int, trials: int, *, z: float = CI_Z) -> ProportionEstimate:
    """Wilson score interval for a binomial proportion.

    WHY WILSON AND NOT WALD
    -----------------------
    Every horizon in this research lives near p = 0.75-0.95, and the reported
    number turns on whether the lower bound clears a confidence level. Wald's
    symmetric ``p +/- z*sqrt(p(1-p)/n)`` is exactly wrong there: it is
    anti-conservative near the boundaries and can produce an upper bound above
    1.0, which would make "80% of openers" defensible on an interval that
    includes impossible values. Wilson is the standard score-based fix, has no
    such overshoot, and degrades gracefully at p = 0 and p = 1 (which genuinely
    occur here: P(Xbar_1 >= 0.9*EV) is very small, and convergence probabilities
    saturate at 1 for large N).

    ``standard_error`` is reported as the plain binomial SE because that is what
    "Monte Carlo standard error" means for a proportion; the INTERVAL is Wilson.
    Both travel with the row so a reader can see they are different objects.
    """
    if trials <= 0:
        raise ValueError("wilson_interval requires a positive trial count")
    if not 0 <= successes <= trials:
        raise ValueError(f"successes {successes} outside [0, {trials}]")

    n = float(trials)
    p = successes / n
    se = math.sqrt(p * (1.0 - p) / n)

    denominator = 1.0 + (z * z) / n
    centre = (p + (z * z) / (2.0 * n)) / denominator
    margin = (z * math.sqrt((p * (1.0 - p) + (z * z) / (4.0 * n)) / n)) / denominator
    return ProportionEstimate(
        successes=int(successes),
        trials=int(trials),
        estimate=p,
        standard_error=se,
        ci_lower=max(0.0, centre - margin),
        ci_upper=min(1.0, centre + margin),
    )


# ---------------------------------------------------------------------------
# Curve points
# ---------------------------------------------------------------------------

@dataclass(frozen=True)
class CurvePoint:
    """One persisted estimate: one metric, at one pack count, at one stage."""

    scope_kind: str
    sealed_product_id: Optional[str]
    pack_count: int
    metric_key: str
    estimate: float
    session_count: int
    stage: str
    seed: int
    successes: Optional[int] = None
    standard_error: Optional[float] = None
    ci_lower: Optional[float] = None
    ci_upper: Optional[float] = None
    ci_method: Optional[str] = None

    @property
    def is_probability(self) -> bool:
        return self.successes is not None


def realization_metric_key(target: float) -> str:
    return f"realization_ge_{target:.2f}"


def convergence_metric_key(tolerance: float) -> str:
    return f"within_tau_{tolerance:.2f}"


SESSION_PER_PACK_PERCENTILES: Tuple[int, ...] = (10, 25, 50, 75, 90, 95, 99)


# ---------------------------------------------------------------------------
# The kernel
# ---------------------------------------------------------------------------

def _index_block_columns(n_sessions: int, block_bytes: int) -> int:
    """Columns per index block, so peak index memory stays under ``block_bytes``.

    Indices are int32 (4 bytes): the source vector is 1e6 elements, far inside
    int32 range, and halving the index width doubles the block width for the
    same memory ceiling.
    """
    return max(1, block_bytes // max(1, n_sessions * 4))


def iter_session_sums(
    outcomes: np.ndarray,
    pack_counts: Sequence[int],
    *,
    session_count: int,
    seed: int,
    block_bytes: int = SESSION_INDEX_BLOCK_BYTES,
) -> Iterator[Tuple[int, np.ndarray]]:
    """Yield ``(pack_count, session_totals)`` for each pack count, ascending.

    The yielded array is the LIVE running buffer, not a copy - consumers must
    read it before advancing the iterator. Copying a 250,000-element vector at
    every one of ~40 grid points would be pure waste.
    """
    x = np.asarray(outcomes, dtype=np.float64)
    if x.ndim != 1 or x.size == 0:
        raise ValueError("iter_session_sums requires a non-empty 1-D outcome vector")
    if session_count <= 0:
        raise ValueError("session_count must be positive")

    ordered = sorted({int(count) for count in pack_counts})
    if not ordered:
        return
    if ordered[0] < 1:
        raise ValueError(f"pack counts must be >= 1; got {ordered[0]}")

    rng = np.random.default_rng(seed)
    running = np.zeros(session_count, dtype=np.float64)
    columns = _index_block_columns(session_count, block_bytes)
    previous = 0
    size = int(x.size)

    for pack_count in ordered:
        remaining = pack_count - previous
        while remaining > 0:
            take = min(remaining, columns)
            indices = rng.integers(0, size, size=(session_count, take), dtype=np.int32)
            running += x[indices].sum(axis=1)
            remaining -= take
        previous = pack_count
        yield pack_count, running


def evaluate_pack_grid(
    outcomes: np.ndarray,
    pack_counts: Sequence[int],
    *,
    ev: float,
    pack_cost: Optional[float],
    realization_targets: Sequence[float],
    convergence_tolerances: Sequence[float],
    session_count: int,
    seed: int,
    stage: str,
    scope_kind: str = SCOPE_PACK_GRID,
    sealed_product_id: Optional[str] = None,
    include_session_distribution: bool = True,
    product_cost: Optional[float] = None,
    block_bytes: int = SESSION_INDEX_BLOCK_BYTES,
) -> List[CurvePoint]:
    """Parts 11, 12 and 17 over one pack-count grid.

    ``product_cost`` overrides ``pack_cost * pack_count`` for a real SKU, because
    a booster box does not cost 36 loose packs and pretending it does would make
    every product-level return ratio wrong (Part 16).
    """
    points: List[CurvePoint] = []
    ev_f = float(ev)
    degenerate_ev = not math.isfinite(ev_f) or ev_f <= 0.0

    realization_thresholds = [(float(r), float(r) * ev_f) for r in realization_targets]
    tolerances = [float(t) for t in convergence_tolerances]

    for pack_count, totals in iter_session_sums(
        outcomes,
        pack_counts,
        session_count=session_count,
        seed=seed,
        block_bytes=block_bytes,
    ):
        per_pack = totals / float(pack_count)

        if not degenerate_ev:
            for target, absolute in realization_thresholds:
                successes = int(np.count_nonzero(per_pack >= absolute))
                estimate = wilson_interval(successes, session_count)
                points.append(
                    CurvePoint(
                        scope_kind=scope_kind,
                        sealed_product_id=sealed_product_id,
                        pack_count=pack_count,
                        metric_key=realization_metric_key(target),
                        estimate=estimate.estimate,
                        session_count=session_count,
                        stage=stage,
                        seed=seed,
                        successes=estimate.successes,
                        standard_error=estimate.standard_error,
                        ci_lower=estimate.ci_lower,
                        ci_upper=estimate.ci_upper,
                        ci_method=estimate.ci_method,
                    )
                )

            relative_error = np.abs(per_pack / ev_f - 1.0)
            for tolerance in tolerances:
                successes = int(np.count_nonzero(relative_error <= tolerance))
                estimate = wilson_interval(successes, session_count)
                points.append(
                    CurvePoint(
                        scope_kind=scope_kind,
                        sealed_product_id=sealed_product_id,
                        pack_count=pack_count,
                        metric_key=convergence_metric_key(tolerance),
                        estimate=estimate.estimate,
                        session_count=session_count,
                        stage=stage,
                        seed=seed,
                        successes=estimate.successes,
                        standard_error=estimate.standard_error,
                        ci_lower=estimate.ci_lower,
                        ci_upper=estimate.ci_upper,
                        ci_method=estimate.ci_method,
                    )
                )

        if not include_session_distribution:
            continue

        # Part 17 - the shape of the session distribution itself, so
        # "what does a 9-pack opening look like" is answerable later without
        # re-running anything.
        scalars: List[Tuple[str, float]] = [
            ("session_mean_per_pack", float(per_pack.mean())),
            ("session_std_dev_per_pack", float(per_pack.std())),
        ]
        quantiles = np.percentile(per_pack, SESSION_PER_PACK_PERCENTILES)
        for percentile, value in zip(SESSION_PER_PACK_PERCENTILES, np.atleast_1d(quantiles)):
            scalars.append((f"session_p{percentile:02d}_per_pack", float(value)))

        session_cost = (
            float(product_cost)
            if product_cost is not None
            else (float(pack_cost) * pack_count if pack_cost is not None else None)
        )
        if session_cost is not None and math.isfinite(session_cost) and session_cost > 0.0:
            ratios = totals / session_cost
            scalars.append(("session_return_ratio_mean", float(ratios.mean())))
            ratio_quantiles = np.percentile(ratios, SESSION_PER_PACK_PERCENTILES)
            for percentile, value in zip(SESSION_PER_PACK_PERCENTILES, np.atleast_1d(ratio_quantiles)):
                scalars.append((f"session_return_ratio_p{percentile:02d}", float(value)))

            recovered = int(np.count_nonzero(totals >= session_cost))
            estimate = wilson_interval(recovered, session_count)
            points.append(
                CurvePoint(
                    scope_kind=scope_kind,
                    sealed_product_id=sealed_product_id,
                    pack_count=pack_count,
                    metric_key="session_recovers_cost",
                    estimate=estimate.estimate,
                    session_count=session_count,
                    stage=stage,
                    seed=seed,
                    successes=estimate.successes,
                    standard_error=estimate.standard_error,
                    ci_lower=estimate.ci_lower,
                    ci_upper=estimate.ci_upper,
                    ci_method=estimate.ci_method,
                )
            )
            scalars.append(("session_cost", session_cost))

        for metric_key, value in scalars:
            points.append(
                CurvePoint(
                    scope_kind=scope_kind,
                    sealed_product_id=sealed_product_id,
                    pack_count=pack_count,
                    metric_key=metric_key,
                    estimate=value,
                    session_count=session_count,
                    stage=stage,
                    seed=seed,
                )
            )

    return points


# ---------------------------------------------------------------------------
# Monotonicity audit
# ---------------------------------------------------------------------------

@dataclass(frozen=True)
class MonotonicityAudit:
    """Evidence about whether the curves actually rise in N, per metric."""

    metric_key: str
    checkpoint_count: int
    violation_count: int
    max_decrease: float
    max_decrease_at: Optional[int]
    #: True when every observed decrease is inside what Monte Carlo noise alone
    #: would explain at these session counts. A decrease LARGER than that is a
    #: real property of the discrete distribution, not sampling noise.
    all_violations_within_noise: bool

    def as_payload(self) -> Dict[str, Any]:
        return {
            "metricKey": self.metric_key,
            "checkpointCount": self.checkpoint_count,
            "violationCount": self.violation_count,
            "maxDecrease": self.max_decrease,
            "maxDecreaseAt": self.max_decrease_at,
            "allViolationsWithinNoise": self.all_violations_within_noise,
        }


def audit_monotonicity(points: Sequence[CurvePoint], *, z: float = CI_Z) -> List[MonotonicityAudit]:
    """Count local decreases in each probability curve.

    A decrease is flagged as "within noise" when it is smaller than
    ``z * sqrt(se_a^2 + se_b^2)``, the standard error of the DIFFERENCE of two
    proportions treated as independent. Common random numbers make consecutive
    estimates positively correlated, which SHRINKS the true variance of their
    difference - so this test is conservative: it will call a decrease "real"
    slightly more often than it should, never the reverse. That is the right
    direction for an assumption audit.
    """
    by_metric: Dict[str, List[CurvePoint]] = {}
    for point in points:
        if point.is_probability:
            by_metric.setdefault(point.metric_key, []).append(point)

    audits: List[MonotonicityAudit] = []
    for metric_key, metric_points in sorted(by_metric.items()):
        ordered = sorted(metric_points, key=lambda item: item.pack_count)
        violations = 0
        max_decrease = 0.0
        max_at: Optional[int] = None
        all_within_noise = True
        for previous, current in zip(ordered, ordered[1:]):
            decrease = previous.estimate - current.estimate
            if decrease <= 0.0:
                continue
            violations += 1
            noise = z * math.sqrt(
                (previous.standard_error or 0.0) ** 2 + (current.standard_error or 0.0) ** 2
            )
            if decrease > noise:
                all_within_noise = False
            if decrease > max_decrease:
                max_decrease = decrease
                max_at = current.pack_count
        audits.append(
            MonotonicityAudit(
                metric_key=metric_key,
                checkpoint_count=len(ordered),
                violation_count=violations,
                max_decrease=max_decrease,
                max_decrease_at=max_at,
                all_violations_within_noise=all_within_noise,
            )
        )
    return audits


# ---------------------------------------------------------------------------
# Horizons (Parts 13 and 14)
# ---------------------------------------------------------------------------

@dataclass(frozen=True)
class Horizon:
    """One horizon: the pack count at which a threshold is met.

    TWO NUMBERS, DELIBERATELY
    -------------------------
    ``first_crossing_n`` is the smallest grid point whose POINT ESTIMATE clears
    the confidence level. It is cheap, it is what a naive implementation would
    report, and it is noisy - a 79.99% vs 80.01% coin flip decides it.

    ``stable_n`` requires the WILSON LOWER BOUND to clear the level, and to keep
    clearing it across a multiplicative band above the crossing, re-estimated
    from an independent seed at the confirmation session count. That is the
    number fit to publish.

    Reporting both makes the difference between them measurable, which is itself
    a research finding: if they are usually equal, the noise concern was
    overstated for these distributions; if they diverge widely, it was not.
    """

    metric_key: str
    confidence: float
    first_crossing_n: Optional[int]
    stable_n: Optional[int]
    status: str
    stage: str
    search_cap: int
    stable_estimate: Optional[float] = None
    stable_ci_lower: Optional[float] = None
    stable_session_count: Optional[int] = None
    band_points_checked: int = 0

    def as_payload(self) -> Dict[str, Any]:
        return {
            "metricKey": self.metric_key,
            "confidence": self.confidence,
            "firstCrossingN": self.first_crossing_n,
            "stableN": self.stable_n,
            "status": self.status,
            "stage": self.stage,
            "searchCap": self.search_cap,
            "stableEstimate": self.stable_estimate,
            "stableCiLower": self.stable_ci_lower,
            "stableSessionCount": self.stable_session_count,
            "bandPointsChecked": self.band_points_checked,
        }


def _curve_for_metric(points: Sequence[CurvePoint], metric_key: str) -> List[CurvePoint]:
    return sorted(
        (p for p in points if p.metric_key == metric_key and p.is_probability),
        key=lambda item: item.pack_count,
    )


def resolve_horizon(
    points: Sequence[CurvePoint],
    *,
    metric_key: str,
    confidence: float,
    search_cap: int,
    band_factor: float = STABILITY_BAND_FACTOR,
    min_band_points: int = STABILITY_MIN_BAND_POINTS,
    stage: str = STAGE_COARSE,
) -> Horizon:
    """Locate both horizon definitions on an already-evaluated curve.

    The stability rule: N qualifies when its own Wilson lower bound clears
    ``confidence`` AND every evaluated grid point in ``[N, N * band_factor]``
    does too, with at least ``min_band_points`` points in that window (N
    included). If the grid runs out before the band is full, the candidate is not
    promoted - a crossing at the very edge of the searched range has not been
    shown to hold.
    """
    curve = _curve_for_metric(points, metric_key)
    if not curve:
        return Horizon(
            metric_key=metric_key,
            confidence=confidence,
            first_crossing_n=None,
            stable_n=None,
            status=HORIZON_DEGENERATE,
            stage=stage,
            search_cap=search_cap,
        )

    first_crossing = next((p.pack_count for p in curve if p.estimate >= confidence), None)

    stable: Optional[CurvePoint] = None
    band_checked = 0
    for index, candidate in enumerate(curve):
        if (candidate.ci_lower or 0.0) < confidence:
            continue
        window = [
            p for p in curve[index:]
            if p.pack_count <= candidate.pack_count * band_factor
        ]
        if len(window) < min_band_points:
            # Not enough evaluated points above the candidate to demonstrate the
            # threshold HOLDS. Only accept if the grid genuinely ended because
            # the search cap was reached, and every remaining point qualifies.
            if curve[-1].pack_count < search_cap:
                continue
            window = curve[index:]
            if len(window) < min_band_points:
                continue
        if all((p.ci_lower or 0.0) >= confidence for p in window):
            stable = candidate
            band_checked = len(window)
            break

    if stable is not None:
        status = (
            HORIZON_IMMEDIATE
            if stable.pack_count == curve[0].pack_count
            else HORIZON_RESOLVED
        )
        return Horizon(
            metric_key=metric_key,
            confidence=confidence,
            first_crossing_n=first_crossing,
            stable_n=stable.pack_count,
            status=status,
            stage=stage,
            search_cap=search_cap,
            stable_estimate=stable.estimate,
            stable_ci_lower=stable.ci_lower,
            stable_session_count=stable.session_count,
            band_points_checked=band_checked,
        )

    return Horizon(
        metric_key=metric_key,
        confidence=confidence,
        first_crossing_n=first_crossing,
        stable_n=None,
        status=HORIZON_EXCEEDS_CAP,
        stage=stage,
        search_cap=search_cap,
    )


def build_confirmation_grid(
    candidate: int,
    *,
    band_factor: float = STABILITY_BAND_FACTOR,
    min_band_points: int = STABILITY_MIN_BAND_POINTS,
) -> List[int]:
    """The pack counts a confirmation pass must re-estimate.

    The candidate plus a geometric ladder up to ``candidate * band_factor``, so
    the confirmation checks the SAME claim the coarse stage made (the threshold
    holds across the band), not merely the single crossing point.

    One point BELOW the candidate is included: if the threshold turns out to hold
    there too under the sharper estimate, the confirmed horizon should move down,
    not stay artificially high.
    """
    points = {candidate}
    if candidate > 1:
        points.add(max(1, int(round(candidate / band_factor))))
    steps = max(1, min_band_points - 1)
    for step in range(1, steps + 1):
        points.add(int(round(candidate * band_factor ** (step / steps))))
    return sorted(points)


def confirm_session_count(
    candidate_grid: Sequence[int],
    *,
    preferred: int = CONFIRM_SESSION_COUNT,
    draw_budget: int = CONFIRM_DRAW_BUDGET,
    minimum: int = 40_000,
) -> int:
    """Sessions the confirmation pass can afford at this depth.

    A horizon in the tens of thousands would otherwise make one set cost more
    than the rest of the cohort combined. When the budget binds, the session
    count is reduced rather than the confirmation being skipped, and the ACTUAL
    count is persisted on every row - so the widened Wilson interval is visible
    in the data instead of being implied by a footnote.
    """
    deepest = max(int(count) for count in candidate_grid)
    affordable = int(draw_budget // max(1, deepest))
    return max(minimum, min(preferred, affordable))
