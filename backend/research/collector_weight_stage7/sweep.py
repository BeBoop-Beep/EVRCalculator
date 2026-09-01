"""Stage VII: the Collector weight sweep, and the honesty machinery around it.

RESEARCH ONLY. Nothing here is read by production.

THE ONE THING THIS MODULE EXISTS TO PREVENT
-------------------------------------------
Raising Collector necessarily lowers Financial, because Chase is pinned at 0.06
and the weights must sum to one:

    financial = 0.94 - collector

So every ranking change observed between two Collector weights has TWO possible
causes, and they are not the same finding:

* **direct Collector effect** - the two products differ in ``C``, and the extra
  weight on that difference changed the comparison;
* **reallocation effect** - the two products may have identical ``C``; what
  moved them is Financial losing a point of weight while Chase kept its own.

:func:`decompose_pair` separates them exactly, and the rule is absolute: **for a
pair whose Collector values are equal, one hundred per cent of the change is
reallocation and none of it may be credited to Collector.** Collector Appeal V5
is a SET-level score, so every same-set pair is such a pair - which makes this
distinction the difference between a real result and a self-deception.

POPULATION SCHEMES
------------------
Collector is one set score repeated across every product of that set, so a
product-weighted analysis silently weights each set by how many SKUs it happens
to ship. :func:`set_balanced_weights` gives each set equal total weight, and
every contribution statistic is reported under both schemes.
"""

from __future__ import annotations

import itertools
import math
from dataclasses import dataclass
from typing import Any, Callable, Dict, List, Mapping, Optional, Sequence, Tuple

import numpy as np

from backend.research.chase_weight_stage6a import pairs as gate_pairs

#: Chase is fixed for the whole stage. Weight may not be taken from it.
CHASE_WEIGHT = 0.06

#: financial = FINANCIAL_BUDGET - collector
FINANCIAL_BUDGET = 1.0 - CHASE_WEIGHT


@dataclass(frozen=True)
class WeightPoint:
    """One (financial, collector, chase) point on the pre-registered grid."""

    collector: float
    selectable: bool
    role: str = ""

    @property
    def financial(self) -> float:
        return FINANCIAL_BUDGET - self.collector

    @property
    def chase(self) -> float:
        return CHASE_WEIGHT

    @property
    def key(self) -> str:
        return "%.4g/%.4g/%.4g" % (self.financial * 100, self.collector * 100,
                                   self.chase * 100)

    @property
    def weight_set(self) -> Dict[str, float]:
        return {"financial_rip": self.financial, "collector_appeal": self.collector,
                "chase": self.chase}

    def __post_init__(self) -> None:
        total = self.financial + self.collector + self.chase
        if abs(total - 1.0) > 1e-12:
            raise ValueError("%s sums to %.12f" % (self.key, total))
        if self.chase != CHASE_WEIGHT:
            raise ValueError("Chase must stay at %.2f" % CHASE_WEIGHT)


#: The pre-registered grid. Selectability is a property of the point, so a
#: 14%/15% diagnostic cannot be chosen by a later loop that forgot the ceiling.
SELECTABLE = (0.10, 0.11, 0.12, 0.13)
DIAGNOSTIC = (0.00, 0.05, 0.075, 0.14, 0.15)


def grid() -> List[WeightPoint]:
    points = [WeightPoint(collector=c, selectable=True) for c in SELECTABLE]
    roles = {0.00: "collector ablation", 0.05: "below-production boundary",
             0.075: "historical V4 provisional recommendation",
             0.14: "above ceiling; diagnostic only",
             0.15: "above ceiling; diagnostic only"}
    points += [WeightPoint(collector=c, selectable=False, role=roles[c])
               for c in DIAGNOSTIC]
    return sorted(points, key=lambda p: p.collector)


def score(point: WeightPoint, *, financial: Sequence[float],
          collector: Sequence[float], chase: Sequence[float]) -> List[float]:
    return [point.financial * float(financial[i]) + point.collector * float(collector[i])
            + point.chase * float(chase[i]) for i in range(len(financial))]


