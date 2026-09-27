"""Bucket 3: prepared-lifecycle engine keeps Bucket 2 results exactly and accounts for every block."""
from __future__ import annotations

import pytest

from backend.calculations.evr.best_open_price_v2_fused_batched_prepared import (
    PreparedLifecycleBatchedDualBestOpenPriceSearch as Lifecycle,
)
from backend.tests.unit.calculations.test_best_open_price_v2_bounded_batching import (
    _Harness, _base, _batched, _control, _kwargs, _strip,
)

_OVERS = [
    {},
    {"rip_current_rank": 1, "rip_benchmark": {"sealedProductId": "r", "thresholdCents": 640}},
    {"rip_current_rank": 1, "financial_current_rank": 1,
     "rip_benchmark": {"sealedProductId": "r", "thresholdCents": 777},
     "financial_benchmark": {"sealedProductId": "f", "thresholdCents": 503}},
]


def _life(harness, n, **over):
    opts = {k: over.pop(k) for k in ("initial_width", "max_width", "abandon_policy", "trace",
                                     "measure_speculative_marginal") if k in over}
    return Lifecycle(
        **_kwargs(**over), prepare_quantity=harness.single, build_block=harness.build_block,
        prepare_from_values=harness.prepare_from_values, rng_outcome_count=n, **opts,
    )


@pytest.mark.parametrize("over", _OVERS)
@pytest.mark.parametrize("policy,initial", [("none", 4), ("none", 24), ("reset", 4), ("halve", 8)])
def test_results_scores_and_order_equal_control_for_every_policy(over, policy, initial):
    control_calls = []
    expected = _control(control_calls, **over).search()
    x = _base(101)
    h = _Harness(x)
    got = _life(h, x.size, abandon_policy=policy, initial_width=initial, **dict(over)).search()
    assert _strip(got) == _strip(expected)
    assert h.score_calls == control_calls
    assert got["diagnostics"]["quantityBatchFallbacks"] == 0


def test_lifecycle_counts_are_consistent_and_speculative_q_is_never_prepared():
    x = _base(101)
    h = _Harness(x)
    trace = []
    search = _life(h, x.size, trace=trace, max_width=8)
    d = search.search()["diagnostics"]
    assert d["preparedBuilt"] == d["quantitiesConsumedFromBlocks"] == len(h.raw)
    assert d["speculativePreparationsAvoided"] == d["speculativeQuantitiesGeneratedNotConsumed"]
    assert d["preparedBuilt"] + d["speculativePreparationsAvoided"] == d["quantityBatchQuantities"]
    assert d["blocksAbandoned"] + d["blocksFullyConsumed"] == d["blocksFinalized"] == d["quantityBatchBuilds"]
    assert set(h.raw).isdisjoint(  # quantities prepared are exactly the consumed ones
        {q for e in trace if e["kind"] == "block" for q in e["planned"] if q not in e["consumed"]})
    assert d["maximumActivePreparedQuantities"] == 1
    assert d["maxRawPendingBytes"] <= 8 * x.size * 8
    assert search._pending_values == {}


def test_trace_requests_match_consumed_and_are_absent_by_default():
    x = _base(101)
    h = _Harness(x)
    trace = []
    _life(h, x.size, trace=trace).search()
    requests = [e["q"] for e in trace if e["kind"] == "request"]
    assert requests and set(requests) == set(h.raw)
    h2 = _Harness(x)
    search = _life(h2, x.size)
    assert search.trace is None
    search.search()


def test_abandon_policy_resets_ramp_and_validates_name():
    x = _base(101)
    h = _Harness(x)
    r = _life(h, x.size, abandon_policy="reset", initial_width=2, max_width=8).search()["diagnostics"]
    assert r["rampResets"] == r["blocksAbandoned"]
    with pytest.raises(ValueError):
        _life(_Harness(x), x.size, abandon_policy="bogus", initial_width=2).search()
