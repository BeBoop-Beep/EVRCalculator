# Bucket 4 implementation

Product Rankings now use a publication-bound relational read from
`budget_product_ranking_latest` / `budget_product_ranking_rows`, joined to
`sealed_products` and `sets`. The paid endpoints no longer obtain identity or
Chase from `pokemon_explore_rankings_snapshot_latest.productFamilyRankings`.

Both paid views and the public catalogue accept `page`, `page_size` (maximum
100), `search`, and `family`; paid views also accept `sort` and `direction`.
Filtering and sorting precede paging, while the canonical Full Market rank is
preserved. The browser receives only the requested page.

Scores expose scalar `chaseScore`, calculated by the existing canonical
`chase_accessibility_overall_score` helper, plus inherited `collectorAppeal`.
Economics validates exact evidence by `(sealed_product_id,
source_calculation_run_id)` and batches simulation and Best-Open reads.

No schema migration, scoring change, publication change, or Best-Open
methodology change was made.

Closure testing found and fixed two Product-only presentation regressions. A
stale Scores contract is now discarded when switching to Economics, preventing
the incompatible table from flashing. The Best-Open cell now sits above the
stretched row-link overlay, so its information trigger accepts pointer input.

The controlled production-browser harness lives at
`frontend/.perf-audit/rankings-b4-product-certification.mjs`. It covers Plus
Scores/Economics, anonymous catalogue, desktop/mobile pagination, search,
family, view reset, global sort-before-page, exact/tiny Recover Cost,
Best-Open details, delayed responses, and public leakage.
