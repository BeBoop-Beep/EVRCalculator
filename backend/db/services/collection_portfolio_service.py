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


def _to_nullable_number(value: Any) -> Optional[float]:
    if value is None:
        return None
    try:
        parsed = float(value)
    except (TypeError, ValueError):
        return None
    if parsed != parsed or parsed in (float("inf"), float("-inf")):
        return None
    return parsed


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


def _first_non_empty(*values: Any) -> Optional[str]:
    for value in values:
        normalized = _to_trimmed_string(value)
        if normalized:
            return normalized
    return None


def _resolve_legacy_large_image_url(
    primary_large: Any,
    primary_small: Any,
    secondary_large: Any = None,
    secondary_small: Any = None,
) -> str:
    return (
        _first_non_empty(primary_large, secondary_large, primary_small, secondary_small)
        or DEFAULT_COLLECTION_IMAGE_PATH
    )


def _normalize_collectible_type_from_view(holding_type: Any) -> str:
    normalized = _to_trimmed_string(holding_type).lower()
    mapped = {
        "card": "card",
        "cards": "card",
        "sealed_product": "sealed_product",
        "sealed": "sealed_product",
        "sealedproduct": "sealed_product",
        "graded_card": "graded_card",
        "graded": "graded_card",
        "gradedcard": "graded_card",
    }
    return mapped.get(normalized, "card")


def _resolve_view_image_payload(collectible_type: str, image_url: Optional[str]) -> Dict[str, str]:
    if collectible_type == "sealed_product":
        return resolve_display_image("sealed_product", sealed_large=image_url, sealed_small=image_url)
    if collectible_type == "graded_card":
        return resolve_display_image("graded_card", card_large=image_url, card_small=image_url)
    return resolve_display_image("card", card_large=image_url, card_small=image_url)


