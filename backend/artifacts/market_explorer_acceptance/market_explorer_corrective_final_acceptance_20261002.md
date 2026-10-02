# Market Explorer corrective final acceptance — 2026-10-02

## Verdict

**INCOMPLETE — do not merge or deploy.** The production catalog-search blocker is resolved and the public live matrix passes, but this workstation has no authorized Index+ browser session. The auth-gated Activity, Inspect, constituent paging, and Builder scenarios therefore remain unproven live. Per the acceptance rule, this is not a complete pass.

No production write, migration application/reapplication, Activity rebuild, merge, or application deployment was performed by this acceptance run.

## Source and migration correction

- Branch: `fix/market-explorer-corrective-final-acceptance-20261002`
- Remote head received at continuation: `b0af781f8156c276993824e705a9dcbe8c7ee2cb`
- Installed production migration identity supplied by the operator: `20261002224218_market_explorer_catalog_search_v2_paging`
- Source paths now match that identity in both migration trees.
- Both copies use `latest_market_date` / alias `md`; the invalid `current_date` CTE identifier is absent.
- SHA-256 parity: `4B0CC1035D6E365549D8F7DBFAC35A9C7CD4DE10A8954E4E6510CE64FF5B6C5F` for both files.
- No second migration was created and the installed migration was not reapplied.

## Narrow acceptance fix

The first six-viewport run found a real code defect: default canonical initialization replaced the historical Raw + Sealed workspace with Raw only. The corrected path resolves Raw and Sealed as two independent public V2 reads (empty comparison context), preserving enumerable generation metadata without treating the baseline pair as a user-added entitled comparison. Anonymous constituent prefetch is suppressed, so the page does not issue known-to-fail auth-gated reads before inspection.

## Verification

- Focused frontend component/contract slice: **84/84 passed**.
- Migration source contract: **3/3 passed**.
- Live public Playwright matrix: **6/6 passed in 22.5 s**.
- Optimized Next production build: **PASS** (compiled in 73 s; existing lint warnings only).
- Required viewports: `1728x1000`, `1440x900`, `1024x768`, `768x1024`, `390x844`, `844x390`.
- Screenshots: Cards and Sealed page-2 grouped search receipts for all six viewports under `corrective_final_live_20261002/`.
- Network receipts: matching `*-network.json` files; 48/48 Explorer requests returned HTTP 200, 71–382 ms.
- Console: zero unexpected errors. Each anonymous session produced the expected `/api/auth/me` HTTP 401 probe, recorded separately and not classified as an application error.

Representative warm live receipt (`1728x1000`):

| Route | Status | Elapsed |
|---|---:|---:|
| asset options, Cards | 200 | 194 ms |
| prepared Raw | 200 | 367 ms |
| prepared Sealed | 200 | 382 ms |
| Cards `prismatic`, page 1 | 200 | 108 ms |
| Cards `prismatic`, continuation | 200 | 82 ms |
| asset options, Sealed | 200 | 81 ms |
| Sealed `prismatic`, page 1 | 200 | 96 ms |
| Sealed `prismatic`, continuation | 200 | 93 ms |

Additional direct live receipts after warmup:

- Top Sealed, limit 10: HTTP 200, 10 rows, 201 ms.
- Worst Sealed, limit 10: HTTP 200, 10 rows, 66 ms.
- Cards `charizard`, limit 12: HTTP 200, 233 ms.
- Cards `pikachu`, limit 12: HTTP 200, 80 ms.

The first post-migration Cards `prismatic` request took 24.4 s while processes/upstream connections were cold; subsequent browser requests were 96–108 ms. This is classified as cold process/network settlement, not a persistent DB or catalog defect. The Next development server's first route compilation took about 121 s; warm navigation was about 152 ms.

## Required scenario ledger

`PASS (live)` means exercised against the live read authority. `PASS (source/component)` is supporting evidence only and does not satisfy the user's live gate.

| # | Scenario | Result |
|---:|---|---|
| 1 | Raw + Sealed initial markets | **PASS (live, 6/6 viewports)** |
| 2 | Add Prismatic Cards | **UNPROVEN live — requires entitled comparison session** |
| 3 | Prismatic loads without timeout under healthy upstream | **PASS (live read path)**; page-1 96–108 ms warm |
| 4 | Prismatic chip inspection + focus | **UNPROVEN live — auth session unavailable**; component contract passes |
| 5 | Activity available for focused supported market | **UNPROVEN live — auth session unavailable**; serving authority was not rebuilt |
| 6 | Enter/exit Activity without losing Index workspace | **UNPROVEN live — auth session unavailable**; component contract passes |
| 7 | Raw parent Inspect | **UNPROVEN live — auth session unavailable**; V2 composition contract passes |
| 8 | Sealed parent Inspect | **UNPROVEN live — auth session unavailable**; V2 composition contract passes |
| 9 | Raw/Sealed constituent pagination | **UNPROVEN live — endpoint requires auth**; paging contracts pass |
| 10 | No gap after constituent LT | **UNPROVEN live**; intrinsic-width component contract passes |
| 11 | 1Y fills actual available history | **UNPROVEN live**; short-history domain contract passes |
| 12 | Prismatic Cards grouped priced search + continuation | **PASS (live, 6/6)**; 12 → 24 rows |
| 13 | Prismatic Sealed grouped priced search + continuation | **PASS (live, 6/6)**; 12 → 24 rows |
| 14 | Top Sealed: 10 | **PASS (live backend)**; browser surface not re-exercised |
| 15 | Worst Sealed: 10 | **PASS (live backend)**; browser surface not re-exercised |
| 16 | Generic pills carry asset suffixes | **UNPROVEN live**; source/component contract only |
| 17 | Builder controls and secondary styling | **UNPROVEN live — Premium UI unavailable**; component contract only |
| 18 | Tooltip includes all authoritative values at/before date | **UNPROVEN live**; chart contract only |
| 19 | No unexpected 5xx | **PASS for public live matrix: 0/48** |
| 20 | No console errors | **PASS for public live matrix**; only expected anonymous auth probes |

## Classification

| Class | Finding |
|---|---|
| Code defect | Raw-only default initialization; fixed narrowly and verified across all six viewports. |
| Upstream outage | None during the successful matrix. Earlier local `ECONNREFUSED` occurred because the local FastAPI process had exited; rerun after restart was clean. |
| Legitimate unavailable data | None encountered in the public scenarios. Auth-gated reads are not labeled unavailable data. |
| Expected dev cold compile | First `/Market/Explorer` compile about 121 s; warm navigation about 152 ms. |
| Acceptance environment gap | No authorized Index+ browser token/session was available, blocking truthful live proof of scenarios 2, 4–11, and 16–18. |

## Exact recommendation

Do **not** merge or deploy yet. Provide an authorized, non-production-mutating Index+ acceptance session, rerun scenarios 2, 4–11, and 16–18 across the required desktop/mobile viewports, and require zero unexpected 5xx/console errors. If those live checks pass, the corrected migration identity, public search/read path, focused tests, and optimized build are ready for merge review. Do not reapply migration `20261002224218`, rebuild Activity authority, or alter production data.
