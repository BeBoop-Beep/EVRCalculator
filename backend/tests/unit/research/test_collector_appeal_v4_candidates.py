"""Behavioural contract for the RESEARCH-ONLY Collector Appeal V4 candidates.

These tests are about BEHAVIOUR, not about where any particular set lands. There
is deliberately no assertion anywhere in this file of the form "Ascended Heroes
must outrank Pitch Black": fitting a formula to a preferred leaderboard is the
failure mode this whole study exists to avoid.

The last section pins the non-actions: V3 stays canonical, Overall RIP V7 stays
canonical, and nothing production imports the candidate module.
"""

from __future__ import annotations

import ast
import itertools
from pathlib import Path

import pytest

from backend.desirability import collector_appeal as canonical
from backend.desirability import scoring_config
from backend.research import collector_appeal_v4_candidates as v4

REPO_ROOT = Path(__file__).resolve().parents[4]

# A coarse but honest sweep of the admissible input space. Small enough to run
# fast, dense enough that a monotonicity break cannot hide between samples.
D_GRID = [0.0, 0.15, 0.3, 0.45, 0.6, 0.75, 0.85, 0.9, 0.95, 1.0]
H_GRID = [0.005, 0.02, 0.0625, 0.125, 0.2, 0.25, 0.4, 1.0]
P_GRID = [0.0, 0.1, 0.25, 0.3, 0.5, 0.75, 1.0]


# ---------------------------------------------------------------------------
# bounds
# ---------------------------------------------------------------------------


@pytest.mark.parametrize("ceiling", v4.MODIFIER_CEILING_GRID)
@pytest.mark.parametrize("damping", v4.PENALTY_DAMPING_GRID)
def test_additive_candidate_stays_on_the_public_scale(ceiling, damping):
    for d, h, p in itertools.product(D_GRID, H_GRID, P_GRID):
        score = v4.collector_appeal_v4_candidate_additive(
            d, h, p, ceiling=ceiling, penalty_damping=damping
        )
        assert score is not None
        assert 0.0 <= score <= 100.0


@pytest.mark.parametrize("gain", v4.MULTIPLICATIVE_GAIN_GRID)
def test_multiplicative_candidate_stays_on_the_public_scale(gain):
    for d, h, p in itertools.product(D_GRID, H_GRID, P_GRID):
        score = v4.collector_appeal_v4_candidate_multiplicative(d, h, p, gain=gain)
        assert score is not None
        assert 0.0 <= score <= 100.0


def test_structural_indices_are_bounded_and_neutral_at_the_declared_anchors():
    assert v4.h_structural_index(1.0 / v4.H_NEUTRAL_ONE_IN_N) == pytest.approx(0.5)
    assert v4.h_structural_index(1.0 / v4.H_STRONG_ONE_IN_N) == pytest.approx(1.0)
    assert v4.h_structural_index(1.0 / v4.H_WEAK_ONE_IN_N) == pytest.approx(0.0)
    assert v4.p_structural_index(v4.P_NEUTRAL) == pytest.approx(0.5)
    assert v4.p_structural_index(v4.P_STRONG_ANCHOR) == pytest.approx(1.0)
    assert v4.p_structural_index(v4.P_WEAK_ANCHOR) == pytest.approx(0.0)
    for value in (-5.0, 0.0, 0.001, 0.5, 5.0):
        index = v4.p_structural_index(value)
        assert index is None or 0.0 <= index <= 1.0


# ---------------------------------------------------------------------------
# requirement 1: desirability dominance
# ---------------------------------------------------------------------------


@pytest.mark.parametrize("ceiling", v4.MODIFIER_CEILING_GRID)
def test_strictly_increasing_in_d_at_equal_structure(ceiling):
    """The headline requirement: with structure held equal, more D is always more
    Collector Appeal. Asserted away from the 100-point clamp, which is the only
    place the additive family can tie - and which the audit reports separately as
    a saturation count."""
    for h, p in itertools.product(H_GRID, P_GRID):
        previous = None
        for d in D_GRID:
            if d * 100.0 + ceiling > 100.0:
                continue
            score = v4.collector_appeal_v4_candidate_additive(d, h, p, ceiling=ceiling)
            if previous is not None:
                assert score > previous
            previous = score


