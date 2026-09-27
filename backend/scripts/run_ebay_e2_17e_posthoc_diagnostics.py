"""Audit whether consumed cohorts can be scored under frozen LANGUAGE-v2.

Never substitutes a human language label, listing title, or prior OCR version
for missing provider getItem aspects or frozen OCR-v3 predictions.
"""
from __future__ import annotations

import csv
import json
from pathlib import Path

OUT = Path(__file__).resolve().parents[1] / "artifacts/index_fair_value"


def diagnostic(out: Path = OUT) -> dict:
    if not ((out / "ebay_e2_17e_language_v2_freeze_manifest.json").exists() and
            (out / "ebay_e2_17e_combined_identity_v4_freeze_manifest.json").exists()):
        raise RuntimeError("E2.17E policy freezes must precede historical post-hoc work")
    e214 = json.loads((out / "ebay_e2_14_fresh_blind_certification.json").read_text(encoding="utf-8"))
    old = json.loads((out / "ebay_combined_identity_v3_prospective_diagnostic.json").read_text(encoding="utf-8"))
    queue = list(csv.DictReader((out / "ebay_e2_13_fresh_blind_queue.csv").open(encoding="utf-8", newline="")))
    key = next(row for row in queue if row["benchmark_row_id"] == "E13-0127")
    result = {
        "classification": "HISTORICAL_POST_HOC_NON_CERTIFYING",
        "status": "BLOCKED_MISSING_RETAINED_LANGUAGE_V2_INPUTS",
        "reason": "The retained E2.14/V4/V5/E2.9B artifacts lack per-row getItem localizedAspects and frozen OCR-v3 predictions. Reusing human language labels or titles as provider evidence would be invalid.",
        "e214_key_row": {"row_id": "E13-0127", "listing_item_id": key["listing_item_id"],
                          "human_language_review": key["language"],
                          "provider_language_aspect": None, "ocr_v3_state": None,
                          "language_v2_state": "UNSCORABLE", "combined_v4_state": "UNSCORABLE"},
        "e214_v2_baseline_not_v4": {**e214["metrics"],
                                    "card_coverage_count": e214["card_coverage_detail"]["covered_count"],
                                    "catastrophic_false_accepts": e214["false_accept_rows"]},
        "prior_v3_diagnostics_not_v4": old["results"],
        "e214_v4": None,
        "v4_v5_e29b_v4": None,
        "new_blind_capture_justified": False,
        "blocked_gates": ["E13-0127 rejection unverified", "E2.14 v4 false accepts unmeasured",
                          "E2.14 v4 Wilson lower unmeasured", "E2.14 v4 coverage unmeasured",
                          "newly rejected human-YES rows unmeasured"],
    }
    return result


if __name__ == "__main__":
    result = diagnostic()
    (OUT / "ebay_e2_17e_posthoc_diagnostics.json").write_text(
        json.dumps(result, indent=2, ensure_ascii=False) + "\n", encoding="utf-8")
    print(result["status"])
