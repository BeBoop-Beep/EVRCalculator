"""Observation-only adapters from existing inDex authorities into Sentinel."""

from __future__ import annotations

from datetime import datetime, timedelta, timezone
from types import SimpleNamespace
from typing import Any, Callable, Dict, Iterable, Mapping, Optional
from zoneinfo import ZoneInfo

from backend.sentinel.models import CheckResult, Severity
from backend.sentinel.registry import CheckContext


PHOENIX = ZoneInfo("America/Phoenix")
CANONICAL_LEGACY_RUNNING_GRACE_SECONDS = 7200
_SAMPLE_LIMIT = 20


def _market_date(context: CheckContext) -> str:
    return context.now.astimezone(PHOENIX).date().isoformat()


def _dt(value: Any) -> Optional[datetime]:
    if value in (None, ""):
        return None
    parsed = datetime.fromisoformat(str(value).replace("Z", "+00:00"))
    if parsed.tzinfo is None:
        parsed = parsed.replace(tzinfo=timezone.utc)
    return parsed.astimezone(timezone.utc)


def _default_client() -> Any:
    from backend.db.clients.supabase_client import supabase

    return supabase


def _small_mapping(value: Mapping[str, Any]) -> Dict[str, Any]:
    return {str(k): v for k, v in value.items()}


def check_alert_delivery(
    context: CheckContext,
    *,
    health_loader: Optional[Callable[[], Mapping[str, Any]]] = None,
) -> CheckResult:
    """Adapt the existing dispatcher health contract without reimplementing it."""
    if health_loader is None:
        from backend.alerts.dispatcher import get_dispatcher_health

        health_loader = get_dispatcher_health
    health = _small_mapping(health_loader())
    expected = {
        "alerts_enabled": True,
        "slack_webhook_configured": True,
        "dispatcher_scheduled": True,
        "freshness_watchdog_scheduled": True,
        "backlog_healthy": True,
    }

    failure_code: Optional[str] = None
    if health.get("database_connected") is False:
        failure_code = "alert_delivery_database_unavailable"
    elif health.get("alerts_enabled") is not True:
        failure_code = "alert_delivery_disabled"
    elif health.get("slack_webhook_configured") is not True:
        failure_code = "alert_webhook_missing"
    elif (
        health.get("dispatcher_scheduled") is not True
        or health.get("freshness_watchdog_scheduled") is not True
    ):
        failure_code = "alert_schedules_unconfirmed"
    elif health.get("backlog_healthy") is False:
        failure_code = "alert_backlog_stalled"
    elif health.get("delivery_progress_healthy") is False:
        failure_code = "alert_delivery_stalled"
    elif health.get("healthy") is not True:
        failure_code = "alert_delivery_unhealthy"

    if failure_code:
        return CheckResult.failure(
            "alerts.delivery",
            failure_code=failure_code,
            severity=Severity.CRITICAL,
            authority_identity="alert-delivery-v1",
            expected=expected,
            observed=health,
            evidence={
                "pending_unsuppressed_count": health.get("pending_unsuppressed_count"),
                "oldest_pending_age_minutes": health.get("oldest_pending_age_minutes"),
                "last_sent_at": health.get("last_sent_at"),
            },
            checked_at=context.now,
        )
    return CheckResult.healthy(
        "alerts.delivery",
        authority_identity="alert-delivery-v1",
        expected=expected,
        observed=health,
        checked_at=context.now,
    )


_WATCHDOG_PRIORITY = {
    "market_watchdog_execution_failed": 0,
    "batch_not_created": 1,
    "batch_progress_stalled": 2,
    "market_publication_stale": 3,
    "market_snapshot_date_divergence": 4,
}


def _dominant_watchdog_failure(failures: Iterable[Mapping[str, Any]]) -> Mapping[str, Any]:
    rows = list(failures)
    if not rows:
        return {}
    return min(
        rows,
        key=lambda row: (
            _WATCHDOG_PRIORITY.get(str(row.get("alert_type") or ""), 999),
            str(row.get("alert_type") or ""),
            str(row.get("failure_class") or ""),
        ),
    )


