"""Tests for Scarlet and Violet card group extraction logic.

Validates dual semantic membership where pattern-overlay rows preserve base
rarity membership while still being routed to the hit pool for pattern slots.
"""

from __future__ import annotations

import pandas as pd
import pytest

from backend.simulations.utils.extractScarletAndVioletCardGroups import (
    _build_base_pool_mask,
    _build_hit_pool_mask,
    _build_pattern_overlay_mask,
    extract_scarletandviolet_card_groups,
)


class TestBuildBasePoolMask:
    """Test _build_base_pool_mask preserves base rarity membership."""

    def test_normal_rare_card_included_in_base_rare_pool(self):
        """A normal rare card (no pattern) should be included in the base rare pool."""
        df = pd.DataFrame({
            "Rarity": ["rare"],
            "Special Type": [""],
        })
        
        mask = _build_base_pool_mask(df, "rare")
        
        # Normal rare card should be included
        assert mask.iloc[0], \
            f"Expected normal rare card to be in base rare pool, got mask={mask.iloc[0]}"

    def test_pattern_rare_card_included_in_base_rare_pool(self):
        """A pattern-overlay rare card still belongs to the base rare pool."""
        df = pd.DataFrame({
            "Rarity": ["rare"],
            "Special Type": ["master ball"],
        })
        
        mask = _build_base_pool_mask(df, "rare")
        
        # Pattern rare card should remain in base rare pool.
        assert mask.iloc[0], \
            f"Expected pattern rare card to remain in base rare pool, got mask={mask.iloc[0]}"

    def test_poke_ball_pattern_rare_card_included_in_base_rare_pool(self):
        """A poke_ball pattern rare card still belongs to the base rare pool."""
        df = pd.DataFrame({
            "Rarity": ["rare"],
            "Special Type": ["poke ball"],
        })
        
        mask = _build_base_pool_mask(df, "rare")
        
        # Pattern rare card should remain in base rare pool.
        assert mask.iloc[0], \
            f"Expected poke_ball pattern rare card to remain in base rare pool, got mask={mask.iloc[0]}"

    def test_mixed_rare_cards_all_stay_in_base_pool(self):
        """Multiple rare cards: both plain and pattern rows remain in base rare."""
        df = pd.DataFrame({
            "Rarity": ["rare", "rare", "rare"],
            "Special Type": ["", "master ball", "poke ball"],
        })
        
        mask = _build_base_pool_mask(df, "rare")
        
        expected = [True, True, True]
        assert mask.tolist() == expected, \
            f"Expected {expected}, got {mask.tolist()}"

    def test_different_rarities_not_affected_by_pattern_logic(self):
        """Pattern exclusion applies only to matching rarity."""
        df = pd.DataFrame({
            "Rarity": ["rare", "uncommon", "common"],
            "Special Type": ["", "", ""],
        })
        
        mask = _build_base_pool_mask(df, "rare")
        
        expected = [True, False, False]
        assert mask.tolist() == expected, \
            f"Expected {expected}, got {mask.tolist()}"


class TestPatternCardRouting:
    """Test that pattern cards are correctly routed to hit pool."""

    def test_pattern_rare_card_in_hit_pool(self):
        """A pattern-overlay rare card should end up in the hit pool."""
        df = pd.DataFrame({
            "Rarity": ["rare"],
            "Special Type": ["master ball"],
        })
        
        hit_mask = _build_hit_pool_mask(df)
        
        # Pattern rare card should be in hit pool
        assert hit_mask.iloc[0], \
            f"Expected pattern rare card to be in hit pool, got mask={hit_mask.iloc[0]}"

    def test_normal_rare_card_not_in_hit_pool(self):
        """A normal rare card should NOT be in the hit pool."""
        df = pd.DataFrame({
            "Rarity": ["rare"],
            "Special Type": [""],
        })
        
        hit_mask = _build_hit_pool_mask(df)
        
        # Normal rare card should not be in hit pool
        assert not hit_mask.iloc[0], \
            f"Expected normal rare card to NOT be in hit pool, got mask={hit_mask.iloc[0]}"

    def test_both_pattern_and_base_rare_correct_routing(self):
        """Both pattern and normal rare cards are routed to correct pools."""
        df = pd.DataFrame({
            "Rarity": ["rare", "rare", "common"],
            "Special Type": ["", "master ball", ""],
        })
        
        base_rare_mask = _build_base_pool_mask(df, "rare")
        hit_mask = _build_hit_pool_mask(df)
        
        # Row 0: normal rare -> in base pool, not in hit pool
        assert base_rare_mask.iloc[0], "Normal rare should be in base pool"
        assert not hit_mask.iloc[0], "Normal rare should not be in hit pool"
        
        # Row 1: pattern rare -> in base pool and in hit pool
        assert base_rare_mask.iloc[1], "Pattern rare should remain in base pool"
        assert hit_mask.iloc[1], "Pattern rare should be in hit pool"
        
        # Row 2: normal common -> in base pool, not in hit pool
        assert not base_rare_mask.iloc[2], "Common should not be in rare base pool"
        assert not hit_mask.iloc[2], "Common should not be in hit pool"


class TestPatternOverlayMask:
    """Test _build_pattern_overlay_mask correctly identifies pattern cards."""

    def test_identifies_master_ball_pattern(self):
        """Master ball pattern should be identified as a pattern."""
        df = pd.DataFrame({
            "Rarity": ["rare"],
            "Special Type": ["master ball"],
        })
        
        mask = _build_pattern_overlay_mask(df)
        
        assert mask.iloc[0], \
            "Master ball pattern should be identified as a pattern"

    def test_identifies_poke_ball_pattern(self):
        """Poke ball pattern should be identified as a pattern."""
        df = pd.DataFrame({
            "Rarity": ["rare"],
            "Special Type": ["poke ball"],
        })
        
        mask = _build_pattern_overlay_mask(df)
        
        assert mask.iloc[0], \
            "Poke ball pattern should be identified as a pattern"

    def test_empty_special_type_not_pattern(self):
        """Empty Special Type should NOT be identified as a pattern."""
        df = pd.DataFrame({
            "Rarity": ["rare"],
            "Special Type": [""],
        })
        
        mask = _build_pattern_overlay_mask(df)
        
        assert not mask.iloc[0], \
            "Empty Special Type should not be identified as a pattern"


class TestExtractCardGroups:
    """Integration tests for extract_scarletandviolet_card_groups function."""

    @pytest.fixture
    def mock_config(self):
        """Provide a minimal mock config for reverse pool testing."""
        class MockConfig:
            def get_reverse_eligible_rarities(self):
                return ["common", "uncommon", "rare"]
        
        return MockConfig()

    def test_pattern_rare_stays_in_base_rare_group(self, mock_config):
        """Full extraction: pattern rare card should appear in 'rare' group."""
        df = pd.DataFrame({
            "Rarity": ["rare", "rare"],
            "Special Type": ["", "master ball"],
        })
        
        groups = extract_scarletandviolet_card_groups(mock_config, df)
        
        assert len(groups["rare"]) == 2, \
            f"Expected both rare rows in 'rare' group, got {len(groups['rare'])}"

    def test_pattern_rare_in_hit_group(self, mock_config):
        """Full extraction: pattern rare card should appear in 'hit' group."""
        df = pd.DataFrame({
            "Rarity": ["rare", "rare"],
            "Special Type": ["", "master ball"],
        })
        
        groups = extract_scarletandviolet_card_groups(mock_config, df)
        
        # Pattern card should be in hit group
        assert len(groups["hit"]) >= 1, \
            f"Expected pattern card in 'hit' group, got {len(groups['hit'])}"
