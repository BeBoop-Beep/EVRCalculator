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
CHECKPOINT = ROOT / "logs/financial_rip_v5_best_open_checkpoint.json"


def trajectory_audit(candidate):
    checkpoint = json.loads(CHECKPOINT.read_text(encoding="utf-8"))
    for key in ("sourceSnapshotId", "sourceFingerprint", "sourceAuthorityFingerprint",
                "candidateVersion", "overallShadowVersion", "searchMethodIdentity"):
        if checkpoint.get(key) != candidate.get(key):
            raise RuntimeError(f"trajectory checkpoint authority mismatch: {key}")
    files = checkpoint["collectorCheckpoint"]["trajectoryFiles"]
    if len(files) != len(candidate["products"]):
        raise RuntimeError("missing per-product candidate-price trajectory")
    summary = {"sameQuantityAdjacentCents": 0, "quantityBoundaryAdjacentCents": 0,
               "sameQuantityV5ScoreInversions": 0,
               "sameQuantityV4ScoreInversions": 0,
               "highWinStates": 0, "highWinProducts": 0,
               "highWinTrueWinSaturatedStates": 0,
               "minimumEvaluatedPriceCents": None,
               "maximumV5Score": None,
               "largestSameQuantityV5Step": None,
               "largestQuantityBoundaryV5Step": None,
               "inversionExamples": []}
    for product, name in zip(candidate["products"], files):
        with np.load(CHECKPOINT.parent / name) as saved:
            columns = {key: np.asarray(saved[key]) for key in (
                "priceCents", "quantity", "pWin", "typical", "loss", "shortfall",
                "trueWin", "v4", "v5", "overallV12", "overallV5", "p50Value",
                "committedCapital")}
        count = len(columns["priceCents"])
        if count:
            minimum_price = int(np.min(columns["priceCents"]))
            maximum_v5 = float(np.max(columns["v5"]))
            summary["minimumEvaluatedPriceCents"] = (
                minimum_price if summary["minimumEvaluatedPriceCents"] is None else
                min(summary["minimumEvaluatedPriceCents"], minimum_price))
            summary["maximumV5Score"] = (
                maximum_v5 if summary["maximumV5Score"] is None else
                max(summary["maximumV5Score"], maximum_v5))
        if count != len(set(columns["priceCents"].astype(int))):
            raise RuntimeError("duplicate candidate price in trajectory")
        if np.any(columns["pWin"] >= .5):
            summary["highWinProducts"] += 1
        summary["highWinStates"] += int(np.count_nonzero(columns["pWin"] >= .5))
        summary["highWinTrueWinSaturatedStates"] += int(np.count_nonzero(
            (columns["pWin"] >= .5) & (columns["trueWin"] >= 99.9999)))
        order = np.argsort(columns["priceCents"])[::-1]
        for key in columns:
            columns[key] = columns[key][order]
        prices = columns["priceCents"].astype(int)
        adjacent = (prices[:-1] - prices[1:]) == 1
        same_q = columns["quantity"][:-1] == columns["quantity"][1:]
        for boundary, label, counter in ((adjacent & same_q, "largestSameQuantityV5Step", "sameQuantityAdjacentCents"),
                                         (adjacent & ~same_q, "largestQuantityBoundaryV5Step", "quantityBoundaryAdjacentCents")):
            indices = np.flatnonzero(boundary)
            summary[counter] += len(indices)
            if len(indices):
                steps = columns["v5"][indices + 1] - columns["v5"][indices]
                chosen = int(indices[np.argmax(np.abs(steps))])
                evidence = {"sealedProductId": product["sealedProductId"],
                            "higherPriceCents": int(prices[chosen]),
                            "lowerPriceCents": int(prices[chosen + 1]),
                            "higherQuantity": int(columns["quantity"][chosen]),
                            "lowerQuantity": int(columns["quantity"][chosen + 1]),
                            "v5ScoreDeltaAtLowerCent": float(
                                columns["v5"][chosen + 1] - columns["v5"][chosen]),
                            "v4ScoreDeltaAtLowerCent": float(
                                columns["v4"][chosen + 1] - columns["v4"][chosen]),
                            "committedCapitalDelta": float(
                                columns["committedCapital"][chosen + 1] -
                                columns["committedCapital"][chosen]),
                            "pWinDelta": float(columns["pWin"][chosen + 1] -
                                               columns["pWin"][chosen]),
                            "typicalDelta": float(columns["typical"][chosen + 1] -
                                                  columns["typical"][chosen]),
                            "shortfallDelta": float(columns["shortfall"][chosen + 1] -
                                                    columns["shortfall"][chosen])}
                if (summary[label] is None or
                        abs(evidence["v5ScoreDeltaAtLowerCent"]) >
                        abs(summary[label]["v5ScoreDeltaAtLowerCent"])):
                    summary[label] = evidence
        same_indices = np.flatnonzero(adjacent & same_q)
        if len(same_indices):
            v5_steps = columns["v5"][same_indices + 1] - columns["v5"][same_indices]
            v4_steps = columns["v4"][same_indices + 1] - columns["v4"][same_indices]
            v5_bad = same_indices[v5_steps < -1e-4]
            summary["sameQuantityV5ScoreInversions"] += len(v5_bad)
            summary["sameQuantityV4ScoreInversions"] += int(np.count_nonzero(v4_steps < -1e-4))
            for i in v5_bad[:3]:
                summary["inversionExamples"].append({
                    "sealedProductId": product["sealedProductId"],
                    "higherPriceCents": int(prices[i]), "lowerPriceCents": int(prices[i + 1]),
                    "higherV5": float(columns["v5"][i]),
                    "lowerV5": float(columns["v5"][i + 1]),
                })
    summary["inversionExamples"] = summary["inversionExamples"][:10]
    return summary


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


