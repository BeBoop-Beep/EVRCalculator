from backend.db.services import pokemon_public_snapshot_service, pokemon_set_market_service


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
        self.select_fields = _fields
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


def test_enrich_cards_payload_with_desirability_exposes_canonical_card_appeal_correlation(monkeypatch):
    cards = [
        {
            "id": f"card-{index}",
            "name": f"Pokemon {index}",
            "rarity": "Common",
        }
        for index in range(1, 259)
    ]
    links = [
        {
            "pokemon_canonical_card_id": f"card-{index}",
            "pokemon_reference_id": index,
            "pokedex_number": index,
            "contribution_weight": 1.0,
            "match_confidence": "exact",
            "is_hit_eligible": index <= 40,
        }
        for index in range(1, 210)
    ]
    scores = [
        {
            "pokemon_reference_id": index,
            "pokedex_number": index,
            "pokemon_name": f"Pokemon {index}",
            "desirability_score": 40.0 + (index % 60),
        }
        for index in range(1, 210)
    ]
    client = _Client(
        {
            "pokemon_card_desirability_links": lambda _query: links,
            "pokemon_desirability_composite_scores": lambda _query: scores,
        }
    )
    monkeypatch.setattr(pokemon_public_snapshot_service, "public_read_client", client)

    prices_by_card = {
        f"card-{index}": {"market_price": 1.0 + index, "variant_id": f"variant-{index}"}
        for index in range(1, 259)
    }
    enriched = pokemon_public_snapshot_service.enrich_cards_payload_with_desirability(
        {"cards": cards, "meta": {}},
        prices_by_card=prices_by_card,
    )
    correlation = enriched["cardAppealMarketPriceCorrelation"]

    assert len(enriched["cardDesirabilityValidation"]["cards"][:40]) == 40
    assert correlation["canonical_count"] == 258
    assert correlation["priced_count"] == 258
    assert correlation["linked_count"] == 209
    assert correlation["scored_linked_count"] == 209
    assert correlation["included_count"] == 209
    assert correlation["excluded_unpriced_count"] == 0
    assert correlation["excluded_unlinked_count"] == 49
    assert correlation["excluded_missing_score_count"] == 0
    assert correlation["n"] == 209
    assert correlation["n"] != 40
    assert correlation["sample_source"] == "canonical_checklist_cards"
    assert len(correlation["rows"]) == 209
    assert len(correlation["plotRows"]) == 258
    assert sum(1 for row in correlation["rows"] if row["is_hit_eligible"]) == 40
    assert sum(1 for row in correlation["plotRows"] if row["treatmentScore"] is not None) == 258
    assert sum(1 for row in correlation["plotRows"] if row["cardAppealScore"] is not None) == 209
    assert correlation["metricDiagnostics"]["cardAppeal"]["includedCount"] == 209
    assert correlation["metricDiagnostics"]["treatmentScore"]["includedCount"] == 258
    assert correlation["rows"][0]["marketPrice"] == 2.0
    assert correlation["rows"][0]["pokemonDesirabilityScore"] == 41.0
    assert enriched["meta"]["cardAppealMarketPriceCorrelation"]["n"] == 209


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
                "set_value_histories_json": {"standard": [{"date": "2026-06-02", "setValue": 321.0}]},
                "top_chase_cards_json": [
                    {
                        "cardId": "card-1",
                        "cardVariantId": "variant-1",
                        "name": "Chase Card",
                        "imageUrl": "https://example.test/card.png",
                        "marketPrice": 12.0,
                        "deltas": {"30D": None},
                    }
                ],
                "top_chase_card_histories_json": {},
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


def test_market_dashboard_snapshot_hydrates_top_chase_history_from_canonical_variant_observations(monkeypatch):
    observation_queries = []

    def read_dashboard(_query):
        return [
            {
                "set_id": "set-1",
                "window_key": "365d",
                "latest_market_date": "2026-06-25",
                "updated_at": "2026-06-25T00:00:00+00:00",
                "top_chase_cards_json": [
                    {
                        "cardId": "legacy-card-1",
                        "cardVariantId": "stale-variant",
                        "name": "Reshiram ex",
                        "marketPrice": 12.0,
                    }
                ],
                "top_chase_card_histories_json": {},
            }
        ]

    def read_observations(query):
        observation_queries.append(query)
        if ("card_variant_id", ["stale-variant"]) in query.in_filters:
            return []
        return [
            {
                "captured_at": "2026-06-25T09:00:00+00:00",
                "card_variant_id": "canonical-variant",
                "condition_id": pokemon_public_snapshot_service.TOP_CHASE_NEAR_MINT_CONDITION_ID,
                "market_price": 22.0,
            },
            {
                "captured_at": "2026-06-24T09:00:00+00:00",
                "card_variant_id": "canonical-variant",
                "condition_id": pokemon_public_snapshot_service.TOP_CHASE_NEAR_MINT_CONDITION_ID,
                "market_price": 21.0,
            },
            {
                "captured_at": "2026-06-23T09:00:00+00:00",
                "card_variant_id": "canonical-variant",
                "condition_id": pokemon_public_snapshot_service.TOP_CHASE_NEAR_MINT_CONDITION_ID,
                "market_price": 20.0,
            },
        ]

    client = _Client(
        {
            "sets": lambda _query: [{"id": "set-1", "name": "Known Set", "canonical_key": "knownSet"}],
            "pokemon_set_market_dashboard_snapshot_latest": read_dashboard,
            "pokemon_canonical_cards": lambda _query: [
                {
                    "id": "canonical-card-1",
                    "set_id": "set-1",
                    "pokemon_tcg_api_card_id": "bw-001",
                    "name": "Reshiram ex",
                    "number": "1",
                    "printed_number": "1/99",
                }
            ],
            "cards": lambda _query: [
                {
                    "id": "legacy-card-1",
                    "set_id": "set-1",
                    "name": "Reshiram ex",
                    "card_number": "1",
                    "pokemon_tcg_api_id": "bw-001",
                }
            ],
            "card_variants": lambda _query: [
                {"id": "stale-variant", "card_id": "legacy-card-1", "pokemon_tcg_api_id": "bw-001"},
                {"id": "canonical-variant", "card_id": "legacy-card-1", "pokemon_tcg_api_id": "bw-001"},
            ],
            "card_variant_price_observations": read_observations,
        }
    )
    monkeypatch.setattr(pokemon_public_snapshot_service, "public_read_client", client)

    payload = pokemon_public_snapshot_service.get_pokemon_set_market_dashboard_snapshot_payload("set-1", window="365D")
    history = payload["topChaseCards"][0]["priceHistory"]

    assert [point["date"] for point in history] == ["2026-06-23", "2026-06-24", "2026-06-25"]
    assert [point["marketPrice"] for point in history] == [20.0, 21.0, 22.0]
    assert all(point["isObserved"] is True for point in history)
    assert all(point["isCarriedForward"] is False for point in history)
    assert all(point["sourceVariantId"] == "canonical-variant" for point in history)
    assert payload["topChaseCardHistories"]["stale-variant"] == history
    assert ("card_variant_id", ["canonical-variant", "stale-variant"]) in observation_queries[-1].in_filters


