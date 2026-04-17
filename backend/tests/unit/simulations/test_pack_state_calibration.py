from copy import deepcopy
from pathlib import Path

import pytest

from backend.simulations.validations.packStateCalibration import (
    DIMENSION_AGGREGATE_HITS,
    DIMENSION_RARE_SLOT,
    DIMENSION_STATE,
    MODE_CONSISTENCY,
    MODE_RARITY,
    MODE_STATE,
    compare_distribution_dimension,
    compare_model_to_observed,
    compute_goodness_of_fit_metrics,
    export_calibration_results,
    generate_calibration_artifact,
    load_observed_pull_data,
    run_pack_state_validation,
)


class ToyCalibrationConfig:
    ERA = ""
    PACK_STATE_MODEL = {
        "state_probabilities": {
            "baseline": 0.70,
            "double_rare_only": 0.20,
            "sir_only": 0.10,
        },
        "state_outcomes": {
            "baseline": {
                "rare": "rare",
                "reverse_1": "regular reverse",
                "reverse_2": "regular reverse",
            },
            "double_rare_only": {
                "rare": "double rare",
                "reverse_1": "regular reverse",
                "reverse_2": "regular reverse",
            },
            "sir_only": {
                "rare": "rare",
                "reverse_1": "regular reverse",
                "reverse_2": "special illustration rare",
            },
        },
    }


def _observed_complete_payload() -> dict:
    return {
        "set_id": "toy-set",
        "set_name": "Toy Set",
        "sample_size": 100,
        "source_metadata": {"source": "unit-test"},
        "notes": "complete data",
        "counts_by_dimension": {
            "state": {
                "baseline": 68,
                "double_rare_only": 22,
                "sir_only": 10,
            },
            "rare_slot_rarity": {
                "rare": 78,
                "double rare": 22,
            },
            "reverse_1_rarity": {
                "regular reverse": 100,
            },
            "reverse_2_rarity": {
                "regular reverse": 90,
                "special illustration rare": 10,
            },
            "reverse_slot_rarity": {
                "regular reverse": 190,
                "special illustration rare": 10,
            },
            "aggregate_hit_frequency": {
                "any_non_regular_hit_pack": 32,
                "no_non_regular_hit_pack": 68,
                "two_or_more_non_regular_hit_pack": 10,
            },
        },
    }


def test_comparison_utility_aligns_expected_simulated_and_observed_distributions():
    report = run_pack_state_validation(
        config=ToyCalibrationConfig,
        observed_data=_observed_complete_payload(),
        modes=(MODE_STATE,),
        simulation_packs=40000,
        random_seed=11,
    )

    state_section = report["comparisons_by_dimension"][DIMENSION_STATE]
    rows = {row["category"]: row for row in state_section["comparison_rows"]}

    assert pytest.approx(0.70, abs=1e-9) == rows["baseline"]["expected_probability"]
    assert rows["baseline"]["simulated_probability"] is not None
    assert pytest.approx(0.68, abs=1e-9) == rows["baseline"]["observed_probability"]
    assert pytest.approx(70.0, abs=1e-9) == rows["baseline"]["expected_count_at_observed_n"]


def test_state_comparison_with_complete_observed_data_produces_metrics_and_residuals():
    report = compare_model_to_observed(
        config=ToyCalibrationConfig,
        observed_data=_observed_complete_payload(),
        modes=(MODE_STATE,),
        simulation_packs=30000,
        random_seed=7,
    )

    state_section = report["comparisons_by_dimension"][DIMENSION_STATE]
    assert state_section["metrics"] is not None
    assert "total_variation_distance" in state_section["metrics"]
    assert report["state_residuals"]["top_over_predicted"]
    assert report["state_residuals"]["top_under_predicted"]


