# Best-Open Price Bucket 3A — PRIVATE Durable Persistence + Atomic Publication

Scope: persistence and atomic publication ONLY. No frontend, no public API,
no entitlement surface, no cron orchestration. Nothing applied to production.

## Migration file(s) and SQL object list

`backend/db/migrations/20260913220000_create_budget_product_best_open_price_store.sql`,
mirrored byte-for-byte at
`supabase/migrations/20260913220000_create_budget_product_best_open_price_store.sql`.

Objects created:
- `public.budget_product_best_open_price_snapshots` — one row per publication.
- `public.budget_product_best_open_price_rows` — one row per resolved product per snapshot.
- `public.budget_product_best_open_price_latest` — one row per `best_open_price_method_version`, pointing at the current snapshot.
- `public.publish_budget_product_best_open_price_snapshot(p_snapshot JSONB, p_rows JSONB) RETURNS UUID` — the sole write path, `SECURITY DEFINER`, `SET search_path = public`, `service_role`-only `EXECUTE`.
- Index `idx_budget_product_best_open_price_rows_snapshot`.

## Schema summary

**Snapshots** carry full source-identity binding (`source_budget_snapshot_id`,
`source_budget_published_at`, `source_market_date`, `source_cohort_fingerprint`,
`source_full_market_row_fingerprint`, `source_full_market_budget`,
`source_eligible_cohort_count`), every model-authority version field
(ranking/allocation/comparison-scope/financial-RIP/overall-RIP-V12/collector-
appeal/chase-accessibility/chase-accessibility-transform/best-open-price
method), and diagnostics (`resolved_count`, `unresolved_count`,
`runtime_seconds`, `diagnostics_json` — which the RPC augments with a
`content_fingerprint` for idempotency/non-determinism detection).

**Rows** carry identity (`sealed_product_id`, `set_id`, `product_family`,
`source_calculation_run_id`), current source state at computation time
(`current_market_price`, `current_quantity`, `current_budget_rank`,
`current_overall_rip_v12_score`), the locked status taxonomy, threshold
fields (`best_open_price`, `threshold_quantity`, `price_gap_dollars`,
`price_gap_percent`), benchmark fields, and light search diagnostics only
(`candidate_price_evaluations`, `bracket_expansions`, `bracket_refinements`,
`monotonicity_fallback_count`, `search_wall_seconds`) — no per-candidate
probe dump is persisted.

All money fields (`current_market_price`, `best_open_price`) are
`NUMERIC` with `CHECK (... = round(..., 2))`, rejecting fractional cents at
the DB level. The status taxonomy is locked via `CHECK (status IN
('resolved_below_market', 'current_number_one_with_headroom',
'resolved_at_market'))`, with a second `CHECK` enforcing the per-status
price/gap invariant (headroom is `best_open_price >= current_market_price`
with `price_gap_dollars <= 0` — never treated as a discount).

## RPC contract

One PL/pgSQL function, one transaction, in order:
1. Reject non-array or empty `p_rows`; reject duplicate `sealed_product_id`.
2. Reject if row count ≠ `resolved_count`.
3. Re-read the LIVE `budget_product_ranking_latest` → `budget_product_ranking_snapshots`
   for the payload's `(ranking_method_version, allocation_method_version)` and
   compare every source-identity/version field against the payload exactly —
   any mismatch aborts with "stale or non-deterministic input".
4. Cross-check **every row** directly against the live
   `budget_product_ranking_rows` (`product_market_price`, `quantity`,
   `budget_rank_v12`, `overall_rip_v12_score`, `set_id`) — not just the
   snapshot-level fingerprint.
5. Verify `resolved_count + unresolved_count` equals the live eligible cohort count.
6. Defense-in-depth cent-precision check over the JSON payload (schema `CHECK`
   is the primary guard; this catches it before insert).
