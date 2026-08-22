"""Read-only audit: sealed index observation density for representative sets.

Does not write anything. Reuses the exact query pattern from
backend/scripts/build_pokemon_set_sealed_market_snapshots.py.
"""
from __future__ import annotations

import sys
from datetime import date, timedelta
from pathlib import Path

ROOT = Path(__file__).resolve()
sys.path.insert(0, "D:/EVRCalculator")

from backend.db.clients.supabase_client import public_read_client
from backend.db.services.pokemon_set_sealed_market_snapshot_service import (
    build_sealed_segment_history,
    build_snapshot,
    normalize_daily_history,
)
from backend.domain.pokemon.sealed_product_classifier import classify_sealed_product

SETS = [
    "pitchBlack",          # modern, many SKUs (newest)
    "destinedRivals",      # well-covered recent, high popularity
    "prismaticEvolutions", # moderate/high coverage
    "surgingSparks",       # moderate coverage, ~9mo older
    "shroudedFable",       # older tracked set (2024-08)
    "baseSetShadowless",   # very old / likely sparse or no sealed tracking
]


def rows(query):
    return list(query.execute().data or [])


def paged_rows(factory, page_size=1000):
    out, offset = [], 0
    while True:
        page = rows(factory().range(offset, offset + page_size - 1))
        out.extend(page)
        if len(page) < page_size:
            return out
        offset += page_size


def resolve_set_row(canonical_key):
    found = rows(public_read_client.table("sets").select("id,canonical_key,name,release_date").eq("canonical_key", canonical_key).limit(1))
    return found[0] if found else None


def window_point_count(index_history, days, end_date_str):
    if not index_history:
        return 0
    end = date.fromisoformat(end_date_str)
    if days is None:
        return len(index_history)
    start = (end - timedelta(days=days)).isoformat()
    return sum(1 for row in index_history if row["date"] >= start)


def audit_set(canonical_key):
    set_row = resolve_set_row(canonical_key)
    if not set_row:
        print(f"{canonical_key}: SET NOT FOUND")
        return

    products = rows(public_read_client.table("sealed_products").select("id,set_id,name,product_type").eq("set_id", set_row["id"]))
    product_ids = [p["id"] for p in products]
    observations = paged_rows(
        lambda: public_read_client.table("sealed_product_price_observations")
        .select("id,sealed_product_id,market_price,source,currency,captured_at")
        .in_("sealed_product_id", product_ids)
        .order("captured_at")
    ) if product_ids else []

    identities = [classify_sealed_product(p["name"]) for p in products]
    eligible_count = sum(i["isOverviewEligible"] for i in identities)

    result = build_snapshot(set_row, products, observations)
    payload = result["payload_json"]
    payload_products = payload["products"]  # eligible AND has >=1 observation

    if not payload_products:
        print(f"\n=== {canonical_key} ({set_row['name']}) ===")
        print(f"  raw products: {len(products)}  overview-eligible: {eligible_count}  with-history: 0")
        print("  NO ELIGIBLE PRODUCT HAS ANY OBSERVED PRICE HISTORY")
        return

    all_dates = sorted({point["date"] for p in payload_products for point in p["history"]})
    date_range_start, date_range_end = all_dates[0], all_dates[-1]
    calendar_days = (date.fromisoformat(date_range_end) - date.fromisoformat(date_range_start)).days + 1

    any_obs_days = len(all_dates)
    eligible_ids = {str(p["sealedProductId"]) for p in payload_products}
    by_date = {}
    for p in payload_products:
        for point in p["history"]:
            by_date.setdefault(point["date"], set()).add(str(p["sealedProductId"]))
    full_completeness_days = sum(1 for d in by_date if eligible_ids.issubset(by_date[d]))

    segment = build_sealed_segment_history(payload_products)
    index = segment.get("marketIndex") if segment else None
    index_history = index["history"] if index else []
    index_point_count = len(index_history)
    end_date_str = index_history[-1]["date"] if index_history else None

    print(f"\n=== {canonical_key} ({set_row['name']}) ===")
    print(f"  raw products: {len(products)}  overview-eligible: {eligible_count}  with-history (payload): {len(payload_products)}")
    print(f"  history range: {date_range_start} .. {date_range_end}  ({calendar_days} calendar days)")
    print(f"  any-observation days: {any_obs_days}   full-completeness days (all eligible priced same day): {full_completeness_days}")
    print(f"  current Tracked Value: {segment['currentValue'] if segment else None}   trackingSince: {segment['trackingSince'] if segment else None}")
    print(f"  index points (final, chain-linked): {index_point_count}")
    if index_history and end_date_str:
        for label, days in [("7D", 7), ("30D", 30), ("3M", 90), ("6M", 180), ("1Y", 365), ("All", None)]:
            print(f"    {label:4s}: {window_point_count(index_history, days, end_date_str)} index points")
    else:
        print("    NO INDEX POINTS AT ALL (no two consecutive fully-observed days)")

    # per-product latest observation date, to eyeball staleness
    print("  per-product latest observation:")
    for p in payload_products:
        print(f"    {p['name'][:50]:50s} latest={p['priceAsOf']}  points={len(p['history'])}")


for key in SETS:
    audit_set(key)
