# FMA-3 — Focused Market Activity UI handoff

Status: **FIXTURE-BACKED / NOT LIVE API**

## Delivery identity

- Original implementation base: `8e86b6b3ab83422d95299107a66510a56ae5c336`
- Reconciliation base (`origin/develop`): `875ae95f6da3178572e7d3b642ef6483354ca04a`
- Reconciled implementation SHA: `91c6c7c72d9ab7341bc5d0ca4889d0d4bc9e0815` (the handoff-only commit follows)
- Branch: `fma3-focused-market-activity-ui`
- PR: https://github.com/BeBoop-Beep/EVRCalculator/pull/495
- Contract: `market_activity_v1.1`
- Domain: `market_activity_domain_v1.1.0`
- Fixture set: `market_activity_v1_fixtures_2`
- Canonical fixture-manifest SHA-256: `e6235d9c73dc7ce6e38b81431bcfe60e4a32ae27f2780632aae45d407705e007`

## Reconciled implementation

The normal Explorer product path defaults to `NO_BACKEND_CAPABILITIES`. Market Activity is unavailable unless an exact capability and a transport are explicitly injected. The UI no longer invents an activity generation, roster reference, evidence fingerprint, as-of date, window, grade, or tier. An incomplete capability fails closed.

`useMarketActivity` depends on an injected transport interface. Before publishing ready state, the request owner verifies the response contract version and exact initiating scope: market key, activity generation, roster reference, as-of date, window, applicable tier/grade, and evidence identity. Scope mismatch is rejected even when the response is the latest sequence. Existing `AbortController` cancellation and A→B sequencing remain intact.

The companion pane receives the canonical chart's visible dates. Sparse observations are positioned with the same indexed horizontal domain used by the canonical chart, rather than as equal-width children. Missing dates remain gaps, dates outside Activity coverage remain unknown, and explicit zeroes are introduced only inside a proven sales span. Activity does not forward-fill and does not own pointer, crosshair, or tooltip behavior.

## Fixture isolation

`marketActivityFixtures.mjs` remains the acceptance validator and loader, but it is no longer imported by the normal client or hook. Exact fixture authority lives in `marketActivityFixtureHarness.mjs` and is enabled only by the explicit `MARKET_ACTIVITY_FIXTURE_MODE=1` server-side harness. The harness validates and injects the selected fixture payload and capability. Normal production rendering receives neither fixture authority nor fixture transport, keeping the 19 fixture JSON documents off the normal client import path.

FMA-4 can replace the injected transport with authenticated structured POST calls without rewriting the Activity state machine or UI.

## Principal files

- `frontend/app/Market/Explorer/page.js`
- `frontend/components/explore/MarketActivityPane.jsx`
- `frontend/components/explore/MarketExplorerChart.jsx`
- `frontend/components/explore/MarketExplorerClient.jsx`
- `frontend/hooks/explore/useMarketActivity.js`
- `frontend/lib/explore/marketActivityFixtureHarness.mjs`
- `frontend/lib/explore/marketActivityFixtures.mjs`
- `frontend/lib/explore/marketActivityState.mjs`
- `frontend/lib/explore/marketExplorerAccess.mjs`
- `frontend/e2e/market-explorer/activity.playwright.spec.mjs`
- focused state, access, chart, and workspace regression tests
- `backend/artifacts/market_activity_v1/fma3/*.png`

## Verification

- FMA-3 state/component plus shared chart and Explorer regressions: **111 tests, 77 passed, 34 intentionally skipped, 0 failed**.
- Final focused reconciliation subset: **48 passed, 0 failed**.
- All 19 fixture documents passed manifest identity, individual fingerprint, contract, and request-pin validation without changing accepted versions.
- Exact response-scope tests cover wrong market, activity generation, roster, as-of date, window, tier, and evidence identity, plus exact-scope ready state.
- Product-default regression confirms Market Activity is unavailable with no `marketCapabilities`.
- Production build completed compilation, lint/type checks, and page generation successfully with the required backend environment configured.
- Browser acceptance: **3 Playwright tests passed** at 1440×900, 1366×768, and 390 px. Coverage includes product-default unavailable state, explicit fixture enablement, Sales, Offered Supply, partial data, synchronized inspected date, canonical x-axis alignment, A→B race protection, scope-mismatch unit coverage, no hover-time requests, and mobile layout.

## Browser evidence

- `backend/artifacts/market_activity_v1/fma3/1440x900-product-default-activity-unavailable.png`
- `backend/artifacts/market_activity_v1/fma3/1440x900-activity-off.png`
- `backend/artifacts/market_activity_v1/fma3/1440x900-sales-partial.png`
- `backend/artifacts/market_activity_v1/fma3/1440x900-offered-supply.png`
- `backend/artifacts/market_activity_v1/fma3/1440x900-synchronized-date-tooltip.png`
- `backend/artifacts/market_activity_v1/fma3/1366x768-activity.png`
- `backend/artifacts/market_activity_v1/fma3/390x844-activity.png`

## FMA-4 boundary

This remains fixture-backed acceptance work, not a live API integration. FMA-4 must supply authenticated POST transport and real per-market capability metadata through the established seams. No FMA-4 transport, caching, paging, retry, deployment, or merge work is included here.

FMA3_RECONCILIATION_READY
