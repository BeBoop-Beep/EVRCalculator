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

    def observations(variant_ids, condition_by_variant, _days, _sources):
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
