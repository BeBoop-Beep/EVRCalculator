"""Daily coverage health check for the fixed-panel active-supply collector."""
from __future__ import annotations

import argparse
import json
import uuid
from datetime import date, datetime, timedelta, timezone
from pathlib import Path
from typing import Any

ROOT = Path(__file__).resolve().parents[2]
MANIFEST = ROOT / "docs/research/index_fair_value/core_panel_v1_manifest.json"

def evaluate(rows: list[dict[str, Any]], *, expected_date: str, expected_targets: int = 207) -> dict[str, Any]:
    matching = [row for row in rows if row.get("expected_observation_date") == expected_date]
    if not matching:
        return {"healthy": False, "state": "RUN_MISSING", "expected_date": expected_date,
                "expected_targets": expected_targets, "observed_targets": 0, "coverage": 0.0}
    run = matching[0]
    observed = int(run.get("observed_target_count") or 0)
    target_count = int(run.get("target_count") or expected_targets)
    coverage = observed / target_count if target_count else 0.0
    return {"healthy": run.get("status") == "COMPLETE" and observed == target_count,
            "state": run.get("status"), "expected_date": expected_date,
            "expected_targets": target_count, "observed_targets": observed,
            "coverage": round(coverage, 6), "run_id": run.get("run_id")}


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--expected-date", default=(date.today() - timedelta(days=1)).isoformat())
    parser.add_argument("--record-missing", action="store_true",
                        help="persist explicit RUN_MISSING continuity rows (not scheduled by this PR)")
    args = parser.parse_args()
    from backend.db.clients.supabase_client import create_service_role_client

    db = create_service_role_client()
    rows = (db.table("market_active_supply_snapshot_runs_v1")
            .select("run_id,expected_observation_date,status,target_count,observed_target_count")
            .eq("source_provider", "pkmnprices_tcgplayer")
            .eq("expected_observation_date", args.expected_date).execute().data or [])
    result = evaluate(rows, expected_date=args.expected_date)
    if result["state"] == "RUN_MISSING" and args.record_missing:
        manifest = json.loads(MANIFEST.read_text(encoding="utf-8"))
        run_id = str(uuid.uuid4())
        now = datetime.now(timezone.utc).isoformat()
        db.table("market_active_supply_snapshot_runs_v1").insert({
            "run_id": run_id, "panel_version": manifest["version"],
            "panel_fingerprint": manifest["panel_fingerprint"],
            "source_provider": "pkmnprices_tcgplayer",
            "expected_observation_date": args.expected_date,
            "started_at": now, "finished_at": now, "status": "MISSING",
            "target_count": len(manifest["rows"]), "observed_target_count": 0,
            "metadata": {"reason": "expected_collection_not_observed", "automatic_schedule_enabled": False},
        }).execute()
        snapshots = [{
            "run_id": run_id, "canonical_card_id": row["canonical_card_id"],
            "card_variant_id": row["card_variant_id"], "source_provider": "pkmnprices_tcgplayer",
            "source_card_id": str(row.get("provider_card_id") or f"tcgplayer:{row['tcgplayer_product_id']}"),
            "observed_at": None, "observation_state": "RUN_MISSING", "language": "English",
            "condition_label": "Near Mint", "printing_label": row.get("printing_type"),
            "requested_depth": 0, "captured_listing_count": 0, "captured_quantity": 0,
            "distinct_seller_count": 0, "has_more": None, "next_cursor_present": None,
            "continuity_eligible": False, "error_code": "EXPECTED_RUN_MISSING",
            "source_payload": {"absence_is_not_disappearance": True},
        } for row in manifest["rows"]]
        for start in range(0, len(snapshots), 100):
            db.table("market_active_supply_snapshots_v1").insert(snapshots[start:start + 100]).execute()
        result = {**result, "run_id": run_id, "missing_rows_recorded": len(snapshots)}
    print(json.dumps(result, indent=2, sort_keys=True))
    return 0 if result["healthy"] else 1


if __name__ == "__main__":
    raise SystemExit(main())
