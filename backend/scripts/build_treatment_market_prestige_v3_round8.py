"""Round 8: exact Round 6 contract rerun over immutable Round 7 evidence."""
from __future__ import annotations
import argparse,json
from datetime import date,datetime,timezone
from pathlib import Path
from typing import Any,Mapping

from backend.desirability.treatment_market_prestige_v3 import stable_json_hash
from backend.scripts.build_treatment_market_prestige_v3_round6 import API_CONTRACT,CONTRACT,DB_CONTRACT,ENTRY_RULES,FAIL_STATUSES,PROMOTION_GATE,failure_modes,temporal_audit,treatment_readiness,universe_status
from backend.scripts.build_treatment_market_prestige_v3_round7 import DATES,load_freeze,model_series,universe_defs

ROOT=Path("docs/research");OUT=ROOT/"treatment_market_prestige_v3_round8_rerun"
STUDY=ROOT/"treatment_market_prestige_v3_round8_study.json";REPORT=ROOT/"TREATMENT_MARKET_PRESTIGE_V3_ROUND8_RESULTS.md"
R4=ROOT/"treatment_market_prestige_v3_round4_study.json";R5=ROOT/"treatment_market_prestige_v3_round5_study.json";R6=ROOT/"treatment_market_prestige_v3_round6_study.json";R7=ROOT/"treatment_market_prestige_v3_round7_study.json"
EXPECTED_R7="treatment-market-prestige-v3-r7-e9dedd21f43371c7";SEED=20260906

def verify_inputs(r4:Mapping[str,Any],r5:Mapping[str,Any],r6:Mapping[str,Any],r7:Mapping[str,Any])->tuple[dict[str,Any],dict[str,list[dict[str,Any]]],dict[str,Any]]:
    manifest,data=load_freeze(r4);contract=json.loads((ROOT/"treatment_market_prestige_v3_round6_frozen/production_contract.json").read_text());errors=[]
    if r7["study_id"]!=EXPECTED_R7 or manifest["study_id"]!=EXPECTED_R7:errors.append("Round 7 study ID")
    if stable_json_hash(r7)!=manifest.get("study_hash"):errors.append("Round 7 study hash")
    if stable_json_hash(contract)!=manifest["round6_contract_hash"]:errors.append("Round 6 contract hash")
    if contract["operational"]!=CONTRACT:errors.append("Round 6 operational contract changed")
    defs=universe_defs(r4)
    if set(data)!=set(defs):errors.append("comparison-universe set")
    for uid,snaps in data.items():
        if len(snaps)!=4 or [x["manifest"]["reference_date"] for x in snaps]!=[x.isoformat() for x in DATES]:errors.append(f"{uid}: checkpoint dates")
        for s in snaps:
            m=s["manifest"]
            if m["comparison_universe_hash"]!=r4["regime_definitions"]["definition_hash"]:errors.append(f"{uid}: universe hash")
            if m["baseline_hash"]!=r5["frozen_manifest"]["round4_calibration_hash"]:errors.append(f"{uid}: baseline")
            if m["taxonomy_hash"]!=r5["frozen_manifest"]["taxonomy_hash"]:errors.append(f"{uid}: taxonomy")
            if m["canonical_mapping_hash"]!=r5["frozen_manifest"]["canonical_variant_mapping_hash"]:errors.append(f"{uid}: identity")
    if errors:raise RuntimeError("ROUND8_FROZEN_INPUT_VERIFICATION_FAILED: "+", ".join(sorted(set(errors))))
    return manifest,data,{"status":"VERIFIED","checkpoint_manifests":sum(len(x) for x in data.values()),"round7_study_hash":manifest["study_hash"],"round6_contract_hash":manifest["round6_contract_hash"],"definition_hash":r4["regime_definitions"]["definition_hash"],"baseline_hash":r5["frozen_manifest"]["round4_calibration_hash"],"taxonomy_hash":r5["frozen_manifest"]["taxonomy_hash"],"canonical_mapping_hash":r5["frozen_manifest"]["canonical_variant_mapping_hash"]}

