"""Market Explorer V2 prepared-surface adapter (application layer).

React never learns DB tables. This module reads the DB agent's generation-pinned
V2 surface through its private service-role RPCs and normalizes rows into the
SAME row shape the V1 prepared readers publish (plus a few explicit V2 fields),
so the existing loader/graph keep working.

CUTOVER SEMANTICS (not an error-swallowing fallback):
  * V2 absent (RPC not installed, or no serving generation => empty directory)
    -> callers use the proven V1 prepared surface.
  * V2 present -> V2 is authoritative. Any V2 failure after that point raises;
    it is never masked by V1 data.
"""
from __future__ import annotations

import logging
import time
from threading import Lock
from typing import Any

from backend.db.services.market_explorer_prepared_directory import (
    PreparedSurfaceValidationError, _prepared_window_movements,
)

logger = logging.getLogger(__name__)

DIRECTORY_RPC_V2 = "get_pokemon_market_explorer_surface_directory_v2"
HISTORY_RPC_V2 = "get_pokemon_market_explorer_surface_history_v2"
CONSTITUENTS_RPC_V2 = "get_pokemon_market_explorer_surface_constituents_v2"
ASSET_OPTIONS_RPC_V2 = "get_pokemon_market_explorer_asset_options_v2"
SEARCH_RPC_V1 = "search_pokemon_market_explorer_catalog_v1"
ALIASES_TABLE_V2 = "pokemon_market_explorer_surface_aliases_v2"
SERVING_TABLE_V2 = "pokemon_market_explorer_surface_serving_v2"

MAX_MARKETS_V2 = 25
V2_HISTORY_MAX_KEYS = 50
CONSTITUENT_MAX_LIMIT = 100
SEARCH_MIN_QUERY_LENGTH = 2
SEARCH_MAX_LIMIT = 50
ASSETS = ("cards", "sealed", "graded")
ABSENT_CACHE_TTL_SECONDS = 15.0
DIRECTORY_CACHE_TTL_SECONDS = 30.0

# DB scope_kind -> the V1 `market_type` vocabulary the frontend already renders.
_MARKET_TYPE = {
    "parent": "parent", "era": "era", "set": "set", "quick": "curated",
    "rarity": "prepared_rarity", "type": "prepared_format",
}


class SurfaceV2Error(RuntimeError):
    """A visible V2 failure. `code` is stable; message is safe for logs, not browsers."""

    def __init__(self, code: str, message: str = "") -> None:
        super().__init__(message or code)
        self.code = code


class GenerationMismatch(SurfaceV2Error):
    def __init__(self, message: str = "GENERATION_MISMATCH") -> None:
        super().__init__("GENERATION_MISMATCH", message)


_absent_lock = Lock()
_absent_until = 0.0
_surface_cache_lock = Lock()
_directory_cache: dict[str, tuple[float, list[dict[str, Any]]]] = {}
_alias_cache: dict[str, dict[str, str]] = {}


def _reset_v2_state_cache() -> None:
    global _absent_until
    with _absent_lock:
        _absent_until = 0.0
    with _surface_cache_lock:
        _directory_cache.clear()
        _alias_cache.clear()


def _rows(result: Any) -> list[dict[str, Any]]:
    return [dict(row) for row in (getattr(result, "data", None) or [])]


def _one_row(result: Any) -> dict[str, Any] | None:
    rows = _rows(result)
    return rows[0] if rows else None


def _timed_read(stage: str, operation: Any, **context: Any) -> Any:
    """Emit one stage receipt without changing read or error semantics."""
    started = time.perf_counter()
    outcome = "ok"
    try:
        return operation()
    except Exception:
        outcome = "error"
        raise
    finally:
        logger.info("market_explorer_v2_read", extra={
            "stage": stage,
            "elapsed_ms": round((time.perf_counter() - started) * 1000, 2),
            "outcome": outcome,
            **context,
        })


def _is_rpc_missing(exc: BaseException) -> bool:
    text = f"{type(exc).__name__} {exc}".lower()
    return ("pgrst202" in text or "could not find the function" in text
            or "42883" in text or ("function" in text and "does not exist" in text))


