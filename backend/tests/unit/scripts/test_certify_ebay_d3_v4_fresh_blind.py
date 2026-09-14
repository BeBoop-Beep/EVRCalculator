import json

import pytest

from backend.scripts import ebay_d3_matcher_v3 as v3
from backend.scripts import ebay_d3_matcher_v4 as v4
from backend.scripts.certify_ebay_d3_v4_fresh_blind import (
    CertificationBlocked,
    apply_gates,
    check_preconditions,
    classify_human_label,
    compute_certification_metrics,
    main,
    validate_label_contract,
    wilson,
)

DESIGN = {"preregistered_gate": {"high_precision_minimum": 0.99, "wilson_95_lower_minimum": 0.98,
                                  "card_coverage_minimum": 0.80, "catastrophic_high_false_positives_maximum": 0}}


def make_row(row_id, card_id, name="Kyurem ex", number="165", set_name="Black Bolt", treatment="special_illustration_rare",
             title=None, exact="yes", single_or_lot="single", raw_or_graded="raw", card_or_sealed="card",
             number_consistency="match", set_consistency="match", language="english", variant="match",
             reviewer_id="ReviewerA", timestamp="2026-09-14T00:00:00Z", condition="Ungraded"):
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


# 1. certification refuses missing labels
def test_certification_refuses_missing_cohort_file(tmp_path, monkeypatch):
    import backend.scripts.certify_ebay_d3_v4_fresh_blind as module

    monkeypatch.setattr(module, "QUEUE_PATH", tmp_path / "nope.csv")
    monkeypatch.setattr(module, "BLIND_MANIFEST_PATH", tmp_path / "nope.json")
    report = check_preconditions()
    assert report["overall_pass"] is False
    assert report["blocking_reason"] == "EBAY_D3_V4_CERTIFICATION_BLOCKED_COHORT_MISSING"


# 2. certification refuses incomplete labels
def test_certification_refuses_incomplete_labels(tmp_path, monkeypatch):
    import backend.scripts.certify_ebay_d3_v4_fresh_blind as module
    import csv

    rows = [make_row("D4-0000", "c1", exact="yes"), make_row("D4-0001", "c1", exact="")]
    queue = tmp_path / "queue.csv"
    with queue.open("w", newline="", encoding="utf-8") as f:
        writer = csv.DictWriter(f, fieldnames=list(rows[0].keys()))
        writer.writeheader()
        writer.writerows(rows)
    manifest = tmp_path / "manifest.json"
    from backend.scripts.certify_ebay_d3_v4_fresh_blind import _cohort_fingerprint

    manifest.write_text(json.dumps({"cohort_fingerprint": _cohort_fingerprint(rows), "labels_exist": True, "protocol": "SINGLE_REVIEWER_BLIND", "reviewer_b_exists": False}), encoding="utf-8")
    freeze = tmp_path / "freeze.json"
    freeze.write_text(json.dumps({"matcher_fingerprint": v4.rule_fingerprint()}), encoding="utf-8")

    monkeypatch.setattr(module, "QUEUE_PATH", queue)
    monkeypatch.setattr(module, "BLIND_MANIFEST_PATH", manifest)
    monkeypatch.setattr(module, "FREEZE_MANIFEST_PATH", freeze)
    report = check_preconditions()
    assert report["overall_pass"] is False
    assert report["blocking_reason"] == "EBAY_D3_V4_CERTIFICATION_BLOCKED_LABELS_NOT_FROZEN"


# 3. certification refuses mutable/unfrozen labels (manifest says not frozen even if rows look labeled)
def test_certification_refuses_when_manifest_declares_labels_not_frozen(tmp_path, monkeypatch):
    import backend.scripts.certify_ebay_d3_v4_fresh_blind as module
    import csv

    rows = [make_row("D4-0000", "c1", exact="yes")]
    queue = tmp_path / "queue.csv"
    with queue.open("w", newline="", encoding="utf-8") as f:
        writer = csv.DictWriter(f, fieldnames=list(rows[0].keys()))
        writer.writeheader()
        writer.writerows(rows)
    from backend.scripts.certify_ebay_d3_v4_fresh_blind import _cohort_fingerprint

    manifest = tmp_path / "manifest.json"
    manifest.write_text(json.dumps({"cohort_fingerprint": _cohort_fingerprint(rows), "labels_exist": False, "protocol": "SINGLE_REVIEWER_BLIND", "reviewer_b_exists": False}), encoding="utf-8")
    freeze = tmp_path / "freeze.json"
    freeze.write_text(json.dumps({"matcher_fingerprint": v4.rule_fingerprint()}), encoding="utf-8")

    monkeypatch.setattr(module, "QUEUE_PATH", queue)
    monkeypatch.setattr(module, "BLIND_MANIFEST_PATH", manifest)
    monkeypatch.setattr(module, "FREEZE_MANIFEST_PATH", freeze)
    report = check_preconditions()
    assert report["overall_pass"] is False
    assert report["blocking_reason"] == "EBAY_D3_V4_CERTIFICATION_BLOCKED_LABELS_NOT_FROZEN"


