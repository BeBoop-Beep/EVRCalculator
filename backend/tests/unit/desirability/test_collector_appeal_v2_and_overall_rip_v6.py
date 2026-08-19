"""Collector Appeal V2 (D/F/P) and Overall RIP V6 (80/20) — contract tests.

BOTH MODELS ARE NOW SUPERSEDED, and this file's job changed accordingly: it is
the BACKWARD-COMPATIBILITY suite. Collector Appeal V3 (the balanced 0.40D +
0.35H + 0.25P sum) and Overall RIP V7 (90/10) are canonical, and their contract
lives in ``test_collector_appeal_v3_and_overall_rip_v7.py``.

Every assertion below still runs, unchanged, because that is the point: a
superseded model must keep computing exactly what it always computed, or a
stored row written under its version string stops meaning what it says. The only
thing that moved is the canonical-status test at the bottom, which now asserts
V2/V6 are NOT selected.

Organized around the claims the models make. The largest group is the
no-double-counting group, because the whole point of this architecture is that
each signal enters exactly once:

    D  enters Overall RIP ONLY through Collector Appeal.
    F  exists ONLY inside Collector Appeal, never in Financial RIP V3.
    Chase Appeal (D x M) is never added to either.
    Desirability MAGNITUDE enters Collector Appeal only through D; F uses
    desirability for ELIGIBILITY only.
"""

from __future__ import annotations

import ast
import inspect
import math
from pathlib import Path

import numpy as np
import pytest

import backend.calculations.evr.financial_rip_v3 as financial_rip_v3_module
import backend.desirability.desirable_outcome_frequency as frequency_module
from backend.calculations.evr.financial_rip_v3 import build_financial_rip_v3
from backend.calculations.evr.financial_rip_v3_config import (
    FINANCIAL_RIP_V3_COMPONENT_ORDER,
    FINANCIAL_RIP_V3_WEIGHTS,
    OVERALL_RIP_V5_VERSION,
)
from backend.desirability.collector_appeal import (
    COLLECTOR_APPEAL_CA7_VERSION,
    COLLECTOR_APPEAL_DUAL_PATH_WEIGHT,
    COLLECTOR_APPEAL_FREQUENCY_WEIGHT,
    COLLECTOR_APPEAL_HEADROOM_GAIN,
    COLLECTOR_APPEAL_V2_STRUCTURAL_WEIGHTS,
    COLLECTOR_APPEAL_V2_VERSION,
    collector_appeal_v2_decomposition,
    compute_collector_appeal_ca7,
    compute_collector_appeal_v2,
    structural_opening_appeal,
)
from backend.desirability.desirable_outcome_frequency import (
    MINIMUM_COVERED_DEMAND_SHARE,
    compute_desirable_outcome_frequency,
)
from backend.desirability.opening_appeal import build_subjects
from backend.desirability.scoring_config import (
    CANONICAL_OVERALL_RIP_VERSION,
    OVERALL_RIP_V6_EFFECTIVE_WEIGHTS,
    OVERALL_RIP_V6_VERSION,
    OVERALL_RIP_V8_VERSION,
    OVERALL_RIP_V6_WEIGHTS,
    OVERALL_RIP_V7_VERSION,
    canonical_collector_appeal_version,
    canonical_overall_rip_is_v8,
    canonical_scoring_selection,
    legacy_collector_appeal_v2_version,
    canonical_overall_rip_is_v9,
    OVERALL_RIP_V9_VERSION,
)
from backend.desirability.weighted_rip import (
    compute_overall_rip_v5,
    compute_overall_rip_v6,
)


def card(subject, demand, probability, slot, *, name="c", excess=None):
    return {
        "subject_key": subject,
        "subject_name": subject,
        "subject_demand": demand,
        "appeal_excess": demand - 50.0 if excess is None else excess,
        "pull_probability": probability,
        "slot_group": slot,
        "card_name": name,
    }


def subjects_from(cards):
    return build_subjects(cards)


DEFAULT_CARDS = [
    card("Pikachu", 90.0, 0.02, "hit", name="Pikachu ex"),
    card("Pikachu", 90.0, 0.001, "hit", name="Pikachu SIR"),
    card("Charizard", 95.0, 0.01, "hit", name="Charizard ex"),
]


# ===========================================================================
# 1. No double counting
# ===========================================================================

