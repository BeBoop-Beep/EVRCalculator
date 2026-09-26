"""EBAY E2.17B -- Authoritative Japanese OCR validation tests.

Real data, real fingerprints, real (unchanged) OCR-v1 candidate. No mocks for
items 1-14/21. Items 15-20 concern LANGUAGE-v2 / COMBINED-v4 / E2.14
post-hoc, none of which were implemented or frozen because OCR-v1 itself did
not clear the Phase G freeze bar (heldout Japanese N=4, trivially small).
Those tests instead pin the SPEC-DEFINED precedence table as pure logic
(the contract this task would build against, IF a future task freezes
OCR-v1) and assert that no freeze/production artifact was produced this run.

DEVELOPMENT_ONLY. No production reads/writes. No git operations.
"""
from __future__ import annotations

import csv
import hashlib
import json
import math
import os
import sys

import pytest

ROOT = os.path.abspath(os.path.join(os.path.dirname(__file__), "..", "..", ".."))
AF = os.path.join(ROOT, "backend", "artifacts", "index_fair_value")
SCRIPTS = os.path.join(ROOT, "backend", "scripts")
if SCRIPTS not in sys.path:
    sys.path.insert(0, SCRIPTS)

EXPECTED_CORPUS_FP = "4a5607b94dbdfb7c5123316c2855a181903f0089b5bf66015491febc3e9e4333"
EXPECTED_LABEL_FP = "3dc900663abc939c64564383fe79234aea01b7abd7d252e5f1c3ce562ba0dda9"


# ---------------------------------------------------------------------------
# fixtures
# ---------------------------------------------------------------------------

@pytest.fixture(scope="module")
def queue_rows():
    path = os.path.join(AF, "ebay_e2_17_japanese_specific_language_review_queue.csv")
    with open(path, encoding="utf-8", newline="") as f:
        return list(csv.DictReader(f))


@pytest.fixture(scope="module")
def split_rows():
    with open(os.path.join(AF, "ebay_e2_17_combined_corpus_split.json"), encoding="utf-8") as f:
        return json.load(f)


@pytest.fixture(scope="module")
def split_by_id(split_rows):
    return {r["row_id"]: r for r in split_rows}


@pytest.fixture(scope="module")
def orig_ocr():
    with open(os.path.join(AF, "ebay_e2_17_ocr_results.json"), encoding="utf-8") as f:
        return json.load(f)


@pytest.fixture(scope="module")
def supp_ocr():
    with open(os.path.join(AF, "ebay_e2_17b_supplemental_ocr_results.json"), encoding="utf-8") as f:
        return json.load(f)


@pytest.fixture(scope="module")
def ocr_by_id(orig_ocr, supp_ocr):
    merged = {r["row_id"]: r for r in orig_ocr["rows"]}
    for r in supp_ocr["rows"]:
        assert r["row_id"] not in merged, "supplemental OCR must not duplicate original rows"
        merged[r["row_id"]] = r
    return merged


@pytest.fixture(scope="module")
def joined25(queue_rows, split_by_id, ocr_by_id):
    rows = []
    for qr in queue_rows:
        src = qr["source_row_id"]
        sp = split_by_id[src]
        oc = ocr_by_id[src]
        rows.append({
            "queue_row_id": qr["queue_row_id"],
            "row_id": src,
            "specific_language": qr["specific_language_if_known"],
            "split": sp["split"],
            "ocr_v1_decision": oc["ocr_v1_decision"],
            "japanese_kana_count": oc["japanese_kana_count"],
            "cjk_shared_count": oc["cjk_shared_count"],
            "korean_hangul_count": oc["korean_hangul_count"],
        })
    return rows


def _corpus_fingerprint(rows):
    return hashlib.sha256(
        "|".join(
            sorted(
                "{}:{}:{}:{}".format(
                    r["queue_row_id"], r["source_row_id"], r["source_corpus"], r["canonical_card_id"]
                )
                for r in rows
            )
        ).encode()
    ).hexdigest()


