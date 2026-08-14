# Full-System Performance Audit — inDex

Audit-only pass. No production code was changed; all instrumentation has been removed.

## Measurement environment

| | |
|---|---|
| Branch / SHA | `feature/perf_updates_two` @ `93f7388f8dd04a518e244f280d264aee8924e243` |
| Frontend build | isolated production (`PERF_AUDIT_DIST_DIR=.next-audit`, `next start -p 3100`) |
| Backend | local `uvicorn backend.api.main:app` (no `--reload`) against **live** Supabase |
| Browser | Playwright 1.62.1 Chromium, fresh context per run |
| Desktop profile | 1440×900, no throttling, 10 runs/measure |
| Mobile profile | Pixel 7 device emulation, **4× CPU throttle**, 10 Mbps / 40 ms RTT, 5 runs/measure |
| Warm/cold | "warm" = warm server process + fresh browser context. Cold-process runs are called out explicitly |
| Backend sweep | 1 cold + 7 warm per endpoint |

**Known contamination:** the V8 migration (below) makes Overall RIP and Collector Appeal unresolvable
on live data. Document sizes for Rankings/Home are therefore *smaller* than they will be once V8
publishes, and any "Unavailable" UI state seen during this audit is migration state, not a perf fault.

---

## 1. Executive summary

**Is the site broadly performant? Yes, on the server and on transfer — with one broken surface and one
large outlier.**

Home, Rankings and Market are all fast: TTFB 7–10 ms, FCP 44–48 ms, LCP 148–236 ms desktop; TBT ~0.
The prior optimizations all hold. But three things stand out:

1. **P0 — Overall RIP and Collector Appeal are unavailable sitewide.** The frontend reads V8; the
   snapshot published today at 18:07 contains only V7. Measured on live data: **0/34 targets resolve
   Overall RIP, 0/34 resolve Collector Appeal, 0/34 produce a Rankings score/rank/tier.** This is a
   functional migration gap, not a latency defect, but it is the most severe finding.
2. **P1 — the set page is a 4 MB page.** 1,653,134 B document (215 KB gzip), 723 KB of eager API, and
   1,470,616 B of JS. 97.6% of its client boundary is `targetsPayload`, of which the client reads 0.77%.
3. **P1 — the RIP tab eagerly downloads 556 KB of `/market/top-chase`** to render a three-card preview.

---

## 2. System performance map

Desktop, warm server, fresh context, 10 runs, p50.

| Route | TTFB | FCP | LCP | TBT | doc gzip | doc raw | JS | total bytes | reqs | LCP element |
|---|---|---|---|---|---|---|---|---|---|---|
| `/` | 7 | 44 | 148 | 0 | 14,657 | 57,027 | 847,110 | 1,105,473 | 29 | `H1` |
| `/Rankings` | 8 | 48 | 236 | 0 | 17,621 | 146,433 | 890,644 | 1,515,164 | 68 | ambient `IMG` |
| `/Market` | 10 | 48 | 228 | 0 | 24,253 | 219,561 | 887,600 | 1,726,600 | 85 | ambient `IMG` |
| set page (RIP) | 49 | 220 | 232 | 16 | 215,299 | **1,653,080** | **1,470,616** | **4,051,085** | 44 | ambient `IMG` |

Mobile (Pixel 7, 4× CPU, 10 Mbps), 5 runs, p50:

| Route | FCP | LCP | TBT | long tasks | load | total bytes |
|---|---|---|---|---|---|---|
| `/` | 272 | 692 | 109 | 3 | 573 | 1,116,511 |
| `/Rankings` | 308 | 312 | 54 | 3 | 634 | 1,243,793 |
| `/Market` | 272 | 272 | 57 | 3 | 571 | 1,423,210 |
| set page (RIP) | 284 | **780** | **234** | 4 | 975 | **4,053,704** |

Transitions from the RIP tab (desktop, 10 runs, p50):

