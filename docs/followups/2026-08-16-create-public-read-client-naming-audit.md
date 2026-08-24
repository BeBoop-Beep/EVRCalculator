# Follow-up: public and service Supabase readers are authority-explicit

Status: RESOLVED. Originally recorded 2026-08-16; resolved 2026-08-23.

## Root cause

`create_public_read_client()` and `public_read_client` used
`SUPABASE_SERVICE_ROLE_KEY`. “Public” described the customer-facing read path
and its shorter timeout, not the database role. That naming made a privileged
client look RLS-constrained and caused a false-positive security check.

## Resolution

- Existing backend readers were audited as internal service operations and
  renamed to `create_short_timeout_service_client()` / `service_read_client`.
- `create_public_read_client()` now uses only `SUPABASE_ANON_KEY` and remains
  constrained by grants and RLS.
- Missing anon configuration raises `MissingPublicCredential`; there is no
  service-role fallback.
- Constructor-mock tests pin public/service credential separation without
  logging or asserting real secret values.

The change is authority-contract hardening. Existing internal readers retain
their service authority, while any future caller requesting a public client
receives a genuine anonymous client.
