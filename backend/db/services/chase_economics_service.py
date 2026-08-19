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
from datetime import datetime, timezone
from typing import Any, Dict, Iterable, List, Mapping, Optional, Sequence, Tuple

from backend.db.services.rip_decision_service import (
    _load_current_run_product_rows,
    _load_run_near_mint_prices,
    _load_run_population,
    INPUT_CARDS_TABLE,
)

from backend.domain.pokemon.sealed_product_stage2_composition import (
    REASON_MISSING_PROMO_PRICE,
    REASON_NO_VERIFIED_COMPOSITION,
)
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
                "currentPriceAsOf": _optional_str(
                    row.get("current_near_mint_price_captured_at")
                ),
                "currentPriceObservationSource": _optional_str(
                    row.get("current_near_mint_price_source")
                ),
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
) -> Tuple[List[PackGroup], Optional[str]]:
    """How one scored SKU decomposes into random-pack groups for the chase.

    Returns ``(pack_groups, reason)``. Every product modeled today produces
    exactly ONE group; the list shape exists so a future heterogeneous product
    needs no contract change.

    STAGE 2 EXCLUDES THE GUARANTEED COMPONENT from the per-pack value. The
    stored ``expected_value`` already contains the promo at its exact market
    price, so ``expected_value / pack_count`` would smear a certain component
    across random packs and overstate what each pack contributes to a chase.
    The promo is handed to ``target_chase_for_product`` separately, where it is
    added once per product opened.

    FAIL CLOSED ON A HALF-POPULATED STAGE 2 ROW. The Stage 2 path is taken only
    when BOTH ``guaranteed_component_market_value`` and ``random_pack_count``
    are present and valid; when NEITHER is present this is a genuine Stage 1
    product and the Stage 1 path applies unchanged. But a row carrying EXACTLY
    ONE of the two is not a genuine Stage 1 product - it is an incompletely
    populated Stage 2 row - and falling through to the Stage 1 path would
    divide the full ``expected_value`` (promo included) across the random
    packs, smearing a certain component across chance and producing a
    confident wrong number with no signal. Such a row is refused outright, with
    the reason drawn from the existing Stage 2 vocabulary.
    """
    p = _positive(target_probability_per_pack)
    if p is None:
        return [], None

    expected_value = _optional_float(product_row.get("expected_value"))
    if expected_value is None:
        return [], None

    promo_value = _positive(product_row.get("guaranteed_component_market_value"))
    random_pack_count = _positive(product_row.get("random_pack_count"))

    if promo_value is not None and random_pack_count is not None:
        pack_count = int(random_pack_count)
        random_value = expected_value - promo_value
    elif promo_value is None and random_pack_count is None:
        total_pack_count = _positive(product_row.get("pack_count"))
        if total_pack_count is None:
            return [], None
        pack_count = int(total_pack_count)
        random_value = expected_value
    elif promo_value is None:
        # random_pack_count present, but the promo's market value is missing or
        # invalid: the certain component cannot be priced or excluded.
        return [], REASON_MISSING_PROMO_PRICE
    else:
        # promo value present, but random_pack_count is missing or invalid: the
        # composition needed to split random packs from the guaranteed
        # component was never resolved.
        return [], REASON_NO_VERIFIED_COMPOSITION

    if pack_count <= 0:
        return [], None

    return (
        [
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
        ],
        None,
    )


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
        groups, _stage2_reason = pack_groups_for_product(
            row, target_probability_per_pack=probability
        )
        block = target_chase_for_product(
            product_price=row.get("product_market_cost"),
            pack_groups=groups,
            target_value_used_in_ev=ev_basis,
            current_target_market_price=current_price,
            guaranteed_component_market_value=(
                _positive(row.get("guaranteed_component_market_value")) or 0.0
            ),
        )
        # The pure calculator only knows that it received no pack groups.  The
        # integration layer knows the more useful reason: this was a partially
        # populated Stage 2 row, not a generic absence of pack data.
        if _stage2_reason is not None:
            block = {**block, "available": False, "reason": _stage2_reason}
        products.append(
            {
                "sealedProductId": _optional_str(row.get("sealed_product_id")),
                "productName": _optional_str(row.get("product_name")),
                "productFamily": _optional_str(row.get("product_family")),
                "productPrice": _positive(row.get("product_market_cost")),
                "productPriceAsOf": _optional_str(row.get("price_as_of")),
                "productPriceSource": _optional_str(row.get("price_source")),
                "productSourceUpdatedAt": _optional_str(row.get("updated_at")),
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
        "currentPriceObservationSource": card.get("currentPriceObservationSource"),
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
    snapshot_built_at: Optional[str] = None,
) -> Dict[str, Any]:
    """The published chase-economics contract for ONE set.

    ``eligible_card_count`` is the size of the population BEFORE the cap, so a
    reader can see that 25 of 187 chaseable cards were published rather than
    inferring that the set has 25.
    """
    resolved_run_id = _optional_str(run_id)
    card_list = [c for c in (cards or []) if isinstance(c, Mapping)]
    rows = [r for r in (product_rows or []) if isinstance(r, Mapping)]

    built_at = _optional_str(snapshot_built_at)
    card_price_dates = sorted(
        {str(c.get("currentPriceAsOf")) for c in card_list if c.get("currentPriceAsOf")}
    )
    ev_basis_dates = sorted(
        {str(c.get("evPriceBasisAsOf")) for c in card_list if c.get("evPriceBasisAsOf")}
    )
    product_price_dates = sorted(
        {str(r.get("price_as_of")) for r in rows if r.get("price_as_of")}
    )
    return {
        "contractVersion": CHASE_ECONOMICS_CONTRACT_VERSION,
        "recoveryModel": RECOVERY_MODEL_GROSS_MARKET_VALUE,
        "sourceCalculationRunId": resolved_run_id,
        "snapshotBuiltAt": built_at,
        "provenance": {
            "sourceCalculationRunId": resolved_run_id,
            "evPriceBasisDates": ev_basis_dates,
            "currentCardPriceDates": card_price_dates,
            "currentProductPriceDates": product_price_dates,
            "snapshotBuiltAt": built_at,
        },
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


def build_chase_economics_snapshot_row(
    *, set_id: Any, run_id: Any, client: Any,
    limit: int = DEFAULT_PUBLISHED_CARD_LIMIT,
) -> Dict[str, Any]:
    """Build the independently persisted chase snapshot for one set/run.

    Selection considers the complete run population before applying the
    storage cap.  The EV price and its capture time come from the named run;
    the comparison price comes from the current Near Mint projection.
    """
    resolved_set_id = _optional_str(set_id)
    if resolved_set_id is None:
        raise ValueError("set_id is required")
    resolved_run_id = _optional_str(run_id)

    built_at = datetime.now(timezone.utc).isoformat()
    if resolved_run_id is None:
        contract = build_chase_economics_contract(
            cards=[], product_rows=[], run_id=None, limit=limit,
            eligible_card_count=0,
            snapshot_built_at=built_at,
        )
        return {
            "set_id": resolved_set_id,
            "calculation_run_id": None,
            "payload_json": contract,
            "card_count": 0,
            "as_of": None,
            "updated_at": built_at,
        }

    input_rows = _load_run_population(
        client,
        table=INPUT_CARDS_TABLE,
        select="card_variant_id,effective_pull_rate,price_used,captured_at",
        run_id=resolved_run_id,
    )
    denominators: Dict[str, float] = {}
    ev_prices: Dict[str, float] = {}
    ev_as_of: Dict[str, str] = {}
    for row in input_rows:
        variant_id = _optional_str(row.get("card_variant_id"))
        denominator = _positive(row.get("effective_pull_rate"))
        if variant_id and denominator is not None:
            denominators[variant_id] = denominator
        price_used = _positive(row.get("price_used"))
        if variant_id and price_used is not None:
            ev_prices[variant_id] = price_used
        captured_at = _optional_str(row.get("captured_at"))
        if variant_id and captured_at:
            ev_as_of[variant_id] = captured_at

    price_rows = _load_run_near_mint_prices(client, run_id=resolved_run_id)
    priced_with_provenance = [
        {**row, "price_used_as_of": ev_as_of.get(_optional_str(row.get("card_variant_id")) or "")}
        for row in price_rows
    ]
    # An uncapped selection supplies the true eligible population. Only the
    # stored card list is subsequently sliced to the publication policy.
    eligible = select_chase_cards(
        priced_with_provenance, denominators, ev_prices,
        limit=len(priced_with_provenance),
    )
    product_rows = _load_current_run_product_rows(
        run_id=resolved_run_id, set_id=resolved_set_id, client=client,
    )
    contract = build_chase_economics_contract(
        cards=eligible[: max(0, int(limit))],
        product_rows=product_rows,
        run_id=resolved_run_id,
        limit=limit,
        eligible_card_count=len(eligible),
        snapshot_built_at=built_at,
    )
    as_of_values = [value for value in ev_as_of.values() if value]
    return {
        "set_id": resolved_set_id,
        "calculation_run_id": resolved_run_id,
        "payload_json": contract,
        "card_count": len(contract["cards"]),
        "as_of": max(as_of_values) if as_of_values else None,
        "updated_at": built_at,
    }


def read_chase_economics_snapshot(*, set_id: Any, client: Any) -> Dict[str, Any]:
    """Read only the dedicated chase row; never inflate another snapshot."""
    resolved_set_id = _optional_str(set_id)
    if resolved_set_id is None:
        raise ValueError("set_id is required")
    result = (
        client.table("pokemon_set_chase_economics_snapshot_latest")
        .select("set_id,calculation_run_id,payload_json,card_count,as_of,updated_at")
        .eq("set_id", resolved_set_id)
        .limit(1)
        .execute()
    )
    rows = list(result.data or [])
    if rows and isinstance(rows[0].get("payload_json"), dict):
        return rows[0]["payload_json"]
    return build_chase_economics_contract(cards=[], product_rows=[], run_id=None)
