import inspect

import pytest

from backend.scripts.research_collector_c5_combination import positive_headroom, score_v4, signed, weighted


@pytest.mark.parametrize("d", [0, 50, 90, 99, 100])
@pytest.mark.parametrize("f", [1 / 32, 1 / 16, 1 / 8, 1 / 4, 1 / 2])
def test_preferred_score_is_bounded(d, f):
    assert 0 <= signed(d, f, 2, 1) <= 100


def test_missing_inputs_are_unavailable_never_fallbacks():
    assert signed(None, .25, 2, 1) is None
    assert signed(90, None, 2, 1) is None


def test_frequency_neutral_returns_frozen_d_exactly():
    assert signed(83, 1 / 8, 2, 1) == pytest.approx(83)


def test_signed_modifier_has_frozen_semantic_caps():
    assert signed(80, 1 / 16, 2, 1) == pytest.approx(79)
    assert signed(80, 1 / 4, 2, 1) == pytest.approx(82)


def test_preferred_decomposition_reconstructs_score():
    d, f = 91, .2
    score = signed(d, f, 2, 1)
    assert d + (score - d) == pytest.approx(score)


def test_score_is_cohort_independent_and_uses_only_d_and_f():
    first = signed(91, .2, 2, 1)
    unrelated_sets = [(50, .01), (99, .9)]
    assert unrelated_sets and signed(91, .2, 2, 1) == first
    names = set(inspect.signature(signed).parameters)
    assert names == {"d", "f", "up", "down"}


def test_forbidden_constructs_are_not_formula_inputs():
    names = set().union(*(inspect.signature(fn).parameters for fn in (signed, score_v4, positive_headroom, weighted)))
    assert not names & {"price", "market_price", "artist", "treatment", "energy", "playability", "dual_path_depth", "p"}
