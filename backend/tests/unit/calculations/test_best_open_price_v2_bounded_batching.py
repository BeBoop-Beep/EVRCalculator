"""Bucket 2: bounded exact multi-q look-ahead for the fused V2 Best-Open search."""
from __future__ import annotations

from dataclasses import dataclass, field

import numpy as np
import pytest

from backend.calculations.evr.best_open_price import quantity_price_interval_cents
from backend.calculations.evr.best_open_price_v2_fused import (
    DualBestOpenPriceSearch as ControlSearch,
)
from backend.calculations.evr.best_open_price_v2_fused_batched import (
    BoundedBatchedDualBestOpenPriceSearch as BatchedSearch,
)
from backend.calculations.evr.sealed_product_distribution import (
    build_single_q_parity_distributions,
    build_stage1_product_distributions,
)
from backend.tests.unit.calculations.test_best_open_price_v2_fused import _FakeCandidate


def _base(n=257):
    return np.random.default_rng(20260919).lognormal(1.0, 0.8, n)


class _Harness:
    """Fake block/prepare plumbing around the real exact block builder."""

    def __init__(self, x, *, key="budget:p", fail=None):
        self.x = x
        self.key = key
        self.fail = fail or {}
        self.blocks = []
        self.raw = {}
        self.score_calls = []
        self.singles = []

    def build_block(self, quantities, **kwargs):
        self.blocks.append(tuple(quantities))
        if "block" in self.fail:
            raise self.fail["block"]
        built = build_single_q_parity_distributions(
            self.x, quantities=quantities, canonical_set_key=self.key,
            run_fingerprint=None, **kwargs,
        )
        if self.fail.get("wrong_set"):
            built["distributions"].pop(quantities[-1], None)
        if self.fail.get("wrong_shape"):
            built["distributions"][quantities[0]] = built["distributions"][quantities[0]][:-1].copy()
        return built

    def prepare_from_values(self, quantity, values):
        if "prepare" in self.fail:
            raise self.fail["prepare"]
        self.raw[quantity] = np.array(values, copy=True)
        pid = "wrong" if self.fail.get("identity") else "candidate"
        return _FakeCandidate(pid, quantity, self.score_calls)

    def single(self, quantity):
        self.singles.append(quantity)
        return _FakeCandidate("candidate", quantity, self.score_calls)


def _kwargs(**over):
    base = dict(
        product_id="candidate", budget_cents=1000, current_price_cents=500,
        current_quantity=2, rip_current_rank=2,
        rip_benchmark={"sealedProductId": "r", "thresholdCents": 18},
        financial_current_rank=2,
        financial_benchmark={"sealedProductId": "f", "thresholdCents": 21},
        source_authority_fingerprint="fp", expected_source_authority_fingerprint="fp",
        max_quantity_to_construct=200,
    )
    base.update(over)
    return base


def _batched(harness, n, **over):
    return BatchedSearch(
        **_kwargs(**over), prepare_quantity=harness.single,
        build_block=harness.build_block,
        prepare_from_values=harness.prepare_from_values,
        rng_outcome_count=n,
    )


def _control(calls, **over):
    return ControlSearch(
        **_kwargs(**over),
        prepare_quantity=lambda q: _FakeCandidate("candidate", q, calls),
    )


def _strip(result):
    out = {}
    for axis in ("ripResult", "financialResult"):
        r = result[axis]
        out[axis] = (r["status"], r["threshold"], r["exactness"], r["evaluationCount"],
                     r["physicalQuantitiesConstructed"], r["lowestCandidatePriceCents"])
    return out


