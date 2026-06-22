from __future__ import annotations

import logging
import time
from datetime import date, datetime, timedelta, timezone
from typing import Any, Dict, List, Optional

from backend.db.clients.supabase_client import public_read_client
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
DEFAULT_TOP_CHASE_DASHBOARD_WINDOW = "30D"
DEFAULT_TOP_CHASE_DASHBOARD_DAYS = 30
MAX_TOP_CHASE_DASHBOARD_DAYS = 365
TOP_CHASE_HISTORY_PAGE_SIZE = 1000
DEFAULT_RANKINGS_SCOPE = "rip-statistics"
DEFAULT_RANKINGS_LIMIT = 100
MAX_RANKINGS_LIMIT = 200
MIN_LIMIT = 1


def _to_optional_str(value: Any) -> Optional[str]:
    if value is None:
        return None
    text = str(value).strip()
    return text or None


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


def _to_optional_float(value: Any) -> Optional[float]:
    try:
        parsed = float(value)
    except (TypeError, ValueError):
        return None
    return parsed if parsed > 0 else None


def _window_days(value: Any) -> Optional[int]:
    normalized = str(value or "").strip().lower().replace("_", "").replace("-", "")
    aliases = {
        "1d": 1,
        "7d": 7,
        "30d": 30,
        "3m": 90,
        "90d": 90,
        "6m": 180,
        "180d": 180,
        "1y": 365,
        "365d": 365,
        "lifetime": MAX_TOP_CHASE_DASHBOARD_DAYS,
    }
    return aliases.get(normalized)


def _sanitize_top_chase_history_days(days: Any = None, window: Any = None) -> int:
    try:
        parsed = int(days)
    except (TypeError, ValueError):
        parsed = _window_days(window) or DEFAULT_TOP_CHASE_DASHBOARD_DAYS
    return max(1, min(parsed, MAX_TOP_CHASE_DASHBOARD_DAYS))


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


def _card_id_key(card: Dict[str, Any]) -> Optional[str]:
    return _to_optional_str(card.get("id")) or _to_optional_str(card.get("cardId")) or _to_optional_str(card.get("card_id"))


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
    return {**payload, "meta": meta}


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
            payload = row["ranking_payload_json"]
            targets = list(payload.get("targets") or [])[:clamped_limit]
            meta = dict(payload.get("meta") or {})
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
    payload = get_rip_statistics_targets_payload(limit=clamped_limit)
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
    meta["snapshot"] = {
        "source": "live_fallback_missing_pokemon_set_cards_snapshot_latest",
        "updatedAt": datetime.now(timezone.utc).isoformat(),
        "isStaleFallback": False,
    }
    return {**payload, "meta": meta}


def _read_market_dashboard_snapshot(set_id: str, window: str = DEFAULT_DASHBOARD_WINDOW) -> Optional[Dict[str, Any]]:
    selected_row = None
    for window_key in [window, DEFAULT_DASHBOARD_WINDOW]:
        if selected_row is not None:
            break
        result = (
            public_read_client.table("pokemon_set_market_dashboard_snapshot_latest")
            .select("set_id,window_key,payload_json,latest_market_date,updated_at")
            .eq("set_id", set_id)
            .eq("window_key", window_key)
            .limit(1)
            .execute()
        )
        selected_row = _first_row(result)
    row = selected_row
    if not row or not isinstance(row.get("payload_json"), dict):
        return None
    payload = row["payload_json"]
    meta = dict(payload.get("meta") or {})
    snapshot = dict(meta.get("snapshot") or {})
    snapshot.update(
        {
            "source": "pokemon_set_market_dashboard_snapshot_latest",
            "window": row.get("window_key"),
            "window_key": row.get("window_key"),
            "updatedAt": _to_optional_str(row.get("updated_at")),
            "latestMarketDate": _parse_date_key(row.get("latest_market_date")),
            "isStaleFallback": True,
        }
    )
    meta["snapshot"] = snapshot
    return {**payload, "meta": meta}


