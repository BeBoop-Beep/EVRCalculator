# Trend contract

`get_pokemon_rankings_trend_history_v1` accepts at most 22 Set/Era entities and a bounded date interval. It returns all four metrics in one narrow response, so changing Metric is local and causes no history request.

- Financial RIP: `pokemon_financial_rip_history_rows_v1`; its certified absolute value, rank, cohort size, and Overall reference remain unchanged.
- Expected Value / Pack: canonical `pokemon_rip_stats_v3` published snapshot payload, Set `averageModelBreakEvenPerPack`; Era is the equal-Set mean; Overall is the published global value.
- Chance to Beat Pack: the canonical snapshot-set `calculation_run_id` joined to `simulation_run_summary.prob_profit`; Era is the equal-Set mean; Overall is published `packEconomics.chanceToBeatCost`.
- Chance to Recover Cost: canonical snapshot Set `chanceToRecoverCost`; Era is the equal-Set mean; Overall is the published global value.

Chance to Beat Pack is not Chance to Recover Cost. The former is linked run-summary profit probability; the latter is the hierarchical Product-opening recovery probability.

For duplicate publication dates, the RPC selects one snapshot by latest `published_at`, then deterministic `id`. It filters contract `pokemon-rip-stats-v3`, methodology `hierarchical_product_per_pack_empirical_v1`, and weighting `equal-set_equal-family_equal-sku-v1`. No scoring/model code runs.

`1D` means the latest two available certified observation dates. It never invents or interpolates yesterday. `7D` remains latest date plus six calendar days, preserving publication gaps. With one observation, the chart renders that point and reports the missing predecessor truthfully.
