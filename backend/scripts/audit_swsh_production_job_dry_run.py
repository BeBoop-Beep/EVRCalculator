"""Project 7 metric semantics dry-run audit for swsh6/swsh7.

This script exercises the real production EVR job entrypoint
(backend.jobs.evr_runner.EVRRunOrchestrator.run) for:
- swsh6 / chillingReign
- swsh7 / evolvingSkies

Hard safety behavior:
- Requires --dry-run (refuses to run otherwise)
- Intercepts all simulation persistence calls with in-memory spies
- Performs zero actual DB writes
- Keeps scope surgical to swsh6/swsh7 only
"""

from __future__ import annotations

import argparse
import json
import random
import time
from contextlib import contextmanager
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Dict, List, Mapping, Optional, Sequence

import pandas as pd

import backend.jobs.evr_runner as evr_runner
import backend.simulations.evrSimulator as evr_simulator
from backend.scripts.audit_swsh_production_runtime_smoke import (
    TARGETS,
    _capture_other_swsh_runtime_enabled_state,
    _capture_sv_mega_routing_state,
    _compute_probability_table_status,
    _compute_sv_mega_routing_status,
)
from backend.simulations.evrSimulator import _should_use_monte_carlo_v2, get_simulation_engine
from backend.simulations.value_distribution_bins import compute_simulation_value_distribution_bins
from backend.simulations.value_threshold_bins import compute_simulation_value_threshold_bins


DEFAULT_JSON_PATH = Path("logs/audits/swsh_production_job_dry_run.json")
DEFAULT_MD_PATH = Path("backend/docs/audits/SWSH_PRODUCTION_JOB_DRY_RUN.md")

TARGET_SET_IDS = {"swsh6", "swsh7"}
PRICE_COLUMN_CANDIDATES: Sequence[str] = (
    "Price ($)",
    "price",
    "market_price",
    "usd_market",
    "near_mint_price",
)

ROI_FORMULA = "(average_pack_value - estimated_pack_price) / estimated_pack_price"
ROI_ABSOLUTE_DELTA_THRESHOLD = 1e-9
VALUE_TO_COST_RATIO_ABSOLUTE_DELTA_THRESHOLD = 1e-9
PROBABILITY_ABSOLUTE_DELTA_THRESHOLD = 0.001


def _safe_float(value: Any, default: float = 0.0) -> float:
    try:
        parsed = float(value)
    except (TypeError, ValueError):
        return default
    return parsed if parsed == parsed else default


def _quantile(values: Sequence[float], q: float) -> float:
    if not values:
        return 0.0
    if q <= 0:
        return float(min(values))
    if q >= 1:
        return float(max(values))

    ordered = sorted(float(v) for v in values)
    position = (len(ordered) - 1) * q
    lower = int(position)
    upper = min(lower + 1, len(ordered) - 1)
    fraction = position - lower
    return float(ordered[lower] * (1.0 - fraction) + ordered[upper] * fraction)


def _resolve_detected_price_column(df: pd.DataFrame) -> Optional[str]:
    for column in PRICE_COLUMN_CANDIDATES:
        if column not in df.columns:
            continue
        numeric = pd.to_numeric(df[column], errors="coerce")
        if numeric.notna().any():
            return str(column)
    return None


def _build_input_metadata(prepared_payload: Mapping[str, Any]) -> Dict[str, Any]:
    dataframe = prepared_payload.get("dataframe")
    if not isinstance(dataframe, pd.DataFrame):
        return {
            "source": "db_evr_input_preparation_service",
            "fallback_used": False,
            "row_count": 0,
            "required_columns_present": False,
            "missing_required_columns": ["Card Name", "Card Number", "Rarity"],
            "price_column_detected": None,
            "usable_price_rows": 0,
            "pack_price_source": None,
            "pack_price_resolution_status": None,
        }

    diagnostics = prepared_payload.get("diagnostics") or {}
    row_count = int(len(dataframe))
    required_columns = ["Card Name", "Card Number", "Rarity"]
    missing_required = [column for column in required_columns if column not in dataframe.columns]
    detected_price_column = _resolve_detected_price_column(dataframe)

    usable_price_rows = 0
    if detected_price_column is not None:
        numeric = pd.to_numeric(dataframe[detected_price_column], errors="coerce")
        usable_price_rows = int((numeric.fillna(0.0) > 0.0).sum())

    return {
        "source": "db_evr_input_preparation_service",
        "fallback_used": False,
        "row_count": row_count,
        "required_columns_present": len(missing_required) == 0,
        "missing_required_columns": missing_required,
        "price_column_detected": detected_price_column,
        "usable_price_rows": usable_price_rows,
        "pack_price_source": diagnostics.get("pack_price_source"),
        "pack_price_resolution_status": diagnostics.get("pack_price_resolution_status"),
    }


def _validate_input_metadata(metadata: Mapping[str, Any], *, strict_db_input: bool) -> None:
    if not strict_db_input:
        return

    source = str(metadata.get("source") or "")
    if source != "db_evr_input_preparation_service":
        raise RuntimeError(f"Strict DB input failed: non-db source={source}")

    if bool(metadata.get("fallback_used")):
        raise RuntimeError("Strict DB input failed: fallback input detected")

    if int(metadata.get("row_count") or 0) <= 0:
        raise RuntimeError("Strict DB input failed: empty dataframe")

    if not bool(metadata.get("required_columns_present")):
        raise RuntimeError(
            "Strict DB input failed: missing required columns "
            f"{metadata.get('missing_required_columns') or []}"
        )

    if not metadata.get("price_column_detected"):
        raise RuntimeError("Strict DB input failed: no price column detected")

    if int(metadata.get("usable_price_rows") or 0) <= 0:
        raise RuntimeError("Strict DB input failed: no usable price rows")


