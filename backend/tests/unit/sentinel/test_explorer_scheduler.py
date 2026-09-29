from __future__ import annotations

from datetime import datetime, timezone

from backend.sentinel.checks.explorer import (
    MARKET_EXPLORER_PROGRESS_CHECK_KEY,
    MARKET_EXPLORER_SCHEDULER_AUTHORITY,
    MARKET_EXPLORER_SCHEDULER_CHECK_KEY,
    check_market_explorer_progress,
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
* * * * * /usr/bin/flock -n /tmp/market-explorer-prewarm-cron.lock -c 'bash /repo/infra/oracle/run_market_explorer_prewarm_guarded.sh'
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
        "minute_cadence_entries": 1,
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



def _health(*, v2_healthy=False, alerts=None, ready=10, maintained=37):
    return {
        "latest_approved_market_date": "2026-09-27",
        "maintained_count": maintained,
        "ready_and_current": ready,
        "v2": {
            "healthy": v2_healthy,
            "status": "CURRENT" if v2_healthy else "STALE",
            "reason": None if v2_healthy else "SURFACE_V2_PUBLICATION_LAG",
            "canonical_accepted_date": "2026-09-27",
            "surface_v2_date": "2026-09-27" if v2_healthy else "2026-09-26",
            "surface_lag_days": 0 if v2_healthy else 1,
            "maintained_cache_total": maintained,
            "maintained_cache_current": ready,
            "maintained_cache_not_current": maintained - ready,
        },
        "alerts": list(alerts or []),
    }


def test_explorer_progress_is_healthy_while_normal_worker_is_advancing():
    rows = [
        {"status": "ready", "computed_through": "2026-09-27", "updated_at": "2026-09-27T17:58:00+00:00"},
        {"status": "ready", "computed_through": "2026-09-26", "updated_at": "2026-09-27T17:59:00+00:00"},
    ]
    result = check_market_explorer_progress(
        CTX,
        client=object(),
        health_checker=lambda _client: _health(v2_healthy=False, ready=1, maintained=2),
        cache_rows_loader=lambda _client: rows,
    )
    assert result.outcome == CheckOutcome.HEALTHY
    assert result.check_key == MARKET_EXPLORER_PROGRESS_CHECK_KEY
    assert result.observed["state"] == "converging"
    assert result.observed["stale_maintained_count"] == 1


def test_explorer_progress_stalls_when_no_recent_worker_progress():
    rows = [
        {"status": "ready", "computed_through": "2026-09-26", "updated_at": "2026-09-27T17:00:00+00:00"},
    ]
    result = check_market_explorer_progress(
        CTX,
        client=object(),
        max_progress_age_seconds=600,
        health_checker=lambda _client: _health(v2_healthy=False, ready=0, maintained=1),
        cache_rows_loader=lambda _client: rows,
    )
    assert result.outcome == CheckOutcome.FAILURE
    assert result.failure_code == "MARKET_EXPLORER_CONVERGENCE_STALLED"
    assert result.severity == Severity.CRITICAL
    assert result.authority_identity == "2026-09-27"


def test_explorer_progress_stalls_immediately_on_failed_cache():
    rows = [
        {"status": "failed", "computed_through": "2026-09-26", "updated_at": "2026-09-27T17:59:00+00:00"},
    ]
    result = check_market_explorer_progress(
        CTX,
        client=object(),
        health_checker=lambda _client: _health(
            v2_healthy=False,
            ready=0,
            maintained=1,
            alerts=[{"reason": "failed", "fingerprint": "x"}],
        ),
        cache_rows_loader=lambda _client: rows,
    )
    assert result.outcome == CheckOutcome.FAILURE
    assert result.failure_code == "MARKET_EXPLORER_CONVERGENCE_STALLED"
