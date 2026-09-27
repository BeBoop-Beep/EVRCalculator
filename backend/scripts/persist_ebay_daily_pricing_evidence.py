"""Persist compact P2 active-ask evidence to the isolated P3 tables."""
from __future__ import annotations

import argparse
import hashlib
import json
import statistics
import uuid
from collections import Counter, defaultdict
from datetime import datetime, timezone
from decimal import Decimal, InvalidOperation
from pathlib import Path
from typing import Any

from backend.scripts.ebay_d3_matcher_v5 import MATCHER_VERSION, rule_fingerprint
from backend.scripts.ebay_language_policy_v1 import METHOD_VERSION as LANGUAGE_VERSION, policy_source_hash
from backend.scripts.index_fair_value_ebay_evidence_collector import (
    COLLECTOR_VERSION, QUERY_STRATEGY_VERSION, RunState, cohort_fingerprint, generate_queries,
)

ROOT = Path(__file__).resolve().parents[2]
ELIGIBLE = {"ENGLISH_ELIGIBLE", "LANGUAGE_UNRESOLVED"}
STATES = ELIGIBLE | {"NON_ENGLISH_EXCLUDED", "IDENTITY_REJECTED"}


def digest(value: Any) -> str:
    return hashlib.sha256(json.dumps(value, sort_keys=True, separators=(",", ":"), ensure_ascii=False).encode()).hexdigest()


def read_jsonl(path: Path) -> list[dict[str, Any]]:
    return [json.loads(line) for line in path.read_text(encoding="utf-8").splitlines() if line.strip()]


def _money(value: Any) -> Decimal | None:
    if value is None:
        return None
    try:
        number = Decimal(str(value))
    except InvalidOperation as exc:
        raise ValueError("invalid price") from exc
    if not number.is_finite() or number < 0 or number.as_tuple().exponent < -2:
        raise ValueError("invalid USD price")
    return number


def _usd(value: Decimal | None) -> str | None:
    return str(value.quantize(Decimal("0.01"))) if value is not None else None


def normalize_evidence(raw: dict[str, Any], match: dict[str, Any], target: dict[str, Any],
                       market_date: str, run_id: str) -> dict[str, Any] | None:
    if raw.get("evidence_kind") != "active_ask":
        raise ValueError("only active_ask evidence is permitted")
    state = match.get("eligibility_status")
    if state not in STATES:
        raise ValueError(f"invalid eligibility state: {state}")
    identity_ok = match.get("identity_qualified") is True and match.get("identity_state") == "HIGH_CONFIDENCE"
    if (state == "IDENTITY_REJECTED") == identity_ok:
        raise ValueError("identity/eligibility contradiction")
    if state == "ENGLISH_ELIGIBLE" and match.get("language_state") != "LANGUAGE_MATCH":
        raise ValueError("English eligibility requires language match")
    if state == "LANGUAGE_UNRESOLVED" and match.get("language_state") != "LANGUAGE_UNVERIFIED":
        raise ValueError("unresolved eligibility requires unverified language")
    if not identity_ok or state == "NON_ENGLISH_EXCLUDED":
        return None
    if raw.get("price_currency") != "USD" or raw.get("marketplace") != "EBAY_US":
        return None
    item_price = _money(raw.get("price_value"))
    if item_price is None:
        return None
    shipping = _money(raw.get("shipping_value")) if raw.get("shipping_currency") == "USD" else None
    if shipping is None and raw.get("shipping_value") is not None and raw.get("shipping_currency") not in (None, "USD"):
        raise ValueError("shipping currency conflicts with USD item")
    landed = item_price + shipping if shipping is not None else None
    item_id = str(raw.get("ebay_item_id") or "")
    if not item_id or not raw.get("retrieved_at") or not raw.get("title"):
        raise ValueError("missing listing identity or capture metadata")
    if str(raw.get("collector_run_id")) != run_id:
        raise ValueError("raw listing run mismatch")
    if match.get("identity_matcher_version") != MATCHER_VERSION or match.get("language_method_version") != LANGUAGE_VERSION:
        raise ValueError("matcher or language policy version mismatch")
    seller = str(raw.get("seller_username") or "").strip().casefold()
    return {
        "id": str(uuid.uuid5(uuid.NAMESPACE_URL, f"ebay-pricing:{run_id}:{target['canonical_card_id']}:{item_id}")),
        "run_id": str(uuid.UUID(run_id)), "market_date": market_date, "captured_at": raw["retrieved_at"],
        "canonical_card_id": target["canonical_card_id"], "card_variant_id": target.get("card_variant_id"),
        "condition_id": None, "listing_item_id": item_id, "marketplace": "EBAY_US",
        "evidence_kind": "active_ask", "query_formulation": raw.get("search_formulation") or "unknown",
        "query_strategy_version": QUERY_STRATEGY_VERSION, "currency": "USD",
        "item_price_usd": _usd(item_price), "shipping_price_usd": _usd(shipping),
        "landed_ask_usd": _usd(landed), "title": raw["title"],
        "buying_options": raw.get("buying_options") or [], "condition_text": raw.get("condition"),
        "seller_key_sha256": hashlib.sha256(seller.encode()).hexdigest() if seller else None,
        "listing_url": raw.get("item_web_url"), "image_url": raw.get("image_url"),
        "identity_state": "HIGH_CONFIDENCE", "language_state": match["language_state"],
        "english_market_eligibility_state": state, "identity_reason": match.get("identity_reason"),
        "language_reason": match.get("language_reason"), "eligibility_reason": match.get("eligibility_reason") or state,
        "matcher_version": MATCHER_VERSION, "matcher_fingerprint": rule_fingerprint(),
        "language_policy_version": LANGUAGE_VERSION, "language_policy_fingerprint": policy_source_hash(),
    }


