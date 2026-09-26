"""Integrity tests for the EBAY E2.17C small Japanese holdout blind review
server and its historical-exclusion / sampling contract.

Covers the required integrity checks:
 10. holdout excludes old listing IDs (historical exclusion set membership)
 11. OCR output not used in sampling (builder module never imports the OCR
     scripts / never reads ocr_v2 output)
 12. reviewer sees only JAPANESE / NOT_JAPANESE / UNCERTAIN
 13. provider language hidden from reviewer-visible columns
 14. OCR evidence hidden from reviewer-visible columns
 15. review starts at 0 reviewed rows
 16. row/image binding (stable row_id <-> image_url pairing through freeze)
 17. no production writes (freeze only touches the E2.17C artifact paths)
"""
from __future__ import annotations

import csv
import importlib
import json
import sys
from pathlib import Path

import pytest

ROOT = Path(__file__).resolve().parents[2]
SCRIPTS = ROOT / "backend" / "scripts"
if str(SCRIPTS) not in sys.path:
    sys.path.insert(0, str(SCRIPTS))

srv = importlib.import_module("ebay_e2_17c_holdout_review_server")
builder = importlib.import_module("build_ebay_e2_17c_small_japanese_holdout")

REAL_QUEUE_PATH = ROOT / "backend/artifacts/index_fair_value/ebay_e2_17c_small_japanese_holdout_queue.csv"
REAL_MANIFEST_PATH = ROOT / "backend/artifacts/index_fair_value/ebay_e2_17c_small_japanese_holdout_manifest.json"


def _has_real_queue() -> bool:
    return REAL_QUEUE_PATH.exists()


# --------------------------------------------------------------------------
# 12. Exactly three label choices
# --------------------------------------------------------------------------


def test_label_choices_are_exactly_three():
    assert srv.LABEL_CHOICES == ("JAPANESE", "NOT_JAPANESE", "UNCERTAIN")


def test_build_label_event_rejects_other_labels():
    with pytest.raises(ValueError):
        srv.build_label_event("r1", "tester", "KOREAN")
    with pytest.raises(ValueError):
        srv.build_label_event("r1", "tester", "ENGLISH")


# --------------------------------------------------------------------------
# 13 & 14. Provider language / OCR evidence hidden
# --------------------------------------------------------------------------


def test_reviewer_visible_columns_exclude_forbidden_fields():
    assert srv.REVIEWER_VISIBLE_COLUMNS.isdisjoint(srv.FORBIDDEN_REVIEWER_COLUMNS)
    assert "language_aspect_normalized" not in srv.REVIEWER_VISIBLE_COLUMNS
    assert "development_stratum" not in srv.REVIEWER_VISIBLE_COLUMNS
    assert "listing_title" not in srv.REVIEWER_VISIBLE_COLUMNS
    assert "ocr_v2_decision" not in srv.REVIEWER_VISIBLE_COLUMNS


def test_assert_reviewer_blind_raises_on_leaked_column():
    rows = [{"row_id": "r1", "canonical_card_id": "c1", "image_url": "http://x",
             "language_aspect_normalized": "JAPANESE"}]
    with pytest.raises(srv.FreezeRefused):
        srv.assert_reviewer_blind(rows)


def test_assert_reviewer_blind_passes_on_clean_rows():
    rows = [{"row_id": "r1", "canonical_card_id": "c1", "image_url": "http://x",
             "human_truth_label": "", "human_note": "", "reviewer_id": "", "label_timestamp": ""}]
    srv.assert_reviewer_blind(rows)  # must not raise


def test_page_html_never_contains_forbidden_evidence_strings():
    row = {"row_id": "r1", "canonical_card_id": "c1", "image_url": "http://example/img.jpg"}
    html_out = srv.page(row, reviewed=0, total=1, position=1)
    for forbidden in ("language_aspect", "ocr_v2_decision", "korean_hangul_count",
                       "japanese_kana_count", "development_stratum"):
        assert forbidden not in html_out


# --------------------------------------------------------------------------
# 15. review starts at 0 reviewed rows (fresh manifest)
# --------------------------------------------------------------------------


