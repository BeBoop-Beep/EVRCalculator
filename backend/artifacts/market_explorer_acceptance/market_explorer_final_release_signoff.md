# Market Explorer Final Release Sign-off

QA date: 2026-09-07 (America/Phoenix)  
Production application: `https://www.inthedex.io/Market/Explorer`

## A. Main/deployed SHA

- Final `origin/main`: `3d9b42a058efde5e2afc863481cc4c4fdf85ba1a`.
- Production web deployment: `3d9b42a058efde5e2afc863481cc4c4fdf85ba1a` (Vercel production bundle deployment `dpl_8icCyYamegAXiJwpmgQzHZzKyQiw`).
- Production runtime/cron checkout: clean detached checkout at `3d9b42a058efde5e2afc863481cc4c4fdf85ba1a`.
- `git merge-base --is-ancestor 390e1095d0c89a26871d4d1652c62c7453d37a16 3d9b42a058efde5e2afc863481cc4c4fdf85ba1a` exited 0.

## B. Production health

The release-gate audit reported the latest approved market date as 2026-09-06. V1 and V2 each cover 165/165 authority sets through that date. The dynamically discovered maintained-cache count is 37: 37 ready/current, 0 failed, 0 stale, 0 building, and no orphan-lease alert. The production crontab retains publication (`15 6 * * *`), prewarm (`5-59/15 * * * *`), and health (`10-59/15 * * * *`) jobs, all pointed at the exact release checkout.

## C. Desktop QA

Authenticated Chromium 151 was exercised at 1440 px against production using an existing Index Plus account. The Explorer, Builder, Screens, Benchmarks, chart, Active Markets, Constituents, comparison analysis, and trailing Methodology sections rendered without page or console errors. The warmed page load was approximately 2.52 s (the first cold session was approximately 15.2 s). No page-level horizontal overflow was observed.

The initial browser pass exposed a real correctness defect: a Global/All-rarities/All query was incorrectly deduplicated to the older prepared Raw Card Market (22 sets/4,360 cards as of September 5) instead of current query authority. The prepared-resolution logic now keeps Global card and card-segment queries on the current query path while retaining sealed prepared resolution. Production retest returned 165 resolved sets and 33,961 eligible variants as of September 6.

## D. Builder QA

All Raw, one-set (Gym Challenge), one-rarity (Special Illustration Rare), and one release-age cohort (Established) were built through the real UI. Era, price, Top N, and Pokemon controls rendered and retained their draft selection; Plus entitlement correctly gated compound/custom/Pokemon cases. Editing the draft did not mutate active markets. Clear Graph removed active markets while preserving the draft; Builder Clear reset the draft without rebuilding active markets. The ordinary single-axis SIR and Established builds succeeded with current counts of 222 and 5,870 respectively.

## E. Screens QA

All card Screen controls were click-tested: Rarity Leaders, Momentum Leaders, Largest Drawdowns, Obtainable, Intermediate, Premium, New Release, Established, and Top 10 in Selected Set. Established successfully handed its semantic spec to the Builder and built. Equivalent Screen/Builder specifications use the same semantic fingerprint. The selected-set Top 10 control identifies its set requirement and Premium lock; it did not issue a query or silently become a Global Top 10 without a selected set.

## F. Benchmark QA

Per-Set Chase joined the active comparison as the published benchmark without a query rebuild or draft mutation. Its identity, explanation, chart series, and fingerprint are distinct from a custom Global Top 10 query.

## G. Comparison QA

Raw, Sealed, and Per-Set Chase were displayed together. The comparison table showed the three visible series. Hiding one series updated the visible comparison set while leaving the market active; hide/show operations issued no market request. Hide all produced the intentional empty-chart state and Show all restored the series.

## H. Constituents QA

Switching the inspected market changed the constituent title/context without changing chart visibility. Rows rendered rank, card/product, set, rarity/family, price, and change. Global constituents used the separate paged endpoint: page 1 requested `afterRank: 0, limit: 100` (about 57,986 bytes), page 2 requested `afterRank: 100, limit: 100` (about 57,869 bytes), and the UI then reported 33,761 remaining. The full 33,961-member universe was not retained in the summary response.

## I. Variant/vintage QA

