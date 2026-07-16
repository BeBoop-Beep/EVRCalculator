"""Collector Appeal candidate tests (research-only module).

Covers the brief's required areas: formula purity, monotonicity, complementarity
behaviour, candidate/weight registration, no price leakage, no database writes,
missing-data behaviour, reproducibility, fixed normalization, and the absence of
any unregistered formula or weight search.

The synthetic archetypes below are the ten structures named in the brief. They
are built from explicit pull probabilities so every assertion is exact and
cohort-independent.
"""

from __future__ import annotations

import ast
import inspect
import math

import pytest

from backend.desirability import collector_appeal as ca
from backend.desirability.collector_appeal import (
    CA4_WEIGHT_GRID,
    CA5_WEIGHT_GRID,
    CA6_DUAL_PATH_FLOOR,
    CA6_DUAL_PATH_GAIN,
    CA7_LAMBDA_GRID,
    COLLECTOR_APPEAL_CANDIDATE_KEYS,
    COLLECTOR_APPEAL_WEIGHT_GRID,
    FINANCIAL_RATIO,
    axis_position,
    complement_gap,
    compute_collector_appeal_candidates,
    compute_dual_path_depth,
    degeneracy_note,
    dual_path_utility,
    profit_funded_rip_weights,
    proportional_rip_weights,
    subject_dual_path,
)
from backend.desirability.opening_appeal import build_subjects


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


def _candidates(d=0.8, a=0.4, m=0.6, p=0.2):
    return compute_collector_appeal_candidates(d=d, a_star=a, m_star=m, dual_path_depth=p)


# ---------------------------------------------------------------------------
# Registration: nothing may be searched or added after seeing an outcome
# ---------------------------------------------------------------------------

def _identifiers(module):
    """Every identifier actually referenced in code (docstrings excluded)."""
    return _identifiers_of(inspect.getsource(module))


def _identifiers_of(source):
    tree = ast.parse(inspect.getsource(source) if not isinstance(source, str) else source)
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


def test_candidate_and_weight_grids_are_pre_registered_constants():
    assert CA4_WEIGHT_GRID == ((0.75, 0.25), (0.60, 0.40), (0.50, 0.50), (0.40, 0.60), (0.25, 0.75))
    assert CA5_WEIGHT_GRID == ((0.45, 0.45, 0.10), (0.40, 0.40, 0.20), (0.35, 0.35, 0.30))
    assert COLLECTOR_APPEAL_WEIGHT_GRID == (0.10, 0.15, 0.20, 0.25, 0.30)
    assert CA7_LAMBDA_GRID == (0.25, 0.50, 0.75)
    # The computed key set cannot grow beyond the registered tuple.
    assert set(_candidates()) == set(COLLECTOR_APPEAL_CANDIDATE_KEYS)
    # 4 named + 5 CA4 + 3 CA5 + 1 CA6 + 3 CA7
    assert len(COLLECTOR_APPEAL_CANDIDATE_KEYS) == 16


def test_no_optimizer_or_weight_search_exists_in_the_module():
    names = _identifiers(ca)
    for forbidden in (
        "argmax", "argmin", "curve_fit", "minimize", "fmin", "grid_search",
        "best_weight", "optimize", "scipy", "sklearn", "statsmodels",
    ):
        assert forbidden not in names, forbidden


def test_no_price_or_market_input_reaches_any_candidate():
    """Purity is asserted over the CONSTRUCTION surface specifically.

    Scoped to the functions that build candidates rather than the whole module:
    ``profit_funded_rip_weights`` legitimately names the Profit pillar because it
    reweights RIP, and that is a weight, not a price. Walking the whole module
    would either fail on that or invite renaming the variable to dodge the check
    - neither of which tests the actual rule.
    """
    construction = (
        ca.compute_collector_appeal_candidates,
        ca.compute_dual_path_depth,
        ca.subject_dual_path,
        ca.dual_path_utility,
        ca.complement_gap,
        ca.axis_position,
        ca.collector_appeal_payload,
    )
    for function in construction:
        names = _identifiers_of(inspect.getsource(function))
        for forbidden in (
            "price", "market_price", "expected_value", "profit", "set_value", "ev",
            "treatment_prestige", "revenue", "cost", "value_hhi",
        ):
            assert forbidden not in names, f"{function.__name__}: {forbidden}"


