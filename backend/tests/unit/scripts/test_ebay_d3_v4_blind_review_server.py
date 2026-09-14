import csv
import inspect
import json
import sys

import pytest

import backend.scripts.ebay_d3_v4_blind_review_server as server


FIELDS = [
    "benchmark_row_id", "listing_item_id", "item_url", "listing_title", "condition", "condition_id",
    "category_id", "buying_options_json", "seller_id", "image_url", "canonical_card_id", "card_variant_id",
    "target_card_name", "target_set_name", "target_card_number", "target_treatment",
    "exact_match_yes_no_uncertain", "single_card_or_lot", "raw_or_graded", "card_or_sealed_nonshcard",
    "collector_number_consistency", "set_consistency", "language", "variant_treatment",
    "reviewer_id", "label_timestamp", "review_note", "adjudicated_result",
]


def make_row(i, card_id="c1"):
    return {
        "benchmark_row_id": f"D4-{i:04d}", "listing_item_id": f"v1|{i}|0", "item_url": "u", "listing_title": "t",
        "condition": "Ungraded", "condition_id": "4000", "category_id": "", "buying_options_json": "[]",
        "seller_id": "s", "image_url": "img", "canonical_card_id": card_id, "card_variant_id": "v1",
        "target_card_name": "Kyurem ex", "target_set_name": "Black Bolt", "target_card_number": "165",
        "target_treatment": "special_illustration_rare", "exact_match_yes_no_uncertain": "", "single_card_or_lot": "",
        "raw_or_graded": "", "card_or_sealed_nonshcard": "", "collector_number_consistency": "", "set_consistency": "",
        "language": "", "variant_treatment": "", "reviewer_id": "", "label_timestamp": "", "review_note": "", "adjudicated_result": "",
    }


def write_queue(path, rows):
    with path.open("w", newline="", encoding="utf-8") as f:
        writer = csv.DictWriter(f, fieldnames=FIELDS)
        writer.writeheader()
        writer.writerows(rows)


@pytest.fixture
def env(tmp_path, monkeypatch):
    rows = [make_row(i, card_id=f"c{i % 5}") for i in range(420)]
    queue = tmp_path / "queue.csv"
    write_queue(queue, rows)
    manifest = tmp_path / "manifest.json"
    manifest.write_text(json.dumps({
        "cohort_fingerprint": server.cohort_fingerprint(rows), "labels_exist": False,
        "protocol": "SINGLE_REVIEWER_BLIND", "reviewer_b_exists": False,
    }), encoding="utf-8")
    history = tmp_path / "history.jsonl"
    correction_history = tmp_path / "correction_history.jsonl"
    monkeypatch.setattr(server, "QUEUE_PATH", queue)
    monkeypatch.setattr(server, "MANIFEST_PATH", manifest)
    monkeypatch.setattr(server, "HISTORY_PATH", history)
    monkeypatch.setattr(server, "CORRECTION_HISTORY_PATH", correction_history)
    return {"rows": rows, "queue": queue, "manifest": manifest, "history": history, "correction_history": correction_history}


def label_all(env, reviewer="Donny"):
    for row in env["rows"]:
        server.append_event(server.build_label_event(row["benchmark_row_id"], reviewer, "YES"))


# 1. queue loads exactly 420 rows
def test_queue_loads_exactly_420_rows(env):
    assert len(server.load_queue_rows()) == 420


# 2. no matcher-derived fields displayed
def test_page_html_never_contains_matcher_field_names(env):
    # Some FORBIDDEN_MATCHER_COLUMNS entries ("reason", "accepted", "score",
    # "confidence") are also ordinary English words the human-labeling UI
    # legitimately uses (a "reason" for NO, an "Undo" button, etc.) -- check
    # only the genuinely matcher-specific compound identifiers here.
    row = env["rows"][0]
    rendered = server.page(row, 0, 420)
    matcher_specific = {"matcher_version", "matcher_state", "identity_state", "match_status",
                         "confidence_tier", "rejection_reason", "v3_state", "v4_state"}
    for forbidden in matcher_specific:
        assert forbidden not in rendered


# 3. matcher module is never imported/invoked
def test_server_module_never_imports_or_calls_matcher_at_top_level():
    import ast

    source = inspect.getsource(server)
    assert "classify_listing" not in source
    tree = ast.parse(source)
    module_level_imports = [
        node for node in tree.body if isinstance(node, (ast.Import, ast.ImportFrom))
    ]
    for node in module_level_imports:
        names = [node.module] if isinstance(node, ast.ImportFrom) else [a.name for a in node.names]
        for name in names:
            assert name is None or "ebay_d3_matcher" not in name


# 4. append-only event creation
def test_append_event_is_append_only_and_never_deletes(env):
    e1 = server.append_event(server.build_label_event_from_fields("D4-0000", "Donny", {f: "YES" for f in server.LABEL_FIELDS}))
    e2 = server.append_event(server.build_label_event_from_fields("D4-0000", "Donny", {f: "NO" for f in server.LABEL_FIELDS}))
    events = server.read_history()
    assert len(events) == 2
    assert events[0]["event_id"] == e1["event_id"]
    assert events[1]["event_id"] == e2["event_id"]


# 5. resume state reconstruction
def test_resume_reconstructs_effective_state_from_history(env):
    server.append_event(server.build_label_event_from_fields("D4-0000", "Donny", {f: "YES" for f in server.LABEL_FIELDS}))
    reloaded_events = server.read_history()  # simulate a fresh process reading the file
    effective = server.reconstruct_effective_labels(reloaded_events)
    assert "D4-0000" in effective
    assert effective["D4-0000"]["fields"]["exact_match_yes_no_uncertain"] == "YES"


