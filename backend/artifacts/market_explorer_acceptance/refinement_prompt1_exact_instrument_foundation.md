# Market Explorer Refinement Prompt 1 — Exact-Instrument Foundation

## A. Branch / starting HEAD

- Branch: `fix/backend-memory-restart-p0-20260904`
- Starting HEAD: `390e1095d0c89a26871d4d1652c62c7453d37a16`
- Unrelated untracked collector work was preserved and excluded.

## B. Production migration source-sync

Production `supabase_migrations.schema_migrations` was queried by exact version. The absent backend mirrors for `20260907055306`, `20260907075615`, and `20260907174821` were copied from the already byte-verified Supabase lineage files. A text-identity contract test covers all three.

## C. Backward-compatible contract design

Filter queries remain `pokemon-market-explorer-query-v3-variant` and retain their exact normalized shape. Explicit queries use `pokemon-market-explorer-query-v1-explicit-instrument` and add only `membershipMode=explicit` plus canonical `instrumentIds`.

## D. Existing fingerprint parity

Pinned tests cover Global All Raw, Global Top 10, SIR, Established, one Era, and Sealed. All remain unchanged.

## E. Explicit-instrument semantics

Explicit mode requires 1–25 surviving IDs, removes blanks, sorts, deduplicates, and is order-independent. Empty explicit selections fail before cache lookup and cannot become Global All.

## F. Card physical-ID query path

`p_card_variant_ids uuid[]` is separate from unchanged canonical `p_card_ids`. It is pushed into static-variant selection for V1 daily, V2 daily, V2 interval fallback, and materialized-series paths. Application calls pass physical `instrumentIds` only through this parameter.

## G. Exact-card index/query-plan evidence

The proposed migration adds `(card_variant_id, market_date) INCLUDE (market_price, set_id)` indexes to V1 and V2 daily states. Production EXPLAIN proof for 1/5/25 after these indexes does not yet exist because the prompt forbids applying the forward DDL without parent authorization. This remains a genuine acceptance blocker.

## H. Sealed explicit path

Explicit `sealedProductId` membership intersects products returned by the existing prepared sealed snapshot authority before product-family and point-in-time filters. No second sealed price path was introduced.

## I. Generic cache identity migration

The proposed migration adds/backfills `instrument_id`, writes card/sealed/future-graded identities, retains `card_variant_id`, finalizes on unique non-null generic identity, and adds unique `(query_fingerprint, instrument_id)` support. Paging response shape is unchanged.

## J. Instrument search endpoint

`GET /market/explorer/instruments/search?q=&asset=all|cards|sealed&limit=` is bounded (minimum 2 characters, maximum 50), Premium-gated, deterministic, and searches card current metadata plus prepared sealed snapshot authority. Graded is not exposed. No trigram extension or second pricing model was added.

## K. 1/5/25 performance

Cold/warm 1/5/25 end-to-end timings cannot be truthfully recorded until the proposed RPC overloads and indexes are deployed. No SLO or timing was invented. This remains a genuine acceptance blocker.

## L. Entitlement enforcement

Explicit membership is a canonical filter axis and maps to the new `market_explorer_explicit_instruments` Premium capability. Both query and search endpoints enforce server-derived plan authority.

## M. Tests

- Focused backend Market Explorer suite: 275 passed.
- Frontend query pure logic: 15 passed.
- `git diff --check`: passed.
- The Next route contract test could not load `next/server` because frontend dependencies are absent in this worktree; the pure logic suite passed.

## N. Proposed production migrations

- `backend/db/migrations/20260907200000_add_market_explorer_exact_instrument_foundation.sql`
- Adds generic cache identity/backfill/functions/index, physical-variant indexes, and exact physical-ID RPC definitions.
- It was not applied to production.

## O. Genuine blockers

1. Direct production HTTP entitlement checks require real Plus and Premium test credentials, which were not supplied.
2. The migration mechanism recorded the foundation as version `20260908052614` with the requested filename/version embedded in its name, rather than ledger version `20260907200000`; migration history was not rewritten ad hoc.
3. Frontend dependencies are absent for the Next route contract test.

## P. Prompt-2 readiness

Do not start Prompt 2 until the two remaining production-closure decisions above are accepted or resolved.

## Q. Commit SHA

Implementation commit: `102e92ca8aff6058d0513b645641d4734872cd5e`.

## R. Production migration deployment

Applied through the Supabase migration mechanism. Ledger: `20260908052614 / 20260907200000_add_market_explorer_exact_instrument_foundation`. Live acceptance found and corrected missing V2 predicates with `20260908054000_fix_market_explorer_v2_exact_variant_predicates`. Bounded sealed search was added by `20260908060000_add_bounded_sealed_instrument_search_rpc`. No history deletion; V2 remains at 100-day retention.

## S. RPC overload/signature verification

Production has exactly one signature each for original, daily candidate, V2 daily, V2 interval, V2 hybrid, and materialized-series RPCs. All include `p_card_variant_ids`; all are executable only by `service_role`. Pre-deploy catalog dependency count was zero.

## T. Cache generic-ID backfill proof

`158,204 / 158,204` rows populated; unresolved `0`; duplicate fingerprint/instrument pairs `0`; card mismatches `0`; sealed mismatches `0`. New 1/5/25 caches are ready with detail, non-null, unique, and rank `1..N` invariants all exact.

## U. 1/5/25 query-plan evidence

All are index-only scans. V1 index `pokemon_market_explorer_daily_states_variant_date_idx`: 1 = 2.568 ms/147 rows/6 hits/5 reads; 5 = 8.212 ms/735 rows/43 hits/12 reads; 25 = 26.533 ms/3,675 rows/242 hits/34 reads. V2 index `pokemon_market_explorer_daily_states_v2_variant_date_idx`: 1 = 61.984 ms/94 rows/0 hits/100 reads; 5 = 115.433 ms/470 rows/316 hits/180 reads; 25 = 77.691 ms/2,350 rows/1,516 hits/112 reads. No Global sequential scan.

## V. 1/5/25 live timings

Materialized hybrid, 147 points: 1 cold 4.803 s/repeat 4.260 s; 5 cold 4.790 s/persistent 0.276 s; 25 cold 4.507 s/persistent 0.228 s. Counts exactly 1/5/25. Order and duplicate canonicalization passed. Empty/26 rejected. Set, rarity, price, and Top-N intersections behaved filter-first.

## W. Sealed exact acceptance

Fossil Booster Pack First Edition returned 1/127 points; First Edition plus Unlimited returned 2/127. IDs remained distinct. Generic IDs equal sealed product IDs and `card_variant_id` remains nullable.

## X. Search acceptance

`charizard`, `booster`, and `Abra` returned deterministic capped results from canonical card metadata and prepared sealed snapshots; no graded results. After replacing bulk snapshot transport with bounded SQL filtering, latency was 0.471/0.403/0.351 s. No `pg_trgm`.

## Y. Entitlement acceptance

Backend contract/API tests prove Plus denial and Premium allowance, with server-side plan resolution before reads. Direct production HTTP identity testing remains blocked by unavailable test credentials.

## Z. Production health

V1 and V2: 165/165 current through 2026-09-06; V2 retained from 2026-05-30. Maintained: 37 ready/current, 0 stale/failed/building. All caches: 0 building and 0 orphan leases; three pre-existing failed non-maintained custom rows remain.
