# Best-Open Price Bucket 3A — Source Evidence Extension Validation (2026-09-14)

## Starting state (this session)

A prior attempt was interrupted by a rate limit before creating any branch
or touching any DB. On resuming, inspection showed the schema/RPC/service/
builder code changes described in the task were **already fully
implemented** in the working tree (not merely planned):

- `supabase/migrations/20260913220000_create_budget_product_best_open_price_store.sql`
  and its mirror `backend/db/migrations/20260913220000_create_budget_product_best_open_price_store.sql`
  were byte-identical (`diff` exit 0) and already contained every new
  column, the extended fingerprint-adjacent evidence, and the extended RPC
  cross-checks described below.
- `backend/db/services/budget_product_best_open_price_service.py` already
  populated the new fields in `build_row_payload`.
- `backend/scripts/build_budget_product_best_open_price_snapshot.py` already
  documented and relied on `content_fingerprint` (which hashes the full
  sorted row payload, so it automatically covers the new raw fields — no
  separate fingerprint-composition change was needed).
- No `docs/research/BEST_OPEN_PRICE_BUCKET3A_SOURCE_EVIDENCE_EXTENSION.md`
  existed yet.

The only defect found in the existing code was two builder unit-test
fixtures (`ENGINE_ROW` in
`backend/tests/unit/scripts/test_build_budget_product_best_open_price_snapshot.py`)
missing the new required engine-output keys
(`currentFinancialRipV4Score`, `currentCollectorAppealScore`,
`currentChaseAccessibilityRaw`, `currentChanceToRecoverCapital`,
`currentActualCommittedCapital`, `benchmarkFinancialRipV4Score`,
`benchmarkChanceToRecoverCapital`, `benchmarkActualCommittedCapital`),
causing `KeyError: 'currentActualCommittedCapital'` in
`test_dry_run_writes_local_report_and_does_not_call_rpc` and
`test_commit_calls_the_publication_rpc`. Fixed by adding the missing keys
to the fixture (test data only — no assertion or production code changed).
All 44 local tests then passed.

## New columns (on `budget_product_best_open_price_rows`)

| Column | Type | Constraint |
|---|---|---|
| `current_financial_rip_v4_score` | NUMERIC | nullable |
| `current_collector_appeal_score` | NUMERIC | nullable |
| `current_chase_accessibility_raw` | NUMERIC | nullable |
| `current_chance_to_recover_capital` | NUMERIC | nullable, CHECK 0–1 |
| `current_actual_committed_capital` | NUMERIC | NOT NULL, CHECK > 0 (named to match source `budget_product_ranking_rows.actual_committed_capital`) |
| `benchmark_financial_rip_v4_score` | NUMERIC | NOT NULL |
| `benchmark_chance_to_recover_capital` | NUMERIC | nullable, CHECK 0–1 |
| `benchmark_actual_committed_capital` | NUMERIC | NOT NULL, CHECK > 0 |

All prior columns (current Overall RIP V12 score, current rank, current
market price, `source_calculation_run_id`, benchmark_sealed_product_id,
benchmark_overall_rip_v12_score, all version identity fields) are
untouched. Source column names were confirmed against the real upstream
migration (`supabase/migrations/20260823193538_..._create_budget_normalized_product_rankings.sql`):
`financial_rip_v4_score`, `collector_appeal_score`, `chance_to_recover_capital`,
`actual_committed_capital` all exist verbatim there; `chase_accessibility_raw`
and `budget_rank_v12` come from
`backend/db/migrations/20260902010000_add_budget_product_ranking_v12_authority_columns.sql`.

## Fingerprint

`source_full_market_row_fingerprint` is populated from
`content_fingerprint()` (SHA-256 over the full row payload,
`sort_keys=True`, rows sorted by `sealed_product_id`). Because it hashes
the entire row dict rather than an enumerated field list, it already picks
up every new raw field with no code change required — confirmed by reading
`budget_product_best_open_price_service.py::content_fingerprint` and
`build_budget_product_best_open_price_snapshot.py::build_payload_from_engine_result`.

## RPC changes

`publish_budget_product_best_open_price_snapshot`'s per-row live cross-check
(step 3) now also compares `current_financial_rip_v4_score`,
`current_collector_appeal_score`, `current_chase_accessibility_raw`,
`current_chance_to_recover_capital`, `current_actual_committed_capital`
against the live `budget_product_ranking_rows` row. A new step 3b performs
the same raw-value cross-check against the live **benchmark** row
(`benchmark_overall_rip_v12_score`, `benchmark_financial_rip_v4_score`,
`benchmark_chance_to_recover_capital`, `benchmark_actual_committed_capital`).
Both follow the exact `LEFT JOIN ... WHERE x IS DISTINCT FROM y` rejection
pattern already used for `current_market_price`.

## Branch validation

- Production project confirmed via `backend/.env` `SUPABASE_URL` and
  `list_projects`: **`zwxzxuuawalvwioadhmf`** ("TheIndex").
- New ephemeral branch created: **`bucket3a-source-evidence-validation`**,
  branch id `669d39a5-e291-4772-9138-a6231d2d9835`, project ref
  **`plxaavautmsyeodfaobl`** — confirmed distinct from production via
  `execute_sql` (`current_database()`, `inet_server_addr()`, empty public
  schema at creation: 0 tables).
