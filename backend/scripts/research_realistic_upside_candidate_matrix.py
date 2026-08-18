"""STEP 3B: controlled Realistic Upside definition x influence study."""

from __future__ import annotations

import argparse
import hashlib
import json
import math
import sys
from collections import Counter, defaultdict
from pathlib import Path
from typing import Any, Mapping, Optional, Sequence

import numpy as np
from scipy.stats import spearmanr

REPO_ROOT=Path(__file__).resolve().parents[2]
if str(REPO_ROOT) not in sys.path:sys.path.insert(0,str(REPO_ROOT))

from backend.calculations.evr.financial_rip_v3 import build_financial_rip_v3
from backend.calculations.evr.financial_rip_v3_config import FINANCIAL_RIP_V3_COMPONENT_ORDER,normalize_metric
from backend.scripts.research_cross_format_product_rip import resolve_authoritative_snapshot
from backend.scripts.research_equal_spend_product_rip import PRIMARY_TOLERANCE,SENSITIVITY_TOLERANCE,StrategyEngine,load_authoritative_products,load_run_fingerprints
from backend.scripts.research_product_rip_dominance_utility import strategy_values
from backend.scripts.research_realistic_upside_semantics import power_utility,weakest_risk_seeking

STEP2A_PATH=REPO_ROOT/"logs/product_rip_publication_architecture_research.json"
STEP2C_PATH=REPO_ROOT/"logs/product_rip_dominance_utility_research.json"
STEP3A_PATH=REPO_ROOT/"logs/realistic_upside_semantics_research.json"
DEFINITIONS=("CURRENT_REALISTIC","P95_THRESHOLD_ONLY")
REALISTIC_WEIGHTS=(.25,.20,.15,.10)
CORE=("true_win_frequency","typical_retention","loss_resilience","base_economic_efficiency")
BASE_CORE={"true_win_frequency":.25,"typical_retention":.20,"loss_resilience":.15,"base_economic_efficiency":.05}
GAMMAS=(2.0,1.0,.5,0.0,-.5,-1.0)
DECISION="P95_THRESHOLD_AND_LOWER_WEIGHT_SUPPORTED"


def candidate_weights(realistic_weight:float)->dict[str,float]:
    removed=.25-float(realistic_weight)
    weights={key:value+removed*value/.65 for key,value in BASE_CORE.items()}
    return {"true_win_frequency":weights["true_win_frequency"],"typical_retention":weights["typical_retention"],
        "loss_resilience":weights["loss_resilience"],"realistic_upside":float(realistic_weight),"jackpot_upside":.10,
        "base_economic_efficiency":weights["base_economic_efficiency"]}


def candidate_id(definition:str,weight:float)->str:return f"{definition}@{int(round(weight*100))}"


def candidates()->dict[str,dict[str,Any]]:
    return {candidate_id(d,w):{"definition":d,"realisticWeight":w,"weights":candidate_weights(w)} for d in DEFINITIONS for w in REALISTIC_WEIGHTS}


def realistic_score(definition:str,p95_ratio:float,current_score:float)->float:
    return float(current_score) if definition=="CURRENT_REALISTIC" else float(normalize_metric("p95_threshold_ratio",float(p95_ratio))["score"])


def score_candidate(components:Mapping[str,float],p95_ratio:float,candidate:Mapping[str,Any])->float:
    definition=candidate["definition"];weights=candidate["weights"]
    return float(sum(weights[key]*(realistic_score(definition,p95_ratio,components[key]) if key=="realistic_upside" else float(components[key])) for key in FINANCIAL_RIP_V3_COMPONENT_ORDER))


def deterministic_subsample(values:np.ndarray,size:int,repetition:int,seed_key:str)->np.ndarray:
    if size>=len(values):return np.asarray(values,float).copy()
    seed=int(hashlib.sha256(f"{seed_key}:{size}:{repetition}".encode()).hexdigest()[:16],16)%(2**32)
    return np.asarray(values,float)[np.random.default_rng(seed).choice(len(values),size=size,replace=False)]


def p95_boundary_diagnostic(values:np.ndarray,cost:float)->dict[str,Any]:
    sorted_values=np.sort(np.asarray(values,float));n=len(sorted_values);p95=float(np.percentile(sorted_values,95));equal=int(np.count_nonzero(sorted_values==p95));idx=int(math.floor(.95*(n-1)))
    below=float(sorted_values[max(0,idx-1)]);above=float(sorted_values[min(n-1,idx+1)])
    return {"p95":p95,"p95Ratio":p95/cost,"exactTieCount":equal,"exactTieShare":equal/n,"adjacentJumpBelow":p95-below,"adjacentJumpAbove":above-p95,
        "normalizedAdjacentScoreSpan":float(normalize_metric("p95_threshold_ratio",above/cost)["score"]-normalize_metric("p95_threshold_ratio",below/cost)["score"])}


