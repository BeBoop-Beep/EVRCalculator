import html
import json

import pytest

from backend.scripts.ebay_final_gold_audit import (
    append_audit_event, audit_summary, build_audit_queue, build_audit_undo,
    effective_gold_fingerprint, effective_labels, freeze_gold,
    read_audit_history, reconstruct_audit_state,
)
from backend.scripts.ebay_gold_review_server import audit_page


def base(label):
    return {"label": label, "confidence": "HIGH"}


def test_audit_queue_membership_includes_four_labels_and_relevant_notes():
    rows = [{"benchmark_row_id": str(i)} for i in range(6)]
    labels = {str(i): base(label) for i, label in enumerate([
        "EXACT_TARGET_MATCH", "RELATED_BUT_WRONG_VARIANT", "AMBIGUOUS",
        "LOT_OR_BUNDLE", "SEALED_OR_ACCESSORY", "GRADED",
    ])}
    notes = [{"partition":"FINAL_BLIND_TEST", "reviewer_id":"Donny", "row_id":"0", "action":"note", "note":"variant unresolved"}]
    assert [r["benchmark_row_id"] for r in build_audit_queue(rows, labels, notes, "Donny")] == ["0", "1", "2", "3", "4"]


def test_audit_page_has_human_label_and_no_matcher_or_prices():
    row = {"benchmark_row_id":"1", "current_human_label":"AMBIGUOUS", "target_card_name":"A", "target_set_name":"S", "target_card_number":"1", "target_treatment":"Regular", "listing_title":"A card", "condition":"Raw", "buying_options_json":"[]", "image_url":"", "item_url":"", "price_json":"secret"}
    markup = audit_page(row, 0, 1)
    assert html.escape(row["listing_title"]) in markup and "AMBIGUOUS" in markup
    assert "matcher" not in markup.lower() and "secret" not in markup and "Fair Value" not in markup


def test_append_only_decisions_undo_and_effective_reconstruction(tmp_path):
    path = tmp_path / "audit.jsonl"
    keep = append_audit_event({"partition":"FINAL_BLIND_TEST", "reviewer_id":"Donny", "row_id":"1", "action":"audit_keep", "original_label":"AMBIGUOUS"}, path)
    append_audit_event({"partition":"FINAL_BLIND_TEST", "reviewer_id":"Donny", "row_id":"2", "action":"audit_replace", "original_label":"RELATED_BUT_WRONG_VARIANT", "replacement_label":"AMBIGUOUS", "reason":"variant unresolved"}, path)
    before = path.read_bytes()
    undo = build_audit_undo(read_audit_history(path), "Donny", ["1", "2"])
    append_audit_event(undo, path)
    assert path.read_bytes().startswith(before) and undo["reverses_action"] == "audit_replace"
    state = reconstruct_audit_state(read_audit_history(path), "Donny", ["1", "2"])
    assert set(state["decisions"]) == {"1"} and state["unreviewed"] == {"2"}
    assert keep["event_id"]


def test_locked_semantics_can_be_recorded_without_automation():
    events = [
        {"partition":"FINAL_BLIND_TEST", "reviewer_id":"Donny", "row_id":"v", "action":"audit_replace", "original_label":"RELATED_BUT_WRONG_VARIANT", "replacement_label":"AMBIGUOUS", "_event_id":"1"},
        {"partition":"FINAL_BLIND_TEST", "reviewer_id":"Donny", "row_id":"c", "action":"audit_keep", "original_label":"LOT_OR_BUNDLE", "_event_id":"2"},
        {"partition":"FINAL_BLIND_TEST", "reviewer_id":"Donny", "row_id":"a", "action":"audit_keep", "original_label":"SEALED_OR_ACCESSORY", "_event_id":"3"},
    ]
    state = reconstruct_audit_state(events, "Donny", ["v", "c", "a"])
    labels = effective_labels({"v":base("RELATED_BUT_WRONG_VARIANT"), "c":base("LOT_OR_BUNDLE"), "a":base("SEALED_OR_ACCESSORY")}, state)
    assert labels == {"v":"AMBIGUOUS", "c":"LOT_OR_BUNDLE", "a":"SEALED_OR_ACCESSORY"}


def test_gold_fingerprint_stability_and_incomplete_freeze_rejected(tmp_path):
    labels = {"2":"AMBIGUOUS", "1":"EXACT_TARGET_MATCH"}
    assert effective_gold_fingerprint(labels) == effective_gold_fingerprint(dict(reversed(list(labels.items()))))
    with pytest.raises(ValueError, match="audit is incomplete"):
        freeze_gold([{"benchmark_row_id":"1"}], {"1":base("AMBIGUOUS")}, {"decisions":{}, "unreviewed":{"1"}}, "Donny", tmp_path/"review.jsonl", tmp_path/"audit.jsonl", tmp_path/"manifest.json")


def test_no_final_blind_prediction_artifact_exists():
    from backend.scripts.ebay_gold_access import OUT
    names = [path.name.lower() for path in OUT.iterdir()]
    assert not any("final_blind" in name and ("prediction" in name or "metrics" in name) for name in names)