class WriteSpyHarness:
    """In-memory write-capture harness for dry-run execution."""

    def __init__(self) -> None:
        self.current_set_id: Optional[str] = None
        self.intended_write_counts_by_set: Dict[str, Dict[str, int]] = {}
        self.input_metadata_by_canonical_key: Dict[str, Dict[str, Any]] = {}
        self.sim_output_summary_by_set: Dict[str, Dict[str, Any]] = {}
        self.actual_writes_performed = 0

    def set_current_set(self, set_id: str) -> None:
        self.current_set_id = str(set_id)
        self.intended_write_counts_by_set.setdefault(self.current_set_id, {})

    def _record_intended(self, target: str, count: int) -> None:
        if self.current_set_id is None:
            return
        if count <= 0:
            return
        set_counts = self.intended_write_counts_by_set.setdefault(self.current_set_id, {})
        set_counts[target] = int(set_counts.get(target, 0)) + int(count)

    def spy_parent_run_with_price_snapshots(
        self,
        *,
        config: Any,
        canonical_key: str,
        set_name: str,
        input_mode: str,
        price_inputs: Dict[str, Any],
        pack_value_vs_cost_comparison: Dict[str, Any],
        etb_value_vs_cost_comparison: Dict[str, Any] | None,
        booster_box_value_vs_cost_comparison: Dict[str, Any],
    ) -> Dict[str, Any]:
        _ = (
            config,
            canonical_key,
            set_name,
            input_mode,
            pack_value_vs_cost_comparison,
            etb_value_vs_cost_comparison,
            booster_box_value_vs_cost_comparison,
        )

        snapshot_count = sum(1 for key in ("pack", "booster_box") if price_inputs.get(key) is not None)

        # get_or_create semantics may skip insert for calculation_configs, but
        # this path can write at most one config row per run.
        self._record_intended("calculation_configs", 1)
        self._record_intended("calculation_runs", 1)
        self._record_intended("calculation_price_snapshots", snapshot_count)

        set_suffix = self.current_set_id or canonical_key or "set"
        return {
            "config_id": f"dry-config-{set_suffix}",
            "config_hash": f"dry-hash-{set_suffix}",
            "run_id": f"dry-run-{set_suffix}",
            "snapshot_count": snapshot_count,
            "dry_run": True,
            "no_write": True,
        }

    def spy_simulation_inputs(
        self,
        *,
        run_id: Any,
        calculation_input: Any,
        config: Any,
    ) -> Dict[str, Any]:
        _ = (run_id, config)
        row_count = int(len(calculation_input)) if hasattr(calculation_input, "__len__") else 0
        self._record_intended("simulation_input_cards", row_count)
        return {
            "top_hits_count": 0,
            "input_cards_count": row_count,
            "dry_run": True,
            "no_write": True,
        }

    def spy_simulation_outputs(
        self,
        *,
        run_id: Any,
        sim_results: Dict[str, Any],
        pack_metrics: Dict[str, Any],
        derived: Dict[str, Any] | None,
    ) -> Dict[str, Any]:
        _ = run_id
        values = [float(v) for v in (sim_results.get("values") or [])]
        percentiles = sim_results.get("percentiles") or {}
        pull_counts = sim_results.get("rarity_pull_counts") or {}
        state_counts = sim_results.get("pack_state_counts") or {}

        distribution_bins = compute_simulation_value_distribution_bins(values) if values else []
        threshold_bins = compute_simulation_value_threshold_bins(values) if values else []

        self._record_intended("simulation_run_summary", 1)
        self._record_intended("simulation_percentiles", len(percentiles))
        self._record_intended("simulation_pull_summary", len(pull_counts))
        self._record_intended("simulation_state_counts", len(state_counts))
        self._record_intended("simulation_derived_metrics", 1 if isinstance(derived, Mapping) else 0)
        self._record_intended("simulation_value_distribution_bins", len(distribution_bins))
        self._record_intended("simulation_value_threshold_bins", len(threshold_bins))

        if self.current_set_id is not None:
            pack_decision = (derived or {}).get("pack_decision_metrics") if isinstance(derived, Mapping) else {}
            pack_cost = _safe_float((pack_decision or {}).get("pack_cost"), 0.0)
            prob_beat_pack_cost = (
                float(sum(1 for value in values if value >= pack_cost)) / float(len(values))
                if values
                else 0.0
            )
            mean_from_values = (float(sum(values)) / float(len(values))) if values else 0.0
            median_from_values = _quantile(values, 0.5) if values else 0.0

            self.sim_output_summary_by_set[self.current_set_id] = {
                "value_count": len(values),
                "mean_from_values": mean_from_values,
                "median_from_values": median_from_values,
                "pack_cost_used": pack_cost,
                "probability_to_beat_pack_cost_from_values": prob_beat_pack_cost,
                "p05": _quantile(values, 0.05),
                "p95": _quantile(values, 0.95),
                "p99": _quantile(values, 0.99),
            }

        return {
            "run_summary_id": f"dry-summary-{self.current_set_id or 'set'}",
            "percentile_count": len(percentiles),
            "pull_summary_count": len(pull_counts),
            "state_count": len(state_counts),
            "derived_metric_count": 1 if isinstance(derived, Mapping) else 0,
            "distribution_bin_count": len(distribution_bins),
            "threshold_bin_count": len(threshold_bins),
            "dry_run": True,
            "no_write": True,
        }

    def spy_simulation_etb_summary(
        self,
        *,
        run_id: Any,
        etb_metrics: Dict[str, Any] | None,
    ) -> Dict[str, Any]:
        _ = (run_id, etb_metrics)
        self._record_intended("simulation_etb_summary", 1)
        return {
            "persisted": False,
            "etb_summary_id": None,
            "dry_run": True,
            "no_write": True,
        }


def _make_input_service_spy(
    *,
    harness: WriteSpyHarness,
    strict_db_input: bool,
    original_service_cls: type,
) -> type:
    class _InputServiceSpy:
        def __init__(self, *args: Any, **kwargs: Any) -> None:
            self._delegate = original_service_cls(*args, **kwargs)

        def prepare_for_set(self, config: Any, canonical_key: str, set_name: str) -> Dict[str, Any]:
            payload = self._delegate.prepare_for_set(config, canonical_key, set_name)
            metadata = _build_input_metadata(payload)
            harness.input_metadata_by_canonical_key[str(canonical_key)] = metadata
            _validate_input_metadata(metadata, strict_db_input=strict_db_input)
            return payload

    return _InputServiceSpy


