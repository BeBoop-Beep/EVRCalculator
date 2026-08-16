"""Current market price for an EXACT guaranteed card printing.

THE PRICING CONTRACT, AND WHY IT IS NOT A NEW ONE
--------------------------------------------------
The application's canonical card price is defined by migration 040's
``pokemon_canonical_card_market_prices_latest`` builder, and it is precise:

    the most recently captured NEAR MINT, USD, strictly-positive market price
    observation for a card variant

That definition has two halves. The first half resolves WHICH VARIANT represents
a canonical checklist card - an identity match plus a printing-preference ladder
(holo before non-holo before reverse-holo, and so on). The second half reads the
price for that variant.

Stage 2 reuses the SECOND half exactly and deliberately omits the first, because
a Stage 2 composition already names the exact ``card_variant_id`` it guarantees.
Running the printing ladder here would be actively wrong: its entire purpose is
to FALL BACK to another printing when the preferred one has no price, and
"the wrong printing cannot substitute" is a Stage 2 rule. A product that
guarantees the Pokemon Center-stamped Koraidon is not worth the price of the
ordinary Koraidon, so an unpriced component yields no price - never a neighbour's.

WHY NOT `pokemon_canonical_card_market_prices_latest` DIRECTLY
---------------------------------------------------------------
It cannot express these cards. That table requires a NOT NULL
``canonical_card_id``, and the SV Black Star Promo catalog - which every Stage 2
guaranteed promo in the supported cohort belongs to - has zero canonical rows,
because it has no unique Pokemon TCG API set match. The canonical model also has
no representation for a Pokemon Center stamp at all, while the legacy catalog
carries stamped printings as distinct products. So this reads the same source
table the canonical builder reads, under the same selection rule, at the only
identity that can tell the two printings apart.

NO FALLBACKS OF ANY KIND
------------------------
Not a sibling printing, not MSRP, not eBay, not an average of history, not the
last known good price, not zero. A guaranteed component with no current valid
market price makes its PRODUCT unscorable with a structured reason. That is a
worse-looking outcome than a number, and a truer one.
"""

from __future__ import annotations

import logging
import time
from typing import Any, Dict, List, Mapping, Optional, Sequence

logger = logging.getLogger(__name__)

PRICING_CONTRACT_VERSION = "guaranteed-component-pricing-v1"

#: The same grade the canonical card price layer uses. Resolved by name rather
#: than hard-coded as a UUID so this does not silently price a different grade if
#: the conditions table is ever re-seeded.
NEAR_MINT_CONDITION_NAME = "Near Mint"
NEAR_MINT_CONDITION_ABBREVIATION = "NM"

PRICE_SOURCE_CONTRACT = "card_variant_price_observations.near_mint_usd_latest"

REASON_NO_PRICE_OBSERVATION = "no_near_mint_usd_market_price_observation"
REASON_NON_POSITIVE_PRICE = "non_positive_market_price"


def _normalize_currency(value: Any) -> str:
    """Match migration 040's currency handling, quote-stripping included.

    The stored currency has been observed carrying literal quote characters,
    which is why the canonical SQL trims them. Normalizing differently here would
    make this layer disagree with the canonical price layer about the same row.
    """
    return str(value or "").strip().strip('"').upper()


def resolve_near_mint_condition_id(client: Any) -> str:
    response = (
        client.table("conditions")
        .select("id")
        .eq("name", NEAR_MINT_CONDITION_NAME)
        .eq("abbreviation", NEAR_MINT_CONDITION_ABBREVIATION)
        .order("id")
        .limit(1)
        .execute()
    )
    rows = list(response.data or [])
    if not rows:
        # Not an expected data gap - the conditions table is reference data. A
        # missing Near Mint grade means the pricing contract has no meaning.
        raise RuntimeError(
            "Near Mint condition not found; the guaranteed-component pricing contract "
            "is defined in terms of it and cannot be evaluated."
        )
    return str(rows[0]["id"])


def get_latest_near_mint_prices(
    card_variant_ids: Sequence[Any],
    *,
    client: Any = None,
) -> Dict[str, Dict[str, Any]]:
    """``{card_variant_id: {market_price, captured_at, source}}`` for priced variants.

    Variants with no qualifying observation are ABSENT from the result rather
    than present with a null price, so a caller cannot accidentally read a
    missing price as a value.
    """
    if client is None:
        from backend.db.clients.supabase_client import supabase as client  # type: ignore

    ids = [str(value) for value in card_variant_ids if value is not None]
    if not ids:
        return {}

    condition_id = resolve_near_mint_condition_id(client)

    response = (
        client.table("card_variant_price_observations")
        .select("card_variant_id,market_price,captured_at,created_at,currency,source")
        .in_("card_variant_id", ids)
        .eq("condition_id", condition_id)
        .order("captured_at", desc=True)
        .order("created_at", desc=True)
        .execute()
    )

    latest: Dict[str, Dict[str, Any]] = {}
    for observation in list(response.data or []):
        variant_id = str(observation.get("card_variant_id"))
        if variant_id in latest:
            # Rows arrive newest-first, so the first acceptable observation per
            # variant IS the latest one.
            continue
        if _normalize_currency(observation.get("currency")) != "USD":
            continue
        try:
            price = float(observation.get("market_price"))
        except (TypeError, ValueError):
            continue
        if not (price > 0.0):
            continue

        latest[variant_id] = {
            "market_price": price,
            "captured_at": observation.get("captured_at"),
            "source": observation.get("source"),
            "priceContract": PRICE_SOURCE_CONTRACT,
        }

    return latest


def price_guaranteed_components(
    components: Sequence[Any],
    *,
    client: Any = None,
    price_lookup_fn=None,
) -> Dict[str, Any]:
    """Attach a market price to every guaranteed component, or explain why not.

    ``components`` are ``GuaranteedCardComponent`` value objects. Returns::

        {"priced": [...], "missing": [...], "totalGuaranteedValue": float|None,
         "elapsedMs": float}

    ``priced`` is only usable when ``missing`` is empty: a product is a SINGLE
    opening, so a partial valuation of its guaranteed contents is not a smaller
    number, it is a wrong one. Callers check ``missing`` first.
    """
    started = time.perf_counter()
    lookup = price_lookup_fn or (lambda ids: get_latest_near_mint_prices(ids, client=client))

    variant_ids = [component.card_variant_id for component in components]
    prices = lookup(variant_ids) if variant_ids else {}

    priced: List[Dict[str, Any]] = []
    missing: List[Dict[str, Any]] = []

    for component in components:
        record = prices.get(str(component.card_variant_id))
        if not record:
            missing.append(
                {
                    "cardVariantId": component.card_variant_id,
                    "componentRole": component.component_role,
                    "reason": REASON_NO_PRICE_OBSERVATION,
                }
            )
            continue
        priced.append(
            {
                "card_variant_id": component.card_variant_id,
                "canonical_card_id": component.canonical_card_id,
                "component_role": component.component_role,
                "quantity": int(component.quantity),
                "display_name": component.display_name,
                "market_price": record["market_price"],
                "captured_at": record.get("captured_at"),
                "source": record.get("source"),
                "price_contract": record.get("priceContract", PRICE_SOURCE_CONTRACT),
            }
        )

    total: Optional[float] = None
    if not missing and priced:
        total = sum(entry["market_price"] * entry["quantity"] for entry in priced)

    return {
        "pricingContractVersion": PRICING_CONTRACT_VERSION,
        "priced": priced,
        "missing": missing,
        "totalGuaranteedValue": total,
        "elapsedMs": round((time.perf_counter() - started) * 1000.0, 3),
    }
