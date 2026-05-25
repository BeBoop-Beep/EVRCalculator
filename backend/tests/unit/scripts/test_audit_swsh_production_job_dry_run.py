import json

import pytest

import backend.jobs.evr_runner as evr_runner
from backend.constants.tcg.pokemon.swordAndShieldEra.chillingReign import SetChillingReignConfig
from backend.constants.tcg.pokemon.swordAndShieldEra.evolvingSkies import SetEvolvingSkiesConfig
from backend.scripts import audit_swsh_production_job_dry_run as audit_script
from backend.simulations.evrSimulator import _should_use_monte_carlo_v2, get_simulation_engine


class _DummyConfig:
    USE_MONTE_CARLO_V2 = False


def test_requires_dry_run_flag(tmp_path):
    with pytest.raises(RuntimeError, match="--dry-run"):
        audit_script.run_production_job_dry_run(
            json_output_path=tmp_path / "out.json",
            markdown_output_path=tmp_path / "out.md",
            pack_count=10,
            strict_db_input=True,
            dry_run=False,
        )


def test_no_write_spy_context_patches_persistence_and_restores_after_exit():
    harness = audit_script.WriteSpyHarness()
    harness.set_current_set("swsh6")

    original_parent = evr_runner.persist_parent_run_with_price_snapshots

    with audit_script._no_write_spy_context(harness, pack_count=25, strict_db_input=False):
        assert evr_runner.persist_parent_run_with_price_snapshots is not original_parent

        result = evr_runner.persist_parent_run_with_price_snapshots(
            config=_DummyConfig,
            canonical_key="chillingReign",
            set_name="Chilling Reign",
            input_mode="db",
            price_inputs={"pack": 4.99, "booster_box": 149.99},
            pack_value_vs_cost_comparison={},
            etb_value_vs_cost_comparison=None,
            booster_box_value_vs_cost_comparison={},
        )

        assert result["dry_run"] is True
        assert result["no_write"] is True

    assert evr_runner.persist_parent_run_with_price_snapshots is original_parent

    intended = harness.intended_write_counts_by_set["swsh6"]
    assert intended["calculation_runs"] == 1
    assert intended["calculation_price_snapshots"] == 2


def test_validate_input_metadata_rejects_fallback_in_strict_mode():
    with pytest.raises(RuntimeError, match="fallback"):
        audit_script._validate_input_metadata(
            {
                "source": "db_evr_input_preparation_service",
                "fallback_used": True,
                "row_count": 1,
                "required_columns_present": True,
                "price_column_detected": "Price ($)",
                "usable_price_rows": 1,
            },
            strict_db_input=True,
        )


def test_scope_is_only_swsh6_swsh7():
    set_ids = {target.set_id for target in audit_script.TARGETS}
    assert set_ids == {"swsh6", "swsh7"}


def test_swsh6_swsh7_select_slot_schema_and_bypass_v2():
    for config in [SetChillingReignConfig, SetEvolvingSkiesConfig]:
        assert get_simulation_engine(config) == "slot_schema"
        assert _should_use_monte_carlo_v2(config) is False


def test_warning_flags_no_critical_on_happy_path():
    flags = audit_script._build_warning_flags(
        dry_run_enabled=True,
        actual_writes_performed=0,
        intended_write_total=12,
        simulation_engine="slot_schema",
        monte_carlo_v2_bypassed=True,
        slot_schema_runtime_used=True,
        production_probability_equals_draft=True,
        strict_db_input_passed=True,
        output_payload_metrics_present=True,
        output_payload_json_serializable=True,
        roi_absolute_delta=0.0,
        roi_consistency_passed=True,
        value_to_cost_ratio_absolute_delta=0.0,
        value_to_cost_ratio_consistency_passed=True,
        probability_to_beat_pack_cost_absolute_delta=0.0,
        probability_to_beat_pack_cost_consistency_passed=True,
        sv_mega_routing_status={"changed": False, "all_expected_v2": True, "v2_violations": []},
        other_swsh_guardrail_unchanged=True,
    )

    critical_triggered = [
        flag["code"]
        for flag in flags
        if flag["severity"] == "critical" and flag["triggered"]
    ]
    assert critical_triggered == []


