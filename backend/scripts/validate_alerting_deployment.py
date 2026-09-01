"""Fail production deploy when alert delivery/watchdog scheduling is absent."""

from __future__ import annotations

import json
import subprocess
from typing import Any, Dict

from backend.alerts.dispatcher import get_dispatcher_health


REQUIRED_SCHEDULE_COMMANDS = (
    "backend.alerts.dispatcher",
    "backend.alerts.market_freshness_watchdog",
)


def validate_schedule_text(text: str) -> Dict[str, Any]:
    missing = [command for command in REQUIRED_SCHEDULE_COMMANDS if command not in text]
    return {"healthy": not missing, "missing_commands": missing}


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
