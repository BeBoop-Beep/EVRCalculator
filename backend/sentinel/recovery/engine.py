"""Bounded deterministic recovery execution for inDex Sentinel.

Recovery is deliberately conservative:
- an exact check/failure pair must map to one allowlisted runbook,
- a persistent Sentinel state store is mandatory,
- the incident must still be the active confirmed failure for its check,
- preconditions are re-read immediately before mutation,
- the attempt is persisted before mutation,
- one failed execution/verification escalates instead of looping,
- successful recovery is only accepted after a healthy deterministic verifier.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from datetime import datetime, timedelta
from typing import Any, Callable, Dict, Mapping, Optional
from uuid import uuid4

from backend.sentinel.evidence import bounded_evidence
from backend.sentinel.incidents import IncidentManager
from backend.sentinel.models import (
    CheckOutcome,
    CheckResult,
    CheckStateStatus,
    IncidentRecord,
    IncidentStatus,
    RecoveryAttemptRecord,
    RecoveryAttemptStatus,
    RunnerIdentity,
)
from backend.sentinel.registry import RegisteredCheck
from backend.sentinel.state import SentinelStateStore


@dataclass(frozen=True)
class RecoveryContext:
    now: datetime
    runner_identity: RunnerIdentity


@dataclass(frozen=True)
class RecoveryDecision:
    eligible: bool
    reason_code: str
    details: Mapping[str, Any] = field(default_factory=dict)

    @classmethod
    def allow(cls, reason_code: str = "preconditions_satisfied", **details: Any) -> "RecoveryDecision":
        return cls(True, reason_code, details)

    @classmethod
    def block(cls, reason_code: str, **details: Any) -> "RecoveryDecision":
        return cls(False, reason_code, details)


@dataclass(frozen=True)
class RecoveryExecution:
    status: RecoveryAttemptStatus
    result: Mapping[str, Any] = field(default_factory=dict)
    mutation_performed: bool = False

    @classmethod
    def succeeded(
        cls, *, result: Optional[Mapping[str, Any]] = None, mutation_performed: bool = True
    ) -> "RecoveryExecution":
        return cls(
            RecoveryAttemptStatus.SUCCEEDED,
            result=result or {},
            mutation_performed=mutation_performed,
        )

    @classmethod
    def failed(cls, *, result: Optional[Mapping[str, Any]] = None) -> "RecoveryExecution":
        return cls(RecoveryAttemptStatus.FAILED, result=result or {}, mutation_performed=True)

    @classmethod
    def blocked(cls, *, result: Optional[Mapping[str, Any]] = None) -> "RecoveryExecution":
        return cls(RecoveryAttemptStatus.BLOCKED, result=result or {}, mutation_performed=False)


@dataclass(frozen=True)
class RecoveryRunbook:
    key: str
    version: str
    check_key: str
    failure_code: str
    precondition: Callable[[IncidentRecord, RecoveryContext], RecoveryDecision]
    execute: Callable[[IncidentRecord, RecoveryContext], RecoveryExecution]
    verify: Callable[[IncidentRecord, RecoveryContext], CheckResult]
    max_attempts: int = 1
    cooldown_seconds: int = 60 * 60

    def __post_init__(self) -> None:
        if not self.key.strip() or not self.version.strip():
            raise ValueError("recovery runbook key/version are required")
        if not self.check_key.strip() or not self.failure_code.strip():
            raise ValueError("recovery runbook check/failure match is required")
        if self.max_attempts < 1:
            raise ValueError("recovery max_attempts must be positive")
        if self.cooldown_seconds < 0:
            raise ValueError("recovery cooldown_seconds cannot be negative")

    @property
    def match_key(self) -> tuple[str, str]:
        return (self.check_key, self.failure_code)


class RecoveryRegistry:
    """Exact-match recovery allowlist; no wildcard recovery is supported."""

    def __init__(self) -> None:
        self._runbooks: Dict[tuple[str, str], RecoveryRunbook] = {}

    def register(self, runbook: RecoveryRunbook) -> RecoveryRunbook:
        if runbook.match_key in self._runbooks:
            raise ValueError(f"duplicate recovery match: {runbook.match_key!r}")
        self._runbooks[runbook.match_key] = runbook
        return runbook

    def for_incident(self, incident: IncidentRecord) -> Optional[RecoveryRunbook]:
        return self._runbooks.get((incident.check_key, incident.failure_code))

    def matches(self) -> tuple[tuple[str, str], ...]:
        return tuple(sorted(self._runbooks))


def _bounded_mapping(value: Mapping[str, Any]) -> Dict[str, Any]:
    bounded = bounded_evidence(dict(value))
    if isinstance(bounded, dict):
        return bounded
    return {"value": bounded}


def _execution_error(exc: Exception) -> RecoveryExecution:
    # Do not persist arbitrary exception messages here: subprocess/HTTP/database
    # exceptions can contain credentials or capability URLs. The exception class
    # is enough to diagnose the recovery stage without leaking secret material.
    return RecoveryExecution(
        RecoveryAttemptStatus.FAILED,
        result={"error_type": exc.__class__.__name__},
        mutation_performed=False,
    )


class RecoveryRunner:
    def __init__(self, store: SentinelStateStore, registry: RecoveryRegistry) -> None:
        self.store = store
        self.registry = registry

    def attempt(
        self,
        incident: IncidentRecord,
        registered_check: RegisteredCheck,
        *,
        identity: RunnerIdentity,
        now: datetime,
    ) -> Dict[str, Any]:
        runbook = self.registry.for_incident(incident)
        if runbook is None:
            return {
                "action": "not_allowlisted",
                "incident_id": incident.id,
                "check_key": incident.check_key,
                "failure_code": incident.failure_code,
            }

        if not self.store.persistent:
            return {
                "action": "blocked",
                "reason_code": "recovery_requires_persistent_state",
                "incident_id": incident.id,
                "runbook": runbook.key,
            }
        if registered_check.key != incident.check_key:
            return {
                "action": "blocked",
                "reason_code": "registered_check_mismatch",
                "incident_id": incident.id,
                "runbook": runbook.key,
            }
        if incident.status is not IncidentStatus.OPEN:
            return {
                "action": "blocked",
                "reason_code": "incident_not_open",
                "incident_id": incident.id,
                "incident_status": incident.status.value,
                "runbook": runbook.key,
            }

        state = self.store.get_check_state(incident.check_key)
        if (
            state is None
            or state.status is not CheckStateStatus.FAILING
            or state.current_incident_id != incident.id
        ):
            return {
                "action": "blocked",
                "reason_code": "incident_not_active_check_failure",
                "incident_id": incident.id,
                "runbook": runbook.key,
            }

        if incident.recovery_attempt_count >= runbook.max_attempts:
            return {
                "action": "blocked",
                "reason_code": "recovery_attempt_limit_reached",
                "incident_id": incident.id,
                "runbook": runbook.key,
                "attempt_count": incident.recovery_attempt_count,
            }

        latest = self.store.get_latest_recovery_attempt(incident.id, runbook.key)
        if latest and latest.cooldown_until and latest.cooldown_until > now:
            return {
                "action": "blocked",
                "reason_code": "recovery_cooldown_active",
                "incident_id": incident.id,
                "runbook": runbook.key,
                "cooldown_until": latest.cooldown_until.isoformat(),
            }

        context = RecoveryContext(now=now, runner_identity=identity)
        try:
            decision = runbook.precondition(incident, context)
        except Exception as exc:
            return {
                "action": "blocked",
                "reason_code": "recovery_precondition_error",
                "incident_id": incident.id,
                "runbook": runbook.key,
                "error_type": exc.__class__.__name__,
            }
        if not decision.eligible:
            return {
                "action": "blocked",
                "reason_code": decision.reason_code,
                "incident_id": incident.id,
                "runbook": runbook.key,
                "preconditions": _bounded_mapping(decision.details),
            }

        attempt_number = incident.recovery_attempt_count + 1
        attempt = RecoveryAttemptRecord(
            id=str(uuid4()),
            incident_id=incident.id,
            runbook=runbook.key,
            runbook_version=runbook.version,
            started_at=now,
            status=RecoveryAttemptStatus.STARTED,
            attempt_number=attempt_number,
            preconditions_json=_bounded_mapping(decision.details),
        )
        # Persist the audit record and RECOVERING state before any mutation.
        self.store.save_recovery_attempt(attempt)
        incident.status = IncidentStatus.RECOVERING
        incident.recovery_eligible = True
        incident.recovery_attempt_count = attempt_number
        incident.last_seen_at = now
        self.store.upsert_incident(incident)

        try:
            execution = runbook.execute(incident, context)
        except Exception as exc:
            execution = _execution_error(exc)

        result_json: Dict[str, Any] = {
            "execution": {
                "status": execution.status.value,
                "mutation_performed": execution.mutation_performed,
                "result": _bounded_mapping(execution.result),
            }
        }

        if execution.status is not RecoveryAttemptStatus.SUCCEEDED:
            attempt.status = execution.status
            attempt.completed_at = now
            attempt.result_json = result_json
            attempt.cooldown_until = now + timedelta(seconds=runbook.cooldown_seconds)
            self.store.save_recovery_attempt(attempt)
            incident.status = IncidentStatus.ESCALATED
            self.store.upsert_incident(incident)
            return {
                "action": "escalated",
                "reason_code": "recovery_execution_not_successful",
                "incident_id": incident.id,
                "runbook": runbook.key,
                "attempt_number": attempt_number,
                "execution_status": execution.status.value,
            }

        try:
            verification = runbook.verify(incident, context)
        except Exception as exc:
            verification = CheckResult.execution_error(
                incident.check_key,
                failure_code="recovery_verification_execution_failed",
                authority_identity=incident.authority_identity,
                evidence={"exception_type": exc.__class__.__name__},
                checked_at=now,
            )

        if verification.check_key != incident.check_key:
            verification = CheckResult.execution_error(
                incident.check_key,
                failure_code="recovery_verification_contract_invalid",
                authority_identity=incident.authority_identity,
                evidence={"returned_check_key": verification.check_key},
                checked_at=now,
            )

        result_json["verification"] = {
            "outcome": verification.outcome.value,
            "failure_code": verification.failure_code,
            "authority_identity": verification.authority_identity,
            "observed": _bounded_mapping(verification.observed),
        }

        if verification.outcome is CheckOutcome.HEALTHY:
            attempt.status = RecoveryAttemptStatus.SUCCEEDED
            attempt.completed_at = now
            attempt.result_json = result_json
            self.store.save_recovery_attempt(attempt)
            transition = IncidentManager(self.store).process(
                registered_check, verification, identity
            )
            return {
                "action": "recovered",
                "incident_id": incident.id,
                "runbook": runbook.key,
                "attempt_number": attempt_number,
                "verification_transition": transition.action,
            }

        attempt.status = RecoveryAttemptStatus.FAILED
        attempt.completed_at = now
        attempt.result_json = result_json
        attempt.cooldown_until = now + timedelta(seconds=runbook.cooldown_seconds)
        self.store.save_recovery_attempt(attempt)
        # Do not feed a failed verifier into IncidentManager here. A changed
        # failure signature could close the original incident and create a new
        # confirmation window. Instead, escalate this recovery attempt and let
        # the next normal Sentinel observation establish the next incident state.
        incident.status = IncidentStatus.ESCALATED
        incident.last_seen_at = now
        self.store.upsert_incident(incident)
        return {
            "action": "escalated",
            "reason_code": "recovery_verification_failed",
            "incident_id": incident.id,
            "runbook": runbook.key,
            "attempt_number": attempt_number,
            "verification_failure_code": verification.failure_code,
        }
