"""EBAY_E2_9A: exact distinct-card coverage closure -- focused tests.

Covers, on synthetic per-row fixtures (no network / no model, so these run
fast and deterministically): exact distinct-card coverage arithmetic,
Tier A/Tier B de-duplication, Tier B incremental recovery, uncovered-card
reporting, four-gate evaluation, and reproduction-check accounting. Also
locks the frozen COMBINED-IDENTITY-v2 fingerprint/manifest and policy
source hash so this measurement task cannot have silently mutated them.
"""
from __future__ import annotations

import json
from pathlib import Path

from backend.scripts import ebay_combined_identity_policy_v2 as policy_v2
from backend.scripts.ebay_gold_access import OUT
from backend.scripts.run_ebay_e2_9a_exact_card_coverage import (
    _is_scoped,
    exact_card_coverage,
    four_gates,
    reproduction_check,
)

FREEZE_MANIFEST_PATH = OUT / "ebay_combined_identity_v2_freeze_manifest.json"


def _row(row_id, cohort, card_id, human, tier, image_state="MATCH", text_state="HIGH_CONFIDENCE"):
    combined_state = {
        "TIER_A": policy_v2.TIER_A_IMAGE_VERIFIED,
        "TIER_B": policy_v2.TIER_B_TEXT_VERIFIED_IMAGE_UNVERIFIED,
        None: policy_v2.REJECTED_IMAGE_CONTRADICTION if image_state == "MISMATCH" else policy_v2.TEXT_AMBIGUOUS_NOT_PROMOTED,
    }[tier]
    eligible = combined_state in policy_v2.ELIGIBLE_STATES
    return {
        "row_id": row_id, "cohort": cohort, "canonical_card_id": card_id, "human_truth": human,
        "text_state": text_state, "text_contradiction": False, "image_state": image_state,
        "combined_v1_state": combined_state, "combined_v2_state": combined_state,
        "eligible_under_v2": eligible, "tier": tier,
        "true_eligible_accept": bool(eligible and human == "YES"),
    }


# --- exact distinct-card coverage + de-duplication + incremental recovery -


def test_tier_a_only_card_counts_once_even_with_multiple_tier_a_rows():
    rows = {"V4": [
        _row("r1", "V4", "card-1", "YES", "TIER_A"),
        _row("r2", "V4", "card-1", "YES", "TIER_A"),  # same card, second listing
    ]}
    coverage = exact_card_coverage(rows)["V4"]
    assert coverage["tier_a_covered_count"] == 1
    assert coverage["total_covered_count"] == 1


def test_card_with_both_tier_a_and_tier_b_is_not_double_counted():
    rows = {"V4": [
        _row("r1", "V4", "card-1", "YES", "TIER_A"),
        _row("r2", "V4", "card-1", "YES", "TIER_B", image_state="UNVERIFIED"),
    ]}
    coverage = exact_card_coverage(rows)["V4"]
    assert coverage["tier_a_covered_count"] == 1
    assert coverage["tier_b_incremental_count"] == 0, "card already covered by Tier A must not also count as Tier B incremental"
    assert coverage["total_covered_count"] == 1


def test_tier_b_recovers_a_card_with_no_tier_a_accept():
    rows = {"V4": [
        _row("r1", "V4", "card-1", "YES", "TIER_B", image_state="UNVERIFIED"),
    ]}
    coverage = exact_card_coverage(rows)["V4"]
    assert coverage["tier_a_covered_count"] == 0
    assert coverage["tier_b_incremental_count"] == 1
    assert coverage["total_covered_count"] == 1
    assert coverage["tier_b_incremental_card_ids"] == ["card-1"]


def test_exact_coverage_is_d_over_70():
    rows = {"V4": [_row(f"r{i}", "V4", f"card-{i}", "YES", "TIER_A") for i in range(56)]}
    coverage = exact_card_coverage(rows)["V4"]
    assert coverage["total_target_cards"] == 70
    assert coverage["exact_coverage"] == 56 / 70


