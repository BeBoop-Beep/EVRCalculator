"""Read-only 90/180/365-day mature-vintage history availability audit."""
from __future__ import annotations
import json
from datetime import date
from pathlib import Path
from dotenv import load_dotenv
from backend.db.clients.supabase_client import create_service_role_client
from backend.desirability.treatment_market_prestige_v3 import stable_json_hash
from backend.scripts.build_treatment_market_prestige_v3_round7 import pull

ROOT=Path("docs/research");COHORT=ROOT/"treatment_market_prestige_v3_round5_frozen/cohort.json";SETMAP=ROOT/"treatment_market_prestige_v3_frozen_cohort/set_era_mapping.json";OUT=ROOT/"treatment_market_prestige_v3_round14_vintage_history_audit.json";OBS=ROOT/"treatment_market_prestige_v3_round14_vintage_observations.json"
HORIZONS={"90_DAY":[date(2026,5,31),date(2026,6,30),date(2026,7,30),date(2026,8,29)],"180_DAY":[date(2026,3,2),date(2026,5,1),date(2026,6,30),date(2026,8,29)],"365_DAY":[date(2025,8,29),date(2025,12,29),date(2026,4,29),date(2026,8,29)]}
CUTOFF=date(2011,8,29)
def main():
 rows=json.loads(COHORT.read_text(encoding="utf-8"))["rows"];sets={x["id"]:x for x in json.loads(SETMAP.read_text(encoding="utf-8"))};era_last={}
 for r in rows:
  d=sets.get(r["set_id"],{}).get("release_date")
  if d:era_last[r["era_name"]]=max(era_last.get(r["era_name"],d),d)
 mature={e for e,d in era_last.items() if date.fromisoformat(d)<=CUTOFF};selected=[r for r in rows if r["era_name"] in mature and r.get("species_id") and r.get("demand_score") is not None and not r.get("promo_status_ambiguous")];variants=sorted({r["variant_id"] for r in selected});load_dotenv(Path("backend/.env"));client=create_service_role_client();conditions=client.table("conditions").select("id,name,abbreviation").execute().data or [];nm=next(x for x in conditions if x.get("name")=="Near Mint" or x.get("abbreviation")=="NM");cid=str(nm["id"]);dates=sorted({d for ds in HORIZONS.values() for d in ds});observations={}
 for d in dates:
  print(f"read-only vintage checkpoint {d}",flush=True);p=pull(client,variants,cid,d);observations[d.isoformat()]={v:{"market_price":float(x["market_price"]),"captured_at":x.get("captured_at"),"source":x.get("source")} for v,x in p.items()}
 summary={}
 for era in sorted(mature):
  g=[r for r in selected if r["era_name"]==era]
  if not g:continue
  summary[era]={"eligibleCards":len(g),"finalSetRelease":era_last[era],"horizons":{}}
  for h,ds in HORIZONS.items():
   per={d.isoformat():sum(r["variant_id"] in observations[d.isoformat()] for r in g) for d in ds};all4=sum(all(r["variant_id"] in observations[d.isoformat()] for d in ds) for r in g);summary[era]["horizons"][h]={"perDateAvailable":per,"perDateCoverage":{d:n/len(g) for d,n in per.items()},"allFourCards":all4,"allFourCoverage":all4/len(g),"historyReady":all(n/len(g)>=.95 for n in per.values())}
 payload={"readOnly":True,"matureVintageDefinition":{"rule":"era final canonical set release is at least 15 years before 2026-08-29","cutoff":CUTOFF.isoformat(),"definedBeforeOutcomeInspection":True},"condition":"Near Mint; positive finite USD market_price; fixed seven-day windows; no interpolation","horizons":{k:[d.isoformat() for d in v] for k,v in HORIZONS.items()},"matureEras":sorted(mature),"selectedVariants":len(variants),"summary":summary,"observationIdentityHash":stable_json_hash({d:sorted(v) for d,v in observations.items()})};OUT.write_text(json.dumps(payload,indent=2),encoding="utf-8");OBS.write_text(json.dumps({"readOnly":True,"observations":observations},indent=2),encoding="utf-8")
if __name__=="__main__":main()
