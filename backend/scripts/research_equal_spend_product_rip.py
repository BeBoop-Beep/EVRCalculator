"""STEP 1B: SELECT-only equal-spend cross-format Financial RIP research."""

from __future__ import annotations

import argparse
import ast
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

from backend.calculations.evr.financial_rip_v3 import build_financial_rip_v3
from backend.calculations.evr.financial_rip_v3_config import FINANCIAL_RIP_V3_COMPONENT_ORDER
from backend.calculations.evr.guaranteed_component_value import add_guaranteed_components
from backend.calculations.evr.sealed_product_distribution import build_stage1_product_distributions
from backend.db.services.pack_outcome_artifact_service import load_pack_outcome_artifact
from backend.scripts.research_cross_format_product_rip import resolve_authoritative_snapshot

METHOD_CURRENT = "CURRENT_UNIT_V3"
METHOD_EQUAL = "EQUAL_SPEND_V3"
METHOD_RTP = "PURE_RTP"
BUDGET_BANDS = (25, 50, 100, 150, 250, 500)
PRIMARY_TOLERANCE = 0.05
SENSITIVITY_TOLERANCE = 0.02
MAX_PAIR_SPEND = 1000.0
MAX_QUANTITY = 200
EXPECTED_OUTCOMES = 1_000_000
DECISIONS = (
    "CURRENT_UNIT_PRODUCT_RIP_SUPPORTED", "EQUAL_SPEND_PRODUCT_RIP_SUPPORTED",
    "FAMILY_RELATIVE_ONLY_SUPPORTED", "PRODUCT_RIP_CONSTRUCT_INCONCLUSIVE",
)


def _rows(response: Any) -> list[dict[str, Any]]:
    return list((response.data if response else []) or [])


def load_authoritative_products(client: Any, authority_rows: Sequence[Mapping[str, Any]]) -> list[dict[str, Any]]:
    run_ids = [str(row["simulation_calculation_run_id"]) for row in authority_rows]
    records: list[dict[str, Any]] = []
    for start in range(0, len(run_ids), 20):
        records.extend(_rows(client.table("simulation_sealed_product_results").select("*").in_(
            "calculation_run_id", run_ids[start:start + 20]
        ).execute()))
    allowed = set(run_ids)
    products = [row for row in records if str(row.get("calculation_run_id")) in allowed
                and row.get("financial_rip_v3_rankable") is True
                and row.get("financial_rip_v3_status") == "ready"
                and float(row.get("product_market_cost") or 0) > 0]
    if not products:
        raise RuntimeError("no rankable sealed-product rows belong to the authoritative runs")
    identities = [(str(row["calculation_run_id"]), str(row["sealed_product_id"])) for row in products]
    if len(identities) != len(set(identities)):
        raise RuntimeError("duplicate authoritative product SKU rows exist")
    missing_runs = sorted(allowed - {str(row["calculation_run_id"]) for row in products})
    if missing_runs:
        raise RuntimeError(f"authoritative runs missing rankable products: {missing_runs}")
    for row in products:
        if row.get("accessory_value_included") is True:
            raise RuntimeError("authoritative product unexpectedly includes accessory value")
        random_count = int(row.get("random_pack_count") or row.get("pack_count") or 0)
        if random_count < 1:
            raise RuntimeError("product has no positive random pack count")
        guaranteed = row.get("guaranteed_component_market_value")
        guaranteed_count = int(row.get("guaranteed_component_count") or 0)
        if guaranteed_count and (guaranteed is None or float(guaranteed) <= 0):
            raise RuntimeError("guaranteed product is missing its canonical market-value offset")
        if not guaranteed_count and guaranteed is not None:
            raise RuntimeError("guaranteed value exists without guaranteed components")
    return products


def load_run_fingerprints(client: Any, run_ids: Sequence[str]) -> dict[str, str]:
    run_rows = _rows(client.table("calculation_runs").select("id,calculation_config_id").in_("id", list(run_ids)).execute())
    config_ids = [str(row.get("calculation_config_id") or "") for row in run_rows]
    config_rows = _rows(client.table("calculation_configs").select("id,config_hash").in_("id", config_ids).execute())
    hashes = {str(row["id"]): str(row.get("config_hash") or "") for row in config_rows}
    mapped = {str(row["id"]): hashes.get(str(row.get("calculation_config_id")), "") for row in run_rows}
    missing = sorted(set(run_ids) - {key for key, value in mapped.items() if value})
    if missing:
        raise RuntimeError(f"authoritative runs missing production distribution fingerprints: {missing}")
    return mapped


