"""Read-only E-Card retention root-cause audit; no reconstructed prices."""
from __future__ import annotations
import json
from collections import Counter
from datetime import date,timedelta
from pathlib import Path
from dotenv import load_dotenv
from backend.db.clients.supabase_client import create_service_role_client
from backend.desirability.treatment_market_prestige_v3 import stable_json_hash
from backend.scripts.build_treatment_market_prestige_v3_round7 import DATES,chunks

ROOT=Path("docs/research");COHORT=ROOT/"treatment_market_prestige_v3_round5_frozen/cohort.json";R12OBS=ROOT/"treatment_market_prestige_v3_round12_history_observations.json";OUT=ROOT/"treatment_market_prestige_v3_round13_ecard_retention_audit.json"
def main():
 rows=json.loads(COHORT.read_text(encoding="utf-8"))["rows"];eligible=[r for r in rows if r["era_name"]=="E-Card" and r.get("species_id") and r.get("demand_score") is not None and not r.get("promo_status_ambiguous")];frozen=json.loads(R12OBS.read_text(encoding="utf-8"))["observations"]
 load_dotenv(Path("backend/.env"));client=create_service_role_client();conditions=client.table("conditions").select("id,name,abbreviation").execute().data or [];nm=next(x for x in conditions if x.get("name")=="Near Mint" or x.get("abbreviation")=="NM");cid=str(nm["id"]);records=[]
 for checkpoint in DATES:
  d=checkpoint.isoformat();missing=[r for r in eligible if r["variant_id"] not in frozen[d]];wide={}
  for part in chunks(sorted({r["variant_id"] for r in missing}),75):
   offset=0
   while True:
    batch=(client.table("card_variant_price_observations").select("id,card_variant_id,condition_id,market_price,currency,source,captured_at,captured_date").in_("card_variant_id",part).gte("captured_at",(checkpoint-timedelta(days=30)).isoformat()).lt("captured_at",(checkpoint+timedelta(days=31)).isoformat()).range(offset,offset+999).execute().data or [])
    for x in batch:wide.setdefault(str(x["card_variant_id"]),[]).append(x)
    if len(batch)<1000:break
    offset+=1000
  for r in missing:
   found=wide.get(r["variant_id"],[]);same=[x for x in found if str(x.get("condition_id"))==cid and str(x.get("currency") or "").strip('"').upper()=="USD" and float(x.get("market_price") or 0)>0]
   other=[x for x in found if str(x.get("condition_id"))!=cid]
   cause="INCOMPLETE_SOURCE_INGESTION" if same else "PRICE_CONDITION_MISMATCH" if other else "HISTORICAL_OBSERVATIONS_NEVER_RETAINED"
   records.append({"canonicalCardId":r["canonical_card_id"],"variantId":r["variant_id"],"checkpoint":d,"cause":cause,"nearMintObservationsWithin30Days":len(same),"otherConditionObservationsWithin30Days":len(other),"safeCheckpointRepair":False})
 payload={"readOnly":True,"era":"E-Card","eligibleCards":len(eligible),"missingCardDates":len(records),"rootCauses":dict(Counter(x["cause"] for x in records)),"safeRepairedObservations":0,"repairedAllFourCoverage":sum(all(r["variant_id"] in frozen[d.isoformat()] for d in DATES) for r in eligible)/len(eligible),"reason":"Observations outside the fixed seven-day checkpoint window cannot be substituted or interpolated.","records":records};payload["auditHash"]=stable_json_hash(payload);OUT.write_text(json.dumps(payload,indent=2),encoding="utf-8")
if __name__=="__main__":main()
