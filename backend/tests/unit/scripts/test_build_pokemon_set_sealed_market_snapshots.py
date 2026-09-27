from types import SimpleNamespace

import pytest

from backend.scripts.build_pokemon_set_sealed_market_snapshots import (
    SealedObservationReadIncomplete,
    _paged_rows,
)


def _row(day: int):
    return {
        "id": f"00000000-0000-0000-0000-{day:012d}",
        "captured_at": f"2026-09-{day:02d}",
    }


class _FakeQuery:
    def __init__(self, rows, counts, *, short_first=False):
        self.rows = rows
        self.counts = counts
        self.short_first = short_first
        self.calls = 0
        self.start = 0
        self.end = 0

    def range(self, start, end):
        self.start = start
        self.end = end
        return self

    def execute(self):
        count = self.counts[min(self.calls, len(self.counts) - 1)]
        self.calls += 1
        if self.short_first and self.start == 0:
            data = self.rows[:2]
        else:
            data = self.rows[self.start : self.end + 1]
        return SimpleNamespace(data=data, count=count)


def test_paged_rows_continues_after_short_page_until_exact_count():
    rows = [_row(day) for day in range(1, 8)]
    query = _FakeQuery(rows, [len(rows)], short_first=True)

    result = _paged_rows(lambda: query, page_size=4, max_rows=20)

    assert result == rows
    assert query.calls == 3


def test_paged_rows_fails_closed_when_exact_count_changes_mid_read():
    rows = [_row(day) for day in range(1, 8)]
    query = _FakeQuery(rows, [7, 8])

    with pytest.raises(
        SealedObservationReadIncomplete,
        match="sealed_observations_changed_during_pagination",
    ):
        _paged_rows(lambda: query, page_size=4, max_rows=20)


def test_paged_rows_rejects_duplicate_or_regressing_order():
    rows = [_row(1), _row(2), _row(2)]
    query = _FakeQuery(rows, [3])

    with pytest.raises(
        SealedObservationReadIncomplete,
        match="unordered_or_duplicate_sealed_observations",
    ):
        _paged_rows(lambda: query, page_size=3, max_rows=20)
