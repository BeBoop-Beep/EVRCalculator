"""Collection dashboard and item DTO assembly for API endpoints."""

from __future__ import annotations

from copy import deepcopy
from datetime import datetime
import json
import logging
from time import perf_counter
from typing import Any, Dict, Iterable, List, Optional, Tuple

from backend.db.clients.supabase_client import create_service_role_client, supabase
from backend.db.services.collection_summary_service import get_user_collection_summary_snapshot
from backend.db.services.public_identity_service import normalize_public_username, resolve_public_user_by_username


DEFAULT_COLLECTION_IMAGE_PATH = "/images/default_image.png"

logger = logging.getLogger(__name__)

DEFAULT_DASHBOARD_DATA: Dict[str, Any] = {
    "commandCenter": {
        "totalValue": 18245.87,
        "change24hPercent": 0.91,
        "change7dPercent": 4.38,
        "cardsCount": 428,
        "sealedCount": 37,
        "wishlistCount": 64,
        "lastSyncedAt": "2026-03-31T14:08:00.000Z",
        "freshnessLabel": "Fresh",
    },
    "performance": {
        "periodLabel": "Last 7 days",
        "points": [
            {"dateLabel": "Mar 24", "totalValue": 17120},
            {"dateLabel": "Mar 25", "totalValue": 17385},
            {"dateLabel": "Mar 26", "totalValue": 17640},
            {"dateLabel": "Mar 27", "totalValue": 17530},
            {"dateLabel": "Mar 28", "totalValue": 17825},
            {"dateLabel": "Mar 29", "totalValue": 18080},
            {"dateLabel": "Mar 30", "totalValue": 18170},
            {"dateLabel": "Mar 31", "totalValue": 18245},
        ],
        "rangeSeries": {
            "LT": {
                "points": [
                    {"dateLabel": "2022", "totalValue": 9420},
                    {"dateLabel": "2023", "totalValue": 11680},
                    {"dateLabel": "2024", "totalValue": 13970},
                    {"dateLabel": "2025", "totalValue": 16480},
                    {"dateLabel": "Now", "totalValue": 18245},
                ],
                "helper": "Performance since portfolio inception",
            },
        },
    },
    "insights": {
        "topMovers": [
            {"id": "m1", "name": "Charizard ex SIR", "changePercent7d": 8.7, "dollarImpact": 51},
            {"id": "m2", "name": "Mew ex Gold", "changePercent7d": 6.1, "dollarImpact": 13},
            {"id": "m3", "name": "Gengar VMAX Alt", "changePercent7d": -2.4, "dollarImpact": -8},
        ],
        "allocationSummary": [
            {"id": "a1", "label": "Cards", "valuePercent": 68, "valueLabel": "$12.4k"},
            {"id": "a2", "label": "Sealed", "valuePercent": 24, "valueLabel": "$4.4k"},
            {"id": "a3", "label": "Merchandise", "valuePercent": 8, "valueLabel": "$1.4k"},
        ],
        "concentrationText": "Top 5 assets represent 46% of total portfolio value.",
    },
}


def _to_number(value: Any, fallback: float = 0.0) -> float:
    try:
        parsed = float(value)
    except (TypeError, ValueError):
        return fallback
    return parsed if parsed == parsed and parsed not in (float("inf"), float("-inf")) else fallback


def _to_trimmed_string(value: Any) -> str:
    if not isinstance(value, str):
        return ""
    return value.strip()


def _to_optional_string(value: Any) -> Optional[str]:
    normalized = _to_trimmed_string(value)
    return normalized or None


def _default_public_collection_summary() -> Dict[str, Any]:
    return {
        "portfolio_value": 0.0,
        "cards_count": 0,
        "sealed_count": 0,
        "graded_count": 0,
        "portfolio_delta_1d": 0.0,
        "portfolio_delta_7d": 0.0,
        "portfolio_delta_3m": 0.0,
        "portfolio_delta_6m": 0.0,
        "portfolio_delta_1y": 0.0,
        "portfolio_delta_lifetime": 0.0,
        "portfolio_delta_pct_1d": None,
        "portfolio_delta_pct_7d": None,
        "portfolio_delta_pct_3m": None,
        "portfolio_delta_pct_6m": None,
        "portfolio_delta_pct_1y": None,
        "portfolio_delta_pct_lifetime": None,
    }


def _public_summary_response_from_snapshot(summary_snapshot: Optional[Dict[str, Any]]) -> Dict[str, Any]:
    summary = _default_public_collection_summary()
    if not isinstance(summary_snapshot, dict):
        return summary

    summary["portfolio_value"] = _to_number(summary_snapshot.get("portfolio_value"), 0.0)
    summary["cards_count"] = max(0, int(_to_number(summary_snapshot.get("cards_count"), 0.0)))
    summary["sealed_count"] = max(0, int(_to_number(summary_snapshot.get("sealed_count"), 0.0)))
    summary["graded_count"] = max(0, int(_to_number(summary_snapshot.get("graded_count"), 0.0)))
    summary["portfolio_delta_1d"] = _to_number(summary_snapshot.get("portfolio_delta_1d"), 0.0)
    summary["portfolio_delta_7d"] = _to_number(summary_snapshot.get("portfolio_delta_7d"), 0.0)
    summary["portfolio_delta_3m"] = _to_number(summary_snapshot.get("portfolio_delta_3m"), 0.0)
    summary["portfolio_delta_6m"] = _to_number(summary_snapshot.get("portfolio_delta_6m"), 0.0)
    summary["portfolio_delta_1y"] = _to_number(summary_snapshot.get("portfolio_delta_1y"), 0.0)
    summary["portfolio_delta_lifetime"] = _to_number(summary_snapshot.get("portfolio_delta_lifetime"), 0.0)

    for field_name in (
        "portfolio_delta_pct_1d",
        "portfolio_delta_pct_7d",
        "portfolio_delta_pct_3m",
        "portfolio_delta_pct_6m",
        "portfolio_delta_pct_1y",
        "portfolio_delta_pct_lifetime",
    ):
        raw_value = summary_snapshot.get(field_name)
        summary[field_name] = _to_number(raw_value, 0.0) if raw_value is not None else None

    return summary


def _unique_values(values: Iterable[Any]) -> List[Any]:
    seen = set()
    unique: List[Any] = []
    for value in values:
        if value is None or value == "":
            continue
        token = str(value)
        if token in seen:
            continue
        seen.add(token)
        unique.append(value)
    return unique


def _resolve_card_like_images(
    variant_small: Any,
    variant_large: Any,
    card_small: Any,
    card_large: Any,
) -> Dict[str, str]:
    resolved_small = _to_trimmed_string(variant_small) or _to_trimmed_string(card_small) or DEFAULT_COLLECTION_IMAGE_PATH
    resolved_large = _to_trimmed_string(variant_large) or _to_trimmed_string(card_large) or DEFAULT_COLLECTION_IMAGE_PATH
    return {
        "image_url": resolved_small,
        "image_large_url": resolved_large,
    }


def _extract_market_price(row: Dict[str, Any]) -> float:
    for field_name in ("market_price", "current_market_price", "price"):
        if field_name not in row:
            continue
        parsed = _to_number(row.get(field_name), 0.0)
        if parsed >= 0:
            return parsed
    return 0.0


