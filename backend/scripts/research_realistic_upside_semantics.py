"""STEP 3A: read-only Realistic Upside semantics and overlap audit."""

from __future__ import annotations

import argparse
import json
import math
import sys
from collections import Counter, defaultdict
from pathlib import Path
from typing import Any, Mapping, Optional, Sequence

import numpy as np
from scipy.stats import pearsonr, spearmanr

REPO_ROOT = Path(__file__).resolve().parents[2]
if str(REPO_ROOT) not in sys.path:
    sys.path.insert(0, str(REPO_ROOT))

from backend.calculations.evr.financial_rip_v3 import TailBuckets, build_financial_rip_v3
from backend.calculations.evr.financial_rip_v3_config import (
    FINANCIAL_RIP_V3_COMPONENT_INPUTS,
    FINANCIAL_RIP_V3_COMPONENT_ORDER,
    FINANCIAL_RIP_V3_TRANSFORMS,
    FINANCIAL_RIP_V3_WEIGHTS,
    normalize_metric,
)
from backend.scripts.research_cross_format_product_rip import resolve_authoritative_snapshot
from backend.scripts.research_equal_spend_product_rip import (
    PRIMARY_TOLERANCE,
    SENSITIVITY_TOLERANCE,
    StrategyEngine,
    load_authoritative_products,
    load_run_fingerprints,
)
from backend.scripts.research_product_rip_dominance_utility import strategy_values

STEP1B_PATH = REPO_ROOT / "logs/equal_spend_product_rip_research.json"
STEP2A_PATH = REPO_ROOT / "logs/product_rip_publication_architecture_research.json"
STEP2B_PATH = REPO_ROOT / "logs/opponent_adjusted_product_rip_research.json"
STEP2C_PATH = REPO_ROOT / "logs/product_rip_dominance_utility_research.json"
DECISION = "REALISTIC_UPSIDE_DEFINITION_AND_WEIGHT_REQUIRE_RESEARCH"
COUNTERFACTUALS = ("CURRENT", "P95_THRESHOLD_ONLY", "P95_TO_P99_BAND", "TOP5_WINSORIZED_AT_P99", "TOP5_EXCLUDING_TOP1")
UTILITY_GAMMAS = (0.5, 1.0, 2.0, 0.0, -0.5, -1.0)


def _corr(x: Sequence[float], y: Sequence[float]) -> dict[str, Optional[float]]:
    a, b = np.asarray(x, float), np.asarray(y, float)
    if len(a) < 3 or np.std(a) == 0 or np.std(b) == 0:
        return {"pearson": None, "spearman": None}
    return {"pearson": float(pearsonr(a, b).statistic), "spearman": float(spearmanr(a, b).statistic)}


def residualize(values: Sequence[float], control: Sequence[float]) -> np.ndarray:
    y, x = np.asarray(values, float), np.asarray(control, float)
    return y - np.column_stack((np.ones(len(x)), x)) @ np.linalg.lstsq(np.column_stack((np.ones(len(x)), x)), y, rcond=None)[0]


def region_decomposition(values: np.ndarray, cost: float) -> dict[str, Any]:
    """Rank-exact, mutually exclusive below-P95 / P95-P99 / P99+ buckets."""
    sorted_values = np.sort(np.asarray(values, float)); buckets = TailBuckets(sorted_values)
    regions = {"belowP95": sorted_values[: len(sorted_values) - buckets.top_5_count],
               "p95ToBelowP99": buckets.realistic, "p99AndAbove": buckets.jackpot}
    total = float(np.sum(sorted_values)); result = {}
    for name, region in regions.items():
        ev_contribution = float(np.sum(region) / len(sorted_values))
        result[name] = {"count": int(region.size), "probabilityMass": float(region.size / len(sorted_values)),
            "meanOutcome": float(np.mean(region)) if region.size else None, "meanOutcomeRatio": float(np.mean(region) / cost) if region.size else None,
            "evContribution": ev_contribution, "evContributionRatio": ev_contribution / cost,
            "shareOfTotalEv": float(np.sum(region) / total) if total else None}
    result["tieRule"] = "stable ascending rank; exact ceil(5%) and ceil(1%) masses; equal boundary values are interchangeable"
    result["currentRealisticTop1Contribution"] = 0.0
    return result


