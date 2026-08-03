#!/usr/bin/env python
"""Build prepared sealed-market snapshots for one or all Pokémon sets."""

from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path
from typing import Any, Dict, List

ROOT = Path(__file__).resolve().parents[2]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from backend.db.clients.supabase_client import public_read_client, supabase
from backend.db.services.pokemon_set_sealed_market_snapshot_service import build_snapshot, upsert_snapshot
from backend.domain.pokemon.sealed_product_classifier import classify_sealed_product
from backend.scripts.pokemon_snapshot_builders import list_pokemon_sets, resolve_set_row


def _rows(query: Any) -> List[Dict[str, Any]]:
    return list(query.execute().data or [])


def _paged_rows(query_factory: Any, page_size: int = 1000) -> List[Dict[str, Any]]:
    rows: List[Dict[str, Any]] = []
    offset = 0
    while True:
        page = _rows(query_factory().range(offset, offset + page_size - 1))
        rows.extend(page)
        if len(page) < page_size:
            return rows
        offset += page_size


def resolve_sets(selector: str | None, all_sets: bool) -> List[Dict[str, Any]]:
    if all_sets:
        return list_pokemon_sets(public_read_client)
    return [resolve_set_row(public_read_client, str(selector))]


def build_one(set_row: Dict[str, Any], commit: bool) -> Dict[str, Any]:
    products = _rows(
        public_read_client.table("sealed_products").select("id,set_id,name,product_type").eq("set_id", set_row["id"])
    )
    product_ids = [product["id"] for product in products]
    observations = _paged_rows(
        lambda: public_read_client.table("sealed_product_price_observations")
        .select("id,sealed_product_id,market_price,source,currency,captured_at")
        .in_("sealed_product_id", product_ids)
        .order("captured_at")
    ) if product_ids else []
    row = build_snapshot(set_row, products, observations)
    existing = _rows(
        public_read_client.table("pokemon_set_sealed_market_snapshot_latest")
        .select("source_generation_fingerprint")
        .eq("set_id", set_row["id"])
        .limit(1)
    )
    action = "inserted" if not existing else (
        "unchanged" if existing[0].get("source_generation_fingerprint") == row["source_generation_fingerprint"] else "updated"
    )
    identities = [classify_sealed_product(product["name"]) for product in products]
    payload = row["payload_json"]
    report = {
        "set": payload["set"],
        "rawProductCount": len(products),
        "classifiedProductCount": len(identities),
        "overviewEligibleProductCount": sum(identity["isOverviewEligible"] for identity in identities),
        "excludedProductCountByReason": {
            family: sum(identity["productFamily"] == family for identity in identities if not identity["isOverviewEligible"])
            for family in sorted({identity["productFamily"] for identity in identities if not identity["isOverviewEligible"]})
        },
        "productsWithHistory": row["product_count"],
        "productsWithoutHistory": sum(identity["isOverviewEligible"] for identity in identities) - row["product_count"],
        "productsSelectedForPayload": [product["name"] for product in payload["products"]],
        "defaultSelectedProduct": payload["defaultProductId"],
        "historyStartDate": min((point["date"] for product in payload["products"] for point in product["history"]), default=None),
        "historyEndDate": row["market_date"],
        "productLatestDates": {product["sealedProductId"]: product["priceAsOf"] for product in payload["products"]},
        "snapshotMarketDate": row["market_date"],
        "fingerprint": row["source_generation_fingerprint"],
        "warnings": payload["meta"]["warnings"],
        "action": action,
    }
    if commit and action != "unchanged":
        upsert_snapshot(supabase, row)
    return report


def main() -> int:
    parser = argparse.ArgumentParser()
    target = parser.add_mutually_exclusive_group(required=True)
    target.add_argument("--set-id")
    target.add_argument("--all", action="store_true")
    mode = parser.add_mutually_exclusive_group(required=True)
    mode.add_argument("--dry-run", action="store_true")
    mode.add_argument("--commit", action="store_true")
    args = parser.parse_args()
    for set_row in resolve_sets(args.set_id, args.all):
        print(json.dumps(build_one(set_row, args.commit), indent=2, sort_keys=True))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
