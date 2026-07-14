from backend.db.services.pokemon_card_market_delta_contract import (
    WINDOW_CONVENTION,
    calculate_pokemon_card_market_delta,
)
from backend.db.services import pokemon_set_market_service
from backend.scripts import pokemon_snapshot_builders
from backend.scripts.audit_pokemon_card_delta_parity import audit_payloads


VARIANT_ID = "variant-clefairy"
CONDITION_ID = "near-mint"
CARD_ID = "canonical-clefairy"
OBSERVATIONS = [
    {"captured_at": "2026-06-13T23:00:00Z", "market_price": 132.17},
    {"captured_at": "2026-06-14T23:00:00Z", "market_price": 129.24},
    {"captured_at": "2026-07-06T23:00:00Z", "market_price": 126.89},
    {"captured_at": "2026-07-07T23:00:00Z", "market_price": 125.64},
    {"captured_at": "2026-07-13T23:00:00Z", "market_price": 127.13},
]


def _delta(days, observations=OBSERVATIONS):
    return calculate_pokemon_card_market_delta(
        observations=observations,
        selected_current_price=127.13,
        selected_variant_id=VARIANT_ID,
        selected_condition_id=CONDITION_ID,
        latest_market_date="2026-07-13",
        requested_window_days=days,
        selected_current_source_date="2026-07-13T23:00:00Z",
    )


def test_inclusive_7d_and_30d_journey_together_regression():
    seven = _delta(7)
    thirty = _delta(30)
    assert seven["windowConvention"] == WINDOW_CONVENTION
    assert seven["targetStartDate"] == "2026-07-07"
    assert seven["startDate"] == "2026-07-07"
    assert seven["endDate"] == "2026-07-13"
    assert seven["changeAmount"] == 1.49
    assert seven["changePercent"] == 1.19
    assert thirty["targetStartDate"] == "2026-06-14"
    assert thirty["startDate"] == "2026-06-14"
    assert thirty["changeAmount"] == -2.11
    assert thirty["changePercent"] == -1.63


def test_ascended_heroes_pikachu_276_uses_correct_inclusive_7d_baseline_on_every_surface():
    canonical_card_id = "301185dd-2bde-4699-80bd-8b2a3cfd8f7f"
    variant_id = "ascended-heroes-pikachu-276-variant"
    condition_id = "near-mint"
    observations = [
        {"captured_at": "2026-07-06T23:00:00Z", "market_price": 1301.08},
        {"captured_at": "2026-07-07T23:00:00Z", "market_price": 1237.84},
        {"captured_at": "2026-07-13T23:00:00Z", "market_price": 1284.32},
    ]
    selected_price = {
        "card_variant_id": variant_id,
        "condition_id": condition_id,
        "market_price": 1284.32,
        "captured_at": "2026-07-13T23:00:00Z",
    }
    delta = calculate_pokemon_card_market_delta(
        observations=observations,
        selected_current_price=1284.32,
        selected_variant_id=variant_id,
        selected_condition_id=condition_id,
        latest_market_date="2026-07-13",
        requested_window_days=7,
        selected_current_source_date="2026-07-13T23:00:00Z",
    )

    # The stale dashboard used 2026-07-06 and produced -$16.76.  The unchanged
    # inclusive contract must target 2026-07-07 and produce +$46.48.
    assert round(1284.32 - 1301.08, 2) == -16.76
    assert delta["targetStartDate"] == "2026-07-07"
    assert delta["startDate"] == "2026-07-07"
    assert delta["endDate"] == "2026-07-13"
    assert delta["currentPrice"] == 1284.32
    assert delta["changeAmount"] == 46.48
    assert delta["changePercent"] == 3.75

    cards_movement = pokemon_snapshot_builders._movement_contract(
        price={
            "market_price": 1284.32,
            "captured_at": "2026-07-13T23:00:00Z",
            "variant_id": variant_id,
            "condition_id": condition_id,
        },
        observations=[
            {"source_date": row["captured_at"][:10], "market_price": row["market_price"]}
            for row in observations
        ],
        latest_market_date="2026-07-13",
        window_days=7,
    )
    mover = pokemon_set_market_service._canonical_public_card_movement(
        canonical_card={"id": canonical_card_id, "set_id": "ascended-heroes", "name": "Pikachu ex"},
        selected_price=selected_price,
        delta=delta,
    )
    top_cards, diagnostics = pokemon_snapshot_builders._enrich_top_chase_cards_with_canonical_deltas(
        [{"cardId": canonical_card_id, "cardVariantId": variant_id, "name": "Pikachu ex"}],
        histories={
            variant_id: [
                {"date": row["captured_at"][:10], "marketPrice": row["market_price"]}
                for row in observations
            ]
        },
        canonical_context={
            "display_key_to_canonical_id": {variant_id: canonical_card_id},
            "selected_price_by_canonical_id": {canonical_card_id: selected_price},
        },
        latest_market_date="2026-07-13",
        movement_metadata={
            "movementContractVersion": "pokemon_card_movement_v1",
            "windowConvention": WINDOW_CONVENTION,
            "movementAsOfDate": "2026-07-13",
            "generationId": "11111111-1111-4111-8111-111111111111",
            "builtAt": "2026-07-13T23:59:00+00:00",
        },
    )
    top_movement = top_cards[0]["marketDeltaWindows"]["7D"]
    assert diagnostics == []
    assert set(top_cards[0]["marketDeltaWindows"]) == {"1D", "7D", "30D"}
    assert top_cards[0]["movementMetadata"]["generationId"] == "11111111-1111-4111-8111-111111111111"
    assert top_movement["canonicalCardId"] == canonical_card_id
    assert all(
        movement["generationId"] == "11111111-1111-4111-8111-111111111111"
        for movement in top_cards[0]["marketDeltaWindows"].values()
    )
    for field in (
        "cardVariantId", "conditionId", "currentPrice", "targetStartDate",
        "startDate", "endDate", "changeAmount", "changePercent",
        "fullWindowCoverage", "windowConvention",
    ):
        assert cards_movement[field] == mover[field] == top_movement[field]

    assert audit_payloads(
        [{"id": canonical_card_id, "movement7d": cards_movement}],
        {
            "marketMoversByWindow": {"7D": {"all": [mover]}},
            "topChaseCards": [{
                "canonicalCardId": canonical_card_id,
                "marketDeltaWindows": {"7D": top_movement},
            }],
        },
        set_id="ascended-heroes",
    ) == []


