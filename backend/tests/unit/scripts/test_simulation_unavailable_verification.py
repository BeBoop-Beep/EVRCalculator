"""Strict verification of the COMPLETE simulation-derived surface.

The verifier used to inspect a single freshness key (``simulationDrivers``), so
an unavailable page could mark Opening Profit vs Cost, the outcome distribution
or the simulation metrics ``current`` and still pass strict mode unless the
payload volunteered them under ``carriedForwardSections``. Verification now
walks every known simulation-derived section directly.
"""

import pytest

from backend.db.services.explore_page_service import ExplorePageError
from backend.scripts import pokemon_snapshot_builders
from backend.scripts import refresh_stale_public_snapshots as refresh
from backend.scripts.pokemon_snapshot_builders import (
    SIMULATION_DEPENDENT_SECTIONS,
    SIMULATION_UNAVAILABLE_WARNING,
)
from backend.tests.unit.scripts.test_pokemon_snapshot_builders import _Client


def _unavailable_row(**payload_overrides):
    """A truthful simulation-unavailable page shaped like the real builder's."""
    payload = {
        "target": {"target_type": "set", "target_id": "set-1", "id": "set-1", "name": "Alpha"},
        "summary": {},
        "rankings": [],
        "rip_statistics": {"pack_paths": {}, "normal_pack_states": {}},
        "percentiles": [],
        "distribution_bins": [],
        "threshold_bins": [],
        "top_hits": [],
        "history_trend": [],
        "interpretation": None,
        "pull_rate_assumptions": None,
        "meta": {
            "snapshot": {"type": "pokemon_set_page", "builtAt": "2026-07-26T00:00:00+00:00"},
            "snapshotCompleteness": {"ok": True},
            "sectionFreshness": {"simulationDrivers": {"status": "missing", "dataAsOf": None}},
            "simulationAvailability": {
                "available": False,
                "reason": "No simulation data found for this target",
                "asOfDate": None,
                "unavailableSections": list(SIMULATION_DEPENDENT_SECTIONS),
                "carryForward": False,
                "carriedForwardSections": [],
            },
            "sources": {"simulation_input_cards": "NO_ROW"},
            "warnings": [SIMULATION_UNAVAILABLE_WARNING],
        },
    }
    payload.update(payload_overrides)
    return {"set_id": "set-1", "updated_at": "2026-07-26T00:00:00+00:00", "payload_json": payload}


def _verify(monkeypatch, row):
    monkeypatch.setattr(
        refresh,
        "_read_snapshot_row",
        lambda _c, table, _s, _f: (row if table == "pokemon_set_page_snapshot_latest" else None),
    )
    monkeypatch.setattr(refresh, "_has_known_stale_warning", lambda _w: False)
    monkeypatch.setattr(refresh, "_source_rows_exist_for_set_page", lambda _c, _s: False)
    return refresh._verify_set_page(
        None, {"id": "set-1", "canonical_key": "alpha"}, rankings_updated_at=None
    )


def _label(row, key, entry):
    row["payload_json"]["meta"]["sectionFreshness"][key] = entry
    return row


def _build_real_partial_payload(monkeypatch):
    """The ACTUAL payload build_set_page_snapshot_row emits for a set with no run."""

    def _raise_missing(_target_type, _set_id):
        raise ExplorePageError(
            status_code=404,
            message="No simulation data found for this target",
            code="TARGET_NOT_FOUND",
        )

    monkeypatch.setattr(pokemon_snapshot_builders, "get_explore_page_payload", _raise_missing)
    monkeypatch.setattr(
        pokemon_snapshot_builders, "get_rip_statistics_targets_payload", lambda limit: {"targets": []}
    )
    client = _Client(
        {
            "simulation_input_cards_with_near_mint_price": lambda _q: [],
            "simulation_input_cards": lambda _q: [],
            "pokemon_set_cards_snapshot_latest": lambda _q: [],
            "pokemon_explore_rankings_snapshot_latest": lambda _q: [],
            "explore_rip_statistics_latest": lambda _q: [],
            "simulation_latest_by_target": lambda _q: [],
            "pokemon_set_page_snapshot_latest": lambda _q: [],
        }
    )
    return pokemon_snapshot_builders.build_set_page_snapshot_row(
        {"id": "set-1", "name": "Alpha", "canonical_key": "alpha"}, client=client
    )["payload_json"]


# 1. Valid simulation-unavailable partial page passes.
def test_valid_unavailable_partial_page_passes(monkeypatch):
    assert _verify(monkeypatch, _unavailable_row()) == []


# 2-5. Any simulation-derived section labeled current/fresh fails.
@pytest.mark.parametrize(
    "key",
    [
        "openingProfitVsCost",
        "simulationDrivers",
        "outcomeDistribution",
        "simulationMetrics",
        "historyTrend",
        "pullRateAssumptions",
        "valueStructure",
        "packPaths",
        "simulationSummary",
    ],
)
@pytest.mark.parametrize("status", ["current", "fresh"])
def test_simulation_section_labeled_current_while_unavailable_fails(monkeypatch, key, status):
    row = _label(_unavailable_row(), key, {"status": status, "dataAsOf": "2026-07-26"})
    assert any(f"simulation section {key} labeled {status}" in p for p in _verify(monkeypatch, row))


def test_snake_case_freshness_alias_is_also_rejected(monkeypatch):
    row = _label(_unavailable_row(), "opening_profit_vs_cost", {"status": "current"})
    assert any("opening_profit_vs_cost labeled current" in p for p in _verify(monkeypatch, row))


