"""Queue scrape-orchestration alert rows into public.alert_events.

Database state is authoritative. These helpers only *queue* alert rows; the
existing dispatcher (:mod:`backend.alerts.dispatcher`) delivers them to Slack and
marks them sent. A Slack delivery failure never affects queue/batch correctness —
the alert row simply retries on the next dispatch.

Alert types (Phase 8):
    batch_not_created            — expected daily batch missing by deadline
    worker_no_heartbeat          — no worker heartbeat within threshold
    job_lease_expired            — a running job lease expired (reclaimed)
    queue_diag_divergence        — queue vs diagnostic status mismatch
    batch_incomplete             — batch incomplete after retry window
    missing_current_sets         — current/newest sets missing from the batch
    finalization_db_failure      — finalization could not reach the database
    snapshot_promotion_blocked   — partial batch blocked downstream promotion
    runtime_registry_mismatch    — deployed runtime disagrees with DB metadata
    deterministic_scrape_failure — non-retryable configuration/deployment failure
"""

from __future__ import annotations

import logging
from typing import Any, Dict, List, Optional

from backend.db.clients.supabase_client import supabase

logger = logging.getLogger(__name__)

_ALERT_TAG = "[scrape-alerts]"

_VALID_SEVERITIES = ("info", "warning", "error", "critical")


def queue_alert(
    alert_type: str,
    title: str,
    message: str,
    *,
    severity: str = "error",
    dedupe_key: Optional[str] = None,
    payload: Optional[Dict[str, Any]] = None,
) -> Optional[Dict[str, Any]]:
    """Insert an alert row into public.alert_events. Best-effort, never raises.

    Returns the inserted row, or ``None`` if the insert failed (logged). The
    payload should include, where known: market_date, batch_id, queue_job_id,
    canonical_key, attempt_count, error_category, timestamps, missing_set_count.
    """
    if severity not in _VALID_SEVERITIES:
        severity = "error"

    row = {
        "alert_type": alert_type,
        "severity": severity,
        "title": title[:300],
        "message": message[:2000],
        "payload": payload or {},
    }
    if dedupe_key:
        row["dedupe_key"] = dedupe_key[:300]

    try:
        result = supabase.table("alert_events").insert(row).execute()
        if result and result.data:
            logger.warning(
                "%s queued alert type=%s severity=%s title=%s",
                _ALERT_TAG, alert_type, severity, title,
            )
            return result.data[0]
        logger.error("%s queue_alert returned no data for type=%s", _ALERT_TAG, alert_type)
        return None
    except Exception as exc:  # pragma: no cover - alerts must never break the queue
        logger.error("%s queue_alert failed for type=%s: %s", _ALERT_TAG, alert_type, exc)
        return None


def alert_finalization_db_failure(
    job_id: int,
    *,
    market_date: Optional[str] = None,
    batch_id: Optional[int] = None,
    canonical_key: Optional[str] = None,
    attempt_count: Optional[int] = None,
    error: Optional[str] = None,
    recovery_record: Optional[str] = None,
) -> Optional[Dict[str, Any]]:
    return queue_alert(
        "finalization_db_failure",
        title=f"Scrape finalization DB write failed (job {job_id})",
        message=(
            f"finalize_scrape_job could not reach the database for job {job_id}. "
            f"A local recovery record was written and the lease watchdog will reconcile."
        ),
        severity="critical",
        dedupe_key=f"finalization_db_failure:{job_id}",
        payload={
            "job_id": job_id,
            "market_date": market_date,
            "batch_id": batch_id,
            "canonical_key": canonical_key,
            "attempt_count": attempt_count,
            "error_category": "finalization_db_failure",
            "error_summary": error,
            "recovery_record": recovery_record,
        },
    )


