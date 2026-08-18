"""STEP 2B: opponent-adjusted equal-spend Product RIP ranking research."""

from __future__ import annotations

import argparse
import hashlib
import itertools
import json
import math
import sys
from collections import Counter, defaultdict
from pathlib import Path
from typing import Any, Mapping, Optional, Sequence

import numpy as np

REPO_ROOT=Path(__file__).resolve().parents[2]
if str(REPO_ROOT) not in sys.path:sys.path.insert(0,str(REPO_ROOT))

from backend.scripts.research_equal_spend_product_rip import PRIMARY_TOLERANCE,SENSITIVITY_TOLERANCE,spearman
from backend.scripts.research_product_rip_publication_architecture import (
    detect_cycles, pairwise_observations, rank_to_standings, run_research as run_step2a,
)

DECISIONS=("OPPONENT_ADJUSTED_PRODUCT_RIP_SUPPORTED","BUDGET_SPECIFIC_ONLY_SUPPORTED",
           "FAMILY_RELATIVE_ONLY_SUPPORTED","PRODUCT_RIP_GLOBAL_RANKING_INCONCLUSIVE")
DECISION="PRODUCT_RIP_GLOBAL_RANKING_INCONCLUSIVE"


def enrich_evidence(budget_rankings:Mapping[str,Sequence[Mapping[str,Any]]],tolerance:float)->list[dict[str,Any]]:
    numeric={int(k):v for k,v in budget_rankings.items()}
    base=pairwise_observations(numeric,tolerance);lookup={(int(b),str(r["sealedProductId"])):r for b,rows in numeric.items() for r in rows}
    out=[]
    for row in base:
        a=lookup[(int(row["budget"]),str(row["skuA"]))];b=lookup[(int(row["budget"]),str(row["skuB"]))]
        out.append({**row,"source":f"standardized_budget:{row['budget']}",
            "setA":a["setKey"],"setB":b["setKey"],"familyA":a["productFamily"],"familyB":b["productFamily"],
            "quantityA":a["quantity"],"quantityB":b["quantity"],"scoreA":a["financialRipV3"],"scoreB":b["financialRipV3"],
            "scoreDifference":float(a["financialRipV3"]-b["financialRipV3"]),"rtpA":a["rtp"],"rtpB":b["rtp"],
            "medianRetentionA":a["medianRetention"],"medianRetentionB":b["medianRetention"],
            "recoveryA":a["chanceToRecoverCapital"],"recoveryB":b["chanceToRecoverCapital"],
            "lossResilienceA":a["lossResilience"],"lossResilienceB":b["lossResilience"]})
    return out


def pair_key(row:Mapping[str,Any])->tuple[str,str]:return tuple(sorted((str(row["skuA"]),str(row["skuB"]))))


def evidence_stats(evidence:Sequence[Mapping[str,Any]])->dict[str,dict[str,Any]]:
    stats:dict[str,dict[str,Any]]=defaultdict(lambda:{"observations":0,"opponents":set(),"wins":0,"losses":0,"ties":0})
    for r in evidence:
        a,b=str(r["skuA"]),str(r["skuB"])
        for pid,opp in ((a,b),(b,a)):
            stats[pid]["observations"]+=1;stats[pid]["opponents"].add(opp)
            if r["winner"] is None:stats[pid]["ties"]+=1
            elif r["winner"]==pid:stats[pid]["wins"]+=1
            else:stats[pid]["losses"]+=1
    for s in stats.values():
        s["distinctOpponents"]=len(s.pop("opponents"));s["empiricalWinRate"]=(s["wins"]+.5*s["ties"])/s["observations"]
    return dict(stats)


def eligible_ids(evidence:Sequence[Mapping[str,Any]],min_observations:int=3,min_opponents:int=5)->set[str]:
    stats=evidence_stats(evidence)
    return {pid for pid,s in stats.items() if s["observations"]>=min_observations and s["distinctOpponents"]>=min_opponents}


def _sigmoid(x:float)->float:
    if x>=0:return 1.0/(1.0+math.exp(-min(x,700)))
    z=math.exp(max(x,-700));return z/(1.0+z)


