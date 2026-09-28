# Rankings Redesign — DB Bucket 1 Final Closure

Date: 2026-09-28

## Corrective migration

Production migration:
`20260928210657_rankings_db_bucket1_final_continuation_v1.sql`

Mirrored byte-for-byte in:
- `supabase/migrations/`
- `backend/db/migrations/`

## Financial identity decoupling

`refresh_pokemon_financial_rip_history_snapshot_v1(uuid)` now resolves every leaderboard `set_id` only through:

`pokemon_public_rip_leaderboard_rows.set_id -> sets.id -> sets.era_id`

There are zero Collector-table references in the single-snapshot Financial publisher or the full reconciliation wrapper.

A rollback production smoke removed the Collector current pointer before completing a synthetic exact 22-Set snapshot. Financial publication still produced 22 Set rows and 2 Era rows, then the entire smoke transaction rolled back. Production remained at 12 dates / 288 rows.

## Incremental Financial continuation

Normal writes no longer invoke the whole-history loop.

- Snapshot insert/status change -> `refresh_pokemon_financial_rip_history_snapshot_v1(NEW.id)`
- Row batch insert -> transition-table trigger gathers only distinct newly touched `snapshot_id` values and processes those snapshots.
- `refresh_pokemon_financial_rip_history_v1()` remains the explicit maintenance/backfill/reconciliation entry point.

Failure-order smoke:
- incomplete/failed header -> no publication
- rows while not complete -> no publication
- final complete transition -> exactly one publication
- retry -> no duplicate
- rollback -> original production state restored

Accepted semantic lineage remains unchanged:
- Sep17 wrapper -> Sep15
- Sep26 wrapper -> Sep25
- no Sep17/Sep26 fake chart points

Measured production timings:
- previous whole-history trigger-style refresh before correction: ~14.4 ms
- revised single current 22-Set snapshot retry: ~9.0 ms
- explicit full reconciliation after correction: ~25.1 ms; second run inserted 0

The important scaling change is that the daily path is bounded to one touched snapshot instead of growing with historical snapshot count.

## Automatic Card facet continuation

Collector:
- real source pointer: `pokemon_collector_appeal_current(scope='pokemon').model_run_id`
- pointer INSERT/model-run UPDATE trigger invokes `refresh_pokemon_collector_card_ranking_facets_v1(model_run_id)`
- generation creation is idempotent and append-only

Chase:
- real source pointer: canonical row in `pokemon_card_chase_efficiency_latest`
- pointer INSERT/snapshot UPDATE trigger invokes `refresh_pokemon_chase_card_ranking_facets_v1(snapshot_id)`
- only published Chase snapshots can build a generation

Facet generation errors occur in the same transaction as pointer mutation, so a failed build cannot leave a new source pointer active without matching facets.

## Current facet semantics

`pokemon_card_ranking_facets_current_v1` no longer selects by newest `built_at`.

It joins facet generations directly to:
- the current Collector model-run pointer
- the canonical current Chase snapshot pointer

A real 2026-09-27 Chase historical generation was built after the 2026-09-28 current generation. Despite its later facet-build timestamp, the current view remained bound to the 2026-09-28 Chase pointer.

## Facet performance

Measured production:
- Collector full generation rebuild, rollback benchmark: ~312.3 ms for 207 facets
- Chase real historical generation build: ~84.0 ms for 38 facets
- same-authority Collector retry: ~4.3 ms
- same-authority Chase retry: ~3.1 ms
- Collector current Set facet lookup: ~0.264 ms / 155 rows
- Chase current Set facet lookup: ~0.167 ms / 22 rows

Interactive reads never scan the 18,293-row Collector universe.

## Preserved current data

Financial:
- 12 exact dates
- 288 rows
- 264 Set
- 24 Era

Collector current facets:
- 16 Eras
- 155 Sets
- 33 rarities
- 3 subject types

Chase current facets:
- 2 Eras
- 22 Sets
- 14 rarities

Collector V7 scoring/ranks and the research-only calibration shadow were not changed.

## Validation

- 12/12 source/migration contract assertions passed.
- 6/6 Financial rollback safety assertions passed.
- 7/7 facet failure/pointer safety assertions passed.
- Explicit full Financial reconciliation remained idempotent: 0 new publications on retry.
- Security advisors were rerun after migration; no new Bucket-1 security finding references the new tables/views/functions.
- Performance advisors only mention new indexes as currently unused, expected immediately after creation; no new structural performance warning was introduced.

New executable contract test:
`backend/tests/unit/db/test_rankings_db_bucket1_final_continuation_sql.py`