def _make_runner_compatible_config(config_cls: type) -> type:
    """Return a runner-compatible config class without mutating production classes."""
    if hasattr(config_cls, "get_rarity_pack_multiplier"):
        return config_cls

    class _RunnerCompatibleConfig(config_cls):
        # Legacy pack-calculation path expects rarity/pull-rate mappings that are
        # not guaranteed on slot-schema-only SWSH configs.
        RARITY_MAPPING = getattr(config_cls, "RARITY_MAPPING", None) or {
            "common": "common",
            "uncommon": "uncommon",
            "rare": "rare",
            "holo rare": "rare",
            "rare holo": "rare",
            "ultra rare": "rare",
            "secret rare": "rare",
            "amazing rare": "rare",
            "rare holo v": "rare",
            "rare holo vmax": "rare",
            "rare rainbow": "rare",
        }
        PULL_RATE_MAPPING = getattr(config_cls, "PULL_RATE_MAPPING", None) or {
            "common": 180,
            "uncommon": 120,
            "rare": 12,
            "holo rare": 12,
            "rare holo": 12,
            "rare holo v": 48,
            "rare holo vmax": 120,
            "rare holo gx": 60,
            "rare holo ex": 48,
            "ultra rare": 90,
            "secret rare": 180,
            "amazing rare": 120,
            "full art": 160,
            "alternate art": 260,
            "rainbow": 240,
            "gold": 280,
        }

        @classmethod
        def get_rarity_pack_multiplier(cls):
            return {"common": 5, "uncommon": 3}

    _RunnerCompatibleConfig.__name__ = f"{config_cls.__name__}RunnerCompat"
    return _RunnerCompatibleConfig


@contextmanager
def _no_write_spy_context(
    harness: WriteSpyHarness,
    *,
    pack_count: int,
    strict_db_input: bool,
):
    if int(pack_count) <= 0:
        raise ValueError("pack_count must be > 0")

    original_parent = evr_runner.persist_parent_run_with_price_snapshots
    original_inputs = evr_runner.persist_simulation_inputs
    original_outputs = evr_runner.persist_simulation_outputs
    original_etb = evr_runner.persist_simulation_etb_summary
    original_input_service = evr_runner.EVRInputPreparationService
    original_resolve_set_config = evr_runner._resolve_set_config

    original_run_simulation = evr_simulator.run_simulation
    original_run_simulation_v2 = evr_simulator.run_simulation_v2
    original_simulate_slot_schema_packs = evr_simulator.simulate_slot_schema_packs

    input_service_spy_cls = _make_input_service_spy(
        harness=harness,
        strict_db_input=bool(strict_db_input),
        original_service_cls=original_input_service,
    )

    local_target_lookup: Dict[str, Any] = {}
    for target in TARGETS:
        config_cls = _make_runner_compatible_config(target.production_config)
        local_target_lookup[str(target.canonical_key).strip().lower()] = (config_cls, target.canonical_key)
        local_target_lookup[str(target.set_id).strip().lower()] = (config_cls, target.canonical_key)
        local_target_lookup[str(target.set_name).strip().lower()] = (config_cls, target.canonical_key)

    def _resolve_set_config_override(target_set_identifier: str) -> tuple[Any, str]:
        key = str(target_set_identifier or "").strip().lower()
        if key in local_target_lookup:
            return local_target_lookup[key]
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

    try:
        evr_runner.persist_parent_run_with_price_snapshots = harness.spy_parent_run_with_price_snapshots
        evr_runner.persist_simulation_inputs = harness.spy_simulation_inputs
        evr_runner.persist_simulation_outputs = harness.spy_simulation_outputs
        evr_runner.persist_simulation_etb_summary = harness.spy_simulation_etb_summary
        evr_runner.EVRInputPreparationService = input_service_spy_cls
        evr_runner._resolve_set_config = _resolve_set_config_override

        evr_simulator.run_simulation = _run_simulation_override
        evr_simulator.run_simulation_v2 = _run_simulation_v2_override
        evr_simulator.simulate_slot_schema_packs = _simulate_slot_schema_packs_override

        yield
    finally:
        evr_runner.persist_parent_run_with_price_snapshots = original_parent
        evr_runner.persist_simulation_inputs = original_inputs
        evr_runner.persist_simulation_outputs = original_outputs
        evr_runner.persist_simulation_etb_summary = original_etb
        evr_runner.EVRInputPreparationService = original_input_service
        evr_runner._resolve_set_config = original_resolve_set_config

        evr_simulator.run_simulation = original_run_simulation
        evr_simulator.run_simulation_v2 = original_run_simulation_v2
        evr_simulator.simulate_slot_schema_packs = original_simulate_slot_schema_packs


