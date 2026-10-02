from __future__ import annotations

from datetime import datetime, timedelta, timezone
from types import SimpleNamespace

import pytest

import backend.sentinel.operational as operational
from backend.sentinel.checks.db_safety import (
    DB_SAFETY_HOLD_AUTHORITY,
    DB_SAFETY_HOLD_CHECK_KEY,
    FAILURE_ACTIVE as DB_SAFETY_HOLD_ACTIVE,
    FAILURE_INVALID_EMPTY as DB_SAFETY_HOLD_INVALID_EMPTY,
)
from backend.sentinel.checks.registry import build_fast_registry
from backend.sentinel.config import SentinelConfig
from backend.sentinel.incidents import IncidentManager
from backend.sentinel.models import (
    CheckOutcome,
    CheckResult,
    IncidentStatus,
    RecoveryAttemptRecord,
    RecoveryAttemptStatus,
    RunnerIdentity,
    Severity,
)
from backend.sentinel.recovery.engine import (
    RecoveryDecision,
    RecoveryExecution,
    RecoveryRegistry,
    RecoveryRunbook,
    RecoveryRunner,
)
from backend.sentinel.recovery.runbooks import (
    DB_SAFETY_HOLD_RUNBOOK,
    LEASE_RUNBOOK,
    MARKET_EXPLORER_PROGRESS_RUNBOOK,
    MARKET_EXPLORER_SCHEDULER_RUNBOOK,
    PRICING_RUNBOOK,
    PRICING_SCHEDULER_RUNBOOK,
    PUBLICATION_DIVERGENCE_RUNBOOK,
    PUBLICATION_RUNBOOK,
    SENTINEL_SCHEDULER_RUNBOOK,
    build_safe_recovery_registry,
)
from backend.sentinel.registry import CheckRegistry
from backend.sentinel.state import MemoryStateStore, NoopStateStore


NOW = datetime(2026, 9, 11, 20, 0, tzinfo=timezone.utc)
IDENTITY = RunnerIdentity(component="sentinel_vm", host="vm-1", build_sha="sha")


def _open_incident(
    store,
    *,
    key="market.freshness",
    code="market_publication_stale",
    authority="2026-09-11",
    confirm_after=1,
):
    registry = CheckRegistry()
    registered = registry.register(
        key,
        lambda ctx: CheckResult.failure(
            key,
            failure_code=code,
            severity=Severity.CRITICAL,
            authority_identity=authority,
            checked_at=ctx.now,
        ),
        confirm_after=confirm_after,
    )
    result = CheckResult.failure(
        key,
        failure_code=code,
        severity=Severity.CRITICAL,
        authority_identity=authority,
        checked_at=NOW,
    )
    transition = IncidentManager(store).process(registered, result, IDENTITY)
    assert transition.incident_id
    return registered, store.get_incident(transition.incident_id)


def _generic_runbook(
    *,
    key="market.freshness",
    code="market_publication_stale",
    precondition=None,
    execute=None,
    verify=None,
    max_attempts=1,
    cooldown_seconds=3600,
):
    return RecoveryRunbook(
        key="test_runbook_v1",
        version="1",
        check_key=key,
        failure_code=code,
        precondition=precondition
        or (lambda incident, ctx: RecoveryDecision.allow(authority=incident.authority_identity)),
        execute=execute
        or (lambda incident, ctx: RecoveryExecution.succeeded(result={"ok": True})),
        verify=verify
        or (
            lambda incident, ctx: CheckResult.healthy(
                incident.check_key,
                authority_identity=incident.authority_identity,
                checked_at=ctx.now,
            )
        ),
        max_attempts=max_attempts,
        cooldown_seconds=cooldown_seconds,
    )


def _runner(store, runbook):
    registry = RecoveryRegistry()
    registry.register(runbook)
    return RecoveryRunner(store, registry)


def test_recovery_registry_is_exact_match_only():
    registry = RecoveryRegistry()
    runbook = _generic_runbook()
    registry.register(runbook)
    assert registry.matches() == (("market.freshness", "market_publication_stale"),)
    with pytest.raises(ValueError, match="duplicate"):
        registry.register(runbook)


def test_recovery_requires_persistent_state_before_any_mutation():
    registered = CheckRegistry().register(
        "market.freshness", lambda ctx: None, confirm_after=1
    )
    incident = SimpleNamespace(
        id="incident-1",
        check_key="market.freshness",
        failure_code="market_publication_stale",
        status=IncidentStatus.OPEN,
        authority_identity="2026-09-11",
        recovery_attempt_count=0,
    )
    report = _runner(NoopStateStore(), _generic_runbook()).attempt(
        incident, registered, identity=IDENTITY, now=NOW
    )
    assert report["reason_code"] == "recovery_requires_persistent_state"


