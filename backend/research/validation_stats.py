"""Statistics for the Collector Appeal / Financial RIP V3 validation. RESEARCH ONLY.

Deterministic by construction: every routine that draws randomness takes an
explicit ``random.Random`` or an integer seed and never touches the global RNG.
Two runs of the validation script with the same seed must produce byte-identical
artifacts, and a global-RNG call anywhere in this module would quietly break
that the moment an unrelated import consumed a draw.

SMALL-COHORT DISCIPLINE
-----------------------
The cohort is ~20-35 sets. At n = 22 a Spearman rho needs to exceed roughly 0.42
to clear p < 0.05 uncorrected, bootstrap intervals are wide and skewed, and a
partial correlation controlling for three variables is fitting 4 parameters to
22 points. Every routine here therefore reports its own n, and
:func:`interval_is_wide` and :func:`partial_correlation`'s ``overfitRisk`` flag
exist so the report can carry that warning per-row rather than once in a
footnote nobody maps back to a specific number.

Nothing here reads a database, a price, or a production score. It takes numbers
and returns numbers.
"""

from __future__ import annotations

import math
import random
from typing import Any, Callable, Dict, List, Mapping, Optional, Sequence, Tuple

# n below which an estimate is labelled fragile in every payload that carries one.
SMALL_SAMPLE_THRESHOLD = 30

# A bootstrap CI wider than this (on a correlation, so on a [-1, 1] scale) tells
# the reader the point estimate is close to uninformative.
WIDE_INTERVAL_THRESHOLD = 0.60


def _finite(value: Any) -> Optional[float]:
    try:
        parsed = float(value)
    except (TypeError, ValueError):
        return None
    return parsed if math.isfinite(parsed) else None


def paired(
    rows: Sequence[Mapping[str, Any]], x_key: str, y_key: str
) -> Tuple[List[float], List[float]]:
    """Rows where BOTH values are finite, in input order.

    Pairwise deletion, stated explicitly: a set missing one variable is dropped
    from that pair's statistic only, not from the study. Every payload reports
    the surviving n, so two cells of a matrix computed on different subsets can
    never be compared as if they shared a denominator.
    """
    xs: List[float] = []
    ys: List[float] = []
    for row in rows:
        x = _finite(row.get(x_key))
        y = _finite(row.get(y_key))
        if x is None or y is None:
            continue
        xs.append(x)
        ys.append(y)
    return xs, ys


# ---------------------------------------------------------------------------
# Ranks and correlations
# ---------------------------------------------------------------------------

def average_ranks(values: Sequence[float]) -> List[float]:
    """1-based midranks; tied values share their mean rank.

    Tie correction is not cosmetic here: Dual-Path Depth and several coverage
    counts tie routinely across a 22-set cohort, and ordinal ranks would bias
    every rho computed over them.
    """
    order = sorted(range(len(values)), key=lambda index: values[index])
    ranks = [0.0] * len(values)
    position = 0
    while position < len(order):
        end = position
        while end + 1 < len(order) and values[order[end + 1]] == values[order[position]]:
            end += 1
        mean_rank = (position + end) / 2.0 + 1.0
        for index in range(position, end + 1):
            ranks[order[index]] = mean_rank
        position = end + 1
    return ranks


def pearson(xs: Sequence[float], ys: Sequence[float]) -> Optional[float]:
    n = len(xs)
    if n < 3 or n != len(ys):
        return None
    mean_x = sum(xs) / n
    mean_y = sum(ys) / n
    cov = sum((x - mean_x) * (y - mean_y) for x, y in zip(xs, ys))
    var_x = sum((x - mean_x) ** 2 for x in xs)
    var_y = sum((y - mean_y) ** 2 for y in ys)
    if var_x <= 0 or var_y <= 0:
        return None
    return cov / math.sqrt(var_x * var_y)


def spearman(xs: Sequence[float], ys: Sequence[float]) -> Optional[float]:
    """Tie-corrected Spearman: Pearson on midranks."""
    if len(xs) < 3 or len(xs) != len(ys):
        return None
    return pearson(average_ranks(list(xs)), average_ranks(list(ys)))


