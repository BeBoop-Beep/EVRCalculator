"""Immediate post-scrape publication handoff (orchestration only).

When the every-minute scrape dispatcher's idle completion check
(:func:`backend.db.services.scrape_batch_service.run_batch_completion_and_repair`)
reports a batch as ``complete``, this module launches the EXISTING canonical
post-scrape publication wrapper (``backend/scripts/rebuild_snapshots_after_scrape.sh``)
for that EXACT market date instead of waiting for the fixed 6:00 AM cron.

Design constraints (see docs/superpowers ... post-scrape publication plan):

* The scrape dispatcher must never block for hours: the wrapper is launched
  DETACHED via ``subprocess.Popen`` and this call returns immediately.
* The batch-cohort gate (``run_batch_completion_and_repair`` /
  ``complete_scrape_batch_if_ready``) remains the ONLY completion authority.
  This module only reacts to an already-complete result; it never evaluates
  completeness itself and never bypasses the gate.
* Idempotence: a durable, already-existing publication authority — the
  post-scrape publication audit
  (``backend.scripts.audit_pokemon_market_publication.run_market_publication_audit``,
  phase ``post-scrape``) — is consulted for the EXACT market date before any
  launch. If every required surface is already current for that date, this is
  a no-op. No new schema/migration is introduced: the audit already reads the
  durable public snapshot tables that ARE the publication record.
* A failed launch never mutates the (already successful) scrape batch. It is
  logged loudly and best-effort alerted; the existing 6:00 AM fallback retries.
* Concurrent-publisher protection is enforced by the wrapper script itself via
  a non-blocking ``flock`` (see ``rebuild_snapshots_after_scrape.sh``), so a
  launch racing an already-running publisher is a safe no-op there.
"""

from __future__ import annotations

import logging
import os
import re
import subprocess
import sys
from pathlib import Path
from typing import Any, Callable, Dict, Optional

logger = logging.getLogger(__name__)

TRIGGER_TAG = "[post-scrape-trigger]"

_MARKET_DATE_RE = re.compile(r"^\d{4}-\d{2}-\d{2}$")

_PROJECT_ROOT = Path(__file__).resolve().parents[3]
REBUILD_SCRIPT = _PROJECT_ROOT / "backend" / "scripts" / "rebuild_snapshots_after_scrape.sh"
CANONICAL_PUBLICATION_LOG = _PROJECT_ROOT / "publication.log"

# Kept in sync with rebuild_snapshots_after_scrape.sh's own LOCK_PATH constant.
# Documented for operators; the actual lock is acquired inside the wrapper.
PUBLICATION_LOCK_PATH = "/tmp/pokemon-post-scrape-publication.lock"

STATUS_SKIPPED_ALREADY_CURRENT = "skipped_already_current"
STATUS_LAUNCH_REQUESTED = "launch_requested"
STATUS_LAUNCH_FAILED = "launch_failed"
STATUS_INVALID_MARKET_DATE = "invalid_market_date"
STATUS_NOT_COMPLETE = "skipped_batch_not_complete"


def is_valid_market_date(value: Any) -> bool:
    return isinstance(value, str) and bool(_MARKET_DATE_RE.match(value))


def _default_publication_current(market_date: str) -> bool:
    """Durable idempotence check: is post-scrape publication already current?

    Reuses the existing post-scrape audit authority for the EXACT market date
    (bypassing its own "latest promoted batch" resolution by passing the date
    explicitly) rather than inventing new schema.
    """
    try:
        from backend.db.clients.supabase_client import supabase
        from backend.scripts.audit_pokemon_market_publication import (
            PHASE_POST_SCRAPE,
            run_market_publication_audit,
        )

        report = run_market_publication_audit(
            supabase, market_date=market_date, phase=PHASE_POST_SCRAPE
        )
        return bool(report.market_date == market_date and report.passed)
    except Exception:  # pragma: no cover - fail-open to "not current" so we retry
        logger.exception(
            "%s publication-currency check failed for market_date=%s; treating as stale",
            TRIGGER_TAG, market_date,
        )
        return False


