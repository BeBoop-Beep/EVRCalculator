"""Collector Appeal V3 (0.40D + 0.35H + 0.25P) and Overall RIP V7 (90/10).

BOTH MODELS ARE NOW SUPERSEDED: Financial RIP V4 and Overall RIP V10 (90/10
over Collector Appeal V5) are canonical - see
``test_overall_rip_v10_and_financial_v4_integration.py``. This file remains
the backward-compatibility suite for Collector Appeal V3 / Overall RIP V7,
one rung above the V2/V6 suite in ``test_collector_appeal_v2_and_overall_rip_v6.py``.

Organised around the claims these models make:

    1. the exact formula, its bounds and its monotonicity
    2. contributions reconstruct the score
    3. the construct ordering: D nominally first, H close behind, P material
    4. missing and malformed inputs make the score UNAVAILABLE, never 0 / 0.5 /
       D / a previous version
    5. no financial input is read anywhere in the appeal path
    6. Overall RIP V7 is exactly 90/10 over Financial RIP V3 and Collector
       Appeal V3, with no substitution in either direction
    7. Financial RIP V3 is untouched by this cutover
    8. the public projection discloses no weight and no formula
"""

from __future__ import annotations

import ast
import inspect

import pytest

import backend.desirability.collector_appeal as collector_appeal_module
import backend.desirability.desirable_outcome_frequency as frequency_module
from backend.calculations.evr.financial_rip_v3_config import (
    FINANCIAL_RIP_V3_COMPONENT_ORDER,
    FINANCIAL_RIP_V3_VERSION,
    FINANCIAL_RIP_V3_WEIGHTS,
)
from backend.calculations.evr.financial_rip_v4_config import (
    FINANCIAL_RIP_V4_VERSION,
)
from backend.desirability.collector_appeal import (
    COLLECTOR_APPEAL_CA7_VERSION,
    COLLECTOR_APPEAL_V2_VERSION,
    COLLECTOR_APPEAL_V3_FORMULA_VERSION,
    COLLECTOR_APPEAL_V3_INPUT_ORDER,
    COLLECTOR_APPEAL_V3_VERSION,
    COLLECTOR_APPEAL_V3_WEIGHTS,
    collector_appeal_v3_decomposition,
    collector_appeal_v3_missing_inputs,
    collector_appeal_v3_public_identity,
    compute_collector_appeal_ca7,
    compute_collector_appeal_v2,
    compute_collector_appeal_v3,
)
from backend.desirability.public_rip_contract_v7 import (
    COLLECTOR_APPEAL_WITHHELD_FIELDS,
    PUBLIC_RIP_CONTRACT_V7_VERSION,
    build_public_rip_contract_v7,
)
from backend.desirability.scoring_config import (
    CANONICAL_OVERALL_RIP_VERSION,
    OVERALL_RIP_COLLECTOR_APPEAL_SENSITIVITY_WEIGHTS,
    OVERALL_RIP_PRODUCTION_GUARDRAILS,
    OVERALL_RIP_V6_VERSION,
    OVERALL_RIP_V7_EFFECTIVE_WEIGHTS,
    OVERALL_RIP_V7_VERSION,
    OVERALL_RIP_V7_WEIGHTS,
    canonical_collector_appeal_formula_version,
    canonical_collector_appeal_version,
    legacy_collector_appeal_v3_version,
    canonical_overall_rip_is_v8,
    canonical_public_rip_contract_version,
    canonical_scoring_selection,
    canonical_overall_rip_is_v9,
    canonical_overall_rip_is_v10,
    canonical_overall_rip_is_v12,
    OVERALL_RIP_V10_VERSION,
    OVERALL_RIP_V12_VERSION,
)
from backend.desirability.weighted_rip import compute_overall_rip_v7

GRID = (0.0, 0.1, 0.25, 0.4, 0.5, 0.6, 0.75, 0.9, 1.0)

W_D = COLLECTOR_APPEAL_V3_WEIGHTS["roster_desirability"]
W_H = COLLECTOR_APPEAL_V3_WEIGHTS["desirable_outcome_frequency"]
W_P = COLLECTOR_APPEAL_V3_WEIGHTS["dual_path_depth"]


# ===========================================================================
# 1. The exact formula
# ===========================================================================