def kendall_tau_b(xs: Sequence[float], ys: Sequence[float]) -> Optional[float]:
    """Kendall tau-b, the tie-corrected variant.

    tau-a would be biased low wherever ties exist, and ties are common in this
    cohort. Reported alongside Spearman because the two disagree in an
    informative way: tau-b is less sensitive to a single large rank swap, so a
    big Spearman/tau-b gap points at one or two influential sets rather than a
    broad reordering.
    """
    n = len(xs)
    if n < 3 or n != len(ys):
        return None
    concordant = discordant = 0
    ties_x = ties_y = 0
    for i in range(n - 1):
        for j in range(i + 1, n):
            dx = xs[i] - xs[j]
            dy = ys[i] - ys[j]
            product = dx * dy
            if product > 0:
                concordant += 1
            elif product < 0:
                discordant += 1
            else:
                if dx == 0:
                    ties_x += 1
                if dy == 0:
                    ties_y += 1
    denominator = math.sqrt((concordant + discordant + ties_x) * (concordant + discordant + ties_y))
    if denominator <= 0:
        return None
    return (concordant - discordant) / denominator


# ---------------------------------------------------------------------------
# Resampling
# ---------------------------------------------------------------------------

def bootstrap_correlation_ci(
    xs: Sequence[float],
    ys: Sequence[float],
    *,
    draws: int,
    seed: int,
    method: str = "spearman",
    confidence: float = 0.95,
) -> Dict[str, Any]:
    """Percentile bootstrap CI for a correlation, resampling PAIRS.

    Pairs are resampled together, never x and y independently - resampling them
    apart would destroy the association being estimated and produce an interval
    centred on zero by construction.

    A resample whose x or y is constant yields an undefined correlation; those
    draws are DISCARDED and counted in ``degenerateDraws`` rather than being
    coerced to 0.0. Coercing them would drag the interval toward zero in exactly
    the small, tied cohorts where the bias matters most.
    """
    estimator = spearman if method == "spearman" else pearson
    n = len(xs)
    point = estimator(xs, ys)
    payload: Dict[str, Any] = {
        "n": n,
        "method": method,
        "estimate": round(point, 6) if point is not None else None,
        "draws": int(draws),
        "seed": int(seed),
        "confidence": confidence,
        "ciLow": None,
        "ciHigh": None,
        "degenerateDraws": 0,
        "smallSample": n < SMALL_SAMPLE_THRESHOLD,
    }
    if point is None or n < 3 or draws <= 0:
        return payload

    rng = random.Random(seed)
    estimates: List[float] = []
    degenerate = 0
    for _ in range(int(draws)):
        picks = [rng.randrange(n) for _ in range(n)]
        sample_x = [xs[i] for i in picks]
        sample_y = [ys[i] for i in picks]
        value = estimator(sample_x, sample_y)
        if value is None:
            degenerate += 1
            continue
        estimates.append(value)

    payload["degenerateDraws"] = degenerate
    if not estimates:
        return payload

    estimates.sort()
    alpha = (1.0 - confidence) / 2.0
    low = _percentile(estimates, alpha * 100.0)
    high = _percentile(estimates, (1.0 - alpha) * 100.0)
    payload["ciLow"] = round(low, 6)
    payload["ciHigh"] = round(high, 6)
    payload["ciWidth"] = round(high - low, 6)
    payload["wideInterval"] = (high - low) > WIDE_INTERVAL_THRESHOLD
    payload["includesZero"] = low <= 0.0 <= high
    return payload


def permutation_p_value(
    xs: Sequence[float],
    ys: Sequence[float],
    *,
    draws: int,
    seed: int,
    method: str = "spearman",
) -> Dict[str, Any]:
    """Two-sided permutation p-value for a correlation.

    Shuffles y against a fixed x, which is the exact null "no association"
    without assuming normality or a t-distribution - appropriate here because
    several inputs are bounded shares with visibly non-normal distributions.

    Uses the (r + 1) / (draws + 1) estimator, so the p-value can never be
    reported as exactly 0. A permutation test cannot demonstrate a p smaller
    than its own resolution, and printing 0.000 would claim it had.
    """
    estimator = spearman if method == "spearman" else pearson
    n = len(xs)
    observed = estimator(xs, ys)
    payload: Dict[str, Any] = {
        "n": n,
        "method": method,
        "observed": round(observed, 6) if observed is not None else None,
        "draws": int(draws),
        "seed": int(seed),
        "pValue": None,
        "smallSample": n < SMALL_SAMPLE_THRESHOLD,
    }
    if observed is None or n < 3 or draws <= 0:
        return payload

    rng = random.Random(seed)
    shuffled = list(ys)
    at_least_as_extreme = 0
    valid = 0
    target = abs(observed)
    for _ in range(int(draws)):
        rng.shuffle(shuffled)
        value = estimator(xs, shuffled)
        if value is None:
            continue
        valid += 1
        if abs(value) >= target - 1e-12:
            at_least_as_extreme += 1

    payload["validDraws"] = valid
    payload["pValue"] = round((at_least_as_extreme + 1) / (valid + 1), 6) if valid else None
    return payload


