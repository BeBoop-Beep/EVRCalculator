"""Project 8 controlled persistence preflight for swsh6/swsh7.

Default mode is strict no-write dry-run and must never mutate DB state.
This preflight executes the real production orchestration path:
backend.jobs.evr_runner.EVRRunOrchestrator.run

Writes are intercepted at repository insert boundaries and captured in-memory
as an intended-write manifest.
"""

from __future__ import annotations

import argparse
import json
import random
import time
from contextlib import contextmanager, nullcontext
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Dict, List, Mapping, Optional, Sequence

import backend.jobs.evr_runner as evr_runner
import backend.simulations.evrSimulator as evr_simulator
from backend.db.repositories import calculation_runs_repository
from backend.db.clients import supabase_client
from backend.scripts.audit_swsh_production_job_dry_run import (
    PROBABILITY_ABSOLUTE_DELTA_THRESHOLD,
    ROI_ABSOLUTE_DELTA_THRESHOLD,
    VALUE_TO_COST_RATIO_ABSOLUTE_DELTA_THRESHOLD,
    _build_input_metadata,
    _compute_formula_roi,
    _compute_semantic_status,
    _extract_probability_to_beat_pack_cost,
    _is_json_serializable,
    _make_input_service_spy,
    _make_runner_compatible_config,
    _output_metrics_present,
    _quantile,
    _safe_float,
    _validate_input_metadata,
)
from backend.scripts.audit_swsh_production_runtime_smoke import (
    TARGETS,
    _capture_other_swsh_runtime_enabled_state,
    _capture_sv_mega_routing_state,
    _compute_probability_table_status,
    _compute_sv_mega_routing_status,
)
from backend.simulations.evrSimulator import _should_use_monte_carlo_v2, get_simulation_engine


DEFAULT_JSON_PATH = Path("logs/audits/swsh_controlled_persistence_preflight.json")
DEFAULT_MD_PATH = Path("backend/docs/audits/SWSH_CONTROLLED_PERSISTENCE_PREFLIGHT.md")
DEFAULT_CLOSURE_JSON_PATH = Path("logs/audits/swsh_project_8_controlled_persistence_gate_closure.json")
DEFAULT_CLOSURE_MD_PATH = Path("backend/docs/audits/SWSH_PROJECT_8_CONTROLLED_PERSISTENCE_GATE_CLOSURE.md")

TARGET_SET_IDS = {"swsh6", "swsh7"}
EXPECTED_WRITE_TABLE_ALLOWLIST = {
    "calculation_configs",
    "calculation_runs",
    "calculation_price_snapshots",
    "simulation_input_cards",
    "simulation_run_summary",
    "simulation_percentiles",
    "simulation_pull_summary",
    "simulation_state_counts",
    "simulation_derived_metrics",
    "simulation_value_distribution_bins",
    "simulation_value_threshold_bins",
    "simulation_etb_summary",
}

PERSISTENCE_OPERATION_CLASSIFICATION = {
    "calculation_configs": "get_or_create",
    "calculation_runs": "insert_only",
    "calculation_price_snapshots": "insert_only",
    "simulation_input_cards": "insert_only",
    "simulation_run_summary": "insert_only",
    "simulation_percentiles": "insert_only",
    "simulation_pull_summary": "insert_only",
    "simulation_state_counts": "insert_only",
    "simulation_derived_metrics": "insert_only",
    "simulation_value_distribution_bins": "insert_only",
    "simulation_value_threshold_bins": "insert_only",
    "simulation_etb_summary": "insert_only",
}

DESTRUCTIVE_MARKERS = {
    "delete",
    "truncate",
    "drop",
    "overwrite",
    "replace",
    "update",
}

ROI_FORMULA = "(average_pack_value - estimated_pack_price) / estimated_pack_price"
METRIC_SEMANTICS_VERSION = "formula_roi_v2"
EXECUTE_CONFIRMATION_TOKEN = "swsh6-swsh7-formula-roi-v2"


class DBWriteMonitor:
    """Track write operations in execute mode and enforce allowlisted insert-only writes."""

    def __init__(self, *, allowlist: Sequence[str]) -> None:
        self.allowlist = {str(table) for table in allowlist}
        self.write_counts_by_table: Dict[str, int] = {}
        self.operations_by_table: Dict[str, List[str]] = {}
        self.actual_writes_performed_total = 0

    def register_operation(self, *, table_name: str, operation: str) -> None:
        table = str(table_name)
        op = str(operation).strip().lower()
        self.operations_by_table.setdefault(table, []).append(op)

        if op in DESTRUCTIVE_MARKERS:
            raise RuntimeError(f"Destructive operation '{op}' is not permitted in execute mode.")

        if op not in {"insert"}:
            raise RuntimeError(f"Write operation '{op}' is not permitted in execute mode.")

        if table not in self.allowlist:
            raise RuntimeError(f"Unexpected write target '{table}' is not permitted in execute mode.")

    def register_execute_result(self, *, table_name: str, row_count: int) -> None:
        table = str(table_name)
        count = max(0, int(row_count))
        self.write_counts_by_table[table] = int(self.write_counts_by_table.get(table, 0)) + count
        self.actual_writes_performed_total += count


class _QueryProxy:
    def __init__(
        self,
        query: Any,
        *,
        table_name: str,
        monitor: DBWriteMonitor,
        pending_write_operations: Optional[List[str]] = None,
    ) -> None:
        self._query = query
        self._table_name = str(table_name)
        self._monitor = monitor
        # Keep pending operations shared across chained query-builder objects.
        self._pending_write_operations = pending_write_operations if pending_write_operations is not None else []

    def __getattr__(self, name: str) -> Any:
        attr = getattr(self._query, name)
        if not callable(attr):
            return attr

        def _wrapped(*args: Any, **kwargs: Any) -> Any:
            op = str(name).strip().lower()
            if op in {"insert", "upsert", "update", "delete"}:
                self._monitor.register_operation(table_name=self._table_name, operation=op)
                self._pending_write_operations.append(op)

            result = attr(*args, **kwargs)

            if op == "execute" and self._pending_write_operations:
                data = getattr(result, "data", None)
                if isinstance(data, list):
                    row_count = len(data)
                elif data is None:
                    row_count = 0
                else:
                    row_count = 1

                for _ in self._pending_write_operations:
                    self._monitor.register_execute_result(table_name=self._table_name, row_count=row_count)
                self._pending_write_operations.clear()

            if result is self._query:
                return self
            if hasattr(result, "execute"):
                return _QueryProxy(
                    result,
                    table_name=self._table_name,
                    monitor=self._monitor,
                    pending_write_operations=self._pending_write_operations,
                )
            return result

        return _wrapped


@contextmanager
def _monitor_real_db_writes_context(monitor: DBWriteMonitor):
    original_table = supabase_client.supabase.table

    def _table_wrapper(table_name: str) -> _QueryProxy:
        query = original_table(table_name)
        return _QueryProxy(query, table_name=str(table_name), monitor=monitor)

    try:
        supabase_client.supabase.table = _table_wrapper
        yield
    finally:
        supabase_client.supabase.table = original_table


class ControlledPersistenceHarness:
    """Collect intended writes and simulation summaries while blocking DB mutation."""

    def __init__(self) -> None:
        self.current_set_id: Optional[str] = None
        self.current_set_canonical_key: Optional[str] = None
        self.current_set_name: Optional[str] = None

        self.actual_writes_performed_total = 0
        self.next_id = 1

        self.intended_write_counts_by_set: Dict[str, Dict[str, int]] = {}
        self.intended_operations_by_set: Dict[str, List[str]] = {}
        self.insert_payload_keys_by_set: Dict[str, Dict[str, List[str]]] = {}

        self.sim_output_summary_by_set: Dict[str, Dict[str, Any]] = {}
        self.input_metadata_by_canonical_key: Dict[str, Dict[str, Any]] = {}
        self.persister_payload_keys_by_set: Dict[str, Dict[str, List[str]]] = {}

    def set_current_set(self, *, set_id: str, canonical_key: str, set_name: str) -> None:
        self.current_set_id = str(set_id)
        self.current_set_canonical_key = str(canonical_key)
        self.current_set_name = str(set_name)
        self.intended_write_counts_by_set.setdefault(self.current_set_id, {})
        self.intended_operations_by_set.setdefault(self.current_set_id, [])
        self.insert_payload_keys_by_set.setdefault(self.current_set_id, {})

    def _bump_id(self) -> str:
        token = f"dry-id-{self.next_id}"
        self.next_id += 1
        return token

    def _record_insert(self, *, table_name: str, payload: Mapping[str, Any]) -> None:
        if self.current_set_id is None:
            return

        table = str(table_name)
        counts = self.intended_write_counts_by_set.setdefault(self.current_set_id, {})
        counts[table] = int(counts.get(table, 0)) + 1

        operations = self.intended_operations_by_set.setdefault(self.current_set_id, [])
        operations.append("insert")

        key_map = self.insert_payload_keys_by_set.setdefault(self.current_set_id, {})
        key_map.setdefault(table, sorted(payload.keys()))

    def insert_required_payload_spy(self, table_name: str, payload: Dict[str, Any], context: str) -> Dict[str, Any]:
        _ = context
        self._record_insert(table_name=table_name, payload=payload)
        row = dict(payload)
        row.setdefault("id", self._bump_id())
        return row


