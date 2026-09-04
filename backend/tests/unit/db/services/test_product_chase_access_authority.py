"""Chase Access at Budget - authority coherence + Phase 13 no-N+1 performance.

Uses a fake fluent Supabase-style client (same convention as
``test_budget_product_ranking_authority.py``) capable of serving BOTH tables
this orchestration reads: the Chase Accessibility snapshot table (batched
cohort read) and ``simulation_card_variant_pull_rates`` (batched per-run
variant universe read). Call counts on each table are asserted directly -
this is the actual N+1 regression guard, not a description of one.
"""

from __future__ import annotations

from collections import defaultdict

import pytest

from backend.db.services.chase_accessibility_service import SNAPSHOT_TABLE, PULL_RATES_TABLE
from backend.db.services.product_chase_access_authority import (
    resolve_product_chase_access,
)
from backend.desirability.chase_accessibility import CHASE_ACCESSIBILITY_VERSION

CHASE_DEPTH_VERSION = "chase_depth_v1_hc_effective_count"


def _snapshot_row(set_id, run_id, accessibility=0.08, mass=0.995):
    return {
        "set_id": set_id, "calculation_run_id": run_id, "accessibility": accessibility,
        "chase_depth": 3.2, "mapped_hc_mass": mass, "status": "ready",
        "status_reason": None, "version": CHASE_ACCESSIBILITY_VERSION,
        "significance_version": "chase_significance_v1_squared_value_share",
        "depth_version": CHASE_DEPTH_VERSION,
    }


def _pull_rate_row(set_id, run_id, variant_id, price, probability, pull_count=5):
    return {
        "calculation_run_id": run_id, "set_id": set_id, "card_variant_id": variant_id,
        "price_used": price, "modeled_probability": probability,
        "effective_pull_rate": None if not probability else 1.0 / probability,
        "pull_count": pull_count, "pack_presence_count": pull_count, "simulation_count": 1000,
    }


def _cohort_row(sealed_product_id, set_id, run_id, price, random_pack_count):
    return {
        "sealed_product_id": sealed_product_id, "set_id": set_id,
        "calculation_run_id": run_id, "product_market_cost": price,
        "random_pack_count": random_pack_count, "product_name": "Product %s" % sealed_product_id,
        "product_family": "elite_trainer_box",
    }


class _Query:
    def __init__(self, table_name, rows, call_log):
        self._table = table_name
        self._rows = rows
        self._filters = []
        self._call_log = call_log

    def select(self, *_a, **_k):
        return self

    def eq(self, column, value):
        self._filters.append(("eq", column, value))
        return self

    def gt(self, column, value):
        self._filters.append(("gt", column, value))
        return self

    def in_(self, column, values):
        self._filters.append(("in", column, set(values)))
        return self

    def order(self, *_a, **_k):
        return self

    def range(self, start, end):
        self._filters.append(("range", start, end))
        return self

    def execute(self):
        self._call_log[self._table] += 1
        rows = list(self._rows)
        for kind, *rest in self._filters:
            if kind == "eq":
                column, value = rest
                rows = [r for r in rows if r.get(column) == value]
            elif kind == "gt":
                column, value = rest
                rows = [r for r in rows if (r.get(column) or 0) > value]
            elif kind == "in":
                column, values = rest
                rows = [r for r in rows if r.get(column) in values]
            elif kind == "range":
                start, end = rest
                rows = rows[start:end + 1]
        return type("R", (), {"data": rows})()


class _FakeClient:
    """Serves both the snapshot table and the pull-rates table, logging
    every ``.table(...).execute()`` call so tests can assert exact counts."""

    def __init__(self, snapshot_rows, pull_rate_rows):
        self._tables = {SNAPSHOT_TABLE: snapshot_rows, PULL_RATES_TABLE: pull_rate_rows}
        self.call_log = defaultdict(int)

    def table(self, name):
        return _Query(name, self._tables.get(name, []), self.call_log)


def _three_product_two_set_fixture():
    """2 sets, 2 distinct runs, 3 products total (set-1 has TWO products)."""
    snapshot_rows = [_snapshot_row("set-1", "run-1"), _snapshot_row("set-2", "run-2", accessibility=0.05)]
    pull_rate_rows = [
        _pull_rate_row("set-1", "run-1", "v1", 1.0, 0.10),
        _pull_rate_row("set-1", "run-1", "v2", 2.0, 0.40),
        _pull_rate_row("set-2", "run-2", "v3", 5.0, 0.20),
        _pull_rate_row("set-2", "run-2", "v4", 10.0, 0.05),
    ]
    cohort = [
        _cohort_row("p1", "set-1", "run-1", price=12.0, random_pack_count=1),
        _cohort_row("p2", "set-1", "run-1", price=144.0, random_pack_count=36),
        _cohort_row("p3", "set-2", "run-2", price=42.0, random_pack_count=4),
    ]
    return _FakeClient(snapshot_rows, pull_rate_rows), cohort


