"""
Tests for card identity correctness across the EV contribution and
hit/non-hit classification pipeline.

These tests verify that:
- Same-named cards with different card_numbers are NOT collapsed
- EV contribution grouping uses card_number (stable identity), not display name
- Hit classification uses the correct exact card row via card_number
- A common Charmander and an IR Charmander coexist without misclassification
- Double rare / ultra rare / SIR versions of same-named card are handled distinctly
- God-pack selection resolves intended cards by card_number
- hit_cards_count increases for a toy set with duplicate names when card_number is used
- Diagnostics are emitted for unmatched/ambiguous identity
"""

import io
import sys
import pytest
import pandas as pd
from types import MappingProxyType

from backend.configured_special_pack_resolver import resolve_configured_god_pack_rows
from backend.calculations.packCalcsRefractored.packCalculationOrchestrator import PackCalculationOrchestrator
from backend.calculations.utils.rarity_classification import filter_card_ev_by_hits
from backend.constants.tcg.pokemon.scarletAndVioletEra.blackBolt import SetBlackBoltConfig
from backend.constants.tcg.pokemon.scarletAndVioletEra.prismaticEvolutions import SetPrismaticEvolutionsConfig
from backend.constants.tcg.pokemon.scarletAndVioletEra.scarletAndViolet151 import Set151Config
from backend.constants.tcg.pokemon.scarletAndVioletEra.whiteFlare import SetWhiteFlareConfig


# ============================================================================
# Shared test config
# ============================================================================

class MockSVConfig:
    """Mock Scarlet & Violet era config."""
    RARITY_MAPPING = MappingProxyType({
        'common': 'common',
        'uncommon': 'uncommon',
        'rare': 'rare',
        'double rare': 'hits',
        'ultra rare': 'hits',
        'illustration rare': 'hits',
        'special illustration rare': 'hits',
    })
    PULL_RATE_MAPPING = MappingProxyType({
        'common': 66,
        'uncommon': 62,
        'rare': 26,
        'double rare': 90,
        'illustration rare': 188,
        'special illustration rare': 225,
        'ultra rare': 248,
    })


# ============================================================================
# Helper: build a minimal toy DataFrame with Card Number
# ============================================================================

def _make_df_with_card_number(rows):
    """Build a toy DataFrame matching the calculator's expected column schema."""
    df = pd.DataFrame(rows)
    # Ensure all required columns are present
    for col in ["Card Name", "Card Number", "Rarity", "Price ($)", "EV"]:
        if col not in df.columns:
            df[col] = ""
    return df


# ============================================================================
# Tests: build_card_ev_contributions with Card Number
# ============================================================================

