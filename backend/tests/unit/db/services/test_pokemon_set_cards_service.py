"""Tests for the slim, paginated cards-page contract
(get_pokemon_set_cards_page_snapshot_payload), which lives in
pokemon_public_snapshot_service.py alongside the other split contracts
(overview/top-chase/movers) added in earlier phases."""

import json

from backend.db.services import pokemon_public_snapshot_service, pokemon_set_market_service


class _Result:
    def __init__(self, data):
        self.data = data


class _Query:
    def __init__(self, table_name, handlers):
        self.table_name = table_name
        self.handlers = handlers
        self.select_fields = None
        self.eq_filters = []
        self.limit_value = None

    def select(self, fields):
        self.select_fields = fields
        return self

    def eq(self, field, value):
        self.eq_filters.append((field, value))
        return self

    def limit(self, value):
        self.limit_value = value
        return self

    def execute(self):
        return _Result(self.handlers[self.table_name](self))


class _Client:
    def __init__(self, handlers):
        self.handlers = handlers

    def table(self, table_name):
        return _Query(table_name, self.handlers)


_TEST_UUID = "9f6d9d63-df3d-4e63-9a4d-2f7ce9f5a111"


def _make_card(index, **overrides):
    delta = (index % 5) - 2  # -2..2, gives both positive and negative movers
    card = {
        "id": f"card-{index}",
        "name": f"Chase Card {index:03d}",
        "set_id": _TEST_UUID,
        "set_name": "Test Set",
        "pokemon_tcg_api_card_id": f"api-{index}",
        "card_number": str(index + 1),
        "number": str(index + 1),
        "printed_number": str(index + 1),
        "rarity": "Rare" if index % 2 == 0 else "Common",
        "supertype": "Pokémon",
        "subtypes": [],
        "national_pokedex_numbers": [],
        "image_small_url": f"https://images.example.com/{index}-small.png",
        "image_large_url": f"https://images.example.com/{index}-large.png",
        "market_price": round(10.0 + index, 2),
        "marketPrice": round(10.0 + index, 2),
        "tcgplayer_product_id": None,
        "currentPrice": round(10.0 + index, 2),
        "current_price": round(10.0 + index, 2),
        "change30dAmount": delta,
        "change_30d_amount": delta,
        "change30dPercent": round(delta * 1.5, 2),
        "change_30d_percent": round(delta * 1.5, 2),
        "movementScore": delta,
        "movement_score": delta,
        "movementLabel": "heating_up" if delta > 0 else ("cooling_off" if delta < 0 else "flat"),
        "movement_label": "heating_up" if delta > 0 else ("cooling_off" if delta < 0 else "flat"),
        "enoughHistory": True,
        "enough_history": True,
        "confidence": "medium",
        "cardDesirabilityScore": round(50 + index * 0.1, 2),
        "card_desirability_score": round(50 + index * 0.1, 2),
        "pokemonDesirabilityScore": round(50 + index * 0.1, 2),
        "pokemon_desirability_score": round(50 + index * 0.1, 2),
        "treatmentScore": 1.2,
        "treatment_score": 1.2,
        "scarcityScore": 0.8,
        "scarcity_score": 0.8,
        "adjustedCardAppealScore": 40.5,
        "adjusted_card_appeal_score": 40.5,
        "pullRate": 0.01,
        "pull_rate": 0.01,
        "pullRateSource": "pullRate",
        "pull_rate_source": "pullRate",
        "setValueShare": 0.02,
        "set_value_share": 0.02,
        "isHitEligible": index % 3 == 0,
        "is_hit_eligible": index % 3 == 0,
        "linkedPokemonName": "Pikachu",
        "linked_pokemon_name": "Pikachu",
        "linkedPokemon": [
            {
                "pokemonName": "Pikachu",
                "pokemon_name": "Pikachu",
                "pokemonReferenceId": 25,
                "pokemon_reference_id": 25,
                "desirabilityScore": 90.0,
                "desirability_score": 90.0,
                "contributionWeight": 1.0,
                "contribution_weight": 1.0,
            }
        ],
        "linked_pokemon": [
            {
                "pokemonName": "Pikachu",
                "pokemon_name": "Pikachu",
                "pokemonReferenceId": 25,
                "pokemon_reference_id": 25,
                "desirabilityScore": 90.0,
                "desirability_score": 90.0,
                "contributionWeight": 1.0,
                "contribution_weight": 1.0,
            }
        ],
        "movement30d": {
            "currentPrice": round(10.0 + index, 2),
            "current_price": round(10.0 + index, 2),
            "changeAmount": delta,
            "change_amount": delta,
            "changePercent": round(delta * 1.5, 2),
            "change_percent": round(delta * 1.5, 2),
            "score": delta,
            "movementScore": delta,
            "movement_score": delta,
            "label": "heating_up",
            "movementLabel": "heating_up",
            "movement_label": "heating_up",
            "enoughHistory": True,
            "enough_history": True,
            "confidence": "medium",
        },
    }
    card.update(overrides)
    return card


