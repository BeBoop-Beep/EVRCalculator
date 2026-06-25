from backend.db.services import pokemon_public_snapshot_service


class _Result:
    def __init__(self, data):
        self.data = data


class _Query:
    def __init__(self, table_name, handlers):
        self.table_name = table_name
        self.handlers = handlers
        self.eq_filters = []
        self.in_filters = []
        self.gte_filters = []
        self.lte_filters = []
        self.gt_filters = []
        self.lt_filters = []
        self.limit_value = None

    def select(self, _fields):
        return self

    def in_(self, _field, _values):
        self.in_filters.append((_field, list(_values)))
        return self

    def eq(self, _field, _value):
        self.eq_filters.append((_field, _value))
        return self

    def gte(self, _field, _value):
        self.gte_filters.append((_field, _value))
        return self

    def lte(self, _field, _value):
        self.lte_filters.append((_field, _value))
        return self

    def gt(self, _field, _value):
        self.gt_filters.append((_field, _value))
        return self

    def lt(self, _field, _value):
        self.lt_filters.append((_field, _value))
        return self

    def limit(self, _value):
        self.limit_value = _value
        return self

    def order(self, _field, desc=False):
        return self

    def execute(self):
        return _Result(self.handlers[self.table_name](self))


class _Client:
    def __init__(self, handlers):
        self.handlers = handlers

    def table(self, table_name):
        return _Query(table_name, self.handlers)


def _daily_top_chase_rows(count, *, start_date="2025-06-25", variant_id="variant-1", start_price=10.0):
    from datetime import date, timedelta

    start = date.fromisoformat(start_date)
    return [
        {
            "snapshot_date": (start + timedelta(days=index)).isoformat(),
            "card_variant_id": variant_id,
            "market_price": start_price + index,
            "source_date": (start + timedelta(days=index)).isoformat(),
        }
        for index in range(count)
    ]


def _raw_observation_rows(count, *, start_date="2026-04-11", variant_id="variant-1", start_price=10.0):
    from datetime import date, timedelta

    start = date.fromisoformat(start_date)
    return [
        {
            "captured_at": f"{(start + timedelta(days=index)).isoformat()}T12:00:00+00:00",
            "card_variant_id": variant_id,
            "condition_id": pokemon_public_snapshot_service.TOP_CHASE_NEAR_MINT_CONDITION_ID,
            "market_price": start_price + index,
        }
        for index in range(count)
    ]


def test_enrich_cards_payload_with_desirability_adds_card_validation_fields(monkeypatch):
    client = _Client(
        {
            "pokemon_card_desirability_links": lambda _query: [
                {
                    "pokemon_canonical_card_id": "card-1",
                    "pokemon_reference_id": 6,
                    "pokedex_number": 6,
                    "contribution_weight": 1.0,
                    "match_confidence": "exact",
                    "is_hit_eligible": True,
                }
            ],
            "pokemon_desirability_composite_scores": lambda _query: [
                {
                    "pokemon_reference_id": 6,
                    "pokedex_number": 6,
                    "pokemon_name": "Charizard",
                    "desirability_score": 92.0,
                }
            ],
        }
    )
    monkeypatch.setattr(pokemon_public_snapshot_service, "public_read_client", client)

    payload = {
        "cards": [
            {"id": "card-1", "name": "Charizard ex", "rarity": "Special Illustration Rare", "marketPrice": 120.0},
            {"id": "card-2", "name": "Professor's Research", "rarity": "Uncommon", "marketPrice": 0.5},
        ],
        "meta": {},
    }

    enriched = pokemon_public_snapshot_service.enrich_cards_payload_with_desirability(payload)
    first_card = enriched["cards"][0]
    trainer_card = enriched["cards"][1]

    assert first_card["pokemonDesirabilityScore"] == 92.0
    assert first_card["treatmentScore"] == 96.0
    assert first_card["adjustedCardAppealScore"] is not None
    assert first_card["isHitEligible"] is True
    assert trainer_card["adjustedCardAppealScore"] is None
    assert enriched["meta"]["cardDesirability"]["linkedPokemonCards"] == 1
    assert enriched["meta"]["cardDesirability"]["excludedNonPokemonCards"] == 1
    assert enriched["cardDesirabilityValidation"]["cards"][0]["pokemonName"] == "Charizard"