def _format_compact_currency(value: float) -> str:
    abs_value = abs(value)
    if abs_value >= 1000:
        return f"${value / 1000:.1f}k"
    return f"${value:.0f}"


def _format_date_label(value: Any, include_year: bool) -> Optional[str]:
    if value is None:
        return None

    parsed: Optional[datetime] = None
    if isinstance(value, datetime):
        parsed = value
    elif isinstance(value, str):
        raw = value.strip()
        if not raw:
            return None
        try:
            parsed = datetime.fromisoformat(raw.replace("Z", "+00:00"))
        except ValueError:
            try:
                parsed = datetime.strptime(raw[:10], "%Y-%m-%d")
            except ValueError:
                return None

    if parsed is None:
        return None

    if include_year:
        return parsed.strftime("%b %d, %y")
    return parsed.strftime("%b %d")


def _build_row_map(rows: Iterable[Dict[str, Any]], key_name: str) -> Dict[str, Dict[str, Any]]:
    mapped: Dict[str, Dict[str, Any]] = {}
    for row in rows:
        key = row.get(key_name)
        if key is None:
            continue
        mapped[str(key)] = row
    return mapped


def _build_price_lookup(rows: Iterable[Dict[str, Any]], id_key: str, condition_key: Optional[str] = None) -> Dict[str, float]:
    lookup: Dict[str, float] = {}
    for row in rows:
        row_id = row.get(id_key)
        if row_id is None:
            continue

        value = _extract_market_price(row)
        if condition_key is None:
            lookup[str(row_id)] = value
            continue

        condition_value = row.get(condition_key)
        condition_token = "null" if condition_value is None else str(condition_value)
        lookup[f"{row_id}:{condition_token}"] = value
    return lookup


def _get_card_market_price(price_map: Dict[str, float], variant_id: Any, condition_id: Any) -> float:
    if variant_id is None:
        return 0.0

    condition_token = "null" if condition_id is None else str(condition_id)
    with_condition_key = f"{variant_id}:{condition_token}"
    if with_condition_key in price_map:
        return _to_number(price_map.get(with_condition_key), 0.0)

    null_condition_key = f"{variant_id}:null"
    return _to_number(price_map.get(null_condition_key), 0.0)


def _select_with_fallback(
    table: str,
    select_candidates: List[str],
    filters: Optional[List[Tuple[str, str, Any]]] = None,
    order_by: Optional[Tuple[str, bool]] = None,
    limit: Optional[int] = None,
    offset: Optional[int] = None,
    correlation_id: Optional[str] = None,
    trace_label: Optional[str] = None,
    db_client: Any = None,
) -> List[Dict[str, Any]]:
    filters = filters or []
    client = db_client or supabase

    for select_clause in select_candidates:
        started_at = perf_counter()
        try:
            query = client.table(table).select(select_clause)
            for operator, column, value in filters:
                if operator == "eq":
                    query = query.eq(column, value)
                elif operator == "in" and isinstance(value, list) and value:
                    query = query.in_(column, value)

            if order_by:
                query = query.order(order_by[0], desc=not order_by[1])

            if isinstance(limit, int):
                if isinstance(offset, int) and offset >= 0:
                    query = query.range(offset, max(offset, offset + max(limit - 1, 0)))
                else:
                    query = query.limit(limit)

            response = query.execute()
            rows = response.data or []
            logger.info(
                "public_collection.query correlation_id=%s trace_label=%s table=%s select=%s rows=%s elapsed_ms=%.2f",
                correlation_id,
                trace_label,
                table,
                select_clause,
                len(rows),
                (perf_counter() - started_at) * 1000,
            )
            return rows
        except Exception as exc:
            logger.warning(
                "public_collection.query correlation_id=%s trace_label=%s table=%s select=%s error=%s elapsed_ms=%.2f",
                correlation_id,
                trace_label,
                table,
                select_clause,
                type(exc).__name__,
                (perf_counter() - started_at) * 1000,
            )
            continue

    logger.warning(
        "public_collection.query correlation_id=%s trace_label=%s table=%s rows=0 reason=ALL_SELECTS_FAILED",
        correlation_id,
        trace_label,
        table,
    )
    return []


def _payload_size_bytes(payload: Dict[str, Any]) -> int:
    try:
        return len(json.dumps(payload, separators=(",", ":"), default=str).encode("utf-8"))
    except Exception:
        return 0


def _summarize_collection_items(items: Iterable[Dict[str, Any]]) -> Dict[str, Any]:
    item_meta = [
        {
            "id": str(item.get("id") or ""),
            "type": str(item.get("collectible_type") or ""),
            "collectible_id": str(item.get("collectible_id") or ""),
        }
        for item in items
    ]
    by_type: Dict[str, int] = {}
    for row in item_meta:
        type_key = row.get("type") or "unknown"
        by_type[type_key] = by_type.get(type_key, 0) + 1
    return {
        "count": len(item_meta),
        "by_type": by_type,
        "item_meta": item_meta,
    }


def _load_dashboard_snapshot_rows(user_id: str) -> List[Dict[str, Any]]:
    return _select_with_fallback(
        table="portfolio_daily_snapshots",
        select_candidates=[
            "snapshot_date,total_value,change_24h_percent,change_7d_percent,cards_count,sealed_count,wishlist_count,last_synced_at,freshness_label"
        ],
        filters=[("eq", "user_id", user_id)],
        order_by=("snapshot_date", True),
    )


