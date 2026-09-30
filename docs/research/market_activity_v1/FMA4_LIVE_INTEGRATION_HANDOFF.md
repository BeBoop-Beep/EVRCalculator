# FMA-4 — Live frontend integration handoff

Status: **IMPLEMENTATION COMPLETE / PR CREATION BLOCKED BY LOCAL GITHUB AUTHORITY**

## Delivery identity

- Starting SHA: `0689a04de41379da670fc8f1787d6548a11d6f12`
- Implementation SHA: `30c1a58d6022718aea74dc1f956743ef0e34aed9`
- Branch: `fma4-live-market-activity-integration`
- Remote branch: `origin/fma4-live-market-activity-integration`
- PR: not opened; this environment has no `gh` executable and no `GITHUB_TOKEN`/`GH_TOKEN`
- Compare/open-PR URL: `https://github.com/BeBoop-Beep/EVRCalculator/compare/develop...fma4-live-market-activity-integration?expand=1`
- Contract: `market_activity_v1.1`
- Domain: `market_activity_domain_v1.1.0`
- Fixture set: `market_activity_v1_fixtures_2`
- Fixture manifest SHA-256: `e6235d9c73dc7ce6e38b81431bcfe60e4a32ae27f2780632aae45d407705e007`

No backend Python, database migration, generation promotion, collector, provider integration, deployment, or merge is included.

## Endpoint and proxy integration

The frontend now uses these structured POST endpoints:

- `/api/market/explorer/activity/capabilities` → `/market/explorer/activity/capabilities`
- `/api/market/explorer/activity` → `/market/explorer/activity`
- `/api/market/explorer/activity/constituents` → `/market/explorer/activity/constituents`
- `/api/market/explorer/activity/instrument` → `/market/explorer/activity/instrument`

Proxy route files are under `frontend/app/api/market/explorer/activity/`. Shared forwarding is in `frontend/lib/explore/marketActivityProxy.js`. It forwards only `Authorization`, `Cookie`, JSON content negotiation, and the original body. It preserves backend status and response text without reshaping, sets `Cache-Control: private, no-store` and `Vary: Cookie, Authorization`, and maps network failure to `503 / MARKET_ACTIVITY_PROXY_UNAVAILABLE`. No service-role, provider, or database credentials are referenced.

`frontend/lib/explore/marketActivityApi.mjs` is the production browser transport. It uses `boundedFetch`, caller abort signals, `credentials: include`, JSON POST bodies, and typed 400/401/403/5xx failures. It performs no retries.

## Capability discovery lifecycle

`useMarketActivityCapabilities` batches the eligible active card-market set. Its key contains user identity, resolved plan, focus key, canonical market key, and immutable roster reference. Focus is absent from the trigger, so changing focus among an unchanged active set performs no capability request.

Stale batches are aborted and sequence-guarded. The cache is cleared on logout, identity change, or plan downgrade. Removing/adding a market or changing its prepared generation changes the exact batch key. Basic has no capability request, and sealed/graded Explorer assets are excluded. The backend remains the entitlement authority.

Prepared V2 markets derive `SURFACE_V2_GENERATION` only from the series' backend-published `generationId` and canonical key. Custom markets require an explicit published `revisionId` and use `QUERY_CACHE_PUBLISHED_REVISION`. A query fingerprint alone never enables Activity. Current custom query responses do not publish such an immutable revision, so custom Market Activity remains unavailable.

## Live group Activity

Normal product mode now defaults to `fetchMarketActivityGroup`; only `MARKET_ACTIVITY_FIXTURE_MODE=1` uses the fixture payload. The request includes exact capability pins and the visible canonical chart start/end dates. Response validation covers contract, market, activity generation, roster, as-of, window, tier, evidence fingerprint, and chart range before rendering.

The canonical chart remains pointer/crosshair/tooltip owner. Activity receives the inspected date. No hover-time request, forward-fill, or missing-as-zero behavior was added. A failed Activity read preserves the canonical graph and an exact-scope last-known payload. Manual Retry is available for retryable failures; there is no automatic loop. Auth, entitlement, invalid, domain-unavailable, and temporary-unavailable states have distinct copy.

Live mode contains descriptive source/methodology copy. “Fixture-backed / not live API” appears only when explicit fixture mode is active.

## Constituent Activity and instrument drilldown

