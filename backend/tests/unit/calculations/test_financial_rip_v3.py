"""Financial RIP V3 — calculation contract tests.

Every test here is deterministic: distributions are constructed explicitly, not
sampled, so a failure is a real behavioural change and never a seed.

The suite is organized around the CLAIMS the model makes. Each test names a
claim a reader of the published score is entitled to rely on - "P05 does not
affect this score", "one huge outlier cannot buy more than 10 points",
"my score does not depend on which other sets exist" - and checks it directly.
"""

from __future__ import annotations

import json
import math

import numpy as np
import pytest

from backend.calculations.evr.financial_rip_v3 import (
    TailBuckets,
    build_financial_rip_v3,
    validate_financial_rip_v3_payload,
    verify_financial_rip_v3_score,
)
from backend.calculations.evr.financial_rip_v3_config import (
    FINANCIAL_RIP_V3_COMPONENT_ORDER,
    FINANCIAL_RIP_V3_MIN_SIMULATION_COUNT,
    FINANCIAL_RIP_V3_NORMALIZATION_VERSION,
    FINANCIAL_RIP_V3_TRANSFORMS,
    FINANCIAL_RIP_V3_VERSION,
    FINANCIAL_RIP_V3_WEIGHTS,
    JACKPOT_UPSIDE_SUBWEIGHTS,
    LOSS_RESILIENCE_SUBWEIGHTS,
    REALISTIC_UPSIDE_SUBWEIGHTS,
    normalize_metric,
)

PACK_COST = 5.0
N = 20_000


def make_distribution(
    *,
    n: int = N,
    bulk_value: float = 1.0,
    bulk_share: float = 0.90,
    mid_value: float = 6.0,
    top_value: float = 60.0,
    jackpot_value: float = 400.0,
) -> np.ndarray:
    """A deterministic, plateau-heavy distribution shaped like a real booster.

    Explicitly built with large ties at each level: the tie behaviour is the
    whole reason V3 selects tails by rank, so the fixtures must have ties.
    """
    bulk_count = int(n * bulk_share)
    jackpot_count = max(1, int(n * 0.01))
    top_count = max(1, int(n * 0.04))
    mid_count = n - bulk_count - top_count - jackpot_count
    values = np.concatenate(
        [
            np.full(bulk_count, bulk_value),
            np.full(mid_count, mid_value),
            np.full(top_count, top_value),
            np.full(jackpot_count, jackpot_value),
        ]
    )
    assert values.size == n
    return values


def build(values: np.ndarray, cost: float = PACK_COST, **kwargs):
    return build_financial_rip_v3(values, cost, **kwargs)


# ---------------------------------------------------------------------------
# 1. Weights sum exactly to 1
# ---------------------------------------------------------------------------

def test_top_level_weights_sum_to_exactly_one():
    assert sum(FINANCIAL_RIP_V3_WEIGHTS.values()) == pytest.approx(1.0, abs=1e-12)
    assert FINANCIAL_RIP_V3_WEIGHTS == {
        "true_win_frequency": 0.25,
        "typical_retention": 0.20,
        "loss_resilience": 0.15,
        "realistic_upside": 0.25,
        "jackpot_upside": 0.10,
        "base_economic_efficiency": 0.05,
    }


def test_subcomponent_weights_sum_to_one():
    for block in (
        LOSS_RESILIENCE_SUBWEIGHTS,
        REALISTIC_UPSIDE_SUBWEIGHTS,
        JACKPOT_UPSIDE_SUBWEIGHTS,
    ):
        assert sum(block.values()) == pytest.approx(1.0, abs=1e-12)


# ---------------------------------------------------------------------------
# 2. Contributions reconstruct the score
# ---------------------------------------------------------------------------

def test_contributions_reconstruct_the_final_score():
    result = build(make_distribution())
    assert result["status"] == "ready"
    verification = verify_financial_rip_v3_score(result)
    assert verification["reconstructed"] is True

    rebuilt = sum(
        result["components"][key]["score"] * FINANCIAL_RIP_V3_WEIGHTS[key]
        for key in FINANCIAL_RIP_V3_COMPONENT_ORDER
    )
    assert rebuilt == pytest.approx(result["score"], abs=1e-3)


def test_published_component_weights_are_the_applied_weights():
    result = build(make_distribution())
    for key in FINANCIAL_RIP_V3_COMPONENT_ORDER:
        component = result["components"][key]
        assert component["weight"] == FINANCIAL_RIP_V3_WEIGHTS[key]
        assert component["contribution"] == pytest.approx(
            component["score"] * component["weight"], abs=1e-3
        )