7. Idempotency: if a snapshot already exists for the same
   `(source_budget_snapshot_id, source_budget_published_at,
   best_open_price_method_version)`, compare content fingerprints — identical
   content returns the existing id (no-op); differing content raises loudly
   ("refusing silent replace") rather than overwriting.
8. Insert snapshot, insert rows, reconcile persisted row count, move the
   `_latest` pointer (`ON CONFLICT ... DO UPDATE`).

Any `RAISE EXCEPTION` at any step rolls back the whole transaction — the
`_latest` pointer never moves on a failed publish, by ordinary Postgres
transaction semantics (the pointer UPSERT textually follows every validation
step, and both live inside the same `BEGIN … COMMIT`).

## Source-binding / race-protection design

The non-negotiable race is: engine binds to budget-ranking source `S` at
`T1`; if `S` is republished under the same id with a new `published_at` at
`T2` before the ~65-minute engine run finishes, a publish built from the
`T1` snapshot must fail, not silently attach to `T2`'s live data. This is
enforced twice:
- **RPC-side** (step 3 above): the RPC always re-reads the CURRENT live
  source at publish time and compares it to the payload's claimed source
  identity, independent of when the payload was built.
- **Builder-side** (`backend/scripts/build_budget_product_best_open_price_snapshot.py::verify_no_drift`):
  re-reads the live source identity immediately before calling the RPC and
  aborts locally with a descriptive `RuntimeError` if it drifted — a
  fail-fast layer in front of the authoritative DB-side check.

Neither layer holds a DB transaction open for the long computation: the
`FileLock`-based singleton lock (reused from
`backend/scripts/run_market_explorer_maintained_cache_prewarm.py`) only
prevents two builder invocations from running concurrently (`already_running`),
and is released in a `finally` block.

## Security audit summary

- RLS `ENABLE`d on all three tables, with **no** `CREATE POLICY` anywhere in
  the migration — with RLS on and zero policies, only roles that bypass RLS
  (`service_role`, table owner) can touch the tables at all.
- Explicit `REVOKE ALL … FROM PUBLIC, anon, authenticated` on all three
  tables, matching the repo's Budget Ranking convention.
- The RPC is `SECURITY DEFINER` with `SET search_path = public` (no search-path
  injection surface), `EXECUTE` revoked from `PUBLIC, anon, authenticated`,
  granted only to `service_role`.
- No new column, table, or function name appears in any file outside
  `backend/db/migrations/`, `supabase/migrations/`,
  `backend/db/services/budget_product_best_open_price_service.py`,
  `backend/scripts/build_budget_product_best_open_price_snapshot.py`, and
  their tests/this doc — confirmed by grep; no frontend, public API,
  `RankingsProductLensClient`, product detail page, homepage, or video export
  file was touched.

## Dry-run parity result

**Not run against production data.** This environment has no configured
read-only Supabase/production credentials available to this session (no
`SUPABASE_URL`/service-role key resolvable, and the MCP Supabase connector
tools require interactive OAuth authorization not available in this
non-interactive session). Per the task's explicit instruction, this
limitation is stated plainly rather than fabricating a dry-run result. The
builder (`build_budget_product_best_open_price_snapshot.py::run`) is fully
implemented and unit-tested against a fake client covering the same control
flow a real dry run would exercise (source resolution, already-published
skip, drift abort, local JSON report), but no live 138-product reproduction
of the Bucket 2.x reference cohort was executed in this session.

## Test counts and results

- New migration SQL contract tests:
  `backend/tests/unit/db/test_budget_product_best_open_price_migration_sql.py`
  — 22 tests, all passing (string/regex contract against the executable SQL
  text, mirroring the repo's existing `test_budget_product_ranking_migration_sql.py`
  convention — this repo has no live-DB migration test harness; RPC behavior
  is asserted via SQL body text order/content, e.g.
  `test_rpc_moves_latest_pointer_only_after_all_validation`).
