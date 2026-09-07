"""Lean, serial, resource-guarded, lockable operational worker that builds at
most one stale ``cache_kind='maintained'`` Market Explorer query cache per
invocation, then exits, releasing all process memory.

WHY THIS EXISTS (P0 incident, 2026-09): ``run_market_explorer_daily_publication.py``
used to end its normal daily run by discovering every maintained cache and
rebuilding all of them (21, all stale that day) serially IN THE SAME PROCESS
as the authoritative projection. That drove the Oracle scraper VM to memory
saturation and made it unresponsive over SSH. This script is the replacement:
a completely separate CLI, never called by the daily publication path, never
called by any cron/systemd entry as part of this change (that is a
deliberate, separate operational decision -- see the module docstring of
``run_market_explorer_daily_publication.py``). One invocation builds at most
``--max-caches`` (default 1) stale caches and exits; an operator or scheduler
runs it repeatedly to work through a backlog without ever holding more than
one cache's worth of build memory at a time.

Not a benchmark runner: unlike ``build_market_explorer_maintained_cache.py``
this never repeats a build for cold/L1/L2 timing samples -- exactly one real
planner/cache build per selected cache.

Uses only Python stdlib for the host-resource guard (no psutil): available/
total memory from ``/proc/meminfo`` on Linux, load average from
``os.getloadavg()``, cpu count from ``os.cpu_count()``. On a host where these
are unavailable (e.g. a Windows dev box, or a container without
``/proc/meminfo``) the guard reports "unavailable" and does not block --
it must never crash local/non-Linux runs.

Dry-run is the default-safe mode; writes require ``--commit``.

FAILURE COOLDOWN (added after a live 2026-09 remediation found that
deterministic oldest-``computed_through``-first ordering lets one
persistently-failing maintained cache win the single selection slot on every
invocation forever, starving every other stale cache behind it): a stale row
with ``status='failed'`` whose ``updated_at`` is within
``--failure-cooldown-seconds`` (default 900s / 15 minutes) of "now" is
deprioritized -- sorted after every other eligible stale cache -- rather than
excluded outright, so it is still picked (and thus still retried) when it is
the only stale cache left. This uses the cache row's own ``updated_at``
column; no schema change and no separate failure-tracking table. The row's
``status`` is never rewritten by this deprioritization and it is never
permanently excluded: once ``updated_at`` ages past the cooldown it re-enters
normal oldest-first priority on its own. ``--skip-fingerprint`` remains
available as a manual override for a human operator, but the cooldown is what
lets the unattended scheduler make progress on its own.
"""
from __future__ import annotations

import argparse
import json
import logging
import os
import time
from dataclasses import asdict, dataclass
from datetime import datetime, timezone
from typing import Any, Callable, Optional, Sequence

from backend.db.services.market_explorer_maintained_cache_ops import (
    CacheAdvanceReport,
    advance_one_maintained_cache,
    discover_maintained_caches,
)
from backend.scripts.run_market_explorer_daily_publication import (
    resolve_latest_approved_market_date,
)

LOG = logging.getLogger("market_explorer_maintained_cache_prewarm")

DEFAULT_LOCK_PATH = "/tmp/market_explorer_maintained_cache_prewarm.lock"
DEFAULT_MIN_AVAILABLE_MEMORY_MB = 512.0
DEFAULT_MIN_AVAILABLE_MEMORY_PERCENT = 25.0
DEFAULT_MAX_LOAD_PER_CPU = 1.5
DEFAULT_FAILURE_COOLDOWN_SECONDS = 900.0


# --- Host resource metrics (stdlib only; never crashes off-Linux) ------------

def available_memory_mb() -> Optional[float]:
    """Best-effort ``MemAvailable`` from ``/proc/meminfo``, or ``None`` when
    unavailable (any non-Linux host, or a container without the file) --
    callers must treat ``None`` as "unverifiable", never as zero.
    """
    try:
        with open("/proc/meminfo", "r", encoding="utf-8") as handle:
            for line in handle:
                if line.startswith("MemAvailable:"):
                    return float(line.split()[1]) / 1024.0
    except Exception:  # pragma: no cover - exercised off-Linux / sandboxed
        return None
    return None