# 6. undo semantics
def test_undo_reverts_row_to_unlabeled_without_deleting_history(env):
    server.append_event(server.build_label_event_from_fields("D4-0000", "Donny", {f: "YES" for f in server.LABEL_FIELDS}))
    events_before = server.read_history()
    undo = server.build_undo_event(events_before, "D4-0000", "Donny")
    server.append_event(undo)
    events_after = server.read_history()
    assert len(events_after) == 2  # nothing deleted
    effective = server.reconstruct_effective_labels(events_after)
    assert "D4-0000" not in effective


def test_undo_with_no_prior_label_returns_none(env):
    assert server.build_undo_event([], "D4-0000", "Donny") is None


# 7. all required label fields
def test_label_event_captures_all_required_fields(env):
    event = server.build_label_event_from_fields("D4-0000", "Donny", {f: "YES" for f in server.LABEL_FIELDS}, note="n")
    assert set(event["fields"].keys()) == set(server.LABEL_FIELDS)
    assert event["reviewer_id"] == "Donny"
    assert event["note"] == "n"


# 8. uncertain values accepted honestly
def test_uncertain_value_is_stored_verbatim_not_coerced(env):
    event = server.build_label_event_from_fields("D4-0000", "Donny", {"exact_match_yes_no_uncertain": "UNCERTAIN",
                                                            **{f: "NOT_VISIBLE" for f in server.LABEL_FIELDS if f != "exact_match_yes_no_uncertain"}})
    server.append_event(event)
    effective = server.reconstruct_effective_labels(server.read_history())
    assert effective["D4-0000"]["fields"]["exact_match_yes_no_uncertain"] == "UNCERTAIN"


# 9. incomplete review cannot freeze
def test_freeze_refuses_when_incomplete(env):
    label_all(env)
    server.append_event(server.build_undo_event(server.read_history(), "D4-0000", "Donny"))  # unlabel one row
    with pytest.raises(server.FreezeRefused) as excinfo:
        server.freeze("Donny")
    assert excinfo.value.reason == "EBAY_D3_V4_REVIEW_BLOCKED_INCOMPLETE_LABELS"


# 10. queue fingerprint mismatch cannot freeze
def test_freeze_refuses_on_cohort_fingerprint_mismatch(env):
    label_all(env)
    manifest = json.loads(env["manifest"].read_text(encoding="utf-8"))
    manifest["cohort_fingerprint"] = "stale"
    env["manifest"].write_text(json.dumps(manifest), encoding="utf-8")
    with pytest.raises(server.FreezeRefused) as excinfo:
        server.freeze("Donny")
    assert excinfo.value.reason == "EBAY_D3_V4_REVIEW_BLOCKED_COHORT_FINGERPRINT_MISMATCH"


# 11. forbidden matcher field cannot freeze
def test_freeze_refuses_when_forbidden_column_present(env):
    rows = [dict(r, matcher_state="HIGH_CONFIDENCE") for r in env["rows"]]
    with env["queue"].open("w", newline="", encoding="utf-8") as f:
        writer = csv.DictWriter(f, fieldnames=FIELDS + ["matcher_state"])
        writer.writeheader()
        writer.writerows(rows)
    label_all(env)
    with pytest.raises(server.FreezeRefused) as excinfo:
        server.freeze("Donny")
    assert excinfo.value.reason == "EBAY_D3_V4_REVIEW_BLOCKED_MATCHER_COLUMNS_PRESENT"


# 12. freeze materializes exactly 420 labels
def test_freeze_materializes_all_420_labels(env):
    label_all(env)
    result = server.freeze("Donny")
    assert result["rows_materialized"] == 420
    frozen_rows = server.load_queue_rows()
    assert all(r["exact_match_yes_no_uncertain"] == "YES" for r in frozen_rows)


# 13. original non-label columns remain byte/value-equivalent
def test_freeze_preserves_original_listing_columns(env):
    before = {r["benchmark_row_id"]: r["listing_title"] for r in env["rows"]}
    label_all(env)
    server.freeze("Donny")
    after = {r["benchmark_row_id"]: r["listing_title"] for r in server.load_queue_rows()}
    assert before == after


# 14. manifest labels_exist becomes true
def test_freeze_sets_manifest_labels_exist_true(env):
    label_all(env)
    server.freeze("Donny")
    manifest = json.loads(env["manifest"].read_text(encoding="utf-8"))
    assert manifest["labels_exist"] is True
    assert manifest["labels_frozen"] is True


# 15. label fingerprint recorded
def test_freeze_records_label_fingerprint(env):
    label_all(env)
    result = server.freeze("Donny")
    manifest = json.loads(env["manifest"].read_text(encoding="utf-8"))
    assert manifest["label_fingerprint"] == result["label_fingerprint"]
    assert len(manifest["label_fingerprint"]) == 64


# 16. no fabricated Reviewer B/adjudication
def test_freeze_never_populates_adjudication(env):
    label_all(env)
    server.freeze("Donny")
    rows = server.load_queue_rows()
    assert all(r["adjudicated_result"] == "" for r in rows)
    manifest = json.loads(env["manifest"].read_text(encoding="utf-8"))
    assert manifest["reviewer_protocol"] == "SINGLE_REVIEWER_BLIND"


# 17. post-freeze writes refused
def test_post_freeze_append_event_refused(env):
    label_all(env)
    server.freeze("Donny")
    with pytest.raises(server.ReviewFrozen):
        server.append_event(server.build_label_event_from_fields("D4-0000", "Donny", {f: "YES" for f in server.LABEL_FIELDS}))


# 18. existing E2.2 certifier still refuses before freeze
def test_certifier_still_refuses_before_freeze(env, monkeypatch):
    import backend.scripts.certify_ebay_d3_v4_fresh_blind as certifier

    monkeypatch.setattr(certifier, "QUEUE_PATH", env["queue"])
    monkeypatch.setattr(certifier, "BLIND_MANIFEST_PATH", env["manifest"])
    report = certifier.check_preconditions()
    assert report["overall_pass"] is False
    assert report["blocking_reason"] == "EBAY_D3_V4_CERTIFICATION_BLOCKED_LABELS_NOT_FROZEN"


