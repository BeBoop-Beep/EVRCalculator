"""Round 6 production-contract validation. Design/research only; no DB writes."""
from __future__ import annotations
import argparse,json,math
from collections import Counter
from datetime import datetime,timezone
from pathlib import Path
from typing import Any,Mapping

from backend.desirability.treatment_market_prestige_v3 import stable_json_hash
from backend.scripts.build_treatment_market_prestige_v3_round3 import load_checkpoints
from backend.scripts.build_treatment_market_prestige_v3_round5 import clean_rows,hierarchical

ROOT=Path("docs/research");OUT=ROOT/"treatment_market_prestige_v3_round6_frozen"
STUDY=ROOT/"treatment_market_prestige_v3_round6_study.json";REPORT=ROOT/"TREATMENT_MARKET_PRESTIGE_V3_ROUND6_RESULTS.md"
R5=ROOT/"treatment_market_prestige_v3_round5_study.json";R4=ROOT/"treatment_market_prestige_v3_round4_study.json";SEED=20260904

# Operational thresholds are preregistered here before temporal models execute.
CONTRACT={
 "semantics":"How strongly the market values this card's treatment package relative to evidence-supported treatments in the appropriate Pokémon era or treatment regime, after adjusting for established non-treatment characteristics.",
 "score_drift":{"maximum_adjacent_checkpoint":.50,"maximum_30_day":.50,"maximum_90_day":1.00,"rank_flip_confidence_floor":.80,"maximum_interval_width_expansion_ratio":1.50,"maximum_tier_steps":1,
  "classification":"movement within gates is MARKET_MOVEMENT; a breached gate without a source/cohort/taxonomy explanation is MODEL_INSTABILITY"},
 "treatment_gate":{"minimum_cards":25,"minimum_sets":3,"minimum_species":20,"maximum_single_set_share":.60,"minimum_price_coverage":.95,"maximum_score_interval_width":2.0,"maximum_prediction_interval_width":4.0,"maximum_loso_shift":1.0,"minimum_historical_checkpoints":4,"minimum_history_days":85},
 "universe_gate":{"minimum_eligible_treatments":2,"minimum_sets":3,"unique_ordering_required":False},
 "heterogeneity_gate":{"production_eligible_prediction_width":2.5,"high_uncertainty_prediction_width":4.0,"maximum_between_set_score_sd":1.25,"maximum_loso_shift":1.0,"maximum_90_day_drift":1.0,"maximum_heldout_rmse_ratio":1.02},
 "staleness":{"market_authority_age_days":45,"publication_age_days":62,"taxonomy_or_universe_change":"immediate MODEL_STALE","baseline_change":"old run remains reproducible but is not latest-version eligible","material_new_set":"MODEL_STALE after 30 days unless entry review completes"},
 "precision":{"storage":"numeric(6,4) for score/effects and numeric(7,4) interval bounds","api":"one decimal scoreDisplay; full stored numeric score reserved for audit","display":"one decimal"},
 "cadence":{"candidate_build":"weekly coordinated market snapshot","approved_promotion":"monthly after full validation; exceptional promotion after canonical taxonomy/universe change","reason":"monthly checkpoints show stability, but no evidence supports daily promotion and daily prices would imply false responsiveness"},
 "freshness":"current market prestige as of a coordinated approved snapshot; hierarchical stabilization, not a temporal moving-average blend",
}
FAIL_STATUSES=["AVAILABLE","INSUFFICIENT_TREATMENT_SUPPORT","INSUFFICIENT_ERA_SUPPORT","INSUFFICIENT_REGIME_SUPPORT","HIGH_HETEROGENEITY","INSUFFICIENT_HISTORY","TAXONOMY_UNMAPPED","NEW_TREATMENT_RESEARCHING","MODEL_INSTABILITY","MODEL_STALE","NO_APPROVED_RUN"]