def _cards_row(count, **overrides):
    row = {
        "set_id": _TEST_UUID,
        "cards_json": [_make_card(index) for index in range(count)],
        "payload_json": {
            "cards": [],
            "cardDesirabilityValidation": {"cards": [{"junk": "must never appear in the page contract"}]},
            "cardAppealMarketPriceCorrelation": {"n": 999},
        },
        "card_count": count,
        "updated_at": "2026-06-30T00:00:00+00:00",
    }
    row.update(overrides)
    return row


def _find_snake_case_keys(value, path=""):
    found = []
    if isinstance(value, dict):
        for key, inner in value.items():
            label = f"{path}.{key}" if path else str(key)
            if isinstance(key, str) and "_" in key:
                found.append(label)
            found.extend(_find_snake_case_keys(inner, label))
    elif isinstance(value, list):
        for index, item in enumerate(value):
            found.extend(_find_snake_case_keys(item, f"{path}[{index}]"))
    return found


def test_cards_page_payload_returns_only_requested_page(monkeypatch):
    row = _cards_row(150)
    client = _Client({"pokemon_set_cards_snapshot_latest": lambda _q: [row]})
    monkeypatch.setattr(pokemon_public_snapshot_service, "public_read_client", client)

    payload = pokemon_public_snapshot_service.get_pokemon_set_cards_page_snapshot_payload(_TEST_UUID, page=2, page_size=60)

    assert len(payload["cards"]) == 60
    assert payload["cards"][0]["name"] == "Chase Card 060"
    assert payload["pagination"]["page"] == 2
    assert payload["pagination"]["pageSize"] == 60
    assert payload["pagination"]["totalCards"] == 150
    assert payload["pagination"]["totalPages"] == 3
    assert payload["pagination"]["hasNextPage"] is True
    assert payload["pagination"]["hasPreviousPage"] is True


def test_cards_page_payload_last_page_has_no_next_page(monkeypatch):
    row = _cards_row(150)
    client = _Client({"pokemon_set_cards_snapshot_latest": lambda _q: [row]})
    monkeypatch.setattr(pokemon_public_snapshot_service, "public_read_client", client)

    payload = pokemon_public_snapshot_service.get_pokemon_set_cards_page_snapshot_payload(_TEST_UUID, page=3, page_size=60)

    assert len(payload["cards"]) == 30
    assert payload["pagination"]["hasNextPage"] is False
    assert payload["pagination"]["hasPreviousPage"] is True


def test_cards_page_payload_page_size_max_clamp(monkeypatch):
    row = _cards_row(200)
    client = _Client({"pokemon_set_cards_snapshot_latest": lambda _q: [row]})
    monkeypatch.setattr(pokemon_public_snapshot_service, "public_read_client", client)

    payload = pokemon_public_snapshot_service.get_pokemon_set_cards_page_snapshot_payload(_TEST_UUID, page_size=999)

    assert payload["pagination"]["pageSize"] == 120
    assert len(payload["cards"]) == 120


def test_cards_page_payload_defaults_page_size_to_60(monkeypatch):
    row = _cards_row(10)
    client = _Client({"pokemon_set_cards_snapshot_latest": lambda _q: [row]})
    monkeypatch.setattr(pokemon_public_snapshot_service, "public_read_client", client)

    payload = pokemon_public_snapshot_service.get_pokemon_set_cards_page_snapshot_payload(_TEST_UUID, page_size=None)

    assert payload["pagination"]["pageSize"] == 60


def test_cards_page_payload_search_query_filters_by_name(monkeypatch):
    row = _cards_row(20)
    client = _Client({"pokemon_set_cards_snapshot_latest": lambda _q: [row]})
    monkeypatch.setattr(pokemon_public_snapshot_service, "public_read_client", client)

    payload = pokemon_public_snapshot_service.get_pokemon_set_cards_page_snapshot_payload(_TEST_UUID, query="005")

    assert payload["pagination"]["totalCards"] == 1
    assert payload["cards"][0]["name"] == "Chase Card 005"


