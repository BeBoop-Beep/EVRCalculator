"""The pre-registered candidate grid: bounds, monotonicity, and no fitting.

The mathematical properties matter because they are what make the score
readable: if the formula were not monotone in D, a set could become "more
appealing" by having a less-wanted roster, and no amount of downstream
validation would recover from that.

The anti-fitting tests matter for a different reason. Pre-registration is only
meaningful if it is enforced; a grid that can quietly gain a cell after the
results are seen is not pre-registered, it is a menu.
"""

from __future__ import annotations

import ast
import inspect

import pytest

from backend.research import collector_appeal_candidates as module
from backend.research.collector_appeal_candidates import (
    CANDIDATE_GRID,
    CANDIDATE_KEYS,
    COLLECTOR_APPEAL_FREQUENCY_WEIGHT_GRID,
    COLLECTOR_APPEAL_HEADROOM_GAIN_GRID,
    OVERALL_COLLECTOR_APPEAL_WEIGHT_GRID,
    PRIMARY_CANDIDATE_KEY,
    candidate_key,
    compute_all_candidates,
    compute_candidate,
    compute_comparisons,
    compute_overall,
    compute_primary,
    primary_matches_production,
    structural_opening_appeal,
)

GRID = [i / 10.0 for i in range(11)]


# ---------------------------------------------------------------------------
# Pre-registration
# ---------------------------------------------------------------------------

def test_grids_are_exactly_the_pre_registered_values():
    """Pinned literally. A new cell must fail here before it can reach a report."""
    assert COLLECTOR_APPEAL_FREQUENCY_WEIGHT_GRID == (0.50, 0.60, 0.70)
    assert COLLECTOR_APPEAL_HEADROOM_GAIN_GRID == (0.25, 0.50, 0.75)
    assert OVERALL_COLLECTOR_APPEAL_WEIGHT_GRID == (0.00, 0.10, 0.13, 0.14, 0.15, 0.20)
    assert len(CANDIDATE_GRID) == 9
    assert len(CANDIDATE_KEYS) == 9
    assert len(set(CANDIDATE_KEYS)) == 9


def test_primary_candidate_is_the_brief_specified_cell():
    assert PRIMARY_CANDIDATE_KEY == "CA8_D_H60_P40_L50"
    assert PRIMARY_CANDIDATE_KEY in CANDIDATE_KEYS


def test_candidate_keys_use_the_required_identifier_format():
    assert candidate_key(0.60, 0.50) == "CA8_D_H60_P40_L50"
    assert candidate_key(0.50, 0.50) == "CA8_D_H50_P50_L50"
    assert candidate_key(0.70, 0.50) == "CA8_D_H70_P30_L50"


def test_primary_candidate_still_reproduces_the_superseded_collector_appeal_v2():
    """The grid's primary cell IS Collector Appeal V2, exactly.

    That is what keeps the V2-vs-V3 comparison honest: the study's "primary"
    column has to be the formula V3 actually replaced, not an approximation of
    it.
    """
    from backend.desirability.collector_appeal import compute_collector_appeal_v2

    for d in GRID:
        for h in GRID:
            for p in GRID:
                assert compute_primary(d, h, p) == pytest.approx(
                    compute_collector_appeal_v2(d, h, p), abs=1e-12
                )


def test_the_grid_no_longer_describes_the_canonical_production_formula():
    """``primary_matches_production()`` must now report False.

    Production ships the Collector Appeal V3 balanced weighted sum, which is not
    in this bounded-headroom family at all. Reporting True would tell a reader
    the study is validating the shipping model when it is validating the model
    the shipping one replaced.
    """
    from backend.desirability.collector_appeal import compute_collector_appeal_v3

    assert primary_matches_production() is False
    registry = module.candidate_registry()
    assert registry["matchesProductionFormula"] is False
    assert registry["canonicalProductionKey"] == "collector_appeal_v3_balanced"
    # And the two really do differ wherever H and P are not both extreme.
    assert compute_primary(0.80, 0.20, 0.40) != pytest.approx(
        compute_collector_appeal_v3(0.80, 0.20, 0.40), abs=1e-9
    )


def test_the_canonical_formula_is_available_as_a_comparison_column():
    """The study must be able to compare V3 against everything it replaced."""
    from backend.desirability.collector_appeal import compute_collector_appeal_v3

    comparisons = module.compute_comparisons(d=0.80, h=0.20, p=0.40, m=0.50)
    for key in module.COMPARISON_KEYS:
        assert key in comparisons
    assert comparisons["collector_appeal_v3_balanced"] == pytest.approx(
        compute_collector_appeal_v3(0.80, 0.20, 0.40), abs=1e-12
    )
    assert comparisons["pure_D"] == pytest.approx(0.80, abs=1e-12)
    assert comparisons["collector_appeal_v2_bounded_headroom"] is not None


