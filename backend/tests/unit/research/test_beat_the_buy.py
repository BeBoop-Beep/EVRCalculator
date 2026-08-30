"""Part-14 sanity tests for Beat-the-Buy, plus the Stage-II support machinery.

Stage I was rejected because its metric rose under every basket expansion. The
central test here is the mirror image: `test_padding_with_a_cheap_frequent_card
_can_reduce_beat_the_buy` asserts that Beat-the-Buy CAN fall when the chase
universe is diluted. If that ever stops holding, Beat-the-Buy has acquired
Stage I's defect and must be re-derived before use.
"""

from __future__ import annotations

import math

import numpy as np
import pytest

from backend.research.set_chase_efficiency.baskets import ChaseCandidate
from backend.research.set_chase_efficiency.chase_metrics import (
    beat_the_buy,
    chase_cost_gap,
    chase_ev,
    chase_journeys,
)
from backend.research.set_chase_efficiency.chase_universe import (
    boundary_description,
    depth_statistics,
    jaccard,
    largest_log_gap,
    log_price_two_cluster,
    modified_zscore_outliers,
    perturbed_universe,
)


def card(entity_id: int, price: float, pulls: int = 10, name: str = None) -> ChaseCandidate:
    return ChaseCandidate(
        entity_id=entity_id, card_variant_id=f"v{entity_id}", card_id=f"c{entity_id}",
        card_name=name or f"Card {entity_id}", card_number=f"{entity_id:03d}",
        printing_type="normal", rarity_key="hits", price=price,
        price_captured_at="2026-08-28", price_source="src", pull_count=pulls)


def synthetic_run(*, packs: int, hit_every: int, value: float, seed: int = 7):
    """A deterministic pack sequence with one chase card at a known rate."""
    rng = np.random.default_rng(seed)
    qualifying = rng.random(packs) < (1.0 / hit_every)
    values = np.where(qualifying, value, 0.0)
    return qualifying, values


def btb(*, packs=200_000, hit_every=50, value=100.0, cost=10.0, seed=7):
    qualifying, values = synthetic_run(packs=packs, hit_every=hit_every, value=value, seed=seed)
    p = float(qualifying.mean())
    return beat_the_buy(qualifying=qualifying, chase_values=values,
                        probability=p, pack_cost=cost)


# --- Property 1: lower pack price must not reduce BTB ----------------------

@pytest.mark.parametrize("cost", [2.0, 5.0, 10.0, 25.0])
def test_lower_pack_price_never_reduces_beat_the_buy(cost):
    cheaper = btb(cost=cost * 0.8)["closedForm"]
    dearer = btb(cost=cost)["closedForm"]
    assert cheaper >= dearer


# --- Property 2: higher chase value must not reduce BTB --------------------

@pytest.mark.parametrize("value", [30.0, 100.0, 500.0])
def test_higher_chase_value_never_reduces_beat_the_buy(value):
    assert btb(value=value * 1.5)["closedForm"] >= btb(value=value)["closedForm"]


# --- Property 3: higher hit probability must not reduce BTB ----------------

