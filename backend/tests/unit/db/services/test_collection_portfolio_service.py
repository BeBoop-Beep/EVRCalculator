from unittest.mock import patch

from backend.db.services.collection_portfolio_service import get_public_collection_data_by_username


@patch("backend.db.services.collection_summary_service.get_user_collection_summary_snapshot")
@patch("backend.db.services.collection_portfolio_service._load_collection_items_from_market_view")
@patch("backend.db.services.collection_portfolio_service.get_collection_summary_and_items_for_user_id")
def test_get_public_collection_data_uses_market_items_for_totals_and_snapshot_for_deltas(
    mock_collection_payload,
    mock_load_collection_items_from_market_view,
    mock_get_user_collection_summary_snapshot,
):
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
    mock_load_collection_items_from_market_view.return_value = [
        {
            "id": "card-row",
            "collectible_type": "card",
            "quantity": 1,
            "estimated_value": 120.0,
        },
        {
            "id": "graded-row",
            "collectible_type": "graded_card",
            "quantity": 1,
            "estimated_value": 333.0,
        },
        {
            "id": "sealed-row",
            "collectible_type": "sealed_product",
            "quantity": 1,
            "estimated_value": 220.99,
        },
    ]
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

    payload, error = get_public_collection_data_by_username(
        "donald-stivison-jr",
        include_collection_items=True,
        resolved_public_user={
            "id": "875e0257-7233-4677-bde2-6e3388e22a9d",
            "username": "donald-stivison-jr",
            "is_profile_public": True,
        },
    )

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
        "computed_at": "2026-04-08T12:34:56+00:00",
        "is_stale": False,
        "row_found": True,
    }
    assert payload["collection_items"] == mock_load_collection_items_from_market_view.return_value
    mock_get_user_collection_summary_snapshot.assert_called_once()