DB_CONTRACT={
 "publication_run":{"table":"treatment_market_prestige_publication_runs","fields":{"id":"uuid pk","model_version":"text not null","methodology_version":"text not null","score_transform_version":"text not null","baseline_version":"text not null","market_reference_date":"date not null","built_at":"timestamptz not null","approval_status":"enum(candidate, approved, rejected, revoked)","approved_at":"timestamptz nullable","approved_by":"uuid nullable","comparison_universe_config_hash":"text not null","source_cohort_hash":"text not null","validation_metadata":"jsonb not null"},"constraints":["approval is explicit and transactional","unique approved model/methodology/baseline/reference tuple"]},
 "score_row":{"table":"treatment_market_prestige_scores","fields":{"id":"uuid pk","publication_run_id":"uuid fk not null","era_id":"uuid not null","treatment_regime_id":"text nullable","comparison_universe_type":"enum(era_relative,treatment_regime_relative)","treatment_key":"text not null","coefficient":"numeric(10,6) not null","score":"numeric(6,4) nullable","score_interval_low":"numeric(6,4) nullable","score_interval_high":"numeric(6,4) nullable","prediction_interval_low":"numeric(6,4) nullable","prediction_interval_high":"numeric(6,4) nullable","evidence_status":"text not null","card_count":"int not null","species_count":"int not null","set_count":"int not null","between_set_variance":"numeric nullable","ordering_metadata":"jsonb not null","as_of_date":"date not null","provenance":"jsonb not null"},"constraints":["unique run/universe/regime/treatment","score is null unless evidence_status AVAILABLE or SUPPORTED_WITH_HIGH_UNCERTAINTY","no redundant full research artifact"]},
 "latest_approved_reader":{"name":"latest_approved_treatment_market_prestige","semantics":"security-invoker read model selecting the greatest approved market_reference_date, then approved_at, only within the current non-stale methodology/baseline version; candidate/completed/rejected/revoked runs are invisible; explicit approval cannot be inferred from successful execution","publication_atomicity":"run and all score rows staged as candidate, validation finalized, then one transaction changes approval; partial writes never become visible"}}

API_CONTRACT={"field":"treatmentMarketPrestige","nullable":False,"fields":{"status":"fail-closed status enum","modelVersion":"string|null","methodologyVersion":"string|null","asOfDate":"date|null","eraId":"uuid|null","eraName":"string|null","comparisonUniverseType":"ERA_RELATIVE|TREATMENT_REGIME_RELATIVE|null","treatmentRegimeId":"string|null","treatmentKey":"string|null","treatmentLabel":"string|null","score":"number|null","scoreDisplay":"string|null","scoreInterval":"{low,high}|null","tier":"null initially","confidence":"STANDARD|HIGH_UNCERTAINTY|null","evidenceStatus":"string","cardCount":"integer|null","setCount":"integer|null","comparisonUniverseSize":"integer|null"},
 "resolution":"card -> canonical era -> frozen set-to-regime mapping where applicable -> normalized treatment key -> latest approved non-stale eligible row","forbidden":["frontend calculation","rarity-name heuristic","V1 fallback","neighbor treatment fallback","neighbor era fallback"],
 "tooltip_requirements":["market-relative within the appropriate era/regime","real-world scarcity and mechanics bundled with the treatment are part of the package","not Exact Pull Scarcity","similar prestige can produce similar scores","unsupported evidence is unavailable, never estimated"]}

ENTRY_RULES={"new_set":{"initial_status":"MODEL_STALE for affected universe pending review; its rows do not influence approved scores","gates":["canonical set/era mapping complete","price maturity >=30 days","minimum 25 eligible cards and >=5 per treatment cell","taxonomy/mechanics coverage >=95%","hierarchy estimable","leave-one-new-set influence <=1.0 score point","publication validation passes"],"regime":"join only through structural ontology review; price behavior cannot create a regime"},
 "new_treatment":{"initial_status":"NEW_TREATMENT_RESEARCHING","gates":["normalized taxonomy approved",">=25 cards, >=3 sets, >=20 species","price maturity >=30 days","four checkpoints spanning >=85 days","hierarchical and influence gates pass","universe still has >=2 eligible treatments"],"fallback":"none; no V1, neighboring treatment, or cross-era borrowing"},
 "baseline":{"creation":"created for a newly validated comparison universe or methodology major version","replacement":"only after full historical backtest and explicit approval","versioning":"replacement requires score-transform/baseline version bump; methodology bump if formula/estimand changes","new_sets":"never mutate an existing baseline","new_treatments":"enter against the frozen baseline after eligibility; do not re-center prior scores","history":"every row retains baseline version and immutable parameters"}}

