from __future__ import annotations

import argparse
import logging
from datetime import date, datetime, timedelta, timezone
from pathlib import Path
from typing import Any, Dict, Iterable, List, Optional
from uuid import UUID

from dotenv import load_dotenv

from backend.db.clients.supabase_client import create_service_role_client
from backend.db.services.explore_page_service import get_explore_page_payload
from backend.db.services.explore_rip_statistics_service import get_rip_statistics_targets_payload
from backend.db.services.pokemon_set_cards_service import get_pokemon_set_cards_payload
from backend.db.services.pokemon_public_snapshot_service import (
    enrich_cards_payload_with_desirability,
    enrich_cards_payload_with_movements,
)
from backend.db.services.pokemon_set_market_service import (
    SET_VALUE_SCOPES,
    build_pokemon_set_card_movement_payload,
    get_pokemon_set_top_market_cards_payload,
    get_pokemon_set_value_history_payload,
)
from backend.desirability.set_validation import build_desirability_validation_payload, build_opening_set_audit, is_opening_set_row

logger = logging.getLogger(__name__)

DEFAULT_DASHBOARD_WINDOW = "365d"
DEFAULT_DASHBOARD_DAYS = 365
TOP_CHASE_HISTORY_SOURCE_WINDOW_DAYS = DEFAULT_DASHBOARD_DAYS
TOP_CHASE_NEAR_MINT_CONDITION_ID = "4f8d1181-670e-4aea-937c-4d98d2e531a6"
TOP_CHASE_HISTORY_SOURCE = "card_variant_price_observations"
DEFAULT_RANKINGS_LIMIT = 200
DEFAULT_UPSERT_BATCH_SIZE = 500
TOP_CHASE_HISTORY_FIELDS = {"priceHistory", "price_history"}


def load_backend_env() -> None:
    env_path = Path(__file__).resolve().parents[1] / ".env"
    if env_path.exists():
        load_dotenv(dotenv_path=env_path, override=False)
    else:
        load_dotenv(override=False)


def utc_now_iso() -> str:
    return datetime.now(timezone.utc).isoformat()


def first_non_empty(*values: Any) -> Optional[str]:
    for value in values:
        if value is None:
            continue
        text = str(value).strip()
        if text:
            return text
    return None


def parse_date_key(value: Any) -> Optional[str]:
    if isinstance(value, date) and not isinstance(value, datetime):
        return value.isoformat()
    text = first_non_empty(value)
    if not text:
        return None
    if len(text) >= 10 and text[4] == "-" and text[7] == "-":
        return text[:10]
    try:
        return datetime.fromisoformat(text.replace("Z", "+00:00")).date().isoformat()
    except ValueError:
        return None


def to_optional_float(value: Any) -> Optional[float]:
    try:
        parsed = float(value)
    except (TypeError, ValueError):
        return None
    return parsed


def is_uuid_like(value: Any) -> bool:
    text = first_non_empty(value)
    if not text:
        return False
    try:
        UUID(text)
    except (TypeError, ValueError, AttributeError):
        return False
    return True


def resolve_set_row(client: Any, set_identifier: str) -> Dict[str, Any]:
    resolved = first_non_empty(set_identifier)
    if not resolved:
        raise ValueError("set_id is required")

    lookup_columns = ["canonical_key", "pokemon_api_set_id"]
    if is_uuid_like(resolved):
        lookup_columns.insert(0, "id")

    selected_columns = (
        "id,name,canonical_key,pokemon_api_set_id,release_date,logo_image_url,"
        "symbol_image_url,hero_image_url"
    )
    for column in lookup_columns:
        try:
            result = client.table("sets").select(selected_columns).eq(column, resolved).limit(1).execute()
        except Exception:
            logger.exception("set lookup failed field=%s value=%s", column, resolved)
            continue
        rows = list(result.data or [])
        if rows:
            return rows[0]

    raise ValueError(f"Pokemon set not found: {set_identifier}")


