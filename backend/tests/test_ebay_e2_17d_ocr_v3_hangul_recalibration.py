"""Unit tests for EBAY E2.17D OCR-v3 (Hangul-suppression recalibration).

Covers the 19 tests required by the task spec that are testable without a
live EasyOCR model download / network fetch in CI. Tests 13-16 (holdout
prediction artifact / fingerprint / membership / blank labels) read the
REAL sealed artifacts on disk once OCR-v3 has frozen and predictions have
been sealed for the 43-row E2.17C holdout; they are skipped (not faked) if
those artifacts do not exist yet.
"""
from __future__ import annotations

import csv
import hashlib
import importlib.util
import json
import sys
from pathlib import Path

import pytest

ROOT = Path(__file__).resolve().parents[2]
SCRIPTS = ROOT / "backend" / "scripts"
ARTIFACTS = ROOT / "backend" / "artifacts" / "index_fair_value"
if str(SCRIPTS) not in sys.path:
    sys.path.insert(0, str(SCRIPTS))

v3 = importlib.import_module("ebay_e2_17d_ocr_v3_hangul_recalibration")


def _ev(**kwargs):
    base = dict(row_id="synthetic", ocr_ok=True, num_regions=5, total_recognized_text=50)
    base.update(kwargs)
    return v3.OcrV3Evidence(**base)


# 1. Real Hangul evidence available (classification + wiring)
def test_hangul_classified_as_korean():
    assert v3.classify_char("가") == "KOREAN"


def test_hiragana_katakana_classified_as_jp_kana():
    assert v3.classify_char("あ") == "JP_KANA"
    assert v3.classify_char("ア") == "JP_KANA"


# 2. Weak Hangul hallucination does NOT suppress strong kana
def test_weak_spurious_hangul_does_not_suppress_strong_kana():
    """This is the core E2.17D regression: many LOW-confidence, single-char
    Hangul hits smeared across a real Japanese image (the ko-reader
    hallucination pattern found in Phase B) must not erase Japanese
    detection."""
    ev = _ev(
        high_conf_kana_count=10, distinct_regions_with_kana=4, japanese_kana_count=40,
        korean_hangul_count=25,  # raw count is HIGH (mirrors real saturation data)
        ko_distinct_high_conf_hangul_regions=0,  # but none are high-confidence multi-char regions
        ko_max_hangul_run_length=1,
    )
    decision, reason = v3.ocr_v3_decision(ev)
    assert decision == "JAPANESE_MISMATCH"
    assert reason == "strong_kana_weak_or_spurious_hangul"


# 3. Strong Korean evidence suppresses Japanese mismatch (real Korean row)
def test_strong_hangul_no_kana_suppresses_and_becomes_not_japanese_evidence():
    ev = _ev(
        high_conf_kana_count=0, distinct_regions_with_kana=0, japanese_kana_count=2,
        korean_hangul_count=70,
        ko_distinct_high_conf_hangul_regions=5, ko_max_hangul_run_length=4,
    )
    decision, reason = v3.ocr_v3_decision(ev)
    assert decision == "NOT_JAPANESE_EVIDENCE"
    assert reason == "strong_hangul_no_meaningful_kana"


# 4. Strong kana + strong Hangul => UNVERIFIED (genuine conflict)
def test_strong_kana_and_strong_hangul_conflict_is_unverified():
    ev = _ev(
        high_conf_kana_count=8, distinct_regions_with_kana=4, japanese_kana_count=40,
        korean_hangul_count=40,
        ko_distinct_high_conf_hangul_regions=3, ko_max_hangul_run_length=3,
    )
    decision, reason = v3.ocr_v3_decision(ev)
    assert decision == "UNVERIFIED"
    assert reason == "conflict_strong_kana_and_strong_hangul"


# 5. weak/weak => UNVERIFIED
def test_weak_kana_weak_hangul_is_unverified():
    ev = _ev(
        high_conf_kana_count=1, distinct_regions_with_kana=1, japanese_kana_count=2,
        korean_hangul_count=1, ko_distinct_high_conf_hangul_regions=0, ko_max_hangul_run_length=1,
    )
    decision, _ = v3.ocr_v3_decision(ev)
    assert decision == "UNVERIFIED"


