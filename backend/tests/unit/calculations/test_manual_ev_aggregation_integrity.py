"""
Tests for manual EV aggregation integrity audit.

Verifies that:
1. Pattern-overlay rows aggregate to INTENDED buckets (master_ball_pattern, pokeball_pattern)
2. Pattern rows do NOT ALSO contribute through conflicting base-rarity buckets
3. Aggregation axis is correct and stable
4. No row appears in two conflicting buckets
"""
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


class TestPatternRowAggregation:
    """Tests verifying pattern rows aggregate to pattern buckets, not base buckets."""

    def test_pattern_row_in_pattern_bucket_not_base_bucket(self):
        """
        Pattern rows (e.g., master_ball_pattern with base rarity=rare) should:
        - Be counted in ev_totals_by_rarity['master_ball_pattern']
        - NOT be counted in ev_totals_by_rarity['rare']
        """
        calculator = _build_calculator()
        
        # Synthetic data: pattern row with base rarity 'rare'
        df = pd.DataFrame({
            'Card Name': ['Master Ball Pattern Rare Card'],
            'aggregation_key': ['master_ball_pattern'],  # Pattern rows have pattern as aggregation_key
            'rarity_key': ['rare'],  # But may have base rarity in rarity_key
            'pattern_key': ['master_ball_pattern'],  # Indicates it's a pattern row
            'EV': [10.0],
        })
        
        ev_totals = calculator.calculate_rarity_ev_totals(df, ev_reverse_total=0.0)
        
        # Verify pattern bucket contains the row
        assert 'master_ball_pattern' in ev_totals
        assert ev_totals['master_ball_pattern'] == pytest.approx(10.0)
        
        # Verify base rarity bucket does NOT contain the row
        # (If it did, we'd have double-counting)
        if 'rare' in ev_totals:
            assert ev_totals['rare'] == pytest.approx(0.0), \
                f"Pattern row should not be counted in base rarity bucket. rare={ev_totals['rare']}"
        else:
            assert 'rare' not in ev_totals, \
                f"Base rarity 'rare' should not be in buckets if no non-pattern rows exist"

    def test_pokeball_pattern_row_aggregates_to_pattern_bucket(self):
        """Pokeball pattern rows aggregate to pokeball_pattern bucket, not base rarity."""
        calculator = _build_calculator()
        
        df = pd.DataFrame({
            'Card Name': ['Poke Ball Pattern Common Card'],
            'aggregation_key': ['pokeball_pattern'],
            'rarity_key': ['common'],
            'pattern_key': ['pokeball_pattern'],
            'EV': [5.5],
        })
        
        ev_totals = calculator.calculate_rarity_ev_totals(df, ev_reverse_total=0.0)
        
        assert 'pokeball_pattern' in ev_totals
        assert ev_totals['pokeball_pattern'] == pytest.approx(5.5)
        assert 'common' not in ev_totals, \
            "Base rarity 'common' should not appear if all commons are pattern rows"

    def test_no_double_counting_with_mixed_patterns_and_base_rarities(self):
        """
        Mixed dataset with both pattern rows and base-rarity rows should:
        - Count pattern rows only in pattern buckets
        - Count base-rarity rows only in base-rarity buckets
        - Have zero overlap
        """
        calculator = _build_calculator()
        
        df = pd.DataFrame({
            'Card Name': [
                'Master Ball Pattern Rare',
                'Poke Ball Pattern Common',
                'Regular Rare',
                'Regular Common',
            ],
            'aggregation_key': [
                'master_ball_pattern',
                'pokeball_pattern',
                'rare',
                'common',
            ],
            'rarity_key': [
                'rare',
                'common',
                'rare',
                'common',
            ],
            'pattern_key': [
                'master_ball_pattern',
                'pokeball_pattern',
                '',
                '',
            ],
            'EV': [10.0, 5.0, 15.0, 8.0],
        })
        
        ev_totals = calculator.calculate_rarity_ev_totals(df, ev_reverse_total=0.0)
        
        # Pattern buckets should contain only pattern rows
        assert ev_totals['master_ball_pattern'] == pytest.approx(10.0)
        assert ev_totals['pokeball_pattern'] == pytest.approx(5.0)
        
        # Base-rarity buckets should contain only non-pattern rows
        assert ev_totals['rare'] == pytest.approx(15.0)
        assert ev_totals['common'] == pytest.approx(8.0)
        
        # Total should be sum of all EVs (no double-counting)
        total_from_buckets = sum(v for k, v in ev_totals.items() if k != 'reverse')
        expected_total = 10.0 + 5.0 + 15.0 + 8.0
        assert total_from_buckets == pytest.approx(expected_total)

    def test_multiple_pattern_rows_same_pattern(self):
        """Multiple rows with same pattern should all be in that pattern bucket."""
        calculator = _build_calculator()
        
        df = pd.DataFrame({
            'Card Name': [
                'Master Ball Pattern Rare A',
                'Master Ball Pattern Rare B',
                'Master Ball Pattern Common',
            ],
            'aggregation_key': [
                'master_ball_pattern',
                'master_ball_pattern',
                'master_ball_pattern',
            ],
            'rarity_key': [
                'rare',
                'rare',
                'common',
            ],
            'pattern_key': [
                'master_ball_pattern',
                'master_ball_pattern',
                'master_ball_pattern',
            ],
            'EV': [10.0, 12.0, 8.0],
        })
        
        ev_totals = calculator.calculate_rarity_ev_totals(df, ev_reverse_total=0.0)
        
        assert ev_totals['master_ball_pattern'] == pytest.approx(10.0 + 12.0 + 8.0)
        assert 'rare' not in ev_totals
        assert 'common' not in ev_totals


