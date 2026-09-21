"""Bounded watchdog for the post-scrape publication process.

This is deliberately narrower than the market freshness watchdog:
- it acts only after a scrape batch is authoritatively complete;
- it distinguishes an active publisher from a missing publisher;
- it relaunches only when NO publisher owns the canonical flock;
- it never bypasses the publication gate;
- SIGTERM recovery is bounded to an exact canonical refresh child whose
  process identity is proven either stalled or superseded by a newer complete batch.
"""

from __future__ import annotations

import argparse
import json
import logging
import os
import re
import signal
import subprocess
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Callable, Dict, Optional

from backend.alerts.scrape_alerts import queue_alert
from backend.db.clients.supabase_client import create_service_role_client, supabase
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
from backend.scripts.snapshot_query_retry import run_snapshot_operation_with_retry
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
DEFAULT_STALL_RECOVERY_COOLDOWN_SECONDS = 60 * 60
STALL_RECOVERY_MARKER_DIR = Path("/tmp")
REFRESH_SCRIPT_TOKEN = "backend/scripts/refresh_stale_public_snapshots.py"


def _env_positive_int(name: str, default: int) -> int:
    raw = str(os.getenv(name, str(default))).strip()
    try:
        value = int(raw)
    except (TypeError, ValueError):
        return default
    return value if value > 0 else default


def _latest_complete_batch_once(client: Any) -> Optional[Dict[str, Any]]:
    rows = list(
        client.table("pokemon_scrape_batches")
        .select("id,market_date,status,promoted_at,updated_at,expected_set_count,missing_set_count")
        .eq("status", "complete")
        .order("market_date", desc=True)
        .limit(1)
        .execute().data or []
    )
    return dict(rows[0]) if rows else None


def _latest_complete_batch(
    client: Any,
    *,
    client_factory: Callable[[], Any] = create_service_role_client,
    sleep: Optional[Callable[[float], None]] = None,
) -> Optional[Dict[str, Any]]:
    """Load the newest complete batch with bounded fresh-client transient retries."""
    kwargs = {
        "operation_name": "post-scrape-publication-watchdog:latest-complete-batch",
        "max_attempts": 3,
        "client_factory": client_factory,
    }
    if sleep is not None:
        kwargs["sleep"] = sleep
    return run_snapshot_operation_with_retry(
        lambda retry_client: _latest_complete_batch_once(retry_client),
        **kwargs,
    )

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


def _default_all_publication_processes() -> list[dict[str, Any]]:
    """Return canonical wrapper/refresh processes with their exact market date."""
    result = subprocess.run(
        ["ps", "-eo", "pid=,ppid=,etimes=,args="],
        capture_output=True,
        text=True,
        check=False,
    )
    if result.returncode != 0:
        raise RuntimeError(
            f"ps failed with exit code {result.returncode}: {result.stderr[:500]}"
        )

    wrapper_token = str(
        REPO_ROOT / "backend" / "scripts" / "rebuild_snapshots_after_scrape.sh"
    )
    date_pattern = re.compile(r"^\d{4}-\d{2}-\d{2}$")
    refresh_date_pattern = re.compile(
        r"(?:^|\s)--market-date(?:=|\s+)(\d{4}-\d{2}-\d{2})(?:\s|$)"
    )
    rows: list[dict[str, Any]] = []
    for raw in result.stdout.splitlines():
        parts = raw.strip().split(None, 3)
        if len(parts) != 4:
            continue
        pid_text, ppid_text, age_text, args = parts
        try:
            pid = int(pid_text)
            ppid = int(ppid_text)
            age_seconds = int(age_text)
        except ValueError:
            continue

        kind = None
        market_date = None
        tokens = args.split()
        if wrapper_token in tokens:
            index = tokens.index(wrapper_token)
            if index + 1 < len(tokens) and date_pattern.match(tokens[index + 1]):
                kind = "wrapper"
                market_date = tokens[index + 1]
        elif REFRESH_SCRIPT_TOKEN in args:
            match = refresh_date_pattern.search(args)
            if match:
                kind = "refresh"
                market_date = match.group(1)

        if kind and market_date:
            rows.append(
                {
                    "pid": pid,
                    "ppid": ppid,
                    "age_seconds": age_seconds,
                    "args": args,
                    "kind": kind,
                    "market_date": market_date,
                }
            )
    return rows