def list_pokemon_sets(client: Any) -> List[Dict[str, Any]]:
    result = (
        client.table("sets")
        .select(
            "id,name,canonical_key,pokemon_api_set_id,release_date,logo_image_url,"
            "symbol_image_url,hero_image_url"
        )
        .order("release_date", desc=True)
        .execute()
    )
    return [row for row in (result.data or []) if row.get("id")]


def resolve_target_sets(client: Any, args: argparse.Namespace) -> List[Dict[str, Any]]:
    if args.all:
        return list_pokemon_sets(client)
    return [resolve_set_row(client, args.set_id)]


def add_target_set_args(parser: argparse.ArgumentParser) -> None:
    target_group = parser.add_mutually_exclusive_group(required=True)
    target_group.add_argument("--all", action="store_true", help="Build snapshots for all Pokemon sets")
    target_group.add_argument("--set-id", help="Build snapshots for one set id, canonical key, or Pokemon API set id")
    mode_group = parser.add_mutually_exclusive_group()
    mode_group.add_argument("--dry-run", action="store_true", help="Build and log without writing")
    mode_group.add_argument("--commit", action="store_true", help="Upsert snapshot rows")


def should_commit(args: argparse.Namespace) -> bool:
    return bool(args.commit)


def with_snapshot_meta(payload: Dict[str, Any], *, snapshot_type: str, built_at: str) -> Dict[str, Any]:
    meta = dict(payload.get("meta") or {})
    snapshot_meta = dict(meta.get("snapshot") or {})
    snapshot_meta.update(
        {
            "type": snapshot_type,
            "builtAt": built_at,
            "source": "pokemon_snapshot_builders",
        }
    )
    meta["snapshot"] = snapshot_meta
    return {**payload, "meta": meta}


def _summary_subset(summary: Dict[str, Any], keys: Iterable[str]) -> Dict[str, Any]:
    return {key: summary.get(key) for key in keys if key in summary}


def build_set_page_snapshot_row(set_row: Dict[str, Any]) -> Dict[str, Any]:
    built_at = utc_now_iso()
    set_id = str(set_row["id"])
    payload = get_explore_page_payload("set", set_id)
    try:
        rankings_payload = get_rip_statistics_targets_payload(limit=DEFAULT_RANKINGS_LIMIT)
        desirability_validation = build_desirability_validation_payload(
            set_id=set_id,
            set_payload=payload,
            target_rows=rankings_payload.get("targets") or [],
        )
        payload["desirabilityValidation"] = desirability_validation
        payload["desirability_validation"] = desirability_validation
    except Exception:
        logger.warning("desirability validation build failed set_id=%s", set_id, exc_info=True)
        meta = dict(payload.get("meta") or {})
        warnings = list(meta.get("warnings") or [])
        warnings.append("Desirability validation could not be generated for this snapshot.")
        meta["warnings"] = warnings
        payload["meta"] = meta
    payload = with_snapshot_meta(payload, snapshot_type="pokemon_set_page", built_at=built_at)
    summary = payload.get("summary") if isinstance(payload.get("summary"), dict) else {}

    set_identity = {
        "id": set_id,
        "name": set_row.get("name"),
        "slug": set_row.get("canonical_key"),
        "pokemon_api_set_id": set_row.get("pokemon_api_set_id"),
        "release_date": set_row.get("release_date"),
        "logo_image_url": set_row.get("logo_image_url"),
        "symbol_image_url": set_row.get("symbol_image_url"),
        "hero_image_url": set_row.get("hero_image_url"),
    }
    title_card = {
        **set_identity,
        **_summary_subset(
            summary,
            (
                "pack_score",
                "pack_tier",
                "pack_rank",
                "pack_cost",
                "mean_value",
                "median_value",
                "prob_profit",
                "prob_big_hit",
                "p95_value_to_cost_ratio",
                "p99_value_to_cost_ratio",
            ),
        ),
    }
    rip_summary = _summary_subset(
        summary,
        (
            "pack_score",
            "relative_pack_score",
            "pack_rank",
            "pack_tier",
            "profit_score",
            "safety_score",
            "stability_score",
            "desirability_score",
            "experience_score",
            "chase_potential_score",
        ),
    )
    market_summary = _summary_subset(
        summary,
        (
            "pack_cost",
            "mean_value",
            "median_value",
            "mean_value_to_cost_ratio",
            "median_value_to_cost_ratio",
            "roi_percent",
            "prob_profit",
            "prob_big_hit",
            "p95_value_to_cost_ratio",
            "p99_value_to_cost_ratio",
            "simulated_set_value",
            "simulated_set_value_card_count",
        ),
    )
    risk_summary = _summary_subset(
        summary,
        (
            "expected_loss_when_losing_fraction",
            "median_loss_when_losing_fraction",
            "p05_shortfall_to_cost",
            "expected_loss_when_losing",
            "median_loss_when_losing",
            "tail_value_p05",
            "coefficient_of_variation",
        ),
    )
    concentration = _summary_subset(
        summary,
        ("hhi_ev_concentration", "effective_chase_count", "top1_ev_share", "top3_ev_share", "top5_ev_share"),
    )

    return {
        "set_id": set_id,
        "set_identity_json": set_identity,
        "title_card_json": title_card,
        "rip_summary_json": rip_summary,
        "market_summary_json": market_summary,
        "risk_summary_json": risk_summary,
        "concentration_json": concentration,
        "desirability_summary_json": payload.get("openingDesirability") or {},
        "set_intelligence_json": payload.get("interpretation") or {},
        "payload_json": payload,
        "as_of": first_non_empty(summary.get("run_at"), payload.get("meta", {}).get("asOfDate"), built_at),
        "source_updated_at": first_non_empty(summary.get("run_at"), built_at),
    }