def _num(value: Any) -> Any:
    return None if value is None else float(value)


def normalize_directory_row(row: dict[str, Any]) -> dict[str, Any]:
    """One V2 directory row -> V1-shaped prepared row (+ explicit V2 fields)."""
    scope_kind = row.get("scope_kind")
    end = row.get("history_end_date") or row.get("source_as_of")
    comparison_as_of = row.get("comparison_as_of") or end
    availability = str(row.get("availability") or "available").lower()
    available = availability == "available"
    normalized = {
        "market_key": row.get("market_key"), "label": row.get("label"),
        "base_label": row.get("base_label"), "asset": row.get("asset"),
        "market_type": _MARKET_TYPE.get(str(scope_kind), str(scope_kind or "")),
        "scope_kind": scope_kind, "source_kind": row.get("source_kind"),
        "generation_id": row.get("generation_id"),
        "prepared_series_key": row.get("market_key"),
        "set_id": row.get("set_id"), "era_id": row.get("era_id"),
        "parent_era_id": row.get("era_id") if scope_kind == "set" else None,
        "market_scope": row.get("market_scope"), "taxonomy_key": row.get("taxonomy_key"),
        "source_as_of": row.get("source_as_of"), "comparison_as_of": comparison_as_of,
        "current_value": _num(row.get("current_tracked_value")),
        "comparison_value": _num(row.get("current_tracked_value")),
        "comparison_index_value": _num(row.get("current_index_value")),
        "history_available": bool(row.get("history_available")),
        "history_start_date": row.get("history_start_date"),
        "history_end_date": row.get("history_end_date"),
        "history_point_count": row.get("history_point_count"),
        "constituent_count": row.get("constituent_count"),
        "composition_kind": row.get("composition_kind"),
        "availability": availability,
        "available": available,
        "unavailable_reason": row.get("unavailable_reason"),
        "definition_version": row.get("definition_version"),
        "return_7d_pct": row.get("return_7d_pct"), "return_30d_pct": row.get("return_30d_pct"),
        "return_90d_pct": row.get("return_90d_pct"), "return_1y_pct": row.get("return_1y_pct"),
        "current_drawdown_pct": row.get("current_drawdown_pct"),
        "max_drawdown_pct": row.get("max_drawdown_pct"),
        "screen_group": row.get("screen_group"), "screen_eligible": row.get("screen_eligible"),
        "source_status": "current" if available else availability, "surface_version": "v2",
        "metadata": dict(row.get("metadata") or {}),
    }
    if row.get("market_scope") and "marketScope" not in normalized["metadata"]:
        normalized["metadata"]["marketScope"] = row["market_scope"]
    return normalized