def resolve_display_image(
    collectible_type: str,
    *,
    variant_large: Any = None,
    variant_small: Any = None,
    card_large: Any = None,
    card_small: Any = None,
    sealed_large: Any = None,
    sealed_small: Any = None,
) -> Dict[str, str]:
    if collectible_type == "card":
        resolved_variant = _first_non_empty(variant_large, variant_small)
        if resolved_variant:
            return {
                "image_url": resolved_variant,
                "image_type": "card",
                "image_source": "card_variant",
                "source_confidence": "high",
            }

        resolved_card = _first_non_empty(card_large, card_small)
        if resolved_card:
            return {
                "image_url": resolved_card,
                "image_type": "card",
                "image_source": "card",
                "source_confidence": "high",
            }

        return {
            "image_url": DEFAULT_COLLECTION_IMAGE_PATH,
            "image_type": "card",
            "image_source": "fallback",
            "source_confidence": "low",
        }

    if collectible_type == "graded_card":
        resolved_variant = _first_non_empty(variant_large, variant_small)
        if resolved_variant:
            return {
                "image_url": resolved_variant,
                "image_type": "graded_base_card",
                "image_source": "graded_linked_card_variant",
                "source_confidence": "medium",
            }

        resolved_card = _first_non_empty(card_large, card_small)
        if resolved_card:
            return {
                "image_url": resolved_card,
                "image_type": "graded_base_card",
                "image_source": "graded_linked_card",
                "source_confidence": "medium",
            }

        return {
            "image_url": DEFAULT_COLLECTION_IMAGE_PATH,
            "image_type": "graded_base_card",
            "image_source": "fallback",
            "source_confidence": "low",
        }

    resolved_sealed = _first_non_empty(sealed_large, sealed_small)
    if resolved_sealed:
        return {
            "image_url": resolved_sealed,
            "image_type": "sealed",
            "image_source": "sealed_product",
            "source_confidence": "high",
        }

    return {
        "image_url": DEFAULT_COLLECTION_IMAGE_PATH,
        "image_type": "fallback",
        "image_source": "fallback",
        "source_confidence": "low",
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
    view_query_started_at = perf_counter()
    view_rows = _select_with_fallback(
        table="user_collection_items_with_market",
        select_candidates=[
            "holding_id,holding_type,collectible_id,quantity,name,card_number,rarity,condition_id,condition,printing_type,edition,special_type,product_type,grade_value,special_label,grading_company_name,certification_number,image_url,market_price,estimated_value,set_name,set_id,user_id",
            "holding_id,holding_type,collectible_id,quantity,name,card_number,rarity,condition_id,condition,printing_type,edition,special_type,product_type,grade_value,special_label,grading_company_name,certification_number,image_url,market_price,estimated_value,set_name,user_id",
            "holding_id,holding_type,collectible_id,quantity,name,card_number,rarity,condition,printing_type,edition,special_type,product_type,grade_value,special_label,grading_company_name,certification_number,image_url,market_price,estimated_value,set_name,user_id",
            "holding_id,holding_type,collectible_id,quantity,name,card_number,rarity,condition,printing_type,edition,special_type,product_type,image_url,market_price,estimated_value,set_name,user_id",
            "holding_id,holding_type,collectible_id,quantity,name,image_url,market_price,estimated_value,user_id",
        ],
        filters=[("eq", "user_id", user_id)],
        correlation_id=correlation_id,
        trace_label="collection_items_with_market",
        limit=limit,
        offset=offset,
        db_client=client,
    )
    view_query_elapsed_ms = (perf_counter() - view_query_started_at) * 1000

    private_fields_map: Dict[str, Dict[str, Any]] = {}
    private_query_elapsed_ms = 0.0
    if include_private_fields:
        private_query_started_at = perf_counter()
        holding_ids_by_type: Dict[str, List[str]] = {
            "card": [],
            "sealed_product": [],
            "graded_card": [],
        }
        for row in view_rows:
            normalized_type = _normalize_collectible_type_from_view(row.get("holding_type"))
            holding_id = row.get("holding_id")
            if holding_id is None:
                continue
            holding_ids_by_type[normalized_type].append(str(holding_id))

        card_private_rows = (
            _select_with_fallback(
                table="user_card_holdings",
                select_candidates=[
                    "id,user_id,purchase_price,cost_basis,roi,unrealized_gain,acquisition_date,fees_taxes,notes",
                    "id,user_id,purchase_price,cost_basis,roi,unrealized_gain,acquisition_date,fees_taxes",
                    "id,user_id,purchase_price,cost_basis,roi,unrealized_gain,acquisition_date",
                    "id,user_id,purchase_price,cost_basis,roi,unrealized_gain",
                    "id,user_id,purchase_price,cost_basis",
                    "id,user_id,purchase_price",
                    "id,user_id",
                    "id",
                ],
                filters=[("in", "id", _unique_values(holding_ids_by_type["card"]))],
                correlation_id=correlation_id,
                trace_label="collection_items_private_card",
                db_client=client,
            )
            if holding_ids_by_type["card"]
            else []
        )
        sealed_private_rows = (
            _select_with_fallback(
                table="user_sealed_product_holdings",
                select_candidates=[
                    "id,user_id,purchase_price,cost_basis,roi,unrealized_gain,acquisition_date,fees_taxes,notes",
                    "id,user_id,purchase_price,cost_basis,roi,unrealized_gain,acquisition_date,fees_taxes",
                    "id,user_id,purchase_price,cost_basis,roi,unrealized_gain,acquisition_date",
                    "id,user_id,purchase_price,cost_basis,roi,unrealized_gain",
                    "id,user_id,purchase_price,cost_basis",
                    "id,user_id,purchase_price",
                    "id,user_id",
                    "id",
                ],
                filters=[("in", "id", _unique_values(holding_ids_by_type["sealed_product"]))],
                correlation_id=correlation_id,
                trace_label="collection_items_private_sealed",
                db_client=client,
            )
            if holding_ids_by_type["sealed_product"]
            else []
        )
        graded_private_rows = (
            _select_with_fallback(
                table="user_graded_card_holdings",
                select_candidates=[
                    "id,user_id,purchase_price,cost_basis,roi,unrealized_gain,acquisition_date,fees_taxes,notes",
                    "id,user_id,purchase_price,cost_basis,roi,unrealized_gain,acquisition_date,fees_taxes",
                    "id,user_id,purchase_price,cost_basis,roi,unrealized_gain,acquisition_date",
                    "id,user_id,purchase_price,cost_basis,roi,unrealized_gain",
                    "id,user_id,purchase_price,cost_basis",
                    "id,user_id,purchase_price",
                    "id,user_id",
                    "id",
                ],
                filters=[("in", "id", _unique_values(holding_ids_by_type["graded_card"]))],
                correlation_id=correlation_id,
                trace_label="collection_items_private_graded",
                db_client=client,
            )
            if holding_ids_by_type["graded_card"]
            else []
        )

        for row in card_private_rows:
            private_fields_map[f"card:{row.get('id')}"] = row
        for row in sealed_private_rows:
            private_fields_map[f"sealed_product:{row.get('id')}"] = row
        for row in graded_private_rows:
            private_fields_map[f"graded_card:{row.get('id')}"] = row

        private_query_elapsed_ms = (perf_counter() - private_query_started_at) * 1000

    merge_started_at = perf_counter()
    collection_items: List[Dict[str, Any]] = []
    cards_quantity_total = 0
    sealed_quantity_total = 0
    graded_quantity_total = 0

    for row in view_rows:
        collectible_type = _normalize_collectible_type_from_view(row.get("holding_type"))
        quantity = int(max(0.0, _to_number(row.get("quantity"), 0.0)))

        if collectible_type == "card":
            cards_quantity_total += quantity
        elif collectible_type == "sealed_product":
            sealed_quantity_total += quantity
        elif collectible_type == "graded_card":
            graded_quantity_total += quantity

        resolved_image_url = _to_optional_string(row.get("image_url"))
        display_image = _resolve_view_image_payload(collectible_type, resolved_image_url)
        legacy_large_image_url = _resolve_legacy_large_image_url(
            primary_large=resolved_image_url,
            primary_small=resolved_image_url,
        )

        market_price = _to_nullable_number(row.get("market_price"))
        estimated_value = _to_nullable_number(row.get("estimated_value"))
        if estimated_value is None and market_price is not None:
            estimated_value = float(quantity) * market_price

        condition_label = _to_optional_string(row.get("condition"))
        if collectible_type == "sealed_product" and not condition_label:
            condition_label = "Sealed"
        if collectible_type == "graded_card" and not condition_label:
            grade_value = _to_optional_string(row.get("grade_value"))
            if grade_value:
                condition_label = f"Grade {grade_value}"

        special_type_value = _to_optional_string(row.get("special_type"))
        if not special_type_value:
            special_type_value = _to_optional_string(row.get("product_type"))

        item: Dict[str, Any] = {
            "id": str(row.get("holding_id") or row.get("id") or ""),
            "collectible_type": collectible_type,
            "collectible_id": row.get("collectible_id"),
            "quantity": quantity,
            "name": _to_optional_string(row.get("name"))
            or ("Sealed Product" if collectible_type == "sealed_product" else "Unknown Card"),
            "set_name": _to_optional_string(row.get("set_name")),
            "card_number": _to_optional_string(row.get("card_number")),
            "rarity": _to_optional_string(row.get("rarity")),
            "condition_id": row.get("condition_id"),
            "condition": condition_label,
            "printing_type": _to_optional_string(row.get("printing_type")),
            "edition": _to_optional_string(row.get("edition")),
            "special_type": special_type_value,
            "product_type": _to_optional_string(row.get("product_type")),
            "grade_value": _to_nullable_number(row.get("grade_value")),
            "special_label": _to_optional_string(row.get("special_label")),
            "grading_company_name": _to_optional_string(row.get("grading_company_name")),
            "certification_number": _to_optional_string(row.get("certification_number")),
            "market_price": market_price,
            "estimated_value": estimated_value,
            "image_url": display_image["image_url"],
            "image_large_url": legacy_large_image_url,
            "image_type": display_image["image_type"],
            "image_source": display_image["image_source"],
            "source_confidence": display_image["source_confidence"],
        }

        if include_private_fields:
            private_key = f"{collectible_type}:{item['id']}"
            private_row = private_fields_map.get(private_key, {})
            item.update(
                {
                    "user_id": private_row.get("user_id") if private_row else row.get("user_id"),
                    "purchase_price": _to_number(private_row.get("purchase_price"), 0.0),
                    "cost_basis": _to_number(private_row.get("cost_basis"), 0.0),
                    "roi": _to_number(private_row.get("roi"), 0.0),
                    "unrealized_gain": _to_number(private_row.get("unrealized_gain"), 0.0),
                    "acquisition_date": private_row.get("acquisition_date"),
                    "fees_taxes": _to_number(private_row.get("fees_taxes"), 0.0),
                    "notes": _to_optional_string(private_row.get("notes")),
                }
            )

        collection_items.append(item)

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
        "portfolio_value": _to_number(
            sum(
                item_value
                for item_value in (_to_nullable_number(item.get("estimated_value")) for item in collection_items)
                if item_value is not None
            ),
            0.0,
        ),
        "cards_count": cards_quantity_total,
        "sealed_count": sealed_quantity_total,
        "graded_count": graded_quantity_total,
    }

    serializer_started_at = perf_counter()
    response_payload = {
        "summary": summary,
        "collection_items": collection_items if include_collection_items else [],
    }
    serializer_elapsed_ms = (perf_counter() - serializer_started_at) * 1000

    logger.info(
        "public_collection.timing correlation_id=%s username=%s user_id=%s include_items=%s path_used=%s limit=%s offset=%s view_query_ms=%.2f private_query_ms=%.2f merge_ms=%.2f serializer_ms=%.2f total_ms=%.2f",
        correlation_id,
        requested_username,
        user_id,
        include_collection_items,
        "view_assembly" if include_collection_items else "summary_only",
        limit,
        offset,
        view_query_elapsed_ms,
        private_query_elapsed_ms,
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
        display_image = resolve_display_image(
            "card",
            variant_large=variant.get("image_large_url"),
            variant_small=variant.get("image_small_url"),
            card_large=card.get("image_large_url"),
            card_small=card.get("image_small_url"),
        )
        legacy_large_image_url = _resolve_legacy_large_image_url(
            primary_large=variant.get("image_large_url"),
            primary_small=variant.get("image_small_url"),
            secondary_large=card.get("image_large_url"),
            secondary_small=card.get("image_small_url"),
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
            "image_url": display_image["image_url"],
            "image_large_url": legacy_large_image_url,
            "image_type": display_image["image_type"],
            "image_source": display_image["image_source"],
            "source_confidence": display_image["source_confidence"],
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
        display_image = resolve_display_image(
            "sealed_product",
            sealed_large=sealed.get("image_large_url"),
            sealed_small=sealed.get("image_small_url"),
        )
        legacy_large_image_url = _resolve_legacy_large_image_url(
            primary_large=sealed.get("image_large_url"),
            primary_small=sealed.get("image_small_url"),
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
            "image_url": display_image["image_url"],
            "image_large_url": legacy_large_image_url,
            "image_type": display_image["image_type"],
            "image_source": display_image["image_source"],
            "source_confidence": display_image["source_confidence"],
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
            select_candidates=["id,card_variant_id,card_id,grade", "id,card_variant_id,card_id", "id,card_variant_id"],
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
        resolved_card_id = variant.get("card_id") if variant.get("card_id") is not None else graded_variant.get("card_id")
        card_rows_join = _select_with_fallback(
            table="cards",
            select_candidates=["id,name,rarity,card_number,set_id,image_small_url,image_large_url", "id,name,set_id"],
            filters=[("eq", "id", resolved_card_id)],
            limit=1,
            correlation_id=correlation_id,
            trace_label="entry_graded_card",
            db_client=client,
        ) if resolved_card_id is not None else []
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
        display_image = resolve_display_image(
            "graded_card",
            variant_large=variant.get("image_large_url"),
            variant_small=variant.get("image_small_url"),
            card_large=card.get("image_large_url"),
            card_small=card.get("image_small_url"),
        )
        legacy_large_image_url = _resolve_legacy_large_image_url(
            primary_large=variant.get("image_large_url"),
            primary_small=variant.get("image_small_url"),
            secondary_large=card.get("image_large_url"),
            secondary_small=card.get("image_small_url"),
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
            "image_url": display_image["image_url"],
            "image_large_url": legacy_large_image_url,
            "image_type": display_image["image_type"],
            "image_source": display_image["image_source"],
            "source_confidence": display_image["source_confidence"],
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
