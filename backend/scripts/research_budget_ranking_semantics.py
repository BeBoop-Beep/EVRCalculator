"""SELECT-only validation of Budget-Normalized Product Ranking V1 semantics.

Answers ONE question: should the ranking mean "best whole-product strategy
that fits within a budget ceiling" (FLOOR_BUDGET) or "approximately equal
actual committed capital" (MATCHED_CAPITAL)?

Read-only. No production writes, no schema changes, no publication.

    python -m backend.scripts.research_budget_ranking_semantics \
        --json logs/budget_ranking_semantics.json \
        --markdown logs/budget_ranking_semantics.md
"""

from __future__ import annotations

import argparse
import itertools
import json
import math
import sys
from collections import Counter, defaultdict
from pathlib import Path
from typing import Any, Dict, List, Mapping, Optional, Sequence

import numpy as np

REPO_ROOT = Path(__file__).resolve().parents[2]
if str(REPO_ROOT) not in sys.path:
    sys.path.insert(0, str(REPO_ROOT))

from backend.calculations.evr.budget_normalized_product_ranking import (
    build_budget_strategy_values,
    whole_unit_allocation,
)
from backend.calculations.evr.financial_rip_v3 import build_financial_rip_v3
from backend.calculations.evr.financial_rip_v4 import (
    project_financial_rip_v4_from_v3_payload,
)
from backend.db.services.pack_outcome_artifact_service import load_pack_outcome_artifact
from backend.desirability.weighted_rip import compute_overall_rip_v10
from backend.scripts.build_budget_normalized_product_rankings import (
    build_stage1_distributions_cached,
)
from backend.scripts.pokemon_snapshot_builders import get_client
from backend.scripts.research_equal_spend_product_rip_v4 import (
    MAX_PAIR_SPEND,
    MAX_QUANTITY,
    PRIMARY_TOLERANCE,
    SENSITIVITY_TOLERANCE,
    multi_metric_dominator,
    nearest_spend_pair,
)

FULL_MARKET_ANCHOR = 1350.0
STRESS_ANCHORS = (1350.0, 1400.0, 1450.0, 1500.0, 1600.0)
BAND_500 = 500.0
ROUNDING_INCREMENTS = (25.0, 50.0, 100.0)
PRICE_SCENARIOS = (1320.0, 1330.0, 1339.19, 1345.0, 1349.0, 1351.0, 1375.0, 1399.0, 1401.0)
DOMINANCE_METRICS = ("rtp", "medianRetention", "chanceToRecoverCapital", "lossResilience")

#: The preregistered pairwise bound excludes any strategy needing >$1000 of
#: committed capital. At a Full Market scale that is a structural constraint,
#: so we ALSO run a relaxed bound to prove whether findings are parametric.
RELAXED_PAIR_SPEND = 2800.0


# ------------------------------------------------------------------ authority
def load_pinned_products(client: Any, price_as_of: Optional[str] = None) -> tuple[List[Dict[str, Any]], Dict[str, Any]]:
    """One coherent priced cohort, pinned to a SINGLE `price_as_of`.

    `build_budget_normalized_product_rankings.load_eligible_products` fails
    closed the moment any SKU has more than one V4-ready run — which is
    correct for publication but unusable here, because production keeps
    landing partial single-set refresh runs. Rather than "latest run wins"
    (which would silently blend 2026-08-17 prices for most SKUs with newer
    prices for a handful — exactly the mixed authority this pass must
    refuse), we pin to the price_as_of covering the MOST SKUs and drop
    every run outside it, then re-assert one run per SKU.
    """
    rows = client.table("simulation_sealed_product_results").select("*").eq(
        "financial_rip_v4_status", "ready"
    ).execute().data or []
    rows = [r for r in rows if float(r.get("product_market_cost") or 0) > 0]
    if not rows:
        raise RuntimeError("no V4-ready priced sealed-product rows exist")

    by_as_of: Dict[str, list] = defaultdict(list)
    for r in rows:
        by_as_of[str(r.get("price_as_of"))].append(r)
    if price_as_of is not None:
        if price_as_of not in by_as_of:
            raise RuntimeError(
                "requested price_as_of %s has no V4-ready rows (available: %s)"
                % (price_as_of, sorted(by_as_of))
            )
        pinned_as_of = price_as_of
    else:
        # Deterministic: most SKUs wins; ties break to the LATEST date. Both
        # halves matter — production now carries two complete 137-SKU cohorts
        # (2026-08-17 and 2026-08-21), so a count-only rule is a coin flip.
        pinned_as_of = max(
            by_as_of,
            key=lambda k: (len({str(r["sealed_product_id"]) for r in by_as_of[k]}), k),
        )
    pinned = by_as_of[pinned_as_of]

    seen: Dict[str, set] = defaultdict(set)
    for r in pinned:
        seen[str(r["sealed_product_id"])].add(str(r["calculation_run_id"]))
    ambiguous = sorted(p for p, runs in seen.items() if len(runs) > 1)
    if ambiguous:
        raise RuntimeError(
            "MIXED AUTHORITY: %d SKU(s) have >1 V4-ready run inside price_as_of %s"
            % (len(ambiguous), pinned_as_of)
        )

    excluded = [
        {
            "sealedProductId": str(r["sealed_product_id"]),
            "productName": r.get("product_name"),
            "calculationRunId": str(r["calculation_run_id"]),
            "priceAsOf": str(r.get("price_as_of")),
            "reason": "outside_pinned_price_as_of",
        }
        for k, group in by_as_of.items() if k != pinned_as_of for r in group
    ]
    provenance = {
        "pinnedPriceAsOf": pinned_as_of,
        "excludedRunCount": len({e["calculationRunId"] for e in excluded}),
        "excludedRowCount": len(excluded),
        "excludedRows": excluded,
    }
    return pinned, provenance


