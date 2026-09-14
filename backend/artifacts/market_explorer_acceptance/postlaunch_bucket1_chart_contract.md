# Market Explorer correction bucket 1 — dual chart contract

## A. Starting branch/HEAD

- Branch observed at task start: `develop`
- Starting HEAD: `1b3cb4ce`
- No branch or worktree was created.

## B. Dual-view architecture

One shared `MarketPerformanceChart` now accepts the canonical presentation mode. Constants and projection helpers live in `marketPerformanceDomain.mjs`; no backend or stored payload behavior changed.

## C. Performance semantics

PASS. Performance remains the default. Each already-clipped timeframe independently anchors every series to its first finite observation at 0%. Leading and interior null values remain null, each All-history series starts on its own first observation, and source arrays are unchanged.

## D. Index semantics

PASS. Index mode plots copied raw canonical Market Index levels. Changing timeframe continues to clip upstream history and never rebases the displayed index to 100.

## E. Shared toggle

PASS. `/Market` and `/Market/Explorer` use the same `MarketChartViewToggle`, mode constants, teal selected treatment, visible text, keyboard-native buttons, and `aria-pressed` state.

## F. /Market integration

PASS. The presentation mode is independent local state. The existing parent-owned timeframe still drives the overview period column, chart, and percentage legend.

## G. Explorer integration

PASS. Explorer uses the same toggle and chart primitive without adding a card or changing Active Markets. Prepared and query-built series continue through the existing shared chart model.

## H. Tooltip semantics

PASS. Both modes expose selected-window performance at the hovered date and canonical Market Index. Performance mode emphasizes percentage first; Index mode emphasizes Market Index first. Existing portalled interaction and placement are unchanged.

## I. Axis/domain behavior

PASS. Performance uses the honest relative percentage domain and 0% reference. Index reuses `buildMarketPerformanceDomain`; Index 100 renders only when contained in the resulting raw domain. Axis labels switch between adaptive percentages and formatted index levels.

## J. Network behavior

PASS. Mode switching is React presentation state in the two chart wrappers. Neither the toggle nor chart owns fetch, routing, query, or cache behavior, so switching causes no market request.

## K. Tests/build

- Focused chart/model and `/Market` composition tests: 69 passed, 0 failed.
- Production frontend build (`npm.cmd run build`): passed.
- `git diff --check`: passed; line-ending conversion warnings only.
- Existing repository lint and webpack-cache warnings remained non-fatal.

## L. Files changed

- `frontend/components/explore/MarketPerformanceChart.jsx`
- `frontend/components/explore/marketPerformanceDomain.mjs`
- `frontend/components/explore/MarketChartViewToggle.jsx`
- `frontend/components/explore/MarketExplorerChart.jsx`
- `frontend/components/explore/PokemonMarketPerformance.jsx`
- Focused chart, page-composition, and regression contract tests for those files.

## M. Genuine blockers

None.

## N. Commit SHA

Implementation: `e9181daa`

## O. Bucket-2 readiness

Bucket 1 is source-complete and verified. Bucket 2 was not started.