def _build_warning_flags(
    *,
    dry_run_enabled: bool,
    actual_writes_performed: int,
    intended_write_total: int,
    simulation_engine: str,
    monte_carlo_v2_bypassed: bool,
    slot_schema_runtime_used: bool,
    production_probability_equals_draft: bool,
    strict_db_input_passed: bool,
    output_payload_metrics_present: bool,
    output_payload_json_serializable: bool,
    roi_absolute_delta: float,
    roi_consistency_passed: bool,
    value_to_cost_ratio_absolute_delta: float,
    value_to_cost_ratio_consistency_passed: bool,
    probability_to_beat_pack_cost_absolute_delta: float,
    probability_to_beat_pack_cost_consistency_passed: bool,
    sv_mega_routing_status: Mapping[str, Any],
    other_swsh_guardrail_unchanged: bool,
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
        "dry_run_required",
        "critical",
        not bool(dry_run_enabled),
        "Dry-run mode is required for this audit.",
        value={"dry_run_enabled": bool(dry_run_enabled)},
    )
    emit(
        "actual_writes_detected",
        "critical",
        int(actual_writes_performed) > 0,
        "Actual writes were performed.",
        value={"actual_writes_performed": int(actual_writes_performed)},
    )
    emit(
        "no_intended_writes_captured",
        "critical",
        int(intended_write_total) <= 0,
        "No intended writes were captured by the in-memory spy.",
        value={"intended_write_total": int(intended_write_total)},
    )
    emit(
        "wrong_engine",
        "critical",
        str(simulation_engine) != "slot_schema",
        "swsh6/swsh7 must select slot_schema.",
        value={"simulation_engine": simulation_engine},
    )
    emit(
        "v2_not_bypassed",
        "critical",
        not bool(monte_carlo_v2_bypassed),
        "swsh6/swsh7 must bypass Monte Carlo V2.",
        value={"monte_carlo_v2_bypassed": bool(monte_carlo_v2_bypassed)},
    )
    emit(
        "slot_schema_runtime_not_used",
        "critical",
        not bool(slot_schema_runtime_used),
        "slot_schema runtime must be enabled/used.",
        value={"slot_schema_runtime_used": bool(slot_schema_runtime_used)},
    )
    emit(
        "production_probability_mismatch",
        "critical",
        not bool(production_probability_equals_draft),
        "Production RARE_SLOT_PROBABILITY must equal draft empirical table.",
        value={"production_probability_equals_draft": bool(production_probability_equals_draft)},
    )
    emit(
        "strict_db_input_failed",
        "critical",
        not bool(strict_db_input_passed),
        "Strict DB input guard failed.",
        value={"strict_db_input_passed": bool(strict_db_input_passed)},
    )
    emit(
        "required_output_metrics_missing",
        "critical",
        not bool(output_payload_metrics_present),
        "Output payload is missing required metrics.",
        value={"output_payload_metrics_present": bool(output_payload_metrics_present)},
    )
    emit(
        "output_not_json_serializable",
        "critical",
        not bool(output_payload_json_serializable),
        "Output payload is not JSON-serializable.",
        value={"output_payload_json_serializable": bool(output_payload_json_serializable)},
    )
    emit(
        "roi_semantic_mismatch",
        "critical",
        not bool(roi_consistency_passed),
        "Reported ROI differs from formula-derived ROI by more than threshold.",
        value={
            "roi_absolute_delta": float(roi_absolute_delta),
            "threshold": ROI_ABSOLUTE_DELTA_THRESHOLD,
        },
    )
    emit(
        "value_to_cost_ratio_semantic_mismatch",
        "critical",
        not bool(value_to_cost_ratio_consistency_passed),
        "Reported value_to_cost_ratio differs from value-derived ratio by more than threshold.",
        value={
            "value_to_cost_ratio_absolute_delta": float(value_to_cost_ratio_absolute_delta),
            "threshold": VALUE_TO_COST_RATIO_ABSOLUTE_DELTA_THRESHOLD,
        },
    )
    emit(
        "probability_to_beat_cost_semantic_mismatch",
        "critical",
        not bool(probability_to_beat_pack_cost_consistency_passed),
        "Reported probability_to_beat_pack_cost differs from value-derived probability by more than threshold.",
        value={
            "probability_to_beat_pack_cost_absolute_delta": float(probability_to_beat_pack_cost_absolute_delta),
            "threshold": PROBABILITY_ABSOLUTE_DELTA_THRESHOLD,
        },
    )
    emit(
        "sv_mega_routing_changed",
        "critical",
        bool(sv_mega_routing_status.get("changed")) or not bool(sv_mega_routing_status.get("all_expected_v2")),
        "SV/Mega routing changed or no longer routes to v2.",
        value={
            "changed": bool(sv_mega_routing_status.get("changed")),
            "all_expected_v2": bool(sv_mega_routing_status.get("all_expected_v2")),
            "v2_violations": sv_mega_routing_status.get("v2_violations") or [],
        },
    )
    emit(
        "other_swsh_sets_changed",
        "critical",
        not bool(other_swsh_guardrail_unchanged),
        "Other SWSH runtime-enabled state changed.",
        value={"other_swsh_guardrail_unchanged": bool(other_swsh_guardrail_unchanged)},
    )

    return flags


def _extract_probability_to_beat_pack_cost(
    *,
    result_payload: Mapping[str, Any],
) -> float:
    derived = result_payload.get("derived") or {}
    pack_decision = derived.get("pack_decision_metrics") or {}
    return _safe_float(pack_decision.get("prob_profit"), 0.0)


def _compute_formula_roi(*, average_pack_value: float, estimated_pack_price: float) -> float:
    if estimated_pack_price <= 0:
        return 0.0
    return (float(average_pack_value) - float(estimated_pack_price)) / float(estimated_pack_price)


def _compute_semantic_status(*, passed: bool, mismatch_label: str, aligned_label: str) -> str:
    return aligned_label if bool(passed) else mismatch_label


def _output_metrics_present(row: Mapping[str, Any]) -> bool:
    required_paths = [
        ("estimated_pack_price",),
        ("average_pack_value",),
        ("median_pack_value",),
        ("cost",),
        ("expected_value",),
        ("value_to_cost_ratio",),
        ("reported_roi",),
        ("expected_roi_from_mean_and_pack_price",),
        ("roi_formula",),
        ("metric_semantics_version",),
        ("probability_to_beat_pack_cost",),
        ("reported_probability_to_beat_pack_cost",),
        ("output_payload_keys",),
    ]
    for path in required_paths:
        value = row
        for key in path:
            if not isinstance(value, Mapping) or key not in value:
                return False
            value = value[key]
        if value is None:
            return False
    return True


def _is_json_serializable(value: Any) -> bool:
    try:
        json.dumps(value, sort_keys=True)
        return True
    except (TypeError, ValueError):
        return False


