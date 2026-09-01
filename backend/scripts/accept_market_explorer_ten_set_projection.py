"""Exact ten-set projection/interval comparison and API timing matrix."""
from __future__ import annotations

import json
import statistics
import time
from datetime import date, timedelta
from pathlib import Path

from backend.db.clients.supabase_client import create_service_role_client

INTERVAL = "get_pokemon_market_explorer_filtered_cohort"
DAILY = "get_pokemon_market_explorer_filtered_cohort_daily"
SETS = [
    "be7c981b-c55e-4f60-a1b8-be922531452d", "c86889c9-ea25-4caa-b63c-7aa0b9796da8",
    "8cd0a0f0-d17c-4a5c-bc52-47e1723e0699", "93212749-ce0e-498e-975e-7d947a3448ce",
    "1c7aa5c4-c8c9-4ae8-a1eb-d613f7e4b890", "75cd439d-aaa2-41cb-86f3-2fefa5b26e29",
    "f59f25a2-d3da-4100-a918-901271a99925", "dfcf6c98-1bf3-43a8-83a2-7e56b3c65d03",
    "75cc9ef9-1099-4e47-8d09-17f416606865", "3562f9c9-f879-4d49-9d69-d0ab511230f9",
]


def params(**overrides):
    return {**{"p_set_ids": SETS, "p_start_date": "2026-04-11", "p_end_date": "2026-08-31",
               "p_card_ids": None, "p_segment_ids": None, "p_pokemon_ids": None,
               "p_price_segment_ids": None, "p_release_age_cohort_ids": None,
               "p_top_n": None}, **overrides}


def chunked(client, rpc, value):
    first, last = date.fromisoformat(value["p_start_date"]), date.fromisoformat(value["p_end_date"])
    rows, cursor, previous = [], first, None
    while cursor <= last:
        # Ten-set interval fallback exceeds the statement timeout at the old
        # 30-day pilot chunk; seven days remains bounded and exact.
        end = min(last, cursor + timedelta(days=6))
        request = {**value, "p_start_date": previous or cursor.isoformat(), "p_end_date": end.isoformat()}
        page = list(client.rpc(rpc, request).execute().data or [])
        if previous:
            page = [row for row in page if str(row.get("market_date"))[:10] != previous]
        if page:
            rows.extend(page); previous = str(page[-1].get("market_date"))[:10]
        cursor = end + timedelta(days=1)
    return rows


def main() -> None:
    client = create_service_role_client()
    cases = {
        "full": params(), "top10": params(p_top_n=10),
        "rarity": params(p_segment_ids=["rareHolo"]),
        "rarityTop10": params(p_segment_ids=["rareHolo"], p_top_n=10),
        "premium": params(p_price_segment_ids=["premium"]),
        "established": params(p_release_age_cohort_ids=["established"]),
        "pokemon": params(p_pokemon_ids=[25]),
        "pokemonRarity": params(p_pokemon_ids=[25], p_segment_ids=["rareUltra"]),
        "price": params(p_price_segment_ids=["obtainable"]),
        "releasePrice": params(p_release_age_cohort_ids=["established"], p_price_segment_ids=["premium"]),
        "compound": params(p_segment_ids=["rareUltra"], p_price_segment_ids=["premium"]),
    }
    exact = {name: chunked(client, INTERVAL, value) == chunked(client, DAILY, value)
             for name, value in cases.items()}
    timings = {}
    for name in ("full", "top10", "rarity", "premium", "established", "pokemonRarity", "compound"):
        samples = []
        for _ in range(5):
            started = time.perf_counter(); client.rpc(DAILY, cases[name]).execute()
            samples.append((time.perf_counter() - started) * 1000)
        timings[name] = {"medianMs": statistics.median(samples), "p95Ms": max(samples), "samplesMs": samples}
    for name, top in (("current", None), ("currentTop25", 25)):
        value = params(p_start_date="2026-08-31", p_top_n=top)
        samples = []
        for _ in range(5):
            started = time.perf_counter(); client.rpc(INTERVAL, value).execute()
            samples.append((time.perf_counter() - started) * 1000)
        timings[name] = {"medianMs": statistics.median(samples), "p95Ms": max(samples), "samplesMs": samples}
    report = {"allExact": all(exact.values()), "correctness": exact, "performance": timings}
    output = Path("artifacts/market_explorer_acceptance/20260831_effort1k_ten_set.json")
    output.parent.mkdir(parents=True, exist_ok=True); output.write_text(json.dumps(report, indent=2))
    print(json.dumps(report, indent=2))


if __name__ == "__main__":
    main()
