import inspect
import math

from backend.desirability import scoring_config, weighted_rip
from backend.desirability.scoring_config import (
    DEFAULT_RIP_WEIGHTS,
    SET_VALUE_ASSOCIATION_IS_DIAGNOSTIC_ONLY,
    UNIVERSAL_COMPONENT_WEIGHTS,
    renormalize_weights,
    resolve_rip_weights,
)
from backend.desirability.weighted_rip import (
    compute_financial_rip,
    compute_weighted_rip,
    evaluate_set_value_association,
    pillar_redundancy_matrix,
    weight_sensitivity_report,
)
from backend.desirability.universal_set_desirability import (
    assess_desirability_coverage,
    assess_simulation_coverage,
    compute_chase_subject_depth_v3,
    compute_chase_subject_strength_v3,
    compute_favorite_hit_coverage_raw,
    compute_universal_set_desirability,
    eligible_subject_rollups,
    normalize_favorite_hit_coverage,
    rank_universal_scores,
)


def _subject(name, demand, *, reference=None, bucket="major_hit", cards=1, fan=None, trend=None):
    return {
        "subject_key": f"ref:{reference if reference is not None else name}",
        "subject_name": name,
        "pokemon_reference_id": reference if reference is not None else hash(name) % 10000,
        "max_desirability_score": demand,
        "max_fan_score": fan,
        "max_trend_score": trend,
        "best_rarity_bucket": bucket,
        "rarity_buckets_present": [bucket],
        "card_count": cards,
    }


# ---------------------------------------------------------------------------
# Config / weights
# ---------------------------------------------------------------------------

def test_default_rip_weights_sum_to_exactly_one():
    assert math.isclose(sum(DEFAULT_RIP_WEIGHTS.values()), 1.0, abs_tol=1e-12)


def test_universal_component_weights_are_30_25_35_over_90():
    assert math.isclose(UNIVERSAL_COMPONENT_WEIGHTS["chase_subject_strength"], 30 / 90)
    assert math.isclose(UNIVERSAL_COMPONENT_WEIGHTS["chase_subject_depth"], 25 / 90)
    assert math.isclose(UNIVERSAL_COMPONENT_WEIGHTS["favorite_hit_coverage"], 35 / 90)
    assert math.isclose(sum(UNIVERSAL_COMPONENT_WEIGHTS.values()), 1.0, abs_tol=1e-12)


def test_renormalization_is_exact_when_a_component_is_absent():
    renormalized = renormalize_weights(DEFAULT_RIP_WEIGHTS, exclude=("desirability",))
    assert math.isclose(sum(renormalized.values()), 1.0, abs_tol=1e-12)
    assert math.isclose(renormalized["profit"], 0.58 / 0.90)
    assert math.isclose(renormalized["safety"], 0.20 / 0.90)
    assert math.isclose(renormalized["stability"], 0.12 / 0.90)


def test_weights_are_parameters_desirability_zero_and_one_are_valid():
    financial_only = resolve_rip_weights({"desirability": 0.0})
    assert "desirability" not in financial_only
    assert math.isclose(sum(financial_only.values()), 1.0, abs_tol=1e-12)

    pure_desirability = resolve_rip_weights(
        {"profit": 0.0, "safety": 0.0, "stability": 0.0, "desirability": 1.0}
    )
    assert pure_desirability == {"desirability": 1.0}


# ---------------------------------------------------------------------------
# Set-value association is a DIAGNOSTIC, never a gate
# ---------------------------------------------------------------------------

def test_set_value_association_is_descriptive_and_never_gates_rip():
    # Deliberately price-independent construct: a weak set-value correlation is
    # an expected property, not a failure, and must not zero the RIP weight.
    weakly_associated = [
        {"score": 90.0, "set_value": 10.0},
        {"score": 80.0, "set_value": 900.0},
        {"score": 70.0, "set_value": 50.0},
        {"score": 60.0, "set_value": 400.0},
    ]
    association = evaluate_set_value_association(weakly_associated)
    assert association["isDiagnosticOnly"] is True
    assert "clearedToInfluenceRip" not in association
    assert association["spearman"] is not None

    # Regardless of that correlation, desirability keeps its configured weight.
    rip = compute_weighted_rip(
        {"profit": 50.0, "safety": 50.0, "stability": 50.0, "desirability": 100.0}
    )
    assert math.isclose(rip["effectiveWeights"]["desirability"], 0.10, abs_tol=1e-9)
    assert rip["desirabilityIncluded"] is True


def test_no_gate_machinery_survives_anywhere_in_scoring_code():
    # Guards the amendment: gating a pure construct on price correlation would
    # optimize it back toward price contamination.
    for module in (scoring_config, weighted_rip):
        source = inspect.getsource(module)
        assert "clearedToInfluenceRip" not in source.replace(
            "no ``clearedToInfluenceRip`` flag", ""
        ), f"{module.__name__} still carries gate machinery"
    assert SET_VALUE_ASSOCIATION_IS_DIAGNOSTIC_ONLY is True
    assert not hasattr(scoring_config, "set_value_gate_effective_threshold")
    assert not hasattr(weighted_rip, "evaluate_set_value_gate")


