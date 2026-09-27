"""Integrity tests for the EBAY E2.17A specific-language blind review server.

Covers the 14 integrity checks required before handoff:
1. exactly 25 rows
2. parent NON_ENGLISH truth unchanged (identity columns immutable through freeze)
3. specific-language labels blank initially
4. provider Language hidden
5. OCR evidence hidden
6. title not rendered
7. all available images render
8. first/middle/last row navigation
9. Previous works
10. Undo works
11. relabel works
12. fingerprint deterministic
13. no frozen OCR/policy artifact modified
14. development_only remains true
"""
from __future__ import annotations

import csv
import importlib
import json
import sys
from pathlib import Path

import pytest

ROOT = Path(__file__).resolve().parents[2]
if str(ROOT / "backend" / "scripts") not in sys.path:
    sys.path.insert(0, str(ROOT / "backend" / "scripts"))

srv = importlib.import_module("ebay_e2_17a_specific_language_review_server")

REAL_QUEUE_PATH = ROOT / "backend/artifacts/index_fair_value/ebay_e2_17_japanese_specific_language_review_queue.csv"
FEASIBILITY_MD = ROOT / "backend/artifacts/index_fair_value/EBAY_E2_17_OCR_V1_JAPANESE_LANGUAGE_FEASIBILITY.md"


# --------------------------------------------------------------------------
# Fixtures
# --------------------------------------------------------------------------


@pytest.fixture()
def real_rows() -> list[dict]:
    return srv.load_queue_rows(REAL_QUEUE_PATH)


@pytest.fixture()
def sandbox(tmp_path, real_rows):
    """A throwaway copy of the real 25-row queue plus fresh manifest/history
    paths, so tests can freeze/label without touching real artifacts."""
    queue_path = tmp_path / "queue.csv"
    with queue_path.open("w", encoding="utf-8", newline="") as fh:
        writer = csv.DictWriter(fh, fieldnames=list(real_rows[0].keys()))
        writer.writeheader()
        writer.writerows(real_rows)
    manifest_path = tmp_path / "manifest.json"
    history_path = tmp_path / "history.jsonl"
    return {
        "queue_path": queue_path,
        "manifest_path": manifest_path,
        "history_path": history_path,
    }


def label_all(sandbox, rows, reviewer="test_reviewer", label="JAPANESE"):
    for r in rows:
        event = srv.build_label_event(r["queue_row_id"], reviewer, label)
        srv.append_event(event, sandbox["history_path"], sandbox["manifest_path"])


# --------------------------------------------------------------------------
# 1. exactly 25 rows
# --------------------------------------------------------------------------


def test_exactly_25_rows(real_rows):
    assert len(real_rows) == srv.EXPECTED_ROW_COUNT == 25


# --------------------------------------------------------------------------
# 2. parent NON_ENGLISH truth unchanged (identity columns immutable)
# --------------------------------------------------------------------------


def test_parent_truth_identity_columns_present(real_rows):
    for col in srv.PARENT_TRUTH_IDENTITY_COLUMNS:
        assert all(col in r for r in real_rows)


def test_freeze_does_not_mutate_identity_columns(sandbox, real_rows):
    label_all(sandbox, real_rows)
    result = srv.freeze(
        "test_reviewer",
        queue_path=sandbox["queue_path"],
        history_path=sandbox["history_path"],
        manifest_path=sandbox["manifest_path"],
    )
    assert result["rows_materialized"] == 25
    after_rows = srv.load_queue_rows(sandbox["queue_path"])
    for before, after in zip(real_rows, after_rows):
        for col in srv.PARENT_TRUTH_IDENTITY_COLUMNS:
            assert before[col] == after[col]


def test_assert_parent_truth_identity_unchanged_detects_mutation():
    before = [{"queue_row_id": "r1", "source_row_id": "s1", "source_corpus": "c1", "canonical_card_id": "cc1"}]
    after = [{"queue_row_id": "r1", "source_row_id": "s1", "source_corpus": "c1", "canonical_card_id": "MUTATED"}]
    with pytest.raises(srv.FreezeRefused):
        srv.assert_parent_truth_identity_unchanged(before, after)


# --------------------------------------------------------------------------
# 3. specific-language labels blank initially
# --------------------------------------------------------------------------


