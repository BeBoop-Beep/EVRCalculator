"""Tests for the derived decision-metrics layer.

All tests use deterministic toy inputs so they run without any database,
external config, or real simulation data.

Test categories
---------------
1.  prob_profit — counts over known value arrays
2.  big-hit probabilities — fixed and dynamic
3.  downside metrics — conditional vs unconditional separation
4.  coefficient of variation
5.  chase dependency — known EV contribution maps
6.  session simulation metrics — deterministic toy pack function
7.  packs-to-hit — deterministic toy scenarios
8.  PACK Score — bounded 0-100, correct direction
9.  score component breakdown present and interpretable
10. compute_all_derived_metrics integration path
11. PackSimulationSummary dataclass construction
"""

from __future__ import annotations

import math
from typing import List, Optional
from unittest.mock import patch

import numpy as np
import pytest

from backend.calculations.evr.derived_metrics import (
    _PACK_SCORE_V2_WEIGHTS_PCT,
    _RUNTIME_V2_ANCHORS,
    _weighted_average,
    _compute_effective_chase_count,
    _compute_hhi_from_ev_contributions,
    _normalize_fixed_anchor_0_100,
    PackSimulationSummary,
    build_pack_simulation_summary,
    compute_all_derived_metrics,
    compute_chase_dependency_metrics,
    compute_downside_metrics,
    compute_pack_scores_for_set_records,
    compute_pack_decision_metrics,
    compute_probability_metrics,
    compute_volatility_metrics,
    derive_packs_to_hit_metrics,
    derive_session_metrics,
    simulate_packs_until_hit,
    simulate_session,
)


# ---------------------------------------------------------------------------
# Helpers / fixtures
# ---------------------------------------------------------------------------

def _make_values(profit_frac: float = 0.6, n: int = 1000, pack_cost: float = 5.0) -> List[float]:
    """Build a controlled value array.

    profit_frac × n values are at pack_cost + 1.0 (profit side).
    (1 - profit_frac) × n values are at pack_cost - 1.0 (loss side).
    """
    rng = np.random.default_rng(42)
    n_profit = int(round(profit_frac * n))
    n_loss = n - n_profit
    profit_vals = rng.uniform(pack_cost + 0.01, pack_cost + 10.0, size=n_profit).tolist()
    loss_vals = rng.uniform(0.0, pack_cost - 0.01, size=n_loss).tolist()
    combined = profit_vals + loss_vals
    rng.shuffle(combined)
    return combined


PACK_COST = 5.0
TOY_VALUES = [1.0, 2.0, 3.0, 4.0, 5.0, 6.0, 7.0, 8.0, 9.0, 10.0]
#  pack_cost = 5.0 → values [5,6,7,8,9,10] are profit → 6/10 = 0.60
# losing values: [1,2,3,4] → losses [4,3,2,1] → mean=2.5 median=2.5
# unconditional loss = mean(max(5-v,0) for v in TOY_VALUES)
#   = mean([4,3,2,1,0,0,0,0,0,0]) = 10/10 = 1.0


# ---------------------------------------------------------------------------
# 1. Probability of profit
# ---------------------------------------------------------------------------

class TestProbProfit:
    def test_exact_fraction(self):
        result = compute_probability_metrics(TOY_VALUES, PACK_COST)
        # 5.0 counts as profit (>=), so [5,6,7,8,9,10] = 6 out of 10
        assert result["prob_profit"] == pytest.approx(0.60)

    def test_all_profit(self):
        result = compute_probability_metrics([10.0, 20.0, 30.0], pack_cost=1.0)
        assert result["prob_profit"] == pytest.approx(1.0)

    def test_no_profit(self):
        result = compute_probability_metrics([1.0, 2.0, 3.0], pack_cost=100.0)
        assert result["prob_profit"] == pytest.approx(0.0)

    def test_n_runs_reported(self):
        result = compute_probability_metrics(TOY_VALUES, PACK_COST)
        assert result["n_runs"] == 10

    def test_empty_raises(self):
        with pytest.raises(ValueError):
            compute_probability_metrics([], PACK_COST)


# ---------------------------------------------------------------------------
# 2. Big-hit probabilities — fixed and dynamic
# ---------------------------------------------------------------------------

class TestBigHitProbabilities:
    def test_fixed_threshold_exact(self):
        # Values [8,9,10] are >= 8.0 → 3/10
        result = compute_probability_metrics(TOY_VALUES, PACK_COST, big_hit_threshold_fixed=8.0)
        assert result["prob_big_hit_fixed"] == pytest.approx(0.30)
        assert result["big_hit_threshold_fixed"] == pytest.approx(8.0)

    def test_no_fixed_threshold_returns_none(self):
        result = compute_probability_metrics(TOY_VALUES, PACK_COST)
        assert result["prob_big_hit_fixed"] is None
        assert result["big_hit_threshold_fixed"] is None

    def test_dynamic_cost_multiple(self):
        # 5× $5 = $25; none of TOY_VALUES reach 25 → 0
        result = compute_probability_metrics(
            TOY_VALUES, PACK_COST,
            big_hit_dynamic_mode="cost_multiple",
            big_hit_dynamic_param=5.0,
        )
        assert result["prob_big_hit_dynamic"] == pytest.approx(0.0)
        assert result["big_hit_threshold_dynamic"] == pytest.approx(25.0)
        assert result["big_hit_dynamic_param"] == pytest.approx(5.0)

    def test_dynamic_cost_multiple_partial(self):
        # 2× $5 = $10; only value=10 qualifies → 1/10
        result = compute_probability_metrics(
            TOY_VALUES, PACK_COST,
            big_hit_dynamic_mode="cost_multiple",
            big_hit_dynamic_param=2.0,
        )
        assert result["prob_big_hit_dynamic"] == pytest.approx(0.10)

    def test_dynamic_percentile_mode(self):
        # p90 of TOY_VALUES ≈ 9.1; values >= that: [10] → 1/10
        result = compute_probability_metrics(
            TOY_VALUES, PACK_COST,
            big_hit_dynamic_mode="percentile",
            big_hit_dynamic_param=90.0,
        )
        assert result["prob_big_hit_dynamic"] == pytest.approx(0.10, abs=0.15)
        assert result["big_hit_dynamic_mode"] == "percentile"

    def test_dynamic_cost_multiple_threshold_formula_exact(self):
        result = compute_probability_metrics(
            [0.1, 0.2, 0.3],
            pack_cost=13.99,
            big_hit_dynamic_mode="cost_multiple",
            big_hit_dynamic_param=5.0,
        )
        assert result["big_hit_threshold_dynamic"] == pytest.approx(69.95)

    def test_probabilities_remain_full_precision_in_backend_outputs(self):
        values = [0.0, 1.0, 2.0]
        result = compute_probability_metrics(
            values,
            pack_cost=1.0,
            big_hit_dynamic_mode="cost_multiple",
            big_hit_dynamic_param=1.0,
        )
        # 2 / 3 should not be rounded to a presentation value in backend output.
        assert result["prob_profit"] == pytest.approx(2.0 / 3.0)
        assert result["prob_big_hit_dynamic"] == pytest.approx(2.0 / 3.0)

    def test_unknown_mode_raises(self):
        with pytest.raises(ValueError, match="big_hit_dynamic_mode"):
            compute_probability_metrics(TOY_VALUES, PACK_COST, big_hit_dynamic_mode="magic")


