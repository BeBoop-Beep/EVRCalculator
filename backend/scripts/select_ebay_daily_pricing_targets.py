"""Read-only, deterministic English Pokémon pricing target planner."""
from __future__ import annotations

import argparse
import hashlib
import json
from collections import Counter
from datetime import date, timedelta
from pathlib import Path
from typing import Any, Mapping

from backend.scripts.index_fair_value_ebay_evidence_collector import generate_queries

ROOT = Path(__file__).resolve().parents[2]
OUTPUT_DIR = ROOT / "backend/artifacts/pricing"
SELECTOR_VERSION = "ebay_daily_pricing_selector_p1_v1"
HIGH_RARITY = ("illustration", "secret", "ultra", "hyper", "rainbow", "special", "rare holo", "shiny", "gold")


def _hash(value: Any) -> str:
    return hashlib.sha256(json.dumps(value, sort_keys=True, separators=(",", ":"), ensure_ascii=False).encode()).hexdigest()


def _age(value: Any, market_date: date) -> int | None:
    if not value:
        return None
    return (market_date - date.fromisoformat(str(value)[:10])).days


def plan(cards: list[Mapping[str, Any]], sets: list[Mapping[str, Any]],
         prices: list[Mapping[str, Any]], market_date: date, *, ceiling: int = 900,
         pages_per_query: int = 3, recent_events: list[Mapping[str, Any]] | None = None) -> dict[str, Any]:
    if ceiling < 0 or pages_per_query < 1:
        raise ValueError("invalid request plan")
    sets_by = {str(row["id"]): row for row in sets}
    prices_by = {str(row["canonical_card_id"]): row for row in prices}
    events_by: dict[str, list[Mapping[str, Any]]] = {}
    for event in recent_events or []:
        if event.get("card_variant_id") and event.get("market_price") is not None:
            events_by.setdefault(str(event["card_variant_id"]), []).append(event)
    candidates = []
    seen = set()
    for card in cards:
        cid = str(card["id"])
        if cid in seen:
            raise ValueError(f"duplicate canonical card: {cid}")
        seen.add(cid)
        set_row = sets_by.get(str(card.get("set_id")))
        if not set_row or not set_row.get("name") or not card.get("name"):
            continue
        if card.get("canonical_review_status") != "approved" or card.get("catalog_role") != "main":
            continue
        price = prices_by.get(cid, {})
        value = float(price["market_price"]) if price.get("market_price") is not None else None
        age = _age(price.get("captured_at"), market_date)
        rarity = str(card.get("rarity") or "")
        high_rarity = any(word in rarity.casefold() for word in HIGH_RARITY)
        opening = card.get("opening_eligible") is True
        set_value = card.get("set_value_eligible") is True
        low_rarity = rarity.casefold() in {"common", "uncommon", "promo", "energy"} or not rarity
        relevant = high_rarity or (value is not None and value >= 20) or (opening and not low_rarity)
        if not relevant:
            continue
        reasons = []
        if value is None or value <= 0:
            reasons.append("IMPORTANT_PRICE_GAP")
        if age is None or age >= 14:
            reasons.append("STALE_TCGPLAYER_PRICE")
        history = sorted(events_by.get(str(price.get("card_variant_id")), []),
                         key=lambda row: (str(row.get("effective_date")), str(row.get("id"))))
        history_values = [float(row["market_price"]) for row in history if float(row["market_price"]) > 0]
        if len(history_values) >= 2:
            first, last = history_values[0], history_values[-1]
            if abs(last - first) >= 5 and abs(last / first - 1) >= .2:
                reasons.append("RECENT_MEANINGFUL_MOVER")
            if (max(history_values) - min(history_values)) >= 5 and max(history_values) / min(history_values) - 1 >= .3:
                reasons.append("RECENT_HIGH_VOLATILITY")
        if value is not None and value >= 50:
            reasons.append("HIGH_VALUE")
        if high_rarity:
            reasons.append("HIGH_RARITY_CHASE")
        if opening:
            reasons.append("OPENING_EV_INPUT")
        if set_value:
            reasons.append("SET_VALUE_INPUT")
        if not any(reason in reasons for reason in ("IMPORTANT_PRICE_GAP", "STALE_TCGPLAYER_PRICE", "HIGH_VALUE", "HIGH_RARITY_CHASE", "RECENT_MEANINGFUL_MOVER", "RECENT_HIGH_VOLATILITY")):
            reasons.append("ROTATIONAL_COVERAGE")
        target = {
            "pricing_target": True, "canonical_card_id": cid,
            "card_variant_id": price.get("card_variant_id"),
            "card_name": card["name"], "card_number": card.get("printed_number") or card.get("number"),
            "set_id": str(card["set_id"]), "set_name": set_row["name"],
            "era_id": set_row.get("era_id"), "rarity": rarity,
            "priority_reasons": reasons,
            "tcgplayer_market_price": value, "tcgplayer_captured_at": price.get("captured_at"),
            "tcgplayer_age_days": age,
        }
        target["planned_queries"] = generate_queries(target)
        target["estimated_request_cost"] = len(target["planned_queries"]) * pages_per_query
        rotation = _hash([market_date.isoformat(), cid])
        tier = 0 if "IMPORTANT_PRICE_GAP" in reasons else (1 if any(r in reasons for r in ("STALE_TCGPLAYER_PRICE", "RECENT_MEANINGFUL_MOVER", "RECENT_HIGH_VOLATILITY")) else (2 if "HIGH_VALUE" in reasons or high_rarity else 3))
        candidates.append((tier, -(value or 0) if tier == 2 else 0, rotation, cid, target))
    candidates.sort(key=lambda row: row[:4])
    chosen = []
    cost = 0
    priority_limit = ceiling * 4 // 5
    for tier_group, group_limit in ((lambda tier: tier < 3, priority_limit),
                                    (lambda tier: tier == 3, ceiling)):
        for tier, _, _, _, target in candidates:
            if not tier_group(tier):
                continue
            added = target["estimated_request_cost"]
            if cost + added <= group_limit:
                chosen.append(target)
                cost += added
    if cost < ceiling:
        selected = {x["canonical_card_id"] for x in chosen}
        for _, _, _, cid, target in candidates:
            if cid not in selected and cost + target["estimated_request_cost"] <= ceiling:
                chosen.append(target)
                cost += target["estimated_request_cost"]
    reasons_count = Counter(reason for row in chosen for reason in row["priority_reasons"])
    manifest = {
        "market_date": market_date.isoformat(), "selector_version": SELECTOR_VERSION,
        "target_count": len(chosen), "canonical_card_ids": [x["canonical_card_id"] for x in chosen],
        "estimated_requests": cost, "planning_ceiling": ceiling,
        "max_pages_per_search": pages_per_query,
        "reason_counts": dict(sorted(reasons_count.items())),
        "set_count": len({x["set_id"] for x in chosen}),
        "era_count": len({x["era_id"] for x in chosen if x["era_id"]}),
        "candidate_count": len(candidates), "cards": chosen,
    }
    manifest["selector_fingerprint"] = _hash(manifest)
    return manifest