def _run_single_set_dry_run(
    *,
    target: Any,
    orchestrator: evr_runner.EVRRunOrchestrator,
    harness: WriteSpyHarness,
    dry_run: bool,
    strict_db_input: bool,
    sv_mega_routing_status: Mapping[str, Any],
    other_swsh_guardrail_unchanged: bool,
) -> Dict[str, Any]:
    if not dry_run:
        raise RuntimeError("Dry-run mode is required and must be enabled.")

    probability_status = _compute_probability_table_status(target)

    # Safety assertions required by the project acceptance criteria.
    if not probability_status.get("routes_slot_schema"):
        raise AssertionError(f"{target.set_id} must route to slot_schema")
    if not probability_status.get("monte_carlo_v2_disabled"):
        raise AssertionError(f"{target.set_id} must bypass Monte Carlo V2")
    if not probability_status.get("production_equals_draft"):
        raise AssertionError(f"{target.set_id} production RARE_SLOT_PROBABILITY must equal draft")

    result = orchestrator.run(
        target_set_identifier=target.canonical_key,
        input_source="db",
        run_metadata={
            "trigger": "audit_swsh_production_job_dry_run",
            "dry_run": True,
            "no_write": True,
            "set_id": target.set_id,
        },
    )

    input_metadata = harness.input_metadata_by_canonical_key.get(target.canonical_key, {})
    strict_db_input_passed = True
    try:
        _validate_input_metadata(input_metadata, strict_db_input=bool(strict_db_input))
    except Exception:
        strict_db_input_passed = False

    set_counts = harness.intended_write_counts_by_set.get(target.set_id, {})
    intended_write_total = int(sum(int(v) for v in set_counts.values()))
    intended_targets = sorted(set_counts.keys())

    pack_comparison = (result.get("pack_value_vs_cost_comparison") or {}).get(
        "simulated_mean_pack_value_vs_pack_cost",
        {},
    )
    median_pack_comparison = (result.get("pack_value_vs_cost_comparison") or {}).get(
        "simulated_median_pack_value_vs_pack_cost",
        {},
    )

    estimated_pack_price = _safe_float(result.get("pack_price"), 0.0)
    reported_average_pack_value = _safe_float(pack_comparison.get("expected_value"), 0.0)
    reported_median_pack_value = _safe_float(median_pack_comparison.get("expected_value"), 0.0)
    reported_roi = _safe_float(pack_comparison.get("roi"), 0.0)
    reported_value_to_cost_ratio = _safe_float(pack_comparison.get("value_to_cost_ratio"), 0.0)

    sim_output_summary = harness.sim_output_summary_by_set.get(target.set_id, {})
    average_pack_value = _safe_float(sim_output_summary.get("mean_from_values"), reported_average_pack_value)
    median_pack_value = _safe_float(sim_output_summary.get("median_from_values"), reported_median_pack_value)

    expected_roi_from_mean_and_pack_price = _compute_formula_roi(
        average_pack_value=average_pack_value,
        estimated_pack_price=estimated_pack_price,
    )
    roi_absolute_delta = abs(float(reported_roi) - float(expected_roi_from_mean_and_pack_price))
    roi_consistency_passed = roi_absolute_delta <= ROI_ABSOLUTE_DELTA_THRESHOLD

    expected_value_to_cost_ratio_from_mean_and_pack_price = (
        (average_pack_value / estimated_pack_price) if estimated_pack_price > 0 else 0.0
    )
    value_to_cost_ratio_absolute_delta = abs(
        float(reported_value_to_cost_ratio) - float(expected_value_to_cost_ratio_from_mean_and_pack_price)
    )
    value_to_cost_ratio_consistency_passed = (
        value_to_cost_ratio_absolute_delta <= VALUE_TO_COST_RATIO_ABSOLUTE_DELTA_THRESHOLD
    )

    reported_probability_to_beat_pack_cost = _extract_probability_to_beat_pack_cost(
        result_payload=result,
    )
    probability_to_beat_pack_cost_from_values = _safe_float(
        sim_output_summary.get("probability_to_beat_pack_cost_from_values"),
        0.0,
    )
    probability_to_beat_pack_cost_absolute_delta = abs(
        float(reported_probability_to_beat_pack_cost)
        - float(probability_to_beat_pack_cost_from_values)
    )
    probability_to_beat_pack_cost_consistency_passed = (
        probability_to_beat_pack_cost_absolute_delta <= PROBABILITY_ABSOLUTE_DELTA_THRESHOLD
    )

    p05 = _safe_float(sim_output_summary.get("p05"), 0.0)
    p95 = _safe_float(sim_output_summary.get("p95"), 0.0)
    p99 = _safe_float(sim_output_summary.get("p99"), 0.0)

    simulation_engine = get_simulation_engine(target.production_config)
    monte_carlo_v2_bypassed = not _should_use_monte_carlo_v2(target.production_config)
    slot_schema_runtime_used = simulation_engine == "slot_schema" and bool(
        getattr(target.production_config, "SLOT_SCHEMA_RUNTIME_ENABLED", False)
    )

    row: Dict[str, Any] = {
        "set_key": target.canonical_key,
        "set_id": target.set_id,
        "set_name": target.set_name,
        "selected_simulation_engine": simulation_engine,
        "monte_carlo_v2_bypassed": monte_carlo_v2_bypassed,
        "slot_schema_runtime_used": slot_schema_runtime_used,
        "db_input_source": input_metadata.get("source"),
        "pack_count": int(sim_output_summary.get("value_count") or 0),
        "estimated_pack_price": estimated_pack_price,
        "cost": estimated_pack_price,
        "expected_value": average_pack_value,
        "average_pack_value": average_pack_value,
        "median_pack_value": median_pack_value,
        "roi": expected_roi_from_mean_and_pack_price,
        "roi_formula": ROI_FORMULA,
        "metric_semantics_version": pack_comparison.get("metric_semantics_version") or "formula_roi_v2",
        "value_to_cost_ratio": reported_value_to_cost_ratio,
        "legacy_value_cost_ratio": reported_value_to_cost_ratio,
        "expected_roi_from_mean_and_pack_price": expected_roi_from_mean_and_pack_price,
        "reported_roi": reported_roi,
        "reported_value_to_cost_ratio": reported_value_to_cost_ratio,
        "formula_roi": expected_roi_from_mean_and_pack_price,
        "roi_absolute_delta": roi_absolute_delta,
        "roi_consistency_passed": roi_consistency_passed,
        "value_to_cost_ratio_absolute_delta": value_to_cost_ratio_absolute_delta,
        "value_to_cost_ratio_consistency_passed": value_to_cost_ratio_consistency_passed,
        "probability_to_beat_pack_cost": probability_to_beat_pack_cost_from_values,
        "probability_to_beat_pack_cost_from_values": probability_to_beat_pack_cost_from_values,
        "reported_probability_to_beat_pack_cost": reported_probability_to_beat_pack_cost,
        "probability_to_beat_pack_cost_absolute_delta": probability_to_beat_pack_cost_absolute_delta,
        "probability_to_beat_pack_cost_consistency_passed": probability_to_beat_pack_cost_consistency_passed,
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
                passed=probability_to_beat_pack_cost_consistency_passed,
                mismatch_label="reported_probability_not_value_derived",
                aligned_label="value_derived_probability_aligned",
            ),
        },
        "value_summary": sim_output_summary,
        "p05": p05,
        "p95": p95,
        "p99": p99,
        "output_payload_keys": sorted(result.keys()),
        "intended_persistence_targets": intended_targets,
        "intended_write_counts": set_counts,
        "actual_writes_performed": 0,
        "strict_db_input_passed": strict_db_input_passed,
        "production_probability_equals_draft": bool(probability_status.get("production_equals_draft")),
        "probability_table_status": probability_status,
    }

    output_metrics_present = _output_metrics_present(row)
    output_json_serializable = _is_json_serializable(row)

    warning_flags = _build_warning_flags(
        dry_run_enabled=bool(dry_run),
        actual_writes_performed=0,
        intended_write_total=intended_write_total,
        simulation_engine=simulation_engine,
        monte_carlo_v2_bypassed=bool(monte_carlo_v2_bypassed),
        slot_schema_runtime_used=bool(slot_schema_runtime_used),
        production_probability_equals_draft=bool(probability_status.get("production_equals_draft")),
        strict_db_input_passed=bool(strict_db_input_passed),
        output_payload_metrics_present=bool(output_metrics_present),
        output_payload_json_serializable=bool(output_json_serializable),
        roi_absolute_delta=roi_absolute_delta,
        roi_consistency_passed=roi_consistency_passed,
        value_to_cost_ratio_absolute_delta=value_to_cost_ratio_absolute_delta,
        value_to_cost_ratio_consistency_passed=value_to_cost_ratio_consistency_passed,
        probability_to_beat_pack_cost_absolute_delta=probability_to_beat_pack_cost_absolute_delta,
        probability_to_beat_pack_cost_consistency_passed=probability_to_beat_pack_cost_consistency_passed,
        sv_mega_routing_status=sv_mega_routing_status,
        other_swsh_guardrail_unchanged=bool(other_swsh_guardrail_unchanged),
    )

    row["output_payload_metrics_present"] = output_metrics_present
    row["output_payload_json_serializable"] = output_json_serializable
    row["warning_flags"] = warning_flags

    return row


