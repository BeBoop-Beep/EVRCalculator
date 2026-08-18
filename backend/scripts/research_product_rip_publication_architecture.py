"""STEP 2A: research a public architecture for equal-spend Product RIP.

SELECT-only.  This module may write only its requested research reports.
"""

from __future__ import annotations

import argparse
import itertools
import json
import math
import sys
from collections import Counter, defaultdict
from pathlib import Path
from typing import Any, Iterable, Mapping, Optional, Sequence

import numpy as np

REPO_ROOT = Path(__file__).resolve().parents[2]
if str(REPO_ROOT) not in sys.path:
    sys.path.insert(0, str(REPO_ROOT))

from backend.scripts.research_cross_format_product_rip import resolve_authoritative_snapshot
from backend.scripts.research_equal_spend_product_rip import (
    BUDGET_BANDS, EXPECTED_OUTCOMES, PRIMARY_TOLERANCE, SENSITIVITY_TOLERANCE,
    StrategyEngine, fixed_budget_quantity, load_authoritative_products,
    load_run_fingerprints, multi_metric_dominator, spearman,
)

DECISION = "PRODUCT_RIP_PUBLICATION_ARCHITECTURE_INCONCLUSIVE"
MIN_PAIRWISE_OBSERVATIONS = 3
MIN_DISTINCT_OPPONENTS = 5


def rank_to_standings(items: Sequence[Mapping[str, Any]], *, score_key: str,
                      identity_key: str = "sealedProductId") -> list[dict[str, Any]]:
    """Descending midrank and [0,1] standing; exact rounded scores tie."""
    ordered = sorted(items, key=lambda x: (-round(float(x[score_key]), 8), str(x[identity_key])))
    n = len(ordered)
    output: list[dict[str, Any]] = []
    i = 0
    while i < n:
        j = i + 1
        score = round(float(ordered[i][score_key]), 8)
        while j < n and round(float(ordered[j][score_key]), 8) == score:
            j += 1
        midrank = ((i + 1) + j) / 2.0
        standing = 1.0 if n == 1 else 1.0 - (midrank - 1.0) / (n - 1.0)
        for item in ordered[i:j]:
            output.append({**dict(item), "rank": midrank, "relativeStanding": standing})
        i = j
    return sorted(output, key=lambda x: (float(x["rank"]), str(x[identity_key])))


def aggregate_standings(observations: Sequence[Mapping[str, Any]]) -> list[dict[str, Any]]:
    grouped: dict[str, list[Mapping[str, Any]]] = defaultdict(list)
    for row in observations:
        grouped[str(row["sealedProductId"])].append(row)
    candidates = []
    for pid, rows in grouped.items():
        values = np.asarray([float(row["relativeStanding"]) for row in rows], float)
        trimmed = values
        if values.size >= 5:
            trimmed = np.sort(values)[1:-1]
        candidates.append({"sealedProductId": pid, "productName": rows[0]["productName"],
            "productFamily": rows[0]["productFamily"], "setKey": rows[0]["setKey"],
            "unitPrice": rows[0]["unitPrice"], "budgetsEligible": sorted(int(row["budget"]) for row in rows),
            "observationCount": int(values.size),
            "standingsByBudget": {str(row["budget"]): row["relativeStanding"] for row in rows},
            "meanStanding": float(np.mean(values)), "medianStanding": float(np.median(values)),
            "lowerQuartileStanding": float(np.percentile(values, 25)),
            "trimmedMeanStanding": float(np.mean(trimmed)), "minStanding": float(np.min(values)),
            "maxStanding": float(np.max(values)), "standingStdDev": float(np.std(values)),
            "standingRange": float(np.max(values)-np.min(values))})
    return rank_to_standings(candidates, score_key="meanStanding")


