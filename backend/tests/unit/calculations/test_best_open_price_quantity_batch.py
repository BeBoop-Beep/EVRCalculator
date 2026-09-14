import numpy as np
import pytest

from backend.calculations.evr.best_open_price import (
    ExactBestOpenPriceSearch,
    PreparedCanonicalCandidate,
)
from backend.calculations.evr.financial_rip_v3 import (
    PreparedFinancialRipDistribution,
    build_financial_rip_v3,
)
from backend.calculations.evr.guaranteed_component_value import add_guaranteed_components
from backend.calculations.evr.sealed_product_distribution import (
    build_single_q_parity_distributions,
    build_stage1_product_distributions,
    stage1_distribution_seed,
    single_q_parity_batch_width,
)


def _values(n=257):
    return np.random.default_rng(20260913).lognormal(1.0, 0.8, n)


@pytest.mark.parametrize("seed,n,q,chunk", [
    (1, 7, 3, 2), (2, 101, 17, 31), (99, 4097, 73, 997),
])
def test_flat_integer_rng_stream_is_shape_and_chunk_boundary_invariant(seed, n, q, chunk):
    shaped = np.random.default_rng(seed).integers(0, n, size=(n, q), dtype=np.int64).ravel()
    rng = np.random.default_rng(seed)
    pieces = [rng.integers(0, n, size=min(chunk, n * q - start), dtype=np.int64)
              for start in range(0, n * q, chunk)]
    np.testing.assert_array_equal(shaped, np.concatenate(pieces))


@pytest.mark.parametrize("n,quantities,flat_chunk", [
    (31, [1, 2, 7], 5),
    (257, [3, 8, 19], 101),
    (4097, [2, 37, 129], 997),
])
def test_batch_vectors_are_bitwise_equal_to_independent_single_q(n, quantities, flat_chunk):
    x = _values(n)
    batch = build_single_q_parity_distributions(
        x, quantities=quantities, canonical_set_key="product:a",
        flat_draw_limit=flat_chunk, memory_ceiling_bytes=8 * 1024 * 1024,
    )
    for quantity in quantities:
        single = build_stage1_product_distributions(
            x, pack_counts=[quantity], canonical_set_key="product:a", chunk_size=113,
        )["distributions"][quantity]
        np.testing.assert_array_equal(batch["distributions"][quantity], single)


def test_existing_multi_q_builder_is_not_mistaken_for_single_q_parity():
    x = _values()
    multi = build_stage1_product_distributions(
        x, pack_counts=[3, 11], canonical_set_key="product:a",
    )["distributions"]
    single = build_stage1_product_distributions(
        x, pack_counts=[3], canonical_set_key="product:a",
    )["distributions"][3]
    assert not np.array_equal(multi[3], single)
    np.testing.assert_array_equal(
        multi[11],
        build_stage1_product_distributions(
            x, pack_counts=[11], canonical_set_key="product:a",
        )["distributions"][11],
    )


def test_batch_preserves_guaranteed_component_and_financial_score_exactly():
    x = _values(20_000)
    q = 13
    batch = build_single_q_parity_distributions(
        x, quantities=[q], canonical_set_key="product:g",
    )["distributions"][q]
    single = build_stage1_product_distributions(
        x, pack_counts=[q], canonical_set_key="product:g",
    )["distributions"][q]
    batch_shifted = add_guaranteed_components(batch, 2.75 * q)
    single_shifted = add_guaranteed_components(single, 2.75 * q)
    np.testing.assert_array_equal(batch_shifted, single_shifted)
    assert build_financial_rip_v3(batch_shifted, 135.0) == build_financial_rip_v3(single_shifted, 135.0)


def test_batch_refuses_allocations_above_the_explicit_memory_ceiling():
    with pytest.raises(MemoryError, match="memory ceiling"):
        build_single_q_parity_distributions(
            _values(1000), quantities=[20, 21], canonical_set_key="a",
            memory_ceiling_bytes=16_100,
        )


def test_batch_width_auto_tunes_to_outcome_count_and_memory_ceiling():
    assert single_q_parity_batch_width(
        1_000_000, requested_width=24, maximum_quantity=4096,
    ) == 24
    assert single_q_parity_batch_width(
        2_000_000, requested_width=24, maximum_quantity=4096,
        memory_ceiling_bytes=128 * 1024 * 1024,
    ) == 8


def _candidate(product_id, quantity):
    values = np.linspace(quantity, quantity + 2, 100)
    return PreparedCanonicalCandidate(
        product_id, quantity, PreparedFinancialRipDistribution.prepare(values), 50.0, 0.5, 10.0,
        min_simulation_count=1,
    )


def test_exact_refinement_consumes_batches_in_quantity_order_without_shared_state(monkeypatch):
    prepared_batches = []

    def prepare_many(quantities):
        prepared_batches.append(list(quantities))
        return {q: _candidate("p", q) for q in quantities}

    search = ExactBestOpenPriceSearch(
        product_id="p", budget_cents=1000, current_price_cents=100,
        current_quantity=10, current_rank=2,
        benchmark={"sealedProductId": "b"}, prepare_quantity=lambda q: _candidate("p", q),
        prepare_quantities=prepare_many, quantity_batch_size=3,
        source_authority_fingerprint="x", expected_source_authority_fingerprint="x",
    )
    visited = []

    def solve(quantity):
        visited.append(quantity)
        return {"wins": True, "priceCents": 80, "quantity": quantity} if quantity == 14 else None

    monkeypatch.setattr(search, "_solve_interval", solve)
    assert search._scan_quantity_range(10, 18)["quantity"] == 14
    assert visited == [10, 11, 12, 13, 14]
    assert prepared_batches == [[10, 11, 12], [13, 14, 15]]
    assert search.max_pending_batch_candidates == 3
    assert len(search._quantities) <= search.max_cached_quantities
    other = ExactBestOpenPriceSearch(
        product_id="other", budget_cents=1000, current_price_cents=100,
        current_quantity=10, current_rank=2, benchmark={"sealedProductId": "b"},
        prepare_quantity=lambda q: _candidate("other", q),
        source_authority_fingerprint="x", expected_source_authority_fingerprint="x",
    )
    assert other._constructed_quantities == set()


def test_invalid_batch_falls_back_to_legacy_single_q_candidates(monkeypatch):
    search = ExactBestOpenPriceSearch(
        product_id="p", budget_cents=1000, current_price_cents=100,
        current_quantity=10, current_rank=2, benchmark={"sealedProductId": "b"},
        prepare_quantity=lambda q: _candidate("p", q),
        prepare_quantities=lambda quantities: {}, quantity_batch_size=2,
        source_authority_fingerprint="x", expected_source_authority_fingerprint="x",
    )
    monkeypatch.setattr(search, "_solve_interval", lambda q: (
        {"wins": True, "priceCents": 80, "quantity": q} if q == 11 else None
    ))
    assert search._scan_quantity_range(10, 12)["quantity"] == 11
    assert search.batch_fallback_count == 1


def test_seed_used_by_batch_matches_canonical_single_q_seed():
    x = _values(100)
    batch = build_single_q_parity_distributions(
        x, quantities=[2, 5], canonical_set_key="same", run_fingerprint="run",
    )
    assert batch["meta"]["seed"] == stage1_distribution_seed(
        canonical_set_key="same", outcome_count=100, run_fingerprint="run",
    )
