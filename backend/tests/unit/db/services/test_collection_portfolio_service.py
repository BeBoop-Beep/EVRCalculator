from unittest.mock import patch

from backend.db.services.collection_portfolio_service import get_public_collection_data_by_username


@patch("backend.db.services.collection_portfolio_service.get_user_collection_summary_snapshot")
@patch("backend.db.services.collection_portfolio_service.get_collection_summary_and_items_for_user_id")
@patch("backend.db.services.collection_portfolio_service._select_with_fallback")
def test_get_public_collection_data_uses_summary_table_when_items_requested(
    mock_select_with_fallback,
    mock_collection_payload,
    mock_get_user_collection_summary_snapshot,
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
            "portfolio_value": 10.0,
            "cards_count": 99,
            "sealed_count": 88,
            "graded_count": 77,
        },
        "collection_items": [
            {
                "id": "item-1",
                "estimated_value": 0.0,
                "image_url": "https://example.test/card.png",
            }
        ],
    }
    mock_get_user_collection_summary_snapshot.return_value = {
        "portfolio_value": 2152.5,
        "cards_count": 1,
        "sealed_count": 1,
        "graded_count": 1,
        "portfolio_delta_1d": 3.5,
        "portfolio_delta_7d": 10.0,
        "portfolio_delta_3m": 22.0,
        "portfolio_delta_6m": 31.0,
        "portfolio_delta_1y": 50.0,
        "portfolio_delta_lifetime": 120.0,
        "portfolio_delta_pct_1d": 0.2,
        "portfolio_delta_pct_7d": 0.6,
        "portfolio_delta_pct_3m": 1.1,
        "portfolio_delta_pct_6m": 1.9,
        "portfolio_delta_pct_1y": 3.2,
        "portfolio_delta_pct_lifetime": 7.4,
        "computed_at": "2026-04-08T12:34:56+00:00",
        "is_stale": False,
        "row_found": True,
    }

    payload, error = get_public_collection_data_by_username("donald-stivison-jr", include_collection_items=True)

    assert error is None
    assert payload["collection_summary"] == {
        "portfolio_value": 2152.5,
        "cards_count": 1,
        "sealed_count": 1,
        "graded_count": 1,
        "portfolio_delta_1d": 3.5,
        "portfolio_delta_7d": 10.0,
        "portfolio_delta_3m": 22.0,
        "portfolio_delta_6m": 31.0,
        "portfolio_delta_1y": 50.0,
        "portfolio_delta_lifetime": 120.0,
        "portfolio_delta_pct_1d": 0.2,
        "portfolio_delta_pct_7d": 0.6,
        "portfolio_delta_pct_3m": 1.1,
        "portfolio_delta_pct_6m": 1.9,
        "portfolio_delta_pct_1y": 3.2,
        "portfolio_delta_pct_lifetime": 7.4,
    }
    assert payload["collection_items"] == mock_collection_payload.return_value["collection_items"]
    mock_get_user_collection_summary_snapshot.assert_called_once_with("875e0257-7233-4677-bde2-6e3388e22a9d")


@patch("backend.db.services.collection_portfolio_service.get_user_collection_summary_snapshot")
@patch("backend.db.services.collection_portfolio_service.resolve_public_user_by_username")
def test_get_public_collection_data_resolves_legacy_username_slug(
    mock_resolve_public_user_by_username,
    mock_get_user_collection_summary_snapshot,
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
    mock_get_user_collection_summary_snapshot.return_value = {
        "portfolio_value": 10.0,
        "cards_count": 1,
        "sealed_count": 0,
        "graded_count": 0,
        "portfolio_delta_1d": 0.0,
        "portfolio_delta_7d": 0.0,
        "portfolio_delta_3m": 0.0,
        "portfolio_delta_6m": 0.0,
        "portfolio_delta_1y": 0.0,
        "portfolio_delta_lifetime": 0.0,
        "portfolio_delta_pct_1d": None,
        "portfolio_delta_pct_7d": None,
        "portfolio_delta_pct_3m": None,
        "portfolio_delta_pct_6m": None,
        "portfolio_delta_pct_1y": None,
        "portfolio_delta_pct_lifetime": None,
        "computed_at": "2026-04-08T12:34:56+00:00",
        "is_stale": False,
        "row_found": True,
    }

    payload, error = get_public_collection_data_by_username("donald-stivison-jr")

    assert error is None
    assert payload["collection_summary"]["portfolio_value"] == 10.0


@patch("backend.db.services.collection_portfolio_service.get_user_collection_summary_snapshot")
@patch("backend.db.services.collection_portfolio_service.resolve_public_user_by_username")
def test_get_public_collection_data_returns_zero_summary_when_summary_row_missing(
    mock_resolve_public_user_by_username,
    mock_get_user_collection_summary_snapshot,
):
    mock_resolve_public_user_by_username.return_value = (
        {
            "id": "875e0257-7233-4677-bde2-6e3388e22a9d",
            "username": "donald-stivison-jr",
            "is_profile_public": True,
        },
        {
            "normalized_username": "donald-stivison-jr",
            "lookup_strategy": "username_exact",
            "row_found": True,
        },
    )
    mock_get_user_collection_summary_snapshot.return_value = {
        "portfolio_value": 0.0,
        "cards_count": 0,
        "sealed_count": 0,
        "graded_count": 0,
        "portfolio_delta_1d": 0.0,
        "portfolio_delta_7d": 0.0,
        "portfolio_delta_3m": 0.0,
        "portfolio_delta_6m": 0.0,
        "portfolio_delta_1y": 0.0,
        "portfolio_delta_lifetime": 0.0,
        "portfolio_delta_pct_1d": None,
        "portfolio_delta_pct_7d": None,
        "portfolio_delta_pct_3m": None,
        "portfolio_delta_pct_6m": None,
        "portfolio_delta_pct_1y": None,
        "portfolio_delta_pct_lifetime": None,
        "computed_at": None,
        "is_stale": None,
        "row_found": False,
    }

    payload, error = get_public_collection_data_by_username("donald-stivison-jr")

    assert error is None
    assert payload["collection_summary"] == {
        "portfolio_value": 0.0,
        "cards_count": 0,
        "sealed_count": 0,
        "graded_count": 0,
        "portfolio_delta_1d": 0.0,
        "portfolio_delta_7d": 0.0,
        "portfolio_delta_3m": 0.0,
        "portfolio_delta_6m": 0.0,
        "portfolio_delta_1y": 0.0,
        "portfolio_delta_lifetime": 0.0,
        "portfolio_delta_pct_1d": None,
        "portfolio_delta_pct_7d": None,
        "portfolio_delta_pct_3m": None,
        "portfolio_delta_pct_6m": None,
        "portfolio_delta_pct_1y": None,
        "portfolio_delta_pct_lifetime": None,
    }