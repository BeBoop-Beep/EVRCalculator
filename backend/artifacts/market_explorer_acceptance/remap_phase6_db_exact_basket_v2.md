# Market Explorer Remap Phase 6 — DB Exact Basket V2

Status: `MARKET_EXPLORER_REMAP_PHASE6_DB_COMPLETE`

The authoritative live RPC is `get_pokemon_market_explorer_explicit_basket_series_v2(p_instruments jsonb, p_start_date date, p_end_date date)`. It accepts 1–25 physical Card and Sealed Product leaves identified by `(asset, instrumentId)`, deduplicates and orders qualified identity, rejects unknown/non-leaf identities, and models exactly one physical unit per selected leaf.

Current state is resolved at one coherent `basket_as_of`. `ready`, `stale`, and `unavailable` are distinct; unavailable value is null, never zero. DB-provided current constituents own prices, quantity-one semantics, value shares, metadata, and as-of date. Historical rows publish `common_instrument_count`, `common_current_value`, and `common_previous_value` for the existing application chain-link builder; raw `basket_value` changes are not returns.

Canonical search remains `search_pokemon_market_explorer_instruments_v2`. The application must not use the retained `_unfiltered_phase2` function. New exact definitions use `pokemon-market-explorer-query-v2-qualified-explicit-instrument`; existing V1 cache definitions remain immutable and readable. Cards-only cache asset is `cards`, Sealed-only is `sealed`, and cross-asset is `mixed`. The accepted service/methodology lineage is `pokemon-market-explorer-exact-basket-v2` / `pokemon-qualified-leaf-one-unit-v1`.

Live acceptance covered 1 Card, 1 Sealed, 2 Cards, 2 Sealed, mixed 1+1, mixed 5+5, and mixed 20+5. The 25-leaf mixed basket returned 25 unique current constituents, $5,681.83, zero direct-source sum difference, and shares totaling approximately 100%. Representative execution ranged from roughly 5 ms for one leaf to 25 ms for 25 mixed leaves.

The four authoritative ledger migrations are:

- `20260911211011_market_explorer_phase6_exact_basket_v2_contract` — MD5 `49f8184f49c9edface89cb12983686c8`
- `20260911211033_market_explorer_phase6_search_exact_eligibility` — MD5 `ad8084a3f9ee4fd26d16ce32dcd0a537`
- `20260911211130_market_explorer_phase6_preserve_stale_exact_basket_state` — MD5 `35a28f3e34fbe111103018fede255388`
- `20260911211254_market_explorer_phase6_separate_leaf_identity_from_price_state` — MD5 `fa2cb59a708700fcfe37b379bc56eda3`

They are mirrored verbatim in both canonical migration trees and were not reapplied.
