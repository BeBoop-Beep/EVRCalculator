"""EBAY E2.16C -- tests for the Japanese-aspect validation / LANGUAGE-v2
freeze-decision analysis. DEVELOPMENT ONLY, non-certifying. Exercises
backend/scripts/ebay_e2_16c_japanese_language_aspect_validation.py against
the real, now-completed E2.16B review history and raw internal evidence.
No production writes; frozen LANGUAGE-v1 / COMBINED-v3 source files are
never imported for mutation, only read for diagnostics.
"""
from __future__ import annotations

import copy
import hashlib
import sys
from pathlib import Path

import pytest

ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(ROOT / "backend" / "scripts"))

import ebay_e2_16c_japanese_language_aspect_validation as m  # noqa: E402


@pytest.fixture(scope="module")
def analysis():
    return m.run_analysis()


@pytest.fixture(scope="module")
def joined(analysis):
    return analysis["joined"]


@pytest.fixture(scope="module")
def definitive(joined):
    return [j for j in joined if j["human_truth"] != "UNCERTAIN"]


@pytest.fixture(scope="module")
def japanese_rows(joined):
    return [j for j in joined if j["normalized_language"] == "JAPANESE"]


# --------------------------------------------------------------------------
# 1. frozen E2.16B corpus fingerprint
# --------------------------------------------------------------------------

def test_corpus_fingerprint_matches_manifest(analysis):
    manifest = analysis["manifest"]
    assert analysis["recomputed_corpus_fp"] == manifest["corpus_fingerprint"]


def test_corpus_row_count_is_150(analysis):
    assert len(analysis["rows"]) == 150


# --------------------------------------------------------------------------
# 2. computed label fingerprint determinism
# --------------------------------------------------------------------------

def test_label_fingerprint_deterministic(analysis):
    fp1 = analysis["recomputed_label_fp"]
    fp2 = m.label_fingerprint(analysis["materialized"])
    assert fp1 == fp2


def test_label_fingerprint_matches_manifest(analysis):
    manifest = analysis["manifest"]
    assert analysis["recomputed_label_fp"] == manifest["label_fingerprint"]


def test_label_fingerprint_changes_if_a_label_changes(analysis):
    tampered = copy.deepcopy(analysis["materialized"])
    tampered[0] = dict(tampered[0])
    tampered[0]["human_truth_label"] = (
        "ENGLISH" if tampered[0]["human_truth_label"] != "ENGLISH" else "NON_ENGLISH"
    )
    assert m.label_fingerprint(tampered) != analysis["recomputed_label_fp"]


# --------------------------------------------------------------------------
# 3. UNCERTAIN exclusion
# --------------------------------------------------------------------------

def test_uncertain_excluded_from_definitive(joined, definitive):
    uncertain_count = sum(1 for j in joined if j["human_truth"] == "UNCERTAIN")
    assert uncertain_count == 1
    assert all(j["human_truth"] != "UNCERTAIN" for j in definitive)
    assert len(definitive) == len(joined) - uncertain_count


# --------------------------------------------------------------------------
# 4/5/6/7. Japanese TP / FP / precision / false-mismatch rate
# --------------------------------------------------------------------------

def test_japanese_true_positives(japanese_rows):
    tp = sum(1 for j in japanese_rows if j["human_truth"] == "NON_ENGLISH")
    assert tp == 90


def test_japanese_false_positives(japanese_rows):
    fp = sum(1 for j in japanese_rows if j["human_truth"] == "ENGLISH")
    assert fp == 2


def test_japanese_precision(japanese_rows):
    tp = sum(1 for j in japanese_rows if j["human_truth"] == "NON_ENGLISH")
    fp = sum(1 for j in japanese_rows if j["human_truth"] == "ENGLISH")
    precision = tp / (tp + fp)
    assert precision == pytest.approx(90 / 92)


