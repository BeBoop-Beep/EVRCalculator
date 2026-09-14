# Best-Open Price Bucket 3A — Remote Ephemeral-Branch RPC Validation (2026-09-14)

## Environment

- Production project: `zwxzxuuawalvwioadhmf` ("TheIndex", confirmed via `.env`
  `SUPABASE_URL` and `list_projects`).
- Ephemeral branch: project ref `gzhpfshwmflryzmynggl` (branch id
  `d3e8a1a3-e161-4f27-9457-30b7f3440f2d`), created via `create_branch` off
  `zwxzxuuawalvwioadhmf`. Confirmed distinct project ref before any SQL ran
  (`get_project` on the branch 404'd — expected, it's a separate managed
  project — and `execute_sql` on the branch returned its own
  `current_database()`/server address, distinct from production).
- **All SQL in this validation ran only against `gzhpfshwmflryzmynggl`.**
  Production was never mutated.
- The branch came up with an **empty public schema** (0 tables, 0
  migrations) — branching here does not clone production schema/data, only
  provisions a fresh Postgres. All prerequisite migrations were therefore
  applied to the branch first: `create_budget_normalized_product_rankings`,
  `strengthen_budget_product_ranking_publication`,
  `expose_budget_product_strategy_expected_value`,
  `add_budget_product_ranking_v12_authority_columns` (backend/db/migrations
  only — applied here as a throwaway-branch prerequisite, not to any
  persistent environment), `extend_budget_product_ranking_publication_rpc_v12_atomic`,
  then the migration under test,
  `20260913220000_create_budget_product_best_open_price_store.sql`.
- Fixtures: one synthetic V12-authority budget-ranking snapshot (5 sealed
  products, `full_market_budget=500`, prices $100/$80/$60/$40/$20, ranks
  1-5, all synthetic UUIDs), published via the real
  `publish_budget_product_ranking_snapshot` RPC with
  `ranked_under_v12_authority=true` and the exact locked V12/Financial/
  Collector-Appeal/Chase-Accessibility identity strings.

## Real bugs found and fixed (both `supabase/migrations/...` and
`backend/db/migrations/...` kept identical)

1. **Ambiguous column references** in the live-source-verification query
   (`market_date`, `ranking_method_version`, `allocation_method_version`
   exist on both joined tables) — every call to the RPC failed with
   Postgres error 42702 before ever reaching any business validation. Fixed
   by qualifying all three with `s.`.
2. **`search_path` excluded `extensions`**, where Supabase installs
   `pgcrypto` by default — `digest()` (used for the content fingerprint)
   failed with 42883 on every real Supabase-hosted project, including
   production, exactly as deployed. Fixed by adding `extensions` to
   `SET search_path = public, extensions`.
3. **`source_calculation_run_id` and `chase_accessibility_version`/
   `chase_accessibility_transform_version` were stored but never
   cross-checked** against the live ranking source, despite being named as
   required-reject cases in the validation spec. Added
   `source_calculation_run_id` to the per-row `LEFT JOIN` cross-check and
   `chase_accessibility_version`/`chase_accessibility_transform_version` to
   the snapshot-level binding check.

All three fixes were applied to the branch and the affected scenarios
re-run afterward to confirm.

## Scope note (not a bug, not fixed)