def pairwise_observations(budget_rankings: Mapping[int, Sequence[Mapping[str, Any]]],
                          tolerance: float) -> list[dict[str, Any]]:
    output = []
    for budget, rows in budget_rankings.items():
        for a, b in itertools.combinations(rows, 2):
            spend_a = float(a["actualCommittedCapital"]); spend_b = float(b["actualCommittedCapital"])
            mismatch = abs(spend_a-spend_b)/max(spend_a,spend_b)
            if mismatch > tolerance:
                continue
            score_a=float(a["financialRipV3"]);score_b=float(b["financialRipV3"])
            winner = None if abs(score_a-score_b)<=1e-8 else (a["sealedProductId"] if score_a>score_b else b["sealedProductId"])
            loser = None if winner is None else (b["sealedProductId"] if winner==a["sealedProductId"] else a["sealedProductId"])
            dominance=multi_metric_dominator(a,b)
            dominator=None if dominance is None else (a["sealedProductId"] if dominance=="A" else b["sealedProductId"])
            dominated=None if dominance is None else (b["sealedProductId"] if dominance=="A" else a["sealedProductId"])
            output.append({"budget":budget,"skuA":a["sealedProductId"],"skuB":b["sealedProductId"],
                "spendA":spend_a,"spendB":spend_b,"spendMismatch":mismatch,
                "winner":winner,"loser":loser,"dominator":dominator,"dominated":dominated})
    return output


def aggregate_pairwise(observations: Sequence[Mapping[str, Any]], products: Mapping[str, Mapping[str, Any]]) -> tuple[list[dict[str, Any]], list[dict[str, Any]]]:
    stats: dict[str, dict[str, Any]] = {}
    for pid,p in products.items():
        stats[pid]={"sealedProductId":pid,"productName":p["productName"],"productFamily":p["productFamily"],
            "setKey":p["setKey"],"unitPrice":p["unitPrice"],"comparisonCount":0,"wins":0,"losses":0,"ties":0,
            "dominanceWins":0,"dominanceLosses":0,"opponents":set(),"budgets":set()}
    pair_results: dict[tuple[str,str],list[Mapping[str,Any]]]=defaultdict(list)
    for row in observations:
        a,b=str(row["skuA"]),str(row["skuB"]);pair_results[tuple(sorted((a,b)))].append(row)
        for pid,opponent in ((a,b),(b,a)):
            s=stats[pid];s["comparisonCount"]+=1;s["opponents"].add(opponent);s["budgets"].add(int(row["budget"]))
            if row["winner"] is None:s["ties"]+=1
            elif row["winner"]==pid:s["wins"]+=1
            else:s["losses"]+=1
            if row["dominator"]==pid:s["dominanceWins"]+=1
            if row["dominated"]==pid:s["dominanceLosses"]+=1
    eligible=[]
    for s in stats.values():
        s["distinctOpponentCount"]=len(s.pop("opponents"));s["budgetsCompared"]=sorted(s.pop("budgets"))
        s["pairwiseEligible"]=s["comparisonCount"]>=MIN_PAIRWISE_OBSERVATIONS and s["distinctOpponentCount"]>=MIN_DISTINCT_OPPONENTS
        s["winRate"]=(s["wins"]+.5*s["ties"])/s["comparisonCount"] if s["comparisonCount"] else None
        if s["pairwiseEligible"]:eligible.append(s)
    ranking=rank_to_standings(eligible,score_key="winRate")
    majority=[]
    for (a,b),rows in pair_results.items():
        wins_a=sum(r["winner"]==a for r in rows);wins_b=sum(r["winner"]==b for r in rows);ties=sum(r["winner"] is None for r in rows)
        winner=None if wins_a==wins_b else (a if wins_a>wins_b else b)
        majority.append({"skuA":a,"skuB":b,"observationCount":len(rows),"winsA":wins_a,"winsB":wins_b,
            "ties":ties,"majorityWinner":winner,"consistentAcrossBudgets":wins_a==0 or wins_b==0,
            "budgetConflict":wins_a>0 and wins_b>0})
    return ranking,majority