Constituents defaults to Performance. Activity is a local card-only view and is shown only with an exact capability. Pages use the server cursor and server roster order; there is no client-page sort. Canonical display metadata joins only by exact `cardVariantId`, and the raw `instrumentKey` must match that same variant. A mismatch is withheld rather than borrowing another variant's metadata.

Desktop columns are Card, Observed Sales, Proven Sales, Median Sale, Ask State/Lowest Ask, and Coverage. Missing values render as unavailable, never zero. Mobile uses compact cards.

Opening a row performs one instrument request and displays exact tier identity, observed/proven windows, price summary/sample basis, ask state and bounded supply, source confirmation, peer percentile/denominator/supplied scope label, and unavailable reasons. Closing the drawer leaves parent market, focus, target, filters, and timeframe untouched. No instrument prefetch exists. Raw is shown by default; graded Activity is explicitly unavailable unless an exact graded instrument payload is published, and no grader tiers are merged.

## Request counts

The proxy-backed browser acceptance recorded:

- capability discovery: 1 request for the active-set revision
- enabled group Activity: 1 request
- first Activity constituent page: 1 request
- explicitly opened instrument: 1 request
- chart hover/keyboard inspection: 0 Activity requests

The first-page constituent request is in-flight deduplicated so React development strict-effect replay does not duplicate the HTTP read.

## Verification

- Focused contract/regression run: 45 passed, 0 failed.
- Wider Explorer React run: 105 passed, 34 intentional skips, 0 failed after the one source-layout reconciliation assertion was restored.
- All 19 accepted Activity fixtures passed manifest, fixture fingerprint, contract, and request-pin validation.
- Production build: compiled, lint/type checked, and generated successfully with local required URL environment values. Existing unrelated repository warnings remain; FMA-4 introduced no remaining hook warning.
- Fixture browser acceptance: 2 passed at 1440×900, 1366×768, and 390×844, covering Sales, Offered Supply, shared inspection, sparse alignment, and zero hover requests.
- Live proxy browser acceptance: 2 passed, covering Plus capability/group, constituent Activity, exact instrument drawer, Basic locked state, mobile, non-fixture copy, and exact 1/1/1/1 request counts.
- Accessibility checks: semantic tablists/tabs, status/alert live regions, dialog labelling, keyboard-reachable buttons, minimum mobile control sizing, explicit unavailable text, and retained canonical chart keyboard inspection.
- `agent-browser` was unavailable on PATH; repository Playwright was used for real-browser acceptance.

## Browser evidence

- `backend/artifacts/market_activity_v1/fma4/1440x900-basic-activity-locked.png`
- `backend/artifacts/market_activity_v1/fma4/1440x900-live-group-sales.png`
- `backend/artifacts/market_activity_v1/fma4/1440x900-live-constituents-activity.png`
- `backend/artifacts/market_activity_v1/fma4/1440x900-live-instrument-detail.png`
- `backend/artifacts/market_activity_v1/fma4/390x844-live-activity.png`
- FMA-3 fixture evidence was rerun and restored in its existing artifact directory without changing the accepted files.

## Known data-readiness limitations

- Custom Activity stays unavailable until the query/series response publishes an immutable `QUERY_CACHE_PUBLISHED_REVISION.revisionId`.
- Exact graded tiers appear only when the backend publishes an exact graded instrument payload/capability. Raw parent Market Index is never relabelled as graded.
- Production usefulness depends on FMA-2 serving the shared routes and on a live Activity generation whose roster pins match the current prepared generation.
- The mocked live backend is browser-test infrastructure only; it is not imported by product code.

## FMA-5 release requirements

1. Open the PR from the pushed branch and obtain review; do not merge until FMA-2/FMA-4 reconciliation is complete.
2. Reconcile response/error details against the final FMA-2 route implementation without weakening the frozen v1.1 pins.
3. Run authenticated staging acceptance for Basic, Plus, and Premium against a real promoted Activity generation.
4. Verify logout/downgrade and expired-generation behavior with real auth/cache boundaries.
5. Confirm production observability for proxy 503s, backend 401/403/400, generation expiry, and roster mismatch.
6. Re-run 1440×900, 1366×768, and 390 px acceptance and retain network-count evidence.
7. Complete security/accessibility review, release approval, generation promotion, and deployment as separate authorized work.

FMA4_BLOCKED
