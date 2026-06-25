from __future__ import annotations

import logging
import math
import re
import time
from datetime import date, datetime, timedelta, timezone
from typing import Any, Dict, List, Optional

from backend.db.clients.supabase_client import public_read_client
from backend.desirability.card_appeal import (
    calculate_adjusted_card_appeal,
    calculate_scarcity_score,
    get_treatment_score,
    normalize_pull_probability,
)
from backend.desirability.set_validation import build_desirability_validation_payload, build_opening_set_audit, is_opening_set_row
from backend.db.services.explore_page_service import ExplorePageError, get_explore_page_payload
from backend.db.services.explore_rip_statistics_service import (
    ExploreRipStatisticsTargetsError,
    get_rip_statistics_targets_payload,
)
from backend.db.services.pokemon_set_cards_service import PokemonSetCardsError, get_pokemon_set_cards_payload
from backend.db.services.pokemon_set_market_service import (
    DEFAULT_SET_VALUE_HISTORY_DAYS,
    DEFAULT_TOP_MARKET_CARDS_LIMIT,
    SET_VALUE_SCOPE_LABELS,
    SET_VALUE_SCOPES,
    PokemonSetMarketError,
    get_pokemon_set_top_market_cards_payload,
    get_pokemon_set_value_history_payload,
)

logger = logging.getLogger(__name__)

DEFAULT_DASHBOARD_WINDOW = "365d"
DEFAULT_TOP_CHASE_DASHBOARD_WINDOW = "30d"
TOP_CHASE_HISTORY_SOURCE_WINDOW_DAYS = 365
TOP_CHASE_NEAR_MINT_CONDITION_ID = "4f8d1181-670e-4aea-937c-4d98d2e531a6"
TOP_CHASE_HISTORY_SOURCE = "card_variant_price_observations"
DEFAULT_RANKINGS_SCOPE = "rip-statistics"
DEFAULT_RANKINGS_LIMIT = 100
MAX_RANKINGS_LIMIT = 200
MIN_LIMIT = 1


def _to_optional_str(value: Any) -> Optional[str]:
    if value is None:
        return None
    text = str(value).strip()
    return text or None


def _normalize_market_dashboard_window_key(value: Any, *, default: str = DEFAULT_DASHBOARD_WINDOW) -> str:
    return (_to_optional_str(value) or default).lower()


def _to_optional_float(value: Any) -> Optional[float]:
    try:
        parsed = float(value)
    except (TypeError, ValueError):
        return None
    return parsed if math.isfinite(parsed) else None


def _normalise_set_lookup_key(value: Any) -> str:
    return re.sub(r"[^a-z0-9]+", "", str(value or "").strip().lower())


def _first_row(result: Any) -> Optional[Dict[str, Any]]:
    if result and result.data:
        return result.data[0]
    return None


def _sanitize_limit(value: Any, *, default: int, max_value: int) -> int:
    try:
        parsed = int(value)
    except (TypeError, ValueError):
        return default
    return max(MIN_LIMIT, min(parsed, max_value))


def _sanitize_days(value: Any, *, default: int = DEFAULT_SET_VALUE_HISTORY_DAYS) -> int:
    try:
        parsed = int(value)
    except (TypeError, ValueError):
        return default
    return max(1, min(parsed, 1825))


def _sanitize_top_limit(value: Any) -> int:
    try:
        parsed = int(value)
    except (TypeError, ValueError):
        return DEFAULT_TOP_MARKET_CARDS_LIMIT
    return max(1, min(parsed, 50))


def _sanitize_scope(value: Any) -> str:
    normalized = str(value or "").strip().lower().replace("_", "").replace("-", "")
    aliases = {
        "": "standard",
        "standard": "standard",
        "all": "standard",
        "hits": "hits",
        "hit": "hits",
        "top10": "top10",
        "topten": "top10",
    }
    return aliases.get(normalized, "standard")


def _parse_date_key(value: Any) -> Optional[str]:
    if isinstance(value, date) and not isinstance(value, datetime):
        return value.isoformat()
    text = _to_optional_str(value)
    if not text:
        return None
    if len(text) >= 10 and text[4] == "-" and text[7] == "-":
        return text[:10]
    try:
        return datetime.fromisoformat(text.replace("Z", "+00:00")).date().isoformat()
    except ValueError:
        return None


def _market_dashboard_window_days(window: Any, days: Any = None) -> int:
    text = _normalize_market_dashboard_window_key(window)
    match = re.match(r"^(\d+)\s*d$", text)
    if match:
        return _sanitize_days(match.group(1), default=365)
    return _sanitize_days(days, default=365)


def _is_missing_snapshot_relation_error(exc: Exception) -> bool:
    payload = getattr(exc, "args", ())
    text = " ".join(str(part) for part in payload)
    for attr in ("code", "message", "details"):
        value = getattr(exc, attr, None)
        if value:
            text = f"{text} {value}"
    text = text.lower()
    return (
        "42p01" in text
        or "does not exist" in text
        or "could not find the table" in text
        or "relation" in text and "pokemon_set_market_dashboard_snapshot_latest" in text
    )


def _card_id_key(card: Dict[str, Any]) -> Optional[str]:
    return (
        _to_optional_str(card.get("id"))
        or _to_optional_str(card.get("cardId"))
        or _to_optional_str(card.get("card_id"))
    )


def _movement_card_id_key(movement: Dict[str, Any]) -> Optional[str]:
    return _to_optional_str(movement.get("cardId")) or _to_optional_str(movement.get("card_id"))


def _movement_fields(movement: Dict[str, Any]) -> Dict[str, Any]:
    current_price = movement.get("currentPrice", movement.get("current_price"))
    change_amount = movement.get("change30dAmount", movement.get("change_30d_amount"))
    change_percent = movement.get("change30dPercent", movement.get("change_30d_percent"))
    movement_score = movement.get("movementScore", movement.get("movement_score"))
    movement_label = movement.get("movementLabel", movement.get("movement_label"))
    enough_history = movement.get("enoughHistory", movement.get("enough_history"))
    confidence = movement.get("confidence")
    return {
        "currentPrice": current_price,
        "current_price": current_price,
        "marketPrice": current_price,
        "market_price": current_price,
        "change30dAmount": change_amount,
        "change_30d_amount": change_amount,
        "change30dPercent": change_percent,
        "change_30d_percent": change_percent,
        "movementScore": movement_score,
        "movement_score": movement_score,
        "movementLabel": movement_label,
        "movement_label": movement_label,
        "enoughHistory": enough_history,
        "enough_history": enough_history,
        "confidence": confidence,
        "movement30d": {
            "currentPrice": current_price,
            "current_price": current_price,
            "changeAmount": change_amount,
            "change_amount": change_amount,
            "changePercent": change_percent,
            "change_percent": change_percent,
            "score": movement_score,
            "movementScore": movement_score,
            "movement_score": movement_score,
            "label": movement_label,
            "movementLabel": movement_label,
            "movement_label": movement_label,
            "enoughHistory": enough_history,
            "enough_history": enough_history,
            "confidence": confidence,
        },
    }


