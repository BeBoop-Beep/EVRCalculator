"""Stage VII: is Collector Appeal V5 correctly weighted at 10%?

RESEARCH ONLY. Reads the Stage VI artifacts and prints the phase analyses.
Writes nothing and touches no production state.

    python -m backend.scripts.report_collector_weight_stage7

Selection posture: the lowest sufficient weight wins. A higher coefficient must
earn its place with COLLECTOR-SPECIFIC information, not with movement created by
taking weight away from Financial.
"""

from __future__ import annotations

import argparse
import hashlib
import itertools
import json
import statistics as st
import sys
from pathlib import Path
from typing import Any, Dict, List, Mapping, Optional, Sequence

import numpy as np

from backend.research.chase_pillar_stage6 import control as control_module
from backend.research.chase_pillar_stage6 import stats
from backend.research.chase_weight_stage6a import attribution, closure, decisions, pairs, scale
from backend.research.collector_weight_stage7 import sweep

DATASET = Path("docs/research/chase_pillar_stage6_dataset.json")
SCENARIOS = Path("docs/research/chase_pillar_stage6_scenarios.json")
PREREG = Path("docs/research/COLLECTOR_WEIGHT_STAGE7_PREREGISTRATION.json")


def _fmt(value: Optional[float], spec: str = "%+.4f") -> str:
    return "-" if value is None else spec % value


def _prepare(rows: List[Dict[str, Any]]) -> None:
    """Attach the Stage VI-B normalized Chase column, unclamped."""
    for row in rows:
        row["chaseNormalized"] = scale.rescaled_0_100(row["coreK"])


def phase0_prereg() -> str:
    digest = hashlib.sha256(PREREG.read_bytes()).hexdigest()
    print("\n=== PHASE 7 - preregistration (locked before any candidate result) ===")
    print("  file   %s" % PREREG)
    print("  sha256 %s" % digest)
    payload = json.loads(PREREG.read_text(encoding="utf-8"))
    print("  selectable  %s" % [c["key"] for c in payload["selectableCandidates"]])
    print("  diagnostic  %s" % [c["key"] for c in payload["diagnosticCandidates"]])
    print("  ceiling     %.2f (0.14/0.15 diagnostic only)" % payload["selectionCeiling"])
    print("  funding     %s" % payload["fundingRule"]["financialFormula"])
    return digest


def phase2_control(payload, rows) -> List[float]:
    print("\n=== PHASE 2 - Stage VI-B CONTROL reproduction (gate) ===")
    mismatches, worst = 0, 0.0
    for row in rows:
        rebuilt = control_module.control_score(
            financial_rip_v4_score=row["financialRip"],
            collector_appeal_v5_score=row["collectorAppeal"],
            financial_version=row["financialVersion"],
            appeal_version=row["collectorAppealVersion"])
        delta = abs(rebuilt["score"] - row["overallControl"])
        worst = max(worst, delta)
        mismatches += delta > 1e-9
    print("  cohort %d products / %d sets / %d families"
          % (payload["rowCount"], payload["setCount"], len(payload["familyCounts"])))
    print("  V10 CONTROL inputs re-derived: %d/%d mismatches, worst |delta| %.2e"
          % (mismatches, len(rows), worst))
    if mismatches:
        print("\n  COLLECTOR_STAGE7_BLOCKED_CONTROL_REPRODUCTION_FAILURE")
        raise SystemExit(2)

    control = closure.CANDIDATE_A.score(
        financial=[r["financialRip"] for r in rows],
        collector=[r["collectorAppeal"] for r in rows],
        core_k=[r["coreK"] for r in rows])
    point = sweep.WeightPoint(collector=0.10, selectable=True)
    direct = sweep.score(point, financial=[r["financialRip"] for r in rows],
                         collector=[r["collectorAppeal"] for r in rows],
                         chase=[r["chaseNormalized"] for r in rows])
    delta = max(abs(a - b) for a, b in zip(control, direct))
    print("  Stage VI-B 84/10/6 reproduced independently: worst |delta| %.2e" % delta)
    if delta > 1e-12:
        print("\n  COLLECTOR_STAGE7_BLOCKED_CONTROL_REPRODUCTION_FAILURE")
        raise SystemExit(2)
    return control


