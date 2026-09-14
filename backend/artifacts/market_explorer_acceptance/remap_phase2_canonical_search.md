# Market Explorer Remap Phase 2 — Canonical Search Acceptance

## A. Starting SHA

`05fadb2272bc657b2df1c5a3aa28b9f4b53b5f2b` on shared `develop`, equal to `origin/develop` at start.

## B–D. Prior architecture and canonical authority

The prior Cards path performed a literal `%query%` `ILIKE` against current card metadata, while Sealed used a separate sealed-only RPC. Python merged and alphabetically sorted both result sets. Search also shared the five-per-ten-second custom Market build bucket.

Both assets now use the single service-role call `search_pokemon_market_explorer_instruments_v2` with exactly `p_query`, `p_asset`, and `p_limit`. PostgreSQL exclusively owns normalization, token-order-insensitive matching, prefix matching, Set context, collector-number behavior, fuzzy matching, relevance, cross-asset order, and the bounded result cap. Python performs no fuzzy comparisons and preserves DB order.

## E–H. Application contract and assets

The browser contract includes `asset`, `instrumentId`, `displayName`, transitional `name`/`label`, `setId`, `setName`, `imageUrl`, and useful leaf-specific display fields. Cards map collector number, rarity, edition, printing/finish, and special type. Sealed maps product family/type and variant label. Ranking internals are discarded. Invalid or mismatched rows are defensively removed, while `all` accepts both leaf assets. No Set/Era aggregate is introduced.

## I. Dedicated rate policy

Authenticated Plus discovery remains unchanged, as does Premium execution enforcement. Search now uses `instrument_search` (30 requests/10 seconds, 600/hour) rather than `custom_query` (unchanged at 5/10 seconds, 30/hour). HTTP tests prove thirty rapid searches are accepted, request 31 receives the standard typed 429 with `Retry-After`, and all five custom-query requests remain available afterward.

## J. Migration mirror

The four authoritative applied statements are mirrored in `backend/db/migrations` and `supabase/migrations`. Tests verify both trees are byte-identical and match live-ledger MD5 values after removing only the repository terminal newline. See `remap_phase2_db_search.md`.

## K. Latency evidence

DB workstream warm timings were ~59–82 ms for representative card and sealed searches, ~143 ms for `temporal forces/all`, and ~256 ms for broad two-character `ex`. The picker retains a 300 ms debounce, minimum two-character query, AbortController cancellation, stale-token protection, and a 20-result request.

## L–M. Tests and production build

- Phase 2 adapter, API entitlement, HTTP abuse, rate-policy, and migration checks: **30 passed**.
- Exact picker and related Market Explorer frontend regressions: **40 passed**.
- Broad Market Explorer/abuse selection: **440 passed, 2 pre-existing baseline failures**. The failures are the unchanged global daily-projection fixture coverage expectation and a CRLF-sensitive Phase 1 historical migration checksum; neither touches Phase 2 search.
- Next.js 15.5.15 production build: **passed**. Existing lint/cache and unavailable-local-backend fallback warnings remain non-blocking.
- `git diff --check`: passed before commit.

## N. Files changed

- canonical search service adapter
- API search-policy wiring and abuse policy
- focused backend service/API/migration tests
- four exact migration mirrors in each canonical tree
- DB handoff and this acceptance report

Unrelated concurrent Trends V2, Market root-authority, log, and capture files were excluded.

## O. Remaining caveats and manual QA

The intentionally broad two-character query is slower than normal searches. Manual preview QA should repeat the accepted matrix: Mega Dragonite in both orders and typo forms; Temporal Forces + Gastly in both orders; collector `290`; `DRAGONITE-GX`; Pokemon/Pokémon; Elite Trainer Box/ETB/Pokemon Center ETB; Booster Bundle; Set + sealed type in both orders; and `all`/`cards`/`sealed` isolation.

Nav search and Phase 3+ work were not changed.

## P. Final commit SHA

Phase 2 source implementation commit: `487e16a2a2eb6bf5523adc08114847da8c426e7c`.
