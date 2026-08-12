# inDex frontend performance baseline (Phase 0)

## Executive summary

The current production build is usable on desktop but has poor cold mobile LCP on image-heavy routes. The largest measured bottleneck is image/resource transfer: the global `/inDex.png` is 1.74 MB and appears on every tested route, while Cards reaches 6.44 MB mobile / 10.98 MB desktop and is dominated by remote card PNGs. The second-largest bottleneck is the set page's monolithic client graph plus eager API work: every set tab transfers 413 kB JavaScript, initial RIP executes about 1.01 s of JavaScript on mobile, and RIP requests Pull Rates, Insights, value history, and top chase before interaction. Images and API payloads dominate bytes; client execution dominates set-page main-thread time.

Recommended first optimization: optimize delivery of the existing global logo and card/pack images without changing artwork or layout, then split tab-only code and requests out of the set client boundary. This ordering is based on measured user impact, not source size.

## Environment and method

- Audited commit: `207795f8c887cab3dc330347eff4e6ba390418ff` (`main`, synchronized to `origin/main` on 2026-08-11)
- Test date: 2026-08-11 America/Phoenix (Lighthouse timestamps cross into 2026-08-12 UTC)
- OS: Windows / PowerShell host
- Node: 22.13.1
- Next: 15.5.15
- React: 19.2.5
- Lighthouse: 12.8.2
- Browser: installed Microsoft Edge driven through Chromium DevTools; exact Edge version was not exposed by the captured Lighthouse summary
- Mode: `next build` followed by `next start`; never `next dev`
- Backend: repository FastAPI service on localhost, using the repository's configured data services. These are production-code measurements, not deployed internet TTFB.
- Cold lab runs: one fresh Lighthouse context/cache per route and device, simulated throttling. A single run is a baseline, not a distribution; server TTFB outliers should be rechecked with 3-5 runs in follow-up work.
- Warm observations: one persistent Playwright browser context, sequential repeat page loads. They demonstrate cache reuse but are full navigations, not precise click-to-paint RUM.

An existing dev server was using ports 3000 and 3100 and rewriting `.next`. Those invalid measurements were discarded. The valid production build used the opt-in `.next-perf` directory and port 4174.

## Build baseline

- Production build succeeded.
- First isolated timed build: 105.07 s total; compile 63.0 s. A subsequent analyzer build compiled in 16.6 s with warm caches.
- All application pages were reported dynamic (`ƒ`) except `robots.txt` (`○`).
- Shared first-load JS: 102 kB.
- Set detail: 392 kB first-load JS; `/Explore/rip-statistics`: 391 kB.
- Home: 235 kB; Rankings: 117 kB; Market: 119 kB; Research and Sets catalog: 105 kB.
- Largest shared chunks reported by Next: 54.2 kB and 45.5 kB compressed/transfer accounting.
- Middleware: 34.2 kB.
- Warnings include many raw `<img>` uses, including the set client and Sets catalog, plus unstable hook dependency objects/missing dependencies in `RipStatisticsPageClient.jsx`. No build error occurred.
- During static-generation probing, `/` and `/Market` attempted a `revalidate: 0` targets fetch and fell back after Next identified dynamic server usage.

## Route baseline

Times are milliseconds; transfer and JS are decimal MB. TTFB is Lighthouse's initial server-response audit and shows run-to-run backend variability.

