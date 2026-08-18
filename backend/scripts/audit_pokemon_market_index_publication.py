from __future__ import annotations
import argparse, json, math, sys
from pathlib import Path
REPO_ROOT=Path(__file__).resolve().parents[2]
if str(REPO_ROOT) not in sys.path: sys.path.insert(0,str(REPO_ROOT))
from backend.db.services.pokemon_market_index_service import build_market_index_history, build_market_overview, read_index_history
from backend.scripts.pokemon_snapshot_builders import get_client

def audit(client, market_date):
    expected=[row for row in build_market_index_history(client,through_date=market_date) if row["market_date"]==market_date]
    persisted=[row for row in read_index_history(client,through_date=market_date) if str(row["market_date"])[:10]==market_date]
    failures=[]
    by_key={row["index_key"]:row for row in persisted}
    for row in expected:
        actual=by_key.get(row["index_key"])
        if not actual: failures.append(f"missing index_key={row['index_key']}"); continue
        for field in ("set_count","card_count","cohort_fingerprint","source_generation_fingerprint"):
            if str(actual.get(field))!=str(row.get(field)): failures.append(f"{row['index_key']} {field} mismatch")
        if abs(float(actual["basket_value"])-float(row["basket_value"]))>.005: failures.append(f"{row['index_key']} basket mismatch")
        if not math.isfinite(float(actual["normalized_index_value"])) or float(actual["normalized_index_value"])<=0: failures.append(f"{row['index_key']} invalid index")
    overview=build_market_overview(read_index_history(client,through_date=market_date),market_date=market_date)
    latest=list(client.table("pokemon_explore_set_value_snapshot_latest").select("market_date,payload_json").eq("tcg","pokemon").eq("scope","market").limit(1).execute().data or [])
    public=(latest[0].get("payload_json") or {}).get("marketOverview") if latest else None
    if not public or public.get("marketDate")!=market_date: failures.append("public marketOverview date mismatch")
    if public and public.get("coverage")!=overview.get("coverage"): failures.append("public marketOverview coverage mismatch")
    return {"status":"passed" if not failures else "failed","marketDate":market_date,"indexRows":len(persisted),"failures":failures}

def main():
    p=argparse.ArgumentParser(); p.add_argument("--market-date",required=True); a=p.parse_args(); result=audit(get_client(),a.market_date); print(json.dumps(result,indent=2,sort_keys=True)); raise SystemExit(0 if result["status"]=="passed" else 1)
if __name__=="__main__": main()
