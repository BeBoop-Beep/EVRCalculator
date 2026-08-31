"""Overall RIP V11 - formula, Chase transform, missing-vs-zero, V10 immutability."""

from __future__ import annotations

import json
from pathlib import Path

import pytest

from backend.desirability.chase_core_k import (
    CORE_MULTIPLE,
    EXTENDED_MULTIPLE,
    compute_core_k,
    pack_equivalent_cost,
)
from backend.desirability.chase_opportunity import (
    CHASE_OPPORTUNITY_V1_VERSION,
    chase_opportunity_score,
    compute_chase_opportunity,
)
from backend.desirability.scoring_config import (
    OVERALL_RIP_V10_VERSION,
    OVERALL_RIP_V10_WEIGHTS,
    OVERALL_RIP_V11_VERSION,
    OVERALL_RIP_V11_WEIGHTS,
)
from backend.desirability.weighted_rip import (
    compute_overall_rip_v10,
    compute_overall_rip_v11,
)

DATASET = Path("docs/research/chase_pillar_stage6_dataset.json")


# ------------------------------------------------------------ V10 immutability

def test_v10_version_string_unchanged():
    assert OVERALL_RIP_V10_VERSION == "overall_rip_v10_90_financial_v4_10_collector_appeal_v5"


def test_v10_weights_remain_exactly_90_10():
    assert OVERALL_RIP_V10_WEIGHTS == {"financial_rip": 0.90, "collector_appeal": 0.10}


def test_v10_arithmetic_is_untouched_by_v11():
    result = compute_overall_rip_v10(80.0, 40.0)
    assert result["score"] == pytest.approx(0.90 * 80.0 + 0.10 * 40.0, abs=1e-9)
    assert result["version"] == OVERALL_RIP_V10_VERSION
    assert "chaseOpportunity" not in result["components"]


def test_v10_and_v11_are_distinct_identities():
    assert OVERALL_RIP_V11_VERSION != OVERALL_RIP_V10_VERSION
    assert "v11" in OVERALL_RIP_V11_VERSION
    for token in ("83", "financial_v4", "11", "collector_appeal_v5", "06", "chase_opportunity"):
        assert token in OVERALL_RIP_V11_VERSION


# ------------------------------------------------------------------- weights

def test_v11_weights_are_83_11_6_and_sum_to_one():
    assert OVERALL_RIP_V11_WEIGHTS["financial_rip"] == 0.83
    assert OVERALL_RIP_V11_WEIGHTS["collector_appeal"] == 0.11
    assert OVERALL_RIP_V11_WEIGHTS["chase_opportunity"] == 0.06
    assert sum(OVERALL_RIP_V11_WEIGHTS.values()) == pytest.approx(1.0, abs=1e-9)


# ----------------------------------------------------------- Chase transform

@pytest.mark.parametrize("k,expected", [
    (0, 0.0),
    (1, 100.0 / 11.0),
    (2, 200.0 / 12.0),
    (5, 500.0 / 15.0),
    (10, 50.0),
    (14, 1400.0 / 24.0),
])
def test_chase_transform_exact_values(k, expected):
    assert chase_opportunity_score(k) == pytest.approx(expected, abs=1e-12)


def test_chase_transform_is_strictly_monotonic_and_saturating():
    values = [chase_opportunity_score(k) for k in range(0, 401)]
    assert all(b > a for a, b in zip(values, values[1:]))
    increments = [b - a for a, b in zip(values, values[1:])]
    assert all(b < a for a, b in zip(increments, increments[1:]))


def test_chase_transform_is_below_100_for_large_finite_k():
    assert chase_opportunity_score(10 ** 6) < 100.0
    assert chase_opportunity_score(10 ** 12) < 100.0


def test_no_clamp_distinguishes_k_above_the_saturation_constant():
    """The old 200K/(K+10) scale clamped K>=11 onto 100; this one must not."""
    scores = {k: chase_opportunity_score(k) for k in (11, 12, 13, 14)}
    assert len(set(scores.values())) == 4


def test_equal_k_is_a_legitimate_tie():
    assert chase_opportunity_score(13) == chase_opportunity_score(13)


def test_stage_six_200_scale_is_not_used():
    assert chase_opportunity_score(10) == 50.0  # the 200 scale would give 100.0


# ------------------------------------------------------------ missing vs zero

def test_valid_zero_k_is_ready_and_scores_zero():
    payload = compute_chase_opportunity(0)
    assert payload["score"] == 0.0
    assert payload["coreK"] == 0
    assert payload["status"] == "ready"
    assert payload["rankable"] is True


def test_missing_k_is_unavailable_not_zero():
    payload = compute_chase_opportunity(None)
    assert payload["score"] is None
    assert payload["coreK"] is None
    assert payload["status"] == "unavailable_missing_core_k"
    assert payload["rankable"] is False