def test_canonical_top_chase_history_forward_fills_only_missing_days_and_later_actual_wins(monkeypatch):
    def read_observations(_query):
        return [
            {
                "captured_at": "2026-06-23T09:00:00+00:00",
                "card_variant_id": "canonical-variant",
                "condition_id": pokemon_set_market_service.TOP_CHASE_NEAR_MINT_CONDITION_ID
                if hasattr(pokemon_set_market_service, "TOP_CHASE_NEAR_MINT_CONDITION_ID")
                else pokemon_public_snapshot_service.TOP_CHASE_NEAR_MINT_CONDITION_ID,
                "market_price": 20.0,
                "source": "tcgplayer",
            },
            {
                "captured_at": "2026-06-25T09:00:00+00:00",
                "card_variant_id": "canonical-variant",
                "condition_id": pokemon_public_snapshot_service.TOP_CHASE_NEAR_MINT_CONDITION_ID,
                "market_price": 22.0,
                "source": "tcgplayer",
            },
            {
                "captured_at": "2026-06-25T18:00:00+00:00",
                "card_variant_id": "canonical-variant",
                "condition_id": pokemon_public_snapshot_service.TOP_CHASE_NEAR_MINT_CONDITION_ID,
                "market_price": 23.0,
                "source": "tcgplayer",
            },
        ]

    client = _Client({"card_variant_price_observations": read_observations})
    monkeypatch.setattr(pokemon_set_market_service, "public_read_client", client)

    history_by_variant, diagnostics, meta = pokemon_set_market_service._load_canonical_top_chase_price_history(
        [
            {
                "card_id": "legacy-card-1",
                "card_variant_id": "stale-variant",
                "condition_id": pokemon_public_snapshot_service.TOP_CHASE_NEAR_MINT_CONDITION_ID,
                "card_name": "Reshiram ex",
                "price_used": 23.0,
                "captured_at": "2026-06-25T20:00:00+00:00",
            }
        ],
        3,
        {
            "set": {"id": "set-1"},
            "condition_id": pokemon_public_snapshot_service.TOP_CHASE_NEAR_MINT_CONDITION_ID,
            "legacy_card_to_canonical_id": {"legacy-card-1": "canonical-card-1"},
            "variant_to_canonical_id": {
                "stale-variant": "canonical-card-1",
                "canonical-variant": "canonical-card-1",
            },
        },
        {},
        [],
    )

    history = history_by_variant["stale-variant"]

    assert meta["windowStart"] == "2026-06-23"
    assert [point["date"] for point in history] == ["2026-06-23", "2026-06-24", "2026-06-25"]
    assert [point["marketPrice"] for point in history] == [20.0, 20.0, 23.0]
    assert history[0]["isObserved"] is True
    assert history[1]["isObserved"] is False
    assert history[1]["isCarriedForward"] is True
    assert history[1]["sourceDate"] == "2026-06-23"
    assert history[2]["isObserved"] is True
    assert history[2]["isCarriedForward"] is False
    assert history[2]["sourceDate"] == "2026-06-25"
    assert diagnostics["stale-variant"]["canonicalCardId"] == "canonical-card-1"
    assert diagnostics["stale-variant"]["variantCount"] == 2
    assert diagnostics["stale-variant"]["matchingConditionObservationCount"] == 3
    assert diagnostics["stale-variant"]["latestHistoryPrice"] == 23.0


def test_market_dashboard_snapshot_returns_stored_histories_without_live_queries(monkeypatch):
    """Stored topChaseCardHistories in the snapshot are returned directly — no live observation queries."""
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
                "top_chase_cards_json": [
                    {
                        "cardId": "card-1",
                        "cardVariantId": "variant-1",
                        "name": "Chase Card",
                        "marketPrice": 374.0,
                    }
                ],
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

    # Stored histories must be used directly — no live observation or daily-history queries.
    assert len(history) == 365
    assert history[0]["date"] == "2025-06-25"
    assert history[-1]["date"] == "2026-06-24"
    assert payload["topChaseCardHistories"]["variant-1"] == history
    assert observation_queries == [], "live card_variant_price_observations must NOT be queried when stored histories exist"
    assert daily_queries == []
    assert payload["meta"]["topChaseHistorySource"] == "card_variant_price_observations"
    assert payload["meta"]["topChaseHistorySourceWindowDays"] == 365
    assert payload["meta"]["topChaseHistoryMinPoints"] == 365
    assert payload["meta"]["topChaseHistoryMaxPoints"] == 365
    assert payload["meta"]["topChaseHistoryHydratedFromDailyTable"] is False


def test_market_dashboard_snapshot_uses_row_histories_when_payload_histories_empty(monkeypatch):
    """When payload_json has empty topChaseCardHistories but top_chase_card_histories_json has data, row data is used without live queries."""
    observation_queries = []
    row_histories = _daily_top_chase_rows(365)

    def read_dashboard(_query):
        return [
            {
                "set_id": "set-1",
                "window_key": "365d",
                "latest_market_date": "2026-06-24",
                "updated_at": "2026-06-24T00:00:00+00:00",
                "top_chase_card_histories_json": {"variant-1": row_histories},
                "top_chase_cards_json": [{"cardId": "card-1", "cardVariantId": "variant-1", "name": "Chase Card"}],
            }
        ]

    client = _Client(
        {
            "sets": lambda _query: [{"id": "set-1", "name": "Known Set", "canonical_key": "knownSet"}],
            "pokemon_set_market_dashboard_snapshot_latest": read_dashboard,
            "card_variant_price_observations": lambda _query: (observation_queries.append(_query) or _raw_observation_rows(75)),
        }
    )
    monkeypatch.setattr(pokemon_public_snapshot_service, "public_read_client", client)

    payload = pokemon_public_snapshot_service.get_pokemon_set_market_dashboard_snapshot_payload("set-1", window="365D")
    history = payload["topChaseCards"][0]["priceHistory"]

    # Stored row histories must be returned; no live observation queries.
    assert len(history) == 365
    assert history[0]["date"] == "2025-06-25"
    assert observation_queries == [], "live card_variant_price_observations must NOT be queried when top_chase_card_histories_json has data"


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
                "top_chase_cards_json": [
                    {
                        "cardId": "card-1",
                        "cardVariantId": "variant-1",
                        "name": "Chase Card",
                        "marketPrice": 374.0,
                    }
                ],
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