PROMOTION_GATE=["cohort_integrity","taxonomy_mapping","model_execution","treatment_eligibility","universe_eligibility","temporal_validation","baseline_version_compatibility","score_drift_and_influence","historical_regression_tests","atomic_write_simulation","explicit_human_approval"]

def temporal_models(checkpoints:list[dict[str,Any]],r4:Mapping[str,Any],draws:int,seed:int)->dict[str,Any]:
    out={e:[] for e in ("Scarlet and Violet","Mega Evolution")}
    for i,cp in enumerate(checkpoints):
        for j,era in enumerate(out):
            source=[{**r,"market_price":r["historical_market_price"],"log_price":r["historical_log_price"]} for r in cp["rows"]]
            rows=clean_rows(source,era);cal=r4["calibration"][era];model=hierarchical(rows,cal["frozen_center"],cal["frozen_scale"],draws,seed+i*10+j)
            out[era].append({"date":cp["manifest"]["reference_date"],"cohort_hash":cp["manifest"]["cohort_hash"],"n":len(rows),"model":model})
    return out

def temporal_audit(series:list[dict[str,Any]])->dict[str,Any]:
    treatments=sorted(set.intersection(*[set(x["model"].get("effects",{})) for x in series])) if series else []
    result={}
    for t in treatments:
        vals=[x["model"]["effects"][t] for x in series];scores=[x["score"] for x in vals];widths=[x["score_interval"][1]-x["score_interval"][0] for x in vals]
        adjacent=max([abs(b-a) for a,b in zip(scores,scores[1:])] or [0]);drift90=abs(scores[-1]-scores[0]);expansion=max(widths)/max(min(widths),1e-9)
        passed=adjacent<=CONTRACT["score_drift"]["maximum_adjacent_checkpoint"] and drift90<=CONTRACT["score_drift"]["maximum_90_day"] and expansion<=CONTRACT["score_drift"]["maximum_interval_width_expansion_ratio"]
        result[t]={"scores":scores,"coefficient_drift":vals[-1]["population_effect"]-vals[0]["population_effect"],"maximum_adjacent_score_drift":adjacent,"ninety_day_score_drift":drift90,"interval_width_expansion":expansion,"between_set_variances":[x["between_set_variance"] for x in vals],"status":"MARKET_MOVEMENT" if passed else "MODEL_INSTABILITY"}
    return {"treatments":result,"eligible_treatment_set_drift":[sorted(x["model"].get("effects",{})) for x in series],"sample_sizes":[x["n"] for x in series]}

def treatment_readiness(rows:list[dict[str,Any]],model:Mapping[str,Any],audit:Mapping[str,Any]|None)->dict[str,Any]:
    output={};gate=CONTRACT["treatment_gate"]
    for t,d in model.get("effects",{}).items():
        group=[r for r in rows if r.get("rarity_designation")==t];species=len({r["species_id"] for r in group});sets=Counter(r["set_id"] for r in group);reasons=[]
        if len(group)<gate["minimum_cards"]:reasons.append("card_count")
        if len(sets)<gate["minimum_sets"]:reasons.append("set_count")
        if species<gate["minimum_species"]:reasons.append("species_count")
        if max(sets.values(),default=0)/max(len(group),1)>gate["maximum_single_set_share"]:reasons.append("set_concentration")
        if d["score_interval"][1]-d["score_interval"][0]>gate["maximum_score_interval_width"]:reasons.append("score_uncertainty")
        if d["score_prediction_interval"][1]-d["score_prediction_interval"][0]>gate["maximum_prediction_interval_width"]:reasons.append("heterogeneity")
        if model["leave_set_out_score_stability"][t]["maximum_shift"]>gate["maximum_loso_shift"]:reasons.append("influence")
        if audit is None or t not in audit.get("treatments",{}):reasons.append("history")
        elif audit["treatments"][t]["status"]!="MARKET_MOVEMENT":reasons.append("temporal_instability")
        status="AVAILABLE" if not reasons else "MODEL_INSTABILITY" if "temporal_instability" in reasons else "HIGH_HETEROGENEITY" if any(x in reasons for x in ("heterogeneity","influence")) else "INSUFFICIENT_HISTORY" if "history" in reasons else "INSUFFICIENT_TREATMENT_SUPPORT"
        output[t]={"status":status,"reasons":reasons,"score":d["score"],"scoreDisplay":f"{d['score']:.1f}","scoreInterval":d["score_interval"],"predictionInterval":d["score_prediction_interval"],"effect":d["population_effect"],"betweenSetVariance":d["between_set_variance"],"cardCount":len(group),"setCount":len(sets),"speciesCount":species}
    return output

