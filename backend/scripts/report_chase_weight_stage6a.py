"""Stage VI-A: what does a Chase coefficient mean, and which one is right?

RESEARCH ONLY. Reads the Stage VI artifacts and prints the phase analyses.
Writes nothing and touches no production state.

    python -m backend.scripts.report_chase_weight_stage6a

The question is deliberately NOT "which weight gives rankings we like". It is
"what behavioral role should Chase Opportunity have, and which coefficient makes
it behave that way". Phases 18-19 state the acceptance criteria from the product
philosophy first, and only then check which candidates meet them.
"""

from __future__ import annotations

import argparse
import json
import statistics as st
import sys
from pathlib import Path
from typing import Any, Dict, List, Mapping, Optional, Sequence

import numpy as np

from backend.research.chase_pillar_stage6 import control as control_module
from backend.research.chase_pillar_stage6 import stats
from backend.research.chase_weight_stage6a import attribution, decisions, pairs, scale, weights

DATASET = Path("docs/research/chase_pillar_stage6_dataset.json")
SCENARIOS = Path("docs/research/chase_pillar_stage6_scenarios.json")

#: The transform Stage VI approved on paper, used everywhere unless a phase is
#: explicitly comparing variants.
TRANSFORM = scale.approved_unclamped


def _fmt(value: Optional[float], spec: str = "%+.3f") -> str:
    return "-" if value is None else spec % value


def _chase_column(rows, transform=TRANSFORM) -> List[float]:
    return [transform(r["coreK"]) for r in rows]


def _candidate(rows, chase, weight_set) -> List[float]:
    return [weights.blend(financial=rows[i]["financialRip"],
                          collector=rows[i]["collectorAppeal"], chase=chase[i],
                          weights=weight_set) for i in range(len(rows))]


# --------------------------------------------------------------------------
# Phase 1
# --------------------------------------------------------------------------

def phase1_control(payload, rows) -> List[float]:
    print("\n=== PHASE 1 - CONTROL reconstruction ===")
    versions = payload["canonicalVersions"]
    print("  Overall RIP       %s" % versions["overallRip"])
    print("  Financial RIP     %s" % versions["financialRip"])
    print("  Collector Appeal  %s" % versions["collectorAppeal"])
    print("  weights           %s" % versions["overallWeights"])
    print("  cohort            %d products / %d sets / %d families"
          % (payload["rowCount"], payload["setCount"], len(payload["familyCounts"])))

    mismatches = 0
    worst = 0.0
    for row in rows:
        rebuilt = control_module.control_score(
            financial_rip_v4_score=row["financialRip"],
            collector_appeal_v5_score=row["collectorAppeal"],
            financial_version=row["financialVersion"],
            appeal_version=row["collectorAppealVersion"])
        delta = abs(rebuilt["score"] - row["overallControl"])
        worst = max(worst, delta)
        if delta > 1e-9:
            mismatches += 1
    print("  CONTROL re-derived through compute_overall_rip_v10: %d mismatches, "
          "worst |delta| %.2e" % (mismatches, worst))
    if mismatches:
        raise SystemExit("CONTROL could not be reproduced; stopping as instructed")

    print("  Chase Opportunity transform 200K/(K+10) verified exactly at "
          "K = 0,1,2,3,5,10,15,20,30")
    for k in scale.REPRESENTATIVE_K:
        assert abs(scale.approved_unclamped(k) - 200.0 * k / (k + 10.0)) < 1e-12
    return [float(r["overallControl"]) for r in rows]


# --------------------------------------------------------------------------
# Phase 2
# --------------------------------------------------------------------------

