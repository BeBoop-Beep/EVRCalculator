from __future__ import annotations

import json
import logging
import os
import time
from datetime import datetime, timedelta, timezone
from pathlib import Path
from typing import Any, Dict, Iterable, List, Optional, Sequence, Set

from ..clients.supabase_client import supabase

logger = logging.getLogger(__name__)

_JOB_TAG = "[scrape-jobs]"
_SCRAPE_JOB_CYCLE_STATUSES = ("pending", "running", "completed", "failed")
_SCRAPE_READY_SET_SELECT = "id"
_SCRAPE_JOB_INSERT_CHUNK_SIZE = 500

# Default worker lease. Must comfortably exceed a single-set scrape wall time so
# a healthy worker never has its own lease reclaimed mid-run.
DEFAULT_LEASE_SECONDS = 1800

# Local durable recovery records are written here when a finalization cannot
# reach the database after bounded retries (Phase 5). The lease watchdog will
# still reconcile the job, but the failure must never be invisible.
_RECOVERY_DIR = Path("backend/constants/tcg/pokemon/scrape_job_reports/recovery")

# Transient finalization retry policy (bounded exponential backoff).
_FINALIZE_MAX_ATTEMPTS = 4
_FINALIZE_BASE_BACKOFF_SECONDS = 0.5


def _chunked(values: Sequence[Any], size: int) -> Iterable[Sequence[Any]]:
    for index in range(0, len(values), size):
        yield values[index : index + size]


def _is_active_job_conflict(exc: Exception) -> bool:
    message = str(exc).lower()
    return "idx_scrape_jobs_one_active_per_set" in message or (
        "duplicate key" in message and "scrape_jobs" in message
    )


def _is_missing_enqueue_rpc(exc: Exception) -> bool:
    message = str(exc).lower()
    return isinstance(exc, AttributeError) or (
        "pgrst202" in message
        or "could not find the function" in message
        or "enqueue_missing_scrape_jobs_for_ready_sets" in message and "not found" in message
    )


def _normalize_inserted_count(data: Any) -> int:
    if data is None:
        return 0
    if isinstance(data, int):
        return data
    if isinstance(data, list) and data:
        return _normalize_inserted_count(data[0])
    if isinstance(data, dict):
        value = data.get("enqueue_missing_scrape_jobs_for_ready_sets")
        if value is None:
            value = data.get("inserted_count")
        return int(value or 0)
    return int(data or 0)


def _enqueue_missing_scrape_jobs_via_rpc() -> int:
    result = supabase.rpc("enqueue_missing_scrape_jobs_for_ready_sets").execute()
    return _normalize_inserted_count(result.data if result else None)


def _fetch_scrape_ready_set_ids() -> List[str]:
    response = (
        supabase.table("sets")
        .select(_SCRAPE_READY_SET_SELECT)
        .eq("ready_for_daily_scrape", True)
        .eq("has_card_details_url", True)
        .not_.is_("card_details_url", "null")
        .execute()
    )
    rows = response.data if response and response.data else []
    return [str(row["id"]) for row in rows if row.get("id")]


def _current_utc_day_window() -> tuple[datetime, datetime]:
    cycle_start = datetime.now(timezone.utc).replace(hour=0, minute=0, second=0, microsecond=0)
    cycle_end = cycle_start + timedelta(days=1)
    return cycle_start, cycle_end


def _fetch_current_cycle_scrape_job_set_ids(set_ids: Sequence[str]) -> Set[str]:
    if not set_ids:
        return set()

    cycle_start, cycle_end = _current_utc_day_window()
    cycle_set_ids: Set[str] = set()
    for set_id_chunk in _chunked(list(set_ids), _SCRAPE_JOB_INSERT_CHUNK_SIZE):
        response = (
            supabase.table("scrape_jobs")
            .select("set_id")
            .in_("set_id", list(set_id_chunk))
            .in_("status", list(_SCRAPE_JOB_CYCLE_STATUSES))
            .gte("created_at", cycle_start.isoformat())
            .lt("created_at", cycle_end.isoformat())
            .execute()
        )
        rows = response.data if response and response.data else []
        cycle_set_ids.update(str(row["set_id"]) for row in rows if row.get("set_id"))

    return cycle_set_ids


