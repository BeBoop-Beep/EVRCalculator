import pandas as pd
import pytest
from unittest import mock

from backend.calculations.packCalcsRefractored.evrCalculator import PackEVCalculator


class _MockConfig:
    PULL_RATE_MAPPING = {}
    RARE_SLOT_PROBABILITY = {'rare': 1.0}
    REVERSE_SLOT_PROBABILITIES = {
        'slot_1': {'regular reverse': 0.0},
        'slot_2': {'regular reverse': 0.0},
    }
    GOD_PACK_CONFIG = {'enabled': False}
    DEMI_GOD_PACK_CONFIG = {'enabled': False}

    def get_rarity_pack_multiplier(self):
        return {'common': 1, 'uncommon': 1}


def _build_calculator():
    return PackEVCalculator(_MockConfig())


def test_calculate_rarity_ev_totals_includes_shiny_rarities_from_aggregation_key_and_total_ev_remains_additive(capsys):
    calculator = _build_calculator()
    df = pd.DataFrame(
        {
            'Card Name': ['Shiny A', 'Shiny B', 'Common A'],
            'aggregation_key': ['shiny_rare', 'shiny_ultra_rare', 'common'],
            'rarity_key': ['shiny_rare', 'shiny_ultra_rare', 'common'],
            'EV': [1.25, 2.5, 0.75],
        }
    )

    ev_totals = calculator.calculate_rarity_ev_totals(df, ev_reverse_total=0.25)
    output = capsys.readouterr().out

    with mock.patch.object(
        calculator,
        'calculate_god_packs_ev_contributions',
        return_value={
            'god_pack_ev': 0.0,
            'demi_god_pack_ev': 0.0,
        },
    ):
        total_ev, regular_pack_ev, god_pack_ev, demi_god_pack_ev = calculator.calculate_total_ev(
            ev_totals,
            df,
        )

    assert ev_totals['shiny_rare'] == pytest.approx(1.25)
    assert ev_totals['shiny_ultra_rare'] == pytest.approx(2.5)
    assert ev_totals['common'] == pytest.approx(0.75)
    assert ev_totals['reverse'] == pytest.approx(0.25)
    assert regular_pack_ev == pytest.approx(4.75)
    assert god_pack_ev == pytest.approx(0.0)
    assert demi_god_pack_ev == pytest.approx(0.0)
    assert total_ev == pytest.approx(4.75)
    assert '[RARITY_EV_BUCKETS] row-derived totals by aggregation_key (fallback rarity_key when blank):' in output
    assert 'shiny_rare: rows=1 ev_total=1.2500' in output
    assert 'shiny_ultra_rare: rows=1 ev_total=2.5000' in output
    assert 'reverse: rows=external ev_total=0.2500' in output


def test_calculate_rarity_ev_totals_prefers_pattern_classification_bucket_over_base_rarity(capsys):
    calculator = _build_calculator()
    df = pd.DataFrame(
        {
            'Card Name': ['Poke Ball Pattern A', 'Master Ball Pattern A', 'Rare A'],
            'aggregation_key': ['pokeball_pattern', 'master_ball_pattern', 'rare'],
            'rarity_key': ['common', 'rare', 'rare'],
            'EV': [0.3, 0.4, 0.5],
        }
    )

    ev_totals = calculator.calculate_rarity_ev_totals(df, ev_reverse_total=0.6)
    output = capsys.readouterr().out

    assert ev_totals['pokeball_pattern'] == pytest.approx(0.3)
    assert ev_totals['master_ball_pattern'] == pytest.approx(0.4)
    assert ev_totals['rare'] == pytest.approx(0.5)
    assert 'common' not in ev_totals
    assert ev_totals['reverse'] == pytest.approx(0.6)
    assert 'pokeball_pattern: rows=1 ev_total=0.3000' in output
    assert 'master_ball_pattern: rows=1 ev_total=0.4000' in output
    assert 'rare: rows=1 ev_total=0.5000' in output