def _paged(factory):
    rows = []
    start = 0
    while True:
        page = list(factory().range(start, start + 999).execute().data or [])
        rows.extend(page)
        if len(page) < 1000:
            return rows
        start += 1000


def main(argv: list[str] | None = None) -> dict[str, Any]:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--market-date", type=date.fromisoformat, default=date.today())
    parser.add_argument("--ceiling", type=int, default=900)
    parser.add_argument("--output", type=Path)
    args = parser.parse_args(argv)
    from dotenv import load_dotenv
    from backend.db.clients.supabase_client import create_service_role_client
    load_dotenv(ROOT / "backend/.env", override=False)
    client = create_service_role_client()
    cards = _paged(lambda: client.table("pokemon_canonical_cards").select(
        "id,set_id,name,number,printed_number,rarity,catalog_role,opening_eligible,set_value_eligible,canonical_review_status").order("id"))
    sets = _paged(lambda: client.table("sets").select("id,name,era_id").order("id"))
    prices = _paged(lambda: client.table("pokemon_canonical_card_market_prices_latest").select(
        "canonical_card_id,card_variant_id,market_price,captured_at,source").order("canonical_card_id"))
    if any(row.get("source") not in (None, "TCGPlayer", "TCGPLAYER", "tcgplayer") for row in prices):
        raise RuntimeError("current canonical price source is no longer exclusively TCGplayer")
    window_start = (args.market_date - timedelta(days=30)).isoformat()
    events = list(client.table("card_variant_price_events_v2").select(
        "id,card_variant_id,effective_date,market_price,source").gte("effective_date", window_start).lte(
        "effective_date", args.market_date.isoformat()).eq("source", "TCGPlayer")
        .order("effective_date", desc=True).order("id", desc=True).range(0, 999).execute().data or [])
    manifest = plan(cards, sets, prices, args.market_date, ceiling=args.ceiling, recent_events=events)
    manifest["recent_event_sample_count"] = len(events)
    manifest["recent_event_sample_limit"] = 1000
    manifest["selector_fingerprint"] = _hash({key: value for key, value in manifest.items() if key != "selector_fingerprint"})
    OUTPUT_DIR.mkdir(parents=True, exist_ok=True)
    path = args.output or OUTPUT_DIR / f"ebay_daily_pricing_targets_{args.market_date.isoformat()}.json"
    path.write_text(json.dumps(manifest, indent=2, ensure_ascii=False) + "\n", encoding="utf-8")
    print(json.dumps({"path": str(path), "target_count": manifest["target_count"],
                      "estimated_requests": manifest["estimated_requests"],
                      "selector_fingerprint": manifest["selector_fingerprint"]}, indent=2))
    return manifest


if __name__ == "__main__":
    main()