def test_rip_weight_helpers_touch_weights_only_and_never_a_price():
    """The reweighting helpers may name pillars; they must not read market data."""
    for function in (ca.proportional_rip_weights, ca.profit_funded_rip_weights):
        names = _identifiers_of(inspect.getsource(function))
        for forbidden in ("market_price", "set_value", "expected_value", "price"):
            assert forbidden not in names, f"{function.__name__}: {forbidden}"


def test_module_performs_no_database_access():
    source = inspect.getsource(ca)
    for forbidden in ("supabase", "insert", "upsert", "delete(", "execute(", "client", "psycopg"):
        assert forbidden not in source, forbidden


def test_candidates_are_deterministic_and_reproducible():
    assert _candidates() == _candidates()
    names = _identifiers(ca)
    for forbidden in ("random", "shuffle", "now", "datetime", "uuid"):
        assert forbidden not in names, forbidden


# ---------------------------------------------------------------------------
# Complementarity: the central mathematical fact
# ---------------------------------------------------------------------------

def test_single_printing_subjects_force_the_complement_gap_to_zero():
    """A+M == 1 exactly when each desirable subject has one printing.

    This is the structural proof that A and M are one axis, not two: with one
    card per subject there is literally no second dimension to measure.
    """
    subjects = _subjects(
        _card("Pikachu", 95, 0.004, slot="hit_slot"),
        _card("Charizard", 90, 0.002, slot="hit_slot"),
        _card("Mew", 80, 0.05, slot="hit_slot"),
    )
    from backend.desirability.factorized_opening_appeal import compute_a_star, compute_m_star_m2

    broad = compute_a_star(subjects)["broad_access_structure"]
    m2 = compute_m_star_m2(subjects)["value"]
    # 1e-6 is the precision floor, not a fudge: compute_a_star reports
    # broad_access_structure rounded to 6 dp, so exact equality is unreachable
    # through the public payload. The identity itself is exact.
    assert broad + m2 == pytest.approx(1.0, abs=1e-6)
    assert complement_gap(broad, m2) == pytest.approx(0.0, abs=1e-6)


def test_complement_gap_is_signed_and_distinguishes_its_two_causes():
    # Positive gap: reach AND chase both present.
    assert complement_gap(0.7, 0.6) == pytest.approx(0.3)
    # Negative gap: a dead middle - weak on both paths at once.
    assert complement_gap(0.3, 0.4) == pytest.approx(-0.3)
    # The two must not be folded together into a magnitude.
    assert complement_gap(0.7, 0.6) != complement_gap(0.3, 0.4)


def test_axis_position_isolates_taste_from_the_dual_path_dimension():
    """A/(A+M) is invariant when both paths scale together."""
    assert axis_position(0.2, 0.8) == pytest.approx(0.2)
    assert axis_position(0.4, 0.6) == pytest.approx(0.4)
    # Same taste coordinate, different gap: position must not move.
    assert axis_position(0.1, 0.4) == pytest.approx(axis_position(0.2, 0.8))
    assert complement_gap(0.1, 0.4) != complement_gap(0.2, 0.8)


def test_ca4_at_equal_weights_is_degenerate_under_complementarity():
    """The 50/50 blend collapses to a rescaled D and cannot rank anything."""
    scores = set()
    for a in (0.1, 0.3, 0.5, 0.7, 0.9):
        result = compute_collector_appeal_candidates(
            d=0.8, a_star=a, m_star=1.0 - a, dual_path_depth=0.2
        )
        scores.add(round(result["CA4_linear_50_50"], 10))
    assert len(scores) == 1, "50/50 must be constant under exact complementarity"
    assert scores.pop() == pytest.approx(0.8 * 0.5)
    assert "DEGENERATE" in degeneracy_note("CA4_linear_50_50")