def baseline_financial_chase(*, financial: Sequence[float],
                             chase: Sequence[float]) -> List[float]:
    """``0.94F + 0.06K`` - the three-pillar analogue of the historical
    Financial-only baseline the inherited guardrails were written against."""
    return [FINANCIAL_BUDGET * float(financial[i]) + CHASE_WEIGHT * float(chase[i])
            for i in range(len(financial))]


# --------------------------------------------------------------------------
# Population schemes
# --------------------------------------------------------------------------

def set_balanced_weights(sets: Sequence[str]) -> np.ndarray:
    """Weight 1/n for each product of an n-product set, so sets weigh equally."""
    counts: Dict[str, int] = {}
    for name in sets:
        counts[name] = counts.get(name, 0) + 1
    return np.asarray([1.0 / counts[name] for name in sets], dtype=np.float64)


def weighted_moments(values: Sequence[float], weights: np.ndarray) -> Tuple[float, float]:
    array = np.asarray([float(v) for v in values], dtype=np.float64)
    total = float(weights.sum())
    mean = float((array * weights).sum() / total)
    variance = float((weights * (array - mean) ** 2).sum() / total)
    return mean, variance


def weighted_covariance_shares(components: Mapping[str, Sequence[float]],
                               weight_set: Mapping[str, float],
                               observation_weights: np.ndarray) -> Dict[str, float]:
    """Covariance-with-the-total shares under an arbitrary observation weighting.

    Sums to one by construction, exactly as the unweighted form does, so the
    product-weighted and set-balanced answers are directly comparable.
    """
    columns = {name: np.asarray([float(v) for v in values], dtype=np.float64)
               * float(weight_set.get(name, 0.0))
               for name, values in components.items()}
    total = sum(columns.values())
    total_mean, total_variance = weighted_moments(total, observation_weights)
    if total_variance <= 0:
        return {name: float("nan") for name in columns}
    out: Dict[str, float] = {}
    normaliser = float(observation_weights.sum())
    for name, column in columns.items():
        mean, _ = weighted_moments(column, observation_weights)
        covariance = float((observation_weights * (column - mean)
                            * (total - total_mean)).sum() / normaliser)
        out[name] = covariance / total_variance
    return out


# --------------------------------------------------------------------------
# Within-set structure
# --------------------------------------------------------------------------

def within_set_structure(rows: Sequence[Mapping[str, Any]], key: str) -> Dict[str, Any]:
    """Is ``key`` product-specific, mostly set-level, or exactly set-constant?"""
    by_set: Dict[str, List[float]] = {}
    for row in rows:
        by_set.setdefault(row["set"], []).append(float(row[key]))

    per_set = []
    varying = 0
    for name, values in sorted(by_set.items()):
        distinct = len({round(v, 12) for v in values})
        sd = float(np.std(values, ddof=1)) if len(values) > 1 else 0.0
        if len(values) > 1 and distinct > 1:
            varying += 1
        per_set.append({"set": name, "products": len(values), "distinct": distinct,
                        "min": min(values), "max": max(values), "sd": sd})
    multi = [p for p in per_set if p["products"] > 1]
    if not multi:
        verdict = "no multi-product sets"
    elif varying == 0:
        verdict = "exactly constant within every set"
    elif varying == len(multi):
        verdict = "genuinely product-specific"
    else:
        verdict = "mostly set-level (%d/%d sets vary)" % (varying, len(multi))
    return {"perSet": per_set, "multiProductSets": len(multi),
            "setsWithVariation": varying, "verdict": verdict}


# --------------------------------------------------------------------------
# The direct / reallocation decomposition
# --------------------------------------------------------------------------

