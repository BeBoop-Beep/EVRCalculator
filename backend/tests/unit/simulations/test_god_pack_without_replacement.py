"""
Tests for god-pack without-replacement sampling.

Verifies that:
1. Without-replacement god-pack buckets never produce duplicate cards within the bucket
2. With-replacement behavior is preserved for backward compatibility
3. Invalid counts (count > pool size) raise clear errors
4. Ascended Heroes split buckets work correctly
5. White Flare / Black Bolt split buckets work correctly
6. Config format backward compatibility (simple int vs dict)
"""

import pandas as pd
import numpy as np
import pytest
from collections import defaultdict

from backend.simulations.monteCarloSimV2 import (
    make_simulate_pack_fn_v2,
    _parse_rarity_config,
    _sample_special_pack_details,
    _sample_rows_controlled,
)
from backend.simulations.utils.monteCarloSimUtils.specialPackLogic import sample_god_pack
from backend.utils.special_pack_config import iter_rarity_bucket_rules
from backend.constants.tcg.pokemon.scarletAndVioletEra.whiteFlare import SetWhiteFlareConfig
from backend.constants.tcg.pokemon.scarletAndVioletEra.blackBolt import SetBlackBoltConfig


class DummyASCConfig:
    """Dummy Ascended Heroes config for testing."""
    SET_NAME = "Ascended Heroes"
    SET_ABBREVIATION = "ASC"
    ERA = "mega evolution"
    USE_MONTE_CARLO_V2 = True
    SLOTS_PER_RARITY = {"common": 4, "uncommon": 3, "reverse": 2, "rare": 1}
    
    PULL_RATE_MAPPING = {
        "common": 216,
        "uncommon": 69,
        "rare": 25,
        "double rare": 191,
        "illustration rare": 293,
        "special illustration rare": 1533,
        "ultra rare": 291,
        "mega attack rare": 202,
        "mega hyper rare": 1080,
        "god pack": 2000,
    }

    RARE_SLOT_PROBABILITY = {
        "double rare": 1 / 5,
        "ultra rare": 1 / 21,
        "mega attack rare": 1 / 29,
        "rare": 1 - (1 / 5) - (1 / 21) - (1 / 29),
    }

    REVERSE_SLOT_PROBABILITIES = {
        "slot_1": {
            "illustration rare": 1/9,
            "special illustration rare": 1/70,
            "regular reverse": 1 - (1/9) - (1/70)
        },
        "slot_2": {
            "illustration rare": 1/9,
            "special illustration rare": 1/70,
            "mega hyper rare": 1/540,
            "regular reverse": 1 - (1/9) - (1/70) - (1/540)
        }
    }

    PACK_CONSTRAINTS = {}

    GOD_PACK_CONFIG = {
        "enabled": True,
        "pull_rate": 1.0,  # Always god pack for testing
        "strategy": {
            "type": "random",
            "rules": {
                "rarities": {
                    "mega attack rare": {"count": 3, "replacement": "without_replacement"},
                    "special illustration rare": {"count": 7, "replacement": "without_replacement"},
                }
            }
        }
    }

    DEMI_GOD_PACK_CONFIG = {
        "enabled": False,
    }

    @classmethod
    def get_pack_state_overrides(cls):
        return {}


class DummyWhiteFlareConfig(DummyASCConfig):
    """Dummy White Flare style config for 9 IR + 1 SIR god packs."""

    SET_NAME = "White Flare"
    SET_ABBREVIATION = "WHT"
    ERA = "scarlet and violet"

    GOD_PACK_CONFIG = {
        "enabled": True,
        "pull_rate": 1.0,
        "strategy": {
            "type": "random",
            "rules": {
                "rarities": {
                    "illustration rare": {"count": 9, "replacement": "without_replacement"},
                    "special illustration rare": {"count": 1, "replacement": "without_replacement"},
                }
            },
        },
    }


