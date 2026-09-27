"""Item 2 (Best-Open promotion): harden `_fetch_source_rows` against 57014.

Bucket 4's CI-runtime validation of Best-Open Price V2 observed the
`budget_product_ranking_rows` source load repeatedly hitting Postgres
statement timeouts (57014) mid-pagination, forcing whole-script `--resume`
restarts (see docs/research/BEST_OPEN_PRICE_V2_CI_RUNTIME_VALIDATION.md,
Phase 4). These tests pin: multi-page completeness, isolated per-page
retry-then-succeed, bounded repeated-failure, permanent-error non-retry,
stable ordering, and page-count boundary conditions -- deterministic, no
real Supabase/Postgres involved.
"""

from __future__ import annotations

from typing import Any

import pytest
from postgrest.exceptions import APIError

from backend.scripts.research_best_open_price_bucket0 import _PAGE_SIZE, _fetch_source_rows

SNAPSHOT_ID = "snap-1"


def _row(pid: str, rank: int) -> dict[str, Any]:
    return {
        "sealed_product_id": pid,
        "snapshot_id": SNAPSHOT_ID,
        "target_budget": 1300.0,
        "budget_type": "full_market",
        "budget_rank_v12": rank,
        "set_id": f"set-{pid}",
        "source_calculation_run_id": "run-1",
        "product_market_price": 100.0,
        "chase_accessibility_raw": 0.5,
    }


def _statement_timeout_error() -> APIError:
    return APIError(
        {"message": "canceling statement due to statement timeout", "code": "57014", "hint": None, "details": None}
    )


def _permanent_error() -> APIError:
    return APIError(
        {"message": 'column "bogus" does not exist', "code": "42703", "hint": None, "details": None}
    )


class _FakeQuery:
    def __init__(self, client: "_PaginatingSourceRowsClient") -> None:
        self._client = client
        self._range: tuple[int, int] | None = None

    def table(self, _name: str) -> "_FakeQuery":
        return self

    def select(self, *_a: Any, **_k: Any) -> "_FakeQuery":
        return self

    def eq(self, _column: str, _value: Any) -> "_FakeQuery":
        return self

    def order(self, _column: str, desc: bool = False) -> "_FakeQuery":
        return self

    def range(self, start: int, end: int) -> "_FakeQuery":
        self._range = (start, end)
        return self

    def execute(self) -> Any:
        assert self._range is not None
        start, end = self._range
        page_index = start // _PAGE_SIZE
        self._client.calls.append(page_index)
        fault = self._client.faults.get(page_index)
        if fault and fault[0] > 0:
            fault[0] -= 1
            raise fault[1]
        page = self._client.all_rows[start : end + 1]
        return type("R", (), {"data": list(page)})()


class _PaginatingSourceRowsClient:
    """Fake modelling paginated reads over `budget_product_ranking_rows`.

    ``faults`` maps a zero-based page index to ``[fail_count, exception]``.
    """

    def __init__(self, rows: list[dict[str, Any]], faults: dict[int, list] | None = None) -> None:
        self.all_rows = rows
        self.faults = faults or {}
        self.calls: list[int] = []

    def table(self, _name: str) -> _FakeQuery:
        return _FakeQuery(self)


class _NonPaginatingFakeClient:
    """Unit-fake without range()/order() support: single unbounded read."""

    def __init__(self, rows: list[dict[str, Any]]) -> None:
        self._rows = rows

    def table(self, _name: str) -> "_NonPaginatingFakeClient":
        return self

    def select(self, *_a: Any, **_k: Any) -> "_NonPaginatingFakeClient":
        return self

    def eq(self, _column: str, _value: Any) -> "_NonPaginatingFakeClient":
        return self

    def order(self, _column: str, desc: bool = False) -> "_NonPaginatingFakeClient":
        return self

    def execute(self) -> Any:
        return type("R", (), {"data": list(self._rows)})()


def test_multi_page_completeness_no_omissions_no_duplicates_stable_order():
    rows = [_row(f"p{i:04d}", i) for i in range(_PAGE_SIZE + 250)]
    client = _PaginatingSourceRowsClient(rows)

    result = _fetch_source_rows(client, SNAPSHOT_ID)

    assert len(result) == len(rows)
    assert [r["sealed_product_id"] for r in result] == [r["sealed_product_id"] for r in rows]
    assert len({r["sealed_product_id"] for r in result}) == len(rows)


def test_one_statement_timeout_then_success_retries_only_the_failed_page():
    rows = [_row(f"p{i:04d}", i) for i in range(_PAGE_SIZE + 10)]
    client = _PaginatingSourceRowsClient(rows, faults={1: [1, _statement_timeout_error()]})

    result = _fetch_source_rows(client, SNAPSHOT_ID)

    assert len(result) == len(rows)
    assert client.calls.count(0) == 1
    assert client.calls.count(1) == 2


def test_repeated_statement_timeout_fails_bounded_not_infinite():
    rows = [_row(f"p{i:04d}", i) for i in range(_PAGE_SIZE + 10)]
    client = _PaginatingSourceRowsClient(rows, faults={1: [99, _statement_timeout_error()]})

    with pytest.raises(RuntimeError) as excinfo:
        _fetch_source_rows(client, SNAPSHOT_ID)

    message = str(excinfo.value)
    assert "[1000, 1999]" in message
    assert "4 attempt" in message
    assert client.calls.count(1) == 4


def test_permanent_error_is_not_retried():
    rows = [_row("p0", 1)]
    client = _PaginatingSourceRowsClient(rows, faults={0: [99, _permanent_error()]})

    with pytest.raises(APIError):
        _fetch_source_rows(client, SNAPSHOT_ID)

    assert client.calls.count(0) == 1


def test_boundary_exactly_one_full_page():
    rows = [_row(f"p{i:04d}", i) for i in range(_PAGE_SIZE)]
    client = _PaginatingSourceRowsClient(rows)

    result = _fetch_source_rows(client, SNAPSHOT_ID)

    assert len(result) == _PAGE_SIZE
    assert client.calls == [0, 1]


def test_boundary_full_page_plus_one_row():
    rows = [_row(f"p{i:04d}", i) for i in range(_PAGE_SIZE + 1)]
    client = _PaginatingSourceRowsClient(rows)

    result = _fetch_source_rows(client, SNAPSHOT_ID)

    assert len(result) == _PAGE_SIZE + 1
    assert client.calls == [0, 1]


def test_boundary_empty_result():
    client = _PaginatingSourceRowsClient([])

    result = _fetch_source_rows(client, SNAPSHOT_ID)

    assert result == []
    assert client.calls == [0]


def test_non_paginating_client_still_returns_single_read_unchanged():
    """Unit fakes without range()/order() keep their pre-hardening behaviour."""
    rows = [_row("p0", 1), _row("p1", 2)]
    client = _NonPaginatingFakeClient(rows)

    result = _fetch_source_rows(client, SNAPSHOT_ID)

    assert result == rows
