"""Financial RIP V3 — the outcome-profile engine.

WHAT THIS IS
------------
A financial-only, pack-level score built from TWO inputs and nothing else:

    X = the simulated per-pack value vector
    C = the pack cost that simulation ran against

Everything published under Financial RIP V3 is a function of ``X`` and ``C``.
This module is the ONE authoritative builder; simulation-derived metrics,
persistence validation, the ranking path, the audit scripts and the tests all
call :func:`compute_financial_rip_v3` rather than re-deriving anything.

WHAT V3 DELIBERATELY DOES NOT CONSUME
-------------------------------------
Collector Appeal, Opening Desirability, Universal Set Desirability, Pokemon
popularity, set value, other sets' market prices, cohort min-max scores, P05,
Bad Floor, coefficient of variation, Stability Score, HHI as a weighted term,
and Best Pull as a weighted term.

P05 in particular is still calculated and still persisted by the V2 path (it
remains a real, useful downside statistic and it drives the distribution
charts), but it carries ZERO V3 weight and is not read anywhere below. A set
with a catastrophic 5th-percentile outcome is not penalised twice: Loss
Resilience already measures what losing outcomes feel like, using the whole
losing mass rather than a single quantile that one rare wipeout can drag down.

THE SIX COMPONENTS
------------------
    True Win Frequency        25%   how often the pack recovers its cost
    Typical Retention         20%   what the median pack hands back
    Loss Resilience           15%   what losing packs hand back
    Realistic Upside          25%   the 95th-99th percentile band
    Jackpot Upside            10%   the top 1%, saturating
    Base Economic Efficiency   5%   RTP with the top 1% removed

Weights and every fixed normalization anchor live in
:mod:`backend.calculations.evr.financial_rip_v3_config`. Nothing numeric is
hardcoded here.

MISSING DATA
------------
There is no neutral 50 in this module. An invalid pack cost, an empty or
non-finite outcome vector, or too few simulated packs makes V3 UNAVAILABLE with
an explicit machine-readable reason and ``rankable=False``. An unavailable V3
never falls back to V2 and never borrows a V2 field.
"""

from __future__ import annotations

import math
from typing import Any, Dict, List, Mapping, Optional, Sequence, Tuple

import numpy as np

from backend.calculations.evr.financial_rip_v3_config import (
    DEPTH_AND_ROBUSTNESS_LABELS,
    DEPTH_AND_ROBUSTNESS_VERSION,
    FINANCIAL_RIP_V3_COMPONENT_INPUTS,
    FINANCIAL_RIP_V3_COMPONENT_ORDER,
    FINANCIAL_RIP_V3_CONFIG_VERSION,
    FINANCIAL_RIP_V3_MIN_SIMULATION_COUNT,
    FINANCIAL_RIP_V3_NORMALIZATION_VERSION,
    FINANCIAL_RIP_V3_PUBLIC_COMPONENT_KEYS,
    FINANCIAL_RIP_V3_TAIL_CONTRACT_VERSION,
    FINANCIAL_RIP_V3_VERSION,
    FINANCIAL_RIP_V3_WEIGHTS,
    JACKPOT_TAIL_SHARE,
    REALISTIC_TAIL_SHARE,
    REASON_EMPTY_OUTCOMES,
    REASON_INSUFFICIENT_RUNS,
    REASON_INVALID_PACK_COST,
    REASON_MISSING_COMPONENT,
    REASON_NON_FINITE_OUTCOMES,
    SCORE_RECONSTRUCTION_TOLERANCE,
    SOFT_LOSS_RATIO_THRESHOLD,
    STATUS_READY,
    STATUS_UNAVAILABLE,
    classify_depth_and_robustness,
    financial_rip_v3_weights_payload,
    normalize_metric,
)


# ---------------------------------------------------------------------------
# JSON-safety helpers
# ---------------------------------------------------------------------------
# NumPy scalars are not JSON-serializable and silently poison a JSONB insert
# several layers away from where they were created. Every number that leaves
# this module goes through one of these.

def _f(value: Any) -> Optional[float]:
    """Ordinary finite Python float, or None. Never a numpy scalar."""
    if value is None:
        return None
    try:
        parsed = float(value)
    except (TypeError, ValueError):
        return None
    return parsed if math.isfinite(parsed) else None


def _i(value: Any) -> Optional[int]:
    parsed = _f(value)
    return int(round(parsed)) if parsed is not None else None


def _round(value: Optional[float], digits: int) -> Optional[float]:
    return round(value, digits) if value is not None else None


def _ratio(numerator: Optional[float], denominator: Optional[float]) -> Optional[float]:
    num = _f(numerator)
    den = _f(denominator)
    if num is None or den is None or den == 0.0:
        return None
    return _f(num / den)


# ---------------------------------------------------------------------------
# Exact empirical tail selection
# ---------------------------------------------------------------------------