def test_a_false_accept_row_never_counts_toward_coverage():
    """A human-NO row that somehow reached Tier A/B must not silently
    contribute a card to coverage -- coverage counts TRUE eligible accepts
    only."""
    rows = {"V4": [_row("r1", "V4", "card-1", "NO", "TIER_A")]}
    coverage = exact_card_coverage(rows)["V4"]
    assert coverage["tier_a_covered_count"] == 0
    assert coverage["total_covered_count"] == 0


def test_uncovered_cards_are_reported_by_id():
    rows = {"V4": [
        _row("r1", "V4", "card-1", "YES", "TIER_A"),
        _row("r2", "V4", "card-2", "YES", None, image_state="MISMATCH"),  # rejected, never covers card-2
    ]}
    coverage = exact_card_coverage(rows)["V4"]
    assert coverage["uncovered_card_ids"] == ["card-2"]


# --- scoping predicate ------------------------------------------------------


def test_scoping_requires_high_confidence_and_no_contradiction():
    assert _is_scoped("HIGH_CONFIDENCE", False) is True
    assert _is_scoped("HIGH_CONFIDENCE", True) is False
    assert _is_scoped("MEDIUM_CONFIDENCE", False) is False
    assert _is_scoped("REJECTED", False) is False
    assert _is_scoped("AMBIGUOUS", False) is False


# --- four-gate evaluation ----------------------------------------------------


def _reproduction(precision=1.0, wilson=0.99, catastrophic=0):
    return {"combined_precision": precision, "combined_wilson_lower": wilson, "catastrophic_false_accepts": catastrophic}


def _coverage(exact=0.85):
    return {"exact_coverage": exact}


def test_four_gates_all_pass():
    gates = four_gates(
        {"V4": _reproduction(), "V5": _reproduction()},
        {"V4": _coverage(), "V5": _coverage()},
    )
    assert gates["V4"]["all_pass"] is True
    assert gates["V5"]["all_pass"] is True
    assert gates["both_cohorts_pass"] is True


def test_four_gates_fail_when_coverage_below_threshold_in_either_cohort():
    gates = four_gates(
        {"V4": _reproduction(), "V5": _reproduction()},
        {"V4": _coverage(0.75), "V5": _coverage(0.85)},
    )
    assert gates["V4"]["card_coverage_ge_0_80"] is False
    assert gates["V4"]["all_pass"] is False
    assert gates["both_cohorts_pass"] is False, "one cohort failing must fail the combined gate"


def test_four_gates_fail_on_catastrophic_false_accept():
    gates = four_gates(
        {"V4": _reproduction(catastrophic=1), "V5": _reproduction()},
        {"V4": _coverage(), "V5": _coverage()},
    )
    assert gates["V4"]["catastrophic_false_accepts_eq_0"] is False
    assert gates["both_cohorts_pass"] is False


def test_four_gates_boundary_is_inclusive():
    """>= 0.80 and >= 0.98 must accept the boundary value itself, not
    reject it -- an off-by-epsilon here would misreport an exact-tie
    cohort (as this task's real V4/V5 result turned out to be)."""
    gates = four_gates(
        {"V4": _reproduction(wilson=0.98), "V5": _reproduction()},
        {"V4": _coverage(0.80), "V5": _coverage()},
    )
    assert gates["V4"]["card_coverage_ge_0_80"] is True
    assert gates["V4"]["wilson_lower_ge_0_98"] is True


# --- reproduction check ------------------------------------------------------