# ---------------------------------------------------------------- statistics
def _rankdata(values: Sequence[float]) -> np.ndarray:
    a = np.asarray(values, float)
    order = np.argsort(a, kind="mergesort")
    ranks = np.empty(len(a), float)
    i = 0
    while i < len(a):
        j = i
        while j + 1 < len(a) and a[order[j + 1]] == a[order[i]]:
            j += 1
        ranks[order[i:j + 1]] = 0.5 * (i + j) + 1.0
        i = j + 1
    return ranks


def spearman(x: Sequence[float], y: Sequence[float]) -> Optional[float]:
    if len(x) < 3:
        return None
    rx, ry = _rankdata(x), _rankdata(y)
    if np.std(rx) == 0 or np.std(ry) == 0:
        return None
    return float(np.corrcoef(rx, ry)[0, 1])


def pearson(x: Sequence[float], y: Sequence[float]) -> Optional[float]:
    if len(x) < 3:
        return None
    a, b = np.asarray(x, float), np.asarray(y, float)
    if np.std(a) == 0 or np.std(b) == 0:
        return None
    return float(np.corrcoef(a, b)[0, 1])


def kendall(x: Sequence[float], y: Sequence[float]) -> Optional[float]:
    n = len(x)
    if n < 3:
        return None
    con = dis = 0
    for i in range(n):
        for j in range(i + 1, n):
            s = np.sign(x[i] - x[j]) * np.sign(y[i] - y[j])
            if s > 0:
                con += 1
            elif s < 0:
                dis += 1
    tot = con + dis
    return None if tot == 0 else float((con - dis) / tot)


def overlap(a: Sequence[str], b: Sequence[str], k: int) -> int:
    return len(set(a[:k]) & set(b[:k]))


def describe(values: Sequence[float]) -> Dict[str, Any]:
    arr = np.asarray(values, float)
    if arr.size == 0:
        return {}
    return {
        "n": int(arr.size),
        "mean": float(np.mean(arr)),
        "median": float(np.median(arr)),
        "stdDev": float(np.std(arr, ddof=1)) if arr.size > 1 else 0.0,
        "minimum": float(np.min(arr)),
        "p10": float(np.percentile(arr, 10)),
        "p25": float(np.percentile(arr, 25)),
        "p75": float(np.percentile(arr, 75)),
        "p90": float(np.percentile(arr, 90)),
        "maximum": float(np.max(arr)),
    }


