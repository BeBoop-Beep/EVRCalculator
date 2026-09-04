"""Overall RIP V12 - 86/4/10 Financial/ChaseAccessibility/Collector formula.

Covers: exact formula, transform anchor semantics, monotonicity, scale
separation (raw vs A_score), missing-data contract, weight sum, nested/flat
parity, V10/V11 immutability, ECE absence, Chase Depth absence, and the
research-locked identity contract (Phase 11 of the implementation prompt).
"""

from __future__ import annotations

import inspect

import pytest

from backend.desirability.chase_accessibility import CHASE_ACCESSIBILITY_VERSION
from backend.desirability.chase_accessibility_overall_score import (
    CHASE_ACCESSIBILITY_OVERALL_SCORE_K,
    CHASE_ACCESSIBILITY_OVERALL_SCORE_VERSION,
    chase_accessibility_overall_score,
)
from backend.desirability.collector_appeal import COLLECTOR_APPEAL_V5_VERSION
from backend.calculations.evr.financial_rip_v4_config import FINANCIAL_RIP_V4_VERSION
from backend.desirability.scoring_config import (
    CANONICAL_OVERALL_RIP_VERSION,
    OVERALL_RIP_V10_VERSION,
    OVERALL_RIP_V10_WEIGHTS,
    OVERALL_RIP_V11_VERSION,
    OVERALL_RIP_V11_WEIGHTS,
    OVERALL_RIP_V12_CHASE_ACCESSIBILITY_SHARE_OF_MARKET_BASED,
    OVERALL_RIP_V12_FINANCIAL_SHARE_OF_MARKET_BASED,
    OVERALL_RIP_V12_VERSION,
    OVERALL_RIP_V12_WEIGHTS,
)
from backend.desirability.weighted_rip import (
    compute_overall_rip_v10,
    compute_overall_rip_v11,
    compute_overall_rip_v12,
)


# --------------------------------------------------------------- A. Formula

def test_v12_exact_formula():
    a_raw = 0.0025
    expected_a_score = 100.0 * a_raw / (a_raw + 0.002)
    result = compute_overall_rip_v12(70.0, a_raw, 60.0)
    assert result["components"]["chaseAccessibility"]["score"] == pytest.approx(
        expected_a_score, abs=1e-4
    )
    expected_overall = 0.86 * 70.0 + 0.04 * expected_a_score + 0.10 * 60.0
    assert result["score"] == pytest.approx(expected_overall, abs=1e-4)
    assert result["version"] == OVERALL_RIP_V12_VERSION


# ------------------------------------------------------------ B. Anchor semantics

@pytest.mark.parametrize(
    "a_raw,expected_score",
    [
        (0.002 / 3.0, 25.0),
        (0.002, 50.0),
        (0.006, 75.0),
    ],
)
def test_anchor_semantics(a_raw, expected_score):
    assert chase_accessibility_overall_score(a_raw) == pytest.approx(expected_score, abs=1e-6)


def test_anchor_constant_is_locked_at_0_002():
    assert CHASE_ACCESSIBILITY_OVERALL_SCORE_K == 0.002


# ------------------------------------------------------------- C. Monotonicity

def test_higher_a_raw_never_reduces_overall_with_fixed_financial_and_collector():
    f, c = 55.0, 40.0
    a_values = [0.0, 0.0002, 0.0005, 0.001, 0.002, 0.004, 0.01, 0.05, 1.0, 100.0]
    scores = [compute_overall_rip_v12(f, a, c)["score"] for a in a_values]
    assert all(b >= a for a, b in zip(scores, scores[1:]))


def test_transform_itself_is_strictly_monotonic():
    values = [chase_accessibility_overall_score(a / 1000.0) for a in range(0, 200)]
    assert all(b > a for a, b in zip(values, values[1:]))


# --------------------------------------------------------- D. Scale separation

def test_raw_accessibility_field_is_not_the_overall_score_transform():
    """The public raw metric and this Overall-scoring transform are distinct
    functions; nothing conflates them under one name."""
    import backend.desirability.chase_accessibility as raw_module
    import backend.desirability.chase_accessibility_overall_score as transform_module

    assert raw_module is not transform_module
    assert not hasattr(raw_module, "chase_accessibility_overall_score")
    # The raw module's public identity is untouched by this prompt.
    assert raw_module.CHASE_ACCESSIBILITY_VERSION == (
        "chase_accessibility_v1_hc_value_squared_modeled_probability"
    )


