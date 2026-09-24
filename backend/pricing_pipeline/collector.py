"""Resumable adaptive eBay collector (P2 shallow search + P4A selective getItem), one durable checkpoint per target.

The per-target logic is the P4A adaptive capture, unchanged (candidate ranking, eligibility policy, seller-distinct
stop). What P6 adds: no 40-target cap, a persistent request budget, and a checkpoint so a crashed or resumed run skips
every target that already completed instead of repeating network work.
"""
from __future__ import annotations

import hashlib
import json
import os
import urllib.parse
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Mapping

from backend.pricing_pipeline.contracts import DETAILS_PER_TARGET, STOP_SELLERS
from backend.pricing_pipeline.targets import with_queries
from backend.scripts import ebay_d3_matcher_v5
from backend.scripts.ebay_english_price_eligibility_v1 import resolve
from backend.scripts.index_fair_value_ebay_evidence_collector import BudgetExhausted, RunCounters, _search_url
from backend.scripts.run_ebay_p4a_adaptive_development import ITEM_URL, candidate_rank


class CollectionCheckpoint:
    """Append-only JSONL of completed targets plus a raw provider-response log (VM state directory only)."""

    def __init__(self, directory: Path) -> None:
        self.dir = Path(directory)
        self.dir.mkdir(parents=True, exist_ok=True)
        self.records_path = self.dir / "collection.jsonl"
        self.raw_path = self.dir / "raw.jsonl"

    def completed(self) -> dict[str, dict[str, Any]]:
        if not self.records_path.exists():
            return {}
        out: dict[str, dict[str, Any]] = {}
        for line in self.records_path.read_text(encoding="utf-8").splitlines():
            if line.strip():
                try:
                    record = json.loads(line)
                except json.JSONDecodeError:
                    continue  # a torn final line from a crash is discarded; that target is simply redone
                out[record["canonical_card_id"]] = record
        return out

    def append(self, record: Mapping[str, Any], raw_lines: list[dict[str, Any]]) -> None:
        with self.raw_path.open("a", encoding="utf-8") as raw:
            for line in raw_lines:
                raw.write(json.dumps(line, ensure_ascii=False) + "\n")
            raw.flush()
            os.fsync(raw.fileno())
        with self.records_path.open("a", encoding="utf-8") as fh:
            fh.write(json.dumps(record, ensure_ascii=False) + "\n")
            fh.flush()
            os.fsync(fh.fileno())