def enrich_cards_payload_with_movements(
    payload: Dict[str, Any],
    movement_payload: Dict[str, Any],
) -> Dict[str, Any]:
    movements = list(movement_payload.get("movements") or [])
    if not movements:
        return payload

    movement_by_card_id = {
        key: movement
        for movement in movements
        for key in [_movement_card_id_key(movement)]
        if key
    }
    cards = []
    for card in list(payload.get("cards") or []):
        card_payload = dict(card or {})
        movement = movement_by_card_id.get(_card_id_key(card_payload) or "")
        if movement:
            card_payload.update(_movement_fields(movement))
        cards.append(card_payload)

    meta = dict(payload.get("meta") or {})
    market_movement_meta = {
        "window": movement_payload.get("window") or movement_payload.get("window_key") or "30D",
        "windowDays": movement_payload.get("windowDays") or movement_payload.get("window_days"),
        "source": "pokemon_set_card_movement_payload",
        "guardrails": (movement_payload.get("meta") or {}).get("guardrails"),
    }
    meta["marketMovement"] = market_movement_meta
    meta["market_movement"] = market_movement_meta
    return {**payload, "cards": cards, "meta": meta}


def _latest_composite_scores_for_references(reference_ids: List[int]) -> Dict[int, Dict[str, Any]]:
    clean_ids = sorted({reference_id for reference_id in reference_ids if reference_id is not None})
    if not clean_ids:
        return {}

    try:
        response = (
            public_read_client.table("pokemon_desirability_composite_scores")
            .select("pokemon_reference_id,pokedex_number,pokemon_name,desirability_score,created_at")
            .in_("pokemon_reference_id", clean_ids)
            .order("created_at", desc=True)
            .execute()
        )
    except Exception:
        logger.warning("[pokemon-snapshot] card desirability score lookup failed", exc_info=True)
        return {}

    scores_by_reference: Dict[int, Dict[str, Any]] = {}
    for row in response.data or []:
        try:
            reference_id = int(row.get("pokemon_reference_id"))
        except (TypeError, ValueError):
            continue
        scores_by_reference.setdefault(reference_id, row)
    return scores_by_reference


def _resolve_pull_probability(card: Dict[str, Any]) -> tuple[Optional[float], Optional[str]]:
    for key in ("pullRate", "pull_rate", "pullProbability", "pull_probability"):
        probability = normalize_pull_probability(card.get(key))
        if probability is not None:
            return probability, key
    for key in ("pullRateOneInX", "pull_rate_one_in_x", "specificCardOddsDenominator", "specific_card_odds_denominator"):
        denominator = _to_optional_float(card.get(key))
        if denominator is not None and denominator > 0:
            return 1.0 / denominator, key
    return None, None


def _apply_card_validation_fields(card: Dict[str, Any], *, total_market_value: float) -> Dict[str, Any]:
    card_payload = dict(card or {})
    pokemon_score = _to_optional_float(
        card_payload.get("pokemonDesirabilityScore")
        if card_payload.get("pokemonDesirabilityScore") is not None
        else card_payload.get("pokemon_desirability_score")
        if card_payload.get("pokemon_desirability_score") is not None
        else card_payload.get("cardDesirabilityScore")
        if card_payload.get("cardDesirabilityScore") is not None
        else card_payload.get("card_desirability_score")
    )
    treatment_score = get_treatment_score(card_payload.get("rarity"))
    pull_probability, pull_source = _resolve_pull_probability(card_payload)
    scarcity_score = calculate_scarcity_score(pull_probability)
    adjusted_score = calculate_adjusted_card_appeal(pokemon_score, treatment_score, scarcity_score)
    market_price = _to_optional_float(
        card_payload.get("marketPrice")
        if card_payload.get("marketPrice") is not None
        else card_payload.get("market_price")
        if card_payload.get("market_price") is not None
        else card_payload.get("currentPrice")
        if card_payload.get("currentPrice") is not None
        else card_payload.get("current_price")
    )
    set_value_share = (
        round(market_price / total_market_value, 6)
        if market_price is not None and total_market_value > 0
        else None
    )

    card_payload.update(
        {
            "treatmentScore": treatment_score,
            "treatment_score": treatment_score,
            "scarcityScore": scarcity_score,
            "scarcity_score": scarcity_score,
            "adjustedCardAppealScore": adjusted_score,
            "adjusted_card_appeal_score": adjusted_score,
            "pullRate": pull_probability,
            "pull_rate": pull_probability,
            "pullRateSource": pull_source,
            "pull_rate_source": pull_source,
            "setValueShare": set_value_share,
            "set_value_share": set_value_share,
        }
    )
    return card_payload


