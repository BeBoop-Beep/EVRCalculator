"""Stage VI apparatus invariants.

These tests guard the machinery that decides whether Chase becomes a third
pillar. Several are written so that the OBVIOUS wrong implementation passes a
happy path and fails here: the grouped cross-validation test would pass for a
random-split implementation, and the variance-contribution test would pass for
one that simply reported the nominal weights back.
"""

from __future__ import annotations

import math

import pytest

from backend.research.chase_pillar_stage6 import candidates, control, stats, transforms


# --------------------------------------------------------------------------
# Statistics
# --------------------------------------------------------------------------

def test_spearman_uses_average_ranks_for_ties():
    """Core K is a small integer and ties constantly; competition ranks would lie."""
    assert stats.spearman([1, 2, 3, 4], [7, 7, 7, 7]) is None
    assert stats.spearman([1, 2, 3, 4], [10, 20, 30, 40]) == pytest.approx(1.0)


def test_pearson_and_spearman_disagree_on_a_monotone_nonlinear_pair():
    x = [1, 2, 3, 4, 5, 6]
    y = [v ** 4 for v in x]
    assert stats.spearman(x, y) == pytest.approx(1.0)
    assert stats.pearson(x, y) < 0.98


def test_overlap_classification_matches_the_declared_thresholds():
    assert stats.classify_overlap(0.90) == "strong_redundancy"
    assert stats.classify_overlap(-0.90) == "strong_redundancy"
    assert stats.classify_overlap(0.70) == "moderate_overlap"
    assert stats.classify_overlap(0.10) == "distinct"
    assert stats.classify_overlap(None) == "undefined"


def test_reconstruct_reports_a_perfect_linear_fit_as_perfect():
    x = list(range(20))
    y = [3.0 * v + 1.0 for v in x]
    result = stats.reconstruct(name="y", target=y, predictors={"x": x},
                               groups=["s%d" % (i % 5) for i in range(20)])
    assert result["r2"] == pytest.approx(1.0)
    assert result["crossValidatedR2"] == pytest.approx(1.0)
    assert result["residualShareOfSd"] == pytest.approx(0.0, abs=1e-9)


def test_cross_validated_r2_folds_by_group_not_by_row():
    """The leakage guard.

    ``y`` is pure per-GROUP noise with no relationship to ``x`` at all. A random
    row split would let the model see other rows of the same group and score
    well. Leave-one-group-out cannot, and must report roughly zero or worse.
    """
    groups, x, y = [], [], []
    offsets = {"a": 10.0, "b": -7.0, "c": 3.0, "d": -1.0, "e": 6.0}
    for name, offset in offsets.items():
        for i in range(8):
            groups.append(name)
            x.append(float(i))
            y.append(offset)
    result = stats.reconstruct(name="y", target=y, predictors={"x": x}, groups=groups)
    assert result["r2"] == pytest.approx(0.0, abs=1e-9)
    assert result["crossValidatedR2"] is not None
    assert result["crossValidatedR2"] < 0.05


def test_cross_validated_r2_can_go_negative_and_that_is_meaningful():
    groups = ["a"] * 6 + ["b"] * 6 + ["c"] * 6 + ["d"] * 6
    x = list(range(24))
    y = [100.0 if g in ("a", "c") else -100.0 for g in groups]
    result = stats.reconstruct(name="y", target=y, predictors={"x": x}, groups=groups)
    assert result["crossValidatedR2"] < 0.0


def test_residualising_a_perfect_linear_function_leaves_nothing():
    """The degenerate half: x = 2z has no residual once z is known.

    Asserted on the residual's MAGNITUDE, not on a correlation. Two vectors of
    pure floating-point rounding noise can correlate at almost anything, so a
    correlation assertion here would be measuring the arithmetic, not the model.
    """
    import numpy as np

    z = [float(v) for v in range(30)]
    residual = stats.residualise([2.0 * v for v in z], [z])
    assert float(np.max(np.abs(residual))) < 1e-9


def test_partial_correlation_removes_a_shared_driver():
    """Two variables sharing a driver, each with its own INDEPENDENT component.

    Raw correlation is high because both track ``z``. The partial must collapse
    to roughly zero, because what is left is the two independent components,
    which are uncorrelated by construction.
    """
    import numpy as np

    rng = np.random.default_rng(20260831)
    z = rng.normal(size=400)
    x = 3.0 * z + rng.normal(size=400)
    y = 3.0 * z + rng.normal(size=400)
    result = stats.partial_correlation(x=list(x), y=list(y), controls={"z": list(z)})
    assert result["rawPearson"] > 0.85
    assert abs(result["partialPearson"]) < 0.12


