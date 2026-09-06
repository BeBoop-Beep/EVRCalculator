# Prompt 5 — Daily Operationalization: Repo-Side Workflow

## A. Branch / HEAD
Branch `fix/public-rankings-entitlement-regression-2`, authored on top of HEAD `04c2c5bd`
(fix(market-explorer): correct Global set resolution and same-day projection routing). This is a
shared branch; other concurrent workstream files (budget product rankings, desirability) were
present dirty in `git status` at session start and were left untouched — only this session's own
two new files were staged and committed.

## B. Existing daily publication architecture
`backend/scripts/run_daily_opening_publication.py` is the only existing "coordinated daily
publication" orchestrator in the repo. It sequences: resolve promoted market date (never
wall-clock) -> run opening simulations for sets not yet current -> verify the cohort -> finalize
sealed-product Collector Appeal/Overall RIP -> publish RIP Stats -> rebuild market/set-page/Chase
snapshots -> eight sequential publication-gate audits (OPvC freshness, market-wide publication
audit, RIP contract audit, RIP Stats audit). It has zero awareness of
`pokemon_market_explorer_card_daily_states`, `pokemon_market_explorer_card_daily_coverage`, or
Market Explorer query caches — it is entirely about sealed-product opening-simulation outcomes
and RIP scoring, a different domain with a different clock and different gate semantics
(publication authority, simulation freshness, rollover).

## C. Integration point — no safe bolt-on point exists; new standalone script, explicitly
`backend/scripts/publish_market_explorer_daily_projection.py` (Prompt 4) and
`backend/scripts/accept_market_explorer_global_daily_projection.py` already exist and are reused
directly, not reimplemented. `backend/scripts/build_market_explorer_maintained_cache.py` and
`build_market_explorer_global_maintained_caches.py` (Prompt 4) supplied the exact
planner/persistent-cache/`run_market_explorer_query` builder pattern that the new cache-prewarm
code follows. Per the task's own instruction ("if genuinely no safe integration point exists, say
so explicitly rather than forcing one"): `run_daily_opening_publication.py` was inspected in full
(1083 lines) and there is no safe splice point — its eight audits are opening-analytics-specific,
its exit codes (`GATE_DEFERRED_EXIT_CODE`, publication-authority gate) are opening-analytics
concepts, and bolting Market Explorer's own success/failure semantics onto that script's `orchestrate()`
would either silently piggyback on an unrelated gate or require threading a second success/failure
path through it. **New standalone script**: `backend/scripts/run_market_explorer_daily_publication.py`,
in the same script family (`*_publication.py`, `publish_market_explorer_daily_projection.py`) and
callable directly from a cron entry the same way `run_daily_opening_publication.py` already is.

## D. Normal-day workflow (`run_daily_publication`)
1. `resolve_latest_approved_market_date` / `market_date_is_approved` — reads
   `pokemon_market_date_quality` (READY/LEGACY_VERIFIED only, `APPROVED_STATUSES` reused from the
   Prompt 4 script, not redefined). No approved date -> `status="not_ready"`, no writes at all
   (CASE D).
2. `refresh_current_metadata` — reconciles `pokemon_market_explorer_card_current_metadata` to the
   exact current canonical authority: `resolve_tracked_set_ids` (165-set intersection, unchanged)
   -> `get_pokemon_canonical_card_variant_authority` RPC (same RPC the Prompt 4 publish script
   already uses) -> excludes any `pokemon_market_explorer_variant_merge_ledger` predecessor ->
   upserts, then deletes any existing metadata row no longer in the expected set (so a newly
   retired predecessor is actually removed, not just never re-added).
3. `run_publish` (imported unchanged from `publish_market_explorer_daily_projection.py`) —
   append-only materialization + per-set exact reconciliation + coverage
   activation/repair-from-actual-table, scoped to `resolve_tracked_set_ids(client)` and
   `through_date=<resolved market date>`. This is the existing, already-tested Prompt 4 logic —
   nothing about its reconciliation/coverage contract was changed.
4. If `run_publish` reports any `failures` or `sets_reconciliation_failed`, the run stops at
   `status="projection_failed"` and **`prewarm_maintained_caches` is never called** — no cache is
   advanced past a projection that failed reconciliation.
5. Otherwise, `prewarm_maintained_caches(client, market_date=D, commit=commit)` discovers every
   `cache_kind='maintained'` row (spec-driven from `normalized_spec`, never a hardcoded
   fingerprint list) and advances each to D via `MarketExplorerQueryPlanner.execute(...,
   canonical_through=lambda: D)` — the same mechanism `build_market_explorer_maintained_cache.py`
   already uses. Each cache is wrapped in its own try/except; one failure never blocks another and
   never touches the already-committed projection/coverage state.

## E. Historical-repair workflow (`run_historical_repair`)
Separate entry point, `--repair` on the CLI. Given `set_ids` and `repair_start` (the earliest
affected approved date, supplied by the caller — this script does not attempt to discover it from
raw interval diffs, consistent with "interval repair already done upstream"):
1. Calls `reproject_pokemon_market_explorer_card_daily_states(p_set_ids, p_start_date, p_end_date)`
   — the same RPC name already declared and used by
   `repair_market_explorer_vintage_predecessor_identities.py`'s pilot re-projection path, reused
   here for the general case rather than re-derived.
2. Exact reconciliation reuses `load_variant_ids_for_set` / `load_retired_predecessor_ids` /
   `load_interval_join` / `count_actual_rows` directly from the Prompt 4 publish module — same
   point-in-time interval join, same expected-vs-actual contract, no duplicated logic.
3. On reconciliation failure: `status="reconciliation_failed"`, coverage is **not** touched
   (`activate_or_repair_coverage` is never called), the scoped-invalidation RPC is never called,
   and `prewarm_maintained_caches` is never called — verified explicitly by
   `test_historical_repair_reconciliation_failure_blocks_coverage_and_caches`.
