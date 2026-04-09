from unittest.mock import patch

from backend.db.services.collection_portfolio_service import get_public_collection_data_by_username
from backend.models.collection_summary_models import CollectionSummary


@patch("backend.db.services.collection_summary_service.get_user_collection_summary")
@patch("backend.db.services.collection_portfolio_service.get_collection_summary_and_items_for_user_id")
@patch("backend.db.services.collection_portfolio_service._select_with_fallback")
def test_get_public_collection_data_uses_authoritative_summary(
    mock_select_with_fallback,
    mock_collection_payload,
    mock_get_user_collection_summary,
):
    mock_select_with_fallback.return_value = [
        {
            "id": "875e0257-7233-4677-bde2-6e3388e22a9d",
            "username": "donald-stivison-jr",
            "is_profile_public": True,
        }
    ]
    mock_collection_payload.return_value = {
        "summary": {
            "portfolio_value": 0.0,
            "cards_count": 1,
            "sealed_count": 1,
            "graded_count": 1,
        },
        "collection_items": [
            {
                "id": "item-1",
                "estimated_value": 0.0,
                "image_url": "https://example.test/card.png",
            }
        ],
    }
    mock_get_user_collection_summary.return_value = CollectionSummary(
        portfolio_value=2152.5,
        cards_count=1,
        sealed_count=1,
        graded_count=1,
    )

    payload, error = get_public_collection_data_by_username("donald-stivison-jr", include_collection_items=True)

    assert error is None
    assert payload["collection_summary"] == {
        "portfolio_value": 2152.5,
        "cards_count": 1,
        "sealed_count": 1,
        "graded_count": 1,
    }
    assert payload["collection_items"] == mock_collection_payload.return_value["collection_items"]


@patch("backend.db.services.collection_summary_service.get_user_collection_summary")
@patch("backend.db.services.collection_portfolio_service.get_collection_summary_and_items_for_user_id")
@patch("backend.db.services.collection_portfolio_service.resolve_public_user_by_username")
def test_get_public_collection_data_resolves_legacy_username_slug(
    mock_resolve_public_user_by_username,
    mock_collection_payload,
    mock_get_user_collection_summary,
):
    mock_resolve_public_user_by_username.return_value = (
        {
            "id": "875e0257-7233-4677-bde2-6e3388e22a9d",
            "username": "Donald Stivison Jr",
            "is_profile_public": True,
        },
        {
            "normalized_username": "donald-stivison-jr",
            "lookup_strategy": "username_ilike_spaced",
            "row_found": True,
        },
    )
    mock_collection_payload.return_value = {
        "summary": {
            "portfolio_value": 0.0,
            "cards_count": 1,
            "sealed_count": 0,
            "graded_count": 0,
        },
        "collection_items": [],
    }
    mock_get_user_collection_summary.return_value = CollectionSummary(
        portfolio_value=10.0,
        cards_count=1,
        sealed_count=0,
        graded_count=0,
    )

    payload, error = get_public_collection_data_by_username("donald-stivison-jr")

    assert error is None
    assert payload["collection_summary"]["portfolio_value"] == 10.0