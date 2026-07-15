"""Unit tests for the card-level market amplification study's estimator.

These pin the statistical machinery (not the live findings): fixed-effects
absorption, leave-whole-set-out grouping, and the study's structural rules.
"""

import math

import numpy as np
import pytest

from backend.scripts.build_card_market_amplification_study import (
    CONTROL_COLUMNS,
    _card_number,
    _is_secret,
    _printed_set_size,
    add_centered_terms,
    fit_within_ols,
    leave_one_set_out_cv,
    model_specs,
)


def _rows(n_sets=6, per_set=40, appeal_beta=0.02, interaction_beta=0.03, seed=7):
    rng = np.random.default_rng(seed)
    rows = []
    for set_index in range(n_sets):
        set_level_price = rng.normal(0, 2.0)  # set fixed effect
        for _ in range(per_set):
            appeal = rng.uniform(0, 100)
            scarcity = rng.uniform(1, 3)
            log_price = (
                set_level_price
                + appeal_beta * appeal
                + 1.5 * scarcity
                + interaction_beta * (appeal - 50) * (scarcity - 2)
                + rng.normal(0, 0.05)
            )
            rows.append(
                {
                    "set_id": f"set-{set_index}",
                    "set_name": f"Set {set_index}",
                    "era": "TestEra",
                    "log_price": log_price,
                    "appeal": appeal,
                    "pull_scarcity": scarcity,
                    "treatment_prestige": 0.5,
                    "log_release_age": math.log1p(100 * (set_index + 1)),
                    "is_secret": 0,
                    "is_promo": 0,
                    "is_mechanic_card": 0,
                    "is_stage2": 0,
                }
            )
    return rows


# ---------------------------------------------------------------------------
# Set-size / secret parsing (guards a real bug: deriving set size from the max
# numerator makes is_secret always 0, because the max numerator IS a secret)
# ---------------------------------------------------------------------------

def test_printed_set_size_reads_the_denominator_not_the_numerator():
    assert _printed_set_size({"printed_number": "245/91"}) == 91
    assert _card_number({"printed_number": "245/91"}) == 245
    assert _printed_set_size({"printed_number": "12"}) is None


def test_is_secret_flags_cards_numbered_above_the_printed_set_size():
    sizes = {"s": 91}
    secret = {"set_id": "s", "printed_number": "245/91"}
    normal = {"set_id": "s", "printed_number": "12/91"}
    assert _is_secret(secret, sizes) == 1
    assert _is_secret(normal, sizes) == 0


# ---------------------------------------------------------------------------
# Estimator behaviour
# ---------------------------------------------------------------------------

def test_within_ols_recovers_known_appeal_and_interaction_coefficients():
    rows = _rows()
    add_centered_terms(rows)
    fit = fit_within_ols(rows, ["appeal_c", "pull_scarcity_c", "appeal_x_scarcity"])
    assert fit is not None
    assert fit["coefficients"]["appeal_c"] == pytest.approx(0.02, abs=0.01)
    assert fit["coefficients"]["appeal_x_scarcity"] == pytest.approx(0.03, abs=0.01)
    assert fit["n_sets"] == 6
    assert fit["within_r2"] > 0.9


def test_set_fixed_effects_absorb_set_level_controls():
    # log_release_age is constant within a set, so set FE must absorb it; it is
    # reported as dropped rather than silently producing a bogus coefficient.
    rows = _rows()
    add_centered_terms(rows)
    fit = fit_within_ols(rows, ["log_release_age", "appeal_c"])
    assert fit is not None
    assert "log_release_age" in fit["dropped_collinear_columns"]
    assert "log_release_age" not in fit["coefficients"]


def test_leave_whole_set_out_cv_predicts_every_card_from_a_model_that_never_saw_its_set():
    rows = _rows()
    add_centered_terms(rows)
    cv = leave_one_set_out_cv(rows, ["appeal_c", "pull_scarcity_c"])

    assert cv is not None
    assert cv["n_folds"] == 6, "one fold per whole set"
    assert cv["n"] == len(rows), "every card predicted exactly once, out of sample"
    assert cv["mae"] > 0


def test_leave_whole_set_out_cv_needs_at_least_three_sets():
    rows = _rows(n_sets=2, per_set=30)
    add_centered_terms(rows)
    assert leave_one_set_out_cv(rows, ["appeal_c"]) is None


def test_model_specs_are_strictly_nested_m0_through_m5():
    specs = model_specs()
    assert specs["M0_controls_only"] == CONTROL_COLUMNS
    order = [
        "M0_controls_only",
        "M1_appeal",
        "M2_scarcity",
        "M3_appeal_scarcity",
        "M4_interaction",
        "M5_plus_prestige",
    ]
    assert list(specs) == order
    # M1/M2 each add exactly one term to M0; M3 nests both; M4 adds the
    # interaction; M5 adds prestige.
    assert set(specs["M1_appeal"]) - set(specs["M0_controls_only"]) == {"appeal_c"}
    assert set(specs["M2_scarcity"]) - set(specs["M0_controls_only"]) == {"pull_scarcity_c"}
    assert set(specs["M3_appeal_scarcity"]) > set(specs["M1_appeal"]) - {"appeal_c"} | {"appeal_c"}
    assert set(specs["M4_interaction"]) - set(specs["M3_appeal_scarcity"]) == {"appeal_x_scarcity"}
    assert set(specs["M5_plus_prestige"]) - set(specs["M4_interaction"]) == {"treatment_prestige"}


def test_centering_makes_interaction_main_effects_interpretable_at_the_mean():
    rows = _rows(n_sets=3, per_set=20)
    centering = add_centered_terms(rows)
    assert centering["appeal_mean"] == pytest.approx(
        float(np.mean([row["appeal"] for row in rows]))
    )
    assert float(np.mean([row["appeal_c"] for row in rows])) == pytest.approx(0.0, abs=1e-9)
    for row in rows:
        assert row["appeal_x_scarcity"] == pytest.approx(row["appeal_c"] * row["pull_scarcity_c"])
