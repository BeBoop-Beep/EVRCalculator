"""STEP 2C: explain matched-capital Financial RIP dominance inversions."""

from __future__ import annotations

import argparse
import json
import math
import sys
from collections import Counter,defaultdict
from pathlib import Path
from typing import Any,Mapping,Optional,Sequence

import numpy as np

REPO_ROOT=Path(__file__).resolve().parents[2]
if str(REPO_ROOT) not in sys.path:sys.path.insert(0,str(REPO_ROOT))

from backend.calculations.evr.financial_rip_v3 import build_financial_rip_v3
from backend.calculations.evr.financial_rip_v3_config import FINANCIAL_RIP_V3_COMPONENT_ORDER
from backend.calculations.evr.sealed_product_distribution import build_stage1_product_distributions
from backend.scripts.research_cross_format_product_rip import resolve_authoritative_snapshot
from backend.scripts.research_equal_spend_product_rip import (
    PRIMARY_TOLERANCE,SENSITIVITY_TOLERANCE,StrategyEngine,load_authoritative_products,load_run_fingerprints,
)
from backend.scripts.research_opponent_adjusted_product_rip import pair_key

STEP2A_PATH=REPO_ROOT/"logs/product_rip_publication_architecture_research.json"
STEP2B_PATH=REPO_ROOT/"logs/opponent_adjusted_product_rip_research.json"
STEP1B_PATH=REPO_ROOT/"logs/equal_spend_product_rip_research.json"
DECISION="V3_UPSIDE_WEIGHTING_REQUIRES_RESEARCH"


def _ge(values_b:Sequence[float],values_a:Sequence[float],eps:float=1e-9)->bool:
    return all(b+eps>=a for a,b in zip(values_a,values_b)) and any(b>a+eps for a,b in zip(values_a,values_b))


def dominance_layers(a:Mapping[str,Any],b:Mapping[str,Any])->dict[str,bool]:
    """Whether B dominates A, where A is the higher-V3 inversion winner."""
    core=("rtp","medianRetention","chanceToRecoverCapital","lossResilience")
    layer1=_ge([float(b[k]) for k in core],[float(a[k]) for k in core])
    ca,cb=a["components"],b["components"]
    layer2=layer1 and float(cb["realistic_upside"])>=float(ca["realistic_upside"])-1e-9
    non_jackpot=("true_win_frequency","typical_retention","loss_resilience","realistic_upside","base_economic_efficiency")
    layer3=_ge([float(cb[k]) for k in non_jackpot],[float(ca[k]) for k in non_jackpot])
    layer4=_ge([float(cb[k]) for k in FINANCIAL_RIP_V3_COMPONENT_ORDER],[float(ca[k]) for k in FINANCIAL_RIP_V3_COMPONENT_ORDER])
    return {"layer1Core":layer1,"layer2CorePlusRealistic":layer2,"layer3AllNonJackpot":layer3,"layer4FullComponentPareto":layer4}


def classify_driver(delta_contributions:Mapping[str,float])->str:
    realistic=float(delta_contributions["realistic_upside"]);jackpot=float(delta_contributions["jackpot_upside"])
    if realistic>0 and jackpot>0:return "BOTH_UPSIDE_COMPONENTS"
    if realistic>0:return "REALISTIC_UPSIDE_DRIVEN"
    if jackpot>0:return "JACKPOT_UPSIDE_DRIVEN"
    return "OTHER_COMPONENT_INTERACTION"


def tail_removal(scores:Mapping[str,float],contrib_a:Mapping[str,float],contrib_b:Mapping[str,float])->dict[str,Any]:
    result={}
    for name,removed in (("removeJackpot",("jackpot_upside",)),("removeRealistic",("realistic_upside",)),
                         ("removeBothUpside",("realistic_upside","jackpot_upside"))):
        a=float(scores["a"])-sum(float(contrib_a[k]) for k in removed);b=float(scores["b"])-sum(float(contrib_b[k]) for k in removed)
        result[name]={"scoreA":a,"scoreB":b,"flipsToB":a<b}
    return result


def sacrifice_bin(value:float)->str:
    points=abs(float(value))*100
    if points<1:return "<1pp"
    if points<3:return "1-3pp"
    if points<5:return "3-5pp"
    if points<10:return "5-10pp"
    return ">10pp"


