"""Bounded V2-only movement enrichment for one Market Explorer constituent page."""

from __future__ import annotations

from datetime import date
from typing import Any, Callable, Mapping

from backend.domain.pokemon.constituent_movement import (
    CONSTITUENT_MOVEMENT_WINDOWS,
    build_constituent_movements,
)
from backend.domain.pokemon.market_index import resolve_window_baselines

V2_DAILY_TABLE = "pokemon_market_explorer_card_daily_states_v2_shadow"
V2_INTERVAL_TABLE = "pokemon_market_price_intervals_v2_shadow"
QUALITY_TABLE = "pokemon_market_date_quality"
WINDOWS = CONSTITUENT_MOVEMENT_WINDOWS
SEALED_MOVEMENT_RPC = "get_pokemon_market_explorer_sealed_constituent_movement_v1"
SEALED_MOVEMENT_MAX_IDS = 100


def _execute_rows(query: Any) -> list[dict[str, Any]]:
    return list(getattr(query.execute(), "data", None) or [])


def _paged(query_factory: Callable[[], Any], *, page_size: int = 1000) -> list[dict[str, Any]]:
    rows: list[dict[str, Any]] = []
    start = 0
    while True:
        page = list(query_factory().range(start, start + page_size - 1).execute().data or [])
        rows.extend(page)
        if len(page) < page_size:
            return rows
        start += page_size


def _published_dates(client: Any, as_of: str) -> list[str]:
    end = date.fromisoformat(str(as_of)[:10])
    rows = _execute_rows(
        client.table(QUALITY_TABLE).select("market_date")
        .eq("tcg", "pokemon").in_("status", ["READY", "LEGACY_VERIFIED"])
        .lte("market_date", end.isoformat())
        .order("market_date")
    )
    return [str(row.get("market_date"))[:10] for row in rows if row.get("market_date")]


def _daily_price_rows(client: Any, variant_ids: list[str], dates: list[str]) -> list[dict[str, Any]]:
    if not variant_ids or not dates:
        return []
    return _paged(
        lambda: client.table(V2_DAILY_TABLE)
        .select("card_variant_id,market_date,market_price")
        .in_("card_variant_id", variant_ids)
        .in_("market_date", dates)
        .order("market_date")
        .order("card_variant_id")
    )


def _interval_price_rows(client: Any, variant_ids: list[str], dates: list[str]) -> list[dict[str, Any]]:
    """Resolve point-in-time prices from V2 intervals for dates outside daily retention."""
    if not variant_ids or not dates:
        return []
    wanted = sorted({str(value)[:10] for value in dates})
    max_date = wanted[-1]
    interval_rows: list[dict[str, Any]] = []
    for offset in range(0, len(variant_ids), 50):
        batch = variant_ids[offset:offset + 50]
        interval_rows.extend(_paged(
            lambda batch=batch: client.table(V2_INTERVAL_TABLE)
            .select("card_variant_id,set_id,market_price,valid_from,valid_to")
            .in_("card_variant_id", batch)
            .lte("valid_from", max_date)
            .order("card_variant_id")
            .order("valid_from")
        ))

    resolved: list[dict[str, Any]] = []
    for market_date in wanted:
        for row in interval_rows:
            valid_from = str(row.get("valid_from") or "")[:10]
            valid_to = str(row.get("valid_to") or "")[:10] if row.get("valid_to") else None
            if valid_from and valid_from <= market_date and (valid_to is None or market_date < valid_to):
                resolved.append({
                    "card_variant_id": row.get("card_variant_id"),
                    "market_date": market_date,
                    "market_price": row.get("market_price"),
                })
    return resolved


