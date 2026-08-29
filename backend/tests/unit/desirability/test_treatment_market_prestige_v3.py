import numpy as np
import pytest

from backend.desirability.treatment_market_prestige_v3 import (
    centered_contributions,
    mechanic_flags,
    normalize_label,
    residualize_fixed_effects,
    stable_json_hash,
    treatment_contribution,
)


def test_normalization_does_not_infer_unknowns():
    assert normalize_label("Special Illustration Rare") == "special_illustration_rare"
    assert normalize_label(None) is None
    assert normalize_label("  ") is None


def test_mechanics_are_explicit_controls():
    assert mechanic_flags(["Stage 1", "MEGA", "Single Strike"]) == ("mega", "stage_1")


def test_treatment_contribution_excludes_controls():
    row = {"rarity_designation": "rare", "printing_finish": "holo", "set_id": "set-a"}
    coefficients = {"rarity_designation:rare": .4, "printing_finish:holo": .2, "set:set-a": 99, "species:x": 99}
    assert treatment_contribution(row, coefficients) == pytest.approx(.6)


def test_centering_is_within_era():
    rows = [
        {"era_id": "a", "rarity_designation": "common"},
        {"era_id": "a", "rarity_designation": "rare"},
        {"era_id": "b", "rarity_designation": "rare"},
    ]
    values = centered_contributions(rows, {"rarity_designation:rare": 1.0})
    assert np.allclose(values, [-.5, .5, 0])


def test_fixed_effect_residuals_have_zero_group_means():
    matrix = np.asarray([[1.0], [3.0], [2.0], [6.0]])
    result = residualize_fixed_effects(matrix, [["a", "a", "b", "b"]])[:, 0]
    assert np.allclose(result, [-1, 1, -2, 2])


def test_hash_is_order_stable_for_mapping_keys():
    assert stable_json_hash({"a": 1, "b": 2}) == stable_json_hash({"b": 2, "a": 1})
