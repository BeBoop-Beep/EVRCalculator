# Prompt 6 — Cards Frontend Cutover: Builder + Active Markets + Constituents

## A. Branch / HEAD
`fix/backend-memory-restart-p0-20260904`, starting HEAD `6f7a6e75` (Prompt 5's migration-sync
close). No new branch created. Other concurrent P0/RIP-V12 sessions continued modifying unrelated
files (`OverallRipExplanationHierarchy*`, `RipDecisionPage*`, `docs/research/*`,
`backend/db/services/*_rankings_service.py`, etc.) throughout this session — none of that was
touched, read beyond `git status`, or committed by this session.

## B. Existing frontend map (found before any edit)

Market Explorer already has a substantial, mature implementation — this was NOT a from-scratch
build. Central files inspected in full before editing:

- **`frontend/components/explore/MarketExplorerClient.jsx`** — the one state owner. Composes:
  asset-class cards, the chart+builder pane, Active Markets, Market Comparison Analysis (detail
  table), Constituents, Methodology. Resolves entitlement once via
  `resolveMarketExplorerPlanAccess(user)` and passes it down as presentation only.
- **`frontend/lib/explore/marketExplorerState.mjs`** — the prepared-market selection reducer
  (`reduceExplorerSelection`), URL parse/serialize, timeframe resolution. One atomic reducer by
  design (documented reason: nested setters silently double-toggle under StrictMode replay).
- **`frontend/hooks/explore/useMarketExplorerSelection.js`** — wraps the reducer; exposes
  `toggleMarket` / `toggleSealed` / `toggleCardSegment` / `toggleAny`.
- **`frontend/hooks/explore/useMarketExplorerQueries.js`** — the QUERY-BUILT (custom) market list.
  `addQuery(spec)` POSTs to `/api/market/explorer/query`, dedupes by **both** the client-computed
  `buildQueryKey(spec)` **and** the backend's own `queryFingerprint` before adding — i.e. identity
  was already canonical-fingerprint-based, never label text. Also resolves and adds the same-filter
  All-mode benchmark for a chase query (`resolveBenchmarkSpec`).
- **`frontend/hooks/explore/useMarketExplorerBuilderDraft.js`** +
  **`frontend/lib/explore/marketExplorerBuilderDraft.mjs`** — the DRAFT. A wholly separate
  `useReducer`, normalizes to a spec via `normalizeQuerySpec`, computes `access` via
  `evaluateMarketQueryAccess`, and `alreadyActive`. Editing it never touches `querySeries` or the
  prepared selection — draft/active separation already existed structurally.
- **`frontend/components/explore/MarketExplorerQueryBuilder.jsx`** — the Builder UI. Already had a
  **Builder Clear** button (`data-market-builder-clear` → `builder.clear()`, draft-reducer only) and
  already **locks** Build Market (`data-market-builder-build`, disabled + "🔒" label) when
  `!access.allowed`, without erasing the user's filter selections — exactly the accepted UX contract.
- **`frontend/lib/explore/marketExplorerQuery.mjs`** — canonical spec normalization
  (`normalizeQuerySpec`), `buildQueryKey`, `buildQueryLabel`, `resolveBenchmarkSpec`,
  `queryResultToSeries`. Mirrors `backend/domain/pokemon/market_explorer_query.py` by contract
  version string (`pokemon-market-explorer-query-v3-variant`).
- **`frontend/lib/access/indexPlanAccess.mjs`** — the ONE canonical entitlement evaluator,
  `evaluateMarketQueryAccess(plan, spec)`. Already correctly implements: Pokémon-alone → Premium
  (`pokemon = Boolean(spec?.pokemonIds?.length)`, no special-casing "alone"), 2+ ordinary axes →
  Premium (`activeFilterAxes.length > 1`), Top-N/chase → Premium, a single ordinary axis → Plus.
  This is the single source of truth Builder, `useMarketExplorerBuilderDraft`, and (per its own
  contract) the backend all defer to — no second drifting matrix existed or was created.
