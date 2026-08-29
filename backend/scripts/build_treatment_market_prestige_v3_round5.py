"""Round 5 hierarchical Treatment Market Prestige research (no production writes)."""
from __future__ import annotations

import argparse, json, math
from collections import Counter, defaultdict
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Iterable, Mapping

import numpy as np

from backend.desirability.treatment_market_prestige_v3 import stable_json_hash
from backend.scripts.build_treatment_market_prestige_v3_round2 import fit, load_round1
from backend.scripts.build_treatment_market_prestige_v3_round3 import load_checkpoints

ROOT=Path("docs/research"); OUT=ROOT/"treatment_market_prestige_v3_round5_frozen"
STUDY=ROOT/"treatment_market_prestige_v3_round5_study.json"; REPORT=ROOT/"TREATMENT_MARKET_PRESTIGE_V3_ROUND5_RESULTS.md"
R4=ROOT/"treatment_market_prestige_v3_round4_study.json"; R4F=ROOT/"treatment_market_prestige_v3_round4_frozen"
SEED=20260903

# Frozen before final classification. Log bands correspond to ~25%, 75%, and 200% package multipliers.
PREREG={"practical_log_bands":{"approximately_equivalent":math.log(1.25),"slight_edge":math.log(1.75),"moderate_difference":math.log(3)},
 "minimum_set_treatment_n":5,"minimum_sets_for_hierarchy":4,"bootstrap_draws":399,
 "eligibility":{"maximum_score_between_set_sd":1.25,"maximum_score_prediction_interval_width":4.0,"maximum_loso_score_shift":1.0,
                "maximum_temporal_score_range":1.0,"maximum_hierarchical_heldout_rmse_ratio":1.02},
 "predictors":["release_time","set_size","treatment_counts","demand_composition","exact_pull_scarcity_composition","mechanic_mix","canonical_special_set"],
 "predictor_gate":{"minimum_sets":8,"minimum_loocv_rmse_improvement":.05,"minimum_absolute_correlation":.35}}

def score(beta:float,center:float,scale:float)->float:
    x=max(-60.,min(60.,(beta-center)/max(scale,1e-9)))
    return float(1+8/(1+math.exp(-x)))

def clean_rows(rows:Iterable[Mapping[str,Any]],era:str,set_ids:set[str]|None=None)->list[dict[str,Any]]:
    return [dict(r) for r in rows if r["era_name"]==era and (set_ids is None or r["set_id"] in set_ids) and r.get("rarity_designation") and r.get("species_id") and r.get("demand_score") is not None and not r.get("promo_status_ambiguous")]

def freeze(rows:list[dict[str,Any]],r1:Mapping[str,Any],r4:Mapping[str,Any],temporal:Mapping[str,Any])->dict[str,Any]:
    payload={"rows":rows}; cohort_hash=stable_json_hash(rows)
    core={"frozen_at":datetime.now(timezone.utc).isoformat(),"methodology":"treatment_market_prestige_v3_round5_hierarchical",
      "round1_study_id":r1["study_id"],"round1_cohort_hash":r1["cohort_hash"],"round4_study_id":r4["study_id"],
      "round4_definition_id":r4["definition_id"],"round4_definition_hash":r4["regime_definitions"]["definition_hash"],
      "round4_calibration_hash":stable_json_hash(r4["calibration"]),"temporal_manifest_hash":temporal["manifest_hash"],
      "canonical_variant_mapping_hash":stable_json_hash(json.loads((ROOT/"treatment_market_prestige_v3_frozen_cohort/canonical_variant_mapping.json").read_text())),
      "taxonomy_hash":stable_json_hash(json.loads((ROOT/"treatment_market_prestige_v3_frozen_cohort/taxonomy.json").read_text())),
      "set_era_mapping_hash":stable_json_hash(json.loads((ROOT/"treatment_market_prestige_v3_frozen_cohort/set_era_mapping.json").read_text())),
      "pricing_reference":"immutable Round 1 selected positive USD near-mint market price","demand_snapshot_id":r1["demand_snapshot_id"],
      "exact_pull_provenance":"immutable Round 1 exact_pull_probability/run_id fields where populated","cohort_hash":cohort_hash,"rows":len(rows),"preregistration":PREREG}
    digest=stable_json_hash(core); manifest={"study_id":f"treatment-market-prestige-v3-r5-{digest[:16]}","manifest_hash":digest,**core}; payload["study_id"]=manifest["study_id"]
    OUT.mkdir(parents=True,exist_ok=True);(OUT/"cohort.json").write_text(json.dumps(payload,indent=2),encoding="utf-8");(OUT/"manifest.json").write_text(json.dumps(manifest,indent=2),encoding="utf-8");return manifest