def test_1d_uses_previous_distinct_utc_market_date():
    movement = _delta(1)
    assert movement["targetStartDate"] == "2026-07-07"
    assert movement["startDate"] == "2026-07-07"
    assert movement["changeAmount"] == 1.49


def test_missing_pre_boundary_history_is_partial_but_displayable():
    movement = _delta(30, observations=OBSERVATIONS[-2:])
    assert movement["targetStartDate"] == "2026-06-14"
    assert movement["startDate"] == "2026-07-07"
    assert movement["changeAmount"] == 1.49
    assert movement["fullWindowCoverage"] is False
    assert movement["isPartialWindow"] is True
    assert movement["reliable"] is False
    assert movement["reliability"] == "partial_window"


def test_top_chase_omits_unusable_short_windows_and_reports_identity_gaps():
    selected_price = {
        "card_variant_id": VARIANT_ID,
        "condition_id": CONDITION_ID,
        "market_price": 127.13,
        "captured_at": "2026-07-13T23:00:00Z",
    }
    cards, diagnostics = pokemon_snapshot_builders._enrich_top_chase_cards_with_canonical_deltas(
        [
            {"cardId": "display-1", "cardVariantId": VARIANT_ID, "name": "One Point"},
            {"cardId": "unmapped", "cardVariantId": "unmapped-variant", "name": "Unmapped"},
        ],
        histories={VARIANT_ID: [{"date": "2026-07-13", "marketPrice": 127.13}]},
        canonical_context={
            "display_key_to_canonical_id": {VARIANT_ID: CARD_ID},
            "selected_price_by_canonical_id": {CARD_ID: selected_price},
        },
        latest_market_date="2026-07-13",
    )

    assert cards[0]["marketDeltaWindows"] == {}
    assert "marketDeltaWindows" not in cards[1]
    assert diagnostics == [{
        "type": "top_chase_missing_canonical_identity",
        "displayCardId": "unmapped-variant",
        "name": "Unmapped",
    }]


def test_top_chase_reports_missing_selected_variant():
    cards, diagnostics = pokemon_snapshot_builders._enrich_top_chase_cards_with_canonical_deltas(
        [{"cardId": "display-1", "cardVariantId": VARIANT_ID, "name": "No Selection"}],
        histories={},
        canonical_context={
            "display_key_to_canonical_id": {VARIANT_ID: CARD_ID},
            "selected_price_by_canonical_id": {},
        },
        latest_market_date="2026-07-13",
    )

    assert "marketDeltaWindows" not in cards[0]
    assert diagnostics[0]["type"] == "top_chase_missing_selected_variant"


