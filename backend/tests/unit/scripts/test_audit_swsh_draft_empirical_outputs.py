import json

import pytest

import backend.db.services.evr_input_preparation_service as evr_input_preparation_service
from backend.constants.tcg.pokemon.swordAndShieldEra.chillingReign import SetChillingReignConfig
from backend.constants.tcg.pokemon.swordAndShieldEra.evolvingSkies import SetEvolvingSkiesConfig
from backend.scripts.audit_swsh_draft_empirical_outputs import (
    TARGETS,
    _load_simulation_input,
    _warning_flags,
    run_draft_output_inspection,
)


def _run_payload(tmp_path):
    json_path = tmp_path / "draft_empirical_inspection.json"
    md_path = tmp_path / "draft_empirical_inspection.md"
    payload = run_draft_output_inspection(
        json_output_path=json_path,
        markdown_output_path=md_path,
        pack_count=1500,
        seed_base=70100,
        prefer_db_input=False,
    )
    return payload, json_path, md_path


def test_script_runs_read_only_and_writes_artifacts(tmp_path):
    before = {
        "chilling_runtime": SetChillingReignConfig.SLOT_SCHEMA_RUNTIME_ENABLED,
        "evolving_runtime": SetEvolvingSkiesConfig.SLOT_SCHEMA_RUNTIME_ENABLED,
        "chilling_has_rare": hasattr(SetChillingReignConfig, "RARE_SLOT_PROBABILITY"),
        "evolving_has_rare": hasattr(SetEvolvingSkiesConfig, "RARE_SLOT_PROBABILITY"),
    }

    payload, json_path, md_path = _run_payload(tmp_path)

    assert json_path.exists()
    assert md_path.exists()

    assert payload["guardrails"]["unchanged"] is True
    assert SetChillingReignConfig.SLOT_SCHEMA_RUNTIME_ENABLED is before["chilling_runtime"]
    assert SetEvolvingSkiesConfig.SLOT_SCHEMA_RUNTIME_ENABLED is before["evolving_runtime"]
    assert hasattr(SetChillingReignConfig, "RARE_SLOT_PROBABILITY") is before["chilling_has_rare"]
    assert hasattr(SetEvolvingSkiesConfig, "RARE_SLOT_PROBABILITY") is before["evolving_has_rare"]


def test_output_contains_required_sets_probability_status_metrics_and_warnings(tmp_path):
    payload, _json_path, _md_path = _run_payload(tmp_path)

    rows = payload["sets"]
    by_set_id = {row["set_id"]: row for row in rows}
    assert {"swsh6", "swsh7"}.issubset(by_set_id.keys())

    for set_id in ("swsh6", "swsh7"):
        row = by_set_id[set_id]

        probability_status = row["probability_table_status"]
        assert "draft_probability_table" in probability_status
        assert "sum_is_one" in probability_status
        assert "mapping_keys_match" in probability_status
        assert "production_runtime_enabled" in probability_status
        assert "production_has_rare_slot_probability" in probability_status

        metrics = row["metrics"]
        assert "average_pack_value" in metrics
        assert "median_pack_value" in metrics
        assert "roi_at_estimated_pack_price" in metrics
        assert "chance_to_beat_pack_cost" in metrics
        assert "chance_at_big_hit" in metrics
        assert "p05" in metrics
        assert "p95" in metrics
        assert "p99" in metrics
        assert "best_simulated_pull" in metrics

        frequency_deltas = row["rare_slot_frequency_deltas"]
        assert isinstance(frequency_deltas.get("rows"), list)
        assert len(frequency_deltas["rows"]) > 0
        assert "largest_abs_delta" in frequency_deltas

        warning_flags = row["warning_flags"]
        assert isinstance(warning_flags, list)
        assert warning_flags
        for flag in warning_flags:
            assert "code" in flag
            assert "severity" in flag
            assert "triggered" in flag
            assert "detail" in flag


def test_output_metadata_identifies_fallback_usage_and_status(tmp_path):
    payload, _json_path, _md_path = _run_payload(tmp_path)

    assert payload["runtime_approval_input_status"] == "fallback_behavior_only"

    for row in payload["sets"]:
        simulation_input = row["simulation_input"]
        assert simulation_input["fallback_used"] is True
        assert simulation_input["strict_db_input"] is False
        assert simulation_input["source"] == "fallback_test_builder"
        assert isinstance(simulation_input["row_count"], int)
        assert isinstance(simulation_input["column_names"], list)
        assert "required_columns_present" in simulation_input
        assert "price_column_detected" in simulation_input
        assert "missing_price_rows" in simulation_input
        assert "non_positive_price_rows" in simulation_input
        assert "usable_price_rows" in simulation_input


