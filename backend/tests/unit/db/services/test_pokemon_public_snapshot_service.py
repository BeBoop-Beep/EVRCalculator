import pytest
from postgrest.exceptions import APIError

from backend.db.services import pokemon_public_snapshot_service, pokemon_set_market_service, public_read_retry


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


@pytest.fixture(autouse=True)
def reset_public_read_circuit():
    public_read_retry._reset_public_read_circuit_breaker_for_tests()
    yield
    public_read_retry._reset_public_read_circuit_breaker_for_tests()


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
                        "meta": {
                            "warnings": ["existing warning"],
                            "snapshot": {"fallbackReason": "older_failure"},
                        },
                    },
                    "default_target_json": {"target_id": "set-1", "target_type": "set"},
                }
            ],
        }
    )
    monkeypatch.setattr(pokemon_public_snapshot_service, "public_read_client", client)
    monkeypatch.setattr(
        pokemon_public_snapshot_service,
        "create_public_read_client",
        lambda: (_ for _ in ()).throw(AssertionError("fresh client should not be created")),
    )
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
    assert payload["meta"]["snapshot"]["isStaleFallback"] is False
    assert "fallbackReason" not in payload["meta"]["snapshot"]


def test_rankings_snapshot_retries_with_fresh_client_and_returns_normal_data(monkeypatch):
    def fail(_query):
        raise APIError({"message": "schema cache unavailable", "code": "PGRST002", "hint": None, "details": None})

    initial_client = _Client({"pokemon_explore_rankings_snapshot_latest": fail})
    fresh_client = _Client(
        {
            "pokemon_explore_rankings_snapshot_latest": lambda _query: [
                {
                    "updated_at": "2026-07-13T00:00:00Z",
                    "ranking_payload_json": {
                        "targets": [
                            {
                                "id": "set-1",
                                "target_id": "set-1",
                                "target_type": "set",
                                "is_opening_set": True,
                            }
                        ],
                        "meta": {
                            "snapshot": {
                                "isStaleFallback": True,
                                "fallbackReason": "older_failure",
                            }
                        },
                    },
                    "default_target_json": {"target_id": "set-1", "target_type": "set"},
                }
            ]
        }
    )
    factories = []
    monkeypatch.setattr(pokemon_public_snapshot_service, "public_read_client", initial_client)
    monkeypatch.setattr(
        pokemon_public_snapshot_service,
        "create_public_read_client",
        lambda: factories.append(fresh_client) or fresh_client,
    )
    monkeypatch.setattr(
        pokemon_public_snapshot_service,
        "_enrich_rankings_payload_with_checklist_set_values",
        lambda payload: payload,
    )

    payload = pokemon_public_snapshot_service.get_pokemon_explore_rankings_snapshot_payload(limit=10)

    assert payload["targets"][0]["id"] == "set-1"
    assert payload["meta"]["snapshot"]["isStaleFallback"] is False
    assert "fallbackReason" not in payload["meta"]["snapshot"]
    assert factories == [fresh_client]


def test_rankings_snapshot_transient_failure_returns_503_not_generic_500(monkeypatch):
    pokemon_public_snapshot_service._LAST_SUCCESSFUL_RANKINGS_PAYLOADS.clear()

    def fail(_query):
        raise APIError({"message": "schema cache unavailable", "code": "PGRST002", "hint": None, "details": None})

    monkeypatch.setattr(
        pokemon_public_snapshot_service,
        "public_read_client",
        _Client({"pokemon_explore_rankings_snapshot_latest": fail}),
    )
    monkeypatch.setattr(
        pokemon_public_snapshot_service,
        "create_public_read_client",
        lambda: _Client({"pokemon_explore_rankings_snapshot_latest": fail}),
    )

    with pytest.raises(pokemon_public_snapshot_service.ExploreRipStatisticsTargetsError) as raised:
        pokemon_public_snapshot_service.get_pokemon_explore_rankings_snapshot_payload(limit=10)

    assert raised.value.status_code == 503
    assert raised.value.code == "RIP_STATISTICS_TARGETS_TEMPORARILY_UNAVAILABLE"
    assert raised.value.retry_after_seconds == 15


def test_rankings_snapshot_transient_failure_can_serve_explicit_stale_fallback(monkeypatch):
    pokemon_public_snapshot_service._LAST_SUCCESSFUL_RANKINGS_PAYLOADS.clear()
    state = {"fail": False, "calls": 0}

    def rows(_query):
        state["calls"] += 1
        if state["fail"]:
            raise APIError({"message": "schema cache unavailable", "code": "PGRST002", "hint": None, "details": None})
        return [{
            "updated_at": "2026-07-13T00:00:00Z",
            "ranking_payload_json": {
                "targets": [{"id": "set-1", "target_id": "set-1", "target_type": "set", "is_opening_set": True}],
                "meta": {},
            },
            "default_target_json": {"target_id": "set-1", "target_type": "set"},
        }]

    monkeypatch.setattr(
        pokemon_public_snapshot_service,
        "public_read_client",
        _Client({"pokemon_explore_rankings_snapshot_latest": rows}),
    )
    monkeypatch.setattr(
        pokemon_public_snapshot_service,
        "create_public_read_client",
        lambda: _Client({"pokemon_explore_rankings_snapshot_latest": rows}),
    )
    monkeypatch.setattr(
        pokemon_public_snapshot_service,
        "_enrich_rankings_payload_with_checklist_set_values",
        lambda payload: payload,
    )

    fresh = pokemon_public_snapshot_service.get_pokemon_explore_rankings_snapshot_payload(limit=10)
    state["fail"] = True
    fallback = pokemon_public_snapshot_service.get_pokemon_explore_rankings_snapshot_payload(limit=10)

    assert fallback["targets"] == fresh["targets"]
    assert fallback["meta"]["snapshot"]["isStaleFallback"] is True
    assert fallback["meta"]["snapshot"]["fallbackReason"] == "transient_data_service_failure"
    assert state["calls"] == 3
    authoritative = pokemon_public_snapshot_service._LAST_SUCCESSFUL_RANKINGS_PAYLOADS[10]
    assert authoritative["meta"]["snapshot"]["isStaleFallback"] is False
    assert "fallbackReason" not in authoritative["meta"]["snapshot"]


def test_rankings_snapshot_non_transient_failure_remains_500(monkeypatch):
    def fail(_query):
        raise APIError({"message": "missing column", "code": "42703", "hint": None, "details": None})

    monkeypatch.setattr(
        pokemon_public_snapshot_service,
        "public_read_client",
        _Client({"pokemon_explore_rankings_snapshot_latest": fail}),
    )
    factories = []
    monkeypatch.setattr(
        pokemon_public_snapshot_service,
        "create_public_read_client",
        lambda: factories.append(object()) or object(),
    )

    with pytest.raises(pokemon_public_snapshot_service.ExploreRipStatisticsTargetsError) as raised:
        pokemon_public_snapshot_service.get_pokemon_explore_rankings_snapshot_payload(limit=10)

    assert raised.value.status_code == 500
    assert raised.value.code == "RIP_STATISTICS_TARGETS_SNAPSHOT_FAILED"
    assert factories == []


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


def test_market_dashboard_reader_selects_payload_json_for_market_movers(monkeypatch):
    """The market dashboard reader must select payload_json — it's the only source of marketMovers."""
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
                "payload_json": {"marketMovers": {"heatingUp": [], "coolingOff": [], "all": []}},
            }
        ]

    client = _Client({"pokemon_set_market_dashboard_snapshot_latest": read_dashboard})
    monkeypatch.setattr(pokemon_public_snapshot_service, "public_read_client", client)

    payload = pokemon_public_snapshot_service.get_pokemon_set_market_dashboard_snapshot_payload(_TEST_UUID, window="365d")

    assert len(captured_queries) == 1
    selected_fields = captured_queries[0].select_fields
    assert "payload_json" in selected_fields
    assert "set_value_histories_json" in selected_fields
    assert "top_chase_cards_json" in selected_fields

    assert payload["set"]["id"] == _TEST_UUID
    assert payload["setValueHistoriesByScope"]["standard"][0]["setValue"] == 200.0
    assert payload["meta"]["snapshot"]["source"] == "pokemon_set_market_dashboard_snapshot_latest"


def test_market_dashboard_snapshot_returns_market_movers_from_payload_json(monkeypatch):
    """marketMovers/market_movers must be read from the stored payload_json blob, not dropped."""
    heating_up = [{"cardId": "card-1", "name": "Hot Card", "change30dPercent": 42.0}]
    cooling_off = [{"cardId": "card-2", "name": "Cold Card", "change30dPercent": -12.0}]

    def read_dashboard(query):
        return [
            {
                "set_id": "set-1",
                "window_key": "365d",
                "latest_market_date": "2026-06-28",
                "updated_at": "2026-06-28T00:00:00+00:00",
                "set_value_histories_json": {"standard": [{"date": "2026-06-28", "setValue": 200.0}]},
                "performance_vs_cost_history_json": [],
                "top_chase_cards_json": [],
                "top_chase_card_histories_json": {},
                "available_scopes_json": [],
                "payload_json": {
                    "marketMovers": {"heatingUp": heating_up, "coolingOff": cooling_off, "all": heating_up + cooling_off},
                    "market_movers": {"heatingUp": heating_up, "coolingOff": cooling_off, "all": heating_up + cooling_off},
                },
            }
        ]

    client = _Client(
        {
            "sets": lambda _query: [{"id": "set-1", "name": "Set One", "canonical_key": "set-one"}],
            "pokemon_set_market_dashboard_snapshot_latest": read_dashboard,
        }
    )
    monkeypatch.setattr(pokemon_public_snapshot_service, "public_read_client", client)

    payload = pokemon_public_snapshot_service.get_pokemon_set_market_dashboard_snapshot_payload("set-1", window="365d")

    for key in ("marketMovers", "market_movers"):
        assert payload[key]["heatingUp"] == heating_up
        assert payload[key]["coolingOff"] == cooling_off
        assert payload[key]["all"] == heating_up + cooling_off


def test_market_dashboard_snapshot_defaults_market_movers_when_missing_from_payload_json(monkeypatch):
    """A stored snapshot without marketMovers in payload_json still returns the empty shape, not a KeyError."""

    def read_dashboard(query):
        return [
            {
                "set_id": "set-1",
                "window_key": "365d",
                "latest_market_date": "2026-06-28",
                "updated_at": "2026-06-28T00:00:00+00:00",
                "set_value_histories_json": {"standard": [{"date": "2026-06-28", "setValue": 200.0}]},
                "performance_vs_cost_history_json": [],
                "top_chase_cards_json": [],
                "top_chase_card_histories_json": {},
                "available_scopes_json": [],
                "payload_json": {},
            }
        ]

    client = _Client(
        {
            "sets": lambda _query: [{"id": "set-1", "name": "Set One", "canonical_key": "set-one"}],
            "pokemon_set_market_dashboard_snapshot_latest": read_dashboard,
        }
    )
    monkeypatch.setattr(pokemon_public_snapshot_service, "public_read_client", client)

    payload = pokemon_public_snapshot_service.get_pokemon_set_market_dashboard_snapshot_payload("set-1", window="365d")

    for key in ("marketMovers", "market_movers"):
        assert payload[key] == {"heatingUp": [], "coolingOff": [], "all": []}


def test_market_dashboard_snapshot_returns_market_movers_by_window_from_payload_json(monkeypatch):
    """marketMoversByWindow/market_movers_by_window must expose 1D/7D/30D, with marketMovers as the 30D compat field."""
    by_window = {
        "1D": {"heatingUp": [{"cardId": "card-1d"}], "coolingOff": [], "all": [{"cardId": "card-1d"}]},
        "7D": {"heatingUp": [{"cardId": "card-7d"}], "coolingOff": [], "all": [{"cardId": "card-7d"}]},
        "30D": {"heatingUp": [{"cardId": "card-30d"}], "coolingOff": [], "all": [{"cardId": "card-30d"}]},
    }
    by_window_snake = {
        "1D": {"heating_up": [{"cardId": "card-1d"}], "cooling_off": [], "all": [{"cardId": "card-1d"}]},
        "7D": {"heating_up": [{"cardId": "card-7d"}], "cooling_off": [], "all": [{"cardId": "card-7d"}]},
        "30D": {"heating_up": [{"cardId": "card-30d"}], "cooling_off": [], "all": [{"cardId": "card-30d"}]},
    }

    def read_dashboard(query):
        return [
            {
                "set_id": "set-1",
                "window_key": "365d",
                "latest_market_date": "2026-06-28",
                "updated_at": "2026-06-28T00:00:00+00:00",
                "set_value_histories_json": {"standard": [{"date": "2026-06-28", "setValue": 200.0}]},
                "performance_vs_cost_history_json": [],
                "top_chase_cards_json": [],
                "top_chase_card_histories_json": {},
                "available_scopes_json": [],
                "payload_json": {
                    "marketMovers": by_window["30D"],
                    "market_movers": by_window_snake["30D"],
                    "marketMoversByWindow": by_window,
                    "market_movers_by_window": by_window_snake,
                },
            }
        ]

    client = _Client(
        {
            "sets": lambda _query: [{"id": "set-1", "name": "Set One", "canonical_key": "set-one"}],
            "pokemon_set_market_dashboard_snapshot_latest": read_dashboard,
        }
    )
    monkeypatch.setattr(pokemon_public_snapshot_service, "public_read_client", client)

    payload = pokemon_public_snapshot_service.get_pokemon_set_market_dashboard_snapshot_payload("set-1", window="365d")

    # Both the camelCase and snake_case top-level keys resolve to the same picked
    # dict (camelCase preferred), mirroring the existing marketMovers/market_movers pattern.
    assert payload["marketMoversByWindow"] == by_window
    assert payload["market_movers_by_window"] == by_window
    for key in ("1D", "7D", "30D"):
        assert payload["marketMoversByWindow"][key]["heatingUp"][0]["cardId"] == f"card-{key.lower()}"

    # Backward compatibility: marketMovers/market_movers must still be the 30D entry.
    assert payload["marketMovers"] == by_window["30D"]
    assert payload["market_movers"] == by_window["30D"]


def test_market_dashboard_snapshot_defaults_market_movers_by_window_to_30d_when_missing(monkeypatch):
    """Snapshots written before per-window movers existed must still serve the 30D tab via fallback."""
    thirty_day_movers = {"heatingUp": [{"cardId": "card-30d"}], "coolingOff": [], "all": [{"cardId": "card-30d"}]}

    def read_dashboard(query):
        return [
            {
                "set_id": "set-1",
                "window_key": "365d",
                "latest_market_date": "2026-06-28",
                "updated_at": "2026-06-28T00:00:00+00:00",
                "set_value_histories_json": {"standard": [{"date": "2026-06-28", "setValue": 200.0}]},
                "performance_vs_cost_history_json": [],
                "top_chase_cards_json": [],
                "top_chase_card_histories_json": {},
                "available_scopes_json": [],
                "payload_json": {"marketMovers": thirty_day_movers, "market_movers": thirty_day_movers},
            }
        ]

    client = _Client(
        {
            "sets": lambda _query: [{"id": "set-1", "name": "Set One", "canonical_key": "set-one"}],
            "pokemon_set_market_dashboard_snapshot_latest": read_dashboard,
        }
    )
    monkeypatch.setattr(pokemon_public_snapshot_service, "public_read_client", client)

    payload = pokemon_public_snapshot_service.get_pokemon_set_market_dashboard_snapshot_payload("set-1", window="365d")

    assert payload["marketMoversByWindow"] == {"30D": thirty_day_movers}
    assert payload["market_movers_by_window"] == {"30D": thirty_day_movers}


def test_shell_snapshot_reader_does_not_select_whole_payload_json(monkeypatch):
    """The shell may project exact JSON paths but must never pull the whole payload_json blob."""
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
    assert "payload_json" not in {field.strip() for field in selected_fields.split(",")}
    assert "payload_json->summary->relative_experience_score" in selected_fields
    assert "set_identity_json" in selected_fields
    assert "title_card_json" in selected_fields

    assert payload["set"]["id"] == _TEST_UUID
    assert payload["set"]["name"] == "Shell Set"
    assert payload["summary"]["pack_score"] == 71.5
    assert payload["summary"]["pack_rank"] == 3
    assert payload["summary"]["simulated_set_value"] == 199.5
    assert payload["summary"]["pack_tier"] == "A"
    assert payload["meta"]["snapshot"]["source"] == "pokemon_set_page_snapshot_latest"
    assert payload["meta"]["timings"]["snapshot_query_ms"] is not None


