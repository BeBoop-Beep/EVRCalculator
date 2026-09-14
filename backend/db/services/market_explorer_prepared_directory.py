"""Read-only Phase-5 prepared Market Explorer serving adapter."""
from __future__ import annotations

from threading import Lock
import time
from typing import Any

DIRECTORY_RPC = "get_pokemon_market_explorer_prepared_directory_v1"
COMPARISON_RPC = "get_pokemon_market_explorer_prepared_comparison_v1"
HISTORY_RPC = "get_pokemon_market_explorer_prepared_history_v1"
SCREEN_RPC = "get_pokemon_market_explorer_prepared_screen_v1"
CONTEXT_RPC = "get_pokemon_market_explorer_set_context_ranking_v1"
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


def read_prepared_history(client: Any, market_keys: list[str], start_date: str | None = None) -> list[dict[str, Any]]:
    if not 1 <= len(market_keys) <= MAX_MARKETS:
        raise ValueError("prepared history requires 1..25 market keys")
    return _rows(client.rpc(HISTORY_RPC, {"p_market_keys": market_keys, "p_start_date": start_date}).execute())


def read_prepared_screen(client: Any, screen_key: str, asset: str | None, limit: int) -> list[dict[str, Any]]:
    return _rows(client.rpc(SCREEN_RPC, {"p_screen_key": screen_key, "p_asset": asset, "p_limit": limit}).execute())


def read_set_context_ranking(client: Any, set_id: str, ranking: str, timeframe: str, limit: int, as_of: str | None) -> dict[str, Any]:
    data = client.rpc(CONTEXT_RPC, {"p_set_id": set_id, "p_ranking": ranking, "p_timeframe": timeframe, "p_limit": limit, "p_as_of": as_of}).execute().data
    return dict(data or {})