def check_market_freshness(
    context: CheckContext,
    *,
    client: Any = None,
    watchdog_runner: Optional[Callable[..., Mapping[str, Any]]] = None,
) -> CheckResult:
    """Run the legacy freshness watchdog in its explicit read-only mode."""
    if watchdog_runner is None:
        from backend.alerts.market_freshness_watchdog import run_watchdog

        watchdog_runner = run_watchdog
    resolved_client = client if client is not None else _default_client()
    report = _small_mapping(
        watchdog_runner(client=resolved_client, now=context.now, queue_failures=False)
    )
    market_date = str(report.get("market_date") or _market_date(context))
    failures = list(report.get("failures") or [])
    if report.get("healthy") is True and not failures:
        return CheckResult.healthy(
            "market.freshness",
            authority_identity=market_date,
            expected={"healthy": True, "market_date": market_date},
            observed={
                "healthy": True,
                "failure_count": report.get("failure_count", 0),
                "authority_dates": (report.get("state") or {}).get("authority_dates", {}),
            },
            checked_at=context.now,
        )

    dominant = _dominant_watchdog_failure(failures)
    alert_type = str(dominant.get("alert_type") or "market_watchdog_unhealthy")
    failure_code = (
        "market_watchdog_state_load_failed"
        if report.get("execution_failed") is True
        else alert_type
    )
    return CheckResult.failure(
        "market.freshness",
        failure_code=failure_code,
        severity=Severity.CRITICAL,
        authority_identity=market_date,
        expected={"healthy": True, "market_date": market_date},
        observed={
            "healthy": False,
            "failure_count": report.get("failure_count", len(failures)),
            "dominant_alert_type": alert_type,
            "authority_dates": (report.get("state") or {}).get("authority_dates", {}),
        },
        evidence={"failures": failures[:_SAMPLE_LIMIT]},
        checked_at=context.now,
    )


def check_scrape_queue_leases(
    context: CheckContext,
    *,
    client: Any = None,
    legacy_running_grace_seconds: int = CANONICAL_LEGACY_RUNNING_GRACE_SECONDS,
) -> CheckResult:
    """Observe the same stale-running predicates used by the DB lease watchdog."""
    resolved_client = client if client is not None else _default_client()
    result = (
        resolved_client.table("scrape_jobs")
        .select(
            "id,set_id,status,attempts,max_attempts,started_at,lease_expires_at,"
            "heartbeat_at,market_date,batch_id,worker_id"
        )
        .eq("status", "running")
        .execute()
    )
    rows = list((result.data if result else []) or [])
    now_utc = context.now.astimezone(timezone.utc)
    legacy_cutoff = now_utc - timedelta(seconds=max(60, int(legacy_running_grace_seconds)))
    stale: list[Dict[str, Any]] = []
    invalid: list[Dict[str, Any]] = []

    for row in rows:
        try:
            lease = _dt(row.get("lease_expires_at"))
            started = _dt(row.get("started_at"))
        except (TypeError, ValueError) as exc:
            invalid.append({"id": row.get("id"), "error": str(exc)[:200]})
            continue
        expired_lease = lease is not None and lease < now_utc
        stale_legacy = lease is None and started is not None and started < legacy_cutoff
        if expired_lease or stale_legacy:
            stale.append(
                {
                    "id": row.get("id"),
                    "set_id": row.get("set_id"),
                    "batch_id": row.get("batch_id"),
                    "market_date": row.get("market_date"),
                    "worker_id": row.get("worker_id"),
                    "started_at": row.get("started_at"),
                    "heartbeat_at": row.get("heartbeat_at"),
                    "lease_expires_at": row.get("lease_expires_at"),
                    "attempts": row.get("attempts"),
                    "max_attempts": row.get("max_attempts"),
                    "stale_reason": "lease_expired" if expired_lease else "legacy_running_grace_exceeded",
                }
            )

    authority = _market_date(context)
    if invalid:
        return CheckResult.failure(
            "scrape.queue_leases",
            failure_code="scrape_lease_contract_invalid",
            severity=Severity.CRITICAL,
            authority_identity=authority,
            expected={"invalid_running_rows": 0},
            observed={"invalid_running_rows": len(invalid), "running_jobs": len(rows)},
            evidence={"invalid_rows": invalid[:_SAMPLE_LIMIT]},
            checked_at=context.now,
        )
    if stale:
        return CheckResult.failure(
            "scrape.queue_leases",
            failure_code="scrape_job_lease_expired",
            severity=Severity.CRITICAL,
            authority_identity=authority,
            expected={"stale_running_jobs": 0},
            observed={"stale_running_jobs": len(stale), "running_jobs": len(rows)},
            evidence={"stale_jobs": stale[:_SAMPLE_LIMIT]},
            checked_at=context.now,
        )
    return CheckResult.healthy(
        "scrape.queue_leases",
        authority_identity=authority,
        expected={"stale_running_jobs": 0},
        observed={"stale_running_jobs": 0, "running_jobs": len(rows)},
        checked_at=context.now,
    )