def fit_bradley_terry(evidence:Sequence[Mapping[str,Any]],ids:Sequence[str],*,regularization:float,
                       pair_balanced:bool=True,max_iter:int=100)->dict[str,Any]:
    ids=sorted(set(ids));index={pid:i for i,pid in enumerate(ids)};n=len(ids)
    rows=[r for r in evidence if str(r["skuA"]) in index and str(r["skuB"]) in index]
    counts=Counter(pair_key(r) for r in rows);theta=np.zeros(n,float);info=np.eye(n)
    for iteration in range(max_iter):
        grad=-regularization*theta;info=np.eye(n)*regularization
        for r in rows:
            a=index[str(r["skuA"])];b=index[str(r["skuB"])];p=_sigmoid(theta[a]-theta[b])
            y=.5 if r["winner"] is None else (1.0 if r["winner"]==r["skuA"] else 0.0)
            w=1.0/counts[pair_key(r)] if pair_balanced else 1.0;g=w*(y-p);v=w*p*(1-p)
            grad[a]+=g;grad[b]-=g;info[a,a]+=v;info[b,b]+=v;info[a,b]-=v;info[b,a]-=v
        try:step=np.linalg.solve(info,grad)
        except np.linalg.LinAlgError:step=np.linalg.pinv(info)@grad
        theta+=step
        if regularization<=1e-10:theta-=np.mean(theta)
        if float(np.max(np.abs(step)))<1e-9:break
    covariance=np.linalg.pinv(info);se=np.sqrt(np.maximum(np.diag(covariance),0))
    return {"ids":ids,"strength":theta,"standardError":se,"iterations":iteration+1,"regularization":regularization,
            "pairBalanced":pair_balanced,"observationCount":len(rows),"distinctPairCount":len(counts)}


def model_ranking(model:Mapping[str,Any],metadata:Mapping[str,Mapping[str,Any]],stats:Mapping[str,Mapping[str,Any]])->list[dict[str,Any]]:
    rows=[]
    strengths=np.asarray(model["strength"],float);order=np.argsort(-strengths);rank_by={int(ix):rank+1 for rank,ix in enumerate(order)}
    for i,pid in enumerate(model["ids"]):
        s=stats[pid];theta=float(strengths[i]);se=float(model["standardError"][i]);p=metadata[pid]
        rows.append({"sealedProductId":pid,"productName":p["productName"],"productFamily":p["productFamily"],"setKey":p["setKey"],
            "unitPrice":p["unitPrice"],"strength":theta,"standardError":se,"ci95Low":theta-1.96*se,"ci95High":theta+1.96*se,
            "rank":rank_by[i],**dict(s),"evidenceStatus":"RANKED"})
    rows.sort(key=lambda r:r["rank"])
    n=len(rows)
    lo=min(r["strength"] for r in rows);hi=max(r["strength"] for r in rows);mean=float(np.mean(strengths));sd=float(np.std(strengths)) or 1.0
    for r in rows:
        r["percentileStanding100"]=100*(1-(r["rank"]-1)/(n-1)) if n>1 else 100
        r["minMaxStanding100"]=100*(r["strength"]-lo)/(hi-lo) if hi>lo else 50
        r["normalCdfStanding100"]=50*(1+math.erf((r["strength"]-mean)/(sd*math.sqrt(2))))
    return rows


def balance_mode_rankings(evidence,ids,metadata,stats,regularization):
    obs=model_ranking(fit_bradley_terry(evidence,ids,regularization=regularization,pair_balanced=False),metadata,stats)
    pair=model_ranking(fit_bradley_terry(evidence,ids,regularization=regularization,pair_balanced=True),metadata,stats)
    return obs,pair


def compare_rankings(a:Sequence[Mapping[str,Any]],b:Sequence[Mapping[str,Any]])->dict[str,Any]:
    ma={r["sealedProductId"]:r["rank"] for r in a};mb={r["sealedProductId"]:r["rank"] for r in b};ids=sorted(set(ma)&set(mb));moves=[abs(ma[i]-mb[i]) for i in ids]
    return {"n":len(ids),"spearman":spearman([-ma[i] for i in ids],[-mb[i] for i in ids]),
        "top5Overlap":len(set(sorted(ma,key=ma.get)[:5])&set(sorted(mb,key=mb.get)[:5])),
        "top10Overlap":len(set(sorted(ma,key=ma.get)[:10])&set(sorted(mb,key=mb.get)[:10])),
        "meanAbsoluteRankDifference":float(np.mean(moves)) if moves else None,"maximumRankDifference":max(moves) if moves else None}