def test_recovery_persists_started_attempt_before_mutation_and_resolves_only_after_verify():
    store = MemoryStateStore()
    registered, incident = _open_incident(store)
    observed = {}

    def execute(current, ctx):
        attempt = store.get_latest_recovery_attempt(current.id, "test_runbook_v1")
        observed["attempt_status_during_execute"] = attempt.status
        observed["incident_status_during_execute"] = store.get_incident(current.id).status
        return RecoveryExecution.succeeded(result={"published": True})

    report = _runner(store, _generic_runbook(execute=execute)).attempt(
        incident, registered, identity=IDENTITY, now=NOW
    )
    assert report["action"] == "recovered"
    assert observed["attempt_status_during_execute"] is RecoveryAttemptStatus.STARTED
    assert observed["incident_status_during_execute"] is IncidentStatus.RECOVERING
    attempt = store.get_latest_recovery_attempt(incident.id, "test_runbook_v1")
    assert attempt.status is RecoveryAttemptStatus.SUCCEEDED
    assert store.get_incident(incident.id).status is IncidentStatus.RESOLVED
    assert store.get_check_state(incident.check_key).current_incident_id is None


def test_execution_exception_is_escalated_without_secret_message_persistence():
    store = MemoryStateStore()
    registered, incident = _open_incident(store)

    def boom(_incident, _ctx):
        raise RuntimeError("secret-capability-token-must-not-persist")

    report = _runner(store, _generic_runbook(execute=boom)).attempt(
        incident, registered, identity=IDENTITY, now=NOW
    )
    assert report["action"] == "escalated"
    assert store.get_incident(incident.id).status is IncidentStatus.ESCALATED
    attempt = store.get_latest_recovery_attempt(incident.id, "test_runbook_v1")
    assert attempt.status is RecoveryAttemptStatus.FAILED
    rendered = str(attempt.result_json)
    assert "RuntimeError" in rendered
    assert "secret-capability-token" not in rendered


def test_failed_verification_escalates_original_incident_without_spawning_replacement():
    store = MemoryStateStore()
    registered, incident = _open_incident(store)

    def verify(current, ctx):
        return CheckResult.failure(
            current.check_key,
            failure_code="different_failure_after_repair",
            severity=Severity.CRITICAL,
            authority_identity=current.authority_identity,
            checked_at=ctx.now,
        )

    report = _runner(store, _generic_runbook(verify=verify)).attempt(
        incident, registered, identity=IDENTITY, now=NOW
    )
    assert report["reason_code"] == "recovery_verification_failed"
    assert store.get_incident(incident.id).status is IncidentStatus.ESCALATED
    assert len(store.incidents) == 1
    assert store.get_check_state(incident.check_key).current_incident_id == incident.id


def test_attempt_limit_blocks_second_mutation():
    store = MemoryStateStore()
    registered, incident = _open_incident(store)
    incident.recovery_attempt_count = 1
    store.upsert_incident(incident)
    called = []
    runbook = _generic_runbook(execute=lambda *a: called.append(True))
    report = _runner(store, runbook).attempt(
        incident, registered, identity=IDENTITY, now=NOW
    )
    assert report["reason_code"] == "recovery_attempt_limit_reached"
    assert called == []


def test_blocked_no_mutation_attempt_retries_after_cooldown():
    store = MemoryStateStore()
    registered, incident = _open_incident(store)
    executions = iter(
        [
            RecoveryExecution.blocked(result={"status": "database_safety_hold"}),
            RecoveryExecution.succeeded(
                result={"status": "published"}, mutation_performed=True
            ),
        ]
    )
    calls = []

    def execute(*_args):
        calls.append(True)
        return next(executions)

    runbook = _generic_runbook(execute=execute, cooldown_seconds=60 * 60)
    runner = _runner(store, runbook)

    first = runner.attempt(incident, registered, identity=IDENTITY, now=NOW)
    assert first["reason_code"] == "recovery_execution_blocked"
    assert store.get_incident(incident.id).status is IncidentStatus.OPEN
    assert store.get_incident(incident.id).recovery_attempt_count == 1

    still_cooling = runner.attempt(
        store.get_incident(incident.id),
        registered,
        identity=IDENTITY,
        now=NOW + timedelta(minutes=30),
    )
    assert still_cooling["reason_code"] == "recovery_cooldown_active"
    assert calls == [True]

    recovered = runner.attempt(
        store.get_incident(incident.id),
        registered,
        identity=IDENTITY,
        now=NOW + timedelta(minutes=61),
    )
    assert recovered["action"] == "recovered"
    assert calls == [True, True]
    latest = store.get_latest_recovery_attempt(incident.id, runbook.key)
    assert latest.attempt_number == 2
    assert latest.status is RecoveryAttemptStatus.SUCCEEDED