# ------------------------------------------------------------------- engine
class StrategyEngine:
    """Caches base distributions per run and scored strategies per (SKU, qty)."""

    def __init__(self, client: Any, products: Sequence[Mapping[str, Any]]):
        self.products = {str(p["sealed_product_id"]): dict(p) for p in products}
        run_ids = sorted({str(p["calculation_run_id"]) for p in products})
        self.artifacts = {r: load_pack_outcome_artifact(client, r) for r in run_ids}
        self._base: Dict[tuple, Any] = {}
        self._scored: Dict[tuple, Dict[str, Any]] = {}

    def base_values(self, product: Mapping[str, Any]):
        run_id = str(product["calculation_run_id"])
        rc = int(product.get("random_pack_count") or product["pack_count"])
        key = (run_id, rc)
        if key not in self._base:
            self._base[key] = build_stage1_distributions_cached(self.artifacts[run_id], rc, run_id)
        return self._base[key]

    def strategy(self, product_id: str, quantity: int) -> Dict[str, Any]:
        key = (product_id, quantity)
        if key in self._scored:
            return self._scored[key]
        product = self.products[product_id]
        price = float(product["product_market_cost"])
        committed = quantity * price
        values = build_budget_strategy_values(
            base_random_pack_values=self.base_values(product),
            quantity=quantity,
            guaranteed_component_market_value=product.get("guaranteed_component_market_value"),
            canonical_set_key="budget:%s" % product_id,
            run_fingerprint=None,
        )
        v3 = build_financial_rip_v3(values, committed)
        v4 = project_financial_rip_v4_from_v3_payload(v3)
        # The V4 PROJECTION carries an empty `audit.normalizedInputs`; the raw
        # distribution metrics survive only on the V3 payload it is projected
        # from. Reading them off V4 silently yields None for
        # typical_retention_ratio / true_win_probability, which makes the
        # four-metric dominance test vacuous (0 comparable pairs). Always
        # source the raws from V3.
        raw = {k: rec.get("raw") for k, rec in ((v3.get("audit") or {}).get("normalizedInputs") or {}).items()}
        ca = product.get("collector_appeal_score")
        score = v4.get("score")
        v10 = None
        if v4.get("rankable") and score is not None and ca is not None:
            v10 = compute_overall_rip_v10(score, ca)
        out = {
            "sealedProductId": product_id,
            "productName": product.get("product_name"),
            "productFamily": product.get("product_family"),
            "setId": str(product.get("set_id")),
            "unitPrice": price,
            "quantity": quantity,
            "actualCommittedCapital": committed,
            "financialRipV4": score,
            "financialRipV4Rankable": bool(v4.get("rankable")),
            "overallRipV10": (v10 or {}).get("score"),
            "expectedValue": float(np.mean(values)),
            "medianValue": float(np.median(values)),
            "rtp": float(np.mean(values) / committed),
            "medianRetention": raw.get("typical_retention_ratio"),
            "chanceToRecoverCapital": raw.get("true_win_probability"),
            "lossResilience": (v4.get("components") or {}).get("loss_resilience", {}).get("score"),
            "probAtOrAboveCost": float(np.mean(np.asarray(values) >= committed)),
        }
        missing = [m for m in DOMINANCE_METRICS if out.get(m) is None]
        if missing:
            raise RuntimeError(
                "strategy %s x%d is missing dominance metric(s) %s — a vacuous "
                "dominance test would report a misleading 'zero inversions'"
                % (product.get("product_name"), quantity, missing)
            )
        self._scored[key] = out
        return out


def sort_key(entry: Mapping[str, Any]) -> tuple:
    """Mirrors the production comparator in budget_normalized_product_ranking."""
    o, f = entry.get("overallRipV10"), entry.get("financialRipV4")
    r = entry.get("chanceToRecoverCapital")
    mismatch = abs(entry.get("actualCommittedCapital", 0.0) - entry.get("targetBudget", 0.0))
    return (
        -(o if o is not None else float("-inf")),
        -(f if f is not None else float("-inf")),
        -(r if r is not None else float("-inf")),
        mismatch,
        str(entry.get("sealedProductId") or ""),
    )


def floor_ranking(engine: StrategyEngine, budget: float) -> List[Dict[str, Any]]:
    rows: List[Dict[str, Any]] = []
    for pid, product in engine.products.items():
        alloc = whole_unit_allocation(budget, float(product["product_market_cost"]))
        if not alloc["eligible"]:
            continue
        s = dict(engine.strategy(pid, alloc["quantity"]))
        s.update({
            "targetBudget": budget,
            "unusedCapital": alloc["unusedCapital"],
            "unusedCapitalPercent": alloc["unusedCapitalPercent"],
            "capitalUtilization": alloc["actualCommittedCapital"] / budget,
        })
        rows.append(s)
    rankable = [r for r in rows if r.get("overallRipV10") is not None]
    ordered = sorted(rankable, key=sort_key)
    for i, r in enumerate(ordered, start=1):
        r["rank"] = i
    return ordered