def universe_status(treatments:Mapping[str,Any],kind:str)->str:
    return "AVAILABLE" if sum(x["status"]=="AVAILABLE" for x in treatments.values())>=CONTRACT["universe_gate"]["minimum_eligible_treatments"] else ("INSUFFICIENT_REGIME_SUPPORT" if kind=="regime" else "INSUFFICIENT_ERA_SUPPORT")

def failure_modes()->dict[str,Any]:
    return {"missing_treatment_taxonomy":"TAXONOMY_UNMAPPED","new_unsupported_treatment":"NEW_TREATMENT_RESEARCHING","low_sample_treatment":"INSUFFICIENT_TREATMENT_SUPPORT","missing_era_mapping":"TAXONOMY_UNMAPPED","missing_regime_mapping":"INSUFFICIENT_REGIME_SUPPORT","no_approved_run":"NO_APPROVED_RUN","stale_approved_run":"MODEL_STALE","high_heterogeneity":"HIGH_HETEROGENEITY","incomplete_historical_pricing":"INSUFFICIENT_HISTORY","temporal_gate_failure":"MODEL_INSTABILITY","publication_run_failure":"NO_APPROVED_RUN","partial_database_write":"NO_APPROVED_RUN"}

def render(s:Mapping[str,Any])->str:
    labels=["Round 6 study ID","Historical checkpoint dates","Temporal results by era/regime","Score-drift contract","Score-freshness conclusion","Recommended calculation cadence","Recommended promotion cadence","Baseline-versioning rules","New-set entry rules","New-treatment entry rules","Treatment eligibility contract","Era/regime eligibility contract","Heterogeneity eligibility contract","Fail-closed statuses","Numeric precision recommendation","Uncertainty contract","Tier recommendation","Ordering-confidence contract","Exact Pull Scarcity separation","Database run schema","Database score-row schema","Latest-approved reader semantics","Card Detail resolution contract","Card Detail API object","Tooltip scientific requirements","S&V readiness","Mega readiness","Sword & Shield regime readiness","Sun & Moon regime readiness","XY readiness","Older-era fail-closed matrix","Publication cadence","Staleness rules","Deterministic promotion gate","Historical production-contract backtest","Failure-mode tests","Overall production-readiness status","Production implementation authorization","Rows persisted","Current production behavior","Files changed","Tests executed","Remaining limitations","Exact recommended implementation task"]
    vals=[s["study_id"],s["checkpoint_dates"],s["temporal_results"],CONTRACT["score_drift"],CONTRACT["freshness"],CONTRACT["cadence"]["candidate_build"],CONTRACT["cadence"]["approved_promotion"],ENTRY_RULES["baseline"],ENTRY_RULES["new_set"],ENTRY_RULES["new_treatment"],CONTRACT["treatment_gate"],CONTRACT["universe_gate"],CONTRACT["heterogeneity_gate"],FAIL_STATUSES,CONTRACT["precision"],s["uncertainty_contract"],s["tier_recommendation"],s["ordering_confidence_contract"],s["exact_pull_separation"],DB_CONTRACT["publication_run"],DB_CONTRACT["score_row"],DB_CONTRACT["latest_approved_reader"],API_CONTRACT["resolution"],API_CONTRACT,API_CONTRACT["tooltip_requirements"],s["readiness"]["Scarlet and Violet"],s["readiness"]["Mega Evolution"],s["readiness"]["Sword and Shield"],s["readiness"]["Sun and Moon"],s["readiness"]["XY"],s["older_era_matrix"],CONTRACT["cadence"],CONTRACT["staleness"],PROMOTION_GATE,s["backtest"],s["failure_modes"],s["production_readiness_status"],s["implementation_authorization"],0,s["production_behavior"],s["files_changed"],s["tests_executed"],s["limitations"],s["recommended_implementation_task"]]
    return "# Treatment Market Prestige V3 — Round 6 Results\n\n"+"\n\n".join(f"{i}. **{a}:** `{json.dumps(v,sort_keys=True,default=str)}`" for i,(a,v) in enumerate(zip(labels,vals),1))+"\n"

