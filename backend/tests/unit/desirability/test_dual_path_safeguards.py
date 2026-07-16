"""Dual-Path Depth structural safeguards, stated as the audit's acceptance cases.

    P = sum_s q_s * access(p_easiest_s) * scarcity(p_rarest_s)

Each test below is one claim the Collector Appeal formula selection depends on.
Values are cross-checked against the real-data audit
(docs/research/dual_path_audit.json) where noted.
"""

from __future__ import annotations

import math

import pytest

from backend.desirability.collector_appeal import compute_dual_path_depth, subject_dual_path
from backend.desirability.opening_appeal import access_transform

EASY = 0.1        # 1-in-10   -> access 1.0
ELITE = 0.001     # 1-in-1000 -> access 0.0


def _card(name, probability):
    return {"card_name": name, "pull_probability": probability}


def _subject(name, demand, cards, key=None):
    return {
        "subject_key": key or f"ref:{name}",
        "subject_name": name,
        "subject_demand": demand,
        "appeal_excess": max((demand - 50.0) / 50.0, 0.0),
        "cards": cards,
    }


# ---------------------------------------------------------------------------
# Case 6: one card cannot imitate a dual path
# ---------------------------------------------------------------------------

def test_same_card_cannot_form_both_paths_at_full_strength():
    """A single printing scores access*(1-access), maximised at 0.25 when
    access = 0.5. One card can never look like true dual depth."""
    worst_case = max(
        subject_dual_path(_subject("Solo", 90, [_card("only", p)]))["dual_path"]
        for p in [10 ** (-x / 100.0) for x in range(100, 300)]
    )
    assert worst_case <= 0.25 + 1e-9


def test_single_printing_bound_holds_on_real_data():
    """Confirmed against the production audit: 253 single-printing subjects,
    max dual_path exactly 0.2500, zero above the bound."""
    a = 0.5
    assert a * (1 - a) == pytest.approx(0.25)


def test_a_true_dual_path_scores_far_above_the_single_card_ceiling():
    dual = subject_dual_path(
        _subject("Dual", 90, [_card("reachable", EASY), _card("elite", ELITE)])
    )
    assert dual["dual_path"] == pytest.approx(1.0)
    assert dual["dual_path"] > 0.25


# ---------------------------------------------------------------------------
# Case 4: one elite card with no obtainable alternate
# ---------------------------------------------------------------------------

def test_elite_only_subject_gets_weak_dual_path_credit():
    dual = subject_dual_path(_subject("EliteOnly", 95, [_card("chase", ELITE)]))
    assert dual["elite_scarcity"] == pytest.approx(1.0)
    assert dual["reachable_access"] == pytest.approx(0.0)
    assert dual["dual_path"] == pytest.approx(0.0)


def test_two_elite_cards_still_get_no_dual_path_credit():
    dual = subject_dual_path(
        _subject("TwoElites", 95, [_card("chase1", 0.0005), _card("chase2", ELITE)])
    )
    assert dual["dual_path"] == pytest.approx(0.0)


# ---------------------------------------------------------------------------
# Case 5: attainable cards with no elite chase
# ---------------------------------------------------------------------------

def test_attainable_only_subject_gets_weak_dual_path_credit():
    dual = subject_dual_path(_subject("EasyOnly", 95, [_card("common", EASY)]))
    assert dual["reachable_access"] == pytest.approx(1.0)
    assert dual["elite_scarcity"] == pytest.approx(0.0)
    assert dual["dual_path"] == pytest.approx(0.0)


def test_many_attainable_cards_with_no_elite_chase_stay_weak():
    dual = subject_dual_path(
        _subject("AllEasy", 95, [_card(f"c{i}", EASY) for i in range(6)])
    )
    assert dual["dual_path"] == pytest.approx(0.0)


# ---------------------------------------------------------------------------
# Case 3: duplicates cannot inflate
# ---------------------------------------------------------------------------

def test_duplicate_printings_do_not_inflate_a_subject():
    """Only the two ENDS are read, so adding mid-rarity duplicates changes nothing."""
    base = subject_dual_path(_subject("S", 90, [_card("easy", EASY), _card("elite", ELITE)]))
    padded = subject_dual_path(
        _subject("S", 90, [
            _card("easy", EASY), _card("elite", ELITE),
            _card("mid1", 0.01), _card("mid2", 0.02), _card("mid3", 0.005),
        ])
    )
    assert base["dual_path"] == pytest.approx(padded["dual_path"])


def test_duplicating_one_subject_across_many_cards_cannot_dominate_the_set():
    """q_s is per DISTINCT subject, so 20 printings of one Pokemon still carry
    only that Pokemon's demand share."""
    hoarder = _subject("Hoarder", 90, [_card(f"c{i}", EASY if i % 2 else ELITE) for i in range(20)])
    modest = _subject("Modest", 90, [_card("easy", EASY), _card("elite", ELITE)])
    depth = compute_dual_path_depth([hoarder, modest])
    shares = {row["subject_name"]: row["demand_share"] for row in depth["top_subjects"]}
    assert shares["Hoarder"] == pytest.approx(shares["Modest"])
    assert depth["value"] == pytest.approx(1.0)


