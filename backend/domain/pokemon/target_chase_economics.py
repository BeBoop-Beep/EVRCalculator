"""Target-card chase economics: what chasing ONE card actually costs.

THE QUESTION
------------
    If I want this specific card and choose to rip products until I pull it,
    what does that journey cost me compared with buying the single?

The point is NOT that opening packs is bad. The point is to price the
entertainment honestly, so someone who wants to open products can see what the
experience costs them relative to the alternative.

THE MODEL, AND ITS LIMITS
-------------------------
Three assumptions, all published on the contract via
``model_assumptions_contract`` so no reader has to infer them:

1. ``successfulProductFullyOpened`` - every product bought is opened in full,
   INCLUDING the one containing the target. This matches the sealed-product RIP
   use case ("buy a box, open the box"). It is NOT the same as opening packs
   until the target appears and reselling the remainder sealed, which is a
   different and un-modeled journey.
2. ``packIndependenceAssumption`` - packs are i.i.d. draws, inherited from the
   existing Stage 1/2 pipeline. Real collation is not perfectly independent.
3. ``retainedTargetCopies = 1`` - the chaser keeps ONE copy and sells
   everything else, duplicate targets included.

Every result here is EXACT UNDER THESE ASSUMPTIONS - the closed forms are not
approximations of a simulation, they are the model's answer. That is a
different and weaker claim than being exact about physical products, and the
``exactnessScope`` field says so.

WHY CLOSED FORM RATHER THAN MONTE CARLO
---------------------------------------
Products are i.i.d. draws and "open until the first product containing the
target" is a stopping time adapted to the sequence, so Wald's identity gives
``E[sum over the journey] = E[products] * E[value per product]`` exactly within
the model. Simulating would reproduce these numbers with added sampling noise
and minutes of runtime per set. A Monte Carlo agreement test exists
(``test_target_chase_monte_carlo.py``) and is test-only.

WHY ``incidentalRecovery`` AND NOT ``nonTargetRecovery``
--------------------------------------------------------
Because it legitimately includes DUPLICATE COPIES OF THE TARGET. The chaser
keeps one and sells the rest, so extra copies are recoverable exactly like any
other incidental pull. Calling the term "non-target" would misdescribe its
contents.

TWO PRICES, NOT ONE
-------------------
``target_value_used_in_ev`` is the price the stored EV was actually built from
(``simulation_input_cards.price_used``). ``current_target_market_price`` is what
buying the single costs today. They drift apart between runs. The retained copy
is removed from the journey value at the EV basis - removing it at today's
price would manufacture phantom recovery equal to the drift - while the
buy-versus-rip comparison uses today's price, because that is what the reader
would actually pay.

RECOVERY IS GROSS MARKET VALUE, NOT REALIZABLE CASH
---------------------------------------------------
``incidentalRecovery`` credits every saleable incidental pull at 100% of its
market price. No fees, shipping, liquidity, condition, or sell-through haircut
is modeled. Consequently ``ripAcquisitionCost`` is an optimistic modeled cost
under gross-market-value recovery; it is not a measured realizable cash
acquisition cost.
"""

from __future__ import annotations

import math
from dataclasses import dataclass
from typing import Any, Dict, Optional, Sequence

from backend.domain.pokemon.rip_decision_metrics import (
    packs_for_cumulative_probability,
)

TARGET_CHASE_CONTRACT_VERSION = "target-chase-economics-v1"

#: The published cumulative-probability thresholds. Ordered ascending; the
#: contract's monotonicity guarantee depends on that order.
CHASE_THRESHOLDS = (0.50, 0.75, 0.90, 0.95)

REASON_PROBABILITY_UNAVAILABLE = "modeled_probability_unavailable"
REASON_PRODUCT_PRICE_UNAVAILABLE = "product_price_unavailable"
REASON_NO_PACK_GROUPS = "no_pack_groups"

_PRECISION = 12


@dataclass(frozen=True)
class PackGroup:
    """One homogeneous block of random packs inside a product.

    ``target_probability_per_pack`` and ``expected_target_copies_per_pack`` are
    SEPARATE inputs on purpose. Under today's Pokemon model a specific card
    occupies at most one slot per pack, so they are numerically equal and the
    service populates the second from the first - but they are different
    quantities, and a future pack model with two target-capable slots must not
    require a contract rewrite to express.

    ``expected_pack_value`` is the gross market value of ONE RANDOM pack. For a
    Stage 2 product this must EXCLUDE the guaranteed component: the stored
    ``expected_value`` already contains the promo, and dividing the whole figure
    by the pack count would smear a certain component across random packs. The
    promo is passed separately to ``target_chase_for_product``.

    A product is a SEQUENCE of these. Every product modeled today has exactly
    one group; the sequence exists so a future collection product with packs
    from two sets is expressible without reshaping anything.
    """

    pack_count: int
    target_probability_per_pack: float
    expected_target_copies_per_pack: float
    expected_pack_value: float


