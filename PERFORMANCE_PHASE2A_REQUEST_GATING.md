# inDex performance Phase 2A — set page request gating

## Executive summary

The Phase 0 baseline listed five API requests firing eagerly on a cold RIP visit and treated all five as gating candidates. The Phase 2A audit traced each one to its actual rendered consumer and found that **four of the five are genuinely RIP-critical** — they are consumed by components the user sees on the initial RIP decision surface. Only one, the 365-day Set Value history, had no RIP consumer.

That single deferral was made, and it turned out to be worth more than the RIP-only framing suggested: the request was firing on **every** set tab, not just RIP. Gating it removed it from RIP, Cards, and Pull Rates alike.

Measured on `paldea-evolved` against the local production build and backend, mobile viewport, one fresh browser context per route:

| Route | API requests before → after | API bytes before → after |
| --- | ---: | ---: |
| RIP | 5 → **4** | 789.3 kB → **698.4 kB** (−90.9 kB) |
| Market | 5 → 5 | 1,093.7 kB → 1,093.7 kB (unchanged, by design) |
| Cards | 2 → **1** | 272.5 kB → **181.5 kB** (−90.9 kB) |
| Pull Rates | 2 → **1** | 97.9 kB → **7.0 kB** (−90.9 kB) |

- **Requests removed from initial RIP:** 1 of 5 (Value History, 365d, standard scope).
- **Bytes removed from initial RIP:** 90.9 kB of 789.3 kB — a **11.5%** reduction in RIP API transfer.
- **Backend work avoided:** one 365-day set-value history query per cold visit to RIP, Cards, or Pull Rates. Across the three affected tabs this removes 272.7 kB and three backend history queries from the concurrent burst.
- **Direct Market is byte-identical** — the tab that actually renders the history still fetches it immediately on a direct `?tab=market` landing, with no added client delay.
- **Requests that had to remain eager, unexpectedly:** four. Pull Rates, Insights Critical, Insights Secondary, and Top Chase all have proven, currently-visible RIP consumers. In particular **Insights Secondary is not below-the-fold data despite its name** — it owns `outcomeDistribution.percentiles`, which RIP renders above the fold as p50/p95 inside `RipDecisionPage`. Gating or viewport-deferring it would have visibly degraded the RIP decision surface.
- **Did RIP performance measurably improve?** Yes, on the metric this phase targets (unnecessary network/backend work). No Lighthouse LCP/TBT re-measurement was completed — see *Measurements* below for exactly what was and was not measured.

The honest headline: Phase 2A's ceiling was much lower than the Phase 0 baseline implied, because the set page's request graph was already substantially better gated than the baseline's request-count framing suggested. The remaining RIP API cost is dominated by **payload size, not request count** — 536 kB of the 698 kB that RIP still fetches is a single Top Chase response. That is a Phase 3 problem, not a Phase 2A one.

---

## Request ownership map

Every request the set page can initiate, with its proven consumer. Ownership was determined by tracing rendered JSX and state consumers, not by function name.

| Request | Client function | Trigger condition (after Phase 2A) | RIP | Market | Cards | Pull Rates | Fold | Decision |
| --- | --- | --- | :-: | :-: | :-: | :-: | --- | --- |
| Pull Rates | `getPokemonSetPullRates` | `tab === "pull-rates" \|\| tab === "overview"` | ✅ | — | — | ✅ | above | **KEPT — RIP critical** |
| Insights Critical | `getPokemonSetInsightsCritical` | always (set detail) | ✅ | — | — | — | above | **KEPT — RIP critical** |
| Insights Secondary | `getPokemonSetInsightsSecondary` | always (set detail) | ✅ | — | — | — | above | **KEPT — RIP critical** |
| Top Chase | `getPokemonSetTopChase` | `tab === "overview" \|\| tab === "market"` | ✅ | ✅ | — | — | above | **KEPT — RIP critical** |
| Value History 365d | `getPokemonSetValueHistory` | `tab === "market"`, or shell seed missing | ❌ | ✅ | — | — | below | **DEFERRED — other tab** |
| Market Overview | `getPokemonSetOverview` | `tab === "market"` | ❌ | ✅ | — | — | — | already gated |
| Market Movers | `getPokemonSetMarketMovers` | `tab === "market"` | ❌ | ✅ | — | — | — | already gated |
| Sealed Market | `getPokemonSetSealedMarket` | `tab === "market"` | ❌ | ✅ | — | — | — | already gated |
| Market Dashboard | `getPokemonSetMarketDashboard` | never fetched live; seed/cache hydrate only | ❌ | ✅ | — | — | — | already gated |
| Cards page | `getPokemonSetCardsPage` | `tab === "cards"` | ❌ | ❌ | ✅ | — | — | already gated |
| Cards validation | `getPokemonSetCardsValidation` | cards/insights consumer only | ❌ | ❌ | ✅ | — | — | already gated |
| Full page snapshot | `fetchPokemonSetPageSnapshot` | `SET_DETAIL_TABS_REQUIRING_FULL_PAGE_PAYLOAD` is `new Set([])` | — | — | — | — | — | **proven dead, left in place** |