def test_negative_k_is_refused():
    assert compute_chase_opportunity(-1)["rankable"] is False


def test_v11_ready_on_valid_zero_chase_but_unavailable_on_missing_chase():
    ready = compute_overall_rip_v11(50.0, 50.0, compute_chase_opportunity(0)["score"])
    assert ready["status"] == "ready" and ready["rankable"] is True

    missing = compute_overall_rip_v11(50.0, 50.0, compute_chase_opportunity(None)["score"])
    assert missing["score"] is None and missing["rankable"] is False
    assert "chase_opportunity_v1" in missing["missingInputs"]


# ---------------------------------------------------------------- V11 formula

def test_v11_formula_is_83_11_6():
    f, c, q = 62.5, 88.0, 33.3333333333
    result = compute_overall_rip_v11(f, c, q)
    assert result["score"] == pytest.approx(0.83 * f + 0.11 * c + 0.06 * q, abs=5e-5)
    assert result["version"] == OVERALL_RIP_V11_VERSION


@pytest.mark.parametrize("missing", ["financial", "collector", "chase"])
def test_v11_fails_closed_with_no_renormalization(missing):
    args = {"financial": 70.0, "collector": 70.0, "chase": 70.0}
    args[missing] = None
    result = compute_overall_rip_v11(args["financial"], args["collector"], args["chase"])
    assert result["score"] is None
    assert result["rankable"] is False
    assert result["version"] == OVERALL_RIP_V11_VERSION  # never falls back to V10


def test_v11_clamp_is_unreachable_for_valid_pillars():
    """All pillars in [0,100] and weights partition 1.0 -> the bound never binds."""
    for f in (0.0, 50.0, 100.0):
        for c in (0.0, 50.0, 100.0):
            for k in (0, 1, 10, 10 ** 6):
                q = chase_opportunity_score(k)
                raw = 0.83 * f + 0.11 * c + 0.06 * q
                assert 0.0 <= raw <= 100.0
                assert compute_overall_rip_v11(f, c, q)["score"] == pytest.approx(raw, abs=5e-5)


# ------------------------------------------------------------- Core K contract

def test_core_floor_is_three_x_pack_cost_not_five_and_not_a_percentile():
    assert CORE_MULTIPLE == 3.0
    assert EXTENDED_MULTIPLE == 1.0


def test_pack_equivalent_cost_uses_own_cost_over_random_pack_count():
    assert pack_equivalent_cost(product_market_cost=86.8, random_pack_count=6) == pytest.approx(
        86.8 / 6, abs=1e-12
    )


def test_missing_cost_or_pack_count_yields_no_core_k_rather_than_zero():
    for kwargs in (
        {"product_market_cost": None, "random_pack_count": 6},
        {"product_market_cost": 86.8, "random_pack_count": 0},
    ):
        result = compute_core_k(card_values=[100.0], **kwargs)
        assert result["coreK"] is None
        assert result["status"].startswith("unavailable_")


def test_core_counts_cards_at_or_above_floor_and_extended_contains_core():
    # pack cost 10.0 -> core floor 30.0, extended floor 10.0
    result = compute_core_k(
        card_values=[5.0, 10.0, 29.99, 30.0, 100.0, None, "bad"],
        product_market_cost=60.0,
        random_pack_count=6,
    )
    assert result["packEquivalentCost"] == pytest.approx(10.0)
    assert result["coreThreshold"] == pytest.approx(30.0)
    assert result["coreK"] == 2          # 30.0 and 100.0
    assert result["extendedK"] == 4      # 10.0, 29.99, 30.0, 100.0
    assert result["coreK"] <= result["extendedK"]


# ------------------------------------------------------------- research parity

def test_production_reproduces_the_frozen_stage_seven_cohort():
    rows = json.loads(DATASET.read_text(encoding="utf-8"))["rows"]
    assert len(rows) == 131
    worst = 0.0
    for row in rows:
        k = row["coreK"]
        assert pack_equivalent_cost(
            product_market_cost=row["productMarketCost"],
            random_pack_count=row["randomPackCount"],
        ) == pytest.approx(row["packEquivalentCost"], abs=1e-9)

        q = chase_opportunity_score(k)
        assert q == pytest.approx(100.0 * k / (k + 10.0), abs=1e-12)

        expected = 0.83 * row["financialRip"] + 0.11 * row["collectorAppeal"] + 0.06 * q
        worst = max(worst, abs(compute_overall_rip_v11(
            row["financialRip"], row["collectorAppeal"], q)["score"] - expected))
    assert worst < 5e-5


def test_chase_opportunity_version_identity_is_stable():
    assert CHASE_OPPORTUNITY_V1_VERSION == "chase_opportunity_v1_core_k_saturating_100_k10"