def test_strict_mode_raises_when_db_input_is_unavailable(monkeypatch):
    def _raise_db_unavailable(_self, _config, _canonical_key, _set_name):
        raise RuntimeError("db unavailable for strict test")

    monkeypatch.setattr(
        evr_input_preparation_service.EVRInputPreparationService,
        "prepare_for_set",
        _raise_db_unavailable,
    )

    try:
        _load_simulation_input(
            TARGETS[0],
            prefer_db_input=True,
            allow_fallback=False,
        )
    except RuntimeError as exc:
        assert "fallback disabled" in str(exc)
    else:
        assert False, "Expected strict mode to raise when DB input is unavailable"


def test_strict_mode_failure_writes_non_success_status_artifact(tmp_path, monkeypatch):
    json_path = tmp_path / "strict_fail.json"
    md_path = tmp_path / "strict_fail.md"

    def _raise_on_set(*_args, **_kwargs):
        raise RuntimeError("forced strict db blocker")

    monkeypatch.setattr(
        "backend.scripts.audit_swsh_draft_empirical_outputs._run_single_set_inspection",
        _raise_on_set,
    )

    try:
        run_draft_output_inspection(
            json_output_path=json_path,
            markdown_output_path=md_path,
            pack_count=500,
            prefer_db_input=True,
            strict_db_input=True,
        )
    except RuntimeError as exc:
        assert "forced strict db blocker" in str(exc)
    else:
        assert False, "Expected strict run to raise blocker"

    assert json_path.exists()
    payload = json.loads(json_path.read_text(encoding="utf-8"))
    assert payload["runtime_approval_input_status"] == "strict_db_input_failed"
    assert payload["runtime_approval_input_status"] != "strict_db_input_passed"


def test_runtime_is_enabled_intentionally_and_production_rare_slot_probability_is_present(tmp_path):
    _payload, _json_path, _md_path = _run_payload(tmp_path)

    assert SetChillingReignConfig.SLOT_SCHEMA_RUNTIME_ENABLED is True
    assert SetEvolvingSkiesConfig.SLOT_SCHEMA_RUNTIME_ENABLED is True
    assert hasattr(SetChillingReignConfig, "RARE_SLOT_PROBABILITY")
    assert hasattr(SetEvolvingSkiesConfig, "RARE_SLOT_PROBABILITY")
    assert SetChillingReignConfig.RARE_SLOT_PROBABILITY == SetChillingReignConfig.CHILLING_REIGN_RARE_SLOT_PROBABILITY_DRAFT
    assert SetEvolvingSkiesConfig.RARE_SLOT_PROBABILITY == SetEvolvingSkiesConfig.EVOLVING_SKIES_RARE_SLOT_PROBABILITY_DRAFT


# ---------------------------------------------------------------------------
# Project 6.8.2 — new focused tests
# ---------------------------------------------------------------------------


def test_strict_failure_artifact_computes_guardrails_unchanged_from_snapshots(tmp_path, monkeypatch):
    """guardrails['unchanged'] must be computed from before/after snapshots, never hardcoded."""
    json_path = tmp_path / "strict_fail_guardrail.json"
    md_path = tmp_path / "strict_fail_guardrail.md"

    def _raise_on_set(*_args, **_kwargs):
        raise RuntimeError("forced strict db blocker for guardrail test")

    monkeypatch.setattr(
        "backend.scripts.audit_swsh_draft_empirical_outputs._run_single_set_inspection",
        _raise_on_set,
    )

    with pytest.raises(RuntimeError, match="forced strict db blocker"):
        run_draft_output_inspection(
            json_output_path=json_path,
            markdown_output_path=md_path,
            pack_count=500,
            prefer_db_input=True,
            strict_db_input=True,
        )

    assert json_path.exists()
    payload = json.loads(json_path.read_text(encoding="utf-8"))
    guardrails = payload["guardrails"]

    # The computed unchanged flag must equal the actual comparison, not True.
    expected_unchanged = guardrails["before"] == guardrails["after"]
    assert guardrails["unchanged"] == expected_unchanged, (
        "guardrails['unchanged'] must be computed from before/after snapshots"
    )
    # Production configs are never mutated; both snapshots must match.
    assert guardrails["unchanged"] is True


