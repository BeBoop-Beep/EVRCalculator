"""Slim, variant-aware public Pokemon card-detail contract."""

from __future__ import annotations

from datetime import date, datetime, timedelta, timezone
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
from backend.db.services.pokemon_sets_catalog_service import _slugify as canonical_set_route_slug
from backend.domain.pokemon.sealed_product_classifier import classify_sealed_product


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


_MARKET_WINDOWS = {"1D": 1, "7D": 7, "30D": 30, "3M": 90, "6M": 180, "1Y": 365}


def _date_key(value: Any) -> Optional[str]:
    text = _text(value)
    if not text:
        return None
    try:
        return datetime.fromisoformat(text.replace("Z", "+00:00")).date().isoformat()
    except ValueError:
        try:
            return date.fromisoformat(text[:10]).isoformat()
        except ValueError:
            return None


def _market_movement(history: List[Dict[str, Any]], window: str) -> Dict[str, Any]:
    valued = [row for row in history if _positive(row.get("marketPrice")) is not None]
    if not valued:
        return {"available": False, "status": "unavailable", "requestedWindow": window}
    end = valued[-1]
    requested_start = valued[0]["date"]
    if window != "lifetime":
        requested_start = (date.fromisoformat(end["date"]) - timedelta(days=_MARKET_WINDOWS[window])).isoformat()
    candidates = [row for row in valued if row["date"] <= requested_start]
    start = candidates[-1] if candidates else valued[0]
    start_price = _positive(start.get("marketPrice"))
    end_price = _positive(end.get("marketPrice"))
    if start_price is None or end_price is None:
        return {"available": False, "status": "unavailable", "requestedWindow": window}
    amount = round(end_price - start_price, 2)
    full_coverage = window == "lifetime" or valued[0]["date"] <= requested_start
    return {
        "available": True,
        "status": "available" if full_coverage else "partial_history",
        "requestedWindow": window,
        "effectiveWindow": window if full_coverage else "lifetime",
        "fullCoverage": full_coverage,
        "startDate": start["date"],
        "endDate": end["date"],
        "startPrice": start_price,
        "endPrice": end_price,
        "deltaAmount": amount,
        "deltaPercent": round(amount / start_price * 100, 2),
        "historyPointCount": sum(start["date"] <= row["date"] <= end["date"] for row in valued),
    }


def _load_card_market_history(client: Any, variant_id: Optional[str], condition_id: Optional[str]) -> List[Dict[str, Any]]:
    if not variant_id or not condition_id:
        return []
    rows = _rows(
        client.table("card_variant_price_observations")
        .select("card_variant_id,condition_id,market_price,source,captured_at")
        .eq("card_variant_id", variant_id)
        .eq("condition_id", condition_id)
    )
    by_day: Dict[str, Dict[str, Any]] = {}
    for row in rows:
        day = _date_key(row.get("captured_at"))
        price = _positive(row.get("market_price"))
        if not day or price is None:
            continue
        existing = by_day.get(day)
        if not existing or str(row.get("captured_at") or "") > str(existing.get("observedAt") or ""):
            by_day[day] = {
                "date": day, "marketPrice": round(price, 2), "source": _text(row.get("source")),
                "conditionId": condition_id, "isObserved": True, "isCarriedForward": False,
                "sourceDate": day, "observedAt": _text(row.get("captured_at")),
            }
    return [by_day[key] for key in sorted(by_day)]


def _load_card_intelligence(client: Any, card_id: str, rarity: Any) -> Dict[str, Any]:
    """Narrow, best-effort projection of production card desirability data."""
    try:
        links = _rows(
            client.table("pokemon_card_desirability_links")
            .select("pokemon_reference_id,contribution_weight,match_confidence")
            .eq("pokemon_canonical_card_id", card_id)
        )
        reference_ids = [row.get("pokemon_reference_id") for row in links if row.get("pokemon_reference_id") is not None]
        scores = _rows(
            client.table("pokemon_desirability_composite_scores")
            .select("pokemon_reference_id,desirability_score,scoring_version,created_at")
            .in_("pokemon_reference_id", reference_ids)
        ) if reference_ids else []
        latest: Dict[str, Dict[str, Any]] = {}
        for row in scores:
            key = str(row.get("pokemon_reference_id"))
            if key not in latest or str(row.get("created_at") or "") > str(latest[key].get("created_at") or ""):
                latest[key] = row
        weighted = []
        for link in links:
            score = _positive((latest.get(str(link.get("pokemon_reference_id"))) or {}).get("desirability_score"))
            weight = _positive(link.get("contribution_weight"))
            if score is not None and weight is not None:
                weighted.append((score, weight))
        demand = round(sum(score * weight for score, weight in weighted) / sum(weight for _, weight in weighted), 2) if weighted else None
        from backend.desirability.card_appeal import calculate_adjusted_card_appeal, get_treatment_score
        from backend.desirability.composite import assign_composite_tier
        treatment = get_treatment_score(rarity)
        appeal = calculate_adjusted_card_appeal(demand, treatment, None)
        return {
            "available": appeal is not None or demand is not None or treatment is not None,
            "cardAppeal": {"score": appeal, "tier": assign_composite_tier(appeal) if appeal is not None else None, "available": appeal is not None},
            "pokemonDemand": {"score": demand, "tier": assign_composite_tier(demand) if demand is not None else None, "available": demand is not None},
            "treatment": {"score": treatment, "tier": assign_composite_tier(treatment) if treatment is not None else None, "available": treatment is not None},
            "scarcity": {"score": None, "available": False},
            "provenance": {"source": "pokemon_card_desirability_links+pokemon_desirability_composite_scores", "formula": "card_appeal_v1"},
        }
    except Exception:
        return {"available": False, "reason": "card_intelligence_unavailable"}