### Consumer justification for each *kept* request

**Pull Rates — KEPT.** RIP does still consume this endpoint directly. `RipStatisticsPageClient` passes `pullRateAssumptions` into `RipDecisionPage`, which calls `buildRipDecisionModel({ ..., pullRateAssumptions })`. That model builds `openingOdds` from `row.rarityOddsDenominator` and renders the Opening Odds panel on the RIP decision surface. Per the task's §6 instruction, the required fields were checked against other already-required responses — they are **not** present in the shell seed, Insights Critical, or Insights Secondary payloads. `rarityOddsDenominator` is owned exclusively by the pull-rates contract, so reusing another source would have meant duplicating or fabricating pull-rate values. The request stays. It is also the cheapest of the five at 7.0 kB.

**Insights Critical — KEPT.** Backs the RIP verdict, Why It Ranks, Financial RIP evidence, and Collector Appeal blocks. 114.0 kB. Flagged below as a Phase 3 payload candidate.

**Insights Secondary — KEPT, and this is the important correction to the Phase 0 characterization.** Phase 0 described it as "secondary/below fold". It is not. `pokemonSetInsightsSecondaryClient.js` normalizes `outcomeDistribution.percentiles`, and the page derives `percentileP50` / `percentileP95` from exactly that, then passes them as `p50=` / `p95=` into `RipDecisionPage` — above the fold. It additionally owns `rip_statistics`, `openingDesirability`, and `desirabilityValidation`, which drive the Simulation Results and Desirability Evidence sections. Deferring it, or hiding it behind an IntersectionObserver, would have blanked above-the-fold RIP numbers. The task's §7 explicitly permitted viewport gating here; the audit says not to, and the audit wins.

**Top Chase — KEPT, per §9.** RIP renders a three-card consumer chase preview from this response and Market renders the full Top 10 table; the existing code comments this as deliberately shared data, and a shared request key means a RIP→Market switch costs one fetch, not two. Because RIP visibly requires the existing request, §9 directs leaving it eager and **not** touching the endpoint contract in this phase. Done. At 536.3 kB it is now **77% of all remaining RIP API bytes** and is the single highest-value Phase 3 target.

### Justification for the one deferral

**Value History 365d — DEFERRED to Market.**

The only component that renders the full 365-day series is Market's Set Value Trend card. Tracing `activeSetValueHistory` through the page shows exactly five reads: a memo, a debug-only effect, a `useSectionTiming` call, one render site inside the `setDetailTab === "market"` branch, and one inside a `false && setDetailTab === "overview"` branch — i.e. dead code. No live RIP render site exists.

The one real complication is the title/header card, which is present on *every* tab and reads the canonical `standard` scope for its sparkline and 30-day delta via `activeSetValueContract`. That is why the pre-existing code fetched the canonical scope unconditionally. But the page already seeds precisely that scope from `setShellContract.setValueSummary.compact.visiblePoints`, which rides the shell request the page fetches regardless — no extra network cost.

So the gate is deliberately **not** a bare `tab === "market"`. It is:

```js
const titleCardNeedsCanonicalScopeFetch = shellSetValueVisiblePoints.length === 0;
const desiredScopes = Array.from(
  new Set([
    ...(setDetailTab === "market" || titleCardNeedsCanonicalScopeFetch ? [CANONICAL_SET_VALUE_SCOPE] : []),
    ...(setDetailTab === "market" ? [setValueTrendScope || CANONICAL_SET_VALUE_SCOPE] : []),
  ])
);
```

Market keeps both scopes. Every other tab requests the canonical scope **only** as a correctness fallback when the shell seed is genuinely absent. This is what keeps the change compliant with §22 "no changes to visible outputs": a set whose shell lacks compact points still fetches, so the title card's sparkline and 30D delta render byte-for-byte as before rather than silently degrading to the "Coming soon" placeholder. Sets with a normal shell payload — the overwhelming majority — skip the request entirely.

---

## Before/after RIP waterfall

Same set, same local backend, same harness; one fresh 390×844 mobile browser context per route, `networkidle` plus a 4 s settle.

| API request | Phase 0 (baseline doc) | Before (re-measured) | Phase 2A | Bytes removed from initial RIP | Decision |
| --- | ---: | ---: | ---: | ---: | --- |
| Pull Rates | 7.5 kB | 7.0 kB | 7.0 kB | 0 | KEPT — RIP critical |
| Insights Critical | 117 kB | 114.0 kB | 114.0 kB | 0 | KEPT — RIP critical |
| Insights Secondary | 42 kB | 41.1 kB | 41.1 kB | 0 | KEPT — RIP critical |
| Value History 365d | 93 kB | 90.9 kB | — not requested — | **−90.9 kB** | DEFERRED — other tab |
| Top Chase 365d/10 | 549 kB | 536.3 kB | 536.3 kB | 0 | KEPT — RIP critical |
| **Total** | **~808 kB / 5 req** | **789.3 kB / 5 req** | **698.4 kB / 4 req** | **−90.9 kB / −1 req** | |

The re-measured "before" column was captured by reverting the change, rebuilding, and re-running the identical harness, so the before/after comparison is apples-to-apples rather than a comparison against the Phase 0 document. The small deltas against the Phase 0 column (e.g. 549 → 536.3 kB) are decompressed-body vs. transfer accounting and normal data drift, and they apply equally to both columns.

No duplicate requests were observed on any route, before or after.

---

## Direct-tab verification

Direct URL landings, each in a fresh context — confirming the active tab still owns its data immediately and no interaction is required:

**`?tab=market`** — 5 requests, 1,093.7 kB, **identical to before**:
```
Sealed Market      200   79.2 kB
Market Overview    200  353.6 kB
Market Movers      200   33.8 kB
Top Chase          200  536.3 kB
Value History      200   90.9 kB   <- still immediate on direct landing
```
Market got no slower. The four independent market requests still start together rather than waterfalling (§15).

**`?tab=cards`** — 1 request (was 2), 181.5 kB:
```
Cards Page         200  181.5 kB
```
No market-only requests, no Pull Rates. Value History no longer fires here.

**`?tab=pull-rates`** — 1 request (was 2), 7.0 kB:
```
Pull Rates         200    7.0 kB
```
Loads immediately without interaction. No Cards, no market-only requests. This tab's API cost fell by **93%**.

**Initial RIP** — 4 requests: Pull Rates, Insights Critical, Insights Secondary, Top Chase. No Cards request, no market-only request, no Value History.

---

## Duplicate-request and cache-reuse verification

A single session was driven through `RIP → Market → Cards → Pull Rates → RIP → Market` in one browser context:

- **Value History fired exactly once** across the entire session, during the Market phase only. Precisely the intended ownership.
- **Returning to RIP issued zero API requests** — all RIP data was reused from client-held state, confirming §17 cache reuse is intact and no refetch was forced by the tab return.
- **Returning to Market re-fetched Sealed / Overview / Movers but not Value History.** Those three are `no-store` endpoints and this repeat behavior is pre-existing and unchanged by Phase 2A.
- The per-route traces (fresh context each, no navigation) showed **no duplicate requests on any of the four routes**, before or after.