# ---------------------------------------------------------------------------
# 3. Downside metrics — conditional vs unconditional
# ---------------------------------------------------------------------------

class TestDownsideMetrics:
    def test_expected_loss_given_loss(self):
        # Losing values: [1,2,3,4] → losses [4,3,2,1] → mean = 2.5
        result = compute_downside_metrics(TOY_VALUES, PACK_COST)
        assert result["expected_loss_given_loss"] == pytest.approx(2.5)

    def test_median_loss_given_loss(self):
        # Losses = [4,3,2,1] → median = 2.5
        result = compute_downside_metrics(TOY_VALUES, PACK_COST)
        assert result["median_loss_given_loss"] == pytest.approx(2.5)

    def test_expected_loss_unconditional(self):
        # max(5-v,0) for v in [1..10] = [4,3,2,1,0,0,0,0,0,0] → mean = 1.0
        result = compute_downside_metrics(TOY_VALUES, PACK_COST)
        assert result["expected_loss_unconditional"] == pytest.approx(1.0)

    def test_conditional_unconditional_not_equal(self):
        """Conditional and unconditional loss are distinct metrics."""
        result = compute_downside_metrics(TOY_VALUES, PACK_COST)
        assert result["expected_loss_given_loss"] != result["expected_loss_unconditional"]

    def test_no_losing_runs_returns_none(self):
        result = compute_downside_metrics([10.0, 20.0, 30.0], pack_cost=1.0)
        assert result["expected_loss_given_loss"] is None
        assert result["median_loss_given_loss"] is None
        assert result["n_losing_runs"] == 0

    def test_unconditional_still_zero_when_no_loss(self):
        result = compute_downside_metrics([10.0, 20.0], pack_cost=1.0)
        assert result["expected_loss_unconditional"] == pytest.approx(0.0)

    def test_n_losing_runs_counted(self):
        result = compute_downside_metrics(TOY_VALUES, PACK_COST)
        assert result["n_losing_runs"] == 4  # values [1,2,3,4]

    def test_tail_value_p05(self):
        result = compute_downside_metrics(TOY_VALUES, PACK_COST)
        # p05 of [1..10] ≈ 1.45
        assert result["tail_value_p05"] < PACK_COST

    def test_empty_raises(self):
        with pytest.raises(ValueError):
            compute_downside_metrics([], PACK_COST)


# ---------------------------------------------------------------------------
# 4. Coefficient of variation
# ---------------------------------------------------------------------------

class TestVolatilityMetrics:
    def test_cv_formula(self):
        values = [1.0, 2.0, 3.0, 4.0, 5.0]
        result = compute_volatility_metrics(values)
        expected_cv = np.std(values) / np.mean(values)
        assert result["coefficient_of_variation"] == pytest.approx(expected_cv)

    def test_cv_none_when_mean_zero(self):
        # All zeros → mean = 0
        result = compute_volatility_metrics([0.0, 0.0, 0.0])
        assert result["coefficient_of_variation"] is None

    def test_mean_and_median(self):
        values = [2.0, 4.0, 6.0]
        result = compute_volatility_metrics(values)
        assert result["mean"] == pytest.approx(4.0)
        assert result["median"] == pytest.approx(4.0)

    def test_percentile_keys_present(self):
        result = compute_volatility_metrics(TOY_VALUES)
        for key in ("p05", "p25", "p50", "p75", "p95", "p99"):
            assert key in result

    def test_percentile_ordering(self):
        result = compute_volatility_metrics(TOY_VALUES)
        assert result["p05"] <= result["p25"] <= result["p50"]
        assert result["p50"] <= result["p75"] <= result["p95"]
        assert result["p95"] <= result["p99"]

    def test_empty_raises(self):
        with pytest.raises(ValueError):
            compute_volatility_metrics([])


# ---------------------------------------------------------------------------
# 5. Chase dependency metrics
# ---------------------------------------------------------------------------

class TestChaseDependencyMetrics:
    def test_top1_share_dominant_card(self):
        # One card contributes 80% of EV
        contribs = {"chase_a": 8.0, "common_1": 0.5, "common_2": 0.5, "rare_1": 1.0}
        result = compute_chase_dependency_metrics(contribs)
        assert result["top1_ev_share"] == pytest.approx(8.0 / 10.0)

    def test_top3_share(self):
        contribs = {f"card_{i}": float(i + 1) for i in range(10)}  # 1..10
        total = sum(range(1, 11))  # 55
        result = compute_chase_dependency_metrics(contribs)
        # Top 3: [10, 9, 8] = 27
        assert result["top3_ev_share"] == pytest.approx(27.0 / total)

    def test_top5_share(self):
        contribs = {f"card_{i}": float(i + 1) for i in range(10)}
        total = 55.0
        result = compute_chase_dependency_metrics(contribs)
        # Top 5: [10,9,8,7,6] = 40
        assert result["top5_ev_share"] == pytest.approx(40.0 / total)

    def test_zero_total_ev_returns_none_shares(self):
        contribs = {"card_a": 0.0, "card_b": 0.0}
        result = compute_chase_dependency_metrics(contribs)
        assert result["top1_ev_share"] is None
        assert result["top3_ev_share"] is None
        assert result["top5_ev_share"] is None
        assert result["hhi_ev_concentration"] is None
        assert result["effective_chase_count"] is None

    def test_empty_contributions(self):
        result = compute_chase_dependency_metrics({})
        assert result["n_cards"] == 0
        assert result["cards_tracked"] == 0
        assert result["total_ev"] == pytest.approx(0.0)
        assert result["total_card_ev"] == pytest.approx(0.0)
        assert result["top1_ev_share"] is None

    def test_contract_aliases_match_legacy_chase_metrics(self):
        contribs = {"a": 5.0, "b": 3.0, "c": 2.0}
        result = compute_chase_dependency_metrics(contribs)

        assert result["cards_tracked"] == result["n_cards"]
        assert result["total_card_ev"] == pytest.approx(result["total_ev"])

    def test_ranked_cards_returned_when_requested(self):
        contribs = {"a": 5.0, "b": 3.0, "c": 2.0}
        result = compute_chase_dependency_metrics(contribs, return_ranked_cards=True)
        assert "ranked_cards" in result
        ranked = result["ranked_cards"]
        assert ranked[0][0] == "a"
        assert ranked[1][0] == "b"

    def test_no_ranked_cards_by_default(self):
        result = compute_chase_dependency_metrics({"a": 1.0})
        assert "ranked_cards" not in result

    def test_equal_split_uniform_distribution(self):
        contribs = {f"card_{i}": 1.0 for i in range(10)}
        result = compute_chase_dependency_metrics(contribs)
        assert result["top1_ev_share"] == pytest.approx(0.1)
        assert result["top3_ev_share"] == pytest.approx(0.3)
        assert result["top5_ev_share"] == pytest.approx(0.5)

    def test_negative_contributions_treated_as_zero(self):
        """Negative EV contributions must not inflate shares."""
        contribs = {"good_card": 10.0, "negative_card": -5.0}
        result = compute_chase_dependency_metrics(contribs)
        # total_ev capped at 10.0 (negative clamped to 0)
        assert result["top1_ev_share"] == pytest.approx(1.0)

    def test_hhi_and_effective_chase_count_computed_from_full_distribution(self):
        contribs = {"a": 4.0, "b": 3.0, "c": 2.0, "d": 1.0}
        result = compute_chase_dependency_metrics(contribs)
        # shares: [0.4, 0.3, 0.2, 0.1] => HHI = 0.16 + 0.09 + 0.04 + 0.01 = 0.30
        assert result["hhi_ev_concentration"] == pytest.approx(0.30)
        assert result["effective_chase_count"] == pytest.approx(1.0 / 0.30)

    def test_hhi_helper_and_effective_count_math(self):
        hhi = _compute_hhi_from_ev_contributions([4.0, 3.0, 2.0, 1.0])
        assert hhi == pytest.approx(0.30)
        assert _compute_effective_chase_count(hhi) == pytest.approx(1.0 / 0.30)


