"""Application adapter for canonical, server-ranked leaf-instrument search."""

from __future__ import annotations

from typing import Any

MIN_QUERY_LENGTH = 2
MAX_RESULTS = 50
SEARCH_RPC = "search_pokemon_market_explorer_instruments_v2"


def _text(row: dict[str, Any], *keys: str) -> str | None:
    for key in keys:
        value = row.get(key)
        if value is not None and str(value).strip():
            return str(value)
    return None


def _canonical_item(row: dict[str, Any]) -> dict[str, Any] | None:
    """Translate the private SQL shape without exposing ranking internals."""
    asset = _text(row, "asset", "asset_type")
    instrument_id = _text(row, "instrument_id", "instrumentId")
    display_name = _text(row, "display_name", "displayName", "name", "product_name", "card_name")
    if asset not in ("cards", "sealed") or not instrument_id or not display_name:
        return None
    item = {
        "asset": asset,
        "instrumentId": instrument_id,
        "displayName": display_name,
        # Transitional aliases keep the Phase-1 picker/drafts compatible.
        "name": display_name,
        "label": display_name,
        "setId": _text(row, "set_id", "setId") or "",
        "setName": _text(row, "set_name", "setName"),
        "secondaryLabel": _text(row, "secondary_label", "secondaryLabel"),
        "imageUrl": _text(row, "image_url", "imageUrl"),
    }
    if asset == "cards":
        item.update({
            "cardNumber": _text(row, "collector_number", "card_number", "cardNumber"),
            "rarity": _text(row, "rarity"),
            "edition": _text(row, "edition"),
            "printingType": _text(row, "printing_type", "printingType"),
            "specialType": _text(row, "special_type", "specialType"),
            "variantLabel": _text(row, "variant_label", "variantLabel"),
        })
    else:
        family = _text(row, "product_family", "productFamily", "product_type", "productType")
        item.update({
            "productFamily": family,
            "productType": _text(row, "product_type", "productType") or family,
            "variantLabel": _text(row, "variant_label", "variantLabel"),
        })
    return {key: value for key, value in item.items() if value is not None}


def search_market_explorer_instruments(client: Any, *, q: str, asset: str = "all",
                                       limit: int = 20) -> dict[str, Any]:
    needle = str(q or "").strip()
    if len(needle) < MIN_QUERY_LENGTH:
        raise ValueError(f"q must contain at least {MIN_QUERY_LENGTH} characters")
    if asset not in ("all", "cards", "sealed"):
        raise ValueError("asset must be all, cards, or sealed")
    cap = max(1, min(int(limit), MAX_RESULTS))
    rows = list((client.rpc(SEARCH_RPC, {
        "p_query": needle, "p_asset": asset, "p_limit": cap,
    }).execute()).data or [])
    # Preserve SQL order: the database owns normalization, relevance, fuzzy
    # matching, cross-asset ranking, and the cap.
    results = [item for row in rows if (item := _canonical_item(dict(row)))]
    results = [item for item in results if asset == "all" or item["asset"] == asset]
    return {"query": needle, "asset": asset, "limit": cap, "items": results[:cap]}
