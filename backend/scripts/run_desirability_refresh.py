"""Unified desirability refresh orchestrator - the ONE scheduled entry point.

This is the only script the Windows scheduled task needs to call. It locates the
repository root itself and does not depend on the shell's working directory.

    python backend/scripts/run_desirability_refresh.py --dry-run
    python backend/scripts/run_desirability_refresh.py --commit
    python backend/scripts/run_desirability_refresh.py --commit --force-static
    python backend/scripts/run_desirability_refresh.py --resume <run_id>
    python backend/scripts/run_desirability_refresh.py --stage trends
    python backend/scripts/run_desirability_refresh.py --stage rebuild
    python backend/scripts/run_desirability_refresh.py --stage snapshot

DRY RUN IS THE DEFAULT. ``--commit`` is required to write anything.

STAGES
------
    preflight -> trends -> static -> composite -> links -> sets -> snapshot -> report

STATIC SOURCE CADENCE
---------------------
The favoritepokemon fan-popularity source is effectively static: it is a
community poll ranking that moves on the order of months. Re-scraping it three
times a week is pointless load with a real failure surface. It is refreshed only
when older than ``STATIC_MAX_AGE_DAYS`` or when ``--force-static`` is passed.

WHY THE PIPELINE WAS FAILING (see the rollout doc for the full table)
--------------------------------------------------------------------
  1. ``pytrends`` was declared in requirements.txt but NOT installed in
     backend/.venv, so every Trends run exited 'provider_unavailable'.
  2. The Pikachu anchor is so dominant that ~half the roster rounds to 0 on
     Trends' relative 0-100 scale. That is a measurement artifact, not low
     interest - see backend/desirability/trend_anchor_tiers.py.

SAFETY RULES
------------
  * No stage writes unless its quality gate passes. A partial pipeline must
    never replace good current data.
  * A failed source retrieval is NEVER recorded as a zero.
  * Historical tables are append-only; observed_on is kept separate from
    captured_at.
  * Exceptions are never silently swallowed; every failure lands in the manifest
    with its traceback and sets a structured exit code.
"""

from __future__ import annotations

import argparse
import json
import logging
import os
import random
import socket
import subprocess
import sys
import time
import traceback
import uuid
from dataclasses import dataclass, field
from datetime import datetime, timedelta, timezone
from pathlib import Path
from typing import Any, Callable, Dict, List, Optional, Sequence

# Repository-root discovery: never trust the caller's working directory. The
# scheduled task's "Start in" can be anything, and Task Scheduler has been known
# to launch with C:\Windows\System32 as CWD.
REPO_ROOT = Path(__file__).resolve().parents[2]
if str(REPO_ROOT) not in sys.path:
    sys.path.insert(0, str(REPO_ROOT))

from dotenv import load_dotenv  # noqa: E402

logger = logging.getLogger("desirability_refresh")

ORCHESTRATOR_VERSION = "desirability_refresh_v1"
LOG_DIR = REPO_ROOT / "logs" / "desirability-refresh"
LOCK_PATH = LOG_DIR / "refresh.lock"
CHECKPOINT_DIR = LOG_DIR / "checkpoints"

# Keep the log directory bounded; a thrice-weekly task otherwise grows forever.
LOG_RETENTION_RUNS = 60
LOCK_STALE_AFTER_SECONDS = 6 * 3600
STATIC_MAX_AGE_DAYS = 30

# Structured exit codes so Task Scheduler's "last run result" is meaningful.
EXIT_OK = 0
EXIT_PREFLIGHT_FAILED = 2
EXIT_LOCKED = 3
EXIT_SOURCE_QUALITY_GATE_FAILED = 4
EXIT_STAGE_FAILED = 5
EXIT_VALIDATION_GATE_FAILED = 6
EXIT_INTERRUPTED = 130

STAGE_ORDER: Sequence[str] = ("preflight", "trends", "static", "composite", "links", "sets", "snapshot")

