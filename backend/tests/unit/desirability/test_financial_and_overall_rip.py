"""Financial RIP (60/25/15) and Overall RIP (0.90 financial + 0.10 CA7).

Unit-level proofs for the two shipping formulas, independent of the service.
The capped additive-adjustment model (Overall RIP v3) has been retired; these
tests pin the weighted blend and prove no authoritative cap survives.
"""

from __future__ import annotations

import pytest

from backend.desirability.scoring_config import (
    FINANCIAL_RIP_WEIGHTS,
    OVERALL_RIP_EFFECTIVE_WEIGHTS,
    OVERALL_RIP_V4_VERSION,
    OVERALL_RIP_WEIGHTS,
)
from backend.desirability.weighted_rip import (
    compute_financial_rip,
    compute_overall_rip,
)

PILLARS = {"profit": 24.51, "safety": 21.40, "stability": 15.08}
ASCENDED_FINANCIAL = 0.60 * 24.51 + 0.25 * 21.40 + 0.15 * 15.08  # ~22.32
# A representative CA7 Opening Desirability score (0-100), the same scale the
# Collector Appeal service publishes under collectorAppeal.score.
CA7_SCORE = 78.0


# ---------------------------------------------------------------------------
# Financial RIP
# ---------------------------------------------------------------------------

def test_financial_rip_weights_are_exactly_60_25_15():
    assert FINANCIAL_RIP_WEIGHTS == {"profit": 0.60, "safety": 0.25, "stability": 0.15}
    assert sum(FINANCIAL_RIP_WEIGHTS.values()) == pytest.approx(1.0)


def test_financial_rip_matches_the_hand_calculation():
    """Validation check against the production pillar values for Ascended Heroes."""
    result = compute_financial_rip(PILLARS)
    assert result["score"] == pytest.approx(ASCENDED_FINANCIAL, abs=1e-4)
    assert result["score"] == pytest.approx(22.32, abs=0.01)


def test_financial_rip_contributions_sum_to_the_score():
    result = compute_financial_rip(PILLARS)
    total = sum(component["contribution"] for component in result["components"].values())
    assert total == pytest.approx(result["score"], abs=1e-3)


def test_financial_rip_published_weights_are_the_applied_weights():
    result = compute_financial_rip(PILLARS)
    for pillar, weight in FINANCIAL_RIP_WEIGHTS.items():
        component = result["components"][pillar]
        assert component["weight"] == pytest.approx(weight)
        assert component["contribution"] == pytest.approx(component["score"] * weight, abs=1e-4)


@pytest.mark.parametrize("missing", ["profit", "safety", "stability"])
def test_financial_rip_unavailable_when_any_pillar_missing(missing):
    pillars = dict(PILLARS)
    pillars[missing] = None
    result = compute_financial_rip(pillars)
    assert result["score"] is None
    assert result["missingPillars"] == [missing]
    assert result["rankable"] is False


def test_financial_rip_does_not_renormalize_surviving_pillars():
    """Renormalizing would emit a comparable-looking score from fewer pillars."""
    result = compute_financial_rip({"profit": 90.0, "safety": 90.0, "stability": None})
    assert result["score"] is None


def test_financial_rip_ignores_a_desirability_input():
    """Desirability is not a pillar and cannot be smuggled in as one."""
    with_desirability = compute_financial_rip({**PILLARS, "desirability": 99.0})
    without = compute_financial_rip(PILLARS)
    assert with_desirability["score"] == pytest.approx(without["score"])
    assert "desirability" not in with_desirability["components"]


# ---------------------------------------------------------------------------
# Overall RIP = 0.90 * Financial RIP + 0.10 * CA7 Opening Desirability
# ---------------------------------------------------------------------------

def test_overall_rip_weights_are_90_10():
    assert OVERALL_RIP_WEIGHTS == {"financial_rip": 0.90, "opening_desirability": 0.10}
    assert sum(OVERALL_RIP_WEIGHTS.values()) == pytest.approx(1.0)