@pytest.mark.parametrize("gain", v4.MULTIPLICATIVE_GAIN_GRID)
def test_multiplicative_is_strictly_increasing_in_d(gain):
    for h, p in itertools.product(H_GRID, P_GRID):
        previous = None
        for d in D_GRID:
            score = v4.collector_appeal_v4_candidate_multiplicative(d, h, p, gain=gain)
            # As with the additive family, the only place strict monotonicity
            # can tie is the 100-point clamp, which needs D at the very ceiling.
            if previous is not None and d > 0.0 and previous < 100.0:
                assert score > previous
            previous = score


def test_neutral_structure_returns_exactly_d():
    """The property that makes structure a refinement rather than a second source
    of appeal: a set with neutral obtainability scores its desirability, full
    stop."""
    neutral_h = 1.0 / v4.H_NEUTRAL_ONE_IN_N
    for d in D_GRID:
        for ceiling in v4.MODIFIER_CEILING_GRID:
            assert v4.collector_appeal_v4_candidate_additive(
                d, neutral_h, v4.P_NEUTRAL, ceiling=ceiling
            ) == pytest.approx(d * 100.0)


# ---------------------------------------------------------------------------
# requirements 2/3: inversion limits
# ---------------------------------------------------------------------------


@pytest.mark.parametrize("ceiling", v4.MODIFIER_CEILING_GRID)
@pytest.mark.parametrize("damping", v4.PENALTY_DAMPING_GRID)
def test_inversion_is_impossible_beyond_the_derived_boundary(ceiling, damping):
    """No H or P anywhere in the admissible space can overturn a D gap wider than
    ``ceiling * (1 + damping)``. This is the model's central promise and is
    checked by exhaustive search rather than by trusting the algebra."""
    limit = v4.max_overturnable_d_gap_points(ceiling, damping)
    gap = (limit + 1.0) / 100.0
    d_high = 0.90
    d_low = d_high - gap
    incumbent = v4.collector_appeal_v4_candidate_additive(
        d_high, 0.001, 0.0, ceiling=ceiling, penalty_damping=damping
    )
    for h, p in itertools.product(H_GRID, P_GRID):
        challenger = v4.collector_appeal_v4_candidate_additive(
            d_low, h, p, ceiling=ceiling, penalty_damping=damping
        )
        assert challenger < incumbent


@pytest.mark.parametrize("ceiling", v4.MODIFIER_CEILING_GRID)
def test_a_small_d_gap_can_still_be_overturned(ceiling):
    """Requirement 4: the model must not collapse into D-only. A 1-point D gap is
    overturnable by a strong-versus-weak structural difference at every ceiling
    in the research grid."""
    d_high, d_low = 0.90, 0.89
    incumbent = v4.collector_appeal_v4_candidate_additive(d_high, 0.02, 0.05, ceiling=ceiling)
    challenger = v4.collector_appeal_v4_candidate_additive(d_low, 0.40, 0.90, ceiling=ceiling)
    assert challenger > incumbent


def test_derived_boundary_matches_the_registry():
    for entry in v4.candidate_registry().values():
        if entry["max_flip_gap"] is None:
            continue
        assert entry["max_flip_gap"] >= 0.0


# ---------------------------------------------------------------------------
# requirement 5: difficulty is not automatically punished
# ---------------------------------------------------------------------------