def test_strict_failure_surfaces_set_id_and_set_name_in_exception(monkeypatch):
    """RuntimeError raised in strict mode must include set_id and set_name."""
    def _raise_db_unavailable(_self, _config, _canonical_key, _set_name):
        raise RuntimeError("db unavailable")

    monkeypatch.setattr(
        evr_input_preparation_service.EVRInputPreparationService,
        "prepare_for_set",
        _raise_db_unavailable,
    )

    target = TARGETS[0]  # swsh6 / Chilling Reign
    with pytest.raises(RuntimeError) as exc_info:
        _load_simulation_input(target, prefer_db_input=True, allow_fallback=False)

    error_message = str(exc_info.value)
    assert target.set_id in error_message, f"set_id={target.set_id!r} missing from error: {error_message}"
    assert target.set_name in error_message, f"set_name={target.set_name!r} missing from error: {error_message}"


def _make_mock_set_row(*, set_id: str, set_name: str, fallback_used: bool, source: str) -> dict:
    """Return a minimal inspection row accepted by run_draft_output_inspection."""
    return {
        "set_id": set_id,
        "set_name": set_name,
        "canonical_key": set_id,
        "simulation_input": {
            "source": source,
            "db_attempted": True,
            "fallback_used": fallback_used,
            "strict_db_input": True,
            "row_count": 1,
            "column_names": [],
            "required_columns_present": True,
            "missing_required_columns": [],
            "price_column_detected": "Price ($)",
            "non_positive_price_rows": 0,
            "missing_price_rows": 0,
            "usable_price_rows": 1,
        },
        "pack_count": 200,
        "estimated_pack_price": 4.99,
        "probability_table_status": {
            "draft_table_attr": "",
            "sum_probability": 1.0,
            "sum_is_one": True,
            "mapping_keys_match": True,
            "missing_mapping_keys": [],
            "unexpected_table_keys": [],
            "residual_rare_probability": 0.0,
            "production_runtime_enabled": False,
            "production_has_rare_slot_probability": False,
            "draft_probability_table": {},
        },
        "rare_slot_probability_table": {},
        "residual_rare_probability": 0.0,
        "metrics": {
            "average_pack_value": 0.5,
            "median_pack_value": 0.5,
            "roi_at_estimated_pack_price": -0.9,
            "chance_to_beat_pack_cost": 0.1,
            "chance_at_big_hit": 0.01,
            "big_hit_threshold": 14.97,
            "p05": 0.1,
            "p95": 1.0,
            "p99": 2.0,
            "best_simulated_pull": {"max_pack_value": 2.0, "best_pool_card_reference": {}},
        },
        "top_ev_contributing_cards": [],
        "cards_carrying_set": {},
        "rare_slot_bucket_frequencies": [],
        "rare_slot_frequency_deltas": {"rows": [], "largest_abs_delta": 0.0},
        "reverse_slot_sanity_check": {},
        "warning_flags": [],
        "elapsed_seconds": 0.1,
    }


def test_strict_mode_sets_passed_status_when_db_input_is_valid(tmp_path, monkeypatch):
    """When DB input is valid and no fallback used, strict mode must set strict_db_input_passed."""
    json_path = tmp_path / "strict_pass.json"
    md_path = tmp_path / "strict_pass.md"

    def _mock_single_set(target, *, pack_count, seed, prefer_db_input, strict_db_input):
        return _make_mock_set_row(
            set_id=target.set_id,
            set_name=target.set_name,
            fallback_used=False,
            source="db_evr_input_preparation_service",
        )

    monkeypatch.setattr(
        "backend.scripts.audit_swsh_draft_empirical_outputs._run_single_set_inspection",
        _mock_single_set,
    )

    payload = run_draft_output_inspection(
        json_output_path=json_path,
        markdown_output_path=md_path,
        pack_count=200,
        prefer_db_input=True,
        strict_db_input=True,
    )

    assert payload["runtime_approval_input_status"] == "strict_db_input_passed"
    for row in payload["sets"]:
        sim_input = row["simulation_input"]
        assert sim_input["fallback_used"] is False
        assert sim_input["source"] == "db_evr_input_preparation_service"


