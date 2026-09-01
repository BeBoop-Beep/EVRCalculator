"""Stage VI-A apparatus invariants.

These tests guard the machinery that sets a production coefficient. Several are
written so that a plausible wrong implementation passes a happy path and fails
here: the override-classification tests would pass for a version that ignored
whether Financial and CONTROL agree, and the attribution test would pass for one
that simply echoed the nominal weights back.
"""

from __future__ import annotations

import math

import numpy as np
import pytest

from backend.research.chase_weight_stage6a import attribution, decisions, pairs, scale, weights


# --------------------------------------------------------------------------
# Core K saturation - exact arithmetic
# --------------------------------------------------------------------------

@pytest.mark.parametrize("k,expected", [
    (0, 0.0), (1, 200.0 / 11), (2, 200.0 * 2 / 12), (3, 600.0 / 13),
    (5, 1000.0 / 15), (10, 100.0), (15, 120.0), (20, 400.0 / 3), (30, 150.0),
])
def test_approved_transform_is_exact(k, expected):
    assert scale.approved_unclamped(k) == pytest.approx(expected, abs=1e-12)


def test_the_approved_formula_exceeds_one_hundred_above_k_ten():
    """The Phase-2 question, pinned. This is (B), a saturating index past 100."""
    assert scale.approved_unclamped(10) == pytest.approx(100.0)
    assert scale.approved_unclamped(11) > 100.0
    assert scale.approved_unclamped(14) == pytest.approx(200.0 * 14 / 24)


def test_the_clamped_variant_destroys_differentiation_above_k_ten():
    """The Stage VI implementation defect, stated as a test rather than prose."""
    assert scale.approved_clamped(11) == scale.approved_clamped(30) == 100.0
    assert scale.approved_unclamped(11) < scale.approved_unclamped(30)


def test_the_rescaled_variant_is_a_true_zero_hundred_pillar():
    assert scale.rescaled_0_100(10) == pytest.approx(50.0)
    assert scale.rescaled_0_100(10_000) < 100.0
    assert all(0.0 <= scale.rescaled_0_100(k) < 100.0 for k in range(0, 500))


def test_every_variant_preserves_the_same_product_order():
    """Order identity is what makes the scale choice a labelling decision."""
    ks = [0, 1, 2, 3, 4, 5, 8, 10, 12, 14]
    base = [scale.approved_unclamped(k) for k in ks]
    rescaled = [scale.rescaled_0_100(k) for k in ks]
    assert all(
        (base[i] < base[j]) == (rescaled[i] < rescaled[j])
        for i in range(len(ks)) for j in range(len(ks)))


def test_rescaled_is_exactly_half_the_approved_transform():
    for k in range(0, 40):
        assert scale.rescaled_0_100(k) == pytest.approx(
            scale.approved_unclamped(k) / 2.0, abs=1e-12)


def test_zero_and_negative_core_k_score_zero_not_missing():
    for value in (0, -3, None, "x", float("nan")):
        assert scale.approved_unclamped(value) == 0.0


def test_dispersion_equivalent_weight_explains_the_leverage():
    """A pillar with 3x the spread at 5% behaves like a 15% reference pillar."""
    result = scale.dispersion_equivalent_weight(
        reference_sd=8.0, pillar_sd=24.0, reference_weight=0.90, nominal_weight=0.05)
    assert result["dispersionRatio"] == pytest.approx(3.0)
    assert result["effectiveAsReference"] == pytest.approx(0.15)


# --------------------------------------------------------------------------
# The weight grid and its funding rule
# --------------------------------------------------------------------------

BASE = {"financial_rip": 0.90, "collector_appeal": 0.10}


def test_every_grid_entry_sums_to_one():
    for entry in weights.chase_grid(base=BASE):
        assert sum(entry["weights"].values()) == pytest.approx(1.0)


def test_collector_is_held_fixed_across_the_whole_grid():
    for entry in weights.chase_grid(base=BASE):
        assert entry["weights"]["collector_appeal"] == pytest.approx(0.10)


def test_chase_is_funded_only_from_financial():
    for entry in weights.chase_grid(base=BASE):
        share = entry["chaseWeight"]
        assert entry["weights"]["financial_rip"] == pytest.approx(0.90 - share)
        assert entry["weights"]["chase"] == pytest.approx(share)