def test_shell_snapshot_prefers_tracked_lens_values_projected_from_payload_summary(monkeypatch):
    row = {
        **_SHELL_ROW_FIXTURE,
        "rip_summary_json": {
            **_SHELL_ROW_FIXTURE["rip_summary_json"],
            "relative_experience_score": 1,
            "relative_biggest_upside_score": 2,
        },
        "tracked_lens_relative_experience_score": 66,
        "tracked_lens_relative_chase_potential_score": 75.78,
        "tracked_lens_relative_biggest_upside_score": 82.41462252449374,
        "tracked_lens_relative_average_return_score": 74.99503475670308,
        "tracked_lens_experience_rank": 8,
        "tracked_lens_chase_potential_rank": 7,
        "tracked_lens_biggest_upside_rank": 7,
        "tracked_lens_mean_value_to_cost_rank": 6,
    }
    client = _Client(
        {
            "pokemon_set_page_snapshot_latest": lambda _query: [row],
            "pokemon_set_market_dashboard_snapshot_latest": lambda _query: [],
        }
    )
    monkeypatch.setattr(pokemon_public_snapshot_service, "public_read_client", client)

    payload = pokemon_public_snapshot_service.get_pokemon_set_shell_snapshot_payload(_TEST_UUID)

    assert payload["summary"]["relative_experience_score"] == 66
    assert payload["summary"]["relative_chase_potential_score"] == 75.78
    assert payload["summary"]["relative_biggest_upside_score"] == 82.41462252449374
    assert payload["summary"]["relative_average_return_score"] == 74.99503475670308
    assert payload["summary"]["experience_rank"] == 8
    assert payload["summary"]["mean_value_to_cost_rank"] == 6


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
    assert "set_value_histories_by_scope" not in payload


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


# ---------------------------------------------------------------------------
# Phase 5C: shell payload slimming regression coverage
# ---------------------------------------------------------------------------

_SHELL_ROW_FIXTURE = {
    "set_id": _TEST_UUID,
    "set_identity_json": {"id": _TEST_UUID, "name": "Shell Set", "slug": "shell-set"},
    "title_card_json": {"pack_score": 71.5, "pack_tier": "A"},
    "rip_summary_json": {"pack_rank": 3, "profit_score": 60.1},
    "market_summary_json": {"simulated_set_value": 199.5, "pack_cost": 4.99},
    "risk_summary_json": {"coefficient_of_variation": 1.2},
    "concentration_json": {"hhi_ev_concentration": 0.3},
    "desirability_summary_json": {"score": 0.8},
    "set_intelligence_json": {"packScore": "Weak", "meta": {"packScore": {"label": "Weak"}}},
    "as_of": "2026-06-28",
    "source_updated_at": "2026-06-28T00:00:00+00:00",
    "updated_at": "2026-06-28T00:00:00+00:00",
}


def _bloated_set_value_history_point(date_str, value):
    """Mirrors the ~20-field dual-cased shape set_value_histories_json rows
    actually carry in prod (see the real fixture captured against
    pokemon_set_market_dashboard_snapshot_latest during the Phase 5C audit)."""
    return {
        "date": date_str,
        "source": "card_variant_price_observations_near_mint_latest_as_of_day:standard:card_variants_by_set",
        "provider": "card_variant_price_observations_near_mint_latest_as_of_day:standard:card_variants_by_set",
        "setValue": value,
        "set_value": value,
        "createdAt": "2026-06-18T21:35:22.405422+00:00",
        "created_at": "2026-06-18T21:35:22.405422+00:00",
        "updatedAt": "2026-06-20T16:22:37.013731+00:00",
        "updated_at": "2026-06-20T16:22:37.013731+00:00",
        "sourceDate": date_str,
        "source_date": date_str,
        "valueScope": "standard",
        "value_scope": "standard",
        "totalCardCount": 123,
        "total_card_count": 123,
        "cardCountPriced": 123,
        "card_count_priced": 123,
        "calculationRunId": None,
        "calculation_run_id": None,
        "isCarriedForward": False,
        "is_carried_forward": False,
    }


def test_shell_snapshot_excludes_dual_cased_header_column_duplicates(monkeypatch):
    """The shell must not re-expose title_card/rip_summary/market_summary/risk_summary/
    concentration/desirability_summary as standalone top-level keys (camelCase or
    snake_case) — no frontend shell consumer reads them, only `summary` does."""
    client = _Client(
        {
            "pokemon_set_page_snapshot_latest": lambda _query: [_SHELL_ROW_FIXTURE],
            "pokemon_set_market_dashboard_snapshot_latest": lambda _query: [],
        }
    )
    monkeypatch.setattr(pokemon_public_snapshot_service, "public_read_client", client)

    payload = pokemon_public_snapshot_service.get_pokemon_set_shell_snapshot_payload(_TEST_UUID)

    assert set(payload.keys()) == {"set", "summary", "interpretation", "setValueHistoriesByScope", "meta"}
    for removed_key in (
        "titleCard",
        "title_card",
        "ripSummary",
        "rip_summary",
        "marketSummary",
        "market_summary",
        "riskSummary",
        "risk_summary",
        "concentration",
        "desirabilitySummary",
        "desirability_summary",
        "set_value_histories_by_scope",
    ):
        assert removed_key not in payload
    # ...but the fields still reach the client through the flattened summary.
    assert payload["summary"]["pack_tier"] == "A"
    assert payload["summary"]["pack_rank"] == 3
    assert payload["summary"]["simulated_set_value"] == 199.5
    assert payload["summary"]["coefficient_of_variation"] == 1.2
    assert payload["summary"]["hhi_ev_concentration"] == 0.3


def test_shell_snapshot_excludes_cards_market_dashboard_and_pull_rates(monkeypatch):
    """The shell must never carry full-cards, market-dashboard, or pull-rates data —
    those are separate slim contracts fetched independently by their own tabs."""
    client = _Client(
        {
            "pokemon_set_page_snapshot_latest": lambda _query: [_SHELL_ROW_FIXTURE],
            "pokemon_set_market_dashboard_snapshot_latest": lambda _query: [],
        }
    )
    monkeypatch.setattr(pokemon_public_snapshot_service, "public_read_client", client)

    payload = pokemon_public_snapshot_service.get_pokemon_set_shell_snapshot_payload(_TEST_UUID)

    for absent_key in (
        "cards",
        "marketDashboard",
        "market_dashboard",
        "pullRates",
        "pull_rate_assumptions",
        "topChaseCards",
        "topChaseCardHistories",
        "marketMovers",
        "distributionBins",
        "validationCards",
        "cardDesirabilityValidation",
    ):
        assert absent_key not in payload
        assert absent_key not in payload.get("summary", {})


def test_shell_snapshot_history_points_are_slimmed_to_four_camel_case_fields(monkeypatch):
    """set_value_histories_json rows carry ~20 dual-cased fields per point (shared
    with the Overview market dashboard); the shell must slim each point down to
    only what the title-card sparkline reads: date, setValue, sourceDate,
    isCarriedForward — camelCase only, no snake_case siblings."""

    def read_market_dashboard(_query):
        return [
            {
                "window_key": "30d",
                "set_value_histories_json": {
                    "standard": [
                        _bloated_set_value_history_point("2026-06-01", 100.0),
                        _bloated_set_value_history_point("2026-06-28", 123.45),
                    ]
                },
            }
        ]

    client = _Client(
        {
            "pokemon_set_page_snapshot_latest": lambda _query: [_SHELL_ROW_FIXTURE],
            "pokemon_set_market_dashboard_snapshot_latest": read_market_dashboard,
        }
    )
    monkeypatch.setattr(pokemon_public_snapshot_service, "public_read_client", client)

    payload = pokemon_public_snapshot_service.get_pokemon_set_shell_snapshot_payload(_TEST_UUID)

    points = payload["setValueHistoriesByScope"]["standard"]
    assert len(points) == 2
    for point in points:
        assert set(point.keys()) == {"date", "setValue", "sourceDate", "isCarriedForward"}
    assert points[-1]["setValue"] == 123.45
    assert points[-1]["date"] == "2026-06-28"


def test_shell_snapshot_stays_under_75kb_budget_for_large_fixture(monkeypatch):
    """A representative large set (long price history + a sizable interpretation
    payload) must still serialize under the shell's 75KB budget."""
    import json

    large_interpretation = {
        "packScore": "Above Average Value Profile",
        "meta": {
            "packScore": {"label": "Above Average Value Profile", "summary": "x" * 500},
            "profit": {"label": "Profit", "summary": "y" * 500},
            "safety": {"label": "Safety", "summary": "z" * 500},
            "desirability": {"label": "Desirability", "summary": "w" * 500},
            "stability": {"label": "Stability", "summary": "v" * 500},
            "set_intelligence": [{"key": f"lens-{i}", "tier": "B", "summary": "n" * 200} for i in range(10)],
        },
    }
    row = {**_SHELL_ROW_FIXTURE, "set_intelligence_json": large_interpretation}

    def read_market_dashboard(_query):
        from datetime import date, timedelta

        start = date(2024, 1, 1)
        history = [
            _bloated_set_value_history_point((start + timedelta(days=i)).isoformat(), 100.0 + i)
            for i in range(400)
        ]
        return [{"window_key": "30d", "set_value_histories_json": {"standard": history}}]

    client = _Client(
        {
            "pokemon_set_page_snapshot_latest": lambda _query: [row],
            "pokemon_set_market_dashboard_snapshot_latest": read_market_dashboard,
        }
    )
    monkeypatch.setattr(pokemon_public_snapshot_service, "public_read_client", client)

    payload = pokemon_public_snapshot_service.get_pokemon_set_shell_snapshot_payload(_TEST_UUID)

    byte_size = len(json.dumps(payload, default=str).encode("utf-8"))
    assert byte_size < 75_000, f"shell payload is {byte_size} bytes, over the 75,000B budget"


def test_shell_snapshot_missing_row_fallback_excludes_dual_cased_duplicates(monkeypatch):
    """The missing-snapshot fallback shell shape must match the slim contract too —
    no dual-cased header duplicates, camelCase-only top-level keys."""
    client = _Client(
        {
            "pokemon_set_page_snapshot_latest": lambda _query: [],
            "sets": lambda _query: [{"id": _TEST_UUID, "name": "Fallback Set", "canonical_key": "fallback-set"}],
        }
    )
    monkeypatch.setattr(pokemon_public_snapshot_service, "public_read_client", client)

    payload = pokemon_public_snapshot_service.get_pokemon_set_shell_snapshot_payload(_TEST_UUID)

    assert set(payload.keys()) == {"set", "summary", "interpretation", "setValueHistoriesByScope", "meta"}
    assert payload["summary"] == {}
    assert payload["setValueHistoriesByScope"] == {}
    assert payload["meta"]["fallback"] is True


# ---------------------------------------------------------------------------
# Shared resolver wiring
# ---------------------------------------------------------------------------


def test_resolve_set_row_delegates_to_shared_resolver_with_its_own_client(monkeypatch):
    """Guards against re-divergence: this module must delegate set-identifier
    resolution to the single shared implementation in pokemon_set_market_service,
    passing this module's own (patchable) public_read_client explicitly rather
    than silently falling back to pokemon_set_market_service's client — a bare
    `_resolve_set_row = resolve_pokemon_set_identifier` alias would resolve
    public_read_client from pokemon_set_market_service's globals instead of
    this module's, so a public_read_client monkeypatch made in this module
    would silently miss every call routed through the shared resolver."""
    calls = []

    def fake_resolver(set_id, *, client=None):
        calls.append((set_id, client))
        return {"id": "resolved"}

    sentinel_client = object()
    monkeypatch.setattr(pokemon_public_snapshot_service, "resolve_pokemon_set_identifier", fake_resolver)
    monkeypatch.setattr(pokemon_public_snapshot_service, "public_read_client", sentinel_client)

    row = pokemon_public_snapshot_service._resolve_set_row("prismatic-evolutions")

    assert row == {"id": "resolved"}
    assert calls == [("prismatic-evolutions", sentinel_client)]


# ---------------------------------------------------------------------------
# get_pokemon_set_overview_snapshot_payload
# ---------------------------------------------------------------------------


def _overview_dashboard_row(**overrides):
    row = {
        "set_id": _TEST_UUID,
        "window_key": "365d",
        "set_value_histories_json": {
            "standard": [{"date": "2026-06-01", "setValue": 100.0}, {"date": "2026-06-30", "setValue": 123.45}],
        },
        "performance_vs_cost_history_json": [
            {"date": "2026-06-30", "meanValue": 5.5, "packCost": 4.99},
        ],
        "top_chase_cards_json": [{"cardId": "card-1", "name": "Should Not Appear"}],
        "top_chase_card_histories_json": {"card-1": [{"date": "2026-06-30", "marketPrice": 12.0}]},
        "available_scopes_json": [{"key": "standard", "label": "Standard", "latestDate": "2026-06-30"}],
        "latest_market_date": "2026-06-30",
        "updated_at": "2026-06-30T00:00:00+00:00",
        "payload_json": {
            "marketMovers": {"heatingUp": [{"cardId": "card-1"}], "coolingOff": [], "all": []},
            "marketMoversByWindow": {"30D": {"heatingUp": [], "coolingOff": [], "all": []}},
        },
    }
    row.update(overrides)
    return row


def test_overview_payload_excludes_top_chase_and_market_movers(monkeypatch):
    """The overview payload must never carry topChaseCards, topChaseCardHistories,
    marketMovers, or marketMoversByWindow — those live on the market dashboard
    and top-chase/movers endpoints instead."""
    captured_queries = []

    def read_dashboard(query):
        captured_queries.append(query)
        return [_overview_dashboard_row()]

    client = _Client({"pokemon_set_market_dashboard_snapshot_latest": read_dashboard})
    monkeypatch.setattr(pokemon_public_snapshot_service, "public_read_client", client)

    payload = pokemon_public_snapshot_service.get_pokemon_set_overview_snapshot_payload(_TEST_UUID)

    assert len(captured_queries) == 1
    selected_fields = captured_queries[0].select_fields
    assert "top_chase_cards_json" not in selected_fields
    assert "top_chase_card_histories_json" not in selected_fields
    assert "payload_json" not in selected_fields

    assert "topChaseCards" not in payload
    assert "topChaseCardHistories" not in payload
    assert "marketMovers" not in payload
    assert "marketMoversByWindow" not in payload

    assert payload["set"]["id"] == _TEST_UUID
    assert payload["setValueHistoriesByScope"]["standard"][1]["setValue"] == 123.45
    assert payload["performanceVsCostHistory"][0]["meanValue"] == 5.5
    assert payload["availableScopes"][0]["key"] == "standard"
    assert payload["latestMarketDate"] == "2026-06-30"
    assert payload["meta"]["snapshot"]["source"] == "pokemon_set_market_dashboard_snapshot_latest"
    assert payload["meta"]["timings"]["snapshotQueryMs"] is not None


def test_overview_snapshot_columns_do_not_include_payload_json():
    """/overview must never select the large monolithic payload_json column —
    the split columns are the only source of overview data."""
    selected = {column.strip() for column in pokemon_public_snapshot_service._OVERVIEW_SNAPSHOT_COLUMNS.split(",")}
    assert "payload_json" not in selected
    assert selected == {
        "set_id",
        "window_key",
        "set_value_histories_json",
        "performance_vs_cost_history_json",
        "available_scopes_json",
        "latest_market_date",
        "updated_at",
    }


def test_overview_payload_treats_missing_split_columns_as_empty_structures(monkeypatch):
    """A row with null split columns yields empty structures — there is no
    payload_json fallback anymore, and payload_json is never emitted."""
    row = _overview_dashboard_row(
        set_value_histories_json=None,
        performance_vs_cost_history_json=None,
        available_scopes_json=None,
    )
    client = _Client({"pokemon_set_market_dashboard_snapshot_latest": lambda _q: [row]})
    monkeypatch.setattr(pokemon_public_snapshot_service, "public_read_client", client)

    payload = pokemon_public_snapshot_service.get_pokemon_set_overview_snapshot_payload(_TEST_UUID)

    assert payload["setValueHistoriesByScope"] == {}
    assert payload["performanceVsCostHistory"] == []
    assert payload["availableScopes"] == []
    assert "payload_json" not in payload
    assert "payloadJson" not in payload


def test_overview_payload_returns_performance_history_from_split_column(monkeypatch):
    """/overview serves performanceVsCostHistory straight from
    performance_vs_cost_history_json, ignoring any payload_json content."""
    row = _overview_dashboard_row(
        performance_vs_cost_history_json=[{"date": "2026-06-30", "meanValue": 7.7, "packCost": 4.99}],
        payload_json={
            "performanceVsCostHistory": [{"date": "2026-06-30", "meanValue": 9.9, "packCost": 4.99}],
        },
    )
    client = _Client({"pokemon_set_market_dashboard_snapshot_latest": lambda _q: [row]})
    monkeypatch.setattr(pokemon_public_snapshot_service, "public_read_client", client)

    payload = pokemon_public_snapshot_service.get_pokemon_set_overview_snapshot_payload(_TEST_UUID)

    assert payload["performanceVsCostHistory"] == [{"date": "2026-06-30", "meanValue": 7.7, "packCost": 4.99}]
    assert "payload_json" not in payload
    assert "payloadJson" not in payload