# --stage groups
STAGE_GROUPS: Dict[str, Sequence[str]] = {
    "all": STAGE_ORDER,
    "trends": ("preflight", "trends"),
    "rebuild": ("preflight", "composite", "links", "sets"),
    "snapshot": ("preflight", "snapshot"),
    "static": ("preflight", "static"),
}

REQUIRED_ENV = ("SUPABASE_URL", "SUPABASE_SERVICE_ROLE_KEY")
REQUIRED_MODULES = ("pytrends", "pandas", "numpy", "supabase", "dotenv", "requests")
REQUIRED_TABLES = (
    "pokemon_reference",
    "pokemon_desirability_source_snapshots",
    "pokemon_desirability_scores",
    "pokemon_trend_source_snapshots",
    "pokemon_trend_scores",
    "pokemon_desirability_composite_scores",
    "pokemon_card_desirability_links",
    "pokemon_set_desirability_component_scores",
)

# Quality gates. A run that cannot meet these must not promote its results over
# the previous good data.
MIN_TREND_USABLE_RATIO = 0.90
MAX_TREND_FAILURE_RATIO = 0.10
MIN_COMPOSITE_COVERAGE = 0.95
MAX_RANK_CHURN_RATIO = 0.50


@dataclass
class StageResult:
    name: str
    status: str = "pending"          # pending | ok | skipped | failed
    started_at: Optional[str] = None
    ended_at: Optional[str] = None
    duration_seconds: Optional[float] = None
    detail: Dict[str, Any] = field(default_factory=dict)
    error: Optional[str] = None
    traceback: Optional[str] = None

    def to_dict(self) -> Dict[str, Any]:
        return {
            "stage": self.name,
            "status": self.status,
            "started_at": self.started_at,
            "ended_at": self.ended_at,
            "duration_seconds": self.duration_seconds,
            "detail": self.detail,
            "error": self.error,
            "traceback": self.traceback,
        }


class StageFailure(RuntimeError):
    """A stage failed in a way that must stop the pipeline. Never swallowed."""

    def __init__(self, message: str, *, exit_code: int = EXIT_STAGE_FAILED, detail: Any = None):
        super().__init__(message)
        self.exit_code = exit_code
        self.detail = detail


# ---------------------------------------------------------------------------
# Locking
# ---------------------------------------------------------------------------

class RunLock:
    """Refuse overlapping runs. A thrice-weekly task can still collide with a
    manual run, and two concurrent writers to the current-state tables would
    interleave unpredictably."""

    def __init__(self, path: Path, run_id: str):
        self.path = path
        self.run_id = run_id
        self.acquired = False

    def acquire(self) -> None:
        self.path.parent.mkdir(parents=True, exist_ok=True)
        if self.path.exists():
            try:
                held = json.loads(self.path.read_text(encoding="utf-8"))
            except (json.JSONDecodeError, OSError):
                held = {}
            started = held.get("started_at_epoch") or 0
            age = time.time() - float(started or 0)
            if age < LOCK_STALE_AFTER_SECONDS:
                raise StageFailure(
                    f"Another run holds the lock (run_id={held.get('run_id')}, "
                    f"pid={held.get('pid')}, age={age:.0f}s). Refusing to start.",
                    exit_code=EXIT_LOCKED,
                    detail=held,
                )
            logger.warning(
                "Breaking a stale lock from run_id=%s (age %.0fs > %ss).",
                held.get("run_id"), age, LOCK_STALE_AFTER_SECONDS,
            )
        self.path.write_text(
            json.dumps({
                "run_id": self.run_id,
                "pid": os.getpid(),
                "host": socket.gethostname(),
                "started_at": datetime.now(timezone.utc).isoformat(),
                "started_at_epoch": time.time(),
            }),
            encoding="utf-8",
        )
        self.acquired = True

    def release(self) -> None:
        if not self.acquired:
            return
        try:
            self.path.unlink(missing_ok=True)
        except OSError as error:
            logger.warning("Could not release lock: %s", error)

    def __enter__(self) -> "RunLock":
        self.acquire()
        return self

    def __exit__(self, *exc: Any) -> None:
        self.release()