def _capture_output_summary(*, harness: ControlledPersistenceHarness, sim_results: Mapping[str, Any], derived: Mapping[str, Any]) -> None:
    if harness.current_set_id is None:
        return

    values = [float(v) for v in (sim_results.get("values") or [])]
    pack_decision = (derived or {}).get("pack_decision_metrics") if isinstance(derived, Mapping) else {}
    pack_cost = _safe_float((pack_decision or {}).get("pack_cost"), 0.0)

    probability_to_beat_pack_cost = (
        float(sum(1 for value in values if value >= pack_cost)) / float(len(values)) if values else 0.0
    )

    harness.sim_output_summary_by_set[harness.current_set_id] = {
        "value_count": len(values),
        "mean_from_values": (float(sum(values)) / float(len(values))) if values else 0.0,
        "median_from_values": _quantile(values, 0.5) if values else 0.0,
        "p05": _quantile(values, 0.05) if values else 0.0,
        "p95": _quantile(values, 0.95) if values else 0.0,
        "p99": _quantile(values, 0.99) if values else 0.0,
        "pack_cost_used": pack_cost,
        "probability_to_beat_pack_cost_from_values": probability_to_beat_pack_cost,
    }


def _normalized_sim_results_for_persistence(sim_results: Mapping[str, Any]) -> Dict[str, Any]:
    values = [float(v) for v in (sim_results.get("values") or [])]
    normalized = dict(sim_results)

    if "percentiles" not in normalized or not isinstance(normalized.get("percentiles"), Mapping):
        normalized["percentiles"] = {
            "5th": _quantile(values, 0.05),
            "25th": _quantile(values, 0.25),
            "50th": _quantile(values, 0.50),
            "75th": _quantile(values, 0.75),
            "90th": _quantile(values, 0.90),
            "95th": _quantile(values, 0.95),
            "99th": _quantile(values, 0.99),
        }

    if "rarity_pull_counts" not in normalized or not isinstance(normalized.get("rarity_pull_counts"), Mapping):
        normalized["rarity_pull_counts"] = {}

    if "rarity_value_totals" not in normalized or not isinstance(normalized.get("rarity_value_totals"), Mapping):
        normalized["rarity_value_totals"] = {
            str(k): 0.0 for k in (normalized.get("rarity_pull_counts") or {}).keys()
        }

    has_pack_path_counts = isinstance(normalized.get("pack_path_counts"), Mapping)
    has_pack_state_counts = isinstance(normalized.get("pack_state_counts"), Mapping)
    if not has_pack_path_counts and not has_pack_state_counts:
        normalized["pack_path_counts"] = {
            "slot_schema": len(values),
        }

    return normalized


@contextmanager
def _controlled_no_write_context(
    harness: ControlledPersistenceHarness,
    *,
    pack_count: int,
    strict_db_input: bool,
    intercept_writes: bool = True,
):
    if int(pack_count) <= 0:
        raise ValueError("pack_count must be > 0")

    original_input_service = evr_runner.EVRInputPreparationService
    original_resolve_set_config = evr_runner._resolve_set_config
    original_persist_outputs = evr_runner.persist_simulation_outputs

    original_run_simulation = evr_simulator.run_simulation
    original_run_simulation_v2 = evr_simulator.run_simulation_v2
    original_simulate_slot_schema_packs = evr_simulator.simulate_slot_schema_packs

    original_insert_required_payload = calculation_runs_repository._insert_required_payload

    input_service_spy_cls = _make_input_service_spy(
        harness=harness,
        strict_db_input=bool(strict_db_input),
        original_service_cls=original_input_service,
    )

    target_lookup: Dict[str, Any] = {}
    for target in TARGETS:
        config_cls = _make_runner_compatible_config(target.production_config)
        target_lookup[str(target.canonical_key).strip().lower()] = (config_cls, target.canonical_key)
        target_lookup[str(target.set_id).strip().lower()] = (config_cls, target.canonical_key)
        target_lookup[str(target.set_name).strip().lower()] = (config_cls, target.canonical_key)

    def _resolve_set_config_override(target_set_identifier: str) -> tuple[Any, str]:
        key = str(target_set_identifier or "").strip().lower()
        if key in target_lookup:
            return target_lookup[key]
        return original_resolve_set_config(target_set_identifier)

    def _run_simulation_override(*args: Any, **kwargs: Any) -> Dict[str, Any]:
        kwargs["n"] = int(pack_count)
        return original_run_simulation(*args, **kwargs)

    def _run_simulation_v2_override(*args: Any, **kwargs: Any) -> Dict[str, Any]:
        kwargs["n"] = int(pack_count)
        return original_run_simulation_v2(*args, **kwargs)

    def _simulate_slot_schema_packs_override(*args: Any, **kwargs: Any) -> Dict[str, Any]:
        kwargs["num_packs"] = int(pack_count)
        return original_simulate_slot_schema_packs(*args, **kwargs)

    def _persist_simulation_outputs_wrapper(*, run_id: Any, sim_results: Dict[str, Any], pack_metrics: Dict[str, Any], derived: Dict[str, Any] | None) -> Dict[str, Any]:
        normalized_sim_results = _normalized_sim_results_for_persistence(sim_results)
        _capture_output_summary(harness=harness, sim_results=normalized_sim_results, derived=derived or {})
        result = original_persist_outputs(
            run_id=run_id,
            sim_results=normalized_sim_results,
            pack_metrics=pack_metrics,
            derived=derived,
        )
        if harness.current_set_id is not None:
            harness.persister_payload_keys_by_set.setdefault(harness.current_set_id, {})[
                "simulation_outputs_return"
            ] = sorted(result.keys())
        return result

    try:
        evr_runner.EVRInputPreparationService = input_service_spy_cls
        evr_runner._resolve_set_config = _resolve_set_config_override
        evr_runner.persist_simulation_outputs = _persist_simulation_outputs_wrapper

        evr_simulator.run_simulation = _run_simulation_override
        evr_simulator.run_simulation_v2 = _run_simulation_v2_override
        evr_simulator.simulate_slot_schema_packs = _simulate_slot_schema_packs_override

        if intercept_writes:
            calculation_runs_repository._insert_required_payload = harness.insert_required_payload_spy

        yield
    finally:
        evr_runner.EVRInputPreparationService = original_input_service
        evr_runner._resolve_set_config = original_resolve_set_config
        evr_runner.persist_simulation_outputs = original_persist_outputs

        evr_simulator.run_simulation = original_run_simulation
        evr_simulator.run_simulation_v2 = original_run_simulation_v2
        evr_simulator.simulate_slot_schema_packs = original_simulate_slot_schema_packs

        if intercept_writes:
            calculation_runs_repository._insert_required_payload = original_insert_required_payload


def _parse_manifest_set_ids(rows: Sequence[Mapping[str, Any]]) -> List[str]:
    return sorted({str(row.get("set_id") or "") for row in rows if row.get("set_id")})


def _detect_unexpected_write_targets(targets: Sequence[str]) -> List[str]:
    return sorted(set(str(target) for target in targets) - set(EXPECTED_WRITE_TABLE_ALLOWLIST))


def _destructive_markers_detected(operations: Sequence[str]) -> List[str]:
    markers: List[str] = []
    for op in operations:
        op_lower = str(op).strip().lower()
        if op_lower in DESTRUCTIVE_MARKERS:
            markers.append(op_lower)
    return sorted(set(markers))