class TailBuckets:
    """Deterministic rank-based tail buckets over a sorted outcome vector.

    WHY NOT ``values >= np.percentile(values, 95)``
    -----------------------------------------------
    Pokemon pack distributions are discrete and dense with ties: an enormous
    share of packs land on exactly the same handful of bulk values. A boolean
    mask against a percentile threshold therefore selects EVERY observation on
    the threshold plateau, which can be materially more than the 5% of runs the
    metric claims to describe. "Average of the top 5%" computed that way can
    quietly be an average of the top 30%.

    Rank buckets fix the MASS instead of the threshold:

        top_1_count = max(1, ceil(n * 0.01))
        top_5_count = max(top_1_count + 1, ceil(n * 0.05))

        jackpot   = the highest ``top_1_count`` observations
        realistic = the observations immediately below the jackpot bucket,
                    up to ``top_5_count`` tail observations in total

    Ties may straddle a rank boundary, but tied observations are by definition
    EQUAL, so which side of the boundary a given tied observation falls on
    cannot move the conditional mean. The selected mass is exact and the
    conditional mean is stable.
    """

    def __init__(self, sorted_values: np.ndarray) -> None:
        n = int(sorted_values.size)
        top_1_count = max(1, math.ceil(n * JACKPOT_TAIL_SHARE))
        top_5_count = max(top_1_count + 1, math.ceil(n * REALISTIC_TAIL_SHARE))

        self.n = n
        self.sorted_values = sorted_values
        self.top_1_count = top_1_count
        self.top_5_count = top_5_count
        self.jackpot = sorted_values[n - top_1_count:]
        self.realistic = sorted_values[n - top_5_count: n - top_1_count]
        self.excluding_jackpot = sorted_values[: n - top_1_count]

    @property
    def sufficient(self) -> bool:
        """True when the vector is long enough for a non-degenerate 95-99 band."""
        return self.n > self.top_5_count and self.realistic.size > 0

    def payload(self, pack_cost: float) -> Dict[str, Any]:
        """Full tail-selection audit record."""
        return {
            "method": FINANCIAL_RIP_V3_TAIL_CONTRACT_VERSION,
            "totalObservations": self.n,
            "requestedShares": {
                "jackpot": JACKPOT_TAIL_SHARE,
                "realistic": REALISTIC_TAIL_SHARE,
            },
            "selectedCounts": {
                "jackpot": int(self.jackpot.size),
                "realistic": int(self.realistic.size),
                "combinedTail": int(self.top_5_count),
                "excludingJackpot": int(self.excluding_jackpot.size),
            },
            "selectedShares": {
                "jackpot": _round(_ratio(self.jackpot.size, self.n), 8),
                "realistic": _round(_ratio(self.realistic.size, self.n), 8),
                "combinedTail": _round(_ratio(self.top_5_count, self.n), 8),
            },
            # The rank-exact boundary values, so the reported percentile
            # thresholds and the conditional means can be reconciled against the
            # same sort. These are observations, not interpolated quantiles.
            "rankBoundaryValues": {
                "jackpotEntry": _round(_f(self.jackpot[0]), 6) if self.jackpot.size else None,
                "realisticEntry": _round(_f(self.realistic[0]), 6) if self.realistic.size else None,
            },
            "rankBoundaryRatios": {
                "jackpotEntry": (
                    _round(_ratio(_f(self.jackpot[0]), pack_cost), 6) if self.jackpot.size else None
                ),
                "realisticEntry": (
                    _round(_ratio(_f(self.realistic[0]), pack_cost), 6) if self.realistic.size else None
                ),
            },
        }


# ---------------------------------------------------------------------------
# Raw V3 metrics
# ---------------------------------------------------------------------------

def compute_true_win_frequency_raw(values: np.ndarray, pack_cost: float) -> Dict[str, Any]:
    """``P(X >= C)`` — how often a pack recovers its cost.

    A tie at exactly pack cost COUNTS as a true win: recovering the cost is
    exactly what this component measures, and excluding the tie would make the
    metric disagree with the plain-language claim on the card.
    """
    n = int(values.size)
    winning = int(np.count_nonzero(values >= pack_cost))
    probability = _ratio(winning, n)
    return {
        "winningRunCount": winning,
        "totalRunCount": n,
        "trueWinProbability": _round(probability, 8),
        # "roughly one pack in N". Only meaningful when some pack won.
        "impliedOddsOneInN": (
            _round(_ratio(1.0, probability), 3) if probability and probability > 0.0 else None
        ),
        "packCost": _round(_f(pack_cost), 4),
    }


def compute_typical_retention_raw(values: np.ndarray, pack_cost: float) -> Dict[str, Any]:
    """``P50(X)`` and ``P50(X) / C``.

    P50 is the TYPICAL pack, not a floor. Half of simulated packs came back
    below this number and half above it; the copy on the card must say median or
    typical and must never imply a guaranteed minimum.
    """
    typical_value = _f(np.median(values))
    return {
        "typicalPackValue": _round(typical_value, 6),
        "typicalRetentionRatio": _round(_ratio(typical_value, pack_cost), 6),
        "label": "median",
        "packCost": _round(_f(pack_cost), 4),
    }