def test_ca3_is_not_injective_under_complementarity():
    """A highly accessible set and an extreme-chase set score identically.

    This is a construct defect, not a rounding artifact: sqrt(A*(1-A)) is
    symmetric about A=0.5.
    """
    low = compute_collector_appeal_candidates(d=0.8, a_star=0.2, m_star=0.8, dual_path_depth=0.1)
    high = compute_collector_appeal_candidates(d=0.8, a_star=0.8, m_star=0.2, dual_path_depth=0.1)
    assert low["CA3_geometric_balance"] == pytest.approx(high["CA3_geometric_balance"])
    assert "NOT INJECTIVE" in degeneracy_note("CA3_geometric_balance")


def test_ca3_rewards_the_middle_by_construction():
    """Peak at A=0.5 comes from the formula's shape, not from evidence."""
    values = {
        a: compute_collector_appeal_candidates(
            d=1.0, a_star=a, m_star=1.0 - a, dual_path_depth=0.0
        )["CA3_geometric_balance"]
        for a in (0.1, 0.25, 0.5, 0.75, 0.9)
    }
    assert max(values, key=values.get) == 0.5


def test_ca5_interaction_term_is_the_same_hump_as_ca3():
    """With wA = wM the linear part cancels and only the hump remains."""
    values = {
        a: compute_collector_appeal_candidates(
            d=1.0, a_star=a, m_star=1.0 - a, dual_path_depth=0.0
        )["CA5_interaction_35_35_30"]
        for a in (0.1, 0.3, 0.5, 0.7, 0.9)
    }
    assert max(values, key=values.get) == 0.5
    # Symmetric: 0.1 and 0.9 tie, exactly like CA3.
    assert values[0.1] == pytest.approx(values[0.9])


# ---------------------------------------------------------------------------
# Monotonicity
# ---------------------------------------------------------------------------

def test_increasing_d_never_lowers_any_candidate():
    low = _candidates(d=0.4)
    high = _candidates(d=0.9)
    for key in COLLECTOR_APPEAL_CANDIDATE_KEYS:
        assert high[key] >= low[key] - 1e-12, key


def test_increasing_accessibility_never_lowers_an_accessibility_bearing_candidate():
    low = _candidates(a=0.2, m=0.5)
    high = _candidates(a=0.8, m=0.5)
    for key in ("CA1_accessible", "CA3_geometric_balance", "CA4_linear_75_25", "CA5_interaction_40_40_20"):
        assert high[key] >= low[key] - 1e-12, key
    # Candidates carrying no A term must be completely unmoved.
    assert high["CA2_chase"] == pytest.approx(low["CA2_chase"])
    assert high["CA6_dual_path_utility"] == pytest.approx(low["CA6_dual_path_utility"])


def test_increasing_chase_intensity_never_lowers_a_chase_bearing_candidate():
    low = _candidates(a=0.5, m=0.2)
    high = _candidates(a=0.5, m=0.8)
    for key in ("CA2_chase", "CA3_geometric_balance", "CA4_linear_25_75", "CA5_interaction_40_40_20"):
        assert high[key] >= low[key] - 1e-12, key
    assert high["CA1_accessible"] == pytest.approx(low["CA1_accessible"])


def test_increasing_dual_path_depth_never_lowers_ca6():
    low = _candidates(p=0.1)
    high = _candidates(p=0.9)
    assert high["CA6_dual_path_utility"] > low["CA6_dual_path_utility"]


def test_dual_path_utility_floor_and_gain_are_respected():
    assert dual_path_utility(0.0) == pytest.approx(CA6_DUAL_PATH_FLOOR)
    assert dual_path_utility(1.0) == pytest.approx(CA6_DUAL_PATH_FLOOR + CA6_DUAL_PATH_GAIN)
    assert dual_path_utility(None) is None


# ---------------------------------------------------------------------------
# Zero-component and missing-data behaviour
# ---------------------------------------------------------------------------

