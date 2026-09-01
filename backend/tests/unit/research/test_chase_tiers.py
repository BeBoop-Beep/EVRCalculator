"""Stage-IV tests: tier-rule invariants and the Phase-17 pathological cases.

The pathological cases are the point of this file. Every candidate tier family
is run against six controlled price distributions whose "right answer" is
obvious to a human, and the tests record what each family actually does -
including where it fails. Several assertions below encode FAILURES on purpose,
so that a family cannot later be adopted without someone deleting an explicit
statement of its known defect.
"""

from __future__ import annotations

import math

import pytest

from backend.research.set_chase_efficiency.baskets import ChaseCandidate
from backend.research.set_chase_efficiency.tiers import (
    COUNT_PERCENTILES,
    candidate_rules,
    candidate_systems,
    count_percentile_rule,
    discrete_k,
    jaccard,
    log_zscore_rule,
    multiple_of_quantile_rule,
    ordered,
    relative_to_top_rule,
    shocked_cards,
)


def card(index: int, price: float) -> ChaseCandidate:
    return ChaseCandidate(
        entity_id=index, card_variant_id=f"v{index}", card_id=f"c{index}",
        card_name=f"Card {index}", card_number=f"{index:03d}",
        printing_type="holo", rarity_key="hits", price=price,
        price_captured_at="2026-08-28", price_source="src", pull_count=100)


def universe(prices):
    return [card(i, price) for i, price in enumerate(prices)]


# --- Phase 17 fixtures: the controlled cases -------------------------------

CASE_A = universe([500.0] + [5.0] * 99)                    # one hero, bulk tail
CASE_B = universe([100.0] * 10 + [5.0] * 90)               # ten real chases
CASE_C = universe([100.0 - i for i in range(20)] + [4.0] * 80)  # tight cluster
CASE_D = universe([40.0, 30.0, 25.0] + [3.0] * 97)         # weak singles
CASE_E = universe([60.0, 55.0, 50.0, 45.0, 40.0, 35.0, 30.0, 25.0]
                  + [8.0] * 92)                            # many modest cards
CASE_F = universe([900.0, 180.0, 150.0, 120.0, 90.0] + [4.0] * 95)  # hero + real seconds

CASES = {"A_single_hero": CASE_A, "B_ten_chases": CASE_B, "C_tight_cluster": CASE_C,
         "D_weak_singles": CASE_D, "E_many_modest": CASE_E, "F_hero_plus_seconds": CASE_F}


# --- Discrete rounding ------------------------------------------------------

def test_ceil_rounding_never_produces_an_empty_tier():
    """A percentage that rounds to zero cards is not a tier rule."""
    for population in (1, 5, 12, 30, 39):
        for fraction in COUNT_PERCENTILES:
            assert discrete_k(fraction, population, mode="ceil") >= 1


def test_floor_rounding_would_produce_empty_tiers_without_the_clamp():
    """Documents WHY ceil is the default: floor(0.025 * 30) is 0."""
    assert math.floor(0.025 * 30) == 0
    # The clamp rescues it, but only because the minimum is enforced.
    assert discrete_k(0.025, 30, mode="floor") == 1
    assert discrete_k(0.025, 30, mode="floor", minimum=0) == 0


def test_round_mode_is_half_up_not_bankers():
    """Python's round(2.5) is 2; that would make even K smaller than odd K."""
    assert discrete_k(0.05, 50, mode="round") == 3  # 2.5 -> 3
    assert round(2.5) == 2                          # the trap being avoided


def test_k_never_exceeds_the_population():
    assert discrete_k(0.20, 3, mode="ceil") == 1 or discrete_k(0.20, 3, mode="ceil") <= 3


# --- Ordering ---------------------------------------------------------------

def test_ordering_is_deterministic_under_ties():
    tied = [card(3, 10.0), card(1, 10.0), card(2, 10.0)]
    assert [c.entity_id for c in ordered(tied)] == [c.entity_id for c in ordered(tied[::-1])]


# --- Monotonicity invariants ------------------------------------------------

@pytest.mark.parametrize("name", list(CASES))
def test_wider_percentiles_are_supersets_of_narrower_ones(name):
    cards = CASES[name]
    previous = None
    for fraction in COUNT_PERCENTILES:
        chosen = {c.entity_id for c in count_percentile_rule(fraction).select(cards, 10.0)}
        if previous is not None:
            assert previous <= chosen, f"{name}: top {fraction:.1%} is not a superset"
        previous = chosen


