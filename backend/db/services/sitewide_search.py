"""Bounded sitewide navigation search composed from canonical authorities."""

from __future__ import annotations

from collections import OrderedDict
from difflib import SequenceMatcher
import re
from threading import Lock
import time
import unicodedata
from urllib.parse import quote
from typing import Any

from backend.db.services.market_explorer_instrument_search import search_sitewide_instruments
from backend.db.services.market_explorer_prepared_directory import read_prepared_directory_cached
from backend.db.services.pokemon_sets_catalog_service import _slugify as slugify_set

MIN_QUERY_LENGTH = 2
MAX_RESULTS = 30
PREPARED_CAP = 8
RESULT_CACHE_TTL_SECONDS = 45.0
RESULT_CACHE_MAX_ENTRIES = 200
_result_cache: OrderedDict[tuple[str, int], tuple[float, dict[str, Any]]] = OrderedDict()
_result_cache_lock = Lock()


def _normalize(value: Any) -> str:
    folded = unicodedata.normalize("NFKD", str(value or "")).encode("ascii", "ignore").decode("ascii").lower()
    return " ".join(re.sub(r"[^a-z0-9]+", " ", folded).split())


def _prepared_rank(label: str, query: str) -> tuple[int, float] | None:
    normalized = _normalize(label)
    tokens, query_tokens = normalized.split(), query.split()
    if normalized == query:
        return (0, 1.0)
    if query_tokens and all(token in tokens for token in query_tokens):
        return (1, 1.0)
    if query_tokens and all(any(word.startswith(token) for word in tokens) for token in query_tokens):
        return (2, 1.0)
    # Controlled typo tolerance: every query token must resemble a distinct
    # label token. This accepts "evolvng skies" but not "roaring skies" for
    # an "evolving skies" query merely because one word is identical.
    remaining = list(tokens)
    token_scores = []
    for query_token in query_tokens:
        choices = [(SequenceMatcher(None, query_token, token).ratio(), index) for index, token in enumerate(remaining)]
        best, index = max(choices, default=(0.0, -1))
        if best < 0.72:
            return None
        token_scores.append(best)
        remaining.pop(index)
    similarity = sum(token_scores) / len(token_scores) if token_scores else 0.0
    threshold = 0.72 if len(query) >= 8 else 0.78
    return (3, similarity) if similarity >= threshold else None


def match_prepared_markets(rows: list[dict[str, Any]], query: str, limit: int = PREPARED_CAP) -> list[dict[str, Any]]:
    normalized_query = _normalize(query)
    ranked = []
    for row in rows:
        market_type = str(row.get("market_type") or "")
        if market_type not in {"set", "era", "curated"}:
            continue
        rank = _prepared_rank(str(row.get("label") or ""), normalized_query)
        if rank is not None:
            ranked.append((rank[0], -rank[1], str(row.get("label") or "").lower(), str(row.get("market_key") or ""), row))
    ranked.sort(key=lambda item: item[:4])
    return [item[4] for item in ranked[: max(0, limit)]]


def _prepared_result(row: dict[str, Any]) -> dict[str, Any]:
    market_type = str(row.get("market_type"))
    label, key = str(row.get("label") or ""), str(row.get("market_key") or "")
    category = {"set": "Sets", "era": "Eras", "curated": "Quick Markets"}[market_type]
    if market_type == "set":
        href = f"/TCGs/Pokemon/Sets/{quote(slugify_set(label), safe='')}"
        secondary = "Pokémon set"
    else:
        href = f"/Market/Explorer?prepared={quote(key, safe='')}"
        secondary = "Prepared era market" if market_type == "era" else "Curated prepared market"
    result_type = "quick" if market_type == "curated" else market_type
    result = {"resultType": result_type, "category": category, "id": key, "label": label,
              "secondaryLabel": secondary, "href": href, "preparedMarketKey": key}
    if market_type == "set":
        metadata = row.get("metadata") if isinstance(row.get("metadata"), dict) else {}
        result["imageUrl"] = metadata.get("logoUrl")
        result["imageFallbackUrl"] = metadata.get("symbolUrl")
    return result


def _cached_result(key: tuple[str, int], now: float) -> dict[str, Any] | None:
    with _result_cache_lock:
        cached = _result_cache.get(key)
        if cached is None or cached[0] <= now:
            if cached is not None:
                del _result_cache[key]
            return None
        _result_cache.move_to_end(key)
        result = {**cached[1], "timing": {"leafSearchMs": 0.0, "preparedMatchMs": 0.0,
                  "cardRouteMs": 0.0, "totalMs": 0.0, "cacheHit": True}}
        return result


def _store_result(key: tuple[str, int], result: dict[str, Any], now: float) -> None:
    with _result_cache_lock:
        _result_cache[key] = (now + RESULT_CACHE_TTL_SECONDS, result)
        _result_cache.move_to_end(key)
        while len(_result_cache) > RESULT_CACHE_MAX_ENTRIES:
            _result_cache.popitem(last=False)


def _reset_sitewide_result_cache() -> None:
    with _result_cache_lock:
        _result_cache.clear()


def search_sitewide(client: Any, *, q: str, limit: int = 20) -> dict[str, Any]:
    needle = str(q or "").strip()
    if len(needle) < MIN_QUERY_LENGTH:
        raise ValueError(f"q must contain at least {MIN_QUERY_LENGTH} characters")
    cap = max(1, min(int(limit), MAX_RESULTS))
    started = time.perf_counter()
    cache_key = (_normalize(needle), cap)
    cached = _cached_result(cache_key, time.monotonic())
    if cached is not None:
        cached["timing"]["totalMs"] = round((time.perf_counter() - started) * 1000, 2)
        return cached
    leaf_started = time.perf_counter()
    leaf = search_sitewide_instruments(client, q=needle, limit=cap)["items"]
    leaf_ms = round((time.perf_counter() - leaf_started) * 1000, 2)
    prepared_started = time.perf_counter()
    prepared = match_prepared_markets(read_prepared_directory_cached(client), needle, min(PREPARED_CAP, cap))
    prepared_ms = round((time.perf_counter() - prepared_started) * 1000, 2)
    leaf_results = []
    for item in leaf:
        asset, instrument_id = item["asset"], item["instrumentId"]
        if asset == "cards":
            card_id = item.get("canonicalCardId")
            if not card_id or not item.get("setId"):
                continue
            href = f"/TCGs/Pokemon/Sets/{quote(str(item['setId']), safe='')}/Cards/{quote(card_id, safe='')}?variant={quote(instrument_id, safe='')}"
            category, result_type = "Cards", "card"
        else:
            href = f"/sealed-products/{quote(instrument_id, safe='')}"
            category, result_type = "Sealed", "sealed"
        leaf_results.append({"resultType": result_type, "category": category, "asset": asset,
            "id": instrument_id, "label": item["displayName"],
            "secondaryLabel": " · ".join(filter(None, [item.get("setName"), item.get("variantLabel"), item.get("cardNumber")])),
            "imageUrl": item.get("imageUrl"), "href": href})
    items = [_prepared_result(row) for row in prepared] + leaf_results
    result = {"query": needle, "limit": cap, "items": items[:cap], "timing": {
        "leafSearchMs": leaf_ms, "preparedMatchMs": prepared_ms,
        "cardRouteMs": 0.0, "totalMs": round((time.perf_counter() - started) * 1000, 2),
        "cacheHit": False}}
    _store_result(cache_key, result, time.monotonic())
    return result