def test_variance_contribution_exposes_a_nominally_small_but_loud_pillar():
    """The Phase-21 trap, stated as a test.

    ``loud`` carries a nominal 10% weight but ten times the spread of ``quiet``,
    so its share of the composite's variance must come out far above 0.10. An
    implementation that echoed the nominal weights would fail here.
    """
    quiet = [50.0 + (i % 5) for i in range(40)]
    loud = [50.0 + 10.0 * (i % 5) for i in range(40)]
    report = stats.variance_contribution(
        {"financial_rip": quiet, "chase": loud},
        {"financial_rip": 0.90, "chase": 0.10})
    share = report["shares"]["chase"]["varianceShare"]
    assert share > 0.30
    total = sum(v["varianceShare"] for v in report["shares"].values())
    assert total == pytest.approx(1.0)


def test_rank_movement_reports_no_movement_for_an_identical_ranking():
    values = [5.0, 3.0, 9.0, 1.0, 7.0]
    labels = list("abcde")
    movement = stats.rank_movement(values, values, labels=labels)
    assert movement["spearman"] == pytest.approx(1.0)
    assert movement["maxMovement"] == 0.0
    assert movement["turnover"]["top5"]["turnover"] == 0


def test_rank_movement_detects_a_reversal():
    values = [1.0, 2.0, 3.0, 4.0, 5.0]
    movement = stats.rank_movement(values, values[::-1], labels=list("abcde"))
    assert movement["spearman"] == pytest.approx(-1.0)
    assert movement["maxMovement"] == 4.0


# --------------------------------------------------------------------------
# Transforms - direction, bounds, anchor independence
# --------------------------------------------------------------------------

def test_the_directional_contract_is_declared_for_every_candidate():
    assert set(transforms.DIRECTION) == set(candidates.ALLOWED_FACTORS)
    assert transforms.DIRECTION["chaseSpend50"] == "lower"


def test_chase_spend_is_inverted_so_cheaper_scores_higher():
    assert transforms.normalize_chase_spend(200.0) > transforms.normalize_chase_spend(5000.0)


def test_every_normalizer_is_bounded_to_zero_hundred():
    extremes = (None, -5.0, 0.0, 1e-9, 1e9)
    for function in (transforms.normalize_any_chase, transforms.normalize_chase_spend,
                     transforms.normalize_ev_return, *transforms.CORE_K_TRANSFORMS.values()):
        for value in extremes:
            score = function(value)
            assert score is not None and 0.0 <= score <= 100.0, (function, value)


def test_a_product_with_no_core_scores_zero_not_missing():
    """Stage V-C established no-Core as a measured zero. It must survive here."""
    row = transforms.normalize_row({"anyChasePerProduct": 0.0, "chaseSpend50": None,
                                    "coreK": 0, "chaseEvReturn": None})
    assert row == {"anyChasePerProduct": 0.0, "chaseSpend50": 0.0,
                   "chaseEvReturn": 0.0, "coreK": 0.0}


def test_normalization_is_independent_of_the_cohort():
    """The forbidden min/max would break this. A fixed anchor cannot."""
    alone = transforms.normalize_any_chase(0.10)
    for other in (0.001, 0.99, 0.5):
        transforms.normalize_any_chase(other)
    assert transforms.normalize_any_chase(0.10) == alone


def test_all_core_k_transforms_are_monotone_non_decreasing():
    for name, function in transforms.CORE_K_TRANSFORMS.items():
        scores = [function(k) for k in range(0, 40)]
        assert all(b >= a - 1e-12 for a, b in zip(scores, scores[1:])), name


def test_the_saturating_transform_actually_saturates():
    """The brief's requirement: 30 chases must not be worth twice 15."""
    fifteen = transforms.core_k_saturating(15)
    thirty = transforms.core_k_saturating(30)
    assert thirty < 2.0 * fifteen
    # The linear control does NOT satisfy it below its own ceiling, which is why
    # it is kept as the null hypothesis rather than quietly dropped.
    assert transforms.core_k_raw(4) == pytest.approx(2.0 * transforms.core_k_raw(2))


def test_anchor_stress_detects_a_transform_that_depends_on_its_anchors():
    values = [0.01, 0.05, 0.10, 0.30, 0.60]
    report = transforms.anchor_stress(
        transforms.normalize_any_chase, values,
        {"tight": {"floor": 0.05, "ceiling": 0.10}})
    # Clamping everything outside a narrow band destroys ordering information,
    # and the apparatus must be able to say so.
    assert report["tight"]["saturatedAtFloor"] >= 1
    assert report["tight"]["saturatedAtCeiling"] >= 1


