"""Project 17D.2 early regular SWSH controlled runtime dry-run (no writes).

Targets are fixed to:
- swsh1 (Sword & Shield)
- swsh2 (Rebel Clash)
- swsh3 (Darkness Ablaze)

This script reuses production orchestration and simulation paths while intercepting
all persistence boundaries in-memory. It enforces dry-run behavior and bounded
pack counts so runtime assumptions can be validated safely before execute work.
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
from backend.simulations.evrSimulator import (
    _should_use_monte_carlo_v2,
    _validate_slot_schema_runtime_readiness,
    get_simulation_engine,
)
from backend.simulations.slotSchemaContract import validate_slot_schema_config


DEFAULT_JSON_PATH = Path("logs/audits/swsh_early_regular_controlled_runtime_dry_run.json")

TARGET_SET_IDS = ("swsh1", "swsh2", "swsh3")
TARGET_ALLOWLIST = set(TARGET_SET_IDS)

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


class WriteSpyHarness:
    """In-memory write-capture harness for dry-run execution."""

    def __init__(self) -> None:
        self.current_set_id: Optional[str] = None
        self.intended_write_counts_by_set: Dict[str, Dict[str, int]] = {}
        self.actual_writes_performed = 0
        self.input_metadata_by_set: Dict[str, Dict[str, Any]] = {}
        self.sim_output_summary_by_set: Dict[str, Dict[str, Any]] = {}

    def set_current_set(self, set_id: str) -> None:
        self.current_set_id = str(set_id)
        self.intended_write_counts_by_set.setdefault(self.current_set_id, {})

    def _record_intended(self, target: str, count: int) -> None:
        if self.current_set_id is None:
            return
        if int(count) <= 0:
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
        self._record_intended("calculation_configs", 1)
        self._record_intended("calculation_runs", 1)
        self._record_intended("calculation_price_snapshots", snapshot_count)

        suffix = self.current_set_id or "unknown"
        return {
            "config_id": f"dry-config-{suffix}",
            "config_hash": f"dry-hash-{suffix}",
            "run_id": f"dry-run-{suffix}",
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

        self._record_intended("simulation_run_summary", 1)
        self._record_intended("simulation_percentiles", len(percentiles))
        self._record_intended("simulation_pull_summary", len(pull_counts))
        self._record_intended("simulation_state_counts", len(state_counts))
        self._record_intended("simulation_derived_metrics", 1 if isinstance(derived, Mapping) else 0)

        if self.current_set_id is not None:
            self.sim_output_summary_by_set[self.current_set_id] = {
                "value_count": len(values),
                "mean_from_values": (float(sum(values)) / float(len(values))) if values else 0.0,
                "pack_metrics_total_ev": _safe_float(pack_metrics.get("total_ev"), 0.0),
            }

        suffix = self.current_set_id or "unknown"
        return {
            "run_summary_id": f"dry-summary-{suffix}",
            "percentile_count": len(percentiles),
            "pull_summary_count": len(pull_counts),
            "state_count": len(state_counts),
            "derived_metric_count": 1 if isinstance(derived, Mapping) else 0,
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


def _make_input_service_spy(*, harness: WriteSpyHarness, original_service_cls: type) -> type:
    class _InputServiceSpy:
        def __init__(self, *args: Any, **kwargs: Any) -> None:
            self._delegate = original_service_cls(*args, **kwargs)

        def prepare_for_set(self, config: Any, canonical_key: str, set_name: str) -> Dict[str, Any]:
            payload = self._delegate.prepare_for_set(config, canonical_key, set_name)
            dataframe = payload.get("dataframe")
            row_count = int(len(dataframe)) if hasattr(dataframe, "__len__") else 0
            if harness.current_set_id is not None:
                harness.input_metadata_by_set[harness.current_set_id] = {
                    "canonical_key": str(canonical_key),
                    "set_name": str(set_name),
                    "source": "db_evr_input_preparation_service",
                    "row_count": row_count,
                }
            return payload

    return _InputServiceSpy


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


@contextmanager
def _early_regular_no_write_context(*, harness: WriteSpyHarness, pack_count: int, target_lookup: Dict[str, Any]):
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
        original_service_cls=original_input_service,
    )

    def _resolve_set_config_override(target_set_identifier: str) -> tuple[Any, str]:
        key = str(target_set_identifier or "").strip().lower()
        if key in target_lookup:
            return target_lookup[key]
        raise RuntimeError(
            "Controlled runtime dry-run scope violation: target is outside early-regular allowlist "
            f"{sorted(TARGET_ALLOWLIST)}. received_target={target_set_identifier!r}"
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


def _build_early_regular_lookup() -> Dict[str, Any]:
    lookup: Dict[str, Any] = {}
    for target_set_id in TARGET_SET_IDS:
        canonical_key = SET_ALIAS_MAP.get(target_set_id)
        if not canonical_key:
            raise RuntimeError(f"SWSH alias map missing canonical key for {target_set_id}")

        config_cls_raw = SET_CONFIG_MAP.get(canonical_key)
        if config_cls_raw is None:
            raise RuntimeError(f"SWSH set config map missing class for canonical key {canonical_key}")
        config_cls = _make_runner_compatible_config(config_cls_raw)

        keys = {
            target_set_id,
            canonical_key.lower(),
            str(getattr(config_cls, "SET_NAME", "")).strip().lower(),
        }
        for alias_key, alias_value in SET_ALIAS_MAP.items():
            if str(alias_value) == canonical_key:
                keys.add(str(alias_key).strip().lower())

        for key in keys:
            lookup[key] = (config_cls, canonical_key)

    return lookup


def _assert_runtime_contract(config_cls: type, target_set_id: str) -> Dict[str, Any]:
    config = config_cls()

    if str(getattr(config, "SET_ID", "")).strip().lower() != str(target_set_id).lower():
        raise AssertionError(
            f"Unexpected SET_ID for config {config_cls.__name__}: "
            f"expected={target_set_id!r} actual={getattr(config, 'SET_ID', None)!r}"
        )

    selected_engine = get_simulation_engine(config)
    if selected_engine != "slot_schema":
        raise AssertionError(f"Expected slot_schema engine for {target_set_id}, got {selected_engine!r}")

    if not bool(getattr(config, "SLOT_SCHEMA_RUNTIME_ENABLED", False)):
        raise AssertionError(f"SLOT_SCHEMA_RUNTIME_ENABLED must be True for {target_set_id}")

    validate_slot_schema_config(config)
    _validate_slot_schema_runtime_readiness(config)

    rare_slot_probability = getattr(config, "RARE_SLOT_PROBABILITY", None)
    reverse_slot_probabilities = getattr(config, "REVERSE_SLOT_PROBABILITIES", None)
    outcome_pool_mapping = getattr(config, "SLOT_SCHEMA_OUTCOME_POOL_MAPPING", None)

    if not isinstance(rare_slot_probability, Mapping) or not rare_slot_probability:
        raise AssertionError("RARE_SLOT_PROBABILITY must be a non-empty mapping")
    if not isinstance(reverse_slot_probabilities, Mapping) or not reverse_slot_probabilities:
        raise AssertionError("REVERSE_SLOT_PROBABILITIES must be a non-empty mapping")
    if not isinstance(outcome_pool_mapping, Mapping) or not outcome_pool_mapping:
        raise AssertionError("SLOT_SCHEMA_OUTCOME_POOL_MAPPING must be a non-empty mapping")

    return {
        "set_id": str(getattr(config, "SET_ID", "")),
        "set_name": str(getattr(config, "SET_NAME", "")),
        "simulation_engine": selected_engine,
        "slot_schema_runtime_enabled": bool(getattr(config, "SLOT_SCHEMA_RUNTIME_ENABLED", False)),
        "rare_slot_probability_keys": sorted(str(k) for k in rare_slot_probability.keys()),
        "reverse_slot_probability_keys": sorted(str(k) for k in reverse_slot_probabilities.keys()),
        "outcome_pool_mapping_keys": sorted(str(k) for k in outcome_pool_mapping.keys()),
        "monte_carlo_v2_bypassed": not _should_use_monte_carlo_v2(config),
    }


def _extract_runtime_caveats(config_cls: type) -> list[str]:
    confidence = getattr(config_cls, "SLOT_SCHEMA_SOURCE_CONFIDENCE", {}) or {}
    caveats = []
    caveat = str(confidence.get("source_caveat") or "").strip()
    if caveat:
        caveats.append(caveat)

    for attr_name in dir(config_cls):
        if not attr_name.endswith("_PULL_RATE_REFERENCE_BUCKET_EVIDENCE"):
            continue
        evidence_rows = getattr(config_cls, attr_name, None)
        if not isinstance(evidence_rows, list):
            continue
        for row in evidence_rows:
            if not isinstance(row, Mapping):
                continue
            if bool(row.get("used_in_runtime")):
                continue
            normalized_bucket = str(row.get("normalized_bucket") or "").strip()
            status = str(row.get("source_status") or "").strip()
            note = str(row.get("caveat") or "").strip()
            if normalized_bucket or status:
                caveats.append(f"{normalized_bucket or 'unknown'}: {status} ({note})")

    deduped = []
    seen = set()
    for item in caveats:
        key = item.strip().lower()
        if key and key not in seen:
            seen.add(key)
            deduped.append(item)
    return deduped


def run_swsh_early_regular_controlled_runtime_dry_run(
    *,
    json_output_path: Path = DEFAULT_JSON_PATH,
    pack_count: int = 120,
    dry_run: bool = False,
    seed: int = 17083,
) -> Dict[str, Any]:
    if not bool(dry_run):
        raise RuntimeError("Refusing to run without --dry-run. This script must run in no-write mode.")

    if int(pack_count) <= 0:
        raise ValueError("pack_count must be > 0")

    started_at = time.perf_counter()
    random.seed(int(seed))

    target_lookup = _build_early_regular_lookup()
    harness = WriteSpyHarness()
    orchestrator = evr_runner.EVRRunOrchestrator()

    per_set: Dict[str, Dict[str, Any]] = {}
    global_failures: list[str] = []

    with _early_regular_no_write_context(harness=harness, pack_count=int(pack_count), target_lookup=target_lookup):
        for set_id in TARGET_SET_IDS:
            canonical_key = SET_ALIAS_MAP.get(set_id)
            if canonical_key is None:
                raise RuntimeError(f"Missing canonical key for allowlisted set {set_id}")
            config_cls = SET_CONFIG_MAP.get(canonical_key)
            if config_cls is None:
                raise RuntimeError(f"Missing config class for canonical key {canonical_key}")

            harness.set_current_set(set_id)
            runtime_contract = _assert_runtime_contract(config_cls, set_id)

            run_result = orchestrator.run(
                target_set_identifier=set_id,
                input_source="db",
                run_metadata={
                    "trigger": "audit_swsh_early_regular_controlled_runtime_dry_run",
                    "project": "17D.2",
                    "dry_run": True,
                    "no_write": True,
                    "set_id": set_id,
                    "pack_count_override": int(pack_count),
                },
            )

            intended_counts = harness.intended_write_counts_by_set.get(set_id, {})
            intended_write_total = int(sum(int(v) for v in intended_counts.values()))
            write_tables_touched = sorted(intended_counts.keys())
            unexpected_write_tables = sorted(set(write_tables_touched) - EXPECTED_WRITE_TABLE_ALLOWLIST)

            persisted_parent = (run_result.get("persisted") or {}).get("parent") or {}
            persisted_outputs = (run_result.get("persisted") or {}).get("outputs") or {}
            persisted_inputs = (run_result.get("persisted") or {}).get("inputs") or {}
            sim_summary = harness.sim_output_summary_by_set.get(set_id, {})

            failures = []
            if harness.actual_writes_performed != 0:
                failures.append(f"actual_writes_performed must be 0, got {harness.actual_writes_performed}")
            if intended_write_total <= 0:
                failures.append("no intended writes captured; expected intercepted persistence calls")
            if unexpected_write_tables:
                failures.append(f"unexpected write tables captured: {unexpected_write_tables}")
            if runtime_contract.get("simulation_engine") != "slot_schema":
                failures.append("runtime engine was not slot_schema")
            if not runtime_contract.get("slot_schema_runtime_enabled"):
                failures.append("slot_schema runtime flag not enabled")
            if int(sim_summary.get("value_count") or 0) != int(pack_count):
                failures.append(
                    "simulation value_count mismatch "
                    f"expected={int(pack_count)} actual={int(sim_summary.get('value_count') or 0)}"
                )
            if not bool(persisted_parent.get("no_write")):
                failures.append("persisted.parent.no_write must be True")
            if not bool(persisted_outputs.get("no_write")):
                failures.append("persisted.outputs.no_write must be True")
            if not bool(persisted_inputs.get("no_write")):
                failures.append("persisted.inputs.no_write must be True")
            if run_result.get("derived") is None:
                failures.append("derived metrics missing from run result")

            per_set[set_id] = {
                "set_id": set_id,
                "canonical_key": canonical_key,
                "runtime_contract": runtime_contract,
                "input_metadata": harness.input_metadata_by_set.get(set_id, {}),
                "persistence": {
                    "actual_writes_performed_total": int(harness.actual_writes_performed),
                    "intended_writes_captured_total": intended_write_total,
                    "intended_write_counts": intended_counts,
                    "write_tables_touched": write_tables_touched,
                    "unexpected_write_tables": unexpected_write_tables,
                    "persisted_payload_flags": {
                        "parent_no_write": bool(persisted_parent.get("no_write")),
                        "inputs_no_write": bool(persisted_inputs.get("no_write")),
                        "outputs_no_write": bool(persisted_outputs.get("no_write")),
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
                "source_runtime_caveats": _extract_runtime_caveats(config_cls),
                "safety_assertions": {
                    "passed": len(failures) == 0,
                    "failures": failures,
                },
            }

            if failures:
                global_failures.extend(f"{set_id}: {failure}" for failure in failures)

    payload: Dict[str, Any] = {
        "meta": {
            "generated_at_utc": datetime.now(timezone.utc).isoformat(),
            "project": "17D.2",
            "script": "audit_swsh_early_regular_controlled_runtime_dry_run.py",
            "elapsed_seconds": time.perf_counter() - started_at,
            "dry_run_enforced": True,
        },
        "target": {
            "allowlist": sorted(TARGET_ALLOWLIST),
            "pack_count": int(pack_count),
        },
        "per_set": per_set,
        "safety_assertions": {
            "passed": len(global_failures) == 0,
            "failures": global_failures,
        },
    }

    json_output_path.parent.mkdir(parents=True, exist_ok=True)
    json_output_path.write_text(json.dumps(payload, indent=2, sort_keys=True), encoding="utf-8")
    return payload


def _build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(description="Early regular SWSH controlled runtime dry-run audit (no writes)")
    parser.add_argument("--json-output", default=str(DEFAULT_JSON_PATH), help="JSON output path")
    parser.add_argument("--pack-count", type=int, default=120, help="Bounded simulation pack count override")
    parser.add_argument("--seed", type=int, default=17083, help="Random seed")
    parser.add_argument("--dry-run", action="store_true", help="Required no-write mode")
    parser.add_argument("--stdout", action="store_true", help="Print summary JSON to stdout")
    return parser


def main() -> int:
    args = _build_parser().parse_args()

    try:
        payload = run_swsh_early_regular_controlled_runtime_dry_run(
            json_output_path=Path(args.json_output),
            pack_count=int(args.pack_count),
            dry_run=bool(args.dry_run),
            seed=int(args.seed),
        )
    except Exception as exc:
        print(f"[audit] status=failed error={type(exc).__name__}: {exc}")
        return 1

    summary = {
        "status": "passed" if payload.get("safety_assertions", {}).get("passed") else "failed",
        "allowlist": payload.get("target", {}).get("allowlist"),
        "pack_count": payload.get("target", {}).get("pack_count"),
        "failed_set_count": sum(
            1
            for row in (payload.get("per_set") or {}).values()
            if not (row.get("safety_assertions") or {}).get("passed")
        ),
        "safety_failures": payload.get("safety_assertions", {}).get("failures", []),
    }

    print(f"[audit] status={summary['status']}")
    print(f"[audit] allowlist={summary['allowlist']}")
    print(f"[audit] pack_count={summary['pack_count']} failed_set_count={summary['failed_set_count']}")

    if args.stdout:
        print(json.dumps(summary, indent=2, sort_keys=True))

    return 0 if summary["status"] == "passed" else 1


if __name__ == "__main__":
    raise SystemExit(main())
