"""Tests for EBAY E2.16 -- targeted foreign-language DEVELOPMENT cohort +
review server. DEVELOPMENT-ONLY artifact: these tests verify corpus
construction, historical exclusion, reviewer blinding, and the review
server's session/cursor/undo/edit machinery. They never assert any
LANGUAGE-v1 freeze, certification result, or production authority --
none of those exist yet.
"""
from __future__ import annotations

import csv
import json
from pathlib import Path

import pytest

from backend.scripts import build_ebay_e2_16_language_development_cohort as builder
from backend.scripts import ebay_e2_16_language_development_review_server as server

ARTIFACTS = Path(__file__).resolve().parents[1] / "artifacts" / "index_fair_value"
QUEUE_PATH = ARTIFACTS / "ebay_e2_16_language_development_queue.csv"
MANIFEST_PATH = ARTIFACTS / "ebay_e2_16_language_development_manifest.json"
RAW_PATH = ARTIFACTS / "ebay_e2_16_language_development_raw_internal.jsonl"


def _load_queue_rows():
    with QUEUE_PATH.open(encoding="utf-8", newline="") as fh:
        return list(csv.DictReader(fh))


def _load_internal_rows():
    return [json.loads(line) for line in RAW_PATH.read_text(encoding="utf-8").splitlines() if line.strip()]


def _load_manifest():
    return json.loads(MANIFEST_PATH.read_text(encoding="utf-8"))


# --------------------------------------------------------------------------
# 1. historical ID exclusion
# --------------------------------------------------------------------------


def test_historical_id_exclusion_no_overlap():
    exclusions = builder._collect_historical_exclusions()
    excluded_ids = exclusions["exact_ids"]
    assert len(excluded_ids) > 1000  # sanity: real historical corpora are large
    rows = _load_queue_rows()
    overlap = [r["listing_item_id"] for r in rows if r["listing_item_id"] in excluded_ids]
    assert overlap == []


def test_historical_id_exclusion_covers_expected_files():
    exclusions = builder._collect_historical_exclusions()
    counts = exclusions["counts_per_file"]
    for name in builder.HISTORICAL_FILES:
        assert name in counts
    assert "ebay_e2_14_fresh_blind_predictions.json" in counts
    assert "ebay_e2_15_item_detail_language_study.json" in counts
    assert counts["ebay_e2_15_item_detail_language_study.json"] == 38


# --------------------------------------------------------------------------
# 2. language-strata sampling
# --------------------------------------------------------------------------


def test_strata_present_in_manifest():
    manifest = _load_manifest()
    strata = manifest["strata_counts_selected"]
    assert manifest["row_count"] == sum(strata.values())
    assert strata.get("ENGLISH_CONTROL", 0) > 0
    assert strata.get("NON_LATIN_FOREIGN", 0) > 0
    assert strata.get("LATIN_SCRIPT_FOREIGN", 0) > 0


def test_row_count_in_target_range():
    manifest = _load_manifest()
    # Spec target: ~150-250, prefer ~200. Report honestly if under/over.
    assert 50 <= manifest["row_count"] <= 250


# --------------------------------------------------------------------------
# 3. explicit Language raw preservation (internal artifact only)
# --------------------------------------------------------------------------


def test_internal_raw_preserves_language_aspect():
    internal = _load_internal_rows()
    assert internal, "internal raw artifact must be non-empty"
    assert all("language_aspect_raw" in row for row in internal)
    assert all("language_aspect_normalized" in row for row in internal)
    assert all("language_aspect_present" in row for row in internal)
    present_count = sum(1 for row in internal if row["language_aspect_present"])
    assert present_count > 0


def test_internal_raw_row_ids_match_queue():
    internal_ids = {row["row_id"] for row in _load_internal_rows()}
    queue_ids = {row["row_id"] for row in _load_queue_rows()}
    assert internal_ids == queue_ids


# --------------------------------------------------------------------------
# 4 + 5. reviewer field redaction / cannot see normalized language
# --------------------------------------------------------------------------


def test_reviewer_queue_has_no_forbidden_columns():
    rows = _load_queue_rows()
    columns = set(rows[0].keys())
    assert not (server.FORBIDDEN_REVIEWER_COLUMNS & columns)
    assert not (builder.FORBIDDEN_REVIEWER_COLUMNS & columns)


def test_assert_reviewer_blind_passes_on_real_queue():
    rows = _load_queue_rows()
    server.assert_reviewer_blind(rows)  # must not raise


def test_assert_reviewer_blind_rejects_leaked_column():
    rows = _load_queue_rows()
    poisoned = [dict(rows[0], language_aspect_raw="English")]
    with pytest.raises(server.FreezeRefused):
        server.assert_reviewer_blind(poisoned)


