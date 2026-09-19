"""EBAY_E2_10 -- POST-HOC, NON-CERTIFYING coverage-failure forensics for the
CONSUMED, NOT-CERTIFIED E2.9B fresh blind cohort under COMBINED-IDENTITY-v2.

Reads only the already-frozen Phase-1 prediction artifact
(ebay_combined_identity_v2_fresh_blind_predictions.json) and the already
finally-frozen human labels (the E2.9B queue CSV) -- never re-scores, never
re-labels, never modifies either. Produces a per-target-card diagnostic
breakdown used to root-cause the 16 uncovered cards. This is diagnostic
tooling only: it does not implement, certify, or freeze any policy change.
"""
from __future__ import annotations

import json
from collections import defaultdict
from typing import Any

from backend.scripts.ebay_gold_access import OUT
from backend.scripts.ebay_e2_9b_blind_review_server import load_queue_rows

PREDICTIONS_PATH = OUT / "ebay_combined_identity_v2_fresh_blind_predictions.json"
COHORT_PATH = OUT / "ebay_pilot_cohort.json"
OUTPUT_PATH = OUT / "ebay_e2_10_coverage_failure_forensics.json"

TOTAL_TARGET_CARDS = 70


def build_per_card_forensics() -> dict[str, Any]:
    predictions = json.loads(PREDICTIONS_PATH.read_text(encoding="utf-8"))["predictions"]
    rows = {r["benchmark_row_id"]: r for r in load_queue_rows()}
    all_cards = {c["canonical_card_id"]: c for c in json.loads(COHORT_PATH.read_text(encoding="utf-8"))["cards"]}

    per_card: dict[str, dict[str, Any]] = defaultdict(lambda: {
        "represented": False, "row_count": 0, "yes": 0, "no": 0,
        "high_conf_yes": 0, "image_match_yes": 0, "image_unverified_yes": 0, "image_mismatch_yes": 0,
        "tier_a_true": 0, "tier_b_true": 0, "rows": [],
    })

    for row_id, pred in predictions.items():
        row = rows[row_id]
        card_id = pred["canonical_card_id"]
        human = row["exact_match_yes_no_uncertain"]
        d = per_card[card_id]
        d["represented"] = True
        d["row_count"] += 1
        if human == "YES":
            d["yes"] += 1
        elif human == "NO":
            d["no"] += 1
        if pred["text_state"] == "HIGH_CONFIDENCE" and human == "YES":
            d["high_conf_yes"] += 1
        if human == "YES" and pred["image_state"] == "MATCH":
            d["image_match_yes"] += 1
        if human == "YES" and pred["image_state"] == "UNVERIFIED":
            d["image_unverified_yes"] += 1
        if human == "YES" and pred["image_state"] == "MISMATCH":
            d["image_mismatch_yes"] += 1
        if pred["identity_tier"] == "TIER_A" and human == "YES":
            d["tier_a_true"] += 1
        if pred["identity_tier"] == "TIER_B" and human == "YES":
            d["tier_b_true"] += 1
        d["rows"].append({
            "row_id": row_id, "human": human, "text_state": pred["text_state"],
            "text_contradiction": pred["text_contradiction_present"], "image_state": pred["image_state"],
            "tier": pred["identity_tier"], "eligible": pred["eligible"],
            "combined_state": pred["combined_state"], "listing_title": row["listing_title"],
        })

    results = []
    for card_id, c in all_cards.items():
        d = per_card.get(card_id)
        if d is None:
            results.append({
                "canonical_card_id": card_id, "card_name": c["card_name"], "set_name": c["set_name"],
                "represented": False, "row_count": 0, "yes": 0, "no": 0,
                "high_conf_yes": 0, "image_match_yes": 0, "image_unverified_yes": 0, "image_mismatch_yes": 0,
                "tier_a_true": 0, "tier_b_true": 0, "covered": False, "rows": [],
            })
            continue
        covered = (d["tier_a_true"] + d["tier_b_true"]) > 0
        results.append({
            "canonical_card_id": card_id, "card_name": c["card_name"], "set_name": c["set_name"],
            "represented": d["represented"], "row_count": d["row_count"], "yes": d["yes"], "no": d["no"],
            "high_conf_yes": d["high_conf_yes"], "image_match_yes": d["image_match_yes"],
            "image_unverified_yes": d["image_unverified_yes"], "image_mismatch_yes": d["image_mismatch_yes"],
            "tier_a_true": d["tier_a_true"], "tier_b_true": d["tier_b_true"], "covered": covered,
            "rows": d["rows"],
        })

    covered_count = sum(1 for r in results if r["covered"])
    uncovered = [r for r in results if not r["covered"]]

    output = {
        "label": "EBAY_E2_10_COVERAGE_FAILURE_FORENSICS_NON_CERTIFYING",
        "note": "Post-hoc diagnostic only. Reads frozen predictions + frozen labels; "
                "never re-scores, never re-labels, never certifies.",
        "total_target_cards": TOTAL_TARGET_CARDS,
        "covered_count": covered_count,
        "uncovered_count": len(uncovered),
        "per_card": results,
    }
    OUTPUT_PATH.write_text(json.dumps(output, indent=2, ensure_ascii=False) + "\n", encoding="utf-8")
    return output


if __name__ == "__main__":
    result = build_per_card_forensics()
    print(json.dumps({k: v for k, v in result.items() if k != "per_card"}, indent=2))