# 6. A current simulation run id / as-of date must not be advertised.
def test_current_simulation_run_id_while_unavailable_fails(monkeypatch):
    row = _unavailable_row()
    row["payload_json"]["summary"] = {"calculation_run_id": "run-123"}
    assert any("simulation run id run-123 advertised" in p for p in _verify(monkeypatch, row))


def test_simulation_as_of_date_while_unavailable_fails(monkeypatch):
    row = _unavailable_row()
    row["payload_json"]["meta"]["simulationAvailability"]["asOfDate"] = "2026-07-26"
    assert any("asOfDate=2026-07-26 advertised" in p for p in _verify(monkeypatch, row))


# 7-8. Carried-forward content must be stale AND dated.
def test_carried_forward_opvc_marked_stale_with_a_source_date_passes(monkeypatch):
    row = _unavailable_row(openingProfitVsCost={"points": [{"date": "2026-07-17", "ratio": 1.1}]})
    _label(row, "openingProfitVsCost", {"status": "stale", "dataAsOf": "2026-07-17T00:00:00+00:00"})
    availability = row["payload_json"]["meta"]["simulationAvailability"]
    availability["carryForward"] = True
    availability["carriedForwardSections"] = ["openingProfitVsCost"]
    assert _verify(monkeypatch, row) == []


def test_carried_forward_opvc_without_a_source_date_fails(monkeypatch):
    row = _unavailable_row(openingProfitVsCost={"points": [{"date": "2026-07-17", "ratio": 1.1}]})
    _label(row, "openingProfitVsCost", {"status": "stale", "dataAsOf": None})
    assert any("has no source/data-as-of date" in p for p in _verify(monkeypatch, row))


def test_populated_simulation_section_without_stale_labeling_fails(monkeypatch):
    """The case ``carriedForwardSections`` alone could never catch."""
    row = _unavailable_row(openingProfitVsCost={"points": [{"date": "2026-07-17"}]})
    problems = _verify(monkeypatch, row)
    assert any("openingProfitVsCost is populated but not labeled stale" in p for p in problems)


# 9. Missing / malformed unavailable declarations fail.
def test_missing_unavailable_declaration_fails(monkeypatch):
    row = _unavailable_row()
    row["payload_json"]["meta"]["simulationAvailability"]["unavailableSections"] = [
        section for section in SIMULATION_DEPENDENT_SECTIONS if section != "openingProfitVsCost"
    ]
    problems = _verify(monkeypatch, row)
    assert any("missing absent simulation section openingProfitVsCost" in p for p in problems)


def test_empty_unavailable_sections_fails(monkeypatch):
    row = _unavailable_row()
    row["payload_json"]["meta"]["simulationAvailability"]["unavailableSections"] = []
    assert any("unavailableSections must be nonempty" in p for p in _verify(monkeypatch, row))


def test_malformed_availability_metadata_fails(monkeypatch):
    row = _unavailable_row()
    row["payload_json"]["meta"]["simulationAvailability"]["available"] = "no"
    assert any("available must be a boolean" in p for p in _verify(monkeypatch, row))


# 10. Independent market content does not fail because simulation is absent.
def test_independent_set_value_and_cards_content_does_not_fail(monkeypatch):
    row = _unavailable_row(
        cardAppealMarketPriceCorrelation={"pearson": 0.62},
        setValueTrend={"latest": 1234.5, "sourceDate": "2026-07-26"},
    )
    _label(row, "cardAppealValidation", {"status": "fresh", "dataAsOf": "2026-07-26T00:00:00+00:00"})
    _label(row, "decisionSignalRanks", {"status": "fresh", "dataAsOf": "2026-07-26T00:00:00+00:00"})
    assert _verify(monkeypatch, row) == []


# 11-12. The available-simulation contract is unchanged.
def test_available_page_missing_top_hits_still_fails(monkeypatch):
    row = _unavailable_row()
    row["payload_json"]["meta"]["simulationAvailability"]["available"] = True
    row["payload_json"]["meta"]["sources"]["simulation_input_cards"] = "OK"
    assert any("top_hits missing" in p for p in _verify(monkeypatch, row))


def test_available_page_with_invalid_simulation_source_still_fails(monkeypatch):
    row = _unavailable_row(top_hits=[{"name": "Chase", "value": 100.0}])
    row["payload_json"]["meta"]["simulationAvailability"]["available"] = True
    row["payload_json"]["meta"]["sources"]["simulation_input_cards"] = "NO_ROWS"
    assert any("simulation_input_cards source=NO_ROWS" in p for p in _verify(monkeypatch, row))


# Builder -> verifier integration on the REAL partial payload.
def test_real_partial_payload_from_the_builder_passes_strict_verification(monkeypatch):
    payload = _build_real_partial_payload(monkeypatch)
    assert payload["meta"]["simulationAvailability"]["available"] is False
    row = {"set_id": "set-1", "updated_at": "2026-07-26T00:00:00+00:00", "payload_json": payload}
    assert _verify(monkeypatch, row) == []


def test_real_partial_payload_fails_once_a_section_is_relabeled_current(monkeypatch):
    payload = _build_real_partial_payload(monkeypatch)
    payload["meta"]["sectionFreshness"]["openingProfitVsCost"] = {"status": "current"}
    row = {"set_id": "set-1", "updated_at": "2026-07-26T00:00:00+00:00", "payload_json": payload}
    assert any("openingProfitVsCost labeled current" in p for p in _verify(monkeypatch, row))
