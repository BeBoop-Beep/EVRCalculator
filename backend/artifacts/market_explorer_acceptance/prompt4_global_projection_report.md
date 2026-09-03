# Prompt 4 — Global Daily Serving Projection: Repo-Side Tooling

## A. Branch / HEAD
Branch `fix/public-rankings-entitlement-regression-2`. Original repo-tooling pass was authored
on top of HEAD `cf128ad4`. This addendum (production cache-acceptance pass) was authored on top
of HEAD `e834ac0a` (docs: finalize Prompt 4 repo-readiness report content), before this
session's own commit — see section R for what this session actually wrote to production.

## B. Starting projection state (external / planning baseline, given, not re-derived)
Coverage: 50 sets, 1,886,684 rows, date range 2026-04-07..2026-09-01. 115 sets unprojected.
Approved dates: 143, range 2026-04-07..2026-09-02 (`pokemon_market_date_quality`,
status READY/LEGACY_VERIFIED).

## C. Corrected global authority (external baseline, given, not re-derived)
165 sets, 34,225 physical instruments, 33,956 with NM history, 269 without. 839 retired vintage
predecessor identities already excluded via `pokemon_market_explorer_variant_merge_ledger`.

## D. Coverage metadata repair (tooling design)
`backend/scripts/publish_market_explorer_daily_projection.py::activate_or_repair_coverage`
never trusts a prior `pokemon_market_explorer_card_daily_coverage` row. For every set touched
(new, appended, or `up_to_date`) it recomputes `first_market_date`/`computed_through` from
`MIN`/`MAX(market_date)` and `row_count` from `COUNT(*)` against the actual
`pokemon_market_explorer_card_daily_states` rows for that `set_id`, then upserts. This directly
targets the known 48/50 stale-`row_count` defect (sums to 1,873,043 vs actual 1,886,684) and is
exercised by `test_coverage_row_count_derived_from_actual_table_not_trusted_input`, which
simulates that exact defect shape (correct date bounds, stale understated `row_count`) and
asserts the repaired value matches the real table contents.

## E–J. Production projection state — externally reported, spot-checked this session
Sections E–J described PENDING publication work in the repo-tooling pass. That production
publication has since been completed by a separate external process (per this session's task
brief): 165/165 sets covered, 34,225 physical instruments (33,956 with NM history, 269
without), 4,597,555 total projection rows, coverage `computed_through` = 2026-09-02 for all
sets, zero coverage mismatches, zero retired-predecessor rows. This session did **not**
re-derive that baseline from scratch, but independently confirmed a materially equivalent
picture live: `pokemon_market_explorer_card_daily_coverage` join to `sets`/`eras` shows all 17
eras with nonzero coverage (Base/WOTC 5, Black and White 14, Diamond and Pearl 7, E-Card 3, EX
16, Gym 2, HGSS 6, Mega Evolution 6, Neo 4, NP 1, Other 13, Platinum 4, POP 9, Scarlet and
Violet 16, Sun and Moon 18, Sword and Shield 24, XY 17 = 165 sets), and confirmed exact
projection/interval parity for two representative eras on 2026-09-02 (section K/I below).

## K. Sampled interval oracle/parity — RUN LIVE this session (application-path, not raw SQL)
`accept_market_explorer_global_daily_projection.py` was inspected but not run at true global
scope this session — see the Part B/global blocker in section M. Instead, parity was verified
directly through `load_filtered_daily_cohort_rows` (the exact function `run_market_explorer_query`
calls) against both `get_pokemon_market_explorer_filtered_cohort` (interval oracle) and
`get_pokemon_market_explorer_filtered_cohort_daily` (projection) for 2026-09-02, using
`resolve_scope_set_ids` (the real scope resolver) rather than a raw `sets` table filter:
- **Sword and Shield** (24 tracked sets): interval `{constituentCount: 5401, basketValue:
  27389.59}` == daily projection `{constituentCount: 5401, basketValue: 27389.59}`. Exact match.
- **Base/WOTC** (5 tracked sets): interval `{constituentCount: 650, basketValue: 18013.43}` ==
  daily projection `{constituentCount: 650, basketValue: 18013.43}`. Exact match.
Both scopes' maintained-cache builds (section M) also self-validated: each build's
`novel_builder` result reported `executionEngine`/cache source `daily_projection` (or
`cache_incremental_daily_projection` for an append), and each build's resulting
`constituent_count` in `pokemon_market_explorer_query_cache` matches the interval-oracle
`constituentCount` above exactly (SWSH 5401, Base/WOTC 650).

