"""Exact Basket V2 adapter over the canonical qualified-leaf RPC."""

from __future__ import annotations

from typing import Any, Mapping, Sequence

from backend.domain.pokemon.market_explorer_query import (
    MEMBERSHIP_EXPLICIT, build_chain_linked_history_from_cohorts,
    normalize_query_spec, query_fingerprint, query_key,
)
from backend.domain.pokemon.market_index import compute_strict_window_movements

EXACT_BASKET_RPC = "get_pokemon_market_explorer_explicit_basket_series_v2"
EXACT_BASKET_SERVICE_VERSION = "pokemon-market-explorer-exact-basket-v2"
EXACT_BASKET_METHODOLOGY_VERSION = "pokemon-qualified-leaf-one-unit-v1"


class MarketExplorerExactBasketUnavailable(RuntimeError):
    pass


def run_exact_basket_v2(
    client: Any, *, instruments: Sequence[Mapping[str, str]],
    start_date: str | None = None, end_date: str | None = None,
) -> dict[str, Any]:
    rows = list(client.rpc(EXACT_BASKET_RPC, {
        "p_instruments": [dict(item) for item in instruments],
        "p_start_date": start_date,
        "p_end_date": end_date,
    }).execute().data or [])
    if not rows:
        raise MarketExplorerExactBasketUnavailable("Exact Basket has no coherent priced history")
    terminal = rows[-1]
    if terminal.get("status") == "unavailable" or not terminal.get("basket_as_of"):
        raise MarketExplorerExactBasketUnavailable("Exact Basket has no common priced date")

    cohorts = [{
        "marketDate": row.get("market_date"),
        "basketValue": row.get("basket_value"),
        "commonCount": row.get("common_instrument_count"),
        "commonCurrentValue": row.get("common_current_value"),
        "commonPreviousValue": row.get("common_previous_value"),
        "constituentCount": row.get("priced_instrument_count"),
        "eligibleUniverseCount": row.get("selected_instrument_count"),
    } for row in rows if row.get("market_date")]
    history = build_chain_linked_history_from_cohorts(cohorts)
    if not history:
        raise MarketExplorerExactBasketUnavailable("Exact Basket has no coherent priced history")
    current_segment = history[-1]["chainSegmentId"]
    current = [row for row in history if row["chainSegmentId"] == current_segment]
    index_points = [{"date": row["marketDate"], "value": row["normalizedIndexValue"]} for row in current]
    basket_points = [{"date": row["marketDate"], "value": row["basketValue"]} for row in current]
    constituents = list(terminal.get("current_constituents") or [])
    basket_as_of = str(terminal["basket_as_of"])[:10]
    spec = normalize_query_spec(mode="all", membership_mode=MEMBERSHIP_EXPLICIT,
                                instruments=instruments)
    return {
        "queryFingerprint": query_fingerprint(spec),
        "queryKey": query_key(spec),
        "displayLabel": f"Exact Basket · {len(spec['instruments'])} items",
        "spec": spec,
        "asOf": basket_as_of,
        "basketAsOf": basket_as_of,
        "comparisonAsOf": str(terminal.get("comparison_as_of") or basket_as_of)[:10],
        "status": terminal.get("status"),
        "historyStartDate": current[0]["marketDate"],
        "indexValue": float(current[-1]["normalizedIndexValue"]),
        "trackedValue": float(terminal["basket_value"]),
        "familyChanges": compute_strict_window_movements(index_points),
        "trackedValueChanges": compute_strict_window_movements(basket_points),
        "trend": [[row["marketDate"], row["normalizedIndexValue"]] for row in current],
        "trackedValueHistory": basket_points,
        "currentConstituents": constituents,
        "membershipByDate": [{
            "marketDate": basket_as_of,
            "constituentIds": [f"{item.get('asset')}:{item.get('instrumentId')}" for item in constituents],
        }],
        "reconciliation": {
            "actualConstituentCount": len(constituents),
            "eligibleUniverseCount": int(terminal.get("selected_instrument_count") or 0),
            "currentBasketValue": float(terminal["basket_value"]),
        },
        "metadata": {
            "oneUnitPerLeaf": True,
            "observationCount": len(history),
            "currentSegmentId": current_segment,
            "chainSegmentCount": len({row["chainSegmentId"] for row in history}),
            "seriesPath": "qualifiedExplicitBasketV2",
            "serviceVersion": EXACT_BASKET_SERVICE_VERSION,
            "instrumentMethodologyVersion": EXACT_BASKET_METHODOLOGY_VERSION,
        },
    }