# ---------------------------------------------------------------------------
# 5b. EV Composition reconciliation
# ---------------------------------------------------------------------------

class TestEvCompositionMetrics:
    def test_basic_composition(self):
        """Hit EV, non-hit EV, and share are computed correctly."""
        from backend.calculations.evr.derived_metrics import compute_ev_composition_metrics
        
        result = compute_ev_composition_metrics(total_pack_ev=7.18, hit_ev=6.16)
        assert result["total_pack_ev"] == pytest.approx(7.18)
        assert result["hit_ev"] == pytest.approx(6.16)
        assert result["non_hit_ev"] == pytest.approx(1.02)
        assert result["hit_ev_share_of_pack_ev"] == pytest.approx(6.16 / 7.18)

    def test_all_hit_ev(self):
        """When all EV is from hits, non-hit is zero and share is 100%."""
        from backend.calculations.evr.derived_metrics import compute_ev_composition_metrics
        
        result = compute_ev_composition_metrics(total_pack_ev=10.0, hit_ev=10.0)
        assert result["non_hit_ev"] == pytest.approx(0.0)
        assert result["hit_ev_share_of_pack_ev"] == pytest.approx(1.0)

    def test_no_hit_ev(self):
        """When all EV is non-hit, share is 0%."""
        from backend.calculations.evr.derived_metrics import compute_ev_composition_metrics
        
        result = compute_ev_composition_metrics(total_pack_ev=10.0, hit_ev=0.0)
        assert result["non_hit_ev"] == pytest.approx(10.0)
        assert result["hit_ev_share_of_pack_ev"] == pytest.approx(0.0)

    def test_zero_total_ev_share_is_none(self):
        """When total pack EV is 0 or negative, share is None."""
        from backend.calculations.evr.derived_metrics import compute_ev_composition_metrics
        
        result = compute_ev_composition_metrics(total_pack_ev=0.0, hit_ev=0.0)
        assert result["hit_ev_share_of_pack_ev"] is None

    def test_negative_total_ev_share_is_none(self):
        """Share is None when total is negative (meaningless case)."""
        from backend.calculations.evr.derived_metrics import compute_ev_composition_metrics
        
        result = compute_ev_composition_metrics(total_pack_ev=-1.0, hit_ev=-0.5)
        assert result["hit_ev_share_of_pack_ev"] is None

    def test_hit_cards_count_included(self):
        """When provided, hit_cards_count is included in output."""
        from backend.calculations.evr.derived_metrics import compute_ev_composition_metrics
        
        result = compute_ev_composition_metrics(
            total_pack_ev=7.18, hit_ev=6.16, hit_cards_count=208
        )
        assert result["hit_cards_count"] == 208

    def test_hit_cards_count_omitted_when_not_provided(self):
        """hit_cards_count is not in output if not provided."""
        from backend.calculations.evr.derived_metrics import compute_ev_composition_metrics
        
        result = compute_ev_composition_metrics(total_pack_ev=7.18, hit_ev=6.16)
        assert "hit_cards_count" not in result

    def test_float_conversion(self):
        """Inputs are coerced to floats; outputs are floats."""
        from backend.calculations.evr.derived_metrics import compute_ev_composition_metrics
        
        result = compute_ev_composition_metrics(total_pack_ev=10, hit_ev=5)
        assert isinstance(result["total_pack_ev"], float)
        assert isinstance(result["hit_ev"], float)
        assert isinstance(result["non_hit_ev"], float)
        assert isinstance(result["hit_ev_share_of_pack_ev"], (float, type(None)))

    def test_realistic_scenario(self):
        """Test with realistic EV values."""
        from backend.calculations.evr.derived_metrics import compute_ev_composition_metrics
        
        # Set where total EV is $7.18, but only $6.16 from hits; bulk from non-hit
        result = compute_ev_composition_metrics(total_pack_ev=7.18, hit_ev=6.16, hit_cards_count=208)
        
        assert result["total_pack_ev"] == pytest.approx(7.18)
        assert result["hit_ev"] == pytest.approx(6.16)
        assert result["non_hit_ev"] == pytest.approx(1.02)
        assert result["hit_ev_share_of_pack_ev"] == pytest.approx(0.858, rel=0.01)
        assert result["hit_cards_count"] == 208


# ---------------------------------------------------------------------------
# 6. Session simulation metrics — deterministic toy pack
# ---------------------------------------------------------------------------

def _constant_pack(value: float):
    """Returns a callable that always produces *value*."""
    def fn() -> float:
        return value
    return fn


class TestSessionSimulationMetrics:
    def test_session_cost_is_pack_cost_times_n_packs(self):
        data = simulate_session(_constant_pack(3.0), n_packs=10, n_runs=5, pack_cost=4.0)
        assert data["session_cost"] == pytest.approx(40.0)

    def test_expected_box_value_constant_pack(self):
        # 36 packs × $3.00 = $108 per session
        data = simulate_session(_constant_pack(3.0), n_packs=36, n_runs=100, pack_cost=4.0)
        metrics = derive_session_metrics(data)
        assert metrics["expected_box_value"] == pytest.approx(108.0)

    def test_median_box_value_constant_pack(self):
        data = simulate_session(_constant_pack(3.0), n_packs=10, n_runs=50, pack_cost=4.0)
        metrics = derive_session_metrics(data)
        assert metrics["median_box_value"] == pytest.approx(30.0)

    def test_prob_box_profit_never_when_constant_loss(self):
        # Each pack = $2; box_cost = 36 × $4 = $144; box_value = 36 × $2 = $72 → never profit
        data = simulate_session(_constant_pack(2.0), n_packs=36, n_runs=100, pack_cost=4.0)
        metrics = derive_session_metrics(data)
        assert metrics["prob_box_profit"] == pytest.approx(0.0)

    def test_prob_box_profit_always_when_constant_profit(self):
        # pack_value > pack_cost always → always profit
        data = simulate_session(_constant_pack(10.0), n_packs=36, n_runs=100, pack_cost=4.0)
        metrics = derive_session_metrics(data)
        assert metrics["prob_box_profit"] == pytest.approx(1.0)

    def test_prob_no_chase_hit_uses_chase_fn(self):
        # Chase hit = value > 50; constant pack = 3 → never a hit
        def chase_fn(v: float) -> bool:
            return v > 50.0

        data = simulate_session(
            _constant_pack(3.0), n_packs=10, n_runs=50, pack_cost=4.0, chase_hit_fn=chase_fn
        )
        metrics = derive_session_metrics(data)
        assert metrics["prob_no_chase_hit_in_box"] == pytest.approx(1.0)

    def test_prob_no_chase_hit_none_when_no_chase_fn(self):
        data = simulate_session(_constant_pack(3.0), n_packs=10, n_runs=10, pack_cost=4.0)
        metrics = derive_session_metrics(data)
        assert metrics["prob_no_chase_hit_in_box"] is None

    def test_session_not_approximated_from_pack_averages(self):
        """Session values are independently drawn, not repeated from a summary."""
        counter = {"calls": 0}

        def counting_pack() -> float:
            counter["calls"] += 1
            return 3.0

        simulate_session(counting_pack, n_packs=36, n_runs=10, pack_cost=4.0)
        # Should have called the pack function 36 × 10 = 360 times
        assert counter["calls"] == 360

    def test_invalid_n_packs_raises(self):
        with pytest.raises(ValueError):
            simulate_session(_constant_pack(3.0), n_packs=0, n_runs=10, pack_cost=4.0)

    def test_invalid_n_runs_raises(self):
        with pytest.raises(ValueError):
            simulate_session(_constant_pack(3.0), n_packs=10, n_runs=0, pack_cost=4.0)


