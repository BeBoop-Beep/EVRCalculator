"""Gate F, Phase 9 - V12 budget-ranking readiness addendum tests.

This addendum is explicit-opt-in only; the existing V10
`resolve_budget_ranking_readiness` default path and its own test suite are
untouched (see test_budget_product_ranking_readiness.py, still 100% green).
"""

from __future__ import annotations

from backend.db.services.budget_product_ranking_authority import (
    EXPECTED_CHASE_ACCESSIBILITY_VERSION,
)
from backend.db.services.budget_product_ranking_readiness import (
    resolve_v12_budget_authority_readiness,
)


def _cohort(set_ids):
    return [{"set_id": s} for s in set_ids]


def _resolution(by_set):
    return {"chaseAccessibilityVersion": EXPECTED_CHASE_ACCESSIBILITY_VERSION, "bySet": by_set}


def test_exact_authority_all_sets_eligible_passes():
    by_set = {
        "set-1": {"ready": True, "version": EXPECTED_CHASE_ACCESSIBILITY_VERSION, "mappedHcMass": 1.0, "aRaw": 0.01},
        "set-2": {"ready": True, "version": EXPECTED_CHASE_ACCESSIBILITY_VERSION, "mappedHcMass": 0.995, "aRaw": 0.02},
    }
    result = resolve_v12_budget_authority_readiness(_cohort(["set-1", "set-2"]), _resolution(by_set))
    assert result["ready"] is True
    assert result["allSetsEligible"] is True
    assert sorted(result["eligibleSetIds"]) == ["set-1", "set-2"]


def test_one_set_below_mass_threshold_fails_the_whole_cohort_readiness():
    by_set = {
        "set-1": {"ready": True, "version": EXPECTED_CHASE_ACCESSIBILITY_VERSION, "mappedHcMass": 1.0, "aRaw": 0.01},
        "set-2": {"ready": True, "version": EXPECTED_CHASE_ACCESSIBILITY_VERSION, "mappedHcMass": 0.5, "aRaw": 0.02},
    }
    result = resolve_v12_budget_authority_readiness(_cohort(["set-1", "set-2"]), _resolution(by_set))
    assert result["ready"] is False
    assert result["perSet"]["set-2"]["reason"] == "insufficient_mapped_hc_mass"
    assert result["perSet"]["set-1"]["eligible"] is True


def test_mixed_authority_wrong_version_on_one_set_fails():
    by_set = {
        "set-1": {"ready": True, "version": EXPECTED_CHASE_ACCESSIBILITY_VERSION, "mappedHcMass": 1.0, "aRaw": 0.01},
        "set-2": {"ready": True, "version": "chase_accessibility_v0_legacy", "mappedHcMass": 1.0, "aRaw": 0.02},
    }
    result = resolve_v12_budget_authority_readiness(_cohort(["set-1", "set-2"]), _resolution(by_set))
    assert result["ready"] is False
    assert result["perSet"]["set-2"]["reason"] == "accessibility_version_mismatch"


def test_unready_accessibility_rejection_propagates_reasons():
    by_set = {
        "set-1": {"ready": False, "reasons": [{"reason": "stale_calculation_run"}]},
    }
    result = resolve_v12_budget_authority_readiness(_cohort(["set-1"]), _resolution(by_set))
    assert result["ready"] is False
    assert result["perSet"]["set-1"]["reason"] == "accessibility_unavailable_or_rejected"


def test_missing_resolution_entry_for_a_cohort_set_fails_explicitly():
    result = resolve_v12_budget_authority_readiness(_cohort(["set-1"]), _resolution({}))
    assert result["ready"] is False
    assert result["perSet"]["set-1"]["reason"] == "no_accessibility_resolution_for_set"


def test_empty_cohort_is_not_considered_ready():
    result = resolve_v12_budget_authority_readiness([], _resolution({}))
    assert result["ready"] is False
    assert result["allSetsEligible"] is False