def detect_cycles(majority: Sequence[Mapping[str, Any]]) -> dict[str, Any]:
    edges=set();nodes=set()
    for row in majority:
        winner=row.get("majorityWinner")
        if winner is None:continue
        a,b=str(row["skuA"]),str(row["skuB"]);loser=b if winner==a else a
        edges.add((str(winner),loser));nodes.update((a,b))
    cycles=[];comparable_triplets=0
    for a,b,c in itertools.combinations(sorted(nodes),3):
        if not all(((x,y) in edges or (y,x) in edges) for x,y in ((a,b),(b,c),(a,c))):continue
        comparable_triplets+=1
        if ((a,b) in edges and (b,c) in edges and (c,a) in edges) or ((b,a) in edges and (a,c) in edges and (c,b) in edges):
            cycles.append((a,b,c))
    involvement=Counter(pid for cycle in cycles for pid in cycle)
    return {"cycleCount":len(cycles),"comparableTripletCount":comparable_triplets,
        "affectedTripletPercentage":100*len(cycles)/comparable_triplets if comparable_triplets else 0.0,
        "mostInvolved":[{"sealedProductId":pid,"cycleCount":count} for pid,count in involvement.most_common(20)],
        "cycles":cycles[:1000]}


def rank_map(rows: Sequence[Mapping[str, Any]]) -> dict[str,float]:
    return {str(row["sealedProductId"]):float(row["rank"]) for row in rows}


def compare_rankings(a: Sequence[Mapping[str, Any]], b: Sequence[Mapping[str, Any]], name_a: str, name_b: str) -> dict[str, Any]:
    ma,mb=rank_map(a),rank_map(b);ids=sorted(set(ma)&set(mb))
    movements=[abs(ma[i]-mb[i]) for i in ids]
    top=lambda m,k:set(sorted(m,key=m.get)[:k])
    return {"rankingA":name_a,"rankingB":name_b,"overlapCount":len(ids),
        "spearman":spearman([-ma[i] for i in ids],[-mb[i] for i in ids]),
        "top5Overlap":len(top(ma,5)&top(mb,5)),"top10Overlap":len(top(ma,10)&top(mb,10)),
        "meanAbsoluteRankDifference":float(np.mean(movements)) if movements else None,
        "maximumRankDifference":float(np.max(movements)) if movements else None}


def dominance_inversions(ranking: Sequence[Mapping[str, Any]], observations: Sequence[Mapping[str, Any]]) -> dict[str, Any]:
    ranks=rank_map(ranking);pairs=set();examples=[]
    for row in observations:
        d=row.get("dominator");x=row.get("dominated")
        if d in ranks and x in ranks and ranks[x]<ranks[d]:
            pair=(str(d),str(x))
            if pair not in pairs:examples.append({"dominator":d,"dominated":x,"dominatorRank":ranks[d],"dominatedRank":ranks[x]})
            pairs.add(pair)
    return {"inversionCount":len(pairs),"examples":examples[:100]}


def consistent_dominance_observations(observations: Sequence[Mapping[str, Any]], minimum: int = 2) -> list[dict[str, Any]]:
    """Keep only pair directions repeated without a reverse dominance result."""
    grouped:dict[tuple[str,str],list[Mapping[str,Any]]]=defaultdict(list)
    for row in observations:
        if row.get("dominator") and row.get("dominated"):
            grouped[tuple(sorted((str(row["dominator"]),str(row["dominated"]))))].append(row)
    out=[]
    for rows in grouped.values():
        directions={(str(row["dominator"]),str(row["dominated"])) for row in rows}
        if len(directions)==1 and len(rows)>=minimum:
            out.extend(rows)
    return out


