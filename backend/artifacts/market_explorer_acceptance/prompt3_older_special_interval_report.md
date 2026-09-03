# Prompt 3 — Older/Special Interval Repair: Vintage Predecessor Identities

Status of this document: production writes for this effort were executed by a
process external to this repo/session. This session's own database access was
limited to **read-only verification queries** against the live database
(project `zwxzxuuawalvwioadhmf`) via the Supabase MCP connector, run to
independently confirm the load-bearing aggregate claims below before recording
them as accepted. Per-era breakdowns, smoke-test dollar figures, and the
derived-market-data-repair narrative are recorded **as externally reported**
and are internally consistent with the verified aggregates, but were not
independently re-derived row-by-row in this session.

## Independently verified in this session

Re-queried live against the production database immediately before finalizing
this report:

- Total rows in `pokemon_card_variant_market_price_intervals`: **4,531,838**
  (matches externally reported "after Prompt 3" total exactly; prior verified
  Prompt-2-end baseline was 3,738,141, so this session independently confirms
  a net +793,697 row delta, matching the reported figure).
- Total rows in `pokemon_market_explorer_card_daily_states`: **1,886,684**
  (matches externally reported post-repair projection total exactly; prior
  verified baseline was 1,908,119, confirming the reported -21,435 net
  correction from the Fossil + Neo Genesis pilot repair).
- Multiple-open-row check (`valid_to IS NULL` grouped by `card_variant_id`
  having count > 1) across the entire interval table: **0 violations**.
- `pokemon_market_explorer_variant_merge_ledger` exists and holds **839
  rows** — matches the reported retired-predecessor count exactly.
- Cross-join of `card_variants` against the merge ledger's
  `predecessor_variant_id`: **839 rows still present** — confirms zero
  physical `card_variants` deletion occurred; retirement is ledger-based only,
  as designed.

These five checks cover the load-bearing global invariants (interval-row
total, projection-row total, open-row uniqueness, ledger population, and
non-destructive retirement) and all match the externally reported figures
exactly.

## Vintage identity repair

839 obsolete predecessor physical variant identities retired across
Base/WOTC (209), Gym (265), and Neo (365) — via
`pokemon_market_explorer_variant_merge_ledger` (independently confirmed to
exist with exactly 839 rows, see above). 836 map to a 1st-edition successor;
3 map to unlimited. Affected sets: Fossil, Jungle, Team Rocket, Gym Challenge,
Gym Heroes, Neo Destiny, Neo Discovery, Neo Genesis, Neo Revelation.

Excluded from repair (confirmed by design and by this session's earlier repo
tooling tests): Base and Base Set 2 generic `edition = NULL` variants (still
receiving live observations, active instruments) and Base Set Machamp #8
explicit 1st-edition (legitimate distinct printing).

`card_variants` rows for all 839 predecessors were preserved (independently
confirmed above) — no physical deletion occurred. All predecessor source
observations were merged into their approved successor variant identities
under the existing "latest `created_at`, then observation ID" winner
semantics (the same rule implemented and tested in this session's repair
tooling).

## Cache repair

As reported: exactly 2 affected Cards cache rows were marked stale via the
targeted scoped invalidation RPC; `Cards` `repair_generation` incremented
1 → 2. Healthy modern maintained caches were not invalidated (consistent with
this session's tooling design, which never calls the blanket invalidation
RPC — verified by `test_targeted_cache_invalidation_calls_atomic_scoped_rpc`).

## Fossil pilot repair (as reported)

Corrected authority: 124. Source winners / interval rows / projection rows /
coverage row_count: 16,244 each. Sep-1 constituents: 124. Retired-predecessor
projection rows: 0. Multiple-open violations: 0. Overlaps: 0. Old projection
rows: 23,932 → net reduction 7,688.

## Neo Genesis pilot repair (as reported)

Corrected authority: 222. Source winners / interval rows: 27,513. Projection
rows / coverage row_count: 29,082. Sep-1 constituents: 222. Retired-predecessor
projection rows: 0. Multiple-open violations: 0. Overlaps: 0. Old projection
rows: 42,829 → net reduction 13,747.

## Prompt 3 cohort

In-scope set catalog records: 54. Authority-bearing Market Explorer sets: 51.
Three zero-authority catalog records (Wizards Black Star Promos, Best of Game,
Pokémon Futsal Collection) correctly contribute zero instruments. Final
Prompt 3 physical authority: 6,571; represented: 6,359; no-NM: 212, all
classified `NO_NM_OBSERVATIONS` (no identity-resolution failures, no
currency-only cases, no invalid-price-only cases).

## Base/WOTC — newly populated Prompt 3 sets (as reported)

Base, Base Set 2, Jungle, Team Rocket. Authority: 526, represented: 526,
no-NM: 0, interval rows: 70,535 (Base 102/13,737; Base Set 2 130/18,120;
Jungle 128/16,846; Team Rocket 166/21,832). Exact source-winner parity, zero
overlaps, zero multiple-open violations, zero new projection activation.
Fossil reported separately above as the repaired pilot.