def read_v2_directory(client: Any) -> list[dict[str, Any]] | None:
    """Normalized V2 directory, or None when V2 is not serving.

    None ONLY for: RPC not installed, or an empty directory (no serving
    generation). Every other failure raises SurfaceV2Error (visible).
    """
    global _absent_until
    now = time.monotonic()
    with _absent_lock:
        if now < _absent_until:
            return None
    try:
        serving = _timed_read("serving_pointer", lambda: _one_row(
            client.table(SERVING_TABLE_V2).select("generation_id")
            .eq("singleton", 1).limit(1).execute()))
        serving_generation = str((serving or {}).get("generation_id") or "")
        if serving_generation:
            with _surface_cache_lock:
                cached = _directory_cache.get(serving_generation)
                if cached and now < cached[0]:
                    return [dict(row) for row in cached[1]]
                # The serving pointer is the invalidation authority. Retained
                # generations cannot leak into a new request after promotion.
                for generation in list(_directory_cache):
                    if generation != serving_generation:
                        _directory_cache.pop(generation, None)
                        _alias_cache.pop(generation, None)
                rows = _timed_read("directory", lambda: _rows(client.rpc(DIRECTORY_RPC_V2, {}).execute()),
                                   generation_id=serving_generation)
                if rows:
                    generations = {str(row.get("generation_id")) for row in rows}
                    if generations != {serving_generation}:
                        raise GenerationMismatch("V2 directory does not match serving generation")
                    keys = [row.get("market_key") for row in rows]
                    if len(set(keys)) != len(keys):
                        raise SurfaceV2Error("SURFACE_V2_DUPLICATE_MARKET_KEY")
                    normalized = [normalize_directory_row(row) for row in rows]
                    _directory_cache[serving_generation] = (
                        time.monotonic() + DIRECTORY_CACHE_TTL_SECONDS,
                        [dict(row) for row in normalized],
                    )
                    return normalized
        else:
            rows = _timed_read("directory", lambda: _rows(client.rpc(DIRECTORY_RPC_V2, {}).execute()))
    except SurfaceV2Error:
        raise
    except Exception as exc:
        if _is_rpc_missing(exc):
            with _absent_lock:
                _absent_until = now + ABSENT_CACHE_TTL_SECONDS
            return None
        logger.error("market_explorer_v2_directory_failed", extra={"error": str(exc)[:300]})
        raise SurfaceV2Error("SURFACE_V2_DIRECTORY_FAILED", str(exc)) from exc
    if not rows:
        with _absent_lock:
            _absent_until = now + ABSENT_CACHE_TTL_SECONDS
        return None
    generations = {str(row.get("generation_id")) for row in rows}
    if len(generations) != 1:
        raise GenerationMismatch("V2 directory rows span multiple generations")
    keys = [row.get("market_key") for row in rows]
    if len(set(keys)) != len(keys):
        raise SurfaceV2Error("SURFACE_V2_DUPLICATE_MARKET_KEY")
    normalized = [normalize_directory_row(row) for row in rows]
    generation_id = next(iter(generations))
    with _surface_cache_lock:
        _directory_cache[generation_id] = (
            time.monotonic() + DIRECTORY_CACHE_TTL_SECONDS,
            [dict(row) for row in normalized],
        )
    return normalized


def read_aliases(client: Any, generation_id: str) -> dict[str, str]:
    """Generation-scoped legacy alias -> canonical market key (resolved server-side)."""
    with _surface_cache_lock:
        cached = _alias_cache.get(str(generation_id))
        if cached is not None:
            return dict(cached)
    rows = _timed_read("aliases", lambda: _rows(
        client.table(ALIASES_TABLE_V2).select("alias_key,market_key")
        .eq("generation_id", generation_id).execute()), generation_id=generation_id)
    aliases = {str(r["alias_key"]): str(r["market_key"]) for r in rows}
    with _surface_cache_lock:
        _alias_cache[str(generation_id)] = dict(aliases)
    return aliases


def resolve_requested_keys(keys: list[str], directory_keys: set[str],
                           aliases: dict[str, str]) -> dict[str, str]:
    """requested key -> canonical key. Unknown keys are omitted (reported missing)."""
    resolved: dict[str, str] = {}
    for key in keys:
        if key in directory_keys:
            resolved[key] = key
        elif key in aliases and aliases[key] in directory_keys:
            resolved[key] = aliases[key]
    return resolved


def normalize_history(rows: list[dict[str, Any]], generation_id: str,
                      canonical_to_requested: dict[str, list[str]]) -> list[dict[str, Any]]:
    out: list[dict[str, Any]] = []
    for row in rows:
        row_generation = row.get("generation_id")
        if row_generation is not None and str(row_generation) != str(generation_id):
            raise GenerationMismatch("V2 history row from a different generation")
        key = str(row.get("market_key") or "")
        for requested in canonical_to_requested.get(key, [key]):
            out.append({
                "market_key": key, "requested_market_key": requested,
                "market_date": str(row["market_date"])[:10],
                "index_value": row.get("index_value"), "tracked_value": row.get("tracked_value"),
                "constituent_count": row.get("constituent_count"),
                "chain_segment_id": row.get("chain_segment_id"),
            })
    return out


