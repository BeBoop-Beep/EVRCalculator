import pytest
from postgrest.exceptions import APIError

from backend.db.services import pokemon_set_cards_service
from backend.db.services import pokemon_set_market_service
from backend.db.services import pokemon_sets_catalog_service


class _Result:
    def __init__(self, data):
        self.data = data


class _Query:
    def __init__(self, table_name, handlers, calls):
        self.table_name = table_name
        self.handlers = handlers
        self.calls = calls
        self.select_fields = None
        self.eq_filters = []
        self.in_filters = []
        self.gte_filters = []
        self.order_fields = []
        self.limit_value = None
        self.range_value = None
        self.single_mode = None

    def select(self, fields):
        self.select_fields = fields
        return self

    def eq(self, field, value):
        self.eq_filters.append((field, value))
        return self

    def ilike(self, field, value):
        self.eq_filters.append((field, value))
        return self

    def in_(self, field, values):
        self.in_filters.append((field, list(values)))
        return self

    def gte(self, field, value):
        self.gte_filters.append((field, value))
        return self

    def order(self, field, desc=False):
        self.order_fields.append((field, desc))
        return self

    def limit(self, value):
        self.limit_value = value
        return self

    def range(self, start, end):
        self.range_value = (start, end)
        return self

    def maybe_single(self):
        self.single_mode = "maybe_single"
        return self

    def execute(self):
        self.calls.append(self)
        payload = self.handlers[self.table_name](self)
        if self.single_mode == "maybe_single" and isinstance(payload, list):
            payload = payload[0] if payload else None
        return _Result(payload)


class _Client:
    def __init__(self, handlers):
        self.handlers = handlers
        self.calls = []

    def table(self, table_name):
        if table_name not in self.handlers:
            raise AssertionError(f"Unexpected table requested: {table_name}")
        return _Query(table_name, self.handlers, self.calls)


def test_sets_catalog_card_count_comes_from_canonical_cards(monkeypatch):
    handlers = {
        "tcgs": lambda _query: [{"id": "pokemon-tcg", "name": "Pokemon"}],
        "sets": lambda _query: [
            {
                "id": "set-1",
                "name": "Inflated Legacy Set",
                "canonical_key": "inflatedLegacySet",
                "tcg_id": "pokemon-tcg",
                "pokemon_api_set_id": "sv-test",
                "official_card_count": 999,
                "printed_total": 999,
                "total_cards": 999,
                "era_id": "era-1",
            },
            {
                "id": "set-2",
                "name": "No Canonical Yet",
                "canonical_key": "noCanonicalYet",
                "tcg_id": "pokemon-tcg",
                "pokemon_api_set_id": "sv-empty",
                "official_card_count": 123,
                "printed_total": 123,
                "total_cards": 123,
                "era_id": "era-1",
            },
        ],
        "pokemon_canonical_cards": lambda _query: [
            {"set_id": "set-1"},
            {"set_id": "set-1"},
        ],
        "eras": lambda _query: [{"id": "era-1", "name": "Test Era"}],
    }
    client = _Client(handlers)
    monkeypatch.setattr(pokemon_sets_catalog_service, "public_read_client", client)

    payload = pokemon_sets_catalog_service.get_pokemon_sets_catalog_payload()

    counts_by_id = {row["id"]: row["card_count"] for row in payload["sets"]}
    assert counts_by_id == {"set-1": 2, "set-2": 0}
    assert payload["meta"]["sources"]["pokemon_canonical_cards"] == "OK"


def test_sets_catalog_transient_tcg_lookup_returns_503_without_variant_fanout(monkeypatch):
    calls = []

    def fail(query):
        calls.append(query)
        raise APIError({"message": "schema cache unavailable", "code": "PGRST002", "hint": None, "details": None})

    monkeypatch.setattr(pokemon_sets_catalog_service, "public_read_client", _Client({"tcgs": fail}))

    with pytest.raises(pokemon_sets_catalog_service.PokemonSetsCatalogError) as raised:
        pokemon_sets_catalog_service.get_pokemon_sets_catalog_payload()

    assert raised.value.status_code == 503
    assert raised.value.code == "POKEMON_CATALOG_TEMPORARILY_UNAVAILABLE"
    assert raised.value.retry_after_seconds == 30
    assert len(calls) == 1


