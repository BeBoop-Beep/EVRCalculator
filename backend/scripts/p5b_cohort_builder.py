"""P5B.1: canonical-universe snapshot and stratified paired-development cohort planner.

Read-only. Reuses the P1 target shape and query generator; does not touch eBay or pricing tables.
"""
from __future__ import annotations

import argparse
import gzip
import hashlib
import json
from collections import Counter
from datetime import date
from pathlib import Path
from typing import Any, Mapping

from backend.scripts.index_fair_value_ebay_evidence_collector import generate_queries

ROOT = Path(__file__).resolve().parents[2]
OUT = ROOT / "backend/artifacts/pricing"
VERSION = "p5b_cohort_v1"
PRICE_BANDS = (("lt5", 0, 5), ("5_20", 5, 20), ("20_50", 20, 50), ("50_100", 50, 100),
               ("100_250", 100, 250), ("250_plus", 250, float("inf")))
PRICED_ROLES = {"main", "subset", "promo", "pack_variant"}
HIGH_RARITY = ("illustration", "secret", "ultra", "hyper", "rainbow", "special", "shiny", "gold")


def digest(value: Any) -> str:
    return hashlib.sha256(json.dumps(value, sort_keys=True, separators=(",", ":"), ensure_ascii=False).encode()).hexdigest()


def price_band(value: float | None) -> str:
    if value is None:
        return "missing"
    for name, low, high in PRICE_BANDS:
        if low <= value < high:
            return name
    return "missing"


def tcg_status(age_days: int | None, price: float | None) -> str:
    if price is None:
        return "missing"
    return "fresh" if age_days is not None and age_days <= 1 else "stale"


def structure(rarity: str | None) -> str:
    text = (rarity or "").casefold()
    if any(word in text for word in HIGH_RARITY):
        return "hit_special"
    if "holo" in text or "rare" in text:
        return "rare_holo"
    return "other"


def build_universe(cards, sets, eras, prices, market_date: date) -> list[dict[str, Any]]:
    sets_by = {str(r["id"]): r for r in sets}
    eras_by = {str(r["id"]): r for r in eras}
    prices_by = {str(r["canonical_card_id"]): r for r in prices}
    rows = []
    for card in cards:
        cid = str(card["id"])
        set_row = sets_by.get(str(card.get("set_id"))) or {}
        era = eras_by.get(str(set_row.get("era_id"))) or {}
        price = prices_by.get(cid)
        value = float(price["market_price"]) if price and price.get("market_price") is not None else None
        age = (market_date - date.fromisoformat(str(price["captured_at"])[:10])).days if price and price.get("captured_at") else None
        rows.append({
            "canonical_card_id": cid, "card_variant_id": price.get("card_variant_id") if price else None,
            "card_name": card.get("name"), "card_number": card.get("printed_number") or card.get("number"),
            "set_id": str(card.get("set_id")), "set_name": set_row.get("name"),
            "era_id": set_row.get("era_id"), "era": era.get("name"), "era_sort": era.get("sort_order"),
            "rarity": card.get("rarity") or "", "catalog_role": card.get("catalog_role"),
            "opening_eligible": card.get("opening_eligible") is True,
            "set_value_eligible": card.get("set_value_eligible") is True,
            "review_status": card.get("canonical_review_status"),
            "tcgplayer_market_price": value,
            "tcgplayer_captured_at": price.get("captured_at") if price else None,
            "tcgplayer_age_days": age, "tcg_status": tcg_status(age, value),
            "price_band": price_band(value), "structure": structure(card.get("rarity")),
        })
    return rows


def eligible_for_cohort(row: Mapping[str, Any]) -> bool:
    return (row["review_status"] == "approved" and row["catalog_role"] in {"main", "promo"}
            and bool(row["set_name"]) and bool(row["card_name"]))


def _rot(row: Mapping[str, Any], market_date: str) -> str:
    return digest([VERSION, market_date, row["canonical_card_id"]])