def test_a_chase_weight_larger_than_financial_is_refused():
    assert weights.chase_grid([0.95], base=BASE) == []


def test_weight_zero_reproduces_control_exactly():
    zero = [e for e in weights.chase_grid(base=BASE) if e["chaseWeight"] == 0.0][0]
    for financial, collector, chase in ((50.0, 70.0, 116.0), (12.5, 99.0, 0.0)):
        assert weights.blend(financial=financial, collector=collector, chase=chase,
                             weights=zero["weights"]) == pytest.approx(
            0.90 * financial + 0.10 * collector)


def test_score_point_semantics_is_literal_arithmetic():
    semantics = weights.score_point_semantics(
        {"financial_rip": 0.85, "collector_appeal": 0.10, "chase": 0.05})
    assert semantics["perPillar"]["chase"] == pytest.approx(0.5)
    assert semantics["perPillar"]["financial_rip"] == pytest.approx(8.5)
    assert semantics["chasePointsPerFinancialPoint"] == pytest.approx(17.0)


# --------------------------------------------------------------------------
# Monotonicity and ordering invariants
# --------------------------------------------------------------------------

def test_higher_chase_gains_relative_to_lower_chase_as_weight_rises():
    """The defining property of a Chase coefficient."""
    previous = None
    for share in (0.0, 0.01, 0.03, 0.05, 0.10):
        weight_set = {"financial_rip": 0.90 - share, "collector_appeal": 0.10,
                      "chase": share}
        low = weights.blend(financial=40.0, collector=70.0,
                            chase=scale.approved_unclamped(1), weights=weight_set)
        high = weights.blend(financial=40.0, collector=70.0,
                             chase=scale.approved_unclamped(14), weights=weight_set)
        gap = high - low
        if previous is not None:
            assert gap > previous
        previous = gap


def test_identical_chase_scores_cannot_change_pairwise_ordering():
    """If two products share a Chase score, no weight can reorder them."""
    for share in (0.0, 0.02, 0.05, 0.10, 0.30):
        weight_set = {"financial_rip": 0.90 - share, "collector_appeal": 0.10,
                      "chase": share}
        a = weights.blend(financial=45.0, collector=60.0, chase=66.7, weights=weight_set)
        b = weights.blend(financial=41.0, collector=60.0, chase=66.7, weights=weight_set)
        assert a > b


def test_financial_only_differences_behave_monotonically():
    weight_set = {"financial_rip": 0.85, "collector_appeal": 0.10, "chase": 0.05}
    scores = [weights.blend(financial=f, collector=70.0, chase=50.0,
                            weights=weight_set) for f in (10.0, 20.0, 30.0, 40.0)]
    assert scores == sorted(scores)
    assert scores[1] - scores[0] == pytest.approx(scores[2] - scores[1])


def test_a_missing_pillar_value_refuses_rather_than_scoring_zero():
    weight_set = {"financial_rip": 0.85, "collector_appeal": 0.10, "chase": 0.05}
    assert weights.blend(financial=None, collector=70.0, chase=50.0,
                         weights=weight_set) is None
    # ...but a pillar carrying zero weight is not consulted at all.
    zero = {"financial_rip": 0.90, "collector_appeal": 0.10, "chase": 0.0}
    assert weights.blend(financial=40.0, collector=70.0, chase=None,
                         weights=zero) == pytest.approx(43.0)


# --------------------------------------------------------------------------
# Variance attribution
# --------------------------------------------------------------------------

def _components(seed=7, n=120):
    rng = np.random.default_rng(seed)
    financial = rng.normal(30.0, 8.0, n)
    return {
        "financial_rip": list(financial),
        "collector_appeal": list(rng.normal(80.0, 11.0, n)),
        "chase": list(0.5 * financial + rng.normal(50.0, 25.0, n)),
    }


def test_covariance_and_shapley_shares_reconcile_to_the_total():
    weight_set = {"financial_rip": 0.85, "collector_appeal": 0.10, "chase": 0.05}
    result = attribution.attribute(_components(), weight_set)
    assert result["covarianceSumsToOne"] == pytest.approx(1.0, abs=1e-9)
    assert result["shapleySumsToOne"] == pytest.approx(1.0, abs=1e-9)


def test_direct_variance_deliberately_does_not_sum_to_one():
    """It ignores covariance, and the report must not pretend otherwise."""
    weight_set = {"financial_rip": 0.85, "collector_appeal": 0.10, "chase": 0.05}
    shares = attribution.direct_variance(_components(), weight_set)
    assert sum(shares.values()) < 0.999


