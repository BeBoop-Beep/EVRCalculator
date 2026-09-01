"""Overall RIP V11 Stage VII guardrail reproduction (Phase 23).

READ-ONLY. The five pre-registered Stage VI-A/VI-B gates C1-C5, re-run against
the PRODUCTION 83/11/6 weights and the PRODUCTION Chase transform.

The measuring instrument is the unchanged Stage VI-A research machinery, so a
difference in verdict cannot come from a difference in the instrument. What is
substituted is only the candidate: production weights from ``scoring_config``
and the production transform from ``chase_opportunity``.
"""

from __future__ import annotations

import json
from collections import defaultdict
from pathlib import Path

from backend.desirability.chase_opportunity import chase_opportunity_score
from backend.desirability.scoring_config import OVERALL_RIP_V11_WEIGHTS
from backend.research.chase_weight_stage6a import closure

DATASET = Path("docs/research/chase_pillar_stage6_dataset.json")
SCENARIOS = Path("docs/research/chase_pillar_stage6_scenarios.json")


def main() -> int:
    rows = json.loads(DATASET.read_text(encoding="utf-8"))["rows"]
    scen = json.loads(SCENARIOS.read_text(encoding="utf-8"))

    production = closure.Candidate(
        key="V11",
        financial=OVERALL_RIP_V11_WEIGHTS["financial_rip"],
        collector=OVERALL_RIP_V11_WEIGHTS["collector_appeal"],
        chase=OVERALL_RIP_V11_WEIGHTS["chase_opportunity"],
        transform=chase_opportunity_score,
        transform_name="100K/(K+10) [production]",
        note="Overall RIP V11 as implemented in backend.desirability",
    )

    # Stage VII section 8: each candidate is measured against ITS OWN Chase-free
    # control, (1 - c) * F + c * C, so C1-C5 keep the meaning they were validated
    # with. For the selected 11% Collector weight that is 0.89F + 0.11C - NOT
    # Overall RIP V10's 0.90/0.10, which holds Collector at a different weight
    # and therefore measures a different question.
    c_weight = OVERALL_RIP_V11_WEIGHTS["collector_appeal"]
    f_weight = 1.0 - c_weight
    control = [
        f_weight * float(r["financialRip"]) + c_weight * float(r["collectorAppeal"])
        for r in rows
    ]
    index = {r["sealedProductId"]: i for i, r in enumerate(rows)}

    by_scenario = defaultdict(dict)
    for obs in scen["observations"]:
        if obs.get("kind") != "shock":
            continue
        pos = index.get(obs["sealedProductId"])
        if pos is not None:
            by_scenario[obs["scenario"]][pos] = int(obs["coreK"])

    base = closure.evaluate(production, rows=rows, control=control)

    print(f"candidate : {production.label}")
    print(f"cohort    : {base['n']} products\n")

    c1_gaps = [("base", base["clearOverrides"], base["maxGapOverturned"])]
    for key in closure.C1_SHOCK_KEYS:
        k = by_scenario.get(key)
        if not k or len(k) != len(rows):
            print(f"  !! shock {key} incomplete ({len(k or {})}/{len(rows)})")
            continue
        r = closure.evaluate(production, rows=rows, control=control, core_k=k)
        c1_gaps.append((key, r["clearOverrides"], r["maxGapOverturned"]))

    worst_gap = max(g for _, _, g in c1_gaps)
    total_clear = sum(c for _, c, _ in c1_gaps)

    c1 = total_clear == 0 and worst_gap < 10.0
    c2 = base["closeOverrideRate"] >= 0.10
    c3 = base["shapley"]["financial_rip"] > 0.80 and base["shapley"]["chase"] < 0.20
    c4 = base["spearman"] >= 0.98 and base["top5Turnover"] <= 1
    c5 = base["sameSetOverrides"] > 0

    for key, clear, gap in c1_gaps:
        print(f"  {key:<10} clear overrides {clear}   max gap {gap:.2f}")
    print()
    print(f"C1 clear==0 & maxgap<10 (base + 4 shocks) : {total_clear} / {worst_gap:.2f}  -> {'PASS' if c1 else 'FAIL'}")
    print(f"C2 close override rate >= 0.10            : {base['closeOverrideRate']:.5f}      -> {'PASS' if c2 else 'FAIL'}")
    print(f"C3 Financial>0.80 Chase<0.20              : {base['shapley']['financial_rip']:.4f} / {base['shapley']['chase']:.4f} -> {'PASS' if c3 else 'FAIL'}")
    print(f"C4 Spearman>=0.98 & Top5 turnover<=1      : {base['spearman']:.4f} / {base['top5Turnover']}   -> {'PASS' if c4 else 'FAIL'}")
    print(f"C5 same-set reversals > 0                 : {base['sameSetOverrides']}          -> {'PASS' if c5 else 'FAIL'}")
    flags = "".join("Y" if x else "N" for x in (c1, c2, c3, c4, c5))
    print(f"\nsame-set WINNER changes (expect 0)        : {base['winnerChanges']}")
    print(f"C1-C5 flags                               : {flags}")
    print("\nGUARDRAILS:", "PASS" if flags == "YYYYY" else "FAIL")
    return 0 if flags == "YYYYY" else 1


if __name__ == "__main__":
    raise SystemExit(main())
