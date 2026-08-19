"""Production Financial RIP V4 must reproduce the frozen P95_ONLY_25 candidate.

The frozen research candidate was not a separate engine: it scored a product as
the V3 component scores under the V3 weight vector, with Realistic Upside
replaced by ``normalize_metric("p95_threshold_ratio", p95Ratio)``. So parity is
an identity to prove, not a tolerance to accept - and proving it on the engine
covers every outcome vector rather than only the 137 SKUs in the August 17
cohort.

The frozen artifact diagnostics are also asserted, so the numbers the promotion
rests on are checked against the file rather than restated from memory.
"""

from __future__ import annotations

import pytest

from backend.calculations.evr.financial_rip_v4_config import (
    FINANCIAL_RIP_V4_RESEARCH_AUTHORITY_DATE,
    FINANCIAL_RIP_V4_RESEARCH_CANDIDATE_ID,
    FINANCIAL_RIP_V4_WEIGHTS,
)
from backend.scripts.research_financial_rip_final_validation import CANDIDATES
from backend.scripts.research_financial_rip_v4_parity import (
    EXPECTED_DIAGNOSTICS,
    check_engine_parity,
    main,
    read_frozen_diagnostics,
)


@pytest.fixture(scope="module")
def parity():
    return check_engine_parity()


def test_production_v4_reproduces_the_frozen_candidate(parity):
    assert parity["reproduced"] is True, parity["cases"]


def test_the_exact_identities_hold_on_every_case(parity):
    assert parity["exactIdentitiesHold"] is True
    for case in parity["cases"]:
        assert case["realisticUpsideIsP95Only"] is True
        assert case["otherComponentsUnchangedFromV3"] is True
        assert case["v3ScoreVersionDistinct"] is True


def test_the_residual_is_only_publication_rounding(parity):
    """4dp component rounding plus one 4dp headline rounding: 1e-4, no more."""
    assert parity["roundingBudget"] == 1e-4
    assert parity["worstAbsoluteDifference"] <= parity["roundingBudget"]


def test_production_weights_equal_the_candidate_weights():
    candidate = CANDIDATES[FINANCIAL_RIP_V4_RESEARCH_CANDIDATE_ID]
    assert dict(FINANCIAL_RIP_V4_WEIGHTS) == dict(candidate["weights"])
    assert candidate["definition"] == "P95_THRESHOLD_ONLY"
    assert candidate["realisticWeight"] == 0.25


def test_the_rejected_20_percent_candidate_was_not_implemented():
    rejected = CANDIDATES["P95_ONLY_20"]
    assert dict(FINANCIAL_RIP_V4_WEIGHTS) != dict(rejected["weights"])
    assert FINANCIAL_RIP_V4_WEIGHTS["realistic_upside"] != rejected["realisticWeight"]


def test_the_engine_and_the_projection_agree_on_every_case(parity):
    assert all(case["engineMatchesProjection"] for case in parity["cases"])


def test_multiple_distribution_shapes_are_covered(parity):
    shapes = {case["vector"] for case in parity["cases"]}
    assert shapes == {
        "lognormal_booster",
        "chase_concentrated",
        "flat",
        "cheap_high_variance",
    }


# ---------------------------------------------------------------------------
# The frozen artifact
# ---------------------------------------------------------------------------

@pytest.fixture(scope="module")
def frozen():
    return read_frozen_diagnostics()


def test_the_frozen_artifact_carries_the_expected_diagnostics(frozen):
    if not frozen.get("artifactPresent"):
        pytest.skip("frozen research artifact is not present in this checkout")
    assert frozen["matchesExpected"] is True, frozen["mismatches"]
    assert frozen["observed"]["layer1InversionsAt5Pct"] == 8
    assert frozen["observed"]["layer1InversionsAt2Pct"] == 3
    assert frozen["observed"]["layer2Inversions"] == 0
    assert frozen["observed"]["layer3Inversions"] == 0
    assert frozen["observed"]["layer4Inversions"] == 0
    assert frozen["observed"]["comparisonsAt5Pct"] == 5796


def test_no_unexpected_top_strategy_changes(frozen):
    if not frozen.get("artifactPresent"):
        pytest.skip("frozen research artifact is not present in this checkout")
    assert frozen["observed"]["topStrategyChanges"] == 0


def test_pack_and_set_ranking_structure_is_preserved(frozen):
    if not frozen.get("artifactPresent"):
        pytest.skip("frozen research artifact is not present in this checkout")
    for state in frozen["states"]:
        assert state["packSpearman"] >= 0.98
        assert state["packMaxRankMovement"] <= 2
        assert state["packSetsMovingAtLeast3"] == []


def test_the_authority_is_the_august_17_development_state(frozen):
    if not frozen.get("artifactPresent"):
        pytest.skip("frozen research artifact is not present in this checkout")
    assert FINANCIAL_RIP_V4_RESEARCH_AUTHORITY_DATE == "2026-08-17"
    assert frozen["stateDates"] == ["2026-08-17"]


def test_the_absence_of_temporal_validation_is_recorded_not_implied(frozen):
    """The decision record forbids rewriting this history. Assert it stays stated."""
    if not frozen.get("artifactPresent"):
        pytest.skip("frozen research artifact is not present in this checkout")
    assert frozen["temporalValidation"] == (
        "none_independent_temporal_validation_at_promotion"
    )
    assert frozen["reconstructableDistinctStates"] == 1


def test_the_expected_diagnostics_table_matches_the_decision_record():
    assert EXPECTED_DIAGNOSTICS["layer1InversionsAt5Pct"] == 8
    assert EXPECTED_DIAGNOSTICS["layer1InversionsAt2Pct"] == 3
    assert EXPECTED_DIAGNOSTICS["comparisonsAt5Pct"] == 5796


def test_the_verifier_exits_zero():
    assert main([]) == 0
