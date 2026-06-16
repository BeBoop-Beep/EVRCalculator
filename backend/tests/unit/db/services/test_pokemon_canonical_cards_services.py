from backend.db.services import pokemon_set_cards_service
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

    def in_(self, field, values):
        self.in_filters.append((field, list(values)))
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