def test_the_formula_is_exactly_forty_thirtyfive_twentyfive():
    assert COLLECTOR_APPEAL_V3_WEIGHTS == {
        "roster_desirability": 0.40,
        "desirable_outcome_frequency": 0.35,
        "dual_path_depth": 0.25,
    }
    assert sum(COLLECTOR_APPEAL_V3_WEIGHTS.values()) == pytest.approx(1.0, abs=1e-12)
    assert tuple(COLLECTOR_APPEAL_V3_WEIGHTS) == COLLECTOR_APPEAL_V3_INPUT_ORDER


@pytest.mark.parametrize("d", GRID)
@pytest.mark.parametrize("h", (0.0, 0.37, 1.0))
@pytest.mark.parametrize("p", (0.0, 0.62, 1.0))
def test_the_score_is_the_exact_weighted_sum(d, h, p):
    assert compute_collector_appeal_v3(d, h, p) == pytest.approx(
        W_D * d + W_H * h + W_P * p, abs=1e-12
    )


def test_equal_inputs_reproduce_the_input_because_the_weights_partition_unity():
    for value in GRID:
        assert compute_collector_appeal_v3(value, value, value) == pytest.approx(
            value, abs=1e-12
        )


@pytest.mark.parametrize("d", GRID)
@pytest.mark.parametrize("h", GRID)
@pytest.mark.parametrize("p", GRID)
def test_the_score_is_always_inside_zero_and_one(d, h, p):
    score = compute_collector_appeal_v3(d, h, p)
    assert 0.0 <= score <= 1.0


def test_the_public_score_is_one_hundred_times_the_unit_score():
    decomposition = collector_appeal_v3_decomposition(0.42, 0.18, 0.55)
    assert decomposition["publicScore"] == pytest.approx(
        decomposition["unitScore"] * 100.0, abs=1e-12
    )


# ===========================================================================
# 2. Monotonicity in each input, independently
# ===========================================================================

@pytest.mark.parametrize("index,weight", [(0, W_D), (1, W_H), (2, W_P)])
def test_the_score_is_strictly_increasing_in_each_input(index, weight):
    """Independently of where the other two sit - the balanced sum's whole point.

    Under the superseded V2 formula the marginal effect of H and P was scaled by
    ``(1 - D)``, so a desirable roster crushed them toward zero. Here the slope
    is the weight, everywhere.
    """
    for others in ((0.0, 0.0), (0.5, 0.5), (1.0, 1.0), (0.9, 0.1)):
        base = list(others)
        base.insert(index, 0.0)
        low = compute_collector_appeal_v3(*base)
        base[index] = 1.0
        high = compute_collector_appeal_v3(*base)
        assert high > low
        assert high - low == pytest.approx(weight, abs=1e-12)


def test_the_marginal_effect_of_h_does_not_depend_on_d():
    """The specific defect V3 fixes, asserted directly."""
    def delta_h(d):
        return compute_collector_appeal_v3(d, 1.0, 0.5) - compute_collector_appeal_v3(d, 0.0, 0.5)

    assert delta_h(0.05) == pytest.approx(delta_h(0.95), abs=1e-12)
    # Under V2 it emphatically DID depend on D, which is why V2 collapsed into D.
    def v2_delta_h(d):
        return compute_collector_appeal_v2(d, 1.0, 0.5) - compute_collector_appeal_v2(d, 0.0, 0.5)

    assert v2_delta_h(0.05) > v2_delta_h(0.95) * 5


# ===========================================================================
# 3. Contributions reconstruct the score
# ===========================================================================

@pytest.mark.parametrize("d,h,p", [(0.42, 0.18, 0.55), (0.0, 0.0, 0.0), (1.0, 1.0, 1.0),
                                   (0.93, 0.07, 0.61)])
def test_contributions_sum_exactly_to_the_unit_score(d, h, p):
    decomposition = collector_appeal_v3_decomposition(d, h, p)
    total = (
        decomposition["dContribution"]
        + decomposition["hContribution"]
        + decomposition["pContribution"]
    )
    assert total == pytest.approx(decomposition["unitScore"], abs=1e-12)
    assert decomposition["contributionsReconcile"] is True


def test_each_contribution_is_its_weight_times_its_input():
    decomposition = collector_appeal_v3_decomposition(0.42, 0.18, 0.55)
    assert decomposition["dContribution"] == pytest.approx(W_D * 0.42, abs=1e-12)
    assert decomposition["hContribution"] == pytest.approx(W_H * 0.18, abs=1e-12)
    assert decomposition["pContribution"] == pytest.approx(W_P * 0.55, abs=1e-12)