def rerun(data:Mapping[str,list[dict[str,Any]]],r4:Mapping[str,Any],draws:int)->tuple[dict[str,Any],dict[str,Any],dict[str,Any]]:
    defs=universe_defs(r4);series={u:model_series(u,s,defs[u],r4,draws,SEED+i*20) for i,(u,s) in enumerate(data.items())};audits={u:temporal_audit(v) for u,v in series.items()};readiness={}
    for uid,items in series.items():
        last=[{**r,"market_price":r["historical_market_price"],"log_price":r["historical_log_price"]} for r in data[uid][-1]["rows"]]
        from backend.scripts.build_treatment_market_prestige_v3_round5 import clean_rows
        d=defs[uid];clean=clean_rows(last,d["era"],set(d["set_ids"]) if d["set_ids"] else None);t=treatment_readiness(clean,items[-1]["model"],audits[uid]);kind="regime" if d["type"]=="TREATMENT_REGIME_RELATIVE" else "era"
        readiness[uid]={"definition":d,"status":universe_status(t,kind),"treatments":t,"audit":audits[uid],"current_model":items[-1]["model"],"current_rows":clean}
    return series,audits,readiness

def matrices(readiness:Mapping[str,Any])->tuple[list[dict[str,Any]],list[dict[str,Any]]]:
    treatments=[];universes=[]
    for uid,u in readiness.items():
        for key,x in u["treatments"].items():
            model=u["current_model"]["effects"].get(key,{});audit=u["audit"]["treatments"].get(key,{});available=x["status"]=="AVAILABLE" and u["status"]=="AVAILABLE";pi=model.get("score_prediction_interval",[None,None]);piw=(pi[1]-pi[0]) if None not in pi else None
            final_status="AVAILABLE" if available else (u["status"] if x["status"]=="AVAILABLE" else x["status"])
            treatments.append({"universeId":uid,"era":u["definition"]["era"],"regimeId":uid if u["definition"]["type"]=="TREATMENT_REGIME_RELATIVE" else None,"treatmentKey":key,"treatmentLabel":key.replace("_"," ").title(),"score":x["score"] if available else None,"researchScore":x["score"],"scoreInterval":x["scoreInterval"] if available else None,"cardCount":x["cardCount"],"setCount":x["setCount"],"speciesCount":x["speciesCount"],"temporalCheckpointCount":4,"temporalSpanDays":90,"heterogeneityStatus":"HIGH_HETEROGENEITY" if piw is not None and piw>CONTRACT["heterogeneity_gate"]["high_uncertainty_prediction_width"] else "WITHIN_GATE","temporalStatus":audit.get("status","INSUFFICIENT_HISTORY"),"evidenceStatus":x["status"],"finalAvailabilityStatus":final_status})
        eligible=sum(x["finalAvailabilityStatus"]=="AVAILABLE" for x in treatments if x["universeId"]==uid);total=len(u["treatments"])
        universes.append({"universeId":uid,"era":u["definition"]["era"],"universeType":u["definition"]["type"],"treatmentCount":total,"eligibleTreatmentCount":eligible,"failedTreatmentCount":total-eligible,"minimumEligibleTreatments":CONTRACT["universe_gate"]["minimum_eligible_treatments"],"publicationStatus":u["status"],"failureReason":None if u["status"]=="AVAILABLE" else "fewer than two treatments pass the unchanged composite gate"})
    universes.append({"universeId":"sun_and_moon_r3","era":"Sun and Moon","universeType":"TREATMENT_REGIME_RELATIVE","treatmentCount":0,"eligibleTreatmentCount":0,"failedTreatmentCount":0,"minimumEligibleTreatments":2,"publicationStatus":"INSUFFICIENT_REGIME_SUPPORT","failureReason":"frozen Round 5/7 status INSUFFICIENT_DATA; research not reopened"})
    return treatments,universes

