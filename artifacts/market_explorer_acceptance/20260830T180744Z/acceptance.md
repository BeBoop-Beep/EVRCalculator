# Market Explorer acceptance

- Status: **FAIL**
- Git SHA: `8db74ab79140bb91f09e635d478138b9e0bfaf02`
- Mode: `preflight`
- Environment: `production-read-only`

## Checks

- **PASS** `migration_exists` — D:\EVRCalculator\supabase\migrations\20260829210512_market_explorer_filtered_card_cohorts.sql
- **PASS** `no_global_migration_backfill` — migration must not invoke an unbounded refresh
- **PASS** `empty_refresh_is_noop` — null/empty scope returns zero
- **PASS** `distinct_set_refresh_rpc` — set refresh has a distinct PostgREST name
- **PASS** `service_only_sql` — invoker functions and explicit backend-only grants
- **PASS** `benchmark_fixture_exists` — D:\EVRCalculator\backend\research\market_explorer\effort1c_interval_vs_fact_benchmark.sql
- **PASS** `benchmark_temp_only` — fixture may create session-local objects only
- **FAIL** `table:pokemon_card_variant_market_price_intervals` — required table is unavailable
- **FAIL** `rpc:get_pokemon_canonical_card_variant_authority` — RPC signature unavailable
- **FAIL** `rpc:refresh_pokemon_card_variant_market_price_intervals` — RPC signature unavailable
- **FAIL** `rpc:refresh_pokemon_card_variant_market_price_intervals_for_sets` — RPC signature unavailable
- **FAIL** `rpc:get_pokemon_market_explorer_filtered_cohort` — RPC signature unavailable
- **PASS** `near_mint_authority` — exactly one Near Mint/NM row required
- **PASS** `market_date_authority` — canonical usable Market dates
- **PASS** `pilot:celebrations` — Celebrations exists with source card data
- **PASS** `pilot:fossil` — Fossil exists with source card data
- **BLOCKED** `catalog:function_signatures` — direct PostgreSQL catalog access was not supplied
- **BLOCKED** `catalog:ambiguous_overload_absent` — direct PostgreSQL catalog access was not supplied
- **BLOCKED** `catalog:interval_indexes` — direct PostgreSQL catalog access was not supplied
- **BLOCKED** `catalog:rls_enabled` — direct PostgreSQL catalog access was not supplied
- **BLOCKED** `catalog:privileges` — direct PostgreSQL catalog access was not supplied
