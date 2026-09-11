"""Persistence boundary for Sentinel state.

The default Prompt-2 runtime uses NoopStateStore. Supabase writes are only
possible when SENTINEL_STATE_WRITES_ENABLED=true and the proposed Sentinel
schema has been explicitly deployed in a later activation step.
"""

from __future__ import annotations

from dataclasses import replace
from datetime import datetime, timezone
from typing import Any, Dict, Optional, Protocol

from backend.sentinel.models import (
    CheckState,
    CheckStateStatus,
    IncidentRecord,
    IncidentStatus,
    RunnerIdentity,
    Severity,
)


_OPEN_INCIDENT_STATUSES = {
    IncidentStatus.OPEN,
    IncidentStatus.RECOVERING,
    IncidentStatus.ESCALATED,
}


def _iso(value: Optional[datetime]) -> Optional[str]:
    return value.isoformat() if value else None


def _dt(value: Any) -> Optional[datetime]:
    if value is None or value == "":
        return None
    parsed = datetime.fromisoformat(str(value).replace("Z", "+00:00"))
    if parsed.tzinfo is None:
        parsed = parsed.replace(tzinfo=timezone.utc)
    return parsed


class SentinelStateStore(Protocol):
    persistent: bool

    def get_check_state(self, check_key: str) -> Optional[CheckState]: ...
    def save_check_state(self, state: CheckState) -> None: ...
    def get_incident(self, incident_id: str) -> Optional[IncidentRecord]: ...
    def get_open_incident_by_fingerprint(
        self, fingerprint: str
    ) -> Optional[IncidentRecord]: ...
    def upsert_incident(self, incident: IncidentRecord) -> None: ...
    def resolve_incident(self, incident_id: str, resolved_at: datetime) -> None: ...
    def record_heartbeat(
        self,
        identity: RunnerIdentity,
        at: datetime,
        metadata: Dict[str, Any],
    ) -> None: ...


class NoopStateStore:
    """Production-inert store used until Sentinel persistence is activated."""

    persistent = False

    def get_check_state(self, check_key: str) -> Optional[CheckState]:
        return None

    def save_check_state(self, state: CheckState) -> None:
        return None

    def get_incident(self, incident_id: str) -> Optional[IncidentRecord]:
        return None

    def get_open_incident_by_fingerprint(
        self, fingerprint: str
    ) -> Optional[IncidentRecord]:
        return None

    def upsert_incident(self, incident: IncidentRecord) -> None:
        return None

    def resolve_incident(self, incident_id: str, resolved_at: datetime) -> None:
        return None

    def record_heartbeat(
        self,
        identity: RunnerIdentity,
        at: datetime,
        metadata: Dict[str, Any],
    ) -> None:
        return None


class MemoryStateStore:
    """Deterministic in-memory implementation used by unit tests."""

    persistent = True

    def __init__(self) -> None:
        self.check_states: Dict[str, CheckState] = {}
        self.incidents: Dict[str, IncidentRecord] = {}
        self.heartbeats: Dict[tuple[str, str], Dict[str, Any]] = {}

    def get_check_state(self, check_key: str) -> Optional[CheckState]:
        value = self.check_states.get(check_key)
        return replace(value) if value else None

    def save_check_state(self, state: CheckState) -> None:
        self.check_states[state.check_key] = replace(state)

    def get_incident(self, incident_id: str) -> Optional[IncidentRecord]:
        value = self.incidents.get(incident_id)
        return replace(value) if value else None

    def get_open_incident_by_fingerprint(
        self, fingerprint: str
    ) -> Optional[IncidentRecord]:
        for incident in self.incidents.values():
            if (
                incident.fingerprint == fingerprint
                and incident.status in _OPEN_INCIDENT_STATUSES
            ):
                return replace(incident)
        return None

    def upsert_incident(self, incident: IncidentRecord) -> None:
        self.incidents[incident.id] = replace(incident)

    def resolve_incident(self, incident_id: str, resolved_at: datetime) -> None:
        incident = self.incidents.get(incident_id)
        if not incident:
            return
        incident.status = IncidentStatus.RESOLVED
        incident.resolved_at = resolved_at
        incident.last_seen_at = resolved_at

    def record_heartbeat(
        self,
        identity: RunnerIdentity,
        at: datetime,
        metadata: Dict[str, Any],
    ) -> None:
        self.heartbeats[(identity.component, identity.host)] = {
            "build_sha": identity.build_sha,
            "heartbeat_at": at,
            "metadata": dict(metadata),
        }