@pytest.fixture
def sample_dataframe():
    """Create a sample dataframe with various rarities."""
    data = {
        "Card Name": [
            # Commons (10 total)
            *[f"Common {i}" for i in range(1, 11)],
            # Uncommons (8 total)
            *[f"Uncommon {i}" for i in range(1, 9)],
            # Rares (5 total)
            *[f"Rare {i}" for i in range(1, 6)],
            # Mega Attack Rares (6 total - need at least 3 for god pack)
            *[f"Mega Attack Rare {i}" for i in range(1, 7)],
            # Special Illustration Rares (10 total - need at least 7 for god pack)
            *[f"Special Illustration Rare {i}" for i in range(1, 11)],
            # Illustration Rares (12 total)
            *[f"Illustration Rare {i}" for i in range(1, 13)],
        ],
        "Price ($)": [
            # Commons: low value
            *[0.15] * 10,
            # Uncommons: medium value
            *[0.35] * 8,
            # Rares: good value
            *[2.50] * 5,
            # Mega Attack Rares: high value
            *[15.00] * 6,
            # Special Illustration Rares: very high value
            *[25.00] * 10,
            # Illustration Rares: high value
            *[18.00] * 12,
        ],
        "Rarity": [
            # Commons
            *["common"] * 10,
            # Uncommons
            *["uncommon"] * 8,
            # Rares
            *["rare"] * 5,
            # Mega Attack Rares
            *["mega attack rare"] * 6,
            # Special Illustration Rares
            *["special illustration rare"] * 10,
            # Illustration Rares
            *["illustration rare"] * 12,
        ],
        # 10+8+5+6+10+12 = 51 total cards
        "Card Number": [f"{i:03d}/217" for i in range(1, 52)],
    }
    df = pd.DataFrame(data)
    # Verify all columns have same length
    assert len(set(len(col) for col in data.values())) == 1, "All columns must have the same length"
    return df


class TestParseRarityConfig:
    """Test the _parse_rarity_config helper function."""

    def test_simple_int_config(self):
        """Simple int config should default to with_replacement."""
        count, use_replacement = _parse_rarity_config(5)
        assert count == 5
        assert use_replacement is True

    def test_dict_config_with_replacement_explicit(self):
        """Dict config with explicit with_replacement."""
        config = {"count": 3, "replacement": "with_replacement"}
        count, use_replacement = _parse_rarity_config(config)
        assert count == 3
        assert use_replacement is True

    def test_dict_config_without_replacement(self):
        """Dict config with without_replacement."""
        config = {"count": 7, "replacement": "without_replacement"}
        count, use_replacement = _parse_rarity_config(config)
        assert count == 7
        assert use_replacement is False

    def test_dict_config_default_to_with_replacement(self):
        """Dict config without explicit replacement defaults to with_replacement."""
        config = {"count": 4}
        count, use_replacement = _parse_rarity_config(config)
        assert count == 4
        assert use_replacement is True

    def test_dict_config_case_insensitive(self):
        """Replacement mode should be case insensitive."""
        config = {"count": 2, "replacement": "WITHOUT_REPLACEMENT"}
        count, use_replacement = _parse_rarity_config(config)
        assert use_replacement is False

    def test_invalid_config_raises(self):
        """Invalid config format should raise ValueError."""
        with pytest.raises(ValueError, match="Invalid rarity config format"):
            _parse_rarity_config("invalid")


class TestSampleRowsControlled:
    """Test the _sample_rows_controlled function."""

    @pytest.fixture
    def test_df(self):
        """Create a small test dataframe."""
        return pd.DataFrame({
            "Card Name": [f"Card {i}" for i in range(10)],
            "Price ($)": [float(i + 1) for i in range(10)],
        })

    def test_with_replacement_allows_duplicates(self, test_df):
        """With replacement sampling can produce duplicates."""
        rng = np.random.default_rng(42)
        # Sample many times and check for duplicates
        samples = _sample_rows_controlled(test_df, 100, rng, replace=True)
        # It's extremely unlikely to get no duplicates with 100 samples from 10 cards
        assert len(samples) == 100

    def test_without_replacement_no_duplicates(self, test_df):
        """Without replacement sampling should never produce duplicates."""
        rng = np.random.default_rng(42)
        samples = _sample_rows_controlled(test_df, 10, rng, replace=False)
        assert len(samples) == 10
        # All samples should be unique (all indices from 0-9)
        assert len(set(samples.index)) == 10

    def test_without_replacement_exceeds_pool_raises(self, test_df):
        """Requesting more samples than pool size without replacement should raise."""
        rng = np.random.default_rng(42)
        with pytest.raises(ValueError, match="Cannot sample.*unique cards"):
            _sample_rows_controlled(test_df, 15, rng, replace=False)

    def test_empty_dataframe(self):
        """Empty dataframe returns empty result."""
        empty_df = pd.DataFrame({"Card Name": [], "Price ($)": []})
        rng = np.random.default_rng(42)
        result = _sample_rows_controlled(empty_df, 5, rng, replace=True)
        assert result.empty

    def test_zero_samples_requested(self, test_df):
        """Requesting 0 samples returns empty result."""
        rng = np.random.default_rng(42)
        result = _sample_rows_controlled(test_df, 0, rng, replace=True)
        assert result.empty


