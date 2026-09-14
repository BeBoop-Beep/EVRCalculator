"""Freeze a blinded eBay D2 listing review queue. No production writes."""
from __future__ import annotations

import csv
import json
import urllib.parse
import urllib.request
from collections import Counter, defaultdict
from datetime import datetime, timezone
from pathlib import Path

from backend.scripts.index_fair_value_ebay_supply import build_query, classify_listing
from backend.scripts.run_index_fair_value_ebay_supply_d1 import env, token

ROOT = Path(__file__).resolve().parents[2]
OUT = ROOT / "backend" / "artifacts" / "index_fair_value"
LABELS = (
    "EXACT_TARGET_MATCH", "RELATED_BUT_WRONG_VARIANT", "WRONG_SET",
    "WRONG_CARD_NUMBER", "WRONG_LANGUAGE", "GRADED", "LOT_OR_BUNDLE",
    "SEALED_OR_ACCESSORY", "CONDITION_INELIGIBLE", "AMBIGUOUS", "OTHER",
)
FIELDS = (
    "title", "itemId", "categoryId", "condition", "conditionId",
    "localizedAspects", "brand", "buyingOptions", "seller", "image",
    "itemWebUrl", "price", "shippingOptions",
)


def populated(value):
    return value not in (None, "", [], {})


def request_page(access_token, query, offset=0):
    params = urllib.parse.urlencode({
        "q": query["query"], "category_ids": query["category_id"],
        "limit": query["limit"], "offset": offset, "filter": query["filters"],
    })
    req = urllib.request.Request(
        "https://api.ebay.com/buy/browse/v1/item_summary/search?" + params,
        headers={"Authorization": f"Bearer {access_token}", "X-EBAY-C-MARKETPLACE-ID": "EBAY_US", "Accept": "application/json"},
    )
    with urllib.request.urlopen(req, timeout=30) as response:
        return json.load(response)


def main():
    cohort = json.loads((OUT / "ebay_pilot_cohort.json").read_text(encoding="utf-8"))
    access_token = token(env())
    captured_at = datetime.now(timezone.utc).isoformat()
    observations, field_counts, errors = [], Counter(), []
    for card in cohort["cards"]:
        try:
            payload = request_page(access_token, build_query(card))
        except Exception as exc:
            errors.append({"canonical_card_id": card["canonical_card_id"], "error_type": type(exc).__name__})
            continue
        for item in payload.get("itemSummaries", []):
            for field in FIELDS:
                field_counts[field] += int(populated(item.get(field)))
            observations.append((card, item, classify_listing(card, item)))

    # Stratify within every card and D1 prediction state, then fill deterministically.
    grouped = defaultdict(list)
    for record in observations:
        grouped[(record[0]["canonical_card_id"], record[2]["match_state"])].append(record)
    selected = []
    for card in cohort["cards"]:
        card_id = card["canonical_card_id"]
        pool = []
        for state in ("EXACT_MATCH", "LIKELY_MATCH", "AMBIGUOUS", "WRONG_CARD", "GRADED", "LOT_OR_BUNDLE", "NON_ENGLISH", "ACCESSORY", "SEALED_PRODUCT", "RAW_NON_NM"):
            candidates = sorted(grouped[(card_id, state)], key=lambda row: str(row[1].get("itemId")))
            take = 3 if state in {"EXACT_MATCH", "LIKELY_MATCH", "AMBIGUOUS", "WRONG_CARD"} else 1
            pool.extend(candidates[:take])
        seen = {str(row[1].get("itemId")) for row in pool}
        all_card = sorted((row for row in observations if row[0]["canonical_card_id"] == card_id), key=lambda row: str(row[1].get("itemId")))
        pool.extend(row for row in all_card if str(row[1].get("itemId")) not in seen)
        selected.extend(pool[:15])

    columns = [
        "benchmark_row_id", "canonical_card_id", "card_variant_id", "target_card_name",
        "target_set_name", "target_card_number", "target_treatment", "listing_item_id",
        "listing_title", "category_id", "condition", "condition_id", "localized_aspects_json",
        "buying_options_json", "seller_id", "image_url", "item_url", "price_json",
        "shipping_json", "gold_label", "reviewer_notes", "review_status",
    ]
    with (OUT / "ebay_manual_gold_labels.csv").open("w", newline="", encoding="utf-8") as handle:
        writer = csv.DictWriter(handle, fieldnames=columns)
        writer.writeheader()
        for index, (card, item, _) in enumerate(selected, 1):
            writer.writerow({
                "benchmark_row_id": f"D2-{index:04d}",
                "canonical_card_id": card["canonical_card_id"],
                "card_variant_id": card.get("card_variant_id"),
                "target_card_name": card["card_name"],
                "target_set_name": card["set_name"],
                "target_card_number": card.get("card_number"),
                "target_treatment": card.get("treatment_key"),
                "listing_item_id": item.get("itemId"),
                "listing_title": item.get("title"),
                "category_id": item.get("categoryId"),
                "condition": item.get("condition"),
                "condition_id": item.get("conditionId"),
                "localized_aspects_json": json.dumps(item.get("localizedAspects") or [], ensure_ascii=False),
                "buying_options_json": json.dumps(item.get("buyingOptions") or []),
                "seller_id": (item.get("seller") or {}).get("username"),
                "image_url": (item.get("image") or {}).get("imageUrl"),
                "item_url": item.get("itemWebUrl"),
                "price_json": json.dumps(item.get("price") or {}),
                "shipping_json": json.dumps(item.get("shippingOptions") or []),
                "gold_label": "",
                "reviewer_notes": "",
                "review_status": "PENDING_INDEPENDENT_HUMAN_REVIEW",
            })

    audit = {
        "version": "index_fair_value_ebay_d2_gold_queue_v1",
        "captured_at": captured_at,
        "frozen_before_matcher_revision": True,
        "blinded_to_d1_prediction": True,
        "cards_attempted": len(cohort["cards"]),
        "cards_captured": len({row[0]["canonical_card_id"] for row in observations}),
        "listings_observed": len(observations),
        "review_queue_rows": len(selected),
        "completed_gold_labels": 0,
        "allowed_labels": LABELS,
        "errors": errors,
        "field_population": {
            field: {"count": field_counts[field], "rate": field_counts[field] / len(observations) if observations else None}
            for field in FIELDS
        },
        "gate": "BLOCKED_PENDING_INDEPENDENT_HUMAN_REVIEW",
    }
    (OUT / "ebay_d2_capture_audit.json").write_text(json.dumps(audit, indent=2) + "\n", encoding="utf-8")
    print(json.dumps(audit, indent=2))


if __name__ == "__main__":
    main()