def test_set_value_history_snapshot_payload_reads_daily_history_directly(monkeypatch):
    calls = []

    def _daily_history_payload(set_id, days, value_scope):
        calls.append({"set_id": set_id, "days": days, "value_scope": value_scope})
        return {
            "set": {"id": set_id, "name": "Known Set"},
            "history": [
                {"date": "2026-06-23", "setValue": 100.0},
                {"date": "2026-06-24", "setValue": 101.0},
            ],
            "meta": {
                "days": 6,
                "valueScope": "standard",
                "priceBasis": "Near Mint card_variant_price_observations rolled up into pokemon_set_value_daily_history",
            },
        }

    monkeypatch.setattr(
        pokemon_public_snapshot_service,
        "get_pokemon_set_value_history_payload",
        _daily_history_payload,
    )
    monkeypatch.setattr(
        pokemon_public_snapshot_service,
        "get_pokemon_set_market_dashboard_snapshot_payload",
        lambda *args, **kwargs: (_ for _ in ()).throw(AssertionError("dashboard snapshot should not be read")),
    )

    payload = pokemon_public_snapshot_service.get_pokemon_set_value_history_snapshot_payload(
        "set-1",
        days="6",
        value_scope="standard",
    )

    assert calls == [{"set_id": "set-1", "days": "6", "value_scope": "standard"}]
    assert [point["date"] for point in payload["history"]] == ["2026-06-23", "2026-06-24"]
    assert payload["meta"]["priceBasis"].startswith("Near Mint")


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

    assert payload.get("desirabilityValidation") is None
    assert payload.get("desirability_validation") is None
    assert (
        "Desirability validation is missing in this snapshot; request path skipped runtime rebuild."
        in payload["meta"]["warnings"]
    )


def test_rankings_snapshot_returns_stored_payload_when_checklist_enrichment_fails(monkeypatch):
    def fail_enrichment(_payload):
        raise RuntimeError("dashboard enrichment unavailable")

    client = _Client(
        {
            "pokemon_explore_rankings_snapshot_latest": lambda _query: [
                {
                    "updated_at": "2026-06-01T00:00:00+00:00",
                    "ranking_payload_json": {
                        "targets": [
                            {
                                "id": "set-1",
                                "target_id": "set-1",
                                "target_type": "set",
                                "name": "Stored Set",
                                "is_opening_set": True,
                            }
                        ],
                        "meta": {"warnings": ["existing warning"]},
                    },
                    "default_target_json": {"target_id": "set-1", "target_type": "set"},
                }
            ],
        }
    )
    monkeypatch.setattr(pokemon_public_snapshot_service, "public_read_client", client)
    monkeypatch.setattr(
        pokemon_public_snapshot_service,
        "_enrich_rankings_payload_with_checklist_set_values",
        fail_enrichment,
    )
    monkeypatch.setattr(
        pokemon_public_snapshot_service,
        "get_rip_statistics_targets_payload",
        lambda **_kwargs: (_ for _ in ()).throw(AssertionError("live fallback should not run")),
    )

    payload = pokemon_public_snapshot_service.get_pokemon_explore_rankings_snapshot_payload(limit=10)

    assert payload["targets"][0]["target_id"] == "set-1"
    assert payload["default_target"]["target_id"] == "set-1"
    assert payload["meta"]["warnings"][0] == "existing warning"
    assert (
        "Checklist set value enrichment failed; served persisted rankings snapshot without enrichment."
        in payload["meta"]["warnings"]
    )
    assert payload["meta"]["sources"]["checklist_set_value_enrichment"] == "FAILED_OPTIONAL"
    assert payload["meta"]["snapshot"]["source"] == "pokemon_explore_rankings_snapshot_latest"


def test_set_page_snapshot_with_top_hits_renders_when_rankings_enrichment_fails(monkeypatch):
    def fail_enrichment(_payload):
        raise RuntimeError("dashboard enrichment unavailable")

    client = _Client(
        {
            "sets": lambda _query: [
                {
                    "id": "set-1",
                    "name": "White Flare",
                    "canonical_key": "white-flare",
                    "pokemon_api_set_id": "rsv10pt5",
                }
            ],
            "pokemon_set_page_snapshot_latest": lambda _query: [
                {
                    "set_id": "set-1",
                    "updated_at": "2026-06-01T00:00:00+00:00",
                    "payload_json": {
                        "summary": {
                            "target_id": "set-1",
                            "set_id": "set-1",
                            "name": "White Flare",
                            "desirability_score": 90,
                            "pack_score": 80,
                            "profit_score": 70,
                            "safety_score": 60,
                            "stability_score": 50,
                        },
                        "top_hits": [{"card_name": "Chase", "ev_contribution": 1.2}],
                        "meta": {
                            "sources": {"simulation_input_cards": "OK"},
                            "snapshotCompleteness": {"simulation_input_cards": "OK"},
                            "warnings": [],
                        },
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
                                "target_id": "set-1",
                                "target_type": "set",
                                "name": "White Flare",
                                "is_opening_set": True,
                                "summary": {
                                    "desirability_score": 90,
                                    "pack_score": 80,
                                    "profit_score": 70,
                                    "safety_score": 60,
                                    "stability_score": 50,
                                },
                            }
                        ],
                        "meta": {},
                    },
                    "default_target_json": {"target_id": "set-1", "target_type": "set"},
                }
            ],
        }
    )
    monkeypatch.setattr(pokemon_public_snapshot_service, "public_read_client", client)
    monkeypatch.setattr(
        pokemon_public_snapshot_service,
        "_enrich_rankings_payload_with_checklist_set_values",
        fail_enrichment,
    )

    payload = pokemon_public_snapshot_service.get_pokemon_set_page_snapshot_payload("white-flare")

    assert payload["summary"]["name"] == "White Flare"
    assert payload["top_hits"][0]["card_name"] == "Chase"
    assert payload["meta"]["sources"]["simulation_input_cards"] == "OK"
    assert payload.get("desirabilityValidation") is None
    assert payload.get("desirability_validation") is None
    assert "Desirability validation is missing in this snapshot; request path skipped runtime rebuild." in payload["meta"]["warnings"]


def test_set_page_missing_snapshot_returns_fallback_without_live_assembly(monkeypatch):
    client = _Client(
        {
            "sets": lambda _query: [
                {
                    "id": "set-1",
                    "name": "Known Set",
                    "canonical_key": "known-set",
                    "pokemon_api_set_id": "sv-known",
                }
            ],
            "pokemon_set_page_snapshot_latest": lambda _query: [],
        }
    )
    monkeypatch.setattr(pokemon_public_snapshot_service, "public_read_client", client)

    payload = pokemon_public_snapshot_service.get_pokemon_set_page_snapshot_payload("set-1")

    assert payload["summary"]["target_id"] == "set-1"
    assert payload["summary"]["name"] == "Known Set"
    assert payload["top_hits"] == []
    assert payload["meta"]["fallback"] is True
    assert payload["meta"]["sources"]["setPage"] == "fallback_missing_pokemon_set_page_snapshot_latest"
    assert payload["meta"]["errors"][0]["code"] == "POKEMON_SET_PAGE_SNAPSHOT_MISSING"


