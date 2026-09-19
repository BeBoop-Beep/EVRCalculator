from backend.scripts.freeze_ebay_active_ask_v1 import estimate, replay


def test_frozen_replay_is_deterministic_and_never_prices_thin_cards():
    first = replay()
    second = replay()
    assert first["fingerprint"] == second["fingerprint"]
    assert first["depth_counts"] == {"SUFFICIENT": 8, "THIN": 2, "INSUFFICIENT": 20}
    assert sum(r["estimated_price"] is not None for r in first["rows"]) == 6
    assert all(r["estimated_price"] is None for r in first["rows"] if r["depth_state"] != "SUFFICIENT")


def test_item_and_seller_deduplication_and_five_seller_gate():
    target = {"canonical_card_id": "card", "card_variant_id": "variant"}
    rows = [{"state": "ENGLISH_PRICE_ELIGIBLE", "item_id": f"item{i}",
             "seller_key_sha256": f"seller{i}", "landed_ask_usd": f"{i}.00"} for i in range(1, 6)]
    rows += [dict(rows[0]), {**rows[0], "item_id": "second-from-seller1", "landed_ask_usd": "99.00"}]
    enough = estimate(target, rows, "2026-09-19", "run")
    assert enough["eligible_listing_count"] == 6
    assert enough["distinct_seller_count"] == 5
    assert enough["estimated_price"] == "2.00"
    assert estimate(target, rows[:-3], "2026-09-19", "run")["estimated_price"] is None