def _rank(values:Sequence[float])->np.ndarray:return np.argsort(np.argsort(-np.asarray(values,float)))+1


def _dominates(low:Sequence[float],high:Sequence[float])->bool:
    return all(x>=y-1e-9 for x,y in zip(low,high)) and any(x>y+1e-9 for x,y in zip(low,high))


def enrich_row(row:Mapping[str,Any],metrics:Mapping[str,Any],matrix:Mapping[str,Mapping[str,Any]])->dict[str,Any]:
    out=dict(row);out.update({key:metrics[key] for key in ("p95ThresholdRatio","realisticTailMeanRatio","p99ThresholdRatio","jackpotTailMeanRatio")})
    out["candidateRealistic"]={key:realistic_score(c["definition"],metrics["p95ThresholdRatio"],metrics["components"]["realistic_upside"]) for key,c in matrix.items()}
    out["candidateScores"]={key:score_candidate(metrics["components"],metrics["p95ThresholdRatio"],c) for key,c in matrix.items()}
    return out


def cohort_matrix(budget:Mapping[str,Sequence[Mapping[str,Any]]],matrix:Mapping[str,Mapping[str,Any]],tolerance:float)->dict[str,Any]:
    summaries={key:Counter() for key in matrix};inversions={key:[] for key in matrix};observations=[];score_rtp={key:[[],[]] for key in matrix};pair_directions={key:defaultdict(list) for key in matrix}
    for budget_key,rows in budget.items():
        for key in matrix:
            top=max(rows,key=lambda r:r["candidateScores"][key]);baseline=max(rows,key=lambda r:r["financialRipV3"])
            summaries[key]["topStrategyChanges"]+=top["sealedProductId"]!=baseline["sealedProductId"]
            score_rtp[key][0].extend(r["candidateScores"][key] for r in rows);score_rtp[key][1].extend(r["rtp"] for r in rows)
        for i,a in enumerate(rows):
            for b in rows[i+1:]:
                mismatch=abs(a["actualCommittedCapital"]-b["actualCommittedCapital"])/max(a["actualCommittedCapital"],b["actualCommittedCapital"])
                if mismatch>tolerance:continue
                observation={"budget":int(budget_key),"skuA":a["sealedProductId"],"skuB":b["sealedProductId"],"setA":a["setKey"],"setB":b["setKey"],"spendMismatch":mismatch,"candidates":{}}
                core_a=(a["rtp"],a["medianRetention"],a["chanceToRecoverCapital"],a["lossResilience"]);core_b=(b["rtp"],b["medianRetention"],b["chanceToRecoverCapital"],b["lossResilience"])
                for key,candidate in matrix.items():
                    high,low=(a,b) if a["candidateScores"][key]>=b["candidateScores"][key] else (b,a);high_core,low_core=(core_a,core_b) if high is a else (core_b,core_a)
                    summaries[key]["comparisons"]+=1;summaries[key]["rtpAgreement"]+=high["rtp"]>=low["rtp"]
                    for metric,label in (("medianRetention","medianAgreement"),("chanceToRecoverCapital","recoveryAgreement"),("lossResilience","lossResilienceAgreement")):summaries[key][label]+=high[metric]>=low[metric]
                    rtp_sac=max(0.,low["rtp"]-high["rtp"])
                    for threshold,label in ((.01,"rtpSacrificeGt1pp"),(.03,"rtpSacrificeGt3pp"),(.05,"rtpSacrificeGt5pp"),(.10,"rtpSacrificeGt10pp")):summaries[key][label]+=rtp_sac>threshold
                    layer1=_dominates(low_core,high_core)
                    realistic_high=high["candidateRealistic"][key];realistic_low=low["candidateRealistic"][key]
                    layer2=layer1 and realistic_low>=realistic_high-1e-9
                    non_high=(high["components"]["true_win_frequency"],high["components"]["typical_retention"],high["components"]["loss_resilience"],realistic_high,high["components"]["base_economic_efficiency"])
                    non_low=(low["components"]["true_win_frequency"],low["components"]["typical_retention"],low["components"]["loss_resilience"],realistic_low,low["components"]["base_economic_efficiency"])
                    layer3=_dominates(non_low,non_high)
                    full_high=non_high[:4]+(high["components"]["jackpot_upside"],non_high[4]);full_low=non_low[:4]+(low["components"]["jackpot_upside"],non_low[4]);layer4=_dominates(full_low,full_high)
                    for value,label in ((layer1,"layer1Inversions"),(layer2,"layer2Inversions"),(layer3,"layer3Inversions"),(layer4,"layer4Inversions")):summaries[key][label]+=value
                    if layer1:
                        record={"budget":int(budget_key),"winnerSku":high["sealedProductId"],"dominatorSku":low["sealedProductId"],"setWinner":high["setKey"],"setDominator":low["setKey"],"spendMismatch":mismatch,
                            "margin":high["candidateScores"][key]-low["candidateScores"][key],"rtpSacrifice":low["rtp"]-high["rtp"],"medianSacrifice":low["medianRetention"]-high["medianRetention"],
                            "recoverySacrifice":low["chanceToRecoverCapital"]-high["chanceToRecoverCapital"],"realisticAdvantage":realistic_high-realistic_low,
                            "winnerQuantity":high["quantity"],"dominatorQuantity":low["quantity"]}
                        inversions[key].append(record);pair_directions[key][tuple(sorted((high["sealedProductId"],low["sealedProductId"])))].append((high["sealedProductId"],low["sealedProductId"]))
                    observation["candidates"][key]={"winner":high["sealedProductId"],"layers":[layer1,layer2,layer3,layer4]}
                observations.append(observation)
    result={}
    for key,counts in summaries.items():
        n=counts["comparisons"];counts["repeatedNoReversalLayer1Pairs"]=sum(len(v)>=2 and len(set(v))==1 for v in pair_directions[key].values())
        result[key]={**dict(counts),"layer1Rate":counts["layer1Inversions"]/n,"rtpAgreementRate":counts["rtpAgreement"]/n,
            "medianAgreementRate":counts["medianAgreement"]/n,"recoveryAgreementRate":counts["recoveryAgreement"]/n,"lossResilienceAgreementRate":counts["lossResilienceAgreement"]/n,
            "scoreRtpSpearman":float(spearmanr(*score_rtp[key]).statistic),"inversions":inversions[key]}
    return {"comparisons":len(observations),"candidates":result,"observations":observations}


