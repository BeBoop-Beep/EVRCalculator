"""Sentinel checks for Market Explorer's bounded maintained-cache scheduler."""

from __future__ import annotations

import subprocess
from datetime import datetime, timedelta, timezone
from typing import Any, Callable, Optional

from backend.sentinel.models import CheckResult, Severity
from backend.sentinel.registry import CheckContext

MARKET_EXPLORER_SCHEDULER_CHECK_KEY = "market_explorer.maintenance_scheduler"
MARKET_EXPLORER_SCHEDULER_AUTHORITY = "market-explorer-prewarm-cron-v1"
MARKET_EXPLORER_PROGRESS_CHECK_KEY = "market_explorer.maintenance_progress"
DEFAULT_PROGRESS_MAX_AGE_SECONDS = 10 * 60

_BEGIN = "# BEGIN market-explorer-prewarm (managed by install_market_explorer_prewarm_cron.sh)"
_END = "# END market-explorer-prewarm"


def check_market_explorer_scheduler(
    context: CheckContext,
    *,
    crontab_loader: Optional[Callable[[], str]] = None,
) -> CheckResult:
    """Require exactly one bounded writer and one read-only health schedule."""
    if crontab_loader is None:
        def crontab_loader() -> str:
            result = subprocess.run(
                ["crontab", "-l"],
                capture_output=True,
                text=True,
                check=False,
                timeout=10,
            )
            if result.returncode != 0:
                raise RuntimeError("crontab_unavailable")
            return result.stdout

    text = crontab_loader()
    blocks = 0
    prewarm = 0
    health = 0
    bounded = 0
    in_block = False
    for raw in text.splitlines():
        line = raw.strip()
        if line == _BEGIN:
            blocks += 1
            in_block = True
            continue
        if line == _END:
            in_block = False
            continue
        if not in_block or not line or line.startswith("#"):
            continue
        if "run_market_explorer_prewarm_guarded.sh" in line:
            prewarm += 1
            if "/usr/bin/flock -n" in line:
                bounded += 1
        if "check_market_explorer_maintained_cache_health" in line:
            health += 1

    observed = {
        "managed_blocks": blocks,
        "prewarm_entries": prewarm,
        "health_entries": health,
        "bounded_prewarm_entries": bounded,
    }
    expected = {
        "managed_blocks": 1,
        "prewarm_entries": 1,
        "health_entries": 1,
        "bounded_prewarm_entries": 1,
    }
    if observed != expected:
        return CheckResult.failure(
            MARKET_EXPLORER_SCHEDULER_CHECK_KEY,
            failure_code="MARKET_EXPLORER_MAINTENANCE_SCHEDULE_MISSING",
            severity=Severity.CRITICAL,
            authority_identity=MARKET_EXPLORER_SCHEDULER_AUTHORITY,
            expected=expected,
            observed=observed,
            checked_at=context.now,
        )
    return CheckResult.healthy(
        MARKET_EXPLORER_SCHEDULER_CHECK_KEY,
        authority_identity=MARKET_EXPLORER_SCHEDULER_AUTHORITY,
        expected=expected,
        observed=observed,
        checked_at=context.now,
    )



def _parse_timestamp(value: Any) -> Optional[datetime]:
    if not value:
        return None
    try:
        parsed = datetime.fromisoformat(str(value).replace("Z", "+00:00"))
    except ValueError:
        return None
    if parsed.tzinfo is None:
        parsed = parsed.replace(tzinfo=timezone.utc)
    return parsed.astimezone(timezone.utc)


def check_market_explorer_progress(
    context: CheckContext,
    *,
    client: Any = None,
    max_progress_age_seconds: int = DEFAULT_PROGRESS_MAX_AGE_SECONDS,
) -> CheckResult:
    """Require Explorer's normal bounded worker to be converged or actively advancing.

    This does not demand that all 37 maintained caches finish in one Sentinel tick.
    A lagging cohort is healthy while it is making recent progress. Sentinel only
    escalates when convergence stalls, which lets the normal cron remain primary.
    """
    if client is None:
        from backend.db.clients.supabase_client import create_service_role_client
        client = create_service_role_client()

    from backend.scripts.check_market_explorer_maintained_cache_health import (
        check_maintained_cache_health,
    )

    report = check_maintained_cache_health(client)
    target = str(report.get("latest_approved_market_date") or "")[:10] or None
    v2 = dict(report.get("v2") or {})
    alerts = list(report.get("alerts") or [])

    rows = list(
        client.table("pokemon_market_explorer_query_cache")
        .select("status,computed_through,updated_at")
        .eq("cache_kind", "maintained")
        .execute().data or []
    )
    stale = [
        row for row in rows
        if target and (
            str(row.get("status") or "") != "ready"
            or str(row.get("computed_through") or "")[:10] < target
        )
    ]
    latest_progress = max(
        (_parse_timestamp(row.get("updated_at")) for row in rows),
        default=None,
        key=lambda value: value or datetime.min.replace(tzinfo=timezone.utc),
    )
    progress_age = (
        max(0.0, (context.now.astimezone(timezone.utc) - latest_progress).total_seconds())
        if latest_progress is not None else None
    )

    observed = {
        "target_market_date": target,
        "maintained_count": int(report.get("maintained_count") or 0),
        "ready_and_current": int(report.get("ready_and_current") or 0),
        "stale_maintained_count": len(stale),
        "v2_healthy": bool(v2.get("healthy")),
        "v2_min_computed_through": v2.get("min_computed_through"),
        "v2_max_computed_through": v2.get("max_computed_through"),
        "alert_count": len(alerts),
        "latest_progress_at": latest_progress.isoformat() if latest_progress else None,
        "progress_age_seconds": progress_age,
    }

    if target is None:
        return CheckResult.failure(
            MARKET_EXPLORER_PROGRESS_CHECK_KEY,
            failure_code="MARKET_EXPLORER_APPROVED_DATE_UNAVAILABLE",
            severity=Severity.CRITICAL,
            observed=observed,
            checked_at=context.now,
        )

    if bool(v2.get("healthy")) and not alerts and not stale:
        return CheckResult.healthy(
            MARKET_EXPLORER_PROGRESS_CHECK_KEY,
            authority_identity=target,
            observed={**observed, "state": "current"},
            checked_at=context.now,
        )

    has_recent_progress = (
        progress_age is not None
        and progress_age <= max(1, int(max_progress_age_seconds))
    )
    deterministic_failure = any(
        str(row.get("reason") or "") in {"failed", "orphan_lease"}
        for row in alerts
    )
    if stale and has_recent_progress and not deterministic_failure:
        return CheckResult.healthy(
            MARKET_EXPLORER_PROGRESS_CHECK_KEY,
            authority_identity=target,
            observed={**observed, "state": "converging"},
            checked_at=context.now,
        )

    return CheckResult.failure(
        MARKET_EXPLORER_PROGRESS_CHECK_KEY,
        failure_code="MARKET_EXPLORER_CONVERGENCE_STALLED",
        severity=Severity.CRITICAL,
        authority_identity=target,
        observed={**observed, "state": "stalled"},
        evidence={"alerts": alerts[:10]},
        checked_at=context.now,
    )