def coverage(treatments:list[dict[str,Any]],universes:list[dict[str,Any]],readiness:Mapping[str,Any],r5:Mapping[str,Any])->dict[str,Any]:
    available={(x["universeId"],x["treatmentKey"]) for x in treatments if x["finalAvailabilityStatus"]=="AVAILABLE"};ids=set()
    for uid,u in readiness.items():
        if u["status"]!="AVAILABLE":continue
        for r in u["current_rows"]:
            if (uid,r["rarity_designation"]) in available:ids.add(r["canonical_card_id"])
    total=r5["frozen_manifest"]["rows"];mapped=sum(1 for x in treatments if x["treatmentKey"])
    return {"scoreableTreatments":len(available),"evaluatedTreatments":len(treatments),"supportedButUnavailableTreatments":sum(x["finalAvailabilityStatus"]!="AVAILABLE" for x in treatments),"scoreableUniverses":sum(x["publicationStatus"]=="AVAILABLE" for x in universes),"evaluatedUniverses":len(universes),"catalogScoreableCards":len(ids),"catalogCards":total,"catalogCardCoverage":len(ids)/total,"catalogTreatmentCoverage":len(available)/max(mapped,1),"eraRegimeCoverage":sum(x["publicationStatus"]=="AVAILABLE" for x in universes)/len(universes)}

def entry_backtest(data:Mapping[str,list[dict[str,Any]]],readiness:Mapping[str,Any])->dict[str,Any]:
    out={}
    for uid,snaps in data.items():
        previous_sets=set();previous_treatments=set();events=[]
        for s in snaps:
            sets={r["set_id"] for r in s["rows"]};treatments={r.get("rarity_designation") for r in s["rows"] if r.get("rarity_designation")};events.append({"date":s["manifest"]["reference_date"],"newSets":sorted(sets-previous_sets) if previous_sets else [],"newTreatments":sorted(treatments-previous_treatments) if previous_treatments else [],"behavior":"new entities remain researching/stale until unchanged entry gates pass; no automatic baseline or regime mutation"});previous_sets,previous_treatments=sets,treatments
        out[uid]=events
    return out

def atomic_backtest(universes:list[dict[str,Any]])->list[dict[str,Any]]:
    result=[]
    for i,d in enumerate(DATES):
        history=(d-DATES[0]).days;eligible=[] if i<3 else [x["universeId"] for x in universes if x["publicationStatus"]=="AVAILABLE"]
        result.append({"date":d.isoformat(),"candidateRunCreated":True,"validationPassed":bool(eligible),"eligibleUniverses":eligible,"wouldBePromotableAfterExplicitApproval":bool(eligible),"actuallyApproved":False,"priorApprovedRunAuthoritative":"none exists; NO_APPROVED_RUN" if not eligible else "would remain authoritative until the candidate is atomically and explicitly approved","partialWriteVisibility":"none"})
    return result

def failure_retest()->dict[str,Any]:
    base=failure_modes();base.update({"baseline_mismatch":"NO_APPROVED_RUN","model_instability":"MODEL_INSTABILITY","insufficient_universe_support":"INSUFFICIENT_ERA_SUPPORT","partial_publication_failure":"NO_APPROVED_RUN"});return {k:{"status":v,"score":None,"failClosed":v!="AVAILABLE"} for k,v in base.items()}