One caveat reported honestly: in the *navigated* session the ad-hoc harness attributed three Pull Rates requests to the initial-RIP phase. The harness attributes responses to whichever phase is current when its async handler runs, so late responses can be misfiled across phase boundaries, and the clean per-route traces show Pull Rates firing exactly once on both RIP and Pull Rates. The change does not touch the pull-rates effect. This is most likely instrumentation attribution rather than a real duplicate, but it was not conclusively isolated and is **not** being claimed as verified-clean — worth a dedicated check in a later pass.

---

## Measurements

**What was measured:** API request count, per-request transfer bytes, request identity, duplicate detection, and cache reuse across tab switches — for all four routes, in both the before and after builds, using the same harness and the same set (`paldea-evolved`). This is the primary success metric for this phase and it is fully evidenced above.

**What was not measured:** the 3-run mobile Lighthouse matrix (LCP / FCP / TBT / Speed Index / total transfer) requested in §21. This is a gap in the deliverable and I am not going to substitute an estimate for it. Two things about the expected result are worth stating so the gap is interpretable:

- Total mobile RIP transfer should fall by ~90.9 kB, from the Phase 0 baseline of 4.05 MB to roughly 3.96 MB — about a 2% reduction, because RIP's transfer is dominated by images (Phase 1) and the 413 kB JS bundle (Phase 2B), not by this API response.
- LCP is unlikely to move measurably. Phase 0 established that RIP's mobile LCP is "more dominated by image completion than TBT," and the deferred request is a below-fold, non-render-blocking XHR that does not feed any above-fold element. A phase whose deliverable is "less unnecessary backend work" should not be judged on an LCP delta it was never positioned to produce.

Set-detail first-load JS is **392 kB, unchanged**, exactly as §22 expects — JS splitting is Phase 2B.

---

## Tests

| | Total | Pass | Fail |
| --- | ---: | ---: | ---: |
| Before (Phase 0 baseline) | 1,451 | 1,359 | 92 |
| After Phase 2A | 1,462 | 1,370 | 92 |

- **+11 tests, +11 passing, no new failures.** The 92 remaining failures are the pre-existing red suite documented in the Phase 0 baseline and were not touched.
- `npm run build`: **passes** (`✓ Compiled successfully`). One build attempt exited non-zero on the known flaky `revalidate: 0` targets static-generation probe for `/` and `/Market` that the Phase 0 baseline already documents as an expected dynamic-rendering fallback; a re-run succeeded.

New file: `frontend/components/explore/SetTabRequestGating.contract.test.mjs` — 11 tests asserting **what does not load**, in the repo's existing source-contract style:

- Value History is gated to Market plus the shell-seed fallback, and no longer requests the canonical scope unconditionally.
- Market still requests both its canonical and selected trend scopes.
- Scope de-duplication (`seededLoadedScopes`, `alreadyLoadedScopes`, the empty-list short-circuit) survived the gating change.
- Value History scopes are still issued via `Promise.all` — gating did not introduce a waterfall (§15).
- **Pull Rates, Top Chase, Insights Critical and Insights Secondary must stay eager on RIP**, each pinned to its proven RIP consumer. These are deliberately tripwires in the opposite direction: they fail if a future pass "optimizes away" a request RIP actually renders.
- Market-only and Cards-only requests do not fire on RIP.
- The legacy full-page snapshot set remains empty and inert.
- Every tab-gated fetch is evaluated inside a `useEffect`, so a direct `?tab=` landing fetches on mount rather than waiting for interaction (§12).

One pre-existing test, `RipStatisticsSetLoad.contract.test.js` → *"Phase 6B: set value history direct-fetch effect skips scopes…"*, briefly broke: it slices the effect using `"activeMarketDashboardDerivedState,\n  ]);"` as an end anchor, and appending a new dependency after that line invalidated the anchor. Rather than weaken the existing assertion, the new dependency was **ordered before** `activeMarketDashboardDerivedState` so the anchor stays intact. The test passes unmodified.

