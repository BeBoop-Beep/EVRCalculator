"""Contract tests for the RIP decision-layer display math.

These are pure transformations of numbers that already exist on
``simulation_sealed_product_results`` / ``simulation_input_cards``. Nothing here
is a score, and nothing here is allowed to invent a value when its inputs are
missing - a fabricated 0.0 ratio reads exactly like a real one on a page.
"""

import math

import pytest

from backend.domain.pokemon.rip_decision_metrics import (
    exact_card_probability_contract,
    implied_odds_one_in_n,
    packs_for_cumulative_probability,
    product_decision_metrics,
)


# ---------------------------------------------------------------------------
# Product decision metrics
# ---------------------------------------------------------------------------

def test_model_break_even_price_is_exactly_expected_value():
    metrics = product_decision_metrics(expected_value=9.0, product_market_cost=12.0)
    assert metrics["modelBreakEvenPrice"] == 9.0


def test_model_break_even_price_survives_a_missing_market_cost():
    # The price at which modeled EV equals purchase price does not depend on
    # what the product currently costs, so it stays available when cost does not.
    metrics = product_decision_metrics(expected_value=9.0, product_market_cost=None)
    assert metrics["modelBreakEvenPrice"] == 9.0
    assert metrics["modeledReturnRatio"] is None


def test_underwater_product_ratios():
    metrics = product_decision_metrics(expected_value=9.0, product_market_cost=12.0)
    assert metrics["modeledReturnRatio"] == 0.75
    assert metrics["modeledReturnPercent"] == 75.0
    assert metrics["modelEdgePercent"] == -25.0


def test_positive_edge_product_ratios_are_free_of_float_noise():
    metrics = product_decision_metrics(expected_value=10.5, product_market_cost=10.0)
    assert metrics["modeledReturnRatio"] == 1.05
    assert metrics["modeledReturnPercent"] == 105.0
    assert metrics["modelEdgePercent"] == 5.0


@pytest.mark.parametrize("cost", [None, 0, 0.0, -1.0, "", "abc", float("nan"), float("inf")])
def test_invalid_market_cost_never_fabricates_metrics(cost):
    metrics = product_decision_metrics(expected_value=9.0, product_market_cost=cost)
    assert metrics["modeledReturnRatio"] is None
    assert metrics["modeledReturnPercent"] is None
    assert metrics["modelEdgePercent"] is None


@pytest.mark.parametrize("expected_value", [None, "", "abc", float("nan"), float("inf"), -1.0])
def test_invalid_expected_value_never_fabricates_metrics(expected_value):
    metrics = product_decision_metrics(expected_value=expected_value, product_market_cost=12.0)
    assert metrics["modelBreakEvenPrice"] is None
    assert metrics["modeledReturnRatio"] is None
    assert metrics["modeledReturnPercent"] is None
    assert metrics["modelEdgePercent"] is None


def test_a_zero_expected_value_is_a_real_result_not_a_missing_one():
    # A modeled EV of exactly zero is a legitimate (if extreme) model output.
    # Treating it as "missing" would hide a real answer behind an outage state.
    metrics = product_decision_metrics(expected_value=0.0, product_market_cost=10.0)
    assert metrics["modelBreakEvenPrice"] == 0.0
    assert metrics["modeledReturnRatio"] == 0.0
    assert metrics["modelEdgePercent"] == -100.0


# ---------------------------------------------------------------------------
# Exact-card cumulative probability
# ---------------------------------------------------------------------------

def test_packs_for_fifty_and_ninety_percent_of_a_known_probability():
    # p = 0.01: ceil(ln(0.5)/ln(0.99)) = 69, ceil(ln(0.1)/ln(0.99)) = 230.
    assert packs_for_cumulative_probability(0.01, 0.50) == 69
    assert packs_for_cumulative_probability(0.01, 0.90) == 230


def test_packs_for_a_one_in_four_pull():
    assert packs_for_cumulative_probability(0.25, 0.50) == 3
    assert packs_for_cumulative_probability(0.25, 0.90) == 9


@pytest.mark.parametrize("p", [0, 0.0, -0.5, None, "", "abc", float("nan"), float("inf")])
def test_non_positive_or_missing_probability_is_unavailable(p):
    assert packs_for_cumulative_probability(p, 0.50) is None
    assert implied_odds_one_in_n(p) is None


@pytest.mark.parametrize("p", [1.0, 1, 1.5])
def test_certain_probability_needs_exactly_one_pack(p):
    assert packs_for_cumulative_probability(p, 0.50) == 1
    assert packs_for_cumulative_probability(p, 0.90) == 1


def test_implied_odds_are_the_reciprocal_of_the_modeled_probability():
    assert implied_odds_one_in_n(0.004) == 250.0
    assert implied_odds_one_in_n(1.0) == 1.0


def test_probability_contract_is_json_safe_for_every_input():
    for p in (None, 0.0, -1.0, float("nan"), float("inf"), 1e-12, 0.01, 1.0):
        contract = exact_card_probability_contract(p)
        for key in (
            "modeledProbability",
            "impliedOddsOneInN",
            "packsFor50PercentChance",
            "packsFor90PercentChance",
        ):
            value = contract[key]
            assert value is None or (
                isinstance(value, (int, float)) and math.isfinite(value)
            ), f"{key} for p={p!r} was {value!r}"


def test_a_vanishingly_small_probability_stays_finite_rather_than_overflowing():
    contract = exact_card_probability_contract(1e-12)
    assert contract["packsFor50PercentChance"] is not None
    assert math.isfinite(contract["packsFor50PercentChance"])
