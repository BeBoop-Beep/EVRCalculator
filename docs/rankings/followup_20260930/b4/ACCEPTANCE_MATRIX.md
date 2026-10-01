# Bucket 4 acceptance matrix

| Area | Result | Evidence |
|---|---|---|
| Relational paid authority | PASS | `product_rankings_v2_service.py`; 75 focused backend tests pass |
| Old Product snapshot dependency | PASS | `_rankings_product_v2` has no lens/snapshot call |
| Chase scalar and labels | PASS | canonical helper; browser proves scalar `Chase` and no old Set labels |
| Exact Recover Cost | PASS | exact SKU + source-run composite key; 9.9% and 0.0002% fixtures visible |
| Adaptive precision | PASS | shared `formatRecoverCost`; tiny-positive screenshot |
| Paid pagination and bounds | PASS | desktop/mobile page size 25, forward/back, page 3 bound |
| Search, family, and view reset | PASS | controlled production-browser requests reset to page 1 |
| Global sort before page | PASS | Chase descending places global fixture leader `p-60` on page 1 |
| Public pagination and leakage | PASS | 25 identity-only rows; DOM text/attribute leak scan passes |
| Page-first enrichment | PASS | normal page requests carry only the 25 selected IDs |
| Best-Open interaction | PASS | pointer-open popover shows threshold, market, delta, dates/status, and unavailable MSRP |
| Entitlement boundary | PASS | Plus and anonymous fixtures exercise separate paid/public endpoints |
| Production build | PASS | `.next-build-b4closure`; 85/85 static pages generated |
| Live local Product endpoint timing | BLOCKED_RUNTIME | no local authenticated database credentials/runtime supplied |
| B1/B2/B3 behavior | N/A | no requested expansion; B4 remained Product-only |

Controlled-browser artifacts are under `evidence/`, including desktop Scores,
desktop Economics, mobile Scores, anonymous catalogue, tiny-positive Recover
Cost, and the machine-readable request/measurement record.

## Stale Product expectation reconciliation

| Old expectation | Classification | Replacement |
|---|---|---|
| `readProductRankings(target)` and per-view client state maps | OLD_IMPLEMENTATION_EXPECTATION | parameterized `readProductRankings(view, { params })` and cross-view contract invalidation |
| client-side Product search/family/sort | OLD_IMPLEMENTATION_EXPECTATION | server query parameters; filter/sort before pagination |
| separate anonymous Scores/Economics table components | OLD_IMPLEMENTATION_EXPECTATION | one identity-only `PublicTable` with locked cells |
| inline Best-Open evidence prose | OLD_IMPLEMENTATION_EXPECTATION | keyboard/pointer-accessible `BestOpenDetailsPopover` |
| legacy `ProductFamilyRankingsClient` as active Product authority | OBSOLETE_EXPECTATION | retirement contract verifies `RankingsProductLensClient` is the active lazy client |
| Card dynamic import and Set/Product-detail `publicScore` assertions | PRE_EXISTING_UNRELATED_FAILURE | unchanged; outside Bucket 4 Product Rankings scope |
| entitlement Playwright test launched through the generic Node runner | PRE_EXISTING_UNRELATED_FAILURE | dedicated controlled production-browser acceptance passes |
