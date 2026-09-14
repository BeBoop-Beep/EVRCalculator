from __future__ import annotations

import ast
import inspect
from datetime import date

import pytest

from backend.scripts import publish_market_explorer_daily_projection as pub


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
        return _Response(self.client.responses.get(self.name, {}))


class _Client:
    def __init__(self):
        self.calls: list[tuple[str, dict]] = []
        self.responses = {
            pub.V2_PUBLISH_RPC: {
                "status": "verified",
                "reconciled": True,
                "expected_rows": 10,
                "actual_rows": 10,
                "mode": "advanced",
            },
            pub.V2_VERIFY_RPC: {
                "reconciled": True,
                "expected_rows": 10,
                "actual_rows": 10,
            },
        }

    def rpc(self, name, params):
        return _Rpc(self, name, params)


def test_publish_set_v2_calls_only_verified_v2_rpc():
    client = _Client()
    result = pub.publish_set_v2(
        client,
        set_id="set-a",
        through_date="2026-09-10",
        retention_days=100,
        force_rebuild=True,
    )
    assert result["status"] == "verified"
    assert result["reconciled"] is True
    assert client.calls == [(
        pub.V2_PUBLISH_RPC,
        {
            "p_set_id": "set-a",
            "p_through_date": "2026-09-10",
            "p_retention_days": 100,
            "p_force_rebuild": True,
        },
    )]


def test_publish_set_v2_rejects_unverified_response():
    client = _Client()
    client.responses[pub.V2_PUBLISH_RPC] = {
        "status": "advanced",
        "reconciled": False,
    }
    with pytest.raises(RuntimeError, match="unverified"):
        pub.publish_set_v2(
            client,
            set_id="set-a",
            through_date="2026-09-10",
        )


def test_verify_set_v2_uses_v2_verifier_rpc():
    client = _Client()
    result = pub.verify_set_v2(
        client,
        set_id="set-a",
        through_date="2026-09-10",
    )
    assert result["reconciled"] is True
    assert client.calls[0][0] == pub.V2_VERIFY_RPC


def test_run_publish_dry_run_performs_no_v2_write(monkeypatch):
    monkeypatch.setattr(pub, "load_approved_dates", lambda *_a, **_k: ["2026-09-10"])
    monkeypatch.setattr(pub, "load_set_ids", lambda *_a, **_k: ["set-a", "set-b"])
    calls = []

    def fake_process(_client, *, commit, set_id, through_date, **_kwargs):
        calls.append((commit, set_id, through_date))
        return pub.SetReport(set_id=set_id, mode="up_to_date")

    monkeypatch.setattr(pub, "process_set", fake_process)
    report = pub.run_publish(object(), commit=False, through_date=date(2026, 9, 10))

    assert report["dry_run"] is True
    assert report["sets_attempted"] == 2
    assert report["failures"] == 0
    assert calls == [
        (False, "set-a", "2026-09-10"),
        (False, "set-b", "2026-09-10"),
    ]


def test_run_publish_commit_requires_reconciled_v2_for_every_set(monkeypatch):
    monkeypatch.setattr(pub, "load_approved_dates", lambda *_a, **_k: ["2026-09-10"])
    monkeypatch.setattr(pub, "load_set_ids", lambda *_a, **_k: ["set-a", "set-b"])

    def fake_process(_client, *, set_id, **_kwargs):
        return pub.SetReport(
            set_id=set_id,
            mode="advanced",
            expected_rows=10,
            actual_rows=10,
            reconciled=(set_id == "set-a"),
        )

    monkeypatch.setattr(pub, "process_set", fake_process)
    report = pub.run_publish(object(), commit=True, through_date=date(2026, 9, 10))

    assert report["sets_attempted"] == 2
    assert report["sets_reconciliation_failed"] == 1
    assert report["failures"] == 0


def test_run_publish_reports_per_set_rpc_failure(monkeypatch):
    monkeypatch.setattr(pub, "load_approved_dates", lambda *_a, **_k: ["2026-09-10"])
    monkeypatch.setattr(pub, "load_set_ids", lambda *_a, **_k: ["set-a", "set-b"])

    def fake_process(_client, *, set_id, **_kwargs):
        if set_id == "set-b":
            raise RuntimeError("reconciliation failed")
        return pub.SetReport(set_id=set_id, mode="advanced", reconciled=True)

    monkeypatch.setattr(pub, "process_set", fake_process)
    report = pub.run_publish(object(), commit=True, through_date=date(2026, 9, 10))

    assert report["sets_attempted"] == 2
    assert report["failures"] == 1
    assert len(report["reports"]) == 1


def test_run_publish_fails_closed_when_requested_date_is_not_approved(monkeypatch):
    monkeypatch.setattr(pub, "load_approved_dates", lambda *_a, **_k: ["2026-09-09"])
    report = pub.run_publish(object(), commit=True, through_date=date(2026, 9, 10))
    assert report["failures"] == 1
    assert report["sets_attempted"] == 0


def test_runtime_module_contains_no_exact_retired_v1_relation_literals():
    tree = ast.parse(inspect.getsource(pub))
    string_literals = {
        node.value for node in ast.walk(tree)
        if isinstance(node, ast.Constant) and isinstance(node.value, str)
    }
    assert "pokemon_market_explorer_card_daily_states" not in string_literals
    assert "pokemon_market_explorer_card_daily_coverage" not in string_literals
    assert "pokemon_card_variant_market_price_intervals" not in string_literals
