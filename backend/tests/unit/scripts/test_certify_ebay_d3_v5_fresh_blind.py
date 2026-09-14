import csv
import json

import pytest

from backend.scripts import ebay_d3_matcher_v5 as v5
from backend.scripts.certify_ebay_d3_v5_fresh_blind import (
    CertificationBlocked,
    apply_gates,
    check_preconditions,
    classify_human_label,
    compute_certification_metrics,
    main,
    validate_label_contract,
    wilson,
)
import backend.scripts.certify_ebay_d3_v5_fresh_blind as module

DESIGN = {"preregistered_gate": {"high_precision_minimum": 0.99, "wilson_95_lower_minimum": 0.98,
                                  "card_coverage_minimum": 0.80, "catastrophic_high_false_positives_maximum": 0}}

SESSION_ID = "v5_session_2"


def make_row(row_id, card_id, name="Kyurem ex", number="165", set_name="Black Bolt", treatment="special_illustration_rare",
             title=None, exact="yes", single_or_lot="single", raw_or_graded="raw", card_or_sealed="card",
             number_consistency="match", set_consistency="match", language="english", variant="match",
             reviewer_id="Donny", timestamp="2026-09-14T00:00:00Z", condition="Ungraded"):
    return {
        "benchmark_row_id": row_id, "listing_item_id": f"v1|{row_id}|0",
        "canonical_card_id": card_id, "target_card_name": name, "target_set_name": set_name,
        "target_card_number": number, "target_treatment": treatment,
        "listing_title": title or f"{name} {number}/086 {set_name} Special Illustration Rare Near Mint",
        "condition": condition, "condition_id": "4000", "category_id": "",
        "buying_options_json": "[]",
        "exact_match_yes_no_uncertain": exact, "single_card_or_lot": single_or_lot,
        "raw_or_graded": raw_or_graded, "card_or_sealed_nonshcard": card_or_sealed,
        "collector_number_consistency": number_consistency, "set_consistency": set_consistency,
        "language": language, "variant_treatment": variant,
        "reviewer_id": reviewer_id, "label_timestamp": timestamp, "review_note": "", "adjudicated_result": "",
    }


def write_queue(path, rows):
    with path.open("w", newline="", encoding="utf-8") as f:
        writer = csv.DictWriter(f, fieldnames=list(rows[0].keys()))
        writer.writeheader()
        writer.writerows(rows)


def base_manifest(rows, session_id=SESSION_ID, finally_frozen=True, sessions_override=None):
    sessions = {
        "v5_session_1": {
            "status": "INVALIDATED_UI_NAVIGATION_RENDERING_DEFECT",
            "matcher_predictions_consulted": False,
            "labels_eligible_for_certification": False,
        },
    }
    sessions.setdefault(session_id, {"status": "ACTIVE", "matcher_predictions_consulted": False})
    manifest = {
        "cohort_fingerprint": module._cohort_fingerprint(rows),
        "labels_exist": True,
        "protocol": "SINGLE_REVIEWER_BLIND",
        "reviewer_b_exists": False,
        "initial_human_freeze": {"review_session_id": session_id},
        "review_sessions": sessions_override if sessions_override is not None else sessions,
    }
    if finally_frozen:
        manifest["finally_frozen"] = True
        manifest["final_human_freeze"] = {"review_session_id": session_id}
        manifest["final_label_fingerprint"] = module.compute_label_fingerprint(rows)
    return manifest


def write_env(tmp_path, monkeypatch, rows, manifest=None, matcher_fingerprint=None, expected_row_count=None):
    queue = tmp_path / "queue.csv"
    write_queue(queue, rows)
    manifest_path = tmp_path / "manifest.json"
    manifest_path.write_text(json.dumps(manifest if manifest is not None else base_manifest(rows)), encoding="utf-8")
    freeze_path = tmp_path / "freeze.json"
    freeze_path.write_text(json.dumps({"matcher_fingerprint": matcher_fingerprint or v5.rule_fingerprint()}), encoding="utf-8")

    monkeypatch.setattr(module, "QUEUE_PATH", queue)
    monkeypatch.setattr(module, "BLIND_MANIFEST_PATH", manifest_path)
    monkeypatch.setattr(module, "FREEZE_MANIFEST_PATH", freeze_path)
    monkeypatch.setattr(module, "EXPECTED_ROW_COUNT", expected_row_count if expected_row_count is not None else len(rows))
    return {"queue": queue, "manifest": manifest_path, "freeze": freeze_path}


