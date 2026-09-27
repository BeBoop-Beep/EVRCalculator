"""
EBAY E2.17 -- Local OCR-v1 Japanese physical-card language feasibility.

DEVELOPMENT RESEARCH ONLY. Does not certify, does not write to production,
does not use paid OCR APIs, does not touch Fair Value / Explorer / prices.

This script:
  1. Loads the E2.16 (200 rows) + E2.16B (150 rows) development corpora.
  2. Builds a canonical-card-id-grouped DESIGN(~70%)/HELDOUT(~30%) split
     (see ebay_e2_17_combined_corpus_split.json, already generated).
  3. Runs local EasyOCR (ja+en) against a real, network-fetched sample of
     the corpus images.
  4. Computes conservative CJK/Japanese-script evidence signals per image
     (character counts, distinct region counts, confidence) WITHOUT doing
     full-card transcription.
  5. Derives a fixed conservative rule on the DESIGN split only, applies it
     unmodified to the HELDOUT split, and reports the confusion outcome.

Deterministic: same image bytes + same easyocr version + same rule -> same
OCR_V1 output. No provider Language aspect is read by the classifier.
"""
from __future__ import annotations

import json
import os
import re
import time
import unicodedata
from dataclasses import dataclass, field
from typing import Optional

# ---------------------------------------------------------------------------
# Unicode script ranges (conservative; Japanese-specific scripts only)
# ---------------------------------------------------------------------------
HIRAGANA = (0x3040, 0x309F)
KATAKANA = (0x30A0, 0x30FF)
CJK_UNIFIED = (0x4E00, 0x9FFF)  # shared Kanji/Hanzi -- NOT Japanese-exclusive
LATIN_BASIC = (0x0041, 0x007A)
HANGUL = (0xAC00, 0xD7A3)  # Korean -- used as a hard-negative signal


def _in_range(ch: str, rng) -> bool:
    return rng[0] <= ord(ch) <= rng[1]


def classify_char(ch: str) -> str:
    if _in_range(ch, HIRAGANA) or _in_range(ch, KATAKANA):
        return "JP_KANA"  # unambiguous Japanese-only script
    if _in_range(ch, HANGUL):
        return "KOREAN"
    if _in_range(ch, CJK_UNIFIED):
        return "CJK_SHARED"  # Japanese Kanji OR Chinese Hanzi -- ambiguous alone
    if ch.isascii() and ch.isalpha():
        return "LATIN"
    return "OTHER"


@dataclass
class OcrEvidence:
    row_id: str
    ocr_ok: bool = False
    error: Optional[str] = None
    num_regions: int = 0
    total_recognized_text: int = 0
    japanese_kana_count: int = 0          # unambiguous hiragana/katakana chars
    cjk_shared_count: int = 0             # shared kanji/hanzi chars (ambiguous)
    korean_hangul_count: int = 0
    latin_char_count: int = 0
    distinct_regions_with_kana: int = 0
    high_conf_kana_count: int = 0         # kana chars in regions with conf >= 0.5
    max_region_conf: float = 0.0
    mean_region_conf: float = 0.0
    raw_regions: list = field(default_factory=list)  # (text, conf) tuples


def run_ocr(reader, image_path: str, row_id: str) -> OcrEvidence:
    ev = OcrEvidence(row_id=row_id)
    try:
        import cv2
        img = cv2.imread(image_path)
        if img is None:
            ev.error = "cv2_decode_failed"
            return ev
        h, w = img.shape[:2]
        if h < 50 or w < 50:
            ev.error = "image_too_small"
            return ev
        results = reader.readtext(image_path)
    except Exception as e:  # noqa: BLE001
        ev.error = f"ocr_exception:{type(e).__name__}:{e}"
        return ev

    ev.ocr_ok = True
    ev.num_regions = len(results)
    confs = []
    for (_bbox, text, conf) in results:
        confs.append(conf)
        ev.raw_regions.append((text, conf))
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
            elif cls == "KOREAN":
                ev.korean_hangul_count += 1
            elif cls == "LATIN":
                ev.latin_char_count += 1
        if region_kana > 0:
            ev.distinct_regions_with_kana += 1
    if confs:
        ev.max_region_conf = max(confs)
        ev.mean_region_conf = sum(confs) / len(confs)
    return ev


