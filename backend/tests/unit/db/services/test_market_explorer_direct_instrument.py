from types import SimpleNamespace

import pytest

from backend.db.services.market_explorer_direct_instrument import (
    DirectInstrumentError,
    read_direct_instrument,
)

CARD = "11111111-1111-1111-1111-111111111111"
SEALED = "22222222-2222-2222-2222-222222222222"


class Query:
    def __init__(self, rows):
        self.rows = [dict(row) for row in rows]

    def select(self, *_args): return self
    def eq(self, key, value):
        self.rows = [row for row in self.rows if str(row.get(key)) == str(value)]
        return self
    def order(self, key):
        self.rows.sort(key=lambda row: str(row.get(key) or ""))
        return self
    def limit(self, count):
        self.rows = self.rows[:count]
        return self
    def execute(self): return SimpleNamespace(data=self.rows)


class Client:
    def __init__(self):
        self.tables = {
            "pokemon_market_explorer_card_current_metadata": [{
                "card_variant_id": CARD, "canonical_card_id": "c1", "card_name": "Gengar",
                "set_id": "s1", "rarity": "Rare Holo", "image_url": "img",
            }],
            "pokemon_market_explorer_card_daily_states_v2_shadow": [
                {"card_variant_id": CARD, "market_date": "2026-09-01", "market_price": 20, "set_id": "s1"},
                {"card_variant_id": CARD, "market_date": "2026-09-02", "market_price": 22, "set_id": "s1"},
            ],
            "sets": [{"id": "s1", "name": "Fossil"}],
            "pokemon_market_explorer_sealed_current_metadata_v1": [{
                "sealed_product_id": SEALED, "name": "Booster Box", "set_name": "Fossil",
                "product_family": "booster_box", "image_small_url": "sealed-img",
            }],
            "sealed_product_price_observations": [
                {"sealed_product_id": SEALED, "captured_at": "2026-09-01T01:00:00Z", "market_price": 100, "currency": None, "id": 1},
                {"sealed_product_id": SEALED, "captured_at": "2026-09-01T23:00:00Z", "market_price": 110, "currency": "usd", "id": 2},
                {"sealed_product_id": SEALED, "captured_at": "2026-09-02T01:00:00Z", "market_price": 90, "currency": "CAD", "id": 3},
            ],
        }

    def table(self, name): return Query(self.tables.get(name, []))


def test_card_is_one_exact_enumerable_series_with_server_index():
    result = read_direct_instrument(Client(), "cards", CARD)
    assert result["instrumentId"] == CARD and result["seriesKey"] == f"direct:cards:{CARD}"
    assert result["constituents"]["totalCount"] == 1
    assert result["constituents"]["topConstituents"][0]["cardVariantId"] == CARD
    assert [point["indexValue"] for point in result["history"]] == pytest.approx([100.0, 110.0])


def test_sealed_uses_latest_usd_observation_per_day_and_legacy_null_currency():
    result = read_direct_instrument(Client(), "sealed", SEALED)
    assert len(result["history"]) == 1
    assert result["currentPrice"] == 110
    assert result["constituents"]["topConstituents"][0]["sealedProductId"] == SEALED


@pytest.mark.parametrize("asset,identity,code", [
    ("graded", CARD, "DIRECT_INSTRUMENT_ASSET_UNSUPPORTED"),
    ("cards", "not-a-uuid", "DIRECT_INSTRUMENT_ID_INVALID"),
    ("cards", "33333333-3333-3333-3333-333333333333", "DIRECT_INSTRUMENT_UNKNOWN"),
])
def test_direct_read_fails_closed(asset, identity, code):
    with pytest.raises(DirectInstrumentError) as error:
        read_direct_instrument(Client(), asset, identity)
    assert error.value.code == code