@patch("backend.db.services.collection_summary_service.get_user_collection_summary_snapshot")
@patch("backend.db.services.collection_portfolio_service._load_collection_items_from_market_view")
def test_get_public_collection_data_resolves_legacy_username_slug(
    mock_load_collection_items_from_market_view,
    mock_get_user_collection_summary_snapshot,
):
    mock_load_collection_items_from_market_view.return_value = [
        {
            "id": "card-row",
            "collectible_type": "card",
            "quantity": 1,
            "estimated_value": 10.0,
        }
    ]
    mock_get_user_collection_summary_snapshot.return_value = {
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

    payload, error = get_public_collection_data_by_username(
        "donald-stivison-jr",
        resolved_public_user={
            "id": "875e0257-7233-4677-bde2-6e3388e22a9d",
            "username": "Donald Stivison Jr",
            "is_profile_public": True,
        },
    )

    assert error is None
    assert payload["collection_summary"]["portfolio_value"] is None
    assert payload["collection_summary"]["row_found"] is True
    assert payload["collection_summary"]["is_stale"] is False


@patch("backend.db.services.collection_summary_service.get_user_collection_summary_snapshot")
@patch("backend.db.services.collection_portfolio_service._load_collection_items_from_market_view")
@patch("backend.db.services.collection_portfolio_service.get_collection_summary_and_items_for_user_id")
def test_get_public_collection_data_returns_zero_summary_when_summary_row_missing(
    mock_get_collection_summary_and_items_for_user_id,
    mock_load_collection_items_from_market_view,
    mock_get_user_collection_summary_snapshot,
):
    mock_get_collection_summary_and_items_for_user_id.return_value = {
        "summary": {
            "portfolio_value": 0.0,
            "cards_count": 0,
            "sealed_count": 0,
            "graded_count": 0,
        },
        "collection_items": [],
    }
    mock_load_collection_items_from_market_view.return_value = []
    mock_get_user_collection_summary_snapshot.return_value = {
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

    payload, error = get_public_collection_data_by_username(
        "donald-stivison-jr",
        resolved_public_user={
            "id": "875e0257-7233-4677-bde2-6e3388e22a9d",
            "username": "donald-stivison-jr",
            "is_profile_public": True,
        },
    )

    assert error is None
    assert payload["collection_summary"] == {
        "portfolio_value": None,
        "cards_count": None,
        "sealed_count": None,
        "graded_count": None,
        "portfolio_delta_1d": None,
        "portfolio_delta_7d": None,
        "portfolio_delta_3m": None,
        "portfolio_delta_6m": None,
        "portfolio_delta_1y": None,
        "portfolio_delta_lifetime": None,
        "portfolio_delta_pct_1d": None,
        "portfolio_delta_pct_7d": None,
        "portfolio_delta_pct_3m": None,
        "portfolio_delta_pct_6m": None,
        "portfolio_delta_pct_1y": None,
        "portfolio_delta_pct_lifetime": None,
        "computed_at": None,
        "is_stale": True,
        "row_found": False,
    }


@patch("backend.db.services.collection_portfolio_service._load_collection_items_from_market_view")
@patch("backend.db.services.collection_summary_service.get_user_collection_summary_snapshot")
def test_get_public_collection_data_prefers_market_view_items(
    mock_get_user_collection_summary_snapshot,
    mock_load_collection_items_from_market_view,
):
    mock_get_user_collection_summary_snapshot.return_value = {
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

    mock_load_collection_items_from_market_view.return_value = [
        {"id": "card-row", "collectible_type": "card", "quantity": 1, "estimated_value": 120.0},
        {"id": "graded-row", "collectible_type": "graded_card", "quantity": 1, "estimated_value": 333.0},
        {"id": "sealed-row", "collectible_type": "sealed_product", "quantity": 1, "estimated_value": 220.99},
    ]

    payload, error = get_public_collection_data_by_username(
        "donald-stivison-jr",
        include_collection_items=True,
        resolved_public_user={
            "id": "875e0257-7233-4677-bde2-6e3388e22a9d",
            "username": "donald-stivison-jr",
            "is_profile_public": True,
        },
    )

    assert error is None
    assert payload["collection_summary"]["portfolio_value"] is None
    assert payload["collection_summary"]["row_found"] is False
    assert len(payload["collection_items"]) == 3
    assert {item["collectible_type"] for item in payload["collection_items"]} == {
        "card",
        "graded_card",
        "sealed_product",
    }
    mock_load_collection_items_from_market_view.assert_called_once_with("875e0257-7233-4677-bde2-6e3388e22a9d")


@patch("backend.db.services.collection_summary_service.get_user_collection_summary_snapshot")
@patch("backend.db.services.collection_portfolio_service._load_collection_items_from_market_view")
def test_get_public_collection_data_does_not_recompute_summary_from_items(
    mock_load_collection_items_from_market_view,
    mock_get_user_collection_summary_snapshot,
):
    mock_load_collection_items_from_market_view.return_value = [
        {"id": "card-row", "collectible_type": "card", "quantity": 1, "estimated_value": 120.0},
        {"id": "graded-row", "collectible_type": "graded_card", "quantity": 1, "estimated_value": 333.0},
        {"id": "sealed-row", "collectible_type": "sealed_product", "quantity": 1, "estimated_value": 220.99},
    ]
    mock_get_user_collection_summary_snapshot.return_value = {
        "portfolio_value": 42.0,
        "cards_count": 7,
        "sealed_count": 8,
        "graded_count": 9,
        "portfolio_delta_1d": 1.5,
        "portfolio_delta_7d": 2.5,
        "portfolio_delta_3m": 3.5,
        "portfolio_delta_6m": 4.5,
        "portfolio_delta_1y": 5.5,
        "portfolio_delta_lifetime": 6.5,
        "portfolio_delta_pct_1d": 0.1,
        "portfolio_delta_pct_7d": 0.2,
        "portfolio_delta_pct_3m": 0.3,
        "portfolio_delta_pct_6m": 0.4,
        "portfolio_delta_pct_1y": 0.5,
        "portfolio_delta_pct_lifetime": 0.6,
        "computed_at": "2026-04-19T00:00:00+00:00",
        "is_stale": False,
        "row_found": True,
    }

    payload, error = get_public_collection_data_by_username(
        "donald-stivison-jr",
        include_collection_items=True,
        resolved_public_user={
            "id": "875e0257-7233-4677-bde2-6e3388e22a9d",
            "username": "donald-stivison-jr",
            "is_profile_public": True,
        },
    )

    assert error is None
    assert payload["collection_summary"]["portfolio_value"] == 42.0
    assert payload["collection_summary"]["cards_count"] == 7
    assert payload["collection_summary"]["sealed_count"] == 8
    assert payload["collection_summary"]["graded_count"] == 9
    assert payload["collection_summary"]["row_found"] is True


@patch("backend.db.services.collection_portfolio_service.get_collection_summary_and_items_for_user_id")
@patch("backend.db.services.collection_summary_service.get_user_collection_summary_snapshot")
@patch("backend.db.services.collection_portfolio_service._load_collection_items_from_market_view")
def test_get_public_collection_data_uses_item_only_fallback_when_market_view_is_empty(
    mock_load_collection_items_from_market_view,
    mock_get_user_collection_summary_snapshot,
    mock_get_collection_summary_and_items_for_user_id,
):
    mock_load_collection_items_from_market_view.return_value = []
    mock_get_user_collection_summary_snapshot.return_value = {
        "portfolio_value": 2160.07,
        "cards_count": 1,
        "sealed_count": 1,
        "graded_count": 1,
        "portfolio_delta_1d": 62.5,
        "portfolio_delta_7d": 80.0,
        "portfolio_delta_3m": 120.0,
        "portfolio_delta_6m": 160.0,
        "portfolio_delta_1y": 220.0,
        "portfolio_delta_lifetime": 420.0,
        "portfolio_delta_pct_1d": 2.9,
        "portfolio_delta_pct_7d": 3.7,
        "portfolio_delta_pct_3m": 5.9,
        "portfolio_delta_pct_6m": 8.1,
        "portfolio_delta_pct_1y": 11.4,
        "portfolio_delta_pct_lifetime": 24.0,
        "computed_at": "2026-04-19T00:00:00+00:00",
        "is_stale": False,
        "row_found": True,
    }
    mock_get_collection_summary_and_items_for_user_id.return_value = {
        "summary": {
            "portfolio_value": 999.0,
            "cards_count": 999,
            "sealed_count": 999,
            "graded_count": 999,
        },
        "collection_items": [
            {"id": "card-row", "collectible_type": "card", "quantity": 1, "estimated_value": 1485.21},
            {"id": "graded-row", "collectible_type": "graded_card", "quantity": 1, "estimated_value": 424.0},
            {"id": "sealed-row", "collectible_type": "sealed_product", "quantity": 1, "estimated_value": 249.99},
        ],
    }

    payload, error = get_public_collection_data_by_username(
        "donald-stivison-jr",
        include_collection_items=True,
        resolved_public_user={
            "id": "875e0257-7233-4677-bde2-6e3388e22a9d",
            "username": "donald-stivison-jr",
            "is_profile_public": True,
        },
    )

    assert error is None
    assert payload["collection_summary"]["portfolio_value"] == 2160.07
    assert payload["collection_summary"]["cards_count"] == 1
    assert payload["collection_summary"]["sealed_count"] == 1
    assert payload["collection_summary"]["graded_count"] == 1
    assert len(payload["collection_items"]) == 3
    assert {item["collectible_type"] for item in payload["collection_items"]} == {
        "card",
        "graded_card",
        "sealed_product",
    }
    mock_get_collection_summary_and_items_for_user_id.assert_called_once_with(
        user_id="875e0257-7233-4677-bde2-6e3388e22a9d",
        include_collection_items=True,
        include_private_fields=False,
    )