def test_market_dashboard_missing_snapshot_relation_uses_live_fallback(monkeypatch):
    client = _Client(
        {
            "sets": lambda _query: [
                {
                    "id": "set-1",
                    "name": "Known Set",
                    "canonical_key": "knownSet",
                    "pokemon_api_set_id": "sv-known",
                }
            ],
            "pokemon_set_market_dashboard_snapshot_latest": lambda _query: (_ for _ in ()).throw(
                Exception('relation "pokemon_set_market_dashboard_snapshot_latest" does not exist 42P01')
            ),
        }
    )
    monkeypatch.setattr(pokemon_public_snapshot_service, "public_read_client", client)
    monkeypatch.setattr(
        pokemon_public_snapshot_service,
        "get_pokemon_set_value_history_payload",
        lambda set_id, days, value_scope: {
            "history": [{"date": "2026-06-01", "setValue": 123.45}],
            "meta": {"warnings": []},
        },
    )
    monkeypatch.setattr(
        pokemon_public_snapshot_service,
        "get_pokemon_set_top_market_cards_payload",
        lambda set_id, limit, days: {
            "set": {"id": set_id, "name": "Known Set"},
            "cards": [],
            "meta": {"warnings": []},
        },
    )

    payload = pokemon_public_snapshot_service.get_pokemon_set_market_dashboard_snapshot_payload("set-1", window="30D")

    assert payload["setValueHistoriesByScope"]["standard"][0]["setValue"] == 123.45
    assert payload["meta"]["snapshot"]["source"] == "live_fallback_missing_pokemon_set_market_dashboard_snapshot_latest"


def test_market_dashboard_snapshot_normalizes_30d_window(monkeypatch):
    captured_filters = []

    def read_dashboard(query):
        captured_filters.append(list(query.eq_filters))
        return [
            {
                "set_id": "set-1",
                "window_key": "30d",
                "latest_market_date": "2026-06-01",
                "updated_at": "2026-06-02T00:00:00+00:00",
                "payload_json": {
                    "set": {"id": "set-1", "name": "Known Set"},
                    "window": "30d",
                    "window_key": "30d",
                    "setValueHistoriesByScope": {"standard": [{"date": "2026-06-01", "setValue": 321.0}]},
                    "topChaseCards": [],
                    "meta": {},
                },
            }
        ]

    client = _Client(
        {
            "sets": lambda _query: [
                {
                    "id": "set-1",
                    "name": "Known Set",
                    "canonical_key": "knownSet",
                    "pokemon_api_set_id": "sv-known",
                }
            ],
            "pokemon_set_market_dashboard_snapshot_latest": read_dashboard,
        }
    )
    monkeypatch.setattr(pokemon_public_snapshot_service, "public_read_client", client)

    payload = pokemon_public_snapshot_service.get_pokemon_set_market_dashboard_snapshot_payload("set-1", window="30D")

    assert ("window_key", "30d") in captured_filters[0]
    assert payload["window_key"] == "30d"
    assert payload["meta"]["snapshot"]["window"] == "30d"


