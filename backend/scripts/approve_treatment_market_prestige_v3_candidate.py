"""Explicit approval entry point. Never invoked by candidate builds."""
from __future__ import annotations
import argparse,json
from backend.db.services.treatment_market_prestige_v3_service import approve_candidate
def main()->None:
    p=argparse.ArgumentParser();p.add_argument("run_id");p.add_argument("--actor",required=True);p.add_argument("--metadata-json",default="{}");a=p.parse_args();print(approve_candidate(a.run_id,approval_actor=a.actor,approval_metadata=json.loads(a.metadata_json)))
if __name__=="__main__":main()