def test_partial_observed_data_still_generates_usable_report():
    observed = {
        "sample_size": 100,
        "counts_by_dimension": {
            "state": {
                "baseline": 70,
                "double_rare_only": 20,
                "sir_only": 10,
            }
        },
    }
    report = run_pack_state_validation(
        config=ToyCalibrationConfig,
        observed_data=observed,
        modes=(MODE_STATE, MODE_RARITY),
        simulation_packs=20000,
        random_seed=19,
    )

    assert DIMENSION_STATE in report["comparisons_by_dimension"]
    assert DIMENSION_RARE_SLOT in report["comparisons_by_dimension"]
    rare_rows = report["comparisons_by_dimension"][DIMENSION_RARE_SLOT]["comparison_rows"]
    assert all(row["observed_probability"] is None for row in rare_rows)


def test_rarity_level_comparison_works_without_state_labels():
    observed = {
        "sample_size": 100,
        "counts_by_dimension": {
            "rare_slot_rarity": {
                "rare": 80,
                "double rare": 20,
            },
            "reverse_slot_rarity": {
                "regular reverse": 190,
                "special illustration rare": 10,
            },
            "aggregate_hit_frequency": {
                "any_non_regular_hit_pack": 30,
                "no_non_regular_hit_pack": 70,
                "two_or_more_non_regular_hit_pack": 9,
            },
        },
    }

    report = run_pack_state_validation(
        config=ToyCalibrationConfig,
        observed_data=observed,
        modes=(MODE_RARITY,),
        simulation_packs=15000,
        random_seed=5,
    )

    assert DIMENSION_STATE not in report["comparisons_by_dimension"]
    assert DIMENSION_RARE_SLOT in report["comparisons_by_dimension"]
    assert DIMENSION_AGGREGATE_HITS in report["comparisons_by_dimension"]


def test_monte_carlo_consistency_mode_shows_expected_and_simulated_are_close():
    report = run_pack_state_validation(
        config=ToyCalibrationConfig,
        observed_data=None,
        modes=(MODE_CONSISTENCY,),
        simulation_packs=120000,
        random_seed=3,
    )

    rows = report["comparisons_by_dimension"][DIMENSION_STATE]["comparison_rows"]
    max_abs = max(abs(float(row["difference_simulated_vs_expected"])) for row in rows)
    assert max_abs < 0.02


def test_goodness_of_fit_metrics_on_toy_example_are_correct():
    metrics = compute_goodness_of_fit_metrics(
        expected_probabilities={"a": 0.5, "b": 0.5},
        observed_probabilities={"a": 0.6, "b": 0.4},
        observed_counts={"a": 60, "b": 40},
        sample_size=100,
    )

    assert pytest.approx(0.1, abs=1e-9) == metrics["total_variation_distance"]
    assert pytest.approx(0.1, abs=1e-9) == metrics["mean_absolute_error"]
    assert metrics["chi_square"] is not None
    assert "aggregate_score" not in metrics


def test_chi_square_excludes_sparse_expected_categories():
    metrics = compute_goodness_of_fit_metrics(
        expected_probabilities={"common": 0.99, "ultra_rare": 0.01},
        observed_probabilities={"common": 0.95, "ultra_rare": 0.05},
        observed_counts={"common": 95, "ultra_rare": 5},
        sample_size=100,
        min_expected_count_for_chi_square=5.0,
    )

    assert "ultra_rare" in metrics["chi_square_categories_excluded"]
    assert "ultra_rare" not in metrics["chi_square_categories_used"]


def test_chi_square_matches_known_toy_example_for_eligible_categories():
    metrics = compute_goodness_of_fit_metrics(
        expected_probabilities={"a": 0.5, "b": 0.5},
        observed_probabilities={"a": 0.6, "b": 0.4},
        observed_counts={"a": 60, "b": 40},
        sample_size=100,
        min_expected_count_for_chi_square=5.0,
    )

    expected_chi_square = ((60 - 50) ** 2 / 50) + ((40 - 50) ** 2 / 50)
    assert pytest.approx(expected_chi_square, abs=1e-9) == metrics["chi_square"]