4. On success: `activate_or_repair_coverage` (imported unchanged, same "recompute from actual
   MIN/MAX/COUNT, never trust prior row_count" contract) restores coverage per set, then
   `invalidate_pokemon_market_explorer_query_cache_scoped(p_set_ids)` is called — the exact atomic
   RPC identified in the Prompt 3 repair script's own comment as handling BOTH scoped cache
   invalidation AND the `Cards` asset's `repair_generation` bump on the DB side. This script does
   not do its own read-then-write generation bump, matching that script's explicit guidance not to
   reintroduce one.
5. `prewarm_maintained_caches(..., only_set_ids=set_ids)` then rebuilds **only** the maintained
   caches whose `normalized_spec.setIds` overlaps the repaired sets — a healthy unrelated
   maintained cache (verified by `test_scoped_prewarm_only_touches_overlapping_caches`) is left
   completely alone.

## F. Failure handling (normal-day matrix)
| Case | Behavior | Test |
|---|---|---|
| A: intervals current, projection ok, cache ok | everything advances to D | `test_normal_day_full_success_case_a` |
| B: projection ok, cache fails | projection/coverage advance to D, cache stays stale, no rollback | `test_cache_failure_does_not_roll_back_projection_case_b` |
| C: projection reconciliation fails | coverage stays at D-1, caches never touched | `test_projection_failure_prevents_cache_prewarm_case_c` |
| D: market date not ready | no-op, fail closed | `test_normal_day_not_ready_is_a_noop_case_d` |

## G. Cache-prewarm behavior
`discover_maintained_caches` reads `pokemon_market_explorer_query_cache` filtered to
`cache_kind='maintained'` only — proven dynamic (not hardcoded) by
`test_maintained_caches_discovered_dynamically_not_hardcoded`, which seeds a mixed
`maintained`/`novel` cache set and asserts only the maintained row is returned.
`advance_one_maintained_cache` skips a cache already `computed_through >= D` (idempotent
same-date rerun / resume-after-partial-batch), and rebuilds via the real
`MarketExplorerQueryPlanner`/`PersistentMarketExplorerCache`/`run_market_explorer_query` path
otherwise — no raw SQL cache payload write, matching every Prompt 4/5 script in this family.
`prewarm_maintained_caches` isolates each cache's build in its own try/except
(`test_one_failed_cache_does_not_block_others`) and supports a `only_set_ids` scope filter for the
historical-repair path.

## H. Tests / results
New suite: `backend/tests/unit/scripts/test_run_market_explorer_daily_publication.py` — **24
passed, 0 failed**. Covers: market-date resolution and fail-closed non-readiness; metadata refresh
(retired-predecessor exclusion, catalog-only exclusion, idempotency, stale-row removal, dry-run no
writes); maintained-cache discovery (dynamic, not hardcoded), already-current skip, one-failure
isolation, scoped-only prewarm; the full normal-day failure matrix (A/B/C/D above); historical
repair (earliest-date reprojection, `repair_generation` bump via the scoped RPC, reconciliation
failure blocking coverage/cache/generation-bump, no-sets no-op); service-role-only write boundary
in `main()`; JSON-serializable summary.

Combined run with the pre-existing Market Explorer suites this work touches or depends on:
```
python -m pytest -p no:randomly \
  backend/tests/unit/scripts/test_run_market_explorer_daily_publication.py \
  backend/tests/unit/scripts/test_publish_market_explorer_daily_projection.py \
  backend/tests/unit/scripts/test_accept_market_explorer_global_daily_projection.py \
  backend/tests/unit/scripts/test_repair_market_explorer_vintage_predecessor_identities.py \
  backend/tests/unit/db/services/test_market_explorer_query_planner.py \
  backend/tests/unit/db/services/test_pokemon_market_explorer_query_service.py \
  backend/tests/unit/db/test_market_explorer_query_cache_migration.py
```
**136 passed, 0 failed.** `git diff --check` on this session's own two new files: clean (the only
`git diff --check` warning was a pre-existing CRLF/LF note on an unrelated concurrent file this
session did not touch).

### Set universe / same-day routing — preserved, verified unchanged
`resolve_tracked_set_ids` and the `daily_projection_covers`-driven same-day routing in
`pokemon_market_explorer_query_service.py` were **not modified** by this session — no diff exists
against that file. The pre-existing test suite for it
(`backend/tests/unit/db/services/test_pokemon_market_explorer_query_service.py`) still passes
unchanged (included in the 136-pass run above), confirming the 165-set intersection contract and
the daily-projection-covered same-day routing fix from the prior session remain intact.

## I. Observability
Every stage's summary is a plain dataclass converted via `asdict()`, JSON-printable by
`main()` (`json.dumps(report, indent=2, sort_keys=True, default=str)`), confirmed
JSON-serializable by `test_summary_is_json_serializable`. `run_daily_publication`'s top-level
summary carries `market_date`, `status`, `metadata_refresh` (row counts), `projection` (the full
`run_publish` summary: sets attempted/new/appended/up_to_date/reconciliation_failed, rows
inserted, coverage rows repaired), `caches` (attempted/advanced/already_current/failed + one
report per cache with fingerprint/label/status/error), and `elapsed_seconds`. Failures identify the
failing scope directly (`error` string naming the market date or reconciliation diff for
projection; per-cache `error` field for cache failures) rather than dumping constituent payloads —
`prewarm_maintained_caches` reports per-cache summaries, never full cache payload bodies.

## J. Security
`run_market_explorer_daily_publication.py`'s `main()` is the only place a live client is
constructed, and it is exclusively `create_service_role_client()` (verified by
`test_main_uses_service_role_client_only`, which patches the factory and asserts the client passed
into `run_daily_publication` is the service-role sentinel). The module makes zero live-database
connections on import, matching the Prompt 4 scripts' contract. No HTTP route, API endpoint, or
anon/authenticated-role code path calls into this module anywhere in the repo — it is exclusively
an operational script invoked from the CLI/cron, exactly like its two siblings.

## K. Retry / resume
- Same-date rerun: `advance_one_maintained_cache` compares `computed_through` and returns
  `already_current` without rebuilding; `run_publish`'s existing `up_to_date` mode (Prompt 4,
  unchanged) does the same for projection/coverage.
- Cache-only retry after projection succeeded: `run_daily_publication` can be re-invoked with the
  same market date; the projection stage is a no-op (`up_to_date`) and only caches still behind D
  are rebuilt.
- Partial set-batch resume: `prewarm_maintained_caches` processes each discovered cache
  independently — a run interrupted mid-list leaves already-advanced caches at D and un-advanced
  ones at their prior `computed_through`; the next invocation picks up exactly where it left off
  because of the `computed_through >= D` skip.
- Safe interruption between stages: metadata refresh, projection, and cache prewarm are three
  independent stages with no shared transaction spanning them — an interruption after stage 2
  (projection succeeded) leaves stage 3 (caches) simply stale, which is stage B's contract, not a
  special case.

## L. Migration sync status
Unchanged from the Prompt 4 report: `PRODUCTION_MIGRATION_SOURCE_SYNC_PENDING_CHATGPT`. The four
previously-identified production migrations
(`20260902221622_add_market_explorer_vintage_identity_repair_primitives.sql`,
`20260902221819_add_scoped_variant_monthly_rollup_rebuild.sql`,
`20260903034704_harden_market_explorer_vintage_top_hits_rebuild.sql`,
`20260903192911_add_market_explorer_current_metadata_projection.sql`) remain absent from this
worktree; this session did not attempt to reconstruct any of them, and this session's new code
assumes (per the task brief) that `pokemon_market_explorer_card_current_metadata` and the RPCs
`reproject_pokemon_market_explorer_card_daily_states` /
`invalidate_pokemon_market_explorer_query_cache_scoped` already exist in production exactly as
named — the same assumption the Prompt 3/4 repair and publish scripts already make about their own
RPC dependencies.

## M. Production writes — none this session
This session made **zero** live production reads or writes. Per the task's own guidance
("prioritize a correct, well-tested implementation over a live run"), no dry-run or live
acceptance pass was executed against the production database this session — the two new files were
built, unit-tested against mocked clients only, and committed. A future session running the live
acceptance plan below needs Supabase access this session did not exercise.

## N. Production acceptance plan (for a future session)
1. `python -m backend.scripts.run_market_explorer_daily_publication --dry-run` against production
   — confirms `resolve_latest_approved_market_date`, `refresh_current_metadata`'s expected row
   count (should read ~34,225, matching the accepted Prompt 4 baseline), and
   `run_publish`'s dry-run projection plan (should report `sets_up_to_date=165` if the projection
   is already current through the resolved date) without any writes.