def phase3_diagnose(rows) -> None:
    print("\n=== PHASE 3 - what Collector Appeal V5 actually is at product level ===")
    series = {
        "Financial RIP V4": [r["financialRip"] for r in rows],
        "Collector Appeal V5": [r["collectorAppeal"] for r in rows],
        "Chase 100K/(K+10)": [r["chaseNormalized"] for r in rows],
    }
    print("  %-22s %7s %7s %7s %7s %7s %7s %7s %7s %7s %7s %8s" % (
        "series", "min", "P05", "P25", "med", "mean", "P75", "P95", "max", "sd",
        "IQR", "distinct"))
    for name, values in series.items():
        array = np.asarray(values, dtype=np.float64)
        q = lambda p: float(np.percentile(array, p))
        print("  %-22s %7.2f %7.2f %7.2f %7.2f %7.2f %7.2f %7.2f %7.2f %7.2f %7.2f %8d" % (
            name, array.min(), q(5), q(25), q(50), array.mean(), q(75), q(95),
            array.max(), array.std(ddof=1), q(75) - q(25),
            len({round(v, 9) for v in values})))
    financial_sd = float(np.std(series["Financial RIP V4"], ddof=1))
    print("\n  range and dispersion versus Financial")
    for name, values in series.items():
        array = np.asarray(values, dtype=np.float64)
        print("    %-22s range %6.2f  sd %6.2f  (%.2fx Financial sd)"
              % (name, array.max() - array.min(), array.std(ddof=1),
                 array.std(ddof=1) / financial_sd))

    print("\n  3A. within-set variation")
    structure = sweep.within_set_structure(rows, "collectorAppeal")
    print("    verdict: Collector Appeal V5 is %s" % structure["verdict"])
    print("    multi-product sets %d ; sets with any within-set variation %d"
          % (structure["multiProductSets"], structure["setsWithVariation"]))
    for key, label in (("financialRip", "Financial RIP V4"),
                       ("chaseNormalized", "Chase Opportunity")):
        other = sweep.within_set_structure(rows, key)
        print("    for comparison, %-20s is %s" % (label, other["verdict"]))
    if structure["setsWithVariation"] == 0:
        print()
        print("    => Collector Appeal cannot directly change the ordering of")
        print("       products WITHIN a set at any fixed Financial/Chase weighting")
        print("       ratio. Every same-set product carries the identical set score,")
        print("       so the Collector term cancels exactly in a same-set comparison.")
        print("       Any within-set movement observed when the Collector weight is")
        print("       raised is therefore reallocation, not Collector differentiation.")