def test_cards_page_payload_rarity_filter(monkeypatch):
    row = _cards_row(20)
    client = _Client({"pokemon_set_cards_snapshot_latest": lambda _q: [row]})
    monkeypatch.setattr(pokemon_public_snapshot_service, "public_read_client", client)

    payload = pokemon_public_snapshot_service.get_pokemon_set_cards_page_snapshot_payload(_TEST_UUID, rarity="Rare")

    assert payload["pagination"]["totalCards"] == 10
    assert all(card["rarity"] == "Rare" for card in payload["cards"])
    assert sorted(payload["filters"]["availableRarities"]) == ["Common", "Rare"]


def test_cards_page_payload_movement_filter_heating_and_cooling(monkeypatch):
    row = _cards_row(20)
    client = _Client({"pokemon_set_cards_snapshot_latest": lambda _q: [row]})
    monkeypatch.setattr(pokemon_public_snapshot_service, "public_read_client", client)

    heating = pokemon_public_snapshot_service.get_pokemon_set_cards_page_snapshot_payload(_TEST_UUID, movement_filter="heating")
    cooling = pokemon_public_snapshot_service.get_pokemon_set_cards_page_snapshot_payload(_TEST_UUID, movement_filter="cooling")

    assert all(card["change30dAmount"] > 0 for card in heating["cards"])
    assert all(card["change30dAmount"] < 0 for card in cooling["cards"])
    assert heating["pagination"]["totalCards"] > 0
    assert cooling["pagination"]["totalCards"] > 0


def test_cards_page_payload_30d_gainers_sort_orders_by_change_descending(monkeypatch):
    row = _cards_row(20)
    client = _Client({"pokemon_set_cards_snapshot_latest": lambda _q: [row]})
    monkeypatch.setattr(pokemon_public_snapshot_service, "public_read_client", client)

    payload = pokemon_public_snapshot_service.get_pokemon_set_cards_page_snapshot_payload(_TEST_UUID, sort="30d-gainers", page_size=20)

    amounts = [card["change30dAmount"] for card in payload["cards"]]
    assert amounts == sorted(amounts, reverse=True)


def test_cards_page_payload_movement_sort_overrides_sort(monkeypatch):
    row = _cards_row(20)
    client = _Client({"pokemon_set_cards_snapshot_latest": lambda _q: [row]})
    monkeypatch.setattr(pokemon_public_snapshot_service, "public_read_client", client)

    payload = pokemon_public_snapshot_service.get_pokemon_set_cards_page_snapshot_payload(
        _TEST_UUID, sort="set-number", movement_sort="30d-decliners", page_size=20
    )

    amounts = [card["change30dAmount"] for card in payload["cards"]]
    assert amounts == sorted(amounts)
    assert payload["filters"]["movementSort"] == "30d-decliners"


def test_cards_page_30d_sorts_reliable_full_windows_before_partial_deltas(monkeypatch):
    reliable = _make_card(
        1,
        change30dAmount=1.0,
        change30dPercent=5.0,
        movement30d={"reliable": True, "fullWindowCoverage": True, "changeAmount": 1.0, "changePercent": 5.0},
    )
    partial = _make_card(
        2,
        change30dAmount=20.0,
        change30dPercent=100.0,
        movement30d={"reliable": False, "fullWindowCoverage": False, "isPartialWindow": True, "changeAmount": 20.0, "changePercent": 100.0},
    )
    row = _cards_row(2)
    row["cards_json"] = [partial, reliable]
    monkeypatch.setattr(
        pokemon_public_snapshot_service,
        "public_read_client",
        _Client({"pokemon_set_cards_snapshot_latest": lambda _q: [row]}),
    )

    gainers = pokemon_public_snapshot_service.get_pokemon_set_cards_page_snapshot_payload(
        _TEST_UUID, movement_sort="30d-gainers", page_size=20
    )["cards"]
    heating = pokemon_public_snapshot_service.get_pokemon_set_cards_page_snapshot_payload(
        _TEST_UUID, movement_sort="30d-gainers", movement_filter="heating", page_size=20
    )["cards"]

    assert [card["id"] for card in gainers] == [reliable["id"], partial["id"]]
    assert gainers[1]["movement30d"]["isPartialWindow"] is True
    assert gainers[1]["movement30d"]["fullWindowCoverage"] is False
    assert [card["id"] for card in heating] == [reliable["id"]]


