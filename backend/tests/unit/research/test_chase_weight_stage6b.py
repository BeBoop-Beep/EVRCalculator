"""Stage VI-B closure invariants.

The Stage VI-A error these pin is a specific one: describing two Overall RIP
formulas as "equivalent" when only their Chase TERM matched. The tests below
make that confusion unrepresentable - a Candidate carries its own three weights
and its own transform, and nothing derives Financial as ``0.90 - chase``.
"""

from __future__ import annotations

import json
from pathlib import Path

import numpy as np
import pytest

from backend.research.chase_weight_stage6a import closure, scale


# --------------------------------------------------------------------------
# The equivalence claim, stated correctly
# --------------------------------------------------------------------------

def test_the_two_transforms_differ_by_exactly_a_factor_of_two():
    for k in range(0, 60):
        assert scale.approved_unclamped(k) == pytest.approx(
            2.0 * scale.rescaled_0_100(k), abs=1e-12)


def test_a_and_b_carry_identical_chase_contribution_strength():
    """0.06 * S and 0.03 * T are the same term. That much WAS equivalent."""
    for k in range(0, 40):
        assert (closure.CANDIDATE_A.chase * scale.rescaled_0_100(k)
                == pytest.approx(
                    closure.CANDIDATE_B.chase * scale.approved_unclamped(k), abs=1e-12))


def test_a_and_b_are_not_the_same_overall_formula():
    """The Stage VI-A error, pinned so it cannot be re-asserted."""
    assert closure.CANDIDATE_A.financial != closure.CANDIDATE_B.financial
    assert closure.CANDIDATE_B.financial - closure.CANDIDATE_A.financial == pytest.approx(0.03)


def test_b_minus_a_is_exactly_three_hundredths_of_financial():
    financial = [10.0, 28.97, 57.07, 0.0]
    collector = [70.0] * 4
    core_k = [0, 4, 14, 9]
    a = closure.CANDIDATE_A.score(financial=financial, collector=collector,
                                  core_k=core_k)
    b = closure.CANDIDATE_B.score(financial=financial, collector=collector,
                                  core_k=core_k)
    for i, f in enumerate(financial):
        assert b[i] - a[i] == pytest.approx(0.03 * f, abs=1e-12)


def test_analytic_difference_reports_the_closed_form():
    result = closure.analytic_difference(
        financial=[10.0, 50.0], left=closure.CANDIDATE_A, right=closure.CANDIDATE_B)
    assert result["closedForm"] is True
    assert result["financialCoefficient"] == pytest.approx(0.03)
    assert result["predicted"] == pytest.approx([0.3, 1.5])


def test_analytic_difference_refuses_when_chase_strength_differs():
    """A' has A's weights on B's scale, so its Chase term is twice A's."""
    result = closure.analytic_difference(
        financial=[10.0], left=closure.CANDIDATE_A, right=closure.CANDIDATE_A_PRIME)
    assert result["closedForm"] is False


# --------------------------------------------------------------------------
# Candidate construction
# --------------------------------------------------------------------------

def test_weights_must_sum_to_one():
    with pytest.raises(ValueError):
        closure.Candidate(key="bad", financial=0.87, collector=0.10, chase=0.06,
                          transform=scale.rescaled_0_100, transform_name="S")


@pytest.mark.parametrize("candidate", [closure.CANDIDATE_A, closure.CANDIDATE_B,
                                       closure.CANDIDATE_A_PRIME])
def test_every_declared_candidate_sums_to_one(candidate):
    assert (candidate.financial + candidate.collector
            + candidate.chase) == pytest.approx(1.0)


def test_candidate_a_is_the_production_specification():
    assert (closure.CANDIDATE_A.financial, closure.CANDIDATE_A.collector,
            closure.CANDIDATE_A.chase) == (0.84, 0.10, 0.06)
    assert closure.CANDIDATE_A.transform is scale.rescaled_0_100


def test_a_candidate_does_not_derive_financial_from_the_chase_weight():
    """The specific mechanism that produced the Stage VI-A confusion."""
    candidate = closure.Candidate(
        key="x", financial=0.60, collector=0.10, chase=0.30,
        transform=scale.rescaled_0_100, transform_name="S")
    assert candidate.financial == 0.60
    assert candidate.financial != 0.90 - candidate.chase


# --------------------------------------------------------------------------
# Transform semantics required by Phase 6
# --------------------------------------------------------------------------

@pytest.mark.parametrize("k,expected", [
    (0, 0.0), (1, 100.0 / 11), (2, 100.0 * 2 / 12), (10, 50.0), (14, 1400.0 / 24)])
def test_normalized_chase_semantics(k, expected):
    assert scale.rescaled_0_100(k) == pytest.approx(expected, abs=1e-12)


def test_normalized_chase_is_strictly_monotone_and_saturating():
    values = [scale.rescaled_0_100(k) for k in range(0, 400)]
    increments = [b - a for a, b in zip(values, values[1:])]
    assert all(b > a for a, b in zip(values, values[1:]))
    assert all(b < a for a, b in zip(increments, increments[1:]))


def test_normalized_chase_never_reaches_one_hundred_and_needs_no_clamp():
    assert scale.rescaled_0_100(10 ** 9) < 100.0
    assert max(scale.rescaled_0_100(k) for k in range(0, 10_000)) < 100.0


