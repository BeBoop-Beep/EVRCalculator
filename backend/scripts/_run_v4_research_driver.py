"""Throwaway, SELECT-only driver for the V4/V10 equal-spend research.

Bypasses `resolve_authoritative_snapshot` (which requires the PUBLISHED
`pokemon_public_rip_leaderboard_snapshots` row to be V3/V9-prefixed - it is,
as of this run, because the daily Set RIP leaderboard publish job has not
been re-run under V10 yet, independent of the per-product V4/V10 scores,
which ARE fully computed). Instead this resolves "the current calculation
run per set" directly from `simulation_sealed_product_results` wherever
`financial_rip_v4_status = 'ready'`, which is the same authority Family Rank
already reads. Read-only. No production writes.
"""
from __future__ import annotations

import json
import sys
from collections import defaultdict
from pathlib import Path

REPO_ROOT = Path(__file__).resolve().parents[2]
if str(REPO_ROOT) not in sys.path:
    sys.path.insert(0, str(REPO_ROOT))

from backend.scripts.pokemon_snapshot_builders import get_client
import backend.scripts.research_equal_spend_product_rip_v4 as research


def resolve_authority_from_v4_rows(client):
    rows = client.table("simulation_sealed_product_results").select(
        "set_id,calculation_run_id,financial_rip_v4_status"
    ).eq("financial_rip_v4_status", "ready").execute().data or []
    by_set: dict[str, set[str]] = defaultdict(set)
    for row in rows:
        by_set[str(row["set_id"])].add(str(row["calculation_run_id"]))
    problems = [set_id for set_id, runs in by_set.items() if len(runs) != 1]
    if problems:
        raise RuntimeError(f"sets with ambiguous V4-ready run id: {problems}")
    # The REAL set_canonical_key (e.g. "temporalForces"), not the set_id, is
    # required: it feeds the deterministic resampling fingerprint inside
    # build_stage1_product_distributions, and substituting set_id produced a
    # small but real reconstruction delta (~0.01 / 100) in verification.
    # pokemon_public_rip_leaderboard_rows carries this mapping independent of
    # which model version that leaderboard was last published under.
    key_rows = client.table("pokemon_public_rip_leaderboard_rows").select(
        "set_id,set_canonical_key"
    ).execute().data or []
    canonical_key_by_set = {str(r["set_id"]): str(r["set_canonical_key"]) for r in key_rows if r.get("set_canonical_key")}
    missing_keys = sorted(set(by_set) - set(canonical_key_by_set))
    if missing_keys:
        raise RuntimeError(f"sets with V4-ready rows but no known set_canonical_key: {missing_keys}")
    authority_rows = [
        {
            "set_id": set_id,
            "set_canonical_key": canonical_key_by_set[set_id],
            "simulation_calculation_run_id": next(iter(runs)),
        }
        for set_id, runs in sorted(by_set.items())
    ]
    snapshot = {
        "id": "adhoc-v4-research-authority",
        "market_date": "live-query",
        "eligible_cohort_count": len(authority_rows),
    }
    return snapshot, authority_rows


def main() -> int:
    client = get_client()
    research.resolve_authoritative_snapshot = resolve_authority_from_v4_rows
    report = research.run_research(client)
    out = Path("logs/equal_spend_product_rip_research_v4.json")
    out.parent.mkdir(parents=True, exist_ok=True)
    out.write_text(json.dumps(report, indent=2, default=str), encoding="utf-8")
    print(f"wrote {out}")
    print(json.dumps({
        "cohortSize": report["authority"]["cohortSize"],
        "productRowCount": report["authority"]["productRowCount"],
        "familyCoverage": report["familyCoverage"],
        "threeWayAgreement": report["threeWayAgreement"],
        "dominance": report["dominance"],
        "rankCorrelation": {k: v for k, v in report["rankCorrelation"].items() if k != "cohorts"},
        "calibrationCoherence": report["calibrationCoherence"],
        "priceEfficiency": report["priceEfficiency"],
    }, indent=2, default=str))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