# ===========================================================================
# 4. The construct ordering
# ===========================================================================

def test_d_has_the_highest_nominal_coefficient():
    assert W_D > W_H
    assert W_D > W_P
    assert W_D == max(COLLECTOR_APPEAL_V3_WEIGHTS.values())


def test_h_is_nearly_comparable_to_d():
    """H is close behind D, not a rounding error beside it.

    "Nearly comparable" is made concrete: H carries at least 80% of D's weight,
    and the gap between them is smaller than the gap between H and P.
    """
    assert W_H / W_D >= 0.80
    assert (W_D - W_H) < (W_H - W_P) or (W_D - W_H) == pytest.approx(W_H - W_P, abs=1e-12)


def test_p_remains_material():
    """P is materially weighted - not a token term.

    Concretely: it carries at least a fifth of the score, and moving P alone from
    0 to 1 moves the published score by 25 points, which reorders any realistic
    cohort.
    """
    assert W_P >= 0.20
    low = compute_collector_appeal_v3(0.5, 0.5, 0.0)
    high = compute_collector_appeal_v3(0.5, 0.5, 1.0)
    assert (high - low) * 100.0 == pytest.approx(25.0, abs=1e-9)


def test_no_input_can_dominate_the_other_two_combined():
    """No single input carries a majority, so none can outvote the rest."""
    for key, weight in COLLECTOR_APPEAL_V3_WEIGHTS.items():
        assert weight < 0.5, key


# ===========================================================================
# 5. Missing and malformed inputs
# ===========================================================================

@pytest.mark.parametrize("d,h,p,expected", [
    (None, 0.5, 0.5, "roster_desirability"),
    (0.5, None, 0.5, "desirable_outcome_frequency"),
    (0.5, 0.5, None, "dual_path_depth"),
])
def test_a_missing_input_makes_the_score_unavailable_and_names_itself(d, h, p, expected):
    assert compute_collector_appeal_v3(d, h, p) is None
    assert collector_appeal_v3_missing_inputs(d, h, p) == [expected]


def test_a_missing_input_is_never_substituted_with_anything():
    """Not 0, not 0.5, not D, not a previous version. The score is unavailable.

    Each substitution is checked explicitly because each is a plausible-looking
    "helpful" default, and each would be a claim the absent data does not
    support.
    """
    score = compute_collector_appeal_v3(0.80, None, 0.40)
    assert score is None
    assert score != 0.0
    assert score != 0.5
    assert score != 0.80
    assert score != compute_collector_appeal_ca7(0.80, 0.40)
    assert score != compute_collector_appeal_v2(0.80, 0.0, 0.40)


@pytest.mark.parametrize("bad", ["nope", float("nan"), float("inf"), float("-inf"),
                                 1.4, -0.2, object(), [], {}])
def test_malformed_values_make_the_score_unavailable(bad):
    """Out-of-range is REJECTED, not clamped.

    A 1.4 or a -0.2 arriving here is a units error or a corrupted payload, not an
    extreme set; clamping it would publish a score built from a number nobody
    intended.
    """
    assert compute_collector_appeal_v3(bad, 0.5, 0.5) is None
    assert compute_collector_appeal_v3(0.5, bad, 0.5) is None
    assert compute_collector_appeal_v3(0.5, 0.5, bad) is None


def test_floating_point_residue_just_outside_the_interval_is_clamped_not_rejected():
    """A hair outside [0,1] is arithmetic residue from a union, not a units error."""
    assert compute_collector_appeal_v3(1.0 + 1e-12, 0.5, 0.5) == pytest.approx(
        compute_collector_appeal_v3(1.0, 0.5, 0.5), abs=1e-9
    )
    assert compute_collector_appeal_v3(-1e-12, 0.5, 0.5) == pytest.approx(
        compute_collector_appeal_v3(0.0, 0.5, 0.5), abs=1e-9
    )


def test_the_decomposition_of_an_unavailable_score_names_what_is_missing():
    decomposition = collector_appeal_v3_decomposition(0.5, None, None)
    assert decomposition["unitScore"] is None
    assert decomposition["publicScore"] is None
    assert decomposition["contributionsReconcile"] is None
    assert decomposition["missingInputs"] == [
        "desirable_outcome_frequency", "dual_path_depth"
    ]


