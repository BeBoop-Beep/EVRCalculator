import math

import numpy as np
import pytest

from backend.calculations.evr.budget_normalized_product_ranking import (
    BUDGET_TYPE_FULL_MARKET,
    CANONICAL_BUDGET_BANDS,
    FULL_MARKET_ROUNDING_INCREMENT,
    rank_budget_cohort,
    resolve_full_market_budget,
    whole_unit_allocation,
)


# --- whole_unit_allocation ---------------------------------------------------

def test_arbitrary_positive_budget_is_supported_without_a_predefined_band():
    # $180 is not one of CANONICAL_BUDGET_BANDS -- the engine must not be
    # hard-wired exclusively to the predefined bands.
    result = whole_unit_allocation(180, 42.5)
    assert result["eligible"] is True
    assert result["quantity"] == 4
    assert result["actualCommittedCapital"] == pytest.approx(170.0)
    assert result["unusedCapital"] == pytest.approx(10.0)
    assert result["unusedCapitalPercent"] == pytest.approx(10.0 / 180)


@pytest.mark.parametrize("budget", CANONICAL_BUDGET_BANDS)
def test_predefined_canonical_bands_all_resolve(budget):
    result = whole_unit_allocation(budget, 25.0)
    assert result["quantity"] == int(budget // 25)


def test_whole_unit_enforcement_never_returns_a_fractional_quantity():
    result = whole_unit_allocation(100, 30)
    assert result["quantity"] == 3
    assert isinstance(result["quantity"], int)
    # 3 whole units at $30, not 3.33
    assert result["actualCommittedCapital"] == pytest.approx(90.0)


def test_insufficient_budget_excludes_the_product_rather_than_buying_zero_as_if_eligible():
    result = whole_unit_allocation(20, 25)
    assert result["eligible"] is False
    assert result["quantity"] == 0
    assert result["actualCommittedCapital"] == 0.0
    assert result["unusedCapital"] == 20.0


def test_unused_capital_is_explicit_and_never_silently_treated_as_spent():
    result = whole_unit_allocation(100, 33)
    assert result["quantity"] == 3
    assert result["actualCommittedCapital"] == pytest.approx(99.0)
    assert result["unusedCapital"] == pytest.approx(1.0)
    assert result["unusedCapitalPercent"] == pytest.approx(0.01)


def test_allocation_rejects_nonpositive_inputs():
    with pytest.raises(ValueError):
        whole_unit_allocation(0, 10)
    with pytest.raises(ValueError):
        whole_unit_allocation(10, 0)


def test_allocation_is_deterministic():
    a = whole_unit_allocation(257.0, 41.5)
    b = whole_unit_allocation(257.0, 41.5)
    assert a == b


# --- resolve_full_market_budget ----------------------------------------------

def test_full_market_resolves_from_the_max_eligible_price_not_a_hardcoded_value():
    result = resolve_full_market_budget([5.65, 208.44, 1339.19])
    assert result["maxEligibleSkuPrice"] == 1339.19
    assert result["budget"] == 1350.0  # ceil(1339.19 / 50) * 50
    assert result["roundingIncrement"] == FULL_MARKET_ROUNDING_INCREMENT


def test_full_market_rounding_rule_admits_every_eligible_sku_by_construction():
    prices = [5.0, 91.0, 499.5, 500.0, 733.21]
    result = resolve_full_market_budget(prices)
    for price in prices:
        assert result["budget"] >= price  # every SKU can buy >=1 whole unit


def test_full_market_is_stable_within_one_rounding_bucket():
    # A max price moving from 1301 to 1340 does not cross the 1300/1350
    # boundary -- the anchor must not change.
    a = resolve_full_market_budget([1301.0])
    b = resolve_full_market_budget([1340.0])
    assert a["budget"] == b["budget"] == 1350.0


def test_full_market_changes_deterministically_when_crossing_a_rounding_boundary():
    below = resolve_full_market_budget([1349.0])
    above = resolve_full_market_budget([1351.0])
    assert below["budget"] == 1350.0
    assert above["budget"] == 1400.0
    assert below["budget"] != above["budget"]


def test_full_market_rejects_an_empty_or_all_nonpositive_price_list():
    with pytest.raises(ValueError):
        resolve_full_market_budget([])
    with pytest.raises(ValueError):
        resolve_full_market_budget([0, -5, None])


def test_a_price_exactly_on_a_rounding_boundary_still_admits_itself():
    result = resolve_full_market_budget([1350.0])
    assert result["budget"] >= 1350.0


# --- rank_budget_cohort -------------------------------------------------------

def _strategy(pid, overall, financial=50.0, capital=100.0, target=100.0, recover=None):
    return {
        "sealedProductId": pid,
        "overallRipV10Score": overall,
        "financialRipV4Score": financial,
        "actualCommittedCapital": capital,
        "targetBudget": target,
        "chanceToRecoverCost": recover,
    }


def test_rank_range_is_contiguous_one_to_cohort_size():
    strategies = [_strategy("a", 80), _strategy("b", 90), _strategy("c", 70)]
    ranked = rank_budget_cohort(strategies)
    assert [r["budgetRank"] for r in ranked] == [1, 2, 3]
    assert all(r["budgetCohortSize"] == 3 for r in ranked)


def test_cohort_and_tier_consistency_every_row_shares_one_cohort_and_a_tier_from_its_own_score():
    from backend.desirability.composite import assign_composite_tier

    strategies = [_strategy("a", 95), _strategy("b", 40)]
    ranked = rank_budget_cohort(strategies)
    for row in ranked:
        assert row["budgetTier"] == assign_composite_tier(row["overallRipV10Score"])
    assert len({r["budgetCohortSize"] for r in ranked}) == 1


def test_unrankable_strategies_never_receive_a_fabricated_rank_and_shrink_the_cohort():
    strategies = [_strategy("a", 80), _strategy("b", None), _strategy("c", 60)]
    ranked = rank_budget_cohort(strategies)
    assert {r["sealedProductId"] for r in ranked} == {"a", "c"}
    assert all(r["budgetCohortSize"] == 2 for r in ranked)


def test_deterministic_tie_break_uses_financial_rip_then_sealed_product_id():
    strategies = [
        _strategy("z", 80, financial=60),
        _strategy("a", 80, financial=60),  # identical scores -> id tie-break
        _strategy("m", 80, financial=70),  # higher financial wins the overall tie
    ]
    ranked = rank_budget_cohort(strategies)
    assert [r["sealedProductId"] for r in ranked] == ["m", "a", "z"]


def test_ranking_is_deterministic_across_repeated_calls():
    strategies = [_strategy("a", 80), _strategy("b", 90), _strategy("c", 90)]
    first = rank_budget_cohort(strategies)
    second = rank_budget_cohort(list(reversed(strategies)))
    assert [r["sealedProductId"] for r in first] == [r["sealedProductId"] for r in second]


def test_every_rank_is_budget_qualified_no_naked_context_free_rank_field():
    # The rank record itself always carries its target budget alongside the
    # rank -- there is no bare "rank" concept divorced from a budget context.
    strategies = [_strategy("a", 80, target=250.0), _strategy("b", 90, target=250.0)]
    ranked = rank_budget_cohort(strategies)
    for row in ranked:
        assert row["targetBudget"] == 250.0
        assert "budgetRank" in row and "budgetCohortSize" in row


def test_full_market_budget_type_constant_is_distinct_from_standard_bands():
    assert BUDGET_TYPE_FULL_MARKET not in {f"{b:g}" for b in CANONICAL_BUDGET_BANDS}
