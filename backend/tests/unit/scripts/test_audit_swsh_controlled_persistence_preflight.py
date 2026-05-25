import json

import pytest

from backend.db.repositories import calculation_runs_repository
from backend.scripts import audit_swsh_controlled_persistence_preflight as preflight


def _base_flags_kwargs():
    return {
        "execute_mode": False,
        "actual_writes_performed": 0,
        "intended_write_total": 10,
        "target_scope": ["swsh6", "swsh7"],
        "simulation_engine": "slot_schema",
        "monte_carlo_v2_bypassed": True,
        "slot_schema_runtime_used": True,
        "production_has_rare_slot_probability": True,
        "production_probability_equals_draft": True,
        "sum_probability": 1.0,
        "residual_rare_non_negative": True,
        "strict_db_input_source_ok": True,
        "strict_db_fallback_not_used": True,
        "strict_db_required_columns_present": True,
        "usable_price_rows_positive": True,
        "estimated_pack_price_present": True,
        "pack_price_source_present": True,
        "reverse_holo_leakage_detected": False,
        "roi_consistency_passed": True,
        "value_to_cost_ratio_consistency_passed": True,
        "probability_to_beat_pack_cost_consistency_passed": True,
        "output_payload_json_serializable": True,
        "persistence_payload_validators_passed": True,
        "unexpected_write_targets": [],
        "destructive_operations_detected": [],
        "sv_mega_routing_status": {"changed": False, "all_expected_v2": True, "v2_violations": []},
        "other_swsh_guardrail_unchanged": True,
        "execute_mode_confirmed": False,
        "parent_run_id_present": False,
        "expected_persisted_ids_present": True,
        "execute_real_writes_expected": False,
    }


def _critical_codes(flags):
    return [
        flag["code"]
        for flag in flags
        if flag["severity"] == "critical" and bool(flag.get("triggered"))
    ]


def _fake_row(set_id: str, run_mode: str, actual_writes_performed: int) -> dict:
    return {
        "set_id": set_id,
        "set_name": set_id,
        "canonical_key": set_id,
        "run_mode": run_mode,
        "actual_writes_performed": actual_writes_performed,
        "intended_writes_captured_total": 3,
        "persistence_payload_validators_passed": True,
        "strict_db_input_passed": True,
        "semantic_status": {
            "roi": "formula_roi_aligned",
            "value_to_cost_ratio": "value_to_cost_ratio_aligned",
            "probability_to_beat_pack_cost": "value_derived_probability_aligned",
        },
        "warning_flags": [],
        "intended_persistence_targets": ["calculation_runs"],
        "unexpected_write_targets": [],
        "destructive_operations_detected": [],
        "production_probability_table_status": {"production_equals_draft": True},
        "persisted_identifiers": {
            "parent_run_id": f"run-{set_id}",
            "simulation_summary_id": f"summary-{set_id}",
        },
    }


def _fake_pass_payload(*, run_mode: str, actual_writes: int, row_writes: int, intended_writes: int = 6) -> dict:
    return {
        "meta": {
            "generated_at_utc": "2026-01-01T00:00:00+00:00",
            "project": "8",
            "run_mode": run_mode,
            "strict_db_input": True,
            "pack_count": 10,
            "actual_writes_performed_total": actual_writes,
            "intended_writes_captured_total": intended_writes,
            "execute_mode_exists": True,
            "execute_mode_run": run_mode == "execute",
            "real_db_writes_performed": run_mode == "execute" and actual_writes > 0,
        },
        "other_swsh_runtime_guardrail": {"before": {}, "after": {}, "unchanged": True},
        "sv_mega_routing_guardrail": {"changed": False, "all_expected_v2": True, "v2_violations": []},
        "expected_write_table_allowlist": sorted(preflight.EXPECTED_WRITE_TABLE_ALLOWLIST),
        "write_operation_classification": dict(preflight.PERSISTENCE_OPERATION_CLASSIFICATION),
        "real_write_counts_by_table": {"calculation_runs": actual_writes} if actual_writes > 0 else {},
        "real_write_operations_by_table": {"calculation_runs": ["insert"]} if actual_writes > 0 else {},
        "sets": [
            _fake_row("swsh6", run_mode, row_writes),
            _fake_row("swsh7", run_mode, row_writes),
        ],
        "safety_assertions": {"passed": True, "failures": []},
    }


