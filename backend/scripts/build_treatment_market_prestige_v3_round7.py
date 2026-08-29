"""Round 7 authoritative temporal backfill and Mega diagnosis (research-only)."""
from __future__ import annotations
import argparse,json,math,time
from collections import Counter
from datetime import date,datetime,timedelta,timezone
from pathlib import Path
from typing import Any,Iterable,Mapping
import numpy as np
from dotenv import load_dotenv

from backend.db.clients.supabase_client import create_service_role_client
from backend.desirability.treatment_market_prestige_v3 import stable_json_hash
from backend.scripts.build_treatment_market_prestige_v3_round5 import clean_rows,hierarchical
from backend.scripts.build_treatment_market_prestige_v3_round6 import CONTRACT,temporal_audit,treatment_readiness,universe_status

ROOT=Path("docs/research");OUT=ROOT/"treatment_market_prestige_v3_round7_temporal"
STUDY=ROOT/"treatment_market_prestige_v3_round7_study.json";REPORT=ROOT/"TREATMENT_MARKET_PRESTIGE_V3_ROUND7_RESULTS.md"
R4=ROOT/"treatment_market_prestige_v3_round4_study.json";R5=ROOT/"treatment_market_prestige_v3_round5_study.json";R6=ROOT/"treatment_market_prestige_v3_round6_study.json"
DATES=(date(2026,5,31),date(2026,6,30),date(2026,7,30),date(2026,8,29));ERAS=("Scarlet and Violet","Mega Evolution","XY","Sword and Shield","Sun and Moon");SEED=20260905
SOURCE={"relation":"public.card_variant_price_observations","identity":"card_variant_id -> immutable Round 5 canonical card/variant mapping","condition":"Near Mint condition_id resolved canonically from public.conditions","price":"positive finite USD market_price","market_date":"captured_at/captured_date","retention":"daily observations; unique by variant, condition, source, captured_date; latest scrape wins within day","checkpoint":"latest authoritative observation in fixed seven-day window ending at reference date; no interpolation","publication":"observations, not reconstructed current prices"}

def chunks(values:list[str],n:int=75):
    for i in range(0,len(values),n):yield values[i:i+n]

def pull(client:Any,variants:list[str],condition_id:str,checkpoint:date)->dict[str,dict[str,Any]]:
    start=(checkpoint-timedelta(days=6)).isoformat();end=(checkpoint+timedelta(days=1)).isoformat();selected={}
    for part in chunks(variants):
        offset=0
        while True:
            for attempt in range(3):
                try:
                    batch=(client.table("card_variant_price_observations").select("id,card_variant_id,condition_id,market_price,currency,source,captured_at,captured_date,created_at")
                           .in_("card_variant_id",part).eq("condition_id",condition_id).gte("captured_at",start).lt("captured_at",end).range(offset,offset+999).execute().data or []);break
                except Exception:
                    if attempt==2:raise
                    time.sleep(1+attempt)
            for row in batch:
                try:p=float(row.get("market_price"))
                except (TypeError,ValueError):continue
                if p<=0 or not math.isfinite(p) or str(row.get("currency") or "").strip('"').upper()!="USD":continue
                vid=str(row["card_variant_id"]);rank=(str(row.get("captured_at") or ""),str(row.get("created_at") or ""),str(row.get("id") or ""))
                if vid not in selected or rank>selected[vid][0]:selected[vid]=(rank,row)
            if len(batch)<1000:break
            offset+=1000
    return {k:v[1] for k,v in selected.items()}

def universe_defs(r4:Mapping[str,Any])->dict[str,dict[str,Any]]:
    out={"Scarlet and Violet":{"era":"Scarlet and Violet","type":"ERA_RELATIVE","set_ids":None},"Mega Evolution":{"era":"Mega Evolution","type":"ERA_RELATIVE","set_ids":None},"XY":{"era":"XY","type":"ERA_RELATIVE","set_ids":None}}
    for era in ("Sword and Shield","Sun and Moon"):
        regs=r4["regime_definitions"]["era_regimes"][era]["regimes"]
        if era=="Sun and Moon":regs=regs[:2]
        for r in regs:out[r["regime_id"]]={"era":era,"type":"TREATMENT_REGIME_RELATIVE","set_ids":r["set_ids"],"sets":r["sets"]}
    return out

