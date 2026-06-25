from backend.scripts import pokemon_snapshot_builders


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

    def select(self, _fields):
        return self

    def eq(self, _field, _value):
        self.eq_filters.append((_field, _value))
        return self

    def in_(self, _field, _values):
        self.in_filters.append((_field, list(_values)))
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

    def order(self, _field, desc=False):
        return self

    def limit(self, _value):
        return self

    def execute(self):
        return _Result(self.handlers[self.table_name](self))


class _Client:
    def __init__(self, handlers):
        self.handlers = handlers

    def table(self, table_name):
        return _Query(table_name, self.handlers)


def _daily_top_chase_rows(count, *, start_date="2025-06-03", variant_id="variant-1", start_price=10.0):
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


def _raw_observation_rows(count, *, start_date="2025-06-03", variant_id="variant-1", start_price=10.0):
    from datetime import date, timedelta

    start = date.fromisoformat(start_date)
    return [
        {
            "captured_at": f"{(start + timedelta(days=index)).isoformat()}T12:00:00+00:00",
            "card_variant_id": variant_id,
            "condition_id": pokemon_snapshot_builders.TOP_CHASE_NEAR_MINT_CONDITION_ID,
            "market_price": start_price + index,
        }
        for index in range(count)
    ]


def test_build_cards_snapshot_row_includes_precomputed_card_validation(monkeypatch):
    monkeypatch.setattr(
        pokemon_snapshot_builders,
        "get_pokemon_set_cards_payload",
        lambda set_id: {
            "set": {"id": set_id, "name": "Snapshot Set"},
            "cards": [{"id": "card-1", "name": "Charizard ex", "marketPrice": 100.0}],
            "meta": {},
        },
    )
    monkeypatch.setattr(
        pokemon_snapshot_builders,
        "build_pokemon_set_card_movement_payload",
        lambda set_id: {"movements": [], "meta": {}},
    )

    def _enrich_with_validation(payload, **_kwargs):
        cards = [
            {
                **payload["cards"][0],
                "pokemonDesirabilityScore": 92.0,
                "adjustedCardAppealScore": 93.0,
                "isHitEligible": True,
            }
        ]
        return {
            **payload,
            "cards": cards,
            "cardDesirabilityValidation": {
                "cards": [
                    {
                        "cardId": "card-1",
                        "name": "Charizard ex",
                        "marketPrice": 100.0,
                        "pokemonDesirabilityScore": 92.0,
                        "adjustedCardAppealScore": 93.0,
                        "isHitEligible": True,
                    }
                ],
                "meta": {"scoringVersion": "card_appeal_v1"},
            },
        }

    monkeypatch.setattr(pokemon_snapshot_builders, "enrich_cards_payload_with_desirability", _enrich_with_validation)

    row = pokemon_snapshot_builders.build_cards_snapshot_row({"id": "set-1"})

    validation_rows = row["payload_json"]["cardDesirabilityValidation"]["cards"]
    assert row["card_count"] == 1
    assert validation_rows[0]["pokemonDesirabilityScore"] == 92.0
    assert validation_rows[0]["adjustedCardAppealScore"] == 93.0
    assert row["payload_json"]["cards"][0]["adjustedCardAppealScore"] == 93.0