def test_overview_payload_resolves_hyphenated_slug(monkeypatch):
    """Regression test: prismatic-evolutions must resolve through the overview
    endpoint service the same way it does through value-history and the
    market dashboard, via the shared normalized-slug fallback."""
    sets_rows = [
        {"id": "set-uuid-1", "name": "Prismatic Evolutions", "canonical_key": "prismaticEvolutions", "pokemon_api_set_id": "sv8pt5"}
    ]

    def read_sets(query):
        if query.eq_filters:
            field, value = query.eq_filters[-1]
            return [row for row in sets_rows if row.get(field) == value]
        return sets_rows

    dashboard_row = _overview_dashboard_row(set_id="set-uuid-1")

    client = _Client(
        {
            "sets": read_sets,
            "pokemon_set_market_dashboard_snapshot_latest": lambda _q: [dashboard_row],
        }
    )
    monkeypatch.setattr(pokemon_public_snapshot_service, "public_read_client", client)
    monkeypatch.setattr(pokemon_set_market_service, "public_read_client", client)

    payload = pokemon_public_snapshot_service.get_pokemon_set_overview_snapshot_payload("prismatic-evolutions")

    assert payload["set"]["id"] == "set-uuid-1"
    assert payload["setValueHistoriesByScope"]["standard"][1]["setValue"] == 123.45


def test_overview_payload_serialized_size_is_under_250kb(monkeypatch):
    """Payload budget: a representative worst-case fixture (full-year daily
    histories across 3 scopes plus a full-year performance history) must
    serialize under 250KB, since topChaseCards/topChaseCardHistories/
    marketMovers are never included."""
    import json

    def _daily_history(days, value_key):
        return [
            {"date": f"2026-{(day % 12) + 1:02d}-{(day % 28) + 1:02d}", value_key: round(100 + day * 0.1, 2)}
            for day in range(days)
        ]

    row = _overview_dashboard_row(
        set_value_histories_json={
            "standard": _daily_history(365, "setValue"),
            "hits": _daily_history(365, "setValue"),
            "top10": _daily_history(365, "setValue"),
        },
        performance_vs_cost_history_json=_daily_history(365, "meanValue"),
    )
    client = _Client({"pokemon_set_market_dashboard_snapshot_latest": lambda _q: [row]})
    monkeypatch.setattr(pokemon_public_snapshot_service, "public_read_client", client)

    payload = pokemon_public_snapshot_service.get_pokemon_set_overview_snapshot_payload(_TEST_UUID)

    serialized_bytes = len(json.dumps(payload, default=str).encode("utf-8"))
    assert serialized_bytes < 250_000, f"overview payload was {serialized_bytes} bytes, over the 250KB budget"


def _top_chase_dashboard_row(**overrides):
    row = {
        "set_id": _TEST_UUID,
        "window_key": "30d",
        "top_chase_cards_json": [
            {"cardId": "card-1", "cardVariantId": "variant-1", "name": "Chase Card"},
        ],
        "top_chase_card_histories_json": {
            "variant-1": [
                {"date": f"2026-06-{day:02d}", "marketPrice": 10.0 + day}
                for day in range(1, 31)
            ],
            "variant-unreferenced": [{"date": "2026-06-30", "marketPrice": 5.0}],
        },
        "latest_market_date": "2026-06-30",
        "updated_at": "2026-06-30T00:00:00+00:00",
        # Fields that must never be read/emitted by the slim top-chase payload.
        "set_value_histories_json": {"standard": [{"date": "2026-06-30", "setValue": 100.0}]},
        "performance_vs_cost_history_json": [{"date": "2026-06-30", "meanValue": 5.5}],
        "available_scopes_json": [{"key": "standard", "label": "Standard"}],
        "payload_json": {"marketMovers": {"heatingUp": [], "coolingOff": [], "all": []}},
    }
    row.update(overrides)
    return row


def test_top_chase_payload_reads_split_columns_and_does_not_call_full_dashboard_payload(monkeypatch):
    """The top-chase payload must query only the split top-chase columns and
    must never go through get_pokemon_set_market_dashboard_snapshot_payload."""
    captured_queries = []

    def read_dashboard(query):
        captured_queries.append(query)
        return [_top_chase_dashboard_row()]

    client = _Client({"pokemon_set_market_dashboard_snapshot_latest": read_dashboard})
    monkeypatch.setattr(pokemon_public_snapshot_service, "public_read_client", client)

    def _fail_if_called(*_args, **_kwargs):
        raise AssertionError("get_pokemon_set_market_dashboard_snapshot_payload must not be called")

    monkeypatch.setattr(
        pokemon_public_snapshot_service,
        "get_pokemon_set_market_dashboard_snapshot_payload",
        _fail_if_called,
    )

    payload = pokemon_public_snapshot_service.get_pokemon_set_top_chase_snapshot_payload(_TEST_UUID)

    # A 30D request reads the requested (30d) row and the canonical (365d) row
    # for the freshness comparison — never more, and every read uses the narrow
    # split-column select (never the full payload_json).
    assert 1 <= len(captured_queries) <= 2
    for captured in captured_queries:
        selected_fields = captured.select_fields
        assert "top_chase_cards_json" in selected_fields
        assert "top_chase_card_histories_json" in selected_fields
        assert "set_value_histories_json" not in selected_fields
        assert "performance_vs_cost_history_json" not in selected_fields
        assert "available_scopes_json" not in selected_fields
        assert "payload_json" not in selected_fields
    assert payload["topChaseCards"][0]["cardId"] == "card-1"


def test_top_chase_payload_excludes_set_value_performance_and_movers(monkeypatch):
    client = _Client({"pokemon_set_market_dashboard_snapshot_latest": lambda _q: [_top_chase_dashboard_row()]})
    monkeypatch.setattr(pokemon_public_snapshot_service, "public_read_client", client)

    payload = pokemon_public_snapshot_service.get_pokemon_set_top_chase_snapshot_payload(_TEST_UUID)

    assert "setValueHistoriesByScope" not in payload
    assert "performanceVsCostHistory" not in payload
    assert "availableScopes" not in payload
    assert "marketMovers" not in payload
    assert "marketMoversByWindow" not in payload
    assert "payload_json" not in payload
    assert set(payload.keys()) == {"set", "window", "topChaseCards", "topChaseCardHistories", "latestMarketDate", "meta"}


def test_top_chase_payload_slices_histories_to_requested_window(monkeypatch):
    """topChaseCardHistories must be sliced to the requested window (default
    30D), not the full 365-day source history, and must only include cards
    that are actually in topChaseCards."""
    client = _Client({"pokemon_set_market_dashboard_snapshot_latest": lambda _q: [_top_chase_dashboard_row()]})
    monkeypatch.setattr(pokemon_public_snapshot_service, "public_read_client", client)

    payload = pokemon_public_snapshot_service.get_pokemon_set_top_chase_snapshot_payload(_TEST_UUID, window="7D")

    histories = payload["topChaseCardHistories"]
    assert "variant-unreferenced" not in histories, "histories for cards outside topChaseCards must be dropped"
    assert len(histories["variant-1"]) == 7
    assert histories["variant-1"][-1]["date"] == "2026-06-30"


def test_top_chase_payload_resolves_prismatic_evolutions(monkeypatch):
    sets_rows = [
        {"id": "set-uuid-1", "name": "Prismatic Evolutions", "canonical_key": "prismaticEvolutions", "pokemon_api_set_id": "sv8pt5"}
    ]

    def read_sets(query):
        if query.eq_filters:
            field, value = query.eq_filters[-1]
            return [row for row in sets_rows if row.get(field) == value]
        return sets_rows

    dashboard_row = _top_chase_dashboard_row(set_id="set-uuid-1")

    client = _Client(
        {
            "sets": read_sets,
            "pokemon_set_market_dashboard_snapshot_latest": lambda _q: [dashboard_row],
        }
    )
    monkeypatch.setattr(pokemon_public_snapshot_service, "public_read_client", client)
    monkeypatch.setattr(pokemon_set_market_service, "public_read_client", client)

    payload = pokemon_public_snapshot_service.get_pokemon_set_top_chase_snapshot_payload("prismatic-evolutions")

    assert payload["set"]["id"] == "set-uuid-1"
    assert payload["topChaseCards"][0]["cardId"] == "card-1"


def test_top_chase_payload_serialized_size_is_under_250kb(monkeypatch):
    import json

    row = _top_chase_dashboard_row(
        top_chase_cards_json=[
            {"cardId": f"card-{index}", "cardVariantId": f"variant-{index}", "name": f"Chase Card {index}"}
            for index in range(10)
        ],
        top_chase_card_histories_json={
            f"variant-{index}": [
                {"date": f"2026-{(day % 12) + 1:02d}-{(day % 28) + 1:02d}", "marketPrice": round(10 + day * 0.1, 2)}
                for day in range(365)
            ]
            for index in range(10)
        },
    )
    client = _Client({"pokemon_set_market_dashboard_snapshot_latest": lambda _q: [row]})
    monkeypatch.setattr(pokemon_public_snapshot_service, "public_read_client", client)

    payload = pokemon_public_snapshot_service.get_pokemon_set_top_chase_snapshot_payload(_TEST_UUID)

    serialized_bytes = len(json.dumps(payload, default=str).encode("utf-8"))
    assert serialized_bytes < 250_000, f"top-chase payload was {serialized_bytes} bytes, over the 250KB budget"


def test_slim_top_chase_hydrates_empty_histories_from_observations_without_dragging_price(monkeypatch):
    """When the served row's histories are empty, they hydrate from raw
    observations to give the chart real points — but the card's current price
    stays the snapshot's own stored value and is NOT overwritten by the latest
    history point. Dragging the price onto the history is exactly the reverted
    Ascended Heroes patch (history can be stale/carried-forward). Price
    freshness is handled by serving the freshest row upstream, never by syncing
    the price column onto the chart.

    (The stale-stored-price-with-fresher-observations shape below is contrived:
    the freshest served row normally carries a fresh price, so this divergence
    doesn't arise in production — the test only pins the no-drag rule.)"""
    row = _top_chase_dashboard_row(
        top_chase_cards_json=[
            {
                "cardId": "card-1",
                "cardVariantId": "variant-1",
                "name": "Mega Gengar ex",
                "marketPrice": 120.0,
                "currentPrice": 120.0,
                "estimatedMarketPrice": 120.0,
                "priceUsed": 120.0,
                "priceUpdatedAt": "2026-06-20",
            }
        ],
        top_chase_card_histories_json={},
        latest_market_date="2026-06-20",
    )
    client = _Client({"pokemon_set_market_dashboard_snapshot_latest": lambda _q: [row]})
    monkeypatch.setattr(pokemon_public_snapshot_service, "public_read_client", client)

    def fake_observation_histories(**_kwargs):
        return {
            "variant-1": [
                {"date": "2026-07-06", "marketPrice": 150.0, "market_price": 150.0},
                {"date": "2026-07-08", "marketPrice": 175.0, "market_price": 175.0},
            ]
        }

    monkeypatch.setattr(
        pokemon_public_snapshot_service,
        "_load_top_chase_observation_histories",
        fake_observation_histories,
    )

    payload = pokemon_public_snapshot_service.get_pokemon_set_top_chase_snapshot_payload(_TEST_UUID, window="30D")

    # History hydrated from observations, latest point is 175.0 on 2026-07-08.
    assert payload["topChaseCardHistories"]["variant-1"][-1]["marketPrice"] == 175.0
    assert payload["meta"]["topChaseHistoryHydratedFromObservations"] is True
    assert payload["meta"]["topChaseHistorySourceLatestObservedDate"] == "2026-07-08"
    # The card price column keeps the snapshot's own stored current price — it
    # is NOT dragged onto the latest history point.
    card = payload["topChaseCards"][0]
    assert card["marketPrice"] == 120.0
    assert card["currentPrice"] == 120.0
    assert card["priceUpdatedAt"] == "2026-06-20"
    # The reverted sync meta must be gone.
    assert "topChaseCardPricesSyncedToHistory" not in payload["meta"]
    assert "topChaseCardPricesSyncedCount" not in payload["meta"]


def test_slim_top_chase_aligns_current_price_and_skips_observation_scan_when_histories_exist(monkeypatch):
    """When stored histories already cover the cards, no raw-observation scan
    runs and the card's stored current price is served as-is — never
    aligned to the latest stored history point when it reaches latestMarketDate."""
    observation_calls = []

    def _fail_observation_scan(*_args, **_kwargs):
        observation_calls.append(True)
        raise AssertionError("observation scan must not run when stored histories exist")

    row = _top_chase_dashboard_row(
        top_chase_cards_json=[
            {"cardId": "card-1", "cardVariantId": "variant-1", "name": "Chase Card", "marketPrice": 10.0},
        ],
        top_chase_card_histories_json={
            "variant-1": [
                {"date": "2026-06-29", "marketPrice": 40.0},
                {"date": "2026-06-30", "marketPrice": 41.0},
            ],
        },
        latest_market_date="2026-06-30",
    )
    client = _Client({"pokemon_set_market_dashboard_snapshot_latest": lambda _q: [row]})
    monkeypatch.setattr(pokemon_public_snapshot_service, "public_read_client", client)
    monkeypatch.setattr(
        pokemon_public_snapshot_service, "_load_top_chase_observation_histories", _fail_observation_scan
    )

    payload = pokemon_public_snapshot_service.get_pokemon_set_top_chase_snapshot_payload(_TEST_UUID, window="30D")

    assert observation_calls == []
    assert payload["topChaseCards"][0]["marketPrice"] == 41.0


def test_slim_top_chase_keeps_histories_separate(monkeypatch):
    """topChaseCardHistories stays the canonical history container — the sliced
    per-card price history must not be re-embedded onto each card (the slim
    endpoint strips priceHistory to stay under budget), and the card's stored
    current price agrees with the terminal history point."""
    row = _top_chase_dashboard_row(
        top_chase_cards_json=[
            {"cardId": "card-1", "cardVariantId": "variant-1", "name": "Chase Card", "marketPrice": 99.0},
        ],
    )
    client = _Client({"pokemon_set_market_dashboard_snapshot_latest": lambda _q: [row]})
    monkeypatch.setattr(pokemon_public_snapshot_service, "public_read_client", client)

    payload = pokemon_public_snapshot_service.get_pokemon_set_top_chase_snapshot_payload(_TEST_UUID, window="30D")

    assert "variant-1" in payload["topChaseCardHistories"]
    for card in payload["topChaseCards"]:
        assert "priceHistory" not in card, "slim endpoint must not re-embed priceHistory onto cards"
        assert "price_history" not in card
    assert payload["topChaseCards"][0]["marketPrice"] == 40.0


# ---------------------------------------------------------------------------
# Phase 5.7 — Market Movers now reads pokemon_set_market_dashboard_snapshot_latest
# (payload_json->marketMoversByWindow) via a narrow PostgREST JSON-path select,
# instead of live-aggregating card_variant_price_observations on every
# request. These tests guard the read-model path, the safe-empty fallback,
# and that the live aggregation path is never touched when a snapshot exists.
# ---------------------------------------------------------------------------


def _mover_card(card_id, *, score=10.0, label="heating_up", price=100.0):
    return {
        "cardId": card_id,
        "name": f"Card {card_id}",
        "currentPrice": price,
        "change30dAmount": 5.0,
        "change30dPercent": 5.0,
        "movementScore": score,
        "movementLabel": label,
        "enoughHistory": True,
        "confidence": "medium",
    }


def _market_movers_by_window(
    *,
    heating_30d=None,
    cooling_30d=None,
    heating_7d=None,
    cooling_7d=None,
    heating_1d=None,
    cooling_1d=None,
):
    def entry(window, days, heating, cooling):
        heating = heating if heating is not None else [_mover_card("30d-heat-1", score=42.0)]
        cooling = cooling if cooling is not None else [_mover_card("30d-cool-1", score=-10.0, label="cooling_off")]
        return {
            "window": window,
            "windowDays": days,
            "heatingUp": heating,
            "heating_up": heating,
            "coolingOff": cooling,
            "cooling_off": cooling,
            "all": [*heating, *cooling],
        }

    return {
        "1D": entry("1D", 1, heating_1d, cooling_1d),
        "7D": entry("7D", 7, heating_7d, cooling_7d),
        "30D": entry("30D", 30, heating_30d, cooling_30d),
    }


def _make_movers_handler(rows_by_window_key, *, calls=None):
    """Fake `pokemon_set_market_dashboard_snapshot_latest` table handler that
    simulates PostgREST's JSON-path push-down
    (`payload_json->marketMoversByWindow->30D->heatingUp` /
    `->coolingOff`): the real query never transfers the full payload_json
    blob (nor the unused "all" list), so this fake resolves the requested
    mover sub-window's heatingUp/coolingOff arrays straight from the select
    string's aliases, exactly like Postgres would do server-side."""

    def handler(query):
        if calls is not None:
            calls.append(query)
        requested_window_key = None
        for field, value in query.eq_filters:
            if field == "window_key":
                requested_window_key = value
        row = rows_by_window_key.get(requested_window_key)
        if not row:
            return []
        mover_window = None
        for candidate in ("1D", "7D", "30D"):
            if f"marketMoversByWindow->{candidate}->" in query.select_fields:
                mover_window = candidate
                break
        movers_by_window = row.get("_market_movers_by_window") or {}
        entry = movers_by_window.get(mover_window)
        result_row = {key: value for key, value in row.items() if not key.startswith("_")}
        result_row["heating"] = (entry or {}).get("heatingUp") if entry is not None else None
        result_row["cooling"] = (entry or {}).get("coolingOff") if entry is not None else None
        result_row["all_items"] = (entry or {}).get("all") if entry is not None else None
        result_row["heating_snake"] = (entry or {}).get("heating_up") if entry is not None else None
        result_row["cooling_snake"] = (entry or {}).get("cooling_off") if entry is not None else None
        result_row["all_items_snake"] = (entry or {}).get("all") if entry is not None else None
        return [result_row]

    return handler


