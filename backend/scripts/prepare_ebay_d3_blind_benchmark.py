"""Prepare fresh, matcher-blind D3 certification partitions after v3 freeze."""
from __future__ import annotations

import argparse
import csv
import hashlib
import json
from collections import defaultdict
from pathlib import Path
from typing import Any, Callable, Mapping

from backend.scripts.ebay_d3_matcher_v3 import MATCHER_VERSION, classify_listing, rule_fingerprint
from backend.scripts.ebay_gold_access import OUT, load_partition

FREEZE = OUT / "ebay_d3_v3_freeze_manifest.json"
DESIGN = OUT / "ebay_d3_new_blind_benchmark_design.json"
PRECISION_FILE = OUT / "ebay_d3_precision_blind.csv"
COVERAGE_FILE = OUT / "ebay_d3_coverage_blind.csv"
REVIEW_FILE = OUT / "ebay_d3_blind_review_queue.csv"
MANIFEST = OUT / "ebay_d3_blind_benchmark_manifest.json"
SAFE_FIELDS = (
    "benchmark_row_id", "partition", "canonical_card_id",
    "card_variant_id", "target_card_name", "target_set_name", "target_card_number",
    "target_treatment", "listing_item_id", "listing_title", "category_id",
    "condition", "condition_id", "localized_aspects_json", "buying_options_json",
    "seller_id", "image_url", "item_url", "observed_at",
)


def stable(row: Mapping[str, Any], salt: str) -> str:
    material = f"{salt}|{row['canonical_card_id']}|{row['listing_item_id']}|{row.get('seller_id','')}|{row.get('listing_title','')}"
    return hashlib.sha256(material.encode()).hexdigest()


def title_pattern(row: Mapping[str, Any]) -> str:
    title = str(row.get("listing_title", "")).lower()
    return "fraction" if "/" in title else "hash" if "#" in title else "plain"


def select_cohorts(rows: list[dict[str, Any]], precision_n: int = 300, per_card: int = 6) -> tuple[list[dict[str, Any]], list[dict[str, Any]]]:
    by_card = defaultdict(list)
    for row in rows:
        by_card[str(row["canonical_card_id"])].append(row)
    if len(by_card) != 70 or any(len(values) < per_card for values in by_card.values()):
        raise ValueError("fresh capture lacks six rows for every one of 70 cards")
    coverage = []
    for card in sorted(by_card):
        coverage.extend(sorted(by_card[card], key=lambda row: stable(row, "d3-coverage-v1"))[:per_card])
    high_by_card = {
        card: sorted((row for row in values if row["_matcher_state"] == "HIGH_CONFIDENCE"),
                     key=lambda row: (row.get("seller_id", ""), title_pattern(row), stable(row, "d3-precision-v1")))
        for card, values in by_card.items()
    }
    precision = []
    round_number = 0
    while len(precision) < precision_n:
        added = False
        for card in sorted(high_by_card, key=lambda value: hashlib.sha256(f"d3-card|{value}".encode()).hexdigest()):
            if round_number < len(high_by_card[card]):
                precision.append(high_by_card[card][round_number]); added = True
                if len(precision) == precision_n:
                    break
        if not added:
            raise ValueError("fresh capture lacks 300 frozen-v3 HIGH candidates")
        round_number += 1
    return precision, coverage


def safe_row(row: Mapping[str, Any], partition: str) -> dict[str, str]:
    item_id = str(row["listing_item_id"])
    output = {field: str(row.get(field, "") or "") for field in SAFE_FIELDS}
    output["benchmark_row_id"] = "D3-" + hashlib.sha256(f"fresh-v1|{item_id}".encode()).hexdigest()[:16].upper()
    output["partition"] = partition
    return output


