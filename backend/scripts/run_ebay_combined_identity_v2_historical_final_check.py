"""EBAY_E2_9 Phase H: exactly one final historical diagnostic for the
FROZEN COMBINED-IDENTITY-v2 policy, run on the two already-consumed V4/V5
cohorts.

NON-CERTIFYING. This does not re-derive text_state or image_state -- it
re-consumes the exact frozen per-cell (text_state, image_state, human_label)
counts already recorded in
ebay_combined_identity_v1_historical_post_hoc_diagnostic.json (produced by
running the FROZEN D3-v5 and FROZEN IMAGE-v2 against the two consumed blind
cohorts for EBAY_E2_8) and re-classifies each cell under
ebay_combined_identity_policy_v2.combine() instead of v1's combine(). No
threshold in any of the three layers is touched. Per the freeze contract,
this script is run exactly once after freeze; a second run producing
different numbers from the same frozen inputs would itself be a bug, not a
retune.

LIMITATION (recorded explicitly, not silently): the source diagnostic is an
aggregated cross-tab (text_state x image_state x human_label -> count), not
a per-listing record. Card-level coverage for TIER_B and for the combined
(TIER_A + TIER_B) population therefore CANNOT be computed from this input
-- only Tier A's card coverage survives from the original per-row run
(cards_with_true_accept / cards_total in the v1 diagnostic). This script
reports combined card coverage as null/"UNMEASURED", never a guessed
number. See EBAY_E2_9 report Section 12 for what a follow-up measurement
would require.
"""
from __future__ import annotations

import json
import math
from pathlib import Path

from backend.scripts import ebay_combined_identity_policy_v2 as policy_v2
from backend.scripts.ebay_gold_access import OUT

V1_DIAGNOSTIC_PATH = OUT / "ebay_combined_identity_v1_historical_post_hoc_diagnostic.json"
OUTPUT_PATH = OUT / "ebay_combined_identity_v2_historical_final_check.json"

DESIGN_GATE = {
    "high_precision_minimum": 0.99,
    "wilson_95_lower_minimum": 0.98,
    "card_coverage_minimum": 0.80,
    "catastrophic_false_accepts_maximum": 0,
}


def wilson(successes: int, total: int) -> list[float]:
    z = 1.959963984540054
    if not total:
        return [0.0, 0.0]
    p = successes / total
    d = 1 + z * z / total
    c = (p + z * z / (2 * total)) / d
    m = z * math.sqrt(p * (1 - p) / total + z * z / (4 * total * total)) / d
    return [round(c - m, 8), round(c + m, 8)]


def ratio(a: int, b: int) -> float:
    return round(a / b, 8) if b else 0.0


