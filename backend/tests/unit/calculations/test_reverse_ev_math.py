import pandas as pd
import pytest

from backend.calculations.packCalcsRefractored.evrCalculator import PackEVCalculator


class _MockConfig:
    PULL_RATE_MAPPING = {}
    RARE_SLOT_PROBABILITY = {'rare': 1.0}

    def __init__(self, reverse_slot_probabilities, reverse_eligible_rarities):
        self.REVERSE_SLOT_PROBABILITIES = reverse_slot_probabilities
        self._reverse_eligible_rarities = reverse_eligible_rarities

    def get_rarity_pack_multiplier(self):
        return {'common': 1, 'uncommon': 1}

    def get_reverse_eligible_rarities(self):
        return self._reverse_eligible_rarities


def _build_calculator(slot_1_prob, slot_2_prob, eligible_rarities):
    config = _MockConfig(
        reverse_slot_probabilities={
            'slot_1': {'regular reverse': slot_1_prob, 'illustration rare': 1.0 - slot_1_prob},
            'slot_2': {'regular reverse': slot_2_prob, 'special illustration rare': 1.0 - slot_2_prob},
        },
        reverse_eligible_rarities=eligible_rarities,
    )
    return PackEVCalculator(config)


def test_reverse_slot_excludes_non_eligible_high_value_cards_from_pool():
    calculator = _build_calculator(
        slot_1_prob=0.2,
        slot_2_prob=0.0,
        eligible_rarities=[' common ', 'RARE'],
    )

    df = pd.DataFrame(
        {
            'Card Name': ['Common A', 'Rare A', 'IR Hit', 'SIR Hit', 'Ultra Hit'],
            'Rarity': [' common ', 'RARE', 'illustration rare', 'special illustration rare', 'ultra rare'],
            'Reverse Variant Price ($)': [1.0, 3.0, 500.0, 800.0, 1000.0],
        }
    )

    # Eligible pool is only Common A + Rare A => mean = 2.0, EV = 0.2 * 2.0 = 0.4
    slot_ev = calculator.calculate_reverse_ev_for_slot(df, 'slot_1')
    assert slot_ev == pytest.approx(0.4)


def test_total_reverse_ev_equals_sum_of_slot_probability_times_eligible_mean():
    slot_1_prob = 0.25
    slot_2_prob = 0.40
    calculator = _build_calculator(
        slot_1_prob=slot_1_prob,
        slot_2_prob=slot_2_prob,
        eligible_rarities=['common', 'uncommon', 'rare'],
    )

    df = pd.DataFrame(
        {
            'Card Name': ['Common A', 'Uncommon A', 'Rare A', 'IR Hit'],
            'Rarity': ['common', 'uncommon', 'rare', 'illustration rare'],
            'Reverse Variant Price ($)': [2.0, 4.0, 6.0, 999.0],
        }
    )

    eligible_mean = (2.0 + 4.0 + 6.0) / 3.0
    expected_total = (slot_1_prob + slot_2_prob) * eligible_mean

    total_reverse_ev = calculator.calculate_reverse_ev(df)
    assert total_reverse_ev == pytest.approx(expected_total)


def test_reverse_ev_scales_with_slot_probabilities_without_outside_slot_double_counting():
    full_calculator = _build_calculator(
        slot_1_prob=0.30,
        slot_2_prob=0.20,
        eligible_rarities=['common', 'uncommon', 'rare'],
    )
    half_calculator = _build_calculator(
        slot_1_prob=0.15,
        slot_2_prob=0.10,
        eligible_rarities=['common', 'uncommon', 'rare'],
    )

    df = pd.DataFrame(
        {
            'Card Name': ['Common A', 'Uncommon A', 'Rare A'],
            'Rarity': ['common', 'uncommon', 'rare'],
            'Reverse Variant Price ($)': [5.0, 10.0, 15.0],
            # Guard against accidental use of non-slot EV fields in reverse EV math.
            'EV_Reverse': [5000.0, 5000.0, 5000.0],
        }
    )

    full_total = full_calculator.calculate_reverse_ev(df)
    half_total = half_calculator.calculate_reverse_ev(df)

    assert half_total == pytest.approx(full_total * 0.5)


def test_reverse_ev_raises_when_regular_reverse_probability_has_no_eligible_pool():
    calculator = _build_calculator(
        slot_1_prob=0.2,
        slot_2_prob=0.0,
        eligible_rarities=['common'],
    )

    df = pd.DataFrame(
        {
            'Card Name': ['Illustration Hit', 'Master Ball Rare'],
            'Rarity': ['illustration rare', 'rare'],
            'Reverse Variant Price ($)': [100.0, 200.0],
        }
    )

    with pytest.raises(ValueError, match='eligible reverse pool is empty'):
        calculator.calculate_reverse_ev_for_slot(df, 'slot_1')


def test_reverse_ev_raises_for_invalid_slot_probability_sum():
    config = _MockConfig(
        reverse_slot_probabilities={
            'slot_1': {'regular reverse': 0.7, 'illustration rare': 0.4},
            'slot_2': {'regular reverse': 0.0, 'special illustration rare': 1.0},
        },
        reverse_eligible_rarities=['common'],
    )
    calculator = PackEVCalculator(config)

    df = pd.DataFrame(
        {
            'Card Name': ['Common A'],
            'Rarity': ['common'],
            'Reverse Variant Price ($)': [1.0],
        }
    )

    with pytest.raises(ValueError, match='must sum to 1.0'):
        calculator.calculate_reverse_ev_for_slot(df, 'slot_1')