class TestNonPatternRowAggregation:
    """Tests verifying non-pattern rows aggregate to base-rarity buckets."""

    def test_non_pattern_row_in_base_bucket(self):
        """Non-pattern rows should be counted in their base-rarity bucket."""
        calculator = _build_calculator()
        
        df = pd.DataFrame({
            'Card Name': ['Regular Rare Card'],
            'aggregation_key': ['rare'],
            'rarity_key': ['rare'],
            'pattern_key': [''],
            'EV': [5.0],
        })
        
        ev_totals = calculator.calculate_rarity_ev_totals(df, ev_reverse_total=0.0)
        
        assert ev_totals['rare'] == pytest.approx(5.0)
        assert 'master_ball_pattern' not in ev_totals
        assert 'pokeball_pattern' not in ev_totals

    def test_multiple_non_pattern_rows_same_rarity(self):
        """Multiple non-pattern rows with same rarity aggregate to one bucket."""
        calculator = _build_calculator()
        
        df = pd.DataFrame({
            'Card Name': ['Uncommon A', 'Uncommon B', 'Uncommon C'],
            'aggregation_key': ['uncommon', 'uncommon', 'uncommon'],
            'rarity_key': ['uncommon', 'uncommon', 'uncommon'],
            'pattern_key': ['', '', ''],
            'EV': [2.0, 3.0, 4.0],
        })
        
        ev_totals = calculator.calculate_rarity_ev_totals(df, ev_reverse_total=0.0)
        
        assert ev_totals['uncommon'] == pytest.approx(2.0 + 3.0 + 4.0)


class TestAggregationConsistency:
    """Tests verifying aggregation consistency and no structural double-counting."""

    def test_row_level_ev_equals_bucket_total_sum(self):
        """
        Sum of all row EV values (grouped by aggregation_key) should equal
        sum of all values in ev_totals_by_rarity (excluding reverse).
        """
        calculator = _build_calculator()
        
        df = pd.DataFrame({
            'Card Name': [
                'Master Ball A',
                'Poke Ball B',
                'Rare C',
                'Common D',
            ],
            'aggregation_key': [
                'master_ball_pattern',
                'pokeball_pattern',
                'rare',
                'common',
            ],
            'rarity_key': [
                'rare',
                'common',
                'rare',
                'common',
            ],
            'pattern_key': [
                'master_ball_pattern',
                'pokeball_pattern',
                '',
                '',
            ],
            'EV': [7.5, 3.2, 9.1, 2.3],
        })
        
        ev_totals = calculator.calculate_rarity_ev_totals(df, ev_reverse_total=5.0)
        
        # Use audit to verify
        audit_result = calculator.audit_ev_aggregation_integrity(df, ev_totals)
        
        assert audit_result['is_valid'], \
            f"Audit failed with issues: {audit_result['issues']}"
        assert audit_result['row_sum'] == pytest.approx(audit_result['bucket_sum'])

    def test_no_double_counting_with_mixed_rows(self):
        """Comprehensive test ensuring no double-counting with complex mix."""
        calculator = _build_calculator()
        
        # Create a more realistic dataset
        df = pd.DataFrame({
            'Card Name': [
                'Master Ball Pattern Rare 1',
                'Master Ball Pattern Rare 2',
                'Poke Ball Pattern Common 1',
                'Regular Rare 1',
                'Regular Rare 2',
                'Regular Common 1',
                'Regular Uncommon 1',
            ],
            'aggregation_key': [
                'master_ball_pattern',
                'master_ball_pattern',
                'pokeball_pattern',
                'rare',
                'rare',
                'common',
                'uncommon',
            ],
            'rarity_key': [
                'rare',
                'rare',
                'common',
                'rare',
                'rare',
                'common',
                'uncommon',
            ],
            'pattern_key': [
                'master_ball_pattern',
                'master_ball_pattern',
                'pokeball_pattern',
                '',
                '',
                '',
                '',
            ],
            'EV': [10.0, 12.0, 5.0, 15.0, 18.0, 8.0, 6.0],
        })
        
        ev_totals = calculator.calculate_rarity_ev_totals(df, ev_reverse_total=2.0)
        audit_result = calculator.audit_ev_aggregation_integrity(df, ev_totals)
        
        assert audit_result['is_valid'], \
            f"Audit failed with issues: {audit_result['issues']}"
        
        # Verify expected bucket values
        assert ev_totals['master_ball_pattern'] == pytest.approx(10.0 + 12.0)
        assert ev_totals['pokeball_pattern'] == pytest.approx(5.0)
        assert ev_totals['rare'] == pytest.approx(15.0 + 18.0)
        assert ev_totals['common'] == pytest.approx(8.0)
        assert ev_totals['uncommon'] == pytest.approx(6.0)
        
        # Total (including reverse)
        expected_total = 10.0 + 12.0 + 5.0 + 15.0 + 18.0 + 8.0 + 6.0 + 2.0
        actual_total = sum(ev_totals.values())
        assert actual_total == pytest.approx(expected_total)


