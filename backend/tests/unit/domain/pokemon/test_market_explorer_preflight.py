"""Regression tests for the Filtered Cards preflight RPC translation layer.

These are pure translation tests -- no database, no network -- exercising
backend/domain/pokemon/market_explorer_preflight.py against representative
rows shaped like backend/db/migrations/20260910204843_optimize_market_explorer_filtered_cards_preflight.sql's
`preflight_status` outputs.
"""

from __future__ import annotations

import pytest

from backend.domain.pokemon.market_explorer_preflight import (
    PREFLIGHT_CURRENT_ONLY,
    PREFLIGHT_EMPTY,
    PREFLIGHT_HISTORY_UNAVAILABLE,
    PREFLIGHT_PROJECTION_LAGGING,
    PREFLIGHT_READY,
    PREFLIGHT_RPC_NAME,
    PREFLIGHT_UNKNOWN,
    MarketExplorerPreflightError,
    call_filtered_cards_preflight,
    resolve_query_outcome_for_preflight,
    translate_preflight_row,
)


def _row(**overrides):
    base = {
        "matching_constituent_count": 15,
        "matching_set_count": 3,
        "comparison_as_of": "2026-09-09",
        "previous_approved_market_date": "2026-09-08",
        "previous_matching_constituent_count": 15,
        "previous_matching_set_count": 3,
        "common_constituent_count": 15,
        "current_chain_link_ready": True,
        "scope_set_count": 3,
        "scope_projection_ready_set_count": 3,
        "scope_projection_missing_set_count": 0,
        "scope_projection_ready": True,
        "history_probe_projection_ready": True,
        "projection_retained_from": "2026-01-01",
        "projection_computed_through": "2026-09-10",
        "preflight_status": "ready",
    }
    base.update(overrides)
    return base


def test_preflight_ready_maps_correctly():
    result = translate_preflight_row(_row())
    assert result["readiness"] == PREFLIGHT_READY
    assert result["queryOutcome"] is None
    assert result["matchingConstituentCount"] == 15
    assert result["matchingSetCount"] == 3
    assert result["currentChainLinkReady"] is True
    assert resolve_query_outcome_for_preflight(_row()) is None


def test_preflight_empty_maps_correctly():
    row = _row(
        preflight_status="empty",
        matching_constituent_count=0,
        matching_set_count=0,
        current_chain_link_ready=False,
    )
    result = translate_preflight_row(row)
    assert result["readiness"] == PREFLIGHT_EMPTY
    assert result["queryOutcome"] == "QUERY_EMPTY_NOW"
    assert result["matchingConstituentCount"] == 0


def test_projection_lag_does_not_report_as_zero_matches():
    # A lagging V2 projection returns null counts from the RPC (see the
    # optimized migration's `case when r.scope_projection_ready then ... else
    # null end`), and must map to an explicit unavailable/readiness outcome,
    # never to QUERY_EMPTY_NOW.
    row = _row(
        preflight_status="projection_lagging",
        matching_constituent_count=None,
        matching_set_count=None,
        scope_projection_ready=False,
        scope_projection_ready_set_count=1,
        scope_projection_missing_set_count=2,
    )
    result = translate_preflight_row(row)
    assert result["readiness"] == PREFLIGHT_PROJECTION_LAGGING
    assert result["queryOutcome"] == "QUERY_UNAVAILABLE"
    assert result["queryOutcome"] != "QUERY_EMPTY_NOW"
    assert result["matchingConstituentCount"] is None


def test_membership_without_usable_history_maps_to_no_history_family():
    row = _row(preflight_status="current_only", previous_matching_constituent_count=0,
               common_constituent_count=0, current_chain_link_ready=False)
    result = translate_preflight_row(row)
    assert result["readiness"] == PREFLIGHT_CURRENT_ONLY
    assert result["queryOutcome"] == "QUERY_NO_HISTORY"


def test_history_probe_unavailable_maps_to_unavailable_not_empty():
    row = _row(preflight_status="history_probe_unavailable")
    result = translate_preflight_row(row)
    assert result["readiness"] == PREFLIGHT_HISTORY_UNAVAILABLE
    assert result["queryOutcome"] == "QUERY_UNAVAILABLE"


def test_unmapped_sql_status_degrades_to_unknown_unavailable_not_ready():
    row = _row(preflight_status="some_future_status_not_yet_mapped")
    result = translate_preflight_row(row)
    assert result["readiness"] == PREFLIGHT_UNKNOWN
    assert result["queryOutcome"] == "QUERY_UNAVAILABLE"


def test_non_mapping_row_raises():
    with pytest.raises(MarketExplorerPreflightError):
        translate_preflight_row(["not", "a", "mapping"])


class _FakeRpcCall:
    def __init__(self, rows):
        self._rows = rows

    def execute(self):
        return type("Response", (), {"data": self._rows})()


class _FakeSupabaseClient:
    """Records the exact RPC name/params call_filtered_cards_preflight makes."""

    def __init__(self, rows):
        self._rows = rows
        self.calls = []

    def rpc(self, name, params):
        self.calls.append((name, params))
        return _FakeRpcCall(self._rows)


def test_call_filtered_cards_preflight_invokes_the_correct_rpc_with_sorted_params():
    client = _FakeSupabaseClient([_row()])
    result = call_filtered_cards_preflight(
        client,
        set_ids=["set-b", "set-a"],
        segment_ids=["sir"],
        comparison_as_of="2026-09-09",
    )
    assert len(client.calls) == 1
    name, params = client.calls[0]
    assert name == PREFLIGHT_RPC_NAME
    assert params["p_set_ids"] == ["set-a", "set-b"]
    assert params["p_segment_ids"] == ["sir"]
    assert params["p_pokemon_ids"] is None
    assert params["p_comparison_as_of"] == "2026-09-09"
    assert result["readiness"] == PREFLIGHT_READY


def test_call_filtered_cards_preflight_raises_on_empty_rpc_response():
    client = _FakeSupabaseClient([])
    with pytest.raises(MarketExplorerPreflightError):
        call_filtered_cards_preflight(client, set_ids=["set-a"])