def compute_loss_resilience_raw(values: np.ndarray, pack_cost: float) -> Dict[str, Any]:
    """What losing outcomes actually feel like.

    P05 is NOT used. A single quantile describes one point of the losing mass
    and is dominated by the worst rare outcome; these three statistics describe
    the whole losing distribution:

        average_retention_given_loss = E[R | R < 1]
        soft_loss_share_given_loss   = P(0.50 <= R < 1 | R < 1)
        hard_loss_probability        = P(R < 0.50)      (unconditional)

    ``hard_loss_probability`` is disclosed but carries no weight: it is
    algebraically tied to the same buckets as the two weighted inputs, so
    weighting it as well would double-count the same axis.

    With no losing runs at all, Loss Resilience is perfect by definition. That
    is recorded as an explicit reason rather than reached by dividing by zero.
    """
    n = int(values.size)
    ratios = values / pack_cost
    losing_mask = ratios < 1.0
    losing_ratios = ratios[losing_mask]
    losing_values = values[losing_mask]
    losing_count = int(losing_ratios.size)

    hard_mask = ratios < SOFT_LOSS_RATIO_THRESHOLD
    hard_count = int(np.count_nonzero(hard_mask))
    soft_count = losing_count - hard_count

    if losing_count == 0:
        return {
            "losingRunCount": 0,
            "totalRunCount": n,
            "averageLosingReturnValue": None,
            "averageRetentionGivenLoss": 1.0,
            "softLossCount": 0,
            "softLossShareGivenLoss": 1.0,
            "hardLossCount": 0,
            "hardLossProbability": 0.0,
            "softLossRatioThreshold": SOFT_LOSS_RATIO_THRESHOLD,
            "noLosingRuns": True,
            "noLosingRunsReason": (
                "Every simulated pack recovered its cost, so there is no losing "
                "distribution to describe. Loss Resilience is perfect by "
                "construction rather than by division."
            ),
            "packCost": _round(_f(pack_cost), 4),
        }

    return {
        "losingRunCount": losing_count,
        "totalRunCount": n,
        "averageLosingReturnValue": _round(_f(losing_values.mean()), 6),
        "averageRetentionGivenLoss": _round(_f(losing_ratios.mean()), 8),
        "softLossCount": soft_count,
        "softLossShareGivenLoss": _round(_ratio(soft_count, losing_count), 8),
        "hardLossCount": hard_count,
        # Unconditional on purpose: "how often does a pack come back with less
        # than half its cost" is the question a reader actually asks.
        "hardLossProbability": _round(_ratio(hard_count, n), 8),
        "softLossRatioThreshold": SOFT_LOSS_RATIO_THRESHOLD,
        "noLosingRuns": False,
        "packCost": _round(_f(pack_cost), 4),
    }


def compute_realistic_upside_raw(
    values: np.ndarray,
    pack_cost: float,
    buckets: TailBuckets,
) -> Dict[str, Any]:
    """The 95th-99th percentile band: a good pack, not a miraculous one.

    Two distinct numbers, and the copy must keep them distinct:

      * ``p95ThresholdValue`` — where the top 5% BEGINS. It is a threshold. It is
        NOT "the average one-in-20 pack".
      * ``realisticTailMeanValue`` — the mean of the band from the 95th
        percentile up to but EXCLUDING the top 1%. Excluding the top 1% is what
        keeps "realistic upside" meaning realistic: without it, one 300x chase
        would define the number a reader takes as their likely good outcome.
    """
    p95_value = _f(np.percentile(values, 95))
    realistic_mean = _f(buckets.realistic.mean()) if buckets.realistic.size else None
    return {
        "p95ThresholdValue": _round(p95_value, 6),
        "p95ThresholdRatio": _round(_ratio(p95_value, pack_cost), 6),
        "realisticTailMeanValue": _round(realistic_mean, 6),
        "realisticTailMeanRatio": _round(_ratio(realistic_mean, pack_cost), 6),
        "realisticTailObservationCount": int(buckets.realistic.size),
        "excludesTopPercent": JACKPOT_TAIL_SHARE,
        "thresholdLabel": "top_5_percent_entry_threshold",
        "meanLabel": "mean_of_95th_to_99th_percentile_band",
        "packCost": _round(_f(pack_cost), 4),
    }


def compute_jackpot_upside_raw(
    values: np.ndarray,
    pack_cost: float,
    buckets: TailBuckets,
) -> Dict[str, Any]:
    """The exceptional top 1%.

    Both ratios are normalized through SATURATING transforms (see the config
    module), so an arbitrarily large single outcome cannot produce an unbounded
    score. Combined with the 10% top-level weight, the absolute ceiling this
    component can contribute to Financial RIP V3 is 10 points.
    """
    p99_value = _f(np.percentile(values, 99))
    jackpot_mean = _f(buckets.jackpot.mean()) if buckets.jackpot.size else None
    return {
        "p99ThresholdValue": _round(p99_value, 6),
        "p99ThresholdRatio": _round(_ratio(p99_value, pack_cost), 6),
        "jackpotTailMeanValue": _round(jackpot_mean, 6),
        "jackpotTailMeanRatio": _round(_ratio(jackpot_mean, pack_cost), 6),
        "jackpotTailObservationCount": int(buckets.jackpot.size),
        "thresholdLabel": "top_1_percent_entry_threshold",
        "meanLabel": "mean_of_top_1_percent",
        "maximumContributionPoints": _round(100.0 * FINANCIAL_RIP_V3_WEIGHTS["jackpot_upside"], 4),
        "packCost": _round(_f(pack_cost), 4),
    }


