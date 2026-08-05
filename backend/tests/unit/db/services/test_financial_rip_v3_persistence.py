"""Financial RIP V3 — persistence contract tests.

The claims under test:

  * the V2 fields are byte-for-byte what they were before V3 existed,
  * every declared V3 column is produced by the payload builder and read back by
    the select contract (insert and select can never drift),
  * the complete JSONB audit document is persisted, as JSON-safe primitives,
  * a run without V3 stores NULLs rather than a fabricated score,
  * a ready-status payload that fails validation is REJECTED before it reaches
    the database, because a partially-populated ready row would rank and render
    and be wrong.
"""

from __future__ import annotations

import json
from unittest.mock import patch

import numpy as np
import pytest

from backend.calculations.evr.derived_metrics import compute_all_derived_metrics
from backend.calculations.evr.financial_rip_v3 import build_financial_rip_v3
from backend.calculations.evr.financial_rip_v3_config import FINANCIAL_RIP_V3_VERSION
from backend.db.repositories.calculation_runs_repository import (
    DERIVED_METRIC_FIELDS,
    FINANCIAL_RIP_V3_METRIC_FIELDS,
)
from backend.db.services.calculation_run_persistence_service import (
    _build_financial_rip_v3_persistence_payload,
    _build_flat_derived_metrics_payload,
    _json_safe_primitives,
    persist_simulation_derived_metrics,
)

PACK_COST = 4.99
N = 20_000


def make_values() -> np.ndarray:
    bulk = np.full(int(N * 0.90), 1.0)
    mid = np.full(int(N * 0.05), 6.0)
    top = np.full(int(N * 0.04), 40.0)
    jackpot = np.full(N - bulk.size - mid.size - top.size, 500.0)
    return np.concatenate([bulk, mid, top, jackpot])


def make_derived() -> dict:
    return compute_all_derived_metrics(
        list(make_values()),
        PACK_COST,
        card_ev_contributions={"a": 3.0, "b": 1.5, "c": 0.9, "d": 0.4, "e": 0.2},
        total_pack_ev=6.0,
        hit_ev=5.0,
        hit_cards_count=5,
    )


# ---------------------------------------------------------------------------
# Insert / select synchronization
# ---------------------------------------------------------------------------

def test_every_declared_v3_column_appears_in_the_insert_payload():
    payload = _build_flat_derived_metrics_payload(make_derived())
    for field in FINANCIAL_RIP_V3_METRIC_FIELDS:
        assert field in payload, f"{field} is declared but never written"


def test_insert_and_select_field_lists_stay_synchronized():
    payload = _build_flat_derived_metrics_payload(make_derived())
    assert set(payload) == set(DERIVED_METRIC_FIELDS), (
        "the insert payload and the select contract have drifted: "
        f"insert-only={sorted(set(payload) - set(DERIVED_METRIC_FIELDS))} "
        f"select-only={sorted(set(DERIVED_METRIC_FIELDS) - set(payload))}"
    )


def test_v3_fields_are_a_strict_superset_addition_not_a_v2_rename():
    for field in FINANCIAL_RIP_V3_METRIC_FIELDS:
        assert field.startswith("financial_rip_v3_")
    # None of the V2 columns were repurposed.
    for legacy in (
        "pack_score",
        "profit_score",
        "safety_score",
        "stability_score",
        "desirability_score",
        "score_version",
        "normalization_mode",
    ):
        assert legacy in DERIVED_METRIC_FIELDS
        assert legacy not in FINANCIAL_RIP_V3_METRIC_FIELDS


# ---------------------------------------------------------------------------
# V2 is untouched
# ---------------------------------------------------------------------------

def test_v2_fields_are_unchanged_by_the_presence_of_v3():
    derived = make_derived()
    with_v3 = _build_flat_derived_metrics_payload(derived)

    stripped = dict(derived)
    stripped.pop("financial_rip_v3")
    without_v3 = _build_flat_derived_metrics_payload(stripped)

    v2_keys = [key for key in without_v3 if not key.startswith("financial_rip_v3_")]
    for key in v2_keys:
        assert with_v3[key] == without_v3[key], f"{key} changed when V3 was added"


def test_a_run_without_v3_stores_nulls_not_a_fabricated_score():
    derived = dict(make_derived())
    derived.pop("financial_rip_v3")
    payload = _build_flat_derived_metrics_payload(derived)
    for field in FINANCIAL_RIP_V3_METRIC_FIELDS:
        assert payload[field] is None
    # And V2 still persisted normally.
    assert payload["pack_score"] is not None


