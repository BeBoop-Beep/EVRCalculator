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

## I. Live desktop QA
**Not performed.** No backend was reachable from this sandbox: `curl` to both
`http://127.0.0.1:8000/market/explorer/snapshot` and `:8001` returned connection-refused
(`curl` exit 7) before any HTTP response. `npx next build` succeeds and the `/Market/Explorer` route
compiles, confirming the page is structurally sound, but no browser was opened against a running
instance and no screenshots were captured. Stated plainly as a genuine gap rather than asserted as
done — see sections J/K/N/P.

## J. Mobile QA
Not performed for the same reason as I. The existing responsive patterns
(`desk:hidden`/`desk:block` table-vs-card splits) were preserved and extended consistently by this
session's variant-badge and paginated-constituent additions, but no narrow-viewport rendering was
visually inspected.

## K. Network QA
Not performed live (no backend). The claims this section would verify are instead confirmed
structurally, unchanged from Prompt 6 and re-checked this session: `useMarketExplorerQueries` still
posts `responseMode: "summary"`; the constituent pager still posts to the separate
`/api/market/explorer/query/constituents` proxy; visibility toggling still touches no network path
(this session added no code on that path); Clear Graph still issues no rebuild request; timeframe
still has no representation in `normalizeQuerySpec`. None of this was re-verified against live
traffic this session.

## L. Performance observations
Not measured live (no backend). No performance-relevant code paths were touched this session beyond
adding one derived string computation per constituent row (`resolveVariantLabel`, a handful of
string comparisons — negligible relative to existing per-row rendering cost) and the section
reordering (a pure JSX reorder, no new computation).

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
None captured this session — no reachable backend (section I). No screenshot files were created or
committed.

## P. Remaining Prompt 8 items
- **Live visual/responsive QA is still outstanding**, now for a second consecutive prompt. This is
  the single most material open item: none of the 17 live QA scenarios, network QA, or performance
  observations the prompt requested were performed, because no backend was reachable from this
  sandbox in either session. Prompt 8 (or an earlier live session) needs an actual running backend
  to execute this.
- The variant-label audit (section G) is a code/data-contract audit, not a screenshot-verified audit
  against real Base/Fossil/Jungle/Team Rocket/Gym/Neo/e-Card/modern rows — needs live verification.
- `MarketExplorerQueryBuilder.controls.test.jsx` and `MarketExplorerClient.contract.test.jsx` remain
  unexecutable in this sandbox environment (pre-existing `AuthContext.js` esbuild/JSX transform
  issue, present since before Prompt 6, not introduced or worsened by this session) — worth a
  dedicated fix in its own right so this substantial and growing test surface can actually run in CI.
- The "keep at least one" prepared-chip guard (section H) remains as documented; no further action
  needed unless a future session decides to revisit that specific product decision.
- Sealed Format Leaders was confirmed correctly scoped to Sealed (not Cards) and untouched; Sealed's
  broader behavior was not otherwise exercised this session beyond confirming it still shares
  components without modification.
- Graded remains the explicit unavailable placeholder; nothing was added or faked for it.

## Q. Final decision
**Not `PROMPT7_MARKET_EXPLORER_PRODUCT_SURFACE_READY`** as an unqualified pass — the concrete
product-surface work (Screens' missing set-requirement guard, page ordering, Methodology's missing
distinctions, Comparison's visibility semantics, the variant-label rendering gap) is implemented and
unit-tested where the sandbox allows execution. But the prompt's own explicit, repeated requirement —
"Prompt 6 could not perform live visual acceptance. Prompt 7 must." — was not met, for the same
environmental reason (no reachable backend) rather than by oversight. Recommend: `
PROMPT7_MARKET_EXPLORER_PRODUCT_SURFACE_CODE_COMPLETE_LIVE_QA_PENDING`. Do not begin Prompt 8's launch
hardening until live visual/network/performance QA against a real running backend has actually been
performed — it is the one requirement this prompt shares with Prompt 6 that has now been carried
forward twice.
