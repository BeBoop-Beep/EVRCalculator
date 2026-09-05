"""Rebuild + persist Chase Accessibility V1 snapshots for the current cohort.

WHY THIS EXISTS
---------------
`pokemon_set_chase_accessibility_snapshot_latest` (migration 077) is bound to
ONE calculation run per set (see chase_accessibility_service.py's AUTHORITY
note): the V12 authority check in sealed_product_rip_finalization_service.py
refuses an Accessibility row whose `calculation_run_id` does not match the
product cohort's own current run, on purpose, because Accessibility is
computed from that run's own simulated pull-rate variants.

There was previously no production job that rebuilt these snapshots for a
NEW day's simulation run - only `audit_chase_accessibility_v1.py` (read-only,
writes nothing) and test coverage of the builder/persist functions
themselves. This script is the missing write path: for every set the
opening-simulation gate considers CURRENT for a market date, it builds and
upserts one row via the same `build_chase_accessibility_snapshot_row` /
`persist_chase_accessibility_snapshot` functions the tests already exercise.

Idempotent: re-running for the same (set_id, calculation_run_id) recomputes
and upserts the same row (upsert keyed by set_id).

    python -m backend.scripts.rebuild_chase_accessibility_snapshots \
        --market-date 2026-09-04 --json
"""

from __future__ import annotations

import argparse
import json
import sys
from typing import Any, Dict, List, Sequence


def rebuild(client: Any, *, market_date: str) -> Dict[str, Any]:
    from backend.db.services.chase_accessibility_service import (
        build_chase_accessibility_snapshot_row,
        persist_chase_accessibility_snapshot,
    )
    from backend.db.services.ev_representativeness_service import resolve_research_cohort

    targets = resolve_research_cohort(client, market_date=market_date, canonical_keys=None)

    rows: List[Dict[str, Any]] = []
    for target in targets:
        row = build_chase_accessibility_snapshot_row(
            set_id=target.set_id,
            calculation_run_id=target.calculation_run_id,
            client=client,
            market_date=market_date,
        )
        persisted = persist_chase_accessibility_snapshot(row, client=client)
        rows.append({
            "setId": target.set_id,
            "setName": target.set_name,
            "calculationRunId": target.calculation_run_id,
            "status": persisted.get("status"),
            "accessibility": persisted.get("accessibility"),
        })
        print(
            "[chase-accessibility-rebuild] set=%s run=%s status=%s"
            % (target.set_name, target.calculation_run_id, persisted.get("status")),
            flush=True,
        )

    return {
        "marketDate": market_date,
        "cohortSetCount": len(targets),
        "rebuiltCount": len(rows),
        "readyCount": sum(1 for r in rows if r["status"] == "ready"),
        "rows": rows,
    }


def main(argv: Sequence[str]) -> int:
    parser = argparse.ArgumentParser(
        description="Rebuild + persist Chase Accessibility snapshots for the current cohort."
    )
    parser.add_argument("--market-date", required=True)
    parser.add_argument("--json", action="store_true", help="print the raw report as JSON")
    args = parser.parse_args(list(argv))

    from backend.db.clients.supabase_client import supabase as client

    report = rebuild(client, market_date=args.market_date)

    if args.json:
        print(json.dumps(report, indent=2))
    else:
        print(
            "\n[chase-accessibility-rebuild] marketDate=%s cohortSetCount=%d "
            "rebuiltCount=%d readyCount=%d"
            % (report["marketDate"], report["cohortSetCount"],
               report["rebuiltCount"], report["readyCount"])
        )
    return 0


if __name__ == "__main__":
    raise SystemExit(main(sys.argv[1:]))