def _default_popen(args: list, *, cwd: str, log_path: Path) -> subprocess.Popen:
    log_file = open(log_path, "a", encoding="utf-8")
    kwargs: Dict[str, Any] = {
        "cwd": cwd,
        "stdout": log_file,
        "stderr": log_file,
        "stdin": subprocess.DEVNULL,
        "close_fds": True,
    }
    if sys.platform != "win32":
        kwargs["start_new_session"] = True
    else:  # pragma: no cover - VM target is Linux; kept for local/dev safety
        kwargs["creationflags"] = getattr(subprocess, "DETACHED_PROCESS", 0) | getattr(
            subprocess, "CREATE_NEW_PROCESS_GROUP", 0
        )
    return subprocess.Popen(args, **kwargs)


def _queue_launch_failure_alert(market_date: str, error: str) -> None:
    try:
        from backend.alerts.scrape_alerts import queue_alert

        queue_alert(
            "post_scrape_publication_launch_failed",
            title=f"POST-SCRAPE PUBLICATION LAUNCH FAILED — {market_date}",
            message=(
                f"Immediate post-scrape publication launch failed for market_date="
                f"{market_date}. The 6:00 AM fallback will retry. error={error[:500]}"
            ),
            severity="error",
            dedupe_key=f"post_scrape_publication_launch_failed:{market_date}",
            payload={"market_date": market_date, "error": error[:2000]},
        )
    except Exception:  # pragma: no cover - alerting must never break the caller
        logger.exception("%s failed to queue launch-failure alert", TRIGGER_TAG)


def trigger_post_scrape_publication_if_needed(
    market_date: Optional[str],
    *,
    publication_current: Optional[Callable[[str], bool]] = None,
    popen: Optional[Callable[..., subprocess.Popen]] = None,
    rebuild_script: Optional[Path] = None,
    log_path: Optional[Path] = None,
) -> Dict[str, Any]:
    """Launch the canonical post-scrape publication wrapper if it is needed.

    Caller contract: only call this AFTER the authoritative batch completion
    check (``run_batch_completion_and_repair``) reports ``status == "complete"``
    for ``market_date``. This function does not itself evaluate scrape-batch
    completeness — the batch service remains the only completion authority.

    Always best-effort: exceptions are caught, logged, and reported in the
    returned dict rather than raised, so a launch failure can never fail the
    scrape dispatcher or mutate the (already successful) scrape batch.
    """
    result: Dict[str, Any] = {"market_date": market_date, "status": None}

    if not is_valid_market_date(market_date):
        logger.error(
            "%s refusing to trigger publication for invalid market_date=%r",
            TRIGGER_TAG, market_date,
        )
        result["status"] = STATUS_INVALID_MARKET_DATE
        return result

    market_date = str(market_date)
    logger.info("%s batch complete market_date=%s", TRIGGER_TAG, market_date)

    check_current = publication_current or _default_publication_current
    try:
        already_current = bool(check_current(market_date))
    except Exception:  # pragma: no cover - defensive; check_current should not raise
        logger.exception(
            "%s publication-currency check raised for market_date=%s; treating as stale",
            TRIGGER_TAG, market_date,
        )
        already_current = False

    if already_current:
        logger.info(
            "%s already complete for market_date=%s; skipping launch",
            TRIGGER_TAG, market_date,
        )
        result["status"] = STATUS_SKIPPED_ALREADY_CURRENT
        return result

    script_path = Path(rebuild_script) if rebuild_script is not None else REBUILD_SCRIPT
    launch_log_path = Path(log_path) if log_path is not None else CANONICAL_PUBLICATION_LOG
    launcher = popen or _default_popen

    args = [str(script_path), market_date]
    logger.info(
        "%s publication launch requested market_date=%s command=%s",
        TRIGGER_TAG, market_date, " ".join(args),
    )
    try:
        process = launcher(args, cwd=str(_PROJECT_ROOT), log_path=launch_log_path)
        result["status"] = STATUS_LAUNCH_REQUESTED
        result["pid"] = getattr(process, "pid", None)
        return result
    except Exception as exc:
        error_message = f"{type(exc).__name__}: {exc}"
        logger.error(
            "%s launch failure market_date=%s error=%s",
            TRIGGER_TAG, market_date, error_message,
        )
        _queue_launch_failure_alert(market_date, error_message)
        result["status"] = STATUS_LAUNCH_FAILED
        result["error"] = error_message
        return result
