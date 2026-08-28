import numpy as np

from backend.db.services.opening_economics_v3_service import _store_physical_distribution
from backend.domain.pokemon.opening_economics_v3 import WeightedEmpiricalMixture, build_scope


def _row(identity, price, recovered):
    return {"sealed_product_id": identity, "set_id": "set", "product_family": "box",
            "product_market_cost": price, "expected_value": 25, "pack_count": 2,
            "simulation_count": 4, "chance_to_recover_cost": recovered / 4,
            "_regenerated_recovery_count": recovered}


def _build(tmp_path, prices):
    owner = WeightedEmpiricalMixture(tmp_path)
    cache, paths = {}, {}
    vector = np.array([10., 20., 30., 40.])
    for identity, price in prices:
        paths[identity] = _store_physical_distribution(
            owner, cache, ("run", 2, 0), vector, pack_count=2
        )
    rows = [_row(identity, price, int(np.count_nonzero(vector >= price))) for identity, price in prices]
    result = build_scope(rows, paths, qs=(.25, .5, .75))
    stored = np.load(next(iter(cache.values()))[0]).copy()
    owner.cleanup()
    return result, stored, len(cache)


def test_shared_physical_cache_is_price_independent_and_order_invariant(tmp_path):
    cheap_first = [("cheap", 15), ("expensive", 35)]
    expensive_first = list(reversed(cheap_first))
    left, left_vector, left_cache_count = _build(tmp_path / "left", cheap_first)
    right, right_vector, right_cache_count = _build(tmp_path / "right", expensive_first)
    assert left_vector.tolist() == right_vector.tolist() == [10., 20., 30., 40.]
    assert left_cache_count == right_cache_count == 1
    for key in ("averageCostPerPack", "averageModelBreakEvenPerPack", "modeledReturnOnSpend",
                "meanOutcomeRetention", "chanceToRecoverCost", "valuePerPackPercentiles",
                "normalizedReturnPercentiles"):
        assert left[key] == right[key]