@pytest.mark.parametrize("name", list(CASES))
def test_higher_economic_floors_select_fewer_cards(name):
    cards = CASES[name]
    previous = None
    for floor in (1.0, 2.0, 3.0, 5.0, 10.0):
        chosen = {c.entity_id for c in
                  count_percentile_rule(0.20, cost_floor=floor).select(cards, 10.0)}
        if previous is not None:
            assert chosen <= previous, f"{name}: floor {floor} selected more, not fewer"
        previous = chosen


def test_economic_floor_returns_nothing_without_a_usable_pack_cost():
    """A floor expressed in packs is meaningless with no pack price."""
    rule = count_percentile_rule(0.10, cost_floor=5.0)
    assert rule.select(CASE_B, None) == []
    assert rule.select(CASE_B, 0.0) == []


# --- Phase 17: the pathological behaviours ---------------------------------

def test_case_a_pure_percentile_manufactures_fake_chases():
    """THE HEADLINE FAILURE of percentile-only rules.

    One $500 hero and 99 identical $5 commons. Top 5% selects five cards, so
    four $5 commons - worth half a pack - are declared chases purely because
    they are tied for second in a set with nothing else in it.
    """
    chosen = count_percentile_rule(0.05).select(CASE_A, 10.0)
    assert len(chosen) == 5
    assert sum(1 for c in chosen if c.price == 5.0) == 4


def test_case_a_economic_floor_repairs_it():
    """The same case with a floor selects exactly the one real chase."""
    chosen = count_percentile_rule(0.05, cost_floor=2.0).select(CASE_A, 10.0)
    assert [c.price for c in chosen] == [500.0]


def test_case_b_percentile_undercounts_a_genuinely_deep_set():
    """Ten real $100 chases, but top 5% can only ever name five of them.

    The mirror-image failure: a percentage cannot express "this set happens to
    have ten chases" because K is pinned to set size, not to the distribution.
    """
    assert len(count_percentile_rule(0.05).select(CASE_B, 10.0)) == 5
    assert len(count_percentile_rule(0.10).select(CASE_B, 10.0)) == 10
    floored = count_percentile_rule(0.20, cost_floor=2.0).select(CASE_B, 10.0)
    assert len(floored) == 10, "the floor should stop exactly at the $5 tail"


def test_case_d_weak_set_produces_no_chases_under_an_economic_floor():
    """A set whose best card is 4x a pack should not get a 5x Core tier."""
    assert count_percentile_rule(0.05, cost_floor=5.0).select(CASE_D, 10.0) == []
    assert len(count_percentile_rule(0.05, cost_floor=2.0).select(CASE_D, 10.0)) == 3


def test_case_e_cheap_packs_admit_many_modest_cards():
    """With a $2 pack, $25-$60 cards clear 10x cost and are real chases."""
    chosen = count_percentile_rule(0.10, cost_floor=10.0).select(CASE_E, 2.0)
    assert len(chosen) == 8
    assert min(c.price for c in chosen) == 25.0


def test_relative_to_top_collapses_on_a_hero_set():
    """THE HERO-CARD FAILURE the brief asks to be demonstrated.

    In Case F the hero is $900 and the genuine second chase is $180 - exactly
    20% of it. A 33% rule keeps only the hero; a 25% rule still keeps only the
    hero. The rule's answer swings from 1 to 5 cards on where the hero happens
    to sit, which is the definition of scale-sensitivity to a single outlier.
    """
    assert len(relative_to_top_rule(0.33).select(CASE_F, 10.0)) == 1
    assert len(relative_to_top_rule(0.25).select(CASE_F, 10.0)) == 1
    assert len(relative_to_top_rule(0.20).select(CASE_F, 10.0)) == 2
    assert len(relative_to_top_rule(0.10).select(CASE_F, 10.0)) == 5


def test_relative_to_top_over_selects_on_a_flat_set():
    """The same rule on a tight cluster admits nearly everything."""
    assert len(relative_to_top_rule(0.50).select(CASE_C, 10.0)) == 20


def test_log_zscore_needs_a_populated_distribution():
    assert log_zscore_rule(3.0).select(universe([100.0, 50.0]), 10.0) == []