| Transition | click→usable | first API | API bytes | API count | RSC bytes |
|---|---|---|---|---|---|
| → Cards (no dwell) | **463** | 64 | 185,694 | 1 | 1,456,738 |
| → Cards (250 ms dwell) | **173** | prefetched | 185,694 | 1 | 1,456,738 |
| → Market | ~95–103 | 72–78 | **592,505** | **4** | 1,725,433 |
| → Pull Rates | 75–77 | none | 0 | 0 | ~0 |
| → Cards, mobile (no dwell) | **623** | 48 | 185,693 | 1 | 1,456,788 |
| → Market, mobile | — | 159 | **687,113** | **6** | 1,725,481 |

---

## 3. RSC / client-boundary byte attribution

Props crossing into `PokemonSetPageClient` (`"use client"`), serialized:

| Prop | bytes | share |
|---|---|---|
| `targetsPayload` | **1,414,927** | **97.6%** |
| ↳ `.targets[]` | 1,407,415 | 97.1% |
| ↳ `.meta` | 7,402 | 0.5% |
| ↳ `.default_target` | 72 | — |
| `shellPayload` | 34,901 | 2.4% |
| **total** | **1,449,828** | 100% |

**The hypothesis is confirmed.** `targetsPayload` is essentially the entire set-page client boundary,
and it maps directly onto the observed 1,456,738 B RSC per tab hop and the 1,653,134 B document.

Client consumption of `targets[]`, traced through `RipStatisticsPageClient`:

| Consumer | Fields |
|---|---|
| set switcher (4 render sites incl. hero picker) | `target_type`, `target_id`, `name` |
| adjacent-set prefetch | `id` |
| eligibility (`isPublicAnalyticsEligiblePokemonSet`) | `name`, `era`, `eraId`/`era_id` |
| warnings banner | `meta.warnings` |

> `targets[]` full: **1,407,415 B** — client-consumed: **10,839 B (0.77%)**
> Projected props (identity fields + shell + meta): **~45,740 B** vs **1,449,828 B** → **−96.8%**

`targetHrefById` and `selectedTarget` are already separate, correctly-sized props.

**Attribution answer:** the ~1.46 MB RSC per tab hop is caused by `targetsPayload` and essentially
nothing else. No other prop contributes materially.

---

## 4. Frontend / API findings (ranked)

### P0 — V8 contract published nowhere; frontend reads V8 only
Live probe through the real readers (`resolveCanonicalRipV7`, `exploreRankingConfig`):

```
targets: 34
canonical Overall RIP resolvable : 0 / 34
Collector Appeal resolvable      : 0 / 34
Financial RIP resolvable         : 22 / 34
Rankings "overall" mode score    : 0 / 34
sample rank/tier                 : null null
```

Snapshot `builtAt 2026-08-13T18:07:04Z` carries `publicRipContractV7` 34/34 and `publicRipContractV8`
**0/34**. The live builder (`explore_rip_statistics_service.py:1999`) *does* attach V8
unconditionally, so the published row simply predates the V8 code. Secondary effect: `rankTargets` in
`app/Explore/page.js` sorts on `overallRipV8.rank`, which is null for every set — **the Rankings order
itself is currently name-ordered, not rank-ordered.**
*Evidence: measured. Impact: critical-path/functional. Fix confidence: high. Risk: low (republish).*

### P1 — set page ships 1.65 MB document / 1.46 MB RSC per tab hop
Root cause quantified in §3.
*Evidence: measured. Impact: transfer + mobile main-thread. Fix confidence: high (pattern proven twice).
Estimated benefit: −96.8% of client-boundary bytes; document ~1.65 MB → ~250 KB. Risk: low-medium.*

### P1 — RIP tab eagerly fetches 556 KB of `/market/top-chase` for a 3-card preview
The RIP tab's initial load issues 4 client API requests totalling **723,194 B**:

| Endpoint | bytes |
|---|---|
| `/market/top-chase` | **556,284** |
| `/insights/critical` | 117,064 |
| `/insights/secondary` | 42,689 |
| `/pull-rates` | 7,157 |

Note the same endpoint measured **200,199 B** directly against the backend — the proxied request
returns ~2.8× more, worth confirming (different window/params).
*Evidence: measured. Impact: transfer + backend cost. Fix confidence: medium. Risk: low.*

