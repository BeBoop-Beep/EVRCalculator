# Bucket 3 implementation and evidence

## Scope and result

Starting point: `01a5da604f610ac56271d2513987ad4c791ad1f3` on local branch `fix/rankings-exact-sku-economics-b3-20260930`.

The paid Set Pack Economics expansion now renders `Set -> exact named Product` directly on desktop and mobile. The previous visible family aggregate level and tree glyph are removed. Set parents retain the B2 logo, symbol, and initials fallback. Product links continue to use `sealedProductId`.

The backend adds one bounded, batched read from `simulation_sealed_product_results`, keyed by the exact sealed-product IDs and calculation-run IDs already published by Best-Open. Existing Set/family aggregate construction is untouched. Exact rows use only exact evidence; unavailable exact simulation evidence yields null metrics rather than family means.

## Traced pre-change path

`read_pack_economics()` read the latest RIP stats snapshot for Set/family economics, a batched Set artwork projection, the latest Best-Open pointer and rows, and a batched sealed-product name projection. It retained exact identity and Best-Open data inside family groups but discarded exact simulation economics. `SetPackMetrics.jsx` then rendered Set, generic family, and Product levels; Product rows showed Best-Open but no exact economics.

The exact values existed in `simulation_sealed_product_results` at the calculation run named by each Best-Open row. No dedicated stored exact entertainment-cost column exists; its established exact formula and inputs do.

## Invariance and safety

- Set aggregate fields are still copied directly from the same opening-economics snapshot.
- `familyEconomics` remains in the response for internal compatibility/weighting but is not a visible row.
- No RIP model, publication, migration, Product score, Product benchmark, or public endpoint was changed.
- Public preview remains a separate allowlisted response and contains no exact product objects.
- Missing exact evidence is explicitly unavailable; exact current market and Best-Open fields can remain present because they belong to that same SKU.

## Query and fixture measurements

The two-product detailed fixture returns one Set and two exact Product rows. Its reader records six total database calls: latest opening snapshot, Set artwork batch, Best-Open pointer, Best-Open rows batch, sealed-product identity batch, and exact simulation results batch. There is no query inside a Product loop.

Response-size before/after was not certified because the historical implementation did not expose comparable exact-product economics and no live authorized payload was available. No speculative number is reported.

## Verification

- Backend focused suite: 14/14 passed using syntactically valid local placeholder Supabase credentials; all reads are fixture-backed and no network/database call occurred.
- Focused B1/B2/B3 frontend contracts: 22/22 passed.
- Legacy `EraAndPackEconomicsTables.contract.test.mjs`: 7/16 passed. Both B3-touched exact-product tests pass; nine unrelated historical assertions remain stale against approved B1/B2 behavior. The B3 family-row assertion was reconciled to the new exact-product hierarchy without weakening its layout/access intent.
- Production build was started only after the process check showed no competing heavy worker. It compiled successfully in 102 seconds and passed lint/type checking (with pre-existing warnings), then failed during page-data collection because `BACKEND_API_BASE_URL` was not configured. Another build in the shared workspace began after this build started and remained active, so no competing retry or browser server was launched. Browser smoke is `BUILD_DEFERRED_DUE_TO_ACTIVE_PARALLEL_WORK`.

No authorized live database credentials were present in the isolated worktree or process environment. Live row-count/data verification is therefore `BLOCKED`; source tracing and fixture verification are not promoted to live PASS.
