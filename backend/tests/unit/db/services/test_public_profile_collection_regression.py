from types import SimpleNamespace
from unittest.mock import MagicMock, patch

from backend.db.services.collection_portfolio_service import (
    get_collection_summary_and_items_for_user_id,
    get_public_collection_data_by_username,
)
from backend.db.services.frontend_proxy_service import get_public_profile


@patch("backend.db.services.collection_portfolio_service._select_with_fallback")
def test_public_collection_items_use_non_zero_market_prices_and_summary_alignment(mock_select_with_fallback):
    def select_side_effect(table, select_candidates, filters=None, order_by=None, limit=None):
        if table == "user_card_holdings":
            return [{"id": "hold-1", "card_variant_id": 101, "condition_id": 1, "quantity": 2}]
        if table == "user_sealed_product_holdings":
            return []
        if table == "user_graded_card_holdings":
            return []
        if table == "card_market_usd_latest_by_condition":
            return [{"variant_id": 101, "condition_id": 1, "usd_market_price": 12.5}]
        if table == "sealed_product_market_usd_latest":
            return []
        if table == "graded_card_market_latest":
            return []
        if table == "card_variants":
            return [{"id": 101, "card_id": 201, "printing_type": "Holo", "special_type": None, "edition": None}]
        if table == "cards":
            return [
                {
                    "id": 201,
                    "name": "Test Card",
                    "rarity": "Rare",
                    "card_number": "1/100",
                    "set_id": 301,
                    "image_small_url": None,
                    "image_large_url": "https://cdn.example/card-large.png",
                }
            ]
        if table == "graded_card_variants":
            return []
        if table == "sealed_products":
            return []
        if table == "sets":
            return [{"id": 301, "name": "Test Set"}]
        if table == "conditions":
            return [{"id": 1, "name": "Near Mint"}]
        return []

    mock_select_with_fallback.side_effect = select_side_effect

    payload = get_collection_summary_and_items_for_user_id("user-1", include_collection_items=True)

    items = payload["collection_items"]
    assert len(items) == 1
    assert items[0]["estimated_value"] == 25.0
    assert items[0]["image_url"] == "https://cdn.example/card-large.png"

    summary = payload["summary"]
    assert summary["portfolio_value"] == 25.0
    assert summary["cards_count"] == 2
    assert summary["sealed_count"] == 0
    assert summary["graded_count"] == 0


@patch("backend.db.services.collection_portfolio_service._select_with_fallback")
def test_public_collection_graded_item_prefers_graded_variant_image(mock_select_with_fallback):
    def select_side_effect(table, select_candidates, filters=None, order_by=None, limit=None):
        if table == "user_card_holdings":
            return []
        if table == "user_sealed_product_holdings":
            return []
        if table == "user_graded_card_holdings":
            return [{"id": "gh-1", "graded_card_variant_id": 901, "quantity": 1}]
        if table == "card_market_usd_latest_by_condition":
            return []
        if table == "sealed_product_market_usd_latest":
            return []
        if table == "graded_card_market_latest":
            return [{"graded_card_variant_id": 901, "market_price": 42.0}]
        if table == "card_variants":
            return [{"id": 401, "card_id": 501, "printing_type": None, "special_type": None, "edition": None}]
        if table == "cards":
            return [
                {
                    "id": 501,
                    "name": "Linked Card",
                    "rarity": "Rare",
                    "card_number": "5/100",
                    "set_id": 601,
                    "image_small_url": "https://cdn.example/card-small.png",
                    "image_large_url": "https://cdn.example/card-large.png",
                }
            ]
        if table == "graded_card_variants":
            return [
                {
                    "id": 901,
                    "card_variant_id": 401,
                    "grade": "10",
                    "grading_company": "PSA",
                    "image_small_url": "https://cdn.example/graded-small.png",
                    "image_large_url": "https://cdn.example/graded-large.png",
                }
            ]
        if table == "sealed_products":
            return []
        if table == "sets":
            return [{"id": 601, "name": "Graded Set"}]
        if table == "conditions":
            return []
        return []

    mock_select_with_fallback.side_effect = select_side_effect

    payload = get_collection_summary_and_items_for_user_id("user-2", include_collection_items=True)

    item = payload["collection_items"][0]
    assert item["collectible_type"] == "graded_card"
    assert item["image_url"] == "https://cdn.example/graded-large.png"
    assert item["estimated_value"] == 42.0


@patch("backend.db.services.public_identity_service.resolve_public_user_by_username")
def test_public_collection_nonexistent_username_still_returns_not_found(mock_resolve_public_user_by_username):
    mock_resolve_public_user_by_username.return_value = (None, {"row_found": False, "reason": "USER_NOT_FOUND"})

    payload, error = get_public_collection_data_by_username("missing-user")

    assert payload is None
    assert error == "User not found."


@patch("backend.db.services.frontend_proxy_service.get_public_collection_data_by_username")
@patch("backend.db.services.frontend_proxy_service.resolve_public_user_by_username")
@patch("backend.db.services.frontend_proxy_service.supabase")
def test_public_profile_payload_preserves_view_count_when_available(
    mock_supabase,
    mock_resolve_public_user_by_username,
    mock_get_public_collection_data_by_username,
):
    mock_resolve_public_user_by_username.return_value = (
        {"id": "user-123", "username": "collector", "is_profile_public": True},
        {"row_found": True, "lookup_strategy": "username_eq_normalized"},
    )

    profile_query = MagicMock()
    tcg_query = MagicMock()

    profile_query.select.return_value = profile_query
    profile_query.eq.return_value = profile_query
    profile_query.limit.return_value = profile_query
    profile_query.execute.return_value = SimpleNamespace(
        data=[
            {
                "id": "user-123",
                "username": "collector",
                "display_name": "Collector",
                "avatar_url": None,
                "bio": None,
                "is_profile_public": True,
                "location": None,
                "favorite_tcg_id": 7,
                "created_at": "2026-01-01T00:00:00+00:00",
                "view_count": 19,
            }
        ]
    )

    tcg_query.select.return_value = tcg_query
    tcg_query.eq.return_value = tcg_query
    tcg_query.limit.return_value = tcg_query
    tcg_query.execute.return_value = SimpleNamespace(data=[{"id": 7, "name": "Pokemon"}])

    def table_side_effect(table_name):
        if table_name == "users":
            return profile_query
        if table_name == "tcgs":
            return tcg_query
        raise AssertionError(f"Unexpected table lookup: {table_name}")

    mock_supabase.table.side_effect = table_side_effect
    mock_get_public_collection_data_by_username.return_value = ({"collection_summary": {"portfolio_value": 50.0}}, None)

    payload, status = get_public_profile("collector", None)

    assert status == 200
    assert payload["profile"]["view_count"] == 19
    assert payload["profile"]["collection_summary"]["portfolio_value"] == 50.0