# ===========================================================================
# 6. No financial input, anywhere
# ===========================================================================

FINANCIAL_IDENTIFIERS = (
    "price", "market_price", "expected_value", "pack_cost", "profit", "profitability",
    "set_value", "financial_rip", "true_win", "ev", "revenue", "cost",
)


def _financial_identifiers_in(function) -> list:
    """Financial identifiers referenced by one function's EXECUTABLE code.

    AST, not raw text: these functions legitimately DISCUSS price in their
    docstrings - they document at length why price is excluded - and a text
    search cannot tell an explanation from an implementation.
    """
    tree = ast.parse(inspect.getsource(function))
    names = set()
    for node in ast.walk(tree):
        if isinstance(node, ast.Name):
            names.add(node.id.lower())
        elif isinstance(node, ast.Attribute):
            names.add(node.attr.lower())
        elif isinstance(node, ast.Constant) and isinstance(node.value, str):
            names.add(node.value.lower())
    return sorted(
        name for name in names
        if any(token == name or name.startswith(token + "_") for token in FINANCIAL_IDENTIFIERS)
    )


# `collector_appeal_v3_public_identity` is deliberately absent: it DECLARES the
# excluded financial inputs by name, which is the opposite of reading one. Its
# contract is asserted by `test_the_public_identity_declares_the_excluded_inputs`.
@pytest.mark.parametrize("function", [
    compute_collector_appeal_v3,
    collector_appeal_v3_decomposition,
    collector_appeal_v3_missing_inputs,
    collector_appeal_module.compute_dual_path_depth,
    collector_appeal_module.subject_dual_path,
    collector_appeal_module.structural_opening_appeal,
    frequency_module.compute_desirable_outcome_frequency,
])
def test_no_function_on_the_appeal_scoring_path_reads_a_financial_identifier(function):
    """Scoped to the SCORING PATH, not to whole modules, and deliberately so.

    ``collector_appeal`` also contains ``proportional_rip_weights`` and
    ``profit_funded_rip_weights`` - research-only helpers for a RIP weight
    sensitivity study that legitimately name Profit/Safety/Stability. A
    module-wide scan would flag those and would have to be suppressed, and a
    suppressed assertion protects nothing. What must be free of financial inputs
    is the path that computes a published Collector Appeal, which is what this
    enumerates.
    """
    assert _financial_identifiers_in(function) == []


def test_the_public_identity_declares_the_excluded_inputs():
    identity = collector_appeal_v3_public_identity()
    for excluded in (
        "market_price", "expected_value", "pack_cost", "profitability",
        "financial_score", "market_rank_proxy", "scarcity_price_proxy",
    ):
        assert excluded in identity["excludedInputs"]


def test_trainers_and_artists_remain_deferred_rather_than_scored_zero():
    identity = collector_appeal_v3_public_identity()
    assert identity["subjectScope"]["modeled"] == ["pokemon"]
    assert set(identity["subjectScope"]["notYetModeled"]) == {"trainer", "artist"}


# ===========================================================================
# 7. Versions
# ===========================================================================

def test_the_canonical_identifiers_are_the_specified_strings():
    assert COLLECTOR_APPEAL_V3_VERSION == "collector_appeal_v3_balanced_d40_h35_p25"
    assert COLLECTOR_APPEAL_V3_FORMULA_VERSION == "collector_appeal_weighted_sum_d_h_p_v1"
    assert OVERALL_RIP_V7_VERSION == "overall_rip_v7_90_financial_v3_10_collector_appeal_v3"
    assert PUBLIC_RIP_CONTRACT_V7_VERSION == "public_rip_contract_v7"