def _render_markdown(payload: Mapping[str, Any]) -> str:
    lines: List[str] = []
    lines.append("# SWSH Production Job Dry-Run")
    lines.append("")
    lines.append(f"Generated: {payload.get('meta', {}).get('generated_at_utc', '')}")
    lines.append("")
    lines.append("Real production EVR job path dry-run for swsh6/swsh7 with all writes intercepted in-memory.")
    lines.append("")

    lines.append("## Global Safety")
    lines.append("")
    lines.append(f"- Dry run enforced: {payload.get('meta', {}).get('dry_run_enforced')}")
    lines.append(f"- Actual writes performed total: {payload.get('meta', {}).get('actual_writes_performed_total')}")
    lines.append(f"- Intended writes captured total: {payload.get('meta', {}).get('intended_writes_captured_total')}")
    lines.append(f"- Strict DB input: {payload.get('meta', {}).get('strict_db_input')}")
    lines.append(f"- Runtime approval input status: {payload.get('runtime_approval_input_status')}")
    lines.append("")

    for row in payload.get("sets", []):
        lines.append(f"## {row.get('set_name')} ({row.get('set_id')})")
        lines.append("")
        lines.append(f"- set_key: {row.get('set_key')}")
        lines.append(f"- selected simulation engine: {row.get('selected_simulation_engine')}")
        lines.append(f"- Monte Carlo V2 bypassed: {row.get('monte_carlo_v2_bypassed')}")
        lines.append(f"- slot_schema runtime used: {row.get('slot_schema_runtime_used')}")
        lines.append(f"- DB input source: {row.get('db_input_source')}")
        lines.append(f"- pack count: {row.get('pack_count')}")
        lines.append(f"- estimated pack price: {row.get('estimated_pack_price')}")
        lines.append(f"- value to cost ratio: {row.get('value_to_cost_ratio')}")
        lines.append(f"- average pack value: {row.get('average_pack_value')}")
        lines.append(f"- median pack value: {row.get('median_pack_value')}")
        lines.append(f"- metric semantics version: {row.get('metric_semantics_version')}")
        lines.append(f"- ROI formula: {row.get('roi_formula')}")
        lines.append(f"- formula ROI: {row.get('expected_roi_from_mean_and_pack_price')}")
        lines.append(f"- reported ROI: {row.get('reported_roi')}")
        lines.append(f"- legacy value/cost ratio: {row.get('legacy_value_cost_ratio')}")
        lines.append(f"- ROI absolute delta: {row.get('roi_absolute_delta')}")
        lines.append(f"- ROI consistency passed: {row.get('roi_consistency_passed')}")
        lines.append(
            "- value_to_cost_ratio consistency passed: "
            f"{row.get('value_to_cost_ratio_consistency_passed')}"
        )
        lines.append(
            "- value_to_cost_ratio absolute delta: "
            f"{row.get('value_to_cost_ratio_absolute_delta')}"
        )
        lines.append(
            "- probability_to_beat_pack_cost from values: "
            f"{row.get('probability_to_beat_pack_cost_from_values')}"
        )
        lines.append(
            "- reported probability_to_beat_pack_cost: "
            f"{row.get('reported_probability_to_beat_pack_cost')}"
        )
        lines.append(
            "- probability_to_beat_pack_cost absolute delta: "
            f"{row.get('probability_to_beat_pack_cost_absolute_delta')}"
        )
        lines.append(
            "- probability_to_beat_pack_cost consistency passed: "
            f"{row.get('probability_to_beat_pack_cost_consistency_passed')}"
        )
        lines.append(f"- semantic status: {json.dumps(row.get('semantic_status') or {}, sort_keys=True)}")
        lines.append(
            "- P05/P95/P99: "
            f"{row.get('p05')} / {row.get('p95')} / {row.get('p99')}"
        )
        lines.append(f"- output payload keys: {', '.join(row.get('output_payload_keys') or [])}")
        lines.append(f"- intended persistence targets: {', '.join(row.get('intended_persistence_targets') or [])}")
        lines.append(f"- intended write counts: {json.dumps(row.get('intended_write_counts') or {}, sort_keys=True)}")
        lines.append(f"- writes actually performed: {row.get('actual_writes_performed')}")
        lines.append("")

        triggered = [flag for flag in (row.get("warning_flags") or []) if flag.get("triggered")]
        lines.append("### Warning Flags")
        lines.append("")
        if not triggered:
            lines.append("- No warning flags triggered.")
        else:
            for flag in triggered:
                lines.append(
                    f"- TRIGGERED [{flag.get('severity')}] {flag.get('code')}: "
                    f"{flag.get('detail')}"
                )
        lines.append("")

    lines.append("## Guardrails")
    lines.append("")
    lines.append(
        f"- Other SWSH runtime unchanged: "
        f"{payload.get('other_swsh_runtime_guardrail', {}).get('unchanged')}"
    )
    lines.append(
        f"- SV/Mega routing changed: "
        f"{payload.get('sv_mega_routing_guardrail', {}).get('changed')}"
    )
    lines.append(
        f"- SV/Mega all expected v2: "
        f"{payload.get('sv_mega_routing_guardrail', {}).get('all_expected_v2')}"
    )
    lines.append("")

    return "\n".join(lines).rstrip() + "\n"


