"""Application adapter for canonical, server-ranked leaf-instrument search."""

from __future__ import annotations

from typing import Any
import logging
import time

logger = logging.getLogger(__name__)

MIN_QUERY_LENGTH = 2
MAX_RESULTS = 50
MAX_QUERY_LENGTH = 120
LEGACY_SEARCH_RPC = "search_pokemon_market_explorer_instruments_v2"
LEAF_SEARCH_RPC = "search_pokemon_market_explorer_leaves_v1"
# Compatibility alias for callers that imported the original constant. Explorer
# leaf discovery intentionally does not use it.
SEARCH_RPC = LEGACY_SEARCH_RPC
SITEWIDE_SEARCH_RPC = "search_pokemon_sitewide_instruments_v1"
GRADED_UNAVAILABLE_REASON = "Graded leaf search is not available from the current published authority."


class LeafSearchError(RuntimeError):
    def __init__(self, code: str = "LEAF_SEARCH_FAILED") -> None:
        super().__init__(code)
        self.code = code


def _text(row: dict[str, Any], *keys: str) -> str | None:
    for key in keys:
        value = row.get(key)
        if value is not None and str(value).strip():
            return str(value)
    return None


def _value(row: dict[str, Any], *keys: str) -> Any:
    """Return the first published value, preserving zero/False as authority."""
    for key in keys:
        if key in row and row[key] is not None:
            return row[key]
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
        "setId": _text(row, "set_id", "setId"),
        "setName": _text(row, "set_name", "setName"),
        "secondaryLabel": _text(row, "secondary_label", "secondaryLabel"),
        "imageUrl": _text(row, "image_url", "imageUrl"),
        "marketPrice": _value(row, "market_price", "marketPrice"),
        "marketDate": _text(row, "market_date", "marketDate"),
    }
    if asset == "cards":
        item.update({
            "canonicalCardId": _text(row, "canonical_card_id", "canonicalCardId"),
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
            "sealedProductId": _text(row, "sealed_product_id", "sealedProductId") or instrument_id,
            "productFamily": family,
            "productType": _text(row, "product_type", "productType") or family,
            "variantLabel": _text(row, "variant_label", "variantLabel"),
            "bulkContainer": _value(row, "is_bulk_container", "bulk_container", "bulkContainer"),
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
    started = time.perf_counter()
    rows = list((client.rpc(LEGACY_SEARCH_RPC, {
        "p_query": needle, "p_asset": asset, "p_limit": cap,
    }).execute()).data or [])
    logger.info("market_explorer_exact_search_read", extra={"stage": "instrument_rpc", "asset": asset,
        "result_count": len(rows), "elapsed_ms": round((time.perf_counter() - started) * 1000, 2)})
    # Preserve SQL order: the database owns normalization, relevance, fuzzy
    # matching, cross-asset ranking, and the cap.
    results = [item for row in rows if (item := _canonical_item(dict(row)))]
    results = [item for item in results if asset == "all" or item["asset"] == asset]
    return {"query": needle, "asset": asset, "limit": cap, "items": results[:cap]}


def search_market_explorer_leaves(client: Any, *, q: str, asset: str, limit: int = 20) -> dict[str, Any]:
    """Public Explorer leaf discovery; execution entitlement is enforced elsewhere."""
    needle = " ".join(str(q or "").split())
    if not MIN_QUERY_LENGTH <= len(needle) <= MAX_QUERY_LENGTH:
        raise ValueError(f"q must contain {MIN_QUERY_LENGTH}..{MAX_QUERY_LENGTH} characters")
    if asset not in ("cards", "sealed", "graded"):
        raise ValueError("asset must be cards, sealed, or graded")
    if not 1 <= int(limit) <= MAX_RESULTS:
        raise ValueError(f"limit must be 1..{MAX_RESULTS}")
    if asset == "graded":
        return {
            "query": needle, "asset": asset, "limit": int(limit), "items": [],
            "availability": "INSUFFICIENT_AUTHORITY", "reason": GRADED_UNAVAILABLE_REASON,
        }
    try:
        cap = int(limit)
        rows = list((client.rpc(LEAF_SEARCH_RPC, {
            "p_asset": asset, "p_query": needle, "p_limit": cap,
        }).execute()).data or [])
        items = [item for row in rows if (item := _canonical_item(dict(row)))]
        items = [item for item in items if item["asset"] == asset]
        return {"query": needle, "asset": asset, "limit": cap, "items": items[:cap]}
    except Exception as exc:
        text = f"{type(exc).__name__} {exc}".lower()
        code = "LEAF_SEARCH_UNAVAILABLE" if (
            "pgrst202" in text or "could not find the function" in text
            or "function" in text and "does not exist" in text
        ) else "LEAF_SEARCH_FAILED"
        raise LeafSearchError(code) from exc


def search_sitewide_instruments(client: Any, *, q: str, limit: int = 20) -> dict[str, Any]:
    """Canonical V2 results enriched with route identity in the same RPC call."""
    needle = str(q or "").strip()
    if len(needle) < MIN_QUERY_LENGTH:
        raise ValueError(f"q must contain at least {MIN_QUERY_LENGTH} characters")
    cap = max(1, min(int(limit), MAX_RESULTS))
    rows = list((client.rpc(SITEWIDE_SEARCH_RPC, {
        "p_query": needle, "p_asset": "all", "p_limit": cap,
    }).execute()).data or [])
    results = [item for row in rows if (item := _canonical_item(dict(row)))]
    return {"query": needle, "asset": "all", "limit": cap, "items": results[:cap]}
