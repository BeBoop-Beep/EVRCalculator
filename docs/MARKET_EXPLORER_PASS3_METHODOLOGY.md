# Market Explorer Pass 3 methodology

This note records the evidence and definitions behind the Pass 3 research dimensions. These markets use the existing chain-linked/common-cohort index; Pass 3 changes constituent universes, not index mathematics.

## Data authority audit (2026-08-29)

- **Pokémon membership:** `pokemon_reference.id` is the stable subject key. Membership is the many-to-many link `pokemon_card_desirability_links.pokemon_reference_id -> pokemon_reference.id`, with `pokemon_canonical_card_id` identifying the card. The audit found 1,025 references, 17,244 links, 17,109 linked cards, and 125 multi-subject cards. Display-name matching is not a query authority.
- **Release age:** `sets.release_date`. Of 210 sets, 174 had release dates and 36 did not. Missing dates are excluded from release-age markets rather than inferred from price history.
- **Card prices:** canonical card daily constituent/history readers. Current eligible distribution (19,847 cards): minimum $0.01, P25 $0.23, median $0.88, P75 $7.45, P90 $39.19, P95 $93.29, maximum $4,999.99.
- **Sealed prices:** canonical sealed daily snapshots. Current eligible distribution (391 products): minimum $2.16, P25 $58.47, median $190.51, P75 $447.74, P90 $1,099.99, P95 $2,463.87, maximum $18,750.
- **Rarity/family compatibility:** canonical card rarity and sealed taxonomy membership, summarized as segment-to-set ID maps. Pokémon compatibility is summarized independently as Pokémon-to-set IDs; the client intersects maps and the server remains authoritative.

The audit is reproducible with `python -m backend.scripts.audit_market_explorer_pass3`. It is read-only and prints no credentials.

## Price segments

Cards and sealed use separate fixed bands:

| Asset | Obtainable | Intermediate | Premium | Current counts |
| --- | --- | --- | --- | --- |
| Cards | under $10 | $10 to under $100 | $100+ | 15,499 / 3,426 / 922 |
| Sealed | under $100 | $100 to under $500 | $500+ | 132 / 174 / 85 |

Fixed bands were selected over rolling percentiles. They retain understandable dollar meaning and do not silently redefine “Premium” as the catalogue changes. The empirical counts show useful non-empty strata despite extreme right-tail outliers. Membership is recalculated from each observation date's canonical price, before optional Top-N ranking; today's classification is never projected backward.

## Release-age cohorts

Cards and sealed share definitions based on elapsed calendar days between `sets.release_date` and the observation date:

- **New:** 0–180 days
- **Recent:** 181–730 days
- **Established:** 731–1,825 days
- **Legacy:** more than 1,825 days

The current dated-set counts were 3 / 10 / 24 / 137. The Legacy cohort is necessary because combining older releases into Established would obscure most catalogue history. Cohorts move as time passes; they are not stamped from today's age.

## Screens V1

Screens are registry definitions and resolve to canonical prepared markets or serializable builder specs:

- **Rarity Leaders:** prepared card-rarity markets, descending 30-day index return.
- **Sealed Format Leaders:** prepared sealed-family markets, descending 30-day index return.
- **Momentum Leaders:** eligible non-parent prepared markets, descending trailing 30-day index return.
- **Largest Drawdowns:** eligible non-parent prepared markets, ascending `(current index / since-tracking high) - 1`.
- **Obtainable / Intermediate / Premium Market:** card price-tier builder templates using point-in-time membership.
- **New Release / Established Market:** release-age builder templates using observation-date age.
- **Top 10 in Selected Set:** Premium builder handoff that retains selected scope, filters first, and ranks that date's constituents by price.

Momentum is descriptive trailing performance and drawdown is distance from an observed high. Neither is a forecast, valuation, or recommendation. Empty/missing prepared data is omitted rather than replaced with fabricated values.

## Benchmarks and Collector Favorites

A **Benchmark** is a stable persistent comparison reference. A **Screen** is a maintained research shortcut. Top-10 discovery is therefore a Screen/builder workflow, not a generic Benchmark. Raw Cards and Sealed remain parent active markets; the existing Per-Set Chase Market retains its distinct published methodology.

Collector Favorites is deferred as a historical benchmark. The repository has a current canonical appeal/subject model, but no proven point-in-time history of appeal-ranked cohort membership. Backfilling today's favorites through old prices would introduce look-ahead bias. Individual Pokémon markets ship because their identity membership is stable; appeal score is not treated as market performance.

## Entitlement and transport

Basic receives only the existing redacted discovery shell. Plus may run one ordinary axis (scope, rarity/family, price segment, or release age). Pokémon alone, multiple axes, and arbitrary ranked composition require Premium. The shared backend evaluator enforces these rules; UI locks are presentation only. Compatibility metadata is compact maps, not a materialized permutation table, and contains no historical paid series.
