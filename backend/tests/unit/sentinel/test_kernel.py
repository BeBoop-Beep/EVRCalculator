from datetime import datetime, timedelta, timezone

import pytest

from backend.sentinel.evidence import bounded_evidence, sanitize_evidence
from backend.sentinel.fingerprint import incident_fingerprint
from backend.sentinel.incidents import IncidentManager
from backend.sentinel.models import (
    CheckResult,
    CheckStateStatus,
    IncidentStatus,
    RunnerIdentity,
    Severity,
)
from backend.sentinel.registry import CheckRegistry
from backend.sentinel.state import MemoryStateStore, NoopStateStore
from backend.sentinel.triage import DisabledTriageProvider


NOW = datetime(2026, 9, 11, 19, 30, tzinfo=timezone.utc)
IDENTITY = RunnerIdentity(component="sentinel_vm", host="vm-1", build_sha="abc123")


def _failure(key="market.publication", authority="2026-09-11", code="stale"):
    return CheckResult.failure(
        key,
        failure_code=code,
        severity=Severity.CRITICAL,
        authority_identity=authority,
        expected={"market_date": "2026-09-11"},
        observed={"market_date": "2026-09-10"},
        evidence={"market_date": "2026-09-11", "token": "must-not-persist"},
        checked_at=NOW,
    )


def test_registry_rejects_duplicate_and_invalid_keys():
    registry = CheckRegistry()
    registry.register("market.publication", lambda ctx: _failure())
    with pytest.raises(ValueError, match="duplicate"):
        registry.register("market.publication", lambda ctx: _failure())
    with pytest.raises(ValueError):
        registry.register("BAD KEY", lambda ctx: _failure())


def test_registry_confirmation_threshold_must_be_positive():
    with pytest.raises(ValueError, match="confirm_after"):
        CheckRegistry().register("market.publication", lambda ctx: _failure(), confirm_after=0)


def test_failure_requires_failure_code():
    with pytest.raises(ValueError, match="failure_code"):
        CheckResult(
            check_key="market.publication",
            outcome="failure",  # type: ignore[arg-type]
            checked_at=NOW,
        )


def test_incident_fingerprint_is_stable_and_authority_scoped():
    a = incident_fingerprint("market.publication", "stale", "2026-09-11")
    b = incident_fingerprint("market.publication", "stale", "2026-09-11")
    c = incident_fingerprint("market.publication", "stale", "2026-09-12")
    assert a == b
    assert a != c


def test_evidence_redacts_secrets_and_bounds_strings():
    value = sanitize_evidence({
        "token": "abc",
        "nested": {"SLACK_ALERT_WEBHOOK_URL": "https://secret"},
        "message": "x" * 600,
    })
    assert value["token"] == "[REDACTED]"
    assert value["nested"]["SLACK_ALERT_WEBHOOK_URL"] == "[REDACTED]"
    assert len(value["message"]) < 600
    assert "TRUNCATED" in value["message"]


def test_evidence_hard_byte_cap_returns_hash_preview():
    rendered = bounded_evidence({"rows": ["x" * 1000 for _ in range(40)]}, max_bytes=500)
    assert rendered["_truncated"] is True
    assert len(rendered["sha256"]) == 64


def test_noop_store_is_nonpersistent():
    store = NoopStateStore()
    assert store.persistent is False
    assert store.get_check_state("market.publication") is None
    store.record_heartbeat(IDENTITY, NOW, {"x": 1})


def test_two_failures_confirm_one_incident_and_redact_evidence():
    store = MemoryStateStore()
    manager = IncidentManager(store)
    registered = CheckRegistry().register(
        "market.publication", lambda ctx: _failure(), confirm_after=2
    )

    first = manager.process(registered, _failure(), IDENTITY)
    assert first.action == "suspect"
    assert first.incident_id is None
    state = store.get_check_state("market.publication")
    assert state.status == CheckStateStatus.SUSPECT
    assert state.consecutive_failures == 1

    second_result = CheckResult.failure(
        "market.publication",
        failure_code="stale",
        severity=Severity.CRITICAL,
        authority_identity="2026-09-11",
        evidence={"token": "secret"},
        checked_at=NOW + timedelta(minutes=5),
    )
    second = manager.process(registered, second_result, IDENTITY)
    assert second.action == "opened"
    assert second.incident_id
    incident = store.get_incident(second.incident_id)
    assert incident.status == IncidentStatus.OPEN
    assert incident.evidence_json["token"] == "[REDACTED]"