def test_cards_page_payload_7d_movers_sort_is_global_and_paginated(monkeypatch):
    cards = [
        _make_card(index, change7dAmount=float(index), change7dPercent=float(index))
        for index in range(12)
    ]
    row = _cards_row(12)
    row["cards_json"] = cards
    monkeypatch.setattr(
        pokemon_public_snapshot_service,
        "public_read_client",
        _Client({"pokemon_set_cards_snapshot_latest": lambda _q: [row]}),
    )

    first = pokemon_public_snapshot_service.get_pokemon_set_cards_page_snapshot_payload(
        _TEST_UUID, movement_sort="7d-movers", page=1, page_size=5
    )
    second = pokemon_public_snapshot_service.get_pokemon_set_cards_page_snapshot_payload(
        _TEST_UUID, movement_sort="7d-movers", page=2, page_size=5
    )

    assert [card["change7dPercent"] for card in first["cards"]] == [11.0, 10.0, 9.0, 8.0, 7.0]
    assert [card["change7dPercent"] for card in second["cards"]] == [6.0, 5.0, 4.0, 3.0, 2.0]
    assert first["filters"]["movementWindow"] == "7D"


def test_cards_page_payload_7d_movers_filters_sign_and_sorts_missing_last(monkeypatch):
    cards = [
        _make_card(0, change7dAmount=5.0, change7dPercent=50.0),
        _make_card(1, change7dAmount=-4.0, change7dPercent=-40.0),
        _make_card(2, change7dAmount=3.0, change7dPercent=30.0),
        _make_card(3, change7dAmount=None, change7dPercent=None),
    ]
    row = _cards_row(4)
    row["cards_json"] = cards
    monkeypatch.setattr(
        pokemon_public_snapshot_service,
        "public_read_client",
        _Client({"pokemon_set_cards_snapshot_latest": lambda _q: [row]}),
    )

    all_cards = pokemon_public_snapshot_service.get_pokemon_set_cards_page_snapshot_payload(
        _TEST_UUID, movement_sort="7d-movers", page_size=20
    )["cards"]
    heating = pokemon_public_snapshot_service.get_pokemon_set_cards_page_snapshot_payload(
        _TEST_UUID, movement_sort="7d-movers", movement_filter="heating", page_size=20
    )["cards"]
    cooling = pokemon_public_snapshot_service.get_pokemon_set_cards_page_snapshot_payload(
        _TEST_UUID, movement_sort="7d-movers", movement_filter="cooling", page_size=20
    )["cards"]

    assert [card["id"] for card in all_cards] == ["card-0", "card-1", "card-2", "card-3"]
    assert [card["id"] for card in heating] == ["card-0", "card-2"]
    assert [card["id"] for card in cooling] == ["card-1"]


def test_cards_page_payload_7d_movers_ties_are_deterministic(monkeypatch):
    cards = [
        _make_card(9, change7dAmount=-1.0, change7dPercent=-25.0),
        _make_card(2, change7dAmount=1.0, change7dPercent=25.0),
    ]
    row = _cards_row(2)
    row["cards_json"] = cards
    monkeypatch.setattr(
        pokemon_public_snapshot_service,
        "public_read_client",
        _Client({"pokemon_set_cards_snapshot_latest": lambda _q: [row]}),
    )

    payload = pokemon_public_snapshot_service.get_pokemon_set_cards_page_snapshot_payload(
        _TEST_UUID, movement_sort="7d-movers", page_size=20
    )
    assert [card["id"] for card in payload["cards"]] == ["card-2", "card-9"]


def test_cards_snapshot_enrichment_keeps_7d_fields_distinct_from_30d():
    payload = {"cards": [{"id": "card-1", "change30dPercent": 99.0}], "meta": {}}
    movement_payload = {
        "window": "7D",
        "windowDays": 7,
        "movements": [
            {
                "cardId": "card-1",
                "currentPrice": 12.0,
                "change30dAmount": 2.0,
                "change30dPercent": 20.0,
                "enoughHistory": True,
            }
        ],
        "meta": {},
    }

    enriched = pokemon_public_snapshot_service.enrich_cards_payload_with_movements(
        payload, movement_payload, window="7D"
    )
    card = enriched["cards"][0]
    assert card["change7dAmount"] == 2.0
    assert card["change7dPercent"] == 20.0
    assert card["change30dPercent"] == 99.0


