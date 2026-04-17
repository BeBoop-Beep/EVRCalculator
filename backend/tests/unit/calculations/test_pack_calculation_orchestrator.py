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


def test_build_card_ev_contributions_uses_real_ev_column_and_groups_duplicates():
    df = pd.DataFrame(
        {
            "Card Name": ["Card A", "Card B", "Card A", "Card C"],
            "EV": [0.123456789, 1.25, 0.376543211, 0.0],
        }
    )

    contributions = PackCalculationOrchestrator.build_card_ev_contributions(df)

    assert contributions["Card A"] == pytest.approx(0.5)
    assert contributions["Card B"] == pytest.approx(1.25)
    # Zero-EV cards are omitted so concentration metrics are not diluted by null contributors.
    assert "Card C" not in contributions


def test_build_card_ev_contributions_returns_empty_when_required_columns_missing():
    df = pd.DataFrame({"Card Name": ["Card A"], "Price ($)": [10.0]})
    contributions = PackCalculationOrchestrator.build_card_ev_contributions(df)
    assert contributions == {}

# ============================================================================
# Tests for build_hit_and_non_hit_ev_contributions (new method)
# ============================================================================
# Note: The build_hit_and_non_hit_ev_contributions method is tested indirectly
# through the integration tests (main_refactored.py flow) and through direct
# testing of its components (rarity_classification.py utilities and derived
# metrics). Unit tests of this method require complex mocking of the orchestrator
# class hierarchy and don't add value beyond those component tests.