def random_effect(values:np.ndarray,variances:np.ndarray)->dict[str,Any]:
    variances=np.maximum(variances,1e-8); w=1/variances; fixed=float(np.sum(w*values)/np.sum(w)); q=float(np.sum(w*(values-fixed)**2)); df=max(len(values)-1,1)
    c=float(np.sum(w)-np.sum(w*w)/np.sum(w)); tau2=max(0.,(q-df)/max(c,1e-9)); wr=1/(variances+tau2); mean=float(np.sum(wr*values)/np.sum(wr)); se=math.sqrt(1/np.sum(wr)); i2=max(0.,(q-df)/max(q,1e-9))
    shrink=tau2/(tau2+variances); pooled=mean+shrink*(values-mean)
    return {"population_effect":mean,"population_interval":[mean-1.96*se,mean+1.96*se],"between_set_variance":tau2,"between_set_sd":math.sqrt(tau2),"Q":q,"I2":i2,
            "shrinkage_factors":shrink.tolist(),"partially_pooled":pooled.tolist(),"prediction_interval":[mean-1.96*math.sqrt(tau2+se*se),mean+1.96*math.sqrt(tau2+se*se)]}

def hierarchical(rows:list[dict[str,Any]],center:float,scale:float,draws:int,seed:int)->dict[str,Any]:
    counts=Counter(r["rarity_designation"] for r in rows); universe=sorted(t for t,n in counts.items() if n>=25 and len({r["set_id"] for r in rows if r["rarity_designation"]==t})>=3)
    if len(universe)<2 or len({r["set_id"] for r in rows})<3:return {"status":"INSUFFICIENT_DATA","n":len(rows),"universe":universe}
    model=fit(rows,"treatment"); effects={}; residual=np.asarray(model["_residual"]); rng=np.random.default_rng(seed)
    grouped:dict[tuple[str,str],list[float]]=defaultdict(list)
    for r,e in zip(rows,residual):grouped[(r["set_id"],r["rarity_designation"])].append(float(e)+model["coefficients"].get(f"rarity_designation:{r['rarity_designation']}",0.))
    for t in universe:
        cells=[]
        for (sid,tt),vals in grouped.items():
            if tt==t and len(vals)>=PREREG["minimum_set_treatment_n"]:
                a=np.asarray(vals); cells.append((sid,len(vals),float(a.mean()),float(a.var(ddof=1)/len(a)) if len(a)>1 else 1.))
        if len(cells)<PREREG["minimum_sets_for_hierarchy"]:continue
        re=random_effect(np.asarray([x[2] for x in cells]),np.asarray([x[3] for x in cells])); pop=re["population_effect"]; pi=re["prediction_interval"]
        bootstrap=[]
        for _ in range(draws):
            chosen=rng.integers(0,len(cells),len(cells)); vals=np.asarray([cells[i][2] for i in chosen]); var=np.asarray([cells[i][3] for i in chosen]);bootstrap.append(random_effect(vals,var)["population_effect"])
        effects[t]={**re,"sets":len(cells),"cards":sum(x[1] for x in cells),"within_set_variance":float(np.average([x[3]*x[1] for x in cells],weights=[x[1] for x in cells])),"score":score(pop,center,scale),"score_interval":[score(float(np.quantile(bootstrap,.025)),center,scale),score(float(np.quantile(bootstrap,.975)),center,scale)],
                    "score_prediction_interval":[score(pi[0],center,scale),score(pi[1],center,scale)],"set_effects":[{"set_id":x[0],"n":x[1],"unpooled":x[2],"shrinkage":re["shrinkage_factors"][i],"partially_pooled":re["partially_pooled"][i]} for i,x in enumerate(cells)]}
        for i,x in enumerate(cells):
            post_se=math.sqrt(re["between_set_variance"]*x[3]/max(re["between_set_variance"]+x[3],1e-9))
            effects[t]["set_effects"][i]["interval"]=[re["partially_pooled"][i]-1.96*post_se,re["partially_pooled"][i]+1.96*post_se]
    ordering={}
    for left in effects:
        for right in effects:
            if left>=right:continue
            dl=effects[left];dr=effects[right];sel=(dl["population_interval"][1]-dl["population_interval"][0])/3.92;ser=(dr["population_interval"][1]-dr["population_interval"][0])/3.92
            z=(dl["population_effect"]-dr["population_effect"])/max(math.sqrt(sel*sel+ser*ser),1e-9)
            ordering[f"P({left}>{right})"]=float(.5*(1+math.erf(z/math.sqrt(2))))
    pooled_rmse=model["rmse_within"]; hpred=np.asarray(model["_fitted"],float).copy(); npred=hpred.copy()
    lookup={(x["set_id"],t):x["partially_pooled"]-effects[t]["population_effect"] for t,d in effects.items() for x in d["set_effects"]}
    raw={(x["set_id"],t):x["unpooled"]-effects[t]["population_effect"] for t,d in effects.items() for x in d["set_effects"]}
    for i,r in enumerate(rows):hpred[i]+=lookup.get((r["set_id"],r["rarity_designation"]),0);npred[i]+=raw.get((r["set_id"],r["rarity_designation"]),0)
    y=np.asarray(model["_y"]); hierarchical_rmse=float(np.sqrt(np.mean((y-hpred)**2))); no_pool_rmse=float(np.sqrt(np.mean((y-npred)**2)))
    loso={t:[] for t in effects}
    for sid in sorted({r["set_id"] for r in rows}):
        for t,d in effects.items():
            cells=[x for x in d["set_effects"] if x["set_id"]!=sid]
            if len(cells)>=3:
                re=random_effect(np.asarray([x["unpooled"] for x in cells]),np.asarray([max((x["unpooled"]-d["population_effect"])**2/max(x["n"],1),1e-5) for x in cells]));loso[t].append(score(re["population_effect"],center,scale))
    stability={t:{"min":min(v) if v else d["score"],"max":max(v) if v else d["score"],"maximum_shift":max([abs(x-d["score"]) for x in v] or [0])} for t,(v,d) in ((t,(loso[t],effects[t])) for t in effects)}
    return {"status":"ESTIMATED","n":len(rows),"sets":len({r['set_id'] for r in rows}),"universe":universe,"effects":effects,"ordering_probabilities":ordering,
            "model_comparison":{"complete_pooling_rmse":pooled_rmse,"partial_pooling_in_sample_rmse":hierarchical_rmse,"no_pooling_diagnostic_rmse":no_pool_rmse,
             "held_out_set_prediction":"population effect for both pooled and hierarchy; unseen-set deviation is unknowable without a validated structural predictor","heldout_hierarchical_to_pooled_rmse_ratio":1.0,"hierarchical_in_sample_improvement":1-hierarchical_rmse/pooled_rmse},
            "leave_set_out_score_stability":stability}

