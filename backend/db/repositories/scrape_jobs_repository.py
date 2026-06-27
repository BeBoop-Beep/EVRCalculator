from __future__ import annotations

import logging
from datetime import datetime, timedelta, timezone
from typing import Any, Dict, Iterable, List, Optional, Sequence, Set

from ..clients.supabase_client import supabase

logger = logging.getLogger(__name__)

_JOB_TAG = "[scrape-jobs]"
_SCRAPE_JOB_CYCLE_STATUSES = ("pending", "running", "completed", "failed")
_SCRAPE_READY_SET_SELECT = "id"
_SCRAPE_JOB_INSERT_CHUNK_SIZE = 500


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


def claim_next_scrape_job() -> Optional[Dict[str, Any]]:
    try:
        result = supabase.rpc("claim_next_scrape_job").execute()
        if result and result.data:
            job = result.data[0]
            logger.info(
                "%s claimed job id=%s set_id=%s attempts=%s",
                _JOB_TAG,
                job.get("id"),
                job.get("set_id"),
                job.get("attempts"),
            )
            return job
        logger.info("%s no pending scrape jobs available", _JOB_TAG)
        return None
    except Exception as exc:
        logger.error("%s claim_next_scrape_job failed: %s", _JOB_TAG, exc)
        raise


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
