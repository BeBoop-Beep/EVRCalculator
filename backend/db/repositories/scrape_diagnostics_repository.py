"""Repository helpers for shared scrape diagnostics tables.

Tables:
    public.scrape_job_runs          — one row per scrape run
    public.scrape_job_run_failures  — one row per failed item within a run

These helpers are intentionally generic so future jobs (eBay price scrape,
image sync, metadata sync, etc.) can reuse the same tables without a schema
redesign.  The caller is responsible for supplying the correct field values;
this module only performs safe database I/O.
"""

from __future__ import annotations

import logging
import time
from typing import Any, Dict, List, Optional

from ..clients.supabase_client import supabase

logger = logging.getLogger(__name__)

_DIAG_TAG = "[scrape-diagnostics]"

# Bounded exponential backoff for transient diagnostic write failures (Phase 5).
_DIAG_MAX_ATTEMPTS = 3
_DIAG_BASE_BACKOFF_SECONDS = 0.5


def _is_transient_db_error(exc: Exception) -> bool:
    message = str(exc).lower()
    return any(
        marker in message
        for marker in (
            "timeout", "timed out", "temporarily unavailable", "connection",
            "reset", "econnreset", "502", "503", "504", "gateway",
            "could not connect", "server closed", "ssl",
        )
    )


# ---------------------------------------------------------------------------
# scrape_job_runs
# ---------------------------------------------------------------------------

def create_scrape_job_run(run_data: Dict[str, Any]) -> Optional[Dict[str, Any]]:
    """Insert a new row into public.scrape_job_runs.

    Args:
        run_data: Mapping of column names to values.  At minimum must include
                  ``job_name``, ``source_system``, ``job_type``, ``entity_type``,
                  ``status``, and ``started_at``.

    Returns:
        The inserted row dict (with DB-generated ``id``, timestamps, etc.),
        or ``None`` if the insert failed.
    """
    try:
        result = supabase.table("scrape_job_runs").insert(run_data).execute()
        if result and result.data:
            row = result.data[0]
            logger.info(
                "%s created run row id=%s job=%s status=%s",
                _DIAG_TAG,
                row.get("id"),
                run_data.get("job_name"),
                run_data.get("status"),
            )
            return row
        logger.warning("%s create_scrape_job_run returned no data", _DIAG_TAG)
        return None
    except Exception as exc:
        logger.error("%s create_scrape_job_run failed: %s", _DIAG_TAG, exc)
        return None


def update_scrape_job_run(run_id: str, run_data: Dict[str, Any]) -> Optional[Dict[str, Any]]:
    """Update an existing row in public.scrape_job_runs by primary key.

    Args:
        run_id:   UUID of the row to update (``id`` column).
        run_data: Mapping of columns to update.  Only include columns you want
                  to change; un-mentioned columns retain their existing values.

    Returns:
        The updated row dict, or ``None`` if the update failed.
    """
    try:
        result = (
            supabase.table("scrape_job_runs")
            .update(run_data)
            .eq("id", run_id)
            .execute()
        )
        if result and result.data:
            row = result.data[0]
            logger.info(
                "%s updated run row id=%s status=%s",
                _DIAG_TAG,
                run_id,
                run_data.get("status", "<unchanged>"),
            )
            return row
        logger.warning("%s update_scrape_job_run id=%s returned no data", _DIAG_TAG, run_id)
        return None
    except Exception as exc:
        logger.error("%s update_scrape_job_run id=%s failed: %s", _DIAG_TAG, run_id, exc)
        return None


def finalize_scrape_job_run(run_id: str, run_data: Dict[str, Any]) -> Dict[str, Any]:
    """Finalize a diagnostic run with bounded retries, surfacing the outcome.

    Unlike :func:`update_scrape_job_run` (which returns ``None`` on failure and can
    silently hide a divergence), this returns an explicit ``{"ok": bool, ...}`` so
    the caller can alert and let the lease watchdog reconcile the queue job. It
    retries transient database/PostgREST errors with exponential backoff.
    """
    last_exc: Optional[Exception] = None
    for attempt in range(1, _DIAG_MAX_ATTEMPTS + 1):
        try:
            result = (
                supabase.table("scrape_job_runs")
                .update(run_data)
                .eq("id", run_id)
                .execute()
            )
            if result and result.data:
                return {"ok": True, "run_id": run_id, "row": result.data[0]}
            # No row updated is not a transient error — surface it clearly.
            logger.error(
                "%s finalize_scrape_job_run id=%s updated no rows", _DIAG_TAG, run_id
            )
            return {"ok": False, "run_id": run_id, "reason": "no_rows_updated"}
        except Exception as exc:
            last_exc = exc
            if not _is_transient_db_error(exc) or attempt == _DIAG_MAX_ATTEMPTS:
                break
            backoff = _DIAG_BASE_BACKOFF_SECONDS * (2 ** (attempt - 1))
            logger.warning(
                "%s transient finalize_scrape_job_run failure id=%s attempt %s/%s: %s; retrying in %.1fs",
                _DIAG_TAG, run_id, attempt, _DIAG_MAX_ATTEMPTS, exc, backoff,
            )
            time.sleep(backoff)

    logger.error(
        "%s finalize_scrape_job_run id=%s permanently failed: %s", _DIAG_TAG, run_id, last_exc
    )
    return {"ok": False, "run_id": run_id, "reason": "db_error", "error": str(last_exc)}


# ---------------------------------------------------------------------------
# scrape_job_run_failures
# ---------------------------------------------------------------------------

def insert_scrape_job_run_failures(rows: List[Dict[str, Any]]) -> Optional[List[Dict[str, Any]]]:
    """Bulk-insert rows into public.scrape_job_run_failures.

    Each row should include at minimum:
        - ``run_id``       (FK → scrape_job_runs.id)
        - ``source_system``
        - ``job_type``
        - ``entity_type``
        - ``entity_key``
        - ``error_message``

    Optional fields:
        - ``entity_name``
        - ``attempt_count``
        - ``rate_limit_like``
        - ``metadata``   (dict → stored as JSONB)

    Args:
        rows: List of failure row dicts.

    Returns:
        Inserted rows, or ``None`` if the insert failed.
    """
    if not rows:
        return []
    try:
        result = supabase.table("scrape_job_run_failures").insert(rows).execute()
        if result and result.data:
            logger.info(
                "%s inserted %d failure row(s) for run_id=%s",
                _DIAG_TAG,
                len(result.data),
                rows[0].get("run_id"),
            )
            return result.data
        logger.warning("%s insert_scrape_job_run_failures returned no data", _DIAG_TAG)
        return None
    except Exception as exc:
        logger.error("%s insert_scrape_job_run_failures failed: %s", _DIAG_TAG, exc)
        return None
