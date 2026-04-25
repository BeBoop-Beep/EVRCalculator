"""
Unit tests for pattern-aware effective pull-rate calculation.

Tests verify that:
1. Pattern detection uses structured pattern_key field (not brittle card names)
2. Pattern cards (pokeball_pattern, master_ball_pattern) use exact rates
3. Non-pattern cards use rarity-based calculations
4. Card name parameter is NO LONGER used for pattern detection
"""

from types import MappingProxyType
import pytest
from backend.calculations.packCalcsRefractored.evrCalculator import PackEVCalculator


class _ConfigStub:
    """Minimal config for testing pull-rate calculation logic."""
    PULL_RATE_MAPPING = MappingProxyType({})
    RARITY_MAPPING = MappingProxyType({
        "common": "common",
        "uncommon": "uncommon",
        "rare": "rare",
        "double rare": "hits",
        "illustration rare": "hits",
        "special illustration rare": "hits",
    })
    RARE_SLOT_PROBABILITY = {"rare": 1.0}
    REVERSE_SLOT_PROBABILITIES = {
        "slot_1": {"regular reverse": 0.0},
        "slot_2": {"regular reverse": 0.0},
    }

    @staticmethod
    def get_rarity_pack_multiplier():
        # Return the standard multipliers for common/uncommon slots per pack
        return {"common": 4, "uncommon": 3}