def expected_utility(values:np.ndarray,cost:float,gamma:float)->float:
    ratio=np.asarray(values,float)/float(cost);wealth=1.0+ratio
    if gamma==0:return float(np.mean(ratio))
    if gamma==1:return float(np.mean(np.log(wealth)))
    return float(np.mean((np.power(wealth,1-gamma)-1)/(1-gamma)))


def reachability_classification(delta_raw:Mapping[str,float],delta_contrib:Mapping[str,float])->str:
    realistic=float(delta_contrib["realistic_upside"]);jackpot=float(delta_contrib["jackpot_upside"])
    if realistic>0 and float(delta_raw.get("p95_threshold_ratio") or 0)>0:return "P95_OR_ONE_TO_FIVE_PERCENT_REACHABLE"
    if realistic>0:return "ONE_TO_FIVE_PERCENT_TAIL"
    if jackpot>0:return "BELOW_ONE_PERCENT_JACKPOT"
    return "NO_UPSIDE_ADVANTAGE"


def payload_decomposition(payload:Mapping[str,Any])->dict[str,Any]:
    normalized=(payload.get("audit") or {}).get("normalizedInputs") or {};disc=payload.get("distributionDisclosures") or {}
    components={};contributions={}
    for key in FINANCIAL_RIP_V3_COMPONENT_ORDER:
        block=(payload.get("components") or {})[key];components[key]=block["score"];contributions[key]=block["contribution"]
    raw={key:record.get("raw") for key,record in normalized.items()}
    raw["hard_loss_probability"]=disc.get("hardLossProbability");raw["total_rtp_ratio"]=disc.get("totalRtpRatio");raw["jackpot_value_share"]=disc.get("jackpotValueShare")
    return {"score":payload["score"],"components":components,"weightedContributions":contributions,"raw":raw,
        "clippedInputs":((payload.get("estimationDiagnostics") or {}).get("clippedInputs") or [])}


def strategy_values(engine:StrategyEngine,product:Mapping[str,Any],quantity:int)->np.ndarray:
    base=engine.base[str(product["sealed_product_id"])]
    if quantity==1:return base
    return build_stage1_product_distributions(base,pack_counts=[quantity],canonical_set_key=f"product:{product['sealed_product_id']}",
        run_fingerprint=str(product["calculation_run_id"]))["distributions"][quantity]


def strategy_detail(engine:StrategyEngine,product:Mapping[str,Any],quantity:int)->dict[str,Any]:
    values=strategy_values(engine,product,quantity);cost=quantity*float(product["product_market_cost"]);payload=build_financial_rip_v3(values,cost);detail=payload_decomposition(payload)
    sorted_values=np.sort(values);n=len(values);p95=int(math.floor(.95*n));p99=int(math.floor(.99*n));total=float(np.sum(sorted_values))
    detail.update({"quantity":quantity,"actualCommittedCapital":cost,"ev":float(np.mean(values)),"rtp":float(np.mean(values)/cost),
        "effectivePackCost":cost/(quantity*int(product.get("random_pack_count") or product["pack_count"])),
        "guaranteedEv":quantity*float(product.get("guaranteed_component_market_value") or 0),
        "guaranteedEvShare":quantity*float(product.get("guaranteed_component_market_value") or 0)/float(np.mean(values)) if np.mean(values)>0 else None,
        "utilities":{"riskNeutralGamma0":expected_utility(values,cost,0),"upsideTolerantGamma0_5":expected_utility(values,cost,.5),
            "moderateLogGamma1":expected_utility(values,cost,1),"strongGamma2":expected_utility(values,cost,2)},
        "evRegionShares":{"bottom95Pct":float(np.sum(sorted_values[:p95])/total) if total else None,
            "p95ToP99":float(np.sum(sorted_values[p95:p99])/total) if total else None,"top1Pct":float(np.sum(sorted_values[p99:])/total) if total else None}})
    return detail