def test_cooldown_blocks_retry_before_precondition_or_mutation():
    store = MemoryStateStore()
    registered, incident = _open_incident(store)
    incident.recovery_attempt_count = 1
    store.upsert_incident(incident)
    store.save_recovery_attempt(
        RecoveryAttemptRecord(
            id="attempt-1",
            incident_id=incident.id,
            runbook="test_runbook_v1",
            runbook_version="1",
            started_at=NOW - timedelta(minutes=5),
            completed_at=NOW - timedelta(minutes=4),
            status=RecoveryAttemptStatus.FAILED,
            attempt_number=1,
            cooldown_until=NOW + timedelta(minutes=55),
        )
    )
    called = []
    report = _runner(
        store,
        _generic_runbook(max_attempts=2, execute=lambda *a: called.append(True)),
    ).attempt(incident, registered, identity=IDENTITY, now=NOW)
    assert report["reason_code"] == "recovery_cooldown_active"
    assert called == []


def test_precondition_block_does_not_consume_recovery_attempt():
    store = MemoryStateStore()
    registered, incident = _open_incident(store)
    runbook = _generic_runbook(
        precondition=lambda incident, ctx: RecoveryDecision.block("unsafe_now")
    )
    report = _runner(store, runbook).attempt(
        incident, registered, identity=IDENTITY, now=NOW
    )
    assert report["reason_code"] == "unsafe_now"
    assert store.get_incident(incident.id).recovery_attempt_count == 0
    assert store.get_latest_recovery_attempt(incident.id, runbook.key) is None


def test_p6_allowlist_contains_only_bounded_canonical_recoveries():
    noop_failure = lambda *a, **k: CheckResult.failure(
        "market.freshness",
        failure_code="market_publication_stale",
        authority_identity="2026-09-11",
        checked_at=NOW,
    )
    registry = build_safe_recovery_registry(
        client=object(),
        publish_if_needed_fn=lambda *a, **k: {"status": "published"},
        gate_evaluator=lambda *a, **k: SimpleNamespace(allowed=True, reason_code="allowed_complete"),
        market_freshness_checker=noop_failure,
        lease_reconciler=lambda: 0,
        lease_checker=lambda *a, **k: CheckResult.failure(
            "scrape.queue_leases",
            failure_code="scrape_job_lease_expired",
            authority_identity="2026-09-11",
            evidence={"stale_jobs": [{"id": 1}]},
            observed={"stale_running_jobs": 1},
            checked_at=NOW,
        ),
    )
    assert registry.matches() == (
        ("database.safety_hold", "DATABASE_SAFETY_HOLD_INVALID_EMPTY"),
        ("market.freshness", "market_publication_stale"),
        ("market.freshness", "market_snapshot_date_divergence"),
        ("market_explorer.maintenance_progress", "MARKET_EXPLORER_CONVERGENCE_STALLED"),
        ("market_explorer.maintenance_scheduler", "MARKET_EXPLORER_MAINTENANCE_SCHEDULE_MISSING"),
        ("pricing.ebay.scheduler", "EBAY_DAILY_SCHEDULE_MISSING"),
        ("pricing.multi_source.run_freshness", "DAILY_RUN_STALE_OR_INCOMPLETE"),
        ("scrape.queue_leases", "scrape_job_lease_expired"),
        ("sentinel.runtime_scheduler", "SENTINEL_RUNTIME_SCHEDULE_MISSING"),
    )



def test_empty_db_safety_hold_recovery_is_exact_and_verified():
    store = MemoryStateStore()
    registered, incident = _open_incident(
        store,
        key=DB_SAFETY_HOLD_CHECK_KEY,
        code=DB_SAFETY_HOLD_INVALID_EMPTY,
        authority=DB_SAFETY_HOLD_AUTHORITY,
    )
    live_results = iter(
        [
            CheckResult.failure(
                DB_SAFETY_HOLD_CHECK_KEY,
                failure_code=DB_SAFETY_HOLD_INVALID_EMPTY,
                severity=Severity.CRITICAL,
                authority_identity=DB_SAFETY_HOLD_AUTHORITY,
                observed={"state": "invalid_empty"},
                checked_at=NOW,
            ),
            CheckResult.healthy(
                DB_SAFETY_HOLD_CHECK_KEY,
                authority_identity=DB_SAFETY_HOLD_AUTHORITY,
                observed={"state": "absent"},
                checked_at=NOW,
            ),
        ]
    )
    repair_calls = []
    recovery = build_safe_recovery_registry(
        client=object(),
        db_safety_hold_checker=lambda *_a, **_k: next(live_results),
        db_safety_hold_repairer=lambda: (
            repair_calls.append(True),
            {
                "status": "cleared_invalid_empty_hold",
                "mutation_performed": True,
            },
        )[1],
        lease_reconciler=lambda: 0,
        lease_checker=lambda *a, **k: CheckResult.healthy(
            "scrape.queue_leases", checked_at=NOW
        ),
    )

    report = RecoveryRunner(store, recovery).attempt(
        incident, registered, identity=IDENTITY, now=NOW
    )

    assert report["action"] == "recovered"
    assert repair_calls == [True]
    attempt = store.get_latest_recovery_attempt(incident.id, DB_SAFETY_HOLD_RUNBOOK)
    assert attempt.status is RecoveryAttemptStatus.SUCCEEDED
    assert store.get_incident(incident.id).status is IncidentStatus.RESOLVED


