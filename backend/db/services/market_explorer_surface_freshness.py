"""Compact read-only adapter for the database-owned Explorer freshness state."""

from __future__ import annotations

from typing import Any

FRESHNESS_RPC = "get_pokemon_market_explorer_surface_freshness_v2"


def read_surface_freshness(client: Any) -> dict[str, Any]:
    data = client.rpc(FRESHNESS_RPC, {}).execute().data
    if isinstance(data, list):
        data = data[0] if data else {}
    return dict(data or {})
