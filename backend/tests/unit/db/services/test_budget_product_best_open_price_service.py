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


def _v2_engine_row(**overrides):
    """Matches the REAL current build_v2_row() output shape in
    backend/scripts/research_best_open_price_v2.py (read directly, not
    assumed from prose)."""
    row = {
        "methodVersion": "budget_product_best_open_price_full_market_v2_dual_financial_v4_overall_v12",
        "sealedProductId": "11111111-1111-1111-1111-111111111111",
        "setId": "44444444-4444-4444-4444-444444444444",
        "productFamily": "booster_box",
        "sourceCalculationRunId": "run-1",
        "currentMarketPrice": 145.0,
        "currentQuantity": 9,
        "currentOverallRipV12Score": 0.85,
        "currentFinancialRipV4Score": 0.72,
        "currentCollectorAppealScore": 0.55,
        "currentChaseAccessibilityRaw": 0.33,
        "currentChanceToRecoverCapital": 0.6,
        "currentActualCommittedCapital": 1305.0,
        "currentBudgetRank": 2,
        "currentFinancialOnlyRank": 1,
        "resolved": True, "ripResolved": True, "financialResolved": True,
        "diagnostics": {"uniqueQuantitiesConstructed": 3},
        "bestOpenPrice": 145.0, "bestOpenPriceCents": 14500, "status": "exact",
        "thresholdQuantity": 9, "benchmarkSealedProductId": "22222222-2222-2222-2222-222222222222",
        "benchmarkOverallRipV12Score": 80.0,
        "benchmarkFinancialRipV4Score": 0.7,
        "benchmarkChanceToRecoverCapital": 0.5,
        "benchmarkActualCommittedCapital": 1300.0,
        "candidatePriceEvaluations": 5, "bracketExpansions": 2, "bracketRefinements": 1,
        "fallbackCount": 0, "searchWallSeconds": 0.5,
        "exactness": {"thresholdWins": True},
        "priceGapDollars": 5.0, "priceGapPercent": 0.03,
        "ripBestOpenPrice": 145.0, "ripBestOpenPriceCents": 14500, "ripStatus": "exact",
        "ripThresholdQuantity": 9, "ripBenchmarkSealedProductId": "22222222-2222-2222-2222-222222222222",
        "ripBenchmarkOverallRipV12Score": 80.0,
        "ripBenchmarkFinancialRipV4Score": 0.7,
        "ripExactness": {"thresholdWins": True, "nextPriceCents": 14501, "nextPriceWins": False,
                          "oneCentMaximal": True, "quantityIntervalLowCents": 14000, "quantityIntervalHighCents": 15000,
                          "nextCentCrossesQuantityBoundary": False},
        "ripThresholdFinancialRipV4Score": 50.0, "ripThresholdOverallRipV12Score": 80.0,
        "ripThresholdChanceToRecoverCapital": 0.3, "ripThresholdActualCommittedCapital": 1305.0,
        "ripPriceGapDollars": 5.0, "ripPriceGapPercent": 0.03,
        "financialBestOpenPrice": 150.0, "financialBestOpenPriceCents": 15000, "financialStatus": "exact",
        "financialThresholdQuantity": 9, "financialBenchmarkSealedProductId": "33333333-3333-3333-3333-333333333333",
        "financialBenchmarkFinancialRipV4Score": 90.0,
        "financialBenchmarkOverallRipV12Score": 70.0,
        "financialExactness": {"thresholdWins": True, "nextPriceCents": 15001, "nextPriceWins": False,
                                "oneCentMaximal": True, "quantityIntervalLowCents": 14800, "quantityIntervalHighCents": 15200,
                                "nextCentCrossesQuantityBoundary": False},
        "financialThresholdFinancialRipV4Score": 90.0, "financialThresholdOverallRipV12Score": 70.0,
        "financialThresholdChanceToRecoverCapital": 0.4, "financialThresholdActualCommittedCapital": 1350.0,
        "financialPriceGapDollars": 10.0, "financialPriceGapPercent": 0.06,
    }
    row.update(overrides)
    return row