def test_market_movers_snapshot_reads_from_read_model(monkeypatch):
    calls = []
    row = {
        "set_id": _TEST_UUID,
        "window_key": "365d",
        "latest_market_date": "2026-06-30",
        "updated_at": "2026-06-30T00:00:00+00:00",
        "_market_movers_by_window": _market_movers_by_window(),
    }
    client = _Client(
        {"pokemon_set_market_dashboard_snapshot_latest": _make_movers_handler({"365d": row}, calls=calls)}
    )
    monkeypatch.setattr(pokemon_public_snapshot_service, "public_read_client", client)

    payload = pokemon_public_snapshot_service.get_pokemon_set_market_movers_snapshot_payload(_TEST_UUID)

    assert len(calls) == 1, "must read the snapshot row in a single query"
    assert payload["meta"]["snapshot"]["usedReadModel"] is True
    assert payload["meta"]["snapshot"]["source"] == "pokemon_set_market_dashboard_snapshot_latest"
    assert payload["meta"]["snapshot"]["sourceField"] == "payload_json.marketMoversByWindow.all/heatingUp/coolingOff"


def test_market_movers_snapshot_preserves_heating_cooling_order(monkeypatch):
    heating = [_mover_card("h1", score=90.0), _mover_card("h2", score=50.0), _mover_card("h3", score=10.0)]
    cooling = [_mover_card("c1", score=-80.0, label="cooling_off"), _mover_card("c2", score=-20.0, label="cooling_off")]
    row = {
        "set_id": _TEST_UUID,
        "window_key": "365d",
        "latest_market_date": "2026-06-30",
        "updated_at": "2026-06-30T00:00:00+00:00",
        "_market_movers_by_window": _market_movers_by_window(heating_30d=heating, cooling_30d=cooling),
    }
    client = _Client({"pokemon_set_market_dashboard_snapshot_latest": _make_movers_handler({"365d": row})})
    monkeypatch.setattr(pokemon_public_snapshot_service, "public_read_client", client)

    payload = pokemon_public_snapshot_service.get_pokemon_set_market_movers_snapshot_payload(_TEST_UUID, window="30D", limit=5)

    assert [c["cardId"] for c in payload["marketMovers"]["heatingUp"]] == ["h1", "h2", "h3"]
    assert [c["cardId"] for c in payload["marketMovers"]["coolingOff"]] == ["c1", "c2"]


def test_market_movers_snapshot_returns_first_limit_from_complete_ranked_all(monkeypatch):
    ranked_all = [_mover_card(f"rank-{index:02d}", score=100 - index) for index in range(23)]
    movers = _market_movers_by_window()
    movers["7D"]["all"] = ranked_all
    row = {
        "set_id": _TEST_UUID,
        "window_key": "365d",
        "latest_market_date": "2026-06-30",
        "updated_at": "2026-06-30T00:00:00+00:00",
        "_market_movers_by_window": movers,
    }
    client = _Client({"pokemon_set_market_dashboard_snapshot_latest": _make_movers_handler({"365d": row})})
    monkeypatch.setattr(pokemon_public_snapshot_service, "public_read_client", client)

    payload = pokemon_public_snapshot_service.get_pokemon_set_market_movers_snapshot_payload(
        _TEST_UUID, window="7D", limit=10
    )

    assert [card["cardId"] for card in payload["marketMovers"]["all"]] == [
        f"rank-{index:02d}" for index in range(10)
    ]
    assert payload["meta"]["snapshot"]["usedLegacyAllFallback"] is False


def test_market_movers_snapshot_caps_complete_all_at_requested_limit(monkeypatch):
    ranked_all = [_mover_card(f"rank-{index:02d}") for index in range(49)]
    movers = _market_movers_by_window()
    movers["30D"]["all"] = ranked_all
    row = {
        "set_id": _TEST_UUID,
        "window_key": "365d",
        "latest_market_date": "2026-06-30",
        "updated_at": "2026-06-30T00:00:00+00:00",
        "_market_movers_by_window": movers,
    }
    client = _Client({"pokemon_set_market_dashboard_snapshot_latest": _make_movers_handler({"365d": row})})
    monkeypatch.setattr(pokemon_public_snapshot_service, "public_read_client", client)

    payload = pokemon_public_snapshot_service.get_pokemon_set_market_movers_snapshot_payload(
        _TEST_UUID, window="30D", limit=10
    )

    assert len(payload["marketMovers"]["all"]) == 10
    assert [card["cardId"] for card in payload["marketMovers"]["all"]] == [
        f"rank-{index:02d}" for index in range(10)
    ]
    assert len(payload["marketMovers"]["heatingUp"]) <= 10
    assert len(payload["marketMovers"]["coolingOff"]) <= 10


def test_market_movers_snapshot_diagnoses_legacy_all_fallback(monkeypatch):
    movers = _market_movers_by_window()
    movers["7D"].pop("all")
    row = {
        "set_id": _TEST_UUID,
        "window_key": "365d",
        "latest_market_date": "2026-06-30",
        "updated_at": "2026-06-30T00:00:00+00:00",
        "_market_movers_by_window": movers,
    }
    client = _Client({"pokemon_set_market_dashboard_snapshot_latest": _make_movers_handler({"365d": row})})
    monkeypatch.setattr(pokemon_public_snapshot_service, "public_read_client", client)

    payload = pokemon_public_snapshot_service.get_pokemon_set_market_movers_snapshot_payload(
        _TEST_UUID, window="7D", limit=10
    )

    assert payload["marketMovers"]["all"]
    assert payload["meta"]["snapshot"]["usedLegacyAllFallback"] is True
    assert any("Legacy market movers snapshot" in warning for warning in payload["meta"]["warnings"])


def test_market_movers_snapshot_preserves_scores_labels_and_deltas(monkeypatch):
    card = _mover_card("h1", score=42.7574, label="heating_up", price=556.57)
    card["change30dAmount"] = 41.81
    card["change30dPercent"] = 8.12
    row = {
        "set_id": _TEST_UUID,
        "window_key": "365d",
        "latest_market_date": "2026-06-30",
        "updated_at": "2026-06-30T00:00:00+00:00",
        "_market_movers_by_window": _market_movers_by_window(heating_30d=[card], cooling_30d=[]),
    }
    client = _Client({"pokemon_set_market_dashboard_snapshot_latest": _make_movers_handler({"365d": row})})
    monkeypatch.setattr(pokemon_public_snapshot_service, "public_read_client", client)

    payload = pokemon_public_snapshot_service.get_pokemon_set_market_movers_snapshot_payload(_TEST_UUID, window="30D")
    served = payload["marketMovers"]["heatingUp"][0]

    assert served["movementScore"] == 42.7574
    assert served["movementLabel"] == "heating_up"
    assert served["change30dAmount"] == 41.81
    assert served["change30dPercent"] == 8.12
    assert served["currentPrice"] == 556.57


def test_market_movers_snapshot_safe_empty_when_snapshot_missing(monkeypatch):
    client = _Client({"pokemon_set_market_dashboard_snapshot_latest": lambda _q: []})
    monkeypatch.setattr(pokemon_public_snapshot_service, "public_read_client", client)

    payload = pokemon_public_snapshot_service.get_pokemon_set_market_movers_snapshot_payload(_TEST_UUID, window="30D")

    assert payload["marketMovers"]["heatingUp"] == []
    assert payload["marketMovers"]["coolingOff"] == []
    assert payload["marketMovers"]["all"] == []
    assert payload["meta"]["snapshot"]["usedReadModel"] is False
    assert "missing" in payload["meta"]["snapshot"]["source"]


def test_market_movers_snapshot_safe_empty_when_window_absent_from_stored_payload(monkeypatch):
    """A stale row whose marketMoversByWindow predates a mover window (or is
    simply empty) must serve safe empty data, not raise."""
    row = {
        "set_id": _TEST_UUID,
        "window_key": "365d",
        "latest_market_date": "2026-06-20",
        "updated_at": "2026-06-20T00:00:00+00:00",
        "_market_movers_by_window": {},
    }
    client = _Client({"pokemon_set_market_dashboard_snapshot_latest": _make_movers_handler({"365d": row})})
    monkeypatch.setattr(pokemon_public_snapshot_service, "public_read_client", client)

    payload = pokemon_public_snapshot_service.get_pokemon_set_market_movers_snapshot_payload(_TEST_UUID, window="30D")

    assert payload["marketMovers"]["heatingUp"] == []
    assert payload["marketMovers"]["coolingOff"] == []


def test_market_movers_snapshot_never_calls_live_aggregation(monkeypatch):
    """The slim /market/movers snapshot reader must never fall back to the
    live build_pokemon_set_card_movement_payload aggregation — a missing or
    incomplete snapshot serves a safe empty payload instead, exactly like its
    top-chase/overview siblings."""
    row = {
        "set_id": _TEST_UUID,
        "window_key": "365d",
        "latest_market_date": "2026-06-30",
        "updated_at": "2026-06-30T00:00:00+00:00",
        "_market_movers_by_window": _market_movers_by_window(),
    }
    client = _Client({"pokemon_set_market_dashboard_snapshot_latest": _make_movers_handler({"365d": row})})
    monkeypatch.setattr(pokemon_public_snapshot_service, "public_read_client", client)

    def _fail_if_called(*_args, **_kwargs):
        raise AssertionError("build_pokemon_set_card_movement_payload must not be called")

    monkeypatch.setattr(pokemon_set_market_service, "build_pokemon_set_card_movement_payload", _fail_if_called)
    monkeypatch.setattr(pokemon_set_market_service, "get_pokemon_set_market_movers_payload", _fail_if_called)

    # Also exercise the missing-snapshot path with the live functions patched
    # to raise, proving the empty-fallback path truly never calls them either.
    pokemon_public_snapshot_service.get_pokemon_set_market_movers_snapshot_payload(_TEST_UUID, window="30D")

    empty_client = _Client({"pokemon_set_market_dashboard_snapshot_latest": lambda _q: []})
    monkeypatch.setattr(pokemon_public_snapshot_service, "public_read_client", empty_client)
    pokemon_public_snapshot_service.get_pokemon_set_market_movers_snapshot_payload(_TEST_UUID, window="30D")


def test_market_movers_snapshot_normalizes_window_case(monkeypatch):
    row = {
        "set_id": _TEST_UUID,
        "window_key": "365d",
        "latest_market_date": "2026-06-30",
        "updated_at": "2026-06-30T00:00:00+00:00",
        "_market_movers_by_window": _market_movers_by_window(),
    }
    client = _Client({"pokemon_set_market_dashboard_snapshot_latest": _make_movers_handler({"365d": row})})
    monkeypatch.setattr(pokemon_public_snapshot_service, "public_read_client", client)

    upper = pokemon_public_snapshot_service.get_pokemon_set_market_movers_snapshot_payload(_TEST_UUID, window="30D")
    lower = pokemon_public_snapshot_service.get_pokemon_set_market_movers_snapshot_payload(_TEST_UUID, window="30d")

    assert upper["window"] == "30D"
    assert lower["window"] == "30D", "lowercase '30d' must normalize to the same '30D' window as uppercase"
    assert upper["marketMovers"]["heatingUp"] == lower["marketMovers"]["heatingUp"]


def test_market_movers_snapshot_falls_back_to_30d_row_when_365d_missing(monkeypatch):
    row_30d = {
        "set_id": _TEST_UUID,
        "window_key": "30d",
        "latest_market_date": "2026-06-20",
        "updated_at": "2026-06-20T00:00:00+00:00",
        "_market_movers_by_window": _market_movers_by_window(),
    }
    client = _Client({"pokemon_set_market_dashboard_snapshot_latest": _make_movers_handler({"30d": row_30d})})
    monkeypatch.setattr(pokemon_public_snapshot_service, "public_read_client", client)

    payload = pokemon_public_snapshot_service.get_pokemon_set_market_movers_snapshot_payload(_TEST_UUID, window="30D")

    assert payload["meta"]["snapshot"]["usedFallbackWindow"] is True
    assert payload["meta"]["snapshot"]["fallbackReason"] == "missing_365d_row"
    assert len(payload["marketMovers"]["heatingUp"]) > 0


def test_market_movers_snapshot_response_shape_matches_frontend_normalizer_contract(monkeypatch):
    """normalizeMarketMoversPayload (pokemonSetMarketClient.js) reads
    payload.marketMovers.{heatingUp,coolingOff,window,windowDays} and falls
    back to synthesizing `all` from heatingUp+coolingOff when the source
    lacks it (Phase 5.8: the slim contract intentionally omits `all` — see
    normalizeMarketMoversEntry's `Array.isArray(source?.all) ? source.all :
    [...heating, ...cooling]` fallback), so the snapshot-backed payload only
    needs to keep serving heatingUp/coolingOff/window/windowDays."""
    row = {
        "set_id": _TEST_UUID,
        "window_key": "365d",
        "latest_market_date": "2026-06-30",
        "updated_at": "2026-06-30T00:00:00+00:00",
        "_market_movers_by_window": _market_movers_by_window(),
    }
    client = _Client({"pokemon_set_market_dashboard_snapshot_latest": _make_movers_handler({"365d": row})})
    monkeypatch.setattr(pokemon_public_snapshot_service, "public_read_client", client)

    payload = pokemon_public_snapshot_service.get_pokemon_set_market_movers_snapshot_payload(_TEST_UUID, window="30D", limit=5)

    market_movers = payload["marketMovers"]
    assert set(["window", "windowDays", "heatingUp", "coolingOff"]).issubset(market_movers.keys())
    assert isinstance(market_movers["all"], list)
    assert isinstance(market_movers["heatingUp"], list)
    assert isinstance(market_movers["coolingOff"], list)
    first_card = market_movers["heatingUp"][0]
    for field in ("cardId", "name", "currentPrice", "change30dAmount", "change30dPercent", "movementScore", "movementLabel"):
        assert field in first_card


def test_market_movers_snapshot_never_returns_full_dashboard_fields(monkeypatch):
    """The movers-only slim payload must never leak the full monolithic
    dashboard contract's other fields (set value histories, top chase, etc.)."""
    row = {
        "set_id": _TEST_UUID,
        "window_key": "365d",
        "latest_market_date": "2026-06-30",
        "updated_at": "2026-06-30T00:00:00+00:00",
        "_market_movers_by_window": _market_movers_by_window(),
    }
    client = _Client({"pokemon_set_market_dashboard_snapshot_latest": _make_movers_handler({"365d": row})})
    monkeypatch.setattr(pokemon_public_snapshot_service, "public_read_client", client)

    payload = pokemon_public_snapshot_service.get_pokemon_set_market_movers_snapshot_payload(_TEST_UUID, window="30D")

    for forbidden_key in (
        "setValueHistoriesByScope",
        "performanceVsCostHistory",
        "topChaseCards",
        "topChaseCardHistories",
        "availableScopes",
        "payload_json",
    ):
        assert forbidden_key not in payload
    assert set(payload.keys()) == {"set", "window", "windowDays", "marketMovers", "meta"}


def test_full_market_dashboard_still_preserves_all_field(monkeypatch):
    """Phase 5.8 Gate 5 only trims the slim /market/movers contract. The full
    /market/dashboard payload (get_pokemon_set_market_dashboard_snapshot_payload)
    reads payload_json directly and must keep serving `all` unchanged — it's
    a separate code path from get_pokemon_set_market_movers_snapshot_payload
    and this phase must not touch it."""
    row = _overview_dashboard_row(
        payload_json={
            "marketMovers": {"heatingUp": [{"cardId": "card-1"}], "coolingOff": [], "all": [{"cardId": "card-1"}]},
            "marketMoversByWindow": {
                "30D": {"heatingUp": [{"cardId": "card-1"}], "coolingOff": [], "all": [{"cardId": "card-1"}]},
            },
        }
    )
    client = _Client({"pokemon_set_market_dashboard_snapshot_latest": lambda _q: [row]})
    monkeypatch.setattr(pokemon_public_snapshot_service, "public_read_client", client)

    payload = pokemon_public_snapshot_service.get_pokemon_set_market_dashboard_snapshot_payload(_TEST_UUID)

    assert "all" in payload["marketMovers"], "full dashboard marketMovers must still include 'all'"
    assert payload["marketMovers"]["all"] == [{"cardId": "card-1"}]
    assert "all" in payload["marketMoversByWindow"]["30D"], "full dashboard marketMoversByWindow must still include 'all'"
    assert payload["marketMoversByWindow"]["30D"]["all"] == [{"cardId": "card-1"}]


