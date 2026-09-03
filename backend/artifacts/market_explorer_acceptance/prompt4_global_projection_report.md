# Prompt 4 — Global Daily Projection: Repo/Tooling Readiness Report

## A. Branch / HEAD

Branch: `fix/public-rankings-entitlement-regression-2`
Starting HEAD: `df08a19ea85644b08632aae557f76f30d2446696`

This session performed repo/tooling work only: no live database connection was
made, no script was run with `--commit`, and no production writes occurred.

## B. Starting projection state (external baseline, not re-derived here)

Given as established context: 50 sets covered, 1,886,684 rows, date range
2026-04-07 to 2026-09-01. 115 sets remain unprojected. This is a planning
baseline supplied by the task, not independently verified in this session
(no live DB access).

## C. Corrected global authority (external baseline, not re-derived here)

165 sets, 34,225 physical instruments, 33,956 with NM history, 269 without.
839 retired vintage predecessor identities already excluded via
`pokemon_market_explorer_variant_merge_ledger`.

## D. Coverage metadata repair (tooling mechanism)

Implemented in `backend/scripts/publish_market_explorer_daily_projection.py`,
function `activate_or_repair_coverage`: `row_count`, `first_market_date`, and
`computed_through` for `pokemon_market_explorer_card_daily_coverage` are
**always recomputed from `pokemon_market_explorer_card_daily_states`
directly** (`compute_actual_bounds` + `count_actual_rows`), never trusted
from a prior coverage row — including when a set already appears
`up_to_date` with no new dates to materialize (the known 48/50 stale
`row_count` defect scenario). Covered by
`test_coverage_row_count_derived_from_actual_table_not_trusted_input` in
`backend/tests/unit/scripts/test_publish_market_explorer_daily_projection.py`.

## E–H, J–P. Production execution sections

Per the task instructions these are PENDING (production execution is
performed separately, external to this session):

- E. Prompt 2 cohort projection — PENDING
- F. Prompt 3 cohort projection — PENDING
- G. Existing 50 Sep-2 advance — PENDING
- H. Global daily-state reconciliation — PENDING
- J. Coverage reconciliation — PENDING
- K. Sampled interval oracle/parity — tooling built
  (`backend/scripts/accept_market_explorer_global_daily_projection.py`),
  actual results PENDING (requires live projection data)
- L. Global query smoke tests — tooling built (same script, plus reuse of
  `daily_projection_covers` in
  `backend/db/services/pokemon_market_explorer_query_service.py`), actual
  results PENDING
- M. Global/per-era cache builds — PENDING
- N. Cache summary/detail behavior — design described below (section F)
- O. Performance — PENDING
- P. Storage — PENDING

## I. Vintage predecessor exclusion (tooling safeguard)

`publish_market_explorer_daily_projection.py` calls
`load_retired_predecessor_ids`, which reads
`pokemon_market_explorer_variant_merge_ledger.predecessor_variant_id` for the
set's resolved variant authority and excludes every matched id before the
interval join in `materialize_date`. This mirrors the ledger-based (not
row-absence-based) exclusion pattern established in
`repair_market_explorer_vintage_predecessor_identities.py`. Covered by
`test_retired_predecessor_variant_excluded_from_projection`. Live
verification against the actual 839-row ledger is PENDING (no live DB
access in this session).

## Q. Tests (actual results from this session)

New test files:
- `backend/tests/unit/scripts/test_publish_market_explorer_daily_projection.py` — 11 tests, all passing
- `backend/tests/unit/scripts/test_accept_market_explorer_global_daily_projection.py` — 3 tests, all passing

Coverage in the new publication-script suite (mocked DB, no live connection):
new-set activation + reconciliation, exact interval→state parity, coverage
NOT activated on reconciliation failure, coverage `row_count` derived from
actual table contents (not trusted input), repair of the stale 48/50
`row_count` defect scenario, staggered start (set's own
`first_market_date`), forward one-day append for an already-covered set,
idempotent rerun (no duplicate/changed state, no duplicate PK rows), retired
predecessor exclusion, no-NM exclusion without fabrication, and approved-date
filtering by status/range.

