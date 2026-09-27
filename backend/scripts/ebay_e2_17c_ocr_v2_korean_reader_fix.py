"""
EBAY E2.17C -- Local OCR-v2 (Korean-reader fix) Japanese/Korean/Chinese
physical-card language evidence.

DEVELOPMENT RESEARCH ONLY. Does not certify, does not write to production,
does not use paid OCR APIs, does not touch Fair Value / Explorer / prices.

Background (defect fixed here):
  OCR-v1 (backend/scripts/ebay_e2_17_ocr_v1_japanese_language_feasibility.py)
  built its single EasyOCR Reader as Reader(["ja", "en"]). EasyOCR 1.7.2
  raises ValueError if any language incompatible with the Japanese
  recognition-model grouping is added to that same Reader -- confirmed
  empirically for this task:

      >>> easyocr.Reader(["ja", "ko", "en"], gpu=False)
      ValueError: Japanese is only compatible with English,
      try lang_list=["ja","en"]

  Because OCR-v1 never actually ran a Korean-capable reader,
  `korean_hangul_count` in OCR-v1 was STRUCTURALLY always 0 -- the "Korean
  hard-negative guard" in ocr_v1_decision() could never fire from real
  Hangul evidence. (See EBAY_E2_17B_AUTHORITATIVE_JAPANESE_OCR_VALIDATION.md.)

OCR-v2 fix (and ONLY this fix, per the E2.17C change boundary):
  Run TWO separate EasyOCR Reader instances against the same image:
    - reader_ja = easyocr.Reader(["ja", "en"], gpu=False)   (unchanged from v1)
    - reader_ko = easyocr.Reader(["ko", "en"], gpu=False)   (NEW)
  Then deterministically UNION the per-character script evidence from both
  readers' recognized text:
    - japanese_kana_count / high_conf_kana_count / distinct_regions_with_kana
      / cjk_shared_count / latin_char_count are computed from reader_ja's
      output only (unchanged from v1 -- these signals do not need reader_ko).
    - korean_hangul_count is computed from reader_ko's output (this is the
      new, real signal; NOT the artificial variable that was always 0).
  This is the "smallest deterministic local architecture" called for in the
  task spec: two single-purpose readers, no shared-vocabulary hack, no
  invented EasyOCR configuration.

STRICT CHANGE BOUNDARY (per task spec): OCR-v2 changes ONLY the reader
architecture needed to make Hangul evidence real. The Japanese kana
threshold, OCR confidence threshold, Han/Kanji rule, and LANGUAGE_MISMATCH
decision function (ocr_v1_decision, renamed ocr_v2_decision but byte-for-
byte identical in its logic) are UNCHANGED from OCR-v1.

Deterministic: same image bytes + same easyocr version + same two reader
configs + same rule -> same OCR-v2 output. No provider Language aspect is
read by the classifier.
"""
from __future__ import annotations

import hashlib
import json
import os
import time
import unicodedata
from dataclasses import dataclass, field
from typing import Optional

# ---------------------------------------------------------------------------
# Unicode script ranges -- IDENTICAL to OCR-v1. Not retuned.
# ---------------------------------------------------------------------------
HIRAGANA = (0x3040, 0x309F)
KATAKANA = (0x30A0, 0x30FF)
CJK_UNIFIED = (0x4E00, 0x9FFF)  # shared Kanji/Hanzi -- NOT Japanese-exclusive
LATIN_BASIC = (0x0041, 0x007A)
HANGUL = (0xAC00, 0xD7A3)  # Korean

OCR_V2_SOURCE_VERSION = "ebay_e2_17c_ocr_v2_korean_reader_fix_v1"
EASYOCR_VERSION = "1.7.2"
READER_JA_CONFIG = ["ja", "en"]
READER_KO_CONFIG = ["ko", "en"]
MERGE_LOGIC_VERSION = "ocr_v2_merge_v1_union_disjoint_readers"


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


@dataclass
class OcrV2Evidence:
    row_id: str
    ocr_ok: bool = False
    error: Optional[str] = None
    # from reader_ja (unchanged semantics vs v1)
    num_regions: int = 0
    total_recognized_text: int = 0
    japanese_kana_count: int = 0
    cjk_shared_count: int = 0
    latin_char_count: int = 0
    distinct_regions_with_kana: int = 0
    high_conf_kana_count: int = 0
    max_region_conf: float = 0.0
    mean_region_conf: float = 0.0
    raw_regions_ja: list = field(default_factory=list)
    # from reader_ko (NEW -- real Hangul evidence)
    korean_hangul_count: int = 0
    ko_num_regions: int = 0
    ko_ocr_ok: bool = False
    ko_error: Optional[str] = None
    raw_regions_ko: list = field(default_factory=list)


def _run_reader(reader, image_path: str):
    """Returns (results, error) where results is EasyOCR readtext() output
    or None on failure."""
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


def run_ocr_v2(reader_ja, reader_ko, image_path: str, row_id: str) -> OcrV2Evidence:
    ev = OcrV2Evidence(row_id=row_id)

    # --- Japanese+English reader: kana / cjk_shared / latin (unchanged v1 logic) ---
    results_ja, err_ja = _run_reader(reader_ja, image_path)
    if results_ja is None:
        ev.error = err_ja
        return ev
    ev.ocr_ok = True
    ev.num_regions = len(results_ja)
    confs = []
    for (_bbox, text, conf) in results_ja:
        confs.append(conf)
        ev.raw_regions_ja.append((text, conf))
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

    # --- Korean+English reader: real Hangul evidence (NEW in v2) ---
    results_ko, err_ko = _run_reader(reader_ko, image_path)
    if results_ko is None:
        ev.ko_ocr_ok = False
        ev.ko_error = err_ko
        # Korean reader failure does not invalidate the Japanese-side
        # evidence already computed; korean_hangul_count stays at 0
        # (conservative: absence of evidence, not evidence of absence,
        # but this cannot cause a false JAPANESE call because the Hangul
        # guard only ever SUPPRESSES a mismatch call, never causes one).
        return ev
    ev.ko_ocr_ok = True
    ev.ko_num_regions = len(results_ko)
    for (_bbox, text, _conf) in results_ko:
        ev.raw_regions_ko.append((text, _conf))
        for ch in text:
            if classify_char(ch) == "KOREAN":
                ev.korean_hangul_count += 1

    return ev


