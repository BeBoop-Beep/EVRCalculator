"""Market-freshness reference date and Top Chase observed-date contracts.

Two defects are covered here:

* The UTC page BUILD date must never drive market freshness. A snapshot written
  at 18:00 in Phoenix on July 25 carries a July 26 UTC build date; letting that
  advance the freshness reference marked every genuinely current July-25 market
  section stale.
* "Observed" has exactly ONE definition. Forward-fill carries the last real
  observation to the canonical market boundary for display continuity, and no
  observed-date field may be advanced by those synthetic points.
"""

import pytest

from backend.scripts import pokemon_snapshot_builders
from backend.tests.unit.scripts.test_pokemon_snapshot_builders import (
    _Client,
    _empty_movement_windows_payload,
)


# ---------------------------------------------------------------------------
# Defect 1 — page build date vs market freshness reference
# ---------------------------------------------------------------------------


def test_utc_build_date_after_rollover_does_not_stale_current_market_sections():
    fresh = pokemon_snapshot_builders._build_dashboard_section_freshness(
        built_at="2026-07-26T02:34:00+00:00",  # 2026-07-25 19:34 America/Phoenix
        advertised_market_date="2026-07-25",
        set_value_source_date="2026-07-25",
        top_chase_source_date="2026-07-25",
        cards_snapshot_source_date="2026-07-25",
        simulation_source_date="2026-07-17",
    )

    assert fresh["referenceDate"] == "2026-07-25"
    assert fresh["sections"]["setValue"]["status"] == "current"
    assert fresh["sections"]["cards"]["status"] == "current"
    assert fresh["sections"]["topChase"]["status"] == "current"
    # Simulation is compared against the market reference but never advances it.
    assert fresh["sections"]["simulation"]["status"] == "stale"
    # pageSourceDate stays exposed as PUBLICATION metadata under its own status
    # vocabulary, so it cannot be read as a market-data status.
    assert fresh["pageSourceDate"] == "2026-07-26"
    assert fresh["sections"]["page"]["status"] == "published"
    assert fresh["sections"]["page"]["kind"] == "publication"
    assert fresh["marketSectionsUniformlyCurrent"] is True
    assert fresh["uniformlyCurrent"] is False


def test_market_reference_falls_back_to_newest_market_source_when_advertised_missing():
    fresh = pokemon_snapshot_builders._build_dashboard_section_freshness(
        built_at="2026-07-26T02:00:00+00:00",
        advertised_market_date=None,
        set_value_source_date="2026-07-25",
        top_chase_source_date="2026-07-16",
        cards_snapshot_source_date="2026-07-24",
        simulation_source_date="2026-07-17",
    )
    # Newest MARKET source date wins; the July-26 build date is not a candidate.
    assert fresh["referenceDate"] == "2026-07-25"
    assert fresh["sections"]["setValue"]["status"] == "current"
    assert fresh["sections"]["cards"]["status"] == "stale"
    assert fresh["sections"]["topChase"]["status"] == "stale"


def test_simulation_date_never_advances_the_market_reference():
    fresh = pokemon_snapshot_builders._build_dashboard_section_freshness(
        built_at="2026-07-25T00:00:00+00:00",
        advertised_market_date=None,
        set_value_source_date="2026-07-25",
        top_chase_source_date="2026-07-25",
        cards_snapshot_source_date="2026-07-25",
        simulation_source_date="2026-08-01",  # ahead of every market date
    )
    assert fresh["referenceDate"] == "2026-07-25"
    assert fresh["sections"]["setValue"]["status"] == "current"
    assert fresh["sections"]["simulation"]["status"] == "current"


@pytest.mark.parametrize(
    "built_at", ["not-a-timestamp", "", None, "2027-01-01T00:00:00+00:00"]
)
def test_malformed_or_future_build_date_cannot_change_market_statuses(built_at):
    fresh = pokemon_snapshot_builders._build_dashboard_section_freshness(
        built_at=built_at,
        advertised_market_date="2026-07-25",
        set_value_source_date="2026-07-25",
        top_chase_source_date="2026-07-16",
        cards_snapshot_source_date="2026-07-25",
        simulation_source_date="2026-07-17",
    )
    assert fresh["referenceDate"] == "2026-07-25"
    assert fresh["sections"]["setValue"]["status"] == "current"
    assert fresh["sections"]["cards"]["status"] == "current"
    assert fresh["sections"]["topChase"]["status"] == "stale"


