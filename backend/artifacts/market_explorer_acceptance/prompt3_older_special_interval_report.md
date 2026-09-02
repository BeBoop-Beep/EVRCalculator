# Prompt 3 — Older/Special Interval Repair: Vintage Predecessor Identities

Status of this document: repo-side implementation report only. This session made
**zero production database writes** and **zero live database connections**. All
quantitative figures below outside the "Tests" section are carried forward from
findings supplied to this session as established facts (an external audit/session's
output) and are marked explicitly as **PLANNING BASELINE / external, not verified by
this session**.

## Vintage identity repair (PLANNING BASELINE — not verified by this session)

839 obsolete predecessor physical variant identities were identified across
Base/WOTC (209), Gym (265), and Neo (365). These are `card_variants` rows with
`edition IS NULL` for a canonical card that also has an explicit-edition
successor row (`first`/`1st-edition` or `unlimited`). 836 map to a 1st-edition
successor; 3 map to unlimited. Affected sets: Fossil, Jungle, Team Rocket, Gym
Challenge, Gym Heroes, Neo Destiny, Neo Discovery, Neo Genesis, Neo Revelation.

Excluded from repair:
- Base and Base Set 2 generic `edition = NULL` variants — still receiving live
  observations through Sep-2, i.e. active instruments, not stale predecessors.
- Base Set Machamp #8 explicit 1st-edition — a legitimate distinct printing,
  not a predecessor of anything.

Cutover evidence: Base/WOTC + Gym predecessors stop by Apr-24; successors begin
Apr-25+, with zero temporal overlap. Neo has 107 predecessor/successor mappings
with a brief Apr-21–Apr-24 overlap treated as migration overlap, not distinct
markets.

The repair design implemented in this session (see `Repair implementation`
below) derives this same classification from **live semantic queries** — same
canonical card, same set, predecessor `edition IS NULL`, successor edition in
{first, unlimited}, cutover-timing evidence — rather than hardcoding the 839
UUIDs. It has not been run against production and its output has not been
diffed against the 839/836/3 figures above.

## Observation merge (PLANNING BASELINE — not verified by this session)

839 predecessor variants hold 53,032 price observations. 52,582 have no
successor collision. 450 collide with an existing successor observation on
`(successor_variant, condition, source, captured_date)`. For all 450, the
predecessor observation has a **later** `created_at` than the conflicting
successor observation, so under the "latest `created_at`, then observation ID"
source-winner rule the predecessor observation wins in every collision. 441/450
collisions are identical `market_price`; the remaining 9 differing-price rows
are all Neo Destiny Apr-21 cases, and the winner rule still applies by
`created_at`, not by price.

## Fossil repair (external/planning figures — not produced or verified by this session)

Scope: 186 → 124 Sep-1 constituents; 23,932 → ~16,244 projection rows in
`pokemon_market_explorer_card_daily_states`; ~7,688 net rows removed. Fossil is
one of only two sets with an already-published pilot daily-state projection,
so it requires row-level re-projection, not just interval/observation repair.

## Neo Genesis repair (external/planning figures — not produced or verified by this session)

Scope: 333 → 222 Sep-1 constituents; 42,829 → ~29,082 projection rows; ~13,747
net rows removed. Same pilot-projection scoping rationale as Fossil.

## EX / E-Card / Base-WOTC / Gym / Neo / POP / NP / Other (external/planning figures)

Per-era expected corrected counts (not verified by this session):
- Base/WOTC: 859 → 650 authority variants; ~86,779 merged interval winner rows.
- Gym: 794 → 529 authority variants; ~68,958 merged rows.
- Neo: 1,093 → 728 authority variants (1 no-NM); ~90,115 merged rows.
- Overall Prompt 3 target: ~51 sets, ~6,571 physical authority variants,
  ~6,359 NM-covered, ~212 no-NM, ~800,129 interval rows.

## Global Prompt 3 reconciliation (external/planning figures)

Corrected global authority after repair: 35,064 → 34,225 physical authority
variants; 34,787 → 33,956 with NM history; 277 → 269 without NM. 7 successor
variants gain legitimate NM history from the predecessor merge that they did
not previously have on their own.

## Storage (external/planning figures — reference-table safety)

53,032 price observations, 4,191 monthly rollups, 2,422 interval rows, and 80
top-hit-by-edition rows are affected by the repair. The 839 predecessor
variants have **zero** references in: `user_card_holdings`,
`simulation_input_cards`, `simulation_card_variant_pull_rates`,
`simulation_card_variant_exclusions`, `graded_card_variants`,
`sealed_product_composition_card_components`,
`pokemon_card_chase_efficiency_rows`,
`pokemon_canonical_card_market_prices_latest`,
`card_variant_external_identities`. This is why the repair design treats
retirement as safe: nothing downstream holds a foreign key into a predecessor
variant that would need remapping.