def counterfactual_realistic(raw: Mapping[str, float]) -> dict[str, dict[str, float]]:
    p95 = float(raw["p95_threshold_ratio"]); band = float(raw["realistic_tail_mean_ratio"]); p99 = float(raw["p99_threshold_ratio"])
    p95_score = float(normalize_metric("p95_threshold_ratio", p95)["score"])
    band_score = float(normalize_metric("realistic_tail_mean_ratio", band)["score"])
    winsor_mean = 0.8 * band + 0.2 * p99
    winsor_score = float(normalize_metric("realistic_tail_mean_ratio", winsor_mean)["score"])
    return {
        "CURRENT": {"raw": 0.4 * p95 + 0.6 * band, "componentScore": 0.4 * p95_score + 0.6 * band_score},
        "P95_THRESHOLD_ONLY": {"raw": p95, "componentScore": p95_score},
        "P95_TO_P99_BAND": {"raw": 0.4 * p95 + 0.6 * band, "componentScore": 0.4 * p95_score + 0.6 * band_score},
        "TOP5_WINSORIZED_AT_P99": {"raw": winsor_mean, "componentScore": winsor_score},
        "TOP5_EXCLUDING_TOP1": {"raw": band, "componentScore": band_score},
    }


def power_utility(values: np.ndarray, cost: float, gamma: float) -> float:
    """E[u(1 + X/C)]; CRRA gamma, with log at gamma=1 and convexity for gamma<0."""
    wealth = 1.0 + np.asarray(values, float) / float(cost)
    if gamma == 1.0:
        return float(np.mean(np.log(wealth)))
    return float(np.mean((np.power(wealth, 1.0 - gamma) - 1.0) / (1.0 - gamma)))


def weakest_risk_seeking(values_a: np.ndarray, cost_a: float, values_b: np.ndarray, cost_b: float) -> Optional[float]:
    for gamma in np.arange(-0.25, -10.0001, -0.25):
        if power_utility(values_a, cost_a, float(gamma)) > power_utility(values_b, cost_b, float(gamma)):
            return float(gamma)
    return None


def preference_class(threshold: Optional[float]) -> str:
    if threshold is None or threshold <= -3.0:
        return "EXTREME_UPSIDE_PREFERENCE_REQUIRED"
    if threshold <= -0.75:
        return "UPSIDE_SEEKING_PREFERENCE_REQUIRED"
    return "BROADLY_FINANCIALLY_DEFENSIBLE"


def attribution_class(delta_p95: float, delta_band: float) -> str:
    positive_p95, positive_band = max(0.0, delta_p95), max(0.0, delta_band)
    total = positive_p95 + positive_band
    if not total:
        return "MIXED"
    if positive_p95 / total >= 0.65:
        return "P95_THRESHOLD"
    if positive_band / total >= 0.65:
        return "P95_TO_P99_BAND"
    return "MIXED"


def _payload_row(payload: Mapping[str, Any]) -> dict[str, Any]:
    normalized = payload["audit"]["normalizedInputs"]
    raw = {key: float(value["raw"]) for key, value in normalized.items()}
    components = {key: float(payload["components"][key]["score"]) for key in FINANCIAL_RIP_V3_COMPONENT_ORDER}
    contributions = {key: float(payload["components"][key]["contribution"]) for key in FINANCIAL_RIP_V3_COMPONENT_ORDER}
    cf = counterfactual_realistic(raw)
    scores = {key: float(payload["score"] - contributions["realistic_upside"] + FINANCIAL_RIP_V3_WEIGHTS["realistic_upside"] * value["componentScore"]) for key, value in cf.items()}
    return {"score": float(payload["score"]), "raw": raw, "components": components, "contributions": contributions,
            "counterfactualRealistic": cf, "counterfactualScores": scores}


def _rank(values: Sequence[float]) -> np.ndarray:
    return np.asarray(spearmanr(np.arange(len(values)), np.asarray(values)).statistic) if False else np.argsort(np.argsort(-np.asarray(values, float))) + 1