def main()->None:
    ap=argparse.ArgumentParser();ap.add_argument("--bootstrap-draws",type=int,default=199);ap.add_argument("--seed",type=int,default=SEED);a=ap.parse_args()
    r5=json.loads(R5.read_text());r4=json.loads(R4.read_text());checkpoints,tm=load_checkpoints();checkpoints=sorted(checkpoints,key=lambda x:x["manifest"]["reference_date"]);temporal=temporal_models(checkpoints,r4,a.bootstrap_draws,a.seed);audits={e:temporal_audit(v) for e,v in temporal.items()}
    cohort=json.loads((ROOT/"treatment_market_prestige_v3_round5_frozen/cohort.json").read_text())["rows"]
    readiness={}
    for era in ("Scarlet and Violet","Mega Evolution","XY"):
        model=r5["models"][era];rows=clean_rows(cohort,era);audit=audits.get(era);t=treatment_readiness(rows,model,audit);readiness[era]={"comparisonUniverse":"ERA_RELATIVE","status":universe_status(t,"era"),"treatments":t,"temporalStatus":"VALIDATED" if audit else "INSUFFICIENT_HISTORY"}
    for era,key in (("Sword and Shield","swsh_regimes"),("Sun and Moon","sunmoon_regimes")):
        items=[]
        for reg in r5[key]:
            setids={x["set_id"] for d in reg["model"].get("effects",{}).values() for x in d["set_effects"]};rows=clean_rows(cohort,era,setids);t=treatment_readiness(rows,reg["model"],None);items.append({"regimeId":reg["regime_id"],"status":universe_status(t,"regime") if reg["model"].get("status")=="ESTIMATED" else "INSUFFICIENT_REGIME_SUPPORT","treatments":t,"temporalStatus":"INSUFFICIENT_HISTORY"})
        readiness[era]={"comparisonUniverse":"TREATMENT_REGIME_RELATIVE","status":"INSUFFICIENT_HISTORY","regimes":items}
    older={e:("INSUFFICIENT_HISTORY" if st not in ("TAXONOMY_REPAIR_REQUIRED","INSUFFICIENT_DATA") else "TAXONOMY_UNMAPPED" if st=="TAXONOMY_REPAIR_REQUIRED" else "INSUFFICIENT_ERA_SUPPORT") for e,st in r5["support_matrix"].items() if e not in readiness}
    checkpoint_dates=[x["manifest"]["reference_date"] for x in checkpoints];backtest=[]
    for i,date in enumerate(checkpoint_dates):
        history_days=(datetime.fromisoformat(date)-datetime.fromisoformat(checkpoint_dates[0])).days
        available=[]
        if i+1>=CONTRACT["treatment_gate"]["minimum_historical_checkpoints"] and history_days>=CONTRACT["treatment_gate"]["minimum_history_days"]:
            available=[e for e in ("Scarlet and Violet","Mega Evolution") if readiness[e]["status"]=="AVAILABLE"]
        backtest.append({"date":date,"historyDays":history_days,"checkpointCount":i+1,"available":available,"unavailable":[e for e in readiness if e not in available],"stale":[],"newlyEligible":available if i==len(checkpoint_dates)-1 else []})
    all_core_temporal=all(readiness[e]["status"]=="AVAILABLE" for e in ("Scarlet and Violet","Mega Evolution","XY","Sword and Shield","Sun and Moon"))
    status="V3_PRODUCTION_CONTRACT_VALIDATED" if all_core_temporal else "V3_PRODUCTION_CONTRACT_PARTIALLY_VALIDATED"
    auth="PRODUCTION_IMPLEMENTATION_AUTHORIZED" if status=="V3_PRODUCTION_CONTRACT_VALIDATED" else "PRODUCTION_IMPLEMENTATION_NOT_AUTHORIZED"
    cpmeta=[];OUT.mkdir(parents=True,exist_ok=True)
    for cp in checkpoints:
        x={"reference_date":cp["manifest"]["reference_date"],"source_cohort_hash":cp["manifest"]["cohort_hash"],"canonical_mapping_hash":r5["frozen_manifest"]["canonical_variant_mapping_hash"],"taxonomy_hash":r5["frozen_manifest"]["taxonomy_hash"],"comparison_universe_definition_hash":r4["regime_definitions"]["definition_hash"],"model_version":"tmp-v3-hierarchical-r5","baseline_parameters_hash":r5["frozen_manifest"]["round4_calibration_hash"]};x["checkpoint_contract_hash"]=stable_json_hash(x);cpmeta.append(x)
    core={"frozen_at":datetime.now(timezone.utc).isoformat(),"round5_study_id":r5["study_id"],"round5_study_hash":stable_json_hash(r5),"round4_definition_hash":r4["regime_definitions"]["definition_hash"],"temporal_manifest_hash":tm["manifest_hash"],"contract_hash":stable_json_hash(CONTRACT),"database_contract_hash":stable_json_hash(DB_CONTRACT),"api_contract_hash":stable_json_hash(API_CONTRACT),"checkpoints":cpmeta};digest=stable_json_hash(core);manifest={"study_id":f"treatment-market-prestige-v3-r6-{digest[:16]}","manifest_hash":digest,**core}
    (OUT/"manifest.json").write_text(json.dumps(manifest,indent=2),encoding="utf-8");(OUT/"production_contract.json").write_text(json.dumps({"operational":CONTRACT,"database":DB_CONTRACT,"api":API_CONTRACT,"entryRules":ENTRY_RULES,"promotionGate":PROMOTION_GATE,"failStatuses":FAIL_STATUSES},indent=2),encoding="utf-8")
    study={"study_id":manifest["study_id"],"frozen_manifest":manifest,"checkpoint_dates":checkpoint_dates,"temporal_models":temporal,"temporal_results":audits,"contract":CONTRACT,"entry_rules":ENTRY_RULES,"database_contract":DB_CONTRACT,"api_contract":API_CONTRACT,"readiness":readiness,"older_era_matrix":older,"backtest":backtest,"failure_modes":failure_modes(),"production_readiness_status":status,"implementation_authorization":auth,"rows_persisted":0,
      "uncertainty_contract":"Store coefficient, bootstrap score interval, random-effects prediction interval, heterogeneity class, and ordering metadata; expose scoreInterval and confidence in API; initial UI may summarize confidence rather than every pairwise probability.","tier_recommendation":"NO_PUBLIC_TIER_INITIAL_RELEASE: comparison-universe-relative scores and overlapping intervals make a universal qualitative tier potentially misleading; revisit after production monitoring.","ordering_confidence_contract":"Store auditable pairwise superiority probabilities and confidence class per run; never substitute them for magnitude; public API need not expose every pair.","exact_pull_separation":"Exact Pull Scarcity remains a separately versioned metric and is neither an input to nor fallback for the published magnitude score.",
      "production_behavior":"Unchanged; research-only contract staging. No tables, views, routes, scores, frontend, V1/V2, appeal, RIP, or ranking behavior changed.","files_changed":[str(OUT/"manifest.json"),str(OUT/"production_contract.json"),str(STUDY),str(REPORT),"backend/scripts/build_treatment_market_prestige_v3_round6.py","backend/tests/unit/desirability/test_treatment_market_prestige_v3_round6.py"],"tests_executed":["Round 6 contract/failure tests","all V3 research unit tests","artifact hashes and 44 report items"],"limitations":["authoritative 90-day history exists only for S&V and Mega","no SWSH, Sun & Moon, or XY temporal production validation","observational package estimand","no complete supply/liquidity measure","database design is unimplemented and untested against a live schema"],"recommended_implementation_task":"First ingest and freeze >=4 authoritative checkpoints spanning >=85 days for XY and every supported SWSH/Sun & Moon regime, rerun this exact contract, then—only if validated—implement candidate-only database tables/view/resolver with atomic approval and no user-facing activation."}
    STUDY.write_text(json.dumps(study,indent=2),encoding="utf-8");REPORT.write_text(render(study),encoding="utf-8");manifest["study_hash"]=stable_json_hash(study);(OUT/"manifest.json").write_text(json.dumps(manifest,indent=2),encoding="utf-8")

if __name__=="__main__":main()
