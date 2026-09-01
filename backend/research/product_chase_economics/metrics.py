"""Product-level Chase metrics built on one shared set decomposition.

RESEARCH ONLY.

WHAT IS NEW HERE VERSUS STAGE I-IV
----------------------------------
Everything per-PACK is reused from ``backend.research.set_chase_efficiency``
unchanged - the pack is the pack regardless of which box it shipped in. What
Stage V-C adds is the layer above it:

* aggregation from a pack to a PRODUCT of ``n`` random packs;
* accessibility expressed in three separate units (packs, product units and
  dollars) which must never be collapsed into one another;
* cost-gap and Beat-the-Buy in WHOLE PRODUCT granularity, because nobody can
  buy 3.4 Elite Trainer Boxes.

THE AGGREGATION ASSUMPTION IS INHERITED, NOT VALIDATED
------------------------------------------------------
    P(product contains >=1 chase) = 1 - (1 - p_pack)^n

Every scored product in production carries
``pack_independence_assumption = True``. There is therefore no non-IID product
simulation anywhere in this system to check this closed form against: it is not
an approximation of the production model, it IS the production model's own
assumption restated at product scale.

The correct wording, used throughout this module and its report, is
**model-consistent IID assumption** - never "empirically validated IID
behaviour". ``aggregate_to_product`` refuses to run on a product whose contract
does not assert independent packs rather than silently forcing the formula.
"""

from __future__ import annotations

import math
from typing import Any, Dict, Optional, Sequence

import numpy as np

from backend.research.set_chase_efficiency.chase_metrics import chase_journeys
from backend.research.set_chase_efficiency.metrics import (
    PRECISION,
    finite_positive,
    packs_for_horizon,
    whole_packs_for_horizon,
)

#: Probability horizons reported for every accessibility view.
HORIZONS = (0.50, 0.75, 0.90)


def _round(value: Optional[float]) -> Optional[float]:
    return None if value is None else round(float(value), PRECISION)


# --------------------------------------------------------------------------
# Phase 6 - product aggregation
# --------------------------------------------------------------------------

def aggregate_to_product(*, pack_probability: Any, random_pack_count: Any,
                         pack_independent: bool = True) -> Dict[str, Any]:
    """Per-product chase probability under the production IID contract.

    Returns ``None`` values, with a reason, when the product's contract does not
    assert independent packs. Forcing the closed form onto such a product would
    manufacture a number the production model does not stand behind.
    """
    probability = pack_probability
    try:
        probability = float(probability)
    except (TypeError, ValueError):
        probability = None
    count = finite_positive(random_pack_count)
    if probability is None or not (0.0 <= probability <= 1.0) or count is None:
        return {"supported": False, "reason": "missing pack probability or pack count",
                "assumption": "model_consistent_iid"}
    if not pack_independent:
        return {"supported": False, "reason": "not_pack_independent",
                "assumption": "model_consistent_iid"}

    n = int(round(count))
    miss = (1.0 - probability) ** n
    p_product = 1.0 - miss
    # Exactly one chase-containing PACK inside the product.
    p_exactly_one_pack = (n * probability * (1.0 - probability) ** (n - 1)) if n >= 1 else 0.0
    return {
        "supported": True,
        "reason": None,
        "assumption": "model_consistent_iid",
        "randomPackCount": n,
        "packProbability": _round(probability),
        "probabilityAtLeastOne": _round(p_product),
        "probabilityNone": _round(miss),
        "expectedChaseContainingPacks": _round(n * probability),
        "probabilityExactlyOneChasePack": _round(p_exactly_one_pack),
        "probabilityMultipleChasePacks": _round(max(0.0, p_product - p_exactly_one_pack)),
    }


def products_for_horizon(product_probability: Any, horizon: float) -> Optional[float]:
    """Expected whole/fractional product units to reach ``horizon`` confidence."""
    probability = finite_positive(product_probability)
    if probability is None or probability >= 1.0:
        return 1.0 if probability is not None else None
    if not (0.0 < horizon < 1.0):
        return None
    return math.log(1.0 - horizon) / math.log(1.0 - probability)


# --------------------------------------------------------------------------
# Phase 9 - three accessibility views, deliberately not collapsed
# --------------------------------------------------------------------------

