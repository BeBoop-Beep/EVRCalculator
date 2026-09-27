"""Sentinel runtime scheduler contract.

This check is intentionally usable by both the normal Fast profile and the
GitHub Actions VM backstop. If the VM's application crontab loses Sentinel,
the independent scheduler can still run Fast once and let recovery reinstall
the canonical managed block.
"""
from __future__ import annotations

import subprocess
from typing import Callable, Optional

from backend.sentinel.models import CheckResult, Severity
from backend.sentinel.registry import CheckContext

SENTINEL_SCHEDULER_CHECK_KEY = "sentinel.runtime_scheduler"
SENTINEL_SCHEDULER_AUTHORITY = "sentinel-runtime-cron-v1"

_BEGIN = "# BEGIN sentinel-runtime (managed by install_sentinel_cron.sh)"
_END = "# END sentinel-runtime"


def check_sentinel_scheduler(
    context: CheckContext,
    *,
    crontab_loader: Optional[Callable[[], str]] = None,
) -> CheckResult:
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
    blocks = fast = public = audit = dispatcher = freshness = 0
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
        fast += int("backend.sentinel.operational --profile fast" in line)
        public += int("backend.sentinel.operational --profile public" in line)
        audit += int("backend.sentinel.operational --profile audit" in line)
        dispatcher += int("backend.alerts.dispatcher" in line)
        freshness += int("backend.alerts.market_freshness_watchdog" in line)

    observed = {
        "managed_blocks": blocks,
        "fast_entries": fast,
        "public_entries": public,
        "audit_entries": audit,
        "dispatcher_entries": dispatcher,
        "freshness_entries": freshness,
    }
    expected = {
        "managed_blocks": 1,
        "fast_entries": 1,
        "public_entries": 1,
        "audit_entries": 1,
        "dispatcher_entries": 1,
        "freshness_entries": 1,
    }
    if observed != expected:
        return CheckResult.failure(
            SENTINEL_SCHEDULER_CHECK_KEY,
            failure_code="SENTINEL_RUNTIME_SCHEDULE_MISSING",
            severity=Severity.CRITICAL,
            authority_identity=SENTINEL_SCHEDULER_AUTHORITY,
            expected=expected,
            observed=observed,
            checked_at=context.now,
        )
    return CheckResult.healthy(
        SENTINEL_SCHEDULER_CHECK_KEY,
        authority_identity=SENTINEL_SCHEDULER_AUTHORITY,
        expected=expected,
        observed=observed,
        checked_at=context.now,
    )