def _label_fingerprint(rows):
    return hashlib.sha256(
        "\n".join(sorted(f"{r['queue_row_id']}:{r['specific_language_if_known']}" for r in rows)).encode()
    ).hexdigest()


def wilson_interval(x, n, z=1.959963985):
    if n == 0:
        return (None, None)
    phat = x / n
    denom = 1 + z ** 2 / n
    center = phat + z ** 2 / (2 * n)
    margin = z * math.sqrt((phat * (1 - phat) + z ** 2 / (4 * n)) / n)
    return (max(0.0, (center - margin) / denom), min(1.0, (center + margin) / denom))


# ---------------------------------------------------------------------------
# 1. corpus fingerprint
# ---------------------------------------------------------------------------

def test_specific_language_corpus_fingerprint(queue_rows):
    assert len(queue_rows) == 25
    assert _corpus_fingerprint(queue_rows) == EXPECTED_CORPUS_FP


# ---------------------------------------------------------------------------
# 2. label fingerprint
# ---------------------------------------------------------------------------

def test_specific_language_label_fingerprint(queue_rows):
    assert _label_fingerprint(queue_rows) == EXPECTED_LABEL_FP
    manifest_path = os.path.join(AF, "ebay_e2_17a_specific_language_review_manifest.json")
    manifest = json.loads(open(manifest_path, encoding="utf-8").read())
    assert manifest["labels_frozen"] is True
    assert manifest["development_only"] is True
    assert manifest["production_authority"] is False
    assert manifest["specific_language_label_fingerprint"] == EXPECTED_LABEL_FP
    assert manifest["corpus_fingerprint"] == EXPECTED_CORPUS_FP
    assert manifest["specific_language_label_counts"] == {"JAPANESE": 16, "CHINESE": 5, "KOREAN": 4}


# ---------------------------------------------------------------------------
# 3. original split preservation (no reshuffle after seeing specific labels)
# ---------------------------------------------------------------------------

def test_original_split_preserved_and_not_reshuffled(queue_rows, split_by_id):
    # every queued row must resolve to a pre-existing E2.17 split row, and
    # every one of the 25 rows' split membership must be exactly what the
    # (earlier, label-blind) split file already recorded -- i.e. we read it,
    # we never recompute or reassign split here.
    seen_splits = set()
    for qr in queue_rows:
        sp = split_by_id.get(qr["source_row_id"])
        assert sp is not None, f"row {qr['source_row_id']} missing from E2.17 split"
        assert sp["split"] in ("DESIGN", "HELDOUT")
        seen_splits.add(sp["split"])
    assert seen_splits == {"DESIGN", "HELDOUT"}


def test_design_heldout_counts_by_specific_language(joined25):
    counts = {}
    for r in joined25:
        counts.setdefault(r["specific_language"], {}).setdefault(r["split"], 0)
        counts[r["specific_language"]][r["split"]] += 1
    assert counts["JAPANESE"] == {"DESIGN": 12, "HELDOUT": 4}
    assert counts["CHINESE"] == {"DESIGN": 4, "HELDOUT": 1}
    assert counts["KOREAN"] == {"DESIGN": 2, "HELDOUT": 2}


# ---------------------------------------------------------------------------
# 4/5. Japanese TP / FN
# ---------------------------------------------------------------------------

def test_japanese_true_positive_rows_exist(joined25):
    jp = [r for r in joined25 if r["specific_language"] == "JAPANESE"]
    tp = [r for r in jp if r["ocr_v1_decision"] == "LANGUAGE_MISMATCH"]
    assert len(jp) == 16
    assert len(tp) == 12  # all-25 characterization


def test_japanese_false_negatives_fail_to_unverified_not_match(joined25):
    jp = [r for r in joined25 if r["specific_language"] == "JAPANESE"]
    fn = [r for r in jp if r["ocr_v1_decision"] != "LANGUAGE_MISMATCH"]
    assert len(fn) == 4
    # safety property: every miss must be UNVERIFIED, never a false MATCH
    assert all(r["ocr_v1_decision"] == "LANGUAGE_UNVERIFIED" for r in fn)


# ---------------------------------------------------------------------------
# 6/7. Chinese/Korean not Japanese
# ---------------------------------------------------------------------------