def test_market_dashboard_snapshot_normalizes_365d_window(monkeypatch):
    captured_filters = []

    def read_dashboard(query):
        captured_filters.append(list(query.eq_filters))
        return [
            {
                "set_id": "set-1",
                "window_key": "365d",
                "latest_market_date": "2026-06-01",
                "updated_at": "2026-06-02T00:00:00+00:00",
                "payload_json": {
                    "set": {"id": "set-1", "name": "Known Set"},
                    "window": "365d",
                    "window_key": "365d",
                    "setValueHistoriesByScope": {"standard": [{"date": "2026-06-01", "setValue": 321.0}]},
                    "topChaseCards": [],
                    "meta": {},
                },
            }
        ]

    client = _Client(
        {
            "sets": lambda _query: [
                {
                    "id": "set-1",
                    "name": "Known Set",
                    "canonical_key": "knownSet",
                    "pokemon_api_set_id": "sv-known",
                }
            ],
            "pokemon_set_market_dashboard_snapshot_latest": read_dashboard,
        }
    )
    monkeypatch.setattr(pokemon_public_snapshot_service, "public_read_client", client)

    payload = pokemon_public_snapshot_service.get_pokemon_set_market_dashboard_snapshot_payload("set-1", window="365D")

    assert ("window_key", "365d") in captured_filters[0]
    assert payload["window_key"] == "365d"
    assert payload["meta"]["snapshot"]["window"] == "365d"


def test_market_dashboard_snapshot_hydrates_empty_top_chase_histories_from_raw_observations(monkeypatch):
    history_queries = []

    def read_dashboard(_query):
        return [
            {
                "set_id": "set-1",
                "window_key": "365d",
                "latest_market_date": "2026-06-02",
                "updated_at": "2026-06-03T00:00:00+00:00",
                "top_chase_card_histories_json": {},
                "payload_json": {
                    "set": {"id": "set-1", "name": "Known Set"},
                    "window": "365d",
                    "window_key": "365d",
                    "setValueHistoriesByScope": {"standard": [{"date": "2026-06-02", "setValue": 321.0}]},
                    "topChaseCards": [
                        {
                            "cardId": "card-1",
                            "cardVariantId": "variant-1",
                            "name": "Chase Card",
                            "imageUrl": "https://example.test/card.png",
                            "marketPrice": 12.0,
                            "deltas": {"30D": None},
                        }
                    ],
                    "topChaseCardHistories": {},
                    "top_chase_card_histories": {},
                    "meta": {},
                },
            }
        ]

    def read_history(query):
        history_queries.append(query)
        return [
            {
                "captured_at": "2026-06-01T09:00:00+00:00",
                "card_variant_id": "variant-1",
                "market_price": 10.0,
            },
            {
                "captured_at": "2026-06-02T09:00:00+00:00",
                "card_variant_id": "variant-1",
                "market_price": 11.0,
            },
            {
                "captured_at": "2026-06-02T18:00:00+00:00",
                "card_variant_id": "variant-1",
                "market_price": 12.0,
            },
        ]

    client = _Client(
        {
            "sets": lambda _query: [
                {
                    "id": "set-1",
                    "name": "Known Set",
                    "canonical_key": "knownSet",
                    "pokemon_api_set_id": "sv-known",
                }
            ],
            "pokemon_set_market_dashboard_snapshot_latest": read_dashboard,
            "card_variant_price_observations": read_history,
        }
    )
    monkeypatch.setattr(pokemon_public_snapshot_service, "public_read_client", client)

    payload = pokemon_public_snapshot_service.get_pokemon_set_market_dashboard_snapshot_payload("set-1", window="365D")

    expected_history = [
        {
            "date": "2026-06-01",
            "marketPrice": 10.0,
            "market_price": 10.0,
            "sourceDate": "2026-06-01",
            "source_date": "2026-06-01",
            "isObserved": True,
            "is_observed": True,
        },
        {
            "date": "2026-06-02",
            "marketPrice": 12.0,
            "market_price": 12.0,
            "sourceDate": "2026-06-02",
            "source_date": "2026-06-02",
            "isObserved": True,
            "is_observed": True,
        },
    ]

    assert payload["topChaseCardHistories"]["variant-1"] == expected_history
    assert payload["top_chase_card_histories"]["variant-1"] == expected_history
    assert payload["topChaseCards"][0]["priceHistory"] == expected_history
    assert payload["topChaseCards"][0]["price_history"] == expected_history
    assert payload["topChaseCards"][0]["marketPrice"] == 12.0
    assert payload["topChaseCards"][0]["imageUrl"] == "https://example.test/card.png"
    assert ("card_variant_id", ["variant-1"]) in history_queries[0].in_filters
    assert ("condition_id", pokemon_public_snapshot_service.TOP_CHASE_NEAR_MINT_CONDITION_ID) in history_queries[0].eq_filters
    assert ("market_price", 0) in history_queries[0].gt_filters
    assert ("captured_at", "2025-06-03") in history_queries[0].gte_filters
    assert ("captured_at", "2026-06-03") in history_queries[0].lt_filters
    assert payload["meta"]["topChaseHistorySource"] == "card_variant_price_observations"
    assert payload["meta"]["topChaseHistorySourceWindowDays"] == 365
    assert payload["meta"]["topChaseHistoryMinPoints"] == 2
    assert payload["meta"]["topChaseHistoryMaxPoints"] == 2
    assert payload["meta"]["topChaseHistoryFirstObservedDate"] == "2026-06-01"
    assert payload["meta"]["topChaseHistoryLatestObservedDate"] == "2026-06-02"
    assert payload["meta"]["topChaseHistoryHydratedFromDailyTable"] is False