def test_valid_db_safety_hold_is_not_allowlisted_for_auto_clear():
    store = MemoryStateStore()
    registered, incident = _open_incident(
        store,
        key=DB_SAFETY_HOLD_CHECK_KEY,
        code=DB_SAFETY_HOLD_ACTIVE,
        authority=DB_SAFETY_HOLD_AUTHORITY,
    )
    recovery = build_safe_recovery_registry(
        client=object(),
        lease_reconciler=lambda: 0,
        lease_checker=lambda *a, **k: CheckResult.healthy(
            "scrape.queue_leases", checked_at=NOW
        ),
    )

    report = RecoveryRunner(store, recovery).attempt(
        incident, registered, identity=IDENTITY, now=NOW
    )

    assert report["action"] == "not_allowlisted"

def test_publication_recovery_refuses_incomplete_batch_before_publish():
    store = MemoryStateStore()
    registered, incident = _open_incident(store)
    publish_calls = []
    live_failure = lambda *a, **k: CheckResult.failure(
        "market.freshness",
        failure_code="market_publication_stale",
        authority_identity="2026-09-11",
        checked_at=NOW,
    )
    recovery = build_safe_recovery_registry(
        client=object(),
        publish_if_needed_fn=lambda *a, **k: publish_calls.append(True),
        gate_evaluator=lambda *a, **k: SimpleNamespace(
            allowed=False,
            reason_code="blocked_incomplete",
            batch_id=48,
            batch_status="running",
            missing_set_count=3,
        ),
        market_freshness_checker=live_failure,
        lease_reconciler=lambda: 0,
        lease_checker=lambda *a, **k: CheckResult.healthy(
            "scrape.queue_leases", checked_at=NOW
        ),
    )
    report = RecoveryRunner(store, recovery).attempt(
        incident, registered, identity=IDENTITY, now=NOW
    )
    assert report["reason_code"] == "publication_batch_gate_not_complete"
    assert publish_calls == []


def test_publication_recovery_treats_database_safety_hold_as_blocked():
    store = MemoryStateStore()
    registered, incident = _open_incident(store)
    live_failure = lambda *a, **k: CheckResult.failure(
        "market.freshness",
        failure_code="market_publication_stale",
        authority_identity="2026-09-11",
        checked_at=NOW,
    )
    recovery = build_safe_recovery_registry(
        client=object(),
        publish_if_needed_fn=lambda *_a, **_k: {
            "market_date": "2026-09-11",
            "status": "deferred_database_safety_hold",
            "exit_code": 75,
        },
        gate_evaluator=lambda *a, **k: SimpleNamespace(
            allowed=True, reason_code="allowed_complete", batch_id=48
        ),
        market_freshness_checker=live_failure,
        lease_reconciler=lambda: 0,
        lease_checker=lambda *a, **k: CheckResult.healthy(
            "scrape.queue_leases", checked_at=NOW
        ),
    )
    report = RecoveryRunner(store, recovery).attempt(
        incident, registered, identity=IDENTITY, now=NOW
    )
    assert report["reason_code"] == "recovery_execution_blocked"
    assert store.get_incident(incident.id).status is IncidentStatus.OPEN
    attempt = store.get_latest_recovery_attempt(incident.id, PUBLICATION_RUNBOOK)
    assert attempt.status is RecoveryAttemptStatus.BLOCKED
    assert attempt.result_json["execution"]["mutation_performed"] is False


def test_publication_recovery_uses_canonical_wrapper_then_requires_healthy_verification():
    store = MemoryStateStore()
    registered, incident = _open_incident(store)
    live_results = iter(
        [
            CheckResult.failure(
                "market.freshness",
                failure_code="market_publication_stale",
                authority_identity="2026-09-11",
                checked_at=NOW,
            ),
            CheckResult.healthy(
                "market.freshness",
                authority_identity="2026-09-11",
                checked_at=NOW,
            ),
        ]
    )
    publish_calls = []
    recovery = build_safe_recovery_registry(
        client=object(),
        publish_if_needed_fn=lambda market_date, **kwargs: (
            publish_calls.append((market_date, kwargs)),
            {"market_date": market_date, "status": "published"},
        )[1],
        gate_evaluator=lambda *a, **k: SimpleNamespace(
            allowed=True, reason_code="allowed_complete", batch_id=48
        ),
        market_freshness_checker=lambda *a, **k: next(live_results),
        lease_reconciler=lambda: 0,
        lease_checker=lambda *a, **k: CheckResult.healthy(
            "scrape.queue_leases", checked_at=NOW
        ),
    )
    report = RecoveryRunner(store, recovery).attempt(
        incident, registered, identity=IDENTITY, now=NOW
    )
    assert report["action"] == "recovered"
    assert publish_calls[0][0] == "2026-09-11"
    assert store.get_incident(incident.id).status is IncidentStatus.RESOLVED