# 6. English false-mismatch safety (Latin-dominant, no kana, no Hangul)
def test_english_latin_dominant_no_kana_no_hangul_is_not_japanese_evidence_never_mismatch():
    ev = _ev(
        num_regions=3, total_recognized_text=20,
        japanese_kana_count=0, cjk_shared_count=0, latin_char_count=12,
        mean_region_conf=0.6, korean_hangul_count=0,
    )
    decision, _ = v3.ocr_v3_decision(ev)
    assert decision != "JAPANESE_MISMATCH"


def test_english_with_spurious_low_conf_hangul_never_mismatch():
    """English row with a couple of stray low-confidence Hangul-looking
    hits (observed in dev data: ~38% of ENGLISH rows trip korean_hangul>=2)
    must never become JAPANESE_MISMATCH."""
    ev = _ev(
        num_regions=3, total_recognized_text=20,
        japanese_kana_count=0, cjk_shared_count=0, latin_char_count=12,
        mean_region_conf=0.6, korean_hangul_count=3,
        ko_distinct_high_conf_hangul_regions=0, ko_max_hangul_run_length=1,
    )
    decision, _ = v3.ocr_v3_decision(ev)
    assert decision != "JAPANESE_MISMATCH"


# 7. Korean false-Japanese safety (strong Hangul, weak stray kana noise)
def test_korean_row_with_stray_kana_noise_never_mismatch():
    ev = _ev(
        high_conf_kana_count=1, distinct_regions_with_kana=1, japanese_kana_count=3,
        korean_hangul_count=87, ko_distinct_high_conf_hangul_regions=6, ko_max_hangul_run_length=5,
    )
    decision, _ = v3.ocr_v3_decision(ev)
    assert decision != "JAPANESE_MISMATCH"


# 8. Chinese false-Japanese safety (shared CJK alone, no kana, no hangul)
def test_chinese_shared_cjk_alone_never_mismatch():
    ev = _ev(
        num_regions=10, total_recognized_text=60,
        cjk_shared_count=40, japanese_kana_count=0, high_conf_kana_count=0,
        korean_hangul_count=45, ko_distinct_high_conf_hangul_regions=3, ko_max_hangul_run_length=2,
    )
    decision, _ = v3.ocr_v3_decision(ev)
    assert decision != "JAPANESE_MISMATCH"


# 9. Japanese positive (strong kana, no real hangul)
def test_strong_kana_no_hangul_is_japanese_mismatch():
    ev = _ev(
        high_conf_kana_count=6, distinct_regions_with_kana=3, japanese_kana_count=10,
        korean_hangul_count=0,
    )
    decision, _ = v3.ocr_v3_decision(ev)
    assert decision == "JAPANESE_MISMATCH"


# 10. Japanese miss -> UNVERIFIED, never NOT_JAPANESE_EVIDENCE proof
def test_weak_japanese_evidence_misses_to_unverified_not_not_japanese():
    ev = _ev(
        high_conf_kana_count=1, distinct_regions_with_kana=1, japanese_kana_count=3,
        korean_hangul_count=0,
    )
    decision, _ = v3.ocr_v3_decision(ev)
    assert decision == "UNVERIFIED"


# 11. Determinism
def test_decision_is_deterministic():
    ev = _ev(high_conf_kana_count=6, distinct_regions_with_kana=3, japanese_kana_count=10)
    results = {v3.ocr_v3_decision(ev) for _ in range(10)}
    assert len(results) == 1


# 12. Freeze fingerprint computable/stable
def test_source_fingerprint_stable():
    fp1 = v3.compute_source_fingerprint()
    fp2 = v3.compute_source_fingerprint()
    assert fp1 == fp2
    assert len(fp1) == 64


# 13-16: real sealed holdout artifacts (skip if not yet produced)
HOLDOUT_PRED_PATH = ARTIFACTS / "ebay_e2_17d_ocr_v3_holdout_predictions.json"
HOLDOUT_QUEUE_PATH = ARTIFACTS / "ebay_e2_17c_small_japanese_holdout_queue.csv"


