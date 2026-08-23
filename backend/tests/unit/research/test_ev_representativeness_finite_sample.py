"""Part 34 fixtures for the finite-sample layer.

The important one is ``test_monte_carlo_matches_exact_enumeration``: a
distribution small enough to enumerate analytically, so the realization and
convergence estimators are checked against truth rather than against themselves.
"""

from __future__ import annotations

import math
from itertools import product

import numpy as np
import pytest

from backend.research.ev_representativeness.finite_sample import (
    CurvePoint,
    HORIZON_EXCEEDS_CAP,
    HORIZON_RESOLVED,
    audit_monotonicity,
    build_confirmation_grid,
    confirm_session_count,
    convergence_metric_key,
    evaluate_pack_grid,
    iter_session_sums,
    realization_metric_key,
    research_seed,
    resolve_horizon,
    wilson_interval,
)


# ---------------------------------------------------------------------------
# Wilson intervals (Part 22)
# ---------------------------------------------------------------------------

def test_wilson_interval_brackets_the_estimate():
    result = wilson_interval(800, 1000)
    assert result.estimate == pytest.approx(0.80)
    assert result.ci_lower < 0.80 < result.ci_upper
    assert result.standard_error == pytest.approx(math.sqrt(0.8 * 0.2 / 1000))


def test_wilson_interval_never_escapes_the_unit_interval():
    """The Wald failure mode this method exists to avoid."""
    for successes, trials in [(0, 50), (50, 50), (1, 10_000), (9_999, 10_000)]:
        result = wilson_interval(successes, trials)
        assert 0.0 <= result.ci_lower <= result.ci_upper <= 1.0

    # Wald at p = 1.0 would give [1.0, 1.0] and claim certainty from 50 trials.
    saturated = wilson_interval(50, 50)
    assert saturated.ci_lower < 1.0


def test_wilson_interval_narrows_with_more_trials():
    small = wilson_interval(800, 1_000)
    large = wilson_interval(80_000, 100_000)
    assert (large.ci_upper - large.ci_lower) < (small.ci_upper - small.ci_lower)


def test_wilson_interval_rejects_impossible_counts():
    with pytest.raises(ValueError):
        wilson_interval(11, 10)
    with pytest.raises(ValueError):
        wilson_interval(0, 0)


# ---------------------------------------------------------------------------
# The exact-enumeration fixture
# ---------------------------------------------------------------------------

def _exact_probabilities(outcomes, n_packs, ev, target, tolerance):
    """Brute-force truth over every equally likely path of ``n_packs`` draws."""
    realized = 0
    converged = 0
    total = 0
    for path in product(outcomes, repeat=n_packs):
        mean = sum(path) / n_packs
        total += 1
        if mean >= target * ev:
            realized += 1
        if abs(mean / ev - 1.0) <= tolerance:
            converged += 1
    return realized / total, converged / total


@pytest.mark.parametrize("n_packs", [1, 3, 5])
def test_monte_carlo_matches_exact_enumeration(n_packs):
    """Estimator correctness, against enumerated truth.

    X is uniform on {0, 10}, so EV = 5 and every one of the 2^N paths is equally
    likely. The source vector is built with exactly equal mass so bootstrap
    draws reproduce the true distribution rather than an approximation of it,
    which makes this a test of the ESTIMATOR and not of sampling luck.
    """
    outcomes = (0.0, 10.0)
    source = np.array([0.0, 10.0] * 5_000, dtype=np.float64)
    ev = 5.0
    target, tolerance = 0.80, 0.20

    exact_realization, exact_convergence = _exact_probabilities(
        outcomes, n_packs, ev, target, tolerance
    )

    sessions = 400_000
    points = evaluate_pack_grid(
        source,
        [n_packs],
        ev=ev,
        pack_cost=None,
        realization_targets=[target],
        convergence_tolerances=[tolerance],
        session_count=sessions,
        seed=research_seed(["exact-enumeration", n_packs]),
        stage="confirm",
        include_session_distribution=False,
    )
    by_key = {p.metric_key: p for p in points}

    # Tolerance is stated in units of the estimate's OWN standard error, at 5
    # sigma. Asserting the exact answer falls inside the 95% interval would make
    # this test a coin flip - six such checks miss roughly a quarter of the time
    # by construction, which is the interval behaving correctly, not a bug. Five
    # sigma fires with probability ~6e-7 under correct behaviour while still
    # catching any real estimator error, which is orders of magnitude larger.
    def _assert_unbiased(point, truth):
        assert point.standard_error is not None
        if point.standard_error == 0.0:
            assert point.estimate == pytest.approx(truth, abs=1e-12)
        else:
            assert abs(point.estimate - truth) <= 5.0 * point.standard_error
        # The reported interval must still be a sane bracket around the estimate.
        assert point.ci_lower <= point.estimate <= point.ci_upper

    _assert_unbiased(by_key[realization_metric_key(target)], exact_realization)
    _assert_unbiased(by_key[convergence_metric_key(tolerance)], exact_convergence)