def test_output_metrics_present_contract():
    row = {
        "estimated_pack_price": 4.99,
        "cost": 4.99,
        "expected_value": 4.75,
        "average_pack_value": 4.75,
        "median_pack_value": 4.5,
        "value_to_cost_ratio": 0.95,
        "legacy_value_cost_ratio": 0.95,
        "metric_semantics_version": "formula_roi_v2",
        "roi_formula": "(average_pack_value - estimated_pack_price) / estimated_pack_price",
        "reported_roi": -0.05,
        "reported_value_to_cost_ratio": 0.95,
        "expected_roi_from_mean_and_pack_price": -0.05,
        "probability_to_beat_pack_cost": 0.42,
        "reported_probability_to_beat_pack_cost": 0.42,
        "output_payload_keys": ["a", "b"],
    }
    assert audit_script._output_metrics_present(row) is True

    row_missing = dict(row)
    del row_missing["reported_roi"]
    assert audit_script._output_metrics_present(row_missing) is False


def test_warning_flags_value_to_cost_ratio_semantic_mismatch_triggers():
    flags = audit_script._build_warning_flags(
        dry_run_enabled=True,
        actual_writes_performed=0,
        intended_write_total=12,
        simulation_engine="slot_schema",
        monte_carlo_v2_bypassed=True,
        slot_schema_runtime_used=True,
        production_probability_equals_draft=True,
        strict_db_input_passed=True,
        output_payload_metrics_present=True,
        output_payload_json_serializable=True,
        roi_absolute_delta=0.0,
        roi_consistency_passed=True,
        value_to_cost_ratio_absolute_delta=0.01,
        value_to_cost_ratio_consistency_passed=False,
        probability_to_beat_pack_cost_absolute_delta=0.0,
        probability_to_beat_pack_cost_consistency_passed=True,
        sv_mega_routing_status={"changed": False, "all_expected_v2": True, "v2_violations": []},
        other_swsh_guardrail_unchanged=True,
    )

    mismatch = next(flag for flag in flags if flag["code"] == "value_to_cost_ratio_semantic_mismatch")
    assert mismatch["severity"] == "critical"
    assert mismatch["triggered"] is True


def test_warning_flags_roi_semantic_mismatch_triggers():
    flags = audit_script._build_warning_flags(
        dry_run_enabled=True,
        actual_writes_performed=0,
        intended_write_total=12,
        simulation_engine="slot_schema",
        monte_carlo_v2_bypassed=True,
        slot_schema_runtime_used=True,
        production_probability_equals_draft=True,
        strict_db_input_passed=True,
        output_payload_metrics_present=True,
        output_payload_json_serializable=True,
        roi_absolute_delta=0.01,
        roi_consistency_passed=False,
        value_to_cost_ratio_absolute_delta=0.0,
        value_to_cost_ratio_consistency_passed=True,
        probability_to_beat_pack_cost_absolute_delta=0.0,
        probability_to_beat_pack_cost_consistency_passed=True,
        sv_mega_routing_status={"changed": False, "all_expected_v2": True, "v2_violations": []},
        other_swsh_guardrail_unchanged=True,
    )

    mismatch = next(flag for flag in flags if flag["code"] == "roi_semantic_mismatch")
    assert mismatch["severity"] == "critical"
    assert mismatch["triggered"] is True