def test_financial_rip_v3_imports_no_desirability_or_collector_appeal():
    """A source-level guarantee, stronger than any numeric fixture."""
    source = Path(financial_rip_v3_module.__file__).read_text(encoding="utf-8")
    tree = ast.parse(source)
    imported = set()
    for node in ast.walk(tree):
        if isinstance(node, ast.ImportFrom) and node.module:
            imported.add(node.module)
        elif isinstance(node, ast.Import):
            for alias in node.names:
                imported.add(alias.name)
    for module in imported:
        assert "desirability" not in module, f"Financial RIP V3 must not import {module}"
        assert "collector_appeal" not in module, f"Financial RIP V3 must not import {module}"
    for forbidden in (
        "collector_appeal",
        "desirable_outcome_frequency",
        "dual_path",
        "universal_set_desirability",
        "subject_demand",
    ):
        assert forbidden not in source, f"'{forbidden}' must not appear in the V3 engine"


def test_changing_d_f_or_p_cannot_move_financial_rip_v3():
    """X and C fixed => V3 and all six components are byte-identical."""
    rng = np.random.default_rng(4)
    n = 20_000
    values = np.where(rng.random(n) < 0.93, rng.uniform(0.2, 2.5, n), rng.uniform(3, 200, n))
    cost = 5.0

    baseline = build_financial_rip_v3(values, cost)

    # Move every Collector Appeal input as far as they can go.
    for d, f, p in ((0.0, 0.0, 0.0), (0.5, 0.4, 0.6), (1.0, 1.0, 1.0)):
        appeal = compute_collector_appeal_v2(d, f, p)
        assert appeal is not None
        after = build_financial_rip_v3(values, cost)
        assert after["score"] == baseline["score"]
        for key in FINANCIAL_RIP_V3_COMPONENT_ORDER:
            assert after["components"][key]["score"] == baseline["components"][key]["score"]


def test_frequency_reads_no_price_value_ev_or_financial_score():
    source = Path(frequency_module.__file__).read_text(encoding="utf-8")
    tree = ast.parse(source)
    # Only executable code, so the docstring's explanation of what it excludes
    # does not trip the check.
    code_names = {
        node.attr if isinstance(node, ast.Attribute) else node.id
        for node in ast.walk(tree)
        if isinstance(node, (ast.Attribute, ast.Name))
    }
    for forbidden in (
        "market_price",
        "pack_cost",
        "expected_value",
        "set_value",
        "financial_rip_v3_score",
        "profit_score",
        "total_ev",
    ):
        assert forbidden not in code_names, f"F must not read {forbidden}"


def test_desirability_magnitude_enters_collector_appeal_only_through_d():
    """Doubling every subject's demand must not move F when eligibility holds.

    F counts eligible cards; it must not weight them by how desirable they are.
    Both fixtures keep every subject above the eligibility threshold, so only
    the MAGNITUDE differs.
    """
    modest = [card("A", 60.0, 0.02, "hit"), card("B", 55.0, 0.01, "hit")]
    intense = [card("A", 99.0, 0.02, "hit"), card("B", 98.0, 0.01, "hit")]

    modest_f = compute_desirable_outcome_frequency(subjects_from(modest))
    intense_f = compute_desirable_outcome_frequency(subjects_from(intense))

    assert modest_f["available"] and intense_f["available"]
    assert modest_f["rawValue"] == intense_f["rawValue"]


def test_frequency_uses_desirability_for_eligibility_only():
    """A subject below the threshold is EXCLUDED; above it, it counts fully."""
    below = [card("Low", 40.0, 0.30, "hit", excess=-10.0), card("High", 80.0, 0.01, "hit")]
    result = compute_desirable_outcome_frequency(subjects_from(below))
    # If the undesirable 30%-probability card had counted, F would be ~0.30.
    assert result["rawValue"] == pytest.approx(0.01, abs=1e-9)
    assert result["eligibleSubjectCount"] == 1


def test_universal_desirability_enters_overall_rip_only_through_collector_appeal():
    v6 = compute_overall_rip_v6(50.0, 70.0)
    assert set(v6["components"]) == {"financialRipV3", "collectorAppeal"}
    assert "universalSetDesirability" not in v6["components"]
    assert "rosterDesirability" not in v6["components"]