## L. Global query smoke tests (planner-path verification) — RUN LIVE, genuine blocker found
`daily_projection_covers`/`run_market_explorer_query`'s `diagnostics.executionEngine` is the
correct, existing detector and was used as specified — but the **global-scope (all 165
authority sets at once) RPC call itself times out** in production, at both the interval oracle
(`get_pokemon_market_explorer_filtered_cohort`) and the daily-projection RPC
(`get_pokemon_market_explorer_filtered_cohort_daily`), even for a single day
(`2026-09-02`..`2026-09-02`) with no filters: `postgrest.exceptions.APIError: {'code': '57014',
message: 'canceling statement due to statement timeout'}`, reproduced 3 times directly against
production, ~8.0s to fail (i.e. hitting the default statement_timeout, not a slow-but-completing
query). Per-set and per-era scopes (single set, single era, and the existing 2-era SV+Mega
combo) all complete quickly (60ms–200ms for narrow windows; 1–15s cold-build for era-wide
history). **This means the real application code path cannot currently compute Global All Raw
Cards / Global Top 10 / Global rareHolo / Global Premium at all** — not merely slowly — via
either RPC, at the current production statement-timeout setting. This is a genuine, reproducible
blocker for Part A and Part B of this session's task, not a cosmetic issue, and is NOT something
this session attempted to route around with raw SQL. It also means the task brief's stated
baseline ("Global Sep-2 parity already confirmed exact: All Raw 33,956/$637,086.49 ...") was
almost certainly computed by some other mechanism (e.g. a direct aggregate query, not this RPC
pair) — this session cannot reproduce that comparison through the live application RPC path as
it stands today.

## M. Global/per-era cache builds — RUN LIVE this session
**Global (Part B): BLOCKED.** Both `run_market_explorer_query`-driven builds for Global All Raw
Cards and Global Top 10 fail before any cache row can be written, because the underlying RPC
call raises a statement timeout at 165-set scope (section L). No Global cache was built or
promoted this session. This is the one Part that did not check out.

**Per-era (Part C): COMPLETE.** Built/advanced via
`backend/scripts/build_market_explorer_maintained_cache.py` (new this session; same
planner/persistent-cache/`run_market_explorer_query` path as the existing
`accept_market_explorer_cache_first_era.py`, generalized to accept `--era-id`/`--set-id`
combinations and a `--label`, with cache-kind promotion to `maintained` after a ready build —
no raw SQL payload writes). All 17 tracked eras plus the existing SV+Mega combined scope now
have a `maintained`, `ready`, `computed_through=2026-09-02` All Raw cache:

| Scope | Fingerprint (first 8) | Constituents | Prior state | Action |
|---|---|---|---|---|
| Sword and Shield (All Raw) | f46f6e2c | 5401 | maintained, through 09-01 | advanced (incremental append) |
| Sword and Shield (Top 10) | 5fd36e28 | 10 | maintained, through 09-01 | advanced |
| Scarlet and Violet (All Raw) | 66bf6f4d | 6047 | maintained, through 09-01 | advanced |
| Mega Evolution (All Raw) | 0eead8c4 | 1533 | maintained, through 09-01 | advanced |
| SV+Mega combined (All Raw) | 27cd5cd9 | 7580 | maintained, through 09-01 | advanced |
| Sun and Moon (All Raw) | a2a5f8cc | 4845 | none | built new |
| XY (All Raw) | d6fc3717 | 3252 | none | built new |
| EX (All Raw) | 4f08de10 | 3232 | none | built new (interval_fallback for pre-2026-04-11 history; see below) |
| Black and White (All Raw) | fb632535 | 2575 | none | built new |
| Diamond and Pearl (All Raw) | 967a0750 | 1644 | none | built new |
| HeartGold and SoulSilver (All Raw) | ffce396d | 986 | none | built new |
| Platinum (All Raw) | 8c1fb334 | 968 | none | built new |
| E-Card (All Raw) | 0d56e4b1 | 892 | none | built new |
| Neo (All Raw) | c9004388 | 727 | none | built new |
| Base/WOTC (All Raw) | 71bd1296 | 650 | none | built new |
| Gym (All Raw) | cdd03b04 | 529 | none | built new |
| Other (All Raw) | ee778c5a | 385 | none | built new |
| POP (All Raw) | 99ba789f | 212 | none | built new |
| NP (All Raw) | 492c93bf | 78 | none | built new |

19 `maintained`/`ready`/`computed_through=2026-09-02` rows total (18 distinct scopes, one with
both an All Raw and a Top 10 case). EX's cold build used `interval_fallback` (167.5s) rather
than `daily_projection` because its real card-price history predates the projection's staggered
`first_market_date` of 2026-04-11 for its sets — expected "staggered start" behavior per
`project_set_rebuild_staleness_fix`/`project_top_chase_stale_window_row` memory notes, not a
projection defect (the same-day 2026-09-02 slice for EX would resolve via projection; the
`start_date=1999-01-01` sweep this script uses intentionally exercises the full-history interval
fallback path too). All other new-era cold builds used `daily_projection` directly, 1.9s–14.8s
each (Sun and Moon was the slowest at 27.6s, XY next at 14.8s, reflecting larger per-era set
counts).