# ---------------------------------------------------------------------------
# Scalar projection correctness
# ---------------------------------------------------------------------------

def test_v3_scalar_columns_project_the_authoritative_payload_exactly():
    derived = make_derived()
    authoritative = derived["financial_rip_v3"]
    payload = _build_flat_derived_metrics_payload(derived)

    assert payload["financial_rip_v3_score"] == authoritative["score"]
    assert payload["financial_rip_v3_score_version"] == FINANCIAL_RIP_V3_VERSION
    assert payload["financial_rip_v3_status"] == "ready"
    assert payload["financial_rip_v3_rankable"] is True

    components = authoritative["components"]
    assert payload["financial_rip_v3_true_win_frequency_score"] == components["true_win_frequency"]["score"]
    assert payload["financial_rip_v3_typical_retention_score"] == components["typical_retention"]["score"]
    assert payload["financial_rip_v3_loss_resilience_score"] == components["loss_resilience"]["score"]
    assert payload["financial_rip_v3_realistic_upside_score"] == components["realistic_upside"]["score"]
    assert payload["financial_rip_v3_jackpot_upside_score"] == components["jackpot_upside"]["score"]
    assert (
        payload["financial_rip_v3_base_economic_efficiency_score"]
        == components["base_economic_efficiency"]["score"]
    )

    assert (
        payload["financial_rip_v3_realistic_tail_mean_value"]
        == components["realistic_upside"]["raw"]["realisticTailMeanValue"]
    )
    assert (
        payload["financial_rip_v3_jackpot_tail_mean_value"]
        == components["jackpot_upside"]["raw"]["jackpotTailMeanValue"]
    )
    assert (
        payload["financial_rip_v3_hard_loss_probability"]
        == components["loss_resilience"]["raw"]["hardLossProbability"]
    )


def test_full_json_payload_is_persisted_and_json_serializable():
    payload = _build_flat_derived_metrics_payload(make_derived())
    document = payload["financial_rip_v3_payload"]
    assert isinstance(document, dict)
    assert document["scoreVersion"] == FINANCIAL_RIP_V3_VERSION
    assert set(document["components"]) == {
        "true_win_frequency",
        "typical_retention",
        "loss_resilience",
        "realistic_upside",
        "jackpot_upside",
        "base_economic_efficiency",
    }
    # The sub-scores, normalization records and tail selection all survive.
    assert document["audit"]["normalizedInputs"]["p95_threshold_ratio"]["transformVersion"]
    assert document["distributionDisclosures"]["tailSelection"]["method"] == (
        "empirical_rank_exact_mass_v1"
    )
    json.dumps(payload)


def test_numpy_scalars_are_normalized_to_builtin_primitives():
    """A numpy.float64 in a JSONB insert fails far from where it was created."""
    hostile = {
        "score": np.float64(41.5),
        "count": np.int64(7),
        "nested": {"values": np.array([1.0, 2.0])},
        "flag": True,
        "text": "ok",
        "none": None,
    }
    cleaned = _json_safe_primitives(hostile)
    assert type(cleaned["score"]) is float
    assert type(cleaned["count"]) is int
    assert cleaned["nested"]["values"] == [1.0, 2.0]
    json.dumps(cleaned)


def test_top2_ev_share_is_persisted_for_the_depth_diagnostic():
    payload = _build_flat_derived_metrics_payload(make_derived())
    assert "top2_ev_share" in payload
    assert payload["top2_ev_share"] is not None
    # Sanity: top1 <= top2 <= top3.
    assert payload["top1_ev_share"] <= payload["top2_ev_share"] <= payload["top3_ev_share"]


# ---------------------------------------------------------------------------
# Invalid ready payloads fail BEFORE persistence
# ---------------------------------------------------------------------------

def test_invalid_ready_status_payload_is_rejected_before_persistence():
    derived = make_derived()
    tampered = json.loads(json.dumps(derived["financial_rip_v3"]))
    tampered["score"] = 99.0  # no longer reconstructs from the contributions
    derived = {**derived, "financial_rip_v3": tampered}

    with pytest.raises(ValueError, match="failed validation"):
        _build_financial_rip_v3_persistence_payload(derived)


def test_ready_payload_missing_a_component_is_rejected():
    derived = make_derived()
    tampered = json.loads(json.dumps(derived["financial_rip_v3"]))
    del tampered["components"]["loss_resilience"]
    with pytest.raises(ValueError, match="failed validation"):
        _build_financial_rip_v3_persistence_payload({**derived, "financial_rip_v3": tampered})