def compute_base_economic_efficiency_raw(
    values: np.ndarray,
    pack_cost: float,
    buckets: TailBuckets,
) -> Dict[str, Any]:
    """Expected value as an economic guardrail, not the headline.

    The SCORED input is ``base_rtp_excluding_top_1pct``. Total RTP and jackpot
    value share are disclosed alongside it but carry no weight.

    Scoring base RTP rather than total RTP is the point of this component: one
    extremely valuable chase can lift mean(X) far above what an ordinary opening
    returns, and a model that scores mean(X) would report that product as
    economically strong for a reason 99% of buyers will never experience.
    """
    total_value = _f(values.sum())
    jackpot_value = _f(buckets.jackpot.sum()) if buckets.jackpot.size else None
    base_mean = _f(buckets.excluding_jackpot.mean()) if buckets.excluding_jackpot.size else None
    jackpot_share = (
        _ratio(jackpot_value, total_value)
        if total_value is not None and total_value > 0.0
        else None
    )
    return {
        "totalRtpRatio": _round(_ratio(_f(values.mean()), pack_cost), 6),
        "baseRtpExcludingTop1Pct": _round(_ratio(base_mean, pack_cost), 6),
        "baseMeanExcludingTop1PctValue": _round(base_mean, 6),
        "jackpotValueShare": _round(jackpot_share, 8),
        "nonJackpotValueShare": (
            _round(1.0 - jackpot_share, 8) if jackpot_share is not None else None
        ),
        "scoredInput": "base_rtp_excluding_top_1pct",
        "disclosureOnly": ["totalRtpRatio", "jackpotValueShare"],
        "packCost": _round(_f(pack_cost), 4),
    }


# The raw-metric key each normalized input is read from, per component. Kept
# next to the raw builders so a renamed raw field breaks here loudly instead of
# silently normalizing None.
_RAW_INPUT_PATHS: Dict[str, Tuple[str, str]] = {
    "true_win_probability": ("true_win_frequency", "trueWinProbability"),
    "typical_retention_ratio": ("typical_retention", "typicalRetentionRatio"),
    "average_retention_given_loss": ("loss_resilience", "averageRetentionGivenLoss"),
    "soft_loss_share_given_loss": ("loss_resilience", "softLossShareGivenLoss"),
    "p95_threshold_ratio": ("realistic_upside", "p95ThresholdRatio"),
    "realistic_tail_mean_ratio": ("realistic_upside", "realisticTailMeanRatio"),
    "p99_threshold_ratio": ("jackpot_upside", "p99ThresholdRatio"),
    "jackpot_tail_mean_ratio": ("jackpot_upside", "jackpotTailMeanRatio"),
    "base_rtp_excluding_top_1pct": ("base_economic_efficiency", "baseRtpExcludingTop1Pct"),
}


# ---------------------------------------------------------------------------
# Depth and Robustness (UNWEIGHTED diagnostic)
# ---------------------------------------------------------------------------

def build_depth_and_robustness(
    chase_metrics: Optional[Mapping[str, Any]],
    *,
    jackpot_value_share: Optional[float],
) -> Dict[str, Any]:
    """Concentration diagnostics that EXPLAIN a profile without scoring it.

    Stability is no longer a Financial RIP component, but the concentration
    measurements it used are genuinely informative, so they are preserved here
    as an unweighted diagnostic. This is NOT a seventh component and is never
    subtracted from the V3 score: Realistic Upside already excludes the top 1%,
    Jackpot Upside is capped at 10 points, and Base Economics excludes the top
    1%, so concentration is prevented from dominating V3 three times over
    already. Penalising it a fourth time would be double-counting.

    Reuses the values ``compute_chase_dependency_metrics`` already produced.
    Nothing is recomputed from card data here.
    """
    chase = dict(chase_metrics or {})
    available = bool(chase) and chase.get("top1_ev_share") is not None
    top1 = _f(chase.get("top1_ev_share"))
    tag = classify_depth_and_robustness(top1)
    return {
        "version": DEPTH_AND_ROBUSTNESS_VERSION,
        "status": "ready" if available else "unavailable",
        "statusReason": None if available else "No card EV contributions were available for this run.",
        "isWeighted": False,
        "weightNote": (
            "Diagnostic only. Depth and Robustness carries no Financial RIP V3 "
            "weight and is never subtracted from the score."
        ),
        "top1EvShare": _round(top1, 6),
        "top2EvShare": _round(_f(chase.get("top2_ev_share")), 6),
        "top3EvShare": _round(_f(chase.get("top3_ev_share")), 6),
        "top5EvShare": _round(_f(chase.get("top5_ev_share")), 6),
        "hhiEvConcentration": _round(_f(chase.get("hhi_ev_concentration")), 8),
        "effectiveChaseCount": _round(_f(chase.get("effective_chase_count")), 4),
        "cardsTracked": _i(chase.get("cards_tracked") if chase.get("cards_tracked") is not None else chase.get("n_cards")),
        "totalCardEv": _round(_f(chase.get("total_card_ev") if chase.get("total_card_ev") is not None else chase.get("total_ev")), 6),
        # From the OUTCOME distribution rather than the card table: how much of
        # all simulated value the top 1% of packs carried.
        "jackpotValueShare": _round(_f(jackpot_value_share), 8),
        "nonJackpotValueShare": (
            _round(1.0 - _f(jackpot_value_share), 8) if _f(jackpot_value_share) is not None else None
        ),
        "concentrationTag": tag,
        "concentrationLabel": DEPTH_AND_ROBUSTNESS_LABELS.get(tag) if tag else None,
    }


