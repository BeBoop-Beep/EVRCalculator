"""
EBAY E2.17D -- OCR-v3 Hangul-suppression recalibration.

DEVELOPMENT RESEARCH ONLY. Does not certify, does not write to production,
does not touch Fair Value / Explorer / prices / LANGUAGE-v1 / COMBINED-v3 /
D3-v5 / IMAGE-v2 / CAPTURE-ALLOCATION-v2.

Background: OCR-v2 (backend/scripts/ebay_e2_17c_ocr_v2_korean_reader_fix.py)
correctly runs two disjoint EasyOCR readers (reader_ja=["ja","en"],
reader_ko=["ko","en"]) but its inherited `korean_hangul_count >= 2`
suppression guard was calibrated against a field that was structurally
always 0 in OCR-v1. Against a REAL Korean reader, that guard saturates:
100% of NON_ENGLISH dev rows and 38% of ENGLISH dev rows trip it, and
Japanese-mismatch recall on the 16 frozen JAPANESE E2.17A rows collapsed
from 7/16 (v1) to 0/16 (v2).

OCR-v3 keeps the exact same two-reader architecture (byte-identical
reader configs) and the exact same JA-side signal extraction as v1/v2.
The ONLY change is (a) richer per-region KO-reader evidence capture
(needed to root-cause and fix the guard) and (b) a recalibrated
Japanese/Korean script-conflict decision rule.

Richer KO-side evidence captured per row (new in v3, all derived purely
from reader_ko's own per-region (bbox, text, conf) tuples -- no new
provider signal, no listing text):
  - ko_num_regions_total: total regions reader_ko returned (any script)
  - ko_regions_with_hangul: regions containing >=1 Hangul character
  - ko_high_conf_hangul_count: Hangul chars in regions with conf >= 0.5
  - ko_max_hangul_region_conf / ko_mean_hangul_region_conf: confidence
    stats over the regions that contain Hangul
  - ko_max_hangul_run_length: longest contiguous run of Hangul chars in
    any single recognized-text string (distinguishes real Hangul words
    from isolated 1-character noise hits)
  - ko_distinct_high_conf_hangul_regions: count of DISTINCT regions with
    conf >= 0.5 AND >= 1 Hangul char (the feature used by the new rule)
"""
from __future__ import annotations

import hashlib
import json
import os
import time
from dataclasses import dataclass, field
from typing import Optional

HIRAGANA = (0x3040, 0x309F)
KATAKANA = (0x30A0, 0x30FF)
CJK_UNIFIED = (0x4E00, 0x9FFF)
HANGUL = (0xAC00, 0xD7A3)

OCR_V3_SOURCE_VERSION = "ebay_e2_17d_ocr_v3_hangul_recalibration_v1"
EASYOCR_VERSION = "1.7.2"
READER_JA_CONFIG = ["ja", "en"]
READER_KO_CONFIG = ["ko", "en"]
MERGE_LOGIC_VERSION = "ocr_v3_merge_v1_union_disjoint_readers_rich_ko_evidence"
HIGH_CONF_THRESHOLD = 0.5


def _in_range(ch: str, rng) -> bool:
    return rng[0] <= ord(ch) <= rng[1]


def classify_char(ch: str) -> str:
    if _in_range(ch, HIRAGANA) or _in_range(ch, KATAKANA):
        return "JP_KANA"
    if _in_range(ch, HANGUL):
        return "KOREAN"
    if _in_range(ch, CJK_UNIFIED):
        return "CJK_SHARED"
    if ch.isascii() and ch.isalpha():
        return "LATIN"
    return "OTHER"


def _max_hangul_run(text: str) -> int:
    best = cur = 0
    for ch in text:
        if classify_char(ch) == "KOREAN":
            cur += 1
            best = max(best, cur)
        else:
            cur = 0
    return best