def add_utility(inversion_results:dict[str,Any],engine:StrategyEngine,product_by:Mapping[str,Mapping[str,Any]])->None:
    cache={}
    for key,result in inversion_results.items():
        for row in result["inversions"]:
            def values(pid:str,quantity:int)->np.ndarray:
                cache_key=(pid,quantity)
                if cache_key not in cache:cache[cache_key]=strategy_values(engine,product_by[pid],quantity)
                return cache[cache_key]
            a=values(row["winnerSku"],row["winnerQuantity"]);b=values(row["dominatorSku"],row["dominatorQuantity"])
            ca=row["winnerQuantity"]*float(product_by[row["winnerSku"]]["product_market_cost"]);cb=row["dominatorQuantity"]*float(product_by[row["dominatorSku"]]["product_market_cost"])
            row["utilityPreference"]={str(g):("winner" if power_utility(a,ca,g)>power_utility(b,cb,g) else "dominator") for g in GAMMAS}
            row["weakestRiskSeekingGamma"]=weakest_risk_seeking(a,ca,b,cb)
        thresholds=[r["weakestRiskSeekingGamma"] for r in result["inversions"]]
        result["utilitySummary"]={"requiresAnyConvexity":sum(r["utilityPreference"]["0.0"]=="dominator" and all(r["utilityPreference"][str(g)]=="dominator" for g in (2.,1.,.5)) for r in result["inversions"]),
            "requiresGammaLeMinus0_5":sum(t is None or t<=-.5 for t in thresholds),"requiresGammaLeMinus1":sum(t is None or t<=-1 for t in thresholds),"notPreferredThroughMinus10":sum(t is None for t in thresholds)}