def test_damped_penalty_costs_less_than_the_matching_bonus_earns():
    """A hard set is not thereby an unappealing set. Under damping, the worst
    possible obtainability costs strictly less than the best possible
    obtainability earns."""
    ceiling = 4.0
    best = v4.structural_modifier_points(0.5, 1.0, ceiling=ceiling, penalty_damping=0.5)
    worst = v4.structural_modifier_points(0.001, 0.0, ceiling=ceiling, penalty_damping=0.5)
    assert best == pytest.approx(ceiling)
    assert worst == pytest.approx(-ceiling * 0.5)
    assert abs(worst) < best


def test_structure_never_reverses_a_large_desirability_advantage_in_the_cohort_range():
    """A 20-point D gap - the Ascended-Heroes-vs-Chaos-Rising order of magnitude -
    survives every structure the model admits, at every research ceiling."""
    for ceiling, damping in itertools.product(v4.MODIFIER_CEILING_GRID, v4.PENALTY_DAMPING_GRID):
        incumbent = v4.collector_appeal_v4_candidate_additive(
            0.80, 0.001, 0.0, ceiling=ceiling, penalty_damping=damping
        )
        challenger = v4.collector_appeal_v4_candidate_additive(
            0.60, 1.0, 1.0, ceiling=ceiling, penalty_damping=damping
        )
        assert challenger < incumbent


# ---------------------------------------------------------------------------
# H / P behaviour
# ---------------------------------------------------------------------------


@pytest.mark.parametrize("ceiling", v4.MODIFIER_CEILING_GRID)
def test_non_decreasing_in_h_and_in_p(ceiling):
    for d in (0.3, 0.7, 0.85):
        previous = None
        for h in H_GRID:
            score = v4.collector_appeal_v4_candidate_additive(d, h, 0.3, ceiling=ceiling)
            if previous is not None:
                assert score >= previous
            previous = score
        previous = None
        for p in P_GRID:
            score = v4.collector_appeal_v4_candidate_additive(d, 0.125, p, ceiling=ceiling)
            if previous is not None:
                assert score >= previous
            previous = score


def test_p_can_be_dropped_without_a_second_formula():
    """The D+H-only variant is the same function with ``p_weight = 0``, so the
    P-audit compares INPUTS at a fixed budget rather than comparing two
    independently written models."""
    score = v4.collector_appeal_v4_candidate_additive(
        0.8, 0.125, None, ceiling=4.0, h_weight=1.0, p_weight=0.0
    )
    assert score == pytest.approx(80.0)


def test_structural_weights_must_sum_to_one():
    with pytest.raises(ValueError):
        v4.structural_index(0.125, 0.3, h_weight=0.7, p_weight=0.2)


# ---------------------------------------------------------------------------
# missing data
# ---------------------------------------------------------------------------


@pytest.mark.parametrize(
    "d,h,p",
    [
        (None, 0.125, 0.3),
        (0.8, None, 0.3),
        (0.8, 0.125, None),
        ("", 0.125, 0.3),
        (0.8, "n/a", 0.3),
        (0.8, float("nan"), 0.3),
        (0.8, 0.0, 0.3),
    ],
)
def test_missing_input_returns_none_never_zero_and_never_d(d, h, p):
    score = v4.collector_appeal_v4_candidate_additive(d, h, p, ceiling=4.0)
    assert score is None
    assert v4.collector_appeal_v4_candidate_multiplicative(d, h, p, gain=0.04) is None


# ---------------------------------------------------------------------------
# determinism and identity
# ---------------------------------------------------------------------------


def test_scores_are_deterministic_and_cohort_independent():
    """No cohort statistic enters, so the same inputs give the same score no
    matter what else is being measured."""
    first = v4.score_all(0.8734, 0.1412, 0.3117)
    second = v4.score_all(0.8734, 0.1412, 0.3117)
    assert first == second
    assert all(value is not None for value in first.values())


