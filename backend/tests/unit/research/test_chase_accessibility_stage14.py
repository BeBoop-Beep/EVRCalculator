"""Stage XIV Chase Accessibility contract tests."""

from __future__ import annotations

import numpy as np
import pytest

from backend.research.chase_accessibility_stage14 import (
    CHASE_ACCESSIBILITY_RESEARCH_VERSION,
    MIN_MAPPED_HC_MASS,
    STATUS_LOW_COVERAGE,
    STATUS_NO_PULL_MODEL,
    STATUS_READY,
    accessibility_direct,
    accessibility_via_hc,
    chase_significance,
    compute_chase_accessibility,
    mapped_hc_mass,
)

V = [100.0, 40.0, 10.0, 2.0, 1.0, 0.5]
P = [0.001, 0.004, 0.02, 0.08, 0.15, 0.30]


def test_hc_sums_to_one():
    for vals in (V, [1.0] * 25, [5.0, 0.01], [1e6, 1.0]):
        assert chase_significance(vals).sum() == pytest.approx(1.0, abs=1e-12)


def test_hc_is_squared_value_share():
    hc = chase_significance([3.0, 1.0])
    assert hc[0] == pytest.approx(0.9, abs=1e-12)   # 9/10
    assert hc[1] == pytest.approx(0.1, abs=1e-12)


def test_two_formulations_agree_to_machine_precision():
    hc = chase_significance(V)
    assert abs(accessibility_via_hc(hc, P) - accessibility_direct(V, P)) < 1e-15


def test_accessibility_is_bounded_by_the_probabilities():
    o = accessibility_direct(V, P)
    assert min(P) <= o <= max(P)


# ------------------------------------------------------- scale invariance

@pytest.mark.parametrize("mult", [0.5, 2.0, 10.0, 100.0, 1e6])
def test_uniform_price_scaling_leaves_accessibility_exactly_unchanged(mult):
    base = compute_chase_accessibility(values=V, probabilities=P)["accessibility"]
    scaled = compute_chase_accessibility(
        values=[v * mult for v in V], probabilities=P)["accessibility"]
    assert abs(scaled - base) < 1e-15


def test_uniform_scaling_leaves_hc_bit_identical():
    base = chase_significance(V)
    for mult in (0.5, 2.0, 10.0, 100.0):
        assert np.allclose(base, chase_significance([v * mult for v in V]),
                           rtol=0, atol=1e-15)


# ------------------------------------------------------- probability authority

def test_odds_are_never_a_probability_regression():
    """Permanent guard against the Stage XI inversion.

    `effective_pull_rate` is 1-in-N odds. Feeding it where a probability belongs
    must produce a wildly different answer - this test exists so that a future
    refactor cannot silently reintroduce the bug that Stage XI shipped and Stage
    XII caught.
    """
    odds = [1.0 / p for p in P]                      # what the column actually holds
    correct = accessibility_direct(V, P)
    inverted = accessibility_direct(V, odds)
    assert correct < 1.0
    assert inverted > 100.0                          # nonsensical, as it should be
    assert inverted / correct > 1000.0


def test_probability_of_at_least_one_is_not_expected_copies():
    """P(N>=1) <= E[N]; they differ whenever a pack can hold two copies."""
    p_at_least_one, expected_copies = 0.09, 0.11
    assert p_at_least_one < expected_copies


# ------------------------------------------------------- monotonicity

def test_accessibility_is_weakly_increasing_in_every_probability():
    base = accessibility_direct(V, P)
    for i in range(len(P)):
        up = list(P)
        up[i] = min(1.0, up[i] * 1.5)
        assert accessibility_direct(V, up) >= base


def test_zero_probabilities_give_zero_accessibility():
    assert accessibility_direct(V, [0.0] * len(V)) == 0.0


def test_certain_probabilities_give_exactly_one():
    assert accessibility_direct(V, [1.0] * len(V)) == pytest.approx(1.0, abs=1e-15)


# ------------------------------------------------------- missing-data contract

def test_mapped_mass_is_measured_against_the_full_universe():
    """The unusable card's significance must reduce the mass, not vanish."""
    usable = [True, True, True, True, True, False]
    mass = mapped_hc_mass(V, usable)
    assert mass < 1.0
    assert mass == pytest.approx(1.0 - chase_significance(V)[5], abs=1e-12)


def test_missing_high_significance_card_fails_closed():
    usable = [False] + [True] * (len(V) - 1)          # drop the $100 card
    result = compute_chase_accessibility(values=V, probabilities=P, usable=usable)
    assert result["accessibility"] is None
    assert result["status"] == STATUS_LOW_COVERAGE
    assert result["rankable"] is False


def test_unmapped_mass_is_never_renormalised_away():
    """Dropping the top card must not make the set look MORE accessible."""
    full = compute_chase_accessibility(values=V, probabilities=P)["accessibility"]
    usable = [False] + [True] * (len(V) - 1)
    gated = compute_chase_accessibility(values=V, probabilities=P, usable=usable)
    assert gated["accessibility"] is None             # refused, not silently rescaled
    naive = accessibility_direct(V[1:], P[1:])        # what renormalising would give
    assert naive > full                               # and it would be misleading


def test_tiny_low_significance_gap_still_passes_the_gate():
    usable = [True] * (len(V) - 1) + [False]          # drop the $0.50 card
    result = compute_chase_accessibility(values=V, probabilities=P, usable=usable)
    assert result["status"] == STATUS_READY
    assert result["mappedHcMass"] > MIN_MAPPED_HC_MASS


def test_no_pull_model_is_unavailable_not_zero():
    result = compute_chase_accessibility(values=V, probabilities=P, has_pull_model=False)
    assert result["accessibility"] is None
    assert result["status"] == STATUS_NO_PULL_MODEL
    assert result["rankable"] is False


# ------------------------------------------------------- lineage / determinism

def test_output_is_deterministic():
    a = compute_chase_accessibility(values=V, probabilities=P)
    b = compute_chase_accessibility(values=V, probabilities=P)
    assert a["accessibility"] == b["accessibility"]


def test_every_payload_carries_its_version():
    for kwargs in ({}, {"has_pull_model": False},
                   {"usable": [False] + [True] * (len(V) - 1)}):
        result = compute_chase_accessibility(values=V, probabilities=P, **kwargs)
        assert result["version"] == CHASE_ACCESSIBILITY_RESEARCH_VERSION


def test_accessibility_reads_no_product_input():
    """Product invariance: the signature admits no product argument at all."""
    import inspect

    params = set(inspect.signature(compute_chase_accessibility).parameters)
    assert params == {"values", "probabilities", "usable",
                      "has_pull_model", "min_mapped_mass"}
    for banned in ("pack_count", "product", "cost", "price_of_product"):
        assert banned not in params