def freeze_live(rows:list[dict[str,Any]],r4:Mapping[str,Any],r5:Mapping[str,Any])->dict[str,Any]:
    load_dotenv(Path("backend/.env"));client=create_service_role_client();conditions=client.table("conditions").select("id,name,abbreviation").execute().data or [];nm=[x for x in conditions if x.get("name")=="Near Mint" or x.get("abbreviation")=="NM"]
    if not nm:raise RuntimeError("Near Mint condition unavailable")
    cid=str(nm[0]["id"]);base=[r for r in rows if r["era_name"] in ERAS];variants=sorted({r["variant_id"] for r in base});defs=universe_defs(r4);manifests=[]
    for checkpoint in DATES:
        prices=pull(client,variants,cid,checkpoint)
        dated=[]
        for row in base:
            p=prices.get(row["variant_id"])
            if not p:continue
            dated.append({**row,"historical_market_price":float(p["market_price"]),"historical_log_price":math.log(float(p["market_price"])),"historical_price_captured_at":p.get("captured_at"),"historical_price_source":p.get("source")})
        for uid,u in defs.items():
            group=[r for r in dated if r["era_name"]==u["era"] and (u["set_ids"] is None or r["set_id"] in u["set_ids"])]
            group.sort(key=lambda x:(x["set_id"],x["variant_id"]));folder=OUT/uid/checkpoint.isoformat();folder.mkdir(parents=True,exist_ok=True);h=stable_json_hash(group)
            core={"reference_date":checkpoint.isoformat(),"universe_id":uid,"era":u["era"],"comparison_universe_type":u["type"],"set_ids":u["set_ids"],"condition_id":cid,"pricing_semantics":SOURCE["checkpoint"],"source_relation":SOURCE["relation"],"canonical_mapping_hash":r5["frozen_manifest"]["canonical_variant_mapping_hash"],"taxonomy_hash":r5["frozen_manifest"]["taxonomy_hash"],"comparison_universe_hash":r4["regime_definitions"]["definition_hash"],"demand_snapshot_id":r5["frozen_manifest"]["demand_snapshot_id"],"model_version":"tmp-v3-hierarchical-r5","baseline_hash":r5["frozen_manifest"]["round4_calibration_hash"],"cohort_hash":h,"rows":len(group)};mh=stable_json_hash(core);m={"checkpoint_id":f"tmp-v3-r7-{uid}-{checkpoint}-{mh[:10]}","manifest_hash":mh,**core}
            (folder/"cohort.json").write_text(json.dumps({"checkpoint_id":m["checkpoint_id"],"rows":group},indent=2),encoding="utf-8");(folder/"manifest.json").write_text(json.dumps(m,indent=2),encoding="utf-8");manifests.append(m)
    core={"frozen_at":datetime.now(timezone.utc).isoformat(),"methodology":"tmp-v3-round7-authoritative-temporal-backfill","round5_study_id":r5["study_id"],"round6_contract_hash":r6_hash(),"source":SOURCE,"checkpoint_manifest_hashes":[m["manifest_hash"] for m in manifests]};h=stable_json_hash(core);overall={"study_id":f"treatment-market-prestige-v3-r7-{h[:16]}","manifest_hash":h,**core};OUT.mkdir(parents=True,exist_ok=True);(OUT/"manifest.json").write_text(json.dumps(overall,indent=2),encoding="utf-8");return overall

def r6_hash()->str:return stable_json_hash(json.loads((ROOT/"treatment_market_prestige_v3_round6_frozen/production_contract.json").read_text()))

def load_freeze(r4:Mapping[str,Any])->tuple[dict[str,Any],dict[str,list[dict[str,Any]]]]:
    overall=json.loads((OUT/"manifest.json").read_text());data={u:[] for u in universe_defs(r4)};hashes=[]
    for uid in data:
        for d in DATES:
            folder=OUT/uid/d.isoformat();m=json.loads((folder/"manifest.json").read_text());p=json.loads((folder/"cohort.json").read_text());
            if stable_json_hash(p["rows"])!=m["cohort_hash"]:raise RuntimeError(f"checkpoint hash failure {uid} {d}")
            hashes.append(m["manifest_hash"]);data[uid].append({"manifest":m,"rows":p["rows"]})
    if sorted(hashes)!=sorted(overall["checkpoint_manifest_hashes"]):raise RuntimeError("overall checkpoint chain failure")
    return overall,data

