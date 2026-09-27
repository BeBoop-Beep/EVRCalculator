from datetime import datetime, timezone

import pytest

from backend.pricing_pipeline import budget_v2 as b
from backend.pricing_pipeline.contracts import PipelineError

NOW = datetime(2026, 9, 24, 21, 0, tzinfo=timezone.utc)
KEYSET = b.keyset_identity("PRODUCTION", "App-PRD-test")


class ReadTimeout(Exception):
    pass


class _Query:
    def __init__(self, client):
        self.client = client

    def select(self, *_args): return self
    def eq(self, *_args): return self
    def order(self, *_args, **_kwargs): return self
    def limit(self, *_args): return self

    def execute(self):
        self.client.read_calls += 1
        if self.client.read_calls <= self.client.read_failures:
            raise ReadTimeout("The read operation timed out")
        return type("Result", (), {"data": self.client.rows})()


class _Rpc:
    def __init__(self, client):
        self.client = client

    def execute(self):
        self.client.rpc_calls += 1
        if self.client.rpc_calls <= self.client.rpc_failures:
            raise ReadTimeout("The read operation timed out")
        return type("Result", (), {"data": None})()


class _Client:
    def __init__(self, *, rows=None, read_failures=0, rpc_failures=0):
        self.rows = rows or []
        self.read_failures = read_failures
        self.rpc_failures = rpc_failures
        self.read_calls = 0
        self.rpc_calls = 0

    def table(self, _name):
        return _Query(self)

    def rpc(self, _name, _params):
        return _Rpc(self)


def _window():
    return {
        "provider_window_start": "2026-09-24T07:00:00+00:00",
        "provider_window_end": "2026-09-25T07:00:00+00:00",
        "usable_limit": 4500,
        "requests_reserved": 700,
    }


def test_budget_window_retries_httpx_style_read_timeout_then_succeeds():
    client = _Client(rows=[_window()], read_failures=2)
    delays = []
    ledger = b.PoolLedger(client, KEYSET, b.STANDARD)

    row = ledger.window(NOW, sleep=delays.append)

    assert row["requests_reserved"] == 700
    assert client.read_calls == 3
    assert delays == [1.5, 3.0]


def test_budget_window_persistent_read_timeout_fails_closed():
    client = _Client(rows=[_window()], read_failures=99)
    ledger = b.PoolLedger(client, KEYSET, b.STANDARD)

    with pytest.raises(PipelineError) as exc:
        ledger.window(NOW, sleep=lambda _seconds: None)

    assert exc.value.code == "BUDGET_AUTHORITY_UNAVAILABLE"
    assert client.read_calls == b.DB_RETRY_ATTEMPTS


def test_reservation_retries_httpx_style_read_timeout():
    client = _Client(rpc_failures=2)
    delays = []

    b.PoolLedger(client, KEYSET, b.STANDARD).reserve(sleep=delays.append)

    assert client.rpc_calls == 3
    assert delays == [1.5, 3.0]


def test_transient_classifier_does_not_retry_policy_decisions():
    assert b._is_transient_db_error(ReadTimeout("The read operation timed out"))
    assert b._is_transient_db_error(Exception("57014 statement timeout"))
    assert not b._is_transient_db_error(Exception("EBAY_BUDGET_EXHAUSTED"))
    assert not b._is_transient_db_error(Exception("permission denied"))
