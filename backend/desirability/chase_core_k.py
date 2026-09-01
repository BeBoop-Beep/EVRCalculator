"""Core K - the production promotion of the Stage V-C product chase contract.

PRODUCTION MODULE. Nothing here imports from ``backend.research``. The research
module ``backend.research.product_chase_economics.contract`` remains the parity
reference; this module must reproduce its Core counts exactly, and the parity
harness asserts that against the frozen Stage V-C / VI cohort.

THE CONTRACT IS COUPLED, NOT TWO SEPARATE DECISIONS
---------------------------------------------------
    C_product = product_market_cost / random_pack_count
    CORE      : card value >= 3 * C_product

Stage V-A validated the 3x multiple; Stage V-B validated the denominator.
Neither is canonical alone, so there is no entry point here that accepts a
set-level cost. Applying the multiple to Stage IV's set-wide cheapest route is
NOT the validated rule and is the specific error Stage V exists to prevent.

WHY 3x, AND WHY NO PERCENTILE
-----------------------------
5x was rejected: it empties the Core on 9 of 131 real products and reduces 35 to
a single card. Stage IV carried a percentile cap as a guardrail; Stage V-A
measured it binding in 0 of 21 sets at every defensible width and REMOVED it.
There is deliberately no percentile term and no ``max(5C, V95)`` construction
anywhere in the validated lineage.

EXTENDED IS NOT PART OF OVERALL RIP
-----------------------------------
Stage V-C also defines an Extended tier at the 1x breakeven identity. Extended
is the broader universe and strictly contains Core. Overall RIP V11 consumes
Core K ONLY. Extended is retained here for diagnostics and set-page surfaces
and must never be substituted for Core.

MISSING IS NOT ZERO
-------------------
``None`` cost or ``None`` pack count yields ``None`` Core K, not ``0``. A
product with no cost has no chase economics; it does not have cheap chase
economics.
"""

from __future__ import annotations

from typing import Any, Dict, Iterable, List, Optional

#: Core floor, as a multiple of the product's own pack-equivalent cost.
CORE_MULTIPLE = 3.0

#: Extended floor - the breakeven identity, not a tuned constant. Diagnostics
#: only; Overall RIP V11 does not read it.
EXTENDED_MULTIPLE = 1.0

#: Recorded on every artifact so a published K can never be read without the
#: rule that produced it. Byte-identical to the Stage V-C research contract.
CORE_K_TIER_CONTRACT = (
    "core=3x, extended=1x of product_market_cost/random_pack_count"
)

#: The production Core K identity.
CORE_K_V1_VERSION = "chase_core_k_v1_stage5c_3x_pack_equivalent_cost"

#: Why a product can fail to receive native chase economics.
CORE_K_EXCLUSION_REASONS = {
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
    missing. This is the ONLY sanctioned cost basis: a Stage 2 product with
    guaranteed components still divides its own market cost by its own RANDOM
    pack count, never by its total component count and never by a sibling SKU's
    price.
    """
    cost = finite_positive(product_market_cost)
    count = finite_positive(random_pack_count)
    if cost is None or count is None:
        return None
    return cost / count


def core_threshold(pack_cost: float) -> float:
    """The absolute dollar Core floor for one product."""
    return CORE_MULTIPLE * float(pack_cost)


def compute_core_k(*, card_values: Optional[Iterable[Any]],
                   product_market_cost: Any,
                   random_pack_count: Any) -> Dict[str, Any]:
    """Core K for one product against its own pack-equivalent cost.

    ``card_values`` is the product's eligible card-value roster. Every value is
    counted once; de-duplication by card variant is the caller's responsibility
    and is performed upstream by the roster builder, exactly as Stage V-C does.
    """
    cost = finite_positive(product_market_cost)
    if cost is None:
        return _no_core_k("no_product_market_cost")
    count = finite_positive(random_pack_count)
    if count is None:
        return _no_core_k("no_random_pack_count")
    if card_values is None:
        return _no_core_k("no_product_market_cost",
                          detail="no eligible card-value roster was supplied")

    pack_cost = cost / count
    floor = CORE_MULTIPLE * pack_cost
    extended_floor = EXTENDED_MULTIPLE * pack_cost

    core = 0
    extended = 0
    eligible = 0
    for value in card_values:
        price = finite_positive(value)
        if price is None:
            continue
        eligible += 1
        if price >= extended_floor:
            extended += 1
            if price >= floor:
                core += 1

    return {
        "coreK": core,
        "extendedK": extended,
        "eligiblePriceCount": eligible,
        "packEquivalentCost": pack_cost,
        "coreThreshold": floor,
        "extendedThreshold": extended_floor,
        "productMarketCost": cost,
        "randomPackCount": int(round(count)),
        "version": CORE_K_V1_VERSION,
        "tierContract": CORE_K_TIER_CONTRACT,
        "status": "ready",
        "statusReason": None,
    }


def _no_core_k(reason: str, *, detail: Optional[str] = None) -> Dict[str, Any]:
    return {
        "coreK": None,
        "extendedK": None,
        "eligiblePriceCount": None,
        "packEquivalentCost": None,
        "coreThreshold": None,
        "extendedThreshold": None,
        "productMarketCost": None,
        "randomPackCount": None,
        "version": CORE_K_V1_VERSION,
        "tierContract": CORE_K_TIER_CONTRACT,
        "status": f"unavailable_{reason}",
        "statusReason": detail or CORE_K_EXCLUSION_REASONS[reason],
    }
