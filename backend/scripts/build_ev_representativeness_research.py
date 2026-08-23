"""Build the EV Representativeness research layer for one market date.

    python -m backend.scripts.build_ev_representativeness_research \
        --market-date 2026-08-22 [--set <canonical_key> ...] \
        [--with-research-resimulation] [--dry-run] [--export DIR]

DEFAULT IS TIER A ONLY. Tier A reads the exact persisted million-pack artifact
for each authoritative run and is fast (measured ~1.1 s to load an artifact and
~3.5 s for a full N-grid at 50,000 sessions).

``--with-research-resimulation`` additionally re-runs the simulator per set with
a seed and per-card instrumentation, which is what Parts 6, 7, 9, 10, 18 and 19
require and which costs roughly a minute per set. It is off by default because
nothing on the daily path should pay for it.

FAILURE POSTURE (Part 37)
-------------------------
Per-set failures are isolated: one set that cannot be analysed does not abort the
cohort, and the exit code distinguishes "nothing built" from "some sets failed".
This job never mutates simulation state, never writes a market price, and is
never a dependency of publication.
"""

from __future__ import annotations

import argparse
import json
import logging
import math
import sys
import time
from pathlib import Path
from typing import Any, Dict, List, Optional, Sequence

REPO_ROOT = Path(__file__).resolve().parents[2]
if str(REPO_ROOT) not in sys.path:
    sys.path.insert(0, str(REPO_ROOT))

import numpy as np

from backend.db.clients.supabase_client import create_service_role_client
from backend.db.services.ev_representativeness_service import (
    STATUS_BUILT,
    STATUS_FAILED,
    STATUS_PARTIAL,
    TAG,
    EvRepresentativenessError,
    analyse_tier_a,
    persist_research,
    reconcile_tiers,
    resolve_research_cohort,
)
from backend.research.ev_representativeness.version import (
    EV_REPRESENTATIVENESS_VERSION,
    TIER_B_PACK_COUNT,
)

logger = logging.getLogger("ev_representativeness")

EXIT_OK = 0
EXIT_PARTIAL = 2
EXIT_FAILED = 1


def _resolve_market_date(client: Any, requested: Optional[str]) -> str:
    """The coordinated market date, never wall-clock.

    Mirrors the daily orchestrator: an explicit date is honoured so a read-only
    research pass can target any historical day, otherwise the most recent
    promoted complete batch is used.
    """
    if requested:
        return str(requested)[:10]
    rows = (
        client.table("pokemon_scrape_batches")
        .select("market_date,status,promoted_at")
        .eq("status", "complete")
        .not_.is_("promoted_at", "null")
        .order("market_date", desc=True)
        .limit(1)
        .execute()
    )
    data = rows.data if rows else []
    if not data:
        raise EvRepresentativenessError("no promoted complete market date could be resolved")
    return str(data[0]["market_date"])[:10]


def _tier_b_for(client: Any, target: Any, tier_a_outcomes: np.ndarray, pack_count: int) -> Dict[str, Any]:
    """Prepare the exact same inputs the authoritative run used, then re-simulate.

    The set config and the prepared input frame are rebuilt through the SAME
    services the production run uses (``_resolve_set_config`` and
    ``EVRInputPreparationService``), so Tier B is not a second opinion about what
    the inputs were.
    """
    from backend.db.services.evr_input_preparation_service import EVRInputPreparationService
    from backend.jobs.evr_runner import _resolve_set_config
    from backend.research.ev_representativeness.tier_b import run_tier_b

    config_cls, canonical_key = _resolve_set_config(target.canonical_key)
    config = config_cls()
    prepared = EVRInputPreparationService().prepare_for_set(
        config, canonical_key, str(getattr(config, "SET_NAME", canonical_key))
    )
    return run_tier_b(
        config=config,
        calculation_input=prepared["dataframe"],
        calculation_run_id=target.calculation_run_id,
        canonical_key=target.canonical_key,
        pack_cost=target.pack_cost,
        tier_a_outcomes=tier_a_outcomes,
        pack_count=pack_count,
        reconciler=reconcile_tiers,
    )


