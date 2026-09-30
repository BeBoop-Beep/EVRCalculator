# Bucket 4 implementation

Starting commit: `885dedbff3dc5307abda946ca28646ee13d7e722`.

Branch: `fix/rankings-product-reference-bestopen-b4-20260930`.

## Changes

- Replaced the invalid Product use of `benchmark_presentation()` with an explicit absolute-versus-Benchmark response contract.
- Preserved current absolute V12 values on their `0–100` scale and added a publication-driven future Benchmark path.
- Added a persistent, non-sortable Product Overall reference strip with truthful pending-publication behavior.
- Moved Scores/Economics into `AnalyticsTableShell` through a reusable toolbar slot; family controls, query, and local sort state remain independent.
- Replaced permanently stacked Best-Open gap copy with one clean threshold and a shared exact-SKU detail popover.
- Added the exact Best-Open market observation/date to the Product economics projection without another query.
- Reused the popover for B3 desktop and mobile exact-SKU rows.
- Kept MSRP unavailable; no source, migration, API, or fabricated fallback was added.

## Security and query behavior

The public catalogue flow remains independent and alphabetical. Public mode never invokes either paid Product reader and renders ordinary locked cells. The reference strip exposes no numeric protected data in public mode.

No per-row fetch was introduced. Scores and Economics retain separate session-cache keys. The existing client test proves repeated reads reuse their respective cache: one Scores request and one Economics request. Best-Open remains a single batched map read for Economics.

## Verification record

- Backend focused service suite: 15/15 passed with fixture-backed clients and placeholder local Supabase initialization values; no network call.
- Backend paid-boundary suite: collection BLOCKED because the local Python environment lacks `fastapi`.
- Focused B1–B4 frontend contracts: 42/42 passed.
- Product client cache: 1/1 passed.
- Live database verification: `LIVE_PRODUCT_REFERENCE_VERIFICATION_BLOCKED`; authorized credentials were not present and no bypass was attempted.
- Production build/browser: `FULL_BUILD_BLOCKED_MISSING_BACKEND_API_BASE_URL`. No URL was invented. Process inspection showed no active heavy worker, but the required configuration was absent, so no browser server or timing run was started.

No Product benchmark was published, no scoring/model formula changed, and no MSRP was sourced externally.