def _mock_run_orchestrator_pass_factory():
    calls = []

    def _runner(**kwargs):
        calls.append(dict(kwargs))
        run_mode = kwargs["run_mode"]
        if run_mode == "dry_run":
            return {
                "payload": _fake_pass_payload(run_mode="dry_run", actual_writes=0, row_writes=0),
                "failures": [],
            }
        return {
            "payload": _fake_pass_payload(run_mode="execute", actual_writes=8, row_writes=1, intended_writes=0),
            "failures": [],
        }

    return _runner, calls


def test_default_mode_does_not_write_and_stays_preflight_ready(tmp_path, monkeypatch):
    runner, _ = _mock_run_orchestrator_pass_factory()
    monkeypatch.setattr(preflight, "_run_orchestrator_pass", runner)

    result = preflight.run_controlled_persistence_preflight(
        json_output_path=tmp_path / "preflight.json",
        markdown_output_path=tmp_path / "preflight.md",
        closure_json_output_path=tmp_path / "closure.json",
        closure_markdown_output_path=tmp_path / "closure.md",
        pack_count=10,
        strict_db_input=True,
        execute=False,
    )

    assert result["preflight"]["meta"]["actual_writes_performed_total"] == 0
    assert result["closure"]["final_decision"] == "closed_controlled_persistence_preflight_ready_for_explicit_execute"


def test_execute_without_confirmation_token_fails_before_writes(tmp_path, monkeypatch):
    called = {"value": 0}

    def _never_called(**kwargs):
        called["value"] += 1
        raise AssertionError("should not be called")

    monkeypatch.setattr(preflight, "_run_orchestrator_pass", _never_called)

    with pytest.raises(RuntimeError, match="requires --confirm-db-writes"):
        preflight.run_controlled_persistence_preflight(
            json_output_path=tmp_path / "preflight.json",
            markdown_output_path=tmp_path / "preflight.md",
            closure_json_output_path=tmp_path / "closure.json",
            closure_markdown_output_path=tmp_path / "closure.md",
            pack_count=10,
            strict_db_input=True,
            execute=True,
            confirm_db_writes="",
        )

    assert called["value"] == 0


def test_confirmation_token_without_execute_does_not_write(tmp_path, monkeypatch):
    runner, calls = _mock_run_orchestrator_pass_factory()
    monkeypatch.setattr(preflight, "_run_orchestrator_pass", runner)

    result = preflight.run_controlled_persistence_preflight(
        json_output_path=tmp_path / "preflight.json",
        markdown_output_path=tmp_path / "preflight.md",
        closure_json_output_path=tmp_path / "closure.json",
        closure_markdown_output_path=tmp_path / "closure.md",
        pack_count=10,
        strict_db_input=True,
        execute=False,
        confirm_db_writes=preflight.EXECUTE_CONFIRMATION_TOKEN,
    )

    assert len(calls) == 1
    assert result["preflight"]["meta"]["actual_writes_performed_total"] == 0
    assert result["closure"]["execute_mode_run"] is False


def test_wrong_confirmation_token_with_execute_fails_before_writes(tmp_path, monkeypatch):
    called = {"value": 0}

    def _never_called(**kwargs):
        called["value"] += 1
        raise AssertionError("should not be called")

    monkeypatch.setattr(preflight, "_run_orchestrator_pass", _never_called)

    with pytest.raises(RuntimeError, match="requires --confirm-db-writes"):
        preflight.run_controlled_persistence_preflight(
            json_output_path=tmp_path / "preflight.json",
            markdown_output_path=tmp_path / "preflight.md",
            closure_json_output_path=tmp_path / "closure.json",
            closure_markdown_output_path=tmp_path / "closure.md",
            pack_count=10,
            strict_db_input=True,
            execute=True,
            confirm_db_writes="wrong-token",
        )

    assert called["value"] == 0


