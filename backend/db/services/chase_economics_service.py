"""Chase-economics selection and publication policy.

WHERE THIS SITS
---------------
    already-loaded run populations
      -> select_chase_cards      (which cards are worth publishing)
      -> pack_groups_for_product (how each SKU decomposes for the chase)
      -> target_chase_for_product (the pure math, unchanged)
      -> build_chase_economics_contract (the published shape)

Every function here is PURE over rows the caller already holds. The service
issues no queries of its own: the two whole-run populations it needs are the
same two ``rip_decision_service`` already reads for Top Chase, and loading them
twice would double a set-sized read to produce identical rows.

TOP 25 IS A PUBLICATION POLICY
------------------------------
``DEFAULT_PUBLISHED_CARD_LIMIT`` caps what gets STORED, because 25 cards covers
every card anyone would realistically chase while keeping the payload bounded.
It does not cap what can be COMPUTED: ``target_chase_for_product`` accepts any
card, and a future on-demand endpoint for an arbitrary card calls exactly the
same function with the same arguments. ``eligibleCardCount`` is published beside
the capped list so a reader can see how much was left out.

WHAT THIS DELIBERATELY IS NOT
-----------------------------
* NOT a ranking of products. Rows are emitted per SKU in the order given; the
  repository's comparison scope is ``within_product_family_only`` and nothing
  here declares a best way to chase a card.
* NOT a recommendation. No field labels a chase wise or foolish.
"""

from __future__ import annotations

import math
from typing import Any, Dict, Iterable, List, Mapping, Optional, Sequence

from backend.domain.pokemon.target_chase_economics import (
    TARGET_CHASE_CONTRACT_VERSION,
    PackGroup,
    loose_pack_odds_contract,
    model_assumptions_contract,
    target_chase_for_product,
)

CHASE_ECONOMICS_CONTRACT_VERSION = TARGET_CHASE_CONTRACT_VERSION

#: How many cards are STORED per set. Policy, not a limit on the calculator.
DEFAULT_PUBLISHED_CARD_LIMIT = 25

#: Published so a reader knows which question the card list answers.
SELECTION_POLICY = "top_market_price_pullable"

RECOVERY_MODEL_GROSS_MARKET_VALUE = "gross_market_value"


def _optional_float(value: Any) -> Optional[float]:
    if value is None or isinstance(value, bool):
        return None
    try:
        number = float(value)
    except (TypeError, ValueError):
        return None
    return number if math.isfinite(number) else None


def _positive(value: Any) -> Optional[float]:
    number = _optional_float(value)
    if number is None or number <= 0.0:
        return None
    return number


def _optional_str(value: Any) -> Optional[str]:
    if value is None:
        return None
    text = str(value).strip()
    return text or None


def select_chase_cards(
    price_rows: Iterable[Mapping[str, Any]],
    pull_denominators_by_variant_id: Mapping[str, Any],
    price_used_by_variant_id: Mapping[str, Any],
    *,
    limit: int = DEFAULT_PUBLISHED_CARD_LIMIT,
) -> List[Dict[str, Any]]:
    """The N priciest cards the model can actually produce.

    Two filters, in this order: the card must have a current Near Mint price,
    and it must have a positive modeled pull rate in the SAME run. A card the
    packs cannot produce is not a chase this contract can describe, however
    expensive it is - and a set's most expensive cards frequently ARE such
    cards, which is why the modeled population is the gate rather than an
    afterthought.

    ``price_used_by_variant_id`` may be missing an entry. That leaves
    ``targetValueUsedInEV`` as ``None`` rather than borrowing today's price,
    which would silently report zero drift between two bases we never compared.
    """
    eligible: List[Dict[str, Any]] = []
    for row in price_rows or []:
        if not isinstance(row, Mapping):
            continue
        variant_id = _optional_str(row.get("card_variant_id"))
        if variant_id is None:
            continue
        price = _positive(row.get("current_near_mint_price"))
        if price is None:
            continue
        denominator = _positive(pull_denominators_by_variant_id.get(variant_id))
        if denominator is None:
            continue

        eligible.append(
            {
                "cardId": _optional_str(row.get("card_id")),
                "cardVariantId": variant_id,
                "cardName": _optional_str(row.get("card_name")),
                "rarity": _optional_str(row.get("rarity_bucket")),
                "currentTargetMarketPrice": price,
                "currentPriceAsOf": _optional_str(row.get("price_as_of")),
                "targetValueUsedInEV": _positive(
                    price_used_by_variant_id.get(variant_id)
                ),
                "evPriceBasisAsOf": _optional_str(row.get("price_used_as_of")),
                "modeledProbability": 1.0 / denominator,
            }
        )

    # Price descending, then variant id ascending. The id tiebreak makes the
    # same run publish the same list regardless of row arrival order.
    eligible.sort(key=lambda c: (-c["currentTargetMarketPrice"], c["cardVariantId"]))
    return eligible[: max(0, int(limit))]