def test_set_page_snapshot_missing_top_hits_skips_live_repair(monkeypatch):
    client = _Client(
        {
            "sets": lambda _query: [
                {
                    "id": "set-1",
                    "name": "Known Set",
                    "canonical_key": "known-set",
                    "pokemon_api_set_id": "sv-known",
                }
            ],
            "pokemon_set_page_snapshot_latest": lambda _query: [
                {
                    "set_id": "set-1",
                    "updated_at": "2026-06-01T00:00:00+00:00",
                    "payload_json": {
                        "summary": {"target_id": "set-1", "name": "Known Set"},
                        "top_hits": [],
                        "meta": {"sources": {"simulation_input_cards": "FAILED"}, "warnings": []},
                    },
                }
            ],
        }
    )
    monkeypatch.setattr(pokemon_public_snapshot_service, "public_read_client", client)

    payload = pokemon_public_snapshot_service.get_pokemon_set_page_snapshot_payload("set-1")

    assert payload["top_hits"] == []
    assert payload["meta"]["simulationDriversRepairSkipped"]["policy"] == "no_live_assembly_during_route_render"
    assert any("skipped live repair during route render" in warning for warning in payload["meta"]["debugWarnings"])


def test_set_page_snapshot_read_warns_when_rankings_snapshot_is_stale(monkeypatch):
    client = _Client(
        {
            "sets": lambda _query: [
                {
                    "id": "set-1",
                    "name": "Known Set",
                    "canonical_key": "known-set",
                    "pokemon_api_set_id": "sv-known",
                }
            ],
            "pokemon_set_page_snapshot_latest": lambda _query: [
                {
                    "set_id": "set-1",
                    "updated_at": "2026-06-25T12:00:00+00:00",
                    "payload_json": {
                        "summary": {"target_id": "set-1", "name": "Known Set", "profit_rank": 3},
                        "top_hits": [{"card_name": "Chase", "ev_contribution": 1.2}],
                        "meta": {"sources": {"simulation_input_cards": "OK"}, "warnings": []},
                    },
                }
            ],
            "pokemon_explore_rankings_snapshot_latest": lambda _query: [
                {"updated_at": "2026-06-22T12:00:00+00:00"}
            ],
        }
    )
    monkeypatch.setattr(pokemon_public_snapshot_service, "public_read_client", client)

    payload = pokemon_public_snapshot_service.get_pokemon_set_page_snapshot_payload("set-1")

    assert "rankings snapshot is stale relative to set page snapshot" not in payload["meta"]["warnings"]
    assert payload["meta"]["snapshot"].get("exploreRankingsUpdatedAt") is None


def test_set_page_snapshot_read_does_not_runtime_build_desirability_validation(monkeypatch):
    client = _Client(
        {
            "sets": lambda _query: [
                {
                    "id": "set-1",
                    "name": "Known Set",
                    "canonical_key": "known-set",
                    "pokemon_api_set_id": "sv-known",
                }
            ],
            "pokemon_set_page_snapshot_latest": lambda _query: [
                {
                    "set_id": "set-1",
                    "updated_at": "2026-06-25T12:00:00+00:00",
                    "payload_json": {
                        "summary": {"target_id": "set-1", "name": "Known Set"},
                        "top_hits": [{"card_name": "Chase", "ev_contribution": 1.2}],
                        "meta": {"sources": {"simulation_input_cards": "OK"}, "warnings": []},
                    },
                }
            ],
        }
    )
    monkeypatch.setattr(pokemon_public_snapshot_service, "public_read_client", client)
    monkeypatch.setattr(
        pokemon_public_snapshot_service,
        "_with_desirability_validation",
        lambda *_args, **_kwargs: (_ for _ in ()).throw(AssertionError("runtime desirability validation should not run")),
    )
    monkeypatch.setattr(
        pokemon_public_snapshot_service,
        "_with_rankings_freshness_warning",
        lambda *_args, **_kwargs: (_ for _ in ()).throw(AssertionError("rankings freshness lookup should not run")),
    )

    payload = pokemon_public_snapshot_service.get_pokemon_set_page_snapshot_payload("set-1")

    assert payload["summary"]["name"] == "Known Set"
    assert payload["meta"]["timings"]["snapshot_read_ms"] is not None


# ---------------------------------------------------------------------------
# Live fallback: simulation performance history contract tests
# ---------------------------------------------------------------------------


def _set_row_handlers():
    return {
        "sets": lambda _query: [
            {
                "id": "set-1",
                "name": "Test Set",
                "canonical_key": "testSet",
                "pokemon_api_set_id": "sv-test",
            }
        ],
        "pokemon_set_market_dashboard_snapshot_latest": lambda _query: [],
    }


def test_live_fallback_performance_history_comes_from_simulation_not_set_value(monkeypatch):
    """In the live fallback, performanceVsCostHistory must come from calculation_history_trend, not standard set value."""
    history_rows = [
        {
            "snapshot_date": "2026-06-20",
            "calculation_run_id": "run-live-1",
            "run_created_at": "2026-06-20T12:00:00+00:00",
            "simulated_mean_pack_value_vs_pack_cost": 0.75,
            "simulated_median_pack_value_vs_pack_cost": 0.50,
            "p95_value_to_cost_ratio": 2.8,
        }
    ]
    summary_rows = [
        {
            "calculation_run_id": "run-live-1",
            "pack_cost": 4.0,
            "mean_value": 3.0,
            "median_value": 2.0,
        }
    ]

    handlers = {
        **_set_row_handlers(),
        "calculation_history_trend": lambda _query: history_rows,
        "simulation_run_summary": lambda _query: summary_rows,
        "card_variant_price_observations": lambda _query: [],
    }
    monkeypatch.setattr(pokemon_public_snapshot_service, "public_read_client", _Client(handlers))
    monkeypatch.setattr(
        pokemon_public_snapshot_service,
        "get_pokemon_set_value_history_payload",
        lambda set_id, days, value_scope: {
            "history": [{"date": "2026-06-20", "setValue": 999.99}],
            "meta": {"warnings": []},
        },
    )
    monkeypatch.setattr(
        pokemon_public_snapshot_service,
        "get_pokemon_set_top_market_cards_payload",
        lambda set_id, limit, days: {"set": {"id": set_id}, "cards": [], "meta": {"warnings": []}},
    )

    payload = pokemon_public_snapshot_service.get_pokemon_set_market_dashboard_snapshot_payload(
        "set-1", window="365d"
    )

    perf = payload["performanceVsCostHistory"]
    assert len(perf) == 1, "expected one simulation performance point"
    pt = perf[0]

    # Simulation ratio fields must be present
    assert pt["simulated_mean_pack_value_vs_pack_cost"] == 0.75
    assert pt["simulated_median_pack_value_vs_pack_cost"] == 0.50
    assert pt["p95_value_to_cost_ratio"] == 2.8
    assert pt["calculation_run_id"] == "run-live-1"
    assert pt["pack_cost"] == 4.0
    assert pt["source"] == "calculation_history_trend+simulation_run_summary"

    # Must NOT be set value data
    assert "setValue" not in pt
    assert "set_value" not in pt

    # snake_case alias must match
    assert payload["performance_vs_cost_history"] == perf

    # Set value histories must still be populated under their scope
    assert payload["setValueHistoriesByScope"]["standard"][0]["setValue"] == 999.99


