# Performance — Set Navigation + Cards Critical Path

Branch `feature/perf_updates_two`, starting SHA `ca2b4e101c92369388798922bb7a293330b12525`.
Backend local against live Supabase; frontend measured from isolated production builds
(`PERF_AUDIT_DIST_DIR`). Prior fixes confirmed present at start: Rankings client projection, Market
client projection, landing distribution process cache, canonical targets process cache.

> **Environment caveat.** A Collector Appeal / Overall RIP **V7 → V8 migration is in flight** in this
> working tree (backend `062_update_public_rip_rpc_to_v8.sql`, `public_rip_contract_v8.py`, and the
> matching frontend readers). The frontend now reads `overallRipV8` / `publicRipContractV8`, but the
> **published snapshot still carries V7 only**. Both before/after arms below were therefore built from
> the SAME current source, differing only in the change under test, so the comparison is internally
> valid — but the absolute numbers were taken while set-page RIP values render unavailable.

---

## User paths and representative sets

| Set | Cards | Role |
|---|---|---|
| Paradox Rift | 266 | the ~200-300 card set |
| Perfect Order | 124 | differently sized modern set |

---

## Cards transition baseline

10 runs per transition, hover + 250 ms dwell + click, isolated production build. All times ms, p50.

| Transition | click→usable | RSC duration | RSC ends | API starts | API duration |
|---|---|---|---|---|---|
| ParadoxRift RIP→Cards | 463 | 85 | 173 | 60 | 395 |
| ParadoxRift Market→Cards | 474 | 100 | 198 | 73 | 400 |
| ParadoxRift Pull Rates→Cards | 457 | 88 | 155 | 47 | 402 |
| PerfectOrder RIP→Cards | 349 | 84 | 185 | 73 | 267 |
| PerfectOrder Market→Cards | 344 | 88 | 186 | 68 | 266 |
| PerfectOrder Pull Rates→Cards | 323 | 39 | 139 | 49 | 264 |

Direct cold Cards: ParadoxRift 648, PerfectOrder 551.

These are already well below the historical ~923-1049 ms cited for this path — earlier phases moved
Cards onto its own slim paginated contract, and that shows.

---

## Transition lifecycle — the assumption was wrong

The brief's hypothesis was a serial `router.push` → RSC → server → commit → Cards fetch chain, with
the RSC round-trip dominating. **The measurements say otherwise.**

```
click
 ├─ ~50-70 ms   Cards page-1 request STARTS
 ├─ ~85-100 ms  RSC round-trip duration
 ├─ ~140-200 ms RSC response COMPLETE          <-- finished long before content
 └─ ~450 ms     Cards response lands -> first tile paints
```

The RSC navigation and the Cards request overlap. The RSC leg completes at ~150-200 ms and then the
page waits a further ~250-300 ms for Cards data. **The Cards page-1 API is the critical path; the RSC
round-trip is not.** Removing the RSC hop entirely could not have bought more than the ~60 ms head
start the API already has.

RSC payload is nonetheless large — 1,456,738 B per tab hop (the set page document is 1,654,237 B /
215,524 gzip, because `targetsPayload` crosses into `PokemonSetPageClient`). It does not gate first
Cards content, so it is recorded as a separate opportunity rather than fixed here.

---

## Cards API / backend decomposition

`GET /tcgs/pokemon/sets/{id}/cards/page?page=1&page_size=60` measured directly against the backend,
8 runs each:

| Set | TTFB p50 | total p50 | bytes | cards |
|---|---|---|---|---|
| Paradox Rift | 0.433 s | 0.434 s | 185,694 | 60 |
| Perfect Order | 0.273 s | 0.274 s | 186,580 | 60 |

Backend time, not client parsing, is essentially the whole figure (TTFB ≈ total). One request per
transition — no duplicates.

---

## Existing prefetch behavior

Instrumented, not inferred:

- **Set switching** already prefetches: `handleTargetPrefetch` → `router.prefetch(href)` +
  `warmSetDetailResources`, wired to hover/focus on the set pickers.
- **`warmSetDetailResources` is route-prefetch only** and deliberately fetches no module data — an
  earlier phase removed an eager cards/market data prefetch that fanned out across hovered and
  adjacent set ids. A contract test guards that removal.
- **Tabs had no prefetch of any kind.** Tab clicks went straight to `router.push`. Nothing warmed
  Cards on hover, focus, pointerdown, or from a sibling tab.
- `getPokemonSetCardsPage` had only a **concurrent** in-flight join — no result cache — so a prefetch
  that finished before the click would have been discarded and the click would have re-requested the
  identical URL.

---

## Root cause

Moving into Cards costs ~450 ms because the page-1 Cards request (~270-400 ms of backend time) does
not begin until the tab is activated, and nothing warms it beforehand. The user's pointer is
typically resting on the tab for a few hundred milliseconds before the click — time currently spent
idle.

---

## Production change

Two parts, both intent-driven, no routing change.