## N. Cache summary/detail behavior — VERIFIED LIVE
Called `MarketExplorerQueryPlanner.execute(..., summary=True)` directly for the Sword and Shield
All Raw scope (already `ready`/`persistent_cache` sourced): the returned payload's keys are
`asOf, chaseModelNote, diagnostics, displayLabel, familyChanges, historyStartDate, indexValue,
metadata, movementWindows, queryFingerprint, queryKey, reconciliation, scope, serviceVersion,
spec, taxonomyVersion, trackedValue, trackedValueChanges, trackedValueHistory, trend` — no
`currentConstituents` or `membershipByDate` key present, confirming the existing slimming
contract in `MarketExplorerQueryPlanner.execute`'s `response()` closure. Constituent detail was
independently verified against `pokemon_market_explorer_query_cache_constituents` for the SWSH
fingerprint: `SELECT count(*), count(distinct card_variant_id)` returns `5401, 5401` (no
duplicates), rows are ordered/paged by a stable `rank` column (rank 1..5401, first 5 ranks
verified non-null and sequential), and this table has no `currentConstituents`/
`membershipByDate` columns — normalized detail, not a duplicated summary blob. This check could
not be repeated for Global (blocked, section L/M), so it is verified for the per-era case only
this session; the mechanism itself is scope-agnostic (same table, same planner code path).

## O. Performance — RUN LIVE (per-era; Global blocked)
Captured via `build_market_explorer_maintained_cache.py`'s L2 (fresh client/planner instance
per sample, 2 samples) and L1 (same planner instance reused, 2 samples) timing for each of the
19 builds above; sources for every L2/L1 sample after the cold build were `persistent_cache`
(L2) and `memory_cache` (L1) in all cases sampled, i.e. warm serving hit cache, not an
interactive rebuild. Representative timings (SWSH All Raw, largest scope built): cold build
6003ms (`cache_incremental_daily_projection`, Sep-1→Sep-2 append), L2 sub-second, L1
sub-millisecond, matching the shape of the pre-existing SV+Mega combined precedent
(`cache_recover_combined.json`: cold 35788ms, L2 median 756ms/p95 866ms, L1 median 0.05ms/p95
2.4ms, both `persistent_cache`/`memory_cache` sourced). Full raw sample data for every scope is
in `backend/artifacts/market_explorer_acceptance/prompt5_build_*.json` (18 files, one per
scope/label, written this session). Global L2/L1 timing could not be captured (section L/M
blocker).

## P. Storage — not separately measured
No dedicated storage/size query was run this session; `payloadBytes` per scope is recorded in
each `prompt5_build_*.json` artifact (summary=False, i.e. full payload size including
constituents/membership, which is what an un-slimmed cold build actually persists).

## Q. Tests (this session's actual results)
166 passed, 0 failed, run with `python -m pytest -p no:randomly` (test order was flaky for the
new publish-script suite under the repo's default `pytest-randomly` ordering — a shared
`Query.execute` monkeypatch reentrancy artifact in the mock harness, not a bug in the script
itself; deterministic order is 11/11 and 3/3 clean). Suites run:
- `test_publish_market_explorer_daily_projection.py` — 11 passed (new)
- `test_accept_market_explorer_global_daily_projection.py` — 3 passed (new)
- `test_backfill_market_explorer_variant_intervals.py` — passed
- `test_accept_market_explorer_variant_engine.py` — passed
- `test_repair_market_explorer_vintage_predecessor_identities.py` — passed
- `test_market_explorer_query_planner.py` — passed
- `test_pokemon_market_explorer_query_service.py` — passed
- `test_pokemon_sealed_market_explorer_query_service.py` — passed
- `test_market_explorer_query_cache_migration.py` — passed
- `test_market_explorer_instrument_eligibility_migration.py` — passed
- `test_market_explorer_staggered_start_coverage_migration.py` — passed (the staggered-start
  coverage test file referenced in the task)

New-script coverage explicitly includes: new-set activation reconciles-then-activates,
exact interval-to-state parity, coverage NOT activated on reconciliation failure, row_count
derived from actual table (not trusted stale input), staggered start using the set's own
`first_market_date`, forward one-day append for an already-covered set, idempotent rerun with
no duplicate/changed state, no duplicate PK rows, retired-predecessor exclusion, no-NM
exclusion without fabrication, and approved-date filtering by status/range.

`git diff --check` on this session's own files: clean (no output).

Re-run this session (deterministic order, `-p no:randomly`): both suites pass 11/11 and 3/3
(14/14 combined). The reported `pytest-randomly` order-flakiness (mock-harness monkeypatch
reentrancy) was not investigated further for a fix — reproducing and safely patching a
randomized-order-only mock reentrancy issue was judged not worth the time in this
production-acceptance pass per the task's own "don't spend excessive time here" guidance.
Documented as test-harness debt, not a product bug; deterministic-order evidence stands.

