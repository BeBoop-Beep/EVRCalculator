# Homepage & Market Request Architecture — Prompt 2

Date: 2026-09-04
Branch: `fix/backend-memory-restart-p0-20260904`
Builds on Prompt 1 (`get_pokemon_rip_statistics_targets_compact` RPC; `/explore/rip-statistics/targets` payload 8,146,015 → 3,252,697 bytes, flat RSS plateau).

## Scope actually delivered

This pass covers A3/A4 (Homepage caching) and B2/B3 (Market paid-probe removal + cache
fix). A2 (a new narrow compact Homepage-only Rankings projection) was **not** shipped
in the original pass — see "Not done" below — but is now implemented in a follow-up
pass; see "Part D — A2" near the end of this document.

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

## Part D — A2: narrow public Homepage Rankings projection (this pass)

This closes the "Not done"/A2 gap noted above: the Homepage no longer sources
its landing Rankings module from the general-purpose compact
`/explore/rip-statistics/targets` cohort at all.

### Phase A — fields the Homepage actually consumes

Traced `frontend/app/page.js` -> `getLandingPageData()`
(`frontend/lib/landing/landingHeroServer.js`) -> `selectLandingHeroEntries`
(`landingHeroSpotlight.mjs`) -> `selectExploreRankingRows` /
`selectHeroRankingVisuals` / `selectMarketContext` (`landingPreviews.mjs`).
Every field actually read, by module:

- **Identity/imagery**: `target_type`, `target_id`, `name`, `era`,
  `canonical_key`/`canonicalKey`/`slug`, `hero_image_url`/`heroImageUrl`,
  `logo_image_url`, `symbol_image_url`.
