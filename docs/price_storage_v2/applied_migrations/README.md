# Exact original applied SQL — complete frozen 89-record window

All **89** original SQL sequences for `20260905235956` through `20260906233651`
are now present here and mirrored byte-for-byte in both migration directories.
Original version IDs, SQL bytes and final-newline presence are retained. The
complete statement bytes total **409,228**; the independent manifest MD5 is
`d988d2e6e877d3373f613d2351e86339`.

The first eight originals came from prior verified recovery. The owner's full
ledger export supplied the remaining 81. See `../FULL_LEDGER_IMPORT_2026-09-07.json`
for per-record MD5, size, Git blob SHA and upload provenance. Historical annotated
repository copies remain under `../reconciliation_repository_copies/`.

These are records of migrations ALREADY APPLIED. Do not execute this archive,
reapply the SQL manually, or infer production deployment approval from source
restoration. The window includes interleaved rollout, RIP and scraper work and
requires its preceding schema/data for a meaningful isolated restore test.
Migrations outside the frozen window are not certified by this archive.

`python backend/scripts/audit_price_storage_v2_migration_sources.py --strict`
now requires 89 exact sources in both executable directories with no same-name
aliases or byte conflicts. It does not run any database command.