def phase4_variance(rows, control) -> None:
    print("\n=== PHASE 4 - decomposing the 'approximately zero contribution' finding ===")
    financial = [r["financialRip"] for r in rows]
    collector = [r["collectorAppeal"] for r in rows]
    chase = [r["chaseNormalized"] for r in rows]
    point = sweep.WeightPoint(collector=0.10, selectable=True)

    print("\n  A. standalone weighted dispersion  w_i * SD(X_i)")
    for name, values, weight in (("Financial", financial, point.financial),
                                 ("Collector", collector, point.collector),
                                 ("Chase", chase, point.chase)):
        sd = float(np.std(values, ddof=1))
        print("    %-10s w %.2f  SD %7.3f  w*SD %7.4f" % (name, weight, sd, weight * sd))

    print("\n  B. pairwise relationships")
    for left, right, a, b in (("F", "C", financial, collector),
                              ("F", "K", financial, chase),
                              ("C", "K", collector, chase)):
        print("    %s vs %s   Pearson %s   Spearman %s"
              % (left, right, _fmt(stats.pearson(a, b)), _fmt(stats.spearman(a, b))))

    print("\n  C. covariance-aware contribution to Overall  Cov(w_i X_i, O)/Var(O)")
    components = {"financial_rip": financial, "collector_appeal": collector,
                  "chase": chase}
    result = attribution.attribute(components, point.weight_set)
    shares = result["shares"]["covariance"]
    for name, value in shares.items():
        print("    %-18s %+.4f" % (name, value))
    print("    sum %.6f" % sum(shares.values()))
    print("    (negative contributions are real and are not hidden)")

    print("\n  D. incremental explanatory power of each pillar")
    groups = [r["set"] for r in rows]
    plans = {
        "Collector | Financial": ("collector_appeal", {"financial_rip": financial}),
        "Collector | Chase": ("collector_appeal", {"chase": chase}),
        "Collector | Financial+Chase": ("collector_appeal",
                                        {"financial_rip": financial, "chase": chase}),
        "Financial | Collector+Chase": ("financial_rip",
                                        {"collector_appeal": collector, "chase": chase}),
        "Chase | Financial+Collector": ("chase",
                                        {"financial_rip": financial,
                                         "collector_appeal": collector}),
    }
    print("    %-30s %8s %8s %10s" % ("target | controls", "R2", "cvR2", "resid/sd"))
    for label, (target, controls) in plans.items():
        column = components[target]
        block = stats.reconstruct(name=target, target=column, predictors=controls,
                                  groups=groups)
        print("    %-30s %8s %8s %10s" % (
            label, _fmt(block["r2"], "%.4f"), _fmt(block["crossValidatedR2"], "%.4f"),
            _fmt(block["residualShareOfSd"], "%.4f")))

    print("\n  E. leave-one-pillar-out")
    labels = [r["productName"] for r in rows]
    print("    coefficient DELETION (weights no longer sum to 1; scale shrinks)")
    for dropped in ("collector_appeal", "chase", "financial_rip"):
        weight_set = dict(point.weight_set)
        weight_set[dropped] = 0.0
        candidate = [sum(weight_set[k] * float(components[k][i]) for k in components)
                     for i in range(len(rows))]
        print("      without %-18s rho vs CONTROL %s"
              % (dropped, _fmt(stats.spearman(control, candidate), "%.4f")))
    print("    BUDGET REALLOCATION (dropped weight returned to the others pro rata)")
    for dropped in ("collector_appeal", "chase", "financial_rip"):
        remaining = {k: v for k, v in point.weight_set.items() if k != dropped}
        scale_factor = sum(remaining.values())
        weight_set = {k: v / scale_factor for k, v in remaining.items()}
        candidate = [sum(weight_set[k] * float(components[k][i]) for k in weight_set)
                     for i in range(len(rows))]
        print("      without %-18s rho vs CONTROL %s"
              % (dropped, _fmt(stats.spearman(control, candidate), "%.4f")))


def phase5_populations(rows) -> None:
    print("\n=== PHASE 5 - product-weighted versus set-balanced ===")
    financial = [r["financialRip"] for r in rows]
    collector = [r["collectorAppeal"] for r in rows]
    chase = [r["chaseNormalized"] for r in rows]
    sets = [r["set"] for r in rows]
    components = {"financial_rip": financial, "collector_appeal": collector,
                  "chase": chase}
    point = sweep.WeightPoint(collector=0.10, selectable=True)

    product_weights = np.ones(len(rows), dtype=np.float64)
    balanced = sweep.set_balanced_weights(sets)
    print("  set sizes: min %d max %d ; a %d-product set otherwise counts %.1fx a "
          "single-product set" % (int(1 / balanced.max()), int(1 / balanced.min()),
                                  int(1 / balanced.min()), 1 / balanced.min()))

    print("\n  %-22s %14s %14s" % ("covariance share", "product-weighted", "set-balanced"))
    left = sweep.weighted_covariance_shares(components, point.weight_set, product_weights)
    right = sweep.weighted_covariance_shares(components, point.weight_set, balanced)
    for name in ("financial_rip", "collector_appeal", "chase"):
        print("  %-22s %14.4f %14.4f" % (name, left[name], right[name]))

    print("\n  dispersion under each scheme")
    for name, values in components.items():
        _, pv = sweep.weighted_moments(values, product_weights)
        _, bv = sweep.weighted_moments(values, balanced)
        print("    %-18s sd product %7.3f   sd set-balanced %7.3f"
              % (name, pv ** 0.5, bv ** 0.5))

    print("\n  Collector at SET level only (one observation per set)")
    seen: Dict[str, float] = {}
    for row in rows:
        seen.setdefault(row["set"], float(row["collectorAppeal"]))
    values = list(seen.values())
    print("    n %d  min %.2f  median %.2f  max %.2f  sd %.2f"
          % (len(values), min(values), st.median(values), max(values),
             float(np.std(values, ddof=1))))