# ---------------------------------------------------------------------------
# Retry
# ---------------------------------------------------------------------------

def with_retries(
    operation: Callable[[], Any],
    *,
    attempts: int = 3,
    base_delay: float = 5.0,
    max_delay: float = 120.0,
    label: str = "operation",
) -> Any:
    """Bounded retries with exponential backoff and jitter.

    Bounded on purpose: an unbounded retry against a rate-limited source turns a
    3-hour job into an infinite one and makes the next scheduled run collide
    with this one.
    """
    last: Optional[BaseException] = None
    for attempt in range(1, attempts + 1):
        try:
            return operation()
        except KeyboardInterrupt:
            raise
        except Exception as error:  # noqa: BLE001 - re-raised below, never swallowed
            last = error
            if attempt >= attempts:
                break
            delay = min(base_delay * (2 ** (attempt - 1)), max_delay)
            delay += random.uniform(0, delay * 0.25)  # jitter: avoid lockstep retries
            logger.warning(
                "%s failed (attempt %s/%s): %s. Retrying in %.1fs.",
                label, attempt, attempts, error, delay,
            )
            time.sleep(delay)
    raise StageFailure(f"{label} failed after {attempts} attempts: {last}") from last


# ---------------------------------------------------------------------------
# Subprocess stage runner
# ---------------------------------------------------------------------------

def run_script(
    script: str,
    args: Sequence[str],
    *,
    timeout: int,
    label: str,
) -> Dict[str, Any]:
    """Run a pipeline script with the CURRENT interpreter and repo root as CWD.

    Uses sys.executable so the scheduled task never needs venv activation.
    """
    command = [sys.executable, str(REPO_ROOT / "backend" / "scripts" / script), *args]
    logger.info("[%s] %s", label, " ".join(command[1:]))
    started = time.time()
    try:
        completed = subprocess.run(
            command,
            cwd=str(REPO_ROOT),
            capture_output=True,
            text=True,
            timeout=timeout,
            check=False,
        )
    except subprocess.TimeoutExpired as error:
        raise StageFailure(f"{label} timed out after {timeout}s") from error

    duration = time.time() - started
    if completed.returncode != 0:
        tail = (completed.stderr or completed.stdout or "")[-2000:]
        raise StageFailure(
            f"{label} exited {completed.returncode}. Output tail:\n{tail}",
            detail={"returncode": completed.returncode, "stderr_tail": tail},
        )
    payload: Optional[Dict[str, Any]] = None
    text = completed.stdout or ""
    start = text.find("{")
    if start >= 0:
        try:
            payload = json.loads(text[start:])
        except json.JSONDecodeError:
            payload = None
    return {
        "returncode": completed.returncode,
        "duration_seconds": round(duration, 2),
        "payload": payload,
        "stdout_tail": text[-1500:] if payload is None else None,
    }


# ---------------------------------------------------------------------------
# Checkpointing
# ---------------------------------------------------------------------------

def checkpoint_path(run_id: str) -> Path:
    return CHECKPOINT_DIR / f"{run_id}.json"


def save_checkpoint(run_id: str, completed: Sequence[str], detail: Dict[str, Any]) -> None:
    CHECKPOINT_DIR.mkdir(parents=True, exist_ok=True)
    checkpoint_path(run_id).write_text(
        json.dumps({"run_id": run_id, "completed_stages": list(completed),
                    "updated_at": datetime.now(timezone.utc).isoformat(),
                    "detail": detail}, indent=2, default=str),
        encoding="utf-8",
    )


def load_checkpoint(run_id: str) -> Dict[str, Any]:
    path = checkpoint_path(run_id)
    if not path.exists():
        raise StageFailure(f"No checkpoint for run_id={run_id} at {path}")
    return json.loads(path.read_text(encoding="utf-8"))


