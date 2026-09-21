"""Bounded watchdog for the post-scrape publication process.

This is deliberately narrower than the market freshness watchdog:
- it acts only after a scrape batch is authoritatively complete;
- it distinguishes an active publisher from a missing publisher;
- it relaunches only when NO publisher owns the canonical flock;
- it never kills a process or bypasses the publication gate;
- a held lock with no log progress is alert-only until an explicit
  stall-recovery runbook is separately approved.
"""

from __future__ import annotations

import argparse
import json
import logging
import os
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Callable, Dict, Optional

from backend.alerts.scrape_alerts import queue_alert
from backend.db.clients.supabase_client import supabase
from backend.db.services.post_scrape_publication_trigger import (
    PUBLICATION_LOCK_PATH,
    STATUS_CURRENCY_CHECK_FAILED,
    STATUS_INVALID_MARKET_DATE,
    STATUS_LAUNCH_FAILED,
    STATUS_LAUNCH_REQUESTED,
    STATUS_SKIPPED_ALREADY_CURRENT,
    STATUS_SKIPPED_ALREADY_RUNNING,
    trigger_post_scrape_publication_if_needed,
)
from backend.scripts.publish_post_scrape_if_needed import _batch_gate_decision
from backend.db.services.price_storage_v2_projection_gate import (
    REASON_AUTHORITY_UNAVAILABLE as PRICE_PROJECTION_AUTHORITY_UNAVAILABLE,
    advance_price_projection_once,
    evaluate_price_projection_gate,
)

logger = logging.getLogger(__name__)

TAG = "[publication-liveness-watchdog]"
REPO_ROOT = Path(__file__).resolve().parents[2]
PUBLICATION_LOG_PATH = REPO_ROOT / "publication.log"
DEFAULT_STALL_SECONDS = 20 * 60


def _env_positive_int(name: str, default: int) -> int:
    raw = str(os.getenv(name, str(default))).strip()
    try:
        value = int(raw)
    except (TypeError, ValueError):
        return default
    return value if value > 0 else default


def _latest_complete_batch(client: Any) -> Optional[Dict[str, Any]]:
    rows = list(
        client.table("pokemon_scrape_batches")
        .select("id,market_date,status,promoted_at,updated_at,expected_set_count,missing_set_count")
        .eq("status", "complete")
        .order("market_date", desc=True)
        .limit(1)
        .execute().data or []
    )
    return dict(rows[0]) if rows else None


def _lock_is_held(lock_path: str) -> bool:
    """Best-effort POSIX flock probe; false means the canonical wrapper may launch."""
    try:
        import fcntl
    except ImportError:
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


def _log_age_seconds(log_path: Path, now: datetime) -> Optional[float]:
    try:
        stat = log_path.stat()
    except OSError:
        return None
    modified = datetime.fromtimestamp(stat.st_mtime, tz=timezone.utc)
    return max(0.0, (now.astimezone(timezone.utc) - modified).total_seconds())


def evaluate_locked_publication(
    *,
    log_age_seconds: Optional[float],
    stall_seconds: int,
) -> Dict[str, Any]:
    """Pure classification for a lock-held publication process."""
    if log_age_seconds is None:
        return {
            "healthy": False,
            "status": "stalled",
            "failure_code": "publication_log_missing_while_locked",
            "log_age_seconds": None,
        }
    if log_age_seconds > stall_seconds:
        return {
            "healthy": False,
            "status": "stalled",
            "failure_code": "publication_progress_stalled",
            "log_age_seconds": log_age_seconds,
        }
    return {
        "healthy": True,
        "status": "in_progress",
        "failure_code": None,
        "log_age_seconds": log_age_seconds,
    }