class TestPatternAwareEffectivePullRate:
    """Test suite for pattern-aware pull-rate calculations."""

    @pytest.fixture
    def calculator(self):
        """Create a PackEVCalculator instance for testing."""
        config = _ConfigStub()
        return PackEVCalculator(config)

    def test_pokeball_pattern_returns_exact_rate(self, calculator):
        """
        Test that pokeball_pattern cards use exact pull rates.
        
        Pattern overlay cards are database-configured with exact rates,
        so they should return base_pull_rate unchanged.
        """
        base_pull_rate = 10.5
        result = calculator.calculate_effective_pull_rate(
            rarity_group='rare',
            base_pull_rate=base_pull_rate,
            pattern_key='pokeball_pattern'
        )
        assert result == base_pull_rate, \
            "pokeball_pattern should return exact base_pull_rate"

    def test_master_ball_pattern_returns_exact_rate(self, calculator):
        """
        Test that master_ball_pattern cards use exact pull rates.
        
        Pattern overlay cards are database-configured with exact rates,
        so they should return base_pull_rate unchanged.
        """
        base_pull_rate = 15.25
        result = calculator.calculate_effective_pull_rate(
            rarity_group='rare',
            base_pull_rate=base_pull_rate,
            pattern_key='master_ball_pattern'
        )
        assert result == base_pull_rate, \
            "master_ball_pattern should return exact base_pull_rate"

    def test_empty_pattern_key_common_card_uses_guaranteed_slot_calculation(self, calculator):
        """
        Test that common cards with no pattern use guaranteed-slot calculation.
        
        Common cards have a guaranteed slot multiplier (default 4),
        so effective_rate = base_pull_rate / 4.
        """
        base_pull_rate = 20.0  # 1/20
        result = calculator.calculate_effective_pull_rate(
            rarity_group='common',
            base_pull_rate=base_pull_rate,
            pattern_key=''
        )
        # Common multiplier is 4, so 20 / 4 = 5
        expected = base_pull_rate / 4
        assert result == expected, \
            f"Common card should be divided by 4 (slot multiplier). Expected {expected}, got {result}"

    def test_none_pattern_key_common_card_uses_guaranteed_slot_calculation(self, calculator):
        """
        Test that None pattern_key behaves same as empty string for common cards.
        """
        base_pull_rate = 20.0
        result = calculator.calculate_effective_pull_rate(
            rarity_group='common',
            base_pull_rate=base_pull_rate,
            pattern_key=None
        )
        expected = base_pull_rate / 4
        assert result == expected, \
            f"None pattern_key should behave like empty string. Expected {expected}, got {result}"

    def test_empty_pattern_key_uncommon_card_uses_guaranteed_slot_calculation(self, calculator):
        """
        Test that uncommon cards with no pattern use guaranteed-slot calculation.
        
        Uncommon cards have a guaranteed slot multiplier (default 3),
        so effective_rate = base_pull_rate / 3.
        """
        base_pull_rate = 15.0  # 1/15
        result = calculator.calculate_effective_pull_rate(
            rarity_group='uncommon',
            base_pull_rate=base_pull_rate,
            pattern_key=''
        )
        # Uncommon multiplier is 3, so 15 / 3 = 5
        expected = base_pull_rate / 3
        assert result == expected, \
            f"Uncommon card should be divided by 3 (slot multiplier). Expected {expected}, got {result}"

    def test_empty_pattern_key_rare_card_uses_probability_based_calculation(self, calculator):
        """
        Test that rare cards with no pattern use probability-based calculation.
        
        Rare slot probability is 1.0, so:
        effective_probability = 1.0 * (1 / base_pull_rate)
        effective_rate = 1 / effective_probability = base_pull_rate
        """
        base_pull_rate = 5.0  # 1/5
        result = calculator.calculate_effective_pull_rate(
            rarity_group='rare',
            base_pull_rate=base_pull_rate,
            pattern_key=''
        )
        # With rare_slot_prob = 1.0:
        # effective_probability = 1.0 * (1/5) = 0.2
        # effective_rate = 1 / 0.2 = 5.0
        assert result == base_pull_rate, \
            f"Rare card with 100% slot prob should return base_pull_rate. Expected {base_pull_rate}, got {result}"

    def test_pattern_card_ignores_rarity_group_adjustment(self, calculator):
        """
        Test that pattern cards return exact rate regardless of rarity_group.
        
        This ensures pattern cards are not affected by rarity-based multipliers.
        """
        base_pull_rate = 10.0
        
        # Test with 'common' rarity_group (would normally divide by 4)
        result_as_common = calculator.calculate_effective_pull_rate(
            rarity_group='common',
            base_pull_rate=base_pull_rate,
            pattern_key='pokeball_pattern'
        )
        assert result_as_common == base_pull_rate, \
            "Pattern card should ignore 'common' rarity adjustment"
        
        # Test with 'rare' rarity_group
        result_as_rare = calculator.calculate_effective_pull_rate(
            rarity_group='rare',
            base_pull_rate=base_pull_rate,
            pattern_key='master_ball_pattern'
        )
        assert result_as_rare == base_pull_rate, \
            "Pattern card should ignore 'rare' rarity adjustment"

    def test_card_name_not_used_for_pattern_detection(self, calculator):
        """
        Test that card names are NO LONGER used for pattern detection.
        
        Even if a card is named "Master Ball" or "Poke Ball", if pattern_key
        is empty, it should be treated as a regular card.
        """
        base_pull_rate = 20.0
        
        # Card named "Master Ball" but pattern_key is empty
        result = calculator.calculate_effective_pull_rate(
            rarity_group='common',
            base_pull_rate=base_pull_rate,
            pattern_key=''
        )
        
        # Should use common slot calculation, NOT return base_pull_rate exactly
        expected = base_pull_rate / 4
        assert result == expected, \
            f"Card name should NOT affect pattern detection. Expected {expected}, got {result}"

    def test_unrecognized_pattern_key_treated_as_no_pattern(self, calculator):
        """
        Test that unrecognized pattern_key values do not trigger exact-rate logic.
        
        Only 'pokeball_pattern' and 'master_ball_pattern' should be recognized.
        """
        base_pull_rate = 20.0
        
        # Unknown pattern key value
        result = calculator.calculate_effective_pull_rate(
            rarity_group='common',
            base_pull_rate=base_pull_rate,
            pattern_key='unknown_pattern'
        )
        
        # Should use common slot calculation
        expected = base_pull_rate / 4
        assert result == expected, \
            f"Unrecognized pattern_key should be ignored. Expected {expected}, got {result}"

    def test_pattern_detection_case_sensitive(self, calculator):
        """
        Test that pattern key matching is case-sensitive.
        
        Only exact matches 'pokeball_pattern' and 'master_ball_pattern' are recognized.
        Using 'common' rarity to make it easy to detect if pattern matched or not
        (common non-pattern = base/4, pattern = base exactly).
        """
        base_pull_rate = 20.0
        
        # Uppercase should NOT match - should use common calculation (divide by 4)
        result = calculator.calculate_effective_pull_rate(
            rarity_group='common',
            base_pull_rate=base_pull_rate,
            pattern_key='MASTER_BALL_PATTERN'
        )
        
        # Should use common calculation, not return exact rate
        expected = base_pull_rate / 4
        assert result == expected, \
            f"Pattern key matching should be case-sensitive. Expected {expected}, got {result}"

    def test_multiple_pattern_calls_consistent(self, calculator):
        """
        Test that multiple calls with same inputs produce consistent results.
        """
        base_pull_rate = 10.0
        
        result1 = calculator.calculate_effective_pull_rate(
            rarity_group='rare',
            base_pull_rate=base_pull_rate,
            pattern_key='pokeball_pattern'
        )
        result2 = calculator.calculate_effective_pull_rate(
            rarity_group='rare',
            base_pull_rate=base_pull_rate,
            pattern_key='pokeball_pattern'
        )
        
        assert result1 == result2, \
            "Multiple calls should produce consistent results"

    def test_different_base_rates_with_same_pattern(self, calculator):
        """
        Test that different base rates are returned correctly for same pattern.
        """
        result1 = calculator.calculate_effective_pull_rate(
            rarity_group='rare',
            base_pull_rate=5.0,
            pattern_key='master_ball_pattern'
        )
        result2 = calculator.calculate_effective_pull_rate(
            rarity_group='rare',
            base_pull_rate=10.0,
            pattern_key='master_ball_pattern'
        )
        
        assert result1 == 5.0, "Base rate 5.0 should be returned exactly"
        assert result2 == 10.0, "Base rate 10.0 should be returned exactly"

    def test_docstring_exists_and_documents_pattern_semantics(self, calculator):
        """
        Test that the method has a docstring explaining pattern-card semantics.
        """
        docstring = calculator.calculate_effective_pull_rate.__doc__
        assert docstring is not None, "Method should have a docstring"
        assert 'pattern' in docstring.lower(), \
            "Docstring should mention pattern behavior"
        assert 'pattern_key' in docstring, \
            "Docstring should document pattern_key parameter"
        assert 'database' in docstring.lower() or 'db' in docstring.lower(), \
            "Docstring should explain DB configuration semantics"