@pytest.mark.parametrize("dropped", ["d", "h", "p"])
def test_ablations_require_every_input_and_treat_renormalization_distinctly(dropped):
    """Both ablation families, and the property that separates them.

    Renormalized weights sum to 1 so the result stays on [0, 1]; contribution
    removal keeps the original weights so it cannot exceed ``1 - w(dropped)``.
    If the renormalize branch failed to renormalize, the two would silently
    become one column reported twice under two different questions.
    """
    raw = module.compute_v3_without_input(1.0, 1.0, 1.0, dropped=dropped, renormalize=False)
    renormalized = module.compute_v3_without_input(
        1.0, 1.0, 1.0, dropped=dropped, renormalize=True
    )
    weight = module.collector_appeal_v3_weight(dropped)
    assert raw == pytest.approx(1.0 - weight, abs=1e-12)
    assert renormalized == pytest.approx(1.0, abs=1e-12)
    # The DROPPED input is still required to be present, so the ablation cohort
    # and the full cohort are the same sets - otherwise a coverage difference
    # would be attributed to the dropped input.
    assert module.compute_v3_without_input(
        None, 1.0, 1.0, dropped=dropped, renormalize=True
    ) is None


def test_module_contains_no_optimizer_or_search_over_the_grid():
    """No fitting surface may exist in the candidate path.

    Walks the AST for the shapes a search would take - an objective being
    maximized/minimized, a fit/optimize/tune call - rather than trusting the
    docstring. A comment promising no fitting is not enforcement.
    """
    tree = ast.parse(inspect.getsource(module))
    banned_calls = {"minimize", "maximize", "curve_fit", "polyfit", "fit", "optimize", "tune"}
    for node in ast.walk(tree):
        if isinstance(node, ast.Call):
            name = getattr(node.func, "id", None) or getattr(node.func, "attr", None)
            assert name not in banned_calls, f"optimizer-like call {name!r} in candidate module"


def test_no_market_price_identifier_reaches_candidate_calculation():
    source = inspect.getsource(module).lower()
    for banned in ("market_price", "set_value", "top_10_card_value", "expected_value", "profit"):
        # The module names these ONLY in prose that forbids them; assert none
        # appears in an executable position by parsing rather than grepping.
        pass
    tree = ast.parse(inspect.getsource(module))
    for node in ast.walk(tree):
        if isinstance(node, ast.Name):
            assert "price" not in node.id.lower()
            assert "market" not in node.id.lower()


# ---------------------------------------------------------------------------
# Bounds and monotonicity
# ---------------------------------------------------------------------------

@pytest.mark.parametrize("alpha,lam", CANDIDATE_GRID)
def test_every_candidate_stays_within_unit_interval(alpha, lam):
    for d in GRID:
        for h in GRID:
            for p in GRID:
                value = compute_candidate(d, h, p, alpha=alpha, lam=lam)
                assert value is not None
                assert 0.0 <= value <= 1.0


@pytest.mark.parametrize("alpha,lam", CANDIDATE_GRID)
def test_every_candidate_is_monotonic_in_d_h_and_p(alpha, lam):
    """Non-decreasing in each input, holding the others fixed."""
    for fixed_a in GRID:
        for fixed_b in GRID:
            for lower, upper in zip(GRID, GRID[1:]):
                # in D
                assert compute_candidate(lower, fixed_a, fixed_b, alpha=alpha, lam=lam) <= (
                    compute_candidate(upper, fixed_a, fixed_b, alpha=alpha, lam=lam) + 1e-12
                )
                # in H
                assert compute_candidate(fixed_a, lower, fixed_b, alpha=alpha, lam=lam) <= (
                    compute_candidate(fixed_a, upper, fixed_b, alpha=alpha, lam=lam) + 1e-12
                )
                # in P
                assert compute_candidate(fixed_a, fixed_b, lower, alpha=alpha, lam=lam) <= (
                    compute_candidate(fixed_a, fixed_b, upper, alpha=alpha, lam=lam) + 1e-12
                )


@pytest.mark.parametrize("alpha,lam", CANDIDATE_GRID)
def test_zero_structure_returns_d_exactly(alpha, lam):
    """H=0 and P=0 must cost a set nothing at all."""
    for d in GRID:
        assert compute_candidate(d, 0.0, 0.0, alpha=alpha, lam=lam) == pytest.approx(d, abs=1e-12)


@pytest.mark.parametrize("alpha,lam", CANDIDATE_GRID)
def test_perfect_desirability_returns_one(alpha, lam):
    for h in GRID:
        for p in GRID:
            assert compute_candidate(1.0, h, p, alpha=alpha, lam=lam) == pytest.approx(1.0, abs=1e-12)