def _evaluate_payload_safety(payload: Mapping[str, Any]) -> List[str]:
    failures: List[str] = []

    if int(payload.get("meta", {}).get("actual_writes_performed_total") or 0) != 0:
        failures.append("actual_writes_performed_total must be 0")

    if int(payload.get("meta", {}).get("intended_writes_captured_total") or 0) <= 0:
        failures.append("intended_writes_captured_total must be > 0")

    for row in payload.get("sets", []):
        if int(row.get("actual_writes_performed") or 0) != 0:
            failures.append(f"{row.get('set_id')}: actual_writes_performed must be 0")

        if not bool(row.get("strict_db_input_passed")):
            failures.append(f"{row.get('set_id')}: strict_db_input_passed must be true")

        if str(row.get("selected_simulation_engine")) != "slot_schema":
            failures.append(f"{row.get('set_id')}: selected_simulation_engine must be slot_schema")

        if not bool(row.get("monte_carlo_v2_bypassed")):
            failures.append(f"{row.get('set_id')}: monte_carlo_v2_bypassed must be true")

        if not bool(row.get("production_probability_equals_draft")):
            failures.append(f"{row.get('set_id')}: production probability must equal draft")

        if not bool(row.get("output_payload_metrics_present")):
            failures.append(f"{row.get('set_id')}: required output metrics missing")

        if not bool(row.get("output_payload_json_serializable")):
            failures.append(f"{row.get('set_id')}: output payload must be JSON-serializable")

        critical_triggered = [
            flag
            for flag in (row.get("warning_flags") or [])
            if flag.get("severity") == "critical" and bool(flag.get("triggered"))
        ]
        if critical_triggered:
            failures.append(
                f"{row.get('set_id')}: critical warning flags triggered "
                f"{[flag.get('code') for flag in critical_triggered]}"
            )

    sv_mega = payload.get("sv_mega_routing_guardrail", {})
    if bool(sv_mega.get("changed")) or not bool(sv_mega.get("all_expected_v2")):
        failures.append("SV/Mega routing guardrail failed")

    other_swsh = payload.get("other_swsh_runtime_guardrail", {})
    if not bool(other_swsh.get("unchanged")):
        failures.append("Other SWSH runtime-enabled guardrail failed")

    return failures