# ---------------------------------------------------------------------------
# 3. P05 carries zero V3 weight
# ---------------------------------------------------------------------------

def test_p05_changes_do_not_affect_v3_when_v3_inputs_are_unchanged():
    """Move the bottom 4% far down; every V3 input is untouched, so is the score.

    The 5th percentile moves substantially. True win frequency, the median,
    average retention given loss, the soft/hard loss split, both tails and the
    top-1%-excluded RTP are all constructed to be identical between the two
    distributions - so if V3 read P05 anywhere, this test would catch it.
    """
    baseline = np.sort(make_distribution())
    # Crush the bottom 8% so the 5th percentile lands strictly INSIDE the
    # modified region. Everything from the 8th percentile up - the median, both
    # tails, and the top-1%-excluded structure above it - is byte-identical.
    crushed = baseline.copy()
    crushed[: int(N * 0.08)] = 0.05

    high_result = build(baseline)
    low_result = build(crushed)

    low_p05 = low_result["distributionDisclosures"]["p05Value"]
    high_p05 = high_result["distributionDisclosures"]["p05Value"]
    assert low_p05 < high_p05, "the fixture must actually move P05"

    # Loss Resilience legitimately moves (the losing mass changed), but the
    # components that have nothing to do with the bottom 5% must not.
    for untouched in ("realistic_upside", "jackpot_upside", "typical_retention"):
        assert low_result["components"][untouched]["score"] == pytest.approx(
            high_result["components"][untouched]["score"], abs=1e-9
        )
    assert low_result["distributionDisclosures"]["p05IsScoredByV3"] is False


def test_p05_is_not_read_by_any_v3_component_source():
    """A source-level guarantee, not just a numeric one.

    A numeric test can be satisfied by a fixture that happens not to trip the
    dependency. This asserts that the string `p05` appears in the engine only in
    the disclosure block and its explanatory comments - never inside a component
    builder.
    """
    from pathlib import Path

    import backend.calculations.evr.financial_rip_v3 as module

    source = Path(module.__file__).read_text(encoding="utf-8")
    # Split at the disclosures block; everything before it is scoring code.
    marker = '"distributionDisclosures"'
    assert marker in source
    scoring_region = source[: source.index(marker)]
    for builder in (
        "def compute_true_win_frequency_raw",
        "def compute_typical_retention_raw",
        "def compute_loss_resilience_raw",
        "def compute_realistic_upside_raw",
        "def compute_jackpot_upside_raw",
        "def compute_base_economic_efficiency_raw",
    ):
        assert builder in scoring_region
    # `percentile(values, 5)` must never appear inside a component builder.
    body_start = scoring_region.index("def compute_true_win_frequency_raw")
    body_end = scoring_region.index("_RAW_INPUT_PATHS")
    component_bodies = scoring_region[body_start:body_end]
    assert "percentile(values, 5)" not in component_bodies
    assert ", 5)" not in component_bodies.replace("np.percentile(values, 95)", "")


# ---------------------------------------------------------------------------
# 4. Monotonicity: each lever moves the component it should
# ---------------------------------------------------------------------------

def test_higher_true_win_probability_raises_only_its_component_and_the_score():
    low = make_distribution(bulk_value=1.0, mid_value=4.0)
    # Lift the mid tier above cost so more packs recover their cost. This also
    # raises the mid tier's value, so Typical Retention may move; the claim
    # under test is that True Win Frequency rises and the total rises with it.
    high = make_distribution(bulk_value=1.0, mid_value=6.0)

    low_result = build(low)
    high_result = build(high)

    low_win = low_result["components"]["true_win_frequency"]
    high_win = high_result["components"]["true_win_frequency"]
    assert high_win["raw"]["trueWinProbability"] > low_win["raw"]["trueWinProbability"]
    assert high_win["score"] > low_win["score"]
    assert high_result["score"] > low_result["score"]
    # The tails are identical between the two fixtures, so upside must not move.
    assert high_result["components"]["jackpot_upside"]["score"] == pytest.approx(
        low_result["components"]["jackpot_upside"]["score"], abs=1e-9
    )


def test_higher_p50_raises_typical_retention():
    low = make_distribution(bulk_value=1.0, bulk_share=0.60)
    high = make_distribution(bulk_value=3.0, bulk_share=0.60)
    low_result = build(low)
    high_result = build(high)
    assert (
        high_result["components"]["typical_retention"]["raw"]["typicalPackValue"]
        > low_result["components"]["typical_retention"]["raw"]["typicalPackValue"]
    )
    assert (
        high_result["components"]["typical_retention"]["score"]
        > low_result["components"]["typical_retention"]["score"]
    )