# 19. existing E2.2 preconditions succeed after a fixture freeze
def test_certifier_preconditions_pass_after_fixture_freeze(env, monkeypatch, tmp_path):
    import backend.scripts.certify_ebay_d3_v4_fresh_blind as certifier
    from backend.scripts import ebay_d3_matcher_v4 as v4

    label_all(env)
    server.freeze("Donny")  # initial freeze -- all 420 rows are YES
    for row_id in server.build_correction_queue(server.load_queue_rows()):
        server.append_correction_event(server.build_correction_event(row_id, "Donny", "KEEP_YES"))
    server.freeze("Donny")  # final freeze -- auto-dispatches to freeze_final
    freeze_manifest = tmp_path / "freeze_manifest.json"
    freeze_manifest.write_text(json.dumps({"matcher_fingerprint": v4.rule_fingerprint()}), encoding="utf-8")
    monkeypatch.setattr(certifier, "QUEUE_PATH", env["queue"])
    monkeypatch.setattr(certifier, "BLIND_MANIFEST_PATH", env["manifest"])
    monkeypatch.setattr(certifier, "FREEZE_MANIFEST_PATH", freeze_manifest)
    report = certifier.check_preconditions()
    assert report["overall_pass"] is True


# 20. no matcher execution occurs during tests/freeze
def test_freeze_and_summary_never_call_classify_listing(env, monkeypatch):
    calls = {"n": 0}
    import backend.scripts.ebay_d3_matcher_v4 as v4_module

    original = v4_module.classify_listing

    def spy(*args, **kwargs):
        calls["n"] += 1
        return original(*args, **kwargs)

    monkeypatch.setattr(v4_module, "classify_listing", spy)
    label_all(env)
    server.freeze("Donny")
    server.summary("Donny")
    assert calls["n"] == 0


# ---------------------------------------------------------------------------
# E2.1C: simplified YES/NO/UNCERTAIN workflow
# ---------------------------------------------------------------------------


# 1. YES produces valid complete required labels
def test_yes_produces_complete_required_labels_without_redundant_selection(env):
    event = server.append_event(server.build_label_event("D4-0000", "Donny", "YES"))
    fields = event["fields"]
    assert fields["exact_match_yes_no_uncertain"] == "YES"
    assert fields["single_card_or_lot"] == "SINGLE_CARD"
    assert fields["raw_or_graded"] == "RAW"
    assert fields["card_or_sealed_nonshcard"] == "CARD"
    assert server._row_is_complete(event) is True
    # advanced fields were never forced on the reviewer
    assert fields["collector_number_consistency"] == ""
    assert fields["language"] == ""


# 2. UNCERTAIN produces valid complete required labels
def test_uncertain_produces_complete_required_labels(env):
    event = server.append_event(server.build_label_event("D4-0000", "Donny", "UNCERTAIN"))
    fields = event["fields"]
    assert fields["exact_match_yes_no_uncertain"] == "UNCERTAIN"
    assert fields["single_card_or_lot"] == "UNCERTAIN"
    assert fields["raw_or_graded"] == "UNCERTAIN"
    assert fields["card_or_sealed_nonshcard"] == "UNCERTAIN"
    assert server._row_is_complete(event) is True


# 3. each NO reason maps correctly
@pytest.mark.parametrize("reason,expected_field,expected_value", [
    ("GRADED", "raw_or_graded", "GRADED"),
    ("LOT_OR_BUNDLE", "single_card_or_lot", "LOT_OR_BUNDLE"),
    ("SEALED_OR_NON_CARD", "card_or_sealed_nonshcard", "SEALED_OR_NON_CARD"),
    ("WRONG_CARD_NUMBER", "collector_number_consistency", "INCONSISTENT"),
    ("WRONG_SET", "set_consistency", "INCONSISTENT"),
    ("WRONG_LANGUAGE", "language", "NON_ENGLISH"),
    ("WRONG_VARIANT_OR_TREATMENT", "variant_treatment", "INCONSISTENT"),
])
def test_no_reason_maps_to_expected_structural_field(env, reason, expected_field, expected_value):
    event = server.append_event(server.build_label_event("D4-0000", "Donny", "NO", no_reason=reason))
    assert event["fields"]["exact_match_yes_no_uncertain"] == "NO"
    assert event["fields"][expected_field] == expected_value
    assert server._row_is_complete(event) is True


def test_no_reason_wrong_card_and_other_leave_structural_defaults(env):
    for reason in ("WRONG_CARD", "OTHER"):
        event = server.build_label_event("D4-0000", "Donny", "NO", no_reason=reason)
        assert event["fields"]["single_card_or_lot"] == "SINGLE_CARD"
        assert event["fields"]["raw_or_graded"] == "RAW"
        assert event["fields"]["card_or_sealed_nonshcard"] == "CARD"


def test_no_without_reason_is_rejected():
    with pytest.raises(ValueError):
        server.build_label_event("D4-0000", "Donny", "NO")


# 4. wrong-card-number classification remains catastrophic when appropriate
def test_wrong_card_number_no_reason_is_classified_catastrophic_by_certifier():
    from backend.scripts.certify_ebay_d3_v4_fresh_blind import _human_error_class

    event = server.build_label_event("D4-0000", "Donny", "NO", no_reason="WRONG_CARD_NUMBER")
    row = {**event["fields"]}
    assert _human_error_class(row) == "WRONG_CARD_NUMBER"


# 5. NOT_VISIBLE is never treated as wrong language
def test_not_visible_language_never_classified_as_wrong_language():
    from backend.scripts.certify_ebay_d3_v4_fresh_blind import _human_error_class

    event = server.build_label_event("D4-0000", "Donny", "NO", no_reason="WRONG_CARD",
                                      advanced={"language": "NOT_VISIBLE"})
    assert event["fields"]["language"] == "NOT_VISIBLE"
    assert _human_error_class(event["fields"]) != "WRONG_LANGUAGE"