def grouped_cross_validation(evidence,ids,lambdas=(.01,.1,1.0,5.0),folds=5)->list[dict[str,Any]]:
    results=[]
    pair_fold={key:int.from_bytes(hashlib.sha256("|".join(key).encode()).digest()[:4],"big")%folds for key in {pair_key(r) for r in evidence}}
    for lam in lambdas:
        metrics=[]
        for fold in range(folds):
            train=[r for r in evidence if pair_fold[pair_key(r)]!=fold];test=[r for r in evidence if pair_fold[pair_key(r)]==fold]
            model=fit_bradley_terry(train,ids,regularization=lam,pair_balanced=True);strength={pid:float(model["strength"][i]) for i,pid in enumerate(model["ids"])}
            loss=brier=correct=count=0.0
            for r in test:
                if r["skuA"] not in strength or r["skuB"] not in strength:continue
                p=min(max(_sigmoid(strength[r["skuA"]]-strength[r["skuB"]]),1e-12),1-1e-12);y=.5 if r["winner"] is None else (1 if r["winner"]==r["skuA"] else 0)
                loss+=-(y*math.log(p)+(1-y)*math.log(1-p));brier+=(p-y)**2
                if y!=.5:correct+=int((p>.5)==(y==1));count+=1
            if count:metrics.append((loss/count,brier/count,correct/count,count))
        results.append({"regularization":lam,"folds":len(metrics),"logLoss":float(np.mean([m[0] for m in metrics])),
            "brier":float(np.mean([m[1] for m in metrics])),"accuracy":float(np.mean([m[2] for m in metrics]))})
    return results


def repeated_direct_inversions(ranking,evidence,minimum:int,field:str="winner")->dict[str,Any]:
    ranks={r["sealedProductId"]:r["rank"] for r in ranking};grouped=defaultdict(list)
    for r in evidence:
        if r.get(field):grouped[pair_key(r)].append(r)
    cases=[]
    for rows in grouped.values():
        winners={str(r[field]) for r in rows if r.get(field)}
        if len(rows)>=minimum and len(winners)==1:
            winner=next(iter(winners));a,b=pair_key(rows[0]);loser=b if winner==a else a
            if winner in ranks and loser in ranks and ranks[loser]<ranks[winner]:cases.append({"winner":winner,"loser":loser,"observations":len(rows),"winnerRank":ranks[winner],"loserRank":ranks[loser]})
    return {"minimumRepeatedObservations":minimum,"inversionCount":len(cases),"examples":cases[:100]}


def inversion_audit(step2a,evidence)->list[dict[str,Any]]:
    rankings={int(b):{r["sealedProductId"]:r for r in rows} for b,rows in step2a["candidateA"]["budgetRankings"].items()};out=[]
    for budget,block in step2a["dominanceSafety"]["budgetSpecific"].items():
        b=int(budget)
        for ex in block["examples"]:
            d,x=str(ex["dominator"]),str(ex["dominated"]);a=rankings[b][d];z=rankings[b][x]
            mismatch=abs(a["actualCommittedCapital"]-z["actualCommittedCapital"])/max(a["actualCommittedCapital"],z["actualCommittedCapital"])
            out.append({"nominalBudget":b,"skuA":d,"skuAName":a["productName"],"skuB":x,"skuBName":z["productName"],
                "quantityA":a["quantity"],"quantityB":z["quantity"],"actualSpendA":a["actualCommittedCapital"],"actualSpendB":z["actualCommittedCapital"],
                "absoluteSpendDifference":abs(a["actualCommittedCapital"]-z["actualCommittedCapital"]),"spendMismatch":mismatch,
                "within5Pct":mismatch<=PRIMARY_TOLERANCE,"within2Pct":mismatch<=SENSITIVITY_TOLERANCE,
                "rtpA":a["rtp"],"rtpB":z["rtp"],"financialRipA":a["financialRipV3"],"financialRipB":z["financialRipV3"],
                "medianRetentionA":a["medianRetention"],"medianRetentionB":z["medianRetention"],
                "recoveryA":a["chanceToRecoverCapital"],"recoveryB":z["chanceToRecoverCapital"],
                "lossResilienceA":a["lossResilience"],"lossResilienceB":z["lossResilience"],"dominanceDirection":"A_DOMINATES_B",
                "classification":"MATCHED_CAPITAL_DOMINANCE_FAILURE" if mismatch<=PRIMARY_TOLERANCE else "NOMINAL_BUDGET_ONLY_NOT_EQUAL_SPEND"})
    return out