def test_snapshot_divergence_reuses_canonical_publication_wrapper():
    store = MemoryStateStore()
    registered, incident = _open_incident(
        store,
        key="market.freshness",
        code="market_snapshot_date_divergence",
    )
    live_results = iter([
        CheckResult.failure(
            "market.freshness",
            failure_code="market_snapshot_date_divergence",
            authority_identity="2026-09-11",
            checked_at=NOW,
        ),
        CheckResult.healthy(
            "market.freshness",
            authority_identity="2026-09-11",
            checked_at=NOW,
        ),
    ])
    calls = []
    recovery = build_safe_recovery_registry(
        client=object(),
        publish_if_needed_fn=lambda market_date, **kwargs: (
            calls.append(market_date),
            {"market_date": market_date, "status": "published"},
        )[1],
        gate_evaluator=lambda *a, **k: SimpleNamespace(
            allowed=True, reason_code="allowed_complete", batch_id=48
        ),
        market_freshness_checker=lambda *a, **k: next(live_results),
        lease_reconciler=lambda: 0,
        lease_checker=lambda *a, **k: CheckResult.healthy(
            "scrape.queue_leases", checked_at=NOW
        ),
        pricing_health_checker=lambda *a, **k: CheckResult.healthy(
            k["check_key"], authority_identity="2026-09-11", checked_at=NOW
        ),
        pricing_scheduler_checker=lambda *a, **k: CheckResult.healthy(
            "pricing.ebay.scheduler", checked_at=NOW
        ),
    )
    report = RecoveryRunner(store, recovery).attempt(
        incident, registered, identity=IDENTITY, now=NOW
    )
    assert report["action"] == "recovered"
    assert calls == ["2026-09-11"]
    assert PUBLICATION_DIVERGENCE_RUNBOOK != PUBLICATION_RUNBOOK


def test_pricing_daily_recovery_requires_complete_promoted_source_batch():
    store = MemoryStateStore()
    registered, incident = _open_incident(
        store,
        key="pricing.multi_source.run_freshness",
        code="DAILY_RUN_STALE_OR_INCOMPLETE",
    )

    class Query:
        def select(self, *a, **k): return self
        def eq(self, *a, **k): return self
        def order(self, *a, **k): return self
        def limit(self, *a, **k): return self
        def execute(self): return SimpleNamespace(data=[{
            "id": 65, "status": "running", "promoted_at": None, "missing_set_count": 4
        }])

    client = SimpleNamespace(table=lambda name: Query())
    calls = []
    recovery = build_safe_recovery_registry(
        client=client,
        market_freshness_checker=lambda *a, **k: CheckResult.healthy(
            "market.freshness", checked_at=NOW
        ),
        lease_reconciler=lambda: 0,
        lease_checker=lambda *a, **k: CheckResult.healthy(
            "scrape.queue_leases", checked_at=NOW
        ),
        pricing_health_checker=lambda *a, **k: CheckResult.failure(
            "pricing.multi_source.run_freshness",
            failure_code="DAILY_RUN_STALE_OR_INCOMPLETE",
            severity=Severity.WARNING,
            authority_identity="2026-09-11",
            checked_at=NOW,
        ),
        pricing_run_fn=lambda day: calls.append(day) or {"status": "complete", "exit_code": 0},
        pricing_scheduler_checker=lambda *a, **k: CheckResult.healthy(
            "pricing.ebay.scheduler", checked_at=NOW
        ),
    )
    report = RecoveryRunner(store, recovery).attempt(
        incident, registered, identity=IDENTITY, now=NOW
    )
    assert report["reason_code"] == "pricing_source_batch_not_complete"
    assert calls == []


def test_explorer_only_divergence_defers_to_bounded_maintenance_worker():
    store = MemoryStateStore()
    registered, incident = _open_incident(
        store,
        key="market.freshness",
        code="market_snapshot_date_divergence",
    )
    publish_calls = []
    live = CheckResult.failure(
        "market.freshness",
        failure_code="market_snapshot_date_divergence",
        severity=Severity.CRITICAL,
        authority_identity="2026-09-11",
        observed={
            "authority_dates": {
                "accepted_market_quality": "2026-09-11",
                "set_value": "2026-09-11",
                "set_market_dashboard": "2026-09-11",
                "sealed_snapshot": "2026-09-11",
                "global_market_index": "2026-09-11",
                "explore_set_value": "2026-09-11",
                "explore_card_movers": "2026-09-11",
                "card_market_current": "2026-09-11",
                "sealed_product_current": "2026-09-11",
                "explorer_v2": "2026-09-10",
            }
        },
        checked_at=NOW,
    )
    recovery = build_safe_recovery_registry(
        client=object(),
        publish_if_needed_fn=lambda *a, **k: publish_calls.append(True),
        gate_evaluator=lambda *a, **k: SimpleNamespace(
            allowed=True, reason_code="allowed_complete", batch_id=48
        ),
        market_freshness_checker=lambda *a, **k: live,
        lease_reconciler=lambda: 0,
        lease_checker=lambda *a, **k: CheckResult.healthy(
            "scrape.queue_leases", checked_at=NOW
        ),
        pricing_health_checker=lambda *a, **k: CheckResult.healthy(
            k["check_key"], authority_identity="2026-09-11", checked_at=NOW
        ),
        pricing_scheduler_checker=lambda *a, **k: CheckResult.healthy(
            "pricing.ebay.scheduler",
            authority_identity="multi-source-pricing-cron-v1",
            checked_at=NOW,
        ),
        market_explorer_scheduler_checker=lambda *a, **k: CheckResult.healthy(
            "market_explorer.maintenance_scheduler",
            authority_identity="market-explorer-prewarm-cron-v1",
            checked_at=NOW,
        ),
    )
    report = RecoveryRunner(store, recovery).attempt(
        incident, registered, identity=IDENTITY, now=NOW
    )
    assert report["reason_code"] == "explorer_convergence_owned_by_maintained_worker"
    assert publish_calls == []
    assert store.get_incident(incident.id).recovery_attempt_count == 0