def test_zero_desirability_collapses_every_multiplicative_candidate_to_zero():
    """Structure without desirability is never appeal.

    Holds for every candidate of the form D * f(...) - which is every candidate
    EXCEPT CA7, whose additive form is examined separately below. The principle
    is unchanged; the exception is now explicit rather than assumed.
    """
    result = _candidates(d=0.0, a=1.0, m=1.0, p=1.0)
    for key in COLLECTOR_APPEAL_CANDIDATE_KEYS:
        if key.startswith("CA7_"):
            continue
        assert result[key] == pytest.approx(0.0), key


def test_ca7_violates_the_zero_desirability_principle_but_only_where_data_cannot_reach():
    """A KNOWN CONSTRUCT BLEMISH IN CA7, recorded rather than smoothed over.

    CA7 = D + lam*P*(1-D). At D = 0 this leaves lam*P, so a set whose Pokemon
    nobody cares about would score up to 0.75 on dual-path structure alone. That
    genuinely violates "structure without desirability is never appeal", and it
    is a real point in CA6's favour (CA6 = D*U collapses to 0 by construction).

    It is latent rather than active because the two metrics share one selection
    rule: P is computed only over subjects with demand strictly above the
    baseline, and returns None - not 0 - when no such subject exists. So P
    cannot be a number unless at least one subject is desirable, and any such
    subject forces D > 0. The D=0 / P>0 quadrant is unreachable by construction,
    not merely unobserved.

    Recorded here so that if the eligibility rule for P is ever loosened, this
    test fails and the blemish becomes reachable before it becomes a bug.
    """
    result = _candidates(d=0.0, a=1.0, m=1.0, p=1.0)
    assert result["CA7_bounded_bonus_25"] == pytest.approx(0.25)
    assert result["CA7_bounded_bonus_75"] == pytest.approx(0.75)
    assert result["CA6_dual_path_utility"] == pytest.approx(0.0)

    # The unreachability proof: no desirable subject -> P is None, not a number.
    undesirable = [
        {
            "subject_key": "ref:1",
            "subject_name": "Nobody",
            "subject_demand": 40.0,
            "appeal_excess": 0.0,
            "cards": [{"card_name": "easy", "pull_probability": 0.1},
                      {"card_name": "elite", "pull_probability": 0.001}],
        }
    ]
    assert compute_dual_path_depth(undesirable) is None


def test_zero_component_behaviour_is_documented_per_candidate():
    result = _candidates(d=0.8, a=0.0, m=0.9, p=0.0)
    assert result["CA1_accessible"] == pytest.approx(0.0)
    assert result["CA3_geometric_balance"] == pytest.approx(0.0)
    # The chase path survives an absent accessibility path.
    assert result["CA2_chase"] > 0
    # CA6 falls back to its floor, never to zero.
    assert result["CA6_dual_path_utility"] == pytest.approx(0.8 * CA6_DUAL_PATH_FLOOR)


def test_missing_inputs_return_none_never_zero():
    for kwargs in (
        {"d": None, "a_star": 0.5, "m_star": 0.5, "dual_path_depth": 0.5},
        {"d": 0.5, "a_star": None, "m_star": 0.5, "dual_path_depth": 0.5},
        {"d": 0.5, "a_star": 0.5, "m_star": None, "dual_path_depth": 0.5},
    ):
        result = compute_collector_appeal_candidates(**kwargs)
        assert all(v is None for v in result.values())
    # Missing dual-path data disables ONLY CA6.
    partial = compute_collector_appeal_candidates(d=0.5, a_star=0.5, m_star=0.5, dual_path_depth=None)
    assert partial["CA6_dual_path_utility"] is None
    assert partial["CA0_desirability_only"] == pytest.approx(0.5)


def test_dual_path_depth_returns_none_when_no_subject_has_modeled_pull_data():
    subjects = _subjects(_card("Pikachu", 95, None))
    assert compute_dual_path_depth(subjects) is None


def test_undesirable_subjects_are_excluded_not_zeroed():
    """A subject at or below the demand baseline contributes nothing at all."""
    subjects = _subjects(
        _card("Pikachu", 95, 0.004, slot="hit_slot"),
        _card("Furret", 50, 0.5, slot="hit_slot"),
    )
    depth = compute_dual_path_depth(subjects)
    assert depth["subject_count"] == 1
    assert depth["top_subjects"][0]["subject_name"] == "Pikachu"