# ---------------------------------------------------------------------------
# 7. Packs-to-hit metrics — deterministic toy scenarios
# ---------------------------------------------------------------------------

class TestPacksToHitMetrics:
    def _make_alternating_pack(self) -> callable:
        """Returns hit every 5th pack (deterministic cycle)."""
        state = {"count": 0}

        def fn() -> float:
            state["count"] += 1
            return 100.0 if state["count"] % 5 == 0 else 1.0

        return fn

    def test_expected_packs_to_hit_cycle_of_5(self):
        # With every-5th-pack hit, expected = 5
        fn = self._make_alternating_pack()
        is_hit = lambda v: v >= 100.0
        hits = simulate_packs_until_hit(fn, is_hit, n_runs=200, verify_reachable=False)
        metrics = derive_packs_to_hit_metrics(hits)
        assert metrics["expected_packs_to_hit"] == pytest.approx(5.0, abs=1.5)

    def test_hit_on_first_pack(self):
        # Every pack is a hit → always 1 pack needed
        fn = _constant_pack(100.0)
        is_hit = lambda v: v >= 50.0
        hits = simulate_packs_until_hit(fn, is_hit, n_runs=100, verify_reachable=False)
        metrics = derive_packs_to_hit_metrics(hits)
        assert metrics["expected_packs_to_hit"] == pytest.approx(1.0)
        assert metrics["median_packs_to_hit"] == pytest.approx(1.0)

    def test_impossible_target_raises(self):
        fn = _constant_pack(1.0)  # Always returns 1.0
        is_hit = lambda v: v >= 999.0  # Unreachable
        with pytest.raises(ValueError, match="target may be impossible"):
            simulate_packs_until_hit(fn, is_hit, n_runs=10, verify_n_packs=50)

    def test_result_length_matches_n_runs(self):
        fn = _constant_pack(10.0)
        is_hit = lambda v: v >= 5.0
        hits = simulate_packs_until_hit(fn, is_hit, n_runs=77, verify_reachable=False)
        assert len(hits) == 77

    def test_metrics_keys_present(self):
        fn = _constant_pack(10.0)
        is_hit = lambda v: v >= 5.0
        hits = simulate_packs_until_hit(fn, is_hit, n_runs=50, verify_reachable=False)
        metrics = derive_packs_to_hit_metrics(hits)
        for key in (
            "n_runs",
            "expected_packs_to_hit",
            "median_packs_to_hit",
            "p25_packs_to_hit",
            "p75_packs_to_hit",
            "p90_packs_to_hit",
            "p95_packs_to_hit",
            "min_packs_to_hit",
            "max_packs_to_hit",
        ):
            assert key in metrics

    def test_empty_packs_to_hit_raises(self):
        with pytest.raises(ValueError):
            derive_packs_to_hit_metrics([])


# ---------------------------------------------------------------------------
# 8. PACK Score — bounded 0-100, correct direction
# ---------------------------------------------------------------------------

class TestPackScores:
    def _score_pair(self):
        return compute_pack_scores_for_set_records(
            [
                {
                    "prob_profit": 0.80,
                    "ev_to_cost_ratio": 1.30,
                    "expected_loss_when_losing": 1.00,
                    "median_loss_when_losing": 0.90,
                    "coefficient_of_variation": 0.80,
                    "top5_ev_share": 0.40,
                },
                {
                    "prob_profit": 0.20,
                    "ev_to_cost_ratio": 0.70,
                    "expected_loss_when_losing": 3.00,
                    "median_loss_when_losing": 2.50,
                    "coefficient_of_variation": 2.20,
                    "top5_ev_share": 0.90,
                },
            ]
        )

    def test_all_scores_bounded_0_to_100(self):
        scored = self._score_pair()
        for row in scored:
            assert 0.0 <= row["profit_score"] <= 100.0
            assert 0.0 <= row["safety_score"] <= 100.0
            assert 0.0 <= row["stability_score"] <= 100.0
            assert 0.0 <= row["pack_score"] <= 100.0

    def test_better_profit_inputs_improve_profit_score(self):
        better, worse = self._score_pair()
        assert better["profit_score"] > worse["profit_score"]

    def test_worse_downside_inputs_reduce_safety_score(self):
        better, worse = self._score_pair()
        assert better["safety_score"] > worse["safety_score"]

    def test_higher_cv_and_top5_reduce_stability_score(self):
        better, worse = self._score_pair()
        assert better["stability_score"] > worse["stability_score"]

    def test_pack_score_moves_with_components(self):
        better, worse = self._score_pair()
        assert better["pack_score"] > worse["pack_score"]

    def test_zero_range_falls_back_to_neutral(self):
        scored = compute_pack_scores_for_set_records(
            [
                {
                    "prob_profit": 0.5,
                    "ev_to_cost_ratio": 1.0,
                    "expected_loss_when_losing": 2.0,
                    "median_loss_when_losing": 2.0,
                    "coefficient_of_variation": 1.5,
                    "top5_ev_share": 0.6,
                },
                {
                    "prob_profit": 0.5,
                    "ev_to_cost_ratio": 1.0,
                    "expected_loss_when_losing": 2.0,
                    "median_loss_when_losing": 2.0,
                    "coefficient_of_variation": 1.5,
                    "top5_ev_share": 0.6,
                },
            ]
        )
        assert scored[0]["profit_score"] == pytest.approx(50.0)
        assert scored[0]["safety_score"] == pytest.approx(50.0)
        assert scored[0]["stability_score"] == pytest.approx(50.0)
        assert scored[0]["pack_score"] == pytest.approx(50.0)

    def test_missing_values_fall_back_to_neutral(self):
        scored = compute_pack_scores_for_set_records([{"prob_profit": 0.6}])[0]
        assert scored["profit_score"] == pytest.approx(50.0)
        assert scored["safety_score"] == pytest.approx(50.0)
        assert scored["stability_score"] == pytest.approx(50.0)
        assert scored["pack_score"] == pytest.approx(50.0)