class TestBuildCardEvContributionsWithCardNumber:

    def test_same_name_different_card_numbers_are_not_collapsed(self):
        """Two cards with the same name but different card_numbers must not be merged."""
        df = _make_df_with_card_number([
            {"Card Name": "Charizard ex", "Card Number": "006/165", "Rarity": "double rare",
             "Price ($)": 5.0, "EV": 0.055},
            {"Card Name": "Charizard ex", "Card Number": "199/165", "Rarity": "special illustration rare",
             "Price ($)": 45.0, "EV": 0.200},
        ])
        contributions, labels = PackCalculationOrchestrator.build_card_ev_contributions(df)
        # Must have TWO separate entries, not one collapsed "Charizard ex" entry
        assert len(contributions) == 2
        assert "006/165" in contributions
        assert "199/165" in contributions
        assert contributions["006/165"] == pytest.approx(0.055)
        assert contributions["199/165"] == pytest.approx(0.200)

    def test_card_display_labels_map_card_number_to_name(self):
        """card_display_labels must contain correct name/rarity metadata per card_number."""
        df = _make_df_with_card_number([
            {"Card Name": "Charizard ex", "Card Number": "006/165", "Rarity": "double rare",
             "Price ($)": 5.0, "EV": 0.055},
            {"Card Name": "Charizard ex", "Card Number": "199/165", "Rarity": "special illustration rare",
             "Price ($)": 45.0, "EV": 0.200},
        ])
        _, labels = PackCalculationOrchestrator.build_card_ev_contributions(df)
        assert "006/165" in labels
        assert labels["006/165"]["card_name"] == "Charizard ex"
        assert labels["006/165"]["rarity"] == "double rare"
        assert labels["006/165"]["card_number"] == "006/165"

        assert "199/165" in labels
        assert labels["199/165"]["card_name"] == "Charizard ex"
        assert labels["199/165"]["rarity"] == "special illustration rare"
        assert labels["199/165"]["card_number"] == "199/165"

    def test_charmander_common_and_ir_coexist_without_merging(self):
        """A common Charmander (004/165) and an IR Charmander (168/165) must be separate."""
        df = _make_df_with_card_number([
            {"Card Name": "Charmander", "Card Number": "004/165", "Rarity": "common",
             "Price ($)": 0.10, "EV": 0.0015},
            {"Card Name": "Charmander", "Card Number": "168/165", "Rarity": "illustration rare",
             "Price ($)": 8.0, "EV": 0.043},
        ])
        contributions, labels = PackCalculationOrchestrator.build_card_ev_contributions(df)
        assert len(contributions) == 2
        assert "004/165" in contributions
        assert "168/165" in contributions
        # Common Charmander has tiny EV; IR Charmander has larger EV
        assert contributions["168/165"] > contributions["004/165"]

    def test_legacy_fallback_uses_card_name_when_no_card_number_column(self):
        """Without Card Number column, falls back to card-name grouping."""
        df = pd.DataFrame([
            {"Card Name": "Pikachu", "Rarity": "rare", "Price ($)": 1.0, "EV": 0.05},
            {"Card Name": "Raichu", "Rarity": "rare", "Price ($)": 2.0, "EV": 0.10},
        ])
        contributions, labels = PackCalculationOrchestrator.build_card_ev_contributions(df)
        assert "Pikachu" in contributions
        assert "Raichu" in contributions

    def test_zero_ev_cards_excluded_from_contributions(self):
        """Zero-EV cards must not appear in the contribution dict."""
        df = _make_df_with_card_number([
            {"Card Name": "Charizard ex", "Card Number": "199/165", "Rarity": "special illustration rare",
             "Price ($)": 45.0, "EV": 0.200},
            {"Card Name": "Common Filler", "Card Number": "001/165", "Rarity": "common",
             "Price ($)": 0.01, "EV": 0.0},
        ])
        contributions, _ = PackCalculationOrchestrator.build_card_ev_contributions(df)
        assert "001/165" not in contributions
        assert "199/165" in contributions

    def test_hit_cards_count_is_correct_for_set_with_duplicate_names(self):
        """hit_cards_count must reflect unique card_numbers, not unique names."""
        # 5 distinct cards: 2 named "Charizard ex" (different rarities), 3 others
        df = _make_df_with_card_number([
            {"Card Name": "Charizard ex", "Card Number": "006/165", "Rarity": "double rare",
             "Price ($)": 5.0, "EV": 0.055},
            {"Card Name": "Charizard ex", "Card Number": "199/165", "Rarity": "special illustration rare",
             "Price ($)": 45.0, "EV": 0.200},
            {"Card Name": "Pikachu ex", "Card Number": "085/165", "Rarity": "double rare",
             "Price ($)": 4.0, "EV": 0.044},
            {"Card Name": "Mew ex", "Card Number": "193/165", "Rarity": "ultra rare",
             "Price ($)": 12.0, "EV": 0.048},
            {"Card Name": "Alakazam ex", "Card Number": "201/165", "Rarity": "special illustration rare",
             "Price ($)": 30.0, "EV": 0.133},
        ])
        contributions, _ = PackCalculationOrchestrator.build_card_ev_contributions(df)
        # All 5 distinct card_numbers must be tracked
        assert len(contributions) == 5


# ============================================================================
# Tests: filter_card_ev_by_hits with Card Number
# ============================================================================

