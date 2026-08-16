"""Produce Stage 1 product results for real sets WITHOUT writing anything.

WHY THIS EXISTS
---------------
`simulation_sealed_product_results` is empty in production: Stage 1 has never run
there. The V3 product-scope validation needs real payloads across many sets, and
the only honest way to get them without inventing calculation runs is to run the
existing pack simulation and the existing Stage 1 scoring path in memory and dump
the rows to a file.

Nothing is persisted. `persist_fn` is a no-op and the placeholder
`calculation_run_id` is the nil UUID, which is exactly why these rows must never
be inserted.

    python backend/scripts/collect_stage1_product_dry_run.py --out tmp/rows.json
    python backend/scripts/collect_stage1_product_dry_run.py --sets surgingSparks
"""

from __future__ import annotations

import argparse
import json
import logging
import time
from typing import Any, Dict, List

from backend.db.clients.supabase_client import supabase
from backend.db.repositories.sets_repository import get_set_by_canonical_key
from backend.db.services.evr_input_preparation_service import EVRInputPreparationService
from backend.db.services.pokemon_set_sealed_market_snapshot_service import read_snapshot
from backend.db.services.sealed_product_rip_service import (
    _to_row,
    resolve_set_collector_appeal,
    run_stage1_sealed_product_rip,
)
from backend.jobs.evr_runner import _build_constants_config_map, _resolve_set_config
from backend.simulations import calculate_pack_simulations

logger = logging.getLogger(__name__)

NIL_RUN_ID = "00000000-0000-0000-0000-000000000000"


def collect_for_set(canonical_key: str) -> Dict[str, Any]:
    config_cls, canonical = _resolve_set_config(canonical_key)
    config = config_cls()
    set_row = get_set_by_canonical_key(canonical)
    if not set_row:
        return {"canonicalKey": canonical, "status": "no_set_row"}

    set_name = str(getattr(config, "SET_NAME", canonical))
    prepared = EVRInputPreparationService().prepare_for_set(config, canonical, set_name)

    sim_started = time.perf_counter()
    sim_results, _pack_metrics = calculate_pack_simulations(prepared["dataframe"], config)
    sim_ms = (time.perf_counter() - sim_started) * 1000.0

    captured: List[Dict[str, Any]] = []

    def _no_write(rows):
        captured.extend(rows)
        return []  # DRY RUN: nothing is written anywhere.

    summary = run_stage1_sealed_product_rip(
        sim_results=sim_results,
        set_id=set_row["id"],
        canonical_set_key=canonical,
        calculation_run_id=NIL_RUN_ID,
        read_snapshot_fn=lambda sid: read_snapshot(supabase, sid),
        persist_fn=_no_write,
        # EXPLICIT, unlike the scheduled path. This script sweeps every set in ONE
        # process, so the Collector Appeal bundle cache actually works here and
        # the cold build is paid once for the whole sweep - which is exactly the
        # condition the per-set scheduled path cannot satisfy.
        collector_appeal_fn=resolve_set_collector_appeal,
    )
    return {
        "canonicalKey": canonical,
        "setId": str(set_row["id"]),
        "status": summary.get("status"),
        "reason": summary.get("reason"),
        "packSimulationMs": round(sim_ms, 1),
        "stage1ElapsedMs": summary.get("elapsedMs"),
        "phaseTimingsMs": summary.get("phaseTimingsMs"),
        "skippedReasons": summary.get("skippedReasons"),
        "rows": captured,
    }


def main() -> int:
    logging.basicConfig(level=logging.WARNING, format="%(levelname)s %(message)s")
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--sets", nargs="*", default=None, help="Canonical keys; default is every configured set.")
    parser.add_argument("--out", default="tmp/stage1_dry_run_rows.json")
    args = parser.parse_args()

    keys = args.sets or sorted(_build_constants_config_map())
    results = []
    for index, key in enumerate(keys, start=1):
        print(f"[{index}/{len(keys)}] {key} ...", flush=True)
        try:
            result = collect_for_set(key)
        except Exception as exc:  # noqa: BLE001 - a dry run must report, not abort
            logger.exception("collection failed for %s", key)
            result = {"canonicalKey": key, "status": "error", "error": f"{type(exc).__name__}: {exc}"}
        results.append(result)
        print(
            f"    status={result.get('status')} rows={len(result.get('rows') or [])} "
            f"sim_ms={result.get('packSimulationMs')} stage1_ms={result.get('stage1ElapsedMs')}",
            flush=True,
        )
        with open(args.out, "w", encoding="utf-8") as handle:
            json.dump({"source": "dry_run", "sets": results}, handle)

    total_rows = sum(len(r.get("rows") or []) for r in results)
    print(f"\nWrote {total_rows} product rows across {len(results)} sets -> {args.out}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
