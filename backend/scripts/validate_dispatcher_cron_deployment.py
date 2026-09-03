"""Fail production deploy when the scrape dispatcher cron is misconfigured.

Root cause of the Sep 2-3, 2026 OOM incident (requirement P): the every-minute
cron ran ``backend/scripts/run_next_scrape_job.py`` — a long-running drain
worker whose own module docstring says it must run under the CALLER's flock —
WITHOUT any ``flock``. Overlapping dispatcher trees accumulated across minutes
and exhausted RAM+swap. Production has since been hand-patched to:

    * * * * * /usr/bin/flock -n /tmp/pokemon-scrape-dispatcher.lock -c \
    'cd /home/ubuntu/repos/EVRCalculator && .../python backend/scripts/run_next_scrape_job.py' \
    >> backend/logs/cron_dispatcher.log 2>&1

This script makes that hand patch the REQUIRED, validated, canonical
deployment shape: it FAILS (nonzero exit) unless the installed crontab has an
every-minute ``run_next_scrape_job.py`` entry protected by a non-blocking
``flock`` guard. It also FAILS if the legacy 1:00 PM
``build_pokemon_market_dashboard_snapshots.py --all`` dashboard rebuild
(requirement O — superseded by the immediate post-scrape publication trigger
plus the 6:00 AM fallback) is still present in the schedule.

Run in CI / on deploy as ``python -m backend.scripts.validate_dispatcher_cron_deployment``.
"""

from __future__ import annotations

import json
import re
import subprocess
from dataclasses import dataclass, field
from typing import Any, Dict, List


DISPATCHER_MODULE = "run_next_scrape_job.py"
LEGACY_DASHBOARD_REBUILD_MODULE = "build_pokemon_market_dashboard_snapshots.py"

# Every-minute schedule field: "* * * * *" (bare, no step/range trickery to
# detect here — production's canonical entry is exactly this).
_EVERY_MINUTE_RE = re.compile(r"^\*\s+\*\s+\*\s+\*\s+\*\s")

_COMMENT_OR_BLANK_RE = re.compile(r"^\s*(#.*)?$")


@dataclass
class DispatcherScheduleReport:
    healthy: bool
    dispatcher_lines_found: int = 0
    unlocked_dispatcher_lines: List[str] = field(default_factory=list)
    legacy_dashboard_rebuild_lines: List[str] = field(default_factory=list)
    reasons: List[str] = field(default_factory=list)

    def as_dict(self) -> Dict[str, Any]:
        return {
            "healthy": self.healthy,
            "dispatcher_lines_found": self.dispatcher_lines_found,
            "unlocked_dispatcher_lines": self.unlocked_dispatcher_lines,
            "legacy_dashboard_rebuild_lines": self.legacy_dashboard_rebuild_lines,
            "reasons": self.reasons,
        }


def validate_dispatcher_schedule_text(text: str) -> DispatcherScheduleReport:
    """Pure, testable validation of a crontab's text.

    A dispatcher line is REQUIRED to:
      1. be scheduled every minute (``* * * * *``), matching the documented
         production cadence, and
      2. contain ``flock -n`` guarding the invocation — the exact defect that
         caused the incident was this cron entry running WITHOUT it.

    A legacy 1:00 PM dashboard rebuild line referencing
    ``build_pokemon_market_dashboard_snapshots.py --all`` is REQUIRED to be
    absent (requirement O): that family is now owned end-to-end by the
    canonical post-scrape / 6:00 AM publication orchestrator.
    """
    reasons: List[str] = []
    unlocked: List[str] = []
    legacy: List[str] = []
    dispatcher_lines_found = 0
    every_minute_dispatcher_lines_found = 0

    for raw_line in text.splitlines():
        line = raw_line.strip()
        if _COMMENT_OR_BLANK_RE.match(line):
            continue
        if DISPATCHER_MODULE in line:
            dispatcher_lines_found += 1
            is_every_minute = bool(_EVERY_MINUTE_RE.match(line))
            if is_every_minute:
                every_minute_dispatcher_lines_found += 1
            has_flock = "flock -n" in line or "flock --nonblock" in line
            if is_every_minute and not has_flock:
                unlocked.append(raw_line)
        if LEGACY_DASHBOARD_REBUILD_MODULE in line and "--all" in line:
            legacy.append(raw_line)

    if dispatcher_lines_found == 0:
        reasons.append(
            f"no crontab entry found scheduling {DISPATCHER_MODULE}; "
            "the every-minute dispatcher is required for daily scraping"
        )
    elif every_minute_dispatcher_lines_found == 0:
        reasons.append(
            f"no every-minute crontab entry found scheduling {DISPATCHER_MODULE}; "
            "the canonical daily dispatcher cadence is '* * * * *'"
        )
    if unlocked:
        reasons.append(
            f"{len(unlocked)} every-minute {DISPATCHER_MODULE} entry(ies) missing "
            "'flock -n' — this is the exact Sep 2-3, 2026 OOM incident's root cause"
        )
    if legacy:
        reasons.append(
            f"{len(legacy)} legacy 1PM {LEGACY_DASHBOARD_REBUILD_MODULE} --all entry(ies) "
            "present; this family is owned by the canonical publication orchestrator now "
            "(requirement O) and must be removed from the schedule"
        )

    healthy = not reasons
    return DispatcherScheduleReport(
        healthy=healthy,
        dispatcher_lines_found=dispatcher_lines_found,
        unlocked_dispatcher_lines=unlocked,
        legacy_dashboard_rebuild_lines=legacy,
        reasons=reasons,
    )


def _read_installed_crontab() -> str:
    try:
        result = subprocess.run(
            ["crontab", "-l"], capture_output=True, text=True, timeout=10, check=False
        )
        return result.stdout if result.returncode == 0 else ""
    except (OSError, subprocess.SubprocessError):
        return ""


def main() -> int:
    text = _read_installed_crontab()
    report = validate_dispatcher_schedule_text(text)
    print(json.dumps(report.as_dict(), indent=2, sort_keys=True))
    return 0 if report.healthy else 1


if __name__ == "__main__":
    raise SystemExit(main())