| Route/state | Device | TTFB | FCP | LCP | CLS | TBT | Speed Index | Transfer | JS | Requests |
| --- | --- | ---: | ---: | ---: | ---: | ---: | ---: | ---: | ---: | ---: |
| `/` | Mobile | 3,067 | 1,511 | 13,808 | 0.000 | 57 | 6,113 | 2.49 MB | 0.253 MB | 41 |
| `/` | Desktop | 12 | 369 | 2,115 | 0.000 | 0 | 2,901 | 2.48 MB | 0.253 MB | 38 |
| `/Rankings` | Mobile | 1,465 | 2,408 | 4,127 | 0.000 | 24 | 3,716 | 2.65 MB | 0.266 MB | 47 |
| `/Rankings` | Desktop | 117 | 528 | 4,214 | 0.001 | 0 | 971 | 4.53 MB | 0.266 MB | 69 |
| `/Market` | Mobile | 369 | 2,408 | 4,214 | 0.000 | 104 | 2,755 | 4.60 MB | 0.267 MB | 59 |
| `/Market` | Desktop | 2,116 | 530 | 5,954 | 0.000 | 0 | 2,667 | 7.03 MB | 0.267 MB | 85 |
| `/Research` | Mobile | 20 | 1,357 | 11,330 | 0.000 | 8 | 1,357 | 1.95 MB | 0.126 MB | 27 |
| `/Research` | Desktop | 14 | 369 | 542 | 0.000 | 0 | 369 | 1.94 MB | 0.126 MB | 23 |
| `/TCGs/Pokemon/Sets` | Mobile | 57 | 1,963 | 12,234 | 0.000 | 18 | 1,963 | 3.60 MB | 0.126 MB | 47 |
| `/TCGs/Pokemon/Sets` | Desktop | 40 | 452 | 2,388 | 0.000 | 0 | 474 | 6.43 MB | 0.126 MB | 69 |
| `/TCGs/Pokemon/Sets/paldea-evolved` (RIP) | Mobile | 11 | 2,708 | 14,642 | 0.000 | 272 | 7,101 | 4.05 MB | 0.413 MB | 50 |
| same (RIP) | Desktop | 1,638 | 564 | 2,523 | 0.010 | 0 | 1,753 | 4.05 MB | 0.413 MB | 46 |
| same `?tab=market` | Mobile | 18 | 2,857 | 14,855 | 0.000 | 301 | 3,138 | 4.78 MB | 0.413 MB | 52 |
| same `?tab=market` | Desktop | 131 | 565 | 2,523 | 0.000 | 0 | 893 | 7.23 MB | 0.413 MB | 64 |
| same `?tab=cards` | Mobile | 1,205 | 2,708 | 14,641 | 0.115 | 276 | 6,917 | 6.44 MB | 0.413 MB | 64 |
| same `?tab=cards` | Desktop | 3,032 | 565 | 2,484 | 0.038 | 9 | 2,623 | 10.98 MB | 0.413 MB | 85 |
| same `?tab=pull-rates` | Mobile | 116 | 2,705 | 14,478 | 0.000 | 107 | 2,705 | 2.71 MB | 0.413 MB | 44 |
| same `?tab=pull-rates` | Desktop | 117 | 566 | 2,484 | 0.000 | 0 | 626 | 2.70 MB | 0.413 MB | 40 |

Mobile set-page main-thread work was 1.20-1.90 s. JavaScript execution was 598 ms (Pull Rates), 784 ms (Cards), 980 ms (Market), and 1,006 ms (RIP). Lighthouse estimated unused JS at 161-394 kB on these states. Research had 0 measured unused JS.

## Bundle findings

The official `@next/bundle-analyzer` 15.5.15 report was generated under ignored `.next-perf/analyze/`.

- `RipStatisticsPageClient.jsx + 87 modules`: 1.878 MB source/stat size, 554 kB parsed, 136 kB gzip.
- `RipStatisticsPageClient.jsx` alone: 1.008 MB source/stat size and 297 kB parsed inside the concatenated group. The source file is 698 kB / about 13,804 lines.
- Recharts modules: approximately 759 kB source/stat size across the client graph.
- Largest emitted client chunks on disk: `3460` 558 kB raw (138 kB transferred in Lighthouse) and `6801` 370 kB raw (101 kB transferred). Both are loaded by the set route; analyzer/string evidence places the monolithic set client and Recharts in this graph.
- All four tabs transfer exactly the same 413 kB JS. The source statically imports Recharts, `PackValueHistoryChart`, Pull Rates components, Cards controls/client, Market clients, simulation selectors, and below-the-fold charts.
- Therefore inactive Market, Cards, Pull Rates, simulation, and chart code is in the initial client graph. There are no tab-level dynamic imports today.
- Lighthouse unused-JS estimates reinforce this: mobile RIP 356 kB, Market 359 kB, Cards 394 kB, Pull Rates 161 kB.
- Shared global shell is 102 kB first-load JS plus a 26.4 kB raw app-layout chunk. It includes client boundaries for StickyNav/Header, mobile bottom nav, AuthProvider, CartContextProvider, and RouteTransitionFeedback on every route.
- No clear duplicated application module was proven by the analyzer; the material issue is breadth of one eager graph, not measured duplicate chunks.

### Client-boundary map

Initial RIP needs set identity/hero, RIP decision/summary and score selectors, initial value/trend/top-chase views, navigation/scaffold, and the components that render above-the-fold state. Those should remain eager unless the layout is intentionally changed.