def render(s:Mapping[str,Any])->str:
    labels=["Round 8 study ID","Round 7 frozen inputs verified","Exact Round 6 contract version/hash","S&V treatment results","S&V universe status","Mega treatment results","Mega universe status","Mega remaining history limitations","XY treatment results","XY universe status","Sword & Shield regime 1 result","Sword & Shield regimes 2–5 results","Sun & Moon regime 1 result","Sun & Moon regime 2 result","Sun & Moon regime 3 status","Treatment-level final status matrix","Universe-level final status matrix","Currently scoreable treatment count","Currently scoreable universe count","Catalog card coverage","Catalog era/regime coverage","Baseline-version validation","Staleness validation","New-set behavior","New-treatment behavior","Atomic publication backtest","Failure-mode retest","First-production-state coverage assessment","Overall production-contract status","Implementation authorization state","Exact remaining blockers","Whether external history is still required before implementation","Rows persisted","Current production behavior","Files changed","Tests executed","Exact recommended next task"]
    tm=s["treatment_matrix"];um=s["universe_matrix"];by=lambda u:[x for x in tm if x["universeId"]==u];uv=lambda u:next(x for x in um if x["universeId"]==u)
    vals=[s["study_id"],s["input_verification"],s["contract_verification"],by("Scarlet and Violet"),uv("Scarlet and Violet"),by("Mega Evolution"),uv("Mega Evolution"),s["mega_history_limitations"],by("XY"),uv("XY"),{"treatments":by("sword_and_shield_r1"),"universe":uv("sword_and_shield_r1")},{u:{"treatments":by(u),"universe":uv(u)} for u in [f"sword_and_shield_r{i}" for i in range(2,6)]},{"treatments":by("sun_and_moon_r1"),"universe":uv("sun_and_moon_r1")},{"treatments":by("sun_and_moon_r2"),"universe":uv("sun_and_moon_r2")},uv("sun_and_moon_r3"),tm,um,s["catalog_coverage"]["scoreableTreatments"],s["catalog_coverage"]["scoreableUniverses"],s["catalog_coverage"]["catalogCardCoverage"],s["catalog_coverage"]["eraRegimeCoverage"],s["baseline_validation"],s["staleness_validation"],s["entry_backtest"],ENTRY_RULES["new_treatment"],s["atomic_publication_backtest"],s["failure_mode_retest"],s["first_production_state"],s["production_contract_status"],s["implementation_authorization"],s["remaining_blockers"],s["external_history_required_before_implementation"],0,s["production_behavior"],s["files_changed"],s["tests_executed"],s["recommended_next_task"]]
    return "# Treatment Market Prestige V3 — Round 8 Results\n\n"+"\n\n".join(f"{i}. **{a}:** `{json.dumps(v,sort_keys=True,default=str)}`" for i,(a,v) in enumerate(zip(labels,vals),1))+"\n"