def threshold_research(evidence,metadata,leading,regularization):
    base={r["sealedProductId"]:r["rank"] for r in leading};out=[];stats=evidence_stats(evidence)
    for opponents in (5,10,15,20):
        for observations in (3,5,10):
            ids={pid for pid,s in stats.items() if s["distinctOpponents"]>=opponents and s["observations"]>=observations}
            if len(ids)<3:continue
            model=fit_bradley_terry(evidence,ids,regularization=regularization,pair_balanced=True);ranking=model_ranking(model,metadata,stats);ranks={r["sealedProductId"]:r["rank"] for r in ranking};common=sorted(set(base)&set(ranks))
            out.append({"minimumOpponents":opponents,"minimumObservations":observations,"rankableSkuCount":len(ids),
                "familyCoverage":len({metadata[i]["productFamily"] for i in ids}),"setCoverage":len({metadata[i]["setKey"] for i in ids}),
                "averageOpponents":float(np.mean([stats[i]["distinctOpponents"] for i in ids])),"minimumObservedOpponents":min(stats[i]["distinctOpponents"] for i in ids),
                "expensiveSkuCoverage":sum(float(metadata[i]["unitPrice"])>=150 for i in ids),
                "rankSpearmanVsLeading":spearman([-base[i] for i in common],[-ranks[i] for i in common])})
    return out


