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

import inspect

import pytest

from backend.db.services.best_open_price_authority import SOURCE_VERSIONS
from backend.scripts.research_best_open_price_bucket0 import (
    _verify_v12_parity,
    validate_financial_only_rank_reconstructs,
    validate_rank_column_contiguous,
)
import backend.scripts.research_best_open_price_v2 as research_best_open_price_v2
from backend.scripts.research_best_open_price_v2 import build_v2_row, run


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


def test_build_v2_row_populates_price_gap_fields():
    """Mirrors research_best_open_price_bucket2.py's execute_product() exactly:
    gap_dollars = (current_cents - threshold_cents) / 100.0
    gap_percent = (current_cents - threshold_cents) / current_cents."""
    rip_threshold = _threshold(14068, 9, 50.0, 80.0, 0.3, 1266.12)
    dual_result = {
        "ripResult": _search_result("exact", rip_threshold, 2, "rip-bench"),
        "financialResult": _search_result("exact", _threshold(14000, 9, 60.0, 70.0, 0.35, 1260.0), 2, "fin-bench"),
        "diagnostics": {},
    }
    current_price_cents = 15000
    row = build_v2_row(
        dual_result, source_row={"sealed_product_id": "p1", "financial_only_rank": 2, "budget_rank_v12": 2},
        current_price_cents=current_price_cents,
    )
    expected_gap_dollars = (current_price_cents - 14068) / 100.0
    expected_gap_percent = (current_price_cents - 14068) / current_price_cents
    assert row["priceGapDollars"] == pytest.approx(expected_gap_dollars)
    assert row["priceGapPercent"] == pytest.approx(expected_gap_percent)
    assert row["ripPriceGapDollars"] == pytest.approx(expected_gap_dollars)
    assert row["ripPriceGapPercent"] == pytest.approx(expected_gap_percent)


def test_build_v2_row_derives_current_price_cents_from_source_row_when_not_passed():
    rip_threshold = _threshold(14068, 9, 50.0, 80.0, 0.3, 1266.12)
    dual_result = {
        "ripResult": _search_result("exact", rip_threshold, 2, "rip-bench"),
        "financialResult": _search_result("exact", _threshold(14000, 9, 60.0, 70.0, 0.35, 1260.0), 2, "fin-bench"),
        "diagnostics": {},
    }
    row = build_v2_row(
        dual_result,
        source_row={
            "sealed_product_id": "p1", "financial_only_rank": 2, "budget_rank_v12": 2,
            "product_market_price": 150.0,
        },
    )
    assert row["priceGapDollars"] == pytest.approx((15000 - 14068) / 100.0)
    assert row["priceGapPercent"] == pytest.approx((15000 - 14068) / 15000)


def test_build_v2_row_price_gap_fields_are_none_without_current_price():
    dual_result = {
        "ripResult": _search_result("unresolved_extreme_quantity", None, 2, None),
        "financialResult": _search_result("unresolved_extreme_quantity", None, 2, None),
        "diagnostics": {},
    }
    row = build_v2_row(dual_result, source_row={"sealed_product_id": "p1", "financial_only_rank": 2, "budget_rank_v12": 2})
    assert row["priceGapDollars"] is None
    assert row["priceGapPercent"] is None
    assert row["ripPriceGapDollars"] is None
    assert row["ripPriceGapPercent"] is None


def test_run_calls_rip_axis_v12_parity_verification_before_per_product_loop():
    """run() must call _verify_v12_parity (the RIP-axis fail-closed guard,
    equivalent to validate_financial_only_rank_reconstructs on the Financial
    axis) on the whole source snapshot before any per-product search work.

    run() cannot be exercised end-to-end in this environment (no live
    Supabase client / pack-outcome artifacts), so this asserts the call is
    present, in the right place, by inspecting run()'s source -- the same
    limitation and approach already used for run()'s general untestability
    elsewhere in this file."""
    source = inspect.getsource(run)
    parity_call_index = source.index("_verify_v12_parity(")
    loop_index = source.index("for source in ordered:")
    assert parity_call_index != -1
    assert parity_call_index < loop_index, (
        "_verify_v12_parity must be called before the per-product loop, "
        "not interleaved with expensive per-product search work"
    )
    # Also confirm it is called with the *whole* source snapshot (all_rows),
    # not just the Full Market cohort subset (source_rows) -- matching
    # research_best_open_price_bucket2.py's own call site.
    assert "_verify_v12_parity(all_rows" in source


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


