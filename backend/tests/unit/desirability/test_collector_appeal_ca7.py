"""CA6 vs CA7: bounds, monotonicity, lambda pre-registration, RIP separation.

CA6 = D * (0.50 + 0.50 * P)          discount model
CA7 = D + lambda * P * (1 - D)       bounded-bonus model, lambda in {0.25, 0.50, 0.75}

These tests pin the algebraic properties the formula selection rests on, and the
disciplines that keep the selection honest (no lambda search, no price input,
Chase Appeal never becomes a fifth pillar).
"""

from __future__ import annotations

import ast
import inspect
import math

import pytest

from backend.desirability import collector_appeal as ca
from backend.desirability.collector_appeal import (
    CA7_LAMBDA_GRID,
    COLLECTOR_APPEAL_CANDIDATE_KEYS,
    bounded_bonus_appeal,
    compute_collector_appeal_candidates,
    degeneracy_note,
    dual_path_utility,
)
from backend.desirability.scoring_config import DEFAULT_RIP_WEIGHTS

GRID = [i / 20.0 for i in range(21)]  # 0.00 .. 1.00


# ---------------------------------------------------------------------------
# Pre-registration
# ---------------------------------------------------------------------------

def test_ca7_lambda_grid_is_exactly_the_pre_registered_values():
    """The brief pre-registered these three. Any other value is candidate scanning."""
    assert CA7_LAMBDA_GRID == (0.25, 0.50, 0.75)


def test_ca7_candidates_are_registered_in_the_candidate_key_tuple():
    for lam in CA7_LAMBDA_GRID:
        assert f"CA7_bounded_bonus_{int(lam*100)}" in COLLECTOR_APPEAL_CANDIDATE_KEYS


def test_no_search_loop_over_lambda_exists_in_the_module():
    """Walks the AST: no optimizer, no fitting, no scan over lambda.

    A lambda chosen by maximizing anything - correlation, rank movement, price
    agreement - would be a fitted parameter presented as a reasoned default.
    """
    tree = ast.parse(inspect.getsource(ca))
    banned = {
        "minimize", "maximize", "curve_fit", "least_squares", "polyfit",
        "GridSearchCV", "optimize", "fmin", "brute", "argmax", "argmin",
    }
    found = set()
    for node in ast.walk(tree):
        if isinstance(node, ast.Name):
            found.add(node.id)
        elif isinstance(node, ast.Attribute):
            found.add(node.attr)
    assert not (banned & found), f"optimizer surface in collector_appeal: {banned & found}"


def test_module_imports_no_price_or_market_surface():
    source = inspect.getsource(ca)
    tree = ast.parse(source)
    imported = set()
    for node in ast.walk(tree):
        if isinstance(node, (ast.Import, ast.ImportFrom)):
            imported.add(getattr(node, "module", "") or "")
            for alias in node.names:
                imported.add(alias.name)
    banned = {"market_price", "set_value", "expected_value", "prices", "pokemon_canonical_card_market_prices_latest"}
    assert not (banned & imported)


def test_ca7_signature_takes_no_market_outcome():
    signature = inspect.signature(bounded_bonus_appeal)
    assert set(signature.parameters) == {"d", "p", "lam"}


# ---------------------------------------------------------------------------
# CA7 bounds
# ---------------------------------------------------------------------------

@pytest.mark.parametrize("lam", CA7_LAMBDA_GRID)
def test_ca7_is_bounded_on_unit_interval(lam):
    for d in GRID:
        for p in GRID:
            value = bounded_bonus_appeal(d, p, lam)
            assert 0.0 <= value <= 1.0, f"CA7 out of bounds at D={d} P={p} lam={lam}"


@pytest.mark.parametrize("lam", CA7_LAMBDA_GRID)
def test_ca7_at_p_zero_equals_d_exactly(lam):
    """The defining property: absent dual-path structure costs a set NOTHING.

    This is the substantive disagreement with CA6, which charges a set half its
    desirability for the same absence.
    """
    for d in GRID:
        assert bounded_bonus_appeal(d, 0.0, lam) == pytest.approx(d, abs=1e-12)


@pytest.mark.parametrize("lam", CA7_LAMBDA_GRID)
def test_ca7_at_p_one_equals_d_plus_lambda_headroom(lam):
    for d in GRID:
        assert bounded_bonus_appeal(d, 1.0, lam) == pytest.approx(d + lam * (1.0 - d), abs=1e-12)


@pytest.mark.parametrize("lam", CA7_LAMBDA_GRID)
def test_ca7_cannot_exceed_one_even_at_maximum_d_and_p(lam):
    assert bounded_bonus_appeal(1.0, 1.0, lam) == pytest.approx(1.0)


def test_ca7_headroom_bound_is_what_prevents_overshoot():
    """Contrast with an unbounded additive bonus D + lam*P, which would exceed 1."""
    d, p, lam = 0.95, 1.0, 0.75
    naive = d + lam * p
    assert naive > 1.0
    assert bounded_bonus_appeal(d, p, lam) <= 1.0


# ---------------------------------------------------------------------------
# CA7 monotonicity
# ---------------------------------------------------------------------------

