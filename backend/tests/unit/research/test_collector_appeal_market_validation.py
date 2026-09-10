import math

import numpy as np
import pytest

from backend.research.collector_appeal_market_validation.stats import (
    ComponentSpec,
    compare_components,
    grouped_leave_set_out_cv,
    model_specs,
    run_component_suite,
)


def _rows(*, n_sets=6, per_set=45, beta=0.025, scarcity_beta=1.4, interaction_beta=0.02, seed=17):
    rng = np.random.default_rng(seed)
    rows = []
    for set_index in range(n_sets):
        set_level = rng.normal(0, 0.25)
        for card_index in range(per_set):
            component = rng.uniform(10, 95)
            scarcity = rng.uniform(0.8, 3.1)
            centered_component = component - 52.5
            centered_scarcity = scarcity - 1.95
            log_price = (
                0.4
                + set_level
                + beta * component
                + scarcity_beta * scarcity
                + interaction_beta * centered_component * centered_scarcity
                + rng.normal(0, 0.08)
            )
            rows.append({
                "card_id": f"s{set_index}-c{card_index}",
                "set_id": f"set-{set_index}",
                "set_name": f"Set {set_index}",
                "era": "Era A" if set_index < n_sets // 2 else "Era B",
                "subject_type": "pokemon",
                "subject_cluster_key": f"pokemon-{card_index % 12}",
                "collector_component": component,
                "diagnostic_component": 100 - component,
                "log_price": log_price,
                "pull_scarcity": scarcity,
                "treatment_prestige": rng.choice([0.2, 0.5, 0.8]),
                "log_release_age": math.log1p(100 + set_index * 50),
                "is_secret": int(card_index % 11 == 0),
                "is_promo": 0,
                "is_mechanic_card": int(card_index % 7 == 0),
                "is_stage2": int(card_index % 5 == 0),
                "is_trainer": 0,
            })
    return rows


def _spec(**kwargs):
    return ComponentSpec(
        name="pokemon_component",
        column="collector_component",
        subject_types=("pokemon",),
        **kwargs,
    )


def test_model_contract_preserves_m0_to_m5_nested_questions():
    specs = model_specs(_spec())
    assert list(specs) == [
        "M0_controls_only",
        "M1_component",
        "M2_scarcity",
        "M3_component_scarcity",
        "M4_interaction",
        "M5_plus_treatment",
    ]
    assert "component::collector_component" in specs["M1_component"]
    assert "centered::pull_scarcity" in specs["M2_scarcity"]
    assert "interaction::collector_component::pull_scarcity" in specs["M4_interaction"]
    assert specs["M5_plus_treatment"][-1] == "treatment_prestige"


def test_leave_whole_set_out_predicts_every_card_exactly_once():
    rows = _rows()
    predictors = model_specs(_spec())["M3_component_scarcity"]
    cv = grouped_leave_set_out_cv(rows, predictors, _spec())
    assert cv is not None
    assert cv["n_folds"] == 6
    assert cv["n"] == len(rows)
    identities = {(row["set_id"], row["card_id"]) for row in cv["_predictions"]}
    assert len(identities) == len(rows)


def test_cv_centering_is_fit_on_training_sets_not_global_sample():
    rows = _rows(n_sets=4, per_set=20)
    for row in rows:
        if row["set_id"] == "set-3":
            row["collector_component"] += 500.0
    predictors = model_specs(_spec())["M3_component_scarcity"]
    cv = grouped_leave_set_out_cv(rows, predictors, _spec())
    fold = next(row for row in cv["folds"] if row["set_id"] == "set-3")
    training_values = [row["collector_component"] for row in rows if row["set_id"] != "set-3"]
    global_values = [row["collector_component"] for row in rows]
    assert fold["centering"]["collector_component"] == pytest.approx(np.mean(training_values))
    assert fold["centering"]["collector_component"] != pytest.approx(np.mean(global_values))


def test_component_increment_is_measured_in_mae_rmse_r2_and_spearman():
    suite = run_component_suite(_rows(), _spec(), bootstrap_draws=0)
    lift = suite["incremental_lift_out_of_sample"]["component_over_scarcity_M3_vs_M2"]
    assert lift is not None
    assert lift["mae_reduction"] > 0
    assert lift["rmse_reduction"] > 0
    assert lift["r2_gain"] > 0
    assert lift["spearman_gain"] > 0
    cv = suite["models"]["M3_component_scarcity"]["leave_whole_set_out_cv"]
    assert set(("mae", "rmse", "r2", "spearman")) <= set(cv)
    fit = suite["models"]["M3_component_scarcity"]["set_fixed_effects_fit"]
    assert fit["two_way_cluster_robust_se_set_subject"] is not None


def test_relationships_are_against_log_price_and_report_by_era():
    suite = run_component_suite(_rows(), _spec(), bootstrap_draws=0)
    relationships = suite["relationships"]
    assert relationships["spearman_vs_log_price"] is not None
    assert relationships["pearson_vs_log_price"] is not None
    assert set(relationships["by_era"]) == {"Era A", "Era B"}


def test_cross_bucket_pooling_requires_explicit_frozen_comparability_claim():
    with pytest.raises(ValueError, match="cross-bucket comparability"):
        ComponentSpec(
            name="unsafe_pooled",
            column="collector_component",
            subject_types=("pokemon", "trainer"),
        ).validate()
    ComponentSpec(
        name="frozen_final",
        column="collector_component",
        subject_types=("pokemon", "trainer"),
        role="final",
        cross_bucket_comparable=True,
    ).validate()


def test_component_comparison_reports_without_selecting_or_tuning_a_winner():
    rows = _rows()
    report = compare_components(
        rows,
        [
            _spec(),
            ComponentSpec(
                name="diagnostic_inverse",
                column="diagnostic_component",
                subject_types=("pokemon",),
                role="diagnostic",
            ),
        ],
        bootstrap_draws=0,
    )
    assert {row["component"] for row in report["component_summary"]} == {
        "pokemon_component", "diagnostic_inverse"
    }
    assert "winner" not in report
    assert "selected" not in report
    assert "do not tune or select V6" in report["methodology"]["selection_policy"]
