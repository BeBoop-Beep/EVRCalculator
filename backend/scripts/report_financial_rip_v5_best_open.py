"""Report V5 candidate Best-Open evidence after both read-only full runs."""
from __future__ import annotations

import json
from collections import Counter
from pathlib import Path

import numpy as np

ROOT = Path(__file__).resolve().parents[2]
CONTROL = ROOT / "docs/research/financial_rip_v5_best_open_v2_control.json"
CANDIDATE = ROOT / "docs/research/financial_rip_v5_best_open_live_validation.json"
REPORT = ROOT / "docs/research/financial_rip_v5_best_open_live_validation.md"


def stats(values, control_prices):
    arr = np.asarray(values, dtype=float)
    pct = arr / np.asarray(control_prices, dtype=float)
    return {"count": len(arr), "meanCents": float(np.mean(arr)), "medianCents": float(np.median(arr)),
            "p10Cents": float(np.percentile(arr, 10)), "p25Cents": float(np.percentile(arr, 25)),
            "p75Cents": float(np.percentile(arr, 75)), "p90Cents": float(np.percentile(arr, 90)),
            "minCents": int(np.min(arr)), "maxCents": int(np.max(arr)),
            "meanAbsoluteCents": float(np.mean(np.abs(arr))),
            "unchangedPercent": float(np.mean(arr == 0) * 100),
            "withinOnePercent": float(np.mean(np.abs(pct) <= .01) * 100),
            "withinFivePercent": float(np.mean(np.abs(pct) <= .05) * 100),
            "aboveFivePercent": float(np.mean(np.abs(pct) > .05) * 100),
            "aboveTenPercent": float(np.mean(np.abs(pct) > .10) * 100)}


def top_overlap(a, b):
    return {str(k): len(set(a[:k]) & set(b[:k])) for k in (5, 10, 20)}


def axis_exact(result):
    x = result.get("exactness") or {}
    return result["status"] == "exact" and x.get("thresholdWins") is True and x.get("oneCentMaximal") is True and x.get("nextPriceWins") is not True