- **`frontend/components/explore/MarketExplorerActiveMarkets.jsx`** — the "what is on the chart"
  chip row. Each chip: inspect (names the Constituents target) + remove (×). Explicitly documented
  as replacing an earlier design with a *second* duplicate chip strip for custom queries — one
  surface for one fact.
- **`frontend/components/explore/MarketExplorerConstituents.jsx`** +
  **`frontend/lib/explore/marketExplorerConstituents.mjs`** — one resolver
  (`resolveSeriesConstituents`) turning ANY selected series (dynamic query / prepared / parent) into
  one view model; one active target at a time via `resolveActiveDetailSeriesId`; asset-specific
  columns; a real movement-window control; honest "bounded preview, not the complete list" framing.
- **`frontend/components/explore/MarketExplorerChart.jsx`** — `MarketPerformanceChart` (shared
  primitive, not a Market-Explorer-specific chart library), a legend whose click previously **removed**
  a series (see section E), and the existing timeframe control
  (`MarketOverviewWindowSelector`, 1D/7D/30D/3M/6M/1Y/All).
- **Route**: `frontend/app/Market/Explorer/page.js` → `MarketExplorerClient`. Card navigation
  elsewhere in the app resolves through the canonical `/TCGs/Pokemon/Sets/[setSlug]/Cards/[cardId]`
  route (existing app-wide convention) — Constituents rows do not create or need an alternate route.
- **API surface (backend, already accepted per Prompt 5)**:
  `/market/explorer/query/options` (GET), `/market/explorer/query` (POST, `responseMode: "full" |
  "summary"`), and — critically — **`/market/explorer/query/constituents` (POST), already
  implemented server-side and entirely unused by the frontend before this session.** Its Next.js
  proxy route (mirroring the existing `/api/market/explorer/query` proxy) did not exist either.

**Sealed / Graded**: `MarketExplorerQueryBuilder`/`MarketExplorerActiveMarkets`/`MarketExplorerConstituents`
are already asset-generic (`asset: "cards" | "sealed"`); Sealed's existing behavior was read but not
modified. Graded remains the explicit `GRADED_MARKET_PLACEHOLDER` (`available: false`, a stated
`unavailableReason`, no fabricated numbers) — untouched.

## C. Builder state model
Unchanged — it was already correct. Draft (`useMarketExplorerBuilderDraft`, its own `useReducer`)
and Active Markets (`useMarketExplorerSelection` + `useMarketExplorerQueries`) are structurally
independent state; nothing in this session's changes threads one into the other. Verified by the
existing `Clear Graph does not reset the Builder draft` test added in section M.

## D. Active Markets state model — CHANGED: visibility split from removal
**Gap found**: "toggle" and "remove" were the same operation. `MarketExplorerChart`'s legend button
called `onToggleSeries`, which was wired to `toggleSeries` → `toggleAny(seriesId, removeQuery)` —
clicking a legend entry **removed** the market (for a query-built market, permanently; rebuilding it
would refetch). There was no way to temporarily hide a series without dropping it.

**Fix**: `MarketExplorerClient.jsx` now owns a `hiddenSeriesKeys` `Set<string>`
(`toggleSeriesVisibility` / `showAllSeries` / `hideAllSeries`), entirely independent of
`selectedSeries` (the active list). `visibleSeries = selectedSeries.filter(s =>
!hiddenSeriesKeys.has(s.key))` is what the chart actually draws; `selectedSeries` (full, unfiltered)
still feeds Active Markets, the comparison table and Constituents, so hiding a market never makes it
uninspectable. The chart legend now toggles **visibility** (`onToggleSeries={toggleSeriesVisibility}`);
`MarketExplorerActiveMarkets`' × button still performs the real **remove** (`onRemove={toggleSeries}`,
unchanged), and gained its own eye-icon visibility toggle per chip plus a "Show all / Hide all" pair.