def decompose_pair(*, financial: Tuple[float, float], collector: Tuple[float, float],
                   chase: Tuple[float, float], low: WeightPoint,
                   high: WeightPoint) -> Dict[str, Any]:
    """Split the change in one pair's score gap into its two causes.

    The gap between products a and b at weight point w is::

        gap(w) = w_F * dF + w_C * dC + w_K * dK

    Moving from ``low`` to ``high`` changes only ``w_F`` and ``w_C``, by ``-delta``
    and ``+delta``. So::

        gap(high) - gap(low) = delta * (dC - dF)

    The ``delta * dC`` half is Collector information. The ``-delta * dF`` half is
    reallocation - Financial simply carrying less weight. When ``dC == 0`` the
    Collector half is exactly zero and the whole movement is reallocation.
    """
    d_financial = financial[0] - financial[1]
    d_collector = collector[0] - collector[1]
    d_chase = chase[0] - chase[1]
    delta = high.collector - low.collector

    gap_low = (low.financial * d_financial + low.collector * d_collector
               + low.chase * d_chase)
    gap_high = (high.financial * d_financial + high.collector * d_collector
                + high.chase * d_chase)
    direct = delta * d_collector
    reallocation = -delta * d_financial
    return {
        "gapLow": gap_low, "gapHigh": gap_high,
        "change": gap_high - gap_low,
        "directCollector": direct,
        "reallocation": reallocation,
        "collectorIdentical": abs(d_collector) < 1e-12,
        "flipped": gap_low * gap_high < 0,
    }


def classify_reversals(*, rows: Sequence[Mapping[str, Any]], low: WeightPoint,
                       high: WeightPoint) -> Dict[str, Any]:
    """Every pair that reverses between two weight points, attributed to a cause.

    A reversal is counted as Collector-caused only when the two products' Collector
    scores actually differ AND the direct term is what carried the gap across zero.
    """
    financial = [float(r["financialRip"]) for r in rows]
    collector = [float(r["collectorAppeal"]) for r in rows]
    chase = [float(r["chaseNormalized"]) for r in rows]

    collector_caused = reallocation_only = 0
    same_set_reversals = cross_set_reversals = same_family_cross_set = 0
    examples: List[Dict[str, Any]] = []
    for i, j in itertools.combinations(range(len(rows)), 2):
        block = decompose_pair(
            financial=(financial[i], financial[j]),
            collector=(collector[i], collector[j]),
            chase=(chase[i], chase[j]), low=low, high=high)
        if not block["flipped"]:
            continue
        same_set = rows[i]["set"] == rows[j]["set"]
        if same_set:
            same_set_reversals += 1
        else:
            cross_set_reversals += 1
            if rows[i]["family"] == rows[j]["family"]:
                same_family_cross_set += 1
        # ATTRIBUTION BY DOMINANCE, not by mere presence of a Collector gap.
        #
        # change = delta * (dC - dF). A pair can have differing Collector scores
        # and still flip because Financial lost weight; crediting that to
        # Collector would be exactly the self-deception this module exists to
        # prevent. A reversal is Collector-caused only when the direct term is
        # the larger of the two.
        if block["collectorIdentical"] or abs(block["reallocation"]) >= abs(block["directCollector"]):
            reallocation_only += 1
        else:
            collector_caused += 1
            examples.append({
                "directTerm": block["directCollector"],
                "reallocationTerm": block["reallocation"],
                "winner": rows[j]["productName"] if block["gapHigh"] < 0
                          else rows[i]["productName"],
                "loser": rows[i]["productName"] if block["gapHigh"] < 0
                         else rows[j]["productName"],
                "financialGap": abs(financial[i] - financial[j]),
                "collectorGap": abs(collector[i] - collector[j]),
                "sameSet": same_set,
                "band": gate_pairs.band_of(abs(financial[i] - financial[j])),
            })
    examples.sort(key=lambda e: -e["financialGap"])
    return {
        "from": low.key, "to": high.key,
        "totalReversals": collector_caused + reallocation_only,
        "collectorCaused": collector_caused,
        "reallocationDominant": reallocation_only,
        "sameSetReversals": same_set_reversals,
        "crossSetReversals": cross_set_reversals,
        "sameFamilyCrossSetReversals": same_family_cross_set,
        "worstCollectorCaused": examples[:6],
        "maxFinancialGapCrossedByCollector": (
            examples[0]["financialGap"] if examples else 0.0),
    }


# --------------------------------------------------------------------------
# Inherited guardrails
# --------------------------------------------------------------------------

