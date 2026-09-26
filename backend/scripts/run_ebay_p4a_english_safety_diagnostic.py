"""Post-hoc diagnostic of English positive evidence against retained E2.x labels."""
from __future__ import annotations

import csv
import json
from collections import Counter
from pathlib import Path

from backend.scripts.ebay_english_price_eligibility_v1 import VERSION, fingerprint

ROOT = Path(__file__).resolve().parents[2]
BASE = ROOT / "backend/artifacts/index_fair_value"
OUT = ROOT / "backend/artifacts/pricing/ebay_p4a_historical_english_safety.json"
COHORTS = (
    ("E2.14", "ebay_e2_18_e2_14_combined_v4_predictions.json", "ebay_e2_13_fresh_blind_queue.csv"),
    ("V4", "ebay_e2_18_v4_combined_v4_predictions.json", "ebay_d3_v4_fresh_blind_queue.csv"),
    ("V5", "ebay_e2_18_v5_combined_v4_predictions.json", "ebay_d3_v5_fresh_blind_queue.csv"),
    ("E2.9B", "ebay_e2_18_e2_9b_combined_v4_predictions.json", "ebay_e2_9b_fresh_blind_queue.csv"),
)


def accepts(row: dict, rule: str) -> bool:
    if row["text_state"] != "HIGH_CONFIDENCE" or row["image_state"] == "MISMATCH":
        return False
    if row["ocr_v3_state"] == "JAPANESE_MISMATCH":
        return False
    provider = row.get("provider_language_normalized")
    if provider and provider != "ENGLISH":
        return False
    image = row["image_state"] == "MATCH"
    english = provider == "ENGLISH"
    return {"image_match": image, "provider_english": english,
            "either": image or english, "both": image and english}[rule]


def run() -> dict:
    result = {"classification": "HISTORICAL_POST_HOC_NON_CERTIFYING",
              "policy_version": VERSION, "policy_fingerprint": fingerprint(), "cohorts": {}}
    for name, prediction_file, queue_file in COHORTS:
        predictions = json.loads((BASE / prediction_file).read_text(encoding="utf-8"))["predictions"]
        with (BASE / queue_file).open(encoding="utf-8-sig", newline="") as fh:
            labels = {row["benchmark_row_id"]: row for row in csv.DictReader(fh)}
        if len(predictions) != len(labels):
            raise ValueError(f"cohort length mismatch: {name}")
        cohort = {"total_rows": len(labels), "human_yes": sum(x["exact_match_yes_no_uncertain"] == "YES" for x in labels.values()),
                  "human_non_english": sum(x.get("language") == "NON_ENGLISH" for x in labels.values()), "rules": {}}
        for rule in ("image_match", "provider_english", "either", "both"):
            kept = [row for row in predictions if accepts(row, rule)]
            truth = Counter(labels[row["row_id"]]["exact_match_yes_no_uncertain"] for row in kept)
            cohort["rules"][rule] = {
                "accepted": len(kept), "human_exact_english_yes_accepted": truth["YES"],
                "human_no_accepted": truth["NO"], "human_uncertain_accepted": truth["UNCERTAIN"],
                "human_non_english_accepted": sum(labels[row["row_id"]].get("language") == "NON_ENGLISH" for row in kept),
                "human_english_lost": cohort["human_yes"] - truth["YES"],
                "listing_coverage": len(kept) / len(labels),
                "card_coverage": len({row["canonical_card_id"] for row in kept}),
            }
        result["cohorts"][name] = cohort
    OUT.write_text(json.dumps(result, indent=2) + "\n", encoding="utf-8")
    return result


if __name__ == "__main__":
    print(json.dumps(run(), indent=2))