Planner projection-vs-fallback path selection is exercised by the
**existing** `daily_projection_covers` tests in
`backend/tests/unit/db/services/test_pokemon_market_explorer_query_service.py`
(not duplicated here — the task explicitly asked to build around the
existing mechanism rather than reinvent it); the new acceptance script wires
directly into that same function and reports `expectedPath` per scope.

Full combined run of this session's new tests plus every suite named in the
task:

```
backend/tests/unit/scripts/test_backfill_market_explorer_variant_intervals.py
backend/tests/unit/scripts/test_accept_market_explorer_variant_engine.py
backend/tests/unit/db/test_market_explorer_instrument_eligibility_migration.py
backend/tests/unit/db/services/test_market_explorer_query_planner.py
backend/tests/unit/db/services/test_pokemon_market_explorer_query_service.py
backend/tests/unit/db/services/test_pokemon_sealed_market_explorer_query_service.py
backend/tests/unit/db/test_market_explorer_query_cache_migration.py
backend/tests/unit/scripts/test_repair_market_explorer_vintage_predecessor_identities.py
backend/tests/unit/db/test_market_explorer_staggered_start_coverage_migration.py
backend/tests/unit/scripts/test_publish_market_explorer_daily_projection.py
backend/tests/unit/scripts/test_accept_market_explorer_global_daily_projection.py
```

Result: **166 passed, 0 failed** (note: `test_pokemon_sealed_product_market_explorer_query_service.py`
named in the task prompt does not exist in this worktree; the actual sealed
query-service test file is `test_pokemon_sealed_market_explorer_query_service.py`,
which was run above).

`git diff --check` on this session's changed files: clean (exit 0).

## R. Production writes

NONE. This session made zero live database connections, ran no script in
`--commit` mode, and performed zero production writes.

## S. Final decision

**PROMPT4_REPO_READY** — repo-side publication tooling, coverage-repair
mechanism, vintage/no-NM safeguards, resumable/idempotent batching, sampled
global acceptance tooling, and a mocked test suite (166/166 passing) are in
place. This is explicitly NOT "accepted": production has not executed the
publication contract, reconciled global daily-state coverage, run the
sampled oracle/parity checks against live data, or built any cache. Those
remain PENDING and are owned by the external production-execution process.

## Migration source-control sync (non-blocking open item)

Searched this worktree for the three Prompt 3 production migration files:

- `20260902221622_add_market_explorer_vintage_identity_repair_primitives.sql`
- `20260902221819_add_scoped_variant_monthly_rollup_rebuild.sql`
- `20260903034704_harden_market_explorer_vintage_top_hits_rebuild.sql`

None were found anywhere under `backend/` in this worktree (confirmed via
recursive filename search; `backend/db/migrations/` contains no file with
any of these three timestamps). This matches the note already present in
`repair_market_explorer_vintage_predecessor_identities.py` (lines 48-52,
citing the same migrations as installed in production but not present in
this worktree). No SQL was guessed or invented.

**Status: `PRODUCTION_MIGRATION_SOURCE_SYNC_PENDING_CHATGPT`** — non-blocking
open item for this prompt; must be resolved (exact SQL mirrored into
`backend/db/migrations/`) before those three migrations can be considered
under source control in this repository.

## Batching order implemented by the publication tooling

`publish_market_explorer_daily_projection.py` accepts `--set-id`
(repeatable) and `--era-id` (repeatable) exactly like
`backfill_market_explorer_variant_intervals.py`, so the batching order
specified in the task (1. Prompt 2 newer cohort, 2. Prompt 3 older/special
cohort, 3. existing 50-set Sep-2 append + coverage repair, 4. final global
reconciliation) is achieved by invoking the script four times with the
appropriate `--set-id`/`--era-id` scope for each phase — the script itself
is scope-agnostic and idempotent per invocation, so cohorts can be run in
any order and interrupted/resumed without corrupting totals (coverage is
always recomputed from actual table contents on every invocation, per
section D).
