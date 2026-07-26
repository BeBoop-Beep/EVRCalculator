"""Phase 7 — archetype and monotonicity tests for the Opening Appeal candidates.

These are deterministic synthetic tests. They pin the *behaviour* the constructs
must have regardless of what the live data happens to say.
"""

import math

import pytest

from backend.desirability.opening_appeal import (
    OA_BALANCED_KEY,
    OPENING_APPEAL_CANDIDATES,
    access_transform,
    appeal_excess,
    build_subjects,
    compute_accessible_appeal,
    compute_elite_chase_magnetism,
    compute_opening_appeal_candidates,
    scarcity_transform,
    union_probability_from_cards,
)


def _card(subject, demand, probability, *, slot="rare_slot", name=None, rarity="Ultra Rare"):
    return {
        "subject_key": f"ref:{subject}",
        "subject_name": subject,
        "subject_demand": demand,
        "pull_probability": probability,
        "slot_group": slot,
        "card_name": name or f"{subject} {rarity}",
        "rarity": rarity,
    }


# ---------------------------------------------------------------------------
# Transforms
# ---------------------------------------------------------------------------

def test_transforms_hit_their_anchors_and_are_complementary():
    assert access_transform(0.1) == pytest.approx(1.0)
    assert access_transform(0.001) == pytest.approx(0.0)
    assert scarcity_transform(0.1) == pytest.approx(0.0)
    assert scarcity_transform(0.001) == pytest.approx(1.0)
    # Same anchors read from opposite ends: an acknowledged, documented tradeoff.
    for probability in (0.5, 0.1, 0.02, 0.005, 0.001, 0.0001):
        assert access_transform(probability) + scarcity_transform(probability) == pytest.approx(1.0)


def test_appeal_excess_ignores_subjects_at_or_below_baseline():
    assert appeal_excess(100) == pytest.approx(1.0)
    assert appeal_excess(75) == pytest.approx(0.5)
    assert appeal_excess(50) == 0.0
    assert appeal_excess(10) == 0.0


# ---------------------------------------------------------------------------
# Slot logic
# ---------------------------------------------------------------------------

def test_probabilities_add_within_a_slot_and_multiply_across_slots():
    # Same slot -> mutually exclusive -> add.
    same_slot = [
        _card("A", 90, 0.02, slot="rare_slot"),
        _card("A", 90, 0.03, slot="rare_slot"),
    ]
    assert union_probability_from_cards(same_slot) == pytest.approx(0.05)

    # Different slots -> independent -> 1 - (1-p1)(1-p2).
    cross_slot = [
        _card("A", 90, 0.02, slot="rare_slot"),
        _card("A", 90, 0.03, slot="reverse_slot"),
    ]
    assert union_probability_from_cards(cross_slot) == pytest.approx(1 - 0.98 * 0.97)
    # The independence formula must NOT be applied within a shared slot.
    assert union_probability_from_cards(same_slot) != pytest.approx(1 - 0.98 * 0.97)


def test_within_slot_sum_is_clamped_and_missing_pull_data_yields_none():
    saturated = [_card("A", 90, 0.7, slot="s"), _card("A", 90, 0.8, slot="s")]
    assert union_probability_from_cards(saturated) == pytest.approx(1.0)
    assert union_probability_from_cards([_card("A", 90, None)]) is None
    assert union_probability_from_cards([]) is None


# ---------------------------------------------------------------------------
# Monotonicity
# ---------------------------------------------------------------------------

def test_making_a_desirable_card_easier_raises_accessibility():
    hard = build_subjects([_card("A", 90, 0.002), _card("B", 80, 0.002)])
    easy = build_subjects([_card("A", 90, 0.05), _card("B", 80, 0.002)])
    assert compute_accessible_appeal(easy)["score"] > compute_accessible_appeal(hard)["score"]


def test_making_an_elite_desirable_card_harder_raises_magnetism():
    easy = build_subjects([_card("A", 90, 0.05)])
    hard = build_subjects([_card("A", 90, 0.0005)])
    assert compute_elite_chase_magnetism(hard)["score"] > compute_elite_chase_magnetism(easy)["score"]


