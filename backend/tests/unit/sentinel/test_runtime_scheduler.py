from datetime import datetime, timezone

from backend.sentinel.checks.runtime_scheduler import (
    SENTINEL_SCHEDULER_AUTHORITY,
    SENTINEL_SCHEDULER_CHECK_KEY,
    check_sentinel_scheduler,
)
from backend.sentinel.models import CheckOutcome, RunnerIdentity, Severity
from backend.sentinel.registry import CheckContext

CTX = CheckContext(
    now=datetime(2026, 9, 27, 23, 0, tzinfo=timezone.utc),
    runner_identity=RunnerIdentity(component="sentinel_vm", host="test", build_sha="sha"),
)


def _managed_block() -> str:
    return """# BEGIN sentinel-runtime (managed by install_sentinel_cron.sh)
* * * * * /usr/bin/flock -n /tmp/index-alert-dispatcher.lock -c 'python -m backend.alerts.dispatcher'
*/5 * * * * /usr/bin/flock -n /tmp/index-market-freshness-watchdog.lock -c 'python -m backend.alerts.market_freshness_watchdog'
1-59/5 * * * * /usr/bin/flock -n /tmp/index-sentinel-fast.lock -c 'python -m backend.sentinel.operational --profile fast'
4-59/10 * * * * /usr/bin/flock -n /tmp/index-sentinel-public.lock -c 'python -m backend.sentinel.operational --profile public'
30 6,9,12,15,18 * * * /usr/bin/flock -n /tmp/index-sentinel-audit.lock -c 'python -m backend.sentinel.operational --profile audit'
# END sentinel-runtime
"""


def test_missing_sentinel_runtime_schedule_is_critical():
    result = check_sentinel_scheduler(CTX, crontab_loader=lambda: "")
    assert result.outcome == CheckOutcome.FAILURE
    assert result.severity == Severity.CRITICAL
    assert result.failure_code == "SENTINEL_RUNTIME_SCHEDULE_MISSING"
    assert result.authority_identity == SENTINEL_SCHEDULER_AUTHORITY


def test_exact_sentinel_runtime_schedule_is_healthy():
    result = check_sentinel_scheduler(CTX, crontab_loader=_managed_block)
    assert result.outcome == CheckOutcome.HEALTHY
    assert result.check_key == SENTINEL_SCHEDULER_CHECK_KEY
    assert result.observed == {
        "managed_blocks": 1,
        "fast_entries": 1,
        "public_entries": 1,
        "audit_entries": 1,
        "dispatcher_entries": 1,
        "freshness_entries": 1,
    }


def test_partial_or_unmanaged_runtime_schedule_fails_closed():
    text = "1-59/5 * * * * python -m backend.sentinel.operational --profile fast\n"
    result = check_sentinel_scheduler(CTX, crontab_loader=lambda: text)
    assert result.outcome == CheckOutcome.FAILURE


def test_missing_audit_entry_fails_runtime_schedule_contract():
    text = _managed_block().replace(
        "30 6,9,12,15,18 * * * /usr/bin/flock -n /tmp/index-sentinel-audit.lock -c 'python -m backend.sentinel.operational --profile audit'\n",
        "",
    )
    result = check_sentinel_scheduler(CTX, crontab_loader=lambda: text)
    assert result.outcome == CheckOutcome.FAILURE
    assert result.failure_code == "SENTINEL_RUNTIME_SCHEDULE_MISSING"
    assert result.observed["audit_entries"] == 0