def test_sets_catalog_successful_empty_tcg_lookup_remains_404(monkeypatch):
    client = _Client({"tcgs": lambda _query: []})
    monkeypatch.setattr(pokemon_sets_catalog_service, "public_read_client", client)

    with pytest.raises(pokemon_sets_catalog_service.PokemonSetsCatalogError) as raised:
        pokemon_sets_catalog_service.get_pokemon_sets_catalog_payload()

    assert raised.value.status_code == 404
    assert raised.value.code == "POKEMON_TCG_NOT_FOUND"
    assert len(client.calls) == 3


def test_set_cards_payload_reads_canonical_checklist_rows(monkeypatch):
    handlers = {
        "sets": lambda _query: [
            {
                "id": "set-1",
                "name": "Canonical Set",
                "canonical_key": "canonicalSet",
                "pokemon_api_set_id": "sv-test",
            }
        ],
        "pokemon_canonical_cards": lambda _query: [
            {
                "id": "card-row-2",
                "set_id": "set-1",
                "pokemon_tcg_api_card_id": "sv-test-2",
                "name": "Beta",
                "number": "2",
                "printed_number": "2/100",
                "rarity": "Rare",
                "supertype": "Pokemon",
                "subtypes": ["Basic"],
                "national_pokedex_numbers": [25],
                "image_small_url": "https://img.test/beta-small.png",
                "image_large_url": "https://img.test/beta-large.png",
            },
            {
                "id": "card-row-1",
                "set_id": "set-1",
                "pokemon_tcg_api_card_id": "sv-test-1",
                "name": "Alpha",
                "number": "1",
                "printed_number": "1/100",
                "rarity": "Common",
                "supertype": "Pokemon",
                "subtypes": ["Stage 1"],
                "national_pokedex_numbers": [1],
                "image_small_url": "https://img.test/alpha-small.png",
                "image_large_url": "https://img.test/alpha-large.png",
            },
        ],
    }
    client = _Client(handlers)
    monkeypatch.setattr(pokemon_set_cards_service, "public_read_client", client)

    payload = pokemon_set_cards_service.get_pokemon_set_cards_payload("set-1")

    assert payload["set"]["pokemon_api_set_id"] == "sv-test"
    assert payload["meta"]["sources"]["cards"] == "pokemon_canonical_cards"
    assert payload["meta"]["dedupe"]["removed_duplicates"] == 0
    assert [card["name"] for card in payload["cards"]] == ["Alpha", "Beta"]
    assert payload["cards"][0] == {
        "id": "card-row-1",
        "name": "Alpha",
        "set_id": "set-1",
        "set_name": "Canonical Set",
        "pokemon_tcg_api_card_id": "sv-test-1",
        "card_number": "1",
        "number": "1",
        "printed_number": "1/100",
        "rarity": "Common",
        "supertype": "Pokemon",
        "subtypes": ["Stage 1"],
        "national_pokedex_numbers": [1],
        "image_small_url": "https://img.test/alpha-small.png",
        "image_large_url": "https://img.test/alpha-large.png",
        "market_price": None,
        "tcgplayer_product_id": None,
    }