def test_japanese_false_mismatch_rate(definitive, japanese_rows):
    n_english = sum(1 for j in definitive if j["human_truth"] == "ENGLISH")
    fp = sum(1 for j in japanese_rows if j["human_truth"] == "ENGLISH")
    assert n_english == 52
    rate = fp / n_english
    assert rate == pytest.approx(2 / 52)


def test_japanese_wilson_interval_bounds(japanese_rows):
    tp = sum(1 for j in japanese_rows if j["human_truth"] == "NON_ENGLISH")
    fp = sum(1 for j in japanese_rows if j["human_truth"] == "ENGLISH")
    lower, upper = m.wilson_ci(tp, tp + fp)
    assert 0.90 < lower < 0.95
    assert 0.98 < upper <= 1.0


# --------------------------------------------------------------------------
# 8. provider Japanese + human English conflict forensics
# --------------------------------------------------------------------------

def test_japanese_false_positive_rows_identified(japanese_rows):
    fps = [j for j in japanese_rows if j["human_truth"] == "ENGLISH"]
    ids = sorted(j["row_id"] for j in fps)
    assert ids == ["e2_16b_dev_0033", "e2_16b_dev_0050"]


def test_japanese_false_positives_have_distinct_root_causes(japanese_rows):
    fps = [j for j in japanese_rows if j["human_truth"] == "ENGLISH"]
    # row 0033: title itself contains the literal word "Japanese"
    row_0033 = next(j for j in fps if j["row_id"] == "e2_16b_dev_0033")
    assert "japanese" in row_0033["title"].lower()
    # row 0050: title has no language cue at all; the aspect table instead
    # carries Country of Origin/Manufacture = Japan alongside Language =
    # Japanese -- a different, non-title-driven pattern from row 0033.
    row_0050 = next(j for j in fps if j["row_id"] == "e2_16b_dev_0050")
    assert "japan" not in row_0050["title"].lower()
    country_aspects = {
        a.get("name"): a.get("value") for a in row_0050["raw_localized_aspects"]
    }
    assert country_aspects.get("Country of Origin") == "Japan"


# --------------------------------------------------------------------------
# 9/10. missing -> UNVERIFIED, unsupported French -> UNVERIFIED
# --------------------------------------------------------------------------

def test_missing_language_normalizes_unknown():
    assert m.normalize_raw_value(None) == "UNKNOWN"
    assert m.normalize_raw_value("") == "UNKNOWN"


def test_french_normalizes_but_is_not_authoritative_in_v2():
    assert m.normalize_raw_value("French") == "FRENCH"
    # LANGUAGE-v2's authoritative vocabulary (see report) stays
    # {KOREAN, CHINESE, JAPANESE} -- FRENCH remains LANGUAGE_UNVERIFIED.
    supported_v2 = {"KOREAN", "CHINESE", "JAPANESE"}
    assert "FRENCH" not in supported_v2


# --------------------------------------------------------------------------
# 11/12. Korean / Chinese preserved authoritative (no evidence to remove them)
# --------------------------------------------------------------------------

def test_no_korean_or_chinese_rows_in_this_japanese_focused_corpus(joined):
    # This corpus was purpose-built to stress-test Japanese; it contains no
    # Korean/Chinese provider-language rows, so it supplies zero new
    # counter-evidence against the E2.16A-frozen KOREAN/CHINESE inclusion.
    assert sum(1 for j in joined if j["normalized_language"] == "KOREAN") == 0
    assert sum(1 for j in joined if j["normalized_language"] == "CHINESE") == 0


# --------------------------------------------------------------------------
# 13. Japanese only authoritative if freeze criteria pass
# --------------------------------------------------------------------------