def read_v2_comparison_bundle(client: Any, directory: list[dict[str, Any]], keys: list[str],
                              start_date: str | None = None) -> dict[str, Any]:
    """Directory row + history + window movements for exactly the requested markets.

    `directory` is the already-read active V2 directory (single read per request).
    Window movements reuse compute_strict_window_movements against the history
    read here -- no second movement implementation, no client-side math.
    """
    if not 1 <= len(keys) <= MAX_MARKETS_V2:
        raise ValueError("prepared comparison requires 1..25 market keys")
    generations = {
        str(row.get("generation_id"))
        for row in directory
        if row.get("generation_id") is not None
    }
    if len(generations) != 1:
        raise GenerationMismatch("V2 directory rows span multiple generations")
    generation_id = str(directory[0]["generation_id"])
    by_key = {row["market_key"]: row for row in directory}
    aliases = read_aliases(client, generation_id)
    resolved = resolve_requested_keys(keys, set(by_key), aliases)
    canonical = list(dict.fromkeys(resolved.values()))
    missing = [key for key in keys if key not in resolved]
    history_rows: list[dict[str, Any]] = []
    if canonical:
        try:
            history_rows = _timed_read("history", lambda: _rows(client.rpc(HISTORY_RPC_V2, {
                "p_market_keys": canonical, "p_start_date": start_date}).execute()),
                generation_id=generation_id, market_count=len(canonical))
        except Exception as exc:
            logger.error("market_explorer_v2_history_failed", extra={"error": str(exc)[:300]})
            raise SurfaceV2Error("SURFACE_V2_HISTORY_FAILED", str(exc)) from exc
    canonical_to_requested: dict[str, list[str]] = {}
    for requested, canon in resolved.items():
        canonical_to_requested.setdefault(canon, []).append(requested)
    history = normalize_history(history_rows, generation_id, canonical_to_requested)
    movements = _prepared_window_movements(history_rows)
    markets = []
    for requested, canon in resolved.items():
        markets.append({**by_key[canon], "requested_market_key": requested,
                        "window_movements": movements.get(canon, {})})
    comparison_as_of = resolve_surface_comparison_as_of(markets)
    if comparison_as_of and any(
        str(row.get("market_date") or "")[:10] > comparison_as_of for row in history
    ):
        raise PreparedSurfaceValidationError("PREPARED_COMPARISON_HISTORY_AFTER_WATERMARK")
    return {"markets": markets, "history": history, "missingKeys": missing,
            "surface": {"version": "v2", "generationId": generation_id,
                        "comparisonAsOf": comparison_as_of}}


def resolve_surface_comparison_as_of(markets: list[dict[str, Any]]) -> str | None:
    """Resolve the V2 comparison watermark at one isolated cutover seam.

    New rows publish ``comparison_as_of`` explicitly. During the additive DB
    rollout, normalized legacy V2 rows temporarily carry their authoritative
    history/source end date in that field. This compatibility path never uses
    wall-clock time and can be deleted once every serving generation publishes
    the explicit column.
    """
    values = {
        str(row.get("comparison_as_of"))[:10]
        for row in markets
        if row.get("comparison_as_of") is not None
        and str(row.get("availability") or "available").lower() == "available"
    }
    if len(values) > 1:
        raise PreparedSurfaceValidationError("PREPARED_COMPARISON_WATERMARK_MISMATCH")
    return next(iter(values), None)


def _valid_iso_date(value: Any) -> str | None:
    from datetime import date
    text = str(value or "")[:10]
    try:
        return date.fromisoformat(text).isoformat() if len(text) == 10 else None
    except ValueError:
        return None


