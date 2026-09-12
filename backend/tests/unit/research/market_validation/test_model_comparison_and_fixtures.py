from __future__ import annotations

import pytest

from backend.research.market_validation.model_comparison import (
    FrozenModelSnapshot,
    component_deltas,
    incremental_v7_after_v6,
    overall_vs_market,
)
from backend.research.market_validation.historical_fixtures import classify_discrepancy, classify_set_level


class TestFrozenModelSnapshot:
    def test_freeze_accepts_matching_lineage(self, synthetic_card_records):
        snap = FrozenModelSnapshot.freeze("fixture_v1", "fixture-run-1", synthetic_card_records, [])
        assert snap.model_run_id == "fixture-run-1"
        assert len(snap.card_records) == len(synthetic_card_records)

    def test_freeze_rejects_mixed_lineage(self, synthetic_card_records):
        contaminated = [dict(r, collector_model_run_id="some-other-run") for r in synthetic_card_records[:2]] + list(synthetic_card_records[2:])
        with pytest.raises(ValueError, match="lineage mismatch"):
            FrozenModelSnapshot.freeze("fixture_v1", "fixture-run-1", contaminated, [])

    def test_snapshot_is_immutable(self, synthetic_card_records):
        snap = FrozenModelSnapshot.freeze("fixture_v1", "fixture-run-1", synthetic_card_records, [])
        with pytest.raises(Exception):
            snap.model_version = "mutated"  # frozen dataclass should refuse


class TestOverallVsMarket:
    def test_reports_model_identity_and_correlation(self, synthetic_card_records):
        snap = FrozenModelSnapshot.freeze("fixture_v1", "fixture-run-1", synthetic_card_records, [])
        result = overall_vs_market(snap)
        assert result["modelVersion"] == "fixture_v1"
        assert result["modelRunId"] == "fixture-run-1"
        assert result["spearman"] is not None


class TestComponentDeltas:
    def test_identical_snapshots_have_zero_mean_delta(self, synthetic_card_records):
        records_a = [dict(r, collector_model_run_id="run-a") for r in synthetic_card_records]
        snap_a = FrozenModelSnapshot.freeze("v6", "run-a", records_a, [])
        snap_b = FrozenModelSnapshot.freeze("v6", "run-a", records_a, [])
        deltas = component_deltas(snap_a, snap_b, ["pokemon_subject_appeal"])
        assert deltas[0]["meanDelta"] == pytest.approx(0.0)

    def test_shifted_snapshot_shows_nonzero_delta(self, synthetic_card_records):
        base = [dict(r, collector_model_run_id="run-a") for r in synthetic_card_records]
        shifted = [dict(r, pokemon_subject_appeal=r["pokemon_subject_appeal"] + 10, collector_model_run_id="run-b") for r in synthetic_card_records]
        snap_a = FrozenModelSnapshot.freeze("v6", "run-a", base, [])
        snap_b = FrozenModelSnapshot.freeze("v7", "run-b", shifted, [])
        deltas = component_deltas(snap_a, snap_b, ["pokemon_subject_appeal"])
        assert deltas[0]["meanDelta"] == pytest.approx(10.0, abs=0.01)


class TestIncrementalV7AfterV6:
    def test_identical_v7_adds_no_incremental_information(self, synthetic_card_records):
        v6_records = [dict(r, final_card_collector_appeal=r["pokemon_subject_appeal"], collector_model_run_id="run-a") for r in synthetic_card_records]
        v7_records = [dict(r, final_card_collector_appeal=r["pokemon_subject_appeal"], collector_model_run_id="run-b") for r in synthetic_card_records]
        snap_v6 = FrozenModelSnapshot.freeze("v6", "run-a", v6_records, [])
        snap_v7 = FrozenModelSnapshot.freeze("v7", "run-b", v7_records, [])
        result = incremental_v7_after_v6(snap_v6, snap_v7)
        assert result["deltaOosR2"] is not None
        assert abs(result["deltaOosR2"]) < 0.05  # near-zero: V7 is identical to V6 here

    def test_reports_both_model_identities(self, synthetic_card_records):
        v6_records = [dict(r, final_card_collector_appeal=r["pokemon_subject_appeal"], collector_model_run_id="run-a") for r in synthetic_card_records]
        v7_records = [dict(r, final_card_collector_appeal=r["pokemon_subject_appeal"], collector_model_run_id="run-b") for r in synthetic_card_records]
        snap_v6 = FrozenModelSnapshot.freeze("v6", "run-a", v6_records, [])
        snap_v7 = FrozenModelSnapshot.freeze("v7", "run-b", v7_records, [])
        result = incremental_v7_after_v6(snap_v6, snap_v7)
        assert result["v6ModelRunId"] == "run-a"
        assert result["v7ModelRunId"] == "run-b"


class TestHistoricalFixtureCompatibility:
    def test_close_value_is_consistent(self):
        result = classify_discrepancy(0.375, "pure_pokemon_demand_raw_spearman")
        assert result["classification"] == "CONSISTENT_WITH_PRIOR_STUDY"

    def test_moderately_drifted_value_flagged_for_review(self):
        result = classify_discrepancy(0.45, "pure_pokemon_demand_raw_spearman")
        assert result["classification"] == "MODERATE_DRIFT_REVIEW_COHORT"

    def test_wildly_different_value_is_material_discrepancy(self):
        result = classify_discrepancy(0.9, "pure_pokemon_demand_raw_spearman")
        assert result["classification"] == "MATERIAL_DISCREPANCY_INVESTIGATE"

    def test_unknown_key_has_no_historical_reference(self):
        result = classify_discrepancy(0.5, "not_a_real_key")
        assert result["classification"] == "NO_HISTORICAL_REFERENCE"

    def test_missing_new_value_is_unavailable(self):
        result = classify_discrepancy(None, "treatment_raw_spearman")
        assert result["classification"] == "NEW_VALUE_UNAVAILABLE"

    def test_set_level_matching_finding(self):
        result = classify_set_level("scarcity_dominated_demand_x_scarcity_interaction")
        assert result["matchesPrior"] is True

    def test_set_level_non_matching_finding(self):
        result = classify_set_level("demand_dominated")
        assert result["matchesPrior"] is False
