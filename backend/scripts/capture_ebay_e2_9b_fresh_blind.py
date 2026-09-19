"""EBAY_E2_9B: capture a genuinely new blind cohort for COMBINED-IDENTITY-v2
certification -- POST-FREEZE ONLY, POLICY-BLIND SAMPLING ONLY.

Reuses the exact reviewer-row / dedup / stratified-sampling machinery from
capture_ebay_d3_v4_fresh_blind.py / capture_ebay_d3_v5_fresh_blind.py
unchanged, expanded to exclude every prior evidence source used anywhere in
D2, D3, V4, V5, E2.6, E2.7, E2.8, E2.9, E2.9A. (E2.6-E2.9A performed no new
eBay capture of their own -- they only re-consumed the existing D2/D3/V4/V5
queues -- so excluding those queues is exclusion-complete for all of those
phases.)

Sampling never reads D3-v5, IMAGE-v2, COMBINED-IDENTITY-v1/v2, tier state,
similarity, retrieval margin, or any predicted human outcome -- this module
imports none of those and the raw evidence it reads
(`ebay_evidence_runs/<run_id>.raw.jsonl`) was captured with `--no-match`,
so no matcher was even run during collection.
"""
from __future__ import annotations

import csv
import hashlib
import json
import re
from pathlib import Path
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

# Every file anywhere in this repo carrying a real eBay listing_item_id from
# D2/D3/V4/V5 -- this is exclusion-complete for E2.6-E2.9A, which reused
# only these same rows and captured no new listings of their own.
HISTORICAL_ID_FILES = [
    "ebay_manual_gold_labels.csv",
    "ebay_gold_development.csv", "ebay_gold_validation.csv", "ebay_gold_final_blind.csv",
    "ebay_d3_blind_review_queue.csv", "ebay_d3_coverage_blind.csv", "ebay_d3_fresh_observations.csv",
    "ebay_d3_precision_blind.csv", "ebay_d3_v3_coverage_certification_rows.csv",
    "ebay_d3_v3_high_false_positive_forensics.csv", "ebay_d3_v3_precision_certification_rows.csv",
    "ebay_d3_v4_fresh_blind_queue.csv",  # consumed V4 420-row cohort
    "ebay_d3_v5_fresh_blind_queue.csv",  # consumed V5 417-row cohort (E2.6-E2.9A's evidence base)
]
# ebay_d2m_second_review_queue.csv predates listing_item_id but carries
# item_url -- item ID is recoverable from the URL path.
D2M_URL_FILE = "ebay_d2m_second_review_queue.csv"
# ebay_d2f_final_blind_predictions.csv and ebay_d2v_validation_predictions.csv
# predate BOTH listing_item_id and item_url (title-only schema). They cannot
# be exactly ID-excluded -- documented as a known limitation, not silently
# dropped. See EBAY_E2_9B report Section "Historical exclusions".
D2_TITLE_ONLY_FILES_NOT_ID_EXCLUDABLE = [
    "ebay_d2f_final_blind_predictions.csv", "ebay_d2v_validation_predictions.csv",
]

QUEUE_OUT_PATH = OUT / "ebay_e2_9b_fresh_blind_queue.csv"
MANIFEST_OUT_PATH = OUT / "ebay_e2_9b_fresh_blind_manifest.json"

# Kept byte-identical to V4/V5's REVIEWER_FIELDS (the proven, tested schema
# ebay_e2_9b_blind_review_server.py's write-back/materialize logic expects)
# rather than a narrower Section-10-only schema -- see EBAY_E2_9B report,
# "Review-server schema compatibility": V5's rich 8-field internal schema is
# already deterministically DERIVED from one primary answer + one NO reason
# (derive_fields()), so Section 10's contract ("Advanced details remain
# optional") is what this schema already implements; a narrower CSV broke
# the reused server's row materialization on first import-time check.
REVIEWER_FIELDS = [
    "benchmark_row_id", "listing_item_id", "item_url", "listing_title", "condition", "condition_id",
    "category_id", "buying_options_json", "seller_id", "image_url", "canonical_card_id", "card_variant_id",
    "target_card_name", "target_set_name", "target_card_number", "target_treatment",
    "exact_match_yes_no_uncertain", "single_card_or_lot", "raw_or_graded", "card_or_sealed_nonshcard",
    "collector_number_consistency", "set_consistency", "language", "variant_treatment",
    "reviewer_id", "label_timestamp", "review_note", "adjudicated_result",
]