def _top_chase_history_group_key(row: Dict[str, Any]) -> Optional[str]:
    card_variant_id = _to_optional_str(row.get("card_variant_id"))
    card_id = _to_optional_str(row.get("card_id"))
    rank = _to_optional_str(row.get("rank"))
    if card_variant_id:
        return card_variant_id
    if card_id:
        return card_id
    return f"rank:{rank}" if rank else None


def _top_chase_card_history_keys(card: Dict[str, Any], index: int) -> List[str]:
    keys = [
        _to_optional_str(card.get("cardVariantId")),
        _to_optional_str(card.get("card_variant_id")),
        _to_optional_str(card.get("cardId")),
        _to_optional_str(card.get("card_id")),
        _to_optional_str(card.get("id")),
        _to_optional_str(card.get("rank")),
        _to_optional_str(card.get("marketRank")),
        _to_optional_str(card.get("market_rank")),
        f"rank:{index + 1}",
    ]
    seen = set()
    deduped: List[str] = []
    for key in keys:
        if key and key not in seen:
            deduped.append(key)
            seen.add(key)
    return deduped


def _read_top_chase_card_daily_histories(
    resolved_set_id: str,
    *,
    days: Any = None,
    window: Any = None,
) -> Dict[str, List[Dict[str, Any]]]:
    clamped_days = _sanitize_top_chase_history_days(days, window)
    since_date = datetime.now(timezone.utc).date() - timedelta(days=clamped_days)
    rows: List[Dict[str, Any]] = []
    start = 0
    while True:
        result = (
            public_read_client.table("pokemon_set_top_chase_card_daily_history")
            .select(
                "set_id,snapshot_date,card_id,card_variant_id,rank,name,rarity,"
                "image_url,image_small_url,image_large_url,market_price,source,source_date"
            )
            .eq("set_id", resolved_set_id)
            .gte("snapshot_date", since_date.isoformat())
            .order("rank", desc=False)
            .order("snapshot_date", desc=False)
            .range(start, start + TOP_CHASE_HISTORY_PAGE_SIZE - 1)
            .execute()
        )
        page_rows = list(result.data or [])
        rows.extend(page_rows)
        if len(page_rows) < TOP_CHASE_HISTORY_PAGE_SIZE:
            break
        start += TOP_CHASE_HISTORY_PAGE_SIZE

    histories: Dict[str, List[Dict[str, Any]]] = {}
    for row in rows:
        date_key = _parse_date_key(row.get("snapshot_date"))
        key = _top_chase_history_group_key(row)
        if not date_key or not key:
            continue
        price = _to_optional_float(row.get("market_price"))
        source_date = _parse_date_key(row.get("source_date")) or date_key
        point = {
            "date": date_key,
            "marketPrice": round(price, 2) if price is not None else None,
            "market_price": round(price, 2) if price is not None else None,
            "price": round(price, 2) if price is not None else None,
            "cardId": _to_optional_str(row.get("card_id")),
            "card_id": _to_optional_str(row.get("card_id")),
            "cardVariantId": _to_optional_str(row.get("card_variant_id")),
            "card_variant_id": _to_optional_str(row.get("card_variant_id")),
            "rank": row.get("rank"),
            "name": _to_optional_str(row.get("name")),
            "rarity": _to_optional_str(row.get("rarity")),
            "imageUrl": _to_optional_str(row.get("image_url")),
            "image_url": _to_optional_str(row.get("image_url")),
            "imageSmallUrl": _to_optional_str(row.get("image_small_url")),
            "image_small_url": _to_optional_str(row.get("image_small_url")),
            "imageLargeUrl": _to_optional_str(row.get("image_large_url")),
            "image_large_url": _to_optional_str(row.get("image_large_url")),
            "source": _to_optional_str(row.get("source")),
            "provider": _to_optional_str(row.get("source")),
            "sourceDate": source_date,
            "source_date": source_date,
            "isCarriedForward": False,
            "is_carried_forward": False,
        }
        histories.setdefault(key, []).append(point)

    return histories


