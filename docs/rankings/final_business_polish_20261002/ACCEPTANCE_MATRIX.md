# Acceptance matrix

| Requirement | Evidence |
| --- | --- |
| 1D certified predecessor semantics | `financialRipHistoryModel.test.mjs` |
| Shared below-box rank/tier | `RankingsFinalBusinessPolish.contract.test.mjs` |
| Paid scorecard/cache prewarm | frontend contract tests; session-cache suite |
| Pack/Product/Chase prewarm | frontend final-polish contract test |
| Pack authority cache | backend service tests and source-identity contract |
| 151 `$56.95` preservation | final-polish regression fixture |
| independently dated Product Best-Open and pre-page sort | `test_product_rankings_v2_contract.py` |
| consolidated Overview and four-metric Trend | frontend Overview/Trend contracts |
| canonical, bounded, service-role-only history | mirrored SQL migration contract |
| B1-B6/business-review regressions | existing frontend/backend Rankings suites |

## Browser evidence

Production server smoke completed at desktop and 390×844 mobile sizes with no browser-reported page errors. The public Overview exposed the consolidated summary and all four Trend metric controls; the public Sets table exposed the canonical rank plus accessible RIP score rank/tier labels. Paid-only rows correctly remained locked without test credentials.

- `rankings-desktop.png`
- `rankings-mobile.png`
- `rankings-sets-public.png`

## Release-only checks

- Apply `20261002033311_rankings_trend_history_v1.sql` only with separate authorization.
- Capture `EXPLAIN (ANALYZE, BUFFERS)` for 22 Sets / one month and confirm the materialized shape.
- Run live read-only cold/prewarmed/warm endpoint and browser timing with legitimate credentials.
- Repeat desktop/mobile browser acceptance and archive screenshots after the RPC exists in the target database.
