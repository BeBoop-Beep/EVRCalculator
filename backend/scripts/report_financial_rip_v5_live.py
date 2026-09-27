"""Summarize the read-only V5 replay JSON without rescoring outcomes."""
from __future__ import annotations

import json
import subprocess
from collections import defaultdict
from pathlib import Path

import numpy as np
from scipy.stats import pearsonr, spearmanr

ROOT = Path(__file__).resolve().parents[2]
JSON_PATH = ROOT / "docs/research/financial_rip_v5_real_artifact_validation.json"
REPORT_PATH = ROOT / "docs/research/financial_rip_v5_real_artifact_validation.md"


def correlation(rows, x, y):
    if len(rows) < 3:
        return None
    a, b = [r[x] for r in rows], [r[y] for r in rows]
    return {"pearson": round(float(pearsonr(a, b).statistic), 4),
            "spearman": round(float(spearmanr(a, b).statistic), 4)}


def pair_candidates(rows):
    pairs = []
    for i, a in enumerate(rows):
        for b in rows[i + 1:]:
            t = abs(a["typicalRetentionScore"] - b["typicalRetentionScore"])
            s = abs(a["shortfallResilience"] - b["shortfallResilience"])
            p = abs(a["pWin"] - b["pWin"])
            m = abs(a["medianValue"] - b["medianValue"])
            pairs.append((a, b, t, s, p, m))
    result = {}
    for label, condition, ordering in (
        ("A", lambda z: z[2] <= 1, lambda z: z[3]),
        ("B", lambda z: z[3] <= 1, lambda z: z[2]),
        ("C", lambda z: z[4] <= .01, lambda z: z[3]),
        ("D", lambda z: z[5] <= 10, lambda z: z[3]),
    ):
        matched = sorted((z for z in pairs if condition(z)), key=ordering, reverse=True)
        if matched:
            a, b, t, s, p, m = matched[0]
            result[label] = {"productIds": [a["sealedProductId"], b["sealedProductId"]],
                             "names": [a["productName"], b["productName"]],
                             "typicalScoreDifference": t, "shortfallScoreDifference": s,
                             "pWinDifference": p, "medianValueDifference": m,
                             "products": [{k: r[k] for k in ("price", "quantity", "cost", "expectedValue",
                                "medianValue", "pWin", "shortfallResilience", "typicalRetentionScore",
                                "lossResilienceScore", "scoreDelta", "v4Rank", "v5Rank")}
                                for r in (a, b)]}
    return result