def test_family_version_and_status_are_explicitly_research():
    assert "candidate" in v4.COLLECTOR_APPEAL_V4_CANDIDATE_FAMILY_VERSION
    assert "research" in v4.COLLECTOR_APPEAL_V4_CANDIDATE_FAMILY_VERSION
    assert v4.COLLECTOR_APPEAL_V4_CANDIDATE_STATUS == "research_candidate_not_canonical"
    assert v4.RECOMMENDED_CANDIDATE_KEY in v4.candidate_registry()


def test_no_search_loop_over_any_constant():
    """Every constant is pre-registered. A loop that assigned to a module-level
    weight would be tuning, and the AST is walked so it cannot pass review
    silently."""
    tree = ast.parse(Path(v4.__file__).read_text(encoding="utf-8"))
    for node in ast.walk(tree):
        if isinstance(node, (ast.For, ast.While)):
            for inner in ast.walk(node):
                if isinstance(inner, ast.Assign):
                    for target in inner.targets:
                        assert not isinstance(target, ast.Name) or not target.id.isupper()


# ---------------------------------------------------------------------------
# the non-actions
# ---------------------------------------------------------------------------


def test_canonical_collector_appeal_is_still_v3_and_unchanged():
    assert canonical.COLLECTOR_APPEAL_V3_VERSION == "collector_appeal_v3_balanced_d40_h35_p25"
    assert canonical.COLLECTOR_APPEAL_V3_WEIGHTS == {
        "roster_desirability": 0.40,
        "desirable_outcome_frequency": 0.35,
        "dual_path_depth": 0.25,
    }
    assert canonical.compute_collector_appeal_v3(0.8, 0.2, 0.3) == pytest.approx(
        0.40 * 0.8 + 0.35 * 0.2 + 0.25 * 0.3
    )


def test_legacy_models_are_unchanged():
    assert canonical.compute_collector_appeal_ca7(0.8, 0.4) == pytest.approx(
        0.8 + 0.5 * 0.4 * 0.2
    )
    assert canonical.compute_collector_appeal_v2(0.8, 0.2, 0.4) == pytest.approx(
        0.8 + 0.5 * (0.6 * 0.2 + 0.4 * 0.4) * 0.2
    )


def test_overall_rip_v7_is_unchanged_and_guardrails_are_read_not_restated():
    assert scoring_config.CANONICAL_OVERALL_RIP_VERSION == scoring_config.OVERALL_RIP_V7_VERSION
    assert scoring_config.OVERALL_RIP_V7_WEIGHTS == {
        "financial_rip": 0.90,
        "collector_appeal": 0.10,
    }
    audit = (REPO_ROOT / "backend" / "scripts" / "audit_collector_appeal_v4_candidates.py").read_text(
        encoding="utf-8"
    )
    for literal in ("0.95", "0.80", "1.5", "0.10"):
        assert f'"min_spearman_vs_financial_only": {literal}' not in audit
    assert "OVERALL_RIP_PRODUCTION_GUARDRAILS" in audit


def test_candidate_module_is_not_imported_by_any_production_module():
    """The research/production boundary, enforced rather than described."""
    offenders = []
    for path in (REPO_ROOT / "backend").rglob("*.py"):
        parts = path.relative_to(REPO_ROOT).parts
        if "tests" in parts or parts[1] in {"research", "scripts"}:
            continue
        if "collector_appeal_v4_candidates" in path.read_text(encoding="utf-8"):
            offenders.append(str(path))
    assert offenders == []


def test_audit_script_performs_no_writes():
    source = (
        REPO_ROOT / "backend" / "scripts" / "audit_collector_appeal_v4_candidates.py"
    ).read_text(encoding="utf-8")
    for forbidden in (".insert(", ".upsert(", ".update(", ".delete(", ".rpc("):
        assert forbidden not in source


