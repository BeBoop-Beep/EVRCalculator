"""Project 17B.3g Fusion Strike controlled persistence preflight.

Safety behavior:
- Strict target scope: swsh8 only
- Dry-run enforced by default (no writes)
- Intended writes are captured by intercepting repository insert boundaries
- Execute mode is gated by explicit flag + confirmation token + scope checks
"""

from __future__ import annotations

import argparse
import json
import random
import sys
import time
from contextlib import contextmanager
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Dict, Mapping, Optional


REPO_ROOT = Path(__file__).resolve().parents[2]
if str(REPO_ROOT) not in sys.path:
    sys.path.append(str(REPO_ROOT))

import backend.jobs.evr_runner as evr_runner
import backend.simulations.evrSimulator as evr_simulator
from backend.constants.tcg.pokemon.swordAndShieldEra.setMap import SET_ALIAS_MAP, SET_CONFIG_MAP
from backend.db.repositories import calculation_runs_repository
from backend.simulations.evrSimulator import _should_use_monte_carlo_v2, get_simulation_engine


DEFAULT_JSON_PATH = Path("logs/audits/swsh8_controlled_persistence_preflight.json")

TARGET_SET_ID = "swsh8"
TARGET_CANONICAL_KEY = "fusionStrike"
TARGET_ALLOWLIST = {TARGET_SET_ID}

EXECUTE_CONFIRMATION_TOKEN = "swsh8-controlled-persistence-execute"

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


def _safe_float(value: Any, default: float = 0.0) -> float:
    try:
        parsed = float(value)
    except (TypeError, ValueError):
        return default
    return parsed if parsed == parsed else default


def _quantile(values: list[float], q: float) -> float:
    if not values:
        return 0.0
    ordered = sorted(float(v) for v in values)
    if len(ordered) == 1:
        return ordered[0]
    q_clamped = max(0.0, min(1.0, float(q)))
    index = q_clamped * float(len(ordered) - 1)
    lower = int(index)
    upper = min(lower + 1, len(ordered) - 1)
    if lower == upper:
        return ordered[lower]
    weight = index - float(lower)
    return (ordered[lower] * (1.0 - weight)) + (ordered[upper] * weight)


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


class PreflightHarness:
    """Capture intended writes while preventing DB writes."""

    def __init__(self) -> None:
        self.current_set_id: Optional[str] = None
        self.intended_write_counts_by_set: Dict[str, Dict[str, int]] = {}
        self.insert_payload_keys_by_set: Dict[str, Dict[str, list[str]]] = {}
        self.next_id = 1
        self.actual_writes_performed_total = 0
        self.sim_output_summary_by_set: Dict[str, Dict[str, Any]] = {}

    def set_current_set(self, set_id: str) -> None:
        self.current_set_id = str(set_id)
        self.intended_write_counts_by_set.setdefault(self.current_set_id, {})
        self.insert_payload_keys_by_set.setdefault(self.current_set_id, {})

    def _bump_id(self) -> str:
        token = f"dry-id-{self.next_id}"
        self.next_id += 1
        return token

    def _record_intended(self, table_name: str, payload: Mapping[str, Any]) -> None:
        if self.current_set_id is None:
            return

        table = str(table_name)
        set_counts = self.intended_write_counts_by_set.setdefault(self.current_set_id, {})
        set_counts[table] = int(set_counts.get(table, 0)) + 1

        key_map = self.insert_payload_keys_by_set.setdefault(self.current_set_id, {})
        key_map.setdefault(table, sorted(str(k) for k in payload.keys()))

    def insert_required_payload_spy(self, table_name: str, payload: Dict[str, Any], context: str) -> Dict[str, Any]:
        _ = context
        self._record_intended(table_name=table_name, payload=payload)
        row = dict(payload)
        row.setdefault("id", self._bump_id())
        return row

    def spy_persist_simulation_outputs(
        self,
        *,
        run_id: Any,
        sim_results: Dict[str, Any],
        pack_metrics: Dict[str, Any],
        derived: Dict[str, Any] | None,
    ) -> Dict[str, Any]:
        normalized_sim_results = _normalized_sim_results_for_persistence(sim_results)
        values = [float(v) for v in (normalized_sim_results.get("values") or [])]
        if self.current_set_id is not None:
            self.sim_output_summary_by_set[self.current_set_id] = {
                "value_count": len(values),
                "mean_from_values": (float(sum(values)) / float(len(values))) if values else 0.0,
                "pack_metrics_total_ev": _safe_float(pack_metrics.get("total_ev"), 0.0),
                "derived_present": bool(isinstance(derived, Mapping)),
            }
        return self._original_persist_outputs(
            run_id=run_id,
            sim_results=normalized_sim_results,
            pack_metrics=pack_metrics,
            derived=derived,
        )