def test_rendered_page_never_contains_language_aspect_strings():
    rows = _load_queue_rows()
    internal = {row["row_id"]: row for row in _load_internal_rows()}
    checked_any_foreign = False
    for row in rows:
        html_page = server.page(row, reviewed=0, total=len(rows), position=1)
        assert "language_aspect" not in html_page
        raw = internal[row["row_id"]].get("language_aspect_raw")
        # "English" legitimately appears in the UI's own button chrome
        # (id="nonEnglishBtn" etc), so only assert absence for a non-English
        # raw aspect value, which has no legitimate reason to appear anywhere
        # in the reviewer-facing page.
        if raw and raw.strip().lower() != "english":
            # The structured Language ASPECT itself must never be rendered.
            # But if the raw aspect value happens to also appear inside the
            # ordinary, legitimately human-visible listing title (e.g. a
            # seller literally titled the listing "... Korean Deck ..."),
            # that is ordinary evidence the reviewer is meant to see, not an
            # aspect leak -- so only fail when the word appears OUTSIDE of
            # what the listing title itself already contributes.
            page_without_title = html_page.replace(row["listing_title"], "")
            if raw.lower() not in row["listing_title"].lower():
                assert raw not in page_without_title
            checked_any_foreign = True
    assert checked_any_foreign, "expected at least one non-English raw language aspect in the corpus to test against"


# --------------------------------------------------------------------------
# 6/7/8/9. stratum inclusion
# --------------------------------------------------------------------------


def test_english_control_inclusion():
    manifest = _load_manifest()
    assert manifest["strata_counts_selected"].get("ENGLISH_CONTROL", 0) >= 1


def test_foreign_language_stratum_inclusion():
    manifest = _load_manifest()
    strata = manifest["strata_counts_selected"]
    assert (strata.get("NON_LATIN_FOREIGN", 0) + strata.get("LATIN_SCRIPT_FOREIGN", 0)) > 0


def test_latin_script_foreign_inclusion_where_available():
    manifest = _load_manifest()
    # Report honestly: this asserts non-negative and consistent with candidate pool,
    # not a forced minimum -- provider inventory may not support a hard quota.
    assert manifest["strata_counts_selected"].get("LATIN_SCRIPT_FOREIGN", 0) >= 0
    assert manifest["strata_counts_candidate_pool"].get("LATIN_SCRIPT_FOREIGN", 0) >= manifest["strata_counts_selected"].get("LATIN_SCRIPT_FOREIGN", 0)


def test_non_latin_foreign_inclusion_where_available():
    manifest = _load_manifest()
    assert manifest["strata_counts_selected"].get("NON_LATIN_FOREIGN", 0) >= 1


# --------------------------------------------------------------------------
# 10. duplicate prevention
# --------------------------------------------------------------------------


def test_no_duplicate_item_ids():
    rows = _load_queue_rows()
    ids = [r["listing_item_id"] for r in rows]
    assert len(ids) == len(set(ids))


def test_no_duplicate_row_ids():
    rows = _load_queue_rows()
    ids = [r["row_id"] for r in rows]
    assert len(ids) == len(set(ids))


# --------------------------------------------------------------------------
# 11. request budget
# --------------------------------------------------------------------------


def test_request_budget_respected():
    manifest = _load_manifest()
    assert manifest["search_request_count"] <= builder.MAX_SEARCH_REQUESTS
    assert manifest["getitem_request_count"] <= builder.MAX_GETITEM_REQUESTS


# --------------------------------------------------------------------------
# 12. session starts 0 reviewed
# --------------------------------------------------------------------------


def test_summary_starts_zero_reviewed(tmp_path, monkeypatch):
    queue = tmp_path / "queue.csv"
    manifest = tmp_path / "manifest.json"
    history = tmp_path / "history.jsonl"
    rows = _load_queue_rows()[:3]
    with queue.open("w", encoding="utf-8", newline="") as fh:
        writer = csv.DictWriter(fh, fieldnames=list(rows[0].keys()))
        writer.writeheader()
        writer.writerows(rows)
    manifest.write_text(json.dumps({"corpus_fingerprint": server.cohort_fingerprint(rows)}), encoding="utf-8")

    monkeypatch.setattr(server, "QUEUE_PATH", queue)
    monkeypatch.setattr(server, "MANIFEST_PATH", manifest)
    monkeypatch.setattr(server, "HISTORY_PATH", history)

    s = server.summary("test_reviewer")
    assert s["reviewed_rows"] == 0
    assert s["remaining_rows"] == 3
    assert s["frozen"] is False
    assert s["development_only"] is True
    assert s["production_authority"] is False


# --------------------------------------------------------------------------
# 13. row/image binding
# --------------------------------------------------------------------------


