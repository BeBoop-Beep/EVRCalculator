"""Build, audit, report, and optionally publish canonical Chase Efficiency."""
from __future__ import annotations

import argparse
import json

from backend.db.clients.supabase_client import create_service_role_client
from backend.db.services.chase_efficiency_service import load_candidate, publish_candidate, validate_candidate


def run(*, market_date: str, commit: bool, client=None):
    client = client or create_service_role_client()
    candidate = load_candidate(client, market_date=market_date)
    failures = validate_candidate(candidate)
    rows = candidate["rows"]
    report = {
        **candidate["snapshot"], "audit": "PASS" if not failures else "FAIL", "auditFailures": failures,
        "top25": [{k: row.get(k) for k in ("overall_rank","overall_cohort_size","card_name","canonical_rarity","chase_efficiency","probability","current_market_price","best_verified_pack_equivalent_cost","era_rank","era_cohort_size","set_rank","set_cohort_size","rarity_rank","rarity_cohort_size")} for row in rows[:25]],
        "topSIRs": [{"rank": r["rarity_rank"], "name": r["card_name"], "chaseEfficiency": r["chase_efficiency"]} for r in rows if r.get("canonical_rarity") == "Special Illustration Rare"][:25],
        "topIRs": [{"rank": r["rarity_rank"], "name": r["card_name"], "chaseEfficiency": r["chase_efficiency"]} for r in rows if r.get("canonical_rarity") == "Illustration Rare"][:25],
    }
    if failures: return 1, report
    if commit: report["snapshotId"] = publish_candidate(client, candidate)
    return 0, report


def main(argv=None):
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--market-date", required=True)
    mode = parser.add_mutually_exclusive_group(required=True); mode.add_argument("--dry-run", action="store_true"); mode.add_argument("--commit", action="store_true")
    args = parser.parse_args(argv)
    code, report = run(market_date=args.market_date, commit=args.commit)
    print(json.dumps(report, indent=2, default=str)); return code


if __name__ == "__main__": raise SystemExit(main())
