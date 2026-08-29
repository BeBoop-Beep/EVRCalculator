"""Build a deterministic V3 candidate; persistence is explicit and never approval."""
from __future__ import annotations
import argparse,json
from pathlib import Path
from backend.db.services.treatment_market_prestige_v3_service import build_candidate_payload,stage_candidate

def main()->None:
    p=argparse.ArgumentParser();p.add_argument("--output",default="docs/research/treatment_market_prestige_v3_production_candidate.json");p.add_argument("--persist-candidate",action="store_true");a=p.parse_args()
    payload=build_candidate_payload();Path(a.output).write_text(json.dumps(payload,indent=2),encoding="utf-8")
    print(json.dumps({"candidateHash":payload["candidateHash"],"treatments":len(payload["results"]),"universes":len(payload["universes"]),"persistedRunId":stage_candidate(payload) if a.persist_candidate else None,"approved":False}))
if __name__=="__main__":main()