def test_execute_requires_both_flags_and_runs_two_phase(tmp_path, monkeypatch):
    runner, calls = _mock_run_orchestrator_pass_factory()
    monkeypatch.setattr(preflight, "_run_orchestrator_pass", runner)

    result = preflight.run_controlled_persistence_preflight(
        json_output_path=tmp_path / "preflight.json",
        markdown_output_path=tmp_path / "preflight.md",
        closure_json_output_path=tmp_path / "closure.json",
        closure_markdown_output_path=tmp_path / "closure.md",
        pack_count=10,
        strict_db_input=True,
        execute=True,
        confirm_db_writes=preflight.EXECUTE_CONFIRMATION_TOKEN,
    )

    assert [call["run_mode"] for call in calls] == ["dry_run", "execute"]
    assert result["closure"]["execute_mode_run"] is True
    assert result["closure"]["final_decision"] == "closed_controlled_persistence_executed_and_verified"


def test_phase_1_failure_aborts_before_phase_2(tmp_path, monkeypatch):
    calls = []

    def _runner(**kwargs):
        calls.append(dict(kwargs))
        return {
            "payload": _fake_pass_payload(run_mode="dry_run", actual_writes=0, row_writes=0),
            "failures": ["critical preflight blocker"],
        }

    monkeypatch.setattr(preflight, "_run_orchestrator_pass", _runner)

    with pytest.raises(AssertionError, match="critical preflight blocker"):
        preflight.run_controlled_persistence_preflight(
            json_output_path=tmp_path / "preflight.json",
            markdown_output_path=tmp_path / "preflight.md",
            closure_json_output_path=tmp_path / "closure.json",
            closure_markdown_output_path=tmp_path / "closure.md",
            pack_count=10,
            strict_db_input=True,
            execute=True,
            confirm_db_writes=preflight.EXECUTE_CONFIRMATION_TOKEN,
        )

    assert [call["run_mode"] for call in calls] == ["dry_run"]


def test_execute_path_scope_is_swsh6_swsh7_only(tmp_path, monkeypatch):
    runner, _ = _mock_run_orchestrator_pass_factory()
    monkeypatch.setattr(preflight, "_run_orchestrator_pass", runner)

    result = preflight.run_controlled_persistence_preflight(
        json_output_path=tmp_path / "preflight.json",
        markdown_output_path=tmp_path / "preflight.md",
        closure_json_output_path=tmp_path / "closure.json",
        closure_markdown_output_path=tmp_path / "closure.md",
        pack_count=10,
        strict_db_input=True,
        execute=True,
        confirm_db_writes=preflight.EXECUTE_CONFIRMATION_TOKEN,
    )

    assert result["closure"]["swsh6_swsh7_scoped_only"] is True


def test_execute_path_rejects_unexpected_write_targets():
    flags = preflight._build_warning_flags(
        **{**_base_flags_kwargs(), "execute_mode": True, "execute_mode_confirmed": True, "execute_real_writes_expected": True, "unexpected_write_targets": ["rogue_table"]}
    )
    assert "unexpected_write_target" in _critical_codes(flags)


def test_execute_path_rejects_destructive_operations():
    flags = preflight._build_warning_flags(
        **{**_base_flags_kwargs(), "execute_mode": True, "execute_mode_confirmed": True, "execute_real_writes_expected": True, "destructive_operations_detected": ["delete"]}
    )
    assert "destructive_operation_detected" in _critical_codes(flags)


def test_execute_closure_cannot_be_verified_without_real_writes():
    decision = preflight._determine_final_decision(
        execute_mode_exists=True,
        execute_mode_run=True,
        dry_run_preflight_passed=True,
        has_runtime_errors=False,
        has_blockers=False,
        actual_writes_performed_total=0,
        strict_db_input_passed=True,
        scope_is_swsh6_swsh7_only=True,
        expected_non_destructive_write_scope=True,
        semantics_passed=True,
        sv_mega_unchanged=True,
        other_swsh_unchanged=True,
        no_critical_warnings=True,
    )
    assert decision != "closed_controlled_persistence_executed_and_verified"