# ---------------------------------------------------------------------------
# Session opening profile (ADJACENT to V3, never blended into it)
# ---------------------------------------------------------------------------

def build_session_opening_profile(
    session_data: Optional[Mapping[str, Any]],
    *,
    pack_cost: float,
    true_win_probability: Optional[float] = None,
) -> Optional[Dict[str, Any]]:
    """A product-opening profile for ETBs / bundles / boxes, when available.

    NEVER blended into Financial RIP V3. ETBs, booster bundles, booster boxes
    and loose packs carry different pack counts and different prices, so a
    session-aware score would not be comparable across products - which is
    exactly the property V3 exists to have. V3 stays pack-level; this sits
    beside it.

    Returns ``None`` when the simulation orchestration did not supply session
    data. Session data is never a required V3 input.
    """
    if not isinstance(session_data, Mapping):
        return None
    raw_values = session_data.get("session_values")
    if not isinstance(raw_values, (list, tuple, np.ndarray)) or len(raw_values) == 0:
        return None

    session_values = np.asarray(raw_values, dtype=np.float64).ravel()
    if session_values.size == 0 or not np.all(np.isfinite(session_values)):
        return None

    n_packs = _i(session_data.get("n_packs"))
    n_runs = int(session_values.size)
    session_cost = _f(session_data.get("session_cost"))
    if session_cost is None and n_packs is not None:
        session_cost = _f(float(pack_cost) * n_packs)
    if session_cost is None or session_cost <= 0.0:
        return None

    median_session_value = _f(np.median(session_values))
    profile: Dict[str, Any] = {
        "status": "ready",
        "isFinancialRipV3Input": False,
        "note": (
            "Product-opening profile. Reported alongside Financial RIP V3 and "
            "deliberately not blended into it: pack counts and prices differ by "
            "product, so a session-weighted score would not be comparable."
        ),
        "sessionPackCount": n_packs,
        "sessionRunCount": n_runs,
        "sessionCost": _round(session_cost, 4),
        "packCost": _round(_f(pack_cost), 4),
        "probRecoverSessionCost": _round(
            _ratio(int(np.count_nonzero(session_values >= session_cost)), n_runs), 8
        ),
        "medianSessionValue": _round(median_session_value, 6),
        "medianSessionRetentionRatio": _round(_ratio(median_session_value, session_cost), 6),
        "p05SessionValue": _round(_f(np.percentile(session_values, 5)), 6),
        "p95SessionValue": _round(_f(np.percentile(session_values, 95)), 6),
        "probNoConfiguredMeaningfulHit": None,
        "probAtLeastOneTrueWinPack": None,
        "probNoTrueWinPack": None,
        "probAtLeastOneDoubleCostPack": None,
    }

    chase_hit_counts = session_data.get("chase_hit_counts")
    if isinstance(chase_hit_counts, (list, tuple, np.ndarray)) and len(chase_hit_counts) == n_runs:
        counts = np.asarray(chase_hit_counts, dtype=np.int64)
        profile["probNoConfiguredMeaningfulHit"] = _round(
            _ratio(int(np.count_nonzero(counts == 0)), n_runs), 8
        )

    # Per-pack session outcomes are only available when the orchestration kept
    # them. Without them these probabilities are reported as unavailable rather
    # than approximated from the pack-level distribution under an independence
    # assumption the simulation does not guarantee.
    pack_matrix = session_data.get("session_pack_values")
    if isinstance(pack_matrix, (list, tuple, np.ndarray)):
        try:
            matrix = np.asarray(pack_matrix, dtype=np.float64)
        except (TypeError, ValueError):
            matrix = None
        if matrix is not None and matrix.ndim == 2 and matrix.shape[0] == n_runs:
            wins_per_session = (matrix >= float(pack_cost)).sum(axis=1)
            doubles_per_session = (matrix >= 2.0 * float(pack_cost)).sum(axis=1)
            profile["probAtLeastOneTrueWinPack"] = _round(
                _ratio(int(np.count_nonzero(wins_per_session > 0)), n_runs), 8
            )
            profile["probNoTrueWinPack"] = _round(
                _ratio(int(np.count_nonzero(wins_per_session == 0)), n_runs), 8
            )
            profile["probAtLeastOneDoubleCostPack"] = _round(
                _ratio(int(np.count_nonzero(doubles_per_session > 0)), n_runs), 8
            )

    _ = true_win_probability  # accepted for symmetry; never used as a substitute
    return profile


