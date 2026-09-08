# Market Explorer Refinement Prompt 4 — Chart-First Visual Redesign

## A. Branch / starting HEAD

- Branch: `fix/backend-memory-restart-p0-20260904`
- Starting HEAD: `eeb4095715a61b013d57d5bac53dd67962210467`

## B. Workspace hierarchy

Desktop is one coherent grid: a persistent Builder rail on the left and signals, the single active-comparison strip, then the dominant chart on the right. Lower content remains Constituents, comparison detail, Methodology.

## C. Explorer header/rail

The standalone route header was removed. The rail now owns the inDex mark, Market Explorer title, actual plan badge, compact coverage metadata, Builder controls, and sticky CTA area. Desktop rail width scales from 18rem to 21rem.

## D. Asset signals

Raw, Sealed, and Graded occupy three compact informational signal positions. Raw/Sealed show published index/value/period data. Signals have no button, toggle, or `aria-pressed` semantics. Graded says `Coming soon` and fabricates no values.

## E. Active comparison strip

One Active Markets component sits directly above the graph. It retains show/hide, inspect, edit, remove, Show all, Hide all, series color, index where applicable, and selected-period return. Narrow layouts scroll horizontally.

## F. Chart container changes

The redundant glass wrapper and interactive in-chart legend were removed. The chart now uses a lightly veiled transparent surface so page-level Pokémon environmental artwork can show through while axes, grid, lines, and tooltip remain legible.

## G. Chart size

Explorer plot heights are 24rem mobile, 30rem tablet, 38rem desktop, and 42rem wide desktop. The right column receives all width beyond the bounded rail.

## H. Y-domain research and final rule

The old policy always injected Index 100 and inherited a 3% minimum span. The final shared Market Index policy uses visible-data autoscaling for 1D, 7D, 30D, and 3M, with a 0.75% midpoint-relative minimum span and 12% padding. This makes a real 102.2→102.8 move legible without allowing a 0.05% move to fill the chart. 6M, 1Y, and All retain Index 100 context. All visible series feed one domain; hiding a series recalculates locally. Values and observations are unchanged.

## I. /Market scale parity

Both `/Market` and Market Explorer pass their selected timeframe to the same `MarketPerformanceChart` and `buildMarketPerformanceDomain` policy. Generic sparkline domain behavior was not changed.

## J. Pokémon environmental treatment

The existing page-level `PageArtworkAtmosphere` and Pokémon background resolver remain authoritative. The chart primitive does not hardcode Pokémon artwork; its veil was made translucent enough for the existing environment to remain perceptible.

## K. Builder visual system

The rail uses compact typography, thin dividers, restrained teal interaction emphasis, one disclosure vocabulary, and an integrated plan/coverage header. Filter, Screen, Composition, and Reference behavior is unchanged.

## L. Exact-item styling

Filters/Exact Items is now an explicit segmented control. Exact search results are dense rows with lazy thumbnails where available, prominent names, secondary physical identity, and a clear Add/Added state. Selected items remain dense and vertically safe up to 25.

## M. Edit/unsaved styling

Edit mode names the market being edited and displays `Unsaved changes · active line unchanged` independently of Update/Save as new/Cancel button text. Prompt-3 state and request behavior are unchanged.

## N. Lower-page refinement

Constituents retains its table surface and nearby Edit Items action. `Market Comparison Analysis` was de-emphasized to `Comparison detail`; relative-performance insight and the table remain. Methodology stays reference-oriented.

## O. Mobile/tablet behavior

Below 1200px the source intentionally stacks signals → horizontally usable active strip → full-width chart → collapsible Builder. At 768px this avoids starving the plot. At 390px the three compact signal cells fit the available grid, active chips scroll internally, exact rows are full-width, and no fixed desktop rail is imposed.

## P. Accessibility

Signals are semantic information containers rather than toggles. Real controls retain button semantics, focus-visible treatment, labels, expanded/pressed states where appropriate, and text indicators for hidden, selected, locked, Added, and unsaved states. Chart keyboard stepping and tooltip narration remain.

## Q. Performance/network regression

The redesign adds no fetches, catalog preload, animation system, or chart library. Visibility and timeframe changes remain client-only. Existing environmental art remains lazy. Search thumbnails use lazy loading.

## R. Prompt-1/2/3 regression

Query specifications, fingerprints, backend cache identity, entitlement, exact search, Screens, Composition, Reference, constituent movement/paging, instance identity, Update, Save as new, Cancel, and concurrency behavior were not rewritten.

## S. Tests/build

- Focused frontend regression: 75 passed.
- Dedicated layout/domain/chart contracts: 12 passed.
- Backend Market Explorer regression: 212 passed.
- Next.js production build: passed with existing/non-blocking lint warnings.
- Affected esbuild compilation: passed.
- Prompt-owned diff check: passed.

## T. Screenshot/evidence paths

No screenshots were captured. `PROMPT4_BROWSER_REVIEW_PENDING` because an authenticated browser session backed by real Market Explorer data was unavailable.

## U. Genuine blockers

No source blocker. Real-browser visual acceptance remains pending by contract.

## V. Prompt-5 readiness

Source is ready for Prompt 5 final browser/mobile acceptance. Prompt 5 should capture 1440, 1728, 768, and 390×844 states and tune only evidence-backed visual issues.

## W. Commit SHA

Implementation commit: `12b4d51f`.
