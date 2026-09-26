"""EBAY_E2_13: capture a genuinely new blind cohort under the already-frozen
CAPTURE-ALLOCATION-v2 contract -- POST-freeze ONLY, POLICY-BLIND ONLY.

Reuses the exact reviewer-row / dedup / stratified-sampling machinery from
capture_ebay_d3_v4_fresh_blind.py / capture_ebay_e2_9b_fresh_blind.py
unchanged. The only parameter changed from E2.9B is ROWS_PER_CARD, taken
from the frozen ebay_capture_allocation_v2_freeze_manifest.json (8, not 6).
Historical exclusion additionally covers E2.9B's own queue (a gap the E2.12
freeze already corrected).
"""
from __future__ import annotations

import csv
import hashlib
import json
from pathlib import Path
from typing import Any

from backend.scripts.capture_ebay_d3_v4_fresh_blind import (
    build_reviewer_row, fill_target_fields, load_new_raw_evidence, relist_fingerprint, stratified_sample,
)
from backend.scripts.capture_ebay_e2_9b_fresh_blind import (
    _item_id_from_url, D2M_URL_FILE, D2_TITLE_ONLY_FILES_NOT_ID_EXCLUDABLE,
)
from backend.scripts.ebay_gold_access import OUT

ALLOCATION_FREEZE_PATH = OUT / "ebay_capture_allocation_v2_freeze_manifest.json"
ALLOCATION_FREEZE = json.loads(ALLOCATION_FREEZE_PATH.read_text(encoding="utf-8"))
ROWS_PER_CARD = ALLOCATION_FREEZE["rows_per_card"]  # 8, from the frozen contract -- not hardcoded here

# Every file the E2.12 freeze names as in-scope, i.e. every prior evidence
# source including E2.9B's own queue (the gap E2.12 caught and fixed).
HISTORICAL_ID_FILES = [f for f in ALLOCATION_FREEZE["historical_exclusion_files"] if f != D2M_URL_FILE]

QUEUE_OUT_PATH = OUT / "ebay_e2_13_fresh_blind_queue.csv"
MANIFEST_OUT_PATH = OUT / "ebay_e2_13_fresh_blind_manifest.json"

REVIEWER_FIELDS = [
    "benchmark_row_id", "listing_item_id", "item_url", "listing_title", "condition", "condition_id",
    "category_id", "buying_options_json", "seller_id", "image_url", "canonical_card_id", "card_variant_id",
    "target_card_name", "target_set_name", "target_card_number", "target_treatment",
    "exact_match_yes_no_uncertain", "single_card_or_lot", "raw_or_graded", "card_or_sealed_nonshcard",
    "collector_number_consistency", "set_consistency", "language", "variant_treatment",
    "reviewer_id", "label_timestamp", "review_note", "adjudicated_result",
]

TOTAL_TARGET_CARDS = 70


def load_historical_item_ids() -> tuple[set[str], dict[str, int]]:
    ids: set[str] = set()
    per_file: dict[str, int] = {}
    for name in HISTORICAL_ID_FILES:
        path = OUT / name
        if not path.exists():
            per_file[name] = 0
            continue
        count = 0
        with path.open(encoding="utf-8", newline="") as handle:
            for row in csv.DictReader(handle):
                item_id = row.get("listing_item_id")
                if item_id:
                    ids.add(item_id)
                    count += 1
        per_file[name] = count

    path = OUT / D2M_URL_FILE
    count = 0
    if path.exists():
        with path.open(encoding="utf-8", newline="") as handle:
            for row in csv.DictReader(handle):
                item_id = _item_id_from_url(row.get("item_url", ""))
                if item_id:
                    ids.add(item_id)
                    count += 1
    per_file[D2M_URL_FILE] = count
    return ids, per_file


def load_historical_urls() -> set[str]:
    urls: set[str] = set()
    for name in HISTORICAL_ID_FILES + [D2M_URL_FILE]:
        path = OUT / name
        if not path.exists():
            continue
        with path.open(encoding="utf-8", newline="") as handle:
            for row in csv.DictReader(handle):
                url = row.get("item_url")
                if url:
                    urls.add(url)
    return urls


def load_historical_relist_fingerprints() -> set[str]:
    fingerprints: set[str] = set()
    for name in HISTORICAL_ID_FILES:
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