def test_immediate_confirmation_can_open_on_first_failure():
    store = MemoryStateStore()
    registered = CheckRegistry().register(
        "generation.pointer",
        lambda ctx: _failure("generation.pointer"),
        confirm_after=1,
    )
    transition = IncidentManager(store).process(
        registered, _failure("generation.pointer"), IDENTITY
    )
    assert transition.action == "opened"


def test_same_failure_updates_existing_incident_instead_of_spamming():
    store = MemoryStateStore()
    registered = CheckRegistry().register(
        "market.publication", lambda ctx: _failure(), confirm_after=1
    )
    manager = IncidentManager(store)
    first = manager.process(registered, _failure(), IDENTITY)
    later = CheckResult.failure(
        "market.publication",
        failure_code="stale",
        severity=Severity.CRITICAL,
        authority_identity="2026-09-11",
        observed={"market_date": "2026-09-09"},
        checked_at=NOW + timedelta(minutes=5),
    )
    second = manager.process(registered, later, IDENTITY)
    assert second.action == "updated"
    assert second.incident_id == first.incident_id
    assert len(store.incidents) == 1


def test_healthy_result_resolves_open_incident_and_resets_state():
    store = MemoryStateStore()
    registered = CheckRegistry().register(
        "market.publication", lambda ctx: _failure(), confirm_after=1
    )
    manager = IncidentManager(store)
    opened = manager.process(registered, _failure(), IDENTITY)
    healthy = CheckResult.healthy(
        "market.publication", checked_at=NOW + timedelta(minutes=5)
    )
    resolved = manager.process(registered, healthy, IDENTITY)
    assert resolved.action == "resolved"
    incident = store.get_incident(opened.incident_id)
    assert incident.status == IncidentStatus.RESOLVED
    state = store.get_check_state("market.publication")
    assert state.status == CheckStateStatus.HEALTHY
    assert state.consecutive_failures == 0
    assert state.current_incident_id is None


def test_new_authority_resolves_prior_active_failure_and_opens_new_one():
    store = MemoryStateStore()
    registered = CheckRegistry().register(
        "market.publication", lambda ctx: _failure(), confirm_after=1
    )
    manager = IncidentManager(store)
    first = manager.process(registered, _failure(authority="2026-09-11"), IDENTITY)
    second = manager.process(
        registered,
        _failure(authority="2026-09-12"),
        IDENTITY,
    )
    assert second.action == "opened"
    assert second.incident_id != first.incident_id
    assert store.get_incident(first.incident_id).status == IncidentStatus.RESOLVED


def test_new_authority_gets_its_own_confirmation_window():
    store = MemoryStateStore()
    registered = CheckRegistry().register(
        "market.publication", lambda ctx: _failure(), confirm_after=2
    )
    manager = IncidentManager(store)
    manager.process(registered, _failure(authority="2026-09-11"), IDENTITY)
    opened = manager.process(
        registered,
        CheckResult.failure(
            "market.publication",
            failure_code="stale",
            severity=Severity.CRITICAL,
            authority_identity="2026-09-11",
            checked_at=NOW + timedelta(minutes=5),
        ),
        IDENTITY,
    )
    assert opened.action == "opened"

    rollover = manager.process(
        registered,
        CheckResult.failure(
            "market.publication",
            failure_code="stale",
            severity=Severity.CRITICAL,
            authority_identity="2026-09-12",
            checked_at=NOW + timedelta(minutes=10),
        ),
        IDENTITY,
    )
    assert rollover.action == "suspect"
    assert store.get_incident(opened.incident_id).status == IncidentStatus.RESOLVED
    state = store.get_check_state("market.publication")
    assert state.consecutive_failures == 1
    assert state.current_incident_id is None


def test_execution_error_uses_same_confirmation_pipeline():
    store = MemoryStateStore()
    registered = CheckRegistry().register(
        "backend.health", lambda ctx: None, confirm_after=1
    )
    result = CheckResult.execution_error(
        "backend.health",
        evidence={"exception_type": "TimeoutError"},
        checked_at=NOW,
    )
    transition = IncidentManager(store).process(registered, result, IDENTITY)
    assert transition.action == "opened"
    incident = store.get_incident(transition.incident_id)
    assert incident.failure_code == "check_execution_failed"


def test_disabled_triage_never_makes_request():
    result = DisabledTriageProvider().triage({"incident": "x"})
    assert result.status == "disabled"
    assert result.metadata["request_made"] is False