# ---------------------------------------------------------------------------
# OCR-v1 decision rule (fixed on DESIGN split; NOT re-tuned on HELDOUT)
# ---------------------------------------------------------------------------
def ocr_v1_decision(ev: OcrEvidence) -> str:
    """Return one of LANGUAGE_MISMATCH / LANGUAGE_MATCH / LANGUAGE_UNVERIFIED.

    Conservative-by-construction: requires MULTIPLE unambiguous kana
    characters, spread across >=2 recognized regions (or one region with
    >=4 kana chars), at reasonable OCR confidence, before declaring
    LANGUAGE_MISMATCH. A single stray glyph never triggers mismatch.
    Hangul (Korean) presence suppresses a Japanese call (hard-negative
    guard) rather than letting shared CJK ambiguity mislabel Korean cards.
    """
    if not ev.ocr_ok:
        return "LANGUAGE_UNVERIFIED"
    if ev.num_regions == 0 or ev.total_recognized_text < 3:
        return "LANGUAGE_UNVERIFIED"

    # Korean hard-negative guard: real Hangul presence means this is not
    # being called Japanese by this rule, regardless of any CJK ambiguity.
    if ev.korean_hangul_count >= 2:
        return "LANGUAGE_UNVERIFIED"

    strong_japanese = (
        ev.high_conf_kana_count >= 4
        and ev.distinct_regions_with_kana >= 2
    ) or (
        ev.high_conf_kana_count >= 6  # dense single-region case
    )
    if strong_japanese:
        return "LANGUAGE_MISMATCH"

    # English-safety side: need decent Latin evidence and high enough
    # confidence OCR, with NO kana evidence at all (even weak).
    if (
        ev.japanese_kana_count == 0
        and ev.cjk_shared_count == 0
        and ev.latin_char_count >= 8
        and ev.mean_region_conf >= 0.35
        and ev.num_regions >= 2
    ):
        return "LANGUAGE_MATCH"

    return "LANGUAGE_UNVERIFIED"


def main():
    base = os.path.dirname(os.path.dirname(os.path.dirname(__file__)))  # repo root guess
    # Resolve relative to this file's backend/scripts location instead.
    repo_root = os.path.abspath(os.path.join(os.path.dirname(__file__), "..", ".."))
    split_path = os.path.join(
        repo_root, "backend", "artifacts", "index_fair_value",
        "ebay_e2_17_combined_corpus_split.json",
    )
    manifest_path = os.path.join(
        os.environ.get("E217_SCRATCH_DIR", ""), "sample_manifest.json"
    )
    with open(manifest_path, "r", encoding="utf-8") as f:
        manifest = json.load(f)

    import easyocr
    t0 = time.time()
    reader = easyocr.Reader(["ja", "en"], gpu=False, verbose=False)
    load_time = time.time() - t0

    out_rows = []
    infer_times = []
    for i, row in enumerate(manifest):
        if not row.get("fetch_ok") or not row.get("local_image_path"):
            ev = OcrEvidence(row_id=row["row_id"], ocr_ok=False, error="fetch_failed")
        else:
            t1 = time.time()
            ev = run_ocr(reader, row["local_image_path"], row["row_id"])
            infer_times.append(time.time() - t1)
        decision = ocr_v1_decision(ev)
        out_rows.append({
            **{k: row[k] for k in (
                "row_id", "source", "canonical_card_id", "human_truth_label",
                "split", "language_aspect_normalized", "listing_title",
            )},
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
            "ocr_v1_decision": decision,
            "raw_regions_sample": ev.raw_regions[:12],
        })
        print(f"[{i+1}/{len(manifest)}] {row['row_id']} truth={row['human_truth_label']} "
              f"split={row['split']} -> {decision} (kana={ev.japanese_kana_count}, "
              f"cjk={ev.cjk_shared_count}, hangul={ev.korean_hangul_count}, "
              f"latin={ev.latin_char_count}, regions={ev.num_regions})")

    result = {
        "model_load_seconds": load_time,
        "mean_inference_seconds": sum(infer_times) / len(infer_times) if infer_times else None,
        "n_images_ocr_attempted": len(infer_times),
        "rows": out_rows,
    }
    out_path = os.path.join(
        repo_root, "backend", "artifacts", "index_fair_value",
        "ebay_e2_17_ocr_results.json",
    )
    with open(out_path, "w", encoding="utf-8") as f:
        json.dump(result, f, indent=2)
    print("Wrote", out_path)
    print("Model load seconds:", load_time)
    if infer_times:
        print("Mean inference seconds:", sum(infer_times) / len(infer_times))


if __name__ == "__main__":
    main()
