"""Host-local production database safety hold.

The default state lives outside the Git checkout so deploys cannot silently
clear an incident hold. Application serving reads do not use this gate.

Sentinel may repair exactly one corruption shape automatically: an empty,
regular, mode-0600 hold owned by the production account, and only after proving
that disk headroom, the workload guard, the database, and the scheduler are all
healthy. Valid or non-empty malformed holds remain fail-closed.
"""
from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime, timezone
import importlib.util
import json
import os
from pathlib import Path
import pwd
import shutil
import stat
import subprocess
import time
from typing import Any, Callable, Optional


DEFAULT_HOLD_PATH = Path("/home/ubuntu/state/db-safety/hold.json")
DEFAULT_GUARD_PATH = Path("/home/ubuntu/state/db-safety/db_workload_guard.py")
DEFAULT_BACKUP_DIR = Path("/home/ubuntu/ops-backups")
DEFAULT_EXPECTED_OWNER = "ubuntu"
MIN_ROOT_FREE_BYTES = 5 * 1024 * 1024 * 1024

HOLD_ABSENT = "absent"
HOLD_ACTIVE_VALID = "active_valid"
HOLD_INVALID_EMPTY = "invalid_empty"
HOLD_INVALID_MALFORMED = "invalid_malformed"
HOLD_INVALID_PATH = "invalid_path"
HOLD_INACCESSIBLE = "inaccessible"


@dataclass(frozen=True)
class MaintenanceHoldInspection:
    state: str
    path: str
    size_bytes: Optional[int] = None
    mode: Optional[int] = None
    owner: Optional[str] = None
    reason: Optional[str] = None
    parse_error: Optional[str] = None

    @property
    def active(self) -> bool:
        return self.state != HOLD_ABSENT

    def to_dict(self) -> dict[str, Any]:
        return {
            "state": self.state,
            "path": self.path,
            "size_bytes": self.size_bytes,
            "mode": self.mode,
            "owner": self.owner,
            "reason": self.reason,
            "parse_error": self.parse_error,
        }


def _hold_path(path: Optional[Path | str] = None) -> Path:
    if path is not None:
        return Path(path)
    return Path(os.environ.get("INDEX_DB_SAFETY_HOLD_PATH") or DEFAULT_HOLD_PATH)


def _owner_name(uid: int) -> Optional[str]:
    try:
        return pwd.getpwuid(uid).pw_name
    except (KeyError, OSError):
        return None


def inspect_maintenance_hold(
    path: Optional[Path | str] = None,
) -> MaintenanceHoldInspection:
    resolved = _hold_path(path)
    try:
        info = resolved.lstat()
    except FileNotFoundError:
        return MaintenanceHoldInspection(HOLD_ABSENT, str(resolved))
    except OSError as exc:
        return MaintenanceHoldInspection(
            HOLD_INACCESSIBLE,
            str(resolved),
            parse_error=exc.__class__.__name__,
        )

    mode = stat.S_IMODE(info.st_mode)
    owner = _owner_name(info.st_uid)
    common = {
        "path": str(resolved),
        "size_bytes": int(info.st_size),
        "mode": mode,
        "owner": owner,
    }
    if stat.S_ISLNK(info.st_mode) or not stat.S_ISREG(info.st_mode):
        return MaintenanceHoldInspection(HOLD_INVALID_PATH, **common)
    if info.st_size == 0:
        return MaintenanceHoldInspection(HOLD_INVALID_EMPTY, **common)

    try:
        payload = json.loads(resolved.read_text(encoding="utf-8"))
    except Exception as exc:
        return MaintenanceHoldInspection(
            HOLD_INVALID_MALFORMED,
            **common,
            parse_error=exc.__class__.__name__,
        )
    if not isinstance(payload, dict):
        return MaintenanceHoldInspection(
            HOLD_INVALID_MALFORMED,
            **common,
            parse_error="payload_not_object",
        )
    reason = str(payload.get("reason") or "").strip()
    if not reason:
        return MaintenanceHoldInspection(
            HOLD_INVALID_MALFORMED,
            **common,
            parse_error="reason_missing",
        )
    return MaintenanceHoldInspection(
        HOLD_ACTIVE_VALID,
        **common,
        reason=reason,
    )


