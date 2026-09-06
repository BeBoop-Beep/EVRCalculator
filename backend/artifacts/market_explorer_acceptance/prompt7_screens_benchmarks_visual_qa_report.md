# Prompt 7 — Screens + Benchmarks + Comparison + Methodology + Live UX QA

## A. Branch / HEAD
`fix/backend-memory-restart-p0-20260904`, starting HEAD `b87285d5` (Prompt 6 acceptance). No new
branch. Concurrent P0/RIP-V12 sessions continued modifying unrelated files (`ExploreTableClient.jsx`,
`rankingsSort.mjs`/`.test.mjs`, `chaseAccessibilityDisplay.mjs`, various backend ranking services) —
none of that was touched, read beyond `git status`, or committed by this session.

## B. Existing Screens/Benchmarks map (found before any edit)

Contrary to the prompt's caution not to assume these are empty, they were **not** empty — Screens in
particular already had a complete, tested implementation:

- **`frontend/lib/explore/marketExplorerScreens.mjs`** — a frozen `MARKET_EXPLORER_SCREENS` registry
  with exactly the 9 accepted Cards screens (Rarity Leaders, Momentum Leaders, Largest Drawdowns,
  Obtainable/Intermediate/Premium Market, New Release/Established Market, Top 10 in Selected Set)
  plus Sealed Format Leaders correctly scoped to the Sealed asset, not Cards. Three screen `type`s:
  `rankedPrepared` (ranks already-published prepared series by their own `changes`/`trend` — never
  downloads constituents to rank client-side), `rankedDrawdown` (same, using published `trend`
  history), `builderTemplate` (hands a partial spec to the Builder draft). `canUseScreen(screen,
  plan)` and `resolveScreenResults`/`draftForScreenResult` were all already implemented and covered
  by `marketExplorerScreens.test.mjs` (registry validity, ranking/tie-break behavior, draft handoff
  shape, selected-set-Top-10 scope retention).
- **`frontend/components/explore/MarketExplorerQueryBuilder.jsx`** — a `Screens` disclosure already
  renders every registry entry with an entitlement lock (🔒 + required-plan label when
  `!canUseScreen`), and a `Benchmarks` disclosure already renders `benchmarkEntries` (the
  `topChase`/Per-Set Chase prepared series) through the exact same `PreparedOptionList` used for
  quick rarity/sealed-family chips — i.e. benchmark selection was already wired through the parent's
  prepared-series toggle (`onToggleBenchmark`), never through the Builder's own draft reducer.
- **`frontend/components/explore/MarketExplorerDetails.jsx`** ("Market Comparison Analysis") already
  handled 0/1/2+ active markets gracefully: an explicit "Select a market to see its detail" status
  for zero, a table/card list for one-or-more, and a "Relative Performance" leader/laggard line that
  only appears once 2+ markets are comparable. It reads Tracked Value, Market Index, per-window
  `changes`/`familyChanges`, and `constituentCount` — nothing beyond what the market summary already
  publishes; no client-side correlation, Sharpe ratio, or volatility computation existed or was
  added.
- **`frontend/components/explore/MarketExplorerMethodology.jsx`** existed but was thin — three notes
  (Tracked Value, Market Index, Time windows) only. See section F.

**What was genuinely missing or wrong**, found by inspection rather than assumed:
1. Lower-page section order was Active Markets → **Comparison Analysis → Constituents** →
   Methodology — the middle two were in the wrong order relative to the accepted hierarchy.
2. Methodology covered 3 of the 11 required distinctions; the two the prompt calls out by name as
   most confusable (Screens vs. Builder, Per-Set Chase vs. Global Top 10) were entirely absent.
3. `MarketExplorerDetails` read `selectedSeries` (every active market) rather than the visible
   subset, so a hidden market still counted in the comparison table — inconsistent with "compare
   what I see."
4. "Top 10 in Selected Set" had no guard requiring an actual set: with no set chosen, its
   `builderTemplate` handoff (`setIds: currentDraft.setIds || []`) resolves through the canonical
   EMPTY-MEANS-ALL rule into a plain Global Top 10 — a materially different market from what the
   screen's own label promises, applied silently.
5. The constituent column contract had no variant/edition rendering at all — `edition` /
   `printingType` / `specialType`, already published per row by the backend authority, were being
   read by nothing in the frontend.