class ExecuteWriteMonitor:
    """Track insert calls during controlled execute mode."""

    def __init__(self) -> None:
        self.write_counts_by_table: Dict[str, int] = {}
        self.payload_keys_by_table: Dict[str, list[str]] = {}

    def record(self, table_name: str, payload: Mapping[str, Any]) -> None:
        table = str(table_name)
        self.write_counts_by_table[table] = int(self.write_counts_by_table.get(table, 0)) + 1
        self.payload_keys_by_table.setdefault(table, sorted(str(k) for k in payload.keys()))


def _make_runner_compatible_config(config_cls: type) -> type:
    if hasattr(config_cls, "get_rarity_pack_multiplier"):
        return config_cls

    class _RunnerCompatibleConfig(config_cls):
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


def _assert_swsh8_runtime_contract(*, config_cls: type) -> Dict[str, Any]:
    config = config_cls()

    if str(getattr(config, "SET_ID", "")).strip().lower() != TARGET_SET_ID:
        raise AssertionError(f"Unexpected SET_ID for Fusion Strike config: {getattr(config, 'SET_ID', None)!r}")

    selected_engine = get_simulation_engine(config)
    if selected_engine != "slot_schema":
        raise AssertionError(f"Expected slot_schema engine, got {selected_engine!r}")

    if not bool(getattr(config, "SLOT_SCHEMA_RUNTIME_ENABLED", False)):
        raise AssertionError("SLOT_SCHEMA_RUNTIME_ENABLED must be True for swsh8 preflight")

    return {
        "set_id": str(getattr(config, "SET_ID", "")),
        "set_name": str(getattr(config, "SET_NAME", "")),
        "simulation_engine": selected_engine,
        "slot_schema_runtime_enabled": bool(getattr(config, "SLOT_SCHEMA_RUNTIME_ENABLED", False)),
        "monte_carlo_v2_bypassed": not _should_use_monte_carlo_v2(config),
    }


@contextmanager
def _swsh8_no_write_persistence_preflight_context(*, harness: PreflightHarness, pack_count: int, config_cls: type):
    if int(pack_count) <= 0:
        raise ValueError("pack_count must be > 0")

    original_resolve_set_config = evr_runner._resolve_set_config
    original_run_simulation = evr_simulator.run_simulation
    original_run_simulation_v2 = evr_simulator.run_simulation_v2
    original_simulate_slot_schema_packs = evr_simulator.simulate_slot_schema_packs
    original_insert_required_payload = calculation_runs_repository._insert_required_payload
    original_persist_outputs = evr_runner.persist_simulation_outputs

    harness._original_persist_outputs = original_persist_outputs

    compatible_config_cls = _make_runner_compatible_config(config_cls)

    local_target_lookup: Dict[str, Any] = {
        TARGET_SET_ID: (compatible_config_cls, TARGET_CANONICAL_KEY),
        TARGET_CANONICAL_KEY.lower(): (compatible_config_cls, TARGET_CANONICAL_KEY),
        str(getattr(config_cls, "SET_NAME", "")).strip().lower(): (compatible_config_cls, TARGET_CANONICAL_KEY),
    }

    for alias_key, alias_value in SET_ALIAS_MAP.items():
        if str(alias_value) == TARGET_CANONICAL_KEY:
            local_target_lookup[str(alias_key).strip().lower()] = (compatible_config_cls, TARGET_CANONICAL_KEY)

    def _resolve_set_config_override(target_set_identifier: str) -> tuple[Any, str]:
        key = str(target_set_identifier or "").strip().lower()
        if key in local_target_lookup:
            return local_target_lookup[key]
        raise RuntimeError(
            "Controlled persistence preflight scope violation: only swsh8/fusionStrike is allowlisted "
            f"for this script. received_target={target_set_identifier!r}"
        )

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
        evr_runner._resolve_set_config = _resolve_set_config_override
        evr_simulator.run_simulation = _run_simulation_override
        evr_simulator.run_simulation_v2 = _run_simulation_v2_override
        evr_simulator.simulate_slot_schema_packs = _simulate_slot_schema_packs_override

        calculation_runs_repository._insert_required_payload = harness.insert_required_payload_spy
        evr_runner.persist_simulation_outputs = harness.spy_persist_simulation_outputs
        yield
    finally:
        evr_runner._resolve_set_config = original_resolve_set_config
        evr_simulator.run_simulation = original_run_simulation
        evr_simulator.run_simulation_v2 = original_run_simulation_v2
        evr_simulator.simulate_slot_schema_packs = original_simulate_slot_schema_packs
        calculation_runs_repository._insert_required_payload = original_insert_required_payload
        evr_runner.persist_simulation_outputs = original_persist_outputs


