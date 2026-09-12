import csv
import hashlib
import json
from pathlib import Path
import pytest
from backend.scripts.ebay_d2m_matcher import MATCHER_VERSION, rule_fingerprint
from backend.scripts.ebay_gold_access import load_partition

ROOT=Path(__file__).resolve().parents[4]
OUT=ROOT/"backend/artifacts/index_fair_value"

def load(name):
    return json.loads((OUT/name).read_text(encoding="utf-8"))

def test_exact_frozen_matcher_and_config_are_unchanged():
    assert MATCHER_VERSION=="index_fair_value_ebay_d2m_v1"
    assert rule_fingerprint()=="d47384a38912b59bb073c0b7a655e3120424154fa1617faaca541c86d53f2e1c"
    expected={
      "backend/scripts/ebay_d2m_matcher.py":"eb837398826c5aae6dbdb947e2d452c40eea6f613bac9a2705913caff243f2b8",
      "backend/artifacts/index_fair_value/ebay_set_alias_registry.json":"c1c4bcfb36b8df2f9eb920b2453b96fb18d0ef6f958f53bfaf685e3188291397",
      "backend/artifacts/index_fair_value/ebay_variant_identity_rules.json":"11eecd443a322c765fd99c3f3a423a165cf9cd95609b734a3925006dde00f431",
      "backend/artifacts/index_fair_value/ebay_matcher_confidence_rules.json":"7df108920130bc0ed22f2d0b4e748a9fdcc40ddaee76e2ff75060134e6b6a1e7",
    }
    assert {name:hashlib.sha256((ROOT/name).read_bytes()).hexdigest() for name in expected}==expected

def test_validation_predictions_are_complete_and_ambiguous_is_excluded():
    with (OUT/"ebay_d2v_validation_predictions.csv").open(encoding="utf-8",newline="") as handle:
        rows=list(csv.DictReader(handle))
    assert len(rows)==250
    assert sum(row["human_gold_label"]=="AMBIGUOUS" for row in rows)==1
    metrics=load("ebay_d2v_high_metrics.json")
    assert metrics["ambiguous_excluded"]==1
    assert metrics["true_positives"]+metrics["false_negatives"]==170
    assert metrics["true_negatives"]+metrics["false_positives"]==79

def test_wilson_coverage_and_catastrophic_gate_fail_as_preregistered():
    metrics=load("ebay_d2v_high_metrics.json")
    assert metrics["precision"]<metrics["gate"]["precision_minimum"]
    assert metrics["wilson_95"][0]<metrics["gate"]["wilson_lower_minimum"]
    assert metrics["card_coverage"]<metrics["gate"]["card_coverage_minimum"]
    assert metrics["catastrophic_error_count"]==2
    assert metrics["passed"] is False

def test_medium_remains_diagnostic_only():
    medium=load("ebay_d2v_medium_metrics.json")
    assert medium["count"]==12
    assert medium["recommendation"]=="DIAGNOSTIC_ONLY"
    assert medium["incremental_card_coverage_count"]==6

def test_validation_ambiguous_enters_blinded_second_review_queue():
    with (OUT/"ebay_d2m_second_review_queue.csv").open(encoding="utf-8",newline="") as handle:
        rows=list(csv.DictReader(handle))
    validation=[row for row in rows if row["review_reason"].startswith("VALIDATION_")]
    assert len(validation)==69
    assert sum(row["review_reason"]=="VALIDATION_HUMAN_AMBIGUOUS" for row in validation)==1
    assert all("price" not in key and "gold" not in key and "matcher_state" not in key for key in rows[0])

def test_logic_failure_does_not_create_final_freeze_manifest():
    assert not (OUT/"ebay_d2_final_matcher_freeze_manifest.json").exists()
    assert load("ebay_d2v_high_metrics.json")["decision"]=="LOGIC_FAILURE_REDEVELOPMENT_REQUIRED"

def test_final_blind_access_guard_stays_closed():
    with pytest.raises(PermissionError):
        load_partition("FINAL_BLIND_TEST")