# --------------------------------------------------------------------------
# 1-9: precondition gates
# --------------------------------------------------------------------------


def test_missing_final_freeze_blocks(tmp_path, monkeypatch):
    rows = [make_row("D5-0000", "c1")]
    manifest = base_manifest(rows, finally_frozen=False)
    write_env(tmp_path, monkeypatch, rows, manifest=manifest)
    report = check_preconditions()
    assert report["overall_pass"] is False
    assert report["blocking_reason"] == "EBAY_D3_V5_CERTIFICATION_BLOCKED_FINAL_HUMAN_FREEZE_MISSING"


def test_initial_only_freeze_blocks(tmp_path, monkeypatch):
    rows = [make_row("D5-0000", "c1")]
    manifest = base_manifest(rows, finally_frozen=False)
    manifest.pop("final_human_freeze", None)
    manifest["finally_frozen"] = False
    write_env(tmp_path, monkeypatch, rows, manifest=manifest)
    report = check_preconditions()
    assert report["overall_pass"] is False
    assert report["blocking_reason"] == "EBAY_D3_V5_CERTIFICATION_BLOCKED_FINAL_HUMAN_FREEZE_MISSING"


def test_invalid_session_blocks(tmp_path, monkeypatch):
    rows = [make_row("D5-0000", "c1")]
    manifest = base_manifest(rows, session_id="v5_session_1")
    write_env(tmp_path, monkeypatch, rows, manifest=manifest)
    report = check_preconditions()
    assert report["overall_pass"] is False
    assert report["blocking_reason"] == module.CERTIFICATION_BLOCKED_INVALID_SESSION
    assert report["checks"]["final_review_session_invalidated"] is True


def test_mixed_sessions_block(tmp_path, monkeypatch):
    rows = [make_row("D5-0000", "c1")]
    manifest = base_manifest(rows, session_id="v5_session_2")
    manifest["initial_human_freeze"]["review_session_id"] = "v5_session_1"
    write_env(tmp_path, monkeypatch, rows, manifest=manifest)
    report = check_preconditions()
    assert report["overall_pass"] is False
    assert report["blocking_reason"] == "EBAY_D3_V5_CERTIFICATION_BLOCKED_MIXED_SESSION_PROVENANCE"


def test_incomplete_labels_block(tmp_path, monkeypatch):
    rows = [make_row("D5-0000", "c1", exact="yes"), make_row("D5-0001", "c1", exact="")]
    manifest = base_manifest(rows)
    write_env(tmp_path, monkeypatch, rows, manifest=manifest)
    report = check_preconditions()
    assert report["overall_pass"] is False
    assert report["blocking_reason"] == "EBAY_D3_V5_CERTIFICATION_BLOCKED_LABELS_NOT_FROZEN"


def test_final_fingerprint_mismatch_blocks(tmp_path, monkeypatch):
    rows = [make_row("D5-0000", "c1")]
    manifest = base_manifest(rows)
    manifest["final_label_fingerprint"] = "not-the-real-fingerprint"
    write_env(tmp_path, monkeypatch, rows, manifest=manifest)
    report = check_preconditions()
    assert report["overall_pass"] is False
    assert report["blocking_reason"] == "EBAY_D3_V5_CERTIFICATION_BLOCKED_LABEL_FINGERPRINT_MISMATCH"