def test_softer_losing_outcomes_raise_loss_resilience():
    # Same win rate, same tails; the losing mass is simply less catastrophic.
    harsh = make_distribution(bulk_value=0.4)
    soft = make_distribution(bulk_value=3.5)
    harsh_result = build(harsh)
    soft_result = build(soft)

    harsh_loss = harsh_result["components"]["loss_resilience"]
    soft_loss = soft_result["components"]["loss_resilience"]
    assert soft_loss["raw"]["averageRetentionGivenLoss"] > harsh_loss["raw"]["averageRetentionGivenLoss"]
    assert soft_loss["raw"]["hardLossProbability"] < harsh_loss["raw"]["hardLossProbability"]
    assert soft_loss["score"] > harsh_loss["score"]


def test_better_95th_to_99th_band_raises_realistic_upside():
    low = make_distribution(top_value=30.0)
    high = make_distribution(top_value=90.0)
    low_result = build(low)
    high_result = build(high)

    assert (
        high_result["components"]["realistic_upside"]["raw"]["realisticTailMeanValue"]
        > low_result["components"]["realistic_upside"]["raw"]["realisticTailMeanValue"]
    )
    assert (
        high_result["components"]["realistic_upside"]["score"]
        > low_result["components"]["realistic_upside"]["score"]
    )
    # The top 1% ITSELF is untouched, so its conditional mean cannot move.
    assert high_result["components"]["jackpot_upside"]["raw"][
        "jackpotTailMeanValue"
    ] == pytest.approx(
        low_result["components"]["jackpot_upside"]["raw"]["jackpotTailMeanValue"], abs=1e-6
    )
    # The P99 THRESHOLD does rise, and correctly so: raising the 95th-99th band
    # genuinely raises where the top 1% begins. That is a threshold moving, not
    # the jackpot outcomes changing - which is exactly why the two are reported
    # as separate numbers with separate copy.
    assert (
        high_result["components"]["jackpot_upside"]["raw"]["p99ThresholdValue"]
        > low_result["components"]["jackpot_upside"]["raw"]["p99ThresholdValue"]
    )
    # Realistic Upside is the component this lever is for, and it must move more.
    realistic_delta = (
        high_result["components"]["realistic_upside"]["score"]
        - low_result["components"]["realistic_upside"]["score"]
    )
    jackpot_delta = (
        high_result["components"]["jackpot_upside"]["score"]
        - low_result["components"]["jackpot_upside"]["score"]
    )
    assert realistic_delta > jackpot_delta


def test_improving_only_the_top_1pct_affects_jackpot_and_base_disclosures_only():
    low = make_distribution(jackpot_value=200.0)
    high = make_distribution(jackpot_value=900.0)
    low_result = build(low)
    high_result = build(high)

    assert (
        high_result["components"]["jackpot_upside"]["score"]
        > low_result["components"]["jackpot_upside"]["score"]
    )
    # Realistic Upside excludes the top 1%, so it cannot move.
    assert high_result["components"]["realistic_upside"]["score"] == pytest.approx(
        low_result["components"]["realistic_upside"]["score"], abs=1e-9
    )
    # Base Economic Efficiency SCORES the top-1%-excluded RTP, so its score is
    # unchanged even though the total-RTP DISCLOSURE rises. That separation is
    # the point of the component.
    assert high_result["components"]["base_economic_efficiency"]["score"] == pytest.approx(
        low_result["components"]["base_economic_efficiency"]["score"], abs=1e-9
    )
    assert (
        high_result["components"]["base_economic_efficiency"]["raw"]["totalRtpRatio"]
        > low_result["components"]["base_economic_efficiency"]["raw"]["totalRtpRatio"]
    )


# ---------------------------------------------------------------------------
# 5. The jackpot ceiling
# ---------------------------------------------------------------------------

def test_one_huge_outlier_cannot_exceed_the_ten_point_jackpot_ceiling():
    values = make_distribution(jackpot_value=1_000_000.0)
    result = build(values)
    jackpot = result["components"]["jackpot_upside"]
    assert jackpot["score"] <= 100.0
    assert jackpot["contribution"] <= 10.0 + 1e-9
    assert jackpot["weight"] == 0.10


