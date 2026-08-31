"""Stage VI-B: does Candidate A pass its own gate, run directly?

RESEARCH ONLY. Reads the Stage VI artifacts and prints the closure audit.
Writes nothing and touches no production state.

    python -m backend.scripts.report_chase_weight_stage6b

The whole point is that no result here may be inferred from Candidate B. Every
number is recomputed from ``0.84F + 0.10C + 0.06 * 100K/(K+10)``.
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
from backend.research.chase_weight_stage6a import closure, decisions, scale

DATASET = Path("docs/research/chase_pillar_stage6_dataset.json")
SCENARIOS = Path("docs/research/chase_pillar_stage6_scenarios.json")


def _fmt(value: Optional[float], spec: str = "%+.4f") -> str:
    return "-" if value is None else spec % value


def phase5_control(payload, rows) -> List[float]:
    print("\n=== PHASE 5 - CONTROL reproduction (gate) ===")
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
    print("  CONTROL = %s" % payload["canonicalVersions"]["overallRip"])
    print("  re-derived through compute_overall_rip_v10: %d/%d mismatches, "
          "worst |delta| %.2e" % (mismatches, len(rows), worst))
    if mismatches:
        print("\n  STAGE6B_BLOCKED_CONTROL_REPRODUCTION_FAILURE")
        raise SystemExit(2)
    return [float(r["overallControl"]) for r in rows]


def phase1_what_was_tested() -> None:
    print("\n=== PHASE 1 - what the Stage VI-A 0.03 row actually evaluated ===")
    print("  Traced in backend/scripts/report_chase_weight_stage6a.py:")
    print("    line  34: TRANSFORM = scale.approved_unclamped        # = 200K/(K+10)")
    print("    _chase_column(rows) -> [TRANSFORM(r['coreK']) for r in rows]")
    print("    phase19: weight_set = {'financial_rip': 0.90 - share,")
    print("                           'collector_appeal': 0.10, 'chase': share}")
    print("    weights.chase_grid(): 'financial_rip': financial - share")
    print()
    print("  Financial was therefore ALWAYS assigned 1 - 0.10 - chase, and the")
    print("  Chase column was ALWAYS the 200-scale transform. The reported 0.03")
    print("  row is:")
    print("      0.87F + 0.10C + 0.03 * 200K/(K+10)      == CANDIDATE B")
    print()
    print("  Candidate A (0.84F + 0.10C + 0.06 * 100K/(K+10)) appears in Stage VI-A")
    print("  only in a one-off base-cohort command reported in the Phase-13 table.")
    print("  It was NOT run through phase16 (shocks), phase17 (dates) or phase19")
    print("  (the C1-C5 gate). Every C1-C5 verdict in the Stage VI-A report is a")
    print("  verdict on Candidate B.")


def phase2_algebra(rows, control) -> None:
    print("\n=== PHASE 2 - algebraic equivalence audit ===")
    financial = [float(r["financialRip"]) for r in rows]
    a = closure.CANDIDATE_A
    b = closure.CANDIDATE_B
    print("  S = 100K/(K+10) ; T = 200K/(K+10) = 2S")
    print("  A = %.2fF + %.2fC + %.2fS" % (a.financial, a.collector, a.chase))
    print("  B = %.2fF + %.2fC + %.2fT = %.2fF + %.2fC + %.2fS"
          % (b.financial, b.collector, b.chase, b.financial, b.collector, b.chase * 2))
    difference = closure.analytic_difference(financial=financial, left=a, right=b)
    print("  closed form: %s" % difference["expression"])
    print("  => the Chase TERM is identical; the FINANCIAL coefficient differs by "
          "%.2f" % difference["financialCoefficient"])

    core_k = [r["coreK"] for r in rows]
    scores_a = a.score(financial=financial,
                       collector=[r["collectorAppeal"] for r in rows], core_k=core_k)
    scores_b = b.score(financial=financial,
                       collector=[r["collectorAppeal"] for r in rows], core_k=core_k)
    observed = np.asarray([scores_b[i] - scores_a[i] for i in range(len(rows))])
    predicted = np.asarray(difference["predicted"])
    residual = float(np.max(np.abs(observed - predicted)))

    print("\n  observed B - A across the cohort")
    print("    min %.6f  median %.6f  mean %.6f  max %.6f  sd %.6f"
          % (observed.min(), float(np.median(observed)), observed.mean(),
             observed.max(), observed.std(ddof=1)))
    print("    identity residual vs 0.03*F: max |observed - predicted| = %.3e"
          % residual)
    print("    machine-precision agreement: %s" % (residual < 1e-12))
    print()
    print("  CONCLUSION: 'equivalent' is true only of Chase contribution strength.")
    print("  A and B are NOT equivalent Overall RIP formulas. B scores every")
    print("  product higher by 0.03 x its Financial RIP, i.e. %.3f to %.3f points."
          % (observed.min(), observed.max()))


def phase3_a_vs_b(rows, control) -> None:
    print("\n=== PHASE 3 - direct A vs B comparison ===")
    financial = [float(r["financialRip"]) for r in rows]
    collector = [float(r["collectorAppeal"]) for r in rows]
    core_k = [r["coreK"] for r in rows]
    labels = [r["productName"] for r in rows]
    a = closure.CANDIDATE_A.score(financial=financial, collector=collector,
                                  core_k=core_k)
    b = closure.CANDIDATE_B.score(financial=financial, collector=collector,
                                  core_k=core_k)

    influence = decisions.rank_influence(control=a, candidate=b, labels=labels)
    print("  ordering")
    print("    Spearman %s | Kendall tau %s"
          % (_fmt(influence["spearman"], "%.6f"), _fmt(influence["kendallTau"], "%.6f")))
    print("    products whose ordinal position changes: %d/%d"
          % (influence["movedAtAll"], len(rows)))
    print("    movement: median %.1f  mean %.2f  max %.0f"
          % (influence["medianAbsoluteMovement"], influence["meanAbsoluteMovement"],
             influence["maxMovement"]))
    print("    pairwise ordering disagreements: %d" % influence["pairwiseInversions"])

    same_set = 0
    participants = set()
    for i in range(len(rows)):
        for j in range(i + 1, len(rows)):
            if (a[i] - a[j]) * (b[i] - b[j]) < 0:
                participants.add(i)
                participants.add(j)
                if rows[i]["set"] == rows[j]["set"]:
                    same_set += 1
    print("    same-set pairwise disagreements: %d" % same_set)
    print("    products participating in a disagreement: %d" % len(participants))

    by_set: Dict[str, List[int]] = {}
    for index, row in enumerate(rows):
        by_set.setdefault(row["set"], []).append(index)
    differing = []
    multi = 0
    for name, members in sorted(by_set.items()):
        if len(members) < 2:
            continue
        multi += 1
        win_a = max(members, key=lambda i: a[i])
        win_b = max(members, key=lambda i: b[i])
        if win_a != win_b:
            differing.append((name, rows[win_a]["productName"], rows[win_b]["productName"]))
    print("\n  same-set winners: %d/%d differ" % (len(differing), multi))
    for name, left, right in differing:
        print("    %s: A -> %s | B -> %s" % (name, left, right))

    print("\n  top/bottom sensitivity (membership vs ordering)")
    rank_a = stats.rank([-v for v in a])
    rank_b = stats.rank([-v for v in b])
    for size in (10, 25):
        for label, ranks in (("top", None), ("bottom", None)):
            if label == "top":
                set_a = {labels[i] for i in np.argsort(rank_a)[:size]}
                set_b = {labels[i] for i in np.argsort(rank_b)[:size]}
                order_a = [labels[i] for i in np.argsort(rank_a)[:size]]
                order_b = [labels[i] for i in np.argsort(rank_b)[:size]]
            else:
                set_a = {labels[i] for i in np.argsort(rank_a)[-size:]}
                set_b = {labels[i] for i in np.argsort(rank_b)[-size:]}
                order_a = [labels[i] for i in np.argsort(rank_a)[-size:]]
                order_b = [labels[i] for i in np.argsort(rank_b)[-size:]]
            print("    %-7s %2d : membership changes %d | ordering identical %s"
                  % (label, size, size - len(set_a & set_b), order_a == order_b))

    print("\n  tier effects (production leader curve, as Stage VI-A used it)")
    print("    tier changes A -> B: %d" % influence["tierChanges"])
    for change in influence["tierChangeDetail"][:6]:
        print("      %-52s %s -> %s" % (change["label"][:52], change["from"], change["to"]))


def phase6_semantics(rows) -> None:
    print("\n=== PHASE 6 - Chase score semantics for S = 100K/(K+10) ===")
    checks = [(0, 0.0), (1, 100.0 / 11), (10, 50.0)]
    for k, expected in checks:
        got = scale.rescaled_0_100(k)
        print("    K=%-3d -> %9.4f  (expected %9.4f) %s"
              % (k, got, expected, "OK" if abs(got - expected) < 1e-9 else "MISMATCH"))
    monotone = all(scale.rescaled_0_100(k) < scale.rescaled_0_100(k + 1)
                   for k in range(0, 400))
    saturating = all(
        (scale.rescaled_0_100(k + 1) - scale.rescaled_0_100(k))
        < (scale.rescaled_0_100(k) - scale.rescaled_0_100(k - 1)) + 1e-12
        for k in range(1, 400))
    print("    strictly monotonic increasing over K=0..400 : %s" % monotone)
    print("    strictly saturating (shrinking increments)  : %s" % saturating)
    print("    finite K always < 100 (K=1e6 -> %.6f)      : %s"
          % (scale.rescaled_0_100(1_000_000),
             scale.rescaled_0_100(1_000_000) < 100.0))
    print("    no clamp is applied anywhere in the transform")

    core_k = [int(r["coreK"]) for r in rows]
    values = [scale.rescaled_0_100(k) for k in core_k]
    print("\n  cohort")
    print("    K   : min %d  max %d  distinct %d"
          % (min(core_k), max(core_k), len(set(core_k))))
    print("    S   : min %.4f  max %.4f  distinct %d"
          % (min(values), max(values), len({round(v, 12) for v in values})))
    print("    distinct S values == distinct K values: %s"
          % (len({round(v, 12) for v in values}) == len(set(core_k))))

    high = sorted({k for k in core_k if k > 10})
    print("\n  the five products the old clamp collapsed (K > 10)")
    for row in sorted((r for r in rows if int(r["coreK"]) > 10),
                      key=lambda r: -int(r["coreK"])):
        k = int(row["coreK"])
        print("    K=%-3d  old clamped T=%6.2f  new S=%7.4f  %s"
              % (k, scale.approved_clamped(k), scale.rescaled_0_100(k),
                 row["productName"][:48]))
    print("    distinct K above 10: %s -> distinct S: %d"
          % (high, len({round(scale.rescaled_0_100(k), 12) for k in high})))
    print("    every one is now separately representable; no clamp-induced ties.")


def _scenario_core_k(rows, scenarios, kind):
    index = {r["sealedProductId"]: i for i, r in enumerate(rows)}
    out: Dict[str, Dict[int, int]] = {}
    for observation in scenarios["observations"]:
        if observation.get("kind") != kind:
            continue
        position = index.get(observation["sealedProductId"])
        if position is None:
            continue
        out.setdefault(observation["scenario"], {})[position] = int(observation["coreK"])
    return out


def phase4_gate(rows, control, scenarios) -> Dict[str, Any]:
    print("\n=== PHASE 4 - the closure test: Candidate A through the C1-C5 gate ===")
    print("  Candidate A = %s" % closure.CANDIDATE_A.label)
    print("  Recomputed directly. Nothing below is derived from Candidate B.")

    results: Dict[str, Any] = {}
    for candidate in (closure.CANDIDATE_A, closure.CANDIDATE_B):
        base = closure.evaluate(candidate, rows=rows, control=control)
        shocks = _scenario_core_k(rows, scenarios, "shock")
        dates = _scenario_core_k(rows, scenarios, "temporal")

        shock_blocks: Dict[str, Any] = {}
        base_positions = sorted(shocks.get("base", {}))
        for key in ("base",) + closure.SHOCK_KEYS:
            entries = shocks.get(key)
            if not entries:
                continue
            positions = sorted(set(base_positions) & set(entries))
            shock_blocks[key] = closure.evaluate(
                candidate, rows=rows, control=control, positions=positions,
                core_k=entries)

        date_blocks: Dict[str, Any] = {}
        for key in sorted(dates):
            entries = dates[key]
            positions = sorted(entries)
            if len(positions) < 10:
                continue
            date_blocks[key] = closure.evaluate(
                candidate, rows=rows, control=control, positions=positions,
                core_k=entries)

        gate = closure.criteria(base, [shock_blocks.get(k) for k in closure.C1_SHOCK_KEYS])
        results[candidate.key] = {"candidate": candidate, "base": base,
                                  "shocks": shock_blocks, "dates": date_blocks,
                                  "gate": gate}

    for key in ("A", "B"):
        block = results[key]
        print("\n  --- Candidate %s : %s ---" % (key, block["candidate"].label))
        print("      %s" % block["candidate"].note)
        gate = block["gate"]
        print("      %-4s %-58s %-26s %10s  %s"
              % ("gate", "threshold", "observed", "margin", "verdict"))
        for name in ("C1", "C2", "C3", "C4", "C5"):
            entry = gate[name]
            print("      %-4s %-58s %-26s %10.4f  %s"
                  % (name, entry["threshold"][:57], str(entry["observed"])[:25],
                     entry["margin"], "PASS" if entry["passed"] else "FAIL"))
        print("      flags %s  -> %s" % (gate["flags"],
                                         "ALL PASS" if gate["allPassed"] else "FAILS"))
    return results


def phase4b_robustness(results) -> None:
    print("\n=== PHASE 4b - Candidate A across every shock and every date ===")
    for key in ("A", "B"):
        block = results[key]
        print("\n  Candidate %s (%s)" % (key, block["candidate"].label))
        print("  %-12s %5s %9s %9s %11s %9s %11s %9s %6s" % (
            "scenario", "n", "shapley", "leverage", "closeOvr%", "clearOvr",
            "maxGapOvr", "spearman", "tiers"))
        for name, blocks in (("shock", block["shocks"]), ("date", block["dates"])):
            for scenario, entry in blocks.items():
                print("  %-12s %5d %9s %9s %11s %9d %11.2f %9s %6d" % (
                    scenario, entry["n"], _fmt(entry["shapley"]["chase"], "%.4f"),
                    _fmt(entry["leverage"], "%.2f"),
                    _fmt(entry["closeOverrideRate"], "%.4f"), entry["clearOverrides"],
                    entry["maxGapOverturned"], _fmt(entry["spearman"], "%.4f"),
                    entry["tierChanges"]))

    print("\n  C1 margin summary - largest Financial gap Chase can overturn")
    print("  %-12s %12s %12s" % ("scenario", "A", "B"))
    keys = ["base"] + list(closure.SHOCK_KEYS)
    for key in keys:
        left = results["A"]["shocks"].get(key)
        right = results["B"]["shocks"].get(key)
        if not left or not right:
            continue
        print("  %-12s %12.2f %12.2f" % (key, left["maxGapOverturned"],
                                         right["maxGapOverturned"]))
    worst_a = max(b["maxGapOverturned"] for b in results["A"]["shocks"].values())
    worst_b = max(b["maxGapOverturned"] for b in results["B"]["shocks"].values())
    print("  worst across all shocks:  A %.2f (margin %.2f)  B %.2f (margin %.2f)"
          % (worst_a, 10.0 - worst_a, worst_b, 10.0 - worst_b))


def phase3b_same_set(results) -> None:
    print("\n=== PHASE 3b - same-set behaviour under each candidate ===")
    print("  %-12s %18s %18s" % ("candidate", "same-set reversals", "winner changes"))
    for key in ("A", "B"):
        base = results[key]["base"]
        print("  %-12s %18d %18d" % (key, base["sameSetOverrides"],
                                     base["winnerChanges"]))


def main(argv: Sequence[str]) -> int:
    parser = argparse.ArgumentParser(description="Stage VI-B closure audit.")
    parser.add_argument("--dataset", default=str(DATASET))
    parser.add_argument("--scenarios", default=str(SCENARIOS))
    args = parser.parse_args(list(argv))

    payload = json.loads(Path(args.dataset).read_text(encoding="utf-8"))
    rows = payload["rows"]
    scenarios = json.loads(Path(args.scenarios).read_text(encoding="utf-8"))

    print("Stage VI-B - Chase weight closure and formula equivalence audit")
    print("dataset:   %s (%s)" % (payload["stage"], payload["generatedAt"]))
    print("scenarios: %s (%d observations)"
          % (scenarios["stage"], scenarios["observationCount"]))

    control = phase5_control(payload, rows)
    phase1_what_was_tested()
    phase2_algebra(rows, control)
    phase3_a_vs_b(rows, control)
    phase6_semantics(rows)
    results = phase4_gate(rows, control, scenarios)
    phase4b_robustness(results)
    phase3b_same_set(results)
    return 0


if __name__ == "__main__":
    raise SystemExit(main(sys.argv[1:]))