def _build_warning_flags(
    *,
    execute_mode: bool,
    actual_writes_performed: int,
    intended_write_total: int,
    target_scope: Sequence[str],
    simulation_engine: str,
    monte_carlo_v2_bypassed: bool,
    slot_schema_runtime_used: bool,
    production_has_rare_slot_probability: bool,
    production_probability_equals_draft: bool,
    sum_probability: float,
    residual_rare_non_negative: bool,
    strict_db_input_source_ok: bool,
    strict_db_fallback_not_used: bool,
    strict_db_required_columns_present: bool,
    usable_price_rows_positive: bool,
    estimated_pack_price_present: bool,
    pack_price_source_present: bool,
    reverse_holo_leakage_detected: Optional[bool],
    roi_consistency_passed: bool,
    value_to_cost_ratio_consistency_passed: bool,
    probability_to_beat_pack_cost_consistency_passed: bool,
    output_payload_json_serializable: bool,
    persistence_payload_validators_passed: bool,
    unexpected_write_targets: Sequence[str],
    destructive_operations_detected: Sequence[str],
    sv_mega_routing_status: Mapping[str, Any],
    other_swsh_guardrail_unchanged: bool,
    execute_mode_confirmed: bool,
    parent_run_id_present: bool,
    expected_persisted_ids_present: bool,
    execute_real_writes_expected: bool,
) -> List[Dict[str, Any]]:
    flags: List[Dict[str, Any]] = []

    def emit(code: str, severity: str, triggered: bool, detail: str, value: Any = None) -> None:
        flags.append(
            {
                "code": code,
                "severity": severity,
                "triggered": bool(triggered),
                "detail": detail,
                "value": value,
            }
        )

    emit(
        "execute_mode_not_confirmed",
        "critical",
        bool(execute_mode) and not bool(execute_mode_confirmed),
        "Execute mode requires explicit confirmation token approval.",
    )
    emit(
        "actual_writes_missing_in_execute_mode",
        "critical",
        bool(execute_real_writes_expected) and int(actual_writes_performed) <= 0,
        "Execute mode requires real writes > 0.",
    )
    emit(
        "actual_writes_detected_in_dry_run",
        "critical",
        (not bool(execute_mode)) and int(actual_writes_performed) > 0,
        "Dry-run must not perform actual writes.",
    )
    emit(
        "no_intended_writes_captured",
        "critical",
        (not bool(execute_real_writes_expected)) and int(intended_write_total) <= 0,
        "No intended writes captured.",
    )
    emit(
        "target_scope_violation",
        "critical",
        sorted(str(v) for v in target_scope) != sorted(TARGET_SET_IDS),
        "Scope must be exactly swsh6/swsh7.",
        value={"target_scope": sorted(str(v) for v in target_scope)},
    )
    emit("wrong_engine", "critical", str(simulation_engine) != "slot_schema", "Expected slot_schema engine.")
    emit("v2_not_bypassed", "critical", not bool(monte_carlo_v2_bypassed), "Expected Monte Carlo V2 bypass.")
    emit(
        "slot_schema_runtime_disabled",
        "critical",
        not bool(slot_schema_runtime_used),
        "Expected SLOT_SCHEMA_RUNTIME_ENABLED path.",
    )
    emit(
        "production_probability_missing",
        "critical",
        not bool(production_has_rare_slot_probability),
        "RARE_SLOT_PROBABILITY missing.",
    )
    emit(
        "production_probability_mismatch",
        "critical",
        not bool(production_probability_equals_draft),
        "Production RARE_SLOT_PROBABILITY must equal draft table.",
    )
    emit(
        "production_probability_sum_invalid",
        "critical",
        abs(float(sum_probability) - 1.0) > 1e-9,
        "Production probability sum must be approximately 1.",
        value={"sum_probability": float(sum_probability)},
    )
    emit(
        "residual_rare_negative",
        "critical",
        not bool(residual_rare_non_negative),
        "Residual rare probability must be non-negative.",
    )
    emit(
        "strict_db_source_invalid",
        "critical",
        not bool(strict_db_input_source_ok),
        "Strict DB source must be db_evr_input_preparation_service.",
    )
    emit(
        "strict_db_fallback_used",
        "critical",
        not bool(strict_db_fallback_not_used),
        "Strict DB mode forbids fallback input.",
    )
    emit(
        "strict_db_columns_missing",
        "critical",
        not bool(strict_db_required_columns_present),
        "Strict DB mode requires key input columns.",
    )
    emit(
        "strict_db_usable_price_rows_missing",
        "critical",
        not bool(usable_price_rows_positive),
        "Strict DB mode requires usable price rows > 0.",
    )
    emit(
        "pack_price_missing_or_invalid",
        "critical",
        not bool(estimated_pack_price_present),
        "Estimated pack price must be present and > 0.",
    )
    emit(
        "pack_price_source_missing",
        "critical",
        not bool(pack_price_source_present),
        "Pack price source/status must be recorded.",
    )
    emit(
        "reverse_holo_leakage_detected",
        "critical",
        reverse_holo_leakage_detected is True,
        "Reverse-holo leakage detected.",
    )
    emit("roi_semantic_mismatch", "critical", not bool(roi_consistency_passed), "ROI semantic mismatch.")
    emit(
        "value_to_cost_ratio_semantic_mismatch",
        "critical",
        not bool(value_to_cost_ratio_consistency_passed),
        "value_to_cost_ratio semantic mismatch.",
    )
    emit(
        "probability_to_beat_cost_semantic_mismatch",
        "critical",
        not bool(probability_to_beat_pack_cost_consistency_passed),
        "probability_to_beat_pack_cost semantic mismatch.",
    )
    emit(
        "output_not_json_serializable",
        "critical",
        not bool(output_payload_json_serializable),
        "Manifest payload is not JSON serializable.",
    )
    emit(
        "persistence_payload_validator_failure",
        "critical",
        not bool(persistence_payload_validators_passed),
        "Persistence payload validators failed during dry-run interception.",
    )
    emit(
        "unexpected_write_target",
        "critical",
        len(unexpected_write_targets) > 0,
        "Unexpected write target table detected.",
        value={"unexpected_write_targets": list(unexpected_write_targets)},
    )
    emit(
        "destructive_operation_detected",
        "critical",
        len(destructive_operations_detected) > 0,
        "Destructive operation marker detected.",
        value={"destructive_operations_detected": list(destructive_operations_detected)},
    )
    emit(
        "sv_mega_routing_changed",
        "critical",
        bool(sv_mega_routing_status.get("changed")) or not bool(sv_mega_routing_status.get("all_expected_v2")),
        "SV/Mega routing changed or no longer all v2.",
        value={
            "changed": bool(sv_mega_routing_status.get("changed")),
            "all_expected_v2": bool(sv_mega_routing_status.get("all_expected_v2")),
            "v2_violations": sv_mega_routing_status.get("v2_violations") or [],
        },
    )
    emit(
        "other_swsh_runtime_changed",
        "critical",
        not bool(other_swsh_guardrail_unchanged),
        "Other SWSH runtime-enabled state changed.",
    )
    emit(
        "execute_missing_persisted_ids",
        "critical",
        bool(execute_real_writes_expected) and not bool(expected_persisted_ids_present),
        "Execute mode requires persisted IDs for both swsh6/swsh7 outputs.",
    )
    emit(
        "execute_parent_id_present_but_monitor_writes_zero",
        "critical",
        bool(execute_real_writes_expected) and bool(parent_run_id_present) and int(actual_writes_performed) <= 0,
        "Execute mode returned parent_run_id but DB write monitor counted zero rows; inspect persistence artifacts before rerun.",
    )

    return flags