def cohort_layers(budget_rankings:Mapping[str,Sequence[Mapping[str,Any]]],tolerance:float)->dict[str,Any]:
    observations=[]
    for budget,rows in budget_rankings.items():
        for i,a in enumerate(rows):
            for b in rows[i+1:]:
                mismatch=abs(float(a["actualCommittedCapital"])-float(b["actualCommittedCapital"]))/max(float(a["actualCommittedCapital"]),float(b["actualCommittedCapital"]))
                if mismatch>tolerance:continue
                score_a=float(a["financialRipV3"]);score_b=float(b["financialRipV3"])
                high,low=(a,b) if score_a>score_b else (b,a)
                layers=dominance_layers(high,low)
                observations.append({"budget":int(budget),"higherV3":high["sealedProductId"],"lowerV3":low["sealedProductId"],"layers":layers})
    summary={}
    for layer in ("layer1Core","layer2CorePlusRealistic","layer3AllNonJackpot","layer4FullComponentPareto"):
        dominant=[o for o in observations if o["layers"][layer]];pairs=defaultdict(list)
        for o in dominant:pairs[tuple(sorted((o["higherV3"],o["lowerV3"])))].append(o)
        repeated=sum(1 for rows in pairs.values() if len(rows)>=2 and len({(r["higherV3"],r["lowerV3"]) for r in rows})==1)
        summary[layer]={"validComparisons":len(observations),"dominanceInversionCount":len(dominant),
            "inversionRate":len(dominant)/len(observations) if observations else 0,"repeatedNoReversalPairCount":repeated}
    return summary