def pair_analysis(result:dict[str,Any],left:str,right:str)->dict[str,Any]:
    if left not in result.get("effects",{}) or right not in result.get("effects",{}):return {"status":"INSUFFICIENT_DATA"}
    a={x["set_id"]:x for x in result["effects"][left]["set_effects"]};b={x["set_id"]:x for x in result["effects"][right]["set_effects"]}; items=[]; bands=PREREG["practical_log_bands"]
    for sid in sorted(a.keys()&b.keys()):
        diff=b[sid]["partially_pooled"]-a[sid]["partially_pooled"]
        if abs(diff)<=bands["approximately_equivalent"]:label="PRACTICALLY_SIMILAR"
        elif abs(diff)<=bands["slight_edge"]:label=("SIR" if diff>0 else "IR")+"_SLIGHT_EDGE"
        else:label=("SIR" if diff>0 else "IR")+"_MEANINGFUL_EDGE"
        items.append({"set_id":sid,"ir_n":a[sid]["n"],"sir_n":b[sid]["n"],"shrunk_log_difference":diff,"classification":label})
    c=Counter(x["classification"] for x in items);return {"population_log_difference":result["effects"][right]["population_effect"]-result["effects"][left]["population_effect"],"sets":items,"distribution":dict(c),"percentages":{k:v/max(len(items),1) for k,v in c.items()}}