def get_collection_summary_and_items_for_user_id(
    user_id: str,
    include_collection_items: bool = False,
    include_private_fields: bool = False,
    limit: Optional[int] = None,
    offset: int = 0,
    correlation_id: Optional[str] = None,
    requested_username: Optional[str] = None,
    db_client: Any = None,
) -> Dict[str, Any]:
    total_started_at = perf_counter()
    client = db_client or create_service_role_client()
    card_holdings_select_candidates = (
        [
            "id,user_id,card_variant_id,condition_id,quantity,purchase_price,cost_basis,roi,unrealized_gain,acquisition_date,fees_taxes,notes",
            "id,user_id,card_variant_id,condition_id,quantity",
            "id,card_variant_id,condition_id,quantity",
        ]
        if include_private_fields
        else ["id,card_variant_id,condition_id,quantity"]
    )

    sealed_holdings_select_candidates = (
        [
            "id,user_id,sealed_product_id,quantity,purchase_price,cost_basis,roi,unrealized_gain,acquisition_date,fees_taxes,notes",
            "id,user_id,sealed_product_id,quantity",
            "id,sealed_product_id,quantity",
        ]
        if include_private_fields
        else ["id,sealed_product_id,quantity"]
    )

    graded_holdings_select_candidates = (
        [
            "id,user_id,graded_card_variant_id,quantity,purchase_price,cost_basis,roi,unrealized_gain,acquisition_date,fees_taxes,notes",
            "id,user_id,graded_card_variant_id,quantity",
            "id,graded_card_variant_id,quantity",
        ]
        if include_private_fields
        else ["id,graded_card_variant_id,quantity"]
    )

    cards_query_started_at = perf_counter()
    card_holdings = _select_with_fallback(
        table="user_card_holdings",
        select_candidates=card_holdings_select_candidates,
        filters=[("eq", "user_id", user_id)],
        correlation_id=correlation_id,
        trace_label="raw_card_holdings",
        limit=limit,
        offset=offset,
        db_client=client,
    )
    sealed_holdings = _select_with_fallback(
        table="user_sealed_product_holdings",
        select_candidates=sealed_holdings_select_candidates,
        filters=[("eq", "user_id", user_id)],
        correlation_id=correlation_id,
        trace_label="raw_sealed_holdings",
        limit=limit,
        offset=offset,
        db_client=client,
    )
    graded_holdings = _select_with_fallback(
        table="user_graded_card_holdings",
        select_candidates=graded_holdings_select_candidates,
        filters=[("eq", "user_id", user_id)],
        correlation_id=correlation_id,
        trace_label="raw_graded_holdings",
        limit=limit,
        offset=offset,
        db_client=client,
    )

    logger.info(
        "public_collection.aggregate correlation_id=%s stage=raw_holdings username=%s user_id=%s cards=%s sealed=%s graded=%s",
        correlation_id,
        requested_username,
        user_id,
        len(card_holdings),
        len(sealed_holdings),
        len(graded_holdings),
    )

    card_variant_ids = _unique_values(row.get("card_variant_id") for row in card_holdings)
    condition_ids = _unique_values(row.get("condition_id") for row in card_holdings)
    sealed_product_ids = _unique_values(row.get("sealed_product_id") for row in sealed_holdings)
    graded_variant_ids = _unique_values(row.get("graded_card_variant_id") for row in graded_holdings)

    card_market_rows = (
        _select_with_fallback(
            table="card_market_usd_latest",
            select_candidates=["variant_id,condition_id,market_price,current_market_price,price"],
            filters=[("in", "variant_id", card_variant_ids)],
            correlation_id=correlation_id,
            trace_label="card_market_rows",
            db_client=client,
        )
        if card_variant_ids
        else []
    )

    sealed_market_rows = (
        _select_with_fallback(
            table="sealed_product_market_usd_latest",
            select_candidates=["sealed_product_id,market_price,current_market_price,price"],
            filters=[("in", "sealed_product_id", sealed_product_ids)],
            correlation_id=correlation_id,
            trace_label="sealed_market_rows",
            db_client=client,
        )
        if sealed_product_ids
        else []
    )

    graded_market_rows = (
        _select_with_fallback(
            table="graded_card_market_latest",
            select_candidates=["graded_card_variant_id,market_price,current_market_price,price"],
            filters=[("in", "graded_card_variant_id", graded_variant_ids)],
            correlation_id=correlation_id,
            trace_label="graded_market_rows",
            db_client=client,
        )
        if graded_variant_ids
        else []
    )

    card_variant_rows = (
        _select_with_fallback(
            table="card_variants",
            select_candidates=[
                "id,card_id,printing_type,special_type,edition,image_small_url,image_large_url",
                "id,card_id,printing_type,special_type,edition",
            ],
            filters=[("in", "id", card_variant_ids)],
            correlation_id=correlation_id,
            trace_label="card_variant_rows",
            db_client=client,
        )
        if card_variant_ids
        else []
    )

    linked_card_ids = _unique_values(row.get("card_id") for row in card_variant_rows)
    card_rows = (
        _select_with_fallback(
            table="cards",
            select_candidates=[
                "id,name,rarity,card_number,set_id,image_small_url,image_large_url",
                "id,name,rarity,card_number,set_id",
            ],
            filters=[("in", "id", linked_card_ids)],
            correlation_id=correlation_id,
            trace_label="card_rows",
            db_client=client,
        )
        if linked_card_ids
        else []
    )
    cards_query_elapsed_ms = (perf_counter() - cards_query_started_at) * 1000

    graded_query_started_at = perf_counter()
    graded_variant_rows = (
        _select_with_fallback(
            table="graded_card_variants",
            select_candidates=[
                "id,card_variant_id,grade,grading_company",
                "id,card_variant_id,grade",
                "id,card_variant_id",
            ],
            filters=[("in", "id", graded_variant_ids)],
            correlation_id=correlation_id,
            trace_label="graded_variant_rows",
            db_client=client,
        )
        if graded_variant_ids
        else []
    )
    graded_query_elapsed_ms = (perf_counter() - graded_query_started_at) * 1000

    sealed_query_started_at = perf_counter()
    sealed_rows = (
        _select_with_fallback(
            table="sealed_products",
            select_candidates=[
                "id,name,product_type,set_id,image_small_url,image_large_url",
                "id,name,product_type,set_id",
            ],
            filters=[("in", "id", sealed_product_ids)],
            correlation_id=correlation_id,
            trace_label="sealed_rows",
            db_client=client,
        )
        if sealed_product_ids
        else []
    )
    sealed_query_elapsed_ms = (perf_counter() - sealed_query_started_at) * 1000

    set_ids = _unique_values([*(row.get("set_id") for row in card_rows), *(row.get("set_id") for row in sealed_rows)])
    set_rows = (
        _select_with_fallback(
            table="sets",
            select_candidates=["id,name"],
            filters=[("in", "id", set_ids)],
            correlation_id=correlation_id,
            trace_label="set_rows",
            db_client=client,
        )
        if set_ids
        else []
    )

    condition_rows = (
        _select_with_fallback(
            table="conditions",
            select_candidates=["id,name"],
            filters=[("in", "id", condition_ids)],
            correlation_id=correlation_id,
            trace_label="condition_rows",
            db_client=client,
        )
        if condition_ids
        else []
    )

    card_variant_map = _build_row_map(card_variant_rows, "id")
    card_map = _build_row_map(card_rows, "id")
    sealed_map = _build_row_map(sealed_rows, "id")
    graded_variant_map = _build_row_map(graded_variant_rows, "id")
    set_map = _build_row_map(set_rows, "id")
    condition_map = _build_row_map(condition_rows, "id")

    card_price_map = _build_price_lookup(card_market_rows, "variant_id", "condition_id")
    sealed_price_map = _build_price_lookup(sealed_market_rows, "sealed_product_id")
    graded_price_map = _build_price_lookup(graded_market_rows, "graded_card_variant_id")

    card_items: List[Dict[str, Any]] = []
    for holding in card_holdings:
        quantity = max(0.0, _to_number(holding.get("quantity"), 0.0))
        variant = card_variant_map.get(str(holding.get("card_variant_id")))
        card = card_map.get(str(variant.get("card_id"))) if variant else None
        set_row = set_map.get(str(card.get("set_id"))) if card and card.get("set_id") is not None else None
        condition = condition_map.get(str(holding.get("condition_id")))
        market_price = _get_card_market_price(card_price_map, holding.get("card_variant_id"), holding.get("condition_id"))
        estimated_value = quantity * market_price

        images = _resolve_card_like_images(
            variant_small=variant.get("image_small_url") if variant else None,
            variant_large=variant.get("image_large_url") if variant else None,
            card_small=card.get("image_small_url") if card else None,
            card_large=card.get("image_large_url") if card else None,
        )

        base_item: Dict[str, Any] = {
            "id": str(holding.get("id") or ""),
            "collectible_type": "card",
            "collectible_id": holding.get("card_variant_id"),
            "quantity": int(quantity),
            "name": _to_optional_string(card.get("name") if card else None) or "Unknown Card",
            "set_name": _to_optional_string(set_row.get("name") if set_row else None),
            "card_number": _to_optional_string(card.get("card_number") if card else None),
            "rarity": _to_optional_string(card.get("rarity") if card else None),
            "condition": _to_optional_string(condition.get("name") if condition else None),
            "printing_type": _to_optional_string(variant.get("printing_type") if variant else None),
            "edition": _to_optional_string(variant.get("edition") if variant else None),
            "special_type": _to_optional_string(variant.get("special_type") if variant else None),
            "estimated_value": estimated_value,
            "image_url": images["image_url"],
            "image_large_url": images["image_large_url"],
        }

        if include_private_fields:
            base_item.update(
                {
                    "user_id": holding.get("user_id"),
                    "purchase_price": _to_number(holding.get("purchase_price"), 0.0),
                    "cost_basis": _to_number(holding.get("cost_basis"), 0.0),
                    "roi": _to_number(holding.get("roi"), 0.0),
                    "unrealized_gain": _to_number(holding.get("unrealized_gain"), 0.0),
                    "acquisition_date": holding.get("acquisition_date"),
                    "fees_taxes": _to_number(holding.get("fees_taxes"), 0.0),
                    "notes": _to_optional_string(holding.get("notes")),
                }
            )

        card_items.append(base_item)

    sealed_items: List[Dict[str, Any]] = []
    for holding in sealed_holdings:
        quantity = max(0.0, _to_number(holding.get("quantity"), 0.0))
        sealed = sealed_map.get(str(holding.get("sealed_product_id")))
        set_row = set_map.get(str(sealed.get("set_id"))) if sealed and sealed.get("set_id") is not None else None
        market_price = _to_number(sealed_price_map.get(str(holding.get("sealed_product_id"))), 0.0)
        estimated_value = quantity * market_price
        images = _resolve_card_like_images(
            variant_small=sealed.get("image_small_url") if sealed else None,
            variant_large=sealed.get("image_large_url") if sealed else None,
            card_small=None,
            card_large=None,
        )

        base_item = {
            "id": str(holding.get("id") or ""),
            "collectible_type": "sealed_product",
            "collectible_id": holding.get("sealed_product_id"),
            "quantity": int(quantity),
            "name": _to_optional_string(sealed.get("name") if sealed else None) or "Sealed Product",
            "set_name": _to_optional_string(set_row.get("name") if set_row else None),
            "card_number": None,
            "rarity": None,
            "condition": "Sealed",
            "printing_type": None,
            "edition": None,
            "special_type": _to_optional_string(sealed.get("product_type") if sealed else None),
            "estimated_value": estimated_value,
            "image_url": images["image_url"],
            "image_large_url": images["image_large_url"],
        }

        if include_private_fields:
            base_item.update(
                {
                    "user_id": holding.get("user_id"),
                    "purchase_price": _to_number(holding.get("purchase_price"), 0.0),
                    "cost_basis": _to_number(holding.get("cost_basis"), 0.0),
                    "roi": _to_number(holding.get("roi"), 0.0),
                    "unrealized_gain": _to_number(holding.get("unrealized_gain"), 0.0),
                    "acquisition_date": holding.get("acquisition_date"),
                    "fees_taxes": _to_number(holding.get("fees_taxes"), 0.0),
                    "notes": _to_optional_string(holding.get("notes")),
                }
            )

        sealed_items.append(base_item)

    graded_items: List[Dict[str, Any]] = []
    for holding in graded_holdings:
        quantity = max(0.0, _to_number(holding.get("quantity"), 0.0))
        graded_variant = graded_variant_map.get(str(holding.get("graded_card_variant_id")))
        variant = card_variant_map.get(str(graded_variant.get("card_variant_id"))) if graded_variant else None
        card = card_map.get(str(variant.get("card_id"))) if variant else None
        set_row = set_map.get(str(card.get("set_id"))) if card and card.get("set_id") is not None else None
        market_price = _to_number(graded_price_map.get(str(holding.get("graded_card_variant_id"))), 0.0)
        estimated_value = quantity * market_price
        images = _resolve_card_like_images(
            variant_small=variant.get("image_small_url") if variant else None,
            variant_large=variant.get("image_large_url") if variant else None,
            card_small=card.get("image_small_url") if card else None,
            card_large=card.get("image_large_url") if card else None,
        )

        grade_value = graded_variant.get("grade") if graded_variant else None
        grade_label = f"Grade {grade_value}" if grade_value not in (None, "") else None

        base_item = {
            "id": str(holding.get("id") or ""),
            "collectible_type": "graded_card",
            "collectible_id": holding.get("graded_card_variant_id"),
            "quantity": int(quantity),
            "name": _to_optional_string(card.get("name") if card else None) or "Graded Card",
            "set_name": _to_optional_string(set_row.get("name") if set_row else None),
            "card_number": _to_optional_string(card.get("card_number") if card else None),
            "rarity": _to_optional_string(card.get("rarity") if card else None),
            "condition": grade_label,
            "printing_type": _to_optional_string(variant.get("printing_type") if variant else None),
            "edition": _to_optional_string(variant.get("edition") if variant else None),
            "special_type": _to_optional_string(variant.get("special_type") if variant else None),
            "estimated_value": estimated_value,
            "image_url": images["image_url"],
            "image_large_url": images["image_large_url"],
        }

        if include_private_fields:
            base_item.update(
                {
                    "user_id": holding.get("user_id"),
                    "purchase_price": _to_number(holding.get("purchase_price"), 0.0),
                    "cost_basis": _to_number(holding.get("cost_basis"), 0.0),
                    "roi": _to_number(holding.get("roi"), 0.0),
                    "unrealized_gain": _to_number(holding.get("unrealized_gain"), 0.0),
                    "acquisition_date": holding.get("acquisition_date"),
                    "fees_taxes": _to_number(holding.get("fees_taxes"), 0.0),
                    "notes": _to_optional_string(holding.get("notes")),
                }
            )

        graded_items.append(base_item)

    merge_started_at = perf_counter()
    collection_items = [*card_items, *sealed_items, *graded_items]
    merged_summary = _summarize_collection_items(collection_items)
    merge_elapsed_ms = (perf_counter() - merge_started_at) * 1000

    logger.info(
        "public_collection.aggregate correlation_id=%s stage=merged username=%s user_id=%s merged_total=%s by_type=%s",
        correlation_id,
        requested_username,
        user_id,
        merged_summary.get("count"),
        merged_summary.get("by_type"),
    )

    summary = {
        "portfolio_value": _to_number(sum(_to_number(item.get("estimated_value"), 0.0) for item in collection_items), 0.0),
        "cards_count": int(sum(max(0.0, _to_number(row.get("quantity"), 0.0)) for row in card_holdings)),
        "sealed_count": int(sum(max(0.0, _to_number(row.get("quantity"), 0.0)) for row in sealed_holdings)),
        "graded_count": int(sum(max(0.0, _to_number(row.get("quantity"), 0.0)) for row in graded_holdings)),
    }

    serializer_started_at = perf_counter()
    response_payload = {
        "summary": summary,
        "collection_items": collection_items if include_collection_items else [],
    }
    serializer_elapsed_ms = (perf_counter() - serializer_started_at) * 1000

    logger.info(
        "public_collection.timing correlation_id=%s username=%s user_id=%s include_items=%s path_used=%s limit=%s offset=%s cards_query_ms=%.2f sealed_query_ms=%.2f graded_query_ms=%.2f merge_ms=%.2f serializer_ms=%.2f total_ms=%.2f",
        correlation_id,
        requested_username,
        user_id,
        include_collection_items,
        "full_assembly" if include_collection_items else "summary_only",
        limit,
        offset,
        cards_query_elapsed_ms,
        sealed_query_elapsed_ms,
        graded_query_elapsed_ms,
        merge_elapsed_ms,
        serializer_elapsed_ms,
        (perf_counter() - total_started_at) * 1000,
    )

    if include_collection_items:
        final_summary = _summarize_collection_items(response_payload.get("collection_items") or [])
        logger.info(
            "public_collection.aggregate correlation_id=%s stage=final_response username=%s user_id=%s final_total=%s by_type=%s item_meta=%s",
            correlation_id,
            requested_username,
            user_id,
            final_summary.get("count"),
            final_summary.get("by_type"),
            final_summary.get("item_meta"),
        )

    return response_payload


