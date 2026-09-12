from __future__ import annotations

from datetime import datetime, timezone

from backend.sentinel.incidents import IncidentManager
from backend.sentinel.models import (
    CheckResult,
    IncidentStatus,
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
from backend.sentinel.registry import CheckRegistry
from backend.sentinel.state import MemoryStateStore


NOW = datetime(2026, 9, 11, 20, 0, tzinfo=timezone.utc)
IDENTITY = RunnerIdentity(component="sentinel_vm", host="vm-1", build_sha="sha")


def _open_market_incident(store):
    registry = CheckRegistry()
    registered = registry.register(
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
    transition = IncidentManager(store).process(
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
    return registered, store.get_incident(transition.incident_id)


def _runner(store, *, precondition, execute, verify):
    registry = RecoveryRegistry()
    registry.register(
        RecoveryRunbook(
            key="contract-test-v1",
            version="1",
            check_key="market.freshness",
            failure_code="market_publication_stale",
            precondition=precondition,
            execute=execute,
            verify=verify,
        )
    )
    return RecoveryRunner(store, registry)


def test_invalid_precondition_contract_blocks_before_attempt_or_mutation():
    store = MemoryStateStore()
    registered, incident = _open_market_incident(store)
    execute_calls = []
    runner = _runner(
        store,
        precondition=lambda incident, ctx: {"eligible": True},
        execute=lambda incident, ctx: execute_calls.append(True),
        verify=lambda incident, ctx: CheckResult.healthy(
            incident.check_key,
            authority_identity=incident.authority_identity,
            checked_at=ctx.now,
        ),
    )

    report = runner.attempt(incident, registered, identity=IDENTITY, now=NOW)

    assert report["reason_code"] == "recovery_precondition_contract_invalid"
    assert execute_calls == []
    assert store.get_latest_recovery_attempt(incident.id, "contract-test-v1") is None
    assert store.get_incident(incident.id).recovery_attempt_count == 0


def test_invalid_execution_contract_escalates_and_records_possible_mutation():
    store = MemoryStateStore()
    registered, incident = _open_market_incident(store)
    runner = _runner(
        store,
        precondition=lambda incident, ctx: RecoveryDecision.allow(),
        execute=lambda incident, ctx: {"status": "looks-successful-but-invalid"},
        verify=lambda incident, ctx: CheckResult.healthy(
            incident.check_key,
            authority_identity=incident.authority_identity,
            checked_at=ctx.now,
        ),
    )

    report = runner.attempt(incident, registered, identity=IDENTITY, now=NOW)

    assert report["action"] == "escalated"
    assert report["reason_code"] == "recovery_execution_not_successful"
    attempt = store.get_latest_recovery_attempt(incident.id, "contract-test-v1")
    assert attempt.status is RecoveryAttemptStatus.FAILED
    assert attempt.result_json["execution"]["mutation_performed"] is True
    assert (
        attempt.result_json["execution"]["result"]["error_type"]
        == "recovery_execution_contract_invalid"
    )
    assert store.get_incident(incident.id).status is IncidentStatus.ESCALATED


def test_healthy_verification_for_wrong_authority_cannot_resolve_incident():
    store = MemoryStateStore()
    registered, incident = _open_market_incident(store)
    runner = _runner(
        store,
        precondition=lambda incident, ctx: RecoveryDecision.allow(),
        execute=lambda incident, ctx: RecoveryExecution.succeeded(
            result={"published": True}
        ),
        verify=lambda incident, ctx: CheckResult.healthy(
            incident.check_key,
            authority_identity="2026-09-12",
            checked_at=ctx.now,
        ),
    )

    report = runner.attempt(incident, registered, identity=IDENTITY, now=NOW)

    assert report["action"] == "escalated"
    assert report["reason_code"] == "recovery_verification_failed"
    assert report["verification_failure_code"] == "recovery_verification_contract_invalid"
    attempt = store.get_latest_recovery_attempt(incident.id, "contract-test-v1")
    assert attempt.status is RecoveryAttemptStatus.FAILED
    assert store.get_incident(incident.id).status is IncidentStatus.ESCALATED
    assert store.get_check_state(incident.check_key).current_incident_id == incident.id