def prune_logs(keep: int = LOG_RETENTION_RUNS) -> int:
    """Bounded log retention. Returns the number of files removed."""
    if not LOG_DIR.exists():
        return 0
    manifests = sorted(LOG_DIR.glob("*.json"), key=lambda p: p.stat().st_mtime, reverse=True)
    removed = 0
    for stale in manifests[keep:]:
        for suffix in (".json", ".log"):
            candidate = stale.with_suffix(suffix)
            try:
                if candidate.exists():
                    candidate.unlink()
                    removed += 1
            except OSError:
                pass
    return removed


# ---------------------------------------------------------------------------
# Stages
# ---------------------------------------------------------------------------

def stage_preflight(context: Dict[str, Any]) -> Dict[str, Any]:
    """Fail fast and loudly on anything that would corrupt a later stage."""
    detail: Dict[str, Any] = {"repo_root": str(REPO_ROOT), "python": sys.executable}

    missing_modules: List[str] = []
    versions: Dict[str, str] = {}
    for module in REQUIRED_MODULES:
        try:
            imported = __import__(module)
            versions[module] = getattr(imported, "__version__", "unknown")
        except ImportError:
            missing_modules.append(module)
    detail["dependency_versions"] = versions
    detail["missing_modules"] = missing_modules
    if missing_modules:
        raise StageFailure(
            f"Missing required modules: {missing_modules}. "
            f"Run: {sys.executable} -m pip install -r backend/requirements.txt",
            exit_code=EXIT_PREFLIGHT_FAILED,
            detail=detail,
        )

    missing_env = [name for name in REQUIRED_ENV if not os.getenv(name)]
    detail["missing_env"] = missing_env
    if missing_env:
        raise StageFailure(
            f"Missing environment variables: {missing_env} (expected in backend/.env)",
            exit_code=EXIT_PREFLIGHT_FAILED,
            detail=detail,
        )

    try:
        from backend.db.clients.supabase_client import public_read_client
        client = public_read_client
    except Exception as error:  # noqa: BLE001
        raise StageFailure(f"Supabase client init failed: {error}",
                           exit_code=EXIT_PREFLIGHT_FAILED) from error

    table_status: Dict[str, Any] = {}
    missing_tables: List[str] = []
    for table in REQUIRED_TABLES:
        try:
            client.table(table).select("*").limit(1).execute()
            table_status[table] = "ok"
        except Exception as error:  # noqa: BLE001
            table_status[table] = f"unavailable: {str(error)[:120]}"
            missing_tables.append(table)
    detail["tables"] = table_status
    if missing_tables:
        raise StageFailure(
            f"Required tables unavailable: {missing_tables}",
            exit_code=EXIT_PREFLIGHT_FAILED,
            detail=detail,
        )

    context["client"] = client
    return detail


def _static_source_age_days(client) -> Optional[float]:
    from backend.desirability.favoritepokemon_scraper import SOURCE_NAME
    rows = (
        client.table("pokemon_desirability_source_snapshots")
        .select("captured_at,status")
        .eq("source_name", SOURCE_NAME)
        .order("captured_at", desc=True)
        .limit(1)
        .execute()
    ).data or []
    if not rows:
        return None
    captured = rows[0].get("captured_at")
    try:
        when = datetime.fromisoformat(str(captured).replace("Z", "+00:00"))
    except (TypeError, ValueError):
        return None
    return (datetime.now(timezone.utc) - when).total_seconds() / 86400.0