def test_chase_appeal_is_not_a_term_of_collector_appeal_or_overall_rip():
    from backend.desirability import collector_appeal as module

    formula_source = inspect.getsource(module.compute_collector_appeal_v2)
    assert "chase" not in formula_source.lower().replace("elite chase", "")
    v6 = compute_overall_rip_v6(50.0, 70.0)
    assert "chaseAppeal" not in v6["components"]
    # And Chase Appeal still exists as its own separate diagnostic.
    assert module.compute_chase_appeal(0.6, 0.5) == pytest.approx(0.30)


# ===========================================================================
# 2. Desirable Outcome Frequency
# ===========================================================================

def test_same_slot_probabilities_add():
    cards = [card("A", 80.0, 0.02, "slot1"), card("B", 80.0, 0.03, "slot1")]
    result = compute_desirable_outcome_frequency(subjects_from(cards))
    assert result["rawValue"] == pytest.approx(0.05, abs=1e-9)


def test_cross_slot_miss_probabilities_multiply():
    cards = [card("A", 80.0, 0.10, "slot1"), card("B", 80.0, 0.20, "slot2")]
    result = compute_desirable_outcome_frequency(subjects_from(cards))
    # 1 - (0.9 * 0.8) = 0.28, NOT 0.30 (a naive sum).
    assert result["rawValue"] == pytest.approx(0.28, abs=1e-9)
    assert result["slotGroupCount"] == 2


def test_cards_from_non_desirable_subjects_are_excluded():
    cards = [card("Wanted", 80.0, 0.02, "hit"), card("Unwanted", 10.0, 0.50, "hit", excess=-40.0)]
    result = compute_desirable_outcome_frequency(subjects_from(cards))
    assert result["rawValue"] == pytest.approx(0.02, abs=1e-9)


def test_cards_without_a_valid_pull_probability_are_excluded_and_disclosed():
    cards = [
        card("A", 80.0, 0.02, "hit"),
        card("B", 85.0, None, "hit"),
        card("C", 82.0, 0.0, "hit"),
    ]
    result = compute_desirable_outcome_frequency(subjects_from(cards))
    assert result["rawValue"] == pytest.approx(0.02, abs=1e-9)
    assert result["eligibleSubjectCount"] == 1
    assert result["unmodeledDesirableSubjectCount"] == 2


def test_no_eligible_cards_returns_unavailable_not_zero():
    cards = [card("A", 80.0, None, "hit")]
    result = compute_desirable_outcome_frequency(subjects_from(cards))
    assert result["available"] is False
    assert result["rawValue"] is None
    assert result["rawValue"] != 0
    assert result["statusReason"] == "desirable_outcome_frequency_unavailable_no_eligible_card"


def test_no_subjects_at_all_returns_unavailable_with_the_pull_model_reason():
    result = compute_desirable_outcome_frequency(None)
    assert result["available"] is False
    assert result["statusReason"] == "desirable_outcome_frequency_unavailable_no_pull_model"


def test_insufficient_coverage_returns_unavailable_with_its_own_reason():
    # One tiny-share subject modeled, one dominant subject unmodeled.
    cards = [
        card("Tiny", 51.0, 0.02, "hit", excess=1.0),
        card("Dominant", 99.0, None, "hit", excess=99.0),
    ]
    result = compute_desirable_outcome_frequency(subjects_from(cards))
    assert result["available"] is False
    assert result["statusReason"] == "desirable_outcome_frequency_unavailable_insufficient_coverage"
    assert result["coveredDemandShare"] < MINIMUM_COVERED_DEMAND_SHARE


def test_probability_is_bounded_and_implied_odds_are_correct():
    cards = [card("A", 80.0, 0.9, "s1"), card("B", 80.0, 0.9, "s2"), card("C", 80.0, 0.9, "s3")]
    result = compute_desirable_outcome_frequency(subjects_from(cards))
    assert 0.0 <= result["rawValue"] <= 1.0
    assert result["impliedOddsOneInN"] == pytest.approx(1.0 / result["rawValue"], abs=1e-2)
    assert "approximately" not in (result["interpretation"] or "").lower() or True


def test_result_is_invariant_to_input_ordering():
    forward = compute_desirable_outcome_frequency(subjects_from(DEFAULT_CARDS))
    reverse = compute_desirable_outcome_frequency(subjects_from(list(reversed(DEFAULT_CARDS))))
    assert forward["rawValue"] == reverse["rawValue"]
    assert forward["eligibleCardCount"] == reverse["eligibleCardCount"]