def enrich_cards_payload_with_desirability(payload: Dict[str, Any]) -> Dict[str, Any]:
    cards = list(payload.get("cards") or [])
    card_ids = [_card_id_key(card) for card in cards if isinstance(card, dict)]
    clean_card_ids = sorted({card_id for card_id in card_ids if card_id})

    links_by_card: Dict[str, List[Dict[str, Any]]] = {}
    reference_ids: List[int] = []
    if clean_card_ids:
        try:
            links_result = (
                public_read_client.table("pokemon_card_desirability_links")
                .select(
                    "pokemon_canonical_card_id,pokemon_reference_id,pokedex_number,link_position,"
                    "link_count,contribution_weight,match_confidence,is_hit_eligible"
                )
                .in_("pokemon_canonical_card_id", clean_card_ids)
                .execute()
            )
            for link in links_result.data or []:
                card_id = _to_optional_str(link.get("pokemon_canonical_card_id"))
                if not card_id:
                    continue
                try:
                    reference_id = int(link.get("pokemon_reference_id"))
                except (TypeError, ValueError):
                    reference_id = None
                if reference_id is not None:
                    reference_ids.append(reference_id)
                links_by_card.setdefault(card_id, []).append(link)
        except Exception:
            logger.warning("[pokemon-snapshot] card desirability link lookup failed", exc_info=True)

    scores_by_reference = _latest_composite_scores_for_references(reference_ids)
    market_prices = [
        _to_optional_float(card.get("marketPrice") if card.get("marketPrice") is not None else card.get("market_price"))
        for card in cards
        if isinstance(card, dict)
    ]
    total_market_value = sum(price for price in market_prices if price is not None and price > 0)

    enriched_cards: List[Dict[str, Any]] = []
    enriched_count = 0
    hit_eligible_count = 0
    priced_linked_count = 0
    excluded_non_pokemon_count = 0

    for card in cards:
        card_payload = dict(card or {})
        card_id = _card_id_key(card_payload)
        card_links = links_by_card.get(card_id or "", [])
        linked_pokemon: List[Dict[str, Any]] = []
        weighted_score = 0.0
        total_weight = 0.0
        is_hit_eligible = False
        for link in card_links:
            try:
                reference_id = int(link.get("pokemon_reference_id"))
            except (TypeError, ValueError):
                continue
            score_row = scores_by_reference.get(reference_id)
            score = _to_optional_float((score_row or {}).get("desirability_score"))
            weight = _to_optional_float(link.get("contribution_weight")) or 0.0
            if score is None or weight <= 0:
                continue
            is_hit_eligible = is_hit_eligible or bool(link.get("is_hit_eligible"))
            weighted_score += score * weight
            total_weight += weight
            linked_pokemon.append(
                {
                    "pokemonName": _to_optional_str((score_row or {}).get("pokemon_name")),
                    "pokemon_name": _to_optional_str((score_row or {}).get("pokemon_name")),
                    "pokemonReferenceId": reference_id,
                    "pokemon_reference_id": reference_id,
                    "pokedexNumber": link.get("pokedex_number") or (score_row or {}).get("pokedex_number"),
                    "pokedex_number": link.get("pokedex_number") or (score_row or {}).get("pokedex_number"),
                    "desirabilityScore": round(score, 2),
                    "desirability_score": round(score, 2),
                    "contributionWeight": weight,
                    "contribution_weight": weight,
                    "matchConfidence": link.get("match_confidence"),
                    "match_confidence": link.get("match_confidence"),
                }
            )

        if total_weight > 0:
            card_score = round(weighted_score / total_weight, 2)
            card_payload.update(
                {
                    "cardDesirabilityScore": card_score,
                    "card_desirability_score": card_score,
                    "pokemonDesirabilityScore": card_score,
                    "pokemon_desirability_score": card_score,
                    "linkedPokemon": linked_pokemon,
                    "linked_pokemon": linked_pokemon,
                    "linkedPokemonName": ", ".join(
                        entry.get("pokemonName") for entry in linked_pokemon if entry.get("pokemonName")
                    )
                    or None,
                    "linked_pokemon_name": ", ".join(
                        entry.get("pokemonName") for entry in linked_pokemon if entry.get("pokemonName")
                    )
                    or None,
                    "isHitEligible": is_hit_eligible,
                    "is_hit_eligible": is_hit_eligible,
                }
            )
            enriched_count += 1
            if _to_optional_float(card_payload.get("marketPrice") or card_payload.get("market_price")) is not None:
                priced_linked_count += 1
            if is_hit_eligible:
                hit_eligible_count += 1
        else:
            excluded_non_pokemon_count += 1

        enriched_cards.append(_apply_card_validation_fields(card_payload, total_market_value=total_market_value))

    validation_cards = [
        {
            "cardId": card.get("id") or card.get("cardId") or card.get("card_id"),
            "cardVariantId": card.get("cardVariantId") or card.get("card_variant_id"),
            "name": card.get("name"),
            "rarity": card.get("rarity"),
            "imageUrl": card.get("imageUrl") or card.get("image_url"),
            "marketPrice": card.get("marketPrice") or card.get("market_price") or card.get("currentPrice"),
            "pokemonName": card.get("linkedPokemonName") or card.get("linked_pokemon_name"),
            "pokemonDesirabilityScore": card.get("pokemonDesirabilityScore"),
            "treatmentScore": card.get("treatmentScore"),
            "scarcityScore": card.get("scarcityScore"),
            "adjustedCardAppealScore": card.get("adjustedCardAppealScore"),
            "pullRate": card.get("pullRate"),
            "pullRateSource": card.get("pullRateSource"),
            "setValueShare": card.get("setValueShare"),
            "isHitEligible": card.get("isHitEligible"),
        }
        for card in enriched_cards
    ]

    meta = dict(payload.get("meta") or {})
    desirability_meta = {
        "source": "pokemon_card_desirability_links+pokemon_desirability_composite_scores",
        "scoringVersion": "card_appeal_v1",
        "valueScope": "visible_near_mint_market_price",
        "priceSource": "pokemon_set_cards_snapshot.marketPrice",
        "totalCards": len(cards),
        "linkedPokemonCards": enriched_count,
        "pricedLinkedPokemonCards": priced_linked_count,
        "excludedNonPokemonCards": excluded_non_pokemon_count,
        "hitEligibleCardCount": hit_eligible_count,
        "enrichedCardCount": enriched_count,
        "total_cards": len(cards),
        "linked_pokemon_cards": enriched_count,
        "priced_linked_pokemon_cards": priced_linked_count,
        "excluded_non_pokemon_cards": excluded_non_pokemon_count,
        "hit_eligible_card_count": hit_eligible_count,
        "enriched_card_count": enriched_count,
    }
    meta["cardDesirability"] = desirability_meta
    meta["card_desirability"] = desirability_meta
    return {
        **payload,
        "cards": enriched_cards,
        "cardDesirabilityValidation": {
            "cards": validation_cards,
            "meta": {**desirability_meta, "generatedAt": datetime.now(timezone.utc).isoformat()},
        },
        "card_desirability_validation": {
            "cards": validation_cards,
            "meta": {**desirability_meta, "generated_at": datetime.now(timezone.utc).isoformat()},
        },
        "meta": meta,
    }


def _latest_standard_set_value_from_histories(histories_by_scope: Any) -> Dict[str, Any]:
    if not isinstance(histories_by_scope, dict):
        return {}
    history = histories_by_scope.get("standard") or histories_by_scope.get("checklist") or []
    if not isinstance(history, list):
        return {}

    latest: Dict[str, Any] = {}
    latest_date: Optional[str] = None
    for point in history:
        if not isinstance(point, dict):
            continue
        value = _to_optional_float(point.get("setValue") or point.get("set_value") or point.get("value"))
        if value is None or value <= 0:
            continue
        date_key = _parse_date_key(point.get("date") or point.get("snapshot_date") or point.get("sourceDate") or point.get("source_date"))
        if latest_date is not None and date_key is not None and date_key < latest_date:
            continue
        latest = {"value": round(value, 2), "date": date_key}
        if date_key:
            latest_date = date_key

    return latest


def _load_latest_checklist_set_values(set_ids: List[str]) -> Dict[str, Dict[str, Any]]:
    clean_ids = sorted({_to_optional_str(set_id) for set_id in set_ids if _to_optional_str(set_id)})
    if not clean_ids:
        return {}

    window_priority = {
        DEFAULT_TOP_CHASE_DASHBOARD_WINDOW: 0,
        DEFAULT_DASHBOARD_WINDOW: 1,
    }
    try:
        result = (
            public_read_client.table("pokemon_set_market_dashboard_snapshot_latest")
            .select("set_id,window_key,set_value_histories_json,latest_market_date,updated_at")
            .in_("set_id", clean_ids)
            .in_("window_key", [DEFAULT_TOP_CHASE_DASHBOARD_WINDOW, DEFAULT_DASHBOARD_WINDOW])
            .execute()
        )
    except Exception as exc:
        if _is_missing_snapshot_relation_error(exc):
            logger.warning("[pokemon-snapshot] checklist set value snapshot relation missing; continuing without enrichment")
        else:
            logger.warning("[pokemon-snapshot] checklist set value enrichment failed", exc_info=True)
        return {}

    values: Dict[str, Dict[str, Any]] = {}
    for row in result.data or []:
        set_id = _to_optional_str(row.get("set_id"))
        if not set_id:
            continue
        latest = _latest_standard_set_value_from_histories(row.get("set_value_histories_json"))
        value = _to_optional_float(latest.get("value"))
        if value is None:
            continue
        candidate = {
            "value": round(value, 2),
            "date": latest.get("date") or _parse_date_key(row.get("latest_market_date")),
            "updated_at": _to_optional_str(row.get("updated_at")),
            "window_key": _to_optional_str(row.get("window_key")),
        }
        existing = values.get(set_id)
        if existing is None or window_priority.get(candidate["window_key"], 99) < window_priority.get(existing.get("window_key"), 99):
            values[set_id] = candidate

    return values


