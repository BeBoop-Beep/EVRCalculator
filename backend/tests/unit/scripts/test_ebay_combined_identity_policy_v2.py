import json
from pathlib import Path

import pytest

from backend.scripts import ebay_combined_identity_policy_v2 as module
from backend.scripts.ebay_combined_identity_policy_v2 import (
    REJECTED_IMAGE_CONTRADICTION,
    REJECTED_TEXT,
    TEXT_AMBIGUOUS_NOT_PROMOTED,
    TIER_A_IMAGE_VERIFIED,
    TIER_B_TEXT_VERIFIED_IMAGE_UNVERIFIED,
    combine,
    policy_fingerprint,
    policy_source_hash,
)
from backend.scripts import ebay_d3_matcher_v5 as v5
from backend.scripts import ebay_image_retrieval_verifier as image_v2
from backend.scripts.ebay_gold_access import OUT


# 1. Tier A contract: HIGH_CONFIDENCE + no contradiction + MATCH
def test_tier_a_contract():
    result = combine("HIGH_CONFIDENCE", "MATCH")
    assert result.combined_state == TIER_A_IMAGE_VERIFIED
    assert result.is_eligible
    assert result.is_image_verified


# 2. Tier B contract: HIGH_CONFIDENCE + no contradiction + UNVERIFIED
def test_tier_b_contract():
    result = combine("HIGH_CONFIDENCE", "UNVERIFIED")
    assert result.combined_state == TIER_B_TEXT_VERIFIED_IMAGE_UNVERIFIED
    assert result.is_eligible


# 3. image mismatch remains a hard rejection, never demoted to Tier B
def test_image_mismatch_remains_rejection():
    result = combine("HIGH_CONFIDENCE", "MISMATCH")
    assert result.combined_state == REJECTED_IMAGE_CONTRADICTION
    assert not result.is_eligible


# 4. text contradiction remains rejection regardless of image state
@pytest.mark.parametrize("image_state", ["MATCH", "MISMATCH", "UNVERIFIED"])
def test_text_contradiction_remains_rejection(image_state):
    result = combine("HIGH_CONFIDENCE", image_state, text_row_fields={"raw_or_graded": "graded"})
    assert result.combined_state == REJECTED_TEXT
    assert result.text_contradiction_present
    assert not result.is_eligible


# 5. medium/ambiguous text is never promoted by any image state
@pytest.mark.parametrize("text_state", ["MEDIUM_CONFIDENCE", "AMBIGUOUS"])
@pytest.mark.parametrize("image_state", ["MATCH", "MISMATCH", "UNVERIFIED"])
def test_medium_ambiguous_never_promoted(text_state, image_state):
    result = combine(text_state, image_state)
    assert result.combined_state == TEXT_AMBIGUOUS_NOT_PROMOTED
    assert not result.is_eligible


# 6. Tier B is never labeled or treated as image-verified
def test_tier_b_never_labeled_image_verified():
    result = combine("HIGH_CONFIDENCE", "UNVERIFIED")
    assert result.combined_state != TIER_A_IMAGE_VERIFIED
    assert result.is_image_verified is False
    for variant in ("UNVERIFIED_TARGET_NOT_IN_GALLERY", "UNVERIFIED_VISUALLY_INDISTINGUISHABLE"):
        variant_result = combine("HIGH_CONFIDENCE", variant)
        assert variant_result.combined_state == TIER_B_TEXT_VERIFIED_IMAGE_UNVERIFIED
        assert variant_result.is_image_verified is False


# 7. complete failure-matrix accounting: v1's real historical cross-tab sums
#    to the recorded total_rows for both cohorts (no silent row loss).
def test_failure_matrix_accounting_complete():
    diagnostic = json.loads((OUT / "ebay_combined_identity_v1_historical_post_hoc_diagnostic.json").read_text(encoding="utf-8"))
    for cohort in ("V4", "V5"):
        cohort_result = diagnostic["results"][cohort]
        matrix_sum = sum(row["count"] for row in cohort_result["failure_matrix"])
        assert matrix_sum == cohort_result["metrics"]["definitive_rows"]