def test_distinct_core_k_stay_distinct_under_the_normalized_transform():
    """The clamp defect, inverted: no two different K may collide."""
    values = {scale.rescaled_0_100(k) for k in range(0, 200)}
    assert len(values) == 200
    # ...whereas the clamped old transform collapses everything above K = 10.
    clamped = {scale.approved_clamped(k) for k in range(11, 200)}
    assert clamped == {100.0}


# --------------------------------------------------------------------------
# The gate itself
# --------------------------------------------------------------------------

def _fake_base(**overrides):
    block = {
        "clearOverrides": 0, "maxGapOverturned": 7.0, "closeOverrideRate": 0.14,
        "shapley": {"financial_rip": 0.92, "collector_appeal": 0.0, "chase": 0.08},
        "spearman": 0.993, "top5Turnover": 0, "sameSetOverrides": 6,
    }
    block.update(overrides)
    return block


def test_all_five_gates_pass_on_a_healthy_block():
    result = closure.criteria(_fake_base(), [_fake_base()])
    assert result["flags"] == "YYYYY"
    assert result["allPassed"] is True


def test_c1_fails_on_a_single_clear_override_anywhere():
    assert closure.criteria(_fake_base(clearOverrides=1), [_fake_base()])["C1"]["passed"] is False
    assert closure.criteria(_fake_base(), [_fake_base(clearOverrides=1)])["C1"]["passed"] is False


def test_c1_fails_when_a_shock_pushes_the_gap_past_ten():
    result = closure.criteria(_fake_base(), [_fake_base(maxGapOverturned=10.4)])
    assert result["C1"]["passed"] is False
    assert result["C1"]["margin"] < 0


def test_c2_fails_just_below_the_threshold():
    assert closure.criteria(_fake_base(closeOverrideRate=0.0999), [])["C2"]["passed"] is False
    assert closure.criteria(_fake_base(closeOverrideRate=0.10), [])["C2"]["passed"] is True


def test_c3_fails_when_chase_becomes_co_primary():
    loud = {"financial_rip": 0.78, "collector_appeal": 0.0, "chase": 0.22}
    assert closure.criteria(_fake_base(shapley=loud), [])["C3"]["passed"] is False


def test_c4_fails_on_rank_discontinuity():
    assert closure.criteria(_fake_base(spearman=0.97), [])["C4"]["passed"] is False
    assert closure.criteria(_fake_base(top5Turnover=2), [])["C4"]["passed"] is False


def test_c5_fails_without_same_set_reversals():
    assert closure.criteria(_fake_base(sameSetOverrides=0), [])["C5"]["passed"] is False


def test_margins_are_reported_and_signed():
    result = closure.criteria(_fake_base(), [_fake_base()])
    assert result["C1"]["margin"] == pytest.approx(3.0)
    assert result["C2"]["margin"] == pytest.approx(0.04)


# --------------------------------------------------------------------------
# End to end, against the real cohort
# --------------------------------------------------------------------------

def _dataset():
    path = Path("docs/research/chase_pillar_stage6_dataset.json")
    if not path.exists():
        pytest.skip("Stage VI dataset not built")
    return json.loads(path.read_text(encoding="utf-8"))


def test_candidate_a_passes_all_five_gates_on_the_real_cohort():
    """The closure test itself, recomputed - never inferred from Candidate B."""
    payload = _dataset()
    rows = payload["rows"]
    control = [r["overallControl"] for r in rows]
    base = closure.evaluate(closure.CANDIDATE_A, rows=rows, control=control)

    scenarios_path = Path("docs/research/chase_pillar_stage6_scenarios.json")
    shocked = []
    if scenarios_path.exists():
        scenarios = json.loads(scenarios_path.read_text(encoding="utf-8"))
        index = {r["sealedProductId"]: i for i, r in enumerate(rows)}
        per_scenario = {}
        for observation in scenarios["observations"]:
            if observation.get("kind") != "shock":
                continue
            position = index.get(observation["sealedProductId"])
            if position is not None:
                per_scenario.setdefault(observation["scenario"], {})[position] = int(
                    observation["coreK"])
        for key in closure.C1_SHOCK_KEYS:
            entries = per_scenario.get(key)
            if entries:
                shocked.append(closure.evaluate(
                    closure.CANDIDATE_A, rows=rows, control=control,
                    positions=sorted(entries), core_k=entries))
        assert len(shocked) == 4

    result = closure.criteria(base, shocked)
    assert result["allPassed"] is True, result


def test_the_observed_a_to_b_difference_matches_the_identity_on_real_data():
    payload = _dataset()
    rows = payload["rows"]
    financial = [r["financialRip"] for r in rows]
    collector = [r["collectorAppeal"] for r in rows]
    core_k = [r["coreK"] for r in rows]
    a = closure.CANDIDATE_A.score(financial=financial, collector=collector,
                                  core_k=core_k)
    b = closure.CANDIDATE_B.score(financial=financial, collector=collector,
                                  core_k=core_k)
    observed = np.asarray([b[i] - a[i] for i in range(len(rows))])
    predicted = 0.03 * np.asarray(financial, dtype=float)
    assert float(np.max(np.abs(observed - predicted))) < 1e-12
    # And the difference is strictly positive: B flatters every product.
    assert observed.min() > 0.0


def test_candidate_a_changes_no_same_set_winner_versus_control():
    """Stage VI-A's narrowed claim, re-verified on the recommended formula."""
    payload = _dataset()
    rows = payload["rows"]
    control = [r["overallControl"] for r in rows]
    base = closure.evaluate(closure.CANDIDATE_A, rows=rows, control=control)
    assert base["winnerChanges"] == 0
    assert base["sameSetOverrides"] > 0
