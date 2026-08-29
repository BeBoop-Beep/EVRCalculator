import numpy as np

from backend.scripts.build_treatment_market_prestige_v3_round2 import GATES, independent_columns


def test_ranking_thresholds_are_preregistered_and_ordered():
    assert GATES["strong_ordering_probability"] > GATES["moderate_ordering_probability"] > .5


def test_incremental_value_gate_is_nonzero():
    assert GATES["meaningful_partial_r2"] > 0
    assert GATES["meaningful_cv_rmse_reduction"] > 0


def test_independent_columns_prioritize_controls_and_scarcity():
    base = np.asarray([0.0, 1.0, 0.0, 1.0])
    X = np.column_stack([base, base, 1-base])
    selected, names, dropped = independent_columns(X, ["rarity_designation:x", "exact_pull_scarcity", "control_mechanic:y"])
    assert "exact_pull_scarcity" in names
    assert "rarity_designation:x" in dropped
    assert selected.shape[1] == 2