# --------------------------------------------------------------------------
# Candidates - the Phase 12 prohibitions
# --------------------------------------------------------------------------

def test_chase_depth_cannot_enter_a_candidate():
    with pytest.raises(ValueError):
        candidates.build_candidate("x", "x", ["chaseDepth"], [1.0])


def test_beat_the_buy_cannot_be_paired_with_chase_ev_return():
    with pytest.raises(ValueError):
        candidates.build_candidate("x", "x", ["beatTheBuy", "chaseEvReturn"], [0.5, 0.5])


def test_median_cost_gap_cannot_be_paired_with_chase_spend():
    with pytest.raises(ValueError):
        candidates.build_candidate("x", "x", ["medianCostGap", "chaseSpend50"], [0.5, 0.5])


def test_internal_weights_must_sum_to_one():
    with pytest.raises(ValueError):
        candidates.build_candidate("x", "x", ["coreK", "chaseSpend50"], [0.5, 0.4])


def test_every_enumerated_candidate_is_admissible_and_normalized():
    enumerated = candidates.enumerate_candidates()
    assert enumerated
    for candidate in enumerated:
        candidates.validate_factors(candidate.factors)
        assert sum(candidate.weights) == pytest.approx(1.0)
        assert set(candidate.factors) <= set(candidates.ALLOWED_FACTORS)


def test_a_candidate_score_is_the_declared_weighted_sum():
    candidate = candidates.build_candidate(
        "t", "t", ["coreK", "chaseSpend50"], [0.25, 0.75])
    assert candidate.score({"coreK": 40.0, "chaseSpend50": 80.0}) == pytest.approx(70.0)


def test_a_candidate_refuses_to_score_a_missing_factor():
    candidate = candidates.build_candidate("t", "t", ["coreK"], [1.0])
    assert candidate.score({"coreK": None}) is None


# --------------------------------------------------------------------------
# CONTROL and the donor arithmetic
# --------------------------------------------------------------------------

def test_control_refuses_a_non_canonical_financial_input():
    """Resolved by DECLARED version, never by field position."""
    result = control.control_score(
        financial_rip_v4_score=50.0, collector_appeal_v5_score=70.0,
        financial_version="financial_rip_v3_outcome_profile_25_20_15_25_10_5",
        appeal_version=control.canonical_versions()["collectorAppeal"])
    assert result["supported"] is False
    assert "financial" in result["reason"]


def test_control_matches_the_production_ninety_ten_split():
    versions = control.canonical_versions()
    result = control.control_score(
        financial_rip_v4_score=50.0, collector_appeal_v5_score=100.0,
        financial_version=versions["financialRip"],
        appeal_version=versions["collectorAppeal"])
    assert result["supported"] is True
    assert result["score"] == pytest.approx(0.90 * 50.0 + 0.10 * 100.0)


def test_with_chase_reduces_to_control_when_chase_weight_is_zero():
    value = control.with_chase(financial=50.0, appeal=100.0, chase=999.0,
                               weights={"financial_rip": 0.90, "collector_appeal": 0.10,
                                        "chase": 0.0})
    assert value == pytest.approx(0.90 * 50.0 + 0.10 * 100.0)


def test_donor_weights_always_sum_to_one():
    for donor in ("financial", "collector", "proportional"):
        for share in (0.05, 0.10):
            weights = control.donor_weights(share, donor)
            assert sum(weights.values()) == pytest.approx(1.0)
            assert weights["chase"] == pytest.approx(share)


def test_collector_cannot_fund_more_chase_weight_than_it_holds():
    """A structural fact, not a tuning choice: Collector holds only 0.10."""
    assert control.donor_weights(0.10, "collector")
    assert control.donor_weights(0.15, "collector") == {}
    assert control.donor_weights(0.20, "collector") == {}


def test_proportional_donor_preserves_the_financial_to_collector_ratio():
    base = control.canonical_versions()["overallWeights"]
    weights = control.donor_weights(0.20, "proportional")
    before = base["financial_rip"] / base["collector_appeal"]
    after = weights["financial_rip"] / weights["collector_appeal"]
    assert after == pytest.approx(before)


def test_unknown_donor_is_refused():
    with pytest.raises(ValueError):
        control.donor_weights(0.10, "chase")
