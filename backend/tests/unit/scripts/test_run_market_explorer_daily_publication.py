"""Focused tests for the V2-only Market Explorer daily orchestrator."""
from __future__ import annotations

import ast
import inspect
from datetime import date
from unittest.mock import patch

from backend.scripts import run_market_explorer_daily_publication as orch


class _Response:
    def __init__(self, data):
        self.data = data


class _Rpc:
    def __init__(self, client, name, params):
        self.client = client
        self.name = name
        self.params = params

    def execute(self):
        self.client.calls.append((self.name, dict(self.params)))
        return _Response(self.client.responses.get(self.name, 0))


class _Client:
    def __init__(self):
        self.calls: list[tuple[str, dict]] = []
        self.responses = {orch.INVALIDATE_CACHE_SCOPED_RPC: 3}

    def rpc(self, name, params):
        return _Rpc(self, name, params)


def test_normal_day_not_ready_is_a_noop():
    with patch.object(orch, "resolve_latest_approved_market_date", return_value=None), \
         patch.object(orch, "run_publish") as mock_publish:
        result = orch.run_daily_publication(object(), commit=True)
    assert result["status"] == "not_ready"
    mock_publish.assert_not_called()


def test_normal_day_has_one_projection_phase_and_it_is_v2(monkeypatch):
    projection = {
        "dry_run": False,
        "sets_attempted": 165,
        "sets_reconciliation_failed": 0,
        "failures": 0,
    }
    monkeypatch.setattr(orch, "resolve_latest_approved_market_date", lambda *_a: "2026-09-10")
    monkeypatch.setattr(orch, "market_date_is_approved", lambda *_a, **_k: True)
    monkeypatch.setattr(
        orch,
        "refresh_current_metadata",
        lambda *_a, **_k: orch.MetadataRefreshReport(expected_row_count=34228),
    )
    monkeypatch.setattr(orch, "resolve_tracked_set_ids", lambda *_a: ["set-a", "set-b"])
    calls = []

    def fake_publish(_client, **kwargs):
        calls.append(kwargs)
        return projection

    monkeypatch.setattr(orch, "run_publish", fake_publish)
    with patch.object(orch, "advance_v2_daily_shadow") as obsolete_second_phase:
        result = orch.run_daily_publication(object(), commit=True)

    assert result["status"] == "ok"
    assert result["market_date"] == "2026-09-10"
    assert len(calls) == 1
    assert calls[0]["commit"] is True
    assert calls[0]["through_date"] == date(2026, 9, 10)
    assert result["projection"] == projection
    assert result["v2_projection"] == projection
    assert result["caches"] == {
        "status": "deferred",
        "reason": "separate_operational_worker",
    }
    obsolete_second_phase.assert_not_called()


def test_normal_day_fails_closed_on_any_v2_projection_failure(monkeypatch):
    monkeypatch.setattr(orch, "market_date_is_approved", lambda *_a, **_k: True)
    monkeypatch.setattr(
        orch,
        "refresh_current_metadata",
        lambda *_a, **_k: orch.MetadataRefreshReport(expected_row_count=34228),
    )
    monkeypatch.setattr(orch, "resolve_tracked_set_ids", lambda *_a: ["set-a"])
    monkeypatch.setattr(
        orch,
        "run_publish",
        lambda *_a, **_k: {
            "failures": 1,
            "sets_reconciliation_failed": 0,
        },
    )

    result = orch.run_daily_publication(
        object(), commit=True, market_date="2026-09-10",
    )
    assert result["status"] == "projection_failed"
    assert "verified V2" in result["error"]
    assert result["caches"] is None


def test_historical_repair_force_rebuilds_bounded_v2_and_invalidates_cache(monkeypatch):
    client = _Client()
    seen = []
    monkeypatch.setattr(orch, "market_date_is_approved", lambda *_a, **_k: True)

    def fake_publish(_client, **kwargs):
        seen.append(kwargs)
        return {
            "failures": 0,
            "sets_reconciliation_failed": 0,
            "reports": [{
                "set_id": "set-a",
                "expected_rows": 25,
                "actual_rows": 25,
                "reconciled": True,
                "coverage_after": {
                    "set_id": "set-a",
                    "retained_from": "2026-06-03",
                    "computed_through": "2026-09-10",
                },
            }],
        }

    monkeypatch.setattr(orch, "run_publish", fake_publish)
    monkeypatch.setattr(
        orch,
        "deferred_cache_report",
        lambda *_a, **_k: {
            "status": "deferred",
            "reason": "separate_operational_worker",
            "affected": ["fp-a"],
        },
    )

    result = orch.run_historical_repair(
        client,
        commit=True,
        set_ids=["set-a"],
        repair_start=date(2026, 7, 1),
        repair_through=date(2026, 9, 10),
    )

    assert result["status"] == "ok"
    assert result["reconciled"] is True
    assert result["expected_rows"] == result["actual_rows"] == 25
    assert seen[0]["force_rebuild"] is True
    assert seen[0]["retention_days"] == orch.V2_RETENTION_DAYS
    assert client.calls == [(
        orch.INVALIDATE_CACHE_SCOPED_RPC,
        {"p_set_ids": ["set-a"]},
    )]


def test_historical_repair_does_not_invalidate_on_v2_failure(monkeypatch):
    client = _Client()
    monkeypatch.setattr(orch, "market_date_is_approved", lambda *_a, **_k: True)
    monkeypatch.setattr(
        orch,
        "run_publish",
        lambda *_a, **_k: {
            "failures": 1,
            "sets_reconciliation_failed": 0,
            "reports": [],
        },
    )

    result = orch.run_historical_repair(
        client,
        commit=True,
        set_ids=["set-a"],
        repair_start=date(2026, 7, 1),
        repair_through=date(2026, 9, 10),
    )
    assert result["status"] == "reconciliation_failed"
    assert client.calls == []


def test_cache_build_is_always_deferred_from_daily_publisher():
    assert orch.deferred_cache_report() == {
        "status": "deferred",
        "reason": "separate_operational_worker",
    }


def test_runtime_module_contains_no_exact_retired_v1_relation_literals():
    tree = ast.parse(inspect.getsource(orch))
    strings = {
        node.value for node in ast.walk(tree)
        if isinstance(node, ast.Constant) and isinstance(node.value, str)
    }
    assert "pokemon_market_explorer_card_daily_states" not in strings
    assert "pokemon_market_explorer_card_daily_coverage" not in strings
    assert "pokemon_card_variant_market_price_intervals" not in strings
