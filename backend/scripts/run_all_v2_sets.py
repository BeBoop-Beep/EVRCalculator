from __future__ import annotations

import sys
import io

sys.stdout = io.TextIOWrapper(sys.stdout.buffer, encoding='utf-8')
sys.stderr = io.TextIOWrapper(sys.stderr.buffer, encoding='utf-8')

import argparse
import os
import time
from typing import Any

# Ensure project root is on sys.path so backend.* imports resolve when invoked
# as a script path.
_PROJECT_ROOT = os.path.abspath(os.path.join(os.path.dirname(__file__), "..", ".."))
if _PROJECT_ROOT not in sys.path:
    sys.path.insert(0, _PROJECT_ROOT)

from backend.constants.tcg.pokemon.megaEvolutionEra.setMap import (
    SET_CONFIG_MAP as MEGA_EVOLUTION_SET_CONFIG_MAP,
)
from backend.constants.tcg.pokemon.scarletAndVioletEra.setMap import (
    SET_CONFIG_MAP as SCARLET_VIOLET_SET_CONFIG_MAP,
)
from backend.jobs.evr_runner import EVRRunOrchestrator


def format_duration(seconds: float) -> str:
    total_seconds = max(0.0, float(seconds))
    minutes, remaining_seconds = divmod(total_seconds, 60)
    return f"{int(minutes):02d}:{remaining_seconds:05.2f}"


def discover_sets() -> dict:
    return {
        **SCARLET_VIOLET_SET_CONFIG_MAP,
        **MEGA_EVOLUTION_SET_CONFIG_MAP,
    }


def filter_v2_enabled_sets(
    set_map: dict,
    era: str | None = None,
    set_name: str | None = None,
) -> dict:
    filtered: dict[str, Any] = {}
    normalized_era = (era or "").strip().lower()
    normalized_set_name = (set_name or "").strip().lower()

    for set_key, config_cls in set_map.items():
        config = config_cls()

        if not bool(getattr(config, "USE_MONTE_CARLO_V2", False)):
            continue

        config_era = str(getattr(config, "ERA", "")).strip().lower()
        config_set_name = str(getattr(config, "SET_NAME", "")).strip().lower()

        if normalized_era and config_era != normalized_era:
            continue

        if normalized_set_name and normalized_set_name not in {
            str(set_key).strip().lower(),
            config_set_name,
        }:
            continue

        filtered[set_key] = config_cls

    return filtered


def run_single_set(orchestrator, set_key: str, config) -> dict:
    started_at = time.perf_counter()

    try:
        orchestrator.run(
            target_set_identifier=set_key,
            input_source="db",
            run_metadata={
                "trigger": "daily_batch",
                "era": getattr(config, "ERA", None),
                "set": getattr(config, "SET_NAME", set_key),
            },
        )
        return {
            "set": set_key,
            "success": True,
            "error": None,
            "duration": time.perf_counter() - started_at,
        }
    except Exception as exc:
        return {
            "set": set_key,
            "success": False,
            "error": str(exc),
            "duration": time.perf_counter() - started_at,
        }


def run_batch(set_map: dict) -> list:
    orchestrator = EVRRunOrchestrator()
    results: list[dict[str, Any]] = []

    for set_key, config_cls in set_map.items():
        config = config_cls()
        set_label = str(getattr(config, "SET_NAME", set_key))
        print(f"[START] {set_label}")
        print(
            "[START_TRACE] "
            f"set_key={set_key} "
            f"config_class={config_cls.__name__} "
            f"set_name={getattr(config, 'SET_NAME', None)} "
            f"set_id={getattr(config, 'SET_ID', None)} "
            f"use_monte_carlo_v2={getattr(config, 'USE_MONTE_CARLO_V2', None)}"
        )

        result = run_single_set(orchestrator, set_key, config)
        results.append(result)

        if result["success"]:
            print(f"[SUCCESS] {set_label} ({result['duration']:.2f}s)")
        else:
            print(f"[FAILED] {set_label}: {result['error']}")

    return results


def print_summary(results: list, total_runtime: float):
    if results and all(result.get("dry_run") for result in results):
        print("\n=== Batch Summary ===")
        print(f"Matched sets: {len(results)}")
        print(f"Total runtime: {format_duration(total_runtime)}")
        return

    total_sets = len(results)
    success_count = sum(1 for result in results if result.get("success"))
    failure_count = total_sets - success_count
    failed_sets = [result["set"] for result in results if not result.get("success")]

    print("\n=== Batch Summary ===")
    print(f"Total sets processed: {total_sets}")
    print(f"Successful runs: {success_count}")
    print(f"Failed runs: {failure_count}")
    print(f"Total runtime: {format_duration(total_runtime)}")

    if failed_sets:
        print("Failed sets:")
        for set_key in failed_sets:
            print(f"- {set_key}")


def _build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(
        description="Run EVR calculations and Monte Carlo V2 simulations for all eligible sets.",
    )
    parser.add_argument(
        "--era",
        help="Run only sets whose config ERA exactly matches this value.",
    )
    parser.add_argument(
        "--set",
        dest="set_name",
        help="Run only the matching canonical set key or config SET_NAME.",
    )
    parser.add_argument(
        "--dry-run",
        action="store_true",
        help="List matching V2-enabled sets without executing them.",
    )
    return parser


def main():
    args = _build_parser().parse_args()

    discovered_sets = discover_sets()
    filtered_sets = filter_v2_enabled_sets(
        discovered_sets,
        era=args.era,
        set_name=args.set_name,
    )

    if not filtered_sets:
        print("No V2-enabled sets matched the provided filters.")
        print_summary([], 0.0)
        return 0

    if args.dry_run:
        print("Dry run: matching V2-enabled sets")
        dry_run_results: list[dict[str, Any]] = []
        for set_key, config_cls in filtered_sets.items():
            config = config_cls()
            print(
                f"- {set_key} | {getattr(config, 'SET_NAME', set_key)} | "
                f"{getattr(config, 'ERA', 'Unknown Era')}"
            )
            dry_run_results.append({"set": set_key, "dry_run": True})
        print_summary(dry_run_results, 0.0)
        return 0

    batch_started_at = time.perf_counter()
    results = run_batch(filtered_sets)
    total_runtime = time.perf_counter() - batch_started_at
    print_summary(results, total_runtime)
    return 0 if all(result.get("success") for result in results) else 1


if __name__ == "__main__":
    raise SystemExit(main())