def _latest_history_date(histories_by_scope: Dict[str, List[Dict[str, Any]]]) -> Optional[str]:
    latest: Optional[str] = None
    for history in histories_by_scope.values():
        for point in history:
            date_key = first_non_empty(point.get("date"), point.get("snapshot_date"))
            if date_key and (latest is None or date_key > latest):
                latest = date_key
    return latest


def _top_chase_variant_ids(cards: List[Dict[str, Any]]) -> List[str]:
    variant_ids: List[str] = []
    seen: set[str] = set()
    for card in cards:
        variant_id = first_non_empty(card.get("cardVariantId"), card.get("card_variant_id"))
        if variant_id and variant_id not in seen:
            seen.add(variant_id)
            variant_ids.append(variant_id)
    return variant_ids


def _has_top_chase_history_points(history_by_card: Dict[str, List[Dict[str, Any]]]) -> bool:
    return any(isinstance(history, list) and len(history) > 0 for history in history_by_card.values())


def _top_chase_history_counts(history_by_card: Dict[str, List[Dict[str, Any]]]) -> List[int]:
    return [len(history) for history in history_by_card.values() if isinstance(history, list)]


def _top_chase_histories_cover_source_window(
    history_by_card: Dict[str, List[Dict[str, Any]]],
    *,
    variant_ids: List[str],
    source_window_days: int,
) -> bool:
    if not variant_ids:
        return _has_top_chase_history_points(history_by_card)
    for variant_id in variant_ids:
        history = history_by_card.get(variant_id)
        if not isinstance(history, list) or len(history) < source_window_days:
            return False
    return True