def test_top_market_cards_use_latest_market_prices_not_simulation(monkeypatch):
    handlers = {
        "sets": lambda _query: [
            {
                "id": "set-1",
                "name": "Market Set",
                "canonical_key": "marketSet",
                "pokemon_api_set_id": "sv-market",
            }
        ],
        "pokemon_canonical_cards": lambda _query: [
            {
                "id": "canonical-1",
                "set_id": "set-1",
                "pokemon_tcg_api_card_id": "api-1",
                "name": "Alpha",
                "number": "1",
                "printed_number": "1/100",
                "rarity": "Common",
                "image_small_url": "https://img.test/alpha.png",
                "image_large_url": None,
            },
            {
                "id": "canonical-2",
                "set_id": "set-1",
                "pokemon_tcg_api_card_id": "api-2",
                "name": "Beta",
                "number": "2",
                "printed_number": "2/100",
                "rarity": "Rare",
                "image_small_url": "https://img.test/beta.png",
                "image_large_url": None,
            },
            {
                "id": "canonical-3",
                "set_id": "set-1",
                "pokemon_tcg_api_card_id": "api-3",
                "name": "Gamma",
                "number": "3",
                "printed_number": "3/100",
                "rarity": "Uncommon",
                "image_small_url": None,
                "image_large_url": None,
            },
        ],
        "cards": lambda _query: [
            {"id": "card-1", "set_id": "set-1", "name": "Alpha", "rarity": "Common", "card_number": "1/100", "pokemon_tcg_api_id": "api-1"},
            {"id": "card-2", "set_id": "set-1", "name": "Beta", "rarity": "Rare", "card_number": "2/100", "pokemon_tcg_api_id": "api-2"},
            {"id": "card-3", "set_id": "set-1", "name": "Gamma", "rarity": "Uncommon", "card_number": "3/100", "pokemon_tcg_api_id": "api-3"},
        ],
        "card_variants": lambda _query: [
            {"id": "variant-1", "card_id": "card-1", "pokemon_tcg_api_id": "api-1", "image_small_url": None, "image_large_url": None},
            {"id": "variant-2", "card_id": "card-2", "pokemon_tcg_api_id": "api-2", "image_small_url": None, "image_large_url": None},
            {"id": "variant-3", "card_id": "card-3", "pokemon_tcg_api_id": "api-3", "image_small_url": None, "image_large_url": None},
        ],
        "conditions": lambda _query: [{"id": "condition-nm", "name": "Near Mint"}],
        "card_market_usd_latest_by_condition": lambda _query: [
            {
                "variant_id": "variant-1",
                "condition_id": "condition-nm",
                "market_price": 12.5,
                "source": "TCGPLAYER",
                "captured_at": "2026-06-15T12:00:00+00:00",
            },
            {
                "variant_id": "variant-2",
                "condition_id": "condition-nm",
                "market_price": 125.75,
                "source": "TCGPLAYER",
                "captured_at": "2026-06-16T12:00:00+00:00",
            },
            {
                "variant_id": "variant-3",
                "condition_id": "condition-nm",
                "market_price": 0,
                "source": "TCGPLAYER",
                "captured_at": "2026-06-16T12:00:00+00:00",
            },
        ],
    }
    client = _Client(handlers)
    monkeypatch.setattr(pokemon_set_market_service, "public_read_client", client)

    payload = pokemon_set_market_service.get_pokemon_set_top_market_cards_payload("set-1", limit=10, days=30)

    assert [card["name"] for card in payload["cards"]] == ["Beta", "Alpha"]
    assert payload["cards"][0]["cardId"] == "canonical-2"
    assert payload["cards"][0]["estimatedMarketPrice"] == 125.75
    assert payload["cards"][0]["priceUpdatedAt"] == "2026-06-16T12:00:00+00:00"
    assert payload["cards"][0]["source"] == "TCGPLAYER"
    assert payload["cards"][0]["deltas"] == {
        "1D": None,
        "7D": None,
        "30D": None,
        "3M": None,
        "6M": None,
        "1Y": None,
        "lifetime": None,
    }
    assert "simulation_input_cards_with_near_mint_price" not in {call.table_name for call in client.calls}