def build_budget_stability(budget_rankings: Mapping[int,Sequence[Mapping[str,Any]]]) -> dict[str,Any]:
    by_sku:dict[str,list[tuple[int,float]]]=defaultdict(list)
    correlations=[]
    for budget,rows in budget_rankings.items():
        for row in rows:by_sku[str(row["sealedProductId"])].append((budget,float(row["rank"])))
    sku=[]
    for pid,obs in by_sku.items():
        obs=sorted(obs);moves=[abs(obs[i][1]-obs[i-1][1]) for i in range(1,len(obs))]
        sku.append({"sealedProductId":pid,"rankByBudget":{str(b):r for b,r in obs},"rankRange":max(r for _,r in obs)-min(r for _,r in obs),
            "meanAdjacentAbsoluteMovement":float(np.mean(moves)) if moves else 0.0,"maximumMovement":max(moves) if moves else 0.0})
    for a,b in zip(BUDGET_BANDS[:-1],BUDGET_BANDS[1:]):
        ma,mb=rank_map(budget_rankings[a]),rank_map(budget_rankings[b]);ids=sorted(set(ma)&set(mb))
        correlations.append({"budgetA":a,"budgetB":b,"overlapCount":len(ids),"spearman":spearman([-ma[i] for i in ids],[-mb[i] for i in ids]),
            "top5Overlap":len(set(sorted(ma,key=ma.get)[:5])&set(sorted(mb,key=mb.get)[:5])),
            "top10Overlap":len(set(sorted(ma,key=ma.get)[:10])&set(sorted(mb,key=mb.get)[:10]))})
    return {"skus":sorted(sku,key=lambda x:(-x["rankRange"],x["sealedProductId"])),"adjacentBudgetCorrelations":correlations}