# -------------------------------------------------------- matched capital
def matched_capital_ranking(engine: StrategyEngine, tolerance: float,
                            max_spend: float) -> Dict[str, Any]:
    """Copeland ordering over pairwise approximately-equal-committed-capital
    comparisons, using the repository's existing `nearest_spend_pair`."""
    pids = sorted(engine.products)
    prices = {p: float(engine.products[p]["product_market_cost"]) for p in pids}
    wins: Counter = Counter()
    losses: Counter = Counter()
    comparisons = 0
    matched_pairs: List[Dict[str, Any]] = []
    unmatched_counts: Counter = Counter()
    dominance = {"comparablePairs": 0, "inversions": 0, "inversionDetail": []}

    for a, b in itertools.combinations(pids, 2):
        match = nearest_spend_pair(prices[a], prices[b], tolerance=tolerance,
                                   max_spend=max_spend, max_quantity=MAX_QUANTITY)
        if match is None:
            unmatched_counts[a] += 1
            unmatched_counts[b] += 1
            continue
        sa = engine.strategy(a, match["quantityA"])
        sb = engine.strategy(b, match["quantityB"])
        if sa.get("overallRipV10") is None or sb.get("overallRipV10") is None:
            continue
        comparisons += 1
        if sa["overallRipV10"] >= sb["overallRipV10"]:
            winner, loser = a, b
        else:
            winner, loser = b, a
        wins[winner] += 1
        losses[loser] += 1
        matched_pairs.append({
            "a": a, "b": b, "quantityA": match["quantityA"], "quantityB": match["quantityB"],
            "spendA": match["spendA"], "spendB": match["spendB"], "mismatch": match["mismatch"],
            "winner": winner,
        })
        dom = multi_metric_dominator(sa, sb)
        if dom is not None:
            dominance["comparablePairs"] += 1
            dominated_won = (dom == "A" and winner == b) or (dom == "B" and winner == a)
            if dominated_won:
                dominance["inversions"] += 1
                if len(dominance["inversionDetail"]) < 40:
                    dominance["inversionDetail"].append({
                        "dominator": a if dom == "A" else b,
                        "dominatorName": (sa if dom == "A" else sb)["productName"],
                        "rankedHigher": winner,
                        "rankedHigherName": (sa if winner == a else sb)["productName"],
                        "mismatch": match["mismatch"],
                    })

    represented = sorted({p for p in pids if wins[p] + losses[p] > 0})
    scored = sorted(represented, key=lambda p: (-(wins[p] - losses[p]), -wins[p], p))
    ranks = {p: i for i, p in enumerate(scored, start=1)}
    return {
        "tolerance": tolerance,
        "maxSpend": max_spend,
        "comparisonCount": comparisons,
        "representedSkuCount": len(represented),
        "excludedSkuCount": len(pids) - len(represented),
        "excludedSkus": sorted(set(pids) - set(represented)),
        "ranks": ranks,
        "order": scored,
        "copeland": {p: wins[p] - losses[p] for p in represented},
        "dominance": dominance,
        "matchedPairSample": matched_pairs[:50],
    }


def floor_dominance(ranked: Sequence[Mapping[str, Any]]) -> Dict[str, Any]:
    """Dominance integrity of a floor-budget ranking: does a strategy that
    weakly dominates on all four core metrics ever rank BELOW its dominatee?"""
    out = {"comparablePairs": 0, "inversions": 0, "inversionDetail": []}
    for a, b in itertools.combinations(ranked, 2):
        dom = multi_metric_dominator(a, b)
        if dom is None:
            continue
        out["comparablePairs"] += 1
        dominator = a if dom == "A" else b
        other = b if dom == "A" else a
        if dominator["rank"] > other["rank"]:
            out["inversions"] += 1
            if len(out["inversionDetail"]) < 40:
                out["inversionDetail"].append({
                    "dominator": dominator["productName"],
                    "dominatorRank": dominator["rank"],
                    "dominatorUtilization": dominator["capitalUtilization"],
                    "dominated": other["productName"],
                    "dominatedRank": other["rank"],
                    "dominatedUtilization": other["capitalUtilization"],
                })
    out["inversionRate"] = (out["inversions"] / out["comparablePairs"]) if out["comparablePairs"] else None
    return out