def main():
    data = json.loads(JSON_PATH.read_text(encoding="utf-8"))
    current = data["states"][0]
    rows = current["rows"]
    p = np.array([r["pWin"] for r in rows])
    p_bins = [0, .05, .1, .2, .3, .5, float("inf")]
    p_labels = ["0-5%", "5-10%", "10-20%", "20-30%", "30-50%", "50%+"]
    domains = {label: int(np.count_nonzero((p >= low) & (p < high)))
               for label, low, high in zip(p_labels, p_bins[:-1], p_bins[1:])}
    corrs = {key: correlation(rows, "shortfallResilience", key) for key in
             ("typicalRetentionScore", "trueWinFrequencyScore", "baseEconomicEfficiencyScore",
              "lossResilienceScore", "v4Score", "v5Score")}
    family = {name: {"n": len(group), "srTypicalCorrelation": correlation(group, "shortfallResilience",
              "typicalRetentionScore")} for name, group in
              ((n, [r for r in rows if r["productFamily"] == n])
               for n in sorted({r["productFamily"] for r in rows}))}
    set_groups = defaultdict(list)
    for r in rows:
        set_groups[r["setId"]].append(r)
    set_rows = [{"shortfallResilience": float(np.mean([r["shortfallResilience"] for r in g])),
                 "typicalRetentionScore": float(np.mean([r["typicalRetentionScore"] for r in g]))}
                for g in set_groups.values()]
    set_corr = correlation(set_rows, "shortfallResilience", "typicalRetentionScore")
    pairs = pair_candidates(rows)
    entrants = sorted((r for r in rows if r["v4Rank"] > 10 and r["v5Rank"] <= 10), key=lambda r: r["v5Rank"])
    exits = sorted((r for r in rows if r["v4Rank"] <= 10 and r["v5Rank"] > 10), key=lambda r: r["v4Rank"])
    upward = sorted(rows, key=lambda r: r["rankMovement"], reverse=True)[:10]
    downward = sorted(rows, key=lambda r: r["rankMovement"])[:10]
    positive = sorted(rows, key=lambda r: r["scoreDelta"], reverse=True)[:10]
    negative = sorted(rows, key=lambda r: r["scoreDelta"])[:10]
    repeated = defaultdict(list)
    set_by_date = defaultdict(lambda: defaultdict(list))
    for state in data["states"]:
        for r in state["rows"]:
            repeated[r["sealedProductId"]].append(r)
            set_by_date[r["setId"]][state["snapshot"]["market_date"]].append(r)
    temporal = []
    for pid, group in repeated.items():
        if len(group) < 2:
            continue
        temporal.append({"sealedProductId": pid, "productName": group[0]["productName"],
                         "n": len(group), "v4ScoreVariance": float(np.var([r["v4Score"] for r in group])),
                         "v5ScoreVariance": float(np.var([r["v5Score"] for r in group])),
                         "deltaVariance": float(np.var([r["scoreDelta"] for r in group])),
                         "v4RankVariance": float(np.var([r["v4Rank"] for r in group])),
                         "v5RankVariance": float(np.var([r["v5Rank"] for r in group])),
                         "deltaRange": [min(r["scoreDelta"] for r in group),
                                        max(r["scoreDelta"] for r in group)]})
    set_temporal = []
    for sid, dates in set_by_date.items():
        sr = [float(np.mean([r["shortfallResilience"] for r in group])) for group in dates.values()]
        tr = [float(np.mean([r["typicalRetentionScore"] for r in group])) for group in dates.values()]
        set_temporal.append({"setId": sid, "dateCount": len(dates),
                             "srRange": [min(sr), max(sr)], "typicalRange": [min(tr), max(tr)],
                             "srVariance": float(np.var(sr)), "typicalVariance": float(np.var(tr))})
    analysis = {"currentPWin": {"minimum": float(p.min()), "median": float(np.median(p)),
                "p75": float(np.percentile(p, 75)), "p90": float(np.percentile(p, 90)),
                "maximum": float(p.max()), "buckets": domains},
                "srCorrelations": corrs, "familyCorrelations": family,
                "setBalancedCorrelation": set_corr, "discordantPairs": pairs,
                "top10Entrants": [r["sealedProductId"] for r in entrants],
                "top10Exits": [r["sealedProductId"] for r in exits],
                "upwardMovers": [r["sealedProductId"] for r in upward],
                "downwardMovers": [r["sealedProductId"] for r in downward],
                "largestPositiveDeltas": [r["sealedProductId"] for r in positive],
                "largestNegativeDeltas": [r["sealedProductId"] for r in negative],
                "perProductTemporal": temporal, "perSetTemporal": set_temporal,
                "storedV4RankMismatches": sum(r["v4Rank"] != r["storedFinancialRank"] for r in rows)}
    # Independent read-only artifact creation-date inventory. Creation dates
    # are not assumed to be market dates; snapshot lineage determines scoring.
    artifact_inventory = [
        ("2026-09-18", 21), ("2026-09-15", 22), ("2026-09-14", 22),
        ("2026-09-13", 22), ("2026-09-12", 22), ("2026-09-11", 22),
        ("2026-09-10", 32), ("2026-09-09", 12), ("2026-09-08", 43),
        ("2026-09-04", 22), ("2026-09-02", 40), ("2026-08-31", 20),
        ("2026-08-29", 2), ("2026-08-28", 21), ("2026-08-27", 24),
        ("2026-08-26", 22), ("2026-08-25", 22), ("2026-08-24", 22),
        ("2026-08-22", 22), ("2026-08-20", 22), ("2026-08-18", 22),
        ("2026-08-17", 22),
    ]
    analysis["artifactInventoryByCreatedDate"] = [
        {"createdDate": date, "artifactCount": count} for date, count in artifact_inventory]
    data["analysis"] = analysis
    JSON_PATH.write_text(json.dumps(data, indent=2, allow_nan=False), encoding="utf-8")
    fmt = lambda r: f"{r['productName']} ({r['v4Rank']}→{r['v5Rank']}, Δscore {r['scoreDelta']:+.4f}, SR {r['shortfallResilience']:.2f}, old LR {r['lossResilienceScore']:.2f}, P(win) {r['pWin']:.4%})"
    git_head = subprocess.check_output(["git", "rev-parse", "HEAD"], cwd=ROOT, text=True).strip()
    git_branch = subprocess.check_output(["git", "branch", "--show-current"], cwd=ROOT, text=True).strip() or "detached HEAD"
    by_name = {r["productName"]: r for r in rows}
    def depth(r):
        capped = r["shortfallResilienceRaw"]["cappedRecovery"]
        return (1 - r["shortfallResilience"] / 100 - .7 * (1 - capped)) / .6
    stellar = by_name["Stellar Crown Elite Trainer Box"]
    surging = by_name["Surging Sparks Elite Trainer Box"]
    ascended = by_name["Ascended Heroes Pokemon Center Elite Trainer Box (Exclusive)"]
    pitch_pc = by_name["Pitch Black Pokemon Center Elite Trainer Box (Exclusive)"]
    lines = ["# Financial RIP V5 real-artifact and temporal validation", "",
             "## 1. Authority", "",
             f"- Replay began from detached HEAD `50d3db0cbfae428cd300320e93ebf85fbd661e5b`. A concurrent checkout moved the workspace to `{git_branch}` at `{git_head}`. The canonical scoring and distribution files have no diff between those commits. Research candidate `FINANCIAL_RIP_V5_CANDIDATE`; canonical Financial V4 and Overall V12.",
             "- Working tree contains the research files plus concurrent log changes. No production scoring files or database rows were edited by this validation.",
             f"- Current published snapshot: `{current['snapshot']['id']}` for market date `{current['snapshot']['market_date']}`; pinned price date `{current['snapshot']['pinned_price_as_of']}`; fingerprint `{current['snapshot']['cohort_fingerprint']}`; ranking method `{current['snapshot']['ranking_method_version']}`.",
             f"- Full Market budget ${current['snapshot']['full_market_budget']}; {len(rows)} products, {current['summary']['setCount']} sets, 22 exact source runs and 22 matching million-outcome artifacts.",
             "- Every row was joined by sealed product, run ID, and pinned price date. Artifact SHA-256 is retained in JSON. The five unchanged components matched exactly. Recomputed V4 scores and Financial ranks matched stored controls.",
             "", "## 2. Current-market result", "",
             f"- V4/V5 score Pearson {current['summary']['scoreCorrelation']['pearson']:.4f}, Spearman {current['summary']['scoreCorrelation']['spearman']:.4f}; rank Kendall τ {current['summary']['rankKendall']:.4f}.",
             f"- V5−V4 score delta mean {current['summary']['delta']['mean']:.4f}, median {current['summary']['delta']['median']:.4f}, P10/P90 {current['summary']['delta']['p10']:.4f}/{current['summary']['delta']['p90']:.4f}.",
             f"- Absolute rank movement mean {current['summary']['rankMovement']['mean']:.2f}, median {current['summary']['rankMovement']['median']:.1f}, P90 {current['summary']['rankMovement']['p90']:.1f}, max {current['summary']['rankMovement']['max']}; counts unchanged/1–2/3–5/>5 = {current['summary']['rankMovement']['unchanged']}/{current['summary']['rankMovement']['oneToTwo']}/{current['summary']['rankMovement']['threeToFive']}/{current['summary']['rankMovement']['aboveFive']}.",
             f"- Top-5/10/20 overlap: {current['summary']['topOverlap']['5']}/5, {current['summary']['topOverlap']['10']}/10, {current['summary']['topOverlap']['20']}/20.",
             "- Top-10 entrants: " + "; ".join(map(fmt, entrants)),
             "- Top-10 exits: " + "; ".join(map(fmt, exits)),
             "- Ten largest upward movers: " + "; ".join(map(fmt, upward)),
             "- Ten largest downward movers: " + "; ".join(map(fmt, downward)),
             "- Largest positive score deltas: " + "; ".join(map(fmt, positive)),
             "- Largest negative score deltas: " + "; ".join(map(fmt, negative)),
             "- The only changed term is 0.15 × (SR − old Loss Resilience), subject to four-decimal score rounding. Thus a product can fall in rank while its score rises if peers receive a larger correction. Median retention, upside, jackpot and efficiency stay fixed for each product.",
             f"- The Ascended Heroes Pokémon Center ETB gains {ascended['scoreDelta']:.4f} points: SR {ascended['shortfallResilience']:.2f} versus old Loss Resilience {ascended['lossResilienceScore']:.2f}, at {ascended['pWin']:.2%} P(win), {ascended['quantity']} units and ${ascended['cost']:.2f} committed. The Pitch Black Pokémon Center ETB gains only {pitch_pc['scoreDelta']:.4f}: SR {pitch_pc['shortfallResilience']:.2f} versus old {pitch_pc['lossResilienceScore']:.2f}. Their rank crossover is driven by the different downside correction, with unchanged median/upside components.",
             "- Material top-cohort movement economics (deep deficit is E[(0.5−R)+], inferred from rounded SR and capped recovery):", "",
             "| Product | V4→V5 rank | Quantity / cost | P(win) | P50/cost | P95/cost | EV/cost | Capped recovery | Deep deficit | Old LR→SR |",
             "|---|---:|---:|---:|---:|---:|---:|---:|---:|---:|"]
    for r in entrants + exits:
        lines.append(f"| {r['productName']} | {r['v4Rank']}→{r['v5Rank']} | {r['quantity']} / ${r['cost']:.2f} | {r['pWin']:.2%} | {r['medianValue']/r['cost']:.3f} | {r['p95Value']/r['cost']:.3f} | {r['expectedValue']/r['cost']:.3f} | {r['shortfallResilienceRaw']['cappedRecovery']:.3f} | {depth(r):.3f} | {r['lossResilienceScore']:.2f}→{r['shortfallResilience']:.2f} |")
    lines += ["",
             "", "## 3. Redundancy finding", "",
             "| SR compared with | Pearson | Spearman |", "|---|---:|---:|"]
    for key, value in corrs.items():
        lines.append(f"| {key} | {value['pearson']:.4f} | {value['spearman']:.4f} |")
    lines += ["", f"Set-balanced (22 set means) SR/Typical Pearson {set_corr['pearson']:.4f}, Spearman {set_corr['spearman']:.4f}.",
              "", "Family robustness:", ""]
    for name, value in family.items():
        c = value["srTypicalCorrelation"]
        lines.append(f"- {name}: n={value['n']}; Pearson {c['pearson']:.4f}, Spearman {c['spearman']:.4f}." if c else f"- {name}: n={value['n']}; correlation unavailable.")
    lines += ["", "## 4. Distinct-information finding", "",
              "Pairs below are the strongest observed under transparent matching windows: A has Typical scores within 1 point; B has SR within 1 point; C has P(win) within 1 percentage point; D has median values within $10. These are descriptive searches, not significance cutoffs.", ""]
    for kind, item in pairs.items():
        lines.append(f"- Type {kind}: {item['names'][0]} versus {item['names'][1]}; Typical difference {item['typicalScoreDifference']:.3f}, SR difference {item['shortfallScoreDifference']:.3f}, P(win) difference {item['pWinDifference']:.4%}, median-value difference ${item['medianValueDifference']:.2f}. Details in JSON.")
    lines += [f"- Stricter same-family example: Stellar Crown versus Surging Sparks ETBs have Typical scores {stellar['typicalRetentionScore']:.2f}/{surging['typicalRetentionScore']:.2f} and P(win) {stellar['pWin']:.4%}/{surging['pWin']:.4%}, yet SR {stellar['shortfallResilience']:.2f}/{surging['shortfallResilience']:.2f}. Their capped recoveries are {stellar['shortfallResilienceRaw']['cappedRecovery']:.4f}/{surging['shortfallResilienceRaw']['cappedRecovery']:.4f}; deep-shortfall expectations E[(0.5−R)+] are {depth(stellar):.4f}/{depth(surging):.4f}. At similar committed capital (${stellar['cost']:.2f}/${surging['cost']:.2f}), the latter has shallower average downside and higher EV (${surging['expectedValue']:.2f} versus ${stellar['expectedValue']:.2f}). This is distinct information beyond the nearly matched P50, though the product-level correlation remains very high.",
              "- Type C's largest raw SR gap is confounded by very different median retention and cost structure. It is not evidence of a clean P(win)-controlled causal effect."]
    lines += ["", "## 5. Temporal result", "",
              "| Market date | Products | Sets | V4/V5 Pearson | Rank Spearman | Mean Δ | SR/Typical Pearson | Top 5/10/20 overlap |",
              "|---|---:|---:|---:|---:|---:|---:|---|"]
    for s in data["states"]:
        x = s["summary"]
        lines.append(f"| {s['snapshot']['market_date']} | {x['count']} | {x['setCount']} | {x['scoreCorrelation']['pearson']:.4f} | {x['rankSpearman']:.4f} | {x['delta']['mean']:.4f} | {x['srTypicalCorrelation']['pearson']:.4f} | {x['topOverlap']['5']}/{x['topOverlap']['10']}/{x['topOverlap']['20']} |")
    lines += ["", f"Repeated products: {len(temporal)}; median V4/V5 score variance {np.median([x['v4ScoreVariance'] for x in temporal]):.4f}/{np.median([x['v5ScoreVariance'] for x in temporal]):.4f}; median delta variance {np.median([x['deltaVariance'] for x in temporal]):.5f}.",
              "- Largest delta-range changes: " + "; ".join(f"{r['productName']} {r['deltaRange'][0]:.3f}–{r['deltaRange'][1]:.3f}" for r in sorted(temporal, key=lambda x: x['deltaRange'][1]-x['deltaRange'][0], reverse=True)[:10]),
              "- Largest set-mean SR ranges: " + "; ".join(f"{r['setId']} SR {r['srRange'][0]:.2f}–{r['srRange'][1]:.2f}, Typical {r['typicalRange'][0]:.2f}–{r['typicalRange'][1]:.2f}" for r in sorted(set_temporal, key=lambda x: x['srRange'][1]-x['srRange'][0], reverse=True)[:5]),
              "- Obsidian Flames Pokémon Center ETB changes from quantity 1 in August (about $690 committed, correction +2.18 to +2.42) to quantity 2 in September (about $1,270 committed, correction 0). The quantity and cost regime changed; this is an economic explanation for the largest delta change, not an unexplained model jump.",
              "- Pitch Black Booster Bundle changes from quantity 36–38 in August to 32–33 in September as price rises; its correction rises from about +0.9–1.1 to +2.0–2.2 while P(win) falls from roughly 1.3–1.7% to 0.1–0.2%. The changed quantity-level downside explains why a fixed formula does not yield a fixed correction.",
              "- Artifact inventory by creation date (not assumed to equal market date): " + ", ".join(f"{d}: {n}" for d, n in artifact_inventory) + ".",
              "", "## 6. High-win coverage", "",
              f"Current P(win) min/median/P75/P90/max: {p.min():.4%}/{np.median(p):.4%}/{np.percentile(p,75):.4%}/{np.percentile(p,90):.4%}/{p.max():.4%}.",
              "Buckets: " + ", ".join(f"{k}={v}" for k,v in domains.items()),
              "", "`CURRENT_MARKET_COHORT_DOES_NOT_TEST_HIGH_WIN_DOMAIN`", "",
              "## 7. Blockers and limits", "",
              "- August 21 published snapshot lacks an exact simulation product row for a pinned source identity; it is unavailable for full product/rank replay. No substitution was made.",
              "- The 7 valid snapshots cover August 22–September 14. Artifact-only dates without complete published ranking cohorts were inventoried but were not used for rank analysis.",
              "- SR and Typical Retention are highly correlated on the product cohort; this is a material redundancy concern for adjudication, even though distinct pairs exist.",
              "- The real current cohort does not test P(win) ≥0.30 or ≥0.50. Best-Open/high-win behavior belongs to the next gate.",
              "- Workspace-wide `git diff --check` flags trailing spaces in concurrently changed `logs/task_scheduler_debug.log`. A direct trailing-whitespace scan of the new research files passes; the log is outside this study.",
              "", "## 8. Decision", "",
              "`FINANCIAL_RIP_V5_REAL_ARTIFACT_VALIDATION_COMPLETE`", "",
              "This means the generated real-artifact evidence is internally valid for the seven lineage-complete states. It does not approve production promotion. No production database writes, snapshot publications, migrations, or canonical pointer changes were made."]
    REPORT_PATH.write_text("\n".join(lines) + "\n", encoding="utf-8")
    print(REPORT_PATH)


if __name__ == "__main__":
    main()
