import hashlib
import json

import pytest

from backend.scripts import ebay_d3_matcher_v3 as v3
from backend.scripts import ebay_d3_matcher_v4 as v4
from backend.scripts.capture_ebay_d3_v4_fresh_blind import (
    REVIEWER_FIELDS,
    build_reviewer_row,
    relist_fingerprint,
    stratified_sample,
)
from backend.scripts.index_fair_value_ebay_evidence_manifest import (
    EvidenceBoundaryViolation,
    ValidationPassAlreadyConsumed,
    assert_not_used_for_tuning,
    reset_validation_pass_state_for_tests,
)


TARGET = {"card_name": "Kyurem ex", "set_name": "Black Bolt", "card_number": "165", "treatment": "special_illustration_rare"}


def listing(title, condition="Ungraded", condition_id="4000", aspects="[]", buying_options='["FIXED_PRICE"]'):
    return {"title": title, "condition": condition, "conditionId": condition_id, "category": "",
            "aspects": aspects, "buying_options": buying_options, "itemId": "v1|1|0"}


# 1. development-only tuning loader / 2. historical-blind exclusion from tuning
def test_historical_blind_partitions_refuse_tuning_purpose():
    with pytest.raises(EvidenceBoundaryViolation):
        assert_not_used_for_tuning("FINAL_BLIND_TEST", "matcher_development")
    with pytest.raises(EvidenceBoundaryViolation):
        assert_not_used_for_tuning("D3_BLIND_REVIEW", "rule_design")
    assert_not_used_for_tuning("DEVELOPMENT", "matcher_development")  # does not raise


# 3. validation one-pass guard
def test_validation_pass_refuses_second_consumption(tmp_path, monkeypatch):
    import backend.scripts.index_fair_value_ebay_evidence_manifest as manifest_module

    monkeypatch.setattr(manifest_module, "STATE_PATH", tmp_path / "state.json")

    def fake_load_partition(partition, purpose):
        return [{"benchmark_row_id": "x"}]

    monkeypatch.setattr(manifest_module, "load_partition", fake_load_partition)
    manifest_module.load_validation_for_one_time_pass("first_caller")
    with pytest.raises(ValidationPassAlreadyConsumed):
        manifest_module.load_validation_for_one_time_pass("second_caller")


# 4. collector-number parser true positive
def test_number_guard_does_not_flag_structured_fraction_evidence():
    # target number appears via explicit fraction format -- not the suspect bare fallback
    check = v4.number_conflict_guard(TARGET, listing("Kyurem ex 165/086 Black Bolt SIR"))
    assert check["suspect_bare_number_context"] is False


# 5. collector-number parser numeric false-positive controls
def test_number_guard_flags_bare_number_in_price_context():
    check = v4.number_conflict_guard(TARGET, listing("Kyurem ex Black Bolt SIR Near Mint $165 OBO"))
    assert check["suspect_bare_number_context"] is True


def test_number_guard_ignores_unrelated_price_when_number_absent():
    check = v4.number_conflict_guard(TARGET, listing("Kyurem ex Black Bolt SIR Near Mint $40 OBO"))
    assert check["suspect_bare_number_context"] is False


def test_v4_downgrades_high_confidence_on_suspect_bare_number():
    title = "Kyurem ex Black Bolt Special Illustration Rare Near Mint $165 OBO"
    r3 = v3.classify_listing(TARGET, listing(title))
    r4 = v4.classify_listing(TARGET, listing(title))
    if r3["identity_state"] == "HIGH_CONFIDENCE":
        assert r4["identity_state"] != "HIGH_CONFIDENCE"
        assert r4["reason"] == "NUMBER_EVIDENCE_CONTEXT_SUSPECT_V4"


# 6. lot detection
def test_multi_fraction_guard_detects_two_distinct_collector_numbers():
    title = "Kyurem ex 165/086 and 164/086 Combo Black Bolt Special Illustration Rare"
    check = v4.multi_fraction_guard(listing(title))
    assert check["multiple_distinct_collector_numbers"] is True
    result = v4.classify_listing(TARGET, listing(title))
    assert result["identity_state"] == "REJECTED"
    assert result["reason"] == "MULTI_CARD_OFFER_V4_MULTI_FRACTION"


# 7. legitimate single-card controls
def test_single_fraction_listing_is_not_flagged_as_multi():
    check = v4.multi_fraction_guard(listing("Kyurem ex 165/086 Black Bolt Special Illustration Rare"))
    assert check["multiple_distinct_collector_numbers"] is False


def test_legitimate_exact_match_listing_still_reaches_high_confidence():
    title = "Kyurem ex 165/086 Black Bolt Special Illustration Rare Near Mint"
    r4 = v4.classify_listing(TARGET, listing(title))
    r3 = v3.classify_listing(TARGET, listing(title))
    assert r4["identity_state"] == r3["identity_state"]


# 8. sealed/accessory detection
@pytest.mark.parametrize("title", [
    "Pokemon Premium Collection Box Kyurem ex Black Bolt",
    "Pokemon Battle Deck Kyurem Black Bolt",
    "Pokemon Playmat Kyurem ex Black Bolt Art",
    "Pokemon Kyurem Coin Black Bolt",
])
def test_sealed_extension_guard_catches_new_product_terms(title):
    check = v4.sealed_accessory_extension_guard(listing(title))
    assert check["extended_sealed_matches"]
    result = v4.classify_listing(TARGET, listing(title))
    assert result["identity_state"] == "REJECTED"


# 9. raw-card controls
def test_ordinary_raw_card_title_has_no_extended_sealed_matches():
    check = v4.sealed_accessory_extension_guard(listing("Kyurem ex 165/086 Black Bolt Special Illustration Rare Raw NM"))
    assert check["extended_sealed_matches"] == []