def stage_static(context: Dict[str, Any]) -> Dict[str, Any]:
    """Fan popularity: a near-static community poll. Refresh only when due.

    Scraping this three times a week would add a browser-automation failure
    surface to every run in exchange for data that moves on a scale of months.
    """
    args = context["args"]
    age = _static_source_age_days(context["client"])
    detail: Dict[str, Any] = {"static_source_age_days": round(age, 2) if age is not None else None,
                              "max_age_days": STATIC_MAX_AGE_DAYS}
    due = age is None or age >= STATIC_MAX_AGE_DAYS
    if not (due or args.force_static):
        detail["skipped_reason"] = (
            f"fan-popularity source is {age:.1f} days old (< {STATIC_MAX_AGE_DAYS}); "
            f"pass --force-static to override"
        )
        detail["refreshed"] = False
        return detail

    detail["refreshed"] = True
    detail["trigger"] = "forced" if args.force_static else "age"
    result = run_script(
        "ingest_pokemon_desirability.py",
        ["--source", "favoritepokemon", "--commit" if args.commit else "--dry-run"],
        timeout=1800,
        label="static/favoritepokemon",
    )
    detail["result"] = {k: v for k, v in result.items() if k != "payload"}
    return detail


def stage_trends(context: Dict[str, Any]) -> Dict[str, Any]:
    """Google Trends. Quality-gated; a failed retrieval never becomes a zero."""
    args = context["args"]
    script_args = [
        "--provider", "pytrends",
        "--commit" if args.commit else "--dry-run",
        "--batch-size", str(args.trend_batch_size),
        "--delay-seconds", str(args.trend_delay_seconds),
        "--log-level", "WARNING",
    ]
    if args.trend_limit:
        script_args += ["--limit", str(args.trend_limit)]

    result = with_retries(
        lambda: run_script("ingest_pokemon_trends.py", script_args,
                           timeout=args.trend_timeout, label="trends"),
        attempts=2, base_delay=60.0, label="trends ingest",
    )
    payload = result.get("payload") or {}
    diagnostics = payload.get("diagnostics") or {}

    attempted = diagnostics.get("missing_rows_attempted") or 0
    rate_limited = payload.get("rate_limited_batches") or diagnostics.get("rate_limited_batches") or 0
    failed_batches = diagnostics.get("failed_batches") or 0
    captured = diagnostics.get("final_snapshot_row_count") or 0

    detail: Dict[str, Any] = {
        "status": payload.get("status"),
        "provider": payload.get("provider"),
        "attempted": attempted,
        "captured": captured,
        "rate_limited_batches": rate_limited,
        "failed_batches": failed_batches,
        "duration_seconds": result.get("duration_seconds"),
        "anchor_note": (
            "The shipped single-anchor strategy (Pikachu) compresses roughly half the roster "
            "into Trends' bottom rounding bin. See backend/desirability/trend_anchor_tiers.py "
            "for the measured evidence and the tiered-anchor remedy."
        ),
    }

    # Quality gate. Note deliberately: we gate on FAILURE ratio, not on zero
    # ratio - a genuine zero is information; a failed request is not.
    if attempted:
        failure_ratio = float(failed_batches) / max(attempted, 1)
        detail["failure_ratio"] = round(failure_ratio, 4)
        if rate_limited:
            detail["gate"] = "rate_limited"
            raise StageFailure(
                f"Trends reported {rate_limited} rate-limited batches. Refusing to promote a "
                f"partial capture over existing good data.",
                exit_code=EXIT_SOURCE_QUALITY_GATE_FAILED,
                detail=detail,
            )
        if failure_ratio > MAX_TREND_FAILURE_RATIO:
            detail["gate"] = "failure_ratio_exceeded"
            raise StageFailure(
                f"Trends failure ratio {failure_ratio:.2%} exceeds {MAX_TREND_FAILURE_RATIO:.0%}.",
                exit_code=EXIT_SOURCE_QUALITY_GATE_FAILED,
                detail=detail,
            )
    detail["gate"] = "pass"
    return detail