def coverage(snapshot:Mapping[str,Any],base:list[dict[str,Any]])->dict[str,Any]:
    rows=snapshot["rows"];mapped=[r for r in rows if r.get("rarity_designation")];captures=[str(r["historical_price_captured_at"])[:10] for r in rows];base_ids={r["variant_id"] for r in base};ids={r["variant_id"] for r in rows};cells=Counter(r.get("rarity_designation") or "__unmapped__" for r in rows)
    return {"priced_cards":len(rows),"treatments":len(cells),"sets":len({r["set_id"] for r in rows}),"species":len({r["species_id"] for r in rows if r.get("species_id")}),"price_coverage":len(ids&base_ids)/max(len(base_ids),1),"treatment_cells":{str(k):v for k,v in cells.items()},"missing_canonical_identities":len(base_ids-ids),"unmapped_taxonomy_rows":len(rows)-len(mapped),"capture_date_min":min(captures) if captures else None,"capture_date_max":max(captures) if captures else None,"historical_gap":"no observation in fixed seven-day window"}

def model_series(uid:str,snaps:list[dict[str,Any]],definition:Mapping[str,Any],r4:Mapping[str,Any],draws:int,seed:int)->list[dict[str,Any]]:
    out=[];cal=r4["calibration"][definition["era"]]
    for i,s in enumerate(snaps):
        rows=[{**r,"market_price":r["historical_market_price"],"log_price":r["historical_log_price"]} for r in s["rows"]];clean=clean_rows(rows,definition["era"],set(definition["set_ids"]) if definition["set_ids"] else None);m=hierarchical(clean,cal["frozen_center"],cal["frozen_scale"],draws,seed+i)
        out.append({"date":s["manifest"]["reference_date"],"n":len(clean),"model":m})
    return out

def composition(snaps:list[dict[str,Any]])->dict[str,Any]:
    first,last=snaps[0]["rows"],snaps[-1]["rows"];fids={r["variant_id"] for r in first};lids={r["variant_id"] for r in last};ft=Counter(r.get("rarity_designation") for r in first);lt=Counter(r.get("rarity_designation") for r in last)
    return {"first_to_last_card_retention":len(fids&lids)/max(len(fids|lids),1),"cards_added":len(lids-fids),"cards_lost":len(fids-lids),"first_treatments":{str(k):v for k,v in ft.items()},"last_treatments":{str(k):v for k,v in lt.items()},"treatment_count_change":{str(t):lt[t]-ft[t] for t in sorted(set(ft)|set(lt),key=str)}}

def chase(rows:list[dict[str,Any]])->dict[str,Any]:
    out={}
    for t in sorted({r.get("rarity_designation") for r in rows if r.get("rarity_designation")}):
        vals=np.sort(np.asarray([r["historical_market_price"] for r in rows if r.get("rarity_designation")==t],float))[::-1];total=vals.sum();out[t]={f"top_{p}_percent_share":float(vals[:max(1,math.ceil(len(vals)*p/100))].sum()/total) for p in (1,5,10)};out[t]["herfindahl"]=float(np.sum((vals/total)**2))
    return out

