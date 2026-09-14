import csv
import hashlib
import json

import pytest

from backend.scripts import ebay_d3_matcher_v5 as v5
from backend.scripts import ebay_d3_v5_blind_review_server as review_server
import backend.scripts.reconcile_ebay_d3_v5_final_freeze_provenance as module
from backend.scripts.reconcile_ebay_d3_v5_final_freeze_provenance import (
    ReconciliationBlocked,
    main,
    reconcile,
)

FIELDS = [
    "benchmark_row_id", "listing_item_id", "item_url", "listing_title", "condition", "condition_id",
    "category_id", "buying_options_json", "seller_id", "image_url", "canonical_card_id", "card_variant_id",
    "target_card_name", "target_set_name", "target_card_number", "target_treatment",
    "exact_match_yes_no_uncertain", "single_card_or_lot", "raw_or_graded", "card_or_sealed_nonshcard",
    "collector_number_consistency", "set_consistency", "language", "variant_treatment",
    "reviewer_id", "label_timestamp", "review_note", "adjudicated_result",
]

N_ROWS = 417


def make_row(i):
    return {
        "benchmark_row_id": "D5-%04d" % i, "listing_item_id": "v1|%d|0" % i, "item_url": "u",
        "listing_title": "Kyurem ex 165/086 Black Bolt Special Illustration Rare NM",
        "condition": "Ungraded", "condition_id": "4000", "category_id": "", "buying_options_json": "[]",
        "seller_id": "s", "image_url": "img", "canonical_card_id": "c%d" % (i % 5), "card_variant_id": "v1",
        "target_card_name": "Kyurem ex", "target_set_name": "Black Bolt", "target_card_number": "165",
        "target_treatment": "special_illustration_rare",
        "exact_match_yes_no_uncertain": "YES", "single_card_or_lot": "SINGLE_CARD",
        "raw_or_graded": "RAW", "card_or_sealed_nonshcard": "CARD",
        "collector_number_consistency": "", "set_consistency": "", "language": "", "variant_treatment": "",
        "reviewer_id": "Donny", "label_timestamp": "2026-09-14T03:17:00+00:00", "review_note": "", "adjudicated_result": "",
    }


def write_queue(path, rows):
    with path.open("w", newline="", encoding="utf-8") as f:
        writer = csv.DictWriter(f, fieldnames=FIELDS)
        writer.writeheader()
        writer.writerows(rows)


@pytest.fixture
def env(tmp_path, monkeypatch):
    rows = [make_row(i) for i in range(N_ROWS)]
    queue = tmp_path / "queue.csv"
    write_queue(queue, rows)

    cohort_fp = review_server.cohort_fingerprint(rows)
    label_fp = module.compute_label_fingerprint(rows)

    manifest = {
        "cohort_fingerprint": cohort_fp,
        "final_label_fingerprint": label_fp,
        "protocol": "SINGLE_REVIEWER_BLIND",
        "reviewer_b_exists": False,
        "initial_human_freeze": {"review_session_id": "v5_session_2", "reviewer_id": "Donny"},
        "final_human_freeze": {"reviewer_id": "Donny", "freeze_timestamp": "2026-09-14T03:20:25+00:00"},
        "review_sessions": {
            "v5_session_1": {
                "status": "INVALIDATED_UI_NAVIGATION_RENDERING_DEFECT",
                "matcher_predictions_consulted": False,
                "labels_eligible_for_certification": False,
            },
            "v5_session_2": {
                "status": "ACTIVE",
                "matcher_predictions_consulted": False,
                "predecessor_session_id": "v5_session_1",
            },
        },
    }
    manifest_path = tmp_path / "manifest.json"
    manifest_path.write_text(json.dumps(manifest), encoding="utf-8")

    freeze_manifest_path = tmp_path / "freeze.json"
    freeze_manifest_path.write_text(json.dumps({"matcher_fingerprint": v5.rule_fingerprint()}), encoding="utf-8")

    session_history_path = tmp_path / "session2_history.jsonl"
    monkeypatch.setattr(review_server, "HISTORY_PATH", tmp_path / "legacy_history.jsonl")
    for row in rows:
        event = review_server.build_label_event(row["benchmark_row_id"], "Donny", "YES")
        review_server._append(event, session_history_path)
    monkeypatch.setattr(
        module.review_server, "session_history_path",
        lambda session_id: session_history_path if session_id == "v5_session_2" else tmp_path / "other.jsonl",
    )

    reconciliation_output = tmp_path / "reconciliation.json"
    monkeypatch.setattr(module, "QUEUE_PATH", queue)
    monkeypatch.setattr(module, "BLIND_MANIFEST_PATH", manifest_path)
    monkeypatch.setattr(module, "FREEZE_MANIFEST_PATH", freeze_manifest_path)
    monkeypatch.setattr(module, "RECONCILIATION_OUTPUT_PATH", reconciliation_output)

    return {
        "rows": rows, "queue": queue, "manifest_path": manifest_path, "manifest": manifest,
        "freeze_manifest_path": freeze_manifest_path, "reconciliation_output": reconciliation_output,
        "cohort_fp": cohort_fp, "label_fp": label_fp,
    }