## R. Production writes — THIS SESSION (cache-publication only)
This session made real production writes, exclusively through the application's own
builder/lease/publish path (`MarketExplorerQueryPlanner` + `PersistentMarketExplorerCache` +
`run_market_explorer_query`, via the new `backend/scripts/build_market_explorer_maintained_cache.py`)
against `pokemon_market_explorer_query_cache` / `pokemon_market_explorer_query_cache_constituents`.
No raw SQL cache payload writes were made, and nothing in
`pokemon_card_variant_market_price_intervals`, `pokemon_market_explorer_card_daily_states`,
`pokemon_market_explorer_card_daily_coverage`, or vintage identity/merge-ledger tables was
touched. See section M for the full list of 19 maintained/ready cache rows this session
built-new or advanced to `computed_through=2026-09-02`. The interval/projection population
itself (165/165 coverage, 4,597,555 rows) was NOT done by this session — that was already
complete before this session started, per the task's external baseline.

## S. Final decision
**NOT ACCEPTED AS GLOBAL_CARD_MARKET_AUTHORITY_ACCEPTED.** Per-era planner-path verification,
per-era cache builds, cache slimming, per-era constituent-detail paging, and per-era sample
parity all check out cleanly against live production (sections K, M, N, O). However, Part A/B —
the actual Global All Raw / Global Top 10 / Global rareHolo / Global Premium queries — cannot
currently execute at all through the real application RPC path: both
`get_pokemon_market_explorer_filtered_cohort` and `get_pokemon_market_explorer_filtered_cohort_daily`
hit the production statement timeout at true 165-set global scope, even for a single date with
no filters. This is a genuine, reproduced blocker, not a cosmetic one, so the final decision is
**GLOBAL_CARD_MARKET_AUTHORITY_BLOCKED_ON_GLOBAL_SCOPE_RPC_TIMEOUT**. Per-era authority (18
scopes across all 17 tracked eras) is otherwise in good shape and does not need to be redone.

## T. Retest addendum (this session) — HEAD `b52ec630`, after ChatGPT's reported DB-layer fix

Branch `fix/public-rankings-entitlement-regression-2`, HEAD `b52ec6304f06e4d7698435f01aa7bc9eb1704c4d`
at the start of this retest (prior report authored at `1283a739`). Task brief: independently
verify a reported production fix — migration `20260903192911_add_market_explorer_current_metadata_projection`
(new table `pokemon_market_explorer_card_current_metadata`, 34,225 rows / 165 sets / 0 retired
predecessors / 0 catalog-only rows), externally reported to take the global daily-serving RPC
from ~29.2s (timeout) to ~0.97s for one date, ~2.5s for a 3-day chunk.

**B. Global RPC retest timings — split result: the DB-layer fix is real, but the application
code path does not reach it for Global.**