def _insert_scrape_job_rows(rows: Sequence[Dict[str, Any]]) -> int:
    if not rows:
        return 0

    try:
        response = supabase.table("scrape_jobs").insert(list(rows)).execute()
    except Exception as exc:
        if not _is_active_job_conflict(exc):
            raise

        inserted_count = 0
        logger.debug(
            "%s active-job conflict while bulk enqueueing; retrying %s row(s) individually",
            _JOB_TAG,
            len(rows),
        )
        for row in rows:
            try:
                response = supabase.table("scrape_jobs").insert(row).execute()
            except Exception as row_exc:
                if _is_active_job_conflict(row_exc):
                    logger.debug("%s skipped raced active job for set_id=%s", _JOB_TAG, row.get("set_id"))
                    continue
                raise
            inserted_count += len(response.data) if response and response.data else 1
        return inserted_count

    return len(response.data) if response and response.data else len(rows)


def _enqueue_missing_scrape_jobs_via_rest() -> int:
    ready_set_ids = _fetch_scrape_ready_set_ids()
    if not ready_set_ids:
        logger.debug("%s no scrape-ready sets found for queue sync", _JOB_TAG)
        return 0

    current_cycle_set_ids = _fetch_current_cycle_scrape_job_set_ids(ready_set_ids)
    rows_to_insert = [
        {"set_id": set_id, "status": "pending", "attempts": 0}
        for set_id in ready_set_ids
        if set_id not in current_cycle_set_ids
    ]

    if not rows_to_insert:
        logger.debug("%s scrape-ready sets already have scrape jobs for current UTC day", _JOB_TAG)
        return 0

    inserted_count = 0
    for row_chunk in _chunked(rows_to_insert, _SCRAPE_JOB_INSERT_CHUNK_SIZE):
        inserted_count += _insert_scrape_job_rows(row_chunk)

    logger.debug("%s enqueued %s missing scrape job(s)", _JOB_TAG, inserted_count)
    return inserted_count


def enqueue_missing_scrape_jobs_for_ready_sets() -> int:
    """Create pending scrape jobs for scrape-ready sets without a job in the current UTC day."""
    try:
        try:
            inserted_count = _enqueue_missing_scrape_jobs_via_rpc()
            logger.debug("%s enqueued missing scrape jobs count=%s", _JOB_TAG, inserted_count)
            return inserted_count
        except Exception as rpc_exc:
            if not _is_missing_enqueue_rpc(rpc_exc):
                raise
            logger.debug("%s enqueue RPC unavailable; falling back to REST queue sync", _JOB_TAG)
            return _enqueue_missing_scrape_jobs_via_rest()
    except Exception as exc:
        logger.error("%s enqueue_missing_scrape_jobs_for_ready_sets failed: %s", _JOB_TAG, exc)
        raise


def claim_next_scrape_job(
    worker_id: Optional[str] = None,
    lease_seconds: int = DEFAULT_LEASE_SECONDS,
) -> Optional[Dict[str, Any]]:
    """Claim the highest-priority ready pending job under a lease.

    The RPC reconciles expired leases before claiming, so a crashed worker's job
    is reclaimed rather than blocking the queue. Falls back to a zero-arg call
    when the DB still has the legacy claim function signature.
    """
    try:
        try:
            result = supabase.rpc(
                "claim_next_scrape_job",
                {"p_worker_id": worker_id, "p_lease_seconds": lease_seconds},
            ).execute()
        except Exception as exc:
            if not _is_legacy_claim_signature(exc):
                raise
            logger.debug("%s lease-aware claim unavailable; using legacy claim", _JOB_TAG)
            result = supabase.rpc("claim_next_scrape_job").execute()

        if result and result.data:
            job = result.data[0]
            logger.info(
                "%s claimed job id=%s set_id=%s attempts=%s lease_expires=%s",
                _JOB_TAG,
                job.get("id"),
                job.get("set_id"),
                job.get("attempts"),
                job.get("lease_expires_at"),
            )
            return job
        logger.info("%s no pending scrape jobs available", _JOB_TAG)
        return None
    except Exception as exc:
        logger.error("%s claim_next_scrape_job failed: %s", _JOB_TAG, exc)
        raise