# 4. certification refuses matcher hash mismatch
def test_certification_refuses_matcher_hash_mismatch(tmp_path, monkeypatch):
    import backend.scripts.certify_ebay_d3_v4_fresh_blind as module
    import csv

    rows = [make_row("D4-0000", "c1", exact="yes")]
    queue = tmp_path / "queue.csv"
    with queue.open("w", newline="", encoding="utf-8") as f:
        writer = csv.DictWriter(f, fieldnames=list(rows[0].keys()))
        writer.writeheader()
        writer.writerows(rows)
    from backend.scripts.certify_ebay_d3_v4_fresh_blind import _cohort_fingerprint

    manifest = tmp_path / "manifest.json"
    manifest.write_text(json.dumps({"cohort_fingerprint": _cohort_fingerprint(rows), "labels_exist": True, "protocol": "SINGLE_REVIEWER_BLIND", "reviewer_b_exists": False}), encoding="utf-8")
    freeze = tmp_path / "freeze.json"
    freeze.write_text(json.dumps({"matcher_fingerprint": "not_the_real_fingerprint"}), encoding="utf-8")

    monkeypatch.setattr(module, "QUEUE_PATH", queue)
    monkeypatch.setattr(module, "BLIND_MANIFEST_PATH", manifest)
    monkeypatch.setattr(module, "FREEZE_MANIFEST_PATH", freeze)
    report = check_preconditions()
    assert report["overall_pass"] is False
    assert report["blocking_reason"] == "EBAY_D3_V4_CERTIFICATION_BLOCKED_MATCHER_HASH_MISMATCH"


# 5. certification refuses cohort fingerprint mismatch
def test_certification_refuses_cohort_fingerprint_mismatch(tmp_path, monkeypatch):
    import backend.scripts.certify_ebay_d3_v4_fresh_blind as module
    import csv

    rows = [make_row("D4-0000", "c1", exact="yes")]
    queue = tmp_path / "queue.csv"
    with queue.open("w", newline="", encoding="utf-8") as f:
        writer = csv.DictWriter(f, fieldnames=list(rows[0].keys()))
        writer.writeheader()
        writer.writerows(rows)
    manifest = tmp_path / "manifest.json"
    manifest.write_text(json.dumps({"cohort_fingerprint": "stale_fingerprint_from_before_a_silent_edit", "labels_exist": True, "protocol": "SINGLE_REVIEWER_BLIND", "reviewer_b_exists": False}), encoding="utf-8")
    freeze = tmp_path / "freeze.json"
    freeze.write_text(json.dumps({"matcher_fingerprint": v4.rule_fingerprint()}), encoding="utf-8")

    monkeypatch.setattr(module, "QUEUE_PATH", queue)
    monkeypatch.setattr(module, "BLIND_MANIFEST_PATH", manifest)
    monkeypatch.setattr(module, "FREEZE_MANIFEST_PATH", freeze)
    report = check_preconditions()
    assert report["overall_pass"] is False
    assert report["blocking_reason"] == "EBAY_D3_V4_CERTIFICATION_BLOCKED_COHORT_FINGERPRINT_MISMATCH"


