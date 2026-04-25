import pandas as pd
import pytest
from types import MappingProxyType
from unittest import mock

from backend.calculations.evr.derived_metrics import compute_chase_dependency_metrics
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
    CHASE_METRICS_EXCLUDED_RARITIES = set()

    def get_rarity_pack_multiplier(self):
        return {'common': 1, 'uncommon': 1}


class MockPatternExcludedConfig(MockTestConfig):
    RARITY_MAPPING = MappingProxyType(
        {
            'common': 'common',
            'rare': 'rare',
            'ultra rare': 'hits',
            'poke ball pattern': 'hits',
            'master ball pattern': 'hits',
        }
    )
    CHASE_METRICS_EXCLUDED_RARITIES = {"poke ball pattern"}


class MockPatternIncludedConfig(MockPatternExcludedConfig):
    CHASE_METRICS_EXCLUDED_RARITIES = set()


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
    assert top_hits.iloc[0]["ev_contribution"] == pytest.approx(0.2)


def test_calculate_evr_calculations_summary_reads_dynamic_rarity_keys_without_hardcoded_map():
    orchestrator = PackCalculationOrchestrator(MockTestConfig())
    expected_ev_totals_by_rarity = {
        "common": 1.0,
        "illustration_rare": 1.75,
        "special_illustration_rare": 2.25,
        "pokeball_pattern": 0.75,
        "master_ball_pattern": 1.25,
        "shiny_rare": 2.5,
        "shiny_ultra_rare": 3.5,
        "reverse": 0.5,
    }
    expected_total_manual_ev = sum(expected_ev_totals_by_rarity.values()) + 0.3 + 0.2

    with mock.patch.object(orchestrator, "calculate_reverse_ev", return_value=0.5):
        with mock.patch.object(
            orchestrator,
            "calculate_rarity_ev_totals",
            return_value=expected_ev_totals_by_rarity,
        ):
            with mock.patch.object(orchestrator, "calculate_hit_probability", return_value=(10.0, 90.0)):
                with mock.patch.object(
                    orchestrator,
                    "calculate_total_ev",
                    return_value=(expected_total_manual_ev, 5.5, 0.3, 0.2),
                ):
                    with mock.patch.object(
                        orchestrator,
                        "build_hit_and_non_hit_ev_contributions",
                        return_value={
                            "hit_ev_contributions": {"199/165": 2.5},
                            "non_hit_ev_contributions": {"001/165": 1.0},
                            "hit_ev": 2.5,
                            "non_hit_ev": 1.0,
                            "total_card_ev": 3.5,
                            "card_display_labels": {},
                        },
                    ):
                        results = orchestrator.calculate_evr_calculations(pd.DataFrame())

    summary = results["summary_data_for_manual_calcs"]
    ev_totals_by_rarity = results["ev_totals_by_rarity"]

    assert summary["ev_common_total"] == pytest.approx(1.0)
    assert summary["ev_reverse_total"] == pytest.approx(ev_totals_by_rarity["reverse"])
    assert summary["ev_pokeball_total"] == pytest.approx(ev_totals_by_rarity["pokeball_pattern"])
    assert summary["ev_master_ball_total"] == pytest.approx(ev_totals_by_rarity["master_ball_pattern"])
    assert summary["ev_IR_total"] == pytest.approx(ev_totals_by_rarity["illustration_rare"])
    assert summary["ev_SIR_total"] == pytest.approx(ev_totals_by_rarity["special_illustration_rare"])
    assert summary["ev_ultra_rare_total"] == pytest.approx(0.0)
    assert summary["ev_totals_by_rarity"] is ev_totals_by_rarity
    assert results["ev_totals"] is ev_totals_by_rarity
    assert summary["total_manual_ev"] == pytest.approx(expected_total_manual_ev)
    assert results["total_manual_ev"] == pytest.approx(expected_total_manual_ev)
    assert ev_totals_by_rarity["shiny_rare"] == pytest.approx(2.5)
    assert ev_totals_by_rarity["shiny_ultra_rare"] == pytest.approx(3.5)


