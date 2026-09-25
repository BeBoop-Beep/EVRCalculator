"""Bounded prepared reads and canonical one-root publication repair.

No history is rebuilt here. A mismatched dashboard watermark is preserved so
that the global snapshot's existing date/availability checks can reject it.
"""
from __future__ import annotations

from collections.abc import Mapping, Sequence
from typing import Any

COMPOSITE_REPAIR_RPC = "repair_pokemon_market_composite_root_set_value_day_v1"
LEGACY_REPAIR_RPC = "refresh_pokemon_set_value_daily_history"
INDEX_READ_CHUNK = 20
INDEX_SUMMARY_FIELDS = (
    "set_id,window_key,latest_market_date,"
    "index_as_of:payload_json->cardsMarket->marketIndex->asOf,"
    "index_value:payload_json->cardsMarket->marketIndex->currentValue,"
    "index_base:payload_json->cardsMarket->marketIndex->baseValue,"
    "index_movements:payload_json->cardsMarket->marketIndex->movements"
)


def load_compact_market_index_summaries(
    client: Any, set_ids: Sequence[str]
) -> list[dict[str, Any]]:
    """Read only prepared index scalars/movements, never the large histories."""
    ids = sorted({str(value) for value in set_ids if value})
    result: list[dict[str, Any]] = []
    for offset in range(0, len(ids), INDEX_READ_CHUNK):
        response = (
            client.table("pokemon_set_market_dashboard_snapshot_latest")
            .select(INDEX_SUMMARY_FIELDS)
            .eq("window_key", "365d")
            .in_("set_id", ids[offset:offset + INDEX_READ_CHUNK])
            .execute()
        )
        for row in response.data or []:
            result.append({
                "set_id": row.get("set_id"),
                "window_key": row.get("window_key"),
                "latest_market_date": row.get("latest_market_date"),
                "cardsMarket": {"marketIndex": {
                    "asOf": row.get("index_as_of"),
                    "currentValue": row.get("index_value"),
                    "baseValue": row.get("index_base"),
                    "movements": row.get("index_movements"),
                }},
            })
    return result


def refresh_market_root_day(client: Any, set_id: str, market_date: str) -> Any:
    """Route counted-subset parents to the canonical writer, failing closed.

    The caller owns transient retries and the post-write coverage check. The
    canonical RPC itself enforces current-day promoted scrape authority, full
    priceability, the advisory lock and an atomic frozen constituent roster.
    Never fall back to the direct-only legacy writer after a canonical failure.
    """
    children = (
        client.table("sets").select("id")
        .eq("parent_opening_set_id", set_id)
        .eq("counts_toward_parent_set_value", True)
        .limit(1).execute()
    ).data or []
    if children:
        response = client.rpc(COMPOSITE_REPAIR_RPC, {
            "p_root_set_id": set_id, "p_market_date": market_date,
        }).execute()
        receipt = response.data
        if not isinstance(receipt, Mapping) or receipt.get("status") not in {
            "repaired", "already_current"
        }:
            raise RuntimeError("canonical composite root repair returned no accepted receipt")
        if receipt.get("setId") != set_id or receipt.get("marketDate") != market_date:
            raise RuntimeError("canonical composite root repair returned mismatched authority")
        return response
    return client.rpc(LEGACY_REPAIR_RPC, {
        "p_set_id": set_id, "p_start_date": market_date, "p_end_date": market_date,
    }).execute()
