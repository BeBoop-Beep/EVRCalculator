"""Bounded movement enrichment for one Market Explorer constituent page."""

from __future__ import annotations

from datetime import date, timedelta
from typing import Any, Mapping

from backend.domain.pokemon.constituent_movement import build_constituent_movements
from backend.domain.pokemon.market_index import resolve_window_baselines

V2_TABLE = "pokemon_market_explorer_card_daily_states_v2_shadow"
V1_TABLE = "pokemon_market_explorer_card_daily_states"
QUALITY_TABLE = "pokemon_market_date_quality"
WINDOWS = ("1D", "7D", "30D", "3M")


def _execute_rows(query: Any) -> list[dict[str, Any]]:
    return list(getattr(query.execute(), "data", None) or [])


def _published_dates(client: Any, as_of: str) -> list[str]:
    end = date.fromisoformat(str(as_of)[:10])
    start = end - timedelta(days=100)
    rows = _execute_rows(
        client.table(QUALITY_TABLE).select("market_date")
        .eq("tcg", "pokemon").in_("status", ["READY", "LEGACY_VERIFIED"])
        .gte("market_date", start.isoformat()).lte("market_date", end.isoformat())
        .order("market_date")
    )
    return [str(row.get("market_date"))[:10] for row in rows if row.get("market_date")]


def _price_rows(client: Any, table: str, variant_ids: list[str], dates: list[str]) -> list[dict[str, Any]]:
    if not variant_ids or not dates:
        return []
    return _execute_rows(
        client.table(table).select("card_variant_id,market_date,market_price")
        .in_("card_variant_id", variant_ids).in_("market_date", dates)
    )


def enrich_card_constituent_page(client: Any, page: Mapping[str, Any]) -> dict[str, Any]:
    """Return page rows enriched for all four tabs using two bounded reads max."""
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

    rows = _price_rows(client, V2_TABLE, variant_ids, wanted_dates)
    found_dates = {str(row.get("market_date"))[:10] for row in rows}
    missing_dates = [value for value in wanted_dates if value not in found_dates]
    if missing_dates:
        rows.extend(_price_rows(client, V1_TABLE, variant_ids, missing_dates))

    prices: dict[str, dict[str, float]] = {as_of: {}}
    for item in items:
        variant_id = str(item.get("cardVariantId") or "")
        try:
            prices[as_of][variant_id] = float(item["marketPrice"])
        except (KeyError, TypeError, ValueError):
            pass
    for row in rows:
        try:
            prices.setdefault(str(row["market_date"])[:10], {})[str(row["card_variant_id"])] = float(row["market_price"])
        except (KeyError, TypeError, ValueError):
            continue

    movement = build_constituent_movements(prices, windows=WINDOWS)
    by_id = movement.get("byConstituent") or {}
    for item in items:
        item["changes"] = by_id.get(str(item.get("cardVariantId") or ""), {})
    result["items"] = items
    result["movement_windows"] = movement.get("windows") or {}
    return result