def test_raising_demand_at_fixed_probability_cannot_lower_magnetism_or_accessibility():
    low = build_subjects([_card("A", 60, 0.002), _card("B", 60, 0.002)])
    high = build_subjects([_card("A", 95, 0.002), _card("B", 60, 0.002)])
    assert compute_elite_chase_magnetism(high)["score"] >= compute_elite_chase_magnetism(low)["score"]
    # Accessibility is an appeal-weighted average of reachability; with equal
    # probabilities it must not fall when demand rises.
    assert compute_accessible_appeal(high)["score"] >= compute_accessible_appeal(low)["score"] - 1e-9


def test_accessible_secondary_printing_cannot_erase_an_elite_chase_magnetism():
    elite_only = build_subjects([_card("Charizard", 99, 0.0008, name="Charizard SIR")])
    with_secondary = build_subjects(
        [
            _card("Charizard", 99, 0.0008, name="Charizard SIR"),
            _card("Charizard", 99, 0.09, slot="rare_slot", name="Charizard Double Rare"),
        ]
    )
    # max() over the subject's cards keeps the elite chase intact. A union
    # probability would have made Charizard look easy and destroyed the signal.
    assert (
        compute_elite_chase_magnetism(with_secondary)["score"]
        == pytest.approx(compute_elite_chase_magnetism(elite_only)["score"])
    )
    assert compute_elite_chase_magnetism(with_secondary)["top_subjects"][0]["driving_card"][
        "card_name"
    ] == "Charizard SIR"


def test_duplicate_cards_of_one_species_cannot_occupy_multiple_magnetism_slots():
    many_cards_one_species = build_subjects(
        [
            _card("Charizard", 99, 0.0008, name="Charizard SIR"),
            _card("Charizard", 99, 0.0009, name="Charizard Hyper", slot="reverse_slot"),
            _card("Charizard", 99, 0.001, name="Charizard Gold", slot="gold_slot"),
        ]
    )
    magnetism = compute_elite_chase_magnetism(many_cards_one_species)
    names = [row["subject_name"] for row in magnetism["top_subjects"]]
    assert names == ["Charizard"], "one species may occupy exactly one chase slot"
    assert magnetism["distinct_subject_count"] == 1
    # A single elite subject renormalizes to the full weight rather than being
    # penalised for slots that cannot exist.
    assert magnetism["effective_slot_weights"] == [1.0]


# ---------------------------------------------------------------------------
# Archetypes
# ---------------------------------------------------------------------------

def _archetype(name, cards):
    subjects = build_subjects(cards)
    accessible = compute_accessible_appeal(subjects)
    magnetism = compute_elite_chase_magnetism(subjects)
    return {
        "name": name,
        "accessible": accessible["score"] if accessible else None,
        "magnetism": magnetism["score"] if magnetism else None,
    }


def test_six_archetypes_order_as_designed():
    # 1. high roster / high accessibility / high magnetism
    both = _archetype(
        "high_all",
        [
            _card("A", 95, 0.06, slot="rare_slot"),
            _card("B", 90, 0.05, slot="rare_slot"),
            _card("C", 88, 0.0008, slot="sir_slot"),
            _card("D", 92, 0.0009, slot="gold_slot"),
        ],
    )
    # 2. high roster / high accessibility / low magnetism
    accessible_only = _archetype(
        "accessible_no_chase",
        [
            _card("A", 95, 0.08, slot="rare_slot"),
            _card("B", 90, 0.07, slot="rare_slot"),
            _card("C", 88, 0.06, slot="rare_slot"),
        ],
    )
    # 3. high roster / low accessibility / high magnetism
    chase_only = _archetype(
        "chase_no_access",
        [
            _card("A", 95, 0.0006, slot="sir_slot"),
            _card("B", 90, 0.0007, slot="gold_slot"),
            _card("C", 88, 0.0008, slot="hyper_slot"),
        ],
    )
    assert accessible_only["accessible"] > chase_only["accessible"]
    assert chase_only["magnetism"] > accessible_only["magnetism"]
    assert both["accessible"] > chase_only["accessible"]
    assert both["magnetism"] > accessible_only["magnetism"]

    # 4. low roster / extreme scarcity: unloved subjects earn no magnetism no
    #    matter how rare the card is - scarcity alone is never appeal.
    low_roster = _archetype("low_roster_extreme_scarcity", [_card("A", 20, 0.00001, slot="sir_slot")])
    assert low_roster["magnetism"] == 0.0 or low_roster["magnetism"] is None

    # 5. one elite chase, no depth  vs  6. deep accessible roster, no elite chase
    one_elite = _archetype("one_elite_chase", [_card("A", 99, 0.0005, slot="sir_slot")])
    deep_accessible = _archetype(
        "deep_accessible",
        [_card(chr(65 + i), 85, 0.05, slot="rare_slot") for i in range(8)],
    )
    assert one_elite["magnetism"] > deep_accessible["magnetism"]
    assert deep_accessible["accessible"] > one_elite["accessible"]


