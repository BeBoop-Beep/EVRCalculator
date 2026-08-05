"""Desirable Outcome Frequency (H, production's F): the slot-aware union contract.

H is a probability that will be shown to users as "about 1 in N packs". Every
property here protects that sentence from being false in a specific way:

  * summing instead of unioning would make big sets look better than they are,
  * treating same-slot cards as independent would overstate H,
  * counting a duplicated database row twice would inflate it silently,
  * returning 0.0 for missing data would assert something no data supports,
  * letting query order matter would make the number irreproducible.
"""

from __future__ import annotations

import pytest

from backend.desirability.desirable_outcome_frequency import (
    MINIMUM_COVERED_DEMAND_SHARE,
    REASON_INSUFFICIENT_COVERAGE,
    REASON_NO_ELIGIBLE_CARD,
    REASON_NO_PULL_MODEL,
    compute_desirable_outcome_frequency,
)


def subject(key, *, excess=10.0, cards=(), name=None):
    """A minimal subject. `appeal_excess` is what eligibility selects on."""
    return {
        "subject_key": key,
        "subject_name": name or key,
        "subject_demand": 50.0 + excess,
        "appeal_excess": excess,
        "cards": list(cards),
    }


def card(probability, slot="slotA", name="c", rarity="Ultra Rare"):
    return {
        "card_name": name,
        "pull_probability": probability,
        "slot_group": slot,
        "rarity": rarity,
    }


# ---------------------------------------------------------------------------
# The union arithmetic
# ---------------------------------------------------------------------------

def test_same_slot_probabilities_add():
    """Two cards in one mutually exclusive slot: P = p1 + p2, not 1-(1-p1)(1-p2)."""
    result = compute_desirable_outcome_frequency(
        [subject("s1", cards=[card(0.10, "slotA", "a"), card(0.20, "slotA", "b")])]
    )
    assert result["available"] is True
    assert result["rawValue"] == pytest.approx(0.30)
    # The independence answer would be 0.28 - materially different and wrong.
    assert result["rawValue"] != pytest.approx(1 - 0.9 * 0.8)


def test_cross_slot_miss_probabilities_multiply():
    """Independent slots: P = 1 - (1-p1)(1-p2)."""
    result = compute_desirable_outcome_frequency(
        [subject("s1", cards=[card(0.10, "slotA", "a"), card(0.20, "slotB", "b")])]
    )
    assert result["rawValue"] == pytest.approx(1 - 0.9 * 0.8)


def test_probability_never_exceeds_one_when_a_slot_is_saturated():
    result = compute_desirable_outcome_frequency(
        [subject("s1", cards=[card(0.7, "slotA", "a"), card(0.8, "slotA", "b")])]
    )
    assert 0.0 <= result["rawValue"] <= 1.0


def test_naive_summation_is_not_used_across_many_cards():
    """Ten 20% cards across ten slots must not sum to 200%."""
    cards = [card(0.20, f"slot{i}", f"c{i}") for i in range(10)]
    result = compute_desirable_outcome_frequency([subject("s1", cards=cards)])
    assert result["rawValue"] == pytest.approx(1 - 0.8 ** 10)
    assert result["rawValue"] < 1.0


# ---------------------------------------------------------------------------
# Eligibility
# ---------------------------------------------------------------------------

def test_non_desirable_subjects_are_excluded():
    """A subject at or below the demand baseline contributes nothing."""
    eligible_only = compute_desirable_outcome_frequency(
        [subject("s1", excess=10.0, cards=[card(0.10)])]
    )
    with_ineligible = compute_desirable_outcome_frequency(
        [
            subject("s1", excess=10.0, cards=[card(0.10)]),
            subject("s2", excess=0.0, cards=[card(0.90, "slotB")]),
        ]
    )
    assert with_ineligible["rawValue"] == pytest.approx(eligible_only["rawValue"])


def test_cards_without_a_pull_probability_are_excluded_and_disclosed():
    result = compute_desirable_outcome_frequency(
        [
            subject("s1", cards=[card(0.10)]),
            subject("s2", cards=[card(None, "slotB")]),
        ]
    )
    assert result["rawValue"] == pytest.approx(0.10)
    assert result["unmodeledDesirableSubjectCount"] == 1
    assert result["eligibleSubjectCount"] == 1
    assert result["desirableSubjectCount"] == 2


def test_no_eligible_card_returns_unavailable_not_zero():
    result = compute_desirable_outcome_frequency([subject("s1", excess=0.0, cards=[card(0.5)])])
    assert result["available"] is False
    assert result["rawValue"] is None
    assert result["rawValue"] != 0.0
    assert result["statusReason"] == REASON_NO_ELIGIBLE_CARD


