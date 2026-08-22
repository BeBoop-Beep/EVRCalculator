"""Read-only: sealed product observation-interval cadence, across many sets."""
import sys
sys.path.insert(0, "D:/EVRCalculator")

from collections import Counter
from datetime import date

from backend.db.clients.supabase_client import public_read_client
from backend.db.services.pokemon_set_sealed_market_snapshot_service import normalize_daily_history
from backend.domain.pokemon.sealed_product_classifier import classify_sealed_product

SETS = ["pitchBlack", "destinedRivals", "prismaticEvolutions", "surgingSparks", "shroudedFable", "twilightMasquerade", "stellarCrown", "journeyTogether"]


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


all_intervals = []
per_product_examples = []

for key in SETS:
    set_rows = rows(public_read_client.table("sets").select("id,name").eq("canonical_key", key).limit(1))
    if not set_rows:
        continue
    set_row = set_rows[0]
    products = rows(public_read_client.table("sealed_products").select("id,name").eq("set_id", set_row["id"]))
    ids = [p["id"] for p in products]
    if not ids:
        continue
    identities = {p["id"]: classify_sealed_product(p["name"]) for p in products}
    observations = paged_rows(
        lambda: public_read_client.table("sealed_product_price_observations")
        .select("sealed_product_id,market_price,source,currency,captured_at")
        .in_("sealed_product_id", ids)
        .order("captured_at")
    )
    by_product = {}
    for o in observations:
        by_product.setdefault(o["sealed_product_id"], []).append(o)

    for pid, obs in by_product.items():
        if not identities.get(pid, {}).get("isOverviewEligible"):
            continue
        history = normalize_daily_history(obs)
        if len(history) < 2:
            continue
        dates = [date.fromisoformat(h["date"]) for h in history]
        intervals = [(dates[i + 1] - dates[i]).days for i in range(len(dates) - 1)]
        all_intervals.extend(intervals)
        gap_max = max(intervals)
        name = next((p["name"] for p in products if p["id"] == pid), pid)
        latest_date = dates[-1]
        days_since_latest = (date(2026, 8, 22) - latest_date).days
        per_product_examples.append((f"{key}/{name[:40]}", len(history), gap_max, days_since_latest))

all_intervals.sort()
n = len(all_intervals)
if n:
    median = all_intervals[n // 2]
    p90 = all_intervals[int(n * 0.9)]
    p99 = all_intervals[int(n * 0.99)] if n >= 100 else all_intervals[-1]
    print(f"total intervals sampled: {n}")
    print(f"median interval: {median} day(s)")
    print(f"90th percentile interval: {p90} day(s)")
    print(f"99th percentile / max: {p99} / {all_intervals[-1]} day(s)")
    print(f"distribution (days -> count): {dict(Counter(all_intervals).most_common(15))}")
else:
    print("no intervals sampled")

print("\nper-product: name, observed_days, max_gap_days, days_since_latest_as_of_2026-08-22")
per_product_examples.sort(key=lambda row: -row[3])
for row in per_product_examples:
    print(f"  {row[0]:60s} obs={row[1]:4d}  max_gap={row[2]:3d}  days_since_latest={row[3]:4d}")
