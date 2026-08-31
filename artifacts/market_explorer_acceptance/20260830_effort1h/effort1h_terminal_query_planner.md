# Effort 1H — terminal query planner and persistent custom cache

Status: code and forward migration ready for deployment review; production DDL not applied.

## A–C. Branch, current path, and L1 audit

- Branch at implementation: `fix/public-rankings-entitlement-regression`.
- Existing request path was HTTP authentication -> V3 normalization -> server-side entitlement -> abuse control -> five-minute process cache -> Cards/Sealed engine -> unchanged response projection.
- Existing L1 was 300 seconds / 128 entries and correctly sat behind authorization, but its key did not carry every methodology version. It is retained as the planner-owned L1 with LRU capacity and deep-copy isolation.
- Timeframe is presentation slicing and is absent from the backend query request, so it is correctly excluded from semantic identity.

## D–G. MarketSpec, fingerprint, and prepared compatibility

- The existing V3 `normalize_query_spec` remains the one canonical MarketSpec for Cards and Sealed. It sorts/deduplicates IDs, collapses null/empty, drops Top N for all-mode, and retains every membership/mathematics axis.
- Fingerprint envelope version: `market-explorer-fingerprint-v1`.
- SHA-256 inputs: normalized spec, query contract version, asset-specific service version, and asset-specific instrument-methodology version.
- Golden vector: `2cb8862bc86ab03be481ae12f163838a5c9a6371ffc5613cbac03d27b139541d`.
- An explicit exact-fingerprint prepared registry runs before both caches.
- Current prepared Cards markets remain intentionally unregistered: their methodology says canonical Near Mint raw-card set baskets, not the accepted variant/physical-instrument contract.
- Current prepared Sealed overview also remains intentionally unregistered: read-only comparison found 127 points on both paths but a maximum index difference of `6.158905316266342`, current values `105.51146700733617` vs `109.66557978345641`, and 139 vs 359 current constituents. It must not masquerade as exact equivalence.
- When a future publisher carries the exact semantic versions and complete query response contract, it can register its loader without changing the planner.

## H–I. L2 schema and JSON decision

- Migration: `supabase/migrations/20260831034744_add_market_explorer_query_cache.sql`.
- One unique row per versioned fingerprint, with normalized spec, status, semantic watermarks, one JSONB result, current summary, future promotion kind, and bounded build lease.
- Representative 140-point / 211-constituent payload: 18,467 bytes.
- Local JSON parse median: 0.0795 ms. Child-row materialization alone was 0.0065 ms, but a child design would add a relational table, joins/aggregation, and multi-row transport without enabling a required point-query feature. One-row JSONB wins on terminal read simplicity and payload size; a daily append rewrite is trivial at this scale.

## J–M. Planner, lease, incremental refresh, and repairs

Execution order is exact prepared -> L1 -> fresh L2 -> stale incremental -> novel engine -> token-owned publication.

- Atomic `INSERT ... ON CONFLICT ... DO UPDATE` claim uses the unique fingerprint.
- Active leases cannot be stolen; expired leases can be reclaimed.
- Followers briefly re-read and never launch a duplicate build while an active lease remains.
- Publication requires matching `build_token`, `building` status, and an unexpired lease.
- Failures release the row to `failed`; a valid computed response still returns when cache publication fails.
- Normal staleness queries `[D_prev, D_new]`, uses `D_prev` as the chain anchor, drops the duplicate, rescales new index points to the cached anchor, appends every missed date, recomputes full-series movements, and replaces current summary/constituents.
- A stale status represents historical repair and forces full lazy rebuild rather than append.
- Operator hook: `python -m backend.scripts.maintain_market_explorer_query_cache --invalidate-from YYYY-MM-DD --commit`, after repaired interval publication succeeds and before that repair is declared usable.

## N–P. Cards, Sealed, and entitlement proof

- Cards miss dispatches only to the accepted variant interval engine; its physical-role and identity tests remain green.
- Sealed uses the same planner/fingerprint/lease/cache abstraction but dispatches to the existing sealed-product engine and retains `sealedProductId` identity.
- The API still normalizes then authorizes before calling the planner. Basic cannot reach a cached Plus/Premium result; Plus cannot reach ranked/compound Premium results. The cache is backend-only and never makes an entitlement decision.

## Q–R. Migration and exact ACL

- RLS is enabled.
- Table: `REVOKE ALL` from PUBLIC, anon, authenticated, and service_role, followed only by `SELECT, INSERT, UPDATE, DELETE` to service_role.
- No `TRUNCATE`, `REFERENCES`, or `TRIGGER` grant.
- All four helper RPCs are `SECURITY INVOKER`, fixed-search-path, revoked from PUBLIC/anon/authenticated/service_role, then granted execute only to service_role.

## S. Tests

- Relevant backend suites: 219 passed.
- Frontend normalization and authenticated proxy contracts: 20 passed.
- Coverage includes normalization, golden fingerprints/version rotation, prepared exact/near equivalence, planner ordering, L1/L2, one/multi-date refresh, historical repair, build contention, unavailable migration fallback, publication failure, Cards/Sealed identity, entitlements, RLS/ACL, lease reclaim, and token-owned publication.

## T. Benchmark table

Representative local planner/cache overhead (100 samples unless noted):

| Path | Median ms | Min ms | Max ms | Scope |
|---|---:|---:|---:|---|
| prepared registry | 0.9017 | 0.8756 | 19.3933 | in-process, realistic payload |
| L1 | 0.9045 | 0.8773 | 1.0501 | in-process, realistic payload |
| L2 | 1.3544 | 1.3189 | 1.7103 | repository simulated; excludes network |
| incremental merge | 2.2915 | 2.2238 | 2.8273 | repository simulated; excludes one-date DB query |
| novel planner overhead | 0.9003 | 0.8799 | 1.0713 | excludes accepted interval computation |

No production L2 timing is claimed before deployment. A five-sample existing full Cards service run measured `2506.859, 643.951, 574.277, 573.703, 622.490` ms (median 622.490 ms); this includes existing scope/name/metadata PostgREST reads, while the accepted interval RPC itself remains at the previously measured 42.607–153.624 ms direct-DB medians. The planner adds about 0.9 ms and does not complicate that interval engine.

## U–Y. Files, writes, deployment, blocker, and preserved work

Changed implementation files are the canonical query domain, API route, planner service, migration, maintenance/benchmark scripts, and focused tests. Exact paths are in the commit.

Production writes performed: none. Read-only verification returned:

- cache table: absent;
- migration `20260831034744`: not applied;
- interval rows: 18,957.

Deployment sequence:

1. Review the exact migration and security tests.
2. Obtain explicit production-DDL authorization.
3. Apply `20260831034744_add_market_explorer_query_cache.sql` forward-only.
4. Verify RLS, exact ACL, four function signatures/`SECURITY INVOKER`, unique constraint, and lease indexes.
5. Run claim/publish/stale-token/expired-lease smoke tests with a disposable fingerprint.
6. Deploy the backend planner code (code-first is also safe because absent L2 fails open to valid novel computation).
7. Verify prepared/L1/L2/novel diagnostics and response parity.
8. Leave cache population lazy; do not backfill all markets or synchronously refresh them in scrape publication.

Remaining production blocker: explicit authorization to apply the reviewed migration. Prepared hits additionally require a future methodologically compatible prepared publisher; that does not block L1/L2/novel deployment.

Effort 2 UI TODO remains unchanged and unstarted: Clear Graph, zero-series state, separate Builder Clear, variant-aware labels, visible editions/printings, Active Markets, Constituents, Market Comparison Analysis, Methodology, and constituent-before-analysis ordering.
