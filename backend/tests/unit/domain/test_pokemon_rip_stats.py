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


def test_zero_loss_uses_canonical_resilience_defaults():
    result = calculate_pokemon_rip_stats([
        {"set_id": "a", "pack_cost": 5, "outcomes": [5, 6, 10]},
        {"set_id": "b", "pack_cost": 10, "outcomes": [10, 11, 20]},
    ])
    assert result["averageRetentionGivenLoss"] == 1.0
    assert result["softLossShareGivenLoss"] == 1.0
    assert result["hardLossProbability"] == 0.0


def test_pooled_median_is_not_the_mean_of_set_medians():
    """The mean-of-medians regression guard.

    A fixture chosen so the two answers CANNOT coincide. Set "a" is tightly
    clustered, set "b" is long-tailed; their individual medians are 10 and 100,
    whose mean is 55 - a value the pooled population never approaches, because
    pooling puts six of the eight outcomes at or below 20.

    Median is nonlinear, so averaging per-set medians is not an approximation of
    the pooled median, it is a different statistic. This is the arithmetic that
    produced the $1.92 figure in production analysis while the canonical pooled
    P50 was $1.84.
    """
    sets = [
        {"set_id": "a", "pack_cost": 5, "outcomes": np.array([0, 5, 15, 20])},
        {"set_id": "b", "pack_cost": 20, "outcomes": np.array([0, 10, 190, 400])},
    ]
    result = calculate_pokemon_rip_stats(sets)

    mean_of_medians = float(np.mean([np.median(item["outcomes"]) for item in sets]))
    pooled = np.concatenate([np.asarray(item["outcomes"], dtype=float) for item in sets])

    assert mean_of_medians == pytest.approx(55.0)
    assert result["typicalOpeningValue"] == pytest.approx(np.quantile(pooled, .5))
    assert result["typicalOpeningValue"] == pytest.approx(12.5)
    assert result["typicalOpeningValue"] != pytest.approx(mean_of_medians)


def test_sample_count_does_not_change_a_sets_weight():
    """Equal-set weighting is structural, not incidental.

    Unequal artifact sizes are refused outright rather than silently letting the
    larger artifact dominate the mixture, which is the failure mode that would
    make a set's influence depend on how many outcomes happened to be simulated.
    """
    with pytest.raises(PokemonRipStatsError, match="equal outcome counts"):
        calculate_pokemon_rip_stats([
            {"set_id": "a", "pack_cost": 5, "outcomes": np.array([0, 5, 10, 20])},
            {"set_id": "b", "pack_cost": 20, "outcomes": np.array([0, 10])},
        ])


def test_spend_weighted_headlines_differ_from_equal_weighted_legacy_fields():
    """`modeledReturnOnSpend` is sum(EV)/sum(cost), NOT the mean of per-set ratios.

    The fixture prices the two sets differently on purpose so the two
    definitions cannot agree; a reader that swapped one for the other would
    silently change the published headline.
    """
    result = calculate_pokemon_rip_stats([
        {"set_id": "a", "pack_cost": 5, "outcomes": np.array([0, 5, 10, 20])},
        {"set_id": "b", "pack_cost": 20, "outcomes": np.array([0, 10, 20, 100])},
    ])
    ev_a, ev_b = 8.75, 32.5
    total_cost, total_ev = 25.0, ev_a + ev_b

    assert result["modeledReturnOnSpend"] == pytest.approx(total_ev / total_cost)
    assert result["entertainmentCostShare"] == pytest.approx(1 - total_ev / total_cost)
    # Legacy equal-weighted fields keep their original meaning and their value.
    assert result["expectedRetention"] == pytest.approx(np.mean([ev_a / 5, ev_b / 20]))
    assert result["expectedRetention"] != pytest.approx(result["modeledReturnOnSpend"])
    assert result["expectedEntertainmentCostRatio"] == pytest.approx(1 - result["expectedRetention"])


def test_full_quantile_ladder_comes_from_the_exact_pooled_population():
    result = calculate_pokemon_rip_stats([
        {"set_id": "a", "pack_cost": 5, "outcomes": np.arange(0, 100, dtype=float)},
        {"set_id": "b", "pack_cost": 10, "outcomes": np.arange(50, 150, dtype=float)},
    ])
    pooled = np.concatenate([np.arange(0, 100, dtype=float), np.arange(50, 150, dtype=float)])
    retention = np.concatenate([np.arange(0, 100, dtype=float) / 5, np.arange(50, 150, dtype=float) / 10])
    for key, q in (("p05Value", .05), ("p25Value", .25), ("p75Value", .75)):
        assert result[key] == pytest.approx(np.quantile(pooled, q))
    for key, q in (("p05Retention", .05), ("p25Retention", .25), ("p75Retention", .75)):
        assert result[key] == pytest.approx(np.quantile(retention, q))
    # Legacy percentiles are unchanged by the ladder extension.
    assert result["p95Value"] == pytest.approx(np.quantile(pooled, .95))
    assert result["p99Value"] == pytest.approx(np.quantile(pooled, .99))
    assert result["typicalRetention"] == pytest.approx(np.quantile(retention, .5))


def test_contract_version_moves_but_methodology_and_weighting_do_not():
    """The v2 bump marks a wider payload, not a different calculation.

    A consumer needs to distinguish a snapshot carrying `openingEconomics` from
    one published before it existed. That is a contract change. The mixture is
    still exact and empirical and sets are still equally weighted, so asserting
    a methodology or weighting change would misreport how the numbers were
    produced.
    """
    from backend.domain.pokemon import rip_stats

    assert rip_stats.POKEMON_RIP_STATS_CONTRACT_VERSION == "pokemon-rip-stats-v2"
    assert rip_stats.POKEMON_RIP_STATS_METHODOLOGY_VERSION == "exact_empirical_mixture_v1"
    assert rip_stats.POKEMON_RIP_STATS_WEIGHTING_VERSION == "equal-set-empirical-v1"
