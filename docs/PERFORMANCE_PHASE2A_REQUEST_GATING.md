# inDex performance Phase 2A — set page request gating

> ## Status correction — read this first
>
> **The implementation this report originally described was not present in the
> branch.** The report and its 11 contract tests were committed; the source change
> was not. At `c54fcc5` the symbol this document quotes,
> `titleCardNeedsCanonicalScopeFetch`, did not exist anywhere in
> `RipStatisticsPageClient.jsx` (`git log -S` finds no commit that ever introduced
> it), `desiredScopes` still requested the canonical scope unconditionally, and
> **4 of the 11 Phase 2A tests were failing**. Every "after" number in the original
> version of this report therefore described a build that was never committed.
>
> The gate has now been implemented for real, and this document has been rewritten
> against **measured** behaviour at the restored state. The audit's *reasoning* was
> re-verified from scratch and held up; only its claim to be implemented was false.
>
> - Documented but absent at: `c54fcc5`
> - Verified absent and restored during the P1-A pass (this document's current numbers)
> - Independently re-proven before restoring: see *Consumer proof* below.
>
> A second, unrelated defect was found and fixed in the same pass — Top Chase was
> issuing two identical ~542 kB requests per visit. It is recorded at the end of
> this document because it materially changes the byte totals reported here.

## Executive summary

The Phase 0 baseline listed five API requests firing eagerly on a cold RIP visit and treated all five as gating candidates. The Phase 2A audit traced each one to its actual rendered consumer and found that **four of the five are genuinely RIP-critical** — they are consumed by components the user sees on the initial RIP decision surface. Only one, the 365-day Set Value history, had no RIP consumer.

That single deferral was made, and it turned out to be worth more than the RIP-only framing suggested: the request was firing on **every** set tab, not just RIP. Gating it removed it from RIP, Cards, and Pull Rates alike.

Re-measured for the restoration. Two isolated production builds (`PERF_AUDIT_DIST_DIR`),
one at `c54fcc5` and one with the gate plus the Top Chase fix, same harness, same
backend, one fresh 1440×900 browser context per route, 12 s settle. Figures are the
**mean of four sets** — Ascended Heroes, Shrouded Fable, Prismatic Evolutions,
Scarlet & Violet 151 — not a single set:

| Route | API requests before → after | API bytes before → after |
| --- | ---: | ---: |
| RIP | 7.3 → **4.0** | 1,447.4 kB → **710.9 kB** (−736.5 kB, −50.9%) |
| Market | 6.0 → **5.0** | 1,475.5 kB → **1,079.8 kB** (−395.7 kB, −26.8%) |
| Cards | 2.0 → **1.0** | 274.6 kB → **181.7 kB** (−92.9 kB, −33.8%) |
| Pull Rates | 2.0 → **1.0** | 99.1 kB → **8.5 kB** (−90.6 kB, −91.4%) |

The "before" column is much worse than the original report's, for two reasons it
did not account for: Top Chase was being fetched **twice** on both RIP and Market,
and on RIP the value-history request was itself duplicated. Both are gone.

Duplicate request kinds across the four sets fell from **13 to 0**; failed requests
from **2 to 0**.

- **Requests removed from initial RIP:** 3.3 of 7.3 — the Value History fetch (and its duplicate) plus the duplicate Top Chase.
- **Bytes removed from initial RIP:** 736.5 kB of 1,447.4 kB — a **50.9%** reduction in RIP API transfer.
- **Backend work avoided:** one 365-day set-value history query per cold visit to RIP, Cards, or Pull Rates, and one full Top Chase snapshot read per visit to RIP or Market.
- **Direct Market keeps every module it renders** — Set Value Trend, Top Chase, Movers, Sealed and Overview all still fetch immediately on a direct `?tab=market` landing. Market's saving is the removed duplicate Top Chase, not a deferral.
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

### Consumer proof (re-verified before restoring the gate)

The original audit's reasoning was not taken on trust — the gate was only restored
after each claim was re-proven against the current source and the live backend:

- **`SetValueTrendCard` is the only component that renders the 365-day series, and
  it is rendered exclusively inside the `setDetailTab === "market"` branch.**
  Verified at its single render site in `RipStatisticsPageClient.jsx`.
- **The remaining readers of `activeSetValueHistory` do not render it.** They are a
  `debugSetPagePerf` effect, a `useSectionTiming` telemetry call, and a
  `false && setDetailTab === "overview"` branch that is dead by construction.
- **The title card really is fully served by the shell seed.** `adaptSetShell`
  derives `setValueSummary.compact` from the shell payload's own
  `setValueHistoriesByScope`. Running the four sets' live `/shell` responses through
  the real adapter yields, for every one of them, **30 visiblePoints plus a
  currentValue and a delta30dAmount** — with no value-history request at all:

  | Set | visiblePoints | currentValue | delta30d | sourceKey |
  | --- | ---: | ---: | ---: | --- |
  | ascendedHeroes | 30 | 6250.77 | −930.35 | `setValueHistoriesByScope.standard` |
  | shroudedFable | 30 | 879.03 | −46.51 | `setValueHistoriesByScope.standard` |
  | prismaticEvolutions | 30 | 5037.72 | −221.77 | `setValueHistoriesByScope.standard` |
  | scarletAndViolet151 | 30 | 1958.33 | −151.93 | `setValueHistoriesByScope.standard` |

This is why the gate keeps its shell-seed fallback rather than being a bare
`tab === "market"`, and the fallback is not dead code: on a genuinely cold first
paint the shell has not committed yet, so the canonical scope is fetched once and
the title card never degrades to its placeholder. On a warm server the measured
rate is **0 of 4 sets**.

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

Ascended Heroes, both isolated production builds, same harness; one fresh 1440×900
context per route, 12 s settle. Response bodies, measured per request.

| API request | Before (`c54fcc5`) | After | Delta | Decision |
| --- | ---: | ---: | ---: | --- |
| Pull Rates | 8.3 kB ×1 | 8.3 kB ×1 | 0 | KEPT — RIP critical |
| Insights Critical | 115.1 kB ×1 | 115.1 kB ×1 | 0 | KEPT — RIP critical |
| Insights Secondary | 39.4 kB ×1 | 39.4 kB ×1 | 0 | KEPT — RIP critical |
| Value History 365d | 183.3 kB **×2** | — not requested — | **−183.3 kB / −2 req** | DEFERRED — other tab |
| Top Chase 365d/10 | 1,086.0 kB **×2** | 543.0 kB **×1** | **−543.0 kB / −1 req** | KEPT — duplicate removed |
| **Total** | **1,432.1 kB / 7 req** | **705.7 kB / 4 req** | **−726.4 kB / −3 req** | |

The "before" column was captured by building `c54fcc5` into its own dist dir and
running the identical harness against the same backend, so this is apples-to-apples.

**Contrary to the original report, duplicate requests were the dominant cost.** It
claimed "no duplicate requests were observed on any route, before or after"; in fact
RIP was issuing Top Chase twice and Value History twice, and Market was issuing Top
Chase twice, on every single visit for every set tested.

---

## Direct-tab verification

Direct URL landings, each in a fresh context — confirming the active tab still owns
its data immediately and no interaction is required. Means of four sets.

**`?tab=market`** — 5 requests, 1,079.8 kB (was 6 requests, 1,475.5 kB):
```
Sealed Market      200   ~46-70 kB
Market Overview    200  ~347-357 kB
Market Movers      200      ~34 kB
Top Chase          200  ~539-557 kB   <- now ONE request, was two
Value History      200      ~91-95 kB <- still immediate on direct landing
```
Market keeps every module it renders and got no slower; its saving is entirely the
removed duplicate Top Chase. The independent market requests still start together
rather than waterfalling (§15).

**`?tab=cards`** — 1 request, 181.7 kB (was 2, 274.6 kB). No value-history.

**`?tab=pull-rates`** — 1 request, 8.5 kB (was 2, 99.1 kB). No value-history.

**Initial RIP** — 4 requests: Pull Rates, Insights Critical, Insights Secondary, Top
Chase. No Cards request, no market-only request, no Value History.

Rendered-content verification on all four sets after the change: Top Chase network
requests = **1**, occurrences of "Awaiting trend" = **0**, Retry buttons = **0**,
error text = none, and the Sealed / Movers / Set Value sections all render.

---

## Duplicate-request verification

Per-route traces, fresh context each, four sets × four tabs, both builds:

| | Before (`c54fcc5`) | After |
| --- | ---: | ---: |
| Duplicate request kinds (16 route/set traces) | **13** | **0** |
| Failed requests | 2 | **0** |

The duplicates were Top Chase ×2 on RIP and on Market (all four sets), Value History
×2 on RIP (all four sets), and one Pull Rates ×2 on 151.

That last one is worth flagging: the original report recorded a suspected Pull Rates
duplicate, attributed it to harness misfiling, and declined to claim it clean. It was
**real** — it reproduced here on 151 in the before build. It no longer reproduces
after the change, but nothing in this pass targeted the pull-rates effect, so it
should be treated as *not yet explained* rather than fixed. It is the one open thread
left from this document.

---

## Measurements

**What was measured:** API request count, per-request response bytes, request
identity, duplicate detection and failure count — for all four routes, across four
sets, in both the before and after production builds, using the same harness and the
same backend. Plus rendered-content assertions (Top Chase card charts, Sealed,
Movers, Set Value) to confirm the byte savings did not come from losing content.

**What was not measured:** the 3-run mobile Lighthouse matrix (LCP / FCP / TBT / Speed Index / total transfer) requested in §21. This is a gap in the deliverable and I am not going to substitute an estimate for it. Two things about the expected result are worth stating so the gap is interpretable:

- Total mobile RIP transfer should fall by ~726 kB (the measured API delta), a materially larger share of the Phase 0 4.05 MB baseline than the ~90.9 kB the original report projected — because the duplicate Top Chase, which that report did not know about, was the single largest item.
- LCP is unlikely to move measurably. Phase 0 established that RIP's mobile LCP is "more dominated by image completion than TBT," and the deferred request is a below-fold, non-render-blocking XHR that does not feed any above-fold element. A phase whose deliverable is "less unnecessary backend work" should not be judged on an LCP delta it was never positioned to produce.

Set-detail first-load JS is **392 kB, unchanged**, exactly as §22 expects — JS splitting is Phase 2B.

---

## Tests

`npm run test:frontend`, same command both sides:

| | Total | Pass | Fail |
| --- | ---: | ---: | ---: |
| Before (`c54fcc5`) | 1,515 | 1,426 | 89 |
| After (gate restored + Top Chase fix) | 1,522 | 1,438 | 84 |

- **+7 tests, +12 passing, −5 failing, and zero newly-failing tests** (verified by
  diffing the failing-test *names* between the two runs, not just the counts).
- The 5 newly-passing tests are the 4 Phase 2A tests that had been red since the
  implementation went missing, plus `RipStatisticsSetLoad.contract.test.js` →
  *"set value history direct-fetch effect requests only the scopes the active tab
  needs"*. That last one had been failing at HEAD because it pinned the trend scope
  to `setDetailTab === "overview"`, a render site that no longer exists —
  `SetValueTrendCard` lives in the `"market"` branch. The tab name in that assertion
  was corrected; the contract it checks is unchanged.
- The 84 remaining failures are the pre-existing red suite and were not touched.
- `npx next build`: **passes** (`✓ Compiled successfully`), exit 0. It logs the known
  `revalidate: 0` dynamic-rendering fallback for `/` and `/Market`, which the Phase 0
  baseline already documents as expected. Set-detail first-load JS **392 kB, unchanged**.

`frontend/components/explore/SetTabRequestGating.contract.test.mjs` — 11 tests
asserting **what does not load**, in the repo's existing source-contract style. All
11 now pass; 4 of them had never passed before this restoration:

- Value History is gated to Market plus the shell-seed fallback, and no longer requests the canonical scope unconditionally.
- Market still requests both its canonical and selected trend scopes.
- Scope de-duplication (`seededLoadedScopes`, `alreadyLoadedScopes`, the empty-list short-circuit) survived the gating change.
- Value History scopes are still issued via `Promise.all` — gating did not introduce a waterfall (§15).
- **Pull Rates, Top Chase, Insights Critical and Insights Secondary must stay eager on RIP**, each pinned to its proven RIP consumer. These are deliberately tripwires in the opposite direction: they fail if a future pass "optimizes away" a request RIP actually renders.
- Market-only and Cards-only requests do not fire on RIP.
- The legacy full-page snapshot set remains empty and inert.
- Every tab-gated fetch is evaluated inside a `useEffect`, so a direct `?tab=` landing fetches on mount rather than waiting for interaction (§12).

`RipStatisticsSetLoad.contract.test.js` slices the effect using
`"activeMarketDashboardDerivedState,\n  ]);"` as an end anchor, so appending a new
dependency after that line would invalidate the anchor. The new dependency
(`shellSetValueVisiblePoints.length`) is therefore **ordered before**
`activeMarketDashboardDerivedState`, with a comment at the call site saying why.

---

## Part B — the Top Chase duplicate request

Found while measuring this phase, and reported here because it dominates the byte
figures above.

Every Market and RIP visit issued **two byte-identical Top Chase requests** ~400 ms
apart, on every set. The first returned HTTP 200 with a healthy payload.

The cause was in `validateTopChasePayload`'s cross-set card check. It compared each
card's `setId` against `requested` — the normalized form of the identifier the
*caller* used. The set page asks by slug (`ascendedheroes`) while cards carry the set
UUID (`75cd439d-…`), so the two could never be equal and **every card of a healthy
payload was classified foreign**. That produced `cross_set_card_history` →
`IDENTITY_MISMATCH`, which is retryable, so the helper spent a second identical
~542 kB request and reached the same verdict again. Verified against live payloads for
all four sets: every one returned `identity_mismatch / priced=0 / renderable=0` before
the fix and `complete / priced=10 / renderable=10 / 124–128 history points` after.

The payload-level identity check immediately above it already compares against a
*candidate list* (`id` / `slug` / `canonicalKey`) precisely because callers use
different identifier forms. The fix is one line of intent: the card-level check now
uses those same verified candidates. A card from a genuinely different set is still
rejected — neither its UUID nor its slug appears among them, and a test pins that.

This was not only a bandwidth defect. Because both attempts failed validation and no
last-known-good existed, the contract's own terminal behaviour was to throw — Top
Chase was being rejected on every load for every set.

---

## Files changed

- `frontend/components/explore/RipStatisticsPageClient.jsx` — value-history scope gating (one `desiredScopes` block) plus one dependency addition.
- `frontend/lib/pokemon/topChasePayloadContract.mjs` — cross-set card check compares against the payload's verified identity candidates instead of the caller's identifier form.
- `frontend/lib/pokemon/topChaseLifecycle.contract.test.mjs` — +7 tests covering the slug/UUID case and the one-request / bounded-retry / no-pointless-retry / shared-inflight / commit-once matrix.
- `frontend/components/explore/RipStatisticsSetLoad.contract.test.js` — one obsolete tab name corrected (`"overview"` → `"market"`) plus an assertion pinning the new gate.
- `frontend/components/explore/SetTabRequestGating.contract.test.mjs` — unchanged; all 11 now pass.
- `docs/PERFORMANCE_PHASE2A_REQUEST_GATING.md` — this report, rewritten against measured behaviour.

No changes to scores, Financial RIP, Collector Appeal, ranks, tiers, EV, simulation output, pull-rate assumptions, market calculations, payload contracts, metric names, copy, design, tab architecture, routing, SEO, auth, Phase 1 image work, Recharts imports, bundle boundaries, Cards pagination, or backend schema. No dynamic imports were introduced. No endpoint contract was modified.

**Optional intent prefetch (§13) was not implemented.** It is explicitly conditional on measurement showing tab transitions got worse after gating, and they did not: the only request moved is a below-fold Market chart feed, and Market's direct-landing cost is byte-identical. Adding speculative prefetch here would have added complexity with no measured problem to solve.

---

## Deferred opportunities

Ranked by measured bytes, not by code ugliness.

1. **Top Chase payload — ~543 kB per request, `no-store`.** Now fetched once instead of twice, but still **77% of all remaining RIP API bytes** and the single largest item on the page. RIP renders a three-card preview from a response carrying 10 cards with full 365-day histories; Market renders the full table. A projected/windowed variant for the RIP preview is the highest-value remaining API win. Phase 3. The endpoint contract was **not** touched here per §9 — only the client-side validator's identity comparison.
2. **Market Overview payload — ~347–357 kB.** The largest single item on direct Market, larger than expected for a "slim" overview endpoint. Worth a projection audit alongside Top Chase. Phase 3.
3. **Insights Critical payload — ~114–115 kB.** RIP-critical and cannot be deferred, so payload projection is the only available lever. Phase 3.
4. **Rankings/targets endpoint — 2.62 MB, ~1.86 s.** Untouched per §2. Still the largest single payload in the application and the worst latency measured anywhere in Phase 0.
5. **Set JS/client splitting — 392 kB first-load, unchanged.** Phase 2B.
6. **Dead code removal.** `fetchPokemonSetPageSnapshot`, `setPageSnapshotRefreshState`, and the `false && setDetailTab === "overview"` Set Value Trend render branch are all provably unreachable. Left in place: §14 permits removal only when tightly scoped, and this phase's diff was deliberately kept minimal so the network measurement stays isolated.
7. **The Pull Rates duplicate.** Originally dismissed as harness misfiling; it **reproduced** in the before build on 151 (2 requests, 15.1 kB). It does not reproduce after this pass, but nothing here targeted the pull-rates effect, so it is unexplained rather than fixed. Confirm with dedicated instrumentation.
8. **Top Chase 503s under load.** A 40-way concurrency test measured 6/40 (15%) `POKEMON_SET_TOP_CHASE_SNAPSHOT_READ_FAILED` before this pass and 0/40 in two runs after. **This is not claimed as fixed** — the change was client-side and cannot affect a backend read failure. The duplicate removal halves Top Chase load, which may simply have moved the sample below the threshold. Needs its own backend investigation.

---

## Recommendation for the next phase

**Phase 3 (API payload slimming), not Phase 2B (JS splitting).**

Post-Phase-2A measurement, on a cold mobile RIP visit:

- RIP still transfers **~711 kB of API payload** across 4 requests, of which ~543 kB is one `no-store` response that cannot be browser-cached and is therefore re-paid on warm navigation.
- RIP transfers **392 kB of JS**, which *is* cacheable and, per Phase 0's warm measurements, costs 0 additional bytes on every repeat set navigation.

So the largest remaining *repeatable* network cost on the set page is API payload, and by a clear margin. Phase 3 also has a better risk profile for the byte win: Top Chase projection is a contained change behind a contract test, whereas Phase 2B's 392 kB is a medium-to-high-risk restructuring of a 14.6k-line client with loading, focus, routing, and data-cache behavior to preserve.

The counter-argument deserves stating fairly: Phase 0 measured 1,006 ms of mobile JS execution and 272 ms TBT on RIP, and **Phase 3 will not improve either**. Main-thread time is a real user-facing problem that only Phase 2B can address. But Phase 0 also found RIP's mobile LCP is dominated by image completion rather than TBT, which caps how much visible improvement Phase 2B can deliver on the metric users actually feel.

Recommendation: **Phase 3 first**, targeting Top Chase and Market Overview, then Phase 2B for main-thread time. If TBT/interaction responsiveness is judged the more important product goal than transfer, that ordering should be flipped deliberately — but on the bytes measured here, Phase 3 is the larger win.
