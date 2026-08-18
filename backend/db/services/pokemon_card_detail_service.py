"""Slim, variant-aware public Pokemon card-detail contract."""

from __future__ import annotations

from datetime import datetime, timezone
from typing import Any, Dict, List, Mapping, Optional

from backend.db.clients.supabase_client import supabase
from backend.db.services.chase_economics_service import (
    build_chase_economics_contract,
    select_chase_cards,
)
from backend.db.services.pokemon_set_market_service import (
    PokemonSetMarketError,
    resolve_pokemon_set_identifier,
)
from backend.db.services.rip_decision_service import _load_current_run_product_rows


class PokemonCardDetailError(Exception):
    def __init__(self, status_code: int, message: str, code: str) -> None:
        super().__init__(message)
        self.status_code = status_code
        self.message = message
        self.code = code


def _text(value: Any) -> Optional[str]:
    if value is None:
        return None
    value = str(value).strip()
    return value or None


def _positive(value: Any) -> Optional[float]:
    try:
        value = float(value)
    except (TypeError, ValueError):
        return None
    return value if value > 0 else None


def _rows(query: Any) -> List[Dict[str, Any]]:
    return list(query.execute().data or [])


def _variant_label(row: Mapping[str, Any]) -> str:
    special = _text(row.get("special_type"))
    printing = _text(row.get("printing_type"))
    raw = special or printing or "Standard"
    return " ".join(part.capitalize() for part in raw.replace("_", " ").split())


def _current_run_id(client: Any, set_id: str) -> Optional[str]:
    rows = _rows(
        client.table("pokemon_set_page_snapshot_latest")
        .select("payload_json")
        .eq("set_id", set_id)
        .limit(1)
    )
    payload = rows[0].get("payload_json") if rows else {}
    rip = payload.get("ripDecision") if isinstance(payload, dict) else {}
    return _text(rip.get("sourceCalculationRunId") if isinstance(rip, dict) else None)