def collect_target(http: Any, counters: RunCounters, target: Mapping[str, Any], *, stop_sellers: int = STOP_SELLERS,
                   details_per_target: int = DETAILS_PER_TARGET, seen_items: set[str] | None = None) -> tuple[dict[str, Any], list[dict[str, Any]]]:
    seen_items = seen_items if seen_items is not None else set()
    cid = target["canonical_card_id"]
    enriched = with_queries(target)
    raw_lines: list[dict[str, Any]] = []
    search_items: list[dict[str, Any]] = []
    formulation_of: dict[str, str] = {}
    start_attempted, start_failed, start_retries = counters.requests_attempted, counters.requests_failed, counters.retries
    search_calls = 0
    exhausted = False
    for query in enriched["planned_queries"]:
        if search_calls >= 1 and len(candidate_rank(search_items, enriched)) >= 5:
            break
        try:
            outcome = http.get(_search_url(query), counters)
        except BudgetExhausted:
            exhausted = True
            break
        search_calls += 1
        if outcome.ok:
            for item in (outcome.data or {}).get("itemSummaries") or []:
                search_items.append(item)
                formulation_of.setdefault(str(item.get("itemId")), query["formulation"])
                raw_lines.append({"kind": "search_summary", "target_id": cid, "formulation": query["formulation"], "item": item})
    decisions: list[dict[str, Any]] = []
    eligible_sellers: set[str] = set()
    hydrated = 0
    if not exhausted:
        for candidate in candidate_rank(search_items, enriched):
            if hydrated >= details_per_target or len(eligible_sellers) >= stop_sellers:
                break
            item = candidate["item"]
            item_id = item["itemId"]
            if item_id in seen_items:
                continue
            seen_items.add(item_id)
            try:
                outcome = http.get(ITEM_URL + urllib.parse.quote(item_id, safe=""), counters)
            except BudgetExhausted:
                exhausted = True
                seen_items.discard(item_id)
                break
            hydrated += 1
            if not outcome.ok:
                decisions.append({"item_id": item_id, "target_id": cid, "state": "LANGUAGE_UNRESOLVED",
                                  "reason": f"getitem_failed_{outcome.status or outcome.error_type}"})
                continue
            detail = outcome.data or {}
            captured_at = datetime.now(timezone.utc).isoformat()
            raw_lines.append({"kind": "get_item", "target_id": cid, "item_id": item_id, "captured_at": captured_at, "item": detail})
            identity = ebay_d3_matcher_v5.classify_listing(enriched, detail)
            decision = resolve(detail, text_state=identity.get("identity_state") or "REJECTED")
            decision.update({
                "item_id": item_id, "target_id": cid, "captured_at": captured_at, "title": detail.get("title"),
                "query_formulation": formulation_of.get(str(item_id), "adaptive_search"),
                "seller_key_sha256": hashlib.sha256(candidate["seller"].encode()).hexdigest() if candidate["seller"] else None,
                "listing_url": detail.get("itemWebUrl"), "image_url": (detail.get("image") or {}).get("imageUrl"),
                "identity_reason": identity.get("reason")})
            if decision["state"] == "ENGLISH_PRICE_ELIGIBLE":
                eligible_sellers.add(candidate["seller"] or item_id)
            decisions.append(decision)
    record = {
        "canonical_card_id": cid, "card_variant_id": target.get("card_variant_id"),
        "status": "BUDGET_EXHAUSTED" if exhausted else "COMPLETE", "search_calls": search_calls, "detail_calls": hydrated,
        "raw_search_listings": len(search_items), "eligible_seller_count": len(eligible_sellers),
        "requests_attempted": counters.requests_attempted - start_attempted,
        "requests_failed": counters.requests_failed - start_failed, "retries": counters.retries - start_retries,
        "decisions": decisions,
    }
    return record, raw_lines


def collect(manifest: Mapping[str, Any], checkpoint: CollectionCheckpoint, http: Any, *, max_requests: int,
            stop_sellers: int = STOP_SELLERS, details_per_target: int = DETAILS_PER_TARGET, on_target=None) -> dict[str, Any]:
    """Collect every not-yet-completed target in manifest order. Never repeats a completed target."""
    done = checkpoint.completed()
    spent = sum(r.get("requests_attempted", 0) for r in done.values())
    counters = RunCounters(remaining_run_budget=max(0, max_requests - spent))
    # only fully completed targets pin their items; a budget-truncated target is redone from scratch on resume
    seen_items = {d["item_id"] for r in done.values() if r.get("status") == "COMPLETE" for d in r.get("decisions", []) if d.get("item_id")}
    skipped = 0
    exhausted = False
    for target in manifest["cards"]:
        cid = target["canonical_card_id"]
        if cid in done and done[cid].get("status") == "COMPLETE":
            skipped += 1
            continue
        if counters.remaining_run_budget <= 0:
            exhausted = True
            break
        record, raw_lines = collect_target(http, counters, target, stop_sellers=stop_sellers,
                                           details_per_target=details_per_target, seen_items=seen_items)
        if record["status"] == "BUDGET_EXHAUSTED" and record["requests_attempted"] == 0:
            exhausted = True
            break
        checkpoint.append(record, raw_lines)
        done[cid] = record
        if on_target:
            on_target(record)
        if record["status"] == "BUDGET_EXHAUSTED":
            exhausted = True
            break
    return {"targets_total": len(manifest["cards"]), "targets_completed": sum(1 for t in manifest["cards"] if done.get(t["canonical_card_id"], {}).get("status") == "COMPLETE"),
            "targets_resumed_from_checkpoint": skipped, "budget_exhausted": exhausted,
            "requests_attempted": sum(r["requests_attempted"] for r in done.values()),
            "requests_failed": sum(r["requests_failed"] for r in done.values()),
            "retries": sum(r["retries"] for r in done.values())}