def _is_legacy_claim_signature(exc: Exception) -> bool:
    message = str(exc).lower()
    return (
        "p_worker_id" in message
        or "could not find the function" in message
        or "pgrst202" in message
    )


def mark_scrape_job_completed(job_id: int) -> Optional[Dict[str, Any]]:
    payload = {
        "status": "completed",
        "completed_at": datetime.now(timezone.utc).isoformat(),
        "error_message": None,
    }
    try:
        result = (
            supabase.table("scrape_jobs")
            .update(payload)
            .eq("id", job_id)
            .eq("status", "running")
            .execute()
        )
        if result and result.data:
            logger.info("%s marked job id=%s completed", _JOB_TAG, job_id)
            return result.data[0]
        logger.warning("%s completion update returned no row for job id=%s", _JOB_TAG, job_id)
        return None
    except Exception as exc:
        logger.error("%s mark_scrape_job_completed failed for job id=%s: %s", _JOB_TAG, job_id, exc)
        raise


def mark_scrape_job_failed(job_id: int, error_message: str) -> Optional[Dict[str, Any]]:
    payload = {
        "status": "failed",
        "completed_at": datetime.now(timezone.utc).isoformat(),
        "error_message": error_message[:2000],
    }
    try:
        result = (
            supabase.table("scrape_jobs")
            .update(payload)
            .eq("id", job_id)
            .eq("status", "running")
            .execute()
        )
        if result and result.data:
            logger.info("%s marked job id=%s failed", _JOB_TAG, job_id)
            return result.data[0]
        logger.warning("%s failure update returned no row for job id=%s", _JOB_TAG, job_id)
        return None
    except Exception as exc:
        logger.error("%s mark_scrape_job_failed failed for job id=%s: %s", _JOB_TAG, job_id, exc)
        raise


# ===========================================================================
# Batch / lease orchestration (Phase 2/3/4/5/6)
# ===========================================================================

def _rpc_data(result: Any) -> Any:
    return result.data if result else None


def create_daily_scrape_batch(
    market_date: Optional[str] = None,
    timezone_name: str = "America/Phoenix",
    trigger_source: str = "scheduled",
) -> Optional[Dict[str, Any]]:
    """Create (or idempotently return) the daily batch for a market date.

    Reconciles stale/crashed jobs first, derives the expected cohort dynamically,
    and enqueues one pending job per ready set that has no active job. ``market_date``
    is an ``America/Phoenix`` ISO date string; ``None`` lets the RPC default to the
    current Arizona market day.
    """
    params: Dict[str, Any] = {
        "p_timezone": timezone_name,
        "p_trigger_source": trigger_source,
    }
    if market_date is not None:
        params["p_market_date"] = market_date

    try:
        result = supabase.rpc("create_daily_scrape_batch", params).execute()
        data = _rpc_data(result)
        batch = data[0] if isinstance(data, list) and data else data
        if batch:
            logger.info(
                "%s created/updated batch id=%s market_date=%s expected=%s queued=%s trigger=%s",
                _JOB_TAG,
                batch.get("id"),
                batch.get("market_date"),
                batch.get("expected_set_count"),
                batch.get("queued_set_count"),
                trigger_source,
            )
        return batch
    except Exception as exc:
        logger.error("%s create_daily_scrape_batch failed: %s", _JOB_TAG, exc)
        raise


def reconcile_stale_scrape_jobs() -> int:
    """Expire crashed/timed-out jobs and requeue or terminally fail them."""
    try:
        result = supabase.rpc("reconcile_stale_scrape_jobs", {}).execute()
        count = _normalize_inserted_count(_rpc_data(result))
        if count:
            logger.warning("%s reconciled %s stale scrape job(s)", _JOB_TAG, count)
        return count
    except Exception as exc:
        logger.error("%s reconcile_stale_scrape_jobs failed: %s", _JOB_TAG, exc)
        raise


