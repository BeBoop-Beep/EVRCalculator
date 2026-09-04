"""Gate F, Phase 3 - budget-cohort Chase Accessibility authority tests.

The most important test here is the stale-but-otherwise-ready exploit test
(mirroring sealed_product_rip_finalization_service's equivalent): an
Accessibility row that is status=ready, correct version, and passes
mapped_hc_mass, but belongs to the WRONG calculation_run_id, must be
rejected outright - never accepted as "the latest available".
"""

from __future__ import annotations

from typing import Any, Dict, List

import pytest

from backend.db.services.budget_chase_accessibility_authority import (
    accessibility_raw_for_product,
    resolve_budget_cohort_accessibility,
)
from backend.desirability.chase_accessibility import CHASE_ACCESSIBILITY_VERSION


class _FakeTable:
    def __init__(self, rows: List[Dict[str, Any]]):
        self._rows = rows
        self._filters: Dict[str, Any] = {}

    def select(self, *_args, **_kwargs):
        return self

    def in_(self, field, values):
        self._filters[field] = set(values)
        return self

    def order(self, *_args, **_kwargs):
        return self

    def range(self, *_args, **_kwargs):
        return self

    def execute(self):
        rows = self._rows
        for field, values in self._filters.items():
            rows = [r for r in rows if r.get(field) in values]
        return type("Resp", (), {"data": rows})()


class _FakeClient:
    def __init__(self, rows: List[Dict[str, Any]]):
        self._rows = rows
        self.query_count = 0

    def table(self, name):
        assert name == "pokemon_set_chase_accessibility_snapshot_latest"
        self.query_count += 1
        return _FakeTable(self._rows)


def _ready_row(set_id: str, run_id: str, accessibility: float = 0.01, mass: float = 1.0) -> Dict[str, Any]:
    return {
        "set_id": set_id,
        "calculation_run_id": run_id,
        "version": CHASE_ACCESSIBILITY_VERSION,
        "status": "ready",
        "accessibility": accessibility,
        "mapped_hc_mass": mass,
    }


def test_coherent_ready_row_is_accepted():
    client = _FakeClient([_ready_row("set-1", "run-a")])
    resolved = resolve_budget_cohort_accessibility(client, {"set-1": "run-a"})
    assert resolved["bySet"]["set-1"]["ready"] is True
    assert resolved["bySet"]["set-1"]["aRaw"] == 0.01
    assert accessibility_raw_for_product(resolved, "set-1") == 0.01


def test_stale_but_otherwise_ready_row_is_rejected_not_accepted_as_latest():
    """The critical exploit test: status=ready, correct version, mass>=0.99,
    but the row's calculation_run_id does NOT match the expected run for this
    cohort. Must be rejected, never silently treated as the latest available
    Accessibility."""
    stale_row = _ready_row("set-1", "run-YESTERDAY", accessibility=0.02, mass=1.0)
    client = _FakeClient([stale_row])
    resolved = resolve_budget_cohort_accessibility(client, {"set-1": "run-TODAY"})
    entry = resolved["bySet"]["set-1"]
    assert entry["ready"] is False
    assert any(f["reason"] == "stale_calculation_run" for f in entry["reasons"])
    assert accessibility_raw_for_product(resolved, "set-1") is None


def test_wrong_version_row_is_rejected():
    client = _FakeClient([
        {**_ready_row("set-1", "run-a"), "version": "chase_accessibility_v0_legacy"}
    ])
    resolved = resolve_budget_cohort_accessibility(client, {"set-1": "run-a"})
    entry = resolved["bySet"]["set-1"]
    assert entry["ready"] is False
    assert any(f["reason"] == "wrong_model_version" for f in entry["reasons"])


def test_insufficient_mapped_hc_mass_is_rejected():
    client = _FakeClient([_ready_row("set-1", "run-a", mass=0.5)])
    resolved = resolve_budget_cohort_accessibility(client, {"set-1": "run-a"})
    entry = resolved["bySet"]["set-1"]
    assert entry["ready"] is False
    assert any(f["reason"] == "insufficient_mapped_hc_mass" for f in entry["reasons"])


def test_missing_row_for_a_simulation_supported_set_is_rejected():
    client = _FakeClient([])
    resolved = resolve_budget_cohort_accessibility(client, {"set-1": "run-a"})
    entry = resolved["bySet"]["set-1"]
    assert entry["ready"] is False
    assert any(f["reason"] == "missing_chase_accessibility_row" for f in entry["reasons"])


def test_never_falls_back_to_zero_or_a_neutral_value():
    client = _FakeClient([_ready_row("set-1", "run-WRONG")])
    resolved = resolve_budget_cohort_accessibility(client, {"set-1": "run-a"})
    assert accessibility_raw_for_product(resolved, "set-1") is None  # never 0.0


def test_batch_read_is_exactly_one_call_for_the_whole_cohort():
    """Phase 3/14C - ONE query for the whole cohort, never per-set."""
    rows = [_ready_row("set-%d" % i, "run-a") for i in range(1, 26)]
    client = _FakeClient(rows)
    run_id_by_set_id = {"set-%d" % i: "run-a" for i in range(1, 26)}
    resolved = resolve_budget_cohort_accessibility(client, run_id_by_set_id)
    assert client.query_count == 1
    assert resolved["batchReadCount"] == 1
    assert resolved["readySetCount"] == 25


def test_two_different_products_of_the_same_set_get_identical_a_raw_without_a_second_read():
    """Sanity invariant: Accessibility is set-level, so two products (and
    every budget for each) mapped to the same set must read the identical
    resolved value with zero additional queries."""
    client = _FakeClient([_ready_row("set-1", "run-a", accessibility=0.033)])
    resolved = resolve_budget_cohort_accessibility(client, {"set-1": "run-a"})
    assert client.query_count == 1
    a1 = accessibility_raw_for_product(resolved, "set-1")
    a2 = accessibility_raw_for_product(resolved, "set-1")
    assert a1 == a2 == 0.033
    assert client.query_count == 1  # repeated lookups never re-query