def get_pokemon_card_detail_payload(
    *, set_id: str, card_id: str, variant_id: Optional[str] = None, client: Any = None
) -> Dict[str, Any]:
    """Build one canonical card page without reading a whole-set card/Chase payload."""
    active = client or supabase
    try:
        set_row = resolve_pokemon_set_identifier(set_id, client=active)
    except PokemonSetMarketError as exc:
        raise PokemonCardDetailError(exc.status_code, exc.message, exc.code) from exc
    resolved_set_id = str(set_row["id"])

    canonical_rows = _rows(
        active.table("pokemon_canonical_cards")
        .select(
            "id,set_id,pokemon_tcg_api_card_id,name,supertype,subtypes,rarity,number,"
            "printed_number,image_small_url,image_large_url"
        )
        .eq("id", str(card_id))
        .eq("set_id", resolved_set_id)
        .limit(1)
    )
    if not canonical_rows:
        raise PokemonCardDetailError(404, "Pokemon card not found", "POKEMON_CARD_NOT_FOUND")
    card = canonical_rows[0]
    api_card_id = _text(card.get("pokemon_tcg_api_card_id"))

    legacy_query = active.table("cards").select("id,pokemon_tcg_api_id").eq("set_id", resolved_set_id)
    if api_card_id:
        legacy_query = legacy_query.eq("pokemon_tcg_api_id", api_card_id)
    legacy_rows = _rows(legacy_query)
    legacy_ids = [str(row["id"]) for row in legacy_rows if row.get("id")]
    variant_rows: List[Dict[str, Any]] = []
    if legacy_ids:
        variant_rows = _rows(
            active.table("card_variants")
            .select("id,card_id,printing_type,special_type,edition,pokemon_tcg_api_id")
            .in_("card_id", legacy_ids)
        )
    candidate_ids = [str(row["id"]) for row in variant_rows if row.get("id")]

    run_id = _current_run_id(active, resolved_set_id)
    modeled_rows: List[Dict[str, Any]] = []
    price_rows: List[Dict[str, Any]] = []
    if run_id and candidate_ids:
        modeled_rows = _rows(
            active.table("simulation_input_cards")
            .select(
                "card_id,card_variant_id,condition_id,card_name,rarity_bucket,price_used,"
                "captured_at,effective_pull_rate"
            )
            .eq("calculation_run_id", run_id)
            .in_("card_variant_id", candidate_ids)
        )
        price_rows = _rows(
            active.table("simulation_input_cards_with_near_mint_price")
            .select(
                "card_id,card_variant_id,condition_id,card_name,rarity_bucket,current_near_mint_price,"
                "current_near_mint_price_captured_at,current_near_mint_price_source"
            )
            .eq("calculation_run_id", run_id)
            .in_("card_variant_id", candidate_ids)
        )

    modeled = {str(row["card_variant_id"]): row for row in modeled_rows if row.get("card_variant_id")}
    prices = {str(row["card_variant_id"]): row for row in price_rows if row.get("card_variant_id")}
    canonical_market_rows = _rows(
        active.table("pokemon_canonical_card_market_prices_latest")
        .select(
            "canonical_card_id,card_variant_id,condition_id,printing_type,market_price,captured_at,"
            "source,price_selection_reason,refreshed_at"
        )
        .eq("canonical_card_id", str(card_id))
        .eq("set_id", resolved_set_id)
        .limit(1)
    )
    canonical_market = canonical_market_rows[0] if canonical_market_rows else {}
    canonical_selected = _text(canonical_market.get("card_variant_id"))

    requested = _text(variant_id)
    requested_is_valid = bool(requested and requested in modeled and requested in candidate_ids)
    selected: Optional[str] = None
    source: Optional[str] = None
    if requested_is_valid:
        selected, source = requested, "query"
    elif canonical_selected and canonical_selected in modeled:
        selected, source = canonical_selected, "canonical_market_selection"
    elif len(modeled) == 1:
        selected, source = next(iter(modeled)), "only_modeled_variant"

    if selected:
        selection_state = "selected"
    elif modeled:
        selection_state = "selection_required"
    else:
        selection_state = "unavailable"

    variants: List[Dict[str, Any]] = []
    by_id = {str(row["id"]): row for row in variant_rows if row.get("id")}
    for candidate in sorted(candidate_ids, key=lambda value: (_variant_label(by_id[value]), value)):
        row = by_id[candidate]
        current = prices.get(candidate, {})
        observed = _text(current.get("current_near_mint_price_captured_at"))
        variants.append({
            "cardVariantId": candidate,
            "label": _variant_label(row),
            "printingType": _text(row.get("printing_type")),
            "specialType": _text(row.get("special_type")),
            "conditionId": _text((modeled.get(candidate) or {}).get("condition_id")),
            "currentPrice": _positive(current.get("current_near_mint_price")),
            "priceUpdatedAt": observed,
            "priceSourceDate": observed[:10] if observed else None,
            "marketDate": observed[:10] if observed else None,
            "priceCarriedForward": False if observed else None,
            "priceSource": _text(current.get("current_near_mint_price_source")),
            "priceSelectionReason": _text(canonical_market.get("price_selection_reason")) if candidate == canonical_selected else None,
            "modeled": candidate in modeled,
        })

    chase: Dict[str, Any]
    market: Dict[str, Any]
    if selected:
        sim = modeled[selected]
        current = prices.get(selected, {})
        selected_cards = select_chase_cards(
            [{**current, "price_used_as_of": sim.get("captured_at")}],
            {selected: sim.get("effective_pull_rate")},
            {selected: sim.get("price_used")},
            limit=1,
        )
        if selected_cards:
            products = _load_current_run_product_rows(run_id=run_id, set_id=resolved_set_id, client=active)
            contract = build_chase_economics_contract(
                cards=selected_cards,
                product_rows=products,
                run_id=run_id,
                limit=1,
                eligible_card_count=1,
                snapshot_built_at=datetime.now(timezone.utc).isoformat(),
            )
            card_chase = contract["cards"][0]
            chase = {
                "available": True,
                "reason": None,
                **card_chase,
                "recoveryModel": contract["recoveryModel"],
                "modelAssumptions": contract["modelAssumptions"],
                "sourceCalculationRunId": contract["sourceCalculationRunId"],
                "provenance": contract["provenance"],
            }
        else:
            chase = {"available": False, "reason": "current_market_price_unavailable"}
        observed = _text(current.get("current_near_mint_price_captured_at"))
        market = {
            "currentPrice": _positive(current.get("current_near_mint_price")),
            "observedAt": observed,
            "marketDate": observed[:10] if observed else None,
            "source": _text(current.get("current_near_mint_price_source")),
            "priceSelectionReason": _text(canonical_market.get("price_selection_reason")) if selected == canonical_selected else None,
        }
    else:
        chase = {
            "available": False,
            "reason": "variant_selection_required" if modeled else "modeled_chase_unavailable",
            "sourceCalculationRunId": run_id,
        }
        market = {
            "currentPrice": _positive(canonical_market.get("market_price")),
            "observedAt": _text(canonical_market.get("captured_at")),
            "marketDate": (_text(canonical_market.get("captured_at")) or "")[:10] or None,
            "source": _text(canonical_market.get("source")),
            "priceSelectionReason": _text(canonical_market.get("price_selection_reason")),
        }

    return {
        "set": {"id": resolved_set_id, "name": _text(set_row.get("name")), "slug": _text(set_row.get("canonical_key"))},
        "card": {
            "id": str(card["id"]), "canonicalCardId": str(card["id"]),
            "name": _text(card.get("name")), "setId": resolved_set_id,
            "setName": _text(set_row.get("name")), "cardNumber": _text(card.get("number")),
            "printedNumber": _text(card.get("printed_number")), "rarity": _text(card.get("rarity")),
            "supertype": _text(card.get("supertype")),
            "subtypes": card.get("subtypes") if isinstance(card.get("subtypes"), list) else [],
            "imageSmallUrl": _text(card.get("image_small_url")), "imageLargeUrl": _text(card.get("image_large_url")),
            "pokemonTcgApiCardId": api_card_id,
        },
        "availableVariants": variants,
        "selectedVariantId": selected,
        "variantSelection": {"state": selection_state, "source": source},
        "market": market,
        "chase": chase,
        "meta": {
            "contractVersion": "pokemon_card_detail_v1",
            "sources": ["pokemon_canonical_cards", "simulation_input_cards", "simulation_input_cards_with_near_mint_price", "simulation_sealed_product_results"],
            "wholeSetChaseSnapshotRead": False,
            "requestedVariantValid": requested_is_valid if requested else None,
        },
    }
