"""The `simulation_derived_metrics` INSERT contract.

WHY THIS FILE EXISTS
--------------------
`create_simulation_derived_metrics` used to build its insert payload from a
hand-written dict literal that omitted `top2_ev_share` and all 30 Financial RIP
V3 columns. Postgres accepts an insert that does not mention a nullable column,
so the write succeeded and every V3 column stayed NULL - silently, on every run,
with no error and no failing test.

Nothing caught it because the existing coverage stopped one layer too early: the
service-level tests asserted the flat payload was correct and then MOCKED
`create_simulation_derived_metrics` itself. The projection was verified; the
writer that discarded it was not.

These tests assert against the payload that actually reaches Supabase - the
argument to `_insert_required_payload` - which is the only place the omission was
ever observable.
"""

from __future__ import annotations

import json
from collections.abc import Mapping
from unittest.mock import patch

import pytest

from backend.db.repositories import calculation_runs_repository as repo
from backend.db.repositories.calculation_runs_repository import (
    DERIVED_METRIC_FIELDS,
    FINANCIAL_RIP_V3_METRIC_FIELDS,
    create_simulation_derived_metrics,
)

RUN_ID = "run-contract-1"


def _v3_payload_document() -> dict:
    """A miniature but structurally real V3 audit document."""
    return {
        "score": 61.25,
        "scoreVersion": "financial_rip_v3_outcome_profile_25_20_15_25_10_5",
        "status": "ready",
        "components": {"true_win_frequency": {"score": 33.3, "weight": 0.25}},
        "audit": {"scoreVerification": {"reconstructed": 61.25}},
    }


def _ready_flat_payload() -> dict:
    """A complete flat payload, as the service layer produces it."""
    payload = {field: None for field in DERIVED_METRIC_FIELDS}
    payload.update(
        {
            # --- V2 fields ---
            "simulated_set_value": 1234.5,
            "simulated_set_value_card_count": 200,
            "hit_ev": 3.5,
            "non_hit_ev": 0.5,
            "cards_tracked": 180,
            "total_card_ev": 4.0,
            "top1_ev_share": 0.30,
            "top2_ev_share": 0.44,
            "top3_ev_share": 0.55,
            "top5_ev_share": 0.66,
            "pack_score": 55.5,
            "profit_score": 60.0,
            "safety_score": 50.0,
            "stability_score": 45.0,
            "score_version": "v2",
            "normalization_mode": "cohort",
            "pack_score_is_placeholder": False,
            "desirability_is_fallback": True,
            "derived_metric_version": "dm-1",
            # --- V3 scalars ---
            "financial_rip_v3_score": 61.25,
            "financial_rip_v3_score_version": "financial_rip_v3_outcome_profile_25_20_15_25_10_5",
            "financial_rip_v3_normalization_version": "financial_rip_v3_fixed_absolute_piecewise_v1",
            "financial_rip_v3_status": "ready",
            "financial_rip_v3_rankable": True,
            "financial_rip_v3_simulation_count": 12000,
            "financial_rip_v3_true_win_frequency_score": 33.3,
            "financial_rip_v3_typical_retention_score": 40.0,
            "financial_rip_v3_loss_resilience_score": 51.0,
            "financial_rip_v3_realistic_upside_score": 72.0,
            "financial_rip_v3_jackpot_upside_score": 63.0,
            "financial_rip_v3_base_economic_efficiency_score": 48.0,
            "financial_rip_v3_true_win_probability": 0.0833,
            "financial_rip_v3_typical_pack_value": 2.10,
            "financial_rip_v3_typical_retention_ratio": 0.42,
            "financial_rip_v3_average_retention_given_loss": 0.35,
            "financial_rip_v3_soft_loss_share_given_loss": 0.60,
            "financial_rip_v3_hard_loss_probability": 0.28,
            "financial_rip_v3_p95_threshold_value": 14.0,
            "financial_rip_v3_p95_threshold_ratio": 2.8,
            "financial_rip_v3_realistic_tail_mean_value": 21.0,
            "financial_rip_v3_realistic_tail_mean_ratio": 4.2,
            "financial_rip_v3_p99_threshold_value": 45.0,
            "financial_rip_v3_p99_threshold_ratio": 9.0,
            "financial_rip_v3_jackpot_tail_mean_value": 130.0,
            "financial_rip_v3_jackpot_tail_mean_ratio": 26.0,
            "financial_rip_v3_total_rtp_ratio": 0.92,
            "financial_rip_v3_base_rtp_excluding_top_1pct": 0.61,
            "financial_rip_v3_jackpot_value_share": 0.31,
            "financial_rip_v3_payload": _v3_payload_document(),
        }
    )
    return payload


