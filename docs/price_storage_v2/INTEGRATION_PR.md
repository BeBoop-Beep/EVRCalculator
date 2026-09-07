# Price Storage V2 integration — draft, no production cutover

## Current milestone: source reconciliation is complete for the frozen window

The owner supplied the full migration-ledger export. All **89** records in
`20260905235956`–`20260906233651` pass their original SQL checksums and the
independent manifest `d988d2e6e877d3373f613d2351e86339`.

The remaining **81** originals have been restored to both migration directories
and the archive without changing existing SQL or version IDs. The source import
commit is `6ef09bcba773c5fa4319ce9ab00c08c031d2d399`; workflow `34155095653`
verified all 267 SQL copies and passed the strict 89-record gate before committing.
There are **zero missing originals and zero source conflicts within this window**.

Read `FULL_LEDGER_RECONCILIATION_2026-09-07.md` and the machine-readable
`FULL_LEDGER_IMPORT_2026-09-07.json` for exact provenance and limitations. The earlier
`SOURCE_RECONCILIATION_2026-09-07.md` records the preceding eight-original checkpoint
and is historical, not the current remaining-work inventory.

The import caught and fixed a name-matching bug in the audit: `fix_foo` must not
be treated as another timestamped copy of `foo`. No SQL content or hash was relaxed.
The temporary write-enabled importer and compressed transport have been removed.
The standard CI workflow now enforces `--strict` and contains no DB credentials.

## Proposed application integration remains unpublished

- Member/root coordinator defaults to dry-run and uses separate publisher RPCs.
- `backend/db/proposals/price_storage_v2_scoped_publication.sql` specifies separate
  destinations, a disabled release gate, exact source-generation revalidation,
  candidate comparison, and immutable/conflict-rejecting publication.
- The public source check distinguishes combined public-root publication from
  member-only or generic rollout rows; no cohort expansion is implied.
- The production index math is shared with a read-only three-set comparison CLI.
- Existing scheduled writers have NOT been connected to these new destinations.
- No legacy history is retired by this PR or by source reconciliation.

## Validation coverage and limits

The existing suite consists of 40 pure unit tests, seven original-source regressions
and 20 PostgreSQL 17.6 transaction/permission/concurrency tests. New full-window tests
check all89 originals in allthree locations, import provenance, strict positive and
negative gates, full-name alias semantics and zero-write repeated reconciliation.

The PostgreSQL test executes the publisher proposal unchanged on a disposable service
with synthetic prerequisite tables and a controlled preview. It has proven writer-order
independence, independent destinations, retries/noops, conflicts and rollback, source
and candidate rejection, and role restrictions. It is NOT a restored production schema,
real pricing selection test, or scraper/simulator/snapshot end-to-end replay.

```sh
python backend/scripts/audit_price_storage_v2_migration_sources.py --strict
python backend/tests/run_price_storage_v2_unit.py
python -m unittest backend.tests.test_price_storage_v2_migration_reconciliation backend.tests.test_price_storage_v2_full_ledger backend.tests.test_price_storage_v2_reimport -v
```

`compare_price_storage_v2_pipeline.py` remains read-only. It freezes index cohort/prior
inputs, compares source paths through the same index math, fingerprints existing
snapshot payloads, optionally compares specified simulator runs, and detects concurrent
input changes. Existing payload fingerprints are not a replacement for replaying actual
snapshot builders. Missing simulator run IDs remain `not_run`; full E2E remains false.

## Historical live evidence — not refreshed by this file import

The September 6 canary previews matched on 517 raw/V2 canonical prices and root baskets.
Stored member-only Crown Zenith and Celebrations rows nevertheless differed from their
combined-root candidates. They were not overwritten to manufacture publication parity.
The earlier 42 historical constituent exceptions remain a separate acceptance question.
No current scraper completion, publication approval, or DB health is certified by the
uploaded migration ledger. This continuation performed no production DB statements.

## Remaining integration gates

1. Review migration ordering and dependencies outside the now-complete frozen window;
   incorporate concurrent main changes without overwriting unrelated work.
2. Execute against real prerequisite schema and source functions with representative
   data, rather than only the controlled preview used for writer-transaction tests.
3. Connect scheduled member and combined-root producers under explicit release control.
4. Replay actual snapshot/index builders and simulator price readers, preserving subset,
   edition, partial-coverage, freshness, and historical-publication semantics.
5. Approve a bounded production cutover with rollback; retire legacy structures only
   after all direct readers, rebuild scripts and historical fallbacks are replaced.

No new Supabase branch, production SQL apply, database push, source-job state repair,
raw-price deletion, snapshot publication or simulator run was performed for this import.
Do not reapply recovered SQL to production or treat source completeness as release approval.