def high_win_anchor_pairs(domain):
    pairs = []
    for pid, anchors in domain["trajectoryAnchors"].items():
        states = sorted((row for row in anchors
                         if row["chanceToRecoverCapital"] is not None
                         and row["chanceToRecoverCapital"] >= .5),
                        key=lambda row: row["chanceToRecoverCapital"])
        if len(states) < 2 or states[0]["priceCents"] == states[-1]["priceCents"]:
            continue
        low, high = states[0], states[-1]
        pairs.append({"sealedProductId": pid,
                      "from": low, "to": high,
                      "deltaPriceCents": high["priceCents"] - low["priceCents"],
                      "deltaPWin": high["chanceToRecoverCapital"] - low["chanceToRecoverCapital"],
                      "deltaTypical": high["typicalRetentionScore"] - low["typicalRetentionScore"],
                      "deltaTrueWin": high["trueWinFrequencyScore"] - low["trueWinFrequencyScore"],
                      "deltaLoss": high["lossResilienceScore"] - low["lossResilienceScore"],
                      "deltaShortfall": high["shortfallResilienceScore"] - low["shortfallResilienceScore"],
                      "deltaV4": high["financialRipV4Score"] - low["financialRipV4Score"],
                      "deltaV5": high["financialRipV5CandidateScore"] - low["financialRipV5CandidateScore"]})
    return sorted(pairs, key=lambda row: abs(row["deltaShortfall"]), reverse=True)


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
    if control["sourceFingerprint"] != candidate["sourceFingerprint"]:
        raise RuntimeError("cohort fingerprint mismatch")
    if control["sourceAuthorityFingerprint"] != candidate["sourceAuthorityFingerprint"]:
        raise RuntimeError("source authority fingerprint mismatch")
    controls = {r["sealedProductId"]: r for r in control["products"]}
    control_financial_order = [row["sealedProductId"] for row in sorted(
        control["products"], key=lambda row: row["currentFinancialOnlyRank"])]
    control_overall_order = [row["sealedProductId"] for row in sorted(
        control["products"], key=lambda row: row["currentBudgetRank"])]
    financial_order = candidate["currentRankings"]["financialV5"]
    overall_order = candidate["currentRankings"]["overallV5Shadow"]
    products = []
    for research in candidate["products"]:
        pid = research["sealedProductId"]
        old = controls[pid]
        if (old["financialBenchmarkSealedProductId"] !=
                (control_financial_order[1] if old["currentFinancialOnlyRank"] == 1
                 else control_financial_order[0]) or
                old["ripBenchmarkSealedProductId"] !=
                (control_overall_order[1] if old["currentBudgetRank"] == 1
                 else control_overall_order[0])):
            raise RuntimeError(f"control benchmark authority mismatch: {pid}")
        fv5 = research["financialV5"]
        ov5 = research["overallV5Shadow"]
        expected_financial_benchmark = (financial_order[1] if research["currentFinancialV5Rank"] == 1
                                        else financial_order[0])
        expected_overall_benchmark = (overall_order[1] if research["currentOverallV5Rank"] == 1
                                      else overall_order[0])
        if (fv5["benchmarkProductId"] != expected_financial_benchmark or
                ov5["benchmarkProductId"] != expected_overall_benchmark):
            raise RuntimeError(f"candidate benchmark authority mismatch: {pid}")
        if not (axis_exact(fv5) and axis_exact(ov5)
                and old["financialStatus"] == "exact" and old["ripStatus"] == "exact"
                and old["financialExactness"]["oneCentMaximal"]
                and old["ripExactness"]["oneCentMaximal"]):
            raise RuntimeError(f"unresolved or non-exact threshold: {pid}")
        fin_old = int(old["financialBestOpenPriceCents"])
        fin_new = int(fv5["threshold"]["priceCents"])
        overall_old = int(old["ripBestOpenPriceCents"])
        overall_new = int(ov5["threshold"]["priceCents"])
        current_cents = int(research["currentPriceCents"])
        products.append({"sealedProductId": pid, "productName": research["productName"],
                         "family": research["family"], "sourceRunId": research["sourceRunId"],
                         "artifactSha256": research["artifactSha256"],
                         "financialV4BopCents": fin_old, "financialV5BopCents": fin_new,
                         "financialDeltaCents": fin_new - fin_old,
                         "financialV5PriceGapDollars": (fin_new - current_cents) / 100,
                         "financialV5PriceGapPercent":
                             (fin_new - current_cents) / current_cents * 100,
                         "overallV12BopCents": overall_old, "overallV5ShadowBopCents": overall_new,
                         "overallDeltaCents": overall_new - overall_old,
                         "overallV5PriceGapDollars": (overall_new - current_cents) / 100,
                         "overallV5PriceGapPercent":
                             (overall_new - current_cents) / current_cents * 100,
                         "financialBenchmarkChanged": old["financialBenchmarkSealedProductId"] != fv5["benchmarkProductId"],
                         "overallBenchmarkChanged": old["ripBenchmarkSealedProductId"] != ov5["benchmarkProductId"],
                         "financialQuantityChanged": old["financialThresholdQuantity"] != fv5["threshold"]["quantity"],
                         "overallQuantityChanged": old["ripThresholdQuantity"] != ov5["threshold"]["quantity"],
                         "financialModelScoreDeltaAtCandidateThreshold":
                             fv5["threshold"]["financialRipV5CandidateScore"] - fv5["threshold"]["financialRipV4Score"],
                         "overallModelScoreDeltaAtCandidateThreshold":
                             ov5["threshold"]["overallRipFinancialV5ShadowScore"] - ov5["threshold"]["overallRipV12Score"],
                         "overallThresholdFinancialModelScoreDelta":
                             ov5["threshold"]["financialRipV5CandidateScore"] - ov5["threshold"]["financialRipV4Score"],
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
    for row in products:
        for axis in ("financial", "overall"):
            benchmark = row[f"{axis}BenchmarkChanged"]
            quantity = row[f"{axis}QuantityChanged"]
            leader = ((row["financialV4Rank"] == 1) != (row["financialV5Rank"] == 1)
                      if axis == "financial" else
                      (row["overallV12Rank"] == 1) != (row["overallV5Rank"] == 1))
            row[f"{axis}LeaderChanged"] = leader
            row[f"{axis}ObservedMechanisms"] = (
                ["candidate_score_change"]
                + (["benchmark_change"] if benchmark else [])
                + (["threshold_quantity_change"] if quantity else [])
                + (["leader_domain_change"] if leader else [])
            )
            row[f"{axis}CauseClassification"] = (
                "score_benchmark_quantity_leader_interaction" if leader and benchmark and quantity else
                "score_benchmark_leader_interaction" if leader and benchmark else
                "score_quantity_leader_interaction" if leader and quantity else
                "score_leader_domain_change" if leader else
                "score_benchmark_quantity_interaction" if benchmark and quantity else
                "score_and_benchmark" if benchmark else
                "score_and_quantity_boundary" if quantity else
                "score_substitution_same_benchmark_quantity"
            )
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
        "financialMaterialOverallNotMaterialCount": sum(
            abs(r["financialDeltaCents"]) > .05 * r["financialV4BopCents"] and
            abs(r["overallDeltaCents"]) <= .05 * r["overallV12BopCents"]
            for r in products),
        "financialAndOverallMaterialCount": sum(
            abs(r["financialDeltaCents"]) > .05 * r["financialV4BopCents"] and
            abs(r["overallDeltaCents"]) > .05 * r["overallV12BopCents"]
            for r in products),
        "maximumOverallBlendResidualAtCandidateThreshold": max(abs(
            r["overallModelScoreDeltaAtCandidateThreshold"] -
            .86 * r["overallThresholdFinancialModelScoreDelta"])
            for r in products),
        "thresholdCount": 4 * len(products), "exactnessPassCount": 4 * len(products),
        "benchmarkAuthorityPassCount": 4 * len(products),
        "exactnessFailures": [],
        "monotonicityFallbacks": sum((r["financialSearchDiagnostics"]["monotonicityFallbackCount"] or 0)
                                     + (r["overallSearchDiagnostics"]["monotonicityFallbackCount"] or 0)
                                     for r in products),
        "products": products,
    }
    if candidate["comparison"]["maximumOverallBlendResidualAtCandidateThreshold"] > .00011:
        raise RuntimeError("Overall V5 shadow differs from the fixed 86% Financial substitution")
    candidate["trajectoryAudit"] = trajectory_audit(candidate)
    candidate["plateauEvidence"] = high_win_anchor_pairs(candidate["candidatePriceDomain"])
    CANDIDATE.write_text(json.dumps(candidate, indent=2, allow_nan=False), encoding="utf-8")
    comparison = candidate["comparison"]
    domain = candidate["candidatePriceDomain"]
    audit = candidate["trajectoryAudit"]
    pair = candidate["plateauEvidence"][0] if candidate["plateauEvidence"] else None
    largest_financial_shift = max(products, key=lambda row: abs(row["financialDeltaCents"]))
    lines = ["# Financial V5 Best-Open live validation", "",
             "## 1. Control integrity", "",
             f"- Exact current ranking snapshot `{candidate['sourceSnapshotId']}`; fingerprint `{candidate['sourceFingerprint']}`; 138 products; budget ${candidate['budget']:.2f}.",
             f"- V2 control method `{control['methodVersion']}` reproduced {len(control['products'])} products. Four authorities produced {comparison['thresholdCount']} exact thresholds; {comparison['exactnessPassCount']} passed the winning-cent and adjacent-losing-cent checks.",
             f"- All {comparison['benchmarkAuthorityPassCount']} axis comparisons used the benchmark selected under their own current V4, V5, V12, or Overall-V5 ranking authority.",
             "- V5 was scored by the frozen candidate scorer from exact prepared distributions. Candidate ranking and comparator identities were recomputed under their own fields. Overall shadow identity is `OVERALL_RIP_FINANCIAL_V5_SHADOW`.",
             "", "## 2. High-win coverage", "",
             f"- Distinct real candidate-price evaluations: {domain['distinctCandidatePrices']:,}.",
             "- Price-state / distinct-product counts: " + "; ".join(f"{k}: {n:,} / {domain['bucketProductCounts'].get(k,0)}" for k,n in domain["bucketEvaluations"].items()) + ".",
             "- Products reaching P(win) ≥30/50/70/80%: " + "/".join(str(domain["productsAtOrAbove"][str(t)]) for t in (.3,.5,.7,.8)) + ".",
             "- Product IDs crossing 30/50/70/80% are listed in `candidatePriceDomain.productIdsAtOrAbove` in the JSON evidence.",
             "", "## 3. Plateau finding", "",
             ("No evaluated candidate-price state reached P(win) >=50%; the proposed V4 high-win plateau could not be tested in the exact Best-Open domain."
              if audit["highWinStates"] == 0 else
              f"{audit['highWinStates']:,} states across {audit['highWinProducts']} products reached P(win) >=50%. The strongest observed anchor pairs and full delta chain are retained in `plateauEvidence`; {len(candidate['plateauEvidence'])} products have two distinct high-win anchors."),
             ("No two distinct high-win anchors are available for a price-to-score delta chain."
              if pair is None else
              f"Example `{pair['sealedProductId']}`: price {pair['from']['priceCents']} to {pair['to']['priceCents']} cents; quantity {pair['from']['quantity']} to {pair['to']['quantity']}; P(win) {pair['from']['chanceToRecoverCapital']:.4f} to {pair['to']['chanceToRecoverCapital']:.4f}; Typical {pair['deltaTypical']:+.4f}; old Loss {pair['deltaLoss']:+.4f}; Shortfall {pair['deltaShortfall']:+.4f}; V4 {pair['deltaV4']:+.4f}; V5 {pair['deltaV5']:+.4f}."),
             "", "## 4. Shortfall distinctness", "",
             "| P(win) regime | States | SR/Typical Pearson | Spearman | SR/P(win) Pearson | Spearman | SR/BEE Pearson | Spearman |",
             "|---|---:|---:|---:|---:|---:|---:|---:|"]
    for regime, pair in domain["correlations"].items():
        st, sp, sb = pair["srTypical"], pair["srPWin"], pair["srBEE"]
        values = [f"{block[metric]:.4f}" if block is not None else "n/a"
                  for block, metric in ((st, "pearson"), (st, "spearman"),
                                        (sp, "pearson"), (sp, "spearman"),
                                        (sb, "pearson"), (sb, "spearman"))]
        lines.append(f"| {regime} | {domain['correlationSampleCounts'][regime]:,} | "
                     + " | ".join(values) + " |")
    lines += ["", "Prompt 2 current-market SR/Typical Pearson was 0.979; this remains a material redundancy concern.",
              f"Across all {domain['distinctCandidatePrices']:,} real scored price states, SR/Typical Pearson is {domain['correlations']['all']['srTypical']['pearson']:.4f}. The 20–50% slice contains {domain['correlationSampleCounts']['0.20-0.50']} states from {domain['bucketProductCounts'].get('0.20-0.30', 0) + domain['bucketProductCounts'].get('0.30-0.50', 0)} observed product-band entries; it cannot establish cross-product distinctness.",
              ("No >=50% candidate-price states were observed, so there is no real high-win correlation or Type A-D counterexample to establish distinctness."
               if audit["highWinStates"] == 0 else
               "High-win correlation and real anchor pairs must be read alongside sample counts; correlation alone does not establish distinct economic information."),
              "", "## 5. Financial BOP impact", ""]
    def describe(s):
        return f"mean/median/P10/P25/P75/P90/min/max cents {s['meanCents']:.1f}/{s['medianCents']:.1f}/{s['p10Cents']:.1f}/{s['p25Cents']:.1f}/{s['p75Cents']:.1f}/{s['p90Cents']:.1f}/{s['minCents']}/{s['maxCents']}; mean absolute {s['meanAbsoluteCents']:.1f}; unchanged {s['unchangedPercent']:.1f}%, within ±1% {s['withinOnePercent']:.1f}%, within ±5% {s['withinFivePercent']:.1f}%, >5% {s['aboveFivePercent']:.1f}%, >10% {s['aboveTenPercent']:.1f}%"
    def movement(axis, reverse):
        key = f"{axis}DeltaCents"
        selected = sorted(products, key=lambda row: row[key], reverse=reverse)[:10]
        return "; ".join(
            f"{row['productName']} {row[key]:+} cents "
            f"({row[f'{axis}CauseClassification']}, "
            f"local model score delta {row[f'{axis}ModelScoreDeltaAtCandidateThreshold']:+.4f})"
            for row in selected)
    lines += ["- " + describe(comparison["financial"]),
              f"- Benchmark changes {comparison['financialBenchmarkChanges']}; quantity changes {comparison['financialQuantityChanges']}; leader changes {comparison['financialLeaderChanges']}; Top-5/10/20 overlap {comparison['financialTopOverlap']}.",
              "- Largest upward threshold changes: " + movement("financial", True),
              "- Largest downward threshold changes: " + movement("financial", False),
              "", "## 6. Overall BOP impact", "",
              "- " + describe(comparison["overall"]),
              f"- Benchmark changes {comparison['overallBenchmarkChanges']}; quantity changes {comparison['overallQuantityChanges']}; leader changes {comparison['overallLeaderChanges']}; Top-5/10/20 overlap {comparison['overallTopOverlap']}.",
              f"- Financial shifts >5% with Overall shifts <=5%: {comparison['financialMaterialOverallNotMaterialCount']}; shifts >5% in both: {comparison['financialAndOverallMaterialCount']}. Maximum local residual from the fixed 86% Financial propagation: {comparison['maximumOverallBlendResidualAtCandidateThreshold']:.6f} score points (rounding included).",
              "- Largest upward threshold changes: " + movement("overall", True),
              "- Largest downward threshold changes: " + movement("overall", False),
             "", "## 7. Pathology audit", "",
             f"- Exactness failures 0; unresolved searches 0; recorded monotonicity fallbacks {comparison['monotonicityFallbacks']}. Quantity-boundary cases and one-cent adjacency are retained per product in JSON.",
             f"- Across {audit['sameQuantityAdjacentCents']:,} adjacent cents with unchanged quantity, V5 score inversions: {audit['sameQuantityV5ScoreInversions']:,}; V4 score inversions: {audit['sameQuantityV4ScoreInversions']:,}. Adjacent quantity boundaries: {audit['quantityBoundaryAdjacentCents']:,}.",
             f"- Largest same-quantity one-cent V5 score step: {audit['largestSameQuantityV5Step']}; largest quantity-boundary step: {audit['largestQuantityBoundaryV5Step']}.",
             f"- At the largest boundary step, the allocation changes from {audit['largestQuantityBoundaryV5Step']['higherQuantity']} to {audit['largestQuantityBoundaryV5Step']['lowerQuantity']} packs. Committed capital changes {audit['largestQuantityBoundaryV5Step']['committedCapitalDelta']:+.2f}, P(win) changes {audit['largestQuantityBoundaryV5Step']['pWinDelta']:+.4f}, V4 changes {audit['largestQuantityBoundaryV5Step']['v4ScoreDeltaAtLowerCent']:+.4f}, and V5 changes {audit['largestQuantityBoundaryV5Step']['v5ScoreDeltaAtLowerCent']:+.4f}. This is an observed allocation boundary, not a same-quantity one-cent price effect.",
             f"- Lowest evaluated candidate price: {audit['minimumEvaluatedPriceCents']} cents; maximum observed V5 Financial score: {audit['maximumV5Score']}. These are observed search states, not an extrapolation below the exact search domain.",
              "", "## 8. Strongest evidence FOR V5", "",
              ("No evaluated price state entered P(win) >=50%; this study supplies no real high-win example that establishes distinct Shortfall Resilience information."
               if audit["highWinStates"] == 0 else
               f"The strongest observed high-win anchor pair is `{pair['sealedProductId']}` with SR change {pair['deltaShortfall']:+.4f}, old Loss change {pair['deltaLoss']:+.4f}, and V5/V4 score changes {pair['deltaV5']:+.4f}/{pair['deltaV4']:+.4f}." if pair is not None else
               "High-win states occurred, but no two distinct high-win anchors support a trajectory comparison."),
              "", "## 9. Strongest evidence AGAINST V5", "",
              f"The current-market Shortfall/Typical correlation is 0.979. The largest absolute Financial threshold shift is {largest_financial_shift['productName']} at {largest_financial_shift['financialDeltaCents']:+} cents; observed mechanisms: {largest_financial_shift['financialObservedMechanisms']}. Price-state correlations above should be assessed with sample counts; benchmark changes can move thresholds independently of within-product downside improvement.",
              "", "## 10. Blockers", "",
              ("No source-lineage, control-reproduction, candidate-implementation, or exact-search correctness blocker. The real Best-Open domain did not reach high P(win), which limits the economic interpretation of the proposed high-win correction. This is research evidence, not production approval."
               if audit["highWinStates"] == 0 else
               "No source-lineage, control-reproduction, candidate-implementation, or exact-search correctness blocker. This is research evidence, not production approval."),
              "", "## 11. Decision token", "",
              "`FINANCIAL_RIP_V5_BEST_OPEN_LIVE_VALIDATION_COMPLETE`", "",
              "Production rows, pointers, models, and contracts remain unchanged. Prompt 4 adjudication is the next gate."]
    REPORT.write_text("\n".join(lines)+"\n", encoding="utf-8")
    print(REPORT)


if __name__ == "__main__":
    main()