@dataclass
class OcrV3Evidence:
    row_id: str
    ocr_ok: bool = False
    error: Optional[str] = None
    # JA-side (unchanged extraction logic from v1/v2)
    num_regions: int = 0
    total_recognized_text: int = 0
    japanese_kana_count: int = 0
    cjk_shared_count: int = 0
    latin_char_count: int = 0
    distinct_regions_with_kana: int = 0
    high_conf_kana_count: int = 0
    max_region_conf: float = 0.0
    mean_region_conf: float = 0.0
    # KO-side basic (same field names as v2, for continuity)
    korean_hangul_count: int = 0
    ko_num_regions: int = 0
    ko_ocr_ok: bool = False
    ko_error: Optional[str] = None
    # KO-side rich evidence (NEW in v3)
    ko_regions_with_hangul: int = 0
    ko_high_conf_hangul_count: int = 0
    ko_max_hangul_region_conf: float = 0.0
    ko_mean_hangul_region_conf: float = 0.0
    ko_max_hangul_run_length: int = 0
    ko_distinct_high_conf_hangul_regions: int = 0
    raw_ko_regions_sample: list = field(default_factory=list)  # (text, conf, hangul_count) top 10


def _run_reader(reader, image_path: str):
    try:
        import cv2
        img = cv2.imread(image_path)
        if img is None:
            return None, "cv2_decode_failed"
        h, w = img.shape[:2]
        if h < 50 or w < 50:
            return None, "image_too_small"
        results = reader.readtext(image_path)
        return results, None
    except Exception as e:  # noqa: BLE001
        return None, f"ocr_exception:{type(e).__name__}:{e}"


def run_ocr_v3(reader_ja, reader_ko, image_path: str, row_id: str) -> OcrV3Evidence:
    ev = OcrV3Evidence(row_id=row_id)

    results_ja, err_ja = _run_reader(reader_ja, image_path)
    if results_ja is None:
        ev.error = err_ja
        return ev
    ev.ocr_ok = True
    ev.num_regions = len(results_ja)
    confs = []
    for (_bbox, text, conf) in results_ja:
        confs.append(conf)
        ev.total_recognized_text += len(text)
        region_kana = 0
        for ch in text:
            cls = classify_char(ch)
            if cls == "JP_KANA":
                ev.japanese_kana_count += 1
                region_kana += 1
                if conf >= 0.5:
                    ev.high_conf_kana_count += 1
            elif cls == "CJK_SHARED":
                ev.cjk_shared_count += 1
            elif cls == "LATIN":
                ev.latin_char_count += 1
        if region_kana > 0:
            ev.distinct_regions_with_kana += 1
    if confs:
        ev.max_region_conf = max(confs)
        ev.mean_region_conf = sum(confs) / len(confs)

    results_ko, err_ko = _run_reader(reader_ko, image_path)
    if results_ko is None:
        ev.ko_ocr_ok = False
        ev.ko_error = err_ko
        return ev
    ev.ko_ocr_ok = True
    ev.ko_num_regions = len(results_ko)
    hangul_region_confs = []
    for (_bbox, text, conf) in results_ko:
        region_hangul = sum(1 for ch in text if classify_char(ch) == "KOREAN")
        if region_hangul > 0:
            ev.korean_hangul_count += region_hangul
            ev.ko_regions_with_hangul += 1
            hangul_region_confs.append(conf)
            run_len = _max_hangul_run(text)
            ev.ko_max_hangul_run_length = max(ev.ko_max_hangul_run_length, run_len)
            if conf >= HIGH_CONF_THRESHOLD:
                ev.ko_high_conf_hangul_count += region_hangul
                ev.ko_distinct_high_conf_hangul_regions += 1
            if len(ev.raw_ko_regions_sample) < 10:
                ev.raw_ko_regions_sample.append((text, round(conf, 4), region_hangul))
    if hangul_region_confs:
        ev.ko_max_hangul_region_conf = max(hangul_region_confs)
        ev.ko_mean_hangul_region_conf = sum(hangul_region_confs) / len(hangul_region_confs)

    return ev


