"""Capture a genuinely new blind cohort for D3-v5 -- POST-FREEZE ONLY.

Reuses the same collector, dedup, and stratified-sampling machinery as
capture_ebay_d3_v4_fresh_blind.py, but additionally excludes every item ID
already used in the (now-consumed) V4 420-row blind cohort, and writes to
NEW v5-specific artifact names so no V4 evidence is overwritten.
"""
from __future__ import annotations

import csv
import hashlib
import json
from collections import defaultdict
from typing import Any

from backend.scripts.capture_ebay_d3_v4_fresh_blind import (
    ROWS_PER_CARD,
    build_reviewer_row,
    fill_target_fields,
    load_new_raw_evidence,
    relist_fingerprint,
    stratified_sample,
)
from backend.scripts.ebay_gold_access import OUT

HISTORICAL_FILES = [
    "ebay_manual_gold_labels.csv", "ebay_d3_blind_review_queue.csv",
    "ebay_gold_development.csv", "ebay_gold_validation.csv", "ebay_gold_final_blind.csv",
    "ebay_d3_v4_fresh_blind_queue.csv",  # the consumed V4 420-row blind cohort -- excluded from v5's pool
]

QUEUE_OUT_PATH = OUT / "ebay_d3_v5_fresh_blind_queue.csv"
MANIFEST_OUT_PATH = OUT / "ebay_d3_v5_fresh_blind_manifest.json"

REVIEWER_FIELDS = [
    "benchmark_row_id", "listing_item_id", "item_url", "listing_title", "condition", "condition_id",
    "category_id", "buying_options_json", "seller_id", "image_url", "canonical_card_id", "card_variant_id",
    "target_card_name", "target_set_name", "target_card_number", "target_treatment",
    "exact_match_yes_no_uncertain", "single_card_or_lot", "raw_or_graded", "card_or_sealed_nonshcard",
    "collector_number_consistency", "set_consistency", "language", "variant_treatment",
    "reviewer_id", "label_timestamp", "review_note", "adjudicated_result",
]


def load_historical_item_ids() -> set[str]:
    ids: set[str] = set()
    for name in HISTORICAL_FILES:
        path = OUT / name
        if not path.exists():
            continue
        with path.open(encoding="utf-8", newline="") as handle:
            for row in csv.DictReader(handle):
                item_id = row.get("listing_item_id")
                if item_id:
                    ids.add(item_id)
    return ids


def load_historical_relist_fingerprints() -> set[str]:
    fingerprints: set[str] = set()
    for name in HISTORICAL_FILES:
        path = OUT / name
        if not path.exists():
            continue
        with path.open(encoding="utf-8", newline="") as handle:
            for row in csv.DictReader(handle):
                fingerprints.add(relist_fingerprint(
                    title=row.get("listing_title", ""), seller=row.get("seller_id", ""),
                    canonical_card_id=row.get("canonical_card_id", ""), price=None,
                ))
    return fingerprints


def main(run_id: str) -> dict[str, Any]:
    historical_ids = load_historical_item_ids()
    historical_fingerprints = load_historical_relist_fingerprints()
    raw = load_new_raw_evidence(run_id)

    seen_new: dict[str, dict[str, Any]] = {}
    excluded_exact_id = 0
    excluded_relist = 0
    for row in raw:
        item_id = row["ebay_item_id"]
        if item_id in historical_ids:
            excluded_exact_id += 1
            continue
        fp = relist_fingerprint(
            title=row.get("title", ""), seller=row.get("seller_username", ""),
            canonical_card_id=row["target_canonical_card_id"], price=row.get("price_value"),
        )
        if fp in historical_fingerprints:
            excluded_relist += 1
            continue
        if item_id not in seen_new:
            seen_new[item_id] = row

    eligible = list(seen_new.values())
    sampled = stratified_sample(eligible, ROWS_PER_CARD)

    cohort = json.loads((OUT / "ebay_pilot_cohort.json").read_text(encoding="utf-8"))
    reviewer_rows = [build_reviewer_row(row, f"D5-{i:04d}") for i, row in enumerate(sampled)]
    fill_target_fields(reviewer_rows, cohort)

    with QUEUE_OUT_PATH.open("w", encoding="utf-8", newline="") as handle:
        writer = csv.DictWriter(handle, fieldnames=REVIEWER_FIELDS)
        writer.writeheader()
        writer.writerows(reviewer_rows)

    cards_represented = {r["canonical_card_id"] for r in reviewer_rows}
    cohort_fingerprint = hashlib.sha256(
        "\n".join(sorted(f"{r['benchmark_row_id']}:{r['listing_item_id']}" for r in reviewer_rows)).encode()
    ).hexdigest()

    manifest = {
        "version": "ebay_d3_v5_fresh_blind_manifest_v1",
        "matcher_version_under_test": "index_fair_value_ebay_d3_v5",
        "source_run_id": run_id,
        "new_raw_evidence_count": len(raw),
        "excluded_exact_historical_item_id": excluded_exact_id,
        "excluded_likely_relist_fingerprint": excluded_relist,
        "eligible_after_dedup": len(eligible),
        "sampled_row_count": len(reviewer_rows),
        "cards_represented": len(cards_represented),
        "cards_represented_of_70": sorted(cards_represented),
        "rows_per_card_target": ROWS_PER_CARD,
        "cohort_fingerprint": cohort_fingerprint,
        "matcher_outputs_included": False,
        "sampling_method": "deterministic per-card SHA-256 ordering, independent of any matcher status",
        "excludes_v4_blind_cohort": True,
        "historical_exclusion_files": HISTORICAL_FILES,
        "relist_dedup_method": "sha256(normalized_title|seller|canonical_card_id|price_bucket_of_5); "
                                "heuristic only, same limitations as documented for the V4 capture.",
        "labels_exist": False,
        "labels_frozen": False,
        "reviewer_b_exists": False,
        "protocol": "SINGLE_REVIEWER_BLIND",
    }
    MANIFEST_OUT_PATH.write_text(json.dumps(manifest, indent=2) + "\n", encoding="utf-8")
    return manifest


if __name__ == "__main__":
    import sys

    print(json.dumps(main(sys.argv[1]), indent=2))