_ITEM_ID_FROM_URL_RE = re.compile(r"[?&]item=([0-9]+)|/itm/[^/]*?/?([0-9]{9,})")


def _item_id_from_url(url: str) -> str | None:
    match = _ITEM_ID_FROM_URL_RE.search(url or "")
    if not match:
        return None
    return match.group(1) or match.group(2)


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
    historical_fingerprints = load_historical_relist_fingerprints()
    raw = load_new_raw_evidence(run_id)

    seen_new: dict[str, dict[str, Any]] = {}
    excluded_exact_id = 0
    excluded_relist = 0
    duplicate_within_run = 0
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
        if item_id in seen_new:
            duplicate_within_run += 1
            continue
        seen_new[item_id] = row

    eligible = list(seen_new.values())
    sampled = stratified_sample(eligible, ROWS_PER_CARD)

    cohort = json.loads((OUT / "ebay_pilot_cohort.json").read_text(encoding="utf-8"))
    reviewer_rows = [build_reviewer_row(row, f"E9B-{i:04d}") for i, row in enumerate(sampled)]
    fill_target_fields(reviewer_rows, cohort)

    with QUEUE_OUT_PATH.open("w", encoding="utf-8", newline="") as handle:
        writer = csv.DictWriter(handle, fieldnames=REVIEWER_FIELDS)
        writer.writeheader()
        writer.writerows(reviewer_rows)

    cards_represented = {r["canonical_card_id"] for r in reviewer_rows}
    per_card_counts: dict[str, int] = {}
    for r in reviewer_rows:
        per_card_counts[r["canonical_card_id"]] = per_card_counts.get(r["canonical_card_id"], 0) + 1

    cohort_fingerprint = hashlib.sha256(
        "\n".join(sorted(f"{r['benchmark_row_id']}:{r['listing_item_id']}" for r in reviewer_rows)).encode()
    ).hexdigest()

    manifest = {
        "version": "ebay_e2_9b_fresh_blind_manifest_v1",
        "policy_version_under_test": "ebay_combined_identity_policy_v2",
        "source_run_id": run_id,
        "capture_started_at": capture_started_at,
        "capture_finished_at": capture_finished_at,
        "browse_request_count": browse_request_count,
        "raw_evidence_count": len(raw),
        "historical_id_files": HISTORICAL_ID_FILES + [D2M_URL_FILE],
        "historical_id_counts_per_file": per_file_id_counts,
        "historical_ids_not_exact_excludable_title_only_files": D2_TITLE_ONLY_FILES_NOT_ID_EXCLUDABLE,
        "historical_id_pool_size": len(historical_ids),
        "excluded_exact_historical_item_id": excluded_exact_id,
        "excluded_likely_relist_fingerprint": excluded_relist,
        "excluded_duplicate_within_run": duplicate_within_run,
        "eligible_after_dedup": len(eligible),
        "sampled_row_count": len(reviewer_rows),
        "cards_represented": len(cards_represented),
        "cards_represented_of_70": sorted(cards_represented),
        "per_card_counts": per_card_counts,
        "rows_per_card_target": ROWS_PER_CARD,
        "cohort_fingerprint": cohort_fingerprint,
        "matcher_outputs_included": False,
        "sampling_method": "deterministic per-card SHA-256 ordering (stratified_sample, unmodified from V4/V5); "
                            "never orders/filters by D3-v5, IMAGE-v2, COMBINED-v1/v2, tier state, similarity, "
                            "retrieval margin, or predicted outcome -- raw evidence was captured with --no-match "
                            "so no matcher output exists to leak into sampling.",
        "excludes_evidence_used_in": ["D2", "D3", "V4", "V5", "E2.6", "E2.7", "E2.8", "E2.9", "E2.9A"],
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
