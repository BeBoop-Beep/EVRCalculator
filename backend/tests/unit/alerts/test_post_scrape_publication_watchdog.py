from datetime import datetime, timezone
from types import SimpleNamespace
from unittest.mock import patch

from backend.alerts import post_scrape_publication_watchdog as watchdog


NOW = datetime(2026, 9, 21, 0, 20, tzinfo=timezone.utc)
BATCH = {
    "id": 57,
    "market_date": "2026-09-20",
    "status": "complete",
    "promoted_at": "2026-09-20T23:21:43+00:00",
}


def _gate(allowed=True, reason_code="allowed_complete"):
    return SimpleNamespace(allowed=allowed, reason_code=reason_code)


def test_locked_publisher_with_recent_progress_is_healthy():
    with patch.object(watchdog, "_batch_gate_decision", return_value=_gate()):
        result = watchdog.run_watchdog(
            client=object(),
            now=NOW,
            stall_seconds=1200,
            queue_failures=False,
            latest_batch_loader=lambda _client: dict(BATCH),
            lock_checker=lambda _path: True,
            log_age_loader=lambda _path, _now: 45.0,
        )
    assert result["healthy"] is True
    assert result["status"] == "in_progress"


def test_locked_publisher_without_progress_is_stalled_and_never_relaunched():
    calls = []
    with patch.object(watchdog, "_batch_gate_decision", return_value=_gate()):
        result = watchdog.run_watchdog(
            client=object(),
            now=NOW,
            stall_seconds=1200,
            queue_failures=False,
            latest_batch_loader=lambda _client: dict(BATCH),
            lock_checker=lambda _path: True,
            log_age_loader=lambda _path, _now: 1800.0,
            trigger=lambda *_a, **_k: calls.append(True),
        )
    assert result["healthy"] is False
    assert result["failure_code"] == "publication_progress_stalled"
    assert calls == []


def test_missing_publisher_relaunches_through_existing_detached_trigger():
    calls = []
    def trigger(market_date):
        calls.append(market_date)
        return {"market_date": market_date, "status": "launch_requested", "pid": 123}
    with patch.object(watchdog, "_batch_gate_decision", return_value=_gate()):
        result = watchdog.run_watchdog(
            client=object(),
            now=NOW,
            queue_failures=False,
            latest_batch_loader=lambda _client: dict(BATCH),
            lock_checker=lambda _path: False,
            trigger=trigger,
        )
    assert calls == ["2026-09-20"]
    assert result["healthy"] is True
    assert result["status"] == "relaunch_requested"


def test_missing_publisher_currency_failure_is_unhealthy_not_success():
    with patch.object(watchdog, "_batch_gate_decision", return_value=_gate()):
        result = watchdog.run_watchdog(
            client=object(),
            now=NOW,
            queue_failures=False,
            latest_batch_loader=lambda _client: dict(BATCH),
            lock_checker=lambda _path: False,
            trigger=lambda market_date: {
                "market_date": market_date,
                "status": "currency_check_failed",
            },
        )
    assert result["healthy"] is False
    assert result["trigger"]["status"] == "currency_check_failed"


def test_gate_authority_failure_blocks_relaunch():
    calls = []
    with patch.object(
        watchdog,
        "_batch_gate_decision",
        return_value=_gate(False, "blocked_authority_unavailable"),
    ):
        result = watchdog.run_watchdog(
            client=object(),
            now=NOW,
            queue_failures=False,
            latest_batch_loader=lambda _client: dict(BATCH),
            lock_checker=lambda _path: False,
            trigger=lambda *_a, **_k: calls.append(True),
        )
    assert result["healthy"] is False
    assert result["failure_code"] == "blocked_authority_unavailable"
    assert calls == []