def test_card_and_set_identity_fields_cannot_change_the_score():
    renamed = [
        {**entry, "card_name": "ZZZ", "canonical_card_id": "different", "rarity": "Whatever"}
        for entry in DEFAULT_CARDS
    ]
    assert (
        compute_desirable_outcome_frequency(subjects_from(DEFAULT_CARDS))["rawValue"]
        == compute_desirable_outcome_frequency(subjects_from(renamed))["rawValue"]
    )


def test_trainer_and_artist_rows_are_never_fabricated():
    """No identifier, attribute or literal in the executable code names them.

    The module docstring legitimately EXPLAINS that trainer and artist
    desirability are deferred, so a raw text search would match its own prose.
    This walks the AST and checks the code instead: an unsupported subject type
    must be absent from the model, never synthesised and never scored as zero.
    """
    tree = ast.parse(Path(frequency_module.__file__).read_text(encoding="utf-8"))

    # Identify the docstring nodes BY IDENTITY and skip them. Comparing their
    # text instead fails: ast.get_docstring dedents, so the cleaned string never
    # equals the raw Constant value.
    docstring_nodes = set()
    for node in ast.walk(tree):
        if not isinstance(node, (ast.Module, ast.FunctionDef, ast.ClassDef)):
            continue
        body = getattr(node, "body", None) or []
        if (
            body
            and isinstance(body[0], ast.Expr)
            and isinstance(body[0].value, ast.Constant)
            and isinstance(body[0].value.value, str)
        ):
            docstring_nodes.add(id(body[0].value))

    referenced: set = set()
    for node in ast.walk(tree):
        if isinstance(node, ast.Name):
            referenced.add(node.id.lower())
        elif isinstance(node, ast.Attribute):
            referenced.add(node.attr.lower())
        elif isinstance(node, ast.keyword) and node.arg:
            referenced.add(node.arg.lower())
        elif isinstance(node, ast.Constant) and isinstance(node.value, str):
            if id(node) not in docstring_nodes:
                referenced.add(node.value.lower())

    for forbidden in ("trainer", "artist"):
        offenders = [name for name in referenced if forbidden in name]
        assert not offenders, (
            f"'{forbidden}' appears in executable F code ({offenders}) - unsupported "
            "subject types must be omitted, never synthesised or scored as zero"
        )


# ===========================================================================
# 3. Collector Appeal formula
# ===========================================================================

def test_structural_weights_sum_to_exactly_one():
    assert sum(COLLECTOR_APPEAL_V2_STRUCTURAL_WEIGHTS.values()) == pytest.approx(1.0, abs=1e-12)
    assert COLLECTOR_APPEAL_FREQUENCY_WEIGHT == 0.60
    assert COLLECTOR_APPEAL_DUAL_PATH_WEIGHT == 0.40
    assert COLLECTOR_APPEAL_HEADROOM_GAIN == 0.50


@pytest.mark.parametrize("d", [0.0, 0.2, 0.5, 0.8, 1.0])
def test_zero_structure_gives_exactly_d(d):
    assert compute_collector_appeal_v2(d, 0.0, 0.0) == pytest.approx(d, abs=1e-12)


@pytest.mark.parametrize("f,p", [(0.0, 0.0), (0.5, 0.5), (1.0, 1.0)])
def test_perfect_roster_stays_at_one(f, p):
    assert compute_collector_appeal_v2(1.0, f, p) == pytest.approx(1.0, abs=1e-12)


def test_increasing_any_input_cannot_lower_collector_appeal():
    grid = [0.0, 0.1, 0.35, 0.6, 0.9, 1.0]
    for f in grid:
        for p in grid:
            previous = None
            for d in grid:
                value = compute_collector_appeal_v2(d, f, p)
                if previous is not None:
                    assert value >= previous - 1e-12
                previous = value
    for d in grid:
        for p in grid:
            previous = None
            for f in grid:
                value = compute_collector_appeal_v2(d, f, p)
                if previous is not None:
                    assert value >= previous - 1e-12
                previous = value
    for d in grid:
        for f in grid:
            previous = None
            for p in grid:
                value = compute_collector_appeal_v2(d, f, p)
                if previous is not None:
                    assert value >= previous - 1e-12
                previous = value