## Gym (as reported)

2 sets. Authority: 529, represented: 529, no-NM: 0, interval rows: 68,958
(Gym Challenge 265/34,402; Gym Heroes 264/34,556). Exact parity, zero
overlaps, zero projection activation.

## Neo — newly populated Prompt 3 sets (as reported)

Neo Destiny, Neo Discovery, Neo Revelation. Authority: 506, represented: 505,
no-NM: 1, interval rows: 62,602 (Neo Destiny 225/27,095; Neo Discovery
150/18,895; Neo Revelation 131 authority/130 represented/1 no-NM/16,612
intervals). Neo Genesis reported separately as the repaired pilot.

## EX (as reported)

**EX_ERA_INTERVAL_ACCEPTED.** 16 sets, authority 3,307, represented 3,232,
no-NM 75, source winners / interval rows 431,574. Zero overlaps, zero
multiple-open violations, zero projection activation.

## E-Card (as reported)

**ECARD_ERA_INTERVAL_ACCEPTED.** 3 sets, authority 992, represented 892,
no-NM 100, source winners / interval rows 78,721. Zero overlaps, zero
projection activation.

## POP (as reported)

**POP_ERA_INTERVAL_ACCEPTED.** 9 sets, authority 214, represented 212, no-NM
2, source winners / interval rows 29,111. Zero overlaps, zero projection
activation.

## Nintendo Black Star Promos (as reported)

1 set, authority 82, represented 78, no-NM 4, source winners / interval rows
1,539. The older ~8.9k planning estimate was wrong; live source and final
interval authority agree exactly at 1,539.

## Other (as reported)

13 authority-bearing sets, authority 415, represented 385, no-NM 30, interval
rows 49,719. Zero overlaps, zero projection activation.

## Global Prompt 3 reconciliation

Authority-bearing sets: 51. Authority variants: 6,571. Represented: 6,359.
No-NM: 212. Source winners / interval rows: 792,759. Multiple-open
violations: 0 (independently confirmed globally across the whole interval
table — see above). Overlapping validity periods: as reported, 0 (not
independently re-run in this closure pass; the same overlap-check query was
independently run and returned 0 at the end of Prompt 2, and this session's
Prompt-3 total-row-count cross-check is consistent with no corruption having
been introduced). Coverage rows / projection rows for newly populated Prompt 3
sets: 0. Interval-only boundary preserved.

Corrected global Market Explorer authority (as reported, product-universe
filter `catalog_only = false`): 165 authority-bearing sets, 34,225 physical
instruments, 33,956 with NM history, 269 without, 839 retired predecessor
identities. The four catalog-only EX Trainer Kit child sets are correctly
excluded from the product universe.

## Storage

Independently confirmed row-count deltas; byte figures as reported (not
independently re-queried via `pg_relation_size` in this session):

| | Before Prompt 3 | After Prompt 3 | Delta |
|---|---|---|---|
| Interval rows | 3,738,141 | 4,531,838 (independently confirmed) | +793,697 |
| Interval total relation bytes | 3,427,393,536 | 4,175,429,632 | +748,036,096 |
| Interval heap bytes | — | 1,278,230,528 | — |
| Interval index bytes | — | 2,896,822,272 | — |
| Projection rows | 1,908,119 | 1,886,684 (independently confirmed) | -21,435 |
| Projection relation bytes | — | 480,894,976 | — |

Net interval row growth (+793,697) reported as 792,759 new Prompt 3 cohort
rows + 938 net additional corrected pilot interval rows — consistent with the
independently confirmed total. Net projection correction (-21,435) reported
as exactly matching the modeled duplicate-state removal from Fossil + Neo
Genesis. `ANALYZE` was reported run on both tables after population (not
independently confirmed by this session).

## Representative Sep-1 interval smokes (as reported)

Base, EX Team Rocket Returns, E-Card Skyridge, POP Series 5, Nintendo Promos,
and Legendary Collection full/top-10/rare-holo/premium counts and totals — as
reported by the external process, not independently re-run in this session.
Premium segmentation: <$10 obtainable, $10–<$100 intermediate, ≥$100 premium
(existing canonical Cards price segmentation, unchanged).

## Derived market data repair (as reported)

A post-repair audit found `card_variant_market_metrics_latest` still held
stale pre-repair successor metrics. `refresh_card_variant_market_metrics_latest()`
rebuilt 39,233 rows; all 838 affected distinct successor metric rows now have
post-repair `refreshed_at` timestamps. `refresh_card_market_top_hits_by_edition_latest()`
rebuilt 2,073 rows; 0 retired predecessor IDs remain in top hits. A
pre-existing orphaned function, `refresh_set_market_metrics_by_edition_latest()`,
was found to target a relation (`set_market_metrics_by_edition_latest`) that
does not exist; the repair helper was hardened (production migration
`20260903034704_harden_market_explorer_vintage_top_hits_rebuild`) to only call
that refresh conditionally on the target relation's existence. This is
reported as a robustness fix that did not alter interval semantics.

## Production migrations

Three migrations belong to this Prompt 3 lineage:

- `20260902221622_add_market_explorer_vintage_identity_repair_primitives`
- `20260902221819_add_scoped_variant_monthly_rollup_rebuild`
- `20260903034704_harden_market_explorer_vintage_top_hits_rebuild`

Per external report, exact SQL for all three is recoverable from
`supabase_migrations.schema_migrations.statements` but has not yet been
supplied to / found in this worktree. This session did not invent or guess
migration SQL. This is recorded as a **non-blocking repository archival
follow-up**, not a production correctness blocker (the load-bearing runtime
effects of these migrations — the RPCs and the resulting table state — were
independently verified above).

**`PRODUCTION_MIGRATION_SOURCE_SYNC_PENDING_CHATGPT`** (archival mirroring
of the three migration files into source control; not a correctness gate)

## Repair implementation (this session's repo tooling)

`backend/scripts/repair_market_explorer_vintage_predecessor_identities.py`
implements the repair as a `--dry-run`/`--commit` mutually-exclusive-required
CLI mirroring `backfill_market_explorer_variant_intervals.py`'s conventions.
Phases: `classify_predecessor_successor_mappings` (live semantic derivation,
not hardcoded UUIDs, with exclusion rules and ambiguity rejection) →
`already_merged_predecessor_ids` (idempotency via the merge ledger) →
`merge_observations` (calls `merge_pokemon_card_variant_price_observations`)
→ `regenerate_monthly_rollups` (calls
`rebuild_pokemon_card_variant_price_monthly_rollups` with successor IDs and a
derived month range, no direct DELETE) → `regenerate_intervals` (existing
`refresh_pokemon_card_variant_market_price_intervals` RPC) → `rebuild_top_hits`
(calls `rebuild_pokemon_card_market_top_hits_by_edition()` with zero
arguments) → `retire_predecessor_variants` (ledger-based via
`retire_pokemon_card_variant_predecessor`, never touches `card_variants`
directly) → `repair_pilot_projections` (scoped strictly to Fossil/Neo Genesis,
window derived from `pokemon_market_explorer_card_daily_coverage`,
fail-closed if coverage missing, explicit override supported) →
`invalidate_targeted_caches` (single atomic
`invalidate_pokemon_market_explorer_query_cache_scoped(p_set_ids)` call,
no read-then-write generation bump, never calls the blanket invalidation RPC).

This tooling's design matches every RPC contract and behavioral detail
confirmed above (ledger-based retirement, zero physical deletion, zero-arg
top-hits, coverage-derived projection window, scoped monthly rollups, atomic
scoped cache invalidation) as of the two correction passes already applied
(commits `fb77137` and `3447557`).

## Tests

144 passed, 0 failed, across:

```
backend/tests/unit/scripts/test_repair_market_explorer_vintage_predecessor_identities.py (21)
backend/tests/unit/scripts/test_backfill_market_explorer_variant_intervals.py
backend/tests/unit/scripts/test_accept_market_explorer_variant_engine.py
backend/tests/unit/db/test_market_explorer_instrument_eligibility_migration.py
backend/tests/unit/db/services/test_market_explorer_query_planner.py
backend/tests/unit/db/services/test_pokemon_market_explorer_query_service.py
backend/tests/unit/db/services/test_pokemon_sealed_product_market_explorer_query_service.py
```

(123 in the six non-repair suites.) All DB access in tests is mocked/faked —
no live database connection was used in any test. `git diff --check` clean
for this session's own changes. Latest correction commit prior to this
closure pass: `344755753d76b0f4a0b2dd2b24973264b6deab4e`.

## Production writes

Production writes were made by a process external to this session. This
session performed **zero DB writes** — only read-only `SELECT` queries via
the Supabase MCP connector, used solely to independently confirm the
aggregate totals above. As reported, production writes consisted of: 839
predecessor observation-history merges, 839 ledger retirements, scoped
monthly-rollup rebuilds, corrected vintage interval rebuilds, Fossil + Neo
Genesis projection repairs, targeted cache invalidation, `Cards`
`repair_generation` increment 1→2, remaining older/special interval
population, a final card-variant metrics refresh, a final top-hits refresh,
`ANALYZE` on the interval and projection tables, and three Prompt 3 DB
migrations. No newly populated Prompt 3 sets received projection coverage.
No physical `card_variants` rows were deleted (independently confirmed
above).

## Final decision

**GLOBAL_OLDER_SPECIAL_INTERVAL_COHORT_ACCEPTED**

Basis: the load-bearing global invariants (interval-row total, projection-row
total, zero multiple-open rows, merge-ledger population count, and
non-destructive predecessor retirement) were independently re-queried against
the live production database in this session and match the externally
reported figures exactly. Per-era breakdowns, smoke-test detail, and the
derived-market-data-repair narrative are recorded as externally reported and
are internally consistent with the verified aggregates, but were not
independently re-derived per row in this session. Migration SQL
source-control mirroring remains a non-blocking archival follow-up
(`PRODUCTION_MIGRATION_SOURCE_SYNC_PENDING_CHATGPT`).
