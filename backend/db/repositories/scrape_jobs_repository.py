from __future__ import annotations

import logging
from datetime import datetime, timezone
from typing import Any, Dict, Optional

from ..clients.supabase_client import supabase

logger = logging.getLogger(__name__)

_JOB_TAG = "[scrape-jobs]"


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
