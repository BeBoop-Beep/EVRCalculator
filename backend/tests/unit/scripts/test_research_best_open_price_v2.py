"""Unit tests for the V2 dual-threshold cohort engine and result-row contract.

build_v2_row is a pure function and is fully unit-tested here. run() is the
per-cohort orchestration entry point -- it requires a live Supabase client and
real pack-outcome artifacts to exercise end-to-end, which this worktree does
not have credentials for (matching the existing pattern in
test_research_best_open_price_bucket2.py, which only unit-tests bucket2.py's
pure helpers, never run() against a real client). Only run()'s fail-closed
rank-validation behavior is tested here, by calling the already-existing,
already-reviewed Task 2 validators directly.
"""
from __future__ import annotations

import pytest

from backend.scripts.research_best_open_price_bucket0 import (
    validate_financial_only_rank_reconstructs,
    validate_rank_column_contiguous,
)
from backend.scripts.research_best_open_price_v2 import build_v2_row


def _threshold(price_cents, quantity, financial_v4, overall_v12, chance, capital):
    return {
        "wins": True, "priceCents": price_cents, "quantity": quantity,
        "financialRipV4Score": financial_v4, "overallRipV12Score": overall_v12,
        "chanceToRecoverCapital": chance, "actualCommittedCapital": capital,
    }


def _search_result(status, threshold, current_rank, benchmark_id, next_price_cents=None):
    return {
        "methodVersion": "budget_product_best_open_price_full_market_v1",
        "status": status, "currentRank": current_rank, "threshold": threshold,
        "benchmarkProductId": benchmark_id,
        "exactness": {
            "thresholdWins": True, "nextPriceCents": next_price_cents, "nextPriceWins": False,
            "oneCentMaximal": True, "quantityIntervalLowCents": 1, "quantityIntervalHighCents": 2,
            "nextCentCrossesQuantityBoundary": False,
        } if threshold else None,
    }


def test_build_v2_row_exposes_backward_compatible_rip_aliases():
    rip_threshold = _threshold(14068, 9, 50.0, 80.0, 0.3, 1266.12)
    dual_result = {
        "ripResult": _search_result("exact", rip_threshold, 2, "rip-bench"),
        "financialResult": _search_result("exact", _threshold(14000, 9, 60.0, 70.0, 0.35, 1260.0), 2, "fin-bench"),
        "diagnostics": {},
    }
    row = build_v2_row(dual_result, source_row={"sealed_product_id": "p1", "financial_only_rank": 2, "budget_rank_v12": 2})
    assert row["bestOpenPrice"] == row["ripBestOpenPrice"] == 140.68
    assert row["status"] == row["ripStatus"] == "exact"
    assert row["exactness"] == row["ripExactness"]


def test_build_v2_row_financial_fields_are_independent_of_rip():
    rip_threshold = _threshold(14068, 9, 50.0, 80.0, 0.3, 1266.12)
    financial_threshold = _threshold(14500, 10, 90.0, 40.0, 0.5, 1450.0)
    dual_result = {
        "ripResult": _search_result("exact", rip_threshold, 2, "rip-bench"),
        "financialResult": _search_result("exact", financial_threshold, 1, "fin-bench"),
        "diagnostics": {},
    }
    row = build_v2_row(dual_result, source_row={"sealed_product_id": "p1", "financial_only_rank": 1, "budget_rank_v12": 2})
    assert row["financialBestOpenPrice"] == 145.0
    assert row["financialBenchmarkSealedProductId"] == "fin-bench"
    assert row["ripBenchmarkSealedProductId"] == "rip-bench"
    assert row["financialBenchmarkSealedProductId"] != row["ripBenchmarkSealedProductId"]
    assert row["currentFinancialOnlyRank"] == 1


def test_build_v2_row_threshold_evidence_is_copied_not_recomputed():
    rip_threshold = _threshold(14068, 9, 50.0, 80.0, 0.3, 1266.12)
    dual_result = {
        "ripResult": _search_result("exact", rip_threshold, 2, "rip-bench"),
        "financialResult": _search_result("exact", _threshold(14000, 9, 60.0, 70.0, 0.35, 1260.0), 2, "fin-bench"),
        "diagnostics": {},
    }
    row = build_v2_row(dual_result, source_row={"sealed_product_id": "p1", "financial_only_rank": 2, "budget_rank_v12": 2})
    assert row["ripThresholdFinancialRipV4Score"] == 50.0
    assert row["ripThresholdOverallRipV12Score"] == 80.0
    assert row["ripThresholdChanceToRecoverCapital"] == 0.3
    assert row["ripThresholdActualCommittedCapital"] == 1266.12
    assert row["financialThresholdFinancialRipV4Score"] == 60.0
    assert row["financialThresholdOverallRipV12Score"] == 70.0


