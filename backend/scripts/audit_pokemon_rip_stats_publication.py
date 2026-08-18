from __future__ import annotations
import argparse, json, math, sys
from pathlib import Path
REPO_ROOT=Path(__file__).resolve().parents[2]
if str(REPO_ROOT) not in sys.path: sys.path.insert(0,str(REPO_ROOT))
from backend.db.services.opening_simulation_gate import evaluate_opening_simulation_freshness
from backend.db.services.pack_outcome_artifact_service import load_pack_outcome_artifact
from backend.db.services.pokemon_rip_stats_service import read_latest_pokemon_rip_stats
from backend.domain.pokemon.rip_stats import deterministic_fingerprint
from backend.scripts.pokemon_snapshot_builders import get_client

def audit(client, market_date):
    failures=[]; latest=read_latest_pokemon_rip_stats(client); payload=latest.get("payload_json") or {}; population=payload.get("population") or {}
    if str(latest.get("market_date"))[:10]!=market_date: failures.append("latest public market date mismatch")
    gate=evaluate_opening_simulation_freshness(client,market_date=market_date)
    if not gate.ok: failures.append("authoritative simulation gate is not current")
    masters=list(client.table("pokemon_rip_stats_snapshots").select("id,eligible_cohort_count,total_source_outcome_count,source_run_fingerprint,payload_json").eq("market_date",market_date).limit(1).execute().data or [])
    if not masters: failures.append("historical master missing"); return {"status":"failed","marketDate":market_date,"failures":failures}
    master=masters[0]; members=list(client.table("pokemon_rip_stats_snapshot_sets").select("*").eq("snapshot_id",master["id"]).execute().data or [])
    if len(members)!=int(master["eligible_cohort_count"]): failures.append("constituent count mismatch")
    provenance=[]; total=0
    authoritative={str(s.set_id):str(s.calculation_run_id) for s in gate.statuses if s.calculation_run_id}
    for row in members:
        if str(row.get("source_market_date"))[:10]!=market_date: failures.append(f"{row.get('set_id')} source date mismatch")
        if authoritative.get(str(row.get("set_id")))!=str(row.get("calculation_run_id")): failures.append(f"{row.get('set_id')} run is not authoritative")
        try: artifact=load_pack_outcome_artifact(client,row["calculation_run_id"])
        except Exception as exc: failures.append(f"{row.get('set_id')} artifact invalid: {exc}"); continue
        if artifact.metadata["raw_sha256"]!=row.get("artifact_sha256") or int(artifact.metadata["outcome_count"])!=int(row.get("artifact_outcome_count")): failures.append(f"{row.get('set_id')} artifact provenance mismatch")
        total+=int(row["artifact_outcome_count"])
        provenance.append({"set_id":str(row["set_id"]),"calculation_run_id":str(row["calculation_run_id"]),"artifact_sha256":row["artifact_sha256"],"artifact_outcome_count":int(row["artifact_outcome_count"]),"pack_cost":float(row["pack_cost"]),"market_date":market_date})
    fp=deterministic_fingerprint(provenance)
    if fp!=master["source_run_fingerprint"] or fp!=latest["source_run_fingerprint"]: failures.append("source fingerprint mismatch")
    if total!=int(master["total_source_outcome_count"]): failures.append("total outcomes mismatch")
    economics=payload.get("packEconomics") or {}; typical=payload.get("typicalOpening") or {}; upside=payload.get("upside") or {}; downside=payload.get("downside") or {}; one=payload.get("onePackPerSet") or {}; entertainment=payload.get("entertainmentCost") or {}
    if not (0<=float(economics.get("chanceToBeatCost",-1))<=1): failures.append("chanceToBeatCost out of range")
    if not (float(typical.get("value",0))<=float(upside.get("p95Value",-1))<=float(upside.get("p99Value",-1))): failures.append("dollar quantiles unordered")
    if not (float(typical.get("retention",0))<=float(upside.get("p95Retention",-1))<=float(upside.get("p99Retention",-1))): failures.append("retention quantiles unordered")
    if abs(float(one.get("totalPackCost",0))-float(one.get("totalExpectedValue",0))-float(one.get("expectedEntertainmentCost",0)))>.005: failures.append("onePackPerSet identity mismatch")
    if abs(float(entertainment.get("expectedCostRatio",0))-(1-float(economics.get("expectedRetention",0))))>1e-9: failures.append("Entertainment Cost ratio mismatch")
    return {"status":"passed" if not failures else "failed","marketDate":market_date,"setCount":len(members),"totalOutcomes":total,"sourceRunFingerprint":fp,"failures":failures}

def main():
    p=argparse.ArgumentParser(); p.add_argument("--market-date",required=True); a=p.parse_args(); result=audit(get_client(),a.market_date); print(json.dumps(result,indent=2,sort_keys=True)); raise SystemExit(0 if result["status"]=="passed" else 1)
if __name__=="__main__": main()