def test_market_movers_snapshot_query_selects_only_narrow_json_path(monkeypatch):
    """Guards the bandwidth fix itself: the select string must reference only
    the requested mover window's heatingUp/coolingOff JSON paths — never the
    bare payload_json column (the ~3MB monolithic blob) and never the "all"
    sub-path (Phase 5.8 Gate 4/5: unused by the UI, dropped at the query
    level so it's never even transferred from Postgres)."""
    calls = []
    row = {
        "set_id": _TEST_UUID,
        "window_key": "365d",
        "latest_market_date": "2026-06-30",
        "updated_at": "2026-06-30T00:00:00+00:00",
        "_market_movers_by_window": _market_movers_by_window(),
    }
    client = _Client(
        {"pokemon_set_market_dashboard_snapshot_latest": _make_movers_handler({"365d": row}, calls=calls)}
    )
    monkeypatch.setattr(pokemon_public_snapshot_service, "public_read_client", client)

    pokemon_public_snapshot_service.get_pokemon_set_market_movers_snapshot_payload(_TEST_UUID, window="7D")

    assert len(calls) == 1
    select_fields = calls[0].select_fields
    assert "marketMoversByWindow->7D->heatingUp" in select_fields
    assert "marketMoversByWindow->7D->coolingOff" in select_fields
    assert "marketMoversByWindow->7D->all" in select_fields
    assert "market_movers_by_window->7D->all" in select_fields
    assert select_fields.count("payload_json") == 6, "must select six narrow JSON paths off payload_json, not the whole column"
    assert not select_fields.rstrip(",").endswith("payload_json"), "must not select the bare payload_json column"


def test_market_movers_snapshot_resolves_prismatic_evolutions(monkeypatch):
    sets_rows = [
        {"id": "set-uuid-1", "name": "Prismatic Evolutions", "canonical_key": "prismaticEvolutions", "pokemon_api_set_id": "sv8pt5"}
    ]

    def read_sets(query):
        if query.eq_filters:
            field, value = query.eq_filters[-1]
            return [row for row in sets_rows if row.get(field) == value]
        return sets_rows

    row = {
        "set_id": "set-uuid-1",
        "window_key": "365d",
        "latest_market_date": "2026-06-30",
        "updated_at": "2026-06-30T00:00:00+00:00",
        "_market_movers_by_window": _market_movers_by_window(),
    }
    client = _Client(
        {
            "sets": read_sets,
            "pokemon_set_market_dashboard_snapshot_latest": _make_movers_handler({"365d": row}),
        }
    )
    monkeypatch.setattr(pokemon_public_snapshot_service, "public_read_client", client)
    monkeypatch.setattr(pokemon_set_market_service, "public_read_client", client)

    payload = pokemon_public_snapshot_service.get_pokemon_set_market_movers_snapshot_payload("prismatic-evolutions")

    assert payload["set"]["id"] == "set-uuid-1"
    assert len(payload["marketMovers"]["heatingUp"]) > 0


# ---------------------------------------------------------------------------
# Phase 3A — new v2-style slim contracts (overview, top-chase) must be
# camelCase-only, with no legacy snake_case alias duplicates. The legacy
# /market/dashboard contract is intentionally left alone in this phase.
# ---------------------------------------------------------------------------


def test_overview_payload_has_no_duplicate_snake_case_aliases(monkeypatch):
    client = _Client({"pokemon_set_market_dashboard_snapshot_latest": lambda _q: [_overview_dashboard_row()]})
    monkeypatch.setattr(pokemon_public_snapshot_service, "public_read_client", client)

    payload = pokemon_public_snapshot_service.get_pokemon_set_overview_snapshot_payload(_TEST_UUID)

    for snake_key in (
        "set_value_histories_by_scope",
        "performance_vs_cost_history",
        "available_scopes",
        "latest_market_date",
        "top_chase_cards",
        "top_chase_card_histories",
        "market_movers",
        "market_movers_by_window",
    ):
        assert snake_key not in payload, f"{snake_key} must not appear in the camelCase-only overview payload"


def test_top_chase_payload_has_no_duplicate_snake_case_aliases(monkeypatch):
    client = _Client({"pokemon_set_market_dashboard_snapshot_latest": lambda _q: [_top_chase_dashboard_row()]})
    monkeypatch.setattr(pokemon_public_snapshot_service, "public_read_client", client)

    payload = pokemon_public_snapshot_service.get_pokemon_set_top_chase_snapshot_payload(_TEST_UUID)

    for snake_key in (
        "top_chase_cards",
        "top_chase_card_histories",
        "latest_market_date",
        "set_value_histories_by_scope",
        "performance_vs_cost_history",
        "available_scopes",
        "market_movers",
        "market_movers_by_window",
    ):
        assert snake_key not in payload, f"{snake_key} must not appear in the camelCase-only top-chase payload"


# ---------------------------------------------------------------------------
# Phase 5E: top-chase 30D -> 365D window-key fallback
#
# Root cause (Phase 5D audit): pokemon_set_market_dashboard_snapshot_latest
# has a 365d row for virtually every set, but the market dashboard builder
# has (for most sets) never been run with the 30d window. This endpoint
# defaults to window_key="30d" with an exact-match query and no fallback, so
# it returned an empty payload for 165/171 sets even though top_chase_cards_json/
# top_chase_card_histories_json were already fully populated under the 365d
# row. The fix below is read-path only: no DB write, no ranking change.
# ---------------------------------------------------------------------------


def _window_key_from_query(query):
    for field, value in query.eq_filters:
        if field == "window_key":
            return value
    return None


def test_top_chase_payload_falls_back_to_365d_row_when_30d_missing(monkeypatch):
    """A: given no 30d row but a 365d row with cards/histories, the endpoint
    must serve that data instead of the empty fallback, while still
    reporting the requested window and recording the fallback in meta."""
    row_365d = _top_chase_dashboard_row(window_key="365d")

    def read_dashboard(query):
        return [row_365d] if _window_key_from_query(query) == "365d" else []

    client = _Client({"pokemon_set_market_dashboard_snapshot_latest": read_dashboard})
    monkeypatch.setattr(pokemon_public_snapshot_service, "public_read_client", client)

    payload = pokemon_public_snapshot_service.get_pokemon_set_top_chase_snapshot_payload(_TEST_UUID, window="30D")

    assert len(payload["topChaseCards"]) == 1
    assert payload["topChaseCards"][0]["cardId"] == "card-1"
    assert payload["window"] == "30d"
    assert payload["meta"]["snapshot"]["requestedWindow"] == "30d"
    assert payload["meta"]["snapshot"]["sourceWindow"] == "365d"
    assert payload["meta"]["snapshot"]["usedFallbackWindow"] is True
    assert payload["meta"]["snapshot"]["fallbackReason"] == "missing_requested_window_row"
    assert any("365d" in warning for warning in payload["meta"]["warnings"])


def test_top_chase_payload_prefers_fresh_30d_row_over_365d(monkeypatch):
    """B: when the requested 30d row is present and NOT staler than the 365d
    row, it wins — the 365d row is consulted only to confirm freshness and must
    not override an equally-fresh (or fresher) requested-window row."""
    row_30d = _top_chase_dashboard_row(
        window_key="30d",
        latest_market_date="2026-06-30",
        top_chase_cards_json=[{"cardId": "card-30d", "cardVariantId": "variant-30d", "name": "30D Card"}],
    )
    row_365d = _top_chase_dashboard_row(
        window_key="365d",
        latest_market_date="2026-06-30",
        top_chase_cards_json=[{"cardId": "card-365d", "cardVariantId": "variant-365d", "name": "365D Card"}],
    )

    def read_dashboard(query):
        window_key = _window_key_from_query(query)
        if window_key == "30d":
            return [row_30d]
        if window_key == "365d":
            return [row_365d]
        return []

    client = _Client({"pokemon_set_market_dashboard_snapshot_latest": read_dashboard})
    monkeypatch.setattr(pokemon_public_snapshot_service, "public_read_client", client)

    payload = pokemon_public_snapshot_service.get_pokemon_set_top_chase_snapshot_payload(_TEST_UUID, window="30D")

    assert payload["topChaseCards"][0]["cardId"] == "card-30d"
    assert payload["meta"]["snapshot"]["usedFallbackWindow"] is False
    assert payload["meta"]["snapshot"]["sourceWindow"] == "30d"


def test_top_chase_payload_falls_back_to_365d_row_when_30d_row_is_stale(monkeypatch):
    """B2 (Ascended Heroes core regression): the requested 30d row EXISTS but
    is stale (older latest_market_date) while the 365d row is fresh — the
    endpoint must serve the fresher 365d row, not the stale 30d row, so Top
    Chase stops contradicting Market Movers for the same set."""
    row_30d = _top_chase_dashboard_row(
        window_key="30d",
        latest_market_date="2026-06-20",
        top_chase_cards_json=[{"cardId": "card-stale", "cardVariantId": "variant-stale", "name": "Stale Card", "marketPrice": 1368.11}],
    )
    row_365d = _top_chase_dashboard_row(
        window_key="365d",
        latest_market_date="2026-07-08",
        top_chase_cards_json=[{"cardId": "card-fresh", "cardVariantId": "variant-fresh", "name": "Fresh Card", "marketPrice": 1232.12}],
        top_chase_card_histories_json={"variant-fresh": [{"date": "2026-07-08", "marketPrice": 1232.12}]},
    )

    def read_dashboard(query):
        window_key = _window_key_from_query(query)
        if window_key == "30d":
            return [row_30d]
        if window_key == "365d":
            return [row_365d]
        return []

    client = _Client({"pokemon_set_market_dashboard_snapshot_latest": read_dashboard})
    monkeypatch.setattr(pokemon_public_snapshot_service, "public_read_client", client)

    payload = pokemon_public_snapshot_service.get_pokemon_set_top_chase_snapshot_payload(_TEST_UUID, window="30D")

    assert payload["topChaseCards"][0]["cardId"] == "card-fresh"
    assert payload["topChaseCards"][0]["marketPrice"] == 1232.12
    assert payload["meta"]["snapshot"]["usedFallbackWindow"] is True
    assert payload["meta"]["snapshot"]["fallbackReason"] == "requested_window_row_stale"
    assert payload["meta"]["snapshot"]["sourceWindow"] == "365d"
    assert any("stale" in warning for warning in payload["meta"]["warnings"])


def test_top_chase_ascended_heroes_stale_carried_forward_never_overrides_fresh(monkeypatch):
    """Ascended Heroes end-to-end regression (mirrors the real snapshot shape):

    - the requested 30d row is stale (latest_market_date 2026-06-20) with a
      stale Pikachu price (1368.11) and a carried-forward history frozen at
      Jun 20-21,
    - the canonical 365d row is fresh (2026-07-08) with the true current price
      (1232.12) and a real observed history ending 2026-07-08.

    The endpoint must serve the fresh 365d row: the price column resolves to
    1232.12, the chart ends on the real 2026-07-08 observation (never flattened
    at the carried-forward 1368.11), the stale carried-forward point is not used
    as current truth, and meta exposes which row the current price came from.
    """
    pikachu_variant = "af28bc66-9c8b-4dbb-bf83-fa6215bd26f0"
    stale_30d = _top_chase_dashboard_row(
        window_key="30d",
        latest_market_date="2026-06-20",
        top_chase_cards_json=[
            {
                "cardId": "pikachu-ex",
                "cardVariantId": pikachu_variant,
                "name": "Pikachu ex",
                "marketPrice": 1368.11,
                "currentPrice": 1368.11,
                "priceUpdatedAt": "2026-06-21",
            }
        ],
        top_chase_card_histories_json={
            pikachu_variant: [
                {"date": "2026-06-19", "marketPrice": 1368.11, "isCarriedForward": False},
                {"date": "2026-06-20", "marketPrice": 1368.11, "isCarriedForward": True},
                {"date": "2026-06-21", "marketPrice": 1368.11, "isCarriedForward": True},
            ]
        },
    )
    fresh_365d = _top_chase_dashboard_row(
        window_key="365d",
        latest_market_date="2026-07-08",
        top_chase_cards_json=[
            {
                "cardId": "pikachu-ex",
                "cardVariantId": pikachu_variant,
                "name": "Pikachu ex",
                "marketPrice": 1232.12,
                "currentPrice": 1232.12,
                "priceUpdatedAt": "2026-07-08",
            }
        ],
        top_chase_card_histories_json={
            pikachu_variant: [
                {"date": "2026-07-05", "marketPrice": 1301.08},
                {"date": "2026-07-06", "marketPrice": 1301.08},
                {"date": "2026-07-07", "marketPrice": 1237.84},
                {"date": "2026-07-08", "marketPrice": 1232.12},
            ]
        },
    )

    def read_dashboard(query):
        window_key = _window_key_from_query(query)
        if window_key == "30d":
            return [stale_30d]
        if window_key == "365d":
            return [fresh_365d]
        return []

    client = _Client({"pokemon_set_market_dashboard_snapshot_latest": read_dashboard})
    monkeypatch.setattr(pokemon_public_snapshot_service, "public_read_client", client)

    payload = pokemon_public_snapshot_service.get_pokemon_set_top_chase_snapshot_payload(_TEST_UUID, window="30D")

    card = payload["topChaseCards"][0]
    # Price column resolves to the fresh current market truth, not the stale row.
    assert card["marketPrice"] == 1232.12
    assert card["currentPrice"] == 1232.12
    history = payload["topChaseCardHistories"][pikachu_variant]
    # Chart is the real observed history ending 2026-07-08 — never flattened at
    # the carried-forward 1368.11.
    assert history[-1]["date"] == "2026-07-08"
    assert history[-1]["marketPrice"] == 1232.12
    assert all(point["marketPrice"] != 1368.11 for point in history)
    # meta exposes that the current price came from the fresh 365d row.
    assert payload["meta"]["priceSourceWindowKey"] == "365d"
    assert payload["meta"]["snapshot"]["sourceWindow"] == "365d"
    assert payload["meta"]["snapshot"]["usedFallbackWindow"] is True


def test_top_chase_payload_fallback_preserves_card_order_and_histories(monkeypatch):
    """C: the fallback must not re-rank cards or recompute prices/deltas — it
    serves exactly the cards/histories already stored on the 365d row."""
    ordered_cards = [
        {"cardId": "card-a", "cardVariantId": "variant-a", "name": "Card A", "marketPrice": 50.0},
        {"cardId": "card-b", "cardVariantId": "variant-b", "name": "Card B", "marketPrice": 40.0},
        {"cardId": "card-c", "cardVariantId": "variant-c", "name": "Card C", "marketPrice": 30.0},
    ]
    histories = {
        "variant-a": [{"date": "2026-06-30", "marketPrice": 50.0}],
        "variant-b": [{"date": "2026-06-30", "marketPrice": 40.0}],
        "variant-c": [{"date": "2026-06-30", "marketPrice": 30.0}],
    }
    row_365d = _top_chase_dashboard_row(
        window_key="365d", top_chase_cards_json=ordered_cards, top_chase_card_histories_json=histories
    )

    def read_dashboard(query):
        return [row_365d] if _window_key_from_query(query) == "365d" else []

    client = _Client({"pokemon_set_market_dashboard_snapshot_latest": read_dashboard})
    monkeypatch.setattr(pokemon_public_snapshot_service, "public_read_client", client)

    payload = pokemon_public_snapshot_service.get_pokemon_set_top_chase_snapshot_payload(_TEST_UUID, window="30D")

    assert [card["cardId"] for card in payload["topChaseCards"]] == ["card-a", "card-b", "card-c"]
    for key, points in histories.items():
        assert payload["topChaseCardHistories"][key] == points


def test_top_chase_payload_empty_fallback_when_neither_window_row_exists(monkeypatch):
    """D: neither a 30d nor a 365d row exists — the endpoint must still
    return the existing empty fallback shape with a missing-snapshot warning,
    not raise or silently synthesize data."""
    client = _Client({"pokemon_set_market_dashboard_snapshot_latest": lambda _q: []})
    monkeypatch.setattr(pokemon_public_snapshot_service, "public_read_client", client)

    payload = pokemon_public_snapshot_service.get_pokemon_set_top_chase_snapshot_payload(_TEST_UUID, window="30D")

    assert payload["topChaseCards"] == []
    assert payload["topChaseCardHistories"] == {}
    assert payload["meta"]["snapshot"]["source"] == "empty_fallback_missing_pokemon_set_market_dashboard_snapshot_latest"
    assert any("missing" in warning.lower() for warning in payload["meta"]["warnings"])


def test_top_chase_payload_fallback_uses_stored_histories_without_live_observation_query(monkeypatch):
    """E: the 365d fallback must serve the already-stored
    top_chase_card_histories_json as-is — it must never trigger a live
    card_variant_price_observations query. That hydration path belongs only
    to get_pokemon_set_market_dashboard_snapshot_payload/the full dashboard,
    never this slim endpoint."""
    row_365d = _top_chase_dashboard_row(window_key="365d")

    def read_dashboard(query):
        return [row_365d] if _window_key_from_query(query) == "365d" else []

    def reject_observations(_query):
        raise AssertionError("card_variant_price_observations must not be queried by the slim top-chase endpoint")

    client = _Client(
        {
            "pokemon_set_market_dashboard_snapshot_latest": read_dashboard,
            "card_variant_price_observations": reject_observations,
        }
    )
    monkeypatch.setattr(pokemon_public_snapshot_service, "public_read_client", client)

    payload = pokemon_public_snapshot_service.get_pokemon_set_top_chase_snapshot_payload(_TEST_UUID, window="30D")

    assert payload["topChaseCards"][0]["cardId"] == "card-1"
    assert payload["topChaseCardHistories"]["variant-1"]