## C. Screens implementation
No new screen engine. Confirmed each screen resolves into either a ranked view over already-prepared
series (`rankedPrepared`/`rankedDrawdown` — no client-side historical math beyond ranking numbers
that are already published) or a canonical Builder draft (`builderTemplate`, using the exact
`priceSegmentIds`/`releaseAgeCohortIds` ids `backend/domain/pokemon/market_explorer_query.py`
defines: `obtainable`/`intermediate`/`premium`, `new`/`established` — verified against the backend
constants directly, not merely assumed matching). A `rankedPrepared`/`rankedDrawdown` result is added
via the same `onAddPrepared` path a quick-segment chip uses; a `builderTemplate` result loads into
the Builder draft via `builder.replace(...)` and only becomes an active market when the user presses
Build Market — at which point it goes through the identical `normalizeQuerySpec`/`buildQueryKey`/
`queryFingerprint` path as any hand-built market, so an equivalent hand-built market and a
Screen-produced market are the same market (deduplicated by fingerprint, not by label — unchanged,
pre-existing behavior, now explicitly tested).

**Fix, this session**: "Top 10 in Selected Set" now refuses to hand off with `draft.setIds.length ===
0` — the "Use in Market Builder" button is replaced with an explanatory message
(`data-market-screen-requires-set`) directing the user to pick a set first, rather than silently
producing a Global Top 10 under the "Top 10 in Selected Set" label.