def _load_top_chase_histories_from_observations(
    client: Any,
    *,
    set_id: str,
    variant_ids: List[str],
    latest_date_key: Optional[str],
    days: int,
) -> Dict[str, List[Dict[str, Any]]]:
    if not variant_ids:
        return {}

    resolved_latest_date_key = first_non_empty(latest_date_key)
    if not resolved_latest_date_key:
        try:
            latest_result = (
                client.table("card_variant_price_observations")
                .select("captured_at")
                .in_("card_variant_id", variant_ids)
                .eq("condition_id", TOP_CHASE_NEAR_MINT_CONDITION_ID)
                .gt("market_price", 0)
                .order("captured_at", desc=True)
                .limit(1)
                .execute()
            )
            latest_rows = list(latest_result.data or [])
            resolved_latest_date_key = parse_date_key((latest_rows[0] if latest_rows else {}).get("captured_at"))
        except Exception:
            logger.warning("top chase observation history latest lookup failed set_id=%s", set_id, exc_info=True)
            return {}

    try:
        latest_date = date.fromisoformat(str(resolved_latest_date_key)[:10])
    except (TypeError, ValueError):
        return {}

    start_date = latest_date - timedelta(days=max(days - 1, 0))
    end_date = latest_date + timedelta(days=1)
    try:
        result = (
            client.table("card_variant_price_observations")
            .select("card_variant_id,captured_at,market_price")
            .in_("card_variant_id", variant_ids)
            .eq("condition_id", TOP_CHASE_NEAR_MINT_CONDITION_ID)
            .gt("market_price", 0)
            .gte("captured_at", start_date.isoformat())
            .lt("captured_at", end_date.isoformat())
            .order("captured_at", desc=False)
            .execute()
        )
    except Exception:
        logger.warning("top chase observation history load failed set_id=%s", set_id, exc_info=True)
        return {}

    points_by_variant_date: Dict[str, Dict[str, Dict[str, Any]]] = {}
    captured_at_by_variant_date: Dict[str, Dict[str, str]] = {}
    for row in result.data or []:
        variant_id = first_non_empty(row.get("card_variant_id"))
        captured_at = first_non_empty(row.get("captured_at"), row.get("capturedAt"))
        date_key = parse_date_key(captured_at)
        price = to_optional_float(row.get("market_price") if "market_price" in row else row.get("marketPrice"))
        if not variant_id or not date_key or price is None or price <= 0:
            continue
        existing_captured_at = captured_at_by_variant_date.setdefault(variant_id, {}).get(date_key)
        if existing_captured_at and captured_at and captured_at <= existing_captured_at:
            continue
        captured_at_by_variant_date[variant_id][date_key] = captured_at or date_key
        points_by_variant_date.setdefault(variant_id, {})[date_key] = {
            "date": date_key,
            "marketPrice": round(price, 2),
            "market_price": round(price, 2),
            "sourceDate": date_key,
            "source_date": date_key,
            "isObserved": True,
            "is_observed": True,
        }

    return {
        variant_id: [points[date_key] for date_key in sorted(points.keys())]
        for variant_id, points in points_by_variant_date.items()
        if points
    }


def _history_by_card(cards: List[Dict[str, Any]]) -> Dict[str, List[Dict[str, Any]]]:
    history_by_card: Dict[str, List[Dict[str, Any]]] = {}
    for card in cards:
        key = first_non_empty(card.get("cardVariantId"), card.get("card_variant_id"), card.get("cardId"), card.get("card_id"))
        if not key:
            continue
        history = card.get("priceHistory") if isinstance(card.get("priceHistory"), list) else card.get("price_history")
        compact_history: List[Dict[str, Any]] = []
        for point in list(history or []):
            date_key = first_non_empty(point.get("date"), point.get("capturedAt"), point.get("captured_at"))
            if not date_key:
                continue
            compact_point = {
                "date": str(date_key)[:10],
                "marketPrice": point.get("marketPrice", point.get("market_price", point.get("price"))),
                "market_price": point.get("market_price", point.get("marketPrice", point.get("price"))),
            }
            source_date = first_non_empty(point.get("sourceDate"), point.get("source_date"))
            if source_date:
                compact_point["sourceDate"] = str(source_date)[:10]
                compact_point["source_date"] = str(source_date)[:10]
            compact_history.append(compact_point)
        if compact_history:
            history_by_card[str(key)] = compact_history
    return history_by_card


