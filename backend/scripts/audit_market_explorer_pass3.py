"""Read-only capability and distribution audit for Market Explorer Pass 3."""

from __future__ import annotations

import json
import os
from collections import Counter, defaultdict
from datetime import date
from pathlib import Path
from statistics import median

from dotenv import load_dotenv


def _all(client, table: str, columns: str, *, page_size: int = 1000):
    rows, start = [], 0
    while True:
        page = list(client.table(table).select(columns).range(start, start + page_size - 1).execute().data or [])
        rows.extend(page)
        if len(page) < page_size:
            return rows
        start += page_size


def _percentiles(values):
    ordered = sorted(float(value) for value in values if value is not None and float(value) > 0)
    if not ordered:
        return {}
    def at(p):
        return round(ordered[min(len(ordered) - 1, int((len(ordered) - 1) * p))], 2)
    return {"n": len(ordered), "min": ordered[0], "p25": at(.25), "median": round(median(ordered), 2), "p75": at(.75), "p90": at(.9), "p95": at(.95), "max": ordered[-1]}


def _band_counts(values, low_upper, middle_upper):
    prices = [float(value) for value in values if value is not None and float(value) > 0]
    return {
        "obtainable": sum(value < low_upper for value in prices),
        "intermediate": sum(low_upper <= value < middle_upper for value in prices),
        "premium": sum(value >= middle_upper for value in prices),
    }


def main():
    fallback = Path(r"D:\EVRCalculator\backend\.env")
    load_dotenv(os.getenv("MARKET_EXPLORER_AUDIT_ENV") or (fallback if fallback.exists() else None))
    from backend.db.clients.supabase_client import service_read_client as client

    references = _all(client, "pokemon_reference", "id,pokedex_number,canonical_name,display_name")
    links = _all(client, "pokemon_card_desirability_links", "pokemon_canonical_card_id,pokemon_reference_id,link_position,link_count,source")
    cards = _all(client, "pokemon_canonical_cards", "id,set_id,rarity")
    sets = _all(client, "sets", "id,name,era_id,release_date")
    card_prices = _all(client, "pokemon_canonical_card_market_prices_latest", "canonical_card_id,market_price,captured_at")
    sealed_rows = _all(client, "pokemon_set_sealed_market_snapshot_latest", "set_id,market_date,payload_json")

    cards_by_id = {str(row["id"]): row for row in cards}
    reference_by_id = {str(row["id"]): row for row in references}
    link_counts = Counter(str(row["pokemon_canonical_card_id"]) for row in links)
    pokemon_sets = defaultdict(set)
    for row in links:
        card = cards_by_id.get(str(row["pokemon_canonical_card_id"]))
        if card:
            pokemon_sets[str(row["pokemon_reference_id"])].add(str(card["set_id"]))

    sealed_prices = []
    sealed_products = 0
    for row in sealed_rows:
        for product in (row.get("payload_json") or {}).get("products") or []:
            sealed_products += 1
            history = product.get("history") or []
            if history:
                sealed_prices.append(history[-1].get("marketPrice"))

    today = date.today()
    ages = []
    missing_release = 0
    for row in sets:
        if not row.get("release_date"):
            missing_release += 1
            continue
        ages.append((today - date.fromisoformat(str(row["release_date"])[:10])).days)

    card_values = [row.get("market_price") for row in card_prices]
    release_counts = {
        "new_0_180": sum(value <= 180 for value in ages),
        "recent_181_730": sum(180 < value <= 730 for value in ages),
        "established_731_1825": sum(730 < value <= 1825 for value in ages),
        "legacy_1826_plus": sum(value > 1825 for value in ages),
    }
    report = {
        "pokemonAuthority": {
            "references": len(references), "links": len(links),
            "linkedCards": len(link_counts), "multiSubjectCards": sum(count > 1 for count in link_counts.values()),
            "linkSources": dict(Counter(str(row.get("source")) for row in links)),
            "dragonite": [
                {"id": str(row["id"]), "name": row["display_name"], "eligibleSetCount": len(pokemon_sets[str(row["id"])])}
                for row in references if str(row.get("canonical_name", "")).casefold() == "dragonite"
            ],
        },
        "cards": {"catalogueCount": len(cards), "latestPriceDistribution": _percentiles(card_values), "fixedBandCounts10And100": _band_counts(card_values, 10, 100)},
        "sealed": {"snapshotSetCount": len(sealed_rows), "productCount": sealed_products, "latestPriceDistribution": _percentiles(sealed_prices), "fixedBandCounts100And500": _band_counts(sealed_prices, 100, 500)},
        "releaseDates": {"setCount": len(sets), "missing": missing_release, "ageDaysDistribution": _percentiles(ages), "candidateCohortCounts": release_counts},
        "compatibility": {"pokemonWithLinkedSets": sum(bool(value) for value in pokemon_sets.values())},
    }
    print(json.dumps(report, indent=2, sort_keys=True))


if __name__ == "__main__":
    main()