def build(
    client: Any,
    *,
    market_date: Optional[str] = None,
    canonical_keys: Optional[Sequence[str]] = None,
    with_resimulation: bool = False,
    tier_b_pack_count: int = TIER_B_PACK_COUNT,
    dry_run: bool = False,
    export_dir: Optional[Path] = None,
) -> Dict[str, Any]:
    day = _resolve_market_date(client, market_date)
    targets = resolve_research_cohort(client, market_date=day, canonical_keys=canonical_keys)
    print(f"{TAG} market_date={day} version={EV_REPRESENTATIVENESS_VERSION} cohort={len(targets)}")

    built: List[Dict[str, Any]] = []
    failures: List[Dict[str, Any]] = []
    exports: List[Dict[str, Any]] = []
    started = time.perf_counter()

    for index, target in enumerate(targets, start=1):
        set_started = time.perf_counter()
        try:
            result = analyse_tier_a(client, target)
            tier_b = None
            if with_resimulation:
                tier_b = _tier_b_for(client, target, result.outcomes, tier_b_pack_count)

            if not dry_run:
                written = persist_research(client, result, tier_b=tier_b)
            else:
                written = {"dry_run": True}

            baseline = result.baseline
            confirmed = result.diagnostics.get("confirmedHorizons", {})
            record = {
                "canonicalKey": target.canonical_key,
                "setName": target.set_name,
                "calculationRunId": target.calculation_run_id,
                "marketDate": day,
                "packCost": target.pack_cost,
                "ev": baseline.ev,
                "p50": baseline.p50,
                "typicalCapture": baseline.typical_capture,
                "evTypicalGapAbsolute": baseline.ev_typical_gap_absolute,
                "evTypicalGapCostNormalized": baseline.ev_typical_gap_cost_normalized,
                "coefficientOfVariation": baseline.coefficient_of_variation,
                "groeneveldMeedenSkew": baseline.groeneveld_meeden_skew,
                "pearsonSkew2": baseline.pearson_skew_2,
                "top1OutcomeEvShare": baseline.tails[0.01].ev_share,
                "top5OutcomeEvShare": baseline.tails[0.05].ev_share,
                "top10OutcomeEvShare": baseline.tails[0.10].ev_share,
                "top1ConditionalTailMean": baseline.tails[0.01].conditional_mean,
                "horizons": confirmed,
                "runtimeSeconds": round(time.perf_counter() - set_started, 2),
                "tierB": bool(tier_b),
                "written": written,
            }
            if tier_b:
                record["reconciliation"] = tier_b["reconciliation"]
                record["simCardHhi"] = tier_b["concentration"].hhi
                record["simTopCardEvShare"] = tier_b["concentration"].top1_ev_share
            built.append(record)
            exports.append(record)

            capture = baseline.typical_capture
            print(
                f"{TAG} [{index}/{len(targets)}] {target.canonical_key:24s} "
                f"ev={baseline.ev:7.3f} p50={baseline.p50:6.3f} "
                f"capture={(capture * 100 if capture else float('nan')):5.1f}% "
                f"top1share={(baseline.tails[0.01].ev_share or 0) * 100:5.1f}% "
                f"r80c80={confirmed.get('realization_ge_0.80', {}).get('stableN')} "
                f"tau20c80={confirmed.get('within_tau_0.20', {}).get('stableN')} "
                f"{record['runtimeSeconds']:.1f}s"
            )
        except Exception as exc:  # noqa: BLE001 - one set must not abort the cohort
            logger.exception("%s set=%s failed", TAG, target.canonical_key)
            failures.append({"canonicalKey": target.canonical_key, "error": str(exc)})
            print(f"{TAG} [{index}/{len(targets)}] {target.canonical_key:24s} FAILED: {exc}")

    elapsed = time.perf_counter() - started
    status = STATUS_BUILT if not failures else (STATUS_PARTIAL if built else STATUS_FAILED)
    summary = {
        "status": status,
        "marketDate": day,
        "researchMethodVersion": EV_REPRESENTATIVENESS_VERSION,
        "cohortCount": len(targets),
        "builtCount": len(built),
        "failedCount": len(failures),
        "failures": failures,
        "withResimulation": with_resimulation,
        "dryRun": dry_run,
        "elapsedSeconds": round(elapsed, 2),
        "results": exports,
    }

    if export_dir is not None:
        export_dir.mkdir(parents=True, exist_ok=True)
        path = export_dir / f"ev_representativeness_{day}_{EV_REPRESENTATIVENESS_VERSION}.json"
        path.write_text(json.dumps(summary, indent=2, default=str), encoding="utf-8")
        print(f"{TAG} exported {path}")

    print(
        f"{TAG} status={status} built={len(built)} failed={len(failures)} "
        f"elapsed={elapsed:.1f}s"
    )
    return summary


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--market-date", default=None,
                        help="Market date to analyse. Defaults to the latest promoted complete batch.")
    parser.add_argument("--set", dest="sets", action="append", default=None,
                        help="Restrict to one canonical set key. Repeatable.")
    parser.add_argument("--with-research-resimulation", action="store_true",
                        help="Also run Tier B: a seeded instrumented re-simulation per set "
                             "(Parts 6/7/9/10/18/19). Costs roughly a minute per set.")
    parser.add_argument("--tier-b-packs", type=int, default=TIER_B_PACK_COUNT,
                        help="Packs per Tier B re-simulation (default matches the authoritative run).")
    parser.add_argument("--dry-run", action="store_true", help="Compute everything, write nothing.")
    parser.add_argument("--export", default=None, help="Directory for the machine-readable JSON export.")
    return parser


def main(argv: Optional[Sequence[str]] = None) -> int:
    logging.basicConfig(level=logging.WARNING, format="%(asctime)s %(levelname)s [%(name)s] %(message)s")
    args = build_parser().parse_args(argv)
    client = create_service_role_client()
    try:
        summary = build(
            client,
            market_date=args.market_date,
            canonical_keys=args.sets,
            with_resimulation=args.with_research_resimulation,
            tier_b_pack_count=args.tier_b_packs,
            dry_run=args.dry_run,
            export_dir=Path(args.export) if args.export else None,
        )
    except EvRepresentativenessError as exc:
        print(f"{TAG} cannot start: {exc}")
        return EXIT_FAILED
    if summary["status"] == STATUS_BUILT:
        return EXIT_OK
    return EXIT_PARTIAL if summary["builtCount"] else EXIT_FAILED


if __name__ == "__main__":
    sys.exit(main())