def test_unavailable_payload_persists_its_reason_without_a_score():
    unavailable = build_financial_rip_v3(make_values(), 0.0)
    assert unavailable["status"] == "unavailable"
    payload = _build_financial_rip_v3_persistence_payload({"financial_rip_v3": unavailable})
    assert payload["financial_rip_v3_score"] is None
    assert payload["financial_rip_v3_status"] == "unavailable"
    assert payload["financial_rip_v3_rankable"] is False
    assert payload["financial_rip_v3_payload"]["statusReason"] == "invalid_pack_cost"


# ---------------------------------------------------------------------------
# Run identity survives persistence
# ---------------------------------------------------------------------------

@patch("backend.db.services.calculation_run_persistence_service.create_simulation_derived_metrics")
def test_run_identity_and_v3_payload_reach_the_repository_together(mock_create):
    mock_create.return_value = [{"calculation_run_id": "run-42"}]
    derived = make_derived()

    persist_simulation_derived_metrics(run_id="run-42", derived=derived)

    mock_create.assert_called_once()
    run_id, payload = mock_create.call_args[0]
    assert run_id == "run-42"
    # The score, the raw metrics and the simulation count are all from the SAME
    # payload object, so one insert cannot mix two runs.
    assert payload["financial_rip_v3_score"] == derived["financial_rip_v3"]["score"]
    assert payload["financial_rip_v3_simulation_count"] == (
        derived["financial_rip_v3"]["estimationDiagnostics"]["simulationCount"]
    )
    assert payload["financial_rip_v3_payload"]["score"] == payload["financial_rip_v3_score"]


# ---------------------------------------------------------------------------
# End-to-end: builder -> projection -> ACTUAL insert payload
# ---------------------------------------------------------------------------
# The test above mocks `create_simulation_derived_metrics`, which is exactly the
# function that used to discard the V3 block. Mocking it proves the projection is
# correct and proves nothing about what is written. This test carries a ready V3
# result all the way to the argument handed to Supabase, so the writer is inside
# the assertion rather than outside it.

def test_ready_v3_survives_builder_projection_and_repository_insert():
    """A ready V3 result must reach the database payload intact, end to end."""
    from backend.db.repositories import calculation_runs_repository as repo

    derived = make_derived()
    assert derived["financial_rip_v3"]["status"] == "ready"

    with patch.object(repo, "_insert_required_payload") as mock_insert:
        mock_insert.return_value = {"id": "row-e2e"}
        persist_simulation_derived_metrics(run_id="run-e2e", derived=derived)
        mock_insert.assert_called_once()
        table_name, insert_payload, _context = mock_insert.call_args[0]

    assert table_name == "simulation_derived_metrics"
    assert insert_payload["calculation_run_id"] == "run-e2e"

    # Every declared V3 column is present AND carries a real value - the exact
    # condition that was false in production while the insert still succeeded.
    authoritative = derived["financial_rip_v3"]
    for field in FINANCIAL_RIP_V3_METRIC_FIELDS:
        assert field in insert_payload, f"{field} never reached the insert"
        assert insert_payload[field] is not None, f"{field} reached the insert as NULL"

    assert insert_payload["financial_rip_v3_score"] == authoritative["score"]
    assert insert_payload["financial_rip_v3_score_version"] == FINANCIAL_RIP_V3_VERSION
    assert insert_payload["financial_rip_v3_status"] == "ready"
    assert insert_payload["financial_rip_v3_rankable"] is True

    # The JSONB document arrives as a document, and is the same score the scalar
    # column carries - so the projection and the audit payload cannot disagree.
    document = insert_payload["financial_rip_v3_payload"]
    assert isinstance(document, dict)
    assert document["score"] == insert_payload["financial_rip_v3_score"]
    json.dumps(document)

    # The additive Depth-and-Robustness diagnostic travels with it.
    assert insert_payload["top2_ev_share"] is not None


def test_end_to_end_insert_payload_matches_the_declared_column_contract():
    """No declared column missing, no undeclared column invented."""
    from backend.db.repositories import calculation_runs_repository as repo

    with patch.object(repo, "_insert_required_payload") as mock_insert:
        mock_insert.return_value = {"id": "row-e2e-2"}
        persist_simulation_derived_metrics(run_id="run-e2e-2", derived=make_derived())
        _table, insert_payload, _context = mock_insert.call_args[0]

    assert set(insert_payload) == set(DERIVED_METRIC_FIELDS) | {"calculation_run_id"}
