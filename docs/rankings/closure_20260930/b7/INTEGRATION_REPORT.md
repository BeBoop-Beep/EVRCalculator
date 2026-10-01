# Integration report

The final tree combines current develop with the complete B0â€“B6 Rankings closure. B7 additionally reconciles stale tests and fixes Overall-only history window switching by retaining one prior selected entity as a request-only transport anchor. The anchor is never restored to chart selection and therefore cannot render an entity line or legend entry.

## Verification

- Focused B1â€“B6 frontend: 70/70 passed.
- Maintained Rankings-related frontend after reconciliation: 341/341 passed.
- Credential-free backend migration contracts: 14/14 passed.
- Backend service suites: BLOCKED during collection by the repository's explicit missing Supabase configuration guard.
- Full frontend repository baseline: 3,191 passed, 322 failed, 34 skipped. Failures include unrelated current-develop Market Explorer/SEO source-shape drift and are not represented as a green repository-wide gate.
- Production build: optimized compilation passed in 18.1 seconds and lint/type checking completed with existing warnings; page collection failed at `/sitemap.xml` because `BACKEND_API_BASE_URL` is unset.
- Browser and live DB: not run because no legitimate backend configuration, authenticated session, or DB credentials were available.

## Best-Open contract

The UI definition `(market - threshold) / market` matches the canonical engine, publication validation migrations, and backend tests. No discrepancy exists. Numeric MSRP remains absent when exact-SKU evidence is unavailable.

No migrations, publications, scoring changes, remote writes, or production mutations were performed.