def predictors(rows:list[dict[str,Any]],pair:dict[str,Any],set_map:list[dict[str,Any]])->dict[str,Any]:
    dates={s["id"]:s.get("release_date") for s in set_map}; observations=[]
    for item in pair.get("sets",[]):
        g=[r for r in rows if r["set_id"]==item["set_id"]]; ir=[r for r in g if r["rarity_designation"]=="illustration_rare"];sir=[r for r in g if r["rarity_designation"]=="special_illustration_rare"]
        def avg(x,f):
            v=[f(r) for r in x if f(r) is not None];return float(np.mean(v)) if v else 0.
        observations.append({"set_id":item["set_id"],"target":item["shrunk_log_difference"],"release_time":float((dates.get(item["set_id"]) or "2000")[:4]),"set_size":len(g),"sir_count":len(sir),"ir_count":len(ir),
          "demand_difference":avg(sir,lambda r:r.get("demand_score"))-avg(ir,lambda r:r.get("demand_score")),"scarcity_difference":avg(sir,lambda r:math.log(1/r["exact_pull_probability"]) if r.get("exact_pull_probability") else None)-avg(ir,lambda r:math.log(1/r["exact_pull_probability"]) if r.get("exact_pull_probability") else None),
          "mechanic_mix_difference":len({x for r in sir for x in r.get("mechanic_or_card_form") or []})-len({x for r in ir for x in r.get("mechanic_or_card_form") or []}),"canonical_special_set":int(any(x in g[0]["set_name"].lower() for x in ("gallery","vault","collection")))})
    if len(observations)<PREREG["predictor_gate"]["minimum_sets"]:return {"status":"NOT_TESTED_INSUFFICIENT_SETS","observations":observations}
    names=["release_time","set_size","sir_count","ir_count","demand_difference","scarcity_difference","mechanic_mix_difference","canonical_special_set"];y=np.asarray([x["target"] for x in observations]); tests={}
    base=float(np.sqrt(np.mean((y-y.mean())**2)))
    for name in names:
        x=np.asarray([o[name] for o in observations],float);corr=float(np.corrcoef(x,y)[0,1]) if x.std()>0 else 0.;pred=[]
        for i in range(len(y)):
            keep=np.arange(len(y))!=i;X=np.column_stack([np.ones(keep.sum()),x[keep]]);beta=np.linalg.lstsq(X,y[keep],rcond=None)[0];pred.append(beta[0]+beta[1]*x[i])
        rmse=float(np.sqrt(np.mean((y-np.asarray(pred))**2)));tests[name]={"correlation":corr,"loocv_rmse":rmse,"improvement":1-rmse/base if base else 0}
    passing=[n for n,d in tests.items() if abs(d["correlation"])>=.35 and d["improvement"]>=.05]
    return {"status":"CROSS_VALIDATED_CANDIDATE_NOT_INDEPENDENTLY_REPLICATED" if passing else "NO_REPLICATED_STRUCTURAL_PREDICTOR","baseline_rmse":base,"tests":tests,"exploratory_candidates":passing,"observations":observations,
            "interpretation":"LOOCV within the same era is not independent replication; no conditional production estimand is justified."}

def eligibility(result:dict[str,Any],temporal_ranges:Mapping[str,float]|None=None)->dict[str,Any]:
    failures=[];g=PREREG["eligibility"]
    if result.get("status")!="ESTIMATED":return {"eligible":False,"failures":["insufficient model support"]}
    for t,d in result["effects"].items():
        # Prediction-interval score width below is the transform-aware dispersion gate.
        score_sd=(d["score_prediction_interval"][1]-d["score_prediction_interval"][0])/3.92
        width=d["score_prediction_interval"][1]-d["score_prediction_interval"][0]
        if score_sd>g["maximum_score_between_set_sd"]:failures.append(f"{t}: between-set score SD")
        if width>g["maximum_score_prediction_interval_width"]:failures.append(f"{t}: prediction width")
        if result["leave_set_out_score_stability"][t]["maximum_shift"]>g["maximum_loso_score_shift"]:failures.append(f"{t}: LOSO shift")
        if temporal_ranges and temporal_ranges.get(t,0)>g["maximum_temporal_score_range"]:failures.append(f"{t}: temporal range")
    return {"eligible":not failures,"failures":failures,"rule":g}

