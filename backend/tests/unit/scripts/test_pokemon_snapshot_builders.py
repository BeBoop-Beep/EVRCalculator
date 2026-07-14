from backend.scripts import pokemon_snapshot_builders
from backend.scripts.set_value_scope_invariants import SetValueScopeInvariantError
import pytest


def _empty_movement_windows_payload():
    empty = {key: {} for key in ("1D", "7D", "30D")}
    return {
        "marketMoversByWindow": empty,
        "market_movers_by_window": dict(empty),
        "meta": {
            "observationQueryCount": 1,
            "observationRowsLoaded": 0,
            "selectedVariantCount": 0,
            "observationPageCount": 1,
            "windowsCalculated": 3,
        },
    }


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
        self.range_filter = None

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

    def range(self, start, end):
        self.range_filter = (start, end)
        return self

    def execute(self):
        return _Result(self.handlers[self.table_name](self))


class _Client:
    def __init__(self, handlers):
        self.handlers = handlers

    def table(self, table_name):
        return _Query(table_name, self.handlers)


class _RpcCall:
    def __init__(self, data):
        self.data = data

    def execute(self):
        return _Result(self.data)


def _stub_market_dashboard_dependencies(monkeypatch, histories_by_scope):
    monkeypatch.setattr(
        pokemon_snapshot_builders,
        "get_pokemon_set_value_history_payload",
        lambda set_id, days, value_scope: {
            "history": histories_by_scope[value_scope],
            "meta": {"availableScopes": [{"key": value_scope, "label": value_scope}]},
        },
    )
    monkeypatch.setattr(
        pokemon_snapshot_builders,
        "get_pokemon_set_top_market_cards_payload",
        lambda set_id, limit, days: {"set": {"id": set_id}, "cards": [], "meta": {"warnings": []}},
    )
    monkeypatch.setattr(
        pokemon_snapshot_builders,
        "build_pokemon_set_card_movements_by_window_payload",
        lambda set_id, **_kwargs: _empty_movement_windows_payload(),
    )
    monkeypatch.setattr(pokemon_snapshot_builders, "_load_simulation_performance_history", lambda *_args: [])


def test_market_dashboard_builder_rejects_corrupt_subset_history(monkeypatch):
    histories = {
        "standard": [{"date": "2026-06-16", "setValue": 1097.57}],
        "hits": [{"date": "2026-06-16", "setValue": 118137.48}],
        "top10": [{"date": "2026-06-16", "setValue": 941.79}],
    }
    _stub_market_dashboard_dependencies(monkeypatch, histories)

    with pytest.raises(SetValueScopeInvariantError) as exc_info:
        pokemon_snapshot_builders.build_market_dashboard_snapshot_rows(
            {"id": "chaos", "name": "Chaos Rising"},
            client=_Client({"card_variant_price_observations": lambda _query: []}),
        )

    assert exc_info.value.details["scope"] == "hits"
    assert exc_info.value.details["date"] == "2026-06-16"


def test_market_dashboard_builder_emits_repaired_hits_in_all_history_contracts(monkeypatch):
    histories = {
        "standard": [{"date": "2026-06-16", "setValue": 1097.57}],
        "hits": [{"date": "2026-06-16", "setValue": 968.34}],
        "top10": [{"date": "2026-06-16", "setValue": 941.79}],
    }
    _stub_market_dashboard_dependencies(monkeypatch, histories)

    dashboard_row, _ = pokemon_snapshot_builders.build_market_dashboard_snapshot_rows(
        {"id": "chaos", "name": "Chaos Rising"},
        client=_Client({"card_variant_price_observations": lambda _query: []}),
    )

    assert dashboard_row["set_value_histories_json"]["hits"][0]["setValue"] == 968.34
    assert dashboard_row["payload_json"]["setValueHistoriesByScope"]["hits"][0]["setValue"] == 968.34
    assert dashboard_row["payload_json"]["set_value_histories_by_scope"]["hits"][0]["setValue"] == 968.34