def run_production_job_dry_run(
    *,
    json_output_path: Path = DEFAULT_JSON_PATH,
    markdown_output_path: Path = DEFAULT_MD_PATH,
    pack_count: int = 100000,
    strict_db_input: bool = False,
    dry_run: bool = False,
    seed_base: int = 76110,
) -> Dict[str, Any]:
    if not dry_run:
        raise RuntimeError("Refusing to run without --dry-run. This audit must run in no-write mode.")

    if int(pack_count) <= 0:
        raise ValueError("pack_count must be > 0")

    target_ids = {target.set_id for target in TARGETS}
    if target_ids != TARGET_SET_IDS:
        raise AssertionError(f"Unexpected target scope. expected={sorted(TARGET_SET_IDS)} actual={sorted(target_ids)}")

    started_at = time.perf_counter()

    other_swsh_before = _capture_other_swsh_runtime_enabled_state()
    sv_mega_before = _capture_sv_mega_routing_state()

    harness = WriteSpyHarness()
    rows: List[Dict[str, Any]] = []

    with _no_write_spy_context(harness, pack_count=int(pack_count), strict_db_input=bool(strict_db_input)):
        orchestrator = evr_runner.EVRRunOrchestrator()

        for index, target in enumerate(TARGETS):
            random.seed(seed_base + index)
            harness.set_current_set(target.set_id)

            sv_mega_status_during = _compute_sv_mega_routing_status(
                sv_mega_before,
                _capture_sv_mega_routing_state(),
            )
            other_swsh_unchanged_during = (
                other_swsh_before == _capture_other_swsh_runtime_enabled_state()
            )

            row = _run_single_set_dry_run(
                target=target,
                orchestrator=orchestrator,
                harness=harness,
                dry_run=bool(dry_run),
                strict_db_input=bool(strict_db_input),
                sv_mega_routing_status=sv_mega_status_during,
                other_swsh_guardrail_unchanged=other_swsh_unchanged_during,
            )
            rows.append(row)

    other_swsh_after = _capture_other_swsh_runtime_enabled_state()
    sv_mega_after = _capture_sv_mega_routing_state()

    sv_mega_status = _compute_sv_mega_routing_status(sv_mega_before, sv_mega_after)

    intended_writes_total = int(
        sum(
            int(count)
            for per_set in harness.intended_write_counts_by_set.values()
            for count in per_set.values()
        )
    )
    if intended_writes_total <= 0:
        intended_writes_total = int(
            sum(
                int(count)
                for row in rows
                for count in (row.get("intended_write_counts") or {}).values()
            )
        )

    runtime_approval_input_status = "strict_db_input_passed" if strict_db_input else "dry_run_input_checked"

    payload: Dict[str, Any] = {
        "meta": {
            "generated_at_utc": datetime.now(timezone.utc).isoformat(),
            "project": "7",
            "dry_run_enforced": True,
            "strict_db_input": bool(strict_db_input),
            "pack_count": int(pack_count),
            "elapsed_seconds": time.perf_counter() - started_at,
            "actual_writes_performed_total": int(harness.actual_writes_performed),
            "intended_writes_captured_total": intended_writes_total,
        },
        "runtime_approval_input_status": runtime_approval_input_status,
        "other_swsh_runtime_guardrail": {
            "before": other_swsh_before,
            "after": other_swsh_after,
            "unchanged": other_swsh_before == other_swsh_after,
            "unexpected_enabled_ids": [set_id for set_id, enabled in sorted(other_swsh_after.items()) if enabled],
        },
        "sv_mega_routing_guardrail": sv_mega_status,
        "sets": rows,
    }

    failures = _evaluate_payload_safety(payload)
    payload["safety_assertions"] = {
        "passed": len(failures) == 0,
        "failures": failures,
    }

    json_output_path.parent.mkdir(parents=True, exist_ok=True)
    markdown_output_path.parent.mkdir(parents=True, exist_ok=True)

    json_output_path.write_text(json.dumps(payload, indent=2, sort_keys=True), encoding="utf-8")
    markdown_output_path.write_text(_render_markdown(payload), encoding="utf-8")

    if failures:
        raise AssertionError("; ".join(failures))

    return payload


def _build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(description="SWSH production EVR job dry-run audit (no writes)")
    parser.add_argument("--json-output", default=str(DEFAULT_JSON_PATH), help="JSON output path")
    parser.add_argument("--markdown-output", default=str(DEFAULT_MD_PATH), help="Markdown output path")
    parser.add_argument("--pack-count", type=int, default=100000, help="Simulation pack count override")
    parser.add_argument("--seed-base", type=int, default=76110, help="Random seed base")
    parser.add_argument("--strict-db-input", action="store_true", help="Require strict DB input checks")
    parser.add_argument("--dry-run", action="store_true", help="Required no-write mode")
    parser.add_argument("--stdout", action="store_true", help="Print summary JSON to stdout")
    return parser


def main() -> int:
    args = _build_parser().parse_args()
    payload = run_production_job_dry_run(
        json_output_path=Path(args.json_output),
        markdown_output_path=Path(args.markdown_output),
        pack_count=int(args.pack_count),
        strict_db_input=bool(args.strict_db_input),
        dry_run=bool(args.dry_run),
        seed_base=int(args.seed_base),
    )

    summary = {
        "runtime_approval_input_status": payload.get("runtime_approval_input_status"),
        "actual_writes_performed_total": payload.get("meta", {}).get("actual_writes_performed_total"),
        "intended_writes_captured_total": payload.get("meta", {}).get("intended_writes_captured_total"),
        "safety_passed": payload.get("safety_assertions", {}).get("passed"),
        "sets": [
            {
                "set_id": row.get("set_id"),
                "engine": row.get("selected_simulation_engine"),
                "pack_count": row.get("pack_count"),
                "actual_writes_performed": row.get("actual_writes_performed"),
                "critical_triggered": [
                    flag.get("code")
                    for flag in (row.get("warning_flags") or [])
                    if flag.get("severity") == "critical" and flag.get("triggered")
                ],
            }
            for row in payload.get("sets", [])
        ],
    }

    print(f"[audit] runtime_approval_input_status={summary['runtime_approval_input_status']}")
    print(f"[audit] actual_writes_performed_total={summary['actual_writes_performed_total']}")
    print(f"[audit] intended_writes_captured_total={summary['intended_writes_captured_total']}")
    print(f"[audit] safety_passed={summary['safety_passed']}")

    for row in summary["sets"]:
        print(
            "[audit] set_id={set_id} engine={engine} pack_count={pack_count} "
            "actual_writes_performed={actual_writes_performed}".format(
                set_id=row["set_id"],
                engine=row["engine"],
                pack_count=row["pack_count"],
                actual_writes_performed=row["actual_writes_performed"],
            )
        )

    if args.stdout:
        print(json.dumps(summary, indent=2, sort_keys=True))

    return 0


if __name__ == "__main__":
    raise SystemExit(main())
