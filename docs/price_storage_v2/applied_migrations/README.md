# Exact original applied SQL — eight-record checkpoint

This archive contains eight exact original UTF-8 statement sequences from the frozen
89-record production ledger. The same bytes now appear under their original applied
version IDs in both `supabase/migrations/` and `backend/db/migrations/`.

Five were recovered by checksum from repository copies; three were previously
exported and archived. All eight match the captured ledger MD5 and Git blob SHA.
See `../SOURCE_RECONCILIATION_2026-09-07.md` for each difference and timestamp mapping.
The explanatory repository copies are preserved separately, not in executable folders.

**81 original migrations are still missing. Full history reconciliation and dependency
replay are NOT complete.** Do not execute this partial archive, reapply these records
to production, repair the live migration ledger, or deploy the unpublished proposal.

Run `python backend/scripts/audit_price_storage_v2_migration_sources.py` to inspect
status. `--strict` must remain nonzero until all 89 sources are reconciled. Archive
integrity is not deployment readiness.
