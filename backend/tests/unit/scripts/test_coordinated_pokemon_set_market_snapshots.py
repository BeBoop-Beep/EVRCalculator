from uuid import UUID

import pytest

from backend.db.services.pokemon_card_market_delta_contract import (
    calculate_pokemon_card_market_delta,
)
from backend.scripts import pokemon_snapshot_builders as builders
from backend.scripts.audit_pokemon_card_delta_parity import audit_payloads


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


# ---------------------------------------------------------------------------
# Movement parity root cause: one shared window boundary across all surfaces
# ---------------------------------------------------------------------------


def test_canonical_latest_market_date_is_set_wide_max():
    rows = [
        {"canonical_card_id": "a", "market_price": 10.0, "captured_at": "2026-07-10T00:00:00Z"},
        {"canonical_card_id": "b", "market_price": 12.0, "captured_at": "2026-07-13T09:00:00Z"},
        # Newest capture but no usable price — must not set the boundary.
        {"canonical_card_id": "c", "market_price": None, "captured_at": "2026-07-14T00:00:00Z"},
    ]
    assert builders._canonical_latest_market_date(rows) == "2026-07-13"


def test_canonical_latest_market_date_falls_back_to_set_history(monkeypatch):
    monkeypatch.setattr(builders, "_latest_market_date_for_set", lambda _client, _set_id: "2026-07-01")
    # No dated selected rows -> fall back to the set value history date.
    result = builders._canonical_latest_market_date([], client=object(), set_id="set-1")
    assert result == "2026-07-01"


def test_coordinated_builder_threads_one_shared_boundary_to_all_surfaces(monkeypatch):
    calls = {}
    selected_price_rows = [
        {"canonical_card_id": "card-1", "market_price": 10.0, "captured_at": "2026-07-10T00:00:00Z"},
        {"canonical_card_id": "card-2", "market_price": 20.0, "captured_at": "2026-07-13T00:00:00Z"},
    ]

    def build_cards(set_row, **kwargs):
        calls["cards"] = kwargs
        return {"set_id": set_row["id"], "cards_json": [], "payload_json": {"cards": []}}

    def build_dashboard(set_row, **kwargs):
        calls["dashboard"] = kwargs
        return (
            {"set_id": set_row["id"], "window_key": kwargs["window"], "payload_json": {}},
            [],
        )

    monkeypatch.setattr(builders, "build_cards_snapshot_row", build_cards)
    monkeypatch.setattr(builders, "build_market_dashboard_snapshot_rows", build_dashboard)
    monkeypatch.setattr(builders, "_query_rows", lambda *_a, **_k: selected_price_rows)

    builders.build_coordinated_set_market_snapshot_rows({"id": "set-1"}, client=object())

    # The whole point of the fix: Cards and Dashboard receive the identical,
    # set-wide window boundary (not a per-surface subset date).
    assert calls["cards"]["latest_market_date"] == "2026-07-13"
    assert calls["dashboard"]["latest_market_date"] == "2026-07-13"


def _observations():
    # Representative daily-ish history for a chase card, near-mint condition.
    return [
        {"card_variant_id": "variant-1", "condition_id": "near-mint", "market_price": 100.0, "captured_at": "2026-06-13T00:00:00Z"},
        {"card_variant_id": "variant-1", "condition_id": "near-mint", "market_price": 110.0, "captured_at": "2026-07-06T00:00:00Z"},
        {"card_variant_id": "variant-1", "condition_id": "near-mint", "market_price": 120.0, "captured_at": "2026-07-13T00:00:00Z"},
    ]


def _contract(*, window_days, latest_market_date):
    return calculate_pokemon_card_market_delta(
        observations=_observations(),
        selected_current_price=120.0,
        selected_variant_id="variant-1",
        selected_condition_id="near-mint",
        latest_market_date=latest_market_date,
        requested_window_days=window_days,
        selected_current_source_date="2026-07-13",
        selected_current_source="tcgplayer",
    )


def _cards_payload(latest_market_date):
    return [{
        "id": "card-xyz",
        "canonicalCardId": "card-xyz",
        "cardVariantId": "variant-1",
        "conditionId": "near-mint",
        "movement7d": _contract(window_days=7, latest_market_date=latest_market_date),
        "movement30d": _contract(window_days=30, latest_market_date=latest_market_date),
    }]


def _dashboard_payload(latest_market_date):
    return {
        "topChaseCards": [{
            "canonicalCardId": "card-xyz",
            "cardVariantId": "variant-1",
            "conditionId": "near-mint",
            "marketDeltaWindows": {
                "7D": _contract(window_days=7, latest_market_date=latest_market_date),
                "30D": _contract(window_days=30, latest_market_date=latest_market_date),
            },
        }],
    }


def test_shared_boundary_yields_zero_parity_mismatches():
    # Cards and Top Chase driven by the identical canonical contract with the
    # identical end date must produce no parity mismatches.
    mismatches = audit_payloads(
        _cards_payload("2026-07-13"),
        _dashboard_payload("2026-07-13"),
        set_id="set-1",
    )
    assert mismatches == []


def test_divergent_boundary_is_the_root_cause_the_gate_catches():
    # Reproduce the pre-fix divergence: Top Chase computed an earlier end date
    # than Cards. The gate must reject it, and the diagnostic must carry dates.
    mismatches = audit_payloads(
        _cards_payload("2026-07-13"),
        _dashboard_payload("2026-07-12"),
        set_id="set-1",
    )
    types = {mismatch["type"] for mismatch in mismatches}
    assert "as-of-date mismatch" in types
    as_of = next(m for m in mismatches if m["type"] == "as-of-date mismatch")
    assert as_of["left"] == "2026-07-13"
    assert as_of["right"] == "2026-07-12"
    # Enriched diagnostics: variant + source dates travel with every mismatch.
    assert as_of["leftContext"]["cardVariantId"] == "variant-1"
    assert as_of["leftContext"]["endDate"] == "2026-07-13"
    assert as_of["rightContext"]["endDate"] == "2026-07-12"


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
