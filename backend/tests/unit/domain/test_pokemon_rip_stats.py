import numpy as np
import pytest

from backend.domain.pokemon.rip_stats import PokemonRipStatsError, calculate_pokemon_rip_stats


def test_exact_equal_set_empirical_mixture_and_thresholds():
    result = calculate_pokemon_rip_stats([
        {"set_id": "a", "pack_cost": 5, "outcomes": np.array([0, 5, 10, 20])},
        {"set_id": "b", "pack_cost": 20, "outcomes": np.array([0, 10, 20, 100])},
    ])
    pooled = np.array([0, 5, 10, 20, 0, 10, 20, 100], dtype=float)
    retention = np.array([0, 1, 2, 4, 0, .5, 1, 5], dtype=float)
    assert result["expectedValue"] == pytest.approx(pooled.mean())
    assert result["expectedRetention"] == pytest.approx(retention.mean())
    assert result["typicalOpeningValue"] == pytest.approx(np.quantile(pooled, .5))
    assert result["p95Value"] == pytest.approx(np.quantile(pooled, .95))
    assert result["p99Value"] == pytest.approx(np.quantile(pooled, .99))
    assert result["chanceToBeatCost"] == pytest.approx(5 / 8)  # ties count
    assert result["hardLossProbability"] == pytest.approx(2 / 8)
    assert result["softLossShareGivenLoss"] == pytest.approx(1 / 3)
    assert result["expectedEntertainmentCost"] == pytest.approx(result["meanPackCost"] - result["expectedValue"])
    assert result["onePackPerSet"]["expectedEntertainmentCost"] == pytest.approx(
        result["onePackPerSet"]["totalPackCost"] - result["onePackPerSet"]["totalExpectedValue"]
    )


def test_pooled_quantiles_are_not_averages_of_per_set_quantiles():
    vectors = [np.array([0, 0, 0, 100]), np.array([10, 10, 10, 10])]
    result = calculate_pokemon_rip_stats([
        {"set_id": "a", "pack_cost": 5, "outcomes": vectors[0]},
        {"set_id": "b", "pack_cost": 20, "outcomes": vectors[1]},
    ])
    assert result["typicalOpeningValue"] != pytest.approx(np.mean([np.quantile(v, .5) for v in vectors]))
    assert result["p95Value"] != pytest.approx(np.mean([np.quantile(v, .95) for v in vectors]))
    assert result["p99Value"] != pytest.approx(np.mean([np.quantile(v, .99) for v in vectors]))


def test_unequal_counts_duplicate_sets_and_nonfinite_values_fail_closed():
    with pytest.raises(PokemonRipStatsError):
        calculate_pokemon_rip_stats([{"set_id": "a", "pack_cost": 5, "outcomes": [1]}, {"set_id": "b", "pack_cost": 5, "outcomes": [1, 2]}])
    with pytest.raises(PokemonRipStatsError):
        calculate_pokemon_rip_stats([{"set_id": "a", "pack_cost": 5, "outcomes": [1]}, {"set_id": "a", "pack_cost": 5, "outcomes": [1]}])
    with pytest.raises(PokemonRipStatsError):
        calculate_pokemon_rip_stats([{"set_id": "a", "pack_cost": 5, "outcomes": [np.nan]}])
