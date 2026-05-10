"""Stage 1 Derived Intelligence Metrics Tests.

Tests cover internal component helpers plus the final public Stage 1 pack_score
contract, where only composite fields are exposed at top level.
"""

import pytest
import math
from backend.calculations.evr.derived_metrics import (
    _compute_pack_affordability_component,
    _compute_big_hit_frequency_component,
    _compute_big_hit_upside_component,
    _compute_chase_depth_component,
    _assemble_chase_potential_score,
    _assemble_experience_score,
    _normalize_fixed_anchor_0_100,
    _SCORE_DIRECTION_HIGHER_IS_BETTER,
    _SCORE_DIRECTION_LOWER_IS_BETTER,
    _RUNTIME_V2_ANCHORS,
    compute_all_derived_metrics,
)


# =============================================================================
# Stage 1 Component Tests
# =============================================================================

class TestPackAffordabilityComponent:
    """Pack affordability component should extract pack cost."""

    def test_extracts_pack_cost_when_valid(self):
        result = _compute_pack_affordability_component(25.0)
        assert result == 25.0

    def test_returns_none_for_none(self):
        result = _compute_pack_affordability_component(None)
        assert result is None

    def test_returns_none_for_non_numeric(self):
        result = _compute_pack_affordability_component("not_a_number")
        assert result is None

    def test_returns_none_for_infinity(self):
        result = _compute_pack_affordability_component(math.inf)
        assert result is None

    def test_returns_none_for_nan(self):
        result = _compute_pack_affordability_component(math.nan)
        assert result is None


class TestBigHitFrequencyComponent:
    """Big hit frequency component should extract probability of big hit."""

    def test_extracts_probability_when_valid(self):
        result = _compute_big_hit_frequency_component(0.35)
        assert result == 0.35

    def test_returns_none_for_none(self):
        result = _compute_big_hit_frequency_component(None)
        assert result is None

    def test_returns_zero_probability(self):
        result = _compute_big_hit_frequency_component(0.0)
        assert result == 0.0

    def test_returns_one_probability(self):
        result = _compute_big_hit_frequency_component(1.0)
        assert result == 1.0


class TestBigHitUpsideComponent:
    """Big hit upside component should extract p95 value-to-cost ratio."""

    def test_extracts_ratio_when_valid(self):
        result = _compute_big_hit_upside_component(3.2)
        assert result == 3.2

    def test_returns_none_for_none(self):
        result = _compute_big_hit_upside_component(None)
        assert result is None

    def test_handles_low_ratio(self):
        result = _compute_big_hit_upside_component(0.50)
        assert result == 0.50


class TestChaseDepthComponent:
    """Chase depth component should extract effective chase count."""

    def test_extracts_chase_count_when_valid(self):
        result = _compute_chase_depth_component(8.5)
        assert result == 8.5

    def test_returns_none_for_none(self):
        result = _compute_chase_depth_component(None)
        assert result is None

    def test_handles_low_count(self):
        result = _compute_chase_depth_component(1.0)
        assert result == 1.0

    def test_handles_high_count(self):
        result = _compute_chase_depth_component(35.0)
        assert result == 35.0


# =============================================================================
# Component Normalization Tests
# =============================================================================

class TestPackAffordabilityNormalization:
    """Pack affordability should normalize with lower_is_better direction."""

    def test_cheaper_pack_scores_higher(self):
        # Using anchor min=5, max=50, lower_is_better
        cheap = _normalize_fixed_anchor_0_100(
            10.0,
            min_anchor=5.0,
            max_anchor=50.0,
            direction=_SCORE_DIRECTION_LOWER_IS_BETTER,
        )
        expensive = _normalize_fixed_anchor_0_100(
            40.0,
            min_anchor=5.0,
            max_anchor=50.0,
            direction=_SCORE_DIRECTION_LOWER_IS_BETTER,
        )
        assert cheap > expensive

    def test_neutral_fallback_for_none(self):
        result = _normalize_fixed_anchor_0_100(
            None,
            min_anchor=5.0,
            max_anchor=50.0,
            direction=_SCORE_DIRECTION_LOWER_IS_BETTER,
        )
        assert result == 50.0  # neutral score