- New service unit tests:
  `backend/tests/unit/db/services/test_budget_product_best_open_price_service.py`
  — 10 tests, all passing (payload builders, content fingerprinting,
  staleness rule: exact match → available; drifted `published_at`/
  `market_date`/`cohort_fingerprint`/live-snapshot-id → stale; no
  publication/no live source/incomplete rows → unavailable with distinct
  reasons).
- New builder unit tests:
  `backend/tests/unit/scripts/test_build_budget_product_best_open_price_snapshot.py`
  — 8 tests, all passing (already_running, already_published skip, cohort
  mismatch rejection, dry-run report with no RPC call, commit calls RPC,
  lock released on exception, drift abort).
- **Total new tests: 40/40 passing** (`python -m pytest` on the three files above).
- Existing Best-Open Price / Budget Ranking regression suite (121 tests
  across `backend/tests/unit/db` and `backend/tests/unit/scripts` matching
  `budget_product_ranking` or `best_open_price`): **121/121 passing**,
  unaffected by this change. (Seven unrelated pre-existing test files fail
  to *collect* in this environment due to a missing `jwt` module and a
  pre-existing billing-service `TypeError` — confirmed unrelated to this
  work and excluded via `--ignore`.)

RPC happy-path/rejection integration tests against a **real** Postgres
instance (duplicate/missing/extra rows, wrong snapshot id/published_at/
fingerprint/price/rank/score/full-market-budget/method version, non-cent
price, status-invariant violation, atomic rollback, latest-pointer-does-
not-move, idempotent retry, non-deterministic refusal, and the source-
mutability race test) were **not executed** — this repository has no local
Supabase CLI / Postgres test-DB harness wired into its test suite (existing
migration tests are all SQL-text contract tests, not live-DB tests), and no
such harness was available to stand up in this session. The RPC's SQL was
authored to satisfy every one of these cases and each corresponding SQL
branch is covered by a text-contract test above, but this is not equivalent
to executing the RPC.

## Expected production row counts

One row in `_snapshots` and one row in `_latest` per publish. Approximately
138 rows in `_rows` per snapshot, matching the current validated Full Market
eligible cohort size (Bucket 2.x, 138/138). This count is bound to
`source_eligible_cohort_count` at publish time, not hard-coded, so it moves
automatically if the live Full Market cohort size changes.

## Rollback considerations

The migration is additive only (three new tables + one new function); it
touches no existing table, column, or function. Rollback is a plain
`DROP FUNCTION` / `DROP TABLE` in reverse dependency order (`_rows` before
`_snapshots` via the FK, `_latest` independently) — no data migration or
backfill exists to reverse. Nothing in this migration has been applied to
production; it exists only as staged, tested SQL in this branch.

## Bucket 3B canary step list (staged, NOT executed)

1. Obtain read-only production Supabase credentials via the repo's existing
   script convention and re-run the dry-run builder to reproduce the 138-
   product Bucket 2.x reference cohort exactly (status/threshold/benchmark
   parity, stable content fingerprint across two dry runs).
2. Apply migration `20260913220000_create_budget_product_best_open_price_store.sql`
   to production via the standard Supabase migration path (outside this
   session's scope).
3. Run the builder with `--commit` once, by hand, under human supervision —
   confirm exactly one snapshot row, `resolved_count` rows, and the
   `_latest` pointer created.
4. Re-run the builder immediately after with `--commit` again against the
   same unchanged source — confirm it returns `already_published` (idempotent
   skip), not a second snapshot.
5. Manually verify `load_best_open_price_ranking` reports `available: true`
   with the correct row count via a one-off script (no API/frontend wiring).
6. Manually trigger a budget-ranking republish (or wait for the next
   scheduled one) and confirm `load_best_open_price_ranking` flips to
   `available: false, reason: "stale_source_publication"` without any code
   change — proving the staleness rule holds against a real republish, not
   just the unit-test fake.
7. Only after all of the above hold for at least one full production
   publish cycle: propose (in a separate change) any cron/recurring
   orchestration, and only then consider any public-facing exposure — both
   explicitly out of scope for Bucket 3A and 3B.
