"""P3 evidence persistence for the adaptive collector, mapped onto the existing P3 tables.

Only ENGLISH_PRICE_ELIGIBLE listings (English-positive, NM-compatible, fixed-price, USD landed ask) become listing
rows; every hydrated decision still feeds the per-card summary, and raw provider responses stay in the VM state
directory. Ids are deterministic, so replays are idempotent.
"""
from __future__ import annotations

import statistics
import uuid
from collections import Counter
from datetime import datetime, timezone
from decimal import Decimal
from typing import Any, Mapping, Sequence

from backend.pricing_pipeline.contracts import NM_CONDITION_ID, PipelineError, digest
from backend.scripts.ebay_d3_matcher_v5 import MATCHER_VERSION, rule_fingerprint
from backend.scripts.ebay_english_price_eligibility_v1 import VERSION as ELIGIBILITY_VERSION, fingerprint as eligibility_fingerprint

COLLECTOR_VERSION = "multi_source_daily_collector_p6_v1"
QUERY_STRATEGY_VERSION = "ebay_p4a_adaptive_capture_v1"
QUALIFIED = "ENGLISH_PRICE_ELIGIBLE"


def _usd(value: Any) -> str | None:
    return None if value is None else str(Decimal(str(value)).quantize(Decimal("0.01")))


def evidence_id(run_id: str, canonical_card_id: str, item_id: str) -> str:
    return str(uuid.uuid5(uuid.NAMESPACE_URL, f"ebay-pricing:{run_id}:{canonical_card_id}:{item_id}"))


def pricing_run_id(market_date: str, selector_fingerprint: str) -> str:
    return str(uuid.uuid5(uuid.NAMESPACE_URL, f"ebay-pricing-run:{market_date}:{selector_fingerprint}"))


def _evidence_row(decision: Mapping[str, Any], target: Mapping[str, Any], run_id: str, market_date: str) -> dict[str, Any] | None:
    if decision.get("state") != QUALIFIED or decision.get("landed_ask_usd") is None or not decision.get("seller_key_sha256"):
        return None
    landed, item_price, shipping = (Decimal(str(decision[k])) for k in ("landed_ask_usd", "item_price_usd", "shipping_price_usd"))
    if landed <= 0 or landed != item_price + shipping:
        return None
    conditions = decision.get("card_condition_values") or []
    return {
        "id": evidence_id(run_id, target["canonical_card_id"], decision["item_id"]), "run_id": run_id, "market_date": market_date,
        "captured_at": decision["captured_at"], "canonical_card_id": target["canonical_card_id"],
        "card_variant_id": target.get("card_variant_id"), "condition_id": NM_CONDITION_ID, "listing_item_id": decision["item_id"],
        "marketplace": "EBAY_US", "evidence_kind": "active_ask", "query_formulation": decision.get("query_formulation") or "adaptive_search",
        "query_strategy_version": QUERY_STRATEGY_VERSION, "currency": "USD", "item_price_usd": _usd(item_price),
        "shipping_price_usd": _usd(shipping), "landed_ask_usd": _usd(landed), "title": decision.get("title") or decision["item_id"],
        "buying_options": decision.get("buying_options") or [], "condition_text": conditions[0] if conditions else decision.get("condition"),
        "seller_key_sha256": decision["seller_key_sha256"], "listing_url": decision.get("listing_url"), "image_url": decision.get("image_url"),
        "identity_state": "HIGH_CONFIDENCE", "language_state": "LANGUAGE_MATCH", "english_market_eligibility_state": "ENGLISH_ELIGIBLE",
        "identity_reason": decision.get("identity_reason"), "language_reason": decision.get("provider_language_normalized") or decision.get("reason"),
        "eligibility_reason": f"{QUALIFIED}:{decision.get('reason')}", "matcher_version": MATCHER_VERSION,
        "matcher_fingerprint": rule_fingerprint(), "language_policy_version": ELIGIBILITY_VERSION,
        "language_policy_fingerprint": eligibility_fingerprint(),
    }