def get_pokemon_set_top_chase_card_daily_histories_payload(
    set_id: str,
    days: Any = None,
    window: Any = None,
) -> Dict[str, Any]:
    set_row = _resolve_set_row(set_id)
    resolved_set_id = str(set_row["id"])
    clamped_days = _sanitize_top_chase_history_days(days, window)
    histories = _read_top_chase_card_daily_histories(
        resolved_set_id,
        days=clamped_days,
        window=window,
    )
    return {
        "set": {
            "id": _to_optional_str(set_row.get("id")),
            "name": _to_optional_str(set_row.get("name")),
            "slug": _to_optional_str(set_row.get("canonical_key")),
            "pokemon_api_set_id": _to_optional_str(set_row.get("pokemon_api_set_id")),
        },
        "topChaseCardHistories": histories,
        "top_chase_card_histories": histories,
        "meta": {
            "days": clamped_days,
            "window": window or DEFAULT_TOP_CHASE_DASHBOARD_WINDOW,
            "source": "pokemon_set_top_chase_card_daily_history",
        },
    }


def _merge_top_chase_histories_into_dashboard(
    payload: Dict[str, Any],
    histories: Dict[str, List[Dict[str, Any]]],
    *,
    days: int,
    window: Any,
) -> Dict[str, Any]:
    top_cards = list(payload.get("topChaseCards") or payload.get("top_chase_cards") or [])
    cards_with_history: List[Dict[str, Any]] = []
    for index, card in enumerate(top_cards):
        card_payload = dict(card or {})
        history = []
        for key in _top_chase_card_history_keys(card_payload, index):
            history = histories.get(key) or []
            if history:
                break
        if history:
            card_payload["historyPointCount"] = len(history)
            card_payload["history_point_count"] = len(history)
            card_payload["historyStartDate"] = history[0].get("date")
            card_payload["history_start_date"] = history[0].get("date")
            card_payload["historyEndDate"] = history[-1].get("date")
            card_payload["history_end_date"] = history[-1].get("date")
        cards_with_history.append(card_payload)

    meta = dict(payload.get("meta") or {})
    snapshot = dict(meta.get("snapshot") or {})
    snapshot["topChaseHistorySource"] = "pokemon_set_top_chase_card_daily_history"
    meta["snapshot"] = snapshot
    meta["topChaseHistoryDays"] = days
    meta["top_chase_history_days"] = days
    meta["topChaseHistoryWindow"] = window or DEFAULT_TOP_CHASE_DASHBOARD_WINDOW
    meta["top_chase_history_window"] = window or DEFAULT_TOP_CHASE_DASHBOARD_WINDOW
    meta["topChaseHistoryGroups"] = len(histories)
    meta["top_chase_history_groups"] = len(histories)

    return {
        **payload,
        "topChaseCards": cards_with_history,
        "top_chase_cards": cards_with_history,
        "topChaseCardHistories": histories,
        "top_chase_card_histories": histories,
        "meta": meta,
    }