def get_collection_items_for_user_id(
    user_id: str,
    include_private_fields: bool = True,
    limit: Optional[int] = None,
    offset: int = 0,
    correlation_id: Optional[str] = None,
) -> List[Dict[str, Any]]:
    payload = get_collection_summary_and_items_for_user_id(
        user_id=user_id,
        include_collection_items=True,
        include_private_fields=include_private_fields,
        limit=limit,
        offset=offset,
        correlation_id=correlation_id,
    )
    return payload.get("collection_items", [])


def get_collection_entry_detail_for_user_id(
    user_id: str,
    entry_id: str,
    include_private_fields: bool = True,
    correlation_id: Optional[str] = None,
) -> Optional[Dict[str, Any]]:
    started_at = perf_counter()
    normalized_entry_id = str(entry_id or "").strip()
    if not normalized_entry_id:
        return None

    client = create_service_role_client()

    card_rows = _select_with_fallback(
        table="user_card_holdings",
        select_candidates=[
            "id,user_id,card_variant_id,condition_id,quantity,purchase_price,cost_basis,roi,unrealized_gain,acquisition_date,fees_taxes,notes",
            "id,user_id,card_variant_id,condition_id,quantity",
        ],
        filters=[("eq", "id", normalized_entry_id), ("eq", "user_id", user_id)],
        limit=1,
        correlation_id=correlation_id,
        trace_label="entry_lookup_card",
        db_client=client,
    )

    if card_rows:
        holding = card_rows[0]
        variant_rows = _select_with_fallback(
            table="card_variants",
            select_candidates=["id,card_id,printing_type,special_type,edition,image_small_url,image_large_url", "id,card_id"],
            filters=[("eq", "id", holding.get("card_variant_id"))],
            limit=1,
            correlation_id=correlation_id,
            trace_label="entry_card_variant",
            db_client=client,
        )
        variant = variant_rows[0] if variant_rows else {}
        card_rows_join = _select_with_fallback(
            table="cards",
            select_candidates=["id,name,rarity,card_number,set_id,image_small_url,image_large_url", "id,name,set_id"],
            filters=[("eq", "id", variant.get("card_id"))],
            limit=1,
            correlation_id=correlation_id,
            trace_label="entry_card",
            db_client=client,
        )
        card = card_rows_join[0] if card_rows_join else {}
        set_rows = _select_with_fallback(
            table="sets",
            select_candidates=["id,name"],
            filters=[("eq", "id", card.get("set_id"))],
            limit=1,
            correlation_id=correlation_id,
            trace_label="entry_set",
            db_client=client,
        ) if card.get("set_id") else []
        condition_rows = _select_with_fallback(
            table="conditions",
            select_candidates=["id,name"],
            filters=[("eq", "id", holding.get("condition_id"))],
            limit=1,
            correlation_id=correlation_id,
            trace_label="entry_condition",
            db_client=client,
        ) if holding.get("condition_id") else []
        market_rows = _select_with_fallback(
            table="card_market_usd_latest",
            select_candidates=["variant_id,condition_id,market_price,current_market_price,price"],
            filters=[("eq", "variant_id", holding.get("card_variant_id"))],
            limit=10,
            correlation_id=correlation_id,
            trace_label="entry_card_market",
            db_client=client,
        )
        card_market_lookup = _build_price_lookup(market_rows, "variant_id", "condition_id")
        estimated_value = _get_card_market_price(card_market_lookup, holding.get("card_variant_id"), holding.get("condition_id")) * max(
            0.0, _to_number(holding.get("quantity"), 0.0)
        )
        images = _resolve_card_like_images(
            variant_small=variant.get("image_small_url"),
            variant_large=variant.get("image_large_url"),
            card_small=card.get("image_small_url"),
            card_large=card.get("image_large_url"),
        )
        entry: Dict[str, Any] = {
            "id": str(holding.get("id") or ""),
            "collectible_type": "card",
            "collectible_id": holding.get("card_variant_id"),
            "quantity": int(max(0.0, _to_number(holding.get("quantity"), 0.0))),
            "name": _to_optional_string(card.get("name")) or "Unknown Card",
            "set_name": _to_optional_string((set_rows[0] if set_rows else {}).get("name")),
            "card_number": _to_optional_string(card.get("card_number")),
            "rarity": _to_optional_string(card.get("rarity")),
            "condition": _to_optional_string((condition_rows[0] if condition_rows else {}).get("name")),
            "printing_type": _to_optional_string(variant.get("printing_type")),
            "edition": _to_optional_string(variant.get("edition")),
            "special_type": _to_optional_string(variant.get("special_type")),
            "estimated_value": estimated_value,
            "image_url": images["image_url"],
            "image_large_url": images["image_large_url"],
        }
        if include_private_fields:
            entry.update(
                {
                    "user_id": holding.get("user_id"),
                    "purchase_price": _to_number(holding.get("purchase_price"), 0.0),
                    "cost_basis": _to_number(holding.get("cost_basis"), 0.0),
                    "roi": _to_number(holding.get("roi"), 0.0),
                    "unrealized_gain": _to_number(holding.get("unrealized_gain"), 0.0),
                    "acquisition_date": holding.get("acquisition_date"),
                    "fees_taxes": _to_number(holding.get("fees_taxes"), 0.0),
                    "notes": _to_optional_string(holding.get("notes")),
                }
            )
        logger.info(
            "collection.entry_lookup correlation_id=%s user_id=%s entry_id=%s collectible_type=%s found=%s elapsed_ms=%.2f",
            correlation_id,
            user_id,
            normalized_entry_id,
            "card",
            bool(entry),
            (perf_counter() - started_at) * 1000,
        )
        return entry

    sealed_rows = _select_with_fallback(
        table="user_sealed_product_holdings",
        select_candidates=[
            "id,user_id,sealed_product_id,quantity,purchase_price,cost_basis,roi,unrealized_gain,acquisition_date,fees_taxes,notes",
            "id,user_id,sealed_product_id,quantity",
        ],
        filters=[("eq", "id", normalized_entry_id), ("eq", "user_id", user_id)],
        limit=1,
        correlation_id=correlation_id,
        trace_label="entry_lookup_sealed",
        db_client=client,
    )

    if sealed_rows:
        holding = sealed_rows[0]
        sealed_join_rows = _select_with_fallback(
            table="sealed_products",
            select_candidates=["id,name,product_type,set_id,image_small_url,image_large_url", "id,name,product_type,set_id"],
            filters=[("eq", "id", holding.get("sealed_product_id"))],
            limit=1,
            correlation_id=correlation_id,
            trace_label="entry_sealed_product",
            db_client=client,
        )
        sealed = sealed_join_rows[0] if sealed_join_rows else {}
        set_rows = _select_with_fallback(
            table="sets",
            select_candidates=["id,name"],
            filters=[("eq", "id", sealed.get("set_id"))],
            limit=1,
            correlation_id=correlation_id,
            trace_label="entry_sealed_set",
            db_client=client,
        ) if sealed.get("set_id") else []
        market_rows = _select_with_fallback(
            table="sealed_product_market_usd_latest",
            select_candidates=["sealed_product_id,market_price,current_market_price,price"],
            filters=[("eq", "sealed_product_id", holding.get("sealed_product_id"))],
            limit=1,
            correlation_id=correlation_id,
            trace_label="entry_sealed_market",
            db_client=client,
        )
        market_lookup = _build_price_lookup(market_rows, "sealed_product_id")
        estimated_value = _to_number(market_lookup.get(str(holding.get("sealed_product_id"))), 0.0) * max(
            0.0, _to_number(holding.get("quantity"), 0.0)
        )
        images = _resolve_card_like_images(
            variant_small=sealed.get("image_small_url"),
            variant_large=sealed.get("image_large_url"),
            card_small=None,
            card_large=None,
        )
        entry = {
            "id": str(holding.get("id") or ""),
            "collectible_type": "sealed_product",
            "collectible_id": holding.get("sealed_product_id"),
            "quantity": int(max(0.0, _to_number(holding.get("quantity"), 0.0))),
            "name": _to_optional_string(sealed.get("name")) or "Sealed Product",
            "set_name": _to_optional_string((set_rows[0] if set_rows else {}).get("name")),
            "card_number": None,
            "rarity": None,
            "condition": "Sealed",
            "printing_type": None,
            "edition": None,
            "special_type": _to_optional_string(sealed.get("product_type")),
            "estimated_value": estimated_value,
            "image_url": images["image_url"],
            "image_large_url": images["image_large_url"],
        }
        if include_private_fields:
            entry.update(
                {
                    "user_id": holding.get("user_id"),
                    "purchase_price": _to_number(holding.get("purchase_price"), 0.0),
                    "cost_basis": _to_number(holding.get("cost_basis"), 0.0),
                    "roi": _to_number(holding.get("roi"), 0.0),
                    "unrealized_gain": _to_number(holding.get("unrealized_gain"), 0.0),
                    "acquisition_date": holding.get("acquisition_date"),
                    "fees_taxes": _to_number(holding.get("fees_taxes"), 0.0),
                    "notes": _to_optional_string(holding.get("notes")),
                }
            )
        logger.info(
            "collection.entry_lookup correlation_id=%s user_id=%s entry_id=%s collectible_type=%s found=%s elapsed_ms=%.2f",
            correlation_id,
            user_id,
            normalized_entry_id,
            "sealed_product",
            bool(entry),
            (perf_counter() - started_at) * 1000,
        )
        return entry

    graded_rows = _select_with_fallback(
        table="user_graded_card_holdings",
        select_candidates=[
            "id,user_id,graded_card_variant_id,quantity,purchase_price,cost_basis,roi,unrealized_gain,acquisition_date,fees_taxes,notes",
            "id,user_id,graded_card_variant_id,quantity",
        ],
        filters=[("eq", "id", normalized_entry_id), ("eq", "user_id", user_id)],
        limit=1,
        correlation_id=correlation_id,
        trace_label="entry_lookup_graded",
        db_client=client,
    )

    if graded_rows:
        holding = graded_rows[0]
        graded_variant_rows = _select_with_fallback(
            table="graded_card_variants",
            select_candidates=["id,card_variant_id,grade", "id,card_variant_id"],
            filters=[("eq", "id", holding.get("graded_card_variant_id"))],
            limit=1,
            correlation_id=correlation_id,
            trace_label="entry_graded_variant",
            db_client=client,
        )
        graded_variant = graded_variant_rows[0] if graded_variant_rows else {}
        variant_rows = _select_with_fallback(
            table="card_variants",
            select_candidates=["id,card_id,printing_type,special_type,edition,image_small_url,image_large_url", "id,card_id"],
            filters=[("eq", "id", graded_variant.get("card_variant_id"))],
            limit=1,
            correlation_id=correlation_id,
            trace_label="entry_graded_card_variant",
            db_client=client,
        )
        variant = variant_rows[0] if variant_rows else {}
        card_rows_join = _select_with_fallback(
            table="cards",
            select_candidates=["id,name,rarity,card_number,set_id,image_small_url,image_large_url", "id,name,set_id"],
            filters=[("eq", "id", variant.get("card_id"))],
            limit=1,
            correlation_id=correlation_id,
            trace_label="entry_graded_card",
            db_client=client,
        )
        card = card_rows_join[0] if card_rows_join else {}
        set_rows = _select_with_fallback(
            table="sets",
            select_candidates=["id,name"],
            filters=[("eq", "id", card.get("set_id"))],
            limit=1,
            correlation_id=correlation_id,
            trace_label="entry_graded_set",
            db_client=client,
        ) if card.get("set_id") else []
        market_rows = _select_with_fallback(
            table="graded_card_market_latest",
            select_candidates=["graded_card_variant_id,market_price,current_market_price,price"],
            filters=[("eq", "graded_card_variant_id", holding.get("graded_card_variant_id"))],
            limit=1,
            correlation_id=correlation_id,
            trace_label="entry_graded_market",
            db_client=client,
        )
        market_lookup = _build_price_lookup(market_rows, "graded_card_variant_id")
        estimated_value = _to_number(market_lookup.get(str(holding.get("graded_card_variant_id"))), 0.0) * max(
            0.0, _to_number(holding.get("quantity"), 0.0)
        )
        images = _resolve_card_like_images(
            variant_small=variant.get("image_small_url"),
            variant_large=variant.get("image_large_url"),
            card_small=card.get("image_small_url"),
            card_large=card.get("image_large_url"),
        )
        grade_value = graded_variant.get("grade")
        entry = {
            "id": str(holding.get("id") or ""),
            "collectible_type": "graded_card",
            "collectible_id": holding.get("graded_card_variant_id"),
            "quantity": int(max(0.0, _to_number(holding.get("quantity"), 0.0))),
            "name": _to_optional_string(card.get("name")) or "Graded Card",
            "set_name": _to_optional_string((set_rows[0] if set_rows else {}).get("name")),
            "card_number": _to_optional_string(card.get("card_number")),
            "rarity": _to_optional_string(card.get("rarity")),
            "condition": f"Grade {grade_value}" if grade_value not in (None, "") else None,
            "printing_type": _to_optional_string(variant.get("printing_type")),
            "edition": _to_optional_string(variant.get("edition")),
            "special_type": _to_optional_string(variant.get("special_type")),
            "estimated_value": estimated_value,
            "image_url": images["image_url"],
            "image_large_url": images["image_large_url"],
        }
        if include_private_fields:
            entry.update(
                {
                    "user_id": holding.get("user_id"),
                    "purchase_price": _to_number(holding.get("purchase_price"), 0.0),
                    "cost_basis": _to_number(holding.get("cost_basis"), 0.0),
                    "roi": _to_number(holding.get("roi"), 0.0),
                    "unrealized_gain": _to_number(holding.get("unrealized_gain"), 0.0),
                    "acquisition_date": holding.get("acquisition_date"),
                    "fees_taxes": _to_number(holding.get("fees_taxes"), 0.0),
                    "notes": _to_optional_string(holding.get("notes")),
                }
            )
        logger.info(
            "collection.entry_lookup correlation_id=%s user_id=%s entry_id=%s collectible_type=%s found=%s elapsed_ms=%.2f",
            correlation_id,
            user_id,
            normalized_entry_id,
            "graded_card",
            bool(entry),
            (perf_counter() - started_at) * 1000,
        )
        return entry

    logger.info(
        "collection.entry_lookup correlation_id=%s user_id=%s entry_id=%s collectible_type=%s found=false elapsed_ms=%.2f",
        correlation_id,
        user_id,
        normalized_entry_id,
        None,
        (perf_counter() - started_at) * 1000,
    )
    return None