class SupabaseStateStore:
    """Service-role persistence for Sentinel's dedicated tables only."""

    persistent = True

    def __init__(self, client: Any) -> None:
        self.client = client

    def get_check_state(self, check_key: str) -> Optional[CheckState]:
        rows = list(
            (
                self.client.table("sentinel_check_state")
                .select("*")
                .eq("check_key", check_key)
                .limit(1)
                .execute()
            ).data
            or []
        )
        if not rows:
            return None
        row = rows[0]
        return CheckState(
            check_key=row["check_key"],
            status=CheckStateStatus(row["status"]),
            last_checked_at=_dt(row.get("last_checked_at")),
            last_success_at=_dt(row.get("last_success_at")),
            first_failure_at=_dt(row.get("first_failure_at")),
            last_failure_at=_dt(row.get("last_failure_at")),
            consecutive_failures=int(row.get("consecutive_failures") or 0),
            current_incident_id=(
                str(row["current_incident_id"])
                if row.get("current_incident_id")
                else None
            ),
            last_observation_json=dict(row.get("last_observation_json") or {}),
            observation_hash=row.get("observation_hash"),
            runner_build_sha=row.get("runner_build_sha"),
        )

    def save_check_state(self, state: CheckState) -> None:
        payload = {
            "check_key": state.check_key,
            "status": state.status.value,
            "last_checked_at": _iso(state.last_checked_at),
            "last_success_at": _iso(state.last_success_at),
            "first_failure_at": _iso(state.first_failure_at),
            "last_failure_at": _iso(state.last_failure_at),
            "consecutive_failures": state.consecutive_failures,
            "current_incident_id": state.current_incident_id,
            "last_observation_json": state.last_observation_json,
            "observation_hash": state.observation_hash,
            "runner_build_sha": state.runner_build_sha,
            "updated_at": datetime.now(timezone.utc).isoformat(),
        }
        (
            self.client.table("sentinel_check_state")
            .upsert(payload, on_conflict="check_key")
            .execute()
        )

    def _incident_from_row(self, row: Dict[str, Any]) -> IncidentRecord:
        return IncidentRecord(
            id=str(row["id"]),
            fingerprint=row["fingerprint"],
            check_key=row["check_key"],
            severity=Severity(row["severity"]),
            status=IncidentStatus(row["status"]),
            failure_code=row["failure_code"],
            authority_identity=row.get("authority_identity"),
            first_seen_at=_dt(row["first_seen_at"]) or datetime.now(timezone.utc),
            last_seen_at=_dt(row["last_seen_at"]) or datetime.now(timezone.utc),
            resolved_at=_dt(row.get("resolved_at")),
            market_date=(str(row["market_date"]) if row.get("market_date") else None),
            batch_id=(int(row["batch_id"]) if row.get("batch_id") is not None else None),
            generation_id=(
                str(row["generation_id"]) if row.get("generation_id") else None
            ),
            deployment_sha=row.get("deployment_sha"),
            expected_json=dict(row.get("expected_json") or {}),
            observed_json=dict(row.get("observed_json") or {}),
            evidence_json=dict(row.get("evidence_json") or {}),
            recovery_eligible=bool(row.get("recovery_eligible")),
            recovery_attempt_count=int(row.get("recovery_attempt_count") or 0),
            ai_triage_status=str(row.get("ai_triage_status") or "disabled"),
        )

    def get_incident(self, incident_id: str) -> Optional[IncidentRecord]:
        rows = list(
            (
                self.client.table("sentinel_incidents")
                .select("*")
                .eq("id", incident_id)
                .limit(1)
                .execute()
            ).data
            or []
        )
        return self._incident_from_row(rows[0]) if rows else None

    def get_open_incident_by_fingerprint(
        self, fingerprint: str
    ) -> Optional[IncidentRecord]:
        rows = list(
            (
                self.client.table("sentinel_incidents")
                .select("*")
                .eq("fingerprint", fingerprint)
                .in_("status", [status.value for status in _OPEN_INCIDENT_STATUSES])
                .order("last_seen_at", desc=True)
                .limit(1)
                .execute()
            ).data
            or []
        )
        return self._incident_from_row(rows[0]) if rows else None

    def upsert_incident(self, incident: IncidentRecord) -> None:
        payload = {
            "id": incident.id,
            "fingerprint": incident.fingerprint,
            "check_key": incident.check_key,
            "severity": incident.severity.value,
            "status": incident.status.value,
            "failure_code": incident.failure_code,
            "authority_identity": incident.authority_identity,
            "first_seen_at": _iso(incident.first_seen_at),
            "last_seen_at": _iso(incident.last_seen_at),
            "resolved_at": _iso(incident.resolved_at),
            "market_date": incident.market_date,
            "batch_id": incident.batch_id,
            "generation_id": incident.generation_id,
            "deployment_sha": incident.deployment_sha,
            "expected_json": incident.expected_json,
            "observed_json": incident.observed_json,
            "evidence_json": incident.evidence_json,
            "recovery_eligible": incident.recovery_eligible,
            "recovery_attempt_count": incident.recovery_attempt_count,
            "ai_triage_status": incident.ai_triage_status,
            "updated_at": datetime.now(timezone.utc).isoformat(),
        }
        (
            self.client.table("sentinel_incidents")
            .upsert(payload, on_conflict="id")
            .execute()
        )

    def resolve_incident(self, incident_id: str, resolved_at: datetime) -> None:
        (
            self.client.table("sentinel_incidents")
            .update(
                {
                    "status": IncidentStatus.RESOLVED.value,
                    "resolved_at": resolved_at.isoformat(),
                    "last_seen_at": resolved_at.isoformat(),
                    "updated_at": datetime.now(timezone.utc).isoformat(),
                }
            )
            .eq("id", incident_id)
            .execute()
        )

    def record_heartbeat(
        self,
        identity: RunnerIdentity,
        at: datetime,
        metadata: Dict[str, Any],
    ) -> None:
        payload = {
            "component": identity.component,
            "host": identity.host,
            "build_sha": identity.build_sha,
            "heartbeat_at": at.isoformat(),
            "metadata": metadata,
            "updated_at": datetime.now(timezone.utc).isoformat(),
        }
        (
            self.client.table("sentinel_component_heartbeats")
            .upsert(payload, on_conflict="component,host")
            .execute()
        )


def build_state_store(state_writes_enabled: bool) -> SentinelStateStore:
    if not state_writes_enabled:
        return NoopStateStore()
    # Import lazily so observation-only/unit-test imports never initialize the
    # production Supabase client as a side effect.
    from backend.db.clients.supabase_client import supabase

    return SupabaseStateStore(supabase)
