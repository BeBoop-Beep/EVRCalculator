"""Sentinel check for the host-local production DB safety fence."""
from __future__ import annotations

from typing import Callable, Optional

from backend.db.services.production_db_safety import (
    HOLD_ABSENT,
    HOLD_ACTIVE_VALID,
    HOLD_INVALID_EMPTY,
    HOLD_INVALID_MALFORMED,
    HOLD_INVALID_PATH,
    HOLD_INACCESSIBLE,
    MaintenanceHoldInspection,
    inspect_maintenance_hold,
)
from backend.sentinel.models import CheckResult, Severity
from backend.sentinel.registry import CheckContext


DB_SAFETY_HOLD_CHECK_KEY = "database.safety_hold"
DB_SAFETY_HOLD_AUTHORITY = "host-local-db-safety-hold-v1"

FAILURE_ACTIVE = "DATABASE_SAFETY_HOLD_ACTIVE"
FAILURE_INVALID_EMPTY = "DATABASE_SAFETY_HOLD_INVALID_EMPTY"
FAILURE_INVALID_MALFORMED = "DATABASE_SAFETY_HOLD_INVALID_MALFORMED"
FAILURE_INVALID_PATH = "DATABASE_SAFETY_HOLD_INVALID_PATH"
FAILURE_INACCESSIBLE = "DATABASE_SAFETY_HOLD_INACCESSIBLE"


def check_db_safety_hold(
    context: CheckContext,
    *,
    inspector: Optional[Callable[[], MaintenanceHoldInspection]] = None,
) -> CheckResult:
    resolved = (inspector or inspect_maintenance_hold)()
    observed = resolved.to_dict()
    expected = {"state": HOLD_ABSENT}

    if resolved.state == HOLD_ABSENT:
        return CheckResult.healthy(
            DB_SAFETY_HOLD_CHECK_KEY,
            authority_identity=DB_SAFETY_HOLD_AUTHORITY,
            expected=expected,
            observed=observed,
            checked_at=context.now,
        )

    failure_by_state = {
        HOLD_ACTIVE_VALID: FAILURE_ACTIVE,
        HOLD_INVALID_EMPTY: FAILURE_INVALID_EMPTY,
        HOLD_INVALID_MALFORMED: FAILURE_INVALID_MALFORMED,
        HOLD_INVALID_PATH: FAILURE_INVALID_PATH,
        HOLD_INACCESSIBLE: FAILURE_INACCESSIBLE,
    }
    return CheckResult.failure(
        DB_SAFETY_HOLD_CHECK_KEY,
        failure_code=failure_by_state.get(resolved.state, FAILURE_INACCESSIBLE),
        severity=Severity.CRITICAL,
        authority_identity=DB_SAFETY_HOLD_AUTHORITY,
        expected=expected,
        observed=observed,
        checked_at=context.now,
    )