def _percentile(sorted_values: Sequence[float], percent: float) -> float:
    """Linear-interpolation percentile over an ALREADY SORTED sequence."""
    if not sorted_values:
        raise ValueError("percentile of an empty sequence")
    if len(sorted_values) == 1:
        return float(sorted_values[0])
    rank = (percent / 100.0) * (len(sorted_values) - 1)
    low = math.floor(rank)
    high = math.ceil(rank)
    if low == high:
        return float(sorted_values[int(rank)])
    weight = rank - low
    return float(sorted_values[low] * (1.0 - weight) + sorted_values[high] * weight)


def percentile(values: Sequence[float], percent: float) -> Optional[float]:
    finite = sorted(v for v in (_finite(x) for x in values) if v is not None)
    return _percentile(finite, percent) if finite else None


# ---------------------------------------------------------------------------
# Multiple comparisons
# ---------------------------------------------------------------------------

def benjamini_hochberg(p_values: Sequence[Optional[float]]) -> List[Optional[float]]:
    """BH step-up adjusted p-values, returned in the INPUT order.

    Deterministic including ties: sorting is stabilised on the original index,
    so two identical p-values always adjust the same way regardless of dict
    iteration order upstream. The enforced monotonicity (an adjusted value never
    exceeds a larger raw p's adjusted value) is applied on the descending pass.

    None entries pass through as None and are excluded from m, because a
    statistic that could not be computed is not a test that was performed.
    Counting it would inflate m and make every real finding look weaker.
    """
    indexed = [(index, p) for index, p in enumerate(p_values) if p is not None]
    adjusted: List[Optional[float]] = [None] * len(p_values)
    m = len(indexed)
    if m == 0:
        return adjusted

    indexed.sort(key=lambda item: (item[1], item[0]))
    running = 1.0
    for rank in range(m, 0, -1):
        index, p = indexed[rank - 1]
        value = min(running, p * m / rank)
        running = value
        adjusted[index] = round(min(1.0, max(0.0, value)), 6)
    return adjusted


# ---------------------------------------------------------------------------
# Partial correlation
# ---------------------------------------------------------------------------

def partial_correlation(
    xs: Sequence[float],
    ys: Sequence[float],
    controls: Sequence[Sequence[float]],
    *,
    method: str = "spearman",
) -> Dict[str, Any]:
    """Correlation of x and y after linearly removing the controls from both.

    On ranks when ``method='spearman'`` - i.e. a Spearman partial, which removes
    a MONOTONE-linear component of the controls rather than a linear one on the
    raw scale.

    ``overfitRisk`` is set when n is small relative to the number of controls
    (fewer than 10 observations per control). At n=22 with three controls this
    fires, and it should: the residualisation has consumed four degrees of
    freedom and the resulting estimate carries far less information than its
    single number suggests.
    """
    n = len(xs)
    k = len(controls)
    payload: Dict[str, Any] = {
        "n": n,
        "controlCount": k,
        "method": method,
        "partial": None,
        "overfitRisk": bool(n < 10 * (k + 1)),
        "smallSample": n < SMALL_SAMPLE_THRESHOLD,
    }
    if n < k + 3 or any(len(c) != n for c in controls):
        return payload

    if method == "spearman":
        x_work = average_ranks(list(xs))
        y_work = average_ranks(list(ys))
        control_work = [average_ranks(list(c)) for c in controls]
    else:
        x_work, y_work = list(xs), list(ys)
        control_work = [list(c) for c in controls]

    design = [[1.0] + [c[i] for c in control_work] for i in range(n)]
    x_residual = _residuals(design, x_work)
    y_residual = _residuals(design, y_work)
    if x_residual is None or y_residual is None:
        return payload

    value = pearson(x_residual, y_residual)
    payload["partial"] = round(value, 6) if value is not None else None
    return payload