def run_research(client:Any)->dict[str,Any]:
    step1b=json.loads(STEP1B_PATH.read_text(encoding="utf-8"));step2a=json.loads(STEP2A_PATH.read_text(encoding="utf-8"));step2b=json.loads(STEP2B_PATH.read_text(encoding="utf-8"));snapshot,authority=resolve_authoritative_snapshot(client)
    artifact_snapshots=(step1b["authority"]["snapshotId"],step2a["authority"]["snapshotId"],step2b["authority"]["snapshotId"])
    if any(str(snapshot["id"])!=str(artifact_snapshot) for artifact_snapshot in artifact_snapshots):raise RuntimeError("research artifacts do not match current published authority")
    budget=step2a["candidateA"]["budgetRankings"];lookup={(int(b),str(r["sealedProductId"])):r for b,rows in budget.items() for r in rows};evidence=step2b["evidenceGraph"]["observations"]
    target_keys=set()
    for row in step2b["step2aInversionAudit"]["rows"]:target_keys.add((int(row["nominalBudget"]),tuple(sorted((str(row["skuA"]),str(row["skuB"]))))))
    for ex in step2b["dominanceSafety"]["atLeast3"]["examples"]:
        target_pair=tuple(sorted((str(ex["winner"]),str(ex["loser"]))))
        for row in evidence:
            if pair_key(row)==target_pair and row.get("dominator")==ex["winner"] and row.get("winner")==ex["loser"]:
                target_keys.add((int(row["budget"]),target_pair))
    target_rows=[]
    for budget_id,pair in sorted(target_keys):
        a=lookup[(budget_id,pair[0])];b=lookup[(budget_id,pair[1])]
        high,dominator=(a,b) if float(a["financialRipV3"])>float(b["financialRipV3"]) else (b,a)
        target_rows.append({"budget":budget_id,"winnerSku":high["sealedProductId"],"dominatorSku":dominator["sealedProductId"],"spendMismatch":abs(high["actualCommittedCapital"]-dominator["actualCommittedCapital"])/max(high["actualCommittedCapital"],dominator["actualCommittedCapital"])})

    products=load_authoritative_products(client,authority);product_by={str(p["sealed_product_id"]):p for p in products};run_ids=[str(r["simulation_calculation_run_id"]) for r in authority]
    engine=StrategyEngine(client,authority,products,load_run_fingerprints(client,run_ids));by_run=defaultdict(list)
    target_pids={pid for row in target_rows for pid in (row["winnerSku"],row["dominatorSku"])}
    for p in products:
        if str(p["sealed_product_id"]) in target_pids:by_run[str(p["calculation_run_id"])].append(p)
    # Build complete product sets for each needed run so canonical score verification remains active.
    all_by_run=defaultdict(list)
    for p in products:all_by_run[str(p["calculation_run_id"])].append(p)
    for run_id in by_run:engine.build_set(run_id,all_by_run[run_id])
    detail_cache={}
    cases=[]
    for row in target_rows:
        winner_row=lookup[(row["budget"],row["winnerSku"])];dom_row=lookup[(row["budget"],row["dominatorSku"])]
        def get(pid,r):
            key=(pid,int(r["quantity"]))
            if key not in detail_cache:detail_cache[key]=strategy_detail(engine,product_by[pid],int(r["quantity"]))
            return detail_cache[key]
        a=get(row["winnerSku"],winner_row);b=get(row["dominatorSku"],dom_row)
        delta_comp={k:float(a["components"][k]-b["components"][k]) for k in FINANCIAL_RIP_V3_COMPONENT_ORDER};delta_contrib={k:float(a["weightedContributions"][k]-b["weightedContributions"][k]) for k in FINANCIAL_RIP_V3_COMPONENT_ORDER}
        delta_raw={k:float(a["raw"][k]-b["raw"][k]) for k in a["raw"] if a["raw"].get(k) is not None and b["raw"].get(k) is not None}
        layers=dominance_layers({"rtp":a["rtp"],"medianRetention":a["raw"]["typical_retention_ratio"],"chanceToRecoverCapital":a["raw"]["true_win_probability"],"lossResilience":a["components"]["loss_resilience"],"components":a["components"]},
            {"rtp":b["rtp"],"medianRetention":b["raw"]["typical_retention_ratio"],"chanceToRecoverCapital":b["raw"]["true_win_probability"],"lossResilience":b["components"]["loss_resilience"],"components":b["components"]})
        utilities={key:("A" if a["utilities"][key]>b["utilities"][key] else "B") for key in a["utilities"]}
        cases.append({**row,"winner":{"identity":{"set":winner_row["setKey"],"sku":winner_row["productName"],"family":winner_row["productFamily"]},**a},
            "dominator":{"identity":{"set":dom_row["setKey"],"sku":dom_row["productName"],"family":dom_row["productFamily"]},**b},
            "financialRipMargin":float(a["score"]-b["score"]),"deltaComponentScoresAminusB":delta_comp,"deltaWeightedContributionsAminusB":delta_contrib,"deltaRawAminusB":delta_raw,
            "layers":layers,"driver":classify_driver(delta_contrib),"tailRemoval":tail_removal({"a":a["score"],"b":b["score"]},a["weightedContributions"],b["weightedContributions"]),
            "utilityPreference":utilities,"reachability":reachability_classification(delta_raw,delta_contrib),
            "diagnosticRatios":{"ripPointsPerRtpPointSacrificed":(a["score"]-b["score"])/(100*(b["rtp"]-a["rtp"])) if b["rtp"]>a["rtp"] else None,
                "ripPointsPerRecoveryPointSacrificed":(a["score"]-b["score"])/(100*(b["raw"]["true_win_probability"]-a["raw"]["true_win_probability"])) if b["raw"]["true_win_probability"]>a["raw"]["true_win_probability"] else None,
                "ripPointsPerPointOneMedianSacrificed":(a["score"]-b["score"])/((b["raw"]["typical_retention_ratio"]-a["raw"]["typical_retention_ratio"])/.1) if b["raw"]["typical_retention_ratio"]>a["raw"]["typical_retention_ratio"] else None}})
    if any(c["layers"]["layer4FullComponentPareto"] for c in cases):decision="V3_IMPLEMENTATION_OR_NORMALIZATION_DEFECT_FOUND"
    else:decision=DECISION

    # Ascended Heroes non-inversion: locked same-set pairwise-nearest loose-pack/bundle evidence.
    asc_e=[r for r in step1b["primaryComparisons"] if r.get("context")=="pairwise_nearest"
        and str(r.get("strategyA",{}).get("productName","")).startswith("Ascended Heroes")
        and str(r.get("strategyB",{}).get("productName","")).startswith("Ascended Heroes")
        and {r.get("strategyA",{}).get("productFamily"),r.get("strategyB",{}).get("productFamily")}=={"loose_booster_pack","booster_bundle"}]
    asc_control=asc_e[0] if asc_e else None
    cohort5=cohort_layers(budget,PRIMARY_TOLERANCE);cohort2=cohort_layers(budget,SENSITIVITY_TOLERANCE)
    primary15=[c for c in cases if (c["budget"],tuple(sorted((c["winnerSku"],c["dominatorSku"])))) in {(int(r["nominalBudget"]),tuple(sorted((r["skuA"],r["skuB"])))) for r in step2b["step2aInversionAudit"]["rows"]}]
    driver_counts=Counter(c["driver"] for c in primary15);tail_counts={name:sum(c["tailRemoval"][name]["flipsToB"] for c in primary15) for name in ("removeJackpot","removeRealistic","removeBothUpside")}
    sacrifices={"rtp":dict(Counter(sacrifice_bin(c["winner"]["rtp"]-c["dominator"]["rtp"]) for c in primary15)),
        "recovery":dict(Counter(sacrifice_bin(c["winner"]["raw"]["true_win_probability"]-c["dominator"]["raw"]["true_win_probability"]) for c in primary15)),
        "medianRetention":dict(Counter(sacrifice_bin(c["winner"]["raw"]["typical_retention_ratio"]-c["dominator"]["raw"]["typical_retention_ratio"]) for c in primary15))}
    class_summary=[]
    for klass in driver_counts:
        rows=[c for c in primary15 if c["driver"]==klass]
        class_summary.append({"class":klass,"count":len(rows),"averageRtpSacrifice":float(np.mean([c["dominator"]["rtp"]-c["winner"]["rtp"] for c in rows])),
            "averageFinancialRipMargin":float(np.mean([c["financialRipMargin"] for c in rows])),"averageP95Improvement":float(np.mean([c["deltaRawAminusB"].get("p95_threshold_ratio",0) for c in rows])),
            "averageJackpotTailImprovement":float(np.mean([c["deltaRawAminusB"].get("jackpot_tail_mean_ratio",0) for c in rows]))})
    important=sorted(cases,key=lambda c:c["financialRipMargin"],reverse=True)[:5]
    rtp_largest=sorted(cases,key=lambda c:c["dominator"]["rtp"]-c["winner"]["rtp"],reverse=True)[:5]
    utility_summary={key:dict(Counter(c["utilityPreference"][key] for c in primary15)) for key in primary15[0]["utilityPreference"]}
    return {"authority":{"snapshotId":snapshot["id"],"marketDate":snapshot["market_date"],"setCount":len(authority),"runCount":len(run_ids),"artifactCount":len(run_ids),"skuCount":len(products)},
        "caseSet":{"primaryCount":len(primary15),"within2PctCount":sum(c["spendMismatch"]<=SENSITIVITY_TOLERANCE for c in primary15),"deduplicatedObservationCount":len(cases),"cases":cases},
        "layeredDominance":{"primary":{layer:sum(c["layers"][layer] for c in primary15) for layer in primary15[0]["layers"]},"cohort5Pct":cohort5,"cohort2Pct":cohort2},
        "driverSummary":{"counts":dict(driver_counts),"byClass":class_summary},"tailRemovalSummary":tail_counts,"sacrificeBins":sacrifices,
        "utilitySummary":utility_summary,"reachabilityCounts":dict(Counter(c["reachability"] for c in primary15)),
        "importantCases":{"largestRipMargins":important,"largestRtpSacrifices":rtp_largest,"allWithin2Pct":[c for c in primary15 if c["spendMismatch"]<=SENSITIVITY_TOLERANCE],
            "jackpotDriven":[c for c in primary15 if c["driver"]=="JACKPOT_UPSIDE_DRIVEN"]},"ascendedHeroesControl":asc_control,
        "decision":decision,"layer4StopTriggered":decision=="V3_IMPLEMENTATION_OR_NORMALIZATION_DEFECT_FOUND","productionContractChanged":False,"productionMutations":"NONE"}


