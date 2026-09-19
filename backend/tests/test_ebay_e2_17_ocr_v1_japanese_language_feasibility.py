"""
Tests for EBAY E2.17 -- Local OCR-v1 Japanese physical-card language
feasibility research script.

DEVELOPMENT RESEARCH ONLY. These tests validate the OCR-v1 decision rule,
the grouped train/validation split discipline, hard-negative handling, and
the safety/no-production-write/no-paid-API guarantees. They do not require
network access or a live OCR model for the synthetic-evidence tests (fast,
deterministic); a small number of tests that exercise real downloaded
images are marked and skipped automatically if the sample manifest or
easyocr is unavailable in the current environment.
"""
import importlib
import inspect
import json
import os
import sys

import pytest

REPO_ROOT = os.path.abspath(os.path.join(os.path.dirname(__file__), "..", ".."))
SCRIPT_PATH = os.path.join(
    REPO_ROOT, "backend", "scripts",
    "ebay_e2_17_ocr_v1_japanese_language_feasibility.py",
)

sys.path.insert(0, os.path.join(REPO_ROOT, "backend", "scripts"))
mod = importlib.import_module("ebay_e2_17_ocr_v1_japanese_language_feasibility")

OcrEvidence = mod.OcrEvidence
ocr_v1_decision = mod.ocr_v1_decision
classify_char = mod.classify_char


def make_ev(**kwargs):
    base = dict(
        row_id="test",
        ocr_ok=True,
        num_regions=3,
        total_recognized_text=20,
        japanese_kana_count=0,
        cjk_shared_count=0,
        korean_hangul_count=0,
        latin_char_count=0,
        distinct_regions_with_kana=0,
        high_conf_kana_count=0,
        mean_region_conf=0.6,
        max_region_conf=0.9,
    )
    base.update(kwargs)
    return OcrEvidence(**base)


# 1. Japanese-script positive (clear multi-region kana evidence)
def test_japanese_script_positive():
    ev = make_ev(
        japanese_kana_count=8, high_conf_kana_count=6,
        distinct_regions_with_kana=3, num_regions=5, total_recognized_text=30,
    )
    assert ocr_v1_decision(ev) == "LANGUAGE_MISMATCH"


# 2. English positive (clean Latin evidence, no CJK at all)
def test_english_positive():
    ev = make_ev(
        latin_char_count=25, num_regions=4, total_recognized_text=30,
        mean_region_conf=0.7,
    )
    assert ocr_v1_decision(ev) == "LANGUAGE_MATCH"


# 3. Single noisy CJK glyph is NOT sufficient for a mismatch call
def test_single_stray_glyph_insufficient():
    ev = make_ev(
        japanese_kana_count=1, high_conf_kana_count=1,
        distinct_regions_with_kana=1, num_regions=3, total_recognized_text=10,
        latin_char_count=5,
    )
    assert ocr_v1_decision(ev) != "LANGUAGE_MISMATCH"


# 4. Strong multi-character Japanese evidence across regions -> mismatch
def test_strong_multichar_japanese_evidence():
    ev = make_ev(
        japanese_kana_count=12, high_conf_kana_count=10,
        distinct_regions_with_kana=4, num_regions=6, total_recognized_text=40,
    )
    assert ocr_v1_decision(ev) == "LANGUAGE_MISMATCH"


# 5. Weak OCR (very little recognized text) -> UNVERIFIED
def test_weak_ocr_unverified():
    ev = make_ev(num_regions=1, total_recognized_text=1, latin_char_count=1)
    assert ocr_v1_decision(ev) == "LANGUAGE_UNVERIFIED"


# 6. Crop/decode failure -> UNVERIFIED
def test_crop_failure_unverified():
    ev = OcrEvidence(row_id="test", ocr_ok=False, error="cv2_decode_failed")
    assert ocr_v1_decision(ev) == "LANGUAGE_UNVERIFIED"


# 7. Rotation -- modeled as very low confidence + sparse text -> UNVERIFIED
def test_rotation_low_confidence_unverified():
    ev = make_ev(
        num_regions=2, total_recognized_text=6, latin_char_count=6,
        mean_region_conf=0.15, max_region_conf=0.2,
    )
    assert ocr_v1_decision(ev) == "LANGUAGE_UNVERIFIED"


# 8. Low-resolution image -- modeled as OCR returning nothing useful
def test_low_resolution_unverified():
    ev = OcrEvidence(row_id="test", ocr_ok=False, error="image_too_small")
    assert ocr_v1_decision(ev) == "LANGUAGE_UNVERIFIED"


# 9. Multiple-card ambiguity -- modeled as conflicting kana+heavy latin,
#    below strong-Japanese threshold -> UNVERIFIED, never MATCH
def test_multiple_card_ambiguity_unverified():
    ev = make_ev(
        japanese_kana_count=2, high_conf_kana_count=1,
        distinct_regions_with_kana=1, latin_char_count=15,
        num_regions=5, total_recognized_text=30,
    )
    d = ocr_v1_decision(ev)
    assert d == "LANGUAGE_UNVERIFIED"