def total_memory_mb() -> Optional[float]:
    """Best-effort ``MemTotal`` from ``/proc/meminfo``, or ``None``."""
    try:
        with open("/proc/meminfo", "r", encoding="utf-8") as handle:
            for line in handle:
                if line.startswith("MemTotal:"):
                    return float(line.split()[1]) / 1024.0
    except Exception:  # pragma: no cover - exercised off-Linux / sandboxed
        return None
    return None


def load_average_per_cpu() -> Optional[float]:
    """1-minute load average divided by CPU count, or ``None`` when either
    ``os.getloadavg()`` or ``os.cpu_count()`` is unavailable (Windows has no
    ``getloadavg``)."""
    try:
        load1 = os.getloadavg()[0]
    except (AttributeError, OSError):  # pragma: no cover - exercised on Windows
        return None
    cpus = os.cpu_count() or 1
    return load1 / cpus


@dataclass
class HostGuardResult:
    ok: bool
    reason: Optional[str] = None
    observed: dict[str, Any] = None  # type: ignore[assignment]

    def __post_init__(self) -> None:
        if self.observed is None:
            self.observed = {}


def evaluate_host_guard(
    *, min_available_memory_mb: float = DEFAULT_MIN_AVAILABLE_MEMORY_MB,
    min_available_memory_percent: float = DEFAULT_MIN_AVAILABLE_MEMORY_PERCENT,
    max_load_per_cpu: float = DEFAULT_MAX_LOAD_PER_CPU,
) -> HostGuardResult:
    """Never raises. When a metric is unavailable it is reported as such and
    does NOT block the build (there is nothing to guard against if the host
    cannot be observed -- e.g. every dev box on Windows).
    """
    available_mb = available_memory_mb()
    total_mb = total_memory_mb()
    load_per_cpu = load_average_per_cpu()
    observed = {
        "availableMemoryMb": available_mb if available_mb is not None else "unavailable",
        "totalMemoryMb": total_mb if total_mb is not None else "unavailable",
        "loadPerCpu": load_per_cpu if load_per_cpu is not None else "unavailable",
    }

    if available_mb is not None:
        threshold_mb = min_available_memory_mb
        if total_mb is not None:
            threshold_mb = max(threshold_mb, (min_available_memory_percent / 100.0) * total_mb)
        observed["memoryThresholdMb"] = threshold_mb
        if available_mb < threshold_mb:
            return HostGuardResult(
                ok=False,
                reason=(f"available memory {available_mb:.1f}MB below threshold "
                        f"{threshold_mb:.1f}MB"),
                observed=observed,
            )

    if load_per_cpu is not None:
        observed["loadThresholdPerCpu"] = max_load_per_cpu
        if load_per_cpu > max_load_per_cpu:
            return HostGuardResult(
                ok=False,
                reason=(f"load-per-cpu {load_per_cpu:.2f} above threshold "
                        f"{max_load_per_cpu:.2f}"),
                observed=observed,
            )

    return HostGuardResult(ok=True, observed=observed)


# --- Singleton lock (worker only; never used by daily publication) ----------

