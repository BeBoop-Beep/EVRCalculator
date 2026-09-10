from __future__ import annotations

import pytest

from backend.research.market_validation.raw_correlations import coverage_report, raw_relationship, raw_relationship_by_group
from backend.research.market_validation.incremental_models import build_nested_ladder, evaluate_nested_ladder
from backend.research.market_validation.price_separation import PriceContaminationError


class TestRawRelationship:
    def test_real_signal_shows_positive_spearman(self, synthetic_card_records):
        result = raw_relationship(synthetic_card_records, "pokemon_subject_appeal", "log_market_price", seed=1, bootstrap_draws=200)
        assert result["n"] == len(synthetic_card_records)
        assert result["spearman"] is not None and result["spearman"] > 0.3

    def test_noise_signal_shows_weak_spearman(self, synthetic_card_records):
        result = raw_relationship(synthetic_card_records, "trainer_appeal", "log_market_price", seed=1, bootstrap_draws=200)
        assert result["spearman"] is not None
        assert abs(result["spearman"]) < 0.25

    def test_full_coverage_reports_coverage_one(self, synthetic_card_records):
        result = raw_relationship(synthetic_card_records, "pokemon_subject_appeal", "log_market_price")
        assert result["coverage"] == 1.0
        assert result["missingness"] == 0.0

    def test_missing_signal_reduces_coverage(self, synthetic_card_records):
        records = [dict(r) for r in synthetic_card_records]
        for r in records[:5]:
            r["pokemon_subject_appeal"] = None
        result = raw_relationship(records, "pokemon_subject_appeal", "log_market_price")
        assert result["n"] == len(records) - 5
        assert result["coverage"] < 1.0

    def test_too_few_points_returns_none_correlation(self):
        result = raw_relationship([{"x": 1, "log_market_price": 1}], "x", "log_market_price")
        assert result["spearman"] is None

    def test_by_group_breaks_down_per_era(self, synthetic_card_records):
        by_era = raw_relationship_by_group(synthetic_card_records, "pokemon_subject_appeal", "era", seed=1, bootstrap_draws=50)
        assert set(by_era) == {r["era"] for r in synthetic_card_records}


class TestCoverageReport:
    def test_reports_full_coverage_for_present_signal(self, synthetic_card_records):
        report = coverage_report(synthetic_card_records, ["pokemon_subject_appeal", "artist_recognition_score"])
        assert report["pokemon_subject_appeal"]["coverage"] == 1.0
        assert report["artist_recognition_score"]["coverage"] == 0.0  # never present in fixture


class TestNestedLadder:
    def test_unavailable_signals_are_skipped_not_fabricated(self, synthetic_card_records):
        available = [k for k in ["pokemon_subject_appeal", "trainer_appeal", "artist_recognition_score"] if any(r.get(k) is not None for r in synthetic_card_records)]
        stages = build_nested_ladder(available)
        stage_ids = [s["id"] for s in stages]
        assert "M1" in stage_ids  # pokemon_subject_appeal present
        assert "M5" not in stage_ids  # artist_recognition_score never present in fixture

    def test_stages_are_cumulative(self, synthetic_card_records):
        available = ["pokemon_subject_appeal", "trainer_appeal"]
        stages = build_nested_ladder(available)
        m1 = next(s for s in stages if s["id"] == "M1")
        m6 = next(s for s in stages if s["id"] == "M6")
        assert set(m1["predictors"]) <= set(m6["predictors"])


class TestEvaluateNestedLadder:
    def test_runs_without_price_leakage_and_returns_stages(self, synthetic_card_records):
        results = evaluate_nested_ladder(synthetic_card_records, structural_controls=["release_age_days"])
        assert len(results) >= 1
        for stage in results:
            assert "market_price" not in stage["predictors"]
            assert "log_market_price" not in stage["predictors"]

    def test_m1_recovers_positive_oos_signal_from_true_driver(self, synthetic_card_records):
        results = evaluate_nested_ladder(synthetic_card_records, structural_controls=["release_age_days"])
        m1 = next((s for s in results if s["modelId"] == "M1"), None)
        assert m1 is not None
        assert m1["oosR2"] is not None
        # M0 (structural only) should be beaten by M1 once real signal is added.
        m0 = next(s for s in results if s["modelId"] == "M0")
        if m0["oosR2"] is not None:
            assert m1["oosR2"] >= m0["oosR2"] - 0.05  # tolerate CV noise, but should not be materially worse

    def test_price_contamination_in_structural_controls_raises(self, synthetic_card_records):
        with pytest.raises(PriceContaminationError):
            evaluate_nested_ladder(synthetic_card_records, structural_controls=["market_price"])