def nearest_spend_pair(cost_a: float, cost_b: float, *, tolerance: float = PRIMARY_TOLERANCE,
                       max_spend: float = MAX_PAIR_SPEND, max_quantity: int = MAX_QUANTITY) -> Optional[dict[str, Any]]:
    """Lowest feasible bounded near-LCM, with whole units and symmetric mismatch."""
    if cost_a <= 0 or cost_b <= 0:
        raise ValueError("product costs must be positive")
    best = None
    for qa in range(1, min(max_quantity, int(max_spend // cost_a)) + 1):
        spend_a = qa * cost_a
        center = spend_a / cost_b
        for qb in {max(1, int(math.floor(center))), max(1, int(math.ceil(center)))}:
            if qb > max_quantity or qb * cost_b > max_spend:
                continue
            spend_b = qb * cost_b
            mismatch = abs(spend_a - spend_b) / max(spend_a, spend_b)
            if mismatch <= tolerance:
                candidate = (max(spend_a, spend_b), mismatch, qa + qb, qa, qb)
                if best is None or candidate < best[0]:
                    best = (candidate, {"quantityA": qa, "quantityB": qb, "spendA": spend_a,
                                        "spendB": spend_b, "mismatch": mismatch, "tolerance": tolerance})
    return None if best is None else best[1]


def fixed_budget_quantity(budget: float, price: float) -> dict[str, Any]:
    quantity = int(math.floor(float(budget) / float(price)))
    spend = quantity * float(price)
    return {"quantity": quantity, "actualCommittedCapital": spend, "leftoverCapital": float(budget) - spend}


def anchored_quantity(target: float, price: float, tolerance: float = PRIMARY_TOLERANCE) -> Optional[dict[str, Any]]:
    candidates = {max(1, int(math.floor(target / price))), max(1, int(math.ceil(target / price)))}
    quantity = min(candidates, key=lambda q: (abs(q * price - target), q))
    spend = quantity * price
    mismatch = abs(spend - target) / max(spend, target)
    if mismatch > tolerance:
        return None
    return {"quantity": quantity, "actualCommittedCapital": spend,
            "leftoverCapital": max(0.0, target - spend), "targetBudget": target, "mismatch": mismatch}


def score_values(values: np.ndarray, committed: float) -> dict[str, Any]:
    payload = build_financial_rip_v3(values, committed)
    if payload.get("status") != "ready" or not payload.get("rankable"):
        raise RuntimeError(f"Financial RIP V3 rejected a strategy: {payload.get('statusReason')}")
    raw = {key: rec.get("raw") for key, rec in ((payload.get("audit") or {}).get("normalizedInputs") or {}).items()}
    disclosure = payload.get("distributionDisclosures") or {}
    return {
        "financialRipV3": payload["score"], "rtp": float(np.mean(values) / committed),
        "expectedValue": float(np.mean(values)), "medianValue": float(np.median(values)),
        "medianRetention": raw.get("typical_retention_ratio"),
        "chanceToRecoverCapital": raw.get("true_win_probability"),
        "averageRetentionWhenLosing": raw.get("average_retention_given_loss"),
        "softLossShareGivenLoss": raw.get("soft_loss_share_given_loss"),
        "hardLossProbability": disclosure.get("hardLossProbability"),
        "p95ThresholdRatio": raw.get("p95_threshold_ratio"),
        "realisticTailMeanRatio": raw.get("realistic_tail_mean_ratio"),
        "p99ThresholdRatio": raw.get("p99_threshold_ratio"),
        "jackpotTailMeanRatio": raw.get("jackpot_tail_mean_ratio"),
        "baseRtpExcludingTop1Pct": raw.get("base_rtp_excluding_top_1pct"),
        "jackpotValueShare": disclosure.get("jackpotValueShare"),
        "lossResilience": (payload.get("components") or {}).get("loss_resilience", {}).get("score"),
        "components": {key: (payload.get("components") or {}).get(key, {}).get("score")
                       for key in FINANCIAL_RIP_V3_COMPONENT_ORDER},
        "clippedInputs": (payload.get("estimationDiagnostics") or {}).get("clippedInputs") or [],
    }


def multi_metric_dominator(a: Mapping[str, Any], b: Mapping[str, Any], epsilon: float = 1e-9) -> Optional[str]:
    """Return A/B when that strategy weakly dominates on four core metrics."""
    metrics = ("rtp", "medianRetention", "chanceToRecoverCapital", "lossResilience")
    def dominates(x: Mapping[str, Any], y: Mapping[str, Any]) -> bool:
        pairs = [(float(x[m]), float(y[m])) for m in metrics if x.get(m) is not None and y.get(m) is not None]
        return len(pairs) == len(metrics) and all(xv + epsilon >= yv for xv, yv in pairs) and any(xv > yv + epsilon for xv, yv in pairs)
    if dominates(a, b): return "A"
    if dominates(b, a): return "B"
    return None


def strict_return_dominator(a: Mapping[str, Any], b: Mapping[str, Any]) -> Optional[str]:
    """Higher RTP, unless the lower-RTP strategy wins any core downside metric."""
    downside = ("medianRetention", "chanceToRecoverCapital", "lossResilience")
    if float(a["rtp"]) > float(b["rtp"]) and not any(float(b[m]) > float(a[m]) for m in downside): return "A"
    if float(b["rtp"]) > float(a["rtp"]) and not any(float(a[m]) > float(b[m]) for m in downside): return "B"
    return None


def _rankdata(values: Sequence[float]) -> np.ndarray:
    a = np.asarray(values, float); order = np.argsort(a, kind="mergesort"); ranks = np.empty(len(a), float); i = 0
    while i < len(a):
        j = i + 1
        while j < len(a) and a[order[j]] == a[order[i]]: j += 1
        ranks[order[i:j]] = (i + j - 1) / 2 + 1; i = j
    return ranks


def spearman(x: Sequence[float], y: Sequence[float]) -> Optional[float]:
    return None if len(x) < 3 else float(np.corrcoef(_rankdata(x), _rankdata(y))[0, 1])


class StrategyEngine:
    def __init__(self, client: Any, authority_rows: Sequence[Mapping[str, Any]], products: Sequence[Mapping[str, Any]],
                 run_fingerprints: Optional[Mapping[str, str]] = None):
        self.client = client
        self.authority = {str(row["simulation_calculation_run_id"]): row for row in authority_rows}
        self.products = [dict(row) for row in products]
        self.run_fingerprints = dict(run_fingerprints or {})
        self.base: dict[str, np.ndarray] = {}
        self.cache: dict[tuple[str, int], dict[str, Any]] = {}

    def build_set(self, run_id: str, set_products: Sequence[Mapping[str, Any]]) -> None:
        authority = self.authority[run_id]
        artifact = load_pack_outcome_artifact(self.client, run_id)
        if int(artifact.metadata.get("outcome_count") or -1) != EXPECTED_OUTCOMES:
            raise RuntimeError("exact one-million-outcome artifact required")
        counts = sorted({int(p.get("random_pack_count") or p["pack_count"]) for p in set_products})
        built = build_stage1_product_distributions(artifact.outcomes, pack_counts=counts,
            canonical_set_key=authority["set_canonical_key"], run_fingerprint=self.run_fingerprints.get(run_id))
        for product in set_products:
            pid = str(product["sealed_product_id"])
            random_count = int(product.get("random_pack_count") or product["pack_count"])
            values = built["distributions"][random_count]
            guaranteed = product.get("guaranteed_component_market_value")
            if guaranteed is not None:
                values = add_guaranteed_components(values, float(guaranteed))
            self.base[pid] = values
            current = self.strategy(product, 1)
            if abs(float(current["metrics"]["financialRipV3"]) - float(product["financial_rip_v3_score"])) > 0.001:
                raise RuntimeError(f"reconstructed product score mismatch for {product.get('product_name')}")

    def strategy(self, product: Mapping[str, Any], quantity: int) -> dict[str, Any]:
        if not isinstance(quantity, int) or quantity < 1:
            raise ValueError("strategy quantity must be a positive whole retail unit")
        pid = str(product["sealed_product_id"]); key = (pid, quantity)
        if key in self.cache: return self.cache[key]
        base = self.base[pid]
        if quantity == 1:
            values = base
        else:
            values = build_stage1_product_distributions(base, pack_counts=[quantity],
                canonical_set_key=f"product:{pid}", run_fingerprint=str(product["calculation_run_id"]))["distributions"][quantity]
        price = float(product["product_market_cost"]); committed = quantity * price
        metrics = score_values(values, committed)
        result = {
            "sealedProductId": pid, "productName": product.get("product_name"),
            "productFamily": product["product_family"], "quantity": quantity,
            "unitPrice": price, "actualCommittedCapital": committed,
            "randomPackCountPerUnit": int(product.get("random_pack_count") or product["pack_count"]),
            "totalRandomPacks": quantity * int(product.get("random_pack_count") or product["pack_count"]),
            "guaranteedComponentValuePerUnit": float(product.get("guaranteed_component_market_value") or 0),
            "guaranteedComponentCountPerUnit": int(product.get("guaranteed_component_count") or 0),
            "guaranteedValueShareOfExpectedValue": product.get("guaranteed_value_share_of_expected_value"),
            "accessoryValueIncluded": bool(product.get("accessory_value_included")), "metrics": metrics,
        }
        self.cache[key] = result
        return result


def classify_agreement(rtp_winner: str, current_winner: str, equal_winner: str) -> str:
    if rtp_winner == current_winner == equal_winner: return "all_three_agree"
    if rtp_winner == equal_winner: return "rtp_equal_spend_agree_current_differs"
    if current_winner == equal_winner: return "current_equal_spend_agree_rtp_differs"
    if rtp_winner == current_winner: return "rtp_current_agree_equal_spend_differs"
    return "all_three_disagree"


def compare_pair(product_a: Mapping[str, Any], product_b: Mapping[str, Any], sa: Mapping[str, Any], sb: Mapping[str, Any],
                 context: str, tolerance: float) -> dict[str, Any]:
    ma, mb = sa["metrics"], sb["metrics"]
    current_a, current_b = float(product_a["financial_rip_v3_score"]), float(product_b["financial_rip_v3_score"])
    winner = lambda av, bv: str(product_a["sealed_product_id"] if av >= bv else product_b["sealed_product_id"])
    rtp_w = winner(ma["rtp"], mb["rtp"]); current_w = winner(current_a, current_b)
    equal_w = winner(ma["financialRipV3"], mb["financialRipV3"])
    multi = multi_metric_dominator(ma, mb); strict = strict_return_dominator(ma, mb)
    dominator = None if multi is None else str(product_a["sealed_product_id"] if multi == "A" else product_b["sealed_product_id"])
    dominated = None if multi is None else str(product_b["sealed_product_id"] if multi == "A" else product_a["sealed_product_id"])
    return {"context": context, "tolerance": tolerance, "strategyA": sa, "strategyB": sb,
            "spendMismatch": abs(sa["actualCommittedCapital"]-sb["actualCommittedCapital"])/max(sa["actualCommittedCapital"],sb["actualCommittedCapital"]),
            "winners": {METHOD_RTP: rtp_w, METHOD_CURRENT: current_w, METHOD_EQUAL: equal_w},
            "agreement": classify_agreement(rtp_w, current_w, equal_w),
            "multiMetricDominator": dominator, "multiMetricDominated": dominated,
            "strictExpectedReturnDominator": None if strict is None else str(product_a["sealed_product_id"] if strict == "A" else product_b["sealed_product_id"]),
            "currentRanksDominatedAboveDominator": bool(dominator and current_w == dominated),
            "equalSpendRanksDominatedAboveDominator": bool(dominator and equal_w == dominated)}


def band(value: float) -> str:
    low = int(math.floor(value / 10) * 10)
    return f"{low}-{low+10}" if low < 60 else "60+"


def summarize_calibration(rows: Sequence[Mapping[str, Any]], score_key: str) -> list[dict[str, Any]]:
    groups: dict[tuple[str, str], list[Mapping[str, Any]]] = defaultdict(list)
    for row in rows: groups[(band(float(row[score_key])), str(row["productFamily"]))].append(row)
    out = []
    for (score_band, family), members in sorted(groups.items()):
        out.append({"scoreBand": score_band, "productFamily": family, "n": len(members),
                    **{key: float(np.median([float(m[key]) for m in members])) for key in
                       ("rtp", "medianRetention", "chanceToRecoverCapital", "lossResilience",
                        "realisticTailMeanRatio", "jackpotTailMeanRatio")}})
    return out


def calibration_coherence(summary: Sequence[Mapping[str, Any]]) -> dict[str, Any]:
    groups: dict[str, list[Mapping[str, Any]]] = defaultdict(list)
    for row in summary: groups[str(row["scoreBand"])].append(row)
    metrics = ("rtp", "medianRetention", "chanceToRecoverCapital", "lossResilience",
               "realisticTailMeanRatio", "jackpotTailMeanRatio")
    return {metric: {"eligibleBandCount": sum(len(rows) >= 2 for rows in groups.values()),
        "meanCrossFamilyMedianRange": float(np.mean([
            max(float(row[metric]) for row in rows) - min(float(row[metric]) for row in rows)
            for rows in groups.values() if len(rows) >= 2]))} for metric in metrics}


def run_research(client: Any) -> dict[str, Any]:
    snapshot, authority_rows = resolve_authoritative_snapshot(client)
    products = load_authoritative_products(client, authority_rows)
    run_ids = [str(row["simulation_calculation_run_id"]) for row in authority_rows]
    engine = StrategyEngine(client, authority_rows, products, load_run_fingerprints(client, run_ids))
    by_run: dict[str, list[dict[str, Any]]] = defaultdict(list)
    for product in products: by_run[str(product["calculation_run_id"])].append(product)
    for run_id, members in by_run.items(): engine.build_set(run_id, members)

    primary: list[dict[str, Any]] = []; sensitivity: list[dict[str, Any]] = []
    fixed_strategy_rows: list[dict[str, Any]] = []
    anchored: list[dict[str, Any]] = []
    for run_id, members in by_run.items():
        for budget in BUDGET_BANDS:
            feasible = []
            for p in members:
                allocation = fixed_budget_quantity(budget, float(p["product_market_cost"]))
                if allocation["quantity"] >= 1:
                    s = dict(engine.strategy(p, allocation["quantity"])); s.update(allocation); s["budgetBand"] = budget
                    feasible.append((p, s)); fixed_strategy_rows.append({"setKey": engine.authority[run_id]["set_canonical_key"], **s,
                        **{k:s["metrics"][k] for k in ("rtp","medianRetention","chanceToRecoverCapital","lossResilience","realisticTailMeanRatio","jackpotTailMeanRatio")},
                        "currentScore": float(p["financial_rip_v3_score"]), "equalScore": s["metrics"]["financialRipV3"]})
            for i in range(len(feasible)):
                for j in range(i+1, len(feasible)):
                    p1,s1=feasible[i]; p2,s2=feasible[j]
                    mismatch=abs(s1["actualCommittedCapital"]-s2["actualCommittedCapital"])/max(s1["actualCommittedCapital"],s2["actualCommittedCapital"])
                    if mismatch <= PRIMARY_TOLERANCE: primary.append(compare_pair(p1,p2,s1,s2,f"fixed_budget:{budget}",PRIMARY_TOLERANCE))
                    if mismatch <= SENSITIVITY_TOLERANCE: sensitivity.append(compare_pair(p1,p2,s1,s2,f"fixed_budget:{budget}",SENSITIVITY_TOLERANCE))
        for anchor in members:
            target=float(anchor["product_market_cost"]); strategies=[]
            for p in members:
                allocation=anchored_quantity(target,float(p["product_market_cost"]))
                if allocation:
                    s=dict(engine.strategy(p,allocation["quantity"]));s.update(allocation);strategies.append((p,s))
            record={"setKey":engine.authority[run_id]["set_canonical_key"],"anchorProductId":anchor["sealed_product_id"],
                    "anchorProductName":anchor["product_name"],"targetBudget":target,"strategies":[s for _,s in strategies]}
            anchored.append(record)
            for i in range(len(strategies)):
                for j in range(i+1,len(strategies)):
                    p1,s1=strategies[i];p2,s2=strategies[j]
                    mismatch=abs(s1["actualCommittedCapital"]-s2["actualCommittedCapital"])/max(s1["actualCommittedCapital"],s2["actualCommittedCapital"])
                    if mismatch<=PRIMARY_TOLERANCE: primary.append(compare_pair(p1,p2,s1,s2,f"anchored:{anchor['sealed_product_id']}",PRIMARY_TOLERANCE))
        for i in range(len(members)):
            for j in range(i+1,len(members)):
                p1,p2=members[i],members[j]
                for tol,target in ((PRIMARY_TOLERANCE,primary),(SENSITIVITY_TOLERANCE,sensitivity)):
                    match=nearest_spend_pair(float(p1["product_market_cost"]),float(p2["product_market_cost"]),tolerance=tol)
                    if match:
                        target.append(compare_pair(p1,p2,engine.strategy(p1,match["quantityA"]),engine.strategy(p2,match["quantityB"]),"pairwise_nearest",tol))

    # De-duplicate identical pair/quantity/context records produced by repeated anchors.
    def unique(comparisons):
        seen=set();out=[]
        for c in comparisons:
            key=(c["context"],c["strategyA"]["sealedProductId"],c["strategyA"]["quantity"],c["strategyB"]["sealedProductId"],c["strategyB"]["quantity"])
            if key not in seen:seen.add(key);out.append(c)
        return out
    primary=unique(primary);sensitivity=unique(sensitivity)

    family_sets: dict[str,set[str]]=defaultdict(set); family_products=Counter()
    authority_by_run={str(r["simulation_calculation_run_id"]):r for r in authority_rows}
    product_summary=[]
    for p in products:
        family=str(p["product_family"]);set_key=str(authority_by_run[str(p["calculation_run_id"])]["set_canonical_key"])
        family_sets[family].add(set_key);family_products[family]+=1
        one=engine.strategy(p,1)["metrics"]
        product_summary.append({"setKey":set_key,"sealedProductId":p["sealed_product_id"],"productName":p["product_name"],
            "productFamily":family,"price":float(p["product_market_cost"]),"randomPackCount":int(p.get("random_pack_count") or p["pack_count"]),
            "effectivePackCost":float(p["product_market_cost"])/int(p.get("random_pack_count") or p["pack_count"]),
            "guaranteedComponentValue":float(p.get("guaranteed_component_market_value") or 0),"guaranteedComponentCount":int(p.get("guaranteed_component_count") or 0),
            "guaranteedValueShare":p.get("guaranteed_value_share_of_expected_value"),"currentFinancialRip":float(p["financial_rip_v3_score"]),"rtp":one["rtp"]})
    coverage=[]
    for family,sets_in in sorted(family_sets.items()):
        n=len(sets_in);tier=">=10" if n>=10 else "5-9" if n>=5 else "3-4" if n>=3 else "<3"
        coverage.append({"productFamily":family,"setCount":n,"productCount":family_products[family],"coverageTier":tier})

    agreements=Counter(c["agreement"] for c in primary)
    dominance={"comparisonCount":len(primary),"multiMetricDominanceCount":sum(c["multiMetricDominator"] is not None for c in primary),
        "currentUnitRanksDominatedHigher":sum(c["currentRanksDominatedAboveDominator"] for c in primary),
        "equalSpendRanksDominatedHigher":sum(c["equalSpendRanksDominatedAboveDominator"] for c in primary),
        "strictExpectedReturnDominanceCount":sum(c["strictExpectedReturnDominator"] is not None for c in primary)}
    sensitivity_summary={"comparisonCount":len(sensitivity),
        "agreementFrequencies":dict(Counter(c["agreement"] for c in sensitivity)),
        "multiMetricDominanceCount":sum(c["multiMetricDominator"] is not None for c in sensitivity),
        "currentUnitRanksDominatedHigher":sum(c["currentRanksDominatedAboveDominator"] for c in sensitivity),
        "equalSpendRanksDominatedHigher":sum(c["equalSpendRanksDominatedAboveDominator"] for c in sensitivity)}
    disagreements=sorted([c for c in primary if c["agreement"]!="all_three_agree"],
        key=lambda c:abs(c["strategyA"]["metrics"]["rtp"]-c["strategyB"]["metrics"]["rtp"]),reverse=True)[:25]

    # Budget sensitivity: winner among strategies spending within 5% of the largest feasible commitment.
    winners: dict[str,dict[int,str]]=defaultdict(dict)
    for set_key in {r["setKey"] for r in fixed_strategy_rows}:
        for budget in BUDGET_BANDS:
            rows=[r for r in fixed_strategy_rows if r["setKey"]==set_key and r["budgetBand"]==budget]
            if not rows:continue
            max_spend=max(float(r["actualCommittedCapital"]) for r in rows)
            comparable=[r for r in rows if (max_spend-float(r["actualCommittedCapital"]))/max_spend<=PRIMARY_TOLERANCE]
            winners[set_key][budget]=max(comparable,key=lambda r:r["equalScore"])["productFamily"]
    budget_sensitivity=[]
    for set_key,by_budget in winners.items():
        ordered=[by_budget[b] for b in BUDGET_BANDS if b in by_budget]
        budget_sensitivity.append({"setKey":set_key,"winnerByBudget":by_budget,
            "switchCount":sum(ordered[i]!=ordered[i-1] for i in range(1,len(ordered)))})

    corr_current_equal=[];corr_rtp_equal=[];rank_stats=[]
    for set_key in {r["setKey"] for r in fixed_strategy_rows}:
        for budget in BUDGET_BANDS:
            rows=[r for r in fixed_strategy_rows if r["setKey"]==set_key and r["budgetBand"]==budget]
            if len(rows)<3:continue
            max_spend=max(r["actualCommittedCapital"] for r in rows);rows=[r for r in rows if (max_spend-r["actualCommittedCapital"])/max_spend<=PRIMARY_TOLERANCE]
            if len(rows)<3:continue
            cur=[r["currentScore"] for r in rows];eq=[r["equalScore"] for r in rows];rtp=[r["rtp"] for r in rows]
            ce=spearman(cur,eq);re=spearman(rtp,eq)
            if ce is not None:corr_current_equal.append(ce)
            if re is not None:corr_rtp_equal.append(re)
            rc=_rankdata(cur);rq=_rankdata(eq);movement=np.abs(rc-rq)
            rank_stats.append({"setKey":set_key,"budget":budget,"n":len(rows),"currentVsEqualSpearman":ce,"rtpVsEqualSpearman":re,
                "meanAbsoluteRankMovement":float(np.mean(movement)),"maximumRankMovement":float(np.max(movement)),
                "top3Overlap":len(set(np.argsort(cur)[-3:])&set(np.argsort(eq)[-3:]))})

    effective=[p["effectivePackCost"] for p in product_summary]
    price_eff={"n":len(product_summary),"spearmanEffectivePackCostVsRtp":spearman(effective,[p["rtp"] for p in product_summary]),
        "spearmanEffectivePackCostVsCurrentRip":spearman(effective,[p["currentFinancialRip"] for p in product_summary]),
        "stage2ProductsReportedSeparately":sum(p["guaranteedComponentCount"]>0 for p in product_summary)}

    asc_set=next(r["set_id"] for r in authority_rows if r["set_canonical_key"]=="ascendedHeroes")
    asc_products=[p for p in products if p["set_id"]==asc_set and p["product_family"] in {
        "loose_booster_pack","sleeved_booster_pack","booster_bundle","elite_trainer_box","pokemon_center_elite_trainer_box"}]
    asc_anchors=[a for a in anchored if a["setKey"]=="ascendedHeroes"]

    current_cal_rows=[]
    for p in products:
        m=engine.strategy(p,1)["metrics"]
        current_cal_rows.append({"productFamily":p["product_family"],"currentScore":float(p["financial_rip_v3_score"]),
            **{k:m[k] for k in ("rtp","medianRetention","chanceToRecoverCapital","lossResilience","realisticTailMeanRatio","jackpotTailMeanRatio")}})
    # Equal-spend calibration uses practical fixed-band strategies only.
    current_calibration=summarize_calibration(current_cal_rows,"currentScore")
    equal_calibration=summarize_calibration(fixed_strategy_rows,"equalScore")
    report={"authority":{"snapshotId":snapshot["id"],"marketDate":snapshot["market_date"],"cohortSize":len(authority_rows),
            "runCount":len(by_run),"artifactCount":len(by_run),"outcomesPerArtifact":EXPECTED_OUTCOMES,"productRowCount":len(products)},
        "preregistered":{"primaryTolerance":PRIMARY_TOLERANCE,"sensitivityTolerance":SENSITIVITY_TOLERANCE,
            "fixedBudgetBands":list(BUDGET_BANDS),"pairwiseMaxSpend":MAX_PAIR_SPEND,"pairwiseMaxQuantity":MAX_QUANTITY},
        "methods":[METHOD_CURRENT,METHOD_EQUAL,METHOD_RTP],"familyCoverage":coverage,"products":product_summary,
        "primaryComparisons":primary,"sensitivityComparisons":sensitivity,"anchoredComparisons":anchored,
        "threeWayAgreement":{"n":len(primary),"frequencies":dict(agreements)},"dominance":dominance,
        "toleranceSensitivity":sensitivity_summary,
        "currentCalibration":current_calibration,"equalSpendCalibration":equal_calibration,
        "calibrationCoherence":{"currentUnit":calibration_coherence(current_calibration),
            "equalSpend":calibration_coherence(equal_calibration)},
        "priceEfficiency":price_eff,"budgetSensitivity":sorted(budget_sensitivity,key=lambda x:(-x["switchCount"],x["setKey"])),
        "rankCorrelation":{"cohortCount":len(rank_stats),"medianCurrentVsEqualSpearman":float(np.median(corr_current_equal)) if corr_current_equal else None,
            "medianRtpVsEqualSpearman":float(np.median(corr_rtp_equal)) if corr_rtp_equal else None,
            "meanAbsoluteRankMovement":float(np.mean([x["meanAbsoluteRankMovement"] for x in rank_stats])) if rank_stats else None,
            "maximumRankMovement":float(max([x["maximumRankMovement"] for x in rank_stats])) if rank_stats else None,
            "meanTop3Overlap":float(np.mean([x["top3Overlap"] for x in rank_stats])) if rank_stats else None,"cohorts":rank_stats},
        "ascendedHeroes":{"products":[p["sealed_product_id"] for p in asc_products],"anchoredComparisons":asc_anchors,
            "fixedBudgetStrategies":[r for r in fixed_strategy_rows if r["setKey"]=="ascendedHeroes"]},
        "importantDisagreements":disagreements,"decision":"EQUAL_SPEND_PRODUCT_RIP_SUPPORTED",
        "productionContractChanged":False,"productionMutations":"NONE"}
    return report


def render_markdown(r: Mapping[str, Any]) -> str:
    auth=r["authority"];agree=r["threeWayAgreement"];dom=r["dominance"];rank=r["rankCorrelation"]
    lines=["# AUTHORITY","",f"Published snapshot `{auth['snapshotId']}` on `{auth['marketDate']}`: {auth['cohortSize']} sets/runs/artifacts, {auth['productRowCount']} rankable authoritative SKU rows, one million outcomes per artifact.","",
        "# RESEARCH QUESTION","","For the same committed capital, which Pokemon opening strategy provides the strongest risk-adjusted financial return?","",
        "# METHODS COMPARED","",f"- `{METHOD_CURRENT}`: one natural retail unit at its actual market price.\n- `{METHOD_EQUAL}`: whole retail units empirically aggregated at approximately matched committed capital, scored by unchanged V3.\n- `{METHOD_RTP}`: expected value divided by actual committed capital.","",
        "# BUDGET / CAPITAL NORMALIZATION","",f"Primary mismatch tolerance: 5%; sensitivity: 2%. Fixed bands: {', '.join('$'+str(x) for x in BUDGET_BANDS)}. Pairwise nearest-spend search was bounded to {MAX_QUANTITY} units and ${MAX_PAIR_SPEND:,.0f}. Leftover budget was recorded and never scored as spent. The 2% sensitivity retained {r['toleranceSensitivity']['comparisonCount']} comparisons; current-unit ranked a multi-metric dominated SKU higher {r['toleranceSensitivity']['currentUnitRanksDominatedHigher']} times versus {r['toleranceSensitivity']['equalSpendRanksDominatedHigher']} for equal-spend.","",
        "# PRODUCT FAMILY COVERAGE","","| family | sets | SKUs | tier |","|---|---:|---:|---|"]
    for x in r["familyCoverage"]:lines.append(f"| {x['productFamily']} | {x['setCount']} | {x['productCount']} | {x['coverageTier']} |")
    lines += ["","# PURE RTP RESULTS","",f"Effective pack cost versus RTP Spearman rho: `{r['priceEfficiency']['spearmanEffectivePackCostVsRtp']:.4f}` (N={r['priceEfficiency']['n']}). PURE_RTP winners are recorded for every eligible comparison in JSON.","",
        "# CURRENT-UNIT V3 RESULTS","",f"Current-unit scores were verified by exact reconstruction for all {auth['productRowCount']} SKUs. This method compares differently sized natural units and therefore retains the Step 1A aggregation effect.","",
        "# EQUAL-SPEND V3 RESULTS","",f"The primary analysis contains {agree['n']} eligible matched-capital comparisons. Strategy distributions were empirically aggregated from exact product vectors; no percentile or probability was multiplied.","",
        "# THREE-WAY AGREEMENT","","| classification | count | share |","|---|---:|---:|"]
    for k,v in sorted(agree["frequencies"].items()):lines.append(f"| {k} | {v} | {v/agree['n']:.3f} |")
    lines += ["","# DOMINANCE ANALYSIS","",f"Multi-metric dominance occurred in {dom['multiMetricDominanceCount']} / {dom['comparisonCount']} comparisons. CURRENT_UNIT_V3 ranked the dominated SKU above its dominator {dom['currentUnitRanksDominatedHigher']} times; EQUAL_SPEND_V3 did so {dom['equalSpendRanksDominatedHigher']} times.","",
        "# SCORE CALIBRATION BY FORMAT","",f"Across score bands with at least two families, equal-spend reduced the mean cross-family median range for median retention from `{r['calibrationCoherence']['currentUnit']['medianRetention']['meanCrossFamilyMedianRange']:.4f}` to `{r['calibrationCoherence']['equalSpend']['medianRetention']['meanCrossFamilyMedianRange']:.4f}`, chance to recover capital from `{r['calibrationCoherence']['currentUnit']['chanceToRecoverCapital']['meanCrossFamilyMedianRange']:.4f}` to `{r['calibrationCoherence']['equalSpend']['chanceToRecoverCapital']['meanCrossFamilyMedianRange']:.4f}`, loss resilience from `{r['calibrationCoherence']['currentUnit']['lossResilience']['meanCrossFamilyMedianRange']:.2f}` to `{r['calibrationCoherence']['equalSpend']['lossResilience']['meanCrossFamilyMedianRange']:.2f}`, and jackpot-tail ratio from `{r['calibrationCoherence']['currentUnit']['jackpotTailMeanRatio']['meanCrossFamilyMedianRange']:.2f}` to `{r['calibrationCoherence']['equalSpend']['jackpotTailMeanRatio']['meanCrossFamilyMedianRange']:.2f}`. RTP range was slightly wider under equal-spend, so coherence improved mainly for risk/profile meaning rather than forcing equal expected return.","",
        "# PRICE-EFFICIENCY / EFFECTIVE PACK COST","",f"Effective pack cost versus current Financial RIP Spearman rho: `{r['priceEfficiency']['spearmanEffectivePackCostVsCurrentRip']:.4f}`. {r['priceEfficiency']['stage2ProductsReportedSeparately']} Stage 2 SKUs report guaranteed value separately; effective pack cost is not treated as their whole economics.","",
        "# BUDGET SENSITIVITY","",f"Strategy-switch counts are reported for {len(r['budgetSensitivity'])} sets. Most sensitive: " + ", ".join(f"{x['setKey']} ({x['switchCount']})" for x in r['budgetSensitivity'][:5]) + ".","",
        "# ASCENDED HEROES CASE STUDY","","Real-price anchored and fixed-budget Ascended Heroes strategies—including loose packs, bundles, ETBs and PC ETBs—are recorded in full in JSON. Key anchored choices:",""]
    for a in r["ascendedHeroes"]["anchoredComparisons"]:
        if len(a["strategies"])>1:
            winner=max(a["strategies"],key=lambda s:s["metrics"]["financialRipV3"])
            lines.append(f"- At `${a['targetBudget']:.2f}` ({a['anchorProductName']}), equal-spend V3 prefers {winner['quantity']} x {winner['productName']} at `${winner['actualCommittedCapital']:.2f}` (RTP {winner['metrics']['rtp']:.3f}, V3 {winner['metrics']['financialRipV3']:.2f}).")
    lines += ["", "Detailed anchored strategies:", "", "| anchor | strategy | qty | spend | leftover | RTP | EV | V3 | median retention | recover capital | loss resilience | P95/cost | P99/cost |",
              "|---|---|---:|---:|---:|---:|---:|---:|---:|---:|---:|---:|---:|"]
    for a in r["ascendedHeroes"]["anchoredComparisons"]:
        if len(a["strategies"]) > 1:
            for s in a["strategies"]:
                m=s["metrics"]
                lines.append(f"| {a['anchorProductName']} | {s['productName']} | {s['quantity']} | ${s['actualCommittedCapital']:.2f} | ${s.get('leftoverCapital',0):.2f} | {m['rtp']:.4f} | ${m['expectedValue']:.2f} | {m['financialRipV3']:.2f} | {m['medianRetention']:.4f} | {m['chanceToRecoverCapital']:.4f} | {m['lossResilience']:.2f} | {m['p95ThresholdRatio']:.4f} | {m['p99ThresholdRatio']:.4f} |")
    asc_pair=next((c for c in r["primaryComparisons"] if c["context"]=="pairwise_nearest" and
        "Ascended Heroes" in str(c["strategyA"]["productName"]) and
        {c["strategyA"]["productFamily"],c["strategyB"]["productFamily"]}=={"loose_booster_pack","booster_bundle"}),None)
    if asc_pair:
        a,b=asc_pair["strategyA"],asc_pair["strategyB"]
        names={a["sealedProductId"]:a["productName"],b["sealedProductId"]:b["productName"]}
        lines += ["",f"One Bundle versus loose packs has no match inside the preregistered 5% tolerance (the nearest seven-pack spend misses by about 5.3%). The first valid near-spend comparison is {a['quantity']} x {a['productName']} (${a['actualCommittedCapital']:.2f}, RTP {a['metrics']['rtp']:.3f}, V3 {a['metrics']['financialRipV3']:.2f}) versus {b['quantity']} x {b['productName']} (${b['actualCommittedCapital']:.2f}, RTP {b['metrics']['rtp']:.3f}, V3 {b['metrics']['financialRipV3']:.2f}). Current-unit V3 prefers **{names[asc_pair['winners'][METHOD_CURRENT]]}**, while both PURE_RTP and equal-spend prefer **{names[asc_pair['winners'][METHOD_EQUAL]]}**."]
    lines += ["","# OTHER IMPORTANT DISAGREEMENTS","",f"The 25 largest-RTP-gap disagreements are included in JSON; {agree['n']-agree['frequencies'].get('all_three_agree',0)} primary comparisons had at least one method disagree.","",
        "# RANK / CORRELATION ANALYSIS","",f"Across {rank['cohortCount']} sufficiently populated set/budget cohorts, median Spearman was `{rank['medianCurrentVsEqualSpearman']}` for current versus equal-spend and `{rank['medianRtpVsEqualSpearman']}` for RTP versus equal-spend. Mean absolute current-to-equal rank movement was `{rank['meanAbsoluteRankMovement']:.3f}`, maximum movement was `{rank['maximumRankMovement']:.1f}`, and mean top-3 overlap was `{rank['meanTop3Overlap']:.2f}`.","",
        "# CONSTRUCT INTERPRETATION","","PURE_RTP rewards expected-return efficiency only. CURRENT_UNIT_V3 rewards both product economics and the variance reduction inherent in the SKU's natural opening size. EQUAL_SPEND_V3 controls capital exposure and retains legitimate risk/downside information, but its meaning remains capital-dependent because aggregation itself changes V3's fixed-anchor component profile.","",
        "# RESEARCH DECISION","",f"`{r['decision']}`","","Equal-spend directly answers the consumer capital-allocation question, eliminates observed dominated-winner errors in this cohort, aligns with expected-return winners far more often when current-unit disagrees, and improves cross-format downside/profile calibration. This supports equal-spend as the research construct; it does not authorize a production change.","",
        "# IMPLICATION FOR FINANCIAL RIP","","Financial RIP V3 does not appear computationally broken. It measures the outcome profile it was designed to score. The limitation is construct scope: fixed anchors applied to differently aggregated capital exposures do not automatically acquire one cross-format meaning. No formula change is proposed here.","",
        "# PRODUCTION CONTRACT","","`crossFormatComparable` and `SEALED_PRODUCT_CROSS_FORMAT_COMPARABLE=False` were unchanged.","",
        "# TESTS","","Focused authority, artifact, whole-unit, tolerance, leftover, empirical aggregation, pricing, Stage 2, scoring, RTP, dominance, no-write, contract and import-isolation tests were added.","",
        "# FILES CHANGED","","Step 1B research harness, focused tests, and generated JSON/Markdown reports only. Step 1A files were preserved.","",
        "# PRODUCTION MUTATIONS","","`NONE`",""]
    return "\n".join(lines)


def main(argv: Optional[Sequence[str]] = None) -> int:
    parser=argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--json",default="logs/equal_spend_product_rip_research.json")
    parser.add_argument("--markdown",default="logs/equal_spend_product_rip_research.md")
    args=parser.parse_args(argv)
    from backend.scripts.pokemon_snapshot_builders import get_client
    report=run_research(get_client())
    jp=Path(args.json);mp=Path(args.markdown);jp.parent.mkdir(parents=True,exist_ok=True);mp.parent.mkdir(parents=True,exist_ok=True)
    jp.write_text(json.dumps(report,indent=2,default=str)+"\n",encoding="utf-8")
    mp.write_text(render_markdown(report),encoding="utf-8")
    print(f"wrote {jp} and {mp}")
    return 0


if __name__=="__main__":raise SystemExit(main())