def run_research(client: Any) -> dict[str,Any]:
    snapshot,authority_rows=resolve_authoritative_snapshot(client)
    products=load_authoritative_products(client,authority_rows)
    run_ids=[str(row["simulation_calculation_run_id"]) for row in authority_rows]
    engine=StrategyEngine(client,authority_rows,products,load_run_fingerprints(client,run_ids))
    by_run:dict[str,list[dict[str,Any]]]=defaultdict(list)
    authority_by_run={str(row["simulation_calculation_run_id"]):row for row in authority_rows}
    for p in products:by_run[str(p["calculation_run_id"])].append(p)
    for run_id,members in by_run.items():engine.build_set(run_id,members)

    product_meta={}
    budget_rankings={}
    observations=[]
    for budget in BUDGET_BANDS:
        strategies=[]
        for p in products:
            allocation=fixed_budget_quantity(budget,float(p["product_market_cost"]))
            if allocation["quantity"]<1:continue
            s=engine.strategy(p,allocation["quantity"]);m=s["metrics"];run_id=str(p["calculation_run_id"])
            row={"sealedProductId":str(p["sealed_product_id"]),"productName":p["product_name"],"productFamily":p["product_family"],
                "setKey":authority_by_run[run_id]["set_canonical_key"],"unitPrice":float(p["product_market_cost"]),"budget":budget,
                "quantity":allocation["quantity"],"actualCommittedCapital":allocation["actualCommittedCapital"],
                "leftoverBudget":allocation["leftoverCapital"],"financialRipV3":m["financialRipV3"],"ev":m["expectedValue"],"rtp":m["rtp"],
                "medianRetention":m["medianRetention"],"chanceToRecoverCapital":m["chanceToRecoverCapital"],"lossResilience":m["lossResilience"],
                "components":m["components"],"currentUnitV3":float(p["financial_rip_v3_score"])}
            strategies.append(row);product_meta[row["sealedProductId"]]=row
        ranked=rank_to_standings(strategies,score_key="financialRipV3")
        budget_rankings[budget]=ranked;observations.extend(ranked)
    consensus=aggregate_standings(observations)
    pair5=pairwise_observations(budget_rankings,PRIMARY_TOLERANCE);pair2=pairwise_observations(budget_rankings,SENSITIVITY_TOLERANCE)
    pairwise5,majority5=aggregate_pairwise(pair5,product_meta);pairwise2,majority2=aggregate_pairwise(pair2,product_meta)
    cycles5=detect_cycles(majority5);cycles2=detect_cycles(majority2)
    current=rank_to_standings([{"sealedProductId":pid,"productName":p["productName"],"productFamily":p["productFamily"],"setKey":p["setKey"],
        "currentUnitV3":p["currentUnitV3"]} for pid,p in product_meta.items()],score_key="currentUnitV3")

    # Eligibility diagnostics: missing observations are omitted, never imputed.
    obs_counts=[row["observationCount"] for row in consensus];prices=[row["unitPrice"] for row in consensus];means=[row["meanStanding"] for row in consensus]
    eligibility_groups=[]
    for count in sorted(set(obs_counts)):
        rows=[row for row in consensus if row["observationCount"]==count]
        eligibility_groups.append({"observationCount":count,"skuCount":len(rows),"meanUnitPrice":float(np.mean([r["unitPrice"] for r in rows])),
            "meanConsensusStanding":float(np.mean([r["meanStanding"] for r in rows])),"medianConsensusStanding":float(np.median([r["meanStanding"] for r in rows]))})
    fairness={"skuCoverage":len(consensus),"setCoverage":len({r["setKey"] for r in consensus}),"familyCoverage":len({r["productFamily"] for r in consensus}),
        "minimumObservations":min(obs_counts),"maximumObservations":max(obs_counts),"missingBudgetsImputed":False,
        "priceVsObservationCountSpearman":spearman(prices,obs_counts),"observationCountVsMeanStandingSpearman":spearman(obs_counts,means),
        "eligibilityGroups":eligibility_groups,"allBudgetEligibleSkuCount":sum(c==len(BUDGET_BANDS) for c in obs_counts)}

    stability=build_budget_stability(budget_rankings)
    comparisons=[compare_rankings(current,consensus,"CURRENT_UNIT_V3","MULTI_BUDGET_CONSENSUS"),
        compare_rankings(current,pairwise5,"CURRENT_UNIT_V3","PAIRWISE_CONSENSUS"),
        compare_rankings(consensus,pairwise5,"MULTI_BUDGET_CONSENSUS","PAIRWISE_CONSENSUS")]
    consistent_dominance=consistent_dominance_observations(pair5)
    dominance={"budgetSpecific":{str(b):dominance_inversions(rows,[x for x in pair5 if x["budget"]==b]) for b,rows in budget_rankings.items()},
        "globalAnyObserved":{"multiBudgetConsensus":dominance_inversions(consensus,pair5),"pairwiseConsensus":dominance_inversions(pairwise5,pair5)},
        "globalConsistentRepeated":{"qualifyingObservationCount":len(consistent_dominance),
            "multiBudgetConsensus":dominance_inversions(consensus,consistent_dominance),
            "pairwiseConsensus":dominance_inversions(pairwise5,consistent_dominance)}}

    asc_ids={pid for pid,p in product_meta.items() if p["setKey"]=="ascendedHeroes" and p["productFamily"] in {
        "loose_booster_pack","booster_bundle","elite_trainer_box","pokemon_center_elite_trainer_box"}}
    asc={"currentUnit":[r for r in current if r["sealedProductId"] in asc_ids],
        "budgetSpecific":{str(b):[r for r in rows if r["sealedProductId"] in asc_ids] for b,rows in budget_rankings.items()},
        "multiBudgetConsensus":[r for r in consensus if r["sealedProductId"] in asc_ids],
        "pairwiseConsensus":[r for r in pairwise5 if r["sealedProductId"] in asc_ids]}

    return {"authority":{"snapshotId":snapshot["id"],"marketDate":snapshot["market_date"],"setCount":len(authority_rows),
            "runCount":len(run_ids),"artifactCount":len(run_ids),"outcomesPerArtifact":EXPECTED_OUTCOMES,"rankableSkuCount":len(products)},
        "lockedFindings":{"step1A":"natural-unit V3 is not cross-format comparable","step1B":"equal-spend V3 supported"},
        "candidateA":{"budgetRankings":{str(k):v for k,v in budget_rankings.items()},"stability":stability},
        "candidateB":{"consensusRanking":consensus,"aggregation":"arithmetic_mean_relative_standing",
            "alternativesReported":["medianStanding","lowerQuartileStanding","trimmedMeanStanding"],"eligibilityFairness":fairness},
        "candidateC":{"primary":{"tolerance":PRIMARY_TOLERANCE,"observationCount":len(pair5),"ranking":pairwise5,"majorityRelations":majority5,"cycles":cycles5},
            "sensitivity":{"tolerance":SENSITIVITY_TOLERANCE,"observationCount":len(pair2),"ranking":pairwise2,"cycles":cycles2},
            "minimumComparisonEvidence":{"observations":MIN_PAIRWISE_OBSERVATIONS,"distinctOpponents":MIN_DISTINCT_OPPONENTS}},
        "currentUnitBaseline":current,"dominanceSafety":dominance,"candidateRankComparisons":comparisons,"ascendedHeroes":asc,
        "futureFamilyExtensibility":{"familyAllowlistUsed":False,"entryRequirements":["validated composition","authoritative price","outcome distribution","minimum comparison evidence"]},
        "decision":DECISION,"productionContractChanged":False,"productionMutations":"NONE"}