def test_a_score_and_a_raw_differ_for_any_nontrivial_raw_value():
    a_raw = 0.0025
    a_score = chase_accessibility_overall_score(a_raw)
    assert a_score != pytest.approx(a_raw)
    assert a_score > 50.0  # a_raw above the k=0.002 anchor


# ---------------------------------------------------------- E. Missing data

def test_missing_accessibility_makes_overall_unavailable_never_zero():
    result = compute_overall_rip_v12(70.0, None, 60.0)
    assert result["score"] is None
    assert result["rankable"] is False
    assert "chase_accessibility_v1" in result["missingInputs"]
    assert result["version"] == OVERALL_RIP_V12_VERSION  # never silently reverts to V10/V11


def test_negative_accessibility_is_refused_not_clamped_to_zero():
    result = compute_overall_rip_v12(70.0, -0.001, 60.0)
    assert result["score"] is None
    assert result["rankable"] is False


@pytest.mark.parametrize("missing", ["financial", "accessibility", "collector"])
def test_any_single_missing_pillar_fails_closed(missing):
    args = {"financial": 70.0, "accessibility": 0.002, "collector": 60.0}
    args[missing] = None
    result = compute_overall_rip_v12(args["financial"], args["accessibility"], args["collector"])
    assert result["score"] is None
    assert result["rankable"] is False


# -------------------------------------------------------------- F. Weight sum

def test_weights_are_86_04_10_and_sum_to_one():
    assert OVERALL_RIP_V12_WEIGHTS["financial_rip"] == 0.86
    assert OVERALL_RIP_V12_WEIGHTS["chase_accessibility"] == 0.04
    assert OVERALL_RIP_V12_WEIGHTS["collector_appeal"] == 0.10
    assert sum(OVERALL_RIP_V12_WEIGHTS.values()) == pytest.approx(1.0, abs=1e-9)


# ------------------------------------------------------- G. Nested/flat parity

def test_nested_vs_flat_parity_to_machine_precision():
    financial_share = OVERALL_RIP_V12_FINANCIAL_SHARE_OF_MARKET_BASED
    accessibility_share = OVERALL_RIP_V12_CHASE_ACCESSIBILITY_SHARE_OF_MARKET_BASED
    assert financial_share == pytest.approx(86.0 / 90.0, abs=1e-12)
    assert accessibility_share == pytest.approx(4.0 / 90.0, abs=1e-12)

    for f in (12.5, 55.0, 88.0, 100.0):
        for a_raw in (0.0001, 0.002, 0.006, 0.05):
            for c in (0.0, 33.3, 60.0, 100.0):
                a_score = chase_accessibility_overall_score(a_raw)
                market_based = financial_share * f + accessibility_share * a_score
                nested = 0.90 * market_based + 0.10 * c
                flat = 0.86 * f + 0.04 * a_score + 0.10 * c
                assert abs(nested - flat) < 1e-9


# ------------------------------------------------------ H. V10 golden regression

def test_v10_still_computes_unchanged_90_10():
    result = compute_overall_rip_v10(80.0, 40.0)
    assert result["score"] == pytest.approx(0.90 * 80.0 + 0.10 * 40.0, abs=1e-9)
    assert result["version"] == OVERALL_RIP_V10_VERSION
    assert "chaseAccessibility" not in result["components"]


def test_v10_weights_untouched():
    assert OVERALL_RIP_V10_WEIGHTS == {"financial_rip": 0.90, "collector_appeal": 0.10}


# ------------------------------------------------------- I. V11 not restored

def test_v11_still_computes_unchanged_83_11_6_core_k():
    result = compute_overall_rip_v11(60.0, 70.0, 20.0)
    assert result["score"] == pytest.approx(0.83 * 60.0 + 0.11 * 70.0 + 0.06 * 20.0, abs=5e-5)
    assert result["version"] == OVERALL_RIP_V11_VERSION
    assert "chaseAccessibility" not in result["components"]


def test_v11_weights_untouched():
    assert OVERALL_RIP_V11_WEIGHTS == {
        "financial_rip": 0.83,
        "collector_appeal": 0.11,
        "chase_opportunity": 0.06,
    }


