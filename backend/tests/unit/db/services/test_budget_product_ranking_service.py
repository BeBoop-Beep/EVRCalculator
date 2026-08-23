"""Contract: the INTERNAL budget-ranking reader.

Every read returns its authority alongside the rows, so a caller cannot
render a rank without knowing which market state and which budget produced
it. A bare, context-free "best product" read does not exist by design.
"""

from __future__ import annotations

from backend.calculations.evr.budget_normalized_product_ranking import (
    ALLOCATION_METHOD_VERSION,
    BUDGET_NORMALIZED_RANKING_METHOD_VERSION,
)
from backend.db.services.budget_product_ranking_service import (
    load_budget_ranking,
    load_full_market_ranking,
    load_latest_snapshot,
    load_product_budget_ranks,
)

SNAPSHOT = {
    "id": "snap-1",
    "market_date": "2026-08-21",
    "pinned_price_as_of": "2026-08-21",
    "ranking_method_version": BUDGET_NORMALIZED_RANKING_METHOD_VERSION,
    "allocation_method_version": ALLOCATION_METHOD_VERSION,
    "comparison_scope_version": "budget_constrained_whole_unit_cross_format_v1",
    "financial_rip_version": "financial_rip_v4_x",
    "overall_rip_version": "overall_rip_v10_x",
    "collector_appeal_version": "collector_appeal_v5_x",
    "eligible_cohort_count": 137,
    "cohort_fingerprint": "fp",
    "full_market_budget": 1350.0,
    "max_eligible_sku_price": 1331.19,
    "full_market_rounding_increment": 50.0,
    "full_market_rounding_rule_version": "full_market_next_50_above_max_eligible_sku_v1",
}


def _row(pid, budget, rank, budget_type="standard_band"):
    return {
        "sealed_product_id": pid, "snapshot_id": "snap-1", "target_budget": budget,
        "budget_type": budget_type, "budget_rank": rank, "budget_cohort_size": 2,
        "financial_only_rank": rank, "budget_tier": "B", "capital_utilization": 0.97,
    }


class _FakeClient:
    def __init__(self, tables):
        self.tables = tables
        self._name = None
        self._filters = {}
        self._limit = None

    def table(self, name):
        self._name, self._filters, self._limit = name, {}, None
        return self

    def select(self, *_a, **_k):
        return self

    def eq(self, column, value):
        self._filters[column] = value
        return self

    def order(self, _column):
        return self

    def limit(self, n):
        self._limit = n
        return self

    def execute(self):
        rows = list(self.tables.get(self._name, []))
        for column, value in self._filters.items():
            rows = [r for r in rows if str(r.get(column)) == str(value)]
        if self._limit is not None:
            rows = rows[: self._limit]
        return type("R", (), {"data": rows})()


def _client(rows=None, latest=True):
    return _FakeClient({
        "budget_product_ranking_latest": ([{
            "ranking_method_version": BUDGET_NORMALIZED_RANKING_METHOD_VERSION,
            "allocation_method_version": ALLOCATION_METHOD_VERSION,
            "snapshot_id": "snap-1", "market_date": "2026-08-21",
        }] if latest else []),
        "budget_product_ranking_snapshots": [SNAPSHOT],
        "budget_product_ranking_rows": rows or [],
    })


def test_latest_snapshot_resolves_through_the_latest_pointer():
    assert load_latest_snapshot(_client())["id"] == "snap-1"


def test_absent_publication_is_reported_not_raised():
    result = load_budget_ranking(_client(latest=False), 250.0)
    assert result["available"] is False
    assert result["reason"] == "no_published_snapshot"
    assert result["rows"] == []


def test_budget_ranking_returns_rows_with_their_authority():
    rows = [_row("a", 250.0, 1), _row("b", 250.0, 2)]
    result = load_budget_ranking(_client(rows), 250.0)
    assert result["available"] is True
    assert [r["sealed_product_id"] for r in result["rows"]] == ["a", "b"]
    assert result["cohortSize"] == 2
    authority = result["authority"]
    assert authority["pinnedPriceAsOf"] == "2026-08-21"
    assert authority["comparisonScopeVersion"] == "budget_constrained_whole_unit_cross_format_v1"
    assert authority["eligibleCohortCount"] == 137


def test_budget_ranking_is_scoped_to_the_requested_budget():
    rows = [_row("a", 250.0, 1), _row("b", 500.0, 1)]
    result = load_budget_ranking(_client(rows), 250.0)
    assert [r["sealed_product_id"] for r in result["rows"]] == ["a"]


def test_unknown_budget_reports_no_rows_rather_than_inventing_a_cohort():
    result = load_budget_ranking(_client([_row("a", 250.0, 1)]), 175.0)
    assert result["available"] is False
    assert result["reason"] == "no_rows_for_budget"
    assert result["cohortSize"] == 0


def test_full_market_budget_is_read_from_the_snapshot_not_hardcoded():
    """The anchor is dynamic; a hard-coded $1,350 would silently break the day
    the max SKU price crosses a rounding boundary."""
    rows = [_row("a", 1350.0, 1, budget_type="full_market")]
    result = load_full_market_ranking(_client(rows))
    assert result["available"] is True
    assert result["targetBudget"] == 1350.0
    assert result["budgetType"] == "full_market"


def test_product_ranks_span_every_budget_it_qualifies_for():
    rows = [_row("a", 250.0, 1), _row("a", 500.0, 3), _row("b", 250.0, 2)]
    result = load_product_budget_ranks(_client(rows), "a")
    assert result["available"] is True
    assert [r["target_budget"] for r in result["rows"]] == [250.0, 500.0]
    assert result["authority"]["snapshotId"] == "snap-1"


def test_product_absent_from_every_budget_is_reported_explicitly():
    result = load_product_budget_ranks(_client([_row("a", 250.0, 1)]), "zzz")
    assert result["available"] is False
    assert result["reason"] == "product_not_ranked_at_any_budget"


def test_reader_is_not_imported_by_any_public_surface():
    """Second lock. The tables grant nothing to anon/authenticated, but the
    reader must also stay out of public code paths."""
    from pathlib import Path
    backend = Path(__file__).resolve().parents[4]
    offenders = []
    for path in backend.rglob("*.py"):
        if "tests" in path.parts or path.name == "budget_product_ranking_service.py":
            continue
        source = path.read_text(encoding="utf-8", errors="ignore")
        if "budget_product_ranking_service" in source:
            offenders.append(path.name)
    assert not offenders, "internal budget reader referenced outside itself: %s" % offenders