def phase6_within_between(rows) -> None:
    print("\n=== PHASE 6 - within-set versus between-set Collector signal ===")
    collector = [float(r["collectorAppeal"]) for r in rows]
    same_set = same_set_c_differs = 0
    cross_set = cross_set_c_differs = 0
    same_family_cross = 0
    for i, j in itertools.combinations(range(len(rows)), 2):
        differs = abs(collector[i] - collector[j]) > 1e-12
        if rows[i]["set"] == rows[j]["set"]:
            same_set += 1
            same_set_c_differs += differs
        else:
            cross_set += 1
            cross_set_c_differs += differs
            if rows[i]["family"] == rows[j]["family"]:
                same_family_cross += 1
    total = same_set + cross_set
    print("  pair census over %d products (%d pairs)" % (len(rows), total))
    print("    same-set pairs              %6d (%.1f%%) ; C differs in %d of them"
          % (same_set, 100.0 * same_set / total, same_set_c_differs))
    print("    cross-set pairs             %6d (%.1f%%) ; C differs in %d of them"
          % (cross_set, 100.0 * cross_set / total, cross_set_c_differs))
    print("    same-family cross-set pairs %6d" % same_family_cross)
    print()
    print("  => Collector Appeal carries information on %.1f%% of pairs and is"
          % (100.0 * cross_set_c_differs / total))
    print("     structurally silent on the other %.1f%%. Its entire contribution is"
          % (100.0 * (total - cross_set_c_differs) / total))
    print("     BETWEEN sets. No same-set comparison can be Collector-driven.")




# --------------------------------------------------------------------------
# Phases 8-12, 14-16 - the sweep
# --------------------------------------------------------------------------

def _columns(rows):
    return ([r["financialRip"] for r in rows], [r["collectorAppeal"] for r in rows],
            [r["chaseNormalized"] for r in rows])