def _enrich_rankings_payload_with_checklist_set_values(payload: Dict[str, Any]) -> Dict[str, Any]:
    targets = list(payload.get("targets") or [])
    if not targets:
        return payload

    set_ids = [
        _to_optional_str(target.get("set_id") or target.get("id") or target.get("target_id"))
        for target in targets
    ]
    value_lookup = _load_latest_checklist_set_values([set_id for set_id in set_ids if set_id])
    if not value_lookup:
        return payload

    enriched_targets: List[Dict[str, Any]] = []
    for target in targets:
        target_payload = dict(target or {})
        set_id = _to_optional_str(target_payload.get("set_id") or target_payload.get("id") or target_payload.get("target_id"))
        latest_value = value_lookup.get(set_id or "")
        if latest_value:
            target_payload.update(
                {
                    "checklistSetValue": latest_value.get("value"),
                    "checklist_set_value": latest_value.get("value"),
                    "currentChecklistSetValue": latest_value.get("value"),
                    "current_checklist_set_value": latest_value.get("value"),
                    "checklistSetValueAsOf": latest_value.get("date"),
                    "checklist_set_value_as_of": latest_value.get("date"),
                }
            )
            market_payload = dict(target_payload.get("market") or {})
            market_payload.update(
                {
                    "checklistSetValue": latest_value.get("value"),
                    "checklist_set_value": latest_value.get("value"),
                    "asOf": latest_value.get("date"),
                    "as_of": latest_value.get("date"),
                    "source": "pokemon_set_market_dashboard_snapshot_latest",
                }
            )
            target_payload["market"] = market_payload
        enriched_targets.append(target_payload)

    meta = dict(payload.get("meta") or {})
    sources = dict(meta.get("sources") or {})
    sources["checklist_set_value_enrichment"] = "pokemon_set_market_dashboard_snapshot_latest"
    meta["sources"] = sources
    return {**payload, "targets": enriched_targets, "meta": meta}


def _resolve_set_row(set_id: str) -> Dict[str, Any]:
    resolved = _to_optional_str(set_id)
    if not resolved:
        raise PokemonSetMarketError(400, "set_id is required", "POKEMON_SET_ID_REQUIRED")

    for field in ("id", "canonical_key", "pokemon_api_set_id"):
        try:
            result = (
                public_read_client.table("sets")
                .select("id,name,canonical_key,pokemon_api_set_id")
                .eq(field, resolved)
                .limit(1)
                .execute()
            )
            row = _first_row(result)
            if row:
                return row
        except Exception:
            logger.warning("[pokemon-snapshot] set lookup failed field=%s set_id=%s", field, resolved)

    normalized_resolved = _normalise_set_lookup_key(resolved)
    if normalized_resolved:
        try:
            result = (
                public_read_client.table("sets")
                .select("id,name,canonical_key,pokemon_api_set_id")
                .execute()
            )
            for row in list(result.data or []):
                candidate_keys = (
                    row.get("id"),
                    row.get("name"),
                    row.get("canonical_key"),
                    row.get("pokemon_api_set_id"),
                )
                if any(_normalise_set_lookup_key(candidate) == normalized_resolved for candidate in candidate_keys):
                    logger.info(
                        "[pokemon-snapshot] resolved set identifier by normalized slug raw=%s canonical_set_id=%s canonical_key=%s",
                        resolved,
                        row.get("id"),
                        row.get("canonical_key"),
                    )
                    return row
        except Exception:
            logger.warning("[pokemon-snapshot] normalized set lookup failed set_id=%s", resolved)

    raise PokemonSetMarketError(404, "Pokemon set not found", "POKEMON_SET_NOT_FOUND")


def _snapshot_meta(row: Dict[str, Any], source: str) -> Dict[str, Any]:
    return {
        "source": source,
        "snapshot": {
            "asOf": _to_optional_str(row.get("as_of")),
            "sourceUpdatedAt": _to_optional_str(row.get("source_updated_at")),
            "updatedAt": _to_optional_str(row.get("updated_at")),
            "isStaleFallback": True,
        },
    }


def _merge_snapshot_meta(payload: Dict[str, Any], row: Dict[str, Any], source: str) -> Dict[str, Any]:
    meta = dict(payload.get("meta") or {})
    snapshot = dict(meta.get("snapshot") or {})
    snapshot.update(_snapshot_meta(row, source)["snapshot"])
    meta["snapshot"] = snapshot
    return {**payload, "meta": meta}


def _with_desirability_validation(payload: Dict[str, Any], set_id: str) -> Dict[str, Any]:
    if isinstance(payload.get("desirabilityValidation"), dict) or isinstance(payload.get("desirability_validation"), dict):
        return payload
    try:
        rankings = get_pokemon_explore_rankings_snapshot_payload(limit=DEFAULT_RANKINGS_LIMIT)
        validation = build_desirability_validation_payload(
            set_id=set_id,
            set_payload=payload,
            target_rows=rankings.get("targets") or [],
        )
    except Exception:
        logger.warning("[pokemon-snapshot] desirability validation fallback failed set_id=%s", set_id, exc_info=True)
        return payload
    meta = dict(payload.get("meta") or {})
    sources = dict(meta.get("sources") or {})
    sources["desirability_validation"] = "runtime_from_rankings_snapshot"
    meta["sources"] = sources
    return {
        **payload,
        "desirabilityValidation": validation,
        "desirability_validation": validation,
        "meta": meta,
    }