def _residuals(design: Sequence[Sequence[float]], target: Sequence[float]) -> Optional[List[float]]:
    """OLS residuals via normal equations with Gaussian elimination.

    Returns None on a singular system - collinear controls - rather than a
    pseudo-inverse result. A silently pseudo-inverted fit would emit a partial
    correlation that looks ordinary while resting on an arbitrary choice among
    infinitely many solutions.
    """
    n = len(design)
    p = len(design[0])
    ata = [[sum(design[i][a] * design[i][b] for i in range(n)) for b in range(p)] for a in range(p)]
    atb = [sum(design[i][a] * target[i] for i in range(n)) for a in range(p)]

    for column in range(p):
        pivot_row = max(range(column, p), key=lambda r: abs(ata[r][column]))
        if abs(ata[pivot_row][column]) < 1e-12:
            return None
        ata[column], ata[pivot_row] = ata[pivot_row], ata[column]
        atb[column], atb[pivot_row] = atb[pivot_row], atb[column]
        pivot = ata[column][column]
        for row in range(p):
            if row == column:
                continue
            factor = ata[row][column] / pivot
            if factor == 0.0:
                continue
            for col in range(column, p):
                ata[row][col] -= factor * ata[column][col]
            atb[row] -= factor * atb[column]

    coefficients = [atb[i] / ata[i][i] for i in range(p)]
    return [
        target[i] - sum(coefficients[a] * design[i][a] for a in range(p)) for i in range(n)
    ]


# ---------------------------------------------------------------------------
# Leave-one-out
# ---------------------------------------------------------------------------

def leave_one_out_correlation(
    xs: Sequence[float],
    ys: Sequence[float],
    labels: Sequence[str],
    *,
    method: str = "spearman",
) -> Dict[str, Any]:
    """Recompute the correlation with each observation removed in turn.

    At n ~ 22 a single set can carry a relationship, and a leave-one-out range
    that straddles zero means the headline rho is one observation's property
    rather than the cohort's. ``signFlips`` counts removals that reverse the
    sign - the bluntest possible statement of that fragility.
    """
    estimator = spearman if method == "spearman" else pearson
    n = len(xs)
    full = estimator(xs, ys)
    payload: Dict[str, Any] = {
        "n": n,
        "method": method,
        "full": round(full, 6) if full is not None else None,
        "min": None,
        "max": None,
        "signFlips": 0,
        "mostInfluential": None,
    }
    if full is None or n < 4:
        return payload

    values: List[Tuple[str, float]] = []
    for index in range(n):
        sub_x = [x for i, x in enumerate(xs) if i != index]
        sub_y = [y for i, y in enumerate(ys) if i != index]
        value = estimator(sub_x, sub_y)
        if value is None:
            continue
        label = labels[index] if index < len(labels) else str(index)
        values.append((label, value))

    if not values:
        return payload
    only = [v for _, v in values]
    payload["min"] = round(min(only), 6)
    payload["max"] = round(max(only), 6)
    payload["signFlips"] = sum(1 for v in only if (v < 0) != (full < 0))
    payload["mostInfluential"] = max(values, key=lambda item: abs(item[1] - full))[0]
    payload["rangeStraddlesZero"] = min(only) <= 0.0 <= max(only)
    return payload


# ---------------------------------------------------------------------------
# Ranking comparisons
# ---------------------------------------------------------------------------

def dense_ranks(scores: Mapping[str, Optional[float]]) -> Dict[str, Optional[int]]:
    """Rank 1 = best (highest score). Ties broken deterministically by key.

    The tie-break is by set id, not by input order, so a reordered cohort cannot
    silently produce a different leaderboard. Unscored sets rank None, never
    last: "unavailable" and "worst" are different facts.
    """
    scored = sorted(
        ((key, value) for key, value in scores.items() if _finite(value) is not None),
        key=lambda item: (-float(item[1]), str(item[0])),
    )
    ranks: Dict[str, Optional[int]] = {key: None for key in scores}
    for position, (key, _) in enumerate(scored, start=1):
        ranks[key] = position
    return ranks


