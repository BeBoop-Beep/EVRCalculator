"""Freeze read-only Round 11 internal-history coverage for EX/B&W/Trainer/Energy."""
from __future__ import annotations
import json
from collections import defaultdict
from pathlib import Path

from dotenv import load_dotenv
from backend.db.clients.supabase_client import create_service_role_client
from backend.desirability.treatment_market_prestige_v3 import stable_json_hash
from backend.scripts.build_treatment_market_prestige_v3_round7 import DATES, SOURCE, pull

ROOT=Path("docs/research"); COHORT=ROOT/"treatment_market_prestige_v3_round5_frozen/cohort.json"
OUT=ROOT/"treatment_market_prestige_v3_round11_history_audit.json"
OBS=ROOT/"treatment_market_prestige_v3_round11_history_observations.json"

def main()->None:
    rows=json.loads(COHORT.read_text(encoding="utf-8"))["rows"]
    selected=[r for r in rows if r["era_name"] in {"EX","Black and White"} or r.get("supertype") in {"Trainer","Energy"}]
    variants=sorted({r["variant_id"] for r in selected});load_dotenv(Path("backend/.env"));client=create_service_role_client()
    conditions=client.table("conditions").select("id,name,abbreviation").execute().data or []
    nm=next((x for x in conditions if x.get("name")=="Near Mint" or x.get("abbreviation")=="NM"),None)
    if not nm:raise RuntimeError("Near Mint condition unavailable")
    observations={};by_variant={r["variant_id"]:r for r in selected}
    for checkpoint in DATES:
        print(f"read-only checkpoint {checkpoint}",flush=True); prices=pull(client,variants,str(nm["id"]),checkpoint)
        observations[checkpoint.isoformat()]={vid:{"market_price":float(p["market_price"]),"captured_at":p.get("captured_at"),"source":p.get("source")} for vid,p in prices.items()}
    domains={"EX":lambda r:r["era_name"]=="EX","Black and White":lambda r:r["era_name"]=="Black and White","Trainer":lambda r:r.get("supertype")=="Trainer","Energy":lambda r:r.get("supertype")=="Energy"}
    summary={}
    for name,predicate in domains.items():
        group=[r for r in selected if predicate(r)]; per_date={d:sum(r["variant_id"] in observations[d] for r in group) for d in observations}
        all_four=sum(all(r["variant_id"] in observations[d] for d in observations) for r in group)
        any_history=sum(any(r["variant_id"] in observations[d] for d in observations) for r in group)
        summary[name]={"cards":len(group),"perDateAvailable":per_date,"perDateCoverage":{d:n/len(group) for d,n in per_date.items()},"allFourCards":all_four,"allFourCoverage":all_four/len(group),"anyHistoryCards":any_history,"missingAllHistoryCards":len(group)-any_history}
    payload={"readOnly":True,"source":SOURCE,"conditionId":str(nm["id"]),"checkpointDates":[d.isoformat() for d in DATES],"selectedVariants":len(variants),"summary":summary,"observationIdentityHash":stable_json_hash({d:sorted(v) for d,v in observations.items()})}
    OUT.write_text(json.dumps(payload,indent=2),encoding="utf-8")
    OBS.write_text(json.dumps({"readOnly":True,"checkpointDates":payload["checkpointDates"],"observations":observations},indent=2),encoding="utf-8")
if __name__=="__main__":main()
