"""Phase 5 and Phase 13: the directional contract and fixed-anchor normalization.

RESEARCH ONLY. Nothing here is read by production.

WHY NOT COHORT MIN/MAX
----------------------
The brief forbids cohort min/max normalization, and the reason matters more than
the rule. Overall RIP is a 0-100 score whose components are anchored to
interpretable absolutes, so a product's score does not move when a different
product is added to the cohort. A min/max Chase pillar would break that: adding
one $400 sealed product to the cohort would silently rescore all 130 others, and
the Phase-24 temporal report would then be measuring the cohort's composition
rather than the market. Every transform below is therefore a fixed function of
one product's own numbers.

THE DIRECTIONAL CONTRACT (Phase 5)
----------------------------------
=========================  =========  ==========================================
metric                     direction  why
=========================  =========  ==========================================
Chase EV Return            higher     more chase value returned per dollar spent
Any-Chase per product      higher     a unit of this product hits more often
50% Chase Spend            LOWER      fewer dollars to reach even odds
Core K                     higher*    more qualifying chases - but see below
=========================  =========  ==========================================

\\* Core K's direction is asserted but its CURVATURE is not. The brief is
explicit that 30 Core chases should not necessarily be worth twice 15, so four
transforms are provided and Phase 13 selects between them on stated grounds -
never on which produces a nicer ranking.

ANCHOR DISCIPLINE
-----------------
Every anchor below is a round, externally meaningful number chosen BEFORE the
cohort distribution was inspected, and each carries the reason it was chosen.
:func:`anchor_stress` re-runs any candidate under deliberately displaced anchors
so a result that depends on the exact anchor can be detected and rejected.
"""

from __future__ import annotations

import math
from typing import Any, Callable, Dict, Mapping, Optional, Sequence

#: Direction of merit for each surviving Stage V-C candidate.
DIRECTION: Dict[str, str] = {
    "chaseEvReturn": "higher",
    "anyChasePerProduct": "higher",
    "chaseSpend50": "lower",
    "coreK": "higher",
}


def _finite(value: Any) -> Optional[float]:
    try:
        number = float(value)
    except (TypeError, ValueError):
        return None
    return None if number != number or number in (float("inf"), float("-inf")) else number


def _clamp(value: float, low: float = 0.0, high: float = 100.0) -> float:
    return max(low, min(high, value))


# --------------------------------------------------------------------------
# Any-Chase probability per product
# --------------------------------------------------------------------------

#: A product unit that hits a Core chase half the time is an unambiguously
#: strong chase product; one that hits 1 in 100 is unambiguously weak. The
#: anchors are the two ends of that plain-language statement, on a log scale
#: because the interesting range spans two orders of magnitude (the cohort runs
#: from under 1% for a single pack to near 50% for a booster box).
ANY_CHASE_FLOOR = 0.01
ANY_CHASE_CEILING = 0.50


def normalize_any_chase(probability: Any, *, floor: float = ANY_CHASE_FLOOR,
                        ceiling: float = ANY_CHASE_CEILING) -> Optional[float]:
    """0-100 from a per-unit probability, log-spaced between fixed anchors."""
    p = _finite(probability)
    if p is None or p <= 0:
        return 0.0
    if p >= ceiling:
        return 100.0
    if p <= floor:
        return 0.0
    return _clamp(100.0 * math.log(p / floor) / math.log(ceiling / floor))


# --------------------------------------------------------------------------
# 50% Chase Spend - the LOWER-is-better metric
# --------------------------------------------------------------------------

#: $100 to reach even odds of a Core chase is excellent; $10,000 is effectively
#: unreachable for a normal buyer. Log-spaced for the same reason: the cohort
#: spans roughly two decades of dollars.
SPEND_BEST = 100.0
SPEND_WORST = 10000.0


def normalize_chase_spend(spend: Any, *, best: float = SPEND_BEST,
                          worst: float = SPEND_WORST) -> Optional[float]:
    """0-100 from dollars-to-even-odds. Inverted: cheaper is better.

    A product with no attainable chase at all (no Core, so no finite spend)
    scores 0 rather than being dropped - it is the worst possible chase
    accessibility, not missing data.
    """
    dollars = _finite(spend)
    if dollars is None or dollars <= 0:
        return 0.0
    if dollars <= best:
        return 100.0
    if dollars >= worst:
        return 0.0
    return _clamp(100.0 * math.log(worst / dollars) / math.log(worst / best))


# --------------------------------------------------------------------------
# Chase EV Return
# --------------------------------------------------------------------------