def compare_rankings(order_a: Sequence[str], order_b: Sequence[str]) -> Dict[str, Any]:
    common = [p for p in order_a if p in set(order_b)]
    if len(common) < 3:
        return {"commonSkus": len(common)}
    ra = {p: i for i, p in enumerate(order_a, start=1)}
    rb = {p: i for i, p in enumerate(order_b, start=1)}
    xa = [ra[p] for p in common]
    xb = [rb[p] for p in common]
    diffs = [abs(ra[p] - rb[p]) for p in common]
    movers = sorted(common, key=lambda p: -abs(ra[p] - rb[p]))
    return {
        "commonSkus": len(common),
        "spearman": spearman(xa, xb),
        "kendall": kendall(xa, xb) if len(common) <= 160 else None,
        "top5Overlap": overlap(order_a, order_b, 5),
        "top10Overlap": overlap(order_a, order_b, 10),
        "top20Overlap": overlap(order_a, order_b, 20),
        "meanAbsoluteRankDifference": float(np.mean(diffs)),
        "medianAbsoluteRankDifference": float(np.median(diffs)),
        "maximumRankDifference": int(np.max(diffs)),
        "moversAtLeast5": int(sum(1 for d in diffs if d >= 5)),
        "moversAtLeast10": int(sum(1 for d in diffs if d >= 10)),
        "moversAtLeast20": int(sum(1 for d in diffs if d >= 20)),
        "largestDisagreements": [
            {"sealedProductId": p, "rankA": ra[p], "rankB": rb[p], "difference": abs(ra[p] - rb[p])}
            for p in movers[:20]
        ],
    }


def rounding_analysis(max_price: float) -> List[Dict[str, Any]]:
    out = []
    for inc in ROUNDING_INCREMENTS:
        anchor = math.ceil(max_price / inc) * inc
        if anchor < max_price:
            anchor += inc
        scenarios = []
        for price in PRICE_SCENARIOS:
            a = math.ceil(price / inc) * inc
            if a < price:
                a += inc
            scenarios.append({"price": price, "anchor": a})
        distinct = sorted({s["anchor"] for s in scenarios})
        changes = sum(1 for i in range(1, len(scenarios))
                      if scenarios[i]["anchor"] != scenarios[i - 1]["anchor"])
        out.append({
            "increment": inc,
            "anchor": anchor,
            "excessCapitalAboveMaxSku": anchor - max_price,
            "excessCapitalPercent": (anchor - max_price) / max_price,
            "distinctAnchorsAcrossScenarios": len(distinct),
            "anchorChangesAcrossScenarioSweep": changes,
            "scenarios": scenarios,
        })
    return out


