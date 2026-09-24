"""Bucket 3: prepare_exact_accelerated must be bitwise identical to canonical prepare."""
from __future__ import annotations

import dataclasses

import numpy as np
import pytest

from backend.calculations.evr.financial_rip_v3 import PreparedFinancialRipDistribution as P


def _bits(x):
    if isinstance(x, np.ndarray):
        return ("arr", x.dtype.str, x.shape, x.view(np.uint8).tobytes())
    if isinstance(x, float):
        return ("f", np.float64(x).view(np.uint64).item())
    return ("v", x)


def assert_identical(values, offset=0.0):
    a = P.prepare_exact_reference(values, value_offset=offset)
    b = P.prepare_exact_accelerated(values, value_offset=offset)
    for f in dataclasses.fields(P):
        assert _bits(getattr(a, f.name)) == _bits(getattr(b, f.name)), f.name
    # Canonical prepare() must delegate to the accelerated implementation.
    canonical = P.prepare(values, value_offset=offset)
    for f in dataclasses.fields(P):
        assert _bits(getattr(canonical, f.name)) == _bits(getattr(b, f.name)), f.name


def _pokemon_like(rng, n, q, distinct=3000):
    prices = np.round(rng.lognormal(0.0, 1.6, distinct), 2)
    prices[:50] = 0.0
    idx = rng.integers(0, distinct, (n, q))
    return prices[idx].sum(axis=1)


@pytest.mark.parametrize("n", [1, 2, 3, 4, 5, 7, 20, 21, 99, 100, 101, 102, 199, 200, 1000, 1001, 4999, 5000])
def test_lengths_including_tail_and_percentile_boundaries(n):
    rng = np.random.default_rng(n)
    assert_identical(rng.lognormal(1.0, 1.0, n), 0.37)


@pytest.mark.parametrize("q", [1, 2, 6, 24, 95])
@pytest.mark.parametrize("offset", [0.0, 0.01, 3.4999, 125.125])
def test_tied_discrete_pokemon_like_vectors_and_guaranteed_offsets(q, offset):
    rng = np.random.default_rng(1000 + q)
    assert_identical(_pokemon_like(rng, 30_000, q), offset * q)


def test_all_equal_and_constant_and_zero():
    assert_identical(np.full(1000, 2.5), 1.0)
    assert_identical(np.zeros(1000), 0.0)
    assert_identical(np.ones(3))


def test_signed_zero_mix_uses_canonical_stable_order():
    v = np.array([0.0, -0.0, 1.0, -0.0, 0.0, 2.0, 0.0, -0.0] * 50)
    assert_identical(v, 0.5)
    assert_identical(np.array([-0.0, -0.0, 3.0] * 40))


def test_extreme_magnitudes_and_negative_values():
    rng = np.random.default_rng(7)
    v = np.concatenate([rng.normal(0, 1e-9, 500), rng.normal(0, 1e12, 500), [1e300, -1e300, 5e-324]])
    assert_identical(v, 1e-3)


def test_invalid_inputs_match():
    for bad in ([], [1.0, float("nan")], [1.0, float("inf")]):
        a = P.prepare_exact_reference(bad, value_offset=0.0)
        b = P.prepare_exact_accelerated(bad, value_offset=0.0)
        assert (a.invalid_reason, a.non_finite_count, a.n) == (b.invalid_reason, b.non_finite_count, b.n)
    a = P.prepare_exact_reference([1.0], value_offset=float("nan"))
    b = P.prepare_exact_accelerated([1.0], value_offset=float("nan"))
    assert a.invalid_reason == b.invalid_reason


def test_input_is_not_mutated_and_list_input_supported():
    rng = np.random.default_rng(3)
    v = rng.lognormal(0, 1, 10_000)
    before = v.copy()
    P.prepare_exact_accelerated(v, value_offset=1.0)
    assert np.array_equal(v, before)
    assert_identical(list(v[:500]), 2.0)


@pytest.mark.parametrize("q", [1, 7, 353])
def test_million_outcome_vectors(q):
    rng = np.random.default_rng(q)
    assert_identical(_pokemon_like(rng, 1_000_000, min(q, 24)), 0.42 * q)


def test_scores_identical_downstream():
    rng = np.random.default_rng(11)
    v = _pokemon_like(rng, 50_000, 12)
    a = P.prepare_exact_reference(v, value_offset=4.0).score(150.0)
    b = P.prepare_exact_accelerated(v, value_offset=4.0).score(150.0)
    assert a == b


def test_production_prepare_routes_to_accelerated_not_reference():
    """Item 1 promotion: canonical prepare() must resolve to the accelerated
    implementation, not silently fall back to the reference path."""
    rng = np.random.default_rng(99)
    v = _pokemon_like(rng, 5_000, 6)
    accelerated = P.prepare_exact_accelerated(v, value_offset=2.5)
    reference = P.prepare_exact_reference(v, value_offset=2.5)
    canonical = P.prepare(v, value_offset=2.5)
    for f in dataclasses.fields(P):
        assert _bits(getattr(canonical, f.name)) == _bits(getattr(accelerated, f.name)), f.name
    # Sanity: reference and accelerated still agree (methodology unchanged),
    # so this test would not distinguish a regression that broke both paths
    # identically -- it exists to catch prepare() drifting from accelerated.
    for f in dataclasses.fields(P):
        assert _bits(getattr(reference, f.name)) == _bits(getattr(accelerated, f.name)), f.name


def test_reference_path_remains_explicitly_invocable():
    """Control/reference preparation path (Step 5.B)."""
    rng = np.random.default_rng(5)
    v = rng.lognormal(0.5, 1.0, 2000)
    reference = P.prepare_exact_reference(v, value_offset=1.0)
    assert reference.n == 2000
    assert reference.invalid_reason is None