class FileLock:
    """Nonblocking, auto-release-on-exit singleton lock.

    Uses ``fcntl.flock`` on POSIX (the production target -- the Oracle VM is
    Linux). On any platform without ``fcntl`` (Windows dev boxes) this falls
    back to atomic exclusive file creation, which is enough to make the
    behavior testable everywhere without a real global lock. Tests should
    inject a lock instance pointed at a temp path (or a fake) rather than
    depend on the real ``DEFAULT_LOCK_PATH``.
    """

    def __init__(self, path: str = DEFAULT_LOCK_PATH):
        self.path = path
        self._fh = None
        self._owns_fallback_file = False

    def acquire(self) -> bool:
        try:
            import fcntl  # type: ignore
        except ImportError:
            return self._acquire_fallback()
        try:
            self._fh = open(self.path, "w")
            fcntl.flock(self._fh, fcntl.LOCK_EX | fcntl.LOCK_NB)
        except OSError:
            if self._fh is not None:
                self._fh.close()
                self._fh = None
            return False
        return True

    def _acquire_fallback(self) -> bool:
        try:
            fd = os.open(self.path, os.O_CREAT | os.O_EXCL | os.O_WRONLY)
        except FileExistsError:
            return False
        os.write(fd, str(os.getpid()).encode("utf-8"))
        os.close(fd)
        self._owns_fallback_file = True
        return True

    def release(self) -> None:
        if self._fh is not None:
            try:
                import fcntl  # type: ignore
                fcntl.flock(self._fh, fcntl.LOCK_UN)
            except Exception:  # pragma: no cover - best-effort release
                pass
            try:
                self._fh.close()
            except Exception:  # pragma: no cover
                pass
            self._fh = None
        if self._owns_fallback_file:
            try:
                os.remove(self.path)
            except OSError:  # pragma: no cover
                pass
            self._owns_fallback_file = False

    def __enter__(self) -> "FileLock":
        self.acquire()
        return self

    def __exit__(self, *_exc: Any) -> None:
        self.release()


# --- Discovery / staleness / ordering ----------------------------------------

def _is_stale(row: dict[str, Any], target_market_date: str) -> bool:
    """A row is stale unless it is genuinely ready at/beyond the target
    date -- mirrors ``advance_one_maintained_cache``'s already-current check
    exactly so discovery and build agree on what "current" means."""
    return not (row.get("status") == "ready"
                and str(row.get("computed_through") or "")[:10] >= target_market_date)


def _parse_timestamp(value: Any) -> Optional[datetime]:
    if not value:
        return None
    try:
        parsed = datetime.fromisoformat(str(value).replace("Z", "+00:00"))
    except ValueError:
        return None
    if parsed.tzinfo is None:
        parsed = parsed.replace(tzinfo=timezone.utc)
    return parsed


def _in_failure_cooldown(row: dict[str, Any], *, now: datetime,
                          cooldown_seconds: float) -> bool:
    """True when ``row`` failed recently enough that it should be
    deprioritized behind other eligible stale caches this invocation.

    Only ``status='failed'`` rows are ever deprioritized -- a row stuck
    ``status='building'`` (an orphaned lease) is a different failure mode
    the health checker surfaces separately and is not touched here."""
    if row.get("status") != "failed" or cooldown_seconds <= 0:
        return False
    updated_at = _parse_timestamp(row.get("updated_at"))
    if updated_at is None:
        return False
    return (now - updated_at).total_seconds() < cooldown_seconds


def select_stale_caches(
    rows: Sequence[dict[str, Any]], *, target_market_date: str,
    now: Optional[datetime] = None,
    failure_cooldown_seconds: float = DEFAULT_FAILURE_COOLDOWN_SECONDS,
) -> list[dict[str, Any]]:
    """Deterministic oldest-``computed_through``-first, then stable
    fingerprint order -- never a random / dict-iteration-order pick.

    A ``status='failed'`` row whose ``updated_at`` is within
    ``failure_cooldown_seconds`` is moved behind every other eligible stale
    row (not removed -- it is still selected, and thus still retried, once it
    is the only stale cache left) so a persistently-failing cache cannot
    starve everything behind it under ``--max-caches 1``. It naturally
    regains normal priority once ``updated_at`` ages past the cooldown."""
    now = now or datetime.now(timezone.utc)
    stale = [row for row in rows if _is_stale(row, target_market_date)]
    ordered = sorted(
        stale,
        key=lambda row: (str(row.get("computed_through") or "0000-00-00")[:10],
                          str(row.get("query_fingerprint") or "")),
    )
    cooling_down = [row for row in ordered
                    if _in_failure_cooldown(row, now=now, cooldown_seconds=failure_cooldown_seconds)]
    eligible = [row for row in ordered if row not in cooling_down]
    return eligible + cooling_down