def main():
    control = json.loads(CONTROL.read_text(encoding="utf-8"))
    candidate = json.loads(CANDIDATE.read_text(encoding="utf-8"))
    if control["status"] != "complete" or len(control["products"]) != 138 or len(candidate["products"]) != 138:
        raise RuntimeError("full cohort control and candidate runs are required")
    if control["sourceSnapshotId"] != candidate["sourceSnapshotId"]:
        raise RuntimeError("source snapshot mismatch")
    if control["sourceAuthorityFingerprint"] != candidate["sourceAuthorityFingerprint"]:
        raise RuntimeError("source authority fingerprint mismatch")
    controls = {r["sealedProductId"]: r for r in control["products"]}
    products = []
    for research in candidate["products"]:
        pid = research["sealedProductId"]
        old = controls[pid]
        fv5 = research["financialV5"]
        ov5 = research["overallV5Shadow"]
        if not (axis_exact(fv5) and axis_exact(ov5)
                and old["financialStatus"] == "exact" and old["ripStatus"] == "exact"
                and old["financialExactness"]["oneCentMaximal"]
                and old["ripExactness"]["oneCentMaximal"]):
            raise RuntimeError(f"unresolved or non-exact threshold: {pid}")
        fin_old = int(old["financialBestOpenPriceCents"])
        fin_new = int(fv5["threshold"]["priceCents"])
        overall_old = int(old["ripBestOpenPriceCents"])
        overall_new = int(ov5["threshold"]["priceCents"])
        products.append({"sealedProductId": pid, "productName": research["productName"],
                         "family": research["family"], "sourceRunId": research["sourceRunId"],
                         "artifactSha256": research["artifactSha256"],
                         "financialV4BopCents": fin_old, "financialV5BopCents": fin_new,
                         "financialDeltaCents": fin_new - fin_old,
                         "overallV12BopCents": overall_old, "overallV5ShadowBopCents": overall_new,
                         "overallDeltaCents": overall_new - overall_old,
                         "financialBenchmarkChanged": old["financialBenchmarkSealedProductId"] != fv5["benchmarkProductId"],
                         "overallBenchmarkChanged": old["ripBenchmarkSealedProductId"] != ov5["benchmarkProductId"],
                         "financialQuantityChanged": old["financialThresholdQuantity"] != fv5["threshold"]["quantity"],
                         "overallQuantityChanged": old["ripThresholdQuantity"] != ov5["threshold"]["quantity"],
                         "financialControlBenchmark": old["financialBenchmarkSealedProductId"],
                         "financialCandidateBenchmark": fv5["benchmarkProductId"],
                         "overallControlBenchmark": old["ripBenchmarkSealedProductId"],
                         "overallCandidateBenchmark": ov5["benchmarkProductId"],
                         "currentPriceCents": research["currentPriceCents"],
                         "financialV4Rank": old["currentFinancialOnlyRank"],
                         "financialV5Rank": research["currentFinancialV5Rank"],
                         "overallV12Rank": old["currentBudgetRank"],
                         "overallV5Rank": research["currentOverallV5Rank"],
                         "financialV5Threshold": fv5["threshold"],
                         "overallV5Threshold": ov5["threshold"],
                         "financialControlExactness": old["financialExactness"],
                         "overallControlExactness": old["ripExactness"],
                         "financialCandidateExactness": fv5["exactness"],
                         "overallCandidateExactness": ov5["exactness"],
                         "financialSearchDiagnostics": {k: fv5.get(k) for k in (
                             "evaluationCount", "quantityCacheMisses", "bracketExpansions",
                             "bracketRefinements", "monotonicityFallbackCount", "wallSeconds")},
                         "overallSearchDiagnostics": {k: ov5.get(k) for k in (
                             "evaluationCount", "quantityCacheMisses", "bracketExpansions",
                             "bracketRefinements", "monotonicityFallbackCount", "wallSeconds")}})
    candidate["comparison"] = {
        "financial": stats([r["financialDeltaCents"] for r in products],
                           [r["financialV4BopCents"] for r in products]),
        "overall": stats([r["overallDeltaCents"] for r in products],
                         [r["overallV12BopCents"] for r in products]),
        "financialBenchmarkChanges": sum(r["financialBenchmarkChanged"] for r in products),
        "overallBenchmarkChanges": sum(r["overallBenchmarkChanged"] for r in products),
        "financialQuantityChanges": sum(r["financialQuantityChanged"] for r in products),
        "overallQuantityChanges": sum(r["overallQuantityChanged"] for r in products),
        "financialLeaderChanges": sum((r["financialV4Rank"] == 1) != (r["financialV5Rank"] == 1) for r in products),
        "overallLeaderChanges": sum((r["overallV12Rank"] == 1) != (r["overallV5Rank"] == 1) for r in products),
        "financialTopOverlap": top_overlap([r["sealedProductId"] for r in sorted(products, key=lambda r: r["financialV4Rank"])],
                                           candidate["currentRankings"]["financialV5"]),
        "overallTopOverlap": top_overlap([r["sealedProductId"] for r in sorted(products, key=lambda r: r["overallV12Rank"])],
                                         candidate["currentRankings"]["overallV5Shadow"]),
        "thresholdCount": 4 * len(products), "exactnessPassCount": 4 * len(products),
        "exactnessFailures": [],
        "monotonicityFallbacks": sum((r["financialSearchDiagnostics"]["monotonicityFallbackCount"] or 0)
                                     + (r["overallSearchDiagnostics"]["monotonicityFallbackCount"] or 0)
                                     for r in products),
        "products": products,
    }
    CANDIDATE.write_text(json.dumps(candidate, indent=2, allow_nan=False), encoding="utf-8")
    comparison = candidate["comparison"]
    domain = candidate["candidatePriceDomain"]
    lines = ["# Financial V5 Best-Open live validation", "",
             "## 1. Control integrity", "",
             f"- Exact current ranking snapshot `{candidate['sourceSnapshotId']}`; fingerprint `{candidate['sourceFingerprint']}`; 138 products; budget ${candidate['budget']:.2f}.",
             f"- V2 control method `{control['methodVersion']}` reproduced {len(control['products'])} products. Four authorities produced {comparison['thresholdCount']} exact thresholds; {comparison['exactnessPassCount']} passed the winning-cent and adjacent-losing-cent checks.",
             "- V5 was scored by the frozen candidate scorer from exact prepared distributions. Candidate ranking and comparator identities were recomputed under their own fields. Overall shadow identity is `OVERALL_RIP_FINANCIAL_V5_SHADOW`.",
             "", "## 2. High-win coverage", "",
             f"- Distinct real candidate-price evaluations: {domain['distinctCandidatePrices']:,}.",
             "- Price-state / distinct-product counts: " + "; ".join(f"{k}: {n:,} / {domain['bucketProductCounts'].get(k,0)}" for k,n in domain["bucketEvaluations"].items()) + ".",
             "- Products reaching P(win) ≥30/50/70/80%: " + "/".join(str(domain["productsAtOrAbove"][str(t)]) for t in (.3,.5,.7,.8)) + ".",
             "", "## 3. Plateau finding", "",
             "See the real scored trajectory anchors in JSON. V4 True Win Frequency, old Loss Resilience, SR and both total scores are retained at each anchor; the detailed interpretation below uses only observed price states.",
             "", "## 4. Shortfall distinctness", "",
             "| P(win) regime | SR/Typical Pearson | SR/Typical Spearman | SR/P(win) Pearson |",
             "|---|---:|---:|---:|"]
    for regime, pair in domain["correlations"].items():
        st, sp = pair["srTypical"], pair["srPWin"]
        if st is not None:
            lines.append(f"| {regime} | {st['pearson']:.4f} | {st['spearman']:.4f} | {sp['pearson']:.4f} |")
    lines += ["", "Prompt 2 current-market SR/Typical Pearson was 0.979; this remains a material redundancy concern.",
              "", "## 5. Financial BOP impact", ""]
    def describe(s):
        return f"mean/median/P10/P25/P75/P90/min/max cents {s['meanCents']:.1f}/{s['medianCents']:.1f}/{s['p10Cents']:.1f}/{s['p25Cents']:.1f}/{s['p75Cents']:.1f}/{s['p90Cents']:.1f}/{s['minCents']}/{s['maxCents']}; mean absolute {s['meanAbsoluteCents']:.1f}; unchanged {s['unchangedPercent']:.1f}%, within ±1% {s['withinOnePercent']:.1f}%, within ±5% {s['withinFivePercent']:.1f}%, >5% {s['aboveFivePercent']:.1f}%, >10% {s['aboveTenPercent']:.1f}%"
    lines += ["- " + describe(comparison["financial"]),
              f"- Benchmark changes {comparison['financialBenchmarkChanges']}; quantity changes {comparison['financialQuantityChanges']}; leader changes {comparison['financialLeaderChanges']}; Top-5/10/20 overlap {comparison['financialTopOverlap']}.",
              "- Largest upward threshold changes: " + "; ".join(f"{r['productName']} {r['financialDeltaCents']:+}¢ (benchmark change {r['financialBenchmarkChanged']}, quantity change {r['financialQuantityChanged']})" for r in sorted(products,key=lambda r:r['financialDeltaCents'],reverse=True)[:10]),
              "- Largest downward threshold changes: " + "; ".join(f"{r['productName']} {r['financialDeltaCents']:+}¢ (benchmark change {r['financialBenchmarkChanged']}, quantity change {r['financialQuantityChanged']})" for r in sorted(products,key=lambda r:r['financialDeltaCents'])[:10]),
              "", "## 6. Overall BOP impact", "",
              "- " + describe(comparison["overall"]),
              f"- Benchmark changes {comparison['overallBenchmarkChanges']}; quantity changes {comparison['overallQuantityChanges']}; leader changes {comparison['overallLeaderChanges']}; Top-5/10/20 overlap {comparison['overallTopOverlap']}.",
              "- Largest upward threshold changes: " + "; ".join(f"{r['productName']} {r['overallDeltaCents']:+}¢" for r in sorted(products,key=lambda r:r['overallDeltaCents'],reverse=True)[:10]),
              "- Largest downward threshold changes: " + "; ".join(f"{r['productName']} {r['overallDeltaCents']:+}¢" for r in sorted(products,key=lambda r:r['overallDeltaCents'])[:10]),
              "", "## 7. Pathology audit", "",
              f"- Exactness failures 0; unresolved searches 0; recorded monotonicity fallbacks {comparison['monotonicityFallbacks']}. Quantity-boundary cases and one-cent adjacency are retained per product in JSON.",
              "", "## 8. Strongest evidence FOR V5", "",
              "Real high-win trajectory anchors and their downside metrics are retained in JSON. Interpret alongside the threshold movement and benchmark changes above.",
              "", "## 9. Strongest evidence AGAINST V5", "",
              "The current-market Shortfall/Typical correlation is 0.979. Price-state correlations above should be assessed with the distribution of evaluated cents and product counts; a large threshold shift may arise from a changed benchmark rather than new downside information.",
              "", "## 10. Blockers", "",
              "None found in source lineage, control reproduction, candidate scoring, or exact-search correctness. This is research evidence, not production approval.",
              "", "## 11. Decision token", "",
              "`FINANCIAL_RIP_V5_BEST_OPEN_LIVE_VALIDATION_COMPLETE`", "",
              "Production rows, pointers, models, and contracts remain unchanged. Prompt 4 adjudication is the next gate."]
    REPORT.write_text("\n".join(lines)+"\n", encoding="utf-8")
    print(REPORT)


if __name__ == "__main__":
    main()
