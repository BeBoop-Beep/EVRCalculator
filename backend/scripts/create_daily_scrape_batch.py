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
import sys
from datetime import datetime, timezone
from pathlib import Path

_PROJECT_ROOT = os.path.abspath(os.path.join(os.path.dirname(__file__), "..", ".."))
if _PROJECT_ROOT not in sys.path:
    sys.path.insert(0, _PROJECT_ROOT)

from backend.db.repositories.scrape_jobs_repository import (
    create_daily_scrape_batch,
    get_active_batch,
)
from backend.scripts.run_pokemon_set_scrape import _load_backend_env, _market_date_iso

logging.basicConfig(level=logging.INFO, format="%(message)s")
logger = logging.getLogger(__name__)

BATCH_TAG = "[scrape-batch-create]"
MARKET_TIMEZONE = "America/Phoenix"


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
    args = parser.parse_args()

    _load_backend_env()
    market_date = args.market_date or _market_date_iso(MARKET_TIMEZONE)

    try:
        if args.check_only:
            return check_only(market_date, deadline=datetime.now(timezone.utc).isoformat())

        batch = create_batch(market_date, args.trigger_source)
        print(json.dumps({
            "batch_id": batch.get("id"),
            "market_date": str(batch.get("market_date")),
            "status": batch.get("status"),
            "expected_set_count": batch.get("expected_set_count"),
            "queued_set_count": batch.get("queued_set_count"),
            "trigger_source": args.trigger_source,
        }, indent=2))
        return 0
    except Exception as exc:
        logger.exception("%s batch creation failed: %s", BATCH_TAG, exc)
        return 1


if __name__ == "__main__":
    raise SystemExit(main())