- **Set RIP V1 (the Homepage's ONE ranking authority)**: `setRipV1.score`,
  `.rank`, `.tier`, `.cohortSize`, `.rankable` -- never Overall RIP, never
  Financial RIP, never legacy `pack_rank` (see the comment block at the top of
  `landingHeroSpotlight.mjs`).
- **Set Value**: `checklist_set_value` (+ `_as_of`/camelCase variants),
  `current_checklist_set_value` (+ `_date`), `previousChecklistSetValue7d`,
  `setValueComparisonStatus7d`.
- **Opening economics**: `pack_cost`, `mean_value`, `median_value`,
  `prob_profit`, `expected_loss_per_pack` (all camelCase variants too).
- **Desirability/Collector Appeal**: `universalSetDesirability.score`/`.rank`,
  `collector_appeal_score`, `desirability_is_fallback`.
- **Freshness**: `meta.comparisonSnapshots.currentMarketDate` (for
  `selectMarketContext`'s `marketDate`).

Explicitly confirmed **not needed**: product rankings
(`productFamilyRankings`), `openingExperience`, pack/profit/safety/stability
detail scores, `financialRipV4`/`overallRipV10`/`publicRipContractV10`
blocks, `rankingsChase`/`topChase`, or any simulation distribution (the
spotlight distribution is a separate, already-cached read against
`/tcgs/pokemon/sets/{id}/rip/simulation-evidence`, untouched by this pass --
see Part A above). Ranking movement/comparison and spotlight chase identity
are not rendered by the current Homepage and are not in the new contract.

### Phase B -- existing projections checked, neither sufficient

`get_pokemon_rankings_sets_lens` (the Rankings page's compact "sets" lens,
`20260830010000`) was checked field-by-field against Phase A and does **not**
cleanly cover the contract: it is missing `hero_image_url`,
`previousChecklistSetValue7d`/`setValueComparisonStatus7d`,
`collector_appeal_score`, and `desirability_is_fallback`, and it uses
`expected_loss_when_losing` where the Homepage reads `expected_loss_per_pack`
(a different published field, not a rename). It also carries several nested
blocks (`overallRipV8/9/10`, `financialRipV3/4`, `rankingsChase`/`topChase`,
`publicRipContract*`) the Homepage never reads. Reusing it as-is would either
under-serve the Homepage or force it back to over-fetching -- routing
Homepage through the general `/targets` endpoint was ruled out for the same
reason (exactly what this task exists to fix). No other public
leaderboard/landing/market summary projection in the repo covers this
contract either. Conclusion: build a new, narrower projection (Phase C).

### Phase C/D/E -- the new projection

Added `get_pokemon_rankings_homepage_lens(p_limit)` +
`project_pokemon_homepage_rankings_target(target)` in
`supabase/migrations/20260904020000_add_homepage_rankings_summary_rpc.sql`,
mirroring the `get_pokemon_rankings_sets_lens` pattern exactly (same
publication table, same `CROSS JOIN LATERAL ... WITH ORDINALITY` row-ordering,
same `is_opening_set` filter, reusing the existing
`project_rankings_json_keys` helper rather than redefining it). It is a
**pure projection**: no score/rank/tier recomputation, no cohort-membership
recomputation -- `LIMIT` is applied only after the publication's own
`ORDER BY ordinality` (i.e. its own rank order) is preserved. The field list
is exactly (and only) what Phase A found, including a narrowed `setRipV1`
(`score`/`tier`/`rank`/`cohortSize`/`rankable` -- no `familyScores`/
`participatingFamilies`/etc., which the sets lens does carry) and a narrowed
`universalSetDesirability` (`score`/`rank`, no `rankedSetCount`).

Backend wiring (`backend/db/services/pokemon_public_snapshot_service.py`):
added a `"homepage"` lens to the existing generic
`get_pokemon_explore_rankings_lens_payload()` reader (the same function the
`sets`/`eras`/`products` lenses already share), so the **existing fail-closed
publication-identity check** (`_rankings_publication_identity_mismatches`,
Phase E) applies automatically -- no second version authority was
introduced. A Python-side whitelist (`_project_public_homepage_rankings_target`,
a literal field-list mirror of the SQL projection, commented as such) is
applied unconditionally to the lens's `targets`, so the contract stays
public-safe even on the JSON-path fallback branch (used only during a
rolling deploy before the RPC migration reaches PostgREST, which otherwise
returns the full unfiltered target). New wrapper:
`get_pokemon_homepage_rankings_summary_payload(limit)`.

New route: `GET /explore/rankings/homepage-summary` (`backend/api/main.py`).
Deliberately takes **no** `Authorization`/`Cookie` parameters in its function
signature at all -- there is no session state for it to resolve, unlike
`/explore/rip-statistics/targets` and `/explore/rankings/lens/{lens}`, which
both resolve plan entitlement first. Neither of those two existing routes,
nor their backing service functions, was modified.

### Phase F -- Homepage cache integration

`frontend/lib/explore/ripStatisticsServer.js` gained
`getHomepageRankingsSummary()`: its own bounded process cache + in-flight
join (120s TTL, single fixed cache key -- this endpoint is always public, so
there is only ever one entry, mirroring the existing `PUBLIC_COHORT_KEY`
pattern for `/targets`). It is a **separate** cache from the general
`/targets` cohort cache -- a different, smaller backend contract, not
another cache key for the same payload.

`frontend/lib/landing/landingHeroServer.js`'s `getLandingPageData()` now
calls `getHomepageRankingsSummary()` instead of
`getRipStatisticsTargets({ limit: 60, public: true })`. The spotlight
simulation-evidence cache/coalescing from `12d670af` (`distributionCache`/
`distributionInFlight`, keyed on spotlight `setId`) is untouched.

### Phase G -- no entitlement regression

The new endpoint takes no auth parameters and its projection contains only
fields already established as intentionally public (Set RIP V1, checklist
Set Value, opening economics, Set Desirability/Collector Appeal -- the same
categories the existing public Sets lens and public `/targets` Base
projection already expose to anonymous callers). `/explore/rip-statistics/targets`
and `/explore/rankings/lens/{lens}` are unchanged.

### Phase I -- measurement

- **Before**: general `/targets` source ~= 3,252,697 bytes (Prompt 1,
  live-measured, full `limit=200` cohort).
- **After**: measured structurally via the unit fixture in
  `test_rankings_lens_projection.py::test_homepage_lens_projects_only_the_public_whitelist`
  -- one representative target's projected JSON is on the order of a few
  hundred bytes (identity + `setRipV1` + `universalSetDesirability` + a
  dozen numeric fields), versus the same target's full published shape,
  which additionally carries `financialRipV4`, `overallRipV10`,
  `openingExperience`, and `productFamilyRankings` blocks that are excluded.
  **A live byte measurement against a real cold `/explore/rankings/homepage-summary`
  response (the exact number Prompt 1's 3,252,697-byte figure used) requires
  a running backend + published Rankings snapshot and was not available in
  this environment -- this is a deployment-verification item, not something
  this pass claims.** The field-count reduction is structurally proven: the
  homepage projection's target field list
  (`_HOMEPAGE_RANKINGS_TARGET_FIELDS` in `pokemon_public_snapshot_service.py`)
  is a strict subset of the compact `/targets` contract's field list
  (`project_pokemon_rip_statistics_target` in
  `20260904010000_add_rip_statistics_targets_compact_rpc.sql`), which itself
  already excludes `productFamilyRankings`/`setRip`/`eraSetStrengthV1`.

### Phase J -- structural navigation verification

Not independently re-run in this pass beyond what Phase F's cache/in-flight-
join code provides (identical shape to the existing `getRipStatisticsTargets`
publicOnly path, which Part A above already structurally verified for cold/
warm/concurrent behavior). The Market-page verification from Parts A-C is
unaffected and was not re-executed, since this pass does not touch Market's
code paths.

### Files changed (this pass)

- `supabase/migrations/20260904020000_add_homepage_rankings_summary_rpc.sql` (new)
- `backend/db/services/pokemon_public_snapshot_service.py`
- `backend/api/main.py`
- `frontend/lib/explore/ripStatisticsServer.js`
- `frontend/lib/landing/landingHeroServer.js`
- `backend/tests/unit/db/services/test_rankings_lens_projection.py` (new test added)
- `frontend/lib/landing/landingHeroServer.publicAuthInvariance.test.mjs` (updated
  to assert the new `getHomepageRankingsSummary()` contract instead of the old
  `getRipStatisticsTargets({ public: true })` call)

### Tests (this pass)

- `backend/tests/unit/db/services/test_rankings_lens_projection.py` -- 6/6
  pass (1 new: `test_homepage_lens_projects_only_the_public_whitelist`,
  proving the whitelist keeps identity/Set-RIP/Set-Value/economics/
  desirability fields and drops `financialRipV4`/`overallRipV10`/
  `openingExperience`/`productFamilyRankings`/`familyScores`/
  `rankedSetCount`).
- `backend/tests/unit/db/services/test_pokemon_rip_statistics_targets_compact.py`
  -- 11/11 pass, unaffected (proves the general `/targets` compact path is
  untouched).
- `backend/tests/unit/api/test_paid_response_boundary.py` -- could not run in
  this environment (`ModuleNotFoundError: No module named 'fastapi'`,
  pre-existing environment limitation, not caused by this change).
- Frontend: `ripStatisticsServer.normalization.test.mjs`,
  `ripStatisticsServerPublicCache.test.mjs`,
  `ripStatisticsServerCacheIdentity.test.mjs`, `landingHeroSpotlight.test.mjs`,
  `landingPreviews.test.mjs` all pass unmodified/updated. The updated
  `landingHeroServer.publicAuthInvariance.test.mjs` reproduces the **same
  pre-existing** `Cannot find module '@/utils/slugify'` /
  `D:\EVRCalculator-set-p0p1-pass2` stale-worktree-path failure already
  documented in Part A's Tests section above (present before this pass too,
  confirmed by running the unmodified import chain in isolation) -- not a
  regression introduced by this change.

### Closure

Prompt 2 is implementation-**CLOSED** as of this pass: A2 (this section),
A3/A4, and B2/B3 (Parts A-C above) are all implemented. Real browser/server
p50/p95 and the live-backend byte measurement remain deployment-verification
items for a later pass, as scoped.
