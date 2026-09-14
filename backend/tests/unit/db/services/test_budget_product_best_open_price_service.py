"""Unit tests for the PRIVATE Best-Open Price persistence/read service.

No live DB: exercises the pure payload-building helpers and the read-path
staleness rule against a small fake client that mimics the subset of the
supabase-py query builder interface this module uses.
"""

from __future__ import annotations

from typing import Any, Dict, List

import pytest

from backend.db.services import budget_product_best_open_price_service as svc
from backend.db.services.best_open_price_authority import SOURCE_VERSIONS


class _Resp:
    def __init__(self, data):
        self.data = data


class _Query:
    def __init__(self, table_rows: List[Dict[str, Any]]):
        self._rows = list(table_rows)

    def select(self, *_a, **_k):
        return self

    def eq(self, field, value):
        self._rows = [r for r in self._rows if str(r.get(field)) == str(value)]
        return self

    def limit(self, n):
        self._rows = self._rows[:n]
        return self

    def order(self, *_a, **_k):
        return self

    def execute(self):
        return _Resp(self._rows)


class FakeClient:
    def __init__(self, tables: Dict[str, List[Dict[str, Any]]]):
        self._tables = tables
        self.rpc_calls = []

    def table(self, name):
        return _Query(self._tables.get(name, []))

    def rpc(self, name, params):
        self.rpc_calls.append((name, params))
        return _Query([{"data": "fake-id"}])  # unused path in these tests


SOURCE = {
    "id": "src-1", "published_at": "2026-09-01T00:00:00Z", "market_date": "2026-09-01",
    "cohort_fingerprint": "fp-1", "eligible_cohort_count": 138, "full_market_budget": 1400,
}

SNAPSHOT_ROW = {
    "id": "snap-1", "source_budget_snapshot_id": "src-1", "source_budget_published_at": "2026-09-01T00:00:00Z",
    "source_market_date": "2026-09-01", "source_cohort_fingerprint": "fp-1",
    "ranking_method_version": "rmv1", "allocation_method_version": "amv1",
    "resolved_count": 1, "unresolved_count": 0, "built_at": "t", "published_at": "t",
}

SOURCE.update(SOURCE_VERSIONS)
SOURCE.update(pinned_price_as_of=SOURCE['market_date'], ranked_under_v12_authority=True, eligible_cohort_count=2)
SNAPSHOT_ROW.update({key: value for key, value in SOURCE_VERSIONS.items() if key != 'overall_rip_version'})
SNAPSHOT_ROW.update(source_full_market_budget=1400, source_eligible_cohort_count=2, resolved_count=2,
                    best_open_price_method_version=svc.BEST_OPEN_PRICE_METHOD_VERSION)

LATEST_ROW = {"best_open_price_method_version": svc.BEST_OPEN_PRICE_METHOD_VERSION, "snapshot_id": "snap-1"}


def test_build_row_payload_projects_engine_row_fields():
    engine_row = {
        "sealedProductId": "p1", "setId": "s1", "productFamily": "booster_box",
        "sourceCalculationRunId": "run1", "currentMarketPrice": 100.0, "currentQuantity": 14,
        "currentBudgetRank": 1, "currentOverallRipV12Score": 0.9, "status": "current_number_one_with_headroom",
        "currentFinancialRipV4Score": 0.75, "currentCollectorAppealScore": 0.6,
        "currentChaseAccessibilityRaw": 0.4, "currentChanceToRecoverCapital": 0.85,
        "currentActualCommittedCapital": 1386.0,
        "bestOpenPrice": 110.0, "thresholdQuantity": 12, "priceGapDollars": -10.0, "priceGapPercent": -0.1,
        "benchmarkSealedProductId": "p2", "benchmarkOverallRipV12Score": 0.8,
        "benchmarkFinancialRipV4Score": 0.7, "benchmarkChanceToRecoverCapital": 0.8,
        "benchmarkActualCommittedCapital": 1390.0,
        "candidatePriceEvaluations": 5, "bracketExpansions": 2, "bracketRefinements": 3,
        "fallbackCount": 0, "searchWallSeconds": 1.2,
    }
    payload = svc.build_row_payload(engine_row)
    assert payload["sealed_product_id"] == "p1"
    assert payload["best_open_price"] == 110.0
    assert payload["status"] == "current_number_one_with_headroom"
    assert payload["monotonicity_fallback_count"] == 0
    assert payload["current_financial_rip_v4_score"] == 0.75
    assert payload["current_collector_appeal_score"] == 0.6
    assert payload["current_chase_accessibility_raw"] == 0.4
    assert payload["current_chance_to_recover_capital"] == 0.85
    assert payload["current_actual_committed_capital"] == 1386.0
    assert payload["benchmark_financial_rip_v4_score"] == 0.7
    assert payload["benchmark_chance_to_recover_capital"] == 0.8
    assert payload["benchmark_actual_committed_capital"] == 1390.0