def _queue_stall_alert(
    *, market_date: str, batch_id: Any, classification: Dict[str, Any], stall_seconds: int
) -> None:
    age = classification.get("log_age_seconds")
    age_text = "missing" if age is None else f"{int(age)}s"
    queue_alert(
        "post_scrape_publication_stalled",
        title=f"POST-SCRAPE PUBLICATION STALLED — {market_date}",
        message=(
            f"Publication lock is held for market_date={market_date}, but publication.log "
            f"has not made acceptable progress (age={age_text}, threshold={stall_seconds}s). "
            "No process was killed automatically. Investigate the lock owner and publisher state."
        ),
        severity="critical",
        dedupe_key=f"post_scrape_publication_stalled:{market_date}:{classification.get('failure_code')}",
        payload={
            "market_date": market_date,
            "batch_id": batch_id,
            "error_category": "post_scrape_publication_stalled",
            "failure_code": classification.get("failure_code"),
            "log_age_seconds": age,
            "stall_seconds": stall_seconds,
            "lock_path": PUBLICATION_LOCK_PATH,
            "log_path": str(PUBLICATION_LOG_PATH),
        },
    )


def run_watchdog(
    *,
    client: Any = supabase,
    now: Optional[datetime] = None,
    stall_seconds: Optional[int] = None,
    queue_failures: bool = True,
    lock_checker: Callable[[str], bool] = _lock_is_held,
    trigger: Callable[..., Dict[str, Any]] = trigger_post_scrape_publication_if_needed,
    latest_batch_loader: Callable[[Any], Optional[Dict[str, Any]]] = _latest_complete_batch,
    log_age_loader: Callable[[Path, datetime], Optional[float]] = _log_age_seconds,
    projection_checker: Callable[[Any, str], Any] = evaluate_price_projection_gate,
    projection_advancer: Callable[..., Dict[str, Any]] = advance_price_projection_once,
) -> Dict[str, Any]:
    resolved_now = now or datetime.now(timezone.utc)
    threshold = stall_seconds or _env_positive_int(
        "POST_SCRAPE_PUBLICATION_STALL_SECONDS", DEFAULT_STALL_SECONDS
    )

    try:
        batch = latest_batch_loader(client)
    except Exception as exc:
        failure = {
            "healthy": False,
            "status": "authority_unavailable",
            "failure_code": "latest_complete_batch_unavailable",
            "error": f"{type(exc).__name__}: {exc}",
        }
        if queue_failures:
            queue_alert(
                "post_scrape_publication_watchdog_failed",
                title="POST-SCRAPE PUBLICATION WATCHDOG AUTHORITY FAILED",
                message=failure["error"],
                severity="critical",
                dedupe_key=f"post_scrape_publication_watchdog_failed:{resolved_now.date().isoformat()}",
                payload=failure,
            )
        return failure

    if not batch:
        return {"healthy": True, "status": "no_complete_batch", "market_date": None}

    market_date = str(batch.get("market_date") or "")[:10]
    gate = _batch_gate_decision(client, market_date)
    if not gate.allowed:
        failure = {
            "healthy": False,
            "status": "gate_blocked",
            "market_date": market_date,
            "batch_id": batch.get("id"),
            "failure_code": str(gate.reason_code),
        }
        if queue_failures:
            queue_alert(
                "post_scrape_publication_gate_blocked",
                title=f"POST-SCRAPE PUBLICATION GATE BLOCKED — {market_date}",
                message=f"Latest complete batch exists but publication gate returned {gate.reason_code}.",
                severity="critical",
                dedupe_key=f"post_scrape_publication_gate_blocked:{market_date}:{gate.reason_code}",
                payload=failure,
            )
        return failure

    projection = projection_checker(client, market_date)
    if not getattr(projection, "ready", False):
        projection_payload = (
            projection.to_dict() if hasattr(projection, "to_dict") else {}
        )
        if getattr(projection, "reason_code", "") == PRICE_PROJECTION_AUTHORITY_UNAVAILABLE:
            failure = {
                "healthy": False,
                "status": "price_projection_authority_unavailable",
                "market_date": market_date,
                "batch_id": batch.get("id"),
                "price_projection": projection_payload,
            }
            if queue_failures:
                queue_alert(
                    "price_projection_watchdog_failed",
                    title=f"PRICE PROJECTION WATCHDOG FAILED — {market_date}",
                    message="Price Storage V2 readiness authority is unavailable; publication remains blocked.",
                    severity="critical",
                    dedupe_key=f"price_projection_watchdog_failed:{market_date}",
                    payload=failure,
                )
            return failure

        if projection_payload.get("terminal_failed_set_count", 0):
            failure = {
                "healthy": False,
                "status": "price_projection_terminal_failure",
                "market_date": market_date,
                "batch_id": batch.get("id"),
                "price_projection": projection_payload,
            }
            if queue_failures:
                queue_alert(
                    "price_projection_terminal_failure",
                    title=f"PRICE PROJECTION TERMINAL FAILURE — {market_date}",
                    message="One or more Price Storage V2 queue rows exhausted their retry budget.",
                    severity="critical",
                    dedupe_key=f"price_projection_terminal_failure:{market_date}",
                    payload=failure,
                )
            return failure

        try:
            advance = dict(
                projection_advancer(client, market_date, process_limit=20) or {}
            )
        except Exception as exc:
            failure = {
                "healthy": False,
                "status": "price_projection_advance_failed",
                "market_date": market_date,
                "batch_id": batch.get("id"),
                "error": f"{type(exc).__name__}: {exc}",
                "price_projection": projection_payload,
            }
            if queue_failures:
                queue_alert(
                    "price_projection_advance_failed",
                    title=f"PRICE PROJECTION ADVANCE FAILED — {market_date}",
                    message=failure["error"],
                    severity="critical",
                    dedupe_key=f"price_projection_advance_failed:{market_date}",
                    payload=failure,
                )
            return failure

        after = dict(advance.get("after") or {})
        if not after.get("ready"):
            if after.get("terminal_failed_set_count", 0):
                return {
                    "healthy": False,
                    "status": "price_projection_terminal_failure",
                    "market_date": market_date,
                    "batch_id": batch.get("id"),
                    "advance": advance,
                }
            return {
                "healthy": True,
                "status": "price_projection_advancing",
                "market_date": market_date,
                "batch_id": batch.get("id"),
                "advance": advance,
            }

    lock_held = bool(lock_checker(PUBLICATION_LOCK_PATH))
    if lock_held:
        age = log_age_loader(PUBLICATION_LOG_PATH, resolved_now)
        classification = evaluate_locked_publication(
            log_age_seconds=age, stall_seconds=threshold
        )
        result = {
            **classification,
            "market_date": market_date,
            "batch_id": batch.get("id"),
            "lock_held": True,
            "stall_seconds": threshold,
        }
        if not classification["healthy"] and queue_failures:
            _queue_stall_alert(
                market_date=market_date,
                batch_id=batch.get("id"),
                classification=classification,
                stall_seconds=threshold,
            )
        return result

    # No publisher owns the lock. Use the existing detached/idempotent trigger.
    trigger_result = dict(trigger(market_date) or {})
    status = str(trigger_result.get("status") or "")
    healthy_statuses = {
        STATUS_LAUNCH_REQUESTED,
        STATUS_SKIPPED_ALREADY_CURRENT,
        STATUS_SKIPPED_ALREADY_RUNNING,
    }
    healthy = status in healthy_statuses
    result = {
        "healthy": healthy,
        "status": "relaunch_requested" if status == STATUS_LAUNCH_REQUESTED else status,
        "market_date": market_date,
        "batch_id": batch.get("id"),
        "lock_held": False,
        "trigger": trigger_result,
    }
    if not healthy and queue_failures:
        queue_alert(
            "post_scrape_publication_relaunch_failed",
            title=f"POST-SCRAPE PUBLICATION RELAUNCH FAILED — {market_date}",
            message=f"Publication was stale with no lock owner, but trigger returned status={status}.",
            severity="critical",
            dedupe_key=f"post_scrape_publication_relaunch_failed:{market_date}:{status}",
            payload={**result, "error_category": "post_scrape_publication_relaunch_failed"},
        )
    return result


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--health", action="store_true", help="Read-only alert suppression; relaunch logic remains disabled.")
    args = parser.parse_args()
    if args.health:
        # Health mode must be strictly read-only, including no detached relaunch.
        report = run_watchdog(
            queue_failures=False,
            trigger=lambda market_date: {"market_date": market_date, "status": "health_only_no_relaunch"},
        )
        if report.get("status") == "health_only_no_relaunch":
            report["healthy"] = False
    else:
        report = run_watchdog()
    print(json.dumps(report, indent=2, sort_keys=True, default=str))
    return 0 if report.get("healthy") else 1


if __name__ == "__main__":
    raise SystemExit(main())