def test_sentinel_scheduler_recovery_uses_managed_installer_then_verifies():
    store = MemoryStateStore()
    registered, incident = _open_incident(
        store,
        key="sentinel.runtime_scheduler",
        code="SENTINEL_RUNTIME_SCHEDULE_MISSING",
        authority="sentinel-runtime-cron-v1",
    )
    states = iter([
        CheckResult.failure(
            "sentinel.runtime_scheduler",
            failure_code="SENTINEL_RUNTIME_SCHEDULE_MISSING",
            severity=Severity.CRITICAL,
            authority_identity="sentinel-runtime-cron-v1",
            checked_at=NOW,
        ),
        CheckResult.healthy(
            "sentinel.runtime_scheduler",
            authority_identity="sentinel-runtime-cron-v1",
            checked_at=NOW,
        ),
    ])
    installs = []
    recovery = build_safe_recovery_registry(
        client=object(),
        market_freshness_checker=lambda *a, **k: CheckResult.healthy(
            "market.freshness", checked_at=NOW
        ),
        lease_reconciler=lambda: 0,
        lease_checker=lambda *a, **k: CheckResult.healthy(
            "scrape.queue_leases", checked_at=NOW
        ),
        pricing_health_checker=lambda *a, **k: CheckResult.healthy(
            k["check_key"], authority_identity="2026-09-11", checked_at=NOW
        ),
        pricing_scheduler_checker=lambda *a, **k: CheckResult.healthy(
            "pricing.ebay.scheduler", checked_at=NOW
        ),
        market_explorer_scheduler_checker=lambda *a, **k: CheckResult.healthy(
            "market_explorer.maintenance_scheduler", checked_at=NOW
        ),
        market_explorer_progress_checker=lambda *a, **k: CheckResult.healthy(
            "market_explorer.maintenance_progress",
            authority_identity="2026-09-11",
            checked_at=NOW,
        ),
        sentinel_scheduler_checker=lambda *a, **k: next(states),
        sentinel_cron_installer=lambda: installs.append(True) or {
            "status": "installed", "exit_code": 0
        },
    )
    report = RecoveryRunner(store, recovery).attempt(
        incident, registered, identity=IDENTITY, now=NOW
    )
    assert report["action"] == "recovered"
    assert installs == [True]
    assert SENTINEL_SCHEDULER_RUNBOOK


def test_market_explorer_progress_recovery_runs_one_guarded_worker_tick():
    store = MemoryStateStore()
    registered, incident = _open_incident(
        store,
        key="market_explorer.maintenance_progress",
        code="MARKET_EXPLORER_CONVERGENCE_STALLED",
        authority="2026-09-11",
    )
    states = iter([
        CheckResult.failure(
            "market_explorer.maintenance_progress",
            failure_code="MARKET_EXPLORER_CONVERGENCE_STALLED",
            severity=Severity.CRITICAL,
            authority_identity="2026-09-11",
            observed={"state": "stalled", "stale_maintained_count": 3},
            checked_at=NOW,
        ),
        CheckResult.healthy(
            "market_explorer.maintenance_progress",
            authority_identity="2026-09-11",
            observed={"state": "converging", "stale_maintained_count": 2},
            checked_at=NOW,
        ),
    ])
    worker_calls = []
    recovery = build_safe_recovery_registry(
        client=object(),
        market_freshness_checker=lambda *a, **k: CheckResult.healthy(
            "market.freshness", checked_at=NOW
        ),
        lease_reconciler=lambda: 0,
        lease_checker=lambda *a, **k: CheckResult.healthy(
            "scrape.queue_leases", checked_at=NOW
        ),
        pricing_health_checker=lambda *a, **k: CheckResult.healthy(
            k["check_key"], authority_identity="2026-09-11", checked_at=NOW
        ),
        pricing_scheduler_checker=lambda *a, **k: CheckResult.healthy(
            "pricing.ebay.scheduler", checked_at=NOW
        ),
        market_explorer_scheduler_checker=lambda *a, **k: CheckResult.healthy(
            "market_explorer.maintenance_scheduler", checked_at=NOW
        ),
        market_explorer_progress_checker=lambda *a, **k: next(states),
        market_explorer_worker=lambda: worker_calls.append(True) or {
            "status": "advanced", "exit_code": 0
        },
    )
    report = RecoveryRunner(store, recovery).attempt(
        incident, registered, identity=IDENTITY, now=NOW
    )
    assert report["action"] == "recovered"
    assert worker_calls == [True]
    assert MARKET_EXPLORER_PROGRESS_RUNBOOK