# --------------------------------------------------------------------------
# Phase 13 - no N+1
# --------------------------------------------------------------------------

def test_variant_universe_is_read_once_per_distinct_run_not_per_product():
    client, cohort = _three_product_two_set_fixture()
    resolve_product_chase_access(client, cohort, budget=50.0)
    # 2 distinct sets/runs -> exactly 2 pull-rate reads, NOT 3 (one per product).
    assert client.call_log[PULL_RATES_TABLE] == 2


def test_accessibility_cohort_is_read_in_one_batched_query():
    client, cohort = _three_product_two_set_fixture()
    resolve_product_chase_access(client, cohort, budget=50.0)
    assert client.call_log[SNAPSHOT_TABLE] == 1


def test_query_count_is_reported_in_the_response_for_observability():
    client, cohort = _three_product_two_set_fixture()
    result = resolve_product_chase_access(client, cohort, budget=50.0)
    assert result["queryCount"]["accessibilityCohortReads"] == 1
    assert result["queryCount"]["variantUniverseReads"] == 2
    assert result["distinctSetCount"] == 2
    assert result["productCount"] == 3


def test_larger_cohort_same_set_count_does_not_add_more_variant_reads():
    """5 products across the SAME 2 sets must still cost exactly 2 variant reads."""
    client, cohort = _three_product_two_set_fixture()
    cohort = cohort + [
        _cohort_row("p4", "set-1", "run-1", price=4.0, random_pack_count=1),
        _cohort_row("p5", "set-2", "run-2", price=84.0, random_pack_count=8),
    ]
    resolve_product_chase_access(client, cohort, budget=50.0)
    assert client.call_log[PULL_RATES_TABLE] == 2


# --------------------------------------------------------------------------
# Authority coherence
# --------------------------------------------------------------------------

def test_o_budget_uses_the_same_run_variants_as_the_products_run():
    client, cohort = _three_product_two_set_fixture()
    result = resolve_product_chase_access(client, cohort, budget=200.0)
    by_id = {p["sealedProductId"]: p for p in result["products"]}
    assert by_id["p1"]["calculationRunId"] == "run-1"
    assert by_id["p3"]["calculationRunId"] == "run-2"
    assert by_id["p1"]["oBudget"] is not None
    assert by_id["p3"]["oBudget"] is not None


def test_low_mapped_mass_set_is_rejected_not_silently_scored():
    client, cohort = _three_product_two_set_fixture()
    # Corrupt set-2's snapshot to fail the mass gate.
    client._tables[SNAPSHOT_TABLE][1]["mapped_hc_mass"] = 0.5
    result = resolve_product_chase_access(client, cohort, budget=200.0)
    by_id = {p["sealedProductId"]: p for p in result["products"]}
    assert by_id["p3"]["chaseAccessibilityReady"] is False
    assert by_id["p3"]["aRaw"] is None


def test_no_budget_never_invents_o_budget_or_a_rank():
    client, cohort = _three_product_two_set_fixture()
    result = resolve_product_chase_access(client, cohort, budget=None)
    for product in result["products"]:
        assert "oBudget" not in product
        assert "oBudgetRank" not in product
        # Set-level/context fields are still present without a budget.
        assert "effectivePackCost" in product


# --------------------------------------------------------------------------
# Cross-format ranking (Phase 9)
# --------------------------------------------------------------------------

def test_explicit_budget_ranks_by_o_budget_descending():
    client, cohort = _three_product_two_set_fixture()
    result = resolve_product_chase_access(client, cohort, budget=200.0)
    ranked = sorted((p for p in result["products"] if p.get("oBudgetRank")),
                    key=lambda p: p["oBudgetRank"])
    values = [p["oBudget"] for p in ranked]
    assert values == sorted(values, reverse=True)


def test_budget_below_one_unit_is_ineligible_not_zero_faked():
    client, cohort = _three_product_two_set_fixture()
    result = resolve_product_chase_access(client, cohort, budget=1.0)
    by_id = {p["sealedProductId"]: p for p in result["products"]}
    # p2 costs $144 -> ineligible at $1 budget.
    assert by_id["p2"]["quantity"] == 0
    assert by_id["p2"]["oBudget"] is None
    assert by_id["p2"]["oBudgetStatus"] == "unavailable_budget_below_one_unit"
