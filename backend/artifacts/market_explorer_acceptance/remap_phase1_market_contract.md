# Market Explorer Remap Phase 1 — source acceptance

## A. Starting HEAD / shared-work audit

Started on shared `develop` at `84f33bde1e66828170b5a44f904b715734939e26`, one local
commit ahead of `origin/develop` (`e4bf0d15cfe50f00b092b94b565718002b666d98`). Reviewed
history after accepted checkpoint `73518ae7`. Existing Collector V6 scripts/tests, capture
artifacts, and logs were dirty and were preserved untouched.

## B. Filtered Market contract

Filter normalization retains the v3 contract and pinned fingerprints. `membershipMode=filters`
canonicalizes exactly like an omitted mode; stale `instrumentIds` have no identity or execution
effect. Multiple values remain OR within an axis and axes remain AND.

## C. Exact membership isolation

Explicit normalization requires 1–25 sorted unique leaf IDs and uses the existing distinct
explicit contract. Scope, peer filters, and ranking fields are removed. The Builder returns to
Filtered mode whenever an ordinary definition field changes, while its local Exact draft may be
retained for reopening.

## D. Ranked-view semantic boundary

`mode=all|chase` remains only as compatibility. Exact membership canonicalizes to `all`.
Top 10 is documented and implemented as post-membership ranking; Risers/Fallers remain deferred
until a timeframe contract exists. No new Composition/filter-axis semantics were added.

## E. Explorer watermark authority

The authoritative display date is the prepared Explorer publication's
`marketOverview.marketDate`, read from `pokemon_explore_set_value_snapshot_latest`. Backend custom
execution uses the minimum of that date and the asset's usable source-publication date. The
Explorer snapshot exposes `comparisonAsOf`; `/Market` continues using its existing slim contract.

## F. Prepared/custom date coherence

The planner generation and cache freshness are evaluated at the bounded comparison date. Query
fingerprints remain market-definition identities and contain no requested date. A later accepted
publication date advances the generation/computed-through without creating a second definition.

## G. Preflight design

No expensive approximation was added. The exact bounded RPC required to distinguish zero current
members from members lacking usable history is specified in `remap_phase1_db_handoff.md`.

## H. Typed outcomes

The frontend preserves `code`, HTTP `status`, `Retry-After`, and safe `message` in a typed error.
The query endpoint emits `QUERY_INVALID`, `QUERY_UNAVAILABLE`, `QUERY_BUILDING`,
`QUERY_CACHE_REFRESHING`, and `QUERY_FAILED`. HTTP 429 is mapped to `QUERY_RATE_LIMITED` when an
upstream response has no more specific code. Empty/no-history await the bounded preflight RPC.

## I. Maintained-cache source audit

Existing source reclaims expired leases through the claim RPC, does not steal active leases,
retries failed caches, deprioritizes recent failures by bounded cooldown so they cannot starve
others, detects ready rows behind the accepted market date, and defaults to one cache per worker
process. No worker redesign was needed.

## J. DB work intentionally deferred

Production state inspection/remediation and the compact preflight RPC are deferred to the DB
agent. No production database operation was performed.

## K. Tests

Focused frontend normalization/reducer and backend domain/planner tests cover stale-ID removal,
Exact isolation, distinct fingerprints, mode transitions, watermark clipping, and refreshing.
Final command results are recorded at handoff.

## L. Build

Final production frontend build result is recorded at handoff.

## M. Files changed

Frontend query normalization, Builder reducer/tests, query error propagation; backend query
normalization, planner/watermark/tests, API response mapping, Explorer snapshot metadata; these
two acceptance artifacts.

## N. Genuine blockers

`QUERY_EMPTY_NOW` versus `QUERY_NO_HISTORY` cannot be classified cheaply and reliably until the
bounded DB preflight primitive exists. This is an explicit Phase 1 allowed handoff, not an
application approximation.

## O. Commit SHA

Pending final source commit.

## P. Phase-2 readiness

Search behavior was not changed. Phase 2 can consume isolated Exact draft/spec semantics and the
typed frontend error shape without coupling search to peer-filter state.