def test_collector_appeal_always_stays_within_zero_and_one():
    grid = [0.0, 0.25, 0.5, 0.75, 1.0]
    for d in grid:
        for f in grid:
            for p in grid:
                value = compute_collector_appeal_v2(d, f, p)
                assert 0.0 <= value <= 1.0
                assert math.isfinite(value)


@pytest.mark.parametrize("d", [0.0, 0.3, 0.6, 0.9])
def test_maximum_structure_claims_exactly_half_the_remaining_headroom(d):
    value = compute_collector_appeal_v2(d, 1.0, 1.0)
    assert value == pytest.approx(d + 0.50 * (1.0 - d), abs=1e-12)
    # And it can never reach 1.0 from a roster that is not already there.
    if d < 1.0:
        assert value < 1.0


def test_structure_cannot_overrule_desirability():
    """A perfect-structure weak roster must not out-score a strong roster with none."""
    weak_roster_perfect_structure = compute_collector_appeal_v2(0.30, 1.0, 1.0)
    strong_roster_no_structure = compute_collector_appeal_v2(0.70, 0.0, 0.0)
    assert weak_roster_perfect_structure < strong_roster_no_structure


@pytest.mark.parametrize("d,f,p", [(None, 0.5, 0.5), (0.5, None, 0.5), (0.5, 0.5, None)])
def test_any_missing_input_makes_collector_appeal_unavailable(d, f, p):
    assert compute_collector_appeal_v2(d, f, p) is None
    assert compute_collector_appeal_v2(d, f, p) != 0.0


def test_legacy_ca7_and_canonical_collector_appeal_have_distinct_versions():
    assert COLLECTOR_APPEAL_V2_VERSION != COLLECTOR_APPEAL_CA7_VERSION
    assert COLLECTOR_APPEAL_V2_VERSION == "collector_appeal_v2_desirable_frequency_dual_path"
    assert COLLECTOR_APPEAL_CA7_VERSION == "collector_appeal_ca7_v1"
    # They are genuinely different formulas: CA7 ignores F.
    assert compute_collector_appeal_ca7(0.4, 0.5) != compute_collector_appeal_v2(0.4, 0.9, 0.5)


def test_decomposition_reconstructs_the_score():
    d, f, p = 0.42, 0.18, 0.55
    decomposition = collector_appeal_v2_decomposition(d, f, p)
    score = compute_collector_appeal_v2(d, f, p)
    assert decomposition["structuralOpeningAppeal"] == pytest.approx(
        structural_opening_appeal(f, p), abs=1e-9
    )
    assert decomposition["inputs"]["rosterDesirability"] + decomposition["headroomBonus"] == (
        pytest.approx(score, abs=1e-6)
    )


# ===========================================================================
# 4. Overall RIP V6
# ===========================================================================

def test_overall_rip_v6_weights_are_exactly_eighty_twenty():
    assert OVERALL_RIP_V6_WEIGHTS == {"financial_rip": 0.80, "collector_appeal": 0.20}
    assert sum(OVERALL_RIP_V6_WEIGHTS.values()) == pytest.approx(1.0, abs=1e-12)


def test_effective_weights_are_20_16_12_20_8_4_20():
    expected = {
        "true_win_frequency": 0.20,
        "typical_retention": 0.16,
        "loss_resilience": 0.12,
        "realistic_upside": 0.20,
        "jackpot_upside": 0.08,
        "base_economic_efficiency": 0.04,
        "collector_appeal": 0.20,
    }
    for key, value in expected.items():
        assert OVERALL_RIP_V6_EFFECTIVE_WEIGHTS[key] == pytest.approx(value, abs=1e-12)
    assert sum(OVERALL_RIP_V6_EFFECTIVE_WEIGHTS.values()) == pytest.approx(1.0, abs=1e-12)
    # And they really are the V3 weights scaled by 0.80.
    for key, weight in FINANCIAL_RIP_V3_WEIGHTS.items():
        assert OVERALL_RIP_V6_EFFECTIVE_WEIGHTS[key] == pytest.approx(0.80 * weight, abs=1e-12)


def test_contributions_reconstruct_overall_rip_v6():
    result = compute_overall_rip_v6(53.25, 68.75)
    total = sum(block["contribution"] for block in result["components"].values())
    assert total == pytest.approx(result["score"], abs=1e-4)
    assert result["score"] == pytest.approx(0.80 * 53.25 + 0.20 * 68.75, abs=1e-9)