def rank_comparison(
    baseline: Mapping[str, Optional[float]],
    variant: Mapping[str, Optional[float]],
    *,
    top_k: Sequence[int] = (3, 5, 10),
) -> Dict[str, Any]:
    """Full ranking-stability comparison between two score maps.

    Rank deltas are signed so POSITIVE means the set moved UP (toward rank 1),
    which is the direction a reader assumes when a set is described as "moving
    up". The raw subtraction has the opposite sign, so it is done once here
    rather than at each call site where it could be got wrong inconsistently.
    """
    base_ranks = dense_ranks(baseline)
    variant_ranks = dense_ranks(variant)
    shared = [
        key
        for key in baseline
        if base_ranks.get(key) is not None and variant_ranks.get(key) is not None
    ]

    deltas: Dict[str, int] = {}
    score_deltas: Dict[str, float] = {}
    for key in shared:
        deltas[key] = int(base_ranks[key]) - int(variant_ranks[key])
        b = _finite(baseline.get(key))
        v = _finite(variant.get(key))
        if b is not None and v is not None:
            score_deltas[key] = v - b

    absolute = [abs(d) for d in deltas.values()]
    n = len(shared)
    xs = [float(base_ranks[key]) for key in shared]
    ys = [float(variant_ranks[key]) for key in shared]

    overlaps: Dict[str, Optional[float]] = {}
    for k in top_k:
        overlaps[f"top{k}Overlap"] = _top_k_overlap(base_ranks, variant_ranks, k)

    return {
        "n": n,
        "spearman": round(spearman(xs, ys), 6) if n >= 3 else None,
        "kendallTauB": round(kendall_tau_b(xs, ys), 6) if n >= 3 else None,
        "meanAbsRankDelta": round(sum(absolute) / n, 4) if n else None,
        "medianAbsRankDelta": round(_median(absolute), 4) if n else None,
        "maxAbsRankDelta": max(absolute) if absolute else None,
        "meanAbsScoreDelta": (
            round(sum(abs(v) for v in score_deltas.values()) / len(score_deltas), 6)
            if score_deltas
            else None
        ),
        "pctMoving1Plus": _share(absolute, 1),
        "pctMoving3Plus": _share(absolute, 3),
        "pctMoving5Plus": _share(absolute, 5),
        **overlaps,
        "rankDeltas": deltas,
        "scoreDeltas": {k: round(v, 6) for k, v in score_deltas.items()},
        "largestGainers": sorted(deltas.items(), key=lambda i: -i[1])[:5],
        "largestLosers": sorted(deltas.items(), key=lambda i: i[1])[:5],
    }


def _top_k_overlap(
    base: Mapping[str, Optional[int]], variant: Mapping[str, Optional[int]], k: int
) -> Optional[float]:
    base_top = {key for key, rank in base.items() if rank is not None and rank <= k}
    variant_top = {key for key, rank in variant.items() if rank is not None and rank <= k}
    if not base_top:
        return None
    return round(len(base_top & variant_top) / len(base_top), 6)


def _median(values: Sequence[float]) -> float:
    ordered = sorted(values)
    n = len(ordered)
    if n == 0:
        return 0.0
    mid = n // 2
    return float(ordered[mid]) if n % 2 else (ordered[mid - 1] + ordered[mid]) / 2.0


def _share(absolute: Sequence[int], threshold: int) -> Optional[float]:
    if not absolute:
        return None
    return round(sum(1 for a in absolute if a >= threshold) / len(absolute), 6)


# ---------------------------------------------------------------------------
# Variance decomposition
# ---------------------------------------------------------------------------

