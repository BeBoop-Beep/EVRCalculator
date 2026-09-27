# Market Explorer backend contract handoff — 2026-09-26

## DB integration seams

- Explorer leaf discovery is `GET /market/explorer/leaves/search`. Its only DB authority is
  `search_pokemon_market_explorer_instruments_v2`, isolated as `SEARCH_RPC` in
  `market_explorer_instrument_search.py`. An additive replacement RPC requires one service-layer edit.
- Search rows are normalized by `_canonical_item`. Newly published `market_price`, `market_date`, card
  identity/variant fields, and sealed family/type/variant/container fields plug in there without extra reads.
- V2 directory normalization prefers a DB-published `comparison_as_of`. Legacy rows temporarily fall back
  to their authoritative history/source end date in `normalize_directory_row`; resolution and same-watermark
  validation are isolated in `resolve_surface_comparison_as_of`.
- Sealed Quick Markets require no new route or math. Rows such as `sealed-quick:obtainable` and
  `sealed-quick:global-top10` pass through the generic V2 directory, comparison, and constituent adapters.
- `top-performers` and `worst-performers` are registered beside the existing four screen keys. The existing
  `get_pokemon_market_explorer_prepared_screen_v1` RPC owns ranking; Python only validates and normalizes rows.

## Revalidate after DB promotion

1. Cards and sealed leaf searches return physical leaves only, preserve DB order, and publish fresh
   `market_price`/`market_date` plus optional metadata without N+1 enrichment.
2. Every drawable V2 market in the serving generation publishes the same explicit `comparison_as_of`; then
   remove the documented legacy fallback.
3. No prepared history point is later than the published comparison watermark.
4. Both Sealed Quick keys appear with `asset=sealed`, `scope_kind=quick`, history, and constituents.
5. Top/Worst screen calls work for cards, sealed, and an omitted asset at limits 10 and 25, with one serving
   generation and one comparison watermark.
6. Graded leaf discovery remains `INSUFFICIENT_AUTHORITY` until a real graded search authority is promoted.