def test_market_dashboard_snapshot_uses_75_raw_points_instead_of_365_synthetic_top_chase_rows(monkeypatch):
    observation_queries = []
    daily_queries = []
    stale_history = [
        {
            "date": row["snapshot_date"],
            "marketPrice": row["market_price"],
            "market_price": row["market_price"],
            "sourceDate": row["source_date"],
            "source_date": row["source_date"],
        }
        for row in _daily_top_chase_rows(365)
    ]

    def read_dashboard(_query):
        return [
            {
                "set_id": "set-1",
                "window_key": "365d",
                "latest_market_date": "2026-06-24",
                "updated_at": "2026-06-24T00:00:00+00:00",
                "top_chase_card_histories_json": {"variant-1": stale_history},
                "payload_json": {
                    "set": {"id": "set-1", "name": "Known Set"},
                    "window": "365d",
                    "window_key": "365d",
                    "topChaseCards": [
                        {
                            "cardId": "card-1",
                            "cardVariantId": "variant-1",
                            "name": "Chase Card",
                            "marketPrice": 374.0,
                            "priceHistory": stale_history,
                            "price_history": stale_history,
                        }
                    ],
                    "topChaseCardHistories": {"variant-1": stale_history},
                    "meta": {},
                },
            }
        ]

    def read_daily_history(query):
        daily_queries.append(query)
        return _daily_top_chase_rows(365)

    def read_observations(query):
        observation_queries.append(query)
        return _raw_observation_rows(75)

    client = _Client(
        {
            "sets": lambda _query: [{"id": "set-1", "name": "Known Set", "canonical_key": "knownSet"}],
            "pokemon_set_market_dashboard_snapshot_latest": read_dashboard,
            "pokemon_set_top_chase_card_daily_history": read_daily_history,
            "card_variant_price_observations": read_observations,
        }
    )
    monkeypatch.setattr(pokemon_public_snapshot_service, "public_read_client", client)

    payload = pokemon_public_snapshot_service.get_pokemon_set_market_dashboard_snapshot_payload("set-1", window="365D")
    history = payload["topChaseCards"][0]["priceHistory"]

    assert len(history) == 75
    assert history[0]["date"] == "2026-04-11"
    assert history[-1]["date"] == "2026-06-24"
    assert payload["topChaseCardHistories"]["variant-1"] == history
    assert daily_queries == []
    assert ("captured_at", "2025-06-25") in observation_queries[0].gte_filters
    assert ("captured_at", "2026-06-25") in observation_queries[0].lt_filters
    assert payload["meta"]["topChaseHistorySource"] == "card_variant_price_observations"
    assert payload["meta"]["topChaseHistorySourceWindowDays"] == 365
    assert payload["meta"]["topChaseHistoryMinPoints"] == 75
    assert payload["meta"]["topChaseHistoryMaxPoints"] == 75
    assert payload["meta"]["topChaseHistoryFirstObservedDate"] == "2026-04-11"
    assert payload["meta"]["topChaseHistoryLatestObservedDate"] == "2026-06-24"
    assert payload["meta"]["topChaseHistoryHydratedFromDailyTable"] is False