def test_top_chase_payload_strips_redundant_embedded_card_price_history(monkeypatch):
    """Some market-dashboard-built rows (typically 365d rows) embed a full
    per-card priceHistory/historyDiagnostics directly on each
    top_chase_cards_json entry, duplicating the same days already served by
    the separate topChaseCardHistories dict. For 10 cards x 365 days this can
    push a single response past 700KB. These two redundant field-pairs must
    be stripped from the response; every other card field must survive
    untouched, and topChaseCardHistories must still carry the real data."""
    bloated_card = {
        "cardId": "card-1",
        "cardVariantId": "variant-1",
        "name": "Chase Card",
        "marketPrice": 42.5,
        "rank": 1,
        "priceHistory": [{"date": f"2026-01-{day:02d}", "marketPrice": 10.0 + day} for day in range(1, 29)],
        "price_history": [{"date": f"2026-01-{day:02d}", "marketPrice": 10.0 + day} for day in range(1, 29)],
        "historyDiagnostics": {"observationCount": 365, "gapDays": 0},
        "history_diagnostics": {"observationCount": 365, "gapDays": 0},
    }
    row_365d = _top_chase_dashboard_row(
        window_key="365d",
        top_chase_cards_json=[bloated_card],
        top_chase_card_histories_json={"variant-1": [{"date": "2026-06-30", "marketPrice": 5.0}]},
    )

    def read_dashboard(query):
        return [row_365d] if _window_key_from_query(query) == "365d" else []

    client = _Client({"pokemon_set_market_dashboard_snapshot_latest": read_dashboard})
    monkeypatch.setattr(pokemon_public_snapshot_service, "public_read_client", client)

    payload = pokemon_public_snapshot_service.get_pokemon_set_top_chase_snapshot_payload(_TEST_UUID, window="30D")

    card = payload["topChaseCards"][0]
    for redundant_key in ("priceHistory", "price_history", "historyDiagnostics", "history_diagnostics"):
        assert redundant_key not in card, f"{redundant_key} must be stripped from the response card"
    assert card["cardId"] == "card-1"
    # The served history reaches latestMarketDate, so current display and the
    # terminal chart point must agree.
    assert card["marketPrice"] == 5.0
    assert card["rank"] == 1
    assert payload["topChaseCardHistories"]["variant-1"] == [{"date": "2026-06-30", "marketPrice": 5.0}]


def test_top_chase_payload_serialized_size_stays_under_250kb_with_embedded_card_bloat(monkeypatch):
    """Regression guard for the Phase 5E budget finding: 10 cards each
    carrying a full dual-cased 365-day embedded priceHistory/
    historyDiagnostics (the real-world shape a 365d fallback row can have)
    must still serialize under the 250KB slim-contract budget once the
    redundant fields are stripped."""
    import json

    def _bloated_card(index):
        history = [{"date": f"2026-{(day % 12) + 1:02d}-{(day % 28) + 1:02d}", "marketPrice": round(10 + day * 0.1, 2)} for day in range(365)]
        return {
            "cardId": f"card-{index}",
            "cardVariantId": f"variant-{index}",
            "name": f"Chase Card {index}",
            "marketPrice": 10.0 + index,
            "priceHistory": history,
            "price_history": history,
            "historyDiagnostics": {"observationCount": 365, "gapDays": 0, "notes": "x" * 200},
            "history_diagnostics": {"observationCount": 365, "gapDays": 0, "notes": "x" * 200},
        }

    row_365d = _top_chase_dashboard_row(
        window_key="365d",
        top_chase_cards_json=[_bloated_card(index) for index in range(10)],
        top_chase_card_histories_json={
            f"variant-{index}": [
                {"date": f"2026-{(day % 12) + 1:02d}-{(day % 28) + 1:02d}", "marketPrice": round(10 + day * 0.1, 2)}
                for day in range(365)
            ]
            for index in range(10)
        },
    )

    def read_dashboard(query):
        return [row_365d] if _window_key_from_query(query) == "365d" else []

    client = _Client({"pokemon_set_market_dashboard_snapshot_latest": read_dashboard})
    monkeypatch.setattr(pokemon_public_snapshot_service, "public_read_client", client)

    payload = pokemon_public_snapshot_service.get_pokemon_set_top_chase_snapshot_payload(_TEST_UUID, window="30D", limit=10)

    serialized_bytes = len(json.dumps(payload, default=str).encode("utf-8"))
    assert serialized_bytes < 250_000, f"top-chase 365d-fallback payload was {serialized_bytes} bytes, over the 250KB budget"


# ---------------------------------------------------------------------------
# Phase 5F (Gate 2): top-chase cards-exist-but-histories-empty edge case
# (e.g. Ascended Heroes) — distinct from the Phase 5E whole-row-missing case.
# Here the served row's top_chase_cards_json is populated but its
# top_chase_card_histories_json is empty for every one of those cards. The
# fix is a scoped, read-only fallback to card_variant_price_observations
# (the same helper the full market-dashboard payload already uses), never a
# write and never an unscoped table scan.
# ---------------------------------------------------------------------------


def test_top_chase_payload_hydrates_histories_from_observations_when_stored_histories_empty(monkeypatch):
    """A: cards exist but top_chase_card_histories_json is empty (Ascended
    Heroes shape) and raw near-mint observations exist for the card's
    variant — the endpoint must hydrate histories read-only instead of
    serving cards with no price history."""
    row = _top_chase_dashboard_row(top_chase_card_histories_json={})

    def read_dashboard(_query):
        return [row]

    def read_observations(query):
        return _raw_observation_rows(5, variant_id="variant-1")

    client = _Client(
        {
            "pokemon_set_market_dashboard_snapshot_latest": read_dashboard,
            "card_variant_price_observations": read_observations,
        }
    )
    monkeypatch.setattr(pokemon_public_snapshot_service, "public_read_client", client)

    payload = pokemon_public_snapshot_service.get_pokemon_set_top_chase_snapshot_payload(_TEST_UUID, window="30D")

    assert payload["topChaseCards"][0]["cardId"] == "card-1"
    assert payload["topChaseCardHistories"]["variant-1"], "histories must be hydrated from raw observations"


def test_top_chase_payload_observation_hydration_is_scoped_to_variant_ids(monkeypatch):
    """B: the observation-hydration query must be scoped with an in_ filter
    on this row's own card_variant_id values — never an unscoped scan."""
    row = _top_chase_dashboard_row(top_chase_card_histories_json={})
    observation_queries = []

    def read_dashboard(_query):
        return [row]

    def read_observations(query):
        observation_queries.append(query)
        return _raw_observation_rows(5, variant_id="variant-1")

    client = _Client(
        {
            "pokemon_set_market_dashboard_snapshot_latest": read_dashboard,
            "card_variant_price_observations": read_observations,
        }
    )
    monkeypatch.setattr(pokemon_public_snapshot_service, "public_read_client", client)

    pokemon_public_snapshot_service.get_pokemon_set_top_chase_snapshot_payload(_TEST_UUID, window="30D")

    assert observation_queries, "expected a scoped card_variant_price_observations query"
    scoped_filters = [values for field, values in observation_queries[-1].in_filters if field == "card_variant_id"]
    assert scoped_filters and scoped_filters[0] == ["variant-1"]


def test_top_chase_payload_observation_hydration_preserves_price_history_ordering(monkeypatch):
    """C: hydrated history points must be ordered oldest-to-newest, matching
    the same ordering contract as stored histories."""
    row = _top_chase_dashboard_row(top_chase_card_histories_json={})

    def read_dashboard(_query):
        return [row]

    def read_observations(_query):
        return _raw_observation_rows(6, variant_id="variant-1", start_date="2026-06-01")

    client = _Client(
        {
            "pokemon_set_market_dashboard_snapshot_latest": read_dashboard,
            "card_variant_price_observations": read_observations,
        }
    )
    monkeypatch.setattr(pokemon_public_snapshot_service, "public_read_client", client)

    payload = pokemon_public_snapshot_service.get_pokemon_set_top_chase_snapshot_payload(_TEST_UUID, window="30D")

    history = payload["topChaseCardHistories"]["variant-1"]
    dates = [point["date"] for point in history]
    assert dates == sorted(dates)
    assert dates[0] == "2026-06-01"
    assert dates[-1] == "2026-06-06"


def test_top_chase_payload_observation_hydration_meta_marks_source_clearly(monkeypatch):
    """D: meta must clearly mark that histories were hydrated from raw
    observations rather than the stored snapshot, with min/max point counts."""
    row = _top_chase_dashboard_row(top_chase_card_histories_json={})

    def read_dashboard(_query):
        return [row]

    def read_observations(_query):
        return _raw_observation_rows(7, variant_id="variant-1")

    client = _Client(
        {
            "pokemon_set_market_dashboard_snapshot_latest": read_dashboard,
            "card_variant_price_observations": read_observations,
        }
    )
    monkeypatch.setattr(pokemon_public_snapshot_service, "public_read_client", client)

    payload = pokemon_public_snapshot_service.get_pokemon_set_top_chase_snapshot_payload(_TEST_UUID, window="30D")

    assert payload["meta"]["topChaseHistorySource"] == "card_variant_price_observations"
    assert payload["meta"]["topChaseHistoryHydratedFromObservations"] is True
    assert payload["meta"]["topChaseHistoryMinPoints"] == 7
    assert payload["meta"]["topChaseHistoryMaxPoints"] == 7


def test_top_chase_payload_safe_when_stored_histories_and_observations_both_empty(monkeypatch):
    """E: cards exist, stored histories are empty, and no raw observations
    exist either — the endpoint must not crash and must serve cards with a
    clear history-missing warning instead of raising."""
    row = _top_chase_dashboard_row(top_chase_card_histories_json={})

    def read_dashboard(_query):
        return [row]

    def read_observations(_query):
        return []

    client = _Client(
        {
            "pokemon_set_market_dashboard_snapshot_latest": read_dashboard,
            "card_variant_price_observations": read_observations,
        }
    )
    monkeypatch.setattr(pokemon_public_snapshot_service, "public_read_client", client)

    payload = pokemon_public_snapshot_service.get_pokemon_set_top_chase_snapshot_payload(_TEST_UUID, window="30D")

    assert payload["topChaseCards"][0]["cardId"] == "card-1"
    assert payload["topChaseCardHistories"] == {}
    assert payload["meta"]["topChaseHistoryHydratedFromObservations"] is False
    assert payload["meta"]["topChaseHistoryMinPoints"] == 0
    assert payload["meta"]["topChaseHistoryMaxPoints"] == 0
    assert any("no raw price" in warning.lower() for warning in payload["meta"]["warnings"])


def test_top_chase_payload_does_not_query_observations_when_stored_histories_already_populated(monkeypatch):
    """F: regression guard — when stored histories already have data, the new
    Gate 2 fallback must not run an observation query at all (Phase 5E's
    existing no-live-query guarantee must still hold)."""
    row = _top_chase_dashboard_row()  # default fixture already has variant-1 history data

    def read_dashboard(_query):
        return [row]

    def reject_observations(_query):
        raise AssertionError("card_variant_price_observations must not be queried when stored histories exist")

    client = _Client(
        {
            "pokemon_set_market_dashboard_snapshot_latest": read_dashboard,
            "card_variant_price_observations": reject_observations,
        }
    )
    monkeypatch.setattr(pokemon_public_snapshot_service, "public_read_client", client)

    payload = pokemon_public_snapshot_service.get_pokemon_set_top_chase_snapshot_payload(_TEST_UUID, window="30D")

    assert payload["topChaseCardHistories"]["variant-1"]
    assert payload["meta"]["topChaseHistoryHydratedFromObservations"] is False


# ---------------------------------------------------------------------------
# Phase 3C — get_pokemon_set_card_validation_snapshot_payload: slim Insights
# card-validation contract sourced from pokemon_set_cards_snapshot_latest,
# without ever returning the full checklist `cards` array or payload_json.
# ---------------------------------------------------------------------------


def _card_validation_payload_json_fixture(*, card_count=2):
    full_cards = []
    validation_cards = []
    plot_rows = []
    for index in range(card_count):
        card_id = f"card-{index}"
        full_cards.append(
            {
                "id": card_id,
                "name": f"Card {index}",
                "rarity": "Rare",
                "supertype": "Pokémon" if index % 2 == 0 else "Trainer",
                "printedNumber": str(index + 1),
                "marketPrice": 10.0 + index,
                "subtypes": ["Basic"],
                "nationalPokedexNumbers": [index + 1],
                "movement30d": {"currentPrice": 10.0 + index},
            }
        )
        validation_cards.append(
            {
                "cardId": card_id,
                "cardVariantId": f"variant-{index}",
                "name": f"Card {index}",
                "rarity": "Rare",
                "imageUrl": f"https://images.example.com/{index}.png",
                "marketPrice": 10.0 + index,
                "market_price": 10.0 + index,
                "pokemonName": "Pikachu",
                "pokemonDesirabilityScore": 80.0 + index,
                "treatmentScore": 90.0,
                "scarcityScore": 50.0,
                "adjustedCardAppealScore": 75.0 + index,
                "pullRate": 0.01,
                "pullRateSource": "pullRate",
                "setValueShare": 0.02,
                "isHitEligible": index == 0,
            }
        )
        plot_rows.append(
            {
                "pokemon_canonical_card_id": card_id,
                "pokemonCanonicalCardId": card_id,
                "card_name": f"Card {index}",
                "cardName": f"Card {index}",
                "market_price": 10.0 + index,
                "marketPrice": 10.0 + index,
                "subject_desirability_score": 80.0 + index,
                "subjectDesirabilityScore": 80.0 + index,
                "is_hit_eligible": index == 0,
                "isHitEligible": index == 0,
            }
        )
    correlation = {
        "canonical_count": card_count,
        "priced_count": card_count,
        "linked_count": card_count,
        "scored_linked_count": card_count,
        "included_count": card_count,
        "excluded_unpriced_count": 0,
        "excluded_unlinked_count": 0,
        "excluded_missing_score_count": 0,
        "n": card_count,
        "pearson": 0.5,
        "spearman": 0.5,
        "interpretation": "healthy_separation",
        "sample_source": "canonical_checklist_cards",
        "rows": plot_rows,
        "plot_rows": plot_rows,
        "plotRows": plot_rows,
        "plotted_count": len(plot_rows),
        "plottedCount": len(plot_rows),
        "metric_diagnostics": {"purePokemonDemand": {"canonical_count": card_count}},
        "metricDiagnostics": {"purePokemonDemand": {"canonicalCount": card_count}},
    }
    return {
        "cards": full_cards,
        "cardDesirabilityValidation": {"cards": validation_cards, "meta": {}},
        "cardAppealMarketPriceCorrelation": correlation,
        "meta": {},
    }


def _assert_no_snake_case_keys(value, path="root"):
    if isinstance(value, dict):
        for key, inner in value.items():
            assert not (isinstance(key, str) and "_" in key), f"snake_case key '{key}' found at {path}"
            _assert_no_snake_case_keys(inner, f"{path}.{key}")
    elif isinstance(value, list):
        for index, item in enumerate(value):
            _assert_no_snake_case_keys(item, f"{path}[{index}]")


def test_card_validation_payload_excludes_full_cards_array(monkeypatch):
    payload_json = _card_validation_payload_json_fixture(card_count=2)
    client = _Client(
        {
            "pokemon_set_cards_snapshot_latest": lambda _q: [
                {
                    "set_id": _TEST_UUID,
                    "card_count": 2,
                    "updated_at": "2026-06-30T00:00:00+00:00",
                    "payload_json": payload_json,
                }
            ],
        }
    )
    monkeypatch.setattr(pokemon_public_snapshot_service, "public_read_client", client)

    payload = pokemon_public_snapshot_service.get_pokemon_set_card_validation_snapshot_payload(_TEST_UUID)

    assert "payload_json" not in payload
    assert len(payload["cards"]) == 2
    for card in payload["cards"]:
        # Full enriched-card-only fields must never leak into the slim contract.
        assert "subtypes" not in card
        assert "nationalPokedexNumbers" not in card
        assert "movement30d" not in card
        assert set(card.keys()) == {
            "cardId",
            "cardVariantId",
            "name",
            "rarity",
            "supertype",
            "printedNumber",
            "imageUrl",
            "marketPrice",
            "linkedPokemonName",
            "pokemonDesirabilityScore",
            "treatmentScore",
            "scarcityScore",
            "adjustedCardAppealScore",
            "pullRate",
            "pullRateSource",
            "setValueShare",
            "isHitEligible",
        }


def test_card_validation_payload_returns_cards_and_correlation(monkeypatch):
    payload_json = _card_validation_payload_json_fixture(card_count=3)
    client = _Client(
        {
            "pokemon_set_cards_snapshot_latest": lambda _q: [
                {
                    "set_id": _TEST_UUID,
                    "card_count": 3,
                    "updated_at": "2026-06-30T00:00:00+00:00",
                    "payload_json": payload_json,
                }
            ],
        }
    )
    monkeypatch.setattr(pokemon_public_snapshot_service, "public_read_client", client)

    payload = pokemon_public_snapshot_service.get_pokemon_set_card_validation_snapshot_payload(_TEST_UUID)

    assert payload["cards"][0]["cardId"] == "card-0"
    assert payload["cards"][0]["supertype"] == "Pokémon"
    assert payload["cards"][0]["printedNumber"] == "1"
    assert payload["cardAppealMarketPriceCorrelation"]["n"] == 3
    assert payload["cardAppealMarketPriceCorrelation"]["pearson"] == 0.5
    assert len(payload["cardAppealMarketPriceCorrelation"]["plotRows"]) == 3
    assert payload["diagnostics"]["canonicalCount"] == 3
    assert payload["diagnostics"]["sampleSource"] == "canonical_checklist_cards"


