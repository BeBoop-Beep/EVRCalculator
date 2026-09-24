"""Read-only Phase-5 prepared Market Explorer serving adapter."""
from __future__ import annotations

from threading import Lock
import time
from typing import Any

from backend.domain.pokemon.market_index import compute_strict_window_movements

DIRECTORY_RPC = "get_pokemon_market_explorer_prepared_directory_v1"
COMPARISON_RPC = "get_pokemon_market_explorer_prepared_comparison_v1"
HISTORY_RPC = "get_pokemon_market_explorer_prepared_history_v1"
SCREEN_RPC = "get_pokemon_market_explorer_prepared_screen_v1"
CONTEXT_RPC = "get_pokemon_market_explorer_set_context_ranking_v1"
CONSTITUENTS_RPC = "get_pokemon_market_explorer_prepared_constituents_v3"
PREPARED_CONSTITUENT_MAX_LIMIT = 100
# Constituent counts come ONLY from this compact, identity-keyed cache row --
# never from `pokemon_set_market_dashboard_snapshot_latest.payload_json`
# (a ~6MB-per-set column). That path was deleted deliberately: selecting it
# just to read one integer transported ~12MB through PostgREST for a
# two-market comparison and blew past the RPC's own 5s statement_timeout.
# See backend/db/services/market_explorer_prepared_directory_test.py's
# `test_prepared_comparison_bundle_never_selects_payload_json` guard.
QUERY_CACHE_TABLE = "pokemon_market_explorer_query_cache"
MAX_MARKETS = 25
DIRECTORY_CACHE_TTL_SECONDS = 30.0
_directory_cache_lock = Lock()
_directory_cache_rows: list[dict[str, Any]] | None = None
_directory_cache_expires_at = 0.0


def _rows(result: Any) -> list[dict[str, Any]]:
    return [dict(row) for row in (result.data or [])]


def read_prepared_directory(client: Any) -> list[dict[str, Any]]:
    return _rows(client.rpc(DIRECTORY_RPC, {}).execute())


def read_prepared_directory_cached(client: Any, *, now: float | None = None) -> list[dict[str, Any]]:
    """Return the small public directory from one bounded, stale-safe process cache."""
    global _directory_cache_rows, _directory_cache_expires_at
    current = time.monotonic() if now is None else now
    with _directory_cache_lock:
        if _directory_cache_rows is not None and current < _directory_cache_expires_at:
            return [dict(row) for row in _directory_cache_rows]
        try:
            rows = read_prepared_directory(client)
        except Exception:
            if _directory_cache_rows is not None:
                return [dict(row) for row in _directory_cache_rows]
            raise
        _directory_cache_rows = [dict(row) for row in rows]
        _directory_cache_expires_at = current + DIRECTORY_CACHE_TTL_SECONDS
        return [dict(row) for row in _directory_cache_rows]


def _reset_prepared_directory_cache() -> None:
    global _directory_cache_rows, _directory_cache_expires_at
    with _directory_cache_lock:
        _directory_cache_rows = None
        _directory_cache_expires_at = 0.0


def read_prepared_comparison(client: Any, market_keys: list[str]) -> list[dict[str, Any]]:
    if not 1 <= len(market_keys) <= MAX_MARKETS:
        raise ValueError("prepared comparison requires 1..25 market keys")
    return _rows(client.rpc(COMPARISON_RPC, {"p_market_keys": market_keys}).execute())


def read_prepared_constituents(
    client: Any, market_key: str, generation_id: str, after_rank: int = 0, limit: int = 100,
) -> dict[str, Any]:
    """One bounded, generation-pinned page of a prepared market's roster.

    Reads only. The per-market-type authority (maintained query cache for
    Era/Quick/Rarity, the canonical Set roster reader for Sets, the published
    sealed roster for sealed formats) is dispatched INSIDE the RPC from the
    directory row's own ``source_kind`` -- never inferred from a label or key
    string here. A generation that changed since the caller loaded its
    comparison comes back as ``code == "GENERATION_MISMATCH"``; rows from two
    generations are never mixed.
    """
    if not str(market_key or "").strip() or not str(generation_id or "").strip():
        raise ValueError("prepared constituents require a market key and generation id")
    if int(after_rank) < 0 or not 1 <= int(limit) <= PREPARED_CONSTITUENT_MAX_LIMIT:
        raise ValueError("prepared constituents require afterRank >= 0 and 1..100 rows")
    data = client.rpc(CONSTITUENTS_RPC, {
        "p_market_key": market_key, "p_generation_id": generation_id,
        "p_after_rank": int(after_rank), "p_limit": int(limit),
    }).execute().data
    return dict(data or {})


def enrich_prepared_constituent_page(client: Any, page: dict[str, Any]) -> dict[str, Any]:
    """Attach accepted V2 constituent movement to a CARD page; honest otherwise.

    Sealed rosters have no accepted per-constituent movement authority, so they
    are reported ``movementAvailable: false`` rather than given fabricated
    percentages. Movement failure never fails the roster read.
    """
    result = dict(page)
    rows = list(result.get("rows") or [])
    if result.get("availability") != "available" or not rows:
        result["movementAvailable"] = False
        return result
    if result.get("asset") != "cards":
        result["movementAvailable"] = False
        result["movementReason"] = "Constituent movement is only published for card markets."
        return result
    from backend.db.services.market_explorer_constituent_movement import (
        enrich_card_constituent_page,
        enrich_scoped_card_constituent_page,
    )
    try:
        scoped = any(str(row.get("marketScope") or "standard") != "standard" for row in rows)
        enrich = enrich_scoped_card_constituent_page if scoped else enrich_card_constituent_page
        enriched = enrich(
            client, {"items": rows, "as_of": result.get("priceAsOf")})
    except Exception:
        result["movementAvailable"] = False
        result["movementReason"] = "Constituent movement is temporarily unavailable."
        return result
    result["rows"] = list(enriched.get("items") or rows)
    result["movementWindows"] = enriched.get("movement_windows") or {}
    result["movementAvailable"] = any(row.get("changes") for row in result["rows"])
    return result


