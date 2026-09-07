# Price Storage V2 integration — draft, no production cutover

## Verified milestone: the SQL proposal ran on PostgreSQL 17.6

GitHub Actions run **34089247679**, job **101639220165**, passed on commit
`02d67e5b320f9bde26f31b15fde32a334d5759c3` (tested merge
`737563f4f39ff5f1c0f8d37c81a77246c4c6f4d4`). The logs confirm:

- 40 pure unit/regression tests passed.
- 20 PostgreSQL transaction/permission/concurrency tests passed.
- Database identity: `price_storage_v2_ci`, PostgreSQL server_version_num `170006`.
- Both writer orders produce the same scoped data; member/root destinations stay separate.
- Repeat calls are no-ops including timestamps; same-run concurrent calls result in complete + noop.
- Conflicts roll back partial writes. An explicit outer transaction rolls back both RPCs.
- Independent member and root RPCs are resumable, not implicitly one atomic publication.
- Disabled gates, stale source generations, tampered/missing candidates, wrong root/date/run,
  blocked/missing previews, and unauthorized access are rejected.
- Sentinel legacy history, snapshots and simulation rows remain unchanged in every test.

The SQL proposal is executed unchanged. Prerequisite tables and the pricing preview
are **synthetic controlled fixtures**, not a restored production schema. Thus these
results validate the proposed writers' SQL/transaction behavior, not live data
selection or a complete scraper/simulator/snapshot replay.

The first two CI attempts exposed runner setup issues (Docker health-command quoting
and application package initializers loading database dependencies). They were fixed
without adding any production credentials. Pure tests load their exact implementation
files directly; they do not certify complete application package-import integration.

The CI job uses a disposable PostgreSQL Docker service and `contents: read`. It accepts
only that service's local Docker container ID and the designated test database name.
It never accepts a Supabase URL/DSN or production key. The test database is destroyed
after the run; no paid Supabase branch or production compute upgrade was created.

## Implementation in this PR

`price_storage_v2_integration.py` separates member/root coordinator calls, defaults to
dry-run and validates complete source/shadow evidence before using a root preview.
The SQL proposal creates independent destinations and starts with its release gate
disabled. It recomputes source evidence and candidates before writing, and rejects
conflicting immutable publications. It is still outside automatic migration folders.

The production index calculation function is shared with a read-only three-root
canary. The proposed public-rollout materialization check rejects member-only and
generic-rollout rows as substitutes for public-root publication. No production source
reader has been switched to the new destinations by this PR.

## Migration reconciliation: progress, not complete

Read-only production checks reconfirmed **89 applied records / 409,228 UTF-8 statement
bytes** in `20260905235956`–`20260906233651`, manifest MD5
`d988d2e6e877d3373f613d2351e86339`.

`applied_migration_manifest.psv` records each original version, name and SQL MD5.
`applied_migrations/` now preserves three exact original SQL sequences for the member
publication interlock, isolated scope staging and append-only backend grants. Their
statement MD5 and Git blob SHA match production exactly. The other **86 sequences
are not archived here**; full executable-directory reconciliation remains blocked.

The offline source auditor scans both migration folders, distinguishes exact originals
from changed SQL, nominal timestamp aliases, and missing sources, and checks every
archived file against the independent manifest. Integrity success is NOT migration
completion. Use `--strict` for the latter gate.

The original reconciliation utility is still available for a complete read-only export
and collision-checked local import. It never applies SQL, repairs history, renumbers
versions or overwrites files. Existing same-name/different-version migrations require
explicit review; matching names alone do not establish identical SQL.

```sh
python backend/scripts/audit_price_storage_v2_migration_sources.py
python backend/scripts/audit_price_storage_v2_migration_sources.py --strict
python backend/scripts/reconcile_price_storage_v2_migrations.py --database-url-env DATABASE_URL
# Only after reviewing/resolving collisions:
python backend/scripts/reconcile_price_storage_v2_migrations.py --database-url-env DATABASE_URL --write-files
```

The connection URL belongs in the existing local environment, never an argument or
CI secret for these tests. `--export-json` is the importer's offline alternative.
The full migration range includes interleaved RIP/rollout/scraper work, so it must not
be treated as one standalone replayable migration. Preserve original IDs and SQL.

## Reproducible tests

```sh
# Pure unit tests, without database-client package initialization:
python backend/tests/run_price_storage_v2_unit.py
# PostgreSQL tests run automatically via .github/workflows/price-storage-v2-contracts.yml.
# A deliberately named disposable PG17 service container is required for local execution.
python -m backend.tests.test_price_storage_v2_postgres
```

The read-only comparison CLI remains opt-in:

```sh
python backend/scripts/compare_price_storage_v2_pipeline.py --market-date 2026-09-06 --output artifacts/v2-canary.json
# Optionally add explicit --calculation-run-id values for simulator-view comparison.
```

It freezes the cohort and previous index inputs, runs the shared production index math
on both source paths, fingerprints complete existing snapshot payloads before/after,
and repeats source checks to detect concurrent changes. It never stages, scrapes,
simulates, or publishes. Snapshot fingerprints establish no observed payload change,
not reproduction by the new snapshot builder. Missing simulator IDs remain `not_run`;
`full_end_to_end_pass` remains false until an actual builder replay is implemented and run.

## Last recorded live source evidence

Sept 6 previews for Evolving Skies / Crown Zenith / Celebrations matched on **517**
canonical price rows, raw/V2 and live root baskets. Stored shared history nevertheless
contained member-only CZ (254.87 /160 cards) and Celebrations (106.76 /25), versus
combined candidates CZ (2634.47 /230) and Celebrations (624.16 /50). ES matched at
8305.06 /237. No records were overwritten to manufacture integration parity.

This continuation used READ ONLY production SQL throughout. No applied migration,
production function, scheduled writer, raw history, snapshot, or simulation was modified.
The proposed gate remains uninstalled, old pruning disabled, and audit37 remains the
last production cleanup checkpoint at the live check. The older source failures and
42 historical constituent exceptions were not force-resolved.

## Remaining release gates

1. Finish exact migration-source import and resolve executable-directory aliases/order.
2. Test against a restored prerequisite schema and real scoped source functions; the
   current PostgreSQL test preview is synthetic by design.
3. Wire the scheduled member producer and root publisher to their independent destinations
   under explicit release control. Existing scheduled writers are NOT rerouted yet.
4. Run actual snapshot/index builder replay and explicit simulator-run comparisons,
   including partial-coverage and edition behavior; preserve prior published history.
5. Approve a bounded cutover with rollback. Retire raw tables only after all direct
   readers, repair scripts and historical fallback dependencies have been replaced.

The draft remains unmerged. Passing this CI is not permission to enable publication
or reclaim old relational storage.
