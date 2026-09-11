"""evaluate_market_date_quality must use the lightweight authority-only
resolver for Sep 10+, never the heavyweight metadata+certification resolver
(the production statement-timeout risk this pass removes)."""
from __future__ import annotations

from backend.db.services import market_date_quality as mdq


class _Result:
    def __init__(self, data):
        self.data = data


class _Query:
    def __init__(self, rows):
        self.rows = list(rows)

    def select(self, *_a, **_k):
        return self

    def eq(self, field, value):
        self.rows = [row for row in self.rows if str(row.get(field)) == str(value)]
        return self

    def in_(self, field, values):
        values = {str(v) for v in values}
        self.rows = [row for row in self.rows if str(row.get(field)) in values]
        return self

    def lte(self, field, value):
        self.rows = [row for row in self.rows if row.get(field) is not None and str(row[field])[:10] <= str(value)[:10]]
        return self

    def order(self, *_a, **_k):
        return self

    def limit(self, n):
        self.rows = self.rows[:n]
        return self

    def range(self, start, end):
        self.rows = self.rows[start:end + 1]
        return self

    def execute(self):
        return _Result(list(self.rows))


class _Client:
    def __init__(self, tables):
        self.tables = tables

    def table(self, name):
        return _Query(self.tables.get(name, []))


def _authority_rows(ids):
    return [
        {"set_id": set_id, "activated_market_date": "2026-09-10",
         "deactivated_market_date": None, "enabled": True}
        for set_id in ids
    ]


def test_evaluate_market_date_quality_never_calls_heavyweight_resolver(monkeypatch):
    ids = [f"22222222-0000-0000-0000-{i:012d}" for i in range(106)]
    client = _Client({
        mdq.INDEX_TABLE: [],
        "pokemon_market_root_authority": _authority_rows(ids),
        "pokemon_set_value_daily_history": [
            {"set_id": set_id, "snapshot_date": "2026-09-10", "set_value": 10,
             "priced_card_count": 5, "value_scope": scope}
            for set_id in ids for scope in ("standard", "top10")
        ],
    })

    def must_not_call_heavyweight(*_a, **_k):
        raise AssertionError("heavyweight resolve_market_root_cohort must not be called")

    monkeypatch.setattr(mdq, "resolve_market_root_cohort", must_not_call_heavyweight)

    result = mdq.evaluate_market_date_quality(client, "2026-09-10")
    assert result["cohortSetCount"] == 106
    assert result["status"] == mdq.STATUS_READY


def test_cohort_set_ids_for_date_sep10_uses_lightweight_resolver(monkeypatch):
    seen = {}

    def fake_lightweight(client, *, market_date=None):
        seen["market_date"] = market_date
        return ["a", "b", "c"]

    monkeypatch.setattr(mdq, "resolve_market_root_ids", fake_lightweight)
    client = _Client({mdq.INDEX_TABLE: []})

    result = mdq.cohort_set_ids_for_date(client, "2026-09-10")
    assert result == ["a", "b", "c"]
    assert seen["market_date"] == "2026-09-10"
