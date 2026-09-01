"""Publish-if-needed wrapper: the 6:00 AM fallback/watchdog entry point.

This is the "target: `0 6 * * * publish_if_needed_for_today`" command. It
replaces the old *blind* 6:00 AM rebuild with a small decision:

    scrape batch not complete for the date                -> do nothing
    scrape batch complete + publication already current    -> do nothing
    scrape batch complete + publication missing/stale      -> run the
                                                               canonical
                                                               publication
                                                               wrapper

The normal path is the IMMEDIATE trigger fired from
``backend/scripts/run_next_scrape_job.py`` the moment the scrape batch
becomes authoritatively complete (see
``backend.db.services.post_scrape_publication_trigger``). This script is the
FALLBACK: it exists so a missed/failed immediate launch still gets published
by 6:00 AM, and so an operator has one command to check/force the same
decision for any date.

It never bypasses the batch-cohort gate and never passes ``--force-publish``.
It is safe to run repeatedly (idempotent) and safe to run concurrently with
an already-running publisher — ``rebuild_snapshots_after_scrape.sh`` holds
its own single-publisher ``flock`` and treats a held lock as a no-op.
"""

from __future__ import annotations

import argparse
import logging
import os
import subprocess
import sys
from pathlib import Path
from typing import Optional

_PROJECT_ROOT = Path(__file__).resolve().parents[2]
if str(_PROJECT_ROOT) not in sys.path:
    sys.path.insert(0, str(_PROJECT_ROOT))

logging.basicConfig(level=logging.INFO, format="%(message)s")
logger = logging.getLogger(__name__)

TAG = "[publish-if-needed]"

REBUILD_SCRIPT = _PROJECT_ROOT / "backend" / "scripts" / "rebuild_snapshots_after_scrape.sh"

STATUS_NOOP_NOT_COMPLETE = "noop_batch_not_complete"
STATUS_NOOP_ALREADY_CURRENT = "noop_already_current"
STATUS_PUBLISHED = "published"
STATUS_PUBLISH_FAILED = "publish_failed"
STATUS_INVALID_MARKET_DATE = "invalid_market_date"


def _resolve_market_date(explicit: Optional[str]) -> str:
    if explicit:
        return explicit
    from backend.scripts.run_pokemon_set_scrape import _market_date_iso

    return _market_date_iso()


def _batch_complete(client, market_date: str) -> bool:
    """Independent completeness check using the SAME gate the refresh uses.

    Read-only: never requeues or mutates. Batch completion authority stays in
    ``run_batch_completion_and_repair`` / ``complete_scrape_batch_if_ready``.
    """
    from backend.db.services.publication_gate import evaluate_publication_gate

    decision = evaluate_publication_gate(client, market_date=market_date)
    logger.info(
        "%s gate check market_date=%s allowed=%s reason_code=%s",
        TAG, market_date, decision.allowed, decision.reason_code,
    )
    return bool(decision.allowed)


def _already_current(client, market_date: str) -> bool:
    from backend.scripts.audit_pokemon_market_publication import (
        PHASE_POST_SCRAPE,
        run_market_publication_audit,
    )

    report = run_market_publication_audit(client, market_date=market_date, phase=PHASE_POST_SCRAPE)
    return bool(report.market_date == market_date and report.passed)


def publish_if_needed(market_date: str, *, client=None, run_rebuild=None) -> dict:
    from backend.db.services.post_scrape_publication_trigger import is_valid_market_date

    if not is_valid_market_date(market_date):
        logger.error("%s malformed market_date=%r", TAG, market_date)
        return {"market_date": market_date, "status": STATUS_INVALID_MARKET_DATE}

    if client is None:
        from backend.db.clients.supabase_client import supabase as client  # type: ignore

    if not _batch_complete(client, market_date):
        logger.info("%s batch not complete for market_date=%s; no-op", TAG, market_date)
        return {"market_date": market_date, "status": STATUS_NOOP_NOT_COMPLETE}

    if _already_current(client, market_date):
        logger.info("%s already current for market_date=%s; no-op", TAG, market_date)
        return {"market_date": market_date, "status": STATUS_NOOP_ALREADY_CURRENT}

    runner = run_rebuild or _run_rebuild_script
    exit_code = runner(market_date)
    if exit_code == 0:
        logger.info("%s publication complete for market_date=%s", TAG, market_date)
        return {"market_date": market_date, "status": STATUS_PUBLISHED, "exit_code": exit_code}

    logger.error(
        "%s publication FAILED market_date=%s exit_code=%s", TAG, market_date, exit_code
    )
    return {"market_date": market_date, "status": STATUS_PUBLISH_FAILED, "exit_code": exit_code}


def _run_rebuild_script(market_date: str) -> int:
    args = [str(REBUILD_SCRIPT), market_date]
    logger.info("%s command: %s", TAG, " ".join(args))
    result = subprocess.run(args, cwd=str(_PROJECT_ROOT))
    return int(result.returncode)


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument(
        "--market-date",
        default=None,
        help="Explicit America/Phoenix market date (YYYY-MM-DD). Default: today's Phoenix date.",
    )
    return parser


def main(argv: Optional[list] = None) -> int:
    args = build_parser().parse_args(argv)
    market_date = _resolve_market_date(args.market_date)
    result = publish_if_needed(market_date)
    status = result.get("status")
    if status in (STATUS_INVALID_MARKET_DATE, STATUS_PUBLISH_FAILED):
        return 1
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