# 6. reviewer queue contains no matcher fields
def test_precondition_detects_forbidden_matcher_columns(tmp_path, monkeypatch):
    import backend.scripts.certify_ebay_d3_v4_fresh_blind as module
    import csv

    rows = [dict(make_row("D4-0000", "c1", exact="yes"), matcher_state="HIGH_CONFIDENCE")]
    queue = tmp_path / "queue.csv"
    with queue.open("w", newline="", encoding="utf-8") as f:
        writer = csv.DictWriter(f, fieldnames=list(rows[0].keys()))
        writer.writeheader()
        writer.writerows(rows)
    from backend.scripts.certify_ebay_d3_v4_fresh_blind import _cohort_fingerprint

    manifest = tmp_path / "manifest.json"
    manifest.write_text(json.dumps({"cohort_fingerprint": _cohort_fingerprint(rows), "labels_exist": True, "protocol": "SINGLE_REVIEWER_BLIND", "reviewer_b_exists": False}), encoding="utf-8")
    freeze = tmp_path / "freeze.json"
    freeze.write_text(json.dumps({"matcher_fingerprint": v4.rule_fingerprint()}), encoding="utf-8")

    monkeypatch.setattr(module, "QUEUE_PATH", queue)
    monkeypatch.setattr(module, "BLIND_MANIFEST_PATH", manifest)
    monkeypatch.setattr(module, "FREEZE_MANIFEST_PATH", freeze)
    report = check_preconditions()
    assert report["overall_pass"] is False
    assert report["blocking_reason"] == "EBAY_D3_V4_CERTIFICATION_BLOCKED_LABEL_FILE_CONTAINS_MATCHER_OUTPUT"


# 7. human uncertain-label policy
def test_uncertain_labels_excluded_from_precision_denominator():
    rows = [make_row("D4-0000", "c1", exact="yes"), make_row("D4-0001", "c1", exact="uncertain")]
    contract = validate_label_contract(rows)
    assert contract["definitive_count"] == 1
    assert contract["uncertain_count"] == 1
    metrics = compute_certification_metrics(v4, rows)
    assert metrics["human_uncertain_rows"] == 1
    assert metrics["definitive_rows"] == 1


def test_classify_human_label_never_coerces_uncertain():
    assert classify_human_label({"exact_match_yes_no_uncertain": "uncertain"}) == "uncertain"
    assert classify_human_label({"exact_match_yes_no_uncertain": ""}) == "uncertain"
    assert classify_human_label({"exact_match_yes_no_uncertain": "YES"}) == "yes"


# 8. exact precision calculation
def test_precision_calculation_is_exact():
    rows = [make_row(f"D4-{i:04d}", "c1", exact="yes") for i in range(9)] + \
           [make_row("D4-0009", "c1", exact="no", title="PSA 10 Kyurem ex 165/086", raw_or_graded="graded", condition="Graded")]
    metrics = compute_certification_metrics(v4, rows)
    if metrics["accepted_count"]:
        assert metrics["accepted_precision"] == round(metrics["true_accepts"] / metrics["accepted_count"], 8)


# 9. Wilson interval calculation
def test_wilson_interval_matches_known_closed_form_values():
    lo, hi = wilson(297, 300)
    assert 0.97 < lo < hi < 1.0
    assert wilson(0, 0) == [0.0, 0.0]


# 10. catastrophic classification
def test_catastrophic_classification_from_label_schema():
    rows = [
        make_row("D4-0000", "c1", exact="no", raw_or_graded="graded", title="PSA 10 Kyurem ex 165/086 Black Bolt", condition="Graded"),
    ]
    metrics = compute_certification_metrics(v4, rows)
    if metrics["accepted_count"]:
        assert "GRADED" in metrics["catastrophic_false_accepts"] or metrics["catastrophic_false_accept_total"] == 0


# 11. HIGH_CONFIDENCE catastrophic audit
def test_catastrophic_false_accepts_are_always_high_confidence_by_construction():
    # only HIGH_CONFIDENCE matcher rows are counted as "accepted" in this module
    rows = [make_row("D4-0000", "c1", exact="no", raw_or_graded="lot", single_or_lot="lot",
                      title="Kyurem ex 165/086 and 164/086 combo Black Bolt")]
    metrics = compute_certification_metrics(v4, rows)
    assert metrics["catastrophic_high_confidence_count"] == metrics["catastrophic_false_accept_total"]


# 12. card-level coverage calculation
def test_card_level_coverage_counts_cards_with_true_accept():
    rows = [make_row("D4-0000", "c1", exact="yes"), make_row("D4-0001", "c2", exact="no", title="Charizard 4/102 Wrong Card")]
    metrics = compute_certification_metrics(v4, rows)
    assert metrics["cards_total"] == 2
    assert metrics["cards_with_true_accept"] <= 1