#: Chase EV Return is chase-only expected value per dollar of product price. It
#: is bounded well below 1 in practice because it counts ONLY qualifying chase
#: cards. 0.35 is set as the "full marks" anchor because a product returning a
#: third of its price in chase value alone is exceptional; 0 is the floor.
EV_RETURN_CEILING = 0.35


def normalize_ev_return(value: Any, *, ceiling: float = EV_RETURN_CEILING) -> Optional[float]:
    """0-100, linear in return. Linear because the quantity is already a ratio."""
    ratio = _finite(value)
    if ratio is None or ratio <= 0:
        return 0.0
    return _clamp(100.0 * ratio / ceiling)


# --------------------------------------------------------------------------
# Core K - four curvatures, none of them assumed
# --------------------------------------------------------------------------

#: The saturation point. Ten distinct qualifying Core chases is already a rich
#: hunt; the eleventh changes a buyer's experience far less than the second did.
CORE_K_SATURATION = 10.0
CORE_K_CAP = 15.0


def core_k_raw(k: Any, *, saturation: float = CORE_K_SATURATION) -> Optional[float]:
    """Strictly linear. The null hypothesis: every extra chase is worth the same."""
    count = _finite(k)
    if count is None or count <= 0:
        return 0.0
    return _clamp(100.0 * count / saturation)


def core_k_log(k: Any, *, saturation: float = CORE_K_SATURATION) -> Optional[float]:
    """log1p. Diminishing but never flat."""
    count = _finite(k)
    if count is None or count <= 0:
        return 0.0
    return _clamp(100.0 * math.log1p(count) / math.log1p(saturation))


def core_k_capped(k: Any, *, cap: float = CORE_K_CAP) -> Optional[float]:
    """Linear then hard-capped. Crude, and included precisely as the crude control."""
    count = _finite(k)
    if count is None or count <= 0:
        return 0.0
    return _clamp(100.0 * min(count, cap) / cap)


def core_k_saturating(k: Any, *, saturation: float = CORE_K_SATURATION) -> Optional[float]:
    """A smooth Michaelis-Menten style curve: ``100 * k / (k + s)`` rescaled.

    Never reaches 100, which is the honest shape for "breadth of opportunity":
    there is no number of chase cards that makes a product perfect, and each
    additional one is worth strictly less than the last with no discontinuity.
    """
    count = _finite(k)
    if count is None or count <= 0:
        return 0.0
    return _clamp(200.0 * count / (count + saturation))


CORE_K_TRANSFORMS: Dict[str, Callable[..., Optional[float]]] = {
    "raw": core_k_raw,
    "log1p": core_k_log,
    "capped": core_k_capped,
    "saturating": core_k_saturating,
}

NORMALIZERS: Dict[str, Callable[..., Optional[float]]] = {
    "anyChasePerProduct": normalize_any_chase,
    "chaseSpend50": normalize_chase_spend,
    "chaseEvReturn": normalize_ev_return,
}


def normalize_row(row: Mapping[str, Any], *, core_k_transform: str = "saturating"
                  ) -> Dict[str, Optional[float]]:
    """Every Chase factor for one product, on one fixed 0-100 scale."""
    return {
        "anyChasePerProduct": normalize_any_chase(row.get("anyChasePerProduct")),
        "chaseSpend50": normalize_chase_spend(row.get("chaseSpend50")),
        "chaseEvReturn": normalize_ev_return(row.get("chaseEvReturn")),
        "coreK": CORE_K_TRANSFORMS[core_k_transform](row.get("coreK")),
    }


def anchor_stress(normalizer: Callable[..., Optional[float]], values: Sequence[Any],
                  variants: Mapping[str, Mapping[str, float]]) -> Dict[str, Any]:
    """Re-normalize a column under displaced anchors and report rank stability.

    A transform whose RANKING survives its anchors being moved is carrying
    information about the products. One whose ranking does not is carrying
    information about the anchors, and Phase 13 rejects it.
    """
    from backend.research.chase_pillar_stage6.stats import spearman

    base = [normalizer(v) for v in values]
    out: Dict[str, Any] = {}
    for label, keywords in variants.items():
        shifted = [normalizer(v, **keywords) for v in values]
        pairs = [(a, b) for a, b in zip(base, shifted) if a is not None and b is not None]
        out[label] = {
            "anchors": dict(keywords),
            "spearmanVsBase": spearman([p[0] for p in pairs], [p[1] for p in pairs]),
            "meanAbsoluteScoreShift": (
                sum(abs(a - b) for a, b in pairs) / len(pairs) if pairs else None),
            "saturatedAtCeiling": sum(1 for _, b in pairs if b >= 99.999),
            "saturatedAtFloor": sum(1 for _, b in pairs if b <= 0.001),
        }
    return out