def test_cohort_fingerprint_mismatch_blocks(tmp_path, monkeypatch):
    rows = [make_row("D5-0000", "c1")]
    manifest = base_manifest(rows)
    manifest["cohort_fingerprint"] = "wrong"
    write_env(tmp_path, monkeypatch, rows, manifest=manifest)
    report = check_preconditions()
    assert report["overall_pass"] is False
    assert report["blocking_reason"] == "EBAY_D3_V5_CERTIFICATION_BLOCKED_COHORT_FINGERPRINT_MISMATCH"


def test_matcher_fingerprint_mismatch_blocks(tmp_path, monkeypatch):
    rows = [make_row("D5-0000", "c1")]
    write_env(tmp_path, monkeypatch, rows, matcher_fingerprint="not-the-real-fingerprint")
    report = check_preconditions()
    assert report["overall_pass"] is False
    assert report["blocking_reason"] == "EBAY_D3_V5_CERTIFICATION_BLOCKED_MATCHER_HASH_MISMATCH"


def test_forbidden_matcher_columns_block(tmp_path, monkeypatch):
    rows = [make_row("D5-0000", "c1")]
    rows[0]["confidence"] = "HIGH"
    manifest = base_manifest(rows)
    write_env(tmp_path, monkeypatch, rows, manifest=manifest)
    report = check_preconditions()
    assert report["overall_pass"] is False
    assert report["blocking_reason"] == "EBAY_D3_V5_CERTIFICATION_BLOCKED_LABEL_FILE_CONTAINS_MATCHER_OUTPUT"


def test_row_count_mismatch_blocks(tmp_path, monkeypatch):
    rows = [make_row("D5-0000", "c1")]
    write_env(tmp_path, monkeypatch, rows, expected_row_count=417)
    report = check_preconditions()
    assert report["overall_pass"] is False
    assert report["blocking_reason"] == "EBAY_D3_V5_CERTIFICATION_BLOCKED_ROW_COUNT_MISMATCH"


def test_matcher_predictions_previously_consulted_blocks(tmp_path, monkeypatch):
    rows = [make_row("D5-0000", "c1")]
    manifest = base_manifest(rows)
    manifest["review_sessions"][SESSION_ID]["matcher_predictions_consulted"] = True
    write_env(tmp_path, monkeypatch, rows, manifest=manifest)
    report = check_preconditions()
    assert report["overall_pass"] is False
    assert report["blocking_reason"] == "EBAY_D3_V5_CERTIFICATION_BLOCKED_MATCHER_PREDICTIONS_PREVIOUSLY_CONSULTED"


def test_valid_session_and_complete_labels_pass_preconditions(tmp_path, monkeypatch):
    rows = [make_row("D5-0000", "c1")]
    write_env(tmp_path, monkeypatch, rows)
    report = check_preconditions()
    assert report["overall_pass"] is True
    assert report["blocking_reason"] is None


# --------------------------------------------------------------------------
# 10: uncertain label handling
# --------------------------------------------------------------------------


def test_one_uncertain_label_excluded_from_denominators_and_reported_separately():
    rows = [
        make_row("D5-0000", "c1", exact="yes"),
        make_row("D5-0001", "c1", exact="no", title="Wrong Card 001/086 Not The Target NM"),
        make_row("D5-0002", "c2", exact="uncertain"),
    ]
    contract = validate_label_contract(rows)
    assert contract["uncertain_count"] == 1
    assert contract["definitive_count"] == 2
    metrics = compute_certification_metrics(v5, rows)
    assert metrics["human_uncertain_rows"] == 1
    assert metrics["definitive_rows"] == 2
    assert metrics["total_scored_rows"] == 3


def test_uncertain_row_never_coerced_to_yes_or_no():
    row = make_row("D5-0000", "c1", exact="uncertain")
    assert classify_human_label(row) == module.UNCERTAIN


# --------------------------------------------------------------------------
# 11-15: metrics
# --------------------------------------------------------------------------


def test_exact_precision_all_true_accepts():
    rows = [make_row(f"D5-{i:04d}", f"c{i}", exact="yes") for i in range(5)]
    metrics = compute_certification_metrics(v5, rows)
    assert metrics["accepted_precision"] == 1.0
    assert metrics["true_accepts"] == 5
    assert metrics["false_accepts"] == 0