def test_there_is_exactly_one_authoritative_source_for_each_canonical_version():
    """Every accessor resolves to the SAME string. A second source is a second cutover."""
    # V3 is SUPERSEDED. Its own strings must not move - a stored V3 row has to
    # stay reproducible - but the canonical accessors now resolve to V4.
    assert legacy_collector_appeal_v3_version() == COLLECTOR_APPEAL_V3_VERSION
    assert canonical_collector_appeal_version() != COLLECTOR_APPEAL_V3_VERSION
    assert canonical_public_rip_contract_version() != PUBLIC_RIP_CONTRACT_V7_VERSION
    # V7 is SUPERSEDED: its string must not move, and it must no longer be canonical.
    assert OVERALL_RIP_V7_VERSION == "overall_rip_v7_90_financial_v3_10_collector_appeal_v3"
    assert CANONICAL_OVERALL_RIP_VERSION != OVERALL_RIP_V7_VERSION
    # STALE EXPECTATION CORRECTED (2026-09-03): the canonical Overall model is
    # now V12 (86/4/10 Financial V4 + Chase Accessibility + Collector Appeal
    # V5). V8, V9 and V10 are all preserved and identifiable, and are all no
    # longer canonical.
    assert canonical_overall_rip_is_v8() is False
    assert canonical_overall_rip_is_v9() is False
    assert canonical_overall_rip_is_v10() is False
    assert canonical_overall_rip_is_v12() is True
    assert CANONICAL_OVERALL_RIP_VERSION == OVERALL_RIP_V12_VERSION
    assert CANONICAL_OVERALL_RIP_VERSION == OVERALL_RIP_V10_VERSION

    selection = canonical_scoring_selection()
    assert selection["legacyCollectorAppealV3Version"] == COLLECTOR_APPEAL_V3_VERSION
    assert selection["legacyOverallRipV7Version"] == OVERALL_RIP_V7_VERSION
    assert selection["canonicalPublicRipContractVersion"] != PUBLIC_RIP_CONTRACT_V7_VERSION
    # `canonicalFinancialRipVersion` reads the live CANONICAL_FINANCIAL_RIP_VERSION
    # constant, which the V4 cutover moved from V3 to V4.
    assert selection["canonicalFinancialRipVersion"] == FINANCIAL_RIP_V4_VERSION


def test_every_historical_version_stays_distinct_and_readable():
    versions = {
        COLLECTOR_APPEAL_V3_VERSION,
        COLLECTOR_APPEAL_V2_VERSION,
        COLLECTOR_APPEAL_CA7_VERSION,
        OVERALL_RIP_V7_VERSION,
        OVERALL_RIP_V6_VERSION,
    }
    assert len(versions) == 5
    selection = canonical_scoring_selection()
    assert selection["legacyCollectorAppealV2Version"] == COLLECTOR_APPEAL_V2_VERSION
    assert selection["legacyCollectorAppealVersion"] == COLLECTOR_APPEAL_CA7_VERSION
    assert selection["legacyOverallRipV6Version"] == OVERALL_RIP_V6_VERSION


def test_the_version_says_ninety_ten_and_never_eighty_twenty():
    assert "_90_" in OVERALL_RIP_V7_VERSION
    assert "_10_" in OVERALL_RIP_V7_VERSION
    assert "80" not in OVERALL_RIP_V7_VERSION
    assert "_20_" not in OVERALL_RIP_V7_VERSION


# ===========================================================================
# 8. Overall RIP V7
# ===========================================================================

def test_overall_rip_v7_weights_are_exactly_ninety_ten():
    assert OVERALL_RIP_V7_WEIGHTS == {"financial_rip": 0.90, "collector_appeal": 0.10}
    assert sum(OVERALL_RIP_V7_WEIGHTS.values()) == pytest.approx(1.0, abs=1e-12)


def test_effective_weights_expand_financial_rip_v3_across_its_ninety_percent():
    expected = {
        "true_win_frequency": 0.225,
        "typical_retention": 0.180,
        "loss_resilience": 0.135,
        "realistic_upside": 0.225,
        "jackpot_upside": 0.090,
        "base_economic_efficiency": 0.045,
        "collector_appeal": 0.100,
    }
    for key, value in expected.items():
        assert OVERALL_RIP_V7_EFFECTIVE_WEIGHTS[key] == pytest.approx(value, abs=1e-12)
    assert sum(OVERALL_RIP_V7_EFFECTIVE_WEIGHTS.values()) == pytest.approx(1.0, abs=1e-12)
    for key, weight in FINANCIAL_RIP_V3_WEIGHTS.items():
        assert OVERALL_RIP_V7_EFFECTIVE_WEIGHTS[key] == pytest.approx(0.90 * weight, abs=1e-12)