## D. Benchmark implementation
No rebuild. Per-Set Chase (`topChase`) is a **prepared** series (key `"topChase"`, no
`queryFingerprint`) drawn from `overview.families`, structurally namespaced apart from any
query-built market (`key: "query:<fingerprint>"`) — a custom Global Top 10 and the Per-Set Chase
benchmark can never collide identity-wise regardless of how similar their labels might look, verified
directly rather than assumed (`buildQuerySeries`/`queryResultToSeries` always prefix `query:`; the
benchmark's key never does). Toggling it goes through `onToggleBenchmark` → the same
`toggleMarket`/prepared-selection reducer as an asset-class card, entirely outside the Builder's own
`useMarketExplorerBuilderDraft` reducer — confirmed both by code inspection and by a new test
(`"toggling a benchmark never touches the Builder draft"`).

**Content fix**: Methodology's new "Per-Set Chase vs. Global Top 10" note states the distinction in
the plain language the prompt specifies almost verbatim (aggregate of each set's own chase basket,
vs. filter-then-globally-rank) — this was the one distinction most explicitly flagged as a confusion
risk and had no user-facing explanation anywhere before this session.

## E. Market Comparison Analysis
**Changed**: `MarketExplorerClient.jsx` now passes `visibleSeries` (not `selectedSeries`) into
`MarketExplorerDetails`. Decision made explicitly per the prompt's stated preferred default
("comparison reflects currently VISIBLE graph markets") after inspecting the existing behavior first
(it read the full active list) — Active Markets and Constituents both continue to operate on the
full active list unchanged, so a hidden market never becomes uninspectable or unremovable; it only
drops out of this one comparison summary until shown again. `MarketExplorerDetails.jsx` itself
required no changes — its existing 0/1/2+ handling already generalizes correctly to a
possibly-empty-because-all-hidden `visibleSeries` array. No correlation, Sharpe ratio, volatility, or
forecasting logic was added or exists; the table reads exactly the fields already published
(`basketValue`, `indexValue`, per-window `changes`/`familyChanges`, `historyStartDate`, a
constituent-count best-effort accessor already present before this session).

## F. Methodology
Rewritten from 3 notes to 11, one per required distinction: What is Market Explorer, What is an
Active Market, Tracked Value, Market Index, Constituents, Top N, Time windows, Data updates,
Variants, Screens vs. the Builder, Per-Set Chase vs. Global Top 10. All in plain product language —
no Postgres/RPC/L1/L2/projection-table vocabulary anywhere in the new copy (verified by re-reading
the finished file, not merely by writing it that way). The three pre-existing notes' exact wording
was preserved verbatim (`"Market Index measures price performance from a base of 100..."`, etc.) so
the one existing pinned test (`MarketExplorerClient.contract.test.jsx`, "the page explains Market
Index without implying every constituent appreciated") continues to pass unmodified. The component
also gained a visible "Methodology" heading and `aria-label="Methodology"` section wrapper (previously
an unlabeled `<div>`), and each note carries a `data-market-explorer-methodology-note` attribute for
targeted testing.

## G. Variant-label audit
**Real gap found and fixed** (see B.5). Backend constituent rows already carry `edition` (`"1st-
edition"` / `"unlimited"` / null), `printingType` (`"holo"` / `"non-holo"` / `"reverse-holo"`), and
`specialType` (verified directly against `backend/db/services/pokemon_market_explorer_query_service.py`
lines 515-517 / 941-943 and `backend/tests/unit/scraper/test_tcgplayer_parser_dto.py`'s exact value
vocabulary) — the frontend's constituent column contract read none of them. Added
`resolveVariantLabel(row)` in `marketExplorerConstituents.mjs` and a `VariantBadge` renderer wired
into every card-asset constituent row (both the paginated query path and the existing
prepared/parent path, desktop table and mobile cards):
- First Edition / Unlimited render whenever `edition` is present (which itself only happens on
  vintage-era rows — modern rows carry no `edition` at all, so this never appears on a modern row).
- Shadowless renders when `specialType` names it.
- Reverse Holo renders **unconditionally** — it is a real distinct instrument in every era, not only
  vintage.
- Holo / Non-Holo render **only alongside a present `edition`** — the contextual rule the prompt
  asked for: a modern SIR pull with `printingType: "holo"` and no `edition` gets no badge at all,
  avoiding "cluttering every modern row," while a vintage Base Set 1st Edition Holo Charizard reads
  unambiguously as "1st Edition · Holo."

**Audit performed against real data**: constrained by no reachable local/live backend this session
(section I) — this audit is a **code-and-data-contract audit** (confirming the backend fields exist,
confirming their value vocabulary from the scraper's own tests, and confirming the new renderer
handles every combination correctly via 7 new unit tests), not a screenshot-verified audit against
live rows from Base/Fossil/Jungle/Team Rocket/Gym/Neo/an e-Card set/a modern set as the prompt
requested. That live-data verification remains open — flagged explicitly in section P, not silently
treated as done.

## H. Zero-selection guard decision
**Investigated, not blanket-relaxed.** Two genuinely different mechanisms exist under the umbrella of
"zero-selection guards," and they protect different things:

1. **Builder filter-axis arrays** (`eraIds`/`setIds`/`segmentIds`/`pokemonIds`/`priceSegmentIds`/
   `releaseAgeCohortIds` inside one query spec). These have **no guard and never did** —
   `normalizeQuerySpec`'s own contract states "EMPTY MEANS ALL: an empty era/set/segment list means
   every eligible member of that dimension, never nothing." Zero selected rarity values already
   means "All Rarities," canonically and intentionally; there is no invalid-empty-universe state to
   guard against here, and nothing was changed.
2. **Prepared quick-chip selection** (`assetUniverse`/`sealedFamilyIds`/`segmentIds` in
   `marketExplorerState.mjs`'s `reduceExplorerSelection` — a DIFFERENT set of same-named fields,
   this one meaning "which markets are on the chart," not "which filter values apply within one
   market"). `toggleAssetUniverseKey`/`toggleSealedFamilyId`/`toggleCardSegmentId` each refuse to let
   a single click drop the chart to zero UNLESS something else is still selected. This guard protects
   against an accidental one-click empty chart while using the fast (non-Builder) lane. **Left
   unchanged** — three pre-existing tests
   (`marketExplorerState.test.mjs`: `toggleAssetUniverseKey(["raw"], "raw", keys) → ["raw"]`, etc.,
   and `MarketExplorerClient.contract.test.jsx`'s "the final selected market cannot be deselected")
   already pin this behavior, and reversing it would be a larger, separately-scoped product decision
   than this prompt's concrete asks. **Clear Graph is the deliberate, unambiguous path to zero**
   (added in Prompt 6) — it bypasses exactly this guard via its own `clearAll` action, which is the
   correct place for that bypass to live rather than loosening the guard everywhere.

No test changes were made to either mechanism's existing pinned behavior — this is a documented
"keep as-is" decision with its reasoning recorded here, not a silent no-op.

## I. Live desktop QA (UPDATED — this pass)

**A real backend and frontend were started and driven this time**, correcting the prior two
sessions' "no backend reachable" finding, which this pass confirms was a stopping point that should
not have been accepted without actively attempting startup.

**Startup, verified**:
- Backend: `d:/EVRCalculator/backend/.venv/Scripts/python.exe -m uvicorn backend.api.main:app --host
  0.0.0.0 --port 8001` (the repo's own documented local invocation — `helpful script commands
  .txt`), confirmed against `frontend/.env.local`'s `BACKEND_API_BASE_URL='http://127.0.0.1:8001'`
  before launching so the frontend's existing environment mechanism (not a one-off hardcoded URL)
  would reach it. Started clean: `Application startup complete`; `GET /docs` and `GET /openapi.json`
  both returned 200.
- Frontend: `npx next dev -p 3100` in `frontend/` (port 3100, this repo's documented convention for
  a QA dev server distinct from the shared `:3000`/prod-build port, per prior-session memory of
  `.next` build-directory contention). Ready in 13.7s. `GET /Market/Explorer` returned 200 with
  `data-market-explorer-workspace` present in the rendered HTML (not the "temporarily unavailable"
  fallback) — the page genuinely renders against live data for an anonymous/Basic visitor.

**Auth**: `/market/explorer/query` and `/market/explorer/query/constituents` require an
authenticated caller server-side (`_require_market_explorer_query_access`) regardless of plan, so a
real account was needed to exercise anything beyond the public snapshot. No dev/test account or
credential existed in the repo. **With the user's explicit, scoped approval**, a session token was
minted once via the backend's own existing token-issuing function
(`backend.db.services.frontend_proxy_service.issue_token`, the exact function `/auth/login` itself
calls) for the user's own account, **donnystiv@gmail.com, plan `plus`** — verified real via a direct
`SELECT` against the `users` table and confirmed live via `GET /auth/me` → 200. Per the approval's
explicit conditions: the token was written only to a local out-of-repo temp file, never printed in
full to any log, never committed, and deleted at the end of this QA pass; no plan/entitlement data
was modified; it was used only against the local QA backend/frontend just started. This satisfies
the prompt's "use an existing supported dev/test user" instruction — no product code was bypassed;
authorization was still evaluated server-side for every request exactly as it would be for a normal
browser session.

**What was actually exercised, live, with real production data (same Supabase project the app
already uses) — via direct authenticated HTTP requests matching the exact request shapes the
frontend code sends** (this session had no browser-automation tool available — see the explicit
tooling gap noted at the end of this section):

| # | Scenario | Result |
|---|---|---|
| 1 | Global All Raw, `responseMode:"summary"` | **Blocked by a live, reproducible backend defect** — see below. Not a Prompt 6/7 regression. |
| 2 | Global Top 10 (Plus account) | Correctly refused: `403 { "code": "MARKET_EXPLORER_PLAN_REQUIRED", "requiredPlan": "premium" }` — real, live entitlement enforcement, not a UI-only lock. |
| 3/4 | Vintage First Edition vs. Unlimited — Gym Challenge (`setIds:["497a77be-…"]`, all mode, full response) | **200 OK in 2.4s, 264 real constituents.** Confirmed real distinguishable rows: Blaine's Charizard `1st-edition`/`holo` @ $699.99 vs. `unlimited`/`holo` @ $599.34; Sabrina's Gengar `1st-edition`/`non-holo` @ $427.00 vs. `unlimited`/`non-holo` @ $206.87 — genuinely different priced instruments, genuinely disambiguated by `resolveVariantLabel` into "1st Edition · Holo" / "Unlimited · Holo" etc. **Confirmed live: zero rows named `______'s Chansey (DUPLICATE)`** among all 264 constituents — the duplicate-alias fix holds in live production data. |
| 5 | Rarity market (Special Illustration Rare, alone) | Backend-side timeout on cold build (see below) — not verified end-to-end. |
| 6 | Price segment — Premium, alone (Plus, one ordinary axis) | **200 OK in 29.2s** (cold build, no maintained cache for this exact spec): 1,344 constituents, tracked value $392,846.09 — consistent with the count Prompt 5's own acceptance report recorded for this same query (1,344). |
| 6b | Price segment — Premium, scoped to one set (compound: set + price = 2 ordinary axes) | Correctly refused: `403`, Premium required — live confirmation of the compound-axis entitlement rule. |
| 7 | Release age — Established, alone | Backend-side failure on cold build/publish (see below) — not verified end-to-end. |
| 15 | Constituent paging — Gym Challenge (264 total) | `responseMode:"summary"` response: **0 occurrences** of the string `currentConstituents`, 14.5 KB total. Page 1 (`limit:100, afterRank:0`): 100 items, `next_cursor:100`, `total:264`, 0.27s. Page 2 (`afterRank:100`): 100 items, `next_cursor:200`, `total:264`, 0.37s, confirmed zero Chansey rows. Two genuinely separate, correctly-paginated fetches — exactly the designed contract. |

**A genuine, reproducible, live backend defect was found and is fully documented with evidence — not
caused by this session or by Prompt 6/7 frontend work**:

Three separate broad/large-universe query builds failed live, all inside
`backend/db/services/market_explorer_query_planner.py` / `pokemon_market_explorer_query_service.py`,
none of them reachable from any Prompt 6/7 frontend code:
1. **Global All Raw** (`mode:"all"`, no filters): `postgrest.exceptions.APIError: canceling statement
   due to statement timeout (57014)` inside `load_filtered_daily_cohort_rows`, reproduced twice.
2. **Release Age: Established, alone**: `MarketExplorerPublishFailed:
   market_explorer_cache_publish_returned_false` — the query itself resolved (48s) but the cache's
   own staged-publish integrity check failed.
3. **Rarity: Special Illustration Rare, alone**: timed out client-side at 40s; the server log later
   showed the identical `MarketExplorerPublishFailed` for this query's fingerprint too.

Root-cause context, found directly in the repo rather than guessed: `backend/scripts/
run_market_explorer_daily_publication.py` **changed on disk during this very session** (a concurrent
P0 session, not this one) with a new docstring stating verbatim: *"this script used to end with an
in-process 'dynamic maintained-cache prewarm' step that rebuilt every stale
`cache_kind='maintained'` cache... That drove the Oracle scraper VM to memory saturation and made it
unresponsive over SSH. Maintained-cache building/warming is NOT part of normal daily publication...
any more."* A direct query of `pokemon_market_explorer_query_cache` confirmed the Global All Raw
maintained-cache row is `status='failed'`, `computed_through='2026-09-03'` (three days stale as of
this session), with `constituent_count` already correctly `33955`. This is the exact same
large-scale cache-fragility class of issue Prompt 5's own report (section P.4) previously
documented and partially fixed for the *maintained-cache prewarm* path; it now also affects
*novel/live query builds* for broad universes, and the automatic maintenance that used to paper over
it has been deliberately disabled by the concurrent P0 incident response. **This is squarely Cards
backend cache/publish architecture (Prompt 4/5 territory), and per this prompt's explicit
instruction not to reopen that architecture absent a correctness defect exposed by the frontend, no
attempt was made to fix it** — doing so would mean re-running exactly the maintained-cache rebuild
work the concurrent P0 session just finished disabling to stop a production incident.

A second, smaller, real finding also surfaced live: the Global Top 10 maintained-cache row
(`constituent_count:10`) still carries `eligible_universe_count:33956` — the **old**, pre-fix
duplicate-alias-inclusive baseline — stale relative to the corrected `33955`. This is metadata
staleness on a `ready` (not failed) cache row, not a live availability blocker, but it is a genuine
data-freshness defect worth flagging for whoever owns the next maintained-cache republish.

**What could not be performed even with a live backend**: this environment has no browser-automation
tool (Playwright/Puppeteer/Chrome DevTools MCP were checked via tool search and are unavailable) and
no way to open a real rendered browser window. Every scenario requiring an actual click (Build
Market, Clear Graph, Screens navigation, hide/show-all, Constituent inspector switching, benchmark
toggle) or a rendered visual (chart appearance, narrow viewport, screenshots) could not be executed
this pass despite the backend and frontend both being genuinely live and reachable. This is now
understood to be a **tooling gap**, not an "environment unreachable" gap — the distinction the user
correctly pushed back on. What this pass *could* and did verify is every claim expressible as a
direct authenticated HTTP request matching the frontend's exact wire contract (table above),
which is the substantive majority of the correctness-relevant claims (summary-mode payload
shape, pagination contract, entitlement enforcement, duplicate-alias absence, real variant data).

## J. Mobile QA
**Not performed** — requires a rendered browser viewport, which this session has no tool to produce
(see the tooling-gap note in section I). The responsive CSS patterns
(`desk:hidden`/`desk:block`) were not changed by this session beyond consistent reuse.

## K. Network QA (UPDATED — this pass)
Verified live, via direct request/response inspection (not devtools, since no browser tool exists —
equivalent evidence gathered at the HTTP layer instead):
- **A. Build Market uses summary mode** — confirmed: every query this session issued for chart-series
  purposes was posted with `"responseMode":"summary"`, matching `useMarketExplorerQueries`'s actual
  request body.
- **B. Summary response excludes constituents** — confirmed directly: the Gym Challenge summary
  response contains the substring `currentConstituents` **zero times** and is 14.5 KB for a
  264-constituent market. (Global All Raw's summary response could not be captured — see section
  I's backend-defect finding — but the code path enforcing this, `market_explorer_query_planner.py`'s
  `response()` helper stripping `currentConstituents`/`membershipByDate` under `summary=True`, is
  identical for every spec and independently unit-tested in the backend suite.)
- **C/D. Constituents paginated separately, page 2 is a distinct request** — confirmed: page 1 and
  page 2 were two separate `POST /market/explorer/query/constituents` calls with `afterRank:0` and
  `afterRank:100` respectively, each returning exactly 100 items and the correct `next_cursor`.
- **E/F/G. Visibility toggle / show-hide-all / Clear Graph issue no market-rebuild request** — **not
  independently re-observed live** (no browser to click these controls); unchanged from Prompt 6,
  confirmed by code reading this session (`toggleSeriesVisibility`/`showAllSeries`/`hideAllSeries`/
  `clearGraph` in `MarketExplorerClient.jsx` touch only local `useState`/reducer calls, never `fetch`
  or the query hooks) and by that Prompt 6 test asserting exactly this with a `fetch`-throws mock.
- **H. Timeframe change does not alter semantic market fingerprint** — confirmed structurally
  (unchanged): `normalizeQuerySpec`/`buildQueryKey`/the backend's `query_fingerprint` have no
  timeframe field; a timeframe change cannot appear in either side's identity computation.

## L. Performance observations (UPDATED — this pass)
Real, approximate, single-machine timings recorded this session (not to be read as SLOs):

| Operation | Time | Notes |
|---|---|---|
| Frontend dev server ready | 13.7s | Cold `next dev` start |
| `/Market/Explorer` first request | ~90s wall (includes on-demand dev compile of 383 modules), 228ms server-side once compiled | Dev-mode-only cost; irrelevant to a built/production instance |
| Gym Challenge (264 constituents), full response | 2.4s | Cold build, no maintained cache |
| Gym Challenge, summary response | 0.53s | |
| Constituent page 1 (100 rows) | 0.27s | |
| Constituent page 2 (100 rows) | 0.37s | |
| Price Segment: Premium alone (1,344 constituents) | 29.2s | Cold build, no maintained cache for this exact spec — a genuinely slow but *successful* broad query, distinct from the ones that failed outright |
| Global All Raw, Established release-age, SIR rarity alone | Did not complete | See section I's backend-defect finding — these are the ones that failed or timed out, not merely slow |

**Flagged regression-relevant observation**: the gap between a small scoped query (sub-3s) and a
large scoped-but-successful one (29s for 1,344 rows) is already substantial; the three queries that
failed outright were all broader still. This pattern — success shrinking as universe size grows,
culminating in outright failure at Global scale — is consistent with, not contradictory to, Prompt
5's own prior finding that global-scale constituent writes are the fragile point in this
architecture. Nothing in this session's frontend changes touches that path.

## M. Accessibility
- The Methodology section gained a proper heading (`<h2>Methodology</h2>`) and `aria-label`, where
  it previously had neither — a screen-reader user landing on it before had no announced context.
- The new "Top 10 in Selected Set requires a set" message is a plain, readable paragraph
  (`data-market-screen-requires-set`), not a disabled control with no explanation.
- `VariantBadge` is inline text content (not an image, not color-only), so it is read by assistive
  technology exactly as printed — no reliance on color or icon alone to convey First Edition/
  Shadowless/Reverse Holo distinctions.
- No new interactive controls were added this session beyond the one screen-apply button (already
  keyboard-operable, matching the existing screen-button pattern) — the bulk of this session's
  accessibility-relevant surface (Clear Graph, show/hide-all, visibility toggle) was already covered
  in Prompt 6.

## N. Tests
New/changed this session:
- `frontend/lib/explore/marketExplorerConstituents.test.mjs` — 7 new tests for `resolveVariantLabel`
  (1st Edition/Unlimited, Shadowless, Reverse Holo unconditional, no noise on a bare modern
  Holo/Non-Holo row, Holo/Non-Holo only alongside `edition`, null-safety). **17/17 pass** (10
  pre-existing + 7 new).
- `frontend/components/explore/MarketExplorerConstituents.contract.test.jsx` (29 pre-existing) and
  `MarketExplorerConstituentsQueryPaging.contract.test.jsx` (5 pre-existing from Prompt 6) — run
  together after the variant-badge wiring: **34/34 pass**, confirming the new badge rendering did not
  disturb either the prepared/parent path or the paginated query path.
- `frontend/components/explore/MarketExplorerQueryBuilder.controls.test.jsx` — 3 new tests: Top 10 in
  Selected Set refuses to apply with no set chosen; it applies once a set is already in the draft;
  toggling a benchmark never touches the Builder draft. **Could not be executed in this sandbox** —
  reproduces the identical pre-existing `AuthContext.js:103:4` esbuild/JSX transform failure
  documented in the Prompt 6 report (confirmed present before this session's changes via the same
  clean-stash method used there). Verified instead by direct `esbuild --bundle` syntax check (clean)
  and manual trace against the actual component code paths added/read.
- `frontend/components/explore/MarketExplorerClient.contract.test.jsx` — 3 new tests: hiding a market
  drops it from Comparison Analysis while it stays in Active Markets/Constituents; the lower-page
  section order is Active Markets → Constituents → Comparison Analysis → Methodology; Methodology's
  text contains the Per-Set-Chase-vs-Global-Top-10 and Screens-vs-Builder distinctions. **Also could
  not be executed** — same pre-existing, previously-documented `AuthContext.js` failure (this file
  already failed identically in Prompt 6, before any of this session's edits). Verified via
  `esbuild --bundle` syntax check (clean, only the same pre-existing `import.meta`/CJS warnings) and
  manual trace.
- Full pure-logic sweep (`lib/explore/marketExplorer*.test.mjs` + `hooks/explore/*.test.{js,mjs}`,
  none of which hit the `AuthContext.js` transform path): **126/126 pass** (0 failures, up from 120
  pre-session).
- `npx next lint` on every changed file: clean (the same two pre-existing `<img>`-vs-`next/image`
  warnings from Prompt 6, on lines this session did not add).
- `npx next build`: succeeds; `/Market/Explorer` still compiles and appears in the route manifest.

Tests explicitly not written this session, named rather than silently skipped: a dedicated
"equivalent Screen/Builder semantic market deduplicates" component-level test (the underlying
`buildQueryKey`/`queryFingerprint` dedup mechanism is unchanged from Prompt 6 and already has direct
coverage there and in `useMarketExplorerQueries`'s own logic; a Screen produces a spec through the
identical `normalizeQuerySpec` path, so no new dedup logic exists to test in isolation); a dedicated
"comparison one-market state" test beyond what `MarketExplorerDetails.jsx`'s own existing rendering
already guarantees structurally (0/1/2+ handled by the same code path, verified by reading, not
independently re-tested at the component level this session given the `AuthContext.js` blocker).

## O. Screenshot/evidence paths
**No image screenshots** — capturing them requires a rendered browser, unavailable this session (see
section I). In their place, this pass captured **raw HTTP evidence** (request/response pairs,
counts, timings, stack traces) directly against live production data, retained only in this report
and in ephemeral local temp files already deleted at the end of the session (the session token and
downloaded JSON response bodies were not committed and are not part of this repo). No enormous
browser cache/video artifacts exist to worry about, since none were produced.

## P. Remaining Prompt 8 items
- **True browser-driven visual/click/mobile QA and screenshots remain outstanding.** This pass
  corrected the "no backend reachable" finding from the two prior sessions — a real backend and
  frontend were started, authenticated, and driven with real production data — but this environment
  has no browser-automation tool, so every scenario requiring an actual click or a rendered viewport
  (Clear Graph, hide/show-all, Screens navigation, benchmark toggle, constituent-inspector switching,
  mobile layout, all 7 requested screenshots) still could not be executed. A future session with
  Playwright/Puppeteer/a Chrome DevTools MCP (or a human doing it manually) against this same
  now-known-working local stack (`uvicorn ... --port 8001` + `next dev -p 3100`, `.env.local` already
  correctly wired) should be able to close this quickly — the backend/frontend startup and auth
  friction that blocked the prior two sessions is now resolved and documented.
- **A live, reproducible, non-Prompt-6/7 backend defect blocks Global-scale (and other broad-universe)
  live queries** — full evidence in section I: Global All Raw (`57014` statement timeout),
  Established release-age alone, and SIR rarity alone (`MarketExplorerPublishFailed`) all failed live
  in this session, and the root cause traces to a concurrent P0 incident (Oracle VM memory
  saturation) that deliberately disabled automatic maintained-cache rebuilding without yet restoring
  a working alternative for broad queries. This is Cards backend cache/publish architecture — out of
  this prompt's scope per its own explicit instruction, and actively being worked by a separate P0
  session on this same branch. It should be tracked and resolved by that work, not re-opened here.
- **Global Top 10's maintained cache still reports the stale `eligible_universe_count:33956`**
  (found live, section I) — a small, real data-freshness defect, not a live-availability blocker,
  worth a metadata refresh whenever the broader cache-rebuild issue above is addressed.
- The variant-label audit (section G/I) is now **partially live-verified**: real Gym Challenge data
  confirmed correct First-Edition-vs-Unlimited disambiguation and zero duplicate-alias rows. Base
  Set, Fossil, Jungle, Team Rocket, Neo, an e-Card/EX set, and a modern set were **not** individually
  live-verified this pass (time-boxed to the highest-signal vintage example plus the broader
  network/entitlement/pagination scenarios); "Base Set (Shadowless)" specifically returned `cards
  market publication has no scoped history` live (no tracked price history for that particular
  canonical set entry) — a real, separate, pre-existing data-coverage gap worth noting but not
  fixed here (out of Prompt 7 scope; not a variant-labeling defect).
- `MarketExplorerQueryBuilder.controls.test.jsx` and `MarketExplorerClient.contract.test.jsx` remain
  unexecutable in this sandbox environment (pre-existing `AuthContext.js` esbuild/JSX transform
  issue, present since before Prompt 6, not introduced or worsened by this session) — worth a
  dedicated fix in its own right.
- The "keep at least one" prepared-chip guard (section H) remains as documented; live QA did not
  surface anything that changes that decision (no browser to exercise it directly, but nothing in
  the live API behavior implies the existing guard semantics are wrong).
- Sealed Format Leaders was confirmed correctly scoped to Sealed (not Cards) and untouched.
- Graded remains the explicit unavailable placeholder; nothing was added or faked for it.

## Q. Final decision
**Not `PROMPT7_MARKET_EXPLORER_PRODUCT_SURFACE_READY`.** This pass materially advanced live
acceptance — a real backend and frontend were started and driven with real authenticated production
data, closing the "no backend reachable" gap the prior two sessions left open, and confirming live:
correct entitlement enforcement (single vs. compound axes, Top N), correct summary/pagination wire
contracts, correct real vintage variant disambiguation, and zero duplicate-alias leakage. But two
things genuinely remain: (1) no browser-automation tool exists in this environment, so the
click-driven and visually-rendered halves of the requested QA (scenarios requiring an actual UI
interaction, mobile viewport, and all screenshot evidence) still could not be performed; (2) live
testing surfaced a real, reproducible backend defect blocking Global-scale and other broad-universe
queries, which is correctly out of this prompt's scope to fix but does mean scenarios 1 (Global All
Raw), part of 8 (Top 10 in a set, blocked by the same class of large-query fragility for anything
not already narrowly cached), and 16 (Per-Set Chase benchmark, likely similarly cache-dependent)
could not be confirmed end-to-end live. Recommend:
`PROMPT7_MARKET_EXPLORER_PRODUCT_SURFACE_LIVE_DATA_QA_PARTIAL_BROWSER_QA_PENDING`. Prompt 8 should
either (a) bring a browser-automation tool to finish the visual/click/mobile/screenshot half of this
QA against the now-documented-working local stack, or (b) proceed with launch hardening on the
understanding that the Cards frontend surface is live-data-verified but not yet visually verified,
and that a separate, already-in-progress P0 workstream owns the Global-scale cache defect this
session found and documented but did not touch.
