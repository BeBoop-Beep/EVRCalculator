"""Bounded shallow-search / selective-getItem pricing development capture."""
from __future__ import annotations

import argparse
import hashlib
import json
import urllib.parse
import uuid
from collections import Counter
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

from backend.scripts import ebay_d3_matcher_v5
from backend.scripts.ebay_english_price_eligibility_v1 import resolve, fingerprint as eligibility_fingerprint
from backend.scripts.index_fair_value_ebay_evidence_collector import (
    BrowseHTTP, BudgetExhausted, CollectorConfig, DailyBrowseLedger, RunCounters, TokenProvider, _search_url,
    generate_queries, load_ebay_env,
)

ROOT = Path(__file__).resolve().parents[2]
OUT = ROOT / "backend/artifacts/pricing"
ITEM_URL = "https://api.ebay.com/buy/browse/v1/item/"
VERSION = "ebay_p4a_adaptive_capture_v1"


def _band(card: dict[str, Any]) -> str:
    value = card.get("tcgplayer_market_price")
    return "missing" if value is None else "low" if value < 20 else "mid" if value < 100 else "high"


def choose_cohort(manifest: dict[str, Any], count: int = 30) -> list[dict[str, Any]]:
    cards = manifest["cards"]
    chosen: list[dict[str, Any]] = []
    seen = set()

    def add(card):
        if card["canonical_card_id"] not in seen and len(chosen) < count:
            chosen.append(card)
            seen.add(card["canonical_card_id"])

    # First cover eras, then ensure each price band, then use selector order.
    for era in sorted({str(card.get("era_id")) for card in cards}):
        for card in cards:
            if str(card.get("era_id")) == era:
                add(card)
                break
    for band, quota in (("missing", 5), ("low", 5), ("mid", 5), ("high", 5)):
        for card in cards:
            if sum(_band(x) == band for x in chosen) >= quota:
                break
            if _band(card) == band:
                add(card)
    for card in cards:
        add(card)
    return chosen


def candidate_rank(rows: list[dict[str, Any]], target: dict[str, Any]) -> list[dict[str, Any]]:
    """Identity/fixed-price gate, then seller-diverse and price-neighborhood order."""
    candidates = []
    seen_items = set()
    market = target.get("tcgplayer_market_price")
    for item in rows:
        item_id = item.get("itemId")
        if not item_id or item_id in seen_items:
            continue
        seen_items.add(item_id)
        identity = ebay_d3_matcher_v5.classify_listing(target, item)
        options = set(item.get("buyingOptions") or [])
        price = item.get("price") or {}
        shipping = (item.get("shippingOptions") or [{}])[0].get("shippingCost") or {}
        if identity.get("identity_state") != "HIGH_CONFIDENCE" or "FIXED_PRICE" not in options or "AUCTION" in options:
            continue
        if price.get("currency") != "USD" or price.get("value") is None:
            continue
        try:
            amount = float(price["value"])
        except (TypeError, ValueError):
            continue
        if amount <= 0:
            continue
        seller = str((item.get("seller") or {}).get("username") or "").casefold()
        shipping_known = shipping.get("currency") == "USD" and shipping.get("value") is not None
        ratio_distance = abs(__import__("math").log(amount / float(market))) if market and float(market) > 0 else 0
        candidates.append({"item": item, "identity": identity, "seller": seller,
                           "rank_key": (not shipping_known, round(ratio_distance, 4), item_id)})
    candidates.sort(key=lambda row: row["rank_key"])
    first_per_seller, rest = [], []
    used = set()
    for row in candidates:
        seller = row["seller"] or row["item"]["itemId"]
        if seller not in used:
            first_per_seller.append(row)
            used.add(seller)
        else:
            rest.append(row)
    return first_per_seller + rest


