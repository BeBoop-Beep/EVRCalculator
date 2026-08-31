from __future__ import annotations

import argparse
import logging
import os
import signal
import socket
import sys
import time
from pathlib import Path
from typing import Optional

_PROJECT_ROOT = os.path.abspath(os.path.join(os.path.dirname(__file__), "..", ".."))
if _PROJECT_ROOT not in sys.path:
    sys.path.insert(0, _PROJECT_ROOT)

_SCRAPER_ROOT = os.path.join(_PROJECT_ROOT, "backend", "Scraper")
if _SCRAPER_ROOT not in sys.path:
    sys.path.insert(0, _SCRAPER_ROOT)

from backend.db.repositories.scrape_jobs_repository import (
    DEFAULT_LEASE_SECONDS,
    claim_next_scrape_job,
    finalize_scrape_job,
)
from backend.db.repositories.sets_repository import get_set_by_id
from backend.db.services.scrape_failure_classification import (
    ERROR_CATALOG_ONLY_NOT_DAILY_ELIGIBLE,
    ERROR_MISSING_CANONICAL_KEY,
    ERROR_SET_NOT_FOUND,
    ERROR_TRANSIENT_SCRAPE_FAILURE,
    classify_report_failure,
    is_deterministic,
    remediation_for,
)
from backend.scripts.run_pokemon_set_scrape import (
    _apply_safe_runtime_defaults,
    _load_backend_env,
    _market_date_iso,
    extract_reconciliation_metrics,
    run_scraper,
)

logging.basicConfig(level=logging.INFO, format="%(message)s")
logger = logging.getLogger(__name__)

DISPATCHER_TAG = "[scrape-job-dispatcher]"
DEFAULT_JOB_REPORT_DIR = Path("backend/constants/tcg/pokemon/scrape_job_reports")
DEFAULT_DRAIN_MAX_JOBS = 200
DEFAULT_DRAIN_MAX_RUNTIME_SECONDS = 6 * 60 * 60
MAX_CONSECUTIVE_EMPTY_REPAIRS = 2
_stop_after_current_job = False


def _worker_id() -> str:
    try:
        host = socket.gethostname()[:100]
    except Exception:
        host = "unknown"
    return f"{host}:{os.getpid()}"


def _lease_seconds() -> int:
    try:
        return max(60, int(os.getenv("SCRAPE_LEASE_SECONDS", str(DEFAULT_LEASE_SECONDS))))
    except ValueError:
        return DEFAULT_LEASE_SECONDS


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


def _alert_if_retries_exhausted(job: dict, *, canonical_key: Optional[str],
                                error_code: str, error_summary: str) -> None:
    attempts = int(job.get("attempts") or 0)
    max_attempts = int(job.get("max_attempts") or 0)
    if max_attempts <= 0 or attempts < max_attempts:
        return
    try:
        from backend.alerts.pipeline_alerts import alert_set_scrape_failed
        alert_set_scrape_failed(
            market_date=str(job.get("market_date") or ""), batch_id=job.get("batch_id"),
            queue_job_id=job.get("id"), canonical_key=canonical_key or "unknown",
            attempts=attempts, max_attempts=max_attempts, error_code=error_code,
            retryable=False, error_summary=error_summary,
        )
    except Exception:  # pragma: no cover - terminal state remains authoritative
        logger.exception("%s failed to queue terminal scrape alert", DISPATCHER_TAG)


def _request_metrics(report: dict) -> dict:
    keys = (
        "http_requests_total",
        "http_requests_cache_hits",
        "http_requests_cache_misses",
        "http_requests_skipped_redundant",
        "rate_limit_events",
        "retry_count_total",
        "elapsed_seconds",
    )
    metrics = {key: report.get(key) for key in keys if report.get(key) is not None}
    metrics.update(extract_reconciliation_metrics(report))
    return metrics


def _finalize(
    job_id: int,
    report: Optional[dict],
    final_status: str,
    *,
    succeeded: int,
    failed: int,
    error_summary: Optional[str],
    canonical_key: Optional[str] = None,
    error_code: Optional[str] = None,
) -> None:
    """Finalize the queue job + diagnostic run + batch counters transactionally.

    On permanent DB failure a durable local recovery record is written and a
    high-severity alert is queued; the lease watchdog will reconcile the job.

    A deterministic ``error_code`` is passed through so the database burns the
    remaining attempt budget: a configuration/deployment failure must not consume
    three identical attempts, and cohort repair must not reopen it.
    """
    report = report or {}
    result = finalize_scrape_job(
        job_id,
        diag_run_id=report.get("diag_run_id"),
        final_status=final_status,
        succeeded=succeeded,
        failed=failed,
        metrics=_request_metrics(report),
        error_summary=error_summary,
        report_path=str(_build_job_report_path(job_id)),
        error_code=error_code,
    )
    logger.info(
        "%s final status update job id=%s -> %s error_code=%s",
        DISPATCHER_TAG, job_id, final_status, error_code,
    )

    if final_status == "failed" and is_deterministic(error_code):
        logger.error(
            "%s DETERMINISTIC failure job id=%s canonical_key=%s code=%s — not retryable. %s",
            DISPATCHER_TAG, job_id, canonical_key, error_code,
            remediation_for(error_code) or "",
        )
        try:
            from backend.alerts.scrape_alerts import alert_deterministic_scrape_failure

            alert_deterministic_scrape_failure(
                job_id=job_id,
                canonical_key=canonical_key,
                error_code=str(error_code),
                market_date=report.get("market_date"),
                error_summary=error_summary,
            )
        except Exception:  # pragma: no cover - alerting must never break the worker
            logger.exception("%s failed to queue deterministic-failure alert", DISPATCHER_TAG)

    if not result.get("ok"):
        try:
            from backend.alerts.scrape_alerts import alert_finalization_db_failure

            alert_finalization_db_failure(
                job_id,
                market_date=report.get("market_date"),
                canonical_key=canonical_key,
                error=result.get("error"),
                recovery_record=result.get("recovery_record"),
            )
        except Exception:  # pragma: no cover - alerting must never break the worker
            logger.exception("%s failed to queue finalization-failure alert", DISPATCHER_TAG)