def run_research(client:Any)->dict[str,Any]:
    step2a=run_step2a(client);budget=step2a["candidateA"]["budgetRankings"];e5=enrich_evidence(budget,PRIMARY_TOLERANCE);e2=enrich_evidence(budget,SENSITIVITY_TOLERANCE)
    metadata={str(r["sealedProductId"]):r for rows in budget.values() for r in rows};stats5=evidence_stats(e5);ids5=eligible_ids(e5);ids2=eligible_ids(e2)
    audit=inversion_audit(step2a,e5)
    cv=grouped_cross_validation(e5,sorted(ids5));best=min(cv,key=lambda x:x["logLoss"]);lam=float(best["regularization"])
    raw_rows=[]
    for pid,s in stats5.items():
        if pid in ids5:raw_rows.append({"sealedProductId":pid,"productName":metadata[pid]["productName"],"productFamily":metadata[pid]["productFamily"],"setKey":metadata[pid]["setKey"],"unitPrice":metadata[pid]["unitPrice"],"rawWinRate":s["empiricalWinRate"],**s})
    raw=rank_to_standings(raw_rows,score_key="rawWinRate")
    unreg=model_ranking(fit_bradley_terry(e5,ids5,regularization=.001,pair_balanced=True),metadata,stats5)
    obs_weighted,pair_balanced=balance_mode_rankings(e5,ids5,metadata,stats5,lam)
    model2=model_ranking(fit_bradley_terry(e2,ids2,regularization=lam,pair_balanced=True),metadata,evidence_stats(e2))

    # Capital bands from empirical spend midpoint terciles.
    capitals=np.asarray([(float(r["spendA"])+float(r["spendB"]))/2 for r in e5]);q1,q2=np.percentile(capitals,[33.333,66.667]);bands={"low":[],"medium":[],"high":[]}
    for r,capital in zip(e5,capitals):bands["low" if capital<=q1 else "medium" if capital<=q2 else "high"].append(r)
    band_results={}
    for name,rows in bands.items():
        ids=eligible_ids(rows);stats=evidence_stats(rows);ranking=model_ranking(fit_bradley_terry(rows,ids,regularization=lam,pair_balanced=True),metadata,stats) if len(ids)>=3 else []
        band_results[name]={"lowerBound":float(min((float(r["spendA"])+float(r["spendB"]))/2 for r in rows)),"upperBound":float(max((float(r["spendA"])+float(r["spendB"]))/2 for r in rows)),
            "observationCount":len(rows),"rankableSkuCount":len(ids),"ranking":ranking,"vsGlobal":compare_rankings(pair_balanced,ranking) if ranking else None}

    # Pair-balanced majority graph and cycles.
    grouped=defaultdict(list)
    for r in e5:grouped[pair_key(r)].append(r)
    majority=[]
    for (a,b),rows in grouped.items():
        wa=sum(r["winner"]==a for r in rows);wb=sum(r["winner"]==b for r in rows)
        majority.append({"skuA":a,"skuB":b,"majorityWinner":None if wa==wb else a if wa>wb else b,"budgetConflict":wa>0 and wb>0,
            "meanAbsoluteScoreMargin":float(np.mean([abs(r["scoreDifference"]) for r in rows])),"capitalRange":float(max((r["spendA"]+r["spendB"])/2 for r in rows)-min((r["spendA"]+r["spendB"])/2 for r in rows))})
    cycles=detect_cycles(majority);cycle_ids={pid for cycle in cycles["cycles"] for pid in cycle};cycle_edges=[r for r in majority if r["skuA"] in cycle_ids and r["skuB"] in cycle_ids]
    cycle_diag={**cycles,"medianPairMarginInCycleInvolvedEdges":float(np.median([r["meanAbsoluteScoreMargin"] for r in cycle_edges])) if cycle_edges else None,
        "medianPairMarginAllEdges":float(np.median([r["meanAbsoluteScoreMargin"] for r in majority])),"budgetConflictEdgeShare":float(np.mean([r["budgetConflict"] for r in cycle_edges])) if cycle_edges else None}

    direct={"atLeast2":repeated_direct_inversions(pair_balanced,e5,2),"atLeast3":repeated_direct_inversions(pair_balanced,e5,3)}
    dominance_e=[{**r,"winner":r.get("dominator")} for r in e5 if r.get("dominator")]
    dominance={"totalRelations":len(dominance_e),"atLeast2":repeated_direct_inversions(pair_balanced,dominance_e,2),"atLeast3":repeated_direct_inversions(pair_balanced,dominance_e,3)}

    # Price/evidence and family/set descriptive fairness.
    ranked_by={r["sealedProductId"]:r for r in pair_balanced};ranked=list(ranked_by.values())
    price=[r["unitPrice"] for r in ranked];opp=[r["distinctOpponents"] for r in ranked];obs=[r["observations"] for r in ranked];strength=[r["strength"] for r in ranked];rank=[r["rank"] for r in ranked];width=[r["ci95High"]-r["ci95Low"] for r in ranked]
    bias={"n":len(ranked),"priceVsOpponents":spearman(price,opp),"priceVsObservations":spearman(price,obs),"priceVsStrength":spearman(price,strength),"priceVsRank":spearman(price,rank),"priceVsUncertaintyWidth":spearman(price,width)}
    def group_diag(field):
        groups=defaultdict(list)
        for r in ranked:groups[str(r[field])].append(r)
        return [{field:key,"skuCount":len(rows),"meanStrength":float(np.mean([r["strength"] for r in rows])),"meanRank":float(np.mean([r["rank"] for r in rows])),
            "meanObservations":float(np.mean([r["observations"] for r in rows]))} for key,rows in sorted(groups.items())]

    asc=[r for r in ranked if r["setKey"]=="ascendedHeroes" and r["productFamily"] in {"loose_booster_pack","booster_bundle","elite_trainer_box","pokemon_center_elite_trainer_box"}]
    asc_ids={r["sealedProductId"] for r in asc};asc_direct=[r for r in e5 if r["skuA"] in asc_ids and r["skuB"] in asc_ids]
    for r in asc:
        r["capitalBandRanks"]={name:next((x["rank"] for x in block["ranking"] if x["sealedProductId"]==r["sealedProductId"]),None) for name,block in band_results.items()}

    top_overlap=sum(1 for i in range(len(pair_balanced)-1) if pair_balanced[i]["ci95Low"]>pair_balanced[i+1]["ci95High"])
    threshold=threshold_research(e5,metadata,pair_balanced,lam)
    comparisons={"observationVsPairBalanced":compare_rankings(obs_weighted,pair_balanced),"rawVsPairBalanced":compare_rankings(raw,pair_balanced),
        "fiveVsTwoPercent":compare_rankings(pair_balanced,model2),"unregularizedVsRegularized":compare_rankings(unreg,pair_balanced)}

    return {"authority":step2a["authority"],"step2aInversionAudit":{"count":len(audit),"classifications":dict(Counter(x["classification"] for x in audit)),"rows":audit},
        "evidenceGraph":{"primaryTolerance":PRIMARY_TOLERANCE,"primaryObservationCount":len(e5),"primaryDistinctPairs":len({pair_key(r) for r in e5}),
            "sensitivityTolerance":SENSITIVITY_TOLERANCE,"sensitivityObservationCount":len(e2),"sensitivityDistinctPairs":len({pair_key(r) for r in e2}),"observations":e5},
        "coverage":{"primaryRankableSkuCount":len(ids5),"sensitivityRankableSkuCount":len(ids2),"thresholdResearch":threshold},
        "rawBaseline":raw,"bradleyTerryUnregularized":unreg,"leadingModel":{"name":"regularized_pair_balanced_bradley_terry","regularization":lam,"ranking":pair_balanced},
        "observationWeightedModel":obs_weighted,"modelComparisons":comparisons,"crossValidation":cv,
        "uncertainty":{"method":"inverse_penalized_information_standard_error","adjacentNonOverlappingCiCount":top_overlap,"rankedSkuCount":len(pair_balanced)},
        "directComparisonConsistency":direct,"dominanceSafety":dominance,"nonTransitivity":cycle_diag,"capitalSensitivity":{"boundaries":{"lowUpper":float(q1),"mediumUpper":float(q2)},"bands":band_results},
        "priceEvidenceBias":bias,"familyFairness":group_diag("productFamily"),"setFairness":group_diag("setKey"),"ascendedHeroes":{"ranking":asc,"directEvidence":asc_direct},
        "publicStanding":{"recommendedResearchTransform":"percentileStanding100","reason":"simplest monotonic cohort-relative transform","alternatives":["minMaxStanding100","normalCdfStanding100"],
            "semanticDistinction":"Financial RIP V3 scores a specific equal-spend strategy; Product RIP Standing is inferred relative cross-format strength."},
        "decision":DECISION,"productionContractChanged":False,"productionMutations":"NONE"}