def test_card_validation_payload_is_camel_case_only(monkeypatch):
    payload_json = _card_validation_payload_json_fixture(card_count=2)
    client = _Client(
        {
            "pokemon_set_cards_snapshot_latest": lambda _q: [
                {
                    "set_id": _TEST_UUID,
                    "card_count": 2,
                    "updated_at": "2026-06-30T00:00:00+00:00",
                    "payload_json": payload_json,
                }
            ],
        }
    )
    monkeypatch.setattr(pokemon_public_snapshot_service, "public_read_client", client)

    payload = pokemon_public_snapshot_service.get_pokemon_set_card_validation_snapshot_payload(_TEST_UUID)

    _assert_no_snake_case_keys(payload)


def test_card_validation_payload_resolves_hyphenated_slug(monkeypatch):
    sets_rows = [
        {"id": "set-uuid-1", "name": "Prismatic Evolutions", "canonical_key": "prismaticEvolutions", "pokemon_api_set_id": "sv8pt5"}
    ]

    def read_sets(query):
        if query.eq_filters:
            field, value = query.eq_filters[-1]
            return [row for row in sets_rows if row.get(field) == value]
        return sets_rows

    payload_json = _card_validation_payload_json_fixture(card_count=1)
    client = _Client(
        {
            "sets": read_sets,
            "pokemon_set_cards_snapshot_latest": lambda _q: [
                {
                    "set_id": "set-uuid-1",
                    "card_count": 1,
                    "updated_at": "2026-06-30T00:00:00+00:00",
                    "payload_json": payload_json,
                }
            ],
        }
    )
    monkeypatch.setattr(pokemon_public_snapshot_service, "public_read_client", client)

    payload = pokemon_public_snapshot_service.get_pokemon_set_card_validation_snapshot_payload("prismatic-evolutions")

    assert payload["set"]["id"] == "set-uuid-1"
    assert payload["set"]["slug"] == "prismaticEvolutions"
    assert len(payload["cards"]) == 1


def test_card_validation_payload_missing_snapshot_returns_empty_fallback(monkeypatch):
    client = _Client({"pokemon_set_cards_snapshot_latest": lambda _q: []})
    monkeypatch.setattr(pokemon_public_snapshot_service, "public_read_client", client)

    payload = pokemon_public_snapshot_service.get_pokemon_set_card_validation_snapshot_payload(_TEST_UUID)

    assert payload["cards"] == []
    assert payload["cardAppealMarketPriceCorrelation"] is None
    assert payload["diagnostics"]["includedCount"] == 0
    assert payload["diagnostics"]["sampleSource"] == "canonical_checklist_cards"
    assert any("card validation snapshot is missing" in w.lower() for w in payload["meta"]["warnings"])
    assert payload["meta"]["source"] == "empty_fallback_missing_pokemon_set_cards_snapshot_latest"


def test_card_validation_payload_serialized_size_is_under_250kb(monkeypatch):
    import json

    payload_json = _card_validation_payload_json_fixture(card_count=600)
    client = _Client(
        {
            "pokemon_set_cards_snapshot_latest": lambda _q: [
                {
                    "set_id": _TEST_UUID,
                    "card_count": 600,
                    "updated_at": "2026-06-30T00:00:00+00:00",
                    "payload_json": payload_json,
                }
            ],
        }
    )
    monkeypatch.setattr(pokemon_public_snapshot_service, "public_read_client", client)

    payload = pokemon_public_snapshot_service.get_pokemon_set_card_validation_snapshot_payload(_TEST_UUID)

    serialized_bytes = len(json.dumps(payload, default=str).encode("utf-8"))
    assert serialized_bytes < 250_000, f"card validation payload was {serialized_bytes} bytes, over the 250KB budget"
    # 600 available cards > the default max_cards=300 cap, so truncation must be flagged.
    assert payload["meta"]["truncated"] is True
    assert payload["meta"]["totalCards"] == 600
    assert payload["diagnostics"]["canonicalCount"] == 600, "diagnostics counts must not be dropped when truncated"


# ---------------------------------------------------------------------------
# Phase 4A — Pull Rates tab now uses its own slim contract
# (get_pokemon_set_pull_rates_snapshot_payload) instead of requiring the full
# /page payload. It reads pokemon_set_page_snapshot_latest.payload_json only
# to extract pull_rate_assumptions — never cards, market dashboard/top chase/
# market movers, rankings, or top_hits.
# ---------------------------------------------------------------------------


def _pull_rates_payload_json_fixture(*, row_count=3, group_count=1):
    rows = []
    for index in range(row_count):
        rows.append(
            {
                "rarity": f"Rarity {index}",
                "slotLabel": f"Slot {index}",
                "slot_label": f"Slot {index}",
                "cardCount": 10 + index,
                "card_count": 10 + index,
                "expectedCardsPerPack": 1.5,
                "expected_cards_per_pack": 1.5,
                "rarityOddsDenominator": 20 + index,
                "rarity_odds_denominator": 20 + index,
                "specificCardOddsDenominator": 200 + index,
                "specific_card_odds_denominator": 200 + index,
            }
        )
    groups = [
        {
            "key": f"group_{group_index}",
            "label": f"Group {group_index}",
            "rows": rows,
        }
        for group_index in range(group_count)
    ]
    return {
        "pull_rate_assumptions": {"groups": groups, "rows": []},
        # These sections must never leak into the slim pull-rates contract.
        "cards": [{"id": "card-0", "name": "Should not leak into pull rates"}],
        "top_hits": [{"id": "hit-0", "name": "Should not leak"}],
        "market_dashboard": {"topChaseCards": [{"id": "top-0"}], "marketMovers": {"heatingUp": []}},
        "rankings": [{"id": "rank-0"}],
    }


def test_pull_rates_payload_excludes_cards_and_market_dashboard_and_full_payload_json(monkeypatch):
    payload_json = _pull_rates_payload_json_fixture()
    client = _Client(
        {
            "pokemon_set_page_snapshot_latest": lambda _q: [
                {
                    "set_id": _TEST_UUID,
                    "updated_at": "2026-06-30T00:00:00+00:00",
                    "payload_json": payload_json,
                }
            ],
        }
    )
    monkeypatch.setattr(pokemon_public_snapshot_service, "public_read_client", client)

    payload = pokemon_public_snapshot_service.get_pokemon_set_pull_rates_snapshot_payload(_TEST_UUID)

    assert "payload_json" not in payload
    assert "cards" not in payload
    assert "topHits" not in payload and "top_hits" not in payload
    assert "rankings" not in payload
    assert "marketDashboard" not in payload and "market_dashboard" not in payload
    assert "topChaseCards" not in payload
    assert "marketMovers" not in payload
    assert payload["pullRates"]["groups"][0]["rows"][0]["rarity"] == "Rarity 0"


def test_pull_rates_payload_returns_pull_rate_assumptions(monkeypatch):
    payload_json = _pull_rates_payload_json_fixture(row_count=2)
    client = _Client(
        {
            "pokemon_set_page_snapshot_latest": lambda _q: [
                {
                    "set_id": _TEST_UUID,
                    "updated_at": "2026-06-30T00:00:00+00:00",
                    "payload_json": payload_json,
                }
            ],
        }
    )
    monkeypatch.setattr(pokemon_public_snapshot_service, "public_read_client", client)

    payload = pokemon_public_snapshot_service.get_pokemon_set_pull_rates_snapshot_payload(_TEST_UUID)

    assert payload["pullRates"]["groups"][0]["key"] == "group_0"
    assert len(payload["pullRates"]["groups"][0]["rows"]) == 2
    assert payload["pullRates"]["groups"][0]["rows"][0]["cardCount"] == 10
    assert payload["packPaths"] == []
    assert payload["rarityBuckets"] == []
    assert payload["assumptions"] == {}
    assert payload["sources"] == []
    assert payload["meta"]["source"] == "pokemon_set_page_snapshot_latest"
    assert payload["meta"]["warnings"] == []


def test_pull_rates_payload_is_camel_case_only(monkeypatch):
    payload_json = _pull_rates_payload_json_fixture()
    client = _Client(
        {
            "pokemon_set_page_snapshot_latest": lambda _q: [
                {
                    "set_id": _TEST_UUID,
                    "updated_at": "2026-06-30T00:00:00+00:00",
                    "payload_json": payload_json,
                }
            ],
        }
    )
    monkeypatch.setattr(pokemon_public_snapshot_service, "public_read_client", client)

    payload = pokemon_public_snapshot_service.get_pokemon_set_pull_rates_snapshot_payload(_TEST_UUID)

    _assert_no_snake_case_keys(payload)


def test_pull_rates_payload_resolves_hyphenated_slug(monkeypatch):
    sets_rows = [
        {"id": "set-uuid-1", "name": "Prismatic Evolutions", "canonical_key": "prismaticEvolutions", "pokemon_api_set_id": "sv8pt5"}
    ]

    def read_sets(query):
        if query.eq_filters:
            field, value = query.eq_filters[-1]
            return [row for row in sets_rows if row.get(field) == value]
        return sets_rows

    payload_json = _pull_rates_payload_json_fixture(row_count=1)
    client = _Client(
        {
            "sets": read_sets,
            "pokemon_set_page_snapshot_latest": lambda _q: [
                {
                    "set_id": "set-uuid-1",
                    "updated_at": "2026-06-30T00:00:00+00:00",
                    "payload_json": payload_json,
                }
            ],
        }
    )
    monkeypatch.setattr(pokemon_public_snapshot_service, "public_read_client", client)

    payload = pokemon_public_snapshot_service.get_pokemon_set_pull_rates_snapshot_payload("prismatic-evolutions")

    assert payload["set"]["id"] == "set-uuid-1"
    assert payload["set"]["slug"] == "prismaticEvolutions"
    assert len(payload["pullRates"]["groups"][0]["rows"]) == 1


def test_pull_rates_payload_missing_snapshot_returns_empty_fallback(monkeypatch):
    client = _Client({"pokemon_set_page_snapshot_latest": lambda _q: []})
    monkeypatch.setattr(pokemon_public_snapshot_service, "public_read_client", client)

    payload = pokemon_public_snapshot_service.get_pokemon_set_pull_rates_snapshot_payload(_TEST_UUID)

    assert payload["pullRates"] is None
    assert payload["packPaths"] == []
    assert payload["rarityBuckets"] == []
    assert payload["assumptions"] == {}
    assert payload["sources"] == []
    assert any("pull rates snapshot is missing" in w.lower() for w in payload["meta"]["warnings"])
    assert payload["meta"]["source"] == "empty_fallback_missing_pokemon_set_page_snapshot_latest"


def test_pull_rates_payload_serialized_size_is_under_150kb(monkeypatch):
    import json

    payload_json = _pull_rates_payload_json_fixture(row_count=200, group_count=3)
    client = _Client(
        {
            "pokemon_set_page_snapshot_latest": lambda _q: [
                {
                    "set_id": _TEST_UUID,
                    "updated_at": "2026-06-30T00:00:00+00:00",
                    "payload_json": payload_json,
                }
            ],
        }
    )
    monkeypatch.setattr(pokemon_public_snapshot_service, "public_read_client", client)

    payload = pokemon_public_snapshot_service.get_pokemon_set_pull_rates_snapshot_payload(_TEST_UUID)

    serialized_bytes = len(json.dumps(payload, default=str).encode("utf-8"))
    assert serialized_bytes < 150_000, f"pull rates payload was {serialized_bytes} bytes, over the 150KB budget"


# ---------------------------------------------------------------------------
# Gate 3 (Phase 5G): pull-rates source resolution priority — split column
# (pull_rate_assumptions_json, forward-compat only; no such column exists on
# pokemon_set_page_snapshot_latest today) > payload_json.pullRateAssumptions
# (camelCase) > payload_json.pull_rate_assumptions (snake_case). Values must
# pass through untouched — only key casing/source selection is decided here.
# ---------------------------------------------------------------------------


def test_pull_rates_payload_reads_split_column_when_present(monkeypatch):
    """A: a dedicated split column, if a row happens to carry one, must be
    preferred over payload_json entirely."""
    split_column_value = {"groups": [{"key": "split-group", "label": "Split Group", "rows": []}], "rows": []}
    client = _Client(
        {
            "pokemon_set_page_snapshot_latest": lambda _q: [
                {
                    "set_id": _TEST_UUID,
                    "updated_at": "2026-06-30T00:00:00+00:00",
                    "payload_json": {"pull_rate_assumptions": None},
                    "pull_rate_assumptions_json": split_column_value,
                }
            ],
        }
    )
    monkeypatch.setattr(pokemon_public_snapshot_service, "public_read_client", client)

    payload = pokemon_public_snapshot_service.get_pokemon_set_pull_rates_snapshot_payload(_TEST_UUID)

    assert payload["pullRates"]["groups"][0]["key"] == "split-group"
    assert payload["meta"]["snapshot"]["sourceField"] == "pull_rate_assumptions_json"
    assert payload["meta"]["snapshot"]["usedPayloadJsonFallback"] is False


def test_pull_rates_payload_falls_back_to_camel_case_payload_json_when_split_column_missing(monkeypatch):
    """B: no split column on the row — payload_json.pullRateAssumptions
    (camelCase) must be read next, ahead of the snake_case key."""
    client = _Client(
        {
            "pokemon_set_page_snapshot_latest": lambda _q: [
                {
                    "set_id": _TEST_UUID,
                    "updated_at": "2026-06-30T00:00:00+00:00",
                    "payload_json": {
                        "pullRateAssumptions": {"groups": [{"key": "camel-group", "label": "Camel", "rows": []}], "rows": []},
                    },
                }
            ],
        }
    )
    monkeypatch.setattr(pokemon_public_snapshot_service, "public_read_client", client)

    payload = pokemon_public_snapshot_service.get_pokemon_set_pull_rates_snapshot_payload(_TEST_UUID)

    assert payload["pullRates"]["groups"][0]["key"] == "camel-group"
    assert payload["meta"]["snapshot"]["sourceField"] == "payload_json.pullRateAssumptions"
    assert payload["meta"]["snapshot"]["usedPayloadJsonFallback"] is True


def test_pull_rates_payload_falls_back_to_snake_case_payload_json_when_camel_case_missing(monkeypatch):
    """C: neither a split column nor payload_json.pullRateAssumptions exist —
    payload_json.pull_rate_assumptions (snake_case) must still be read."""
    payload_json = _pull_rates_payload_json_fixture(row_count=1)
    client = _Client(
        {
            "pokemon_set_page_snapshot_latest": lambda _q: [
                {
                    "set_id": _TEST_UUID,
                    "updated_at": "2026-06-30T00:00:00+00:00",
                    "payload_json": payload_json,
                }
            ],
        }
    )
    monkeypatch.setattr(pokemon_public_snapshot_service, "public_read_client", client)

    payload = pokemon_public_snapshot_service.get_pokemon_set_pull_rates_snapshot_payload(_TEST_UUID)

    assert payload["pullRates"]["groups"][0]["key"] == "group_0"
    assert payload["meta"]["snapshot"]["sourceField"] == "payload_json.pull_rate_assumptions"
    assert payload["meta"]["snapshot"]["usedPayloadJsonFallback"] is True


def test_pull_rates_payload_split_column_wins_over_payload_json_when_both_exist(monkeypatch):
    """D: split column and payload_json both have data — split column wins."""
    split_column_value = {"groups": [{"key": "split-wins", "label": "Split Wins", "rows": []}], "rows": []}
    payload_json = _pull_rates_payload_json_fixture(row_count=1)
    client = _Client(
        {
            "pokemon_set_page_snapshot_latest": lambda _q: [
                {
                    "set_id": _TEST_UUID,
                    "updated_at": "2026-06-30T00:00:00+00:00",
                    "payload_json": payload_json,
                    "pull_rate_assumptions_json": split_column_value,
                }
            ],
        }
    )
    monkeypatch.setattr(pokemon_public_snapshot_service, "public_read_client", client)

    payload = pokemon_public_snapshot_service.get_pokemon_set_pull_rates_snapshot_payload(_TEST_UUID)

    assert payload["pullRates"]["groups"][0]["key"] == "split-wins"
    assert payload["meta"]["snapshot"]["sourceField"] == "pull_rate_assumptions_json"