def _run_idle_completion_check(market_date: Optional[str] = None) -> dict:
    """When the queue is idle, evaluate batch completeness and repair the cohort."""
    try:
        from backend.db.services.scrape_batch_service import run_batch_completion_and_repair

        summary = run_batch_completion_and_repair(market_date=market_date)
        logger.info("%s idle batch check: %s", DISPATCHER_TAG, summary)
        return summary or {}
    except Exception:  # pragma: no cover - completion check is best-effort
        logger.exception("%s idle batch completion check failed", DISPATCHER_TAG)
        return {}


def _positive_env_int(name: str, default: int) -> int:
    try:
        return max(1, int(os.getenv(name, str(default))))
    except ValueError:
        logger.warning("%s invalid %s; using %s", DISPATCHER_TAG, name, default)
        return default


def _request_stop(signum, _frame) -> None:
    global _stop_after_current_job
    _stop_after_current_job = True
    logger.warning("%s signal=%s received; stopping after current job", DISPATCHER_TAG, signum)


def _install_signal_handlers() -> None:
    if hasattr(signal, "SIGTERM"):
        signal.signal(signal.SIGTERM, _request_stop)
    if hasattr(signal, "SIGINT"):
        signal.signal(signal.SIGINT, _request_stop)


def _process_claimed_job(job: dict, worker_market_date: str) -> None:
    claimed_market_date = str(job.get("market_date") or "")
    if claimed_market_date != worker_market_date:
        # Logically unreachable with the atomic date-qualified claim. Do not
        # scrape, backdate, or deterministically exhaust retries. Leaving the
        # lease intact lets the existing watchdog reconcile this serious DB
        # contract violation without inventing an unsafe release transition.
        raise RuntimeError(
            f"date-qualified claim contract violation: job {job.get('id')} "
            f"market_date={claimed_market_date or 'missing'} "
            f"worker_market_date={worker_market_date}"
        )

    # Claiming reconciles expired leases first (DB watchdog), so a crashed prior
    # worker's job is reclaimed rather than blocking the queue. Batch creation is
    # a SEPARATE scheduled operation — the worker never implicitly creates a batch.
    job_id = int(job["id"])
    set_id = str(job["set_id"])
    logger.info("%s processing claimed job id=%s set_id=%s", DISPATCHER_TAG, job_id, set_id)

    set_row = get_set_by_id(set_id)
    if not set_row:
        logger.error("%s set lookup failed for job id=%s set_id=%s", DISPATCHER_TAG, job_id, set_id)
        _finalize(job_id, None, "failed", succeeded=0, failed=1,
                  error_summary=f"Set not found for set_id={set_id}",
                  error_code=ERROR_SET_NOT_FOUND)
        return 0

    canonical_key: Optional[str] = set_row.get("canonical_key")
    if not canonical_key:
        logger.error("%s canonical_key missing for job id=%s set_id=%s", DISPATCHER_TAG, job_id, set_id)
        _finalize(job_id, None, "failed", succeeded=0, failed=1,
                  error_summary=f"Set canonical_key missing for set_id={set_id}",
                  error_code=ERROR_MISSING_CANONICAL_KEY)
        return 0

    # Secondary defence behind the preflight: if a catalog-only set somehow
    # reached the queue (a race against a metadata sync), fail it deterministically
    # rather than letting it retry and hold the batch incomplete.
    if set_row.get("catalog_only") is True:
        logger.error(
            "%s catalog-only set reached the daily queue job id=%s canonical_key=%s",
            DISPATCHER_TAG, job_id, canonical_key,
        )
        _finalize(job_id, None, "failed", succeeded=0, failed=1,
                  error_summary=f"Set {canonical_key} is catalog_only and is not daily-eligible",
                  canonical_key=canonical_key,
                  error_code=ERROR_CATALOG_ONLY_NOT_DAILY_ELIGIBLE)
        return 0

    logger.info("%s scraper start job id=%s canonical_key=%s", DISPATCHER_TAG, job_id, canonical_key)

    try:
        report = run_scraper(
            dry_run=False,
            era_filter=None,
            set_key_filter=canonical_key,
            limit=1,
            enable_db_ingestion=True,
            shuffle_within_date=False,
            report_path=_build_job_report_path(job_id),
            queue_job_id=job_id,
        )
    except Exception as exc:
        error_message = _truncate_error_message(exc)
        logger.exception("%s scraper failure job id=%s canonical_key=%s", DISPATCHER_TAG, job_id, canonical_key)
        # An unexpected exception is treated as transient: it keeps its retries.
        _finalize(job_id, None, "failed", succeeded=0, failed=1,
                  error_summary=error_message, canonical_key=canonical_key,
                  error_code=ERROR_TRANSIENT_SCRAPE_FAILURE)
        _alert_if_retries_exhausted(
            job, canonical_key=canonical_key, error_code=ERROR_TRANSIENT_SCRAPE_FAILURE,
            error_summary=error_message)
        return 0

    if report.get("sets_succeeded") == 1 and report.get("sets_failed") == 0:
        logger.info("%s scraper success job id=%s canonical_key=%s", DISPATCHER_TAG, job_id, canonical_key)
        _finalize(job_id, report, "completed", succeeded=1, failed=0,
                  error_summary=None, canonical_key=canonical_key)
        return 0

    error_message = _report_error_summary(report)
    # This is the path the 2026-08-03 failures took: run_scraper returns a report
    # with run_abort_reason='invalid_set_key_filter'. Classifying it here is what
    # stops three identical attempts and turns it into an actionable alert.
    error_code = classify_report_failure(report) or ERROR_TRANSIENT_SCRAPE_FAILURE
    logger.error(
        "%s scraper failure job id=%s canonical_key=%s code=%s summary=%s",
        DISPATCHER_TAG, job_id, canonical_key, error_code, error_message,
    )
    _finalize(job_id, report, "failed", succeeded=0, failed=1,
              error_summary=error_message, canonical_key=canonical_key,
              error_code=error_code)
    if not is_deterministic(error_code):
        _alert_if_retries_exhausted(
            job, canonical_key=canonical_key, error_code=error_code,
            error_summary=error_message)
    return 0