---

## Files changed

- `frontend/components/explore/RipStatisticsPageClient.jsx` — value-history scope gating (one `desiredScopes` block) plus one dependency addition. ~20 lines, mostly comment.
- `frontend/components/explore/SetTabRequestGating.contract.test.mjs` — new, 11 request-gating regression tests.
- `PERFORMANCE_PHASE2A_REQUEST_GATING.md` — this report.

No changes to scores, Financial RIP, Collector Appeal, ranks, tiers, EV, simulation output, pull-rate assumptions, market calculations, payload contracts, metric names, copy, design, tab architecture, routing, SEO, auth, Phase 1 image work, Recharts imports, bundle boundaries, Cards pagination, or backend schema. No dynamic imports were introduced. No endpoint contract was modified.

**Optional intent prefetch (§13) was not implemented.** It is explicitly conditional on measurement showing tab transitions got worse after gating, and they did not: the only request moved is a below-fold Market chart feed, and Market's direct-landing cost is byte-identical. Adding speculative prefetch here would have added complexity with no measured problem to solve.

---

## Deferred opportunities

Ranked by measured bytes, not by code ugliness.

1. **Top Chase payload — 536.3 kB, `no-store`.** Now **77% of all remaining RIP API bytes** and the single largest measured item on the page. RIP renders a three-card preview from a response carrying 10 cards with full 365-day histories; Market renders the full table. A projected/windowed variant for the RIP preview is the highest-value remaining API win. Phase 3. Not touched here per §9.
2. **Market Overview payload — 353.6 kB.** The largest single item on direct Market, larger than expected for a "slim" overview endpoint. Worth a projection audit alongside Top Chase. Phase 3.
3. **Insights Critical payload — 114.0 kB.** RIP-critical and cannot be deferred, so payload projection is the only available lever. Phase 3.
4. **Rankings/targets endpoint — 2.62 MB, ~1.86 s.** Untouched per §2. Still the largest single payload in the application and the worst latency measured anywhere in Phase 0.
5. **Set JS/client splitting — 392 kB first-load, unchanged.** Phase 2B.
6. **Dead code removal.** `fetchPokemonSetPageSnapshot`, `setPageSnapshotRefreshState`, and the `false && setDetailTab === "overview"` Set Value Trend render branch are all provably unreachable. Left in place: §14 permits removal only when tightly scoped, and this phase's diff was deliberately kept minimal so the network measurement stays isolated.
7. **The navigated-session Pull Rates duplicate observation** noted above — confirm with better instrumentation.

---

## Recommendation for the next phase

**Phase 3 (API payload slimming), not Phase 2B (JS splitting).**

Post-Phase-2A measurement, on a cold mobile RIP visit:

- RIP still transfers **698.4 kB of API payload** across 4 requests, of which 536.3 kB is one `no-store` response that cannot be browser-cached and is therefore re-paid on warm navigation.
- RIP transfers **392 kB of JS**, which *is* cacheable and, per Phase 0's warm measurements, costs 0 additional bytes on every repeat set navigation.

So the largest remaining *repeatable* network cost on the set page is API payload, and by a clear margin. Phase 3 also has a better risk profile for the byte win: Top Chase projection is a contained change behind a contract test, whereas Phase 2B's 392 kB is a medium-to-high-risk restructuring of a 14.6k-line client with loading, focus, routing, and data-cache behavior to preserve.

The counter-argument deserves stating fairly: Phase 0 measured 1,006 ms of mobile JS execution and 272 ms TBT on RIP, and **Phase 3 will not improve either**. Main-thread time is a real user-facing problem that only Phase 2B can address. But Phase 0 also found RIP's mobile LCP is dominated by image completion rather than TBT, which caps how much visible improvement Phase 2B can deliver on the metric users actually feel.

Recommendation: **Phase 3 first**, targeting Top Chase and Market Overview, then Phase 2B for main-thread time. If TBT/interaction responsiveness is judged the more important product goal than transfer, that ordering should be flipped deliberately — but on the bytes measured here, Phase 3 is the larger win.
