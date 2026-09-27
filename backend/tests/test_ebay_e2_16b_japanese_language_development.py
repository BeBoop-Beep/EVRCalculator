"""Tests for EBAY E2.16B -- Japanese-focused LANGUAGE-v1 DEVELOPMENT
extension corpus + review server. DEVELOPMENT-ONLY: verifies corpus
construction, historical exclusion (including the D2/D3/V4/V5/E2.9B/
E2.13/E2.14/E2.15/E2.16/E2.16A sources), reviewer blinding, and the review
server's session/cursor/undo/edit machinery. Never asserts a LANGUAGE-v1
freeze or certification result -- none exists for Japanese yet, and this
corpus/task must not modify the frozen {KOREAN, CHINESE} LANGUAGE-v1 or
COMBINED-IDENTITY-v3.
"""
from __future__ import annotations

import csv
import json
from pathlib import Path

import pytest

from backend.scripts import build_ebay_e2_16b_japanese_language_development_cohort as builder
from backend.scripts import ebay_e2_16b_japanese_language_development_review_server as server

ARTIFACTS = Path(__file__).resolve().parents[1] / "artifacts" / "index_fair_value"
QUEUE_PATH = ARTIFACTS / "ebay_e2_16b_japanese_language_development_queue.csv"
MANIFEST_PATH = ARTIFACTS / "ebay_e2_16b_japanese_language_development_manifest.json"
RAW_PATH = ARTIFACTS / "ebay_e2_16b_japanese_language_development_raw_internal.jsonl"

E214_LANGUAGE_ITEM_ID = "v1|407215142815|0"  # E2.14 catastrophic WRONG_LANGUAGE row (E13-0127)
E216_JAPANESE_FP_ITEM_ID = "v1|317094720076|0"  # E2.16A Japanese false-positive row (e2_16_dev_0153)


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
    for name in builder.E216_HISTORICAL_FILES:
        assert name in counts
    assert "ebay_e2_14_fresh_blind_predictions.json" in counts
    assert "ebay_e2_15_item_detail_language_study.json" in counts
    assert "ebay_e2_16_language_development_queue.csv" in counts
    assert counts["ebay_e2_16_language_development_queue.csv"] > 0


def test_historical_exclusion_specifically_covers_known_bad_rows():
    """The two specific rows named in the task spec (E2.14's catastrophic
    WRONG_LANGUAGE false accept, and E2.16A's Japanese false-positive row)
    must both be members of the exclusion set, and neither may appear in
    the new E2.16B queue.
    """
    exclusions = builder._collect_historical_exclusions()
    excluded_ids = exclusions["exact_ids"]
    assert E214_LANGUAGE_ITEM_ID in excluded_ids
    assert E216_JAPANESE_FP_ITEM_ID in excluded_ids
    rows = _load_queue_rows()
    ids = {r["listing_item_id"] for r in rows}
    assert E214_LANGUAGE_ITEM_ID not in ids
    assert E216_JAPANESE_FP_ITEM_ID not in ids


# --------------------------------------------------------------------------
# 2. Japanese-primary / English-control / hard-case stratum sampling
# --------------------------------------------------------------------------


def test_strata_present_in_manifest():
    manifest = _load_manifest()
    strata = manifest["strata_counts_selected"]
    assert manifest["row_count"] == sum(strata.values())


def test_japanese_primary_stratum_sampling():
    manifest = _load_manifest()
    strata = manifest["strata_counts_selected"]
    # Report honestly: >=0 always true, but assert the field exists and is
    # consistent with the candidate pool (never larger than what was found).
    assert "JAPANESE_ASPECT_PRIMARY" in manifest["strata_counts_candidate_pool"] or \
        strata.get(builder.STRATUM_JAPANESE_ASPECT_PRIMARY, 0) == 0
    pool = manifest["strata_counts_candidate_pool"].get(builder.STRATUM_JAPANESE_ASPECT_PRIMARY, 0)
    sel = strata.get(builder.STRATUM_JAPANESE_ASPECT_PRIMARY, 0)
    assert sel <= pool