def test_live_fallback_performance_history_empty_when_no_simulation_data(monkeypatch):
    """When calculation_history_trend returns no rows, performanceVsCostHistory is [] and a warning is added."""
    handlers = {
        **_set_row_handlers(),
        "calculation_history_trend": lambda _query: [],
        "simulation_run_summary": lambda _query: [],
        "card_variant_price_observations": lambda _query: [],
    }
    monkeypatch.setattr(pokemon_public_snapshot_service, "public_read_client", _Client(handlers))
    monkeypatch.setattr(
        pokemon_public_snapshot_service,
        "get_pokemon_set_value_history_payload",
        lambda set_id, days, value_scope: {
            "history": [{"date": "2026-06-21", "setValue": 100.0}],
            "meta": {"warnings": []},
        },
    )
    monkeypatch.setattr(
        pokemon_public_snapshot_service,
        "get_pokemon_set_top_market_cards_payload",
        lambda set_id, limit, days: {"set": {"id": set_id}, "cards": [], "meta": {"warnings": []}},
    )

    payload = pokemon_public_snapshot_service.get_pokemon_set_market_dashboard_snapshot_payload(
        "set-1", window="365d"
    )

    # Empty simulation history → empty performanceVsCostHistory, NOT standard set value
    assert payload["performanceVsCostHistory"] == []
    assert payload["performance_vs_cost_history"] == []

    # Standard set value history must still be accessible under its scope
    assert payload["setValueHistoriesByScope"]["standard"][0]["setValue"] == 100.0

    # Warning must be present
    warnings = payload["meta"]["warnings"]
    assert any("simulation performance history" in w.lower() for w in warnings)


# ---------------------------------------------------------------------------
# Snapshot-read fast-path: stored rows return directly, no live rebuilds
# ---------------------------------------------------------------------------


def test_market_dashboard_snapshot_row_returns_stored_payload_without_live_rebuild(monkeypatch):
    """When a market dashboard snapshot row exists with top chase cards and stored histories, no live DB calls
    are made to card_variant_price_observations, set value history, or top market cards."""
    live_queries = []
    stored_history = [
        {"date": "2026-06-23", "marketPrice": 100.0, "market_price": 100.0, "sourceDate": "2026-06-23", "source_date": "2026-06-23"},
        {"date": "2026-06-24", "marketPrice": 101.0, "market_price": 101.0, "sourceDate": "2026-06-24", "source_date": "2026-06-24"},
    ]

    def read_dashboard(_query):
        return [
            {
                "set_id": "set-1",
                "window_key": "365d",
                "latest_market_date": "2026-06-24",
                "updated_at": "2026-06-24T00:00:00+00:00",
                "set_value_histories_json": {"standard": [{"date": "2026-06-24", "setValue": 500.0}]},
                "performance_vs_cost_history_json": [{"date": "2026-06-24", "meanValueToCostRatio": 0.8}],
                "top_chase_card_histories_json": {"variant-1": stored_history},
                "top_chase_cards_json": [
                    {
                        "cardId": "card-1",
                        "cardVariantId": "variant-1",
                        "name": "Chase Card",
                        "marketPrice": 101.0,
                    }
                ],
            }
        ]

    def track_live(query):
        live_queries.append(query)
        return []

    client = _Client(
        {
            "sets": lambda _query: [{"id": "set-1", "name": "Snapshot Set", "canonical_key": "snapshotSet"}],
            "pokemon_set_market_dashboard_snapshot_latest": read_dashboard,
            "card_variant_price_observations": track_live,
            "calculation_history_trend": track_live,
            "simulation_run_summary": track_live,
        }
    )
    monkeypatch.setattr(pokemon_public_snapshot_service, "public_read_client", client)
    monkeypatch.setattr(
        pokemon_public_snapshot_service,
        "get_pokemon_set_value_history_payload",
        lambda *_a, **_kw: (_ for _ in ()).throw(AssertionError("live set value history must not be called when snapshot exists")),
    )
    monkeypatch.setattr(
        pokemon_public_snapshot_service,
        "get_pokemon_set_top_market_cards_payload",
        lambda *_a, **_kw: (_ for _ in ()).throw(AssertionError("live top market cards must not be called when snapshot exists")),
    )

    payload = pokemon_public_snapshot_service.get_pokemon_set_market_dashboard_snapshot_payload("set-1", window="365d")

    assert payload["set"]["name"] == "Snapshot Set"
    assert payload["setValueHistoriesByScope"]["standard"][0]["setValue"] == 500.0
    assert payload["topChaseCards"][0]["priceHistory"] == stored_history
    assert payload["meta"]["snapshot"]["source"] == "pokemon_set_market_dashboard_snapshot_latest"
    assert live_queries == [], "no live observation, calculation_history_trend, or simulation queries when snapshot row exists"
    assert payload["meta"]["timings"]["snapshot_query_ms"] is not None


def test_cards_snapshot_missing_falls_back_to_canonical_cards(monkeypatch):
    """When the cards snapshot row is missing, falls back to get_pokemon_set_cards_payload without desirability enrichment."""
    client = _Client(
        {
            "sets": lambda _query: [
                {"id": "set-1", "name": "Known Set", "canonical_key": "knownSet", "pokemon_api_set_id": "sv-known"}
            ],
            "pokemon_set_cards_snapshot_latest": lambda _query: [],
            "pokemon_card_desirability_links": lambda _query: (_ for _ in ()).throw(
                AssertionError("desirability links must not be queried on fallback path")
            ),
        }
    )
    monkeypatch.setattr(pokemon_public_snapshot_service, "public_read_client", client)
    monkeypatch.setattr(
        pokemon_public_snapshot_service,
        "get_pokemon_set_cards_payload",
        lambda set_id: {
            "set": {"id": set_id, "name": "Known Set"},
            "cards": [{"id": "card-1", "name": "Charizard ex"}],
            "meta": {"warnings": []},
        },
    )

    payload = pokemon_public_snapshot_service.get_pokemon_set_cards_snapshot_payload("set-1")

    assert payload["cards"][0]["id"] == "card-1"
    assert payload["meta"]["snapshot"]["source"] == "live_fallback_missing_pokemon_set_cards_snapshot_latest"
    assert any("Pokemon set cards snapshot is missing" in w for w in payload["meta"]["warnings"])
    assert payload["meta"]["cardDesirabilityValidation"]["precomputed"] is False