def pack_groups_for_product(
    product_row: Mapping[str, Any], *, target_probability_per_pack: Any
) -> List[PackGroup]:
    """How one scored SKU decomposes into random-pack groups for the chase.

    Every product modeled today produces exactly ONE group; the list shape
    exists so a future heterogeneous product needs no contract change.

    STAGE 2 EXCLUDES THE GUARANTEED COMPONENT from the per-pack value. The
    stored ``expected_value`` already contains the promo at its exact market
    price, so ``expected_value / pack_count`` would smear a certain component
    across random packs and overstate what each pack contributes to a chase.
    The promo is handed to ``target_chase_for_product`` separately, where it is
    added once per product opened.
    """
    p = _positive(target_probability_per_pack)
    if p is None:
        return []

    expected_value = _optional_float(product_row.get("expected_value"))
    if expected_value is None:
        return []

    promo_value = _positive(product_row.get("guaranteed_component_market_value"))
    random_pack_count = _positive(product_row.get("random_pack_count"))

    if promo_value is not None and random_pack_count is not None:
        pack_count = int(random_pack_count)
        random_value = expected_value - promo_value
    else:
        total_pack_count = _positive(product_row.get("pack_count"))
        if total_pack_count is None:
            return []
        pack_count = int(total_pack_count)
        random_value = expected_value

    if pack_count <= 0:
        return []

    return [
        PackGroup(
            pack_count=pack_count,
            target_probability_per_pack=p,
            # Today's Pokemon model puts a given card in at most one slot per
            # pack, so copies equal probability. The pure calculator does not
            # assume this; the equality is asserted HERE, where the model that
            # justifies it lives.
            expected_target_copies_per_pack=p,
            expected_pack_value=random_value / pack_count,
        )
    ]


def _card_block(
    card: Mapping[str, Any],
    product_rows: Sequence[Mapping[str, Any]],
    *,
    run_id: Optional[str],
) -> Dict[str, Any]:
    probability = _positive(card.get("modeledProbability"))
    ev_basis = _positive(card.get("targetValueUsedInEV"))
    current_price = _positive(card.get("currentTargetMarketPrice"))

    products: List[Dict[str, Any]] = []
    for row in product_rows:
        groups = pack_groups_for_product(row, target_probability_per_pack=probability)
        block = target_chase_for_product(
            product_price=row.get("product_market_cost"),
            pack_groups=groups,
            target_value_used_in_ev=ev_basis,
            current_target_market_price=current_price,
            guaranteed_component_market_value=(
                _positive(row.get("guaranteed_component_market_value")) or 0.0
            ),
        )
        products.append(
            {
                "sealedProductId": _optional_str(row.get("sealed_product_id")),
                "productName": _optional_str(row.get("product_name")),
                "productFamily": _optional_str(row.get("product_family")),
                "productPrice": _positive(row.get("product_market_cost")),
                **block,
            }
        )

    if ev_basis is None or current_price is None:
        delta = None
    else:
        delta = round(current_price - ev_basis, 12)

    return {
        "cardId": card.get("cardId"),
        "cardVariantId": card.get("cardVariantId"),
        "cardName": card.get("cardName"),
        "rarity": card.get("rarity"),
        "currentTargetMarketPrice": current_price,
        "currentPriceAsOf": card.get("currentPriceAsOf"),
        "currentPriceSource": "simulation_input_cards_with_near_mint_price",
        "targetValueUsedInEV": ev_basis,
        "evPriceBasisRunId": run_id,
        "evPriceBasisAsOf": card.get("evPriceBasisAsOf"),
        # Current MINUS EV basis. Positive means the card appreciated since the
        # run was priced.
        "targetPriceBasisDelta": delta,
        **loose_pack_odds_contract(target_probability_per_pack=probability),
        "products": products,
    }


def build_chase_economics_contract(
    *,
    cards: Sequence[Mapping[str, Any]],
    product_rows: Sequence[Mapping[str, Any]],
    run_id: Any,
    limit: int = DEFAULT_PUBLISHED_CARD_LIMIT,
    eligible_card_count: Optional[int] = None,
) -> Dict[str, Any]:
    """The published chase-economics contract for ONE set.

    ``eligible_card_count`` is the size of the population BEFORE the cap, so a
    reader can see that 25 of 187 chaseable cards were published rather than
    inferring that the set has 25.
    """
    resolved_run_id = _optional_str(run_id)
    card_list = [c for c in (cards or []) if isinstance(c, Mapping)]
    rows = [r for r in (product_rows or []) if isinstance(r, Mapping)]

    return {
        "contractVersion": CHASE_ECONOMICS_CONTRACT_VERSION,
        "recoveryModel": RECOVERY_MODEL_GROSS_MARKET_VALUE,
        "sourceCalculationRunId": resolved_run_id,
        "selectionPolicy": SELECTION_POLICY,
        "publishedCardLimit": int(limit),
        "eligibleCardCount": (
            len(card_list) if eligible_card_count is None else int(eligible_card_count)
        ),
        "modelAssumptions": model_assumptions_contract(),
        "cards": [
            _card_block(card, rows, run_id=resolved_run_id) for card in card_list
        ],
    }