Production rows were checked across the requested vintage families (Base, Fossil, Jungle, Team Rocket, Gym, Neo, e-Card/EX) and a modern set, with the Gym Challenge UI evidence retained. Physical identity is contextual: First Edition/Unlimited and Holo/Reverse Holo/Non-Holo labels appear where needed; modern rows are not indiscriminately overloaded. Gym Challenge displayed separate `1ST EDITION · HOLO` and `UNLIMITED · HOLO` Blaine's Charizard rows. The previously invalid `______'s Chansey (DUPLICATE)` row was absent.

## J. Entitlement QA

The existing Plus account could build an ordinary single non-asset axis. Pokemon-only, compound ordinary axes, and custom Top N remained configurable in the draft but the Build action clearly displayed the Index Premium lock and stayed disabled. A direct authenticated POST for Global Top 10 returned HTTP 403 with `MARKET_EXPLORER_PLAN_REQUIRED`, `requiredPlan: premium`, and `requiredFeature: market_explorer_custom_ranked`; the backend could not be bypassed. No plan or user data was altered. Consequently, a successful Global Top 10 was not launched under this Plus account; its required locked behavior, eligible-universe draft context, and clear distinction from Per-Set Chase were verified.

## K. Network QA

- Global summary POST: HTTP 200, `responseMode: summary`, about 15,265 bytes, fingerprint `66426743…`, and no `currentConstituents` payload.
- Maintained/prepared markets loaded cache-first from the published snapshot.
- Constituents used distinct paged POST requests.
- Single visibility, hide/show all, Clear Graph, and Builder Clear produced zero query/rebuild requests.
- Timeframe selection retained the semantic market fingerprint and did not rebuild the market.
- The initial GET snapshot/options envelope was about 1.17 MB and contained no `currentConstituents` array.

No user-facing error exposed SQL, RPC, Postgres, or cache implementation details.

## L. Performance observations

Approximate browser-facing observations (not SLOs): warmed initial page 2.52 s; Global All Raw 1.76 s; SIR 1.47 s; Established 0.82 s; Global constituent page 1 approximately 1.8 s; page 2 1.78 s. Published three-market visibility/comparison interactions were local and effectively immediate. Global Top 10 was intentionally blocked before execution for the Plus account. No visible freeze or obvious regression remained after the fix.

## M. Mobile QA

Authenticated production was checked at 390×844 and 768×1024. Builder controls, wrapped active chips, timeframe controls, chart, Clear Graph, Show all/Hide all, constituent selection/paging, comparison, and Methodology remained reachable/readable. Neither viewport had page-level horizontal overflow.

## N. Accessibility

Keyboard traversal produced a visibly focused interactive element. Native radio controls and `aria-pressed` state were present, buttons carried meaningful labels, and the UI distinguished Builder Clear from Clear Graph. Screen/tab selection and Premium lock text conveyed state without relying only on color.

## O. Screenshot evidence

Evidence is stored in `backend/artifacts/market_explorer_acceptance/final_release_20260907/`:

1. `01-populated-desktop.png`
2. `02-global-all-raw.png`
3. `03-constituents-paging.png`
4. `04-screens.png`
5. `05-benchmark-comparison.png`
6. `06-empty-chart.png`
7. `07-sir-market.png`
8. `07-vintage-variants.png`
9. `08-mobile-390.png`
10. `08-tablet-768.png`
11. `09-premium-entitlement-lock.png`

## P. Post-QA health

The post-QA check from the exact production runtime SHA exited 0 with no alerts: V1 165/165 current, V2 165/165 current, 37/37 maintained caches ready/current, failed 0, stale 0, building 0, and orphan leases 0. Browser activity did not destabilize the cache system.

## Q. Genuine blockers

None. The only browser-discovered correctness issue (Global card queries resolving to a stale narrow prepared market) was fixed, tested, deployed, and verified against current production authority before sign-off.

Focused prepared-resolution tests pass 3/3. The broader existing frontend suite is not a release-gate claim: its attempted run reported 2,492 passing and 311 failures dominated by pre-existing test/environment drift, including the repository's `.js` JSX transform problem. Production compilation succeeded; local page-data collection requires the deployment-only `BACKEND_API_BASE_URL` environment value.

## R. Final decision

`MARKET_EXPLORER_LAUNCH_READY`
