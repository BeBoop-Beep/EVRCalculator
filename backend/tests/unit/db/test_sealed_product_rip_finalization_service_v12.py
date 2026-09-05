"""Overall RIP V12 shadow-lineage finalization tests.

Covers Phase 14 A/C/H of the V12 persistence/publication implementation:
finalization correctness, authority coherence (including the exploit attempt
of an arbitrary "latest" Accessibility row slipping through), and V10/V9
regression (unchanged by V12's addition).
"""

from __future__ import annotations

import pytest

from backend.db.services.sealed_product_rip_finalization_service import (
    OVERALL_RIP_V12_STATUS_AUTHORITY_MISMATCH,
    _enrichment_for,
    _overall_rip_v12_for,
    finalize_sealed_product_rip,
)
from backend.desirability.scoring_config import OVERALL_RIP_V12_VERSION
from backend.desirability.chase_accessibility import CHASE_ACCESSIBILITY_VERSION as _CAV

RUN_A = "11111111-1111-1111-1111-111111111111"
RUN_B = "22222222-2222-2222-2222-222222222222"

APPEAL = {"score": 60.0, "version": "collector_appeal_v5_contextual_roster_h_only_d_baseline_up4_down2"}


from backend.calculations.evr.financial_rip_v4_config import FINANCIAL_RIP_V4_VERSION


def _row(financial_v4=39.5, run_id=RUN_A, financial_v4_version=FINANCIAL_RIP_V4_VERSION):
    return {"financial_rip_v3_score": 41.0, "financial_rip_v4_score": financial_v4,
            "financial_rip_v4_version": financial_v4_version,
            "calculation_run_id": run_id}


# --------------------------------------------------------------------------
# A. Finalization: valid inputs -> exact V12; missing A -> unavailable;
#    V10 untouched either way.
# --------------------------------------------------------------------------

def test_v12_exact_score_with_coherent_accessibility():
    accessibility_row = {"calculation_run_id": RUN_A, "status": "ready", "accessibility": 0.002, "version": _CAV}
    enrichment = _enrichment_for(
        _row(), APPEAL, accessibility_row=accessibility_row, expected_run_id=RUN_A
    )

    financial = 39.5
    a_score = 100.0 * 0.002 / (0.002 + 0.002)  # = 50.0
    expected = 0.86 * financial + 0.04 * a_score + 0.10 * 60.0

    assert enrichment["overall_rip_v12_score"] == pytest.approx(round(expected, 4))
    assert enrichment["overall_rip_v12_version"] == OVERALL_RIP_V12_VERSION
    assert enrichment["overall_rip_v12_rankable"] is True
    assert enrichment["overall_rip_v12_status"] == "ready"


def test_v12_unavailable_when_accessibility_missing_v10_still_written():
    enrichment = _enrichment_for(
        _row(), APPEAL, accessibility_row=None, expected_run_id=RUN_A
    )

    assert enrichment["overall_rip_v12_score"] is None
    assert enrichment["overall_rip_v12_rankable"] is False
    assert enrichment["overall_rip_v12_status"] == "unavailable_missing_input"

    # V10 completely unaffected by V12's absence.
    assert enrichment["overall_rip_v10_score"] == pytest.approx(0.90 * 39.5 + 0.10 * 60.0)
    assert enrichment["overall_rip_v10_rankable"] is True


def test_v12_unavailable_when_accessibility_row_not_ready():
    accessibility_row = {"calculation_run_id": RUN_A, "status": "unavailable_no_drawable_universe",
                          "accessibility": None}
    enrichment = _enrichment_for(
        _row(), APPEAL, accessibility_row=accessibility_row, expected_run_id=RUN_A
    )
    assert enrichment["overall_rip_v12_score"] is None
    assert enrichment["overall_rip_v12_status"] == "unavailable_missing_input"


def test_v12_never_synthesizes_zero_for_missing_accessibility():
    enrichment = _enrichment_for(_row(), APPEAL, accessibility_row=None, expected_run_id=RUN_A)
    assert enrichment["overall_rip_v12_score"] != 0.0
    assert enrichment["overall_rip_v12_score"] is None


# --------------------------------------------------------------------------
# C. Authority: coherent run passes; stale/mismatched Accessibility fails;
#    an arbitrary "latest" row cannot slip through.
# --------------------------------------------------------------------------