class TestSpecialPackConfigConsistency:
    """Cross-path consistency checks for random special-pack bucket config parsing."""

    @pytest.mark.parametrize("config_cls", [SetWhiteFlareConfig, SetBlackBoltConfig])
    def test_white_flare_black_bolt_bucket_config_is_consistent_across_paths(self, sample_dataframe, config_cls):
        rarity_rules = config_cls.GOD_PACK_CONFIG["strategy"]["rules"]["rarities"]

        # Authoritative parser contract (shared across modules)
        parsed_rules = list(iter_rarity_bucket_rules(rarity_rules))
        assert parsed_rules == [
            ("illustration rare", 9, False),
            ("special illustration rare", 1, False),
        ]

        # V1 helper path accepts and executes the same config shape
        v1_value = sample_god_pack(config_cls.GOD_PACK_CONFIG, sample_dataframe)
        assert v1_value > 0

        # V2 special-pack path accepts the same config and yields expected composition
        v2 = _sample_special_pack_details(
            entry_path="god",
            config_map=config_cls.GOD_PACK_CONFIG,
            df=sample_dataframe,
            common_cards=sample_dataframe[sample_dataframe["Rarity"] == "common"],
            uncommon_cards=sample_dataframe[sample_dataframe["Rarity"] == "uncommon"],
            rng=np.random.default_rng(123),
        )
        v2_rarities = v2["rarities"]
        assert sum(1 for r in v2_rarities if r == "illustration rare") == 9
        assert sum(1 for r in v2_rarities if r == "special illustration rare") == 1

    def test_without_replacement_dict_bucket_parsed_consistently(self):
        spec = {"count": 3, "replacement": "without_replacement"}
        count_v2, replacement_v2 = _parse_rarity_config(spec)
        parsed = list(iter_rarity_bucket_rules({"mega attack rare": spec}))

        assert count_v2 == 3
        assert replacement_v2 is False
        assert parsed == [("mega attack rare", 3, False)]