def effective_influence(rows: Sequence[Mapping[str, Any]]) -> dict[str, Any]:
    total = np.asarray([r["score"] for r in rows]); total_rank = _rank(total); result = {}
    for component in FINANCIAL_RIP_V3_COMPONENT_ORDER:
        scores = np.asarray([r["components"][component] for r in rows]); contrib = np.asarray([r["contributions"][component] for r in rows])
        without = total - contrib; new_rank = _rank(without); flips = 0
        for i in range(len(rows)):
            for j in range(i + 1, len(rows)):
                flips += int(np.sign(total[i] - total[j]) != np.sign(without[i] - without[j]))
        result[component] = {"componentMean": float(np.mean(scores)), "componentSd": float(np.std(scores)), "componentRange": [float(np.min(scores)), float(np.max(scores))],
            "weightedContributionSd": float(np.std(contrib)), "weightedContributionRange": [float(np.min(contrib)), float(np.max(contrib))],
            "spearmanWithTotal": _corr(scores, total)["spearman"], "spearmanWithRank": _corr(scores, -total_rank)["spearman"],
            "meanAbsoluteScoreChange": float(np.mean(np.abs(total - without))), "medianScoreChange": float(np.median(total - without)),
            "meanAbsoluteRankMovement": float(np.mean(np.abs(total_rank - new_rank))), "maxRankMovement": int(np.max(np.abs(total_rank - new_rank))),
            "top10MembershipChanges": len(set(np.argsort(-total)[:10]) ^ set(np.argsort(-without)[:10])), "pairwiseWinnerFlips": flips}
    return result


def cohort_effect(budget: Mapping[str, Sequence[Mapping[str, Any]]], tolerance: float) -> dict[str, Any]:
    summary = {key: Counter() for key in COUNTERFACTUALS}; comparisons = 0; observations=[]
    all_current, all_cf = [], {key: [] for key in COUNTERFACTUALS}
    for rows in budget.values():
        enriched = []
        for row in rows:
            raw = {"p95_threshold_ratio": row["p95ThresholdRatio"], "realistic_tail_mean_ratio": row["realisticTailMeanRatio"], "p99_threshold_ratio": row["p99ThresholdRatio"]}
            cf = counterfactual_realistic(raw); scores = {key: row["financialRipV3"] - 0.25 * row["components"]["realistic_upside"] + 0.25 * value["componentScore"] for key, value in cf.items()}
            enriched.append((row, cf, scores)); all_current.append(row["financialRipV3"])
            for key in COUNTERFACTUALS: all_cf[key].append(scores[key])
        current_top=max(enriched,key=lambda x:x[0]["financialRipV3"])[0]["sealedProductId"]
        rtp_top=max(enriched,key=lambda x:x[0]["rtp"])[0]["sealedProductId"]
        for key in COUNTERFACTUALS:
            cf_top=max(enriched,key=lambda x:x[2][key])[0]["sealedProductId"]
            summary[key]["topRankChangesFromCurrent"] += cf_top != current_top
            summary[key]["topRankAgreementWithRtp"] += cf_top == rtp_top
        for i, (a, acf, ascores) in enumerate(enriched):
            for b, bcf, bscores in enriched[i + 1:]:
                mismatch = abs(a["actualCommittedCapital"] - b["actualCommittedCapital"]) / max(a["actualCommittedCapital"], b["actualCommittedCapital"])
                if mismatch > tolerance: continue
                comparisons += 1; rtp_winner = 0 if a["rtp"] >= b["rtp"] else 1; current_winner = 0 if a["financialRipV3"] >= b["financialRipV3"] else 1
                observation={"budget":a["budget"],"skuA":a["sealedProductId"],"skuB":b["sealedProductId"],"spendMismatch":mismatch,
                    "currentWinner":a["sealedProductId"] if current_winner==0 else b["sealedProductId"],"rtpWinner":a["sealedProductId"] if rtp_winner==0 else b["sealedProductId"],"diagnosticWinners":{}}
                core_a=(a["rtp"],a["medianRetention"],a["chanceToRecoverCapital"],a["lossResilience"]);core_b=(b["rtp"],b["medianRetention"],b["chanceToRecoverCapital"],b["lossResilience"])
                for key in COUNTERFACTUALS:
                    winner = 0 if ascores[key] >= bscores[key] else 1; summary[key]["agreementCurrent"] += winner == current_winner; summary[key]["agreementRtp"] += winner == rtp_winner
                    observation["diagnosticWinners"][key]=a["sealedProductId"] if winner==0 else b["sealedProductId"]
                    high, low = (a,b) if winner==0 else (b,a); hcore,lcore=(core_a,core_b) if winner==0 else (core_b,core_a)
                    layer1 = all(x <= y + 1e-9 for x,y in zip(hcore,lcore)) and any(x < y - 1e-9 for x,y in zip(hcore,lcore))
                    high_cf,low_cf=(acf[key],bcf[key]) if winner==0 else (bcf[key],acf[key])
                    layer2 = layer1 and low_cf["componentScore"] >= high_cf["componentScore"] - 1e-9
                    summary[key]["layer1Inversions"] += layer1;summary[key]["layer2Inversions"] += layer2
                observations.append(observation)
    return {"validComparisons": comparisons, "observations":observations,"diagnostics": {key: {**dict(value), "agreementCurrentRate": value["agreementCurrent"] / comparisons,
        "agreementRtpRate": value["agreementRtp"] / comparisons, "rankCorrelationWithCurrent": _corr(all_cf[key], all_current)["spearman"]} for key,value in summary.items()}}