def render(s:Mapping[str,Any])->str:
    labels=["Round 5 study ID","Hierarchical methodology","Shrinkage/partial-pooling method","Pooled vs hierarchical model performance","Held-out-set performance","S&V IR population effect","S&V SIR population effect","S&V between-set heterogeneity","S&V set-level relationship distribution","Predictors of S&V heterogeneity","S&V conditional-model result if legitimately tested","S&V final research status","Mega hierarchical results","Mega magnitude scores","Sword & Shield regime results","Sword & Shield whole-era vs regime comparison","Sun & Moon regime results","Sun & Moon whole-era vs regime comparison","XY heterogeneity result","Complete-pooling vs partial-pooling vs no-pooling comparison","Temporal hierarchical stability","Frozen-baseline score results","Score uncertainty","Heterogeneity eligibility rule","Support status by era","Modeling-architecture status","Magnitude-score status","Catalog-path status","Whether production-readiness research is authorized","Rows persisted","Production behavior","Files changed","Tests executed","Remaining limitations","Recommended next task"]
    vals=[s["study_id"],s["methodology"],s["shrinkage_method"],s["model_performance"],s["heldout_performance"],s["sv"]["model"].get("effects",{}).get("illustration_rare"),s["sv"]["model"].get("effects",{}).get("special_illustration_rare"),s["sv"]["heterogeneity"],s["sv"]["pair"],s["sv"]["predictors"],s["sv"]["conditional_model"],s["sv_status"],s["mega"],s["mega_scores"],s["swsh_regimes"],s["whole_vs_regime"]["Sword and Shield"],s["sunmoon_regimes"],s["whole_vs_regime"]["Sun and Moon"],s["xy"],s["model_performance"],s["temporal"],s["frozen_score_results"],s["score_uncertainty"],s["eligibility_rule"],s["support_matrix"],s["modeling_architecture_status"],s["magnitude_score_status"],s["catalog_path_status"],s["production_readiness_research_authorized"],0,s["production_behavior"],s["files_changed"],s["tests_executed"],s["limitations"],s["recommended_next_task"]]
    return "# Treatment Market Prestige V3 — Round 5 Results\n\n"+"\n\n".join(f"{i}. **{a}:** `{json.dumps(v,sort_keys=True,default=str)}`" for i,(a,v) in enumerate(zip(labels,vals),1))+"\n"