class TestFilterCardEvByHitsWithCardNumber:

    def test_hit_classification_uses_correct_rarity_for_each_card_number(self):
        """When Card Number is present, each card is classified by its own rarity, not by name."""
        df = _make_df_with_card_number([
            {"Card Name": "Charizard ex", "Card Number": "006/165", "Rarity": "double rare",
             "Price ($)": 5.0, "EV": 0.055},
            {"Card Name": "Charizard ex", "Card Number": "199/165", "Rarity": "special illustration rare",
             "Price ($)": 45.0, "EV": 0.200},
        ])
        contributions = {"006/165": 0.055, "199/165": 0.200}
        hit, non_hit = filter_card_ev_by_hits(contributions, df, MockSVConfig())
        # Both are hits (double rare and SIR are both 'hits' in MockSVConfig)
        assert "006/165" in hit
        assert "199/165" in hit
        assert non_hit == {}

    def test_charmander_common_non_hit_ir_charmander_is_hit(self):
        """Common Charmander must be non-hit; IR Charmander must be hit."""
        df = _make_df_with_card_number([
            {"Card Name": "Charmander", "Card Number": "004/165", "Rarity": "common",
             "Price ($)": 0.10, "EV": 0.0015},
            {"Card Name": "Charmander", "Card Number": "168/165", "Rarity": "illustration rare",
             "Price ($)": 8.0, "EV": 0.043},
        ])
        contributions = {"004/165": 0.0015, "168/165": 0.043}
        hit, non_hit = filter_card_ev_by_hits(contributions, df, MockSVConfig())
        assert "168/165" in hit, "IR Charmander (168/165) must be a hit"
        assert "004/165" in non_hit, "Common Charmander (004/165) must be non-hit"

    def test_ir_charmander_is_not_misclassified_as_common(self):
        """Without card_number, name lookup uses first row. With card_number, each row is independent."""
        # Build df where common Charmander appears first (would cause wrong classification in legacy path)
        df = _make_df_with_card_number([
            {"Card Name": "Charmander", "Card Number": "004/165", "Rarity": "common",
             "Price ($)": 0.10, "EV": 0.0015},
            {"Card Name": "Charmander", "Card Number": "168/165", "Rarity": "illustration rare",
             "Price ($)": 8.0, "EV": 0.043},
        ])
        # In old name-based path with iloc[0], the IR Charmander would be misclassified as common
        # (because common Charmander appears first). The card_number path must correctly classify.
        contributions = {"168/165": 0.043}  # Only the IR one
        hit, non_hit = filter_card_ev_by_hits(contributions, df, MockSVConfig())
        # Must be a hit — if it picked the wrong row (common first), this would fail
        assert "168/165" in hit, "IR Charmander must be classified as hit, not common"
        assert "168/165" not in non_hit

    def test_double_rare_ultra_rare_sir_all_classified_as_hits(self):
        """All hit-rarity variants of same-named cards must be independently classified as hits."""
        df = _make_df_with_card_number([
            {"Card Name": "Pikachu ex", "Card Number": "085/165", "Rarity": "double rare",
             "Price ($)": 4.0, "EV": 0.044},
            {"Card Name": "Pikachu ex", "Card Number": "100/165", "Rarity": "ultra rare",
             "Price ($)": 15.0, "EV": 0.060},
            {"Card Name": "Pikachu ex", "Card Number": "206/165", "Rarity": "special illustration rare",
             "Price ($)": 55.0, "EV": 0.244},
        ])
        contributions = {"085/165": 0.044, "100/165": 0.060, "206/165": 0.244}
        hit, non_hit = filter_card_ev_by_hits(contributions, df, MockSVConfig())
        assert "085/165" in hit
        assert "100/165" in hit
        assert "206/165" in hit
        assert non_hit == {}

    def test_unmatched_card_number_classified_as_non_hit_with_diagnostic(self, capsys):
        """An unmatched card_number must be classified non-hit AND emit a diagnostic."""
        df = _make_df_with_card_number([
            {"Card Name": "Charizard ex", "Card Number": "199/165", "Rarity": "special illustration rare",
             "Price ($)": 45.0, "EV": 0.200},
        ])
        # Contribution key that doesn't exist in df
        contributions = {"999/165": 0.100}
        hit, non_hit = filter_card_ev_by_hits(contributions, df, MockSVConfig())
        assert "999/165" in non_hit, "Unmatched card must be classified as non-hit (conservative)"
        captured = capsys.readouterr()
        assert "IDENTITY_UNMATCHED" in captured.out or "unmatched" in captured.out.lower(), \
            "A diagnostic warning must be printed for unmatched card_number"

    def test_hit_ev_composition_uses_corrected_hit_pool(self):
        """Total hit EV must sum only the true hit-rarity cards, not the non-hits."""
        df = _make_df_with_card_number([
            {"Card Name": "Charmander", "Card Number": "004/165", "Rarity": "common",
             "Price ($)": 0.10, "EV": 0.001},
            {"Card Name": "Charmander", "Card Number": "168/165", "Rarity": "illustration rare",
             "Price ($)": 8.0, "EV": 0.043},
            {"Card Name": "Charizard ex", "Card Number": "199/165", "Rarity": "special illustration rare",
             "Price ($)": 45.0, "EV": 0.200},
        ])
        contributions = {"004/165": 0.001, "168/165": 0.043, "199/165": 0.200}
        hit, non_hit = filter_card_ev_by_hits(contributions, df, MockSVConfig())
        total_hit_ev = sum(hit.values())
        total_non_hit_ev = sum(non_hit.values())
        assert total_hit_ev == pytest.approx(0.043 + 0.200)
        assert total_non_hit_ev == pytest.approx(0.001)