def _finite_float(value: Any) -> Optional[float]:
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


def _non_negative(value: Any) -> Optional[float]:
    number = _finite_float(value)
    if number is None or number < 0.0:
        return None
    return number


def _threshold_key(prefix: str, threshold: float) -> str:
    return f"{prefix}For{int(round(threshold * 100))}PercentChance"


def model_assumptions_contract() -> Dict[str, Any]:
    """The assumptions every number in this module rests on.

    Attached to published contracts rather than documented only here: a reader
    holding the payload cannot open this docstring.
    """
    return {
        "successfulProductFullyOpened": True,
        "packIndependenceAssumption": True,
        "retainedTargetCopies": 1,
        "exactnessScope": "exact_under_model_assumptions",
        "recoveryModel": "gross_market_value",
        "contractVersion": TARGET_CHASE_CONTRACT_VERSION,
    }


def loose_pack_odds_contract(*, target_probability_per_pack: Any) -> Dict[str, Any]:
    """Per-pack odds and LOOSE-PACK thresholds for one card.

    These answer "if I could buy individual packs". They are NOT the number of
    packs a buyer ends up with after purchasing whole products - see
    ``packsPurchasedFor...`` on the product block, which is generally larger
    because products are bought whole.
    """
    p = _positive(target_probability_per_pack)
    block: Dict[str, Any] = {
        "modeledProbability": p,
        "impliedOddsOneInN": None if p is None else round(1.0 / p, _PRECISION),
        "expectedPacksToHit": None if p is None else round(1.0 / p, _PRECISION),
    }
    for threshold in CHASE_THRESHOLDS:
        block[_threshold_key("packs", threshold)] = packs_for_cumulative_probability(
            p, threshold
        )
    return block


def _product_block(
    *,
    pack_count: Optional[int],
    probability: Optional[float],
    expected_products: Optional[float],
    gross_spend: Optional[float],
    gross_pull_value: Optional[float],
    expected_target_copies: Optional[float],
    incidental_recovery: Optional[float],
    rip_acquisition_cost: Optional[float],
    target_value_used_in_ev: Optional[float],
    current_target_market_price: Optional[float],
    price_basis_delta: Optional[float],
    entertainment_premium: Optional[float],
    thresholds: Dict[str, Any],
    spend_distribution: Dict[str, Any],
    available: bool,
    reason: Optional[str],
) -> Dict[str, Any]:
    """The ONE product block shape, shared by available and unavailable results."""
    block: Dict[str, Any] = {
        "packCount": pack_count,
        "targetProbabilityPerProduct": probability,
        "expectedProductsToHit": expected_products,
        "grossSpend": gross_spend,
        "grossPullValue": gross_pull_value,
        "expectedTargetCopies": expected_target_copies,
        # Always 1 under the V1 model, published so a reader never has to guess
        # how many copies were treated as kept.
        "retainedTargetCopies": 1,
        "incidentalRecovery": incidental_recovery,
        "ripAcquisitionCost": rip_acquisition_cost,
        "targetValueUsedInEV": target_value_used_in_ev,
        "currentTargetMarketPrice": current_target_market_price,
        "targetPriceBasisDelta": price_basis_delta,
        "entertainmentPremium": entertainment_premium,
        "available": available,
        "reason": reason,
        "contractVersion": TARGET_CHASE_CONTRACT_VERSION,
    }
    block.update(thresholds)
    block.update(spend_distribution)
    return block


def _empty_thresholds() -> Dict[str, Any]:
    thresholds: Dict[str, Any] = {}
    for threshold in CHASE_THRESHOLDS:
        thresholds[_threshold_key("products", threshold)] = None
        thresholds[_threshold_key("packsPurchased", threshold)] = None
    return thresholds


def _empty_spend_distribution() -> Dict[str, Any]:
    return {"medianChaseSpend": None, "p90ChaseSpend": None, "p95ChaseSpend": None}


def _unavailable(reason: str, **known: Any) -> Dict[str, Any]:
    defaults: Dict[str, Any] = {
        "pack_count": None,
        "probability": None,
        "expected_products": None,
        "gross_spend": None,
        "gross_pull_value": None,
        "expected_target_copies": None,
        "incidental_recovery": None,
        "rip_acquisition_cost": None,
        "target_value_used_in_ev": None,
        "current_target_market_price": None,
        "price_basis_delta": None,
        "entertainment_premium": None,
        "thresholds": _empty_thresholds(),
        "spend_distribution": _empty_spend_distribution(),
        "available": False,
        "reason": reason,
    }
    defaults.update(known)
    return _product_block(**defaults)