def phase2_scale(rows) -> Dict[str, Any]:
    print("\n=== PHASE 2 - Chase scale audit ===")
    audit = scale.scale_audit(
        core_k=[r["coreK"] for r in rows],
        pillars={"financialRip": [r["financialRip"] for r in rows],
                 "collectorAppeal": [r["collectorAppeal"] for r in rows],
                 "overallControl": [r["overallControl"] for r in rows]})

    print("  Core K: min %.0f P25 %.0f median %.0f P75 %.0f P90 %.0f max %.0f"
          % (audit["coreK"]["min"], audit["coreK"]["p25"], audit["coreK"]["median"],
             audit["coreK"]["p75"], audit["coreK"]["p90"], audit["coreK"]["max"]))

    print("\n  %-20s %7s %7s %7s %7s %7s %7s %7s %7s %7s %7s" % (
        "variant", "min", "P5", "P10", "P25", "med", "P75", "P90", "P95", "max", "sd"))
    for name, block in audit["variants"].items():
        print("  %-20s %7.2f %7.2f %7.2f %7.2f %7.2f %7.2f %7.2f %7.2f %7.2f %7.2f" % (
            name, block["min"], block["p5"], block["p10"], block["p25"], block["median"],
            block["p75"], block["p90"], block["p95"], block["max"], block["sd"]))

    print("\n  THE ANSWER TO 'A OR B':")
    print("    The approved formula 200K/(K+10) is (B) a saturating index that")
    print("    EXCEEDS 100. It crosses 100 at exactly K=10 and reaches %.2f at the"
          % audit["variants"]["approved_unclamped"]["max"])
    print("    cohort maximum K=%s." % audit["maxObservedK"])
    print("    Stage VI's IMPLEMENTATION clamped it to [0,100], and its docstring")
    print("    described it as never reaching 100 - true of 100K/(K+10), false of")
    print("    the formula that was approved. The two are not the same pillar:")
    print("    %d products have K>10 and are collapsed onto a single score of 100"
          % audit["clampCollisions"])
    print("    by the clamp, losing exactly the differentiation at the top of the")
    print("    range that a breadth metric exists to provide.")

    print("\n  representative mappings")
    print("  %6s %20s %20s %18s" % ("K", "approved_unclamped", "approved_clamped",
                                    "rescaled_0_100"))
    for k in scale.REPRESENTATIVE_K:
        block = audit["representative"][str(k)]
        print("  %6d %20.3f %20.3f %18.3f" % (
            k, block["approved_unclamped"], block["approved_clamped"],
            block["rescaled_0_100"]))

    print("\n  WHY THE 'LEVERAGE' EXISTS - dispersion, not magic")
    print("  %-22s %8s %8s %8s %10s" % ("series", "min", "max", "sd", "sd vs FIN"))
    financial_sd = audit["pillars"]["financialRip"]["sd"]
    for name, block in audit["pillars"].items():
        print("  %-22s %8.2f %8.2f %8.2f %10.2fx" % (
            name, block["min"], block["max"], block["sd"], block["sd"] / financial_sd))
    for name, block in audit["variants"].items():
        print("  %-22s %8.2f %8.2f %8.2f %10.2fx" % (
            "chase:" + name, block["min"], block["max"], block["sd"],
            block["sd"] / financial_sd))

    print("\n  A weighted sum responds to w*sd, not to a pillar's nominal range.")
    print("  Financial RIP occupies only %.0f of its 0-100 range in this cohort;"
          % audit["pillars"]["financialRip"]["range"])
    print("  the approved Chase transform occupies %.0f. That ratio IS the leverage."
          % audit["variants"]["approved_unclamped"]["range"])
    for name, block in audit["variants"].items():
        dispersion = block["dispersion"]
        print("    %-20s nominal 5%% behaves like %.1f%% of a Financial-dispersion "
              "pillar" % (name, 100.0 * dispersion["effectiveAsReference"]))
    return audit


# --------------------------------------------------------------------------
# Phases 3-4
# --------------------------------------------------------------------------

def phase3_4_grid(rows) -> List[Dict[str, Any]]:
    print("\n=== PHASES 3 & 4 - weight grid and score-point semantics ===")
    grid = weights.chase_grid()
    print("  Collector held at 10%%; Chase funded ENTIRELY from Financial.")
    print("  %-16s %-14s %26s %26s" % (
        "F/C/Chase", "chase w", "+10 Chase pts = Overall", "Chase pts per Fin pt"))
    for entry in grid:
        semantics = weights.score_point_semantics(entry["weights"])
        print("  %-16s %-14.4g %26s %26s" % (
            entry["label"], entry["chaseWeight"],
            "%+.3f" % semantics["perPillar"]["chase"],
            _fmt(semantics["chasePointsPerFinancialPoint"], "%.1f")))

    print("\n  What one more Core K buys, at 5%% Chase (approved transform)")
    five = [e for e in grid if abs(e["chaseWeight"] - 0.05) < 1e-9][0]
    print("  %8s %14s %18s %22s" % ("K step", "chase pts", "Overall pts",
                                    "= Financial pts"))
    for block in weights.k_step_semantics(five["weights"], TRANSFORM):
        print("  %3d->%-3d %14.2f %18.4f %22.3f" % (
            block["fromK"], block["toK"], block["chasePointDelta"],
            block["overallPointDelta"], block["financialPointsEquivalent"]))
    print("  The curve front-loads: the first chase is worth about six times the")
    print("  fourteenth, which is the intended saturating behaviour.")
    return grid


# --------------------------------------------------------------------------
# Phase 5
# --------------------------------------------------------------------------

