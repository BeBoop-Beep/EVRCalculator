import backend.db.services.pokemon_set_sealed_market_snapshot_service as snapshot_service
from backend.db.services.pokemon_set_sealed_market_snapshot_service import (
    MOVEMENT_WINDOWS,
    SNAPSHOT_CONTRACT_VERSION,
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
    assert movement(history, "1D")["actualStartDate"] == "2026-01-01"
    assert movement(history, "30D")["comparisonStatus"] == "since_first_available"
    assert movement(history, "lifetime")["actualStartDate"] == "2026-01-01"


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
    unavailable = movement(history[-1:], "1D")
    assert unavailable["comparisonStatus"] == "baseline_unavailable"
    assert "amount" not in unavailable


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
    assert SNAPSHOT_CONTRACT_VERSION == "pokemon-set-sealed-market-v2"
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