@contextmanager
def _swsh8_execute_monitor_context(*, monitor: ExecuteWriteMonitor, pack_count: int, config_cls: type):
    if int(pack_count) <= 0:
        raise ValueError("pack_count must be > 0")

    original_resolve_set_config = evr_runner._resolve_set_config
    original_run_simulation = evr_simulator.run_simulation
    original_run_simulation_v2 = evr_simulator.run_simulation_v2
    original_simulate_slot_schema_packs = evr_simulator.simulate_slot_schema_packs
    original_insert_required_payload = calculation_runs_repository._insert_required_payload
    original_persist_outputs = evr_runner.persist_simulation_outputs

    compatible_config_cls = _make_runner_compatible_config(config_cls)

    local_target_lookup: Dict[str, Any] = {
        TARGET_SET_ID: (compatible_config_cls, TARGET_CANONICAL_KEY),
        TARGET_CANONICAL_KEY.lower(): (compatible_config_cls, TARGET_CANONICAL_KEY),
        str(getattr(config_cls, "SET_NAME", "")).strip().lower(): (compatible_config_cls, TARGET_CANONICAL_KEY),
    }

    for alias_key, alias_value in SET_ALIAS_MAP.items():
        if str(alias_value) == TARGET_CANONICAL_KEY:
            local_target_lookup[str(alias_key).strip().lower()] = (compatible_config_cls, TARGET_CANONICAL_KEY)

    def _resolve_set_config_override(target_set_identifier: str) -> tuple[Any, str]:
        key = str(target_set_identifier or "").strip().lower()
        if key in local_target_lookup:
            return local_target_lookup[key]
        raise RuntimeError(
            "Controlled execute scope violation: only swsh8/fusionStrike is allowlisted "
            f"for this script. received_target={target_set_identifier!r}"
        )

    def _run_simulation_override(*args: Any, **kwargs: Any) -> Dict[str, Any]:
        kwargs["n"] = int(pack_count)
        return original_run_simulation(*args, **kwargs)

    def _run_simulation_v2_override(*args: Any, **kwargs: Any) -> Dict[str, Any]:
        kwargs["n"] = int(pack_count)
        return original_run_simulation_v2(*args, **kwargs)

    def _simulate_slot_schema_packs_override(*args: Any, **kwargs: Any) -> Dict[str, Any]:
        kwargs["num_packs"] = int(pack_count)
        return original_simulate_slot_schema_packs(*args, **kwargs)

    def _insert_required_payload_monitored(table_name: str, payload: Dict[str, Any], context: str) -> Dict[str, Any]:
        monitor.record(table_name=table_name, payload=payload)
        return original_insert_required_payload(table_name, payload, context)

    def _persist_simulation_outputs_wrapper(
        *,
        run_id: Any,
        sim_results: Dict[str, Any],
        pack_metrics: Dict[str, Any],
        derived: Dict[str, Any] | None,
    ) -> Dict[str, Any]:
        normalized_sim_results = _normalized_sim_results_for_persistence(sim_results)
        return original_persist_outputs(
            run_id=run_id,
            sim_results=normalized_sim_results,
            pack_metrics=pack_metrics,
            derived=derived,
        )

    try:
        evr_runner._resolve_set_config = _resolve_set_config_override
        evr_simulator.run_simulation = _run_simulation_override
        evr_simulator.run_simulation_v2 = _run_simulation_v2_override
        evr_simulator.simulate_slot_schema_packs = _simulate_slot_schema_packs_override
        calculation_runs_repository._insert_required_payload = _insert_required_payload_monitored
        evr_runner.persist_simulation_outputs = _persist_simulation_outputs_wrapper
        yield
    finally:
        evr_runner._resolve_set_config = original_resolve_set_config
        evr_simulator.run_simulation = original_run_simulation
        evr_simulator.run_simulation_v2 = original_run_simulation_v2
        evr_simulator.simulate_slot_schema_packs = original_simulate_slot_schema_packs
        calculation_runs_repository._insert_required_payload = original_insert_required_payload
        evr_runner.persist_simulation_outputs = original_persist_outputs


