"""Collection dashboard and item DTO assembly for API endpoints."""

from __future__ import annotations

from copy import deepcopy
from datetime import datetime
import logging
from typing import Any, Dict, Iterable, List, Optional, Tuple
from uuid import UUID

from backend.db.clients.supabase_client import supabase


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
) -> List[Dict[str, Any]]:
    filters = filters or []

    for select_clause in select_candidates:
        try:
            query = supabase.table(table).select(select_clause)
            for operator, column, value in filters:
                if operator == "eq":
                    query = query.eq(column, value)
                elif operator == "in" and isinstance(value, list) and value:
                    query = query.in_(column, value)

            if order_by:
                query = query.order(order_by[0], desc=not order_by[1])

            if isinstance(limit, int):
                query = query.limit(limit)

            response = query.execute()
            return response.data or []
        except Exception:
            continue

    return []


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
) -> Dict[str, Any]:
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

    card_holdings = _select_with_fallback(
        table="user_card_holdings",
        select_candidates=card_holdings_select_candidates,
        filters=[("eq", "user_id", user_id)],
    )
    sealed_holdings = _select_with_fallback(
        table="user_sealed_product_holdings",
        select_candidates=sealed_holdings_select_candidates,
        filters=[("eq", "user_id", user_id)],
    )
    graded_holdings = _select_with_fallback(
        table="user_graded_card_holdings",
        select_candidates=graded_holdings_select_candidates,
        filters=[("eq", "user_id", user_id)],
    )

    card_variant_ids = _unique_values(row.get("card_variant_id") for row in card_holdings)
    condition_ids = _unique_values(row.get("condition_id") for row in card_holdings)
    sealed_product_ids = _unique_values(row.get("sealed_product_id") for row in sealed_holdings)
    graded_variant_ids = _unique_values(row.get("graded_card_variant_id") for row in graded_holdings)

    card_market_rows = (
        _select_with_fallback(
            table="card_market_usd_latest_by_condition",
            select_candidates=["variant_id,condition_id,market_price,current_market_price,price"],
            filters=[("in", "variant_id", card_variant_ids)],
        )
        if card_variant_ids
        else []
    )

    sealed_market_rows = (
        _select_with_fallback(
            table="sealed_product_market_usd_latest",
            select_candidates=["sealed_product_id,market_price,current_market_price,price"],
            filters=[("in", "sealed_product_id", sealed_product_ids)],
        )
        if sealed_product_ids
        else []
    )

    graded_market_rows = (
        _select_with_fallback(
            table="graded_card_market_latest",
            select_candidates=["graded_card_variant_id,market_price,current_market_price,price"],
            filters=[("in", "graded_card_variant_id", graded_variant_ids)],
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
        )
        if linked_card_ids
        else []
    )

    graded_variant_rows = (
        _select_with_fallback(
            table="graded_card_variants",
            select_candidates=[
                "id,card_variant_id,grade,grading_company",
                "id,card_variant_id,grade",
                "id,card_variant_id",
            ],
            filters=[("in", "id", graded_variant_ids)],
        )
        if graded_variant_ids
        else []
    )

    sealed_rows = (
        _select_with_fallback(
            table="sealed_products",
            select_candidates=[
                "id,name,product_type,set_id,image_small_url,image_large_url",
                "id,name,product_type,set_id",
            ],
            filters=[("in", "id", sealed_product_ids)],
        )
        if sealed_product_ids
        else []
    )

    set_ids = _unique_values([*(row.get("set_id") for row in card_rows), *(row.get("set_id") for row in sealed_rows)])
    set_rows = (
        _select_with_fallback(
            table="sets",
            select_candidates=["id,name"],
            filters=[("in", "id", set_ids)],
        )
        if set_ids
        else []
    )

    condition_rows = (
        _select_with_fallback(
            table="conditions",
            select_candidates=["id,name"],
            filters=[("in", "id", condition_ids)],
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

    collection_items = [*card_items, *sealed_items, *graded_items]

    summary = {
        "portfolio_value": _to_number(sum(_to_number(item.get("estimated_value"), 0.0) for item in collection_items), 0.0),
        "cards_count": int(sum(max(0.0, _to_number(row.get("quantity"), 0.0)) for row in card_holdings)),
        "sealed_count": int(sum(max(0.0, _to_number(row.get("quantity"), 0.0)) for row in sealed_holdings)),
        "graded_count": int(sum(max(0.0, _to_number(row.get("quantity"), 0.0)) for row in graded_holdings)),
    }

    return {
        "summary": summary,
        "collection_items": collection_items if include_collection_items else [],
    }


def get_collection_items_for_user_id(user_id: str, include_private_fields: bool = True) -> List[Dict[str, Any]]:
    payload = get_collection_summary_and_items_for_user_id(
        user_id=user_id,
        include_collection_items=True,
        include_private_fields=include_private_fields,
    )
    return payload.get("collection_items", [])


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
) -> Tuple[Optional[Dict[str, Any]], Optional[str]]:
    normalized_username = _to_trimmed_string(username).lower()
    if not normalized_username:
        return None, "Invalid username."

    user_rows = _select_with_fallback(
        table="users",
        select_candidates=["id,username,is_profile_public"],
        filters=[("eq", "username", normalized_username)],
        limit=1,
    )

    user = user_rows[0] if user_rows else None
    if not user or not user.get("id"):
        return None, "User not found."

    if user.get("is_profile_public") is False:
        if not viewer_user_id or str(viewer_user_id) != str(user.get("id")):
            return None, "User not found."

    collection_payload = get_collection_summary_and_items_for_user_id(
        user_id=str(user.get("id")),
        include_collection_items=include_collection_items,
        include_private_fields=False,
    )

    summary = collection_payload.get("summary") or {
        "portfolio_value": 0,
        "cards_count": 0,
        "sealed_count": 0,
        "graded_count": 0,
    }
    summary_source = "collection_portfolio_service.summary"

    try:
        from backend.db.services.collection_summary_service import get_user_collection_summary

        authoritative_summary = get_user_collection_summary(UUID(str(user.get("id")))).to_dict()
        summary = authoritative_summary
        summary_source = "collection_summary_service"
    except Exception:
        logger.exception(
            "[public-profile-debug] authoritative summary load failed username=%s user_id=%s",
            normalized_username,
            user.get("id"),
        )

    logger.warning(
        "[public-profile-debug] public collection summary username=%s source=%s portfolio_value=%s summary_keys=%s item_count=%s",
        normalized_username,
        summary_source,
        summary.get("portfolio_value") if isinstance(summary, dict) else None,
        sorted(summary.keys()) if isinstance(summary, dict) else [],
        len(collection_payload.get("collection_items") or []),
    )

    response_payload: Dict[str, Any] = {
        "collection_summary": summary,
    }

    if include_collection_items:
        response_payload["collection_items"] = collection_payload.get("collection_items") or []

    return response_payload, None