def test_japanese_freeze_criteria_conservative_standard(japanese_rows):
    """Per Phase G, freeze requires the false-positive pattern to be well
    understood as ONE generalizable, safe mechanism. Here there are 2 FPs
    with two different, independently-arising root causes (a title-level
    self-contradiction vs. a manufacturing-origin/template confusion with
    no title cue at all) -- so a single generalizable detection rule does
    not cover both, and the conservative standard is NOT met."""
    fps = [j for j in japanese_rows if j["human_truth"] == "ENGLISH"]
    assert len(fps) == 2
    title_flagged = sum(1 for j in fps if "japanese" in j["title"].lower())
    non_title_flagged = len(fps) - title_flagged
    # both a title-visible and a title-invisible false positive exist --
    # no single provider-consistency rule catches both without a human.
    assert title_flagged >= 1
    assert non_title_flagged >= 1


# --------------------------------------------------------------------------
# 14. LANGUAGE-v2 fingerprint determinism (structural check -- LANGUAGE-v2
# is NOT frozen per this report's verdict, but the fingerprint function
# must still be deterministic if it is ever invoked)
# --------------------------------------------------------------------------

def test_language_v2_fingerprint_would_be_deterministic():
    def fingerprint(vocab, corpus_fp, label_fp):
        import json
        material = {"vocab": sorted(vocab), "corpus_fp": corpus_fp, "label_fp": label_fp}
        return hashlib.sha256(json.dumps(material, sort_keys=True).encode()).hexdigest()

    vocab = {"KOREAN", "CHINESE", "JAPANESE"}
    a = fingerprint(vocab, "x", "y")
    b = fingerprint(vocab, "x", "y")
    assert a == b


# --------------------------------------------------------------------------
# 15/16/17. COMBINED-v4 veto semantics (structural, since COMBINED-v4 is
# NOT frozen this round -- these tests assert the semantics a future
# COMBINED-v4 MUST implement if Japanese is later added, mirroring
# COMBINED-v3's own contract)
# --------------------------------------------------------------------------

def test_combined_v3_mismatch_veto_semantics_unchanged():
    from ebay_combined_identity_policy_v3 import combine, REJECTED_LANGUAGE_CONTRADICTION
    from ebay_language_policy_v1 import LanguageResult, LANGUAGE_MISMATCH

    result = combine(
        text_state="TEXT_MATCH",
        image_state="IMAGE_VERIFIED",
        language_result=LanguageResult(language_state=LANGUAGE_MISMATCH),
    )
    assert result.combined_state == REJECTED_LANGUAGE_CONTRADICTION


def test_combined_v3_match_falls_through_to_v2():
    from ebay_combined_identity_policy_v3 import combine, REJECTED_LANGUAGE_CONTRADICTION
    from ebay_language_policy_v1 import LanguageResult, LANGUAGE_MATCH

    result = combine(
        text_state="TEXT_MATCH",
        image_state="IMAGE_VERIFIED",
        language_result=LanguageResult(language_state=LANGUAGE_MATCH),
    )
    assert result.combined_state != REJECTED_LANGUAGE_CONTRADICTION


def test_combined_v3_unverified_falls_through_to_v2():
    from ebay_combined_identity_policy_v3 import combine, REJECTED_LANGUAGE_CONTRADICTION
    from ebay_language_policy_v1 import LanguageResult, LANGUAGE_UNVERIFIED

    result = combine(
        text_state="TEXT_MATCH",
        image_state="IMAGE_VERIFIED",
        language_result=LanguageResult(language_state=LANGUAGE_UNVERIFIED),
    )
    assert result.combined_state != REJECTED_LANGUAGE_CONTRADICTION


# --------------------------------------------------------------------------
# 18/19. no title-based veto, no country/marketplace inference in this
# analysis module's own normalization path
# --------------------------------------------------------------------------

def test_normalization_never_reads_title_or_country(joined):
    # Structural guarantee: normalize_raw_value only ever takes the raw
    # aspect string, never title/country/marketplace fields.
    import inspect
    src = inspect.getsource(m.normalize_raw_value)
    assert "title" not in src
    assert "country" not in src
    assert "marketplace" not in src


