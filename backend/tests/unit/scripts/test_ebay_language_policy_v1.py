"""Tests for LANGUAGE-v1 (EBAY_E2_15) and COMBINED-IDENTITY-v3.

Covers the 18 required test areas from the EBAY_E2_15 task spec.
No production writes; no E2.14 certification labels are read here
(that consumed cohort is used only by report-generation scripts, never
by these unit tests).
"""
from __future__ import annotations

import pytest

from backend.scripts import ebay_language_policy_v1 as lang
from backend.scripts import ebay_combined_identity_policy_v3 as combined_v3
from backend.scripts.ebay_combined_identity_policy_v2 import (
    TIER_A_IMAGE_VERIFIED,
    TIER_B_TEXT_VERIFIED_IMAGE_UNVERIFIED,
)


# --------------------------------------------------------------------------
# 1. explicit English language aspect
# --------------------------------------------------------------------------
def test_explicit_english_aspect_is_match():
    result = lang.evaluate_structured_aspect([{"name": "Language", "value": "English"}])
    assert result.language_state == lang.LANGUAGE_MATCH
    assert result.may_reject is False


# --------------------------------------------------------------------------
# 2. explicit non-English language aspect
# --------------------------------------------------------------------------
def test_explicit_japanese_aspect_is_mismatch():
    result = lang.evaluate_structured_aspect([{"name": "Language", "value": "Japanese"}])
    assert result.language_state == lang.LANGUAGE_MISMATCH
    assert result.may_reject is True
    assert result.observed_language == "JAPANESE"


@pytest.mark.parametrize("value", ["French", "German", "Korean", "Spanish", "Italian", "Portuguese", "Chinese"])
def test_explicit_other_language_values_are_mismatch(value):
    result = lang.evaluate_structured_aspect([{"name": "Language", "value": value}])
    assert result.language_state == lang.LANGUAGE_MISMATCH


# --------------------------------------------------------------------------
# 3. missing aspect -> UNVERIFIED
# --------------------------------------------------------------------------
def test_missing_aspect_is_unverified():
    result = lang.evaluate_structured_aspect([{"name": "Rarity", "value": "Holo"}])
    assert result.language_state == lang.LANGUAGE_UNVERIFIED
    assert result.may_reject is False


def test_empty_aspect_list_is_unverified():
    result = lang.evaluate_structured_aspect([])
    assert result.language_state == lang.LANGUAGE_UNVERIFIED
    result_none = lang.evaluate_structured_aspect(None)
    assert result_none.language_state == lang.LANGUAGE_UNVERIFIED


# --------------------------------------------------------------------------
# 4. unknown aspect -> UNVERIFIED
# --------------------------------------------------------------------------
def test_unrecognized_language_value_is_unverified_not_guessed():
    result = lang.evaluate_structured_aspect([{"name": "Language", "value": "Klingon"}])
    assert result.language_state == lang.LANGUAGE_UNVERIFIED
    assert result.reason == "language_aspect_value_not_in_closed_vocabulary"


def test_empty_string_value_is_unverified():
    result = lang.evaluate_structured_aspect([{"name": "Language", "value": ""}])
    assert result.language_state == lang.LANGUAGE_UNVERIFIED


# --------------------------------------------------------------------------
# 5. seller country does not imply card language
# --------------------------------------------------------------------------
def test_seller_country_field_never_consulted():
    assert "seller_country" in lang.FORBIDDEN_EVIDENCE_FIELDS
    # extract_language_aspect ignores every key except a literal "Language"
    # named aspect -- a seller_country field anywhere in the payload can
    # never influence the verdict.
    result = lang.evaluate_structured_aspect(
        [{"name": "seller_country", "value": "Japan"}]
    )
    assert result.language_state == lang.LANGUAGE_UNVERIFIED


# --------------------------------------------------------------------------
# 6. marketplace does not imply card language
# --------------------------------------------------------------------------
def test_marketplace_field_never_consulted():
    assert "marketplace" in lang.FORBIDDEN_EVIDENCE_FIELDS
    result = lang.evaluate_structured_aspect(
        [{"name": "marketplace", "value": "EBAY_JP"}]
    )
    assert result.language_state == lang.LANGUAGE_UNVERIFIED