# ---------------------------------------------------------------------------
# Unavailable result
# ---------------------------------------------------------------------------

def _unavailable(reason: str, detail: str, **extra: Any) -> Dict[str, Any]:
    """An honest unavailable V3 result. No component scores, no neutral 50."""
    return {
        "scoreVersion": FINANCIAL_RIP_V3_VERSION,
        "normalizationVersion": FINANCIAL_RIP_V3_NORMALIZATION_VERSION,
        "tailContractVersion": FINANCIAL_RIP_V3_TAIL_CONTRACT_VERSION,
        "configVersion": FINANCIAL_RIP_V3_CONFIG_VERSION,
        "status": STATUS_UNAVAILABLE,
        "statusReason": reason,
        "statusDetail": detail,
        "rankable": False,
        "score": None,
        "components": {},
        "depthAndRobustness": {},
        "distributionDisclosures": {},
        "estimationDiagnostics": dict(extra),
        "sessionOpeningProfile": None,
        "audit": {"weights": financial_rip_v3_weights_payload()},
    }


# ---------------------------------------------------------------------------
# The authoritative builder
# ---------------------------------------------------------------------------

def build_financial_rip_v3(
    values: Sequence[float],
    pack_cost: Any,
    *,
    chase_metrics: Optional[Mapping[str, Any]] = None,
    session_data: Optional[Mapping[str, Any]] = None,
    min_simulation_count: int = FINANCIAL_RIP_V3_MIN_SIMULATION_COUNT,
) -> Dict[str, Any]:
    """Build the complete, authoritative Financial RIP V3 result for one run.

    Parameters
    ----------
    values:
        The simulated per-pack value vector ``X``. Must be non-empty and finite.
    pack_cost:
        The pack cost ``C`` that THIS simulation ran against. Must be finite and
        strictly positive; a zero or missing cost makes every ratio in the model
        undefined, so V3 is unavailable rather than scored against a guess.
    chase_metrics:
        Optional output of ``compute_chase_dependency_metrics``, reused verbatim
        for the unweighted Depth and Robustness diagnostic.
    session_data:
        Optional session simulation output. Never a required input and never
        blended into the score.
    min_simulation_count:
        Below this, the top-1% conditional mean rests on too few observations to
        publish. Configurable so tests can exercise the engine on small vectors,
        but production reads the config default.

    Returns
    -------
    A JSON-safe dict of ordinary Python primitives. Every numeric leaf is a
    finite ``float``/``int`` or ``None`` — never a NumPy scalar and never NaN.
    """
    cost = _f(pack_cost)
    if cost is None or cost <= 0.0:
        return _unavailable(
            REASON_INVALID_PACK_COST,
            "Financial RIP V3 is defined entirely in terms of value/cost ratios, "
            "so it requires a finite, strictly positive pack cost.",
            packCost=cost,
        )

    array = np.asarray(values, dtype=np.float64).ravel()
    if array.size == 0:
        return _unavailable(
            REASON_EMPTY_OUTCOMES,
            "No simulated pack outcomes were supplied.",
            packCost=_round(cost, 4),
            simulationCount=0,
        )
    if not np.all(np.isfinite(array)):
        return _unavailable(
            REASON_NON_FINITE_OUTCOMES,
            "The simulated outcome vector contains non-finite values.",
            packCost=_round(cost, 4),
            simulationCount=int(array.size),
            nonFiniteCount=int(np.count_nonzero(~np.isfinite(array))),
        )

    n = int(array.size)
    minimum = int(min_simulation_count)
    if n < minimum:
        return _unavailable(
            REASON_INSUFFICIENT_RUNS,
            f"Financial RIP V3 needs at least {minimum} simulated packs so the "
            "top-1% conditional mean rests on enough observations; this run has "
            f"{n}. Re-run the simulation at the configured run count.",
            packCost=_round(cost, 4),
            simulationCount=n,
            requiredSimulationCount=minimum,
        )

    # One deterministic ascending sort backs every rank-based selection below.
    sorted_values = np.sort(array, kind="stable")
    buckets = TailBuckets(sorted_values)
    if not buckets.sufficient:
        return _unavailable(
            REASON_INSUFFICIENT_RUNS,
            "The outcome vector is too short to separate a top-1% bucket from a "
            "95th-99th percentile band without them overlapping.",
            packCost=_round(cost, 4),
            simulationCount=n,
        )

    raw_blocks: Dict[str, Dict[str, Any]] = {
        "true_win_frequency": compute_true_win_frequency_raw(array, cost),
        "typical_retention": compute_typical_retention_raw(array, cost),
        "loss_resilience": compute_loss_resilience_raw(array, cost),
        "realistic_upside": compute_realistic_upside_raw(array, cost, buckets),
        "jackpot_upside": compute_jackpot_upside_raw(array, cost, buckets),
        "base_economic_efficiency": compute_base_economic_efficiency_raw(array, cost, buckets),
    }

    components: Dict[str, Any] = {}
    normalized_audit: Dict[str, Any] = {}
    missing_inputs: List[str] = []

    for component in FINANCIAL_RIP_V3_COMPONENT_ORDER:
        sub_weights = FINANCIAL_RIP_V3_COMPONENT_INPUTS[component]
        sub_scores: Dict[str, Any] = {}
        component_score: Optional[float] = 0.0

        for metric, sub_weight in sub_weights.items():
            block_key, field = _RAW_INPUT_PATHS[metric]
            raw_value = raw_blocks[block_key].get(field)
            record = normalize_metric(metric, raw_value)
            record["subWeight"] = sub_weight
            normalized_audit[metric] = record
            sub_scores[metric] = {
                "score": _round(record["score"], 4),
                "raw": record["raw"],
                "subWeight": sub_weight,
                "clipped": record["clipped"],
            }
            if record["score"] is None:
                missing_inputs.append(metric)
                component_score = None
            elif component_score is not None:
                component_score += sub_weight * record["score"]

        weight = FINANCIAL_RIP_V3_WEIGHTS[component]
        available = component_score is not None
        components[component] = {
            "score": _round(component_score, 4) if available else None,
            "weight": weight,
            "contribution": _round(component_score * weight, 4) if available else None,
            "available": available,
            "subScores": sub_scores,
            "raw": raw_blocks[component],
        }

    if missing_inputs:
        result = _unavailable(
            REASON_MISSING_COMPONENT,
            "Required V3 inputs were unavailable: " + ", ".join(sorted(set(missing_inputs)))
            + ". A missing required metric makes the component and therefore "
            "Financial RIP V3 unavailable; it is never substituted with a "
            "neutral 50.",
            packCost=_round(cost, 4),
            simulationCount=n,
            missingInputs=sorted(set(missing_inputs)),
        )
        result["components"] = components
        return result

    score = sum(
        components[component]["score"] * FINANCIAL_RIP_V3_WEIGHTS[component]
        for component in FINANCIAL_RIP_V3_COMPONENT_ORDER
    )
    # Clamp is a numeric safety net only. With every component in 0-100 and the
    # weights summing to 1.0, the sum is already in range; this catches a future
    # arithmetic slip rather than capping anyone's influence.
    score = max(0.0, min(100.0, score))

    jackpot_value_share = raw_blocks["base_economic_efficiency"].get("jackpotValueShare")

    result: Dict[str, Any] = {
        "scoreVersion": FINANCIAL_RIP_V3_VERSION,
        "normalizationVersion": FINANCIAL_RIP_V3_NORMALIZATION_VERSION,
        "tailContractVersion": FINANCIAL_RIP_V3_TAIL_CONTRACT_VERSION,
        "configVersion": FINANCIAL_RIP_V3_CONFIG_VERSION,
        "status": STATUS_READY,
        "statusReason": None,
        "rankable": True,
        "score": _round(score, 4),
        "packCost": _round(cost, 4),
        "components": components,
        "depthAndRobustness": build_depth_and_robustness(
            chase_metrics, jackpot_value_share=jackpot_value_share
        ),
        "distributionDisclosures": {
            "simulationCount": n,
            "minValue": _round(_f(sorted_values[0]), 6),
            "maxValue": _round(_f(sorted_values[-1]), 6),
            "meanValue": _round(_f(array.mean()), 6),
            "medianValue": _round(_f(np.median(array)), 6),
            "totalRtpRatio": raw_blocks["base_economic_efficiency"]["totalRtpRatio"],
            "baseRtpExcludingTop1Pct": raw_blocks["base_economic_efficiency"]["baseRtpExcludingTop1Pct"],
            "jackpotValueShare": jackpot_value_share,
            "hardLossProbability": raw_blocks["loss_resilience"]["hardLossProbability"],
            "tailSelection": buckets.payload(cost),
            # P05 is disclosed for continuity with the V2 distribution surfaces.
            # It is a DISCLOSURE ONLY and carries zero V3 weight - no component
            # above reads it, and the contract tests prove that.
            "p05Value": _round(_f(np.percentile(array, 5)), 6),
            "p05IsScoredByV3": False,
        },
        "estimationDiagnostics": {
            "simulationCount": n,
            "requiredSimulationCount": minimum,
            "meetsMinimumRunCount": True,
            "jackpotObservationCount": int(buckets.jackpot.size),
            "realisticTailObservationCount": int(buckets.realistic.size),
            "distinctOutcomeCount": int(np.unique(sorted_values).size),
            "clippedInputs": sorted(
                metric for metric, record in normalized_audit.items() if record.get("clipped")
            ),
        },
        "sessionOpeningProfile": build_session_opening_profile(
            session_data,
            pack_cost=cost,
            true_win_probability=raw_blocks["true_win_frequency"].get("trueWinProbability"),
        ),
        "audit": {
            "weights": financial_rip_v3_weights_payload(),
            "normalizedInputs": normalized_audit,
        },
    }

    verification = verify_financial_rip_v3_score(result)
    result["audit"]["scoreVerification"] = verification
    if not verification["reconstructed"]:
        raise ValueError(
            "Financial RIP V3 score does not reconstruct from its component "
            f"contributions: {verification}"
        )
    return result


