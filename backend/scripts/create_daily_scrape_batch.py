"""Create the daily Pokémon scrape batch for an America/Phoenix market date.

This is the explicit, SCHEDULED batch/enqueue operation — separate from worker
dispatch. The worker (``run_next_scrape_job.py``) only claims pending jobs from an
already-created batch and must never implicitly create a batch because the UTC
date changed.

Root-cause fix (July 17 incident): batch creation reconciles stale/crashed jobs
first, then derives the expected cohort dynamically and enqueues one job per ready
set that has no active job — so a stale prior-day ``running`` job can no longer
silently exclude a set.

Recommended schedule (Arizona does not observe DST):
    batch creation: 03:00 America/Phoenix  ==  10:00 UTC (fixed)

Usage:
    # Scheduled batch for today's Arizona market date
    python backend/scripts/create_daily_scrape_batch.py

    # Explicit market date (e.g. backfill / recovery)
    python backend/scripts/create_daily_scrape_batch.py --market-date 2026-07-18

    # Manual targeted recovery keeps trigger_source=manual
    python backend/scripts/create_daily_scrape_batch.py --trigger-source manual

    # Only alert (do not create) if today's batch is missing past deadline
    python backend/scripts/create_daily_scrape_batch.py --check-only
"""

from __future__ import annotations

import argparse
import json
import logging
import os
import subprocess
import sys
from datetime import datetime, timezone
from pathlib import Path

_PROJECT_ROOT = os.path.abspath(os.path.join(os.path.dirname(__file__), "..", ".."))
if _PROJECT_ROOT not in sys.path:
    sys.path.insert(0, _PROJECT_ROOT)

from backend.db.repositories.scrape_jobs_repository import (
    create_daily_scrape_batch,
    get_active_batch,
    record_batch_runtime_provenance,
)
from backend.db.services.pokemon_scrape_runtime_preflight import (
    RuntimePreflightReport,
    format_preflight_json,
    run_runtime_preflight,
)
from backend.scripts.run_pokemon_set_scrape import _load_backend_env, _market_date_iso

logging.basicConfig(level=logging.INFO, format="%(message)s")
logger = logging.getLogger(__name__)

BATCH_TAG = "[scrape-batch-create]"
MARKET_TIMEZONE = "America/Phoenix"
DISCOVERY_TIMEOUT_SECONDS = 180


def run_preflight_or_fail(market_date: str, *, preflight_runner=None) -> RuntimePreflightReport:
    """Verify runtime/database registry parity BEFORE any batch or job is created.

    A mismatch means the database expects canonical keys this deployed runtime
    cannot resolve (or vice versa). Creating a batch anyway is what produced the
    2026-08-03 incident: 34 jobs that could only ever fail, each retried three
    times, holding the batch incomplete.

    ``preflight_runner`` is a test-only injection seam. There is deliberately no
    production bypass flag.
    """
    report = (preflight_runner or run_runtime_preflight)()
    for line in report.report_lines():
        logger.info("%s", line)

    if report.ok:
        return report

    logger.error(
        "%s runtime/database registry preflight FAILED for market_date=%s "
        "(mismatches=%s); refusing to create a batch or enqueue any job",
        BATCH_TAG, market_date, report.mismatch_count,
    )
    try:
        from backend.alerts.scrape_alerts import alert_runtime_registry_mismatch

        alert_runtime_registry_mismatch(market_date, report=report)
    except Exception:  # pragma: no cover - alerting must never mask the failure
        logger.exception("%s failed to queue runtime_registry_mismatch alert", BATCH_TAG)

    raise PreflightFailedError(report)


class PreflightFailedError(RuntimeError):
    """Raised when runtime/database registry parity fails; blocks batch creation."""

    def __init__(self, report: RuntimePreflightReport) -> None:
        super().__init__(
            "runtime/database scrape registry preflight failed with "
            f"{report.mismatch_count} mismatch(es)"
        )
        self.report = report


def persist_runtime_provenance(batch_id, report: RuntimePreflightReport) -> dict:
    """Record which code SHA / registry hash validated and created this batch.

    Returns a status dict. A provenance write failure is reported honestly rather
    than swallowed: the batch exists and is valid, but it is not fully traceable.
    """
    try:
        ok = record_batch_runtime_provenance(
            batch_id,
            runtime_git_sha=report.runtime_git_sha,
            runtime_registry_hash=report.local_registry_hash,
            runtime_preflight_json=report.to_dict(),
        )
    except Exception as exc:
        logger.error("%s failed to record runtime provenance on batch %s: %s", BATCH_TAG, batch_id, exc)
        return {"status": "failed", "error": str(exc)}

    if not ok:
        logger.error("%s runtime provenance write reported no updated row for batch %s", BATCH_TAG, batch_id)
        return {"status": "failed", "error": "no batch row updated"}

    return {
        "status": "recorded",
        "runtime_git_sha": report.runtime_git_sha,
        "runtime_registry_hash": report.local_registry_hash,
    }


def create_batch(market_date: str, trigger_source: str) -> dict:
    batch = create_daily_scrape_batch(
        market_date=market_date,
        timezone_name=MARKET_TIMEZONE,
        trigger_source=trigger_source,
    )
    if not batch:
        raise RuntimeError("create_daily_scrape_batch returned no batch row")
    logger.info(
        "%s batch ready id=%s market_date=%s status=%s expected=%s queued=%s trigger=%s",
        BATCH_TAG,
        batch.get("id"),
        batch.get("market_date"),
        batch.get("status"),
        batch.get("expected_set_count"),
        batch.get("queued_set_count"),
        trigger_source,
    )
    return batch


