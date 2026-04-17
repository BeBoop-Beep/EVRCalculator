"""
Unit tests for rarity classification utilities.

Tests verify that hit/non-hit classification is driven by config rarity mapping,
not by hardcoded assumptions like "rares and above."
"""

import pytest
import pandas as pd
from types import MappingProxyType

from backend.calculations.utils.rarity_classification import (
    normalize_rarity_string,
    is_hit_rarity,
    get_rarity_group,
    filter_card_ev_by_hits,
)


# ============================================================================
# Mock Config Classes
# ============================================================================

class MockScarletVioletConfig:
    """Mock Scarlet & Violet era config."""
    RARITY_MAPPING = MappingProxyType({
        'common': 'common',
        'uncommon': 'uncommon',
        'rare': 'rare',
        'double rare': 'hits',
        'ultra rare': 'hits',
        'hyper rare': 'hits',
        'illustration rare': 'hits',
        'special illustration rare': 'hits',
        'secret rare': 'hits',
        'ace spec rare': 'hits',
        'black white rare': 'hits',
        'shiny rare': 'hits',
        'shiny ultra rare': 'hits',
        'poke ball pattern': 'hits',
        'master ball pattern': 'hits',
    })


class MockPlatinumConfig:
    """Mock Platinum era config (no special rarities as hits)."""
    RARITY_MAPPING = MappingProxyType({
        'common': 'common',
        'uncommon': 'uncommon',
        'rare': 'rare',
        'holo rare': 'hits',
        'ultra rare': 'hits',
        'double rare': 'hits',
        'illustration rare': 'hits',
        'special illustration rare': 'hits',
        'secret rare': 'hits',
    })


# ============================================================================
# Test normalize_rarity_string
# ============================================================================

class TestNormalizeRarityString:
    def test_lowercase_conversion(self):
        assert normalize_rarity_string("ULTRA RARE") == "ultra rare"

    def test_whitespace_stripping(self):
        assert normalize_rarity_string("  rare  ") == "rare"

    def test_combined_normalization(self):
        assert normalize_rarity_string("  SPECIAL ILLUSTRATION RARE  ") == "special illustration rare"

    def test_already_normalized(self):
        assert normalize_rarity_string("common") == "common"


# ============================================================================
# Test is_hit_rarity
# ============================================================================

class TestIsHitRarity:
    def test_hit_rarity_scarlet_violet(self):
        """Ultra rare is mapped to 'hits' in SV."""
        assert is_hit_rarity("ultra rare", MockScarletVioletConfig())

    def test_non_hit_rarity_common(self):
        """Common is never a hit."""
        assert not is_hit_rarity("common", MockScarletVioletConfig())

    def test_non_hit_rarity_uncommon(self):
        """Uncommon is never a hit."""
        assert not is_hit_rarity("uncommon", MockScarletVioletConfig())

    def test_non_hit_rarity_rare(self):
        """Rare (non-special) is never a hit."""
        assert not is_hit_rarity("rare", MockScarletVioletConfig())

    def test_special_rarity_ace_spec_rare(self):
        """Ace spec rare maps to 'hits' in SV."""
        assert is_hit_rarity("ace spec rare", MockScarletVioletConfig())

    def test_special_rarity_black_white_rare(self):
        """Black white rare maps to 'hits' in SV."""
        assert is_hit_rarity("black white rare", MockScarletVioletConfig())

    def test_special_rarity_poke_ball_pattern(self):
        """Poke ball pattern maps to 'hits' in SV."""
        assert is_hit_rarity("poke ball pattern", MockScarletVioletConfig())

    def test_master_ball_pattern(self):
        """Master ball pattern maps to 'hits' in SV."""
        assert is_hit_rarity("master ball pattern", MockScarletVioletConfig())

    def test_case_insensitive_normalization(self):
        """Rarity strings are normalized before comparison."""
        assert is_hit_rarity("ULTRA RARE", MockScarletVioletConfig())
        assert not is_hit_rarity("COMMON", MockScarletVioletConfig())

    def test_whitespace_tolerant(self):
        """Extra whitespace is handled."""
        assert is_hit_rarity("  ultra rare  ", MockScarletVioletConfig())

    def test_different_era_same_rarity(self):
        """Different eras can have different mappings."""
        # In Scarlet & Violet: 'ultra rare' is a hit
        assert is_hit_rarity("ultra rare", MockScarletVioletConfig())
        # In Platinum: 'ultra rare' is also a hit (happens to be same here)
        assert is_hit_rarity("ultra rare", MockPlatinumConfig())

    def test_missing_config_attribute_raises(self):
        """Missing RARITY_MAPPING raises AttributeError."""
        class BadConfig:
            pass
        with pytest.raises(AttributeError, match="RARITY_MAPPING"):
            is_hit_rarity("common", BadConfig())


# ============================================================================
# Test get_rarity_group
# ============================================================================

class TestGetRarityGroup:
    def test_get_hit_group(self):
        assert get_rarity_group("ultra rare", MockScarletVioletConfig()) == "hits"

    def test_get_common_group(self):
        assert get_rarity_group("common", MockScarletVioletConfig()) == "common"

    def test_get_uncommon_group(self):
        assert get_rarity_group("uncommon", MockScarletVioletConfig()) == "uncommon"

    def test_get_rare_group(self):
        assert get_rarity_group("rare", MockScarletVioletConfig()) == "rare"

    def test_get_nonexistent_rarity_returns_none(self):
        """Rarity not in mapping returns None."""
        assert get_rarity_group("nonexistent rarity", MockScarletVioletConfig()) is None

    def test_case_insensitive_get(self):
        assert get_rarity_group("ULTRA RARE", MockScarletVioletConfig()) == "hits"