def test_selected_variant_cannot_be_replaced_by_more_volatile_printing(monkeypatch):
    requested_variants = []

    def observations(variant_ids, condition_by_variant, _days, _sources, **_kwargs):
        requested_variants.extend(variant_ids)
        assert condition_by_variant == {VARIANT_ID: CONDITION_ID}
        return [{**row, "card_variant_id": VARIANT_ID, "condition_id": CONDITION_ID} for row in OBSERVATIONS]

    monkeypatch.setattr(pokemon_set_market_service, "_load_conditioned_price_observation_rows", observations)
    context = {
        "canonical_by_id": {
            CARD_ID: {"id": CARD_ID, "set_id": "set-1", "name": "Lillie's Clefairy ex", "number": "184"}
        },
        "selected_price_by_canonical_id": {
            CARD_ID: {
                "canonical_card_id": CARD_ID,
                "card_variant_id": VARIANT_ID,
                "condition_id": CONDITION_ID,
                "market_price": 127.13,
                "captured_at": "2026-07-13T23:00:00Z",
                "source": "fixture",
            }
        },
        # This printing is deliberately absent from the selected-price layer.
        "variant_ids": [VARIANT_ID, "volatile-alternate-printing"],
    }
    movements = pokemon_set_market_service._build_card_movements_from_context(context, window_days=7)
    assert requested_variants == [VARIANT_ID]
    assert len(movements) == 1
    movement = movements[0]
    assert movement["cardVariantId"] == VARIANT_ID
    assert movement["conditionId"] == CONDITION_ID
    assert movement["changeAmount"] == 1.49
    assert movement["change7dAmount"] == 1.49
    assert "change30dAmount" not in movement
    assert movement["moverEligible"] is True


def test_cards_movers_and_top_chase_share_journey_together_values():
    price = {
        "market_price": 127.13,
        "captured_at": "2026-07-13T23:00:00Z",
        "variant_id": VARIANT_ID,
        "condition_id": CONDITION_ID,
    }
    observations = [
        {"source_date": row["captured_at"][:10], "market_price": row["market_price"]}
        for row in OBSERVATIONS
    ]
    cards = pokemon_snapshot_builders._movement_contract(
        price=price,
        observations=observations,
        latest_market_date="2026-07-13",
        window_days=30,
    )
    mover = pokemon_set_market_service._canonical_public_card_movement(
        canonical_card={"id": CARD_ID, "set_id": "set-1", "name": "Lillie's Clefairy ex"},
        selected_price={
            "card_variant_id": VARIANT_ID,
            "condition_id": CONDITION_ID,
            "market_price": 127.13,
            "captured_at": "2026-07-13T23:00:00Z",
        },
        delta=_delta(30),
    )
    top_cards, diagnostics = pokemon_snapshot_builders._enrich_top_chase_cards_with_canonical_deltas(
        [{"cardId": "simulation-card", "cardVariantId": VARIANT_ID, "name": "Lillie's Clefairy ex"}],
        histories={VARIANT_ID: observations},
        canonical_context={
            "display_key_to_canonical_id": {VARIANT_ID: CARD_ID},
            "selected_price_by_canonical_id": {
                CARD_ID: {
                    "card_variant_id": VARIANT_ID,
                    "condition_id": CONDITION_ID,
                    "market_price": 127.13,
                    "captured_at": "2026-07-13T23:00:00Z",
                }
            },
        },
        latest_market_date="2026-07-13",
    )
    top = top_cards[0]["marketDeltaWindows"]["30D"]
    assert diagnostics == []
    for field in (
        "cardVariantId", "conditionId", "currentPrice", "targetStartDate", "startDate",
        "endDate", "changeAmount", "changePercent", "fullWindowCoverage",
        "isPartialWindow", "windowConvention",
    ):
        assert cards[field] == mover[field] == top[field]


def test_parity_audit_detects_intentional_amount_mismatch():
    movement = _delta(30)
    card = {"id": CARD_ID, "movement30d": movement}
    mover = {"canonicalCardId": CARD_ID, **movement}
    top = {"canonicalCardId": CARD_ID, "marketDeltaWindows": {"30D": {**movement, "changeAmount": -9.99}}}
    mismatches = audit_payloads(
        [card],
        {
            "marketMoversByWindow": {"30D": {"all": [mover]}},
            "topChaseCards": [top],
        },
        set_id="journeyTogether",
    )
    assert any(row["type"] == "amount mismatch" for row in mismatches)