# ------------------------------------------------------------------- driver
def run_research(client: Any, price_as_of: Optional[str] = None) -> Dict[str, Any]:
    products, provenance = load_pinned_products(client, price_as_of)
    if not products:
        raise RuntimeError("no V4/V10-ready priced products resolved")

    run_ids = sorted({str(p["calculation_run_id"]) for p in products})
    ca_versions = sorted({str(p.get("collector_appeal_version")) for p in products})
    prices = [float(p["product_market_cost"]) for p in products]
    price_as_of = sorted({str(p.get("price_as_of")) for p in products})
    families = Counter(p["product_family"] for p in products)

    v4_versions = sorted({str(p.get("financial_rip_v4_version")) for p in products})
    v10_versions = sorted({str(p.get("overall_rip_v10_version")) for p in products})
    if len(v4_versions) != 1 or len(v10_versions) != 1 or len(ca_versions) != 1:
        raise RuntimeError(
            "MIXED AUTHORITY: v4=%s v10=%s ca=%s" % (v4_versions, v10_versions, ca_versions)
        )

    authority = {
        "sourceTable": "simulation_sealed_product_results",
        "authorityFilter": "financial_rip_v4_status == 'ready'",
        "calculationRunIds": run_ids,
        "runCount": len(run_ids),
        "productCount": len(products),
        "familyCounts": dict(sorted(families.items())),
        "minimumSkuPrice": min(prices),
        "maximumSkuPrice": max(prices),
        "priceAsOfRange": [price_as_of[0], price_as_of[-1]],
        "financialRipVersion": v4_versions[0],
        "overallRipVersion": v10_versions[0],
        "collectorAppealVersion": ca_versions[0],
        "provenance": provenance,
    }

    engine = StrategyEngine(client, products)

    # ---- floor rankings at every anchor + the $500 band
    anchors = list(STRESS_ANCHORS)
    rankings: Dict[float, List[Dict[str, Any]]] = {}
    for budget in anchors + [BAND_500]:
        rankings[budget] = floor_ranking(engine, budget)

    primary = rankings[FULL_MARKET_ANCHOR]
    primary_order = [r["sealedProductId"] for r in primary]

    util = [r["capitalUtilization"] for r in primary]
    unused = [r["unusedCapital"] for r in primary]
    unused_pct = [r["unusedCapitalPercent"] for r in primary]

    full_market_block = {
        "targetBudget": FULL_MARKET_ANCHOR,
        "skuCount": len(primary),
        "coverage": "%d/%d" % (len(primary), len(products)),
        "capitalUtilization": describe(util),
        "unusedDollars": describe(unused),
        "unusedPercent": describe(unused_pct),
        "worstUtilization": [
            {
                "productName": r["productName"], "productFamily": r["productFamily"],
                "unitPrice": r["unitPrice"], "quantity": r["quantity"],
                "actualCommittedCapital": r["actualCommittedCapital"],
                "unusedCapital": r["unusedCapital"],
                "capitalUtilization": r["capitalUtilization"], "rank": r["rank"],
            }
            for r in sorted(primary, key=lambda x: x["capitalUtilization"])[:15]
        ],
    }

    ranks = [r["rank"] for r in primary]
    correlations = {
        "spearmanUtilizationVsRank": spearman(util, ranks),
        "pearsonUtilizationVsRank": pearson(util, ranks),
        "spearmanUtilizationVsFinancialRipV4": spearman(util, [r["financialRipV4"] for r in primary]),
        "spearmanUtilizationVsOverallRipV10": spearman(util, [r["overallRipV10"] for r in primary]),
        "spearmanUnusedPercentVsRank": spearman(unused_pct, ranks),
        "pearsonUnusedPercentVsRank": pearson(unused_pct, ranks),
        "spearmanUnitPriceVsRank": spearman([r["unitPrice"] for r in primary], ranks),
        "spearmanQuantityVsRank": spearman([r["quantity"] for r in primary], ranks),
    }

    # ---- utilization quartiles
    edges = np.percentile(np.asarray(util, float), [25, 50, 75])
    quartiles = []
    for qi in range(4):
        members = [r for r in primary
                   if (qi == 0 and r["capitalUtilization"] <= edges[0])
                   or (qi == 1 and edges[0] < r["capitalUtilization"] <= edges[1])
                   or (qi == 2 and edges[1] < r["capitalUtilization"] <= edges[2])
                   or (qi == 3 and r["capitalUtilization"] > edges[2])]
        if not members:
            continue
        quartiles.append({
            "quartile": "Q%d" % (qi + 1),
            "skuCount": len(members),
            "meanUtilization": float(np.mean([m["capitalUtilization"] for m in members])),
            "medianRank": float(np.median([m["rank"] for m in members])),
            "meanFinancialRipV4": float(np.mean([m["financialRipV4"] for m in members])),
            "meanOverallRipV10": float(np.mean([m["overallRipV10"] for m in members])),
            "familyDistribution": dict(Counter(m["productFamily"] for m in members)),
        })

    # ---- matched capital
    matched = {
        "primaryPreregistered": matched_capital_ranking(engine, PRIMARY_TOLERANCE, MAX_PAIR_SPEND),
        "sensitivityPreregistered": matched_capital_ranking(engine, SENSITIVITY_TOLERANCE, MAX_PAIR_SPEND),
        "primaryRelaxedSpend": matched_capital_ranking(engine, PRIMARY_TOLERANCE, RELAXED_PAIR_SPEND),
    }
    floor_vs_matched = {
        key: compare_rankings(primary_order, block["order"])
        for key, block in matched.items()
    }

    # ---- dominance under the floor method
    floor_dom = {"fullMarket_1350": floor_dominance(primary)}

    # ---- retained-cash diagnostic
    retained = []
    for r in primary:
        retained.append({
            "sealedProductId": r["sealedProductId"],
            "productName": r["productName"],
            "productFamily": r["productFamily"],
            "rank": r["rank"],
            "terminalMedianWealth": r["medianValue"] + r["unusedCapital"],
            "terminalExpectedWealth": r["expectedValue"] + r["unusedCapital"],
            "terminalRtpOnBudget": (r["expectedValue"] + r["unusedCapital"]) / FULL_MARKET_ANCHOR,
            "probAtOrAboveBudget": r["probAtOrAboveCost"],
        })
    retained_order = [x["sealedProductId"] for x in
                      sorted(retained, key=lambda x: -x["terminalRtpOnBudget"])]
    retained_median_order = [x["sealedProductId"] for x in
                             sorted(retained, key=lambda x: -x["terminalMedianWealth"])]
    retained_block = {
        "definition": "terminalWealth = openingOutcome + unusedCash, evaluated on the full budget",
        "vsTerminalRtpOnBudget": compare_rankings(primary_order, retained_order),
        "vsTerminalMedianWealth": compare_rankings(primary_order, retained_median_order),
        "rows": sorted(retained, key=lambda x: x["rank"])[:25],
    }

    # ---- anchor stability
    anchor_stability = []
    for budget in anchors:
        order = [r["sealedProductId"] for r in rankings[budget]]
        cmp = compare_rankings(primary_order, order) if budget != FULL_MARKET_ANCHOR else None
        anchor_stability.append({
            "anchor": budget,
            "coverage": "%d/%d" % (len(rankings[budget]), len(products)),
            "rankedCount": len(rankings[budget]),
            "meanUtilization": float(np.mean([r["capitalUtilization"] for r in rankings[budget]])),
            "versus1350": cmp,
            "dominance": floor_dominance(rankings[budget]),
        })

    adjacent = []
    for i in range(1, len(anchors)):
        a, b = anchors[i - 1], anchors[i]
        adjacent.append({
            "from": a, "to": b,
            "comparison": compare_rankings(
                [r["sealedProductId"] for r in rankings[a]],
                [r["sealedProductId"] for r in rankings[b]],
            ),
        })

    # ---- SKU-level stability across the stress anchors
    per_sku: Dict[str, Dict[str, Any]] = {}
    for budget in anchors:
        for r in rankings[budget]:
            e = per_sku.setdefault(r["sealedProductId"], {
                "sealedProductId": r["sealedProductId"], "productName": r["productName"],
                "productFamily": r["productFamily"], "unitPrice": r["unitPrice"],
                "ranks": {}, "quantities": {}, "utilizations": {},
            })
            e["ranks"][budget] = r["rank"]
            e["quantities"][budget] = r["quantity"]
            e["utilizations"][budget] = r["capitalUtilization"]

    stability_rows = []
    for e in per_sku.values():
        seq = [e["ranks"][b] for b in anchors if b in e["ranks"]]
        if len(seq) < 2:
            continue
        adj = [abs(seq[i] - seq[i - 1]) for i in range(1, len(seq))]
        stability_rows.append({
            **{k: e[k] for k in ("sealedProductId", "productName", "productFamily", "unitPrice")},
            "bestRank": int(min(seq)), "worstRank": int(max(seq)),
            "rankRange": int(max(seq) - min(seq)),
            "medianRank": float(np.median(seq)), "meanRank": float(np.mean(seq)),
            "meanAbsoluteAdjacentMovement": float(np.mean(adj)),
            "maximumAdjacentMovement": int(max(adj)),
            "quantitiesByAnchor": {str(b): e["quantities"].get(b) for b in anchors},
            "utilizationByAnchor": {str(b): e["utilizations"].get(b) for b in anchors},
        })
    stability_rows.sort(key=lambda x: (-x["rankRange"], -x["maximumAdjacentMovement"]))

    # ---- quantity-threshold events
    events = []
    for e in per_sku.values():
        for i in range(1, len(anchors)):
            a, b = anchors[i - 1], anchors[i]
            qa, qb = e["quantities"].get(a), e["quantities"].get(b)
            if qa is None or qb is None or qb <= qa:
                continue
            events.append({
                "sealedProductId": e["sealedProductId"], "productName": e["productName"],
                "productFamily": e["productFamily"], "unitPrice": e["unitPrice"],
                "fromAnchor": a, "toAnchor": b, "quantityFrom": qa, "quantityTo": qb,
                "rankFrom": e["ranks"].get(a), "rankTo": e["ranks"].get(b),
                "rankDelta": (e["ranks"].get(a) - e["ranks"].get(b))
                if e["ranks"].get(a) is not None and e["ranks"].get(b) is not None else None,
                "utilizationFrom": e["utilizations"].get(a),
                "utilizationTo": e["utilizations"].get(b),
            })
    events.sort(key=lambda x: -abs(x["rankDelta"] or 0))

    # ---- family stability
    family_rows = []
    for family in sorted(families):
        members = [s for s in stability_rows if s["productFamily"] == family]
        if not members:
            continue
        fam_events = [e for e in events if e["productFamily"] == family]
        fam_primary = [r for r in primary if r["productFamily"] == family]
        family_rows.append({
            "productFamily": family,
            "skuCount": len(members),
            "medianRankMovement": float(np.median([m["meanAbsoluteAdjacentMovement"] for m in members])),
            "meanRankMovement": float(np.mean([m["meanAbsoluteAdjacentMovement"] for m in members])),
            "maximumMovement": int(max(m["maximumAdjacentMovement"] for m in members)),
            "medianUtilizationAt1350": float(np.median([r["capitalUtilization"] for r in fam_primary])),
            "medianRankAt1350": float(np.median([r["rank"] for r in fam_primary])),
            "quantityThresholdEvents": len(fam_events),
        })

    # ---- rounding
    rounding = rounding_analysis(max(prices))

    # ---- $500 versus Full Market
    order_500 = [r["sealedProductId"] for r in rankings[BAND_500]]
    band_500 = {
        "rankedCount": len(rankings[BAND_500]),
        "coverage": "%d/%d" % (len(rankings[BAND_500]), len(products)),
        "dominance": floor_dominance(rankings[BAND_500]),
        "versusFullMarket": compare_rankings(order_500, primary_order),
        "meanUtilization": float(np.mean([r["capitalUtilization"] for r in rankings[BAND_500]])),
    }

    return {
        "authority": authority,
        "methods": {
            "FLOOR_BUDGET": "quantity = floor(budget / price); unused cash recorded, never scored.",
            "MATCHED_CAPITAL": "pairwise nearest_spend_pair within tolerance, Copeland-aggregated.",
            "RETAINED_CASH": "terminalWealth = openingOutcome + unusedCash on the full budget.",
        },
        "preregistered": {
            "primaryTolerance": PRIMARY_TOLERANCE,
            "sensitivityTolerance": SENSITIVITY_TOLERANCE,
            "pairwiseMaxSpend": MAX_PAIR_SPEND,
            "relaxedPairwiseMaxSpend": RELAXED_PAIR_SPEND,
            "pairwiseMaxQuantity": MAX_QUANTITY,
            "stressAnchors": list(STRESS_ANCHORS),
        },
        "fullMarketAt1350": full_market_block,
        "utilizationVsRank": correlations,
        "utilizationQuartiles": quartiles,
        "matchedCapital": matched,
        "floorVersusMatched": floor_vs_matched,
        "floorDominance": floor_dom,
        "retainedCash": retained_block,
        "anchorStability": anchor_stability,
        "adjacentAnchorStability": adjacent,
        "mostUnstableSkus": stability_rows[:20],
        "quantityThresholdEvents": events[:40],
        "quantityThresholdEventCount": len(events),
        "familyStability": family_rows,
        "roundingRule": rounding,
        "band500VersusFullMarket": band_500,
        "productionMutations": "NONE",
        "publicationMutations": "NONE",
    }