def test_contributions_reconstruct_overall_rip_v7():
    result = compute_overall_rip_v7(53.25, 68.75)
    total = sum(block["contribution"] for block in result["components"].values())
    assert total == pytest.approx(result["score"], abs=1e-4)
    assert result["score"] == pytest.approx(0.90 * 53.25 + 0.10 * 68.75, abs=1e-9)
    assert result["version"] == OVERALL_RIP_V7_VERSION
    assert result["rankable"] is True


@pytest.mark.parametrize("financial,appeal,missing", [
    (None, 70.0, "financial_rip_v3"),
    (50.0, None, "collector_appeal_v3"),
])
def test_missing_either_input_blocks_overall_rip_v7(financial, appeal, missing):
    result = compute_overall_rip_v7(financial, appeal)
    assert result["score"] is None
    assert result["rankable"] is False
    assert missing in result["missingInputs"]


def test_a_missing_collector_appeal_is_never_converted_to_zero():
    """Zero would rank the set LAST on a construct it was never measured on.

    That is a stronger claim than "no data", and it is a claim the absence does
    not support.
    """
    unavailable = compute_overall_rip_v7(50.0, None)
    as_zero = compute_overall_rip_v7(50.0, 0.0)
    assert unavailable["score"] is None
    assert as_zero["score"] == pytest.approx(45.0, abs=1e-9)
    assert unavailable["score"] != as_zero["score"]


def test_there_is_no_fallback_to_any_previous_model():
    result = compute_overall_rip_v7(50.0, None)
    reason = result["statusReason"]
    assert "not treated as zero" in reason
    assert "no fallback" in reason.lower()
    for named in ("V6", "V5", "v4", "V2", "Collector Appeal V2", "CA7",
                  "Universal Set Desirability"):
        assert named in reason


def test_financial_rip_v3_is_unchanged_by_the_v7_cutover():
    assert FINANCIAL_RIP_V3_WEIGHTS == {
        "true_win_frequency": 0.25,
        "typical_retention": 0.20,
        "loss_resilience": 0.15,
        "realistic_upside": 0.25,
        "jackpot_upside": 0.10,
        "base_economic_efficiency": 0.05,
    }
    assert len(FINANCIAL_RIP_V3_COMPONENT_ORDER) == 6
    assert FINANCIAL_RIP_V3_VERSION == "financial_rip_v3_outcome_profile_25_20_15_25_10_5"


# ===========================================================================
# 9. Sensitivity weights are research, not production
# ===========================================================================

def test_thirteen_and_fourteen_percent_are_research_candidates_only():
    assert 0.13 in OVERALL_RIP_COLLECTOR_APPEAL_SENSITIVITY_WEIGHTS
    assert 0.14 in OVERALL_RIP_COLLECTOR_APPEAL_SENSITIVITY_WEIGHTS
    # ...and neither is the shipping weight.
    assert OVERALL_RIP_V7_WEIGHTS["collector_appeal"] == 0.10


def test_the_production_guardrails_live_in_reviewed_config():
    """So "do not silently weaken the guardrail" is enforceable, not aspirational."""
    assert OVERALL_RIP_PRODUCTION_GUARDRAILS == {
        "min_spearman_vs_financial_only": 0.95,
        "min_top5_overlap": 0.80,
        "max_mean_absolute_rank_movement": 1.5,
        "max_share_moving_5_plus_ranks": 0.10,
    }


# ===========================================================================
# 10. The public contract discloses no weight and no formula
# ===========================================================================

def _target():
    return {
        "financialRipV3": {"score": 61.0, "status": "ready", "rankable": True, "components": {}},
        "overallRipV7": {
            "score": 59.5,
            "version": OVERALL_RIP_V7_VERSION,
            "rank": 3,
            "cohortSize": 22,
            "components": {
                "financialRipV3": {"score": 61.0, "contribution": 54.9},
                "collectorAppeal": {"score": 46.0, "contribution": 4.6},
            },
        },
        "openingExperience": {
            "collectorAppeal": {
                "score": 46.0,
                "version": COLLECTOR_APPEAL_V3_VERSION,
                "formulaVersion": COLLECTOR_APPEAL_V3_FORMULA_VERSION,
                "factors": {
                    "rosterDesirability": 0.40,
                    "desirableOutcomeFrequency": 0.30,
                    "dualPathDepth": 0.60,
                },
                "rank": 5,
                "cohortSize": 22,
            },
            "desirableOutcomeFrequency": {"rawValue": 0.30, "displayPercent": 30.0},
            "dualPathDepth": {"rawValue": 0.60, "displayPercent": 60.0},
            "coverage": {"status": "available", "reasons": []},
        },
        "universalSetDesirability": {"score": 40.0, "version": "universal_set_desirability_v3"},
        "rip": {}, "ripCore": {}, "overallRipV5": {}, "overallRipV6": {},
    }


