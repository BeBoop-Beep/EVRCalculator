import pytest

from backend.domain.pokemon.constituent_movement import (
    CONSTITUENT_MOVEMENT_WINDOWS,
    build_constituent_movements,
    prices_by_date_from_observations,
    prices_by_date_from_product_histories,
)


def test_movement_is_per_constituent_not_an_aggregate():
    prices = {
        "2026-08-24": {"a": 100.0, "b": 50.0},
        "2026-08-25": {"a": 110.0, "b": 45.0},
    }
    result = build_constituent_movements(prices, windows=("1D",))["byConstituent"]
    assert result["a"]["1D"] == pytest.approx(10.0)
    assert result["b"]["1D"] == pytest.approx(-10.0)


def test_absent_at_window_start_is_unavailable_not_zero():
    prices = {
        "2026-07-01": {"a": 100.0},
        "2026-08-25": {"a": 120.0, "b": 10.0},
    }
    result = build_constituent_movements(prices, windows=("30D",))["byConstituent"]
    assert result["a"]["30D"] is not None
    # None, never 0.0 — "b" was not observed at the window start at all.
    assert result["b"]["30D"] is None


def test_flat_price_reports_a_real_zero():
    prices = {"2026-08-24": {"a": 100.0}, "2026-08-25": {"a": 100.0}}
    result = build_constituent_movements(prices, windows=("1D",))["byConstituent"]
    # A genuine zero is a zero, and must never collapse into the None above.
    assert result["a"]["1D"] == 0.0


def test_every_requested_window_is_present_for_every_current_constituent():
    prices = {"2026-05-01": {"a": 80.0}, "2026-08-24": {"a": 90.0}, "2026-08-25": {"a": 100.0}}
    result = build_constituent_movements(prices)["byConstituent"]
    assert set(result["a"]) == set(CONSTITUENT_MOVEMENT_WINDOWS)


def test_non_positive_and_unparseable_prices_are_dropped_not_zero_filled():
    prices = {
        "2026-08-24": {"a": 0, "b": "nope", "c": 10.0},
        "2026-08-25": {"a": 5.0, "b": 5.0, "c": 12.0},
    }
    result = build_constituent_movements(prices, windows=("1D",))["byConstituent"]
    assert result["a"]["1D"] is None
    assert result["b"]["1D"] is None
    assert result["c"]["1D"] == pytest.approx(20.0)


def test_only_constituents_present_on_the_latest_date_are_reported():
    prices = {"2026-08-24": {"gone": 10.0}, "2026-08-25": {"here": 10.0}}
    result = build_constituent_movements(prices, windows=("1D",))["byConstituent"]
    assert set(result) == {"here"}


def test_observation_adapter_reads_the_shared_index_field_names():
    observations = [
        {"marketDate": "2026-08-24", "constituents": [{"setId": "card-1", "setValue": 10.0}]},
        {"marketDate": "2026-08-25", "constituents": [{"setId": "card-1", "setValue": 11.0}]},
    ]
    prices = prices_by_date_from_observations(observations)
    assert prices == {"2026-08-24": {"card-1": 10.0}, "2026-08-25": {"card-1": 11.0}}
    assert build_constituent_movements(prices, windows=("1D",))["byConstituent"]["card-1"]["1D"] == pytest.approx(10.0)


def test_product_history_adapter_reads_each_products_own_history():
    products = [
        {
            "sealedProductId": "etb-1",
            "history": [
                {"date": "2026-08-24", "marketPrice": 50.0},
                {"date": "2026-08-25", "marketPrice": 55.0},
            ],
        },
        {"sealedProductId": "", "history": [{"date": "2026-08-25", "marketPrice": 1.0}]},
    ]
    prices = prices_by_date_from_product_histories(products)
    assert prices["2026-08-25"] == {"etb-1": 55.0}
    assert build_constituent_movements(prices, windows=("1D",))["byConstituent"]["etb-1"]["1D"] == pytest.approx(10.0)


def test_empty_input_returns_empty_rather_than_raising():
    assert build_constituent_movements({}) == {"windows": {}, "byConstituent": {}}
    assert prices_by_date_from_observations([]) == {}
    assert prices_by_date_from_product_histories([]) == {}


def test_query_row_adapter_accepts_camel_and_snake_case_ids():
    from backend.domain.pokemon.constituent_movement import prices_by_date_from_query_rows

    rows = [
        {"market_date": "2026-08-24", "canonical_card_id": "c1", "market_price": 10.0},
        {"marketDate": "2026-08-25", "canonicalCardId": "c1", "marketPrice": 12.0},
    ]
    prices = prices_by_date_from_query_rows(rows)
    assert prices == {"2026-08-24": {"c1": 10.0}, "2026-08-25": {"c1": 12.0}}


def test_query_row_adapter_covers_the_whole_universe_not_just_basket_members():
    """A card outside today's Top N still contributes its own price history."""
    from backend.domain.pokemon.constituent_movement import prices_by_date_from_query_rows

    rows = [
        {"marketDate": "2026-08-24", "canonicalCardId": "rank12", "marketPrice": 10.0},
        {"marketDate": "2026-08-25", "canonicalCardId": "rank12", "marketPrice": 20.0},
    ]
    movements = build_constituent_movements(
        prices_by_date_from_query_rows(rows), windows=("1D",)
    )["byConstituent"]
    assert movements["rank12"]["1D"] == pytest.approx(100.0)


def test_window_dates_are_published_once_for_the_market_not_per_constituent():
    # The size decision, asserted: three boundary dates repeated across every
    # row measured at +349% on a 25-card summary. They belong to the market.
    prices = {
        "2026-08-24": {"a": 10.0, "b": 20.0},
        "2026-08-25": {"a": 11.0, "b": 21.0},
    }
    result = build_constituent_movements(prices, windows=("1D",))
    assert result["windows"]["1D"]["startDate"] == "2026-08-24"
    assert result["windows"]["1D"]["endDate"] == "2026-08-25"
    assert result["windows"]["1D"]["available"] is True
    # A row carries a bare number and nothing else.
    for value in result["byConstituent"].values():
        assert set(value) == {"1D"}
        assert isinstance(value["1D"], float)


def test_a_window_the_market_cannot_measure_is_reported_at_the_market_level():
    prices = {"2026-08-25": {"a": 10.0}}
    result = build_constituent_movements(prices, windows=("30D",))
    assert result["windows"]["30D"]["available"] is False
    assert result["windows"]["30D"]["startDate"] is None
    assert result["byConstituent"]["a"]["30D"] is None