def test_build_v2_row_payload_projects_generic_rip_fields():
    payload = svc.build_v2_row_payload(_v2_engine_row())
    assert payload["status"] == "exact"
    assert payload["best_open_price"] == 145.0
    assert payload["threshold_quantity"] == 9
    assert payload["price_gap_dollars"] == 5.0
    assert payload["benchmark_sealed_product_id"] == "22222222-2222-2222-2222-222222222222"
    assert payload["sealed_product_id"] == "11111111-1111-1111-1111-111111111111"
    assert payload["set_id"] == "44444444-4444-4444-4444-444444444444"
    assert payload["current_market_price"] == 145.0
    assert payload["current_budget_rank"] == 2


def test_build_v2_row_payload_projects_financial_fields():
    payload = svc.build_v2_row_payload(_v2_engine_row())
    assert payload["current_financial_only_rank"] == 1
    assert payload["financial_best_open_price"] == 150.0
    assert payload["financial_status"] == "exact"
    assert payload["financial_threshold_quantity"] == 9
    assert payload["financial_benchmark_sealed_product_id"] == "33333333-3333-3333-3333-333333333333"
    assert payload["financial_benchmark_financial_rip_v4_score"] == 90.0
    assert payload["financial_benchmark_overall_rip_v12_score"] == 70.0


def test_build_v2_row_payload_projects_both_threshold_evidence_sets():
    payload = svc.build_v2_row_payload(_v2_engine_row())
    assert payload["threshold_financial_rip_v4_score"] == 50.0
    assert payload["threshold_overall_rip_v12_score"] == 80.0
    assert payload["threshold_actual_committed_capital"] == 1305.0
    assert payload["financial_threshold_financial_rip_v4_score"] == 90.0
    assert payload["financial_threshold_overall_rip_v12_score"] == 70.0
    assert payload["financial_threshold_actual_committed_capital"] == 1350.0


def test_build_v2_row_payload_does_not_compute_anything_it_reads_verbatim():
    """No arithmetic beyond straight field copies -- this is a projection,
    not a scorer."""
    row = _v2_engine_row(ripThresholdActualCommittedCapital=9999.0)
    payload = svc.build_v2_row_payload(row)
    assert payload["threshold_actual_committed_capital"] == 9999.0  # copied, not recomputed


def test_build_v2_row_payload_projects_diagnostics_and_shared_v1_fields():
    payload = svc.build_v2_row_payload(_v2_engine_row())
    assert payload["candidate_price_evaluations"] == 5
    assert payload["bracket_expansions"] == 2
    assert payload["bracket_refinements"] == 1
    assert payload["monotonicity_fallback_count"] == 0
    assert payload["search_wall_seconds"] == 0.5
    assert payload["product_family"] == "booster_box"
    assert payload["source_calculation_run_id"] == "run-1"
    assert payload["current_quantity"] == 9
    assert payload["current_overall_rip_v12_score"] == 0.85
    assert payload["current_financial_rip_v4_score"] == 0.72
    assert payload["current_collector_appeal_score"] == 0.55
    assert payload["current_chase_accessibility_raw"] == 0.33
    assert payload["current_chance_to_recover_capital"] == 0.6
    assert payload["current_actual_committed_capital"] == 1305.0
    assert payload["benchmark_overall_rip_v12_score"] == 80.0
    assert payload["benchmark_financial_rip_v4_score"] == 0.7
    assert payload["benchmark_chance_to_recover_capital"] == 0.5
    assert payload["benchmark_actual_committed_capital"] == 1300.0


def test_build_row_payload_v1_is_unaffected():
    """Sanity pin: adding build_v2_row_payload must not touch build_row_payload."""
    assert svc.build_row_payload is not None  # import still works; existing V1 tests cover its behavior


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