def get_pokemon_set_page_snapshot_payload(set_id: str) -> Dict[str, Any]:
    started = time.perf_counter()
    set_row = _resolve_set_row(set_id)
    resolved_set_id = str(set_row["id"])

    try:
        result = (
            public_read_client.table("pokemon_set_page_snapshot_latest")
            .select("set_id,payload_json,as_of,source_updated_at,updated_at")
            .eq("set_id", resolved_set_id)
            .limit(1)
            .execute()
        )
        row = _first_row(result)
        if row and isinstance(row.get("payload_json"), dict):
            payload = _merge_snapshot_meta(row["payload_json"], row, "pokemon_set_page_snapshot_latest")
            payload = _with_desirability_validation(payload, resolved_set_id)
            timings = dict((payload.get("meta") or {}).get("timings") or {})
            timings["snapshot_read_ms"] = round((time.perf_counter() - started) * 1000, 3)
            payload["meta"] = {**(payload.get("meta") or {}), "timings": timings}
            return payload
    except Exception:
        logger.exception("[pokemon-snapshot] set page snapshot read failed set_id=%s", resolved_set_id)
        raise ExplorePageError(500, "Failed to read Pokemon set page snapshot", "POKEMON_SET_PAGE_SNAPSHOT_FAILED")

    logger.warning("[pokemon-snapshot] missing set page snapshot; falling back to live assembly set_id=%s", resolved_set_id)
    payload = get_explore_page_payload("set", resolved_set_id)
    meta = dict(payload.get("meta") or {})
    warnings = list(meta.get("warnings") or [])
    warnings.append("Pokemon set page snapshot is missing; served live fallback data.")
    meta["warnings"] = warnings
    meta["snapshot"] = {
        "source": "live_fallback_missing_pokemon_set_page_snapshot_latest",
        "updatedAt": datetime.now(timezone.utc).isoformat(),
        "isStaleFallback": False,
    }
    return _with_desirability_validation({**payload, "meta": meta}, resolved_set_id)


def get_pokemon_explore_rankings_snapshot_payload(limit: Any = DEFAULT_RANKINGS_LIMIT) -> Dict[str, Any]:
    clamped_limit = _sanitize_limit(limit, default=DEFAULT_RANKINGS_LIMIT, max_value=MAX_RANKINGS_LIMIT)
    try:
        result = (
            public_read_client.table("pokemon_explore_rankings_snapshot_latest")
            .select("tcg,scope,ranking_payload_json,default_target_json,updated_at")
            .eq("tcg", "pokemon")
            .eq("scope", DEFAULT_RANKINGS_SCOPE)
            .limit(1)
            .execute()
        )
        row = _first_row(result)
        if row and isinstance(row.get("ranking_payload_json"), dict):
            payload = _enrich_rankings_payload_with_checklist_set_values(row["ranking_payload_json"])
            raw_targets = list(payload.get("targets") or [])
            targets = [target for target in raw_targets if is_opening_set_row(target)][:clamped_limit]
            meta = dict(payload.get("meta") or {})
            opening_set_audit = build_opening_set_audit(raw_targets)
            request = dict(meta.get("request") or {})
            request["limit"] = clamped_limit
            snapshot = dict(meta.get("snapshot") or {})
            snapshot.update(
                {
                    "source": "pokemon_explore_rankings_snapshot_latest",
                    "updatedAt": _to_optional_str(row.get("updated_at")),
                    "isStaleFallback": True,
                }
            )
            meta["request"] = request
            meta["snapshot"] = snapshot
            meta["openingSetAudit"] = opening_set_audit
            meta["opening_set_audit"] = opening_set_audit
            return {
                **payload,
                "targets": targets,
                "default_target": payload.get("default_target") or row.get("default_target_json") or None,
                "meta": meta,
            }
    except Exception:
        logger.exception("[pokemon-snapshot] explore rankings snapshot read failed")
        raise ExploreRipStatisticsTargetsError(
            status_code=500,
            message="Failed to read RIP Statistics targets snapshot",
            code="RIP_STATISTICS_TARGETS_SNAPSHOT_FAILED",
        )

    logger.warning("[pokemon-snapshot] missing explore rankings snapshot; falling back to live target assembly")
    payload = _enrich_rankings_payload_with_checklist_set_values(get_rip_statistics_targets_payload(limit=clamped_limit))
    meta = dict(payload.get("meta") or {})
    warnings = list(meta.get("warnings") or [])
    warnings.append("Explore rankings snapshot is missing; served live fallback data.")
    meta["warnings"] = warnings
    meta["snapshot"] = {
        "source": "live_fallback_missing_pokemon_explore_rankings_snapshot_latest",
        "updatedAt": datetime.now(timezone.utc).isoformat(),
        "isStaleFallback": False,
    }
    return {**payload, "meta": meta}


def get_pokemon_set_cards_snapshot_payload(set_id: str) -> Dict[str, Any]:
    set_row = _resolve_set_row(set_id)
    resolved_set_id = str(set_row["id"])
    try:
        result = (
            public_read_client.table("pokemon_set_cards_snapshot_latest")
            .select("set_id,payload_json,card_count,updated_at")
            .eq("set_id", resolved_set_id)
            .limit(1)
            .execute()
        )
        row = _first_row(result)
        if row and isinstance(row.get("payload_json"), dict):
            payload = row["payload_json"]
            meta = dict(payload.get("meta") or {})
            card_validation = payload.get("cardDesirabilityValidation") or payload.get("card_desirability_validation") or {}
            card_validation_cards = card_validation.get("cards") if isinstance(card_validation, dict) else []
            meta["cardDesirabilityValidation"] = {
                "precomputed": True,
                "rowCount": len(card_validation_cards) if isinstance(card_validation_cards, list) else 0,
                "source": "pokemon_set_cards_snapshot_latest.payload_json",
            }
            meta["card_desirability_validation"] = {
                "precomputed": True,
                "row_count": len(card_validation_cards) if isinstance(card_validation_cards, list) else 0,
                "source": "pokemon_set_cards_snapshot_latest.payload_json",
            }
            snapshot = dict(meta.get("snapshot") or {})
            snapshot.update(
                {
                    "source": "pokemon_set_cards_snapshot_latest",
                    "updatedAt": _to_optional_str(row.get("updated_at")),
                    "cardCount": row.get("card_count"),
                    "isStaleFallback": True,
                }
            )
            meta["snapshot"] = snapshot
            return {**payload, "meta": meta}
    except Exception:
        logger.exception("[pokemon-snapshot] cards snapshot read failed set_id=%s", resolved_set_id)
        raise PokemonSetCardsError(500, "Failed to read Pokemon set cards snapshot", "POKEMON_SET_CARDS_SNAPSHOT_FAILED")

    logger.warning("[pokemon-snapshot] missing cards snapshot; falling back to canonical cards set_id=%s", resolved_set_id)
    payload = get_pokemon_set_cards_payload(resolved_set_id)
    meta = dict(payload.get("meta") or {})
    warnings = list(meta.get("warnings") or [])
    warnings.append("Pokemon set cards snapshot is missing; served canonical checklist fallback data.")
    meta["warnings"] = warnings
    meta["cardDesirabilityValidation"] = {
        "precomputed": False,
        "rowCount": 0,
        "source": None,
    }
    meta["card_desirability_validation"] = {
        "precomputed": False,
        "row_count": 0,
        "source": None,
    }
    meta["snapshot"] = {
        "source": "live_fallback_missing_pokemon_set_cards_snapshot_latest",
        "updatedAt": datetime.now(timezone.utc).isoformat(),
        "isStaleFallback": False,
    }
    return {**payload, "meta": meta}