def prepare(manifest: dict[str, Any], state: RunState, raw: list[dict[str, Any]],
            matches: list[dict[str, Any]], manifest_path: str) -> dict[str, Any]:
    actual_fingerprint = digest({k: v for k, v in manifest.items() if k != "selector_fingerprint"})
    if actual_fingerprint != manifest.get("selector_fingerprint"):
        raise ValueError("selector fingerprint mismatch")
    cards = {str(c["canonical_card_id"]): c for c in manifest["cards"]}
    if manifest["target_count"] != len(cards) or manifest["canonical_card_ids"] != list(cards):
        raise ValueError("manifest target mismatch")
    if set(state.targets) - set(cards) or state.cohort_fingerprint != cohort_fingerprint([cards[c] for c in state.targets]):
        raise ValueError("collector cohort mismatch")
    if state.query_strategy_version != QUERY_STRATEGY_VERSION or state.config.get("run_matcher") is not True:
        raise ValueError("collector contract mismatch")
    if manifest["estimated_requests"] > manifest["planning_ceiling"] or manifest["planning_ceiling"] > 1000:
        raise ValueError("request plan exceeds budget")
    if any(c.get("planned_queries") != generate_queries(c) for c in cards.values()):
        raise ValueError("planned queries changed")
    try:
        run_id = str(uuid.UUID(state.run_id))
    except ValueError as exc:
        raise ValueError("invalid collector run UUID") from exc
    raw_by_item = {}
    for row in raw:
        if row.get("collector_run_id") != state.run_id:
            raise ValueError("raw run mismatch")
        raw_by_item.setdefault(str(row.get("ebay_item_id")), row)
    match_by_key = {}
    for row in matches:
        if row.get("collector_run_id") != state.run_id:
            raise ValueError("match run mismatch")
        key = (str(row.get("target_canonical_card_id")), str(row.get("ebay_item_id")))
        if key in match_by_key or key[0] not in state.targets or key[1] not in raw_by_item:
            raise ValueError("duplicate or orphan match")
        match_by_key[key] = row
    by_card: dict[str, list[dict[str, Any]]] = defaultdict(list)
    evidence = []
    for (cid, item_id), match in sorted(match_by_key.items()):
        by_card[cid].append(match)
        row = normalize_evidence(raw_by_item[item_id], match, cards[cid], manifest["market_date"], state.run_id)
        if row:
            evidence.append(row)
    summaries = []
    for cid in sorted(state.targets):
        rows = by_card[cid]
        kept = [row for row in evidence if row["canonical_card_id"] == cid]
        eligible_prices = sorted(Decimal(row["landed_ask_usd"]) for row in kept
                                 if row["english_market_eligibility_state"] == "ENGLISH_ELIGIBLE" and row["landed_ask_usd"] is not None)
        sellers = {row["seller_key_sha256"] for row in kept
                   if row["english_market_eligibility_state"] == "ENGLISH_ELIGIBLE" and row["seller_key_sha256"]}
        count = Counter(row["eligibility_status"] for row in rows)
        summary = {
            "run_id": run_id, "canonical_card_id": cid, "card_variant_id": cards[cid].get("card_variant_id"),
            "raw_count": int(state.targets[cid].get("listings_captured") or 0),
            "deduped_count": len(rows), "identity_qualified_count": sum(row.get("identity_qualified") is True for row in rows),
            "english_eligible_count": count["ENGLISH_ELIGIBLE"],
            "language_unresolved_count": count["LANGUAGE_UNRESOLVED"],
            "identity_rejected_count": count["IDENTITY_REJECTED"],
            "non_english_excluded_count": count["NON_ENGLISH_EXCLUDED"],
            "persisted_count": len(kept),
            "min_eligible_landed_ask": _usd(min(eligible_prices)) if eligible_prices else None,
            "median_eligible_landed_ask": _usd(Decimal(str(statistics.median(eligible_prices)))) if eligible_prices else None,
            "max_eligible_landed_ask": _usd(max(eligible_prices)) if eligible_prices else None,
            "eligible_seller_count": len(sellers), "query_count": len(cards[cid]["planned_queries"]),
            "evidence_fingerprint": digest(sorted((row["listing_item_id"], row["english_market_eligibility_state"], row["landed_ask_usd"]) for row in kept)),
        }
        summaries.append(summary)
    status = "PARTIAL" if any(x.get("status") != "completed" or x.get("last_error") for x in state.targets.values()) else "COMPLETE"
    counts = Counter(row["eligibility_status"] for row in matches)
    run = {
        "run_id": run_id, "market_date": manifest["market_date"], "status": status,
        "selector_version": manifest["selector_version"], "selector_fingerprint": manifest["selector_fingerprint"],
        "collector_version": COLLECTOR_VERSION, "query_strategy_version": QUERY_STRATEGY_VERSION,
        "target_count": len(state.targets), "planned_request_count": sum(cards[c]["estimated_request_cost"] for c in state.targets),
        "requests_attempted": state.requests_attempted, "requests_successful": state.requests_successful,
        "requests_failed": state.requests_failed, "retry_count": state.retries,
        "raw_listing_count": sum(x["raw_count"] for x in summaries),
        "deduped_listing_count": len(matches),
        "identity_qualified_count": sum(row.get("identity_qualified") is True for row in matches),
        "english_eligible_count": counts["ENGLISH_ELIGIBLE"],
        "language_unresolved_count": counts["LANGUAGE_UNRESOLVED"],
        "identity_rejected_count": counts["IDENTITY_REJECTED"],
        "non_english_excluded_count": counts["NON_ENGLISH_EXCLUDED"],
        "persisted_listing_count": len(evidence), "started_at": state.started_at,
        "finished_at": datetime.now(timezone.utc).isoformat() if status == "COMPLETE" else None,
        "artifact_manifest_path": manifest_path, "artifact_run_id": state.run_id,
        "run_fingerprint": digest([run_id, manifest["selector_fingerprint"], state.cohort_fingerprint]),
        "production_authority": False,
    }
    return {"run": run, "evidence": evidence, "summaries": summaries,
            "projection": project_volume(run),
            "receipt": {"run_id": run_id, "status": status, "raw_listing_count": run["raw_listing_count"],
                        "deduped_listing_count": run["deduped_listing_count"],
                        "identity_qualified_count": run["identity_qualified_count"],
                        "english_eligible_count": run["english_eligible_count"],
                        "language_unresolved_count": run["language_unresolved_count"],
                        "persisted_listing_count": len(evidence)}}


