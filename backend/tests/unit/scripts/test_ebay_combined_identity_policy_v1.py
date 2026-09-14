import pytest

from backend.scripts import ebay_combined_identity_policy_v1 as module
from backend.scripts.ebay_combined_identity_policy_v1 import (
    IMAGE_MATCH,
    IMAGE_MISMATCH,
    IMAGE_UNVERIFIED,
    IMAGE_UNVERIFIED_TARGET_NOT_IN_GALLERY,
    IMAGE_UNVERIFIED_VISUALLY_INDISTINGUISHABLE,
    REJECTED_IMAGE_CONTRADICTION,
    REJECTED_TEXT,
    TEXT_AMBIGUOUS_NOT_PROMOTED,
    TEXT_MATCH_IMAGE_UNVERIFIED,
    VERIFIED_MATCH,
    combine,
    has_text_contradiction,
    resolve_image_state,
)


# 1. target missing from gallery -> UNVERIFIED
def test_resolve_image_state_target_not_in_gallery():
    class FakeGallery:
        entries = []

    result = resolve_image_state(FakeGallery(), "NOT_PRESENT", "http://example.com/x.jpg")
    assert result["image_identity_state"] == IMAGE_UNVERIFIED_TARGET_NOT_IN_GALLERY


# 2. duplicate/indistinguishable canonical art -> UNVERIFIED
def test_resolve_image_state_visually_indistinguishable():
    class FakeEntry:
        canonical_card_id = "CARD_A"

    class FakeGallery:
        entries = [FakeEntry()]

    result = resolve_image_state(
        FakeGallery(), "CARD_A", "http://example.com/x.jpg",
        indistinguishable_groups=[{"CARD_A", "CARD_A_REVERSE"}],
    )
    assert result["image_identity_state"] == IMAGE_UNVERIFIED_VISUALLY_INDISTINGUISHABLE
    assert set(result["indistinguishable_group"]) == {"CARD_A", "CARD_A_REVERSE"}


def test_indistinguishable_group_of_one_does_not_trigger():
    class FakeEntry:
        canonical_card_id = "CARD_A"

    class FakeGallery:
        entries = [FakeEntry()]

    # A "group" containing only the target itself is not a duplicate-art
    # case -- the len(group) > 1 guard must prevent a false trigger.
    result = resolve_image_state(
        FakeGallery(), "CARD_A", "file:///does/not/exist.jpg",
        indistinguishable_groups=[{"CARD_A"}],
    )
    assert result["image_identity_state"] != IMAGE_UNVERIFIED_VISUALLY_INDISTINGUISHABLE


# 3. text high + image match
def test_text_high_confidence_image_match_is_verified_match():
    result = combine("HIGH_CONFIDENCE", IMAGE_MATCH)
    assert result.combined_state == VERIFIED_MATCH


# 4. text high + image mismatch
def test_text_high_confidence_image_mismatch_is_rejected():
    result = combine("HIGH_CONFIDENCE", IMAGE_MISMATCH)
    assert result.combined_state == REJECTED_IMAGE_CONTRADICTION


# 5. text high + image unverified (all three UNVERIFIED_* variants)
@pytest.mark.parametrize("image_state", [
    IMAGE_UNVERIFIED, IMAGE_UNVERIFIED_TARGET_NOT_IN_GALLERY, IMAGE_UNVERIFIED_VISUALLY_INDISTINGUISHABLE,
])
def test_text_high_confidence_image_unverified_variants(image_state):
    result = combine("HIGH_CONFIDENCE", image_state)
    assert result.combined_state == TEXT_MATCH_IMAGE_UNVERIFIED


# 6. text reject + image match remains reject
def test_text_rejected_stays_rejected_even_with_image_match():
    result = combine("REJECTED", IMAGE_MATCH)
    assert result.combined_state == REJECTED_TEXT


# 7. text contradiction never overridden
def test_text_contradiction_never_overridden_by_image_match():
    fields = {"collector_number_consistency": "INCONSISTENT"}
    result = combine("HIGH_CONFIDENCE", IMAGE_MATCH, text_row_fields=fields)
    assert result.combined_state == REJECTED_TEXT
    assert result.text_contradiction_present is True