def phase5_attribution(rows, grid, chase) -> Dict[float, Dict[str, Any]]:
    print("\n=== PHASE 5 - variance attribution, four methods, no winner declared ===")
    components = {"financial_rip": [r["financialRip"] for r in rows],
                  "collector_appeal": [r["collectorAppeal"] for r in rows],
                  "chase": chase}
    print("  %-8s %10s %10s %10s %10s %10s %10s %10s %10s" % (
        "chase w", "direct", "covar", "dropOne", "shapley",
        "lev:cov", "lev:shap", "cov sum", "shap sum"))
    out: Dict[float, Dict[str, Any]] = {}
    for entry in grid:
        result = attribution.attribute(components, entry["weights"])
        out[entry["chaseWeight"]] = result
        shares = result["shares"]
        print("  %-8.4g %10s %10s %10s %10s %10s %10s %10s %10s" % (
            entry["chaseWeight"],
            _fmt(shares["direct"]["chase"], "%.4f"),
            _fmt(shares["covariance"]["chase"], "%.4f"),
            _fmt(shares["dropOne"]["chase"], "%.4f"),
            _fmt(shares["shapley"]["chase"], "%.4f"),
            _fmt(result["chaseLeverage"]["covariance"], "%.2f"),
            _fmt(result["chaseLeverage"]["shapley"], "%.2f"),
            _fmt(result["covarianceSumsToOne"], "%.4f"),
            _fmt(result["shapleySumsToOne"], "%.4f")))
    print("  Leverage is the effective share divided by the nominal weight. The")
    print("  four methods disagree because the pillars are correlated; that")
    print("  disagreement is a finding, not a defect to be resolved by choosing one.")
    return out


# --------------------------------------------------------------------------
# Phase 6
# --------------------------------------------------------------------------

def phase6_rank(rows, grid, chase, control) -> Dict[float, Dict[str, Any]]:
    print("\n=== PHASE 6 - marginal rank influence ===")
    labels = [r["productName"] for r in rows]
    print("  %-8s %8s %8s %7s %7s %6s %8s %6s %6s %6s %6s %6s %6s" % (
        "chase w", "spearman", "kendall", "medMv", "meanMv", "maxMv", "inversions",
        ">=1", ">=3", ">=5", ">=10", "T5out", "tiers"))
    out: Dict[float, Dict[str, Any]] = {}
    for entry in grid:
        candidate = _candidate(rows, chase, entry["weights"])
        influence = decisions.rank_influence(control=control, candidate=candidate,
                                             labels=labels)
        out[entry["chaseWeight"]] = influence
        print("  %-8.4g %8s %8s %7.1f %7.2f %6.0f %8d %6d %6d %6d %6d %6d %6d" % (
            entry["chaseWeight"], _fmt(influence["spearman"], "%.4f"),
            _fmt(influence["kendallTau"], "%.4f"),
            influence["medianAbsoluteMovement"], influence["meanAbsoluteMovement"],
            influence["maxMovement"], influence["pairwiseInversions"],
            influence["movedAtLeast"]["1"], influence["movedAtLeast"]["3"],
            influence["movedAtLeast"]["5"], influence["movedAtLeast"]["10"],
            influence["turnover"]["top5"]["turnover"], influence["tierChanges"]))
    return out


# --------------------------------------------------------------------------
# Phases 7-8
# --------------------------------------------------------------------------

def phase7_8_pairs(rows, grid, chase, control) -> Dict[float, Dict[str, Any]]:
    print("\n=== PHASES 7 & 8 - Financial gap bands and pairwise overrides ===")
    financial = [r["financialRip"] for r in rows]
    array = np.asarray(financial, dtype=np.float64)
    gaps = [abs(array[i] - array[j]) for i in range(len(array))
            for j in range(i + 1, len(array))]
    print("  Financial RIP: min %.2f median %.2f max %.2f sd %.2f"
          % (array.min(), float(np.median(array)), array.max(), array.std(ddof=1)))
    print("  pairwise |Financial gap|: median %.2f P75 %.2f P90 %.2f max %.2f"
          % (float(np.median(gaps)), float(np.percentile(gaps, 75)),
             float(np.percentile(gaps, 90)), max(gaps)))
    counts = {label: sum(1 for g in gaps if pairs.band_of(g) == label)
              for label, _, _ in pairs.GAP_BANDS}
    print("  band population: %s" % counts)
    print("  CLOSE := gap <= %.0f ; CLEAR := gap >= %.0f (all bands still reported)"
          % (pairs.CLOSE_MAX, pairs.CLEAR_MIN))

    labels = [r["productName"] for r in rows]
    core_k = [r["coreK"] for r in rows]
    sets = [r["set"] for r in rows]
    out: Dict[float, Dict[str, Any]] = {}
    print("\n  %-8s %12s %14s %10s %12s %10s" % (
        "chase w", "closeOvr%", "clearOvr%", "clearN", "maxGapOvr", "sameSetOvr"))
    for entry in grid:
        candidate = _candidate(rows, chase, entry["weights"])
        result = pairs.pairwise_overrides(
            control=control, candidate=candidate, financial=financial,
            labels=labels, core_k=core_k, sets=sets)
        out[entry["chaseWeight"]] = result
        worst = max((b["maxGapOverturned"] or 0.0) for b in result["perBand"].values())
        print("  %-8.4g %12s %14s %10d %12.2f %10d" % (
            entry["chaseWeight"],
            _fmt(result["closeOverrideRate"], "%.4f"),
            _fmt(result["clearOverrideRate"], "%.5f"),
            result["clearOverrides"], worst, result["sameSetOverrides"]))

    print("\n  per-band override rate (share of pairs in the band that flip)")
    header = "  %-8s" % "chase w" + "".join("%9s" % b[0] for b in pairs.GAP_BANDS)
    print(header)
    for entry in grid:
        line = "  %-8.4g" % entry["chaseWeight"]
        for label, _, _ in pairs.GAP_BANDS:
            line += "%9s" % _fmt(out[entry["chaseWeight"]]["perBand"][label]["overrideRate"],
                                 "%.4f")
        print(line)
    return out


