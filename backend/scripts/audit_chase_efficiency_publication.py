"""Fail-closed audit of the persisted canonical Chase Efficiency pointer."""
from __future__ import annotations

import argparse
import json
from typing import Any, Dict, List

from backend.db.clients.supabase_client import create_service_role_client
from backend.db.services.chase_efficiency_service import _all, validate_candidate


def run_audit(client: Any, *, market_date: str) -> Dict[str, Any]:
    try:
        latest = list(client.table("pokemon_card_chase_efficiency_latest").select("snapshot_id,market_date").eq("market_date", market_date).execute().data or [])
        if len(latest) != 1: return {"passed": False, "failures": ["missing or ambiguous latest pointer"]}
        snapshot_id = latest[0]["snapshot_id"]
        snapshots = list(client.table("pokemon_card_chase_efficiency_snapshots").select("*").eq("id", snapshot_id).execute().data or [])
        if len(snapshots) != 1: return {"passed": False, "failures": ["latest snapshot missing"]}
        stored = snapshots[0]
        persisted = _all(lambda: client.table("pokemon_card_chase_efficiency_rows").select("*").eq("snapshot_id", snapshot_id))
        rows: List[Dict[str, Any]] = []
        for row in persisted:
            rows.append({
                **row, "probability": row.get("exact_pull_probability"),
                "current_market_price": row.get("current_near_mint_market_price"),
                "milestones": row.get("milestones_json"), "verified_routes": row.get("verified_routes_json"),
            })
        diagnostics = stored.get("diagnostics_json") or {}
        excluded = diagnostics.get("excludedRows") or []
        candidate = {"snapshot": stored, "rows": rows, "excluded": excluded}
        failures = validate_candidate(candidate)
        if stored.get("publication_status") != "published": failures.append("snapshot is not published")
        if str(stored.get("market_date")) != market_date: failures.append("promoted market date mismatch")
        return {"passed": not failures, "failures": failures, "snapshotId": snapshot_id,
                "eligibleCount": len(rows), "excludedCount": len(excluded),
                "excludedCountByReason": diagnostics.get("excludedCountByReason") or {}}
    except Exception as exc:
        return {"passed": False, "failures": [f"publication surface unreadable: {exc}"]}


def main(argv=None):
    parser = argparse.ArgumentParser(description=__doc__); parser.add_argument("--market-date", required=True)
    args = parser.parse_args(argv); report = run_audit(create_service_role_client(), market_date=args.market_date)
    print(json.dumps(report, indent=2, default=str)); return 0 if report["passed"] else 1


if __name__ == "__main__": raise SystemExit(main())