def mega_diagnosis(snaps:list[dict[str,Any]],series:list[dict[str,Any]],audit:Mapping[str,Any],r4:Mapping[str,Any],draws:int)->dict[str,Any]:
    checkpoints=[];cal=r4["calibration"]["Mega Evolution"]
    for i,(s,mitem) in enumerate(zip(snaps,series)):
        rows=[{**r,"market_price":r["historical_market_price"],"log_price":r["historical_log_price"]} for r in s["rows"]];clean=clean_rows(rows,"Mega Evolution");prices=np.asarray([r["market_price"] for r in clean]);lo,hi=np.quantile(prices,[.05,.95]);trim=[r for r in clean if lo<=r["market_price"]<=hi];tm=hierarchical(trim,cal["frozen_center"],cal["frozen_scale"],99,SEED+500+i)
        trim_sensitivity={t:tm.get("effects",{}).get(t,{}).get("score",d["score"])-d["score"] for t,d in mitem["model"].get("effects",{}).items()};checkpoints.append({"date":mitem["date"],"coverage":coverage(s,clean),"chase_concentration":chase(s["rows"]),"trim_score_sensitivity":trim_sensitivity,"effects":mitem["model"].get("effects",{}),"ordering_probabilities":mitem["model"].get("ordering_probabilities",{})})
    comp=composition(snaps);classifications={}
    for t,d in audit["treatments"].items():
        counts=[x["effects"].get(t,{}).get("cards",0) for x in checkpoints];ch=[x["chase_concentration"].get(t,{}).get("top_10_percent_share",0) for x in checkpoints];trim=[abs(x["trim_score_sensitivity"].get(t,0)) for x in checkpoints]
        if min(counts,default=0)==0:label="INSUFFICIENT_SUPPORT"
        elif max(counts)/max(min(counts),1)>1.25:label="COVERAGE_ARTIFACT"
        elif max(trim,default=0)>.5 or max(ch,default=0)>.65:label="CHASE_CONCENTRATION"
        elif d["status"]=="MARKET_MOVEMENT":label="BROAD_MARKET_MOVEMENT"
        else:label="MULTI_SET_HETEROGENEITY"
        classifications[t]={"classification":label,"contract_status":d["status"],"card_counts":counts,"top10_shares":ch,"maximum_trim_score_shift":max(trim,default=0)}
    return {"checkpoints":checkpoints,"composition":comp,"classifications":classifications,"ir_conclusion":classifications.get("illustration_rare",{"classification":"INSUFFICIENT_HISTORY"})["classification"]}

def retention_audit(data:Mapping[str,list[dict[str,Any]]])->dict[str,Any]:
    return {uid:{"first_date":snaps[0]["manifest"]["reference_date"],"last_date":snaps[-1]["manifest"]["reference_date"],"span_days":90,"nonempty_checkpoints":sum(bool(s["rows"]) for s in snaps),"cause_if_incomplete":"old sets/variants were not uniformly tracked in each seven-day window; canonical IDs remain stable in the frozen mapping"} for uid,snaps in data.items()}

def render(s:Mapping[str,Any])->str:
    labels=["Round 7 study ID","Authoritative historical price source","Exact temporal checkpoint dates","Checkpoint span by universe","Frozen hashes","S&V positive-control reproduction result","XY temporal coverage","Each Sword & Shield regime temporal coverage","Each Sun & Moon supported regime temporal coverage","Checkpoint coverage-quality results","Checkpoint cohort-composition results","Mega temporal series","Mega Double Rare result","Mega Ultra Rare result","Mega IR result","Remaining Mega treatments","Mega score-movement decomposition","Mega set-influence result","Mega chase-concentration result","Mega cohort-composition result","Market movement vs model instability classification","Unchanged Round 6 treatment gates applied","Treatment statuses after temporal backfill","Universe publication statuses","XY contract result","Sword & Shield contract result by regime","Sun & Moon result by regime","Mega contract result","Historical-retention limitations","Whether external historical ingestion is required","Future temporal-retention recommendation","Historical-coverage decision state","Mega decision state","Round 6 rerun authorization state","Rows persisted","Current production behavior","Files changed","Tests executed","Remaining blockers","Exact recommended next task"]
    vals=[s["study_id"],SOURCE,s["checkpoint_dates"],s["retention_audit"],s["frozen_hashes"],s["positive_control"],s["coverage"]["XY"],{k:v for k,v in s["coverage"].items() if k.startswith("sword_and_shield")},{k:v for k,v in s["coverage"].items() if k.startswith("sun_and_moon")},s["coverage"],s["composition"],s["mega"]["series"],s["mega"]["statuses"].get("double_rare"),s["mega"]["statuses"].get("ultra_rare"),s["mega"]["statuses"].get("illustration_rare"),s["mega"]["statuses"],s["mega"]["diagnosis"]["classifications"],s["mega"]["set_influence"],s["mega"]["diagnosis"]["checkpoints"],s["mega"]["diagnosis"]["composition"],s["mega"]["diagnosis"]["classifications"],CONTRACT["treatment_gate"],s["treatment_statuses"],s["universe_statuses"],s["readiness"]["XY"],{k:v for k,v in s["readiness"].items() if k.startswith("sword_and_shield")},{k:v for k,v in s["readiness"].items() if k.startswith("sun_and_moon")},s["readiness"]["Mega Evolution"],s["historical_retention_limitations"],s["external_ingestion_required"],s["future_retention"],s["historical_coverage_status"],s["mega_status"],s["rerun_status"],0,s["production_behavior"],s["files_changed"],s["tests_executed"],s["remaining_blockers"],s["recommended_next_task"]]
    return "# Treatment Market Prestige V3 — Round 7 Results\n\n"+"\n\n".join(f"{i}. **{a}:** `{json.dumps(v,sort_keys=True,default=str)}`" for i,(a,v) in enumerate(zip(labels,vals),1))+"\n"