def stage_composite(context: Dict[str, Any]) -> Dict[str, Any]:
    args = context["args"]
    result = run_script(
        "build_pokemon_desirability_composite.py",
        ["--commit" if args.commit else "--dry-run",
         "--min-coverage", str(MIN_COMPOSITE_COVERAGE), "--log-level", "WARNING"],
        timeout=900, label="composite",
    )
    payload = result.get("payload") or {}
    diagnostics = payload.get("diagnostics") or {}
    processed = diagnostics.get("total_pokemon_processed") or 0
    trend_found = diagnostics.get("trend_scores_found") or 0
    fan_found = diagnostics.get("fan_scores_found") or 0
    detail = {
        "status": payload.get("status"),
        "total_pokemon_processed": processed,
        "fan_scores_found": fan_found,
        "trend_scores_found": trend_found,
        "missing_trend_count": diagnostics.get("missing_trend_count"),
        "scoring_version": diagnostics.get("scoring_version"),
        "duration_seconds": result.get("duration_seconds"),
    }
    if processed:
        coverage = float(fan_found) / processed
        detail["fan_coverage"] = round(coverage, 4)
        if coverage < MIN_COMPOSITE_COVERAGE:
            raise StageFailure(
                f"Composite fan coverage {coverage:.2%} < {MIN_COMPOSITE_COVERAGE:.0%}",
                exit_code=EXIT_VALIDATION_GATE_FAILED, detail=detail,
            )
    detail["gate"] = "pass"
    return detail


def stage_links(context: Dict[str, Any]) -> Dict[str, Any]:
    args = context["args"]
    result = run_script(
        "build_pokemon_card_desirability_links.py",
        ["--all", "--commit" if args.commit else "--dry-run"],
        timeout=1800, label="links",
    )
    return {"duration_seconds": result.get("duration_seconds"),
            "status": (result.get("payload") or {}).get("status")}


def stage_sets(context: Dict[str, Any]) -> Dict[str, Any]:
    """Rebuild set component scores.

    Scheduled runs rebuild only sets whose desirability inputs changed. A full
    rebuild rewrites every set row against the current sources and is therefore
    an explicit, manual decision - never something a thrice-weekly task does on
    its own.
    """
    args = context["args"]
    script_args = ["--commit" if args.commit else "--dry-run"]
    script_args.append("--rebuild-all" if args.rebuild_all else "--rebuild-changed")
    result = run_script(
        "build_pokemon_set_desirability_component_scores.py",
        script_args,
        timeout=1800, label="sets",
    )
    payload = result.get("payload") or {}
    return {"duration_seconds": result.get("duration_seconds"),
            "status": payload.get("status"),
            "rebuild_mode": payload.get("rebuild_mode"),
            "rows_generated": payload.get("rows_generated"),
            "rows_skipped_existing": payload.get("rows_skipped_existing"),
            "rows_to_write": payload.get("rows_to_write"),
            "metric_status_counts": payload.get("metric_status_counts")}


def stage_snapshot(context: Dict[str, Any]) -> Dict[str, Any]:
    """Append today's observation to the point-in-time history tables.

    Guarded: the history tables ship in a PROPOSED migration that may not be
    applied. A missing table is reported as 'blocked', not as a failure of the
    refresh - the current-state pipeline is still valid without it.
    """
    args = context["args"]
    client = context["client"]
    try:
        client.table("pokemon_desirability_score_daily_history").select("observed_on").limit(1).execute()
    except Exception as error:  # noqa: BLE001
        return {
            "status": "blocked",
            "reason": (
                "History tables absent. Apply backend/db/migrations/"
                "046_PROPOSED_desirability_daily_history.sql to enable point-in-time capture."
            ),
            "error": str(error)[:200],
        }
    result = run_script(
        "capture_desirability_history.py",
        (["--commit"] if args.commit else []) + ["--log-level", "WARNING"],
        timeout=900, label="snapshot",
    )
    return {"duration_seconds": result.get("duration_seconds"), "status": "ok"}


STAGE_FUNCTIONS: Dict[str, Callable[[Dict[str, Any]], Dict[str, Any]]] = {
    "preflight": stage_preflight,
    "static": stage_static,
    "trends": stage_trends,
    "composite": stage_composite,
    "links": stage_links,
    "sets": stage_sets,
    "snapshot": stage_snapshot,
}


