import math

import numpy as np
import pytest

from backend.db.services.opening_economics_v3_service import _normalize_preserving_recovery

from backend.domain.pokemon.opening_economics_v3 import (
    OpeningEconomicsV3Error, WeightedEmpiricalMixture, aggregate_scalars,
    assign_hierarchical_weights, normalize_product, persisted_recovery_count,
    percentile_key,
)


def product(pid, set_id="a", family="loose", price=60, ev=30, packs=6, recovery=.2):
    return {"sealed_product_id": pid, "set_id": set_id, "product_family": family,
            "product_market_cost": price, "expected_value": ev, "pack_count": packs,
            "chance_to_recover_cost": recovery, "simulation_count": 10,
            "_regenerated_recovery_count": round(recovery * 10)}


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


@pytest.mark.parametrize("packs", [1, 6, 9, 11, 18, 36])
def test_recovery_boundary_is_identical_before_and_after_pack_normalization(tmp_path, packs):
    price = 99.0
    vector = np.array([0.0, price - 1e-9, price, price, price + 1e-9])
    per_pack = vector / packs
    mixture = WeightedEmpiricalMixture(tmp_path / str(packs))
    mixture.add(per_pack, weight=1, cost_per_pack=price / packs)
    try:
        assert np.count_nonzero(vector >= price) == 3
        assert np.count_nonzero(per_pack >= price / packs) == 3
        assert mixture.recovery_probability() == pytest.approx(3 / 5, abs=1e-15)
    finally:
        mixture.cleanup()


def test_persisted_probability_must_encode_an_exact_integer_count():
    assert persisted_recovery_count({"simulation_count": 1_000_000,
                                     "chance_to_recover_cost": "0.073499"}) == 73_499
    with pytest.raises(OpeningEconomicsV3Error, match="not an exact count"):
        persisted_recovery_count({"simulation_count": 1_000_000,
                                  "chance_to_recover_cost": "0.0734991"})


def test_shared_distribution_uses_each_skus_own_price(tmp_path):
    mixture = WeightedEmpiricalMixture(tmp_path)
    mixture.add(np.array([1.0, 2.0, 3.0, 4.0]), weight=1.0, cost_per_pack=2.0)
    path, count = mixture.components[0].path, mixture.components[0].count
    second = WeightedEmpiricalMixture(tmp_path)
    second.add_path(path, count=count, weight=1.0, cost_per_pack=3.0)
    try:
        assert mixture.recovery_probability() == .75
        assert second.recovery_probability() == .5
    finally:
        second.cleanup(); mixture.cleanup()


def test_production_has_no_data_fitted_recovery_tolerance():
    from backend.domain.pokemon import opening_economics_v3
    source = open(opening_economics_v3.__file__, encoding="utf-8").read()
    assert "abs_tol=2e-5" not in source


def test_percentile_keys_are_stable_for_all_integer_percentiles():
    assert [percentile_key(i / 100) for i in range(1, 100)] == [f"p{i:02d}" for i in range(1, 100)]


def test_weighted_exact_counts_match_independent_ecdf(tmp_path):
    rows = [product("a", price=2, ev=1, packs=1, recovery=.75),
            product("b", price=6, ev=2, packs=1, recovery=.5)]
    rows[0].update(simulation_count=4, _regenerated_recovery_count=3)
    rows[1].update(simulation_count=4, _regenerated_recovery_count=2)
    mixture = WeightedEmpiricalMixture(tmp_path)
    mixture.add(np.array([1., 2., 2., 3.]), weight=.5, cost_per_pack=2.)
    mixture.add(np.array([5., 5., 6., 7.]), weight=.5, cost_per_pack=6.)
    try:
        assert aggregate_scalars(rows)["chanceToRecoverCost"] == .625
        assert mixture.recovery_probability() == pytest.approx(.625, abs=1e-15)
    finally:
        mixture.cleanup()


def test_normalization_pins_only_observations_moved_across_break_even():
    # 122.24 / 11 has a different rounding history from an outcome assembled
    # by summing binary floats, which was the production incident.
    price, packs = 122.24, 11
    below = np.nextafter(price, -np.inf)
    vector = np.array([below, price, np.nextafter(price, np.inf)])
    normalized = _normalize_preserving_recovery(vector, packs=packs, price=price)
    assert (normalized >= price / packs).tolist() == (vector >= price).tolist()