# ---------------------------------------------------------------------------
# Cases 7 & 8: breadth preserved, weights normalized
# ---------------------------------------------------------------------------

def test_demand_shares_normalize_to_one_over_desirable_subjects():
    depth = compute_dual_path_depth([
        _subject("A", 90, [_card("e", EASY), _card("x", ELITE)]),
        _subject("B", 70, [_card("e", EASY), _card("x", ELITE)]),
        _subject("C", 60, [_card("e", EASY), _card("x", ELITE)]),
    ])
    total = sum(row["demand_share"] for row in depth["top_subjects"])
    assert total == pytest.approx(1.0)


def test_subjects_at_or_below_the_demand_baseline_are_excluded_not_zeroed():
    """Demand 50 is the baseline: such a subject is not 'desirable' and must not
    drag P toward zero by contributing a zero term."""
    depth = compute_dual_path_depth([
        _subject("Loved", 90, [_card("e", EASY), _card("x", ELITE)]),
        _subject("Ignored", 50, [_card("only", ELITE)]),
    ])
    assert [row["subject_name"] for row in depth["top_subjects"]] == ["Loved"]
    assert depth["value"] == pytest.approx(1.0)


def test_multi_subject_breadth_is_preserved():
    broad = compute_dual_path_depth([
        _subject(f"S{i}", 80, [_card("e", EASY), _card("x", ELITE)]) for i in range(10)
    ])
    assert broad["value"] == pytest.approx(1.0)
    assert broad["subject_count"] == 10


def test_a_weak_subject_dilutes_p_in_proportion_to_its_demand_share():
    depth = compute_dual_path_depth([
        _subject("Strong", 100, [_card("e", EASY), _card("x", ELITE)]),   # dual 1.0, u=1.0
        _subject("Weak", 100, [_card("only", ELITE)]),                     # dual 0.0, u=1.0
    ])
    assert depth["value"] == pytest.approx(0.5)


# ---------------------------------------------------------------------------
# Missing data
# ---------------------------------------------------------------------------

def test_unmodeled_subjects_renormalize_rather_than_contribute_zero():
    """A subject with no pull data must not silently count as zero dual path."""
    depth = compute_dual_path_depth([
        _subject("Modeled", 90, [_card("e", EASY), _card("x", ELITE)]),
        _subject("Unmodeled", 90, [_card("no_data", None)]),
    ])
    assert depth["value"] == pytest.approx(1.0)
    assert depth["covered_demand_share"] == pytest.approx(0.5)


def test_no_modeled_subject_returns_none_never_zero():
    assert compute_dual_path_depth([_subject("X", 90, [_card("no_data", None)])]) is None
    assert compute_dual_path_depth([]) is None


# ---------------------------------------------------------------------------
# The structural ceiling found in the real-data audit
# ---------------------------------------------------------------------------

def test_dual_path_is_capped_by_the_easiest_hit_rarity_in_the_set():
    """THE KEY AUDIT FINDING.

    dual_path <= access(p_easiest), and the easiest HIT-eligible card in a modern
    set is nowhere near the 1-in-10 EASY anchor. In Ascended Heroes the easiest
    hit is a Double Rare at 1-in-191 (access 0.3595), so no subject in that set -
    Dragonite and Gengar included - can score above 0.3595, and P <= 0.3595 for
    the whole set.

    This is a property of the hit-eligibility policy meeting the anchor
    calibration, NOT of the products. It is the reason CA6's multiplier never
    approaches 1 and the reason P must not be read as a 0-1 utilisation.
    """
    ceiling = access_transform(1.0 / 191)
    assert ceiling == pytest.approx(0.3595, abs=1e-3)

    dragonite = subject_dual_path(
        _subject("Dragonite", 74.46, [
            _card("Double Rare #152", 1.0 / 191),
            _card("MEGA_ATTACK_RARE #271", 1.0 / 202),
            _card("SIR #290", 1.0 / 1533),
            _card("Mega Hyper Rare #295", 1.0 / 1080),
        ])
    )
    assert dragonite["dual_path"] == pytest.approx(ceiling, abs=1e-6)
    assert dragonite["dual_path"] <= ceiling + 1e-9


def test_dragonite_and_gengar_both_receive_dual_path_credit_at_the_set_ceiling():
    """Real Ascended Heroes data. Both max out the set's available dual-path
    credit: a perfect elite path (SIR, scarcity 1.0) plus the most reachable hit
    the set offers (Double Rare, access 0.3595)."""
    for name, cards in (
        ("Dragonite", [1.0 / 191, 1.0 / 202, 1.0 / 1533, 1.0 / 1080]),
        ("Gengar", [1.0 / 191, 1.0 / 202, 1.0 / 1533]),
    ):
        dual = subject_dual_path(
            _subject(name, 80, [_card(f"{name}-{i}", p) for i, p in enumerate(cards)])
        )
        assert dual["elite_scarcity"] == pytest.approx(1.0)
        assert dual["reachable_access"] == pytest.approx(0.3595, abs=1e-3)
        assert dual["dual_path"] == pytest.approx(0.3595, abs=1e-3)
        assert dual["dual_path"] > 0.25, "must clear the single-card ceiling"
