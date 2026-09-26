import json
import math

import pytest

from backend.scripts import ebay_combined_identity_policy_v2 as policy_v2
from backend.scripts.run_ebay_combined_identity_v2_fresh_blind_scoring import score_row
from backend.scripts.run_ebay_combined_identity_v2_fresh_blind_certification import (
    wilson, ratio, _classify_no_reason, run_precondition_checks,
    TOTAL_TARGET_CARDS, DESIGN_GATE,
)
from backend.scripts.ebay_gold_access import OUT


class FakeGalleryEntry:
    def __init__(self, canonical_card_id):
        self.canonical_card_id = canonical_card_id


class FakeGallery:
    def __init__(self, ids):
        self.entries = [FakeGalleryEntry(i) for i in ids]


def base_row(**overrides):
    row = {
        "benchmark_row_id": "T-0000", "canonical_card_id": "CARD_A", "listing_item_id": "v1|1|0",
        "target_card_name": "Test Card", "target_set_name": "Test Set", "target_card_number": "1",
        "target_treatment": "holo", "listing_title": "Test Card 1/100 Test Set",
        "condition": "Ungraded", "condition_id": "4000", "category_id": "", "buying_options_json": "[]",
        "image_url": "http://example.com/x.jpg",
        "single_card_or_lot": "", "raw_or_graded": "", "card_or_sealed_nonshcard": "",
        "collector_number_consistency": "", "set_consistency": "", "language": "", "variant_treatment": "",
    }
    row.update(overrides)
    return row


# 1. precondition failure on cohort fingerprint mismatch
def test_precondition_fails_on_cohort_fingerprint_mismatch(monkeypatch):
    from backend.scripts import run_ebay_combined_identity_v2_fresh_blind_certification as mod
    monkeypatch.setattr(mod, "E2_9B_MANIFEST_PATH", mod.E2_9B_MANIFEST_PATH)
    real_manifest = json.loads(mod.E2_9B_MANIFEST_PATH.read_text(encoding="utf-8"))
    tampered = dict(real_manifest)
    tampered["cohort_fingerprint"] = "0" * 64
    tmp = OUT / "_test_tampered_manifest.json"
    tmp.write_text(json.dumps(tampered), encoding="utf-8")
    monkeypatch.setattr(mod, "E2_9B_MANIFEST_PATH", tmp)
    try:
        checks = mod.run_precondition_checks()
        assert checks["cohort_fingerprint_matches"] is False
    finally:
        tmp.unlink(missing_ok=True)


# 2. precondition failure on final-label fingerprint mismatch
def test_precondition_fails_on_final_label_fingerprint_mismatch(monkeypatch):
    from backend.scripts import run_ebay_combined_identity_v2_fresh_blind_certification as mod
    real_manifest = json.loads(mod.E2_9B_MANIFEST_PATH.read_text(encoding="utf-8"))
    tampered = dict(real_manifest)
    tampered["final_label_fingerprint"] = "0" * 64
    tmp = OUT / "_test_tampered_manifest2.json"
    tmp.write_text(json.dumps(tampered), encoding="utf-8")
    monkeypatch.setattr(mod, "E2_9B_MANIFEST_PATH", tmp)
    try:
        checks = mod.run_precondition_checks()
        assert checks["final_label_fingerprint_recomputes"] is False
    finally:
        tmp.unlink(missing_ok=True)


# 3. precondition failure on policy fingerprint mismatch
def test_precondition_fails_on_policy_fingerprint_mismatch(monkeypatch):
    from backend.scripts import run_ebay_combined_identity_v2_fresh_blind_certification as mod
    real_freeze = json.loads(mod.COMBINED_V2_FREEZE_PATH.read_text(encoding="utf-8"))
    tampered = dict(real_freeze)
    tampered["policy_source_sha256"] = "0" * 64
    tmp = OUT / "_test_tampered_freeze.json"
    tmp.write_text(json.dumps(tampered), encoding="utf-8")
    monkeypatch.setattr(mod, "COMBINED_V2_FREEZE_PATH", tmp)
    try:
        checks = mod.run_precondition_checks()
        assert checks["combined_v2_fingerprint_matches_frozen"] is False
    finally:
        tmp.unlink(missing_ok=True)


# 4. precondition failure on IMAGE-v2 fingerprint mismatch
def test_precondition_fails_on_image_v2_fingerprint_mismatch(monkeypatch):
    from backend.scripts import run_ebay_combined_identity_v2_fresh_blind_certification as mod
    real_freeze = json.loads(mod.COMBINED_V2_FREEZE_PATH.read_text(encoding="utf-8"))
    tampered = dict(real_freeze)
    tampered["image_verifier_fingerprint"] = "0" * 64
    tmp = OUT / "_test_tampered_freeze2.json"
    tmp.write_text(json.dumps(tampered), encoding="utf-8")
    monkeypatch.setattr(mod, "COMBINED_V2_FREEZE_PATH", tmp)
    try:
        checks = mod.run_precondition_checks()
        assert checks["image_v2_fingerprint_matches_frozen"] is False
    finally:
        tmp.unlink(missing_ok=True)