def _gate_observed(decision: Any) -> Dict[str, Any]:
    fields = (
        "allowed",
        "reason_code",
        "gated",
        "mode",
        "override",
        "market_date",
        "batch_id",
        "batch_status",
        "missing_set_count",
        "expected_set_count",
        "promoted_at",
    )
    return {field: getattr(decision, field, None) for field in fields}


def check_publication_batch_gate(
    context: CheckContext,
    *,
    client: Any = None,
    gate_evaluator: Optional[Callable[..., Any]] = None,
) -> CheckResult:
    """Observe the canonical publication gate; do not decide freshness timing here."""
    if gate_evaluator is None:
        from backend.db.services.publication_gate import evaluate_publication_gate

        gate_evaluator = evaluate_publication_gate
    resolved_client = client if client is not None else _default_client()
    market_date = _market_date(context)
    decision = gate_evaluator(resolved_client, market_date=market_date, override=False)
    observed = _gate_observed(decision)
    reason_code = str(observed.get("reason_code") or "unknown")
    status = str(observed.get("batch_status") or "")

    if observed.get("allowed") is True and reason_code == "allowed_complete":
        return CheckResult.healthy(
            "publication.batch_gate",
            authority_identity=market_date,
            expected={"gate_contract_valid": True},
            observed=observed,
            checked_at=context.now,
        )

    # Not-yet-created/running batches are normal pipeline states. The freshness
    # watchdog owns the time/deadline policy for deciding when they become stale.
    if reason_code == "blocked_no_batch" or (
        reason_code == "blocked_incomplete" and status in {"", "pending", "running"}
    ):
        return CheckResult.healthy(
            "publication.batch_gate",
            authority_identity=market_date,
            expected={"gate_contract_valid": True},
            observed={**observed, "publication_eligible": False},
            checked_at=context.now,
        )

    if reason_code == "blocked_incomplete" and status in {"failed", "incomplete"}:
        failure_code = "publication_batch_terminal_incomplete"
    elif reason_code == "blocked_authority_unavailable":
        failure_code = "publication_gate_authority_unavailable"
    elif reason_code == "blocked_invalid_batch_contract":
        failure_code = "publication_batch_contract_invalid"
    elif reason_code in {"disabled_explicitly", "manual_override"} or observed.get("gated") is False:
        failure_code = "publication_gate_bypassed"
    else:
        failure_code = "publication_gate_unclassified_block"

    return CheckResult.failure(
        "publication.batch_gate",
        failure_code=failure_code,
        severity=Severity.CRITICAL,
        authority_identity=market_date,
        expected={"gate_contract_valid": True},
        observed=observed,
        evidence={"reason": str(getattr(decision, "reason", ""))[:500]},
        checked_at=context.now,
    )


def _one_row(query: Any) -> Optional[Dict[str, Any]]:
    result = query.limit(1).execute()
    rows = list((result.data if result else []) or [])
    return dict(rows[0]) if rows else None


def _generation_failure(
    context: CheckContext,
    failure_code: str,
    *,
    authority: str,
    expected: Mapping[str, Any],
    observed: Mapping[str, Any],
) -> CheckResult:
    return CheckResult.failure(
        "setpage.generation",
        failure_code=failure_code,
        severity=Severity.CRITICAL,
        authority_identity=authority,
        expected=expected,
        observed=observed,
        checked_at=context.now,
    )