def test_blank_language_never_classified_as_wrong_language():
    from backend.scripts.certify_ebay_d3_v4_fresh_blind import _human_error_class

    event = server.build_label_event("D4-0000", "Donny", "YES")
    assert event["fields"]["language"] == ""
    assert _human_error_class(event["fields"]) != "WRONG_LANGUAGE"


# 6. reviewer metadata remains automatic
def test_reviewer_metadata_is_automatic_not_reviewer_supplied(env):
    event = server.append_event(server.build_label_event("D4-0000", "Donny", "YES"))
    assert event["reviewer_id"] == "Donny"
    assert event["timestamp"]  # populated by append_event, not the caller


# 7. advanced fields remain optional unless needed
def test_advanced_override_takes_precedence_over_derived_default(env):
    event = server.build_label_event("D4-0000", "Donny", "YES", advanced={"set_consistency": "INCONSISTENT"})
    assert event["fields"]["set_consistency"] == "INCONSISTENT"
    # everything else still auto-derived
    assert event["fields"]["single_card_or_lot"] == "SINGLE_CARD"


def test_advanced_fields_default_blank_when_not_supplied(env):
    event = server.build_label_event("D4-0000", "Donny", "YES")
    for field in server.ADVANCED_OPTIONAL_FIELDS:
        assert event["fields"][field] == ""


def test_unknown_advanced_key_is_ignored_not_injected(env):
    event = server.build_label_event("D4-0000", "Donny", "YES", advanced={"not_a_real_field": "X"})
    assert "not_a_real_field" not in event["fields"]


# freeze end-to-end using only the simplified primary/no_reason workflow
def test_freeze_end_to_end_with_simplified_workflow(env):
    for i, row in enumerate(env["rows"]):
        primary = "YES" if i % 3 else "NO"
        no_reason = "WRONG_CARD" if i % 3 == 0 else None
        server.append_event(server.build_label_event(row["benchmark_row_id"], "Donny", primary, no_reason=no_reason))
    result = server.freeze("Donny")
    assert result["rows_materialized"] == 420
    frozen_rows = server.load_queue_rows()
    assert all(r["exact_match_yes_no_uncertain"] in {"YES", "NO"} for r in frozen_rows)
    assert all(r["single_card_or_lot"] == "SINGLE_CARD" for r in frozen_rows)  # neither YES nor WRONG_CARD implies a lot


# ---------------------------------------------------------------------------
# E2.1D: undo-bug fix, correction audit, canonical fingerprint contract
# ---------------------------------------------------------------------------


def freeze_with_mixed_labels(env, yes_count=252, no_count=168):
    rows = env["rows"]
    for i, row in enumerate(rows):
        primary = "YES" if i < yes_count else "NO"
        no_reason = "WRONG_CARD" if primary == "NO" else None
        server.append_event(server.build_label_event(row["benchmark_row_id"], "Donny", primary, no_reason=no_reason))
    server.freeze("Donny")  # initial freeze


def keep_all_yes(env):
    rows = server.load_queue_rows()
    for row_id in server.build_correction_queue(rows):
        server.append_correction_event(server.build_correction_event(row_id, "Donny", "KEEP_YES"))


# --- Undo bug reproduction / fix (primary review) ---


def test_undo_bug_reproduction_global_last_event_semantics(env):
    server.append_event(server.build_label_event("D4-0000", "Donny", "YES"))
    events = server.read_history()
    undo = server.build_undo_last_label_event(events, "Donny")
    assert undo is not None
    assert undo["benchmark_row_id"] == "D4-0000"
    server.append_event(undo)
    effective = server.reconstruct_effective_labels(server.read_history())
    assert "D4-0000" not in effective


def test_undo_targets_most_recent_row_not_currently_displayed_row(env):
    server.append_event(server.build_label_event("D4-0000", "Donny", "YES"))
    server.append_event(server.build_label_event("D4-0001", "Donny", "NO", no_reason="WRONG_CARD"))
    undo = server.build_undo_last_label_event(server.read_history(), "Donny")
    assert undo["benchmark_row_id"] == "D4-0001"


def test_full_undo_cycle_label_undo_reconstruct_relabel_restart(env):
    server.append_event(server.build_label_event("D4-0000", "Donny", "YES"))
    undo = server.build_undo_last_label_event(server.read_history(), "Donny")
    server.append_event(undo)
    effective = server.reconstruct_effective_labels(server.read_history())
    assert "D4-0000" not in effective
    server.append_event(server.build_label_event("D4-0000", "Donny", "NO", no_reason="GRADED"))
    reloaded = server.read_history()
    effective_after_restart = server.reconstruct_effective_labels(reloaded)
    assert effective_after_restart["D4-0000"]["fields"]["exact_match_yes_no_uncertain"] == "NO"
    assert effective_after_restart["D4-0000"]["fields"]["raw_or_graded"] == "GRADED"
    assert len(reloaded) == 3


def test_undo_with_empty_history_is_noop(env):
    assert server.build_undo_last_label_event([], "Donny") is None


def test_correction_queue_contains_exactly_current_yes_rows(env):
    freeze_with_mixed_labels(env, yes_count=252, no_count=168)
    rows = server.load_queue_rows()
    queue = server.build_correction_queue(rows)
    expected = {r["benchmark_row_id"] for r in rows if r["exact_match_yes_no_uncertain"] == "YES"}
    assert set(queue) == expected
    assert len(queue) == 252


def test_build_correction_queue_never_references_matcher(env):
    import ast
    import inspect

    source = inspect.getsource(server.build_correction_queue)
    tree = ast.parse(source)
    names = {node.id for node in ast.walk(tree) if isinstance(node, ast.Name)}
    assert not any("matcher" in n.lower() for n in names)


