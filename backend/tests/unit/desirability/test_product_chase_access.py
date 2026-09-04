"""Chase Access at Budget V1 (O_budget) - production invariants.

Covers Phase 18.A (math), 18.B (authority coherence subset), 18.C (n
semantics subset), 18.D (ECE policy + Phase 7 same-set invariant), and
18.E (ranking-direction basics) from the Premium Product Chase Intelligence
implementation plan. Mirrors ``test_chase_accessibility.py``'s structure and
row-builder convention.
"""

from __future__ import annotations

import math

import pytest

from backend.desirability import chase_accessibility as ca
from backend.desirability import product_chase_access as pca


def _row(variant, price, probability, **extra):
    row = {
        "set_id": "set-1",
        "calculation_run_id": "run-1",
        "card_variant_id": variant,
        "price_used": price,
        "modeled_probability": probability,
    }
    row.update(extra)
    return row


def _two_card_universe():
    # Values 1.0 and 2.0 -> HC = [0.2, 0.8] exactly, per chase_accessibility's
    # own worked example.
    return [
        _row("v1", 1.0, 0.10),
        _row("v2", 2.0, 0.40),
    ]


# --------------------------------------------------------------------------
# 18.A - O_budget math
# --------------------------------------------------------------------------

def test_o_budget_at_n_equals_1_matches_chase_accessibility():
    """At n=1, 1-(1-p)^1 == p, so O_budget(n=1) must equal A_raw exactly."""
    variants = _two_card_universe()
    a_raw = ca.compute_chase_accessibility(variants=variants)
    o_budget = pca.compute_o_budget(variants=variants, effective_packs=1)
    assert o_budget["status"] == pca.STATUS_READY
    assert o_budget["oBudget"] == pytest.approx(a_raw["accessibility"], abs=1e-12)


def test_o_budget_exact_toy_value():
    hc = [0.2, 0.8]
    p = [0.10, 0.40]
    n = 3
    expected = hc[0] * (1 - (1 - p[0]) ** n) + hc[1] * (1 - (1 - p[1]) ** n)
    variants = _two_card_universe()
    result = pca.compute_o_budget(variants=variants, effective_packs=n)
    assert result["oBudget"] == pytest.approx(expected, abs=1e-12)


def test_o_budget_is_monotonic_nondecreasing_in_n():
    variants = _two_card_universe()
    values = [pca.compute_o_budget(variants=variants, effective_packs=n)["oBudget"]
              for n in (0, 1, 2, 5, 10, 50)]
    assert values == sorted(values)
    assert all(v is not None for v in values)


def test_o_budget_asymptotically_approaches_full_hc_mass_as_n_grows():
    variants = _two_card_universe()
    huge = pca.compute_o_budget(variants=variants, effective_packs=100_000)["oBudget"]
    assert huge == pytest.approx(1.0, abs=1e-6)


def test_o_budget_bounded_zero_to_one():
    variants = _two_card_universe()
    for n in (0, 1, 3, 10, 1000):
        value = pca.compute_o_budget(variants=variants, effective_packs=n)["oBudget"]
        assert 0.0 <= value <= 1.0


def test_o_budget_zero_packs_is_a_real_measured_zero_not_unavailable():
    variants = _two_card_universe()
    result = pca.compute_o_budget(variants=variants, effective_packs=0)
    assert result["status"] == pca.STATUS_READY
    assert result["oBudget"] == 0.0


def test_o_budget_missing_pack_count_is_unavailable_never_zero():
    variants = _two_card_universe()
    result = pca.compute_o_budget(variants=variants, effective_packs=None)
    assert result["status"] == pca.STATUS_NO_PACK_COUNT
    assert result["oBudget"] is None


def test_o_budget_negative_pack_count_is_unavailable():
    variants = _two_card_universe()
    result = pca.compute_o_budget(variants=variants, effective_packs=-5)
    assert result["status"] == pca.STATUS_INVALID_PACK_COUNT
    assert result["oBudget"] is None


def test_o_budget_never_reads_effective_pull_rate():
    """Passing a large effective_pull_rate (odds) alongside modeled_probability
    must not perturb the result: only modeled_probability may drive weighting."""
    variants = [
        _row("v1", 1.0, 0.10, effective_pull_rate=1000),
        _row("v2", 2.0, 0.40, effective_pull_rate=3),
    ]
    with_odds = pca.compute_o_budget(variants=variants, effective_packs=5)["oBudget"]
    without_odds = pca.compute_o_budget(variants=_two_card_universe(), effective_packs=5)["oBudget"]
    assert with_odds == pytest.approx(without_odds, abs=1e-12)


