from copy import deepcopy

from backend.scripts.repair_chaos_rising_hits_history import (
    CHAOS_RISING_SET_ID,
    REPAIR_SOURCE,
    REPLACEMENT_VALUE,
    TARGET_DATES,
    apply_repair_plan,
    build_repair_plan,
)


class _Result:
    def __init__(self, data):
        self.data = data


class _UpdateQuery:
    def __init__(self, rows, updates, writes):
        self.rows = rows
        self.updates = updates
        self.writes = writes
        self.filters = []

    def eq(self, field, value):
        self.filters.append((field, value))
        return self

    def execute(self):
        matches = [row for row in self.rows if all(str(row.get(field)) == str(value) for field, value in self.filters)]
        for row in matches:
            row.update(self.updates)
        self.writes.extend(row.get("id") for row in matches)
        return _Result(deepcopy(matches))


class _Table:
    def __init__(self, rows, writes):
        self.rows = rows
        self.writes = writes

    def update(self, updates):
        return _UpdateQuery(self.rows, updates, self.writes)


class _Client:
    def __init__(self, rows):
        self.rows = rows
        self.writes = []

    def table(self, _name):
        return _Table(self.rows, self.writes)


def _fixture_rows():
    targeted = [
        {
            "id": f"target-{index}",
            "set_id": CHAOS_RISING_SET_ID,
            "snapshot_date": date_key,
            "value_scope": "hits",
            "set_value": 118137.48,
            "source": "old-source",
            "priced_card_count": 34,
        }
        for index, date_key in enumerate(TARGET_DATES)
    ]
    unrelated = [
        {"id": "other-date", "set_id": CHAOS_RISING_SET_ID, "snapshot_date": "2026-06-20", "value_scope": "hits", "set_value": 968.34, "source": "observed"},
        {"id": "other-scope", "set_id": CHAOS_RISING_SET_ID, "snapshot_date": "2026-06-16", "value_scope": "standard", "set_value": 1097.57, "source": "observed"},
        {"id": "other-set", "set_id": "another-set", "snapshot_date": "2026-06-16", "value_scope": "hits", "set_value": 50.0, "source": "observed"},
    ]
    return targeted, unrelated


def test_dry_run_does_not_write():
    targeted, _ = _fixture_rows()
    client = _Client(targeted)
    plan = build_repair_plan(targeted)

    assert apply_repair_plan(client, plan, commit=False) == 0
    assert client.writes == []
    assert all(row["set_value"] == 118137.48 for row in targeted)


def test_commit_changes_exactly_four_rows_and_is_idempotent():
    targeted, unrelated = _fixture_rows()
    all_rows = targeted + unrelated
    client = _Client(all_rows)

    first_plan = build_repair_plan(targeted)
    assert apply_repair_plan(client, first_plan, commit=True) == 4
    assert len(client.writes) == 4
    assert all(row["set_value"] == REPLACEMENT_VALUE for row in targeted)
    assert all(row["source"] == REPAIR_SOURCE for row in targeted)
    assert [row["set_value"] for row in unrelated] == [968.34, 1097.57, 50.0]

    second_plan = build_repair_plan(targeted)
    assert apply_repair_plan(client, second_plan, commit=True) == 0
    assert len(client.writes) == 4
