# Performance certification

## Historical repository measurements

B0 production-build anonymous baselines and earlier bucket reports remain historical evidence only.

## Fixture/unit measurements

- Focused B1â€“B6 suite: 70 tests, 261 ms TAP duration in the integrated worktree.
- Maintained Rankings suite: 341 tests, all passing; final run duration recorded by TAP.
- Cache fixtures prove exact-query reuse, distinct keys for lens/filter/page, forced-successor write ownership, and cross-identity isolation.
- Product uses separate Scores/Economics endpoints with exact-identity warm reuse.
- Cards remains page-first with bounded current-page enrichment and no frontend per-card request waterfall.

## Local production build

Compilation completed in 18.1 seconds. Full page generation and release-like browser startup were blocked by missing `BACKEND_API_BASE_URL`; no bundle/runtime result is promoted to a full-build pass.

## Browser, backend, and DB timings

No legitimate authenticated browser or read-only DB connection was present. Product, Card, and graph interaction latency; proxy/backend/DB spans; payload bytes; and p50/p95 are therefore BLOCKED, not inferred from fixtures.