def test_canonical_selector_is_now_v12_not_v10_or_v11():
    """2026-09-03 cutover: canonical Overall RIP promoted from V10 to V12.

    V11 (the separate Chase Opportunity/Core-K lineage) is untouched and never
    becomes canonical by this promotion. V10 remains fully computable/
    registered as explicit historical/rollback lineage.
    """
    assert CANONICAL_OVERALL_RIP_VERSION == OVERALL_RIP_V12_VERSION
    assert CANONICAL_OVERALL_RIP_VERSION != OVERALL_RIP_V10_VERSION
    assert CANONICAL_OVERALL_RIP_VERSION != OVERALL_RIP_V11_VERSION


# ------------------------------------------------------------------ J. ECE absence

def test_v12_signature_has_no_ece_or_cost_inputs():
    signature = inspect.signature(compute_overall_rip_v12)
    param_names = set(signature.parameters)
    forbidden = {
        "economic_chase_efficiency",
        "product_chase_efficiency",
        "product_market_cost",
        "effective_pack_cost",
        "ece",
    }
    assert not (param_names & forbidden)


def test_v12_formula_string_has_no_ece_terms():
    result = compute_overall_rip_v12(70.0, 0.002, 60.0)
    formula = result["formula"].lower()
    for banned in ("economic_chase_efficiency", "product_chase_efficiency", "ece"):
        assert banned not in formula


# ------------------------------------------------------------- K. Chase Depth absence

def test_v12_signature_has_no_chase_depth_input():
    signature = inspect.signature(compute_overall_rip_v12)
    assert "chase_depth" not in signature.parameters
    assert "chaseDepth" not in result_components(compute_overall_rip_v12(70.0, 0.002, 60.0))


def result_components(result):
    return result.get("components", {})


# ------------------------------------------------------- L. No raw pull-rate input

def test_v12_consumes_authoritative_a_raw_not_a_fresh_probability_computation():
    """V12 takes the already-computed Chase Accessibility A_raw scalar - it
    has no card-level variants/pull-rate parameters of its own."""
    signature = inspect.signature(compute_overall_rip_v12)
    param_names = set(signature.parameters)
    assert "effective_pull_rate" not in param_names
    assert "variants" not in param_names
    assert "modeled_probability" not in param_names
    assert "chase_accessibility_raw" in param_names


# --------------------------------------------------- Research-contract (Phase 11)

def test_research_locked_identity_contract():
    """Locks the validated identity so a future engineer cannot silently
    restore 84/6/10, 83/11/6 (V11's split, wrong pillar), or bare 90/10
    without Accessibility under the V12 name."""
    expected_weights = {
        "financial_rip": 0.86,
        "chase_accessibility": 0.04,
        "collector_appeal": 0.10,
    }
    assert OVERALL_RIP_V12_WEIGHTS == expected_weights

    rejected_weight_tuples = [
        (0.84, 0.06, 0.10),   # the superseded BLOCKED-pass 84/6/10 candidate
        (0.83, 0.11, 0.06),   # V11's split, wrong pillar semantics entirely
        (0.90, 0.00, 0.10),   # 90/10 with no Accessibility at all
    ]
    actual_tuple = (
        OVERALL_RIP_V12_WEIGHTS["financial_rip"],
        OVERALL_RIP_V12_WEIGHTS["chase_accessibility"],
        OVERALL_RIP_V12_WEIGHTS["collector_appeal"],
    )
    assert actual_tuple not in rejected_weight_tuples

    assert CHASE_ACCESSIBILITY_OVERALL_SCORE_K == 0.002
    assert FINANCIAL_RIP_V4_VERSION == (
        "financial_rip_v4_outcome_profile_p95_only_25_20_15_25_10_5"
    )
    assert COLLECTOR_APPEAL_V5_VERSION == (
        "collector_appeal_v5_contextual_roster_h_only_d_baseline_up4_down2"
    )
    assert CHASE_ACCESSIBILITY_VERSION == (
        "chase_accessibility_v1_hc_value_squared_modeled_probability"
    )
    assert CHASE_ACCESSIBILITY_OVERALL_SCORE_VERSION == (
        "chase_accessibility_overall_score_v1_saturating_k002"
    )