## Repair implementation (this session)

`backend/scripts/repair_market_explorer_vintage_predecessor_identities.py`
implements the repair as a `--dry-run`/`--commit` mutually-exclusive-required
CLI mirroring `backfill_market_explorer_variant_intervals.py`'s conventions
(service-role client only, structured JSON `Summary` report).

Phases, run in order for every non-rejected, non-already-merged mapping:
1. `classify_predecessor_successor_mappings` — derives mappings from
   `sets`/`cards`/`card_variants` via semantic grouping by `card_id`, applying
   exclusion rules first, then requiring exactly one predecessor and exactly
   one successor per card_id or the pair is rejected (not guessed).
2. `already_merged_predecessor_ids` — reads
   `pokemon_market_explorer_variant_merge_ledger` to skip pairs already
   merged by a prior run (idempotency).
3. `merge_observations` — reads predecessor + successor observations, applies
   `resolve_observation_winners` (the collision/winner rule) for local
   reporting only, and on `--commit` calls
   `merge_pokemon_card_variant_price_observations(p_predecessor_variant_id,
   p_successor_variant_id)` — a real production RPC per migration
   `20260902221622_add_market_explorer_vintage_identity_repair_primitives`
   (reported by external process, pending independent verification — the
   migration SQL itself is not present in this worktree; see
   PRODUCTION_MIGRATION_SOURCE_SYNC_PENDING_CHATGPT below). The RPC applies
   the same source-winner rule server-side; it does not take per-row
   winning/discarded observation id lists.
4. `regenerate_monthly_rollups` — invalidates (deletes, for downstream
   recompute-on-read) monthly rollup rows for touched successor variants.
5. `regenerate_intervals` — calls the *existing*
   `refresh_pokemon_card_variant_market_price_intervals` RPC (same one the
   backfill script uses) for touched successor variants.
6. `rebuild_top_hits` — calls `rebuild_pokemon_card_market_top_hits_by_edition()`
   for touched sets (reported real production RPC, per migration
   `20260902221622_...`).
7. `retire_predecessor_variants` — calls
   `retire_pokemon_card_variant_predecessor(p_predecessor_variant_id,
   p_successor_variant_id, p_merge_reason)` per mapping. Retirement is
   **ledger-based, not physical deletion**: `card_variants` rows for
   predecessors are preserved for history/FK safety; the RPC is responsible
   for marking retirement and writing the
   `pokemon_market_explorer_variant_merge_ledger` row atomically on the DB
   side, so this script no longer performs a separate ledger upsert of its
   own. Market Explorer authority queries are expected to exclude
   ledger-retired predecessors via that ledger, not via row absence.
8. `repair_pilot_projections` — scoped strictly to Fossil and Neo Genesis;
   calls `reproject_pokemon_market_explorer_card_daily_states(p_set_ids,
   p_start_date, p_end_date)` per pilot set (real production RPC per
   migration `20260902221622_...`).
9. `invalidate_targeted_caches` — for the affected pilot set ids, calls the
   single atomic
   `invalidate_pokemon_market_explorer_query_cache_scoped(p_set_ids)` RPC,
   which handles BOTH targeted (scoped, never blanket/global) cache-row
   invalidation AND the `Cards` `repair_generation` bump atomically on the
   DB side. The prior read-then-write `repair_generation` bump pattern has
   been removed — the script now trusts the RPC's atomicity instead of
   reading-then-writing `pokemon_market_explorer_cache_state` itself.

Mapping safeguards: ambiguous predecessor/successor pairs (more than one
plausible candidate on either side) are collected into a `rejections` list
with a reason code (`multiple_predecessor_candidates`,
`multiple_successor_candidates`, `no_successor_candidate`) rather than
resolved by heuristic. Base/Base Set 2 generic variants and Base Set Machamp
#8 1st-edition are excluded via dedicated, independently testable predicate
functions (`is_excluded_generic_set`, `is_excluded_machamp_first_edition`),
not comments.

## Pilot projection repair handling

`repair_pilot_projections` filters mappings to
`_fold(set_name) in {"fossil", "neo genesis"}` before doing anything, so no
other vintage set's `pokemon_market_explorer_card_daily_states` rows are ever
touched, queried for a re-projection count, or passed to the reprojection RPC.
Verified by `test_pilot_projection_scope_limited_to_fossil_and_neo_genesis_only`.

## Cache invalidation handling

