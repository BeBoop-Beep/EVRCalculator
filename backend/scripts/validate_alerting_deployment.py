"""Fail production deploy when alert delivery/watchdog scheduling is unsafe or absent."""

from __future__ import annotations

import json
import re
import subprocess
import sys
from pathlib import Path
from typing import Any, Dict, List, Tuple

_PROJECT_ROOT = Path(__file__).resolve().parents[2]
if str(_PROJECT_ROOT) not in sys.path:
    sys.path.insert(0, str(_PROJECT_ROOT))

from backend.alerts.dispatcher import get_dispatcher_health


REQUIRED_SCHEDULES: Dict[str, Tuple[str, str, str, str, str]] = {
    "backend.alerts.dispatcher": ("*", "*", "*", "*", "*"),
    "backend.alerts.market_freshness_watchdog": ("*/5", "*", "*", "*", "*"),
}
_NONBLOCKING_FLOCK_RE = re.compile(r"(?:^|\s)(?:\S*/)?flock\s+-n(?:\s|$)")


def _active_cron_entries(text: str) -> List[Dict[str, Any]]:
    entries: List[Dict[str, Any]] = []
    for raw_line in text.splitlines():
        stripped = raw_line.strip()
        if not stripped or stripped.startswith("#"):
            continue
        parts = stripped.split(None, 5)
        if len(parts) < 6:
            # Environment assignments (for example CRON_TZ=...) and malformed
            # lines are not executable five-field cron entries.
            continue
        entries.append({
            "schedule": tuple(parts[:5]),
            "command": parts[5],
        })
    return entries


def validate_schedule_text(text: str) -> Dict[str, Any]:
    """Validate active, independent, canonical alert schedules.

    Commented commands do not count. Each required command must have at least
    one active entry at its canonical cadence and that canonical entry must use
    a non-blocking ``flock -n`` guard. Host-specific paths are deliberately not
    validated.
    """
    entries = _active_cron_entries(text)
    missing_commands: List[str] = []
    issues: List[str] = []
    schedules: Dict[str, Dict[str, bool]] = {}

    for command_name, expected_schedule in REQUIRED_SCHEDULES.items():
        matches = [entry for entry in entries if command_name in entry["command"]]
        present = bool(matches)
        cadence_matches = [entry for entry in matches if entry["schedule"] == expected_schedule]
        cadence_ok = bool(cadence_matches)
        nonblocking_flock = any(
            _NONBLOCKING_FLOCK_RE.search(entry["command"])
            for entry in cadence_matches
        )

        schedules[command_name] = {
            "present": present,
            "cadence_ok": cadence_ok,
            "nonblocking_flock": nonblocking_flock,
        }

        if not present:
            missing_commands.append(command_name)
            issues.append(f"{command_name}:missing_active_schedule")
            continue
        if not cadence_ok:
            issues.append(f"{command_name}:wrong_cadence")
            continue
        if not nonblocking_flock:
            issues.append(f"{command_name}:missing_nonblocking_flock")

    return {
        "healthy": not issues,
        "missing_commands": missing_commands,
        "issues": issues,
        "schedules": schedules,
    }


def main() -> int:
    health = get_dispatcher_health()
    try:
        result = subprocess.run(
            ["crontab", "-l"], capture_output=True, text=True, timeout=10, check=False
        )
        schedule = validate_schedule_text(result.stdout if result.returncode == 0 else "")
    except (OSError, subprocess.SubprocessError):
        schedule = validate_schedule_text("")
    report = {
        "healthy": bool(health.get("healthy")) and schedule["healthy"],
        "dispatcher_health": health,
        "schedule_health": schedule,
    }
    print(json.dumps(report, indent=2, sort_keys=True))
    return 0 if report["healthy"] else 1


if __name__ == "__main__":
    raise SystemExit(main())