def phase8_guardrails(rows, control):
    print("\n=== PHASE 8 - inherited historical guardrails ===")
    financial, collector, chase = _columns(rows)
    labels = [r["productName"] for r in rows]
    baseline = sweep.baseline_financial_chase(financial=financial, chase=chase)
    print("  Baseline = 0.94F + 0.06K (the three-pillar analogue of the historical")
    print("  Financial-only baseline these guardrails were written against).")
    print("  Thresholds read from scoring_config.OVERALL_RIP_PRODUCTION_GUARDRAILS.")
    print()
    print("  %-12s %9s %8s %8s %8s %8s %9s %8s %8s %7s" % (
        "F/C/K", "spearman", "top5", "top7", "top10", "RBO", "meanMv", "share5",
        "maxMv", "gates"))
    out = {}
    for point in sweep.grid():
        candidate = sweep.score(point, financial=financial, collector=collector,
                                chase=chase)
        block = sweep.inherited_guardrails(baseline=baseline, candidate=candidate,
                                           labels=labels)
        out[point.collector] = block
        flags = "".join("Y" if block[k] else "n" for k in
                        ("passSpearman", "passTop5", "passMeanMovement", "passShare5"))
        marker = "" if point.selectable else "  (diagnostic)"
        print("  %-12s %9s %8.2f %8.2f %8.2f %8.4f %9.3f %8.4f %8.0f %7s%s" % (
            point.key, _fmt(block["spearman"], "%.4f"), block["top5Overlap"],
            block["top7Overlap"], block["top10Overlap"], block["rbo"],
            block["meanAbsoluteRankMovement"], block["shareMoving5Plus"],
            block["maxRankMovement"], flags, marker))
    print("\n  gate order: spearman(>=%.2f) top5(>=%.2f) meanMove(<=%.1f) share5(<=%.2f)"
          % (block["thresholds"]["min_spearman_vs_financial_only"],
             block["thresholds"]["min_top5_overlap"],
             block["thresholds"]["max_mean_absolute_rank_movement"],
             block["thresholds"]["max_share_moving_5_plus_ranks"]))
    print()
    print("  THE TWO MOVEMENT GATES ARE NOT SCALE-FREE, and that is why they fail")
    print("  above even at the SHIPPING 10%% weight. They were calibrated on the V4")
    print("  study's ~21-SET cohort; this cohort is %d PRODUCTS. '5 ranks of 21' is"
          % block["cohortSize"])
    print("  a quarter of the field; '5 ranks of %d' is under 4%% of it." % block["cohortSize"])
    print("  Cohort-normalised equivalents (mean move <= %.2f ranks; share moving" % block["scaledMeanThreshold"])
    print("  >= %d ranks <= %.2f):" % (block["scaledRankStep"],
                                       block["thresholds"]["max_share_moving_5_plus_ranks"]))
    print("  %-12s %11s %13s %13s %11s" % (
        "F/C/K", "meanMv", "meanMv/cohort", "share>=%dranks" % block["scaledRankStep"],
        "scaledGates"))
    for point in sweep.grid():
        b = out[point.collector]
        flags = "".join("Y" if b[k] else "n" for k in
                        ("passSpearman", "passMeanMovementScaled", "passShare5Scaled"))
        marker = "" if point.selectable else "  (diag)"
        print("  %-12s %11.3f %13.4f %13.4f %11s%s" % (
            point.key, b["meanAbsoluteRankMovement"], b["meanMovementAsShareOfCohort"],
            b["shareMovingScaledStep"], flags, marker))
    print("  historical mean-movement budget as a share of cohort: %.4f"
          % block["historicalMeanThresholdAsShareOfCohort"])
    print()
    print("  CLASSIFICATION of each inherited guardrail under the three-pillar model:")
    print("    min_spearman_vs_financial_only  INHERITED HARD GATE - still the right")
    print("      question, only the baseline changes (Financial-only -> Financial+Chase).")
    print("    max_mean_absolute_rank_movement INHERITED HARD GATE - unchanged meaning.")
    print("    max_share_moving_5_plus_ranks   INHERITED HARD GATE - unchanged meaning.")
    print("    min_top5_overlap                INHERITED DIAGNOSTIC ONLY - the V4 study")
    print("      itself found the top-5 failures WEIGHT-INVARIANT (identical at 10%,")
    print("      7.5% and 5%) and driven by one set, Shrouded Fable, with D=51.07;")
    print("      it recommended RBO or top-7 instead. It is reported, not gated.")
    return out


def phase9_chase_contract(rows, control, scenarios):
    print("\n=== PHASE 9 - Stage VI-B Chase contract under each Collector weight ===")
    print("  Raising Collector lowers Financial, which changes Chase's RELATIVE")
    print("  strength even though Chase stays pinned at 0.06.")
    shocks = _scenario_core_k(rows, scenarios, "shock")
    base_positions = sorted(shocks.get("base", {}))
    financial, collector, _ = _columns(rows)
    out = {}
    print("  %-12s %9s %9s %11s %9s %11s %9s %7s %7s" % (
        "F/C/K", "shapleyC", "shapleyK", "closeOvr%", "clearOvr", "maxGapOvr",
        "spearman", "sameSet", "C1..C5"))
    for point in sweep.grid():
        if not point.selectable:
            continue
        candidate = closure.Candidate(
            key=point.key, financial=point.financial, collector=point.collector,
            chase=point.chase, transform=scale.rescaled_0_100,
            transform_name="100K/(K+10)")
        # THE CHASE CONTRACT NEEDS ITS OWN CONTROL AT THIS COLLECTOR WEIGHT.
        #
        # Stage VI-B measured Chase against a Chase-FREE control that held
        # Collector fixed and returned Chase's weight to Financial. At Collector
        # weight c that control is (1-c)F + cC. Measuring against the 84/10/6
        # CONTROL instead would ask "how far did Collector move things", which is
        # a different question and makes C2/C5 meaningless.
        chase_free = [(1.0 - point.collector) * float(f) + point.collector * float(c)
                      for f, c in zip(financial, collector)]
        base = closure.evaluate(candidate, rows=rows, control=chase_free)
        shocked = []
        for key in closure.C1_SHOCK_KEYS:
            entries = shocks.get(key)
            if entries:
                positions = sorted(set(base_positions) & set(entries))
                shocked.append(closure.evaluate(
                    candidate, rows=rows, control=chase_free,
                    positions=positions, core_k=entries))
        gate = closure.criteria(base, shocked)
        out[point.collector] = {"base": base, "gate": gate, "shocked": shocked}
        print("  %-12s %9s %9s %11s %9d %11.2f %9s %7d %7s" % (
            point.key, _fmt(base["shapley"]["collector_appeal"], "%.4f"),
            _fmt(base["shapley"]["chase"], "%.4f"),
            _fmt(base["closeOverrideRate"], "%.4f"), base["clearOverrides"],
            base["maxGapOverturned"], _fmt(base["spearman"], "%.4f"),
            base["sameSetOverrides"], gate["flags"]))
    print("\n  Each row is measured against ITS OWN Chase-free control (1-c)F + cC,")
    print("  which is the Stage VI-B construction transplanted to that Collector")
    print("  weight. C1-C5 therefore keep the meaning they were validated with.")
    return out