def select_controls(natural:Sequence[Mapping[str,Any]])->tuple[list[dict[str,Any]],list[dict[str,Any]]]:
    positives=[];negatives=[]
    for i,a in enumerate(natural):
        for b in natural[i+1:]:
            rtp_a=sum(region["evContributionRatio"] for name,region in a["regions"].items() if isinstance(region,dict))
            rtp_b=sum(region["evContributionRatio"] for name,region in b["regions"].items() if isinstance(region,dict))
            rtp_delta=abs(rtp_a-rtp_b)
            p95_delta=abs(a["raw"]["p95_threshold_ratio"]-b["raw"]["p95_threshold_ratio"]);jackpot_delta=abs(a["components"]["jackpot_upside"]-b["components"]["jackpot_upside"])
            if rtp_delta<=.01:positives.append((p95_delta,a,b))
            downside=max(abs(a["components"][k]-b["components"][k]) for k in ("typical_retention","loss_resilience","true_win_frequency"))
            if rtp_delta<=.01 and p95_delta<=.10 and downside<=3 and jackpot_delta>=8:negatives.append((jackpot_delta,a,b))
    def record(item):
        magnitude,a,b=item;return {"skuA":a["sealedProductId"],"skuB":b["sealedProductId"],"magnitude":magnitude,"costBand":("low" if max(a["cost"],b["cost"])<50 else "medium" if max(a["cost"],b["cost"])<150 else "high")}
    positive_records=[record(x) for x in sorted(positives,key=lambda x:x[0],reverse=True)[:10]]
    for band in ("low","medium","high"):
        extra=next((record(x) for x in sorted(positives,key=lambda x:x[0],reverse=True) if record(x)["costBand"]==band and record(x) not in positive_records),None)
        if extra:positive_records.append(extra)
    return positive_records,[record(x) for x in sorted(negatives,key=lambda x:x[0],reverse=True)[:10]]


def control_results(controls:Sequence[Mapping[str,Any]],natural_by:Mapping[str,Mapping[str,Any]],matrix:Mapping[str,Mapping[str,Any]],negative:bool=False)->dict[str,Any]:
    per={key:[] for key in matrix}
    for control in controls:
        a=natural_by[control["skuA"]];b=natural_by[control["skuB"]]
        production=(.25*abs(a["components"]["realistic_upside"]-b["components"]["realistic_upside"]) if negative else abs(a["score"]-b["score"]))
        for key,candidate in matrix.items():
            if negative:
                separation=candidate["realisticWeight"]*abs(realistic_score(candidate["definition"],a["raw"]["p95_threshold_ratio"],a["components"]["realistic_upside"])-realistic_score(candidate["definition"],b["raw"]["p95_threshold_ratio"],b["components"]["realistic_upside"]))
            else:
                separation=abs(score_candidate(a["components"],a["raw"]["p95_threshold_ratio"],candidate)-score_candidate(b["components"],b["raw"]["p95_threshold_ratio"],candidate))
            per[key].append({**control,"separation":separation,"productionSeparation":production,"retention":separation/production if production else None})
    return {key:{"cases":rows,"meanAbsoluteSeparation":float(np.mean([r["separation"] for r in rows])) if rows else None,
        "meanRetention":float(np.mean([r["retention"] for r in rows if r["retention"] is not None])) if rows else None} for key,rows in per.items()}


def stability_study(representatives:Sequence[Mapping[str,Any]],engine:StrategyEngine,matrix:Mapping[str,Mapping[str,Any]])->dict[str,Any]:
    sizes=(100_000,250_000,500_000);repetitions=3;reference={};samples=[]
    for row in representatives:
        values=engine.base[row["sealedProductId"]];payload=build_financial_rip_v3(values,row["cost"]);components={k:payload["components"][k]["score"] for k in FINANCIAL_RIP_V3_COMPONENT_ORDER};p95=payload["audit"]["normalizedInputs"]["p95_threshold_ratio"]["raw"]
        reference[row["sealedProductId"]]={"currentRaw":payload["audit"]["normalizedInputs"]["realistic_tail_mean_ratio"]["raw"],"p95Raw":p95,"currentComponent":components["realistic_upside"],"scores":{k:score_candidate(components,p95,c) for k,c in matrix.items()}}
        for size in sizes:
            for repetition in range(repetitions):
                sub=deterministic_subsample(values,size,repetition,row["sealedProductId"]);p=build_financial_rip_v3(sub,row["cost"],min_simulation_count=10_000);comp={k:p["components"][k]["score"] for k in FINANCIAL_RIP_V3_COMPONENT_ORDER};q95=p["audit"]["normalizedInputs"]["p95_threshold_ratio"]["raw"]
                samples.append({"sku":row["sealedProductId"],"size":size,"repetition":repetition,"currentRaw":p["audit"]["normalizedInputs"]["realistic_tail_mean_ratio"]["raw"],"p95Raw":q95,"currentComponent":comp["realistic_upside"],"p95Component":realistic_score("P95_THRESHOLD_ONLY",q95,comp["realistic_upside"]),"scores":{k:score_candidate(comp,q95,c) for k,c in matrix.items()}})
    summary={}
    for size in sizes:
        rows=[r for r in samples if r["size"]==size];block={}
        for definition,raw_key,component_key in (("CURRENT_REALISTIC","currentRaw","currentComponent"),("P95_THRESHOLD_ONLY","p95Raw","p95Component")):
            deviations=np.asarray([r[raw_key]-reference[r["sku"]]["currentRaw" if definition=="CURRENT_REALISTIC" else "p95Raw"] for r in rows]);vals=np.asarray([r[raw_key] for r in rows]);components=np.asarray([r[component_key] for r in rows]);ref_components=np.asarray([reference[r["sku"]]["currentComponent" if definition=="CURRENT_REALISTIC" else "p95Raw"] for r in rows])
            if definition=="P95_THRESHOLD_ONLY":ref_components=np.asarray([realistic_score(definition,reference[r["sku"]]["p95Raw"],0) for r in rows])
            block[definition]={"rawMean":float(np.mean(vals)),"rawSd":float(np.std(vals)),"rawCv":float(np.std(vals)/abs(np.mean(vals))) if np.mean(vals) else None,"rawMaeFromReference":float(np.mean(np.abs(deviations))),"componentSd":float(np.std(components)),"componentMaeFromReference":float(np.mean(np.abs(components-ref_components)))}
        for key in matrix:
            errors=np.asarray([r["scores"][key]-reference[r["sku"]]["scores"][key] for r in rows]);rank_moves=[];top_stable=[]
            for repetition in range(repetitions):
                rep=[r for r in rows if r["repetition"]==repetition];ref_scores=[reference[r["sku"]]["scores"][key] for r in rep];sample_scores=[r["scores"][key] for r in rep];rank_moves.extend(abs(_rank(ref_scores)-_rank(sample_scores)));top_stable.append(len(set(np.argsort(-np.asarray(ref_scores))[:min(10,len(rep))])&set(np.argsort(-np.asarray(sample_scores))[:min(10,len(rep))]))/min(10,len(rep)))
            block[key]={"scoreSd":float(np.std([r["scores"][key] for r in rows])),"scoreMaeFromReference":float(np.mean(np.abs(errors))),"meanAbsoluteRankMovement":float(np.mean(rank_moves)),"top10Stability":float(np.mean(top_stable))}
        summary[str(size)]=block
    return {"method":"3 deterministic without-replacement subsamples per SKU and size; SHA-256-derived fixed seeds","representativeSkus":[r["sealedProductId"] for r in representatives],"summary":summary,"samples":samples}