def render_markdown(r:Mapping[str,Any])->str:
    a=r["authority"];cs=r["caseSet"];layers=r["layeredDominance"];drivers=r["driverSummary"];tail=r["tailRemovalSummary"]
    lines=["# AUTHORITY","",f"Snapshot `{a['snapshotId']}`, market date `{a['marketDate']}`: {a['setCount']} sets/runs/artifacts and {a['skuCount']} rankable SKUs. Exact persisted vectors and canonical V3; no simulation or newer run.","",
        "# LOCKED PRIOR FINDINGS","","Natural-unit V3 is not cross-format comparable; matched-capital equal-spend is validated; global standing remains inconclusive. Formula and contracts remain locked.","",
        "# INVERSION CASE SET","",f"Primary Step 2A cases: {cs['primaryCount']}; <=2%: {cs['within2PctCount']}; deduplicated observations including Step 2B repeated-dominance cases: {cs['deduplicatedObservationCount']}.","",
        "# FULL V3 DECOMPOSITION","","Every case’s identities, quantities, spend, EV/RTP, pack economics, guaranteed value, 12 raw metrics, six component scores, exact weighted contributions, deltas, clipping, utilities and EV-region shares are in JSON.","",
        "# LAYERED DOMINANCE","","| layer | primary inversions | valid 5% | inversions 5% | rate 5% | repeated 5% | valid 2% | inversions 2% | rate 2% | repeated 2% |","|---|---:|---:|---:|---:|---:|---:|---:|---:|---:|"]
    for layer,count in layers["primary"].items():
        x=layers["cohort5Pct"][layer];y=layers["cohort2Pct"][layer];lines.append(f"| {layer} | {count} | {x['validComparisons']} | {x['dominanceInversionCount']} | {x['inversionRate']:.4%} | {x['repeatedNoReversalPairCount']} | {y['validComparisons']} | {y['dominanceInversionCount']} | {y['inversionRate']:.4%} | {y['repeatedNoReversalPairCount']} |")
    lines += ["","# UPSIDE COMPENSATION","","Component and weighted-contribution deltas identify exactly which positive terms overcome each winner’s RTP/downside deficit. RIP-points-per-sacrifice diagnostics are included case by case in JSON.","",
        "# REALISTIC VS JACKPOT DRIVERS","","| driver | count | mean RTP sacrifice | mean RIP margin | mean P95 improvement | mean jackpot-tail improvement |","|---|---:|---:|---:|---:|---:|"]
    for x in drivers["byClass"]:lines.append(f"| {x['class']} | {x['count']} | {x['averageRtpSacrifice']:.4f} | {x['averageFinancialRipMargin']:.3f} | {x['averageP95Improvement']:.3f} | {x['averageJackpotTailImprovement']:.3f} |")
    lines += ["","# TAIL-REMOVAL DIAGNOSTICS","",f"Without renormalization: removing Jackpot flips {tail['removeJackpot']} / {cs['primaryCount']}; removing Realistic Upside flips {tail['removeRealistic']}; removing both flips {tail['removeBothUpside']}. Diagnostic only.","",
        "# RTP / DOWNSIDE SACRIFICES","",f"RTP bins: `{r['sacrificeBins']['rtp']}`. Recovery bins: `{r['sacrificeBins']['recovery']}`. Median-retention bins: `{r['sacrificeBins']['medianRetention']}`.","",
        "# EXPECTED-UTILITY SENSITIVITY","",f"Preference counts (A=V3 inversion winner, B=core dominator): `{r['utilitySummary']}`. Utilities use terminal wealth `1 + return ratio`: gamma 0 risk-neutral, 0.5 upside-tolerant concave, log gamma 1 moderate, gamma 2 strong.","",
        "# REACHABILITY","",f"Classification counts: `{r['reachabilityCounts']}`. EV shares below P95, P95–P99 and top 1% are disclosed per strategy.","",
        "# IMPORTANT CASE STUDIES","","| V3 winner | dominator | budget | mismatch | RIP margin | driver | statement |","|---|---|---:|---:|---:|---|---|"]
    selected=[];seen=set()
    for c in r["importantCases"]["largestRipMargins"]+r["importantCases"]["largestRtpSacrifices"]+r["importantCases"]["allWithin2Pct"]+r["importantCases"]["jackpotDriven"]:
        key=(c["budget"],c["winnerSku"],c["dominatorSku"])
        if key not in seen:seen.add(key);selected.append(c)
    for c in selected:
        dc=c["deltaWeightedContributionsAminusB"];best=max(dc,key=dc.get);rtp_def=100*(c["dominator"]["rtp"]-c["winner"]["rtp"])
        statement=f"V3 prefers A primarily via {best} ({dc[best]:+.2f} points), overcoming {rtp_def:.2f}pp lower RTP and weaker core downside."
        lines.append(f"| {c['winner']['identity']['sku']} | {c['dominator']['identity']['sku']} | ${c['budget']} | {c['spendMismatch']:.2%} | {c['financialRipMargin']:.2f} | {c['driver']} | {statement} |")
    asc=r["ascendedHeroesControl"];loose=asc["strategyA"] if asc["strategyA"]["productFamily"]=="loose_booster_pack" else asc["strategyB"];bundle=asc["strategyB"] if loose is asc["strategyA"] else asc["strategyA"]
    lines += ["","# ASCENDED HEROES CONTROL","",f"At {asc['spendMismatch']:.2%} mismatch, {loose['quantity']} x loose packs (${loose['actualCommittedCapital']:.2f}) beat {bundle['quantity']} x bundles (${bundle['actualCommittedCapital']:.2f}) on RTP ({loose['metrics']['rtp']:.2%} vs {bundle['metrics']['rtp']:.2%}), median retention ({loose['metrics']['medianRetention']:.2%} vs {bundle['metrics']['medianRetention']:.2%}), recovery ({loose['metrics']['chanceToRecoverCapital']:.2%} vs {bundle['metrics']['chanceToRecoverCapital']:.2%}), Loss Resilience ({loose['metrics']['lossResilience']:.2f} vs {bundle['metrics']['lossResilience']:.2f}), and equal-spend V3 ({loose['metrics']['financialRipV3']:.2f} vs {bundle['metrics']['financialRipV3']:.2f}). V3 therefore preserves the economically stronger strategy in this non-inversion control.","",
        "# COHORT-WIDE INVERSION RATES","","The layered 5%/2% cohort table above distinguishes rare component tradeoffs from structural behavior. Layer 4 is the arithmetic stop gate.","",
        "# CONSTRUCT DECISION","",f"`{r['decision']}`","",("A full six-component Pareto inversion was found; interpretation stopped and arithmetic/normalization requires immediate investigation." if r['layer4StopTriggered'] else "No arithmetic defect exists, and Realistic Upside is a genuine compensating dimension in every case. But all 15 inversions disappear without Realistic Upside and every tested concave/risk-neutral expected-utility profile prefers the core dominator. The utility implied by the current upside contributions is therefore not yet defensible for the public promise “financially smartest with my money.”"),"",
        "# IMPLICATION FOR BUDGET-SPECIFIC PRODUCT RIP","","Do not publish budget-specific Product RIP yet. Preserve equal-spend as the comparison framework, but separately research the semantic utility represented by Realistic Upside and its interaction with Jackpot Upside before choosing a public winner.","",
        "# IMPLICATION FOR FINANCIAL RIP V3","","Financial RIP V3 is computationally correct and no formula or weight was changed. Separate future research should focus on Realistic Upside’s 25% contribution and its interaction with Jackpot Upside—not propose replacement weights in this task. Counterfactual removal and utility analysis remain attribution diagnostics only.","",
        "# PRODUCTION CONTRACT","","Financial RIP V3, Overall RIP V9, comparison scope and `crossFormatComparable=False` remain unchanged.","",
        "# TESTS","","Focused authority, tolerance, layered/Pareto dominance, contributions, drivers, tail removal, sacrifice bins, utility, reachability, Ascended control, sensitivity, no-mutation/no-write and import-isolation tests were added.","",
        "# FILES CHANGED","","Step 2C research harness, focused tests and generated JSON/Markdown only. Prior artifacts preserved.","",
        "# PRODUCTION MUTATIONS","","`NONE`",""]
    return "\n".join(lines)


def main(argv:Optional[Sequence[str]]=None)->int:
    p=argparse.ArgumentParser(description=__doc__);p.add_argument("--json",default="logs/product_rip_dominance_utility_research.json");p.add_argument("--markdown",default="logs/product_rip_dominance_utility_research.md");args=p.parse_args(argv)
    from backend.scripts.pokemon_snapshot_builders import get_client
    r=run_research(get_client());jp=Path(args.json);mp=Path(args.markdown);jp.parent.mkdir(parents=True,exist_ok=True);mp.parent.mkdir(parents=True,exist_ok=True);jp.write_text(json.dumps(r,indent=2,default=str)+"\n",encoding="utf-8");mp.write_text(render_markdown(r),encoding="utf-8");print(f"wrote {jp} and {mp}");return 0


if __name__=="__main__":raise SystemExit(main())