def heartbeat_scrape_job(
    job_id: int,
    worker_id: Optional[str] = None,
    lease_seconds: int = DEFAULT_LEASE_SECONDS,
) -> Optional[Dict[str, Any]]:
    """Extend a running job's lease. Returns None if the job is no longer running."""
    try:
        result = supabase.rpc(
            "heartbeat_scrape_job",
            {"p_job_id": job_id, "p_worker_id": worker_id, "p_lease_seconds": lease_seconds},
        ).execute()
        data = _rpc_data(result)
        row = data[0] if isinstance(data, list) and data else data
        if not row or not row.get("id"):
            logger.warning("%s heartbeat found no running job id=%s", _JOB_TAG, job_id)
            return None
        return row
    except Exception as exc:
        logger.warning("%s heartbeat_scrape_job failed for job id=%s: %s", _JOB_TAG, job_id, exc)
        return None


def _is_transient_db_error(exc: Exception) -> bool:
    message = str(exc).lower()
    transient_markers = (
        "timeout", "timed out", "temporarily unavailable", "connection",
        "reset", "econnreset", "502", "503", "504", "gateway",
        "could not connect", "server closed", "ssl",
    )
    return any(marker in message for marker in transient_markers)


def _write_finalization_recovery_record(record: Dict[str, Any]) -> Optional[str]:
    """Persist a durable local record when finalization cannot reach the DB.

    The lease watchdog still reconciles the job; this guarantees the failure is
    never invisible even if the process later dies.
    """
    try:
        _RECOVERY_DIR.mkdir(parents=True, exist_ok=True)
        stamp = datetime.now(timezone.utc).strftime("%Y%m%dT%H%M%S%fZ")
        path = _RECOVERY_DIR / f"finalize_job_{record.get('job_id')}_{stamp}.json"
        path.write_text(json.dumps(record, indent=2, default=str), encoding="utf-8")
        return str(path)
    except Exception as exc:  # pragma: no cover - best-effort durability
        logger.error("%s failed to write finalization recovery record: %s", _JOB_TAG, exc)
        return None


def finalize_scrape_job(
    job_id: int,
    diag_run_id: Optional[str],
    final_status: str,
    *,
    succeeded: int = 0,
    failed: int = 0,
    metrics: Optional[Dict[str, Any]] = None,
    error_summary: Optional[str] = None,
    report_path: Optional[str] = None,
    completed_at: Optional[str] = None,
) -> Dict[str, Any]:
    """Transactionally finalize a queue job + its diagnostic run + batch counters.

    Retries transient database/PostgREST failures with bounded exponential
    backoff. On permanent failure it writes a durable local recovery record and
    returns ``{"ok": False, ...}`` rather than silently swallowing the error, so
    the caller can alert and the lease watchdog can reconcile.
    """
    if final_status not in ("completed", "failed"):
        raise ValueError(f"finalize_scrape_job: invalid final_status {final_status!r}")

    params = {
        "p_job_id": job_id,
        "p_diag_run_id": diag_run_id,
        "p_final_status": final_status,
        "p_completed_at": completed_at or datetime.now(timezone.utc).isoformat(),
        "p_succeeded": succeeded,
        "p_failed": failed,
        "p_metrics": metrics or {},
        "p_error_summary": (error_summary or None) and error_summary[:2000],
        "p_report_path": report_path,
    }

    last_exc: Optional[Exception] = None
    for attempt in range(1, _FINALIZE_MAX_ATTEMPTS + 1):
        try:
            result = supabase.rpc("finalize_scrape_job", params).execute()
            data = _rpc_data(result)
            payload = data[0] if isinstance(data, list) and data else data
            if isinstance(payload, dict):
                logger.info(
                    "%s finalized job id=%s status=%s idempotent=%s (attempt %s)",
                    _JOB_TAG, job_id, final_status, payload.get("idempotent"), attempt,
                )
                return payload
            return {"ok": True, "job_id": job_id, "status": final_status}
        except Exception as exc:
            last_exc = exc
            if not _is_transient_db_error(exc) or attempt == _FINALIZE_MAX_ATTEMPTS:
                break
            backoff = _FINALIZE_BASE_BACKOFF_SECONDS * (2 ** (attempt - 1))
            logger.warning(
                "%s transient finalize failure job id=%s attempt %s/%s: %s; retrying in %.1fs",
                _JOB_TAG, job_id, attempt, _FINALIZE_MAX_ATTEMPTS, exc, backoff,
            )
            time.sleep(backoff)

    # Permanent failure: surface it durably.
    recovery = {
        "job_id": job_id,
        "diag_run_id": diag_run_id,
        "final_status": final_status,
        "succeeded": succeeded,
        "failed": failed,
        "error_summary": error_summary,
        "report_path": report_path,
        "finalize_error": str(last_exc),
        "recorded_at": datetime.now(timezone.utc).isoformat(),
    }
    recovery_path = _write_finalization_recovery_record(recovery)
    logger.error(
        "%s CRITICAL finalize_scrape_job could not reach DB for job id=%s after %s attempts: %s "
        "(recovery record: %s; lease watchdog will reconcile)",
        _JOB_TAG, job_id, _FINALIZE_MAX_ATTEMPTS, last_exc, recovery_path,
    )
    return {
        "ok": False,
        "job_id": job_id,
        "status": final_status,
        "error": str(last_exc),
        "recovery_record": recovery_path,
    }