# ---------------------------------------------------------------------------
# Driver
# ---------------------------------------------------------------------------

def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(
        description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter
    )
    mode = parser.add_mutually_exclusive_group()
    mode.add_argument("--dry-run", action="store_true",
                      help="Preview without writing (THE DEFAULT).")
    mode.add_argument("--commit", action="store_true",
                      help="Actually write. Required for the scheduled task.")
    parser.add_argument("--stage", choices=sorted(STAGE_GROUPS), default="all",
                        help="Run one stage group. Default: all.")
    parser.add_argument("--resume", metavar="RUN_ID",
                        help="Resume a previous run, skipping its completed stages.")
    parser.add_argument("--force-static",
                        action="store_true",
                        help="Refresh the near-static fan-popularity source even if it is not due.")
    parser.add_argument("--rebuild-all",
                        action="store_true",
                        help="Rebuild EVERY set row, not just those whose inputs changed. "
                             "Manual use only; the scheduled task must never pass this.")
    parser.add_argument("--trend-batch-size", type=int, default=5)
    parser.add_argument("--trend-delay-seconds", type=float, default=8.0)
    parser.add_argument("--trend-limit", type=int, default=None,
                        help="Cap subjects (smoke tests only; a partial roster is not a full refresh).")
    parser.add_argument("--trend-timeout", type=int, default=5 * 3600,
                        help="Seconds. A full-roster multi-timeframe capture is measured in hours.")
    parser.add_argument("--log-level", default="INFO")
    return parser


def configure_logging(run_id: str, level: str) -> Path:
    LOG_DIR.mkdir(parents=True, exist_ok=True)
    log_path = LOG_DIR / f"{run_id}.log"
    handlers: List[logging.Handler] = [logging.FileHandler(log_path, encoding="utf-8"),
                                       logging.StreamHandler(sys.stdout)]
    logging.basicConfig(
        level=getattr(logging, level.upper(), logging.INFO),
        format="%(asctime)s %(levelname)-7s %(name)s: %(message)s",
        handlers=handlers,
        force=True,
    )
    logging.getLogger("httpx").setLevel(logging.WARNING)
    logging.getLogger("urllib3").setLevel(logging.WARNING)
    return log_path


