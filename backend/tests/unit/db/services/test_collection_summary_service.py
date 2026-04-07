from uuid import uuid4
from unittest.mock import patch

from backend.db.services.collection_summary_service import get_user_collection_summary
from backend.models.collection_summary_models import CollectionSummary


@patch("backend.db.services.collection_summary_service.load_user_collection_for_summary")
def test_get_user_collection_summary_returns_model(mock_loader):
    mock_loader.return_value = {
        "user_card_holdings": [{"quantity": 2, "market_price": 10.0}],
        "user_sealed_product_holdings": [{"quantity": 1, "market_price": 20.0}],
        "user_graded_card_holdings": [{"quantity": 3, "market_price": 5.0}],
    }

    result = get_user_collection_summary(uuid4())

    assert isinstance(result, CollectionSummary)
    assert result.cards_count == 2
    assert result.sealed_count == 1
    assert result.graded_count == 3
    assert result.portfolio_value == 55.0


@patch("backend.db.services.collection_summary_service.load_user_collection_for_summary")
def test_get_user_collection_summary_empty_payload(mock_loader):
    mock_loader.return_value = {
        "user_card_holdings": [],
        "user_sealed_product_holdings": [],
        "user_graded_card_holdings": [],
    }

    result = get_user_collection_summary(uuid4())

    assert result.portfolio_value == 0.0
    assert result.cards_count == 0
    assert result.sealed_count == 0
    assert result.graded_count == 0