def test_build_v2_row_requires_both_authorities_resolved_for_complete_status():
    dual_result = {
        "ripResult": _search_result("exact", _threshold(14068, 9, 50.0, 80.0, 0.3, 1266.12), 2, "rip-bench"),
        "financialResult": _search_result("unresolved_extreme_quantity", None, 2, None),
        "diagnostics": {},
    }
    row = build_v2_row(dual_result, source_row={"sealed_product_id": "p1", "financial_only_rank": 2, "budget_rank_v12": 2})
    assert row["resolved"] is False
    assert row["ripResolved"] is True
    assert row["financialResolved"] is False


def test_build_v2_row_threads_raw_benchmark_dicts_for_fields_missing_from_payload():
    """ExactBestOpenPriceSearch._payload() exposes benchmarkOverallRipV12Score
    (from self.benchmark.get("overallRipV12Score")) but NOT a benchmark
    Financial RIP V4 score on either search result (verified against the
    current implementation) -- build_v2_row must accept the raw
    rip_benchmark/financial_benchmark mapping dicts as extra kwargs and read
    benchmark Financial RIP V4 scores from those, never inventing a new field
    on the search engine itself. benchmarkOverallRipV12Score is still read
    verbatim from the search result payload, not from the raw dict."""
    rip_result = _search_result("exact", _threshold(14068, 9, 50.0, 80.0, 0.3, 1266.12), 2, "rip-bench")
    rip_result["benchmarkOverallRipV12Score"] = 82.0
    financial_result = _search_result("exact", _threshold(14000, 9, 60.0, 70.0, 0.35, 1260.0), 2, "fin-bench")
    financial_result["benchmarkOverallRipV12Score"] = 71.0
    dual_result = {"ripResult": rip_result, "financialResult": financial_result, "diagnostics": {}}
    rip_benchmark = {"sealedProductId": "rip-bench", "financialRipV4Score": 55.5, "overallRipV12Score": 82.0}
    financial_benchmark = {"sealedProductId": "fin-bench", "financialRipV4Score": 61.1, "overallRipV12Score": 71.0}
    row = build_v2_row(
        dual_result, source_row={"sealed_product_id": "p1", "financial_only_rank": 2, "budget_rank_v12": 2},
        rip_benchmark=rip_benchmark, financial_benchmark=financial_benchmark,
    )
    assert row["ripBenchmarkFinancialRipV4Score"] == 55.5
    assert row["financialBenchmarkFinancialRipV4Score"] == 61.1
    assert row["ripBenchmarkOverallRipV12Score"] == 82.0
    assert row["financialBenchmarkOverallRipV12Score"] == 71.0


def test_build_v2_row_benchmark_fields_default_to_none_without_raw_benchmarks():
    dual_result = {
        "ripResult": _search_result("exact", _threshold(14068, 9, 50.0, 80.0, 0.3, 1266.12), 2, "rip-bench"),
        "financialResult": _search_result("exact", _threshold(14000, 9, 60.0, 70.0, 0.35, 1260.0), 2, "fin-bench"),
        "diagnostics": {},
    }
    row = build_v2_row(dual_result, source_row={"sealed_product_id": "p1", "financial_only_rank": 2, "budget_rank_v12": 2})
    assert row["ripBenchmarkFinancialRipV4Score"] is None
    assert row["financialBenchmarkFinancialRipV4Score"] is None


def test_run_fails_closed_on_missing_financial_only_rank():
    rows = [{"sealed_product_id": "a", "financial_only_rank": 1, "budget_rank_v12": 1},
            {"sealed_product_id": "b", "financial_only_rank": None, "budget_rank_v12": 2}]
    with pytest.raises(RuntimeError, match="missing"):
        validate_rank_column_contiguous(rows, "financial_only_rank")


def test_run_fails_closed_on_duplicate_financial_only_rank():
    rows = [{"sealed_product_id": "a", "financial_only_rank": 1}, {"sealed_product_id": "b", "financial_only_rank": 1}]
    with pytest.raises(RuntimeError, match="contiguous"):
        validate_rank_column_contiguous(rows, "financial_only_rank")


def test_run_fails_closed_on_non_contiguous_financial_only_rank():
    rows = [{"sealed_product_id": "a", "financial_only_rank": 1}, {"sealed_product_id": "b", "financial_only_rank": 3}]
    with pytest.raises(RuntimeError, match="contiguous"):
        validate_rank_column_contiguous(rows, "financial_only_rank")


def test_run_fails_closed_on_financial_score_parity_failure():
    rows = [
        {"sealed_product_id": "high", "financial_only_rank": 2, "financial_rip_v4_score": 90.0},  # wrong rank
        {"sealed_product_id": "low", "financial_only_rank": 1, "financial_rip_v4_score": 10.0},
    ]
    with pytest.raises(RuntimeError, match="does not reconstruct"):
        validate_financial_only_rank_reconstructs(rows)