def alert_batch_incomplete(
    batch_id: int,
    market_date: str,
    *,
    missing_set_count: int,
    missing_sets: Optional[List[Dict[str, Any]]] = None,
    succeeded_set_count: Optional[int] = None,
    failed_set_count: Optional[int] = None,
) -> Optional[Dict[str, Any]]:
    missing_keys = [
        (s.get("canonical_key") or s.get("name") or str(s.get("set_id")))
        for s in (missing_sets or [])
    ]
    return queue_alert(
        "batch_incomplete",
        title=f"Scrape batch incomplete for {market_date} ({missing_set_count} missing)",
        message=(
            f"Batch {batch_id} for market_date {market_date} is incomplete: "
            f"{missing_set_count} set(s) lack valid Near Mint observations. "
            f"Snapshot promotion is blocked; the previous complete market date stays public. "
            f"Missing: {', '.join(missing_keys[:25]) or 'n/a'}"
        ),
        severity="error",
        dedupe_key=f"batch_incomplete:{market_date}",
        payload={
            "batch_id": batch_id,
            "market_date": market_date,
            "missing_set_count": missing_set_count,
            "missing_sets": missing_keys,
            "succeeded_set_count": succeeded_set_count,
            "failed_set_count": failed_set_count,
            "error_category": "batch_incomplete",
        },
    )


def alert_runtime_registry_mismatch(market_date: str, *, report: Any) -> Optional[Dict[str, Any]]:
    """Deployed runtime disagrees with database metadata; batch creation refused.

    This is a configuration/deployment defect, not a data problem: the fix is to
    deploy the correct commit to the VM (or run the metadata sync), never to
    retry. The message names the diverging keys so the operator does not have to
    reconstruct them from job rows.
    """
    missing = list(getattr(report, "missing_local_keys", []) or [])
    unexpected = list(getattr(report, "unexpected_db_keys", []) or [])
    preview = ", ".join((missing + unexpected)[:10]) or "-"

    return queue_alert(
        "runtime_registry_mismatch",
        title=f"Scrape runtime/database registry mismatch blocked {market_date}",
        message=(
            f"Batch creation for market_date {market_date} was refused: the deployed "
            f"runtime and the database daily cohort disagree on "
            f"{getattr(report, 'mismatch_count', 0)} canonical key(s)/field(s). "
            f"Runtime sha={getattr(report, 'runtime_git_sha', None)} "
            f"branch={getattr(report, 'runtime_git_branch', None)} "
            f"root={getattr(report, 'repository_root', None)}. "
            f"Diverging keys: {preview}. "
            "Deploy the approved commit to the scraper VM and re-run the preflight; "
            "do NOT retry the batch."
        ),
        severity="critical",
        dedupe_key=f"runtime_registry_mismatch:{market_date}",
        payload={
            "market_date": market_date,
            "error_category": "runtime_registry_mismatch",
            "preflight": report.to_dict() if hasattr(report, "to_dict") else None,
        },
    )


def alert_deterministic_scrape_failure(
    *,
    job_id: Any,
    canonical_key: Optional[str],
    error_code: str,
    market_date: Optional[str] = None,
    error_summary: Optional[str] = None,
) -> Optional[Dict[str, Any]]:
    """A job failed for a deterministic configuration/deployment reason.

    Retrying cannot fix these, so the job is finalized without consuming further
    attempts and this alert carries the actionable detail instead.
    """
    return queue_alert(
        "deterministic_scrape_failure",
        title=f"Non-retryable scrape failure ({error_code}) for {canonical_key or 'unknown set'}",
        message=(
            f"Scrape job {job_id} for canonical_key={canonical_key} failed with the "
            f"deterministic error code '{error_code}' on market_date {market_date}. "
            "This is a configuration/deployment defect and was NOT requeued. "
            f"Detail: {(error_summary or '')[:500]}"
        ),
        severity="critical",
        dedupe_key=f"deterministic_scrape_failure:{market_date}:{canonical_key}:{error_code}",
        payload={
            "market_date": market_date,
            "queue_job_id": job_id,
            "canonical_key": canonical_key,
            "error_code": error_code,
            "error_category": "deterministic_configuration_failure",
            "retryable": False,
        },
    )


def alert_batch_not_created(market_date: str, *, deadline: str) -> Optional[Dict[str, Any]]:
    return queue_alert(
        "batch_not_created",
        title=f"Daily scrape batch not created for {market_date}",
        message=(
            f"No scrape batch exists for market_date {market_date} past the "
            f"configured deadline ({deadline})."
        ),
        severity="critical",
        dedupe_key=f"batch_not_created:{market_date}",
        payload={
            "market_date": market_date,
            "deadline": deadline,
            "error_category": "batch_not_created",
        },
    )