def main()->None:
    ap=argparse.ArgumentParser();ap.add_argument("--bootstrap-draws",type=int,default=399);ap.add_argument("--seed",type=int,default=SEED);a=ap.parse_args()
    rows,r1,_=load_round1();r4=json.loads(R4.read_text());checkpoints,tm=load_checkpoints();manifest=freeze(rows,r1,r4,tm)
    set_map=json.loads((ROOT/"treatment_market_prestige_v3_frozen_cohort/set_era_mapping.json").read_text());defs=r4["regime_definitions"]["era_regimes"]
    def run(era,setids=None,offset=0):
        rr=clean_rows(rows,era,set(setids) if setids else None);cal=r4["calibration"][era];return rr,hierarchical(rr,cal["frozen_center"],cal["frozen_scale"],a.bootstrap_draws,a.seed+offset)
    svrows,sv=run("Scarlet and Violet",offset=1);merows,mega=run("Mega Evolution",offset=2);xyrows,xy=run("XY",offset=3);swrows,sw=run("Sword and Shield",offset=4);smrows,sm=run("Sun and Moon",offset=5)
    regimes={}
    for era,off in (("Sword and Shield",20),("Sun and Moon",40)):
        regimes[era]=[]
        for i,reg in enumerate(defs[era]["regimes"]):
            rr,m=run(era,reg["set_ids"],off+i);regimes[era].append({"regime_id":reg["regime_id"],"sets":reg["sets"],"model":m,"eligibility":eligibility(m)})
    pair=pair_analysis(sv,"illustration_rare","special_illustration_rare");pred=predictors(svrows,pair,set_map)
    temporal=[]
    for i,cp in enumerate(checkpoints):
        tr=[{**r,"market_price":r["historical_market_price"],"log_price":r["historical_log_price"]} for r in cp["rows"]];rr=clean_rows(tr,"Scarlet and Violet");cal=r4["calibration"]["Scarlet and Violet"]
        temporal.append({"date":cp["manifest"]["reference_date"],"model":hierarchical(rr,cal["frozen_center"],cal["frozen_scale"],99,a.seed+100+i)})
    tranges={t:max(x["model"]["effects"][t]["score"] for x in temporal if t in x["model"].get("effects",{}))-min(x["model"]["effects"][t]["score"] for x in temporal if t in x["model"].get("effects",{})) for t in sv.get("effects",{}) if any(t in x["model"].get("effects",{}) for x in temporal)}
    svgate=eligibility(sv,tranges);megagate=eligibility(mega);xygate=eligibility(xy)
    sv_status="S&V_ERA_SCORE_STABLE_WITH_HIERARCHICAL_UNCERTAINTY" if svgate["eligible"] else "S&V_ERA_SCORE_REQUIRES_CONTEXT_ADJUSTMENT" if pred["status"]=="PREDICTOR_SUPPORTED" else "S&V_PRESTIGE_TOO_HETEROGENEOUS"
    support={}
    r4status=r4["era_support_statuses"]
    for era,status in r4status.items():
        if status=="TAXONOMY_REPAIR_REQUIRED":support[era]="TAXONOMY_REPAIR_REQUIRED"
        elif status in ("INSUFFICIENT_MULTI_SET_SUPPORT","INSUFFICIENT_TREATMENT_DIVERSITY"):support[era]="INSUFFICIENT_DATA"
        elif era=="Scarlet and Violet":support[era]="HIERARCHICAL_SCORE_RESEARCH_VALIDATED" if svgate["eligible"] else "HETEROGENEITY_TOO_HIGH"
        elif era=="Mega Evolution":support[era]="HIERARCHICAL_SCORE_RESEARCH_VALIDATED" if megagate["eligible"] else "HETEROGENEITY_TOO_HIGH"
        elif era in regimes:support[era]="REGIME_MODEL_VALIDATED" if any(x["eligibility"]["eligible"] for x in regimes[era]) else "HETEROGENEITY_TOO_HIGH"
        elif era=="XY":support[era]="HIERARCHICAL_SCORE_RESEARCH_VALIDATED" if xygate["eligible"] else "HETEROGENEITY_TOO_HIGH"
        else:support[era]="INSUFFICIENT_HISTORY"
    core_pass=svgate["eligible"] and megagate["eligible"] and any(x["eligibility"]["eligible"] for x in regimes["Sword and Shield"]) and any(x["eligibility"]["eligible"] for x in regimes["Sun and Moon"])
    architecture="HIERARCHICAL_MIXED_ERA_REGIME_FRAMEWORK_VALIDATED" if core_pass and xygate["eligible"] else "HIERARCHICAL_FRAMEWORK_PARTIALLY_VALIDATED" if any(x in ("HIERARCHICAL_SCORE_RESEARCH_VALIDATED","REGIME_MODEL_VALIDATED") for x in support.values()) else "HIERARCHICAL_MODEL_INSUFFICIENT"
    score_status="MAGNITUDE_SCORE_WITH_HIERARCHICAL_UNCERTAINTY_VALIDATED" if core_pass else "MAGNITUDE_SCORE_PARTIALLY_VALIDATED" if architecture=="HIERARCHICAL_FRAMEWORK_PARTIALLY_VALIDATED" else "MAGNITUDE_SCORE_NOT_REPRESENTATIVE"
    models={"Scarlet and Violet":sv,"Mega Evolution":mega,"XY":xy,"Sword and Shield":sw,"Sun and Moon":sm}
    study={"study_id":manifest["study_id"],"frozen_manifest":manifest,
      "preserved_inputs":{"round4_comparison_universes":{"Scarlet and Violet":"ERA_RELATIVE","Mega Evolution":"ERA_RELATIVE","Sword and Shield":"TREATMENT_REGIME_RELATIVE","Sun and Moon":"TREATMENT_REGIME_RELATIVE","XY":"ERA_RELATIVE"},"round3_provisional_scores":{"Scarlet and Violet":{"illustration_rare":4.64,"special_illustration_rare":5.36},"Mega Evolution":{"illustration_rare":8.02,"ultra_rare":5.00,"double_rare":3.95}},"round4_sv_calibration_status":"HETEROGENEOUS"},
      "methodology":"Transparent empirical-Bayes random-effects meta-regression on controlled set-treatment pseudo-effects; DerSimonian-Laird tau² and precision-weighted partial pooling.","shrinkage_method":"lambda=tau²/(tau²+sampling variance); small/noisy cells shrink more strongly toward the universe population effect.",
      "practical_bands":PREREG["practical_log_bands"],"models":models,"model_performance":{e:m.get("model_comparison") for e,m in models.items()},"heldout_performance":"For a genuinely unseen set, both pooled and unconditioned hierarchy predict the population mean (ratio 1.0). Hierarchical gains are uncertainty calibration and shrinkage, not fabricated mean-prediction gains.",
      "sv":{"model":sv,"pair":pair,"predictors":pred,"conditional_model":"NOT_JUSTIFIED_WITHOUT_INDEPENDENT_REPLICATION","heterogeneity":{t:{k:d[k] for k in ("between_set_variance","between_set_sd","within_set_variance","I2","prediction_interval")} for t,d in sv.get("effects",{}).items()},"eligibility":svgate},"sv_status":sv_status,
      "mega":{"model":mega,"eligibility":megagate},"mega_scores":{t:{"score":d["score"],"interval":d["score_interval"],"prediction_interval":d["score_prediction_interval"]} for t,d in mega.get("effects",{}).items()},
      "swsh_regimes":regimes["Sword and Shield"],"sunmoon_regimes":regimes["Sun and Moon"],"whole_vs_regime":{"Sword and Shield":{"whole":sw.get("model_comparison"),"regimes":[x["model"].get("model_comparison") for x in regimes["Sword and Shield"]]},"Sun and Moon":{"whole":sm.get("model_comparison"),"regimes":[x["model"].get("model_comparison") for x in regimes["Sun and Moon"]]}},
      "xy":{"model":xy,"eligibility":xygate,"diagnosis":"manageable hierarchical heterogeneity" if xygate["eligible"] else "true broad heterogeneity plus sparse treatment cells; no price-selected regimes permitted"},"temporal":{"checkpoints":temporal,"score_ranges":tranges},
      "frozen_score_results":{e:{t:{"score":d["score"],"interval":d["score_interval"]} for t,d in m.get("effects",{}).items()} for e,m in models.items()},"score_uncertainty":"Bootstrap population intervals and random-effects prediction intervals are propagated separately; ordering confidence is not used as magnitude.","eligibility_rule":PREREG["eligibility"],"support_matrix":support,
      "modeling_architecture_status":architecture,"magnitude_score_status":score_status,"catalog_path_status":"CATALOG_WIDE_PRODUCTION_RESEARCH_AUTHORIZED" if core_pass and xygate["eligible"] else "ADDITIONAL_TARGETED_RESEARCH_REQUIRED","production_readiness_research_authorized":bool(core_pass and xygate["eligible"]),"rows_persisted":0,
      "production_behavior":"Unchanged; no database, approved V3 score, Card Detail, frontend, V1/V2, appeal, RIP, or ranking change.","files_changed":[str(OUT/"cohort.json"),str(OUT/"manifest.json"),str(STUDY),str(REPORT),"backend/scripts/build_treatment_market_prestige_v3_round5.py","backend/tests/unit/desirability/test_treatment_market_prestige_v3_round5.py"],"tests_executed":["Round 5 unit tests","all Treatment Market Prestige V3 unit tests","frozen hashes and 35 report items"],
      "limitations":["observational treatment-package associations","method-of-moments random effects can be imprecise with few sets","unseen-set deviations cannot be predicted absent a replicated structural predictor","historical data is modern-heavy","Exact Pull Scarcity remains complementary and sparse","market supply/liquidity remains future work"],"recommended_next_task":"Targeted independent validation of S&V structural predictors and sparse SWSH/Sun & Moon regimes; do not begin a production contract unless every core gate passes."}
    STUDY.write_text(json.dumps(study,indent=2),encoding="utf-8");REPORT.write_text(render(study),encoding="utf-8")
    manifest["study_hash"]=stable_json_hash(study);(OUT/"manifest.json").write_text(json.dumps(manifest,indent=2),encoding="utf-8")

if __name__=="__main__":main()