def test_cards_page_payload_default_sort_is_set_number(monkeypatch):
    row = _cards_row(20)
    client = _Client({"pokemon_set_cards_snapshot_latest": lambda _q: [row]})
    monkeypatch.setattr(pokemon_public_snapshot_service, "public_read_client", client)

    payload = pokemon_public_snapshot_service.get_pokemon_set_cards_page_snapshot_payload(_TEST_UUID, page_size=20)

    numbers = [int(card["cardNumber"]) for card in payload["cards"]]
    assert numbers == sorted(numbers)


def test_cards_page_payload_reads_cards_json_not_payload_json(monkeypatch):
    captured_queries = []

    def read_cards(query):
        captured_queries.append(query)
        return [_cards_row(5)]

    client = _Client({"pokemon_set_cards_snapshot_latest": read_cards})
    monkeypatch.setattr(pokemon_public_snapshot_service, "public_read_client", client)

    pokemon_public_snapshot_service.get_pokemon_set_cards_page_snapshot_payload(_TEST_UUID)

    assert len(captured_queries) == 1
    selected_fields = captured_queries[0].select_fields
    assert "cards_json" in selected_fields
    assert "payload_json" not in selected_fields


def test_cards_page_payload_excludes_payload_json_and_duplicate_aliases(monkeypatch):
    row = _cards_row(10)
    client = _Client({"pokemon_set_cards_snapshot_latest": lambda _q: [row]})
    monkeypatch.setattr(pokemon_public_snapshot_service, "public_read_client", client)

    payload = pokemon_public_snapshot_service.get_pokemon_set_cards_page_snapshot_payload(_TEST_UUID)

    assert "payload_json" not in payload
    assert "cardDesirabilityValidation" not in payload
    assert "cardAppealMarketPriceCorrelation" not in payload

    snake_case_hits = _find_snake_case_keys(payload["cards"])
    assert snake_case_hits == [], f"duplicate/legacy snake_case keys leaked into the cards page contract: {snake_case_hits}"
    # Sanity: the fixture genuinely has snake_case duplicates upstream, so this
    # assertion is only meaningful because the raw source data included them.
    assert any("_" in key for key in row["cards_json"][0].keys())


def test_cards_page_payload_serialized_size_is_under_250kb(monkeypatch):
    """Payload budget: a representative fixture of richly-enriched cards
    (movement + desirability + linked Pokemon), sliced to the default page
    size, must serialize under 250KB."""
    row = _cards_row(300)
    client = _Client({"pokemon_set_cards_snapshot_latest": lambda _q: [row]})
    monkeypatch.setattr(pokemon_public_snapshot_service, "public_read_client", client)

    payload = pokemon_public_snapshot_service.get_pokemon_set_cards_page_snapshot_payload(_TEST_UUID)

    serialized_bytes = len(json.dumps(payload, default=str).encode("utf-8"))
    assert serialized_bytes < 250_000, f"cards page payload was {serialized_bytes} bytes, over the 250KB budget"


def test_cards_page_payload_resolves_hyphenated_slug(monkeypatch):
    sets_rows = [
        {"id": "set-uuid-1", "name": "Prismatic Evolutions", "canonical_key": "prismaticEvolutions", "pokemon_api_set_id": "sv8pt5"}
    ]

    def read_sets(query):
        if query.eq_filters:
            field, value = query.eq_filters[-1]
            return [row for row in sets_rows if row.get(field) == value]
        return sets_rows

    row = _cards_row(5, set_id="set-uuid-1")
    client = _Client(
        {
            "sets": read_sets,
            "pokemon_set_cards_snapshot_latest": lambda _q: [row],
        }
    )
    monkeypatch.setattr(pokemon_public_snapshot_service, "public_read_client", client)
    monkeypatch.setattr(pokemon_set_market_service, "public_read_client", client)

    payload = pokemon_public_snapshot_service.get_pokemon_set_cards_page_snapshot_payload("prismatic-evolutions")

    assert payload["set"]["id"] == "set-uuid-1"
    assert payload["pagination"]["totalCards"] == 5


def test_cards_page_payload_missing_snapshot_returns_empty_fallback(monkeypatch):
    client = _Client({"pokemon_set_cards_snapshot_latest": lambda _q: []})
    monkeypatch.setattr(pokemon_public_snapshot_service, "public_read_client", client)

    payload = pokemon_public_snapshot_service.get_pokemon_set_cards_page_snapshot_payload(_TEST_UUID)

    assert payload["cards"] == []
    assert payload["pagination"]["totalCards"] == 0
    assert payload["pagination"]["page"] == 1
    assert "missing" in payload["meta"]["warnings"][0].lower()
