import csv
import json
from collections import Counter
from pathlib import Path

from backend.scripts.build_ebay_d2f_final_certification import coverage, high_metrics, wilson

OUT = Path(__file__).resolve().parents[3] / "artifacts/index_fair_value"


def record(card, gold, state):
    return {"canonical_card_id":card, "target_card_name":card, "human_gold_label":gold, "matcher_confidence_state":state}


def test_binary_metrics_exclude_ambiguous_and_calculate_confusion_matrix():
    rows = [record("a","EXACT_TARGET_MATCH","HIGH_CONFIDENCE"), record("a","EXACT_TARGET_MATCH","REJECTED"),
            record("b","GRADED","HIGH_CONFIDENCE"), record("b","WRONG_CARD_NUMBER","REJECTED"),
            record("c","AMBIGUOUS","HIGH_CONFIDENCE")]
    found = high_metrics(rows)
    assert (found["true_positives"], found["false_positives"], found["true_negatives"], found["false_negatives"]) == (1,1,1,1)
    assert found["binary_denominator"] == 4 and found["ambiguous_excluded"] is True


def test_wilson_interval_known_perfect_sample():
    low, high = wilson(298, 298)
    assert low == 0.98727326 and high == 1.0


def test_card_coverage_categories_are_not_faked():
    rows = [record("high","EXACT_TARGET_MATCH","HIGH_CONFIDENCE"),
            record("medium","EXACT_TARGET_MATCH","MEDIUM_CONFIDENCE"),
            record("rejected","EXACT_TARGET_MATCH","REJECTED"),
            record("none","GRADED","REJECTED")]
    found = coverage(rows)
    assert found["covered_card_count"] == 1 and found["observed_benchmark_coverage"] == .25
    assert [x["canonical_card_id"] for x in found["cards_with_only_medium_exact"]] == ["medium"]
    assert [x["canonical_card_id"] for x in found["cards_with_exact_all_rejected_or_ambiguous"]] == ["rejected"]
    assert [x["canonical_card_id"] for x in found["cards_with_no_human_exact"]] == ["none"]


def test_frozen_prediction_artifact_reproduces_metrics_without_running_matcher():
    with (OUT / "ebay_d2f_final_blind_predictions.csv").open(encoding="utf-8", newline="") as handle:
        rows = list(csv.DictReader(handle))
    assert len(rows) == 350
    assert Counter(row["human_gold_label"] for row in rows) == Counter({
        "EXACT_TARGET_MATCH":221, "GRADED":58, "WRONG_CARD_NUMBER":30,
        "SEALED_OR_ACCESSORY":14, "AMBIGUOUS":11,
        "RELATED_BUT_WRONG_VARIANT":9, "LOT_OR_BUNDLE":6, "WRONG_LANGUAGE":1,
    })
    metrics = json.loads((OUT / "ebay_d2f_high_metrics.json").read_text())
    assert metrics["binary_denominator"] == 339 and metrics["ambiguous_excluded"] is True
    assert (metrics["true_positives"], metrics["false_positives"], metrics["true_negatives"], metrics["false_negatives"]) == (151, 2, 116, 70)
    assert metrics["precision_wilson_95"] == [0.95359605, 0.99640786]


def test_failed_gate_creates_no_authority_manifest():
    gate = json.loads((OUT / "ebay_d2f_catastrophic_error_gate.json").read_text())
    assert gate["counts"]["GRADED"] == 1 and gate["counts"]["LOT_OR_BUNDLE"] == 1
    assert gate["passed"] is False
    assert not (OUT / "ebay_identity_matcher_v2_authority_manifest.json").exists()