def test_exact_enumeration_values_are_what_we_think_they_are():
    """Guards the fixture itself: hand-computed truth for N = 5.

    S_5 = 10 * Binomial(5, 1/2).
      realization  P(mean >= 4)      = P(k >= 2) = 26/32
      convergence  P(|mean/5-1|<=.2) = P(2 <= k <= 3) = 20/32
    """
    realization, convergence = _exact_probabilities((0.0, 10.0), 5, 5.0, 0.80, 0.20)
    assert realization == pytest.approx(26 / 32)
    assert convergence == pytest.approx(20 / 32)


# ---------------------------------------------------------------------------
# Kernel behaviour
# ---------------------------------------------------------------------------

def test_session_sums_are_nested_common_random_numbers():
    """Session i's N=10 total must CONTAIN its N=4 total - that is what CRN means."""
    source = np.arange(1.0, 101.0)
    seen = {}
    for pack_count, totals in iter_session_sums(
        source, [4, 10], session_count=500, seed=99
    ):
        seen[pack_count] = totals.copy()
    assert np.all(seen[10] >= seen[4])


def test_session_kernel_is_reproducible_from_its_seed():
    source = np.arange(1.0, 51.0)
    runs = []
    for _ in range(2):
        for pack_count, totals in iter_session_sums(source, [7], session_count=1_000, seed=4242):
            runs.append(totals.copy())
    assert np.array_equal(runs[0], runs[1])


def test_session_kernel_independent_seeds_differ():
    source = np.arange(1.0, 51.0)
    first = next(iter(iter_session_sums(source, [7], session_count=1_000, seed=1)))[1].copy()
    second = next(iter(iter_session_sums(source, [7], session_count=1_000, seed=2)))[1].copy()
    assert not np.array_equal(first, second)


def test_at_one_pack_the_session_distribution_is_the_source_distribution():
    """A one-pack "session" is just a pack; the estimator must not distort it."""
    rng = np.random.default_rng(3)
    source = rng.lognormal(0.0, 1.0, size=100_000)
    points = evaluate_pack_grid(
        source, [1], ev=float(source.mean()), pack_cost=1.0,
        realization_targets=[0.5], convergence_tolerances=[0.2],
        session_count=200_000, seed=7, stage="coarse",
    )
    by_key = {p.metric_key: p.estimate for p in points}
    assert by_key["session_mean_per_pack"] == pytest.approx(source.mean(), rel=0.02)
    assert by_key["session_p50_per_pack"] == pytest.approx(np.median(source), rel=0.05)


def test_degenerate_ev_emits_no_probability_metrics():
    """With EV <= 0 the realization ratio is meaningless; emit nothing, not zeros."""
    points = evaluate_pack_grid(
        np.zeros(1_000), [1, 4], ev=0.0, pack_cost=1.0,
        realization_targets=[0.8], convergence_tolerances=[0.2],
        session_count=100, seed=1, stage="coarse",
    )
    assert not any(p.metric_key.startswith("realization_ge_") for p in points)
    assert not any(p.metric_key.startswith("within_tau_") for p in points)
    assert any(p.metric_key == "session_mean_per_pack" for p in points)


# ---------------------------------------------------------------------------
# Convergence behaviour (the substantive claim)
# ---------------------------------------------------------------------------

