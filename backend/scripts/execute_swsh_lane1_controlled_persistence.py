"""Project 17C.3 regular SWSH Lane 1 controlled persistence execute.

Targets are fixed to:
- swsh5 (Battle Styles)
- swsh9 (Brilliant Stars)
- swsh10 (Astral Radiance)
- swsh11 (Lost Origin)
- swsh12 (Silver Tempest)

Safety behavior:
- strict allowlist scope
- target identity lock against expected UUIDs
- optional dry-run mode (delegates to Lane 1 no-write runtime audit)
- execute mode uses production runner persistence path
- bounded pack-count override for controlled execution
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
from backend.db.clients.supabase_client import public_read_client


DEFAULT_JSON_PATH = Path("logs/audits/swsh_lane1_controlled_persistence_execute.json")

TARGET_SET_IDS = ("swsh5", "swsh9", "swsh10", "swsh11", "swsh12")
TARGET_ALLOWLIST = set(TARGET_SET_IDS)

EXECUTE_CONFIRMATION_TOKEN = "swsh-lane1-controlled-persistence-execute"

EXPECTED_TARGET_UUID_BY_SET_ID = {
    "swsh5": "46ab39a7-dd96-4a2d-af0f-44b868918114",
    "swsh9": "a72c75bd-0d61-4643-b603-fef78425dcfa",
    "swsh10": "0d90b4ed-16a1-456c-81c6-83d2869d3846",
    "swsh11": "5109f22e-0799-46b5-a4ad-8861d1cfefee",
    "swsh12": "2d6ec108-70b2-4698-a21a-1af39828004f",
}


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


def _first_row(result: Any) -> Optional[Dict[str, Any]]:
    if result and result.data and len(result.data) > 0:
        return dict(result.data[0])
    return None


def _normalize_key(value: Any) -> str:
    return str(value or "").strip().lower()


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


def _resolve_target_set_row(set_id: str) -> Dict[str, Any]:
    expected_uuid = EXPECTED_TARGET_UUID_BY_SET_ID[set_id]
    result = (
        public_read_client.table("sets")
        .select("id,name,canonical_key,pokemon_api_set_id")
        .eq("pokemon_api_set_id", set_id)
        .limit(1)
        .execute()
    )
    row = _first_row(result)

    canonical_key = SET_ALIAS_MAP.get(set_id)
    return {
        "set_id": set_id,
        "canonical_key": canonical_key,
        "expected_target_id": expected_uuid,
        "resolved": row is not None,
        "resolved_target_id": row.get("id") if row else None,
        "resolved_set_name": row.get("name") if row else None,
        "resolved_canonical_key": row.get("canonical_key") if row else None,
        "resolved_pokemon_api_set_id": row.get("pokemon_api_set_id") if row else None,
        "matches_expected_target_id": bool(row and str(row.get("id")) == expected_uuid),
        "matches_set_id": bool(row and _normalize_key(row.get("pokemon_api_set_id")) == _normalize_key(set_id)),
    }


def _build_lane1_lookup() -> Dict[str, Any]:
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


@contextmanager
def _lane1_controlled_execute_context(*, pack_count: int, target_lookup: Dict[str, Any]):
    if int(pack_count) <= 0:
        raise ValueError("pack_count must be > 0")

    original_resolve_set_config = evr_runner._resolve_set_config
    original_persist_outputs = evr_runner.persist_simulation_outputs
    original_run_simulation = evr_simulator.run_simulation
    original_run_simulation_v2 = evr_simulator.run_simulation_v2
    original_simulate_slot_schema_packs = evr_simulator.simulate_slot_schema_packs

    def _resolve_set_config_override(target_set_identifier: str) -> tuple[Any, str]:
        key = str(target_set_identifier or "").strip().lower()
        if key in target_lookup:
            return target_lookup[key]
        raise RuntimeError(
            "Controlled execute scope violation: target is outside Lane 1 allowlist "
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
        evr_runner.persist_simulation_outputs = _persist_simulation_outputs_wrapper
        evr_simulator.run_simulation = _run_simulation_override
        evr_simulator.run_simulation_v2 = _run_simulation_v2_override
        evr_simulator.simulate_slot_schema_packs = _simulate_slot_schema_packs_override
        yield
    finally:
        evr_runner._resolve_set_config = original_resolve_set_config
        evr_runner.persist_simulation_outputs = original_persist_outputs
        evr_simulator.run_simulation = original_run_simulation
        evr_simulator.run_simulation_v2 = original_run_simulation_v2
        evr_simulator.simulate_slot_schema_packs = original_simulate_slot_schema_packs


def run_swsh_lane1_controlled_persistence_execute(
    *,
    json_output_path: Path = DEFAULT_JSON_PATH,
    pack_count: int = 1000,
    execute: bool = False,
    dry_run: bool = False,
    confirm_token: Optional[str] = None,
    seed: int = 17390,
) -> Dict[str, Any]:
    if dry_run and execute:
        raise RuntimeError("Choose exactly one mode: --dry-run or --execute")
    if not dry_run and not execute:
        raise RuntimeError("One mode is required: --dry-run or --execute")

    if execute and str(confirm_token or "") != EXECUTE_CONFIRMATION_TOKEN:
        raise RuntimeError(
            "Execute mode requires valid confirmation token. "
            "Use --confirm-token with the approved value."
        )

    from backend.scripts.audit_swsh_lane1_controlled_runtime_dry_run import (
        run_swsh_lane1_controlled_runtime_dry_run,
    )

    started_at = time.perf_counter()
    random.seed(int(seed))

    if dry_run:
        payload = run_swsh_lane1_controlled_runtime_dry_run(
            json_output_path=json_output_path,
            pack_count=int(pack_count),
            dry_run=True,
            seed=int(seed),
        )
        payload.setdefault("meta", {})
        payload["meta"].update(
            {
                "script": "execute_swsh_lane1_controlled_persistence.py",
                "mode": "dry_run_delegate",
            }
        )
        return payload

    target_lookup = _build_lane1_lookup()
    orchestrator = evr_runner.EVRRunOrchestrator()

    per_set: Dict[str, Dict[str, Any]] = {}
    failures: list[str] = []

    with _lane1_controlled_execute_context(pack_count=int(pack_count), target_lookup=target_lookup):
        for set_id in TARGET_SET_IDS:
            identity = _resolve_target_set_row(set_id)
            canonical_key = identity.get("canonical_key")
            set_name = identity.get("resolved_set_name")
            expected_target_id = identity.get("expected_target_id")

            if not identity.get("resolved"):
                reason = "target identity not resolved in sets table"
                failures.append(f"{set_id}: {reason}")
                per_set[set_id] = {
                    "set_id": set_id,
                    "set_name": set_name,
                    "canonical_key": canonical_key,
                    "target_uuid": expected_target_id,
                    "identity": identity,
                    "pack_count": int(pack_count),
                    "run_id": None,
                    "calculation_config_id": None,
                    "persisted_result": {},
                    "status": "failed",
                    "error_message": reason,
                }
                continue

            if not identity.get("matches_expected_target_id") or not identity.get("matches_set_id"):
                reason = "target identity mismatch against locked UUID or set_id"
                failures.append(f"{set_id}: {reason}")
                per_set[set_id] = {
                    "set_id": set_id,
                    "set_name": set_name,
                    "canonical_key": canonical_key,
                    "target_uuid": expected_target_id,
                    "identity": identity,
                    "pack_count": int(pack_count),
                    "run_id": None,
                    "calculation_config_id": None,
                    "persisted_result": {},
                    "status": "failed",
                    "error_message": reason,
                }
                continue

            try:
                run_result = orchestrator.run(
                    target_set_identifier=set_id,
                    input_source="db",
                    run_metadata={
                        "trigger": "execute_swsh_lane1_controlled_persistence",
                        "execute": True,
                        "dry_run": False,
                        "set_id": set_id,
                        "pack_count_override": int(pack_count),
                    },
                )
            except Exception as exc:
                failures.append(f"{set_id}: {type(exc).__name__}: {exc}")
                per_set[set_id] = {
                    "set_id": set_id,
                    "set_name": set_name,
                    "canonical_key": canonical_key,
                    "target_uuid": expected_target_id,
                    "identity": identity,
                    "pack_count": int(pack_count),
                    "run_id": None,
                    "calculation_config_id": None,
                    "persisted_result": {},
                    "status": "failed",
                    "error_message": f"{type(exc).__name__}: {exc}",
                }
                continue

            persisted = (run_result.get("persisted") or {}) if isinstance(run_result, Mapping) else {}
            parent = (persisted.get("parent") or {}) if isinstance(persisted, Mapping) else {}
            inputs = (persisted.get("inputs") or {}) if isinstance(persisted, Mapping) else {}
            outputs = (persisted.get("outputs") or {}) if isinstance(persisted, Mapping) else {}
            etb_summary = (persisted.get("etb_summary") or {}) if isinstance(persisted, Mapping) else {}

            per_set[set_id] = {
                "set_id": set_id,
                "set_name": set_name,
                "canonical_key": canonical_key,
                "target_uuid": expected_target_id,
                "identity": identity,
                "pack_count": int(pack_count),
                "run_id": parent.get("run_id") or parent.get("id"),
                "calculation_config_id": parent.get("config_id") or parent.get("calculation_config_id"),
                "persisted_result": {
                    "parent": parent,
                    "inputs": inputs,
                    "outputs": outputs,
                    "etb_summary": etb_summary,
                },
                "status": "passed",
                "error_message": None,
            }

    payload: Dict[str, Any] = {
        "meta": {
            "generated_at_utc": datetime.now(timezone.utc).isoformat(),
            "project": "17C.3",
            "script": "execute_swsh_lane1_controlled_persistence.py",
            "mode": "execute",
            "elapsed_seconds": time.perf_counter() - started_at,
        },
        "target": {
            "allowlist": list(TARGET_SET_IDS),
            "pack_count": int(pack_count),
            "expected_target_uuid_by_set_id": dict(EXPECTED_TARGET_UUID_BY_SET_ID),
        },
        "execute_guardrails": {
            "execute_flag_required": True,
            "confirmation_token_required": True,
            "confirmation_token_value": EXECUTE_CONFIRMATION_TOKEN,
            "bounded_pack_count_override_applied": True,
            "strict_allowlist_scope": list(TARGET_SET_IDS),
        },
        "per_set": per_set,
        "safety_assertions": {
            "passed": len(failures) == 0,
            "failures": failures,
        },
    }

    json_output_path.parent.mkdir(parents=True, exist_ok=True)
    json_output_path.write_text(json.dumps(payload, indent=2, sort_keys=True), encoding="utf-8")
    return payload


def _build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(description="Lane 1 regular SWSH controlled persistence execute")
    parser.add_argument("--json-output", default=str(DEFAULT_JSON_PATH), help="JSON output path")
    parser.add_argument("--pack-count", type=int, default=1000, help="Bounded simulation pack count override")
    parser.add_argument("--seed", type=int, default=17390, help="Random seed")
    parser.add_argument("--dry-run", action="store_true", help="No-write controlled dry-run mode")
    parser.add_argument("--execute", action="store_true", help="Write-enabled controlled execute mode")
    parser.add_argument("--confirm-token", default=None, help="Confirmation token required for execute mode")
    parser.add_argument("--stdout", action="store_true", help="Print compact JSON summary")
    return parser


def main() -> int:
    args = _build_parser().parse_args()

    try:
        payload = run_swsh_lane1_controlled_persistence_execute(
            json_output_path=Path(args.json_output),
            pack_count=int(args.pack_count),
            execute=bool(args.execute),
            dry_run=bool(args.dry_run),
            confirm_token=args.confirm_token,
            seed=int(args.seed),
        )
    except Exception as exc:
        print(f"[execute] status=failed error={type(exc).__name__}: {exc}")
        return 1

    failed_set_count = sum(
        1
        for row in (payload.get("per_set") or {}).values()
        if str((row or {}).get("status") or "").lower() != "passed"
    )

    summary = {
        "status": "passed" if payload.get("safety_assertions", {}).get("passed") else "failed",
        "mode": payload.get("meta", {}).get("mode"),
        "allowlist": payload.get("target", {}).get("allowlist"),
        "pack_count": payload.get("target", {}).get("pack_count"),
        "failed_set_count": failed_set_count,
        "safety_failures": payload.get("safety_assertions", {}).get("failures", []),
    }

    print(f"[execute] status={summary['status']} mode={summary['mode']}")
    print(f"[execute] allowlist={summary['allowlist']} pack_count={summary['pack_count']}")
    print(f"[execute] failed_set_count={summary['failed_set_count']}")

    if args.stdout:
        print(json.dumps(summary, indent=2, sort_keys=True))

    return 0 if summary["status"] == "passed" else 1


if __name__ == "__main__":
    raise SystemExit(main())
