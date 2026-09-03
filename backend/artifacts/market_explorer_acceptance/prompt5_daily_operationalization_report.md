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

## O. Final decision
**PROMPT5_REPO_READY.** The daily-operationalization workflow (normal-day append -> reconcile ->
coverage advance -> dynamic maintained-cache prewarm, plus a separate historical-repair path) is
implemented as `backend/scripts/run_market_explorer_daily_publication.py`, reuses the existing
Prompt 3/4 tooling (`publish_market_explorer_daily_projection.run_publish`,
`activate_or_repair_coverage`, the vintage repair script's
`invalidate_pokemon_market_explorer_query_cache_scoped`/`reproject_pokemon_market_explorer_card_daily_states`
RPC contracts, and the Prompt 4 maintained-cache builder pattern) rather than duplicating it,
preserves the 165-set `resolve_tracked_set_ids` intersection and same-day projection routing
exactly as-is (no diff against that file, its own test suite still green), and is covered by 24
new focused mocked-DB tests plus 112 passing pre-existing tests in the same domain (136 total, 0
failures). This is a repo-readiness decision only — it does **not** constitute production
operationalization acceptance; section N above is the explicit plan for a future session to run
that live.