"Wrong Financial RIP v4 score", "wrong Collector Appeal score", and "wrong
Chase Accessibility raw input" as literal per-row numeric fields do not
exist in this migration's row schema — `budget_product_best_open_price_rows`
only stores `current_overall_rip_v12_score` (the composite) at row
granularity; per-model raw components are not persisted here. Only the
*version-identity strings* for these models are stored/checked (at the
snapshot level, now all cross-checked per fix #3 above). Redesigning the
row schema to carry raw per-model scores is out of scope for this
migration's frozen contract and was not attempted.

## Scenario matrix (all against the real branch Postgres, genuine SQL calls)

| Scenario | Result |
|---|---|
| Happy path (valid payload) | PASS — snapshot+4 rows persisted, latest pointer moved |
| Duplicate product in payload | PASS — rejected |
| Missing product vs. live cohort | PASS — rejected (row-count/resolved_count reconciliation) |
| Extra product not in live cohort | PASS — rejected |
| Wrong `source_budget_snapshot_id` | PASS — rejected |
| Wrong `source_budget_published_at` (same id) | PASS — rejected |
| Wrong cohort/source fingerprint | PASS — rejected |
| Wrong `source_calculation_run_id` | PASS — rejected (after fix #3) |
| Wrong current market price | PASS — rejected |
| Wrong V12 rank | PASS — rejected |
| Wrong V12 score | PASS — rejected |
| Wrong Financial RIP v4 identity | PASS — rejected |
| Wrong Collector Appeal identity | PASS — rejected |
| Wrong Chase Accessibility identity | PASS — rejected (after fix #3) |
| Wrong Full Market budget | PASS — rejected |
| Non-cent price (isolated, fresh identity) | PASS — rejected by CHECK constraint |
| Invalid status/invariant (isolated, fresh identity) | PASS — rejected by CHECK constraint |
| Atomic rollback (forced mid-payload CHECK failure) | PASS — zero rows/snapshot persisted from that attempt |
| Latest pointer unchanged across all failures | PASS |
| Identical-content idempotency (republish same payload) | PASS — no duplicate snapshot, no-op return |
| Differing-content same-authority refusal | PASS — rejected, no silent replace |
| **Source-mutability race test** (T1-bound payload after same-id T2 republish) | PASS — rejected; `budget_product_best_open_price_latest` never moved |

Final state check: exactly 1 snapshot row, 4 row records, 1 `latest` row
existed at the end of the entire matrix — confirming no rejected scenario
ever left partial state.

## RLS / permissions (verified with real `SET ROLE`, not inferred)

- `anon` `SELECT` on `budget_product_best_open_price_snapshots`: denied
  (`42501 permission denied`).
- `anon` `SELECT` on `budget_product_best_open_price_latest`: denied.
- `authenticated` `SELECT` on `budget_product_best_open_price_rows`: denied.
- `authenticated` `EXECUTE` on `publish_budget_product_best_open_price_snapshot`:
  denied (`42501 permission denied for function`).
- `information_schema.role_routine_grants` for the RPC: only `service_role`
  and `postgres` (owner) — no `anon`/`authenticated` grants.

## Advisors

- Security: only `rls_enabled_no_policy` (INFO) on the six
  `budget_product_ranking_*`/`budget_product_best_open_price_*` tables —
  this is the intended design (RLS enabled, zero policies, service-role-only
  via REVOKE/GRANT), not a defect.
- Performance: pre-existing INFO-level items unrelated to this migration
  (two unindexed FKs on `*_latest.snapshot_id`, one unused index on
  `budget_product_ranking_rows`, an Auth connection-strategy note, and a
  no-PK note on my own scratch `bop_test_results` table). Nothing
  attributable to the Best-Open-Price migration itself beyond the
  already-fixed items above.

## Step 10 (Python service/builder tests against the branch)

Not wired in this pass. Pointing `backend/db/services/budget_product_best_open_price_service.py`
/ `backend/scripts/build_budget_product_best_open_price_snapshot.py` at the
ephemeral branch would require a `DATABASE_URL`/service-role-key override
not established as a convention in this repo's existing test suite (the
prior local-Postgres attempt found the whole suite mocks the Supabase
client rather than connecting live). Not attempted here to stay within
scope; the RPC itself was validated directly and exhaustively above.

## Cleanup

- Branch `bucket3a-best-open-price-validation`
  (`d3e8a1a3-e161-4f27-9457-30b7f3440f2d`, project ref
  `gzhpfshwmflryzmynggl`) deleted via `delete_branch`; confirmed via
  `list_branches` on the parent project — only the implicit `main` branch
  record remains.
- Production project `zwxzxuuawalvwioadhmf` was never touched by any
  mutating call in this session.