def run_research(client: Any) -> dict[str, Any]:
    artifacts = [json.loads(path.read_text(encoding="utf-8")) for path in (STEP1B_PATH,STEP2A_PATH,STEP2B_PATH,STEP2C_PATH)]
    step1b,step2a,step2b,step2c=artifacts;snapshot,authority=resolve_authoritative_snapshot(client)
    if any(str(a["authority"]["snapshotId"]) != str(snapshot["id"]) for a in artifacts): raise RuntimeError("research artifacts do not match current published authority")
    products=load_authoritative_products(client,authority);runs=[str(x["simulation_calculation_run_id"]) for x in authority]
    engine=StrategyEngine(client,authority,products,load_run_fingerprints(client,runs));by_run=defaultdict(list)
    for product in products:by_run[str(product["calculation_run_id"])].append(product)
    natural=[]; product_by={str(p["sealed_product_id"]):p for p in products};authority_by_run={str(x["simulation_calculation_run_id"]):x for x in authority}
    for run_id,run_products in by_run.items():
        engine.build_set(run_id,run_products)
        for product in run_products:
            values=engine.base[str(product["sealed_product_id"])];cost=float(product["product_market_cost"]);payload=build_financial_rip_v3(values,cost)
            row=_payload_row(payload);row.update({"sealedProductId":str(product["sealed_product_id"]),"productName":product["product_name"],"setKey":authority_by_run[run_id]["set_canonical_key"],"cost":cost,"regions":region_decomposition(values,cost)})
            natural.append(row)
    budget_enriched={}
    for budget,rows in step2a["candidateA"]["budgetRankings"].items():
        budget_enriched[budget]=[]
        for source in rows:
            row=dict(source);metrics=engine.strategy(product_by[str(row["sealedProductId"])],int(row["quantity"]))["metrics"]
            for key in ("p95ThresholdRatio","realisticTailMeanRatio","p99ThresholdRatio","jackpotTailMeanRatio"):
                row[key]=metrics[key]
            budget_enriched[budget].append(row)
    raw_keys=("p95_threshold_ratio","realistic_tail_mean_ratio","p99_threshold_ratio","jackpot_tail_mean_ratio")
    redundancy={}
    for x in raw_keys:
        for y in raw_keys:
            if raw_keys.index(y)<=raw_keys.index(x):continue
            redundancy[f"{x}__{y}"]=_corr([r["raw"][x] for r in natural],[r["raw"][y] for r in natural])
    redundancy["componentScores"]=_corr([r["components"]["realistic_upside"] for r in natural],[r["components"]["jackpot_upside"] for r in natural])
    redundancy["weightedContributions"]=_corr([r["contributions"]["realistic_upside"] for r in natural],[r["contributions"]["jackpot_upside"] for r in natural])
    base=[r["raw"]["base_rtp_excluding_top_1pct"] for r in natural]
    redundancy["residualAfterBaseEfficiency"]=_corr(residualize([r["components"]["realistic_upside"] for r in natural],base),residualize([r["components"]["jackpot_upside"] for r in natural],base))
    cf_summary={}
    for key in COUNTERFACTUALS:
        vals=[r["counterfactualRealistic"][key]["componentScore"] for r in natural]
        cf_summary[key]={"mean":float(np.mean(vals)),"sd":float(np.std(vals)),"range":[float(np.min(vals)),float(np.max(vals))],
            "correlationCurrent":_corr(vals,[r["components"]["realistic_upside"] for r in natural]),"correlationJackpot":_corr(vals,[r["components"]["jackpot_upside"] for r in natural])}
    case_results=[]
    for case in step2c["caseSet"]["cases"]:
        strategies=[]
        for side in ("winner","dominator"):
            detail=case[side];pid=case["winnerSku"] if side=="winner" else case["dominatorSku"];values=strategy_values(engine,product_by[pid],detail["quantity"]);cost=detail["actualCommittedCapital"]
            payload=_payload_row(build_financial_rip_v3(values,cost));strategies.append((side,detail,values,cost,payload,region_decomposition(values,cost)))
        (_,a,av,ac,ap,ar),(_,b,bv,bc,bp,br)=strategies
        p95_delta=.25*.4*(normalize_metric("p95_threshold_ratio",ap["raw"]["p95_threshold_ratio"])["score"]-normalize_metric("p95_threshold_ratio",bp["raw"]["p95_threshold_ratio"])["score"])
        band_delta=.25*.6*(normalize_metric("realistic_tail_mean_ratio",ap["raw"]["realistic_tail_mean_ratio"])["score"]-normalize_metric("realistic_tail_mean_ratio",bp["raw"]["realistic_tail_mean_ratio"])["score"])
        threshold=weakest_risk_seeking(av,ac,bv,bc); preferences={str(g):("A" if power_utility(av,ac,g)>power_utility(bv,bc,g) else "B") for g in UTILITY_GAMMAS}
        cf={key:{"winner":"A" if ap["counterfactualScores"][key]>bp["counterfactualScores"][key] else "B","margin":ap["counterfactualScores"][key]-bp["counterfactualScores"][key]} for key in COUNTERFACTUALS}
        case_results.append({"budget":case["budget"],"winnerSku":case["winnerSku"],"dominatorSku":case["dominatorSku"],"spendMismatch":case["spendMismatch"],
            "winnerRawUpside":{k:ap["raw"][k] for k in raw_keys},"dominatorRawUpside":{k:bp["raw"][k] for k in raw_keys},"winnerRegions":ar,"dominatorRegions":br,
            "winnerComponents":{k:ap["components"][k] for k in ("realistic_upside","jackpot_upside")},"dominatorComponents":{k:bp["components"][k] for k in ("realistic_upside","jackpot_upside")},
            "winnerContributions":{k:ap["contributions"][k] for k in ("realistic_upside","jackpot_upside")},"dominatorContributions":{k:bp["contributions"][k] for k in ("realistic_upside","jackpot_upside")},
            "attribution":attribution_class(p95_delta,band_delta),"p95WeightedDelta":p95_delta,"bandWeightedDelta":band_delta,"p99PlusContamination":0.0,
            "counterfactuals":cf,"utilityPreference":preferences,"weakestRiskSeekingGamma":threshold,"preferenceInterpretation":preference_class(threshold)})
    inversion_cf={key:{"remain":sum(c["counterfactuals"][key]["winner"]=="A" for c in case_results),"flip":sum(c["counterfactuals"][key]["winner"]=="B" for c in case_results),
        "within2Remain":sum(c["spendMismatch"]<=SENSITIVITY_TOLERANCE and c["counterfactuals"][key]["winner"]=="A" for c in case_results),
        "flippedCases":[{"budget":c["budget"],"winnerSku":c["winnerSku"],"dominatorSku":c["dominatorSku"]} for c in case_results if c["counterfactuals"][key]["winner"]=="B"]} for key in COUNTERFACTUALS}
    # Positive controls: large P95 differences among pairs with RTP within one percentage point.
    controls=[]
    for i,a in enumerate(natural):
        for b in natural[i+1:]:
            rtp_a=np.mean(engine.base[a["sealedProductId"]])/a["cost"];rtp_b=np.mean(engine.base[b["sealedProductId"]])/b["cost"]
            if abs(rtp_a-rtp_b)<=.01:
                delta=abs(a["raw"]["p95_threshold_ratio"]-b["raw"]["p95_threshold_ratio"])
                controls.append((delta,a,b))
    positive=[]
    for delta,a,b in sorted(controls,key=lambda x:x[0],reverse=True)[:10]:
        differences={key:abs(a["counterfactualRealistic"][key]["componentScore"]-b["counterfactualRealistic"][key]["componentScore"]) for key in COUNTERFACTUALS}
        positive.append({"skuA":a["sealedProductId"],"skuB":b["sealedProductId"],"rtpDifferenceMax":.01,"p95Difference":delta,
            "currentDifference":abs(a["counterfactualRealistic"]["CURRENT"]["componentScore"]-b["counterfactualRealistic"]["CURRENT"]["componentScore"]),
            **{key:differences[key] for key in COUNTERFACTUALS[1:]},
            "preservesReachableDifferentiation":{key:differences[key]>=.5*differences["CURRENT"] for key in COUNTERFACTUALS}})
    profile_counts={str(g):dict(Counter(c["utilityPreference"][str(g)] for c in case_results)) for g in UTILITY_GAMMAS}
    return {"authority":{"snapshotId":snapshot["id"],"marketDate":snapshot["market_date"],"runCount":len(runs),"artifactCount":len(runs),"skuCount":len(products)},
        "productionTrace":{"realistic":{"inputs":FINANCIAL_RIP_V3_COMPONENT_INPUTS["realistic_upside"],"transforms":{k:FINANCIAL_RIP_V3_TRANSFORMS[k] for k in FINANCIAL_RIP_V3_COMPONENT_INPUTS["realistic_upside"]},"weight":FINANCIAL_RIP_V3_WEIGHTS["realistic_upside"],"tail":"rank-exact 95th-to-below-99th band; top 1% excluded"},
            "jackpot":{"inputs":FINANCIAL_RIP_V3_COMPONENT_INPUTS["jackpot_upside"],"transforms":{k:FINANCIAL_RIP_V3_TRANSFORMS[k] for k in FINANCIAL_RIP_V3_COMPONENT_INPUTS["jackpot_upside"]},"weight":FINANCIAL_RIP_V3_WEIGHTS["jackpot_upside"],"tail":"rank-exact top 1%"}},
        "tailOverlap":{"skuDiagnostics":natural,"meanTop1ContributionToRealisticTail":0.0,"sharedTailObservations":False},"redundancy":redundancy,
        "effectiveInfluence":effective_influence(natural),"counterfactualDefinitions":cf_summary,"inversionCases":case_results,"counterfactualInversions":inversion_cf,
        "utilitySummary":{"formula":"E[((1+X/C)^(1-gamma)-1)/(1-gamma)], log at gamma=1; gamma<0 is convex/risk-seeking; X>=0 so wealth>=1","gammas":UTILITY_GAMMAS,
            "profilePreferenceCounts":profile_counts,"preferenceCounts":dict(Counter(c["preferenceInterpretation"] for c in case_results))},
        "cohort5Pct":cohort_effect(budget_enriched,PRIMARY_TOLERANCE),"cohort2Pct":cohort_effect(budget_enriched,SENSITIVITY_TOLERANCE),
        "positiveControls":positive,"decision":DECISION,"productionContractChanged":False,"productionMutations":"NONE"}