def test_convergence_rises_with_n_and_is_slower_for_the_skewed_distribution():
    """More packs -> tighter around EV; and skew makes it take longer.

    Two distributions with the SAME mean: one nearly constant, one 95/5 skewed.
    """
    n = 200_000
    # Deliberately WIDER than the +/-20% band at N = 1. A {4.5, 5.5} pair would
    # already sit inside the tolerance on a single pack, so its curve would be
    # flat at 1.0 everywhere and the test would prove nothing about convergence.
    tight = np.concatenate([np.full(n // 2, 2.0), np.full(n // 2, 8.0)])
    skewed = np.concatenate([np.full(int(n * 0.95), 1.0), np.full(n - int(n * 0.95), 81.0)])
    assert tight.mean() == pytest.approx(skewed.mean(), rel=1e-9)

    grid = [1, 10, 100, 1000]
    key = convergence_metric_key(0.20)

    def curve(source):
        points = evaluate_pack_grid(
            source, grid, ev=float(source.mean()), pack_cost=None,
            realization_targets=[], convergence_tolerances=[0.20],
            session_count=20_000, seed=research_seed([len(source)]), stage="coarse",
            include_session_distribution=False,
        )
        return {p.pack_count: p.estimate for p in points if p.metric_key == key}

    tight_curve, skewed_curve = curve(tight), curve(skewed)

    assert tight_curve[1000] > tight_curve[1]
    assert skewed_curve[1000] > skewed_curve[1]
    # At every checkpoint the skewed distribution is further from representative.
    for pack_count in grid:
        assert skewed_curve[pack_count] <= tight_curve[pack_count] + 1e-9


# ---------------------------------------------------------------------------
# Monotonicity audit and horizon rules
# ---------------------------------------------------------------------------

def _point(pack_count, estimate, *, se=0.001, ci_lower=None, metric_key="within_tau_0.20"):
    return CurvePoint(
        scope_kind="pack_grid", sealed_product_id=None, pack_count=pack_count,
        metric_key=metric_key, estimate=estimate, session_count=50_000,
        stage="coarse", seed=1, successes=int(estimate * 50_000),
        standard_error=se, ci_lower=estimate - 0.01 if ci_lower is None else ci_lower,
        ci_upper=min(1.0, estimate + 0.01), ci_method="wilson_95",
    )


def test_monotonicity_audit_counts_and_sizes_local_decreases():
    points = [_point(1, 0.10), _point(2, 0.30), _point(3, 0.28), _point(4, 0.55)]
    audit = audit_monotonicity(points)[0]
    assert audit.violation_count == 1
    assert audit.max_decrease == pytest.approx(0.02)
    assert audit.max_decrease_at == 3
    assert audit.all_violations_within_noise is False  # 0.02 >> the stated SE


def test_monotonicity_audit_recognises_a_decrease_inside_sampling_noise():
    points = [_point(1, 0.500, se=0.05), _point(2, 0.499, se=0.05)]
    audit = audit_monotonicity(points)[0]
    assert audit.violation_count == 1
    assert audit.all_violations_within_noise is True


def test_stable_horizon_requires_the_lower_bound_to_hold_across_the_band():
    """A single lucky crossing must not be promoted to a stable horizon."""
    points = [
        _point(10, 0.70, ci_lower=0.69),
        _point(20, 0.81, ci_lower=0.805),   # crosses, but...
        _point(30, 0.78, ci_lower=0.775),   # ...falls back inside the band
        _point(40, 0.88, ci_lower=0.875),
        _point(60, 0.91, ci_lower=0.905),
        _point(80, 0.93, ci_lower=0.925),
        _point(100, 0.95, ci_lower=0.945),
    ]
    horizon = resolve_horizon(
        points, metric_key="within_tau_0.20", confidence=0.80, search_cap=100_000
    )
    assert horizon.first_crossing_n == 20        # the noisy answer
    assert horizon.stable_n == 40                # the defensible one
    assert horizon.status == HORIZON_RESOLVED
    assert horizon.stable_n != horizon.first_crossing_n


def test_horizon_reports_exceeds_cap_rather_than_inventing_a_number():
    points = [_point(n, 0.30, ci_lower=0.29) for n in (10, 100, 1_000)]
    horizon = resolve_horizon(
        points, metric_key="within_tau_0.20", confidence=0.80, search_cap=100_000
    )
    assert horizon.first_crossing_n is None
    assert horizon.stable_n is None
    assert horizon.status == HORIZON_EXCEEDS_CAP


def test_horizon_will_not_promote_a_crossing_at_the_edge_of_the_searched_range():
    """Nothing above the crossing has been evaluated, so nothing has been shown."""
    points = [_point(10, 0.50, ci_lower=0.49), _point(20, 0.95, ci_lower=0.94)]
    horizon = resolve_horizon(
        points, metric_key="within_tau_0.20", confidence=0.80, search_cap=100_000
    )
    assert horizon.first_crossing_n == 20
    assert horizon.stable_n is None
    assert horizon.status == HORIZON_EXCEEDS_CAP


def test_point_estimate_alone_never_promotes_a_horizon():
    """Estimate clears 0.80 everywhere, but the interval does not."""
    points = [_point(n, 0.81, ci_lower=0.78) for n in (10, 20, 40, 80)]
    horizon = resolve_horizon(
        points, metric_key="within_tau_0.20", confidence=0.80, search_cap=100_000
    )
    assert horizon.first_crossing_n == 10
    assert horizon.stable_n is None


def test_confirmation_grid_spans_the_band_and_probes_below():
    grid = build_confirmation_grid(100)
    assert 100 in grid
    assert min(grid) < 100          # allows the confirmed horizon to move DOWN
    assert max(grid) == pytest.approx(200, abs=1)
    assert len(grid) >= 3


def test_confirm_session_count_respects_the_draw_budget():
    shallow = confirm_session_count([36], preferred=250_000, draw_budget=6_000_000_000)
    assert shallow == 250_000

    deep = confirm_session_count([80_000], preferred=250_000, draw_budget=6_000_000_000)
    assert deep < 250_000
    assert deep * 80_000 <= 6_000_000_000

    # It reduces sessions rather than abandoning confirmation entirely.
    absurd = confirm_session_count([10_000_000], preferred=250_000, draw_budget=1_000)
    assert absurd == 40_000