def test_build_manual_summary_data_prefers_canonical_pattern_keys_and_derives_total_from_dynamic_map():
    orchestrator = PackCalculationOrchestrator(MockTestConfig())
    ev_totals_by_rarity = {
        "common": 0.25,
        "reverse": 0.5,
        "pokeball_pattern": 1.5,
        "poke_ball_pattern": 9.9,
        "master_ball_pattern": 2.5,
        "master_ball": 8.8,
        "shiny_rare": 3.75,
    }

    summary = orchestrator._build_manual_summary_data(
        ev_totals_by_rarity,
        regular_pack_contribution=999.0,
        god_pack_ev_contribution=0.4,
        demi_god_pack_ev_contribution=0.6,
        total_manual_ev=123.0,
    )

    assert summary["ev_totals_by_rarity"] is ev_totals_by_rarity
    assert summary["ev_pokeball_total"] == pytest.approx(ev_totals_by_rarity["pokeball_pattern"])
    assert summary["ev_master_ball_total"] == pytest.approx(ev_totals_by_rarity["master_ball_pattern"])
    assert summary["total_manual_ev"] == pytest.approx(sum(ev_totals_by_rarity.values()) + 1.0)

# ============================================================================
# Tests for build_hit_and_non_hit_ev_contributions (new method)
# ============================================================================
# Note: The build_hit_and_non_hit_ev_contributions method is tested indirectly
# through the integration tests (main_refactored.py flow) and through direct
# testing of its components (rarity_classification.py utilities and derived
# metrics). Unit tests of this method require complex mocking of the orchestrator
# class hierarchy and don't add value beyond those component tests.


def test_hit_pool_excludes_pokeball_keeps_masterball_and_preserves_total_card_ev():
    orchestrator = PackCalculationOrchestrator(MockPatternExcludedConfig())
    df = pd.DataFrame(
        {
            "Card Number": ["001", "002", "003", "004"],
            "Card Name": ["Poke A", "Master A", "Ultra A", "Common A"],
            "Rarity": ["poke ball pattern", "master ball pattern", "ultra rare", "common"],
            "EV": [5.0, 9.0, 3.0, 1.0],
        }
    )

    split = orchestrator.build_hit_and_non_hit_ev_contributions(df)

    assert split["hit_ev_contributions"] == {"002": 9.0, "003": 3.0}
    assert split["non_hit_ev_contributions"] == {"001": 5.0, "004": 1.0}
    assert split["hit_ev"] == pytest.approx(12.0)
    assert split["total_card_ev"] == pytest.approx(18.0)
    assert len(split["hit_ev_contributions"]) == 2


def test_excluding_pokeball_changes_chase_inputs_and_hhi_effective_count():
    df = pd.DataFrame(
        {
            "Card Number": ["001", "002", "003"],
            "Card Name": ["Poke A", "Master A", "Ultra A"],
            "Rarity": ["poke ball pattern", "master ball pattern", "ultra rare"],
            "EV": [5.0, 9.0, 3.0],
        }
    )

    include_split = PackCalculationOrchestrator(MockPatternIncludedConfig()).build_hit_and_non_hit_ev_contributions(df)
    exclude_split = PackCalculationOrchestrator(MockPatternExcludedConfig()).build_hit_and_non_hit_ev_contributions(df)

    include_chase = compute_chase_dependency_metrics(include_split["hit_ev_contributions"])
    exclude_chase = compute_chase_dependency_metrics(exclude_split["hit_ev_contributions"])

    # With poke ball included: shares [9/17, 5/17, 3/17] => HHI = 115/289
    assert include_chase["hhi_ev_concentration"] == pytest.approx(115.0 / 289.0)

    # With poke ball excluded: shares [9/12, 3/12] => HHI = 0.625
    assert exclude_chase["hhi_ev_concentration"] == pytest.approx(0.625)
    assert exclude_chase["effective_chase_count"] == pytest.approx(1.0 / 0.625)

    # Exclusion narrows chase input set and changes concentration metrics.
    assert set(include_split["hit_ev_contributions"].keys()) == {"001", "002", "003"}
    assert set(exclude_split["hit_ev_contributions"].keys()) == {"002", "003"}
    assert include_chase["hhi_ev_concentration"] != exclude_chase["hhi_ev_concentration"]