def test_market_dashboard_snapshot_returns_no_top_chase_points_before_first_raw_observation(monkeypatch):
    def read_dashboard(_query):
        return [
            {
                "set_id": "set-1",
                "window_key": "365d",
                "latest_market_date": "2026-06-24",
                "updated_at": "2026-06-24T00:00:00+00:00",
                "top_chase_card_histories_json": {"variant-1": _daily_top_chase_rows(365)},
                "payload_json": {
                    "set": {"id": "set-1", "name": "Known Set"},
                    "window": "365d",
                    "window_key": "365d",
                    "topChaseCards": [{"cardId": "card-1", "cardVariantId": "variant-1", "name": "Chase Card"}],
                    "topChaseCardHistories": {},
                    "meta": {},
                },
            }
        ]

    client = _Client(
        {
            "sets": lambda _query: [{"id": "set-1", "name": "Known Set", "canonical_key": "knownSet"}],
            "pokemon_set_market_dashboard_snapshot_latest": read_dashboard,
            "card_variant_price_observations": lambda _query: _raw_observation_rows(75),
        }
    )
    monkeypatch.setattr(pokemon_public_snapshot_service, "public_read_client", client)

    payload = pokemon_public_snapshot_service.get_pokemon_set_market_dashboard_snapshot_payload("set-1", window="365D")
    history = payload["topChaseCards"][0]["priceHistory"]

    assert history[0]["date"] == "2026-04-11"
    assert all(point["date"] >= "2026-04-11" for point in history)
    assert not any(point["date"] < "2026-04-11" for point in history)


def test_market_dashboard_top_chase_hydration_uses_365_day_observation_window_for_30d_request(monkeypatch):
    history_queries = []

    def read_dashboard(_query):
        return [
            {
                "set_id": "set-1",
                "window_key": "30d",
                "latest_market_date": "2026-06-24",
                "updated_at": "2026-06-24T00:00:00+00:00",
                "top_chase_card_histories_json": {},
                "payload_json": {
                    "set": {"id": "set-1", "name": "Known Set"},
                    "window": "30d",
                    "window_key": "30d",
                    "topChaseCards": [
                        {
                            "cardId": "card-1",
                            "cardVariantId": "variant-1",
                            "name": "Chase Card",
                            "marketPrice": 374.0,
                        }
                    ],
                    "topChaseCardHistories": {},
                    "meta": {},
                },
            }
        ]

    def read_history(query):
        history_queries.append(query)
        return _raw_observation_rows(365, start_date="2025-06-25")

    client = _Client(
        {
            "sets": lambda _query: [{"id": "set-1", "name": "Known Set", "canonical_key": "knownSet"}],
            "pokemon_set_market_dashboard_snapshot_latest": read_dashboard,
            "card_variant_price_observations": read_history,
        }
    )
    monkeypatch.setattr(pokemon_public_snapshot_service, "public_read_client", client)

    payload = pokemon_public_snapshot_service.get_pokemon_set_market_dashboard_snapshot_payload("set-1", window="30D")

    assert payload["window_key"] == "30d"
    assert len(payload["topChaseCards"][0]["priceHistory"]) == 365
    assert ("captured_at", "2025-06-25") in history_queries[0].gte_filters
    assert ("captured_at", "2026-06-25") in history_queries[0].lt_filters
    assert payload["meta"]["topChaseHistorySourceWindowDays"] == 365


