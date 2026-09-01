"""Stage VII apparatus invariants.

The specific self-deception these guard against: raising Collector necessarily
lowers Financial, so ranking movement can be credited to Collector when it was
really caused by Financial losing weight. Several tests below would pass for an
implementation that made exactly that mistake, and fail for the correct one.
"""

from __future__ import annotations

import hashlib
import json
from pathlib import Path

import numpy as np
import pytest

from backend.research.chase_weight_stage6a import closure, scale
from backend.research.collector_weight_stage7 import sweep

PREREG = Path("docs/research/COLLECTOR_WEIGHT_STAGE7_PREREGISTRATION.json")

#: The hash recorded when the preregistration was locked, before any candidate
#: outcome existed. A change to the file is a change to the study's contract.
PREREG_SHA256 = "73190a86ab0a4c9d21dc3414d1f7b457d67561592ce141014a5248e713745274"


# --------------------------------------------------------------------------
# Preregistration integrity
# --------------------------------------------------------------------------

def test_the_preregistration_has_not_mutated():
    assert PREREG.exists()
    assert hashlib.sha256(PREREG.read_bytes()).hexdigest() == PREREG_SHA256


def test_the_preregistered_candidate_set_matches_the_code():
    payload = json.loads(PREREG.read_text(encoding="utf-8"))
    selectable = {round(c["collector"], 4) for c in payload["selectableCandidates"]}
    diagnostic = {round(c["collector"], 4) for c in payload["diagnosticCandidates"]}
    assert selectable == {round(c, 4) for c in sweep.SELECTABLE}
    assert diagnostic == {round(c, 4) for c in sweep.DIAGNOSTIC}


def test_the_selection_ceiling_excludes_the_diagnostic_weights():
    payload = json.loads(PREREG.read_text(encoding="utf-8"))
    assert payload["selectionCeiling"] == 0.13
    for point in sweep.grid():
        if point.collector > 0.13:
            assert point.selectable is False


# --------------------------------------------------------------------------
# Weight algebra
# --------------------------------------------------------------------------

@pytest.mark.parametrize("collector", list(sweep.SELECTABLE) + list(sweep.DIAGNOSTIC))
def test_every_grid_point_sums_to_exactly_one(collector):
    point = sweep.WeightPoint(collector=collector, selectable=False)
    assert point.financial + point.collector + point.chase == pytest.approx(1.0, abs=1e-12)


@pytest.mark.parametrize("collector", list(sweep.SELECTABLE) + list(sweep.DIAGNOSTIC))
def test_chase_is_pinned_at_six_percent_throughout(collector):
    assert sweep.WeightPoint(collector=collector, selectable=False).chase == 0.06


@pytest.mark.parametrize("collector", list(sweep.SELECTABLE) + list(sweep.DIAGNOSTIC))
def test_financial_is_exactly_the_budget_minus_collector(collector):
    point = sweep.WeightPoint(collector=collector, selectable=False)
    assert point.financial == pytest.approx(0.94 - collector, abs=1e-12)


def test_a_point_that_moves_chase_is_refused():
    class Rogue(sweep.WeightPoint):
        @property
        def chase(self):
            return 0.05
    with pytest.raises(ValueError):
        Rogue(collector=0.10, selectable=True)


def test_control_point_reproduces_stage_vi_b_candidate_a():
    """84/10/6 must be bit-identical to the validated Stage VI-B formula."""
    financial = [10.0, 28.97, 57.07, 41.2]
    collector = [49.07, 80.82, 99.09, 72.0]
    core_k = [0, 4, 14, 7]
    point = sweep.WeightPoint(collector=0.10, selectable=True)
    ours = sweep.score(point, financial=financial, collector=collector,
                       chase=[scale.rescaled_0_100(k) for k in core_k])
    theirs = closure.CANDIDATE_A.score(financial=financial, collector=collector,
                                       core_k=core_k)
    assert ours == pytest.approx(theirs, abs=1e-12)


def test_the_baseline_is_financial_plus_chase_only():
    baseline = sweep.baseline_financial_chase(financial=[50.0], chase=[30.0])
    assert baseline[0] == pytest.approx(0.94 * 50.0 + 0.06 * 30.0)


# --------------------------------------------------------------------------
# Within-set structure
# --------------------------------------------------------------------------

def _rows(collectors, sets, financials=None, ks=None):
    n = len(collectors)
    financials = financials or [30.0] * n
    ks = ks or [4] * n
    return [{"set": sets[i], "productName": "p%d" % i, "family": "f",
             "collectorAppeal": collectors[i], "financialRip": financials[i],
             "coreK": ks[i], "chaseNormalized": scale.rescaled_0_100(ks[i])}
            for i in range(n)]


def test_a_set_constant_column_is_reported_as_set_constant():
    rows = _rows([80.0, 80.0, 70.0, 70.0], ["A", "A", "B", "B"])
    result = sweep.within_set_structure(rows, "collectorAppeal")
    assert result["setsWithVariation"] == 0
    assert result["verdict"] == "exactly constant within every set"