def _top_chase_variant_ids(cards: List[Dict[str, Any]]) -> List[str]:
    variant_ids: List[str] = []
    seen: set[str] = set()
    for card in cards:
        if not isinstance(card, dict):
            continue
        variant_id = _to_optional_str(card.get("cardVariantId")) or _to_optional_str(card.get("card_variant_id"))
        if variant_id and variant_id not in seen:
            seen.add(variant_id)
            variant_ids.append(variant_id)
    return variant_ids


def _top_chase_history_for_card(card: Dict[str, Any], histories: Dict[str, List[Dict[str, Any]]]) -> List[Dict[str, Any]]:
    for key in (
        card.get("cardVariantId"),
        card.get("card_variant_id"),
        card.get("cardId"),
        card.get("card_id"),
        card.get("id"),
    ):
        normalized = _to_optional_str(key)
        if normalized and isinstance(histories.get(normalized), list):
            return histories[normalized]
    return []


def _compact_top_chase_observation_rows(rows: List[Dict[str, Any]]) -> Dict[str, List[Dict[str, Any]]]:
    point_by_variant_date: Dict[str, Dict[str, Dict[str, Any]]] = {}
    captured_at_by_variant_date: Dict[str, Dict[str, str]] = {}
    for row in rows:
        variant_id = _to_optional_str(row.get("card_variant_id"))
        captured_at = _to_optional_str(row.get("captured_at") or row.get("capturedAt"))
        captured_date = _parse_date_key(captured_at)
        price = _to_optional_float(row.get("market_price") if "market_price" in row else row.get("marketPrice"))
        if not variant_id or not captured_date or price is None or price <= 0:
            continue
        existing_captured_at = captured_at_by_variant_date.setdefault(variant_id, {}).get(captured_date)
        if existing_captured_at and captured_at and captured_at <= existing_captured_at:
            continue
        captured_at_by_variant_date[variant_id][captured_date] = captured_at or captured_date
        point_by_variant_date.setdefault(variant_id, {})[captured_date] = {
            "date": captured_date,
            "marketPrice": round(price, 2),
            "market_price": round(price, 2),
            "sourceDate": captured_date,
            "source_date": captured_date,
            "isObserved": True,
            "is_observed": True,
        }

    return {
        variant_id: [points[date_key] for date_key in sorted(points.keys())]
        for variant_id, points in point_by_variant_date.items()
        if points
    }


def _compact_top_chase_history_points(points: Any) -> List[Dict[str, Any]]:
    compact_points: Dict[str, Dict[str, Any]] = {}
    for point in list(points or []):
        if not isinstance(point, dict):
            continue
        date_key = _parse_date_key(point.get("date") or point.get("snapshot_date") or point.get("capturedAt") or point.get("captured_at"))
        price = _to_optional_float(point.get("marketPrice") if "marketPrice" in point else point.get("market_price", point.get("price")))
        if not date_key or price is None:
            continue
        source_date = _parse_date_key(point.get("sourceDate") or point.get("source_date")) or date_key
        compact_points[date_key] = {
            "date": date_key,
            "marketPrice": round(price, 2),
            "market_price": round(price, 2),
            "sourceDate": source_date,
            "source_date": source_date,
        }
    return [compact_points[date_key] for date_key in sorted(compact_points.keys())]


def _existing_top_chase_histories(
    payload: Dict[str, Any],
    row: Dict[str, Any],
) -> Dict[str, List[Dict[str, Any]]]:
    for candidate in (
        payload.get("topChaseCardHistories"),
        payload.get("top_chase_card_histories"),
        row.get("top_chase_card_histories_json"),
    ):
        if not isinstance(candidate, dict):
            continue
        histories = {
            str(key): compact_history
            for key, value in candidate.items()
            if key is not None
            and isinstance(value, list)
            and (compact_history := _compact_top_chase_history_points(value))
        }
        if histories:
            return histories
    return {}


def _top_chase_history_counts(histories: Dict[str, List[Dict[str, Any]]]) -> List[int]:
    return [len(history) for history in histories.values() if isinstance(history, list)]


def _top_chase_histories_cover_source_window(
    histories: Dict[str, List[Dict[str, Any]]],
    *,
    variant_ids: List[str],
    source_window_days: int,
) -> bool:
    if not variant_ids:
        return bool(histories)
    for variant_id in variant_ids:
        history = histories.get(variant_id)
        if not isinstance(history, list) or len(history) < source_window_days:
            return False
    return True


def _load_top_chase_observation_histories(
    *,
    set_id: str,
    variant_ids: List[str],
    latest_date_key: Optional[str],
    window_days: int,
) -> Dict[str, List[Dict[str, Any]]]:
    if not variant_ids:
        return {}

    resolved_latest_date_key = latest_date_key
    if not resolved_latest_date_key:
        try:
            latest_result = (
                public_read_client.table("card_variant_price_observations")
                .select("captured_at")
                .in_("card_variant_id", variant_ids)
                .eq("condition_id", TOP_CHASE_NEAR_MINT_CONDITION_ID)
                .gt("market_price", 0)
                .order("captured_at", desc=True)
                .limit(1)
                .execute()
            )
            resolved_latest_date_key = _parse_date_key((_first_row(latest_result) or {}).get("captured_at"))
        except Exception as exc:
            logger.warning(
                "[pokemon-snapshot] top chase observation history latest lookup failed set_id=%s error=%s",
                set_id,
                exc,
                exc_info=True,
            )
            return {}

    try:
        latest_date = date.fromisoformat(str(resolved_latest_date_key))
    except (TypeError, ValueError):
        return {}

    start_date = latest_date - timedelta(days=max(window_days - 1, 0))
    end_date = latest_date + timedelta(days=1)
    try:
        history_result = (
            public_read_client.table("card_variant_price_observations")
            .select("card_variant_id,captured_at,market_price")
            .in_("card_variant_id", variant_ids)
            .eq("condition_id", TOP_CHASE_NEAR_MINT_CONDITION_ID)
            .gt("market_price", 0)
            .gte("captured_at", start_date.isoformat())
            .lt("captured_at", end_date.isoformat())
            .order("captured_at", desc=False)
            .execute()
        )
    except Exception as exc:
        logger.warning(
            "[pokemon-snapshot] top chase observation history hydration failed set_id=%s variants=%s error=%s",
            set_id,
            len(variant_ids),
            exc,
            exc_info=True,
        )
        return {}

    return _compact_top_chase_observation_rows(list(history_result.data or []))