def test_fresh_manifest_reports_zero_reviewed(tmp_path):
    rows = [{"row_id": f"r{i}", "canonical_card_id": f"c{i}", "image_url": f"http://x/{i}",
             "human_truth_label": "", "human_note": "", "reviewer_id": "", "label_timestamp": ""}
            for i in range(5)]
    queue_path = tmp_path / "queue.csv"
    with queue_path.open("w", encoding="utf-8", newline="") as fh:
        writer = csv.DictWriter(fh, fieldnames=list(rows[0].keys()))
        writer.writeheader()
        writer.writerows(rows)
    history_path = tmp_path / "history.jsonl"
    manifest_path = tmp_path / "manifest.json"
    s = srv.summary("tester", queue_path, history_path, manifest_path)
    assert s["reviewed_rows"] == 0
    assert s["total_rows"] == 5
    assert s["frozen"] is False
    assert s["development_holdout"] is True
    assert s["production_authority"] is False


# --------------------------------------------------------------------------
# 16. row/image binding through label + freeze cycle
# --------------------------------------------------------------------------


def test_label_and_freeze_preserves_row_image_binding(tmp_path):
    rows = [{"row_id": f"r{i}", "canonical_card_id": f"c{i}", "image_url": f"http://x/{i}.jpg",
             "human_truth_label": "", "human_note": "", "reviewer_id": "", "label_timestamp": ""}
            for i in range(3)]
    queue_path = tmp_path / "queue.csv"
    with queue_path.open("w", encoding="utf-8", newline="") as fh:
        writer = csv.DictWriter(fh, fieldnames=list(rows[0].keys()))
        writer.writeheader()
        writer.writerows(rows)
    history_path = tmp_path / "history.jsonl"
    manifest_path = tmp_path / "manifest.json"
    raw_path = tmp_path / "raw.jsonl"
    predictions_path = tmp_path / "predictions.json"
    raw_rows = [{**r, "listing_item_id": f"listing-{i}"} for i, r in enumerate(rows)]
    raw_path.write_text("".join(json.dumps(r) + "\n" for r in raw_rows), encoding="utf-8")
    predictions_path.write_text(json.dumps({"rows": [{"row_id": r["row_id"]} for r in rows]}), encoding="utf-8")
    manifest_path.write_text(json.dumps({"corpus_fingerprint": srv.corpus_fingerprint(raw_rows)}), encoding="utf-8")

    # freeze() enforces EXPECTED_ROW_COUNT_RANGE against the real holdout
    # target; monkeypatch the range for this small synthetic fixture only.
    original_range = srv.EXPECTED_ROW_COUNT_RANGE
    srv.EXPECTED_ROW_COUNT_RANGE = (1, 10)

    before_urls = {r["row_id"]: r["image_url"] for r in rows}

    for r in rows:
        event = srv.build_label_event(r["row_id"], "tester", "NOT_JAPANESE")
        srv.append_event(event, history_path, manifest_path)

    try:
        # The production verifier requires 43 rows; this fixture checks the
        # materialization path using an isolated verifier stub.
        original_verify = srv.verify_cohort
        srv.verify_cohort = lambda *args: None
        try:
            result = srv.freeze("tester", queue_path, history_path, manifest_path,
                                raw_path, predictions_path)
        finally:
            srv.verify_cohort = original_verify
    finally:
        srv.EXPECTED_ROW_COUNT_RANGE = original_range
    assert result["rows_materialized"] == 3

    after_rows = srv.load_queue_rows(queue_path)
    for r in after_rows:
        assert r["image_url"] == before_urls[r["row_id"]]
        assert r["human_truth_label"] == "NOT_JAPANESE"


def test_undo_then_relabel_works(tmp_path):
    rows = [{"row_id": "r0", "canonical_card_id": "c0", "image_url": "http://x/0.jpg",
             "human_truth_label": "", "human_note": "", "reviewer_id": "", "label_timestamp": ""}]
    history_path = tmp_path / "history.jsonl"
    manifest_path = tmp_path / "manifest.json"

    e1 = srv.build_label_event("r0", "tester", "JAPANESE")
    srv.append_event(e1, history_path, manifest_path)
    events = srv.read_history(history_path)
    undo = srv.build_undo_last_label_event(events, "tester")
    srv.append_event(undo, history_path, manifest_path)

    e2 = srv.build_label_event("r0", "tester", "NOT_JAPANESE")
    srv.append_event(e2, history_path, manifest_path)

    effective = srv.reconstruct_effective_labels(srv.read_history(history_path))
    assert effective["r0"]["human_truth_label"] == "NOT_JAPANESE"


# --------------------------------------------------------------------------
# 17. no production writes: freeze() only ever touches the queue_path passed
# in; it never imports or writes Fair Value / Explorer / price modules.
# --------------------------------------------------------------------------