# ---------------------------------------------------------------------------
# Verification and validation
# ---------------------------------------------------------------------------

def verify_financial_rip_v3_score(result: Mapping[str, Any]) -> Dict[str, Any]:
    """Rebuild the score from the published contributions and compare.

    A component table whose contributions do not add up to the headline score is
    a scoring bug that renders as a plausible number, which is the worst
    possible failure mode. This runs on every build.
    """
    components = result.get("components") or {}
    contributions = [
        _f((components.get(key) or {}).get("contribution"))
        for key in FINANCIAL_RIP_V3_COMPONENT_ORDER
    ]
    if any(value is None for value in contributions):
        return {
            "reconstructed": False,
            "reason": "one_or_more_contributions_missing",
            "expected": _f(result.get("score")),
            "actual": None,
            "tolerance": SCORE_RECONSTRUCTION_TOLERANCE,
        }
    rebuilt = sum(contributions)  # type: ignore[arg-type]
    expected = _f(result.get("score"))
    if expected is None:
        return {
            "reconstructed": False,
            "reason": "score_missing",
            "expected": None,
            "actual": _round(rebuilt, 6),
            "tolerance": SCORE_RECONSTRUCTION_TOLERANCE,
        }
    # Contributions are published rounded to 4dp, so the reconstruction budget is
    # the rounding error of six terms plus the tolerance, not the tolerance alone.
    budget = SCORE_RECONSTRUCTION_TOLERANCE + 5e-5 * len(contributions)
    difference = abs(rebuilt - expected)
    return {
        "reconstructed": difference <= budget,
        "reason": None if difference <= budget else "contribution_sum_mismatch",
        "expected": expected,
        "actual": _round(rebuilt, 6),
        "difference": _round(difference, 9),
        "tolerance": _round(budget, 9),
    }