def run_cohort(cohort: str, failure_matrix: list[dict], v1_metrics: dict) -> dict:
    tier_a_true = tier_a_false = 0
    tier_b_true = tier_b_false = 0
    tier_b_false_rows: list[dict] = []
    tier_a_false_rows: list[dict] = []

    for row in failure_matrix:
        result = policy_v2.combine(row["text_state"], row["image_state"])
        human = row["human_label"]
        count = row["count"]

        if result.combined_state == policy_v2.TIER_A_IMAGE_VERIFIED:
            if human == "YES":
                tier_a_true += count
            else:
                tier_a_false += count
                tier_a_false_rows.append({**row, "combined_state_v2": result.combined_state})
        elif result.combined_state == policy_v2.TIER_B_TEXT_VERIFIED_IMAGE_UNVERIFIED:
            if human == "YES":
                tier_b_true += count
            else:
                tier_b_false += count
                tier_b_false_rows.append({**row, "combined_state_v2": result.combined_state})

    tier_a_accepted = tier_a_true + tier_a_false
    tier_b_accepted = tier_b_true + tier_b_false
    combined_accepted = tier_a_accepted + tier_b_accepted
    combined_true = tier_a_true + tier_b_true
    combined_false = tier_a_false + tier_b_false

    tier_a = {
        "accepted_count": tier_a_accepted, "true_accepts": tier_a_true, "false_accepts": tier_a_false,
        "accepted_precision": ratio(tier_a_true, tier_a_accepted),
        "accepted_precision_wilson_95": wilson(tier_a_true, tier_a_accepted),
        "card_coverage": v1_metrics["card_coverage"],
        "cards_with_true_accept": v1_metrics["cards_with_true_accept"],
        "cards_total": v1_metrics["cards_total"],
        "catastrophic_false_accepts": tier_a_false_rows,
        "catastrophic_false_accept_count": len(tier_a_false_rows),
        "note": "identical population to v1 VERIFIED_MATCH -- v2 does not change Tier A's decision rule.",
    }
    tier_b = {
        "accepted_count": tier_b_accepted, "true_accepts": tier_b_true, "false_accepts": tier_b_false,
        "accepted_precision": ratio(tier_b_true, tier_b_accepted),
        "accepted_precision_wilson_95": wilson(tier_b_true, tier_b_accepted),
        "card_coverage": "UNMEASURED_NO_PER_ROW_CARD_JOIN",
        "catastrophic_false_accepts": tier_b_false_rows,
        "catastrophic_false_accept_count": len(tier_b_false_rows),
        "sample_size_caveat": "Wilson interval reported for completeness; not gate-evaluable in isolation per EBAY_E2_9 instructions when it duplicates Tier A's certifying role.",
    }
    combined = {
        "accepted_count": combined_accepted, "true_accepts": combined_true, "false_accepts": combined_false,
        "accepted_precision": ratio(combined_true, combined_accepted),
        "accepted_precision_wilson_95": wilson(combined_true, combined_accepted),
        "card_coverage": "UNMEASURED_NO_PER_ROW_CARD_JOIN",
        "catastrophic_false_accepts": tier_a_false_rows + tier_b_false_rows,
        "catastrophic_false_accept_count": len(tier_a_false_rows) + len(tier_b_false_rows),
    }

    gates = {
        "tier_a_catastrophic_zero": tier_a["catastrophic_false_accept_count"] == 0,
        "tier_b_catastrophic_zero": tier_b["catastrophic_false_accept_count"] == 0,
        "combined_precision_gate": "PASS" if combined_accepted and combined["accepted_precision"] >= DESIGN_GATE["high_precision_minimum"] else ("NOT_EVALUABLE" if not combined_accepted else "FAIL"),
        "combined_wilson_gate": "PASS" if combined_accepted and combined["accepted_precision_wilson_95"][0] >= DESIGN_GATE["wilson_95_lower_minimum"] else ("NOT_EVALUABLE" if not combined_accepted else "FAIL"),
        "combined_coverage_gate": "UNMEASURED",
        "combined_catastrophic_gate": "PASS" if combined["catastrophic_false_accept_count"] == 0 else "FAIL",
        "overall_gate_result": "NOT_READY_COVERAGE_UNMEASURED",
    }

    return {"tier_a": tier_a, "tier_b": tier_b, "combined": combined, "gates": gates}


def main() -> dict:
    v1 = json.loads(V1_DIAGNOSTIC_PATH.read_text(encoding="utf-8"))
    results = {}
    for cohort in ("V4", "V5"):
        cohort_v1 = v1["results"][cohort]
        results[cohort] = run_cohort(cohort, cohort_v1["failure_matrix"], cohort_v1["metrics"])

    output = {
        "label": "COMBINED_IDENTITY_V2_HISTORICAL_FINAL_CHECK_NON_CERTIFYING",
        "policy_version": policy_v2.METHOD_VERSION,
        "source_diagnostic": str(V1_DIAGNOSTIC_PATH.name),
        "results": results,
        "note": (
            "Re-classifies the frozen v1 historical cross-tab under "
            "COMBINED-IDENTITY-v2's decision table. Combined card coverage "
            "is UNMEASURED (not failing) because the source cross-tab is "
            "aggregated, not per-listing; see module docstring."
        ),
    }
    OUTPUT_PATH.write_text(json.dumps(output, indent=2, ensure_ascii=False) + "\n", encoding="utf-8")
    return output


if __name__ == "__main__":
    result = main()
    print(json.dumps(result, indent=2))
