from unittest.mock import MagicMock, patch

from backend.db.repositories.sealed_product_prices_repository import get_latest_price


@patch("backend.db.repositories.sealed_product_prices_repository.create_client")
def test_get_latest_price_uses_latest_market_view(mock_create_client):
    client = MagicMock()
    query = MagicMock()
    mock_create_client.return_value = client
    client.table.return_value = query
    query.select.return_value = query
    query.eq.return_value = query
    query.maybe_single.return_value = query

    response = MagicMock()
    response.data = {"sealed_product_id": 987, "market_price": 44.5}
    query.execute.return_value = response

    result = get_latest_price(987)

    client.table.assert_called_once_with("sealed_product_market_usd_latest")
    assert result == {"sealed_product_id": 987, "market_price": 44.5}


@patch("backend.db.repositories.sealed_product_prices_repository.create_client")
def test_get_latest_price_returns_none_when_missing(mock_create_client):
    client = MagicMock()
    query = MagicMock()
    mock_create_client.return_value = client
    client.table.return_value = query
    query.select.return_value = query
    query.eq.return_value = query
    query.maybe_single.return_value = query

    response = MagicMock()
    response.data = None
    query.execute.return_value = response

    assert get_latest_price(111) is None