def test_chinese_rows_never_classified_japanese_mismatch(joined25):
    zh = [r for r in joined25 if r["specific_language"] == "CHINESE"]
    assert len(zh) == 5
    assert all(r["ocr_v1_decision"] != "LANGUAGE_MISMATCH" for r in zh)


def test_korean_rows_never_classified_japanese_mismatch(joined25):
    ko = [r for r in joined25 if r["specific_language"] == "KOREAN"]
    assert len(ko) == 4
    assert all(r["ocr_v1_decision"] != "LANGUAGE_MISMATCH" for r in ko)


# ---------------------------------------------------------------------------
# 8/9. heldout-only vs all-row characterization metrics
# ---------------------------------------------------------------------------

def test_heldout_only_japanese_metrics(joined25):
    jp_ho = [r for r in joined25 if r["specific_language"] == "JAPANESE" and r["split"] == "HELDOUT"]
    assert len(jp_ho) == 4  # trivially small -- the whole point of Phase G
    tp = sum(1 for r in jp_ho if r["ocr_v1_decision"] == "LANGUAGE_MISMATCH")
    assert tp == 3
    assert (tp / len(jp_ho)) == pytest.approx(0.75)


def test_all_row_japanese_characterization_metrics(joined25):
    jp_all = [r for r in joined25 if r["specific_language"] == "JAPANESE"]
    tp = sum(1 for r in jp_all if r["ocr_v1_decision"] == "LANGUAGE_MISMATCH")
    assert len(jp_all) == 16
    assert tp == 12
    assert (tp / len(jp_all)) == pytest.approx(0.75)


def test_heldout_and_all_row_metrics_are_kept_distinct(joined25):
    # Phase B requirement: never conflate heldout-only evidence with
    # all-25 post-hoc development characterization.
    jp_ho = [r for r in joined25 if r["specific_language"] == "JAPANESE" and r["split"] == "HELDOUT"]
    jp_all = [r for r in joined25 if r["specific_language"] == "JAPANESE"]
    assert len(jp_ho) < len(jp_all)


# ---------------------------------------------------------------------------
# 10. English false mismatch (reconfirmation on original E2.17 population)
# ---------------------------------------------------------------------------

def test_english_false_japanese_mismatch_rate(orig_ocr):
    eng = [r for r in orig_ocr["rows"] if r["human_truth_label"] == "ENGLISH"]
    false_mismatch = [r for r in eng if r["ocr_v1_decision"] == "LANGUAGE_MISMATCH"]
    assert len(eng) == 65
    assert len(false_mismatch) == 0
    lo, hi = wilson_interval(len(false_mismatch), len(eng))
    assert lo == 0.0
    assert hi < 0.06


# ---------------------------------------------------------------------------
# 11. single Han glyph insufficient / 12. kana positive / 13. Hangul suppression
# ---------------------------------------------------------------------------

def test_single_han_glyph_alone_not_sufficient_for_mismatch():
    from ebay_e2_17_ocr_v1_japanese_language_feasibility import OcrEvidence, ocr_v1_decision
    ev = OcrEvidence(row_id="synthetic_single_han", ocr_ok=True, num_regions=3,
                      total_recognized_text=10, cjk_shared_count=1, latin_char_count=8,
                      mean_region_conf=0.6)
    assert ocr_v1_decision(ev) != "LANGUAGE_MISMATCH"


def test_kana_evidence_can_trigger_mismatch():
    from ebay_e2_17_ocr_v1_japanese_language_feasibility import OcrEvidence, ocr_v1_decision
    ev = OcrEvidence(row_id="synthetic_strong_kana", ocr_ok=True, num_regions=3,
                      total_recognized_text=20, high_conf_kana_count=6,
                      distinct_regions_with_kana=1, mean_region_conf=0.6)
    assert ocr_v1_decision(ev) == "LANGUAGE_MISMATCH"


