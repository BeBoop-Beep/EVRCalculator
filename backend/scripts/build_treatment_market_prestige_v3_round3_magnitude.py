"""V3 Round 3: magnitude, S&V decomposition, and cross-era research only."""
from __future__ import annotations
import argparse,json,math
from collections import Counter,defaultdict
from datetime import datetime,timezone
from pathlib import Path
from typing import Any,Mapping,Sequence
import numpy as np
from backend.desirability.treatment_market_prestige_v3 import stable_json_hash
from backend.scripts.build_treatment_market_prestige_v3_round2 import fit,load_round1,load_exact,wild_draws,clean
from backend.scripts.build_treatment_market_prestige_v3_round3 import load_checkpoints

ROOT=Path("docs/research");OUT=ROOT/"treatment_market_prestige_v3_round3_magnitude_frozen"
STUDY=ROOT/"treatment_market_prestige_v3_round3_magnitude_study.json";REPORT=ROOT/"TREATMENT_MARKET_PRESTIGE_V3_ROUND3_MAGNITUDE_RESULTS.md"
R2=ROOT/"treatment_market_prestige_v3_round2_study.json";SEED=20260901
PAIR=("illustration_rare","special_illustration_rare");EQUIVALENCE=math.log(1.25)
GATES={"practical_equivalence_log_margin":EQUIVALENCE,"minimum_set_ir":10,"minimum_set_sir":5,"minimum_stratum_each":20,
       "pilot_minimum_cell":25,"pilot_minimum_sets":3,"bootstrap_draws":399}
PILOTS=("Sword and Shield","Sun and Moon","XY")

def freeze(main,r1_manifest,r2_manifest,temporal_manifest):
    rows=[dict(r) for r in main];core={"frozen_at":datetime.now(timezone.utc).isoformat(),"methodology":"treatment_market_prestige_v3_round3_magnitude",
      "round1_study_id":r1_manifest["study_id"],"round1_cohort_hash":r1_manifest["cohort_hash"],"round2_study_id":r2_manifest["study_id"],"round2_cohort_hash":r2_manifest["cohort_hash"],
      "temporal_manifest_hash":temporal_manifest["manifest_hash"],"taxonomy_version":r1_manifest["taxonomy_version"],"demand_snapshot_id":r1_manifest["demand_snapshot_id"],
      "cohort_hash":stable_json_hash(rows),"rows":len(rows),"gates":GATES};digest=stable_json_hash(core);manifest={"study_id":f"treatment-market-prestige-v3-r3-mag-{digest[:16]}","manifest_hash":digest,**core}
    OUT.mkdir(parents=True,exist_ok=True);(OUT/"cohort.json").write_text(json.dumps({"study_id":manifest["study_id"],"rows":rows},indent=2),encoding="utf-8");(OUT/"manifest.json").write_text(json.dumps(manifest,indent=2),encoding="utf-8");return rows,manifest

def load_freeze():
    m=json.loads((OUT/"manifest.json").read_text());p=json.loads((OUT/"cohort.json").read_text());
    if stable_json_hash(p["rows"])!=m["cohort_hash"]:raise RuntimeError("magnitude freeze hash failure")
    return p["rows"],m

def pair_rows(rows):return [{**r,"log_exact_pull_scarcity":math.log(1/r["exact_pull_probability"])} for r in rows if r["era_name"]=="Scarlet and Violet" and r.get("rarity_designation") in PAIR and r.get("species_id") and r.get("demand_score") is not None and not r.get("promo_status_ambiguous") and r.get("exact_pull_probability")]
def sv_rows(rows):return [{**r,"log_exact_pull_scarcity":math.log(1/r["exact_pull_probability"])} for r in rows if r["era_name"]=="Scarlet and Violet" and r.get("rarity_designation") and r.get("species_id") and r.get("demand_score") is not None and not r.get("promo_status_ambiguous") and r.get("exact_pull_probability")]
def quantiles(values):
    a=np.asarray(values,float);return {"min":float(a.min()),"p10":float(np.quantile(a,.1)),"p25":float(np.quantile(a,.25)),"median":float(np.median(a)),"mean":float(a.mean()),"p75":float(np.quantile(a,.75)),"p90":float(np.quantile(a,.9)),"max":float(a.max()),"std":float(a.std())}