# ============================================================================
# Tests: structured config shape and resolver behavior
# ============================================================================

class TestStructuredGodPackConfigRegression:

    def test_set_151_god_pack_config_uses_structured_fixed_card_objects(self):
        """151 must keep fixed packs expressed as structured card objects with number+rarity."""
        config = Set151Config.GOD_PACK_CONFIG
        packs = config["strategy"]["packs"]

        assert config["enabled"] is True
        assert config["strategy"]["type"] == "fixed"
        assert packs[0]["name"] == "Charmander Line"
        assert packs[0]["cards"][0] == {
            "name": "Charmander",
            "number": "168/165",
            "rarity": "illustration rare",
        }
        assert packs[0]["cards"][2] == {
            "name": "Charizard ex",
            "number": "199/165",
            "rarity": "special illustration rare",
        }

        for pack in packs:
            for card in pack["cards"]:
                assert card["name"]
                assert card["number"]
                assert card["rarity"]

    def test_prismatic_god_pack_config_keeps_name_only_master_ball_entry(self):
        """Prismatic must keep the name-only master ball object and numbered SIR objects."""
        config = SetPrismaticEvolutionsConfig.GOD_PACK_CONFIG
        cards = config["strategy"]["cards"]

        assert config["strategy"]["type"] == "fixed"
        assert cards[0]["name"] == "Eevee (Master Ball Pattern)"
        assert cards[0]["rarity"] == "master ball pattern"
        assert "number" not in cards[0]
        assert cards[1] == {
            "name": "Eevee ex",
            "number": "167/131",
            "rarity": "special illustration rare",
        }

        for card in cards[1:]:
            assert card["name"]
            assert card["number"]
            assert card["rarity"]

    @pytest.mark.parametrize("config_cls", [SetWhiteFlareConfig, SetBlackBoltConfig])
    def test_white_flare_and_black_bolt_configs_remain_random_rarity_rule_based(self, config_cls):
        """Black Bolt and White Flare must stay on the random rarity-rule config path."""
        config = config_cls.GOD_PACK_CONFIG

        assert config["enabled"] is True
        assert config["strategy"]["type"] == "random"
        assert config["strategy"]["rules"]["rarities"] == {
            "illustration rare": 9,
            "special illustration rare": 1,
        }
        assert "cards" not in config["strategy"]
        assert "packs" not in config["strategy"]