def _capture_insert(flat_payload):
    """Run the writer and return the payload handed to Supabase."""
    with patch.object(repo, "_insert_required_payload") as mock_insert:
        mock_insert.return_value = {"id": "row-1"}
        create_simulation_derived_metrics(RUN_ID, flat_payload)
        mock_insert.assert_called_once()
        table_name, payload, _context = mock_insert.call_args[0]
    assert table_name == "simulation_derived_metrics"
    return payload


# ---------------------------------------------------------------------------
# The regression: fields that were being dropped
# ---------------------------------------------------------------------------

def test_every_financial_rip_v3_field_reaches_the_insert_payload():
    """THE regression test. Each of the 30 V3 columns must be written."""
    payload = _capture_insert(_ready_flat_payload())
    missing = [field for field in FINANCIAL_RIP_V3_METRIC_FIELDS if field not in payload]
    assert not missing, f"V3 columns missing from the insert payload: {missing}"


def test_v3_values_reach_the_insert_unchanged_not_merely_present():
    """Presence is not enough - a key written as None is the same NULL bug."""
    flat = _ready_flat_payload()
    payload = _capture_insert(flat)
    assert payload["financial_rip_v3_score"] == 61.25
    assert payload["financial_rip_v3_status"] == "ready"
    assert payload["financial_rip_v3_rankable"] is True
    assert payload["financial_rip_v3_simulation_count"] == 12000
    assert payload["financial_rip_v3_jackpot_tail_mean_ratio"] == 26.0
    for field in FINANCIAL_RIP_V3_METRIC_FIELDS:
        assert payload[field] is not None, f"{field} reached the insert as NULL"


def test_top2_ev_share_reaches_the_insert():
    """Omitted by the old literal alongside the V3 block."""
    payload = _capture_insert(_ready_flat_payload())
    assert "top2_ev_share" in payload
    assert payload["top2_ev_share"] == 0.44


def test_financial_rip_v3_payload_reaches_the_insert_as_a_json_document():
    """JSONB must arrive as a mapping, never as a stringified blob.

    A stringified document would still insert - into a JSONB column Postgres
    would store a JSON *string* - and every `->>` read against it would then
    return nothing, which is a subtler version of the same silent failure.
    """
    payload = _capture_insert(_ready_flat_payload())
    document = payload["financial_rip_v3_payload"]
    assert isinstance(document, Mapping), f"expected a mapping, got {type(document).__name__}"
    assert not isinstance(document, str)
    assert document["score"] == 61.25
    assert document["components"]["true_win_frequency"]["score"] == 33.3
    # And it must survive real JSON serialization on the way to the driver.
    json.dumps(document)


# ---------------------------------------------------------------------------
# Drift protection
# ---------------------------------------------------------------------------

def test_insert_contract_covers_every_declared_derived_metric_field():
    payload = _capture_insert(_ready_flat_payload())
    missing = [field for field in DERIVED_METRIC_FIELDS if field not in payload]
    assert not missing, f"declared columns absent from the insert: {missing}"


def test_insert_payload_adds_nothing_beyond_the_declared_contract():
    """An undeclared key would fail the insert against the real schema."""
    payload = _capture_insert(_ready_flat_payload())
    allowed = set(DERIVED_METRIC_FIELDS) | {"calculation_run_id"}
    assert set(payload) - allowed == set()


def test_a_future_v3_field_cannot_be_silently_omitted():
    """Adding a column without a coercion rule must fail loudly, not write NULL.

    This is the guard that replaces the second field contract. It simulates the
    exact mistake that caused the original defect - a column declared but not
    handled by the writer - and asserts it is now impossible to do quietly.
    """
    with patch.object(
        repo, "DERIVED_METRIC_FIELDS", [*DERIVED_METRIC_FIELDS, "financial_rip_v3_future_metric"]
    ):
        with pytest.raises(ValueError, match="no insert coercion rule"):
            repo._audit_derived_metric_coercions()


def test_a_coercion_rule_for_an_undeclared_column_is_also_rejected():
    """Drift in the other direction: a rule naming a column that does not exist."""
    with patch.dict(
        repo._DERIVED_METRIC_COERCIONS,
        {"financial_rip_v3_removed_metric": repo._coerce_optional_float},
    ):
        with pytest.raises(ValueError, match="absent from"):
            repo._audit_derived_metric_coercions()