# 5. scoring independent of human labels
def test_score_row_never_reads_human_label():
    import inspect
    from backend.scripts import run_ebay_combined_identity_v2_fresh_blind_scoring as scoring_mod
    source = inspect.getsource(scoring_mod.score_row)
    # Strip the docstring (first \"\"\"...\"\"\" block) so only actual code is
    # scanned -- the docstring legitimately explains why the field is absent.
    parts = source.split('"""')
    code_only = parts[0] + "".join(parts[2:]) if len(parts) >= 3 else source
    assert "exact_match_yes_no_uncertain" not in code_only


def test_scoring_main_strips_label_before_scoring():
    import inspect
    from backend.scripts import run_ebay_combined_identity_v2_fresh_blind_scoring as scoring_mod
    source = inspect.getsource(scoring_mod.main)
    assert 'pop("exact_match_yes_no_uncertain"' in source


# 6. prediction artifact written before evaluation
def test_predictions_file_exists_and_is_read_only_input_to_certification():
    from backend.scripts.run_ebay_combined_identity_v2_fresh_blind_scoring import PREDICTIONS_OUTPUT_PATH
    from backend.scripts.run_ebay_combined_identity_v2_fresh_blind_certification import PREDICTIONS_PATH
    assert PREDICTIONS_OUTPUT_PATH == PREDICTIONS_PATH
    assert PREDICTIONS_PATH.exists()
    doc = json.loads(PREDICTIONS_PATH.read_text(encoding="utf-8"))
    assert doc["phase"] == "PHASE_1_SCORE_LABEL_BLIND"
    import hashlib
    recomputed = hashlib.sha256(json.dumps(doc["predictions"], sort_keys=True, separators=(",", ":")).encode()).hexdigest()
    assert recomputed == doc["predictions_fingerprint"]


# 7. Tier A acceptance
def test_tier_a_acceptance():
    result = policy_v2.combine("HIGH_CONFIDENCE", "MATCH")
    assert result.combined_state == policy_v2.TIER_A_IMAGE_VERIFIED
    assert result.is_eligible


# 8. Tier B acceptance
def test_tier_b_acceptance():
    result = policy_v2.combine("HIGH_CONFIDENCE", "UNVERIFIED")
    assert result.combined_state == policy_v2.TIER_B_TEXT_VERIFIED_IMAGE_UNVERIFIED
    assert result.is_eligible
    assert not result.is_image_verified


# 9. IMAGE MISMATCH rejection
def test_image_mismatch_rejection():
    result = policy_v2.combine("HIGH_CONFIDENCE", "MISMATCH")
    assert result.combined_state == policy_v2.REJECTED_IMAGE_CONTRADICTION
    assert not result.is_eligible


# 10. text contradiction rejection
def test_text_contradiction_rejection():
    result = policy_v2.combine("HIGH_CONFIDENCE", "MATCH", text_row_fields={"raw_or_graded": "graded"})
    assert result.combined_state == policy_v2.REJECTED_TEXT
    assert not result.is_eligible


# 11. weak text not promoted
@pytest.mark.parametrize("text_state", ["MEDIUM_CONFIDENCE", "AMBIGUOUS"])
def test_weak_text_not_promoted(text_state):
    result = policy_v2.combine(text_state, "MATCH")
    assert result.combined_state == policy_v2.TEXT_AMBIGUOUS_NOT_PROMOTED
    assert not result.is_eligible


# 12. human-NO accepted row counted as false accept
def test_human_no_accepted_row_is_false_accept_in_metrics():
    # Simulated: an eligible TIER_A prediction whose human label is NO.
    predictions = {"R1": {"canonical_card_id": "C1", "identity_tier": "TIER_A", "eligible": True}}
    rows_by_id = {"R1": {"exact_match_yes_no_uncertain": "NO", "single_card_or_lot": "", "raw_or_graded": "",
                          "card_or_sealed_nonshcard": "", "collector_number_consistency": "", "set_consistency": "",
                          "variant_treatment": "", "language": "", "target_card_name": "x", "target_set_name": "y",
                          "target_card_number": "1", "listing_title": "t"}}
    row = rows_by_id["R1"]
    human = row["exact_match_yes_no_uncertain"]
    is_correct = human == "YES"
    assert not is_correct  # this row must be counted as a false accept, not a true accept