class TestConfiguredSpecialPackResolver:

    def _make_df_for_special_type_disambiguation(self):
        """Rows that only differ by Special Type for resolver disambiguation tests."""
        return _make_df_with_card_number([
            {
                "Card Name": "Eevee",
                "Card Number": "074/131",
                "Rarity": "common",
                "Special Type": "master ball",
                "Price ($)": 9.75,
                "EV": 0.050,
            },
            {
                "Card Name": "Eevee",
                "Card Number": "074/131",
                "Rarity": "common",
                "Special Type": "pokeball",
                "Price ($)": 1.25,
                "EV": 0.010,
            },
        ])

    def test_structured_object_matching_prefers_card_number_for_same_name_cards(self):
        """Structured objects with numbers must resolve the intended row when names collide."""
        df = _make_df_with_card_number([
            {"Card Name": "Charizard ex", "Card Number": "006/165", "Rarity": "double rare",
             "Price ($)": 5.0, "EV": 0.055},
            {"Card Name": "Charizard ex", "Card Number": "199/165", "Rarity": "special illustration rare",
             "Price ($)": 45.0, "EV": 0.200},
        ])

        resolved = resolve_configured_god_pack_rows(
            [{"name": "Charizard ex", "number": "199/165", "rarity": "special illustration rare"}],
            df,
            context_label="test.structured_number",
        )

        assert len(resolved) == 1
        assert resolved.iloc[0]["Card Number"] == "199/165"
        assert resolved.iloc[0]["Rarity"] == "special illustration rare"
        assert resolved.iloc[0]["Price ($)"] == pytest.approx(45.0)

    def test_structured_object_matching_without_number_supports_prismatic_master_ball_entry(self):
        """The Prismatic master ball entry must resolve from a structured object without a card number."""
        df = _make_df_with_card_number([
            {"Card Name": "Eevee (Master Ball Pattern)", "Card Number": "", "Rarity": "poke ball pattern",
             "Price ($)": 1.25, "EV": 0.010},
            {"Card Name": "Eevee (Master Ball Pattern)", "Card Number": "", "Rarity": "master ball pattern",
             "Price ($)": 9.75, "EV": 0.050},
        ])

        resolved = resolve_configured_god_pack_rows(
            [SetPrismaticEvolutionsConfig.GOD_PACK_CONFIG["strategy"]["cards"][0]],
            df,
            context_label="test.prismatic_master_ball",
        )

        assert len(resolved) == 1
        assert resolved.iloc[0]["Card Name"] == "Eevee (Master Ball Pattern)"
        assert resolved.iloc[0]["Rarity"] == "master ball pattern"
        assert resolved.iloc[0]["Price ($)"] == pytest.approx(9.75)

    def test_special_type_disambiguates_same_name_number_and_rarity(self):
        """Providing special_type must select the intended row when other identity fields are identical."""
        df = self._make_df_for_special_type_disambiguation()

        resolved = resolve_configured_god_pack_rows(
            [{"name": "Eevee", "number": "074/131", "rarity": "common", "special_type": "master ball"}],
            df,
            context_label="test.special_type_disambiguation",
        )

        assert len(resolved) == 1
        assert resolved.iloc[0]["Card Name"] == "Eevee"
        assert resolved.iloc[0]["Card Number"] == "074/131"
        assert resolved.iloc[0]["Rarity"] == "common"
        assert resolved.iloc[0]["Special Type"] == "master ball"

    def test_special_type_suppresses_ambiguity_diagnostic_for_differentiating_case(self, capsys):
        """Supplying special_type should remove ambiguity diagnostics for the differentiating case."""
        df = self._make_df_for_special_type_disambiguation()

        resolve_configured_god_pack_rows(
            [{"name": "Eevee", "number": "074/131", "rarity": "common", "special_type": "master ball"}],
            df,
            context_label="test.special_type_diagnostic",
        )
        captured = capsys.readouterr()

        assert "GOD_PACK_IDENTITY_AMBIGUOUS" not in captured.out

    def test_omitted_special_type_allows_normal_unambiguous_matching(self):
        """Omitting special_type should still resolve generic non-ambiguous rows normally."""
        df = _make_df_with_card_number([
            {
                "Card Name": "Pikachu",
                "Card Number": "001/131",
                "Rarity": "common",
                "Price ($)": 0.12,
                "EV": 0.001,
            },
            {
                "Card Name": "Raichu",
                "Card Number": "002/131",
                "Rarity": "rare",
                "Price ($)": 1.20,
                "EV": 0.010,
            },
        ])

        resolved = resolve_configured_god_pack_rows(
            [{"name": "Pikachu", "number": "001/131", "rarity": "common"}],
            df,
            context_label="test.omitted_special_type_generic",
        )

        assert len(resolved) == 1
        assert resolved.iloc[0]["Card Name"] == "Pikachu"
        assert resolved.iloc[0]["Card Number"] == "001/131"

    def test_omitted_special_type_remains_ambiguous_for_differentiating_case(self, capsys):
        """Without special_type, identical name/number/rarity variants should follow existing ambiguity behavior."""
        df = self._make_df_for_special_type_disambiguation()

        resolved = resolve_configured_god_pack_rows(
            [{"name": "Eevee", "number": "074/131", "rarity": "common"}],
            df,
            context_label="test.omitted_special_type_ambiguous",
        )
        captured = capsys.readouterr()

        assert len(resolved) == 1
        assert "GOD_PACK_IDENTITY_AMBIGUOUS" in captured.out


