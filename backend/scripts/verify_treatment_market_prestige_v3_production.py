"""Verify dark V3 infrastructure after migration/candidate staging."""
from __future__ import annotations
import argparse,json
from backend.db.clients.supabase_client import supabase
from backend.db.services.treatment_market_prestige_v3_service import (
    BASELINE_VERSION,PRODUCTION_CONTRACT_HASH,build_candidate_payload,
    resolve_card_treatment_market_prestige,
)

def verify(*,database:bool=False)->dict:
    candidate=build_candidate_payload();checks={
      "candidate_integrity":candidate["run"]["expected_treatment_count"]==len(candidate["results"])==38,
      "universe_count":len(candidate["universes"])==11,
      "available_treatments":sum(x["final_availability_status"]=="AVAILABLE" for x in candidate["results"])==23,
      "available_universes":sum(x["final_availability_status"]=="AVAILABLE" for x in candidate["universes"])==4,
      "null_score_contract":all((x["magnitude_score"] is not None)==(x["final_availability_status"]=="AVAILABLE") for x in candidate["results"]),
      "contract_hash":candidate["run"]["production_contract_hash"]==PRODUCTION_CONTRACT_HASH,
      "baseline_version":candidate["run"]["baseline_version"]==BASELINE_VERSION,
    };db={"checked":False,"schema":False,"candidateRuns":None,"approvedRuns":None,"latestApprovedRows":None}
    if database:
        db["checked"]=True
        runs=list(supabase.table("treatment_market_prestige_publication_runs").select("id,approval_status").execute().data or [])
        db.update({"schema":True,"candidateRuns":sum(x["approval_status"]=="candidate" for x in runs),"approvedRuns":sum(x["approval_status"]=="approved" for x in runs),"latestApprovedRows":len(supabase.table("latest_approved_treatment_market_prestige").select("id").execute().data or [])})
        checks["first_candidate_unapproved"]=db["approvedRuns"]==0
    return {"passed":all(checks.values()),"checks":checks,"database":db,"candidateHash":candidate["candidateHash"],"productionBehavior":"dark; resolver remains NO_APPROVED_RUN until explicit approval"}

def main()->None:
    p=argparse.ArgumentParser();p.add_argument("--database",action="store_true");a=p.parse_args();result=verify(database=a.database);print(json.dumps(result,indent=2));raise SystemExit(0 if result["passed"] else 1)
if __name__=="__main__":main()