# ---------------------------------------------------------------------------
# OCR-v3 decision rule.
# ---------------------------------------------------------------------------
STRONG_KANA_A_HI = 4
STRONG_KANA_A_REGIONS = 2
STRONG_KANA_B_HI = 6

STRONG_HANGUL_DISTINCT_REGIONS = 2
STRONG_HANGUL_RUN_LENGTH = 2


def _strong_kana(ev: OcrV3Evidence) -> bool:
    return (
        (ev.high_conf_kana_count >= STRONG_KANA_A_HI and ev.distinct_regions_with_kana >= STRONG_KANA_A_REGIONS)
        or (ev.high_conf_kana_count >= STRONG_KANA_B_HI)
    )


def _strong_hangul(ev: OcrV3Evidence) -> bool:
    """Strong Hangul evidence = multiple DISTINCT high-confidence regions
    each containing a multi-character Hangul run (>=2 contiguous Hangul
    chars). A single isolated high-confidence Hangul glyph, or many
    low-confidence Hangul hits smeared across kana/kanji glyphs the ko
    reader has no model for, does NOT count as strong."""
    return (
        ev.ko_distinct_high_conf_hangul_regions >= STRONG_HANGUL_DISTINCT_REGIONS
        and ev.ko_max_hangul_run_length >= STRONG_HANGUL_RUN_LENGTH
    )


def ocr_v3_decision(ev: OcrV3Evidence) -> tuple[str, str]:
    """Returns (decision, reason_code). decision in
    {JAPANESE_MISMATCH, NOT_JAPANESE_EVIDENCE, UNVERIFIED}."""
    if not ev.ocr_ok:
        return "UNVERIFIED", "ja_reader_failed"
    if ev.num_regions == 0 or ev.total_recognized_text < 3:
        return "UNVERIFIED", "insufficient_text"

    strong_kana = _strong_kana(ev)
    strong_hangul = _strong_hangul(ev)

    if strong_kana and strong_hangul:
        return "UNVERIFIED", "conflict_strong_kana_and_strong_hangul"
    if strong_kana and not strong_hangul:
        return "JAPANESE_MISMATCH", "strong_kana_weak_or_spurious_hangul"
    if strong_hangul and not strong_kana:
        return "NOT_JAPANESE_EVIDENCE", "strong_hangul_no_meaningful_kana"

    # weak/weak -- fall through to the (unchanged from v1/v2) English-match
    # sanity check, else UNVERIFIED.
    if (
        ev.japanese_kana_count == 0
        and ev.cjk_shared_count == 0
        and ev.latin_char_count >= 8
        and ev.mean_region_conf >= 0.35
        and ev.num_regions >= 2
    ):
        return "NOT_JAPANESE_EVIDENCE", "latin_dominant_no_kana_no_hangul"

    return "UNVERIFIED", "weak_weak_no_conflict"


def compute_source_fingerprint() -> str:
    with open(__file__, "rb") as f:
        return hashlib.sha256(f.read()).hexdigest()


def build_readers():
    import easyocr
    t0 = time.time()
    reader_ja = easyocr.Reader(READER_JA_CONFIG, gpu=False, verbose=False)
    t1 = time.time()
    reader_ko = easyocr.Reader(READER_KO_CONFIG, gpu=False, verbose=False)
    t2 = time.time()
    return reader_ja, reader_ko, {"ja_load_seconds": t1 - t0, "ko_load_seconds": t2 - t1}