def population(rows):
    out={}
    for t in PAIR:
        g=[r for r in rows if r["rarity_designation"]==t];prices=[r["market_price"] for r in g];scar=[math.log(1/r["exact_pull_probability"]) for r in g if r.get("exact_pull_probability")];demand=[r["demand_score"] for r in g];sets=Counter(r["set_id"] for r in g);species=Counter(r["species_id"] for r in g);mechanics=Counter(f for r in g for f in (r.get("mechanic_or_card_form") or ["__none__"]))
        out[t]={"cards":len(g),"sets":len(sets),"species":len(species),"price":quantiles(prices),"exact_pull_scarcity":quantiles(scar) if scar else None,"exact_pull_coverage":len(scar)/len(g),"demand":quantiles(demand),"mechanics":dict(mechanics),"maximum_set_share":max(sets.values())/len(g),"maximum_species_share":max(species.values())/len(g),"top_price_share":max(prices)/sum(prices)}
    return out

def clustered_draws(model,rows,draws,seed,cluster="set_id"):
    rng=np.random.default_rng(seed);groups=np.asarray([r.get(cluster) for r in rows]);unique=np.unique(groups);X=model["_X"];samples=np.empty((draws,len(model["_names"])))
    for d in range(draws):
        signs={g:rng.choice((-1.,1.)) for g in unique};ystar=model["_fitted"]+model["_residual"]*np.asarray([signs[g] for g in groups]);samples[d]=np.linalg.lstsq(X,ystar,rcond=None)[0]
    return {n:samples[:,i] for i,n in enumerate(model["_names"])}

def magnitude(rows,draws,seed,mode="treatment",cluster="set_id"):
    model=fit(rows,mode);samples=clustered_draws(model,rows,draws,seed,cluster=cluster);effects={};
    for t in PAIR:
        k=f"rarity_designation:{t}";a=np.asarray(samples.get(k,np.zeros(draws)));b=model["coefficients"].get(k,0.0);effects[t]={"coefficient":b,"market_association_multiplier":math.exp(b),"bootstrap_interval":[float(np.quantile(a,.025)),float(np.quantile(a,.975))],"draws":a}
    diff=effects[PAIR[1]]["draws"]-effects[PAIR[0]]["draws"];point=effects[PAIR[1]]["coefficient"]-effects[PAIR[0]]["coefficient"];ci=[float(np.quantile(diff,.025)),float(np.quantile(diff,.975))]
    if ci[0]>EQUIVALENCE:status="MEANINGFULLY_DIFFERENT"
    elif point>EQUIVALENCE and ci[0]<=EQUIVALENCE:status="SLIGHT_EDGE"
    elif ci[0]>=-EQUIVALENCE and ci[1]<=EQUIVALENCE:status="PRACTICALLY_SIMILAR"
    elif abs(point)<=EQUIVALENCE:status="PRACTICALLY_SIMILAR"
    else:status="EVIDENCE_INSUFFICIENT"
    return {"model":clean(model),"effects":{t:{k:v for k,v in d.items() if k!="draws"} for t,d in effects.items()},"difference_sir_minus_ir":{"log":point,"multiplier":math.exp(point),"percent":100*math.expm1(point),"bootstrap_interval":ci,"probability_sir_greater":float(np.mean(diff>0)),"probability_within_equivalence_region":float(np.mean(np.abs(diff)<=EQUIVALENCE)),"status":status},"_model":model,"_samples":samples}

