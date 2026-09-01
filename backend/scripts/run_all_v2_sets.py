from __future__ import annotations

import sys
for _stream in (sys.stdout, sys.stderr):
    _reconfigure = getattr(_stream, "reconfigure", None)
    if callable(_reconfigure):
        _reconfigure(encoding="utf-8")

import argparse
import json
import os
import socket
import time
import urllib.request
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
SLACK_WEBHOOK_URL = os.getenv("SLACK_WEBHOOK_URL", "").strip()


def notify_slack(message: str) -> None:
    if not SLACK_WEBHOOK_URL:
        return

    payload = json.dumps({"text": message}, ensure_ascii=False).encode("utf-8")
    request = urllib.request.Request(
        SLACK_WEBHOOK_URL,
        data=payload,
        headers={"Content-Type": "application/json; charset=utf-8"},
        method="POST",
    )

    try:
        with urllib.request.urlopen(request, timeout=5):
            return
    except Exception as exc:
        print(f"[SLACK_NOTIFY_FAILED] {exc}")


def format_duration(seconds: float) -> str:
    total_seconds = max(0.0, float(seconds))
    minutes, remaining_seconds = divmod(total_seconds, 60)
    return f"{int(minutes):02d}:{remaining_seconds:05.2f}"


def format_progress(current: int, total: int) -> str:
    safe_total = max(total, 1)
    percent = (float(current) / float(safe_total)) * 100.0
    return f"{current}/{total} ({percent:.1f}%)"


def format_eta(completed_durations: list[float], total_sets: int, completed_sets: int) -> str:
    remaining = max(total_sets - completed_sets, 0)
    if remaining == 0:
        return "0.00s"
    if not completed_durations:
        return "estimating..."
    average_duration = sum(completed_durations) / len(completed_durations)
    return f"{remaining * average_duration:.2f}s"


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


# Queue-level cooldown after a set fails for INFRASTRUCTURE reasons.
#
# Per-operation retries (backend.db.services.supabase_persistence_retry) absorb
# the ordinary blip and are the primary defence; this is the second line, for the
# outage that outlives them. Without it, a Supabase edge failure lasting a minute
# would be re-hit immediately by every remaining set and burn the whole queue in
# seconds - the exact behaviour observed on the failing batch.
#
# Only CONSECUTIVE transient failures escalate, and a single success resets the
# ladder: this must not slow down a queue whose sets are failing for their own
# individual, deterministic reasons.
TRANSIENT_SET_FAILURE_COOLDOWN_SECONDS = (30.0, 60.0, 120.0)


def _cooldown_seconds_for_consecutive_transient_failures(count: int) -> float:
    if count <= 0:
        return 0.0
    index = min(count, len(TRANSIENT_SET_FAILURE_COOLDOWN_SECONDS)) - 1
    return TRANSIENT_SET_FAILURE_COOLDOWN_SECONDS[index]


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
                "market_date": getattr(orchestrator, "_publication_market_date", None),
            },
        )
        return {
            "set": set_key,
            "success": True,
            "error": None,
            "transient": False,
            "duration": time.perf_counter() - started_at,
        }
    except Exception as exc:
        # Imported lazily so `--dry-run` and `--help` keep working without a
        # configured Supabase environment.
        from backend.db.services.data_service_health import classify_data_service_error

        return {
            "set": set_key,
            "success": False,
            "error": str(exc),
            "transient": bool(classify_data_service_error(exc).transient),
            "duration": time.perf_counter() - started_at,
        }


