from datetime import datetime, timezone
from types import SimpleNamespace
from unittest.mock import patch

import pytest

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


@pytest.fixture(autouse=True)
def _projection_ready(monkeypatch):
    monkeypatch.setattr(
        watchdog,
        "evaluate_price_projection_gate",
        lambda _client, market_date: SimpleNamespace(
            ready=True,
            reason_code="price_projection_ready",
            to_dict=lambda: {"ready": True, "market_date": market_date},
        ),
    )


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



def test_projection_lag_advances_one_chunk_and_waits_without_launch():
    projection = SimpleNamespace(
        ready=False,
        reason_code="price_projection_not_ready",
        to_dict=lambda: {
            "ready": False,
            "expected_set_count": 165,
            "complete_set_count": 100,
            "terminal_failed_set_count": 0,
        },
    )
    trigger_calls = []
    advance_calls = []

    def advance(_client, market_date, *, process_limit):
        advance_calls.append((market_date, process_limit))
        return {
            "after": {
                "ready": False,
                "expected_set_count": 165,
                "complete_set_count": 120,
                "terminal_failed_set_count": 0,
            }
        }

    with patch.object(watchdog, "_batch_gate_decision", return_value=_gate()):
        result = watchdog.run_watchdog(
            client=object(),
            now=NOW,
            queue_failures=False,
            latest_batch_loader=lambda _client: dict(BATCH),
            lock_checker=lambda _path: False,
            trigger=lambda *_a, **_k: trigger_calls.append(True),
            projection_checker=lambda _client, _date: projection,
            projection_advancer=advance,
        )

    assert result["healthy"] is True
    assert result["status"] == "price_projection_advancing"
    assert advance_calls == [("2026-09-20", 20)]
    assert trigger_calls == []


def test_projection_becomes_ready_after_advance_then_can_launch():
    projection = SimpleNamespace(
        ready=False,
        reason_code="price_projection_not_ready",
        to_dict=lambda: {
            "ready": False,
            "expected_set_count": 165,
            "complete_set_count": 160,
            "terminal_failed_set_count": 0,
        },
    )
    with patch.object(watchdog, "_batch_gate_decision", return_value=_gate()):
        result = watchdog.run_watchdog(
            client=object(),
            now=NOW,
            queue_failures=False,
            latest_batch_loader=lambda _client: dict(BATCH),
            lock_checker=lambda _path: False,
            projection_checker=lambda _client, _date: projection,
            projection_advancer=lambda *_a, **_k: {
                "after": {
                    "ready": True,
                    "expected_set_count": 165,
                    "complete_set_count": 165,
                    "terminal_failed_set_count": 0,
                }
            },
            trigger=lambda market_date: {
                "market_date": market_date,
                "status": "launch_requested",
                "pid": 123,
            },
        )
    assert result["healthy"] is True
    assert result["status"] == "relaunch_requested"


def test_terminal_projection_failure_never_launches():
    projection = SimpleNamespace(
        ready=False,
        reason_code="price_projection_not_ready",
        to_dict=lambda: {
            "ready": False,
            "expected_set_count": 165,
            "complete_set_count": 164,
            "terminal_failed_set_count": 1,
            "terminal_failed_set_ids": ["set-bad"],
        },
    )
    trigger_calls = []
    with patch.object(watchdog, "_batch_gate_decision", return_value=_gate()):
        result = watchdog.run_watchdog(
            client=object(),
            now=NOW,
            queue_failures=False,
            latest_batch_loader=lambda _client: dict(BATCH),
            lock_checker=lambda _path: False,
            trigger=lambda *_a, **_k: trigger_calls.append(True),
            projection_checker=lambda _client, _date: projection,
        )
    assert result["healthy"] is False
    assert result["status"] == "price_projection_terminal_failure"
    assert trigger_calls == []



class _Transient522(Exception):
    code = 522


class _DeterministicRelationError(Exception):
    code = "42P01"


class _BatchResult:
    def __init__(self, client):
        self.client = client

    def execute(self):
        if self.client.error is not None:
            raise self.client.error
        return SimpleNamespace(data=[dict(BATCH)])


class _BatchQuery:
    def __init__(self, client):
        self.client = client

    def select(self, *_args):
        return self

    def eq(self, *_args):
        return self

    def order(self, *_args, **_kwargs):
        return self

    def limit(self, *_args):
        return self

    def execute(self):
        return _BatchResult(self.client).execute()


class _BatchClient:
    def __init__(self, error=None):
        self.error = error

    def table(self, name):
        assert name == "pokemon_scrape_batches"
        return _BatchQuery(self)


def test_latest_complete_batch_retries_transient_authority_failure_with_fresh_client():
    clients = [
        _BatchClient(_Transient522("Cloudflare 522 connection timed out")),
        _BatchClient(),
    ]
    calls = {"n": 0}

    def factory():
        client = clients[calls["n"]]
        calls["n"] += 1
        return client

    result = watchdog._latest_complete_batch(
        object(),
        client_factory=factory,
        sleep=lambda _seconds: None,
    )

    assert calls["n"] == 2
    assert result["id"] == BATCH["id"]
    assert result["market_date"] == BATCH["market_date"]


def test_latest_complete_batch_does_not_retry_deterministic_authority_failure():
    calls = {"n": 0}

    def factory():
        calls["n"] += 1
        return _BatchClient(_DeterministicRelationError("relation does not exist"))

    with pytest.raises(_DeterministicRelationError):
        watchdog._latest_complete_batch(
            object(),
            client_factory=factory,
            sleep=lambda _seconds: None,
        )

    assert calls["n"] == 1
