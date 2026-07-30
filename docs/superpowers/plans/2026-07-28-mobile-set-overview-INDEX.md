# Mobile/Tablet Set Overview Overhaul — Plan Index

> **For agentic workers:** This phase is split into four plans. Execute them in
> the order below. Each produces working, testable software on its own and can
> be reviewed and merged independently.

**Source specs (both authoritative, read both before starting):**
1. The redesign brief — "PHASE — MOBILE/TABLET SET OVERVIEW EXPERIENCE OVERHAUL"
2. The functional-parity spec — "FUNCTIONALITY PARITY — NO LOSS OF EXISTING BEHAVIOR"

Where they overlap, the parity spec wins: parity is release-blocking.

---

## Why this is four plans, not one

The brief covers four genuinely independent subsystems. Splitting them means a
reviewer can reject one without blocking the others, and each merge point leaves
the app in a shippable state.

| # | Plan | Ships on its own? | Blocks |
|---|------|-------------------|--------|
| 1 | [Navigation destinations](2026-07-28-mobile-set-overview-1-navigation.md) | Yes — Tools out, TCGs in, nothing else changes | nothing |
| 2 | [Page shell architecture](2026-07-28-mobile-set-overview-2-page-shell.md) | Yes — fixes duplicate mount, blank gap, floating button, sticky tabs | 3, 4 |
| 3 | [Chart sizing and touch interaction](2026-07-28-mobile-set-overview-3-charts.md) | Yes — charts become touch-usable and correctly sized | 4 (partially) |
| 4 | [Mobile composition](2026-07-28-mobile-set-overview-4-composition.md) | Yes — hero, feed, Top Chase rows, RIP breakdown, section order | nothing |

**Execution order: 1 → 2 → 3 → 4.** Plans 1 and 2 are independent of each other
and may run in parallel if two workers are available. Plans 3 and 4 both depend
on the breakpoint tokens and the single-mount fix from Plan 2.

---

## The finding that shaped this split

`frontend/components/Profile/PublicProfileLocalScaffold.js` contains **three**
`{children}` expressions, two of which mount on any given render:

| Line | Wrapper | Renders when |
|---|---|---|
| 454 | `hidden xl:block xl:rounded-3xl xl:border ...` | `wrapDesktopContentInFrame` (My Collection, `/u/[username]`) |
| 457 | `hidden xl:block` | `!wrapDesktopContentInFrame` (the Set Detail page) |
| 513 | `px-3 pt-3 xl:hidden overflow-x-hidden min-w-0 sm:px-6` | always |

Lines 454 and 457 are the two arms of one ternary, so exactly one of them
renders — but line 513 renders **unconditionally alongside it**. Every consumer
therefore mounts `{children}` twice.

Because `RipStatisticsPageClient` is that `children`, **the entire set detail
page is mounted twice on every render** — two Recharts `ResponsiveContainer`
trees, two `ResizeObserver`s per chart, two copies of every `id="set-detail-*"`
element, two movers tickers. One copy is hidden with `display: none`, which does
not unmount it.

This single defect violates:
- Brief §11 — "Do not mount both a desktop and mobile copy of expensive charts and hide one with CSS"
- Brief acceptance criterion 24 — "No chart is mounted twice for responsive rendering"
- Parity spec §9 — "Avoiding duplicate component mounts", "Avoiding hidden desktop charts"

It is also the cause of the duplicate DOM ids already observed in production
smoke runs.

Fixing it is Task 2 of Plan 2 and must land before Plans 3 and 4, because both of
those assume one chart instance and one set of DOM ids.

---

## Global Constraints

Every task in every plan inherits these. Values are copied verbatim from the specs.

### Breakpoints
- Phone: `0–599px`
- Tablet / mobile application layout: `600–1199px`
- Existing desktop layout: `1200px and above`
- Use viewport or container width, never user-agent or device detection.
- Pay special attention to the `1199px → 1200px` transition and the `599px → 600px` transition.

### Desktop protection (brief §14, acceptance criteria 1)
At `1200px` and above the Set Overview must remain **visually unchanged**: hero,
grid, chart dimensions, section cards, spacing, typography, interactions, loading
behaviour, navigation styling. Do not use broad shared CSS selectors that reach
desktop. Every mobile/tablet override goes inside a deliberate responsive
boundary (`max-desk:` variant or a `@media (max-width: 1199.98px)` block).