def test_warning_flags_probability_semantic_mismatch_triggers():
    flags = audit_script._build_warning_flags(
        dry_run_enabled=True,
        actual_writes_performed=0,
        intended_write_total=12,
        simulation_engine="slot_schema",
        monte_carlo_v2_bypassed=True,
        slot_schema_runtime_used=True,
        production_probability_equals_draft=True,
        strict_db_input_passed=True,
        output_payload_metrics_present=True,
        output_payload_json_serializable=True,
        roi_absolute_delta=0.0,
        roi_consistency_passed=True,
        value_to_cost_ratio_absolute_delta=0.0,
        value_to_cost_ratio_consistency_passed=True,
        probability_to_beat_pack_cost_absolute_delta=0.01,
        probability_to_beat_pack_cost_consistency_passed=False,
        sv_mega_routing_status={"changed": False, "all_expected_v2": True, "v2_violations": []},
        other_swsh_guardrail_unchanged=True,
    )

    mismatch = next(
        flag for flag in flags if flag["code"] == "probability_to_beat_cost_semantic_mismatch"
    )
    assert mismatch["severity"] == "critical"
    assert mismatch["triggered"] is True


def test_run_payload_uses_only_target_scope_with_mocked_set_runner(tmp_path, monkeypatch):
    json_path = tmp_path / "dry_run.json"
    md_path = tmp_path / "dry_run.md"

    def _mock_single_set_dry_run(**kwargs):
        target = kwargs["target"]
        return {
            "set_key": target.canonical_key,
            "set_id": target.set_id,
            "set_name": target.set_name,
            "selected_simulation_engine": "slot_schema",
            "monte_carlo_v2_bypassed": True,
            "slot_schema_runtime_used": True,
            "db_input_source": "db_evr_input_preparation_service",
            "pack_count": 100,
            "estimated_pack_price": 4.99,
            "average_pack_value": 4.75,
            "median_pack_value": 4.5,
            "roi": -0.05,
            "value_to_cost_ratio": 0.95,
            "legacy_value_cost_ratio": 0.95,
            "metric_semantics_version": "formula_roi_v2",
            "roi_formula": "(average_pack_value - estimated_pack_price) / estimated_pack_price",
            "reported_roi": -0.05,
            "reported_value_to_cost_ratio": 0.95,
            "expected_roi_from_mean_and_pack_price": -0.05,
            "probability_to_beat_pack_cost": 0.42,
            "probability_to_beat_pack_cost_from_values": 0.42,
            "reported_probability_to_beat_pack_cost": 0.42,
            "p05": 0.1,
            "p95": 12.0,
            "p99": 25.0,
            "output_payload_keys": ["a", "b"],
            "intended_persistence_targets": ["calculation_runs", "simulation_input_cards"],
            "intended_write_counts": {
                "calculation_runs": 1,
                "simulation_input_cards": 100,
            },
            "actual_writes_performed": 0,
            "strict_db_input_passed": True,
            "production_probability_equals_draft": True,
            "probability_table_status": {
                "production_equals_draft": True,
            },
            "output_payload_metrics_present": True,
            "output_payload_json_serializable": True,
            "warning_flags": [
                {
                    "code": "dry_run_required",
                    "severity": "critical",
                    "triggered": False,
                    "detail": "ok",
                    "value": None,
                }
            ],
        }

    monkeypatch.setattr(audit_script, "_run_single_set_dry_run", _mock_single_set_dry_run)

    payload = audit_script.run_production_job_dry_run(
        json_output_path=json_path,
        markdown_output_path=md_path,
        pack_count=100,
        strict_db_input=True,
        dry_run=True,
    )

    assert json_path.exists()
    assert md_path.exists()

    set_ids = {row["set_id"] for row in payload["sets"]}
    assert set_ids == {"swsh6", "swsh7"}

    assert payload["meta"]["actual_writes_performed_total"] == 0
    assert payload["runtime_approval_input_status"] == "strict_db_input_passed"
    assert payload["safety_assertions"]["passed"] is True

    materialized = json.loads(json_path.read_text(encoding="utf-8"))
    assert materialized["safety_assertions"]["passed"] is True