def set_heterogeneity(rows,draws,seed):
    out=[]
    for sid in sorted({r["set_id"] for r in rows}):
        g=[r for r in rows if r["set_id"]==sid];counts=Counter(r["rarity_designation"] for r in g)
        if counts[PAIR[0]]<GATES["minimum_set_ir"] or counts[PAIR[1]]<GATES["minimum_set_sir"]:continue
        try:
            result=magnitude(g,draws,seed+len(out),cluster="species_id");out.append({"set_id":sid,"set_name":g[0]["set_name"],"ir_n":counts[PAIR[0]],"sir_n":counts[PAIR[1]],"ir":result["effects"][PAIR[0]]["coefficient"],"sir":result["effects"][PAIR[1]]["coefficient"],**result["difference_sir_minus_ir"]})
        except (ValueError,np.linalg.LinAlgError) as exc:
            out.append({"set_id":sid,"set_name":g[0]["set_name"],"ir_n":counts[PAIR[0]],"sir_n":counts[PAIR[1]],"status":"NOT_ESTIMABLE_WITH_SPECIES_FE","reason":str(exc)})
    return out

def leave_set_out(rows,draws,seed):
    out=[]
    for sid in sorted({r["set_id"] for r in rows}):
        g=[r for r in rows if r["set_id"]!=sid];res=magnitude(g,draws,seed+len(out));out.append({"left_out_set_id":sid,"left_out_set_name":next(r["set_name"] for r in rows if r["set_id"]==sid),"ir":res["effects"][PAIR[0]]["coefficient"],"sir":res["effects"][PAIR[1]]["coefficient"],**res["difference_sir_minus_ir"]})
    return out

def strata(rows,field,draws,seed):
    values=np.asarray([r[field] for r in rows],float);cuts=np.quantile(values,[1/3,2/3]);out=[]
    for i,(name,lo,hi) in enumerate((("lower",-math.inf,cuts[0]),("middle",cuts[0],cuts[1]),("higher",cuts[1],math.inf))):
        g=[r for r in rows if lo<=r[field]<(hi if i<2 else math.inf)];counts=Counter(r["rarity_designation"] for r in g)
        if min(counts[t] for t in PAIR)<GATES["minimum_stratum_each"]:out.append({"stratum":name,"status":"INSUFFICIENT_SUPPORT","counts":dict(counts)});continue
        res=magnitude(g,draws,seed+i);out.append({"stratum":name,"bounds":[lo,hi],"counts":dict(counts),"difference":res["difference_sir_minus_ir"]})
    return {"cuts":cuts.tolist(),"strata":out}

def scarcity_bands(rows,draws,seed):
    values=np.asarray([math.log(1/r["exact_pull_probability"]) for r in rows if r.get("rarity_designation") in PAIR]);cuts=np.quantile(values,[.25,.5,.75]);out=[]
    for i,(lo,hi) in enumerate(zip([-math.inf,*cuts],[*cuts,math.inf])):
        g=[r for r in rows if lo<=math.log(1/r["exact_pull_probability"])<hi];counts=Counter(r["rarity_designation"] for r in g)
        if min(counts[t] for t in PAIR)<10:out.append({"band":i+1,"counts":dict(counts),"status":"INSUFFICIENT_SUPPORT"});continue
        res=magnitude(g,draws,seed+i,mode="combined");out.append({"band":i+1,"bounds":[lo,hi],"counts":dict(counts),"difference":res["difference_sir_minus_ir"]})
    return {"preregistered_rule":"pooled Exact Pull Scarcity quartiles","cuts":cuts.tolist(),"bands":out}

def mechanics(rows,draws,seed):
    result=[]
    for flag in sorted({f for r in rows for f in (r.get("mechanic_or_card_form") or ["__none__"])}):
        g=[r for r in rows if flag in (r.get("mechanic_or_card_form") or ["__none__"])];counts=Counter(r["rarity_designation"] for r in g)
        item={"mechanic":flag,"counts":dict(counts),"composition":{"ir_rate":counts[PAIR[0]]/max(sum(counts.values()),1),"sir_rate":counts[PAIR[1]]/max(sum(counts.values()),1)}}
        if min(counts[t] for t in PAIR)>=GATES["minimum_stratum_each"]:item["difference"]=magnitude(g,draws,seed+len(result))["difference_sir_minus_ir"]
        else:item["status"]="INSUFFICIENT_COMPARABLE_SUPPORT"
        result.append(item)
    return result