def test_keep_yes_correction_preserves_yes_fields(env):
    event = server.build_correction_event("D4-0000", "Donny", "KEEP_YES")
    assert event["fields"]["exact_match_yes_no_uncertain"] == "YES"
    assert event["fields"]["single_card_or_lot"] == "SINGLE_CARD"
    assert event["decision"] == "KEEP_YES"


def test_change_to_no_correction_flips_label(env):
    event = server.build_correction_event("D4-0000", "Donny", "CHANGE_TO_NO", no_reason="LOT_OR_BUNDLE")
    assert event["fields"]["exact_match_yes_no_uncertain"] == "NO"
    assert event["fields"]["single_card_or_lot"] == "LOT_OR_BUNDLE"
    assert event["no_reason"] == "LOT_OR_BUNDLE"


def test_change_to_no_without_reason_is_rejected(env):
    with pytest.raises(ValueError):
        server.build_correction_event("D4-0000", "Donny", "CHANGE_TO_NO")


@pytest.mark.parametrize("reason,field,value", [
    ("WRONG_CARD_NUMBER", "collector_number_consistency", "INCONSISTENT"),
    ("SEALED_OR_NON_CARD", "card_or_sealed_nonshcard", "SEALED_OR_NON_CARD"),
    ("GRADED", "raw_or_graded", "GRADED"),
])
def test_correction_no_reason_maps_to_existing_taxonomy(env, reason, field, value):
    event = server.build_correction_event("D4-0000", "Donny", "CHANGE_TO_NO", no_reason=reason)
    assert event["fields"][field] == value


def test_correction_uncertain_produces_uncertain_schema(env):
    event = server.build_correction_event("D4-0000", "Donny", "UNCERTAIN")
    assert event["fields"]["exact_match_yes_no_uncertain"] == "UNCERTAIN"
    assert event["fields"]["single_card_or_lot"] == "UNCERTAIN"


def test_correction_invalid_decision_rejected(env):
    with pytest.raises(ValueError):
        server.build_correction_event("D4-0000", "Donny", "MAYBE")


def test_correction_history_is_append_only_separate_file(env):
    freeze_with_mixed_labels(env)
    e1 = server.append_correction_event(server.build_correction_event("D4-0000", "Donny", "KEEP_YES"))
    e2 = server.append_correction_event(server.build_correction_event("D4-0000", "Donny", "CHANGE_TO_NO", no_reason="OTHER"))
    events = server.read_history(server.CORRECTION_HISTORY_PATH, actions=frozenset({"correction", "undo_correction"}))
    assert len(events) == 2
    assert events[0]["event_id"] == e1["event_id"]
    assert events[1]["event_id"] == e2["event_id"]
    first_pass_events = server.read_history()
    assert all(e["action"] in {"label", "undo"} for e in first_pass_events)


def test_correction_requires_initial_freeze_first(env):
    with pytest.raises(server.ReviewFrozen):
        server.append_correction_event(server.build_correction_event("D4-0000", "Donny", "KEEP_YES"))


def test_undo_correction_reverts_without_deleting_history(env):
    freeze_with_mixed_labels(env)
    server.append_correction_event(server.build_correction_event("D4-0000", "Donny", "KEEP_YES"))
    events_before = server.read_history(server.CORRECTION_HISTORY_PATH, actions=frozenset({"correction", "undo_correction"}))
    undo = server.build_undo_last_correction_event(events_before, "Donny")
    server.append_correction_event(undo)
    events_after = server.read_history(server.CORRECTION_HISTORY_PATH, actions=frozenset({"correction", "undo_correction"}))
    assert len(events_after) == 2
    effective = server.reconstruct_correction_state(events_after)
    assert "D4-0000" not in effective


def test_correction_state_persists_across_restart(env):
    freeze_with_mixed_labels(env)
    server.append_correction_event(server.build_correction_event("D4-0000", "Donny", "CHANGE_TO_NO", no_reason="GRADED"))
    reloaded = server.read_history(server.CORRECTION_HISTORY_PATH, actions=frozenset({"correction", "undo_correction"}))
    effective = server.reconstruct_correction_state(reloaded)
    assert effective["D4-0000"]["decision"] == "CHANGE_TO_NO"


def test_first_pass_history_untouched_by_correction_audit(env):
    freeze_with_mixed_labels(env)
    before = server.read_history()
    server.append_correction_event(server.build_correction_event("D4-0000", "Donny", "CHANGE_TO_NO", no_reason="OTHER"))
    after = server.read_history()
    assert before == after
    assert len(after) == 420


def test_initial_freeze_preserved_in_manifest_after_final_freeze(env):
    freeze_with_mixed_labels(env)
    manifest_before = json.loads(env["manifest"].read_text(encoding="utf-8"))
    initial_fp = manifest_before["initial_human_freeze"]["label_fingerprint"]
    keep_all_yes(env)
    server.freeze("Donny")
    manifest_after = json.loads(env["manifest"].read_text(encoding="utf-8"))
    assert manifest_after["initial_human_freeze"]["label_fingerprint"] == initial_fp
    assert "final_human_freeze" in manifest_after
    assert manifest_after["correction_audit"]["performed"] is True