def _evaluate_global_failures(payload: Mapping[str, Any]) -> List[str]:
    failures: List[str] = []

    meta = payload.get("meta", {})
    run_mode = str(meta.get("run_mode") or "dry_run")
    execute_mode_run = bool(meta.get("execute_mode_run"))
    actual_writes = int(meta.get("actual_writes_performed_total") or 0)
    real_db_writes_performed = bool(meta.get("real_db_writes_performed"))
    real_write_counts_by_table = dict(payload.get("real_write_counts_by_table") or {})
    real_write_operations_by_table = dict(payload.get("real_write_operations_by_table") or {})

    if run_mode == "dry_run" and actual_writes != 0:
        failures.append("actual_writes_performed_total must be 0 in dry-run")

    if run_mode == "dry_run" and int(meta.get("intended_writes_captured_total") or 0) <= 0:
        failures.append("intended_writes_captured_total must be > 0 in dry-run")

    if run_mode == "execute" and execute_mode_run and actual_writes <= 0:
        failures.append("actual_writes_performed_total must be > 0 in execute mode")

    if run_mode == "execute" and execute_mode_run and not real_db_writes_performed:
        failures.append("real_db_writes_performed must be true in execute mode")

    if run_mode == "execute" and execute_mode_run and len(real_write_counts_by_table) == 0:
        failures.append("real_write_counts_by_table must be non-empty in execute mode")

    unexpected_real_write_tables = sorted(
        set(str(table) for table in real_write_counts_by_table.keys()) - set(EXPECTED_WRITE_TABLE_ALLOWLIST)
    )
    if unexpected_real_write_tables:
        failures.append(
            f"unexpected execute write tables detected: {unexpected_real_write_tables}"
        )

    non_insert_operations = sorted(
        {
            str(op).strip().lower()
            for operations in real_write_operations_by_table.values()
            for op in (operations or [])
            if str(op).strip().lower() != "insert"
        }
    )
    if non_insert_operations:
        failures.append(
            f"non-insert execute operations detected: {non_insert_operations}"
        )

    set_scope = _parse_manifest_set_ids(payload.get("sets") or [])
    if set_scope != sorted(TARGET_SET_IDS):
        failures.append(f"target scope must be exactly {sorted(TARGET_SET_IDS)}")

    for row in payload.get("sets", []):
        set_id = str(row.get("set_id"))

        critical = [
            flag.get("code")
            for flag in (row.get("warning_flags") or [])
            if flag.get("severity") == "critical" and bool(flag.get("triggered"))
        ]
        if critical:
            failures.append(f"{set_id}: critical flags triggered {critical}")

        row_writes = int(row.get("actual_writes_performed") or 0)
        if run_mode == "dry_run" and row_writes != 0:
            failures.append(f"{set_id}: actual_writes_performed must be 0 in dry-run")
        if run_mode == "execute" and execute_mode_run and row_writes <= 0:
            failures.append(f"{set_id}: actual_writes_performed must be > 0 in execute mode")

        persisted_identifiers = row.get("persisted_identifiers") or {}
        if (
            run_mode == "execute"
            and execute_mode_run
            and actual_writes <= 0
            and bool(persisted_identifiers.get("parent_run_id"))
        ):
            failures.append(
                f"{set_id}: parent_run_id present while actual_writes_performed_total is 0; execute monitor inconsistency requires read-only DB inspection"
            )

        if run_mode == "dry_run" and int(row.get("intended_writes_captured_total") or 0) <= 0:
            failures.append(f"{set_id}: intended writes must be > 0")

        if run_mode == "execute" and execute_mode_run:
            if not bool(persisted_identifiers.get("parent_run_id")):
                failures.append(f"{set_id}: parent_run_id must be present in execute mode")
            if not bool(persisted_identifiers.get("simulation_summary_id")):
                failures.append(f"{set_id}: simulation_summary_id must be present in execute mode")

        if not bool(row.get("persistence_payload_validators_passed")):
            failures.append(f"{set_id}: persistence payload validators did not pass")

    sv_mega = payload.get("sv_mega_routing_guardrail", {})
    if bool(sv_mega.get("changed")) or not bool(sv_mega.get("all_expected_v2")):
        failures.append("SV/Mega routing guardrail failed")

    other_swsh = payload.get("other_swsh_runtime_guardrail", {})
    if not bool(other_swsh.get("unchanged")):
        failures.append("Other SWSH runtime guardrail failed")

    return failures


def _determine_final_decision(
    *,
    execute_mode_exists: bool,
    execute_mode_run: bool,
    dry_run_preflight_passed: bool,
    has_runtime_errors: bool,
    has_blockers: bool,
    actual_writes_performed_total: int,
    strict_db_input_passed: bool,
    scope_is_swsh6_swsh7_only: bool,
    expected_non_destructive_write_scope: bool,
    semantics_passed: bool,
    sv_mega_unchanged: bool,
    other_swsh_unchanged: bool,
    no_critical_warnings: bool,
) -> str:
    if has_runtime_errors:
        return "not_closed_blockers_remaining"

    if execute_mode_run and int(actual_writes_performed_total) > 0 and not has_blockers:
        return "closed_controlled_persistence_executed_and_verified"

    ready = all(
        [
            dry_run_preflight_passed,
            int(actual_writes_performed_total) == 0,
            strict_db_input_passed,
            scope_is_swsh6_swsh7_only,
            expected_non_destructive_write_scope,
            semantics_passed,
            sv_mega_unchanged,
            other_swsh_unchanged,
            no_critical_warnings,
        ]
    )

    if ready:
        return "closed_controlled_persistence_preflight_ready_for_explicit_execute"

    if not has_runtime_errors and has_blockers:
        return "closed_controlled_persistence_blocked_on_preflight"

    return "not_closed_blockers_remaining"


def _extract_persisted_identifiers(result: Mapping[str, Any]) -> Dict[str, Any]:
    persisted = result.get("persisted") or {}
    parent = persisted.get("parent") or {}
    outputs = persisted.get("outputs") or {}
    return {
        "parent_run_id": parent.get("run_id") or parent.get("id"),
        "simulation_summary_id": outputs.get("run_summary_id") or outputs.get("summary_id") or outputs.get("simulation_summary_id"),
        "simulation_etb_summary_id": outputs.get("etb_summary_id"),
    }


def _render_preflight_markdown(payload: Mapping[str, Any]) -> str:
    lines: List[str] = []
    lines.append("# SWSH Controlled Persistence Preflight")
    lines.append("")
    lines.append(f"Generated: {payload.get('meta', {}).get('generated_at_utc', '')}")
    lines.append("")
    lines.append("Default run mode is dry-run with no DB writes.")
    lines.append("")
    lines.append("## Global")
    lines.append("")
    lines.append(f"- Run mode: {payload.get('meta', {}).get('run_mode')}")
    lines.append(f"- Strict DB input: {payload.get('meta', {}).get('strict_db_input')}")
    lines.append(f"- Actual writes performed total: {payload.get('meta', {}).get('actual_writes_performed_total')}")
    lines.append(f"- Intended writes captured total: {payload.get('meta', {}).get('intended_writes_captured_total')}")
    lines.append(f"- Safety assertions passed: {payload.get('safety_assertions', {}).get('passed')}")
    lines.append("")

    for row in payload.get("sets", []):
        lines.append(f"## {row.get('set_name')} ({row.get('set_id')})")
        lines.append("")
        lines.append(f"- canonical_key: {row.get('canonical_key')}")
        lines.append(f"- run mode: {row.get('run_mode')}")
        lines.append(f"- selected engine: {row.get('selected_engine')}")
        lines.append(f"- pack_count: {row.get('pack_count')}")
        lines.append(f"- estimated_pack_price: {row.get('estimated_pack_price')}")
        lines.append(
            "- pack price source/status: "
            f"{row.get('pack_price_source')} / {row.get('pack_price_resolution_status')}"
        )
        lines.append(f"- average_pack_value: {row.get('average_pack_value')}")
        lines.append(f"- median_pack_value: {row.get('median_pack_value')}")
        lines.append(f"- formula ROI: {row.get('formula_roi')}")
        lines.append(f"- value_to_cost_ratio: {row.get('value_to_cost_ratio')}")
        lines.append(f"- probability_to_beat_pack_cost: {row.get('probability_to_beat_pack_cost')}")
        lines.append(f"- P05/P95/P99: {row.get('p05')} / {row.get('p95')} / {row.get('p99')}")
        lines.append(f"- metric_semantics_version: {row.get('metric_semantics_version')}")
        lines.append(f"- persistence payload validators passed: {row.get('persistence_payload_validators_passed')}")
        lines.append(f"- intended persistence targets: {', '.join(row.get('intended_persistence_targets') or [])}")
        lines.append(f"- intended write counts: {json.dumps(row.get('intended_write_counts') or {}, sort_keys=True)}")
        lines.append(f"- expected parent run payload keys: {', '.join(row.get('expected_parent_run_payload_keys') or [])}")
        lines.append(
            "- expected simulation output payload keys: "
            f"{', '.join(row.get('expected_simulation_output_payload_keys') or [])}"
        )
        lines.append(f"- readiness_status: {row.get('readiness_status')}")

        triggered = [flag for flag in (row.get("warning_flags") or []) if flag.get("triggered")]
        lines.append("")
        lines.append("### Triggered Warning Flags")
        lines.append("")
        if not triggered:
            lines.append("- None")
        else:
            for flag in triggered:
                lines.append(f"- [{flag.get('severity')}] {flag.get('code')}: {flag.get('detail')}")
        lines.append("")

    lines.append("## Write Operation Classification")
    lines.append("")
    for table in sorted(PERSISTENCE_OPERATION_CLASSIFICATION):
        lines.append(f"- {table}: {PERSISTENCE_OPERATION_CLASSIFICATION[table]}")
    lines.append("")

    return "\n".join(lines).rstrip() + "\n"