def get_current_user_portfolio_dashboard_data(user_id: str) -> Dict[str, Any]:
    warnings: List[str] = []
    connected_tables: List[str] = []

    snapshot_rows = _load_dashboard_snapshot_rows(user_id)
    if snapshot_rows:
        connected_tables.append("portfolio_daily_snapshots")

        lifetime_points = []
        for row in snapshot_rows:
            label = _format_date_label(row.get("snapshot_date"), include_year=True)
            if not label:
                continue
            lifetime_points.append({"dateLabel": label, "totalValue": _to_number(row.get("total_value"), 0.0)})

        points = []
        for row in snapshot_rows[-7:]:
            label = _format_date_label(row.get("snapshot_date"), include_year=False)
            if not label:
                continue
            points.append({"dateLabel": label, "totalValue": _to_number(row.get("total_value"), 0.0)})

        latest = snapshot_rows[-1]

        top_movers_rows = _select_with_fallback(
            table="portfolio_movers_7d",
            select_candidates=["asset_id,asset_name,change_percent_7d,current_value"],
            filters=[("eq", "user_id", user_id)],
            limit=20,
        )
        if top_movers_rows:
            connected_tables.append("portfolio_movers_7d")
        else:
            warnings.append("portfolio_movers_7d unavailable")

        allocation_rows = _select_with_fallback(
            table="portfolio_allocations",
            select_candidates=["bucket_label,bucket_percent,bucket_value"],
            filters=[("eq", "user_id", user_id)],
            order_by=("bucket_percent", False),
            limit=5,
        )
        if allocation_rows:
            connected_tables.append("portfolio_allocations")
        else:
            warnings.append("portfolio_allocations unavailable")

        concentration_rows = _select_with_fallback(
            table="portfolio_concentration",
            select_candidates=["top_5_percent,summary_text,updated_at"],
            filters=[("eq", "user_id", user_id)],
            order_by=("updated_at", False),
            limit=1,
        )
        if concentration_rows:
            connected_tables.append("portfolio_concentration")
        else:
            warnings.append("portfolio_concentration unavailable")

        movers = []
        if top_movers_rows:
            raw_movers = []
            for row in top_movers_rows:
                current_value = _to_number(row.get("current_value"), 0.0)
                change_percent = _to_number(row.get("change_percent_7d"), 0.0)
                raw_movers.append(
                    {
                        "id": str(row.get("asset_id") or row.get("asset_name") or "unknown"),
                        "name": row.get("asset_name") or "Unknown Asset",
                        "changePercent7d": change_percent,
                        "dollarImpact": round(current_value * (change_percent / 100.0)),
                    }
                )
            movers = sorted(raw_movers, key=lambda item: abs(item.get("dollarImpact", 0)), reverse=True)[:3]

        allocations = []
        if allocation_rows:
            for idx, row in enumerate(allocation_rows):
                percent = _to_number(row.get("bucket_percent"), 0.0)
                allocations.append(
                    {
                        "id": f"alloc-{idx}",
                        "label": row.get("bucket_label") or f"Bucket {idx + 1}",
                        "valuePercent": max(0.0, min(100.0, percent)),
                        "valueLabel": _format_compact_currency(_to_number(row.get("bucket_value"), 0.0)),
                    }
                )

        concentration_text = concentration_rows[0].get("summary_text") if concentration_rows else None

        return {
            "commandCenter": {
                "totalValue": _to_number(latest.get("total_value"), DEFAULT_DASHBOARD_DATA["commandCenter"]["totalValue"]),
                "change24hPercent": _to_number(
                    latest.get("change_24h_percent"), DEFAULT_DASHBOARD_DATA["commandCenter"]["change24hPercent"]
                ),
                "change7dPercent": _to_number(
                    latest.get("change_7d_percent"), DEFAULT_DASHBOARD_DATA["commandCenter"]["change7dPercent"]
                ),
                "cardsCount": int(_to_number(latest.get("cards_count"), DEFAULT_DASHBOARD_DATA["commandCenter"]["cardsCount"])),
                "sealedCount": int(_to_number(latest.get("sealed_count"), DEFAULT_DASHBOARD_DATA["commandCenter"]["sealedCount"])),
                "wishlistCount": int(
                    _to_number(latest.get("wishlist_count"), DEFAULT_DASHBOARD_DATA["commandCenter"]["wishlistCount"])
                ),
                "lastSyncedAt": latest.get("last_synced_at") or DEFAULT_DASHBOARD_DATA["commandCenter"]["lastSyncedAt"],
                "freshnessLabel": latest.get("freshness_label") or DEFAULT_DASHBOARD_DATA["commandCenter"]["freshnessLabel"],
            },
            "performance": {
                "periodLabel": "Last 7 days",
                "points": points or deepcopy(DEFAULT_DASHBOARD_DATA["performance"]["points"]),
                "rangeSeries": {
                    "LT": {
                        "points": lifetime_points
                        or deepcopy(DEFAULT_DASHBOARD_DATA["performance"]["rangeSeries"]["LT"]["points"]),
                        "helper": "Performance since portfolio inception",
                    }
                },
            },
            "insights": {
                "topMovers": movers or deepcopy(DEFAULT_DASHBOARD_DATA["insights"]["topMovers"]),
                "allocationSummary": allocations or deepcopy(DEFAULT_DASHBOARD_DATA["insights"]["allocationSummary"]),
                "concentrationText": concentration_text or DEFAULT_DASHBOARD_DATA["insights"]["concentrationText"],
            },
            "meta": {
                "connectedTables": connected_tables,
                "warnings": warnings,
                "fallbackUsed": False,
            },
        }

    warnings.append("portfolio_daily_snapshots unavailable")
    dashboard_data = deepcopy(DEFAULT_DASHBOARD_DATA)
    dashboard_data["meta"] = {
        "connectedTables": connected_tables,
        "warnings": warnings,
        "fallbackUsed": True,
    }
    return dashboard_data