def variance_decomposition(
    financial: Sequence[float], appeal: Sequence[float], weight: float
) -> Dict[str, Any]:
    """Exact decomposition of ``Var(O)`` for ``O = aF + bC``.

        Var(O) = a^2 Var(F) + b^2 Var(C) + 2ab Cov(F, C)

    All three terms are reported separately, because the cross term is the one
    that makes a nominal weight misleading: when F and C are positively
    correlated, adding C mostly re-expresses variation Overall RIP already had,
    and the appeal pillar's NOMINAL weight overstates how much independent
    movement it contributes.

    ``reconstructionError`` compares the decomposition against the variance of
    the directly-computed blend. It is not decoration - it is the check that the
    three published terms actually describe the published score. A test asserts
    it stays at numerical zero.

    Population variance (divisor n) throughout: this is a description of the
    cohort in hand, not an inference about a superpopulation of Pokemon sets.
    """
    n = len(financial)
    payload: Dict[str, Any] = {"n": n, "weight": float(weight)}
    if n < 2 or n != len(appeal):
        return payload

    a = 1.0 - float(weight)
    b = float(weight)
    var_f = _population_variance(financial)
    var_c = _population_variance(appeal)
    cov = _population_covariance(financial, appeal)

    term_f = a * a * var_f
    term_c = b * b * var_c
    term_cross = 2.0 * a * b * cov
    total = term_f + term_c + term_cross

    blended = [a * f + b * c for f, c in zip(financial, appeal)]
    direct = _population_variance(blended)
    sd_f = math.sqrt(var_f)
    sd_c = math.sqrt(var_c)
    weighted_sd_f = a * sd_f
    weighted_sd_c = b * sd_c
    weighted_total = weighted_sd_f + weighted_sd_c
    contributions = [b * (c - f) for f, c in zip(financial, appeal)]

    payload.update(
        {
            "aFinancial": round(a, 6),
            "bAppeal": round(b, 6),
            "varFinancial": round(var_f, 6),
            "varAppeal": round(var_c, 6),
            "covariance": round(cov, 6),
            "correlation": (
                round(cov / (sd_f * sd_c), 6) if sd_f > 0 and sd_c > 0 else None
            ),
            "termFinancial": round(term_f, 6),
            "termAppeal": round(term_c, 6),
            "termCross": round(term_cross, 6),
            "varOverallFromTerms": round(total, 6),
            "varOverallDirect": round(direct, 6),
            "reconstructionError": round(abs(total - direct), 12),
            "sdFinancial": round(sd_f, 6),
            "sdAppeal": round(sd_c, 6),
            "weightedSdFinancial": round(weighted_sd_f, 6),
            "weightedSdAppeal": round(weighted_sd_c, 6),
            # Share of WEIGHTED DISPERSION, not of variance: dispersion shares
            # add to 1 in the units a reader thinks in (score points), while
            # variance shares do not because of the cross term.
            "dispersionShareFinancial": (
                round(weighted_sd_f / weighted_total, 6) if weighted_total > 0 else None
            ),
            "dispersionShareAppeal": (
                round(weighted_sd_c / weighted_total, 6) if weighted_total > 0 else None
            ),
            # b*(C - F) is exactly how far the appeal term moves a set's Overall
            # score away from its financial-only score. This is the honest
            # answer to "how much does Collector Appeal actually do here?".
            "appealContributionMean": round(sum(contributions) / n, 6),
            "appealContributionMedian": round(_median(contributions), 6),
            "appealContributionMin": round(min(contributions), 6),
            "appealContributionMax": round(max(contributions), 6),
        }
    )
    return payload


def _population_variance(values: Sequence[float]) -> float:
    n = len(values)
    if n < 1:
        return 0.0
    mean = sum(values) / n
    return sum((v - mean) ** 2 for v in values) / n


def _population_covariance(xs: Sequence[float], ys: Sequence[float]) -> float:
    n = len(xs)
    if n < 1:
        return 0.0
    mean_x = sum(xs) / n
    mean_y = sum(ys) / n
    return sum((x - mean_x) * (y - mean_y) for x, y in zip(xs, ys)) / n


# ---------------------------------------------------------------------------
# Rank indistinguishability
# ---------------------------------------------------------------------------

DEFAULT_DOMINANCE_PROBABILITY = 0.95


