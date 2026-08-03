from datetime import date, timedelta

import backend.db.services.pokemon_set_sealed_market_snapshot_service as snapshot_service
from backend.db.services.pokemon_set_sealed_market_snapshot_service import (
    MOVEMENT_WINDOWS,
    SNAPSHOT_CONTRACT_VERSION,
    build_snapshot,
    fingerprint,
    movement,
    normalize_daily_history,
    product_sort_key,
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
    assert movement(history, "1D")["actualStartDate"] == "2026-01-01"
    assert movement(history, "30D")["comparisonStatus"] == "since_first_available"
    assert movement(history, "lifetime")["actualStartDate"] == "2026-01-01"
    assert seven["fullWindowCoverage"] is True
    assert seven["coverageDays"] == 7


def test_all_windows_partial_coverage_and_unavailable_baseline():
    history = [
        {"date": "2025-01-01", "marketPrice": 100.0},
        {"date": "2025-06-30", "marketPrice": 120.0},
        {"date": "2025-12-31", "marketPrice": 150.0},
        {"date": "2026-01-01", "marketPrice": 160.0},
    ]
    assert tuple(MOVEMENT_WINDOWS) == ("1D", "7D", "30D", "3M", "6M", "1Y", "lifetime")
    for key in MOVEMENT_WINDOWS:
        assert movement(history, key)["status"] == "available"
    assert movement(history, "1D")["actualStartDate"] == "2025-12-31"
    assert movement(history, "7D")["actualStartDate"] == "2025-06-30"
    assert movement(history, "30D")["actualStartDate"] == "2025-06-30"
    assert movement(history, "3M")["actualStartDate"] == "2025-06-30"
    assert movement(history, "6M")["actualStartDate"] == "2025-06-30"
    assert movement(history, "1Y")["actualStartDate"] == "2025-01-01"
    assert movement(history, "lifetime")["actualStartDate"] == "2025-01-01"
    partial = movement(history[-2:], "1Y")
    assert partial["comparisonStatus"] == "since_first_available"
    assert partial["isSinceFirstAvailable"] is True
    assert partial["fullWindowCoverage"] is False
    unavailable = movement(history[-1:], "1D")
    assert unavailable["comparisonStatus"] == "baseline_unavailable"
    assert "amount" not in unavailable


def test_one_day_uses_previous_distinct_observed_date_and_known_prices():
    history = normalize_daily_history([
        {"id": 1, "sealed_product_id": 10, "market_price": 430.00, "captured_at": "2026-08-01T09:00:00Z"},
        {"id": 2, "sealed_product_id": 10, "market_price": 431.72, "captured_at": "2026-08-01T10:00:00Z"},
        {"id": 3, "sealed_product_id": 10, "market_price": 422.60, "captured_at": "2026-08-02T09:00:00Z"},
    ])
    one_day = movement(history, "1D")
    assert one_day["actualStartDate"] == "2026-08-01"
    assert one_day["endDate"] == "2026-08-02"
    assert one_day["amount"] == -9.12
    assert one_day["percent"] == -2.11


def test_exact_fixed_windows_and_insufficient_long_windows():
    end = date(2026, 8, 2)
    history = [
        {"date": (end - timedelta(days=days)).isoformat(), "marketPrice": price}
        for days, price in [(90, 100), (30, 110), (7, 120), (0, 130)]
    ]
    for key in ("7D", "30D", "3M"):
        result = movement(history, key)
        assert result["fullWindowCoverage"] is True
        assert result["coverageDays"] == snapshot_service.WINDOW_DAYS[key]
    for key in ("6M", "1Y"):
        result = movement(history, key)
        assert result["status"] == "available"
        assert result["fullWindowCoverage"] is False
        assert result["comparisonStatus"] == "since_first_available"


def test_equal_price_tie_break_fingerprint_and_empty_set():
    products = [
        {"id": 20, "set_id": "s", "name": "Set Elite Trainer Box [B]", "product_type": "box"},
        {"id": 21, "set_id": "s", "name": "Set Booster Box", "product_type": "box"},
    ]
    observations = [
        {**rows()[0], "sealed_product_id": 20},
        {**rows()[0], "id": 9, "sealed_product_id": 21},
    ]
    result = build_snapshot({"id": "s", "canonical_key": "set", "name": "Set"}, products, observations)
    # Both observe the same price, so ordering falls through to the label
    # tie-breaker ("B" before "Booster Box") rather than to product family.
    assert result["payload_json"]["defaultProductId"] == "20"
    assert [item["sealedProductId"] for item in result["payload_json"]["products"]] == ["20", "21"]
    assert fingerprint("s", products, observations) == fingerprint("s", list(reversed(products)), list(reversed(observations)))
    assert SNAPSHOT_CONTRACT_VERSION == "pokemon-set-sealed-market-v3"
    assert result["payload_json"]["meta"]["snapshotContractVersion"] == SNAPSHOT_CONTRACT_VERSION
    assert list(result["payload_json"]["products"][0]["movements"]) == list(MOVEMENT_WINDOWS)
    empty = build_snapshot({"id": "x", "canonical_key": "x", "name": "X"}, [], [])
    assert empty["payload_json"]["products"] == []
    assert empty["product_count"] == 0


def test_contract_version_changes_fingerprint(monkeypatch):
    products = [{"id": 10}]
    observations = [rows()[0]]
    current = fingerprint("s", products, observations)
    monkeypatch.setattr(snapshot_service, "SNAPSHOT_CONTRACT_VERSION", "pokemon-set-sealed-market-v1")
    assert fingerprint("s", products, observations) != current


def priced_observation(product_id: int, obs_id: int, price: float):
    return {
        "id": obs_id,
        "sealed_product_id": product_id,
        "market_price": price,
        "source": "TCGPLAYER",
        "currency": "USD",
        "captured_at": "2026-01-01T09:00:00Z",
    }


def test_products_and_default_follow_current_price_descending():
    # Ascended Heroes shape: the Pokemon Center ETB is worth far more than the
    # Booster Box that the old family-priority ordering put first.
    products = [
        {"id": 30, "set_id": "s", "name": "Set Booster Bundle", "product_type": "box"},
        {"id": 31, "set_id": "s", "name": "Set Pokemon Center Elite Trainer Box", "product_type": "box"},
        {"id": 32, "set_id": "s", "name": "Set Booster Pack", "product_type": "pack"},
        {"id": 33, "set_id": "s", "name": "Set Elite Trainer Box", "product_type": "box"},
    ]
    observations = [
        priced_observation(30, 1, 80.38),
        priced_observation(31, 2, 422.60),
        priced_observation(32, 3, 6.75),
        priced_observation(33, 4, 169.41),
    ]
    payload = build_snapshot({"id": "s", "canonical_key": "set", "name": "Set"}, products, observations)["payload_json"]

    assert [item["currentPrice"] for item in payload["products"]] == [422.60, 169.41, 80.38, 6.75]
    assert [item["sealedProductId"] for item in payload["products"]] == ["31", "33", "30", "32"]

    # The default is the head of that order, so the API contract and the UI agree.
    assert payload["defaultProductId"] == "31"
    assert payload["defaultProductId"] == payload["products"][0]["sealedProductId"]

    # Standard and Pokemon Center ETBs stay separate, and nothing is dropped.
    families = [item["productFamily"] for item in payload["products"]]
    assert families == ["pokemon_center_elite_trainer_box", "elite_trainer_box", "booster_bundle", "booster_pack"]
    assert len(payload["products"]) == 4


def test_missing_prices_sort_last_without_nan_ordering():
    # A product with no usable observation is dropped before sorting, so the
    # sort key is exercised directly for the missing/invalid price cases.
    items = [
        {"sealedProductId": "a", "currentPrice": None, "variantLabel": None, "productFamilyLabel": "Booster Box", "name": "Booster Box"},
        {"sealedProductId": "b", "currentPrice": 12.5, "variantLabel": None, "productFamilyLabel": "Booster Pack", "name": "Booster Pack"},
        {"sealedProductId": "c", "currentPrice": float("nan"), "variantLabel": None, "productFamilyLabel": "ETB", "name": "ETB"},
        {"sealedProductId": "d", "currentPrice": "not-a-number", "variantLabel": None, "productFamilyLabel": "Bundle", "name": "Bundle"},
        {"sealedProductId": "e", "currentPrice": 0, "variantLabel": None, "productFamilyLabel": "Sleeved", "name": "Sleeved"},
    ]
    ordered = [item["sealedProductId"] for item in sorted(items, key=product_sort_key)]
    assert ordered[0] == "b"
    assert set(ordered[1:]) == {"a", "c", "d", "e"}
    # Deterministic among the unpriced tail rather than NaN-dependent.
    assert ordered == [item["sealedProductId"] for item in sorted(list(reversed(items)), key=product_sort_key)]


def test_product_sort_key_is_numeric_not_lexical():
    cheap = {"sealedProductId": "cheap", "currentPrice": 80.38, "variantLabel": None, "productFamilyLabel": "Bundle", "name": "Bundle"}
    dear = {"sealedProductId": "dear", "currentPrice": 422.60, "variantLabel": None, "productFamilyLabel": "PC ETB", "name": "PC ETB"}
    assert product_sort_key(dear) < product_sort_key(cheap)
    # String prices are coerced, not compared as text.
    assert product_sort_key({**dear, "currentPrice": "422.60"}) < product_sort_key({**cheap, "currentPrice": "80.38"})
