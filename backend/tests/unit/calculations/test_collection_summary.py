from backend.calculations.collection_summary import (
    calculate_cards_count,
    calculate_graded_count,
    calculate_portfolio_value,
    calculate_sealed_count,
)


def test_empty_holdings_are_zero():
    assert calculate_cards_count(user_card_holdings=[]) == 0
    assert calculate_sealed_count(user_sealed_product_holdings=[]) == 0
    assert calculate_graded_count(user_graded_card_holdings=[]) == 0
    assert (
        calculate_portfolio_value(
            user_card_holdings=[],
            user_sealed_product_holdings=[],
            user_graded_card_holdings=[],
        )
        == 0.0
    )


def test_counts_sum_quantities():
    assert calculate_cards_count(user_card_holdings=[{"quantity": 2}, {"quantity": 5}]) == 7
    assert calculate_sealed_count(user_sealed_product_holdings=[{"quantity": 3}, {"quantity": 1}]) == 4
    assert calculate_graded_count(user_graded_card_holdings=[{"quantity": 4}, {"quantity": 6}]) == 10


def test_portfolio_value_sums_all_three_domains():
    value = calculate_portfolio_value(
        user_card_holdings=[{"quantity": 2, "market_price": 10.0}],
        user_sealed_product_holdings=[{"quantity": 3, "market_price": 20.0}],
        user_graded_card_holdings=[{"quantity": 1, "market_price": 50.0}],
    )
    assert value == 130.0


def test_invalid_values_become_zero():
    assert calculate_cards_count(user_card_holdings=[{"quantity": -2}, {"quantity": "bad"}, {"quantity": 3}]) == 3
    value = calculate_portfolio_value(
        user_card_holdings=[{"quantity": -1, "market_price": 10.0}, {"quantity": 2, "market_price": -10.0}],
        user_sealed_product_holdings=[{"quantity": 2, "market_price": "bad"}],
        user_graded_card_holdings=[{"quantity": 1, "market_price": 4.0}],
    )
    assert value == 4.0


def test_explicit_signature_supports_positional_arguments():
    assert calculate_cards_count([{"quantity": 2}, {"quantity": 3}]) == 5
    assert calculate_sealed_count([{"quantity": 4}]) == 4
    assert calculate_graded_count([{"quantity": 1}, {"quantity": 2}]) == 3