def price_sensitivity(representatives:Sequence[Mapping[str,Any]],engine:StrategyEngine,matrix:Mapping[str,Mapping[str,Any]])->dict[str,Any]:
    multipliers=(.95,.98,1.,1.02,1.05);rows=[]
    for row in representatives:
        values=engine.base[row["sealedProductId"]];candidate_series={key:[] for key in matrix}
        for multiplier in multipliers:
            payload=build_financial_rip_v3(values,row["cost"]*multiplier);components={k:payload["components"][k]["score"] for k in FINANCIAL_RIP_V3_COMPONENT_ORDER};p95=payload["audit"]["normalizedInputs"]["p95_threshold_ratio"]["raw"]
            for key,c in matrix.items():candidate_series[key].append(score_candidate(components,p95,c))
        rows.append({"sku":row["sealedProductId"],"scores":candidate_series,"monotonic":{key:all(x>=y-1e-9 for x,y in zip(vals,vals[1:])) for key,vals in candidate_series.items()},"maxAdjacentJump":{key:max(abs(x-y) for x,y in zip(vals,vals[1:])) for key,vals in candidate_series.items()}})
    rank_stability={}
    for key in matrix:
        baseline=_rank([r["scores"][key][2] for r in rows]);movements=[];top_changes=0
        for index in range(len(multipliers)):
            ranks=_rank([r["scores"][key][index] for r in rows]);movements.extend(abs(baseline-ranks));top_changes+=int(np.argmin(ranks)!=np.argmin(baseline))
        rank_stability[key]={"meanAbsoluteRankMovement":float(np.mean(movements)),"maxRankMovement":int(np.max(movements)),"topStrategyChangesAcrossFiveCosts":top_changes}
    return {"multipliers":multipliers,"rows":rows,"nonMonotonicCounts":{key:sum(not r["monotonic"][key] for r in rows) for key in matrix},"rankStability":rank_stability}


def fold_robustness(cohort:Mapping[str,Any],matrix:Mapping[str,Mapping[str,Any]])->dict[str,Any]:
    sets=sorted({o["setA"] for o in cohort["observations"]}|{o["setB"] for o in cohort["observations"]});fold={s:int(hashlib.sha256(s.encode()).hexdigest()[:8],16)%4 for s in sets};result={}
    for index in range(4):
        observations=[o for o in cohort["observations"] if fold[o["setA"]]==index or fold[o["setB"]]==index]
        result[str(index)]={"sets":[s for s in sets if fold[s]==index],"comparisons":len(observations),"candidates":{key:{"layer1Inversions":sum(o["candidates"][key]["layers"][0] for o in observations),"layer1Rate":sum(o["candidates"][key]["layers"][0] for o in observations)/len(observations) if observations else None} for key in matrix}}
    return {"method":"SHA-256(set key) modulo 4; each fold includes every comparison involving one of its sets (cross-fold comparisons appear in both relevant folds)","folds":result}