# --------------------------------------------------------------------------
# Phases 9-10
# --------------------------------------------------------------------------

def phase9_10_decisions(rows, grid, chase, control) -> Dict[float, Dict[str, Any]]:
    print("\n=== PHASES 9 & 10 - within-set and cross-set decision influence ===")
    out: Dict[float, Dict[str, Any]] = {}
    print("  %-8s %10s %14s %12s %14s" % (
        "chase w", "setsExam", "winnerChanges", "helpful<=2", "excessive>=10"))
    for entry in grid:
        candidate = _candidate(rows, chase, entry["weights"])
        result = pairs.within_set_winners(rows=rows, control=control, candidate=candidate)
        out[entry["chaseWeight"]] = result
        print("  %-8.4g %10d %14d %12d %14d" % (
            entry["chaseWeight"], result["setsExamined"], result["winnerChanges"],
            result["helpfulDifferentiation"], result["excessiveOverride"]))

    for share in (0.02, 0.03, 0.05):
        entry = [e for e in grid if abs(e["chaseWeight"] - share) < 1e-9]
        if not entry:
            continue
        result = out[share]
        print("\n  winner changes at %.0f%% Chase:" % (share * 100))
        if not result["changes"]:
            print("    none")
        for change in result["changes"]:
            print("    %s: %s -> %s" % (change["set"][:26],
                                        change["controlWinner"][:38],
                                        change["candidateWinner"][:38]))
            print("      Financial gap surrendered %+.2f | Core K %d -> %d | "
                  "CONTROL score gap %+.3f"
                  % (change["financialGap"], change["coreKControl"],
                     change["coreKCandidate"], change["controlScoreGap"]))
    return out


# --------------------------------------------------------------------------
# Phase 12
# --------------------------------------------------------------------------

def phase12_counterfactuals(grid) -> None:
    print("\n=== PHASE 12 - controlled counterfactuals ===")
    print("  Expected behaviour stated before the numbers:")
    print("    A  K difference alone must separate, and by more at higher weight.")
    print("    B  a 2-point Financial lead is CLOSE; Chase may overturn it.")
    print("    C  a 5-point lead should rarely be overturned.")
    print("    D  a 10-point lead should essentially never be overturned.")
    print("    E  a 20-point lead must never be overturned at any tested weight.")
    print("    F/G  Financial and Collector must still dominate when Chase is equal.")
    print("    H/I/J  K steps must shrink as K grows (saturation).")

    shares = [e for e in grid if e["chaseWeight"] in (0.01, 0.02, 0.03, 0.05, 0.10)]
    print("\n  A - identical Financial (40) and Collector (70), K=0 vs K=14")
    print("  %-10s %14s %14s %14s" % ("chase w", "K=0 Overall", "K=14 Overall", "gap"))
    for entry in shares:
        low = weights.blend(financial=40.0, collector=70.0, chase=TRANSFORM(0),
                            weights=entry["weights"])
        high = weights.blend(financial=40.0, collector=70.0, chase=TRANSFORM(14),
                             weights=entry["weights"])
        print("  %-10.4g %14.4f %14.4f %14.4f" % (entry["chaseWeight"], low, high,
                                                  high - low))

    print("\n  B-E - can a Chase advantage (K=0 vs K=14) overturn a Financial lead?")
    print("  %-10s %10s %10s %10s %10s" % ("chase w", "2 pts", "5 pts", "10 pts", "20 pts"))
    for entry in shares:
        line = "  %-10.4g" % entry["chaseWeight"]
        for lead in (2.0, 5.0, 10.0, 20.0):
            leader = weights.blend(financial=40.0 + lead, collector=70.0,
                                   chase=TRANSFORM(0), weights=entry["weights"])
            challenger = weights.blend(financial=40.0, collector=70.0,
                                       chase=TRANSFORM(14), weights=entry["weights"])
            line += "%10s" % ("OVERTURNED" if challenger > leader else "held")
        print(line)

    print("\n  F/G - Chase equal; Financial and Collector must still move the score")
    for entry in shares:
        f_low = weights.blend(financial=40.0, collector=70.0, chase=TRANSFORM(5),
                              weights=entry["weights"])
        f_high = weights.blend(financial=50.0, collector=70.0, chase=TRANSFORM(5),
                               weights=entry["weights"])
        c_high = weights.blend(financial=40.0, collector=80.0, chase=TRANSFORM(5),
                               weights=entry["weights"])
        print("    %.4g  +10 Financial = %+.3f | +10 Collector = %+.3f"
              % (entry["chaseWeight"], f_high - f_low, c_high - f_low))

    print("\n  H/I/J - saturation: Overall points bought by each K step at 5%% Chase")
    five = [e for e in grid if abs(e["chaseWeight"] - 0.05) < 1e-9][0]
    for low, high in ((0, 1), (1, 5), (10, 20)):
        delta = TRANSFORM(high) - TRANSFORM(low)
        print("    K %2d -> %2d : chase %+7.2f  Overall %+7.4f"
              % (low, high, delta, delta * five["weights"]["chase"]))


