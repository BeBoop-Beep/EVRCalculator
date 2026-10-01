# Bucket 6 performance report

## Historical evidence

B0 established production-build anonymous measurements and found authenticated Product/Card/browser coverage blocked. It also established that Cards is page-first and not an N+1 request per displayed card. Those historical results are not relabeled as B6 measurements.

## Source and fixture evidence

- Focused frontend command: 70 tests passed in 2.666 s TAP duration (4.640 s command wall time). This is test-suite runtime, not UI latency.
- Cache fixture: exact query reused one read; changing lens or page produced distinct reads (three total); a forced successor remained cached after a late predecessor; different access identities shared no paid value.
- Product cold-path inspection: Scores and Economics use distinct lazy paid endpoints, identity-scoped cache keys, and a 60-second cache age. Warm repeats reuse the exact response. Public mode calls only the catalogue. No additional prefetch/cache was added because no measured browser/backend evidence justified hidden work.
- Card path: one facet request plus one page request per mounted lens; search alone retains 250 ms debounce; lens, explicit filters, and paging have no debounce. Enrichment is bounded to current-page identities.

Fixture execution cannot supply p50/p95, browser render duration, proxy duration, DB duration, or production payload latency.

## Actual browser measurements

`AUTHENTICATED_BROWSER_VERIFICATION_BLOCKED`: no authorized Plus/Premium session was present. No tokens/cookies were extracted or fabricated.

`FULL_BUILD_BLOCKED_MISSING_BACKEND_API_BASE_URL`: environment check on 2026-09-30 returned `BACKEND_API_BASE_URL=UNSET`. `npm.cmd run build` compiled successfully in 53 seconds and completed lint/type checking, then failed while collecting `/sitemap.xml` with `BACKEND_API_BASE_URL must be configured in production`. Browser certification therefore could not start.

## Actual backend/DB measurements

`LIVE_CARD_DB_PERFORMANCE_BLOCKED`: `SUPABASE_URL=UNSET` and `SUPABASE_SERVICE_ROLE_KEY=UNSET`. No credential search or bypass was attempted. The focused Python command stopped during collection for that explicit configuration guard, so it is not a backend PASS.

## Findings

The only certified B6 improvements are immediate interaction feedback, warm exact-query reuse, isolated identities/queries, bounded page-first reads, local recovery, and stale-write prevention. The reported real-world latency and login flow still require an authorized production-build session and bounded read-only DB/proxy timing.