def pairwise_dominance(
    draws_by_set: Mapping[str, Sequence[float]],
    *,
    dominance_probability: float = DEFAULT_DOMINANCE_PROBABILITY,
) -> Dict[str, Any]:
    """``P(score_A > score_B)`` across paired uncertainty draws, for every pair.

    Draws must be PAIRED - draw i of set A and draw i of set B come from the
    same scenario - so shared shocks (one pack-cost scenario, one pull-rate
    shock) cancel where they genuinely affect both sets. Comparing independently
    drawn marginals would overstate how separable two sets are.

    A pair is "reliably ordered" only when one direction reaches
    ``dominance_probability``. Everything else is reported as indistinguishable,
    which is the honest state for most adjacent sets in a tightly packed cohort.
    Ties within a draw count as half to each direction.
    """
    keys = sorted(draws_by_set)
    pairs: List[Dict[str, Any]] = []
    indistinguishable = 0

    for i, left in enumerate(keys):
        for right in keys[i + 1:]:
            a = list(draws_by_set[left])
            b = list(draws_by_set[right])
            n = min(len(a), len(b))
            if n == 0:
                continue
            wins = sum(1.0 for k in range(n) if a[k] > b[k])
            ties = sum(1.0 for k in range(n) if a[k] == b[k])
            probability = (wins + 0.5 * ties) / n
            reliable = (
                probability >= dominance_probability
                or (1.0 - probability) >= dominance_probability
            )
            if not reliable:
                indistinguishable += 1
            pairs.append(
                {
                    "setA": left,
                    "setB": right,
                    "pAGreaterThanB": round(probability, 6),
                    "draws": n,
                    "reliablyOrdered": reliable,
                }
            )

    return {
        "dominanceProbability": dominance_probability,
        "pairCount": len(pairs),
        "indistinguishablePairCount": indistinguishable,
        "indistinguishableShare": (
            round(indistinguishable / len(pairs), 6) if pairs else None
        ),
        "pairs": pairs,
    }


def rank_stability_bands(draws_by_set: Mapping[str, Sequence[float]]) -> Dict[str, Any]:
    """Per-set rank distribution across paired draws: median, IQR, 95% band, top-k.

    Ranks are recomputed WITHIN each draw, so a set's rank distribution reflects
    how it moves against a cohort that is itself moving - not against a frozen
    baseline. Ranking against fixed baseline scores would understate rank
    uncertainty substantially.
    """
    keys = sorted(draws_by_set)
    if not keys:
        return {"sets": {}}
    draw_count = min(len(draws_by_set[key]) for key in keys)

    per_set: Dict[str, List[int]] = {key: [] for key in keys}
    for index in range(draw_count):
        snapshot = {key: draws_by_set[key][index] for key in keys}
        ranks = dense_ranks(snapshot)
        for key in keys:
            if ranks[key] is not None:
                per_set[key].append(int(ranks[key]))

    out: Dict[str, Any] = {}
    for key, ranks in per_set.items():
        if not ranks:
            out[key] = {"draws": 0}
            continue
        ordered = sorted(ranks)
        out[key] = {
            "draws": len(ordered),
            "rankMedian": round(_median(ordered), 2),
            "rankP2_5": round(_percentile(ordered, 2.5), 2),
            "rankP25": round(_percentile(ordered, 25.0), 2),
            "rankP75": round(_percentile(ordered, 75.0), 2),
            "rankP97_5": round(_percentile(ordered, 97.5), 2),
            "rankIqr": round(_percentile(ordered, 75.0) - _percentile(ordered, 25.0), 2),
            "pTop3": round(sum(1 for r in ordered if r <= 3) / len(ordered), 6),
            "pTop5": round(sum(1 for r in ordered if r <= 5) / len(ordered), 6),
            "pTop10": round(sum(1 for r in ordered if r <= 10) / len(ordered), 6),
        }
    return {"drawCount": draw_count, "sets": out}


def score_intervals(draws_by_set: Mapping[str, Sequence[float]]) -> Dict[str, Any]:
    """Median, 95% interval and standard error of a score across draws."""
    out: Dict[str, Any] = {}
    for key in sorted(draws_by_set):
        values = sorted(v for v in (_finite(x) for x in draws_by_set[key]) if v is not None)
        if not values:
            out[key] = {"draws": 0}
            continue
        n = len(values)
        mean = sum(values) / n
        variance = sum((v - mean) ** 2 for v in values) / n
        out[key] = {
            "draws": n,
            "median": round(_median(values), 6),
            "mean": round(mean, 6),
            "p2_5": round(_percentile(values, 2.5), 6),
            "p97_5": round(_percentile(values, 97.5), 6),
            "standardError": round(math.sqrt(variance), 6),
        }
    return out


def interval_is_wide(low: Optional[float], high: Optional[float]) -> Optional[bool]:
    if low is None or high is None:
        return None
    return (high - low) > WIDE_INTERVAL_THRESHOLD