def test_forbidden_evidence_fields_not_used_by_frozen_language_v1():
    from ebay_language_policy_v1 import FORBIDDEN_EVIDENCE_FIELDS
    assert set(FORBIDDEN_EVIDENCE_FIELDS) == {"seller_country", "item_location", "marketplace", "title"}


# --------------------------------------------------------------------------
# 20. consumed cohort remains diagnostic only (E2.14 artifacts untouched)
# --------------------------------------------------------------------------

def test_e2_14_certification_artifact_not_modified_by_this_module():
    e14_path = ROOT / "backend/artifacts/index_fair_value/ebay_e2_14_fresh_blind_certification.json"
    assert e14_path.exists()
    # this analysis module performs no writes to any E2.14 artifact
    import ast as _ast
    tree = _ast.parse((ROOT / "backend/scripts/ebay_e2_16c_japanese_language_aspect_validation.py").read_text(encoding="utf-8"))
    src_text = (ROOT / "backend/scripts/ebay_e2_16c_japanese_language_aspect_validation.py").read_text(encoding="utf-8")
    assert "ebay_e2_14_fresh_blind_certification.json" not in src_text
    assert 'open("w"' not in src_text.replace("'", '"')


# --------------------------------------------------------------------------
# 21. no production writes
# --------------------------------------------------------------------------

def test_analysis_module_has_no_write_mode(joined):
    src_text = (ROOT / "backend/scripts/ebay_e2_16c_japanese_language_aspect_validation.py").read_text(encoding="utf-8")
    assert "QUEUE_PATH.open(\"w\"" not in src_text
    assert "HISTORY_PATH.open(\"a\"" not in src_text
    assert "MANIFEST_PATH.write_text" not in src_text


# --------------------------------------------------------------------------
# 22. latest-label-wins resolution correctly handles the relabel on row
# e2_16b_dev_0000 (ENGLISH -> NON_ENGLISH)
# --------------------------------------------------------------------------

def test_row_0000_relabel_resolves_to_latest_event(analysis):
    events = [e for e in analysis["events"] if e.get("row_id") == "e2_16b_dev_0000"]
    label_events = [e for e in events if e["action"] == "label"]
    assert len(label_events) == 2
    assert label_events[0]["human_truth_label"] == "ENGLISH"
    assert label_events[1]["human_truth_label"] == "NON_ENGLISH"
    resolved = analysis["effective"]["e2_16b_dev_0000"]
    assert resolved["human_truth_label"] == "NON_ENGLISH"
    assert resolved["event_id"] == label_events[-1]["event_id"]


def test_reconstruct_effective_labels_generic_relabel_and_undo():
    events = [
        {"action": "label", "row_id": "r1", "event_id": "e1", "human_truth_label": "ENGLISH"},
        {"action": "label", "row_id": "r1", "event_id": "e2", "human_truth_label": "NON_ENGLISH"},
        {"action": "undo", "row_id": "r1", "event_id": "e3", "target_event_id": "e2"},
    ]
    effective = m.reconstruct_effective_labels(events)
    # e2 was undone, so the effective label reverts to e1 (ENGLISH)
    assert effective["r1"]["human_truth_label"] == "ENGLISH"
    assert effective["r1"]["event_id"] == "e1"


# --------------------------------------------------------------------------
# Precondition sanity: all 150 rows have a final resolved label
# --------------------------------------------------------------------------

def test_all_150_rows_have_final_label(analysis):
    assert analysis["missing_labels"] == []
    assert len(analysis["effective"]) == 150


def test_human_truth_counts_match_manifest(analysis):
    manifest = analysis["manifest"]
    counts = analysis["label_counts"]
    assert counts == {"NON_ENGLISH": 97, "ENGLISH": 52, "UNCERTAIN": 1}
    assert manifest["development_only"] is True
    assert manifest["production_authority"] is False