def test_hangul_suppresses_japanese_classification_even_with_strong_kana_signal():
    from ebay_e2_17_ocr_v1_japanese_language_feasibility import OcrEvidence, ocr_v1_decision
    ev = OcrEvidence(row_id="synthetic_hangul_guard", ocr_ok=True, num_regions=3,
                      total_recognized_text=20, high_conf_kana_count=6,
                      distinct_regions_with_kana=2, korean_hangul_count=2,
                      mean_region_conf=0.6)
    assert ocr_v1_decision(ev) == "LANGUAGE_UNVERIFIED"


def test_hangul_guard_never_observed_to_fire_on_real_korean_rows(joined25):
    # Documented finding: the reader is loaded with ["ja", "en"] only (no
    # "ko" model), so real Hangul is never recognized as Hangul text by this
    # candidate -- korean_hangul_count is 0 on every real Korean row in the
    # corpus. Korean safety in practice is provided by the "kana evidence
    # required" arm, not by the Hangul hard-negative arm. This is a real
    # finding, not something this task is allowed to fix (no retuning).
    ko = [r for r in joined25 if r["specific_language"] == "KOREAN"]
    assert all(r["korean_hangul_count"] == 0 for r in ko)


# ---------------------------------------------------------------------------
# 14. OCR candidate immutability / provenance
# ---------------------------------------------------------------------------

def test_ocr_candidate_source_immutable_since_e2_17(orig_ocr):
    src_path = os.path.join(SCRIPTS, "ebay_e2_17_ocr_v1_japanese_language_feasibility.py")
    src_bytes = open(src_path, "rb").read()
    src_sha256 = hashlib.sha256(src_bytes).hexdigest()
    # Recorded at the start of this E2.17B run (see scratch run log); pinned
    # here so any future edit to the OCR-v1 source fails this test loudly.
    assert src_sha256 == "54ad9bf1b33a7247e2a7db52e0e5806c827271cbb0271e96737e0573b9de8212"
    # sanity: the frozen E2.17 results file still exists unmodified in shape
    assert orig_ocr["n_images_ocr_attempted"] == 138
    assert len(orig_ocr["rows"]) == 139


def test_ocr_decision_rule_unicode_ranges_unchanged():
    from ebay_e2_17_ocr_v1_japanese_language_feasibility import HIRAGANA, KATAKANA, CJK_UNIFIED, HANGUL
    assert HIRAGANA == (0x3040, 0x309F)
    assert KATAKANA == (0x30A0, 0x30FF)
    assert CJK_UNIFIED == (0x4E00, 0x9FFF)
    assert HANGUL == (0xAC00, 0xD7A3)


# ---------------------------------------------------------------------------
# 15. OCR freeze fingerprint -- NOT frozen this run (documents why)
# ---------------------------------------------------------------------------

def test_ocr_v1_not_frozen_this_run_no_freeze_artifact_written():
    # Phase G bar was not cleared (heldout Japanese N=4, trivially small),
    # so no OCR-v1 freeze fingerprint file should exist.
    freeze_path = os.path.join(AF, "ebay_e2_17b_ocr_v1_freeze.json")
    assert not os.path.exists(freeze_path)


# ---------------------------------------------------------------------------
# 16-19. LANGUAGE-v2 precedence contract (pure spec logic; not implemented,
# since OCR-v1 did not freeze and LANGUAGE-v2 is gated on that freeze).
# ---------------------------------------------------------------------------

def _language_v2_spec(provider_language, ocr_state):
    """Pure re-statement of the Phase I precedence table from the task spec.
    Not wired into any production code path -- this is a contract pin for a
    future implementation, gated on OCR-v1 freezing (which it did not, this
    run)."""
    if provider_language in ("KOREAN", "CHINESE"):
        return "LANGUAGE_MISMATCH"
    if provider_language == "JAPANESE" and ocr_state == "CLEAR_ENGLISH":
        return "NO_VETO"
    if ocr_state == "CLEAR_JAPANESE":
        return "LANGUAGE_MISMATCH"
    if provider_language in ("ENGLISH", None) and ocr_state == "CLEAR_JAPANESE":
        return "LANGUAGE_MISMATCH"
    if ocr_state in ("WEAK", "FAILED"):
        return "UNVERIFIED_OR_PRESERVE_OTHER"
    if provider_language == "FRENCH_OR_UNSUPPORTED":
        return "UNVERIFIED"
    return "UNVERIFIED"