@pytest.mark.parametrize("hit_every", [20, 50, 200])
def test_higher_hit_probability_never_reduces_beat_the_buy(hit_every):
    easier = btb(hit_every=max(2, hit_every // 2))["closedForm"]
    harder = btb(hit_every=hit_every)["closedForm"]
    assert easier >= harder


# --- Property 4: THE ANTI-DEGENERATION PROPERTY ----------------------------

def test_padding_with_a_cheap_frequent_card_can_reduce_beat_the_buy():
    """Beat-the-Buy must be ABLE to fall when the chase universe is diluted.

    This is the property Stage I's metric provably lacked. A $100 chase at
    1-in-50 padded with a $4 card at 1-in-3 raises p_S a great deal, but the
    padding card is worth less than one $10 pack, so ``floor(Y/C) = 0`` and it
    contributes exactly zero to beating the buy while dominating the successful
    packs. BTB must therefore fall.
    """
    packs, cost = 300_000, 10.0
    rng = np.random.default_rng(11)
    rare = rng.random(packs) < 1 / 50
    common = rng.random(packs) < 1 / 3

    focused_values = np.where(rare, 100.0, 0.0)
    focused = beat_the_buy(qualifying=rare, chase_values=focused_values,
                           probability=float(rare.mean()), pack_cost=cost)

    padded_hit = rare | common
    padded_values = np.maximum(np.where(rare, 100.0, 0.0), np.where(common, 4.0, 0.0))
    padded = beat_the_buy(qualifying=padded_hit, chase_values=padded_values,
                          probability=float(padded_hit.mean()), pack_cost=cost)

    assert padded["closedForm"] < focused["closedForm"], (
        f"dilution raised BTB from {focused['closedForm']} to {padded['closedForm']}; "
        "Beat-the-Buy has acquired the Stage-I degeneracy and must be re-derived"
    )


def test_a_chase_worth_less_than_one_pack_contributes_nothing():
    """``floor(Y/C) = 0`` is the mechanism behind Property 4."""
    qualifying, values = synthetic_run(packs=100_000, hit_every=4, value=9.99)
    result = beat_the_buy(qualifying=qualifying, chase_values=values,
                          probability=float(qualifying.mean()), pack_cost=10.0)
    assert result["closedForm"] == 0.0
    assert result["shareOfChasesWorthLessThanOnePack"] == 1.0


# --- Property 5: an extremely valuable rare card behaves sensibly ----------

def test_a_very_valuable_rare_chase_does_not_automatically_dominate():
    """Value alone cannot buy a high BTB; the card still has to be reachable.

    A $5,000 card at 1-in-20,000 has an enormous affordable-pack exponent, but
    ``(1-p)^n`` with p = 5e-5 and n = 500 still only reaches ~2.5%. BTB stays
    bounded and well below a modest, frequently-hit chase.
    """
    jackpot = btb(packs=400_000, hit_every=20_000, value=5000.0, cost=10.0)["closedForm"]
    modest = btb(packs=400_000, hit_every=30, value=60.0, cost=10.0)["closedForm"]
    assert 0.0 < jackpot < 0.10
    assert modest > jackpot


# --- Property 6/7: missing data and empty baskets --------------------------

def test_missing_price_or_cost_never_becomes_a_zero_value_chase():
    qualifying, values = synthetic_run(packs=1000, hit_every=10, value=100.0)
    p = float(qualifying.mean())
    assert beat_the_buy(qualifying=qualifying, chase_values=values,
                        probability=p, pack_cost=None)["closedForm"] is None
    assert beat_the_buy(qualifying=qualifying, chase_values=values,
                        probability=None, pack_cost=10.0)["closedForm"] is None
    assert beat_the_buy(qualifying=qualifying, chase_values=values,
                        probability=p, pack_cost=0.0)["closedForm"] is None


def test_empty_chase_universe_is_reported_not_scored():
    empty = np.zeros(1000, dtype=bool)
    result = beat_the_buy(qualifying=empty, chase_values=np.zeros(1000),
                          probability=None, pack_cost=10.0)
    assert result["closedForm"] is None
    assert result["direct"] is None
    assert result["reason"] == "no qualifying chase observed"
    assert chase_cost_gap(qualifying=empty, chase_values=np.zeros(1000),
                          pack_cost=10.0)["journeys"] == 0


# --- Property 8: multi-hit packs are one success, not several --------------

def test_a_multi_chase_pack_ends_exactly_one_journey():
    qualifying = np.array([False, False, True, False, True])
    values = np.array([0.0, 0.0, 250.0, 0.0, 80.0])
    packs_used, obtained = chase_journeys(qualifying, values)
    assert list(packs_used) == [3, 2]
    assert list(obtained) == [250.0, 80.0]
    assert packs_used.sum() == qualifying.size


def test_journeys_partition_the_pack_sequence_without_overlap():
    rng = np.random.default_rng(3)
    qualifying = rng.random(50_000) < 0.02
    values = np.where(qualifying, 100.0, 0.0)
    packs_used, _ = chase_journeys(qualifying, values)
    # Every journey ends on a success, so the packs consumed by all journeys
    # equal the index of the final success plus one - never more.
    assert packs_used.sum() == int(np.flatnonzero(qualifying)[-1]) + 1


# --- Property 9: bounded in [0,1] ------------------------------------------

@pytest.mark.parametrize("hit_every,value,cost", [
    (2, 10_000.0, 1.0), (100_000, 0.01, 500.0), (3, 50.0, 10.0), (5000, 900.0, 4.0),
])
def test_beat_the_buy_is_bounded_in_the_unit_interval(hit_every, value, cost):
    result = btb(packs=100_000, hit_every=hit_every, value=value, cost=cost)
    for estimate in (result["closedForm"], result["direct"]):
        if estimate is not None:
            assert 0.0 <= estimate <= 1.0


# --- Property 10: closed form agrees with direct simulation ----------------

@pytest.mark.parametrize("hit_every,value,cost", [
    (20, 100.0, 10.0), (50, 300.0, 15.0), (200, 800.0, 8.0), (10, 45.0, 5.0),
])
def test_closed_form_agrees_with_direct_journey_simulation(hit_every, value, cost):
    """Validates the ``T`` independent of ``Y`` assumption the closed form needs.

    Tolerance is four standard errors of the direct estimate, so this fails on a
    genuine modelling error rather than on Monte Carlo noise.
    """
    result = btb(packs=400_000, hit_every=hit_every, value=value, cost=cost)
    tolerance = max(4.0 * (result["directStandardError"] or 0.0), 0.005)
    assert result["agreementAbsolute"] <= tolerance, (
        f"closed form {result['closedForm']} vs direct {result['direct']} "
        f"exceeds {tolerance}"
    )


# --- Chase EV ---------------------------------------------------------------

def test_chase_ev_credits_only_qualifying_cards_and_splits_the_total():
    totals = np.array([0.0, 0.0, 50.0, 0.0, 10.0])
    full = np.array([3.0, 4.0, 55.0, 2.0, 14.0])
    block = chase_ev(qualifying_totals=totals, pack_cost=10.0, full_pack_values=full)
    assert block["chaseEv"] == pytest.approx(12.0)
    assert block["chaseEvReturn"] == pytest.approx(1.2)
    assert block["fullPackEv"] == pytest.approx(15.6)
    assert block["chaseEvShareOfTotalEv"] + block["nonChaseEvShareOfTotalEv"] == pytest.approx(1.0)
    assert block["chaseEv"] + block["nonChaseEv"] == pytest.approx(block["fullPackEv"])


def test_chase_ev_rises_monotonically_as_the_universe_widens():
    """Chase EV SHOULD degenerate toward full pack EV. It is an EV metric.

    Recorded as an expectation so nobody later mistakes this behaviour for a
    defect, or for evidence that Chase EV measures efficiency.
    """
    full = np.array([10.0, 20.0, 5.0, 40.0])
    narrow = chase_ev(qualifying_totals=np.array([0.0, 20.0, 0.0, 0.0]),
                      pack_cost=5.0, full_pack_values=full)
    wide = chase_ev(qualifying_totals=np.array([10.0, 20.0, 0.0, 40.0]),
                    pack_cost=5.0, full_pack_values=full)
    assert wide["chaseEv"] > narrow["chaseEv"]
    assert wide["chaseEvShareOfTotalEv"] > narrow["chaseEvShareOfTotalEv"]


# --- Chase Cost Gap ---------------------------------------------------------

def test_chase_cost_gap_sign_convention_and_identity():
    qualifying = np.array([False, True, True])
    values = np.array([0.0, 500.0, 5.0])
    block = chase_cost_gap(qualifying=qualifying, chase_values=values, pack_cost=10.0)
    # Journey 1: 2 packs = $20 spend against a $500 chase -> ripping won by $480.
    # Journey 2: 1 pack  = $10 spend against a $5 chase   -> buying won by $5.
    assert block["journeys"] == 2
    assert block["meanGap"] == pytest.approx((20.0 - 500.0 + 10.0 - 5.0) / 2)
    assert block["probabilityGapAtMostZero"] == pytest.approx(0.5)
    assert block["meanSpendToFirstChase"] == pytest.approx(15.0)
    assert block["meanChaseValueObtained"] == pytest.approx(252.5)


def test_gap_and_beat_the_buy_agree_on_the_same_journeys():
    """``BTB direct`` is exactly ``P(Gap <= 0)``. They must never disagree."""
    rng = np.random.default_rng(19)
    qualifying = rng.random(200_000) < 0.01
    values = np.where(qualifying, rng.uniform(20.0, 400.0, 200_000), 0.0)
    p = float(qualifying.mean())
    btb_block = beat_the_buy(qualifying=qualifying, chase_values=values,
                             probability=p, pack_cost=12.0)
    gap_block = chase_cost_gap(qualifying=qualifying, chase_values=values, pack_cost=12.0)
    assert btb_block["direct"] == pytest.approx(gap_block["probabilityGapAtMostZero"])


# --- Depth ------------------------------------------------------------------

def test_the_three_depth_measures_can_disagree():
    """Value-, EV- and probability-concentration are not the same statistic.

    One expensive unreachable card and several cheap frequent ones: value
    concentration is extreme, probability concentration is not.
    """
    members = [card(0, 1000.0), card(1, 10.0), card(2, 10.0), card(3, 10.0)]
    block = depth_statistics(
        members,
        ev_contributions=[0.05, 0.30, 0.30, 0.30],
        hit_probabilities=[0.00005, 0.03, 0.03, 0.03])
    assert block["effectiveValueCount"] < 1.2
    assert block["effectiveEvCount"] > 3.0
    assert block["effectiveProbabilityCount"] > 2.9


def test_depth_of_a_worthless_universe_is_undefined_not_zero():
    block = depth_statistics([card(0, 0.0)], ev_contributions=[0.0], hit_probabilities=[0.0])
    assert block["effectiveValueCount"] is None
    assert block["effectiveEvCount"] is None


# --- Price-boundary selectors -----------------------------------------------

def test_largest_log_gap_finds_an_obvious_cliff():
    universe = [card(0, 800.0), card(1, 700.0), card(2, 650.0),
                card(3, 12.0), card(4, 10.0), card(5, 9.0)]
    result = largest_log_gap(universe)
    assert result["k"] == 3
    assert result["boundaryRatio"] > 50


def test_largest_log_gap_still_returns_a_cut_on_a_smooth_curve():
    """A smooth price curve has no cliff, but the rule still fires.

    This is the falsification: the method ALWAYS returns a K, so a K on its own
    is not evidence that a boundary exists. The ratio is what says whether it
    does, and a near-1.0 ratio means the cut is arbitrary.
    """
    universe = [card(i, 100.0 * (0.93 ** i)) for i in range(25)]
    result = largest_log_gap(universe)
    assert result["k"] is not None
    assert result["boundaryRatio"] < 1.2


def test_robust_zscore_and_clustering_report_reasons_when_they_cannot_fire():
    tiny = [card(0, 50.0), card(1, 40.0)]
    assert modified_zscore_outliers(tiny)["k"] is None
    assert modified_zscore_outliers(tiny)["reason"]
    assert log_price_two_cluster([card(0, 5.0)])["k"] is None


def test_boundary_description_reports_what_was_actually_cut():
    universe = [card(0, 500.0), card(1, 400.0), card(2, 12.0), card(3, 10.0)]
    block = boundary_description(universe, universe[:2])
    assert block["k"] == 2
    assert block["lowestSelectedValue"] == 400.0
    assert block["highestExcludedValue"] == 12.0
    assert block["boundaryRatio"] == pytest.approx(400.0 / 12.0, rel=1e-3)


# --- Stability helpers ------------------------------------------------------

def test_price_perturbation_is_bounded_seeded_and_preserves_identity():
    universe = [card(i, 100.0) for i in range(20)]
    first = perturbed_universe(universe, magnitude=0.10, seed=5)
    again = perturbed_universe(universe, magnitude=0.10, seed=5)
    assert [c.price for c in first] == [c.price for c in again]
    assert all(90.0 <= c.price <= 110.0 for c in first)
    assert [c.entity_id for c in first] == [c.entity_id for c in universe]
    assert all(c.pull_count == 10 for c in first)


def test_jaccard_boundaries():
    assert jaccard([1, 2, 3], [1, 2, 3]) == 1.0
    assert jaccard([1, 2], [3, 4]) == 0.0
    assert jaccard([], []) is None
    assert jaccard([1, 2, 3, 4], [1, 2]) == pytest.approx(0.5)