### P2 — Market tab issues 4–6 client requests totalling ~592 KB (desktop) / ~687 KB (mobile)
`/overview` 369,543 + `/market/top-chase` 556,284 + `/market/sealed` 93,791 + `/market/movers` 34,561
+ `/market/value-history` 94,609 on direct load. Perceived transition is still fast (~95–103 ms) because
the first paint does not wait for all of them, so this is transfer/backend cost, not critical path.
*Evidence: measured. Impact: transfer/backend-cost. Fix confidence: medium. Risk: low.*

### P2 — Cards intent prefetch only helps when the pointer dwells
With 250 ms dwell: 173 ms. With no dwell (fast click, keyboard, touch tap): **463 ms desktop / 623 ms
mobile** — i.e. the pre-optimization figure. The optimization is correct and valuable, but its benefit
is conditional; keyboard and fast-click users get none of it.
*Evidence: measured. Impact: critical-path for a subset of users. Fix confidence: medium. Risk: low.*

### P3 — Pull Rates does NOT have the Cards problem
Explicitly investigated per the brief. RIP→Pull Rates is **75–77 ms desktop / 110 ms mobile with zero
API requests**, because `/pull-rates` (7,157 B) is already fetched during the RIP tab's initial load.
**No intent prefetch is warranted.** The eager fetch is cheap and already acts as a prefetch.

---

## 5. Backend API findings

1 cold + 7 warm per endpoint, live Supabase.

| Endpoint | cold | p50 | p95 | bytes |
|---|---|---|---|---|
| `cards/validation` | 0.842 | **0.777** | 5.146 | 211,400 |
| `rip-statistics/targets?limit=200` | 0.566 | 0.506 | 3.400 | 1,425,895 |
| `pull-rates` | 0.505 | **0.499** | 4.051 | **7,155** |
| `insights` | 0.506 | 0.502 | 4.196 | 82,680 |
| `insights/secondary` | 0.506 | 0.497 | 0.542 | 42,687 |
| `cards/page` | 0.368 | 0.368 | 0.382 | 185,694 |
| `market/top-chase` | 0.366 | 0.372 | 3.882 | 200,199 |
| `market/movers` | 0.314 | 0.316 | 0.340 | 18,006 |
| `shell` | 0.190 | 0.194 | 0.419 | 34,927 |
| `sealed` | 0.130 | 0.135 | 4.113 | 93,791 |
| `overview` | 0.132 | 0.113 | 3.388 | 369,544 |
| `card-market-movers` | 0.116 | 0.061 | 0.066 | 79,029 |

**P1 — `pull-rates` costs ~500 ms for 7 KB.** Worst work-per-byte ratio in the system by two orders of
magnitude; the cost is backend compute/DB, not transfer. Prime candidate for query-level investigation.

**P1 — p95 spikes of 3.4–5.1 s appear across six unrelated endpoints simultaneously** (targets,
pull-rates, insights, top-chase, sealed, overview) while their p50s stay 0.1–0.8 s. Unrelated endpoints
degrading together points at a **shared-resource contention** event rather than per-endpoint cost —
consistent with the carry-forward scheduler-isolation concern. *Evidence: measured but only 7 samples
per endpoint; needs a longer window before acting.*

**P2 — `cards/validation` at 0.777 s / 211 KB** is the slowest single endpoint.

---

## 6. Database findings

Read-only inspection only; **no queries were altered and no indexes created.** I did not obtain
per-endpoint query plans in this pass, so DB findings are limited to what the API timings imply:

- `pull-rates` returning 7 KB in ~500 ms is the strongest signal of an expensive or repeated query
  behind a small result. **Recommend `EXPLAIN` on its read path before any change.**
- The `targets` document (1.43 MB) remains dominated by moving one large JSONB row across the DB
  boundary — previously measured at ~408 ms PostgREST, unchanged and expected.

*This is a genuine coverage gap in this audit, stated rather than papered over.*

---

## 7. Cache findings