# ---------------------------------------------------------------------------
# Dual-Path Depth construct behaviour
# ---------------------------------------------------------------------------

def test_a_single_printing_subject_cannot_masquerade_as_a_dual_path():
    """One card gives access*(1-access) <= 0.25 for any probability."""
    for probability in (0.0005, 0.005, 0.05, 0.5):
        subject = _subjects(_card("Solo", 90, probability))[0]
        assert subject_dual_path(subject)["dual_path"] <= 0.25 + 1e-12


def test_two_printings_at_different_scarcities_beat_one_printing():
    solo = _subjects(_card("A", 90, 0.002, slot="hit_slot"))[0]
    dual = _subjects(
        _card("A", 90, 0.002, slot="hit_slot", name="A elite"),
        _card("A", 90, 0.10, slot="reverse_slot", name="A reachable"),
    )[0]
    assert subject_dual_path(dual)["dual_path"] > subject_dual_path(solo)["dual_path"]
    assert subject_dual_path(dual)["printing_count"] == 2


def test_dual_path_depth_uses_normalized_shares_so_desirability_magnitude_cancels():
    """Doubling every subject's demand excess must leave P bit-identical."""
    base = _subjects(
        _card("A", 60, 0.002, slot="hit_slot"),
        _card("A", 60, 0.10, slot="reverse_slot"),
        _card("B", 70, 0.004, slot="hit_slot"),
    )
    # excess doubles: (60-50)/50=0.2 -> 0.4 needs demand 70; (70-50)/50=0.4 -> 0.8 needs 90
    doubled = _subjects(
        _card("A", 70, 0.002, slot="hit_slot"),
        _card("A", 70, 0.10, slot="reverse_slot"),
        _card("B", 90, 0.004, slot="hit_slot"),
    )
    assert compute_dual_path_depth(base)["value"] == pytest.approx(
        compute_dual_path_depth(doubled)["value"]
    )


def test_dual_path_depth_normalization_is_fixed_not_cohort_dependent():
    """Scoring a set alone or beside another set must give the same value."""
    subjects = _subjects(
        _card("A", 90, 0.002, slot="hit_slot"),
        _card("A", 90, 0.10, slot="reverse_slot"),
    )
    alone = compute_dual_path_depth(subjects)["value"]
    # Recomputing after an unrelated set exists changes nothing: no shared state.
    _ = compute_dual_path_depth(_subjects(_card("Z", 99, 0.001, slot="hit_slot")))
    assert compute_dual_path_depth(subjects)["value"] == pytest.approx(alone)


# ---------------------------------------------------------------------------
# The ten synthetic archetypes from the brief
# ---------------------------------------------------------------------------

