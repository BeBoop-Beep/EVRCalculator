# Full frozen-window migration sources restored

## Completed from the owner's uploaded export

The source-history blocker for migration versions `20260905235956` through
`20260906233651` is resolved. The uploaded JSON contains 89 distinct ledger
records and 409,228 original UTF-8 SQL bytes. Every statement MD5 and the
independently saved manifest match:

- Manifest MD5: `d988d2e6e877d3373f613d2351e86339`
- Uploaded file SHA256: `26f40b379488f6ae927bf0287bae9b94a78b79c3526ed7aa46c94991422c532c`
- Successful source import workflow: `34155095653`
- Source import commit: `6ef09bcba773c5fa4319ce9ab00c08c031d2d399`

The importer added **81 original SQL sequences / 243 new SQL files** and verified
that the **24 existing files** (eight originals in three locations) were unchanged.
All 89 originals now exist byte-for-byte under their actual applied IDs in:

1. `supabase/migrations/`
2. `backend/db/migrations/`
3. `docs/price_storage_v2/applied_migrations/`

The strict repository audit returned `migration_sync_complete=true`,
`status_counts={"reconciled":89}`, zero aliases/content conflicts and zero missing
archive sources. `FULL_LEDGER_IMPORT_2026-09-07.json` contains the per-file byte
counts, hashes, Git blob identities, source provenance and complete audit summary.

## Validation correction, not SQL rewriting

The initial import stopped before committing because the old audit compared
migration names by suffix. It misclassified the independently recorded migration
`fix_activate_exact_parity_set_market_rollouts` as an alias of
`activate_exact_parity_set_market_rollouts`.

The audit and reusable reconciler now compare the COMPLETE name after the version.
The distinct original and fix migration both remain intact. Real same-name aliases,
changed SQL, missing files and bad manifests are still rejected. No original SQL
byte was edited to make validation pass. Regression tests cover both the legitimate
fix name and an intentionally introduced real alias.

The temporary importer used an ephemeral GitHub Actions token solely to commit
source files to the existing PR168 branch. It did not accept a database connection
or execute SQL. The one-use contents-write workflow, importer and compressed transport
were removed after the verified import. Normal validation retains `contents: read`.

## Release scope remains narrow

This completes SOURCE restoration for the frozen 89-record window. It does not
certify all earlier/later migrations or prove a fresh database can replay this slice
independently. Some original migrations dynamically clone prerequisite functions
or have data-dependent preconditions. Restore testing needs the correct preceding
schema and representative data. Existing SQL must not be reapplied to production.

The separate-destination publisher proposal remains outside migration directories.
No production migration, SQL statement, scrape, simulation, snapshot publication,
raw-price deletion, or storage reclamation was performed by this import.

The user does not need to export this same window again. Next integration work is
real-prerequisite schema/source validation, followed by scoped producer wiring and
actual snapshot/index/simulator-reader acceptance. Post-window migrations and
concurrent main changes require separate review before a bounded cutover.

## Reproducible source checks

```sh
python backend/scripts/audit_price_storage_v2_migration_sources.py --strict
python backend/tests/run_price_storage_v2_unit.py
python -m unittest backend.tests.test_price_storage_v2_migration_reconciliation backend.tests.test_price_storage_v2_full_ledger backend.tests.test_price_storage_v2_reimport -v
```

CI now requires the strict full-window gate instead of merely printing remaining
gaps. It also runs the existing 20 PostgreSQL 17.6 writer tests on synthetic
prerequisites. Those tests are not a live-schema restore or end-to-end publication.
