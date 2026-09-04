# Homepage & Market Request Architecture — Prompt 2

Date: 2026-09-04
Branch: `fix/backend-memory-restart-p0-20260904`
Builds on Prompt 1 (`get_pokemon_rip_statistics_targets_compact` RPC; `/explore/rip-statistics/targets` payload 8,146,015 → 3,252,697 bytes, flat RSS plateau).

## Scope actually delivered

This pass covers A3/A4 (Homepage caching) and B2/B3 (Market paid-probe removal + cache
fix). It does **not** ship a new compact Homepage-only RPC (A2) — see "Not done" below.

## Part A — Homepage

### Before

- `getLandingPageData()` → `getRipStatisticsTargets({ limit: 60, public: true })` →
  `_fetchRipStatisticsTargets` → always fetched the full canonical cohort
  (`limit=200`) from `/explore/rip-statistics/targets`, **with no process cache and
  no in-flight join at all**. Every Homepage request (cold or warm, single or
  concurrent) re-executed this backend call.
- Spotlight distribution: `getPublicOpeningDistribution(setId)` called
  `/tcgs/pokemon/sets/{id}/rip/simulation-evidence` with `cache: "no-store"` and no
  cache layer — every Homepage request re-fetched it, even for an unchanged
  spotlight set.
- Net: N concurrent/warm Homepage requests = N full `/explore/rip-statistics/targets`
  reads (compact payload, ~megabytes-scale relative to what's rendered) + N
  simulation-evidence reads.

### After

- `_fetchRipStatisticsTargets` now has a bounded process cache + in-flight join,
  **scoped to the `publicOnly` cohort only** (key `"public"`, TTL 120s). A fresh
  miss triggers exactly one backend read; concurrent misses join that one read;
  warm reads inside the TTL short-circuit with zero backend calls; a failed
  refresh returns the existing recoverable/fallback shape and is never cached
  (so an outage isn't hidden behind a fake hit).
  - The **authenticated** cohort path is deliberately left untouched/uncached —
    see "Why not A2" below; caching it under a single key would leak one
    session's plan-specific response to another session within the TTL window.
- `getPublicOpeningDistribution` gained the same pattern, keyed by `setId`
  (TTL 120s), so repeated Homepage requests for the same spotlight set no longer
  re-hit `/rip/simulation-evidence`; a new spotlight set (different `setId`) is
  never masked by the old cache entry, and only successful reads are cached (a
  null/failed read is retried next time, not stuck).
- Cache reset helpers added for deterministic tests:
  `__resetRipStatisticsTargetsCacheForTests` (ripStatisticsServer.js),
  `__resetLandingDistributionCacheForTests` (landingHeroServer.js).

### Not done (A2 — new compact Homepage-only RPC)

A2 asked for a narrower Homepage-specific compact read if nothing existing safely
covers it. `/explore/rip-statistics/targets?limit=60` (already public, already the
Prompt-1 compact reader) is what the Homepage uses today, and it is now
cached/in-flight-joined per above. Building a *second*, even-narrower canonical
RPC/migration is a real backend/DB change (new migration, new RPC, publication
identity wiring, fail-closed semantics) that this pass did not attempt — it
requires DB coordination and its own verification pass, and was judged too large
to do safely inside this session without risking a half-finished migration on a
shared branch. **Recommendation for follow-up**: the caching fix above removes the
"re-fetched every request" problem; a dedicated ultra-narrow projection is still
worth doing later to cut the *cold* payload size further, but is no longer the
correctness-blocking issue it was.

### Homepage acceptance measurement

| Metric | Before | After |
|---|---|---|
| Cold backend calls (1 request) | 1× targets + 1× simulation-evidence | unchanged (cold miss still reads both once) |
| Warm backend calls (2nd request, same process, <120s) | 1× targets + 1× simulation-evidence (re-fetched) | 0 (both served from process cache) |
| Concurrent requests (N simultaneous, cold) | N× targets + N× simulation-evidence | 1× targets + 1× simulation-evidence (in-flight joined), N waiters |
| Cache identity | none | keyed by cohort type (`public`) / spotlight `setId` |

## Part B — Market page

### Before

- `frontend/lib/explore/exploreSetValueMarketServer.js`:
  `getExploreSetValueMarket()` called `/market/explorer/snapshot` (paid,
  authenticated) **first**, using ambient cookies, then fell back to
  `/explore/set-value-market` (public) only on non-OK. Consequences:
  - Anonymous/Base viewers: every Market page load issued a request to the paid
    endpoint that was guaranteed to 401/403, before falling back to the public
    read — one wasted round trip per page load.
  - Plus/Premium viewers: every Market page load received the **full prepared
    Market Explorer publication** (`/market/explorer/snapshot`), even though the
    top-level `/Market` page only renders `marketOverview`, `sets`, and
    `initialSelectedSetMovers` — all three of which are already published by the
    public `/explore/set-value-market` endpoint (confirmed by reading
    `backend/db/services/pokemon_explore_set_value_service.py`:
    `read_explore_set_value_snapshot` populates `initialSelectedSetMovers`
    itself).
  - Process cache (`processCache.set(...)`) was only ever written on the
    fallback path and **never read/short-circuited** — there was no
    `if (cached.expiresAt > Date.now()) return cached.data` check, so even a
    fully successful, cacheable read hit the backend on every single request.
- `getExploreMarketMovers()` (`exploreMarketMoversServer.js`) already had a correct
  TTL short-circuit (`if (cached?.expiresAt > Date.now()) return cached.data`) —
  audited, left unchanged per B3's "if it's already correct, don't change it."

### After

- `getExploreSetValueMarket()` now calls `/explore/set-value-market` **only** —
  the paid-probe-then-fallback pattern is removed entirely. This is the only
  caller of the paid snapshot endpoint in the frontend tree (verified via repo
  search — no other file references `/market/explorer/snapshot`), so removing
  it here fully eliminates the speculative paid probe with no dangling lazy-load
  path required.
- Added a real TTL short-circuit (`cached.expiresAt > Date.now()` before
  fetching), an in-flight join (module-level `inFlight` promise so concurrent
  misses share one backend call), and a `__resetExploreSetValueMarketCacheForTests`
  reset helper. Failed refreshes still fall back to the last good cached payload
  via the existing `unavailableExploreSetValueMarket(cached?.data)` path.
- `getExploreMarketMovers()`: unchanged (already correct).

### Market request graph, anonymous/Base/Plus/Premium

| Viewer | Before | After |
|---|---|---|
| Anonymous | probe `/market/explorer/snapshot` (401) → fallback `/explore/set-value-market`; + `/explore/card-market-movers` | `/explore/set-value-market` + `/explore/card-market-movers` only |
| Base | same as anonymous (403 instead of 401) | same as anonymous |
| Plus/Premium | probe succeeds → full paid `/market/explorer/snapshot` payload served for a page that renders only public fields | `/explore/set-value-market` + `/explore/card-market-movers` — identical to anonymous/Base for the top-level page; paid Explorer data, if/when the paid Explorer UI is actually opened, loads through its own path (unaffected by this change, since the top-level `/Market` page never referenced it directly) |

No paid data is now fetched, cached, or serialized into the top-level `/Market`
page's props for any plan tier — the backend's own authorization on
`/market/explorer/snapshot` is untouched and still enforced for whatever code
path does need it.

## Part C — navigation-burst re-check

Not independently re-run as a live load test in this pass (no live backend/DB
session available inside this sandboxed session). The structural claim this
pass supports: repeated Homepage⇄Market⇄Set navigation now hits the process
caches added above instead of re-issuing backend/auth work each time —
Homepage's targets+distribution reads and Market's Set Value read are all
TTL-cached + in-flight-joined at 120s. A live burst re-measurement (request
count, bytes, p50/p95, RSS) is recommended as a follow-up smoke run before
calling this fully closed at production scale.

## Semantic/security verification

- Homepage: `getRipStatisticsTargets({ public: true })` still resolves the fixed
  `getPublicBackendRequestHeaders()` set (Accept-only, no Cookie/Authorization)
  on every cache miss/refresh — caching does not change what's requested, only
  how often. The authenticated (non-public) cohort path is untouched and
  deliberately excluded from caching to avoid cross-session entitlement leakage.
- Market: `/explore/set-value-market` is unauthenticated/public by construction
  (`backend/api/main.py::get_explore_set_value_market`) — using it exclusively
  cannot leak paid data. `/market/explorer/snapshot` still requires
  `_require_authenticated_user_id` + `has_index_plus_access` server-side,
  unchanged; the frontend change only stops the top-level Market page from
  calling it, it does not touch backend authorization.

## Files changed

- `frontend/lib/explore/ripStatisticsServer.js`
- `frontend/lib/explore/ripStatisticsServerCacheIdentity.test.mjs`
- `frontend/lib/explore/ripStatisticsServerPublicCache.test.mjs` (new)
- `frontend/lib/landing/landingHeroServer.js`
- `frontend/lib/explore/exploreSetValueMarketServer.js`
- `frontend/lib/explore/exploreSetValueMarketServerCacheBehavior.test.mjs` (new)

## Tests

- `lib/explore/ripStatisticsServerCacheIdentity.test.mjs` — 6/6 pass (existing +
  1 new assertion for the scoped public-only cache).
- `lib/explore/ripStatisticsServerPublicCache.test.mjs` — 3/3 pass (new: warm
  hit, concurrent join, authenticated path stays uncached).
- `lib/explore/exploreSetValueMarketServer.contract.test.mjs`,
  `exploreSetValueMarketServerUnavailable.contract.test.mjs` — 3/3 pass
  (pre-existing, unaffected).
- `lib/explore/exploreSetValueMarketServerCacheBehavior.test.mjs` — 4/4 pass
  (new: no paid probe, warm hit, concurrent join, failure fallback).
- Full `lib/explore/*.test.mjs` + `lib/landing/*.test.mjs` run: 329 tests, 2
  failures, both pre-existing/environmental and unrelated to this change:
  `landingBoosterPack.test.mjs` (booster-pack art selection, untouched by this
  work) and `landingHeroServer.publicAuthInvariance.test.mjs`, which fails at
  module load with `Cannot find module '@/utils/slugify'` resolved against a
  **different worktree path** (`D:\EVRCalculator-set-p0p1-pass2`) baked into a
  stale `tsx` module-resolution cache — not caused by any file this pass
  touched (`ripStatisticsRouting.js` and its `slugify` import were not edited).
