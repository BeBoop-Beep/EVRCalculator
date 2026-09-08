import inspect

import pytest

from backend.scripts.research_collector_c4_set_components import (
    build_groups,
    desirable_frequency,
    group_keys,
    hit_eligible_cards,
    raw_mass,
    roster_score,
)


def card(card_id="1", appeal=70, hit=True, identity="Pikachu", probability=None, slot=None):
    return {"canonical_card_id": card_id, "subject_type": "pokemon", "subject_identity": identity,
            "final_card_collector_appeal": appeal, "hit_eligibility": hit,
            "pull_probability": probability, "slot_group": slot}


def test_duplicate_printings_do_not_create_groups_or_inflate_max_representative():
    one = build_groups([card()], "max")
    duplicate = build_groups([card(), card("2", appeal=55)], "max")
    assert len(one) == len(duplicate) == 1
    assert one[0]["appeal"] == duplicate[0]["appeal"] == 70


def test_pull_probability_is_not_an_input_to_roster_desirability():
    before = roster_score([70, 80], 6)
    assert before == roster_score([70, 80], 6)
    assert set(inspect.signature(roster_score).parameters) == {"values", "k"}


def test_non_hit_card_is_excluded_before_grouping_and_frequency():
    cards = [card(), card("common", 99, hit=False)]
    assert hit_eligible_cards(cards) == [cards[0]]


def test_neutral_is_zero_mass_but_positive_lift_contributes():
    assert raw_mass([50]) == 0
    assert raw_mass([59]) > 0


def test_multi_subject_card_has_two_groups_but_probability_is_deduplicated():
    row = card(probability=.1, slot="rare", identity="Cynthia + Caitlin")
    assert len(group_keys(row)) == 2
    assert desirable_frequency([row, row]) == pytest.approx(.1)


def test_same_slot_adds_and_independent_slots_multiply_misses():
    assert desirable_frequency([card("1", probability=.1, slot="rare"), card("2", probability=.2, slot="rare")]) == pytest.approx(.3)
    assert desirable_frequency([card("1", probability=.1, slot="a"), card("2", probability=.2, slot="b")]) == pytest.approx(.28)


def test_missing_pull_data_is_unavailable_not_zero():
    assert desirable_frequency([card(probability=None)]) is None


def test_price_artist_and_treatment_are_absent_from_formula_inputs():
    names = set(inspect.signature(roster_score).parameters) | set(inspect.signature(desirable_frequency).parameters)
    assert not names & {"price", "market_price", "artist", "treatment"}
