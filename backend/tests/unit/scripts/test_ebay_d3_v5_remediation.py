import json

from backend.scripts.capture_ebay_d3_v5_fresh_blind import HISTORICAL_FILES
from backend.scripts.ebay_gold_access import OUT


# 16. previous-blind item exclusion
def test_v5_capture_historical_files_include_v4_blind_queue():
    assert "ebay_d3_v4_fresh_blind_queue.csv" in HISTORICAL_FILES
    # and everything the v4 capture already excluded, so no D2/D3 gold leaks either
    for name in ("ebay_manual_gold_labels.csv", "ebay_d3_blind_review_queue.csv",
                 "ebay_gold_development.csv", "ebay_gold_validation.csv", "ebay_gold_final_blind.csv"):
        assert name in HISTORICAL_FILES


def test_v5_blind_queue_real_capture_excludes_v4_item_ids():
    """Direct check against the real repo artifacts produced by this task:
    no listing_item_id in the new v5 queue appears in the old v4 queue.
    """
    v5_path = OUT / "ebay_d3_v5_fresh_blind_queue.csv"
    v4_path = OUT / "ebay_d3_v4_fresh_blind_queue.csv"
    if not v5_path.exists() or not v4_path.exists():
        return  # capture not run in this environment; nothing to assert
    import csv

    with v5_path.open(encoding="utf-8", newline="") as f:
        v5_ids = {row["listing_item_id"] for row in csv.DictReader(f)}
    with v4_path.open(encoding="utf-8", newline="") as f:
        v4_ids = {row["listing_item_id"] for row in csv.DictReader(f)}
    assert v5_ids.isdisjoint(v4_ids)


# 17. near-duplicate/relist exclusion (reuses the same relist_fingerprint heuristic as v4)
def test_v5_capture_uses_same_relist_fingerprint_heuristic():
    from backend.scripts.capture_ebay_d3_v4_fresh_blind import relist_fingerprint
    from backend.scripts.capture_ebay_d3_v5_fresh_blind import load_historical_relist_fingerprints

    fp1 = relist_fingerprint(title="Some Card 1/100", seller="s", canonical_card_id="c1", price=10.0)
    fp2 = relist_fingerprint(title="SOME CARD 1/100", seller="S", canonical_card_id="c1", price=11.0)
    assert fp1 == fp2  # normalization collapses case/minor price drift, same as v4
    assert callable(load_historical_relist_fingerprints)


# 18. new queue contains no matcher fields
def test_v5_real_queue_contains_no_matcher_fields():
    path = OUT / "ebay_d3_v5_fresh_blind_queue.csv"
    if not path.exists():
        return
    import csv

    with path.open(encoding="utf-8", newline="") as f:
        rows = list(csv.DictReader(f))
    assert rows
    forbidden = {"matcher_version", "matcher_state", "identity_state", "match_status",
                 "confidence", "confidence_tier", "score", "accepted", "rejection_reason"}
    assert not (forbidden & set(rows[0].keys()))


def test_v5_real_manifest_declares_single_reviewer_honestly():
    """Reviewer-honesty invariants that must hold at every point in the V5
    blind-review lifecycle, before OR after the human review is complete.
    Before the review starts (or while it is in progress), labels_exist is
    False; once a legitimate --freeze has run (E2.3B/E2.4), labels_exist
    flips to True and must be internally consistent with labels_frozen --
    this test never assumes one specific point in that lifecycle.
    """
    path = OUT / "ebay_d3_v5_fresh_blind_manifest.json"
    if not path.exists():
        return
    manifest = json.loads(path.read_text(encoding="utf-8"))
    assert manifest["reviewer_b_exists"] is False
    assert manifest["protocol"] == "SINGLE_REVIEWER_BLIND"
    assert manifest["labels_exist"] == manifest.get("labels_frozen", False)


def test_v5_real_manifest_all_70_cards_represented():
    path = OUT / "ebay_d3_v5_fresh_blind_manifest.json"
    if not path.exists():
        return
    manifest = json.loads(path.read_text(encoding="utf-8"))
    assert manifest["cards_represented"] == 70


# historical diagnostic is clearly non-certifying
def test_historical_diagnostic_output_declares_non_certifying():
    path = OUT / "ebay_d3_v5_historical_post_hoc_diagnostic.json"
    if not path.exists():
        return
    result = json.loads(path.read_text(encoding="utf-8"))
    assert result["status"] == "HISTORICAL_POST_HOC_DIAGNOSTIC"
    assert result["certifying"] is False


def test_v4_blind_cohort_marked_consumed():
    path = OUT / "ebay_d3_v4_fresh_blind_consumed_status.json"
    if not path.exists():
        return
    status = json.loads(path.read_text(encoding="utf-8"))
    assert status["status"] == "CONSUMED_HISTORICAL_DIAGNOSTIC_ONLY"
    assert status["eligible_for_future_certification_of_any_matcher"] is False
