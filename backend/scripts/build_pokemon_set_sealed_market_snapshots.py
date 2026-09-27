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

from backend.db.clients.supabase_client import service_read_client, supabase
from backend.db.services.pokemon_set_sealed_market_snapshot_service import build_snapshot, upsert_snapshot
from backend.domain.pokemon.sealed_product_classifier import classify_sealed_product
from backend.scripts.pokemon_snapshot_builders import list_pokemon_sets, resolve_set_row


def _rows(query: Any) -> List[Dict[str, Any]]:
    return list(query.execute().data or [])


SEALED_OBSERVATION_PAGE_SIZE = 512
SEALED_OBSERVATION_MAX_ROWS_PER_SET = 100_000


class SealedObservationReadIncomplete(RuntimeError):
    """The sealed observation read cannot be proven complete."""


def _paged_rows(
    query_factory: Any,
    page_size: int = SEALED_OBSERVATION_PAGE_SIZE,
    max_rows: int = SEALED_OBSERVATION_MAX_ROWS_PER_SET,
) -> List[Dict[str, Any]]:
    """Read every ordered row, even when PostgREST returns a short page early.

    A short HTTP page is not proof of end-of-data.  The edition-history outage
    exposed exactly that assumption elsewhere in the market pipeline.  Keep an
    exact count stable across pages and advance by the number of rows actually
    received so server-side response caps cannot silently truncate the history.
    """
    if not 1 <= page_size <= 1000 or max_rows < page_size:
        raise ValueError("invalid sealed observation pagination bounds")

    rows: List[Dict[str, Any]] = []
    expected: int | None = None
    previous_key: tuple[str, str] | None = None

    while len(rows) <= max_rows:
        response = query_factory().range(len(rows), len(rows) + page_size - 1).execute()
        total = getattr(response, "count", None)
        if type(total) is not int or total < 0 or total > max_rows:
            raise SealedObservationReadIncomplete("missing_or_invalid_exact_count")
        if expected is None:
            expected = total
        elif expected != total:
            raise SealedObservationReadIncomplete("sealed_observations_changed_during_pagination")

        page = response.data
        if not isinstance(page, list) or len(page) > page_size:
            raise SealedObservationReadIncomplete("invalid_sealed_observation_page")
        if not page:
            if len(rows) != expected:
                raise SealedObservationReadIncomplete("sealed_observations_ended_before_exact_count")
            return rows

        for row in page:
            key = (str(row.get("captured_at") or ""), str(row.get("id") or ""))
            if not key[0] or not key[1] or (previous_key is not None and key <= previous_key):
                raise SealedObservationReadIncomplete("unordered_or_duplicate_sealed_observations")
            rows.append(dict(row))
            previous_key = key

        if len(rows) > expected:
            raise SealedObservationReadIncomplete("sealed_observations_exceed_exact_count")
        if len(rows) == expected:
            return rows

    raise SealedObservationReadIncomplete("sealed_observation_page_budget_exhausted")


def resolve_sets(selector: str | None, all_sets: bool) -> List[Dict[str, Any]]:
    if all_sets:
        return list_pokemon_sets(service_read_client)
    return [resolve_set_row(service_read_client, str(selector))]


def build_one(set_row: Dict[str, Any], commit: bool) -> Dict[str, Any]:
    products = _rows(
        service_read_client.table("sealed_products").select("id,set_id,name,product_type").eq("set_id", set_row["id"])
    )
    product_ids = [product["id"] for product in products]
    observations = _paged_rows(
        lambda: service_read_client.table("sealed_product_price_observations")
        .select("id,sealed_product_id,market_price,source,currency,captured_at", count="exact")
        .in_("sealed_product_id", product_ids)
        .order("captured_at")
        .order("id")
    ) if product_ids else []
    row = build_snapshot(set_row, products, observations)
    existing = _rows(
        service_read_client.table("pokemon_set_sealed_market_snapshot_latest")
        .select("source_generation_fingerprint")
        .eq("set_id", set_row["id"])
        .limit(1)
    )
    action = "inserted" if not existing else (
        "unchanged" if existing[0].get("source_generation_fingerprint") == row["source_generation_fingerprint"] else "updated"
    )
    identities = [classify_sealed_product(product["name"]) for product in products]
    payload = row["payload_json"]
    set_market = payload.get("setMarket") or {}
    consumer_market = payload.get("setPageConsumerMarket") or {}
    market_index = set_market.get("marketIndex") or {}
    market_breadth = set_market.get("marketBreadth") or {}
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
        "snapshotContractVersion": (payload.get("meta") or {}).get("snapshotContractVersion"),
        "setMarketCurrentValue": set_market.get("currentValue"),
        "setMarketIndexCurrentValue": market_index.get("currentValue"),
        "setMarketBreadthKeys": list(market_breadth.keys()),
        "setPageConsumerPolicyVersion": payload["meta"].get("setPageConsumerPolicyVersion"),
        "setPageConsumerProductCount": consumer_market.get("productCount"),
        "setPageConsumerContributingProductCount": consumer_market.get("contributingProductCount"),
        "setPageConsumerCurrentValue": consumer_market.get("currentValue"),
        "setPageConsumerExcludedCaseDisplayCount": payload["meta"].get("setPageConsumerExcludedCaseDisplayCount"),
        "setPageConsumerExcludedBulkContainerCount": payload["meta"].get("setPageConsumerExcludedBulkContainerCount"),
        "setPageConsumerProductsWithoutHistoryCount": payload["meta"].get("setPageConsumerProductsWithoutHistoryCount"),
        "setPageConsumerTopProducts": [product["name"] for product in payload.get("setPageConsumerTopProducts") or []],
        "setPageConsumer7DBreadth": (consumer_market.get("marketBreadth") or {}).get("7D"),
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
