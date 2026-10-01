# Market Explorer Fix Sheet 2 — Bucket 3B Acceptance

Date: 2026-10-01

Branch: `fix/market-explorer-sheet2-activity-ui-20261001`

Starting authority: `fca0b410e8e5a6c65872dbc9e124d1f75b21b73f`

## Delivered

- Market Activity is a controlled third main-canvas mode beside Index and Performance.
- The detached Activity pane and Focus-tool entry were removed.
- Activity is focus-gated to structured Card markets and capability-gated by plan and authority pins.
- Supported windows are mapped exactly: 7D/7, 30D/30, 3M/90, and 6M/180. Entering from another window selects 30D; unsupported controls are disabled while Activity is active.
- Capability cache identity includes the requested window, while existing ownership and stale-response guards remain intact.
- The Activity chart uses calendar-time x positions, sparse sales bars, unconnected listed-supply markers, separate count/Index axes, and ghosted Index context for every selected market.
- Tooltip and keyboard inspection are focused-market only and preserve unknown observations rather than inventing zeroes.
- Loading, error, retry, authentication, entitlement, and unavailable states resolve in the chart canvas; fail-closed states return to Index.
- Constituent Performance/Activity remains independent of chart focus and uses the stable Inspecting target. User-facing supply terminology is “Listed Supply.”

## Verification

- Focused Activity/Explorer tests: 66 passed, 0 failed.
- Broader Activity/3A/constituent regression run: 99 passed, 0 failed.
- Fixture browser flow: 2 passed, 0 failed, covering 1440×900, 1366×768, and 390×844 plus keyboard tooltip inspection.
- Production build: passed (`npm run build`). Existing repository warnings were non-blocking and unrelated to Bucket 3B.
- Browser output confirmed the route returned HTTP 200 with authenticated fixture data. The optional `agent-browser` executable was not installed, so the equivalent Playwright verification was used.

## Evidence

Updated captures are stored under `backend/artifacts/market_activity_v1/fma3/` for desktop, laptop, mobile, sparse sales, listed supply, and synchronized tooltip states.

## Scope

Frontend only. No backend contract, database, migration, merge, or deployment change was made.
