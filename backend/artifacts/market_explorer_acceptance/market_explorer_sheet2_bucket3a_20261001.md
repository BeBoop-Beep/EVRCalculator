# Market Explorer Fix Sheet 2 — Bucket 3A

- Starting SHA: `2b9708ad8a4dddd23c653c2861d177ddb5fe2534`
- Branch: `fix/market-explorer-sheet2-frontend-a-20261001`
- Scope: non-Activity frontend interaction and presentation only

## Closure evidence

- Disclosure layering: the root cause was three sibling stacking contexts (`z-50`, `z-60`, `z-70`) trapping lower popovers. Browse, contextual search, Rarity, and Sealed Types now elevate only their open disclosure root into one `80–83` contract. Popovers use an opaque slate surface; pointer/wheel boundaries, outside click, Escape, keyboard movement, and scrolling remain intact. A Chromium `elementFromPoint` check resolved the visible Sets popover rather than an underlying control; Escape closed it.
- Direct search: the existing Bucket 2 direct-instrument transport remains the only supported Card/Sealed leaf action. Basic clears the prior workspace only after `fetchDirectInstrument` succeeds; paid plans append within the existing slot guard. The exact item becomes the requested inspection target. Abort/sequence stale-response guards remain unchanged.
- Tooltip: readings are sorted on every active date by the value projected for the current Index/Performance view, descending, with unavailable values last and stable key ties. A crossing fixture proves `Red > Green > Purple` can become `Purple > Red > Green`. Focus filters both visible tooltip and generated ARIA sentence to the focused market only.
- Focus and inspection: magnifier focus also sets the requested constituent target. Clearing focus changes only graph focus and leaves inspection intact. Chip body is inspection-only; magnifier, visibility, and remove remain separate controls.
- Constituents: paged prepared composition continues through the generation-pinned page cache and Load More transport. Published parent composition capability, rather than asset or `isParent`, controls inspectability, covering Raw (`20,315`) and Total Sealed (`1,377`) without bootstrap-loading either roster. Count copy now says tracked cards/products; short fixture totals remain 6/3/1 rather than padding to 25.
- Screens: one result region is rendered immediately after the selected desktop row or selected mobile tile. Re-click and the accessible Close control close it. Cached results reopen without refetch. Loading/error/Retry/active/pending/Basic View/paid compare behavior is retained. Top/Worst now include All, Cards, and Sealed choices; asset requests use the backend asset filter and display backend global rank unchanged.
- Naming: `formatExplorerMarketLabel` is the shared structured asset-aware formatter used by Browse, Screen results, Active Markets, and chart-series labels. It adds `— Cards/Sealed/Graded` only when absent and never parses market keys.
- 30D: the graph domain uses `targetStartDate` (Aug 30 through Sep 29 in the acceptance fixture). Raw's Aug 28 calculation baseline remains movement metadata, is not plotted, and no Aug 30 Raw point is synthesized; its first in-window point is Aug 31. Direct Index values are not renormalized or clamped.
- Performance: no request serialization was added. The 250 ms search controller, direct abort/stale guard, prior-chart-until-success behavior, prepared loader, and Screen cache remain in place. Repository warm-read observations remain prepared ~138 ms, search ~147 ms, Screen ~80 ms, constituents ~161 ms, direct Card ~250 ms, and direct Sealed ~125 ms.
- Responsive: Screen result placement uses one-column immediate adjacency below `sm` and a two-column/full-row panel at `sm+`; the existing controls drawer, chart/action ordering, and overflow contracts were not changed.

## Verification

- Focused component/model regression: 76/76 passing (tooltip crossing/focus, naming, Screens, prepared domain, Browse, focus/chips, constituents).
- Chromium fixture smoke: passing for popover pointer hit testing, Escape closure, inline Rarity Screen opening, and accessible close.
- Legacy Playwright batch: not accepted as a green aggregate. Its V1 case had no fixture server on `:3203`; its V2 `networkidle` helper timed out during the initial 126.7 s dev compilation, after which the targeted Chromium smoke passed. This is recorded separately from product behavior.
- Production build: optimized Next build passed; repository-wide pre-existing lint warnings are non-fatal and listed by the build.

## Bucket 3B boundary

The new Market Activity graph remains intentionally unimplemented. Existing Activity DTO/capability code was not changed.
