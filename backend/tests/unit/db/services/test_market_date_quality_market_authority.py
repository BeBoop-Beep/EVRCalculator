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

    def limit(self, count):
        self.rows = self.rows[:count]
        return self

    def execute(self):
        return _Result(list(self.rows))


class _Client:
    def __init__(self, rows):
        self.rows = rows

    def table(self, name):
        return _Query(self.rows.get(name, []))


def _index_row(day: str, set_ids: list[str]):
    return {
        "tcg": "pokemon",
        "index_key": "raw",
        "market_date": day,
        "methodology_version": mdq.MARKET_INDEX_METHODOLOGY_VERSION,
        "constituents_json": [{"setId": set_id} for set_id in set_ids],
    }


def test_pre_cutover_quality_uses_exact_persisted_raw_basket(monkeypatch):
    client = _Client({mdq.INDEX_TABLE: [_index_row("2026-09-08", ["a", "b", "c"])]})

    def must_not_reconstruct(*_a, **_k):
        raise AssertionError("persisted historical basket must win over reconstructed eligibility")

    monkeypatch.setattr(mdq, "resolve_market_root_cohort", must_not_reconstruct)

    assert mdq.cohort_set_ids_for_date(client, "2026-09-08") == ["a", "b", "c"]


def test_pre_cutover_without_persisted_row_falls_back_to_frozen_staged_resolver(monkeypatch):
    client = _Client({mdq.INDEX_TABLE: []})
    seen = []

    def resolve(_client, *, market_date):
        seen.append(market_date)
        return [{"id": "legacy-a"}, {"id": "legacy-b"}]

    monkeypatch.setattr(mdq, "resolve_market_root_cohort", resolve)

    assert mdq.cohort_set_ids_for_date(client, "2026-09-08") == ["legacy-a", "legacy-b"]
    assert seen == ["2026-09-08"]


def test_post_cutover_quality_uses_current_market_root_authority_even_if_index_row_exists(monkeypatch):
    client = _Client({mdq.INDEX_TABLE: [_index_row("2026-09-09", ["old-only"])]})
    seen = []

    def resolve(_client, *, market_date):
        seen.append(market_date)
        return [{"id": "root-1"}, {"id": "root-2"}]

    monkeypatch.setattr(mdq, "resolve_market_root_cohort", resolve)

    assert mdq.cohort_set_ids_for_date(client, "2026-09-09") == ["root-1", "root-2"]
    assert seen == ["2026-09-09"]


def test_quality_contract_explicitly_rejects_simulation_as_requirement():
    result = mdq.classify_market_date(
        market_date="2026-09-09",
        cohort_set_ids={"a", "b"},
        qualifying_set_ids={"a", "b"},
        valuation_set_ids={"standard": {"a", "b"}, "top10": {"a", "b"}},
        has_later_accepted_date=False,
        legacy_allowlist=frozenset(),
    )

    assert result["status"] == mdq.STATUS_READY
    assert result["evidence"]["qualificationAuthority"] == "canonical_market_root_authority"
    assert result["evidence"]["simulationEligibilityRequired"] is False