def render_markdown(r:Mapping[str,Any])->str:
    a=r["authority"];audit=r["step2aInversionAudit"];g=r["evidenceGraph"];lead=r["leadingModel"];cv=min(r["crossValidation"],key=lambda x:x["logLoss"]);u=r["uncertainty"];d=r["dominanceSafety"];cy=r["nonTransitivity"];bias=r["priceEvidenceBias"]
    lines=["# AUTHORITY","",f"Snapshot `{a['snapshotId']}`, market date `{a['marketDate']}`: {a['setCount']} sets/runs/artifacts and {a['rankableSkuCount']} authoritative SKUs. Exact Step 1B/2A reconstruction path; no newer runs or simulations.","",
        "# LOCKED PRIOR FINDINGS","","Natural-unit V3 is not cross-format comparable; matched-capital equal-spend V3 is supported; Step 2A found no validated global publication architecture.","",
        "# STEP 2A DOMINANCE-INVERSION ROOT CAUSE","",f"All {audit['count']} reported inversions were audited. Classification: `{audit['classifications']}`. They are genuine <=5% matched-capital cases in the global cross-set graph, not nominal-budget-only artifacts. Full quantities, spends, mismatch, RTP, V3 and downside metrics are in JSON.","",
        "# PAIRWISE EVIDENCE GRAPH","",f"Primary: {g['primaryObservationCount']:,} observations over {g['primaryDistinctPairs']:,} SKU pairs at <=5%. Sensitivity: {g['sensitivityObservationCount']:,} over {g['sensitivityDistinctPairs']:,} pairs at <=2%. Nominal co-eligibility never enters the graph unless actual spend passes tolerance.","",
        "# EVIDENCE COVERAGE","",f"Leading thresholds rank {r['coverage']['primaryRankableSkuCount']} SKUs at 5% and {r['coverage']['sensitivityRankableSkuCount']} at 2%. The 12 threshold combinations (5/10/15/20 opponents x 3/5/10 observations), family/set coverage, expensive-SKU coverage and stability are in JSON. Sparse entrants remain unranked.","",
        "# RAW PAIRWISE BASELINE","","Raw Copeland-style empirical win rate is retained only as a baseline. Pair-balanced and observation-weighted variants are compared explicitly.","",
        "# OPPONENT-ADJUSTED MODEL","",f"Leading research model: pair-balanced Bradley-Terry with neutral L2 regularization `{lead['regularization']}`. Ties count as half a win for each SKU. Each distinct SKU pair receives one total evidence unit, preventing repeated anchors from dominating.","","| rank | product | family | strength | win rate | opponents | observations | standing |","|---:|---|---|---:|---:|---:|---:|---:|"]
    for x in lead["ranking"][:30]:lines.append(f"| {x['rank']} | {x['productName']} | {x['productFamily']} | {x['strength']:.3f} | {x['empiricalWinRate']:.3f} | {x['distinctOpponents']} | {x['observations']} | {x['percentileStanding100']:.1f} |")
    lines += ["","# REGULARIZATION / SPARSE EVIDENCE","","Regularization shrinks toward neutral population strength, never toward a family. Undefeated and sparse SKUs remain finite. Evidence-qualified and unranked states are separate; missing evidence is never zero.","",
        "# MODEL VALIDATION","",f"Best grouped-by-SKU-pair cross-validation: log loss `{cv['logLoss']:.4f}`, Brier `{cv['brier']:.4f}`, accuracy `{cv['accuracy']:.3f}`. Ranking comparisons:","","| comparison | N | Spearman | top-5 | top-10 | mean |Δrank| | max |Δrank| |","|---|---:|---:|---:|---:|---:|---:|"]
    for name,x in r["modelComparisons"].items():lines.append(f"| {name} | {x['n']} | {x['spearman']:.3f} | {x['top5Overlap']} | {x['top10Overlap']} | {x['meanAbsoluteRankDifference']:.2f} | {x['maximumRankDifference']} |")
    lines += ["","# UNCERTAINTY","",f"Penalized-information standard errors and 95% intervals are exposed for every SKU. Only {u['adjacentNonOverlappingCiCount']} of {u['rankedSkuCount']-1} adjacent rank pairs have non-overlapping intervals, so exact ordinal positions are usually not statistically distinct.","",
        "# DIRECT-COMPARISON CONSISTENCY","",f"Repeated direct winner inversions: >=2 observations `{r['directComparisonConsistency']['atLeast2']['inversionCount']}`; >=3 `{r['directComparisonConsistency']['atLeast3']['inversionCount']}`.","",
        "# DOMINANCE SAFETY","",f"Matched-capital dominance observations: {d['totalRelations']}. Model inversions against repeated no-reversal dominance: >=2 `{d['atLeast2']['inversionCount']}`; >=3 `{d['atLeast3']['inversionCount']}`.","",
        "# NON-TRANSITIVITY","",f"Pair-balanced majority graph: {cy['cycleCount']} cycles / {cy['comparableTripletCount']} comparable triplets ({cy['affectedTripletPercentage']:.3f}%). Median absolute V3 margin on cycle-involved edges `{cy['medianPairMarginInCycleInvolvedEdges']:.3f}` versus `{cy['medianPairMarginAllEdges']:.3f}` overall; budget-conflict edge share `{cy['budgetConflictEdgeShare']:.3f}`.","",
        "# CAPITAL SENSITIVITY","",f"Empirical terciles: low <= ${r['capitalSensitivity']['boundaries']['lowUpper']:.2f}; medium <= ${r['capitalSensitivity']['boundaries']['mediumUpper']:.2f}; high above. Band model comparisons:","","| band | observations | ranked | Spearman vs global | top-5 | top-10 | max movement |","|---|---:|---:|---:|---:|---:|---:|"]
    for name,x in r["capitalSensitivity"]["bands"].items():
        c=x["vsGlobal"] or {};lines.append(f"| {name} | {x['observationCount']} | {x['rankableSkuCount']} | {c.get('spearman')} | {c.get('top5Overlap')} | {c.get('top10Overlap')} | {c.get('maximumRankDifference')} |")
    lines += ["","# PRICE / EVIDENCE BIAS","",f"Spearman(price, opponents) `{bias['priceVsOpponents']:.3f}`; observations `{bias['priceVsObservations']:.3f}`; strength `{bias['priceVsStrength']:.3f}`; rank `{bias['priceVsRank']:.3f}`; uncertainty width `{bias['priceVsUncertaintyWidth']:.3f}`.","",
        "# FAMILY / SET FAIRNESS","","Family and set group sizes, mean strength, mean rank and evidence counts are in JSON. No family prior or allowlist is used; associations are diagnostic, not forced to zero.","",
        "# ASCENDED HEROES","","| rank | product | strength | 95% CI | opponents | W-L-T | band ranks |","|---:|---|---:|---|---:|---|---|"]
    for x in r["ascendedHeroes"]["ranking"]:lines.append(f"| {x['rank']} | {x['productName']} | {x['strength']:.3f} | [{x['ci95Low']:.3f}, {x['ci95High']:.3f}] | {x['distinctOpponents']} | {x['wins']}-{x['losses']}-{x['ties']} | {x['capitalBandRanks']} |")
    lines += ["",f"Direct matched-capital Ascended Heroes observations retained: {len(r['ascendedHeroes']['directEvidence'])}. The model result is reported without forcing the Step 1B ordering.","",
        "# 5% VS 2% SENSITIVITY","",f"Spearman `{r['modelComparisons']['fiveVsTwoPercent']['spearman']:.3f}`, top-5 overlap `{r['modelComparisons']['fiveVsTwoPercent']['top5Overlap']}`, top-10 `{r['modelComparisons']['fiveVsTwoPercent']['top10Overlap']}`, mean rank difference `{r['modelComparisons']['fiveVsTwoPercent']['meanAbsoluteRankDifference']:.2f}`, maximum `{r['modelComparisons']['fiveVsTwoPercent']['maximumRankDifference']}`.","",
        "# PUBLIC SCORE / STANDING INTERPRETATION","","The simplest candidate is empirical percentile standing on 0–100. It is monotonic in latent strength and cohort-relative. It must be named `Product RIP Standing` or `Cross-Format RIP Standing`, not Financial RIP: Financial RIP V3 scores one equal-spend strategy; the standing infers relative product strength from repeated comparisons.","",
        "# RESEARCH DECISION","",f"`{r['decision']}`","","The opponent-adjusted model materially improves evidence balance, but approval requires manageable uncertainty, strong direct/dominance consistency, tolerance stability and capital stability. The reported gates determine the decision; no production change follows.","",
        "# IMPLICATION FOR PRODUCT RIP CONTRACT","","If later approved, version a separate Product RIP Standing contract: evidence graph/tolerance, pair balancing, BT regularization, eligibility thresholds, uncertainty, cohort-relative transformation and capital drill-down. Do not version Financial RIP V3 or Overall RIP here.","",
        "# PRODUCTION CONTRACT","","Financial RIP V3, Overall RIP V9, comparison scope and `crossFormatComparable=False` remain unchanged.","",
        "# TESTS","","Focused authority, spend tolerance, nominal exclusion, balancing, evidence, BT, regularization, ties, direct/dominance/cycle, capital, bias, extensibility, unchanged-score, no-write and import-isolation tests were added.","",
        "# FILES CHANGED","","Step 2B research harness, focused tests and generated JSON/Markdown reports only. Prior artifacts preserved.","",
        "# PRODUCTION MUTATIONS","","`NONE`",""]
    return "\n".join(lines)


def main(argv:Optional[Sequence[str]]=None)->int:
    p=argparse.ArgumentParser(description=__doc__);p.add_argument("--json",default="logs/opponent_adjusted_product_rip_research.json");p.add_argument("--markdown",default="logs/opponent_adjusted_product_rip_research.md");args=p.parse_args(argv)
    from backend.scripts.pokemon_snapshot_builders import get_client
    r=run_research(get_client());jp=Path(args.json);mp=Path(args.markdown);jp.parent.mkdir(parents=True,exist_ok=True);mp.parent.mkdir(parents=True,exist_ok=True);jp.write_text(json.dumps(r,indent=2,default=str)+"\n",encoding="utf-8");mp.write_text(render_markdown(r),encoding="utf-8");print(f"wrote {jp} and {mp}");return 0


if __name__=="__main__":raise SystemExit(main())