def test_execute_verification_requires_persisted_ids_for_both_sets():
    flags = preflight._build_warning_flags(
        **{
            **_base_flags_kwargs(),
            "execute_mode": True,
            "execute_mode_confirmed": True,
            "parent_run_id_present": True,
            "execute_real_writes_expected": True,
            "expected_persisted_ids_present": False,
        }
    )
    assert "execute_missing_persisted_ids" in _critical_codes(flags)


def test_execute_row_warning_state_recomputed_from_final_values():
    row = {
        "run_mode": "execute",
        "actual_writes_performed": 0,
        "intended_writes_captured_total": 3,
        "selected_engine": "slot_schema",
        "monte_carlo_v2_bypassed": True,
        "slot_schema_runtime_used": True,
        "production_probability_table_status": {
            "production_has_rare_slot_probability": True,
            "production_equals_draft": True,
            "sum_probability": 1.0,
            "residual_rare_non_negative": True,
        },
        "strict_db_input_source": "db_evr_input_preparation_service",
        "strict_db_fallback_used": False,
        "strict_db_required_columns_present": True,
        "strict_db_usable_price_rows": 1,
        "estimated_pack_price": 1.0,
        "pack_price_source": "db",
        "pack_price_resolution_status": "resolved",
        "reverse_holo_leakage_detected": False,
        "semantic_status": {
            "roi": "formula_roi_aligned",
            "value_to_cost_ratio": "value_to_cost_ratio_aligned",
            "probability_to_beat_pack_cost": "value_derived_probability_aligned",
        },
        "output_payload_json_serializable": True,
        "persistence_payload_validators_passed": True,
        "unexpected_write_targets": [],
        "destructive_operations_detected": [],
        "persisted_identifiers": {
            "parent_run_id": "run-swsh6",
            "simulation_summary_id": "summary-swsh6",
        },
    }

    preflight._recompute_set_row_warning_state(
        row=row,
        sv_mega_routing_status={"changed": False, "all_expected_v2": True, "v2_violations": []},
        other_swsh_guardrail_unchanged=True,
        execute_mode_confirmed=True,
    )
    assert "actual_writes_missing_in_execute_mode" in _critical_codes(row["warning_flags"])
    assert "execute_parent_id_present_but_monitor_writes_zero" in _critical_codes(row["warning_flags"])

    row["actual_writes_performed"] = 1
    preflight._recompute_set_row_warning_state(
        row=row,
        sv_mega_routing_status={"changed": False, "all_expected_v2": True, "v2_violations": []},
        other_swsh_guardrail_unchanged=True,
        execute_mode_confirmed=True,
    )

    critical_codes = _critical_codes(row["warning_flags"])
    assert "actual_writes_missing_in_execute_mode" not in critical_codes
    assert "execute_missing_persisted_ids" not in critical_codes
    assert "execute_parent_id_present_but_monitor_writes_zero" not in critical_codes
    assert row["readiness_status"] == "ready"


def test_extract_persisted_identifiers_reads_run_summary_id_key():
    identifiers = preflight._extract_persisted_identifiers(
        {
            "persisted": {
                "parent": {"run_id": "run-swsh6"},
                "outputs": {"run_summary_id": "summary-swsh6"},
            }
        }
    )

    assert identifiers["parent_run_id"] == "run-swsh6"
    assert identifiers["simulation_summary_id"] == "summary-swsh6"


def test_query_proxy_counts_chained_insert_execute_rows():
    class _Response:
        def __init__(self, data):
            self.data = data

    class _Query:
        def __init__(self, payload=None):
            self.payload = payload

        def insert(self, payload):
            return _Query(payload=payload)

        def execute(self):
            rows = self.payload if isinstance(self.payload, list) else [self.payload]
            return _Response(rows)

    monitor = preflight.DBWriteMonitor(allowlist=["calculation_runs"])
    query = preflight._QueryProxy(_Query(), table_name="calculation_runs", monitor=monitor)

    query.insert([{"id": "r1"}, {"id": "r2"}]).execute()

    assert monitor.operations_by_table["calculation_runs"] == ["insert"]
    assert monitor.write_counts_by_table["calculation_runs"] == 2
    assert monitor.actual_writes_performed_total == 2