def dispatch_next_scrape_job(market_date: Optional[str] = None) -> int:
    """Drain eligible jobs sequentially under the caller's existing flock.

    Defaults permit a normal 167-set batch while bounding the process to 200
    jobs or six hours. Both guards are configurable through
    SCRAPE_DRAIN_MAX_JOBS and SCRAPE_DRAIN_MAX_RUNTIME_SECONDS.
    """
    global _stop_after_current_job
    logger.info("%s dispatcher start", DISPATCHER_TAG)
    _load_backend_env()
    _apply_safe_runtime_defaults()
    os.environ.setdefault("SCRAPE_TRIGGER_SOURCE", "scheduled")

    _stop_after_current_job = False
    _install_signal_handlers()
    worker_id = _worker_id()
    lease_seconds = _lease_seconds()
    worker_market_date = market_date or _market_date_iso()
    max_jobs = _positive_env_int("SCRAPE_DRAIN_MAX_JOBS", DEFAULT_DRAIN_MAX_JOBS)
    max_runtime = _positive_env_int(
        "SCRAPE_DRAIN_MAX_RUNTIME_SECONDS", DEFAULT_DRAIN_MAX_RUNTIME_SECONDS)
    started = time.monotonic()
    jobs_processed = 0
    consecutive_empty_repairs = 0

    while True:
        if _stop_after_current_job or jobs_processed >= max_jobs:
            break
        if jobs_processed and time.monotonic() - started >= max_runtime:
            break
        if market_date is None and _market_date_iso() != worker_market_date:
            logger.warning("%s Phoenix market date changed; stopping before claim", DISPATCHER_TAG)
            break

        job = claim_next_scrape_job(
            worker_id=worker_id, lease_seconds=lease_seconds,
            expected_market_date=worker_market_date,
        )
        if not job:
            logger.info("%s no pending scrape jobs found", DISPATCHER_TAG)
            summary = _run_idle_completion_check(worker_market_date) or {}
            if int(summary.get("requeued") or 0) > 0:
                consecutive_empty_repairs += 1
                if consecutive_empty_repairs < MAX_CONSECUTIVE_EMPTY_REPAIRS:
                    continue
            break

        consecutive_empty_repairs = 0
        _process_claimed_job(job, worker_market_date)
        jobs_processed += 1

    logger.info("%s dispatcher exit jobs_processed=%s", DISPATCHER_TAG, jobs_processed)
    return 0


def main() -> int:
    parser = argparse.ArgumentParser(description="Drain the normal Pokémon scrape queue for one market date")
    parser.add_argument(
        "--market-date",
        default=None,
        help="Explicit America/Phoenix recovery date; default is the current Phoenix date.",
    )
    args = parser.parse_args()
    try:
        return dispatch_next_scrape_job(market_date=args.market_date)
    except Exception:
        logger.exception("%s dispatcher runtime failure", DISPATCHER_TAG)
        return 1


if __name__ == "__main__":
    raise SystemExit(main())