# ============================================================================
# Tests: god-pack card resolution by card_number
# ============================================================================

class TestGodPackCardNumberResolution:

    def _make_df_for_god_pack(self):
        """Minimal toy DataFrame for god-pack tests."""
        return _make_df_with_card_number([
            {"Card Name": "Charmander", "Card Number": "168/165", "Rarity": "illustration rare",
             "Price ($)": 8.0, "EV": 0.043},
            {"Card Name": "Charmeleon", "Card Number": "169/165", "Rarity": "illustration rare",
             "Price ($)": 6.0, "EV": 0.032},
            {"Card Name": "Charizard ex", "Card Number": "199/165", "Rarity": "special illustration rare",
             "Price ($)": 45.0, "EV": 0.200},
            # This Charizard ex (double rare) has same name but different card_number
            {"Card Name": "Charizard ex", "Card Number": "006/165", "Rarity": "double rare",
             "Price ($)": 5.0, "EV": 0.055},
            {"Card Name": "Common Fill", "Card Number": "001/165", "Rarity": "common",
             "Price ($)": 0.10, "EV": 0.001},
            {"Card Name": "Uncommon Fill", "Card Number": "050/165", "Rarity": "uncommon",
             "Price ($)": 0.25, "EV": 0.004},
        ])

    def test_god_pack_resolves_correct_cards_by_card_number(self):
        """God-pack must use card_number to select the exact intended card, not name alone."""
        from backend.calculations.packCalcsRefractored.evrCalculator import PackEVCalculator

        god_pack_strategy = {
            "enabled": True,
            "pull_rate": 1 / 2000,
            "strategy": {
                "type": "fixed",
                "packs": [
                    {
                        "name": "Charmander Line",
                        "cards": [
                            {"name": "Charmander", "number": "168/165", "rarity": "illustration rare"},
                            {"name": "Charmeleon", "number": "169/165", "rarity": "illustration rare"},
                            {"name": "Charizard ex", "number": "199/165", "rarity": "special illustration rare"},  # Must select SIR (199), not double rare (006)
                        ]
                    }
                ]
            }
        }

        df = self._make_df_for_god_pack()

        # Direct call to the static method — no instantiation needed
        ev = PackEVCalculator._calculate_god_packs_ev_contributions(
            god_pack_strategy, df, MockSVConfig()
        )

        # Expected: trio value = 8.0 + 6.0 + 45.0 = 59.0 (NOT 8+6+5=19 from wrong card)
        avg_common = df[df["Rarity"] == "common"]["Price ($)"].mean()
        avg_uncommon = df[df["Rarity"] == "uncommon"]["Price ($)"].mean()
        expected_pack_value = 59.0 + 4 * avg_common + 3 * avg_uncommon
        expected_ev = (1 / 2000) * expected_pack_value
        assert ev == pytest.approx(expected_ev, rel=1e-4), \
            f"God-pack must use the SIR Charizard ex (199/165) at $45, not the DR at $5"

    def test_god_pack_unmatched_card_number_emits_diagnostic(self, capsys):
        """When a god-pack card spec can't be resolved by card_number, a diagnostic must be emitted."""
        from backend.calculations.packCalcsRefractored.evrCalculator import PackEVCalculator

        god_pack_strategy = {
            "enabled": True,
            "pull_rate": 1 / 2000,
            "strategy": {
                "type": "fixed",
                "packs": [
                    {
                        "name": "Test Pack",
                        "cards": [{"name": "Nonexistent", "number": "999/999", "rarity": "special illustration rare"}]  # Does not exist in df
                    }
                ]
            }
        }

        df = _make_df_with_card_number([
            {"Card Name": "Common Fill", "Card Number": "001/165", "Rarity": "common",
             "Price ($)": 0.10, "EV": 0.001},
            {"Card Name": "Uncommon Fill", "Card Number": "050/165", "Rarity": "uncommon",
             "Price ($)": 0.25, "EV": 0.004},
        ])

        PackEVCalculator._calculate_god_packs_ev_contributions(god_pack_strategy, df, MockSVConfig())
        captured = capsys.readouterr()
        assert "GOD_PACK_IDENTITY_UNMATCHED" in captured.out or "UNMATCHED" in captured.out.upper(), \
            "Must emit GOD_PACK_IDENTITY_UNMATCHED diagnostic for unresolvable card spec"

    def test_god_pack_name_only_object_uses_rarity_to_break_name_ties(self):
        """Name-only structured objects must use rarity as a narrowing hint when names collide."""
        from backend.calculations.packCalcsRefractored.evrCalculator import PackEVCalculator

        god_pack_strategy = {
            "enabled": True,
            "pull_rate": 1.0,
            "strategy": {
                "type": "fixed",
                "cards": [
                    {"name": "Charizard ex", "rarity": "special illustration rare"},
                ],
            },
        }

        df = self._make_df_for_god_pack()

        ev = PackEVCalculator._calculate_god_packs_ev_contributions(
            god_pack_strategy, df, MockSVConfig()
        )

        assert ev == pytest.approx(45.0)