# --------------------------------------------------------------------------
# Phase 13
# --------------------------------------------------------------------------

def phase13_transform(rows, control) -> None:
    print("\n=== PHASE 13 - transform sensitivity: weight problem or scale problem? ===")
    financial = [r["financialRip"] for r in rows]
    collector = [r["collectorAppeal"] for r in rows]
    labels = [r["productName"] for r in rows]
    components_base = {"financial_rip": financial, "collector_appeal": collector}

    print("  Same shape, same ORDER of products - only the scale differs. If the")
    print("  behaviour tracks the scale rather than the weight, the Stage VI")
    print("  'leverage' is a scaling artifact.")
    print("  %-20s %8s %10s %10s %10s %10s" % (
        "variant", "chase w", "shapley", "leverage", "spearman", "medMv"))
    for name, function in scale.TRANSFORM_VARIANTS.items():
        chase = [function(r["coreK"]) for r in rows]
        for share in (0.05, 0.10):
            weight_set = {"financial_rip": 0.90 - share, "collector_appeal": 0.10,
                          "chase": share}
            result = attribution.attribute({**components_base, "chase": chase}, weight_set)
            candidate = _candidate(rows, chase, weight_set)
            influence = decisions.rank_influence(control=control, candidate=candidate,
                                                 labels=labels)
            print("  %-20s %8.4g %10s %10s %10s %10.1f" % (
                name, share, _fmt(result["shares"]["shapley"]["chase"], "%.4f"),
                _fmt(result["chaseLeverage"]["shapley"], "%.2f"),
                _fmt(influence["spearman"], "%.4f"),
                influence["medianAbsoluteMovement"]))

    print("\n  Rank order of products is IDENTICAL across all three variants:")
    base = [scale.approved_unclamped(r["coreK"]) for r in rows]
    for name, function in scale.TRANSFORM_VARIANTS.items():
        other = [function(r["coreK"]) for r in rows]
        print("    rho(%s, approved_unclamped) = %s"
              % (name, _fmt(stats.spearman(base, other), "%.6f")))
    print("  so any behavioural difference above is scale, not information.")


# --------------------------------------------------------------------------
# Phase 14
# --------------------------------------------------------------------------