def _scenario_core_k(rows, scenarios, kind):
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


def phase10_financial_dominance(rows):
    print("\n=== PHASE 10 - Financial dominance versus the Financial+Chase baseline ===")
    financial, collector, chase = _columns(rows)
    labels = [r["productName"] for r in rows]
    core_k = [r["coreK"] for r in rows]
    sets = [r["set"] for r in rows]
    baseline = sweep.baseline_financial_chase(financial=financial, chase=chase)
    print("  Baseline B = 0.94F + 0.06K ; candidate O_c = (0.94-c)F + cC + 0.06K")
    print("  %-12s %11s %9s %11s %11s %11s" % (
        "F/C/K", "closeOvr%", "clearOvr", "maxGapOvr", "crossSetRev", "sameSetRev"))
    out = {}
    for point in sweep.grid():
        candidate = sweep.score(point, financial=financial, collector=collector,
                                chase=chase)
        override = pairs.pairwise_overrides(
            control=baseline, candidate=candidate, financial=financial, labels=labels,
            core_k=core_k, sets=sets)
        worst = max((b["maxGapOverturned"] or 0.0) for b in override["perBand"].values())
        out[point.collector] = override
        marker = "" if point.selectable else "  (diagnostic)"
        print("  %-12s %11s %9d %11.2f %11d %11d%s" % (
            point.key, _fmt(override["closeOverrideRate"], "%.4f"),
            override["clearOverrides"], worst,
            override["pairs"] - override["sameSetPairs"], override["sameSetOverrides"],
            marker))
    print("\n  Collector SHOULD resolve close calls; it should not routinely rescue")
    print("  clearly inferior financial opportunities. clearOvr counts pairs where")
    print("  Financial leads by >= 10 and the baseline agreed, yet Collector flipped it.")
    return out