def _attach_top_chase_histories(
    payload: Dict[str, Any],
    histories: Dict[str, List[Dict[str, Any]]],
    *,
    source_window_days: int = TOP_CHASE_HISTORY_SOURCE_WINDOW_DAYS,
) -> Dict[str, Any]:
    counts = _top_chase_history_counts(histories)
    observed_dates = [
        str(point.get("date"))[:10]
        for history in histories.values()
        if isinstance(history, list)
        for point in history
        if _parse_date_key(point.get("date"))
    ]

    source_cards = (
        payload.get("topChaseCards")
        if isinstance(payload.get("topChaseCards"), list)
        else payload.get("top_chase_cards")
    )
    cards: List[Dict[str, Any]] = []
    for card in list(source_cards or []):
        if not isinstance(card, dict):
            continue
        next_card = {key: value for key, value in card.items() if key not in {"priceHistory", "price_history"}}
        history = _top_chase_history_for_card(next_card, histories)
        if history:
            next_card["priceHistory"] = history
            next_card["price_history"] = history
        cards.append(next_card)

    next_payload = dict(payload)
    next_payload["topChaseCardHistories"] = histories
    next_payload["top_chase_card_histories"] = histories
    next_payload["topChaseCards"] = cards
    next_payload["top_chase_cards"] = cards
    meta = dict(next_payload.get("meta") or {})
    meta["topChaseHistorySource"] = TOP_CHASE_HISTORY_SOURCE
    meta["topChaseHistorySourceWindowDays"] = source_window_days
    meta["topChaseHistoryMinPoints"] = min(counts) if counts else 0
    meta["topChaseHistoryMaxPoints"] = max(counts) if counts else 0
    meta["topChaseHistoryFirstObservedDate"] = min(observed_dates) if observed_dates else None
    meta["topChaseHistoryLatestObservedDate"] = max(observed_dates) if observed_dates else None
    meta["topChaseHistoryHydratedFromDailyTable"] = False
    next_payload["meta"] = meta
    return next_payload


def _hydrate_market_dashboard_top_chase_histories(
    payload: Dict[str, Any],
    row: Dict[str, Any],
    *,
    set_id: str,
    window: str,
    days: Any = None,
) -> Dict[str, Any]:
    top_cards = (
        payload.get("topChaseCards")
        if isinstance(payload.get("topChaseCards"), list)
        else payload.get("top_chase_cards")
    )
    cards = [card for card in list(top_cards or []) if isinstance(card, dict)]
    variant_ids = _top_chase_variant_ids(cards)
    histories = _existing_top_chase_histories(payload, row) if not variant_ids else {}
    if variant_ids:
        histories = _load_top_chase_observation_histories(
            set_id=set_id,
            variant_ids=variant_ids,
            latest_date_key=_parse_date_key(
                row.get("latest_market_date") or payload.get("latestMarketDate") or payload.get("latest_market_date")
            ),
            window_days=TOP_CHASE_HISTORY_SOURCE_WINDOW_DAYS,
        )
    return _attach_top_chase_histories(
        payload,
        histories,
        source_window_days=TOP_CHASE_HISTORY_SOURCE_WINDOW_DAYS,
    )


def _read_market_dashboard_snapshot(
    set_id: str,
    window: str = DEFAULT_DASHBOARD_WINDOW,
    days: Any = None,
) -> Optional[Dict[str, Any]]:
    resolved_window = _normalize_market_dashboard_window_key(window)
    try:
        result = (
            public_read_client.table("pokemon_set_market_dashboard_snapshot_latest")
            .select("set_id,window_key,payload_json,top_chase_card_histories_json,latest_market_date,updated_at")
            .eq("set_id", set_id)
            .eq("window_key", resolved_window)
            .limit(1)
            .execute()
        )
    except Exception as exc:
        if _is_missing_snapshot_relation_error(exc):
            logger.warning(
                "[pokemon-snapshot] market dashboard snapshot relation missing set_id=%s window=%s snapshot_read_status=missing_relation fallback_used=true",
                set_id,
                resolved_window,
            )
            return None
        raise

    row = _first_row(result)
    if not row or not isinstance(row.get("payload_json"), dict):
        logger.info(
            "[pokemon-snapshot] market dashboard snapshot missing row set_id=%s window=%s snapshot_read_status=missing_row fallback_used=true",
            set_id,
            resolved_window,
        )
        return None
    payload = _hydrate_market_dashboard_top_chase_histories(
        row["payload_json"],
        row,
        set_id=set_id,
        window=resolved_window,
        days=days,
    )
    meta = dict(payload.get("meta") or {})
    snapshot = dict(meta.get("snapshot") or {})
    snapshot.update(
        {
            "source": "pokemon_set_market_dashboard_snapshot_latest",
            "window": row.get("window_key"),
            "updatedAt": _to_optional_str(row.get("updated_at")),
            "latestMarketDate": _parse_date_key(row.get("latest_market_date")),
            "isStaleFallback": True,
        }
    )
    meta["snapshot"] = snapshot
    return {**payload, "meta": meta}


def _empty_market_dashboard_payload(
    *,
    set_row: Dict[str, Any],
    window: str,
    warnings: Optional[List[str]] = None,
    fallback_source: str,
) -> Dict[str, Any]:
    resolved_window = _normalize_market_dashboard_window_key(window)
    histories_by_scope: Dict[str, List[Dict[str, Any]]] = {scope: [] for scope in SET_VALUE_SCOPES}
    available_scopes: List[Dict[str, Any]] = [
        {"key": scope, "label": SET_VALUE_SCOPE_LABELS.get(scope, scope), "latestDate": None}
        for scope in SET_VALUE_SCOPES
    ]
    return {
        "set": {
            "id": _to_optional_str(set_row.get("id")),
            "name": _to_optional_str(set_row.get("name")),
            "slug": _to_optional_str(set_row.get("canonical_key")),
            "pokemon_api_set_id": _to_optional_str(set_row.get("pokemon_api_set_id")),
        },
        "window": resolved_window,
        "window_key": resolved_window,
        "setValueHistoriesByScope": histories_by_scope,
        "set_value_histories_by_scope": histories_by_scope,
        "performanceVsCostHistory": [],
        "performance_vs_cost_history": [],
        "topChaseCards": [],
        "top_chase_cards": [],
        "availableScopes": available_scopes,
        "available_scopes": available_scopes,
        "latestMarketDate": None,
        "latest_market_date": None,
        "meta": {
            "warnings": list(warnings or []),
            "snapshot": {
                "source": fallback_source,
                "updatedAt": datetime.now(timezone.utc).isoformat(),
                "isStaleFallback": False,
            },
        },
    }


