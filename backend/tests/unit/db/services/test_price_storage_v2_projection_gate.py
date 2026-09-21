from types import SimpleNamespace

import pytest

from backend.db.services import price_storage_v2_projection_gate as gate


class _Query:
    def __init__(self, rows):
        self.rows = list(rows)
        self.filters = {}

    def select(self, *_args):
        return self

    def eq(self, column, value):
        self.filters[column] = value
        return self

    def execute(self):
        rows = [
            row for row in self.rows
            if all(str(row.get(column)) == str(value) for column, value in self.filters.items())
        ]
        return SimpleNamespace(data=rows)


class _Client:
    def __init__(self, scrape_rows, queue_rows):
        self.scrape_rows = scrape_rows
        self.queue_rows = queue_rows

    def table(self, name):
        if name == "scrape_jobs":
            return _Query(self.scrape_rows)
        if name == "price_storage_v2_shadow_queue":
            return _Query(self.queue_rows)
        raise AssertionError(name)


def _scrape(set_id, completed_at):
    return {
        "set_id": set_id,
        "market_date": "2026-09-20",
        "status": "completed",
        "completed_at": completed_at,
    }


def _queue(set_id, *, status="complete", source_completed_at="2026-09-20T23:10:00+00:00", attempts=1):
    return {
        "set_id": set_id,
        "market_date": "2026-09-20",
        "status": status,
        "attempts": attempts,
        "source_completed_at": source_completed_at,
        "completed_at": "2026-09-20T23:11:00+00:00",
    }


def test_projection_ready_requires_every_completed_scrape_set():
    client = _Client(
        [_scrape("a", "2026-09-20T23:01:00+00:00"), _scrape("b", "2026-09-20T23:02:00+00:00")],
        [_queue("a"), _queue("b")],
    )
    result = gate.evaluate_price_projection_gate(client, "2026-09-20")
    assert result.ready is True
    assert result.expected_set_count == 2
    assert result.complete_set_count == 2


def test_pending_projection_blocks_publication():
    client = _Client(
        [_scrape("a", "2026-09-20T23:01:00+00:00"), _scrape("b", "2026-09-20T23:02:00+00:00")],
        [_queue("a"), _queue("b", status="pending")],
    )
    result = gate.evaluate_price_projection_gate(client, "2026-09-20")
    assert result.ready is False
    assert result.pending_set_ids == ["b"]


def test_complete_queue_row_for_older_scrape_attempt_is_not_ready():
    client = _Client(
        [_scrape("a", "2026-09-20T23:15:00+00:00")],
        [_queue("a", source_completed_at="2026-09-20T23:10:00+00:00")],
    )
    result = gate.evaluate_price_projection_gate(client, "2026-09-20")
    assert result.ready is False
    assert result.complete_set_count == 0
    assert result.stale_source_set_ids == ["a"]


def test_terminal_failed_projection_is_exposed():
    client = _Client(
        [_scrape("a", "2026-09-20T23:01:00+00:00")],
        [_queue("a", status="failed", attempts=5)],
    )
    result = gate.evaluate_price_projection_gate(client, "2026-09-20")
    assert result.ready is False
    assert result.failed_set_ids == ["a"]
    assert result.terminal_failed_set_ids == ["a"]


def test_authority_read_error_fails_closed():
    class Broken:
        def table(self, _name):
            raise RuntimeError("db unavailable")
    result = gate.evaluate_price_projection_gate(Broken(), "2026-09-20")
    assert result.ready is False
    assert result.reason_code == gate.REASON_AUTHORITY_UNAVAILABLE


class _Transient57014(Exception):
    code = "57014"


class _DeterministicSqlError(Exception):
    code = "42P01"


class _RpcCall:
    def __init__(self, *, error=None, data=None):
        self.error = error
        self.data = data

    def execute(self):
        if self.error is not None:
            raise self.error
        return SimpleNamespace(data=self.data)


class _RpcClient:
    def __init__(self, *, expected_rpc, error=None, data=None):
        self.expected_rpc = expected_rpc
        self.error = error
        self.data = data

    def rpc(self, name, params):
        assert name == self.expected_rpc
        return _RpcCall(error=self.error, data=self.data)


def _decision(*, ready=False):
    return gate.PriceProjectionDecision(
        ready=ready,
        market_date="2026-09-21",
        reason_code=gate.REASON_READY if ready else gate.REASON_NOT_READY,
        expected_set_count=167,
        complete_set_count=167 if ready else 0,
    )


def test_process_rpc_retries_transient_57014_with_fresh_client(monkeypatch):
    readiness = iter([_decision(ready=False), _decision(ready=True)])
    monkeypatch.setattr(
        gate,
        "evaluate_price_projection_gate",
        lambda _client, _day: next(readiness),
    )
    clients = [
        _RpcClient(
            expected_rpc="enqueue_price_storage_v2_completed_scrape_jobs",
            data={"queued": 167},
        ),
        _RpcClient(
            expected_rpc="process_price_storage_v2_shadow_queue",
            error=_Transient57014("canceling statement due to statement timeout"),
        ),
        _RpcClient(
            expected_rpc="process_price_storage_v2_shadow_queue",
            data={"processed": 20},
        ),
    ]
    state = {"index": 0}

    def factory():
        client = clients[state["index"]]
        state["index"] += 1
        return client

    result = gate.advance_price_projection_once(
        object(),
        "2026-09-21",
        process_limit=20,
        client_factory=factory,
    )

    assert state["index"] == 3
    assert result["process_result"] == {"processed": 20}
    assert result["after"]["ready"] is True


def test_deterministic_process_failure_is_not_retried(monkeypatch):
    monkeypatch.setattr(
        gate,
        "evaluate_price_projection_gate",
        lambda _client, _day: _decision(ready=False),
    )
    clients = [
        _RpcClient(
            expected_rpc="enqueue_price_storage_v2_completed_scrape_jobs",
            data={"queued": 167},
        ),
        _RpcClient(
            expected_rpc="process_price_storage_v2_shadow_queue",
            error=_DeterministicSqlError("relation does not exist"),
        ),
    ]
    state = {"index": 0}

    def factory():
        client = clients[state["index"]]
        state["index"] += 1
        return client

    with pytest.raises(_DeterministicSqlError):
        gate.advance_price_projection_once(
            object(),
            "2026-09-21",
            process_limit=20,
            client_factory=factory,
        )

    assert state["index"] == 2