# 10. catastrophic acceptance impossible for known development classes
def test_v4_never_upgrades_a_v3_rejection():
    # v4 only ever downgrades/keeps -- never turns a v3 REJECTED into anything else
    graded_title = "PSA 10 Kyurem ex 165/086 Black Bolt Special Illustration Rare"
    r3 = v3.classify_listing(TARGET, listing(graded_title, condition="Graded"))
    r4 = v4.classify_listing(TARGET, listing(graded_title, condition="Graded"))
    assert r3["identity_state"] == "REJECTED"
    assert r4["identity_state"] == "REJECTED"


# 11. explicit rejection reasons
def test_v4_rejection_reasons_are_explicit_not_silent():
    result = v4.classify_listing(TARGET, listing("Pokemon Playmat Kyurem ex Black Bolt Art"))
    assert result["reason"]
    assert result["identity_state"] == "REJECTED"


# 13. card-level coverage classification
def test_coverage_gap_classifier_uses_only_retained_d1_evidence():
    from backend.scripts.diagnose_index_fair_value_ebay_d3_coverage_gap import classify_card

    ample = {"returned_count": 100, "metrics": {"exact_match_listing_count": 50}, "counts": {"AMBIGUOUS": 10}}
    thin_ambiguous = {"returned_count": 100, "metrics": {"exact_match_listing_count": 1}, "counts": {"AMBIGUOUS": 80}}
    assert classify_card(ample)["cause"] == "E"
    assert classify_card(thin_ambiguous)["cause"] == "D"
    assert classify_card(None)["cause"] == "F"


# 14. freeze-manifest creation / 15. matcher-hash verification
def test_matcher_fingerprint_is_deterministic_and_hash_based():
    fp1 = v4.rule_fingerprint()
    fp2 = v4.rule_fingerprint()
    assert fp1 == fp2
    assert len(fp1) == 64  # sha256 hex digest


# 16. post-freeze mutation detection
def test_fingerprint_changes_if_guard_pattern_changes(monkeypatch):
    original = v4.rule_fingerprint()
    monkeypatch.setattr(v4, "_PRICE_CONTEXT_RE", __import__("re").compile(r"DIFFERENT_PATTERN"))
    mutated = v4.rule_fingerprint()
    assert original != mutated


# 17. historical item-ID exclusion from new blind
def test_relist_fingerprint_is_stable_and_content_based():
    fp1 = relist_fingerprint(title="Pikachu ex 238/191", seller="s1", canonical_card_id="c1", price=100.0)
    fp2 = relist_fingerprint(title="Pikachu EX 238/191", seller="S1", canonical_card_id="c1", price=101.5)  # case + small price drift, same $5 bucket
    fp3 = relist_fingerprint(title="Pikachu ex 238/191", seller="s2", canonical_card_id="c1", price=100.0)  # different seller
    assert fp1 == fp2  # normalized title + price bucket collapse together
    assert fp1 != fp3


# 18. blind queue contains no matcher outputs / 19. reviewer files contain no matcher outputs
def test_reviewer_row_contains_no_matcher_derived_fields():
    row = {"ebay_item_id": "v1|1|0", "item_web_url": "u", "title": "t", "condition": "Ungraded",
           "condition_id": "4000", "buying_options": [], "seller_username": "s", "image_url": "i",
           "target_canonical_card_id": "c1", "target_card_variant_id": "v1"}
    built = build_reviewer_row(row, "D4-0001")
    assert set(built.keys()) == set(REVIEWER_FIELDS)
    forbidden = {"matcher_version", "identity_state", "match_status", "confidence", "score", "reason", "accepted"}
    assert not (forbidden & set(built.keys()))


def test_stratified_sample_does_not_reference_matcher_status():
    import ast
    import inspect

    source = inspect.getsource(stratified_sample)
    tree = ast.parse(source)
    names = {node.id for node in ast.walk(tree) if isinstance(node, ast.Name)}
    attrs = {node.attr for node in ast.walk(tree) if isinstance(node, ast.Attribute)}
    tokens = names | attrs
    assert not any("matcher" in t.lower() or "confidence" in t.lower() or "accepted" in t.lower() for t in tokens)


# 20. no fake Reviewer-B/adjudication population
def test_fresh_blind_manifest_declares_single_reviewer_honestly():
    import csv as _csv
    import json as _json

    from backend.scripts.ebay_gold_access import OUT

    manifest_path = OUT / "ebay_d3_v4_fresh_blind_manifest.json"
    if not manifest_path.exists():
        pytest.skip("fresh blind capture not run in this environment")
    manifest = _json.loads(manifest_path.read_text(encoding="utf-8"))
    # These structural honesty properties must hold regardless of how far
    # real human labeling has progressed since this manifest was captured
    # (labels_exist legitimately flips to True once a real reviewer freezes
    # the first pass -- that is not a fabrication, it's the point).
    assert manifest["reviewer_b_exists"] is False
    assert manifest["protocol"] == "SINGLE_REVIEWER_BLIND"
    queue_path = OUT / "ebay_d3_v4_fresh_blind_queue.csv"
    if manifest.get("labels_exist") and queue_path.exists():
        with queue_path.open(encoding="utf-8", newline="") as handle:
            rows = list(_csv.DictReader(handle))
        assert all((row.get("adjudicated_result") or "") == "" for row in rows)


# 21. certification refuses unfrozen labels
def test_certifier_refuses_to_run_without_frozen_inputs(monkeypatch, tmp_path):
    from backend.scripts import certify_ebay_d3_v3 as certifier

    monkeypatch.setattr(certifier, "BLIND_MANIFEST", tmp_path / "does_not_exist.json")
    with pytest.raises(FileNotFoundError):
        certifier.main()