def test_mixed_freshness_fixture_with_july_26_utc_build_date():
    """Required regression fixture: mixed July 16/17/25 data, July 26 UTC build."""
    fresh = pokemon_snapshot_builders._build_dashboard_section_freshness(
        built_at="2026-07-26T03:00:00+00:00",
        advertised_market_date="2026-07-25",
        set_value_source_date="2026-07-25",
        top_chase_source_date="2026-07-16",
        cards_snapshot_source_date="2026-07-16",
        simulation_source_date="2026-07-17",
    )
    assert fresh["referenceDate"] == "2026-07-25"
    assert fresh["sections"]["setValue"]["status"] == "current"
    assert fresh["sections"]["cards"]["status"] == "stale"
    assert fresh["sections"]["topChase"]["status"] == "stale"
    assert fresh["sections"]["simulation"]["status"] == "stale"
    assert fresh["pageSourceDate"] == "2026-07-26"
    assert fresh["uniformlyCurrent"] is False


def test_fully_current_market_with_stale_simulation_fixture():
    fresh = pokemon_snapshot_builders._build_dashboard_section_freshness(
        built_at="2026-07-26T03:00:00+00:00",
        advertised_market_date="2026-07-25",
        set_value_source_date="2026-07-25",
        top_chase_source_date="2026-07-25",
        cards_snapshot_source_date="2026-07-25",
        simulation_source_date="2026-07-17",
    )
    assert fresh["marketSectionsUniformlyCurrent"] is True
    assert fresh["uniformlyCurrent"] is False
    assert fresh["openingProfitVsCost"] == {"sourceDate": "2026-07-17", "status": "stale"}


def test_missing_market_source_dates_report_unavailable_not_current():
    fresh = pokemon_snapshot_builders._build_dashboard_section_freshness(
        built_at="2026-07-26T03:00:00+00:00",
        advertised_market_date=None,
        set_value_source_date=None,
        top_chase_source_date=None,
        cards_snapshot_source_date=None,
        simulation_source_date=None,
    )
    assert fresh["referenceDate"] is None
    for key in ("setValue", "topChase", "cards", "simulation"):
        assert fresh["sections"][key]["status"] == "unavailable"
    assert fresh["uniformlyCurrent"] is False


# ---------------------------------------------------------------------------
# Defect 5 — ONE canonical "genuinely observed" Top Chase point definition
# ---------------------------------------------------------------------------


def test_observed_point_helper_excludes_carry_forward_in_both_conventions():
    is_observed = pokemon_snapshot_builders.is_observed_top_chase_point
    assert is_observed({"date": "2026-07-16"}) is True
    assert is_observed({"date": "2026-07-16", "isObserved": True}) is True
    assert is_observed({"date": "2026-07-16", "is_observed": True}) is True
    # Explicitly unobserved / carried forward, camelCase and snake_case.
    assert is_observed({"date": "2026-07-25", "isObserved": False}) is False
    assert is_observed({"date": "2026-07-25", "is_observed": False}) is False
    assert is_observed({"date": "2026-07-25", "isCarriedForward": True}) is False
    assert is_observed({"date": "2026-07-25", "is_carried_forward": True}) is False
    # No usable date at all.
    assert is_observed({"marketPrice": 1.0}) is False
    assert is_observed(None) is False
    # capturedAt/captured_at are accepted date sources.
    assert is_observed({"captured_at": "2026-07-16T10:00:00+00:00"}) is True


def test_observed_dates_ignore_a_history_that_is_only_carried_forward():
    histories = {
        "variant-1": [
            {"date": "2026-07-24", "isCarriedForward": True},
            {"date": "2026-07-25", "is_carried_forward": True},
        ]
    }
    assert pokemon_snapshot_builders.observed_top_chase_dates(histories) == []