def get_public_collection_data_by_username(
    username: str,
    include_collection_items: bool = False,
    viewer_user_id: Optional[str] = None,
    correlation_id: Optional[str] = None,
    limit: Optional[int] = None,
    offset: int = 0,
    resolved_public_user: Optional[Dict[str, Any]] = None,
    resolved_trace: Optional[Dict[str, Any]] = None,
) -> Tuple[Optional[Dict[str, Any]], Optional[str]]:
    total_started_at = perf_counter()
    client = create_service_role_client()
    requested_username = _to_trimmed_string(username)
    username_resolution_started_at = perf_counter()
    trace = resolved_trace or {}
    user = resolved_public_user
    if not user:
        user, trace = resolve_public_user_by_username(
            requested_username,
            correlation_id=correlation_id,
            db_client=client,
        )
    else:
        trace = {
            "normalized_username": normalize_public_username(requested_username),
            "lookup_strategy": "reused_profile_resolution",
            "reason": None,
        }
    username_resolution_elapsed_ms = (perf_counter() - username_resolution_started_at) * 1000
    normalized_username = trace.get("normalized_username")
    if not normalized_username:
        logger.warning(
            "public_collection.trace correlation_id=%s requested_username=%s normalized_username=%s first_resolves_public_profile=false row_found=false reason=INVALID_USERNAME",
            correlation_id,
            requested_username,
            normalized_username,
        )
        return None, "Invalid username."

    if not user or not user.get("id"):
        logger.warning(
            "public_collection.trace correlation_id=%s requested_username=%s normalized_username=%s first_resolves_public_profile=false lookup_strategy=%s row_found=false reason=%s",
            correlation_id,
            requested_username,
            normalized_username,
            trace.get("lookup_strategy"),
            trace.get("reason") or "USER_NOT_FOUND",
        )
        return None, "User not found."

    if user.get("is_profile_public") is False:
        if not viewer_user_id or str(viewer_user_id) != str(user.get("id")):
            logger.warning(
                "public_collection.trace correlation_id=%s requested_username=%s normalized_username=%s first_resolves_public_profile=false lookup_strategy=%s row_found=true resolved_user_id=%s reason=VISIBILITY_REJECT viewer_user_id=%s",
                correlation_id,
                requested_username,
                normalized_username,
                trace.get("lookup_strategy"),
                user.get("id"),
                viewer_user_id,
            )
            return None, "User not found."

    collection_stage_started_at = perf_counter()
    summary_lookup_started_at = perf_counter()
    summary_snapshot: Optional[Dict[str, Any]] = None
    summary_lookup_fallback_used = False
    try:
        summary_snapshot = get_user_collection_summary_snapshot(user.get("id"))
    except Exception:
        summary_lookup_fallback_used = True
        logger.exception(
            "public_collection.summary_lookup correlation_id=%s requested_username=%s user_id=%s row_found=false fallback_used=true reason=SUMMARY_TABLE_READ_FAILED",
            correlation_id,
            requested_username,
            user.get("id"),
        )

    summary_lookup_elapsed_ms = (perf_counter() - summary_lookup_started_at) * 1000
    if isinstance(summary_snapshot, dict) and summary_snapshot.get("row_found") is False:
        summary_lookup_fallback_used = True

    summary = _public_summary_response_from_snapshot(summary_snapshot)
    collection_payload = None

    if include_collection_items:
        collection_payload = get_collection_summary_and_items_for_user_id(
            user_id=str(user.get("id")),
            include_collection_items=True,
            include_private_fields=False,
            limit=limit,
            offset=offset,
            correlation_id=correlation_id,
            requested_username=requested_username,
            db_client=client,
        )

    collection_stage_elapsed_ms = (perf_counter() - collection_stage_started_at) * 1000

    response_payload: Dict[str, Any] = {
        "collection_summary": summary,
    }

    if include_collection_items:
        response_payload["collection_items"] = collection_payload.get("collection_items") if collection_payload else []

    logger.info(
        "public_collection.trace correlation_id=%s requested_username=%s normalized_username=%s first_resolves_public_profile=false lookup_strategy=%s row_found=true resolved_user_id=%s resolved_username=%s include_items=%s path_used=%s limit=%s offset=%s summary_row_found=%s summary_computed_at=%s summary_is_stale=%s summary_fallback_used=%s portfolio_value=%s cards=%s sealed=%s graded=%s collection_items=%s payload_size_bytes=%s username_resolution_ms=%.2f summary_lookup_ms=%.2f collection_stage_ms=%.2f total_ms=%.2f",
        correlation_id,
        requested_username,
        normalized_username,
        trace.get("lookup_strategy"),
        user.get("id"),
        user.get("username"),
        include_collection_items,
        "full_assembly" if include_collection_items else "summary_snapshot",
        limit,
        offset,
        summary_snapshot.get("row_found") if isinstance(summary_snapshot, dict) else False,
        summary_snapshot.get("computed_at") if isinstance(summary_snapshot, dict) else None,
        summary_snapshot.get("is_stale") if isinstance(summary_snapshot, dict) else None,
        summary_lookup_fallback_used,
        summary.get("portfolio_value") if isinstance(summary, dict) else None,
        summary.get("cards_count") if isinstance(summary, dict) else None,
        summary.get("sealed_count") if isinstance(summary, dict) else None,
        summary.get("graded_count") if isinstance(summary, dict) else None,
        len(response_payload.get("collection_items") or []),
        _payload_size_bytes(response_payload),
        username_resolution_elapsed_ms,
        summary_lookup_elapsed_ms,
        collection_stage_elapsed_ms,
        (perf_counter() - total_started_at) * 1000,
    )

    return response_payload, None