def test_the_v7_contract_publishes_the_canonical_versions():
    """`public_rip_contract_v7` is structurally frozen at the Financial RIP V3 era:
    `canonicalOverallRipVersion` (V7), `canonicalCollectorAppealVersion` (V3), and
    `canonicalFinancialRipVersion` (V3) are all pinned historical literals, not the
    live `CANONICAL_FINANCIAL_RIP_VERSION` switch. Following the live constant would
    make this contract falsely declare a Financial RIP V4 identity while its
    `financialRip` payload still carries V3 numbers, so it must stay unchanged by
    the V4/V10 cutover."""
    contract = build_public_rip_contract_v7(_target())
    assert contract["contractVersion"] == PUBLIC_RIP_CONTRACT_V7_VERSION
    assert contract["canonicalOverallRipVersion"] == OVERALL_RIP_V7_VERSION
    assert contract["canonicalCollectorAppealVersion"] == COLLECTOR_APPEAL_V3_VERSION
    assert contract["canonicalFinancialRipVersion"] == FINANCIAL_RIP_V3_VERSION
    assert contract["overallRip"]["score"] == 59.5
    assert contract["collectorAppeal"]["score"] == 46.0


def test_the_collector_appeal_block_discloses_no_weight_and_no_formula():
    """The arithmetic is a one-line weighted sum.

    Publishing the weight vector would BE publishing the formula, and publishing
    a per-input contribution would be the same thing by division.
    """
    block = build_public_rip_contract_v7(_target())["collectorAppeal"]
    for withheld in COLLECTOR_APPEAL_WITHHELD_FIELDS:
        assert withheld not in block, withheld
    assert block["weightsDisclosed"] is False
    # The factor VALUES and high-level labels ARE published - each is already a
    # published metric in its own right; what stays internal is how they combine.
    assert block["components"]["rosterDesirability"]["rawValue"] == 0.40
    assert block["components"]["desirableOutcomeFrequency"]["rawValue"] == 0.30
    assert block["components"]["dualPathDepth"]["rawValue"] == 0.60
    assert {factor["label"] for factor in block["factorLabels"]} == {
        "Roster Desirability", "Desirable Outcome Frequency", "Dual-Path Depth"
    }


def test_the_overall_rip_block_does_publish_its_ninety_ten_split():
    """That split is a stated PRODUCT fact; hiding it would make the score
    unexplainable. Collector Appeal's internal composition is the thing that
    stays internal."""
    block = build_public_rip_contract_v7(_target())["overallRip"]
    assert block["components"]["financialRipV3"]["weight"] == 0.90
    assert block["components"]["collectorAppeal"]["weight"] == 0.10


def test_the_frequency_block_states_it_is_not_a_financial_metric():
    block = build_public_rip_contract_v7(_target())["collectorAppeal"]
    frequency = block["components"]["desirableOutcomeFrequency"]
    assert frequency["isFinancialMetric"] is False
    assert "worth less than the pack price" in frequency["disclaimer"]


def test_personal_fit_is_declared_as_a_future_pillar_with_no_score():
    contract = build_public_rip_contract_v7(_target())
    assert contract["personalFit"]["status"] == "not_implemented"
    assert "score" not in contract["personalFit"]


def test_an_unavailable_appeal_states_its_no_substitution_policy():
    target = _target()
    target["openingExperience"]["collectorAppeal"] = {
        "score": None,
        "version": COLLECTOR_APPEAL_V3_VERSION,
        "missingInputs": ["desirable_outcome_frequency"],
    }
    target["openingExperience"]["coverage"] = {
        "status": "unavailable",
        "reasons": ["desirable_outcome_frequency_unavailable_no_pull_model"],
    }
    block = build_public_rip_contract_v7(target)["collectorAppeal"]
    assert block["status"] == "unavailable"
    assert block["missingInputs"] == ["desirable_outcome_frequency"]
    assert "never substituted with zero" in block["fallbackPolicy"]