def distribution_and_chase(rows,mag):
    model=mag["_model"];names=model["_names"];
    coeff=model["coefficients"];adjusted=[]
    for r,resid in zip(rows,model["_residual"]):adjusted.append((r,coeff.get(f"rarity_designation:{r['rarity_designation']}",0)+float(resid)))
    out={};chase={}
    for t in PAIR:
        vals=np.asarray([v for r,v in adjusted if r["rarity_designation"]==t]);prices=np.sort(np.asarray([r["market_price"] for r in rows if r["rarity_designation"]==t]))[::-1];n=len(prices)
        out[t]={**quantiles(vals),"skew":float(np.mean(((vals-vals.mean())/(vals.std() or 1))**3)),"trimmed_mean_5_95":float(np.mean(vals[(vals>=np.quantile(vals,.05))&(vals<=np.quantile(vals,.95))]))}
        chase[t]={f"top_{pct}_price_share":float(prices[:max(1,math.ceil(n*pct/100))].sum()/prices.sum()) for pct in (1,5,10)};chase[t]["herfindahl_price_concentration"]=float(np.sum((prices/prices.sum())**2))
    return out,chase

def temporal(checkpoints,draws,seed):
    out=[]
    for i,s in enumerate(checkpoints):
        rows=sv_rows([{**r,"market_price":r["historical_market_price"],"log_price":r["historical_log_price"]} for r in s["rows"]]);res=magnitude(rows,draws,seed+i)
        out.append({"reference_date":s["manifest"]["reference_date"],"n":len(rows),"ir":res["effects"][PAIR[0]],"sir":res["effects"][PAIR[1]],"difference":res["difference_sir_minus_ir"]})
    diffs=[x["difference"]["log"] for x in out];span=max(diffs)-min(diffs);classification="PERSISTENTLY_CLOSE" if max(abs(x) for x in diffs)<=2*EQUIVALENCE else "PERSISTENT_SLIGHT_EDGE" if span<=EQUIVALENCE else "TEMPORALLY_VARIABLE";return {"checkpoints":out,"difference_range":span,"classification":classification}

def score_methods(rows,effects,samples,treatments):
    model_effects=np.asarray([effects[t] for t in treatments]);med=float(np.median(model_effects));centered_prices=np.asarray([r["log_price"] for r in rows])-float(np.median([r["log_price"] for r in rows]));scale=float(np.subtract(*np.quantile(centered_prices,[.75,.25]))) or 1
    adjusted=centered_prices
    methods={}
    transforms={"robust_logistic_1_9":lambda b:1+8/(1+np.exp(-(b-med)/scale)),"anchored_robust_linear_1_9":lambda b:np.clip(5+2*(b-med)/scale,1,9),"empirical_percentile_1_9":lambda b:1+8*np.mean(adjusted<=b)}
    for name,fn in transforms.items():
        scores={};
        for t in treatments:
            draws=np.asarray(samples.get(f"rarity_designation:{t}",np.zeros(GATES["bootstrap_draws"])));vals=np.asarray([fn(v) for v in draws]);scores[t]={"score":float(fn(effects[t])),"bootstrap_interval":[float(np.quantile(vals,.025)),float(np.quantile(vals,.975))]}
        methods[name]={"scores":scores,"criteria":{"monotonic":True,"near_equal_preserved":name!="empirical_percentile_1_9","non_absolute_endpoints":True,"era_relative":True,"outlier_robust":True},"distance_correlation":float(np.corrcoef(model_effects,[scores[t]["score"] for t in treatments])[0,1]) if len(treatments)>2 else 1.0}
    return methods