### Global navigation is frozen (brief "CRITICAL NAVIGATION RESTRICTION")
Do not change any styling of the global top nav or global bottom nav — height,
width, positioning, background, blur, transparency, borders, shadows,
typography, icon sizing, icon treatment, label sizing, spacing, padding,
active-state styling, hover styling, safe-area styling, mobile search-field
styling, logo styling, hamburger styling, or fixed/sticky behaviour.

The only permitted global navigation changes are **destination/content** changes:
remove Tools, add TCGs, using the existing item component, spacing system, icon
treatment, active state and label styling.

Bottom nav destinations become exactly: `Home, Explore, TCGs, Portfolio, Profile`.

The Overview / Cards / Pull Rates / Insights bar is **not** global navigation. It
may be redesigned.

### Data and backend are frozen (brief §11, parity spec §8)
Do not modify backend services, database queries, snapshot builders, API
contracts, RIP formulas, simulation formulas, Set Value calculations, existing
caching behaviour, or existing desktop data flow.

Do not change: Market Movers ranking logic, Top 10 selection logic, seven-day
movement calculations, Set Value history, chart aggregation, chart date ranges,
timeframe definitions, price calculations, RIP values, RIP ranks, RIP tiers,
Opening Profit vs Cost calculations, chase-card rankings, or
Checklist / Hits / Top 10 definitions.

The same set, timeframe and data state must produce equivalent values at 390px,
834px and 1366px. Any difference caused solely by responsive layout is a defect.

### No new dependencies
Reuse the existing stack: `next@^15.5.15`, `react@^19.2.5`, `recharts@^2.15.1`,
`tailwindcss@^3.4.1`. Do not add a UI library, chart library, state library or
responsive framework.

### No new requests
Do not introduce client-side requests that only fire on mobile. Preserve
server-rendered seeds, client caching, prefetch behaviour and request
deduplication.

### Explicit removals — this list is exhaustive
1. The green floating filter button (`#059669`, `bg-brand`).
2. The Tools navigation destination.

Nothing else may be removed. Every other working control must survive, possibly
relocated: set selector; Overview/Cards/Pull Rates/Insights nav; timeframe
selectors; chart series selectors; Checklist/Hits/Top 10 selectors; Market Movers
interactions; RIP breakdown access; Set Value Trend access; chase-card links;
view-all links; information tooltips; retry actions; expand/collapse actions.

### Testing stack — do not introduce a new one
- Runner: `node:test` executed through `tsx --test`
- Component rendering: `react-test-renderer` with `createNodeMock`
- Source-string contract assertions: `fs.readFileSync(...).replace(/\r\n/g, "\n")`

There is **no jsdom and no Testing Library**. Interaction tests invoke handler
props directly on the test-renderer tree, the way
`frontend/components/explore/MoversTickerViewport.test.jsx` already does.

> **CRLF warning:** `RipStatisticsPageClient.jsx` has mixed CRLF/LF line endings.
> Any test that asserts on a multi-line source string must normalise with
> `.replace(/\r\n/g, "\n")` first, or the anchor will not match.

### Accessibility floor (brief §13)
Appropriate touch targets; visible focus states; preserved keyboard navigation;
semantic buttons and links; preserved accessible chart labels and screen-reader
descriptions; never colour alone for positive/negative movement; sticky elements
must not trap focus; horizontal control rows operable by touch and keyboard;
`prefers-reduced-motion` respected; contrast preserved.

---

## Verification widths