Market-only candidates include market dashboard/reducer, sealed market trend, movers, market-window helpers, market tooltips, and related market clients. Cards-only candidates include cards controls, pagination/client fetches, card validation, movement/filter logic, and card-grid rows. Pull-Rates-only candidates include `PullRatesTab`, assumptions card, pull-rate client, and pack-path formatting. Secondary/lazy candidates include full historical charts, distribution/scatter/pie charts, insights-secondary rendering, simulation deep dives, and below-the-fold analysis. These are theoretical Phase 2 boundaries only; no split was performed.

## Request waterfall and API findings

On a cold RIP load the browser began the following together at roughly 3.46 s, after hydration/client startup:

| Request | Status | TTFB/finish observed | Transfer | Cache header | Initial blocker/eagerness |
| --- | ---: | ---: | ---: | --- | --- |
| Pull rates | 200 | 596 ms cold; 560 ms warm set load | 7.5 kB | `public, s-maxage=300, stale-while-revalidate=3600` | Eager on RIP despite inactive tab |
| Insights critical | 200 | 1,436 ms cold; 1,060 ms warm | 117 kB | public SWR | Eager; affects RIP/hero analysis |
| Insights secondary | 200 | 1,387 ms cold; 1,398 ms warm | 42 kB | public SWR | Eager; secondary/below fold |
| Value history, 365d | 200 | 1,000 ms cold; 1,351 ms warm | 93 kB | public SWR | Eager on RIP |
| Top chase, 365d, 10 | 200 | 1,336 ms cold/warm | 549 kB | `no-store` | Eager on RIP; largest API payload |

Warm Market loaded sealed (166 ms), overview (176 ms, no-store), movers (570 ms), top chase (589 ms, no-store), and value history (587 ms). Warm Cards page 1 loaded in about 468 ms and was no-store. Warm Pull Rates/value history took about 507-555 ms when not served from the browser cache. The next supported set (`obsidian-flames`) took 1.09 s document TTFB and its client requests settled around 0.66-1.19 s.

The targets/rankings endpoint returned 2.62 MB and measured 1.85 s TTFB / 1.86 s total on a direct cold-ish call. Its payload reported a 1,106.5 ms targets query, 1,006.7 ms set-value enrichment, 1,167.8 ms top-card enrichment, and 221.0 ms opening-desirability enrichment. One embedded `total_backend_ms` value was inconsistent with wall time and is not treated as latency evidence.

Warm sequential full navigations showed no additional JS transfer after the first set page. Document response starts were normally 99-121 ms for warmed set states, but Market showed a 2.75 s outlier. This variability, plus Lighthouse TTFB outliers from 1.2-3.1 s, makes server/API latency a real secondary problem rather than a stable constant.

## Server rendering and authentication

`app/layout.js` awaits `getAuthenticatedUserFromCookiesWithTimeout(150)` for every route. `authServer.js` calls both `headers()` and `cookies()`, so the root layout opts every inheriting route into request-time dynamic rendering; the build confirms `ƒ` for all application pages.

Every anonymous page resolves the auth boundary, but no-token requests return locally and do **not** call backend `/auth/me`. Production logs measured anonymous resolution at about 1-9 ms, so auth lookup is not a meaningful anonymous TTFB bottleneck. The 150 ms timeout matters only when a token exists and the backend auth request stalls; it does not delay no-token requests by 150 ms.

Without the root boundary, content-only Research and similar shell pages are candidates for static rendering, while data-backed `/`, Rankings, Market, Sets, and set detail would still need their own fetch/cache semantics evaluated route by route. The root auth boundary currently prevents any of those distinctions from appearing in the build output and prevents shared public HTML caching.

## Client rendering findings

- Set RIP mobile: 1,774 ms main-thread work, 1,006 ms JS execution, 272 ms TBT.
- Set Market mobile: 1,765 ms main-thread work, 980 ms JS execution, 301 ms TBT.
- Set Cards mobile: 1,899 ms main-thread work, 784 ms JS execution, 276 ms TBT and CLS 0.115.
- Chart/library code is present before charts/tabs are needed. Recharts is a material contributor, but the measured LCP is more dominated by image completion than TBT.
- Build warnings show several memo/effect dependency issues in the large client. They are plausible rerender risks, but this audit did not produce a React Profiler commit trace, so they are not promoted above measured network/bundle costs.

Existing instrumentation includes `useSectionTiming`, `markSectionTiming`, set-page marks, navigation timing in `RouteTransitionFeedback`, server snapshot timing logs, and request timing logs in set clients. Section marks intentionally disable themselves in production and there is no RUM sink, so Lighthouse/Playwright was used rather than adding duplicate production logging.