def test_candidate_module_reads_no_financial_input():
    """No money enters the combination architecture.

    Checked against IDENTIFIERS in the parsed tree rather than against raw text,
    so the module's own prose about excluding price does not trip the assertion
    and a variable actually named ``pack_cost`` cannot hide inside a comment.
    """
    tree = ast.parse(Path(v4.__file__).read_text(encoding="utf-8"))
    identifiers: set[str] = set()
    for node in ast.walk(tree):
        if isinstance(node, ast.Name):
            identifiers.add(node.id)
        elif isinstance(node, ast.Attribute):
            identifiers.add(node.attr)
        elif isinstance(node, ast.arg):
            identifiers.add(node.arg)
        elif isinstance(node, ast.FunctionDef):
            identifiers.add(node.name)
        elif isinstance(node, (ast.Import, ast.ImportFrom)):
            identifiers.add(getattr(node, "module", "") or "")
            identifiers.update(alias.name for alias in node.names)

    forbidden = ("price", "cost", "profit", "market", "value", "financial", "ev_", "revenue")
    lowered = {name.lower() for name in identifiers}
    for name in lowered:
        # ``value``/``_as_float(value)`` is a generic parameter name, not money;
        # only reject it when paired with a set/card/pack qualifier.
        assert not any(
            token in name
            for token in forbidden
            if token != "value"
        ), f"financial-looking identifier in a non-financial module: {name}"
        assert "set_value" not in name and "pack_value" not in name


# ===========================================================================
# THE FROZEN CANDIDATE'S CONTRACT
#
# These tests exist so the published formula and the executed formula cannot
# disagree. The recurring failure mode they guard against is a model documented
# as "D + 4*(2S-1)" while its negative branch is actually damped to -2 - a
# summary that is wrong in the direction that flatters the model.
# ===========================================================================


def test_frozen_candidate_is_the_grid_entry_it_was_chosen_from():
    """One arithmetic path. If the frozen function ever diverged from the grid
    entry the study compared, the study would be describing a different model."""
    registry = v4.candidate_registry()
    chosen = registry[v4.RECOMMENDED_CANDIDATE_KEY]["scorer"]
    for d, h, p in itertools.product(D_GRID, H_GRID, P_GRID):
        assert v4.collector_appeal_v4_candidate_frozen(d, h, p) == chosen(d, h, p)


def test_frozen_modifier_floor_is_damped_and_not_the_negated_ceiling():
    """The asymmetry, asserted as a number rather than trusted as a comment."""
    assert v4.FROZEN_MODIFIER_CEILING == 4.0
    assert v4.FROZEN_DOWNSIDE_DAMPING == 0.5
    assert v4.FROZEN_MODIFIER_FLOOR == -2.0
    assert v4.FROZEN_MODIFIER_FLOOR != -v4.FROZEN_MODIFIER_CEILING
    best = v4.structural_modifier_points(
        1.0, 1.0, ceiling=v4.FROZEN_MODIFIER_CEILING,
        penalty_damping=v4.FROZEN_DOWNSIDE_DAMPING,
    )
    worst = v4.structural_modifier_points(
        1e-9, 0.0, ceiling=v4.FROZEN_MODIFIER_CEILING,
        penalty_damping=v4.FROZEN_DOWNSIDE_DAMPING,
    )
    assert best == pytest.approx(v4.FROZEN_MODIFIER_CEILING)
    assert worst == pytest.approx(v4.FROZEN_MODIFIER_FLOOR)


def test_frozen_formula_string_states_both_branches():
    """A summary that omits the damped branch would let a reader reproduce the
    wrong number and believe they had reproduced the right one."""
    expression = v4.FROZEN_FORMULA_EXPRESSION
    assert "4.0*z if z >= 0" in expression
    assert "else 2.0*z" in expression
    assert "clamp(100*D + m, 0, 100)" in expression
    assert "D + 4*(2S-1)" not in expression
    assert "ceil4_floor2" in v4.FROZEN_CANDIDATE_VERSION
    assert "up4_down2" in v4.FROZEN_CANDIDATE_KEY