def _default_publication_processes(market_date: str) -> list[dict[str, Any]]:
    """Return exact canonical wrapper/refresh processes for one market date."""
    exact_date = str(market_date)
    return [
        row
        for row in _default_all_publication_processes()
        if str(row.get("market_date") or "") == exact_date
    ]


def _validate_active_publication_identity(
    processes: list[dict[str, Any]],
) -> Dict[str, Any]:
    """Resolve one exact wrapper -> refresh pair without an age requirement."""
    wrappers = [row for row in processes if row.get("kind") == "wrapper"]
    refreshers = [row for row in processes if row.get("kind") == "refresh"]
    if len(wrappers) != 1 or len(refreshers) != 1:
        return {
            "ok": False,
            "reason": "publication_process_identity_ambiguous",
            "wrapper_count": len(wrappers),
            "refresh_count": len(refreshers),
        }
    wrapper = wrappers[0]
    refresh = refreshers[0]
    wrapper_date = str(wrapper.get("market_date") or "")
    refresh_date = str(refresh.get("market_date") or "")
    if not wrapper_date or wrapper_date != refresh_date:
        return {
            "ok": False,
            "reason": "publication_process_market_date_mismatch",
            "wrapper_market_date": wrapper_date,
            "refresh_market_date": refresh_date,
        }
    if int(refresh.get("ppid") or -1) != int(wrapper.get("pid") or -2):
        return {
            "ok": False,
            "reason": "publication_process_parent_mismatch",
            "wrapper_pid": wrapper.get("pid"),
            "refresh_pid": refresh.get("pid"),
            "refresh_ppid": refresh.get("ppid"),
        }
    return {
        "ok": True,
        "reason": "exact_publication_process_identity",
        "wrapper_pid": int(wrapper["pid"]),
        "refresh_pid": int(refresh["pid"]),
        "market_date": wrapper_date,
        "wrapper_age_seconds": int(wrapper.get("age_seconds") or 0),
        "refresh_age_seconds": int(refresh.get("age_seconds") or 0),
    }


def _default_terminate_process(pid: int) -> None:
    if int(pid) <= 1:
        raise RuntimeError(f"refusing to signal unsafe pid={pid}")
    os.kill(int(pid), signal.SIGTERM)


def _stall_recovery_marker_path(market_date: str) -> Path:
    safe_date = str(market_date).replace("/", "_")
    return STALL_RECOVERY_MARKER_DIR / f"pokemon-post-scrape-stall-recovery-{safe_date}.marker"


def _default_recovery_cooldown_active(market_date: str, now: datetime, cooldown_seconds: int) -> bool:
    path = _stall_recovery_marker_path(market_date)
    try:
        modified = datetime.fromtimestamp(path.stat().st_mtime, tz=timezone.utc)
    except OSError:
        return False
    age = max(0.0, (now.astimezone(timezone.utc) - modified).total_seconds())
    return age < int(cooldown_seconds)


def _default_record_recovery_attempt(market_date: str, now: datetime) -> None:
    path = _stall_recovery_marker_path(market_date)
    path.write_text(now.astimezone(timezone.utc).isoformat() + "\n", encoding="utf-8")


def _validate_stalled_process_identity(
    processes: list[dict[str, Any]], *, market_date: str, stall_seconds: int
) -> Dict[str, Any]:
    wrappers = [row for row in processes if row.get("kind") == "wrapper"]
    refreshers = [row for row in processes if row.get("kind") == "refresh"]
    if len(wrappers) != 1 or len(refreshers) != 1:
        return {
            "ok": False,
            "reason": "publication_process_identity_ambiguous",
            "wrapper_count": len(wrappers),
            "refresh_count": len(refreshers),
        }
    wrapper = wrappers[0]
    refresh = refreshers[0]
    if int(refresh.get("ppid") or -1) != int(wrapper.get("pid") or -2):
        return {
            "ok": False,
            "reason": "publication_process_parent_mismatch",
            "wrapper_pid": wrapper.get("pid"),
            "refresh_pid": refresh.get("pid"),
            "refresh_ppid": refresh.get("ppid"),
        }
    if min(int(wrapper.get("age_seconds") or 0), int(refresh.get("age_seconds") or 0)) < int(stall_seconds):
        return {
            "ok": False,
            "reason": "publication_process_too_young_for_stall_recovery",
            "wrapper_age_seconds": wrapper.get("age_seconds"),
            "refresh_age_seconds": refresh.get("age_seconds"),
        }
    return {
        "ok": True,
        "reason": "exact_publication_process_identity",
        "wrapper_pid": int(wrapper["pid"]),
        "refresh_pid": int(refresh["pid"]),
        "market_date": str(market_date),
    }

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