def run_swsh8_controlled_persistence_preflight(
    *,
    json_output_path: Path = DEFAULT_JSON_PATH,
    pack_count: int = 500,
    dry_run: bool = False,
    execute: bool = False,
    confirm_token: Optional[str] = None,
    target_set_id: str = TARGET_SET_ID,
    seed: int = 17383,
) -> Dict[str, Any]:
    scope = {str(target_set_id).strip().lower()}

    if scope != TARGET_ALLOWLIST:
        raise RuntimeError(
            "Scope must be exactly swsh8. "
            f"received_scope={sorted(scope)} expected_scope={sorted(TARGET_ALLOWLIST)}"
        )

    if bool(execute):
        if str(confirm_token or "") != EXECUTE_CONFIRMATION_TOKEN:
            raise RuntimeError(
                "Execute mode requires valid confirmation token. "
                "Use --confirm-token with the approved value."
            )
        if not EXPECTED_WRITE_TABLE_ALLOWLIST:
            raise RuntimeError("Execute mode requires expected write table allowlist to be defined")
    elif not bool(dry_run):
        raise RuntimeError("Refusing to run without --dry-run. Preflight is no-write by default.")

    if int(pack_count) <= 0:
        raise ValueError("pack_count must be > 0")

    if TARGET_ALLOWLIST != {TARGET_SET_ID}:
        raise AssertionError(f"Unexpected allowlist scope: {sorted(TARGET_ALLOWLIST)}")

    resolved_canonical = SET_ALIAS_MAP.get(TARGET_SET_ID)
    if resolved_canonical != TARGET_CANONICAL_KEY:
        raise AssertionError(
            "SWSH alias map resolution mismatch for swsh8: "
            f"expected={TARGET_CANONICAL_KEY} actual={resolved_canonical}"
        )

    config_cls = SET_CONFIG_MAP.get(TARGET_CANONICAL_KEY)
    if config_cls is None:
        raise AssertionError("Fusion Strike config is missing from SWSH SET_CONFIG_MAP")

    runtime_contract = _assert_swsh8_runtime_contract(config_cls=config_cls)

    started_at = time.perf_counter()
    random.seed(int(seed))

    orchestrator = evr_runner.EVRRunOrchestrator()
    run_result: Dict[str, Any]
    intended_counts: Dict[str, int]
    intended_total: int
    write_tables_touched: list[str]
    unexpected_write_tables: list[str]
    sim_summary: Dict[str, Any]
    actual_writes_performed_total: int
    insert_payload_keys_by_table: Dict[str, list[str]]

    if bool(execute):
        monitor = ExecuteWriteMonitor()
        with _swsh8_execute_monitor_context(
            monitor=monitor,
            pack_count=int(pack_count),
            config_cls=config_cls,
        ):
            run_result = orchestrator.run(
                target_set_identifier=TARGET_SET_ID,
                input_source="db",
                run_metadata={
                    "trigger": "audit_swsh8_controlled_persistence_preflight",
                    "execute": True,
                    "dry_run": False,
                    "preflight": False,
                    "set_id": TARGET_SET_ID,
                    "pack_count_override": int(pack_count),
                },
            )

        intended_counts = dict(monitor.write_counts_by_table)
        intended_total = int(sum(int(v) for v in intended_counts.values()))
        write_tables_touched = sorted(intended_counts.keys())
        unexpected_write_tables = sorted(set(write_tables_touched) - EXPECTED_WRITE_TABLE_ALLOWLIST)
        actual_writes_performed_total = intended_total
        insert_payload_keys_by_table = dict(monitor.payload_keys_by_table)
        sim_results = (run_result.get("sim_results") if isinstance(run_result, Mapping) else None) or {}
        values = [float(v) for v in (sim_results.get("values") or [])] if isinstance(sim_results, Mapping) else []
        sim_summary = {
            "value_count": len(values),
            "mean_from_values": (float(sum(values)) / float(len(values))) if values else 0.0,
        }
    else:
        harness = PreflightHarness()
        harness.set_current_set(TARGET_SET_ID)

        with _swsh8_no_write_persistence_preflight_context(
            harness=harness,
            pack_count=int(pack_count),
            config_cls=config_cls,
        ):
            run_result = orchestrator.run(
                target_set_identifier=TARGET_SET_ID,
                input_source="db",
                run_metadata={
                    "trigger": "audit_swsh8_controlled_persistence_preflight",
                    "dry_run": True,
                    "preflight": True,
                    "no_write": True,
                    "set_id": TARGET_SET_ID,
                    "pack_count_override": int(pack_count),
                },
            )

        intended_counts = harness.intended_write_counts_by_set.get(TARGET_SET_ID, {})
        intended_total = int(sum(int(v) for v in intended_counts.values()))
        write_tables_touched = sorted(intended_counts.keys())
        unexpected_write_tables = sorted(set(write_tables_touched) - EXPECTED_WRITE_TABLE_ALLOWLIST)
        sim_summary = harness.sim_output_summary_by_set.get(TARGET_SET_ID, {})
        actual_writes_performed_total = int(harness.actual_writes_performed_total)
        insert_payload_keys_by_table = harness.insert_payload_keys_by_set.get(TARGET_SET_ID, {})

    failures = []
    if bool(execute):
        if actual_writes_performed_total <= 0:
            failures.append("execute mode expected writes > 0")
    else:
        if actual_writes_performed_total != 0:
            failures.append(
                "actual_writes_performed_total must be 0 in dry-run "
                f"actual={actual_writes_performed_total}"
            )
        if intended_total <= 0:
            failures.append("intended_writes_captured_total must be > 0 in preflight")
    if unexpected_write_tables:
        failures.append(f"unexpected write tables captured: {unexpected_write_tables}")
    if runtime_contract.get("simulation_engine") != "slot_schema":
        failures.append("runtime engine must be slot_schema")
    if not bool(runtime_contract.get("slot_schema_runtime_enabled")):
        failures.append("slot schema runtime must be enabled")
    if not bool(execute) and int(sim_summary.get("value_count") or 0) != int(pack_count):
        failures.append(
            "simulation value_count mismatch "
            f"expected={int(pack_count)} actual={int(sim_summary.get('value_count') or 0)}"
        )
    if run_result.get("derived") is None:
        failures.append("derived metrics missing from run result")

    persisted_parent = ((run_result.get("persisted") or {}).get("parent") or {}) if isinstance(run_result, Mapping) else {}
    persisted_outputs = ((run_result.get("persisted") or {}).get("outputs") or {}) if isinstance(run_result, Mapping) else {}

    payload: Dict[str, Any] = {
        "meta": {
            "generated_at_utc": datetime.now(timezone.utc).isoformat(),
            "project": "17B.3g",
            "script": "audit_swsh8_controlled_persistence_preflight.py",
            "elapsed_seconds": time.perf_counter() - started_at,
            "run_mode": "execute" if bool(execute) else "dry_run",
            "dry_run_enforced": not bool(execute),
            "execute_mode_requested": bool(execute),
            "actual_writes_performed_total": int(actual_writes_performed_total),
            "intended_writes_captured_total": intended_total,
        },
        "target": {
            "allowlist": sorted(TARGET_ALLOWLIST),
            "target_scope_locked": sorted(scope),
            "set_id": TARGET_SET_ID,
            "canonical_key": TARGET_CANONICAL_KEY,
            "pack_count": int(pack_count),
        },
        "execute_guardrails": {
            "execute_flag_required": True,
            "confirmation_token_required": True,
            "confirmation_token_value": EXECUTE_CONFIRMATION_TOKEN,
            "target_scope_must_equal": sorted(TARGET_ALLOWLIST),
            "expected_write_tables_known": True,
            "expected_write_tables": sorted(EXPECTED_WRITE_TABLE_ALLOWLIST),
            "execute_mode_blocked_in_17B_3g": False,
        },
        "runtime_contract": runtime_contract,
        "persistence": {
            "actual_writes_performed_total": int(actual_writes_performed_total),
            "intended_writes_captured_total": intended_total,
            "intended_write_counts": intended_counts,
            "write_tables_touched": write_tables_touched,
            "unexpected_write_tables": unexpected_write_tables,
            "insert_payload_keys_by_table": insert_payload_keys_by_table,
            "persisted_identifiers": {
                "calculation_run_id": persisted_parent.get("run_id") or persisted_parent.get("id"),
                "config_id": persisted_parent.get("config_id") or persisted_parent.get("calculation_config_id"),
                "simulation_summary_id": persisted_outputs.get("run_summary_id")
                or persisted_outputs.get("summary_id")
                or persisted_outputs.get("simulation_summary_id"),
            },
        },
        "result_payload_summary": {
            "total_ev": _safe_float(run_result.get("total_ev"), 0.0),
            "pack_price": run_result.get("pack_price"),
            "pack_value_vs_cost_present": bool(run_result.get("pack_value_vs_cost_comparison")),
            "derived_present": bool(run_result.get("derived")),
            "sim_value_count": int(sim_summary.get("value_count") or 0),
            "sim_mean_from_values": _safe_float(sim_summary.get("mean_from_values"), 0.0),
        },
        "safety_assertions": {
            "passed": len(failures) == 0,
            "failures": failures,
        },
    }

    json_output_path.parent.mkdir(parents=True, exist_ok=True)
    json_output_path.write_text(json.dumps(payload, indent=2, sort_keys=True), encoding="utf-8")
    return payload