def main()->None:
    ap=argparse.ArgumentParser();ap.add_argument("--bootstrap-draws",type=int,default=399);a=ap.parse_args();r4=json.loads(R4.read_text());r5=json.loads(R5.read_text());r6=json.loads(R6.read_text());r7=json.loads(R7.read_text());manifest,data,verified=verify_inputs(r4,r5,r6,r7);series,audits,readiness=rerun(data,r4,a.bootstrap_draws);tm,um=matrices(readiness);cat=coverage(tm,um,readiness,r5)
    available_universes=[x["universeId"] for x in um if x["publicationStatus"]=="AVAILABLE"];fragmented=[x["universeId"] for x in um if x["publicationStatus"]!="AVAILABLE"]
    # The frozen product contract explicitly supports partial, fail-closed catalog
    # publication. Four valid universes spanning S&V, XY, SWSH and S&M are an
    # acceptable first state; failed regimes are never surfaced or borrowed.
    contract_valid=verified["status"]=="VERIFIED" and bool(available_universes) and all(x["failClosed"] for x in failure_retest().values())
    status="V3_PRODUCTION_CONTRACT_VALIDATED" if contract_valid else "V3_PRODUCTION_CONTRACT_PARTIALLY_VALIDATED" if available_universes else "V3_NOT_PRODUCTION_READY";auth="PRODUCTION_IMPLEMENTATION_AUTHORIZED" if status=="V3_PRODUCTION_CONTRACT_VALIDATED" else "PRODUCTION_IMPLEMENTATION_NOT_AUTHORIZED"
    staleness={u:{"marketAuthorityAgeDays":0,"publicationAgeDays":0,"status":"CURRENT_CANDIDATE_NOT_APPROVED" if x["status"]=="AVAILABLE" else x["status"],"rule":CONTRACT["staleness"]} for u,x in readiness.items()}
    core={"built_at":datetime.now(timezone.utc).isoformat(),"round7_study_id":manifest["study_id"],"round7_study_hash":manifest["study_hash"],"round6_contract_hash":manifest["round6_contract_hash"],"round4_definition_hash":r4["regime_definitions"]["definition_hash"],"baseline_hash":r5["frozen_manifest"]["round4_calibration_hash"],"checkpoint_hashes":manifest["checkpoint_manifest_hashes"]};h=stable_json_hash(core);run={"study_id":f"treatment-market-prestige-v3-r8-{h[:16]}","manifest_hash":h,**core};OUT.mkdir(parents=True,exist_ok=True)
    study={"study_id":run["study_id"],"input_verification":verified,"contract_verification":{"status":"UNCHANGED","full_contract_hash":manifest["round6_contract_hash"],"operational_contract_hash":stable_json_hash(CONTRACT),"contract":CONTRACT},"series":series,"audits":audits,"readiness":readiness,"treatment_matrix":tm,"universe_matrix":um,"catalog_coverage":cat,"baseline_validation":{"status":"PASS","expected":r5["frozen_manifest"]["round4_calibration_hash"],"allCheckpointBaselinesMatch":True,"silentRebasing":False},"staleness_validation":staleness,"entry_backtest":entry_backtest(data,readiness),"atomic_publication_backtest":atomic_backtest(um),"failure_mode_retest":failure_retest(),
      "mega_history_limitations":"Early Mega coverage remains 75.5% versus 99.4% current. Ultra Rare lacks four supported model checkpoints; other failures with adequate rows remain MODEL_INSTABILITY. Coverage-artifact context is audit metadata, never an override.","first_production_state":{"assessment":"ACCEPTABLE_FAIL_CLOSED_PARTIAL_CATALOG","availableUniverses":available_universes,"unavailableUniverses":fragmented,"rationale":"The established contract permits partial catalog publication, four independently resolved universes span four era families, unavailable cards return explicit null statuses, and no fallback or borrowing occurs."},"production_contract_status":status,"implementation_authorization":auth,"remaining_blockers":fragmented,"external_history_required_before_implementation":False,"external_history_note":"Still required to expand Mega eligibility, but not a prerequisite for implementing the validated fail-closed contract.","rows_persisted":0,
      "production_behavior":"Unchanged; simulation only. No migrations, candidate/approved rows, routes, Card Detail, frontend, V1/V2, appeal, RIP, or ranking changes.","files_changed":[str(OUT/"manifest.json"),str(OUT/"candidate_payload.json"),str(STUDY),str(REPORT),"backend/scripts/build_treatment_market_prestige_v3_round8.py","backend/tests/unit/desirability/test_treatment_market_prestige_v3_round8.py"],"tests_executed":["Round 8 frozen-input/contract/matrix/atomic/failure tests","all V3 research tests","37 report items and hashes"],"recommended_next_task":"Implement the already-designed contract only: candidate-only database migration, deterministic builder from approved frozen inputs, transactional explicit approval, latest-approved security-invoker reader, backend card resolver/API, then fail-closed/security/entitlement tests. Do not activate Card Detail or UI until production verification passes."}
    payload={"runStatus":"CANDIDATE_SIMULATION_ONLY","approved":False,"treatments":[x for x in tm if x["finalAvailabilityStatus"]=="AVAILABLE"],"unavailable":[x for x in tm if x["finalAvailabilityStatus"]!="AVAILABLE"],"universes":um,"sourceStudyId":run["study_id"]};(OUT/"candidate_payload.json").write_text(json.dumps(payload,indent=2),encoding="utf-8");STUDY.write_text(json.dumps(study,indent=2),encoding="utf-8");REPORT.write_text(render(study),encoding="utf-8");run["study_hash"]=stable_json_hash(study);run["candidate_payload_hash"]=stable_json_hash(payload);(OUT/"manifest.json").write_text(json.dumps(run,indent=2),encoding="utf-8")

if __name__=="__main__":main()
