"""Bounded additional getItem calls for P4B seller-depth sensitivity."""
from __future__ import annotations

import argparse
import hashlib
import json
import urllib.parse
from collections import defaultdict
from datetime import datetime, timezone
from pathlib import Path

from backend.scripts import ebay_d3_matcher_v5
from backend.scripts.ebay_english_price_eligibility_v1 import resolve
from backend.scripts.index_fair_value_ebay_evidence_collector import BrowseHTTP, BudgetExhausted, CollectorConfig, DailyBrowseLedger, RunCounters, TokenProvider, load_ebay_env
from backend.scripts.run_ebay_p4a_adaptive_development import OUT, ITEM_URL, candidate_rank


def run(base_run_id: str, manifest_path: Path, *, request_cap: int = 80, stop_sellers: int = 5,
        extra_per_target: int = 8, http=None) -> dict:
    if not 1 <= request_cap <= 1000:
        raise ValueError("invalid request cap")
    base = json.loads((OUT / f"ebay_p4a_{base_run_id}.json").read_text(encoding="utf-8"))
    manifest = json.loads(manifest_path.read_text(encoding="utf-8"))
    cards = {x["canonical_card_id"]: x for x in manifest["cards"]}
    search = defaultdict(list)
    for line in (OUT / f"ebay_p4a_{base_run_id}.raw.jsonl").read_text(encoding="utf-8").splitlines():
        row = json.loads(line)
        if row["kind"] == "search_summary":
            search[row["target_id"]].append(row["item"])
    prior = defaultdict(list)
    for line in (OUT / f"ebay_p4a_{base_run_id}.decisions.jsonl").read_text(encoding="utf-8").splitlines():
        row = json.loads(line)
        prior[row["target_id"]].append(row)
    selected = [row for row in base["targets"] if row["eligible_seller_count"] >= 3]
    cfg = CollectorConfig(max_requests_per_day=1000, max_requests_per_run=request_cap)
    http = http or BrowseHTTP(TokenProvider(load_ebay_env()), cfg,
                             daily_ledger=DailyBrowseLedger(OUT / "ebay_browse_daily_usage.sqlite3"))
    counters = RunCounters(remaining_run_budget=request_cap)
    raw_path = OUT / f"ebay_p4a_{base_run_id}.extension.raw.jsonl"
    decision_path = OUT / f"ebay_p4a_{base_run_id}.extension.decisions.jsonl"
    summary = []
    with raw_path.open("w", encoding="utf-8") as raw_fh, decision_path.open("w", encoding="utf-8") as decision_fh:
        for target_row in selected:
            cid = target_row["canonical_card_id"]
            sellers = {row.get("seller_key_sha256") or row["item_id"] for row in prior[cid]
                       if row["state"] == "ENGLISH_PRICE_ELIGIBLE"}
            seen = {row["item_id"] for row in prior[cid]}
            added = 0
            for candidate in candidate_rank(search[cid], cards[cid]):
                if len(sellers) >= stop_sellers or added >= extra_per_target or counters.remaining_run_budget <= 0:
                    break
                item_id = candidate["item"]["itemId"]
                if item_id in seen:
                    continue
                seen.add(item_id)
                try:
                    outcome = http.get(ITEM_URL + urllib.parse.quote(item_id, safe=""), counters)
                except BudgetExhausted:
                    break
                added += 1
                if not outcome.ok:
                    decision = {"target_id": cid, "item_id": item_id, "state": "LANGUAGE_UNRESOLVED",
                                "reason": f"getitem_failed_{outcome.status or outcome.error_type}"}
                else:
                    detail = outcome.data or {}
                    captured_at = datetime.now(timezone.utc).isoformat()
                    raw_fh.write(json.dumps({"kind": "get_item", "target_id": cid, "item_id": item_id,
                                             "captured_at": captured_at, "item": detail}, ensure_ascii=False) + "\n")
                    identity = ebay_d3_matcher_v5.classify_listing(cards[cid], detail)
                    decision = resolve(detail, text_state=identity.get("identity_state") or "REJECTED")
                    decision.update({"target_id": cid, "item_id": item_id,
                                     "captured_at": captured_at,
                                     "seller_key_sha256": hashlib.sha256(candidate["seller"].encode()).hexdigest() if candidate["seller"] else None,
                                     "seller_feedback_score": (detail.get("seller") or {}).get("feedbackScore"),
                                     "seller_feedback_percentage": (detail.get("seller") or {}).get("feedbackPercentage"),
                                     "listing_url": detail.get("itemWebUrl"),
                                     "image_url": (detail.get("image") or {}).get("imageUrl")})
                    if decision["state"] == "ENGLISH_PRICE_ELIGIBLE":
                        sellers.add(decision.get("seller_key_sha256") or item_id)
                decision_fh.write(json.dumps(decision, ensure_ascii=False) + "\n")
            summary.append({"canonical_card_id": cid, "additional_detail_calls": added,
                            "eligible_seller_count_after": len(sellers)})
    result = {"base_run_id": base_run_id, "request_cap": request_cap,
              "requests_attempted": counters.requests_attempted, "requests_successful": counters.requests_successful,
              "requests_failed": counters.requests_failed, "retries": counters.retries,
              "targets": summary, "raw_artifact_path": str(raw_path), "decisions_artifact_path": str(decision_path)}
    (OUT / f"ebay_p4a_{base_run_id}.extension.json").write_text(json.dumps(result, indent=2) + "\n", encoding="utf-8")
    return result


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--base-run-id", required=True)
    parser.add_argument("--manifest", type=Path, default=OUT / "ebay_daily_pricing_targets_2026-09-19.json")
    args = parser.parse_args()
    print(json.dumps(run(args.base_run_id, args.manifest), indent=2))