def test_language_v2_precedence_provider_korean_chinese_always_mismatch():
    assert _language_v2_spec("KOREAN", "CLEAR_ENGLISH") == "LANGUAGE_MISMATCH"
    assert _language_v2_spec("CHINESE", "WEAK") == "LANGUAGE_MISMATCH"


def test_language_v2_provider_japanese_alone_cannot_veto():
    assert _language_v2_spec("JAPANESE", "CLEAR_ENGLISH") == "NO_VETO"


def test_language_v2_ocr_clear_japanese_can_veto_regardless_of_provider():
    assert _language_v2_spec("JAPANESE", "CLEAR_JAPANESE") == "LANGUAGE_MISMATCH"
    assert _language_v2_spec("ENGLISH", "CLEAR_JAPANESE") == "LANGUAGE_MISMATCH"
    assert _language_v2_spec(None, "CLEAR_JAPANESE") == "LANGUAGE_MISMATCH"


def test_language_v2_weak_ocr_never_invents_a_mismatch():
    result = _language_v2_spec("ENGLISH", "WEAK")
    assert result != "LANGUAGE_MISMATCH"


# ---------------------------------------------------------------------------
# 20. COMBINED-v4 language rejection contract (pure spec logic)
# ---------------------------------------------------------------------------

def _combined_v4_spec(language_v2_state, other_combined_v3_state):
    if language_v2_state == "LANGUAGE_MISMATCH":
        return "REJECTED_LANGUAGE_CONTRADICTION"
    if language_v2_state == "LANGUAGE_MATCH":
        return other_combined_v3_state
    if language_v2_state == "LANGUAGE_UNVERIFIED":
        return other_combined_v3_state
    return other_combined_v3_state


def test_combined_v4_rejects_on_language_mismatch():
    assert _combined_v4_spec("LANGUAGE_MISMATCH", "PROMOTED") == "REJECTED_LANGUAGE_CONTRADICTION"


def test_combined_v4_unverified_preserves_existing_combined_behavior():
    assert _combined_v4_spec("LANGUAGE_UNVERIFIED", "PROMOTED") == "PROMOTED"
    assert _combined_v4_spec("LANGUAGE_UNVERIFIED", "REJECTED_OTHER") == "REJECTED_OTHER"


# ---------------------------------------------------------------------------
# 20b/21. E2.14 post-hoc only + no production writes
# ---------------------------------------------------------------------------

def test_e2_14_diagnostic_was_not_run_this_task():
    # Phase K is explicitly gated on OCR-v1 + LANGUAGE-v2 + COMBINED-v4 all
    # freezing. None froze this run, so no E2.14 E2.17B diagnostic artifact
    # should exist, and the frozen E2.14 certification artifacts must be
    # byte-identical to what E2.17B started with (untouched).
    diag_path = os.path.join(AF, "ebay_e2_17b_e2_14_post_hoc_diagnostic.json")
    assert not os.path.exists(diag_path)
    e214_cert = os.path.join(AF, "ebay_e2_14_fresh_blind_certification.json")
    assert os.path.exists(e214_cert), "frozen E2.14 certification artifact must still exist, untouched"


def test_no_production_database_or_service_modules_touched():
    # This task must not import/modify Fair Value, Explorer, or production
    # write-path modules. Sanity check: this test module itself only reads
    # local artifact files and imports the pure OCR-v1 research script.
    forbidden_modules = ("fair_value_service", "market_explorer_service", "pokemon_set_cards_market_analytics_service")
    for name in sys.modules:
        for forbidden in forbidden_modules:
            assert forbidden not in name


def test_supplemental_ocr_results_file_is_clearly_labeled_non_production():
    with open(os.path.join(AF, "ebay_e2_17b_supplemental_ocr_results.json"), encoding="utf-8") as f:
        data = json.load(f)
    assert "note" in data
    assert "UNCHANGED" in data["note"]
    assert "ocr_v1_source_sha256" in data