def rbo(left: Sequence[str], right: Sequence[str], p: float = 0.9) -> float:
    """Rank-biased overlap, the depth-weighted measure the V4 study introduced.

    NORMALISED FOR TRUNCATION. The textbook ``(1-p) * sum(A_d * p^(d-1))`` is
    defined over infinite lists; evaluated to a finite depth ``k`` it can only
    reach ``1 - p^k``, so two IDENTICAL five-item rankings would score 0.41
    rather than 1.0. Dividing by that achievable maximum makes the statistic a
    proper weighted average of the per-depth agreements, and identical lists
    score exactly 1.0 at any depth. At the 131-product depth used in the report
    ``p^k`` is about 1e-6 and the correction is immaterial - but a measure that
    is wrong on short lists cannot be trusted on long ones.
    """
    depth = min(len(left), len(right))
    if depth == 0:
        return 1.0
    total = 0.0
    seen_left: set = set()
    seen_right: set = set()
    for d in range(depth):
        seen_left.add(left[d])
        seen_right.add(right[d])
        total += (len(seen_left & seen_right) / (d + 1)) * (p ** d)
    achievable = (1.0 - p ** depth) / (1.0 - p)
    return total / achievable if achievable else 1.0


def inherited_guardrails(*, baseline: Sequence[float], candidate: Sequence[float],
                         labels: Sequence[str]) -> Dict[str, Any]:
    """The four ``OVERALL_RIP_PRODUCTION_GUARDRAILS``, read not restated."""
    from backend.desirability.scoring_config import OVERALL_RIP_PRODUCTION_GUARDRAILS
    from backend.research.chase_pillar_stage6.stats import rank, spearman

    thresholds = dict(OVERALL_RIP_PRODUCTION_GUARDRAILS)
    base_rank = rank([-v for v in baseline])
    cand_rank = rank([-v for v in candidate])
    movement = np.abs(cand_rank - base_rank)

    order_base = [labels[i] for i in np.argsort(base_rank)]
    order_cand = [labels[i] for i in np.argsort(cand_rank)]
    overlaps = {}
    for size in (5, 7, 10):
        overlaps["top%d" % size] = len(set(order_base[:size]) & set(order_cand[:size])) / size

    rho = spearman(list(baseline), list(candidate))
    mean_move = float(movement.mean())
    share5 = float(np.mean(movement >= 5))
    # COHORT-SCALE NORMALISATION.
    #
    # The two movement guardrails are absolute rank counts calibrated on the
    # ~21-SET cohort the V4 study ran on. They are not scale-free: "5 ranks out
    # of 21" is a quarter of the field, while "5 ranks out of 131" is under 4%
    # of it. Applied verbatim to a 131-product cohort they fail even at the
    # SHIPPING production weight, which is a statement about cohort size and not
    # about the weight. Both forms are therefore reported, and the report says
    # which one it is gating on.
    n = float(movement.size)
    historical_n = 21.0
    scaled_mean_threshold = thresholds["max_mean_absolute_rank_movement"] * n / historical_n
    scaled_rank_step = max(1.0, round(5.0 * n / historical_n))
    share_scaled = float(np.mean(movement >= scaled_rank_step))
    return {
        "cohortSize": int(n),
        "meanMovementAsShareOfCohort": mean_move / n,
        "historicalMeanThresholdAsShareOfCohort":
            thresholds["max_mean_absolute_rank_movement"] / historical_n,
        "scaledMeanThreshold": scaled_mean_threshold,
        "scaledRankStep": scaled_rank_step,
        "shareMovingScaledStep": share_scaled,
        "passMeanMovementScaled": mean_move <= scaled_mean_threshold,
        "passShare5Scaled": share_scaled <= thresholds["max_share_moving_5_plus_ranks"],
        "spearman": rho,
        "top5Overlap": overlaps["top5"],
        "top7Overlap": overlaps["top7"],
        "top10Overlap": overlaps["top10"],
        "rbo": rbo(order_base, order_cand),
        "meanAbsoluteRankMovement": mean_move,
        "medianAbsoluteRankMovement": float(np.median(movement)),
        "maxRankMovement": float(movement.max()),
        "shareMoving5Plus": share5,
        "productsChangingRank": int(np.sum(movement > 0)),
        "thresholds": thresholds,
        "passSpearman": rho is not None and rho >= thresholds["min_spearman_vs_financial_only"],
        "passTop5": overlaps["top5"] >= thresholds["min_top5_overlap"],
        "passMeanMovement": mean_move <= thresholds["max_mean_absolute_rank_movement"],
        "passShare5": share5 <= thresholds["max_share_moving_5_plus_ranks"],
    }
