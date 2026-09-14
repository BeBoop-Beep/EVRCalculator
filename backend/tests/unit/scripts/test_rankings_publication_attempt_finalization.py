"""Reproduces the live Sept-8 incident and proves it is now structurally
impossible: a Rankings publication that actually commits must always leave
its triggering `pokemon_rankings_publication_attempts` row terminal.

Ground truth from the incident:
  * attempt `fd215ea3-...` was started (status `evaluating`, reason `READY`)
  * ~1 minute later publication `85d7ce0b-...` was written successfully
  * the attempt row was NEVER finalized - `completed_at` stayed NULL and
    `resulting_publication_id` stayed NULL forever.

These tests exercise `publish_explore_rip_rankings_snapshot` end-to-end
against a fake Supabase-shaped client that DOES support the
`pokemon_rankings_publication_attempts` table (so
`_rankings_lifecycle_persistence_supported` reports lifecycle persistence is
available, exactly like the real client), and assert that every exit path -
success, RPC failure, and post-publication parity failure - leaves the
attempt row terminal with `completed_at` set. Readiness is stubbed to a
canned READY report so the test is about attempt finalization, not about the
readiness gate's own content (which is covered by
test_rankings_publication_lifecycle.py).
"""

from __future__ import annotations

import pytest

from backend.db.services.rankings_publication_lifecycle import (
    RankingsReadinessReport,
    READY,
)
from backend.scripts import pokemon_explore_rankings_publisher as command


class _Query:
    def __init__(self, client, name):
        self.client = client
        self.name = name
        self.rows = list(client.tables.setdefault(name, []))
        self._pending_update = None

    def select(self, *_args):
        return self

    def eq(self, key, value):
        self.rows = [row for row in self.rows if str(row.get(key)) == str(value)]
        return self

    def order(self, *_args, **_kwargs):
        return self

    def limit(self, count):
        self.rows = self.rows[:count]
        return self

    def range(self, *_args):
        return self

    def insert(self, row):
        self.client.tables[self.name].append(dict(row))
        self.rows = [row]
        return self

    def update(self, values):
        # Real PostgREST-style builders apply the filter (`.eq(...)`) that
        # follows `.update(...)` before the write actually commits - so this
        # only RECORDS the pending values here and applies them to whatever
        # `self.rows` narrows down to by the time `.execute()` runs.
        self._pending_update = values
        return self

    def execute(self):
        if self._pending_update is not None:
            for row in self.rows:
                row.update(self._pending_update)
        return type("Result", (), {"data": self.rows})()


class FakeClient:
    """Minimal Supabase-shaped fake that supports the attempts table, so
    `_rankings_lifecycle_persistence_supported` reports True exactly like it
    would for a real client."""

    def __init__(self, *, rpc_exception=None, parity_ok=True):
        self._tables = {
            "pokemon_rankings_publication_attempts": [],
            "pokemon_public_rip_leaderboard_snapshots": [],
            "pokemon_explore_rankings_snapshot_latest": [],
            "pokemon_set_chase_accessibility_snapshot_latest": [],
        }
        self.tables = self._tables
        self.rpc_calls = []
        self.rpc_exception = rpc_exception
        self.parity_ok = parity_ok

    def table(self, name):
        return _Query(self, name)

    def rpc(self, name, params):
        self.rpc_calls.append((name, params))
        if self.rpc_exception is not None:
            raise self.rpc_exception
        return _Query(self, "__rpc_noop__")


def _row():
    return {"ranking_payload_json": {
        "targets": [{"set_id": "set-0", "canonical_key": "set-0",
                     "overallRipV12": {"rank": 1, "score": 10}}],
        "meta": {
            "comparisonSnapshots": {"currentMarketDate": "2026-09-08"},
            "snapshot": {"builtAt": "2026-09-08T08:00:00Z"},
            "publicAnalyticsCohort": {"version": "cohort-v1", "eligibleSetCount": 1,
                                       "overallRanked": {"rankedSetCount": 1}},
            "ripWeightsConfig": {
                "overallRip": {"version": "v12"}, "financialRip": {"version": "v4"},
                "collectorAppeal": {"version": "v5"}, "publicContract": {"version": "v11"},
            },
        },
    }}


def _ready_report(market_date="2026-09-08"):
    return RankingsReadinessReport(
        status=READY, reason_code=READY,
        detail=f"Rankings candidate is ready for {market_date} with 1 supported sets",
        market_date=market_date, expected_supported_cohort_count=1,
        verified_simulation_cohort_count=1, source_run_ids={"set-0": "run-0"},
        source_run_fingerprint="fp", contract_versions={
            "overallRipVersion": "v12", "financialRipVersion": "v4",
            "collectorAppealVersion": "v5", "publicRipContractVersion": "v11",
        },
    )


@pytest.fixture(autouse=True)
def _stub_publisher_internals(monkeypatch):
    monkeypatch.setattr(command, "build_explore_rankings_snapshot_row", lambda **_kwargs: _row())
    monkeypatch.setattr(command, "publication_contract", lambda row: (
        {"id": "pub-1", "market_date": "2026-09-08", "eligible_cohort_count": 1,
         "cohort_version": "cohort-v1", "overall_rip_version": "v12",
         "financial_rip_version": "v4", "ca7_version": "v5", "diagnostics": {},
         "simulation_source_market_date": "2026-09-08"},
        [{"set_id": "set-0"}],
    ))
    monkeypatch.setattr(command, "validate_publication_payload", lambda *_a, **_k: None)
    monkeypatch.setattr(command, "evaluate_rankings_publication_readiness",
                         lambda *_a, **_k: _ready_report())