def test_strict_mode_does_not_mutate_intentionally_enabled_runtime_or_production_probability_table(tmp_path, monkeypatch):
    """Strict mode must not mutate production runtime/probability configuration."""
    json_path = tmp_path / "strict_no_mutate.json"
    md_path = tmp_path / "strict_no_mutate.md"

    def _mock_single_set(target, *, pack_count, seed, prefer_db_input, strict_db_input):
        return _make_mock_set_row(
            set_id=target.set_id,
            set_name=target.set_name,
            fallback_used=False,
            source="db_evr_input_preparation_service",
        )

    monkeypatch.setattr(
        "backend.scripts.audit_swsh_draft_empirical_outputs._run_single_set_inspection",
        _mock_single_set,
    )

    run_draft_output_inspection(
        json_output_path=json_path,
        markdown_output_path=md_path,
        pack_count=200,
        prefer_db_input=True,
        strict_db_input=True,
    )

    # Production configs must remain untouched.
    assert SetChillingReignConfig.SLOT_SCHEMA_RUNTIME_ENABLED is True
    assert SetEvolvingSkiesConfig.SLOT_SCHEMA_RUNTIME_ENABLED is True
    assert hasattr(SetChillingReignConfig, "RARE_SLOT_PROBABILITY")
    assert hasattr(SetEvolvingSkiesConfig, "RARE_SLOT_PROBABILITY")
    assert SetChillingReignConfig.RARE_SLOT_PROBABILITY == SetChillingReignConfig.CHILLING_REIGN_RARE_SLOT_PROBABILITY_DRAFT
    assert SetEvolvingSkiesConfig.RARE_SLOT_PROBABILITY == SetEvolvingSkiesConfig.EVOLVING_SKIES_RARE_SLOT_PROBABILITY_DRAFT


def _warning_by_code(flags, code):
    for flag in flags:
        if flag.get("code") == code:
            return flag
    raise AssertionError(f"warning flag not found: {code}")


def _base_warning_flags(reverse_sanity):
    return _warning_flags(
        probability_status={"sum_is_one": True, "mapping_keys_match": True},
        avg_pack_value=3.0,
        median_pack_value=1.0,
        pack_price=10.0,
        largest_rare_slot_delta=0.001,
        reverse_sanity=reverse_sanity,
        card_pool={"rare": [{"value": 1.0}]},
        draft_table={"rare": 1.0},
        top_concentration={"top_1_share_of_hit_ev": 0.1, "top_5_share_of_hit_ev": 0.2},
    )


def test_reverse_pool_base_row_representation_does_not_trigger_critical_leakage():
    flags = _base_warning_flags(
        {
            "has_reverse_holo_leakage": False,
            "rare_slot_reverse_holo_leakage_by_bucket": {},
            "reverse_pool_has_non_reverse_entries": True,
            "reverse_pool_count": 112,
            "expected_regular_reverse_count": 100,
            "observed_regular_reverse_count": 100,
            "count_delta": 0,
        }
    )

    leakage_flag = _warning_by_code(flags, "reverse_holo_leakage")
    representation_flag = _warning_by_code(flags, "reverse_pool_representation_uses_base_rows")

    assert leakage_flag["severity"] == "critical"
    assert leakage_flag["triggered"] is False
    assert representation_flag["severity"] == "info"
    assert representation_flag["triggered"] is True


def test_rare_slot_reverse_leakage_still_triggers_critical_flag():
    flags = _base_warning_flags(
        {
            "has_reverse_holo_leakage": False,
            "rare_slot_reverse_holo_leakage_by_bucket": {"holo rare": 3},
            "reverse_pool_has_non_reverse_entries": True,
            "reverse_pool_count": 112,
            "expected_regular_reverse_count": 100,
            "observed_regular_reverse_count": 100,
            "count_delta": 0,
        }
    )

    leakage_flag = _warning_by_code(flags, "reverse_holo_leakage")
    assert leakage_flag["triggered"] is True
    assert leakage_flag["severity"] == "critical"


def test_reverse_slot_count_delta_remains_independent_warning():
    flags = _base_warning_flags(
        {
            "has_reverse_holo_leakage": False,
            "rare_slot_reverse_holo_leakage_by_bucket": {},
            "reverse_pool_has_non_reverse_entries": False,
            "reverse_pool_count": 112,
            "expected_regular_reverse_count": 100,
            "observed_regular_reverse_count": 98,
            "count_delta": -2,
        }
    )

    count_flag = _warning_by_code(flags, "reverse_slot_regular_count_mismatch")
    assert count_flag["severity"] == "warning"
    assert count_flag["triggered"] is True