def test_no_subjects_at_all_returns_unavailable_with_a_pull_model_reason():
    result = compute_desirable_outcome_frequency([])
    assert result["available"] is False
    assert result["statusReason"] == REASON_NO_PULL_MODEL


def test_insufficient_covered_demand_returns_unavailable():
    """Most demand unmodeled: a union over the fragment would look complete."""
    result = compute_desirable_outcome_frequency(
        [
            subject("modeled", excess=1.0, cards=[card(0.10)]),
            subject("unmodeled", excess=99.0, cards=[card(None, "slotB")]),
        ]
    )
    assert result["available"] is False
    assert result["statusReason"] == REASON_INSUFFICIENT_COVERAGE
    assert result["coveredDemandShare"] < MINIMUM_COVERED_DEMAND_SHARE


# ---------------------------------------------------------------------------
# Determinism and robustness
# ---------------------------------------------------------------------------

def test_query_ordering_cannot_change_the_result():
    """Reordering subjects and cards must not move the number."""
    subjects = [
        subject("s1", excess=20.0, cards=[card(0.10, "slotA", "a"), card(0.05, "slotB", "b")]),
        subject("s2", excess=5.0, cards=[card(0.20, "slotB", "c")]),
        subject("s3", excess=8.0, cards=[card(0.02, "slotC", "d")]),
    ]
    forward = compute_desirable_outcome_frequency(subjects)
    reversed_subjects = [
        {**s, "cards": list(reversed(s["cards"]))} for s in reversed(subjects)
    ]
    backward = compute_desirable_outcome_frequency(reversed_subjects)
    assert forward["rawValue"] == pytest.approx(backward["rawValue"])


def test_duplicated_rows_inflate_probability_and_must_be_deduplicated_upstream():
    """A duplicated card row DOES change H - which is why dedup is upstream's job.

    This test documents the boundary honestly rather than asserting a safety the
    module does not provide: `compute_desirable_outcome_frequency` receives an
    already-assembled subject index and cannot tell a genuine second printing
    from a duplicated join row. Both are real cards to it.

    The guarantee lives in `collector_appeal_inputs.build_subject_index`, which
    builds one card entry per card id. If that ever emitted duplicates, H would
    silently rise - so this test exists to keep the dependency visible.
    """
    single = compute_desirable_outcome_frequency(
        [subject("s1", cards=[card(0.10, "slotA", "a")])]
    )
    duplicated = compute_desirable_outcome_frequency(
        [subject("s1", cards=[card(0.10, "slotA", "a"), card(0.10, "slotA", "a")])]
    )
    assert duplicated["rawValue"] > single["rawValue"]


def test_probability_stays_within_zero_and_one_across_many_shapes():
    for probability in (1e-9, 0.001, 0.25, 0.5, 0.999, 1.0):
        result = compute_desirable_outcome_frequency(
            [subject("s1", cards=[card(probability)])]
        )
        assert 0.0 <= result["rawValue"] <= 1.0


def test_desirability_magnitude_does_not_scale_the_probability():
    """H is a probability. Demand decides ELIGIBILITY, never magnitude.

    Multiplying desirability into H would apply it twice, since D already
    carries it in the candidate formula - and the second application would be
    invisible in the published arithmetic.
    """
    low = compute_desirable_outcome_frequency([subject("s1", excess=1.0, cards=[card(0.10)])])
    high = compute_desirable_outcome_frequency([subject("s1", excess=99.0, cards=[card(0.10)])])
    assert low["rawValue"] == pytest.approx(high["rawValue"])


def test_trainer_and_artist_desirability_are_not_fabricated():
    """Only the Pokemon subject model is used; unsupported types are absent.

    An unsupported subject type must not be invented, substituted, or assigned a
    zero - it simply does not appear, and the payload discloses the counts it
    did use.
    """
    result = compute_desirable_outcome_frequency([subject("s1", cards=[card(0.10)])])
    text = repr(result).lower()
    assert "trainer" not in text
    assert "artist" not in text
    assert result["eligibleSubjectCount"] == 1


def test_payload_carries_the_research_fields_the_brief_requires():
    result = compute_desirable_outcome_frequency(
        [subject("s1", cards=[card(0.10, "slotA"), card(0.05, "slotB")])]
    )
    for field in (
        "rawValue", "displayPercent", "impliedOddsOneInN", "eligibleCardCount",
        "eligibleSubjectCount", "desirableSubjectCount",
        "unmodeledDesirableSubjectCount", "coveredDemandShare", "slotGroupCount",
        "version", "coveragePolicyVersion", "source",
    ):
        assert field in result, f"missing research field {field}"
    assert result["slotGroupCount"] == 2
    assert result["impliedOddsOneInN"] == pytest.approx(1.0 / result["rawValue"], rel=1e-3)
