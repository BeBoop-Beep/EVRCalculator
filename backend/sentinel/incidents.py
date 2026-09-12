"""Deterministic Sentinel incident confirmation and lifecycle transitions."""

from __future__ import annotations

from uuid import uuid4

from backend.sentinel.evidence import bounded_evidence
from backend.sentinel.fingerprint import incident_fingerprint, observation_hash
from backend.sentinel.models import (
    CheckOutcome,
    CheckResult,
    CheckState,
    CheckStateStatus,
    IncidentRecord,
    IncidentStatus,
    IncidentTransition,
    RunnerIdentity,
)
from backend.sentinel.registry import RegisteredCheck
from backend.sentinel.state import SentinelStateStore


def _context_value(result: CheckResult, key: str):
    if key in result.observed:
        return result.observed.get(key)
    return result.evidence.get(key)


def _optional_int(value):
    try:
        return int(value) if value is not None else None
    except (TypeError, ValueError):
        return None


class IncidentManager:
    def __init__(self, store: SentinelStateStore) -> None:
        self.store = store

    def process(
        self,
        registered: RegisteredCheck,
        result: CheckResult,
        identity: RunnerIdentity,
    ) -> IncidentTransition:
        previous = self.store.get_check_state(result.check_key)
        state = previous or CheckState(check_key=result.check_key)
        now = result.checked_at

        sanitized_evidence = bounded_evidence(dict(result.evidence))
        safe_result = CheckResult(
            check_key=result.check_key,
            outcome=result.outcome,
            severity=result.severity,
            failure_code=result.failure_code,
            authority_identity=result.authority_identity,
            expected=dict(result.expected),
            observed=dict(result.observed),
            evidence=sanitized_evidence if isinstance(sanitized_evidence, dict) else {
                "evidence": sanitized_evidence
            },
            checked_at=result.checked_at,
        )
        obs_hash = observation_hash(safe_result)
        observation = {
            "outcome": safe_result.outcome.value,
            "failure_code": safe_result.failure_code,
            "authority_identity": safe_result.authority_identity,
            "expected": dict(safe_result.expected),
            "observed": dict(safe_result.observed),
        }

        if safe_result.outcome == CheckOutcome.HEALTHY:
            resolved_id = state.current_incident_id
            if resolved_id:
                self.store.resolve_incident(resolved_id, now)
            state.status = CheckStateStatus.HEALTHY
            state.last_checked_at = now
            state.last_success_at = now
            state.first_failure_at = None
            state.last_failure_at = None
            state.consecutive_failures = 0
            state.current_incident_id = None
            state.last_observation_json = observation
            state.observation_hash = obs_hash
            state.runner_build_sha = identity.build_sha
            self.store.save_check_state(state)
            return IncidentTransition(
                action="resolved" if resolved_id else "healthy",
                check_status=CheckStateStatus.HEALTHY,
                incident_id=resolved_id,
            )

        fingerprint = incident_fingerprint(
            safe_result.check_key,
            safe_result.failure_code or "unknown_failure",
            safe_result.authority_identity,
        )
        current = (
            self.store.get_incident(state.current_incident_id)
            if state.current_incident_id
            else None
        )

        previous_signature = (
            state.last_observation_json.get("failure_code"),
            state.last_observation_json.get("authority_identity"),
        )
        current_signature = (
            safe_result.failure_code,
            safe_result.authority_identity,
        )
        signature_changed = (
            state.status != CheckStateStatus.HEALTHY
            and bool(state.last_observation_json)
            and previous_signature != current_signature
        )

        if signature_changed:
            # A new failure authority is a new incident candidate. Close any
            # confirmed prior incident and require the new candidate to satisfy
            # its own confirmation threshold.
            if current:
                self.store.resolve_incident(current.id, now)
            current = None
            state.current_incident_id = None
            previous_failures = 0
            first_failure = now
        else:
            previous_failures = state.consecutive_failures
            if state.status == CheckStateStatus.HEALTHY:
                previous_failures = 0
            first_failure = state.first_failure_at or now

        failures = previous_failures + 1

        state.last_checked_at = now
        state.first_failure_at = first_failure
        state.last_failure_at = now
        state.consecutive_failures = failures
        state.last_observation_json = observation
        state.observation_hash = obs_hash
        state.runner_build_sha = identity.build_sha

        if failures < registered.confirm_after:
            state.status = CheckStateStatus.SUSPECT
            self.store.save_check_state(state)
            return IncidentTransition(
                action="suspect",
                check_status=CheckStateStatus.SUSPECT,
            )

        state.status = CheckStateStatus.FAILING
        incident = current or self.store.get_open_incident_by_fingerprint(fingerprint)
        action = "updated"
        if incident is None:
            incident = IncidentRecord(
                id=str(uuid4()),
                fingerprint=fingerprint,
                check_key=safe_result.check_key,
                severity=safe_result.severity,
                status=IncidentStatus.OPEN,
                failure_code=safe_result.failure_code or "unknown_failure",
                authority_identity=safe_result.authority_identity,
                first_seen_at=first_failure,
                last_seen_at=now,
                market_date=(
                    str(_context_value(safe_result, "market_date"))
                    if _context_value(safe_result, "market_date")
                    else None
                ),
                batch_id=_optional_int(_context_value(safe_result, "batch_id")),
                generation_id=(
                    str(_context_value(safe_result, "generation_id"))
                    if _context_value(safe_result, "generation_id")
                    else None
                ),
                deployment_sha=(
                    str(_context_value(safe_result, "deployment_sha"))
                    if _context_value(safe_result, "deployment_sha")
                    else None
                ),
                expected_json=dict(safe_result.expected),
                observed_json=dict(safe_result.observed),
                evidence_json=dict(safe_result.evidence),
                recovery_eligible=False,
                ai_triage_status="disabled",
            )
            action = "opened"
        else:
            incident.last_seen_at = now
            incident.severity = safe_result.severity
            incident.expected_json = dict(safe_result.expected)
            incident.observed_json = dict(safe_result.observed)
            incident.evidence_json = dict(safe_result.evidence)

        self.store.upsert_incident(incident)
        state.current_incident_id = incident.id
        self.store.save_check_state(state)
        return IncidentTransition(
            action=action,
            check_status=CheckStateStatus.FAILING,
            incident_id=incident.id,
            fingerprint=fingerprint,
        )