def test_market_dashboard_live_fallback_keeps_set_value_when_top_cards_fail(monkeypatch):
    client = _Client(
        {
            "sets": lambda _query: [
                {
                    "id": "set-1",
                    "name": "Known Set",
                    "canonical_key": "knownSet",
                    "pokemon_api_set_id": "sv-known",
                }
            ],
            "pokemon_set_market_dashboard_snapshot_latest": lambda _query: [],
        }
    )
    monkeypatch.setattr(pokemon_public_snapshot_service, "public_read_client", client)
    monkeypatch.setattr(
        pokemon_public_snapshot_service,
        "get_pokemon_set_value_history_payload",
        lambda set_id, days, value_scope: {
            "history": [{"date": "2026-06-01", "setValue": 123.45}],
            "meta": {"warnings": []},
        },
    )
    monkeypatch.setattr(
        pokemon_public_snapshot_service,
        "get_pokemon_set_top_market_cards_payload",
        lambda set_id, limit, days: (_ for _ in ()).throw(Exception("top cards unavailable")),
    )

    payload = pokemon_public_snapshot_service.get_pokemon_set_market_dashboard_snapshot_payload("set-1", window="30D")

    assert payload["window_key"] == "30d"
    assert payload["setValueHistoriesByScope"]["standard"][0]["setValue"] == 123.45
    assert payload["topChaseCards"] == []
    assert payload["meta"]["snapshot"]["source"] == "live_fallback_missing_pokemon_set_market_dashboard_snapshot_latest"


def test_market_dashboard_live_fallback_keeps_top_cards_when_set_value_fails(monkeypatch):
    client = _Client(
        {
            "sets": lambda _query: [
                {
                    "id": "set-1",
                    "name": "Known Set",
                    "canonical_key": "knownSet",
                    "pokemon_api_set_id": "sv-known",
                }
            ],
            "pokemon_set_market_dashboard_snapshot_latest": lambda _query: [],
        }
    )
    monkeypatch.setattr(pokemon_public_snapshot_service, "public_read_client", client)
    monkeypatch.setattr(
        pokemon_public_snapshot_service,
        "get_pokemon_set_value_history_payload",
        lambda set_id, days, value_scope: (_ for _ in ()).throw(Exception("set value unavailable")),
    )
    monkeypatch.setattr(
        pokemon_public_snapshot_service,
        "get_pokemon_set_top_market_cards_payload",
        lambda set_id, limit, days: {
            "set": {"id": set_id, "name": "Known Set"},
            "cards": [{"cardId": "card-1", "name": "Charizard ex", "marketPrice": 100.0}],
            "meta": {"warnings": []},
        },
    )

    payload = pokemon_public_snapshot_service.get_pokemon_set_market_dashboard_snapshot_payload("set-1", window="30D")

    assert payload["window_key"] == "30d"
    assert payload["setValueHistoriesByScope"]["standard"] == []
    assert payload["topChaseCards"][0]["name"] == "Charizard ex"
    assert payload["meta"]["snapshot"]["source"] == "live_fallback_missing_pokemon_set_market_dashboard_snapshot_latest"


def test_market_dashboard_live_fallback_failure_returns_empty_payload(monkeypatch):
    client = _Client(
        {
            "sets": lambda _query: [
                {
                    "id": "set-1",
                    "name": "Known Set",
                    "canonical_key": "knownSet",
                    "pokemon_api_set_id": "sv-known",
                }
            ],
            "pokemon_set_market_dashboard_snapshot_latest": lambda _query: [],
        }
    )
    monkeypatch.setattr(pokemon_public_snapshot_service, "public_read_client", client)
    monkeypatch.setattr(
        pokemon_public_snapshot_service,
        "get_pokemon_set_value_history_payload",
        lambda set_id, days, value_scope: (_ for _ in ()).throw(Exception("local market table missing")),
    )

    payload = pokemon_public_snapshot_service.get_pokemon_set_market_dashboard_snapshot_payload("set-1", window="30D")

    assert payload["set"]["id"] == "set-1"
    assert payload["setValueHistoriesByScope"]["standard"] == []
    assert payload["meta"]["snapshot"]["source"] == "empty_fallback_missing_pokemon_set_market_dashboard_snapshot_latest"


