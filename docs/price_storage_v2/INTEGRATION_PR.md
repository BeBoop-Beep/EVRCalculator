# Price Storage V2 integration — draft, no production cutover

## Current source checkpoint: September 7, 2026

See `SOURCE_RECONCILIATION_2026-09-07.md` for the reviewed original-source reconciliation.
All five previously flagged discrepancies were comment/whitespace differences, with
three also carrying nominal filenames different from their applied ledger timestamps.
Each complete recovered byte stream matches the independent ledger checksum and Git
blob SHA. Explanatory repository copies remain preserved separately.

**Eight original migrations are now present under the ledger IDs in both migration
folders and the archive. Eighty-one are still missing.** The existing strict checker
continues to block complete migration synchronization. None of the recovered files
was executed against a database. Do not reapply them manually or deploy this partial
history. A fresh export of the remaining originals is required; database access was
not available in this continuation.

The PR incorporates main through `a3efb5e8ebde199a58d42d90ff8a27e1e4701544`, preserving
its newer Collector Appeal and Market Explorer work. The two sets of changed paths
had no overlap. This is a feature-branch update, not a merge into or deployment of main.

## Implemented, still unpublished

- Explicit member/root coordinator, dry-run by default.
- Separate-destination SQL proposal with a disabled release gate, independently
  revalidated source evidence, immutable conflicting-publication rejection and retries.
- Correct public-root source-materialization checks, not just row-existence checks.
- Shared production index math and an opt-in read-only three-set comparison runner.
- Exact migration export/import tools, an offline inventory, and original-source tests.

`backend/db/proposals/price_storage_v2_scoped_publication.sql` remains outside executable
migration directories. Existing scheduled producers have not been connected to its new
destinations. No trigger, scheduler or production gate is added by these source changes.

## Validation boundaries

Earlier GitHub Actions runs executed the actual SQL proposal on disposable PostgreSQL
17.6: 40 pure unit tests and 20 SQL transaction/permission/concurrency tests passed.
The current suite additionally checks the eight exact sources, original timestamps,
retained comment copies, and the distinction between subset recovery and full completion.
Use the current commit's CI results rather than treating older green runs as new proof.

The SQL tests use controlled synthetic prerequisite tables and a synthetic price preview.
They prove transaction behavior, writer order independence, repeat/noop behavior,
concurrent same-run calls, permission rejection, source-drift rejection and rollback.
They do not establish real-source database restore or full scraper/simulator/snapshot
integration. Sentinel data verifies isolated tests do not modify their protected fixtures;
it is not a production-data audit.

```sh
python backend/tests/run_price_storage_v2_unit.py
python -m unittest backend.tests.test_price_storage_v2_migration_reconciliation -v
python backend/scripts/audit_price_storage_v2_migration_sources.py
# Intentionally fails while original sources remain missing:
python backend/scripts/audit_price_storage_v2_migration_sources.py --strict
```

The original migration reconciler uses READ ONLY database transactions and defaults to
filesystem dry-run. It retains exact original SQL and IDs and refuses conflicting
paths. It never runs migration repair, applies SQL, renumbers ledger history or creates
placeholder SQL. The frozen 89-record window includes interleaved work, not one standalone
replayable migration. Later migrations need separate inspection before deployment.

```sh
python backend/scripts/reconcile_price_storage_v2_migrations.py --database-url-env DATABASE_URL
# Only after reviewing the plan and resolving collisions:
python backend/scripts/reconcile_price_storage_v2_migrations.py --database-url-env DATABASE_URL --write-files
```

The read-only comparison CLI remains opt-in. It does not scrape, simulate, stage or publish.
It compares the shared index math on frozen inputs, fingerprints complete existing
snapshot payloads before/after and checks source stability. Payload fingerprints are
not a replay of the actual snapshot builders. Missing simulator run IDs remain `not_run`;
`full_end_to_end_pass` remains false until the actual builder replay is implemented and run.

```sh
python backend/scripts/compare_price_storage_v2_pipeline.py --market-date 2026-09-06 --output artifacts/v2-canary.json
```

The last recorded three-set source preflight covered 517 canonical prices across Evolving
Skies, Crown Zenith and Celebrations with zero raw/V2 and live-root basket differences.
Stored member-only rows for the latter two were not overwritten to manufacture parity.
Those are historical observations, not refreshed live status in this continuation.

## Remaining release gates

1. Obtain/import the 81 missing original source sequences and inspect post-window migrations.
2. Restore relevant real prerequisites and verify the actual pricing/preview functions.
3. Connect the scheduled member and root producers under explicit release control.
4. Replay actual snapshot/index builders and simulator price-reader checks, preserving
   subset, edition, partial-coverage, freshness and already-published-history semantics.
5. Approve a bounded production cutover with rollback, then retire legacy structures
   individually only after every direct/rebuild/fallback dependency has been replaced.

The PR remains draft. Source-only reconciliation and successful fixture CI do not
permit data deletion, gate enablement or a production deployment.