def ev_to_dict(row, ev: OcrV3Evidence, decision: str, reason: str) -> dict:
    return {
        "row_id": row["row_id"],
        "source": row.get("source"),
        "human_truth_label": row.get("human_truth_label"),
        "specific_language_truth": row.get("specific_language_truth"),
        "ocr_ok": ev.ocr_ok,
        "error": ev.error,
        "num_regions": ev.num_regions,
        "total_recognized_text": ev.total_recognized_text,
        "japanese_kana_count": ev.japanese_kana_count,
        "cjk_shared_count": ev.cjk_shared_count,
        "latin_char_count": ev.latin_char_count,
        "distinct_regions_with_kana": ev.distinct_regions_with_kana,
        "high_conf_kana_count": ev.high_conf_kana_count,
        "mean_region_conf": round(ev.mean_region_conf, 4),
        "max_region_conf": round(ev.max_region_conf, 4),
        "ko_ocr_ok": ev.ko_ocr_ok,
        "ko_error": ev.ko_error,
        "ko_num_regions": ev.ko_num_regions,
        "korean_hangul_count": ev.korean_hangul_count,
        "ko_regions_with_hangul": ev.ko_regions_with_hangul,
        "ko_high_conf_hangul_count": ev.ko_high_conf_hangul_count,
        "ko_max_hangul_region_conf": round(ev.ko_max_hangul_region_conf, 4),
        "ko_mean_hangul_region_conf": round(ev.ko_mean_hangul_region_conf, 4),
        "ko_max_hangul_run_length": ev.ko_max_hangul_run_length,
        "ko_distinct_high_conf_hangul_regions": ev.ko_distinct_high_conf_hangul_regions,
        "raw_ko_regions_sample": ev.raw_ko_regions_sample,
        "ocr_v3_decision": decision,
        "ocr_v3_reason_code": reason,
    }


def main():
    repo_root = os.path.abspath(os.path.join(os.path.dirname(__file__), "..", ".."))
    manifest_path = os.environ["E217D_MANIFEST_PATH"]
    images_dir = os.environ["E217D_IMAGES_DIR"]
    out_path = os.environ.get(
        "E217D_OUT_PATH",
        os.path.join(repo_root, "backend", "artifacts", "index_fair_value",
                      "ebay_e2_17d_ocr_v3_development_results.json"),
    )
    with open(manifest_path, "r", encoding="utf-8") as f:
        manifest = json.load(f)

    reader_ja, reader_ko, load_times = build_readers()

    out_rows = []
    infer_times = []
    for i, row in enumerate(manifest):
        img_path = os.path.join(images_dir, row["row_id"].replace("/", "_") + ".jpg")
        if not os.path.exists(img_path):
            ev = OcrV3Evidence(row_id=row["row_id"], ocr_ok=False, error="image_not_fetched")
        else:
            t1 = time.time()
            ev = run_ocr_v3(reader_ja, reader_ko, img_path, row["row_id"])
            infer_times.append(time.time() - t1)
        decision, reason = ocr_v3_decision(ev)
        out_rows.append(ev_to_dict(row, ev, decision, reason))
        print(f"[{i+1}/{len(manifest)}] {row['row_id']} truth={row.get('human_truth_label')}/"
              f"{row.get('specific_language_truth')} -> {decision} ({reason}) "
              f"kana_hi={ev.high_conf_kana_count} hangul_hi_regions={ev.ko_distinct_high_conf_hangul_regions} "
              f"hangul_run={ev.ko_max_hangul_run_length}")

    result = {
        "ocr_v3_source_version": OCR_V3_SOURCE_VERSION,
        "ocr_v3_source_fingerprint_sha256": compute_source_fingerprint(),
        "easyocr_version": EASYOCR_VERSION,
        "reader_ja_config": READER_JA_CONFIG,
        "reader_ko_config": READER_KO_CONFIG,
        "merge_logic_version": MERGE_LOGIC_VERSION,
        "ja_load_seconds": load_times["ja_load_seconds"],
        "ko_load_seconds": load_times["ko_load_seconds"],
        "mean_inference_seconds": sum(infer_times) / len(infer_times) if infer_times else None,
        "n_images_ocr_attempted": len(infer_times),
        "n_rows_total": len(manifest),
        "production_authority": False,
        "rows": out_rows,
    }
    with open(out_path, "w", encoding="utf-8") as f:
        json.dump(result, f, indent=2)
    print("Wrote", out_path)


if __name__ == "__main__":
    main()
