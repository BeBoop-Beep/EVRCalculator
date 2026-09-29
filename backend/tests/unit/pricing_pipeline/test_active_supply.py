from __future__ import annotations

import pytest

from backend.pricing_pipeline.active_supply import normalize_listing, seller_hash, summarize

KEY = "fixed-test-key-that-is-at-least-thirty-two-bytes"


def test_seller_hash_is_stable_keyed_and_never_raw():
    first = seller_hash("seller-123", KEY)
    assert first == seller_hash("seller-123", KEY)
    assert first != seller_hash("seller-123", KEY + "x")
    assert first.startswith("hmac-sha256:v1:")
    assert "seller-123" not in first


def test_listing_normalization_preserves_prices_timestamps_and_safe_reputation():
    row = normalize_listing({
        "id": "listing-1", "price": "10.00", "shipping_price": "1.25",
        "quantity": 3, "currency": "usd", "printing": "Holofoil",
        "condition": "Near Mint", "language": "English",
        "updated_at": "2026-09-29T12:00:00Z", "snapshot_at": "2026-09-29T12:01:00Z",
        "seller": {"id": "private-id", "name": "private-name", "rating": "99.8", "sales_count": 44},
    }, rank=1, seller_hash_key=KEY)
    assert row["item_price"] == "10.00"
    assert row["shipping_price"] == "1.25"
    assert row["landed_price"] == "11.25"
    assert row["listing_updated_at"].endswith("Z")
    assert row["provider_snapshot_at"].endswith("Z")
    encoded = str(row)
    assert "private-id" not in encoded and "private-name" not in encoded
    assert row["source_payload"]["seller_sales_count"] == 44


def test_summary_is_explicitly_captured_depth_only_math():
    listings = [
        {"landed_price": "10.00", "quantity": 3, "source_seller_id": "a"},
        {"landed_price": "12.00", "quantity": 1, "source_seller_id": "b"},
        {"landed_price": "14.00", "quantity": 2, "source_seller_id": "a"},
    ]
    out = summarize(listings)
    assert out["captured_listing_count"] == 3
    assert out["captured_quantity"] == 6
    assert out["distinct_seller_count"] == 2
    assert out["seller_concentration_hhi"] == "0.722222"
    assert out["lowest_landed_ask"] == "10.00"
    assert out["median_landed_ask"] == "12.00"
    assert out["landed_ask_mad"] == "2.00"
    assert out["price_depth_bands"]["within_25pct"] == 4


def test_missing_or_weak_seller_identity_fails_closed():
    with pytest.raises(ValueError, match="seller identity missing"):
        normalize_listing({"id": 1, "price": 1}, rank=1, seller_hash_key=KEY)
    with pytest.raises(ValueError, match="at least 32"):
        seller_hash("seller", "short")