def test_o_budget_low_mapped_mass_fails_closed_no_renormalisation():
    # A third, high-value card with NO modeled_probability: its HC mass is
    # large enough to breach the 0.99 mapped-mass floor.
    variants = _two_card_universe() + [_row("v3", 100.0, None)]
    result = pca.compute_o_budget(variants=variants, effective_packs=5)
    assert result["status"] == pca.STATUS_LOW_COVERAGE
    assert result["oBudget"] is None


# --------------------------------------------------------------------------
# 18.B - authority coherence
# --------------------------------------------------------------------------

def test_o_budget_rejects_mixed_set_ids():
    variants = [_row("v1", 1.0, 0.1, set_id="set-1"), _row("v2", 2.0, 0.4, set_id="set-2")]
    with pytest.raises(pca.ProductChaseAccessInputError):
        pca.compute_o_budget(variants=variants, effective_packs=1)


def test_o_budget_rejects_mixed_run_ids():
    variants = [_row("v1", 1.0, 0.1, calculation_run_id="run-a"),
                _row("v2", 2.0, 0.4, calculation_run_id="run-b")]
    with pytest.raises(pca.ProductChaseAccessInputError):
        pca.compute_o_budget(variants=variants, effective_packs=1)


def test_o_budget_rejects_duplicate_variant_ids():
    variants = [_row("v1", 1.0, 0.1), _row("v1", 2.0, 0.4)]
    with pytest.raises(pca.ProductChaseAccessInputError):
        pca.compute_o_budget(variants=variants, effective_packs=1)


def test_o_budget_no_pull_model_is_unavailable():
    result = pca.compute_o_budget(variants=_two_card_universe(), effective_packs=1,
                                  has_pull_model=False)
    assert result["status"] == pca.STATUS_NO_PULL_MODEL


def test_o_budget_no_universe_is_unavailable():
    result = pca.compute_o_budget(variants=[], effective_packs=1)
    assert result["status"] == pca.STATUS_NO_UNIVERSE


def test_o_budget_no_priced_universe_is_unavailable():
    variants = [_row("v1", None, 0.1), _row("v2", None, 0.4)]
    result = pca.compute_o_budget(variants=variants, effective_packs=1)
    assert result["status"] == pca.STATUS_NO_PRICED_UNIVERSE


# --------------------------------------------------------------------------
# 18.C - n / effective-pack semantics
# --------------------------------------------------------------------------

def test_effective_random_packs_multiplies_quantity_by_pack_count():
    assert pca.effective_random_packs(quantity=3, random_pack_count=1) == 3.0
    assert pca.effective_random_packs(quantity=2, random_pack_count=6) == 12.0


def test_effective_random_packs_excludes_guaranteed_accessories_by_contract():
    """random_pack_count for an ETB must already exclude its guaranteed promo -
    this function trusts its caller's composition value and does no counting
    of its own, so passing the ETB's real random-slot count (not total
    components) is the caller's job. Documented here as the semantic contract."""
    etb_random_pack_count = 4  # e.g. 4 boosters, promo card excluded upstream
    assert pca.effective_random_packs(quantity=1, random_pack_count=etb_random_pack_count) == 4.0


def test_effective_random_packs_zero_quantity_is_real_zero():
    assert pca.effective_random_packs(quantity=0, random_pack_count=6) == 0.0


def test_effective_random_packs_missing_input_is_unavailable():
    assert pca.effective_random_packs(quantity=None, random_pack_count=6) is None
    assert pca.effective_random_packs(quantity=2, random_pack_count=None) is None


def test_effective_random_packs_rejects_negative_quantity():
    assert pca.effective_random_packs(quantity=-1, random_pack_count=6) is None


# --------------------------------------------------------------------------
# 18.D - ECE: exact formula + Phase 7 same-set invariant
# --------------------------------------------------------------------------

def test_ece_exact_formula():
    cost = pca.effective_pack_cost(product_market_cost=24.0, random_pack_count=6)
    assert cost == pytest.approx(4.0)
    ece = pca.compute_ece(a_raw=0.08, effective_pack_cost_value=cost)
    assert ece == pytest.approx(0.02)