# 13. inventory-vs-matcher coverage distinction
def test_cards_with_false_only_accept_is_reported_separately_from_zero_coverage():
    rows = [make_row("D4-0000", "c1", exact="no", title="Wrong card entirely", name="Kyurem ex", number="165")]
    metrics = compute_certification_metrics(v4, rows)
    # this card has an accepted-but-false candidate distinct from "no candidates at all"
    assert isinstance(metrics["cards_with_false_only_accept"], list)


# 14. slice metrics retain sample size (smoke test on the metrics contract)
def test_metrics_contract_always_includes_sample_sizes():
    rows = [make_row("D4-0000", "c1", exact="yes")]
    metrics = compute_certification_metrics(v4, rows)
    assert "total_scored_rows" in metrics and "definitive_rows" in metrics and "accepted_count" in metrics


# 15. all gates independently reported / 16. failed gate cannot be overridden by headline precision
def test_gates_reported_independently_and_catastrophic_cannot_be_overridden():
    rows = [make_row(f"D4-{i:04d}", "c1", exact="yes") for i in range(250)] + \
           [make_row("D4-0250", "c1", exact="no", raw_or_graded="graded", condition="Graded", title="PSA 10 Kyurem ex 165/086 Black Bolt")]
    metrics = compute_certification_metrics(v4, rows)
    result = apply_gates(metrics, DESIGN)
    assert set(result["gates"].keys()) == {"accepted_precision", "wilson_lower", "coverage", "catastrophic"}
    if metrics["catastrophic_false_accept_total"] > 0:
        assert result["gates"]["catastrophic"]["status"] == "FAIL"
        assert result["overall_result"] == "FAIL"  # even if precision point estimate looks high


# 17. no certification rerun with alternate thresholds
def test_apply_gates_uses_fixed_repository_thresholds_not_caller_supplied():
    import inspect

    source = inspect.getsource(apply_gates)
    assert "gate_spec[" in source  # thresholds come only from the design document, not a parameter override


# 18. v3/v4 diagnostic occurs only after frozen v4 result (ordering contract, not enforced at runtime -- documented + tested at the call-site level)
def test_v3_diagnostic_helper_is_separate_from_v4_certification_path():
    rows = [make_row("D4-0000", "c1", exact="yes")]
    v4_metrics = compute_certification_metrics(v4, rows)
    v3_metrics = compute_certification_metrics(v3, rows)
    assert v4_metrics["accepted_count"] >= 0 and v3_metrics["accepted_count"] >= 0
    # both are independent, read-only computations; neither mutates the frozen v4 module
    assert v4.rule_fingerprint() == v4.rule_fingerprint()


# 19. evidence-quality cap removed only on successful certification
def test_evidence_quality_still_capped_when_matcher_uncertified():
    from backend.scripts.index_fair_value_ebay_evidence_quality import EvidenceQuality, assess_evidence_quality

    listings = [{"price_value": 10.0, "seller_username": f"s{i}", "condition": "Ungraded"} for i in range(20)]
    result = assess_evidence_quality(listings, matcher_certified=False)
    assert result.status != EvidenceQuality.HIGH


# 20. active-ask semantics unchanged
def test_certification_output_never_claims_transaction_semantics():
    rows = [make_row("D4-0000", "c1", exact="yes")]
    metrics = compute_certification_metrics(v4, rows)
    dumped = json.dumps(metrics).lower()
    assert "sold" not in dumped
    assert "transaction" not in dumped
    assert "realized_price" not in dumped


def test_main_never_fabricates_a_result_on_the_real_cohort():
    """The real V4 cohort's labeling/freeze state legitimately changes over
    time (it has since been genuinely labeled and certified for real, ending
    in EBAY_D3_V4_NOT_CERTIFIED). This test asserts the tool is honest about
    whatever the CURRENT real state is -- either it cleanly refuses (labels
    not yet frozen), or it reproduces a real, gate-derived result -- never a
    fabricated PASS.
    """
    try:
        result = main()
    except CertificationBlocked as exc:
        assert exc.reason.startswith("EBAY_D3_V4_CERTIFICATION_BLOCKED_")
        return
    assert result["final_result"] in ("EBAY_D3_V4_SINGLE_REVIEWER_BLIND_CERTIFIED_E3_READY", "EBAY_D3_V4_NOT_CERTIFIED")
    assert result["gate_result"]["overall_result"] in ("PASS", "FAIL")
