import pandas as pd
import pytest
from types import MappingProxyType
from unittest import mock

from backend.calculations.packCalcsRefractored.packCalculationOrchestrator import (
    PackCalculationOrchestrator,
)


# Mock config for testing
class MockTestConfig:
    """Mock base config with rarity mapping."""
    RARITY_MAPPING = MappingProxyType({
        'common': 'common',
        'uncommon': 'uncommon',
        'rare': 'rare',
        'double rare': 'hits',
        'ultra rare': 'hits',
        'illustration rare': 'hits',
        'special illustration rare': 'hits',
        'secret rare': 'hits',
    })
    PULL_RATE_MAPPING = MappingProxyType({'common': 10, 'rare': 20})
    RARE_SLOT_PROBABILITY = {'rare': 1.0}
    REVERSE_SLOT_PROBABILITIES = {
        'slot_1': {'regular reverse': 0.0},
        'slot_2': {'regular reverse': 0.0},
    }

    GOD_PACK_CONFIG = {'enabled': False}
    DEMI_GOD_PACK_CONFIG = {'enabled': False}

    def get_rarity_pack_multiplier(self):
        return {'common': 1, 'uncommon': 1}


def test_build_card_ev_contributions_uses_real_ev_column_and_groups_duplicates():
    df = pd.DataFrame(
        {
            "Card Name": ["Card A", "Card B", "Card A", "Card C"],
            "EV": [0.123456789, 1.25, 0.376543211, 0.0],
        }
    )

    contributions, labels = PackCalculationOrchestrator.build_card_ev_contributions(df)

    assert contributions["Card A"] == pytest.approx(0.5)
    assert contributions["Card B"] == pytest.approx(1.25)
    # Zero-EV cards are omitted so concentration metrics are not diluted by null contributors.
    assert "Card C" not in contributions


def test_build_card_ev_contributions_returns_empty_when_required_columns_missing():
    df = pd.DataFrame({"Card Name": ["Card A"], "Price ($)": [10.0]})
    contributions, labels = PackCalculationOrchestrator.build_card_ev_contributions(df)
    assert contributions == {}


def test_calculate_pack_ev_preserves_top_hit_mapping_columns_when_available():
    orchestrator = PackCalculationOrchestrator(MockTestConfig())
    df = pd.DataFrame(
        {
            "card_id": ["199/165"],
            "card_variant_id": ["variant-199/165"],
            "Card Name": ["Charizard ex"],
            "Card Number": ["199/165"],
            "rarity_group": ["hits"],
            "Rarity": ["special illustration rare"],
            "Price ($)": [45.0],
            "Effective_Pull_Rate": [225.0],
            "EV": [0.2],
        }
    )

    with mock.patch.object(orchestrator, "load_and_prepare_data", return_value=(df, 5.0)):
        with mock.patch.object(
            orchestrator,
            "calculate_evr_calculations",
            return_value={
                "total_manual_ev": 5.5,
                "card_ev_contributions": {"199/165": 0.2},
                "hit_ev_contributions": {"199/165": 0.2},
                "non_hit_ev_contributions": {},
                "hit_ev": 0.2,
                "non_hit_ev": 0.0,
                "total_card_ev": 0.2,
                "card_display_labels": {"199/165": {"card_name": "Charizard ex"}},
                "hit_probability_percentage": 10.0,
                "no_hit_probability_percentage": 90.0,
                "regular_pack_contribution": 0.0,
                "god_pack_ev_contribution": 0.0,
                "demi_god_pack_ev_contribution": 0.0,
                "summary_data_for_manual_calcs": {},
            },
        ):
            _results, _summary, top_hits, _pack_price = orchestrator.calculate_pack_ev(df)

    assert top_hits.iloc[0]["card_id"] == "199/165"
    assert top_hits.iloc[0]["card_variant_id"] == "variant-199/165"
    assert top_hits.iloc[0]["rank"] == 1
    assert top_hits.iloc[0]["EV"] == pytest.approx(0.2)

# ============================================================================
# Tests for build_hit_and_non_hit_ev_contributions (new method)
# ============================================================================
# Note: The build_hit_and_non_hit_ev_contributions method is tested indirectly
# through the integration tests (main_refactored.py flow) and through direct
# testing of its components (rarity_classification.py utilities and derived
# metrics). Unit tests of this method require complex mocking of the orchestrator
# class hierarchy and don't add value beyond those component tests.