def maintenance_hold_active() -> bool:
    # Preserve the original fail-closed contract: every state except absence is
    # an active fence, including unreadable or malformed state.
    return inspect_maintenance_hold().active


def require_maintenance_allowed() -> None:
    if maintenance_hold_active():
        raise RuntimeError("production_database_safety_hold_active")


def _default_live_pressure_loader(guard_path: Path) -> Optional[str]:
    spec = importlib.util.spec_from_file_location("index_db_workload_guard", guard_path)
    if spec is None or spec.loader is None:
        raise RuntimeError("workload_guard_import_unavailable")
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    loader = getattr(module, "live_pressure", None)
    if not callable(loader):
        raise RuntimeError("workload_guard_live_pressure_missing")
    value = loader()
    return str(value) if value else None


def _default_crontab_loader() -> str:
    result = subprocess.run(
        ["crontab", "-l"],
        capture_output=True,
        text=True,
        check=False,
        timeout=10,
    )
    if result.returncode != 0:
        raise RuntimeError("crontab_unavailable")
    return result.stdout


def _probe_database(client: Any) -> dict[str, Any]:
    rows = list(
        client.table("pokemon_scrape_batches")
        .select("id,market_date,status")
        .order("market_date", desc=True)
        .limit(1)
        .execute().data
        or []
    )
    if not rows:
        raise RuntimeError("database_probe_no_scrape_batch")
    return dict(rows[0])


def _same_inode(path: Path, initial: os.stat_result) -> bool:
    try:
        current = path.lstat()
    except OSError:
        return False
    return (
        current.st_dev == initial.st_dev
        and current.st_ino == initial.st_ino
        and current.st_size == 0
        and stat.S_ISREG(current.st_mode)
        and not stat.S_ISLNK(current.st_mode)
    )