def test_attribution_does_not_merely_echo_the_nominal_weights():
    """The Phase-21 trap: a wide pillar must report more than its coefficient."""
    weight_set = {"financial_rip": 0.90, "collector_appeal": 0.05, "chase": 0.05}
    components = {"financial_rip": [50.0 + (i % 5) for i in range(60)],
                  "collector_appeal": [80.0 + (i % 3) for i in range(60)],
                  "chase": [50.0 + 20.0 * (i % 5) for i in range(60)]}
    result = attribution.attribute(components, weight_set)
    assert result["shares"]["shapley"]["chase"] > 0.20
    assert result["chaseLeverage"]["shapley"] > 4.0


def test_a_zero_weight_pillar_contributes_nothing():
    weight_set = {"financial_rip": 0.90, "collector_appeal": 0.10, "chase": 0.0}
    result = attribution.attribute(_components(), weight_set)
    assert result["shares"]["shapley"]["chase"] == pytest.approx(0.0, abs=1e-12)
    assert result["shares"]["covariance"]["chase"] == pytest.approx(0.0, abs=1e-12)


# --------------------------------------------------------------------------
# Override classification
# --------------------------------------------------------------------------

def test_band_edges_are_assigned_to_exactly_one_band():
    assert pairs.band_of(0.0) == "<=2"
    assert pairs.band_of(2.0) == "2-5"
    assert pairs.band_of(9.99) == "5-10"
    assert pairs.band_of(10.0) == "10-15"
    assert pairs.band_of(1000.0) == ">20"


def test_a_close_flip_is_counted_and_a_clear_one_is_not_when_none_occurs():
    """A flips ahead of B on Chase across a 1-point Financial gap: CLOSE only."""
    result = pairs.pairwise_overrides(
        control=[50.0, 51.0], candidate=[52.0, 51.0], financial=[40.0, 41.0],
        labels=["a", "b"], core_k=[12, 0], sets=["s", "s"])
    assert result["perBand"]["<=2"]["overrides"] == 1
    assert result["clearOverrides"] == 0
    assert result["sameSetOverrides"] == 1


def test_a_clear_override_is_counted_when_financial_agrees_with_control():
    result = pairs.pairwise_overrides(
        control=[50.0, 62.0], candidate=[63.0, 62.0], financial=[30.0, 45.0],
        labels=["a", "b"], core_k=[14, 0], sets=["s", "t"])
    # |30 - 45| = 15.0, which falls in the "15-20" band, not "10-15".
    assert result["clearOverrides"] == 1
    assert result["perBand"]["10-15"]["financialAlignedOverrides"] == 0
    assert result["perBand"]["15-20"]["financialAlignedOverrides"] == 1
    assert result["worstOverrides"][0]["financialGapOverturned"] == pytest.approx(15.0)


def test_a_flip_is_not_a_clear_override_when_collector_already_inverted_financial():
    """The discipline that keeps the override rate honest.

    CONTROL ranks A above B even though B has the better Financial score,
    because Collector Appeal put A ahead. Chase flipping that back is not Chase
    overturning a superior financial profile - it is Chase agreeing with it.
    """
    result = pairs.pairwise_overrides(
        control=[60.0, 55.0], candidate=[54.0, 55.0], financial=[20.0, 40.0],
        labels=["a", "b"], core_k=[0, 5], sets=["s", "t"])
    # |20 - 40| = 20.0, which is the lower edge of the ">20" band.
    assert result["perBand"][">20"]["overrides"] == 1
    assert result["clearOverrides"] == 0


def test_exactly_tied_control_scores_are_not_treated_as_overrides():
    result = pairs.pairwise_overrides(
        control=[50.0, 50.0], candidate=[51.0, 50.0], financial=[40.0, 40.0],
        labels=["a", "b"], core_k=[5, 0], sets=["s", "s"])
    assert result["perBand"]["<=2"]["overrides"] == 0