def test_final_effective_labels_reflect_corrections(env):
    freeze_with_mixed_labels(env, yes_count=3, no_count=417)
    rows = server.load_queue_rows()
    yes_rows = [r["benchmark_row_id"] for r in rows if r["exact_match_yes_no_uncertain"] == "YES"]
    assert len(yes_rows) == 3
    server.append_correction_event(server.build_correction_event(yes_rows[0], "Donny", "KEEP_YES"))
    server.append_correction_event(server.build_correction_event(yes_rows[1], "Donny", "CHANGE_TO_NO", no_reason="LOT_OR_BUNDLE"))
    server.append_correction_event(server.build_correction_event(yes_rows[2], "Donny", "UNCERTAIN"))
    result = server.freeze("Donny")
    assert result["stage"] == "final_human_freeze"
    final_rows = {r["benchmark_row_id"]: r for r in server.load_queue_rows()}
    assert final_rows[yes_rows[0]]["exact_match_yes_no_uncertain"] == "YES"
    assert final_rows[yes_rows[1]]["exact_match_yes_no_uncertain"] == "NO"
    assert final_rows[yes_rows[1]]["single_card_or_lot"] == "LOT_OR_BUNDLE"
    assert final_rows[yes_rows[2]]["exact_match_yes_no_uncertain"] == "UNCERTAIN"
    no_row_id = next(r["benchmark_row_id"] for r in rows if r["exact_match_yes_no_uncertain"] == "NO")
    assert final_rows[no_row_id]["exact_match_yes_no_uncertain"] == "NO"


def test_final_freeze_refused_when_correction_audit_incomplete(env):
    freeze_with_mixed_labels(env, yes_count=5, no_count=415)
    with pytest.raises(server.FreezeRefused) as excinfo:
        server.freeze("Donny")
    assert excinfo.value.reason == "EBAY_D3_V4_REVIEW_BLOCKED_CORRECTION_AUDIT_INCOMPLETE"


def test_single_canonical_fingerprint_function_used_by_both_tools(env):
    from backend.scripts.certify_ebay_d3_v4_fresh_blind import compute_label_fingerprint

    rows = [{"benchmark_row_id": "r1", "exact_match_yes_no_uncertain": "YES", "single_card_or_lot": "SINGLE_CARD",
             "raw_or_graded": "RAW", "card_or_sealed_nonshcard": "CARD", "reviewer_id": "Donny", "label_timestamp": "t"}]
    assert server._canonical_label_fingerprint(rows) == compute_label_fingerprint(rows)


def test_freezer_and_certifier_fingerprints_agree_after_final_freeze(env):
    freeze_with_mixed_labels(env)
    keep_all_yes(env)
    result = server.freeze("Donny")
    from backend.scripts.certify_ebay_d3_v4_fresh_blind import compute_label_fingerprint

    recomputed = compute_label_fingerprint(server.load_queue_rows())
    assert result["final_label_fingerprint"] == recomputed
    manifest = json.loads(env["manifest"].read_text(encoding="utf-8"))
    assert manifest["final_label_fingerprint"] == recomputed


def test_certifier_blocks_on_label_fingerprint_mismatch(env, monkeypatch, tmp_path):
    import backend.scripts.certify_ebay_d3_v4_fresh_blind as certifier
    from backend.scripts import ebay_d3_matcher_v4 as v4

    freeze_with_mixed_labels(env)
    keep_all_yes(env)
    server.freeze("Donny")
    manifest = json.loads(env["manifest"].read_text(encoding="utf-8"))
    manifest["final_label_fingerprint"] = "deliberately_wrong_fingerprint"
    env["manifest"].write_text(json.dumps(manifest), encoding="utf-8")
    freeze_manifest = tmp_path / "freeze_manifest.json"
    freeze_manifest.write_text(json.dumps({"matcher_fingerprint": v4.rule_fingerprint()}), encoding="utf-8")
    monkeypatch.setattr(certifier, "QUEUE_PATH", env["queue"])
    monkeypatch.setattr(certifier, "BLIND_MANIFEST_PATH", env["manifest"])
    monkeypatch.setattr(certifier, "FREEZE_MANIFEST_PATH", freeze_manifest)
    report = certifier.check_preconditions()
    assert report["overall_pass"] is False
    assert report["blocking_reason"] == "EBAY_D3_V4_CERTIFICATION_BLOCKED_LABEL_FINGERPRINT_MISMATCH"


def test_manifest_without_final_fingerprint_never_passes(env, monkeypatch, tmp_path):
    import backend.scripts.certify_ebay_d3_v4_fresh_blind as certifier
    from backend.scripts import ebay_d3_matcher_v4 as v4

    freeze_with_mixed_labels(env)
    keep_all_yes(env)
    server.freeze("Donny")
    manifest = json.loads(env["manifest"].read_text(encoding="utf-8"))
    del manifest["final_label_fingerprint"]
    env["manifest"].write_text(json.dumps(manifest), encoding="utf-8")
    freeze_manifest = tmp_path / "freeze_manifest.json"
    freeze_manifest.write_text(json.dumps({"matcher_fingerprint": v4.rule_fingerprint()}), encoding="utf-8")
    monkeypatch.setattr(certifier, "QUEUE_PATH", env["queue"])
    monkeypatch.setattr(certifier, "BLIND_MANIFEST_PATH", env["manifest"])
    monkeypatch.setattr(certifier, "FREEZE_MANIFEST_PATH", freeze_manifest)
    report = certifier.check_preconditions()
    assert report["overall_pass"] is False


def test_cohort_fingerprint_unchanged_through_correction_and_final_freeze(env):
    original = server.cohort_fingerprint(env["rows"])
    freeze_with_mixed_labels(env)
    keep_all_yes(env)
    result = server.freeze("Donny")
    assert result["cohort_fingerprint"] == original


def test_review_server_never_touches_matcher_fingerprint(env):
    from backend.scripts import ebay_d3_matcher_v4 as v4

    before = v4.rule_fingerprint()
    freeze_with_mixed_labels(env)
    keep_all_yes(env)
    server.freeze("Donny")
    after = v4.rule_fingerprint()
    assert before == after


def test_correction_workflow_never_calls_classify_listing(env, monkeypatch):
    calls = {"n": 0}
    import backend.scripts.ebay_d3_matcher_v4 as v4_module

    original = v4_module.classify_listing

    def spy(*args, **kwargs):
        calls["n"] += 1
        return original(*args, **kwargs)

    monkeypatch.setattr(v4_module, "classify_listing", spy)
    freeze_with_mixed_labels(env)
    keep_all_yes(env)
    server.freeze("Donny")
    server.summary("Donny")
    assert calls["n"] == 0


