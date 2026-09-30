# Runtime blockers

- `FULL_BUILD_CERTIFICATION_BLOCKED_MISSING_BACKEND_API_BASE_URL`: compile and checks passed; `/sitemap.xml` page-data collection failed.
- `ANONYMOUS_BROWSER_VERIFICATION_BLOCKED`: no complete release-like server could start after the build stopped.
- `AUTHENTICATED_BROWSER_VERIFICATION_BLOCKED`: no approved Plus/Premium session was available.
- `LIVE_EXACT_SKU_DB_VERIFICATION_BLOCKED`: no authorized configured read-only Supabase connection.
- `LIVE_PRODUCT_REFERENCE_VERIFICATION_BLOCKED`: current live Product benchmark publication could not be queried.
- `LIVE_CARD_DB_PERFORMANCE_BLOCKED`: Card query timings and plans could not be measured.
- Backend service tests importing the global Supabase client are blocked at collection because `SUPABASE_URL` and `SUPABASE_SERVICE_ROLE_KEY` are unset. Credential-free SQL contracts pass.

These are verification gaps. No credential bypass, invented URL, or fabricated session was used.
