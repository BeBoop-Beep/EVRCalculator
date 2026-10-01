# Bucket 3 acceptance matrix

| Requirement | Status | Evidence |
| --- | --- | --- |
| R15 preserve public/paid boundary | PASS (source + fixture) | Public preview remains allowlisted and contains no detailed `products`; B1 contracts pass. Live DB check is BLOCKED. |
| R23 Set expands directly to exact named Products | PASS | Desktop/mobile render `row.products` with no `FamilyRow` or tree glyph; focused UI contracts pass. |
| R24 each Product has its own economics | PASS | Exact simulation row is joined by product ID + calculation run; fixture asserts cost, EV/pack, return, recovery, entertainment cost, and dates independently. |
| R25 same-family variants remain separate | PASS | Two ETBs in one family produce `p1` and `p2` with deliberately different pack counts, costs, EV/pack, recovery, and Best-Open values. |
| R26 Set aggregates/model weighting unchanged | PASS | Fixture asserts the original Set cost, EV/pack, return, recovery, and entertainment values byte/numerically; `familyEconomics` construction is unchanged. |
| Exact entertainment cost | PASS | Existing model formula `(price - EV) / pack_count` is applied only to exact inputs; missing exact evidence returns null. |
| Best-Open exactness | PASS | Same exact Best-Open row supplies sealed-product price, comparison, gaps, status, and date. No averaging. |
| B2 Set artwork | PASS | Parent still renders logo, symbol fallback, and initials fallback; focused B2/B3 tests pass; no per-row artwork request. |
| B1 Era/Set public rankings | PASS | Focused public-access contract suite passes. |
| B1 public Product catalogue | PASS | Focused contract confirms independent alphabetical catalogue remains score-free. |
| B2 score presentation | PASS | Focused B2 presentation contracts pass. |
| Product score/reference | DEFERRED | Unchanged by B3: `B4_PENDING_PRODUCT_SCORE_REFERENCE`. |
| Query shape | PASS (fixture) | Six batched calls for one detailed request; no N+1 loop. |
| Live exact-SKU data | BLOCKED | No authorized live DB credentials were available; no bypass attempted. |
| Production build | BLOCKED (environment) | Optimized compilation succeeded in 102s and lint/type checks completed; page-data collection failed because `BACKEND_API_BASE_URL` was not configured. |
| Browser smoke | DEFERRED | `BUILD_DEFERRED_DUE_TO_ACTIVE_PARALLEL_WORK`; a shared-workspace build began after this build started, so no retry/server was launched. |

Provisional code verdict pending final build record: `B3_CODE_READY_FOR_REVIEW`.
