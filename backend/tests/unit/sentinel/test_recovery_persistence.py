from __future__ import annotations

from datetime import datetime, timedelta, timezone

from backend.sentinel.incidents import IncidentManager
from backend.sentinel.models import (
    CheckResult,
    RecoveryAttemptRecord,
    RecoveryAttemptStatus,
    RunnerIdentity,
    Severity,
)
from backend.sentinel.recovery.engine import (
    RecoveryExecution,
    RecoveryRegistry,
    RecoveryRunbook,
    RecoveryRunner,
)
from backend.sentinel.registry import CheckRegistry
from backend.sentinel.state import MemoryStateStore, SupabaseStateStore


NOW = datetime(2026, 9, 11, 20, 0, tzinfo=timezone.utc)
IDENTITY = RunnerIdentity(component="sentinel_vm", host="vm-1", build_sha="sha")


class _Result:
    def __init__(self, data=None):
        self.data = data or []


class _RecoveryQuery:
    def __init__(self, client, table_name):
        self.client = client
        self.table_name = table_name
        self.rows = [dict(row) for row in client.rows.get(table_name, [])]
        self.upsert_payload = None
        self.on_conflict = None

    def select(self, *_args, **_kwargs):
        return self

    def eq(self, key, value):
        self.rows = [row for row in self.rows if row.get(key) == value]
        return self

    def order(self, key, desc=False):
        self.rows = sorted(self.rows, key=lambda row: row.get(key), reverse=desc)
        return self

    def limit(self, count):
        self.rows = self.rows[:count]
        return self

    def upsert(self, payload, on_conflict=None):
        self.upsert_payload = dict(payload)
        self.on_conflict = on_conflict
        self.client.upserts.append((self.table_name, self.upsert_payload, on_conflict))
        return self

    def execute(self):
        return _Result(self.rows)


class _Client:
    def __init__(self, rows=None):
        self.rows = rows or {}
        self.upserts = []

    def table(self, name):
        return _RecoveryQuery(self, name)


def test_supabase_recovery_attempt_round_trip_shape_uses_internal_table_and_id_conflict():
    client = _Client()
    store = SupabaseStateStore(client)
    attempt = RecoveryAttemptRecord(
        id="attempt-1",
        incident_id="incident-1",
        runbook="publish_post_scrape_if_needed_v1",
        runbook_version="1",
        started_at=NOW,
        completed_at=NOW + timedelta(seconds=5),
        status=RecoveryAttemptStatus.SUCCEEDED,
        attempt_number=1,
        preconditions_json={"batch_id": 48},
        result_json={"verification": {"outcome": "healthy"}},
    )
    store.save_recovery_attempt(attempt)
    table, payload, conflict = client.upserts[0]
    assert table == "sentinel_recovery_attempts"
    assert conflict == "id"
    assert payload["incident_id"] == "incident-1"
    assert payload["runbook"] == "publish_post_scrape_if_needed_v1"
    assert payload["status"] == "succeeded"
    assert payload["attempt_number"] == 1


def test_supabase_latest_recovery_attempt_orders_by_attempt_number_descending():
    client = _Client(
        {
            "sentinel_recovery_attempts": [
                {
                    "id": "attempt-1",
                    "incident_id": "incident-1",
                    "runbook": "runbook-v1",
                    "runbook_version": "1",
                    "started_at": (NOW - timedelta(minutes=10)).isoformat(),
                    "completed_at": (NOW - timedelta(minutes=9)).isoformat(),
                    "preconditions_json": {},
                    "result_json": {},
                    "status": "failed",
                    "attempt_number": 1,
                    "cooldown_until": None,
                },
                {
                    "id": "attempt-2",
                    "incident_id": "incident-1",
                    "runbook": "runbook-v1",
                    "runbook_version": "1",
                    "started_at": (NOW - timedelta(minutes=5)).isoformat(),
                    "completed_at": None,
                    "preconditions_json": {},
                    "result_json": {},
                    "status": "started",
                    "attempt_number": 2,
                    "cooldown_until": None,
                },
            ]
        }
    )
    latest = SupabaseStateStore(client).get_latest_recovery_attempt(
        "incident-1", "runbook-v1"
    )
    assert latest.id == "attempt-2"
    assert latest.status is RecoveryAttemptStatus.STARTED
    assert latest.attempt_number == 2


def test_unfinished_started_attempt_blocks_blind_replay_after_partial_state_write():
    store = MemoryStateStore()
    checks = CheckRegistry()
    registered = checks.register(
        "market.freshness",
        lambda ctx: CheckResult.failure(
            "market.freshness",
            failure_code="market_publication_stale",
            severity=Severity.CRITICAL,
            authority_identity="2026-09-11",
            checked_at=ctx.now,
        ),
        confirm_after=1,
    )
    opened = IncidentManager(store).process(
        registered,
        CheckResult.failure(
            "market.freshness",
            failure_code="market_publication_stale",
            severity=Severity.CRITICAL,
            authority_identity="2026-09-11",
            checked_at=NOW,
        ),
        IDENTITY,
    )
    incident = store.get_incident(opened.incident_id)

    # Simulate a process dying after STARTED was persisted but before the
    # incident row was advanced to RECOVERING/attempt_count=1.
    store.save_recovery_attempt(
        RecoveryAttemptRecord(
            id="partial-attempt",
            incident_id=incident.id,
            runbook="test-runbook",
            runbook_version="1",
            started_at=NOW,
            status=RecoveryAttemptStatus.STARTED,
            attempt_number=1,
        )
    )
    called = []
    recovery = RecoveryRegistry()
    recovery.register(
        RecoveryRunbook(
            key="test-runbook",
            version="1",
            check_key="market.freshness",
            failure_code="market_publication_stale",
            precondition=lambda incident, ctx: (_ for _ in ()).throw(
                AssertionError("precondition must not re-run")
            ),
            execute=lambda incident, ctx: (
                called.append(True),
                RecoveryExecution.succeeded(),
            )[1],
            verify=lambda incident, ctx: CheckResult.healthy(
                incident.check_key, checked_at=ctx.now
            ),
            max_attempts=2,
        )
    )
    report = RecoveryRunner(store, recovery).attempt(
        incident, registered, identity=IDENTITY, now=NOW + timedelta(minutes=1)
    )
    assert report["reason_code"] == "recovery_prior_attempt_unfinished"
    assert called == []
    assert store.get_incident(incident.id).recovery_attempt_count == 0
