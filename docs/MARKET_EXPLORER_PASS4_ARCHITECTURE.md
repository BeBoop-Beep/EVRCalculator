# Market Explorer Pass 4 architecture

## Filtered card cohort RPC

`get_pokemon_market_explorer_filtered_cohort` is the cards-only historical execution primitive. The API resolves and validates scope, rarity and canonical Pokémon membership, then passes bounded set/card UUID arrays and validated price/release taxonomy IDs. PostgreSQL:

1. obtains the canonical daily price panel;
2. evaluates price and set-release age on each market date;
3. ranks the surviving universe per date;
4. applies Top 10 only after filtering;
5. reduces the result to basket and adjacent-date common-cohort values;
6. returns one aggregate row per date and constituent identities only for the latest date.

The existing Python chain-linking code remains authoritative. Thirty-day chunks overlap the previous observed date so a chunk boundary cannot manufacture a chain break.

The function is `SECURITY INVOKER`. Execution is revoked from `PUBLIC`, `anon`, and `authenticated`, and granted only to `service_role`. Browser clients cannot call it. No user expression or SQL fragment is accepted.

No new index is proposed. The expensive observation lookup is already served by the covering `(card_variant_id, condition_id, captured_at)` index documented in `20260826001000_market_explorer_bounded_constituents_and_covering_index.sql`; set IDs are primary-key joins, and canonical Pokémon link tables already have card/reference indexes. Price and release predicates operate on the reduced function rows, so indexing raw price or release date would not improve this function without a different materialization strategy.

## Metadata caching

The options response contains canonical taxonomy and compatibility metadata, not market results. It has a bounded 15-minute backend process cache after authentication and Plus entitlement checks. A process restart/deploy invalidates it immediately; otherwise TTL expiry rebuilds it from current authorities. Query-result caching remains a separate, entitlement-gated cache keyed by normalized fingerprint and market date. No user-specific object is stored in the metadata cache.

## Page hierarchy

The lower page is ordered:

1. Active Markets
2. Market Comparison Analysis
3. Constituents
4. Methodology

Comparison Analysis uses the same authoritative movement objects as the chart. It shows tracked value, index, tracking start, constituent count, 7D, 30D, 90D, 6M, 1Y and Since Tracking where available. The chart timeframe column is emphasized. With two or more comparable markets, the leader/laggard spread is a direct percentage-point subtraction—never a score, forecast, alpha, or recommendation.

Constituents continues to inspect exactly one active market. Selecting a market from Active Markets, Comparison Analysis, or the constituent picker updates the shared inspection identity without altering chart membership.

## Deployment requirement

The SQL migration must be applied through the repository's Supabase migration workflow before deploying the application code that calls the new RPC. Validate the function against a linked/local database, inspect `EXPLAIN (ANALYZE, BUFFERS)` for representative price and release queries, then record cold and warm production timings. The current workstation has neither a linked Supabase project nor Docker, so local application and production plan/timing verification cannot be performed here.