def test_a_product_specific_column_is_reported_as_product_specific():
    rows = _rows([80.0, 81.0, 70.0, 71.0], ["A", "A", "B", "B"])
    result = sweep.within_set_structure(rows, "collectorAppeal")
    assert result["setsWithVariation"] == 2
    assert result["verdict"] == "genuinely product-specific"


# --------------------------------------------------------------------------
# The direct / reallocation decomposition
# --------------------------------------------------------------------------

LOW = sweep.WeightPoint(collector=0.10, selectable=True)
HIGH = sweep.WeightPoint(collector=0.13, selectable=True)


def test_equal_collector_means_one_hundred_percent_reallocation():
    """The hard rule. A same-set pair can never be Collector-caused."""
    block = sweep.decompose_pair(financial=(40.0, 30.0), collector=(80.0, 80.0),
                                 chase=(50.0, 20.0), low=LOW, high=HIGH)
    assert block["collectorIdentical"] is True
    assert block["directCollector"] == pytest.approx(0.0, abs=1e-12)
    assert block["reallocation"] == pytest.approx(block["change"], abs=1e-12)


def test_the_decomposition_sums_to_the_observed_change():
    block = sweep.decompose_pair(financial=(40.0, 30.0), collector=(60.0, 90.0),
                                 chase=(50.0, 20.0), low=LOW, high=HIGH)
    assert (block["directCollector"] + block["reallocation"]
            == pytest.approx(block["change"], abs=1e-12))


def test_the_direct_term_is_delta_times_the_collector_gap():
    block = sweep.decompose_pair(financial=(0.0, 0.0), collector=(90.0, 60.0),
                                 chase=(0.0, 0.0), low=LOW, high=HIGH)
    assert block["directCollector"] == pytest.approx(0.03 * 30.0, abs=1e-12)


def test_same_set_pairs_never_reverse_when_collector_is_set_constant():
    rows = _rows([80.0, 80.0], ["A", "A"], financials=[30.0, 31.0], ks=[14, 0])
    block = sweep.classify_reversals(rows=rows, low=LOW, high=HIGH)
    assert block["sameSetReversals"] == 0
    assert block["collectorCaused"] == 0


def test_a_reversal_driven_by_financial_losing_weight_is_not_credited_to_collector():
    """The generous-attribution trap.

    The two products differ slightly on Collector, but the Financial gap is far
    larger, so the reallocation term dominates. An implementation that counted
    any differing-Collector reversal as Collector-caused would fail here.
    """
    rows = _rows([80.0, 79.0], ["A", "B"], financials=[31.0, 30.0], ks=[0, 14])
    block = sweep.classify_reversals(rows=rows, low=LOW, high=HIGH)
    assert block["collectorCaused"] == 0
    if block["totalReversals"]:
        assert block["reallocationDominant"] == block["totalReversals"]


def test_a_reversal_driven_by_a_large_collector_gap_is_credited_to_collector():
    # A is 45 Collector points ahead but 6 Financial points behind, which is
    # exactly the regime where the extra Collector weight flips the pair.
    rows = _rows([95.0, 50.0], ["A", "B"], financials=[30.0, 36.0], ks=[4, 4])
    block = sweep.classify_reversals(rows=rows, low=LOW, high=HIGH)
    assert block["collectorCaused"] == 1
    assert block["reallocationDominant"] == 0
    assert block["crossSetReversals"] == 1


# --------------------------------------------------------------------------
# Population schemes
# --------------------------------------------------------------------------

def test_set_balanced_weights_give_every_set_equal_total_weight():
    weights = sweep.set_balanced_weights(["A", "A", "A", "B"])
    assert weights.tolist() == pytest.approx([1 / 3, 1 / 3, 1 / 3, 1.0])
    assert weights[:3].sum() == pytest.approx(weights[3])


def test_uniform_weights_reproduce_the_unweighted_moments():
    values = [1.0, 4.0, 9.0, 16.0]
    mean, variance = sweep.weighted_moments(values, np.ones(4))
    assert mean == pytest.approx(np.mean(values))
    assert variance == pytest.approx(np.var(values))


def test_covariance_shares_reconstruct_the_total_variance():
    rng = np.random.default_rng(7)
    components = {"financial_rip": list(rng.normal(30, 8, 80)),
                  "collector_appeal": list(rng.normal(80, 11, 80)),
                  "chase": list(rng.normal(25, 14, 80))}
    weight_set = {"financial_rip": 0.84, "collector_appeal": 0.10, "chase": 0.06}
    for weights in (np.ones(80), sweep.set_balanced_weights(["s%d" % (i % 9) for i in range(80)])):
        shares = sweep.weighted_covariance_shares(components, weight_set, weights)
        assert sum(shares.values()) == pytest.approx(1.0, abs=1e-9)


# --------------------------------------------------------------------------
# Inherited guardrails
# --------------------------------------------------------------------------

def test_guardrail_thresholds_are_read_from_production_config_not_restated():
    from backend.desirability.scoring_config import OVERALL_RIP_PRODUCTION_GUARDRAILS

    block = sweep.inherited_guardrails(baseline=[3.0, 2.0, 1.0], candidate=[3.0, 2.0, 1.0],
                                       labels=["a", "b", "c"])
    assert block["thresholds"] == dict(OVERALL_RIP_PRODUCTION_GUARDRAILS)