def collect(manifest: dict[str, Any], *, target_count: int = 30, request_cap: int = 400,
            details_per_target: int = 8, stop_sellers: int = 3,
            http: BrowseHTTP | None = None) -> dict[str, Any]:
    if not 1 <= request_cap <= 1000 or not 1 <= target_count <= 40:
        raise ValueError("unsafe request or target bound")
    material = {key: value for key, value in manifest.items() if key != "selector_fingerprint"}
    if hashlib.sha256(json.dumps(material, sort_keys=True, separators=(",", ":"), ensure_ascii=False).encode()).hexdigest() != manifest.get("selector_fingerprint"):
        raise ValueError("selector manifest fingerprint mismatch")
    cards = choose_cohort(manifest, target_count)
    config = CollectorConfig(max_requests_per_day=1000, max_requests_per_run=request_cap, max_pages_per_search=1)
    http = http or BrowseHTTP(TokenProvider(load_ebay_env()), config,
                             daily_ledger=DailyBrowseLedger(OUT / "ebay_browse_daily_usage.sqlite3"))
    counters = RunCounters(remaining_run_budget=request_cap)
    run_id = uuid.uuid4().hex
    all_rows = []
    raw_path = OUT / f"ebay_p4a_{run_id}.raw.jsonl"
    decisions_path = OUT / f"ebay_p4a_{run_id}.decisions.jsonl"
    OUT.mkdir(parents=True, exist_ok=True)
    global_items = set()
    with raw_path.open("w", encoding="utf-8") as raw_fh, decisions_path.open("w", encoding="utf-8") as decision_fh:
        for target in cards:
            cid = target["canonical_card_id"]
            search_items = []
            search_calls = 0
            for query in generate_queries(target):
                if search_calls >= 1 and len(candidate_rank(search_items, target)) >= 5:
                    break
                if counters.remaining_run_budget <= 0:
                    break
                try:
                    outcome = http.get(_search_url(query), counters)
                except BudgetExhausted:
                    break
                search_calls += 1
                if outcome.ok:
                    for item in (outcome.data or {}).get("itemSummaries") or []:
                        search_items.append(item)
                        raw_fh.write(json.dumps({"kind": "search_summary", "target_id": cid,
                                                 "formulation": query["formulation"], "item": item}, ensure_ascii=False) + "\n")
            candidates = candidate_rank(search_items, target)
            eligible_sellers = set()
            hydrated = 0
            decisions = []
            for candidate in candidates:
                if hydrated >= details_per_target or len(eligible_sellers) >= stop_sellers or counters.remaining_run_budget <= 0:
                    break
                item = candidate["item"]
                item_id = item["itemId"]
                if item_id in global_items:
                    continue
                global_items.add(item_id)
                url = ITEM_URL + urllib.parse.quote(item_id, safe="")
                try:
                    outcome = http.get(url, counters)
                except BudgetExhausted:
                    break
                hydrated += 1
                if not outcome.ok:
                    decision = {"item_id": item_id, "target_id": cid, "state": "LANGUAGE_UNRESOLVED",
                                "reason": f"getitem_failed_{outcome.status or outcome.error_type}"}
                else:
                    detail = outcome.data or {}
                    captured_at = datetime.now(timezone.utc).isoformat()
                    raw_fh.write(json.dumps({"kind": "get_item", "target_id": cid, "item_id": item_id,
                                             "captured_at": captured_at, "item": detail}, ensure_ascii=False) + "\n")
                    identity = ebay_d3_matcher_v5.classify_listing(target, detail)
                    decision = resolve(detail, text_state=identity.get("identity_state") or "REJECTED")
                    decision.update({"item_id": item_id, "target_id": cid,
                                     "captured_at": captured_at,
                                     "seller_key_sha256": hashlib.sha256(candidate["seller"].encode()).hexdigest() if candidate["seller"] else None,
                                     "seller_feedback_score": (detail.get("seller") or {}).get("feedbackScore"),
                                     "seller_feedback_percentage": (detail.get("seller") or {}).get("feedbackPercentage"),
                                     "listing_url": detail.get("itemWebUrl"),
                                     "image_url": (detail.get("image") or {}).get("imageUrl")})
                    if decision["state"] == "ENGLISH_PRICE_ELIGIBLE":
                        eligible_sellers.add(candidate["seller"] or item_id)
                decisions.append(decision)
                decision_fh.write(json.dumps(decision, ensure_ascii=False) + "\n")
            counts = Counter(row["state"] for row in decisions)
            all_rows.append({"canonical_card_id": cid, "card_variant_id": target.get("card_variant_id"),
                             "set_id": target.get("set_id"), "era_id": target.get("era_id"),
                             "tcgplayer_market_price": target.get("tcgplayer_market_price"),
                             "price_band": _band(target), "raw_search_listings": len(search_items),
                             "candidate_count": len(candidates), "search_calls": search_calls,
                             "detail_calls": hydrated, "eligible_seller_count": len(eligible_sellers),
                             "state_counts": dict(counts)})
    result = {"version": VERSION, "run_id": run_id, "market_date": manifest["market_date"],
              "selector_fingerprint": manifest["selector_fingerprint"],
              "eligibility_policy_fingerprint": eligibility_fingerprint(),
              "request_cap": request_cap, "requests_attempted": counters.requests_attempted,
              "requests_successful": counters.requests_successful, "requests_failed": counters.requests_failed,
              "retries": counters.retries, "targets": all_rows,
              "raw_artifact_path": str(raw_path), "decisions_artifact_path": str(decisions_path)}
    result["capture_fingerprint"] = hashlib.sha256(json.dumps(result, sort_keys=True).encode()).hexdigest()
    (OUT / f"ebay_p4a_{run_id}.json").write_text(json.dumps(result, indent=2) + "\n", encoding="utf-8")
    return result


def main(argv: list[str] | None = None) -> dict[str, Any]:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--manifest", type=Path, default=OUT / "ebay_daily_pricing_targets_2026-09-19.json")
    parser.add_argument("--targets", type=int, default=30)
    parser.add_argument("--request-cap", type=int, default=400)
    args = parser.parse_args(argv)
    manifest = json.loads(args.manifest.read_text(encoding="utf-8"))
    result = collect(manifest, target_count=args.targets, request_cap=args.request_cap)
    print(json.dumps({"run_id": result["run_id"], "targets": len(result["targets"]),
                      "requests_attempted": result["requests_attempted"],
                      "raw_artifact_path": result["raw_artifact_path"],
                      "decisions_artifact_path": result["decisions_artifact_path"]}, indent=2))
    return result


if __name__ == "__main__":
    main()
