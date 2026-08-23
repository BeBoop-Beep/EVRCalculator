"""Part 34 fixtures for the one-pack distribution layer.

Synthetic distributions whose correct answers are known by construction, plus
the contract test that keeps the tail rule welded to Financial RIP V3's.
"""

from __future__ import annotations

import math

import numpy as np
import pytest

from backend.calculations.evr.financial_rip_v3 import TailBuckets
from backend.calculations.evr.financial_rip_v3_config import (
    JACKPOT_TAIL_SHARE,
    REALISTIC_TAIL_SHARE,
)
from backend.research.ev_representativeness.distribution import (
    compute_baseline_distribution,
    compute_outcome_tails,
    compute_return_ratio_buckets,
    rank_tail_count,
)


# ---------------------------------------------------------------------------
# The reuse contract
# ---------------------------------------------------------------------------

@pytest.mark.parametrize("n", [100, 1_000, 12_345, 1_000_000])
def test_rank_tail_count_matches_financial_rip_tail_buckets(n):
    """The generalized rule must BE Financial RIP V3's rule, not resemble it.

    If TailBuckets ever changes its selection, this fails loudly rather than
    letting the research layer publish a differently-defined "top 1%".
    """
    buckets = TailBuckets(np.sort(np.arange(n, dtype=np.float64)))
    assert rank_tail_count(n, JACKPOT_TAIL_SHARE) == buckets.top_1_count
    assert rank_tail_count(n, REALISTIC_TAIL_SHARE) == buckets.top_5_count


def test_rank_tail_count_fixes_mass_not_threshold():
    """A tie plateau must not inflate the selected observation count.

    This is the defect the rank rule exists to prevent: 900 of these 1,000
    outcomes are exactly 1.0, so `values >= percentile(values, 99)` would be a
    correct-looking mask over a wildly wrong number of observations.
    """
    values = np.concatenate([np.full(900, 1.0), np.linspace(2.0, 100.0, 100)])
    assert rank_tail_count(values.size, 0.01) == 10

    plateau = np.full(1000, 5.0)
    threshold_selected = int(np.count_nonzero(plateau >= np.percentile(plateau, 99)))
    assert threshold_selected == 1000       # every observation - the failure mode
    assert rank_tail_count(plateau.size, 0.01) == 10   # exactly 1%


# ---------------------------------------------------------------------------
# Fixture 1 - constant distribution
# ---------------------------------------------------------------------------

def test_constant_distribution_has_no_gap_and_full_capture():
    values = np.full(10_000, 4.0)
    result = compute_baseline_distribution(values, pack_cost=4.0)

    assert result.ev == pytest.approx(4.0)
    assert result.p50 == pytest.approx(4.0)
    assert result.std_dev == pytest.approx(0.0)
    assert result.variance == pytest.approx(0.0)
    assert result.ev_typical_gap_absolute == pytest.approx(0.0)
    assert result.typical_capture == pytest.approx(1.0)
    assert result.relative_gap == pytest.approx(0.0)
    assert result.mean_abs_dev_about_median == pytest.approx(0.0)

    # Both skew diagnostics divide by a vanishing dispersion. "Undefined" is the
    # honest answer; 0/0 -> nan or a huge float would both be lies.
    assert result.pearson_skew_2 is None
    assert result.groeneveld_meeden_skew is None

    # A flat distribution puts exactly its population share of value in any tail.
    top1 = result.tails[0.01]
    assert top1.ev_share == pytest.approx(0.01, abs=1e-6)
    assert top1.conditional_mean == pytest.approx(4.0)


# ---------------------------------------------------------------------------
# Fixture 2 - strong two-point skew (95% low / 5% high)
# ---------------------------------------------------------------------------

def _two_point(n=100_000, low=1.0, high=100.0, high_share=0.05):
    high_count = int(round(n * high_share))
    return np.concatenate([np.full(n - high_count, low), np.full(high_count, high)])


def test_two_point_skew_produces_positive_gap_and_tail_concentration():
    values = _two_point()
    result = compute_baseline_distribution(values, pack_cost=5.0)

    # EV = 0.95*1 + 0.05*100 = 5.95 ; median = 1.0
    assert result.ev == pytest.approx(5.95, abs=1e-9)
    assert result.p50 == pytest.approx(1.0)
    assert result.ev > result.p50
    assert result.ev_typical_gap_absolute == pytest.approx(4.95, abs=1e-9)
    assert result.typical_capture == pytest.approx(1.0 / 5.95, rel=1e-9)
    assert result.relative_gap == pytest.approx(1.0 - 1.0 / 5.95, rel=1e-9)

    # Both skew diagnostics must agree on the SIGN; they are different scalings
    # of the same mean-median gap and are not expected to agree on magnitude.
    assert result.pearson_skew_2 > 0
    assert result.groeneveld_meeden_skew > 0

    # E[|X - median|] = 0.05 * 99 = 4.95, so GM = 4.95 / 4.95 = 1.0 exactly.
    assert result.mean_abs_dev_about_median == pytest.approx(4.95, abs=1e-9)
    assert result.groeneveld_meeden_skew == pytest.approx(1.0, abs=1e-9)

    # The top 5% is precisely the high outcomes: 5% of packs, 5*100/595 of value.
    top5 = result.tails[0.05]
    assert top5.ev_share == pytest.approx(500.0 / 595.0, rel=1e-9)
    assert top5.conditional_mean == pytest.approx(100.0)


