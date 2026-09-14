from __future__ import annotations

from datetime import datetime, timedelta, timezone
from types import SimpleNamespace

import pytest

import backend.sentinel.operational as operational
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
    LEASE_RUNBOOK,
    PUBLICATION_RUNBOOK,
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


def test_p6_allowlist_contains_only_publication_stale_and_expired_lease():
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
        ("market.freshness", "market_publication_stale"),
        ("scrape.queue_leases", "scrape_job_lease_expired"),
    )


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