class TestAuditFunction:
    """Tests specifically for the audit_ev_aggregation_integrity() function."""

    def test_audit_valid_when_no_double_counting(self):
        """Audit should pass (is_valid=True) when data has no double-counting."""
        calculator = _build_calculator()
        
        df = pd.DataFrame({
            'Card Name': ['Pattern Rare', 'Regular Rare'],
            'aggregation_key': ['master_ball_pattern', 'rare'],
            'rarity_key': ['rare', 'rare'],
            'pattern_key': ['master_ball_pattern', ''],
            'EV': [10.0, 15.0],
        })
        
        ev_totals = calculator.calculate_rarity_ev_totals(df, ev_reverse_total=0.0)
        audit_result = calculator.audit_ev_aggregation_integrity(df, ev_totals)
        
        assert audit_result['is_valid']
        assert len(audit_result['issues']) == 0

    def test_audit_reports_missing_columns(self):
        """Audit should report missing required columns."""
        calculator = _build_calculator()
        
        # DataFrame missing 'aggregation_key'
        df = pd.DataFrame({
            'Card Name': ['Some Card'],
            'rarity_key': ['rare'],
            'EV': [10.0],
        })
        
        ev_totals = {'rare': 10.0}
        audit_result = calculator.audit_ev_aggregation_integrity(df, ev_totals)
        
        assert not audit_result['is_valid']
        assert any("missing" in issue.lower() for issue in audit_result['issues'])

    def test_audit_spot_checks_pattern_rows(self):
        """Audit should perform spot-checks on pattern rows."""
        calculator = _build_calculator()
        
        df = pd.DataFrame({
            'Card Name': [
                'Master Ball Pattern Rare A',
                'Master Ball Pattern Rare B',
            ],
            'aggregation_key': [
                'master_ball_pattern',
                'master_ball_pattern',
            ],
            'rarity_key': ['rare', 'rare'],
            'pattern_key': ['master_ball_pattern', 'master_ball_pattern'],
            'EV': [10.0, 12.0],
        })
        
        ev_totals = calculator.calculate_rarity_ev_totals(df, ev_reverse_total=0.0)
        audit_result = calculator.audit_ev_aggregation_integrity(df, ev_totals)
        
        assert audit_result['is_valid']
        
        # Check spot-check structure
        assert 'spot_checks' in audit_result
        assert 'pattern_rows' in audit_result['spot_checks']
        assert 'master_ball_pattern' in audit_result['spot_checks']['pattern_rows']
        
        pattern_check = audit_result['spot_checks']['pattern_rows']['master_ball_pattern']
        assert pattern_check['row_count'] == 2
        assert pattern_check['ev_from_rows'] == pytest.approx(10.0 + 12.0)
        assert pattern_check['ev_in_bucket'] == pytest.approx(10.0 + 12.0)
        assert pattern_check['match']

    def test_audit_spot_checks_non_pattern_rows(self):
        """Audit should perform spot-checks on non-pattern rows."""
        calculator = _build_calculator()
        
        df = pd.DataFrame({
            'Card Name': ['Rare A', 'Rare B', 'Rare C'],
            'aggregation_key': ['rare', 'rare', 'rare'],
            'rarity_key': ['rare', 'rare', 'rare'],
            'pattern_key': ['', '', ''],
            'EV': [5.0, 6.0, 7.0],
        })
        
        ev_totals = calculator.calculate_rarity_ev_totals(df, ev_reverse_total=0.0)
        audit_result = calculator.audit_ev_aggregation_integrity(df, ev_totals)
        
        assert audit_result['is_valid']
        assert 'non_pattern_rows' in audit_result['spot_checks']
        assert 'rare' in audit_result['spot_checks']['non_pattern_rows']
        
        rare_check = audit_result['spot_checks']['non_pattern_rows']['rare']
        assert rare_check['row_count'] == 3
        assert rare_check['ev_from_rows'] == pytest.approx(5.0 + 6.0 + 7.0)
        assert rare_check['ev_in_bucket'] == pytest.approx(5.0 + 6.0 + 7.0)
        assert rare_check['match']

    def test_audit_row_sum_and_bucket_sum_comparison(self):
        """Audit should report row_sum and bucket_sum for verification."""
        calculator = _build_calculator()
        
        df = pd.DataFrame({
            'Card Name': [
                'Master Ball Rare',
                'Regular Rare',
                'Regular Common',
            ],
            'aggregation_key': [
                'master_ball_pattern',
                'rare',
                'common',
            ],
            'rarity_key': ['rare', 'rare', 'common'],
            'pattern_key': ['master_ball_pattern', '', ''],
            'EV': [20.0, 30.0, 15.0],
        })
        
        ev_totals = calculator.calculate_rarity_ev_totals(df, ev_reverse_total=0.0)
        audit_result = calculator.audit_ev_aggregation_integrity(df, ev_totals)
        
        expected_row_sum = 20.0 + 30.0 + 15.0
        expected_bucket_sum = 20.0 + 30.0 + 15.0
        
        assert audit_result['row_sum'] == pytest.approx(expected_row_sum)
        assert audit_result['bucket_sum'] == pytest.approx(expected_bucket_sum)