class TestBigHitFrequencyNormalization:
    """Big hit frequency should normalize with higher_is_better direction."""

    def test_higher_probability_scores_higher(self):
        high_prob = _normalize_fixed_anchor_0_100(
            0.8,
            min_anchor=0.0,
            max_anchor=1.0,
            direction=_SCORE_DIRECTION_HIGHER_IS_BETTER,
        )
        low_prob = _normalize_fixed_anchor_0_100(
            0.2,
            min_anchor=0.0,
            max_anchor=1.0,
            direction=_SCORE_DIRECTION_HIGHER_IS_BETTER,
        )
        assert high_prob > low_prob
        assert high_prob > 50.0  # above neutral
        assert low_prob < 50.0   # below neutral


class TestBigHitUpsideNormalization:
    """Big hit upside should normalize with higher_is_better direction."""

    def test_higher_ratio_scores_higher(self):
        high_upside = _normalize_fixed_anchor_0_100(
            4.5,
            min_anchor=0.25,
            max_anchor=5.0,
            direction=_SCORE_DIRECTION_HIGHER_IS_BETTER,
        )
        low_upside = _normalize_fixed_anchor_0_100(
            1.0,
            min_anchor=0.25,
            max_anchor=5.0,
            direction=_SCORE_DIRECTION_HIGHER_IS_BETTER,
        )
        assert high_upside > low_upside


class TestChaseDepthNormalization:
    """Chase depth should normalize with higher_is_better direction."""

    def test_higher_count_scores_higher(self):
        diverse = _normalize_fixed_anchor_0_100(
            30.0,
            min_anchor=1.0,
            max_anchor=40.0,
            direction=_SCORE_DIRECTION_HIGHER_IS_BETTER,
        )
        concentrated = _normalize_fixed_anchor_0_100(
            3.0,
            min_anchor=1.0,
            max_anchor=40.0,
            direction=_SCORE_DIRECTION_HIGHER_IS_BETTER,
        )
        assert diverse > concentrated


# =============================================================================
# Composite Metric Assembly Tests
# =============================================================================

class TestChasePotentialScoreAssembly:
    """Chase Potential Score should blend components correctly."""

    def test_produces_bounded_score_when_all_components_valid(self):
        score = _assemble_chase_potential_score(
            big_hit_frequency_normalized=75.0,
            big_hit_upside_normalized=80.0,
            chase_depth_normalized=70.0,
            pack_affordability_normalized=65.0,
            profit_score=72.0,
        )
        assert 0.0 <= score <= 100.0
        assert 60.0 < score < 85.0  # should be reasonably high

    def test_higher_components_produce_higher_score(self):
        low_score = _assemble_chase_potential_score(
            big_hit_frequency_normalized=20.0,
            big_hit_upside_normalized=25.0,
            chase_depth_normalized=30.0,
            pack_affordability_normalized=35.0,
            profit_score=40.0,
        )
        high_score = _assemble_chase_potential_score(
            big_hit_frequency_normalized=80.0,
            big_hit_upside_normalized=85.0,
            chase_depth_normalized=80.0,
            pack_affordability_normalized=75.0,
            profit_score=80.0,
        )
        assert low_score < high_score

    def test_neutral_components_produce_neutral_score(self):
        neutral_score = _assemble_chase_potential_score(
            big_hit_frequency_normalized=50.0,
            big_hit_upside_normalized=50.0,
            chase_depth_normalized=50.0,
            pack_affordability_normalized=50.0,
            profit_score=50.0,
        )
        assert 45.0 <= neutral_score <= 55.0  # close to 50


