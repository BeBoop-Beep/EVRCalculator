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
8.  inDex Score — bounded 0-100, correct direction
9.  score component breakdown present and interpretable
10. compute_all_derived_metrics integration path
11. PackSimulationSummary dataclass construction
"""

from __future__ import annotations

import math
from typing import List, Optional

import numpy as np
import pytest

from backend.calculations.evr.derived_metrics import (
    PackSimulationSummary,
    build_pack_simulation_summary,
    compute_all_derived_metrics,
    compute_chase_dependency_metrics,
    compute_downside_metrics,
    compute_index_score_v1,
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

    def test_empty_contributions(self):
        result = compute_chase_dependency_metrics({})
        assert result["n_cards"] == 0
        assert result["total_ev"] == pytest.approx(0.0)
        assert result["top1_ev_share"] is None

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
# 8. inDex Score — bounded 0-100, correct direction
# ---------------------------------------------------------------------------

class TestIndexScoreV1:
    def test_score_bounded_0_to_100(self):
        score = compute_index_score_v1(
            prob_profit=0.7, coefficient_of_variation=1.2, top5_ev_share=0.5
        )
        assert 0.0 <= score["ind_ex_score_v1"] <= 100.0

    def test_perfect_inputs_approach_100(self):
        score = compute_index_score_v1(
            prob_profit=1.0, coefficient_of_variation=0.0, top5_ev_share=0.0
        )
        assert score["ind_ex_score_v1"] == pytest.approx(100.0)

    def test_worst_inputs_approach_0(self):
        # prob_profit=0, extreme CV, top5=100%
        score = compute_index_score_v1(
            prob_profit=0.0, coefficient_of_variation=100.0, top5_ev_share=1.0
        )
        assert score["ind_ex_score_v1"] == pytest.approx(0.0)

    def test_higher_prob_profit_increases_score(self):
        low = compute_index_score_v1(prob_profit=0.1, coefficient_of_variation=1.0, top5_ev_share=0.5)
        high = compute_index_score_v1(prob_profit=0.9, coefficient_of_variation=1.0, top5_ev_share=0.5)
        assert high["ind_ex_score_v1"] > low["ind_ex_score_v1"]

    def test_lower_cv_increases_score(self):
        volatile = compute_index_score_v1(prob_profit=0.5, coefficient_of_variation=4.0, top5_ev_share=0.5)
        stable = compute_index_score_v1(prob_profit=0.5, coefficient_of_variation=0.5, top5_ev_share=0.5)
        assert stable["ind_ex_score_v1"] > volatile["ind_ex_score_v1"]

    def test_lower_chase_dependency_increases_score(self):
        concentrated = compute_index_score_v1(prob_profit=0.5, coefficient_of_variation=1.0, top5_ev_share=0.9)
        diverse = compute_index_score_v1(prob_profit=0.5, coefficient_of_variation=1.0, top5_ev_share=0.1)
        assert diverse["ind_ex_score_v1"] > concentrated["ind_ex_score_v1"]

    def test_weights_must_sum_to_1(self):
        with pytest.raises(ValueError, match="Weights must sum to 1.0"):
            compute_index_score_v1(
                prob_profit=0.5, coefficient_of_variation=1.0, top5_ev_share=0.5,
                weights=(0.5, 0.5, 0.5),  # sums to 1.5
            )

    def test_none_cv_falls_back_to_neutral(self):
        # None CV → stability = 0.5 (documented neutral fallback)
        score = compute_index_score_v1(prob_profit=0.5, coefficient_of_variation=None, top5_ev_share=0.5)
        assert score["ind_ex_score_v1"] is not None
        assert score["cv_used"] is None

    def test_none_top5_falls_back_to_neutral(self):
        score = compute_index_score_v1(prob_profit=0.5, coefficient_of_variation=1.0, top5_ev_share=None)
        assert score["ind_ex_score_v1"] is not None
        assert score["top5_ev_share_used"] is None

    def test_score_version_is_v1(self):
        score = compute_index_score_v1(prob_profit=0.5, coefficient_of_variation=1.0, top5_ev_share=0.5)
        assert score["score_version"] == "v1"

    def test_extreme_cv_clamped_not_unbounded(self):
        # Very high CV must not blow up; stability_component should be 0
        score_high_cv = compute_index_score_v1(prob_profit=0.5, coefficient_of_variation=1000.0, top5_ev_share=0.5)
        score_mod_cv = compute_index_score_v1(prob_profit=0.5, coefficient_of_variation=5.0, top5_ev_share=0.5)
        # Both should have the same stability (0) once CV >= CV_MAX
        assert score_high_cv["stability_component"] == pytest.approx(0.0)
        assert score_mod_cv["stability_component"] == pytest.approx(0.0)


# ---------------------------------------------------------------------------
# 9. Score component breakdown present and interpretable
# ---------------------------------------------------------------------------

class TestScoreBreakdown:
    def test_all_component_keys_present(self):
        result = compute_index_score_v1(
            prob_profit=0.65, coefficient_of_variation=1.2, top5_ev_share=0.4
        )
        required_keys = {
            "ind_ex_score_v1",
            "score_version",
            "score_raw",
            "weights",
            "prob_profit_component",
            "stability_component",
            "cv_used",
            "cv_max",
            "diversification_component",
            "top5_ev_share_used",
        }
        assert required_keys.issubset(result.keys())

    def test_components_sum_to_score_raw(self):
        result = compute_index_score_v1(
            prob_profit=0.65, coefficient_of_variation=1.2, top5_ev_share=0.4
        )
        w1, w2, w3 = result["weights"]
        expected_raw = (
            w1 * result["prob_profit_component"]
            + w2 * result["stability_component"]
            + w3 * result["diversification_component"]
        )
        assert result["score_raw"] == pytest.approx(expected_raw, abs=1e-9)

    def test_score_raw_scales_to_100(self):
        result = compute_index_score_v1(
            prob_profit=0.65, coefficient_of_variation=1.2, top5_ev_share=0.4
        )
        assert result["ind_ex_score_v1"] == pytest.approx(100.0 * result["score_raw"], abs=0.005)

    def test_custom_weights_respected(self):
        weights = (0.50, 0.25, 0.25)
        result = compute_index_score_v1(
            prob_profit=0.8, coefficient_of_variation=0.5, top5_ev_share=0.3,
            weights=weights,
        )
        assert result["weights"] == weights


# ---------------------------------------------------------------------------
# 10. compute_all_derived_metrics integration path
# ---------------------------------------------------------------------------

class TestComputeAllDerivedMetrics:
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

    def test_index_score_always_present(self):
        result = compute_all_derived_metrics(TOY_VALUES, PACK_COST)
        assert "index_score" in result
        assert result["index_score"]["score_version"] == "v1"

    def test_index_score_uses_chase_dependency_when_available(self):
        contribs = {"big_chase": 9.0, "others": 1.0}
        result_with = compute_all_derived_metrics(
            TOY_VALUES, PACK_COST, card_ev_contributions=contribs
        )
        result_without = compute_all_derived_metrics(TOY_VALUES, PACK_COST)
        # With high chase dependency, diversification should be lower → different score
        assert (
            result_with["index_score"]["ind_ex_score_v1"]
            != result_without["index_score"]["ind_ex_score_v1"]
        )

    def test_index_score_uses_actual_top5_share_when_contributions_present(self):
        contribs = {"card_a": 6.0, "card_b": 3.0, "card_c": 1.0}
        result = compute_all_derived_metrics(
            TOY_VALUES,
            PACK_COST,
            card_ev_contributions=contribs,
        )
        top5 = result["chase_dependency_metrics"]["top5_ev_share"]
        assert top5 == pytest.approx(1.0)
        assert result["index_score"]["top5_ev_share_used"] == pytest.approx(top5)

    def test_diversification_component_not_neutral_when_real_data_supplied(self):
        contribs = {"card_a": 6.0, "card_b": 3.0, "card_c": 1.0}
        result = compute_all_derived_metrics(
            TOY_VALUES,
            PACK_COST,
            card_ev_contributions=contribs,
        )
        # Neutral fallback is 0.5 only when top5 share is unavailable.
        assert result["index_score"]["diversification_component"] != pytest.approx(0.5)

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
        assert s.score_version == "v1"

    def test_ind_ex_score_v1_stored_and_bounded(self):
        s = self._build_summary()
        assert s.ind_ex_score_v1 is not None
        assert 0.0 <= s.ind_ex_score_v1 <= 100.0

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
