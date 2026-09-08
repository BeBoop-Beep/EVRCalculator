import pytest

from backend.db.services.personal_market_source_service import (
    WISHLIST_UNAVAILABLE_REASON,
    adapt_portfolio_value_history,
    personal_market_identity,
    public_cache_payload_allowed,
    wishlist_source,
)


OWNER_A = "11111111-1111-1111-1111-111111111111"
OWNER_B = "22222222-2222-2222-2222-222222222222"
ROW = {
    "snapshot_date": "2026-09-08",
    "portfolio_value": 1000,
    "cards_value": 400,
    "sealed_value": 350,
    "graded_value": 250,
    "cards_count": 10,
    "sealed_count": 3,
    "graded_count": 2,
}


def adapt(partition="total"):
    return adapt_portfolio_value_history([ROW], authenticated_user_id=OWNER_A, asset_partition=partition)


def test_identity_includes_private_user_scope_without_exposing_user_id():
    a = personal_market_identity(OWNER_A, "portfolio", "total")
    b = personal_market_identity(OWNER_B, "portfolio", "total")
    assert a != b and a.startswith("private:personal:")
    assert OWNER_A not in a


def test_user_a_cannot_request_user_b_portfolio():
    with pytest.raises(PermissionError):
        adapt_portfolio_value_history([ROW], authenticated_user_id=OWNER_A, requested_user_id=OWNER_B)


def test_signed_out_personal_market_is_denied():
    with pytest.raises(PermissionError):
        adapt_portfolio_value_history([ROW], authenticated_user_id=None)


@pytest.mark.parametrize("partition,column", [
    ("total", "portfolio_value"), ("raw", "cards_value"),
    ("sealed", "sealed_value"), ("graded", "graded_value"),
])
def test_portfolio_partition_maps_canonical_value(partition, column):
    assert adapt(partition)["points"][0]["value"] == ROW[column]


def test_partition_counts_remain_metadata():
    assert adapt("raw")["points"][0]["count"] == ROW["cards_count"]
    assert adapt("total")["points"][0]["counts"] == {"raw": 10, "sealed": 3, "graded": 2}


def test_value_history_is_never_called_market_return_or_index():
    result = adapt()
    assert result["seriesKind"] == "value"
    assert result["isMarketIndex"] is False
    assert result["isMarketReturn"] is False
    assert result["holdingsFlowNeutralized"] is False


def test_wishlist_is_unavailable_without_published_authority_and_has_no_data():
    result = wishlist_source().to_dict()
    assert result["available"] is False
    assert result["reason"] == WISHLIST_UNAVAILABLE_REASON
    assert "points" not in result and "payload" not in result


def test_personal_identity_cannot_collide_with_public_query_fingerprint():
    assert personal_market_identity(OWNER_A, "portfolio", "total").startswith("private:")
    assert not public_cache_payload_allowed(adapt())


def test_wishlist_payload_is_also_rejected_by_public_cache_guard():
    payload = {"key": "anything", "source": wishlist_source().to_dict()}
    assert public_cache_payload_allowed(payload) is False


def test_ordinary_public_query_payload_remains_cacheable():
    assert public_cache_payload_allowed({"key": "query:abc", "source": {"sourceType": "query"}})