@pytest.mark.parametrize("field,value", [
    ("collector_number_consistency", "INCONSISTENT"),
    ("set_consistency", "inconsistent"),
    ("single_card_or_lot", "LOT_OR_BUNDLE"),
    ("raw_or_graded", "GRADED"),
    ("card_or_sealed_nonshcard", "SEALED_OR_NON_CARD"),
])
def test_each_contradiction_field_is_detected(field, value):
    assert has_text_contradiction({field: value}) is True


def test_no_contradiction_for_clean_fields():
    fields = {
        "collector_number_consistency": "CONSISTENT", "set_consistency": "CONSISTENT",
        "single_card_or_lot": "SINGLE_CARD", "raw_or_graded": "RAW", "card_or_sealed_nonshcard": "CARD",
    }
    assert has_text_contradiction(fields) is False


# 8. human uncertain excluded correctly -- documented at the benchmark layer,
# not this module (this module has no notion of human labels at all); this
# test asserts that invariant directly.
def test_combined_policy_module_has_no_human_label_concept():
    import inspect

    source = inspect.getsource(module)
    assert "UNCERTAIN" not in source  # human-label handling belongs to the benchmark script, not the policy


# 9. combined catastrophic taxonomy -- REJECTED_IMAGE_CONTRADICTION and
# REJECTED_TEXT must both be distinguishable, non-VERIFIED_MATCH outcomes
def test_all_reject_outcomes_are_distinct_from_verified_match():
    for state in (REJECTED_TEXT, REJECTED_IMAGE_CONTRADICTION, TEXT_AMBIGUOUS_NOT_PROMOTED, TEXT_MATCH_IMAGE_UNVERIFIED):
        assert state != VERIFIED_MATCH


# ambiguous/medium text is never promoted by image match
@pytest.mark.parametrize("text_state", ["MEDIUM_CONFIDENCE", "AMBIGUOUS"])
def test_weak_text_never_promoted_by_image_match(text_state):
    result = combine(text_state, IMAGE_MATCH)
    assert result.combined_state == TEXT_AMBIGUOUS_NOT_PROMOTED
    assert result.combined_state != VERIFIED_MATCH


def test_result_serializes_full_contract():
    result = combine("HIGH_CONFIDENCE", IMAGE_MATCH)
    payload = result.to_dict()
    for field in ("combined_state", "method_version", "text_state", "image_state", "text_contradiction_present", "reason"):
        assert field in payload


# 13. IMAGE-v2 immutable -- this module must never import matcher/verifier
# internals it could accidentally mutate, and must never reference
# retraining/threshold-adjustment code.
def test_combined_policy_never_modifies_image_v2_or_text_v5():
    import inspect

    source = inspect.getsource(module)
    assert "MATCH_MIN_SIMILARITY_FLOOR =" not in source  # no local threshold redefinition
    assert "rule_fingerprint" not in source  # never touches matcher internals


# 14. D3-v5 immutable -- structural guard
def test_combined_policy_does_not_import_matcher_for_reimplementation():
    import inspect

    source = inspect.getsource(module)
    # combine() takes a pre-computed text_state string; it must never import
    # ebay_d3_matcher_v5 itself (that stays the exclusive job of whatever
    # benchmark script calls classify_listing()).
    assert "import ebay_d3_matcher_v5" not in source
    assert "from backend.scripts import ebay_d3_matcher_v5" not in source


# 15. no paid services
def test_combined_policy_never_references_paid_providers():
    import inspect

    source = inspect.getsource(module)
    for forbidden in ("openai", "OpenAI", "googlevision", "rekognition", "boto3"):
        assert forbidden not in source


# 16. no public price writes
def test_combined_policy_never_touches_pricing_modules():
    import inspect

    source = inspect.getsource(module)
    for forbidden in ("financial_rip", "build_pokemon_set_page_snapshots", "simulate_", "set_value"):
        assert forbidden not in source