def normalize_constituent_page(payload: dict[str, Any], *, after_rank: int, asset: str | None) -> dict[str, Any]:
    """V2 constituent page -> the contract the frontend page hook already consumes."""
    rows = [dict(r) for r in (payload.get("rows") or [])]
    for index, row in enumerate(rows):
        row.setdefault("rank", after_rank + index + 1)
    total = int(payload.get("totalCount") or 0)
    # The accepted movement enrichment needs ONE as-of date. Use the page's own
    # if published; otherwise normalize once here, and ONLY when every
    # generation-pinned row carries the same valid ISO date. Never guess.
    price_as_of = _valid_iso_date(payload.get("priceAsOf"))
    if price_as_of is None and rows:
        row_dates = {_valid_iso_date(r.get("priceAsOf")) for r in rows}
        if len(row_dates) == 1 and None not in row_dates:
            price_as_of = row_dates.pop()
    last_rank = int(rows[-1]["rank"]) if rows else after_rank
    next_cursor = last_rank if rows and last_rank < total else None
    return {
        "marketKey": payload.get("marketKey"), "requestedMarketKey": payload.get("requestedMarketKey"),
        "generationId": payload.get("generationId"), "asset": asset,
        "availability": payload.get("availability") or "unavailable",
        "availabilityReason": payload.get("reason"), "totalCount": total,
        "afterRank": after_rank, "limit": payload.get("limit"),
        "rows": rows, "nextCursor": next_cursor, "sourceKind": "surface_v2",
        "priceAsOf": price_as_of,
        "movementAvailable": False,
    }


def read_v2_constituents(client: Any, directory: list[dict[str, Any]] | None, market_key: str,
                         generation_id: str, after_rank: int = 0, limit: int = 100) -> dict[str, Any]:
    if not str(market_key or "").strip() or not str(generation_id or "").strip():
        raise ValueError("prepared constituents require a market key and generation id")
    if int(after_rank) < 0 or not 1 <= int(limit) <= CONSTITUENT_MAX_LIMIT:
        raise ValueError("prepared constituents require afterRank >= 0 and 1..100 rows")
    if directory:
        # Converge with comparison: the canonical CURRENT key wins over an alias, and
        # aliases resolve app-side, bounded to the directory's own generation.
        directory_generation = str(directory[0]["generation_id"])
        if directory_generation != str(generation_id):
            return {"code": "GENERATION_MISMATCH", "marketKey": market_key, "generationId": generation_id}
        if market_key not in {row["market_key"] for row in directory}:
            market_key = read_aliases(client, directory_generation).get(market_key, market_key)
    try:
        payload = _timed_read("constituent_page", lambda: client.rpc(CONSTITUENTS_RPC_V2, {
            "p_market_key": market_key, "p_generation_id": generation_id,
            "p_after_rank": int(after_rank), "p_limit": int(limit)}).execute().data,
            generation_id=generation_id, market_key=market_key, after_rank=int(after_rank), limit=int(limit))
    except Exception as exc:
        if "GENERATION_MISMATCH" in str(exc):
            return {"code": "GENERATION_MISMATCH", "marketKey": market_key, "generationId": generation_id}
        logger.error("market_explorer_v2_constituents_failed", extra={"error": str(exc)[:300]})
        raise SurfaceV2Error("SURFACE_V2_CONSTITUENTS_FAILED", str(exc)) from exc
    payload = dict(payload or {})
    if not payload:
        raise SurfaceV2Error("SURFACE_V2_CONSTITUENTS_EMPTY_RESPONSE")
    asset = None
    if directory:
        canonical = payload.get("marketKey") or market_key
        asset = next((r.get("asset") for r in directory if r["market_key"] == canonical), None)
    return normalize_constituent_page(payload, after_rank=int(after_rank), asset=asset)


def read_asset_options(client: Any, asset: str) -> dict[str, Any]:
    asset = str(asset or "").strip().lower()
    if asset not in ASSETS:
        raise ValueError("asset must be cards, sealed or graded")
    try:
        data = _timed_read("asset_options", lambda: client.rpc(
            ASSET_OPTIONS_RPC_V2, {"p_asset": asset}).execute().data, asset=asset)
    except Exception as exc:
        if _is_rpc_missing(exc):
            raise SurfaceV2Error("ASSET_OPTIONS_UNAVAILABLE", "asset options authority not installed") from exc
        raise SurfaceV2Error("ASSET_OPTIONS_FAILED", str(exc)) from exc
    return dict(data or {})