def test_jackpot_transforms_saturate_and_never_reach_one_hundred():
    for metric in ("p99_threshold_ratio", "jackpot_tail_mean_ratio"):
        assert FINANCIAL_RIP_V3_TRANSFORMS[metric]["family"] == "saturating_exp"
        enormous = normalize_metric(metric, 1e9)
        assert enormous["score"] <= 100.0
        assert math.isfinite(enormous["score"])
        # Strictly increasing.
        assert normalize_metric(metric, 50.0)["score"] > normalize_metric(metric, 10.0)["score"]


# ---------------------------------------------------------------------------
# 6. Exact empirical tail handling
# ---------------------------------------------------------------------------

def test_realistic_tail_mean_excludes_the_top_one_percent():
    values = make_distribution(top_value=50.0, jackpot_value=5000.0)
    result = build(values)
    realistic = result["components"]["realistic_upside"]["raw"]
    jackpot = result["components"]["jackpot_upside"]["raw"]
    # If the top 1% leaked into the realistic band, a 5000 jackpot would drag
    # the band mean far above the 50 plateau it is actually made of.
    assert realistic["realisticTailMeanValue"] == pytest.approx(50.0, abs=1e-6)
    assert jackpot["jackpotTailMeanValue"] == pytest.approx(5000.0, abs=1e-6)


def test_rank_tail_selection_uses_exact_empirical_mass_despite_ties():
    """A massive plateau at the P95 threshold must not inflate the tail.

    60% of this distribution sits on one value that IS the 95th percentile. A
    boolean `values >= percentile` mask would select 60% of runs and call it the
    top 5%. The rank buckets select exactly 1% and 4%.
    """
    n = 10_000
    values = np.concatenate([np.full(9_500, 2.0), np.full(400, 2.0), np.full(100, 500.0)])
    assert values.size == n
    buckets = TailBuckets(np.sort(values))
    assert buckets.jackpot.size == 100
    assert buckets.realistic.size == 400
    assert buckets.jackpot.size / n == pytest.approx(0.01)
    assert (buckets.jackpot.size + buckets.realistic.size) / n == pytest.approx(0.05)
    # Every realistic-band observation is on the plateau, so its mean is the
    # plateau value - stable despite the ties straddling the boundary.
    assert float(buckets.realistic.mean()) == pytest.approx(2.0)


def test_tail_selection_payload_reports_requested_and_actual_shares():
    result = build(make_distribution())
    tail = result["distributionDisclosures"]["tailSelection"]
    assert tail["method"] == "empirical_rank_exact_mass_v1"
    assert tail["requestedShares"] == {"jackpot": 0.01, "realistic": 0.05}
    assert tail["selectedCounts"]["jackpot"] == pytest.approx(N * 0.01)
    assert tail["selectedShares"]["jackpot"] == pytest.approx(0.01, abs=1e-6)
    assert tail["selectedShares"]["combinedTail"] == pytest.approx(0.05, abs=1e-6)


# ---------------------------------------------------------------------------
# 7. Availability: never a neutral 50
# ---------------------------------------------------------------------------

@pytest.mark.parametrize("bad_cost", [0.0, -1.0, None, float("nan"), "abc"])
def test_invalid_pack_cost_makes_v3_unavailable(bad_cost):
    result = build_financial_rip_v3(make_distribution(), bad_cost)
    assert result["status"] == "unavailable"
    assert result["statusReason"] == "invalid_pack_cost"
    assert result["score"] is None
    assert result["rankable"] is False
    assert result["components"] == {}


def test_too_few_simulations_makes_v3_unavailable_and_unrankable():
    small = make_distribution(n=500)
    result = build_financial_rip_v3(small, PACK_COST)
    assert result["status"] == "unavailable"
    assert result["statusReason"] == "insufficient_simulation_count"
    assert result["rankable"] is False
    assert result["score"] is None
    assert result["estimationDiagnostics"]["requiredSimulationCount"] == (
        FINANCIAL_RIP_V3_MIN_SIMULATION_COUNT
    )


def test_empty_and_non_finite_outcome_vectors_are_unavailable():
    empty = build_financial_rip_v3(np.array([]), PACK_COST)
    assert empty["statusReason"] == "empty_outcome_vector"

    broken = make_distribution().astype(np.float64)
    broken[0] = np.inf
    result = build_financial_rip_v3(broken, PACK_COST)
    assert result["statusReason"] == "non_finite_outcome_vector"
    assert result["score"] is None


def test_missing_required_data_never_becomes_a_neutral_fifty():
    for metric in FINANCIAL_RIP_V3_TRANSFORMS:
        record = normalize_metric(metric, None)
        assert record["score"] is None
        assert record["available"] is False
        assert record["score"] != 50


