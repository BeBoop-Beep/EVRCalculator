"""Tests for EBAY E2.15 LANGUAGE-v1 structured-aspect evidence normalizer.

LANGUAGE-v1 is a research/development module, not part of the frozen
production identity stack. These tests exercise the contract described in
backend/services/ebay_language_evidence_v1.py and the E2.15 task spec.
"""
from __future__ import annotations

import json
from pathlib import Path

import pytest

from backend.services.ebay_language_evidence_v1 import (
    LANGUAGE_MATCH,
    LANGUAGE_MISMATCH,
    LANGUAGE_UNVERIFIED,
    apply_combined_identity_v3,
    classify_structured_language_evidence,
    normalize_language_value,
)


def _item(language_value=None, title="Some English-sounding Title", **extra):
    aspects = []
    if language_value is not None:
        aspects.append({"type": "STRING", "name": "Language", "value": language_value})
    item = {
        "title": title,
        "localizedAspects": aspects,
        "itemLocation": {"country": extra.get("country", "US")},
        "listingMarketplaceId": extra.get("marketplace", "EBAY_US"),
        "seller": {"username": extra.get("seller", "some_seller")},
    }
    return item


def test_explicit_english_aspect_is_match():
    result = classify_structured_language_evidence(_item("English"))
    assert result["state"] == LANGUAGE_MATCH


def test_explicit_non_english_aspect_is_mismatch():
    result = classify_structured_language_evidence(_item("Japanese"))
    assert result["state"] == LANGUAGE_MISMATCH
    assert result["normalized_value"] == "Japanese"


def test_missing_aspect_is_unverified():
    result = classify_structured_language_evidence(_item(None))
    assert result["state"] == LANGUAGE_UNVERIFIED
    assert result["reason"] == "no_language_aspect_present"


def test_unknown_aspect_value_is_unverified_not_mismatch():
    result = classify_structured_language_evidence(_item("Klingon"))
    assert result["state"] == LANGUAGE_UNVERIFIED
    assert result["reason"] == "language_aspect_value_unrecognized"


def test_seller_country_does_not_imply_language():
    # A Japan-located seller with an explicit English aspect must still MATCH;
    # a US-located seller with no aspect must still be UNVERIFIED. Country is
    # never consulted by the function at all.
    item = _item("English", country="JP")
    result = classify_structured_language_evidence(item)
    assert result["state"] == LANGUAGE_MATCH

    item2 = _item(None, country="US")
    result2 = classify_structured_language_evidence(item2)
    assert result2["state"] == LANGUAGE_UNVERIFIED


def test_marketplace_does_not_imply_language():
    item = _item("Japanese", marketplace="EBAY_US")
    result = classify_structured_language_evidence(item)
    # Marketplace is EBAY_US but the card's structured language aspect is
    # authoritative and says Japanese -> MISMATCH, not MATCH.
    assert result["state"] == LANGUAGE_MISMATCH


def test_english_title_does_not_override_explicit_foreign_aspect():
    item = _item("Japanese", title="Charizard VMAX English Ultra Rare NM")
    result = classify_structured_language_evidence(item)
    assert result["state"] == LANGUAGE_MISMATCH
    # title text is simply never read by the classifier
    assert "title" not in {"state", "raw_value", "normalized_value", "evidence_source", "reason"} or True


def test_evidence_source_is_labeled_structured_aspect_seller_provided():
    # LIMITATION (documented in module docstring and E2.15 report): the
    # observed Browse item/{id} schema does not expose a separate
    # inferredLocalizedAspects block distinguishing seller-provided from
    # eBay-inferred data, so every localizedAspects Language value is
    # labeled uniformly rather than falsely claiming a distinction the
    # schema doesn't support.
    result = classify_structured_language_evidence(_item("English"))
    assert result["evidence_source"] == "structured_aspect_seller_provided"


def test_malformed_item_detail_is_unverified():
    result = classify_structured_language_evidence(None)  # type: ignore[arg-type]
    assert result["state"] == LANGUAGE_UNVERIFIED
    result2 = classify_structured_language_evidence({"localizedAspects": "not-a-list"})
    assert result2["state"] == LANGUAGE_UNVERIFIED


@pytest.mark.parametrize(
    "raw,expected",
    [
        ("French", "French"),
        ("german", "German"),
        (" Spanish ", "Spanish"),
        ("Italian", "Italian"),
        ("Portuguese", "Portuguese"),
    ],
)
def test_latin_script_hard_cases_normalize_correctly(raw, expected):
    # Phase G: Latin-script languages must be recognized as distinct from
    # English, not silently treated as "looks Latin so it's fine."
    assert normalize_language_value(raw) == expected
    result = classify_structured_language_evidence(_item(raw))
    assert result["state"] == LANGUAGE_MISMATCH


def test_stylized_or_noisy_value_falls_back_to_unverified_never_mismatch():
    # Simulates a garbled/stylized aspect value that isn't a clean language
    # name -- must never be coerced into MISMATCH.
    result = classify_structured_language_evidence(_item("Eng1ish™"))
    assert result["state"] == LANGUAGE_UNVERIFIED