def test_content_fingerprint_is_order_independent_but_content_sensitive():
    rows_a = [{"sealed_product_id": "1"}, {"sealed_product_id": "2"}]
    rows_b = [{"sealed_product_id": "2"}, {"sealed_product_id": "1"}]
    assert svc.content_fingerprint(rows_a) == svc.content_fingerprint(rows_b)
    rows_c = [{"sealed_product_id": "2"}, {"sealed_product_id": "3"}]
    assert svc.content_fingerprint(rows_a) != svc.content_fingerprint(rows_c)


def test_load_best_open_price_ranking_unavailable_when_no_snapshot():
    client = FakeClient({"budget_product_best_open_price_latest": []})
    result = svc.load_best_open_price_ranking(client)
    assert result == {"available": False, "reason": "no_published_snapshot", "rows": []}


def test_load_best_open_price_ranking_available_on_exact_match():
    client = FakeClient({
        "budget_product_best_open_price_latest": [LATEST_ROW],
        "budget_product_best_open_price_snapshots": [SNAPSHOT_ROW],
        "budget_product_ranking_latest": [{"ranking_method_version": SOURCE["ranking_method_version"], "allocation_method_version": SOURCE["allocation_method_version"], "snapshot_id": "src-1"}],
        "budget_product_ranking_snapshots": [SOURCE],
        "budget_product_best_open_price_rows": [{"sealed_product_id": pid, "snapshot_id": "snap-1"} for pid in ("p1", "p2")],
    })
    result = svc.load_best_open_price_ranking(client)
    assert result["available"] is True
    assert result["reason"] is None
    assert result["snapshotId"] == "snap-1"


@pytest.mark.parametrize("drift_field,drift_value", [
    ("published_at", "2026-09-02T00:00:00Z"),
    ("market_date", "2026-09-02"),
    ("cohort_fingerprint", "fp-DIFFERENT"),
])
def test_load_best_open_price_ranking_stale_on_any_source_drift(drift_field, drift_value):
    drifted_source = dict(SOURCE)
    drifted_source[drift_field] = drift_value
    client = FakeClient({
        "budget_product_best_open_price_latest": [LATEST_ROW],
        "budget_product_best_open_price_snapshots": [SNAPSHOT_ROW],
        "budget_product_ranking_latest": [{"ranking_method_version": SOURCE["ranking_method_version"], "allocation_method_version": SOURCE["allocation_method_version"], "snapshot_id": "src-1"}],
        "budget_product_ranking_snapshots": [drifted_source],
        "budget_product_best_open_price_rows": [{"sealed_product_id": pid, "snapshot_id": "snap-1"} for pid in ("p1", "p2")],
    })
    result = svc.load_best_open_price_ranking(client)
    assert result == {"available": False, "reason": "stale_source_publication", "rows": []}


def test_load_best_open_price_ranking_stale_when_live_snapshot_id_differs():
    other_source = dict(SOURCE, id="src-OTHER")
    client = FakeClient({
        "budget_product_best_open_price_latest": [LATEST_ROW],
        "budget_product_best_open_price_snapshots": [SNAPSHOT_ROW],
        "budget_product_ranking_latest": [{"ranking_method_version": SOURCE["ranking_method_version"], "allocation_method_version": SOURCE["allocation_method_version"], "snapshot_id": "src-OTHER"}],
        "budget_product_ranking_snapshots": [other_source],
        "budget_product_best_open_price_rows": [{"sealed_product_id": pid, "snapshot_id": "snap-1"} for pid in ("p1", "p2")],
    })
    result = svc.load_best_open_price_ranking(client)
    assert result == {"available": False, "reason": "stale_source_publication", "rows": []}


def test_load_best_open_price_ranking_unavailable_when_no_live_source():
    client = FakeClient({
        "budget_product_best_open_price_latest": [LATEST_ROW],
        "budget_product_best_open_price_snapshots": [SNAPSHOT_ROW],
        "budget_product_ranking_latest": [],
    })
    result = svc.load_best_open_price_ranking(client)
    assert result == {"available": False, "reason": "no_live_budget_ranking_source", "rows": []}


def test_load_best_open_price_ranking_unavailable_when_rows_incomplete():
    client = FakeClient({
        "budget_product_best_open_price_latest": [LATEST_ROW],
        "budget_product_best_open_price_snapshots": [SNAPSHOT_ROW],
        "budget_product_ranking_latest": [{"ranking_method_version": SOURCE["ranking_method_version"], "allocation_method_version": SOURCE["allocation_method_version"], "snapshot_id": "src-1"}],
        "budget_product_ranking_snapshots": [SOURCE],
        "budget_product_best_open_price_rows": [],  # resolved_count says 1, actual 0
    })
    result = svc.load_best_open_price_ranking(client)
    assert result == {"available": False, "reason": "incomplete_snapshot_rows", "rows": []}