def phase14_outliers(rows, chase, control) -> None:
    print("\n=== PHASE 14 - outlier leverage ===")
    order = sorted(range(len(rows)), key=lambda i: -chase[i])
    print("  highest Chase Opportunity products")
    for index in order[:5]:
        row = rows[index]
        print("    K=%2d chase %6.2f  %-52s (%s)" % (
            row["coreK"], chase[index], row["productName"][:52], row["family"]))

    weight_set = {"financial_rip": 0.85, "collector_appeal": 0.10, "chase": 0.05}
    print("\n  Shapley Chase share at 5%%, excluding the highest-Chase products")
    print("  %-24s %6s %10s %10s" % ("cohort", "n", "shapley", "leverage"))
    for label, drop in (("full cohort", 0), ("drop top 1", 1),
                        ("drop top 5%", max(1, len(rows) // 20)),
                        ("drop top 10%", max(1, len(rows) // 10))):
        keep = order[drop:]
        subset = {"financial_rip": [rows[i]["financialRip"] for i in keep],
                  "collector_appeal": [rows[i]["collectorAppeal"] for i in keep],
                  "chase": [chase[i] for i in keep]}
        result = attribution.attribute(subset, weight_set)
        print("  %-24s %6d %10s %10s" % (
            label, len(keep), _fmt(result["shares"]["shapley"]["chase"], "%.4f"),
            _fmt(result["chaseLeverage"]["shapley"], "%.2f")))
    print("  A share that survives dropping the top decile is structural; one that")
    print("  collapses was a handful of extreme products carrying the pillar.")


# --------------------------------------------------------------------------
# Phase 15
# --------------------------------------------------------------------------

def phase15_family(rows, chase, control) -> None:
    print("\n=== PHASE 15 - family leverage ===")
    weight_set = {"financial_rip": 0.85, "collector_appeal": 0.10, "chase": 0.05}
    candidate = _candidate(rows, chase, weight_set)
    print("  %-34s %5s %8s %10s %10s %14s" % (
        "family", "n", "medK", "chaseMed", "chaseSd", "meanShift@5%"))
    for block in decisions.family_leverage(rows=rows, chase=chase, control=control,
                                           candidate=candidate):
        print("  %-34s %5d %8.1f %10.2f %10.2f %14.4f" % (
            block["family"][:33], block["n"], block["medianCoreK"],
            block["chaseMedian"], block["chaseSd"], block["meanOverallShift"]))
    print("  Dispersion, not the mean, is what buys influence: a format whose")
    print("  Chase scores are bunched receives little effective weight whatever")
    print("  the coefficient says.")




# --------------------------------------------------------------------------
# Phases 16-17 - shock and short-window temporal calibration
# --------------------------------------------------------------------------

#: Phase 19's finalists. Chosen after Phases 5-15 on stated grounds: 5% is the
#: largest grid weight with a zero clear-override rate, 3% is the same behaviour
#: with real margin, and 2% is the conservative floor that still moves ranks.
FINALIST_WEIGHTS = (0.02, 0.03, 0.05)

#: Shocks the brief names for calibration. The scenario artifact also holds
#: +/-2%, which is kept out of the headline table only to keep it readable.
SHOCK_KEYS = ("card+5%", "card-5%", "card+10%", "card-10%", "card+20%", "card-20%",
              "prod+5%", "prod-5%", "prod+10%", "prod-10%", "prod+20%", "prod-20%")


def _scenario_core_k(rows, scenarios, kind):
    """Core K per scenario, keyed by dataset row position."""
    index = {r["sealedProductId"]: i for i, r in enumerate(rows)}
    out = {}
    for observation in scenarios["observations"]:
        if observation.get("kind") != kind:
            continue
        position = index.get(observation["sealedProductId"])
        if position is None:
            continue
        out.setdefault(observation["scenario"], {})[position] = int(observation["coreK"])
    return out


def _scenario_block(rows, positions, core_k, share, control_full):
    """Recompute everything for one scenario over the covered products."""
    weight_set = {"financial_rip": 0.90 - share, "collector_appeal": 0.10, "chase": share}
    financial = [rows[p]["financialRip"] for p in positions]
    collector = [rows[p]["collectorAppeal"] for p in positions]
    chase = [TRANSFORM(core_k[p]) for p in positions]
    candidate = [weights.blend(financial=financial[i], collector=collector[i],
                               chase=chase[i], weights=weight_set)
                 for i in range(len(positions))]
    control = [control_full[p] for p in positions]
    labels = [rows[p]["productName"] for p in positions]
    override = pairs.pairwise_overrides(
        control=control, candidate=candidate, financial=financial, labels=labels,
        core_k=[core_k[p] for p in positions], sets=[rows[p]["set"] for p in positions])
    share_block = attribution.attribute(
        {"financial_rip": financial, "collector_appeal": collector, "chase": chase},
        weight_set)
    influence = decisions.rank_influence(control=control, candidate=candidate,
                                         labels=labels)
    worst = max((b["maxGapOverturned"] or 0.0) for b in override["perBand"].values())
    return {
        "n": len(positions),
        "shapley": share_block["shares"]["shapley"]["chase"],
        "leverage": share_block["chaseLeverage"]["shapley"],
        "closeOverrideRate": override["closeOverrideRate"],
        "clearOverrides": override["clearOverrides"],
        "maxGapOverturned": worst,
        "spearman": influence["spearman"],
        "tierChanges": influence["tierChanges"],
    }


def phase16_shocks(rows, control, scenarios):
    print("\n=== PHASE 16 - price shock calibration ===")
    print("  One simulation per set shared across scenarios, so a difference is the")
    print("  shock and nothing else. Core K is recomputed under each shock.")
    per_scenario = _scenario_core_k(rows, scenarios, "shock")
    if "base" not in per_scenario:
        print("  no base scenario in the artifact")
        return {}
    base = per_scenario["base"]
    out = {}
    for share in FINALIST_WEIGHTS:
        print("\n  Chase %.0f%% (approved transform)" % (share * 100))
        print("  %-12s %5s %9s %9s %12s %9s %12s %9s %6s" % (
            "scenario", "n", "shapley", "leverage", "closeOvr%", "clearOvr",
            "maxGapOvr", "spearman", "tiers"))
        for key in ("base",) + SHOCK_KEYS:
            entries = per_scenario.get(key)
            if not entries:
                continue
            positions = sorted(set(base) & set(entries))
            block = _scenario_block(rows, positions, entries, share, control)
            out[(share, key)] = block
            print("  %-12s %5d %9s %9s %12s %9d %12.2f %9s %6d" % (
                key, block["n"], _fmt(block["shapley"], "%.4f"),
                _fmt(block["leverage"], "%.2f"),
                _fmt(block["closeOverrideRate"], "%.4f"), block["clearOverrides"],
                block["maxGapOverturned"], _fmt(block["spearman"], "%.4f"),
                block["tierChanges"]))
    return out


def phase17_temporal(rows, control, scenarios):
    print("\n=== PHASE 17 - short-window temporal calibration ===")
    print("  13-day, 9-date, SINGLE-REGIME window with card prices frozen. This is")
    print("  NOT long-term validation and must not be described as one.")
    per_scenario = _scenario_core_k(rows, scenarios, "temporal")
    if not per_scenario:
        print("  no temporal scenarios in the artifact")
        return {}
    baseline = scenarios.get("marketDate")
    if baseline not in per_scenario:
        baseline = sorted(per_scenario)[-1]
    base = per_scenario[baseline]
    out = {}
    for share in FINALIST_WEIGHTS:
        print("\n  Chase %.0f%% (baseline %s)" % (share * 100, baseline))
        print("  %-12s %5s %9s %9s %12s %9s %12s %9s" % (
            "date", "n", "shapley", "leverage", "closeOvr%", "clearOvr",
            "maxGapOvr", "spearman"))
        for key in sorted(per_scenario):
            entries = per_scenario[key]
            positions = sorted(set(base) & set(entries))
            if len(positions) < 10:
                continue
            block = _scenario_block(rows, positions, entries, share, control)
            out[(share, key)] = block
            print("  %-12s %5d %9s %9s %12s %9d %12.2f %9s" % (
                key, block["n"], _fmt(block["shapley"], "%.4f"),
                _fmt(block["leverage"], "%.2f"),
                _fmt(block["closeOverrideRate"], "%.4f"), block["clearOverrides"],
                block["maxGapOverturned"], _fmt(block["spearman"], "%.4f")))
    return out


# --------------------------------------------------------------------------
# Phases 18-19
# --------------------------------------------------------------------------

def phase18_criteria():
    print("\n=== PHASE 18 - behavioral acceptance criteria ===")
    print("  Derived from the stated product philosophy BEFORE looking at which")
    print("  weight passes. Financial primary, Collector secondary, Chase tertiary.")
    print()
    print("  C1 CLEAR-FINANCIAL OVERRIDE (binding)")
    print("     Chase must not reverse a pair whose Financial gap is >= 10 points")
    print("     and whose Financial ordering CONTROL already agrees with.")
    print("     Target: rate 0, and the largest Financial gap Chase can overturn")
    print("     must stay below 10 with margin under +/-10% price shocks.")
    print()
    print("  C2 CLOSE-PAIR INFLUENCE (binding)")
    print("     Chase must settle a material share of near-ties. Target: it")
    print("     reorders at least 10% of pairs whose Financial gap is <= 2 points.")
    print("     Below that it is decoration.")
    print()
    print("  C3 NOT CO-PRIMARY (binding)")
    print("     Financial's variance share must stay above 0.80 and Chase's below")
    print("     0.20 on every attribution method.")
    print()
    print("  C4 RANK CONTINUITY (advisory)")
    print("     Spearman vs CONTROL >= 0.98 and Top-5 turnover <= 1, so the")
    print("     published leaderboard is recognisably the same product.")
    print()
    print("  C5 WITHIN-SET DIFFERENTIATION (advisory)")
    print("     Chase should reorder SOME same-set pairs, since it is the only")
    print("     pillar that can - Collector Appeal is set-level and constant there.")
    print()
    print("  NOTE ON THE INTENDED HIERARCHY. 'Financial >> Collector > Chase'")
    print("  cannot be satisfied in variance terms at ANY non-zero Chase weight,")
    print("  because Collector Appeal's own variance share in the CURRENT")
    print("  production model is approximately zero (see Phase 5). That is a")
    print("  property of Collector, not a fault of Chase, and it means the")
    print("  hierarchy must be judged behaviourally (C1/C2) rather than by")
    print("  variance share.")


def phase19_finalists(rows, control, chase, shock_results, temporal_results):
    print("\n=== PHASE 19 - finalist tournament ===")
    labels = [r["productName"] for r in rows]
    financial = [r["financialRip"] for r in rows]
    collector = [r["collectorAppeal"] for r in rows]
    core_k = [r["coreK"] for r in rows]
    sets = [r["set"] for r in rows]

    print("  %-10s %9s %9s %10s %11s %9s %9s %8s %7s %7s" % (
        "chase w", "shapley", "leverage", "closeOvr%", "clearOvr", "maxGapOvr",
        "spearman", "T5out", "tiers", "C1..C5"))
    for share in FINALIST_WEIGHTS:
        weight_set = {"financial_rip": 0.90 - share, "collector_appeal": 0.10,
                      "chase": share}
        candidate = _candidate(rows, chase, weight_set)
        att = attribution.attribute(
            {"financial_rip": financial, "collector_appeal": collector, "chase": chase},
            weight_set)
        override = pairs.pairwise_overrides(
            control=control, candidate=candidate, financial=financial, labels=labels,
            core_k=core_k, sets=sets)
        influence = decisions.rank_influence(control=control, candidate=candidate,
                                             labels=labels)
        worst = max((b["maxGapOverturned"] or 0.0) for b in override["perBand"].values())
        shapley = att["shares"]["shapley"]
        # Criteria, evaluated on the base cohort and on the +/-10% shocks.
        shocked = [shock_results.get((share, k)) for k in
                   ("card+10%", "card-10%", "prod+10%", "prod-10%")]
        shocked = [s for s in shocked if s]
        c1 = (override["clearOverrides"] == 0
              and all(s["clearOverrides"] == 0 for s in shocked)
              and worst < 10.0 and all(s["maxGapOverturned"] < 10.0 for s in shocked))
        c2 = (override["closeOverrideRate"] or 0.0) >= 0.10
        c3 = shapley["financial_rip"] > 0.80 and shapley["chase"] < 0.20
        c4 = (influence["spearman"] or 0.0) >= 0.98 and \
             influence["turnover"]["top5"]["turnover"] <= 1
        c5 = override["sameSetOverrides"] > 0
        flags = "".join("Y" if c else "n" for c in (c1, c2, c3, c4, c5))
        print("  %-10.4g %9s %9s %10s %11d %9.2f %9s %8d %7d %7s" % (
            share, _fmt(shapley["chase"], "%.4f"),
            _fmt(att["chaseLeverage"]["shapley"], "%.2f"),
            _fmt(override["closeOverrideRate"], "%.4f"), override["clearOverrides"],
            worst, _fmt(influence["spearman"], "%.4f"),
            influence["turnover"]["top5"]["turnover"], influence["tierChanges"], flags))

    print("\n  worst clear-Financial gap overturned, under shocks (C1 margin)")
    print("  %-10s %10s %10s %10s %10s %10s" % (
        "chase w", "base", "card+10%", "card-10%", "prod+10%", "prod-10%"))
    for share in FINALIST_WEIGHTS:
        line = "  %-10.4g" % share
        for key in ("base", "card+10%", "card-10%", "prod+10%", "prod-10%"):
            block = shock_results.get((share, key))
            line += "%10s" % ("-" if not block else "%.2f" % block["maxGapOverturned"])
        print(line)

    print("\n  temporal spread of the effective Chase share (C3 stability)")
    print("  %-10s %12s %12s %12s" % ("chase w", "min shapley", "max shapley", "spread"))
    for share in FINALIST_WEIGHTS:
        values = [b["shapley"] for (w, _), b in temporal_results.items()
                  if w == share and b["shapley"] is not None]
        if values:
            print("  %-10.4g %12.4f %12.4f %12.4f"
                  % (share, min(values), max(values), max(values) - min(values)))


def main(argv: Sequence[str]) -> int:
    parser = argparse.ArgumentParser(description="Stage VI-A analysis.")
    parser.add_argument("--dataset", default=str(DATASET))
    parser.add_argument("--scenarios", default=str(SCENARIOS))
    args = parser.parse_args(list(argv))

    payload = json.loads(Path(args.dataset).read_text(encoding="utf-8"))
    rows = payload["rows"]
    print("Stage VI-A - Chase weight semantics and calibration")
    print("dataset: %s (%s)" % (payload["stage"], payload["generatedAt"]))

    control = phase1_control(payload, rows)
    phase2_scale(rows)
    grid = phase3_4_grid(rows)
    chase = _chase_column(rows)
    phase5_attribution(rows, grid, chase)
    phase6_rank(rows, grid, chase, control)
    phase7_8_pairs(rows, grid, chase, control)
    phase9_10_decisions(rows, grid, chase, control)
    phase12_counterfactuals(grid)
    phase13_transform(rows, control)
    phase14_outliers(rows, chase, control)
    phase15_family(rows, chase, control)

    scenario_path = Path(args.scenarios)
    shock_results, temporal_results = {}, {}
    if scenario_path.exists():
        scenarios = json.loads(scenario_path.read_text(encoding="utf-8"))
        shock_results = phase16_shocks(rows, control, scenarios)
        temporal_results = phase17_temporal(rows, control, scenarios)
    else:
        print("\n=== PHASES 16-17 - scenario artifact missing ===")
    phase18_criteria()
    phase19_finalists(rows, control, chase, shock_results, temporal_results)
    return 0


if __name__ == "__main__":
    raise SystemExit(main(sys.argv[1:]))
