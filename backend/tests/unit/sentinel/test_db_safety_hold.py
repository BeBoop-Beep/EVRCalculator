from __future__ import annotations

from datetime import datetime, timezone

from backend.db.services.production_db_safety import (
    HOLD_ABSENT,
    HOLD_ACTIVE_VALID,
    HOLD_INVALID_EMPTY,
    HOLD_INVALID_MALFORMED,
    MaintenanceHoldInspection,
)
from backend.sentinel.checks.db_safety import (
    DB_SAFETY_HOLD_CHECK_KEY,
    FAILURE_ACTIVE,
    FAILURE_INVALID_EMPTY,
    FAILURE_INVALID_MALFORMED,
    check_db_safety_hold,
)
from backend.sentinel.checks.registry import build_fast_registry
from backend.sentinel.models import CheckOutcome, RunnerIdentity, Severity
from backend.sentinel.registry import CheckContext


CTX = CheckContext(
    now=datetime(2026, 10, 2, 17, 0, tzinfo=timezone.utc),
    runner_identity=RunnerIdentity(
        component="sentinel_vm",
        host="vm-1",
        build_sha="sha",
    ),
)


def _inspection(state: str) -> MaintenanceHoldInspection:
    return MaintenanceHoldInspection(
        state=state,
        path="/home/ubuntu/state/db-safety/hold.json",
        size_bytes=0 if state == HOLD_INVALID_EMPTY else 64,
        mode=0o600,
        owner="ubuntu",
        reason="operator_hold" if state == HOLD_ACTIVE_VALID else None,
    )


def test_absent_db_safety_hold_is_healthy():
    result = check_db_safety_hold(
        CTX, inspector=lambda: _inspection(HOLD_ABSENT)
    )
    assert result.outcome is CheckOutcome.HEALTHY
    assert result.check_key == DB_SAFETY_HOLD_CHECK_KEY


def test_valid_db_safety_hold_remains_critical_and_not_self_described_as_corrupt():
    result = check_db_safety_hold(
        CTX, inspector=lambda: _inspection(HOLD_ACTIVE_VALID)
    )
    assert result.outcome is CheckOutcome.FAILURE
    assert result.severity is Severity.CRITICAL
    assert result.failure_code == FAILURE_ACTIVE


def test_empty_hold_has_exact_recoverable_failure_signature():
    result = check_db_safety_hold(
        CTX, inspector=lambda: _inspection(HOLD_INVALID_EMPTY)
    )
    assert result.outcome is CheckOutcome.FAILURE
    assert result.failure_code == FAILURE_INVALID_EMPTY


def test_nonempty_malformed_hold_has_nonrecoverable_failure_signature():
    result = check_db_safety_hold(
        CTX, inspector=lambda: _inspection(HOLD_INVALID_MALFORMED)
    )
    assert result.outcome is CheckOutcome.FAILURE
    assert result.failure_code == FAILURE_INVALID_MALFORMED


def test_fast_profile_runs_db_safety_before_market_freshness():
    registry = build_fast_registry(client=object())
    keys = list(registry.keys())
    assert DB_SAFETY_HOLD_CHECK_KEY in keys
    assert keys.index(DB_SAFETY_HOLD_CHECK_KEY) < keys.index("market.freshness")