def test_the_live_contract_is_currently_exhaustive():
    """The audit passes as shipped - no missing and no extra rules."""
    repo._audit_derived_metric_coercions()
    assert set(repo._DERIVED_METRIC_COERCIONS) == set(DERIVED_METRIC_FIELDS)


# ---------------------------------------------------------------------------
# Unavailable V3 and legacy callers
# ---------------------------------------------------------------------------

def test_unavailable_v3_persists_explicit_status_and_rankable_without_a_score():
    """An unavailable run records WHY, rather than storing nothing at all."""
    flat = {field: None for field in DERIVED_METRIC_FIELDS}
    flat.update(
        {
            "pack_score": 50.0,
            "score_version": "v2",
            "financial_rip_v3_status": "unavailable",
            "financial_rip_v3_rankable": False,
            "financial_rip_v3_score": None,
        }
    )
    payload = _capture_insert(flat)
    assert payload["financial_rip_v3_status"] == "unavailable"
    # False must survive as False, not be coerced to None - "not rankable" and
    # "we do not know whether it is rankable" are different facts.
    assert payload["financial_rip_v3_rankable"] is False
    assert payload["financial_rip_v3_score"] is None


def test_a_legacy_caller_without_v3_persists_v2_with_null_v3_columns():
    """A derived payload predating V3 must still insert cleanly."""
    legacy = {
        "simulated_set_value": 900.0,
        "pack_score": 48.0,
        "profit_score": 55.0,
        "safety_score": 44.0,
        "stability_score": 41.0,
        "score_version": "v2",
        "normalization_mode": "cohort",
        "top1_ev_share": 0.2,
        "top3_ev_share": 0.4,
        "top5_ev_share": 0.5,
    }
    payload = _capture_insert(legacy)
    assert payload["pack_score"] == 48.0
    assert payload["top1_ev_share"] == 0.2
    # Genuinely absent, so genuinely NULL - never a fabricated zero or score.
    for field in FINANCIAL_RIP_V3_METRIC_FIELDS:
        assert field in payload
        assert payload[field] is None
    assert payload["top2_ev_share"] is None


def test_v2_field_values_are_unchanged_by_the_new_writer():
    """Every V2 column keeps its exact prior value and meaning."""
    flat = _ready_flat_payload()
    payload = _capture_insert(flat)
    for field in (
        "simulated_set_value", "simulated_set_value_card_count", "hit_ev", "non_hit_ev",
        "cards_tracked", "total_card_ev", "top1_ev_share", "top3_ev_share",
        "top5_ev_share", "pack_score", "profit_score", "safety_score",
        "stability_score", "score_version", "normalization_mode",
        "pack_score_is_placeholder", "desirability_is_fallback",
        "derived_metric_version",
    ):
        assert payload[field] == flat[field], f"{field} changed"


def test_run_id_is_required_and_carried_onto_the_row():
    payload = _capture_insert(_ready_flat_payload())
    assert payload["calculation_run_id"] == RUN_ID


def test_a_non_mapping_derived_payload_is_rejected():
    with pytest.raises(ValueError, match="derived"):
        create_simulation_derived_metrics(RUN_ID, None)


# ---------------------------------------------------------------------------
# Coercion behaviour
# ---------------------------------------------------------------------------

def test_numeric_strings_are_coerced_for_numeric_columns():
    flat = {field: None for field in DERIVED_METRIC_FIELDS}
    flat.update({"financial_rip_v3_score": "61.25", "financial_rip_v3_simulation_count": "12000"})
    payload = _capture_insert(flat)
    assert payload["financial_rip_v3_score"] == 61.25
    assert payload["financial_rip_v3_simulation_count"] == 12000


def test_a_json_string_payload_is_parsed_back_into_a_document():
    """Defensive: a pre-serialized document must not land in JSONB as a string."""
    flat = {field: None for field in DERIVED_METRIC_FIELDS}
    flat["financial_rip_v3_payload"] = json.dumps(_v3_payload_document())
    payload = _capture_insert(flat)
    assert isinstance(payload["financial_rip_v3_payload"], Mapping)
    assert payload["financial_rip_v3_payload"]["score"] == 61.25


def test_an_empty_v3_document_is_stored_as_null_not_an_empty_object():
    """`{}` would claim a V3 result was recorded and was empty. It was not."""
    flat = {field: None for field in DERIVED_METRIC_FIELDS}
    flat["financial_rip_v3_payload"] = {}
    payload = _capture_insert(flat)
    assert payload["financial_rip_v3_payload"] is None