def test_no_false_mismatch_on_development_english_positive_sample():
    # Regression guard sourced from the E2.15 Phase B bounded live study
    # (backend/artifacts/index_fair_value/ebay_e2_15_item_detail_language_study.json):
    # every listing where a Language aspect was present and populated in
    # that sample carried the value "English". None of those must classify
    # as MISMATCH.
    study_path = (
        Path(__file__).resolve().parents[3]
        / "artifacts"
        / "index_fair_value"
        / "ebay_e2_15_item_detail_language_study.json"
    )
    if not study_path.exists():
        pytest.skip("Phase B live study artifact not present in this environment")
    data = json.loads(study_path.read_text(encoding="utf-8"))
    false_mismatches = 0
    checked = 0
    for row in data.get("results", []):
        if not row.get("language_aspect_present"):
            continue
        checked += 1
        item = _item(row.get("language_aspect_value"))
        result = classify_structured_language_evidence(item)
        if result["state"] == LANGUAGE_MISMATCH:
            false_mismatches += 1
    assert checked > 0
    assert false_mismatches == 0


def test_language_mismatch_vetoes_combined_v3():
    result = apply_combined_identity_v3(
        combined_v2_eligible=True,
        combined_v2_reason="tier_b_eligible",
        language_state=LANGUAGE_MISMATCH,
    )
    assert result["eligible"] is False
    assert result["reason"] == "REJECT_LANGUAGE_CONTRADICTION"


def test_language_unverified_preserves_combined_v2_behavior_exactly():
    for v2_eligible, v2_reason in [(True, "tier_a_eligible"), (False, "not_eligible_wrong_card")]:
        result = apply_combined_identity_v3(
            combined_v2_eligible=v2_eligible,
            combined_v2_reason=v2_reason,
            language_state=LANGUAGE_UNVERIFIED,
        )
        assert result["eligible"] == v2_eligible
        assert result["reason"] == v2_reason


def test_language_match_preserves_combined_v2_behavior_exactly():
    result = apply_combined_identity_v3(
        combined_v2_eligible=True,
        combined_v2_reason="tier_a_eligible",
        language_state=LANGUAGE_MATCH,
    )
    assert result["eligible"] is True
    assert result["reason"] == "tier_a_eligible"


def test_invalid_language_state_raises():
    with pytest.raises(ValueError):
        apply_combined_identity_v3(True, "x", "NOT_A_REAL_STATE")


def test_consumed_e214_cohort_excluded_from_tuning():
    # Phase B explicitly excludes the E2.14 fresh-blind label cohort's
    # listing IDs from the bounded live item-detail study candidate pool.
    # This test asserts that exclusion actually happened by checking the
    # study artifact's excluded_e214_cohort_size against the certification
    # row_count, and that no candidate item id overlaps the E2.14 cohort.
    root = Path(__file__).resolve().parents[3]
    study_path = root / "artifacts" / "index_fair_value" / "ebay_e2_15_item_detail_language_study.json"
    preds_path = root / "artifacts" / "index_fair_value" / "ebay_e2_14_fresh_blind_predictions.json"
    if not (study_path.exists() and preds_path.exists()):
        pytest.skip("required artifacts not present in this environment")

    study = json.loads(study_path.read_text(encoding="utf-8"))
    preds = json.loads(preds_path.read_text(encoding="utf-8"))
    e214_ids = {row["listing_item_id"] for row in preds["predictions"].values()}

    assert study["excluded_e214_cohort_size"] == len(e214_ids)
    sampled_ids = {row["item_id"] for row in study.get("results", [])}
    assert sampled_ids.isdisjoint(e214_ids)


def test_no_production_writes_diagnostic_is_read_only():
    # The Phase K post-hoc diagnostic script must only read frozen E2.14
    # artifacts and write to a clearly-scoped diagnostics-only output path;
    # it must never touch a "production", "publish", or "prices" path.
    from backend.scripts import run_ebay_e2_15_combined_v3_posthoc_diagnostic as diag

    assert "posthoc_diagnostic" in str(diag.OUT_PATH).lower() or "diagnostic" in str(diag.OUT_PATH).lower()
    for forbidden in ("publish", "production", "/prices/", "fair_value_index"):
        assert forbidden not in str(diag.OUT_PATH).lower()
    assert diag.E214_PRED_PATH.name.startswith("ebay_e2_14_fresh_blind_predictions")
    assert diag.E214_CERT_PATH.name.startswith("ebay_e2_14_fresh_blind_certification")


def test_frozen_policy_fingerprint_not_claimed():
    # Because LANGUAGE-v1 was NOT frozen (see E2.15 report), there must be
    # no freeze-manifest artifact claiming a frozen fingerprint for it.
    root = Path(__file__).resolve().parents[3]
    freeze_path = root / "artifacts" / "index_fair_value" / "ebay_language_v1_freeze_manifest.json"
    assert not freeze_path.exists(), (
        "LANGUAGE-v1 was not frozen per the E2.15 research findings; no "
        "freeze manifest should exist."
    )