## Image findings

- `/inDex.png` transfers 1,742,140 bytes and is the largest single resource on the RIP trace; it is inherited globally.
- Remote card PNGs commonly transfer 180-245 kB each. Cards and Market scale this across many visible rows/cards, causing 6.44-10.98 MB total transfer.
- The Paldea Evolved logo is 113.7 kB and is rendered at about 56 x 18 CSS px on mobile without intrinsic `width`/`height`; Lighthouse flags it as unsized. This is a layout-shift risk even where measured CLS happened to be zero.
- Cards mobile measured CLS 0.115 and desktop 0.038.
- Offscreen-image audit did not identify a material eager-offscreen saving in the sampled Cards run; many images already use `loading="lazy"`.
- Local booster WebPs exist, but the measured global PNG and remote card PNGs dominate more than those local WebPs.
- Image density changes with viewport, explaining why desktop transfer can exceed mobile even where desktop LCP is much better.

## Cold versus warm findings

Cold Lighthouse set states always downloaded 413 kB JS. After the first set page, repeat full navigations downloaded 0 additional JS, reducing warmed resource transfer to approximately 1.13 MB for Market, 191 kB for Cards, 4 kB for Pull Rates, and 759 kB for set-to-set (browser cache accounting only). API requests still cost roughly 0.5-1.4 s and no-store top-chase/overview/cards endpoints repeat. Problems therefore divide into:

1. cold image/network transfer and LCP;
2. cold set JS parse/execute/hydration;
3. repeated API latency/no-store work on warm navigation;
4. server response variance when data requests miss warm paths.

## Ranked bottlenecks

### P0 — Global and card image delivery

- **Evidence:** 1.74 MB global PNG; 11.3-14.9 s mobile LCP on content/set routes; Cards up to 10.98 MB; remote cards 180-245 kB each.
- **User impact:** slow visible completion on every route, especially mobile; Cards layout shift.
- **Likely cause:** oversized PNGs, raw `<img>`, missing intrinsic dimensions, remote source images larger than rendered size.
- **Recommended fix:** preserve artwork/layout but generate an appropriately sized logo asset, use responsive image delivery where allowed, add intrinsic dimensions/aspect ratios, and size card requests/components to rendered slots.
- **Expected impact:** remove roughly 1.5+ MB from every cold route and multiple MB from image-heavy tabs; materially lower LCP and CLS.
- **Risk:** low-to-medium (asset quality, remote-loader policy, cache behavior).

### P1 — Eager set API graph and large responses

- **Evidence:** RIP requests inactive Pull Rates plus secondary insights; top chase is 549 kB/no-store; targets is 2.62 MB and ~1.86 s; set API responses settle around 0.6-1.4 s.
- **User impact:** delayed section readiness, repeat warm-navigation work, server TTFB variability.
- **Likely cause:** fetch orchestration centralized in one client and broad payload contracts.
- **Recommended fix:** gate tab-only/secondary requests by active tab/viewport and audit top-chase/targets response projections and cache policy without reverting slim endpoint architecture.
- **Expected impact:** fewer requests/bytes on RIP and lower backend concurrency; faster warm tabs when prefetched intentionally near interaction.
- **Risk:** medium (state freshness and tab transition regressions).

### P1 — Monolithic set client and chart bundle

- **Evidence:** 413 kB JS on every tab; 554 kB parsed main concatenated chunk; 297 kB parsed from the page client itself; Recharts 759 kB source; up to 1.01 s mobile JS execution and 394 kB unused JS.
- **User impact:** slow hydration and blocking on cold mobile set visits.
- **Likely cause:** one 13.8k-line client statically imports all tabs/charts/analysis.
- **Recommended fix:** introduce tab-level and below-fold dynamic boundaries, keeping hero/RIP-critical presentation eager.
- **Expected impact:** substantially reduce initial set JS and mobile main-thread work; exact target should be established by a Phase 2 A/B build.
- **Risk:** medium-high (loading/error state, routing, focus, and data-cache behavior).

### P2 — Root auth makes every public route dynamic