# --------------------------------------------------------------------------
# 7. English title does not override explicit foreign-language evidence
# --------------------------------------------------------------------------
def test_english_title_never_overrides_explicit_mismatch():
    # This module has no title parameter at all in evaluate_structured_aspect
    # -- title text cannot be passed in and cannot influence the verdict.
    # Observed live case (EBAY_E2_15 dev probe): item v1|407215142815|0,
    # title "PIKACHU EX #277 POKEMON ASCENDED HEROES - MINT/NEAR MINT"
    # (plain English, no language marker), structured Language aspect
    # "Japanese".
    result = lang.evaluate_structured_aspect(
        [
            {"name": "Set", "value": "SV2a Pokemon Card 151"},
            {"name": "Language", "value": "Japanese"},
        ]
    )
    assert result.language_state == lang.LANGUAGE_MISMATCH
    assert "title" not in result.to_dict()


def test_french_title_word_does_not_override_english_aspect():
    # Observed live case: item v1|158291222488|0, title contains the word
    # "French" (as part of the card's French name "Dracaufeu"), but the
    # structured Language aspect is explicitly "English". Title text is
    # never read by this module, so the word "French" cannot leak in.
    result = lang.evaluate_structured_aspect(
        [{"name": "Language", "value": "English"}]
    )
    assert result.language_state == lang.LANGUAGE_MATCH


# --------------------------------------------------------------------------
# 8. seller-provided vs inferred aspect semantics
# --------------------------------------------------------------------------
def test_no_provenance_field_available_documented_limitation():
    """eBay's getItem localizedAspects response (verified live, EBAY_E2_15
    Phase B) carries no field distinguishing seller-typed vs
    catalog-inferred aspects. LANGUAGE-v1 therefore treats any explicit
    Language aspect as one merged structured-authority tier -- this test
    documents that both hypothetical provenance shapes evaluate
    identically today, which IS the intended (honest, non-invented)
    behavior."""
    seller_shaped = [{"name": "Language", "value": "Japanese", "source": "SELLER"}]
    inferred_shaped = [{"name": "Language", "value": "Japanese", "source": "CATALOG_INFERRED"}]
    r1 = lang.evaluate_structured_aspect(seller_shaped)
    r2 = lang.evaluate_structured_aspect(inferred_shaped)
    assert r1.language_state == r2.language_state == lang.LANGUAGE_MISMATCH
    assert r1.evidence_source == r2.evidence_source == "structured_aspect_seller_or_catalog"


# --------------------------------------------------------------------------
# 9 & 10 & 11. OCR (NOT implemented in frozen v1 -- these tests assert
# that fact and that no OCR path exists to accidentally reject on.
# --------------------------------------------------------------------------
def test_no_ocr_path_exists_in_frozen_v1():
    assert not hasattr(lang, "evaluate_ocr")
    assert not hasattr(lang, "ocr_language_check")


def test_getitem_call_failure_is_unverified_never_mismatch():
    result = lang.evaluate_getitem_call_failure("network_timeout")
    assert result.language_state == lang.LANGUAGE_UNVERIFIED
    assert result.may_reject is False


def test_getitem_call_failure_reason_is_recorded():
    result = lang.evaluate_getitem_call_failure("http_500")
    assert result.reason == "http_500"


# --------------------------------------------------------------------------
# 12. Latin-script foreign language hard case
# --------------------------------------------------------------------------
def test_french_latin_script_card_is_mismatch_not_falsely_matched():
    # Observed live case: item v1|407213129938|0, title
    # "Dracaufeu / Charizard 4/102 Base Set French MP Pokemon TCG",
    # explicit Language aspect "French" -- artwork/alphabet is close to
    # English but the structured signal still correctly resolves.
    result = lang.evaluate_structured_aspect([{"name": "Language", "value": "French"}])
    assert result.language_state == lang.LANGUAGE_MISMATCH


def test_german_missing_aspect_stays_unverified_not_mismatch():
    # Observed live case: 4/4 live "German" search results had NO
    # explicit Language aspect despite the word "German" in every title
    # -- a real, disclosed structured-metadata coverage gap. LANGUAGE-v1
    # must fail safe to UNVERIFIED here, never guess MISMATCH from the
    # title word "German".
    result = lang.evaluate_structured_aspect([{"name": "Rarity", "value": "Holo Rare"}])
    assert result.language_state == lang.LANGUAGE_UNVERIFIED


