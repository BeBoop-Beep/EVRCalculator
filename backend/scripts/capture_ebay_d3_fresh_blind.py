"""Bounded fresh eBay Browse capture and frozen-v3 blind cohort materialization."""
from __future__ import annotations

import csv
import hashlib
import json
import urllib.request
import uuid
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Mapping

from backend.scripts.ebay_d3_matcher_v3 import MATCHER_VERSION, classify_listing, rule_fingerprint
from backend.scripts.ebay_gold_access import OUT, load_partition
from backend.scripts.index_fair_value_ebay_supply import build_query, normalize
from backend.scripts.prepare_ebay_d3_blind_benchmark import (
    COVERAGE_FILE, DESIGN, FREEZE, PRECISION_FILE, REVIEW_FILE, safe_row,
    select_cohorts, stable, write_partition,
)
from backend.scripts.run_index_fair_value_ebay_supply_d1 import env, token

CAPTURE_MANIFEST = OUT / "ebay_d3_fresh_capture_manifest.json"
EXCLUSION_MANIFEST = OUT / "ebay_d3_historical_exclusion_manifest.json"
OBSERVATIONS = OUT / "ebay_d3_fresh_observations.csv"
PRIVATE_PREDICTIONS = OUT / "ebay_d3_private_frozen_v3_predictions.jsonl"
BLIND_MANIFEST = OUT / "ebay_d3_fresh_blind_manifest.json"
DOCS = Path(__file__).resolve().parents[2] / "docs/research/index_fair_value"


def canonical_fingerprint(values: Any) -> str:
    return hashlib.sha256(json.dumps(values, sort_keys=True, separators=(",", ":"), ensure_ascii=False).encode()).hexdigest()


def seller_title(row: Mapping[str, Any]) -> str | None:
    seller = normalize(row.get("seller_id"))
    title = normalize(row.get("listing_title"))
    return f"{seller}|{title}" if seller and title else None


def historical_exclusion() -> tuple[set[str], set[str], dict[str, Any]]:
    rows = [row for partition in ("DEVELOPMENT", "VALIDATION", "FINAL_BLIND_TEST")
            for row in load_partition(partition, purpose="human_review")]
    item_ids = {str(row["listing_item_id"]) for row in rows}
    identities = {identity for row in rows if (identity := seller_title(row))}
    payload = {
        "version":"ebay_d3_historical_exclusion_manifest_v1",
        "historical_listing_id_count":len(item_ids),
        "historical_seller_title_identity_count":len(identities),
        "listing_ids_fingerprint":canonical_fingerprint(sorted(item_ids)),
        "seller_title_fingerprint":canonical_fingerprint(sorted(identities)),
    }
    payload["historical_exclusion_fingerprint"] = canonical_fingerprint(payload)
    return item_ids, identities, payload


def target_cards() -> list[dict[str, Any]]:
    cards = {}
    for partition in ("DEVELOPMENT", "VALIDATION", "FINAL_BLIND_TEST"):
        for row in load_partition(partition, purpose="human_review"):
            cards.setdefault(row["canonical_card_id"], {
                "canonical_card_id":row["canonical_card_id"], "card_variant_id":row["card_variant_id"],
                "card_name":row["target_card_name"], "set_name":row["target_set_name"],
                "card_number":row["target_card_number"], "treatment_key":row["target_treatment"],
            })
    if len(cards) != 70:
        raise RuntimeError("EXPECTED_70_TARGET_CARDS")
    return [cards[key] for key in sorted(cards)]


def request_page(access_token: str, url: str) -> dict[str, Any]:
    request = urllib.request.Request(url, headers={
        "Authorization":f"Bearer {access_token}", "X-EBAY-C-MARKETPLACE-ID":"EBAY_US",
        "Accept":"application/json",
    })
    with urllib.request.urlopen(request, timeout=30) as response:
        return json.load(response)


def first_url(query: Mapping[str, Any]) -> str:
    import urllib.parse
    params = urllib.parse.urlencode({"q":query["query"], "category_ids":query["category_id"],
                                     "limit":query["limit"], "filter":query["filters"]})
    return "https://api.ebay.com/buy/browse/v1/item_summary/search?" + params


def observation(card: Mapping[str, Any], query: Mapping[str, Any], item: Mapping[str, Any],
                run_id: str, capture_at: str, page: int) -> dict[str, Any]:
    return {
        "capture_run_id":run_id, "canonical_card_id":card["canonical_card_id"],
        "card_variant_id":card.get("card_variant_id"), "target_card_name":card["card_name"],
        "target_set_name":card["set_name"], "target_card_number":card.get("card_number"),
        "target_treatment":card.get("treatment_key"), "query":query["query"],
        "listing_item_id":str(item.get("itemId") or ""),
        "seller_id":str((item.get("seller") or {}).get("username") or ""),
        "listing_title":str(item.get("title") or ""), "subtitle":str(item.get("subtitle") or ""),
        "condition":str(item.get("condition") or ""), "condition_id":str(item.get("conditionId") or ""),
        "category_id":str(item.get("categoryId") or ""),
        "localized_aspects_json":json.dumps(item.get("localizedAspects") or [], ensure_ascii=False, separators=(",", ":")),
        "buying_options_json":json.dumps(item.get("buyingOptions") or [], separators=(",", ":")),
        "image_url":str((item.get("image") or {}).get("imageUrl") or ""),
        "item_url":str(item.get("itemWebUrl") or ""), "observed_at":capture_at,
        "captured_at":capture_at, "source_page":page,
    }