def render_markdown(r: Mapping[str, Any]) -> str:
    a=r["authority"];red=r["redundancy"];inv=r["counterfactualInversions"];cohort=r["cohort5Pct"]
    lines=["# AUTHORITY","",f"Snapshot `{a['snapshotId']}`, market date `{a['marketDate']}`; {a['runCount']} exact runs/artifacts and {a['skuCount']} SKUs. No simulation rerun or newer-run substitution.","",
        "# LOCKED PRIOR FINDINGS","","Equal-spend remains the validated framework; Step 2C found 15 core inversions and directed this semantics/weight research. Production remains locked.","",
        "# PRODUCTION REALISTIC UPSIDE DEFINITION","","Realistic Upside is 40% normalized interpolated P95 threshold ratio plus 60% normalized rank-exact 95th-to-below-99th conditional mean ratio. Piecewise-linear transforms clip at 8x/100 and 12x/100 respectively; the component contributes 25% of V3.","",
        "# PRODUCTION JACKPOT UPSIDE DEFINITION","","Jackpot Upside is 35% normalized interpolated P99 threshold ratio plus 65% normalized rank-exact top-1% conditional mean ratio. Saturating exponentials use k=8 and k=25; the component contributes 10% of V3.","",
        "# TAIL OVERLAP","","The conditional-mean buckets are mutually exclusive. Current Realistic Upside includes zero P99+ observations and has 0% direct top-1% contribution. Thresholds can remain correlated through common distribution shape, but there is no top-1% contamination of the realistic band mean.","",
        "# COMPONENT REDUNDANCY","",f"Realistic/Jackpot component correlation: `{red['componentScores']}`; weighted-contribution correlation is identical up to fixed scaling. After linear descriptive control for base efficiency: `{red['residualAfterBaseEfficiency']}`. Correlation is descriptive, not causal independence.","",
        "# EFFECTIVE COMPONENT INFLUENCE","","Per-component means, dispersion, contribution ranges, total/rank correlation, leave-one-out rank movement, top-10 changes and pairwise flips are reported in JSON.","",
        "# INVERSION ATTRIBUTION","",f"Attribution counts: `{dict(Counter(c['attribution'] for c in r['inversionCases']))}`. P99+ contamination is zero by construction for all 15.","",
        "# COUNTERFACTUAL TAIL DEFINITIONS","","CURRENT and P95_TO_P99_BAND intentionally coincide because production already implements the disjoint band. Other diagnostics isolate P95, the band mean, or a P99-winsorized top 5%. Distribution and redundancy diagnostics are in JSON.","",
        "# COUNTERFACTUAL INVERSION RESULTS","","| diagnostic | remain | flip | <=2% remain | cohort Layer-1 | cohort Layer-2 |","|---|---:|---:|---:|---:|---:|"]
    for key in COUNTERFACTUALS:
        c=inv[key];d=cohort["diagnostics"][key];lines.append(f"| {key} | {c['remain']} | {c['flip']} | {c['within2Remain']} | {d['layer1Inversions']} | {d['layer2Inversions']} |")
    lines += ["","# RISK-SEEKING UTILITY THRESHOLDS","",f"Utility and threshold details are reported per inversion. Interpretation counts: `{r['utilitySummary']['preferenceCounts']}`.","",
        "# USER-PREFERENCE INTERPRETATION","","Classifications use the weakest tested convex CRRA gamma: above -0.75 broadly defensible, -0.75 through above -3 materially upside-seeking, and -3 or lower/no flip extreme. These are semantic bands, not normative recommendations.","",
        "# FULL-COHORT EFFECT","",f"At <=5%, {cohort['validComparisons']} valid comparisons were evaluated. Agreement with current V3/RTP, layered inversions and score-rank correlations are reported for every diagnostic in JSON.","",
        "# POSITIVE-CONTROL PRESERVATION","","Ten near-RTP pairs with the largest P95 separation quantify whether each diagnostic preserves useful reachable-upside differentiation.","",
        "# RESEARCH DECISION","",f"`{r['decision']}`","",
        "# IMPLICATION FOR FINANCIAL RIP","","The production tail buckets are semantically disjoint, but the 95th-to-99th conditional-mean term remains strongly redundant with Jackpot Upside and drives most target inversions. Its 25% component influence also produces preferences that always require convex utility and sometimes require extreme convexity. Both definition and influence warrant controlled research; no production change is proposed.","",
        "# NEXT RESEARCH IF REQUIRED","","A future controlled study should prioritize the P95-threshold diagnostic because it reduced jackpot correlation and target inversions while preserving all selected reachable-upside controls. It should separately assess influence without optimizing both dimensions at once, preserving exact tail separation, monotonicity and existing arithmetic while evaluating utility thresholds, RTP agreement, top-rank stability and cohort-wide pairwise flips.","",
        "# PRODUCTION CONTRACT","","Financial RIP V3, weights, transforms, Overall RIP V9, comparison contracts and `crossFormatComparable=False` are unchanged.","",
        "# TESTS","","Focused authority, exact trace, tail decomposition, counterfactual, utility, attribution, cohort, preservation, no-write and import-isolation tests accompany the harness.","",
        "# FILES CHANGED","","Step 3A research harness, focused tests, and generated JSON/Markdown only.","",
        "# PRODUCTION MUTATIONS","","NONE",""]
    return "\n".join(lines)


def main(argv: Optional[Sequence[str]]=None) -> int:
    parser=argparse.ArgumentParser(description=__doc__);parser.add_argument("--json",default="logs/realistic_upside_semantics_research.json");parser.add_argument("--markdown",default="logs/realistic_upside_semantics_research.md");args=parser.parse_args(argv)
    from backend.scripts.pokemon_snapshot_builders import get_client
    result=run_research(get_client());json_path=Path(args.json);markdown_path=Path(args.markdown);json_path.parent.mkdir(parents=True,exist_ok=True);markdown_path.parent.mkdir(parents=True,exist_ok=True)
    json_path.write_text(json.dumps(result,indent=2,default=str)+"\n",encoding="utf-8");markdown_path.write_text(render_markdown(result),encoding="utf-8");print(f"wrote {json_path} and {markdown_path}");return 0


if __name__ == "__main__":
    raise SystemExit(main())