def test_rip_has_no_cap_or_clamp_on_desirability_influence():
    # Influence is bounded linearly by the weight only. A max-desirability set
    # must move exactly 0.10 * (100 - 0) versus a zero-desirability set.
    base = {"profit": 50.0, "safety": 50.0, "stability": 50.0}
    high = compute_weighted_rip({**base, "desirability": 100.0})["score"]
    low = compute_weighted_rip({**base, "desirability": 0.0})["score"]
    assert math.isclose(high - low, 10.0, abs_tol=1e-6)


def test_desirability_zero_weight_reproduces_renormalized_financial_only_rip():
    pillars = {"profit": 80.0, "safety": 40.0, "stability": 60.0, "desirability": 95.0}
    zero_weighted = compute_weighted_rip(pillars, weights={"desirability": 0.0})
    financial_only = compute_financial_rip(pillars)
    assert math.isclose(zero_weighted["score"], financial_only["score"], abs_tol=1e-9)
    expected = (0.58 * 80.0 + 0.20 * 40.0 + 0.12 * 60.0) / 0.90
    assert math.isclose(financial_only["score"], round(expected, 4), abs_tol=1e-3)


def test_missing_desirability_data_renormalizes_instead_of_scoring_zero():
    with_missing = compute_weighted_rip(
        {"profit": 80.0, "safety": 40.0, "stability": 60.0, "desirability": None}
    )
    financial_only = compute_financial_rip({"profit": 80.0, "safety": 40.0, "stability": 60.0})
    assert math.isclose(with_missing["score"], financial_only["score"], abs_tol=1e-9)
    assert "desirability" not in with_missing["effectiveWeights"]


def test_pillar_diagnostics_are_report_only_and_do_not_mutate_weights():
    rows = [
        {"set_name": f"s{i}", "profit_score": 50 + i, "safety_score": 40 + (i % 5),
         "stability_score": 60 - (i % 7), "desirability_score": 70 + (i % 3)}
        for i in range(12)
    ]
    before = dict(DEFAULT_RIP_WEIGHTS)
    redundancy = pillar_redundancy_matrix(rows)
    sensitivity = weight_sensitivity_report(rows)
    assert redundancy["pairs"] and all("spearman" in pair for pair in redundancy["pairs"])
    assert sensitivity["comparisons"]
    assert DEFAULT_RIP_WEIGHTS == before, "diagnostics must never mutate shipping weights"


# ---------------------------------------------------------------------------
# Component 1 - Chase Subject Strength
# ---------------------------------------------------------------------------

def test_strength_uses_top3_distinct_subjects_with_50_30_20():
    subjects = eligible_subject_rollups(
        [_subject("A", 90), _subject("B", 80), _subject("C", 70), _subject("D", 60)]
    )
    score, inputs = compute_chase_subject_strength_v3(subjects)
    assert score == round(0.5 * 90 + 0.3 * 80 + 0.2 * 70, 4)
    assert [s["subject_name"] for s in inputs["top_subjects"]] == ["A", "B", "C"]


def test_duplicate_species_cannot_occupy_multiple_strength_slots():
    # Same pokemon_reference_id twice: only one rollup survives selection.
    rows = [
        _subject("Charizard", 99, reference=6),
        _subject("Charizard", 95, reference=6),
        _subject("Pikachu", 90, reference=25),
    ]
    subjects = eligible_subject_rollups(rows)
    assert len(subjects) == 2
    score, inputs = compute_chase_subject_strength_v3(subjects)
    names = [s["subject_name"] for s in inputs["top_subjects"]]
    assert names.count("Charizard") == 1


def test_missing_strength_slots_renormalize_instead_of_inserting_zero():
    one_subject = eligible_subject_rollups([_subject("A", 80)])
    score, inputs = compute_chase_subject_strength_v3(one_subject)
    assert score == 80.0  # 0.50 weight renormalized to 1.0, not 0.5*80
    two_subjects = eligible_subject_rollups([_subject("A", 80), _subject("B", 60)])
    score2, _ = compute_chase_subject_strength_v3(two_subjects)
    assert score2 == round((0.5 * 80 + 0.3 * 60) / 0.8, 4)


# ---------------------------------------------------------------------------
# Component 2 - Chase Subject Depth (HHI / effective count)
# ---------------------------------------------------------------------------

def test_depth_hhi_effective_count_is_correct_for_equal_subjects():
    # 4 equal contributions -> HHI = 4*(0.25^2) = 0.25 -> effective count 4.
    subjects = eligible_subject_rollups([_subject(chr(65 + i), 80) for i in range(4)])
    depth, inputs = compute_chase_subject_depth_v3(subjects)
    assert math.isclose(inputs["effective_subject_count"], 4.0, abs_tol=1e-6)
    assert depth == round(100 * (4 - 1) / (8 - 1), 4)