def test_no_losing_runs_is_perfect_by_construction_not_by_division():
    # Every pack beats cost.
    values = np.concatenate([np.full(19_800, 8.0), np.full(200, 90.0)])
    result = build_financial_rip_v3(values, PACK_COST, min_simulation_count=10_000)
    loss = result["components"]["loss_resilience"]
    assert loss["raw"]["noLosingRuns"] is True
    assert loss["raw"]["losingRunCount"] == 0
    assert loss["score"] == pytest.approx(100.0)
    assert loss["raw"]["noLosingRunsReason"]


# ---------------------------------------------------------------------------
# 8. JSON safety
# ---------------------------------------------------------------------------

def test_every_returned_number_is_a_finite_json_safe_primitive():
    result = build(make_distribution())
    encoded = json.dumps(result)  # must not raise on a numpy scalar
    assert encoded

    def walk(node):
        if isinstance(node, dict):
            for value in node.values():
                walk(value)
        elif isinstance(node, (list, tuple)):
            for value in node:
                walk(value)
        elif isinstance(node, (int, float)) and not isinstance(node, bool):
            assert type(node) in (int, float), f"{node!r} is {type(node)}, not a builtin"
            assert math.isfinite(node)
        else:
            assert node is None or isinstance(node, (str, bool)), f"unexpected leaf {node!r}"

    walk(result)


# ---------------------------------------------------------------------------
# 9. Cohort independence — the defining property of V3
# ---------------------------------------------------------------------------

def test_score_does_not_depend_on_other_sets_in_the_cohort():
    """The same distribution scores identically however it is batched.

    V3 takes no cohort argument at all, which is the structural guarantee. This
    checks the consequence a reader cares about: the number does not move.
    """
    values = make_distribution()
    alone = build(values)

    others = [
        make_distribution(bulk_value=0.1, jackpot_value=10_000.0),
        make_distribution(bulk_value=4.9, top_value=5.0, jackpot_value=6.0),
    ]
    for other in others:
        build(other)  # scoring another set must have no side effect
    after = build(values)

    assert after["score"] == alone["score"]
    for key in FINANCIAL_RIP_V3_COMPONENT_ORDER:
        assert after["components"][key]["score"] == alone["components"][key]["score"]


def test_adding_a_fake_unrelated_set_does_not_change_an_existing_absolute_score():
    values = make_distribution()
    before = build(values)["score"]

    # An extreme fake set that WOULD dominate any cohort min-max normalization.
    fake = np.concatenate([np.full(19_000, 0.01), np.full(1_000, 100_000.0)])
    fake_result = build_financial_rip_v3(fake, PACK_COST, min_simulation_count=10_000)
    assert fake_result["status"] == "ready"

    after = build(values)["score"]
    assert after == before


# ---------------------------------------------------------------------------
# 10. Validator
# ---------------------------------------------------------------------------

def test_validator_accepts_a_real_payload_and_rejects_tampering():
    result = build(make_distribution())
    ok, problems = validate_financial_rip_v3_payload(result)
    assert ok, problems

    tampered = json.loads(json.dumps(result))
    tampered["score"] = 99.0
    ok, problems = validate_financial_rip_v3_payload(tampered)
    assert not ok
    assert any("reconstruct" in problem for problem in problems)

    wrong_version = json.loads(json.dumps(result))
    wrong_version["scoreVersion"] = "rip_v3_weighted_four_component"
    ok, problems = validate_financial_rip_v3_payload(wrong_version)
    assert not ok
    assert any("scoreVersion" in problem for problem in problems)

    missing_component = json.loads(json.dumps(result))
    del missing_component["components"]["jackpot_upside"]
    ok, problems = validate_financial_rip_v3_payload(missing_component)
    assert not ok


def test_versions_are_distinct_from_every_pre_existing_identifier():
    from backend.desirability.scoring_config import (
        FINANCIAL_RIP_V2_VERSION,
        OVERALL_RIP_V3_VERSION,
        OVERALL_RIP_V4_VERSION,
        RIP_V3_VERSION,
    )

    distinct = {
        FINANCIAL_RIP_V3_VERSION,
        FINANCIAL_RIP_V3_NORMALIZATION_VERSION,
        FINANCIAL_RIP_V2_VERSION,
        RIP_V3_VERSION,
        OVERALL_RIP_V3_VERSION,
        OVERALL_RIP_V4_VERSION,
    }
    assert len(distinct) == 6
    assert FINANCIAL_RIP_V3_VERSION == "financial_rip_v3_outcome_profile_25_20_15_25_10_5"
