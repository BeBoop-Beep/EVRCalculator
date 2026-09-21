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
import time
from pathlib import Path
from typing import Optional

_PROJECT_ROOT = Path(__file__).resolve().parents[2]
if str(_PROJECT_ROOT) not in sys.path:
    sys.path.insert(0, str(_PROJECT_ROOT))

logging.basicConfig(level=logging.INFO, format="%(message)s")
logger = logging.getLogger(__name__)

TAG = "[publish-if-needed]"

REBUILD_SCRIPT = _PROJECT_ROOT / "backend" / "scripts" / "rebuild_snapshots_after_scrape.sh"
LOCK_HELD_EXIT_CODE = 4

STATUS_NOOP_NOT_COMPLETE = "noop_batch_not_complete"
STATUS_NOOP_ALREADY_CURRENT = "noop_already_current"
STATUS_NOOP_ALREADY_RUNNING = "noop_already_running"
STATUS_NOOP_CURRENCY_UNKNOWN = "noop_currency_unknown"
STATUS_GATE_AUTHORITY_UNAVAILABLE = "gate_authority_unavailable"
STATUS_GATE_INVALID_CONTRACT = "gate_invalid_contract"
STATUS_PUBLISHED = "published"
STATUS_PUBLISH_FAILED = "publish_failed"
STATUS_INVALID_MARKET_DATE = "invalid_market_date"

# Statuses that must cause the CLI to exit nonzero so ops/alerting notices.
_NONZERO_EXIT_STATUSES = (
    STATUS_INVALID_MARKET_DATE,
    STATUS_PUBLISH_FAILED,
    STATUS_NOOP_CURRENCY_UNKNOWN,
    STATUS_GATE_AUTHORITY_UNAVAILABLE,
    STATUS_GATE_INVALID_CONTRACT,
)


def _resolve_market_date(explicit: Optional[str]) -> str:
    if explicit:
        return explicit
    from backend.scripts.run_pokemon_set_scrape import _market_date_iso

    return _market_date_iso()


def _batch_gate_decision(
    client,
    market_date: str,
    *,
    evaluator=None,
    client_factory=None,
    sleep_fn=time.sleep,
    max_attempts: int = 3,
):
    """Return the structured publication-gate decision with transient retries.

    ``evaluate_publication_gate`` intentionally catches authority read errors and
    returns ``blocked_authority_unavailable`` rather than raising. That is the
    correct fail-closed behavior for publishers, but a fallback scheduler must
    not collapse that classification into the same harmless no-op used for a
    genuinely incomplete batch. Retry only that transient/unknown authority
    class with a fresh service-role client, then return the final structured
    decision so the caller can exit nonzero if the authority remains unknown.
    """
    from backend.db.services.publication_gate import (
        REASON_BLOCKED_AUTHORITY_UNAVAILABLE,
        evaluate_publication_gate,
    )

    check = evaluator or evaluate_publication_gate
    factory = client_factory
    if factory is None:
        from backend.db.clients.supabase_client import create_service_role_client
        factory = create_service_role_client

    current_client = client
    attempts = max(1, int(max_attempts or 1))
    for attempt in range(1, attempts + 1):
        decision = check(current_client, market_date=market_date)
        logger.info(
            "%s gate check market_date=%s allowed=%s reason_code=%s attempt=%s/%s",
            TAG, market_date, decision.allowed, decision.reason_code, attempt, attempts,
        )
        if decision.reason_code != REASON_BLOCKED_AUTHORITY_UNAVAILABLE:
            return decision
        if attempt >= attempts:
            return decision
        delay = min(5.0 * attempt, 10.0)
        logger.warning(
            "%s batch authority unavailable for market_date=%s; retrying in %.1fs",
            TAG, market_date, delay,
        )
        sleep_fn(delay)
        current_client = factory()

    return decision


def _already_current(client, market_date: str) -> "PublicationCurrencyStatus":
    from backend.db.services.post_scrape_publication_trigger import PublicationCurrencyStatus
    from backend.scripts.audit_pokemon_market_publication import (
        PHASE_POST_SCRAPE,
        run_market_publication_audit,
    )

    try:
        report = run_market_publication_audit(client, market_date=market_date, phase=PHASE_POST_SCRAPE)
    except Exception:
        logger.exception(
            "%s currency audit failed for market_date=%s; treating as UNKNOWN", TAG, market_date
        )
        return PublicationCurrencyStatus.UNKNOWN
    if report.market_date == market_date and report.passed:
        return PublicationCurrencyStatus.CURRENT
    return PublicationCurrencyStatus.STALE