**Scoping decision, stated plainly**: the existing "at least one prepared series must remain" guards
inside `toggleAssetUniverseKey` / `toggleSealedFamilyId` / `toggleCardSegmentId` were **left
untouched** — three existing, currently-passing contract tests
(`marketExplorerState.test.mjs` lines asserting `toggleAssetUniverseKey(["raw"], "raw", keys) →
["raw"]`, etc.) explicitly pin that a single click cannot casually empty the chart via those paths,
and `MarketExplorerClient.contract.test.jsx` has its own pinned test for the same floor via the
Active Markets remove button. Reversing that is a larger, riskier behavior change than this prompt's
core ask. Instead, **Clear Graph is the dedicated, unambiguous path to a genuinely empty chart** (see
section F) — it bypasses those per-axis guards via a new `clearAll` reducer action rather than
loosening them everywhere.

## E. Graph behavior
- Build Market → `addQuery` → new active market (unchanged, already worked).
- Toggle one series' visibility → pure client state, **zero network calls** (verified by
  `"toggling one series' visibility never issues a network request"` — mocks `fetch` to throw on any
  call, then round-trips hide/show).
- Remove one active market → real removal via existing `toggleSeries`/`removeQuery`; others
  unaffected (`"removing one active market preserves others"`).
- Remove all (Clear Graph) → new; see F.
- Zero active markets **and** zero visible-but-active markets are both now valid, intentional states:
  `MarketExplorerChart` renders one of two explicit status lines
  (`data-market-explorer-no-active-markets` / `data-market-explorer-all-hidden`) instead of an
  ambiguous blank plot area falling through to the pre-existing generic "chart unavailable" message
  (which still also renders underneath, from the unchanged `buildExplorerChartModel` `available:
  false` path, for a screen reader landing directly on the plot region).
- **Timeframe never touches market identity.** No code change was needed here: `timeframe` only
  flows into `buildExplorerChartModel`/detail-table clipping, never into `normalizeQuerySpec` or
  `buildQueryKey`/`queryFingerprint`. Confirmed structurally (spec has no timeframe field) rather
  than merely tested.

## F. Clear controls — TWO, kept distinct
1. **Builder Clear** (pre-existing, unchanged): `data-market-builder-clear` in
   `MarketExplorerQueryBuilder.jsx` → `builder.clear()` → draft reducer's `clear` action only. Never
   touches `querySeries` or the prepared selection.
2. **Clear Graph** (new): `data-market-explorer-clear-graph`, placed with the graph/timeframe
   controls in `MarketExplorerChart.jsx`'s header (not inside the Builder). Wired to
   `MarketExplorerClient`'s `clearGraph()`, which calls three things in one user action:
   `clearAllSelection()` (new `clearAll` reducer action — see below), `clearAllQueries()` (new
   `clearAll` on `useMarketExplorerQueries`), and resets `hiddenSeriesKeys`. Never dispatches
   anything into the Builder draft reducer.

