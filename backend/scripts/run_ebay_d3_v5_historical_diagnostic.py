"""HISTORICAL_POST_HOC_DIAGNOSTIC only -- NOT a certification.

Runs the already-frozen D3-v5 against the already-consumed 420-row V4 blind
cohort, purely to see whether the two known catastrophic errors (and overall
metrics) change. This may NOT trigger any further v5 revision in this task;
a changed v5 would require a new freeze and a genuinely new blind cohort.
"""
from __future__ import annotations

import json

from backend.scripts import ebay_d3_matcher_v4 as v4
from backend.scripts import ebay_d3_matcher_v5 as v5
from backend.scripts.certify_ebay_d3_v4_fresh_blind import (
    apply_gates,
    classify_human_label,
    compute_certification_metrics,
    load_queue_rows,
)
from backend.scripts.ebay_gold_access import OUT

DESIGN_PATH = OUT / "ebay_d3_new_blind_benchmark_design.json"
OUTPUT_PATH = OUT / "ebay_d3_v5_historical_post_hoc_diagnostic.json"


def main() -> dict:
    rows = load_queue_rows()  # the FROZEN, consumed 420-row V4 cohort -- read-only
    design = json.loads(DESIGN_PATH.read_text(encoding="utf-8"))

    v4_metrics = compute_certification_metrics(v4, rows)
    v5_metrics = compute_certification_metrics(v5, rows)
    v4_gates = apply_gates(v4_metrics, design)
    v5_gates = apply_gates(v5_metrics, design)

    v4_error_ids = {e["benchmark_row_id"] for e in v4_metrics["error_rows"]}
    v5_error_ids = {e["benchmark_row_id"] for e in v5_metrics["error_rows"]}

    result = {
        "version": "ebay_d3_v5_historical_post_hoc_diagnostic_v1",
        "status": "HISTORICAL_POST_HOC_DIAGNOSTIC",
        "certifying": False,
        "note": "This cohort is CONSUMED and permanently ineligible to certify any matcher. "
                "This run exists only to report whether the two known catastrophic errors persist "
                "under v5; it does not pass/fail v5 and must not trigger further tuning.",
        "v4_recomputed_on_consumed_cohort": {
            "accepted_precision": v4_metrics["accepted_precision"],
            "catastrophic_false_accept_total": v4_metrics["catastrophic_false_accept_total"],
            "error_rows": v4_metrics["error_rows"],
            "gates": v4_gates["gates"], "overall_result": v4_gates["overall_result"],
        },
        "v5_on_consumed_cohort": {
            "accepted_precision": v5_metrics["accepted_precision"],
            "accepted_precision_wilson_95": v5_metrics["accepted_precision_wilson_95"],
            "accepted_recall": v5_metrics["accepted_recall"],
            "acceptance_rate": v5_metrics["acceptance_rate"],
            "card_coverage": v5_metrics["card_coverage"],
            "catastrophic_false_accept_total": v5_metrics["catastrophic_false_accept_total"],
            "error_rows": v5_metrics["error_rows"],
            "gates": v5_gates["gates"], "overall_result": v5_gates["overall_result"],
        },
        "d4_0375_still_a_false_accept_under_v5": "D4-0375" in v5_error_ids,
        "d4_0415_still_a_false_accept_under_v5": "D4-0415" in v5_error_ids,
        "errors_resolved_by_v5": sorted(v4_error_ids - v5_error_ids),
        "errors_persisting_under_v5": sorted(v4_error_ids & v5_error_ids),
        "new_errors_introduced_by_v5": sorted(v5_error_ids - v4_error_ids),
    }
    OUTPUT_PATH.write_text(json.dumps(result, indent=2, ensure_ascii=False) + "\n", encoding="utf-8")
    return result


if __name__ == "__main__":
    print(json.dumps(main(), indent=2, ensure_ascii=False))