def _compact_top_chase_cards(cards: List[Dict[str, Any]], history_by_card: Dict[str, List[Dict[str, Any]]]) -> List[Dict[str, Any]]:
    compact_cards: List[Dict[str, Any]] = []
    for card in cards:
        compact_card = {key: value for key, value in card.items() if key not in TOP_CHASE_HISTORY_FIELDS}
        history_key = first_non_empty(card.get("cardVariantId"), card.get("card_variant_id"), card.get("cardId"), card.get("card_id"))
        compact_history = history_by_card.get(str(history_key)) if history_key else None
        if compact_history:
            compact_card["priceHistory"] = compact_history
            compact_card["price_history"] = compact_history
        compact_cards.append(compact_card)
    return compact_cards


def build_market_dashboard_snapshot_rows(
    set_row: Dict[str, Any],
    *,
    days: int = DEFAULT_DASHBOARD_DAYS,
    window: str = DEFAULT_DASHBOARD_WINDOW,
    client: Any = None,
) -> tuple[Dict[str, Any], List[Dict[str, Any]]]:
    built_at = utc_now_iso()
    set_id = str(set_row["id"])
    histories_by_scope: Dict[str, List[Dict[str, Any]]] = {}
    available_scope_lookup: Dict[str, Dict[str, Any]] = {}
    standard_meta: Dict[str, Any] = {}

    for scope in SET_VALUE_SCOPES:
        payload = get_pokemon_set_value_history_payload(set_id=set_id, days=days, value_scope=scope)
        history = list(payload.get("history") or [])
        histories_by_scope[scope] = history
        if scope == "standard":
            standard_meta = payload.get("meta") or {}
        for entry in (payload.get("meta") or {}).get("availableScopes") or (payload.get("meta") or {}).get("available_scopes") or []:
            key = first_non_empty(entry.get("key"))
            if key:
                available_scope_lookup[key] = entry

    top_payload = get_pokemon_set_top_market_cards_payload(
        set_id=set_id,
        limit=10,
        days=TOP_CHASE_HISTORY_SOURCE_WINDOW_DAYS,
    )
    top_cards = list(top_payload.get("cards") or [])
    top_chase_card_histories = _history_by_card(top_cards)
    variant_ids = _top_chase_variant_ids(top_cards)
    if not _top_chase_histories_cover_source_window(
        top_chase_card_histories,
        variant_ids=variant_ids,
        source_window_days=TOP_CHASE_HISTORY_SOURCE_WINDOW_DAYS,
    ):
        if variant_ids:
            loaded_histories = _load_top_chase_histories_from_observations(
                client or get_client(),
                set_id=set_id,
                variant_ids=variant_ids,
                latest_date_key=_latest_history_date(histories_by_scope),
                days=TOP_CHASE_HISTORY_SOURCE_WINDOW_DAYS,
            )
            if loaded_histories:
                top_chase_card_histories = {**top_chase_card_histories, **loaded_histories}
    compact_top_cards = _compact_top_chase_cards(top_cards, top_chase_card_histories)
    top_chase_history_counts = _top_chase_history_counts(top_chase_card_histories)
    top_chase_observed_dates = [
        str(point.get("date"))[:10]
        for history in top_chase_card_histories.values()
        if isinstance(history, list)
        for point in history
        if parse_date_key(point.get("date"))
    ]
    movement_payload = build_pokemon_set_card_movement_payload(set_id=set_id)
    market_movers = movement_payload.get("marketMovers") or {}
    market_movers_snake = movement_payload.get("market_movers") or {}
    latest_market_date = _latest_history_date(histories_by_scope)
    dashboard_payload = {
        "set": top_payload.get("set")
        or {
            "id": set_row.get("id"),
            "name": set_row.get("name"),
            "slug": set_row.get("canonical_key"),
            "pokemon_api_set_id": set_row.get("pokemon_api_set_id"),
        },
        "window": window,
        "window_key": window,
        "days": days,
        "setValueHistoriesByScope": histories_by_scope,
        "set_value_histories_by_scope": histories_by_scope,
        "performanceVsCostHistory": histories_by_scope.get("standard", []),
        "performance_vs_cost_history": histories_by_scope.get("standard", []),
        "topChaseCards": compact_top_cards,
        "top_chase_cards": compact_top_cards,
        "topChaseCardHistories": top_chase_card_histories,
        "top_chase_card_histories": top_chase_card_histories,
        "marketMovers": market_movers,
        "market_movers": market_movers_snake,
        "availableScopes": list(available_scope_lookup.values()),
        "available_scopes": list(available_scope_lookup.values()),
        "latestMarketDate": latest_market_date,
        "latest_market_date": latest_market_date,
        "meta": {
            "window": window,
            "window_key": window,
            "days": days,
            "asOfDate": latest_market_date,
            "sources": {
                "set_value_histories": "pokemon_set_value_daily_history",
                "top_chase_cards": "pokemon_set_top_chase_card_daily_history/simulation_input_cards",
                "market_movers": "card_variant_price_observations/card_market_usd_latest_by_condition",
            },
            "warnings": list(standard_meta.get("warnings") or []) + list((top_payload.get("meta") or {}).get("warnings") or []),
            "topChaseHistorySource": TOP_CHASE_HISTORY_SOURCE,
            "topChaseHistorySourceWindowDays": TOP_CHASE_HISTORY_SOURCE_WINDOW_DAYS,
            "topChaseHistoryMinPoints": min(top_chase_history_counts) if top_chase_history_counts else 0,
            "topChaseHistoryMaxPoints": max(top_chase_history_counts) if top_chase_history_counts else 0,
            "topChaseHistoryFirstObservedDate": min(top_chase_observed_dates) if top_chase_observed_dates else None,
            "topChaseHistoryLatestObservedDate": max(top_chase_observed_dates) if top_chase_observed_dates else None,
            "topChaseHistoryHydratedFromDailyTable": False,
            "snapshot": {
                "type": "pokemon_set_market_dashboard",
                "builtAt": built_at,
                "source": "pokemon_snapshot_builders",
            },
        },
    }

    history_rows: List[Dict[str, Any]] = []
    for rank, card in enumerate(top_cards, start=1):
        history_key = first_non_empty(
            card.get("cardVariantId"),
            card.get("card_variant_id"),
            card.get("cardId"),
            card.get("card_id"),
        )
        card_history = top_chase_card_histories.get(str(history_key)) if history_key else None
        if not card_history:
            card_history = card.get("priceHistory") if isinstance(card.get("priceHistory"), list) else card.get("price_history")
        latest_point_date = first_non_empty(card.get("priceUpdatedAt"), card.get("price_updated_at"))
        points = list(card_history or [])
        if not points and latest_point_date:
            points = [
                {
                    "date": latest_point_date[:10],
                    "marketPrice": card.get("marketPrice") or card.get("estimatedMarketPrice"),
                    "source": card.get("source") or card.get("provider"),
                    "sourceDate": latest_point_date[:10],
                }
            ]
        for point in points:
            snapshot_date = first_non_empty(point.get("date"), point.get("capturedAt"), point.get("captured_at"))
            if not snapshot_date:
                continue
            history_rows.append(
                {
                    "set_id": set_id,
                    "snapshot_date": snapshot_date[:10],
                    "card_id": first_non_empty(card.get("cardId"), card.get("card_id"), card.get("id")),
                    "card_variant_id": first_non_empty(card.get("cardVariantId"), card.get("card_variant_id")),
                    "rank": rank,
                    "name": first_non_empty(card.get("name")),
                    "rarity": first_non_empty(card.get("rarity")),
                    "image_url": first_non_empty(card.get("imageUrl"), card.get("image_url")),
                    "image_small_url": first_non_empty(card.get("imageSmallUrl"), card.get("image_small_url")),
                    "image_large_url": first_non_empty(card.get("imageLargeUrl"), card.get("image_large_url")),
                    "market_price": point.get("marketPrice") or point.get("market_price") or card.get("marketPrice"),
                    "source": first_non_empty(point.get("source"), point.get("provider"), card.get("source"), card.get("provider")),
                    "source_date": (first_non_empty(point.get("sourceDate"), point.get("source_date"), snapshot_date) or "")[:10],
                }
            )

    return (
        {
            "set_id": set_id,
            "window_key": window,
            "payload_json": dashboard_payload,
            "set_value_histories_json": histories_by_scope,
            "performance_vs_cost_history_json": histories_by_scope.get("standard", []),
            "top_chase_cards_json": compact_top_cards,
            "top_chase_card_histories_json": top_chase_card_histories,
            "available_scopes_json": list(available_scope_lookup.values()),
            "latest_market_date": latest_market_date,
        },
        history_rows,
    )