def target_chase_for_product(
    *,
    product_price: Any,
    pack_groups: Sequence[PackGroup],
    target_value_used_in_ev: Any,
    current_target_market_price: Any,
    guaranteed_component_market_value: Any = 0.0,
) -> Dict[str, Any]:
    """The full chase journey for ONE target card through ONE sealed product.

    There is deliberately no ``guaranteed_target_copies`` parameter. A product
    whose composition guarantees the target has ``p_prod == 1``: the journey is
    one product with no thresholds and no accumulation, which is a different
    model rather than a parameter of this one. Passing the keyword raises
    ``TypeError``, which is the intended behaviour.
    """
    groups = [g for g in (pack_groups or []) if isinstance(g, PackGroup)]
    if not groups:
        return _unavailable(REASON_NO_PACK_GROUPS)

    price = _positive(product_price)
    if price is None:
        return _unavailable(REASON_PRODUCT_PRICE_UNAVAILABLE)

    # ---- Combine the groups -------------------------------------------------
    # p_prod = 1 - PROD_g (1 - p_g)^{k_g}: the chance that at least one pack in
    # the whole product carries the target. Accumulated as a product of misses
    # rather than a sum, because the groups are independent, not exclusive.
    miss = 1.0
    pack_count = 0
    product_value = 0.0
    expected_copies_per_product = 0.0
    for group in groups:
        k = _positive(group.pack_count)
        p = _finite_float(group.target_probability_per_pack)
        copies = _non_negative(group.expected_target_copies_per_pack)
        ev = _finite_float(group.expected_pack_value)
        if k is None or p is None or copies is None or ev is None:
            return _unavailable(REASON_PROBABILITY_UNAVAILABLE)
        if not 0.0 < p <= 1.0:
            return _unavailable(REASON_PROBABILITY_UNAVAILABLE)
        k_int = int(k)
        miss *= (1.0 - p) ** k_int
        pack_count += k_int
        product_value += k_int * ev
        expected_copies_per_product += k_int * copies

    promo_value = _non_negative(guaranteed_component_market_value) or 0.0
    # The guaranteed component is certain, so it is added ONCE PER PRODUCT, not
    # once per pack. Adding it per pack would multiply one promo by 36.
    product_value += promo_value

    p_prod = 1.0 - miss
    if p_prod <= 0.0:
        return _unavailable(REASON_PROBABILITY_UNAVAILABLE, pack_count=pack_count)

    # ---- Journey expectations (Wald, exact under the model) ------------------
    expected_products = 1.0 / p_prod
    gross_spend = price * expected_products
    gross_pull_value = product_value * expected_products
    expected_target_copies = expected_copies_per_product * expected_products

    # ---- One retained copy --------------------------------------------------
    # Removed at the EV BASIS, the same basis gross_pull_value was built on.
    # Removing it at today's price would invent recovery equal to the drift.
    ev_basis = _positive(target_value_used_in_ev)
    if ev_basis is None:
        incidental_recovery = None
        rip_acquisition_cost = None
    else:
        # Gross-market-value recovery on purpose. This is optimistic relative
        # to liquidation and must not be relabeled as realizable cash value.
        incidental_recovery = gross_pull_value - ev_basis
        rip_acquisition_cost = gross_spend - incidental_recovery

    current_price = _positive(current_target_market_price)
    if rip_acquisition_cost is None or current_price is None:
        entertainment_premium = None
    else:
        entertainment_premium = rip_acquisition_cost - current_price

    if ev_basis is None or current_price is None:
        price_basis_delta = None
    else:
        # Current MINUS EV basis: positive means the card appreciated since the
        # run was priced, so buying the single today costs more than the EV
        # credited it. The opposite ordering reads every drift backwards.
        price_basis_delta = current_price - ev_basis

    # ---- Thresholds ---------------------------------------------------------
    thresholds: Dict[str, Any] = {}
    spend_distribution: Dict[str, Any] = {}
    products_by_threshold: Dict[float, Optional[int]] = {}
    for threshold in CHASE_THRESHOLDS:
        products = packs_for_cumulative_probability(p_prod, threshold)
        products_by_threshold[threshold] = products
        thresholds[_threshold_key("products", threshold)] = products
        thresholds[_threshold_key("packsPurchased", threshold)] = (
            None if products is None else products * pack_count
        )

    for key, threshold in (("medianChaseSpend", 0.50), ("p90ChaseSpend", 0.90), ("p95ChaseSpend", 0.95)):
        products = products_by_threshold.get(threshold)
        spend_distribution[key] = None if products is None else round(products * price, _PRECISION)

    def _round(value: Optional[float]) -> Optional[float]:
        return None if value is None else round(value, _PRECISION)

    return _product_block(
        pack_count=pack_count,
        probability=_round(p_prod),
        expected_products=_round(expected_products),
        gross_spend=_round(gross_spend),
        gross_pull_value=_round(gross_pull_value),
        expected_target_copies=_round(expected_target_copies),
        incidental_recovery=_round(incidental_recovery),
        rip_acquisition_cost=_round(rip_acquisition_cost),
        target_value_used_in_ev=ev_basis,
        current_target_market_price=current_price,
        price_basis_delta=_round(price_basis_delta),
        entertainment_premium=_round(entertainment_premium),
        thresholds=thresholds,
        spend_distribution=spend_distribution,
        available=True,
        reason=None,
    )
