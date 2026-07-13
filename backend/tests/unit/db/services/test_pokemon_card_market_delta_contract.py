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