1. **`lib/pokemon/pokemonSetCardsClient.js`** — a 60 s result cache for completed `cards-page`
   responses, keyed by the request's existing `cacheKey` (set id, contract version, page, page size,
   sort, direction, query, rarity, movement filter/sort/metric, section). Successful responses only,
   so the Retry path is unaffected. Plus `prefetchPokemonSetCardsPage`, which calls
   `getPokemonSetCardsPage` itself — guaranteeing identical key derivation — and swallows errors.

2. **`components/explore/RipStatisticsPageClient.jsx`** — `handleSetDetailTabIntent`, wired to
   `onPointerEnter` / `onFocus` / `onPointerDown` on the tab control via a new optional
   `onOptionIntent` prop on `SectionViewTabs`. It warms **page one of the active set only**, using the
   exact argument expressions the cards-page effect uses, gated on the same
   `canFetchSetDetailModules`.

It never preloads other sets, further pages, images, Market Movers mode, or search results.

---

## Prefetch / cache identity proof

`lib/pokemon/pokemonSetCardsPrefetch.test.mjs`, 8 tests, counting real fetches against the module:

- prefetch and render request the **identical URL**
- a completed prefetch removes the render's network request **entirely** (1 request total)
- the reused payload is byte-identical to what the render would have fetched
- every scope change (page, sort, direction, query, rarity, movementFilter, movementMetric, section)
  is a **different identity** and still fetches
- a different set is a different identity
- a failed prefetch is not cached, returns null, and leaves the render free to retry
- prefetch never rejects on a missing set id
- concurrent prefetch + render still issue one request (in-flight join)

---

## Before / after

Both arms built from the same source; the only difference is whether `onOptionIntent` is wired.
10 runs each, hover + 250 ms dwell + click. **click → first usable Cards content, p50 / p95 (ms):**

| Transition | before | after | Δ p50 |
|---|---|---|---|
| ParadoxRift RIP→Cards | 463 / 477 | **173 / 199** | **−63%** |
| ParadoxRift Market→Cards | 474 / 2142 | **176 / 330** | **−63%** |
| ParadoxRift Pull Rates→Cards | 457 / 482 | **151 / 183** | **−67%** |
| PerfectOrder RIP→Cards | 349 / 706 | **100 / 122** | **−71%** |
| PerfectOrder Market→Cards | 344 / 2214 | **107 / 125** | **−69%** |
| PerfectOrder Pull Rates→Cards | 323 / 367 | **96 / 110** | **−70%** |
| ParadoxRift direct cold Cards | 648 | 640 | unchanged (expected) |
| PerfectOrder direct cold Cards | 551 | 519 | unchanged (expected) |

Every intent-known transition is now **96-176 ms**, comfortably inside the <300-400 ms target, and
direct cold entry is unchanged because there is no intent signal to act on there.

Request count is unchanged at one `/cards/page` per transition — the prefetch **replaces** the
click-time request rather than adding one. Repeated hovering issues at most one request.

> **Measurement note.** In the after arm the harness's `apiStart` / `apiDuration` columns are
> meaningless: the request now fires during hover, before the harness's click timestamp exists, so
> those two fields go negative. `clickToUsable` is measured from the real click and is the figure
> reported. Likewise the harness's `urlOk` flag read false in the after arm purely because it sampled
> the URL sooner than `router.push` committed — disproved by the correctness suite below.

---

## Back/forward/deep-link correctness

13/13 passed against the after build:

| Check | Result |
|---|---|
| URL becomes `?tab=cards` after click | PASS |
| Cards grid rendered (60 tiles) | PASS |
| back leaves `?tab=cards` | PASS |
| forward restores `?tab=cards` | PASS |
| Cards render after forward | PASS |
| Cards render after refresh | PASS |
| URL survives refresh | PASS |
| direct deep link renders Cards | PASS |
| set A → set B shows different cards (no stale carry-over) | PASS |
| set B URL correct | PASS |
| Cards → Market → Cards still renders | PASS |
| hover alone does not navigate | PASS |
| repeated hover de-duplicates to one request | PASS |

---

## Tests

- `pokemonSetCardsPrefetch.test.mjs` — 8 new tests, all pass.
- `RipStatisticsSetLoad.contract.test.js` — the existing guard forbidding the removed eager
  full-snapshot prefetch matched `prefetchPokemonSetCardsPage` by substring. The guard's **intent** is
  preserved (that ban is about fanning out data fetches across hovered/adjacent sets); it was
  tightened to a word-boundary match on the old symbol, the warmup-path ban was left covering **both**
  symbols, and a new positive test pins the new prefetch as active-set-only, page-one-only,
  Cards-only, gated, and driven by pointer/focus intent rather than an effect.
- Failure-set parity verified by stashing the change: the file fails **the identical 17 tests** with
  and without it. Those 17 are pre-existing, from the in-flight V7→V8 migration, and are not touched
  here.

---

## Carry-forward

Documented, not fixed: Top Chase backend 503 load reliability; Pull Rates lifecycle; production
scheduler isolation; ambient decorative LCP on Rankings/Market. Newly recorded: the set page ships
**1,654,237 B / 215,524 gzip** and re-sends ~1.46 MB of RSC on every tab hop because `targetsPayload`
crosses into `PokemonSetPageClient` — the same client-boundary pattern already fixed on Rankings and
Market, and the largest remaining transfer on the site.