def test_overall_rip_effective_weights_are_54_225_135_10():
    assert OVERALL_RIP_EFFECTIVE_WEIGHTS["profit"] == pytest.approx(0.54)
    assert OVERALL_RIP_EFFECTIVE_WEIGHTS["safety"] == pytest.approx(0.225)
    assert OVERALL_RIP_EFFECTIVE_WEIGHTS["stability"] == pytest.approx(0.135)
    assert OVERALL_RIP_EFFECTIVE_WEIGHTS["opening_desirability"] == pytest.approx(0.10)
    assert sum(OVERALL_RIP_EFFECTIVE_WEIGHTS.values()) == pytest.approx(1.0)


def test_overall_rip_is_exactly_90_financial_plus_10_ca7():
    result = compute_overall_rip(PILLARS, CA7_SCORE)
    expected = 0.90 * ASCENDED_FINANCIAL + 0.10 * CA7_SCORE
    assert result["score"] == pytest.approx(expected, abs=1e-4)
    assert result["version"] == OVERALL_RIP_V4_VERSION


def test_overall_rip_contributions_sum_to_the_score():
    result = compute_overall_rip(PILLARS, CA7_SCORE)
    components = result["components"]
    total = (
        components["financialRip"]["contribution"]
        + components["openingDesirability"]["contribution"]
    )
    assert total == pytest.approx(result["score"], abs=1e-3)


def test_overall_rip_has_no_cap_and_can_move_more_than_5_points():
    """The capped +/-3 adjustment is gone; a high CA7 moves Overall well past 5."""
    financial = compute_financial_rip(PILLARS)["score"]
    result = compute_overall_rip(PILLARS, 100.0)
    # 0.9*F + 0.1*100 - F = 0.1*(100 - F); with F ~= 22.3 that is ~7.8 points.
    assert result["score"] - financial > 5.0
    assert "desirabilityAdjustment" not in result
    assert "cap" not in result
    assert "adjustmentCap" not in result


def test_overall_rip_desirability_can_overtake_a_financial_gap():
    """Intentional under the blend: both scores are published side by side."""
    behind = compute_overall_rip({"profit": 50.0, "safety": 50.0, "stability": 50.0}, 100.0)
    ahead = compute_overall_rip({"profit": 60.0, "safety": 60.0, "stability": 60.0}, 0.0)
    # Financial: behind = 50, ahead = 60. Overall: behind = 55, ahead = 54.
    assert behind["financialRip"]["score"] == pytest.approx(50.0)
    assert ahead["financialRip"]["score"] == pytest.approx(60.0)
    assert behind["score"] == pytest.approx(55.0)
    assert ahead["score"] == pytest.approx(54.0)
    assert behind["score"] > ahead["score"]


def test_overall_rip_requires_ca7():
    result = compute_overall_rip(PILLARS, None)
    assert result["score"] is None
    assert result["missingInputs"] == ["opening_desirability_ca7"]
    assert result["rankable"] is False


def test_overall_rip_does_not_fall_back_to_universal_when_ca7_missing():
    """CA7 absent -> Overall unavailable, but Financial RIP stays available."""
    result = compute_overall_rip(PILLARS, None)
    assert result["score"] is None
    assert result["financialRip"]["score"] == pytest.approx(ASCENDED_FINANCIAL, abs=1e-4)


def test_overall_rip_requires_financial_rip():
    result = compute_overall_rip({"profit": 90.0, "safety": None, "stability": 70.0}, CA7_SCORE)
    assert result["score"] is None
    assert "safety" in result["missingInputs"]


def test_overall_rip_is_clamped_to_0_100():
    high = compute_overall_rip({"profit": 100.0, "safety": 100.0, "stability": 100.0}, 100.0)
    assert high["score"] == 100.0
    low = compute_overall_rip({"profit": 0.0, "safety": 0.0, "stability": 0.0}, 0.0)
    assert low["score"] == 0.0


def test_overall_rip_does_not_double_count_universal_desirability():
    """Universal Set Desirability enters ONLY through CA7, so a separate high
    universal score cannot influence Overall RIP - only the CA7 input does."""
    ca7_low = compute_overall_rip(PILLARS, 10.0)
    ca7_high = compute_overall_rip(PILLARS, 90.0)
    # The ONLY desirability lever is the CA7 argument. Nothing else is accepted.
    assert ca7_high["score"] - ca7_low["score"] == pytest.approx(0.10 * (90.0 - 10.0), abs=1e-4)