def main(run_id: str, capture_started_at: str, capture_finished_at: str, browse_request_count: int) -> dict[str, Any]:
    historical_ids, per_file_id_counts = load_historical_item_ids()
    historical_urls = load_historical_urls()
    historical_fingerprints = load_historical_relist_fingerprints()
    raw = load_new_raw_evidence(run_id)

    seen_new: dict[str, dict[str, Any]] = {}
    excluded_exact_id = 0
    excluded_relist = 0
    duplicate_within_run = 0
    per_card_raw: dict[str, int] = {}
    per_card_surviving: dict[str, int] = {}

    for row in raw:
        card_id = row["target_canonical_card_id"]
        per_card_raw[card_id] = per_card_raw.get(card_id, 0) + 1
        item_id = row["ebay_item_id"]
        if item_id in historical_ids:
            excluded_exact_id += 1
            continue
        fp = relist_fingerprint(
            title=row.get("title", ""), seller=row.get("seller_username", ""),
            canonical_card_id=card_id, price=row.get("price_value"),
        )
        if fp in historical_fingerprints:
            excluded_relist += 1
            continue
        if item_id in seen_new:
            duplicate_within_run += 1
            continue
        seen_new[item_id] = row
        per_card_surviving[card_id] = per_card_surviving.get(card_id, 0) + 1

    eligible = list(seen_new.values())
    sampled = stratified_sample(eligible, ROWS_PER_CARD)

    cohort = json.loads((OUT / "ebay_pilot_cohort.json").read_text(encoding="utf-8"))
    all_card_ids = {c["canonical_card_id"] for c in cohort["cards"]}
    reviewer_rows = [build_reviewer_row(row, f"E13-{i:04d}") for i, row in enumerate(sampled)]
    fill_target_fields(reviewer_rows, cohort)

    with QUEUE_OUT_PATH.open("w", encoding="utf-8", newline="") as handle:
        writer = csv.DictWriter(handle, fieldnames=REVIEWER_FIELDS)
        writer.writeheader()
        writer.writerows(reviewer_rows)

    per_card_counts: dict[str, int] = {}
    for r in reviewer_rows:
        per_card_counts[r["canonical_card_id"]] = per_card_counts.get(r["canonical_card_id"], 0) + 1

    cards_represented = set(per_card_counts)
    unrepresented_cards = sorted(all_card_ids - cards_represented)
    shortfall_cards = {
        cid: {"surviving_candidates": per_card_surviving.get(cid, 0), "selected": per_card_counts.get(cid, 0)}
        for cid in all_card_ids
        if per_card_counts.get(cid, 0) < ROWS_PER_CARD
    }

    cohort_fingerprint = hashlib.sha256(
        "\n".join(sorted(f"{r['benchmark_row_id']}:{r['listing_item_id']}" for r in reviewer_rows)).encode()
    ).hexdigest()

    # Prior final-blind row IDs (E2.9B's own benchmark_row_id values) for the
    # "0 overlap with prior final blind row IDs" novelty proof (Phase 5).
    prior_row_ids: set[str] = set()
    e29b_path = OUT / "ebay_e2_9b_fresh_blind_queue.csv"
    if e29b_path.exists():
        with e29b_path.open(encoding="utf-8", newline="") as handle:
            for row in csv.DictReader(handle):
                prior_row_ids.add(row["benchmark_row_id"])

    manifest = {
        "version": "ebay_e2_13_fresh_blind_manifest_v1",
        "policy_version_under_test": "ebay_combined_identity_policy_v2",
        "capture_allocation_version": ALLOCATION_FREEZE["version"],
        "capture_allocation_fingerprint": ALLOCATION_FREEZE["allocation_fingerprint"],
        "source_run_id": run_id,
        "capture_started_at": capture_started_at,
        "capture_finished_at": capture_finished_at,
        "browse_request_count": browse_request_count,
        "raw_evidence_count": len(raw),
        "rows_per_card": ROWS_PER_CARD,
        "coverage_universe": TOTAL_TARGET_CARDS,
        "historical_id_files": HISTORICAL_ID_FILES + [D2M_URL_FILE],
        "historical_id_counts_per_file": per_file_id_counts,
        "historical_ids_not_exact_excludable_title_only_files": D2_TITLE_ONLY_FILES_NOT_ID_EXCLUDABLE,
        "historical_id_pool_size": len(historical_ids),
        "historical_url_pool_size": len(historical_urls),
        "excluded_exact_historical_item_id": excluded_exact_id,
        "excluded_likely_relist_fingerprint": excluded_relist,
        "excluded_duplicate_within_run": duplicate_within_run,
        "eligible_after_dedup": len(eligible),
        "sampled_row_count": len(reviewer_rows),
        "cards_represented": len(cards_represented),
        "cards_represented_of_70": sorted(cards_represented),
        "unrepresented_cards_of_70": unrepresented_cards,
        "per_card_counts": per_card_counts,
        "per_card_raw_candidates": per_card_raw,
        "per_card_surviving_candidates": per_card_surviving,
        "shortfall_cards": shortfall_cards,
        "cohort_fingerprint": cohort_fingerprint,
        "matcher_outputs_included": False,
        "sampling_method": "deterministic per-card SHA-256 ordering (stratified_sample, unmodified from V4/V5/E2.9B); "
                            "never orders/filters by D3-v5, IMAGE-v2, COMBINED-v1/v2, tier state, similarity, "
                            "retrieval margin, or predicted outcome.",
        "excludes_evidence_used_in": ["D2", "D3", "V4", "V5", "E2.6", "E2.7", "E2.8", "E2.9", "E2.9A",
                                       "E2.9B", "E2.9C", "E2.10", "E2.11"],
        "prior_final_blind_row_id_count_checked_against": len(prior_row_ids),
        "labels_exist": False,
        "labels_frozen": False,
        "reviewer_b_exists": False,
        "protocol": "SINGLE_REVIEWER_BLIND",
        "reviewed_count": 0,
        "production_authority": False,
    }
    MANIFEST_OUT_PATH.write_text(json.dumps(manifest, indent=2) + "\n", encoding="utf-8")
    return manifest


if __name__ == "__main__":
    import sys

    print(json.dumps(main(sys.argv[1], sys.argv[2], sys.argv[3], int(sys.argv[4])), indent=2))