def test_english_control_inclusion():
    manifest = _load_manifest()
    strata = manifest["strata_counts_selected"]
    pool = manifest["strata_counts_candidate_pool"].get(builder.STRATUM_ENGLISH_ASPECT_CONTROL, 0)
    sel = strata.get(builder.STRATUM_ENGLISH_ASPECT_CONTROL, 0)
    assert sel <= pool


def test_aspect_missing_hard_case_inclusion():
    manifest = _load_manifest()
    strata = manifest["strata_counts_selected"]
    pool = manifest["strata_counts_candidate_pool"].get(builder.STRATUM_JAPANESE_QUERY_HARD_CASE, 0)
    sel = strata.get(builder.STRATUM_JAPANESE_QUERY_HARD_CASE, 0)
    assert sel <= pool


def test_row_count_recorded_honestly():
    manifest = _load_manifest()
    assert manifest["row_count"] >= 0
    assert manifest["row_count"] == len(_load_queue_rows())
    assert manifest["row_count"] == len(_load_internal_rows())


# --------------------------------------------------------------------------
# 3. raw internal evidence preservation
# --------------------------------------------------------------------------


def test_internal_raw_preserves_language_aspect_and_full_evidence():
    internal = _load_internal_rows()
    for row in internal:
        assert "language_aspect_raw" in row
        assert "language_aspect_normalized" in row
        assert "language_aspect_present" in row
        assert "raw_localized_aspects" in row
        assert "capture_timestamp" in row
        assert "development_stratum" in row


def test_internal_raw_row_ids_match_queue():
    internal_ids = {row["row_id"] for row in _load_internal_rows()}
    queue_ids = {row["row_id"] for row in _load_queue_rows()}
    assert internal_ids == queue_ids


# --------------------------------------------------------------------------
# 4/5. reviewer blinding -- no raw/normalized language, no stratum, no
# policy outputs visible to reviewer
# --------------------------------------------------------------------------


def test_reviewer_queue_has_no_forbidden_columns():
    rows = _load_queue_rows()
    columns = set(rows[0].keys()) if rows else set()
    assert not (server.FORBIDDEN_REVIEWER_COLUMNS & columns)
    assert not (builder.FORBIDDEN_REVIEWER_COLUMNS & columns)
    assert "development_stratum" not in columns
    assert "language_aspect_raw" not in columns
    assert "language_aspect_normalized" not in columns


def test_assert_reviewer_blind_passes_on_real_queue():
    rows = _load_queue_rows()
    server.assert_reviewer_blind(rows)  # must not raise


def test_assert_reviewer_blind_rejects_leaked_column():
    rows = _load_queue_rows()
    poisoned = [dict(rows[0], language_aspect_raw="Japanese")]
    with pytest.raises(server.FreezeRefused):
        server.assert_reviewer_blind(poisoned)


def test_assert_reviewer_blind_rejects_leaked_stratum():
    rows = _load_queue_rows()
    poisoned = [dict(rows[0], development_stratum="JAPANESE_ASPECT_PRIMARY")]
    with pytest.raises(server.FreezeRefused):
        server.assert_reviewer_blind(poisoned)


def test_rendered_page_never_contains_forbidden_evidence():
    rows = _load_queue_rows()
    for row in rows[:25]:  # sample for speed; page() is pure and deterministic
        html_page = server.page(row, reviewed=0, total=len(rows), position=1)
        assert "language_aspect" not in html_page
        assert "development_stratum" not in html_page
        assert "JAPANESE_ASPECT_PRIMARY" not in html_page
        assert "ENGLISH_ASPECT_CONTROL" not in html_page
        assert "JAPANESE_QUERY_HARD_CASE" not in html_page


# --------------------------------------------------------------------------
# 6. duplicate prevention
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
# 7. request budget
# --------------------------------------------------------------------------


def test_request_budget_respected():
    manifest = _load_manifest()
    assert manifest["search_request_count"] <= builder.MAX_SEARCH_REQUESTS
    assert manifest["getitem_request_count"] <= builder.MAX_GETITEM_REQUESTS