def get_public_collection_entry_by_username_and_item_id(
    username: str,
    item_id: str,
    viewer_user_id: Optional[str] = None,
    correlation_id: Optional[str] = None,
) -> Tuple[Optional[Dict[str, Any]], Optional[str]]:
    client = create_service_role_client()
    requested_username = _to_trimmed_string(username)
    user, trace = resolve_public_user_by_username(
        requested_username,
        correlation_id=correlation_id,
        db_client=client,
    )

    if not user or not user.get("id"):
        return None, "User not found."

    if user.get("is_profile_public") is False:
        if not viewer_user_id or str(viewer_user_id) != str(user.get("id")):
            return None, "User not found."

    entry = get_collection_entry_detail_for_user_id(
        user_id=str(user.get("id")),
        entry_id=item_id,
        include_private_fields=False,
        correlation_id=correlation_id,
    )
    if not entry:
        logger.info(
            "public_collection.entry_lookup correlation_id=%s requested_username=%s normalized_username=%s lookup_strategy=%s item_id=%s found=false",
            correlation_id,
            requested_username,
            trace.get("normalized_username"),
            trace.get("lookup_strategy"),
            item_id,
        )
        return None, "Collection entry not found."

    logger.info(
        "public_collection.entry_lookup correlation_id=%s requested_username=%s normalized_username=%s lookup_strategy=%s item_id=%s found=true collectible_type=%s",
        correlation_id,
        requested_username,
        trace.get("normalized_username"),
        trace.get("lookup_strategy"),
        item_id,
        entry.get("collectible_type"),
    )
    return entry, None