class TestPrismaticFixtureSimulation:
    """Tests using synthetic data that simulates Prismatic set data."""

    def test_prismatic_fixture_data_integrity(self):
        """
        Simulates Prismatic set with:
        - Common (no pattern)
        - Uncommon (no pattern)
        - Rare (no pattern)
        - Rare + Master Ball pattern
        - Common + Poke Ball pattern
        """
        calculator = _build_calculator()
        
        # Simulated Prismatic set data
        df = pd.DataFrame({
            'Card Name': [
                'Bulbasaur Common',
                'Charmander Uncommon',
                'Squirtle Rare',
                'Pikachu Rare (Master Ball Pattern)',
                'Venusaur Common (Poke Ball Pattern)',
            ],
            'Rarity': ['common', 'uncommon', 'rare', 'rare', 'common'],
            'Special Type': ['', '', '', 'master ball', 'poke ball'],
            'aggregation_key': [
                'common',
                'uncommon',
                'rare',
                'master_ball_pattern',
                'pokeball_pattern',
            ],
            'rarity_key': [
                'common',
                'uncommon',
                'rare',
                'rare',
                'common',
            ],
            'pattern_key': [
                '',
                '',
                '',
                'master_ball_pattern',
                'pokeball_pattern',
            ],
            'EV': [1.0, 2.0, 3.0, 4.0, 5.0],
        })
        
        ev_totals = calculator.calculate_rarity_ev_totals(df, ev_reverse_total=1.5)
        audit_result = calculator.audit_ev_aggregation_integrity(df, ev_totals)
        
        # Verify audit passes
        assert audit_result['is_valid'], \
            f"Prismatic fixture audit failed: {audit_result['issues']}"
        
        # Verify aggregation
        assert ev_totals['common'] == pytest.approx(1.0)  # Non-pattern common only
        assert ev_totals['uncommon'] == pytest.approx(2.0)
        assert ev_totals['rare'] == pytest.approx(3.0)  # Non-pattern rare only
        assert ev_totals['master_ball_pattern'] == pytest.approx(4.0)
        assert ev_totals['pokeball_pattern'] == pytest.approx(5.0)
        assert ev_totals['reverse'] == pytest.approx(1.5)
        
        # Verify no double-counting
        non_reverse_total = sum(v for k, v in ev_totals.items() if k != 'reverse')
        assert non_reverse_total == pytest.approx(1.0 + 2.0 + 3.0 + 4.0 + 5.0)

    def test_prismatic_with_multiple_patterns_per_rarity(self):
        """Prismatic set with multiple pattern variants per rarity level."""
        calculator = _build_calculator()
        
        df = pd.DataFrame({
            'Card Name': [
                'Card 1 Common',
                'Card 2 Common (MB)',
                'Card 3 Common (PB)',
                'Card 4 Rare',
                'Card 5 Rare (MB)',
                'Card 6 Rare (PB)',
            ],
            'aggregation_key': [
                'common',
                'master_ball_pattern',
                'pokeball_pattern',
                'rare',
                'master_ball_pattern',
                'pokeball_pattern',
            ],
            'rarity_key': [
                'common',
                'common',
                'common',
                'rare',
                'rare',
                'rare',
            ],
            'pattern_key': [
                '',
                'master_ball_pattern',
                'pokeball_pattern',
                '',
                'master_ball_pattern',
                'pokeball_pattern',
            ],
            'EV': [1.0, 2.0, 2.5, 3.0, 3.5, 4.0],
        })
        
        ev_totals = calculator.calculate_rarity_ev_totals(df, ev_reverse_total=0.5)
        audit_result = calculator.audit_ev_aggregation_integrity(df, ev_totals)
        
        assert audit_result['is_valid']
        
        # Base rarities should only contain non-pattern rows
        assert ev_totals['common'] == pytest.approx(1.0)
        assert ev_totals['rare'] == pytest.approx(3.0)
        
        # Pattern buckets should contain all pattern rows
        assert ev_totals['master_ball_pattern'] == pytest.approx(2.0 + 3.5)
        assert ev_totals['pokeball_pattern'] == pytest.approx(2.5 + 4.0)

    def test_prismatic_all_rows_are_patterns(self):
        """Edge case: all rows are pattern rows (no base rarities)."""
        calculator = _build_calculator()
        
        df = pd.DataFrame({
            'Card Name': [
                'Pattern A (MB)',
                'Pattern B (MB)',
                'Pattern C (PB)',
                'Pattern D (PB)',
            ],
            'aggregation_key': [
                'master_ball_pattern',
                'master_ball_pattern',
                'pokeball_pattern',
                'pokeball_pattern',
            ],
            'rarity_key': ['rare', 'rare', 'common', 'common'],
            'pattern_key': [
                'master_ball_pattern',
                'master_ball_pattern',
                'pokeball_pattern',
                'pokeball_pattern',
            ],
            'EV': [5.0, 6.0, 3.0, 4.0],
        })
        
        ev_totals = calculator.calculate_rarity_ev_totals(df, ev_reverse_total=0.0)
        audit_result = calculator.audit_ev_aggregation_integrity(df, ev_totals)
        
        assert audit_result['is_valid']
        assert ev_totals['master_ball_pattern'] == pytest.approx(5.0 + 6.0)
        assert ev_totals['pokeball_pattern'] == pytest.approx(3.0 + 4.0)
        assert 'common' not in ev_totals
        assert 'rare' not in ev_totals