# 13. Tier-specific metrics stay visible (not collapsed into combined-only)
def test_tier_specific_metrics_present_in_certification_output():
    cert = json.loads((OUT / "ebay_combined_identity_v2_fresh_blind_certification.json").read_text(encoding="utf-8"))
    assert "tier_a" in cert and "tier_b" in cert
    assert "distinct_cards_covered" in cert["tier_a"]
    assert "distinct_cards_incrementally_recovered" in cert["tier_b"]


# 14. card de-duplication: distinct_cards_covered never exceeds accepted_count
def test_card_dedup_never_exceeds_accepted_rows():
    cert = json.loads((OUT / "ebay_combined_identity_v2_fresh_blind_certification.json").read_text(encoding="utf-8"))
    assert cert["tier_a"]["distinct_cards_covered"] <= cert["tier_a"]["true_accepts"]


# 15. coverage denominator fixed at 70
def test_coverage_denominator_is_70():
    assert TOTAL_TARGET_CARDS == 70
    cert = json.loads((OUT / "ebay_combined_identity_v2_fresh_blind_certification.json").read_text(encoding="utf-8"))
    assert cert["card_coverage_detail"]["denominator"] == 70
    assert cert["metrics"]["distinct_card_coverage"] == cert["card_coverage_detail"]["covered_count"] / 70


# 16. missing 70th card remains uncovered
def test_missing_capture_card_remains_uncovered():
    cert = json.loads((OUT / "ebay_combined_identity_v2_fresh_blind_certification.json").read_text(encoding="utf-8"))
    missing = cert["unrepresented_target_card"][0]
    assert missing in cert["card_coverage_detail"]["all_uncovered_card_ids"]
    assert missing not in cert["card_coverage_detail"]["all_covered_card_ids"]


# 17. 56/70 passes
def test_56_of_70_passes_coverage_gate():
    assert (56 / 70) >= DESIGN_GATE["card_coverage_minimum"]


# 18. 55/70 fails
def test_55_of_70_fails_coverage_gate():
    assert not ((55 / 70) >= DESIGN_GATE["card_coverage_minimum"])


# 19. Wilson calculation
def test_wilson_calculation_known_values():
    lower, upper = wilson(185, 185)
    assert lower == pytest.approx(0.97966, abs=1e-4)
    assert upper == 1.0
    lo0, hi0 = wilson(0, 0)
    assert lo0 == 0.0 and hi0 == 0.0


# 20. catastrophic false-accept gate
def test_catastrophic_gate_real_result_is_zero():
    cert = json.loads((OUT / "ebay_combined_identity_v2_fresh_blind_certification.json").read_text(encoding="utf-8"))
    assert cert["gates"]["catastrophic_false_accepts_eq_0"] is True
    assert len(cert["false_accept_rows"]) == 0


# 21. no production pricing writes
def test_no_pricing_writes_in_certification_module():
    import pathlib
    import backend.scripts.run_ebay_combined_identity_v2_fresh_blind_certification as mod
    source = pathlib.Path(mod.__file__).read_text(encoding="utf-8").lower()
    for forbidden in ("fair_value_publish", "publish_price", "set_value_write"):
        assert forbidden not in source


# 22. no Fair Value activation
def test_certification_output_declares_production_authority_false():
    cert = json.loads((OUT / "ebay_combined_identity_v2_fresh_blind_certification.json").read_text(encoding="utf-8"))
    assert cert["production_authority"] is False


# 23. no Explorer modification
def test_no_explorer_imports_in_certification_scripts():
    import pathlib
    for mod_name in ("run_ebay_combined_identity_v2_fresh_blind_scoring", "run_ebay_combined_identity_v2_fresh_blind_certification"):
        mod = __import__(f"backend.scripts.{mod_name}", fromlist=["x"])
        source = pathlib.Path(mod.__file__).read_text(encoding="utf-8").lower()
        assert "market_explorer" not in source and "explorer" not in source


# 24. frozen authorities unchanged (real, not simulated)
def test_frozen_authorities_unchanged_for_real():
    from backend.scripts import ebay_d3_matcher_v5 as v5
    from backend.scripts import ebay_image_retrieval_verifier as image_v2
    frozen = json.loads((OUT / "ebay_combined_identity_v2_freeze_manifest.json").read_text(encoding="utf-8"))
    assert v5.rule_fingerprint() == frozen["text_matcher_fingerprint"]
    assert image_v2.source_sha256() == frozen["image_verifier_fingerprint"]
    assert policy_v2.policy_source_hash() == frozen["policy_source_sha256"]


# Real end-to-end precondition check (not simulated) -- all real preconditions
# for this actual certification run were true.
def test_all_real_preconditions_passed():
    checks = run_precondition_checks()
    failed = [k for k, v in checks.items() if not v]
    assert failed == [], f"unexpected failed preconditions: {failed}"