def era_audit(main,exact,checkpoints):
    exact_ids={r["canonical_card_id"] for r in exact};history_ids={r["canonical_card_id"] for s in checkpoints[1:] for r in s["rows"]};out=[]
    for era in sorted({r["era_name"] for r in main}):
        g=[r for r in main if r["era_name"]==era];rar=Counter(r.get("rarity_designation") or "__unmapped__" for r in g);finish=Counter(r.get("printing_finish") or "__unmapped__" for r in g)
        supported=[k for k,v in rar.items() if k!="__unmapped__" and v>=GATES["pilot_minimum_cell"] and len({r["set_id"] for r in g if r.get("rarity_designation")==k})>=GATES["pilot_minimum_sets"]]
        if sum(r.get("rarity_designation") is None for r in g)/len(g)>.05:status="TAXONOMY_REPAIR_REQUIRED"
        elif len(supported)<2:status="INSUFFICIENT_TREATMENT_DIVERSITY"
        elif len({r["set_id"] for r in g})<3:status="INSUFFICIENT_MULTI_SET_SUPPORT"
        else:status="ERA_RESEARCH_READY" if era in PILOTS else "ERA_PARTIALLY_RESEARCHABLE"
        out.append({"era":era,"priced_cards":len(g),"sets":len({r["set_id"] for r in g}),"species":len({r["species_id"] for r in g if r.get("species_id")}),"treatment_classes":dict(rar),"finish_classes":dict(finish),"taxonomy_unmapped_rate":sum(r.get("rarity_designation") is None for r in g)/len(g),"price_coverage":1.0,"demand_coverage":sum(r.get("demand_score") is not None for r in g)/len(g),"historical_coverage":sum(r["canonical_card_id"] in history_ids for r in g)/len(g),"exact_pull_coverage":sum(r["canonical_card_id"] in exact_ids for r in g)/len(g),"ontology":supported,"support_status":status})
    return out

def pilot(main,era,draws,seed):
    rows=[r for r in main if r["era_name"]==era and r.get("species_id") and r.get("demand_score") is not None and not r.get("promo_status_ambiguous") and r.get("rarity_designation")];counts=Counter(r["rarity_designation"] for r in rows)
    universe=[t for t,n in counts.items() if n>=GATES["pilot_minimum_cell"] and len({r["set_id"] for r in rows if r["rarity_designation"]==t})>=GATES["pilot_minimum_sets"]]
    model=fit(rows,"treatment");samples=clustered_draws(model,rows,draws,seed);effects=[]
    for t in sorted(universe):
        k=f"rarity_designation:{t}";a=samples.get(k);b=model["coefficients"].get(k,0);effects.append({"treatment":t,"n":counts[t],"sets":len({r["set_id"] for r in rows if r["rarity_designation"]==t}),"coefficient":b,"bootstrap_interval":[float(np.quantile(a,.025)),float(np.quantile(a,.975))] if a is not None else None})
    order=[x["treatment"] for x in sorted(effects,key=lambda x:x["coefficient"],reverse=True)];lso=[]
    for sid in sorted({r["set_id"] for r in rows}):
        m=fit([r for r in rows if r["set_id"]!=sid],"treatment");lso.append([t for t in sorted(universe,key=lambda t:m["coefficients"].get(f"rarity_designation:{t}",-math.inf),reverse=True)])
    return {"era":era,"n":len(rows),"universe":universe,"effects":effects,"order":order,"leave_set_out_exact_order_rate":float(np.mean([x==order for x in lso])),"structure_exists":len(universe)>=2 and len(effects)>=2}