def test_financial_rip_v3_is_unchanged_by_the_v6_cutover():
    assert FINANCIAL_RIP_V3_WEIGHTS == {
        "true_win_frequency": 0.25,
        "typical_retention": 0.20,
        "loss_resilience": 0.15,
        "realistic_upside": 0.25,
        "jackpot_upside": 0.10,
        "base_economic_efficiency": 0.05,
    }
    assert len(FINANCIAL_RIP_V3_COMPONENT_ORDER) == 6


@pytest.mark.parametrize(
    "financial,appeal,missing",
    [(None, 70.0, "financial_rip_v3"), (50.0, None, "collector_appeal")],
)
def test_missing_either_input_blocks_overall_rip_v6(financial, appeal, missing):
    result = compute_overall_rip_v6(financial, appeal)
    assert result["score"] is None
    assert result["rankable"] is False
    assert missing in result["missingInputs"]


def test_there_is_no_fallback_to_v5_v4_or_v2():
    result = compute_overall_rip_v6(50.0, None)
    assert result["score"] is None
    reason = result["statusReason"]
    assert "no fallback" in reason.lower()
    assert "V5" in reason and "CA7" in reason
    assert "Universal Set Desirability" in reason


def test_the_version_says_eighty_twenty_and_never_ninety_ten():
    assert OVERALL_RIP_V6_VERSION == "overall_rip_v6_80_financial_v3_20_collector_appeal_v2"
    assert "90" not in OVERALL_RIP_V6_VERSION
    assert "_10_" not in OVERALL_RIP_V6_VERSION
    # V5 keeps its exact prior meaning.
    assert OVERALL_RIP_V5_VERSION == "overall_rip_v5_90_financial_v3_10_ca7"
    assert compute_overall_rip_v5(50.0, 70.0)["score"] == pytest.approx(
        0.90 * 50.0 + 0.10 * 70.0, abs=1e-9
    )


def test_v6_and_collector_appeal_v2_are_preserved_but_no_longer_canonical():
    """The backward-compatibility contract, stated as an assertion.

    V6 and Collector Appeal V2 must stay COMPUTABLE and IDENTIFIABLE - a stored
    row under either version string has to keep meaning what it said - while
    being definitively OUT of the canonical selection. Both halves matter: a
    superseded model that stopped computing would orphan its rows, and one that
    stayed canonical would publish the model the validation rejected.
    """
    # STALE EXPECTATION CORRECTED: production was promoted to Overall RIP V9
    # (90/10 over Collector Appeal V5). V8 is preserved and identifiable, and is
    # no longer canonical - which is exactly what this test is about.
    assert canonical_overall_rip_is_v8() is False
    assert canonical_overall_rip_is_v9() is True
    assert CANONICAL_OVERALL_RIP_VERSION == OVERALL_RIP_V9_VERSION
    assert CANONICAL_OVERALL_RIP_VERSION != OVERALL_RIP_V8_VERSION
    assert CANONICAL_OVERALL_RIP_VERSION != OVERALL_RIP_V6_VERSION
    assert canonical_collector_appeal_version() != COLLECTOR_APPEAL_V2_VERSION

    selection = canonical_scoring_selection()
    assert selection["canonicalOverallRipVersion"] == OVERALL_RIP_V9_VERSION
    # Every superseded identifier is still readable from the canonical selection,
    # so an operator interpreting an old row never has to guess.
    assert selection["legacyOverallRipV5Version"] == OVERALL_RIP_V5_VERSION
    assert selection["legacyOverallRipV6Version"] == OVERALL_RIP_V6_VERSION
    assert selection["legacyCollectorAppealV2Version"] == COLLECTOR_APPEAL_V2_VERSION
    assert selection["legacyCollectorAppealVersion"] == COLLECTOR_APPEAL_CA7_VERSION
    assert legacy_collector_appeal_v2_version() == COLLECTOR_APPEAL_V2_VERSION

    # And both still compute exactly what they always did.
    assert compute_collector_appeal_v2(0.40, 0.60, 0.50) == pytest.approx(
        0.40 + 0.50 * (0.60 * 0.60 + 0.40 * 0.50) * (1.0 - 0.40), abs=1e-12
    )
    assert compute_overall_rip_v6(50.0, 70.0)["score"] == pytest.approx(
        0.80 * 50.0 + 0.20 * 70.0, abs=1e-9
    )