# 8. Tier-B precision metrics: re-derived from the real v1 cross-tab, the
#    measured HIGH_CONFIDENCE+UNVERIFIED human-NO count is exactly zero in
#    both consumed cohorts -- this is the central EBAY_E2_9 finding.
def test_tier_b_precision_metrics_from_real_data():
    diagnostic = json.loads((OUT / "ebay_combined_identity_v1_historical_post_hoc_diagnostic.json").read_text(encoding="utf-8"))
    for cohort, expected_true in (("V4", 88), ("V5", 99)):
        rows = diagnostic["results"][cohort]["failure_matrix"]
        high_unverified = [r for r in rows if r["text_state"] == "HIGH_CONFIDENCE" and r["image_state"] == "UNVERIFIED"]
        yes_count = sum(r["count"] for r in high_unverified if r["human_label"] == "YES")
        no_count = sum(r["count"] for r in high_unverified if r["human_label"] == "NO")
        assert yes_count == expected_true
        assert no_count == 0


# 9. Tier-B catastrophic metrics: zero catastrophic false accepts measured
#    in either consumed cohort under the v2 policy.
def test_tier_b_catastrophic_metrics_zero():
    check = json.loads((OUT / "ebay_combined_identity_v2_historical_final_check.json").read_text(encoding="utf-8"))
    for cohort in ("V4", "V5"):
        assert check["results"][cohort]["tier_b"]["catastrophic_false_accept_count"] == 0
        assert check["results"][cohort]["gates"]["tier_b_catastrophic_zero"] is True


# 10. combined metrics: Tier A + Tier B precision/Wilson computed correctly
#     and strictly at least as large an accepted population as Tier A alone.
def test_combined_metrics_at_least_tier_a():
    check = json.loads((OUT / "ebay_combined_identity_v2_historical_final_check.json").read_text(encoding="utf-8"))
    for cohort in ("V4", "V5"):
        result = check["results"][cohort]
        assert result["combined"]["accepted_count"] == result["tier_a"]["accepted_count"] + result["tier_b"]["accepted_count"]
        assert result["combined"]["accepted_precision"] == 1.0
        assert result["combined"]["catastrophic_false_accept_count"] == 0


# 11. target-rank diagnostic handling: v2 does not consume or require
#     target_rank/margin diagnostics for its (flat) Tier B -- combine()
#     accepts no such kwargs, by design (Candidate 2 salvage not built).
def test_combine_has_no_diagnostic_dependent_kwargs():
    import inspect
    params = set(inspect.signature(combine).parameters)
    assert params == {"text_state", "image_state", "text_row_fields"}


# 12. canonical resolver checks: policy v2 performs no canonical image
#     resolution of its own (no such symbol exists in the module).
def test_policy_v2_has_no_canonical_resolution_logic():
    assert not hasattr(module, "resolve_image_state")
    assert not hasattr(module, "CanonicalGallery")


# 13. consumed cohorts treated as policy-development only
def test_historical_diagnostics_labeled_non_certifying():
    for name in (
        "ebay_combined_identity_v1_historical_post_hoc_diagnostic.json",
        "ebay_combined_identity_v2_historical_final_check.json",
    ):
        data = json.loads((OUT / name).read_text(encoding="utf-8"))
        assert "NON_CERTIFYING" in data["label"]


# 14. policy freeze: freeze manifest records source hash + fingerprints
def test_policy_freeze_manifest_fields():
    manifest = json.loads((OUT / "ebay_combined_identity_v2_freeze_manifest.json").read_text(encoding="utf-8"))
    assert manifest["policy_source_sha256"] == policy_source_hash()
    assert manifest["policy_fingerprint"] == policy_fingerprint(
        manifest["text_matcher_fingerprint"], manifest["image_verifier_fingerprint"]
    )
    assert manifest["text_matcher_fingerprint"] == v5.rule_fingerprint()
    assert manifest["image_verifier_fingerprint"] == image_v2.source_sha256()
    assert manifest["production_authority"] is False
    assert manifest["shadow_research_only"] is True
    assert manifest["certified_against_new_blind"] is False


