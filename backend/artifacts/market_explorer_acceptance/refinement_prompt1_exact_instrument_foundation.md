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

1. Forward migration deployment was not authorized.
2. Consequently, post-index production EXPLAIN evidence and real cold/warm 1/5/25 acceptance timings are unavailable.
3. Frontend dependencies are absent for the Next route contract test.

## P. Prompt-2 readiness

Not ready to start Prompt 2. Prompt 1 requires DB-side review/deployment followed by plan and performance acceptance.

## Q. Commit SHA

Recorded in the final handoff after the scoped implementation commit is created.