def test_uuid_set_id_resolves_with_single_query(monkeypatch):
    """UUID-shaped set_id must be resolved via a single id= lookup — no sequential field fallbacks."""
    queries_made = []

    def track_sets(query):
        queries_made.append(list(query.eq_filters))
        return [{"id": "75cd439d-aaa2-41cb-86f3-2fefa5b26e29", "name": "Ascended Heroes", "canonical_key": "ascendedHeroes"}]

    client = _Client(
        {
            "sets": track_sets,
            "pokemon_set_page_snapshot_latest": lambda _query: [],
        }
    )
    monkeypatch.setattr(pokemon_public_snapshot_service, "public_read_client", client)

    pokemon_public_snapshot_service.get_pokemon_set_page_snapshot_payload("75cd439d-aaa2-41cb-86f3-2fefa5b26e29")

    # Only one sets query should be made, and it must use `id` equality.
    assert len(queries_made) == 1, f"expected 1 sets query, got {len(queries_made)}: {queries_made}"
    assert ("id", "75cd439d-aaa2-41cb-86f3-2fefa5b26e29") in queries_made[0]


_TEST_UUID = "75cd439d-aaa2-41cb-86f3-2fefa5b26e29"


def test_uuid_page_snapshot_hit_skips_sets_query(monkeypatch):
    """UUID set_id + existing page snapshot row → returns stored payload without any sets table query."""

    def reject_sets(_query):
        raise AssertionError("sets table must not be queried for UUID fast path on snapshot hit")

    client = _Client(
        {
            "sets": reject_sets,
            "pokemon_set_page_snapshot_latest": lambda _query: [
                {
                    "set_id": _TEST_UUID,
                    "payload_json": {
                        "set": {"id": _TEST_UUID, "name": "Fast Set"},
                        "cards": [],
                        "meta": {"snapshot": {"source": "pokemon_set_page_snapshot_latest"}},
                    },
                    "as_of": "2026-06-28",
                    "source_updated_at": "2026-06-28T00:00:00+00:00",
                    "updated_at": "2026-06-28T00:00:00+00:00",
                }
            ],
            "pokemon_explore_rankings_snapshot_latest": lambda _query: [],
        }
    )
    monkeypatch.setattr(pokemon_public_snapshot_service, "public_read_client", client)

    payload = pokemon_public_snapshot_service.get_pokemon_set_page_snapshot_payload(_TEST_UUID)

    assert payload["set"]["id"] == _TEST_UUID
    assert payload["meta"]["snapshot"]["source"] == "pokemon_set_page_snapshot_latest"
    assert payload["meta"]["timings"]["snapshot_query_ms"] is not None


def test_uuid_cards_snapshot_hit_skips_sets_query(monkeypatch):
    """UUID set_id + existing cards snapshot row → returns stored payload without any sets table query."""

    def reject_sets(_query):
        raise AssertionError("sets table must not be queried for UUID fast path on snapshot hit")

    client = _Client(
        {
            "sets": reject_sets,
            "pokemon_set_cards_snapshot_latest": lambda _query: [
                {
                    "set_id": _TEST_UUID,
                    "card_count": 165,
                    "updated_at": "2026-06-28T00:00:00+00:00",
                    "payload_json": {
                        "set": {"id": _TEST_UUID, "name": "Fast Cards Set"},
                        "cards": [{"id": "card-1", "name": "Pikachu ex"}],
                        "meta": {
                            "snapshot": {"source": "pokemon_set_cards_snapshot_latest"},
                            "timings": {},
                        },
                    },
                }
            ],
        }
    )
    monkeypatch.setattr(pokemon_public_snapshot_service, "public_read_client", client)

    payload = pokemon_public_snapshot_service.get_pokemon_set_cards_snapshot_payload(_TEST_UUID)

    assert payload["set"]["id"] == _TEST_UUID
    assert payload["cards"][0]["name"] == "Pikachu ex"
    assert payload["meta"]["snapshot"]["source"] == "pokemon_set_cards_snapshot_latest"
    assert payload["meta"]["cardDesirabilityValidation"]["precomputed"] is True
    assert payload["meta"]["timings"]["snapshot_query_ms"] is not None
    assert "set_resolve_ms" not in payload["meta"]["timings"]


def test_uuid_market_dashboard_snapshot_hit_skips_sets_and_live_queries(monkeypatch):
    """UUID set_id + existing market dashboard snapshot row → returns stored payload; no sets query, no live assembly."""
    live_calls = []

    stored_history = [
        {"date": "2026-06-27", "marketPrice": 50.0},
        {"date": "2026-06-28", "marketPrice": 55.0},
    ]

    def reject_sets(_query):
        raise AssertionError("sets table must not be queried for UUID fast path on snapshot hit")

    client = _Client(
        {
            "sets": reject_sets,
            "pokemon_set_market_dashboard_snapshot_latest": lambda _query: [
                {
                    "set_id": _TEST_UUID,
                    "window_key": "365d",
                    "latest_market_date": "2026-06-28",
                    "updated_at": "2026-06-28T00:00:00+00:00",
                    "set_value_histories_json": {"standard": [{"date": "2026-06-28", "setValue": 200.0}]},
                    "performance_vs_cost_history_json": [],
                    "top_chase_card_histories_json": {"variant-uuid": stored_history},
                    "top_chase_cards_json": [
                        {
                            "cardId": "card-uuid-1",
                            "cardVariantId": "variant-uuid",
                            "name": "UUID Chase Card",
                            "marketPrice": 55.0,
                        }
                    ],
                }
            ],
            "card_variant_price_observations": lambda _q: (live_calls.append("observations") or []),
            "calculation_history_trend": lambda _q: (live_calls.append("calc_trend") or []),
            "simulation_run_summary": lambda _q: (live_calls.append("sim_summary") or []),
        }
    )
    monkeypatch.setattr(pokemon_public_snapshot_service, "public_read_client", client)
    monkeypatch.setattr(
        pokemon_public_snapshot_service,
        "get_pokemon_set_value_history_payload",
        lambda *_a, **_kw: (_ for _ in ()).throw(AssertionError("live value history must not run on UUID snapshot hit")),
    )
    monkeypatch.setattr(
        pokemon_public_snapshot_service,
        "get_pokemon_set_top_market_cards_payload",
        lambda *_a, **_kw: (_ for _ in ()).throw(AssertionError("live top cards must not run on UUID snapshot hit")),
    )

    payload = pokemon_public_snapshot_service.get_pokemon_set_market_dashboard_snapshot_payload(_TEST_UUID, window="365d")

    assert payload["set"]["id"] == _TEST_UUID
    assert payload["setValueHistoriesByScope"]["standard"][0]["setValue"] == 200.0
    price_history = payload["topChaseCards"][0]["priceHistory"]
    assert len(price_history) == len(stored_history)
    assert price_history[0]["date"] == stored_history[0]["date"]
    assert price_history[0]["marketPrice"] == stored_history[0]["marketPrice"]
    assert payload["meta"]["snapshot"]["source"] == "pokemon_set_market_dashboard_snapshot_latest"
    assert live_calls == [], f"no live DB calls expected for UUID snapshot hit, got: {live_calls}"


