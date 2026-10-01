# Rankings Follow-up B3 - Acceptance Matrix

Evidence key: **U** unit/contract test, **R** rendered-HTML test, **B** production-build browser run (Playwright, fixtures; desktop 1440 and mobile 390 touch).

| # | Requirement | Evidence |
|---|---|---|
| 1 | Clear All exists | R `FinancialRipHistoryLegend.render` (accessible name, pill), B |
| 2-4 | Clears all selections; Overall remains; no entity keys | U `financialRipHistoryFocus` (empty model keeps Overall), U `FinancialRipHistoryB3`, B ("no entity keys, Overall key + line remain", selector count 0, axes remain) |
| 5 | No request from Clear All | U source contract (no cache/fetch calls in handler), B (0 requests desktop and mobile) |
| 6 | Overall-only range change fetches the new range | U anchor tests, B (30D->3M and 3M->6M each 1 request with the correct range; second change proves the anchor is retained) |
| 7 | Anchor never rendered | U (no `entity_` keys / empty `series`), B (no key or line reappears) |
| 8-9 | Key body is a focus control; x is separate | R (two buttons per key, labels, order) |
| 10-12 | Focus fades others, Overall stays, click again restores | U `seriesEmphasis`, B (opacities 0.14 vs 1; Overall stays 0.72) |
| 13 | Removing the focused entity clears focus | U source contract, B |
| 14-15 | Hover focus temporary; leave restores persistent/all | U `resolveActiveFocus`, R (mouse-only handlers), B |
| 16 | Focus makes no history request | B (0 requests across focus/hover/remove) |
| 17-18 | Normal tooltip lists selected rows; focused tooltip only focused + Overall | R, U, B (16 rows -> 1 row) |
| 19-22 | Real vertical scroll; wheel doesn't change selection; 16-Set tooltip usable; touch scroll possible | R (overflow-y, contain, pan-y, bounded height), B (wheel scrolls the tooltip to the last row and not the page; pinned panel wheel; raw touch-drag scrolls the pinned panel, page unmoved) |
| 23 | No tooltip hover requests | B |
| 24-25 | Dedupe; prewarm + mount = one request | U `financialHistoryCache.test`, B (single 3-Set request) |
| 26-27 | 22-Set idle prefetch entitlement-gated and save-data-aware | U (`planCohortPrefetch`, `prewarmFinancialHistory`), U source contract |
| 28 | Cached superset serves a subset locally | U (identical rows, no refetch), B (Set add and 16-Set Era preset: 0 requests) |
| 29-30 | A range cannot satisfy another range; a Set cache cannot satisfy Era mode | U, B (Era mode issues its own `era` request) |
| 31 | Access identity change blocks paid cache reuse | U (user B / next publication / anonymous caches empty) |
| 32 | Stale older range cannot overwrite the newest | U (out-of-order resolution keeps each range's own entry), U source contract (`active` cleanup) |
| 33-34 | B1 green Sets/Eras and range buttons remain | U `FinancialRipHistoryB3` + `RankingsFollowupB1` |
| 35 | Clear All red pill | R |
| 36 | Overall cannot be removed | R (no button), U |

## Results
| Check | Result |
|---|---|
| New B3 frontend tests | 46 pass / 0 fail (cache 10, focus model 8, legend+tooltip render 9, B3 contract 10, chart contract 9) |
| Frontend focused regression set (503 tests) | 485 pass, 18 fail; **0 new** vs the B2 baseline (same 18 existing Set-detail / Playwright / panel failures) |
| Backend (rankings, redesign contract, paid boundary) | 107 passed; backend untouched by B3 |
| Production build (B7 procedure, isolated `node_modules`) | PASS, 85/85 static pages, `/Rankings` 119 kB First Load JS (was 115 kB) |
| Browser acceptance (production build, fixtures) | 48/48 checks pass (desktop 38, mobile 10 incl. 16-Set legend, pinned tooltip touch scroll, Clear All) |

Not covered live: mid-session downgrade with a request in flight (covered by unit/contract tests only), real backend latency, Era mode beyond the request/type assertion.

Screenshots: `evidence/desktop-focused.png`, `evidence/desktop-large-era-tooltip.png` (16-Set Era preset, scrollable tooltip), `evidence/desktop-overall-only.png`, `evidence/mobile-focused.png`.