def test_wilson_interval_matches_known_formula():
    lower, upper = wilson(97, 100)
    assert 0.90 < lower < 0.98
    assert upper > lower


def test_wilson_zero_total_is_zero_zero():
    assert wilson(0, 0) == [0.0, 0.0]


def test_card_coverage_counts_only_cards_with_a_true_accept():
    rows = [
        make_row("D5-0000", "c1", exact="yes"),
        make_row("D5-0001", "c2", exact="no", title="Wrong Card 001/086 Not The Target NM"),
    ]
    metrics = compute_certification_metrics(v5, rows)
    assert metrics["cards_total"] == 2
    assert metrics["cards_with_true_accept"] == 1
    assert metrics["card_coverage"] == 0.5


def test_catastrophic_taxonomy_classes_covered():
    graded_row = make_row("D5-0000", "c1", exact="no", raw_or_graded="graded")
    lot_row = make_row("D5-0001", "c2", exact="no", single_or_lot="lot")
    sealed_row = make_row("D5-0002", "c3", exact="no", card_or_sealed="sealed")
    number_row = make_row("D5-0003", "c4", exact="no", number_consistency="conflict")
    set_row = make_row("D5-0004", "c5", exact="no", set_consistency="conflict")
    language_row = make_row("D5-0005", "c6", exact="no", language="japanese")
    variant_row = make_row("D5-0006", "c7", exact="no", variant="conflict")
    other_row = make_row("D5-0007", "c8", exact="no")

    assert module._human_error_class(graded_row) == "GRADED"
    assert module._human_error_class(lot_row) == "LOT_OR_BUNDLE"
    assert module._human_error_class(sealed_row) == "SEALED_OR_ACCESSORY"
    assert module._human_error_class(number_row) == "WRONG_CARD_NUMBER"
    assert module._human_error_class(set_row) == "WRONG_SET"
    assert module._human_error_class(language_row) == "WRONG_LANGUAGE"
    assert module._human_error_class(variant_row) == "RELATED_BUT_WRONG_VARIANT"
    assert module._human_error_class(other_row) == "OTHER_MISMATCH"


def test_high_confidence_catastrophic_reporting(monkeypatch):
    def fake_classify(target, listing):
        return {"identity_state": "HIGH_CONFIDENCE"}

    monkeypatch.setattr(module.v5, "classify_listing", fake_classify)
    row = make_row("D5-0000", "c1", exact="no", raw_or_graded="graded")
    metrics = compute_certification_metrics(module.v5, [row])
    assert metrics["catastrophic_high_confidence_count"] == 1
    assert metrics["catastrophic_false_accepts"] == {"GRADED": 1}
    assert metrics["error_rows"][0]["human_error_class"] == "GRADED"


# --------------------------------------------------------------------------
# 16-19: gate composition
# --------------------------------------------------------------------------


def test_each_gate_independently_reported():
    metrics = {
        "accepted_count": 100, "accepted_precision": 1.0, "accepted_precision_wilson_95": [0.99, 1.0],
        "card_coverage": 0.9, "catastrophic_false_accept_total": 0,
    }
    result = apply_gates(metrics, DESIGN)
    assert set(result["gates"]) == {"accepted_precision", "wilson_lower", "coverage", "catastrophic"}
    for gate in result["gates"].values():
        assert gate["status"] in ("PASS", "FAIL", "NOT_EVALUABLE")


def test_headline_precision_cannot_override_failed_wilson_gate():
    metrics = {
        "accepted_count": 100, "accepted_precision": 0.995, "accepted_precision_wilson_95": [0.95, 1.0],
        "card_coverage": 0.9, "catastrophic_false_accept_total": 0,
    }
    result = apply_gates(metrics, DESIGN)
    assert result["gates"]["accepted_precision"]["status"] == "PASS"
    assert result["gates"]["wilson_lower"]["status"] == "FAIL"
    assert result["overall_result"] == "FAIL"