def test_uuid_market_dashboard_snapshot_miss_returns_fast_empty(monkeypatch):
    """UUID set_id + no market dashboard snapshot row → fast empty payload; no sets query, no live assembly."""

    def reject_sets(_query):
        raise AssertionError("sets table must not be queried for UUID fast path on snapshot miss")

    client = _Client(
        {
            "sets": reject_sets,
            "pokemon_set_market_dashboard_snapshot_latest": lambda _query: [],
        }
    )
    monkeypatch.setattr(pokemon_public_snapshot_service, "public_read_client", client)
    monkeypatch.setattr(
        pokemon_public_snapshot_service,
        "get_pokemon_set_value_history_payload",
        lambda *_a, **_kw: (_ for _ in ()).throw(AssertionError("live value history must not run on UUID snapshot miss")),
    )
    monkeypatch.setattr(
        pokemon_public_snapshot_service,
        "get_pokemon_set_top_market_cards_payload",
        lambda *_a, **_kw: (_ for _ in ()).throw(AssertionError("live top cards must not run on UUID snapshot miss")),
    )
    monkeypatch.setattr(
        pokemon_public_snapshot_service,
        "_load_simulation_performance_history_live",
        lambda *_a, **_kw: (_ for _ in ()).throw(AssertionError("simulation history must not run on UUID snapshot miss")),
    )

    payload = pokemon_public_snapshot_service.get_pokemon_set_market_dashboard_snapshot_payload(_TEST_UUID, window="365d")

    assert payload["set"]["id"] == _TEST_UUID
    assert payload["topChaseCards"] == []
    assert payload["setValueHistoriesByScope"] == {"standard": [], "hits": [], "top10": []}
    assert "missing" in payload["meta"]["warnings"][0].lower() or "snapshot" in payload["meta"]["warnings"][0].lower()
    assert "empty_fallback" in payload["meta"]["snapshot"]["source"]


def test_market_dashboard_reader_does_not_select_payload_json(monkeypatch):
    """The market dashboard reader must never pull payload_json off pokemon_set_market_dashboard_snapshot_latest."""
    captured_queries = []

    def read_dashboard(query):
        captured_queries.append(query)
        return [
            {
                "set_id": _TEST_UUID,
                "window_key": "365d",
                "latest_market_date": "2026-06-28",
                "updated_at": "2026-06-28T00:00:00+00:00",
                "set_value_histories_json": {"standard": [{"date": "2026-06-28", "setValue": 200.0}]},
                "performance_vs_cost_history_json": [],
                "top_chase_cards_json": [],
                "top_chase_card_histories_json": {},
                "available_scopes_json": [],
            }
        ]

    client = _Client({"pokemon_set_market_dashboard_snapshot_latest": read_dashboard})
    monkeypatch.setattr(pokemon_public_snapshot_service, "public_read_client", client)

    payload = pokemon_public_snapshot_service.get_pokemon_set_market_dashboard_snapshot_payload(_TEST_UUID, window="365d")

    assert len(captured_queries) == 1
    selected_fields = captured_queries[0].select_fields
    assert "payload_json" not in selected_fields
    assert "set_value_histories_json" in selected_fields
    assert "top_chase_cards_json" in selected_fields

    assert payload["set"]["id"] == _TEST_UUID
    assert payload["setValueHistoriesByScope"]["standard"][0]["setValue"] == 200.0
    assert payload["meta"]["snapshot"]["source"] == "pokemon_set_market_dashboard_snapshot_latest"


def test_shell_snapshot_reader_does_not_select_payload_json(monkeypatch):
    """The shell reader must never pull payload_json off pokemon_set_page_snapshot_latest."""
    captured_queries = []

    def read_shell(query):
        captured_queries.append(query)
        return [
            {
                "set_id": _TEST_UUID,
                "set_identity_json": {"id": _TEST_UUID, "name": "Shell Set", "slug": "shell-set"},
                "title_card_json": {"pack_score": 71.5, "pack_tier": "A"},
                "rip_summary_json": {"pack_rank": 3, "profit_score": 60.1},
                "market_summary_json": {"simulated_set_value": 199.5, "pack_cost": 4.99},
                "risk_summary_json": {"coefficient_of_variation": 1.2},
                "concentration_json": {"hhi_ev_concentration": 0.3},
                "desirability_summary_json": {"score": 0.8},
                "as_of": "2026-06-28",
                "source_updated_at": "2026-06-28T00:00:00+00:00",
                "updated_at": "2026-06-28T00:00:00+00:00",
            }
        ]

    client = _Client({"pokemon_set_page_snapshot_latest": read_shell})
    monkeypatch.setattr(pokemon_public_snapshot_service, "public_read_client", client)

    payload = pokemon_public_snapshot_service.get_pokemon_set_shell_snapshot_payload(_TEST_UUID)

    assert len(captured_queries) == 1
    selected_fields = captured_queries[0].select_fields
    assert "payload_json" not in selected_fields
    assert "set_identity_json" in selected_fields
    assert "title_card_json" in selected_fields

    assert payload["set"]["id"] == _TEST_UUID
    assert payload["set"]["name"] == "Shell Set"
    assert payload["summary"]["pack_score"] == 71.5
    assert payload["summary"]["pack_rank"] == 3
    assert payload["summary"]["simulated_set_value"] == 199.5
    assert payload["titleCard"]["pack_tier"] == "A"
    assert payload["meta"]["snapshot"]["source"] == "pokemon_set_page_snapshot_latest"
    assert payload["meta"]["timings"]["snapshot_query_ms"] is not None