@pytest.mark.parametrize("over", [
    {},  # both non-leaders
    {"rip_current_rank": 1, "rip_benchmark": {"sealedProductId": "r", "thresholdCents": 640}},
    {"rip_current_rank": 1, "financial_current_rank": 1,
     "rip_benchmark": {"sealedProductId": "r", "thresholdCents": 777},
     "financial_benchmark": {"sealedProductId": "f", "thresholdCents": 503}},
    {"rip_benchmark": {"sealedProductId": "r", "thresholdCents": 7},
     "financial_benchmark": {"sealedProductId": "f", "thresholdCents": 5}},
])
def test_batched_result_score_order_and_thresholds_equal_control(over):
    control_calls = []
    expected = _control(control_calls, **over).search()
    x = _base(101)
    h = _Harness(x)
    got = _batched(h, x.size, **over).search()
    assert _strip(got) == _strip(expected)
    # Exactly the same prices scored in exactly the same order.
    assert h.score_calls == control_calls
    d = got["diagnostics"]
    assert d["uniqueCandidatePricesScored"] == expected["diagnostics"]["uniqueCandidatePricesScored"]
    assert d["quantityBatchFallbacks"] == 0


def test_raw_block_vectors_are_bitwise_equal_to_independent_single_q():
    x = _base(257)
    h = _Harness(x)
    _batched(h, x.size, budget_cents=1000, current_price_cents=500).search()
    assert len(h.raw) > 5
    for quantity, values in h.raw.items():
        single = build_stage1_product_distributions(
            x, pack_counts=[quantity], canonical_set_key="budget:p", chunk_size=113,
        )["distributions"][quantity]
        np.testing.assert_array_equal(values, single)


def test_chunk_boundary_and_high_q_blocks_stay_exact():
    x = _base(97)
    h = _Harness(x)

    def small_chunks(quantities, **kwargs):
        kwargs["flat_draw_limit"] = 31
        return h.build_block(quantities, **kwargs)

    search = BatchedSearch(
        **_kwargs(budget_cents=600, current_price_cents=300, max_quantity_to_construct=120,
                  rip_benchmark={"sealedProductId": "r", "thresholdCents": 6},
                  financial_benchmark={"sealedProductId": "f", "thresholdCents": 6}),
        prepare_quantity=h.single, build_block=small_chunks,
        prepare_from_values=h.prepare_from_values, rng_outcome_count=x.size,
    )
    search.search()
    high = [q for q in h.raw if q >= 60]
    assert high
    for q in high:
        single = build_stage1_product_distributions(
            x, pack_counts=[q], canonical_set_key="budget:p", chunk_size=50,
        )["distributions"][q]
        np.testing.assert_array_equal(h.raw[q], single)


def test_blocks_are_contiguous_bounded_ramped_and_release_between_blocks():
    x = _base(101)
    h = _Harness(x)
    search = _batched(h, x.size, max_width=6, initial_width=2,
                      rip_benchmark={"sealedProductId": "r", "thresholdCents": 6},
                      financial_benchmark={"sealedProductId": "f", "thresholdCents": 6})
    result = search.search()
    d = result["diagnostics"]
    assert d["maximumActivePreparedQuantities"] == 1
    assert d["maximumResidentSharedQuantities"] == 1
    assert 1 <= d["maximumPendingBatchCandidates"] <= 6
    assert max(map(len, h.blocks)) <= 6
    assert search._pending_values == {}
    assert search._resident_candidate is None  # released at search end
    low_blocks = [b for b in h.blocks if len(b) > 1]
    for block in low_blocks:
        assert list(block) == sorted(block)
    widths = d["blockWidths"]
    assert widths[0] <= 2  # ramp starts small
    assert d["quantitiesConsumedFromBlocks"] + d["speculativeQuantitiesGeneratedNotConsumed"] == d["quantityBatchQuantities"]
    assert d["speculativeQuantitiesGeneratedNotConsumed"] >= 0


def test_unreachable_quantities_are_never_requested():
    x = _base(101)
    h = _Harness(x)
    _batched(h, x.size, max_quantity_to_construct=60,
             rip_benchmark={"sealedProductId": "r", "thresholdCents": 18},
             financial_benchmark={"sealedProductId": "f", "thresholdCents": 18}).search()
    for block in h.blocks:
        if len(block) == 1:
            continue
        for q in block:
            low, high = quantity_price_interval_cents(1000, q)
            assert low <= 1000 and high >= 1