# --------------------------------------------------------------------------
# 13. no false mismatch on development English positives
# --------------------------------------------------------------------------
@pytest.mark.parametrize(
    "aspects",
    [
        [{"name": "Language", "value": "English"}],
        [{"name": "Language", "value": "EN"}],
        [{"name": "Language", "value": "Eng"}],
    ],
)
def test_no_false_mismatch_on_english_variants(aspects):
    result = lang.evaluate_structured_aspect(aspects)
    assert result.language_state == lang.LANGUAGE_MATCH


def test_development_true_accept_sample_zero_false_mismatch():
    """EBAY_E2_15 Phase D/H: a bounded live getItem sample of 15 E2.14
    TRUE-accept rows (human-YES, excluding the one known false accept)
    returned 12/15 explicit "English" aspects and 3/15 UNVERIFIED
    (missing aspect); 0/15 MISMATCH. This test locks that same input
    shape against a false-mismatch regression."""
    sample_aspect_lists = (
        [[{"name": "Language", "value": "English"}]] * 12
        + [[]] * 3
    )
    for aspects in sample_aspect_lists:
        result = lang.evaluate_structured_aspect(aspects)
        assert result.language_state != lang.LANGUAGE_MISMATCH


# --------------------------------------------------------------------------
# 14. language mismatch veto (COMBINED-v3)
# --------------------------------------------------------------------------
def test_combined_v3_mismatch_vetoes_before_tier_eligibility():
    mismatch = lang.evaluate_structured_aspect([{"name": "Language", "value": "Japanese"}])
    result = combined_v3.combine(
        text_state="HIGH_CONFIDENCE",
        image_state="UNVERIFIED",
        language_result=mismatch,
        text_row_fields={},
    )
    assert result.combined_state == combined_v3.REJECTED_LANGUAGE_CONTRADICTION
    assert result.is_eligible is False


def test_combined_v3_catches_the_e2_14_catastrophic_row_shape():
    """Reproduces the exact E2.14 catastrophic row's text/image inputs
    (row E13-0127: HIGH_CONFIDENCE text, no contradiction, IMAGE-v2
    UNVERIFIED -> Tier B accepted under COMBINED-v2) plus the LANGUAGE-v1
    verdict measured live for that row's real listing item
    (v1|407215142815|0: explicit Language aspect = "Japanese"). This is
    a POST-HOC diagnostic only -- LANGUAGE-v1's contract was frozen from
    the broader development evidence, not tuned to this specific row."""
    catastrophic_language_result = lang.evaluate_structured_aspect(
        [{"name": "Set", "value": "SV2a Pokemon Card 151"}, {"name": "Language", "value": "Japanese"}]
    )
    result = combined_v3.combine(
        text_state="HIGH_CONFIDENCE",
        image_state="UNVERIFIED",
        language_result=catastrophic_language_result,
        text_row_fields={},
    )
    assert result.combined_state == combined_v3.REJECTED_LANGUAGE_CONTRADICTION
    assert result.is_eligible is False


# --------------------------------------------------------------------------
# 15. language unverified preserves combined-v2 behavior
# --------------------------------------------------------------------------
def test_combined_v3_unverified_preserves_tier_a():
    unverified = lang.evaluate_structured_aspect([])
    result = combined_v3.combine(
        text_state="HIGH_CONFIDENCE",
        image_state="MATCH",
        language_result=unverified,
        text_row_fields={},
    )
    assert result.combined_state == TIER_A_IMAGE_VERIFIED
    assert result.is_eligible is True
    assert result.is_image_verified is True


def test_combined_v3_unverified_preserves_tier_b():
    unverified = lang.evaluate_structured_aspect([])
    result = combined_v3.combine(
        text_state="HIGH_CONFIDENCE",
        image_state="UNVERIFIED",
        language_result=unverified,
        text_row_fields={},
    )
    assert result.combined_state == TIER_B_TEXT_VERIFIED_IMAGE_UNVERIFIED
    assert result.is_eligible is True
    assert result.is_image_verified is False


def test_combined_v3_match_preserves_v2_behavior_identically():
    match = lang.evaluate_structured_aspect([{"name": "Language", "value": "English"}])
    v3_result = combined_v3.combine("HIGH_CONFIDENCE", "MATCH", match, {})
    assert v3_result.combined_state == TIER_A_IMAGE_VERIFIED