def test_build_cards_snapshot_row_uses_canonical_price_index_for_card_appeal_correlation(monkeypatch):
    canonical_cards = [
        {
            "id": f"card-{index}",
            "name": f"Pokemon {index}",
            "number": str(index),
            "printed_number": str(index),
            "rarity": "Common",
            "pokemon_tcg_api_card_id": f"api-{index}",
        }
        for index in range(1, 259)
    ]
    legacy_cards = [
        {
            "id": f"legacy-{index}",
            "set_id": "set-1",
            "name": f"Pokemon {index}",
            "card_number": str(index),
            "pokemon_tcg_api_id": f"api-{index}",
        }
        for index in range(1, 259)
    ]
    variant_rows = [
        {
            "id": f"variant-{index}",
            "card_id": f"legacy-{index}",
            "pokemon_tcg_api_id": f"api-{index}",
        }
        for index in range(1, 259)
    ]
    latest_price_rows = [
        {
            "variant_id": f"variant-{index}",
            "condition_id": "condition-nm",
            "market_price": 1.0 + index,
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

    monkeypatch.setattr(
        pokemon_snapshot_builders,
        "get_pokemon_set_cards_payload",
        lambda set_id: {"set": {"id": set_id}, "cards": canonical_cards, "meta": {}},
    )
    monkeypatch.setattr(
        pokemon_snapshot_builders,
        "build_pokemon_set_card_movement_payload",
        lambda set_id: {"movements": [], "meta": {}},
    )
    monkeypatch.setattr(
        pokemon_snapshot_builders,
        "get_client",
        lambda: _Client(
            {
                "cards": lambda _query: legacy_cards,
                "card_variants": lambda _query: variant_rows,
                "conditions": lambda _query: [{"id": "condition-nm", "name": "Near Mint"}],
                "card_market_usd_latest_by_condition": lambda _query: latest_price_rows,
            }
        ),
    )

    from backend.db.services import pokemon_public_snapshot_service

    monkeypatch.setattr(
        pokemon_public_snapshot_service,
        "public_read_client",
        _Client(
            {
                "pokemon_card_desirability_links": lambda _query: links,
                "pokemon_desirability_composite_scores": lambda _query: scores,
            }
        ),
    )

    row = pokemon_snapshot_builders.build_cards_snapshot_row({"id": "set-1"})
    correlation = row["payload_json"]["cardAppealMarketPriceCorrelation"]

    assert correlation["canonical_count"] == 258
    assert correlation["priced_count"] == 258
    assert correlation["linked_count"] == 209
    assert correlation["included_count"] == 209
    assert correlation["excluded_unpriced_count"] == 0
    assert correlation["excluded_unlinked_count"] == 49
    assert correlation["n"] == 209
    assert correlation["n"] != 40
    assert correlation["sample_source"] == "canonical_checklist_cards"
    assert len(correlation["rows"]) == 209
    assert len(correlation["plotRows"]) == 258
    assert sum(1 for row in correlation["rows"] if row["isHitEligible"]) == 40
    assert sum(1 for row in correlation["plotRows"] if row["cardAppealScore"] is not None) == 209
    assert sum(1 for row in correlation["plotRows"] if row["treatmentScore"] is not None) == 258
    assert correlation["metricDiagnostics"]["cardAppeal"]["includedCount"] == 209
    assert correlation["metricDiagnostics"]["treatmentScore"]["includedCount"] == 258


def test_build_market_dashboard_snapshot_row_preserves_top_chase_price_history(monkeypatch):
    history = [
        {"date": "2026-06-01", "marketPrice": 10.0, "sourceDate": "2026-06-01", "isCarriedForward": False},
        {"date": "2026-06-02", "marketPrice": 12.0, "sourceDate": "2026-06-02", "isCarriedForward": False},
    ]
    monkeypatch.setattr(
        pokemon_snapshot_builders,
        "get_pokemon_set_value_history_payload",
        lambda set_id, days, value_scope: {
            "history": [{"date": "2026-06-02", "setValue": 100.0}],
            "meta": {"availableScopes": [{"key": value_scope, "label": value_scope}]},
        },
    )
    monkeypatch.setattr(
        pokemon_snapshot_builders,
        "get_pokemon_set_top_market_cards_payload",
        lambda set_id, limit, days: {
            "set": {"id": set_id, "name": "Snapshot Set"},
            "cards": [
                {
                    "cardId": "card-1",
                    "cardVariantId": "variant-1",
                    "name": "Chase Card",
                    "marketPrice": 12.0,
                    "priceHistory": history,
                    "price_history": history,
                    "conditionIdUsed": "condition-nm",
                    "deltas": {"30D": 20.0, "lifetime": 20.0},
                }
            ],
            "meta": {"warnings": []},
        },
    )
    monkeypatch.setattr(
        pokemon_snapshot_builders,
        "build_pokemon_set_card_movement_payload",
        lambda set_id: {"marketMovers": {}, "market_movers": {}},
    )

    dashboard_row, history_rows = pokemon_snapshot_builders.build_market_dashboard_snapshot_rows(
        {"id": "set-1", "name": "Snapshot Set"},
        days=365,
        window="365d",
        client=_Client({"card_variant_price_observations": lambda _query: []}),
    )

    payload = dashboard_row["payload_json"]
    card = payload["topChaseCards"][0]
    histories = payload["topChaseCardHistories"]
    expected_history = [
        {
            "date": "2026-06-01",
            "marketPrice": 10.0,
            "market_price": 10.0,
            "sourceDate": "2026-06-01",
            "source_date": "2026-06-01",
        },
        {
            "date": "2026-06-02",
            "marketPrice": 12.0,
            "market_price": 12.0,
            "sourceDate": "2026-06-02",
            "source_date": "2026-06-02",
        },
    ]

    assert "priceHistory" in card
    assert card["priceHistory"] == expected_history
    assert histories["variant-1"] == expected_history
    assert dashboard_row["top_chase_card_histories_json"]["variant-1"] == expected_history
    assert payload["meta"]["topChaseHistorySourceWindowDays"] == 365
    assert payload["meta"]["topChaseHistorySource"] == "card_variant_price_observations"
    assert payload["meta"]["topChaseHistoryMinPoints"] == 2
    assert payload["meta"]["topChaseHistoryMaxPoints"] == 2
    assert payload["meta"]["topChaseHistoryHydratedFromDailyTable"] is False
    assert history_rows[0]["card_variant_id"] == "variant-1"
    assert history_rows[0]["market_price"] == 10.0


def test_build_market_dashboard_snapshot_row_hydrates_top_chase_history_from_raw_observations(monkeypatch):
    history_queries = []

    monkeypatch.setattr(
        pokemon_snapshot_builders,
        "get_pokemon_set_value_history_payload",
        lambda set_id, days, value_scope: {
            "history": [{"date": "2026-06-02", "setValue": 100.0}],
            "meta": {"availableScopes": [{"key": value_scope, "label": value_scope}]},
        },
    )
    monkeypatch.setattr(
        pokemon_snapshot_builders,
        "get_pokemon_set_top_market_cards_payload",
        lambda set_id, limit, days: {
            "set": {"id": set_id, "name": "Snapshot Set"},
            "cards": [
                {
                    "cardId": "card-1",
                    "cardVariantId": "variant-1",
                    "name": "Chase Card",
                    "marketPrice": 12.0,
                    "imageUrl": "https://example.test/card.png",
                    "conditionIdUsed": "condition-nm",
                    "deltas": {"30D": None},
                }
            ],
            "meta": {"warnings": []},
        },
    )
    monkeypatch.setattr(
        pokemon_snapshot_builders,
        "build_pokemon_set_card_movement_payload",
        lambda set_id: {"marketMovers": {}, "market_movers": {}},
    )

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

    dashboard_row, history_rows = pokemon_snapshot_builders.build_market_dashboard_snapshot_rows(
        {"id": "set-1", "name": "Snapshot Set"},
        days=365,
        window="365d",
        client=_Client({"card_variant_price_observations": read_history}),
    )

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

    payload = dashboard_row["payload_json"]
    card = payload["topChaseCards"][0]
    assert payload["topChaseCardHistories"]["variant-1"] == expected_history
    assert payload["top_chase_card_histories"]["variant-1"] == expected_history
    assert card["priceHistory"] == expected_history
    assert card["price_history"] == expected_history
    assert card["marketPrice"] == 12.0
    assert card["imageUrl"] == "https://example.test/card.png"
    assert dashboard_row["top_chase_card_histories_json"]["variant-1"] == expected_history
    assert history_rows[0]["card_variant_id"] == "variant-1"
    assert history_rows[0]["market_price"] == 10.0
    assert ("card_variant_id", ["variant-1"]) in history_queries[0].in_filters
    assert ("condition_id", pokemon_snapshot_builders.TOP_CHASE_NEAR_MINT_CONDITION_ID) in history_queries[0].eq_filters
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


def test_build_market_dashboard_snapshot_row_uses_365d_top_chase_source_when_days_is_30(monkeypatch):
    history_queries = []
    top_card_days = []
    value_history_days = []

    def value_payload(set_id, days, value_scope):
        value_history_days.append(days)
        return {
            "history": [{"date": "2026-06-02", "setValue": 100.0}],
            "meta": {"availableScopes": [{"key": value_scope, "label": value_scope}]},
        }

    def top_payload(set_id, limit, days):
        top_card_days.append(days)
        return {
            "set": {"id": set_id, "name": "Snapshot Set"},
            "cards": [
                {
                    "cardId": "card-1",
                    "cardVariantId": "variant-1",
                    "name": "Chase Card",
                    "marketPrice": 374.0,
                }
            ],
            "meta": {"warnings": []},
        }

    monkeypatch.setattr(pokemon_snapshot_builders, "get_pokemon_set_value_history_payload", value_payload)
    monkeypatch.setattr(pokemon_snapshot_builders, "get_pokemon_set_top_market_cards_payload", top_payload)
    monkeypatch.setattr(
        pokemon_snapshot_builders,
        "build_pokemon_set_card_movement_payload",
        lambda set_id: {"marketMovers": {}, "market_movers": {}},
    )

    def read_history(query):
        history_queries.append(query)
        return _raw_observation_rows(365)

    dashboard_row, history_rows = pokemon_snapshot_builders.build_market_dashboard_snapshot_rows(
        {"id": "set-1", "name": "Snapshot Set"},
        days=30,
        window="365d",
        client=_Client({"card_variant_price_observations": read_history}),
    )

    payload = dashboard_row["payload_json"]

    assert set(value_history_days) == {30}
    assert top_card_days == [365]
    assert len(payload["topChaseCards"][0]["priceHistory"]) == 365
    assert len(history_rows) == 365
    assert ("captured_at", "2025-06-03") in history_queries[0].gte_filters
    assert ("captured_at", "2026-06-03") in history_queries[0].lt_filters
    assert payload["meta"]["topChaseHistorySourceWindowDays"] == 365


def test_build_set_page_snapshot_row_includes_desirability_validation(monkeypatch):
    monkeypatch.setattr(
        pokemon_snapshot_builders,
        "get_explore_page_payload",
        lambda target_type, set_id: {
            "set": {"id": set_id, "name": "Alpha"},
            "summary": {
                "desirability_score": 90,
                "pack_score": 80,
                "profit_score": 70,
                "safety_score": 60,
                "stability_score": 50,
                "mean_value": 5,
                "p95_value_to_cost_ratio": 2,
            },
            "top_hits": [{"marketPrice": 100}],
            "meta": {},
        },
    )
    monkeypatch.setattr(
        pokemon_snapshot_builders,
        "get_rip_statistics_targets_payload",
        lambda limit: {
            "targets": [
                {
                    "id": "set-1",
                    "target_id": "set-1",
                    "name": "Alpha",
                    "summary": {
                        "desirability_score": 90,
                        "pack_score": 80,
                        "profit_score": 70,
                        "safety_score": 60,
                        "stability_score": 50,
                        "mean_value": 5,
                        "p95_value_to_cost_ratio": 2,
                    },
                    "rip_score_without_desirability": 74.25,
                    "rip_score_with_desirability": 80.0,
                    "rip_score_delta": 5.75,
                    "rip_rank_without_desirability": 3,
                    "rip_rank_with_desirability": 1,
                    "rip_rank_delta": 2,
                    "desirability_component_score": 90.0,
                    "rip_desirability_impact_label": "Rank lift",
                    "rip_desirability_comparison_version": "rip_desirability_comparison_v1",
                    "top_hits": [{"marketPrice": 100}],
                },
                {
                    "id": "set-2",
                    "target_id": "set-2",
                    "name": "Beta",
                    "summary": {
                        "desirability_score": 50,
                        "pack_score": 70,
                        "profit_score": 80,
                        "safety_score": 70,
                        "stability_score": 60,
                        "mean_value": 4,
                        "p95_value_to_cost_ratio": 1.5,
                    },
                    "top_hits": [{"marketPrice": 25}],
                },
            ]
        },
    )

    row = pokemon_snapshot_builders.build_set_page_snapshot_row({"id": "set-1", "name": "Alpha"})

    comparison_fields = {
        "rip_score_without_desirability": 74.25,
        "rip_score_with_desirability": 80.0,
        "rip_score_delta": 5.75,
        "rip_rank_without_desirability": 3,
        "rip_rank_with_desirability": 1,
        "rip_rank_delta": 2,
        "desirability_component_score": 90.0,
        "rip_desirability_impact_label": "Rank lift",
    }
    for key, expected in comparison_fields.items():
        assert row["payload_json"]["summary"][key] == expected
        assert row["payload_json"]["set"][key] == expected
        assert row["rip_summary_json"][key] == expected

    validation = row["payload_json"]["desirabilityValidation"]
    assert validation["formula_version"] == "desirability_validation_v1"
    assert validation["desirability_impact_band"] in {"lift", "drag", "neutral"}
    assert row["payload_json"]["desirability_validation"] == validation