# ============================================================================
# Tests: top1/3/5 EV shares from corrected hit pool
# ============================================================================

class TestTop135EvSharesFromCorrectedPool:

    def test_top1_ev_share_uses_corrected_hit_pool(self):
        """top1_ev_share must be computed from the hit pool with stable identity."""
        from backend.calculations.evr.derived_metrics import compute_chase_dependency_metrics

        # Simulated hit_ev_contributions keyed by card_number (after the fix)
        hit_contributions = {
            "199/165": 0.200,   # Charizard ex SIR — largest
            "193/165": 0.080,   # Mew ex UR
            "168/165": 0.043,   # Charmander IR
        }
        result = compute_chase_dependency_metrics(hit_contributions)
        total = sum(hit_contributions.values())
        expected_top1 = 0.200 / total
        assert result["top1_ev_share"] == pytest.approx(expected_top1)

    def test_hit_pool_with_two_charizard_ex_prints_has_correct_concentration(self):
        """When DR and SIR Charizard ex are tracked separately, concentration is different than merged."""
        from backend.calculations.evr.derived_metrics import compute_chase_dependency_metrics

        # Correctly separated by card_number
        separate_pool = {
            "199/165": 0.200,  # Charizard ex SIR
            "006/165": 0.055,  # Charizard ex DR
            "193/165": 0.080,  # Mew ex
        }
        result_separate = compute_chase_dependency_metrics(separate_pool)

        # Incorrectly merged (old name-based behavior)
        merged_pool = {
            "Charizard ex": 0.255,  # Would be wrong sum if name collapsed
            "Mew ex": 0.080,
        }
        result_merged = compute_chase_dependency_metrics(merged_pool)

        # In the separate pool: top1 = 0.200 / 0.335 ≈ 0.597
        # In the merged pool: top1 = 0.255 / 0.335 ≈ 0.761 (inflated and wrong)
        assert result_separate["top1_ev_share"] < result_merged["top1_ev_share"], \
            "Correctly separated pool must show lower top1 concentration than incorrectly merged"
        assert result_separate["n_cards"] == 3
        assert result_merged["n_cards"] == 2  # Collapsed into 2 (wrong)