class TestExperienceScoreAssembly:
    """Experience Score should blend components correctly."""

    def test_produces_bounded_score_when_all_components_valid(self):
        score = _assemble_experience_score(
            prob_profit_normalized=78.0,
            median_value_to_cost_normalized=75.0,
            safety_score=72.0,
            big_hit_frequency_normalized=68.0,
            stability_score=70.0,
        )
        assert 0.0 <= score <= 100.0

    def test_high_probability_of_profit_boosts_experience(self):
        high_prob_profit = _assemble_experience_score(
            prob_profit_normalized=90.0,  # 35% weight
            median_value_to_cost_normalized=50.0,
            safety_score=50.0,
            big_hit_frequency_normalized=50.0,
            stability_score=50.0,
        )
        low_prob_profit = _assemble_experience_score(
            prob_profit_normalized=20.0,
            median_value_to_cost_normalized=50.0,
            safety_score=50.0,
            big_hit_frequency_normalized=50.0,
            stability_score=50.0,
        )
        assert high_prob_profit > low_prob_profit

    def test_safe_downside_boosts_experience(self):
        safe = _assemble_experience_score(
            prob_profit_normalized=50.0,
            median_value_to_cost_normalized=50.0,
            safety_score=85.0,  # 20% weight
            big_hit_frequency_normalized=50.0,
            stability_score=50.0,
        )
        risky = _assemble_experience_score(
            prob_profit_normalized=50.0,
            median_value_to_cost_normalized=50.0,
            safety_score=15.0,
            big_hit_frequency_normalized=50.0,
            stability_score=50.0,
        )
        assert safe > risky


# =============================================================================
# Integration Tests
# =============================================================================

class TestComputeAllDerivedMetricsIncludesNewMetrics:
    """compute_all_derived_metrics should include Stage 1 metrics in pack_score."""

    def test_pack_score_includes_stage1_metrics(self):
        values = [3.0, 5.0, 8.0, 10.0, 12.0, 15.0, 20.0, 25.0, 30.0, 35.0]
        pack_cost = 4.0
        card_ev_contributions = {"card_1": 7.0, "card_2": 3.0, "card_3": 1.0}

        all_metrics = compute_all_derived_metrics(
            values,
            pack_cost,
            card_ev_contributions=card_ev_contributions,
        )

        pack_score_payload = all_metrics.get("pack_score", {})

        # Check that the public Stage 1 composite metrics are present
        assert "score_version" in pack_score_payload
        assert "normalization_mode" in pack_score_payload
        assert "pack_score_is_placeholder" in pack_score_payload
        assert "profit_score" in pack_score_payload
        assert "safety_score" in pack_score_payload
        assert "stability_score" in pack_score_payload
        assert "pack_score" in pack_score_payload
        assert "chase_potential_score" in pack_score_payload
        assert "experience_score" in pack_score_payload
        assert "chase_potential_tier" in pack_score_payload
        assert "experience_tier" in pack_score_payload
        assert "derived_metric_version" in pack_score_payload

        # Internal components can remain nested for debugging but not top-level.
        for removed_field in [
            "pack_affordability_score",
            "big_hit_frequency_score",
            "big_hit_upside_score",
            "chase_depth_score",
            "relative_chase_potential_score",
            "relative_experience_score",
        ]:
            assert removed_field not in pack_score_payload

    def test_new_metrics_are_bounded_0_100(self):
        values = [2.0, 4.0, 6.0, 8.0, 10.0, 12.0, 15.0, 18.0, 22.0, 25.0]
        pack_cost = 3.0
        card_ev_contributions = {"card_1": 5.0, "card_2": 2.0, "card_3": 1.0}

        all_metrics = compute_all_derived_metrics(
            values,
            pack_cost,
            card_ev_contributions=card_ev_contributions,
        )

        pack_score_payload = all_metrics.get("pack_score", {})

        # Verify all public Stage 1 and canonical scores are in 0-100 range
        for metric_name in [
            "chase_potential_score",
            "experience_score",
            "pack_score",
            "profit_score",
            "safety_score",
            "stability_score",
        ]:
            score = pack_score_payload.get(metric_name)
            assert score is not None, f"{metric_name} should not be None"
            assert 0.0 <= score <= 100.0, f"{metric_name} should be bounded 0-100, got {score}"

        assert pack_score_payload.get("chase_potential_tier") is None
        assert pack_score_payload.get("experience_tier") is None

    def test_existing_metrics_unchanged(self):
        """Verify that adding Stage 1 metrics does not change existing scores."""
        values = [3.0, 5.0, 7.0, 9.0, 11.0, 13.0, 16.0, 19.0, 22.0, 25.0]
        pack_cost = 5.0
        card_ev_contributions = {"card_a": 6.0, "card_b": 4.0, "card_c": 2.0}

        all_metrics = compute_all_derived_metrics(
            values,
            pack_cost,
            card_ev_contributions=card_ev_contributions,
        )

        pack_score_payload = all_metrics.get("pack_score", {})

        # Verify existing scores are still present and valid
        assert "pack_score" in pack_score_payload
        assert "profit_score" in pack_score_payload
        assert "safety_score" in pack_score_payload
        assert "stability_score" in pack_score_payload
        
        # All should be bounded 0-100
        for score_name in ["pack_score", "profit_score", "safety_score", "stability_score"]:
            score = pack_score_payload.get(score_name)
            assert 0.0 <= score <= 100.0

    def test_weights_include_stage1_metrics(self):
        """Verify that weights are included for the new composite metrics."""
        values = [4.0, 6.0, 8.0, 10.0, 12.0, 14.0, 16.0, 18.0, 20.0, 22.0]
        pack_cost = 4.0
        card_ev_contributions = {"card_1": 5.0, "card_2": 3.0}

        all_metrics = compute_all_derived_metrics(
            values,
            pack_cost,
            card_ev_contributions=card_ev_contributions,
        )

        pack_score_payload = all_metrics.get("pack_score", {})
        weights_pct = pack_score_payload.get("weights_pct", {})
        weights_normalized = pack_score_payload.get("weights_normalized", {})

        # Check that Stage 1 weights are present
        assert "chase_potential_score" in weights_pct
        assert "experience_score" in weights_pct
        assert "chase_potential_score" in weights_normalized
        assert "experience_score" in weights_normalized

    def test_version_field_set_correctly(self):
        """Verify that derived_metric_version is set to v1."""
        values = [3.0, 5.0, 7.0, 9.0, 11.0]
        pack_cost = 3.0

        all_metrics = compute_all_derived_metrics(values, pack_cost)
        pack_score_payload = all_metrics.get("pack_score", {})

        assert pack_score_payload.get("derived_metric_version") == "derived_intelligence_v1"

    def test_p95_ratio_remains_canonical_big_hit_upside_metric(self):
        values = [3.0, 5.0, 8.0, 10.0, 12.0, 15.0]
        pack_cost = 4.0

        all_metrics = compute_all_derived_metrics(values, pack_cost)
        pack_score_payload = all_metrics.get("pack_score", {})
        raw_inputs = pack_score_payload.get("raw_inputs", {})
        normalized_inputs = pack_score_payload.get("normalized_inputs", {})

        assert "p95_value_to_cost_ratio" in raw_inputs
        assert "big_hit_upside_score" in normalized_inputs
        assert "big_hit_upside_score" not in pack_score_payload


