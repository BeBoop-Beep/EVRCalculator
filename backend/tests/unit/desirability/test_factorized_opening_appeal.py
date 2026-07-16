"""Factorized Opening Appeal - archetype, monotonicity, and purity tests.

Deterministic synthetic tests. They pin the *behaviour* the factorized
constructs must have regardless of what the live cohort happens to say, and
they assert the algebraic claims the results document relies on.
"""

import ast
import inspect
import math

import pytest

from backend.desirability import factorized_opening_appeal as fx
from backend.desirability.factorized_opening_appeal import (
    A_STAR_VARIANTS,
    D_SATURATION_K_VARIANTS,
    F3_ALPHAS,
    FACTORIZED_CANDIDATE_KEYS,
    TOP3_MODE_ACCESS,
    TOP3_MODE_PROBABILITY,
    accessibility_interpretations,
    complement_error,
    compute_a_star,
    compute_d1,
    compute_d2,
    compute_factorized_candidates,
    compute_m_star_m1,
    compute_m_star_m2,
    demand_shares,
    raw_desirability_mass,
    subject_elite_scarcity,
    to_display_scale,
)
from backend.desirability.opening_appeal import build_subjects, compute_accessible_appeal
from backend.desirability.universal_set_desirability import (
    compute_favorite_hit_coverage_raw,
    normalize_favorite_hit_coverage,
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


def _subjects(*cards):
    return build_subjects(list(cards))


# ---------------------------------------------------------------------------
# D - the shared desirability factor
# ---------------------------------------------------------------------------

def test_d2_counts_each_subject_once_and_saturates():
    mass = raw_desirability_mass([100, 75, 50, 10])
    # u = 1.0, 0.5, 0, 0  ->  sqrt(1) + sqrt(0.5)
    assert mass == pytest.approx(1.0 + math.sqrt(0.5))
    result = compute_d2([100, 75, 50, 10])
    assert 0.0 <= result["value"] <= 1.0
    assert result["contributing_subject_count"] == 2
    assert result["distinct_subject_count"] == 4


def test_d2_is_bounded_and_monotone_in_demand_for_every_saturation_constant():
    for k in D_SATURATION_K_VARIANTS:
        low = compute_d2([60, 60], saturation_k=k)["value"]
        high = compute_d2([95, 95], saturation_k=k)["value"]
        assert 0.0 <= low <= high <= 1.0, k


def test_d2_at_default_k_is_algebraically_identical_to_favorite_hit_coverage():
    """D2 is not a new construct: at K_D = 3 it IS one of D1's own components.

    This is the study's key structural finding about D2 - it re-uses Universal
    Roster Appeal's ``favorite_hit_coverage`` term, so 'D1 vs D2' is really
    'the whole roster score vs one third of it'.
    """
    rollups = [
        {"subject_key": "a", "subject_name": "A", "max_desirability_score": 95,
         "rarity_buckets_present": ["ultra_rare"]},
        {"subject_key": "b", "subject_name": "B", "max_desirability_score": 72,
         "rarity_buckets_present": ["ultra_rare"]},
        {"subject_key": "c", "subject_name": "C", "max_desirability_score": 44,
         "rarity_buckets_present": ["ultra_rare"]},
    ]
    raw, _inputs = compute_favorite_hit_coverage_raw(rollups)
    coverage = normalize_favorite_hit_coverage(raw)
    d2 = compute_d2([row["max_desirability_score"] for row in rollups], saturation_k=3.0)
    assert d2["raw_mass"] == pytest.approx(raw, abs=1e-4)
    assert 100.0 * d2["value"] == pytest.approx(coverage, abs=1e-3)


def test_d2_ignores_price_probability_prestige_and_era():
    """D2 must depend on subject demand and nothing else."""
    base = compute_d2([95, 80, 62])["value"]
    assert compute_d2([95, 80, 62])["value"] == base
    # There is no argument by which price/probability/prestige could enter.
    signature = inspect.signature(compute_d2)
    assert set(signature.parameters) == {"subject_demands", "saturation_k"}


def test_d1_is_roster_appeal_rescaled():
    assert compute_d1(88.0) == pytest.approx(0.88)
    assert compute_d1(None) is None
    assert compute_d1(150) == pytest.approx(1.0)  # bounded


# ---------------------------------------------------------------------------
# Desirability is applied exactly once
# ---------------------------------------------------------------------------

def test_scaling_desirability_magnitude_moves_d_but_never_the_structures():
    """The core factorization property.

    Doubling every subject's demand EXCESS leaves the normalized shares q_s
    unchanged, so A* and M* must not move at all. Only D may respond.
    """
    # excess 0.5 / 0.4  ->  doubled to 1.0 / 0.8
    base = _subjects(_card("A", 75, 0.002), _card("B", 70, 0.05, slot="reverse_slot"))
    scaled = _subjects(_card("A", 100, 0.002), _card("B", 90, 0.05, slot="reverse_slot"))

    assert demand_shares(base) == pytest.approx(demand_shares(scaled))
    assert compute_a_star(base)["value"] == pytest.approx(compute_a_star(scaled)["value"])
    assert compute_m_star_m1(base)["value"] == pytest.approx(compute_m_star_m1(scaled)["value"])
    assert compute_m_star_m2(base)["value"] == pytest.approx(compute_m_star_m2(scaled)["value"])
    # ...while D genuinely rises.
    base_d = compute_d2([75, 70])["value"]
    scaled_d = compute_d2([100, 90])["value"]
    assert scaled_d > base_d


def test_factorizing_accessibility_is_a_no_op_against_the_shipping_score():
    """The audit's headline finding, pinned.

    compute_accessible_appeal already weights by appeal_excess/total_excess - a
    NORMALIZED share whose absolute magnitude cancels - so it was never
    double-counting desirability. The 'factor-free' rebuild therefore reproduces
    it exactly. If this test ever fails, one of the two has changed and the
    study's central claim needs revisiting.
    """
    subjects = _subjects(
        _card("A", 95, 0.001, slot="sir_slot"),
        _card("B", 78, 0.04, slot="rare_slot"),
        _card("C", 63, 0.006, slot="reverse_slot"),
        _card("D", 45, 0.05, slot="rare_slot"),  # below baseline: excluded by both
    )
    rebuilt = compute_a_star(subjects)["value"]
    shipping = compute_accessible_appeal(subjects)["score"]
    assert rebuilt * 100.0 == pytest.approx(shipping, abs=1e-4)


def test_m_star_contains_no_desirability_magnitude():
    """Two sets with identical scarcity but wildly different demand must have
    identical M*. The old Elite Chase Magnetism could NOT pass this test - it
    multiplied appeal_excess in, which is the double-counting being removed."""
    unloved = _subjects(_card("A", 55, 0.0008))
    beloved = _subjects(_card("A", 99, 0.0008))
    assert compute_m_star_m1(unloved)["value"] == pytest.approx(compute_m_star_m1(beloved)["value"])
    assert compute_m_star_m2(unloved)["value"] == pytest.approx(compute_m_star_m2(beloved)["value"])


def test_demand_shares_sum_to_one_and_exclude_undesirable_subjects():
    subjects = _subjects(
        _card("A", 100, 0.01), _card("B", 75, 0.01), _card("C", 50, 0.01), _card("D", 20, 0.01)
    )
    shares = demand_shares(subjects)
    assert sum(shares.values()) == pytest.approx(1.0)
    assert set(shares) == {"ref:A", "ref:B"}


# ---------------------------------------------------------------------------
# Purity: no price / EV / profit / prestige
# ---------------------------------------------------------------------------

@pytest.mark.parametrize(
    "contaminant",
    [
        {"market_price": 9999.0},
        {"expected_value": 42.0, "profit_score": 99.0},
        {"set_value": 123456.0},
        {"treatment_prestige": 1.0, "treatment_score": 96},
    ],
)
def test_no_factorized_construct_reads_price_ev_profit_or_prestige(contaminant):
    cards = [_card("A", 90, 0.002), _card("B", 80, 0.02, slot="reverse_slot")]
    clean = _subjects(*cards)
    dirty = build_subjects([{**card, **contaminant} for card in cards])

    assert compute_a_star(dirty)["value"] == pytest.approx(compute_a_star(clean)["value"])
    assert compute_m_star_m1(dirty)["value"] == pytest.approx(compute_m_star_m1(clean)["value"])
    assert compute_m_star_m2(dirty)["value"] == pytest.approx(compute_m_star_m2(clean)["value"])


def test_module_performs_no_database_access():
    source = inspect.getsource(fx)
    for forbidden in ("supabase", "psycopg", "execute(", ".table(", "insert(", "upsert("):
        assert forbidden not in source, forbidden


def _identifiers(module):
    """Every identifier actually referenced in code (docstrings excluded)."""
    tree = ast.parse(inspect.getsource(module))
    names = set()
    for node in ast.walk(tree):
        if isinstance(node, ast.Name):
            names.add(node.id)
        elif isinstance(node, ast.Attribute):
            names.add(node.attr)
        elif isinstance(node, (ast.Import, ast.ImportFrom)):
            names.add(getattr(node, "module", "") or "")
            for alias in node.names:
                names.add(alias.name)
    return names


def test_no_arbitrary_alpha_optimization_loop_exists():
    """Alphas are pre-registered constants, not searched against an outcome."""
    assert F3_ALPHAS == (0.25, 0.50, 0.75)
    names = _identifiers(fx)
    for forbidden in ("argmax", "argmin", "curve_fit", "minimize", "best_alpha", "scipy", "sklearn"):
        assert forbidden not in names, forbidden
    # The candidate key set is fixed and cannot grow with a search.
    keys = set(compute_factorized_candidates(d=0.5, a_star=0.5, m_star=0.5))
    assert keys == set(FACTORIZED_CANDIDATE_KEYS)


# ---------------------------------------------------------------------------
# Slot logic and duplicate collapsing
# ---------------------------------------------------------------------------

def test_probabilities_add_within_a_slot_and_multiply_across_slots():
    same_slot = _subjects(
        _card("A", 90, 0.02, slot="rare_slot"), _card("A", 90, 0.03, slot="rare_slot")
    )
    cross_slot = _subjects(
        _card("A", 90, 0.02, slot="rare_slot"), _card("A", 90, 0.03, slot="reverse_slot")
    )
    assert same_slot[0]["subject_probability"] == pytest.approx(0.05)
    assert cross_slot[0]["subject_probability"] == pytest.approx(1 - 0.98 * 0.97)
    # Independence must NOT be applied inside a shared slot.
    assert same_slot[0]["subject_probability"] != pytest.approx(1 - 0.98 * 0.97)


def test_duplicate_cards_cannot_duplicate_subject_contribution():
    one_card = _subjects(_card("Charizard", 99, 0.001))
    many_cards = _subjects(
        _card("Charizard", 99, 0.001, name="SIR"),
        _card("Charizard", 99, 0.001, name="Hyper", slot="hyper_slot"),
        _card("Charizard", 99, 0.001, name="Gold", slot="gold_slot"),
    )
    assert len(many_cards) == 1, "one Pokemon is exactly one subject"
    # One species occupies exactly one M* slot and one share.
    assert compute_m_star_m1(many_cards)["distinct_subject_count"] == 1
    assert demand_shares(many_cards) == pytest.approx({"ref:Charizard": 1.0})
    assert demand_shares(one_card) == pytest.approx({"ref:Charizard": 1.0})


def test_an_easy_secondary_printing_cannot_erase_elite_scarcity():
    elite_only = _subjects(_card("Charizard", 99, 0.0008, name="Charizard SIR"))
    with_secondary = _subjects(
        _card("Charizard", 99, 0.0008, name="Charizard SIR"),
        _card("Charizard", 99, 0.09, slot="rare_slot", name="Charizard Double Rare"),
    )
    # max() over the subject's cards keeps the elite chase intact; a union
    # probability would have made Charizard look easy and destroyed the signal.
    assert (
        compute_m_star_m1(with_secondary)["value"]
        == pytest.approx(compute_m_star_m1(elite_only)["value"])
    )
    assert subject_elite_scarcity(with_secondary[0])["card_name"] == "Charizard SIR"


def test_missing_pull_data_returns_unavailable_never_zero():
    subjects = _subjects(_card("A", 90, None), _card("B", 80, None))
    assert compute_a_star(subjects) is None
    assert compute_m_star_m1(subjects) is None
    assert compute_m_star_m2(subjects) is None
    assert accessibility_interpretations(subjects) is None
    candidates = compute_factorized_candidates(d=0.9, a_star=None, m_star=None)
    assert set(candidates) == set(FACTORIZED_CANDIDATE_KEYS)
    assert all(value is None for value in candidates.values()), "unavailable, never 0"


# ---------------------------------------------------------------------------
# Bounds
# ---------------------------------------------------------------------------

def test_all_structures_and_formulas_remain_bounded():
    extreme = _subjects(
        _card("A", 100, 0.99, slot="s1"),
        _card("B", 100, 0.0000001, slot="s2"),
        _card("C", 51, 0.5, slot="s3"),
    )
    assert 0.0 <= compute_a_star(extreme)["value"] <= 1.0
    assert 0.0 <= compute_m_star_m1(extreme)["value"] <= 1.0
    assert 0.0 <= compute_m_star_m2(extreme)["value"] <= 1.0
    for d in (0.0, 0.5, 1.0):
        for a in (0.0, 0.5, 1.0):
            for m in (0.0, 0.5, 1.0):
                for key, value in compute_factorized_candidates(d=d, a_star=a, m_star=m).items():
                    assert 0.0 <= value <= 1.0, (key, d, a, m)
    assert to_display_scale(0.5) == 50.0


# ---------------------------------------------------------------------------
# Monotonicity
# ---------------------------------------------------------------------------

def test_increasing_d_can_never_lower_any_candidate():
    for key in FACTORIZED_CANDIDATE_KEYS:
        low = compute_factorized_candidates(d=0.3, a_star=0.4, m_star=0.6)[key]
        high = compute_factorized_candidates(d=0.9, a_star=0.4, m_star=0.6)[key]
        assert high >= low, key


def test_increasing_a_star_never_lowers_a_star_bearing_candidates_and_never_moves_f4():
    a_bearing = ["F1_balanced_multiplicative", "F2_either_path_union", "F5_accessible_roster",
                 "F3_alpha_0.25", "F3_alpha_0.50", "F3_alpha_0.75"]
    low = compute_factorized_candidates(d=0.7, a_star=0.2, m_star=0.5)
    high = compute_factorized_candidates(d=0.7, a_star=0.8, m_star=0.5)
    for key in a_bearing:
        assert high[key] >= low[key], key
    assert high["F4_market_chase"] == pytest.approx(low["F4_market_chase"])
    assert high["F6_roster_baseline"] == pytest.approx(low["F6_roster_baseline"])


def test_increasing_m_star_never_lowers_m_star_bearing_candidates_and_never_moves_f5():
    m_bearing = ["F1_balanced_multiplicative", "F2_either_path_union", "F4_market_chase",
                 "F3_alpha_0.25", "F3_alpha_0.50", "F3_alpha_0.75"]
    low = compute_factorized_candidates(d=0.7, a_star=0.5, m_star=0.2)
    high = compute_factorized_candidates(d=0.7, a_star=0.5, m_star=0.8)
    for key in m_bearing:
        assert high[key] >= low[key], key
    assert high["F5_accessible_roster"] == pytest.approx(low["F5_accessible_roster"])


def test_making_an_elite_card_harder_raises_m_star_and_lowers_a_star():
    """The structural tradeoff, asserted rather than hidden: A* and M* read the
    same probability axis from opposite ends."""
    easy = _subjects(_card("A", 90, 0.05))
    hard = _subjects(_card("A", 90, 0.0005))
    assert compute_m_star_m1(hard)["value"] > compute_m_star_m1(easy)["value"]
    assert compute_a_star(hard)["value"] < compute_a_star(easy)["value"]


def test_one_zero_component_collapses_only_the_multiplicative_formulas():
    zero_m = compute_factorized_candidates(d=0.8, a_star=0.9, m_star=0.0)
    assert zero_m["F1_balanced_multiplicative"] == pytest.approx(0.0)
    assert zero_m["F4_market_chase"] == pytest.approx(0.0)
    # F2 survives on the accessibility path alone; F5 is unaffected by M*.
    assert zero_m["F2_either_path_union"] == pytest.approx(0.8 * 0.9)
    assert zero_m["F5_accessible_roster"] == pytest.approx(0.8 * 0.9)
    # D = 0 collapses everything: structure without desirability is never appeal.
    zero_d = compute_factorized_candidates(d=0.0, a_star=0.9, m_star=0.9)
    assert all(value == pytest.approx(0.0) for value in zero_d.values())


def test_f1_punishes_lopsided_sets_that_f3_cannot_distinguish():
    even = compute_factorized_candidates(d=0.8, a_star=0.5, m_star=0.5)
    lopsided = compute_factorized_candidates(d=0.8, a_star=0.9, m_star=0.1)
    assert even["F1_balanced_multiplicative"] > lopsided["F1_balanced_multiplicative"]
    # The additive candidate at alpha=0.5 cannot tell them apart at all.
    assert even["F3_alpha_0.50"] == pytest.approx(lopsided["F3_alpha_0.50"])


# ---------------------------------------------------------------------------
# Complementarity and F3 degeneracy
# ---------------------------------------------------------------------------

def test_exact_complements_collapse_f3_to_a_rescaled_roster_baseline():
    """The predicted degeneracy, proved arithmetically.

    If M* = 1 - A* then F3(alpha=0.5) = 0.5*D for EVERY A*, carrying zero
    structural information. An equal additive blend of complements is
    mathematically uninformative and must never be recommended.
    """
    d = 0.8
    values = []
    for a in (0.05, 0.25, 0.5, 0.75, 0.95):
        m = 1.0 - a
        assert complement_error(a, m) == pytest.approx(0.0)
        values.append(compute_factorized_candidates(d=d, a_star=a, m_star=m)["F3_alpha_0.50"])
    assert all(v == pytest.approx(0.5 * d) for v in values)
    # ...and it is exactly the F6 baseline rescaled, i.e. rank-identical to D.
    assert values[0] == pytest.approx(0.5 * compute_factorized_candidates(
        d=d, a_star=0.5, m_star=0.5)["F6_roster_baseline"])


def test_f3_degeneracy_note_reports_the_vanishing_slope():
    assert "DEGENERATE" in fx.f3_degeneracy_note(0.50)
    assert "DEGENERATE" not in fx.f3_degeneracy_note(0.25)


def test_single_card_subjects_make_broad_access_and_m2_exact_complements():
    """A* and M* are NOT independent by construction.

    With one card per subject, subject_probability == p_card, so
    broad = sum(q*access(p)) and M2 = sum(q*(1-access(p))) = 1 - broad exactly.
    Independence must never be claimed merely because the live correlation is
    not exactly -1; the algebra is what settles it.
    """
    subjects = _subjects(
        _card("A", 90, 0.004, slot="s1"),
        _card("B", 80, 0.03, slot="s2"),
        _card("C", 70, 0.0006, slot="s3"),
    )
    broad = compute_a_star(subjects, broad_weight=1.0, top3_weight=0.0)["broad_access_structure"]
    m2 = compute_m_star_m2(subjects)["value"]
    # Tolerance is 1e-5 only because reported values are rounded to 6 dp; the
    # underlying identity broad == 1 - M2 is exact.
    assert complement_error(broad, m2) == pytest.approx(0.0, abs=1e-5)


def test_multi_card_subjects_break_exact_complementarity():
    """The complementarity is broken only by multi-card subjects (union
    probability > the rarest card's probability) and by the top3 term."""
    subjects = _subjects(
        _card("A", 90, 0.0006, slot="s1", name="A SIR"),
        _card("A", 90, 0.08, slot="s2", name="A Double Rare"),
        _card("B", 80, 0.03, slot="s3"),
    )
    broad = compute_a_star(subjects, broad_weight=1.0, top3_weight=0.0)["broad_access_structure"]
    m2 = compute_m_star_m2(subjects)["value"]
    assert complement_error(broad, m2) > 0.01


# ---------------------------------------------------------------------------
# Fixed normalization
# ---------------------------------------------------------------------------

def test_fixed_normalization_is_cohort_independent():
    """Adding or removing a set must never move another set's score."""
    set_a = _subjects(_card("A", 95, 0.001), _card("B", 70, 0.04, slot="s2"))
    alone = (
        compute_d2([95, 70])["value"],
        compute_a_star(set_a)["value"],
        compute_m_star_m1(set_a)["value"],
    )
    # Score a wildly different second set; the first set's values cannot move.
    _other = _subjects(_card("Z", 100, 0.00001), _card("Y", 99, 0.5, slot="s9"))
    _other_scores = (
        compute_d2([100, 99])["value"],
        compute_a_star(_other)["value"],
        compute_m_star_m1(_other)["value"],
    )
    again = (
        compute_d2([95, 70])["value"],
        compute_a_star(set_a)["value"],
        compute_m_star_m1(set_a)["value"],
    )
    assert alone == again


# ---------------------------------------------------------------------------
# Variants
# ---------------------------------------------------------------------------

def test_every_a_star_variant_stays_bounded_and_broad_only_ignores_top3():
    subjects = _subjects(_card("A", 95, 0.01), _card("B", 80, 0.002, slot="s2"))
    for name, (broad_w, top3_w) in A_STAR_VARIANTS.items():
        result = compute_a_star(subjects, broad_weight=broad_w, top3_weight=top3_w)
        assert 0.0 <= result["value"] <= 1.0, name
    broad_only = compute_a_star(subjects, broad_weight=1.0, top3_weight=0.0)
    assert broad_only["value"] == pytest.approx(broad_only["broad_access_structure"])
    top3_only = compute_a_star(subjects, broad_weight=0.0, top3_weight=1.0)
    assert top3_only["value"] == pytest.approx(top3_only["top3_access_structure"])


def test_top3_mode_variants_are_both_available_and_differ():
    subjects = _subjects(_card("A", 95, 0.01, slot="s1"), _card("B", 80, 0.002, slot="s2"))
    raw = compute_a_star(subjects, top3_mode=TOP3_MODE_PROBABILITY)
    logged = compute_a_star(subjects, top3_mode=TOP3_MODE_ACCESS)
    assert raw["top3_mode"] == TOP3_MODE_PROBABILITY
    assert logged["top3_mode"] == TOP3_MODE_ACCESS
    # The raw probability term is far smaller than its log-scaled counterpart -
    # this is the documented scale-mixing caveat, made visible.
    assert raw["top3_access_structure"] < logged["top3_access_structure"]
    with pytest.raises(ValueError):
        compute_a_star(subjects, top3_mode="nonsense")


def test_m1_ranks_by_demand_not_by_scarcity():
    """M1 selects the top subjects BY DEMAND, then reads their scarcity.

    A wildly rare but less-loved subject must not displace the most-loved
    subject from slot 1 - that is what keeps M* a description of the *chase
    layer of the desirable roster* rather than a scarcity leaderboard.
    """
    subjects = _subjects(
        _card("Beloved", 99, 0.05, slot="s1"),      # loved, easy
        _card("Obscure", 60, 0.00001, slot="s2"),   # unloved, ultra rare
    )
    result = compute_m_star_m1(subjects, slot_weights=(1.0,))
    assert result["top_subjects"][0]["subject_name"] == "Beloved"
    # Slot 1 therefore reports the beloved subject's LOW scarcity.
    assert result["value"] < 0.5


def test_m1_missing_slots_renormalize_rather_than_inserting_zero():
    single = _subjects(_card("A", 90, 0.0005))
    result = compute_m_star_m1(single)
    assert result["effective_slot_weights"] == [1.0]
    assert result["value"] == pytest.approx(result["top_subjects"][0]["elite_scarcity"])


# ---------------------------------------------------------------------------
# Archetypes (section 9 of the brief)
# ---------------------------------------------------------------------------

def _archetype(cards, demands):
    subjects = _subjects(*cards)
    a = compute_a_star(subjects)
    m = compute_m_star_m1(subjects)
    d = compute_d2(demands)["value"]
    return {
        "d": d,
        "a": a["value"] if a else None,
        "m": m["value"] if m else None,
        "f": compute_factorized_candidates(
            d=d, a_star=a["value"] if a else None, m_star=m["value"] if m else None
        ),
    }


def test_archetype_ordering_is_explainable():
    high_d_high_a_high_m = _archetype(
        [
            _card("A", 95, 0.06, slot="rare_slot"),
            _card("B", 92, 0.05, slot="rare_slot"),
            _card("C", 90, 0.0008, slot="sir_slot"),
            _card("D", 88, 0.0009, slot="gold_slot"),
        ],
        [95, 92, 90, 88],
    )
    high_d_high_a_low_m = _archetype(
        [
            _card("A", 95, 0.08, slot="rare_slot"),
            _card("B", 92, 0.07, slot="rare_slot"),
            _card("C", 90, 0.06, slot="rare_slot"),
        ],
        [95, 92, 90],
    )
    high_d_low_a_high_m = _archetype(
        [
            _card("A", 95, 0.0006, slot="sir_slot"),
            _card("B", 92, 0.0007, slot="gold_slot"),
            _card("C", 90, 0.0008, slot="hyper_slot"),
        ],
        [95, 92, 90],
    )

    # Accessibility and magnetism separate the archetypes as designed.
    assert high_d_high_a_low_m["a"] > high_d_low_a_high_m["a"]
    assert high_d_low_a_high_m["m"] > high_d_high_a_low_m["m"]

    # F4 (market chase) prefers the chase-heavy set; F5 (accessible) prefers the
    # accessible one. They are DIFFERENT constructs, not rival estimates of one.
    assert high_d_low_a_high_m["f"]["F4_market_chase"] > high_d_high_a_low_m["f"]["F4_market_chase"]
    assert high_d_high_a_low_m["f"]["F5_accessible_roster"] > high_d_low_a_high_m["f"]["F5_accessible_roster"]

    # F1 rewards the set that has BOTH.
    assert (
        high_d_high_a_high_m["f"]["F1_balanced_multiplicative"]
        > high_d_low_a_high_m["f"]["F1_balanced_multiplicative"]
    )


def test_low_desirability_extreme_scarcity_earns_almost_no_appeal():
    """Scarcity alone is never appeal: D gates every candidate."""
    low_d = _archetype([_card("A", 52, 0.000001, slot="sir_slot")], [52])
    assert low_d["m"] == pytest.approx(1.0)  # maximally scarce
    assert low_d["f"]["F4_market_chase"] < 0.10  # ...but almost no appeal
    assert low_d["f"]["F1_balanced_multiplicative"] < 0.10


def test_identical_d_and_a_different_m_moves_only_m_bearing_formulas():
    d, a = 0.8, 0.5
    low = compute_factorized_candidates(d=d, a_star=a, m_star=0.2)
    high = compute_factorized_candidates(d=d, a_star=a, m_star=0.9)
    assert high["F4_market_chase"] > low["F4_market_chase"]
    assert high["F5_accessible_roster"] == pytest.approx(low["F5_accessible_roster"])
    assert high["F6_roster_baseline"] == pytest.approx(low["F6_roster_baseline"])


def test_identical_a_and_m_different_d_scales_every_formula_proportionally():
    a, m = 0.4, 0.6
    low = compute_factorized_candidates(d=0.4, a_star=a, m_star=m)
    high = compute_factorized_candidates(d=0.8, a_star=a, m_star=m)
    for key in FACTORIZED_CANDIDATE_KEYS:
        assert high[key] == pytest.approx(2.0 * low[key]), key


# ---------------------------------------------------------------------------
# User-facing interpretations
# ---------------------------------------------------------------------------

def test_accessibility_interpretations_are_internally_consistent():
    subjects = _subjects(_card("A", 95, 0.02, slot="s1"), _card("B", 80, 0.01, slot="s2"))
    reading = accessibility_interpretations(subjects)
    assert reading["p_top3_desirable_subject_per_pack"] > 0
    # A booster box must be at least as likely as an ETB.
    assert reading["p_top3_per_booster_box"] >= reading["p_top3_per_etb"]
    # Median packs must satisfy P(at least one in n packs) ~ 0.5. The reported
    # figure is rounded to 2 dp for display, hence the 1e-3 tolerance.
    p = reading["p_top3_desirable_subject_per_pack"]
    n = reading["median_packs_to_top3_encounter"]
    assert 1.0 - (1.0 - p) ** n == pytest.approx(0.5, abs=1e-3)
