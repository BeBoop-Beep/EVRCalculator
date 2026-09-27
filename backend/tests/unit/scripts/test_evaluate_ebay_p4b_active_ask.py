from backend.scripts.evaluate_ebay_p4b_active_ask import evaluate_card


def row(item_id, seller, price):
    return {"item_id": item_id, "seller_key_sha256": seller,
            "landed_ask_usd": str(price), "state": "ENGLISH_PRICE_ELIGIBLE"}


TARGET = {"canonical_card_id": "c", "card_variant_id": "v", "era_id": "e",
          "price_band": "mid", "tcgplayer_market_price": 12}


def test_seller_dedup_and_low_tail_estimator():
    rows = [row("a1", "a", 10), row("a2", "a", 11), row("b", "b", 12),
            row("c", "c", 13), row("d", "d", 20), row("e", "e", 1000)]
    result = evaluate_card(TARGET, rows)
    assert result["eligible_listing_count"] == 6
    assert result["seller_count"] == 5
    assert result["candidates"]["low3_seller_median"] == "12"
    assert result["candidates"]["all_listing_median"] != result["candidates"]["all_seller_median"]
    assert result["depth_state"] == "SUFFICIENT"
    assert result["source_estimate_usd"] == "12"
    assert result["drop_highest_relative_change"] == 0
    assert result["calculation_fingerprint"] == evaluate_card(TARGET, list(reversed(rows)))["calculation_fingerprint"]


def test_depth_one_two_three_five_and_missing_variant():
    rows = [row(str(i), str(i), 10 + i) for i in range(5)]
    assert evaluate_card(TARGET, rows[:1])["depth_state"] == "INSUFFICIENT"
    assert evaluate_card(TARGET, rows[:2])["depth_state"] == "INSUFFICIENT"
    assert evaluate_card(TARGET, rows[:3])["depth_state"] == "THIN"
    assert evaluate_card(TARGET, rows)["depth_state"] == "SUFFICIENT"
    assert evaluate_card(dict(TARGET, card_variant_id=None), rows)["source_estimate_usd"] is None


def test_disappearing_ask_sensitivity_and_source_provenance():
    rows = [row(str(i), str(i), price) for i, price in enumerate((10, 12, 13, 14, 15))]
    result = evaluate_card(TARGET, rows)
    assert result["max_leave_one_seller_out_relative_change"] > 0
    assert result["provenance"]["estimator_version"]
    assert len(result["provenance"]["inputs"]) == 5
    assert {x["listing_item_id"] for x in result["provenance"]["inputs"]} == {str(i) for i in range(5)}