def test_top_market_cards_prefer_latest_simulation_input_prices(monkeypatch):
    handlers = {
        "sets": lambda _query: [
            {
                "id": "set-1",
                "name": "Market Set",
                "canonical_key": "marketSet",
                "pokemon_api_set_id": "sv-market",
            }
        ],
        "pokemon_canonical_cards": lambda _query: [],
        "calculation_runs": lambda _query: [
            {
                "id": "run-1",
                "created_at": "2026-06-16T12:00:00+00:00",
                "target_type": "set",
                "target_id": "set-1",
                "valuation_method": "combined",
            }
        ],
        "simulation_input_cards": lambda _query: [
            {
                "card_id": "card-1",
                "card_variant_id": "variant-1",
                "condition_id": "condition-nm",
                "card_name": "Alpha",
                "rarity": "Common",
                "rarity_bucket": "Common",
                "price_source": "simulation",
                "price_used": 10,
                "captured_at": "2026-06-16T12:00:00+00:00",
            },
            {
                "card_id": "card-2",
                "card_variant_id": "variant-2",
                "condition_id": "condition-nm",
                "card_name": "Beta",
                "rarity": "Rare",
                "rarity_bucket": "Rare",
                "price_source": "simulation",
                "price_used": 125.75,
                "captured_at": "2026-06-16T12:00:00+00:00",
            },
        ],
        "card_variants": lambda _query: [
            {"id": "variant-1", "card_id": "card-1", "pokemon_tcg_api_id": "api-1", "image_small_url": None, "image_large_url": None},
            {"id": "variant-2", "card_id": "card-2", "pokemon_tcg_api_id": "api-2", "image_small_url": "https://img.test/beta.png", "image_large_url": None},
        ],
        "cards": lambda _query: [
            {"id": "card-1", "set_id": "set-1", "name": "Alpha", "rarity": "Common", "card_number": "1/100", "pokemon_tcg_api_id": "api-1", "image_small_url": None, "image_large_url": None},
            {"id": "card-2", "set_id": "set-1", "name": "Beta", "rarity": "Rare", "card_number": "2/100", "pokemon_tcg_api_id": "api-2", "image_small_url": None, "image_large_url": None},
        ],
        "card_variant_price_observations": lambda _query: [
            {
                "card_variant_id": "variant-1",
                "condition_id": "condition-nm",
                "market_price": 100,
                "source": "TCGPLAYER",
                "captured_at": "2026-06-15T08:00:00+00:00",
                "captured_date": "2026-06-15",
            },
            {
                "card_variant_id": "variant-2",
                "condition_id": "condition-nm",
                "market_price": 125.75,
                "source": "TCGPLAYER",
                "captured_at": "2026-06-15T08:00:00+00:00",
                "captured_date": "2026-06-15",
            },
        ],
    }
    client = _Client(handlers)
    monkeypatch.setattr(pokemon_set_market_service, "public_read_client", client)

    payload = pokemon_set_market_service.get_pokemon_set_top_market_cards_payload("set-1", limit=10, days=30)

    assert [card["name"] for card in payload["cards"]] == ["Beta", "Alpha"]
    assert payload["cards"][0]["cardVariantId"] == "variant-2"
    assert payload["cards"][0]["estimatedMarketPrice"] == 125.75
    assert len(payload["cards"][0]["priceHistory"]) == 30
    assert payload["cards"][0]["priceHistory"][0]["date"] == "2026-05-17"
    assert payload["cards"][0]["priceHistory"][0]["marketPrice"] is None
    assert payload["cards"][0]["priceHistory"][-1]["date"] == "2026-06-15"
    assert payload["cards"][0]["priceHistory"][-1]["marketPrice"] == 125.75
    assert payload["cards"][0]["historyDiagnostics"]["latestHistoryPrice"] == 125.75
    assert payload["meta"]["asOfDate"] == "2026-06-15"
    assert payload["meta"]["windowStart"] == "2026-05-17"
    assert payload["meta"]["windowEnd"] == "2026-06-15"
    assert payload["meta"]["windowDays"] == 30
    assert payload["meta"]["priceBasis"] == "latest combined simulation_input_cards.price_used with matching simulation_input_cards.condition_id for trends"