# ---------------------------------------------------------------------------
# 9. Score component breakdown present and interpretable
# ---------------------------------------------------------------------------

class TestScoreBreakdown:
    def test_all_component_keys_present(self):
        result = compute_pack_scores_for_set_records(
            [
                {
                    "prob_profit": 0.65,
                    "ev_to_cost_ratio": 1.1,
                    "expected_loss_when_losing": 2.0,
                    "median_loss_when_losing": 1.8,
                    "coefficient_of_variation": 1.2,
                    "top5_ev_share": 0.4,
                }
            ]
        )[0]
        required_keys = {
            "pack_score",
            "score_version",
            "profit_score",
            "safety_score",
            "stability_score",
            "weights",
            "normalization",
        }
        assert required_keys.issubset(result.keys())

    def test_pack_score_weighted_from_components(self):
        result = compute_pack_scores_for_set_records(
            [
                {
                    "prob_profit": 0.65,
                    "ev_to_cost_ratio": 1.2,
                    "expected_loss_when_losing": 2.2,
                    "median_loss_when_losing": 2.0,
                    "coefficient_of_variation": 1.2,
                    "top5_ev_share": 0.4,
                },
                {
                    "prob_profit": 0.20,
                    "ev_to_cost_ratio": 0.8,
                    "expected_loss_when_losing": 3.4,
                    "median_loss_when_losing": 3.0,
                    "coefficient_of_variation": 2.0,
                    "top5_ev_share": 0.8,
                },
            ]
        )[0]
        expected = (
            0.45 * result["profit_score"]
            + 0.25 * result["safety_score"]
            + 0.20 * result["desirability_score"]
            + 0.10 * result["stability_score"]
        )
        assert result["pack_score"] == pytest.approx(expected, abs=0.01)


class TestPackScorePillarWeightingRegression:
    """Directional guardrails for final score behavior across pillar mixes."""

    @staticmethod
    def _pack_score_from_letters(
        profit: float,
        safety: float,
        stability: float,
        desirability: float = 50.0,
    ) -> float:
        return _weighted_average(
            {
                "profit_score": profit,
                "safety_score": safety,
                "desirability_score": desirability,
                "stability_score": stability,
            },
            _PACK_SCORE_V2_WEIGHTS_PCT,
        )

    def test_canonical_rip_weights_are_45_25_20_10(self):
        assert _PACK_SCORE_V2_WEIGHTS_PCT == {
            "profit_score": 45.0,
            "safety_score": 25.0,
            "desirability_score": 20.0,
            "stability_score": 10.0,
        }

    def test_sample_four_pillar_rip_score_calculation(self):
        score = self._pack_score_from_letters(
            profit=80.0,
            safety=60.0,
            desirability=90.0,
            stability=50.0,
        )
        assert score == pytest.approx(74.0)

    def test_b_b_f_does_not_collapse_to_bottom_tier_behavior(self):
        # B/B/F should remain middle-to-decent and not collapse solely on stability.
        score = self._pack_score_from_letters(profit=75.0, safety=75.0, stability=35.0)
        assert score >= 60.0

    def test_d_d_a_does_not_jump_to_strong_behavior(self):
        # D/D/A should stay capped; strong stability cannot fully rescue weak value pillars.
        score = self._pack_score_from_letters(profit=55.0, safety=55.0, stability=85.0)
        assert score <= 64.0

    def test_f_f_s_remains_weak(self):
        # Terrible profit/safety cannot be rescued by excellent stability.
        score = self._pack_score_from_letters(profit=35.0, safety=35.0, stability=95.0)
        assert score < 55.0

    def test_a_or_s_profit_with_mid_safety_and_f_stability_can_still_be_decent(self):
        # Low stability should flag risk/path quality, not completely bury strong value.
        score = self._pack_score_from_letters(profit=85.0, safety=70.0, stability=35.0)
        assert score >= 65.0


# ---------------------------------------------------------------------------
# 10. compute_all_derived_metrics integration path
# ---------------------------------------------------------------------------