# ---------------------------------------------------------------------------
# OCR-v2 decision rule -- IDENTICAL LOGIC to OCR-v1's ocr_v1_decision().
# The only substantive change is that ev.korean_hangul_count is now a real,
# independently-measured signal rather than a structurally-zero field.
# ---------------------------------------------------------------------------
def ocr_v2_decision(ev: OcrV2Evidence) -> str:
    if not ev.ocr_ok:
        return "LANGUAGE_UNVERIFIED"
    if ev.num_regions == 0 or ev.total_recognized_text < 3:
        return "LANGUAGE_UNVERIFIED"

    # Korean hard-negative guard -- now backed by real Hangul evidence.
    if ev.korean_hangul_count >= 2:
        return "LANGUAGE_UNVERIFIED"

    strong_japanese = (
        ev.high_conf_kana_count >= 4
        and ev.distinct_regions_with_kana >= 2
    ) or (
        ev.high_conf_kana_count >= 6
    )
    if strong_japanese:
        return "LANGUAGE_MISMATCH"

    if (
        ev.japanese_kana_count == 0
        and ev.cjk_shared_count == 0
        and ev.latin_char_count >= 8
        and ev.mean_region_conf >= 0.35
        and ev.num_regions >= 2
    ):
        return "LANGUAGE_MATCH"

    return "LANGUAGE_UNVERIFIED"


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


def main():
    repo_root = os.path.abspath(os.path.join(os.path.dirname(__file__), "..", ".."))
    manifest_path = os.environ.get("E217C_MANIFEST_PATH")
    out_path = os.environ.get(
        "E217C_OUT_PATH",
        os.path.join(repo_root, "backend", "artifacts", "index_fair_value",
                      "ebay_e2_17c_ocr_v2_results.json"),
    )
    with open(manifest_path, "r", encoding="utf-8") as f:
        manifest = json.load(f)

    reader_ja, reader_ko, load_times = build_readers()

    out_rows = []
    infer_times = []
    for i, row in enumerate(manifest):
        if not row.get("fetch_ok") or not row.get("local_image_path"):
            ev = OcrV2Evidence(row_id=row["row_id"], ocr_ok=False, error="fetch_failed")
        else:
            t1 = time.time()
            ev = run_ocr_v2(reader_ja, reader_ko, row["local_image_path"], row["row_id"])
            infer_times.append(time.time() - t1)
        decision = ocr_v2_decision(ev)
        out_rows.append({
            "row_id": row["row_id"],
            "source": row.get("source"),
            "human_truth_label": row.get("human_truth_label"),
            "split": row.get("split"),
            "ocr_ok": ev.ocr_ok,
            "error": ev.error,
            "num_regions": ev.num_regions,
            "total_recognized_text": ev.total_recognized_text,
            "japanese_kana_count": ev.japanese_kana_count,
            "cjk_shared_count": ev.cjk_shared_count,
            "korean_hangul_count": ev.korean_hangul_count,
            "latin_char_count": ev.latin_char_count,
            "distinct_regions_with_kana": ev.distinct_regions_with_kana,
            "high_conf_kana_count": ev.high_conf_kana_count,
            "mean_region_conf": round(ev.mean_region_conf, 4),
            "max_region_conf": round(ev.max_region_conf, 4),
            "ko_ocr_ok": ev.ko_ocr_ok,
            "ko_error": ev.ko_error,
            "ko_num_regions": ev.ko_num_regions,
            "ocr_v2_decision": decision,
        })
        print(f"[{i+1}/{len(manifest)}] {row['row_id']} truth={row.get('human_truth_label')} "
              f"-> {decision} (kana={ev.japanese_kana_count}, cjk={ev.cjk_shared_count}, "
              f"hangul={ev.korean_hangul_count}, latin={ev.latin_char_count}, "
              f"ko_ok={ev.ko_ocr_ok})")

    result = {
        "ocr_v2_source_version": OCR_V2_SOURCE_VERSION,
        "ocr_v2_source_fingerprint_sha256": compute_source_fingerprint(),
        "easyocr_version": EASYOCR_VERSION,
        "reader_ja_config": READER_JA_CONFIG,
        "reader_ko_config": READER_KO_CONFIG,
        "merge_logic_version": MERGE_LOGIC_VERSION,
        "ja_load_seconds": load_times["ja_load_seconds"],
        "ko_load_seconds": load_times["ko_load_seconds"],
        "mean_inference_seconds": sum(infer_times) / len(infer_times) if infer_times else None,
        "n_images_ocr_attempted": len(infer_times),
        "production_authority": False,
        "rows": out_rows,
    }
    with open(out_path, "w", encoding="utf-8") as f:
        json.dump(result, f, indent=2)
    print("Wrote", out_path)
    print("ja_load_seconds:", load_times["ja_load_seconds"])
    print("ko_load_seconds:", load_times["ko_load_seconds"])
    if infer_times:
        print("Mean inference seconds (per row, both readers):",
              sum(infer_times) / len(infer_times))


if __name__ == "__main__":
    main()
