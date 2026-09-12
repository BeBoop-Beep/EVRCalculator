import csv
import hashlib
import json
from collections import Counter
from pathlib import Path

from backend.scripts.capture_ebay_d3_fresh_blind import canonical_fingerprint, seller_title
from backend.scripts.prepare_ebay_d3_blind_benchmark import SAFE_FIELDS, safe_row, select_cohorts

OUT=Path(__file__).resolve().parents[3]/"artifacts/index_fair_value"


def rows():
    result=[]
    for card in range(70):
        for number in range(7):
            result.append({"canonical_card_id":f"card-{card}", "card_variant_id":f"variant-{card}",
                           "listing_item_id":f"item-{card}-{number}", "seller_id":f"seller-{number}",
                           "listing_title":f"Card {card} #{number}", "_matcher_state":"HIGH_CONFIDENCE"})
    return result


def test_fingerprints_and_selection_are_deterministic():
    values=rows(); first=select_cohorts(values); second=select_cohorts(list(reversed(values)))
    assert canonical_fingerprint([row["listing_item_id"] for row in first[0]]) == canonical_fingerprint([row["listing_item_id"] for row in second[0]])
    assert len(first[0])==300 and len(first[1])==420


def test_normalized_seller_title_identity_and_missing_seller_policy():
    assert seller_title({"seller_id":" Seller ","listing_title":"Pokemon  CARD"})=="seller|pokemon card"
    assert seller_title({"seller_id":"","listing_title":"Pokemon card"}) is None


def test_human_review_row_has_no_private_or_price_fields():
    source=dict(rows()[0]);source.update({"price_json":"hidden", "matcher_state":"HIGH_CONFIDENCE", "matcher_evidence":"hidden"})
    output=safe_row(source,"D3_BLIND_REVIEW")
    assert set(output)==set(SAFE_FIELDS)
    assert not any(token in key for key in output for token in ("matcher","confidence","price","cohort"))


def read_csv(name):
    with (OUT/name).open(encoding="utf-8",newline="") as handle:return list(csv.DictReader(handle))


def test_materialized_capture_is_bounded_fresh_and_deduplicated():
    manifest=json.loads((OUT/"ebay_d3_fresh_capture_manifest.json").read_text())
    observations=read_csv("ebay_d3_fresh_observations.csv")
    assert manifest["api_calls"]<=140 and manifest["cards_queried"]==70 and not manifest["errors"]
    assert len(observations)==manifest["fresh_unique_listings"]==9591
    assert all(row["observed_at"] and row["capture_run_id"]==manifest["capture_run_id"] for row in observations)
    assert len({row["listing_item_id"] for row in observations})==len(observations)
    identities=[seller_title(row) for row in observations if seller_title(row)]
    assert len(identities)==len(set(identities))
    historical=[row for name in ("development","validation","final_blind") for row in read_csv(f"ebay_gold_{name}.csv")]
    assert not ({row["listing_item_id"] for row in observations}&{row["listing_item_id"] for row in historical})
    assert not (set(identities)&{identity for row in historical if (identity:=seller_title(row))})


def test_materialized_cohorts_and_review_queue_follow_contract():
    precision=read_csv("ebay_d3_precision_blind.csv");coverage=read_csv("ebay_d3_coverage_blind.csv")
    review=read_csv("ebay_d3_blind_review_queue.csv")
    private={row["listing_item_id"]:row for row in map(json.loads,(OUT/"ebay_d3_private_frozen_v3_predictions.jsonl").read_text(encoding="utf-8").splitlines())}
    assert len(precision)==300 and all(private[row["listing_item_id"]]["matcher_state"]=="HIGH_CONFIDENCE" for row in precision)
    assert len(coverage)==420 and set(Counter(row["canonical_card_id"] for row in coverage).values())=={6}
    precision_ids={row["listing_item_id"] for row in precision};coverage_ids={row["listing_item_id"] for row in coverage}
    assert len(precision_ids&coverage_ids)==16
    assert len(review)==len(precision_ids|coverage_ids)==704
    assert {row["listing_item_id"] for row in review}==precision_ids|coverage_ids
    assert set(review[0])==set(SAFE_FIELDS)
    assert not any(any(token in field.lower() for token in ("matcher","confidence","price","cohort","rationale")) for field in review[0])


def test_frozen_capture_fingerprints_reproduce_exactly():
    manifest=json.loads((OUT/"ebay_d3_fresh_blind_manifest.json").read_text())
    files={"fresh_observation_fingerprint":"ebay_d3_fresh_observations.csv",
           "private_prediction_fingerprint":"ebay_d3_private_frozen_v3_predictions.jsonl",
           "precision_cohort_fingerprint":"ebay_d3_precision_blind.csv",
           "coverage_cohort_fingerprint":"ebay_d3_coverage_blind.csv",
           "review_queue_fingerprint":"ebay_d3_blind_review_queue.csv"}
    assert all(hashlib.sha256((OUT/name).read_bytes()).hexdigest()==manifest[key] for key,name in files.items())
    fingerprint=manifest.pop("manifest_fingerprint")
    assert canonical_fingerprint(manifest)==fingerprint
    assert manifest["matcher_fingerprint"]=="b5e44641f35c5f846a8d83bc6c777285f6e07707c9c672feef47c55cd67c95ec"
    assert manifest["benchmark_design_fingerprint"]=="75505bfcbe2e167821a3178b5da192e1240879fe3e4edd75891fa2c55c02d2c6"
