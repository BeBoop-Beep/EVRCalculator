from copy import deepcopy
from pathlib import Path

import pytest

from backend.simulations.validations.packStateCalibration import (
    DIMENSION_STATE,
    MODE_STATE,
    build_model_assumption_inventory,
    compare_candidate_models,
    compare_distribution_dimension,
    compute_wilson_interval,
    generate_calibration_artifact,
    generate_research_bundle,
    run_confidence_aware_validation,
    run_pack_state_validation,
)


class ToyPhase6Config:
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
        "constraints": {
            "primary_hits": {"double rare", "ultra rare", "illustration rare"},
            "exclusive_hits": {"special illustration rare", "hyper rare", "mega hyper rare"},
            "bonus_hits": {"ace spec rare", "poke ball pattern", "master ball pattern"},
            "max_major_hits": 2,
            "max_non_regular_hits": 2,
            "max_exclusive_hits": 1,
        },
    }
    RARE_SLOT_PROBABILITY = {"rare": 0.7, "double rare": 0.2, "ultra rare": 0.1}
    REVERSE_SLOT_PROBABILITIES = {
        "slot_1": {"regular reverse": 1.0},
        "slot_2": {"regular reverse": 0.9, "special illustration rare": 0.1},
    }


class ToyFallbackConfig:
    ERA = ""
    SLOTS_PER_RARITY = {"common": 4, "uncommon": 3, "reverse": 2, "rare": 1}


def _observed_state_payload() -> dict:
    return {
        "set_id": "toy-phase6",
        "sample_size": 100,
        "counts_by_dimension": {
            "state": {
                "baseline": 68,
                "double_rare_only": 22,
                "sir_only": 10,
            }
        },
    }


def test_wilson_interval_on_known_toy_example_is_reasonable():
    interval = compute_wilson_interval(observed_count=50, sample_size=100, confidence_level=0.95)

    assert interval["method"] == "wilson"
    assert pytest.approx(0.4038, rel=0.01) == interval["lower"]
    assert pytest.approx(0.5962, rel=0.01) == interval["upper"]


def test_expected_probability_interval_inclusion_and_exclusion_are_reported():
    comparison = compare_distribution_dimension(
        dimension=DIMENSION_STATE,
        expected_probabilities={"baseline": 0.80},
        observed_counts={"baseline": 50},
        observed_sample_size=100,
    )

    row = comparison["comparison_rows"][0]
    assert row["expected_outside_observed_ci"] is True
    assert row["review_flag"] in {"flagged_for_review", "flagged_for_review_low_confidence"}

    comparison_inside = compare_distribution_dimension(
        dimension=DIMENSION_STATE,
        expected_probabilities={"baseline": 0.50},
        observed_counts={"baseline": 50},
        observed_sample_size=100,
    )
    row_inside = comparison_inside["comparison_rows"][0]
    assert row_inside["expected_within_observed_ci"] is True


def test_candidate_model_comparison_ranks_better_fit_higher():
    observed = {
        "counts_by_dimension": {
            "state": {
                "baseline": 90,
                "sir_only": 10,
            }
        }
    }
    candidates = {
        "better_candidate": {
            "expected_distributions": {
                "state": {
                    "baseline": 0.9,
                    "sir_only": 0.1,
                }
            }
        },
        "worse_candidate": {
            "expected_distributions": {
                "state": {
                    "baseline": 0.6,
                    "sir_only": 0.4,
                }
            }
        },
    }

    report = compare_candidate_models(
        observed_data=observed,
        candidate_models=candidates,
        modes=(MODE_STATE,),
        ranking_dimension=DIMENSION_STATE,
        ranking_metric="total_variation_distance",
    )

    assert report["ranking"][0]["candidate_name"] == "better_candidate"
    assert report["ranking"][0]["total_variation_distance"] < report["ranking"][1]["total_variation_distance"]


def test_assumption_inventory_labels_fallback_and_unresolved_areas():
    inventory = build_model_assumption_inventory(config=ToyFallbackConfig)

    assert inventory["sourced_truth_boundary"]["source_config_mutation_allowed"] is False
    assert inventory["model_resolution"]["has_explicit_pack_state_model"] is False
    assert any("rare_slot_probability table missing" in item for item in inventory["assumption_status"]["unresolved_assumptions"])
    assert any("reverse_slot_probabilities table missing" in item for item in inventory["assumption_status"]["unresolved_assumptions"])


def test_partial_observed_data_still_yields_confidence_aware_output():
    observed = {
        "sample_size": 40,
        "counts_by_dimension": {
            "state": {
                "baseline": 25,
                "double_rare_only": 10,
                "sir_only": 5,
            }
        },
    }

    result = run_confidence_aware_validation(
        config=ToyPhase6Config,
        observed_data=observed,
        modes=(MODE_STATE,),
        simulation_packs=5000,
        random_seed=7,
    )

    rows = result["validation_report"]["comparisons_by_dimension"][DIMENSION_STATE]["comparison_rows"]
    assert rows
    assert "observed_probability_ci_lower" in rows[0]
    assert "review_flag" in rows[0]


def test_research_bundle_exports_expected_phase6_outputs(tmp_path):
    validation_report = run_pack_state_validation(
        config=ToyPhase6Config,
        observed_data=_observed_state_payload(),
        modes=(MODE_STATE,),
        simulation_packs=5000,
        random_seed=5,
    )
    assumption_inventory = build_model_assumption_inventory(config=ToyPhase6Config)
    candidate_comparison = compare_candidate_models(
        observed_data=_observed_state_payload(),
        candidate_models={
            "current": {"expected_distributions": validation_report["expected_distributions"]},
        },
        modes=(MODE_STATE,),
    )

    exported = generate_research_bundle(
        validation_report=validation_report,
        output_dir=tmp_path,
        file_prefix="phase6_toy",
        model_assumption_inventory=assumption_inventory,
        candidate_model_comparison=candidate_comparison,
    )

    assert "summary_json" in exported
    assert "confidence_aware_residuals_json" in exported
    assert "assumption_inventory_json" in exported
    assert "candidate_model_comparison_json" in exported
    assert "manifest_json" in exported
    for path in exported.values():
        assert Path(path).exists()


def test_phase6_workflow_does_not_mutate_source_config_truth():
    original_model = deepcopy(ToyPhase6Config.PACK_STATE_MODEL)

    validation_report = run_pack_state_validation(
        config=ToyPhase6Config,
        observed_data=_observed_state_payload(),
        modes=(MODE_STATE,),
        simulation_packs=4000,
        random_seed=3,
    )
    artifact = generate_calibration_artifact(validation_report, dimension=DIMENSION_STATE)

    _ = run_confidence_aware_validation(
        config=ToyPhase6Config,
        observed_data=_observed_state_payload(),
        modes=(MODE_STATE,),
        simulation_packs=4000,
        random_seed=3,
        calibration_artifact=artifact,
    )

    assert ToyPhase6Config.PACK_STATE_MODEL == original_model
