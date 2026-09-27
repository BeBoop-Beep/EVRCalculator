from copy import deepcopy
from decimal import Decimal
from uuid import UUID

import pytest

from backend.benchmarking.shadow_v1 import (
    BENCHMARK_KEY, calibration_analysis, certify_set_cohort,
    inherited_product_source, unavailable_era_rows,
)
from backend.domain.pokemon.rip_benchmark_v1 import BenchmarkError, metric_row


def uid(n):
    return str(UUID(int=n))


VERSIONS = {
    "overall_version": "overall-v12", "financial_version": "financial-v4",
    "chase_version": "chase-v1", "collector_version": "collector-v5",
    "score_source_policy": "live_v12_v4_storage",
}


def fixture():
    ids = [uid(i) for i in range(1, 23)]
    targets = []
    for rank, sid in enumerate(ids, 1):
        # Higher score owns the better (smaller) canonical rank.
        financial = Decimal(100 - rank)
        chase = Decimal(90 - rank)
        collector = Decimal(80 - rank)
        overall = Decimal(70 - rank)
        run = uid(100 + rank)
        targets.append({"set_id": sid, "calculation_run_id": run,
            "financialRipV4": {"score": financial, "rank": rank, "cohortSize": 22,
                "status": "ready", "rankable": True, "scoreVersion": "financial-v4"},
            "chaseAccessibility": {"modelScore": chase, "setRank": rank, "setCohortSize": 22,
                "chaseAccessibilityStatus": "ready", "chaseAccessibilityVersion": "chase-v1",
                "chaseAccessibilityMarketDate": "2026-09-15",
                "chaseAccessibilityCalculationRunId": run},
            "openingExperience": {"collectorAppeal": {"score": collector, "rank": rank,
                "cohortSize": 22, "version": "collector-v5"}},
            "overallRipV12": {"score": overall, "rank": rank, "cohortSize": 22,
                "status": "ready", "rankable": True, "version": "overall-v12",
                "components": {"financialRipV4": {"score": financial},
                    "chaseAccessibility": {"score": chase}, "collectorAppeal": {"score": collector}}}})
    return {"updated_at": "x", "ranking_payload_json": {"targets": targets, "meta": {
        "snapshot": {"publicationId": uid(500), "marketDate": "2026-09-17",
                     "simulationSourceMarketDate": "2026-09-15"},
        "publicAnalyticsCohort": {"overallRanked": {"publishable": True,
            "rankedSetCount": 22, "rankedSetIds": ids}},
        # A current standalone authority can coexist but may not replace embedded V5.
        "standaloneCollector": {"version": "collector-v7", "runId": uid(900)}}}}


def test_certifies_four_exact_sources_and_keeps_collector_lineages_separate():
    certified = certify_set_cohort(fixture(), VERSIONS)
    assert len(certified.rows) == 88
    assert {row["source_model_version"] for row in certified.rows
            if row["metric_key"] == "collector"} == {"collector-v5"}
    assert all(row["source_market_date"] == "2026-09-15" for row in certified.rows)
    assert all(row["rank"] is not None for row in certified.rows)


def test_source_date_and_exact_run_mismatches_fail_closed():
    bad = fixture()
    bad["ranking_payload_json"]["targets"][0]["chaseAccessibility"]["chaseAccessibilityMarketDate"] = "2026-09-14"
    with pytest.raises(BenchmarkError, match="exact coherent"):
        certify_set_cohort(bad, VERSIONS)
    bad = fixture()
    bad["ranking_payload_json"]["targets"][0]["chaseAccessibility"]["chaseAccessibilityCalculationRunId"] = uid(999)
    with pytest.raises(BenchmarkError, match="exact coherent"):
        certify_set_cohort(bad, VERSIONS)


def test_calibration_grid_exact_anchor_monotonic_and_rank_independent():
    rows = certify_set_cohort(fixture(), VERSIONS).rows
    report = calibration_analysis(rows)
    assert report["production_calibration_selected"] is False
    assert report["benchmark_key"] == BENCHMARK_KEY
    for metric in report["metrics"].values():
        for candidate in metric["candidates"]:
            assert Decimal(candidate["score_at_benchmark"]) == 5
            assert candidate["monotonicity_violations"] == 0
            assert candidate["rank_inversions"] == 0


def test_missing_calibration_preserves_source_value_and_rank_and_inheritance_drops_rank():
    set_row = certify_set_cohort(fixture(), VERSIONS).rows[1]  # chase
    assert set_row["benchmark_score"] is None and set_row["rank"] is not None
    product_id = uid(700)
    source = inherited_product_source(set_row, product_id=product_id, parent_set_id=set_row["entity_id"])
    product = metric_row(entity_type="sealed_product", entity_id=product_id,
        parent_set_id=set_row["entity_id"], metric_key="chase", market_date="2026-09-15", source=source)
    assert product["raw_model_value"] == set_row["raw_model_value"]
    assert product["rank"] is None and product["cohort_size"] is None


def test_era_models_are_unavailable_not_averaged():
    rows = unavailable_era_rows(era_id=uid(800), market_date="2026-09-25")
    assert len(rows) == 4
    assert {row["model_reason"] for row in rows} == {"unavailable_era_model_contract"}
    assert all(row["raw_model_value"] is None for row in rows)