def test_set_value_history_uses_daily_market_history_table(monkeypatch):
    handlers = {
        "sets": lambda _query: [
            {
                "id": "set-1",
                "name": "Market Set",
                "canonical_key": "marketSet",
                "pokemon_api_set_id": "sv-market",
            },
        ],
        "pokemon_set_value_daily_history": lambda query: (
            [{"snapshot_date": "2026-06-18"}]
            if query.select_fields == "snapshot_date"
            else [
                {
                    "snapshot_date": "2026-06-15",
                    "set_value": 30.25,
                    "priced_card_count": 2,
                    "total_card_count": 100,
                    "source": "card_variant_price_observations_near_mint_latest_as_of_day",
                    "created_at": "2026-06-15T08:00:00+00:00",
                    "updated_at": "2026-06-15T08:00:00+00:00",
                },
                {
                    "snapshot_date": "2026-06-17",
                    "set_value": 90.75,
                    "priced_card_count": 3,
                    "total_card_count": 100,
                    "source": "card_variant_price_observations_near_mint_latest_as_of_day",
                    "created_at": "2026-06-17T08:00:00+00:00",
                    "updated_at": "2026-06-17T08:00:00+00:00",
                },
                {
                    "snapshot_date": "2026-06-18",
                    "set_value": 95.50,
                    "priced_card_count": 3,
                    "total_card_count": 100,
                    "source": "card_variant_price_observations_near_mint_latest_as_of_day",
                    "created_at": "2026-06-18T08:00:00+00:00",
                    "updated_at": "2026-06-18T08:00:00+00:00",
                },
            ]
        ),
    }
    client = _Client(handlers)
    monkeypatch.setattr(pokemon_set_market_service, "public_read_client", client)

    payload = pokemon_set_market_service.get_pokemon_set_value_history_payload("set-1", days=4)

    assert payload["history"][:2] == [
            {
                "date": "2026-06-15",
                "valueScope": "standard",
                "value_scope": "standard",
                "setValue": 30.25,
            "set_value": 30.25,
            "cardCountPriced": 2,
            "card_count_priced": 2,
            "totalCardCount": 100,
            "total_card_count": 100,
            "source": "card_variant_price_observations_near_mint_latest_as_of_day",
            "provider": "card_variant_price_observations_near_mint_latest_as_of_day",
            "calculationRunId": None,
            "calculation_run_id": None,
            "createdAt": "2026-06-15T08:00:00+00:00",
            "created_at": "2026-06-15T08:00:00+00:00",
            "updatedAt": "2026-06-15T08:00:00+00:00",
            "updated_at": "2026-06-15T08:00:00+00:00",
            "isCarriedForward": False,
            "is_carried_forward": False,
            "sourceDate": "2026-06-15",
            "source_date": "2026-06-15",
        },
            {
                "date": "2026-06-16",
                "valueScope": "standard",
                "value_scope": "standard",
                "setValue": 30.25,
            "set_value": 30.25,
            "cardCountPriced": 2,
            "card_count_priced": 2,
            "totalCardCount": 100,
            "total_card_count": 100,
            "source": "card_variant_price_observations_near_mint_latest_as_of_day",
            "provider": "card_variant_price_observations_near_mint_latest_as_of_day",
            "calculationRunId": None,
            "calculation_run_id": None,
            "createdAt": "2026-06-15T08:00:00+00:00",
            "created_at": "2026-06-15T08:00:00+00:00",
            "updatedAt": "2026-06-15T08:00:00+00:00",
            "updated_at": "2026-06-15T08:00:00+00:00",
            "isCarriedForward": True,
            "is_carried_forward": True,
            "sourceDate": "2026-06-15",
            "source_date": "2026-06-15",
        },
    ]
    assert payload["history"][2]["date"] == "2026-06-17"
    assert payload["history"][2]["setValue"] == 90.75
    assert payload["history"][3]["date"] == "2026-06-18"
    assert payload["history"][3]["setValue"] == 95.5
    assert payload["meta"]["asOfDate"] == "2026-06-18"
    assert payload["meta"]["windowStart"] == "2026-06-15"
    assert payload["meta"]["windowEnd"] == "2026-06-18"
    assert payload["meta"]["windowDays"] == 4
    assert payload["meta"]["valueScope"] == "standard"
    assert payload["meta"]["valueField"] == "pokemon_set_value_daily_history.set_value"
    assert payload["meta"]["warnings"] == []


def test_set_value_history_returns_empty_when_snapshots_unavailable(monkeypatch):
    handlers = {
        "sets": lambda _query: [
            {
                "id": "set-1",
                "name": "Market Set",
                "canonical_key": "marketSet",
                "pokemon_api_set_id": "sv-market",
            }
        ],
        "pokemon_set_value_daily_history": lambda _query: [],
    }
    client = _Client(handlers)
    monkeypatch.setattr(pokemon_set_market_service, "public_read_client", client)

    payload = pokemon_set_market_service.get_pokemon_set_value_history_payload("set-1", days=365)

    assert payload["history"] == []
    assert "No daily market set value history is available for this set." in payload["meta"]["warnings"]