def _queue_superseded_alert(
    *,
    latest_market_date: str,
    batch_id: Any,
    active_identity: Dict[str, Any],
    recovery_status: str,
) -> None:
    active_date = str(active_identity.get("market_date") or "unknown")
    queue_alert(
        "post_scrape_publication_superseded",
        title=(
            f"POST-SCRAPE PUBLICATION SUPERSEDED — {active_date} -> "
            f"{latest_market_date}"
        ),
        message=(
            f"Publication lock is owned by market_date={active_date}, while a newer "
            f"complete promoted batch exists for {latest_market_date}. "
            f"recovery_status={recovery_status}."
        ),
        severity="critical",
        dedupe_key=(
            f"post_scrape_publication_superseded:{active_date}:{latest_market_date}"
        ),
        payload={
            "market_date": latest_market_date,
            "batch_id": batch_id,
            "active_market_date": active_date,
            "failure_code": "publication_superseded_by_newer_batch",
            "recovery_status": recovery_status,
            "process_identity": active_identity,
            "lock_path": PUBLICATION_LOCK_PATH,
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
    projection_checker: Optional[Callable[[Any, str], Any]] = None,
    projection_advancer: Optional[Callable[..., Dict[str, Any]]] = None,
    recover_stalled: bool = False,
    recover_superseded: bool = False,
    process_inspector: Callable[[str], list[dict[str, Any]]] = _default_publication_processes,
    all_process_inspector: Callable[[], list[dict[str, Any]]] = _default_all_publication_processes,
    terminate_process: Callable[[int], None] = _default_terminate_process,
    cooldown_checker: Callable[[str, datetime, int], bool] = _default_recovery_cooldown_active,
    recovery_recorder: Callable[[str, datetime], None] = _default_record_recovery_attempt,
    recovery_cooldown_seconds: int = DEFAULT_STALL_RECOVERY_COOLDOWN_SECONDS,
) -> Dict[str, Any]:
    resolved_now = now or datetime.now(timezone.utc)
    threshold = stall_seconds or _env_positive_int(
        "POST_SCRAPE_PUBLICATION_STALL_SECONDS", DEFAULT_STALL_SECONDS
    )
    check_projection = projection_checker or evaluate_price_projection_gate
    advance_projection = projection_advancer or advance_price_projection_once

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

    # A newer promoted batch supersedes any older latest-snapshot publisher.
    # Check this BEFORE doing Price Storage projection work so an obsolete
    # publisher cannot both hold the global publication lock and compete with
    # the new day's projection for database capacity.
    lock_held_precheck = bool(lock_checker(PUBLICATION_LOCK_PATH))
    if lock_held_precheck:
        try:
            active_identity = _validate_active_publication_identity(
                all_process_inspector()
            )
        except Exception as exc:
            active_identity = {
                "ok": False,
                "reason": "publication_process_inspection_failed",
                "error": f"{type(exc).__name__}: {exc}",
            }

        active_date = (
            str(active_identity.get("market_date") or "")
            if active_identity.get("ok")
            else ""
        )
        if active_date and active_date < market_date:
            result = {
                "healthy": False,
                "status": "superseded_publication_active",
                "failure_code": "publication_superseded_by_newer_batch",
                "market_date": market_date,
                "active_market_date": active_date,
                "batch_id": batch.get("id"),
                "lock_held": True,
                "process_identity": active_identity,
                "recovery_attempted": False,
            }
            recovery_key = f"superseded-{active_date}-by-{market_date}"
            if recover_superseded:
                if cooldown_checker(
                    recovery_key,
                    resolved_now,
                    recovery_cooldown_seconds,
                ):
                    result.update(
                        {
                            "status": "supersession_recovery_cooldown",
                            "failure_code": "publication_supersession_recovery_cooldown",
                            "recovery_cooldown_seconds": recovery_cooldown_seconds,
                        }
                    )
                else:
                    refresh_pid = int(active_identity["refresh_pid"])
                    try:
                        recovery_recorder(recovery_key, resolved_now)
                        terminate_process(refresh_pid)
                    except Exception as exc:
                        result.update(
                            {
                                "status": "supersession_recovery_failed",
                                "failure_code": "publication_supersession_sigterm_failed",
                                "recovery_attempted": True,
                                "refresh_pid": refresh_pid,
                                "error": f"{type(exc).__name__}: {exc}",
                            }
                        )
                    else:
                        result.update(
                            {
                                "status": "supersession_sigterm_requested",
                                "failure_code": "publication_supersession_sigterm_requested",
                                "recovery_attempted": True,
                                "refresh_pid": refresh_pid,
                                "wrapper_pid": active_identity.get("wrapper_pid"),
                                "recovery_cooldown_seconds": recovery_cooldown_seconds,
                            }
                        )
            if queue_failures:
                _queue_superseded_alert(
                    latest_market_date=market_date,
                    batch_id=batch.get("id"),
                    active_identity=active_identity,
                    recovery_status=str(result.get("status") or ""),
                )
            return result

    projection = check_projection(client, market_date)
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
                advance_projection(client, market_date, process_limit=20) or {}
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
        if classification["healthy"]:
            return result

        if not recover_stalled:
            if queue_failures:
                _queue_stall_alert(
                    market_date=market_date,
                    batch_id=batch.get("id"),
                    classification=classification,
                    stall_seconds=threshold,
                )
            return result

        if cooldown_checker(market_date, resolved_now, recovery_cooldown_seconds):
            result.update({
                "status": "stall_recovery_cooldown",
                "failure_code": "publication_stall_recovery_cooldown",
                "recovery_attempted": False,
                "recovery_cooldown_seconds": recovery_cooldown_seconds,
            })
            if queue_failures:
                _queue_stall_alert(
                    market_date=market_date,
                    batch_id=batch.get("id"),
                    classification=result,
                    stall_seconds=threshold,
                )
            return result

        try:
            identity = _validate_stalled_process_identity(
                process_inspector(market_date),
                market_date=market_date,
                stall_seconds=threshold,
            )
        except Exception as exc:
            identity = {
                "ok": False,
                "reason": "publication_process_inspection_failed",
                "error": f"{type(exc).__name__}: {exc}",
            }

        if not identity.get("ok"):
            result.update({
                "status": "stall_recovery_blocked",
                "failure_code": str(identity.get("reason") or "publication_process_identity_invalid"),
                "recovery_attempted": False,
                "process_identity": identity,
            })
            if queue_failures:
                _queue_stall_alert(
                    market_date=market_date,
                    batch_id=batch.get("id"),
                    classification=result,
                    stall_seconds=threshold,
                )
            return result

        refresh_pid = int(identity["refresh_pid"])
        try:
            recovery_recorder(market_date, resolved_now)
            terminate_process(refresh_pid)
        except Exception as exc:
            result.update({
                "status": "stall_recovery_failed",
                "failure_code": "publication_stall_sigterm_failed",
                "recovery_attempted": True,
                "refresh_pid": refresh_pid,
                "error": f"{type(exc).__name__}: {exc}",
                "process_identity": identity,
            })
            if queue_failures:
                _queue_stall_alert(
                    market_date=market_date,
                    batch_id=batch.get("id"),
                    classification=result,
                    stall_seconds=threshold,
                )
            return result

        result.update({
            "status": "stall_sigterm_requested",
            "failure_code": "publication_stall_sigterm_requested",
            "recovery_attempted": True,
            "refresh_pid": refresh_pid,
            "wrapper_pid": identity.get("wrapper_pid"),
            "recovery_cooldown_seconds": recovery_cooldown_seconds,
            "process_identity": identity,
        })
        if queue_failures:
            _queue_stall_alert(
                market_date=market_date,
                batch_id=batch.get("id"),
                classification=result,
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
    parser.add_argument(
        "--recover-stalled",
        action="store_true",
        help=(
            "Enable one-shot SIGTERM recovery for an exact canonical refresh child "
            "after the progress-stall threshold. Never SIGKILLs or signals an "
            "ambiguous process identity."
        ),
    )
    parser.add_argument(
        "--recover-superseded",
        action="store_true",
        help=(
            "Enable one-shot SIGTERM recovery when an exact older publication "
            "process owns the lock after a newer complete promoted batch exists."
        ),
    )
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
        report = run_watchdog(\n            recover_stalled=bool(args.recover_stalled),\n            recover_superseded=bool(args.recover_superseded),\n        )
    print(json.dumps(report, indent=2, sort_keys=True, default=str))
    return 0 if report.get("healthy") else 1


if __name__ == "__main__":
    raise SystemExit(main())