Every plan's final task validates at: `320, 360, 390, 430, 480, 599, 600, 768,
834, 1024, 1199, 1200, 1366`, with explicit `599 → 600` and `1199 → 1200`
comparisons.

Also exercise: short and long set names (`Scarlet & Violet—Journey Together`);
sets with and without logos; positive, negative and zero movement; incomplete
history; missing RIP; missing simulation data; missing chase-card image; loading
states; error states; bottom-of-page content; sticky behaviour during long
scrolling; tooltips near viewport edges.

---

## Running the tests

There is currently only one npm test script (`test:movers-ticker`). Plan 1 Task 1
adds a general `test:frontend` script that globs every `*.test.*` file, so later
plans have one command to run. Until it exists, run files directly:

```bash
cd frontend
npx tsx --test components/explore/MoversTickerViewport.test.jsx
```

### Recorded baseline (measured 2026-07-29, before any work in this phase)

`729 tests / 708 pass / 21 fail`. The 21 pre-existing failures are the bar every
later task compares against. They are unrelated to this phase — most are modules
that no longer export a symbol their test imports.

```
Cards tiles render one Price to Delta to Window market block
Overview parity: getPokemonSetMarketMovers's normalized payload shape matches what hasMarketMoverRows/MarketMoversModule read
Set Value and Opening Profit vs Cost use the requested user-facing copy
Set Value cards reserve enough height for the shared price/change stack
Set Value title card and full chart use the shared stack with matching amount, percent, and windows
components\Profile\CollectionBrowser.test.js
constants\exploreRankingConfig.test.mjs
getExplorePagePayload set fetch uses timeout and recoverable fallback instead of route-killing throw
legacy full-page wrappers use the shared canvas without changing component surfaces
lib\pokemon\pokemonSetCardsClient.dedupe.test.mjs
lib\pokemon\pokemonSetCardsClient.normalization.test.mjs
lib\pokemon\pokemonSetInsightsClient.dedupe.test.mjs
lib\pokemon\pokemonSetInsightsClient.normalization.test.mjs
lib\pokemon\pokemonSetMarketClient.normalization.test.mjs
lib\pokemon\pokemonSetPublicCoverage.test.mjs
lib\pokemon\pokemonSetPullRatesClient.dedupe.test.mjs
lib\pokemon\pokemonSetPullRatesClient.normalization.test.mjs
market dashboard normalizer attaches top chase histories to cards
metric options spell out percentage and dollar for assistive tech
set-page content uses shared standard and dense glass surfaces without changing the sticky context card
title/header card keeps stable Set Value data while its score follows the hero mode contract
```

---

## Execution status (2026-07-29)

Inventory taken before any code changed: **every task in all four plans was
"Not started."** Nothing in the phase had been implemented after the plans were
written — no `test:frontend` script, no `tab`/`desk` screens, the triple
`{children}`, the ungated floating button, `overflow-x-hidden` still present, no
`hooks/usePointerMode`, no mobile hero, no `data-mobile-feed`.

All four plans are now implemented, with the five corrections applied.

| Plan | State |
|---|---|
| 1 — Navigation | Complete and verified (3 contract test files, 17 assertions) |
| 2 — Page shell | Complete and verified (breakpoint preset, single mount, button gated, band removed, tabs pinned) |
| 3 — Charts | Complete and verified (pointer mode, tap/scrub, sizing, tooltip layering, state locks) |
| 4 — Composition | Complete and verified (hero, feed, compact chase rows, RIP breakdown, order + parity locks) |

Deviations from the plans as written, all deliberate:

1. **`test:frontend` glob widened.** The plan's glob missed `hooks/**` and
   root-level `*.test.*`, which would have silently skipped
   `hooks/usePointerMode.test.mjs` and `tailwind.breakpoints.contract.test.mjs`.
2. **Pure pointer logic lives in `hooks/pointerMode.mjs`, not `usePointerMode.js`.**
   `frontend/package.json` has no `"type": "module"`, so a `.js` file is CommonJS
   to node's ESM loader and an `.mjs` test cannot import its named exports. The
   hook re-exports them, so call sites are unchanged. This matches the existing
   `*.mjs`-for-pure-logic convention.
3. **The mobile hero receives movement colours as a prop.** Importing
   `interpretationTone` pulls in the `@/` alias, which the node:test runner
   cannot resolve (jsconfig declares `paths` without a `baseUrl`, and tsx reads
   `tsconfig.json`). The page passes the canonical
   `POSITIVE_VALUE_COLOR`/`NEGATIVE_VALUE_COLOR`, so there is still one colour
   system; a contract test asserts the page supplies them.
4. **The `@media (max-width: 1199.98px)` block lives at the end of `globals.css`.**
   Media queries add no specificity. Placed where the plan suggested, it preceded
   the unconditional `.set-glass-surface` rules and its `backdrop-filter: none`
   would have been overridden at every width — a silent no-op.
5. **The desktop header moved inside the content wrapper.** `/u/[username]`
   passes `desktopHeader`, which had always rendered *inside* the bordered
   desktop frame. Hoisting it out of the collapsed wrapper would have been a
   visible regression for public profile pages.
6. **Top Chase desktop grid moved from `lg:` to `desk:`.** The 1024–1199px band
   is tablet under the brief and now gets the compact composition; the column
   labels moved with it or they would have sat over the wrong columns.

---

## Mandatory corrections (applied 2026-07-29)

These supersede anything in the four plans that contradicts them.

### Correction 1 — the 1200px vs `xl` conflict

The Set Overview contract puts desktop at `1200px`; Tailwind's `xl` is `1280px`.
Plan 2's original draft left `PublicProfileLocalScaffold` on `xl:`, which would
have produced a mixed band from `1200–1279px`: the set page's *inner* content
switching to desktop at 1200 while the shared scaffold still applied mobile
gutters, mobile visibility and mobile spacing until 1280.

**Do not** globally move the scaffold to 1200px — My Collection and the public
profile layouts must keep their existing `xl` behaviour.

Implement a **static breakpoint preset**: a `SCAFFOLD_BREAKPOINTS` lookup holding
two fully written-out class recipes (`xl` and `desk`), selected by a
`desktopBreakpoint` prop that defaults to `"xl"`. `RipStatisticsPageClient` passes
`"desk"` only when `setDetailMode` is true. Every class string is written out in
full so Tailwind's scanner sees it; **no variant prefix is ever concatenated at
runtime**.

The preset must cover every scaffold mobile/desktop branch: content-wrapper
gutter and overflow, desktop frame styling, desktop-header visibility, local
scaffold nav visibility, tablet tools-trigger visibility, tools-panel visibility
and the aside/root-grid split.

### Correction 2 — one interactive set-picker owner

Plan 4 Task 2 mounts a mobile hero beside the desktop hero and hides one with
CSS. That is *not* conditional rendering. It is acceptable only under all of:

- exactly one picker menu/listbox is mounted at a time;
- all trigger and control ids are unique across both compositions;
- the hidden composition is not keyboard-focusable;
- no duplicated requests, effects, observers or expensive computations;
- open state is shared (single owner), and an open picker closes safely when the
  1200px boundary is crossed.

### Correction 3 — `CompactSparkline` must not sit inside a row anchor

Plan 3 makes `CompactSparkline` independently interactive (pointer, tap, scrub,
focus, arrow keys, Escape). Plan 4's original Top Chase draft wrapped the whole
row — sparkline included — in an `<a>`. Nested interactive semantics are invalid.

Compose each row as **siblings**: a navigation region (rank, image, name, rarity,
price, movement) that is the link, and a chart region holding the sparkline with
its own pointer and keyboard interaction. `stopPropagation` alone is not the fix.

### Correction 4 — tooltip clipping and first touch

A large `z-index` does not escape ancestor overflow clipping, a containing block,
a stacking context, `isolation`, or a transform-created stacking context. Inspect
the full ancestor chain; prefer removing inappropriate wrapper clipping and
keeping series clipping inside the SVG. Never restyle the global navigation to
solve chart layering.

**First touch is a specific regression risk.** `usePointerMode` seeds itself from
`matchMedia` inside an effect that runs *before paint completes* but the tooltip
trigger must already be correct when the user's first `pointerdown` arrives. The
first deliberate touch after load must inspect a point — it must not be consumed
switching modes.

### Correction 5 — no automatic git operations

All `git add` / `git commit` steps have been deleted from these plans (25 removed).
Do not stage, commit, amend, push or rebase during execution. Inspect, implement,
test, build, verify, report.

> Where a plan says "screenshot-diff against `main`", treat it as *do not change
> desktop*; an automated pixel diff is out of scope for this execution and is
> replaced by (a) proving every mobile override sits behind `max-desk:` /
> `@media (max-width: 1199.98px)`, and (b) contract tests asserting the desktop
> class strings survive verbatim.