# 1. valid historical-freeze reconciliation
def test_valid_reconciliation_succeeds(env):
    attestation = reconcile()
    assert attestation["valid_review_session_id"] == "v5_session_2"
    assert attestation["invalidated_predecessor_session_id"] == "v5_session_1"
    assert attestation["reviewer_id"] == "Donny"
    assert attestation["reviewer_protocol"] == "SINGLE_REVIEWER_BLIND"
    assert attestation["labels_complete"] is True
    assert attestation["matcher_predictions_consulted"] is False
    assert attestation["cohort_fingerprint"] == env["cohort_fp"]
    assert attestation["final_label_fingerprint"] == env["label_fp"]
    assert attestation["reconciliation_reason"] == module.RECONCILIATION_REASON
    assert attestation["historical_manual_backfill_detected"] is True
    assert attestation["no_label_cohort_or_matcher_mutation_performed"] is True
    assert "attestation_fingerprint" in attestation


# 2. cohort fingerprint mismatch blocks
def test_cohort_fingerprint_mismatch_blocks(env):
    manifest = json.loads(env["manifest_path"].read_text(encoding="utf-8"))
    manifest["cohort_fingerprint"] = "wrong"
    env["manifest_path"].write_text(json.dumps(manifest), encoding="utf-8")
    with pytest.raises(ReconciliationBlocked) as exc:
        reconcile()
    assert exc.value.reason == "EBAY_D3_V5_RECONCILIATION_BLOCKED_COHORT_FINGERPRINT_MISMATCH"


# 3. label fingerprint mismatch blocks
def test_label_fingerprint_mismatch_blocks(env):
    manifest = json.loads(env["manifest_path"].read_text(encoding="utf-8"))
    manifest["final_label_fingerprint"] = "wrong"
    env["manifest_path"].write_text(json.dumps(manifest), encoding="utf-8")
    with pytest.raises(ReconciliationBlocked) as exc:
        reconcile()
    assert exc.value.reason == "EBAY_D3_V5_RECONCILIATION_BLOCKED_LABEL_FINGERPRINT_MISMATCH"


# 4. wrong review session blocks (mixed session provenance)
def test_wrong_review_session_blocks(env):
    manifest = json.loads(env["manifest_path"].read_text(encoding="utf-8"))
    manifest["initial_human_freeze"]["review_session_id"] = "v5_session_1"
    env["manifest_path"].write_text(json.dumps(manifest), encoding="utf-8")
    with pytest.raises(ReconciliationBlocked) as exc:
        reconcile()
    assert exc.value.reason in (
        "EBAY_D3_V5_RECONCILIATION_BLOCKED_TRACED_SESSION_INVALIDATED",
        "EBAY_D3_V5_RECONCILIATION_BLOCKED_MIXED_SESSION_PROVENANCE",
        "EBAY_D3_V5_RECONCILIATION_BLOCKED_SESSION_DOES_NOT_RECONSTRUCT_ALL_ROWS",
    )


# 5. invalidated session cannot become authority
def test_invalidated_session_cannot_become_authority(env):
    manifest = json.loads(env["manifest_path"].read_text(encoding="utf-8"))
    manifest["review_sessions"]["v5_session_2"]["status"] = "INVALIDATED_UI_NAVIGATION_RENDERING_DEFECT"
    env["manifest_path"].write_text(json.dumps(manifest), encoding="utf-8")
    with pytest.raises(ReconciliationBlocked) as exc:
        reconcile()
    assert exc.value.reason == "EBAY_D3_V5_RECONCILIATION_BLOCKED_TRACED_SESSION_INVALIDATED"


# 6. mixed-session labels block
def test_mixed_session_labels_block(env):
    manifest = json.loads(env["manifest_path"].read_text(encoding="utf-8"))
    manifest["initial_human_freeze"]["review_session_id"] = None
    env["manifest_path"].write_text(json.dumps(manifest), encoding="utf-8")
    with pytest.raises(ReconciliationBlocked) as exc:
        reconcile()
    assert exc.value.reason == "EBAY_D3_V5_RECONCILIATION_BLOCKED_NO_TRACEABLE_SESSION_ID"