def test_pull_rates_payload_row_with_no_pull_rate_data_returns_empty_with_warning(monkeypatch):
    """E: the page snapshot row exists but has no pull-rate data anywhere
    (the real shape found for 11/171 sets during Gate 3 diagnosis) — must
    return a safe empty pullRates with a clear warning, never crash or
    invent a value."""
    client = _Client(
        {
            "pokemon_set_page_snapshot_latest": lambda _q: [
                {
                    "set_id": _TEST_UUID,
                    "updated_at": "2026-06-30T00:00:00+00:00",
                    "payload_json": {"pull_rate_assumptions": None, "cards": []},
                }
            ],
        }
    )
    monkeypatch.setattr(pokemon_public_snapshot_service, "public_read_client", client)

    payload = pokemon_public_snapshot_service.get_pokemon_set_pull_rates_snapshot_payload(_TEST_UUID)

    assert payload["pullRates"] is None
    assert payload["meta"]["snapshot"]["sourceField"] == "none"
    assert any("not available" in w.lower() for w in payload["meta"]["warnings"])


def test_pull_rates_payload_values_are_not_recalculated(monkeypatch):
    """F: numeric values must pass through byte-for-byte — only key casing
    changes, never a recomputation."""
    payload_json = _pull_rates_payload_json_fixture(row_count=1)
    client = _Client(
        {
            "pokemon_set_page_snapshot_latest": lambda _q: [
                {
                    "set_id": _TEST_UUID,
                    "updated_at": "2026-06-30T00:00:00+00:00",
                    "payload_json": payload_json,
                }
            ],
        }
    )
    monkeypatch.setattr(pokemon_public_snapshot_service, "public_read_client", client)

    payload = pokemon_public_snapshot_service.get_pokemon_set_pull_rates_snapshot_payload(_TEST_UUID)

    row = payload["pullRates"]["groups"][0]["rows"][0]
    source_row = payload_json["pull_rate_assumptions"]["groups"][0]["rows"][0]
    assert row["cardCount"] == source_row["card_count"]
    assert row["expectedCardsPerPack"] == source_row["expected_cards_per_pack"]
    assert row["rarityOddsDenominator"] == source_row["rarity_odds_denominator"]
    assert row["specificCardOddsDenominator"] == source_row["specific_card_odds_denominator"]


# ---------------------------------------------------------------------------
# Phase 4B — Insights slim contract. Must never depend on the full /page
# payload for its consumers (cards, market dashboard, pull rates, per-card
# validation rows), must be camelCase-only, and must keep the exact raw
# section field names selectRipScoreBreakdown/selectSimulationDrivers/
# selectTrendScores/RipDistributionChart/RarityContributionContent need
# (after camelCasing), so the frontend adapter can rebuild an
# explorePayload-compatible shape without any new analytics logic.
# ---------------------------------------------------------------------------


def _insights_payload_json_fixture(*, top_hits_count=3, rankings_count=4, history_days=5):
    return {
        "summary": {
            "target_id": _TEST_UUID,
            "set_id": _TEST_UUID,
            "name": "Prismatic Evolutions",
            "pack_score": 71.4,
            "relative_pack_score": 71.4,
            "pack_rank": 3,
            "pack_tier": "Strong Buy",
            "profit_score": 60.0,
            "relative_profit_score": 60.0,
            "profit_rank": 5,
            "profit_tier": "Good",
            "safety_score": 55.0,
            "relative_safety_score": 55.0,
            "safety_rank": 8,
            "safety_tier": "Fair",
            "desirability_score": 88.0,
            "relative_desirability_score": 88.0,
            "desirability_rank": 1,
            "desirability_tier": "Elite",
            "stability_score": 40.0,
            "relative_stability_score": 40.0,
            "stability_rank": 12,
            "stability_tier": "Weak",
            "pack_cost": 4.99,
            "mean_value": 5.5,
            "mean_value_to_cost_ratio": 1.1,
            "average_hit_value": 12.3,
            "prob_profit": 0.42,
            "prob_big_hit": 0.05,
            "current_checklist_set_value": 123.45,
        },
        "interpretation": {
            "meta": {
                "packScore": {"label": "Strong Buy", "summary": "This set beats its pack cost more often than most."},
                "profit": {"summary": "Profit summary"},
                "safety": {"summary": "Safety summary"},
                "desirability": {"summary": "Desirability summary"},
                "stability": {"summary": "Stability summary"},
                "outcomeDistribution": {"summary": "Outcome distribution summary"},
                "historicalTrend": {"summary": "Historical trend summary"},
                "packBreakdown": {"summary": "Pack breakdown summary"},
                "topEvDrivers": {"summary": "Top EV drivers summary"},
                "rarityContribution": {"summary": "Rarity contribution summary"},
                "pillars": [{"title": "Profit", "score": 60.0, "rankTier": "Good", "rankValue": 5}],
            }
        },
        "rip_statistics": {
            "pack_paths": {"normal": {"count": 10}},
            "normal_pack_states": {"miss": 0.4, "hit": 0.6},
        },
        "percentiles": [{"percentile": 50, "value": 5.5}, {"percentile": 95, "value": 20.0}],
        "distribution_bins": [
            {"bin_floor": 0, "bin_ceiling": 5, "occurrence_count": 400, "probability": 0.4, "cumulative_probability": 0.4}
        ],
        "threshold_bins": [
            {"threshold_floor": 5, "threshold_ceiling": 10, "occurrence_count": 100, "probability": 0.1, "cumulative_probability": 0.5}
        ],
        "top_hits": [
            {
                "card_name": f"Chase Card {index}",
                "ev_contribution": 1.5 + index,
                "current_near_mint_price": 20.0 + index,
                "image_url": f"https://example.test/card-{index}.png",
            }
            for index in range(top_hits_count)
        ],
        "rankings": [
            {"rarity_bucket": f"Rarity {index}", "total_sampled_value": 100.0 + index, "pulled_count": 10 + index}
            for index in range(rankings_count)
        ],
        "history_trend": [
            {"date": f"2026-06-{day:02d}", "meanValue": 5.0 + day, "packCost": 4.99} for day in range(1, history_days + 1)
        ],
        "openingDesirability": {
            "openingDesirabilityScore": 77.0,
            "openingDesirabilityRank": 2,
            "collectorAppealScore": 81.0,
            "topCollectorAppealDrivers": [{"name": "Umbreon ex", "cardDesirabilityScore": 95.0}],
        },
        "desirabilityValidation": {
            "desirability_impact_band": "high",
            "card_appeal_score": 91.2,
            "rip_core_rank_without_desirability": 9,
            "final_rip_rank_with_desirability": 3,
        },
        # These sections must never leak into the slim insights contract.
        "cards": [{"id": "card-0", "name": "Should not leak into insights"}],
        "market_dashboard": {"topChaseCards": [{"id": "top-0"}], "marketMovers": {"heatingUp": []}},
        "pull_rate_assumptions": {"groups": [], "rows": []},
        "cardDesirabilityValidation": {"cards": [{"id": "card-0", "pokemonDesirabilityScore": 90.0}]},
        "card_desirability_validation": {"cards": [{"id": "card-0", "pokemonDesirabilityScore": 90.0}]},
    }


def test_insights_payload_excludes_cards_and_market_and_pull_rates_and_full_payload_json(monkeypatch):
    payload_json = _insights_payload_json_fixture()
    client = _Client(
        {
            "pokemon_set_page_snapshot_latest": lambda _q: [
                {"set_id": _TEST_UUID, "updated_at": "2026-06-30T00:00:00+00:00", "payload_json": payload_json}
            ],
        }
    )
    monkeypatch.setattr(pokemon_public_snapshot_service, "public_read_client", client)

    payload = pokemon_public_snapshot_service.get_pokemon_set_insights_snapshot_payload(_TEST_UUID)

    assert "payload_json" not in payload
    assert "cards" not in payload
    assert "marketDashboard" not in payload and "market_dashboard" not in payload
    assert "topChaseCards" not in payload
    assert "marketMovers" not in payload
    assert "pullRates" not in payload and "pullRateAssumptions" not in payload and "pull_rate_assumptions" not in payload
    assert "cardDesirabilityValidation" not in payload and "card_desirability_validation" not in payload
    # The set-level desirability *proof* row is allowed; per-card validation rows are not.
    assert "cards" not in payload["desirabilityValidation"]


def test_insights_payload_returns_rip_breakdown_inputs(monkeypatch):
    payload_json = _insights_payload_json_fixture()
    client = _Client(
        {
            "pokemon_set_page_snapshot_latest": lambda _q: [
                {"set_id": _TEST_UUID, "updated_at": "2026-06-30T00:00:00+00:00", "payload_json": payload_json}
            ],
        }
    )
    monkeypatch.setattr(pokemon_public_snapshot_service, "public_read_client", client)

    payload = pokemon_public_snapshot_service.get_pokemon_set_insights_snapshot_payload(_TEST_UUID)

    assert payload["set"]["id"] == _TEST_UUID
    assert payload["summary"]["relativeProfitScore"] == 60.0
    assert payload["summary"]["profitRank"] == 5
    assert payload["summary"]["profitTier"] == "Good"
    assert payload["recommendation"]["label"] == "Strong Buy"
    assert payload["ripScore"]["score"] == 71.4
    assert payload["ripScore"]["rank"] == 3
    assert payload["ripScore"]["tier"] == "Strong Buy"
    assert payload["ripStatistics"]["normalPackStates"]["hit"] == 0.6
    assert payload["outcomeDistribution"]["percentiles"][0]["percentile"] == 50
    assert payload["outcomeDistribution"]["distributionBins"][0]["binFloor"] == 0
    assert payload["outcomeDistribution"]["thresholdBins"][0]["thresholdFloor"] == 5
    assert len(payload["simulationDrivers"]) == 3
    assert payload["simulationDrivers"][0]["cardName"] == "Chase Card 0"
    assert len(payload["rarityContribution"]) == 4
    assert payload["rarityContribution"][0]["rarityBucket"] == "Rarity 0"
    assert payload["rarityContribution"][0]["totalSampledValue"] == 100.0
    assert len(payload["historyTrend"]) == 5
    assert payload["desirability"]["openingDesirabilityScore"] == 77.0
    assert payload["desirabilityValidation"]["cardAppealScore"] == 91.2
    assert payload["interpretation"]["meta"]["packScore"]["label"] == "Strong Buy"
    assert payload["meta"]["source"] == "pokemon_set_page_snapshot_latest"
    assert payload["meta"]["warnings"] == []


def test_insights_payload_is_camel_case_only(monkeypatch):
    payload_json = _insights_payload_json_fixture()
    client = _Client(
        {
            "pokemon_set_page_snapshot_latest": lambda _q: [
                {"set_id": _TEST_UUID, "updated_at": "2026-06-30T00:00:00+00:00", "payload_json": payload_json}
            ],
        }
    )
    monkeypatch.setattr(pokemon_public_snapshot_service, "public_read_client", client)

    payload = pokemon_public_snapshot_service.get_pokemon_set_insights_snapshot_payload(_TEST_UUID)

    _assert_no_snake_case_keys(payload)


def test_insights_payload_resolves_hyphenated_slug(monkeypatch):
    sets_rows = [
        {"id": "set-uuid-1", "name": "Prismatic Evolutions", "canonical_key": "prismaticEvolutions", "pokemon_api_set_id": "sv8pt5"}
    ]

    def read_sets(query):
        if query.eq_filters:
            field, value = query.eq_filters[-1]
            return [row for row in sets_rows if row.get(field) == value]
        return sets_rows

    payload_json = _insights_payload_json_fixture()
    client = _Client(
        {
            "sets": read_sets,
            "pokemon_set_page_snapshot_latest": lambda _q: [
                {"set_id": "set-uuid-1", "updated_at": "2026-06-30T00:00:00+00:00", "payload_json": payload_json}
            ],
        }
    )
    monkeypatch.setattr(pokemon_public_snapshot_service, "public_read_client", client)

    payload = pokemon_public_snapshot_service.get_pokemon_set_insights_snapshot_payload("prismatic-evolutions")

    assert payload["set"]["id"] == "set-uuid-1"
    assert payload["set"]["slug"] == "prismaticEvolutions"
    assert payload["summary"]["relativeProfitScore"] == 60.0


def test_insights_payload_missing_snapshot_returns_empty_fallback_with_warning(monkeypatch):
    client = _Client({"pokemon_set_page_snapshot_latest": lambda _q: []})
    monkeypatch.setattr(pokemon_public_snapshot_service, "public_read_client", client)

    payload = pokemon_public_snapshot_service.get_pokemon_set_insights_snapshot_payload(_TEST_UUID)

    assert payload["summary"] == {}
    assert payload["simulationDrivers"] == []
    assert payload["rarityContribution"] == []
    assert payload["outcomeDistribution"] == {"percentiles": [], "distributionBins": [], "thresholdBins": []}
    assert any("insights snapshot is missing" in w.lower() for w in payload["meta"]["warnings"])
    assert payload["meta"]["source"] == "empty_fallback_missing_pokemon_set_page_snapshot_latest"


def test_insights_payload_serialized_size_is_under_400kb(monkeypatch):
    import json

    payload_json = _insights_payload_json_fixture(top_hits_count=25, rankings_count=25, history_days=365)
    client = _Client(
        {
            "pokemon_set_page_snapshot_latest": lambda _q: [
                {"set_id": _TEST_UUID, "updated_at": "2026-06-30T00:00:00+00:00", "payload_json": payload_json}
            ],
        }
    )
    monkeypatch.setattr(pokemon_public_snapshot_service, "public_read_client", client)

    payload = pokemon_public_snapshot_service.get_pokemon_set_insights_snapshot_payload(_TEST_UUID)

    serialized_bytes = len(json.dumps(payload, default=str).encode("utf-8"))
    assert serialized_bytes < 400_000, f"insights payload was {serialized_bytes} bytes, over the 400KB budget"


def test_insights_payload_selectors_can_derive_rip_breakdown_drivers_and_trend_inputs(monkeypatch):
    """Structural proxy for the frontend selectors (selectRipScoreBreakdown/
    selectSimulationDrivers/selectDecisionSignals/selectTrendScores): asserts
    the exact fields those pure JS functions read are present with correct
    values, so the slim payload alone (no full /page fetch) is sufficient for
    them to derive the same output as before."""
    payload_json = _insights_payload_json_fixture()
    client = _Client(
        {
            "pokemon_set_page_snapshot_latest": lambda _q: [
                {"set_id": _TEST_UUID, "updated_at": "2026-06-30T00:00:00+00:00", "payload_json": payload_json}
            ],
        }
    )
    monkeypatch.setattr(pokemon_public_snapshot_service, "public_read_client", client)

    payload = pokemon_public_snapshot_service.get_pokemon_set_insights_snapshot_payload(_TEST_UUID)
    summary = payload["summary"]

    # selectRipScoreBreakdown reads relative_{pillar}_score/{pillar}_score,
    # {pillar}_rank, {pillar}_tier for profit/safety/desirability/stability.
    for pillar in ("profit", "safety", "desirability", "stability"):
        assert summary.get(f"relative{pillar.capitalize()}Score") is not None
        assert summary.get(f"{pillar}Rank") is not None
        assert summary.get(f"{pillar}Tier") is not None

    # selectTrendScores additionally reads pack_cost/mean_value/
    # average_hit_value/prob_profit/prob_big_hit/current_checklist_set_value.
    assert summary.get("packCost") == 4.99
    assert summary.get("meanValue") == 5.5
    assert summary.get("averageHitValue") == 12.3
    assert summary.get("probProfit") == 0.42
    assert summary.get("probBigHit") == 0.05
    assert summary.get("currentChecklistSetValue") == 123.45

    # selectSimulationDrivers reads top_hits/topHits rows with card_name/
    # cardName and ev_contribution/evContribution.
    assert len(payload["simulationDrivers"]) == 3
    assert payload["simulationDrivers"][0].get("cardName") == "Chase Card 0"
    assert payload["simulationDrivers"][0].get("evContribution") == 1.5

    # Decision Signals (Overview tab) ultimately reads its pillar rows from
    # the same RIP breakdown inputs above, via ripScoreBreakdown.rows — no
    # additional payload fields are required beyond `summary`.
# Movement generation diagnostics -------------------------------------------------


def test_movement_generation_metadata_reports_matching_cards_and_dashboard(monkeypatch):
    monkeypatch.setattr(
        pokemon_public_snapshot_service,
        "_read_peer_movement_snapshot_meta",
        lambda _set_id, *, surface: (
            {
                "generationId": "11111111-1111-4111-8111-111111111111",
                "movementContractVersion": "pokemon_card_movement_v1",
            },
            True,
        ),
    )

    result = pokemon_public_snapshot_service._movement_generation_metadata(
        _TEST_UUID,
        cards_snapshot={
            "generationId": "11111111-1111-4111-8111-111111111111",
            "movementContractVersion": "pokemon_card_movement_v1",
        },
    )

    assert result["matches"] is True
    assert result["status"] == "match"
    assert result["cardsGenerationId"] == result["marketDashboardGenerationId"]


def test_movement_generation_metadata_flags_new_cards_with_legacy_dashboard(monkeypatch):
    monkeypatch.setattr(
        pokemon_public_snapshot_service,
        "_read_peer_movement_snapshot_meta",
        lambda _set_id, *, surface: ({}, True),
    )

    result = pokemon_public_snapshot_service._movement_generation_metadata(
        _TEST_UUID,
        cards_snapshot={
            "generationId": "11111111-1111-4111-8111-111111111111",
            "movementContractVersion": "pokemon_card_movement_v1",
        },
    )

    assert result["matches"] is False
    assert result["status"] == "mixed_generation_and_legacy"