def test_reproduction_check_flags_mismatch_against_frozen_expected_counts():
    rows = {
        "V4": [_row(f"a{i}", "V4", f"card-{i}", "YES", "TIER_A") for i in range(114)],  # one short of 115
        "V5": [_row(f"b{i}", "V5", f"card-{i}", "YES", "TIER_A") for i in range(107)]
              + [_row(f"c{i}", "V5", f"card-{i+107}", "YES", "TIER_B", image_state="UNVERIFIED") for i in range(99)]
              + [_row(f"d{i}", "V5", f"card-{i+206}", "YES", None, image_state="MISMATCH") for i in range(15)],
    }
    report = reproduction_check(rows)
    assert report["V4"]["matches"] is False
    assert report["V5"]["matches"] is True
    assert report["_all_reproduced"] is False


def test_reproduction_check_computes_precision_and_wilson_from_true_and_false_accepts():
    rows = {
        "V4": [_row(f"a{i}", "V4", f"card-{i}", "YES", "TIER_A") for i in range(115)]
              + [_row(f"b{i}", "V4", f"card-{i+115}", "YES", "TIER_B", image_state="UNVERIFIED") for i in range(88)]
              + [_row(f"c{i}", "V4", f"card-{i+203}", "YES", None, image_state="MISMATCH") for i in range(13)],
        "V5": [_row(f"d{i}", "V5", f"card-{i}", "YES", "TIER_A") for i in range(107)]
              + [_row(f"e{i}", "V5", f"card-{i+107}", "YES", "TIER_B", image_state="UNVERIFIED") for i in range(99)]
              + [_row(f"f{i}", "V5", f"card-{i+206}", "YES", None, image_state="MISMATCH") for i in range(15)],
    }
    report = reproduction_check(rows)
    assert report["V4"]["matches"] is True
    assert report["V5"]["matches"] is True
    assert report["_all_reproduced"] is True
    assert report["V4"]["combined_precision"] == 1.0
    assert report["V4"]["catastrophic_false_accepts"] == 0
    assert report["V4"]["high_confidence_unverified_human_no"] == 0


def test_a_high_confidence_unverified_human_no_row_is_a_catastrophic_signal():
    """The historical, central empirical claim underpinning Tier B (Sections
    4/86 of the E2.9 report: 0/837 HIGH_CONFIDENCE+UNVERIFIED+NO rows) must
    remain checkable by this reproduction pass -- a single such row appearing
    is exactly what would have to reopen that finding."""
    rows = {"V4": [_row("bad", "V4", "card-x", "NO", "TIER_B", image_state="UNVERIFIED")], "V5": []}
    report = reproduction_check(rows)
    assert report["V4"]["high_confidence_unverified_human_no"] == 1
    assert report["V4"]["tier_b_false_accepts"] == 1
    assert report["V4"]["catastrophic_false_accepts"] == 1


# --- frozen fingerprint immutability -----------------------------------------


def test_combined_identity_v2_policy_source_hash_matches_frozen_manifest():
    manifest = json.loads(FREEZE_MANIFEST_PATH.read_text(encoding="utf-8"))
    assert policy_v2.policy_source_hash() == manifest["policy_source_sha256"], (
        "COMBINED-IDENTITY-v2 source changed since freeze -- this task must not modify policy semantics"
    )


def test_combined_identity_v2_eligible_states_unchanged():
    manifest = json.loads(FREEZE_MANIFEST_PATH.read_text(encoding="utf-8"))
    assert manifest["eligible_states"] == [
        policy_v2.TIER_A_IMAGE_VERIFIED, policy_v2.TIER_B_TEXT_VERIFIED_IMAGE_UNVERIFIED,
    ]


def test_combined_identity_v2_still_not_certified_against_a_new_blind():
    manifest = json.loads(FREEZE_MANIFEST_PATH.read_text(encoding="utf-8"))
    assert manifest["certified_against_new_blind"] is False
    assert manifest["consumed_blind_rows_used_for_tuning"] is False


def test_e2_9a_produced_no_new_blind_queue_file():
    assert not (OUT / "ebay_d3_v6_fresh_blind_queue.csv").exists()
    assert not (OUT / "ebay_d3_v6_fresh_blind_manifest.json").exists()