def test_refresh_canonical_card_market_prices_for_set_calls_authoritative_rpc():
    calls = []

    class _RpcClient:
        def rpc(self, name, params):
            calls.append((name, params))
            return _RpcCall(124)

    refreshed = pokemon_snapshot_builders.refresh_canonical_card_market_prices_for_set(
        _RpcClient(),
        "set-1",
        commit=True,
    )

    assert refreshed == 124
    assert calls == [
        (
            "refresh_pokemon_canonical_card_market_prices_latest_for_set",
            {"target_set_id": "set-1"},
        )
    ]


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
        "build_pokemon_set_card_movements_by_window_payload",
        lambda set_id, **_kwargs: {"movements": [], "meta": {}},
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
    monkeypatch.setattr(
        pokemon_snapshot_builders,
        "_build_card_appeal_price_index_for_set",
        lambda **_kwargs: {},
    )

    row = pokemon_snapshot_builders.build_cards_snapshot_row(
        {"id": "set-1"},
        client=object(),
        generation_id="11111111-1111-4111-8111-111111111111",
        built_at="2026-07-13T23:59:00+00:00",
    )

    validation_rows = row["payload_json"]["cardDesirabilityValidation"]["cards"]
    assert row["card_count"] == 1
    assert validation_rows[0]["pokemonDesirabilityScore"] == 92.0
    assert validation_rows[0]["adjustedCardAppealScore"] == 93.0
    assert row["payload_json"]["cards"][0]["adjustedCardAppealScore"] == 93.0
    snapshot_meta = row["payload_json"]["meta"]["snapshot"]
    assert snapshot_meta == {
        "type": "pokemon_set_cards",
        "builtAt": "2026-07-13T23:59:00+00:00",
        "source": "pokemon_snapshot_builders",
        "movementContractVersion": "pokemon_card_movement_v1",
        "windowConvention": "inclusive_calendar_dates_v1",
        "movementAsOfDate": None,
        "generationId": "11111111-1111-4111-8111-111111111111",
    }
    assert row["cards_json"][0]["movementMetadata"]["generationId"] == snapshot_meta["generationId"]


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
            "canonical_card_id": f"card-{index}",
            "card_variant_id": f"variant-{index}",
            "condition_id": "condition-nm",
            "market_price": 1.0 + index,
            "captured_at": "2026-07-12",
            "source": "tcgplayer",
            "price_selection_reason": "selected_near_mint",
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
        "build_pokemon_set_card_movements_by_window_payload",
        lambda set_id, **_kwargs: {"movements": [], "meta": {}},
    )
    monkeypatch.setattr(
        pokemon_snapshot_builders,
        "get_client",
        lambda: _Client(
            {
                "pokemon_canonical_card_market_prices_latest": lambda _query: latest_price_rows,
                "card_variant_price_observations": lambda _query: [],
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


def test_query_paginated_rows_reads_past_supabase_1000_row_cap():
    source_rows = [{"id": index} for index in range(2505)]

    def _handler(query):
        start, end = query.range_filter
        return source_rows[start : end + 1]

    rows = pokemon_snapshot_builders._query_paginated_rows(
        _Client({"observations": _handler}),
        "observations",
        lambda query: query.select("id").order("id"),
    )

    assert len(rows) == 2505
    assert rows[0]["id"] == 0
    assert rows[-1]["id"] == 2504


def test_authoritative_card_enrichment_keeps_all_cards_and_uses_boundary_carry_forward():
    payload = {
        "cards": [{"id": "card-1"}, {"id": "card-2"}, {"id": "card-unpriced"}],
        "meta": {},
    }
    prices = {
        "card-1": {
            "market_price": 12.0,
            "variant_id": "variant-1",
            "condition_id": "condition-nm",
            "captured_at": "2026-07-12",
            "source": "tcgplayer",
            "price_selection_reason": "selected_near_mint",
        },
        "card-2": {
            "market_price": 5.0,
            "variant_id": "variant-2",
            "condition_id": "condition-nm",
            "captured_at": "2026-07-11",
            "source": "tcgplayer",
            "price_selection_reason": "selected_near_mint",
        },
    }
    observations = [
        {"card_variant_id": "variant-1", "condition_id": "condition-nm", "market_price": 10.0, "captured_at": "2026-07-05", "source": "tcgplayer"},
        {"card_variant_id": "variant-1", "condition_id": "condition-nm", "market_price": 12.0, "captured_at": "2026-07-12", "source": "tcgplayer"},
        {"card_variant_id": "variant-2", "condition_id": "condition-nm", "market_price": 4.0, "captured_at": "2026-07-04", "source": "tcgplayer"},
        {"card_variant_id": "variant-2", "condition_id": "condition-nm", "market_price": 5.0, "captured_at": "2026-07-11", "source": "tcgplayer"},
    ]
    client = _Client({"card_variant_price_observations": lambda _query: observations})

    enriched = pokemon_snapshot_builders._enrich_cards_with_authoritative_prices_and_movements(
        payload,
        set_id="set-1",
        prices_by_card=prices,
        client=client,
    )

    assert len(enriched["cards"]) == 3
    first, carried, unavailable = enriched["cards"]
    assert first["marketPrice"] == 12.0
    assert first["movement7d"]["startDate"] == "2026-07-05"
    assert first["movement7d"]["endDate"] == "2026-07-12"
    assert first["movement7d"]["startingPrice"] == 10.0
    assert first["change7dAmount"] == 2.0
    assert first["change7dPercent"] == 20.0
    assert first["movement30d"]["isPartialWindow"] is True
    assert first["movement30d"]["fullWindowCoverage"] is False
    assert first["movement30d"]["windowCoverageDays"] == 7
    assert first["movement30d"]["requestedWindowDays"] == 30
    assert first["movement30d"]["reliability"] == "partial_window"
    assert first["movement_30d"]["is_partial_window"] is True
    assert first["movement_30d"]["window_coverage_days"] == 7
    assert carried["marketPrice"] == 5.0
    assert carried["priceSourceDate"] == "2026-07-11"
    assert carried["priceCarriedForward"] is True
    assert carried["movement7d"]["endDate"] == "2026-07-12"
    assert carried["movement7d"]["endSourceDate"] == "2026-07-11"
    assert unavailable.get("marketPrice") is None


def test_movement_contract_prefers_full_boundary_then_falls_back_to_partial_history():
    price = {"market_price": 12.0, "captured_at": "2026-07-12", "source": "tcgplayer"}
    full = pokemon_snapshot_builders._movement_contract(
        price=price,
        observations=[
            {"market_price": 10.0, "source_date": "2026-06-10", "source": "tcgplayer"},
            {"market_price": 11.0, "source_date": "2026-06-25", "source": "tcgplayer"},
            {"market_price": 12.0, "source_date": "2026-07-12", "source": "tcgplayer"},
        ],
        latest_market_date="2026-07-12",
        window_days=30,
    )
    partial = pokemon_snapshot_builders._movement_contract(
        price=price,
        observations=[
            {"market_price": 11.0, "source_date": "2026-06-25", "source": "tcgplayer"},
            {"market_price": 12.0, "source_date": "2026-07-12", "source": "tcgplayer"},
        ],
        latest_market_date="2026-07-12",
        window_days=30,
    )

    assert full["startingPrice"] == 10.0
    assert full["fullWindowCoverage"] is True
    assert full["isPartialWindow"] is False
    assert full["reliability"] == "reliable"
    assert partial["startingPrice"] == 11.0
    assert partial["changeAmount"] == 1.0
    assert partial["changePercent"] == 9.09
    assert partial["fullWindowCoverage"] is False
    assert partial["isPartialWindow"] is True
    assert partial["windowCoverageDays"] == 17
    assert partial["requestedWindowDays"] == 30
    assert partial["enoughHistory"] is False
    assert partial["reliable"] is False
    assert partial["reliability"] == "partial_window"


def test_movement_contract_reliability_reasons_are_specific():
    guardrailed = pokemon_snapshot_builders._movement_contract(
        price={"market_price": 10.1, "captured_at": "2026-07-12"},
        observations=[
            {"market_price": 10.0, "source_date": "2026-06-12"},
            {"market_price": 10.1, "source_date": "2026-07-12"},
        ],
        latest_market_date="2026-07-12",
        window_days=30,
    )
    insufficient = pokemon_snapshot_builders._movement_contract(
        price={"market_price": 10.0, "captured_at": "2026-07-12"},
        observations=[
            {"market_price": 8.0, "source_date": "2026-07-01"},
            {"market_price": 10.0, "source_date": "2026-07-12"},
        ],
        latest_market_date="2026-07-12",
        window_days=7,
    )
    unavailable = pokemon_snapshot_builders._movement_contract(
        price={"market_price": None, "captured_at": "2026-07-12"},
        observations=[],
        latest_market_date="2026-07-12",
        window_days=30,
    )

    assert guardrailed["reliability"] == "guardrailed"
    assert guardrailed["changeAmount"] == 0.1
    assert guardrailed["changePercent"] == 1.0
    assert guardrailed["reliable"] is False
    assert insufficient["reliability"] == "insufficient_history"
    assert unavailable["reliability"] == "unavailable"


def test_movement_contract_does_not_invent_delta_from_one_observation():
    movement = pokemon_snapshot_builders._movement_contract(
        price={"market_price": 10.0, "captured_at": "2026-07-12"},
        observations=[{"market_price": 10.0, "source_date": "2026-07-12"}],
        latest_market_date="2026-07-12",
        window_days=30,
    )

    assert movement["changeAmount"] is None
    assert movement["changePercent"] is None
    assert movement["isPartialWindow"] is False
    assert movement["reliable"] is False
    assert movement["reliability"] == "unavailable"


@pytest.mark.parametrize("set_key", ["journeyTogether", "chaosRising"])
def test_recent_set_partial_history_fixture_produces_display_delta(set_key):
    movement = pokemon_snapshot_builders._movement_contract(
        price={"market_price": 12.0, "captured_at": "2026-07-12", "source": set_key},
        observations=[
            {"market_price": 9.0, "source_date": "2026-06-27", "source": set_key},
            {"market_price": 12.0, "source_date": "2026-07-12", "source": set_key},
        ],
        latest_market_date="2026-07-12",
        window_days=30,
    )

    assert movement["changeAmount"] == 3.0
    assert movement["changePercent"] == 33.33
    assert movement["windowCoverageDays"] == 15
    assert movement["isPartialWindow"] is True
    assert movement["reliable"] is False


def test_pricing_contract_diagnostics_are_computed_from_final_cards():
    payload = pokemon_snapshot_builders._with_cards_pricing_contract_diagnostics(
        {
            "cards": [
                {
                    "marketPrice": 12.0,
                    "change7dAmount": 1.0,
                    "change30dAmount": 2.0,
                    "movement7d": {"fullWindowCoverage": True},
                    "movement30d": {"isPartialWindow": True},
                },
                {"marketPrice": 8.0, "movement7d": {}, "movement30d": {}},
                {"marketPrice": None},
            ],
            "meta": {"pricingContract": {"source": "test"}},
        }
    )
    contract = payload["meta"]["pricingContract"]
    assert contract == {
        "source": "test",
        "canonicalCardCount": 3,
        "pricedCardCount": 2,
        "cardsWith7dDelta": 1,
        "cardsWith30dDelta": 1,
        "cardsWithFull7dCoverage": 1,
        "cardsWithFull30dCoverage": 0,
        "cardsWithPartial7dDelta": 0,
        "cardsWithPartial30dDelta": 1,
        "cardsMissingUsableHistory": 1,
    }


def test_forward_fill_top_chase_history_is_idempotent_and_preserves_source_date():
    history = [
        {"date": "2026-07-10", "marketPrice": 20.0, "sourceDate": "2026-07-10"},
        {"date": "2026-07-11", "marketPrice": 22.0, "sourceDate": "2026-07-11"},
    ]
    first = pokemon_snapshot_builders._forward_fill_history_through_date(history, end_date_key="2026-07-12")
    second = pokemon_snapshot_builders._forward_fill_history_through_date(first, end_date_key="2026-07-12")

    assert first == second
    assert [point["date"] for point in first] == ["2026-07-10", "2026-07-11", "2026-07-12"]
    assert first[-1]["marketPrice"] == 22.0
    assert first[-1]["sourceDate"] == "2026-07-11"
    assert first[-1]["isCarriedForward"] is True


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
        "build_pokemon_set_card_movements_by_window_payload",
        lambda set_id, **_kwargs: _empty_movement_windows_payload(),
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
                "isObserved": True,
                "is_observed": True,
                "isCarriedForward": False,
                "is_carried_forward": False,
            },
        {
            "date": "2026-06-02",
            "marketPrice": 12.0,
            "market_price": 12.0,
                "sourceDate": "2026-06-02",
                "source_date": "2026-06-02",
                "isObserved": True,
                "is_observed": True,
                "isCarriedForward": False,
                "is_carried_forward": False,
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
    assert payload["meta"]["topChaseCardCount"] == 1
    assert payload["meta"]["topChaseMovementCountByWindow"] == {"1D": 0, "7D": 0, "30D": 0}
    assert payload["meta"]["topChaseMissingCanonicalIdentityCount"] == 1
    assert payload["meta"]["topChaseMissingSelectedVariantCount"] == 0
    assert payload["meta"]["topChasePartialCardCount"] == 0
    assert payload["meta"]["topChaseCardsWith1dMovement"] == 0
    assert payload["meta"]["topChaseCardsWith7dMovement"] == 0
    assert payload["meta"]["topChaseCardsWith30dMovement"] == 0
    assert payload["meta"]["topChaseCardsMissingCanonicalIdentity"] == 1
    assert payload["meta"]["topChaseCardsMissingSelectedVariant"] == 0
    assert payload["meta"]["topChaseCardsUsingPartialWindow"] == 0
    assert any("priced cards but no usable" in warning for warning in payload["meta"]["warnings"])
    assert history_rows[0]["card_variant_id"] == "variant-1"
    assert history_rows[0]["market_price"] == 10.0


def test_build_market_dashboard_snapshot_row_builds_market_movers_for_1d_7d_30d(monkeypatch):
    """marketMoversByWindow must hold distinct 1D/7D/30D payloads; marketMovers stays the 30D compat field."""
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
        lambda set_id, limit, days: {"set": {"id": set_id}, "cards": [], "meta": {"warnings": []}},
    )

    movement_calls = []

    def fake_movement_payload(*, set_id, window_days=(1, 7, 30), limit=5, client=None, **_kwargs):
        movement_calls.append(tuple(window_days))
        camel = {
            f"{days}D": {
                "window": f"{days}D",
                "windowDays": days,
                "heatingUp": [{"cardId": f"card-{days}"}],
                "heating_up": [{"cardId": f"card-{days}"}],
                "coolingOff": [],
                "cooling_off": [],
                "all": [{"cardId": f"card-{days}"}],
            }
            for days in window_days
        }
        snake = {
            f"{days}D": {
                "window": f"{days}D",
                "window_days": days,
                "heating_up": [{"cardId": f"card-{days}"}],
                "cooling_off": [],
                "all": [{"cardId": f"card-{days}"}],
            }
            for days in window_days
        }
        return {
            "marketMoversByWindow": camel,
            "market_movers_by_window": snake,
            "meta": {
                "observationQueryCount": 1,
                "observationRowsLoaded": 5,
                "selectedVariantCount": 5,
                "observationPageCount": 1,
                "windowsCalculated": 3,
            },
        }

    monkeypatch.setattr(
        pokemon_snapshot_builders,
        "build_pokemon_set_card_movements_by_window_payload",
        fake_movement_payload,
    )

    dashboard_row, _history_rows = pokemon_snapshot_builders.build_market_dashboard_snapshot_rows(
        {"id": "set-1", "name": "Snapshot Set"},
        days=365,
        window="365d",
        client=_Client({"card_variant_price_observations": lambda _query: []}),
    )

    assert movement_calls == [(1, 7, 30)]

    payload = dashboard_row["payload_json"]
    dashboard_snapshot = payload["meta"]["snapshot"]
    assert dashboard_snapshot["movementContractVersion"] == "pokemon_card_movement_v1"
    assert dashboard_snapshot["windowConvention"] == "inclusive_calendar_dates_v1"
    assert dashboard_snapshot["movementAsOfDate"] == "2026-06-02"
    assert dashboard_snapshot["generationId"]
    assert dashboard_snapshot["builtAt"]
    by_window = payload["marketMoversByWindow"]
    by_window_snake = payload["market_movers_by_window"]
    assert set(by_window.keys()) == {"1D", "7D", "30D"}
    assert set(by_window_snake.keys()) == {"1D", "7D", "30D"}
    assert by_window["1D"]["heatingUp"][0]["cardId"] == "card-1"
    assert by_window["7D"]["heatingUp"][0]["cardId"] == "card-7"
    assert by_window["30D"]["heatingUp"][0]["cardId"] == "card-30"
    assert by_window_snake["1D"]["heating_up"][0]["cardId"] == "card-1"

    # Backward compatibility: marketMovers/market_movers must still be the 30D entry.
    assert payload["marketMovers"] == by_window["30D"]
    assert payload["market_movers"] == by_window_snake["30D"]
    assert payload["meta"]["movementQueryDiagnostics"]["windowsCalculated"] == 3


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
        "build_pokemon_set_card_movements_by_window_payload",
        lambda set_id, **_kwargs: _empty_movement_windows_payload(),
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
                "isCarriedForward": False,
                "is_carried_forward": False,
            },
        {
            "date": "2026-06-02",
            "marketPrice": 12.0,
            "market_price": 12.0,
            "sourceDate": "2026-06-02",
            "source_date": "2026-06-02",
                "isObserved": True,
                "is_observed": True,
                "isCarriedForward": False,
                "is_carried_forward": False,
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
        "build_pokemon_set_card_movements_by_window_payload",
        lambda set_id, **_kwargs: _empty_movement_windows_payload(),
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


def test_build_market_dashboard_snapshot_row_writes_set_value_freshness_metadata(monkeypatch):
    histories = {
        "standard": [
            {"date": "2026-06-20", "setValue": 1000.0},
            {"date": "2026-06-24", "setValue": 1040.0},
        ],
        "hits": [
            {"date": "2026-06-20", "setValue": 700.0},
            {"date": "2026-06-24", "setValue": 734.52},
        ],
        "top10": [
            {"date": "2026-06-23", "setValue": 500.0},
        ],
    }

    monkeypatch.setattr(
        pokemon_snapshot_builders,
        "get_pokemon_set_value_history_payload",
        lambda set_id, days, value_scope: {
            "history": histories[value_scope],
            "meta": {"availableScopes": [{"key": value_scope, "label": value_scope}]},
        },
    )
    monkeypatch.setattr(
        pokemon_snapshot_builders,
        "get_pokemon_set_top_market_cards_payload",
        lambda set_id, limit, days: {
            "set": {"id": set_id, "name": "Snapshot Set"},
            "cards": [],
            "meta": {"warnings": []},
        },
    )
    monkeypatch.setattr(
        pokemon_snapshot_builders,
        "build_pokemon_set_card_movements_by_window_payload",
        lambda set_id, **_kwargs: _empty_movement_windows_payload(),
    )

    dashboard_row, _history_rows = pokemon_snapshot_builders.build_market_dashboard_snapshot_rows(
        {"id": "set-1", "name": "Snapshot Set"},
        days=365,
        window="365d",
        client=_Client({"card_variant_price_observations": lambda _query: []}),
    )

    payload = dashboard_row["payload_json"]
    meta = payload["meta"]
    assert dashboard_row["latest_market_date"] == "2026-06-24"
    assert payload["latestMarketDate"] == "2026-06-24"
    assert meta["latestSetValueHistoryDate"] == "2026-06-24"
    assert meta["setValueHistoryLatestDateByScope"] == {
        "standard": "2026-06-24",
        "hits": "2026-06-24",
        "top10": "2026-06-23",
    }
    assert meta["setValueHistoryPointCountByScope"] == {
        "standard": 2,
        "hits": 2,
        "top10": 1,
    }


def test_market_dashboard_snapshot_uses_corrected_local_set_value_history_date(monkeypatch):
    histories = {
        "standard": [{"date": "2026-06-26", "setValue": 701.77}],
        "hits": [{"date": "2026-06-26", "setValue": 512.34}],
        "top10": [{"date": "2026-06-26", "setValue": 400.12}],
    }

    monkeypatch.setattr(
        pokemon_snapshot_builders,
        "get_pokemon_set_value_history_payload",
        lambda set_id, days, value_scope: {
            "history": histories[value_scope],
            "meta": {"availableScopes": [{"key": value_scope, "label": value_scope}]},
        },
    )
    monkeypatch.setattr(
        pokemon_snapshot_builders,
        "get_pokemon_set_top_market_cards_payload",
        lambda set_id, limit, days: {
            "set": {"id": set_id, "name": "Chaos Rising"},
            "cards": [],
            "meta": {"warnings": []},
        },
    )
    monkeypatch.setattr(
        pokemon_snapshot_builders,
        "build_pokemon_set_card_movements_by_window_payload",
        lambda set_id, **_kwargs: _empty_movement_windows_payload(),
    )

    dashboard_row, _history_rows = pokemon_snapshot_builders.build_market_dashboard_snapshot_rows(
        {"id": "set-1", "name": "Chaos Rising"},
        days=365,
        window="365d",
        client=_Client({"card_variant_price_observations": lambda _query: []}),
    )

    assert dashboard_row["latest_market_date"] == "2026-06-26"
    assert dashboard_row["set_value_histories_json"]["standard"][0]["date"] == "2026-06-26"
    assert dashboard_row["payload_json"]["latestMarketDate"] == "2026-06-26"
    assert dashboard_row["payload_json"]["setValueHistoriesByScope"]["hits"][0]["date"] == "2026-06-26"


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
    assert validation["formula_version"] == "desirability_validation_v2"
    assert validation["desirability_impact_band"] in {"lift", "drag", "neutral"}
    assert row["payload_json"]["desirability_validation"] == validation


def test_build_set_page_snapshot_row_merges_decision_signal_ranks_from_rankings(monkeypatch):
    monkeypatch.setattr(
        pokemon_snapshot_builders,
        "get_explore_page_payload",
        lambda target_type, set_id: {
            "set": {"id": set_id, "name": "Alpha"},
            "summary": {
                "pack_score": 80,
                "profit_score": 70,
                "safety_score": 60,
                "desirability_score": 90,
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
                    "profit_rank": 4,
                    "profit_tier": "A",
                    "safety_rank": 6,
                    "safety_tier": "B",
                    "desirability_rank": 2,
                    "desirability_tier": "A",
                    "stability_rank": 9,
                    "stability_tier": "C",
                }
            ]
        },
    )

    row = pokemon_snapshot_builders.build_set_page_snapshot_row({"id": "set-1", "name": "Alpha"})
    summary = row["payload_json"]["summary"]

    assert summary["profit_rank"] == 4
    assert summary["safety_rank"] == 6
    assert summary["desirability_rank"] == 2
    assert summary["stability_rank"] == 9
    assert row["rip_summary_json"]["profit_rank"] == 4


def test_build_set_page_snapshot_row_repairs_missing_top_hits_from_simulation_inputs(monkeypatch):
    monkeypatch.setattr(
        pokemon_snapshot_builders,
        "get_explore_page_payload",
        lambda target_type, set_id: {
            "set": {"id": set_id, "name": "Alpha"},
            "summary": {
                "calculation_run_id": "run-1",
                "desirability_score": 90,
                "pack_score": 80,
                "profit_score": 70,
                "safety_score": 60,
                "stability_score": 50,
                "mean_value": 5,
                "p95_value_to_cost_ratio": 2,
            },
            "top_hits": [],
            "meta": {
                "sources": {"simulation_input_cards": "FAILED"},
                "warnings": ["Failed to load top hits"],
            },
        },
    )
    monkeypatch.setattr(
        pokemon_snapshot_builders,
        "get_rip_statistics_targets_payload",
        lambda limit: {"targets": []},
    )

    client = _Client(
        {
            "simulation_input_cards_with_near_mint_price": lambda _query: [
                {
                    "card_id": "card-1",
                    "card_variant_id": "variant-1",
                    "card_name": "Chase",
                    "rarity_bucket": "hits",
                    "ev_contribution": 1.25,
                    "current_near_mint_price": 100.0,
                }
            ],
            "card_variants": lambda _query: [
                {
                    "id": "variant-1",
                    "card_id": "card-1",
                    "image_small_url": "https://img.example/small.png",
                    "image_large_url": "https://img.example/large.png",
                }
            ],
            "cards": lambda _query: [],
        }
    )

    row = pokemon_snapshot_builders.build_set_page_snapshot_row(
        {"id": "set-1", "name": "Alpha"},
        client=client,
    )

    payload = row["payload_json"]
    assert payload["top_hits"] == [
        {
            "card_id": "card-1",
            "card_variant_id": "variant-1",
            "card_name": "Chase",
            "rarity_bucket": "hits",
            "ev_contribution": 1.25,
            "current_near_mint_price": 100.0,
            "image_url": "https://img.example/small.png",
            "image_small_url": "https://img.example/small.png",
            "image_large_url": "https://img.example/large.png",
        }
    ]
    assert payload["meta"]["sources"]["simulation_input_cards"] == "OK"
    assert (
        payload["meta"]["sources"]["simulation_input_cards_snapshot_completion"]
        == "simulation_input_cards_with_near_mint_price"
    )
    assert payload["meta"]["warnings"] == []


def test_build_set_page_snapshot_row_preserves_top_hit_warning_when_rows_unavailable(monkeypatch):
    monkeypatch.setattr(
        pokemon_snapshot_builders,
        "get_explore_page_payload",
        lambda target_type, set_id: {
            "summary": {"calculation_run_id": "run-1", "pack_score": 80, "mean_value": 5},
            "top_hits": [],
            "meta": {
                "sources": {"simulation_input_cards": "FAILED"},
                "warnings": ["Failed to load top hits"],
            },
        },
    )
    monkeypatch.setattr(pokemon_snapshot_builders, "get_rip_statistics_targets_payload", lambda limit: {"targets": []})

    client = _Client(
        {
            "simulation_input_cards_with_near_mint_price": lambda _query: [],
            "simulation_input_cards": lambda _query: [],
            "pokemon_set_cards_snapshot_latest": lambda _query: [],
            "pokemon_explore_rankings_snapshot_latest": lambda _query: [],
            "explore_rip_statistics_latest": lambda _query: [],
            "simulation_latest_by_target": lambda _query: [],
        }
    )

    row = pokemon_snapshot_builders.build_set_page_snapshot_row({"id": "set-1", "name": "Alpha"}, client=client)

    assert row["payload_json"]["top_hits"] == []
    assert "Failed to load top hits" in row["payload_json"]["meta"]["warnings"]
    assert row["payload_json"]["meta"]["sources"]["simulation_input_cards"] == "FAILED"
    assert row["payload_json"]["meta"]["sectionFreshness"]["simulationDrivers"]["status"] == "missing"


def test_build_set_page_snapshot_row_preserves_previous_top_hits_when_current_build_failed(monkeypatch):
    monkeypatch.setattr(pokemon_snapshot_builders, "utc_now_iso", lambda: "2026-06-25T12:00:00+00:00")
    monkeypatch.setattr(
        pokemon_snapshot_builders,
        "get_explore_page_payload",
        lambda target_type, set_id: {
            "summary": {"calculation_run_id": "run-2", "pack_score": 80, "mean_value": 5},
            "top_hits": [],
            "meta": {
                "sources": {"simulation_input_cards": "FAILED"},
                "warnings": ["Simulation Drivers unavailable: simulation_input_cards FAILED"],
            },
        },
    )
    monkeypatch.setattr(pokemon_snapshot_builders, "get_rip_statistics_targets_payload", lambda limit: {"targets": []})

    previous_top_hits = [{"card_name": "Previous Chase", "ev_contribution": 1.2}]
    client = _Client(
        {
            "simulation_input_cards_with_near_mint_price": lambda _query: [],
            "simulation_input_cards": lambda _query: [],
            "pokemon_set_cards_snapshot_latest": lambda _query: [],
            "pokemon_explore_rankings_snapshot_latest": lambda _query: [],
            "explore_rip_statistics_latest": lambda _query: [],
            "simulation_latest_by_target": lambda _query: [],
            "pokemon_set_page_snapshot_latest": lambda _query: [
                {
                    "payload_json": {
                        "summary": {"calculation_run_id": "run-1", "run_at": "2026-06-24T11:00:00+00:00"},
                        "top_hits": previous_top_hits,
                        "meta": {
                            "snapshot": {"builtAt": "2026-06-24T12:00:00+00:00"},
                            "sectionFreshness": {
                                "simulationDrivers": {
                                    "status": "fresh",
                                    "dataAsOf": "2026-06-24T11:00:00+00:00",
                                    "lastSuccessfulAt": "2026-06-24T12:00:00+00:00",
                                    "attemptedAt": "2026-06-24T12:00:00+00:00",
                                    "source": "simulation_input_cards_with_near_mint_price/run-1",
                                }
                            },
                        },
                    },
                    "updated_at": "2026-06-24T12:05:00+00:00",
                }
            ],
        }
    )

    row = pokemon_snapshot_builders.build_set_page_snapshot_row({"id": "set-1", "name": "Alpha"}, client=client)
    payload = row["payload_json"]
    freshness = payload["meta"]["sectionFreshness"]["simulationDrivers"]

    assert payload["top_hits"] == previous_top_hits
    assert freshness["status"] == "stale"
    assert freshness["dataAsOf"] == "2026-06-24T11:00:00+00:00"
    assert freshness["lastSuccessfulAt"] == "2026-06-24T12:00:00+00:00"
    assert freshness["attemptedAt"] == "2026-06-25T12:00:00+00:00"
    assert payload["meta"]["sectionFreshness"]["simulationDrivers"]["status"] != "missing"


def test_build_set_page_snapshot_row_preserves_previous_rank_fields_when_current_build_lacks_ranks(monkeypatch):
    monkeypatch.setattr(pokemon_snapshot_builders, "utc_now_iso", lambda: "2026-06-25T12:00:00+00:00")
    monkeypatch.setattr(
        pokemon_snapshot_builders,
        "get_explore_page_payload",
        lambda target_type, set_id: {
            "summary": {"calculation_run_id": "run-2", "pack_score": 80, "mean_value": 5},
            "top_hits": [{"card_name": "Chase", "ev_contribution": 1.2}],
            "meta": {"sources": {"simulation_input_cards": "OK"}, "warnings": []},
        },
    )
    monkeypatch.setattr(pokemon_snapshot_builders, "get_rip_statistics_targets_payload", lambda limit: {"targets": []})

    client = _Client(
        {
            "pokemon_set_cards_snapshot_latest": lambda _query: [],
            "pokemon_explore_rankings_snapshot_latest": lambda _query: [],
            "explore_rip_statistics_latest": lambda _query: [],
            "simulation_latest_by_target": lambda _query: [],
            "simulation_input_cards": lambda _query: [{"id": "sic-1"}],
            "simulation_input_cards_with_near_mint_price": lambda _query: [{"id": "sic-nm-1"}],
            "pokemon_set_page_snapshot_latest": lambda _query: [
                {
                    "payload_json": {
                        "summary": {
                            "calculation_run_id": "run-1",
                            "run_at": "2026-06-24T11:00:00+00:00",
                            "pack_rank": 7,
                            "pack_tier": "A",
                            "profit_rank": 12,
                            "profit_tier": "B",
                        },
                        "set": {"pack_rank": 7, "pack_tier": "A", "profit_rank": 12, "profit_tier": "B"},
                        "meta": {"snapshot": {"builtAt": "2026-06-24T12:00:00+00:00"}},
                    },
                    "updated_at": "2026-06-24T12:05:00+00:00",
                }
            ],
        }
    )

    row = pokemon_snapshot_builders.build_set_page_snapshot_row({"id": "set-1", "name": "Alpha"}, client=client)
    payload = row["payload_json"]

    assert payload["summary"]["pack_rank"] == 7
    assert payload["summary"]["pack_tier"] == "A"
    assert payload["summary"]["profit_rank"] == 12
    assert payload["summary"]["profit_tier"] == "B"
    assert payload["set"]["pack_rank"] == 7
    assert payload["meta"]["sectionFreshness"]["decisionSignalRanks"]["status"] == "stale"


def test_build_set_page_snapshot_row_preserves_previous_card_appeal_correlation_when_current_build_lacks_it(monkeypatch):
    monkeypatch.setattr(pokemon_snapshot_builders, "utc_now_iso", lambda: "2026-06-25T12:00:00+00:00")
    monkeypatch.setattr(
        pokemon_snapshot_builders,
        "get_explore_page_payload",
        lambda target_type, set_id: {
            "summary": {"calculation_run_id": "run-2", "pack_score": 80, "mean_value": 5},
            "top_hits": [{"card_name": "Chase", "ev_contribution": 1.2}],
            "meta": {"sources": {"simulation_input_cards": "OK"}, "warnings": []},
        },
    )
    monkeypatch.setattr(pokemon_snapshot_builders, "get_rip_statistics_targets_payload", lambda limit: {"targets": []})

    correlation = {"n": 12, "plotRows": [{"name": "Chase", "cardAppealScore": 91, "marketPrice": 25}]}
    client = _Client(
        {
            "pokemon_set_cards_snapshot_latest": lambda _query: [],
            "pokemon_explore_rankings_snapshot_latest": lambda _query: [],
            "explore_rip_statistics_latest": lambda _query: [],
            "simulation_latest_by_target": lambda _query: [],
            "simulation_input_cards": lambda _query: [{"id": "sic-1"}],
            "simulation_input_cards_with_near_mint_price": lambda _query: [{"id": "sic-nm-1"}],
            "pokemon_set_page_snapshot_latest": lambda _query: [
                {
                    "payload_json": {
                        "summary": {"calculation_run_id": "run-1", "run_at": "2026-06-24T11:00:00+00:00"},
                        "cardAppealMarketPriceCorrelation": correlation,
                        "card_appeal_market_price_correlation": correlation,
                        "meta": {"snapshot": {"builtAt": "2026-06-24T12:00:00+00:00"}},
                    },
                    "updated_at": "2026-06-24T12:05:00+00:00",
                }
            ],
        }
    )

    row = pokemon_snapshot_builders.build_set_page_snapshot_row({"id": "set-1", "name": "Alpha"}, client=client)
    payload = row["payload_json"]

    assert payload["cardAppealMarketPriceCorrelation"] == correlation
    assert payload["card_appeal_market_price_correlation"] == correlation
    assert payload["meta"]["sectionFreshness"]["cardAppealValidation"]["status"] == "stale"


def test_build_set_page_snapshot_row_marks_incomplete_previous_desirability_validation_missing(monkeypatch):
    monkeypatch.setattr(pokemon_snapshot_builders, "utc_now_iso", lambda: "2026-06-25T12:00:00+00:00")
    monkeypatch.setattr(
        pokemon_snapshot_builders,
        "get_explore_page_payload",
        lambda target_type, set_id: {
            "summary": {"calculation_run_id": "run-2", "pack_score": 80, "mean_value": 5},
            "top_hits": [{"card_name": "Chase", "ev_contribution": 1.2}],
            "meta": {"sources": {"simulation_input_cards": "OK"}, "warnings": []},
        },
    )
    monkeypatch.setattr(pokemon_snapshot_builders, "get_rip_statistics_targets_payload", lambda limit: {"targets": []})

    def _raise_validation_error(**_kwargs):
        raise RuntimeError("validation unavailable")

    monkeypatch.setattr(pokemon_snapshot_builders, "build_desirability_validation_payload", _raise_validation_error)

    validation = {"formula_version": "desirability_validation_v1", "summary": {"sampleCount": 12}}
    client = _Client(
        {
            "pokemon_set_cards_snapshot_latest": lambda _query: [],
            "pokemon_explore_rankings_snapshot_latest": lambda _query: [],
            "explore_rip_statistics_latest": lambda _query: [],
            "simulation_latest_by_target": lambda _query: [],
            "simulation_input_cards": lambda _query: [{"id": "sic-1"}],
            "simulation_input_cards_with_near_mint_price": lambda _query: [{"id": "sic-nm-1"}],
            "pokemon_set_page_snapshot_latest": lambda _query: [
                {
                    "payload_json": {
                        "summary": {"calculation_run_id": "run-1", "run_at": "2026-06-24T11:00:00+00:00"},
                        "desirabilityValidation": validation,
                        "desirability_validation": validation,
                        "meta": {"snapshot": {"builtAt": "2026-06-24T12:00:00+00:00"}},
                    },
                    "updated_at": "2026-06-24T12:05:00+00:00",
                }
            ],
        }
    )

    row = pokemon_snapshot_builders.build_set_page_snapshot_row({"id": "set-1", "name": "Alpha"}, client=client)
    payload = row["payload_json"]

    assert "desirabilityValidation" not in payload
    assert "desirability_validation" not in payload
    assert payload["meta"]["sectionFreshness"]["desirabilityValidation"]["status"] == "missing"


def test_build_set_page_snapshot_row_records_completeness_and_card_appeal_snapshot(monkeypatch):
    monkeypatch.setattr(pokemon_snapshot_builders, "utc_now_iso", lambda: "2026-06-25T12:00:00+00:00")
    monkeypatch.setattr(
        pokemon_snapshot_builders,
        "get_explore_page_payload",
        lambda target_type, set_id: {
            "summary": {"calculation_run_id": "run-1", "pack_score": 80, "mean_value": 5},
            "top_hits": [{"card_name": "Chase", "ev_contribution": 1.2}],
            "meta": {
                "sources": {"simulation_input_cards": "OK"},
                "warnings": ["explore_rip_statistics_latest unavailable; fell back to simulation_latest_by_target"],
            },
        },
    )
    monkeypatch.setattr(pokemon_snapshot_builders, "get_rip_statistics_targets_payload", lambda limit: {"targets": []})

    correlation = {"n": 12, "plotRows": [{"name": "Chase", "cardAppealScore": 91, "marketPrice": 25}]}
    client = _Client(
        {
            "pokemon_set_cards_snapshot_latest": lambda _query: [
                {"payload_json": {"cardAppealMarketPriceCorrelation": correlation}}
            ],
            "pokemon_explore_rankings_snapshot_latest": lambda _query: [
                {"updated_at": "2026-06-22T12:00:00+00:00"}
            ],
            "explore_rip_statistics_latest": lambda _query: [
                {"set_id": "set-1", "calculation_run_id": "run-1", "run_at": "2026-06-25T11:00:00+00:00"}
            ],
            "simulation_latest_by_target": lambda _query: [
                {"calculation_run_id": "run-1", "run_at": "2026-06-25T10:00:00+00:00"}
            ],
            "simulation_input_cards": lambda _query: [{"id": "sic-1"}],
            "simulation_input_cards_with_near_mint_price": lambda _query: [{"id": "sic-nm-1"}],
        }
    )

    row = pokemon_snapshot_builders.build_set_page_snapshot_row({"id": "set-1", "name": "Alpha"}, client=client)
    payload = row["payload_json"]
    completeness = payload["meta"]["snapshotCompleteness"]

    assert payload["cardAppealMarketPriceCorrelation"] == correlation
    assert payload["card_appeal_market_price_correlation"] == correlation
    assert "explore_rip_statistics_latest unavailable; fell back to simulation_latest_by_target" not in payload["meta"]["warnings"]
    assert "rankings snapshot is stale relative to set page snapshot" in payload["meta"]["warnings"]
    assert completeness["explore_rankings_snapshot_updated_at"] == "2026-06-22T12:00:00+00:00"
    assert completeness["explore_rip_statistics_latest"]["availability"] == "OK"
    assert completeness["simulation_input_cards_row_count"] == 1
    assert completeness["simulation_input_cards_with_near_mint_price_row_count"] == 1
    assert completeness["top_hits_included_count"] == 1


def test_build_set_page_snapshot_row_suppresses_user_rankings_stale_warning_when_ranks_present(monkeypatch):
    monkeypatch.setattr(pokemon_snapshot_builders, "utc_now_iso", lambda: "2026-06-25T12:00:00+00:00")
    monkeypatch.setattr(
        pokemon_snapshot_builders,
        "get_explore_page_payload",
        lambda target_type, set_id: {
            "summary": {
                "calculation_run_id": "run-1",
                "pack_score": 80,
                "mean_value": 5,
                "pack_rank": 7,
                "profit_rank": 12,
                "safety_rank": 9,
                "desirability_rank": 4,
                "stability_rank": 15,
            },
            "top_hits": [{"card_name": "Chase", "ev_contribution": 1.2}],
            "meta": {
                "sources": {"simulation_input_cards": "OK"},
                "warnings": [],
                "sectionFreshness": {
                    "decisionSignalRanks": {"status": "fresh"},
                },
            },
        },
    )
    monkeypatch.setattr(pokemon_snapshot_builders, "get_rip_statistics_targets_payload", lambda limit: {"targets": []})

    client = _Client(
        {
            "pokemon_set_cards_snapshot_latest": lambda _query: [],
            "pokemon_explore_rankings_snapshot_latest": lambda _query: [
                {"updated_at": "2026-06-22T12:00:00+00:00"}
            ],
            "explore_rip_statistics_latest": lambda _query: [
                {"set_id": "set-1", "calculation_run_id": "run-1", "run_at": "2026-06-25T11:00:00+00:00"}
            ],
            "simulation_latest_by_target": lambda _query: [
                {"calculation_run_id": "run-1", "run_at": "2026-06-25T10:00:00+00:00"}
            ],
            "simulation_input_cards": lambda _query: [{"id": "sic-1"}],
            "simulation_input_cards_with_near_mint_price": lambda _query: [{"id": "sic-nm-1"}],
        }
    )

    row = pokemon_snapshot_builders.build_set_page_snapshot_row({"id": "set-1", "name": "Alpha"}, client=client)
    payload = row["payload_json"]

    assert "rankings snapshot is stale relative to set page snapshot" not in payload["meta"]["warnings"]
    assert "rankings snapshot is stale relative to set page snapshot" in payload["meta"]["debugWarnings"]


# ---------------------------------------------------------------------------
# Simulation performance history contract tests
# ---------------------------------------------------------------------------


def _sim_history_client(*, history_rows=None, summary_rows=None):
    """Build a minimal _Client that handles the tables needed for dashboard + simulation history."""
    _history_rows = history_rows if history_rows is not None else []
    _summary_rows = summary_rows if summary_rows is not None else []
    return _Client(
        {
            "card_variant_price_observations": lambda _query: [],
            "calculation_history_trend": lambda _query: _history_rows,
            "simulation_run_summary": lambda _query: _summary_rows,
        }
    )


def _value_history_stub(*, histories_by_scope=None):
    histories = histories_by_scope or {
        "standard": [{"date": "2026-06-20", "setValue": 1000.0}],
        "hits": [{"date": "2026-06-20", "setValue": 700.0}],
        "top10": [{"date": "2026-06-20", "setValue": 500.0}],
    }
    return lambda set_id, days, value_scope: {
        "history": histories.get(value_scope, []),
        "meta": {"availableScopes": [{"key": value_scope, "label": value_scope}]},
    }


def test_build_market_dashboard_performance_history_comes_from_simulation_not_set_value(monkeypatch):
    """performanceVsCostHistory must come from calculation_history_trend, not pokemon_set_value_daily_history."""
    history_rows = [
        {
            "snapshot_date": "2026-06-20",
            "calculation_run_id": "run-abc",
            "run_created_at": "2026-06-20T12:00:00+00:00",
            "simulated_mean_pack_value_vs_pack_cost": 0.72,
            "simulated_median_pack_value_vs_pack_cost": 0.45,
            "p95_value_to_cost_ratio": 3.1,
        },
    ]
    summary_rows = [
        {
            "calculation_run_id": "run-abc",
            "pack_cost": 5.0,
            "mean_value": 3.6,
            "median_value": 2.25,
        }
    ]

    monkeypatch.setattr(pokemon_snapshot_builders, "get_pokemon_set_value_history_payload", _value_history_stub())
    monkeypatch.setattr(
        pokemon_snapshot_builders,
        "get_pokemon_set_top_market_cards_payload",
        lambda set_id, limit, days: {"set": {"id": set_id}, "cards": [], "meta": {"warnings": []}},
    )
    monkeypatch.setattr(
        pokemon_snapshot_builders,
        "build_pokemon_set_card_movements_by_window_payload",
        lambda set_id, **_kwargs: _empty_movement_windows_payload(),
    )

    dashboard_row, _history_rows = pokemon_snapshot_builders.build_market_dashboard_snapshot_rows(
        {"id": "set-1", "name": "Test Set"},
        days=365,
        window="365d",
        client=_sim_history_client(history_rows=history_rows, summary_rows=summary_rows),
    )

    payload = dashboard_row["payload_json"]
    perf = payload["performanceVsCostHistory"]
    assert len(perf) == 1, "expected one simulation performance point"
    pt = perf[0]

    # Must carry simulation ratio and value fields
    assert pt["simulated_mean_pack_value_vs_pack_cost"] == 0.72
    assert pt["simulated_median_pack_value_vs_pack_cost"] == 0.45
    assert pt["p95_value_to_cost_ratio"] == 3.1
    assert pt["mean_value_to_cost_ratio"] == 0.72
    assert pt["median_value_to_cost_ratio"] == 0.45
    assert pt["p95ValueToCostRatio"] == 3.1
    assert pt["calculationRunId"] == "run-abc"
    assert pt["calculation_run_id"] == "run-abc"
    assert pt["pack_cost"] == 5.0
    assert pt["mean_value"] == 3.6
    assert pt["median_value"] == 2.25
    assert pt["source"] == "calculation_history_trend+simulation_run_summary"
    assert pt["isCarriedForward"] is False

    # Must not look like a set-value point
    assert "setValue" not in pt
    assert "set_value" not in pt
    assert "value" not in pt

    # Row-level column must also match
    assert dashboard_row["performance_vs_cost_history_json"] == perf


def test_build_market_dashboard_set_value_history_stays_in_scope_not_performance(monkeypatch):
    """Set value histories must remain only under setValueHistoriesByScope, not bleed into performanceVsCostHistory."""
    monkeypatch.setattr(
        pokemon_snapshot_builders,
        "get_pokemon_set_value_history_payload",
        _value_history_stub(
            histories_by_scope={
                "standard": [{"date": "2026-06-21", "setValue": 999.0}],
                "hits": [{"date": "2026-06-21", "setValue": 888.0}],
                "top10": [{"date": "2026-06-21", "setValue": 777.0}],
            }
        ),
    )
    monkeypatch.setattr(
        pokemon_snapshot_builders,
        "get_pokemon_set_top_market_cards_payload",
        lambda set_id, limit, days: {"set": {"id": set_id}, "cards": [], "meta": {"warnings": []}},
    )
    monkeypatch.setattr(
        pokemon_snapshot_builders,
        "build_pokemon_set_card_movements_by_window_payload",
        lambda set_id, **_kwargs: _empty_movement_windows_payload(),
    )

    dashboard_row, _history_rows = pokemon_snapshot_builders.build_market_dashboard_snapshot_rows(
        {"id": "set-1"},
        days=365,
        window="365d",
        client=_sim_history_client(),  # no simulation rows → empty perf history
    )

    payload = dashboard_row["payload_json"]

    # Set value histories still populated under their scope key
    assert len(payload["setValueHistoriesByScope"]["standard"]) == 1
    assert payload["setValueHistoriesByScope"]["standard"][0]["setValue"] == 999.0

    # performanceVsCostHistory must be empty (no simulation rows), not copied from standard scope
    assert payload["performanceVsCostHistory"] == []
    assert payload["performance_vs_cost_history"] == []
    assert dashboard_row["performance_vs_cost_history_json"] == []


def test_build_market_dashboard_sources_meta_identifies_simulation_history_source(monkeypatch):
    """meta.sources must identify calculation_history_trend+simulation_run_summary as the performance source."""
    monkeypatch.setattr(pokemon_snapshot_builders, "get_pokemon_set_value_history_payload", _value_history_stub())
    monkeypatch.setattr(
        pokemon_snapshot_builders,
        "get_pokemon_set_top_market_cards_payload",
        lambda set_id, limit, days: {"set": {"id": set_id}, "cards": [], "meta": {"warnings": []}},
    )
    monkeypatch.setattr(
        pokemon_snapshot_builders,
        "build_pokemon_set_card_movements_by_window_payload",
        lambda set_id, **_kwargs: _empty_movement_windows_payload(),
    )

    dashboard_row, _history_rows = pokemon_snapshot_builders.build_market_dashboard_snapshot_rows(
        {"id": "set-1"},
        days=365,
        window="365d",
        client=_sim_history_client(),
    )

    sources = dashboard_row["payload_json"]["meta"]["sources"]
    assert sources["performance_vs_cost_history"] == "calculation_history_trend+simulation_run_summary"
    assert sources["performanceVsCostHistory"] == "calculation_history_trend+simulation_run_summary"
    assert sources["set_value_histories"] == "pokemon_set_value_daily_history"


def test_build_market_dashboard_performance_history_updates_when_simulation_changes_not_set_value(monkeypatch):
    """Regression: changing set value must NOT change performanceVsCostHistory; changing simulation MUST."""
    sim_rows_v1 = [
        {
            "snapshot_date": "2026-06-20",
            "calculation_run_id": "run-v1",
            "run_created_at": "2026-06-20T10:00:00+00:00",
            "simulated_mean_pack_value_vs_pack_cost": 0.60,
            "simulated_median_pack_value_vs_pack_cost": 0.40,
            "p95_value_to_cost_ratio": 2.5,
        }
    ]
    sim_rows_v2 = [
        {
            "snapshot_date": "2026-06-20",
            "calculation_run_id": "run-v2",
            "run_created_at": "2026-06-20T18:00:00+00:00",
            "simulated_mean_pack_value_vs_pack_cost": 0.80,
            "simulated_median_pack_value_vs_pack_cost": 0.55,
            "p95_value_to_cost_ratio": 3.9,
        }
    ]

    def make_row(sim_rows, set_value):
        monkeypatch.setattr(
            pokemon_snapshot_builders,
            "get_pokemon_set_value_history_payload",
            _value_history_stub(
                histories_by_scope={
                    "standard": [{"date": "2026-06-20", "setValue": set_value}],
                    "hits": [],
                    "top10": [],
                }
            ),
        )
        monkeypatch.setattr(
            pokemon_snapshot_builders,
            "get_pokemon_set_top_market_cards_payload",
            lambda set_id, limit, days: {"set": {"id": set_id}, "cards": [], "meta": {"warnings": []}},
        )
        monkeypatch.setattr(
            pokemon_snapshot_builders,
            "build_pokemon_set_card_movements_by_window_payload",
            lambda set_id, **_kwargs: _empty_movement_windows_payload(),
        )
        dashboard_row, _ = pokemon_snapshot_builders.build_market_dashboard_snapshot_rows(
            {"id": "set-1"},
            days=365,
            window="365d",
            client=_sim_history_client(history_rows=sim_rows),
        )
        return dashboard_row["payload_json"]["performanceVsCostHistory"]

    # Baseline: sim_rows_v1, set_value=100
    perf_v1_sv100 = make_row(sim_rows_v1, 100.0)

    # Set value changes (200 vs 100), simulation stays at v1 → performanceVsCostHistory must NOT change
    perf_v1_sv200 = make_row(sim_rows_v1, 200.0)
    assert perf_v1_sv100 == perf_v1_sv200, "set value change must not affect performanceVsCostHistory"

    # Simulation changes (v2), set value stays at 100 → performanceVsCostHistory MUST change
    perf_v2_sv100 = make_row(sim_rows_v2, 100.0)
    assert perf_v2_sv100 != perf_v1_sv100, "simulation change must update performanceVsCostHistory"
    assert perf_v2_sv100[0]["simulated_mean_pack_value_vs_pack_cost"] == 0.80
