"""Idempotently prepare Set component diagnostics for the promoted Collector run."""
from __future__ import annotations

import json
import os
from pathlib import Path

from dotenv import load_dotenv
from supabase import ClientOptions, create_client

from backend.desirability.collector_component_rankings import build_component_ranking_rows

ROOT = Path(__file__).resolve().parents[2]


def backfill_current_component_rankings(client):
    pointers = (client.table("pokemon_collector_appeal_current")
                .select("model_run_id,model_version,as_of_date")
                .eq("scope", "pokemon").limit(1).execute().data or [])
    if len(pointers) != 1:
        raise RuntimeError("exactly one current pokemon Collector run is required")
    pointer = pointers[0]
    model_run_id = str(pointer["model_run_id"])
    card_rows = []
    page_size = 1000
    for start in range(0, 100_000, page_size):
        batch = (client.table("pokemon_card_collector_appeal_scores")
                 .select("model_run_id,pokemon_canonical_card_id,set_id,subject_policy,subject_baseline_score,artist_recognition_score,playability_score,component_inputs_json")
                 .eq("model_run_id", model_run_id)
                 .order("pokemon_canonical_card_id")
                 .range(start, start + page_size - 1).execute().data or [])
        card_rows.extend(batch)
        if len(batch) < page_size:
            break
    if not card_rows or any(str(row["model_run_id"]) != model_run_id for row in card_rows):
        raise RuntimeError("current Collector card rows are missing or mixed across runs")
    prepared = build_component_ranking_rows(card_rows, model_run_id)
    for start in range(0, len(prepared), 100):
        client.table("pokemon_set_collector_component_rankings").upsert(
            prepared[start:start + 100], on_conflict="model_run_id,set_id"
        ).execute()
    current = (client.table("pokemon_set_collector_component_rankings_current_v")
               .select("model_run_id,set_id,drivers_json")
               .eq("model_run_id", model_run_id).execute().data or [])
    coverage = {
        key: sum((row.get("drivers_json") or {}).get(key, {}).get("status") == "scored" for row in current)
        for key in ("pokemonAppeal", "trainerAppeal", "artistImpact", "playabilityImpact")
    }
    if len(current) != len(prepared):
        raise RuntimeError("prepared Set diagnostic persistence count mismatch")
    return {"modelRunId": model_run_id, "modelVersion": pointer["model_version"],
            "asOfDate": pointer["as_of_date"], "cardRows": len(card_rows),
            "setRows": len(current), "coverage": coverage}


def main():
    load_dotenv(ROOT / "backend" / ".env", override=False)
    client = create_client(os.environ["SUPABASE_URL"], os.environ["SUPABASE_SERVICE_ROLE_KEY"],
                           options=ClientOptions(postgrest_client_timeout=90))
    print(json.dumps(backfill_current_component_rankings(client), indent=2))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