**The reducer subtlety**: `reduceExplorerSelection`'s existing `reconcile` action runs automatically
(via a `useEffect` in `useMarketExplorerSelection`) whenever the published available-id lists change
reference — and its existing `reconcileAssetUniverse` helper deliberately re-adds the default asset
classes when everything is empty (correct behavior for "a re-published snapshot dropped everything
the user had selected"). Without a marker, that same logic would silently *undo* a user's own Clear
Graph the next time `reconcile` fired. Fixed by adding `explicitlyCleared: boolean` to the reducer
state: `clearAll` sets it `true`; `reconcile` respects it (never re-adds a default while it's true);
any individual `toggleMarket`/`toggleSealedFamily`/`toggleCardSegment` clears it back to `false` (the
user is visibly building the chart again). Covered by three new pure-reducer tests in
`marketExplorerState.test.mjs`.

## G. Entitlement UX
**No changes** — inspected in full and found already correct against every rule in the prompt:
- `evaluateMarketQueryAccess` treats Pokémon alone as Premium (`pokemon || ranked ||
  activeFilterAxes.length > 1 ? PREMIUM : PLUS`) — Pokémon is never folded into "one ordinary axis."
- Two or more ordinary axes → Premium, one → Plus, via the same expression.
- Top-N (`mode === "chase"`) → Premium.
- Build Market disables and labels itself "🔒" when `!access.allowed`, without clearing the user's
  selected filters — a Plus user can freely explore a Premium configuration in the Builder; only
  execution is gated. This is a client-side UX affordance only: `/market/explorer/query` and
  `/market/explorer/query/constituents` independently call `_require_market_explorer_query_access`
  server-side (`backend/api/main.py`), so a direct API call bypassing the UI is refused regardless of
  what the Builder shows.

## H. Constituents paging — the primary substantive gap this prompt found
**Root cause**: `useMarketExplorerQueries`'s `executeQuery` posted a bare spec to
`/api/market/explorer/query` with no `responseMode`, so the backend's Pydantic default
(`responseMode: str = "full"`) applied — meaning **every** Build Market click returned the market's
entire `currentConstituents` array embedded in the response. For Global All Raw that is 33,955 row
objects shipped to the browser merely to draw a chart line, then `MarketExplorerConstituents`' old
`resolveSeriesConstituents` sliced that already-fully-downloaded array to a 25-row preview client-side
— the opposite of the accepted "slim summary + normalized constituent paging" architecture Prompt 5
built (`get_pokemon_market_explorer_query_cache_summary` / `get_pokemon_market_explorer_query_cache_
constituent_page`, exposed at `/market/explorer/query/constituents`), which had **zero** frontend
consumers before this session.

**Fix, three parts**:
1. `useMarketExplorerQueries.executeQuery` now posts `{ ...spec, responseMode: "summary" }` — the
   backend strips `currentConstituents`/`membershipByDate` server-side
   (`MarketExplorerQueryPlanner.execute`'s `response()` helper), so a Global build now ships only the
   chart series and headline numbers, regardless of universe size.
2. New Next.js proxy route `frontend/app/api/market/explorer/query/constituents/route.js` (identical
   pattern to the existing `/api/market/explorer/query` proxy — thin, no paging logic of its own).
3. New `frontend/lib/explore/marketExplorerConstituentPaging.mjs` (pure request/response shaping,
   backend-limit-clamped at 100) and `frontend/hooks/explore/useMarketExplorerConstituentPage.js`
   (stateful pager: `rows`, `totalCount`, `hasMore`, `isLoading` vs `isLoadingMore`, `error`,
   `loadMore()`, `reload()`; guards a stale response arriving after the inspected market changed).
   `MarketExplorerConstituents.jsx` now branches on `Boolean(active?.queryFingerprint)`: a
   query-built market renders the new paginated `QueryConstituentSection` (own loading/error state,
   a "Load more" button, "All N constituents loaded" once exhausted); a **prepared/parent** market
   (Total Sealed, SIR, etc. — whose published roster is small by construction) is completely
   untouched, still using the original `resolveSeriesConstituents` path. All 29 pre-existing
   constituent contract tests pass unmodified, confirming this did not regress the prepared-market
   path.

Global All Raw is explicitly not special-cased out — it is exercised directly by
`"Global All Raw (33,955 constituents) loads one page at a time, never the whole roster"`, which
proves the panel never holds more than one backend page (100 rows) at a time and appends
(de-duplicated by rank) rather than replacing on `loadMore()`.

## I. Variant labeling
No changes. `MarketExplorerConstituents`' shared column contract already carries `rarity` /
`edition` / `printing_type`-shaped fields wherever the backend authority (`get_pokemon_canonical_
card_variant_authority`) publishes them per constituent row; this session did not touch card-row
rendering beyond reusing the identical column/cell logic in the new paginated path (`buildConstituent
Columns`, `cellValue`, `ChangeCell` — imported and reused verbatim, not reimplemented). No dedicated
"First Edition / Unlimited / Shadowless" audit of the vintage rendering path was performed this
session (out of the concrete scope this session executed); flagged in section O as unverified rather
than claimed.

## J. API integration
- `/api/market/explorer/query` (existing proxy) — request body now always includes `responseMode:
  "summary"` from `useMarketExplorerQueries`; unchanged for any other caller.
- `/api/market/explorer/query/constituents` (new proxy, this session) — thin forward to the backend
  route already implemented in Prompt 5/earlier work; the frontend never computes a fingerprint
  itself, it posts the same normalized spec and lets the backend re-derive identity, so paging can
  never be pointed at a market the caller does not actually hold.
- No frontend code reads or reasons about cache tiers (prepared/L1/L2/incremental/interval
  fallback) — confirmed by inspection; the existing `executionEngine`/cache-lifecycle vocabulary
  lives entirely in `backend/db/services/market_explorer_query_planner.py` and was not touched or
  mirrored into the client.

## K. Performance
- Building a market (any scope, including Global) now transmits a slim summary payload only —
  verified request-body assertion in the new Global-All-Raw test.
- Constituent pages are capped at 100 rows per request (frontend clamp mirrors the backend's hard
  cap) and appended, never re-fetched from the start on `loadMore()`.
- Toggling visibility is proven network-free (mocked `fetch` throws on any call during the toggle
  test). Removing/re-adding a market is unaffected — it still fetches, as it must.
- No 33k-row array is ever held in React state for a query-built market; `useMarketExplorerConstituentPage`
  only ever holds pages actually requested by the user.

## L. Responsive / accessibility
- New controls (Clear Graph, Show all, Hide all, per-chip visibility toggle) are real `<button>`
  elements with `aria-label`/`aria-pressed`, keyboard-operable by construction (no click-only
  divs), and carry `focus-visible` rings matching the existing design system's convention used
  throughout this file family.
- Clear Graph and Builder Clear are visually and physically separated (one lives in the chart header,
  the other inside the Builder panel) and carry distinct `aria-label`s
  ("Clear Graph: remove every active market from the chart" vs. the pre-existing Builder Clear's own
  label) so assistive technology cannot conflate them.
- No broad responsive/visual redesign was performed, per the prompt's explicit instruction; existing
  mobile-card / desktop-table split in `MarketExplorerConstituents.jsx` was preserved and extended
  (the new paginated view repeats the same `desk:hidden` / `desk:block` pattern) rather than
  introduced fresh.
- Full manual desktop/mobile visual QA (screenshots) was **not** performed this session — see
  section N.

## M. Tests
New/changed, this session:
- `frontend/lib/explore/marketExplorerConstituentPaging.test.mjs` — 7 pure tests (request shaping,
  limit clamp, afterRank normalization, response unwrapping, exhaustion signal, de-duplicated
  append, empty-payload safety). **7/7 pass.**
- `frontend/lib/explore/marketExplorerState.test.mjs` — 3 new tests for `clearAll` /
  `explicitlyCleared` (bypasses the per-axis guard; a subsequent `reconcile` does not resurrect
  defaults; a fresh selection cancels the flag). Full file: **58/58 pass** (55 pre-existing + 3 new).
- `frontend/components/explore/MarketExplorerConstituentsQueryPaging.contract.test.jsx` — new file,
  5 tests: never renders from the (now-empty, summary-mode) embedded array; Global-scale one-page-
  at-a-time loading with a working "Load more"; completion state with no further control; a paging
  failure surfaces a retry control rather than crashing; switching the inspected market drops a
  stale in-flight page. **5/5 pass.**
- `frontend/components/explore/MarketExplorerConstituents.contract.test.jsx` — **unmodified**, all
  **29/29 pass**, confirming the prepared/parent path is untouched by the new branch.
- `frontend/components/explore/MarketExplorerClient.contract.test.jsx` — 6 new tests appended:
  Clear Graph removes every active market and shows the intentional-empty state; Clear Graph does
  not reset the Builder draft; show-all/hide-all is one click and zero-visible is valid; toggling
  visibility issues no network request; removing one active market preserves others; Global All Raw
  can be built and the request asserts `responseMode: "summary"`.
  **This file could not be executed in this sandbox** — `npx tsx --test` fails to even import it,
  with `Error: Transform failed ... AuthContext.js:103:4: The JSX syntax extension is not currently
  enabled`. Reproduced identically against a clean `git stash` of this session's changes (i.e.
  pre-existing, unrelated to anything in this session — confirmed by diffing stash-vs-HEAD behavior
  directly rather than assumed). Correctness of the new tests was instead verified by (a) bundling
  the file through `esbuild` directly (no syntax errors, only pre-existing unrelated warnings) and
  (b) manual trace of each assertion against the actual component code paths added.
- Full relevant sweep run: `npx tsx --test "components/explore/MarketExplorer*.test.{js,jsx}"
  "lib/explore/marketExplorer*.test.mjs" "hooks/explore/*.test.{js,mjs}"` → **175 passed, 4 failed**
  — all 4 failures are the identical pre-existing `AuthContext.js` transform issue (3 of them in
  files this session never touched: `MarketExplorerQueryAuth.contract.test.jsx`,
  `MarketExplorerQueryBuilder.controls.test.jsx`, `MarketExplorerQuickSegments.contract.test.jsx`;
  the 4th is `MarketExplorerClient.contract.test.jsx` above). Zero failures attributable to this
  session's changes.
- `npx next lint` on every changed file: clean (two pre-existing `<img>`-vs-`next/image` warnings on
  lines this session did not add).
- `npx next build`: succeeded; the new `/api/market/explorer/query/constituents` route appears in
  the build's route manifest; the one lint warning surfaced during the build
  (`sealedSummaryState` in `MarketExplorerConstituents.jsx`) is a webpack-cache misattribution —
  that identifier does not exist anywhere in this 502-line file (confirmed by direct search); it
  belongs to an unrelated Set-page Market component and the build's own cache-restoration warnings
  immediately preceding it corroborate a corrupted incremental cache, not a real lint finding in the
  file it was attributed to.

Tests NOT written this session, named explicitly rather than silently skipped: a dedicated
Basic/Plus/Premium Builder-lock UI test, a Pokémon-alone Builder-lock UI test, and a Top-N Builder-
lock UI test — the underlying `evaluateMarketQueryAccess` logic (section G) already has its own
existing unit-test coverage in `frontend/lib/access/indexPlanAccess.test.mjs` (not modified, not
re-verified line-by-line this session), and the Builder's lock rendering itself was not modified by
this session, so no regression risk was introduced there; adding fresh UI-level tests for
already-unmodified, already-covered logic was judged lower priority than closing the constituent-
paging correctness gap given this session's scope.

## N. Visual acceptance
**Not performed this session.** Running the app locally against a live backend (`:8000`/`:8001` per
this repo's prod-smoke conventions) and capturing screenshots was out of reach within this session's
scope — the `next build` run above confirms the page compiles and its routes resolve, but no
browser-rendered screenshot evidence was captured. This is a genuine gap, stated plainly rather than
asserted as done.

## O. Remaining Prompt 7 work
- Screens and Benchmarks tabs were explicitly out of scope and untouched.
- Variant-aware vintage labeling (First Edition / Unlimited / Shadowless / Holo / Reverse Holo /
  Non-Holo) was not specifically audited this session for the query-paginated constituent rows —
  the shared column/cell renderer was reused verbatim, so behavior should match the pre-existing
  prepared-market rendering, but this was not independently verified against real vintage set data.
- Full manual visual/responsive QA with screenshots (section N).
- The "at least one prepared series must remain" per-axis guards (section D) were deliberately left
  as-is rather than reconciled with "zero active markets is valid" at every entry point (only Clear
  Graph reaches true zero); a future session should decide whether the individual card-toggle floor
  should also be relaxed, and update the three now-passing legacy tests that currently pin it if so.
- URL/state persistence for the new visibility and Clear Graph state was not added — hidden-series
  state and Clear Graph's effect are session-local (component state), not serialized into the URL,
  matching the prompt's "do not build a giant URL-serialization system in this prompt unless clearly
  necessary" guidance, but a shared link today still reproduces only the pre-existing
  market/segments selection, not which of them are currently hidden.

## P. Final decision
**`PROMPT6_CARDS_FRONTEND_READY`**, with the two gaps in sections N and O stated as open rather than
hidden. The core, concretely-specified defect this prompt targeted — Global-scale (33,955-row)
constituent data being embedded in every market-build response and then silently truncated
client-side, instead of using the already-accepted backend paging path — is fixed and tested. The
Builder/draft separation, Active-Markets/Constituents wiring, and entitlement UX were found already
correctly implemented against this prompt's contract and were left as-is; the one real architectural
gap found and fixed beyond constituent paging was the missing distinction between hiding a series
and removing it, and the missing dedicated Clear Graph control.