def test_calculate_rarity_ev_totals_falls_back_to_rarity_key_when_aggregation_key_is_blank(capsys):
    calculator = _build_calculator()
    df = pd.DataFrame(
        {
            'Card Name': [
                'Common A',
                'Double Rare A',
                'Shiny Ultra Rare A',
            ],
            'aggregation_key': [
                'common',
                '',
                '',
            ],
            'rarity_key': [
                'common',
                'double_rare',
                'shiny_ultra_rare',
            ],
            'EV': [0.1, 0.2, 0.5],
        }
    )

    ev_totals = calculator.calculate_rarity_ev_totals(df, ev_reverse_total=0.6)
    output = capsys.readouterr().out

    expected_row_derived_totals = {
        'common': 0.1,
        'double_rare': 0.2,
        'shiny_ultra_rare': 0.5,
    }

    actual_row_derived_totals = {
        rarity_key: total
        for rarity_key, total in ev_totals.items()
        if rarity_key != 'reverse'
    }

    assert actual_row_derived_totals == pytest.approx(expected_row_derived_totals)
    assert sum(actual_row_derived_totals.values()) == pytest.approx(sum(expected_row_derived_totals.values()))
    assert ev_totals['reverse'] == pytest.approx(0.6)
    assert '[RARITY_EV_BUCKETS] skipped_rows_without_aggregation_key_or_rarity_key=' not in output
    assert 'common: rows=1 ev_total=0.1000' in output
    assert 'double_rare: rows=1 ev_total=0.2000' in output
    assert 'shiny_ultra_rare: rows=1 ev_total=0.5000' in output


def test_calculate_rarity_ev_totals_skips_rows_only_when_aggregation_key_and_rarity_key_are_both_missing(capsys):
    calculator = _build_calculator()
    df = pd.DataFrame(
        {
            'Card Name': ['Common A', 'Unknown Row'],
            'aggregation_key': ['common', ''],
            'rarity_key': ['common', ''],
            'EV': [0.1, 999.0],
        }
    )

    ev_totals = calculator.calculate_rarity_ev_totals(df, ev_reverse_total=0.6)
    output = capsys.readouterr().out

    assert ev_totals == pytest.approx(
        {
            'common': 0.1,
            'reverse': 0.6,
        }
    )
    assert '[RARITY_EV_BUCKETS] skipped_rows_without_aggregation_key_or_rarity_key=1' in output
    assert '[RARITY_EV_BUCKETS] excluded_unbucketed_ev_total=999.0000 bucket_source=aggregation_key->rarity_key' in output
    assert 'unbucketed_row: card_name=Unknown Row aggregation_key=<missing> rarity_key=<missing> ev=999.0000' in output


def test_calculate_rarity_ev_totals_falls_back_to_rarity_key_when_classification_key_is_absent(capsys):
    calculator = _build_calculator()
    df = pd.DataFrame(
        {
            'Card Name': ['Common A', 'Shiny A'],
            'rarity_key': ['common', 'shiny_rare'],
            'EV': [0.1, 0.2],
        }
    )

    ev_totals = calculator.calculate_rarity_ev_totals(df, ev_reverse_total=0.3)
    output = capsys.readouterr().out

    assert ev_totals == pytest.approx(
        {
            'common': 0.1,
            'shiny_rare': 0.2,
            'reverse': 0.3,
        }
    )
    assert '[RARITY_EV_BUCKETS] row-derived totals by rarity_key:' in output


def test_calculate_total_ev_sums_dynamic_rarity_map_without_hardcoded_bucket_list():
    calculator = _build_calculator()
    ev_totals_by_rarity = {
        'common': 0.75,
        'shiny_rare': 1.25,
        'shiny_ultra_rare': 2.5,
        'reverse': 0.25,
    }

    with mock.patch.object(
        calculator,
        'calculate_god_packs_ev_contributions',
        return_value={
            'god_pack_ev': 0.3,
            'demi_god_pack_ev': 0.2,
        },
    ):
        total_ev, regular_pack_ev, god_pack_ev, demi_god_pack_ev = calculator.calculate_total_ev(
            ev_totals_by_rarity,
            pd.DataFrame(),
        )

    assert regular_pack_ev == pytest.approx(sum(ev_totals_by_rarity.values()))
    assert god_pack_ev == pytest.approx(0.3)
    assert demi_god_pack_ev == pytest.approx(0.2)
    assert total_ev == pytest.approx(sum(ev_totals_by_rarity.values()) + 0.5)