The existing `invalidate_pokemon_market_explorer_query_cache` RPC (found in
`backend/db/services/market_explorer_query_planner.py` and its migration
tests) is a **blanket, date-scoped** invalidation across every cached query
for every asset — broader than what this repair needs, and the script never
calls it. Instead, on `--commit`, the script calls the single atomic
`invalidate_pokemon_market_explorer_query_cache_scoped(p_set_ids)` RPC
(reported real production RPC per migration
`20260902221622_add_market_explorer_vintage_identity_repair_primitives`,
external/pending independent verification), scoped to the affected pilot set
IDs only. That RPC is expected to handle both the targeted cache-row
invalidation AND the `Cards` `pokemon_market_explorer_cache_state.repair_generation`
bump atomically on the DB side — the same `repair_generation` field the
query planner reads as a cross-worker generation token for its L1 cache. The
prior read-then-write generation-bump pattern has been removed from this
script entirely; it never reads or writes
`pokemon_market_explorer_cache_state` directly anymore. Verified by
`test_targeted_cache_invalidation_calls_atomic_scoped_rpc` and
`test_cache_invalidation_generation_bump_is_atomic_not_read_then_write`.

## Tests

Ran `python -m pytest` from repo root against the new test file plus the six
requested existing suites (the actual cache-invalidation test file found was
`test_market_explorer_query_cache_migration.py`; no other cache-invalidation
test file exists in the repo):

```
backend/tests/unit/scripts/test_repair_market_explorer_vintage_predecessor_identities.py
backend/tests/unit/scripts/test_backfill_market_explorer_variant_intervals.py
backend/tests/unit/scripts/test_accept_market_explorer_variant_engine.py
backend/tests/unit/db/test_market_explorer_instrument_eligibility_migration.py
backend/tests/unit/db/services/test_market_explorer_query_planner.py
backend/tests/unit/db/services/test_pokemon_market_explorer_query_service.py
backend/tests/unit/db/services/test_pokemon_sealed_market_explorer_query_service.py
backend/tests/unit/db/test_market_explorer_query_cache_migration.py
```

**Result (this alignment pass): 142 passed, 0 failed.** Updated test file:
14/14 passed, covering every case from the original suite (clean
generic→first, generic→unlimited, Base/Base Set 2 exclusion, Machamp #8
exclusion, ambiguous-successor rejection, newer-predecessor-wins collision,
exact-price collision, differing-price collision, idempotent rerun, no
forbidden-table calls, pilot-projection scoping) plus new/replaced coverage
for the RPC-contract alignment:
- `test_retirement_is_ledger_based_not_physical_deletion` — asserts
  `retire_pokemon_card_variant_predecessor` is called with
  `p_predecessor_variant_id`/`p_successor_variant_id`/`p_merge_reason`, that
  the predecessor `card_variants` row is preserved (never deleted), and that
  the merge ledger is populated (simulating the RPC's own atomic ledger
  write, not a separate script-side upsert).
- `test_targeted_cache_invalidation_calls_atomic_scoped_rpc` (replaces
  `test_targeted_cache_invalidation_only_touches_affected_caches`) — asserts
  the scoped `invalidate_pokemon_market_explorer_query_cache_scoped` RPC is
  called with exactly the affected set IDs, and that the blanket
  `invalidate_pokemon_market_explorer_query_cache` RPC is never called.
- `test_cache_invalidation_generation_bump_is_atomic_not_read_then_write`
  (replaces `test_repair_generation_increments_appropriately`) — asserts the
  script itself never reads/writes `pokemon_market_explorer_cache_state`
  (`CACHE_STATE_TABLE not in client.calls`), i.e. the old read-then-write
  generation bump path is gone.

One genuine bug was found and fixed during test-writing: the exclusion
counters (`excluded_generic_count`, `excluded_machamp_count`) computed inside
`classify_predecessor_successor_mappings` were never returned to the caller,
so they never reached the `Summary`. Fixed by widening the function's return
tuple and having `run_repair` assign both counters onto `Summary` explicitly.

`git diff --check` against the two new files (script + test) reported no
whitespace errors. Pre-existing unrelated dirty files in the working tree
(`backend/db/services/chase_accessibility_service.py`,
`backend/desirability/*`, `docs/research/*`, `logs/*.log`) were not touched
and not diff-checked.

## Production writes

**NONE.** This session performed zero production database writes, zero
`--commit` invocations of any script, and zero live Supabase connections. All
tests run against an in-memory fake client.

## Migration source sync

Per external instruction (not independently verified by this session), the
production contract these RPCs align to was installed by migrations
`20260902221622_add_market_explorer_vintage_identity_repair_primitives` and
`20260902221819_add_scoped_variant_monthly_rollup_rebuild`. This session
searched `backend/db/migrations`, `supabase/migrations`, and all worktree
copies in this repo for those files; **neither migration's SQL is present in
this worktree.** No migration file was written or guessed to fill the gap,
per instruction.

**`PRODUCTION_MIGRATION_SOURCE_SYNC_PENDING_CHATGPT`**

## Final decision

**REPO_TOOLING_READY — production repair pending external execution, and
migration SQL source-control sync pending
(`PRODUCTION_MIGRATION_SOURCE_SYNC_PENDING_CHATGPT`).**