def write_partition(path: Path, rows: list[dict[str, str]]) -> None:
    with path.open("w", encoding="utf-8", newline="") as handle:
        writer = csv.DictWriter(handle, fieldnames=SAFE_FIELDS)
        writer.writeheader(); writer.writerows(rows)


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("--capture-jsonl", type=Path, required=True)
    args = parser.parse_args()
    freeze = json.loads(FREEZE.read_text(encoding="utf-8"))
    design = json.loads(DESIGN.read_text(encoding="utf-8"))
    if not (freeze.get("logic_frozen") and freeze.get("matcher_version") == MATCHER_VERSION
            and freeze.get("matcher_fingerprint") == rule_fingerprint()
            and freeze.get("benchmark_design_fingerprint") == design.get("benchmark_design_fingerprint")):
        raise RuntimeError("V3_FREEZE_OR_DESIGN_MISMATCH")
    prior_ids = {
        row["listing_item_id"] for partition in ("DEVELOPMENT", "VALIDATION", "FINAL_BLIND_TEST")
        for row in load_partition(partition, purpose="human_review")
    }
    raw = [json.loads(line) for line in args.capture_jsonl.read_text(encoding="utf-8").splitlines() if line.strip()]
    if any(not row.get("observed_at") for row in raw):
        raise ValueError("every fresh observation requires observed_at")
    fresh = []; seen_items = set(); seen_seller_titles = set(); excluded_prior = 0; duplicates = 0
    for row in raw:
        item = str(row.get("listing_item_id") or row.get("itemId") or "")
        row["listing_item_id"] = item
        if not item or item in prior_ids:
            excluded_prior += 1; continue
        seller_title = (str(row.get("seller_id", "")).strip().lower(), " ".join(str(row.get("listing_title", "")).lower().split()))
        if item in seen_items or seller_title in seen_seller_titles:
            duplicates += 1; continue
        seen_items.add(item); seen_seller_titles.add(seller_title)
        result = classify_listing(
            {"card_name":row["target_card_name"], "set_name":row["target_set_name"], "card_number":row["target_card_number"], "treatment":row["target_treatment"]},
            {"title":row["listing_title"], "subtitle":row.get("subtitle"), "condition":row.get("condition"),
             "conditionId":row.get("condition_id"), "category":row.get("category_id"),
             "aspects":row.get("localized_aspects_json"), "itemId":item},
        )
        row["_matcher_state"] = result["identity_state"]
        fresh.append(row)
    precision, coverage = select_cohorts(fresh)
    precision_ids = {row["listing_item_id"] for row in precision}
    coverage_ids = {row["listing_item_id"] for row in coverage}
    overlap = precision_ids & coverage_ids
    precision_output = [safe_row(row, "PRECISION_BLIND") for row in precision]
    coverage_output = [safe_row(row, "COVERAGE_BLIND") for row in coverage]
    unique = {row["listing_item_id"]: row for row in precision + coverage}
    review_output = [safe_row(row, "D3_BLIND_REVIEW") for row in sorted(unique.values(), key=lambda item: stable(item, "d3-review-v1"))]
    write_partition(PRECISION_FILE, precision_output); write_partition(COVERAGE_FILE, coverage_output)
    write_partition(REVIEW_FILE, review_output)
    manifest = {
        "version":"ebay_d3_blind_benchmark_manifest_v1", "matcher_version":MATCHER_VERSION,
        "matcher_fingerprint":rule_fingerprint(), "benchmark_design_fingerprint":design["benchmark_design_fingerprint"],
        "capture_fingerprint":hashlib.sha256(args.capture_jsonl.read_bytes()).hexdigest(),
        "capture_rows":len(raw), "excluded_prior_item_ids":excluded_prior, "duplicate_fresh_rows":duplicates,
        "deduplicated_fresh_listings":len(fresh), "high_candidates":sum(row["_matcher_state"] == "HIGH_CONFIDENCE" for row in fresh),
        "precision_cohort_rows":len(precision), "coverage_cohort_rows":len(coverage),
        "overlap_rows":len(overlap), "unique_human_review_rows":len(review_output),
        "observed_at_min":min(str(row["observed_at"]) for row in fresh), "observed_at_max":max(str(row["observed_at"]) for row in fresh),
        "human_labels_present":False, "matcher_fields_exported_to_reviewer":False, "price_fields_exported_to_reviewer":False,
        "precision_partition_fingerprint":hashlib.sha256(PRECISION_FILE.read_bytes()).hexdigest(),
        "coverage_partition_fingerprint":hashlib.sha256(COVERAGE_FILE.read_bytes()).hexdigest(),
        "review_queue_fingerprint":hashlib.sha256(REVIEW_FILE.read_bytes()).hexdigest(),
    }
    MANIFEST.write_text(json.dumps(manifest, indent=2) + "\n", encoding="utf-8")
    print(json.dumps(manifest, indent=2))


if __name__ == "__main__":
    main()
