"""Append exact current RIP authorities after the existing daily publication.

This command is deliberately not a scheduler.  The Windows daily publication
owns cadence; this is its final, idempotent history step.  It never calls a
Trends provider.  When a source is due it fails closed and prints the due
source keys so the sanctioned source-capture lifecycle can run first.
"""
from __future__ import annotations

import argparse
import hashlib
import json
import sys
from datetime import date, datetime, timezone
from pathlib import Path
from typing import Any, Mapping, Sequence

from dotenv import load_dotenv

ROOT = Path(__file__).resolve().parents[2]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from backend.scripts.plan_collector_appeal_refresh import freshness_plan

V7 = "pokemon_collector_appeal_v7_expanded_price_blind_v1"


def _paged(query_factory):
    rows, start = [], 0
    while True:
        part = query_factory().range(start, start + 999).execute().data or []
        rows.extend(part)
        if len(part) < 1000:
            return rows
        start += 1000


def build_plan(client: Any, *, as_of: date, now: datetime) -> dict[str, Any]:
    runs = _paged(lambda: client.table("pokemon_collector_source_runs").select(
        "id,source_name,status,captured_at,raw_payload_json"
    ))
    freshness = freshness_plan(runs, now)
    current = (client.table("pokemon_collector_appeal_current")
               .select("model_run_id,model_version,as_of_date")
               .eq("scope", "pokemon").single().execute().data)
    if not current or current.get("model_version") != V7:
        raise RuntimeError("current Collector authority is not frozen V7")
    model = (client.table("pokemon_collector_appeal_model_runs")
             .select("id,input_fingerprint,source_run_ids,scoring_config_json")
             .eq("id", current["model_run_id"]).single().execute().data)
    scores = _paged(lambda: client.table("pokemon_set_collector_appeal_scores").select(
        "set_id,collector_appeal_score,score_status"
    ).eq("model_run_id", current["model_run_id"]))
    set_ids = sorted(str(row["set_id"]) for row in scores)
    existing = (client.table("pokemon_rip_temporal_history").select("entity_id", count="exact")
                .eq("domain", "collector").eq("as_of_date", as_of.isoformat())
                .eq("model_version", V7).limit(0).execute().count or 0)
    return {
        "asOfDate": as_of.isoformat(), "freshness": freshness,
        "providerCallsPlanned": 0, "modelRunId": current["model_run_id"],
        "modelFingerprint": model["input_fingerprint"],
        "cohortFingerprint": hashlib.sha256(json.dumps(set_ids, separators=(",", ":")).encode()).hexdigest(),
        "rowsPlanned": len(scores),
        "scoredRows": sum(row.get("score_status") == "scored" for row in scores),
        "unavailableRows": sum(row.get("score_status") != "scored" for row in scores),
        "existingRows": existing,
        "rowsToAppend": max(0, len(scores) - existing),
        "sourceRunIds": model["source_run_ids"],
    }


def execute(client: Any, *, as_of: date, now: datetime, commit: bool) -> dict[str, Any]:
    plan = build_plan(client, as_of=as_of, now=now)
    if not plan["freshness"]["allFresh"]:
        due = [x["key"] for x in plan["freshness"]["sources"] if x["due"]]
        plan.update(status="SOURCE_REFRESH_REQUIRED", dueSources=due, mutationsPerformed=0)
        return plan
    if not commit:
        plan.update(status="VALIDATED_DRY_RUN", mutationsPerformed=0)
        return plan
    inserted = client.rpc("append_current_collector_v7_history", {
        "p_as_of_date": as_of.isoformat()
    }).execute().data
    plan.update(status="APPENDED" if inserted else "ALREADY_PRESENT",
                mutationsPerformed=int(inserted or 0))
    return plan


def main(argv: Sequence[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--as-of-date", required=True)
    parser.add_argument("--commit", action="store_true")
    args = parser.parse_args(argv)
    load_dotenv(ROOT / "backend/.env", override=False)
    from backend.db.clients.supabase_client import supabase
    report = execute(supabase, as_of=date.fromisoformat(args.as_of_date),
                     now=datetime.now(timezone.utc), commit=args.commit)
    print(json.dumps(report, indent=2, default=str))
    return 0 if report["status"] != "SOURCE_REFRESH_REQUIRED" else 2


if __name__ == "__main__":
    raise SystemExit(main())