def test_kl_js_are_returned_with_explicit_smoothing_metadata():
    metrics = compute_goodness_of_fit_metrics(
        expected_probabilities={"a": 1.0, "b": 0.0},
        observed_probabilities={"a": 0.0, "b": 1.0},
        observed_counts={"a": 0, "b": 10},
        sample_size=10,
        smoothing=1e-9,
    )

    assert metrics["kl_divergence_observed_to_expected"] >= 0.0
    assert metrics["jensen_shannon_divergence"] >= 0.0
    assert pytest.approx(1e-9, abs=1e-18) == metrics["divergence_smoothing_epsilon"]


def test_calibration_artifact_generation_does_not_mutate_source_config_truth():
    original = deepcopy(ToyCalibrationConfig.PACK_STATE_MODEL)
    report = run_pack_state_validation(
        config=ToyCalibrationConfig,
        observed_data=_observed_complete_payload(),
        modes=(MODE_STATE,),
        simulation_packs=15000,
        random_seed=13,
    )

    artifact = generate_calibration_artifact(report, dimension=DIMENSION_STATE)
    assert ToyCalibrationConfig.PACK_STATE_MODEL == original
    assert "fitted" in artifact["label"]
    assert "empirical" in artifact["label"]
    assert "provisional" in artifact["label"]
    assert "heuristic" in artifact["label"]
    assert "not statistically fitted truth" in artifact["label"]
    assert "does not overwrite sourced config truth" in artifact["label"]
    assert artifact["artifact_method"] == "heuristic_blend"
    assert artifact["fit_status"] == "exploratory"
    assert artifact["not_for_automatic_config_promotion"] is True
    assert artifact["blend_weight_rationale"] == "sample_size_heuristic"
    assert artifact["non_destructive"] is True
    assert artifact["writes_to_source_config"] is False


def test_missing_and_zero_count_states_are_handled_safely():
    observed = {
        "counts_by_dimension": {
            "state": {
                "baseline": 0,
                "double_rare_only": 5,
                "unknown_new_state": 3,
            }
        }
    }
    report = compare_model_to_observed(
        config=ToyCalibrationConfig,
        observed_data=observed,
        modes=(MODE_STATE,),
        include_simulation=False,
    )

    rows = report["comparisons_by_dimension"][DIMENSION_STATE]["comparison_rows"]
    by_cat = {row["category"]: row for row in rows}
    assert "unknown_new_state" in by_cat
    assert by_cat["unknown_new_state"]["expected_probability"] == 0.0
    assert report["comparisons_by_dimension"][DIMENSION_STATE]["metrics"] is not None


def test_export_outputs_are_generated_with_tmp_path(tmp_path):
    report = run_pack_state_validation(
        config=ToyCalibrationConfig,
        observed_data=_observed_complete_payload(),
        modes=(MODE_STATE, MODE_RARITY),
        simulation_packs=10000,
        random_seed=17,
    )

    exported = export_calibration_results(
        validation_report=report,
        output_dir=tmp_path,
        file_prefix="toy_calibration",
    )

    assert "summary_json" in exported
    for path in exported.values():
        assert (tmp_path / Path(path).name).exists()


def test_load_observed_data_supports_state_alias_mapping():
    observed = {
        "counts_by_dimension": {
            "state": {
                "Double Rare Only": 20,
                "Baseline": 80,
            }
        }
    }
    loaded = load_observed_pull_data(
        observed,
        state_alias_map={
            "double_rare_only": "double_rare_only",
            "baseline": "baseline",
        },
    )

    assert loaded["counts_by_dimension"][DIMENSION_STATE]["double_rare_only"] == 20


def test_compare_distribution_dimension_reports_expected_count_at_observed_n():
    comparison = compare_distribution_dimension(
        dimension=DIMENSION_STATE,
        expected_probabilities={"baseline": 0.7, "double_rare_only": 0.3},
        simulated_probabilities={"baseline": 0.69, "double_rare_only": 0.31},
        observed_counts={"baseline": 71, "double_rare_only": 29},
        observed_sample_size=100,
    )

    rows = {row["category"]: row for row in comparison["comparison_rows"]}
    assert pytest.approx(70.0, abs=1e-9) == rows["baseline"]["expected_count_at_observed_n"]
