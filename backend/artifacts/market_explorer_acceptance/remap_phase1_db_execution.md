# Market Explorer Remap Phase 1 — DB execution report

## A. Production state before work

Read-only audit at `2026-09-10 20:36:19 UTC` found accepted Pokémon quality through
`2026-09-10`, V2 coverage through `2026-09-10`, V1 coverage through `2026-09-08`, and
the published Explorer snapshot at `2026-09-09`. Cache repair generation was 2.

## B. Maintained-cache audit

There were 37 maintained rows. Relative to the Explorer target `2026-09-09`: 5 were ready/current,
30 were ready/stale, and 2 were failed/retryable. Every maintained scope is covered by the 165/165
V2 projection through `2026-09-10`; none is blocked by V2 coverage. Stale rows include the
single-axis Intermediate, Premium, Recent, Established, Legacy, published rarity markets, and
most era markets. New and Global Top 10 were ready through `2026-09-09`. Global Raw and Obtainable
were failed through `2026-09-08`.

The audit query selected, for every row, fingerprint, normalized spec, status, computed bounds,
canonical target, lease timestamps/state, updated time, request count, and cache kind. All 37
classified as G (5 healthy), D (30 stale), or C (2 failed/retryable); none classified A/B/E/F.

## C. Expired/active lease findings

At initial classification, all 37 rows had absent leases: 0 active and 0 expired. The previously
observed Global Raw build had already failed and released its lease through the canonical failure
path. The claim RPC permits takeover only when status is not building or its expiry has passed;
renewal requires the matching token and an unexpired lease.

## D. Cache remediation performed

One bounded canonical recovery was attempted for Obtainable through `2026-09-09` using
`advance_one_maintained_cache`, the same planner/claim/heartbeat/fail machinery used by prewarm.
It failed after the backend PostgREST request reached an upstream 504 timeout. The planner then
called the canonical failure RPC, clearing its lease. No cache payload, fingerprint, constituent,
or computed-through value was manually changed. No other cache build was started.

## E. Post-remediation health

Post-attempt: total 37; ready/current 5; stale ready 30; failed 2; building-active 0;
building-expired 0. Obtainable remains failed at `2026-09-08`, with no lease. Bulk remediation was
not attempted because it would violate the bounded-resource posture and would not cure the
demonstrated broad-query timeout.

## F. V1/V2 coverage

V1: 165 sets, uniform `computed_through=2026-09-08`. V2: 165 sets, uniform
`computed_through=2026-09-10`. The maintained lag is downstream of healthy V2 source coverage.

## G. Watermark authority findings

The existing authoritative Explorer comparison date is
`pokemon_explore_set_value_snapshot_latest.payload_json.marketOverview.marketDate` on the row
`tcg='pokemon', scope='market'`. It was `2026-09-09`. Quality and V2 may safely be newer but do not
own the comparison chart date.

## H. Implemented comparisonAsOf contract

The preflight accepts the prepared comparison date and returns the least of it, accepted quality,
and minimum V2 coverage for the resolved scope. Application handoff: the source resolver landed in
`be8127de` queries snapshot `scope='global'`, but production uses `scope='market'`; Codex must fix
that predicate. No competing watermark table was created.

## I. Preflight architecture

`preflight_pokemon_market_explorer_query` reads only canonical current metadata, the requested
comparison date and immediately preceding accepted V2 state, sets/release dates, Pokémon links,
quality, and scope coverage. It applies the same segment function and price/release boundaries as
the production cohort RPC. It performs no ranking, chain-linking, historical scan, or JSON
constituent transport. Non-empty explicit IDs are rejected.

## J. Preflight RPC/schema changes

Added one `STABLE`, `SECURITY INVOKER` function with empty search path and a 5-second statement
timeout. Execute is revoked from PUBLIC/anon/authenticated and granted only to service_role. No
table, trigger, index, or RLS policy changed.

## K. Query-plan/performance measurements

Baseline current compound count: 564.147 ms cold, 77,310 shared hits and 221 reads. The installed
RPC measured 51.929 ms warm for the same compound shape, 53,314 shared hits and zero reads. No
index was justified or added.

## L. Preflight parity tests

At `2026-09-09`: Global All 33,963/165 sets; Intermediate 6,160/163; New 595/3;
SIR 222/22; SIR+Intermediate 155/22; SIR+Intermediate+New 15/3; SIR+IR 716/22;
Set+Intermediate 6/1; Pokémon+Intermediate 16/11; deliberately absent Pokémon 0/0.
The full canonical V2 cohort RPC independently returned 15 eligible/selected members on both
Sep 8 and Sep 9 and 15 current payload members for SIR+Intermediate+New, matching preflight.
Era scope must be resolved/intersected with tracked sets by the existing application resolver;
passing untracked set IDs correctly reports missing coverage.

## M. Empty vs no-history semantics

Zero current matches returns `EMPTY_NOW`, false membership, false history. Positive membership
without a common eligible member on the immediately preceding accepted date returns
`NO_USABLE_HISTORY`. Missing requested-scope V2 coverage returns `SOURCE_COVERAGE_MISSING`.

## N. DB migrations applied

Applied `20260910203723_market_explorer_filtered_query_preflight.sql` through Supabase migration
tooling. Post-DDL ACL/catalog verification confirmed security invoker, empty search path,
5-second timeout, and execute ACL `{postgres,service_role}`. Advisors found no finding caused by
this function; unrelated existing project advisories were not changed.

## O. Source work intentionally not touched

No frontend, API, entitlement, query normalization, Market Index math, search, screen, rarity
taxonomy, or worker source was changed in this DB workstream.

## P. Remaining DB work for Phase 2/3/5

Phase 2 search and Phase 3 filterable-vs-prepared rarity authority remain intentionally deferred.
A later prepared-market directory for Screens/Quick Markets remains a separate product contract.

## Q. Genuine blockers

Maintained cache recovery is operationally blocked by a broad-query upstream timeout despite
healthy V2 coverage. Source/ops must reduce the incremental response cost or run the worker where
its query execution can complete, while preserving one cache per process. The source watermark
snapshot predicate must change from `scope='global'` to `scope='market'`.

## R. Final production health

V2 source is healthy/current. Preflight is live, private, fast, and parity-verified. Maintained
health remains 5 current, 30 stale, 2 failed, 0 active leases, and 0 expired leases at the final
check. Obtainable is not healthy/current.