def is_selectable_canonical_rarity(options: Any, rarity_key: str) -> bool:
    """Verify a rarity against the current DB-published execution contract."""
    if not isinstance(options, dict) or options.get("asset") != "cards":
        return False
    for option in options.get("rarities") or ():
        if not isinstance(option, dict) or option.get("key") != rarity_key:
            continue
        return (
            option.get("selectionAvailable") is True
            and option.get("eligibilityState") in {"PREPARED", "CUSTOM_BUILD_AVAILABLE"}
        )
    return False


def validate_search_request(asset: str, q: str, limit: int) -> tuple[str, str, int]:
    asset = str(asset or "").strip().lower()
    query = " ".join(str(q or "").split())
    if asset not in ASSETS:
        raise ValueError("asset must be cards, sealed or graded")
    if len(query) < SEARCH_MIN_QUERY_LENGTH:
        raise ValueError(f"q must be at least {SEARCH_MIN_QUERY_LENGTH} characters")
    if not 1 <= int(limit) <= SEARCH_MAX_LIMIT:
        raise ValueError(f"limit must be 1..{SEARCH_MAX_LIMIT}")
    return asset, query[:120], int(limit)


def search_catalog(client: Any, asset: str, q: str, limit: int = 20) -> list[dict[str, Any]]:
    asset, query, limit = validate_search_request(asset, q, limit)
    try:
        rows = _timed_read("catalog_search", lambda: _rows(client.rpc(
            SEARCH_RPC_V1, {"p_asset": asset, "p_query": query, "p_limit": limit}).execute()),
            asset=asset, limit=limit)
    except Exception as exc:
        if _is_rpc_missing(exc):
            raise SurfaceV2Error("CATALOG_SEARCH_UNAVAILABLE", "catalog search authority not installed") from exc
        raise SurfaceV2Error("CATALOG_SEARCH_FAILED", str(exc)) from exc
    return rows[:limit]


# ---------------------------------------------------------------------------
# V2-first / V1-fallback cutover entry points used by the API routes.
# ---------------------------------------------------------------------------

def read_directory_v2_first(client: Any) -> list[dict[str, Any]]:
    from backend.db.services.market_explorer_prepared_directory import read_prepared_directory
    v2 = read_v2_directory(client)
    if v2 is None:
        return read_prepared_directory(client)
    # Legacy prepared identities resolve server-side: each row publishes the
    # generation-scoped aliases that map to it, so deep links / saved selections
    # using an old key still land on the canonical market. React holds no table.
    aliases = read_aliases(client, str(v2[0]["generation_id"]))
    by_market: dict[str, list[str]] = {}
    for alias, market in aliases.items():
        by_market.setdefault(market, []).append(alias)
    return [{**row, "legacy_aliases": sorted(by_market.get(row["market_key"], []))} for row in v2]


def read_comparison_v2_first(client: Any, keys: list[str], start_date: str | None = None) -> dict[str, Any]:
    from backend.db.services.market_explorer_prepared_directory import read_prepared_comparison_bundle
    v2 = read_v2_directory(client)
    if v2 is None:
        return read_prepared_comparison_bundle(client, keys, start_date)
    return read_v2_comparison_bundle(client, v2, keys, start_date)


def read_constituents_v2_first(client: Any, market_key: str, generation_id: str,
                               after_rank: int = 0, limit: int = 100) -> dict[str, Any]:
    from backend.db.services.market_explorer_prepared_directory import read_prepared_constituents
    v2 = read_v2_directory(client)
    if v2 is None:
        return read_prepared_constituents(client, market_key, generation_id, after_rank, limit)
    return read_v2_constituents(client, v2, market_key, generation_id, after_rank, limit)


def read_comparison_v2_bundle_key(client: Any, directory: list[dict[str, Any]], key: str) -> str | None:
    """Canonical market a requested key resolves to (comparison's own resolver)."""
    aliases = read_aliases(client, str(directory[0]["generation_id"]))
    resolved = resolve_requested_keys([key], {row["market_key"] for row in directory}, aliases)
    return resolved.get(key)
