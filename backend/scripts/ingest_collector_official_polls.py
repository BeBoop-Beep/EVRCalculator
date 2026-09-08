"""Ingest sparse, contextual first-party Pokemon Trainer poll observations."""
import argparse, hashlib, json, sys
from datetime import datetime, timezone
from pathlib import Path
from dotenv import load_dotenv

ROOT=Path(__file__).resolve().parents[2]
if str(ROOT) not in sys.path: sys.path.insert(0,str(ROOT))
from backend.desirability.collector_identity import normalize_identity_text  # noqa: E402

CONFIG=ROOT/"backend/config/pokemon_collector_official_polls_v1.json"

def build_rows(poll, entities):
    index={normalize_identity_text(e["display_name"]):e for e in entities}
    rows=[]
    for result in poll["results"]:
        entity=index.get(normalize_identity_text(result["trainer"])); matched=entity is not None
        rows.append({"collector_entity_id":entity["id"] if matched else None,"dimension_key":"official_poll_preference",
          "raw_entity_name":result["trainer"],"external_entity_key":"%s:%s"%(poll["pollKey"],normalize_identity_text(result["trainer"])),
          "raw_rank":result.get("rank"),"raw_value":result.get("percent"),"match_status":"matched" if matched else "unmatched",
          "match_confidence":1.0 if matched else None,"source_detail_url":poll["sourceUrl"],
          "raw_row_json":{"sourceStatus":"valid","pollKey":poll["pollKey"],"pollTitle":poll["title"],"pollContext":poll["context"],"unit":"percent"}})
    return rows

def main():
    p=argparse.ArgumentParser(description=__doc__);p.add_argument("--commit",action="store_true");a=p.parse_args();load_dotenv(ROOT/"backend/.env",override=False)
    from backend.db.clients.supabase_client import supabase
    payload=json.loads(CONFIG.read_text(encoding="utf-8")); poll=payload["polls"][0]
    entities=supabase.table("pokemon_collector_entity_reference").select("id,display_name").eq("entity_type","trainer").execute().data
    rows=build_rows(poll,entities); run_id=None
    if a.commit:
        fingerprint=hashlib.sha256(json.dumps(poll,sort_keys=True).encode()).hexdigest(); now=datetime.now(timezone.utc).isoformat()
        run=supabase.table("pokemon_collector_source_runs").insert({"source_name":"official_pokemon_trainer_polls","source_kind":"fan_ranking",
          "run_key":poll["pollKey"],"capture_version":"official_polls_v1","status":"running","source_url":poll["sourceUrl"],"raw_payload_json":poll}).execute().data[0];run_id=run["id"]
        for row in rows: row["source_run_id"]=run_id
        supabase.table("pokemon_collector_entity_observations").insert(rows).execute()
        supabase.table("pokemon_collector_source_runs").update({"status":"success","completed_at":now,"captured_at":poll["capturedAt"],"item_count":len(rows),
          "source_fingerprint":fingerprint,"diagnostics_json":{"rows":len(rows),"matched":sum(x["match_status"]=="matched" for x in rows),"dbReadRequests":1,"dbWriteRequests":3,"dbRowsRead":len(entities),"dbRowsInserted":len(rows)+1}}).eq("id",run_id).execute()
    print(json.dumps({"status":"committed" if a.commit else "dry_run","sourceRunId":run_id,"rows":len(rows),"matched":sum(x["match_status"]=="matched" for x in rows)},indent=2));return 0
if __name__=="__main__":raise SystemExit(main())