def _render_closure_markdown(closure: Mapping[str, Any]) -> str:
    lines: List[str] = []
    lines.append("# Project 8 Controlled Persistence Gate Closure")
    lines.append("")
    lines.append(f"Generated: {closure.get('generated_at_utc')}")
    lines.append("")
    lines.append(f"- final_decision: {closure.get('final_decision')}")
    lines.append(f"- real_db_writes_performed: {closure.get('real_db_writes_performed')}")
    lines.append(f"- actual_writes_performed_total: {closure.get('actual_writes_performed_total')}")
    lines.append(f"- intended_writes_captured_total: {closure.get('intended_writes_captured_total')}")
    lines.append(f"- execute_mode_exists: {closure.get('execute_mode_exists')}")
    lines.append(f"- execute_mode_run: {closure.get('execute_mode_run')}")
    lines.append(f"- persistence_approved_for_future_explicit_execute: {closure.get('persistence_approved_for_future_explicit_execute')}")
    lines.append(f"- full_intended_write_tables: {', '.join(closure.get('full_intended_write_tables') or [])}")
    lines.append(f"- destructive_operations_found: {closure.get('destructive_operations_found')}")
    lines.append(f"- metrics_semantics_passed: {closure.get('metrics_semantics_passed')}")
    lines.append(f"- strict_db_input_passed: {closure.get('strict_db_input_passed')}")
    lines.append(f"- swsh6_swsh7_scoped_only: {closure.get('swsh6_swsh7_scoped_only')}")
    lines.append(f"- sv_mega_unchanged: {closure.get('sv_mega_unchanged')}")
    lines.append(f"- other_swsh_unchanged: {closure.get('other_swsh_unchanged')}")
    lines.append(f"- production_probability_tables_unchanged: {closure.get('production_probability_tables_unchanged')}")
    lines.append(f"- final_approval_status: {closure.get('final_approval_status')}")
    lines.append("")
    blockers = closure.get("blockers") or []
    lines.append("## Blockers")
    lines.append("")
    if not blockers:
        lines.append("- None")
    else:
        for blocker in blockers:
            lines.append(f"- {blocker}")
    lines.append("")
    return "\n".join(lines).rstrip() + "\n"


def _build_set_row(
    *,
    target: Any,
    result: Mapping[str, Any],
    harness: ControlledPersistenceHarness,
    strict_db_input: bool,
    run_mode: str,
    sv_mega_routing_status: Mapping[str, Any],
    other_swsh_guardrail_unchanged: bool,
    actual_writes_performed: int,
    execute_mode_confirmed: bool,
    execute_real_writes_expected: bool,
    persisted_identifiers: Mapping[str, Any],
) -> Dict[str, Any]:
    probability_status = _compute_probability_table_status(target)

    input_metadata = harness.input_metadata_by_canonical_key.get(target.canonical_key, {})
    strict_db_input_passed = True
    try:
        _validate_input_metadata(input_metadata, strict_db_input=bool(strict_db_input))
    except Exception:
        strict_db_input_passed = False

    set_counts = harness.intended_write_counts_by_set.get(target.set_id, {})
    intended_targets = sorted(set_counts.keys())
    intended_total = int(sum(int(v) for v in set_counts.values()))

    unexpected_write_targets = _detect_unexpected_write_targets(intended_targets)
    destructive_operations_detected = _destructive_markers_detected(
        harness.intended_operations_by_set.get(target.set_id, [])
    )

    pack_comparison = (result.get("pack_value_vs_cost_comparison") or {}).get("simulated_mean_pack_value_vs_pack_cost", {})
    median_pack_comparison = (result.get("pack_value_vs_cost_comparison") or {}).get(
        "simulated_median_pack_value_vs_pack_cost", {}
    )

    estimated_pack_price = _safe_float(result.get("pack_price"), 0.0)
    sim_summary = harness.sim_output_summary_by_set.get(target.set_id, {})
    average_pack_value = _safe_float(sim_summary.get("mean_from_values"), _safe_float(pack_comparison.get("expected_value"), 0.0))
    median_pack_value = _safe_float(sim_summary.get("median_from_values"), _safe_float(median_pack_comparison.get("expected_value"), 0.0))

    formula_roi = _compute_formula_roi(
        average_pack_value=average_pack_value,
        estimated_pack_price=estimated_pack_price,
    )
    reported_roi = _safe_float(pack_comparison.get("roi"), 0.0)
    roi_abs_delta = abs(float(reported_roi) - float(formula_roi))
    roi_consistency_passed = roi_abs_delta <= ROI_ABSOLUTE_DELTA_THRESHOLD

    reported_value_to_cost_ratio = _safe_float(pack_comparison.get("value_to_cost_ratio"), 0.0)
    expected_value_to_cost_ratio = (average_pack_value / estimated_pack_price) if estimated_pack_price > 0 else 0.0
    ratio_abs_delta = abs(float(reported_value_to_cost_ratio) - float(expected_value_to_cost_ratio))
    value_to_cost_ratio_consistency_passed = ratio_abs_delta <= VALUE_TO_COST_RATIO_ABSOLUTE_DELTA_THRESHOLD

    reported_probability = _extract_probability_to_beat_pack_cost(result_payload=result)
    probability_from_values = _safe_float(sim_summary.get("probability_to_beat_pack_cost_from_values"), 0.0)
    probability_abs_delta = abs(float(reported_probability) - float(probability_from_values))
    probability_consistency_passed = probability_abs_delta <= PROBABILITY_ABSOLUTE_DELTA_THRESHOLD

    simulation_engine = get_simulation_engine(target.production_config)
    monte_carlo_v2_bypassed = not _should_use_monte_carlo_v2(target.production_config)
    slot_schema_runtime_used = simulation_engine == "slot_schema" and bool(
        getattr(target.production_config, "SLOT_SCHEMA_RUNTIME_ENABLED", False)
    )

    persisted = result.get("persisted") or {}
    persisted_parent = persisted.get("parent") or {}
    persisted_outputs = persisted.get("outputs") or {}

    if target.set_id in harness.persister_payload_keys_by_set:
        harness.persister_payload_keys_by_set[target.set_id].setdefault(
            "parent_return",
            sorted(persisted_parent.keys()),
        )

    pack_price_source = str(input_metadata.get("pack_price_source") or "unreported")
    pack_price_resolution_status = str(input_metadata.get("pack_price_resolution_status") or "unreported")

    row: Dict[str, Any] = {
        "set_id": target.set_id,
        "set_name": target.set_name,
        "canonical_key": target.canonical_key,
        "run_mode": run_mode,
        "selected_engine": simulation_engine,
        "pack_count": int(sim_summary.get("value_count") or 0),
        "estimated_pack_price": estimated_pack_price,
        "pack_price_source": pack_price_source,
        "pack_price_resolution_status": pack_price_resolution_status,
        "average_pack_value": average_pack_value,
        "median_pack_value": median_pack_value,
        "formula_roi": formula_roi,
        "reported_roi": reported_roi,
        "roi_absolute_delta": roi_abs_delta,
        "value_to_cost_ratio": reported_value_to_cost_ratio,
        "value_to_cost_ratio_absolute_delta": ratio_abs_delta,
        "probability_to_beat_pack_cost": probability_from_values,
        "reported_probability_to_beat_pack_cost": reported_probability,
        "probability_to_beat_pack_cost_absolute_delta": probability_abs_delta,
        "p05": _safe_float(sim_summary.get("p05"), 0.0),
        "p95": _safe_float(sim_summary.get("p95"), 0.0),
        "p99": _safe_float(sim_summary.get("p99"), 0.0),
        "metric_semantics_version": pack_comparison.get("metric_semantics_version") or METRIC_SEMANTICS_VERSION,
        "roi_formula": pack_comparison.get("roi_formula") or ROI_FORMULA,
        "selected_simulation_engine": simulation_engine,
        "monte_carlo_v2_bypassed": monte_carlo_v2_bypassed,
        "slot_schema_runtime_used": slot_schema_runtime_used,
        "strict_db_input_source": input_metadata.get("source"),
        "strict_db_fallback_used": bool(input_metadata.get("fallback_used")),
        "strict_db_required_columns_present": bool(input_metadata.get("required_columns_present")),
        "strict_db_usable_price_rows": int(input_metadata.get("usable_price_rows") or 0),
        "strict_db_input_passed": strict_db_input_passed,
        "production_probability_table_status": probability_status,
        "reverse_holo_leakage_detected": None,
        "reverse_holo_leakage_status": "not_available_from_orchestrator_output",
        "intended_persistence_targets": intended_targets,
        "intended_write_counts": set_counts,
        "intended_writes_captured_total": intended_total,
        "actual_writes_performed": int(actual_writes_performed),
        "unexpected_write_targets": unexpected_write_targets,
        "destructive_operations_detected": destructive_operations_detected,
        "persistence_operation_classification": {
            table: PERSISTENCE_OPERATION_CLASSIFICATION.get(table, "unknown")
            for table in intended_targets
        },
        "expected_parent_run_payload_keys": sorted(persisted_parent.keys()),
        "expected_simulation_output_payload_keys": sorted(persisted_outputs.keys()),
        "persisted_identifiers": dict(persisted_identifiers),
        "output_payload_keys": sorted(result.keys()),
        "persistence_payload_validators_passed": True,
        "output_payload_metrics_present": False,
        "output_payload_json_serializable": False,
        "semantic_status": {
            "roi": _compute_semantic_status(
                passed=roi_consistency_passed,
                mismatch_label="reported_roi_not_formula_roi",
                aligned_label="formula_roi_aligned",
            ),
            "value_to_cost_ratio": _compute_semantic_status(
                passed=value_to_cost_ratio_consistency_passed,
                mismatch_label="reported_value_to_cost_ratio_not_ratio",
                aligned_label="value_to_cost_ratio_aligned",
            ),
            "probability_to_beat_pack_cost": _compute_semantic_status(
                passed=probability_consistency_passed,
                mismatch_label="reported_probability_not_value_derived",
                aligned_label="value_derived_probability_aligned",
            ),
        },
    }

    row["output_payload_metrics_present"] = _output_metrics_present(
        {
            "estimated_pack_price": row["estimated_pack_price"],
            "average_pack_value": row["average_pack_value"],
            "median_pack_value": row["median_pack_value"],
            "cost": row["estimated_pack_price"],
            "expected_value": row["average_pack_value"],
            "value_to_cost_ratio": row["value_to_cost_ratio"],
            "reported_roi": row["reported_roi"],
            "expected_roi_from_mean_and_pack_price": row["formula_roi"],
            "roi_formula": row["roi_formula"],
            "metric_semantics_version": row["metric_semantics_version"],
            "probability_to_beat_pack_cost": row["probability_to_beat_pack_cost"],
            "reported_probability_to_beat_pack_cost": row["reported_probability_to_beat_pack_cost"],
            "output_payload_keys": row["output_payload_keys"],
        }
    )
    row["output_payload_json_serializable"] = _is_json_serializable(row)

    expected_persisted_ids_present = bool(persisted_identifiers.get("parent_run_id")) and bool(
        persisted_identifiers.get("simulation_summary_id")
    )

    warning_flags = _build_warning_flags(
        execute_mode=run_mode == "execute",
        actual_writes_performed=int(actual_writes_performed),
        intended_write_total=intended_total,
        target_scope=sorted(TARGET_SET_IDS),
        simulation_engine=simulation_engine,
        monte_carlo_v2_bypassed=monte_carlo_v2_bypassed,
        slot_schema_runtime_used=slot_schema_runtime_used,
        production_has_rare_slot_probability=bool(probability_status.get("production_has_rare_slot_probability")),
        production_probability_equals_draft=bool(probability_status.get("production_equals_draft")),
        sum_probability=_safe_float(probability_status.get("sum_probability"), 0.0),
        residual_rare_non_negative=bool(probability_status.get("residual_rare_non_negative")),
        strict_db_input_source_ok=str(input_metadata.get("source") or "") == "db_evr_input_preparation_service",
        strict_db_fallback_not_used=not bool(input_metadata.get("fallback_used")),
        strict_db_required_columns_present=bool(input_metadata.get("required_columns_present")),
        usable_price_rows_positive=int(input_metadata.get("usable_price_rows") or 0) > 0,
        estimated_pack_price_present=estimated_pack_price > 0,
        pack_price_source_present=bool(pack_price_source) and bool(pack_price_resolution_status),
        reverse_holo_leakage_detected=row.get("reverse_holo_leakage_detected"),
        roi_consistency_passed=roi_consistency_passed,
        value_to_cost_ratio_consistency_passed=value_to_cost_ratio_consistency_passed,
        probability_to_beat_pack_cost_consistency_passed=probability_consistency_passed,
        output_payload_json_serializable=row["output_payload_json_serializable"],
        persistence_payload_validators_passed=bool(row["persistence_payload_validators_passed"]),
        unexpected_write_targets=unexpected_write_targets,
        destructive_operations_detected=destructive_operations_detected,
        sv_mega_routing_status=sv_mega_routing_status,
        other_swsh_guardrail_unchanged=other_swsh_guardrail_unchanged,
        execute_mode_confirmed=execute_mode_confirmed,
        parent_run_id_present=bool(persisted_identifiers.get("parent_run_id")),
        expected_persisted_ids_present=expected_persisted_ids_present,
        execute_real_writes_expected=execute_real_writes_expected,
    )
    row["warning_flags"] = warning_flags

    critical_triggered = [
        flag for flag in warning_flags if flag.get("severity") == "critical" and bool(flag.get("triggered"))
    ]
    row["readiness_status"] = "ready" if not critical_triggered else "blocked"

    return row