def get_pokemon_set_market_dashboard_snapshot_payload(
    set_id: str,
    window: str = DEFAULT_TOP_CHASE_DASHBOARD_WINDOW,
    days: Any = None,
) -> Dict[str, Any]:
    set_row = _resolve_set_row(set_id)
    resolved_set_id = str(set_row["id"])
    top_chase_history_days = _sanitize_top_chase_history_days(days, window)
    try:
        payload = _read_market_dashboard_snapshot(resolved_set_id, window)
        if payload is not None:
            histories = _read_top_chase_card_daily_histories(
                resolved_set_id,
                days=top_chase_history_days,
                window=window,
            )
            return _merge_top_chase_histories_into_dashboard(
                payload,
                histories,
                days=top_chase_history_days,
                window=window,
            )
    except Exception:
        logger.exception("[pokemon-snapshot] market dashboard snapshot read failed set_id=%s", resolved_set_id)
        raise PokemonSetMarketError(
            500,
            "Failed to read Pokemon set market dashboard snapshot",
            "POKEMON_SET_MARKET_DASHBOARD_SNAPSHOT_FAILED",
        )

    logger.warning("[pokemon-snapshot] missing market dashboard snapshot; falling back to live market assembly set_id=%s", resolved_set_id)
    histories_by_scope: Dict[str, List[Dict[str, Any]]] = {}
    available_scopes: List[Dict[str, Any]] = [
        {"key": scope, "label": SET_VALUE_SCOPE_LABELS.get(scope, scope), "latestDate": None}
        for scope in SET_VALUE_SCOPES
    ]
    warnings: List[str] = ["Pokemon market dashboard snapshot is missing; served live fallback data."]
    for scope in SET_VALUE_SCOPES:
        value_payload = get_pokemon_set_value_history_payload(resolved_set_id, days=365, value_scope=scope)
        histories_by_scope[scope] = list(value_payload.get("history") or [])
        warnings.extend((value_payload.get("meta") or {}).get("warnings") or [])
    top_payload = get_pokemon_set_top_market_cards_payload(resolved_set_id, limit=10, days=top_chase_history_days)
    warnings.extend((top_payload.get("meta") or {}).get("warnings") or [])
    top_cards = top_payload.get("cards") or []
    top_chase_histories: Dict[str, List[Dict[str, Any]]] = {}
    for index, card in enumerate(top_cards):
        history = card.get("priceHistory") if isinstance(card.get("priceHistory"), list) else card.get("price_history")
        if not isinstance(history, list):
            continue
        for key in _top_chase_card_history_keys(card, index):
            top_chase_histories[key] = history
            break
    latest_market_date = None
    for history in histories_by_scope.values():
        for point in history:
            point_date = _parse_date_key(point.get("date"))
            if point_date and (latest_market_date is None or point_date > latest_market_date):
                latest_market_date = point_date
    return {
        "set": top_payload.get("set"),
        "window": window,
        "setValueHistoriesByScope": histories_by_scope,
        "set_value_histories_by_scope": histories_by_scope,
        "performanceVsCostHistory": histories_by_scope.get("standard", []),
        "performance_vs_cost_history": histories_by_scope.get("standard", []),
        "topChaseCards": top_cards,
        "top_chase_cards": top_cards,
        "topChaseCardHistories": top_chase_histories,
        "top_chase_card_histories": top_chase_histories,
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
            "topChaseHistoryDays": top_chase_history_days,
            "top_chase_history_days": top_chase_history_days,
            "topChaseHistoryWindow": window,
            "top_chase_history_window": window,
        },
    }


def get_pokemon_set_top_market_cards_snapshot_payload(
    set_id: str,
    limit: Any = None,
    days: Any = None,
) -> Dict[str, Any]:
    set_row = _resolve_set_row(set_id)
    resolved_set_id = str(set_row["id"])
    limit_value = _sanitize_top_limit(limit)
    top_chase_history_days = _sanitize_top_chase_history_days(days, None)
    dashboard = get_pokemon_set_market_dashboard_snapshot_payload(
        resolved_set_id,
        window=f"{top_chase_history_days}D",
        days=top_chase_history_days,
    )
    cards = list(dashboard.get("topChaseCards") or dashboard.get("top_chase_cards") or [])[:limit_value]
    return {
        "set": dashboard.get("set"),
        "cards": cards,
        "topChaseCardHistories": dashboard.get("topChaseCardHistories") or {},
        "top_chase_card_histories": dashboard.get("top_chase_card_histories") or {},
        "meta": {
            **(dashboard.get("meta") or {}),
            "limit": limit_value,
            "days": top_chase_history_days,
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