def accessibility(*, pack_probability: Any, product_probability: Any,
                  pack_cost: Any, product_cost: Any,
                  random_pack_count: Any) -> Dict[str, Any]:
    """Pack-level, product-unit and cost-normalised accessibility.

    These three answer different questions and a booster box beats an ETB on the
    second while frequently losing on the third. Collapsing them would build the
    pack-count bias straight into the metric, which is exactly the artifact
    Phase 14 exists to detect.
    """
    p_pack = finite_positive(pack_probability)
    p_product = finite_positive(product_probability)
    unit_cost = finite_positive(pack_cost)
    product_price = finite_positive(product_cost)
    packs = finite_positive(random_pack_count)

    pack_view: Dict[str, Any] = {
        "anyChaseRatePerPack": _round(p_pack),
        "expectedPacksPerChase": _round(1.0 / p_pack) if p_pack else None,
    }
    product_view: Dict[str, Any] = {
        "anyChaseRatePerProduct": _round(p_product),
        "expectedProductsPerChase": _round(1.0 / p_product) if p_product else None,
    }
    cost_view: Dict[str, Any] = {}
    for horizon in HORIZONS:
        key = str(int(round(horizon * 100)))
        packs_exact = packs_for_horizon(p_pack, horizon)
        packs_whole = whole_packs_for_horizon(p_pack, horizon)
        units_exact = products_for_horizon(p_product, horizon)
        units_whole = None if units_exact is None else int(math.ceil(units_exact - 1e-12))
        pack_view[key] = {"packsExact": _round(packs_exact), "packsWhole": packs_whole}
        product_view[key] = {"productsExact": _round(units_exact), "productsWhole": units_whole}
        # Cost-normalised: the SAME confidence target, priced two ways.
        spend_packs = None if (packs_exact is None or unit_cost is None) else packs_exact * unit_cost
        spend_units = None if (units_whole is None or product_price is None) else units_whole * product_price
        cost_view[key] = {
            "spendPackGranular": _round(spend_packs),
            "spendWholeProduct": _round(spend_units),
            "wholeProductPremium": (
                None if (spend_packs is None or spend_units is None or spend_packs <= 0)
                else _round(spend_units / spend_packs)
            ),
        }
    return {"perPack": pack_view, "perProduct": product_view, "costNormalised": cost_view,
            "packEquivalentCost": _round(unit_cost), "productCost": _round(product_price),
            "randomPackCount": None if packs is None else int(round(packs))}


# --------------------------------------------------------------------------
# Phases 10-11 - whole-product discretisation of gap and Beat-the-Buy
# --------------------------------------------------------------------------

def _percentiles(values: np.ndarray) -> Dict[str, Any]:
    if values.size == 0:
        return {"mean": None, "median": None, "p25": None, "p75": None, "p90": None}
    ordered = np.sort(values)
    def q(fraction: float) -> float:
        return float(np.interp(fraction * (ordered.size - 1),
                               np.arange(ordered.size), ordered))
    return {"mean": _round(float(values.mean())), "median": _round(q(0.50)),
            "p25": _round(q(0.25)), "p75": _round(q(0.75)), "p90": _round(q(0.90))}


def whole_product_journey(*, qualifying: np.ndarray, chase_values: np.ndarray,
                          product_cost: Any, random_pack_count: Any) -> Dict[str, Any]:
    """Cost gap and Beat-the-Buy when only WHOLE products can be bought.

    The chaser walks the same recorded pack sequence, but pays in product units:
    reaching the chase on pack ``T`` costs ``ceil(T / n)`` whole products. This
    is strictly more expensive than the pack-granular view and is the honest
    figure for a format nobody sells by the pack.
    """
    price = finite_positive(product_cost)
    count = finite_positive(random_pack_count)
    if price is None or count is None:
        return {"journeys": 0, "reason": "missing product cost or pack count"}
    n = max(1, int(round(count)))
    packs_used, obtained = chase_journeys(np.asarray(qualifying, dtype=bool),
                                          np.asarray(chase_values, dtype=np.float64))
    if packs_used.size == 0:
        return {"journeys": 0, "reason": "no qualifying chase observed"}
    units = np.ceil(packs_used.astype(np.float64) / float(n))
    spend = units * price
    gap = spend - obtained
    stats = _percentiles(gap)
    stats.update({
        "journeys": int(packs_used.size),
        "reason": None,
        "productUnitsMean": _round(float(units.mean())),
        "beatTheBuy": _round(float((spend <= obtained).mean())),
        "probabilityGapNonPositive": _round(float((gap <= 0.0).mean())),
    })
    return stats


# --------------------------------------------------------------------------
# Phase 8 - Chase EV at product scale
# --------------------------------------------------------------------------

def product_chase_ev(*, pack_chase_ev: Any, random_pack_count: Any,
                     product_cost: Any, full_pack_ev: Any) -> Dict[str, Any]:
    """Chase EV per product, its return on the product's own price, and share.

    ``chaseEvReturn`` uses the product's whole market price as the denominator,
    which reconciles exactly with the pack-normalised form because the numerator
    is scaled by the same ``n``:

        (ev_pack * n) / product_cost  ==  ev_pack / (product_cost / n)
    """
    ev_pack = finite_positive(pack_chase_ev)
    count = finite_positive(random_pack_count)
    price = finite_positive(product_cost)
    full_pack = finite_positive(full_pack_ev)
    if ev_pack is None or count is None:
        return {"supported": False, "reason": "missing pack chase EV or pack count"}
    n = int(round(count))
    ev_product = ev_pack * n
    return {
        "supported": True,
        "reason": None,
        "chaseEvPerPack": _round(ev_pack),
        "chaseEvPerProduct": _round(ev_product),
        "chaseEvReturn": _round(ev_product / price) if price else None,
        "chaseEvReturnPackNormalised": (
            _round(ev_pack / (price / n)) if price else None),
        "chaseEvShareOfFullEv": (
            _round(ev_pack / full_pack) if full_pack else None),
        "fullPackEv": _round(full_pack),
    }
