from __future__ import annotations

from datetime import datetime, timezone

from backend.sentinel.checks.explorer import (
    MARKET_EXPLORER_SCHEDULER_AUTHORITY,
    MARKET_EXPLORER_SCHEDULER_CHECK_KEY,
    check_market_explorer_scheduler,
)
from backend.sentinel.models import CheckOutcome, RunnerIdentity, Severity
from backend.sentinel.registry import CheckContext

CTX = CheckContext(
    now=datetime(2026, 9, 27, 18, 0, tzinfo=timezone.utc),
    runner_identity=RunnerIdentity(component="sentinel", host="test", build_sha="sha"),
)


def test_missing_explorer_schedule_is_critical():
    result = check_market_explorer_scheduler(CTX, crontab_loader=lambda: "")
    assert result.outcome == CheckOutcome.FAILURE
    assert result.severity == Severity.CRITICAL
    assert result.failure_code == "MARKET_EXPLORER_MAINTENANCE_SCHEDULE_MISSING"
    assert result.authority_identity == MARKET_EXPLORER_SCHEDULER_AUTHORITY


def test_exact_managed_explorer_schedule_is_healthy():
    text = """# BEGIN market-explorer-prewarm (managed by install_market_explorer_prewarm_cron.sh)
0-55/5 * * * * /usr/bin/flock -n /tmp/market-explorer-prewarm-cron.lock -c 'bash /repo/infra/oracle/run_market_explorer_prewarm_guarded.sh'
2-59/15 * * * * /usr/bin/flock -n /tmp/market-explorer-health.lock -c 'python -m backend.scripts.check_market_explorer_maintained_cache_health'
# END market-explorer-prewarm
"""
    result = check_market_explorer_scheduler(CTX, crontab_loader=lambda: text)
    assert result.outcome == CheckOutcome.HEALTHY
    assert result.check_key == MARKET_EXPLORER_SCHEDULER_CHECK_KEY
    assert result.observed == {
        "managed_blocks": 1,
        "prewarm_entries": 1,
        "health_entries": 1,
        "bounded_prewarm_entries": 1,
    }


def test_unbounded_or_duplicate_explorer_schedule_fails_closed():
    text = """# BEGIN market-explorer-prewarm (managed by install_market_explorer_prewarm_cron.sh)
0-55/5 * * * * bash /repo/infra/oracle/run_market_explorer_prewarm_guarded.sh
0-55/5 * * * * bash /repo/infra/oracle/run_market_explorer_prewarm_guarded.sh
2-59/15 * * * * python -m backend.scripts.check_market_explorer_maintained_cache_health
# END market-explorer-prewarm
"""
    result = check_market_explorer_scheduler(CTX, crontab_loader=lambda: text)
    assert result.outcome == CheckOutcome.FAILURE