class TestComputeAllDerivedMetrics:
    def test_runtime_v2_anchor_contract_updated_for_profit_and_stability(self):
        assert _RUNTIME_V2_ANCHORS["prob_profit"]["min"] == pytest.approx(0.0)
        assert _RUNTIME_V2_ANCHORS["prob_profit"]["max"] == pytest.approx(1.0)
        assert _RUNTIME_V2_ANCHORS["p95_value_to_cost_ratio"]["min"] == pytest.approx(0.25)
        assert _RUNTIME_V2_ANCHORS["p95_value_to_cost_ratio"]["max"] == pytest.approx(5.0)
        assert _RUNTIME_V2_ANCHORS["effective_chase_count"]["min"] == pytest.approx(1.0)
        assert _RUNTIME_V2_ANCHORS["effective_chase_count"]["max"] == pytest.approx(40.0)
        assert _RUNTIME_V2_ANCHORS["coefficient_of_variation"]["min"] == pytest.approx(0.25)
        assert _RUNTIME_V2_ANCHORS["coefficient_of_variation"]["max"] == pytest.approx(6.0)

    def test_pack_decision_metrics_present(self):
        result = compute_all_derived_metrics(TOY_VALUES, PACK_COST)
        assert "pack_decision_metrics" in result
        assert result["pack_decision_metrics"]["prob_profit"] == pytest.approx(0.60)

    def test_chase_metrics_present_when_supplied(self):
        contribs = {"chase": 8.0, "common": 2.0}
        result = compute_all_derived_metrics(TOY_VALUES, PACK_COST, card_ev_contributions=contribs)
        assert result["chase_dependency_metrics"] is not None
        assert "top1_ev_share" in result["chase_dependency_metrics"]

    def test_chase_metrics_none_when_not_supplied(self):
        result = compute_all_derived_metrics(TOY_VALUES, PACK_COST)
        assert result["chase_dependency_metrics"] is None

    def test_session_metrics_present_when_supplied(self):
        sess = simulate_session(_constant_pack(3.0), n_packs=10, n_runs=20, pack_cost=4.0)
        result = compute_all_derived_metrics(TOY_VALUES, PACK_COST, session_data=sess)
        assert result["session_metrics"] is not None
        assert "prob_box_profit" in result["session_metrics"]

    def test_session_metrics_none_when_not_supplied(self):
        result = compute_all_derived_metrics(TOY_VALUES, PACK_COST)
        assert result["session_metrics"] is None

    def test_packs_to_hit_present_when_supplied(self):
        result = compute_all_derived_metrics(
            TOY_VALUES, PACK_COST, packs_to_hit_data=[1, 2, 3, 4, 5]
        )
        assert result["packs_to_hit_metrics"] is not None

    def test_packs_to_hit_none_when_not_supplied(self):
        result = compute_all_derived_metrics(TOY_VALUES, PACK_COST)
        assert result["packs_to_hit_metrics"] is None

    def test_pack_score_always_present(self):
        result = compute_all_derived_metrics(TOY_VALUES, PACK_COST)
        assert "pack_score" in result
        assert result["pack_score"]["score_version"] == "rip_score_v2_desirability_45_25_20_10"

    def test_pack_score_runtime_v2_flags(self):
        result = compute_all_derived_metrics(TOY_VALUES, PACK_COST)
        score = result["pack_score"]
        assert score["normalization_mode"] == "fixed_anchor_runtime_v2_chase_weighted"
        assert score["pack_score_is_placeholder"] is False
        assert 0.0 <= score["pack_score"] <= 100.0

    def test_pack_score_raw_input_contract_uses_canonical_fields(self):
        result = compute_all_derived_metrics(TOY_VALUES, PACK_COST)
        raw = result["pack_score"]["raw_inputs"]
        assert set(raw.keys()) == {
            "prob_profit",
            "mean_value_to_cost_ratio",
            "median_value_to_cost_ratio",
            "p95_value_to_cost_ratio",
            "p99_value_to_cost_ratio",
            "expected_loss_when_losing",
            "median_loss_when_losing",
            "expected_loss_when_losing_ratio",
            "median_loss_when_losing_ratio",
            "p05_shortfall_to_cost",
            "coefficient_of_variation",
            "hhi_ev_concentration",
            "effective_chase_count",
            "desirability_score",
            "raw_desirability_score",
            "desirability_source_table",
            "desirability_source_metric",
            "desirability_source_summary_id",
            "desirability_scoring_version",
            "rip_desirability_source",
            "desirability_is_fallback",
            "desirability_fallback_reason",
        }

    def test_pack_score_uses_opening_desirability_when_supplied(self):
        result = compute_all_derived_metrics(
            TOY_VALUES,
            PACK_COST,
            set_desirability_metrics={
                "opening_desirability_score": 81.0,
                "collector_appeal_score": 90.0,
                "desirability_source_summary_id": "11111111-1111-1111-1111-111111111111",
                "desirability_source_table": "pokemon_set_opening_desirability_latest",
                "desirability_source_metric": "opening_desirability_score",
                "desirability_scoring_version": "rip_desirability_v1",
                "rip_desirability_source": "opening_desirability",
            },
        )
        score = result["pack_score"]
        assert score["desirability_score"] == pytest.approx(81.0)
        assert score["desirability_is_fallback"] is False
        assert score["desirability_source_metric"] == "opening_desirability_score"
        assert score["rip_desirability_source"] == "opening_desirability"

    def test_pack_score_uses_collector_appeal_fallback_when_opening_missing(self):
        result = compute_all_derived_metrics(
            TOY_VALUES,
            PACK_COST,
            set_desirability_metrics={
                "opening_desirability_score": None,
                "collector_appeal_score": 74.0,
                "desirability_source_metric": "collector_appeal_score",
                "desirability_is_fallback": True,
                "desirability_fallback_reason": "collector_appeal_fallback_missing_opening_desirability",
                "rip_desirability_source": "collector_appeal_fallback",
            },
        )
        score = result["pack_score"]
        assert score["desirability_score"] == pytest.approx(74.0)
        assert score["desirability_is_fallback"] is True
        assert score["desirability_fallback_reason"] == "collector_appeal_fallback_missing_opening_desirability"
        assert score["rip_desirability_source"] == "collector_appeal_fallback"

    def test_pack_score_still_accepts_legacy_set_hit_desirability_when_supplied(self):
        result = compute_all_derived_metrics(
            TOY_VALUES,
            PACK_COST,
            set_desirability_metrics={
                "weighted_average_hit_desirability_score": 90.0,
                "desirability_source_summary_id": "11111111-1111-1111-1111-111111111111",
                "aggregation_version": "pokemon_set_hit_desirability_v1",
            },
        )
        score = result["pack_score"]
        assert score["desirability_score"] == pytest.approx(90.0)
        assert score["desirability_is_fallback"] is False
        assert score["desirability_source_metric"] == "weighted_average_hit_desirability_score"

    def test_pack_score_uses_neutral_desirability_fallback_when_missing(self):
        result = compute_all_derived_metrics(TOY_VALUES, PACK_COST)
        score = result["pack_score"]
        assert score["desirability_score"] == pytest.approx(50.0)
        assert score["desirability_is_fallback"] is True
        assert score["desirability_fallback_reason"] == "missing_set_hit_desirability_score"
        assert score["rip_desirability_source"] == "missing"

    def test_mean_value_to_cost_ratio_is_mean_over_pack_cost(self):
        result = compute_all_derived_metrics(TOY_VALUES, PACK_COST)
        mean_val = result["pack_decision_metrics"]["mean"]
        assert result["pack_score"]["raw_inputs"]["mean_value_to_cost_ratio"] == pytest.approx(
            mean_val / PACK_COST
        )

    def test_median_value_to_cost_ratio_is_median_over_pack_cost(self):
        result = compute_all_derived_metrics(TOY_VALUES, PACK_COST)
        median_val = result["pack_decision_metrics"]["median"]
        assert result["pack_score"]["raw_inputs"]["median_value_to_cost_ratio"] == pytest.approx(
            median_val / PACK_COST
        )

    def test_cost_ratios_are_none_when_pack_cost_zero(self):
        result = compute_all_derived_metrics(TOY_VALUES, 0.0)
        assert result["pack_score"]["raw_inputs"]["mean_value_to_cost_ratio"] is None
        assert result["pack_score"]["raw_inputs"]["median_value_to_cost_ratio"] is None
        assert result["pack_score"]["raw_inputs"]["p95_value_to_cost_ratio"] is None
        assert result["pack_score"]["raw_inputs"]["p99_value_to_cost_ratio"] is None

    @patch("backend.calculations.evr.derived_metrics.compute_pack_decision_metrics")
    def test_cost_ratios_respect_missing_mean_or_median(self, mock_compute_pack_decision_metrics):
        mock_compute_pack_decision_metrics.return_value = {
            "pack_cost": PACK_COST,
            "n_runs": 10,
            "prob_profit": 0.6,
            "prob_big_hit_fixed": None,
            "big_hit_threshold_fixed": None,
            "prob_big_hit_dynamic": 0.0,
            "big_hit_threshold_dynamic": 25.0,
            "big_hit_dynamic_mode": "cost_multiple",
            "big_hit_dynamic_param": 5.0,
            "n_losing_runs": 4,
            "expected_loss_given_loss": 2.5,
            "median_loss_given_loss": 2.5,
            "expected_loss_unconditional": 1.0,
            "tail_value_p05": 1.45,
            "mean": None,
            "median": None,
            "std_dev": 2.5,
            "coefficient_of_variation": 0.4,
            "p05": 1.45,
            "p25": 3.25,
            "p50": 5.5,
            "p75": 7.75,
            "p95": 9.55,
            "p99": 9.91,
        }

        result = compute_all_derived_metrics(TOY_VALUES, PACK_COST)
        assert result["pack_score"]["raw_inputs"]["mean_value_to_cost_ratio"] is None
        assert result["pack_score"]["raw_inputs"]["median_value_to_cost_ratio"] is None
        assert result["pack_score"]["raw_inputs"]["p95_value_to_cost_ratio"] == pytest.approx(
            9.55 / PACK_COST
        )

    def test_p95_value_to_cost_ratio_is_p95_over_pack_cost(self):
        result = compute_all_derived_metrics(TOY_VALUES, PACK_COST)
        p95_val = result["pack_decision_metrics"]["p95"]
        assert result["pack_score"]["raw_inputs"]["p95_value_to_cost_ratio"] == pytest.approx(
            p95_val / PACK_COST
        )

    def test_p99_value_to_cost_ratio_is_p99_over_pack_cost(self):
        result = compute_all_derived_metrics(TOY_VALUES, PACK_COST)
        p99_val = result["pack_decision_metrics"]["p99"]
        assert result["pack_score"]["raw_inputs"]["p99_value_to_cost_ratio"] == pytest.approx(
            p99_val / PACK_COST
        )

    @patch("backend.calculations.evr.derived_metrics.compute_pack_decision_metrics")
    def test_profit_score_changes_when_p95_changes_all_else_equal(self, mock_compute_pack_decision_metrics):
        base_metrics = {
            "pack_cost": PACK_COST,
            "n_runs": 10,
            "prob_profit": 0.6,
            "prob_big_hit_fixed": None,
            "big_hit_threshold_fixed": None,
            "prob_big_hit_dynamic": 0.0,
            "big_hit_threshold_dynamic": 25.0,
            "big_hit_dynamic_mode": "cost_multiple",
            "big_hit_dynamic_param": 5.0,
            "n_losing_runs": 4,
            "expected_loss_given_loss": 2.5,
            "median_loss_given_loss": 2.5,
            "expected_loss_unconditional": 1.0,
            "tail_value_p05": 1.45,
            "mean": 5.5,
            "median": 5.5,
            "std_dev": 2.5,
            "coefficient_of_variation": 0.4,
            "p05": 1.45,
            "p25": 3.25,
            "p50": 5.5,
            "p75": 7.75,
            "p95": 9.55,
            "p99": 9.91,
        }
        low_p95_metrics = dict(base_metrics)
        low_p95_metrics["p95"] = 3.0
        high_p95_metrics = dict(base_metrics)
        high_p95_metrics["p95"] = 20.0

        mock_compute_pack_decision_metrics.return_value = low_p95_metrics
        low_p95_score = compute_all_derived_metrics(TOY_VALUES, PACK_COST)["pack_score"]

        mock_compute_pack_decision_metrics.return_value = high_p95_metrics
        high_p95_score = compute_all_derived_metrics(TOY_VALUES, PACK_COST)["pack_score"]

        assert high_p95_score["profit_score"] > low_p95_score["profit_score"]

    def test_safety_shortfall_to_cost_formula(self):
        result = compute_all_derived_metrics(TOY_VALUES, PACK_COST)
        p05 = result["pack_decision_metrics"]["tail_value_p05"]
        expected = max(PACK_COST - p05, 0.0) / PACK_COST
        assert result["pack_score"]["raw_inputs"]["p05_shortfall_to_cost"] == pytest.approx(expected)

    def test_safety_ratio_formulas(self):
        result = compute_all_derived_metrics(TOY_VALUES, PACK_COST)
        raw = result["pack_score"]["raw_inputs"]
        assert raw["expected_loss_when_losing_ratio"] == pytest.approx(
            raw["expected_loss_when_losing"] / PACK_COST
        )
        assert raw["median_loss_when_losing_ratio"] == pytest.approx(
            raw["median_loss_when_losing"] / PACK_COST
        )

    def test_pack_score_uses_chase_dependency_when_available(self):
        contribs = {"big_chase": 9.0, "others": 1.0}
        result_with = compute_all_derived_metrics(
            TOY_VALUES, PACK_COST, card_ev_contributions=contribs
        )
        result_without = compute_all_derived_metrics(TOY_VALUES, PACK_COST)
        assert result_with["pack_score"]["raw_inputs"]["effective_chase_count"] is not None
        assert result_without["pack_score"]["raw_inputs"]["effective_chase_count"] is None

    def test_pack_score_breakdown_includes_hhi_and_effective_count(self):
        contribs = {"card_a": 6.0, "card_b": 3.0, "card_c": 1.0}
        result = compute_all_derived_metrics(
            TOY_VALUES,
            PACK_COST,
            card_ev_contributions=contribs,
        )
        hhi = result["chase_dependency_metrics"]["hhi_ev_concentration"]
        eff = result["chase_dependency_metrics"]["effective_chase_count"]
        assert result["pack_score"]["raw_inputs"]["hhi_ev_concentration"] == pytest.approx(hhi)
        assert result["pack_score"]["raw_inputs"]["effective_chase_count"] == pytest.approx(eff)

    def test_stability_component_not_placeholder_when_real_data_supplied(self):
        contribs = {"card_a": 6.0, "card_b": 3.0, "card_c": 1.0}
        result = compute_all_derived_metrics(
            TOY_VALUES,
            PACK_COST,
            card_ev_contributions=contribs,
        )
        assert result["pack_score"]["pack_score_is_placeholder"] is False
        assert 0.0 <= result["pack_score"]["stability_score"] <= 100.0

    def test_component_and_final_weights_sum_to_100(self):
        score = compute_all_derived_metrics(TOY_VALUES, PACK_COST)["pack_score"]
        assert sum(score["weights_pct"]["profit_score"].values()) == pytest.approx(100.0)
        assert sum(score["weights_pct"]["safety_score"].values()) == pytest.approx(100.0)
        assert sum(score["weights_pct"]["stability_score"].values()) == pytest.approx(100.0)
        assert sum(score["weights_pct"]["pack_score"].values()) == pytest.approx(100.0)
        assert score["weights_normalized"]["pack_score"] == {
            "profit_score": pytest.approx(0.45),
            "safety_score": pytest.approx(0.25),
            "desirability_score": pytest.approx(0.20),
            "stability_score": pytest.approx(0.10),
        }

    def test_component_weighted_averages_match_reported_scores(self):
        score = compute_all_derived_metrics(
            TOY_VALUES,
            PACK_COST,
            card_ev_contributions={"a": 4.0, "b": 3.0, "c": 2.0, "d": 1.0},
        )["pack_score"]
        n = score["normalized_inputs"]
        weights = score["weights_pct"]

        expected_profit = sum(
            float(weight) * n[metric]["score"]
            for metric, weight in weights["profit_score"].items()
        ) / 100.0
        expected_safety = sum(
            float(weight) * n[metric]["score"]
            for metric, weight in weights["safety_score"].items()
        ) / 100.0
        expected_stability = sum(
            float(weight) * n[metric]["score"]
            for metric, weight in weights["stability_score"].items()
        ) / 100.0
        expected_pack = (
            float(weights["pack_score"]["profit_score"]) * expected_profit
            + float(weights["pack_score"]["safety_score"]) * expected_safety
            + float(weights["pack_score"]["desirability_score"]) * score["desirability_score"]
            + float(weights["pack_score"]["stability_score"]) * expected_stability
        ) / 100.0

        assert score["profit_score"] == pytest.approx(expected_profit, abs=0.01)
        assert score["safety_score"] == pytest.approx(expected_safety, abs=0.01)
        assert score["stability_score"] == pytest.approx(expected_stability, abs=0.01)
        assert score["pack_score"] == pytest.approx(expected_pack, abs=0.01)

    def test_runtime_normalized_inputs_expose_updated_anchor_bounds(self):
        score = compute_all_derived_metrics(
            TOY_VALUES,
            PACK_COST,
            card_ev_contributions={f"card_{i}": 1.0 for i in range(30)},
        )["pack_score"]
        normalized = score["normalized_inputs"]

        assert normalized["prob_profit"]["min"] == pytest.approx(0.0)
        assert normalized["prob_profit"]["max"] == pytest.approx(1.0)

        assert normalized["effective_chase_count"]["min"] == pytest.approx(1.0)
        assert normalized["effective_chase_count"]["max"] == pytest.approx(40.0)

        assert normalized["coefficient_of_variation"]["min"] == pytest.approx(0.25)
        assert normalized["coefficient_of_variation"]["max"] == pytest.approx(6.0)

        assert normalized["p95_value_to_cost_ratio"]["min"] == pytest.approx(0.25)
        assert normalized["p95_value_to_cost_ratio"]["max"] == pytest.approx(5.0)

    def test_fixed_anchor_normalization_clamps_extreme_values(self):
        # higher-is-better clamps below min to 0 and above max to 100
        assert _normalize_fixed_anchor_0_100(
            -10.0,
            min_anchor=0.0,
            max_anchor=1.0,
            direction="higher_is_better",
        ) == pytest.approx(0.0)
        assert _normalize_fixed_anchor_0_100(
            10.0,
            min_anchor=0.0,
            max_anchor=1.0,
            direction="higher_is_better",
        ) == pytest.approx(100.0)

        # lower-is-better clamps below min to 100 and above max to 0
        assert _normalize_fixed_anchor_0_100(
            -1.0,
            min_anchor=0.25,
            max_anchor=10.0,
            direction="lower_is_better",
        ) == pytest.approx(100.0)
        assert _normalize_fixed_anchor_0_100(
            25.0,
            min_anchor=0.25,
            max_anchor=10.0,
            direction="lower_is_better",
        ) == pytest.approx(0.0)

    def test_inverse_normalization_direction_for_safety_and_cv(self):
        better = compute_all_derived_metrics(TOY_VALUES, PACK_COST)["pack_score"]
        worse_values = [0.0, 0.0, 0.0, 0.0, 10.0, 10.0, 10.0, 10.0]
        worse = compute_all_derived_metrics(worse_values, PACK_COST)["pack_score"]
        assert better["safety_score"] > worse["safety_score"]
        assert better["stability_score"] > worse["stability_score"]

    def test_pack_cost_non_positive_still_returns_bounded_runtime_scores(self):
        score = compute_all_derived_metrics(TOY_VALUES, 0.0)["pack_score"]
        assert score["pack_score_is_placeholder"] is False
        for key in ("profit_score", "safety_score", "stability_score", "pack_score"):
            assert 0.0 <= score[key] <= 100.0

    def test_degenerate_anchor_ranges_fail_loudly(self):
        with pytest.raises(ValueError):
            _normalize_fixed_anchor_0_100(
                0.3,
                min_anchor=1.0,
                max_anchor=1.0,
                direction="higher_is_better",
            )

    def test_ev_composition_present_when_supplied(self):
        result = compute_all_derived_metrics(
            TOY_VALUES, PACK_COST, total_pack_ev=10.0, hit_ev=8.0
        )
        assert result["ev_composition_metrics"] is not None
        assert result["ev_composition_metrics"]["total_pack_ev"] == pytest.approx(10.0)
        assert result["ev_composition_metrics"]["hit_ev"] == pytest.approx(8.0)
        assert result["ev_composition_metrics"]["non_hit_ev"] == pytest.approx(2.0)

    def test_ev_composition_none_when_not_supplied(self):
        result = compute_all_derived_metrics(TOY_VALUES, PACK_COST)
        assert result["ev_composition_metrics"] is None

    def test_ev_composition_none_when_only_total_supplied(self):
        """Both total_pack_ev AND hit_ev must be provided."""
        result = compute_all_derived_metrics(TOY_VALUES, PACK_COST, total_pack_ev=10.0)
        assert result["ev_composition_metrics"] is None

    def test_ev_composition_hit_cards_count_included(self):
        result = compute_all_derived_metrics(
            TOY_VALUES, PACK_COST, 
            total_pack_ev=7.18, hit_ev=6.16, hit_cards_count=208
        )
        assert result["ev_composition_metrics"]["hit_cards_count"] == 208

    def test_hit_and_set_value_metrics_present_when_supplied(self):
        result = compute_all_derived_metrics(
            TOY_VALUES,
            PACK_COST,
            hit_value_metrics={
                "average_hit_value": 40.0,
                "hit_ev_per_pack": 12.0,
                "hit_pull_rate": 0.3,
                "hit_cards_pulled": 3,
            },
            set_value_metrics={
                "simulated_set_value": 123.45,
                "simulated_set_value_card_count": 2,
            },
        )

        assert result["hit_value_metrics"]["average_hit_value"] == pytest.approx(40.0)
        assert result["hit_value_metrics"]["hit_ev_per_pack"] == pytest.approx(12.0)
        assert result["hit_value_metrics"]["hit_pull_rate"] == pytest.approx(0.3)
        assert result["hit_value_metrics"]["hit_cards_pulled"] == 3
        assert result["set_value_metrics"]["simulated_set_value"] == pytest.approx(123.45)
        assert result["set_value_metrics"]["simulated_set_value_card_count"] == 2