def write_csv(path: Path, rows: list[Mapping[str, Any]]) -> None:
    with path.open("w", encoding="utf-8", newline="") as handle:
        writer = csv.DictWriter(handle, fieldnames=list(rows[0]))
        writer.writeheader(); writer.writerows(rows)


def main() -> None:
    freeze = json.loads(FREEZE.read_text(encoding="utf-8")); design = json.loads(DESIGN.read_text(encoding="utf-8"))
    if not (freeze.get("logic_frozen") and freeze.get("matcher_version") == MATCHER_VERSION
            and freeze.get("matcher_fingerprint") == rule_fingerprint()
            and freeze.get("benchmark_design_fingerprint") == design.get("benchmark_design_fingerprint")):
        raise RuntimeError("V3_FREEZE_OR_DESIGN_MISMATCH")
    old_ids, old_identities, exclusion = historical_exclusion()
    EXCLUSION_MANIFEST.write_text(json.dumps(exclusion, indent=2) + "\n", encoding="utf-8")
    access_token = token(env())
    cards = target_cards(); run_id = str(uuid.uuid4()); capture_at = datetime.now(timezone.utc).isoformat()
    raw = []; api_calls = 0; errors = []
    for card in cards:
        query = build_query(card); url = first_url(query)
        for page in (1, 2):
            if not url: break
            if api_calls >= 140: raise RuntimeError("BROWSE_CALL_LIMIT_EXCEEDED")
            api_calls += 1
            try:
                payload = request_page(access_token, url)
            except Exception as exc:
                errors.append({"canonical_card_id":card["canonical_card_id"], "page":page, "error_type":type(exc).__name__})
                break
            raw.extend(observation(card, query, item, run_id, capture_at, page) for item in payload.get("itemSummaries", []))
            url = str(payload.get("next") or "")
    fresh = []; seen_ids = set(); seen_identities = set(); historical_item_exclusions = 0
    historical_identity_exclusions = 0; current_item_duplicates = 0; current_identity_duplicates = 0
    for row in raw:
        item_id = row["listing_item_id"]; identity = seller_title(row)
        if item_id in old_ids:
            historical_item_exclusions += 1; continue
        if identity and identity in old_identities:
            historical_identity_exclusions += 1; continue
        if item_id in seen_ids:
            current_item_duplicates += 1; continue
        if identity and identity in seen_identities:
            current_identity_duplicates += 1; continue
        seen_ids.add(item_id)
        if identity: seen_identities.add(identity)
        fresh.append(row)
    if not fresh: raise RuntimeError("NO_FRESH_OBSERVATIONS")
    write_csv(OBSERVATIONS, fresh)
    predictions = []
    for row in fresh:
        result = classify_listing(
            {"card_name":row["target_card_name"], "set_name":row["target_set_name"], "card_number":row["target_card_number"], "treatment":row["target_treatment"]},
            {"title":row["listing_title"], "subtitle":row["subtitle"], "condition":row["condition"],
             "conditionId":row["condition_id"], "category":row["category_id"], "aspects":row["localized_aspects_json"],
             "itemId":row["listing_item_id"]},
        )
        row["_matcher_state"] = result["identity_state"]
        predictions.append({**row, "matcher_state":result["identity_state"],
                            "product_object_state":result["product_object"]["state"],
                            "matcher_reason":result["reason"], "matcher_evidence":result["evidence"],
                            "matcher_version":MATCHER_VERSION, "matcher_fingerprint":rule_fingerprint()})
    PRIVATE_PREDICTIONS.write_text("".join(json.dumps(row, ensure_ascii=False, separators=(",", ":")) + "\n" for row in predictions), encoding="utf-8")
    high_candidates = sum(row["_matcher_state"] == "HIGH_CONFIDENCE" for row in fresh)
    try:
        precision, coverage = select_cohorts(fresh)
    except ValueError as exc:
        capture_manifest = {"version":"ebay_d3_fresh_capture_manifest_v1", "capture_run_id":run_id,
                            "capture_timestamp":capture_at, "api_calls":api_calls, "cards_queried":len(cards),
                            "raw_returned_listings":len(raw), "historical_item_exclusions":historical_item_exclusions,
                            "historical_seller_title_exclusions":historical_identity_exclusions,
                            "within_capture_item_duplicates":current_item_duplicates,
                            "within_capture_seller_title_duplicates":current_identity_duplicates,
                            "fresh_unique_listings":len(fresh), "eligible_high_candidates":high_candidates,
                            "errors":errors, "cohort_status":"INSUFFICIENT", "reason":str(exc)}
        CAPTURE_MANIFEST.write_text(json.dumps(capture_manifest, indent=2) + "\n", encoding="utf-8")
        raise
    precision_ids = {row["listing_item_id"] for row in precision}; coverage_ids = {row["listing_item_id"] for row in coverage}
    overlap = precision_ids & coverage_ids
    precision_output = [safe_row(row, "PRECISION_BLIND") for row in precision]
    coverage_output = [safe_row(row, "COVERAGE_BLIND") for row in coverage]
    unique = {row["listing_item_id"]:row for row in precision + coverage}
    review_output = [safe_row(row, "D3_BLIND_REVIEW") for row in sorted(unique.values(), key=lambda item:stable(item, "d3-review-v1"))]
    write_partition(PRECISION_FILE, precision_output); write_partition(COVERAGE_FILE, coverage_output); write_partition(REVIEW_FILE, review_output)
    capture_manifest = {"version":"ebay_d3_fresh_capture_manifest_v1", "capture_run_id":run_id,
                        "capture_timestamp":capture_at, "api_calls":api_calls, "cards_queried":len(cards),
                        "raw_returned_listings":len(raw), "historical_item_exclusions":historical_item_exclusions,
                        "historical_seller_title_exclusions":historical_identity_exclusions,
                        "within_capture_item_duplicates":current_item_duplicates,
                        "within_capture_seller_title_duplicates":current_identity_duplicates,
                        "fresh_unique_listings":len(fresh), "eligible_high_candidates":high_candidates,
                        "errors":errors, "cohort_status":"READY"}
    capture_manifest["capture_manifest_fingerprint"] = canonical_fingerprint(capture_manifest)
    CAPTURE_MANIFEST.write_text(json.dumps(capture_manifest, indent=2) + "\n", encoding="utf-8")
    fresh_fp = hashlib.sha256(OBSERVATIONS.read_bytes()).hexdigest()
    precision_fp = hashlib.sha256(PRECISION_FILE.read_bytes()).hexdigest(); coverage_fp = hashlib.sha256(COVERAGE_FILE.read_bytes()).hexdigest()
    review_fp = hashlib.sha256(REVIEW_FILE.read_bytes()).hexdigest()
    blind = {"version":"ebay_d3_fresh_blind_manifest_v1", "matcher_version":MATCHER_VERSION,
             "matcher_fingerprint":rule_fingerprint(), "benchmark_design_fingerprint":design["benchmark_design_fingerprint"],
             "capture_run_id":run_id, "capture_timestamp":capture_at, "api_call_count":api_calls,
             "historical_exclusion_fingerprint":exclusion["historical_exclusion_fingerprint"],
             "fresh_observation_fingerprint":fresh_fp, "private_prediction_fingerprint":hashlib.sha256(PRIVATE_PREDICTIONS.read_bytes()).hexdigest(),
             "precision_cohort_fingerprint":precision_fp, "coverage_cohort_fingerprint":coverage_fp,
             "review_queue_fingerprint":review_fp, "precision_logical_rows":len(precision_output),
             "coverage_logical_rows":len(coverage_output), "overlap_rows":len(overlap),
             "unique_review_rows":len(review_output), "human_labels_collected":False,
             "cohort_membership_frozen":True}
    blind["manifest_fingerprint"] = canonical_fingerprint(blind)
    BLIND_MANIFEST.write_text(json.dumps(blind, indent=2) + "\n", encoding="utf-8")
    report = f"""# eBay D3 fresh capture report

Capture `{run_id}` at `{capture_at}` made {api_calls} Browse calls across 70 cards and
returned {len(raw)} rows. After {historical_item_exclusions + historical_identity_exclusions}
historical exclusions and {current_item_duplicates + current_identity_duplicates}
within-capture duplicates, {len(fresh)} fresh unique observations remained.

Frozen v3 produced {high_candidates} eligible HIGH candidates. The frozen cohorts contain
{len(precision_output)} precision rows and {len(coverage_output)} coverage rows with
{len(overlap)} overlapping rows, for {len(review_output)} unique human reviews. No human
labels were collected and no matcher, confidence, evidence, rationale, or price field is
present in the review queue.
"""
    DOCS.mkdir(parents=True, exist_ok=True)
    (DOCS / "EBAY_D3_FRESH_CAPTURE_REPORT.md").write_text(report, encoding="utf-8")
    runbook = """# eBay D3 blind human review runbook

Start or resume the blinded queue:

`python -m backend.scripts.ebay_gold_review_server --partition D3_BLIND_REVIEW --reviewer YOUR_ALIAS`

Show resume-safe summary only:

`python -m backend.scripts.ebay_gold_review_server --partition D3_BLIND_REVIEW --reviewer YOUR_ALIAS --summary`

The queue is append-only. Notes and skips do not count as labels. Images remain visible
so humans can label image-only slabs as `GRADED`. Cohort membership, matcher output,
confidence, evidence, selection rationale, and all price fields remain hidden.
"""
    (DOCS / "EBAY_D3_BLIND_HUMAN_REVIEW_RUNBOOK.md").write_text(runbook, encoding="utf-8")
    print(json.dumps({"capture":capture_manifest, "blind":blind}, indent=2))


if __name__ == "__main__":
    main()