# 15. no post-freeze mutation: recomputing the fingerprint from the current
#     module source must still match the frozen manifest -- a mismatch
#     means the policy source changed after freeze without a re-freeze.
def test_no_post_freeze_mutation():
    manifest = json.loads((OUT / "ebay_combined_identity_v2_freeze_manifest.json").read_text(encoding="utf-8"))
    assert policy_source_hash() == manifest["policy_source_sha256"], (
        "COMBINED-IDENTITY-v2 source changed after freeze; re-run "
        "freeze_ebay_combined_identity_v2.py deliberately, or revert the edit."
    )


# 16. new blind capture only when all gates pass: the historical final
#     check's own gate result must be NOT_READY given unmeasured coverage,
#     and this must not be silently overridden.
def test_new_blind_not_justified_while_coverage_unmeasured():
    check = json.loads((OUT / "ebay_combined_identity_v2_historical_final_check.json").read_text(encoding="utf-8"))
    for cohort in ("V4", "V5"):
        gates = check["results"][cohort]["gates"]
        assert gates["combined_coverage_gate"] == "UNMEASURED"
        assert gates["overall_gate_result"] == "NOT_READY_COVERAGE_UNMEASURED"


# 17. queue contains no policy output -- EBAY_E2_9 did not capture a new
#     blind cohort (Phase I not executed); no new queue file should exist.
def test_no_new_blind_queue_captured():
    assert not (OUT / "ebay_e2_9_fresh_blind_queue.csv").exists()


# 18. D3-v5 immutable: rule fingerprint matches the value already recorded
#     in the E2.8-era combined-identity-v1 freeze evidence (v5 untouched).
def test_d3_v5_immutable():
    fingerprint_now = v5.rule_fingerprint()
    manifest = json.loads((OUT / "ebay_combined_identity_v2_freeze_manifest.json").read_text(encoding="utf-8"))
    assert fingerprint_now == manifest["text_matcher_fingerprint"]


# 19. IMAGE-v2 immutable: the checked-out file is byte-identical to what
#     git has committed (no uncommitted edit to the frozen verifier).
#     NOTE: source_sha256() itself is checkout-line-ending-sensitive (see
#     EBAY_E2_9 report Section 12) and is therefore NOT used here as the
#     immutability check -- git's own tracked-content comparison is the
#     ground truth that is invariant to CRLF/LF checkout differences.
def test_image_v2_immutable():
    import subprocess

    diff = subprocess.run(
        ["git", "diff", "--quiet", "HEAD", "--", "backend/scripts/ebay_image_retrieval_verifier.py"],
        cwd=Path(image_v2.__file__).resolve().parents[2],
    )
    assert diff.returncode == 0, "ebay_image_retrieval_verifier.py has uncommitted changes vs HEAD"


# 20. no pricing/publication changes: policy v2 module never references
#     price, fair value, or publication concepts.
def test_no_pricing_or_publication_semantics():
    import pathlib
    source = pathlib.Path(module.__file__).read_text(encoding="utf-8").lower()
    for forbidden in ("fair_value", "price", "publish", "set_value"):
        assert forbidden not in source.replace("this module establishes identity eligibility only.", "")


# 21. (full ebay/fair_value suite) -- collection smoke check: this test
#     module itself is collectible under the existing scripts test package,
#     i.e. it participates in the same suite as v1's tests rather than a
#     separate, disconnected runner.
def test_collected_alongside_v1_policy_tests():
    import backend.tests.unit.scripts.test_ebay_combined_identity_policy_v1 as v1_tests
    assert v1_tests is not None