def test_specific_language_blank_initially(real_rows):
    for r in real_rows:
        assert r["specific_language_if_known"] == ""


def test_reviewer_notes_blank_initially(real_rows):
    for r in real_rows:
        assert r["reviewer_notes"] == ""


def test_fresh_sandbox_has_zero_reviewed(sandbox):
    s = srv.summary("test_reviewer", sandbox["queue_path"], sandbox["history_path"], sandbox["manifest_path"])
    assert s["reviewed_rows"] == 0
    assert s["remaining_rows"] == 25
    assert s["frozen"] is False


# --------------------------------------------------------------------------
# 4/5. provider Language + OCR evidence hidden
# --------------------------------------------------------------------------


def test_no_forbidden_columns_in_real_queue(real_rows):
    present = srv.FORBIDDEN_REVIEWER_COLUMNS & set(real_rows[0].keys())
    assert present == set()
    srv.assert_reviewer_blind(real_rows)  # must not raise


def test_assert_reviewer_blind_raises_on_leak():
    leaked_rows = [{"queue_row_id": "r1", "ocr_confidence": "0.9"}]
    with pytest.raises(srv.FreezeRefused):
        srv.assert_reviewer_blind(leaked_rows)


def test_rendered_page_has_no_forbidden_evidence(real_rows):
    html_out = srv.page(real_rows[0], reviewed=0, total=25, position=1)
    for forbidden in srv.FORBIDDEN_REVIEWER_COLUMNS:
        assert forbidden not in html_out.lower()
    assert "language aspect" not in html_out.lower()
    assert "ocr_" not in html_out.lower()
    assert "ocr output" not in html_out.lower()
    assert "ocr confidence" not in html_out.lower()
    assert "japanese character count" not in html_out.lower()


def test_rendered_page_only_uses_allowlisted_columns(real_rows):
    row = dict(real_rows[0])
    row["listing_title_DO_NOT_USE_AS_EVIDENCE"] = "UNIQUE_TITLE_TOKEN_ZZZ"
    html_out = srv.page(row, reviewed=0, total=25, position=1)
    assert "UNIQUE_TITLE_TOKEN_ZZZ" not in html_out


# --------------------------------------------------------------------------
# 6. title not rendered
# --------------------------------------------------------------------------


def test_title_column_not_in_allowlist():
    assert "listing_title_DO_NOT_USE_AS_EVIDENCE" not in srv.REVIEWER_VISIBLE_COLUMNS


def test_title_never_appears_in_any_rendered_row(real_rows):
    for row in real_rows:
        html_out = srv.page(row, reviewed=0, total=25, position=1)
        title = row["listing_title_DO_NOT_USE_AS_EVIDENCE"]
        assert title not in html_out


# --------------------------------------------------------------------------
# 7. all available images render
# --------------------------------------------------------------------------


def test_image_url_renders_for_every_row(real_rows):
    for row in real_rows:
        html_out = srv.page(row, reviewed=0, total=25, position=1)
        assert row["image_url"] in html_out


# --------------------------------------------------------------------------
# 8. first/middle/last row navigation
# --------------------------------------------------------------------------