def test_monitor_counts_writes_from_repository_supabase_client_path(monkeypatch):
    class _Response:
        def __init__(self, data):
            self.data = data

    class _Query:
        def __init__(self, table_name, payload=None):
            self.table_name = table_name
            self.payload = payload

        def insert(self, payload):
            return _Query(self.table_name, payload=payload)

        def execute(self):
            row = dict(self.payload)
            row.setdefault("id", "fake-id")
            return _Response([row])

    def _fake_table(table_name):
        return _Query(str(table_name))

    monkeypatch.setattr(preflight.supabase_client.supabase, "table", _fake_table)

    monitor = preflight.DBWriteMonitor(allowlist=["calculation_runs"])
    with preflight._monitor_real_db_writes_context(monitor):
        inserted = calculation_runs_repository._insert_required_payload(
            "calculation_runs",
            {
                "target_type": "set",
                "target_id": "set-id",
                "calculation_config_id": "cfg-id",
                "valuation_method": "combined",
                "notes": "note",
                "engine_version": "monte_carlo_v1",
            },
            "test insert",
        )

    assert inserted["id"] == "fake-id"
    assert monitor.operations_by_table["calculation_runs"] == ["insert"]
    assert monitor.write_counts_by_table["calculation_runs"] == 1
    assert monitor.actual_writes_performed_total == 1


def test_execute_global_failures_include_parent_id_zero_write_inconsistency():
    payload = _fake_pass_payload(run_mode="execute", actual_writes=0, row_writes=0)
    payload["meta"]["execute_mode_run"] = True
    payload["sets"][0]["persisted_identifiers"]["parent_run_id"] = "run-swsh6"
    payload["sets"][0]["persisted_identifiers"]["simulation_summary_id"] = None

    failures = preflight._evaluate_global_failures(payload)

    assert any(
        "parent_run_id present while actual_writes_performed_total is 0" in failure
        for failure in failures
    )


def test_dry_run_fails_when_intended_writes_not_captured():
    payload = _fake_pass_payload(run_mode="dry_run", actual_writes=0, row_writes=0, intended_writes=0)

    failures = preflight._evaluate_global_failures(payload)

    assert "intended_writes_captured_total must be > 0 in dry-run" in failures


def test_execute_does_not_fail_solely_for_zero_intended_writes():
    payload = _fake_pass_payload(run_mode="execute", actual_writes=8, row_writes=1, intended_writes=0)

    failures = preflight._evaluate_global_failures(payload)

    assert not any("intended writes must be > 0" in failure for failure in failures)
    assert "intended_writes_captured_total must be > 0 in dry-run" not in failures


def test_execute_fails_if_actual_writes_total_not_positive():
    payload = _fake_pass_payload(run_mode="execute", actual_writes=0, row_writes=0, intended_writes=0)

    failures = preflight._evaluate_global_failures(payload)

    assert "actual_writes_performed_total must be > 0 in execute mode" in failures


def test_execute_fails_if_persisted_ids_missing():
    payload = _fake_pass_payload(run_mode="execute", actual_writes=8, row_writes=1, intended_writes=0)
    payload["sets"][0]["persisted_identifiers"]["simulation_summary_id"] = None

    failures = preflight._evaluate_global_failures(payload)

    assert "swsh6: simulation_summary_id must be present in execute mode" in failures


def test_execute_fails_if_real_write_counts_empty():
    payload = _fake_pass_payload(run_mode="execute", actual_writes=8, row_writes=1, intended_writes=0)
    payload["real_write_counts_by_table"] = {}

    failures = preflight._evaluate_global_failures(payload)

    assert "real_write_counts_by_table must be non-empty in execute mode" in failures