def test_multi_window_builder_loads_context_and_observations_once(monkeypatch):
    calls = {"resolve": 0, "context": 0, "observations": 0}
    selected_price = {
        "canonical_card_id": CARD_ID,
        "card_variant_id": VARIANT_ID,
        "condition_id": CONDITION_ID,
        "market_price": 127.13,
        "captured_at": "2026-07-13T23:00:00Z",
        "source": "fixture",
    }
    context = {
        "set": {"id": "set-1", "name": "Journey Together"},
        "canonical_by_id": {
            CARD_ID: {"id": CARD_ID, "set_id": "set-1", "name": "Lillie's Clefairy ex", "number": "184"}
        },
        "selected_price_by_canonical_id": {CARD_ID: selected_price},
    }

    def resolve(set_id, *, client=None):
        calls["resolve"] += 1
        return {"id": "set-1", "name": "Journey Together"}

    def build_context(*_args, **_kwargs):
        calls["context"] += 1
        return context

    def load_observations(_variants, _conditions, _days, _sources, *, diagnostics=None, **_kwargs):
        calls["observations"] += 1
        if diagnostics is not None:
            diagnostics["observationQueryCount"] += 1
            diagnostics["observationPageCount"] += 1
            diagnostics["observationRowsLoaded"] = len(OBSERVATIONS)
        return [{**row, "id": f"obs-{index}", "card_variant_id": VARIANT_ID, "condition_id": CONDITION_ID}
                for index, row in enumerate(OBSERVATIONS)]

    monkeypatch.setattr(pokemon_set_market_service, "resolve_pokemon_set_identifier", resolve)
    monkeypatch.setattr(pokemon_set_market_service, "_build_market_context", build_context)
    monkeypatch.setattr(pokemon_set_market_service, "_load_conditioned_price_observation_rows", load_observations)

    payload = pokemon_set_market_service.build_pokemon_set_card_movements_by_window_payload(
        "set-1",
        client=object(),
    )

    assert calls == {"resolve": 1, "context": 1, "observations": 1}
    assert payload["meta"] == {
        "observationQueryCount": 1,
        "observationRowsLoaded": 5,
        "selectedVariantCount": 1,
        "observationPageCount": 1,
        "windowsCalculated": 3,
        "sources": {},
        "warnings": [],
    }
    seven = payload["payloadsByWindow"]["7D"]["movements"][0]
    thirty = payload["payloadsByWindow"]["30D"]["movements"][0]
    assert (seven["changeAmount"], seven["changePercent"]) == (1.49, 1.19)
    assert (thirty["changeAmount"], thirty["changePercent"]) == (-2.11, -1.63)


def test_observation_query_paginates_and_deduplicates_exact_rows():
    rows = [
        {
            "id": f"obs-{index}",
            "card_variant_id": VARIANT_ID,
            "condition_id": CONDITION_ID,
            "market_price": observation["market_price"],
            "source": "fixture",
            "captured_at": observation["captured_at"],
        }
        for index, observation in enumerate(OBSERVATIONS)
    ]
    rows.insert(3, dict(rows[2]))

    class Result:
        def __init__(self, data):
            self.data = data

    class Query:
        def __init__(self):
            self.range_value = None

        def select(self, *_args, **_kwargs): return self
        def in_(self, *_args, **_kwargs): return self
        def gte(self, *_args, **_kwargs): return self
        def order(self, *_args, **_kwargs): return self
        def range(self, start, end):
            self.range_value = (start, end)
            return self
        def execute(self):
            start, end = self.range_value
            return Result(rows[start:end + 1])

    class Client:
        def table(self, _name): return Query()

    diagnostics = {}
    loaded = pokemon_set_market_service._load_conditioned_price_observation_rows(
        [VARIANT_ID],
        {VARIANT_ID: CONDITION_ID},
        45,
        {},
        client=Client(),
        diagnostics=diagnostics,
        page_size=2,
    )

    assert [row["id"] for row in loaded] == [f"obs-{index}" for index in range(5)]
    assert diagnostics == {
        "observationQueryCount": 4,
        "observationPageCount": 4,
        "observationRowsLoaded": 5,
    }
    deduped_delta = _delta(30, observations=loaded)
    assert (deduped_delta["changeAmount"], deduped_delta["changePercent"]) == (-2.11, -1.63)
