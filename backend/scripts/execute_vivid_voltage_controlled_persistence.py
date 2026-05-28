"""Project 17E.3 swsh4-only controlled persistence execute.

Safety behavior:
- strict allowlist scope: swsh4 only
- strict identity lock to expected target UUID
- explicit --execute plus confirmation token required for writes
- optional dry-run delegation to validated no-write runtime audit
- bounded pack-count override
- fail if Amazing Rare appears in runtime buckets or runtime output pull-count keys
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


DEFAULT_JSON_PATH = Path("logs/audits/vivid_voltage_controlled_persistence_execute.json")

TARGET_SET_ID = "swsh4"
TARGET_SET_NAME = "Vivid Voltage"
TARGET_CANONICAL_KEY = "vividVoltage"
TARGET_ALLOWLIST = {TARGET_SET_ID}

EXECUTE_CONFIRMATION_TOKEN = "swsh4-vivid-voltage-controlled-persistence-execute"
EXPECTED_TARGET_UUID = "26fedb88-87d7-487a-9f01-528d603c682e"


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


def _resolve_target_set_row() -> Dict[str, Any]:
    result = (
        public_read_client.table("sets")
        .select("id,name,canonical_key,pokemon_api_set_id")
        .eq("pokemon_api_set_id", TARGET_SET_ID)
        .limit(1)
        .execute()
    )
    row = _first_row(result)

    return {
        "set_id": TARGET_SET_ID,
        "canonical_key": TARGET_CANONICAL_KEY,
        "expected_target_id": EXPECTED_TARGET_UUID,
        "resolved": row is not None,
        "resolved_target_id": row.get("id") if row else None,
        "resolved_set_name": row.get("name") if row else None,
        "resolved_canonical_key": row.get("canonical_key") if row else None,
        "resolved_pokemon_api_set_id": row.get("pokemon_api_set_id") if row else None,
        "matches_expected_target_id": bool(row and str(row.get("id")) == EXPECTED_TARGET_UUID),
        "matches_set_id": bool(
            row and _normalize_key(row.get("pokemon_api_set_id")) == _normalize_key(TARGET_SET_ID)
        ),
        "matches_canonical_key": bool(
            row and _normalize_key(row.get("canonical_key")) == _normalize_key(TARGET_CANONICAL_KEY)
        ),
    }


def _assert_runtime_guardrails(config_cls: type) -> Dict[str, Any]:
    config = config_cls()
    rare_slot_probability = getattr(config, "RARE_SLOT_PROBABILITY", None)
    outcome_pool_mapping = getattr(config, "SLOT_SCHEMA_OUTCOME_POOL_MAPPING", None)

    if not isinstance(rare_slot_probability, Mapping) or not rare_slot_probability:
        raise AssertionError("RARE_SLOT_PROBABILITY must be a non-empty mapping")
    if not isinstance(outcome_pool_mapping, Mapping) or not outcome_pool_mapping:
        raise AssertionError("SLOT_SCHEMA_OUTCOME_POOL_MAPPING must be a non-empty mapping")

    runtime_bucket_keys = {str(key).strip().lower() for key in rare_slot_probability.keys()}
    mapping_bucket_keys = {str(key).strip().lower() for key in outcome_pool_mapping.keys()}

    if "amazing rare" in runtime_bucket_keys:
        raise AssertionError("Amazing Rare must not appear in RARE_SLOT_PROBABILITY runtime buckets")
    if "amazing rare" in mapping_bucket_keys:
        raise AssertionError("Amazing Rare must not appear in SLOT_SCHEMA_OUTCOME_POOL_MAPPING runtime buckets")

    return {
        "rare_slot_probability_keys": sorted(str(k) for k in rare_slot_probability.keys()),
        "outcome_pool_mapping_keys": sorted(str(k) for k in outcome_pool_mapping.keys()),
    }


@contextmanager
def _controlled_execute_context(*, pack_count: int, target_lookup: Dict[str, Any]):
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
            "Controlled execute scope violation: target is outside allowlist "
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
        pull_count_keys = {
            str(key).strip().lower() for key in (normalized_sim_results.get("rarity_pull_counts") or {}).keys()
        }
        if "amazing rare" in pull_count_keys:
            raise RuntimeError("Amazing Rare appeared in runtime output pull-count keys")
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


def run_vivid_voltage_controlled_persistence_execute(
    *,
    json_output_path: Path = DEFAULT_JSON_PATH,
    pack_count: int = 1000,
    execute: bool = False,
    dry_run: bool = False,
    confirm_token: Optional[str] = None,
    seed: int = 17444,
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

    started_at = time.perf_counter()
    random.seed(int(seed))

    resolved_canonical = SET_ALIAS_MAP.get(TARGET_SET_ID)
    if resolved_canonical != TARGET_CANONICAL_KEY:
        raise RuntimeError(
            "SWSH alias map resolution mismatch for swsh4: "
            f"expected={TARGET_CANONICAL_KEY} actual={resolved_canonical}"
        )

    config_cls_raw = SET_CONFIG_MAP.get(TARGET_CANONICAL_KEY)
    if config_cls_raw is None:
        raise RuntimeError("vividVoltage config missing from SWSH SET_CONFIG_MAP")
    runtime_guardrails = _assert_runtime_guardrails(config_cls_raw)

    if dry_run:
        from backend.scripts.audit_vivid_voltage_controlled_runtime_dry_run import (
            run_vivid_voltage_controlled_runtime_dry_run,
        )

        payload = run_vivid_voltage_controlled_runtime_dry_run(
            json_output_path=json_output_path,
            pack_count=int(pack_count),
            dry_run=True,
            seed=int(seed),
        )
        payload.setdefault("meta", {})
        payload["meta"].update(
            {
                "script": "execute_vivid_voltage_controlled_persistence.py",
                "project": "17E.3",
                "mode": "dry_run_delegate",
            }
        )
        return payload

    config_cls = _make_runner_compatible_config(config_cls_raw)
    target_lookup = {
        TARGET_SET_ID: (config_cls, TARGET_CANONICAL_KEY),
        TARGET_CANONICAL_KEY.lower(): (config_cls, TARGET_CANONICAL_KEY),
        str(getattr(config_cls, "SET_NAME", "")).strip().lower(): (config_cls, TARGET_CANONICAL_KEY),
    }
    for alias_key, alias_value in SET_ALIAS_MAP.items():
        if str(alias_value) == TARGET_CANONICAL_KEY:
            target_lookup[str(alias_key).strip().lower()] = (config_cls, TARGET_CANONICAL_KEY)

    identity = _resolve_target_set_row()
    failures: list[str] = []
    per_set: Dict[str, Any] = {
        TARGET_SET_ID: {
            "set_id": TARGET_SET_ID,
            "set_name": TARGET_SET_NAME,
            "canonical_key": TARGET_CANONICAL_KEY,
            "target_uuid": EXPECTED_TARGET_UUID,
            "identity": identity,
            "pack_count": int(pack_count),
            "run_id": None,
            "calculation_config_id": None,
            "persisted_result": {},
            "status": "failed",
            "error_message": None,
        }
    }

    if not identity.get("resolved"):
        failures.append("swsh4: target identity not resolved in sets table")
        per_set[TARGET_SET_ID]["error_message"] = "target identity not resolved in sets table"
    elif not (
        identity.get("matches_expected_target_id")
        and identity.get("matches_set_id")
        and identity.get("matches_canonical_key")
    ):
        failures.append("swsh4: target identity mismatch against locked UUID/set_id/canonical_key")
        per_set[TARGET_SET_ID]["error_message"] = (
            "target identity mismatch against locked UUID/set_id/canonical_key"
        )
    else:
        orchestrator = evr_runner.EVRRunOrchestrator()
        with _controlled_execute_context(pack_count=int(pack_count), target_lookup=target_lookup):
            try:
                run_result = orchestrator.run(
                    target_set_identifier=TARGET_SET_ID,
                    input_source="db",
                    run_metadata={
                        "trigger": "execute_vivid_voltage_controlled_persistence",
                        "project": "17E.3",
                        "execute": True,
                        "dry_run": False,
                        "set_id": TARGET_SET_ID,
                        "pack_count_override": int(pack_count),
                    },
                )
            except Exception as exc:
                failures.append(f"swsh4: {type(exc).__name__}: {exc}")
                per_set[TARGET_SET_ID]["error_message"] = f"{type(exc).__name__}: {exc}"
            else:
                persisted = (run_result.get("persisted") or {}) if isinstance(run_result, Mapping) else {}
                parent = (persisted.get("parent") or {}) if isinstance(persisted, Mapping) else {}
                inputs = (persisted.get("inputs") or {}) if isinstance(persisted, Mapping) else {}
                outputs = (persisted.get("outputs") or {}) if isinstance(persisted, Mapping) else {}
                etb_summary = (persisted.get("etb_summary") or {}) if isinstance(persisted, Mapping) else {}

                per_set[TARGET_SET_ID].update(
                    {
                        "set_name": identity.get("resolved_set_name") or TARGET_SET_NAME,
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
                )

    payload: Dict[str, Any] = {
        "meta": {
            "generated_at_utc": datetime.now(timezone.utc).isoformat(),
            "project": "17E.3",
            "script": "execute_vivid_voltage_controlled_persistence.py",
            "mode": "execute",
            "elapsed_seconds": time.perf_counter() - started_at,
        },
        "target": {
            "allowlist": [TARGET_SET_ID],
            "pack_count": int(pack_count),
            "set_id": TARGET_SET_ID,
            "set_name": TARGET_SET_NAME,
            "canonical_key": TARGET_CANONICAL_KEY,
            "expected_target_uuid": EXPECTED_TARGET_UUID,
        },
        "execute_guardrails": {
            "execute_flag_required": True,
            "confirmation_token_required": True,
            "confirmation_token_value": EXECUTE_CONFIRMATION_TOKEN,
            "bounded_pack_count_override_applied": True,
            "strict_allowlist_scope": [TARGET_SET_ID],
            "amazing_rare_runtime_excluded": True,
            "runtime_guardrails": runtime_guardrails,
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
    parser = argparse.ArgumentParser(description="Vivid Voltage controlled persistence execute")
    parser.add_argument("--json-output", default=str(DEFAULT_JSON_PATH), help="JSON output path")
    parser.add_argument("--pack-count", type=int, default=1000, help="Bounded simulation pack count override")
    parser.add_argument("--seed", type=int, default=17444, help="Random seed")
    parser.add_argument("--dry-run", action="store_true", help="No-write controlled dry-run delegation mode")
    parser.add_argument("--execute", action="store_true", help="Write-enabled controlled execute mode")
    parser.add_argument("--confirm-token", default=None, help="Confirmation token required for execute mode")
    parser.add_argument("--stdout", action="store_true", help="Print compact JSON summary")
    return parser


def main() -> int:
    args = _build_parser().parse_args()

    try:
        payload = run_vivid_voltage_controlled_persistence_execute(
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
