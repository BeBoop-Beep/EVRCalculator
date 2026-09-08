import pytest
import inspect

from backend.scripts.research_collector_c3b_playability_lift import (
    bounded_score,
    confidence_factor,
    playability_status,
)


@pytest.mark.parametrize("subject", [0, 25, 50, 99, 100])
@pytest.mark.parametrize("playability", [0, 20, 100, None])
@pytest.mark.parametrize("strength", [0.10, 0.20, 0.40])
def test_bounded_lift_never_reduces_or_exceeds_bounds(subject, playability, strength):
    result = bounded_score(subject, playability, strength)
    assert subject <= result <= 100


def test_unknown_zero_and_subject_100_invariants():
    assert bounded_score(63, None, .2) == 63
    assert bounded_score(63, 0, .2) == 63
    assert bounded_score(100, 100, .2) == 100


def test_neutral_high_playability_gets_meaningful_bounded_lift():
    assert bounded_score(50, 100, .2) == 60


def test_threshold_policy_is_explicit_and_disjunctive():
    assert playability_status(3, 1) == "scoreable"
    assert playability_status(1, 20) == "scoreable"
    assert playability_status(2, 19) == "insufficient"
    assert playability_status(0, 0, has_evidence=False) == "unknown"


def test_confidence_dampens_fragile_evidence_and_converges_with_decks():
    assert confidence_factor(1, 2) < confidence_factor(3, 20) < confidence_factor(3, 200)
    assert confidence_factor(3, 200) == pytest.approx(1, abs=0.001)


def test_formula_has_no_market_artist_or_treatment_inputs():
    parameters = set(inspect.signature(bounded_score).parameters)
    assert parameters == {"subject", "playability", "lift_strength"}