def select_cohort(universe: list[dict[str, Any]], market_date: str, quotas: Mapping[str, Any],
                  exclude: set[str] = frozenset()) -> list[dict[str, Any]]:
    """Deterministic, stratified pick.  Quotas: fresh per band, stale total, missing main/promo.

    Within a stratum, cards are ordered by a hash rotation and greedily round-robined across
    (era, structure) so no single era/rarity dominates.  Supply-limited strata simply return less.
    """
    pool = [r for r in universe if eligible_for_cohort(r) and r["canonical_card_id"] not in exclude]
    chosen: list[dict[str, Any]] = []

    def take(rows, n, label):
        rows = sorted(rows, key=lambda r: _rot(r, market_date))
        buckets: dict[tuple, list] = {}
        for r in rows:
            buckets.setdefault((r["era"], r["structure"]), []).append(r)
        order = sorted(buckets, key=lambda k: digest([VERSION, str(k)]))
        picked = []
        while len(picked) < n and any(buckets.values()):
            for key in order:
                if buckets[key] and len(picked) < n:
                    picked.append(buckets[key].pop(0))
        for r in picked:
            chosen.append({**r, "stratum": label})

    for band, n in quotas.get("fresh", {}).items():
        take([r for r in pool if r["tcg_status"] == "fresh" and r["price_band"] == band], n, f"fresh:{band}")
    take([r for r in pool if r["tcg_status"] == "stale"], quotas.get("stale", 0), "stale")
    take([r for r in pool if r["tcg_status"] == "missing" and r["catalog_role"] == "main" and r["opening_eligible"]],
         quotas.get("missing_main", 0), "missing:main")
    take([r for r in pool if r["tcg_status"] == "missing" and r["catalog_role"] == "promo"],
         quotas.get("missing_promo", 0), "missing:promo")
    return chosen


def to_target(row: Mapping[str, Any]) -> dict[str, Any]:
    target = {
        "pricing_target": True, "canonical_card_id": row["canonical_card_id"],
        "card_variant_id": row.get("card_variant_id"), "card_name": row["card_name"],
        "card_number": row["card_number"], "set_id": row["set_id"], "set_name": row["set_name"],
        "era_id": row["era_id"], "rarity": row["rarity"], "priority_reasons": [row["stratum"]],
        "tcgplayer_market_price": row["tcgplayer_market_price"],
        "tcgplayer_captured_at": row["tcgplayer_captured_at"], "tcgplayer_age_days": row["tcgplayer_age_days"],
        "stratum": row["stratum"],
    }
    target["planned_queries"] = generate_queries(target)
    target["estimated_request_cost"] = len(target["planned_queries"])
    return target


def manifest_for(targets: list[dict[str, Any]], market_date: str) -> dict[str, Any]:
    manifest = {"market_date": market_date, "selector_version": VERSION, "target_count": len(targets),
                "canonical_card_ids": [t["canonical_card_id"] for t in targets], "cards": targets}
    manifest["selector_fingerprint"] = digest(manifest)
    return manifest


def _paged(factory):
    rows, start = [], 0
    while True:
        page = list(factory().range(start, start + 999).execute().data or [])
        rows.extend(page)
        if len(page) < 1000:
            return rows
        start += 1000


def fetch_universe(market_date: date) -> list[dict[str, Any]]:
    from dotenv import load_dotenv
    from backend.db.clients.supabase_client import create_service_role_client
    load_dotenv(ROOT / "backend/.env", override=False)
    client = create_service_role_client()
    cards = _paged(lambda: client.table("pokemon_canonical_cards").select(
        "id,set_id,name,number,printed_number,rarity,catalog_role,opening_eligible,set_value_eligible,canonical_review_status").order("id"))
    sets = _paged(lambda: client.table("sets").select("id,name,era_id").order("id"))
    eras = _paged(lambda: client.table("eras").select("id,name,sort_order").order("id"))
    prices = _paged(lambda: client.table("pokemon_canonical_card_market_prices_latest").select(
        "canonical_card_id,card_variant_id,market_price,captured_at,source").order("canonical_card_id"))
    if any(row.get("source") not in (None, "TCGPlayer") for row in prices):
        raise RuntimeError("canonical price source is no longer exclusively TCGPlayer")
    return build_universe(cards, sets, eras, prices, market_date)


def main(argv: list[str] | None = None) -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--market-date", type=date.fromisoformat, default=date.today())
    args = parser.parse_args(argv)
    universe = fetch_universe(args.market_date)
    OUT.mkdir(parents=True, exist_ok=True)
    path = OUT / f"p5b_universe_{args.market_date.isoformat()}.json.gz"
    with gzip.open(path, "wt", encoding="utf-8") as fh:
        json.dump({"market_date": args.market_date.isoformat(), "rows": universe}, fh)
    print(json.dumps({"path": str(path), "rows": len(universe),
                      "tcg_status": Counter(r["tcg_status"] for r in universe)}, default=dict, indent=2))


if __name__ == "__main__":
    main()
