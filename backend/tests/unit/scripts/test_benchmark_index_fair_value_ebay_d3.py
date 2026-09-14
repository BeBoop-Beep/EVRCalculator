import pytest

from backend.scripts.benchmark_index_fair_value_ebay_d3 import (
    FinalBlindTuningAttempt,
    apply_acceptance_gate,
    assert_no_final_blind_tuning,
    critical_error_table,
    discover_gold_partitions,
)


# 1. gold-partition discovery
def test_gold_partition_discovery_reports_all_known_partitions():
    inventory = discover_gold_partitions()
    assert "DEVELOPMENT" in inventory
    assert "FINAL_BLIND_TEST" in inventory
    assert "PRECISION_BLIND" in inventory
    for entry in inventory.values():
        assert "row_count" in entry


# 3. no final-blind rows enter tuning path
def test_final_blind_partitions_refuse_tuning_purpose():
    with pytest.raises(FinalBlindTuningAttempt):
        assert_no_final_blind_tuning("FINAL_BLIND_TEST", "matcher_development")
    with pytest.raises(FinalBlindTuningAttempt):
        assert_no_final_blind_tuning("PRECISION_BLIND", "threshold_validation")
    assert_no_final_blind_tuning("FINAL_BLIND_TEST", "human_review")  # does not raise
    assert_no_final_blind_tuning("DEVELOPMENT", "matcher_development")  # does not raise


# 5. abstention calculation / 6. critical-error classification
def test_critical_error_table_sums_catastrophic_categories():
    final_blind = {
        "status": "AVAILABLE",
        "metrics": {
            "catastrophic_high_errors": {"GRADED": 0, "LOT_OR_BUNDLE": 2, "WRONG_CARD_NUMBER": 1},
            "coverage_cohort": {"high_count": 100},
        },
    }
    result = critical_error_table(final_blind)
    assert result["critical_false_accept_count"] == 3
    assert result["critical_false_accept_rate"] == 0.03


def test_critical_error_table_handles_missing_final_blind():
    result = critical_error_table({"status": "MISSING"})
    assert result["critical_false_accept_count"] is None


# 4. precision calculation / gate application
def test_acceptance_gate_fails_on_any_critical_false_accept():
    final_blind = {
        "status": "AVAILABLE",
        "metrics": {
            "precision_cohort": {"precision": 0.995, "wilson_95": [0.98, 0.999], "logical_rows": 300},
            "gates": {"precision": True, "wilson_lower": True, "coverage": True, "catastrophic": False},
            "overall_result": "FAIL",
        },
    }
    critical = {"critical_false_accept_count": 1}
    gate = apply_acceptance_gate(final_blind, critical)
    assert gate["gate_result"] == "FAIL"


def test_acceptance_gate_fails_below_precision_floor_even_with_zero_critical_errors():
    final_blind = {
        "status": "AVAILABLE",
        "metrics": {
            "precision_cohort": {"precision": 0.97, "wilson_95": [0.94, 0.99], "logical_rows": 300},
            "gates": {"precision": False, "wilson_lower": False, "coverage": True, "catastrophic": True},
            "overall_result": "FAIL",
        },
    }
    critical = {"critical_false_accept_count": 0}
    gate = apply_acceptance_gate(final_blind, critical)
    assert gate["gate_result"] == "FAIL"


def test_acceptance_gate_passes_only_when_everything_clears():
    final_blind = {
        "status": "AVAILABLE",
        "metrics": {
            "precision_cohort": {"precision": 0.995, "wilson_95": [0.99, 0.999], "logical_rows": 300},
            "gates": {"precision": True, "wilson_lower": True, "coverage": True, "catastrophic": True},
            "overall_result": "PASS",
        },
    }
    critical = {"critical_false_accept_count": 0}
    gate = apply_acceptance_gate(final_blind, critical)
    assert gate["gate_result"] == "PASS"