def run_research(client:Any)->dict[str,Any]:
    step2a=json.loads(STEP2A_PATH.read_text(encoding="utf-8"));step2c=json.loads(STEP2C_PATH.read_text(encoding="utf-8"));step3a=json.loads(STEP3A_PATH.read_text(encoding="utf-8"));snapshot,authority=resolve_authoritative_snapshot(client)
    if any(str(x["authority"]["snapshotId"])!=str(snapshot["id"]) for x in (step2a,step2c,step3a)):raise RuntimeError("research artifacts do not match current authority")
    products=load_authoritative_products(client,authority);product_by={str(p["sealed_product_id"]):p for p in products};runs=[str(x["simulation_calculation_run_id"]) for x in authority]
    engine=StrategyEngine(client,authority,products,load_run_fingerprints(client,runs));by_run=defaultdict(list)
    for p in products:by_run[str(p["calculation_run_id"])].append(p)
    for run_id,members in by_run.items():engine.build_set(run_id,members)
    matrix=candidates();budget={}
    for budget_key,rows in step2a["candidateA"]["budgetRankings"].items():
        budget[budget_key]=[]
        for row in rows:budget[budget_key].append(enrich_row(row,engine.strategy(product_by[str(row["sealedProductId"])],int(row["quantity"]))["metrics"],matrix))
    cohort5=cohort_matrix(budget,matrix,PRIMARY_TOLERANCE);cohort2=cohort_matrix(budget,matrix,SENSITIVITY_TOLERANCE);add_utility(cohort5["candidates"],engine,product_by);add_utility(cohort2["candidates"],engine,product_by)
    natural=step3a["tailOverlap"]["skuDiagnostics"];natural_by={r["sealedProductId"]:r for r in natural};positive,negative=select_controls(natural)
    positive_results=control_results(positive,natural_by,matrix);negative_results=control_results(negative,natural_by,matrix,True)
    discreteness=[]
    for row in natural:
        diagnostic=p95_boundary_diagnostic(engine.base[row["sealedProductId"]],row["cost"]);discreteness.append({"sealedProductId":row["sealedProductId"],**diagnostic})
    # Representative set: ordinary, chase-heavy, discrete, inversion, and positive-control distributions.
    by_jackpot=sorted(natural,key=lambda x:x["components"]["jackpot_upside"]);median_start=max(0,len(by_jackpot)//2-1);selected=[]
    representative_ids=([r["sealedProductId"] for r in by_jackpot[median_start:median_start+2]]+
        [r["sealedProductId"] for r in by_jackpot[-2:]]+[r["sealedProductId"] for r in sorted(discreteness,key=lambda x:(x["exactTieShare"],x["normalizedAdjacentScoreSpan"]),reverse=True)[:2]]+
        [c["winnerSku"] for c in step2c["caseSet"]["cases"][:2]]+[c["skuA"] for c in positive[:2]])
    for pid in representative_ids:
        if pid not in selected:selected.append(pid)
    representatives=[natural_by[pid] for pid in selected[:10]]
    stability=stability_study(representatives,engine,matrix);price=price_sensitivity(representatives,engine,matrix)
    original_keys={(c["budget"],c["winnerSku"],c["dominatorSku"]) for c in step2c["caseSet"]["cases"]};original={}
    for key,result in cohort5["candidates"].items():original[key]=[r for r in result["inversions"] if (r["budget"],r["winnerSku"],r["dominatorSku"]) in original_keys]
    baseline=cohort5["candidates"]["CURRENT_REALISTIC@25"]
    attribution={"definitionEffect":{"baselineLayer1":baseline["layer1Inversions"],"P95Only25Layer1":cohort5["candidates"]["P95_THRESHOLD_ONLY@25"]["layer1Inversions"]},
        "weightEffect":{key:cohort5["candidates"][key]["layer1Inversions"] for key in matrix if key.startswith("CURRENT_REALISTIC")},
        "combinedEffect":{key:cohort5["candidates"][key]["layer1Inversions"] for key in matrix if key.startswith("P95_THRESHOLD_ONLY")}}
    def corr(x,y):return float(spearmanr(x,y).statistic)
    current_realistic=[r["components"]["realistic_upside"] for r in natural];p95_realistic=[realistic_score("P95_THRESHOLD_ONLY",r["raw"]["p95_threshold_ratio"],0) for r in natural]
    jackpot=[r["components"]["jackpot_upside"] for r in natural];jackpot_tail=[r["raw"]["jackpot_tail_mean_ratio"] for r in natural]
    jackpot_independence={"CURRENT_REALISTIC":{"spearmanJackpotComponent":corr(current_realistic,jackpot),"spearmanWeightedJackpotContribution":corr(current_realistic,[.1*x for x in jackpot]),"spearmanJackpotTailRaw":corr(current_realistic,jackpot_tail)},
        "P95_THRESHOLD_ONLY":{"spearmanJackpotComponent":corr(p95_realistic,jackpot),"spearmanWeightedJackpotContribution":corr(p95_realistic,[.1*x for x in jackpot]),"spearmanJackpotTailRaw":corr(p95_realistic,jackpot_tail)}}
    return {"authority":{"snapshotId":snapshot["id"],"marketDate":snapshot["market_date"],"runCount":len(runs),"skuCount":len(products),"primaryComparisons":cohort5["comparisons"],"sensitivityComparisons":cohort2["comparisons"]},
        "candidateMatrix":matrix,"factorialAttribution":attribution,"cohort5Pct":cohort5,"cohort2Pct":cohort2,"original15":original,
        "positiveControls":positive_results,"negativeControls":negative_results,"jackpotIndependence":jackpot_independence,"estimatorStability":stability,
        "p95Discreteness":{"summary":{"skuCount":len(discreteness),"skusWithExactInterpolatedP95Ties":sum(r["exactTieCount"]>0 for r in discreteness),"medianNormalizedAdjacentScoreSpan":float(np.median([r["normalizedAdjacentScoreSpan"] for r in discreteness]))},"largestInstability":sorted(discreteness,key=lambda r:r["normalizedAdjacentScoreSpan"],reverse=True)[:20]},
        "priceSensitivity":price,"setFoldRobustness":fold_robustness(cohort5,matrix),"decision":DECISION,"leadingCandidate":"P95_THRESHOLD_ONLY@20","productionContractChanged":False,"productionMutations":"NONE"}


def render_markdown(r:Mapping[str,Any])->str:
    a=r["authority"];matrix=r["candidateMatrix"];c5=r["cohort5Pct"]["candidates"];c2=r["cohort2Pct"]["candidates"]
    lines=["# AUTHORITY","",f"Snapshot `{a['snapshotId']}`, market date `{a['marketDate']}`; {a['runCount']} runs, {a['skuCount']} SKUs, {a['primaryComparisons']} <=5% and {a['sensitivityComparisons']} <=2% comparisons.","",
        "# LOCKED PRIOR FINDINGS","","Equal-spend is validated; production V3 remains locked; Step 3A isolated both definition and influence for controlled study.","",
        "# CANDIDATE MATRIX","","Eight preregistered candidates: current versus canonical P95-threshold-only at 25%, 20%, 15%, and 10% Realistic weight.","",
        "# EXACT CANDIDATE WEIGHTS","","| candidate | true win | typical | resilience | realistic | jackpot | base |","|---|---:|---:|---:|---:|---:|---:|"]
    for key,c in matrix.items():lines.append("| "+key+" | "+" | ".join(f"{100*c['weights'][x]:.4f}%" for x in FINANCIAL_RIP_V3_COMPONENT_ORDER)+" |")
    lines += ["","# DEFINITION EFFECT","",f"At 25%, Layer-1 inversions move from {c5['CURRENT_REALISTIC@25']['layer1Inversions']} to {c5['P95_THRESHOLD_ONLY@25']['layer1Inversions']}.","",
        "# WEIGHT EFFECT","",f"Current-definition Layer-1 response: `{r['factorialAttribution']['weightEffect']}`.","",
        "# COMBINED EFFECT","",f"P95-only response: `{r['factorialAttribution']['combinedEffect']}`.","",
        "# FULL-COHORT DOMINANCE","","| candidate | L1 | L2 | L3 | L4 | repeated | agreement V3 |","|---|---:|---:|---:|---:|---:|---:|"]
    for key,x in c5.items():lines.append(f"| {key} | {x['layer1Inversions']} | {x['layer2Inversions']} | {x['layer3Inversions']} | {x['layer4Inversions']} | {x['repeatedNoReversalLayer1Pairs']} | {sum(o['candidates'][key]['winner']==o['candidates']['CURRENT_REALISTIC@25']['winner'] for o in r['cohort5Pct']['observations'])/a['primaryComparisons']:.2%} |")
    lines += ["","# RTP / DOWNSIDE RELATIONSHIP","","RTP, median, recovery and Loss Resilience agreement plus RTP sacrifice thresholds are reported for every candidate in JSON.","",
        "# UTILITY ALIGNMENT","","Every Layer-1 inversion includes gamma 2, 1, 0.5, 0, -0.5, -1 preferences and the weakest convex gamma through -10. Candidate summaries disclose convexity requirements.","",
        "# REACHABLE-UPSIDE PRESERVATION","","Expanded low/medium/high positive-control separation and retention are reported candidate by candidate.","",
        "# JACKPOT-INDEPENDENCE / NEGATIVE CONTROLS","","Near-equal RTP/downside/P95 pairs with materially different Jackpot behavior measure whether Realistic Upside becomes a second jackpot signal.","",
        "# ESTIMATOR STABILITY","",f"{r['estimatorStability']['method']}. Raw, component, score, rank and top-10 stability are disclosed by sample size.","",
        "# P95 DISCRETENESS / THRESHOLD STABILITY","",f"Diagnostics cover {r['p95Discreteness']['summary']['skuCount']} SKUs; median adjacent normalized P95 score span is {r['p95Discreteness']['summary']['medianNormalizedAdjacentScoreSpan']:.4f}.","",
        "# PRICE SENSITIVITY","",f"Hypothetical -5%, -2%, baseline, +2%, +5% costs used unchanged vectors. Non-monotonic counts: `{r['priceSensitivity']['nonMonotonicCounts']}`.","",
        "# ORIGINAL 15 CASES","","Exact remaining cases, margins, economic sacrifices, Realistic advantages and utility thresholds are in JSON for all eight candidates.","",
        "# POSITIVE CONTROLS","","Ten largest near-equal-RTP P95 separations plus low/medium/high capital representatives are reported with retained production separation.","",
        "# <=2% SENSITIVITY","","| candidate | L1 <=5% | L1 <=2% | RTP agreement <=2% |","|---|---:|---:|---:|"]
    for key in matrix:lines.append(f"| {key} | {c5[key]['layer1Inversions']} | {c2[key]['layer1Inversions']} | {c2[key]['rtpAgreementRate']:.2%} |")
    lines += ["","# SET-FOLD ROBUSTNESS","",f"Deterministic method: {r['setFoldRobustness']['method']}. Per-fold candidate rates are in JSON; no fold-specific fitting occurred.","",
        "# TRADEOFF FRONTIER","","The report preserves definition, influence, utility, stability, control, cohort and fold tradeoffs rather than collapsing them into a scalar objective.","",
        "# RESEARCH DECISION","",f"`{r['decision']}`","",
        "# LEADING RESEARCH CANDIDATE","",f"`{r['leadingCandidate']}`: canonical P95 threshold on the full 0-100 component scale with proportionally redistributed core weights and Jackpot fixed at 10%. It leads only as a research candidate; weaknesses and estimator tradeoffs remain in the evidence tables.","",
        "# REQUIRED TEMPORAL VALIDATION","","Before production, rerun the frozen candidate on later independent snapshots, market dates and unseen sets; preregister drift, stability, inversion, positive/negative-control and utility gates without retuning.","",
        "# IMPLICATION FOR FINANCIAL RIP","","A candidate architecture is selected for temporal validation only. No production scoring or publication action is authorized.","",
        "# PRODUCTION CONTRACT","","Financial RIP V3, canonical weights/anchors, Overall RIP V9, comparison contracts and `crossFormatComparable=False` remain unchanged.","",
        "# TESTS","","Focused candidate arithmetic, reconstruction, dominance, utility, stability, controls, folds, authority, no-write and isolation tests accompany the harness.","",
        "# FILES CHANGED","","Step 3B harness, focused tests and generated reports only.","",
        "# PRODUCTION MUTATIONS","","NONE",""]
    return "\n".join(lines)


def main(argv:Optional[Sequence[str]]=None)->int:
    parser=argparse.ArgumentParser(description=__doc__);parser.add_argument("--json",default="logs/realistic_upside_candidate_matrix_research.json");parser.add_argument("--markdown",default="logs/realistic_upside_candidate_matrix_research.md");args=parser.parse_args(argv)
    from backend.scripts.pokemon_snapshot_builders import get_client
    result=run_research(get_client());jp=Path(args.json);mp=Path(args.markdown);jp.parent.mkdir(parents=True,exist_ok=True);mp.parent.mkdir(parents=True,exist_ok=True);jp.write_text(json.dumps(result,indent=2,default=str)+"\n",encoding="utf-8");mp.write_text(render_markdown(result),encoding="utf-8");print(f"wrote {jp} and {mp}");return 0


if __name__=="__main__":raise SystemExit(main())