# 7. matcher-consulted flag blocks
def test_matcher_consulted_flag_blocks(env):
    manifest = json.loads(env["manifest_path"].read_text(encoding="utf-8"))
    manifest["review_sessions"]["v5_session_2"]["matcher_predictions_consulted"] = True
    env["manifest_path"].write_text(json.dumps(manifest), encoding="utf-8")
    with pytest.raises(ReconciliationBlocked) as exc:
        reconcile()
    assert exc.value.reason == "EBAY_D3_V5_RECONCILIATION_BLOCKED_MATCHER_PREDICTIONS_CONSULTED"


# 8. matcher fingerprint mismatch blocks
def test_matcher_fingerprint_mismatch_blocks(env):
    env["freeze_manifest_path"].write_text(json.dumps({"matcher_fingerprint": "wrong"}), encoding="utf-8")
    with pytest.raises(ReconciliationBlocked) as exc:
        reconcile()
    assert exc.value.reason == "EBAY_D3_V5_RECONCILIATION_BLOCKED_MATCHER_HASH_MISMATCH"


# 9. incomplete labels block
def test_incomplete_labels_block(env):
    rows = env["rows"]
    rows_copy = [dict(r) for r in rows]
    rows_copy[0]["reviewer_id"] = ""
    write_queue(env["queue"], rows_copy)
    with pytest.raises(ReconciliationBlocked) as exc:
        reconcile()
    assert exc.value.reason == "EBAY_D3_V5_RECONCILIATION_BLOCKED_INCOMPLETE_LABELS"


def test_forbidden_matcher_columns_block(env):
    rows = env["rows"]
    rows_copy = [dict(r, confidence="HIGH" if i == 0 else "") for i, r in enumerate(rows)]
    with (env["queue"]).open("w", newline="", encoding="utf-8") as f:
        writer = csv.DictWriter(f, fieldnames=FIELDS + ["confidence"])
        writer.writeheader()
        writer.writerows(rows_copy)
    with pytest.raises(ReconciliationBlocked) as exc:
        reconcile()
    assert exc.value.reason == "EBAY_D3_V5_RECONCILIATION_BLOCKED_LABEL_FILE_CONTAINS_MATCHER_OUTPUT"


def test_row_count_mismatch_blocks(env, tmp_path):
    write_queue(env["queue"], env["rows"][:5])
    with pytest.raises(ReconciliationBlocked) as exc:
        reconcile()
    assert exc.value.reason == "EBAY_D3_V5_RECONCILIATION_BLOCKED_ROW_COUNT_MISMATCH"


def test_predecessor_not_invalidated_blocks(env):
    manifest = json.loads(env["manifest_path"].read_text(encoding="utf-8"))
    manifest["review_sessions"]["v5_session_1"]["status"] = "ACTIVE"
    env["manifest_path"].write_text(json.dumps(manifest), encoding="utf-8")
    with pytest.raises(ReconciliationBlocked) as exc:
        reconcile()
    assert exc.value.reason == "EBAY_D3_V5_RECONCILIATION_BLOCKED_PREDECESSOR_NOT_INVALIDATED"


def test_main_writes_attestation_and_returns_it(env):
    result = main()
    assert env["reconciliation_output"].exists()
    on_disk = json.loads(env["reconciliation_output"].read_text(encoding="utf-8"))
    assert on_disk == result


# 12/13/14. reconciliation performs no mutation of queue, labels, or matcher
def test_reconciliation_does_not_modify_queue(env):
    before = env["queue"].read_bytes()
    main()
    after = env["queue"].read_bytes()
    assert before == after


def test_reconciliation_does_not_modify_labels(env):
    before_rows = json.dumps(env["rows"], sort_keys=True)
    main()
    with env["queue"].open(encoding="utf-8", newline="") as f:
        after_rows = list(csv.DictReader(f))
    assert [r["exact_match_yes_no_uncertain"] for r in after_rows] == ["YES"] * N_ROWS
    assert before_rows == json.dumps(env["rows"], sort_keys=True)


def test_reconciliation_does_not_modify_matcher(env, monkeypatch):
    calls = {"n": 0}
    real_classify = v5.classify_listing

    def spy(*args, **kwargs):
        calls["n"] += 1
        return real_classify(*args, **kwargs)

    monkeypatch.setattr(v5, "classify_listing", spy)
    main()
    assert calls["n"] == 0