# ---------------------------------------------------------------------------
# 11. PackSimulationSummary dataclass and builder
# ---------------------------------------------------------------------------

class TestPackSimulationSummary:
    def _build_summary(self) -> PackSimulationSummary:
        all_metrics = compute_all_derived_metrics(
            TOY_VALUES,
            PACK_COST,
            card_ev_contributions={"chase": 7.0, "common": 3.0},
        )
        return build_pack_simulation_summary(
            set_id="test_set_001",
            pack_cost=PACK_COST,
            simulation_version="v2",
            computed_at="2026-04-16T00:00:00Z",
            all_metrics=all_metrics,
        )

    def test_set_id_stored(self):
        s = self._build_summary()
        assert s.set_id == "test_set_001"

    def test_pack_cost_stored(self):
        s = self._build_summary()
        assert s.pack_cost == pytest.approx(PACK_COST)

    def test_prob_profit_stored(self):
        s = self._build_summary()
        assert s.prob_profit == pytest.approx(0.60)

    def test_score_version_stored(self):
        s = self._build_summary()
        assert s.score_version == "rip_score_v2_desirability_45_25_20_10"

    def test_p95_fields_stored(self):
        s = self._build_summary()
        assert s.p95_value == pytest.approx(9.55)
        assert s.p95_value_to_cost_ratio == pytest.approx(9.55 / PACK_COST)

    def test_pack_score_stored_and_bounded(self):
        s = self._build_summary()
        assert s.pack_score is not None
        assert 0.0 <= s.pack_score <= 100.0

    def test_chase_shares_stored(self):
        s = self._build_summary()
        # top1 = 7/10 = 0.70
        assert s.top1_ev_share == pytest.approx(0.70)

    def test_optional_fields_none_without_session(self):
        s = self._build_summary()
        assert s.prob_box_profit is None
        assert s.expected_box_value is None
        assert s.expected_packs_to_hit is None

    def test_simulation_version_stored(self):
        s = self._build_summary()
        assert s.simulation_version == "v2"

    def test_computed_at_stored(self):
        s = self._build_summary()
        assert s.computed_at == "2026-04-16T00:00:00Z"