def test_within_set_winner_change_is_classified_by_the_financial_gap():
    rows = [
        {"set": "S", "productName": "cheap", "financialRip": 30.0,
         "collectorAppeal": 70.0, "coreK": 12},
        {"set": "S", "productName": "dear", "financialRip": 31.0,
         "collectorAppeal": 70.0, "coreK": 0},
    ]
    result = pairs.within_set_winners(rows=rows, control=[40.0, 41.0],
                                      candidate=[43.0, 41.0])
    assert result["winnerChanges"] == 1
    assert result["helpfulDifferentiation"] == 1
    assert result["excessiveOverride"] == 0
    assert result["changes"][0]["coreKCandidate"] == 12


def test_a_set_with_one_product_is_not_examined():
    rows = [{"set": "S", "productName": "only", "financialRip": 30.0,
             "collectorAppeal": 70.0, "coreK": 3}]
    assert pairs.within_set_winners(rows=rows, control=[40.0],
                                    candidate=[41.0])["setsExamined"] == 0


# --------------------------------------------------------------------------
# Rank and tier handling
# --------------------------------------------------------------------------

def test_rank_influence_reports_nothing_for_an_unchanged_ranking():
    values = [50.0, 30.0, 90.0, 10.0, 70.0]
    labels = list("abcde")
    result = decisions.rank_influence(control=values, candidate=values, labels=labels)
    assert result["spearman"] == pytest.approx(1.0)
    assert result["maxMovement"] == 0.0
    assert result["pairwiseInversions"] == 0
    assert result["tierChanges"] == 0


def test_ranks_use_average_positions_for_ties():
    result = decisions.rank_influence(control=[10.0, 10.0, 10.0, 5.0],
                                      candidate=[10.0, 10.0, 10.0, 5.0],
                                      labels=list("abcd"))
    assert result["movedAtAll"] == 0


def test_pairwise_inversions_counts_a_full_reversal():
    values = [1.0, 2.0, 3.0, 4.0]
    result = decisions.rank_influence(control=values, candidate=values[::-1],
                                      labels=list("abcd"))
    assert result["pairwiseInversions"] == 6
    assert result["spearman"] == pytest.approx(-1.0)


def test_tiers_come_from_the_production_leader_curve():
    """Graded on the leader-normalized display score, not on the raw blend."""
    labels = ["leader", "mid", "tail"]
    grades = decisions.tiers([100.0, 60.0, 10.0], labels)
    assert grades["leader"] == "S"
    assert grades["tail"] != "S"
    assert set(grades) == set(labels)


def test_tier_movement_is_detected_when_the_curve_changes():
    labels = ["a", "b", "c", "d"]
    result = decisions.rank_influence(control=[100.0, 99.0, 98.0, 10.0],
                                      candidate=[100.0, 50.0, 40.0, 10.0],
                                      labels=labels)
    assert result["tierChanges"] > 0
    assert result["demotions"] >= 1


# --------------------------------------------------------------------------
# Scenario integrity
# --------------------------------------------------------------------------

def test_shock_scenarios_actually_change_core_k():
    """The Stage VI bug class, pinned against the real artifact.

    A freshness filter once excluded the whole eligible universe, so every shock
    reported a Core K of 0 and a response of exactly zero - which read as a
    finding rather than a defect. A card-price shock MUST move Core K, and must
    move it in the right direction: dearer cards clear a fixed floor more often.
    """
    import json
    from pathlib import Path

    artifact = Path("docs/research/chase_pillar_stage6_scenarios.json")
    if not artifact.exists():
        pytest.skip("scenario artifact not built")
    payload = json.loads(artifact.read_text(encoding="utf-8"))

    per_scenario = {}
    for observation in payload["observations"]:
        if observation.get("kind") != "shock":
            continue
        per_scenario.setdefault(observation["scenario"], {})[
            observation["sealedProductId"]] = int(observation["coreK"])

    base = per_scenario["base"]
    assert sum(base.values()) > 0, "base scenario has no Core anywhere"

    up = per_scenario["card+20%"]
    down = per_scenario["card-20%"]
    shared = sorted(set(base) & set(up) & set(down))
    assert len(shared) > 100

    assert sum(1 for p in shared if up[p] != base[p]) > 0
    assert sum(1 for p in shared if down[p] != base[p]) > 0
    # Directional: raising every card price cannot shrink a fixed-floor basket.
    assert all(up[p] >= base[p] for p in shared)
    assert all(down[p] <= base[p] for p in shared)
    # A product-cost rise raises the floor, so it cannot widen the basket.
    product_up = per_scenario["prod+20%"]
    assert all(product_up[p] <= base[p] for p in shared if p in product_up)