def test_authority_mismatch_rejected_even_though_row_is_ready_and_valid():
    """The exploit attempt: an Accessibility row that is fully `ready`, with a
    perfectly valid value, but built from a DIFFERENT calculation_run_id than
    this product row's coherent cohort run. Must be refused, never accepted as
    "the latest available" Accessibility.
    """
    stale_but_valid_row = {"calculation_run_id": RUN_B, "status": "ready", "accessibility": 0.005}

    result = _overall_rip_v12_for(
        _row(run_id=RUN_A), 60.0, stale_but_valid_row, expected_run_id=RUN_A
    )

    assert result["score"] is None
    assert result["rankable"] is False
    assert result["status"] == OVERALL_RIP_V12_STATUS_AUTHORITY_MISMATCH
    assert "chase_accessibility_v1" in result["missingInputs"]


def test_authority_coherent_run_passes():
    coherent_row = {"calculation_run_id": RUN_A, "status": "ready", "accessibility": 0.002, "version": _CAV}
    result = _overall_rip_v12_for(_row(run_id=RUN_A), 60.0, coherent_row, expected_run_id=RUN_A)
    assert result["status"] == "ready"
    assert result["score"] is not None


def test_authority_no_expected_run_id_refuses_rather_than_guessing():
    coherent_row = {"calculation_run_id": RUN_A, "status": "ready", "accessibility": 0.002, "version": _CAV}
    result = _overall_rip_v12_for(_row(run_id=RUN_A), 60.0, coherent_row, expected_run_id=None)
    assert result["status"] == OVERALL_RIP_V12_STATUS_AUTHORITY_MISMATCH
    assert result["score"] is None


# --------------------------------------------------------------------------
# I / regression: V9 and V10 arithmetic exactly as before V12 was added.
# --------------------------------------------------------------------------

def test_v9_v10_arithmetic_unchanged_by_v12_presence():
    accessibility_row = {"calculation_run_id": RUN_A, "status": "ready", "accessibility": 0.002, "version": _CAV}
    enrichment = _enrichment_for(
        _row(financial_v4=40.0), APPEAL, accessibility_row=accessibility_row, expected_run_id=RUN_A
    )
    assert enrichment["overall_rip_v10_score"] == pytest.approx(0.90 * 40.0 + 0.10 * 60.0)


def test_finalize_sealed_product_rip_batches_accessibility_reads_once():
    """H. Performance: exactly ONE accessibility_reader_fn call per finalization
    run, regardless of how many product rows are in the cohort (no N+1)."""
    calls = {"count": 0}

    def fake_accessibility_reader(set_ids):
        calls["count"] += 1
        return {
            "set-1": {"calculation_run_id": RUN_A, "status": "ready", "accessibility": 0.002, "version": _CAV},
        }

    from backend.desirability.collector_appeal import COLLECTOR_APPEAL_V5_VERSION

    def fake_bundle_fn(force_refresh=True):
        return {"payloads": {"set-1": {"collectorAppeal": {
                                        "score": 60.0,
                                        "version": COLLECTOR_APPEAL_V5_VERSION}}},
                "identity": {"collectorAppealVersion": COLLECTOR_APPEAL_V5_VERSION}}

    def fake_read_rows_fn(run_ids):
        return [
            {"id": "row-1", "set_id": "set-1", "calculation_run_id": RUN_A,
             "financial_rip_v3_score": 41.0, "financial_rip_v4_score": 39.5,
             "financial_rip_v4_version": FINANCIAL_RIP_V4_VERSION},
            {"id": "row-2", "set_id": "set-1", "calculation_run_id": RUN_A,
             "financial_rip_v3_score": 42.0, "financial_rip_v4_score": 41.0,
             "financial_rip_v4_version": FINANCIAL_RIP_V4_VERSION},
            {"id": "row-3", "set_id": "set-1", "calculation_run_id": RUN_A,
             "financial_rip_v3_score": 43.0, "financial_rip_v4_score": 42.0,
             "financial_rip_v4_version": FINANCIAL_RIP_V4_VERSION},
        ]

    writes = []

    def fake_update_fn(row_id, values):
        writes.append((row_id, values))
        return [values]

    class _FakeGate:
        def __init__(self):
            self.error = None
            self.market_date = "2026-09-02"
            self.ok = True
            self.statuses = [
                _Status(set_id="set-1", calculation_run_id=RUN_A, status="current", canonical_key="set-1"),
            ]

    class _Status:
        def __init__(self, set_id, calculation_run_id, status, canonical_key):
            self.set_id = set_id
            self.calculation_run_id = calculation_run_id
            self.status = status
            self.canonical_key = canonical_key

    import backend.db.services.sealed_product_rip_finalization_service as svc

    original = svc.evaluate_opening_simulation_freshness
    svc.evaluate_opening_simulation_freshness = lambda *a, **k: _FakeGate()
    try:
        report = finalize_sealed_product_rip(
            client=None,
            market_date="2026-09-02",
            bundle_fn=fake_bundle_fn,
            read_rows_fn=fake_read_rows_fn,
            update_fn=fake_update_fn,
            accessibility_reader_fn=fake_accessibility_reader,
        )
    finally:
        svc.evaluate_opening_simulation_freshness = original

    assert report["status"] == "ok"
    assert report["rowsFinalized"] == 3
    # exactly ONE accessibility batch read for 3 product rows in 1 set.
    assert calls["count"] == 1
    assert len(writes) == 3
    for _row_id, values in writes:
        assert values["overall_rip_v12_status"] == "ready"
        assert values["overall_rip_v12_score"] is not None