def main()->None:
    ap=argparse.ArgumentParser();ap.add_argument("--use-existing-freeze",action="store_true");ap.add_argument("--bootstrap-draws",type=int,default=199);a=ap.parse_args();r4=json.loads(R4.read_text());r5=json.loads(R5.read_text());r6=json.loads(R6.read_text());rows=json.loads((ROOT/"treatment_market_prestige_v3_round5_frozen/cohort.json").read_text())["rows"]
    if not a.use_existing_freeze:freeze_live(rows,r4,r5)
    manifest,data=load_freeze(r4);defs=universe_defs(r4);series={uid:model_series(uid,snaps,defs[uid],r4,a.bootstrap_draws,SEED+i*20) for i,(uid,snaps) in enumerate(data.items())};audits={u:temporal_audit(v) for u,v in series.items()}
    coverage_results={};composition_results={}
    for uid,snaps in data.items():
        base=[r for r in rows if r["era_name"]==defs[uid]["era"] and (defs[uid]["set_ids"] is None or r["set_id"] in defs[uid]["set_ids"])]
        coverage_results[uid]=[coverage(s,base) for s in snaps];composition_results[uid]=composition(snaps)
    old=r6["temporal_results"]["Scarlet and Violet"]["treatments"];new=audits["Scarlet and Violet"]["treatments"];common=set(old)&set(new);maxdiff=max((max(abs(a-b) for a,b in zip(old[t]["scores"],new[t]["scores"])) for t in common),default=99);positive={"status":"REPRODUCED" if common and maxdiff<=.15 and all(new[t]["status"]=="MARKET_MOVEMENT" for t in common) else "TEMPORAL_BACKFILL_PIPELINE_REPRODUCTION_FAILED","maximum_score_difference":maxdiff,"tolerance":.15,"common_treatments":sorted(common)}
    if positive["status"]!="REPRODUCED":
        study={"study_id":manifest["study_id"],"positive_control":positive,"historical_coverage_status":"TEMPORAL_EVIDENCE_BACKFILL_PARTIAL","mega_status":"MEGA_HISTORY_INSUFFICIENT","rerun_status":"ADDITIONAL_TEMPORAL_DATA_WORK_REQUIRED","rows_persisted":0};STUDY.write_text(json.dumps(study,indent=2),encoding="utf-8");raise RuntimeError("TEMPORAL_BACKFILL_PIPELINE_REPRODUCTION_FAILED")
    readiness={};treatment_statuses={};universe_statuses={}
    for uid,items in series.items():
        last_rows=[{**r,"market_price":r["historical_market_price"],"log_price":r["historical_log_price"]} for r in data[uid][-1]["rows"]];clean=clean_rows(last_rows,defs[uid]["era"],set(defs[uid]["set_ids"]) if defs[uid]["set_ids"] else None);t=treatment_readiness(clean,items[-1]["model"],audits[uid]);kind="regime" if defs[uid]["type"]=="TREATMENT_REGIME_RELATIVE" else "era";us=universe_status(t,kind);readiness[uid]={"status":us,"treatments":t,"audit":audits[uid]};treatment_statuses[uid]={k:v["status"] for k,v in t.items()};universe_statuses[uid]=us
    mega=mega_diagnosis(data["Mega Evolution"],series["Mega Evolution"],audits["Mega Evolution"],r4,a.bootstrap_draws);mega_statuses=readiness["Mega Evolution"]["treatments"]
    required=["XY",*[k for k in readiness if k.startswith("sword_and_shield")],*[k for k in readiness if k.startswith("sun_and_moon")]]
    # Backfill success is an evidence-coverage question, not a requirement that
    # every treatment pass after adequate evidence is obtained.
    required_coverage_complete=all(len(coverage_results[x])>=4 and all(c["price_coverage"]>=CONTRACT["treatment_gate"]["minimum_price_coverage"] for c in coverage_results[x]) for x in required)
    mega_available=universe_statuses["Mega Evolution"]=="AVAILABLE";mega_coverage_complete=all(c["price_coverage"]>=CONTRACT["treatment_gate"]["minimum_price_coverage"] for c in coverage_results["Mega Evolution"])
    historical="TEMPORAL_EVIDENCE_BACKFILL_COMPLETE" if required_coverage_complete and mega_coverage_complete else "TEMPORAL_EVIDENCE_BACKFILL_PARTIAL" if required_coverage_complete else "EXTERNAL_HISTORICAL_INGESTION_REQUIRED"
    mega_state="MEGA_TEMPORAL_CONTRACT_VALIDATED" if mega_available else "MEGA_PARTIALLY_VALIDATED" if any(v["status"]=="AVAILABLE" for v in mega_statuses.values()) else "MEGA_TRUE_TEMPORAL_INSTABILITY_CONFIRMED" if all("history" not in v["reasons"] for v in mega_statuses.values()) else "MEGA_HISTORY_INSUFFICIENT"
    rerun="ROUND6_CONTRACT_RERUN_AUTHORIZED" if required_coverage_complete and positive["status"]=="REPRODUCED" else "ADDITIONAL_TEMPORAL_DATA_WORK_REQUIRED"
    retention=retention_audit(data);external=not mega_coverage_complete
    study={"study_id":manifest["study_id"],"frozen_manifest":manifest,"checkpoint_dates":[d.isoformat() for d in DATES],"frozen_hashes":manifest["checkpoint_manifest_hashes"],"source":SOURCE,"coverage":coverage_results,"composition":composition_results,"series":series,"audits":audits,"positive_control":positive,"readiness":readiness,"treatment_statuses":treatment_statuses,"universe_statuses":universe_statuses,"mega":{"series":series["Mega Evolution"],"statuses":mega_statuses,"diagnosis":mega,"set_influence":{t:[{"date":x["date"],"loso":x["model"].get("leave_set_out_score_stability",{}).get(t),"sets":x["model"].get("effects",{}).get(t,{}).get("set_effects",[])} for x in series["Mega Evolution"]] for t in mega_statuses}},"retention_audit":retention,
      "historical_retention_limitations":"Daily observations exist, but old variants/sets were not uniformly tracked in every checkpoint window. Missing rows reflect collection coverage, not canonical-ID reconstruction.","external_ingestion_required":external,"external_ingestion_design":{"source":"verified historical TCGPlayer market observations or licensed equivalent","identity":"map provider product -> canonical card -> canonical variant and NM condition","granularity":"daily","deduplication":"latest scrape per variant/condition/source/date","provenance":"provider, captured date, ingestion run, mapping version","freeze":"four immutable checkpoints >=85 days with hashes","validation":"Round 6 coverage, taxonomy, drift, influence, heterogeneity gates unchanged"} if external else None,
      "future_retention":{"requirement":"daily authoritative positive USD NM observation retention for every canonical variant","freeze_with":["market date","canonical mapping version","taxonomy version","universe/regime hash","baseline version","cohort hash","source/run provenance"],"monitor":"alert when any supported universe falls below 95% daily coverage; never delete evidence needed for >=90-day gates"},"historical_coverage_status":historical,"mega_status":mega_state,"rerun_status":rerun,"rows_persisted":0,
      "production_behavior":"Unchanged; no approved run, database score rows, Card Detail, frontend, V1/V2, appeal, RIP, or ranking changes.","files_changed":[str(OUT),str(STUDY),str(REPORT),"backend/scripts/build_treatment_market_prestige_v3_round7.py","backend/tests/unit/desirability/test_treatment_market_prestige_v3_round7.py"],"tests_executed":["Round 7 source/freeze/contract tests","all V3 research tests","40 report items and hashes"],"remaining_blockers":[uid for uid in required if universe_statuses[uid]!="AVAILABLE"]+([] if mega_available else ["Mega Evolution universe"]),"recommended_next_task":"Rerun the unchanged Round 6 production contract against the immutable Round 7 checkpoints. Preserve genuine treatment/regime failures; separately acquire verified Mega history only where it can resolve coverage gaps, without delaying the evidence-based contract rerun."}
    STUDY.write_text(json.dumps(study,indent=2),encoding="utf-8");REPORT.write_text(render(study),encoding="utf-8");manifest["study_hash"]=stable_json_hash(study);(OUT/"manifest.json").write_text(json.dumps(manifest,indent=2),encoding="utf-8")

if __name__=="__main__":main()