# ============================================================================
# Test filter_card_ev_by_hits
# ============================================================================

class TestFilterCardEvByHits:
    def test_all_hits(self):
        """All cards are hits."""
        df = pd.DataFrame({
            'Card Name': ['Ultra Rare A', 'Ultra Rare B'],
            'Rarity': ['ultra rare', 'ultra rare'],
        })
        contribs = {'Ultra Rare A': 3.0, 'Ultra Rare B': 2.0}
        hit, non_hit = filter_card_ev_by_hits(contribs, df, MockScarletVioletConfig())
        assert hit == {'Ultra Rare A': 3.0, 'Ultra Rare B': 2.0}
        assert non_hit == {}

    def test_all_non_hits(self):
        """All cards are non-hits."""
        df = pd.DataFrame({
            'Card Name': ['Common A', 'Common B'],
            'Rarity': ['common', 'common'],
        })
        contribs = {'Common A': 0.5, 'Common B': 0.3}
        hit, non_hit = filter_card_ev_by_hits(contribs, df, MockScarletVioletConfig())
        assert hit == {}
        assert non_hit == {'Common A': 0.5, 'Common B': 0.3}

    def test_mixed_hits_and_non_hits(self):
        """Some cards are hits, some are not."""
        df = pd.DataFrame({
            'Card Name': ['Ultra Rare', 'Common', 'Ace Spec Rare'],
            'Rarity': ['ultra rare', 'common', 'ace spec rare'],
        })
        contribs = {'Ultra Rare': 2.0, 'Common': 0.5, 'Ace Spec Rare': 1.5}
        hit, non_hit = filter_card_ev_by_hits(contribs, df, MockScarletVioletConfig())
        assert hit == {'Ultra Rare': 2.0, 'Ace Spec Rare': 1.5}
        assert non_hit == {'Common': 0.5}

    def test_zero_ev_excluded(self):
        """Cards with EV <= 0 are excluded from both pools."""
        df = pd.DataFrame({
            'Card Name': ['Card A', 'Card B'],
            'Rarity': ['ultra rare', 'common'],
        })
        contribs = {'Card A': 0.0, 'Card B': -1.0}
        hit, non_hit = filter_card_ev_by_hits(contribs, df, MockScarletVioletConfig())
        assert hit == {}
        assert non_hit == {}

    def test_missing_card_assumed_non_hit(self):
        """Cards not found in dataframe are conservatively assumed non-hit."""
        df = pd.DataFrame({
            'Card Name': ['Card A'],
            'Rarity': ['ultra rare'],
        })
        contribs = {'Card A': 1.0, 'Unknown Card': 2.0}
        hit, non_hit = filter_card_ev_by_hits(contribs, df, MockScarletVioletConfig())
        assert hit == {'Card A': 1.0}
        assert non_hit == {'Unknown Card': 2.0}

    def test_case_insensitive_card_matching(self):
        """Card names are matched case-insensitively."""
        df = pd.DataFrame({
            'Card Name': ['PIKACHU'],
            'Rarity': ['ultra rare'],
        })
        contribs = {'pikachu': 5.0}
        hit, non_hit = filter_card_ev_by_hits(contribs, df, MockScarletVioletConfig())
        assert hit == {'pikachu': 5.0}
        assert non_hit == {}

    def test_whitespace_tolerant_matching(self):
        """Whitespace in card names is normalized."""
        df = pd.DataFrame({
            'Card Name': ['  PIKACHU  '],
            'Rarity': ['ultra rare'],
        })
        contribs = {'pikachu': 5.0}
        hit, non_hit = filter_card_ev_by_hits(contribs, df, MockScarletVioletConfig())
        assert hit == {'pikachu': 5.0}

    def test_empty_contributions(self):
        """Empty contribution dict returns empty pools."""
        df = pd.DataFrame({
            'Card Name': ['Card A'],
            'Rarity': ['ultra rare'],
        })
        contribs = {}
        hit, non_hit = filter_card_ev_by_hits(contribs, df, MockScarletVioletConfig())
        assert hit == {}
        assert non_hit == {}

    def test_era_specific_mapping(self):
        """Different eras have different special rarities."""
        # Create a config where a rarity is NOT a hit
        class NoSpecialsConfig:
            RARITY_MAPPING = MappingProxyType({
                'common': 'common',
                'uncommon': 'uncommon',
                'rare': 'rare',
                'holo rare': 'hits',
                'ultra rare': 'hits',
            })

        df = pd.DataFrame({
            'Card Name': ['Poke Ball Pattern'],
            'Rarity': ['poke ball pattern'],
        })
        contribs = {'Poke Ball Pattern': 1.0}

        # In SV, poke ball pattern is a hit
        hit_sv, non_hit_sv = filter_card_ev_by_hits(contribs, df, MockScarletVioletConfig())
        assert 'Poke Ball Pattern' in hit_sv

        # In a config without it, it's not found → assumed non-hit
        hit_none, non_hit_none = filter_card_ev_by_hits(contribs, df, NoSpecialsConfig())
        assert 'Poke Ball Pattern' in non_hit_none
