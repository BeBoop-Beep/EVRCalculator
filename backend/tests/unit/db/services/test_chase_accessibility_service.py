"""Chase Accessibility V1 builder, read model and publication gate."""

from __future__ import annotations

import pytest

from backend.db.services import chase_accessibility_service as svc
from backend.desirability.chase_accessibility import (
    CHASE_ACCESSIBILITY_VERSION, MIN_MAPPED_HC_MASS, STATUS_NO_PULL_MODEL, STATUS_READY,
)


class _Response:
    def __init__(self, data):
        self.data = data


class _Query:
    def __init__(self, rows, recorder):
        self._rows = rows
        self._recorder = recorder

    def select(self, *_args, **_kwargs):
        return self

    def eq(self, column, value):
        self._recorder.setdefault("eq", []).append((column, value))
        return self

    def gt(self, column, value):
        self._recorder.setdefault("gt", []).append((column, value))
        return self

    def order(self, *_args, **_kwargs):
        return self

    def limit(self, *_args, **_kwargs):
        return self

    def range(self, start, end):
        self._recorder.setdefault("range", []).append((start, end))
        self._slice = (start, end)
        return self

    def upsert(self, payload, **kwargs):
        self._recorder["upsert"] = (payload, kwargs)
        self._rows = [payload]
        return self

    def execute(self):
        start, end = getattr(self, "_slice", (0, len(self._rows)))
        return _Response(self._rows[start:end + 1])


class _Client:
    def __init__(self, rows):
        self._rows = rows
        self.recorder = {}

    def table(self, name):
        self.recorder.setdefault("tables", []).append(name)
        return _Query(list(self._rows), self.recorder)


def _variant(i, price, probability, run="run-1"):
    return {"calculation_run_id": run, "set_id": "set-1",
            "card_variant_id": "v%d" % i, "price_used": price,
            "modeled_probability": probability, "pull_count": 5,
            "pack_presence_count": 5, "simulation_count": 100,
            "effective_pull_rate": (1.0 / probability) if probability else None}


# --------------------------------------------------------------------------
# Loader
# --------------------------------------------------------------------------

def test_the_loader_filters_to_drawable_variants_in_the_query():
    client = _Client([_variant(0, 10.0, 0.1)])
    svc.load_drawable_variants(client, calculation_run_id="run-1")
    assert ("pull_count", 0) in client.recorder["gt"]
    assert ("calculation_run_id", "run-1") in client.recorder["eq"]


def test_the_loader_pages_past_the_thousand_row_cap():
    client = _Client([_variant(i, 10.0, 0.1) for i in range(1500)])
    rows = svc.load_drawable_variants(client, calculation_run_id="run-1")
    assert len(rows) == 1500
    assert len(client.recorder["range"]) == 2


# --------------------------------------------------------------------------
# Builder
# --------------------------------------------------------------------------

def test_the_builder_produces_a_ready_row_for_a_supported_set():
    client = _Client([_variant(i, 10.0 * (i + 1), 0.01) for i in range(5)])
    row = svc.build_chase_accessibility_snapshot_row(
        set_id="set-1", calculation_run_id="run-1", client=client,
        market_date="2026-08-31")
    assert row["status"] == STATUS_READY
    assert row["accessibility"] == pytest.approx(0.01)
    assert row["chase_depth"] is not None
    assert row["mapped_hc_mass"] == pytest.approx(1.0)
    assert row["version"] == CHASE_ACCESSIBILITY_VERSION
    assert row["market_date"] == "2026-08-31"
    assert row["calculation_run_id"] == "run-1"


def test_the_builder_is_idempotent():
    client = _Client([_variant(i, 10.0 * (i + 1), 0.02) for i in range(4)])
    first = svc.build_chase_accessibility_snapshot_row(
        set_id="set-1", calculation_run_id="run-1", client=client)
    second = svc.build_chase_accessibility_snapshot_row(
        set_id="set-1", calculation_run_id="run-1", client=_Client(
            [_variant(i, 10.0 * (i + 1), 0.02) for i in range(4)]))
    assert first["accessibility"] == second["accessibility"]
    assert first["chase_depth"] == second["chase_depth"]


def test_a_set_with_no_run_builds_an_explicit_unavailable_row():
    row = svc.build_chase_accessibility_snapshot_row(
        set_id="set-1", calculation_run_id=None, client=_Client([]))
    assert row["status"] == STATUS_NO_PULL_MODEL
    assert row["accessibility"] is None
    assert row["chase_depth"] is None
    assert row["set_id"] == "set-1"


def test_a_run_with_no_drawable_variants_is_unavailable_not_zero():
    row = svc.build_chase_accessibility_snapshot_row(
        set_id="set-1", calculation_run_id="run-1", client=_Client([]))
    assert row["status"] == STATUS_NO_PULL_MODEL
    assert row["accessibility"] is None


def test_the_builder_requires_a_set_id():
    with pytest.raises(ValueError):
        svc.build_chase_accessibility_snapshot_row(
            set_id=None, calculation_run_id="run-1", client=_Client([]))


def test_the_builder_never_reads_a_sealed_product_table():
    client = _Client([_variant(i, 10.0, 0.1) for i in range(3)])
    svc.build_chase_accessibility_snapshot_row(
        set_id="set-1", calculation_run_id="run-1", client=client)
    for table in client.recorder["tables"]:
        assert "sealed" not in table
        assert "product" not in table