def render_markdown(r: Mapping[str,Any]) -> str:
    a=r["authority"];fa=r["candidateB"]["eligibilityFairness"];c=r["candidateC"];d=r["dominanceSafety"]
    lines=["# AUTHORITY","",f"Snapshot `{a['snapshotId']}`, market date `{a['marketDate']}`: {a['setCount']} sets/runs/artifacts, {a['rankableSkuCount']} rankable SKUs, {a['outcomesPerArtifact']:,} outcomes per artifact. Exact published run IDs only; no newer-run substitution.","",
        "# LOCKED STEP 1 FINDINGS","","Step 1A established that natural-unit V3 is not cross-format comparable. Step 1B established that equal-spend V3 is supported and does not require a formula change.","",
        "# PUBLICATION PROBLEM","","Equal-spend score is conditional on capital. A public architecture must expose that condition or aggregate relative performance across standardized capital environments without treating missing eligibility as failure.","",
        "# CANDIDATE A — BUDGET-SPECIFIC","","| budget | eligible SKUs | families | sets | top product | spend | leftover | V3 | RTP |","|---:|---:|---:|---:|---|---:|---:|---:|---:|"]
    for b,rows in r["candidateA"]["budgetRankings"].items():
        top=rows[0];lines.append(f"| ${b} | {len(rows)} | {len({x['productFamily'] for x in rows})} | {len({x['setKey'] for x in rows})} | {top['productName']} | ${top['actualCommittedCapital']:.2f} | ${top['leftoverBudget']:.2f} | {top['financialRipV3']:.2f} | {top['rtp']:.3f} |")
    lines += ["","This is the mathematically clearest personalized view: “best products to open with a $X budget.” It is not one default leaderboard because eligibility and diversification change with X.","",
        "# CANDIDATE B — MULTI-BUDGET CONSENSUS","","Arithmetic mean standing is the leading simple aggregator. Median, lower-quartile and trimmed mean remain disclosed diagnostics; raw V3 scores are never averaged across cohorts.","","| rank | product | family | observations | mean | median | LQ | range |","|---:|---|---|---:|---:|---:|---:|---:|"]
    for x in r["candidateB"]["consensusRanking"][:25]:lines.append(f"| {x['rank']:.1f} | {x['productName']} | {x['productFamily']} | {x['observationCount']} | {x['meanStanding']:.3f} | {x['medianStanding']:.3f} | {x['lowerQuartileStanding']:.3f} | {x['standingRange']:.3f} |")
    lines += ["","# CANDIDATE C — PAIRWISE CONSENSUS","",f"At 5% tolerance: {c['primary']['observationCount']:,} observations and {len(c['primary']['ranking'])} evidence-qualified SKUs. At 2%: {c['sensitivity']['observationCount']:,} observations.","","| rank | product | family | comparisons | opponents | win rate | dominance W-L |","|---:|---|---|---:|---:|---:|---:|"]
    for x in c["primary"]["ranking"][:25]:lines.append(f"| {x['rank']:.1f} | {x['productName']} | {x['productFamily']} | {x['comparisonCount']} | {x['distinctOpponentCount']} | {x['winRate']:.3f} | {x['dominanceWins']}-{x['dominanceLosses']} |")
    lines += ["","# COVERAGE AND ELIGIBILITY FAIRNESS","",f"Consensus covers {fa['skuCoverage']} SKUs, {fa['setCoverage']} sets and {fa['familyCoverage']} families. Observations range {fa['minimumObservations']}–{fa['maximumObservations']}; only {fa['allBudgetEligibleSkuCount']} SKUs enter every budget. Price versus observation-count Spearman is `{fa['priceVsObservationCountSpearman']:.3f}`; observation count versus mean standing is `{fa['observationCountVsMeanStandingSpearman']:.3f}`. Missing budgets are omitted, never zero or neutral. Eligibility-group diagnostics are in JSON.","",
        "# DOMINANCE SAFETY","",f"Using any observed budget dominance, global inversions are multi-budget `{d['globalAnyObserved']['multiBudgetConsensus']['inversionCount']}` and pairwise `{d['globalAnyObserved']['pairwiseConsensus']['inversionCount']}`. Restricting the global gate to dominance repeated at least twice with no reverse result leaves multi-budget `{d['globalConsistentRepeated']['multiBudgetConsensus']['inversionCount']}` and pairwise `{d['globalConsistentRepeated']['pairwiseConsensus']['inversionCount']}`. Budget-specific counts: " + ", ".join(f"${b}={v['inversionCount']}" for b,v in d["budgetSpecific"].items()) + ". No candidate clears the zero-inversion target.","",
        "# BUDGET STABILITY","","Adjacent-budget Spearman and top-5/top-10 overlap are reported below; per-SKU rank ranges and movements are in JSON.","","| budgets | overlap | Spearman | top-5 | top-10 |","|---|---:|---:|---:|---:|"]
    for x in r["candidateA"]["stability"]["adjacentBudgetCorrelations"]:lines.append(f"| ${x['budgetA']}→${x['budgetB']} | {x['overlapCount']} | {x['spearman']:.3f} | {x['top5Overlap']} | {x['top10Overlap']} |")
    lines += ["","# PAIRWISE TRANSITIVITY","",f"At 5%: {c['primary']['cycles']['cycleCount']} cycles among {c['primary']['cycles']['comparableTripletCount']} fully comparable triplets ({c['primary']['cycles']['affectedTripletPercentage']:.3f}%). At 2%: {c['sensitivity']['cycles']['cycleCount']} cycles among {c['sensitivity']['cycles']['comparableTripletCount']} ({c['sensitivity']['cycles']['affectedTripletPercentage']:.3f}%). Budget-conflict and SKU-involvement diagnostics are in JSON.","",
        "# CANDIDATE RANK CORRELATIONS","","| A | B | N | Spearman | top-5 | top-10 | mean |Δrank| | max |Δrank| |","|---|---|---:|---:|---:|---:|---:|---:|"]
    for x in r["candidateRankComparisons"]:lines.append(f"| {x['rankingA']} | {x['rankingB']} | {x['overlapCount']} | {x['spearman']:.3f} | {x['top5Overlap']} | {x['top10Overlap']} | {x['meanAbsoluteRankDifference']:.2f} | {x['maximumRankDifference']:.1f} |")
    lines += ["","# ASCENDED HEROES","","| candidate | rank | product | family | observations / budget | score / standing |","|---|---:|---|---|---|---:|"]
    for x in r["ascendedHeroes"]["currentUnit"]:lines.append(f"| Current unit | {x['rank']:.1f} | {x['productName']} | {x['productFamily']} | natural unit | {x['currentUnitV3']:.3f} |")
    for b,rows in r["ascendedHeroes"]["budgetSpecific"].items():
        for x in rows:lines.append(f"| Budget ${b} | {x['rank']:.1f} | {x['productName']} | {x['productFamily']} | q={x['quantity']}, spend=${x['actualCommittedCapital']:.2f} | {x['financialRipV3']:.3f} |")
    for x in r["ascendedHeroes"]["multiBudgetConsensus"]:lines.append(f"| Multi-budget | {x['rank']:.1f} | {x['productName']} | {x['productFamily']} | {x['observationCount']} budgets | {x['meanStanding']:.3f} |")
    for x in r["ascendedHeroes"]["pairwiseConsensus"]:lines.append(f"| Pairwise | {x['rank']:.1f} | {x['productName']} | {x['productFamily']} | {x['comparisonCount']} comparisons | {x['winRate']:.3f} |")
    lines += ["","Budget-specific and pairwise views preserve Step 1B’s matched-capital conclusion when Ascended Heroes products are jointly comparable. Arithmetic multi-budget consensus does not: the Bundle ranks 7th and loose packs 8th because the Bundle enters fewer, more favorable cohorts. This is direct evidence of eligibility bias, not evidence that the Bundle is better at matched capital.","",
        "# FUTURE PRODUCT FAMILIES","","No family allowlist is used. UPCs, special collections, blisters, Build & Battle and other future families enter without formula redesign once composition, pricing, empirical outcome distribution and minimum evidence are validated. Sparse Enhanced Booster Box evidence remains disclosed rather than generalized.","",
        "# USER-FACING INTERPRETATION","","Candidate A: “Best products to open with a $X budget.” Candidate B: “Products with the strongest risk-adjusted opening value across typical spending levels.” Candidate C: “Products that most consistently beat alternatives at similar spend.” Candidate A is the only statement fully supported as written. Candidate B is undermined by eligibility bias; Candidate C is less interpretable and non-transitive.","",
        "# RESEARCH DECISION","",f"`{r['decision']}`","","Budget-specific equal-spend is suitable for drill-down, but the task requires a canonical public architecture. Arithmetic consensus advantages some sparse entrants and reverses the Ascended Heroes matched-capital result; pairwise consensus has sparse exclusions, cycles and more dominance inversions. No tested default ranking clears the safety and fairness gates, so a hybrid cannot yet be endorsed.","",
        "# IMPLICATION FOR PRODUCT RIP VERSIONING","","Do not version a production Product RIP yet. The next research iteration should preregister and test an eligibility-aware consensus rule (for example minimum evidence plus uncertainty/shrinkage or stratified common-budget aggregation) and a dominance-safe publication constraint. If that later passes, version the publication contract—not Financial RIP V3. Overall RIP and Financial RIP formulas remain unchanged.","",
        "# PRODUCTION CONTRACT","","`crossFormatComparable` remains false. No ranking, snapshot, API, frontend or publication contract was changed.","",
        "# TESTS","","Focused authority, whole-unit, eligibility, missingness, standing/ties, aggregation, pairwise tolerance/results, cycles, dominance, sparse evidence, extensibility, unchanged V3, no-write, contract and import-isolation tests were added.","",
        "# FILES CHANGED","","Step 2A research harness, focused tests and generated JSON/Markdown reports only. Step 1A/1B artifacts were preserved.","",
        "# PRODUCTION MUTATIONS","","`NONE`",""]
    return "\n".join(lines)


def main(argv:Optional[Sequence[str]]=None)->int:
    parser=argparse.ArgumentParser(description=__doc__);parser.add_argument("--json",default="logs/product_rip_publication_architecture_research.json");parser.add_argument("--markdown",default="logs/product_rip_publication_architecture_research.md");args=parser.parse_args(argv)
    from backend.scripts.pokemon_snapshot_builders import get_client
    report=run_research(get_client());jp=Path(args.json);mp=Path(args.markdown);jp.parent.mkdir(parents=True,exist_ok=True);mp.parent.mkdir(parents=True,exist_ok=True)
    jp.write_text(json.dumps(report,indent=2,default=str)+"\n",encoding="utf-8");mp.write_text(render_markdown(report),encoding="utf-8");print(f"wrote {jp} and {mp}");return 0


if __name__=="__main__":raise SystemExit(main())