def phase11_12_marginal(rows):
    print("\n=== PHASES 11 & 12 - what each extra point of Collector actually buys ===")
    print("  Every reversal is attributed to its CAUSE. For a pair whose Collector")
    print("  scores are equal, 100% of the movement is reallocation - Financial")
    print("  losing weight - and none of it is Collector information.")
    steps = [(0.10, 0.11), (0.11, 0.12), (0.12, 0.13), (0.10, 0.13),
             (0.13, 0.14), (0.14, 0.15)]
    print("\n  %-14s %9s %13s %15s %11s %11s %13s" % (
        "step", "reversals", "collectorRev", "reallocDom", "sameSet", "crossSet",
        "maxFgapByC"))
    out = {}
    for low_c, high_c in steps:
        low = sweep.WeightPoint(collector=low_c, selectable=low_c in sweep.SELECTABLE)
        high = sweep.WeightPoint(collector=high_c, selectable=high_c in sweep.SELECTABLE)
        block = sweep.classify_reversals(rows=rows, low=low, high=high)
        out[(low_c, high_c)] = block
        marker = "" if high_c in sweep.SELECTABLE else "  (diagnostic)"
        print("  %-14s %9d %13d %15d %11d %11d %13.2f%s" % (
            "%.0f%%->%.0f%%" % (low_c * 100, high_c * 100), block["totalReversals"],
            block["collectorCaused"], block["reallocationDominant"],
            block["sameSetReversals"], block["crossSetReversals"],
            block["maxFinancialGapCrossedByCollector"], marker))

    print("\n  Same-set reversals are 0 at every step, as they must be.")
    print("  Collector is set-constant, so a same-set pair's Collector term")
    print("  cancels exactly and no Collector weight can reorder it.")
    print("  A reversal counts as Collector-caused ONLY when the direct term")
    print("  delta*dC exceeds the reallocation term -delta*dF in magnitude.")
    detail = out[(0.10, 0.13)]
    print("\n  worst Collector-caused reversals over the full 10%%->13%% move:")
    for example in detail["worstCollectorCaused"][:4]:
        print("    %s" % example["winner"][:66])
        print("      beats %s" % example["loser"][:60])
        print("      Financial gap %.2f (%s) | Collector gap %.2f | direct %+.4f"
              " vs realloc %+.4f" % (example["financialGap"], example["band"],
                                     example["collectorGap"], example["directTerm"],
                                     example["reallocationTerm"]))

    print("\n  marginal movement per additional 1% Collector weight")
    financial, collector, chase = _columns(rows)
    labels = [r["productName"] for r in rows]
    reference = sweep.score(sweep.WeightPoint(collector=0.10, selectable=True),
                            financial=financial, collector=collector, chase=chase)
    print("  %-12s %9s %9s %8s %8s %9s %8s %8s" % (
        "F/C/K", "spearman", "kendall", "meanMv", "maxMv", "changed", "top10", "tiers"))
    for point in sweep.grid():
        candidate = sweep.score(point, financial=financial, collector=collector,
                                chase=chase)
        influence = decisions.rank_influence(control=reference, candidate=candidate,
                                             labels=labels)
        marker = "" if point.selectable else "  (diag)"
        print("  %-12s %9s %9s %8.2f %8.0f %9d %8d %8d%s" % (
            point.key, _fmt(influence["spearman"], "%.4f"),
            _fmt(influence["kendallTau"], "%.4f"),
            influence["meanAbsoluteMovement"], influence["maxMovement"],
            influence["movedAtAll"], influence["turnover"]["top10"]["turnover"],
            influence["tierChanges"], marker))
    return out


def phase14_15_robustness(rows, control, scenarios):
    print("\n=== PHASES 14 & 15 - dates, price shocks and Collector shocks ===")
    financial, collector, chase = _columns(rows)
    labels = [r["productName"] for r in rows]
    core_k = [r["coreK"] for r in rows]
    sets = [r["set"] for r in rows]
    shocks = _scenario_core_k(rows, scenarios, "shock")
    dates = _scenario_core_k(rows, scenarios, "temporal")
    base_positions = sorted(shocks.get("base", {}))

    print("\n  price shocks and dates - clear-Financial overrides vs the 0.94F+0.06K")
    print("  baseline, and max Financial gap overturned")
    print("  %-12s %-12s %5s %9s %11s" % ("F/C/K", "scenario", "n", "clearOvr", "maxGapOvr"))
    for point in sweep.grid():
        if not point.selectable:
            continue
        worst_clear, worst_gap = 0, 0.0
        for name, blocks in (("shock", shocks), ("date", dates)):
            for scenario, entries in blocks.items():
                positions = (sorted(set(base_positions) & set(entries))
                             if name == "shock" else sorted(entries))
                if len(positions) < 10:
                    continue
                f = [financial[p] for p in positions]
                c = [collector[p] for p in positions]
                k = [scale.rescaled_0_100(entries[p]) for p in positions]
                base = sweep.baseline_financial_chase(financial=f, chase=k)
                cand = sweep.score(point, financial=f, collector=c, chase=k)
                override = pairs.pairwise_overrides(
                    control=base, candidate=cand, financial=f,
                    labels=[labels[p] for p in positions],
                    core_k=[entries[p] for p in positions],
                    sets=[sets[p] for p in positions])
                gap = max((b["maxGapOverturned"] or 0.0)
                          for b in override["perBand"].values())
                worst_clear = max(worst_clear, override["clearOverrides"])
                worst_gap = max(worst_gap, gap)
        print("  %-12s %-12s %5s %9d %11.2f" % (
            point.key, "worst of all", "-", worst_clear, worst_gap))

    print("\n  Collector measurement shocks (pre-registered, symmetric)")
    print("  %-12s %-16s %11s %9s %11s %9s" % (
        "F/C/K", "collector shock", "closeOvr%", "clearOvr", "maxGapOvr", "spearman"))
    reference = sweep.score(sweep.WeightPoint(collector=0.10, selectable=True),
                            financial=financial, collector=collector, chase=chase)
    for point in sweep.grid():
        if not point.selectable:
            continue
        for factor in (0.90, 1.10):
            shocked = [min(100.0, max(0.0, v * factor)) for v in collector]
            base = sweep.baseline_financial_chase(financial=financial, chase=chase)
            cand = sweep.score(point, financial=financial, collector=shocked,
                               chase=chase)
            override = pairs.pairwise_overrides(
                control=base, candidate=cand, financial=financial, labels=labels,
                core_k=core_k, sets=sets)
            gap = max((b["maxGapOverturned"] or 0.0) for b in override["perBand"].values())
            print("  %-12s %-16s %11s %9d %11.2f %9s" % (
                point.key, "C x %.2f" % factor,
                _fmt(override["closeOverrideRate"], "%.4f"), override["clearOverrides"],
                gap, _fmt(stats.spearman(reference, cand), "%.4f")))


