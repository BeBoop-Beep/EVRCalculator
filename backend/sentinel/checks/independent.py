"""Independent watch-the-watcher checks for inDex Sentinel.

These checks are intentionally separate from the VM's normal Sentinel profile.
A process cannot prove its own liveness after it has died, so this module is
for an observer running in a different failure domain.
"""

from __future__ import annotations

from datetime import datetime, timezone
from typing import Any, Dict, Optional

from backend.sentinel.models import CheckResult, Severity
from backend.sentinel.registry import CheckContext


DEFAULT_HEARTBEAT_MAX_AGE_SECONDS = 15 * 60
_MAX_FUTURE_SKEW_SECONDS = 60


def _dt(value: Any) -> Optional[datetime]:
    if value in (None, ""):
        return None
    parsed = datetime.fromisoformat(str(value).replace("Z", "+00:00"))
    if parsed.tzinfo is None:
        parsed = parsed.replace(tzinfo=timezone.utc)
    return parsed.astimezone(timezone.utc)


def _failure(
    context: CheckContext,
    *,
    failure_code: str,
    authority: str,
    expected: Dict[str, Any],
    observed: Dict[str, Any],
    evidence: Optional[Dict[str, Any]] = None,
) -> CheckResult:
    return CheckResult.failure(
        "watcher.component_heartbeat",
        failure_code=failure_code,
        severity=Severity.CRITICAL,
        authority_identity=authority,
        expected=expected,
        observed=observed,
        evidence=evidence or {},
        checked_at=context.now,
    )


def check_component_heartbeat(
    context: CheckContext,
    *,
    client: Any,
    component: str = "sentinel_vm",
    host: str,
    max_age_seconds: int = DEFAULT_HEARTBEAT_MAX_AGE_SECONDS,
) -> CheckResult:
    """Verify a specific component/host heartbeat from an independent observer.

    The target host is mandatory. Watching "the newest heartbeat for any host"
    could let a replacement/test host hide the death of the production VM.
    The observer is also rejected when its own component+host identity exactly
    matches the target; self-observation is not an independent failure domain.
    """
    target_component = str(component or "").strip()
    target_host = str(host or "").strip()
    if not target_component:
        raise ValueError("heartbeat component is required")
    if not target_host:
        raise ValueError("heartbeat host is required")
    threshold = int(max_age_seconds)
    if threshold <= 0:
        raise ValueError("heartbeat max_age_seconds must be positive")

    authority = f"{target_component}:{target_host}"
    expected = {
        "component": target_component,
        "host": target_host,
        "max_age_seconds": threshold,
        "independent_observer": True,
    }

    observer = context.runner_identity
    if observer.component == target_component and observer.host == target_host:
        return _failure(
            context,
            failure_code="heartbeat_observer_not_independent",
            authority=authority,
            expected=expected,
            observed={
                "observer_component": observer.component,
                "observer_host": observer.host,
                "target_component": target_component,
                "target_host": target_host,
            },
        )

    result = (
        client.table("sentinel_component_heartbeats")
        .select("component,host,build_sha,heartbeat_at,metadata,updated_at")
        .eq("component", target_component)
        .eq("host", target_host)
        .limit(1)
        .execute()
    )
    rows = list((result.data if result else []) or [])
    if not rows:
        return _failure(
            context,
            failure_code="component_heartbeat_missing",
            authority=authority,
            expected=expected,
            observed={"heartbeat_present": False},
        )

    row = dict(rows[0])
    heartbeat_at = _dt(row.get("heartbeat_at"))
    if heartbeat_at is None:
        return _failure(
            context,
            failure_code="component_heartbeat_contract_invalid",
            authority=authority,
            expected=expected,
            observed={
                "heartbeat_present": True,
                "heartbeat_at": row.get("heartbeat_at"),
                "build_sha": row.get("build_sha"),
            },
        )

    now_utc = context.now.astimezone(timezone.utc)
    age_seconds = (now_utc - heartbeat_at).total_seconds()
    if age_seconds < -_MAX_FUTURE_SKEW_SECONDS:
        return _failure(
            context,
            failure_code="component_heartbeat_clock_invalid",
            authority=authority,
            expected=expected,
            observed={
                "heartbeat_at": heartbeat_at.isoformat(),
                "age_seconds": round(age_seconds, 3),
                "build_sha": row.get("build_sha"),
            },
        )

    safe_age = max(0.0, age_seconds)
    observed = {
        "heartbeat_present": True,
        "heartbeat_at": heartbeat_at.isoformat(),
        "age_seconds": round(safe_age, 3),
        "build_sha": row.get("build_sha"),
    }
    if safe_age > threshold:
        return _failure(
            context,
            failure_code="component_heartbeat_stale",
            authority=authority,
            expected=expected,
            observed=observed,
        )

    return CheckResult.healthy(
        "watcher.component_heartbeat",
        authority_identity=authority,
        expected=expected,
        observed=observed,
        checked_at=context.now,
    )