def run_batch(set_map: dict, *, sleep=time.sleep, market_date: str | None = None) -> list:
    from backend.jobs.evr_runner import EVRRunOrchestrator
    orchestrator = EVRRunOrchestrator()
    orchestrator._publication_market_date = market_date
    results: list[dict[str, Any]] = []
    completed_durations: list[float] = []
    total_sets = len(set_map)
    host = socket.gethostname()
    consecutive_transient_failures = 0

    for current_index, (set_key, config_cls) in enumerate(set_map.items(), start=1):
        cooldown = _cooldown_seconds_for_consecutive_transient_failures(
            consecutive_transient_failures
        )
        if cooldown > 0:
            print(
                "[QUEUE_COOLDOWN] "
                f"consecutive_transient_failures={consecutive_transient_failures} "
                f"sleeping={cooldown:.0f}s before next_set={set_key}"
            )
            sleep(cooldown)

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
        notify_slack(
            "\n".join(
                [
                    "🚀 Simulation set started",
                    f"Host: {host}",
                    f"Set: {set_key}",
                    f"Progress: {format_progress(current_index, total_sets)}",
                ]
            )
        )

        result = run_single_set(orchestrator, set_key, config)
        if result.get("success"):
            consecutive_transient_failures = 0
        elif result.get("transient"):
            consecutive_transient_failures += 1
        else:
            # A deterministic set failure says nothing about the infrastructure,
            # so it must not slow the queue down for the sets behind it.
            consecutive_transient_failures = 0
        results.append(result)
        completed_durations.append(float(result.get("duration", 0.0)))

        completed_count = len(results)
        failed_count = sum(1 for item in results if not item.get("success"))
        remaining_count = max(total_sets - completed_count, 0)
        progress = format_progress(completed_count, total_sets)
        eta = format_eta(completed_durations, total_sets, completed_count)
        elapsed = float(result.get("duration", 0.0))

        if result["success"]:
            print(f"[SUCCESS] {set_label} ({result['duration']:.2f}s)")
            notify_slack(
                "\n".join(
                    [
                        "✅ Simulation set completed",
                        f"Host: {host}",
                        f"Set: {set_key}",
                        f"Elapsed: {elapsed:.2f}s",
                        f"Progress: {progress}",
                        f"Queue: {remaining_count} pending, {failed_count} failed",
                        f"ETA: {eta}",
                    ]
                )
            )
        else:
            print(f"[FAILED] {set_label}: {result['error']}")
            notify_slack(
                "\n".join(
                    [
                        "❌ Simulation set failed",
                        f"Host: {host}",
                        f"Set: {set_key}",
                        f"Elapsed: {elapsed:.2f}s",
                        f"Error: {result.get('error', 'unknown error')}",
                        f"Progress: {progress}",
                        f"Queue: {remaining_count} pending, {failed_count} failed",
                        f"ETA: {eta}",
                    ]
                )
            )

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
        "--market-date",
        default=None,
        help="Canonical promoted market date persisted on every calculation run.",
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
    parser.add_argument(
        "--json", action="store_true",
        help="Emit a final SIMULATION_JSON machine-readable summary.",
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
    matched_sets = [
        {
            "canonical_key": set_key,
            "set_name": str(getattr(config_cls(), "SET_NAME", set_key)),
            "use_monte_carlo_v2": bool(getattr(config_cls(), "USE_MONTE_CARLO_V2", False)),
            "pull_model_status": str(getattr(config_cls(), "PULL_MODEL_STATUS", "unknown")),
        }
        for set_key, config_cls in filtered_sets.items()
    ]

    def emit_json(results=None):
        if args.json:
            print("SIMULATION_JSON=" + json.dumps({
                "matched_set_count": len(matched_sets),
                "matched_sets": matched_sets,
                "results": results or [],
            }, sort_keys=True))

    if not filtered_sets:
        print("No V2-enabled sets matched the provided filters.")
        print_summary([], 0.0)
        emit_json([])
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
        emit_json(dry_run_results)
        return 0

    batch_started_at = time.perf_counter()
    results = run_batch(filtered_sets, market_date=args.market_date)
    total_runtime = time.perf_counter() - batch_started_at
    print_summary(results, total_runtime)
    emit_json(results)
    if all(result.get("success") for result in results):
        return 0
    # A one-set invocation uses this distinct code to let the outer daily
    # coordinator retry infrastructure failures without guessing from prose.
    if results and all(result.get("transient") for result in results if not result.get("success")):
        return 75
    return 1


if __name__ == "__main__":
    raise SystemExit(main())
