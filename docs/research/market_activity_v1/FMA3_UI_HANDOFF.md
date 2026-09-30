# FMA-3 — Focused Market Activity UI handoff

Status: **FIXTURE-BACKED / NOT LIVE API**

## Delivery identity

- Starting SHA: `8e86b6b3ab83422d95299107a66510a56ae5c336`
- Final implementation SHA: `f63ba48da6b88a96116af9da6902d9b0e69a90a0` (the following handoff-only commit adds this document)
- Branch: `fma3-focused-market-activity-ui`
- PR: https://github.com/BeBoop-Beep/EVRCalculator/pull/495
- Contract: `market_activity_v1.1`
- Domain: `market_activity_domain_v1.1.0`
- Fixture set: `market_activity_v1_fixtures_2`
- Canonical fixture-manifest SHA-256: `e6235d9c73dc7ce6e38b81431bcfe60e4a32ae27f2780632aae45d407705e007`

## Implementation

The focused Explorer toolbar now has an Index+-entitled `Market Activity` control. It defaults off, is available only for supported card focus, and does not load until enabled. It follows focused-market state without changing the active/hidden markets, constituent target, requested detail series, chart model, or canonical overlays.

`useMarketActivity` owns the fixture request lifecycle. Its request owner keys exact focus, activity generation, roster reference, evidence fingerprint, as-of date, window, and grade. Every new scope aborts and invalidates the preceding sequence. Disable, focus loss/hide/removal, logout, and plan downgrade clear the data and abort in-flight work. Obsolete completions cannot publish. No data is retained across identity/entitlement loss.

The adapter dynamically reads all 19 committed fixtures, validates the canonical manifest fingerprint and each fixture fingerprint with canonical JSON SHA-256, then validates `contractVersion` and the response request pins. It introduces no route or production transport.

The compact companion pane renders Sales and Offered Supply as distinct units. It preserves sparse dates, treats missing as unknown except within a proven sales span, labels observed-only versus proven facts, and describes captured supply as bounded provider-confirmed depth. Membership is explicitly current-roster retrospective. Capability expiry is evaluated against current time once per minute.

`MarketPerformanceChart` adds one optional prop: `onInspectedDateChange(date | null)`. With the prop absent, its state, pointer/touch/keyboard behavior, tooltip, and rendering remain unchanged. The canonical chart remains the sole tooltip/crosshair owner; the companion receives only the inspected date. Hovering and keyboard stepping cause no Activity request.

Accessibility includes real pressed-state controls, focus-visible rings, tab semantics for the two views, live loading/error/unavailable status, a screen-reader contract description, arrow/Escape behavior inherited from the sole chart inspection owner, and no color-only proof status.

## Files changed

- `frontend/components/explore/MarketActivityPane.jsx`
- `frontend/components/explore/MarketExplorerChart.jsx`
- `frontend/components/explore/MarketExplorerClient.jsx`
- `frontend/components/explore/MarketExplorerFocusTools.jsx`
- `frontend/components/explore/MarketPerformanceChart.jsx`
- `frontend/hooks/explore/useMarketActivity.js`
- `frontend/lib/explore/marketActivityFixtures.mjs`
- `frontend/lib/explore/marketActivityState.mjs`
- `frontend/lib/explore/marketActivityState.test.mjs`
- `frontend/lib/explore/marketExplorerAccess.mjs`
- `frontend/e2e/market-explorer/activity.playwright.spec.mjs`
- `backend/artifacts/market_activity_v1/fma3/*.png`

## Verification

- Focused component/state/regression command: **80 tests, 46 passed, 34 intentionally skipped, 0 failed**.
- Fixture coverage: all 19 accepted fixture documents passed manifest identity, individual fingerprint, contract, and request-pin validation.
- Explicit state checks: A→B race, disable-in-flight, sparse missing versus proven zero, current capability expiry, one tooltip owner, and no Activity overlay path.
- Existing Explorer client/chart and shared chart contract suites passed.
- Production build: compilation, lint, and type checking passed. Final page-data collection stopped on the repository's required missing `BACKEND_API_BASE_URL` production environment configuration; no FMA-3 compile/type error occurred.
- Browser: **2 Playwright tests passed** against the V2 fixture backend, including zero hover-time API requests, keyboard synchronization, Escape, Sales, Offered Supply, unavailable scope, laptop, and mobile.

## Browser evidence

- `backend/artifacts/market_activity_v1/fma3/1440x900-activity-off.png`
- `backend/artifacts/market_activity_v1/fma3/1440x900-sales-partial.png`
- `backend/artifacts/market_activity_v1/fma3/1440x900-offered-supply.png`
- `backend/artifacts/market_activity_v1/fma3/1440x900-synchronized-date-tooltip.png`
- `backend/artifacts/market_activity_v1/fma3/1440x900-activity-unavailable.png`
- `backend/artifacts/market_activity_v1/fma3/1366x768-activity.png`
- `backend/artifacts/market_activity_v1/fma3/390x844-activity.png`

## Fixture-only limitations and FMA-4 requirements

This is deliberately not connected to a live API. The wildcard capability is an explicit fixture authority and loads group fixture 11 by default; fixture IDs can be selected by a supplied capability for acceptance coverage. There is no production caching, proxy route, API authentication, constituent activity paging UI, or transport retry policy in this bucket.

FMA-4 must replace only the adapter seam with the authenticated structured POST reads, pass real activity-generation/roster/as-of/window/chart-range pins from the focused market, and publish per-market capability metadata. It must retain request-owner cancellation, exact scope-key equality, response contract/identity checks, capability re-evaluation, logout/downgrade clearing, sparse-series rules, and the chart-owned inspected date. It must not couple Activity to `requestedDetailSeriesId` unless it adds the separately designed “Inspect focused market” action.

FMA3_FOCUS_UI_READY