def publish_if_needed(market_date: str, *, client=None, run_rebuild=None) -> dict:
    from backend.db.services.post_scrape_publication_trigger import (
        PublicationCurrencyStatus,
        is_valid_market_date,
    )

    if not is_valid_market_date(market_date):
        logger.error("%s malformed market_date=%r", TAG, market_date)
        return {"market_date": market_date, "status": STATUS_INVALID_MARKET_DATE}

    if client is None:
        from backend.db.clients.supabase_client import supabase as client  # type: ignore

    from backend.db.services.publication_gate import (
        REASON_BLOCKED_AUTHORITY_UNAVAILABLE,
        REASON_BLOCKED_INCOMPLETE,
        REASON_BLOCKED_INVALID_BATCH_CONTRACT,
        REASON_BLOCKED_NO_BATCH,
    )

    gate = _batch_gate_decision(client, market_date)
    if not gate.allowed:
        if gate.reason_code in {REASON_BLOCKED_INCOMPLETE, REASON_BLOCKED_NO_BATCH}:
            logger.info(
                "%s batch not complete for market_date=%s reason_code=%s; no-op",
                TAG, market_date, gate.reason_code,
            )
            return {
                "market_date": market_date,
                "status": STATUS_NOOP_NOT_COMPLETE,
                "gate_reason_code": gate.reason_code,
            }
        if gate.reason_code == REASON_BLOCKED_AUTHORITY_UNAVAILABLE:
            logger.error(
                "%s batch authority unavailable for market_date=%s after retries; failing closed",
                TAG, market_date,
            )
            return {
                "market_date": market_date,
                "status": STATUS_GATE_AUTHORITY_UNAVAILABLE,
                "gate_reason_code": gate.reason_code,
            }
        if gate.reason_code == REASON_BLOCKED_INVALID_BATCH_CONTRACT:
            logger.error(
                "%s invalid batch contract for market_date=%s; refusing publication",
                TAG, market_date,
            )
            return {
                "market_date": market_date,
                "status": STATUS_GATE_INVALID_CONTRACT,
                "gate_reason_code": gate.reason_code,
            }
        logger.error(
            "%s publication gate blocked for market_date=%s reason_code=%s; treating as invalid contract",
            TAG, market_date, gate.reason_code,
        )
        return {
            "market_date": market_date,
            "status": STATUS_GATE_INVALID_CONTRACT,
            "gate_reason_code": gate.reason_code,
        }

    currency_status = _already_current(client, market_date)
    if currency_status is PublicationCurrencyStatus.CURRENT:
        logger.info("%s already current for market_date=%s; no-op", TAG, market_date)
        return {"market_date": market_date, "status": STATUS_NOOP_ALREADY_CURRENT}
    if currency_status is PublicationCurrencyStatus.UNKNOWN:
        logger.error(
            "%s currency UNKNOWN for market_date=%s; refusing to blindly rebuild", TAG, market_date
        )
        return {"market_date": market_date, "status": STATUS_NOOP_CURRENCY_UNKNOWN}

    runner = run_rebuild or _run_rebuild_script
    exit_code = runner(market_date)
    if exit_code == 0:
        logger.info("%s publication complete for market_date=%s", TAG, market_date)
        return {"market_date": market_date, "status": STATUS_PUBLISHED, "exit_code": exit_code}
    if exit_code == LOCK_HELD_EXIT_CODE:
        logger.info(
            "%s publication already running for market_date=%s; safe no-op", TAG, market_date
        )
        return {"market_date": market_date, "status": STATUS_NOOP_ALREADY_RUNNING, "exit_code": exit_code}

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


def _status_to_exit_code(status: str) -> int:
    return 1 if status in _NONZERO_EXIT_STATUSES else 0


def main(argv: Optional[list] = None) -> int:
    args = build_parser().parse_args(argv)
    market_date = _resolve_market_date(args.market_date)
    result = publish_if_needed(market_date)
    return _status_to_exit_code(result.get("status"))


if __name__ == "__main__":
    raise SystemExit(main())