def complete_scrape_batch_if_ready(batch_id: int) -> Dict[str, Any]:
    """Promote a batch only when the cohort is observation-complete."""
    try:
        result = supabase.rpc(
            "complete_scrape_batch_if_ready", {"p_batch_id": batch_id}
        ).execute()
        data = _rpc_data(result)
        payload = data[0] if isinstance(data, list) and data else data
        return payload if isinstance(payload, dict) else {"ok": bool(payload)}
    except Exception as exc:
        logger.error("%s complete_scrape_batch_if_ready failed batch=%s: %s", _JOB_TAG, batch_id, exc)
        raise


def get_scrape_missing_sets(market_date: Optional[str] = None) -> List[Dict[str, Any]]:
    """Return cohort sets lacking a valid Near Mint observation for the market date."""
    params: Dict[str, Any] = {}
    if market_date is not None:
        params["p_market_date"] = market_date
    try:
        result = supabase.rpc("pokemon_scrape_missing_sets", params).execute()
        data = _rpc_data(result)
        return list(data) if isinstance(data, list) else []
    except Exception as exc:
        logger.error("%s get_scrape_missing_sets failed: %s", _JOB_TAG, exc)
        raise


def requeue_missing_scrape_jobs_for_batch(batch_id: int) -> int:
    """Requeue only cohort sets missing a valid observation, respecting attempts."""
    try:
        result = supabase.rpc(
            "requeue_missing_scrape_jobs_for_batch", {"p_batch_id": batch_id}
        ).execute()
        count = _normalize_inserted_count(_rpc_data(result))
        if count:
            logger.info("%s cohort repair requeued %s job(s) for batch=%s", _JOB_TAG, count, batch_id)
        return count
    except Exception as exc:
        logger.error("%s requeue_missing_scrape_jobs_for_batch failed batch=%s: %s", _JOB_TAG, batch_id, exc)
        raise


def get_active_batch(market_date: Optional[str] = None) -> Optional[Dict[str, Any]]:
    """Fetch the batch row for a market date (defaults to newest batch)."""
    try:
        query = supabase.table("pokemon_scrape_batches").select("*")
        if market_date is not None:
            query = query.eq("market_date", market_date)
        result = query.order("market_date", desc=True).limit(1).execute()
        rows = result.data if result and result.data else []
        return rows[0] if rows else None
    except Exception as exc:
        logger.error("%s get_active_batch failed: %s", _JOB_TAG, exc)
        raise


def count_active_scrape_jobs(batch_id: Optional[int] = None) -> int:
    """Count pending+running jobs, optionally scoped to a batch (queue-idle check)."""
    try:
        query = (
            supabase.table("scrape_jobs")
            .select("id", count="exact")
            .in_("status", ["pending", "running"])
        )
        if batch_id is not None:
            query = query.eq("batch_id", batch_id)
        result = query.execute()
        if result is not None and getattr(result, "count", None) is not None:
            return int(result.count)
        return len(result.data) if result and result.data else 0
    except Exception as exc:
        logger.error("%s count_active_scrape_jobs failed: %s", _JOB_TAG, exc)
        raise