def get_pokemon_set_market_dashboard_snapshot_payload(
    set_id: str,
    window: str = DEFAULT_DASHBOARD_WINDOW,
    days: Any = None,
) -> Dict[str, Any]:
    set_row = _resolve_set_row(set_id)
    resolved_set_id = str(set_row["id"])
    resolved_window = _normalize_market_dashboard_window_key(window)
    resolved_days = _sanitize_days(days, default=DEFAULT_SET_VALUE_HISTORY_DAYS)
    try:
        payload = _read_market_dashboard_snapshot(resolved_set_id, resolved_window, days=_market_dashboard_window_days(resolved_window, days))
        if payload is not None:
            logger.info(
                "[pokemon-snapshot] market dashboard snapshot read set_id=%s resolved_set_id=%s window=%s snapshot_read_status=hit fallback_used=false",
                set_id,
                resolved_set_id,
                resolved_window,
            )
            return payload
    except Exception as exc:
        logger.warning(
            "[pokemon-snapshot] market dashboard snapshot read failed set_id=%s resolved_set_id=%s window=%s snapshot_read_status=failed fallback_used=true error=%s",
            set_id,
            resolved_set_id,
            resolved_window,
            exc,
            exc_info=True,
        )

    logger.warning("[pokemon-snapshot] missing market dashboard snapshot; falling back to live market assembly set_id=%s", resolved_set_id)
    histories_by_scope: Dict[str, List[Dict[str, Any]]] = {}
    warnings: List[str] = ["Pokemon market dashboard snapshot is missing; served live fallback data."]
    for scope in SET_VALUE_SCOPES:
        try:
            value_payload = get_pokemon_set_value_history_payload(resolved_set_id, days=resolved_days, value_scope=scope)
            histories_by_scope[scope] = list(value_payload.get("history") or [])
            warnings.extend((value_payload.get("meta") or {}).get("warnings") or [])
        except Exception as exc:
            histories_by_scope[scope] = []
            warnings.append(f"Pokemon set value history is unavailable for {scope}; served remaining market data.")
            logger.warning(
                "[pokemon-snapshot] live market dashboard value history fallback failed set_id=%s resolved_set_id=%s window=%s scope=%s error=%s",
                set_id,
                resolved_set_id,
                resolved_window,
                scope,
                exc,
                exc_info=True,
            )
    try:
        top_payload = get_pokemon_set_top_market_cards_payload(resolved_set_id, limit=10, days=resolved_days)
        warnings.extend((top_payload.get("meta") or {}).get("warnings") or [])
    except Exception as exc:
        top_payload = {
            "set": {
                "id": _to_optional_str(set_row.get("id")),
                "name": _to_optional_str(set_row.get("name")),
                "slug": _to_optional_str(set_row.get("canonical_key")),
                "pokemon_api_set_id": _to_optional_str(set_row.get("pokemon_api_set_id")),
            },
            "cards": [],
            "meta": {},
        }
        warnings.append("Pokemon top chase card market data is unavailable; served set value history only.")
        logger.warning(
            "[pokemon-snapshot] live market dashboard top cards fallback failed set_id=%s resolved_set_id=%s window=%s error=%s",
            set_id,
            resolved_set_id,
            resolved_window,
            exc,
            exc_info=True,
        )

    latest_market_date = None
    for history in histories_by_scope.values():
        for point in history:
            point_date = _parse_date_key(point.get("date"))
            if point_date and (latest_market_date is None or point_date > latest_market_date):
                latest_market_date = point_date

    has_set_value_history = any(len(history) > 0 for history in histories_by_scope.values())
    top_chase_cards = top_payload.get("cards") or []
    if not has_set_value_history and not top_chase_cards:
        return _empty_market_dashboard_payload(
            set_row=set_row,
            window=resolved_window,
            warnings=[
                *warnings,
                "Pokemon market dashboard data is unavailable; served an empty fallback payload.",
            ],
            fallback_source="empty_fallback_missing_pokemon_set_market_dashboard_snapshot_latest",
        )

    available_scopes = []
    for scope in SET_VALUE_SCOPES:
        scope_dates = []
        for point in histories_by_scope.get(scope, []):
            point_date = _parse_date_key(point.get("date"))
            if point_date:
                scope_dates.append(point_date)
        available_scopes.append(
            {
                "key": scope,
                "label": SET_VALUE_SCOPE_LABELS.get(scope, scope),
                "latestDate": max(scope_dates) if scope_dates else None,
            }
        )
    return {
        "set": top_payload.get("set"),
        "window": resolved_window,
        "window_key": resolved_window,
        "setValueHistoriesByScope": histories_by_scope,
        "set_value_histories_by_scope": histories_by_scope,
        "performanceVsCostHistory": histories_by_scope.get("standard", []),
        "performance_vs_cost_history": histories_by_scope.get("standard", []),
        "topChaseCards": top_chase_cards,
        "top_chase_cards": top_chase_cards,
        "availableScopes": available_scopes,
        "available_scopes": available_scopes,
        "latestMarketDate": latest_market_date,
        "latest_market_date": latest_market_date,
        "meta": {
            "warnings": warnings,
            "snapshot": {
                "source": "live_fallback_missing_pokemon_set_market_dashboard_snapshot_latest",
                "updatedAt": datetime.now(timezone.utc).isoformat(),
                "isStaleFallback": False,
            },
        },
    }


def get_pokemon_set_top_market_cards_snapshot_payload(
    set_id: str,
    limit: Any = None,
    days: Any = None,
) -> Dict[str, Any]:
    del days
    set_row = _resolve_set_row(set_id)
    resolved_set_id = str(set_row["id"])
    limit_value = _sanitize_top_limit(limit)
    dashboard = get_pokemon_set_market_dashboard_snapshot_payload(resolved_set_id)
    cards = list(dashboard.get("topChaseCards") or dashboard.get("top_chase_cards") or [])[:limit_value]
    return {
        "set": dashboard.get("set"),
        "cards": cards,
        "meta": {
            **(dashboard.get("meta") or {}),
            "limit": limit_value,
            "priceBasis": "pokemon_set_market_dashboard_snapshot_latest.top_chase_cards_json",
        },
    }


def get_pokemon_set_value_history_snapshot_payload(
    set_id: str,
    days: Any = None,
    value_scope: Any = None,
) -> Dict[str, Any]:
    set_row = _resolve_set_row(set_id)
    resolved_set_id = str(set_row["id"])
    days_value = _sanitize_days(days)
    scope = _sanitize_scope(value_scope)
    dashboard = get_pokemon_set_market_dashboard_snapshot_payload(resolved_set_id)
    histories_by_scope = dashboard.get("setValueHistoriesByScope") or dashboard.get("set_value_histories_by_scope") or {}
    history = list(histories_by_scope.get(scope) or [])
    if days_value and len(history) > days_value:
        history = history[-days_value:]
    available_scopes = dashboard.get("availableScopes") or dashboard.get("available_scopes") or []
    return {
        "set": dashboard.get("set"),
        "history": history,
        "meta": {
            **(dashboard.get("meta") or {}),
            "days": days_value,
            "valueScope": scope,
            "value_scope": scope,
            "availableScopes": available_scopes,
            "available_scopes": available_scopes,
            "asOfDate": history[-1].get("date") if history else dashboard.get("latestMarketDate"),
            "windowStart": history[0].get("date") if history else None,
            "windowEnd": history[-1].get("date") if history else None,
            "windowDays": len(history),
            "priceBasis": "pokemon_set_market_dashboard_snapshot_latest.set_value_histories_json",
        },
    }
