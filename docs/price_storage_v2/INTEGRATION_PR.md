# Price Storage V2 integration — draft, not a production cutover

## Delivered by this PR

The new Python module separates member and root publication calls, defaults to dry-run,
and validates a root's complete source/shadow receipt set before using its preview.
The existing index builder now shares its production calculation function with a
read-only three-root comparison CLI. The public rollout materialization check uses
the exact public rollout view and requires scope-specific public-root provenance:
member-only or generic-rollout rows cannot stand in for public root publication.
An incomplete refresh/dry-run cannot silently build a public index from member rows.

`backend/db/proposals/price_storage_v2_scoped_publication.sql` specifies separate
member/root history tables and resumable, idempotent publisher functions. Its
release gate starts disabled. The functions re-run the source preview, verify the
full candidate rows against the independent recomputation, and refuse conflicting
immutable publications. The two destinations are independent: writer order cannot
make one overwrite the other. This SQL is deliberately outside automatic migration
folders; it has NOT been executed on production or validated on a PostgreSQL test
instance in this execution.

No existing DB function, cron, snapshot, frozen simulation record or raw observation
was changed while preparing this PR. This PR is not authorization to drop legacy data.
Do not merge/deploy it until the gates below have been satisfied.

## Migration reconciliation is an explicit remaining gate

A live read-only inspection found **89 applied migration records / 409,228 statement
bytes** in the interval `20260905235956`–`20260906233651`. The exact checksum and
checkpoint are in `live_migration_checkpoint.json`. This interval also contains
interleaved RIP, scraper and rollout migrations; it is not exclusively Price Storage V2.

The original statements have NOT all been imported into this PR. Existing repository
history includes both nominal timestamps and remote-history placeholders. Guessing
replacement IDs or creating additional placeholders would conceal drift.

The included reconciler exports the original statements using a READ ONLY transaction,
verifies the inspected manifest, detects version/name/content conflicts before any
filesystem writes, and preserves exact original bytes and version IDs in both migration
folders. It never applies SQL or calls migration repair. A compatible local repository
checkout with `psql` and an authorized DB connection is needed for its database export.
The execution environment used for this PR had connector access but no local repository
network checkout, PostgreSQL client or DB connection; no credentials were requested or
embedded to bypass that limitation.

```sh
# Environment variable contains the existing connection URL; don't paste it into arguments.
python backend/scripts/reconcile_price_storage_v2_migrations.py --database-url-env DATABASE_URL
# Only after reviewing/resolving the reported collisions:
python backend/scripts/reconcile_price_storage_v2_migrations.py --database-url-env DATABASE_URL --write-files
```

Alternatively supply the JSON output of the script's `EXPORT_SQL` through `--export-json`.
The default is always a filesystem dry-run. Changed manifest = stop and re-audit; do
not weaken validation to make an updated export pass an obsolete checkpoint.

After reconciliation, generate the proposed migration with the installed Supabase CLI
(`supabase migration new price_storage_v2_scoped_publication`), copy the proposal SQL,
mirror according to the repository convention, and test against an isolated restored
schema. Do not execute the historic migration files manually against production.

## Tests and limitations

Run the hermetic suite:

```sh
python -m unittest backend.tests.test_price_storage_v2_integration -v
```

Forty initial tests passed locally. They cover scope/provenance rejection, null vs zero,
subset completion receipts, immutable destination routing, duplicate and stale inputs,
index economics and transition neutralization, exact migration checksums, collision
handling, and proposal-source guard assertions. The pure production index function is
AST-loaded to isolate it from database-client imports. SQL assertions inspect source;
they are NOT database execution tests. The writer-order tests assert independent RPC
routing; they are NOT a substitute for transaction/order tests in PostgreSQL.

The comparison CLI is read-only and opt-in:

```sh
python backend/scripts/compare_price_storage_v2_pipeline.py --market-date 2026-09-06 --output artifacts/v2-canary.json
# Optional: add --calculation-run-id for each exact existing run to check current/frozen view rows.
```

It obtains the Evolving Skies / Crown Zenith / Celebrations inputs, invokes the **same
production index math** twice with frozen cohort and previous rows, fingerprints complete
existing snapshot payloads before/after, and repeats source checks to detect concurrent
changes. It has no commit switch, never runs a scraper/simulation, never stages a value,
and never publishes an index. Only source-storage provenance fields are excluded from
economic comparison; actual card counts, dates, returns, and cohort membership remain.
Missing simulator run IDs are `not_run`, never a pass. Snapshot fingerprints establish
no observed payload change, NOT reproduction by the new builder. `full_end_to_end_pass`
stays false until real snapshot-builder replay is added and executed separately.

## Live source evidence obtained during PR preparation

For market date September 6, all three source-gated previews passed raw/V2 and live-root
basket comparisons: **517 canonical card rows** (237 + 230 + 50), with zero differences.
However, the shared stored-history table still has the following scope mismatch:

| Set | Stored Standard | Candidate combined-root Standard | Stored Top 10 | Candidate combined-root Top 10 |
|---|---:|---:|---:|---:|
| Evolving Skies | 8,305.06 / 237 cards | 8,305.06 / 237 cards | 6,596.25 | 6,596.25 |
| Crown Zenith | 254.87 / 160 cards | 2,634.47 / 230 cards | 151.47 | 1,432.66 |
| Celebrations | 106.76 / 25 cards | 624.16 / 50 cards | 102.07 | 512.14 |

A correct comparison must flag these as incompatible existing scope, not assert that
storage compression lost prices. They were not overwritten to obtain a passing report.
The full CLI was not executed against production from this environment; the recorded
live evidence is the read-only SQL source preflight, not a fabricated E2E result.

Brilliant Stars and Shining Fates still had failed scheduled jobs and absent current-day
shadow records at the inspection. This does not establish the status of manual reruns.
Do not import partial observations or fabricate completion receipts. The 42 historical
constituent exceptions and legacy prune-disabled setting remain untouched.

## Required before merge / rollout

1. Import/reconcile the original 89 migration records and review interleaved ownership.
2. Execute the proposed SQL on an isolated restored database; test disabled gate,
   source receipt drift, candidate tampering, two writer orders, repeat/noop behavior,
   conflicts, concurrent publication, grants, and complete rollback.
3. Wire the scheduled member producer and root publication coordinator to their separate
   destinations under an explicit disabled-by-default release control. Existing writers
   are NOT yet rerouted by this PR. No undeclared trigger or scheduler should do it.
4. Execute real snapshot/index builder comparisons, exact simulator-view comparisons,
   and approved mixed-coverage/edition behavior. Preserve prior published history.
5. Approve a bounded production cutover with fallback. Do not retire any raw table while
   direct readers, rebuild scripts, or historical selection fallbacks still require it.

The current-day 122-root stage pass and the 123-set historical constituent pass concern
different tests. Neither number is blanket permission for a full-market cutover.