def test_depth_single_dominant_subject_scores_zero_depth():
    subjects = eligible_subject_rollups([_subject("Solo", 95)])
    depth, inputs = compute_chase_subject_depth_v3(subjects)
    assert inputs["effective_subject_count"] == 1.0
    assert depth == 0.0


def test_depth_is_zero_when_no_subject_clears_the_demand_baseline():
    subjects = eligible_subject_rollups([_subject("A", 30), _subject("B", 40)])
    depth, inputs = compute_chase_subject_depth_v3(subjects)
    assert depth == 0.0
    assert inputs["contributing_subject_count"] == 0


# ---------------------------------------------------------------------------
# Component 3 - Favorite Hit Coverage (diminishing returns, checklist-based)
# ---------------------------------------------------------------------------

def test_favorite_hit_coverage_uses_sqrt_diminishing_returns():
    subjects = eligible_subject_rollups([_subject("A", 100), _subject("B", 75)])
    raw, inputs = compute_favorite_hit_coverage_raw(subjects)
    assert raw == round(math.sqrt(1.0) + math.sqrt(0.5), 4)
    assert inputs["subjects_above_75"] == 1  # strictly above 75


def test_favorite_hit_coverage_ignores_subjects_at_or_below_baseline():
    raw, _ = compute_favorite_hit_coverage_raw(
        eligible_subject_rollups([_subject("A", 50), _subject("B", 10)])
    )
    assert raw == 0.0
    assert normalize_favorite_hit_coverage(0.0) == 0.0


def test_favorite_hit_coverage_saturates_below_100():
    assert normalize_favorite_hit_coverage(1e9) <= 100.0
    assert normalize_favorite_hit_coverage(3.0) == round(100 * (1 - math.exp(-1.0)), 4)


# ---------------------------------------------------------------------------
# Composite + purity
# ---------------------------------------------------------------------------

def test_universal_score_weights_and_price_independence():
    rollups = [_subject("A", 90), _subject("B", 80), _subject("C", 70), _subject("D", 65)]
    baseline = compute_universal_set_desirability(rollups)
    expected = (
        (30 / 90) * baseline["components"]["chase_subject_strength"]
        + (25 / 90) * baseline["components"]["chase_subject_depth"]
        + (35 / 90) * baseline["components"]["favorite_hit_coverage"]
    )
    assert math.isclose(baseline["score"], round(expected, 4), abs_tol=1e-6)

    # Injecting price / treatment / simulation fields must not change anything.
    contaminated = [
        {**row, "market_price": 9999.0, "treatment_score": 96, "pull_rate": 0.001, "set_value": 123456.0}
        for row in rollups
    ]
    assert compute_universal_set_desirability(contaminated)["score"] == baseline["score"]
    for banned in ("market_price", "set_value", "treatment_score", "pull_probability"):
        assert banned in baseline["excluded_inputs"] or banned in ("pull_probability",)


def test_every_full_coverage_set_gets_rank_and_missing_simulation_does_not_suppress():
    rows = [
        {"set_id": "a", "score": 90.0},
        {"set_id": "b", "score": 70.0},
        {"set_id": "c", "score": 80.0},
    ]
    rank_universal_scores(rows)
    assert [row["rank"] for row in sorted(rows, key=lambda r: r["set_id"])] == [1, 3, 2]
    # Simulation coverage is independent: unavailable simulation is not a
    # desirability reason code.
    simulation = assess_simulation_coverage(None)
    assert simulation["status"] == "unavailable"
    desirability = assess_desirability_coverage(
        canonical_card_count=100,
        hit_eligible_card_count=20,
        scored_hit_eligible_card_count=20,
        unique_subject_count=15,
    )
    assert desirability["status"] == "full"
    assert not set(desirability["reasons"]) & set(simulation["reasons"])


def test_desirability_coverage_reason_codes():
    assert assess_desirability_coverage(
        canonical_card_count=0,
        hit_eligible_card_count=0,
        scored_hit_eligible_card_count=0,
        unique_subject_count=0,
    )["status"] == "unavailable"
    partial = assess_desirability_coverage(
        canonical_card_count=100,
        hit_eligible_card_count=20,
        scored_hit_eligible_card_count=12,
        unique_subject_count=10,
    )
    assert partial["status"] == "partial"
    assert "insufficient_link_coverage" in partial["reasons"]
    none_eligible = assess_desirability_coverage(
        canonical_card_count=50,
        hit_eligible_card_count=0,
        scored_hit_eligible_card_count=0,
        unique_subject_count=0,
    )
    assert none_eligible["status"] == "unavailable"
    assert "no_eligible_pokemon_subjects" in none_eligible["reasons"]
