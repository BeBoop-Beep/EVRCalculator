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