class TestAggregationAxisStability:
    """Tests verifying aggregation axis is correct and stable."""

    def test_aggregation_key_stability_with_same_data(self):
        """Running aggregation twice on same data should yield same results."""
        calculator = _build_calculator()
        
        df = pd.DataFrame({
            'Card Name': ['A', 'B', 'C'],
            'aggregation_key': ['rare', 'master_ball_pattern', 'common'],
            'rarity_key': ['rare', 'rare', 'common'],
            'pattern_key': ['', 'master_ball_pattern', ''],
            'EV': [10.0, 5.0, 3.0],
        })
        
        result1 = calculator.calculate_rarity_ev_totals(df, ev_reverse_total=1.0)
        result2 = calculator.calculate_rarity_ev_totals(df, ev_reverse_total=1.0)
        
        assert result1 == result2

    def test_fallback_to_rarity_key_when_aggregation_key_empty(self):
        """When aggregation_key is empty, should fall back to rarity_key."""
        calculator = _build_calculator()
        
        df = pd.DataFrame({
            'Card Name': ['Card A', 'Card B'],
            'aggregation_key': ['', ''],  # Empty aggregation_key
            'rarity_key': ['rare', 'common'],  # Should use these as fallback
            'pattern_key': ['', ''],
            'EV': [10.0, 5.0],
        })
        
        ev_totals = calculator.calculate_rarity_ev_totals(df, ev_reverse_total=0.0)
        
        # Should fall back to rarity_key values
        assert ev_totals['rare'] == pytest.approx(10.0)
        assert ev_totals['common'] == pytest.approx(5.0)