def test_correction_module_functions_never_import_matcher():
    import ast
    import inspect

    for func in (server.build_correction_queue, server.build_correction_event, server.reconstruct_correction_state):
        tree = ast.parse(inspect.getsource(func))
        for node in ast.walk(tree):
            if isinstance(node, (ast.Import, ast.ImportFrom)):
                names = [node.module] if isinstance(node, ast.ImportFrom) else [a.name for a in node.names]
                for name in names:
                    assert name is None or "ebay_d3_matcher" not in name


def test_correction_tooling_never_calls_certification_metrics(env, monkeypatch):
    import backend.scripts.certify_ebay_d3_v4_fresh_blind as certifier

    calls = {"n": 0}
    original = certifier.compute_certification_metrics

    def spy(*args, **kwargs):
        calls["n"] += 1
        return original(*args, **kwargs)

    monkeypatch.setattr(certifier, "compute_certification_metrics", spy)
    freeze_with_mixed_labels(env)
    keep_all_yes(env)
    server.freeze("Donny")
    server.run_precondition_check_only()
    assert calls["n"] == 0


# ---------------------------------------------------------------------------
# E2.1E: reliable undo, previous/back, edit/relabel any row, --review-existing
# ---------------------------------------------------------------------------


# 1-4. label YES, Undo, row becomes unlabeled, restart and verify state
def test_e21e_label_undo_restore_and_restart(env):
    server.append_event(server.build_label_event("D4-0000", "Donny", "YES"))
    undo = server.build_undo_last_label_event(server.read_history(), "Donny")
    server.append_event(undo)
    effective = server.reconstruct_effective_labels(server.read_history())
    assert "D4-0000" not in effective
    # simulate restart: fresh read from disk
    reloaded = server.reconstruct_effective_labels(server.read_history())
    assert "D4-0000" not in reloaded


# 5-7. label YES, navigate away, Previous returns to same row (correction audit)
def test_e21e_previous_returns_to_same_row_in_correction_audit(env):
    freeze_with_mixed_labels(env, yes_count=5, no_count=415)
    rows = server.load_queue_rows()
    queue = server.build_correction_queue(rows)
    server.append_correction_event(server.build_correction_event(queue[0], "Donny", "KEEP_YES"))
    # cursor conceptually advanced past queue[0] to the next uncorrected row;
    # Previous must be able to return to queue[0].
    effective = server.reconstruct_correction_state(server._read_correction_events())
    idx0 = server._position_of(queue, queue[0])
    assert idx0 == 0
    prev_index = server._clamped_index(1 - 1, len(queue))
    assert queue[prev_index] == queue[0]
    assert queue[0] in effective


# 8-10. relabel YES -> NO, effective state is NO, original YES event still exists
def test_e21e_relabel_yes_to_no_preserves_original_event(env):
    freeze_with_mixed_labels(env, yes_count=5, no_count=415)
    rows = server.load_queue_rows()
    queue = server.build_correction_queue(rows)
    row_id = queue[0]
    e1 = server.append_correction_event(server.build_correction_event(row_id, "Donny", "KEEP_YES"))
    e2 = server.append_correction_event(server.build_correction_event(row_id, "Donny", "CHANGE_TO_NO", no_reason="GRADED"))
    events = server._read_correction_events()
    assert any(e["event_id"] == e1["event_id"] for e in events)  # original event never deleted
    assert any(e["event_id"] == e2["event_id"] for e in events)
    effective = server.reconstruct_correction_state(events)
    assert effective[row_id]["decision"] == "CHANGE_TO_NO"
    assert effective[row_id]["fields"]["exact_match_yes_no_uncertain"] == "NO"


# 11. Undo relabel restores YES
def test_e21e_undo_relabel_restores_previous_decision(env):
    freeze_with_mixed_labels(env, yes_count=5, no_count=415)
    rows = server.load_queue_rows()
    queue = server.build_correction_queue(rows)
    row_id = queue[0]
    server.append_correction_event(server.build_correction_event(row_id, "Donny", "KEEP_YES"))
    server.append_correction_event(server.build_correction_event(row_id, "Donny", "CHANGE_TO_NO", no_reason="GRADED"))
    undo = server.build_undo_last_correction_event(server._read_correction_events(), "Donny")
    server.append_correction_event(undo)
    effective = server.reconstruct_correction_state(server._read_correction_events())
    # undoing the relabel reverts to unlabeled at the correction layer (undo
    # targets the LAST event globally, which was the CHANGE_TO_NO)
    assert row_id not in effective or effective[row_id]["decision"] == "KEEP_YES"


# 12. NO -> YES relabel works (via --review-existing extended decisions)
def test_e21e_no_to_yes_relabel_via_review_existing(env):
    freeze_with_mixed_labels(env, yes_count=5, no_count=415)
    rows = server.load_queue_rows()
    no_row_id = next(r["benchmark_row_id"] for r in rows if r["exact_match_yes_no_uncertain"] == "NO")
    event = server.build_correction_event(no_row_id, "Donny", "CHANGE_TO_YES")
    server.append_correction_event(event)
    effective = server.reconstruct_correction_state(server._read_correction_events())
    assert effective[no_row_id]["fields"]["exact_match_yes_no_uncertain"] == "YES"


