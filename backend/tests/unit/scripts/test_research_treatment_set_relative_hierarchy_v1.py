import numpy as np

from backend.scripts.research_treatment_set_relative_hierarchy_v1 import (
    EXPECTED_SET_ORDER,
    design,
    fit,
    set_levels,
)


def _row(set_name, high, low, y, scarcity=0.0, artist=0.0):
    return {
        "set_name": set_name,
        "high_treatment": high,
        "low_treatment": low,
        "mean_log_ratio": y,
        "scarcity_log_ratio": scarcity,
        "artist_delta": artist,
    }


def test_set_specific_design_recovers_levels():
    rows = []
    for i, set_name in enumerate(EXPECTED_SET_ORDER):
        ur = 0.2 + i * 0.05
        sir = 1.0 + i * 0.1
        rows += [
            _row(set_name, "Ultra Rare", "Double Rare", ur),
            _row(set_name, "Special Illustration Rare", "Double Rare", sir),
            _row(set_name, "Special Illustration Rare", "Ultra Rare", sir - ur),
        ]
    # Add two nuisance-identifying perturbations while preserving treatment truth.
    rows[0]["scarcity_log_ratio"] = 1.0
    rows[0]["mean_log_ratio"] += 0.4
    rows[4]["artist_delta"] = 100.0
    rows[4]["mean_log_ratio"] += 0.3

    beta, rank, condition = fit(rows)
    assert rank == 12
    assert condition < 30
    levels = set_levels(beta)
    for i, set_name in enumerate(EXPECTED_SET_ORDER):
        assert np.isclose(levels[set_name]["Ultra Rare"], 0.2 + i * 0.05)
        assert np.isclose(levels[set_name]["Special Illustration Rare"], 1.0 + i * 0.1)
    assert np.isclose(beta[-2], 0.4)
    assert np.isclose(beta[-1], 0.3)


def test_design_has_twelve_columns():
    rows = [_row(EXPECTED_SET_ORDER[0], "Ultra Rare", "Double Rare", 0.0)]
    X, y = design(rows)
    assert X.shape == (1, 12)
    assert y.shape == (1,)