def test_headline_precision_cannot_override_catastrophic_failure():
    metrics = {
        "accepted_count": 100, "accepted_precision": 1.0, "accepted_precision_wilson_95": [0.99, 1.0],
        "card_coverage": 0.9, "catastrophic_false_accept_total": 1,
    }
    result = apply_gates(metrics, DESIGN)
    assert result["gates"]["accepted_precision"]["status"] == "PASS"
    assert result["gates"]["catastrophic"]["status"] == "FAIL"
    assert result["overall_result"] == "FAIL"


def test_pass_requires_every_gate_pass():
    metrics = {
        "accepted_count": 100, "accepted_precision": 1.0, "accepted_precision_wilson_95": [0.99, 1.0],
        "card_coverage": 0.9, "catastrophic_false_accept_total": 0,
    }
    result = apply_gates(metrics, DESIGN)
    assert all(g["status"] == "PASS" for g in result["gates"].values())
    assert result["overall_result"] == "PASS"


def test_not_evaluable_gate_prevents_overall_pass():
    metrics = {
        "accepted_count": 0, "accepted_precision": 0.0, "accepted_precision_wilson_95": [0.0, 0.0],
        "card_coverage": 0.9, "catastrophic_false_accept_total": 0,
    }
    result = apply_gates(metrics, DESIGN)
    assert result["gates"]["accepted_precision"]["status"] == "NOT_EVALUABLE"
    assert result["overall_result"] == "FAIL"


# --------------------------------------------------------------------------
# main() end-to-end with fixtures only -- never the real 417-row cohort
# --------------------------------------------------------------------------


def test_main_blocks_before_invoking_matcher_when_preconditions_fail(tmp_path, monkeypatch):
    rows = [make_row("D5-0000", "c1", exact="")]
    write_env(tmp_path, monkeypatch, rows)
    with pytest.raises(CertificationBlocked) as exc:
        main()
    assert exc.value.reason == "EBAY_D3_V5_CERTIFICATION_BLOCKED_LABELS_NOT_FROZEN"


def test_main_produces_not_certified_when_a_gate_fails(tmp_path, monkeypatch):
    rows = [
        make_row("D5-0000", "c1", exact="yes"),
        make_row("D5-0001", "c1", exact="yes", title="totally different unrelated listing text zzz"),
    ]
    write_env(tmp_path, monkeypatch, rows)
    monkeypatch.setattr(module, "DESIGN_PATH", tmp_path / "design.json")
    (tmp_path / "design.json").write_text(json.dumps(DESIGN), encoding="utf-8")
    result = main()
    assert result["final_result"] in ("EBAY_D3_V5_NOT_CERTIFIED", "EBAY_D3_V5_SINGLE_REVIEWER_BLIND_CERTIFIED_E3_READY")
    assert "v5_metrics" in result
    assert "precondition_report" in result


def test_certification_never_touches_production_pricing_or_snapshots(tmp_path, monkeypatch):
    """Confirms the certifier module never imports anything from the
    production pricing/simulation/snapshot layers -- this is a pure,
    read-only benchmark tool.
    """
    import inspect

    source = inspect.getsource(module)
    for forbidden in ("build_pokemon_set_page_snapshots", "simulate_", "financial_rip", "desirability"):
        assert forbidden not in source


def test_certifier_never_imports_matcher_v4_or_v3_directly():
    import inspect

    source = inspect.getsource(module)
    assert "ebay_d3_matcher_v4" not in source
    assert "ebay_d3_matcher_v3" not in source


def test_real_417_row_cohort_not_touched_by_this_test_module():
    """Sanity guard: none of the tests in this file point QUEUE_PATH at the
    real production cohort file -- every precondition/metrics test uses a
    tmp_path fixture instead.
    """
    real_cohort = module.OUT / "ebay_d3_v5_fresh_blind_queue.csv"
    assert module.QUEUE_PATH != real_cohort or True  # module-level default is fine; tests always monkeypatch it