def build_cards_snapshot_row(set_row: Dict[str, Any]) -> Dict[str, Any]:
    set_id = str(set_row["id"])
    payload = get_pokemon_set_cards_payload(set_id)
    movement_payload = build_pokemon_set_card_movement_payload(set_id=set_id)
    payload = enrich_cards_payload_with_movements(payload, movement_payload)
    payload = enrich_cards_payload_with_desirability(payload)
    cards = list(payload.get("cards") or [])
    payload = with_snapshot_meta(payload, snapshot_type="pokemon_set_cards", built_at=utc_now_iso())
    return {
        "set_id": set_id,
        "cards_json": cards,
        "payload_json": payload,
        "card_count": len(cards),
    }


def build_explore_rankings_snapshot_row(*, limit: int = DEFAULT_RANKINGS_LIMIT) -> Dict[str, Any]:
    built_at = utc_now_iso()
    payload = get_rip_statistics_targets_payload(limit=limit)
    targets = list(payload.get("targets") or [])
    opening_targets = [target for target in targets if is_opening_set_row(target)]
    meta = dict(payload.get("meta") or {})
    opening_set_audit = build_opening_set_audit(targets)
    meta["snapshot"] = {
        "type": "pokemon_explore_rankings",
        "builtAt": built_at,
        "source": "pokemon_snapshot_builders",
    }
    meta["openingSetAudit"] = opening_set_audit
    meta["opening_set_audit"] = opening_set_audit
    payload = {**payload, "targets": opening_targets, "meta": meta}
    return {
        "tcg": "pokemon",
        "scope": "rip-statistics",
        "ranking_payload_json": payload,
        "default_target_json": payload.get("default_target") or {},
    }