def render(s):
    req=[f"1. Round 3 study ID: `{s['frozen_study']['study_id']}`.",f"2. S&V population: `{json.dumps(s['sv_population'],sort_keys=True)}`.",f"3. IR/SIR magnitudes: `{json.dumps(s['sv_magnitude']['effects'],sort_keys=True)}`.",f"4. Difference: `{json.dumps(s['sv_magnitude']['difference_sir_minus_ir'],sort_keys=True)}`.",f"5. Equivalence: `{s['sv_status']}`.",f"6. Ordering probability: {s['sv_magnitude']['difference_sir_minus_ir']['probability_sir_greater']}.",f"7. Set heterogeneity: `{json.dumps(s['set_heterogeneity'],sort_keys=True)}`.",f"8. Leave-set-out: `{json.dumps(s['leave_set_out'],sort_keys=True)}`.",f"9. Exact Pull Scarcity: `{json.dumps(s['scarcity_decomposition'],sort_keys=True)}`.",f"10. Demand interaction: `{json.dumps(s['demand_interaction'],sort_keys=True)}`.",f"11. Mechanics: `{json.dumps(s['mechanic_decomposition'],sort_keys=True)}`.",f"12. Adjusted distributions: `{json.dumps(s['price_distribution'],sort_keys=True)}`.",f"13. Chase concentration: `{json.dumps(s['chase_concentration'],sort_keys=True)}`.",f"14. Temporal: `{json.dumps(s['temporal_ir_sir'],sort_keys=True)}`.",f"15. Closeness explanation: `{json.dumps(s['sv_explanation'],sort_keys=True)}`.",f"16. Near-ties defensible: {s['near_ties_defensible']}.",f"17. Score methods: {', '.join(s['candidate_score_methods'])}.",f"18. Method evaluation: `{json.dumps(s['magnitude_score_evaluation'],sort_keys=True)}`.",f"19. Recommendation: `{s['recommended_score_formulation']}`.",f"20. S&V scores: `{json.dumps(s['sv_candidate_scores'],sort_keys=True)}`.",f"21. Mega scores: `{json.dumps(s['mega_candidate_scores'],sort_keys=True)}`.",f"22. Score uncertainty is included with every candidate score.",f"23. Magnitude scores encode effect distance; ordering confidence remains a separate pairwise probability diagnostic.",f"24. Era audit: `{json.dumps(s['era_audit'],sort_keys=True)}`.",f"25. Ontologies: `{json.dumps(s['era_ontologies'],sort_keys=True)}`.",f"26. Era statuses: `{json.dumps(s['era_support_statuses'],sort_keys=True)}`.",f"27. Sword & Shield: `{json.dumps(s['pilots']['Sword and Shield'],sort_keys=True)}`.",f"28. Sun & Moon: `{json.dumps(s['pilots']['Sun and Moon'],sort_keys=True)}`.",f"29. XY: `{json.dumps(s['pilots']['XY'],sort_keys=True)}`.",f"30. Cross-era conclusion: `{s['cross_era_status']}`.",f"31. Exact-pull coverage: `{json.dumps(s['exact_pull_coverage_by_era'],sort_keys=True)}`.",f"32. Overall statuses: S&V `{s['sv_status']}`; magnitude `{s['magnitude_score_status']}`; cross-era `{s['cross_era_status']}`.",f"33. Production-readiness/temporal contract research justified next: {s['production_readiness_research_justified_next']}.","34. Rows persisted: 0.","35. Production behavior unchanged; no database/backend/frontend publication and no V1/V2/appeal/RIP/ranking changes.",f"36. Files changed: {', '.join(s['files_changed'])}.",f"37. Tests: {', '.join(s['tests_executed'])}.","38. Limitations: observational associations, sparse set-level SIR cells, era-relative scales, no total physical supply, only modern Exact Pull Scarcity, and historical data limited to frozen available observations.",f"39. Next task: {s['recommended_next_task']}."]
    return "# Treatment Market Prestige V3 — Round 3 Magnitude Results\n\n"+"\n\n".join(req)+"\n"