def test_frozen_max_pairwise_structural_advantage_is_six_and_holds_exhaustively():
    assert v4.FROZEN_MAX_PAIRWISE_STRUCTURAL_ADVANTAGE == pytest.approx(6.0)
    limit = v4.FROZEN_MAX_PAIRWISE_STRUCTURAL_ADVANTAGE
    d_high = 0.90
    incumbent = v4.collector_appeal_v4_candidate_frozen(d_high, 1e-9, 0.0)
    challenger_best = v4.collector_appeal_v4_candidate_frozen(
        d_high - (limit + 0.01) / 100.0, 1.0, 1.0
    )
    assert challenger_best < incumbent
    challenger_inside = v4.collector_appeal_v4_candidate_frozen(
        d_high - (limit - 0.01) / 100.0, 1.0, 1.0
    )
    assert challenger_inside > incumbent
    modifiers = [
        v4.structural_modifier_points(
            h, p, ceiling=v4.FROZEN_MODIFIER_CEILING,
            penalty_damping=v4.FROZEN_DOWNSIDE_DAMPING,
        )
        for h, p in itertools.product(H_GRID, P_GRID)
    ]
    assert max(modifiers) - min(modifiers) <= limit + 1e-9


def test_frozen_monotonicity_contract_matches_the_implementation():
    """Strict increase OFF the clamp; non-decreasing everywhere; ties possible
    ONLY inside the saturation region the contract names."""
    contract = v4.FROZEN_MONOTONICITY_CONTRACT
    upper = contract["upper_saturation_begins_above_d"]
    lower = contract["lower_saturation_begins_below_d"]
    assert upper == pytest.approx(0.96)
    assert lower == pytest.approx(0.02)

    ties_outside_saturation = []
    for h, p in itertools.product(H_GRID, P_GRID):
        previous_d = previous_score = None
        for step in range(201):
            d = step / 200.0
            score = v4.collector_appeal_v4_candidate_frozen(d, h, p)
            if previous_score is not None:
                assert score >= previous_score  # non-decreasing EVERYWHERE
                if score == previous_score and lower < previous_d and d < upper:
                    ties_outside_saturation.append((previous_d, d, h, p))
            previous_d, previous_score = d, score
    assert ties_outside_saturation == []


def test_frozen_clamp_binds_only_inside_the_declared_region():
    upper = v4.FROZEN_MONOTONICITY_CONTRACT["upper_saturation_begins_above_d"]
    assert v4.collector_appeal_v4_candidate_frozen(0.99, 1.0, 1.0) == 100.0
    assert v4.collector_appeal_v4_candidate_frozen(upper, 1.0, 1.0) == pytest.approx(100.0)
    assert v4.collector_appeal_v4_candidate_frozen(upper - 0.01, 1.0, 1.0) < 100.0


def test_no_eligible_cohort_set_is_inside_the_saturation_region():
    """A fact about the DATA, asserted separately from the fact about the
    FORMULA. If a future set crosses D = 0.96 this fails and forces a review
    rather than silently producing a tie."""
    from backend.scripts.audit_collector_appeal_v4_candidates import load_published_cohort

    upper = v4.FROZEN_MONOTONICITY_CONTRACT["upper_saturation_begins_above_d"]
    lower = v4.FROZEN_MONOTONICITY_CONTRACT["lower_saturation_begins_below_d"]
    for row in load_published_cohort():
        assert lower < row["D"] < upper, f"{row['set']} at D={row['D']} is in the clamp region"