# --- Worker summary -----------------------------------------------------------

@dataclass
class PrewarmSummary:
    targetMarketDate: Optional[str] = None
    discoveredMaintained: int = 0
    staleMaintained: int = 0
    alreadyCurrent: int = 0
    attempted: int = 0
    advanced: int = 0
    failed: int = 0
    deferred: list[str] = None  # type: ignore[assignment]
    skipped: list[str] = None  # type: ignore[assignment]
    coolingDown: list[str] = None  # type: ignore[assignment]
    stopReason: Optional[str] = None
    reports: list[dict[str, Any]] = None  # type: ignore[assignment]
    elapsedSeconds: float = 0.0

    def __post_init__(self) -> None:
        if self.deferred is None:
            self.deferred = []
        if self.skipped is None:
            self.skipped = []
        if self.coolingDown is None:
            self.coolingDown = []
        if self.reports is None:
            self.reports = []


def run_prewarm(
    client: Any, *, market_date: Optional[str] = None, max_caches: int = 1,
    commit: bool = False, only_set_ids: Sequence[str] = (),
    skip_fingerprints: Sequence[str] = (),
    failure_cooldown_seconds: float = DEFAULT_FAILURE_COOLDOWN_SECONDS,
    now: Optional[datetime] = None,
    lock: Optional[FileLock] = None,
    guard: Callable[[], HostGuardResult] = evaluate_host_guard,
) -> dict[str, Any]:
    started = time.monotonic()
    summary = PrewarmSummary()

    lock = lock or FileLock()
    if not lock.acquire():
        summary.stopReason = "already_running"
        summary.elapsedSeconds = round(time.monotonic() - started, 3)
        return asdict(summary)

    try:
        target = market_date or resolve_latest_approved_market_date(client)
        if not target:
            summary.stopReason = "no_approved_market_date"
            summary.elapsedSeconds = round(time.monotonic() - started, 3)
            return asdict(summary)
        summary.targetMarketDate = target

        rows = discover_maintained_caches(client)
        if only_set_ids:
            scope = {str(v) for v in only_set_ids}
            rows = [row for row in rows
                    if {str(v) for v in ((row.get("normalized_spec") or {}).get("setIds") or [])} & scope]
        summary.discoveredMaintained = len(rows)

        if not rows:
            summary.stopReason = "no_maintained_caches"
            summary.elapsedSeconds = round(time.monotonic() - started, 3)
            return asdict(summary)

        stale = select_stale_caches(rows, target_market_date=target,
                                     now=now, failure_cooldown_seconds=failure_cooldown_seconds)
        summary.staleMaintained = len(stale)
        summary.alreadyCurrent = summary.discoveredMaintained - summary.staleMaintained
        summary.coolingDown = [
            str(row.get("query_fingerprint") or "") for row in stale
            if _in_failure_cooldown(row, now=now or datetime.now(timezone.utc),
                                     cooldown_seconds=failure_cooldown_seconds)
        ]

        if skip_fingerprints:
            skip = {str(v) for v in skip_fingerprints}
            summary.skipped = [str(row.get("query_fingerprint") or "") for row in stale
                                if str(row.get("query_fingerprint") or "") in skip]
            stale = [row for row in stale if str(row.get("query_fingerprint") or "") not in skip]

        if not stale:
            summary.stopReason = "no_stale_caches"
            summary.elapsedSeconds = round(time.monotonic() - started, 3)
            return asdict(summary)

        remaining = list(stale)
        while remaining and summary.attempted < max_caches:
            if commit:
                guard_result = guard()
                if not guard_result.ok:
                    summary.stopReason = f"host_guard:{guard_result.reason}"
                    summary.reports.append({"event": "host_guard_deferred",
                                             "observed": guard_result.observed,
                                             "reason": guard_result.reason})
                    break

            row = remaining.pop(0)
            summary.attempted += 1
            try:
                report = advance_one_maintained_cache(client, row, market_date=target, commit=commit)
            except Exception as exc:  # noqa: BLE001 - isolated; never corrupts other caches
                summary.failed += 1
                summary.reports.append(asdict(CacheAdvanceReport(
                    fingerprint=str(row.get("query_fingerprint") or ""),
                    label=str(row.get("label") or row.get("query_fingerprint") or "?"),
                    status="failed", error=str(exc),
                )))
                LOG.error(json.dumps({
                    "event": "maintained_cache_build_failed",
                    "fingerprint": row.get("query_fingerprint"), "error": str(exc),
                }, sort_keys=True))
                continue
            if report.status == "advanced":
                summary.advanced += 1
            summary.reports.append(asdict(report))

        if summary.stopReason is None:
            summary.stopReason = "max_caches_reached" if remaining or summary.attempted >= max_caches else "completed"

        summary.deferred = [str(row.get("query_fingerprint") or "") for row in remaining]
        summary.elapsedSeconds = round(time.monotonic() - started, 3)
        return asdict(summary)
    finally:
        lock.release()