def test_market_explorer_scheduler_recovery_uses_canonical_installer_then_verifies():
    store = MemoryStateStore()
    registered, incident = _open_incident(
        store,
        key="market_explorer.maintenance_scheduler",
        code="MARKET_EXPLORER_MAINTENANCE_SCHEDULE_MISSING",
        authority="market-explorer-prewarm-cron-v1",
    )
    states = iter([
        CheckResult.failure(
            "market_explorer.maintenance_scheduler",
            failure_code="MARKET_EXPLORER_MAINTENANCE_SCHEDULE_MISSING",
            severity=Severity.CRITICAL,
            authority_identity="market-explorer-prewarm-cron-v1",
            checked_at=NOW,
        ),
        CheckResult.healthy(
            "market_explorer.maintenance_scheduler",
            authority_identity="market-explorer-prewarm-cron-v1",
            checked_at=NOW,
        ),
    ])
    installs = []
    recovery = build_safe_recovery_registry(
        client=object(),
        market_freshness_checker=lambda *a, **k: CheckResult.healthy(
            "market.freshness", checked_at=NOW
        ),
        lease_reconciler=lambda: 0,
        lease_checker=lambda *a, **k: CheckResult.healthy(
            "scrape.queue_leases", checked_at=NOW
        ),
        pricing_health_checker=lambda *a, **k: CheckResult.healthy(
            k["check_key"], authority_identity="2026-09-11", checked_at=NOW
        ),
        pricing_scheduler_checker=lambda *a, **k: CheckResult.healthy(
            "pricing.ebay.scheduler",
            authority_identity="multi-source-pricing-cron-v1",
            checked_at=NOW,
        ),
        market_explorer_scheduler_checker=lambda *a, **k: next(states),
        market_explorer_cron_installer=lambda: installs.append(True) or {
            "status": "installed", "exit_code": 0
        },
    )
    report = RecoveryRunner(store, recovery).attempt(
        incident, registered, identity=IDENTITY, now=NOW
    )
    assert report["action"] == "recovered"
    assert installs == [True]
    assert MARKET_EXPLORER_SCHEDULER_RUNBOOK


def test_pricing_scheduler_recovery_uses_canonical_installer_then_verifies():
    store = MemoryStateStore()
    registered, incident = _open_incident(
        store,
        key="pricing.ebay.scheduler",
        code="EBAY_DAILY_SCHEDULE_MISSING",
        authority="multi-source-pricing-cron-v1",
    )
    states = iter([
        CheckResult.failure(
            "pricing.ebay.scheduler",
            failure_code="EBAY_DAILY_SCHEDULE_MISSING",
            severity=Severity.WARNING,
            authority_identity="multi-source-pricing-cron-v1",
            checked_at=NOW,
        ),
        CheckResult.healthy(
            "pricing.ebay.scheduler",
            authority_identity="multi-source-pricing-cron-v1",
            checked_at=NOW,
        ),
    ])
    installs = []
    recovery = build_safe_recovery_registry(
        client=object(),
        market_freshness_checker=lambda *a, **k: CheckResult.healthy(
            "market.freshness", checked_at=NOW
        ),
        lease_reconciler=lambda: 0,
        lease_checker=lambda *a, **k: CheckResult.healthy(
            "scrape.queue_leases", checked_at=NOW
        ),
        pricing_health_checker=lambda *a, **k: CheckResult.healthy(
            k["check_key"], authority_identity="2026-09-11", checked_at=NOW
        ),
        pricing_scheduler_checker=lambda *a, **k: next(states),
        pricing_cron_installer=lambda: installs.append(True) or {
            "status": "installed", "exit_code": 0
        },
    )
    report = RecoveryRunner(store, recovery).attempt(
        incident, registered, identity=IDENTITY, now=NOW
    )
    assert report["action"] == "recovered"
    assert installs == [True]
    assert PRICING_SCHEDULER_RUNBOOK