2. Advance the interval authority and approve one new market date (upstream, outside this script's
   scope), then run `--commit` once and confirm: `status="ok"`, `metadata_refresh.rows_removed==0`
   (no unexpected retirement), `projection.sets_reconciliation_failed==0`, coverage
   `computed_through` advanced to the new date for all 165 sets, and `caches.failed==0` with all 21
   maintained caches (19 per-era + 2 global, per the Prompt 4 acceptance) advanced to the new date.
3. Deliberately test CASE B by disabling one maintained cache's build path (or simulating a
   transient RPC failure) and confirming projection/coverage still advanced while only that one
   cache stayed stale.
4. Exercise `--repair` against a narrow, low-risk historical set/date range once a genuine
   historical interval repair is scheduled, confirming `repair_generation` increments exactly once
   and only the overlapping maintained caches rebuild.
5. Wire this script into the production cron schedule as its own line, immediately after (or
   independent of, since the domains don't share a gate) `run_daily_opening_publication.py`'s
   entry, per section C.

## O. Final decision (superseded — see section P for the live acceptance result)
**PROMPT5_REPO_READY.** The daily-operationalization workflow (normal-day append -> reconcile ->
coverage advance -> dynamic maintained-cache prewarm, plus a separate historical-repair path) is
implemented as `backend/scripts/run_market_explorer_daily_publication.py`, reuses the existing
Prompt 3/4 tooling (`publish_market_explorer_daily_projection.run_publish`,
`activate_or_repair_coverage`, the vintage repair script's
`invalidate_pokemon_market_explorer_query_cache_scoped`/`reproject_pokemon_market_explorer_card_daily_states`
RPC contracts, and the Prompt 4 maintained-cache builder pattern) rather than duplicating it,
preserves the 165-set `resolve_tracked_set_ids` intersection and same-day projection routing
exactly as-is (no diff against that file, its own test suite still green), and is covered by
**21** (not 24 — corrected) new focused mocked-DB tests plus pre-existing tests in the same domain
(136 total at that point, 0 failures). This was a repo-readiness decision only, not production
operationalization acceptance.

## P. Live production acceptance (later sessions)

### P.1 Sep-3 daily publication — ACCEPTED
The real `--commit --market-date 2026-09-03` run against production succeeded end-to-end:
**33,956 Sep-3 daily-state rows** (exact match to expected interval-authority join), **165/165**
sets advanced to `coverage.computed_through=2026-09-03`, coverage `row_count` sum **4,631,511**
exactly matching the actual total row count in `pokemon_market_explorer_card_daily_states` (zero
mismatch). Two real bugs were found and fixed along the way (both independently verified live,
not just unit-tested): the daily-states upsert's `ON CONFLICT` target was
`market_date,card_variant_id,set_id`, which matches no real constraint (the actual primary key,
confirmed via `pg_constraint`, is `(market_date, card_variant_id)` only) — every commit-mode
insert failed with `42P10` until corrected; and `_spec_from_normalized` selectively reconstructed
a subset of the persisted `normalized_spec` dict, silently dropping `contractVersion`, which
`query_fingerprint`/the planner path require — every maintained-cache advance failed with a
`KeyError` until the function was changed to spread the full stored dict.

### P.2 Failed-cache lifecycle defect and fix
20 of 21 maintained caches advanced cleanly to Sep-3. The 21st, **Global All Raw**
(fingerprint `66426743b657a45f4381f3a5b9a5f216158158d4dd3c6ba8b8da6ec56c53a8e6`), was stuck
`status='failed'` with a fully valid, intact Sep-2 artifact (`series_payload` present with a real
`trend` key, `constituent_count=33956`, normalized constituent detail intact at 33,956 rows). Root
cause, confirmed by reading `MarketExplorerQueryPlanner.execute()` directly: a `failed` row was
never considered a possible incremental build base — only `status='ready'` rows supplied
`previous`, so a failed row always forced `previous=None`, triggering a full historical rebuild
(from the earliest interval date) at global scope, which is why the original Sep-3 refresh
attempt had failed with a `57014` statement timeout in the first place. A second, related defect:
`persistent.publish(...)` returning `False` was only recorded as a metric, not raised — the
planner could report a false "success" while the cache never actually became `ready`.

**Fix implemented** in `backend/db/services/market_explorer_query_planner.py`:
- `_is_recoverable_failed_base(row, spec, generation)` — a `status='failed'` row may supply
  `previous_computed_through` (never served as a cache hit) only when: `computed_through` is
  present, `series_payload` exists and has a real `trend` key, `query_contract_version` /
  `service_version` / `instrument_methodology_version` are `None` or match the current spec's
  expected values, no active build lease is held (`build_token`/`build_expires_at` both null —
  the invariant `fail_pokemon_market_explorer_query_cache_build` guarantees on release), and the
  publication-generation watermark is `trusted` (an untrusted/unknown repair generation fails
  closed, matching the module's existing freshness posture).
- `execute()` now computes `previous` from either a `ready` row (existing behavior, unchanged) or
  a recoverable-`failed` row (new) — both feed the same incremental `novel_builder`/
  `merge_incremental_result` path already used for normal forward publication. A failed row is
  still never returned by the `status == "ready"` cache-hit gate above it in `execute()` — it is
  purely an internal build-base source.
- `persistent.publish(...)` returning `False` now raises `MarketExplorerPublishFailed` (new
  exception class) instead of silently returning success; the existing `except Exception:
  persistent.fail(...)` handler around the build/publish block already covers this, so the lease
  is released the same way any other build failure releases it — no new cleanup path needed.
- Ready-cache preservation: because `publish()` is one atomic `UPDATE ... WHERE status='building'
  AND build_token=... AND build_expires_at > now()` (confirmed via `pg_get_functiondef`), a failed
  publish attempt never touches the row's previously-committed `series_payload`/`computed_through`
  at all — there is no separate "clear then rebuild" step to accidentally destroy a last-good
  `ready` artifact. This was true of the existing schema/RPC design already; no additional code
  was needed to satisfy this requirement.
- A related bug in the **orchestrator** (`run_market_explorer_daily_publication.py`, not the
  shared planner) was found and fixed during live testing: `advance_one_maintained_cache`'s
  already-current short-circuit checked only `computed_through >= market_date`, ignoring `status`
  entirely — so a `failed` row whose `computed_through` had already been bumped to the target date
  by an earlier partial attempt was silently treated as "already current" and never even handed to
  `planner.execute()` for a recovery attempt. Fixed to require `status == "ready"` before
  short-circuiting; a `failed` row at any `computed_through` now always reaches the planner.

### P.3 Tests
16 planner tests plus 2 orchestrator tests (23 total new/changed across both files) added,
covering: failed-row eligibility as an incremental base; failed rows never served as
`persistent_cache` hits; correct `previous` resolution (Sep-2, not `None`) for a recoverable
failed row when canonical-through is Sep-3; successful recovery publishing `ready`/Sep-3; failed
rows with no payload, no `computed_through`, incompatible version, or stale repair-generation are
each correctly rejected as unrecoverable; a previously-`ready` cache's payload is untouched by a
failed refresh attempt; a never-successful cache may correctly remain `failed`;
`publish(False)` raises and cannot produce a successful result; the build lease is released after
a publish failure; existing L1/L2 hit semantics and stale/incremental behavior are unchanged; and
the orchestrator's `already_current` vs. must-attempt-recovery decision now correctly depends on
`status`, not just date. Full relevant regression run: **153 passed, 0 failed**
(`test_market_explorer_query_planner.py`, `test_run_market_explorer_daily_publication.py`,
`test_publish_market_explorer_daily_projection.py`, `test_pokemon_market_explorer_query_service.py`,
`test_market_explorer_query_cache_migration.py`, `test_accept_market_explorer_global_daily_projection.py`,
`test_repair_market_explorer_vintage_predecessor_identities.py`). `test_pokemon_public_snapshot_service.py`
was not run — known, pre-existing, unrelated breakage from concurrent P0 work on this shared
branch, out of scope.

### P.4 Global All Raw live recovery — BLOCKED on a genuine, separate DB-side issue
With the planner and orchestrator fixes in place, live testing confirmed the fix works exactly as
designed: `_is_recoverable_failed_base` correctly returns `True` for the Global All Raw row, and
the orchestrator no longer short-circuits it as already-current. A direct timed diagnostic
against production confirmed the incremental builder itself is fast — `builder(previous=
'2026-09-03', through='2026-09-03')` completed in **4.2 seconds** (`executionEngine=
daily_projection`, `currentBasketRowCount=33955`), nowhere near the 300-second build lease. So
the recovery detection and incremental-build path are proven correct and fast.

The actual blocker is one level deeper: calling the real
`publish_pokemon_market_explorer_query_cache_build` RPC directly (bypassing the Python
`publish()` wrapper, which was swallowing the real exception behind a bare `type(exc).__name__`
log line) surfaces `APIError {'code': '57014', 'message': 'canceling statement due to statement
timeout'}` — the **publish RPC itself** times out server-side while writing the ~33,956-row
`p_current_constituents` payload for the Global scope specifically (every other, smaller per-era
cache publishes this same RPC without issue). This is a genuine database-side performance
limitation in the publish/constituent-write path at global scale, not a defect in the planner
recovery logic this session was scoped to fix, and it is explicitly out of this session's
authorized scope to address (no `statement_timeout` increases, no migration authoring — that
remains "ChatGPT"'s domain per the standing task boundaries). Every failed attempt correctly
self-recovered: `persistent.fail(...)` released the build lease every time (confirmed live —
`build_token`/`build_expires_at` both `null` after each attempt), so the row is left in a clean,
retryable `failed` state, not stuck or corrupted.

### P.5 21-cache state — 20/21
Reconfirmed live: 21 total maintained Cards caches, **20 ready through `computed_through=
2026-09-03`**, 1 (Global All Raw) still `status='failed'` (clean, retryable, per P.4). Projection
and coverage are unaffected by any of this: 33,956 Sep-3 rows, 4,631,511 total rows, 165/165
coverage through Sep-3, row_count sum 4,631,511 — all unchanged and exact across every retry in
this session.

### P.6 Idempotency
Every rerun in this session correctly detected the 165 sets as already up-to-date (no duplicate
projection rows, no coverage regression) and the 20 healthy caches as already-current — only the
one genuinely-still-failed Global All Raw cache was re-attempted each time, exactly as designed.
No Global cold rebuild occurred at any point once the planner fix landed (every attempt used the
fast incremental path); the only remaining failure mode is the publish-RPC timeout in P.4.

### P.7 Global query smokes — not run this session
Not exercised, since Global All Raw remains non-`ready` (P.4/P.5) — running the smoke queries
against an unpublished cache would not be a meaningful acceptance signal. Recommended as the next
step once the publish-RPC timeout is resolved.

### P.8 Final decision
**NOT `MARKET_EXPLORER_DAILY_OPERATIONALIZATION_ACCEPTED`.** The planner-level failed-cache
recovery fix (the actual subject of this task) is implemented, tested (153/153), and verified
live to work correctly and quickly. However, full 21/21 cache acceptance is blocked by a genuine,
separate, database-side statement-timeout in the publish RPC's constituent-write path at global
scale — a real production finding, not a false pass forced through. Sep-3 projection/coverage
(the load-bearing data) remain fully accepted and untouched by any of this session's retries.

### P.9 Next recommendation
Investigate and fix the `publish_pokemon_market_explorer_query_cache_build` RPC's performance at
~34k-row `p_current_constituents` scale (e.g., writing normalized constituent detail via a
separate bulk/batched path rather than one large JSONB parameter in the same statement as the
summary-row `UPDATE`, or raising the timeout specifically for this one RPC if that is judged safe
by whoever owns database performance — this session was explicitly not authorized to make that
call). Once fixed, rerun `run_market_explorer_daily_publication.py --commit --market-date
2026-09-03` once more — no further Python-side changes should be needed; the planner recovery
path already correctly detects and uses the failed Sep-2 artifact as an incremental base. After
Global All Raw reaches `ready`, run the Global query smokes (P.7) to complete acceptance.

## Q. Staged/batched publication integration — ACCEPTED (final session)

This section documents the resolution of the P.4/P.9 blocker. The narrative in sections P.1–P.9
above is preserved exactly as it happened and should not be read as superseded in substance — the
diagnosis there (a genuine `57014` in the publish path at global scale) was correct; this section
records the fix and final live acceptance.

### Q.1 Trigger root cause (as reported by the production migration author)
The pre-existing `PUBLISH_RPC` (`publish_pokemon_market_explorer_query_cache_build`) was not
itself the bottleneck — a synchronous trigger, `trg_sync_market_explorer_query_cache_constituents`,
fires whenever `current_constituents` changes and does a `DELETE` + full JSONB parse + `INSERT`
of one normalized row per constituent, all inside the same statement/transaction as the publish
RPC. For Global All Raw that is ~34k synchronous row writes inside one PostgREST call, which is
what actually hit the statement timeout — not the summary-row `UPDATE` itself.

### Q.2 Migration `20260905040740_add_batched_market_explorer_cache_publication`
Applied live in production (confirmed via `pg_get_functiondef`, not merely trusted). Adds four new
service-role-only RPCs, alongside the unchanged legacy `PUBLISH_RPC` (kept for other callers, not
used as a Global fallback):
- `stage_pokemon_market_explorer_query_cache_build(...)` — writes the summary row
  (`computed_from`/`computed_through`/`series_payload`/`current_value`/`constituent_count`/
  `eligible_universe_count`/`current_constituents`) while explicitly setting
  `market_explorer.skip_constituent_sync = on` for the session, bypassing the synchronous trigger.
  Requires `status='building'` + matching `build_token` + unexpired lease; returns `false`
  otherwise.
- `upsert_pokemon_market_explorer_query_cache_constituent_batch(p_items jsonb)` — inserts/updates
  up to 1000 items per call (hard-enforced server-side; the function itself returns `-1` for a
  batch outside `[1, 1000]`), each item keyed by `(query_fingerprint, rank)` with `card_variant_id`
  extracted for indexing and the full item JSON preserved. Also requires the row to be
  `building`/token-matched/lease-unexpired, and rejects (`-1`) any batch with a null/non-positive
  rank or a duplicate rank within the batch. Returns the actual affected row count on success.
- `trim_pokemon_market_explorer_query_cache_constituent_batch(p_keep_through_rank, p_limit=1000)`
  — deletes constituent rows with `rank > p_keep_through_rank`, up to `p_limit` (max 5000) per
  call, for a shrinking market; returns the deleted count, or `-1` on an invalid/unclaimed request.
- `finalize_pokemon_market_explorer_query_cache_build(...)` — independently re-derives
  `constituent_count` from the summary row, then cross-validates the just-written detail table:
  `count(*) == expected`, `count(card_variant_id) == expected` (no nulls), `count(distinct
  card_variant_id) == expected` (no duplicates), `min(rank) = 1`, `max(rank) = expected` (no
  gaps). Only if all hold does it atomically flip `building → ready` and clear the lease; any
  mismatch returns `false` and leaves the row `building` (letting the caller decide to fail/retry).

### Q.3 `PersistentMarketExplorerCache.publish()` rewrite
`backend/db/services/market_explorer_query_planner.py` — `publish()` now: (1) slices
`payload["currentConstituents"]` into batches of `CONSTITUENT_BATCH_SIZE=500` (a safety margin
under the production hard limit of 1000, never sent at more than 1000 regardless), calling
`upsert_..._constituent_batch` per slice with each item's **absolute** rank preserved (batch N
contains ranks `500N+1..500N+500`, never renumbered to `1..500`), aborting with `False` if any
batch call errors, returns `< 0`, or returns a count not equal to the batch length; (2) loops
`trim_..._constituent_batch` with `p_keep_through_rank=len(constituents)` until it returns `0`,
aborting with `False` on any negative return (handles a market whose constituent count shrank
since the last publish); (3) only after all constituent writes complete, calls
`stage_..._build` with the summary fields, aborting with `False` if it returns `False`; (4) only
after a successful stage, calls `finalize_..._build`, returning its boolean result directly. Any
exception at any step is caught by the existing outer `try/except` (unchanged), which logs and
returns `False` — there is no fallback to the legacy one-shot `PUBLISH_RPC` at any point.

### Q.4 Failed-base validation hardening
Production re-inspection (before this fix) found the Global All Raw row's "valid" Sep-2 artifact
from P.4 had since been overwritten by a subsequent failed attempt into an internally
*incoherent* shape: `computed_through` advanced to Sep-3, `constituent_count` still `33956`
(stale), but `series_payload` reduced to `{"asOf": "2026-09-03", "trend": [["2026-09-03", 1]]}`
and `current_constituents: []` — every field individually present, but mutually contradictory.
`_is_recoverable_failed_base` was hardened to catch exactly this shape (and confirmed live against
the actual corrupted row before the fix — see Q.6): it now additionally requires
`current_constituents` to exist as a list and (`if constituent_count > 0`) have length exactly
equal to `constituent_count`; `series_payload["asOf"]` to agree with `computed_through`;
`series_payload["historyStartDate"]` to agree with `computed_from` when both are present; and (a
market spanning more than one day) `len(trend) > 1` — a single-point trend can never honestly
represent a multi-day history, which is precisely the placeholder shape a partial failed write
leaves behind. `PersistentMarketExplorerCache.read()`'s column selection was also missing
`constituent_count` entirely (silently `None` for every caller) and has been added.

### Q.5 Tests
17 new/changed planner tests (68 total in `test_market_explorer_query_planner.py`, up from 51):
a direct regression fixture reproducing the exact corrupted-row shape from Q.4
(`test_corrupted_global_shaped_failed_artifact_is_not_recoverable`, asserting
`_is_recoverable_failed_base(...) is False`) plus its complementary coherent-artifact case; a
`StagedRpcClient` fake exercising `PersistentMarketExplorerCache.publish()` directly against the
real RPC call sequence (no live DB) covering: batching at the configured size, absolute rank
preservation across batch boundaries, a hard guarantee no single batch call ever exceeds 1000
items, a batch-count-mismatch or negative-return failure aborting the publish, the trim loop
running until it returns zero, stage only being called after all batches/trim complete, a `False`
from `stage` or `finalize` aborting without a false-success, a raised exception during any RPC
call aborting cleanly, and confirmation that `constituent_page()` and the legacy `read()`
`currentConstituents` hydration are both untouched by the rewrite. Full relevant regression:
**170 passed, 0 failed** (`test_market_explorer_query_planner.py`,
`test_run_market_explorer_daily_publication.py`, `test_publish_market_explorer_daily_projection.py`,
`test_pokemon_market_explorer_query_service.py`, `test_market_explorer_query_cache_migration.py`,
`test_accept_market_explorer_global_daily_projection.py`,
`test_repair_market_explorer_vintage_predecessor_identities.py`). `git diff --check` clean.
The two previously-restored fixes (`on_conflict="market_date,card_variant_id"` and
`_spec_from_normalized`'s full-dict spread including `contractVersion`) were reconfirmed present
and untouched.

### Q.6 Live Global All Raw recovery
Before running the fix, the corrupted row was reconfirmed live exactly as Q.4 describes
(`status=failed`, `computed_through=2026-09-03`, `constituent_count=33956`,
`series_payload={"asOf":"2026-09-03","trend":[["2026-09-03",1]]}`, `current_constituents=[]`) —
so the hardened `_is_recoverable_failed_base` correctly rejects it, and the planner takes the
expected path: a full cold rebuild (not a fallback to interval, not a `statement_timeout`
increase). Running `run_market_explorer_daily_publication.py --commit --market-date 2026-09-03`
produced `caches: {"advanced": 1, "already_current": 20, "failed": 0}` and overall `"status":
"ok"`. Live verification immediately after:
- `pokemon_market_explorer_query_cache`: `status='ready'`, `computed_from='2026-04-07'`,
  `computed_through='2026-09-03'`, `constituent_count=33955`, `eligible_universe_count=33955`.
- `pokemon_market_explorer_query_cache_constituents`: `count(*)=33955`,
  `count(distinct card_variant_id)=33955`, `min(rank)=1`, `max(rank)=33955` — internally exact,
  confirming `finalize_..._build`'s own integrity check passed for real.
- Retired-predecessor leakage: `0` (joined against `pokemon_market_explorer_variant_merge_ledger`).

**One honest discrepancy worth flagging, not hidden:** the constituent count is **33,955**, not
the **33,956** baselined earlier in this document and in Prompt 4's acceptance. This is NOT a
batching/finalize bug — the detail table is perfectly self-consistent (count = unique IDs = max
rank), and an earlier same-session diagnostic (a direct, unbatched timed call to the underlying
builder, before any of today's fix was involved) independently reported the identical
`currentBasketRowCount: 33955` for real Sep-3 data. The underlying `pokemon_market_explorer_
card_daily_states` table itself still has exactly `33956` rows for Sep-3 — so one instrument that
has a valid daily-state row is being excluded somewhere in the cohort/basket-construction layer
(`run_market_explorer_query`/its helpers in `pokemon_market_explorer_query_service.py`) before it
reaches the cache payload. That code was not touched by this session and is outside this task's
scope (planner-side cache lifecycle, not query cohort construction) — flagged here as a real,
specific, one-row discrepancy for a future session to trace, not swept under "legitimate drift"
without evidence. It is not a blocker: Sep-3 projection/coverage (the source of truth) remain
exactly 33,956/4,631,511/165-of-165 throughout, unaffected by this cache-layer discrepancy.

### Q.7 Final 21/21 cache acceptance
Reconfirmed live: **21 maintained Cards caches, 21 ready**, `min(computed_through) =
max(computed_through) = 2026-09-03`. No maintained cache left `building`/`failed`/stale for Sep-3.

### Q.8 Idempotency rerun
Ran the identical `--commit --market-date 2026-09-03` command a second time. Result:
`caches: {"advanced": 0, "already_current": 21, "failed": 0}`, projection
`{"sets_appended": 0, "sets_up_to_date": 165, "total_rows_inserted": 0}`, overall `"status": "ok"`.
Live re-verification: Sep-3 rows unchanged (33,956), total projection rows unchanged (4,631,511),
coverage unchanged (165/165 through Sep-3, row_count sum 4,631,511 exactly), all 21 caches
unchanged (still ready through Sep-3). No Global cold rebuild occurred on the rerun — Global All
Raw was correctly recognized as `status='ready'`/`computed_through>=market_date` and skipped as
`already_current`, exactly as designed.

### Q.9 Global query smokes
Ran all four via the real `run_market_explorer_query` application function for `2026-09-03`:

| Query | executionEngine | constituentCount | eligibleUniverseCount | trackedValue |
|---|---|---|---|---|
| Global All Raw | `daily_projection` | 33,955 | 33,955 | 637,042.00 |
| Global Top10 | `daily_projection` | 10 | 33,955 | 35,332.31 |
| Global rareHolo | `daily_projection` | 3,055 | 3,055 | 148,957.52 |
| Global Premium | `daily_projection` | 1,344 | 1,344 | 392,879.76 |

All four resolved via `daily_projection` — no interval fallback, no `57014` timeout, in any case.
rareHolo/Premium counts and values match the originally-baselined Sep-3 figures exactly; All
Raw/Top10 reflect the same 33,955-vs-33,956 discrepancy noted in Q.6, not a new issue.

### Q.10 Migration source-sync status
Five Market Explorer production migrations now await exact source-control mirroring (one more
than before — the new batched-publication migration):
`20260902221622_add_market_explorer_vintage_identity_repair_primitives.sql`,
`20260902221819_add_scoped_variant_monthly_rollup_rebuild.sql`,
`20260903034704_harden_market_explorer_vintage_top_hits_rebuild.sql`,
`20260903192911_add_market_explorer_current_metadata_projection.sql`,
`20260905040740_add_batched_market_explorer_cache_publication.sql`. None were reconstructed —
their exact SQL was read live via `pg_get_functiondef` for verification purposes only, not written
to any file in this repo. **`PRODUCTION_MIGRATION_SOURCE_SYNC_PENDING_CHATGPT`**, non-blocking.

### Q.11 Final decision
**`MARKET_EXPLORER_DAILY_OPERATIONALIZATION_ACCEPTED`.** The staged/batched publication path is
implemented, tested (170/170), and verified live end-to-end: the hardened failed-base validation
correctly rejected the corrupted Global All Raw artifact, the resulting cold rebuild published
successfully through the new staged RPC sequence, all 21 maintained caches are `ready` through
Sep-3, a full idempotent rerun performed zero redundant work, and all four Global query smokes
resolve via `daily_projection` with no timeout. The one open item (Q.6's 33,955-vs-33,956
one-row discrepancy) is a real, narrow, non-blocking finding in the query cohort-construction
layer — outside this task's scope — recommended as the next investigation, not a gap in this
session's actual deliverable.

### Q.12 Next recommendation (superseded — see section R for the resolution)
Trace the single-instrument discrepancy from Q.6: compare `pokemon_market_explorer_card_daily_
states` for `market_date='2026-09-03'` (33,956 rows) against whatever cohort-filtering step in
`run_market_explorer_query`/its helpers produces the 33,955-row Global All Raw basket, to identify
which one instrument is being excluded and why (a genuine data-quality exclusion, e.g. a price of
zero/null slipping through, versus an unintended filter). This is unrelated to Prompt 5's
daily-operationalization scope and does not block treating this task as complete. Do not begin
Prompt 6 without explicit instruction.

## R. Projection authority hardening — RESOLVED (later session)

This section resolves the Q.6/Q.12 open item. The 33,955-vs-33,956 discrepancy is **not** a
query-cohort construction bug — it was a genuine leaked row in the daily-states projection itself.

### R.1 Root cause
One invalid instrument was present in the daily projection: `card_variant_id
1358073e-4ad4-4d8c-8b87-5801fd36c7e8` (Gym Challenge, "______'s Chansey (DUPLICATE)" #113),
whose canonical `catalog_role` is `duplicate_alias` — a role Market Explorer instrument semantics
explicitly exclude (alongside `abstract_identity` and any unapproved role), via the existing
canonical predicate `is_pokemon_market_instrument_catalog_role(...)`. The query/cache layer
correctly excluded it through current metadata (hence the correct `33,955` cache basket); the
**daily projection publisher** did not, so `pokemon_market_explorer_card_daily_states` carried
`33,956` Sep-3 rows — one too many. 140 invalid historical state rows (2026-04-11 through
2026-09-03) were removed from production directly (by the collaborating session that traced this
live); this session did not touch production data, only the Python-side authority boundary that
allowed the leak to persist/reproduce.

### R.2 Why the normal append path didn't already exclude it
`publish_market_explorer_daily_projection.py`'s normal new/append path already derives its
candidate variant set from `get_pokemon_canonical_card_variant_authority` (via
`load_variant_ids_for_set`), which already filters on `is_pokemon_market_instrument_catalog_role`
— that RPC's output is trusted as-is, not re-filtered with a Python allow-list. The leaked row
predates that filtering being authoritative for this instrument (or was written via
`run_market_explorer_daily_publication.py`'s historical-repair path, which invokes the opaque,
DB-side `reproject_pokemon_market_explorer_card_daily_states` RPC — a function this repo does not
own the SQL for and cannot audit). Because normal daily runs only ever append *new* dates forward
(`process_set`'s `append`/`up_to_date` modes never re-touch previously-materialized dates), a stray
row written by any other path — a historical reproject, or a row predating a catalog-role
correction — would never be re-examined or removed by the ordinary day-to-day flow, regardless of
how correct that flow's own filtering is.

### R.3 Fix — self-healing authority boundary, not a Chansey special case
Added `purge_ineligible_daily_state_rows(client, *, commit, set_id, eligible_variant_ids)` to
`backend/scripts/publish_market_explorer_daily_projection.py`: it loads every `card_variant_id`
currently materialized for a set (`load_materialized_variant_ids`) and deletes any row whose
variant is not in the current authority-eligible set (variant ids from
`get_pokemon_canonical_card_variant_authority`, minus active vintage-predecessor retirements — the
same `eligible` set already used for materialization). This is called:
- In `process_set`, immediately after resolving `variant_ids`/`retired_ids`, **before** any
  reconciliation or coverage decision — for every mode (`new`/`append`/`up_to_date`), so a stray
  row is purged even on a set that has nothing new to materialize.
- In `run_historical_repair`, immediately after the opaque `reproject_pokemon_market_explorer_card_
  daily_states` RPC call and before the expected/actual reconciliation loop, using the identical
  `eligible` list that produces `expected` — guaranteeing both sides of that reconciliation compare
  the same instrument universe regardless of what the RPC itself wrote.

No catalog-role list is duplicated in Python: eligibility is entirely delegated to the existing
`get_pokemon_canonical_card_variant_authority` RPC (which already applies
`is_pokemon_market_instrument_catalog_role`). This makes the fix generic — it would equally purge
an `abstract_identity` or any future-excluded role, and self-heals a rerun so an excluded identity
can never be reintroduced, without naming any one instrument in code.

### R.4 Reconciliation-filter implementation
`reconcile_set` and the historical-repair reconciliation loop already computed `expected` from
`load_interval_join(client, eligible, market_date)` using the same authority-filtered `eligible`
list used for materialization — so once the purge removes a stray row from the `actual` side,
`expected == actual` holds exactly, with no separate "expected-side" allow-list needed.

### R.5 Tests
14 new tests added across `backend/tests/unit/scripts/test_publish_market_explorer_daily_
projection.py` and `test_run_market_explorer_daily_publication.py`, covering: duplicate_alias
excluded from materialization and from the expected count; approved physical roles still
materialize; a valid instrument with no NM state on a date is not fabricated; both reconciliation
sides use the identical filtered universe; a rerun cannot reinsert an excluded alias; purge removes
a stray row left by any prior leak (dry-run-safe); a reduced-scale Sep-3-style fixture (5 valid +
1 duplicate_alias raw candidate → expected/actual = 5); the opaque historical-reproject RPC path is
purged before reconciliation; and all pre-existing idempotency / `on_conflict="market_date,card_
variant_id"` behavior remains intact. Full regression: **336 passed, 0 failed**
(`-k market_explorer` across `backend/tests`, billing/stripe-module and one unrelated logging test
module excluded from collection — pre-existing `ModuleNotFoundError: stripe` / Python 3.8 typing
issue, unrelated to this change). `git diff --check` clean on all changed files.

### R.6 Corrected baselines going forward
Sep-3 valid Global All Raw / canonical daily-states universe: **33,955** (not 33,956). Sep-3 total
projection rows, coverage sum, and the 4,631,511 figure throughout sections P/Q above are likewise
superseded by the corrected, reconciled production figures: **4,631,371** total projection rows,
coverage sum **4,631,371**, 0 mismatches, 165/165 sets covered through Sep-3, 21/21 maintained
caches ready. The `33,956` / `4,631,511` figures anywhere above are historical narrative of the
leak as it was diagnosed, not the current correct state.

### R.7 Final decision
The projection authority boundary is hardened: excluded catalog roles (`duplicate_alias`,
`abstract_identity`, any unapproved role) can no longer be materialized or survive a rerun, on
either the normal daily-append path or the historical-repair path, via a single generic
self-healing purge rather than an instrument-specific patch. Do not begin Prompt 6 without explicit
instruction.

## S. DB-side authority hardening — production migration mirrored (later session)

This section closes the remaining gap R.2 flagged: the opaque, DB-side
`reproject_pokemon_market_explorer_card_daily_states` RPC that this repo could not audit.

### S.1 What changed at the database level
The historical reproject RPC previously rebuilt `pokemon_market_explorer_card_daily_states`
directly from `pokemon_card_variant_market_price_intervals` alone -- no authority join -- so any
interval row for an excluded catalog role (`duplicate_alias`, `abstract_identity`, unapproved)
would be re-materialized verbatim by a historical repair, regardless of the Python-side purge
added in R.3. Production migration `20260906003840_harden_market_explorer_reproject_authority_
boundary` replaces the function so its `INSERT` now joins interval candidates through
`get_pokemon_canonical_card_variant_authority(p_set_ids)` on **both** `card_variant_id` and
`set_id` before they can reach the daily-states table -- an excluded catalog role can no longer
be reintroduced by historical repair at the database level, not merely purged after the fact.
The RPC is unchanged otherwise: still `service_role`-only execute, still `SET statement_timeout TO
'300s'` / `SET work_mem TO '64MB'`, still enforces its pre-existing coverage preconditions (every
requested set must already have a coverage row; the repair end date may not exceed any requested
set's `computed_through`), and still recomputes coverage `row_count`/`first_market_date` from the
actual post-repair table contents rather than trusting an input. It additionally returns
`authorityFiltered: true` in its result payload, an explicit signal the authority join is active.

### S.2 Repo migration file
Added `backend/db/migrations/20260906003840_harden_market_explorer_reproject_authority_boundary.sql`
containing the exact statement recorded in production's `supabase_migrations.schema_migrations`
for version `20260906003840` (read via direct SQL query against that ledger, byte-compared against
the file on disk to confirm an exact match) -- not reconstructed or paraphrased from the task
description or from reading the function live via `pg_get_functiondef`.

### S.3 Live verification (already performed, not rerun)
For Gym Challenge across the previously-affected historical window: raw interval candidates
**35,252**, authority-filtered candidates **35,112**, difference **140** -- exactly matching the
140 duplicate_alias state rows removed from production in the original diagnosis (see the root
Prompt 5 summary above). No destructive reproject was rerun in this session merely to reprove this;
the ledger SQL and this arithmetic match are the verification.

### S.4 Contract tests
New file `backend/tests/unit/db/test_market_explorer_reproject_authority_boundary_migration.py`,
following the same string-contract pattern as the existing eligibility-migration test
(`test_market_explorer_instrument_eligibility_migration.py`), asserting on the normalized SQL text:
the authority RPC is called with `p_set_ids`; the join is keyed by both `card_variant_id` and
`set_id`; the `INSERT`'s own join chain actually includes the authority CTE (not merely defined and
unused); the coverage preconditions and their exact error text are preserved; coverage `row_count`
is recomputed from actual daily-states contents; `service_role`-only grant/revoke is preserved; the
`300s`/`64MB` session settings are preserved; and the result payload asserts
`'authorityfiltered',true`. **8/8 passed.** The pre-existing Python purge tests from commit
`6b8f5417` were left untouched and reconfirmed passing. Combined regression across the migration
contract tests, the eligibility migration test, and the full Prompt 4/5 script/service/planner
suite: **194 passed, 0 failed**. `git diff --check` clean.

### S.5 Defense-in-depth posture
Both layers now independently enforce the authority boundary: the database-level join in this
migration prevents an excluded catalog role from ever being written by historical repair, and the
Python-level `purge_ineligible_daily_state_rows` (R.3) independently self-heals any stray row from
any source -- including a row written before this migration existed, or by any future write path
this repo does not control. Neither depends on the other for correctness; removing either still
leaves the boundary enforced by the remaining one.

### S.6 Corrected baseline reconfirmed
Canonical Sep-3 Global All Raw / daily-states universe remains **33,955** (unchanged by this
session -- this session hardened the write path, it did not touch data).

### S.7 Market Explorer migration-source-sync backlog (superseded — see section T)
Queried production's `supabase_migrations.schema_migrations` directly (version >=
`20260902000000`) and cross-checked against `backend/db/migrations/` and `supabase/migrations/` in
this repo. Market-Explorer-scoped migrations still live in production but **absent from this repo**
(none reconstructed or guessed -- listed here as backlog only):
- `20260902221622_add_market_explorer_vintage_identity_repair_primitives`
- `20260902221819_add_scoped_variant_monthly_rollup_rebuild`
- `20260903034704_harden_market_explorer_vintage_top_hits_rebuild`
- `20260903192911_add_market_explorer_current_metadata_projection`
- `20260904173530_canonical_market_root_set_universe_v1`
- `20260904173806_exclude_invalid_gym_challenge_duplicate` -- notable: this is very likely the
  actual production data-repair migration for the Chansey duplicate_alias rows this entire
  investigation traces back to; it has not been read or reconstructed this session.
- `20260904174406_canonical_market_publication_certification_v1`
- `20260904174801_canonical_market_root_set_daily_history_v1`
- `20260905040740_add_batched_market_explorer_cache_publication`

Confirmed already present and unaffected: `20260902031454_push_down_market_explorer_daily_scope_
filters` (in `supabase/migrations/`), and this session's own
`20260906003840_harden_market_explorer_reproject_authority_boundary` (in `backend/db/migrations/`).
`PRODUCTION_MIGRATION_SOURCE_SYNC_PENDING_CHATGPT` remains the status for the backlog above --
non-blocking, and out of this session's scope to reconstruct.

### S.8 Final decision (superseded — see section T for the completed sync)
DB-side authority hardening is mirrored into the repo, byte-verified against the production
migration ledger, and covered by a passing contract test suite. Combined with the R-section
Python-side purge, the Market Explorer daily/historical projection write path is now enforced
against the canonical instrument authority at both the database and application layers. Do not
begin Prompt 6 without explicit instruction.

## T. Final production migration source sync — COMPLETE (later session)

This section resolves the S.7 backlog. All nine previously-missing Market Explorer production
migrations were retrieved directly from `supabase_migrations.schema_migrations` and mirrored
verbatim -- no SQL reconstructed, paraphrased, normalized, or "cleaned up."

### T.1 Files added
`backend/db/migrations/`:
- `20260902221622_add_market_explorer_vintage_identity_repair_primitives.sql`
- `20260902221819_add_scoped_variant_monthly_rollup_rebuild.sql`
- `20260903034704_harden_market_explorer_vintage_top_hits_rebuild.sql`
- `20260903192911_add_market_explorer_current_metadata_projection.sql`
- `20260904173530_canonical_market_root_set_universe_v1.sql`
- `20260904173806_exclude_invalid_gym_challenge_duplicate.sql`
- `20260904174406_canonical_market_publication_certification_v1.sql`
- `20260904174801_canonical_market_root_set_daily_history_v1.sql`
- `20260905040740_add_batched_market_explorer_cache_publication.sql`

`20260906003840_harden_market_explorer_reproject_authority_boundary.sql` (mirrored in the prior
session, section S) was compared against the ledger again and left unmodified -- exact match.

### T.2 Exact ledger verification (two independent passes)
Pass 1: fetched each version's `statements` array from `supabase_migrations.schema_migrations`,
wrote it verbatim to its target file, and round-tripped a read-back comparison at write time. Pass
2 (independent, on a fresh query): computed `md5(array_to_string(statements, E'\n'))` directly in
production for all ten versions (the nine new mirrors plus `20260906003840`) and compared each
against the local file's MD5 (file content minus the single trailing newline added on write, since
`array_to_string` of a one-element array reproduces that element exactly). **All 10 versions
MD5-matched exactly.** No whitespace normalization, reformatting, or reconstruction occurred at any
step -- every file is the literal ledger statement.

### T.3 Chansey migration content confirmed
`20260904173806_exclude_invalid_gym_challenge_duplicate` contains **only** an `UPDATE
public.pokemon_canonical_cards` for canonical id `5b336ad8-1397-42ea-a88b-53c0d67f6d82`
(`______'s Chansey (DUPLICATE)`), setting `catalog_role='duplicate_alias'`,
`set_value_eligible=false`, `opening_eligible=false`, and an explanatory `eligibility_reason`. It
does not reference or delete from `pokemon_market_explorer_card_daily_states` -- confirming the
root-cause narrative exactly: the canonical correction alone did not retroactively clean
already-materialized daily-state rows; that gap was closed separately by Prompt 5's own generic
purge (`purge_ineligible_daily_state_rows`, commit `6b8f5417`) and by the later DB-side
`20260906003840` hardening (section S), not by this migration.

### T.4 Historical ordering preserved, not "fixed"
`20260902221622` (the *original* `reproject_pokemon_market_explorer_card_daily_states`,
2026-09-02) inserts directly from `pokemon_card_variant_market_price_intervals` with no canonical-
authority join -- exactly as it ran in production at that time, left untouched as historical
record. `20260906003840` (2026-09-06) is the later `CREATE OR REPLACE` that adds the authority join
described in section S. Both files coexist in the repo because both actually ran, in that order,
in production; the repo now reflects the true migration history rather than only the final state.

### T.5 Contract tests
New file `backend/tests/unit/db/test_market_explorer_migration_source_sync.py`, 7 focused tests
(not one-per-line): every listed version has a repo file; the original reproject migration lacks
the authority join while the hardened one has it (proving supersession without rewriting the
original); the Chansey migration is scoped to exactly the canonical UPDATE with no daily-states
reference; the batched-publication migration contains all four staged RPCs
(stage/upsert/trim/finalize) plus the trigger-bypass sync function; service-role-only
revoke/grant boundaries are present on the reproject, current-metadata-refresh, and
finalize-build functions; and the mirrored versions sort in production chronological order.
**7/7 passed.** Combined with the existing migration-contract tests
(`test_market_explorer_reproject_authority_boundary_migration.py`,
`test_market_explorer_instrument_eligibility_migration.py`) and the full Prompt 4/5 script/
service/planner/cache suite: **201 passed, 0 failed**. Broader `-k market_explorer` sweep across
`backend/tests` (billing/stripe and one unrelated logging module excluded from collection --
pre-existing, unrelated to this change): **351 passed, 0 failed**. `git diff --check` clean.

### T.6 Corrected baseline reconfirmed
Canonical Sep-3 Global All Raw / daily-states universe remains **33,955**. This session performed
no production reads or writes beyond `SELECT`s against the migration ledger; no data changed.

### T.7 Remaining Market Explorer migration-source-sync backlog
**None outstanding.** Every Market Explorer production migration identified in this investigation
(back through `20260902031454_push_down_market_explorer_daily_scope_filters`, already present) is
now mirrored in this repo across `backend/db/migrations/` and `supabase/migrations/`. Status is
updated from `PRODUCTION_MIGRATION_SOURCE_SYNC_PENDING_CHATGPT` to
**`PRODUCTION_MIGRATION_SOURCE_SYNC_COMPLETE`** for the Market Explorer domain specifically. (This
does not claim every migration in the wider production ledger -- e.g. the concurrent price-storage-
v2, collector-appeal, and budget-ranking migrations visible in the same ledger query -- is mirrored;
those are outside Market Explorer scope and were not evaluated by this session.)

### T.8 Final decision
`PRODUCTION_MIGRATION_SOURCE_SYNC_COMPLETE` for the Market Explorer domain. The database now has a
complete, byte-verified, chronologically faithful repo mirror of every migration that shaped
`reproject_pokemon_market_explorer_card_daily_states`, the canonical vintage/merge-ledger
primitives, the current-metadata projection, the Chansey duplicate_alias correction, the top-hits
rebuild hardening, the canonical market-root/publication-certification/daily-history migrations,
the batched cache-publication RPCs, and the final authority-join hardening -- in the exact order
they ran. Do not begin Prompt 6 without explicit instruction.