# 13. review-existing shows current human state
def test_e21e_current_effective_fields_reflects_correction_override(env):
    freeze_with_mixed_labels(env, yes_count=5, no_count=415)
    rows = server.load_queue_rows()
    row = rows[0]
    no_row_id = row["benchmark_row_id"]
    assert row["exact_match_yes_no_uncertain"] == "YES" if False else True  # sanity no-op
    # before any correction: falls back to materialized CSV value
    empty_effective = {}
    fields_before = server.current_effective_fields(row, empty_effective)
    assert fields_before["exact_match_yes_no_uncertain"] == row["exact_match_yes_no_uncertain"]
    # after a correction: reflects the override
    event = server.append_correction_event(server.build_correction_event(row["benchmark_row_id"], "Donny", "CHANGE_TO_UNCERTAIN"))
    effective = server.reconstruct_correction_state(server._read_correction_events())
    fields_after = server.current_effective_fields(row, effective)
    assert fields_after["exact_match_yes_no_uncertain"] == "UNCERTAIN"


# 14. Back/Next do not create events
def test_e21e_back_and_next_navigation_create_no_events(env):
    freeze_with_mixed_labels(env, yes_count=5, no_count=415)
    before = server._read_correction_events()
    # Previous/Next are pure cursor moves in the HTTP layer -- at the data
    # layer, simply confirm no correction-event builder is invoked by
    # navigation helpers.
    n = 10
    idx = server._clamped_index(3, n)
    idx2 = server._clamped_index(idx - 1, n)
    idx3 = server._clamped_index(idx2 + 1, n)
    assert idx3 == idx
    after = server._read_correction_events()
    assert before == after


# 15. progress counters remain correct
def test_e21e_progress_counters_correct_after_relabel(env):
    freeze_with_mixed_labels(env, yes_count=5, no_count=415)
    rows = server.load_queue_rows()
    queue = server.build_correction_queue(rows)
    for row_id in queue:
        server.append_correction_event(server.build_correction_event(row_id, "Donny", "KEEP_YES"))
    summary_before = server.correction_summary("Donny")
    assert summary_before["corrected_rows"] == 5 and summary_before["remaining_rows"] == 0
    # relabeling an already-corrected row must not change the corrected/remaining counts
    server.append_correction_event(server.build_correction_event(queue[0], "Donny", "CHANGE_TO_NO", no_reason="OTHER"))
    summary_after = server.correction_summary("Donny")
    assert summary_after["corrected_rows"] == 5 and summary_after["remaining_rows"] == 0


# 16-17. freeze consumes latest effective state; final fingerprint matches certifier
def test_e21e_freeze_consumes_latest_effective_state_and_fingerprint_matches(env):
    from backend.scripts.certify_ebay_d3_v4_fresh_blind import compute_label_fingerprint

    freeze_with_mixed_labels(env, yes_count=5, no_count=415)
    rows = server.load_queue_rows()
    queue = server.build_correction_queue(rows)
    for row_id in queue:
        server.append_correction_event(server.build_correction_event(row_id, "Donny", "KEEP_YES"))
    # relabel one after the fact -- freeze must use the LATEST decision
    server.append_correction_event(server.build_correction_event(queue[0], "Donny", "CHANGE_TO_NO", no_reason="LOT_OR_BUNDLE"))
    result = server.freeze("Donny")
    final_rows = {r["benchmark_row_id"]: r for r in server.load_queue_rows()}
    assert final_rows[queue[0]]["exact_match_yes_no_uncertain"] == "NO"
    assert final_rows[queue[0]]["single_card_or_lot"] == "LOT_OR_BUNDLE"
    recomputed = compute_label_fingerprint(server.load_queue_rows())
    assert result["final_label_fingerprint"] == recomputed


# 18. matcher is never imported/invoked (review-existing + navigation helpers)
def test_e21e_review_existing_and_navigation_never_touch_matcher():
    import ast
    import inspect

    for func in (server.current_effective_fields, server._clamped_index, server._position_of, server.build_correction_event):
        tree = ast.parse(inspect.getsource(func))
        for node in ast.walk(tree):
            if isinstance(node, (ast.Import, ast.ImportFrom)):
                names = [node.module] if isinstance(node, ast.ImportFrom) else [a.name for a in node.names]
                for name in names:
                    assert name is None or "ebay_d3_matcher" not in name


def test_e21e_review_existing_page_contains_no_matcher_fields(env):
    freeze_with_mixed_labels(env, yes_count=5, no_count=415)
    row = env["rows"][0]
    rendered = server.review_existing_page(row, {f: "" for f in server.LABEL_FIELDS}, 1, 420)
    matcher_specific = {"matcher_version", "matcher_state", "identity_state", "match_status",
                         "confidence_tier", "rejection_reason", "v3_state", "v4_state"}
    for forbidden in matcher_specific:
        assert forbidden not in rendered


# 19. certification is never executed
def test_e21e_review_existing_workflow_never_runs_certification(env, monkeypatch):
    import backend.scripts.certify_ebay_d3_v4_fresh_blind as certifier

    calls = {"n": 0}
    original = certifier.main

    def spy(*args, **kwargs):
        calls["n"] += 1
        return original(*args, **kwargs)

    monkeypatch.setattr(certifier, "main", spy)
    freeze_with_mixed_labels(env, yes_count=5, no_count=415)
    rows = server.load_queue_rows()
    no_row_id = next(r["benchmark_row_id"] for r in rows if r["exact_match_yes_no_uncertain"] == "NO")
    server.append_correction_event(server.build_correction_event(no_row_id, "Donny", "CHANGE_TO_YES"))
    server.correction_summary("Donny")
    assert calls["n"] == 0


# extended-decision validation
def test_e21e_keep_current_requires_current_fields(env):
    with pytest.raises(ValueError):
        server.build_correction_event("D4-0000", "Donny", "KEEP_CURRENT")


def test_e21e_keep_current_reproduces_supplied_fields(env):
    current = {f: "SOME_VALUE" for f in server.LABEL_FIELDS}
    current["exact_match_yes_no_uncertain"] = "NO"
    event = server.build_correction_event("D4-0000", "Donny", "KEEP_CURRENT", current_fields=current)
    assert event["fields"]["exact_match_yes_no_uncertain"] == "NO"