@pytest.mark.parametrize("fail,reason", [
    ({"block": RuntimeError("boom")}, "block build failed"),
    ({"block": MemoryError("ceiling")}, "block build failed"),
    ({"wrong_set": True}, "wrong quantity set"),
    ({"wrong_shape": True}, "wrong outcome count"),
    ({"prepare": ValueError("bad")}, "prepare from block failed"),
    ({"identity": True}, "prepare from block failed"),
])
def test_any_block_or_identity_failure_falls_back_to_canonical_single_q(fail, reason):
    control_calls = []
    expected = _control(control_calls).search()
    x = _base(101)
    h = _Harness(x, fail=fail)
    got = _batched(h, x.size).search()
    assert _strip(got) == _strip(expected)
    d = got["diagnostics"]
    assert d["quantityBatchFallbacks"] == 1
    assert d["batchingDisabledAfterFallback"] is True
    assert any(reason in r for r in d["fallbackReasons"])
    assert h.singles  # canonical single-q factory was used
    assert d["singleQuantityConstructions"] == len(h.singles)


def test_memory_ceiling_refusal_falls_back_exactly():
    control_calls = []
    expected = _control(control_calls).search()
    x = _base(1000)
    h = _Harness(x)
    # A ceiling that cannot hold a workspace: the width policy collapses to 1,
    # and/or the builder refuses; either way the result is exact.
    got = _batched(h, x.size, memory_ceiling_bytes=16_100).search()
    assert _strip(got) == _strip(expected)
    assert got["diagnostics"]["maximumPendingBatchCandidates"] <= 1
    assert got["diagnostics"]["quantityBatchFallbacks"] in (0, 1)


def test_width_policy_responds_to_memory_ceiling_and_outcome_count():
    x = _base(400_000 // 100)  # small vector; ceilings below scale the policy
    per_output = x.size * 8
    h = _Harness(x)
    ceiling = per_output * 3 + 24 * 2_000_000 + 4096
    search = _batched(h, x.size, max_width=24, initial_width=24, memory_ceiling_bytes=ceiling)
    result = search.search()
    assert max(map(len, h.blocks)) <= 3
    assert result["diagnostics"]["quantityBatchFallbacks"] == 0


def test_without_block_callables_behaves_like_control():
    control_calls = []
    expected = _control(control_calls).search()
    calls = []
    got = BatchedSearch(
        **_kwargs(), prepare_quantity=lambda q: _FakeCandidate("candidate", q, calls),
    ).search()
    assert _strip(got) == _strip(expected)
    assert calls == control_calls
    assert got["diagnostics"]["quantityBatchBuilds"] == 0


def test_effective_and_legacy_draw_accounting_uses_bucket2x_definitions():
    x = _base(101)
    h = _Harness(x)
    got = _batched(h, x.size).search()
    d = got["diagnostics"]
    expected_effective = 0
    expected_legacy = 0
    for block in h.blocks:
        qs = [q for q in block if q > 1]
        if qs:
            expected_effective += x.size * max(qs)
            expected_legacy += x.size * sum(qs)
    assert d["effectiveRngDraws"] == expected_effective
    assert d["legacyEquivalentRngDraws"] == expected_legacy
    assert d["effectiveRngDraws"] <= d["legacyEquivalentRngDraws"]


@pytest.mark.parametrize("n,quantities,flat_limit", [
    (1, [1, 2, 9], 1),
    (7, [2, 3, 5, 8], 3),
    (97, [1, 4, 13, 64, 129], 31),
    (257, [2, 37, 64, 200], 101),
    (1000, [8, 9, 10, 11, 12, 13, 14, 15], 997),
    (4097, [3, 129], 2_000_000),
])
def test_boundary_carry_optimization_is_bitwise_equal_to_canonical_single_q(n, quantities, flat_limit):
    """Rows split across flat-chunk boundaries must sum exactly like SINGLE-q."""
    x = _base(n)
    batch = build_single_q_parity_distributions(
        x, quantities=quantities, canonical_set_key="budget:p", flat_draw_limit=flat_limit,
        memory_ceiling_bytes=64 * 1024 * 1024,
    )["distributions"]
    for q in quantities:
        single = build_stage1_product_distributions(
            x, pack_counts=[q], canonical_set_key="budget:p", chunk_size=max(1, n // 3),
        )["distributions"][q]
        np.testing.assert_array_equal(batch[q], single)
