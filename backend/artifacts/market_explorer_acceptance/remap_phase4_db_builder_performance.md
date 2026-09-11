# Market Explorer Remap Phase 4 — Database Builder Performance

Measured against Supabase project `zwxzxuuawalvwioadhmf` on 2026-09-11. Current approved market date was 2026-09-10; all 165 tracked sets had V2 coverage through that date, retained from 2026-06-03.

## A. Live function graph

- `preflight_pokemon_market_explorer_filtered_cards_v1` is the active bounded leaf preflight. It reads V2 daily states/current metadata, returns NULL counts when projection coverage is incomplete, is `SECURITY INVOKER`, fixes `search_path=''`, and has 5s timeout/16MB work memory.
- Legacy `preflight_pokemon_market_explorer_query` is a PL/pgSQL wrapper/older contract over the same daily authority; the application endpoint calls the filtered-cards V1 leaf.
- `get_pokemon_market_explorer_filtered_cohort_materialized_series(..., p_use_v2, ...)` is the active selector. `p_use_v2=true` reads daily V2 states; false delegates to `get_pokemon_market_explorer_filtered_cohort_v2_interval_shadow`.
- `get_pokemon_market_explorer_filtered_cohort_v2_shadow` is the full daily V2 leaf including current constituent JSON. The Phase 4 summary path uses the materialized-series selector, avoiding that giant payload.
- The V2, interval, and selector functions are stable invokers with fixed empty search paths and 300s bounded timeouts.

`p_set_ids` is interpreted as `set_id = ANY(...)`; `p_segment_ids`, Pokémon IDs, price IDs, and age IDs each use OR/`ANY` inside their predicate and AND between predicates. `p_card_ids` and `p_card_variant_ids` are independent optional intersections. `p_top_n IS NULL` selects every eligible member; only a non-NULL value activates ranking after filtering.

## B–C. Exact semantic proof

Expected membership was independently counted from approved-date daily states joined to current metadata, Sets, and Pokémon links. Actual membership came from live preflight. Missing and extra were zero in every row.

| Case | Expected/actual variants | Expected/actual sets | Status |
|---|---:|---:|---|
| legend OR radiantRare | 33 / 33 | 9 / 9 | ready |
| Pokémon 25 OR 6 | 301 / 301 | 98 / 98 | ready |
| Pitch Black OR Chaos Rising | 392 / 392 | 2 / 2 | ready |
| (legend OR radiantRare) AND (25 OR 6) | 2 / 2 | 2 / 2 | ready |
| (legend OR radiantRare) AND Intermediate | 3 / 3 | 2 / 2 | ready |
| SIR AND New | 18 / 18 | 3 / 3 | ready |
| (25 OR 6) AND Intermediate AND New | 0 / 0 | 0 / 0 | empty |
| scoped (Common OR Rare) AND (25 OR 6) AND (Obtainable OR Intermediate) AND New | 0 / 0 | 0 / 0 | empty |

This proves OR within each array and AND across arrays. Array ordering is canonicalized by application query normalization before fingerprint/cache lookup; SQL `ANY` membership is independently order-insensitive.

## D–F. One match, empty, and projection lag

`amazingRare AND Pokémon 243` resolves to exactly one variant in one set. Preflight returned count 1, set count 1, `ready`, and chain-link ready. The V2 materialized path returned that one constituent on both 2026-09-09 and 2026-09-10 with common count 1 on the latter date; no minimum-count gate exists.

The legitimate multi-axis examples above returned count 0 and typed `empty`. In contrast, the real catalog set `ME: Mega Evolution Promo` lacks projection coverage: preflight returned NULL matching counts, one missing projection set, `projection_lagging`, and count source `unavailable`. Projection lag therefore cannot masquerade as empty.

## G–J. Broad-query performance

Application-level service-role RPC timings include network/client overhead. Materialized timings cover a bounded two-approved-date summary and return no constituent JSON.

| Case | Variants | Sets | Preflight ms | V2 materialized ms |
|---|---:|---:|---:|---:|
| Global All Cards | 33,964 | 165 | 471.9 | 612.5 |
| Intermediate | 6,164 | 163 | 197.3 | 201.3 |
| New | 595 | 3 | 74.5 | 349.6 |
| Common | 10,602 | 138 | 330.2 | 386.9 |
| Rare | 5,045 | 132 | 315.2 | 342.3 |
| Pikachu (25) | 191 | 82 | 515.3 | 413.2 |
| legend OR radiantRare | 33 | 9 | 288.3 | 276.2 |
| Common AND Intermediate | 1,078 | 87 | 170.3 | 156.4 |
| Rare AND Legacy | 3,954 | 103 | 243.4 | 292.0 |
| SIR AND Intermediate AND New | 15 | 3 | 70.8 | 131.2 |

Intermediate/Common/Rare remain legitimate broad custom markets. The SIR regression remains exactly 15 variants/3 sets.

## K–M. Routing and EXPLAIN

Every current preflight reported `count_source=daily_v2`. `EXPLAIN (ANALYZE, BUFFERS)` measured Global preflight at 376.679 ms DB-internal (all cache hits) and Global two-day materialized V2 at 632.711 ms. SIR + Intermediate + New materialized V2 measured 85.454 ms. Plans were bounded function scans with no temp spill.

Coverage begins 2026-06-03. An explicit selector call for 2026-05-30 through 2026-06-02 with `p_use_v2=false` executed the interval leaf in 217.061 ms; the selector definition proves interval fallback is entered only on false. Current-window calls used true. No plan justified a new index.

## N. Indexes and migrations

None. No speculative DDL, index, timeout increase, or infrastructure expansion was made.

## O. Real build and lease evidence

A bounded real planner build for `amazingRare AND Pokémon 243` published fingerprint `d4a88c79b92ac928f74b71d56b07074ed5ac9ee16832027c9977bf5f14cbafd2`. The final cache row is `ready`, covers 2026-04-11 through the planner comparison date 2026-09-09, contains 146 trend points, and has NULL `build_token`/`build_started_at`: no orphaned lease. A fresh-process read hit persistent cache in 487.5 ms and the consecutive process-L1 read hit memory in under 0.1 ms.

## P–Q. Timeouts and security

Preflight remains bounded at 5s; cohort functions remain at 300s. Measurements are comfortably below targets, so neither was changed. All audited functions are `SECURITY INVOKER`, fixed-search-path, and executable only by `postgres` and `service_role`. The Supabase security advisor reported existing project-wide notices, but none names these fixed-path functions and Phase 4 introduced no schema/security warning.

## R–T. Integration, blockers, final status

Source commit `9edfae4f9a67672ca35057b2e7472f1c88a98660` consumes the preflight as a debounced, abortable, stale-safe UX check; Build remains summary mode and Constituents remains paged separately. Prepared resolution and the 39-filter/9-prepared Phase 3 split are unchanged.

Blockers: none. Final DB status: accepted with zero DDL and zero migration versions.