def test_ece_missing_inputs_unavailable():
    assert pca.compute_ece(a_raw=None, effective_pack_cost_value=4.0) is None
    assert pca.compute_ece(a_raw=0.08, effective_pack_cost_value=None) is None
    assert pca.effective_pack_cost(product_market_cost=None, random_pack_count=6) is None
    assert pca.effective_pack_cost(product_market_cost=24.0, random_pack_count=0) is None


def test_phase7_same_set_ece_ordering_is_exactly_inverse_effective_pack_cost_ordering():
    """PERMANENT REGRESSION TEST (Phase 7).

    For products of the SAME set/run, A_raw is identical by construction, so
    ECE(P1) > ECE(P2) must hold if and only if
    effective_pack_cost(P1) < effective_pack_cost(P2). This is the proof that
    ECE carries ZERO extra ranking information beyond price within a set and
    therefore can NEVER be a universal All-Products quality score. If this
    test ever fails, ECE has stopped being price-only within a set and every
    place that treats it as "context only" must be re-audited.
    """
    a_raw = 0.0734  # one fixed set-level A_raw, shared by every product below
    products = [
        {"name": "loose_booster", "cost": 4.50, "packs": 1},
        {"name": "booster_box", "cost": 144.00, "packs": 36},
        {"name": "etb", "cost": 42.00, "packs": 4},
        {"name": "blister", "cost": 12.00, "packs": 2},
    ]
    for product in products:
        product["effectivePackCost"] = pca.effective_pack_cost(
            product_market_cost=product["cost"], random_pack_count=product["packs"])
        product["ece"] = pca.compute_ece(
            a_raw=a_raw, effective_pack_cost_value=product["effectivePackCost"])

    for p1 in products:
        for p2 in products:
            if p1 is p2:
                continue
            ece_says_p1_better = p1["ece"] > p2["ece"]
            cost_says_p1_better = p1["effectivePackCost"] < p2["effectivePackCost"]
            assert ece_says_p1_better == cost_says_p1_better, (
                f"{p1['name']} vs {p2['name']}: ECE ordering diverged from "
                "inverse-effective-pack-cost ordering within one set/run - ECE is "
                "no longer provably price-only and must not be treated as context-only."
            )


def test_ece_cannot_be_selected_as_a_universal_all_products_authority():
    """Structural check: the module exposes no ranking/sorting entry point at
    all for ECE - only the pure per-product formula. Any future universal
    ECE leaderboard would have to be built as new code outside this module,
    which is exactly the point: this module provides no such surface."""
    public_names = [name for name in dir(pca) if not name.startswith("_")]
    forbidden_substrings = ("rank", "leaderboard", "sort", "all_products", "cohort")
    ece_related_ranking_functions = [
        name for name in public_names
        if "ece" in name.lower() and any(f in name.lower() for f in forbidden_substrings)
    ]
    assert ece_related_ranking_functions == [], (
        "found an ECE ranking/leaderboard entry point in the pure math module: "
        f"{ece_related_ranking_functions} - ECE ranking, if ever added, must live "
        "in a family-scoped caller that asserts genuine comparability, never here."
    )


# --------------------------------------------------------------------------
# 18.E - ranking/ordering basics
# --------------------------------------------------------------------------

def test_changing_budget_can_legitimately_change_o_budget_ordering():
    """Two products in DIFFERENT sets can flip relative order as n changes,
    because the reachability curve saturates at different rates depending on
    the per-card probabilities - this is expected, not a bug."""
    slow_saturating = [_row("v1", 1.0, 0.02), _row("v2", 2.0, 0.03)]
    fast_saturating = [_row("v1", 1.0, 0.30, set_id="set-2", calculation_run_id="run-2"),
                       _row("v2", 2.0, 0.35, set_id="set-2", calculation_run_id="run-2")]

    low_n_slow = pca.compute_o_budget(variants=slow_saturating, effective_packs=1)["oBudget"]
    low_n_fast = pca.compute_o_budget(variants=fast_saturating, effective_packs=1)["oBudget"]
    high_n_slow = pca.compute_o_budget(variants=slow_saturating, effective_packs=200)["oBudget"]
    high_n_fast = pca.compute_o_budget(variants=fast_saturating, effective_packs=200)["oBudget"]

    assert low_n_fast > low_n_slow
    # Both saturate toward 1.0 at very high n - ordering compresses, it does
    # not need to flip, but neither is a fixed universal ranking independent
    # of budget.
    assert high_n_slow == pytest.approx(1.0, abs=1e-2)
    assert high_n_fast == pytest.approx(1.0, abs=1e-3)