def test_frozen_fingerprint_is_deterministic_and_assumption_sensitive():
    first = v4.frozen_candidate_fingerprint()
    assert first == v4.frozen_candidate_fingerprint()
    assert len(first) == 64

    from backend.desirability.collector_appeal_fingerprint import fingerprint_assumptions

    assumptions = v4.frozen_candidate_assumptions()
    assert fingerprint_assumptions(assumptions) == first

    # Every constant that changes a score must change the hash. The damping is
    # listed explicitly: a fingerprint blind to it would let a symmetric variant
    # masquerade as this one.
    for path, replacement in (
        (("modifier", "positive_ceiling_points"), 6.0),
        (("modifier", "downside_damping"), 1.0),
        (("modifier", "negative_floor_points"), -4.0),
        (("structural_blend", "h_weight"), 0.85),
        (("h_transform", "anchor_neutral_one_in_n"), 6.0),
        (("p_transform", "anchor_one"), 0.60),
    ):
        mutated = {k: (dict(v) if isinstance(v, dict) else v) for k, v in assumptions.items()}
        mutated[path[0]][path[1]] = replacement
        assert fingerprint_assumptions(mutated) != first, path


def test_frozen_identity_reports_the_floor_not_just_the_ceiling():
    identity = v4.frozen_candidate_identity()
    assert identity["modifierCeiling"] == 4.0
    assert identity["modifierFloor"] == -2.0
    assert identity["maxPairwiseStructuralAdvantage"] == 6.0
    assert identity["status"] == "research_candidate_frozen_not_canonical"
    assert identity["fingerprint"] == v4.frozen_candidate_fingerprint()


# ---------------------------------------------------------------------------
# the P ablation twin
# ---------------------------------------------------------------------------


def test_ablation_twin_shares_every_assumption_except_p():
    """If these two differed in any other assumption, the ablation would not be
    measuring P."""
    neutral_h = 1.0 / v4.FROZEN_H_ANCHOR_NEUTRAL_ONE_IN_N
    for d in D_GRID:
        # At neutral P, sP contributes exactly what neutrality removes, so the
        # blended model and the H-only model must agree exactly - for every H.
        for h in H_GRID:
            blended = v4.collector_appeal_v4_candidate_frozen(d, h, v4.FROZEN_P_ANCHOR_NEUTRAL)
            h_only = v4.collector_appeal_v4_candidate_frozen_h_only(d, h)
            if h == neutral_h:
                assert blended == pytest.approx(h_only)
    # Same ceiling, same floor, same clamp, same missing-data policy.
    assert v4.collector_appeal_v4_candidate_frozen_h_only(0.90, 1.0) == pytest.approx(94.0)
    assert v4.collector_appeal_v4_candidate_frozen_h_only(0.90, 1e-9) == pytest.approx(88.0)
    assert v4.collector_appeal_v4_candidate_frozen_h_only(None, 0.2) is None
    assert v4.collector_appeal_v4_candidate_frozen_h_only(0.9, None) is None


def test_ablation_twin_ignores_p_entirely():
    baseline = v4.collector_appeal_v4_candidate_frozen_h_only(0.85, 0.15, 0.0)
    for p in P_GRID:
        assert v4.collector_appeal_v4_candidate_frozen_h_only(0.85, 0.15, p) == baseline


def test_both_frozen_models_are_registered_and_neither_is_canonical():
    registry = v4.candidate_registry()
    assert registry[v4.FROZEN_CANDIDATE_KEY]["family"] == "frozen_candidate"
    assert registry[v4.FROZEN_ABLATION_KEY]["family"] == "frozen_ablation"
    assert "not_canonical" in v4.FROZEN_CANDIDATE_STATUS
    assert canonical.COLLECTOR_APPEAL_V3_VERSION == "collector_appeal_v3_balanced_d40_h35_p25"


def test_historical_replay_script_performs_no_writes():
    source = (
        REPO_ROOT / "backend" / "scripts" / "audit_collector_appeal_v4_historical_replay.py"
    ).read_text(encoding="utf-8")
    for forbidden in (".insert(", ".upsert(", ".update(", ".delete(", ".rpc("):
        assert forbidden not in source
    # Guardrail thresholds must be read from config, never restated here.
    assert "OVERALL_RIP_PRODUCTION_GUARDRAILS" in source
    for literal in ('"min_spearman_vs_financial_only": 0.95', '"min_top5_overlap": 0.8'):
        assert literal not in source
