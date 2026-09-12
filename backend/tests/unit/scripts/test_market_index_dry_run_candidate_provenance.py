"""Phase 5/7: dry-run must accept candidate provenance; commit must require FINAL.

Six scenarios:
1. dry-run + candidate provenance -> success, provenanceState=candidate, zero writes
2. dry-run + generic/member-only rows -> rejected (not materialized)
3. dry-run + incomplete candidate pairs (one scope missing) -> rejected
4. commit + candidate-only initially -> finalizer invoked, then FINAL re-required
5. commit + already-FINAL -> no redundant finalizer call
6. commit + finalization fails (still not FINAL after finalizer) -> write blocked
"""
from __future__ import annotations

import pytest

import backend.scripts.build_pokemon_market_index_history as index_history
from backend.db.services.price_storage_v2_integration import public_root_materialization

DAY = "2026-09-10"
ROOT = "root-1"


def _final_row(scope):
    source = "canonical_root_set_public_rollout_v1" if scope == "standard" else "canonical_root_top10_public_rollout_v1"
    return {"set_id": ROOT, "value_scope": scope, "snapshot_date": DAY, "source": source}


def _candidate_row(scope):
    source = ("canonical_root_set_public_rollout_candidate_v1" if scope == "standard"
              else "canonical_root_top10_public_rollout_candidate_v1")
    return {"set_id": ROOT, "value_scope": scope, "snapshot_date": DAY, "source": source}


def _generic_row(scope):
    return {"set_id": ROOT, "value_scope": scope, "snapshot_date": DAY, "source": "member_price_storage_v2_generic"}


# ---- Unit-level: public_root_materialization contract ----

def test_dry_run_candidate_provenance_accepted():
    rows = [_candidate_row("standard"), _candidate_row("top10")]
    result = public_root_materialization([ROOT], rows, DAY, allow_candidate=True)
    assert result["ready"] is True
    assert result["provenanceState"] == "candidate"


def test_dry_run_generic_member_only_rows_rejected():
    rows = [_generic_row("standard"), _generic_row("top10")]
    result = public_root_materialization([ROOT], rows, DAY, allow_candidate=True)
    assert result["ready"] is False
    assert result["provenanceState"] == "none"


def test_dry_run_incomplete_candidate_pair_rejected():
    rows = [_candidate_row("standard")]  # top10 missing
    result = public_root_materialization([ROOT], rows, DAY, allow_candidate=True)
    assert result["ready"] is False
    assert ["root-1", "top10"] in result["missingRootScopePairs"]


def test_commit_mode_rejects_candidate_provenance_by_default():
    rows = [_candidate_row("standard"), _candidate_row("top10")]
    result = public_root_materialization([ROOT], rows, DAY, allow_candidate=False)
    assert result["ready"] is False


def test_commit_mode_accepts_final_provenance():
    rows = [_final_row("standard"), _final_row("top10")]
    result = public_root_materialization([ROOT], rows, DAY, allow_candidate=False)
    assert result["ready"] is True
    assert result["provenanceState"] == "final"


# ---- Orchestration-level: build()'s finalizer invocation contract ----

class _Result:
    def __init__(self, data):
        self.data = data


class _RPC:
    def __init__(self, client, name, payload):
        self._client, self._name, self._payload = client, name, payload

    def execute(self):
        self._client.rpc_calls.append((self._name, self._payload))
        return _Result({"status": "ok"})


class _FakeClient:
    """Client whose materialization outcome is scripted per-call."""

    def __init__(self, materializations):
        self.materializations = list(materializations)
        self.rpc_calls = []

    def rpc(self, name, payload):
        return _RPC(self, name, payload)


@pytest.fixture(autouse=True)
def _stub_row_building(monkeypatch):
    monkeypatch.setattr(index_history, "build_rollout_market_index_rows", lambda *_a, **_k: [])
    monkeypatch.setattr(index_history, "persist_rollout_market_index_rows", lambda *_a, **_k: 0)
    monkeypatch.setattr(index_history, "resolve_market_root_cohort", lambda *_a, **_k: [])


def _scripted_materialization(monkeypatch, outcomes):
    calls = []

    def fake(client, market_date, *, allow_candidate=False):
        calls.append(allow_candidate)
        return outcomes[len(calls) - 1]

    monkeypatch.setattr(index_history, "_rollout_source_materialization", fake)
    return calls


def _ready(provenance_state):
    return {"ready": True, "provenanceState": provenance_state, "missingRootScopePairs": [],
            "duplicatePairs": [], "rootCount": 1, "materializedPairCount": 2}


def _not_ready(provenance_state="none"):
    return {"ready": False, "provenanceState": provenance_state, "missingRootScopePairs": [["root-1", "top10"]],
            "duplicatePairs": [], "rootCount": 1, "materializedPairCount": 0}


def test_commit_candidate_only_invokes_finalizer_then_rechecks_final(monkeypatch):
    calls = _scripted_materialization(monkeypatch, [_not_ready("candidate"), _ready("final")])
    client = _FakeClient([])
    result = index_history.build(client, market_date=DAY, commit=True)
    assert calls == [False, False]
    assert client.rpc_calls and client.rpc_calls[0][0] == index_history.ROLLOUT_REFRESH_RPC
    assert result["rolloutRefresh"] is not None


def test_commit_already_final_no_redundant_finalizer_call(monkeypatch):
    calls = _scripted_materialization(monkeypatch, [_ready("final")])
    client = _FakeClient([])
    index_history.build(client, market_date=DAY, commit=True)
    assert calls == [False]
    assert client.rpc_calls == []


def test_commit_finalization_fails_write_blocked(monkeypatch):
    _scripted_materialization(monkeypatch, [_not_ready("candidate"), _not_ready("candidate")])
    client = _FakeClient([])
    with pytest.raises(RuntimeError):
        index_history.build(client, market_date=DAY, commit=True)
