"""Entertainment Cost: what you pay for the experience of opening.

WHAT THIS IS
------------
    Entertainment Cost = purchase price - modeled gross market value of contents

A direct, reversible transformation of two numbers that already exist on
``simulation_sealed_product_results``: ``product_market_cost`` and
``expected_value``. Pure: no database, no policy, no run resolution.

WHAT THIS DELIBERATELY IS NOT
-----------------------------
* NOT a score. Nothing here is fitted, weighted, calibrated or normalized, and
  nothing here may be ranked.
* NOT a judgement. A high entertainment cost is not "a bad buy" - buying
  entertainment is a legitimate purchase, and this module only prices it.
* NOT a liquidation estimate. See RECOVERY MODEL below.

RECOVERY MODEL
--------------
``gross_market_value``. Expected value is the raw mean of modeled Near Mint
market prices with NO deduction for marketplace fees, shipping, grading,
bid/ask spread or the practical impossibility of selling every card. The real
cash a seller nets is therefore LOWER than the value credited here, which makes
the entertainment cost published here a LOWER BOUND. This is disclosed on every
block rather than assumed, and no haircut is invented: the repository has no
empirically grounded one, and a made-up multiplier would look like a
measurement while being a guess.

Accessories - sleeves, dice, boxes, binders, code cards - carry ZERO value,
matching the existing ``ACCESSORY_VALUE_INCLUDED = False`` contract in the
Stage 2 composition module. This is inherited, not a new assumption.

MISSING INPUTS STAY MISSING
---------------------------
Every field is ``None`` rather than a placeholder when its input is absent,
non-numeric, non-finite or out of domain. A fabricated ``0.0`` is
indistinguishable on a page from a measured one, which makes it the more
dangerous of the two failure modes.
"""

from __future__ import annotations

import math
from typing import Any, Dict, Optional

ENTERTAINMENT_COST_CONTRACT_VERSION = "entertainment-cost-v1"

#: The only recovery basis this module implements. Published on every block.
RECOVERY_MODEL_GROSS_MARKET_VALUE = "gross_market_value"

#: Inherited from the Stage 2 composition contract, not decided here.
ACCESSORY_VALUE_INCLUDED = False

# Reason vocabulary. These strings MUST equal the identically-named constants in
# ``backend.db.services.rip_decision_service``; a test asserts it. They are
# duplicated rather than imported because a domain module importing a database
# service would invert the dependency direction for two string literals.
REASON_EXPECTED_VALUE_UNAVAILABLE = "expected_value_unavailable"
REASON_MARKET_PRICE_UNAVAILABLE = "market_price_unavailable"

#: Rounding strips IEEE-754 representation noise only (``0.1 + 0.2``). The
#: precision is far beyond any display need under the model assumptions, so
#: this never changes a value.
_PRECISION = 12


def _finite_float(value: Any) -> Optional[float]:
    """``value`` as a finite float, or ``None``. Booleans are not numbers here."""
    if value is None or isinstance(value, bool):
        return None
    try:
        number = float(value)
    except (TypeError, ValueError):
        return None
    if not math.isfinite(number):
        return None
    return number


def _positive(value: Any) -> Optional[float]:
    number = _finite_float(value)
    if number is None or number <= 0.0:
        return None
    return number


def _positive_int(value: Any) -> Optional[int]:
    number = _finite_float(value)
    if number is None or number <= 0.0:
        return None
    return int(number)


def _block(
    *,
    entertainment_cost: Optional[float],
    per_pack_equivalent: Optional[float],
    ratio: Optional[float],
    purchase_price: Optional[float],
    expected_value: Optional[float],
    pack_count: Optional[int],
    guaranteed_component_included: bool,
    available: bool,
    reason: Optional[str],
) -> Dict[str, Any]:
    """The ONE block shape. Available and unavailable results share it exactly.

    Two shapes would force every consumer to branch before reading a field, and
    a consumer that forgets to branch reads a missing key as a missing value.
    """
    return {
        "entertainmentCost": entertainment_cost,
        "entertainmentCostPerPackEquivalent": per_pack_equivalent,
        "entertainmentCostRatio": ratio,
        "purchasePrice": purchase_price,
        "expectedValue": expected_value,
        "packCount": pack_count,
        "recoveryModel": RECOVERY_MODEL_GROSS_MARKET_VALUE,
        "accessoryValueIncluded": ACCESSORY_VALUE_INCLUDED,
        "guaranteedComponentIncluded": bool(guaranteed_component_included),
        "available": available,
        "reason": reason,
        "contractVersion": ENTERTAINMENT_COST_CONTRACT_VERSION,
    }


def entertainment_cost_contract(
    *,
    purchase_price: Any,
    expected_value: Any,
    pack_count: Any,
    guaranteed_component_included: bool = False,
) -> Dict[str, Any]:
    """Entertainment Cost for ONE sealed product.

    ``expected_value`` is the stored ``expected_value`` for the SKU. For a
    Stage 2 product it ALREADY includes the guaranteed component's exact market
    value, so nothing is added here - adding it again would double-count the
    promo.

    Negative results are returned unchanged. A product whose modeled contents
    are worth more than its price has a negative entertainment cost, and
    clamping it to zero would erase the most interesting rows in the table.
    """
    price = _positive(purchase_price)
    value = _finite_float(expected_value)
    packs = _positive_int(pack_count)

    if value is None:
        return _block(
            entertainment_cost=None,
            per_pack_equivalent=None,
            ratio=None,
            purchase_price=price,
            expected_value=None,
            pack_count=packs,
            guaranteed_component_included=guaranteed_component_included,
            available=False,
            reason=REASON_EXPECTED_VALUE_UNAVAILABLE,
        )

    if price is None:
        return _block(
            entertainment_cost=None,
            per_pack_equivalent=None,
            ratio=None,
            purchase_price=None,
            expected_value=value,
            pack_count=packs,
            guaranteed_component_included=guaranteed_component_included,
            available=False,
            reason=REASON_MARKET_PRICE_UNAVAILABLE,
        )

    cost = round(price - value, _PRECISION)
    return _block(
        entertainment_cost=cost,
        # Survives independently: a missing pack count does not invalidate the
        # total, only the per-pack normalization used to compare formats.
        per_pack_equivalent=None if packs is None else round(cost / packs, _PRECISION),
        ratio=round(cost / price, _PRECISION),
        purchase_price=price,
        expected_value=value,
        pack_count=packs,
        guaranteed_component_included=guaranteed_component_included,
        available=True,
        reason=None,
    )


def unsupported_entertainment_cost(
    reason: str, *, purchase_price: Any = None, pack_count: Any = None
) -> Dict[str, Any]:
    """An explicitly unavailable block for a product we do not model.

    Emitted rather than omitted. A blister that vanishes from the table is
    indistinguishable from a blister that does not exist, and a reader
    comparing formats needs to know the difference.

    ``reason`` must come from the existing closed vocabulary in the Stage 1/2
    composition and decision modules. No reason string is invented here.
    """
    return _block(
        entertainment_cost=None,
        per_pack_equivalent=None,
        ratio=None,
        purchase_price=_positive(purchase_price),
        expected_value=None,
        pack_count=_positive_int(pack_count),
        guaranteed_component_included=False,
        available=False,
        reason=reason,
    )