def test_first_middle_last_navigation(real_rows):
    n = len(real_rows)
    first, middle, last = real_rows[0], real_rows[n // 2], real_rows[-1]
    for row in (first, middle, last):
        html_out = srv.page(row, reviewed=0, total=n, position=1)
        assert row["queue_row_id"] in html_out


def test_next_unreviewed_index_walks_all_rows(real_rows):
    effective: dict = {}
    idx = -1
    seen = set()
    for _ in range(len(real_rows)):
        idx = srv.next_unreviewed_index(real_rows, effective, idx)
        assert idx is not None
        row_id = real_rows[idx]["queue_row_id"]
        assert row_id not in seen
        seen.add(row_id)
        effective[row_id] = {"specific_language_if_known": "JAPANESE"}
    assert srv.next_unreviewed_index(real_rows, effective, idx) is None


def test_clamped_index_bounds():
    assert srv._clamped_index(-5, 25) == 0
    assert srv._clamped_index(100, 25) == 24
    assert srv._clamped_index(10, 25) == 10


# --------------------------------------------------------------------------
# 9. Previous works (clamped index arithmetic, exercised via server helper)
# --------------------------------------------------------------------------


def test_previous_moves_index_back():
    n = 25
    index = 10
    index = srv._clamped_index(index - 1, n)
    assert index == 9


def test_previous_clamps_at_zero():
    n = 25
    index = 0
    index = srv._clamped_index(index - 1, n)
    assert index == 0


# --------------------------------------------------------------------------
# 10. Undo works
# --------------------------------------------------------------------------


def test_undo_reverts_last_label(sandbox, real_rows):
    row = real_rows[0]
    event = srv.build_label_event(row["queue_row_id"], "test_reviewer", "KOREAN")
    srv.append_event(event, sandbox["history_path"], sandbox["manifest_path"])
    effective = srv.reconstruct_effective_labels(srv.read_history(sandbox["history_path"]))
    assert effective[row["queue_row_id"]]["specific_language_if_known"] == "KOREAN"

    undo_event = srv.build_undo_last_label_event(srv.read_history(sandbox["history_path"]), "test_reviewer")
    assert undo_event is not None
    srv.append_event(undo_event, sandbox["history_path"], sandbox["manifest_path"])
    effective = srv.reconstruct_effective_labels(srv.read_history(sandbox["history_path"]))
    assert row["queue_row_id"] not in effective


def test_undo_with_no_labels_returns_none(sandbox):
    undo_event = srv.build_undo_last_label_event(srv.read_history(sandbox["history_path"]), "test_reviewer")
    assert undo_event is None


# --------------------------------------------------------------------------
# 11. relabel works
# --------------------------------------------------------------------------


def test_relabel_overwrites_effective_label(sandbox, real_rows):
    row = real_rows[0]
    e1 = srv.build_label_event(row["queue_row_id"], "test_reviewer", "CHINESE")
    srv.append_event(e1, sandbox["history_path"], sandbox["manifest_path"])
    e2 = srv.build_label_event(row["queue_row_id"], "test_reviewer", "JAPANESE")
    srv.append_event(e2, sandbox["history_path"], sandbox["manifest_path"])
    effective = srv.reconstruct_effective_labels(srv.read_history(sandbox["history_path"]))
    assert effective[row["queue_row_id"]]["specific_language_if_known"] == "JAPANESE"


def test_build_label_event_rejects_english():
    with pytest.raises(ValueError):
        srv.build_label_event("r1", "reviewer", "ENGLISH")


def test_build_label_event_rejects_invalid_label():
    with pytest.raises(ValueError):
        srv.build_label_event("r1", "reviewer", "MARTIAN")


def test_all_specific_language_choices_valid_and_no_english():
    assert "ENGLISH" not in srv.SPECIFIC_LANGUAGE_CHOICES
    assert set(srv.SPECIFIC_LANGUAGE_CHOICES) == {
        "JAPANESE", "KOREAN", "CHINESE", "OTHER_NON_ENGLISH", "UNCERTAIN",
    }


# --------------------------------------------------------------------------
# 12. fingerprint deterministic
# --------------------------------------------------------------------------


def test_corpus_fingerprint_deterministic(real_rows):
    fp1 = srv.corpus_fingerprint(real_rows)
    fp2 = srv.corpus_fingerprint(list(reversed(real_rows)))  # order-independent
    assert fp1 == fp2
    fp3 = srv.corpus_fingerprint(real_rows)
    assert fp1 == fp3


def test_label_fingerprint_deterministic(sandbox, real_rows):
    label_all(sandbox, real_rows, label="JAPANESE")
    result1 = srv.freeze(
        "test_reviewer",
        queue_path=sandbox["queue_path"],
        history_path=sandbox["history_path"],
        manifest_path=sandbox["manifest_path"],
    )
    fp1 = result1["specific_language_label_fingerprint"]

    # Rebuild an independent sandbox with the same labels, confirm same fingerprint.
    import tempfile
    with tempfile.TemporaryDirectory() as td:
        td_path = Path(td)
        queue_path2 = td_path / "queue.csv"
        with queue_path2.open("w", encoding="utf-8", newline="") as fh:
            writer = csv.DictWriter(fh, fieldnames=list(real_rows[0].keys()))
            writer.writeheader()
            writer.writerows(real_rows)
        manifest_path2 = td_path / "manifest.json"
        history_path2 = td_path / "history.jsonl"
        for r in real_rows:
            event = srv.build_label_event(r["queue_row_id"], "test_reviewer", "JAPANESE")
            srv.append_event(event, history_path2, manifest_path2)
        result2 = srv.freeze("test_reviewer", queue_path=queue_path2, history_path=history_path2, manifest_path=manifest_path2)
        fp2 = result2["specific_language_label_fingerprint"]
    assert fp1 == fp2


# --------------------------------------------------------------------------
# 13. no frozen OCR/policy artifact modified
# --------------------------------------------------------------------------


def test_feasibility_report_not_modified_by_import():
    assert FEASIBILITY_MD.exists()
    # Server module import / row loading must not touch this file's mtime/content;
    # simplest robust check: content is non-empty and untouched by our test run.
    content_before = FEASIBILITY_MD.read_text(encoding="utf-8")
    srv.load_queue_rows(REAL_QUEUE_PATH)
    content_after = FEASIBILITY_MD.read_text(encoding="utf-8")
    assert content_before == content_after


def test_real_queue_csv_not_mutated_by_test_suite(real_rows):
    # This test operates only on the sandboxed copy elsewhere; confirm the real
    # queue file still has blank specific_language_if_known (i.e. no test wrote to it).
    fresh = srv.load_queue_rows(REAL_QUEUE_PATH)
    for r in fresh:
        assert r["specific_language_if_known"] == ""
    assert fresh == real_rows


# --------------------------------------------------------------------------
# 14. development_only remains true
# --------------------------------------------------------------------------


def test_summary_development_only_true(sandbox):
    s = srv.summary("test_reviewer", sandbox["queue_path"], sandbox["history_path"], sandbox["manifest_path"])
    assert s["development_only"] is True
    assert s["production_authority"] is False


def test_freeze_manifest_development_only_true(sandbox, real_rows):
    label_all(sandbox, real_rows)
    result = srv.freeze(
        "test_reviewer",
        queue_path=sandbox["queue_path"],
        history_path=sandbox["history_path"],
        manifest_path=sandbox["manifest_path"],
    )
    assert result["development_only"] is True
    assert result["production_authority"] is False
    manifest = json.loads(sandbox["manifest_path"].read_text(encoding="utf-8"))
    assert manifest["development_only"] is True
    assert manifest["production_authority"] is False


# --------------------------------------------------------------------------
# Additional freeze-safety coverage
# --------------------------------------------------------------------------


def test_freeze_refuses_when_incomplete(sandbox, real_rows):
    # Label only 24 of 25 rows.
    for r in real_rows[:-1]:
        event = srv.build_label_event(r["queue_row_id"], "test_reviewer", "JAPANESE")
        srv.append_event(event, sandbox["history_path"], sandbox["manifest_path"])
    with pytest.raises(srv.FreezeRefused):
        srv.freeze(
            "test_reviewer",
            queue_path=sandbox["queue_path"],
            history_path=sandbox["history_path"],
            manifest_path=sandbox["manifest_path"],
        )


def test_freeze_refuses_double_freeze(sandbox, real_rows):
    label_all(sandbox, real_rows)
    srv.freeze("test_reviewer", queue_path=sandbox["queue_path"], history_path=sandbox["history_path"], manifest_path=sandbox["manifest_path"])
    with pytest.raises(srv.FreezeRefused):
        srv.freeze("test_reviewer", queue_path=sandbox["queue_path"], history_path=sandbox["history_path"], manifest_path=sandbox["manifest_path"])


def test_append_event_refuses_after_freeze(sandbox, real_rows):
    label_all(sandbox, real_rows)
    srv.freeze("test_reviewer", queue_path=sandbox["queue_path"], history_path=sandbox["history_path"], manifest_path=sandbox["manifest_path"])
    event = srv.build_label_event(real_rows[0]["queue_row_id"], "test_reviewer", "KOREAN")
    with pytest.raises(srv.ReviewFrozen):
        srv.append_event(event, sandbox["history_path"], sandbox["manifest_path"])