1. Calling `get_pokemon_market_explorer_filtered_cohort_daily` directly with the correct
   165-set Market Explorer authority (read from `pokemon_market_explorer_card_daily_coverage`,
   165 distinct `set_id` rows, confirmed live) succeeded every time, no 57014, 3 repeats each:
   - All Raw, 1 day (2026-09-02): 1928ms / 1835ms / 1741ms — `constituent_count=33956`,
     `basket_value=637086.49` (exact match to the task's stated Sep-2 global baseline).
   - All Raw, 3-day chunk (2026-08-31..2026-09-02): 2640ms / 2632ms / 2229ms —
     `constituent_count=33953`, `basket_value=634320.18`.
   - Top 10, 1 day: 752ms / 277ms / 263ms — `constituent_count=10`, `basket_value=35332.31`.
   - rareHolo, 1 day: 883ms / 761ms / 844ms — `constituent_count=3055`.
   - Premium, 1 day: 206ms / 500ms / 210ms — `constituent_count=1344`.
   These are **this session's own measurements**, not the externally reported ~29.2s→0.97s /
   ~2.5s figures — they are directionally consistent (sub-3s, no timeout) but not identical
   numbers; both point to the same real fix. Raw output:
   `backend/artifacts/market_explorer_acceptance/prompt4b_global_daily_rpc_165authority.json`.
2. Calling the same RPC (and the real application entry points `run_market_explorer_query` /
   `build_market_explorer_maintained_cache.py`, i.e. the actual authorized builder path) with
   the scope Global queries **actually resolve to in production** — `resolve_tracked_set_ids`,
   which every live caller including `resolve_scope_set_ids`/`run_market_explorer_query` uses —
   returns **169 sets, not 165**. The 4 extra sets (`EX Trainer Kit Latios`, `EX Trainer Kit
   Latias`, `EX Trainer Kit 2 Plusle`, `EX Trainer Kit 2 Minun`) have real price history in
   `pokemon_set_value_daily_history_coverage` but were never onboarded into the Market Explorer
   projection/coverage tables (`pokemon_market_explorer_card_daily_coverage` has exactly 165
   rows; confirmed 0 overlap with these 4 ids). Two consequences, both reproduced live:
   - `get_pokemon_market_explorer_filtered_cohort_daily` called with the real 169-set scope
     returns instantly (62ms) but with **0 rows** — the new candidate function does not return
     partial results when any requested set lacks a current-metadata/coverage row, it returns
     nothing.
   - `daily_projection_covers(client, scope_set_ids=169 sets, ...)` therefore evaluates
     **False** for the real Global scope (4 of 169 requested sets have no
     `pokemon_market_explorer_card_daily_coverage` row at all), so
     `run_market_explorer_query`'s engine selection falls to `interval_fallback` for any
     multi-day range, and to `interval_current` (also `get_pokemon_market_explorer_filtered_cohort`,
     the un-fixed interval oracle) for a same-day range regardless of coverage — the
     `current_only` branch in `run_market_explorer_query` never even checks
     `daily_projection_covers` before choosing the interval RPC.
   - Both of those call `get_pokemon_market_explorer_filtered_cohort` (the interval oracle),
     which was **not** touched by migration `20260903192911` and still performs a full scan of
     `pokemon_card_variant_market_price_intervals` (4.5M+ rows) at 169-set scope. Reproduced
     live, 3/3, through the actual application code:
     - `run_market_explorer_query(mode="all", start=end=2026-09-02)` (Global All Raw, 1 day):
       **FAIL, 8890ms, 57014 statement timeout.**
     - `run_market_explorer_query(mode="all", start=2026-08-31, end=2026-09-02)` (Global All
       Raw, 3-day): **FAIL, 8889ms, 57014 statement timeout.**
     - `run_market_explorer_query(mode="chase", top_n=10, start=end=2026-09-02)` (Global Top
       10, 1 day): **FAIL, 8689ms, 57014 statement timeout.**
   - `backend/scripts/build_market_explorer_maintained_cache.py --mode all --label
     global_allraw_retest` (the actual authorized cache builder, `START="1999-01-01"` through
     today, i.e. the exact code path Part 2/3 of this task requires) reproduces the identical
     57014 traceback from inside `run_market_explorer_query` → `load_filtered_daily_cohort_rows`
     → `client.rpc(get_pokemon_market_explorer_filtered_cohort, ...)`.

**Conclusion for B:** the DB-layer fix in migration `20260903192911` is genuine and independently
verified — the daily RPC itself is fast and correct at the correct 165-set scope. But it is not
reachable from the real Global query/cache-build code path today, because that path's tracked-set
resolver (`resolve_tracked_set_ids`) includes 4 sets outside the Market Explorer authority that
were never given coverage rows, which (a) makes the new daily candidate function return an empty
result for the true 169-set scope, and (b) makes `daily_projection_covers` fail closed, routing
every Global query — including same-day queries, which never even reach the coverage check —
back onto the un-fixed, still-timing-out interval oracle RPC. This is a different, more precise
failure mode than the prior report's blanket "both RPCs time out at global scope" — the daily RPC
does not time out at the correct scope; the application never calls it with the correct scope.

**C/D. Global All Raw / Global Top 10 cache builds: BLOCKED, same as before, for the reason
above.** No Global cache was built or promoted this session — `build_market_explorer_maintained_cache.py`
raised the 57014 error before any `pokemon_market_explorer_query_cache` row could be written, so
there is nothing to report for cache-kind promotion, `computed_through`, or `constituent_count`
beyond the direct-RPC number already confirmed in B (`33956`, matching the task's required value
for when this becomes reachable).

**E/F/G/H. Summary slimming, detail-row paging, warm L2/L1 timings: NOT RUN for Global** — all
of these require a `ready` Global cache row from step C/D, which does not exist. Not fabricated.

**I. Existing maintained cache health — CONFIRMED, still healthy, not rebuilt.** Queried
`pokemon_market_explorer_query_cache` directly for `cache_kind='maintained'`: all 19 rows from
the prior pass (18 distinct scopes, SWSH All Raw + Top 10) are still `status=ready`,
`computed_through=2026-09-02`, with unchanged `constituent_count` values (5401/10/6047/1533/7580/
4845/3252/3232/2575/1644/986/968/892/727/650/529/385/212/78). No rebuild performed, per scope.

**J. Tests — PASSED.** `python -m pytest -p no:randomly
backend/tests/unit/scripts/test_publish_market_explorer_daily_projection.py
backend/tests/unit/scripts/test_accept_market_explorer_global_daily_projection.py
backend/tests/unit/db/services/test_market_explorer_query_planner.py
backend/tests/unit/db/services/test_pokemon_market_explorer_query_service.py
backend/tests/unit/db/test_market_explorer_query_cache_migration.py` → **85 passed, 0 failed**
(deterministic order). The pytest-randomly order-flakiness noted in the prior pass was not
re-investigated, per the task's explicit instruction not to reopen that debt.

**K. Report commit — this addendum only** (section T + this open-item update), same file.

**L. Production cache writes — NONE this session.** No `pokemon_market_explorer_query_cache` /
`..._constituents` rows were written or modified. The only production reads performed were the
RPC calls and table reads above (all read-only) and the pre-existing maintained-cache health
query (a plain `select`).

**M. Migration source-sync status — worse than "pending," now confirmed genuinely missing from
this worktree.** `list_migrations` against the live project confirms
`20260903192911_add_market_explorer_current_metadata_projection` is applied (last entry in the
migration list), and the SQL body of `get_pokemon_market_explorer_filtered_cohort_daily` was
read live via `pg_get_functiondef` — it now delegates to
`get_pokemon_market_explorer_filtered_cohort_daily_candidate` (unchanged wrapper from the prior
Prompt-4 pass; the new metadata table is consumed inside that candidate function, not inspected
line-by-line this session). No corresponding `.sql` file for `20260903192911`, nor the three
previously-missing Prompt 3 migrations, exist anywhere in this worktree
(`find . -iname "*20260903192911*"` and `*market_explorer_current_metadata*`: no matches). Status
remains **PRODUCTION_MIGRATION_SOURCE_SYNC_PENDING_CHATGPT**, now with a fourth migration added
to the missing list.

**N. Final decision — NOT ACCEPTED. GLOBAL_CARD_MARKET_AUTHORITY_BLOCKED_ON_GLOBAL_SCOPE_RPC_TIMEOUT
still applies, root cause narrowed.** The externally reported DB-layer fix is real and
independently verified: the daily-projection RPC itself is fast (sub-3s, 3/3, no 57014) and
returns the exact expected Sep-2 global numbers (33956/$637,086.49) when called with the correct
165-set Market Explorer authority. But the actual application/cache-build code path
(`run_market_explorer_query`, and therefore every authorized builder that calls it) resolves
Global to 169 tracked sets, not 165, because `resolve_tracked_set_ids` reads from
`pokemon_set_value_daily_history_coverage` (169 sets with general price history) rather than the
165-set Market Explorer coverage authority; the 4 extra EX Trainer Kit sets have no
`pokemon_market_explorer_card_daily_coverage` row, which makes `daily_projection_covers` fail
closed for Global and routes every Global query — same-day queries included, since the
`current_only` branch bypasses the coverage check entirely — onto the un-fixed interval oracle
RPC, which still times out at 8s exactly as in the prior pass. Reproduced 3/3 through
`run_market_explorer_query` directly and once through the actual authorized builder script
(`build_market_explorer_maintained_cache.py`). This is an application-layer set-resolution gap,
not a database performance problem, and is outside this session's authorized scope to fix (no
code changes were made; Prompt 5 was not begun). Per-era authority (19 maintained/ready rows,
section M of the original report) remains healthy and unaffected — confirmed again this session,
not rebuilt.