def _build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(description="swsh8 controlled persistence preflight (no writes)")
    parser.add_argument("--json-output", default=str(DEFAULT_JSON_PATH), help="JSON output path")
    parser.add_argument("--pack-count", type=int, default=500, help="Bounded simulation pack count override")
    parser.add_argument("--seed", type=int, default=17383, help="Random seed")
    parser.add_argument("--target-set-id", default=TARGET_SET_ID, help="Must be swsh8")
    parser.add_argument("--dry-run", action="store_true", help="Required no-write mode")
    parser.add_argument("--execute", action="store_true", help="Execute mode (guarded, blocked in 17B.3g)")
    parser.add_argument("--confirm-token", default=None, help="Confirmation token required for execute mode")
    parser.add_argument("--stdout", action="store_true", help="Print summary JSON to stdout")
    return parser


def main() -> int:
    args = _build_parser().parse_args()

    try:
        payload = run_swsh8_controlled_persistence_preflight(
            json_output_path=Path(args.json_output),
            pack_count=int(args.pack_count),
            dry_run=bool(args.dry_run),
            execute=bool(args.execute),
            confirm_token=args.confirm_token,
            target_set_id=str(args.target_set_id),
            seed=int(args.seed),
        )
    except Exception as exc:
        print(f"[audit] status=failed error={type(exc).__name__}: {exc}")
        return 1

    summary = {
        "status": "passed" if payload.get("safety_assertions", {}).get("passed") else "failed",
        "set_id": payload.get("target", {}).get("set_id"),
        "allowlist": payload.get("target", {}).get("allowlist"),
        "pack_count": payload.get("target", {}).get("pack_count"),
        "engine": payload.get("runtime_contract", {}).get("simulation_engine"),
        "actual_writes_performed_total": payload.get("persistence", {}).get("actual_writes_performed_total"),
        "intended_writes_captured_total": payload.get("persistence", {}).get("intended_writes_captured_total"),
        "write_tables_touched": payload.get("persistence", {}).get("write_tables_touched", []),
        "safety_failures": payload.get("safety_assertions", {}).get("failures", []),
    }

    print(f"[audit] status={summary['status']}")
    print(f"[audit] set_id={summary['set_id']} allowlist={summary['allowlist']}")
    print(f"[audit] pack_count={summary['pack_count']} engine={summary['engine']}")
    print(
        "[audit] actual_writes_performed_total={} intended_writes_captured_total={}".format(
            summary["actual_writes_performed_total"],
            summary["intended_writes_captured_total"],
        )
    )
    print(f"[audit] write_tables_touched={summary['write_tables_touched']}")

    if args.stdout:
        print(json.dumps(summary, indent=2, sort_keys=True))

    return 0 if summary["status"] == "passed" else 1


if __name__ == "__main__":
    raise SystemExit(main())
