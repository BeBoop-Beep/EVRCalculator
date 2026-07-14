from uuid import UUID

import pytest

from backend.scripts import pokemon_snapshot_builders as builders


def test_coordinated_builder_reuses_one_generation_and_build_timestamp(monkeypatch):
    calls = {}
    selected_price_rows = [{"canonical_card_id": "card-1", "market_price": 10.0}]

    def build_cards(set_row, **kwargs):
        calls["cards"] = kwargs
        return {"set_id": set_row["id"], "cards_json": [], "payload_json": {"cards": []}}

    def build_dashboard(set_row, **kwargs):
        calls["dashboard"] = kwargs
        return (
            {
                "set_id": set_row["id"],
                "window_key": kwargs["window"],
                "payload_json": {"marketMoversByWindow": {}, "topChaseCards": []},
            },
            [],
        )

    monkeypatch.setattr(builders, "build_cards_snapshot_row", build_cards)
    monkeypatch.setattr(builders, "build_market_dashboard_snapshot_rows", build_dashboard)
    monkeypatch.setattr(builders, "_query_rows", lambda *_args, **_kwargs: selected_price_rows)

    cards_row, dashboard_row, history_rows = builders.build_coordinated_set_market_snapshot_rows(
        {"id": "set-1"},
        client=object(),
    )

    assert cards_row["set_id"] == dashboard_row["set_id"] == "set-1"
    assert history_rows == []
    assert calls["cards"]["generation_id"] == calls["dashboard"]["generation_id"]
    assert calls["cards"]["built_at"] == calls["dashboard"]["built_at"]
    assert calls["cards"]["selected_price_rows"] is selected_price_rows
    assert calls["dashboard"]["selected_price_rows"] is selected_price_rows
    UUID(calls["cards"]["generation_id"])


def test_parity_gate_rejects_target_start_date_mismatch():
    shared = {
        "cardVariantId": "variant-1",
        "conditionId": "near-mint",
        "currentPrice": 1284.32,
        "startDate": "2026-07-07",
        "endDate": "2026-07-13",
        "changeAmount": 46.48,
        "changePercent": 3.75,
        "fullWindowCoverage": True,
        "windowConvention": "inclusive_calendar_dates_v1",
    }
    cards_row = {
        "set_id": "ascended-heroes",
        "cards_json": [{
            "id": "301185dd-2bde-4699-80bd-8b2a3cfd8f7f",
            "movement7d": {**shared, "targetStartDate": "2026-07-07"},
        }],
    }
    dashboard_row = {
        "set_id": "ascended-heroes",
        "payload_json": {
            "topChaseCards": [{
                "canonicalCardId": "301185dd-2bde-4699-80bd-8b2a3cfd8f7f",
                "marketDeltaWindows": {
                    "7D": {**shared, "targetStartDate": "2026-07-06"},
                },
            }],
        },
    }

    with pytest.raises(builders.PokemonSnapshotMovementParityError) as raised:
        builders.validate_coordinated_movement_parity(cards_row, dashboard_row)

    assert any(
        mismatch["type"] == "target-baseline-date mismatch"
        for mismatch in raised.value.mismatches
    )