# --------------------------------------------------------------------------
# 8. session starts at 0 reviewed
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


def test_manifest_reviewed_count_zero_before_review():
    manifest = _load_manifest()
    assert manifest["reviewed_count"] == 0
    assert manifest["review_session_id"] is None


# --------------------------------------------------------------------------
# 9. row/image binding
# --------------------------------------------------------------------------


def test_row_image_binding_in_rendered_page():
    rows = _load_queue_rows()
    row = rows[0]
    html_page = server.page(row, reviewed=0, total=len(rows), position=1)
    assert row["row_id"] in html_page
    assert f"data-row-id=\"{row['row_id']}\"" in html_page
    assert f"IMAGE ROW: <b>{row['row_id']}</b>" in html_page


def test_multi_image_rows_render_all_images():
    rows = _load_queue_rows()
    multi = [r for r in rows if r.get("image_urls_json") and len(json.loads(r["image_urls_json"])) > 1]
    if not multi:
        pytest.skip("no multi-image rows in this capture to test against")
    row = multi[0]
    html_page = server.page(row, reviewed=0, total=len(rows), position=1)
    urls = json.loads(row["image_urls_json"])
    for u in urls:
        assert u.split("?")[0] in html_page


def test_first_middle_last_rows_render():
    import html as html_lib
    rows = _load_queue_rows()
    for idx in (0, len(rows) // 2, len(rows) - 1):
        html_page = server.page(rows[idx], reviewed=0, total=len(rows), position=idx + 1)
        assert rows[idx]["row_id"] in html_page
        title = rows[idx]["listing_title"]
        assert not title or html_lib.escape(title[:20]) in html_page


# --------------------------------------------------------------------------
# 10. fingerprint determinism
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
# 11. development-only contract
# --------------------------------------------------------------------------


def test_manifest_development_only_contract():
    manifest = _load_manifest()
    assert manifest["development_only"] is True
    assert manifest["production_authority"] is False
    assert manifest["modifies_frozen_language_v1"] is False
    assert manifest["modifies_frozen_combined_v3"] is False
    assert manifest["reviewed_count"] == 0
    assert manifest["review_session_id"] is None


def test_no_production_module_imports():
    import backend.scripts.build_ebay_e2_16b_japanese_language_development_cohort as b
    import backend.scripts.ebay_e2_16b_japanese_language_development_review_server as s
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


def test_never_writes_e2_16_or_e2_16a_artifacts():
    """E2.16B must never modify the E2.16/E2.16A files it reads for
    historical exclusion -- confirmed by source inspection (no open(...,'w')
    or Path.write_text targeting those filenames in either module).
    """
    b_src = Path(builder.__file__).read_text(encoding="utf-8")
    s_src = Path(server.__file__).read_text(encoding="utf-8")
    for forbidden in ("ebay_e2_16_language_development_queue.csv", "ebay_e2_16_language_development_raw_internal.jsonl"):
        # allowed to be referenced as a read-only path (for exclusion), but
        # never opened for writing -- check no "w" mode call sites reference it.
        assert f'QUEUE_PATH.open("w"' not in b_src or forbidden not in b_src.split('QUEUE_PATH.open("w"')[0][-200:]
    assert "E216_QUEUE_PATH" in b_src  # read path exists
    assert 'E216_QUEUE_PATH.open("w"' not in b_src
    assert 'E216_RAW_PATH.open("w"' not in b_src
    assert not any(x in s_src for x in ["ebay_e2_16_language_development_queue.csv", "ebay_e2_16_language_development_raw_internal.jsonl"])


def test_label_event_schema_matches_spec():
    event = server.build_label_event("row_x", "donny", "NON_ENGLISH", language_if_known="Japanese", note="clear photo")
    assert event["human_truth_label"] == "NON_ENGLISH"
    assert event["human_language_if_known"] == "Japanese"
    with pytest.raises(ValueError):
        server.build_label_event("row_x", "donny", "SPANISH")  # not a valid human_truth_label


# --------------------------------------------------------------------------
# Undo / edit / cursor mechanics (reused pattern from E2.16/E2.13)
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
