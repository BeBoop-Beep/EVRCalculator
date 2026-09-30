# Runtime blockers

Resolved:

- `FULL_BUILD_CERTIFICATION_BLOCKED_MISSING_BACKEND_API_BASE_URL`: resolved. The documented local backend URL was supplied to both build variables; the full 85-page production build passed.
- `ANONYMOUS_BROWSER_VERIFICATION_BLOCKED`: partially resolved. Production-browser desktop/mobile fixture acceptance and security inspection passed, but live-backed Overview data is unavailable.

Remaining:

- `ANONYMOUS_LIVE_DATA_VERIFICATION_BLOCKED`: localhost backend cannot legitimately start because required Supabase configuration is absent; Overview displays four “Temporarily unavailable” cards and Opening Economics unavailable.
- `AUTHENTICATED_BROWSER_VERIFICATION_BLOCKED`: no approved Plus/Premium session or approved storage state exists. No auth was fabricated and no cookies/tokens were read or saved.
- `LIVE_EXACT_SKU_DB_VERIFICATION_BLOCKED`: `SUPABASE_URL` and `SUPABASE_SERVICE_ROLE_KEY` are absent.
- `LIVE_PRODUCT_REFERENCE_VERIFICATION_BLOCKED`: the live Product publication cannot be queried without authorized DB/backend access.
- `LIVE_CARD_DB_PERFORMANCE_BLOCKED`: Card queries/plans cannot be measured without authorized DB access and a paid browser session.
- `PAID_GRAPH_RUNTIME_VERIFICATION_BLOCKED`: add/remove/Overall-only/window/tooltip behavior cannot be exercised without entitlement and history data.
- `AGENT_BROWSER_EXECUTABLE_BLOCKED`: the prescribed executable was not installed; repository Playwright was used as the browser fallback.

These are access/configuration gaps, not PASS results. No credential bypass, invented service, deployment, write, migration, or publication action occurred.
