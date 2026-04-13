from unittest.mock import MagicMock, patch

from backend.db.repositories.graded_card_variant_prices_repository import get_latest_price


@patch("backend.db.repositories.graded_card_variant_prices_repository.supabase")
def test_get_latest_price_uses_shared_supabase_client(mock_supabase):
    query = MagicMock()
    mock_supabase.table.return_value = query
    query.select.return_value = query
    query.eq.return_value = query
    query.maybe_single.return_value = query

    response = MagicMock()
    response.data = {"graded_card_variant_id": 123, "market_price": 55.0}
    query.execute.return_value = response

    result = get_latest_price(123)

    mock_supabase.table.assert_called_once_with("graded_card_market_latest")
    assert result == {"graded_card_variant_id": 123, "market_price": 55.0}


@patch("backend.db.repositories.graded_card_variant_prices_repository.supabase")
def test_get_latest_price_returns_none_when_missing(mock_supabase):
    query = MagicMock()
    mock_supabase.table.return_value = query
    query.select.return_value = query
    query.eq.return_value = query
    query.maybe_single.return_value = query

    response = MagicMock()
    response.data = None
    query.execute.return_value = response

    assert get_latest_price(999) is None