def _archetype(name):
    """Ten set structures with controlled A/M/D structure."""
    if name == "accessible_no_chase":
        return _subjects(
            _card("A", 90, 0.12, slot="hit_slot"), _card("B", 85, 0.15, slot="hit_slot")
        )
    if name == "balanced":
        return _subjects(
            _card("A", 90, 0.02, slot="hit_slot"), _card("B", 85, 0.03, slot="hit_slot")
        )
    if name == "inaccessible_extreme_chase":
        return _subjects(
            _card("A", 90, 0.0005, slot="hit_slot"), _card("B", 85, 0.0008, slot="hit_slot")
        )
    if name == "low_access_low_chase":
        return _subjects(
            _card("A", 90, 0.03, slot="hit_slot"), _card("B", 85, 0.035, slot="hit_slot")
        )
    if name == "dual_path_both":
        # Multi-card subjects: reachable AND elite for the same Pokemon.
        return _subjects(
            _card("A", 90, 0.0008, slot="hit_slot", name="A elite"),
            _card("A", 90, 0.15, slot="reverse_slot", name="A reachable"),
            _card("B", 85, 0.001, slot="hit_slot", name="B elite"),
            _card("B", 85, 0.18, slot="reverse_slot", name="B reachable"),
        )
    if name == "high_d_low_structure":
        return _subjects(
            _card("A", 100, 0.05, slot="hit_slot"), _card("B", 98, 0.05, slot="hit_slot")
        )
    if name == "low_d_extreme_chase":
        return _subjects(
            _card("A", 55, 0.0005, slot="hit_slot"), _card("B", 52, 0.0006, slot="hit_slot")
        )
    if name == "moderate_d_broad_access":
        return _subjects(
            _card("A", 70, 0.10, slot="hit_slot"), _card("B", 68, 0.12, slot="hit_slot"),
            _card("C", 66, 0.11, slot="hit_slot"),
        )
    if name == "one_enormous_chase":
        return _subjects(
            _card("A", 90, 0.0002, slot="hit_slot"), _card("B", 60, 0.20, slot="reverse_slot")
        )
    if name == "several_meaningful_chases":
        return _subjects(
            _card("A", 90, 0.003, slot="hit_slot"), _card("B", 88, 0.003, slot="hit_slot"),
            _card("C", 86, 0.004, slot="hit_slot"),
        )
    if name == "duplicates_same_subject":
        return _subjects(
            _card("A", 90, 0.003, slot="hit_slot", name="A v1"),
            _card("A", 90, 0.003, slot="hit_slot", name="A v2"),
        )
    if name == "distinct_subjects":
        return _subjects(
            _card("A", 90, 0.003, slot="hit_slot"), _card("B", 90, 0.003, slot="hit_slot")
        )
    raise AssertionError(name)


def test_dual_path_archetype_is_the_only_one_that_breaks_complementarity():
    """Archetype 5 (multi-printing subjects) is exactly where the gap opens.

    This is the empirical justification for treating Dual-Path Depth as the
    second dimension: single-printing archetypes sit on the degenerate line.
    """
    from backend.desirability.factorized_opening_appeal import compute_a_star, compute_m_star_m2

    for name in ("accessible_no_chase", "balanced", "inaccessible_extreme_chase", "several_meaningful_chases"):
        subjects = _archetype(name)
        gap = complement_gap(
            compute_a_star(subjects)["broad_access_structure"], compute_m_star_m2(subjects)["value"]
        )
        assert gap == pytest.approx(0.0, abs=1e-6), name

    dual = _archetype("dual_path_both")
    gap = complement_gap(
        compute_a_star(dual)["broad_access_structure"], compute_m_star_m2(dual)["value"]
    )
    assert gap > 0.20, "multi-printing subjects must open a positive gap"


def test_dual_path_depth_ranks_the_archetypes_as_designed():
    depths = {
        name: compute_dual_path_depth(_archetype(name))["value"]
        for name in (
            "dual_path_both", "one_enormous_chase", "balanced",
            "accessible_no_chase", "inaccessible_extreme_chase",
        )
    }
    # The both-paths archetype must lead.
    assert max(depths, key=depths.get) == "dual_path_both"
    # A set with only unreachable elites has almost no dual-path depth.
    assert depths["inaccessible_extreme_chase"] < 0.05
    # A set with only easy hits has no chase to pair with, so also low.
    assert depths["accessible_no_chase"] < 0.15


def test_duplicate_printings_of_one_subject_cannot_outrank_distinct_subjects_on_d():
    """Archetype 10: one Pokemon twice is not two Pokemon."""
    from backend.desirability.factorized_opening_appeal import raw_desirability_mass

    duplicates = _archetype("duplicates_same_subject")
    distinct = _archetype("distinct_subjects")
    assert len(duplicates) == 1
    assert len(distinct) == 2
    dup_mass = raw_desirability_mass([s["subject_demand"] for s in duplicates])
    dis_mass = raw_desirability_mass([s["subject_demand"] for s in distinct])
    assert dis_mass > dup_mass