def prepare(manifest: Mapping[str, Any], records: Mapping[str, Mapping[str, Any]], *, market_date: str, state_path: str,
            started_at: str, requests: Mapping[str, int], planned_requests: int) -> dict[str, Any]:
    run_id = pricing_run_id(market_date, manifest["selector_fingerprint"])
    targets = {t["canonical_card_id"]: t for t in manifest["cards"]}
    attempted = {cid: rec for cid, rec in records.items() if rec.get("status") == "COMPLETE" and cid in targets}
    evidence: dict[tuple, dict[str, Any]] = {}
    summaries = []
    counts: Counter = Counter()
    for cid in sorted(attempted):
        rec, target = attempted[cid], targets[cid]
        decisions = rec["decisions"]
        state = Counter(d.get("state") for d in decisions)
        kept = []
        for d in decisions:
            row = _evidence_row(d, target, run_id, market_date)
            if row and (cid, row["listing_item_id"]) not in evidence:
                evidence[(cid, row["listing_item_id"])] = row
                kept.append(row)
        prices = sorted(Decimal(r["landed_ask_usd"]) for r in kept)
        sellers = {r["seller_key_sha256"] for r in kept}
        counts.update(state)
        summaries.append({
            "run_id": run_id, "canonical_card_id": cid, "card_variant_id": target.get("card_variant_id"),
            "raw_count": rec["raw_search_listings"], "deduped_count": len(decisions),
            "identity_qualified_count": sum(v for k, v in state.items() if k != "IDENTITY_REJECTED"),
            "english_eligible_count": state[QUALIFIED], "language_unresolved_count": state["LANGUAGE_UNRESOLVED"],
            "identity_rejected_count": state["IDENTITY_REJECTED"], "non_english_excluded_count": state["NON_ENGLISH_EXCLUDED"],
            "persisted_count": len(kept), "min_eligible_landed_ask": _usd(prices[0]) if prices else None,
            "median_eligible_landed_ask": _usd(statistics.median(prices)) if prices else None,
            "max_eligible_landed_ask": _usd(prices[-1]) if prices else None, "eligible_seller_count": len(sellers),
            "query_count": rec["search_calls"],
            "evidence_fingerprint": digest(sorted((r["listing_item_id"], r["landed_ask_usd"]) for r in kept)),
        })
    rows = sorted(evidence.values(), key=lambda r: r["id"])
    evidence_digest = digest([(s["canonical_card_id"], s["evidence_fingerprint"]) for s in summaries])
    run = {
        "run_id": run_id, "market_date": market_date, "status": "COMPLETE", "selector_version": manifest["selector_version"],
        "selector_fingerprint": manifest["selector_fingerprint"], "collector_version": COLLECTOR_VERSION,
        "query_strategy_version": QUERY_STRATEGY_VERSION, "target_count": len(attempted),
        "planned_request_count": max(0, min(5000, int(planned_requests))), "requests_attempted": requests["attempted"],
        "requests_successful": max(0, requests["attempted"] - requests["failed"]), "requests_failed": requests["failed"],
        "retry_count": requests["retries"], "raw_listing_count": sum(s["raw_count"] for s in summaries),
        "deduped_listing_count": sum(s["deduped_count"] for s in summaries),
        "identity_qualified_count": sum(s["identity_qualified_count"] for s in summaries),
        "english_eligible_count": counts[QUALIFIED], "language_unresolved_count": counts["LANGUAGE_UNRESOLVED"],
        "identity_rejected_count": counts["IDENTITY_REJECTED"], "non_english_excluded_count": counts["NON_ENGLISH_EXCLUDED"],
        "persisted_listing_count": len(rows), "started_at": started_at,
        "finished_at": datetime.now(timezone.utc).isoformat(), "artifact_manifest_path": state_path,
        "artifact_run_id": run_id, "run_fingerprint": digest([run_id, manifest["selector_fingerprint"], evidence_digest]),
        "production_authority": False,
    }
    return {"run": run, "evidence": rows, "summaries": summaries, "evidence_digest": evidence_digest,
            "state_counts": dict(counts)}


def persist(store: Any, prepared: Mapping[str, Any]) -> dict[str, Any]:
    run = dict(prepared["run"])
    existing = store.get_pricing_run(run["run_id"])
    if existing and existing["run_fingerprint"] != run["run_fingerprint"]:
        raise PipelineError("EVIDENCE_RUN_CONTRACT_CHANGED", run["run_id"])
    already = bool(existing and existing["status"] == "COMPLETE"
                   and len(store.get_evidence(run["run_id"])) == len(prepared["evidence"])
                   and len(store.get_summaries(run["run_id"])) == len(prepared["summaries"]))
    if already:
        return {"run_id": run["run_id"], "inserted": 0, "skipped": len(prepared["evidence"]), "replayed": True}
    store.upsert_pricing_run(dict(run, status="RUNNING", finished_at=None))
    inserted, skipped = store.insert_evidence(list(prepared["evidence"]))
    store.upsert_summaries(list(prepared["summaries"]))
    store.upsert_pricing_run(run)
    return {"run_id": run["run_id"], "inserted": inserted, "skipped": skipped, "replayed": False}


def verify(store: Any, prepared: Mapping[str, Any]) -> None:
    run_id = prepared["run"]["run_id"]
    stored = store.get_evidence(run_id)
    if len(stored) != len(prepared["evidence"]) or {r["id"] for r in stored} != {r["id"] for r in prepared["evidence"]}:
        raise PipelineError("EVIDENCE_PERSISTENCE_MISMATCH", f"stored {len(stored)} != prepared {len(prepared['evidence'])}")
    summaries = {s["canonical_card_id"]: s["evidence_fingerprint"] for s in store.get_summaries(run_id)}
    if summaries != {s["canonical_card_id"]: s["evidence_fingerprint"] for s in prepared["summaries"]}:
        raise PipelineError("EVIDENCE_SUMMARY_MISMATCH", run_id)