def _load_sealed_product_catalog(client: Any, set_id: str) -> List[Dict[str, Any]]:
    """Return every canonical SKU once, enriched with its latest real price."""
    products = _rows(
        client.table("sealed_products")
        .select("id,name,product_type,set_id,image_small_url,image_large_url")
        .eq("set_id", set_id)
    )
    product_ids = [str(row["id"]) for row in products if row.get("id")]
    observations = _rows(
        client.table("sealed_product_price_observations")
        .select("sealed_product_id,market_price,captured_at,source")
        .in_("sealed_product_id", product_ids)
    ) if product_ids else []
    latest: Dict[str, Dict[str, Any]] = {}
    for row in observations:
        product_id = _text(row.get("sealed_product_id"))
        price = _positive(row.get("market_price"))
        if not product_id or price is None:
            continue
        current = latest.get(product_id)
        if current is None or str(row.get("captured_at") or "") > str(current.get("captured_at") or ""):
            latest[product_id] = row
    catalog: Dict[str, Dict[str, Any]] = {}
    for row in products:
        product_id = _text(row.get("id"))
        if not product_id or product_id in catalog:
            continue
        identity = classify_sealed_product(row.get("name"))
        price = latest.get(product_id, {})
        catalog[product_id] = {
            "sealedProductId": product_id,
            "productName": _text(row.get("name")) or _text(row.get("product_type")),
            "catalogProductType": _text(row.get("product_type")),
            "productFamily": identity.get("productFamily"),
            "productFamilyLabel": identity.get("productFamilyLabel"),
            "imageUrl": _text(row.get("image_small_url")) or _text(row.get("image_large_url")),
            "imageSmallUrl": _text(row.get("image_small_url")),
            "imageLargeUrl": _text(row.get("image_large_url")),
            "productPageId": product_id,
            "currentPrice": _positive(price.get("market_price")),
            "priceAsOf": _date_key(price.get("captured_at")),
            "priceSource": _text(price.get("source")),
            "available": False,
            "reason": "chase_economics_not_supported",
        }
    return list(catalog.values())


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
    try:
        artwork_rows = _rows(active.table("sets").select("id,hero_image_url,logo_image_url,symbol_image_url").eq("id", resolved_set_id).limit(1))
        if artwork_rows:
            set_row = {**set_row, **artwork_rows[0]}
    except Exception:
        pass

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
    near_mint_rows = _rows(
        active.table("conditions").select("id,name").eq("name", "Near Mint").limit(1)
    )
    near_mint_condition_id = _text(near_mint_rows[0].get("id")) if near_mint_rows else None

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
    # Market-only variants stay selectable. Their pull modules explicitly
    # remain unavailable instead of inheriting another printing's model.
    requested_is_valid = bool(requested and requested in candidate_ids)
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
    if selected and selected in modeled:
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
            supported_products = {str(item.get("sealedProductId")): item for item in card_chase.get("products", [])}
            try:
                catalog_rows = _load_sealed_product_catalog(active, resolved_set_id)
            except Exception:
                catalog_rows = []
            all_products = []
            for product in catalog_rows:
                product_id = str(product.get("sealedProductId"))
                supported = supported_products.pop(product_id, None)
                all_products.append({**product, **(supported or {})})
            all_products.extend(supported_products.values())
            chase = {
                "available": True,
                "reason": None,
                **card_chase,
                "products": all_products,
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
            "reason": "variant_not_modeled" if selected else ("variant_selection_required" if modeled else "modeled_chase_unavailable"),
            "sourceCalculationRunId": run_id,
        }
        market = {
            "currentPrice": None if selected else _positive(canonical_market.get("market_price")),
            "observedAt": None if selected else _text(canonical_market.get("captured_at")),
            "marketDate": None if selected else (_text(canonical_market.get("captured_at")) or "")[:10] or None,
            "source": None if selected else _text(canonical_market.get("source")),
            "priceSelectionReason": None if selected else _text(canonical_market.get("price_selection_reason")),
        }

    selected_condition = _text((modeled.get(selected or "") or {}).get("condition_id")) or near_mint_condition_id
    canonical_condition = _text(canonical_market.get("condition_id")) if not selected or selected == canonical_selected else None
    history = _load_card_market_history(active, selected or canonical_selected, selected_condition or canonical_condition)
    if selected and history and market.get("currentPrice") is None:
        latest = history[-1]
        market.update({
            "currentPrice": latest.get("marketPrice"),
            "observedAt": latest.get("observedAt") or latest.get("date"),
            "marketDate": latest.get("date"),
            "source": latest.get("source"),
        })
    market["history"] = history
    market["movements"] = {key: _market_movement(history, key) for key in (*_MARKET_WINDOWS, "lifetime")}
    intelligence = _load_card_intelligence(active, str(card_id), card.get("rarity"))

    return {
        "set": {"id": resolved_set_id, "targetId": _text(set_row.get("canonical_key")), "name": _text(set_row.get("name")), "slug": canonical_set_route_slug(_text(set_row.get("name")) or ""),
                "heroImageUrl": _text(set_row.get("hero_image_url")), "logoImageUrl": _text(set_row.get("logo_image_url")),
                "symbolImageUrl": _text(set_row.get("symbol_image_url"))},
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
        "intelligence": intelligence,
        "meta": {
            "contractVersion": "pokemon_card_detail_v2",
            "sources": ["pokemon_canonical_cards", "card_variant_price_observations", "simulation_input_cards", "simulation_input_cards_with_near_mint_price", "simulation_sealed_product_results", "pokemon_card_desirability_links", "pokemon_desirability_composite_scores"],
            "wholeSetChaseSnapshotRead": False,
            "requestedVariantValid": requested_is_valid if requested else None,
        },
    }