def test_balanced_candidate_rewards_having_both_and_collapses_when_one_is_absent():
    # Same arithmetic mean (60), very different balance -> the geometric mean
    # punishes the lopsided set. This is the explicit product judgment that
    # having BOTH attainable favorites and elite chases beats excelling at one.
    even = compute_opening_appeal_candidates(
        roster_appeal=80, accessible_appeal=60, elite_chase_magnetism=60
    )[OA_BALANCED_KEY]
    lopsided = compute_opening_appeal_candidates(
        roster_appeal=80, accessible_appeal=115, elite_chase_magnetism=5
    )[OA_BALANCED_KEY]
    assert even > lopsided
    # The additive candidates cannot tell those two sets apart at all - that is
    # precisely what the balanced candidate is for.
    for name in OPENING_APPEAL_CANDIDATES:
        even_additive = compute_opening_appeal_candidates(
            roster_appeal=80, accessible_appeal=60, elite_chase_magnetism=60
        )[name]
        lopsided_additive = compute_opening_appeal_candidates(
            roster_appeal=80, accessible_appeal=115, elite_chase_magnetism=5
        )[name]
        assert even_additive == pytest.approx(lopsided_additive), name

    # Missing one submetric entirely collapses the interaction term to 0.
    absent = compute_opening_appeal_candidates(
        roster_appeal=80, accessible_appeal=60, elite_chase_magnetism=0
    )[OA_BALANCED_KEY]
    assert absent == pytest.approx(0.60 * 80)


# ---------------------------------------------------------------------------
# Availability + purity
# ---------------------------------------------------------------------------

def test_missing_pull_data_yields_unavailable_never_zero():
    subjects = build_subjects([_card("A", 90, None), _card("B", 80, None)])
    assert compute_accessible_appeal(subjects) is None
    assert compute_elite_chase_magnetism(subjects) is None
    candidates = compute_opening_appeal_candidates(
        roster_appeal=90, accessible_appeal=None, elite_chase_magnetism=None
    )
    assert set(candidates) == set(OPENING_APPEAL_CANDIDATES) | {OA_BALANCED_KEY}
    assert all(value is None for value in candidates.values()), "unavailable, never 0"


def test_no_opening_appeal_construct_reads_price_or_market_fields():
    cards = [_card("A", 90, 0.002), _card("B", 80, 0.02)]
    baseline_subjects = build_subjects(cards)
    baseline = (
        compute_accessible_appeal(baseline_subjects)["score"],
        compute_elite_chase_magnetism(baseline_subjects)["score"],
    )
    contaminated = build_subjects(
        [
            {**card, "market_price": 9999.0, "set_value": 123456.0, "expected_value": 42.0,
             "profit_score": 99.0, "treatment_score": 96}
            for card in cards
        ]
    )
    assert (
        compute_accessible_appeal(contaminated)["score"],
        compute_elite_chase_magnetism(contaminated)["score"],
    ) == baseline


def test_candidate_weights_sum_to_one():
    for name, weights in OPENING_APPEAL_CANDIDATES.items():
        assert sum(weights.values()) == pytest.approx(1.0), name
