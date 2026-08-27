import math

import numpy as np
import pytest

from backend.domain.pokemon.opening_economics_v3 import (
    OpeningEconomicsV3Error, WeightedEmpiricalMixture, aggregate_scalars,
    assign_hierarchical_weights, normalize_product,
)


def product(pid, set_id="a", family="loose", price=60, ev=30, packs=6, recovery=.2):
    return {"sealed_product_id": pid, "set_id": set_id, "product_family": family,
            "product_market_cost": price, "expected_value": ev, "pack_count": packs,
            "chance_to_recover_cost": recovery}


def test_product_normalization():
    row = normalize_product(product("p"))
    assert row["cost_per_pack"] == 10
    assert row["expected_value_per_pack"] == 5
    assert row["entertainment_cost_per_pack"] == 5
    assert row["modeled_return_ratio"] == .5


def test_stage2_count_must_agree_and_complete_ev_is_divided_once():
    row = product("etb", price=90, ev=45, packs=9)
    row.update(random_pack_count=9, guaranteed_component_market_value=18)
    assert normalize_product(row)["expected_value_per_pack"] == 5
    row["random_pack_count"] = 8
    with pytest.raises(OpeningEconomicsV3Error, match="pack-count mismatch"):
        normalize_product(row)


def test_hierarchy_balances_sets_families_and_duplicate_skus():
    rows = [product("a-l"), product("a-e1", family="etb"), product("a-e2", family="etb"),
            product("b-l", set_id="b"), product("b-e", set_id="b", family="etb")]
    weighted = assign_hierarchical_weights(rows)
    by_id = {row["sealed_product_id"]: row["weight"] for row in weighted}
    assert by_id == {"a-l": .25, "a-e1": .125, "a-e2": .125, "b-l": .25, "b-e": .25}
    assert math.isclose(sum(row["weight"] for row in weighted if row["set_id"] == "a"), .5)
    assert math.isclose(sum(row["weight"] for row in weighted if row["set_id"] == "b"), .5)


def test_weighted_inverse_ecdf_and_cleanup(tmp_path):
    directory = tmp_path / "mix"
    with WeightedEmpiricalMixture(directory) as mixture:
        mixture.add(np.array([1, 2, 9]), weight=.5, cost_per_pack=2)
        mixture.add(np.array([3, 4]), weight=.5, cost_per_pack=4)
        # Brute-force atoms: .5/3 each at 1,2,9 and .5/2 each at 3,4.
        assert mixture.quantile(.05) == 1
        assert mixture.quantile(.50) == 3
        assert mixture.quantile(.95) == 9
        assert mixture.quantile(.50, normalized=True) == 1
    assert list(directory.glob("*.npy")) == []


def test_ratio_of_weighted_means_is_not_mean_ratio():
    metrics = aggregate_scalars([product("cheap", price=10, ev=8, packs=1),
                                 product("dear", price=100, ev=20, packs=1)])
    assert metrics["modeledReturnOnSpend"] == pytest.approx(28 / 110)
    assert metrics["meanOutcomeRetention"] == pytest.approx(.5)
    assert metrics["modeledReturnOnSpend"] != metrics["meanOutcomeRetention"]
