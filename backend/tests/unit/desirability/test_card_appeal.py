import pytest

from backend.desirability.card_appeal import (
    calculate_adjusted_card_appeal,
    calculate_scarcity_score,
    get_treatment_score,
)


def test_treatment_score_mapping_prioritizes_premium_treatments():
    assert get_treatment_score("Special Illustration Rare") == pytest.approx(96.0)
    assert get_treatment_score("Hyper Rare") == pytest.approx(82.0)
    assert get_treatment_score("Common") == pytest.approx(18.0)


def test_scarcity_score_uses_log_scaled_pull_probability():
    common_score = calculate_scarcity_score(1 / 10)
    rare_score = calculate_scarcity_score(1 / 1000)

    assert common_score is not None
    assert rare_score is not None
    assert rare_score > common_score
    assert rare_score <= 100


def test_scarcity_score_accepts_odds_denominator():
    assert calculate_scarcity_score(odds_denominator=500) == pytest.approx(calculate_scarcity_score(1 / 500))


def test_adjusted_card_appeal_blends_all_inputs():
    score = calculate_adjusted_card_appeal(80, 96, 70)
    assert score == pytest.approx(82.0)


def test_adjusted_card_appeal_renormalizes_when_scarcity_is_missing():
    score = calculate_adjusted_card_appeal(80, 96, None)
    expected = ((80 * 0.55) + (96 * 0.25)) / (0.55 + 0.25)
    assert score == pytest.approx(round(expected, 2))


def test_adjusted_card_appeal_handles_null_nan_and_non_pokemon_cards():
    assert calculate_adjusted_card_appeal(None, 96, 70) is None
    assert calculate_adjusted_card_appeal(float("nan"), 96, 70) is None
    assert calculate_adjusted_card_appeal("not-a-score", 96, 70) is None