def repair_invalid_empty_hold_if_safe(
    client: Any,
    *,
    path: Optional[Path | str] = None,
    guard_path: Path | str = DEFAULT_GUARD_PATH,
    backup_dir: Path | str = DEFAULT_BACKUP_DIR,
    expected_owner: Optional[str] = None,
    min_root_free_bytes: int = MIN_ROOT_FREE_BYTES,
    root_free_loader: Optional[Callable[[], int]] = None,
    live_pressure_loader: Optional[Callable[[Path], Optional[str]]] = None,
    crontab_loader: Optional[Callable[[], str]] = None,
    sleep: Callable[[float], None] = time.sleep,
    probe_attempts: int = 3,
) -> dict[str, Any]:
    """Clear only a proven empty/corrupt hold after independent safety gates.

    This intentionally does not repair valid holds, symlinks, non-regular
    paths, or non-empty malformed JSON. Those remain fail-closed.
    """
    resolved = _hold_path(path)
    inspection = inspect_maintenance_hold(resolved)
    if inspection.state != HOLD_INVALID_EMPTY:
        return {
            "status": "blocked",
            "reason": "hold_not_invalid_empty",
            "hold_state": inspection.state,
        }

    initial = resolved.lstat()
    owner = inspection.owner
    required_owner = (
        expected_owner
        if expected_owner is not None
        else os.environ.get("INDEX_DB_SAFETY_HOLD_OWNER", DEFAULT_EXPECTED_OWNER)
    )
    if owner != required_owner:
        return {
            "status": "blocked",
            "reason": "hold_owner_mismatch",
            "observed_owner": owner,
        }
    if inspection.mode != 0o600:
        return {
            "status": "blocked",
            "reason": "hold_mode_mismatch",
            "observed_mode": inspection.mode,
        }

    free_loader = root_free_loader or (lambda: int(shutil.disk_usage("/").free))
    root_free = int(free_loader())
    if root_free < int(min_root_free_bytes):
        return {
            "status": "blocked",
            "reason": "insufficient_root_headroom",
            "root_free_bytes": root_free,
        }

    resolved_guard = Path(guard_path)
    try:
        guard_stat = resolved_guard.lstat()
    except OSError:
        return {"status": "blocked", "reason": "workload_guard_missing"}
    if stat.S_ISLNK(guard_stat.st_mode) or not stat.S_ISREG(guard_stat.st_mode):
        return {"status": "blocked", "reason": "workload_guard_invalid_path"}
    if _owner_name(guard_stat.st_uid) != required_owner:
        return {"status": "blocked", "reason": "workload_guard_owner_mismatch"}

    pressure_reader = live_pressure_loader or _default_live_pressure_loader
    try:
        pressure = pressure_reader(resolved_guard)
    except Exception as exc:
        return {
            "status": "blocked",
            "reason": "live_pressure_unavailable",
            "error_type": exc.__class__.__name__,
        }
    if pressure:
        return {
            "status": "blocked",
            "reason": "live_db_pressure_active",
            "pressure": str(pressure),
        }

    cron_reader = crontab_loader or _default_crontab_loader
    try:
        cron = cron_reader()
    except Exception as exc:
        return {
            "status": "blocked",
            "reason": "scheduler_state_unavailable",
            "error_type": exc.__class__.__name__,
        }
    disabled_entries = sum(
        1 for line in cron.splitlines() if line.startswith("# CODE_RED_DISABLED ")
    )
    if disabled_entries:
        return {
            "status": "blocked",
            "reason": "code_red_scheduler_still_disabled",
            "disabled_entries": disabled_entries,
        }

    latest_batch: Optional[dict[str, Any]] = None
    attempts = max(1, int(probe_attempts))
    for attempt in range(attempts):
        try:
            latest_batch = _probe_database(client)
        except Exception as exc:
            return {
                "status": "blocked",
                "reason": "database_probe_failed",
                "error_type": exc.__class__.__name__,
                "probe_number": attempt + 1,
            }
        if attempt + 1 < attempts:
            sleep(2)

    # Defend against a concurrent operator replacing the hold after our gates.
    if not _same_inode(resolved, initial):
        return {"status": "blocked", "reason": "hold_changed_during_repair"}
    final = inspect_maintenance_hold(resolved)
    if (
        final.state != HOLD_INVALID_EMPTY
        or final.mode != 0o600
        or final.owner != required_owner
    ):
        return {"status": "blocked", "reason": "hold_changed_during_repair"}

    backup_root = Path(backup_dir)
    backup_root.mkdir(parents=True, exist_ok=True)
    os.chmod(backup_root, 0o700)
    stamp = datetime.now(timezone.utc).strftime("%Y%m%dT%H%M%S%fZ")
    backup = backup_root / f"hold.invalid-empty.{stamp}.{initial.st_ino}.bak"

    # Write the forensic copy first. If anything fails before unlink, the
    # fail-closed hold remains in place.
    with backup.open("xb") as target:
        target.flush()
        os.fsync(target.fileno())
    os.chmod(backup, 0o600)

    if not _same_inode(resolved, initial):
        try:
            backup.unlink()
        except OSError:
            pass
        return {"status": "blocked", "reason": "hold_changed_before_unlink"}

    resolved.unlink()
    try:
        dir_fd = os.open(str(resolved.parent), os.O_RDONLY)
    except OSError:
        dir_fd = None
    if dir_fd is not None:
        try:
            os.fsync(dir_fd)
        finally:
            os.close(dir_fd)

    return {
        "status": "cleared_invalid_empty_hold",
        "mutation_performed": True,
        "backup_path": str(backup),
        "root_free_bytes": root_free,
        "database_probe_market_date": (latest_batch or {}).get("market_date"),
    }