def check_set_page_generation(
    context: CheckContext,
    *,
    client: Any = None,
    scope: str = "pokemon",
) -> CheckResult:
    """Validate only the current-pointer/generation contract already stored in DB."""
    resolved_client = client if client is not None else _default_client()
    pointer = _one_row(
        resolved_client.table("pokemon_set_page_snapshot_current_generation")
        .select("scope,generation_id,activated_at,updated_at")
        .eq("scope", scope)
    )
    if not pointer or not pointer.get("generation_id"):
        return _generation_failure(
            context,
            "setpage_generation_pointer_missing",
            authority=scope,
            expected={"current_generation_pointer": True},
            observed={"pointer": pointer},
        )

    generation_id = str(pointer["generation_id"])
    generation = _one_row(
        resolved_client.table("pokemon_set_page_snapshot_generations")
        .select(
            "id,scope,status,expected_set_count,completed_set_count,validation_passed,"
            "validation_error,generation_fingerprint,published_at,completed_at,updated_at"
        )
        .eq("id", generation_id)
    )
    if not generation:
        return _generation_failure(
            context,
            "setpage_generation_row_missing",
            authority=generation_id,
            expected={"generation_row": True},
            observed={"pointer": pointer},
        )

    count_result = (
        resolved_client.table("pokemon_set_page_snapshot_generation_rows")
        .select("set_id", count="exact")
        .eq("generation_id", generation_id)
        .limit(1)
        .execute()
    )
    row_count = int(getattr(count_result, "count", None) or 0)
    expected_count = generation.get("expected_set_count")
    completed_count = generation.get("completed_set_count")
    try:
        expected_count = int(expected_count)
        completed_count = int(completed_count)
    except (TypeError, ValueError):
        expected_count = -1
        completed_count = -1

    observed = {
        "scope": generation.get("scope"),
        "generation_id": generation_id,
        "status": generation.get("status"),
        "validation_passed": generation.get("validation_passed"),
        "published_at": generation.get("published_at"),
        "expected_set_count": expected_count,
        "completed_set_count": completed_count,
        "generation_row_count": row_count,
        "generation_fingerprint": generation.get("generation_fingerprint"),
    }
    expected = {
        "scope": scope,
        "status": "published",
        "validation_passed": True,
        "published_at_present": True,
        "completed_equals_expected": True,
        "row_count_equals_expected": True,
    }

    if generation.get("scope") != scope:
        code = "setpage_generation_scope_mismatch"
    elif generation.get("status") != "published":
        code = "setpage_generation_not_published"
    elif generation.get("validation_passed") is not True:
        code = "setpage_generation_validation_failed"
    elif not generation.get("published_at"):
        code = "setpage_generation_published_at_missing"
    elif expected_count <= 0:
        code = "setpage_generation_expected_count_invalid"
    elif completed_count != expected_count:
        code = "setpage_generation_completion_mismatch"
    elif row_count != expected_count:
        code = "setpage_generation_row_count_mismatch"
    else:
        return CheckResult.healthy(
            "setpage.generation",
            authority_identity=generation_id,
            expected=expected,
            observed=observed,
            checked_at=context.now,
        )
    return _generation_failure(
        context,
        code,
        authority=generation_id,
        expected=expected,
        observed=observed,
    )


def check_post_scrape_publication_audit(
    context: CheckContext,
    *,
    client: Any = None,
    audit_runner: Optional[Callable[..., Any]] = None,
) -> CheckResult:
    """Adapt the existing heavy post-scrape publication audit without duplicating it."""
    if audit_runner is None:
        from backend.scripts.audit_pokemon_market_publication import (
            PHASE_POST_SCRAPE,
            run_market_publication_audit,
        )

        audit_runner = lambda resolved_client: run_market_publication_audit(
            resolved_client, phase=PHASE_POST_SCRAPE
        )
    resolved_client = client if client is not None else _default_client()
    report = audit_runner(resolved_client)
    payload = dict(report.to_dict())
    market_date = str(payload.get("market_date") or _market_date(context))
    compact_evidence = {
        "phase": payload.get("phase"),
        "error": payload.get("error"),
        "set_count": payload.get("set_count"),
        "failed_set_count": payload.get("failed_set_count"),
        "failed_sets": list(payload.get("failed_sets") or [])[:_SAMPLE_LIMIT],
        "failed_by_section": {
            str(key): list(values or [])[:_SAMPLE_LIMIT]
            for key, values in dict(payload.get("failed_by_section") or {}).items()
        },
    }
    if payload.get("passed") is True:
        return CheckResult.healthy(
            "publication.audit.post_scrape",
            authority_identity=market_date,
            expected={"passed": True},
            observed={
                "passed": True,
                "market_date": market_date,
                "phase": payload.get("phase"),
                "set_count": payload.get("set_count"),
            },
            checked_at=context.now,
        )
    failure_code = (
        "publication_audit_unavailable"
        if payload.get("error")
        else "publication_audit_failed"
    )
    return CheckResult.failure(
        "publication.audit.post_scrape",
        failure_code=failure_code,
        severity=Severity.CRITICAL,
        authority_identity=market_date,
        expected={"passed": True},
        observed={
            "passed": False,
            "market_date": market_date,
            "phase": payload.get("phase"),
            "failed_set_count": payload.get("failed_set_count"),
        },
        evidence=compact_evidence,
        checked_at=context.now,
    )