def check_only(market_date: str, deadline: str) -> int:
    batch = get_active_batch(market_date)
    if batch:
        logger.info("%s batch already exists for %s (id=%s)", BATCH_TAG, market_date, batch.get("id"))
        return 0

    logger.error("%s no batch exists for market_date=%s past deadline", BATCH_TAG, market_date)
    try:
        from backend.alerts.scrape_alerts import alert_batch_not_created

        alert_batch_not_created(market_date, deadline=deadline)
    except Exception:  # pragma: no cover
        logger.exception("%s failed to queue batch_not_created alert", BATCH_TAG)
    return 1


def run_new_set_discovery(timeout_seconds: int = DISCOVERY_TIMEOUT_SECONDS) -> dict:
    """Run bounded post-batch discovery; never raise into the batch critical path."""
    command = [
        sys.executable, str(Path(__file__).with_name("discover_new_pokemon_sets.py")),
        "--commit", "--json",
    ]
    try:
        completed = subprocess.run(
            command, capture_output=True, text=True, timeout=timeout_seconds, check=False,
        )
        try:
            payload = json.loads(completed.stdout)
        except (TypeError, json.JSONDecodeError):
            payload = {"stdout": completed.stdout[-2000:]}
        return {
            "status": "completed" if completed.returncode == 0 else "failed",
            "exit_code": completed.returncode, "result": payload,
            "stderr": completed.stderr[-2000:] or None,
        }
    except subprocess.TimeoutExpired:
        logger.warning("%s new-set discovery timed out after %ss", BATCH_TAG, timeout_seconds)
        return {"status": "timed_out", "timeout_seconds": timeout_seconds}
    except Exception as exc:  # best-effort by design
        logger.exception("%s new-set discovery failed", BATCH_TAG)
        return {"status": "failed", "error": str(exc)}


def main() -> int:
    parser = argparse.ArgumentParser(description="Create the daily Pokémon scrape batch (America/Phoenix).")
    parser.add_argument(
        "--market-date",
        default=None,
        help="Market date (YYYY-MM-DD, America/Phoenix). Defaults to today in Arizona.",
    )
    parser.add_argument(
        "--trigger-source",
        default="scheduled",
        choices=["scheduled", "manual"],
        help="How this batch creation was invoked (default: scheduled).",
    )
    parser.add_argument(
        "--check-only",
        action="store_true",
        help="Do not create; alert if the batch is missing (deadline monitor).",
    )
    parser.add_argument(
        "--skip-new-set-detection", action="store_true",
        help="Skip the bounded best-effort post-batch new-set detector.",
    )
    parser.add_argument(
        "--new-set-detection-timeout", type=int, default=DISCOVERY_TIMEOUT_SECONDS,
        help=argparse.SUPPRESS,
    )
    args = parser.parse_args()

    _load_backend_env()
    market_date = args.market_date or _market_date_iso(MARKET_TIMEZONE)

    try:
        if args.check_only:
            return check_only(market_date, deadline=datetime.now(timezone.utc).isoformat())

        # Registry parity is verified BEFORE the batch RPC. On failure this
        # raises, so no batch is created and no job is enqueued.
        preflight = run_preflight_or_fail(market_date)

        batch = create_batch(market_date, args.trigger_source)
        provenance = persist_runtime_provenance(batch.get("id"), preflight)
        if provenance.get("status") == "recorded":
            try:
                from backend.alerts.pipeline_alerts import alert_daily_batch_created
                alert_daily_batch_created(
                    market_date=market_date, batch_id=batch.get("id"),
                    expected_set_count=int(batch.get("expected_set_count") or 0),
                    queued_set_count=int(batch.get("queued_set_count") or 0),
                    trigger_source=args.trigger_source,
                    runtime_git_sha=preflight.runtime_git_sha,
                    runtime_registry_hash=preflight.local_registry_hash,
                )
            except Exception:  # pragma: no cover - observability cannot block creation
                logger.exception("%s failed to queue daily-batch-created alert", BATCH_TAG)
        discovery = (
            {"status": "skipped"}
            if args.skip_new_set_detection
            else run_new_set_discovery(max(1, args.new_set_detection_timeout))
        )
        print(json.dumps({
            "batch_id": batch.get("id"),
            "market_date": str(batch.get("market_date")),
            "status": batch.get("status"),
            "expected_set_count": batch.get("expected_set_count"),
            "queued_set_count": batch.get("queued_set_count"),
            "trigger_source": args.trigger_source,
            "runtime_preflight": preflight.to_dict(),
            "runtime_provenance": provenance,
            "new_set_discovery": discovery,
        }, indent=2))
        # The batch is valid, but claiming it is "fully verified" when its
        # provenance could not be written would be a lie.
        return 0 if provenance.get("status") == "recorded" else 1
    except PreflightFailedError as exc:
        print(format_preflight_json(exc.report))
        return 1
    except Exception as exc:
        logger.exception("%s batch creation failed: %s", BATCH_TAG, exc)
        return 1


if __name__ == "__main__":
    raise SystemExit(main())