def read_prepared_history(client: Any, market_keys: list[str], start_date: str | None = None) -> list[dict[str, Any]]:
    if not 1 <= len(market_keys) <= MAX_MARKETS:
        raise ValueError("prepared history requires 1..25 market keys")
    return _rows(client.rpc(HISTORY_RPC, {"p_market_keys": market_keys, "p_start_date": start_date}).execute())


def _prepared_window_movements(history: list[dict[str, Any]]) -> dict[str, dict[str, dict[str, Any]]]:
    """Compute 1D/7D/30D/3M/6M/1Y/SinceTracking per market from history already fetched.

    Zero additional DB queries: `history` is exactly what
    `read_prepared_history` already returned for this same request. This is
    the one canonical movement primitive (`compute_strict_window_movements`)
    shared with the Cards Market Index and Market Breadth -- no new financial
    math is introduced here, only reuse.
    """
    grouped: dict[str, list[dict[str, Any]]] = {}
    for row in history:
        market_key = str(row.get("market_key") or "")
        if not market_key or row.get("index_value") is None or not row.get("market_date"):
            continue
        grouped.setdefault(market_key, []).append({
            "date": str(row["market_date"])[:10],
            "value": row["index_value"],
        })
    return {
        market_key: compute_strict_window_movements(points)
        for market_key, points in grouped.items()
        if points
    }


def _prepared_constituent_counts(client: Any, markets: list[dict[str, Any]]) -> dict[str, int]:
    """Constituent counts from ONE compact, identity-keyed authority only.

    Prepared rows whose metadata carries a `queryFingerprint` (custom-filter
    and rarity/format markets built through the query engine) resolve their
    count from `pokemon_market_explorer_query_cache`, keyed by that exact
    fingerprint -- an exact identity match, not a "latest as of today" guess.

    Deliberately NOT restored: a Set-market fallback through
    `pokemon_set_cards_snapshot_latest.card_count` or any other "latest"
    table. Those tables carry no `comparison_as_of`/`snapshot_date` column
    that could be checked against a given prepared row's own
    `comparison_as_of`, so using them would silently assume "latest" always
    equals "the date this comparison row was generated for" with no way to
    prove it. A prepared Set market's constituent count is left `None` here
    (the frontend already renders that as "-") rather than fill the cell
    with an unproven number. If a genuinely dated compact authority is
    identified later (e.g. a set-scoped column on
    `pokemon_market_explorer_prepared_directory_v1` itself, populated at
    prepared-generation time), that is the correct place to add it -- not a
    second query against an undated "latest" table here.
    """
    counts: dict[str, int] = {}
    fingerprints = {
        str((row.get("metadata") or {}).get("queryFingerprint") or "")
        for row in markets
        if (row.get("metadata") or {}).get("queryFingerprint")
    }
    if not fingerprints:
        return counts
    rows = list(
        client.table(QUERY_CACHE_TABLE)
        .select("query_fingerprint,constituent_count")
        .in_("query_fingerprint", sorted(fingerprints))
        .execute().data or []
    )
    by_fingerprint = {
        str(row.get("query_fingerprint") or ""): int(row.get("constituent_count") or 0)
        for row in rows if row.get("query_fingerprint")
    }
    for market in markets:
        fingerprint = str((market.get("metadata") or {}).get("queryFingerprint") or "")
        if fingerprint in by_fingerprint:
            counts[str(market.get("market_key") or "")] = by_fingerprint[fingerprint]
    return counts


def read_prepared_comparison_bundle(
    client: Any, market_keys: list[str], start_date: str | None = None,
) -> dict[str, list[dict[str, Any]]]:
    """Comparison rows enriched from the already-requested prepared history.

    Long-window returns (1D/7D/30D/3M/6M/1Y/SinceTracking) are computed
    server-side from the normalized prepared history -- the frontend never
    recomputes financial analytics, only renders published values.
    Constituent counts come only from the compact fingerprint-keyed cache
    row (see `_prepared_constituent_counts`); everything else stays `None`.
    This adds zero DB queries beyond the comparison + history reads already
    performed by the two RPC calls below.
    """
    markets = read_prepared_comparison(client, market_keys)
    history = read_prepared_history(client, market_keys, start_date)
    movements = _prepared_window_movements(history)
    counts = _prepared_constituent_counts(client, markets)
    enriched: list[dict[str, Any]] = []
    for row in markets:
        market_key = str(row.get("market_key") or "")
        enriched.append({
            **row,
            "window_movements": movements.get(market_key, {}),
            "constituent_count": counts.get(market_key),
        })
    found = {str(row.get("market_key") or "") for row in markets}
    return {
        "markets": enriched, "history": history,
        "missingKeys": [key for key in market_keys if key not in found],
    }


def read_prepared_screen(client: Any, screen_key: str, asset: str | None, limit: int) -> list[dict[str, Any]]:
    return _rows(client.rpc(SCREEN_RPC, {"p_screen_key": screen_key, "p_asset": asset, "p_limit": limit}).execute())


def read_set_context_ranking(client: Any, set_id: str, ranking: str, timeframe: str, limit: int, as_of: str | None) -> dict[str, Any]:
    data = client.rpc(CONTEXT_RPC, {"p_set_id": set_id, "p_ranking": ranking, "p_timeframe": timeframe, "p_limit": limit, "p_as_of": as_of}).execute().data
    return dict(data or {})
