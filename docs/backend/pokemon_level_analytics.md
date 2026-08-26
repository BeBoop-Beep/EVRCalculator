# Pokemon-level analytics computational contracts

## Market

The Raw Card Basket is the sum of `pokemon_set_value_daily_history` rows whose
`value_scope` is `standard` for every public-analytics-eligible,
opening-simulation-supported set released by the observation date. The Chase
Card Basket uses the same cohort and the `top10` scope. The detailed legacy
top-chase history is not an aggregate index source. Neither basket is market
capitalization.

Both normalized indexes start at 100 on the first date with complete required
cohort coverage. For adjacent valid dates, only set IDs present on both dates
enter the return: `current_common_value / previous_common_value - 1`. The prior
index is multiplied by one plus that return. An entering set is present in the
current dollar basket but cannot manufacture appreciation on entry; exits are
symmetrical.

Windows use the latest valid observation at or before their TRUE ELAPSED
target, resolved by the single helper `resolve_market_window_target`: 1D
subtracts 1 day, 7D subtracts 7, 30D subtracts 30, then 90 / 180 / 365. Ending
2026-08-25 the targets are 2026-08-24, 2026-08-18, 2026-07-26, 2026-05-27,
2026-02-26 and 2025-08-25. A named window is unavailable when tracking does not
reach its target, except 6M and 1Y, which may report the series' first
available observation and flag `isSinceFirstAvailable`. `SinceTracking` is the
explicit first-to-latest comparison and is never relabeled as a partial long
window.

### Comparison-window contract versions

`MARKET_COMPARISON_WINDOW_CONTRACT_VERSION` names the interpretation of the
fixed-window targets, and the semantics change with the string.

| Version | Interpretation | 7D ending 2026-08-25 | 30D |
| --- | --- | --- | --- |
| `common_observation_domain_v4` (retired) | Inclusive day COUNT: `end - (days - 1)`, so 7D spanned six elapsed days | 2026-08-19 | 2026-07-27 |
| `true_elapsed_lookback_v5` (current) | True elapsed lookback: `end - days` | 2026-08-18 | 2026-07-26 |

The v4 formula lived only in `build_comparison_windows`; the family-window
resolver already subtracted the full day count, so the same label named two
different spans in one publication. Both now call one resolver.

### Timeframe semantics presented to a reader

`familyChanges` — each market's OWN history — is what every user-facing
timeframe control reads, including "All", which therefore reconciles with that
market's published index level: an index of 105.87 reports All ≈ +5.87%.
`changes` — the shared comparable domain across the compared markets — is still
published for explicit cross-market analysis, but must be named "Since
Comparable Start" / "Comparable Period" wherever it is surfaced, never "All"
and never "Since Tracking".

## Pokemon RIP Stats

The experiment selects one eligible supported set uniformly, then opens one
pack from that set's exact persisted simulation artifact. V1 requires identical
outcome counts, making the concatenated empirical distribution exactly
equal-set weighted. Dollar quantiles use the pooled outcomes `X`; retention
quantiles use each outcome divided by its own set's pack cost `X / C_i`.
Per-set quantiles are never averaged.

A tie beats cost (`X >= C_i`). Loss is retention below 1, hard loss is below
0.50, and soft loss is `[0.50, 1)`. Unconditional expected loss is
`mean(max(C_i-X, 0))`. Entertainment Cost is purchase price minus modeled gross
market value, without fees or clamping; its population ratio is
`1 - expectedRetention`. The one-pack-per-set summary is a transparent sum,
not the expected value of the random-one-pack experiment.

Exact aggregate history begins only when every cohort member has a validated
exact artifact. Older per-set summaries cannot be used to fabricate P50, P95,
or P99. This layer publishes economics and disclosures, not a Pokemon RIP
score. Set-level Overall RIP and Financial RIP remain ranking concepts.

Publication uses two sequential artifact passes. Metadata and equal outcome
counts are validated before allocation. Pass 1 copies one decoded set at a time
into a single aggregate `float64` dollar buffer, then computes dollar metrics
and in-place quantiles. Pass 2 reloads one artifact at a time and overwrites the
same slices with per-set retention. No list retains decoded set vectors, and no
second full-population NumPy buffer is allocated. Temporary storage is bounded
to one decoded set vector plus per-set Boolean/quantile workspace.