# --------------------------------------------------------------------------
# Phase 13: version alignment checks - V12 requires exactly Financial V4,
# Chase Accessibility V1; a mismatch is a hard refusal, never a coerced read.
# --------------------------------------------------------------------------

def test_wrong_financial_version_is_rejected_even_with_valid_score():
    row = _row(financial_v4_version="financial_rip_v3_...")  # wrong lineage
    accessibility_row = {"calculation_run_id": RUN_A, "status": "ready",
                          "accessibility": 0.002, "version": _CAV}
    result = _overall_rip_v12_for(row, 60.0, accessibility_row, expected_run_id=RUN_A)
    assert result["score"] is None
    assert result["status"] == "unavailable_missing_input"
    assert "financial_rip_v4" in result["missingInputs"]


def test_wrong_accessibility_version_is_rejected_even_with_valid_value():
    accessibility_row = {"calculation_run_id": RUN_A, "status": "ready", "accessibility": 0.002,
                          "version": "chase_opportunity_v1_core_k_saturating_100_k10"}
    result = _overall_rip_v12_for(_row(run_id=RUN_A), 60.0, accessibility_row, expected_run_id=RUN_A)
    assert result["score"] is None
    assert result["status"] == "unavailable_missing_input"
    assert "chase_accessibility_v1" in result["missingInputs"]


def test_correct_accessibility_version_is_accepted():
    accessibility_row = {"calculation_run_id": RUN_A, "status": "ready", "accessibility": 0.002,
                          "version": _CAV}
    result = _overall_rip_v12_for(_row(run_id=RUN_A), 60.0, accessibility_row, expected_run_id=RUN_A)
    assert result["status"] == "ready"
    assert result["score"] is not None


# --------------------------------------------------------------------------
# I. Regression: the default accessibility_reader_fn must resolve the real
#    Supabase client module. A prior defect imported from the non-existent
#    `backend.clients.supabase_client` (the actual module lives at
#    `backend.db.clients.supabase_client`), which raised ModuleNotFoundError
#    the first time production reached this branch - only when NO
#    accessibility_reader_fn override was supplied, so every other test in
#    this file (which all pass one explicitly) never exercised it.
# --------------------------------------------------------------------------

def test_default_accessibility_reader_resolves_real_supabase_client_module(monkeypatch):
    import backend.db.services.sealed_product_rip_finalization_service as svc

    class _FakeFreshnessReport:
        error = "no_current_runs"
        market_date = "2026-09-04"
        statuses: List[Any] = []
        ok = False

    monkeypatch.setattr(
        svc, "evaluate_opening_simulation_freshness", lambda *a, **k: _FakeFreshnessReport()
    )

    # accessibility_reader_fn intentionally omitted -> forces the default
    # `from backend.db.clients.supabase_client import supabase` branch to run.
    # Before the fix this raised ModuleNotFoundError instead of returning.
    result = finalize_sealed_product_rip(
        client=object(),
        market_date="2026-09-04",
        bundle_fn=lambda *a, **k: {},
        read_rows_fn=lambda *a, **k: [],
        update_fn=lambda *a, **k: None,
    )

    assert result["status"] == svc.STATUS_CANNOT_START
    assert result["error"] == "no_current_runs"