def main(argv: Optional[Sequence[str]] = None) -> int:
    args = build_parser().parse_args(argv)
    # Dry run is the default: --commit must be explicit.
    args.commit = bool(args.commit)

    run_id = args.resume or f"{datetime.now(timezone.utc):%Y%m%dT%H%M%SZ}-{uuid.uuid4().hex[:8]}"
    log_path = configure_logging(run_id, args.log_level)
    load_dotenv(REPO_ROOT / "backend" / ".env", override=False)

    already_done: List[str] = []
    if args.resume:
        already_done = list(load_checkpoint(run_id).get("completed_stages") or [])
        logger.info("Resuming run %s; already completed: %s", run_id, already_done or "nothing")

    planned = [s for s in STAGE_GROUPS[args.stage]]
    started_at = datetime.now(timezone.utc)
    logger.info("=" * 72)
    logger.info("Desirability refresh %s | mode=%s | stages=%s",
                run_id, "COMMIT" if args.commit else "DRY-RUN", ",".join(planned))
    logger.info("Repo root: %s", REPO_ROOT)
    logger.info("=" * 72)

    context: Dict[str, Any] = {"args": args, "run_id": run_id}
    results: List[StageResult] = []
    exit_code = EXIT_OK
    completed: List[str] = list(already_done)

    try:
        with RunLock(LOCK_PATH, run_id):
            for name in planned:
                if name in already_done and name != "preflight":
                    results.append(StageResult(name=name, status="skipped",
                                               detail={"reason": "completed in the resumed run"}))
                    logger.info("[%s] skipped (already completed)", name)
                    continue
                stage = StageResult(name=name, started_at=datetime.now(timezone.utc).isoformat())
                clock = time.time()
                try:
                    stage.detail = STAGE_FUNCTIONS[name](context)
                    stage.status = "skipped" if stage.detail.get("refreshed") is False else "ok"
                    if stage.detail.get("status") == "blocked":
                        stage.status = "skipped"
                    if name not in completed:
                        completed.append(name)
                except StageFailure as failure:
                    stage.status = "failed"
                    stage.error = str(failure)
                    stage.traceback = traceback.format_exc()
                    if failure.detail:
                        stage.detail = {**stage.detail, "failure_detail": failure.detail}
                    exit_code = failure.exit_code
                    logger.error("[%s] FAILED: %s", name, failure)
                    results.append(stage)
                    break
                except Exception as error:  # noqa: BLE001 - recorded, never swallowed
                    stage.status = "failed"
                    stage.error = f"{type(error).__name__}: {error}"
                    stage.traceback = traceback.format_exc()
                    exit_code = EXIT_STAGE_FAILED
                    logger.exception("[%s] UNEXPECTED FAILURE", name)
                    results.append(stage)
                    break
                finally:
                    stage.ended_at = datetime.now(timezone.utc).isoformat()
                    stage.duration_seconds = round(time.time() - clock, 2)
                    save_checkpoint(run_id, completed, {"last_stage": name})
                results.append(stage)
                logger.info("[%s] %s in %.1fs", name, stage.status, stage.duration_seconds or 0)
    except StageFailure as failure:
        exit_code = failure.exit_code
        logger.error("Run aborted: %s", failure)
        results.append(StageResult(name="lock", status="failed", error=str(failure)))
    except KeyboardInterrupt:
        exit_code = EXIT_INTERRUPTED
        logger.warning("Interrupted by user.")

    ended_at = datetime.now(timezone.utc)
    pruned = prune_logs()
    manifest = {
        "run_id": run_id,
        "orchestrator_version": ORCHESTRATOR_VERSION,
        "started_at": started_at.isoformat(),
        "ended_at": ended_at.isoformat(),
        "duration_seconds": round((ended_at - started_at).total_seconds(), 2),
        "requested_mode": "commit" if args.commit else "dry_run",
        "writes_occurred": bool(args.commit and exit_code == EXIT_OK),
        "requested_stage_group": args.stage,
        "planned_stages": planned,
        "successful_stages": [r.name for r in results if r.status == "ok"],
        "skipped_stages": [r.name for r in results if r.status == "skipped"],
        "failed_stages": [r.name for r in results if r.status == "failed"],
        "exit_code": exit_code,
        "stages": [r.to_dict() for r in results],
        "log_path": str(log_path),
        "logs_pruned": pruned,
        "quality_gates": {
            "min_trend_usable_ratio": MIN_TREND_USABLE_RATIO,
            "max_trend_failure_ratio": MAX_TREND_FAILURE_RATIO,
            "min_composite_coverage": MIN_COMPOSITE_COVERAGE,
        },
        "static_source_policy": {
            "max_age_days": STATIC_MAX_AGE_DAYS,
            "rationale": (
                "favoritepokemon fan popularity is a community poll that moves on a scale of "
                "months. Re-scraping it three times a week adds a browser-automation failure "
                "surface for no new information."
            ),
        },
    }
    manifest_path = LOG_DIR / f"{run_id}.json"
    manifest_path.write_text(json.dumps(manifest, indent=2, default=str), encoding="utf-8")

    logger.info("=" * 72)
    logger.info("Run %s finished: exit=%s ok=%s failed=%s",
                run_id, exit_code, manifest["successful_stages"], manifest["failed_stages"])
    logger.info("Manifest: %s", manifest_path)
    if not args.commit and exit_code == EXIT_OK:
        logger.info("DRY RUN - nothing was written. Re-run with --commit to persist.")
    logger.info("=" * 72)
    return exit_code


if __name__ == "__main__":
    raise SystemExit(main())
