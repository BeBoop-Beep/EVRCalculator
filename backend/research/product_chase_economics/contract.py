"""The Stage V-C product-level Chase tier contract.

RESEARCH ONLY. Nothing here is read by production.

THE CONTRACT IS COUPLED, NOT TWO SEPARATE DECISIONS
---------------------------------------------------
Stage V-A validated multiples of 3x and 1x. Stage V-B validated a denominator.
Neither is canonical on its own, and this module exists so that they cannot be
used apart:

    C_product = product_market_cost / random_pack_count

    CORE      : card value >= 3 * C_product
    EXTENDED  : card value >= 1 * C_product

Applying 3x/1x to Stage IV's set-wide cheapest route is NOT the validated rule
and is the specific error Stage V exists to prevent. ``pack_equivalent_cost``
therefore takes a single product's own cost and pack count, and there is no
entry point that accepts a set-level cost.

WHY 1x IS THE EXTENDED FLOOR
----------------------------
1x is not a tuned constant. It is the breakeven identity: the point at which a
single card repays the pack it came out of. 3x was selected in Stage V-A because
it is the only Core multiple that stays non-degenerate under BOTH cost bases
tested - 5x empties the Core on 9 of 131 real products and reduces 35 to a
single card.

NO PERCENTILE
-------------
Stage IV carried a percentile cap as a guardrail. Stage V-A measured it binding
in 0 of 21 sets at every defensible width and removed it. There is no percentile
term here, deliberately.
"""

from __future__ import annotations

from typing import Any, Dict, List, Optional, Sequence

#: Core floor, as a multiple of the product's own pack-equivalent cost.
CORE_MULTIPLE = 3.0

#: Extended floor. The breakeven identity, not a tuned constant.
EXTENDED_MULTIPLE = 1.0

#: Tier labels.
TIER_CORE = "core"
TIER_EXTENDED = "extended"
TIER_NON_CHASE = "non_chase"

#: Why a product can fail to receive native chase economics. Nothing is dropped
#: silently; a product either scores or carries one of these.
PRODUCT_EXCLUSION_REASONS = {
    "no_product_market_cost":
        "the product has no finite positive current market price of its own, and "
        "Stage V-B forbids substituting a sibling SKU, pack_price * pack_count or MSRP",
    "no_random_pack_count":
        "the product has no positive random pack count, so a pack-equivalent cost "
        "cannot be formed",
    "unverified_composition":
        "the product carries neither composition_id nor composition_version, so its "
        "random pack count is not verified",
    "not_pack_independent":
        "the product's production contract does not assert independent packs, so the "
        "closed-form product aggregation may not be applied to it",
}


def finite_positive(value: Any) -> Optional[float]:
    """Return ``value`` as a float when it is finite and strictly positive."""
    try:
        number = float(value)
    except (TypeError, ValueError):
        return None
    if number != number or number in (float("inf"), float("-inf")):
        return None
    return number if number > 0 else None


def pack_equivalent_cost(*, product_market_cost: Any,
                         random_pack_count: Any) -> Optional[float]:
    """``C_product`` - the Stage V-B live cost authority.

    Returns ``None`` rather than a fabricated number when either input is
    missing. A product with no cost has no chase economics; it does not have
    cheap chase economics.
    """
    cost = finite_positive(product_market_cost)
    count = finite_positive(random_pack_count)
    if cost is None or count is None:
        return None
    return cost / count


def tier_thresholds(pack_cost: float) -> Dict[str, float]:
    """Absolute dollar floors for one product."""
    return {
        "core": CORE_MULTIPLE * pack_cost,
        "extended": EXTENDED_MULTIPLE * pack_cost,
    }


def classify(value: Any, pack_cost: float) -> str:
    """Tier for one card value against one product's pack-equivalent cost."""
    price = finite_positive(value)
    if price is None:
        return TIER_NON_CHASE
    if price >= CORE_MULTIPLE * pack_cost:
        return TIER_CORE
    if price >= EXTENDED_MULTIPLE * pack_cost:
        return TIER_EXTENDED
    return TIER_NON_CHASE


def product_basket(entities: Sequence[Any], pack_cost: float) -> Dict[str, Any]:
    """Core and Extended membership for one product.

    ``entities`` is any sequence of objects exposing ``entity_id``,
    ``card_variant_id`` and ``price``.

    Extended is the BROADER universe and strictly contains Core - it is not the
    ring between the two floors. Callers wanting the ring should difference the
    two, and the invariant ``core <= extended`` is asserted by the test suite.
    """
    thresholds = tier_thresholds(pack_cost)
    core: List[Any] = []
    extended: List[Any] = []
    for entity in entities:
        price = finite_positive(getattr(entity, "price", None))
        if price is None:
            continue
        if price >= thresholds["extended"]:
            extended.append(entity)
            if price >= thresholds["core"]:
                core.append(entity)
    return {
        "packEquivalentCost": pack_cost,
        "coreThreshold": thresholds["core"],
        "extendedThreshold": thresholds["extended"],
        "coreEntityIds": [int(e.entity_id) for e in core],
        "extendedEntityIds": [int(e.entity_id) for e in extended],
        "coreCardVariantIds": [str(getattr(e, "card_variant_id", "")) for e in core],
        "extendedCardVariantIds": [str(getattr(e, "card_variant_id", "")) for e in extended],
        "coreCount": len(core),
        "extendedCount": len(extended),
        "corePrices": sorted((float(e.price) for e in core), reverse=True),
        "extendedPrices": sorted((float(e.price) for e in extended), reverse=True),
    }