def _recompute_set_row_warning_state(
    *,
    row: Dict[str, Any],
    sv_mega_routing_status: Mapping[str, Any],
    other_swsh_guardrail_unchanged: bool,
    execute_mode_confirmed: bool,
) -> None:
    probability_status = row.get("production_probability_table_status") or {}
    persisted_identifiers = row.get("persisted_identifiers") or {}

    expected_persisted_ids_present = bool(persisted_identifiers.get("parent_run_id")) and bool(
        persisted_identifiers.get("simulation_summary_id")
    )
    warning_flags = _build_warning_flags(
        execute_mode=str(row.get("run_mode") or "") == "execute",
        actual_writes_performed=int(row.get("actual_writes_performed") or 0),
        intended_write_total=int(row.get("intended_writes_captured_total") or 0),
        target_scope=sorted(TARGET_SET_IDS),
        simulation_engine=str(row.get("selected_engine") or ""),
        monte_carlo_v2_bypassed=bool(row.get("monte_carlo_v2_bypassed")),
        slot_schema_runtime_used=bool(row.get("slot_schema_runtime_used")),
        production_has_rare_slot_probability=bool(probability_status.get("production_has_rare_slot_probability")),
        production_probability_equals_draft=bool(probability_status.get("production_equals_draft")),
        sum_probability=_safe_float(probability_status.get("sum_probability"), 0.0),
        residual_rare_non_negative=bool(probability_status.get("residual_rare_non_negative")),
        strict_db_input_source_ok=str(row.get("strict_db_input_source") or "") == "db_evr_input_preparation_service",
        strict_db_fallback_not_used=not bool(row.get("strict_db_fallback_used")),
        strict_db_required_columns_present=bool(row.get("strict_db_required_columns_present")),
        usable_price_rows_positive=int(row.get("strict_db_usable_price_rows") or 0) > 0,
        estimated_pack_price_present=_safe_float(row.get("estimated_pack_price"), 0.0) > 0,
        pack_price_source_present=bool(row.get("pack_price_source")) and bool(row.get("pack_price_resolution_status")),
        reverse_holo_leakage_detected=row.get("reverse_holo_leakage_detected"),
        roi_consistency_passed=str((row.get("semantic_status") or {}).get("roi")) == "formula_roi_aligned",
        value_to_cost_ratio_consistency_passed=str((row.get("semantic_status") or {}).get("value_to_cost_ratio"))
        == "value_to_cost_ratio_aligned",
        probability_to_beat_pack_cost_consistency_passed=str(
            (row.get("semantic_status") or {}).get("probability_to_beat_pack_cost")
        )
        == "value_derived_probability_aligned",
        output_payload_json_serializable=bool(row.get("output_payload_json_serializable")),
        persistence_payload_validators_passed=bool(row.get("persistence_payload_validators_passed")),
        unexpected_write_targets=list(row.get("unexpected_write_targets") or []),
        destructive_operations_detected=list(row.get("destructive_operations_detected") or []),
        sv_mega_routing_status=sv_mega_routing_status,
        other_swsh_guardrail_unchanged=other_swsh_guardrail_unchanged,
        execute_mode_confirmed=execute_mode_confirmed,
        parent_run_id_present=bool(persisted_identifiers.get("parent_run_id")),
        expected_persisted_ids_present=expected_persisted_ids_present,
        execute_real_writes_expected=str(row.get("run_mode") or "") == "execute",
    )

    row["warning_flags"] = warning_flags
    critical_triggered = [
        flag for flag in warning_flags if flag.get("severity") == "critical" and bool(flag.get("triggered"))
    ]
    row["readiness_status"] = "ready" if not critical_triggered else "blocked"