- Migrations applied to the branch in order: `create_budget_normalized_product_rankings`,
  `strengthen_budget_product_ranking_publication`,
  `expose_budget_product_strategy_expected_value`,
  `add_budget_product_ranking_v12_authority_columns`,
  `extend_budget_product_ranking_publication_rpc_v12_atomic`, then the
  REVISED migration under test,
  `create_budget_product_best_open_price_store` (with the new columns/RPC
  checks above). All applied successfully.
- Fixtures: one synthetic V12-authority budget-ranking snapshot (5 sealed
  products, `full_market_budget=500`, prices $100/$80/$60/$40/$20, ranks
  1–5, synthetic UUIDs, realistic Financial RIP V4 / Collector Appeal /
  Chase Accessibility raw / chance-to-recover-capital / committed-capital
  values per product), published via the real
  `publish_budget_product_ranking_snapshot` RPC with
  `ranked_under_v12_authority=true` and the exact locked identity strings.
  **All SQL ran only against `plxaavautmsyeodfaobl`. Production was never
  touched.**

## Scenario matrix (all against real branch Postgres)

| Scenario | Result |
|---|---|
| Happy path (5 rows, all new fields populated) | PASS — snapshot+5 rows persisted, latest pointer moved |
| **Wrong current Financial RIP V4 score** | PASS — rejected |
| **Wrong current Collector Appeal score** | PASS — rejected |
| **Wrong current Chase Accessibility raw** | PASS — rejected |
| **Wrong current chance-to-recover-capital** | PASS — rejected |
| **Wrong current committed capital** | PASS — rejected |
| **Wrong benchmark Financial RIP V4 score** | PASS — rejected |
| **Wrong benchmark chance-to-recover-capital** | PASS — rejected |
| **Wrong benchmark committed capital** | PASS — rejected |
| Duplicate `sealed_product_id` in payload | PASS — rejected |
| Extra product not in live cohort | PASS — rejected |
| Wrong `source_budget_snapshot_id` | PASS — rejected |
| Non-cent price (fractional cent) | PASS — rejected (CHECK constraint) |
| Invalid status/invariant (claims below-market with headroom pricing) | PASS — rejected (CHECK constraint) |
| Atomic rollback (5th row violates status CHECK mid-insert) | PASS — zero rows/snapshot persisted from that attempt |
| Identical-content idempotency (exact republish) | PASS — returned existing snapshot id, no duplicate row |
| Differing-content same-authority refusal (same identity, one row value changed) | PASS — rejected, no silent replace |
| **Source-mutability race test** (T1-bound payload published after same-id T2 republish of budget ranking) | PASS — rejected; `budget_product_best_open_price_latest` never moved |
| Latest pointer unchanged across every rejection above | PASS — verified via count query before/after |

Final state: exactly 1 snapshot, 5 rows, 1 latest-pointer row existed at
the end of the entire matrix.

## RLS / permissions (verified with real `SET ROLE`)

- `anon` `SELECT` on `budget_product_best_open_price_snapshots`: denied (42501).
- `authenticated` `SELECT` on `budget_product_best_open_price_rows`: denied (42501).
- `authenticated` `EXECUTE` on `publish_budget_product_best_open_price_snapshot`: denied (42501).
- `anon` `SELECT` on `budget_product_best_open_price_latest`: denied (42501).
- `information_schema.role_routine_grants` for the RPC: only `service_role`
  and `postgres` (owner) hold EXECUTE.

## Advisors

- Security: only `rls_enabled_no_policy` (INFO) on all six
  `budget_product_ranking_*` / `budget_product_best_open_price_*` tables —
  intended design (RLS on, zero policies, service-role-only via REVOKE/GRANT).
- Performance: pre-existing INFO items unrelated to this change (two
  unindexed `*_latest.snapshot_id` FKs, one unused index on
  `budget_product_ranking_rows`, one Auth connection-strategy note).
  Nothing attributable to the Best-Open-Price schema extension.

## Local test results

`backend/tests/unit/db/test_budget_product_best_open_price_migration_sql.py`
+ `backend/tests/unit/db/services/test_budget_product_best_open_price_service.py`
+ `backend/tests/unit/scripts/test_build_budget_product_best_open_price_snapshot.py`:
**44/44 passing** after fixing the two builder-test fixtures described above.

## Bug found + fixed

Two test fixtures in
`backend/tests/unit/scripts/test_build_budget_product_best_open_price_snapshot.py`
(`ENGINE_ROW`, used by `test_dry_run_writes_local_report_and_does_not_call_rpc`
and `test_commit_calls_the_publication_rpc`) predated the new required
engine-output fields and raised `KeyError`. Fixed by adding the eight new
keys with realistic synthetic values to the fixture. No assertion or
non-test code was changed.

## Cleanup

Branch `bucket3a-source-evidence-validation`
(`669d39a5-e291-4772-9138-a6231d2d9835`, project ref
`plxaavautmsyeodfaobl`) deleted via `delete_branch`; confirmed via
`list_branches` on the parent project — only the implicit `main` branch
record remains. Production project `zwxzxuuawalvwioadhmf` was never
touched by any mutating call in this session.
