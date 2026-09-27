"""Sentinel checks for Market Explorer's bounded maintained-cache scheduler."""

from __future__ import annotations

import subprocess
from typing import Callable, Optional

from backend.sentinel.models import CheckResult, Severity
from backend.sentinel.registry import CheckContext

MARKET_EXPLORER_SCHEDULER_CHECK_KEY = "market_explorer.maintenance_scheduler"
MARKET_EXPLORER_SCHEDULER_AUTHORITY = "market-explorer-prewarm-cron-v1"

_BEGIN = "# BEGIN market-explorer-prewarm (managed by install_market_explorer_prewarm_cron.sh)"
_END = "# END market-explorer-prewarm"


def check_market_explorer_scheduler(
    context: CheckContext,
    *,
    crontab_loader: Optional[Callable[[], str]] = None,
) -> CheckResult:
    """Require exactly one bounded writer and one read-only health schedule."""
    if crontab_loader is None:
        def crontab_loader() -> str:
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

    text = crontab_loader()
    blocks = 0
    prewarm = 0
    health = 0
    bounded = 0
    in_block = False
    for raw in text.splitlines():
        line = raw.strip()
        if line == _BEGIN:
            blocks += 1
            in_block = True
            continue
        if line == _END:
            in_block = False
            continue
        if not in_block or not line or line.startswith("#"):
            continue
        if "run_market_explorer_prewarm_guarded.sh" in line:
            prewarm += 1
            if "/usr/bin/flock -n" in line:
                bounded += 1
        if "check_market_explorer_maintained_cache_health" in line:
            health += 1

    observed = {
        "managed_blocks": blocks,
        "prewarm_entries": prewarm,
        "health_entries": health,
        "bounded_prewarm_entries": bounded,
    }
    expected = {
        "managed_blocks": 1,
        "prewarm_entries": 1,
        "health_entries": 1,
        "bounded_prewarm_entries": 1,
    }
    if observed != expected:
        return CheckResult.failure(
            MARKET_EXPLORER_SCHEDULER_CHECK_KEY,
            failure_code="MARKET_EXPLORER_MAINTENANCE_SCHEDULE_MISSING",
            severity=Severity.CRITICAL,
            authority_identity=MARKET_EXPLORER_SCHEDULER_AUTHORITY,
            expected=expected,
            observed=observed,
            checked_at=context.now,
        )
    return CheckResult.healthy(
        MARKET_EXPLORER_SCHEDULER_CHECK_KEY,
        authority_identity=MARKET_EXPLORER_SCHEDULER_AUTHORITY,
        expected=expected,
        observed=observed,
        checked_at=context.now,
    )