def test_combined_v3_preserves_v2_text_contradiction_reject():
    unverified = lang.evaluate_structured_aspect([])
    result = combined_v3.combine(
        text_state="HIGH_CONFIDENCE",
        image_state="MATCH",
        language_result=unverified,
        text_row_fields={"card_or_sealed_nonshcard": "SEALED"},
    )
    assert result.combined_state == "REJECTED_TEXT"


def test_combined_v3_preserves_v2_image_mismatch_veto():
    unverified = lang.evaluate_structured_aspect([])
    result = combined_v3.combine(
        text_state="HIGH_CONFIDENCE",
        image_state="MISMATCH",
        language_result=unverified,
        text_row_fields={},
    )
    assert result.combined_state == "REJECTED_IMAGE_CONTRADICTION"


# --------------------------------------------------------------------------
# 16. consumed E2.14 excluded from tuning
# --------------------------------------------------------------------------
def test_no_e2_14_label_file_imported_by_policy_modules():
    """The policy modules may DISCUSS the consumed E2.14 cohort in their
    docstrings (documenting the failure that motivated LANGUAGE-v1), but
    must never programmatically open/read/import any E2.14 label or
    prediction artifact -- no rule in this module was fit against it."""
    import backend.scripts.ebay_language_policy_v1 as mod1
    import backend.scripts.ebay_combined_identity_policy_v3 as mod2

    for mod in (mod1, mod2):
        assert "ebay_e2_14_fresh_blind_certification" not in mod.__dict__
        assert "ebay_e2_14_fresh_blind_predictions" not in mod.__dict__
        assert "ebay_manual_gold_labels" not in mod.__dict__
        for name in dir(mod):
            if name.startswith("__"):
                continue
            assert "e2_14" not in name.lower()
            assert "gold_labels" not in name.lower()


# --------------------------------------------------------------------------
# 17. frozen-policy fingerprint
# --------------------------------------------------------------------------
def test_language_policy_fingerprint_deterministic():
    fp1 = lang.policy_fingerprint("dev_corpus_v1_fp")
    fp2 = lang.policy_fingerprint("dev_corpus_v1_fp")
    assert fp1 == fp2
    assert len(fp1) == 64  # sha256 hex


def test_language_policy_fingerprint_changes_with_corpus():
    fp1 = lang.policy_fingerprint("corpus_a")
    fp2 = lang.policy_fingerprint("corpus_b")
    assert fp1 != fp2


def test_combined_v3_fingerprint_deterministic_and_composes_v2():
    fp1 = combined_v3.policy_fingerprint("text_fp", "image_fp", "lang_fp")
    fp2 = combined_v3.policy_fingerprint("text_fp", "image_fp", "lang_fp")
    assert fp1 == fp2
    fp3 = combined_v3.policy_fingerprint("text_fp", "image_fp", "different_lang_fp")
    assert fp1 != fp3


# --------------------------------------------------------------------------
# 18. no production writes
# --------------------------------------------------------------------------
def test_modules_contain_no_production_write_calls():
    """No file-write, DB-insert, or Supabase call anywhere in the
    executable source of either policy module (module docstrings may
    reference the research report path in prose, which is fine -- this
    checks for actual write operations, not mentions)."""
    import ast
    import backend.scripts.ebay_language_policy_v1 as mod1
    import backend.scripts.ebay_combined_identity_policy_v3 as mod2

    write_call_names = {"write_text", "write_bytes", "execute", "executemany", "insert", "upsert", "to_sql"}
    for mod in (mod1, mod2):
        tree = ast.parse(open(mod.__file__, encoding="utf-8").read())
        for node in ast.walk(tree):
            if isinstance(node, ast.Attribute):
                assert node.attr not in write_call_names, f"{mod.__name__} calls .{node.attr}(...)"
        src_lower = open(mod.__file__, encoding="utf-8").read().lower()
        assert "supabase" not in src_lower
        assert "insert into" not in src_lower


def test_valid_states_closed_set():
    assert set(lang.VALID_STATES) == {
        lang.LANGUAGE_MATCH,
        lang.LANGUAGE_MISMATCH,
        lang.LANGUAGE_UNVERIFIED,
    }
    for result in (
        lang.evaluate_structured_aspect([{"name": "Language", "value": "English"}]),
        lang.evaluate_structured_aspect([{"name": "Language", "value": "Japanese"}]),
        lang.evaluate_structured_aspect([]),
    ):
        assert result.language_state in lang.VALID_STATES