def _attempt_rows(client):
    return list(client.tables["pokemon_rankings_publication_attempts"])


def test_successful_publication_finalizes_its_attempt_as_published(monkeypatch):
    """The exact incident: attempt must NOT stay `evaluating` after a
    publication that actually commits."""
    monkeypatch.setattr(command, "assert_rankings_publication_parity", lambda *_a, **_k: {"status": "passed"})
    client = FakeClient()

    result = command.publish_explore_rip_rankings_snapshot(client, commit=True)

    attempts = _attempt_rows(client)
    assert len(attempts) == 1
    attempt = attempts[0]
    assert attempt["status"] == "published"
    assert attempt["completed_at"] is not None
    assert attempt["resulting_publication_id"] == "pub-1"
    assert result["_rankingsPublicationOutcome"]["classification"] == "PUBLISHED"
    assert result["_rankingsPublicationOutcome"]["attempt_id"] == attempt["id"]
    assert result["_rankingsPublicationOutcome"]["publication_id"] == "pub-1"
    assert [name for name, _params in client.rpc_calls] == ["publish_pokemon_public_rip_leaderboard"]


def test_rpc_failure_finalizes_the_attempt_as_failed_not_evaluating():
    client = FakeClient(rpc_exception=RuntimeError("boom"))
    with pytest.raises(RuntimeError, match="boom"):
        command.publish_explore_rip_rankings_snapshot(client, commit=True)
    attempts = _attempt_rows(client)
    assert len(attempts) == 1
    assert attempts[0]["status"] == "failed"
    assert attempts[0]["reason_code"] == "FAILED_PUBLICATION_RPC"
    assert attempts[0]["completed_at"] is not None
    assert attempts[0]["resulting_publication_id"] is None


def test_post_publication_parity_failure_finalizes_the_attempt_as_failed(monkeypatch):
    def _raise_parity(*_a, **_k):
        raise RuntimeError("parity mismatch")
    monkeypatch.setattr(command, "assert_rankings_publication_parity", _raise_parity)
    client = FakeClient()
    with pytest.raises(RuntimeError, match="parity mismatch"):
        command.publish_explore_rip_rankings_snapshot(client, commit=True)
    attempts = _attempt_rows(client)
    assert len(attempts) == 1
    assert attempts[0]["status"] == "failed"
    assert attempts[0]["reason_code"] == "FAILED_POST_PUBLICATION_PARITY"
    assert attempts[0]["completed_at"] is not None
    # A publication ID IS recorded even on a parity failure: the RPC already
    # committed by this point, so the attempt should still say what it wrote.
    assert attempts[0]["resulting_publication_id"] == "pub-1"


def test_validation_failure_finalizes_the_attempt_as_failed_before_any_rpc(monkeypatch):
    def _raise_validation(*_a, **_k):
        raise RuntimeError("malformed contract")
    monkeypatch.setattr(command, "validate_publication_payload", _raise_validation)
    client = FakeClient()
    with pytest.raises(RuntimeError, match="malformed contract"):
        command.publish_explore_rip_rankings_snapshot(client, commit=True)
    attempts = _attempt_rows(client)
    assert len(attempts) == 1
    assert attempts[0]["status"] == "failed"
    assert attempts[0]["completed_at"] is not None
    assert client.rpc_calls == []


def test_a_publication_requiring_rankings_never_exits_with_zero_attempt_rows(monkeypatch):
    """A canonical candidate that needs publication must create a lifecycle
    attempt row - a commit-capable workflow must never silently do nothing."""
    monkeypatch.setattr(command, "assert_rankings_publication_parity", lambda *_a, **_k: {"status": "passed"})
    client = FakeClient()
    command.publish_explore_rip_rankings_snapshot(client, commit=True)
    assert len(_attempt_rows(client)) == 1


def test_orphaned_evaluating_attempt_from_a_crashed_prior_run_is_reconciled(monkeypatch):
    """A prior process started an attempt (readiness READY) and then never
    finished it - simulating the crash/restart the Sept-8 incident's
    `fd215ea3-...` attempt actually suffered. The NEXT publication for the
    same market date must close it out rather than leaving it orphaned
    forever alongside the new one.
    """
    monkeypatch.setattr(command, "assert_rankings_publication_parity", lambda *_a, **_k: {"status": "passed"})
    client = FakeClient()
    from backend.db.services.rankings_publication_lifecycle import start_rankings_publication_attempt
    orphan_id = start_rankings_publication_attempt(client, _ready_report())
    assert client.tables["pokemon_rankings_publication_attempts"][0]["status"] == "evaluating"

    command.publish_explore_rip_rankings_snapshot(client, commit=True)

    attempts = {row["id"]: row for row in _attempt_rows(client)}
    assert len(attempts) == 2
    assert attempts[orphan_id]["status"] == "failed"
    assert attempts[orphan_id]["reason_code"] == "ORPHANED_ATTEMPT_SUPERSEDED"
    assert attempts[orphan_id]["completed_at"] is not None
    new_attempt = next(row for aid, row in attempts.items() if aid != orphan_id)
    assert new_attempt["status"] == "published"