def test_module_imports_no_production_write_paths():
    """The server module must never import a production write surface
    (Fair Value / Market Explorer / price-history writers) and never issue
    SQL writes -- checked against its actual `import` statements, not
    prose in comments/docstrings that legitimately reference these terms
    when explaining what this module does NOT do."""
    import ast
    import inspect
    tree = ast.parse(inspect.getsource(srv))
    imported_modules = set()
    for node in ast.walk(tree):
        if isinstance(node, ast.Import):
            imported_modules.update(a.name for a in node.names)
        elif isinstance(node, ast.ImportFrom) and node.module:
            imported_modules.add(node.module)
    for forbidden in ("fair_value", "market_explorer", "price_history"):
        assert not any(forbidden in m for m in imported_modules), imported_modules
    assert "INSERT INTO" not in inspect.getsource(srv)
    assert "UPDATE prices" not in inspect.getsource(srv)


# --------------------------------------------------------------------------
# 11. OCR output not used in sampling -- the builder module must not import
# the OCR-v2 (or OCR-v1) modules at all.
# --------------------------------------------------------------------------


def test_holdout_builder_never_imports_ocr_modules():
    """OCR output must never influence holdout row sampling: assert the
    builder's actual `import` statements never pull in either OCR module or
    easyocr itself (docstring prose that explains what this module does NOT
    do is not checked -- only real imports are)."""
    import ast
    import inspect
    tree = ast.parse(inspect.getsource(builder))
    imported_modules = set()
    for node in ast.walk(tree):
        if isinstance(node, ast.Import):
            imported_modules.update(a.name for a in node.names)
        elif isinstance(node, ast.ImportFrom) and node.module:
            imported_modules.add(node.module)
    assert not any("ocr_v1" in m or "ocr_v2" in m or m == "easyocr" for m in imported_modules), imported_modules


def test_holdout_builder_forbidden_reviewer_columns_defined():
    assert "language_aspect_normalized" in builder.FORBIDDEN_REVIEWER_COLUMNS
    assert "development_stratum" in builder.FORBIDDEN_REVIEWER_COLUMNS
    assert "listing_title" in builder.FORBIDDEN_REVIEWER_COLUMNS


# --------------------------------------------------------------------------
# 10. Historical exclusion set membership (uses real historical artifacts;
# skipped if none exist in this checkout, but they do in this repo).
# --------------------------------------------------------------------------


def test_historical_exclusion_covers_e216_and_e216b_listing_ids():
    e216_queue = ROOT / "backend/artifacts/index_fair_value/ebay_e2_16_language_development_queue.csv"
    e216b_queue = ROOT / "backend/artifacts/index_fair_value/ebay_e2_16b_japanese_language_development_queue.csv"
    if not (e216_queue.exists() and e216b_queue.exists()):
        pytest.skip("historical artifacts not present in this checkout")
    exclusions = builder._collect_historical_exclusions()
    exact = exclusions["exact_ids"]

    with e216_queue.open(encoding="utf-8", newline="") as fh:
        sample_e216_ids = [row["listing_item_id"] for row in csv.DictReader(fh) if row.get("listing_item_id")][:5]
    with e216b_queue.open(encoding="utf-8", newline="") as fh:
        sample_e216b_ids = [row["listing_item_id"] for row in csv.DictReader(fh) if row.get("listing_item_id")][:5]

    for lid in sample_e216_ids + sample_e216b_ids:
        assert lid in exact, f"{lid} should be excluded by historical exclusion set"


# --------------------------------------------------------------------------
# Real-artifact checks (run only if the holdout was actually captured)
# --------------------------------------------------------------------------


@pytest.mark.skipif(not _has_real_queue(), reason="real E2.17C holdout queue not yet captured")
def test_real_holdout_queue_reviewed_count_zero_and_labels_blank():
    rows = srv.load_queue_rows(REAL_QUEUE_PATH)
    assert len(rows) >= 1
    if not srv.is_frozen(REAL_MANIFEST_PATH):
        for r in rows:
            assert r["human_truth_label"] == ""
    srv.assert_reviewer_blind(rows)


@pytest.mark.skipif(not _has_real_queue(), reason="real E2.17C holdout queue not yet captured")
def test_real_holdout_row_count_in_target_range():
    rows = srv.load_queue_rows(REAL_QUEUE_PATH)
    lo, hi = srv.EXPECTED_ROW_COUNT_RANGE
    assert lo <= len(rows) <= hi