| Cache | Owner | Key | TTL | In-flight join | Caches failures | Notes |
|---|---|---|---|---|---|---|
| targets cohort | `ripStatisticsServer` | single canonical key | 120 s | yes | no (stale fallback) | shared by Rankings/Market/set page — **correct, do not fragment** |
| global movers | `exploreMarketMoversServer` | `"7D"` | 120 s | via `react cache` | no | fine |
| landing distribution | `landingHeroServer` | set id | 120 s | no | no | added earlier; correct |
| cards-page result | `pokemonSetCardsClient` | full request `cacheKey` | 60 s | yes | **no** | identity proven by test |
| full cards snapshot | `pokemonSetCardsClient` | set id | **24 h** | yes | no | long TTL for price-bearing data — worth reviewing |
| Next data cache | framework | — | — | — | — | bypassed for cards/market-dashboard (2 MB entry limit) |

No duplicate caches over the same source were found. No identity mismatches found. The one item worth
a second look is the **24 h** full-snapshot cards cache, which holds market prices.

---

## 8. Images / JS / hydration / fonts

- **Logo regression check passes**: `/Rankings` issues 22 optimized logo requests at `w=96` totalling
  **64,072 B** — exactly the documented post-fix figure. Plus 1× `w=64` and 1× `w=128`. No regression.
- **Ambient decorative artwork is still the desktop LCP element** on Rankings, Market and the set page.
  Desktop LCP is 228–236 ms, so this is now **P3, not P2** — it is no longer meaningfully harmful.
  On *mobile* the LCP element is instead `IMG.index-loader-logo` (the loading logo) on Rankings/Market,
  meaning real content paints after the loader — worth a look, but LCP is 272–312 ms, still good.
- **JS is the largest remaining fixed cost**: 847 KB (Home) / 891 KB (Rankings) / 888 KB (Market) /
  **1,471 KB (set page)**. Set-page mobile TBT is 234 ms with 4 long tasks — the only surface where
  main-thread cost is visible. *P2, and only for the set page.*
- **CSS 130–171 KB uncompressed, fonts 24,576 B, CLS ≈ 0** on every route, desktop and mobile. Nothing
  actionable. *P3.*

---

## 9. Scalability findings

- **`targetsPayload` scales with total set count** and is shipped to the browser on every set page and
  every tab hop. At 34 sets it is 1.4 MB; this grows linearly with the catalogue and is the clearest
  unbounded-growth risk in the client path. *P1 scalability, same fix as §3.*
- `targets?limit=200` builds the entire cohort regardless of limit (documented and intentional), so
  cohort growth raises cost for every consumer simultaneously.
- `cards/page` is properly paginated (60/page) and does **not** scale with set size — good.
- Set-page eager API (723 KB) scales with cards-per-set via `top-chase`.

---

## 10. Regression verification

| Previously optimized path | Status | Evidence |
|---|---|---|
| Rankings → set SSR | **holds** | warm p50 **57 ms** total / 49 ms TTFB, 10 runs |
| Logo sizing | **holds** | 22 logos @ `w=96` = 64,072 B (matches documented fix exactly) |
| Rankings client projection | **present** | `projectRankingsTargets` wired in `app/Explore/page.js` |
| Market client projection | **present** | `projectMarketRankingTargets` wired; doc 219,561 B / 24,253 gzip |
| Landing distribution cache | **present** | `DISTRIBUTION_TTL_MS`; Home TTFB 7 ms |
| Canonical targets cache | **present** | single shared key intact |
| Cards intent prefetch | **holds** | 173 ms with dwell vs 463 ms without |

Nothing regressed.

---

## 11. V8 migration effects (functional, not performance)

- Frontend reads `overallRipV8` / `publicRipContractV8`; published snapshot has V7 only.
- Consequence: Overall RIP and Collector Appeal render Unavailable everywhere; Rankings order falls
  back to name order.
- **Measurement contamination:** Home doc is 57,027 B and Rankings doc 146,433 B *because* scores are
  missing — both will grow once V8 publishes. Set-page and Market figures are essentially unaffected
  (their bulk is `targetsPayload` and images).
- Financial RIP still resolves for 22/34 because its config reads top-level `financialRipV3`.
- No V7/V8 dual-normalization cost was observed on the client; the reader resolves one shape only.

---

## 12. Top remaining issues

