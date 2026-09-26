"""Item 2 (Best-Open promotion): harden `_fetch_all_ready_rows` against 57014.

Bucket 4's CI-runtime validation of Best-Open Price V2 observed this exact
read (`simulation_sealed_product_results`, the whole V4-ready table, not
scoped to one `price_as_of`) repeatedly hitting Postgres statement timeouts
(57014) mid-pagination, forcing whole-script `--resume` restarts. These tests
pin: multi-page completeness, isolated per-page retry-then-succeed, bounded
repeated-failure, permanent-error non-retry, stable ordering, and page-count
boundary conditions -- all deterministic, no real Supabase/Postgres involved.
"""

from __future__ import annotations

from typing import Any

import pytest
from postgrest.exceptions import APIError

from backend.db.services.budget_product_ranking_authority import (
    _PAGE_SIZE,
    _fetch_all_ready_rows,
)


def _row(pid: str) -> dict[str, Any]:
    return {
        "sealed_product_id": pid,
        "set_id": f"set-{pid}",
        "product_family": "booster_box",
        "product_name": f"Product {pid}",
        "pack_count": 36,
        "random_pack_count": 36,
        "guaranteed_component_count": 0,
        "guaranteed_component_market_value": None,
        "product_market_cost": 100.0,
        "price_as_of": "2026-09-01",
        "collector_appeal_score": 55.0,
        "collector_appeal_version": "collector_appeal_v5_contextual_roster_h_only_d_baseline_up4_down2",
        "calculation_run_id": "run-1",
        "financial_rip_v4_status": "ready",
        "financial_rip_v4_score": 40.0,
        "financial_rip_v4_version": "financial_rip_v4_outcome_profile_p95_only_25_20_15_25_10_5",
        "overall_rip_v10_score": 42.0,
        "overall_rip_v10_version": "overall_rip_v10_90_financial_v4_10_collector_appeal_v5",
        "accessory_value_included": False,
        "overall_rip_v12_score": 43.0,
        "overall_rip_v12_status": "ready",
        "overall_rip_v12_version": (
            "overall_rip_v12_86_financial_v4_04_chase_accessibility_v1_10_collector_appeal_v5"
        ),
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
    def __init__(self, client: "_PaginatingReadyRowsClient") -> None:
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
        if fault:
            remaining = fault
            if remaining[0] > 0:
                remaining[0] -= 1
                raise remaining[1]
        page = self._client.all_rows[start : end + 1]
        return type("R", (), {"data": list(page)})()


class _PaginatingReadyRowsClient:
    """Fake modelling paginated reads over `simulation_sealed_product_results`.

    ``faults`` maps a zero-based page index to ``[fail_count, exception]``:
    that page raises ``exception`` on its first ``fail_count`` attempts, then
    succeeds. This reproduces "one 57014 then success" and "repeated 57014"
    without ever touching a real database.
    """

    def __init__(self, rows: list[dict[str, Any]], faults: dict[int, list] | None = None) -> None:
        self.all_rows = rows
        self.faults = faults or {}
        self.calls: list[int] = []

    def table(self, _name: str) -> _FakeQuery:
        return _FakeQuery(self)


def test_multi_page_completeness_no_omissions_no_duplicates_stable_order():
    rows = [_row(f"p{i:04d}") for i in range(_PAGE_SIZE + 250)]
    client = _PaginatingReadyRowsClient(rows)

    result = _fetch_all_ready_rows(client)

    assert len(result) == len(rows)
    assert [r["sealed_product_id"] for r in result] == [r["sealed_product_id"] for r in rows]
    assert len({r["sealed_product_id"] for r in result}) == len(rows)


def test_one_statement_timeout_then_success_retries_only_the_failed_page():
    rows = [_row(f"p{i:04d}") for i in range(_PAGE_SIZE + 10)]
    # Page 1 (the second, partial page) fails once with 57014 then succeeds.
    client = _PaginatingReadyRowsClient(rows, faults={1: [1, _statement_timeout_error()]})

    result = _fetch_all_ready_rows(client)

    assert len(result) == len(rows)
    assert {r["sealed_product_id"] for r in result} == {r["sealed_product_id"] for r in rows}
    # Page 0 fetched exactly once; page 1 fetched twice (one failure + retry).
    assert client.calls.count(0) == 1
    assert client.calls.count(1) == 2


def test_repeated_statement_timeout_fails_bounded_not_infinite():
    rows = [_row(f"p{i:04d}") for i in range(_PAGE_SIZE + 10)]
    client = _PaginatingReadyRowsClient(rows, faults={1: [99, _statement_timeout_error()]})

    with pytest.raises(RuntimeError) as excinfo:
        _fetch_all_ready_rows(client)

    message = str(excinfo.value)
    assert "[1000, 1999]" in message
    assert "4 attempt" in message  # matches _FETCH_MAX_ATTEMPTS
    assert client.calls.count(1) == 4  # bounded, not infinite


def test_permanent_error_is_not_retried():
    rows = [_row("p0")]
    client = _PaginatingReadyRowsClient(rows, faults={0: [99, _permanent_error()]})

    with pytest.raises(APIError):
        _fetch_all_ready_rows(client)

    assert client.calls.count(0) == 1  # no retry attempted


def test_boundary_exactly_one_full_page():
    rows = [_row(f"p{i:04d}") for i in range(_PAGE_SIZE)]
    client = _PaginatingReadyRowsClient(rows)

    result = _fetch_all_ready_rows(client)

    assert len(result) == _PAGE_SIZE
    assert client.calls == [0, 1]  # must probe page 1 to confirm no more rows


def test_boundary_full_page_plus_one_row():
    rows = [_row(f"p{i:04d}") for i in range(_PAGE_SIZE + 1)]
    client = _PaginatingReadyRowsClient(rows)

    result = _fetch_all_ready_rows(client)

    assert len(result) == _PAGE_SIZE + 1
    assert client.calls == [0, 1]


def test_boundary_empty_result():
    client = _PaginatingReadyRowsClient([])

    result = _fetch_all_ready_rows(client)

    assert result == []
    assert client.calls == [0]