def _run_orchestrator_pass(
    *,
    pack_count: int,
    strict_db_input: bool,
    seed_base: int,
    run_mode: str,
    intercept_writes: bool,
    monitor: Optional[DBWriteMonitor],
    execute_mode_confirmed: bool,
) -> Dict[str, Any]:
    other_swsh_before = _capture_other_swsh_runtime_enabled_state()
    sv_mega_before = _capture_sv_mega_routing_state()

    harness = ControlledPersistenceHarness()
    rows: List[Dict[str, Any]] = []

    if int(pack_count) <= 0:
        raise ValueError("pack_count must be > 0")

    write_context = _monitor_real_db_writes_context(monitor) if monitor else nullcontext()

    with write_context:
        with _controlled_no_write_context(
            harness,
            pack_count=int(pack_count),
            strict_db_input=bool(strict_db_input),
            intercept_writes=bool(intercept_writes),
        ):
            orchestrator = evr_runner.EVRRunOrchestrator()

            for index, target in enumerate(TARGETS):
                random.seed(seed_base + index)
                harness.set_current_set(
                    set_id=target.set_id,
                    canonical_key=target.canonical_key,
                    set_name=target.set_name,
                )

                sv_mega_status_during = _compute_sv_mega_routing_status(
                    sv_mega_before,
                    _capture_sv_mega_routing_state(),
                )
                other_swsh_unchanged_during = other_swsh_before == _capture_other_swsh_runtime_enabled_state()

                result = orchestrator.run(
                    target_set_identifier=target.canonical_key,
                    input_source="db",
                    run_metadata={
                        "trigger": "audit_swsh_controlled_persistence_preflight",
                        "project": 8,
                        "run_mode": run_mode,
                        "strict_db_input": bool(strict_db_input),
                        "set_id": target.set_id,
                    },
                )

                persisted_identifiers = _extract_persisted_identifiers(result)
                row = _build_set_row(
                    target=target,
                    result=result,
                    harness=harness,
                    strict_db_input=bool(strict_db_input),
                    run_mode=run_mode,
                    sv_mega_routing_status=sv_mega_status_during,
                    other_swsh_guardrail_unchanged=other_swsh_unchanged_during,
                    actual_writes_performed=0,
                    execute_mode_confirmed=execute_mode_confirmed,
                    execute_real_writes_expected=(run_mode == "execute"),
                    persisted_identifiers=persisted_identifiers,
                )
                rows.append(row)

    other_swsh_after = _capture_other_swsh_runtime_enabled_state()
    sv_mega_after = _capture_sv_mega_routing_state()
    sv_mega_status = _compute_sv_mega_routing_status(sv_mega_before, sv_mega_after)

    if monitor is not None:
        writes_by_table = dict(monitor.write_counts_by_table)
        operations_by_table = dict(monitor.operations_by_table)
        total_writes = int(monitor.actual_writes_performed_total)
        for row in rows:
            persisted_ids = row.get("persisted_identifiers") or {}
            row["actual_writes_performed"] = 1 if (total_writes > 0 and persisted_ids.get("parent_run_id")) else 0
            _recompute_set_row_warning_state(
                row=row,
                sv_mega_routing_status=sv_mega_status,
                other_swsh_guardrail_unchanged=other_swsh_before == other_swsh_after,
                execute_mode_confirmed=execute_mode_confirmed,
            )
    else:
        writes_by_table = {}
        operations_by_table = {}
        total_writes = int(harness.actual_writes_performed_total)

    intended_total = int(
        sum(
            int(count)
            for per_set in harness.intended_write_counts_by_set.values()
            for count in per_set.values()
        )
    )

    payload: Dict[str, Any] = {
        "meta": {
            "generated_at_utc": datetime.now(timezone.utc).isoformat(),
            "project": "8",
            "run_mode": run_mode,
            "strict_db_input": bool(strict_db_input),
            "pack_count": int(pack_count),
            "actual_writes_performed_total": int(total_writes),
            "intended_writes_captured_total": intended_total,
            "execute_mode_exists": True,
            "execute_mode_run": run_mode == "execute",
        },
        "other_swsh_runtime_guardrail": {
            "before": other_swsh_before,
            "after": other_swsh_after,
            "unchanged": other_swsh_before == other_swsh_after,
        },
        "sv_mega_routing_guardrail": sv_mega_status,
        "expected_write_table_allowlist": sorted(EXPECTED_WRITE_TABLE_ALLOWLIST),
        "write_operation_classification": dict(PERSISTENCE_OPERATION_CLASSIFICATION),
        "real_write_counts_by_table": writes_by_table,
        "real_write_operations_by_table": operations_by_table,
        "sets": rows,
    }

    failures = _evaluate_global_failures(payload)
    payload["safety_assertions"] = {
        "passed": len(failures) == 0,
        "failures": failures,
    }

    return {
        "payload": payload,
        "failures": failures,
    }


