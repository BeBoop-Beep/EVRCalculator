"""EBAY_E2_11 Phase H -- development-only comparison of D3-v5 vs candidate
D3-v6 across V4, V5, and the consumed E2.9B cohort. NON-CERTIFYING.
"""
from __future__ import annotations

import csv
import json
from collections import Counter
from typing import Any

from backend.scripts import ebay_d3_matcher_v5 as v5
from backend.scripts import ebay_d3_matcher_v6 as v6
from backend.scripts.ebay_gold_access import OUT

SOURCES = {
    "V4": OUT / "ebay_d3_v4_fresh_blind_queue.csv",
    "V5": OUT / "ebay_d3_v5_fresh_blind_queue.csv",
    "E2.9B": OUT / "ebay_e2_9b_fresh_blind_queue.csv",
}
OUTPUT_PATH = OUT / "ebay_d3_v6_development_metrics.json"


def _target_dict(row: dict[str, Any]) -> dict[str, Any]:
    return {"card_name": row["target_card_name"], "set_name": row["target_set_name"],
            "card_number": row["target_card_number"], "treatment": row["target_treatment"],
            "canonical_card_id": row["canonical_card_id"]}


def _listing_dict(row: dict[str, Any]) -> dict[str, Any]:
    return {"title": row["listing_title"], "condition": row["condition"], "conditionId": row["condition_id"],
            "category": row.get("category_id") or "", "aspects": "[]",
            "buying_options": row.get("buying_options_json") or "[]", "itemId": row["listing_item_id"]}


def compare_cohort(name: str, path) -> dict[str, Any]:
    rows = list(csv.DictReader(open(path, encoding="utf-8")))
    transitions = Counter()
    new_high_confidence_yes = []
    new_high_confidence_no = []
    new_rejected_yes = []
    new_rejected_no = []

    for row in rows:
        human = row["exact_match_yes_no_uncertain"]
        if human not in ("YES", "NO"):
            continue
        target = _target_dict(row)
        listing = _listing_dict(row)
        v5_result = v5.classify_listing(target, listing)
        v6_result = v6.classify_listing(target, listing)
        v5_state, v6_state = v5_result["identity_state"], v6_result["identity_state"]
        transitions[(v5_state, v6_state)] += 1

        if v5_state != "HIGH_CONFIDENCE" and v6_state == "HIGH_CONFIDENCE":
            (new_high_confidence_yes if human == "YES" else new_high_confidence_no).append(row["benchmark_row_id"])
        if v5_state != "REJECTED" and v6_state == "REJECTED":
            (new_rejected_yes if human == "YES" else new_rejected_no).append(row["benchmark_row_id"])

    return {
        "cohort": name,
        "row_count": len(rows),
        "reason_code_transitions": {f"{a}->{b}": c for (a, b), c in transitions.items() if a != b},
        "new_high_confidence_rows": {
            "true_positive_rows": new_high_confidence_yes, "false_positive_rows": new_high_confidence_no,
            "count_yes": len(new_high_confidence_yes), "count_no": len(new_high_confidence_no),
        },
        "new_rejected_rows": {
            "correctly_rejected_no_rows": new_rejected_no, "incorrectly_rejected_yes_rows": new_rejected_yes,
            "count_no": len(new_rejected_no), "count_yes": len(new_rejected_yes),
        },
    }


def main() -> dict[str, Any]:
    results = {name: compare_cohort(name, path) for name, path in SOURCES.items()}
    total_new_false_accepts = sum(r["new_high_confidence_rows"]["count_no"] for r in results.values())
    total_new_recall_gain = sum(r["new_high_confidence_rows"]["count_yes"] for r in results.values())
    total_new_false_rejects = sum(r["new_rejected_rows"]["count_yes"] for r in results.values())
    total_new_correct_rejects = sum(r["new_rejected_rows"]["count_no"] for r in results.values())

    output = {
        "label": "EBAY_D3_V6_DEVELOPMENT_METRICS_NON_CERTIFYING",
        "text_matcher_v5_fingerprint": v5.rule_fingerprint(),
        "text_matcher_v6_fingerprint": v6.rule_fingerprint(),
        "results": results,
        "summary": {
            "new_high_confidence_true_positives": total_new_recall_gain,
            "new_high_confidence_false_positives": total_new_false_accepts,
            "new_rejected_correct_no_rows": total_new_correct_rejects,
            "new_rejected_incorrect_yes_rows": total_new_false_rejects,
        },
    }
    OUTPUT_PATH.write_text(json.dumps(output, indent=2, ensure_ascii=False) + "\n", encoding="utf-8")
    return output


if __name__ == "__main__":
    print(json.dumps(main(), indent=2))
