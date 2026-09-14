"""Capture a genuinely new blind cohort for D3-v4 -- POST-FREEZE ONLY.

Deduplicates against every historical partition (D2 manual queue, D3 blind
review queue, development/validation/final-blind gold) by exact item ID, and
flags likely relists via a content fingerprint. Produces a reviewer-facing
queue with NO matcher output of any kind. Stratifies deterministically by
card (not by matcher acceptance) so sampling cannot select only examples the
matcher likes.
"""
from __future__ import annotations

import csv
import hashlib
import json
import re
from collections import defaultdict
from pathlib import Path
from typing import Any

from backend.scripts.ebay_gold_access import OUT
from backend.scripts.index_fair_value_ebay_evidence_collector import RUNS_DIR
from backend.scripts.index_fair_value_ebay_supply import normalize

HISTORICAL_FILES = [
    "ebay_manual_gold_labels.csv", "ebay_d3_blind_review_queue.csv",
    "ebay_gold_development.csv", "ebay_gold_validation.csv", "ebay_gold_final_blind.csv",
]
ROWS_PER_CARD = 6


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
    """Content fingerprint: normalized title + seller + target card. Price is
    bucketed to a $5 neighborhood so ordinary price drift doesn't defeat the
    match, but this is a heuristic, not a guarantee -- documented as such.
    """
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


def relist_fingerprint(*, title: str, seller: str, canonical_card_id: str, price: float | None) -> str:
    price_bucket = round(price / 5) * 5 if price is not None else "unknown"
    material = f"{normalize(title)}|{(seller or '').lower()}|{canonical_card_id}|{price_bucket}"
    return hashlib.sha256(material.encode()).hexdigest()


def load_new_raw_evidence(run_id: str) -> list[dict[str, Any]]:
    path = RUNS_DIR / f"{run_id}.raw.jsonl"
    return [json.loads(l) for l in path.read_text(encoding="utf-8").splitlines() if l.strip()]


def stratified_sample(eligible: list[dict[str, Any]], rows_per_card: int = ROWS_PER_CARD) -> list[dict[str, Any]]:
    """Deterministic per-card SHA-256 ordering -- the same technique already
    used by the repository's existing blind-cohort designs. Never orders by
    matcher status (this module never even computes matcher status).
    """
    by_card: dict[str, list[dict[str, Any]]] = defaultdict(list)
    for row in eligible:
        by_card[row["target_canonical_card_id"]].append(row)
    sampled = []
    for card_id, rows in by_card.items():
        ordered = sorted(rows, key=lambda r: hashlib.sha256(f"{card_id}:{r['ebay_item_id']}".encode()).hexdigest())
        sampled.extend(ordered[:rows_per_card])
    return sampled


REVIEWER_FIELDS = [
    "benchmark_row_id", "listing_item_id", "item_url", "listing_title", "condition", "condition_id",
    "category_id", "buying_options_json", "seller_id", "image_url", "canonical_card_id", "card_variant_id",
    "target_card_name", "target_set_name", "target_card_number", "target_treatment",
    "exact_match_yes_no_uncertain", "single_card_or_lot", "raw_or_graded", "card_or_sealed_nonshcard",
    "collector_number_consistency", "set_consistency", "language", "variant_treatment",
    "reviewer_id", "label_timestamp", "review_note", "adjudicated_result",
]


def build_reviewer_row(row: dict[str, Any], benchmark_row_id: str) -> dict[str, Any]:
    """Every field here is either raw listing metadata or an EMPTY label
    column. No matcher status/score/confidence/reason/disagreement of any
    kind is included.
    """
    return {
        "benchmark_row_id": benchmark_row_id,
        "listing_item_id": row["ebay_item_id"],
        "item_url": row.get("item_web_url"),
        "listing_title": row.get("title"),
        "condition": row.get("condition"),
        "condition_id": row.get("condition_id"),
        "category_id": None,
        "buying_options_json": json.dumps(row.get("buying_options") or []),
        "seller_id": row.get("seller_username"),
        "image_url": row.get("image_url"),
        "canonical_card_id": row.get("target_canonical_card_id"),
        "card_variant_id": row.get("target_card_variant_id"),
        "target_card_name": None, "target_set_name": None, "target_card_number": None, "target_treatment": None,
        "exact_match_yes_no_uncertain": "", "single_card_or_lot": "", "raw_or_graded": "",
        "card_or_sealed_nonshcard": "", "collector_number_consistency": "", "set_consistency": "",
        "language": "", "variant_treatment": "",
        "reviewer_id": "", "label_timestamp": "", "review_note": "", "adjudicated_result": "",
    }


def fill_target_fields(reviewer_rows: list[dict[str, Any]], cohort: dict[str, Any]) -> None:
    cards = {c["canonical_card_id"]: c for c in cohort["cards"]}
    for row in reviewer_rows:
        card = cards.get(row["canonical_card_id"])
        if card:
            row["target_card_name"] = card["card_name"]
            row["target_set_name"] = card["set_name"]
            row["target_card_number"] = card["card_number"]
            row["target_treatment"] = card.get("treatment_key")


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
    reviewer_rows = [build_reviewer_row(row, f"D4-{i:04d}") for i, row in enumerate(sampled)]
    fill_target_fields(reviewer_rows, cohort)

    queue_path = OUT / "ebay_d3_v4_fresh_blind_queue.csv"
    with queue_path.open("w", encoding="utf-8", newline="") as handle:
        writer = csv.DictWriter(handle, fieldnames=REVIEWER_FIELDS)
        writer.writeheader()
        writer.writerows(reviewer_rows)

    cards_represented = {r["canonical_card_id"] for r in reviewer_rows}
    cohort_fingerprint = hashlib.sha256(
        "\n".join(sorted(f"{r['benchmark_row_id']}:{r['listing_item_id']}" for r in reviewer_rows)).encode()
    ).hexdigest()

    manifest = {
        "version": "ebay_d3_v4_fresh_blind_manifest_v1",
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
        "relist_dedup_method": "sha256(normalized_title|seller|canonical_card_id|price_bucket_of_5); "
                                "heuristic only -- a genuinely new listing with a coincidentally identical "
                                "title/seller/price bucket for the same card would be (incorrectly) excluded; "
                                "this trades a small amount of eligible-pool recall for lower false-inclusion risk.",
        "labels_exist": False,
        "reviewer_b_exists": False,
        "protocol": "SINGLE_REVIEWER_BLIND",
    }
    (OUT / "ebay_d3_v4_fresh_blind_manifest.json").write_text(json.dumps(manifest, indent=2) + "\n", encoding="utf-8")
    return manifest


if __name__ == "__main__":
    import sys

    print(json.dumps(main(sys.argv[1]), indent=2))
