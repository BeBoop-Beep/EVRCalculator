# Market Explorer post-launch Bucket 5 acceptance

## A. Starting branch/HEAD

- Branch: `develop`.
- Starting HEAD: `c10185ee75f6b4ef93eaf25f52d58cdc6a454392`, matching the requested baseline.
- Unrelated rankings-artifact/export-script work was preserved. No branch or worktree was created.

## B. Reference Market scroll diagnosis

The document owns narrow-page vertical scrolling; `data-market-builder-scroll-region` owns the desktop rail's `overflow-y-auto` scroll. An isolated Chromium measurement of the existing visible-label/`sr-only` checkbox interaction held `window.scrollY=500`, rail `scrollTop=250`, and the row top at 250px before and after activation; focus correctly moved from BODY to INPUT. That ruled out the hidden checkbox focus path as the cause.

Source/layout inspection identified the unstable geometry: Active Markets used a desktop-only wrapping chip list. Adding/removing the prepared Reference chip could grow/shrink the grid row above the chart. The one-to-two-series transition also conditionally inserted the visibility group. Those reflows can visibly move the chart and allow browser scroll anchoring to reposition a page whose anchor is below the changing row.

## C. Page-scroll result

Active chips now stay in one horizontal row inside the existing `overflow-x-auto` owner, and the visibility-control footprint is reserved for the one-series state. Reference selection therefore does not change the height of the Active Markets/grid row. No page-scroll restoration, `window.scrollTo`, anchor/hash navigation, or `scrollIntoView` was introduced.

## D. Builder-scroll result

The Reference row itself retains identical geometry across selected/unselected state, and the prepared selection path dispatches no Builder draft action. The rail scroll owner and its `scrollTop` are not read, written, replaced, or remounted by selection. The isolated browser measurement also held the modeled rail `scrollTop` exactly.

## E. Focus/keyboard behavior

The native checkbox remains the logical focus target with its visible label, checked/disabled semantics, focus-visible treatment, and standard click/Space keyboard behavior. No `preventDefault` or focus suppression was added.

## F. Reference Market fix

The smallest fix was applied at the actual changing layout: `MarketExplorerActiveMarkets` now keeps a non-wrapping chip row and a visibility-control placeholder with stable dimensions. Reference Market remains the existing `ExplorerMarketOption`; the native control was not replaced because browser measurement did not implicate it.

## G. Prepared-market/network regression

Raw, rarity, sealed-family, and Reference selections retain their prepared-series callback. Reference toggling executes `onToggleBenchmark` once, does not call `builder.replace`, and does not reach custom query, taxonomy, exact search, cache build, or mutation paths.

## H. Existing tooltip diagnosis

The shared tooltip was portalled to `document.body` and hard-positioned at `chartTop - 10` with `translate(-50%, -100%)`, deliberately placing its final rectangle above the graph. Its horizontal coordinate also used pointer/clamp state rather than deriving final placement from the snapped active guide.

## I. Tooltip positioning architecture

`positionMarketPerformanceTooltip` is one independently tested geometry model. It receives chart bounds, snapped crosshair X, pointer Y or keyboard source, measured tooltip dimensions, viewport bounds, gutter, and offset. It returns fixed left/top, constrained width/max-height, and horizontal/vertical placement labels.

## J. Pointer placement

Pointer and touch selection preserve a chart-relative Y ratio and snap the selected index as before. Final horizontal placement uses `xAt(activeIndex)`, so tooltip, guide, markers, and data share one observation. Left-side guides prefer a tooltip to their right; right-side guides prefer left. Vertical placement prefers above the pointer, flips below near the top, and clamps when necessary.

## K. Keyboard placement

Focus and ArrowLeft/ArrowRight use the selected guide with a stable upper-middle vertical anchor. Arrow stepping updates the date/readings and positioning without scrolling the page; Escape clears selection. The tooltip remains inside the graph rather than above it.

## L. Touch/coarse-pointer behavior

The existing tap/scrub/page-scroll classifier and `touch-pan-y` contract are unchanged. Vertical gesture intent remains owned by the page; taps and horizontal scrubs update the same selected index and inside-chart tooltip.

## M. Collision containment

Chart bounds are the primary containment region and viewport bounds narrow it further. The helper clamps all four edges with a 10px gutter, constrains width on narrow/mobile charts, and returns a bounded max-height. Tooltip height is measured from both its rendered box and `scrollHeight`; dense multi-series content becomes internally scrollable instead of escaping or silently truncating values.

## N. Scroll/resize reanchoring

The existing capture-phase scroll and resize listeners remain. Reanchoring now refreshes the complete chart rectangle while preserving pointer-relative Y/source, so body-portalled fixed coordinates continue to follow the selected guide after ancestor scroll or resize.

## O. Shared `/Market` + Explorer behavior

Both `PokemonMarketPerformance` and `MarketExplorerChart` still render the same `MarketPerformanceChart`. Tooltip placement exists only in that shared component/helper; no page-specific tooltip implementation was introduced.

## P. Accessibility

Chart `role=img`, keyboard focus, dynamic spoken description, both Performance/Index readings, Arrow keys, Escape, and carried-forward disclosure remain unchanged. The visual tooltip remains supplemental and `pointer-events:none`.

## Q. Tests/build

- Focused Reference, helper, chart, `/Market`, Explorer Builder, and interaction tests: 59 passed.
- Full Bucket 1-4 plus Bucket 5 focused regression set: 144 passed.
- Tooltip helper covers left/right choice, top/bottom flip, middle placement, chart gutters, viewport edges, 390px mobile containment, oversized/dense content, and keyboard placement.
- Frontend production build: passed. Existing non-fatal webpack cache, lint, unauthenticated static-generation, and dynamic-route diagnostics were emitted.
- Scoped `git diff --check`: passed; Git emitted only LF-to-CRLF working-tree notices.
- No authenticated application browser QA was performed. The only browser measurement was an unauthenticated isolated native-control diagnostic; full visual scroll confirmation remains user-owned manual QA.

## R. Files changed

- `frontend/components/explore/MarketExplorerActiveMarkets.jsx`
- `frontend/components/explore/MarketPerformanceChart.jsx`
- `frontend/components/explore/marketPerformanceTooltipPosition.mjs`
- `frontend/components/explore/marketPerformanceTooltipPosition.test.mjs`
- `frontend/components/explore/MarketExplorerInteractionPolish.contract.test.mjs`
- `backend/artifacts/market_explorer_acceptance/postlaunch_bucket5_interaction_polish.md`

## S. Genuine blockers

None for source acceptance. Authenticated end-to-end browser measurement was explicitly out of scope; it is not claimed as completed.

## T. Commit SHA

Implementation commit: `f9ce6687564166e1d569f29b21c5a55a2e0e3193`.

## U. Bucket-6 readiness

Bucket 5 is source/test ready. Bucket 6 and final manual QA were not started.

Final decision: `MARKET_EXPLORER_BUCKET5_INTERACTION_POLISH_COMPLETE`