class TestStage1CompositeHelpers:
    """Composite helper functions should remain bounded."""

    def test_chase_potential_helper_is_bounded(self):
        result = _assemble_chase_potential_score(
            big_hit_frequency_normalized=50.0,
            big_hit_upside_normalized=75.0,
            chase_depth_normalized=60.0,
            pack_affordability_normalized=55.0,
            profit_score=80.0,
        )
        assert 0 <= result <= 100

    def test_experience_helper_is_bounded(self):
        result = _assemble_experience_score(
            prob_profit_normalized=60.0,
            median_value_to_cost_normalized=70.0,
            safety_score=70.0,
            big_hit_frequency_normalized=40.0,
            stability_score=75.0,
        )
        assert 0 <= result <= 100


class TestDerivedMetricsIntegration:
    """Integration tests for compute_all_derived_metrics."""

    def test_includes_chase_potential_and_experience_scores(self):
        values = [10, 20, 30, 40, 50]
        pack_cost = 25.0
        all_metrics = compute_all_derived_metrics(values, pack_cost)
        assert "chase_potential_score" in all_metrics["pack_score"]
        assert "experience_score" in all_metrics["pack_score"]
        assert 0 <= all_metrics["pack_score"]["chase_potential_score"] <= 100
        assert 0 <= all_metrics["pack_score"]["experience_score"] <= 100