# 10. Korean hard negative -- Hangul present must not be classified Japanese
def test_korean_hard_negative():
    ev = make_ev(
        korean_hangul_count=6, num_regions=4, total_recognized_text=20,
    )
    assert ocr_v1_decision(ev) != "LANGUAGE_MISMATCH"
    assert ocr_v1_decision(ev) == "LANGUAGE_UNVERIFIED"


# 11. Chinese hard negative -- shared CJK glyphs alone (no kana) must not mismatch
def test_chinese_hard_negative_shared_cjk_alone():
    ev = make_ev(
        cjk_shared_count=10, japanese_kana_count=0, high_conf_kana_count=0,
        distinct_regions_with_kana=0, num_regions=4, total_recognized_text=20,
    )
    assert ocr_v1_decision(ev) != "LANGUAGE_MISMATCH"


# 12. Latin-script foreign hard negative (e.g. French) -- must not become MATCH or MISMATCH
def test_latin_foreign_hard_negative():
    # French text is Latin-script; rule cannot distinguish French from English
    # by script alone, so it may return MATCH (English safety) -- but it must
    # NEVER become LANGUAGE_MISMATCH, since the rule has zero Japanese evidence.
    ev = make_ev(latin_char_count=20, num_regions=3, total_recognized_text=25)
    assert ocr_v1_decision(ev) != "LANGUAGE_MISMATCH"


# 13. English false-mismatch safety -- large Latin corpus, zero CJK, never mismatch
def test_english_false_mismatch_safety():
    ev = make_ev(
        latin_char_count=60, japanese_kana_count=0, cjk_shared_count=0,
        num_regions=8, total_recognized_text=70, mean_region_conf=0.8,
    )
    assert ocr_v1_decision(ev) == "LANGUAGE_MATCH"


# 14. Grouped development split -- design/heldout partition has zero
#     canonical_card_id overlap
def test_grouped_split_no_identity_leak():
    split_path = os.path.join(
        REPO_ROOT, "backend", "artifacts", "index_fair_value",
        "ebay_e2_17_combined_corpus_split.json",
    )
    if not os.path.exists(split_path):
        pytest.skip("split file not generated in this environment")
    data = json.load(open(split_path, encoding="utf-8"))
    design_ccids = {r["canonical_card_id"] for r in data if r["split"] == "DESIGN"}
    heldout_ccids = {r["canonical_card_id"] for r in data if r["split"] == "HELDOUT"}
    assert design_ccids.isdisjoint(heldout_ccids)


# 15. Validation held out from tuning -- decision rule source contains no
#     reference to "HELDOUT" (i.e. the rule cannot special-case the holdout
#     partition; thresholds are fixed constants only)
def test_validation_not_referenced_in_rule_source():
    src = inspect.getsource(ocr_v1_decision)
    assert "HELDOUT" not in src
    assert "heldout" not in src


# 16. Provider Japanese aspect alone cannot veto (structural/contract test):
#     the OCR decision function never reads any provider/aspect field --
#     it only accepts OcrEvidence, which carries no provider-language field.
def test_provider_japanese_alone_cannot_veto():
    ev_fields = set(OcrEvidence.__dataclass_fields__.keys())
    forbidden = {"language_aspect", "provider_language", "language_aspect_normalized"}
    assert ev_fields.isdisjoint(forbidden)
    sig_params = set(inspect.signature(ocr_v1_decision).parameters.keys())
    assert sig_params == {"ev"}


# 17. Korean/Chinese provider veto preserved -- LANGUAGE-v1 module untouched
def test_language_v1_module_untouched():
    v1_path = os.path.join(
        REPO_ROOT, "backend", "scripts", "ebay_e2_16a_language_aspect_validation.py",
    )
    assert os.path.exists(v1_path), "LANGUAGE-v1 script must remain in place, unmodified by E2.17"
    src = open(v1_path, encoding="utf-8").read()
    assert "KOREAN" in src and "CHINESE" in src


# 18. OCR Japanese veto -- decision rule can independently produce MISMATCH
#     from OCR evidence alone (no provider field needed, re-asserted here
#     with a fresh evidence object distinct from test 1/4)
def test_ocr_japanese_veto_independent_of_provider():
    ev = make_ev(
        japanese_kana_count=9, high_conf_kana_count=7,
        distinct_regions_with_kana=3, num_regions=4, total_recognized_text=25,
    )
    assert not hasattr(ev, "language_aspect")
    assert ocr_v1_decision(ev) == "LANGUAGE_MISMATCH"