def test_an_identical_ranking_passes_every_guardrail():
    values = [9.0, 5.0, 3.0, 1.0, 7.0]
    block = sweep.inherited_guardrails(baseline=values, candidate=values,
                                       labels=list("abcde"))
    assert block["spearman"] == pytest.approx(1.0)
    assert block["meanAbsoluteRankMovement"] == 0.0
    assert block["shareMoving5Plus"] == 0.0
    assert block["rbo"] == pytest.approx(1.0, abs=1e-6)


def test_the_movement_gates_are_reported_in_both_raw_and_cohort_scaled_form():
    """They are absolute rank counts calibrated on a 21-set cohort."""
    values = list(range(40))
    block = sweep.inherited_guardrails(baseline=values, candidate=values[::-1],
                                       labels=[str(i) for i in values])
    assert block["cohortSize"] == 40
    assert block["scaledRankStep"] > 5
    assert "meanMovementAsShareOfCohort" in block
    assert block["historicalMeanThresholdAsShareOfCohort"] == pytest.approx(1.5 / 21.0)


def test_rbo_is_one_for_identical_orders_and_lower_for_a_reversal():
    order = ["a", "b", "c", "d", "e"]
    assert sweep.rbo(order, order) == pytest.approx(1.0, abs=1e-6)
    assert sweep.rbo(order, order[::-1]) < 0.6


# --------------------------------------------------------------------------
# End to end against the real cohort
# --------------------------------------------------------------------------

def _dataset():
    path = Path("docs/research/chase_pillar_stage6_dataset.json")
    if not path.exists():
        pytest.skip("Stage VI dataset not built")
    payload = json.loads(path.read_text(encoding="utf-8"))
    for row in payload["rows"]:
        row["chaseNormalized"] = scale.rescaled_0_100(row["coreK"])
    return payload


def test_collector_appeal_is_exactly_set_constant_on_the_real_cohort():
    rows = _dataset()["rows"]
    result = sweep.within_set_structure(rows, "collectorAppeal")
    assert result["setsWithVariation"] == 0
    assert len({r["collectorAppeal"] for r in rows}) == 21


def test_control_reproduces_the_stage_vi_b_score_on_the_real_cohort():
    rows = _dataset()["rows"]
    point = sweep.WeightPoint(collector=0.10, selectable=True)
    ours = sweep.score(point, financial=[r["financialRip"] for r in rows],
                       collector=[r["collectorAppeal"] for r in rows],
                       chase=[r["chaseNormalized"] for r in rows])
    theirs = closure.CANDIDATE_A.score(
        financial=[r["financialRip"] for r in rows],
        collector=[r["collectorAppeal"] for r in rows],
        core_k=[r["coreK"] for r in rows])
    assert max(abs(a - b) for a, b in zip(ours, theirs)) < 1e-12


def test_no_same_set_reversal_occurs_anywhere_in_the_real_sweep():
    rows = _dataset()["rows"]
    for low_c, high_c in ((0.10, 0.11), (0.11, 0.12), (0.12, 0.13), (0.10, 0.13)):
        block = sweep.classify_reversals(
            rows=rows,
            low=sweep.WeightPoint(collector=low_c, selectable=True),
            high=sweep.WeightPoint(collector=high_c, selectable=True))
        assert block["sameSetReversals"] == 0, (low_c, high_c)


def test_every_selectable_candidate_passes_all_five_stage_vi_b_chase_gates():
    """Raising Collector must not break the validated tertiary Chase behaviour."""
    payload = _dataset()
    rows = payload["rows"]
    financial = [r["financialRip"] for r in rows]
    collector = [r["collectorAppeal"] for r in rows]

    scenarios_path = Path("docs/research/chase_pillar_stage6_scenarios.json")
    shocks = {}
    if scenarios_path.exists():
        scenarios = json.loads(scenarios_path.read_text(encoding="utf-8"))
        index = {r["sealedProductId"]: i for i, r in enumerate(rows)}
        for observation in scenarios["observations"]:
            if observation.get("kind") != "shock":
                continue
            position = index.get(observation["sealedProductId"])
            if position is not None:
                shocks.setdefault(observation["scenario"], {})[position] = int(
                    observation["coreK"])

    for point in sweep.grid():
        if not point.selectable:
            continue
        candidate = closure.Candidate(
            key=point.key, financial=point.financial, collector=point.collector,
            chase=point.chase, transform=scale.rescaled_0_100,
            transform_name="100K/(K+10)")
        chase_free = [(1.0 - point.collector) * f + point.collector * c
                      for f, c in zip(financial, collector)]
        base = closure.evaluate(candidate, rows=rows, control=chase_free)
        shocked = []
        for key in closure.C1_SHOCK_KEYS:
            entries = shocks.get(key)
            if entries:
                shocked.append(closure.evaluate(
                    candidate, rows=rows, control=chase_free,
                    positions=sorted(entries), core_k=entries))
        gate = closure.criteria(base, shocked)
        assert gate["allPassed"] is True, (point.key, gate["flags"])
