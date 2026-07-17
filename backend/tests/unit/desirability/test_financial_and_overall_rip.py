"""Financial RIP (60/25/15) and Overall RIP (financial + bounded adjustment).

Unit-level proofs for the two shipping formulas, independent of the service.
"""

from __future__ import annotations

import pytest

from backend.desirability.scoring_config import (
    DESIRABILITY_ADJUSTMENT_BASELINE,
    DESIRABILITY_ADJUSTMENT_CAP,
    DESIRABILITY_ADJUSTMENT_DIVISOR,
    FINANCIAL_RIP_WEIGHTS,
)
from backend.desirability.weighted_rip import (
    compute_desirability_adjustment,
    compute_financial_rip,
    compute_overall_rip,
)

PILLARS = {"profit": 24.51, "safety": 21.40, "stability": 15.08}
ASCENDED_FINANCIAL = 0.60 * 24.51 + 0.25 * 21.40 + 0.15 * 15.08  # ~22.32


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
# Desirability adjustment
# ---------------------------------------------------------------------------

def test_adjustment_is_zero_at_the_baseline():
    assert compute_desirability_adjustment(DESIRABILITY_ADJUSTMENT_BASELINE)["adjustment"] == 0.0


def test_adjustment_is_desirability_minus_50_over_10():
    result = compute_desirability_adjustment(74.0, cap=5.0)
    assert result["rawAdjustment"] == pytest.approx((74.0 - 50.0) / 10.0)
    assert result["adjustment"] == pytest.approx(2.4)
    assert result["clamped"] is False


@pytest.mark.parametrize(
    "score, cap, expected",
    [
        (100.0, 3.0, 3.0),    # raw +5.0 -> clamped to +3
        (100.0, 5.0, 5.0),    # raw +5.0 -> exactly at cap
        (0.0, 3.0, -3.0),     # raw -5.0 -> clamped to -3
        (0.0, 5.0, -5.0),     # raw -5.0 -> exactly at cap
        (80.0, 3.0, 3.0),     # raw +3.0 -> at cap
        (80.0, 5.0, 3.0),     # raw +3.0 -> inside cap 5
        (95.4809, 3.0, 3.0),  # Ascended Heroes clamps under cap 3
        (95.4809, 5.0, 4.54809),
    ],
)
def test_cap_3_and_cap_5_clamp_correctly(score, cap, expected):
    result = compute_desirability_adjustment(score, cap=cap)
    assert result["adjustment"] == pytest.approx(expected, abs=1e-4)
    assert abs(result["adjustment"]) <= cap + 1e-9


def test_clamped_flag_distinguishes_a_capped_set_from_one_inside_the_cap():
    assert compute_desirability_adjustment(100.0, cap=3.0)["clamped"] is True
    assert compute_desirability_adjustment(74.0, cap=3.0)["clamped"] is False


def test_adjustment_divisor_and_baseline_are_config_driven():
    assert DESIRABILITY_ADJUSTMENT_BASELINE == 50.0
    assert DESIRABILITY_ADJUSTMENT_DIVISOR == 10.0


def test_missing_desirability_yields_no_adjustment():
    assert compute_desirability_adjustment(None)["adjustment"] is None


# ---------------------------------------------------------------------------
# Overall RIP
# ---------------------------------------------------------------------------

def test_overall_rip_is_financial_plus_capped_adjustment():
    result = compute_overall_rip(PILLARS, 95.4809, cap=5.0)
    assert result["score"] == pytest.approx(ASCENDED_FINANCIAL + 4.54809, abs=1e-3)


def test_overall_rip_does_not_require_ca7():
    """No CA7 is passed anywhere; a score is still produced."""
    result = compute_overall_rip(PILLARS, 95.4809)
    assert result["score"] is not None
    assert result["rankable"] is True
    assert result.get("status") != "incomplete_missing_desirability"


def test_overall_rip_requires_financial_rip():
    result = compute_overall_rip({"profit": 90.0, "safety": None, "stability": 70.0}, 95.0)
    assert result["score"] is None
    assert "safety" in result["missingInputs"]


def test_overall_rip_requires_universal_desirability():
    result = compute_overall_rip(PILLARS, None)
    assert result["score"] is None
    assert result["missingInputs"] == ["universal_set_desirability"]


def test_overall_rip_is_clamped_to_0_100():
    high = compute_overall_rip({"profit": 100.0, "safety": 100.0, "stability": 100.0}, 100.0)
    assert high["score"] == 100.0
    low = compute_overall_rip({"profit": 0.0, "safety": 0.0, "stability": 0.0}, 0.0)
    assert low["score"] == 0.0


def test_overall_rip_uses_the_default_cap_from_config():
    result = compute_overall_rip(PILLARS, 100.0)
    assert result["desirabilityAdjustment"]["cap"] == DESIRABILITY_ADJUSTMENT_CAP
    assert result["desirabilityAdjustment"]["adjustment"] == pytest.approx(
        min(5.0, DESIRABILITY_ADJUSTMENT_CAP)
    )


def test_a_perfect_desirability_cannot_rescue_a_weak_financial_set():
    """Guardrail 3, at the formula level."""
    result = compute_overall_rip({"profit": 39.0, "safety": 39.0, "stability": 39.0}, 100.0)
    assert result["financialRip"]["score"] == pytest.approx(39.0)
    assert result["score"] <= 39.0 + DESIRABILITY_ADJUSTMENT_CAP
    assert result["score"] <= 50.0


@pytest.mark.parametrize("cap", [3.0, 5.0])
def test_desirability_cannot_close_a_10_point_financial_gap(cap):
    """Guardrail 4, at the formula level.

    The maximum swing between two sets is 2*cap, so at cap 5 a 10-point gap
    closes to exactly a tie and never a strict overtake; at cap 3 it cannot even
    close. Passed explicitly rather than relying on the shipping default, so
    this keeps proving the property if the cap is retuned.
    """
    behind = compute_overall_rip({"profit": 50.0, "safety": 50.0, "stability": 50.0}, 100.0, cap=cap)
    ahead = compute_overall_rip({"profit": 60.0, "safety": 60.0, "stability": 60.0}, 0.0, cap=cap)
    assert behind["score"] == pytest.approx(50.0 + cap)
    assert ahead["score"] == pytest.approx(60.0 - cap)
    assert behind["score"] <= ahead["score"], "desirability must never overtake a 10-point gap"