def _require_holdout_predictions():
    if not HOLDOUT_PRED_PATH.exists():
        pytest.skip("OCR-v3 not frozen / holdout predictions not sealed yet")
    return json.loads(HOLDOUT_PRED_PATH.read_text(encoding="utf-8"))


def test_holdout_prediction_artifact_written_after_freeze():
    data = _require_holdout_predictions()
    assert data.get("ocr_v3_freeze_fingerprint")
    assert len(data["rows"]) == 43


def test_holdout_prediction_fingerprint_matches_recomputation():
    data = _require_holdout_predictions()
    recomputed = hashlib.sha256(
        "|".join(
            f"{r['row_id']}:{r['ocr_v3_decision']}" for r in sorted(data["rows"], key=lambda r: r["row_id"])
        ).encode()
    ).hexdigest()
    assert data["prediction_fingerprint"] == recomputed


def test_holdout_membership_unchanged():
    data = _require_holdout_predictions()
    rows = list(csv.DictReader(HOLDOUT_QUEUE_PATH.open(encoding="utf-8")))
    assert len(rows) == 43
    queue_ids = {r["row_id"] for r in rows}
    pred_ids = {r["row_id"] for r in data["rows"]}
    assert queue_ids == pred_ids


def test_holdout_labels_still_blank():
    rows = list(csv.DictReader(HOLDOUT_QUEUE_PATH.open(encoding="utf-8")))
    manifest = json.loads((HOLDOUT_QUEUE_PATH.parent / "ebay_e2_17c_small_japanese_holdout_manifest.json").read_text(encoding="utf-8"))
    if manifest.get("labels_frozen"):
        assert all(r.get("human_truth_label") in {"JAPANESE", "NOT_JAPANESE", "UNCERTAIN"} for r in rows)
    else:
        assert all(not r.get("human_truth_label") for r in rows)


# 17. OCR output hidden from reviewer (reuse the E2.17C blinding contract)
def test_ocr_output_hidden_from_reviewer():
    server = importlib.import_module("ebay_e2_17c_holdout_review_server")
    forbidden_leak_terms = {
        "ocr_v3", "japanese_kana_count", "korean_hangul_count", "high_conf_kana_count",
        "ko_distinct_high_conf_hangul_regions", "mean_region_conf", "development_stratum",
    }
    assert server.REVIEWER_VISIBLE_COLUMNS.isdisjoint(forbidden_leak_terms)
    # Freeze verifies sealed prediction membership, but the reviewer page
    # still renders only the explicit reviewer-visible fields.
    import inspect
    assert "PREDICTIONS_PATH" not in inspect.getsource(server.page)


# 18. No E2.14 tuning -- OCR-v3 module never references E2.14 artifacts
def test_no_e2_14_tuning_reference():
    src = (SCRIPTS / "ebay_e2_17d_ocr_v3_hangul_recalibration.py").read_text(encoding="utf-8")
    assert "e2_14" not in src.lower()
    assert "gold_final_blind" not in src.lower()


# 19. No production writes -- module never imports production DB/write helpers
def test_no_production_writes():
    src = (SCRIPTS / "ebay_e2_17d_ocr_v3_hangul_recalibration.py").read_text(encoding="utf-8")
    for forbidden in ("supabase", "psycopg", "UPDATE fair_value", "production_authority = True",
                       "production_authority=True"):
        assert forbidden not in src
    assert '"production_authority": False' in src


def test_ocr_v3_config_constants_match_expected_architecture():
    assert v3.READER_JA_CONFIG == ["ja", "en"]
    assert v3.READER_KO_CONFIG == ["ko", "en"]
    assert v3.MERGE_LOGIC_VERSION


def test_easyocr_rejects_combined_ja_ko_en_reader():
    easyocr = pytest.importorskip("easyocr")
    with pytest.raises(ValueError):
        easyocr.Reader(["ja", "ko", "en"], gpu=False, verbose=False)
