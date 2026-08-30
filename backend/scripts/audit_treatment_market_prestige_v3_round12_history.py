"""Read-only four-checkpoint history freeze for remaining unsupported Pokémon eras."""
from __future__ import annotations
import json
from pathlib import Path
from dotenv import load_dotenv
from backend.db.clients.supabase_client import create_service_role_client
from backend.desirability.treatment_market_prestige_v3 import stable_json_hash
from backend.scripts.build_treatment_market_prestige_v3_round7 import DATES,SOURCE,pull

ROOT=Path("docs/research");COHORT=ROOT/"treatment_market_prestige_v3_round5_frozen/cohort.json";OUT=ROOT/"treatment_market_prestige_v3_round12_history_audit.json";OBS=ROOT/"treatment_market_prestige_v3_round12_history_observations.json"
EXCLUDED={"Scarlet and Violet","Mega Evolution","Sword and Shield","Sun and Moon","XY","EX","Black and White"}
def main():
 rows=json.loads(COHORT.read_text(encoding="utf-8"))["rows"];selected=[r for r in rows if r["era_name"] not in EXCLUDED and r.get("species_id") and r.get("demand_score") is not None and not r.get("promo_status_ambiguous")]
 variants=sorted({r["variant_id"] for r in selected});load_dotenv(Path("backend/.env"));client=create_service_role_client();conditions=client.table("conditions").select("id,name,abbreviation").execute().data or [];nm=next((x for x in conditions if x.get("name")=="Near Mint" or x.get("abbreviation")=="NM"),None)
 if not nm:raise RuntimeError("Near Mint condition unavailable")
 observations={}
 for d in DATES:
  print(f"read-only checkpoint {d}",flush=True);prices=pull(client,variants,str(nm["id"]),d);observations[d.isoformat()]={v:{"market_price":float(x["market_price"]),"captured_at":x.get("captured_at"),"source":x.get("source")} for v,x in prices.items()}
 summary={}
 for era in sorted({r["era_name"] for r in selected}):
  g=[r for r in selected if r["era_name"]==era];per={d:sum(r["variant_id"] in observations[d] for r in g) for d in observations};all4=sum(all(r["variant_id"] in observations[d] for d in observations) for r in g);anyh=sum(any(r["variant_id"] in observations[d] for d in observations) for r in g)
  summary[era]={"requiredCards":len(g),"perDateAvailable":per,"perDateCoverage":{d:n/len(g) for d,n in per.items()},"allFourCards":all4,"allFourCoverage":all4/len(g),"anyHistoryCards":anyh,"missingAllHistoryCards":len(g)-anyh,"earliestReliableDate":"2026-05-31" if per.get("2026-05-31",0) else None}
 payload={"readOnly":True,"source":SOURCE,"conditionId":str(nm["id"]),"checkpointDates":[d.isoformat() for d in DATES],"selectedVariants":len(variants),"summary":summary,"observationIdentityHash":stable_json_hash({d:sorted(v) for d,v in observations.items()})};OUT.write_text(json.dumps(payload,indent=2),encoding="utf-8");OBS.write_text(json.dumps({"readOnly":True,"checkpointDates":payload["checkpointDates"],"observations":observations},indent=2),encoding="utf-8")
if __name__=="__main__":main()