def enrich_card_constituent_page(client: Any, page: Mapping[str, Any]) -> dict[str, Any]:
    """Enrich one constituent page from V2 daily rows plus V2 interval fallback."""
    result = dict(page)
    items = [dict(row) for row in result.get("items") or []]
    as_of = str(result.get("as_of") or result.get("asOf") or "")[:10]
    variant_ids = sorted({str(row.get("cardVariantId") or "") for row in items} - {""})
    if not items or not as_of or not variant_ids:
        result["items"] = items
        return result

    market_dates = _published_dates(client, as_of)
    baselines = resolve_window_baselines(market_dates)
    wanted_dates = sorted({
        str((baselines.get(window) or {}).get("startDate") or "")[:10]
        for window in WINDOWS
    } - {""})

    rows = _daily_price_rows(client, variant_ids, wanted_dates)
    found_dates = {str(row.get("market_date"))[:10] for row in rows if row.get("market_date")}
    missing_dates = [value for value in wanted_dates if value not in found_dates]
    if missing_dates:
        rows.extend(_interval_price_rows(client, variant_ids, missing_dates))

    prices: dict[str, dict[str, float]] = {as_of: {}}
    for item in items:
        variant_id = str(item.get("cardVariantId") or "")
        try:
            prices[as_of][variant_id] = float(item["marketPrice"])
        except (KeyError, TypeError, ValueError):
            pass
    for row in rows:
        try:
            prices.setdefault(str(row["market_date"])[:10], {})[
                str(row["card_variant_id"])
            ] = float(row["market_price"])
        except (KeyError, TypeError, ValueError):
            continue

    movement = build_constituent_movements(prices, windows=WINDOWS)
    by_id = movement.get("byConstituent") or {}
    for item in items:
        item["changes"] = by_id.get(str(item.get("cardVariantId") or ""), {})
    result["items"] = items
    result["movement_windows"] = movement.get("windows") or {}
    return result


def enrich_sealed_constituent_page(client: Any, page: Mapping[str, Any]) -> dict[str, Any]:
    """Attach DB-authoritative movement to one bounded sealed-product page.

    The RPC owns baseline selection and percentage calculation. This adapter
    only validates the civil date, performs one call, and maps rows by the
    canonical sealed product identity. Missing baselines remain ``None``.
    """
    result = dict(page)
    items = [dict(row) for row in result.get("items") or []]
    as_of = str(result.get("as_of") or result.get("asOf") or "")[:10]
    try:
        as_of = date.fromisoformat(as_of).isoformat()
    except ValueError:
        result["items"] = items
        return result
    product_ids = list(dict.fromkeys(
        str(row.get("sealedProductId") or "") for row in items
        if row.get("sealedProductId")
    ))
    if not items or not product_ids:
        result["items"] = items
        return result
    if len(product_ids) > SEALED_MOVEMENT_MAX_IDS:
        raise ValueError("sealed movement requires 1..100 product ids")

    rows = _execute_rows(client.rpc(SEALED_MOVEMENT_RPC, {
        "p_sealed_product_ids": product_ids,
        "p_as_of": as_of,
    }))
    by_id = {str(row.get("sealed_product_id")): row for row in rows}
    fields = {
        "1D": ("movement_1d_pct", "baseline_1d_date"),
        "7D": ("movement_7d_pct", "baseline_7d_date"),
        "30D": ("movement_30d_pct", "baseline_30d_date"),
        "3M": ("movement_3m_pct", "baseline_3m_date"),
    }
    for item in items:
        movement_row = by_id.get(str(item.get("sealedProductId") or ""), {})
        item["changes"] = {
            window: (None if movement_row.get(value_key) is None else float(movement_row[value_key]))
            for window, (value_key, _) in fields.items()
        }
        item["changeBaselines"] = {
            window: (str(movement_row[date_key])[:10] if movement_row.get(date_key) else None)
            for window, (_, date_key) in fields.items()
        }
    result["items"] = items
    return result


def enrich_constituent_page(client: Any, page: Mapping[str, Any], asset: str) -> dict[str, Any]:
    """Dispatch movement enrichment by asset without crossing authorities."""
    if asset == "cards":
        return enrich_card_constituent_page(client, page)
    if asset == "sealed":
        return enrich_sealed_constituent_page(client, page)
    return dict(page)