def validate_financial_rip_v3_payload(payload: Any) -> Tuple[bool, List[str]]:
    """Lightweight structural validator shared by persistence, publication and tests.

    Returns ``(ok, problems)``. Checks, in order:
      * the version matches this build's identifier,
      * all six components are present when status is ready,
      * the applied weights sum to 1.0,
      * the contributions reconstruct the score,
      * every score is finite and inside 0-100,
      * the required raw metrics are present,
      * ``rankable`` is False whenever required metrics are unavailable.
    """
    problems: List[str] = []
    if not isinstance(payload, Mapping):
        return False, ["payload is not a mapping"]

    version = payload.get("scoreVersion")
    if version != FINANCIAL_RIP_V3_VERSION:
        problems.append(f"scoreVersion {version!r} != {FINANCIAL_RIP_V3_VERSION!r}")
    if payload.get("normalizationVersion") != FINANCIAL_RIP_V3_NORMALIZATION_VERSION:
        problems.append("normalizationVersion does not match this build")

    status = payload.get("status")
    if status not in (STATUS_READY, STATUS_UNAVAILABLE):
        problems.append(f"unknown status {status!r}")

    if status != STATUS_READY:
        # An unavailable payload must not claim rankability or carry a score.
        if payload.get("rankable"):
            problems.append("rankable must be False when status is not ready")
        if payload.get("score") is not None:
            problems.append("score must be None when status is not ready")
        if not payload.get("statusReason"):
            problems.append("an unavailable payload must carry a statusReason")
        return (not problems), problems

    components = payload.get("components")
    if not isinstance(components, Mapping):
        return False, problems + ["components block is missing"]

    weight_total = 0.0
    for key in FINANCIAL_RIP_V3_COMPONENT_ORDER:
        block = components.get(key)
        if not isinstance(block, Mapping):
            problems.append(f"component {key!r} is missing")
            continue
        score = _f(block.get("score"))
        weight = _f(block.get("weight"))
        contribution = _f(block.get("contribution"))
        if score is None:
            problems.append(f"component {key!r} has no finite score")
        elif not (0.0 <= score <= 100.0):
            problems.append(f"component {key!r} score {score} is outside 0-100")
        if weight is None:
            problems.append(f"component {key!r} has no weight")
        else:
            weight_total += weight
            if abs(weight - FINANCIAL_RIP_V3_WEIGHTS[key]) > 1e-9:
                problems.append(f"component {key!r} weight {weight} != configured weight")
        if contribution is None:
            problems.append(f"component {key!r} has no contribution")
        raw = block.get("raw")
        if not isinstance(raw, Mapping) or not raw:
            problems.append(f"component {key!r} carries no raw metrics")

    if abs(weight_total - 1.0) > 1e-9:
        problems.append(f"applied weights sum to {weight_total}, not 1.0")

    score = _f(payload.get("score"))
    if score is None:
        problems.append("ready payload has no finite score")
    elif not (0.0 <= score <= 100.0):
        problems.append(f"score {score} is outside 0-100")

    verification = verify_financial_rip_v3_score(payload)
    if not verification.get("reconstructed"):
        problems.append(f"score does not reconstruct from contributions: {verification}")

    if not payload.get("rankable"):
        problems.append("a ready payload must be rankable")

    return (not problems), problems
