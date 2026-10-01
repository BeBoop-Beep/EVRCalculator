# Bucket 5 acceptance matrix

| Requirement | Result | Evidence |
|---|---|---|
| One Cards async boundary | PASS | Hub statically imports both conditional children; initial `/Rankings` stays 119 kB |
| Cards intent chunk preload | PASS | existing top-level `onIntent` loads `lensModules.cards` |
| Collector idle prewarm | PASS | entitlement/save-data gated; exact facet/row keys |
| Mount joins prewarm | PASS | one default row request maximum |
| Facets independent of rows | PASS | parallel cache requests and independent UI error state |
| Warm same-query return | PASS | zero row requests in browser fixture |
| Truthful cold loading | PASS | loading screenshot and DOM assertion; no false zero/page count |
| Global component ranks | PASS | component RPC unchanged; service tests preserve returned global rank/cohort |
| Conditional Collector enrichment | PASS | Artist-only detail batch; no Era batch |
| Chase explicit projection | PASS | `CHASE_PAGE_COLUMNS`; no page `select("*")` |
| Plus/Premium separation | PASS | normal entitlement hooks/routes retained |
| Access-loss safety | PASS | identity-scoped cache, remount key, generation guards |
| Anonymous/Base paid leakage | PASS | zero paid Card fixture requests |
| Desktop/mobile | PASS | Collector desktop/mobile and Premium Chase accepted |
| Production build | PASS | optimized compile, lint/type with existing warnings, 85/85 pages |
| Live route timing | BLOCKED_RUNTIME | no legitimate authenticated local database runtime supplied |
| Card model/rank changes | N/A | explicitly out of scope; none made |