def test_low_desirability_extreme_chase_earns_little_appeal():
    """Archetype 7: scarcity alone is not appeal."""
    subjects = _archetype("low_d_extreme_chase")
    from backend.desirability.factorized_opening_appeal import compute_m_star_m1

    m = compute_m_star_m1(subjects)["value"]
    depth = compute_dual_path_depth(subjects)["value"]
    result = compute_collector_appeal_candidates(d=0.06, a_star=0.02, m_star=m, dual_path_depth=depth)
    assert m > 0.95, "the chase really is extreme"
    for key in COLLECTOR_APPEAL_CANDIDATE_KEYS:
        assert result[key] < 0.10, key


# ---------------------------------------------------------------------------
# RIP reweighting
# ---------------------------------------------------------------------------

def test_proportional_rescaling_preserves_the_financial_ratio_exactly():
    for weight in COLLECTOR_APPEAL_WEIGHT_GRID:
        weights = proportional_rip_weights(weight)
        assert sum(weights.values()) == pytest.approx(1.0)
        assert weights["desirability"] == pytest.approx(weight)
        # 58:20:12 preserved at every Collector Appeal weight.
        assert weights["profit"] / weights["safety"] == pytest.approx(0.58 / 0.20)
        assert weights["safety"] / weights["stability"] == pytest.approx(0.20 / 0.12)


def test_proportional_rescaling_at_10pct_reproduces_the_shipping_weights():
    weights = proportional_rip_weights(0.10)
    assert weights["profit"] == pytest.approx(0.58, abs=1e-9)
    assert weights["safety"] == pytest.approx(0.20, abs=1e-9)
    assert weights["stability"] == pytest.approx(0.12, abs=1e-9)


def test_collector_appeal_becomes_second_largest_above_18_18_percent():
    """The crossover is 18.18%, NOT 25% as the study brief assumed.

    Under proportional rescaling Safety shrinks as Collector Appeal grows, so
    they cross where w = r/(1+r) with r = 0.20/0.90 -> w = 2/11 = 18.18%.
    Collector Appeal is therefore already the second-largest pillar at a 20%
    weight, and stays below Profit at every weight on the grid.
    """
    crossover = (0.20 / 0.90) / (1.0 + 0.20 / 0.90)
    assert crossover == pytest.approx(2.0 / 11.0)
    for weight in (0.10, 0.15, 0.18):
        weights = proportional_rip_weights(weight)
        assert weights["desirability"] < weights["safety"], weight
    for weight in (0.20, 0.25, 0.30):
        weights = proportional_rip_weights(weight)
        assert weights["desirability"] > weights["safety"], weight
        assert weights["desirability"] < weights["profit"], weight


def test_profit_funded_variant_takes_only_from_profit():
    weights = profit_funded_rip_weights(0.30)
    assert weights["safety"] == pytest.approx(FINANCIAL_RATIO["safety"])
    assert weights["stability"] == pytest.approx(FINANCIAL_RATIO["stability"])
    assert weights["profit"] == pytest.approx(0.58 - 0.20)
    assert sum(weights.values()) == pytest.approx(1.0)


def test_invalid_rip_weights_raise_rather_than_silently_clamp():
    with pytest.raises(ValueError):
        proportional_rip_weights(1.0)
    with pytest.raises(ValueError):
        proportional_rip_weights(-0.1)
    with pytest.raises(ValueError):
        profit_funded_rip_weights(0.75)


# ---------------------------------------------------------------------------
# Bounds
# ---------------------------------------------------------------------------

def test_every_candidate_stays_within_zero_and_one():
    for d in (0.0, 0.5, 1.0):
        for a in (0.0, 0.5, 1.0):
            for m in (0.0, 0.5, 1.0):
                for p in (0.0, 0.5, 1.0):
                    result = compute_collector_appeal_candidates(
                        d=d, a_star=a, m_star=m, dual_path_depth=p
                    )
                    for key, value in result.items():
                        assert 0.0 - 1e-12 <= value <= 1.0 + 1e-12, (key, d, a, m, p)


def test_every_registered_candidate_has_a_degeneracy_note():
    for key in COLLECTOR_APPEAL_CANDIDATE_KEYS:
        note = degeneracy_note(key)
        assert note and note != "unregistered candidate", key