- **Evidence:** every app route is `ƒ`; root calls `headers()`/`cookies()` before rendering. Anonymous auth itself is only 1-9 ms and makes no backend call.
- **User impact:** prevents otherwise cacheable public shell/HTML paths and increases exposure to server variance.
- **Likely cause:** authenticated shell state resolved in the root layout.
- **Recommended fix:** in a separate auth-safe phase, isolate personalized auth below a cacheable public boundary or route group; preserve semantics.
- **Expected impact:** strongest on Research and public shell pages; potential TTFB/cache-hit improvement elsewhere.
- **Risk:** high (authentication hydration and personalized header correctness).

### P3 — Rerender/layout stability debt

- **Evidence:** hook dependency warnings in the set client and Cards CLS 0.115; unsized logo.
- **User impact:** possible extra work and visible movement, mainly Cards/mobile.
- **Likely cause:** unstable derived objects/effects and late image sizing.
- **Recommended fix:** profile React commits after larger network/bundle fixes; stabilize only measured hot paths and reserve image geometry.
- **Expected impact:** smaller than P0/P1 but improves polish/interaction consistency.
- **Risk:** medium because memo/effect changes can alter behavior.

## Recommended implementation phases

### Phase 1 — Image/resource delivery

- Likely files: `frontend/components/Header.js`, brand/logo components, `frontend/components/explore/RipStatisticsPageClient.jsx`, set/card image components, `frontend/app/TCGs/Pokemon/Sets/page.js`, `frontend/next.config.mjs`, and existing `frontend/public/` assets.
- Benefit: largest immediate cold-load and LCP reduction across all routes.
- Risk: low-to-medium; no visual redesign.
- Verify: repeat all Lighthouse routes 3 times/device; compare LCP, transfer, Cards CLS, and visual snapshots.

### Phase 2 — Set client and tab boundaries

- Likely files: `RipStatisticsPageClient.jsx`, `components/pokemon/set-page/{Cards,PullRates,Overview}`, chart components, and related clients.
- Benefit: reduce 413 kB initial JS, unused JS, parse/execute, hydration, and inactive-tab requests.
- Risk: medium-high.
- Verify: analyzer diff, Lighthouse set states, route/query contract tests, tab focus/history/loading tests, and request waterfall assertions.

### Phase 3 — API projection, cache, and waterfall work

- Likely files: `frontend/lib/pokemon/*Client.js`, set API proxy routes, `frontend/lib/explore/ripStatisticsServer.js`, and corresponding backend service/projection code only where evidence demands.
- Benefit: shrink 549 kB top chase and 2.62 MB targets payloads; reduce 0.5-1.9 s waits and no-store repeats.
- Risk: medium-high because public metric contracts must remain unchanged.
- Verify: payload contract tests, byte/timing capture, cold/warm transition trace, and cache-header checks.

### Phase 4 — Public rendering/cache boundary

- Likely files: `frontend/app/layout.js`, route groups/layouts, `frontend/lib/authServer.js`, AuthProvider/Header.
- Benefit: restore static/cacheable behavior where possible.
- Risk: high; auth semantics must remain identical.
- Verify: build route modes, anonymous/authenticated header tests, cache headers, TTFB distribution, login/logout navigation.

### Phase 5 — React rendering hot paths

- Likely files: measured hot sections of `RipStatisticsPageClient.jsx` and chart/selectors.
- Benefit: reduce residual rerenders/TBT after boundary work.
- Risk: medium.
- Verify: React Profiler/RUM commit measurements, not lint warnings alone.

## Tests and engineering safety

- `npm run build`: passed.
- `npm run test:frontend`: failed on audited `main`: 1,451 tests, 1,359 pass, 92 fail. The first failures are revalidation-tag contract assertions; failures pre-exist the audit configuration and were not rewritten.
- Public metric tests were part of the run, but the suite-level result is red; no claim of a fully passing contract suite is made.
- General frontend tests do not appear to be broadly enforced in GitHub CI. CI enforcement is a separate engineering-safety recommendation, not part of this performance change.
- `npm install` reports 51 dependency vulnerabilities (4 low, 26 moderate, 17 high, 4 critical). Remediation is out of scope for this performance baseline.

## Measurement limitations

- Lighthouse values are single-run lab measurements and show meaningful TTFB variance; do not use them as percentile SLOs.
- Tests used a local frontend/backend and real configured data services, not deployed CDN/edge geography.
- Exact browser version and production-user auth latency were not measured. Anonymous auth was measured; authenticated `/auth/me` was not tested because no test credential/token was provided.
- JavaScript execution and unused-JS values are available from Lighthouse; a React Profiler trace was not captured.
- Analyzer HTML and raw Lighthouse JSON remain ignored/uncommitted in `.next-perf` and `tmp`.