def _top_chase_dashboard_meta(monkeypatch, *, price_history, built_at, latest_market_date):
    histories = {
        scope: [{"date": latest_market_date, "setValue": 100.0}]
        for scope in ("standard", "hits", "top10")
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
        lambda set_id, limit, days, **_kwargs: {
            "set": {"id": set_id},
            "cards": [
                {"cardVariantId": "variant-1", "name": "Chase", "priceHistory": price_history}
            ],
            "meta": {"warnings": []},
        },
    )
    monkeypatch.setattr(
        pokemon_snapshot_builders, "_build_top_chase_canonical_history_context", lambda *a, **k: {}
    )
    monkeypatch.setattr(
        pokemon_snapshot_builders, "_load_top_chase_histories_from_observations", lambda *a, **k: {}
    )
    monkeypatch.setattr(
        pokemon_snapshot_builders,
        "build_pokemon_set_card_movements_by_window_payload",
        lambda set_id, **_kwargs: _empty_movement_windows_payload(),
    )
    monkeypatch.setattr(pokemon_snapshot_builders, "_load_simulation_performance_history", lambda *_a: [])
    dashboard_row, _rows = pokemon_snapshot_builders.build_market_dashboard_snapshot_rows(
        {"id": "set-1", "name": "Alpha"},
        days=365,
        window="365d",
        client=_Client({"card_variant_price_observations": lambda _q: []}),
        built_at=built_at,
        latest_market_date=latest_market_date,
    )
    return dashboard_row["payload_json"]["meta"]


def test_legacy_observed_date_fields_agree_with_the_authoritative_source_date(monkeypatch):
    """Last real observation July 16, carried forward through July 25.

    Display history may still end July 25; no observed-date field may.
    """
    meta = _top_chase_dashboard_meta(
        monkeypatch,
        price_history=[
            {"date": "2026-07-10", "marketPrice": 100.0},
            {"date": "2026-07-16", "marketPrice": 110.0},
            {"date": "2026-07-20", "marketPrice": 110.0, "isCarriedForward": True},
            {"date": "2026-07-25", "marketPrice": 110.0, "is_carried_forward": True, "isObserved": False},
        ],
        built_at="2026-07-26T02:00:00+00:00",
        latest_market_date="2026-07-25",
    )

    assert meta["topChaseSourceDate"] == "2026-07-16"
    assert meta["topChaseHistoryLatestObservedDate"] == "2026-07-16"
    assert meta["topChaseHistoryFirstObservedDate"] == "2026-07-10"
    # Only July 10 and July 16 are real; forward-fill materializes every other
    # day through the July 25 boundary as explicitly carried-forward.
    assert meta["topChaseObservedPointCount"] == 2
    assert meta["topChaseCarriedForwardPointCount"] == 14
    # No contradictory metadata: the legacy field agrees with the source date.
    assert meta["topChaseHistoryLatestObservedDate"] == meta["topChaseSourceDate"]
    # Stale against the July 25 market boundary.
    assert meta["sectionFreshness"]["sections"]["topChase"]["status"] == "stale"


def test_real_observation_on_the_market_date_reports_current(monkeypatch):
    meta = _top_chase_dashboard_meta(
        monkeypatch,
        price_history=[
            {"date": "2026-07-24", "marketPrice": 100.0},
            {"date": "2026-07-25", "marketPrice": 120.0},
        ],
        built_at="2026-07-26T02:00:00+00:00",
        latest_market_date="2026-07-25",
    )
    assert meta["topChaseSourceDate"] == "2026-07-25"
    assert meta["topChaseHistoryLatestObservedDate"] == "2026-07-25"
    assert meta["topChaseHistoryFirstObservedDate"] == "2026-07-24"
    assert meta["sectionFreshness"]["sections"]["topChase"]["status"] == "current"


def test_history_with_only_carried_forward_points_reports_unavailable_observed_source(monkeypatch):
    meta = _top_chase_dashboard_meta(
        monkeypatch,
        price_history=[
            {"date": "2026-07-24", "marketPrice": 100.0, "isCarriedForward": True},
            {"date": "2026-07-25", "marketPrice": 100.0, "isCarriedForward": True},
        ],
        built_at="2026-07-26T02:00:00+00:00",
        latest_market_date="2026-07-25",
    )
    assert meta["topChaseSourceDate"] is None
    assert meta["topChaseHistoryLatestObservedDate"] is None
    assert meta["topChaseHistoryFirstObservedDate"] is None
    assert meta["sectionFreshness"]["sections"]["topChase"]["status"] == "unavailable"


def test_explicit_is_observed_false_point_is_excluded_even_without_carry_flag(monkeypatch):
    meta = _top_chase_dashboard_meta(
        monkeypatch,
        price_history=[
            {"date": "2026-07-16", "marketPrice": 100.0},
            {"date": "2026-07-25", "marketPrice": 100.0, "isObserved": False},
        ],
        built_at="2026-07-26T02:00:00+00:00",
        latest_market_date="2026-07-25",
    )
    assert meta["topChaseSourceDate"] == "2026-07-16"
    assert meta["topChaseHistoryLatestObservedDate"] == "2026-07-16"