# --- CLI ----------------------------------------------------------------------

def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(description=__doc__)
    mode = parser.add_mutually_exclusive_group(required=True)
    mode.add_argument("--dry-run", action="store_true", help="Plan the run; perform no writes.")
    mode.add_argument("--commit", action="store_true", help="Execute via the service-role client.")
    parser.add_argument("--market-date", default=None,
                        help="Override the target market date (default: latest approved).")
    parser.add_argument("--max-caches", type=int, default=1,
                        help="Maximum stale caches to build in this invocation (default: 1).")
    parser.add_argument("--only-set-id", action="append", default=[],
                        help="Repeatable; restrict to maintained caches overlapping these set IDs.")
    parser.add_argument("--skip-fingerprint", action="append", default=[],
                        help="Repeatable; manual override to exclude these query_fingerprint values "
                             "from selection this invocation. Does not clear or alter the skipped "
                             "row's own status. Prefer letting --failure-cooldown-seconds handle this "
                             "automatically; this flag is for a human operator investigating a "
                             "specific cache.")
    parser.add_argument("--failure-cooldown-seconds", type=float,
                        default=DEFAULT_FAILURE_COOLDOWN_SECONDS,
                        help="A stale cache with status='failed' whose updated_at is within this many "
                             "seconds is deprioritized behind other eligible stale caches so it cannot "
                             "starve them under --max-caches 1 (default: 900s / 15 minutes). It is "
                             "still selected -- and thus retried -- once it is the only stale cache "
                             "left, and regains normal priority once the cooldown elapses. Set to 0 "
                             "to disable.")
    parser.add_argument("--lock-path", default=DEFAULT_LOCK_PATH)
    parser.add_argument("--min-available-memory-mb", type=float,
                        default=DEFAULT_MIN_AVAILABLE_MEMORY_MB)
    parser.add_argument("--min-available-memory-percent", type=float,
                        default=DEFAULT_MIN_AVAILABLE_MEMORY_PERCENT)
    parser.add_argument("--max-load-per-cpu", type=float, default=DEFAULT_MAX_LOAD_PER_CPU)
    return parser


def main() -> int:
    logging.basicConfig(level=logging.INFO, format="%(message)s")
    args = build_parser().parse_args()
    from backend.db.clients.supabase_client import create_service_role_client
    client = create_service_role_client()

    def guard() -> HostGuardResult:
        return evaluate_host_guard(
            min_available_memory_mb=args.min_available_memory_mb,
            min_available_memory_percent=args.min_available_memory_percent,
            max_load_per_cpu=args.max_load_per_cpu,
        )

    report = run_prewarm(
        client, market_date=args.market_date, max_caches=args.max_caches,
        commit=bool(args.commit), only_set_ids=args.only_set_id,
        skip_fingerprints=args.skip_fingerprint,
        failure_cooldown_seconds=args.failure_cooldown_seconds,
        lock=FileLock(args.lock_path), guard=guard,
    )
    print(json.dumps(report, indent=2, sort_keys=True, default=str))
    return 1 if report["failed"] else 0


if __name__ == "__main__":
    raise SystemExit(main())