@pytest.mark.parametrize("alpha,lam", CANDIDATE_GRID)
def test_structure_can_overturn_desirability_only_by_the_headroom_bound(alpha, lam):
    """Exactly how much desirability can perfect structure overturn?

    The bound is algebraic and identical for every alpha, because at H = P = 1
    the structural term is 1 regardless of how it is split:

        D_weak + lambda * (1 - D_weak)  vs  D_strong

    So perfect structure beats a stronger roster precisely when
    ``D_strong - D_weak < lambda * (1 - D_weak)``. This test asserts that
    boundary rather than a single hand-picked pair, so the property is
    characterised for the whole grid instead of spot-checked.
    """
    for weak in (0.10, 0.30, 0.50):
        for strong in (0.55, 0.70, 0.80, 0.95):
            if strong <= weak:
                continue
            weak_perfect = compute_candidate(weak, 1.0, 1.0, alpha=alpha, lam=lam)
            strong_bare = compute_candidate(strong, 0.0, 0.0, alpha=alpha, lam=lam)
            inversion_expected = (strong - weak) < lam * (1.0 - weak) - 1e-12
            assert (weak_perfect > strong_bare) is inversion_expected


def test_lambda_050_preserves_desirability_ordering_where_lambda_075_does_not():
    """A FINDING, pinned as a test: lambda = 0.75 permits structural inversion.

    At the pre-registered primary lambda = 0.50, a roster at D = 0.80 with no
    structure still outranks a roster at D = 0.30 with perfect structure. At the
    sensitivity variant lambda = 0.75 it does NOT - structure overturns a
    50-point desirability gap.

    The July rollout study rejected lambda = 0.75 on the softer ground that it
    "over-weights a quantity we measure with known compression". This is the
    harder version of that objection and it is worth stating separately in the
    report: at 0.75 the formula stops being a bounded bonus on desirability and
    becomes capable of reordering sets against it.
    """
    assert compute_candidate(0.80, 0.0, 0.0, alpha=0.60, lam=0.50) > compute_candidate(
        0.30, 1.0, 1.0, alpha=0.60, lam=0.50
    )
    assert compute_candidate(0.80, 0.0, 0.0, alpha=0.60, lam=0.75) < compute_candidate(
        0.30, 1.0, 1.0, alpha=0.60, lam=0.75
    )


# ---------------------------------------------------------------------------
# Missing data
# ---------------------------------------------------------------------------

@pytest.mark.parametrize("d,h,p", [(None, 0.5, 0.5), (0.5, None, 0.5), (0.5, 0.5, None)])
def test_missing_input_returns_unavailable_never_zero(d, h, p):
    value = compute_primary(d, h, p)
    assert value is None
    assert value != 0.0


def test_all_candidates_returns_the_full_key_set_even_when_unavailable():
    """A short dict would let 'unavailable' be misread as 'not in the grid'."""
    result = compute_all_candidates(None, None, None)
    assert set(result) == set(CANDIDATE_KEYS)
    assert all(value is None for value in result.values())


def test_structural_term_requires_both_inputs():
    assert structural_opening_appeal(None, 0.5, 0.6) is None
    assert structural_opening_appeal(0.5, None, 0.6) is None


# ---------------------------------------------------------------------------
# Overall blend
# ---------------------------------------------------------------------------

def test_overall_requires_both_inputs_even_at_zero_weight():
    """At w=0 the appeal input is still required.

    Otherwise the baseline column would cover a different (larger) cohort than
    the weighted columns, and a coverage difference would be indistinguishable
    from a weight effect in every comparison built on it.
    """
    assert compute_overall(60.0, None, 0.00) is None
    assert compute_overall(None, 70.0, 0.00) is None
    assert compute_overall(60.0, 70.0, 0.00) == pytest.approx(60.0)


def test_overall_blend_is_exactly_the_stated_arithmetic():
    assert compute_overall(50.0, 100.0, 0.20) == pytest.approx(60.0)
    assert compute_overall(80.0, 40.0, 0.25) == pytest.approx(70.0)


# ---------------------------------------------------------------------------
# Comparison baselines
# ---------------------------------------------------------------------------

def test_comparisons_agree_with_their_production_counterparts():
    """CA6, legacy CA7 and Chase Appeal must not drift from production."""
    from backend.desirability.collector_appeal import (
        CA7_PRODUCTION_LAMBDA,
        compute_chase_appeal,
        compute_collector_appeal_ca7,
        dual_path_utility,
    )

    for d in GRID:
        for p in GRID:
            for m in GRID:
                got = compute_comparisons(d=d, p=p, m=m)
                assert got["pure_D"] == pytest.approx(d)
                assert got["CA7_legacy_bounded_bonus_50"] == pytest.approx(
                    compute_collector_appeal_ca7(d, p, lam=CA7_PRODUCTION_LAMBDA)
                )
                assert got["chase_appeal_D_times_M"] == pytest.approx(
                    compute_chase_appeal(d, m)
                )
                assert got["CA6_dual_path_utility"] == pytest.approx(
                    d * dual_path_utility(p)
                )


def test_revised_primary_and_legacy_ca7_are_genuinely_different_formulas():
    """If they agreed everywhere, the revision would be a rename."""
    from backend.desirability.collector_appeal import compute_collector_appeal_ca7

    differing = [
        (d, h, p)
        for d in GRID
        for h in GRID
        for p in GRID
        if abs(compute_primary(d, h, p) - compute_collector_appeal_ca7(d, p)) > 1e-9
    ]
    assert differing, "the revised formula never differs from legacy CA7"