| # | Issue | Sev | Measured impact | Root cause | Recommended fix | Est. benefit | Risk |
|---|---|---|---|---|---|---|---|
| 1 | Overall RIP / Collector Appeal unavailable sitewide | **P0** | 0/34 targets resolve; Rankings mis-ordered | published snapshot is V7, frontend reads V8 | republish rankings snapshot from current backend | restores core product | low |
| 2 | Set page 1.65 MB doc / 1.46 MB RSC per tab hop | **P1** | 97.6% of client boundary; client uses 0.77% | `targetsPayload` crosses into `PokemonSetPageClient` | client-boundary projection (proven pattern) | doc → ~250 KB; −96.8% props | low-med |
| 3 | `pull-rates` ~500 ms for 7 KB | **P1** | worst work-per-byte in system | backend/DB compute | `EXPLAIN` its read path first | up to ~450 ms/call | low |
| 4 | 3.4–5.1 s p95 across 6 unrelated endpoints | **P1** | tail latency for real users | probable shared-resource contention (scheduler) | longer sampling window, then isolate | removes worst tail | medium |
| 5 | RIP tab eagerly pulls 556 KB top-chase for 3 cards | P1 | 723 KB eager API per set page | over-broad endpoint for a preview | slim preview contract or reuse | ~500 KB/page | low |
| 6 | Market tab 4–6 requests / ~592–687 KB | P2 | transfer + backend cost | five independent module fetches | consolidate or defer below-fold | ~300 KB | low |
| 7 | Cards prefetch benefits only dwelling pointers | P2 | 463 ms desktop / 623 ms mobile without dwell | intent signal requires hover time | also warm on tab-bar focus/first paint of set page | −290 ms for non-dwell | low |
| 8 | Set page JS 1.47 MB, mobile TBT 234 ms | P2 | only surface with visible main-thread cost | monolithic 14.6k-line client component | split by tab | lower TBT | medium |
| 9 | 24 h TTL on price-bearing full cards snapshot | P3 | staleness risk, not latency | long TTL | review TTL | correctness | low |
| 10 | Ambient decorative artwork is LCP element | P3 | LCP 228–236 ms desktop | decorative image wins LCP | leave; no longer material | marginal | low |

---

## 13. ONE next optimization

**Republish the rankings snapshot so the V8 contract exists (issue #1).**

Not the `targetsPayload` projection. The projection is real, is the largest *performance* item, and is
correctly identified — but the product is currently showing no Overall RIP score, no Collector Appeal
and a mis-ordered leaderboard on every surface. A 1.4 MB payload on a page whose headline numbers all
read "Unavailable" is the second problem, not the first. Issue #1 is also far cheaper and lower risk:
it needs a publish from current backend code, not a code change.

Explicitly: **if the V8 publication is already scheduled or the migration is intentionally mid-flight,
then the answer becomes the `targetsPayload` client-boundary projection**, which §3 proves is the
largest remaining performance issue by a wide margin.

## 14. Follow-on queue

1. `targetsPayload` → `PokemonSetPageClient` client-boundary projection (P1, −96.8% props)
2. `pull-rates` query investigation (P1, `EXPLAIN` first)
3. p95 contention study — longer sampling window before touching the scheduler (P1)
4. RIP tab's 556 KB `top-chase` preview fetch (P1)
5. Market tab request consolidation (P2)
6. Cards prefetch for non-dwelling interactions (P2)
7. Set-page JS split by tab (P2)
8. 24 h cards-snapshot TTL review (P3)

## 15. Files changed

Documentation only: this file. All harnesses (`__audit.mjs`, `__probe.mjs`, `__cards.mjs`,
`__bench.mjs`, `__parity.mjs`, `__correctness.mjs`) and all `.next-*` audit build directories were
removed; port 3100 released. No production code, no scoring code, no snapshots, no commits.

## 16. Coverage gaps (stated, not hidden)

- No SQL query plans captured; DB findings are inferred from API timings.
- Insights/Analysis tab transition not measured — the tab control did not match the harness locator.
- INP not measured directly; TBT and long-task counts used as the interaction proxy.
- Backend p95 based on 7 samples/endpoint — enough to flag the spikes, not to characterise them.
- Set A → set B while retaining tab, and back/forward, were verified functionally in the previous
  pass but not re-timed here.