# --------------------------------------------------------------------------
# Read model
# --------------------------------------------------------------------------

def test_projection_exposes_the_documented_fields():
    row = {"accessibility": 0.0037, "chase_depth": 3.9, "mapped_hc_mass": 1.0,
           "status": STATUS_READY, "version": CHASE_ACCESSIBILITY_VERSION,
           "calculation_run_id": "run-1", "market_date": "2026-08-31"}
    projected = svc.project_chase_accessibility(row)
    for field in ("chaseAccessibility", "chaseAccessibilityPct",
                  "chaseAccessibilityStatus", "chaseAccessibilityVersion",
                  "chaseDepth", "mappedHcMass"):
        assert field in projected
    assert projected["chaseAccessibility"] == pytest.approx(0.0037)
    assert projected["chaseAccessibilityPct"] == pytest.approx(0.37)


def test_projection_does_not_leak_internal_diagnostics():
    row = {"accessibility": 0.0037, "chase_depth": 3.9, "mapped_hc_mass": 1.0,
           "status": STATUS_READY, "version": CHASE_ACCESSIBILITY_VERSION,
           "eligible_variant_count": 406, "parity_delta": 1e-19}
    projected = svc.project_chase_accessibility(row)
    assert "eligibleVariantCount" not in projected
    assert "parityDelta" not in projected


def test_an_unsupported_set_projects_null_not_zero():
    projected = svc.project_chase_accessibility(None)
    assert projected["chaseAccessibility"] is None
    assert projected["chaseAccessibilityPct"] is None
    assert projected["chaseAccessibilityStatus"] == STATUS_NO_PULL_MODEL
    assert projected["chaseAccessibility"] is not 0
    assert projected["chaseDepth"] is None


def test_a_measured_zero_projects_as_zero_not_null():
    projected = svc.project_chase_accessibility(
        {"accessibility": 0.0, "chase_depth": 2.0, "status": STATUS_READY,
         "version": CHASE_ACCESSIBILITY_VERSION, "mapped_hc_mass": 1.0})
    assert projected["chaseAccessibility"] == 0.0
    assert projected["chaseAccessibility"] is not None
    assert projected["chaseAccessibilityPct"] == 0.0


# --------------------------------------------------------------------------
# Publication gate
# --------------------------------------------------------------------------

READY_ROW = {"set_id": "s1", "status": STATUS_READY, "accessibility": 0.004,
             "mapped_hc_mass": 1.0, "version": CHASE_ACCESSIBILITY_VERSION,
             "calculation_run_id": "run-1"}


def test_a_supported_set_with_a_good_row_does_not_block_publication():
    assert svc.publication_integrity_failures(
        [READY_ROW], simulation_supported_set_ids=["s1"]) == []


def test_an_unsupported_set_never_blocks_publication():
    """Vintage sets have no pull model. That is a model boundary, not a failure."""
    row = {"set_id": "s2", "status": STATUS_NO_PULL_MODEL, "accessibility": None,
           "mapped_hc_mass": None, "version": CHASE_ACCESSIBILITY_VERSION}
    assert svc.publication_integrity_failures(
        [READY_ROW, row], simulation_supported_set_ids=["s1"]) == []


def test_a_missing_row_for_a_supported_set_is_an_integrity_error():
    failures = svc.publication_integrity_failures(
        [], simulation_supported_set_ids=["s1"])
    assert [f["reason"] for f in failures] == ["missing_chase_accessibility_row"]


def test_a_supported_set_that_is_not_ready_is_an_integrity_error():
    row = dict(READY_ROW, status="chase_accessibility_insufficient_probability_coverage",
               accessibility=None)
    failures = svc.publication_integrity_failures(
        [row], simulation_supported_set_ids=["s1"])
    assert any(f["reason"] == "not_ready" for f in failures)


def test_a_wrong_model_version_is_rejected():
    row = dict(READY_ROW, version="chase_opportunity_v1_core_k_saturating_100_k10")
    failures = svc.publication_integrity_failures(
        [row], simulation_supported_set_ids=["s1"])
    assert any(f["reason"] == "wrong_model_version" for f in failures)


def test_insufficient_mapped_mass_is_rejected_even_if_marked_ready():
    row = dict(READY_ROW, mapped_hc_mass=0.98)
    failures = svc.publication_integrity_failures(
        [row], simulation_supported_set_ids=["s1"])
    assert any(f["reason"] == "insufficient_mapped_hc_mass" for f in failures)


def test_a_stale_calculation_run_is_rejected():
    failures = svc.publication_integrity_failures(
        [READY_ROW], simulation_supported_set_ids=["s1"],
        expected_run_by_set={"s1": "run-2"})
    assert any(f["reason"] == "stale_calculation_run" for f in failures)


def test_a_matching_calculation_run_is_accepted():
    assert svc.publication_integrity_failures(
        [READY_ROW], simulation_supported_set_ids=["s1"],
        expected_run_by_set={"s1": "run-1"}) == []


def test_the_gate_threshold_is_the_module_constant_not_a_literal():
    assert MIN_MAPPED_HC_MASS == 0.99