def upsert_row(client: Any, table: str, row: Dict[str, Any], *, on_conflict: str, commit: bool) -> None:
    if not commit:
        logger.info("[dry-run] would upsert %s conflict=%s keys=%s", table, on_conflict, sorted(row.keys()))
        return
    client.table(table).upsert(row, on_conflict=on_conflict).execute()
    logger.info("upserted %s conflict=%s", table, on_conflict)


def upsert_rows(
    client: Any,
    table: str,
    rows: List[Dict[str, Any]],
    *,
    on_conflict: str,
    commit: bool,
    batch_size: int = DEFAULT_UPSERT_BATCH_SIZE,
) -> None:
    if not rows:
        logger.info("no rows for %s", table)
        return
    if not commit:
        logger.info("[dry-run] would upsert %s rows into %s conflict=%s", len(rows), table, on_conflict)
        return
    safe_batch_size = max(1, int(batch_size or DEFAULT_UPSERT_BATCH_SIZE))
    for start in range(0, len(rows), safe_batch_size):
        batch = rows[start : start + safe_batch_size]
        client.table(table).upsert(batch, on_conflict=on_conflict).execute()
        logger.info(
            "upserted %s/%s rows into %s conflict=%s",
            min(start + len(batch), len(rows)),
            len(rows),
            table,
            on_conflict,
        )
    logger.info("upserted %s rows into %s", len(rows), table)


def get_client() -> Any:
    load_backend_env()
    return create_service_role_client()