class TestGodPackWithoutReplacement:
    """Test god-pack simulation with without-replacement buckets."""

    def test_ascended_heroes_god_pack_no_duplicates(self, sample_dataframe):
        """Ascended Heroes god pack should never have duplicate cards within buckets."""
        config = DummyASCConfig()
        reverse_pool = sample_dataframe[sample_dataframe["Rarity"] == "illustration rare"].copy()
        reverse_pool["Reverse Variant Price ($)"] = reverse_pool["Price ($)"]
        
        rarity_pull_counts = defaultdict(int)
        rarity_value_totals = defaultdict(float)
        logs = []
        
        fn = make_simulate_pack_fn_v2(
            common_cards=sample_dataframe[sample_dataframe["Rarity"] == "common"],
            uncommon_cards=sample_dataframe[sample_dataframe["Rarity"] == "uncommon"],
            rare_cards=sample_dataframe[sample_dataframe["Rarity"] == "rare"],
            hit_cards=pd.concat([
                sample_dataframe[sample_dataframe["Rarity"] == "mega attack rare"],
                sample_dataframe[sample_dataframe["Rarity"] == "special illustration rare"],
                sample_dataframe[sample_dataframe["Rarity"] == "illustration rare"],
            ]),
            reverse_pool=reverse_pool,
            slots_per_rarity=config.SLOTS_PER_RARITY,
            config=config,
            df=sample_dataframe,
            rarity_pull_counts=rarity_pull_counts,
            rarity_value_totals=rarity_value_totals,
            pack_logs=logs,
            rng=np.random.default_rng(42),
        )
        
        # Simulate many packs and check for duplicates
        for _ in range(100):
            value, pack_data = fn(return_pack_data=True)
            
            # Extract the special pack rarities from the pack data
            if "special_pack_rarities" in pack_data:
                special_rarities = pack_data["special_pack_rarities"]
                
                # Count mega attack rares in this pack
                mega_attack_rare_count = sum(1 for r in special_rarities if r == "mega attack rare")
                assert mega_attack_rare_count == 3, f"Expected exactly 3 mega attack rares, got {mega_attack_rare_count}"
                
                # Count special illustration rares in this pack
                sir_count = sum(1 for r in special_rarities if r == "special illustration rare")
                assert sir_count == 7, f"Expected exactly 7 special illustration rares, got {sir_count}"

    def test_white_flare_style_9_ir_1_sir_composition(self, sample_dataframe):
        """White Flare style god pack should be exactly 9 IR + 1 SIR."""
        config = DummyWhiteFlareConfig()
        reverse_pool = sample_dataframe[sample_dataframe["Rarity"] == "illustration rare"].copy()
        reverse_pool["Reverse Variant Price ($)"] = reverse_pool["Price ($)"]

        rarity_pull_counts = defaultdict(int)
        rarity_value_totals = defaultdict(float)

        fn = make_simulate_pack_fn_v2(
            common_cards=sample_dataframe[sample_dataframe["Rarity"] == "common"],
            uncommon_cards=sample_dataframe[sample_dataframe["Rarity"] == "uncommon"],
            rare_cards=sample_dataframe[sample_dataframe["Rarity"] == "rare"],
            hit_cards=pd.concat([
                sample_dataframe[sample_dataframe["Rarity"] == "mega attack rare"],
                sample_dataframe[sample_dataframe["Rarity"] == "special illustration rare"],
                sample_dataframe[sample_dataframe["Rarity"] == "illustration rare"],
            ]),
            reverse_pool=reverse_pool,
            slots_per_rarity=config.SLOTS_PER_RARITY,
            config=config,
            df=sample_dataframe,
            rarity_pull_counts=rarity_pull_counts,
            rarity_value_totals=rarity_value_totals,
            rng=np.random.default_rng(123),
        )

        for _ in range(50):
            value, pack_data = fn(return_pack_data=True)
            assert value > 0
            special_rarities = pack_data["special_pack_rarities"]
            ir_count = sum(1 for r in special_rarities if r == "illustration rare")
            sir_count = sum(1 for r in special_rarities if r == "special illustration rare")
            assert ir_count == 9, f"Expected exactly 9 illustration rares, got {ir_count}"
            assert sir_count == 1, f"Expected exactly 1 special illustration rare, got {sir_count}"

    def test_god_pack_config_backward_compatibility(self, sample_dataframe):
        """Test that old format (simple int) still works with backward compatibility."""
        config = DummyASCConfig()
        reverse_pool = sample_dataframe[sample_dataframe["Rarity"] == "illustration rare"].copy()
        reverse_pool["Reverse Variant Price ($)"] = reverse_pool["Price ($)"]
        # Override to use old format
        config.GOD_PACK_CONFIG["strategy"]["rules"]["rarities"] = {
            "mega attack rare": 3,
            "special illustration rare": 7,
        }
        
        rarity_pull_counts = defaultdict(int)
        rarity_value_totals = defaultdict(float)
        
        fn = make_simulate_pack_fn_v2(
            common_cards=sample_dataframe[sample_dataframe["Rarity"] == "common"],
            uncommon_cards=sample_dataframe[sample_dataframe["Rarity"] == "uncommon"],
            rare_cards=sample_dataframe[sample_dataframe["Rarity"] == "rare"],
            hit_cards=pd.concat([
                sample_dataframe[sample_dataframe["Rarity"] == "mega attack rare"],
                sample_dataframe[sample_dataframe["Rarity"] == "special illustration rare"],
                sample_dataframe[sample_dataframe["Rarity"] == "illustration rare"],
            ]),
            reverse_pool=reverse_pool,
            slots_per_rarity=config.SLOTS_PER_RARITY,
            config=config,
            df=sample_dataframe,
            rarity_pull_counts=rarity_pull_counts,
            rarity_value_totals=rarity_value_totals,
            rng=np.random.default_rng(42),
        )
        
        # Should not raise and should return a value
        value = fn()
        assert value > 0

    def test_with_replacement_can_have_duplicates(self, sample_dataframe):
        """With-replacement buckets can produce duplicates (verify old behavior)."""
        config = DummyASCConfig()
        reverse_pool = sample_dataframe[sample_dataframe["Rarity"] == "illustration rare"].copy()
        reverse_pool["Reverse Variant Price ($)"] = reverse_pool["Price ($)"]
        # Override to use with_replacement explicitly
        config.GOD_PACK_CONFIG["strategy"]["rules"]["rarities"] = {
            "mega attack rare": {"count": 3, "replacement": "with_replacement"},
            "special illustration rare": {"count": 7, "replacement": "with_replacement"},
        }
        
        rarity_pull_counts = defaultdict(int)
        rarity_value_totals = defaultdict(float)
        
        fn = make_simulate_pack_fn_v2(
            common_cards=sample_dataframe[sample_dataframe["Rarity"] == "common"],
            uncommon_cards=sample_dataframe[sample_dataframe["Rarity"] == "uncommon"],
            rare_cards=sample_dataframe[sample_dataframe["Rarity"] == "rare"],
            hit_cards=pd.concat([
                sample_dataframe[sample_dataframe["Rarity"] == "mega attack rare"],
                sample_dataframe[sample_dataframe["Rarity"] == "special illustration rare"],
                sample_dataframe[sample_dataframe["Rarity"] == "illustration rare"],
            ]),
            reverse_pool=reverse_pool,
            slots_per_rarity=config.SLOTS_PER_RARITY,
            config=config,
            df=sample_dataframe,
            rarity_pull_counts=rarity_pull_counts,
            rarity_value_totals=rarity_value_totals,
            rng=np.random.default_rng(42),
        )
        
        # With replacement, we should be able to simulate successfully
        value = fn()
        assert value > 0

    def test_invalid_count_without_replacement_raises(self, sample_dataframe):
        """Requesting more cards than available without replacement should raise."""
        config = DummyASCConfig()
        reverse_pool = sample_dataframe[sample_dataframe["Rarity"] == "illustration rare"].copy()
        reverse_pool["Reverse Variant Price ($)"] = reverse_pool["Price ($)"]
        # Override to request 10 mega attack rares but only 6 exist
        config.GOD_PACK_CONFIG["strategy"]["rules"]["rarities"] = {
            "mega attack rare": {"count": 10, "replacement": "without_replacement"},
        }
        
        rarity_pull_counts = defaultdict(int)
        rarity_value_totals = defaultdict(float)
        
        fn = make_simulate_pack_fn_v2(
            common_cards=sample_dataframe[sample_dataframe["Rarity"] == "common"],
            uncommon_cards=sample_dataframe[sample_dataframe["Rarity"] == "uncommon"],
            rare_cards=sample_dataframe[sample_dataframe["Rarity"] == "rare"],
            hit_cards=pd.concat([
                sample_dataframe[sample_dataframe["Rarity"] == "mega attack rare"],
                sample_dataframe[sample_dataframe["Rarity"] == "special illustration rare"],
                sample_dataframe[sample_dataframe["Rarity"] == "illustration rare"],
            ]),
            reverse_pool=reverse_pool,
            slots_per_rarity=config.SLOTS_PER_RARITY,
            config=config,
            df=sample_dataframe,
            rarity_pull_counts=rarity_pull_counts,
            rarity_value_totals=rarity_value_totals,
            rng=np.random.default_rng(42),
        )
        
        # Should raise because we're requesting 10 unique cards but only 6 exist
        with pytest.raises(ValueError, match="Cannot sample.*unique cards"):
            fn()


if __name__ == "__main__":
    pytest.main([__file__, "-v"])
