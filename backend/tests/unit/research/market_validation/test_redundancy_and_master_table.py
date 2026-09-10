from __future__ import annotations

from backend.research.market_validation.redundancy import (
    incremental_contribution_after,
    pairwise_redundancy,
    redundancy_matrix,
    vif_report,
)
from backend.research.market_validation.master_table import build_master_table, classify_signal_status, SignalStatus


class TestPairwiseRedundancy:
    def test_two_unrelated_signals_show_weak_correlation(self, synthetic_card_records):
        result = pairwise_redundancy(synthetic_card_records, "pokemon_subject_appeal", "trainer_appeal")
        assert abs(result["spearman"]) < 0.3

    def test_signal_perfectly_correlated_with_itself(self, synthetic_card_records):
        records = [dict(r, dup_appeal=r["pokemon_subject_appeal"]) for r in synthetic_card_records]
        result = pairwise_redundancy(records, "pokemon_subject_appeal", "dup_appeal")
        assert result["pearson"] == 1.0


class TestVif:
    def test_uncorrelated_predictors_have_low_vif(self, synthetic_card_records):
        report = vif_report(synthetic_card_records, ["pokemon_subject_appeal", "trainer_appeal"])
        for v in report.values():
            assert v is None or v < 5.0

    def test_duplicated_predictor_has_very_high_vif(self, synthetic_card_records):
        records = [dict(r, appeal_copy=r["pokemon_subject_appeal"] + 1e-9) for r in synthetic_card_records]
        report = vif_report(records, ["pokemon_subject_appeal", "appeal_copy"])
        assert report["pokemon_subject_appeal"] > 50 or report["pokemon_subject_appeal"] == float("inf")


class TestIncrementalContribution:
    def test_true_driver_adds_positive_delta_over_controls_only(self, synthetic_card_records):
        result = incremental_contribution_after(synthetic_card_records, ["release_age_days"], "pokemon_subject_appeal")
        assert result["deltaOosR2"] is not None
        assert result["deltaOosR2"] > 0

    def test_noise_signal_adds_little_after_true_driver_present(self, synthetic_card_records):
        result = incremental_contribution_after(synthetic_card_records, ["release_age_days", "pokemon_subject_appeal"], "trainer_appeal")
        assert result["deltaOosR2"] is not None
        assert result["deltaOosR2"] < 0.05


class TestRedundancyMatrix:
    def test_only_evaluates_pairs_present_in_dataset(self, synthetic_card_records):
        results = redundancy_matrix(synthetic_card_records)
        evaluated_pairs = {(r["a"], r["b"]) for r in results}
        assert ("artist_recognition_score", "treatment_prestige_score") not in evaluated_pairs  # never present in fixture


class TestSignalStatusClassification:
    def test_price_dependent_signal_is_always_reject(self):
        assert classify_signal_status(n=1000, delta_oos_r2=0.5, era_stable=True, price_independent=False) == SignalStatus.REJECT

    def test_small_n_is_insufficient_evidence(self):
        assert classify_signal_status(n=5, delta_oos_r2=0.5, era_stable=True, price_independent=True) == SignalStatus.INSUFFICIENT_EVIDENCE

    def test_strong_stable_positive_signal_is_core(self):
        assert classify_signal_status(n=200, delta_oos_r2=0.05, era_stable=True, price_independent=True) == SignalStatus.CORE

    def test_weak_positive_signal_is_positive_lift(self):
        assert classify_signal_status(n=200, delta_oos_r2=0.005, era_stable=True, price_independent=True) == SignalStatus.POSITIVE_LIFT

    def test_nonpositive_delta_is_diagnostic(self):
        assert classify_signal_status(n=200, delta_oos_r2=-0.01, era_stable=True, price_independent=True) == SignalStatus.DIAGNOSTIC


class TestMasterTable:
    def test_builds_rows_only_for_present_signals(self, synthetic_card_records):
        rows = build_master_table(
            synthetic_card_records,
            signal_keys=["pokemon_subject_appeal", "trainer_appeal", "artist_recognition_score"],
            base_predictor_keys=["release_age_days"],
        )
        signals_present = {r["signal"] for r in rows}
        assert "pokemon_subject_appeal" in signals_present
        assert "artist_recognition_score" not in signals_present  # V7 signal absent from fixture

    def test_true_driver_classified_favorably(self, synthetic_card_records):
        rows = build_master_table(
            synthetic_card_records,
            signal_keys=["pokemon_subject_appeal"],
            base_predictor_keys=["release_age_days"],
        )
        row = rows[0]
        assert row["status"] in (SignalStatus.CORE, SignalStatus.POSITIVE_LIFT)

    def test_price_independence_flag_forces_reject(self, synthetic_card_records):
        rows = build_master_table(
            synthetic_card_records,
            signal_keys=["pokemon_subject_appeal"],
            base_predictor_keys=["release_age_days"],
            price_independence_flags={"pokemon_subject_appeal": False},
        )
        assert rows[0]["status"] == SignalStatus.REJECT