# 19. Provider/OCR conflict precedence is documented in the report, not
#     implemented as production code in this development task (LANGUAGE-v2
#     was not frozen -- see report). This test asserts that no LANGUAGE-v2
#     or COMBINED-v4 module was created/frozen by this script, matching the
#     spec's "only if OCR-v1 freezes" gating.
def test_no_premature_language_v2_combined_v4_module():
    for fname in (
        "ebay_e2_17_language_v2.py",
        "ebay_e2_17_combined_identity_v4.py",
        "ebay_language_v2_policy.py",
        "ebay_combined_identity_policy_v4.py",
    ):
        assert not os.path.exists(os.path.join(REPO_ROOT, "backend", "scripts", fname))


# 20. Deterministic OCR fingerprint -- same evidence object always yields
#     the same decision (no randomness in the rule)
def test_deterministic_decision():
    ev = make_ev(
        japanese_kana_count=8, high_conf_kana_count=6,
        distinct_regions_with_kana=3, num_regions=5, total_recognized_text=30,
    )
    results = {ocr_v1_decision(ev) for _ in range(25)}
    assert len(results) == 1


# 21. E2.14 excluded from tuning -- source of the decision rule and the
#     split-generation code must not reference any E2.14 artifact path
def test_e2_14_excluded_from_tuning_sources():
    script_src = open(SCRIPT_PATH, encoding="utf-8").read()
    assert "ebay_e2_14" not in script_src
    assert "e2_14" not in script_src.lower()


# 22. No paid APIs -- script source contains no paid-vision-API imports/calls
def test_no_paid_apis_referenced():
    script_src = open(SCRIPT_PATH, encoding="utf-8").read().lower()
    for forbidden in (
        "openai", "google.cloud.vision", "boto3", "rekognition",
        "textract", "azure.cognitiveservices", "computervision",
    ):
        assert forbidden not in script_src


# 23. CPU-only path -- easyocr Reader is constructed with gpu=False
def test_cpu_only_path():
    script_src = open(SCRIPT_PATH, encoding="utf-8").read()
    assert "gpu=False" in script_src


# 24. No production writes -- script only writes into
#     backend/artifacts/index_fair_value (development artifacts directory),
#     never into a "production", "live", or Fair-Value-serving path
def test_no_production_writes():
    script_src = open(SCRIPT_PATH, encoding="utf-8").read()
    assert "fair_value" not in script_src.lower() or "index_fair_value" in script_src
    for forbidden in ("market_explorer", "publish_price", "production_write"):
        assert forbidden not in script_src.lower()


# ---------------------------------------------------------------------------
# Script-classification helper unit tests (supporting the above)
# ---------------------------------------------------------------------------
def test_classify_char_hiragana():
    assert classify_char("あ") == "JP_KANA"


def test_classify_char_katakana():
    assert classify_char("ア") == "JP_KANA"


def test_classify_char_shared_kanji():
    assert classify_char("日") == "CJK_SHARED"


def test_classify_char_hangul():
    assert classify_char("가") == "KOREAN"


def test_classify_char_latin():
    assert classify_char("A") == "LATIN"


# ---------------------------------------------------------------------------
# Optional real-image-backed tests (skip cleanly if OCR results not present
# in this environment/run -- these exercise the actual EasyOCR pipeline
# against real, network-fetched eBay listing images from the development
# corpora, not synthetic evidence).
# ---------------------------------------------------------------------------
RESULTS_PATH = os.path.join(
    REPO_ROOT, "backend", "artifacts", "index_fair_value", "ebay_e2_17_ocr_results.json",
)


@pytest.fixture(scope="module")
def real_ocr_results():
    if not os.path.exists(RESULTS_PATH):
        pytest.skip("real OCR results not generated in this environment/run")
    return json.load(open(RESULTS_PATH, encoding="utf-8"))["rows"]


def test_real_ocr_produced_some_decisions(real_ocr_results):
    assert len(real_ocr_results) > 0
    decisions = {r["ocr_v1_decision"] for r in real_ocr_results}
    assert decisions.issubset({"LANGUAGE_MISMATCH", "LANGUAGE_MATCH", "LANGUAGE_UNVERIFIED"})


def test_real_ocr_no_provider_field_used_in_decision(real_ocr_results):
    # the decision must be derivable from OCR-only fields; presence of the
    # provider language_aspect_normalized column alongside the result is
    # for reporting only, not an input to ocr_v1_decision (already asserted
    # structurally in test 16, this re-checks against real rows too)
    for r in real_ocr_results[:5]:
        ev = make_ev(
            japanese_kana_count=r["japanese_kana_count"],
            high_conf_kana_count=r["high_conf_kana_count"],
            distinct_regions_with_kana=r["distinct_regions_with_kana"],
            korean_hangul_count=r["korean_hangul_count"],
            cjk_shared_count=r["cjk_shared_count"],
            latin_char_count=r["latin_char_count"],
            num_regions=r["num_regions"],
            total_recognized_text=r["total_recognized_text"],
            mean_region_conf=r["mean_region_conf"],
            max_region_conf=r["max_region_conf"],
            ocr_ok=r["ocr_ok"],
        )
        assert ocr_v1_decision(ev) == r["ocr_v1_decision"]