def test_execute_fails_if_unexpected_real_write_table_present():
    payload = _fake_pass_payload(run_mode="execute", actual_writes=8, row_writes=1, intended_writes=0)
    payload["real_write_counts_by_table"]["rogue_table"] = 1

    failures = preflight._evaluate_global_failures(payload)

    assert any("unexpected execute write tables detected" in failure for failure in failures)


def test_execute_fails_if_non_insert_operation_present():
    payload = _fake_pass_payload(run_mode="execute", actual_writes=8, row_writes=1, intended_writes=0)
    payload["real_write_operations_by_table"] = {
        "calculation_runs": ["insert", "update"],
    }

    failures = preflight._evaluate_global_failures(payload)

    assert any("non-insert execute operations detected" in failure for failure in failures)


def test_execute_decision_can_be_verified_with_zero_intended_writes_when_real_writes_present():
    decision = preflight._determine_final_decision(
        execute_mode_exists=True,
        execute_mode_run=True,
        dry_run_preflight_passed=True,
        has_runtime_errors=False,
        has_blockers=False,
        actual_writes_performed_total=8,
        strict_db_input_passed=True,
        scope_is_swsh6_swsh7_only=True,
        expected_non_destructive_write_scope=True,
        semantics_passed=True,
        sv_mega_unchanged=True,
        other_swsh_unchanged=True,
        no_critical_warnings=True,
    )

    assert decision == "closed_controlled_persistence_executed_and_verified"


def test_execute_decision_blocked_when_critical_warnings_remain():
    decision = preflight._determine_final_decision(
        execute_mode_exists=True,
        execute_mode_run=True,
        dry_run_preflight_passed=True,
        has_runtime_errors=False,
        has_blockers=True,
        actual_writes_performed_total=8,
        strict_db_input_passed=True,
        scope_is_swsh6_swsh7_only=True,
        expected_non_destructive_write_scope=True,
        semantics_passed=True,
        sv_mega_unchanged=True,
        other_swsh_unchanged=True,
        no_critical_warnings=False,
    )
    assert decision != "closed_controlled_persistence_executed_and_verified"


def test_existing_scope_and_helper_gate_tests_still_pass():
    set_ids = {target.set_id for target in preflight.TARGETS}
    assert set_ids == {"swsh6", "swsh7"}
    assert preflight._detect_unexpected_write_targets(["calculation_runs"]) == []
    assert preflight._detect_unexpected_write_targets(["calculation_runs", "rogue_table"]) == ["rogue_table"]
    assert preflight._destructive_markers_detected(["insert", "insert"]) == []
    assert preflight._destructive_markers_detected(["insert", "delete", "truncate"]) == ["delete", "truncate"]


def test_markdown_render_includes_decision_and_tables():
    closure = {
        "generated_at_utc": "2026-01-01T00:00:00+00:00",
        "final_decision": "closed_controlled_persistence_preflight_ready_for_explicit_execute",
        "real_db_writes_performed": False,
        "actual_writes_performed_total": 0,
        "intended_writes_captured_total": 5,
        "execute_mode_exists": True,
        "execute_mode_run": False,
        "persistence_approved_for_future_explicit_execute": True,
        "full_intended_write_tables": ["calculation_runs"],
        "destructive_operations_found": False,
        "metrics_semantics_passed": True,
        "strict_db_input_passed": True,
        "swsh6_swsh7_scoped_only": True,
        "sv_mega_unchanged": True,
        "other_swsh_unchanged": True,
        "production_probability_tables_unchanged": True,
        "final_approval_status": "ready_for_explicit_execute",
        "blockers": [],
    }
    md = preflight._render_closure_markdown(closure)
    assert "closed_controlled_persistence_preflight_ready_for_explicit_execute" in md
    assert "calculation_runs" in md


def test_preflight_payload_json_serializable_contract():
    payload = {
        "meta": {"actual_writes_performed_total": 0},
        "sets": [],
        "other_swsh_runtime_guardrail": {"unchanged": True},
        "sv_mega_routing_guardrail": {"changed": False, "all_expected_v2": True},
    }
    assert json.loads(json.dumps(payload))["meta"]["actual_writes_performed_total"] == 0