def project_volume(run: dict[str, Any], bytes_per_row: int = 1500) -> dict[str, Any]:
    rows = {"all_raw": run["raw_listing_count"], "deduped": run["deduped_listing_count"],
            "identity_qualified": run["identity_qualified_count"],
            "english_plus_unresolved": run["english_eligible_count"] + run["language_unresolved_count"],
            "eligible_only": run["english_eligible_count"], "chosen_persisted": run["persisted_listing_count"]}
    return {key: {"rows_per_run": value, "rows_month_30_runs": value * 30,
                  "rows_year_365_runs": value * 365, "estimated_year_gib": round(value * 365 * bytes_per_row / 2**30, 3)}
            for key, value in rows.items()}


def persist(client: Any, prepared: dict[str, Any]) -> dict[str, Any]:
    run = prepared["run"]
    existing = client.table("ebay_pricing_runs_v1").select("run_fingerprint,finished_at").eq("run_id", run["run_id"]).limit(1).execute().data or []
    if existing and existing[0]["run_fingerprint"] != run["run_fingerprint"]:
        raise ValueError("run ID already belongs to a different capture contract")
    previous_summaries = client.table("ebay_card_pricing_run_summary_v1").select("canonical_card_id,evidence_fingerprint,raw_count,deduped_count").eq("run_id", run["run_id"]).execute().data or []
    expected_summaries = {row["canonical_card_id"]: row for row in prepared["summaries"]}
    for previous in previous_summaries:
        expected = expected_summaries.get(previous["canonical_card_id"])
        if expected is None or any(previous.get(field) != expected.get(field) for field in ("evidence_fingerprint", "raw_count", "deduped_count")):
            raise ValueError("capture artifacts changed after partial persistence")
    if existing and existing[0].get("finished_at") and run["status"] == "COMPLETE":
        run = dict(run, finished_at=existing[0]["finished_at"])
    provisional = dict(run, status="RUNNING", finished_at=None)
    client.table("ebay_pricing_runs_v1").upsert(provisional, on_conflict="run_id").execute()
    written_any = False
    try:
        for start in range(0, len(prepared["evidence"]), 100):
            client.table("ebay_card_listing_evidence_v1").upsert(
                prepared["evidence"][start:start + 100], on_conflict="run_id,canonical_card_id,listing_item_id").execute()
            written_any = True
        for start in range(0, len(prepared["summaries"]), 100):
            client.table("ebay_card_pricing_run_summary_v1").upsert(
                prepared["summaries"][start:start + 100], on_conflict="run_id,canonical_card_id").execute()
            written_any = True
        client.table("ebay_pricing_runs_v1").upsert(run, on_conflict="run_id").execute()
    except Exception:
        client.table("ebay_pricing_runs_v1").update({"status": "PARTIAL" if written_any else "FAILED"}).eq("run_id", run["run_id"]).execute()
        raise
    return dict(prepared["receipt"], db_writes=True, run_fingerprint=run["run_fingerprint"])


def main(argv: list[str] | None = None) -> dict[str, Any]:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--manifest", type=Path, required=True)
    parser.add_argument("--run-id", required=True)
    mode = parser.add_mutually_exclusive_group(required=True)
    mode.add_argument("--dry-run", action="store_true")
    mode.add_argument("--persist", action="store_true")
    args = parser.parse_args(argv)
    state = RunState.load(args.run_id)
    manifest = json.loads(args.manifest.read_text(encoding="utf-8"))
    prepared = prepare(manifest, state, read_jsonl(state.raw_evidence_path()),
                       read_jsonl(state.match_results_path()), str(args.manifest.resolve()))
    if args.dry_run:
        result = dict(prepared["receipt"], db_writes=False, projection=prepared["projection"])
    else:
        from backend.db.clients.supabase_client import create_service_role_client
        result = persist(create_service_role_client(), prepared)
    print(json.dumps(result, indent=2))
    return result


if __name__ == "__main__":
    main()