@pytest.mark.parametrize("lam", CA7_LAMBDA_GRID)
def test_ca7_is_non_decreasing_in_p(lam):
    for d in GRID:
        values = [bounded_bonus_appeal(d, p, lam) for p in GRID]
        assert all(b >= a - 1e-12 for a, b in zip(values, values[1:])), f"not monotone in P at D={d}"


@pytest.mark.parametrize("lam", CA7_LAMBDA_GRID)
def test_ca7_is_strictly_increasing_in_d(lam):
    """dCA7/dD = 1 - lam*P >= 1 - lam > 0 for every registered lambda.

    This is the guarantee that structure can never overrule desirability: a more
    desirable set always scores higher, whatever its dual-path structure.
    """
    for p in GRID:
        values = [bounded_bonus_appeal(d, p, lam) for d in GRID]
        assert all(b > a - 1e-12 for a, b in zip(values, values[1:])), f"not increasing in D at P={p}"


@pytest.mark.parametrize("lam", CA7_LAMBDA_GRID)
def test_ca7_high_d_low_p_beats_low_d_high_p(lam):
    """Desirability dominates: a beloved roster with no dual path outranks an
    unloved roster with perfect dual path."""
    assert bounded_bonus_appeal(0.90, 0.0, lam) > bounded_bonus_appeal(0.40, 1.0, lam)


# ---------------------------------------------------------------------------
# CA6 bounds / monotonicity (the comparison baseline)
# ---------------------------------------------------------------------------

def test_ca6_is_bounded_and_monotone():
    for d in GRID:
        previous = None
        for p in GRID:
            value = d * dual_path_utility(p)
            assert 0.0 <= value <= 1.0
            if previous is not None:
                assert value >= previous - 1e-12
            previous = value


def test_ca6_at_p_zero_charges_half_of_desirability():
    """CA6's defining behaviour, stated as a test so the tradeoff is explicit.

    A set of beloved Pokemon with one printing each keeps only 50% of its
    desirability. Whether that is right is the construct question the results
    doc answers; that it HAPPENS is not in dispute.
    """
    assert 0.90 * dual_path_utility(0.0) == pytest.approx(0.45)


def test_ca6_ceiling_is_unreachable_given_observed_dual_path_range():
    """On real data P maxes out at ~0.447, so CA6's multiplier maxes at ~0.723.

    The consequence: under CA6 the most appealing set in the catalogue scores
    ~65/100 and nothing ever approaches 100. The 0-100 scale stops being
    readable as "Collector Appeal" - it is D times a factor that never reaches 1.
    """
    observed_max_p = 0.4466
    assert dual_path_utility(observed_max_p) == pytest.approx(0.7233, abs=1e-3)
    assert 0.9548 * dual_path_utility(observed_max_p) < 0.70


def test_ca6_and_ca7_diverge_most_where_dual_path_is_absent():
    d = 0.90
    assert d * dual_path_utility(0.0) == pytest.approx(0.45)
    assert bounded_bonus_appeal(d, 0.0, 0.50) == pytest.approx(0.90)


# ---------------------------------------------------------------------------
# Missing data never becomes zero
# ---------------------------------------------------------------------------

@pytest.mark.parametrize("lam", CA7_LAMBDA_GRID)
def test_ca7_returns_none_for_missing_inputs_never_zero(lam):
    assert bounded_bonus_appeal(None, 0.5, lam) is None
    assert bounded_bonus_appeal(0.5, None, lam) is None


def test_missing_dual_path_makes_only_the_dual_path_candidates_unavailable():
    out = compute_collector_appeal_candidates(d=0.8, a_star=0.5, m_star=0.5, dual_path_depth=None)
    assert out["CA6_dual_path_utility"] is None
    for lam in CA7_LAMBDA_GRID:
        assert out[f"CA7_bounded_bonus_{int(lam*100)}"] is None
    assert out["CA0_desirability_only"] == pytest.approx(0.8)


def test_every_registered_candidate_is_computed():
    out = compute_collector_appeal_candidates(d=0.8, a_star=0.5, m_star=0.5, dual_path_depth=0.3)
    assert set(out) == set(COLLECTOR_APPEAL_CANDIDATE_KEYS)
    assert all(value is not None for value in out.values())


def test_ca7_degeneracy_note_is_registered_for_each_lambda():
    for lam in CA7_LAMBDA_GRID:
        note = degeneracy_note(f"CA7_bounded_bonus_{int(lam*100)}")
        assert note != "unregistered candidate"
        assert "bonus" in note.lower()


# ---------------------------------------------------------------------------
# Chase Appeal stays out of RIP
# ---------------------------------------------------------------------------

def test_rip_has_exactly_four_pillars_and_chase_appeal_is_not_one():
    """Chase Appeal (D x M) is reported separately and must never become a
    fifth pillar - adding it would apply desirability to RIP twice."""
    assert set(DEFAULT_RIP_WEIGHTS) == {"profit", "safety", "stability", "desirability"}
    assert "chase_appeal" not in DEFAULT_RIP_WEIGHTS
    assert "chase_intensity" not in DEFAULT_RIP_WEIGHTS


def test_collector_appeal_weight_stays_at_ten_percent():
    assert DEFAULT_RIP_WEIGHTS["desirability"] == 0.10
    assert sum(DEFAULT_RIP_WEIGHTS.values()) == pytest.approx(1.0)