def test_cards_snapshot_read_does_not_perform_live_desirability_enrichment(monkeypatch):
    client = _Client(
        {
            "sets": lambda _query: [
                {
                    "id": "set-1",
                    "name": "Snapshot Set",
                    "canonical_key": "snapshotSet",
                    "pokemon_api_set_id": "sv-snapshot",
                }
            ],
            "pokemon_set_cards_snapshot_latest": lambda _query: [
                {
                    "set_id": "set-1",
                    "card_count": 1,
                    "updated_at": "2026-06-01T00:00:00+00:00",
                    "payload_json": {
                        "cards": [{"id": "card-1", "name": "Charizard ex"}],
                        "cardDesirabilityValidation": {"cards": [{"cardId": "card-1", "adjustedCardAppealScore": 88}]},
                        "meta": {},
                    },
                }
            ],
            "pokemon_card_desirability_links": lambda _query: (_ for _ in ()).throw(AssertionError("runtime desirability lookup should not run")),
            "pokemon_desirability_composite_scores": lambda _query: (_ for _ in ()).throw(AssertionError("runtime score lookup should not run")),
        }
    )
    monkeypatch.setattr(pokemon_public_snapshot_service, "public_read_client", client)

    payload = pokemon_public_snapshot_service.get_pokemon_set_cards_snapshot_payload("set-1")

    assert payload["cards"][0]["id"] == "card-1"
    assert payload["meta"]["cardDesirabilityValidation"]["precomputed"] is True
    assert payload["meta"]["cardDesirabilityValidation"]["rowCount"] == 1


def test_set_page_snapshot_read_adds_desirability_validation_when_missing(monkeypatch):
    client = _Client(
        {
            "sets": lambda _query: [
                {
                    "id": "set-1",
                    "name": "Snapshot Set",
                    "canonical_key": "snapshotSet",
                    "pokemon_api_set_id": "sv-snapshot",
                }
            ],
            "pokemon_set_page_snapshot_latest": lambda _query: [
                {
                    "set_id": "set-1",
                    "updated_at": "2026-06-01T00:00:00+00:00",
                    "payload_json": {
                        "set": {"id": "set-1", "name": "Snapshot Set"},
                        "summary": {
                            "desirability_score": 90,
                            "pack_score": 80,
                            "profit_score": 70,
                            "safety_score": 60,
                            "stability_score": 50,
                        },
                        "top_hits": [{"marketPrice": 100}],
                        "meta": {},
                    },
                }
            ],
            "pokemon_explore_rankings_snapshot_latest": lambda _query: [
                {
                    "updated_at": "2026-06-01T00:00:00+00:00",
                    "ranking_payload_json": {
                        "targets": [
                            {
                                "id": "set-1",
                                "name": "Snapshot Set",
                                "summary": {
                                    "desirability_score": 90,
                                    "pack_score": 80,
                                    "profit_score": 70,
                                    "safety_score": 60,
                                    "stability_score": 50,
                                },
                                "top_hits": [{"marketPrice": 100}],
                            },
                            {
                                "id": "set-2",
                                "name": "Other Set",
                                "summary": {
                                    "desirability_score": 50,
                                    "pack_score": 70,
                                    "profit_score": 80,
                                    "safety_score": 70,
                                    "stability_score": 60,
                                },
                                "top_hits": [{"marketPrice": 25}],
                            },
                        ]
                    },
                    "default_target_json": {},
                }
            ],
            "pokemon_set_market_dashboard_snapshot_latest": lambda _query: [],
        }
    )
    monkeypatch.setattr(pokemon_public_snapshot_service, "public_read_client", client)

    payload = pokemon_public_snapshot_service.get_pokemon_set_page_snapshot_payload("set-1")

    assert payload["desirabilityValidation"]["formula_version"] == "desirability_validation_v1"
    assert payload["desirability_validation"] == payload["desirabilityValidation"]
    assert payload["meta"]["sources"]["desirability_validation"] == "runtime_from_rankings_snapshot"