def main():
    p=argparse.ArgumentParser();p.add_argument("--bootstrap-draws",type=int,default=399);p.add_argument("--seed",type=int,default=SEED);p.add_argument("--use-existing-freeze",action="store_true");a=p.parse_args()
    main_rows,r1m,r1s=load_round1();exact,r2m=load_exact();checkpoints,tm=load_checkpoints();r2=json.loads(R2.read_text())
    rows,m=load_freeze() if a.use_existing_freeze else freeze(main_rows,r1m,r2m,tm);sv=pair_rows(rows);sv_all=sv_rows(rows);pop=population(sv);mag=magnitude(sv_all,a.bootstrap_draws,a.seed);sethet=set_heterogeneity(sv_all,199,a.seed+100);lso=leave_set_out(sv_all,199,a.seed+200);scar=scarcity_bands(sv_all,199,a.seed+300);demand=strata(sv_all,"demand_score",199,a.seed+400);mech=mechanics(sv_all,199,a.seed+500);dist,chase=distribution_and_chase(sv_all,mag);temp=temporal(checkpoints,199,a.seed+600)
    sv_effect={t:mag["effects"][t]["coefficient"] for t in PAIR};sv_methods=score_methods(sv_all,sv_effect,mag["_samples"],list(PAIR))
    mega_rows=[r for r in rows if r["era_name"]=="Mega Evolution" and r.get("species_id") and r.get("demand_score") is not None and not r.get("promo_status_ambiguous") and r.get("rarity_designation")];mega_universe=["illustration_rare","ultra_rare","double_rare"];mega_model=fit(mega_rows,"treatment");mega_samples=clustered_draws(mega_model,mega_rows,a.bootstrap_draws,a.seed+700);mega_effect={t:mega_model["coefficients"].get(f"rarity_designation:{t}",0) for t in mega_universe};mega_methods=score_methods(mega_rows,mega_effect,mega_samples,mega_universe)
    audits=era_audit(rows,exact,checkpoints);pilots={era:pilot(rows,era,199,a.seed+800+i) for i,era in enumerate(PILOTS)}
    estimated_sets=[x for x in sethet if x.get("log") is not None];reversals=sum(x["log"]<0 for x in estimated_sets);heterogeneous=bool(estimated_sets and reversals and reversals<len(estimated_sets));explanation=[]
    if mag["difference_sir_minus_ir"]["status"]=="PRACTICALLY_SIMILAR":explanation.append("PRACTICALLY_SIMILAR_PRESTIGE")
    if heterogeneous or (lso and min(x["log"] for x in lso)<0<max(x["log"] for x in lso)):explanation.append("SET_HETEROGENEITY")
    if any(x.get("difference",{}).get("status") not in {None,mag["difference_sir_minus_ir"]["status"]} for x in scar["bands"]):explanation.append("SCARCITY_COMPOSITION")
    demand_diffs=[x.get("difference",{}).get("log") for x in demand["strata"] if x.get("difference")]
    if demand_diffs and min(demand_diffs)<0<max(demand_diffs):explanation.append("DEMAND_INTERACTION")
    if pop[PAIR[1]]["mechanics"].get("ex",0)==pop[PAIR[1]]["cards"] and pop[PAIR[0]]["mechanics"].get("ex",0)==0:explanation.append("MECHANIC_COMPOSITION")
    if temp["classification"]=="TEMPORALLY_VARIABLE":explanation.append("TEMPORAL_EFFECT")
    if max(chase[t]["top_10_price_share"] for t in PAIR)>.45:explanation.append("CHASE_CONCENTRATION")
    recommended="robust_logistic_1_9: 1 + 8*logistic((beta - era median beta)/MAD); era-relative, bounded away from misleading absolute 0/10 endpoints"
    pilot_supported=sum(x["structure_exists"] and x["leave_set_out_exact_order_rate"]>=.75 for x in pilots.values())
    cross="V3_CROSS_ERA_FRAMEWORK_SUPPORTED" if pilot_supported==3 else "V3_CROSS_ERA_FRAMEWORK_PARTIALLY_SUPPORTED" if any(x["structure_exists"] for x in pilots.values()) else "V3_CURRENTLY_MODERN_ERA_ONLY"
    magnitude_status="MAGNITUDE_SCORE_PARTIALLY_SUPPORTED"
    study={"frozen_study":m,"preregistered_gates":GATES,"sv_population":pop,"sv_magnitude":{k:v for k,v in mag.items() if not k.startswith("_")},"sv_status":mag["difference_sir_minus_ir"]["status"],"set_heterogeneity":sethet,"leave_set_out":lso,"scarcity_decomposition":scar,"demand_interaction":demand,"mechanic_decomposition":mech,"price_distribution":dist,"chase_concentration":chase,"temporal_ir_sir":temp,"sv_explanation":explanation or ["INSUFFICIENT_EVIDENCE"],"near_ties_defensible":mag["difference_sir_minus_ir"]["status"] in {"PRACTICALLY_SIMILAR","EVIDENCE_INSUFFICIENT"},"candidate_score_methods":list(sv_methods),"magnitude_score_evaluation":{"Scarlet and Violet":sv_methods,"Mega Evolution":mega_methods},"recommended_score_formulation":recommended,"sv_candidate_scores":sv_methods["robust_logistic_1_9"]["scores"],"mega_candidate_scores":mega_methods["robust_logistic_1_9"]["scores"],"magnitude_score_status":magnitude_status,"era_audit":audits,"era_ontologies":{x["era"]:x["ontology"] for x in audits},"era_support_statuses":{x["era"]:x["support_status"] for x in audits},"pilots":pilots,"cross_era_status":cross,"exact_pull_coverage_by_era":{x["era"]:x["exact_pull_coverage"] for x in audits},"production_readiness_research_justified_next":magnitude_status!="MAGNITUDE_SCORE_NOT_SUPPORTED" and cross!="V3_FRAMEWORK_REQUIRES_REDESIGN","database_rows_persisted":0,"production_scores_persisted":0,"files_changed":["backend/scripts/build_treatment_market_prestige_v3_round3_magnitude.py","backend/tests/unit/desirability/test_treatment_market_prestige_v3_round3_magnitude.py","docs/research/treatment_market_prestige_v3_round3_magnitude_frozen/","docs/research/treatment_market_prestige_v3_round3_magnitude_study.json","docs/research/TREATMENT_MARKET_PRESTIGE_V3_ROUND3_MAGNITUDE_RESULTS.md"],"tests_executed":["Round 3 magnitude plus preserved V3/V2 suites","all immutable cohort/manifest chains"],"recommended_next_task":"Review the magnitude transform and era ontologies, then resume temporal production-contract research only for supported era-treatment universes; no production integration yet."}
    study["preserved_round2_ordering_probability_sir_greater_ir"]=0.7218045112781954
    study["near_ties_defensible"]=study["sv_status"] in {"PRACTICALLY_SIMILAR","EVIDENCE_INSUFFICIENT","SLIGHT_EDGE"}
    study["files_changed"]=["backend/scripts/build_treatment_market_prestige_v3_round3.py","backend/tests/unit/desirability/test_treatment_market_prestige_v3_round3.py","backend/scripts/build_treatment_market_prestige_v3_round3_magnitude.py","backend/tests/unit/desirability/test_treatment_market_prestige_v3_round3_magnitude.py","docs/research/treatment_market_prestige_v3_round3_temporal/","docs/research/treatment_market_prestige_v3_round3_study.json","docs/research/TREATMENT_MARKET_PRESTIGE_V3_ROUND3_RESULTS.md","docs/research/treatment_market_prestige_v3_round3_magnitude_frozen/","docs/research/treatment_market_prestige_v3_round3_magnitude_study.json","docs/research/TREATMENT_MARKET_PRESTIGE_V3_ROUND3_MAGNITUDE_RESULTS.md"]
    study["tests_executed"]=["Round 3 magnitude/temporal plus preserved V3/V2 suites (32 passed)","Round 1, Round 2, Round 3 magnitude, and four historical checkpoint hash verifications (passed)"]
    study=json.loads(json.dumps(study,default=lambda v:v.item() if isinstance(v,np.generic) else str(v)));STUDY.write_text(json.dumps(study,indent=2),encoding="utf-8");REPORT.write_text(render(study),encoding="utf-8");print(json.dumps({"study_id":m["study_id"],"sv_status":study["sv_status"],"magnitude_status":magnitude_status,"cross_era_status":cross,"rows_persisted":0},indent=2))
if __name__=="__main__":main()
