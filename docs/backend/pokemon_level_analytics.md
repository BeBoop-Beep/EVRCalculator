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

Windows use the latest valid observation at or before their inclusive-calendar
target (7D subtracts 6 days, 30D subtracts 29, then 90/180/365 days). A named
window is unavailable when tracking does not reach its target. `SinceTracking`
is the explicit first-to-latest comparison and is never relabeled as a partial
long window.

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