def main(argv: Optional[Sequence[str]] = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--json", default="logs/budget_ranking_semantics.json")
    parser.add_argument("--markdown", default="logs/budget_ranking_semantics.md")
    parser.add_argument("--price-as-of", default=None,
                        help="Pin the cohort to this price_as_of (default: most SKUs, ties to latest).")
    args = parser.parse_args(argv)

    report = run_research(get_client(), args.price_as_of)
    jp = Path(args.json)
    jp.parent.mkdir(parents=True, exist_ok=True)
    jp.write_text(json.dumps(report, indent=2, default=str) + "\n", encoding="utf-8")

    a = report["authority"]
    fm = report["fullMarketAt1350"]
    print("authority: %d SKUs / %d runs, V4=%s" % (a["productCount"], a["runCount"], a["financialRipVersion"]))
    print("full market 1350: coverage %s, mean util %.4f, median util %.4f, min util %.4f"
          % (fm["coverage"], fm["capitalUtilization"]["mean"],
             fm["capitalUtilization"]["median"], fm["capitalUtilization"]["minimum"]))
    print("utilization vs rank: spearman %s pearson %s"
          % (report["utilizationVsRank"]["spearmanUtilizationVsRank"],
             report["utilizationVsRank"]["pearsonUtilizationVsRank"]))
    for key, block in report["matchedCapital"].items():
        print("matched[%s]: comparisons=%d represented=%d excluded=%d inversions=%d/%d"
              % (key, block["comparisonCount"], block["representedSkuCount"],
                 block["excludedSkuCount"], block["dominance"]["inversions"],
                 block["dominance"]["comparablePairs"]))
    fd = report["floorDominance"]["fullMarket_1350"]
    print("floor dominance @1350: %d inversions / %d comparable pairs"
          % (fd["inversions"], fd["comparablePairs"]))
    for row in report["anchorStability"]:
        v = row["versus1350"]
        print("anchor %s: coverage %s spearman-vs-1350 %s dominance-inv %d"
              % (row["anchor"], row["coverage"],
                 (v or {}).get("spearman"), row["dominance"]["inversions"]))
    print("wrote %s" % jp)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