def test_shell_snapshot_missing_row_returns_fallback(monkeypatch):
    """Missing shell snapshot row falls back to a minimal identity-only shell without raising."""
    client = _Client(
        {
            "pokemon_set_page_snapshot_latest": lambda _query: [],
            "sets": lambda _query: [{"id": _TEST_UUID, "name": "Fallback Set", "canonical_key": "fallback-set"}],
        }
    )
    monkeypatch.setattr(pokemon_public_snapshot_service, "public_read_client", client)

    payload = pokemon_public_snapshot_service.get_pokemon_set_shell_snapshot_payload(_TEST_UUID)

    assert payload["set"]["id"] == _TEST_UUID
    assert payload["set"]["name"] == "Fallback Set"
    assert payload["meta"]["fallback"] is True
    assert payload["summary"] == {}


def test_uuid_shell_snapshot_hit_skips_sets_query(monkeypatch):
    """UUID set_id + existing shell row → returns split-column payload without any sets table query."""

    def reject_sets(_query):
        raise AssertionError("sets table must not be queried for UUID fast path on shell snapshot hit")

    client = _Client(
        {
            "sets": reject_sets,
            "pokemon_set_page_snapshot_latest": lambda _query: [
                {
                    "set_id": _TEST_UUID,
                    "set_identity_json": {"id": _TEST_UUID, "name": "Fast Shell Set"},
                    "title_card_json": {"pack_score": 50.0},
                    "rip_summary_json": {},
                    "market_summary_json": {},
                    "risk_summary_json": {},
                    "concentration_json": {},
                    "desirability_summary_json": {},
                    "as_of": "2026-06-28",
                    "source_updated_at": "2026-06-28T00:00:00+00:00",
                    "updated_at": "2026-06-28T00:00:00+00:00",
                }
            ],
        }
    )
    monkeypatch.setattr(pokemon_public_snapshot_service, "public_read_client", client)

    payload = pokemon_public_snapshot_service.get_pokemon_set_shell_snapshot_payload(_TEST_UUID)

    assert payload["set"]["id"] == _TEST_UUID
    assert payload["set"]["name"] == "Fast Shell Set"
    assert payload["summary"]["pack_score"] == 50.0


def test_shell_snapshot_exposes_interpretation_from_set_intelligence_json(monkeypatch):
    """The shell must expose the same recommendation badge/summary the full /page payload uses."""
    client = _Client(
        {
            "pokemon_set_page_snapshot_latest": lambda _query: [
                {
                    "set_id": _TEST_UUID,
                    "set_identity_json": {"id": _TEST_UUID, "name": "Shell Set"},
                    "title_card_json": {"pack_score": 71.5, "pack_tier": "A"},
                    "rip_summary_json": {},
                    "market_summary_json": {},
                    "risk_summary_json": {},
                    "concentration_json": {},
                    "desirability_summary_json": {},
                    "set_intelligence_json": {
                        "packScore": "Very Weak Value Profile",
                        "meta": {
                            "packScore": {"label": "Very Weak Value Profile", "summary": "This set trails the field."},
                            "set_intelligence": [{"key": "opening_experience", "tier": "C"}],
                        },
                    },
                    "as_of": "2026-06-28",
                    "source_updated_at": "2026-06-28T00:00:00+00:00",
                    "updated_at": "2026-06-28T00:00:00+00:00",
                }
            ],
            "pokemon_set_market_dashboard_snapshot_latest": lambda _query: [],
        }
    )
    monkeypatch.setattr(pokemon_public_snapshot_service, "public_read_client", client)

    payload = pokemon_public_snapshot_service.get_pokemon_set_shell_snapshot_payload(_TEST_UUID)

    assert payload["interpretation"]["meta"]["packScore"]["label"] == "Very Weak Value Profile"
    assert payload["interpretation"]["meta"]["packScore"]["summary"] == "This set trails the field."
    assert payload["interpretation"]["meta"]["set_intelligence"][0]["tier"] == "C"


def test_shell_snapshot_includes_checklist_set_value_history(monkeypatch):
    """The shell must include a standard-scope set value history so the title-card
    sparkline renders immediately on every tab, not only after Overview loads."""

    def read_market_dashboard(query):
        assert ("set_id", _TEST_UUID) in query.eq_filters
        return [
            {
                "window_key": "30d",
                "set_value_histories_json": {
                    "standard": [
                        {"date": "2026-06-01", "setValue": 100.0},
                        {"date": "2026-06-28", "setValue": 123.45},
                    ]
                },
            },
            {
                "window_key": "365d",
                "set_value_histories_json": {
                    "standard": [{"date": "2025-07-01", "setValue": 50.0}]
                },
            },
        ]

    client = _Client(
        {
            "pokemon_set_page_snapshot_latest": lambda _query: [
                {
                    "set_id": _TEST_UUID,
                    "set_identity_json": {"id": _TEST_UUID, "name": "Shell Set"},
                    "title_card_json": {},
                    "rip_summary_json": {},
                    "market_summary_json": {},
                    "risk_summary_json": {},
                    "concentration_json": {},
                    "desirability_summary_json": {},
                    "as_of": "2026-06-28",
                    "source_updated_at": "2026-06-28T00:00:00+00:00",
                    "updated_at": "2026-06-28T00:00:00+00:00",
                }
            ],
            "pokemon_set_market_dashboard_snapshot_latest": read_market_dashboard,
        }
    )
    monkeypatch.setattr(pokemon_public_snapshot_service, "public_read_client", client)

    payload = pokemon_public_snapshot_service.get_pokemon_set_shell_snapshot_payload(_TEST_UUID)

    # Prefers the 30d window row's history over the 365d row when both exist.
    assert payload["setValueHistoriesByScope"]["standard"][-1]["setValue"] == 123.45
    assert len(payload["setValueHistoriesByScope"]["standard"]) == 2
    assert payload["set_value_histories_by_scope"] == payload["setValueHistoriesByScope"]


def test_shell_snapshot_tolerates_missing_market_dashboard_row(monkeypatch):
    """A missing/empty market dashboard row must not fail the shell request."""
    client = _Client(
        {
            "pokemon_set_page_snapshot_latest": lambda _query: [
                {
                    "set_id": _TEST_UUID,
                    "set_identity_json": {"id": _TEST_UUID, "name": "Shell Set"},
                    "title_card_json": {},
                    "rip_summary_json": {},
                    "market_summary_json": {},
                    "risk_summary_json": {},
                    "concentration_json": {},
                    "desirability_summary_json": {},
                    "as_of": "2026-06-28",
                    "source_updated_at": "2026-06-28T00:00:00+00:00",
                    "updated_at": "2026-06-28T00:00:00+00:00",
                }
            ],
            "pokemon_set_market_dashboard_snapshot_latest": lambda _query: [],
        }
    )
    monkeypatch.setattr(pokemon_public_snapshot_service, "public_read_client", client)

    payload = pokemon_public_snapshot_service.get_pokemon_set_shell_snapshot_payload(_TEST_UUID)

    assert payload["setValueHistoriesByScope"] == {}
    assert payload["set"]["id"] == _TEST_UUID