## Open item
Three Prompt 3 production migrations were searched for in this worktree and NOT found:
`20260902221622_add_market_explorer_vintage_identity_repair_primitives.sql`,
`20260902221819_add_scoped_variant_monthly_rollup_rebuild.sql`,
`20260903034704_harden_market_explorer_vintage_top_hits_rebuild.sql`.
Status: **PRODUCTION_MIGRATION_SOURCE_SYNC_PENDING_CHATGPT** (non-blocking; no SQL was
guessed/invented to fill this gap). Re-confirmed not present in this worktree this session.

## Next recommendation (superseded — see section U)
Before Global scopes can be built or verified, someone with database access needs to either (a)
raise the PostgREST/Postgres `statement_timeout` for these two RPCs specifically (or a service-
role-scoped override) high enough to let a true 165-set, single-date cohort query complete, or
(b) add a genuinely incremental/batched global aggregation path (e.g. union of the now-existing
17 per-era maintained caches, if that composition is mathematically valid for the Global
scope's card-level ranking/basket semantics) so Global never needs one unbounded 165-set RPC
call. Once either exists, re-run this session's Part A/B/D/E/F/G/I checks against the Global
scope specifically — the per-era work does not need to be repeated.

## U. Second retest addendum (this session) — application-layer fix + Global cache build, ACCEPTED

Branch `fix/public-rankings-entitlement-regression-2`. This pass fixed the two precise root
causes identified in section T (169-vs-165 set resolution, and the same-day projection-routing
bypass) and re-ran the Global acceptance end to end. Note: two earlier attempts at this exact
task within this session stalled waiting on background monitors that never fired (a subagent
limitation, not a product issue) after correctly implementing both code fixes but before
finishing tests/retest/commit — this addendum was completed directly rather than re-delegated,
after independently confirming the in-flight code changes were correct.

### Files changed
- `backend/db/services/pokemon_market_explorer_query_service.py` — two fixes:
  1. `resolve_tracked_set_ids()`: now intersects the history-tracked set list
     (`pokemon_set_value_daily_history_coverage`, `has_history=true`) with the non-catalog-only
     set universe (`sets.catalog_only=false`), loaded separately and intersected in Python
     (avoids an expensive UUID IN query). This excludes the 4 catalog-only EX Trainer Kit child
     sets (Latias/Latios/2 Minun/2 Plusle) from Global scope resolution while preserving the
     history-tracking requirement for every other set — a genuinely uncovered-but-tracked set
     remains resolvable, per the "intersection, not source-switch" contract. Docstring updated
     to describe the correct 165-set (not 167/169-set) universe.
  2. `run_market_explorer_query()`: `projection_covered` is no longer gated by `not current_only`
     — it is now `daily_projection_covers(client, scope_set_ids, start_date=effective_start,
     end_date=effective_end)` unconditionally, with the engine-selection order changed to
     `daily_projection` (if covered) → `interval_current` (if same-day, uncovered) →
     `interval_fallback` (otherwise). A fully-covered same-day query now correctly uses the
     daily projection instead of always falling to `interval_current`.
- `backend/tests/unit/db/services/test_pokemon_market_explorer_query_service.py` — new tests
  covering: `resolve_tracked_set_ids` returns 165 given 169 history-tracked sets with 4
  `catalog_only=true`; a normal non-catalog tracked set remains included; a `catalog_only=false`
  set with no tracked history stays excluded (intersection, not "all catalog sets"); fully-covered
  same-day query resolves `daily_projection` with `diagnostics.executionEngine="daily_projection"`;
  uncovered same-day query preserves `interval_current`; fully-covered multi-day remains
  `daily_projection`; uncovered multi-day remains `interval_fallback`; staggered-start behavior
  unchanged.
- `backend/tests/unit/scripts/test_accept_market_explorer_global_daily_projection.py` — minor
  update for consistency with the corrected engine-selection contract.
- `backend/scripts/build_market_explorer_global_maintained_caches.py`,
  `build_market_explorer_global_top10_cache.py`,
  `sample_market_explorer_global_allraw_cache.py`,
  `verify_market_explorer_global_allraw_detail.py` — new, small single-purpose driver scripts for
  this retest, all built strictly on `MarketExplorerQueryPlanner` /
  `PersistentMarketExplorerCache` / `run_market_explorer_query` (no raw SQL cache payload
  writes); kept as reusable maintenance tooling rather than deleted as scratch.
- `backend/artifacts/market_explorer_acceptance/prompt4_global_cache_build_evidence.json` — raw
  cold/L2/L1 timing evidence captured mid-session from a fully successful build_one() run for
  both Global scopes (see Global timings below).

### C. Tracked-set resolution result
Verified live: `resolve_tracked_set_ids(production_client)` now returns **165** set IDs,
matching `pokemon_market_explorer_card_daily_coverage`'s 165 rows exactly, with the 4 EX Trainer
Kit sets confirmed absent from the result.

### D. Same-day projection-routing fix
Verified via the new unit tests (mocked) and live: a same-day Global query
(`2026-09-02`..`2026-09-02`) with full coverage now resolves through `daily_projection`, not
`interval_current`.

### E. Global application-path timings (production, via the real `run_market_explorer_query` /
builder path — not a direct RPC call)
- **Global All Raw, cold build**: succeeded via `daily_projection`. One fully-instrumented run
  captured mid-session (before this addendum's final cleanup pass) recorded `coldMs=132,938ms`
  (~133s; a one-time, offline-acceptable full 143-day historical materialization sweep,
  `coldSource=daily_projection`) — see `prompt4_global_cache_build_evidence.json`. A later
  confirmatory run against the already-`ready` row read from `persistent_cache` in 2865ms
  (cache already warm from the prior successful build).
- **Global Top 10, cold build**: `coldMs=49,250ms` (~49s, `coldSource=daily_projection`) in the
  same captured run; a later confirmatory run read `persistent_cache` in 209ms.
- No 57014 timeout occurred in any attempt once both fixes were applied and the correct 165-set
  scope was used throughout.

### F. Global All Raw cache — READY
`pokemon_market_explorer_query_cache` row for the Global All Raw fingerprint
(`66426743...`): `status=ready`, `cache_kind=maintained`, `computed_through=2026-09-02`,
`constituent_count=33956`, `eligible_universe_count=33956` — all required values met exactly.

### G. Global Top 10 cache — READY
Fingerprint `133fe00a...`: `status=ready`, `cache_kind=maintained`,
`computed_through=2026-09-02`, `constituent_count=10`, `eligible_universe_count=33956` — all
required values met exactly.

### H. Detail/slimming results
Global All Raw summary payload (via `MarketExplorerQueryPlanner.execute(..., summary=True)`)
confirmed: `currentConstituents` absent, `membershipByDate` absent. Payload keys: `asOf,
chaseModelNote, diagnostics, displayLabel, familyChanges, historyStartDate, indexValue,
metadata, movementWindows, queryFingerprint, queryKey, reconciliation, scope, serviceVersion,
spec, taxonomyVersion, trackedValue, trackedValueChanges, trackedValueHistory, trend` — same
slimming contract as the per-era case, confirmed for Global specifically this time.

Normalized detail, fully paginated (not the PostgREST 1000-row default cap):
**33,956 total rows, 33,956 unique `card_variant_id` (0 duplicates), ranks sequential 1..33956,
0 retired-predecessor IDs present.** First page (ranks 1–5) and a later page (ranks 1001–1005)
both returned valid, correctly ordered rows.

### I. L2/L1 timings
| Cache | L2 samples (ms) | L2 source | L1 samples (ms) | L1 source |
|---|---|---|---|---|
| Global All Raw (full run) | 5019, 1800 | persistent_cache, persistent_cache | 13.0, 0.10 | memory_cache, memory_cache |
| Global All Raw (confirmatory re-sample) | 254, 223 | persistent_cache, persistent_cache | 0.06, 0.02 | memory_cache, memory_cache |
| Global Top 10 (full run) | 158, 235 | persistent_cache, persistent_cache | 0.07, 0.02 | memory_cache, memory_cache |
| Global Top 10 (confirmatory re-sample) | 160, 160 | persistent_cache, persistent_cache | — | — |

Warm serving requirement met: every L2/L1 sample after the cold build sourced from
`persistent_cache`/`memory_cache`, never a live rebuild. The one-time cold build (49s–133s) is
the offline/maintained-path cost, not the interactive contract — consistent with the task's
explicit instruction not to judge cold builds against the 8s interactive envelope.

### J. Per-era cache health — CONFIRMED, unchanged, not rebuilt
Queried `pokemon_market_explorer_query_cache` for `cache_kind='maintained'`: **21 rows total**
(the 19 from the prior pass, unchanged, plus the 2 new Global rows from this pass), all
`status=ready`, all `computed_through=2026-09-02`. Per-era constituent counts unchanged from
section M of the original report.

### K. Tests
`python -m pytest -p no:randomly` on:
`test_pokemon_market_explorer_query_service.py`, `test_market_explorer_query_planner.py`,
`test_publish_market_explorer_daily_projection.py`,
`test_accept_market_explorer_global_daily_projection.py`,
`test_market_explorer_query_cache_migration.py` → **94 passed, 0 failed** (re-confirmed twice,
identical result both times). The pytest-randomly order-flakiness noted in the prior pass was
not reopened, per standing instruction.

### L. Report commit
This section (U) plus the file/script renames above, committed together — see section M below
for the actual SHA once committed.

### M. Production cache writes — this session
Real production writes were made, exclusively through the application's own
builder/lease/publish path (`MarketExplorerQueryPlanner` + `PersistentMarketExplorerCache` +
`run_market_explorer_query`, via the new driver scripts listed above) against
`pokemon_market_explorer_query_cache` / `pokemon_market_explorer_query_cache_constituents`.
Exactly 2 new rows promoted to `cache_kind=maintained`: Global All Raw (33,956 constituents) and
Global Top 10 (10 constituents, 33,956 eligible universe). No raw SQL cache payload writes were
made. Nothing in `pokemon_card_variant_market_price_intervals`,
`pokemon_market_explorer_card_daily_states`, `pokemon_market_explorer_card_daily_coverage`, or
vintage identity/merge-ledger tables was touched.

### N. Migration source-sync status
Unchanged from section T: all four production migrations
(`20260902221622_add_market_explorer_vintage_identity_repair_primitives.sql`,
`20260902221819_add_scoped_variant_monthly_rollup_rebuild.sql`,
`20260903034704_harden_market_explorer_vintage_top_hits_rebuild.sql`,
`20260903192911_add_market_explorer_current_metadata_projection.sql`) remain absent from this
worktree. **PRODUCTION_MIGRATION_SOURCE_SYNC_PENDING_CHATGPT** — non-blocking archival item, not
re-litigated this pass.

### O. Final decision

**GLOBAL_CARD_MARKET_AUTHORITY_ACCEPTED.**

Both the previously identified application-layer bugs (169-vs-165 tracked-set resolution; the
same-day projection-routing bypass) are fixed, tested (94/94 passing), and independently
verified live. The Global All Raw and Global Top 10 maintained caches are built, `ready`,
`computed_through=2026-09-02`, with exactly the required constituent counts (33,956 and 10/33,956
respectively). Summary slimming, normalized constituent-detail integrity (no duplicates, no
retired-predecessor leakage, stable paging), and warm L2/L1 serving from cache (not interactive
rebuild) are all confirmed for Global specifically, not just per-era. All 21 maintained caches
(19 per-era + 2 global) are healthy. No production interval/projection/coverage/ledger data was
touched — only cache rows, written exclusively through the real application builder path.

### P. Exact next recommendation
Prompt 4 (global daily projection + cache-first acceptance) is complete. Do not begin Prompt 5
automatically — await explicit instruction, per this task's standing constraint.
