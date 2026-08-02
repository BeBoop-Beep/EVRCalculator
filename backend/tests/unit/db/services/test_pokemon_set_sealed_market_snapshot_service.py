from backend.db.services.pokemon_set_sealed_market_snapshot_service import (
    build_snapshot,
    fingerprint,
    movement,
    normalize_daily_history,
)


def rows():
    return [
        {"id": 1, "sealed_product_id": 10, "market_price": 100, "source": "TCGPLAYER", "currency": "USD", "captured_at": "2026-01-01T09:00:00Z"},
        {"id": 2, "sealed_product_id": 10, "market_price": 105, "source": "TCGPLAYER", "currency": "USD", "captured_at": "2026-01-01T11:00:00Z"},
        {"id": 3, "sealed_product_id": 10, "market_price": 110, "source": "TCGPLAYER", "currency": "USD", "captured_at": "2026-01-08T11:00:00Z"},
        {"id": 4, "sealed_product_id": 10, "market_price": 0, "source": "TCGPLAYER", "currency": "USD", "captured_at": "2026-01-09T11:00:00Z"},
    ]


def test_daily_normalization_and_movements():
    history = normalize_daily_history(rows())
    assert [point["marketPrice"] for point in history] == [105.0, 110.0]
    seven = movement(history, "7D")
    assert seven["status"] == "available"
    assert seven["amount"] == 5
    assert movement(history, "30D")["comparisonStatus"] == "baseline_unavailable"
    assert movement(history, "LT")["actualStartDate"] == "2026-01-01"


def test_default_priority_fingerprint_and_empty_set():
    products = [
        {"id": 20, "set_id": "s", "name": "Set Elite Trainer Box [B]", "product_type": "box"},
        {"id": 21, "set_id": "s", "name": "Set Booster Box", "product_type": "box"},
    ]
    observations = [
        {**rows()[0], "sealed_product_id": 20},
        {**rows()[0], "id": 9, "sealed_product_id": 21},
    ]
    result = build_snapshot({"id": "s", "canonical_key": "set", "name": "Set"}, products, observations)
    assert result["payload_json"]["defaultProductId"] == "21"
    assert fingerprint("s", products, observations) == fingerprint("s", list(reversed(products)), list(reversed(observations)))
    empty = build_snapshot({"id": "x", "canonical_key": "x", "name": "X"}, [], [])
    assert empty["payload_json"]["products"] == []
    assert empty["product_count"] == 0