def test_multiple_of_median_is_immune_to_a_joint_price_shift():
    """Scale-free families should not move at all under a market-wide shift."""
    rule = multiple_of_quantile_rule(0.5, 10.0)
    before = {c.entity_id for c in rule.select(CASE_F, 10.0)}
    doubled = [ChaseCandidate(**{**c.__dict__, "price": c.price * 2}) for c in CASE_F]
    after = {c.entity_id for c in rule.select(doubled, 10.0)}
    assert before == after


def test_economic_floor_is_not_immune_to_a_joint_price_shift():
    """And a floor rule SHOULD move, because the economics really did change."""
    rule = count_percentile_rule(0.20, cost_floor=5.0)
    before = {c.entity_id for c in rule.select(CASE_D, 10.0)}
    doubled = [ChaseCandidate(**{**c.__dict__, "price": c.price * 2}) for c in CASE_D]
    after = {c.entity_id for c in rule.select(doubled, 10.0)}
    assert before != after


# --- Two-tier systems -------------------------------------------------------

@pytest.mark.parametrize("name", list(CASES))
def test_core_always_nests_inside_extended_after_application(name):
    """``CORE ⊆ EXTENDED`` is a contract; apply() must never break it."""
    cards = CASES[name]
    for system in candidate_systems():
        applied = system.apply(cards, 10.0)
        core = {c.entity_id for c in applied["core"]}
        extended = {c.entity_id for c in applied["extended"]}
        assert core <= extended, f"{system.key} on {name} violated nesting"


def test_nesting_violations_are_repaired_and_counted():
    """A tight Core floor with a looser Extended floor can invert; it is fixed."""
    from backend.research.set_chase_efficiency.tiers import TierSystem
    system = TierSystem("inverted",
                        count_percentile_rule(0.20, cost_floor=1.0),
                        count_percentile_rule(0.05, cost_floor=1.0))
    applied = system.apply(CASE_B, 10.0)
    assert applied["nestingViolations"] > 0
    assert {c.entity_id for c in applied["core"]} <= {c.entity_id for c in applied["extended"]}


def test_extended_only_cards_exclude_the_core():
    system = next(s for s in candidate_systems() if s.key == "A_pct_only")
    applied = system.apply(CASE_B, 10.0)
    core = {c.entity_id for c in applied["core"]}
    assert not (core & {c.entity_id for c in applied["extendedOnly"]})


# --- Registry ---------------------------------------------------------------

def test_every_candidate_rule_has_a_unique_key_and_description():
    rules = candidate_rules()
    assert len({rule.key for rule in rules}) == len(rules)
    assert all(rule.describe for rule in rules)
    assert {rule.family for rule in rules} == {
        "count_percentile", "percentile_floor", "price_distribution", "relative_to_top"}


def test_every_candidate_system_has_a_unique_key():
    systems = candidate_systems()
    assert len({system.key for system in systems}) == len(systems)


@pytest.mark.parametrize("name", list(CASES))
def test_no_rule_ever_selects_a_card_outside_the_universe(name):
    cards = CASES[name]
    ids = {c.entity_id for c in cards}
    for rule in candidate_rules():
        assert {c.entity_id for c in rule.select(cards, 10.0)} <= ids


# --- Shock helper -----------------------------------------------------------

def test_joint_shock_moves_every_card_by_the_same_factor():
    shocked = shocked_cards(CASE_B, magnitude=0.10, seed=1, joint=True)
    ratios = {round(new.price / old.price, 9)
              for new, old in zip(shocked, CASE_B)}
    assert len(ratios) == 1


def test_independent_shock_moves_cards_differently_and_stays_bounded():
    shocked = shocked_cards(CASE_B, magnitude=0.10, seed=1, joint=False)
    ratios = [new.price / old.price for new, old in zip(shocked, CASE_B)]
    assert len(set(round(r, 9) for r in ratios)) > 1
    assert all(0.9 - 1e-9 <= r <= 1.1 + 1e-9 for r in ratios)


def test_shocks_are_seeded_and_preserve_identity():
    first = shocked_cards(CASE_B, magnitude=0.10, seed=7)
    again = shocked_cards(CASE_B, magnitude=0.10, seed=7)
    assert [c.price for c in first] == [c.price for c in again]
    assert [c.entity_id for c in first] == [c.entity_id for c in CASE_B]
    assert all(c.pull_count == 100 for c in first)


def test_jaccard_edges():
    assert jaccard([1, 2], [1, 2]) == 1.0
    assert jaccard([], []) is None
    assert jaccard([1], [2]) == 0.0