def test_cost_normalized_gap_makes_differently_priced_products_comparable():
    """Raw dollar gaps are not comparable across price points; normalized are."""
    cheap = compute_baseline_distribution(_two_point(low=1.0, high=100.0), pack_cost=5.0)
    pricey = compute_baseline_distribution(_two_point(low=2.0, high=200.0), pack_cost=10.0)

    # The expensive product's raw gap is exactly double...
    assert pricey.ev_typical_gap_absolute == pytest.approx(
        2.0 * cheap.ev_typical_gap_absolute, rel=1e-9
    )
    # ...but it is the same product economically, which only normalization shows.
    assert pricey.ev_typical_gap_cost_normalized == pytest.approx(
        cheap.ev_typical_gap_cost_normalized, rel=1e-9
    )
    assert pricey.typical_capture == pytest.approx(cheap.typical_capture, rel=1e-9)


# ---------------------------------------------------------------------------
# Fixture 3 - broad value vs concentrated value at matched EV
# ---------------------------------------------------------------------------

def test_concentration_metrics_separate_broad_from_concentrated_at_equal_ev():
    """Two distributions, same EV, opposite opening experience.

    This is the H4 shape in miniature: if the tail-concentration metrics cannot
    tell these apart, they cannot tell apart the real sets either.
    """
    n = 100_000
    # Concentrated: 99% at $1, 1% at $496 -> EV = 5.95
    concentrated = np.concatenate([np.full(99_000, 1.0), np.full(1_000, 496.0)])
    # Broad: four moderately valuable outcomes of equal probability -> EV = 5.95
    broad = np.concatenate([
        np.full(n // 4, 2.0), np.full(n // 4, 4.0),
        np.full(n // 4, 7.0), np.full(n // 4, 10.8),
    ])
    assert concentrated.mean() == pytest.approx(broad.mean(), rel=1e-9)

    con = compute_baseline_distribution(concentrated, pack_cost=5.0)
    brd = compute_baseline_distribution(broad, pack_cost=5.0)

    assert con.tails[0.01].ev_share > 0.80
    assert brd.tails[0.01].ev_share < 0.05
    assert con.typical_capture < brd.typical_capture
    assert con.groeneveld_meeden_skew > brd.groeneveld_meeden_skew
    assert con.coefficient_of_variation > brd.coefficient_of_variation


def test_tail_shares_are_nested_and_ordered():
    rng = np.random.default_rng(11)
    values = rng.lognormal(mean=0.0, sigma=2.0, size=50_000)
    tails = compute_outcome_tails(np.sort(values))

    assert tails[0.10].ev_share >= tails[0.05].ev_share >= tails[0.01].ev_share
    # Conditional means run the other way: a narrower tail is a richer one.
    assert tails[0.01].conditional_mean >= tails[0.05].conditional_mean >= tails[0.10].conditional_mean
    assert tails[0.10].observation_count > tails[0.05].observation_count > tails[0.01].observation_count


# ---------------------------------------------------------------------------
# Degenerate handling (Part 2.3's explicit requirement)
# ---------------------------------------------------------------------------

def test_zero_ev_yields_none_not_division_by_zero():
    result = compute_baseline_distribution(np.zeros(1_000), pack_cost=4.0)
    assert result.ev == pytest.approx(0.0)
    assert result.typical_capture is None
    assert result.relative_gap is None
    assert result.pearson_skew_2 is None
    assert result.groeneveld_meeden_skew is None
    assert result.tails[0.01].ev_share is None  # a share of nothing is undefined


def test_empty_input_is_rejected():
    with pytest.raises(ValueError):
        compute_baseline_distribution(np.array([], dtype=np.float64))


# ---------------------------------------------------------------------------
# Part 5 - return-ratio buckets
# ---------------------------------------------------------------------------

def test_return_ratio_buckets_partition_every_outcome():
    rng = np.random.default_rng(5)
    values = rng.lognormal(mean=1.0, sigma=1.5, size=20_000)
    result = compute_return_ratio_buckets(values, cost=4.0)

    assert sum(row["occurrenceCount"] for row in result["buckets"]) == values.size
    assert result["buckets"][-1]["cumulativeProbability"] == pytest.approx(1.0)
    assert all(0.0 <= row["probability"] <= 1.0 for row in result["buckets"])


def test_return_ratio_buckets_place_known_outcomes_exactly():
    # 0.4x, 0.8x, 1.2x, 3.0x and 8.0x of a $10 cost.
    values = np.array([4.0, 8.0, 12.0, 30.0, 80.0])
    rows = {r["bucketLabel"]: r["occurrenceCount"] for r in
            compute_return_ratio_buckets(values, cost=10.0)["buckets"]}
    assert rows["0.25-0.5x"] == 1
    assert rows["0.75-1x"] == 1
    assert rows["1-1.5x"] == 1
    assert rows["2-5x"] == 1
    assert rows[">=5x"] == 1


def test_return_ratio_buckets_reject_non_positive_cost():
    with pytest.raises(ValueError):
        compute_return_ratio_buckets(np.array([1.0, 2.0]), cost=0.0)