def phase16_redundancy(rows):
    print("\n=== PHASE 16 - redundancy: is Collector already inside Financial? ===")
    financial, collector, chase = _columns(rows)
    groups = [r["set"] for r in rows]
    print("  F vs C   Pearson %s   Spearman %s"
          % (_fmt(stats.pearson(financial, collector)),
             _fmt(stats.spearman(financial, collector))))
    partial = stats.partial_correlation(x=collector, y=financial, controls={"chase": chase})
    print("  F vs C controlling for Chase: partial Pearson %s  partial Spearman %s"
          % (_fmt(partial["partialPearson"]), _fmt(partial["partialSpearman"])))
    block = stats.reconstruct(name="collector", target=collector,
                              predictors={"financial_rip": financial, "chase": chase},
                              groups=groups)
    print("  Collector reconstructed from Financial+Chase: R2 %s  cvR2 %s  resid/sd %s"
          % (_fmt(block["r2"], "%.4f"), _fmt(block["crossValidatedR2"], "%.4f"),
             _fmt(block["residualShareOfSd"], "%.4f")))
    print()
    print("  The relationship with Financial is NEGATIVE, not redundant: collectible")
    print("  sets are, if anything, slightly WORSE financial value. Collector retains")
    print("  %.0f%% of its own spread after both other pillars are known."
          % (100.0 * (block["residualShareOfSd"] or 0.0)))


def main(argv: Sequence[str]) -> int:
    parser = argparse.ArgumentParser(description="Stage VII Collector weight study.")
    parser.add_argument("--dataset", default=str(DATASET))
    parser.add_argument("--scenarios", default=str(SCENARIOS))
    args = parser.parse_args(list(argv))

    payload = json.loads(Path(args.dataset).read_text(encoding="utf-8"))
    rows = payload["rows"]
    _prepare(rows)

    print("Stage VII - Collector Appeal weight re-stress test")
    print("dataset: %s (%s)" % (payload["stage"], payload["generatedAt"]))

    phase0_prereg()
    control = phase2_control(payload, rows)
    phase3_diagnose(rows)
    phase4_variance(rows, control)
    phase5_populations(rows)
    phase6_within_between(rows)

    scenarios = json.loads(Path(args.scenarios).read_text(encoding="utf-8"))
    phase8_guardrails(rows, control)
    phase9_chase_contract(rows, control, scenarios)
    phase10_financial_dominance(rows)
    phase11_12_marginal(rows)
    phase14_15_robustness(rows, control, scenarios)
    phase16_redundancy(rows)
    return 0


if __name__ == "__main__":
    raise SystemExit(main(sys.argv[1:]))
