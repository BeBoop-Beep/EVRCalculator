from __future__ import annotations

import logging
import os
import sys
from pathlib import Path
from typing import Optional

_PROJECT_ROOT = os.path.abspath(os.path.join(os.path.dirname(__file__), "..", ".."))
if _PROJECT_ROOT not in sys.path:
    sys.path.insert(0, _PROJECT_ROOT)

_SCRAPER_ROOT = os.path.join(_PROJECT_ROOT, "backend", "Scraper")
if _SCRAPER_ROOT not in sys.path:
    sys.path.insert(0, _SCRAPER_ROOT)

from backend.db.repositories.scrape_jobs_repository import (
    claim_next_scrape_job,
    mark_scrape_job_completed,
    mark_scrape_job_failed,
)
from backend.db.repositories.sets_repository import get_set_by_id
from run_pokemon_set_scrape import (
    _apply_safe_runtime_defaults,
    _load_backend_env,
    run_scraper,
)

logging.basicConfig(level=logging.INFO, format="%(message)s")
logger = logging.getLogger(__name__)

DISPATCHER_TAG = "[scrape-job-dispatcher]"
DEFAULT_JOB_REPORT_DIR = Path("backend/constants/tcg/pokemon/scrape_job_reports")


def _build_job_report_path(job_id: int) -> Path:
    return DEFAULT_JOB_REPORT_DIR / f"scrape_job_{job_id}.json"


def _truncate_error_message(exc: BaseException) -> str:
    return f"{type(exc).__name__}: {exc}"[:2000]


def _report_error_summary(report: dict) -> str:
    if report.get("run_abort_reason"):
        return str(report["run_abort_reason"])

    results = report.get("results") or []
    if results:
        first_error = results[0].get("error")
        if first_error:
            return str(first_error)[:2000]

    if report.get("sets_selected", 0) == 0:
        return "Selected set did not resolve to a scrape-ready target"

    return "Single scrape job did not complete successfully"


def dispatch_next_scrape_job() -> int:
    logger.info("%s dispatcher start", DISPATCHER_TAG)

    _load_backend_env()
    _apply_safe_runtime_defaults()

    job = claim_next_scrape_job()
    if not job:
        logger.info("%s no pending scrape jobs found", DISPATCHER_TAG)
        return 0

    job_id = int(job["id"])
    set_id = str(job["set_id"])
    logger.info("%s claimed job id=%s set_id=%s", DISPATCHER_TAG, job_id, set_id)

    set_row = get_set_by_id(set_id)
    if not set_row:
        logger.error("%s set lookup failed for job id=%s set_id=%s", DISPATCHER_TAG, job_id, set_id)
        mark_scrape_job_failed(job_id, f"Set not found for set_id={set_id}")
        logger.info("%s final status update job id=%s -> failed", DISPATCHER_TAG, job_id)
        return 0

    canonical_key: Optional[str] = set_row.get("canonical_key")
    if not canonical_key:
        logger.error("%s canonical_key missing for job id=%s set_id=%s", DISPATCHER_TAG, job_id, set_id)
        mark_scrape_job_failed(job_id, f"Set canonical_key missing for set_id={set_id}")
        logger.info("%s final status update job id=%s -> failed", DISPATCHER_TAG, job_id)
        return 0

    logger.info(
        "%s scraper start job id=%s canonical_key=%s",
        DISPATCHER_TAG,
        job_id,
        canonical_key,
    )

    try:
        report = run_scraper(
            dry_run=False,
            era_filter=None,
            set_key_filter=canonical_key,
            limit=1,
            enable_db_ingestion=True,
            shuffle_within_date=False,
            report_path=_build_job_report_path(job_id),
        )
    except Exception as exc:
        error_message = _truncate_error_message(exc)
        logger.exception("%s scraper failure job id=%s canonical_key=%s", DISPATCHER_TAG, job_id, canonical_key)
        mark_scrape_job_failed(job_id, error_message)
        logger.info("%s final status update job id=%s -> failed", DISPATCHER_TAG, job_id)
        return 0

    if report.get("sets_succeeded") == 1 and report.get("sets_failed") == 0:
        logger.info("%s scraper success job id=%s canonical_key=%s", DISPATCHER_TAG, job_id, canonical_key)
        mark_scrape_job_completed(job_id)
        logger.info("%s final status update job id=%s -> completed", DISPATCHER_TAG, job_id)
        return 0

    error_message = _report_error_summary(report)
    logger.error(
        "%s scraper failure job id=%s canonical_key=%s summary=%s",
        DISPATCHER_TAG,
        job_id,
        canonical_key,
        error_message,
    )
    mark_scrape_job_failed(job_id, error_message)
    logger.info("%s final status update job id=%s -> failed", DISPATCHER_TAG, job_id)
    return 0


def main() -> int:
    try:
        return dispatch_next_scrape_job()
    except Exception:
        logger.exception("%s dispatcher runtime failure", DISPATCHER_TAG)
        return 1


if __name__ == "__main__":
    raise SystemExit(main())
