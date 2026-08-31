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
    return 0


if __name__ == "__main__":
    raise SystemExit(main(sys.argv[1:]))
