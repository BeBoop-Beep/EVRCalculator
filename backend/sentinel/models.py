"""Typed contracts shared by Sentinel checks, persistence, and incidents."""

from __future__ import annotations

from dataclasses import dataclass, field
from datetime import datetime, timezone
from enum import Enum
from typing import Any, Dict, Mapping, Optional


class Severity(str, Enum):
    INFO = "info"
    WARNING = "warning"
    ERROR = "error"
    CRITICAL = "critical"


class CheckOutcome(str, Enum):
    HEALTHY = "healthy"
    FAILURE = "failure"
    ERROR = "error"


class CheckStateStatus(str, Enum):
    HEALTHY = "healthy"
    SUSPECT = "suspect"
    FAILING = "failing"


class IncidentStatus(str, Enum):
    OPEN = "open"
    RECOVERING = "recovering"
    ESCALATED = "escalated"
    RESOLVED = "resolved"


def utc_now() -> datetime:
    return datetime.now(timezone.utc)


def _require_aware(value: datetime, field_name: str) -> None:
    if value.tzinfo is None or value.utcoffset() is None:
        raise ValueError(f"{field_name} must be timezone-aware")


@dataclass(frozen=True)
class RunnerIdentity:
    component: str
    host: str
    build_sha: str

    def to_dict(self) -> Dict[str, str]:
        return {
            "component": self.component,
            "host": self.host,
            "build_sha": self.build_sha,
        }


@dataclass(frozen=True)
class CheckResult:
    check_key: str
    outcome: CheckOutcome
    severity: Severity = Severity.INFO
    failure_code: Optional[str] = None
    authority_identity: Optional[str] = None
    expected: Mapping[str, Any] = field(default_factory=dict)
    observed: Mapping[str, Any] = field(default_factory=dict)
    evidence: Mapping[str, Any] = field(default_factory=dict)
    checked_at: datetime = field(default_factory=utc_now)

    def __post_init__(self) -> None:
        if not self.check_key.strip():
            raise ValueError("check_key is required")
        _require_aware(self.checked_at, "checked_at")
        if self.outcome in {CheckOutcome.FAILURE, CheckOutcome.ERROR} and not self.failure_code:
            raise ValueError("failure/error CheckResult requires failure_code")

    @classmethod
    def healthy(
        cls,
        check_key: str,
        *,
        expected: Optional[Mapping[str, Any]] = None,
        observed: Optional[Mapping[str, Any]] = None,
        evidence: Optional[Mapping[str, Any]] = None,
        authority_identity: Optional[str] = None,
        checked_at: Optional[datetime] = None,
    ) -> "CheckResult":
        return cls(
            check_key=check_key,
            outcome=CheckOutcome.HEALTHY,
            severity=Severity.INFO,
            authority_identity=authority_identity,
            expected=expected or {},
            observed=observed or {},
            evidence=evidence or {},
            checked_at=checked_at or utc_now(),
        )

    @classmethod
    def failure(
        cls,
        check_key: str,
        *,
        failure_code: str,
        severity: Severity = Severity.ERROR,
        expected: Optional[Mapping[str, Any]] = None,
        observed: Optional[Mapping[str, Any]] = None,
        evidence: Optional[Mapping[str, Any]] = None,
        authority_identity: Optional[str] = None,
        checked_at: Optional[datetime] = None,
    ) -> "CheckResult":
        return cls(
            check_key=check_key,
            outcome=CheckOutcome.FAILURE,
            severity=severity,
            failure_code=failure_code,
            authority_identity=authority_identity,
            expected=expected or {},
            observed=observed or {},
            evidence=evidence or {},
            checked_at=checked_at or utc_now(),
        )

    @classmethod
    def execution_error(
        cls,
        check_key: str,
        *,
        failure_code: str = "check_execution_failed",
        severity: Severity = Severity.CRITICAL,
        evidence: Optional[Mapping[str, Any]] = None,
        authority_identity: Optional[str] = None,
        checked_at: Optional[datetime] = None,
    ) -> "CheckResult":
        return cls(
            check_key=check_key,
            outcome=CheckOutcome.ERROR,
            severity=severity,
            failure_code=failure_code,
            authority_identity=authority_identity,
            evidence=evidence or {},
            checked_at=checked_at or utc_now(),
        )

    def to_dict(self) -> Dict[str, Any]:
        return {
            "check_key": self.check_key,
            "outcome": self.outcome.value,
            "severity": self.severity.value,
            "failure_code": self.failure_code,
            "authority_identity": self.authority_identity,
            "expected": dict(self.expected),
            "observed": dict(self.observed),
            "evidence": dict(self.evidence),
            "checked_at": self.checked_at.isoformat(),
        }


@dataclass
class CheckState:
    check_key: str
    status: CheckStateStatus = CheckStateStatus.HEALTHY
    last_checked_at: Optional[datetime] = None
    last_success_at: Optional[datetime] = None
    first_failure_at: Optional[datetime] = None
    last_failure_at: Optional[datetime] = None
    consecutive_failures: int = 0
    current_incident_id: Optional[str] = None
    last_observation_json: Dict[str, Any] = field(default_factory=dict)
    observation_hash: Optional[str] = None
    runner_build_sha: Optional[str] = None

    def __post_init__(self) -> None:
        if self.consecutive_failures < 0:
            raise ValueError("consecutive_failures cannot be negative")


@dataclass
class IncidentRecord:
    id: str
    fingerprint: str
    check_key: str
    severity: Severity
    status: IncidentStatus
    failure_code: str
    authority_identity: Optional[str]
    first_seen_at: datetime
    last_seen_at: datetime
    resolved_at: Optional[datetime] = None
    market_date: Optional[str] = None
    batch_id: Optional[int] = None
    generation_id: Optional[str] = None
    deployment_sha: Optional[str] = None
    expected_json: Dict[str, Any] = field(default_factory=dict)
    observed_json: Dict[str, Any] = field(default_factory=dict)
    evidence_json: Dict[str, Any] = field(default_factory=dict)
    recovery_eligible: bool = False
    recovery_attempt_count: int = 0
    ai_triage_status: str = "disabled"

    def __post_init__(self) -> None:
        _require_aware(self.first_seen_at, "first_seen_at")
        _require_aware(self.last_seen_at, "last_seen_at")
        if self.resolved_at is not None:
            _require_aware(self.resolved_at, "resolved_at")


@dataclass(frozen=True)
class IncidentTransition:
    action: str
    check_status: CheckStateStatus
    incident_id: Optional[str] = None
    fingerprint: Optional[str] = None