def test_run_fails_closed_on_current_v12_score_parity_failure():
    """Matrix item 29: the RIP-axis analogue of
    test_run_fails_closed_on_financial_score_parity_failure -- a persisted
    overall_rip_v12_score that does not reconstruct from its own inputs via
    compute_overall_rip_v12() must fail closed, exactly as
    validate_financial_only_rank_reconstructs() does for the Financial axis.
    _verify_v12_parity is the same RIP-axis guard run() calls (per
    test_run_calls_rip_axis_v12_parity_verification_before_per_product_loop
    above) against the whole source snapshot before any per-product search."""
    rows = [{
        "sealed_product_id": "a",
        "financial_rip_v4_score": 50.0,
        "collector_appeal_score": 60.0,
        "chase_accessibility_raw": 0.002,
        "overall_rip_v12_score": 999999.0,  # deliberately does not reconstruct
    }]
    with pytest.raises(RuntimeError, match="V12 parity failed"):
        _verify_v12_parity(rows, label="rip")


def test_run_itself_fails_closed_before_any_expensive_work(monkeypatch):
    """Actually calls run() (not just the validators it wraps) with a stub
    client and a monkeypatched _load_source returning a deliberately-bad-rank
    fixture (duplicate financial_only_rank), and asserts run() raises
    RuntimeError before _load_exact_source_products -- the expensive,
    per-cohort artifact-loading step -- is ever reached. This proves run()
    genuinely wires up its fail-closed guards in the right order, rather than
    merely calling the same validators in isolation as the tests above do."""
    valid_snapshot = {
        **SOURCE_VERSIONS,
        "id": "snapshot-1",
        "published_at": "2026-01-01T00:00:00+00:00",
        "market_date": "2026-01-01",
        "pinned_price_as_of": "2026-01-01",
        "cohort_fingerprint": "fp-1",
        "full_market_budget": "100.00",
        "eligible_cohort_count": "2",
        "ranked_under_v12_authority": True,
    }
    # Duplicate financial_only_rank -> validate_rank_column_contiguous must
    # raise RuntimeError before the per-product loop / artifact loading.
    bad_source_rows = [
        {"sealed_product_id": "a", "budget_rank_v12": 1, "financial_only_rank": 1},
        {"sealed_product_id": "b", "budget_rank_v12": 2, "financial_only_rank": 1},
    ]
    all_rows = list(bad_source_rows)

    def fake_load_source(client, snapshot_id):
        return valid_snapshot, bad_source_rows, all_rows

    def should_not_be_reached(*args, **kwargs):
        raise AssertionError("should not be reached")

    monkeypatch.setattr(research_best_open_price_v2, "_load_source", fake_load_source)
    monkeypatch.setattr(
        research_best_open_price_v2, "_load_exact_source_products", should_not_be_reached
    )

    with pytest.raises(RuntimeError, match="contiguous"):
        research_best_open_price_v2.run(
            client=object(),
            source_snapshot_id="snapshot-1",
            expected_source_authority_fingerprint="anything",
        )


def test_build_v2_row_populates_financial_price_gap_fields():
    """Minor #4: financialPriceGapDollars/financialPriceGapPercent use the
    same formula pattern as the RIP gap fields but against the Financial
    threshold's priceCents."""
    rip_threshold = _threshold(14068, 9, 50.0, 80.0, 0.3, 1266.12)
    financial_threshold = _threshold(14500, 10, 90.0, 40.0, 0.5, 1450.0)
    dual_result = {
        "ripResult": _search_result("exact", rip_threshold, 2, "rip-bench"),
        "financialResult": _search_result("exact", financial_threshold, 1, "fin-bench"),
        "diagnostics": {},
    }
    current_price_cents = 15000
    row = build_v2_row(
        dual_result, source_row={"sealed_product_id": "p1", "financial_only_rank": 1, "budget_rank_v12": 2},
        current_price_cents=current_price_cents,
    )
    expected_gap_dollars = (current_price_cents - 14500) / 100.0
    expected_gap_percent = (current_price_cents - 14500) / current_price_cents
    assert row["financialPriceGapDollars"] == pytest.approx(expected_gap_dollars)
    assert row["financialPriceGapPercent"] == pytest.approx(expected_gap_percent)


def test_build_v2_row_financial_price_gap_fields_are_none_without_current_price():
    dual_result = {
        "ripResult": _search_result("unresolved_extreme_quantity", None, 2, None),
        "financialResult": _search_result("unresolved_extreme_quantity", None, 2, None),
        "diagnostics": {},
    }
    row = build_v2_row(dual_result, source_row={"sealed_product_id": "p1", "financial_only_rank": 2, "budget_rank_v12": 2})
    assert row["financialPriceGapDollars"] is None
    assert row["financialPriceGapPercent"] is None
