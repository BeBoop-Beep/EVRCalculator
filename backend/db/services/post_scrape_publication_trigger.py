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
from enum import Enum
from pathlib import Path
from typing import Any, Callable, Dict, Optional

logger = logging.getLogger(__name__)


class PublicationCurrencyStatus(Enum):
    """Three-state result of a publication-currency check.

    UNKNOWN is distinct from STALE: it means the currency check itself could
    not run (e.g. audit-infrastructure/DB outage), not that the audit ran and
    found stale data. Callers must never launch publication on UNKNOWN.
    """

    CURRENT = "current"
    STALE = "stale"
    UNKNOWN = "unknown"

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
STATUS_CURRENCY_CHECK_FAILED = "currency_check_failed"
STATUS_SKIPPED_ALREADY_RUNNING = "skipped_already_running"


def is_valid_market_date(value: Any) -> bool:
    return isinstance(value, str) and bool(_MARKET_DATE_RE.match(value))


def _default_publication_current(market_date: str) -> PublicationCurrencyStatus:
    """Durable idempotence check: is post-scrape publication already current?

    Reuses the existing post-scrape audit authority for the EXACT market date
    (bypassing its own "latest promoted batch" resolution by passing the date
    explicitly) rather than inventing new schema.

    Returns UNKNOWN (never STALE) when the audit itself could not run — an
    audit-infrastructure/DB outage is not evidence that publication is stale.
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
        if report.market_date == market_date and report.passed:
            return PublicationCurrencyStatus.CURRENT
        return PublicationCurrencyStatus.STALE
    except Exception:
        logger.exception(
            "%s publication-currency check failed for market_date=%s; currency is UNKNOWN, not stale",
            TRIGGER_TAG, market_date,
        )
        return PublicationCurrencyStatus.UNKNOWN


def _default_lock_is_held(lock_path: str) -> bool:
    """Best-effort, non-blocking check: is the publication wrapper's own flock
    (``rebuild_snapshots_after_scrape.sh``'s ``LOCK_PATH``) currently held?

    This is a PRE-CHECK only — the shell wrapper's own ``flock -n`` remains the
    authoritative, race-free lock (belt-and-suspenders per requirement K). Its
    purpose is purely to avoid spawning a detached subprocess (and the log-file
    I/O, PID, etc. that comes with it) on every idle-minute dispatcher tick
    while a publication run is already in flight — not to replace the shell
    lock as the correctness guarantee.

    Fails OPEN (returns False, "not held") on any platform or I/O condition
    where the check itself cannot be performed (e.g. Windows dev boxes, a
    missing ``fcntl`` module, or a permissions error) so a broken pre-check can
    never itself block a legitimate publication launch — only the shell
    wrapper's own lock is allowed to do that.
    """
    try:
        import fcntl  # POSIX only; the VM target is Linux.
    except ImportError:  # pragma: no cover - exercised on Windows dev boxes
        return False
    try:
        with open(lock_path, "a+") as handle:
            try:
                fcntl.flock(handle, fcntl.LOCK_EX | fcntl.LOCK_NB)
            except BlockingIOError:
                return True
            else:
                fcntl.flock(handle, fcntl.LOCK_UN)
                return False
    except OSError:
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


def _default_queue_currency_unknown_alert(*, market_date: str, **_ignored: Any) -> None:
    """Deduplicated alert for an UNKNOWN publication-currency result.

    Reuses the existing alert-queue mechanism (``backend.alerts.scrape_alerts.
    queue_alert``), the same one already used by ``_queue_launch_failure_alert``
    above, keyed by exact market_date via ``dedupe_key`` so repeated every-minute
    dispatcher calls during an outage do not spam duplicate alerts.
    """
    try:
        from backend.alerts.scrape_alerts import queue_alert

        queue_alert(
            "publication_currency_check_failed",
            title=f"POST-SCRAPE PUBLICATION CURRENCY CHECK FAILED — {market_date}",
            message=(
                f"Publication-currency check failed for market_date={market_date}; "
                f"audit infrastructure may be unavailable. Publication is NOT being "
                f"launched automatically because currency is UNKNOWN, not confirmed "
                f"stale. Investigate the audit path; the 6:00 AM fallback will retry."
            ),
            severity="error",
            dedupe_key=f"publication_currency_check_failed:{market_date}",
            payload={"market_date": market_date},
        )
    except Exception:  # pragma: no cover - alerting must never break the caller
        logger.exception("%s failed to queue currency-check-failed alert", TRIGGER_TAG)


def trigger_post_scrape_publication_if_needed(
    market_date: Optional[str],
    *,
    publication_current: Optional[Callable[[str], PublicationCurrencyStatus]] = None,
    popen: Optional[Callable[..., subprocess.Popen]] = None,
    rebuild_script: Optional[Path] = None,
    log_path: Optional[Path] = None,
    queue_alert: Optional[Callable[..., None]] = None,
    lock_check: Optional[Callable[[str], bool]] = None,
    lock_path: Optional[str] = None,
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

    # L: an already-running publication must not receive a fresh detached launch
    # request every idle minute. This is a pre-check ONLY — the shell wrapper's
    # own flock (rebuild_snapshots_after_scrape.sh) remains the authoritative
    # lock (requirement K); this simply avoids spawning the subprocess at all
    # when we can already tell it would just no-op on that lock. It also bounds
    # M (a transient Supabase 5xx making publication_current look stale on every
    # call): however many idle-minute ticks land while a run is in flight, at
    # most one publisher process is ever alive because every later tick sees
    # the held lock and skips.
    check_lock_held = lock_check or _default_lock_is_held
    resolved_lock_path = lock_path or PUBLICATION_LOCK_PATH
    try:
        already_running = bool(check_lock_held(resolved_lock_path))
    except Exception:  # pragma: no cover - defensive; check must never raise
        logger.exception(
            "%s publication lock check raised for market_date=%s; assuming not running",
            TRIGGER_TAG, market_date,
        )
        already_running = False
    if already_running:
        logger.info(
            "%s publication already running (lock_path=%s held); skipping launch for market_date=%s",
            TRIGGER_TAG, resolved_lock_path, market_date,
        )
        result["status"] = STATUS_SKIPPED_ALREADY_RUNNING
        return result

    check_current = publication_current or _default_publication_current
    alert_queuer = queue_alert or _default_queue_currency_unknown_alert
    try:
        currency_status = check_current(market_date)
    except Exception:  # defensive; check_current should not raise, but if it does
        logger.exception(
            "%s publication_current callable raised for market_date=%s; currency is UNKNOWN",
            TRIGGER_TAG, market_date,
        )
        currency_status = PublicationCurrencyStatus.UNKNOWN

    if currency_status is PublicationCurrencyStatus.CURRENT:
        logger.info(
            "%s already complete for market_date=%s; skipping launch",
            TRIGGER_TAG, market_date,
        )
        result["status"] = STATUS_SKIPPED_ALREADY_CURRENT
        return result

    if currency_status is PublicationCurrencyStatus.UNKNOWN:
        logger.error(
            "%s publication currency UNKNOWN for market_date=%s; NOT launching, alerting instead",
            TRIGGER_TAG, market_date,
        )
        try:
            alert_queuer(alert_type="publication_currency_check_failed", market_date=market_date)
        except Exception:  # pragma: no cover - alerting must never break the caller
            logger.exception("%s queue_alert callable raised", TRIGGER_TAG)
        result["status"] = STATUS_CURRENCY_CHECK_FAILED
        return result

    # currency_status is STALE -> proceed to launch (existing launch code below, unchanged)
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
