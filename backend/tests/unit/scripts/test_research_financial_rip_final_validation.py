import numpy as np

from backend.scripts.research_financial_rip_final_validation import (
    CANONICAL, CANDIDATES, PARAMETERS, cpt_value, cpt_values, p95_class,
    probability_weight,
)


def test_frozen_candidates_have_exact_architectures():
    assert CANDIDATES["P95_ONLY_25"]["weights"] == {
        "true_win_frequency": .25, "typical_retention": .20, "loss_resilience": .15,
        "realistic_upside": .25, "jackpot_upside": .10, "base_economic_efficiency": .05,
    }
    assert CANDIDATES["P95_ONLY_20"]["weights"] == {
        "true_win_frequency": .269231, "typical_retention": .215385, "loss_resilience": .161538,
        "realistic_upside": .20, "jackpot_upside": .10, "base_economic_efficiency": .053846,
    }
    assert all(abs(sum(c["weights"].values()) - 1.) < 1e-12 for c in CANDIDATES.values())


def test_cpt_grid_is_preregistered_and_contains_canonical_anchor():
    assert len(PARAMETERS) == 54
    assert CANONICAL in PARAMETERS
    assert probability_weight(0., .61) == 0.
    assert probability_weight(1., .61) == 1.


def test_vectorized_cpt_matches_single_parameter_evaluator():
    outcomes = np.asarray([0., 4., 10., 12., 50.])
    all_values = cpt_values(outcomes, 10.)
    assert len(all_values) == len(PARAMETERS)
    for index in (0, PARAMETERS.index(CANONICAL), len(PARAMETERS) - 1):
        assert abs(all_values[index] - cpt_value(outcomes, 10., PARAMETERS[index])) < 1e-10


def test_cpt_uses_purchase_cost_as_zero_reference_and_is_monotonic():
    low = np.asarray([5., 10., 15.]); high = low + 1.
    assert cpt_value(high, 10., CANONICAL) > cpt_value(low, 10., CANONICAL)
    assert cpt_value(np.asarray([10.]), 10., CANONICAL) == 0.


def test_p95_classes_are_descriptive_and_ordered_around_break_even():
    assert p95_class(.94) == "P95_BELOW_COST"
    assert p95_class(1.) == "P95_NEAR_BREAK_EVEN"
    assert p95_class(1.5) == "P95_MEANINGFUL_WIN"
    assert p95_class(2.) == "P95_LARGE_WIN"