def run_controlled_persistence_preflight(
    *,
    json_output_path: Path = DEFAULT_JSON_PATH,
    markdown_output_path: Path = DEFAULT_MD_PATH,
    closure_json_output_path: Path = DEFAULT_CLOSURE_JSON_PATH,
    closure_markdown_output_path: Path = DEFAULT_CLOSURE_MD_PATH,
    pack_count: int = 100000,
    strict_db_input: bool = False,
    execute: bool = False,
    confirm_db_writes: Optional[str] = None,
    seed_base: int = 81670,
) -> Dict[str, Any]:
    if int(pack_count) <= 0:
        raise ValueError("pack_count must be > 0")

    if execute and str(confirm_db_writes or "") != EXECUTE_CONFIRMATION_TOKEN:
        raise RuntimeError(
            "Execute mode requires --confirm-db-writes "
            f"{EXECUTE_CONFIRMATION_TOKEN} before any write operation."
        )

    target_ids = {target.set_id for target in TARGETS}
    if target_ids != TARGET_SET_IDS:
        raise AssertionError(f"Unexpected target scope. expected={sorted(TARGET_SET_IDS)} actual={sorted(target_ids)}")

    started_at = time.perf_counter()
    run_mode = "execute" if execute else "dry_run"

    phase1 = _run_orchestrator_pass(
        pack_count=int(pack_count),
        strict_db_input=bool(strict_db_input),
        seed_base=int(seed_base),
        run_mode="dry_run",
        intercept_writes=True,
        monitor=None,
        execute_mode_confirmed=bool(execute and str(confirm_db_writes or "") == EXECUTE_CONFIRMATION_TOKEN),
    )

    phase1_payload = phase1["payload"]
    phase1_failures = list(phase1["failures"])

    if execute and phase1_failures:
        payload = dict(phase1_payload)
        payload["meta"] = dict(payload.get("meta") or {})
        payload["meta"].update(
            {
                "run_mode": "execute",
                "execute_mode_run": False,
                "execute_mode_exists": True,
                "execute_mode_requested": True,
                "execute_confirmation_token_accepted": True,
                "real_db_writes_performed": False,
                "elapsed_seconds": time.perf_counter() - started_at,
            }
        )
        payload["phase_1_preflight_passed"] = False
        payload["phase_2_execute_attempted"] = False
        payload["phase_1_preflight_failures"] = list(phase1_failures)
    elif execute:
        monitor = DBWriteMonitor(allowlist=sorted(EXPECTED_WRITE_TABLE_ALLOWLIST))
        phase2 = _run_orchestrator_pass(
            pack_count=int(pack_count),
            strict_db_input=bool(strict_db_input),
            seed_base=int(seed_base),
            run_mode="execute",
            intercept_writes=False,
            monitor=monitor,
            execute_mode_confirmed=True,
        )
        payload = phase2["payload"]
        payload["meta"]["elapsed_seconds"] = time.perf_counter() - started_at
        payload["meta"]["execute_mode_requested"] = True
        payload["meta"]["execute_confirmation_token_accepted"] = True
        payload["meta"]["real_db_writes_performed"] = int(payload["meta"].get("actual_writes_performed_total") or 0) > 0
        payload["phase_1_preflight_passed"] = True
        payload["phase_2_execute_attempted"] = True
        payload["phase_1_summary"] = {
            "safety_passed": bool(phase1_payload.get("safety_assertions", {}).get("passed")),
            "actual_writes_performed_total": int(phase1_payload.get("meta", {}).get("actual_writes_performed_total") or 0),
            "intended_writes_captured_total": int(phase1_payload.get("meta", {}).get("intended_writes_captured_total") or 0),
        }
    else:
        payload = phase1_payload
        payload["meta"]["elapsed_seconds"] = time.perf_counter() - started_at
        payload["meta"]["execute_mode_requested"] = False
        payload["meta"]["execute_confirmation_token_accepted"] = False
        payload["meta"]["real_db_writes_performed"] = False
        payload["phase_1_preflight_passed"] = bool(payload.get("safety_assertions", {}).get("passed"))
        payload["phase_2_execute_attempted"] = False

    rows = list(payload.get("sets") or [])
    failures = _evaluate_global_failures(payload)
    failures.extend(str(item) for item in (payload.get("phase_1_preflight_failures") or []))
    failures = sorted(set(failures))
    payload["safety_assertions"] = {
        "passed": len(failures) == 0,
        "failures": failures,
    }

    full_intended_write_tables = sorted(
        {
            table
            for row in rows
            for table in (row.get("intended_persistence_targets") or [])
        }
    )
    all_unexpected_targets = sorted(
        {
            table
            for row in rows
            for table in (row.get("unexpected_write_targets") or [])
        }
    )
    destructive_detected = sorted(
        {
            marker
            for row in rows
            for marker in (row.get("destructive_operations_detected") or [])
        }
    )

    strict_db_input_passed = all(bool(row.get("strict_db_input_passed")) for row in rows)
    semantics_passed = all(
        bool(row.get("semantic_status", {}).get("roi") == "formula_roi_aligned")
        and bool(row.get("semantic_status", {}).get("value_to_cost_ratio") == "value_to_cost_ratio_aligned")
        and bool(
            row.get("semantic_status", {}).get("probability_to_beat_pack_cost") == "value_derived_probability_aligned"
        )
        for row in rows
    )
    scope_is_swsh6_swsh7_only = _parse_manifest_set_ids(rows) == sorted(TARGET_SET_IDS)
    expected_non_destructive_write_scope = len(all_unexpected_targets) == 0 and len(destructive_detected) == 0
    sv_mega_status = payload.get("sv_mega_routing_guardrail") or {}
    sv_mega_unchanged = not bool(sv_mega_status.get("changed")) and bool(sv_mega_status.get("all_expected_v2"))
    other_swsh_unchanged = bool(payload["other_swsh_runtime_guardrail"]["unchanged"])
    no_critical_warnings = all(
        not [
            flag
            for flag in (row.get("warning_flags") or [])
            if flag.get("severity") == "critical" and bool(flag.get("triggered"))
        ]
        for row in rows
    )

    decision = _determine_final_decision(
        execute_mode_exists=True,
        execute_mode_run=bool(execute and payload.get("phase_1_preflight_passed") and payload.get("phase_2_execute_attempted")),
        dry_run_preflight_passed=bool(payload.get("phase_1_preflight_passed")),
        has_runtime_errors=False,
        has_blockers=not bool(payload["safety_assertions"]["passed"]),
        actual_writes_performed_total=int(payload["meta"]["actual_writes_performed_total"]),
        strict_db_input_passed=strict_db_input_passed,
        scope_is_swsh6_swsh7_only=scope_is_swsh6_swsh7_only,
        expected_non_destructive_write_scope=expected_non_destructive_write_scope,
        semantics_passed=semantics_passed,
        sv_mega_unchanged=sv_mega_unchanged,
        other_swsh_unchanged=other_swsh_unchanged,
        no_critical_warnings=no_critical_warnings,
    )

    closure = {
        "generated_at_utc": datetime.now(timezone.utc).isoformat(),
        "project": 8,
        "final_decision": decision,
        "run_mode": run_mode,
        "confirmation_token_expected": EXECUTE_CONFIRMATION_TOKEN,
        "confirmation_token_accepted": bool(execute and str(confirm_db_writes or "") == EXECUTE_CONFIRMATION_TOKEN),
        "real_db_writes_performed": bool(payload.get("meta", {}).get("real_db_writes_performed")),
        "actual_writes_performed_total": int(payload["meta"]["actual_writes_performed_total"]),
        "intended_writes_captured_total": int(payload["meta"]["intended_writes_captured_total"]),
        "execute_mode_exists": True,
        "execute_mode_run": bool(execute and payload.get("phase_2_execute_attempted")),
        "execute_mode_blocked": False,
        "persistence_approved_for_future_explicit_execute": decision
        == "closed_controlled_persistence_preflight_ready_for_explicit_execute",
        "full_intended_write_tables": full_intended_write_tables,
        "full_write_tables": sorted(
            {
                table
                for table in full_intended_write_tables
                for _ in [table]
            }
            | set((payload.get("real_write_counts_by_table") or {}).keys())
        ),
        "real_write_counts_by_table": dict(payload.get("real_write_counts_by_table") or {}),
        "real_write_operations_by_table": dict(payload.get("real_write_operations_by_table") or {}),
        "destructive_operations_found": len(destructive_detected) > 0,
        "destructive_operation_markers": destructive_detected,
        "metrics_semantics_passed": semantics_passed,
        "strict_db_input_passed": strict_db_input_passed,
        "swsh6_swsh7_scoped_only": scope_is_swsh6_swsh7_only,
        "sv_mega_unchanged": sv_mega_unchanged,
        "other_swsh_unchanged": other_swsh_unchanged,
        "production_probability_tables_unchanged": all(
            bool(row.get("production_probability_table_status", {}).get("production_equals_draft")) for row in rows
        ),
        "phase_1_preflight_passed": bool(payload.get("phase_1_preflight_passed")),
        "phase_2_execute_attempted": bool(payload.get("phase_2_execute_attempted")),
        "persisted_identifiers_by_set": {
            str(row.get("set_id")): dict(row.get("persisted_identifiers") or {})
            for row in rows
        },
        "final_approval_status": "ready_for_explicit_execute"
        if decision == "closed_controlled_persistence_preflight_ready_for_explicit_execute"
        else "executed_and_verified"
        if decision == "closed_controlled_persistence_executed_and_verified"
        else "blocked",
        "blockers": list(payload["safety_assertions"]["failures"]),
    }

    json_output_path.parent.mkdir(parents=True, exist_ok=True)
    markdown_output_path.parent.mkdir(parents=True, exist_ok=True)
    closure_json_output_path.parent.mkdir(parents=True, exist_ok=True)
    closure_markdown_output_path.parent.mkdir(parents=True, exist_ok=True)

    json_output_path.write_text(json.dumps(payload, indent=2, sort_keys=True), encoding="utf-8")
    markdown_output_path.write_text(_render_preflight_markdown(payload), encoding="utf-8")
    closure_json_output_path.write_text(json.dumps(closure, indent=2, sort_keys=True), encoding="utf-8")
    closure_markdown_output_path.write_text(_render_closure_markdown(closure), encoding="utf-8")

    if failures:
        raise AssertionError("; ".join(failures))

    return {
        "preflight": payload,
        "closure": closure,
    }


def _build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(description="Project 8 controlled persistence preflight for swsh6/swsh7")
    parser.add_argument("--json-output", default=str(DEFAULT_JSON_PATH), help="Preflight JSON output path")
    parser.add_argument("--markdown-output", default=str(DEFAULT_MD_PATH), help="Preflight markdown output path")
    parser.add_argument("--closure-json-output", default=str(DEFAULT_CLOSURE_JSON_PATH), help="Closure JSON output path")
    parser.add_argument(
        "--closure-markdown-output",
        default=str(DEFAULT_CLOSURE_MD_PATH),
        help="Closure markdown output path",
    )
    parser.add_argument("--pack-count", type=int, default=100000, help="Simulation pack count override")
    parser.add_argument("--seed-base", type=int, default=81670, help="Random seed base")
    parser.add_argument("--strict-db-input", action="store_true", help="Require strict DB input checks")
    parser.add_argument(
        "--execute",
        action="store_true",
        help="Explicit execute mode flag (requires confirmation token)",
    )
    parser.add_argument(
        "--confirm-db-writes",
        default="",
        help=f"Required with --execute. Must exactly equal: {EXECUTE_CONFIRMATION_TOKEN}",
    )
    parser.add_argument("--stdout", action="store_true", help="Print compact summary JSON")
    return parser


def main() -> int:
    args = _build_parser().parse_args()
    result = run_controlled_persistence_preflight(
        json_output_path=Path(args.json_output),
        markdown_output_path=Path(args.markdown_output),
        closure_json_output_path=Path(args.closure_json_output),
        closure_markdown_output_path=Path(args.closure_markdown_output),
        pack_count=int(args.pack_count),
        strict_db_input=bool(args.strict_db_input),
        execute=bool(args.execute),
        confirm_db_writes=str(args.confirm_db_writes or ""),
        seed_base=int(args.seed_base),
    )

    preflight = result["preflight"]
    closure = result["closure"]

    summary = {
        "final_decision": closure.get("final_decision"),
        "actual_writes_performed_total": preflight.get("meta", {}).get("actual_writes_performed_total"),
        "intended_writes_captured_total": preflight.get("meta", {}).get("intended_writes_captured_total"),
        "safety_passed": preflight.get("safety_assertions", {}).get("passed"),
        "set_ids": [row.get("set_id") for row in preflight.get("sets", [])],
    }

    print(f"[preflight] final_decision={summary['final_decision']}")
    print(f"[preflight] actual_writes_performed_total={summary['actual_writes_performed_total']}")
    print(f"[preflight] intended_writes_captured_total={summary['intended_writes_captured_total']}")
    print(f"[preflight] safety_passed={summary['safety_passed']}")

    if args.stdout:
        print(json.dumps(summary, indent=2, sort_keys=True))

    return 0


if __name__ == "__main__":
    raise SystemExit(main())