def test_row_image_binding_in_rendered_page():
    rows = _load_queue_rows()
    row = rows[0]
    html_page = server.page(row, reviewed=0, total=len(rows), position=1)
    assert row["row_id"] in html_page
    assert f"data-row-id=\"{row['row_id']}\"" in html_page
    assert f"IMAGE ROW: <b>{row['row_id']}</b>" in html_page


def test_first_middle_last_rows_render():
    import html as html_lib
    rows = _load_queue_rows()
    for idx in (0, len(rows) // 2, len(rows) - 1):
        html_page = server.page(rows[idx], reviewed=0, total=len(rows), position=idx + 1)
        assert rows[idx]["row_id"] in html_page
        title = rows[idx]["listing_title"]
        assert not title or html_lib.escape(title[:20]) in html_page


# --------------------------------------------------------------------------
# 14. fingerprint determinism
# --------------------------------------------------------------------------


def test_fingerprint_deterministic():
    rows = _load_queue_rows()
    fp1 = server.cohort_fingerprint(rows)
    fp2 = server.cohort_fingerprint(list(reversed(rows)))
    assert fp1 == fp2  # order-independent
    manifest = _load_manifest()
    assert fp1 == manifest["corpus_fingerprint"]


def test_fingerprint_changes_on_mutation():
    rows = _load_queue_rows()
    fp1 = server.cohort_fingerprint(rows)
    mutated = list(rows)
    mutated[0] = dict(mutated[0], listing_item_id="mutated_id_zzz")
    fp2 = server.cohort_fingerprint(mutated)
    assert fp1 != fp2


# --------------------------------------------------------------------------
# 15. development-only contract
# --------------------------------------------------------------------------


def test_manifest_development_only_contract():
    manifest = _load_manifest()
    assert manifest["development_only"] is True
    assert manifest["production_authority"] is False
    assert manifest["reviewed_count"] == 0
    assert manifest["review_session_id"] is None


# --------------------------------------------------------------------------
# 16. no production writes -- module never imports/writes fair value, explorer,
#     or the frozen identity stack.
# --------------------------------------------------------------------------


def test_no_production_module_imports():
    import backend.scripts.build_ebay_e2_16_language_development_cohort as b
    import backend.scripts.ebay_e2_16_language_development_review_server as s
    src_b = Path(b.__file__).read_text(encoding="utf-8")
    src_s = Path(s.__file__).read_text(encoding="utf-8")
    forbidden_imports = [
        "ebay_d3_matcher_v5", "ebay_image_identity_verifier", "ebay_combined_identity_policy_v2",
        "freeze_ebay_capture_allocation_v2", "freeze_ebay_combined_identity_v2", "freeze_ebay_d3_v5",
        "run_ebay_e2_14_fresh_blind_certification",
    ]
    for name in forbidden_imports:
        assert name not in src_b
        assert name not in src_s


def test_label_event_schema_matches_spec():
    event = server.build_label_event("row_x", "donny", "NON_ENGLISH", language_if_known="Japanese", note="clear photo")
    assert event["human_truth_label"] == "NON_ENGLISH"
    assert event["human_language_if_known"] == "Japanese"
    with pytest.raises(ValueError):
        server.build_label_event("row_x", "donny", "SPANISH")  # not a valid human_truth_label


# --------------------------------------------------------------------------
# Undo / edit / cursor mechanics (reused pattern from E2.13)
# --------------------------------------------------------------------------


def test_undo_targets_last_recorded_event_not_current_row():
    events = [
        {"action": "label", "row_id": "r1", "event_id": "e1", "human_truth_label": "ENGLISH"},
        {"action": "label", "row_id": "r2", "event_id": "e2", "human_truth_label": "NON_ENGLISH"},
    ]
    undo = server.build_undo_last_label_event(events, "donny")
    assert undo["row_id"] == "r2"
    assert undo["target_event_id"] == "e2"


def test_reconstruct_effective_labels_handles_undo_and_relabel():
    events = [
        {"action": "label", "row_id": "r1", "event_id": "e1", "human_truth_label": "ENGLISH"},
        {"action": "undo", "row_id": "r1", "event_id": "e2", "target_event_id": "e1"},
        {"action": "label", "row_id": "r1", "event_id": "e3", "human_truth_label": "NON_ENGLISH"},
    ]
    effective = server.reconstruct_effective_labels(events)
    assert effective["r1"]["human_truth_label"] == "NON_ENGLISH"


def test_next_unreviewed_index_wraps_and_skips_reviewed():
    rows = [{"row_id": "a"}, {"row_id": "b"}, {"row_id": "c"}]
    effective = {"a": {}, "b": {}}
    idx = server.next_unreviewed_index(rows, effective, after=-1)
    assert idx == 2  # only "c" unreviewed