def test_lease_recovery_uses_narrow_reconciler_and_verifies_queue_clear():
    store = MemoryStateStore()
    registered, incident = _open_incident(
        store,
        key="scrape.queue_leases",
        code="scrape_job_lease_expired",
    )
    live_results = iter(
        [
            CheckResult.failure(
                "scrape.queue_leases",
                failure_code="scrape_job_lease_expired",
                authority_identity="2026-09-11",
                observed={"stale_running_jobs": 1},
                evidence={"stale_jobs": [{"id": 123}]},
                checked_at=NOW,
            ),
            CheckResult.healthy(
                "scrape.queue_leases",
                authority_identity="2026-09-11",
                observed={"stale_running_jobs": 0},
                checked_at=NOW,
            ),
        ]
    )
    reconciler_calls = []
    recovery = build_safe_recovery_registry(
        client=object(),
        publish_if_needed_fn=lambda *a, **k: {"status": "noop_already_current"},
        gate_evaluator=lambda *a, **k: SimpleNamespace(allowed=True, reason_code="allowed_complete"),
        market_freshness_checker=lambda *a, **k: CheckResult.healthy(
            "market.freshness", checked_at=NOW
        ),
        lease_reconciler=lambda: (reconciler_calls.append(True), 1)[1],
        lease_checker=lambda *a, **k: next(live_results),
    )
    report = RecoveryRunner(store, recovery).attempt(
        incident, registered, identity=IDENTITY, now=NOW
    )
    assert report["action"] == "recovered"
    assert reconciler_calls == [True]
    attempt = store.get_latest_recovery_attempt(incident.id, LEASE_RUNBOOK)
    assert attempt.result_json["execution"]["result"]["jobs_reconciled"] == 1


def test_triple_gate_required_before_recovery_config_is_accepted():
    base = dict(recovery_enabled=True, recovery_execution_ready=True)
    with pytest.raises(RuntimeError, match="STATE_WRITES"):
        SentinelConfig(**base).validate_kernel_v1()
    with pytest.raises(RuntimeError, match="PERSISTENCE_SCHEMA_READY"):
        SentinelConfig(state_writes_enabled=True, **base).validate_kernel_v1()
    SentinelConfig(
        state_writes_enabled=True,
        persistence_schema_ready=True,
        recovery_enabled=True,
        recovery_execution_ready=True,
    ).validate_kernel_v1()


def test_operational_recovery_waits_for_confirmation_then_recovers(monkeypatch):
    store = MemoryStateStore()
    checks = CheckRegistry()
    checks.register(
        "market.freshness",
        lambda ctx: CheckResult.failure(
            "market.freshness",
            failure_code="market_publication_stale",
            authority_identity="2026-09-11",
            checked_at=ctx.now,
        ),
        confirm_after=2,
    )
    monkeypatch.setattr(operational, "build_profile_registry", lambda *a, **k: checks)

    recovery = RecoveryRegistry()
    recovery.register(
        _generic_runbook(
            execute=lambda incident, ctx: RecoveryExecution.succeeded(
                result={"published": True}
            ),
            verify=lambda incident, ctx: CheckResult.healthy(
                incident.check_key,
                authority_identity=incident.authority_identity,
                checked_at=ctx.now,
            ),
        )
    )
    config = SentinelConfig(
        state_writes_enabled=True,
        persistence_schema_ready=True,
        recovery_enabled=True,
        recovery_execution_ready=True,
    )

    first = operational.run_profile(
        "fast", config=config, store=store, recovery_registry=recovery
    )
    assert first["healthy"] is False
    assert first["results"][0]["transition"]["action"] == "suspect"
    assert first["recovery"]["attempts"] == []

    second = operational.run_profile(
        "fast", config=config, store=store, recovery_registry=recovery
    )
    assert second["healthy"] is True
    assert second["status"] == "recovered"
    assert second["recovery"]["recovered_check_keys"] == ["market.freshness"]


def test_fast_registry_recovery_signatures_are_the_only_initial_mutating_checks():
    fast = build_fast_registry(client=object())
    assert fast.get("market.freshness").confirm_after == 2
    assert fast.get("scrape.queue_leases").confirm_after == 1
    assert PUBLICATION_RUNBOOK != LEASE_RUNBOOK



def test_publication_recovery_does_not_claim_success_when_publisher_already_running():
    store = MemoryStateStore()
    registered, incident = _open_incident(store)
    live_failure = lambda *a, **k: CheckResult.failure(
        "market.freshness",
        failure_code="market_publication_stale",
        authority_identity="2026-09-11",
        checked_at=NOW,
    )
    recovery = build_safe_recovery_registry(
        client=object(),
        publish_if_needed_fn=lambda *a, **k: {
            "market_date": "2026-09-11",
            "status": "noop_already_running",
            "exit_code": 4,
        },
        gate_evaluator=lambda *a, **k: SimpleNamespace(
            allowed=True, reason_code="allowed_complete", batch_id=48
        ),
        market_freshness_checker=live_failure,
        lease_reconciler=lambda: 0,
        lease_checker=lambda *a, **k: CheckResult.healthy(
            "scrape.queue_leases", checked_at=NOW
        ),
    )

    report = RecoveryRunner(store, recovery).attempt(
        incident, registered, identity=IDENTITY, now=NOW
    )

    assert report["action"] == "blocked"
    attempt = store.get_latest_recovery_attempt(incident.id, PUBLICATION_RUNBOOK)
    assert attempt is not None
    assert attempt.result_json["execution"]["result"]["status"] == "noop_already_running"
