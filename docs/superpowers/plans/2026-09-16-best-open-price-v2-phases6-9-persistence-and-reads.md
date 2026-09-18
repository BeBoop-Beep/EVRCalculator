# Best-Open Price V2 — Phases 6-9 Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Add an additive DB migration for the V2 dual-threshold row contract, a hardened RPC that dispatches between historical V1 semantics (unchanged) and new V2 semantics (dual RIP + Financial evidence, both benchmarks independently validated, both threshold-evidence sets required), extend the Python persistence service with an explicit V2 payload builder (no scoring, pure projection), make the private/public read services method-version-aware so a V2 row's `bestOpenPrice`/`financialBestOpenPrice` are both exposed without fabricating data for V1 rows, and add the full migration/RPC/service contract test matrix — including a disposable-Postgres integration suite following this repo's existing, working CI pattern.

**Architecture:** ONE new additive migration (mirrored byte-for-byte in `backend/db/migrations/` and `supabase/migrations/`) adds nullable V2 columns to `budget_product_best_open_price_rows` with CHECK constraints that tolerate NULL (historical V1 rows), then `CREATE OR REPLACE`s `public.publish_budget_product_best_open_price_snapshot(JSONB, JSONB)` so it branches internally on `p_snapshot->>'best_open_price_method_version'`: the V1 literal (`'budget_product_best_open_price_full_market_v1'`) runs the EXISTING validation body verbatim (copied inside an `IF` branch, not refactored, to minimize risk of altering historical behavior), and the new V2 literal (`'budget_product_best_open_price_full_market_v2_dual_financial_v4_overall_v12'`) runs a parallel validation body that additionally requires and cross-checks every Financial-axis field, both independent benchmarks, and both threshold-evidence sets. `backend/db/services/budget_product_best_open_price_service.py` gains `build_v2_row_payload(...)` alongside the untouched `build_row_payload(...)` (V1) — no ambiguous dual-purpose builder. Read services (`load_best_open_price_ranking`/`load_best_open_price_product`, `public_overall_product_rankings_service.py`, `pokemon_sealed_product_detail_service.py`) become explicitly method-version-aware, so a V1 row is never interpreted as V2 and a V1 row's response never fabricates `financialBestOpenPrice`. Testing follows the existing, already-working two-tier pattern this repo uses for the V1 RPC: pure-Python unit tests with a fake/mocked Supabase client for payload shaping and read-service logic, plus a disposable-Postgres integration test file (`backend/tests/integration/test_best_open_publication_v2_postgres.py`) that is skipped locally without a real Postgres DSN and runs for real only in the `postgres-integration` CI job — this environment has no Docker/local Postgres, so this plan's local test run explicitly cannot execute those RPC-level tests; they are authored, mirror-checksummed, and CI-gated exactly like the V1 file they extend, and their real execution is deferred to CI (or to whoever runs this branch's CI), not silently skipped or faked.

**Tech Stack:** PostgreSQL/PL/pgSQL (migration + RPC), Python 3 (service/read layers), pytest, psycopg (integration tests, CI-only in this environment).

**Spec:** No separate spec file — this plan implements Phases 6-9 of the "BEST-OPEN PRICE V2" task instructions supplied directly in conversation. Phases 0-5 are complete and on `develop` (commit `b55f4e07`). Phase 10 (read-only production-source validation) is explicitly out of scope here.

## Global Constraints

- Do NOT apply any migration to production. Do NOT publish any V2 (or V1) snapshot. Do NOT run the final 138-product cohort validation. Do NOT redesign frontend UI. Do NOT change Financial RIP V4, Overall RIP V12, or exact-search mathematics. Do NOT change or rewrite V1 historical rows. Do NOT change the V1 method identity string.
- The new migration must be purely additive: new nullable columns, new constraints that tolerate NULL, `CREATE OR REPLACE FUNCTION` — never an `ALTER TABLE ... DROP`/`ALTER COLUMN ... SET NOT NULL` on any existing column, never editing the two already-applied migration files (`20260914184759_...sql`, `20260914225000_...sql`).
- V1's existing RPC validation body (all ~15 steps: object-type guards, version-literal pin, locking sequence, live-authority cross-checks, cohort completeness, numeric finiteness, arithmetic/direction checks, current-row cross-checks, benchmark cross-checks, cent-precision, idempotency fingerprint, insert, post-insert count check, `latest` upsert) must be preserved byte-for-byte inside its own branch of the replaced function — copy it, do not refactor it, so a diff against the V1 branch's SQL text against the current live function body (minus the branch wrapper) shows zero semantic change.
- Do NOT duplicate the generic RIP price into separate `rip_*` money DB columns — `status`/`best_open_price`/`threshold_quantity`/`price_gap_dollars`/`price_gap_percent`/`benchmark_*` remain the persisted RIP threshold at the DB layer; explicit `rip*` aliasing is a Python/service-layer concern only.
- Do NOT add a SQL NUMERIC equality requiring `threshold_actual_committed_capital = threshold_quantity * best_open_price` — Python's `quantity * float(price)` operation order is the scoring authority, and reproducing it in SQL NUMERIC arithmetic would reject legitimate IEEE-754-tailed values (this is the exact defect Phase 0 fixed in the Python validator; a tiny explicit economic-reconciliation tolerance is the correct SQL-side check for THRESHOLD evidence). For CURRENT source evidence, direct equality against the live `budget_product_ranking_rows.actual_committed_capital` remains the authority — never re-derived.
- Git workflow authority (per explicit user instruction, overrides any skill/plan default): build directly on `develop`. No feature branch, no PR. Work only in `D:\EVRCalculator\.claude\worktrees\best-open-price-v2`, kept detached at the current `origin/develop` head (expected: `b55f4e07` at plan-authoring time). For each task's reviewed checkpoint: `git fetch origin develop`, confirm no unexpected advance (reconcile if it has), tests/review already green, commit, `git push origin HEAD:develop`. Never force-push.
- **Known environment limitation, acknowledged up front:** this worktree has no Docker, no local PostgreSQL, and no Supabase CLI (verified: `which docker/pg_ctl/initdb/postgres/supabase` all return nothing). The existing V1 RPC's own integration test (`backend/tests/integration/test_best_open_publication_postgres.py`) is `pytest.mark.skipif(not os.getenv('BEST_OPEN_TEST_DATABASE_URL'))` — it has NEVER been runnable in this local environment either; it runs for real only in `.github/workflows/best-open-price-guardrails.yml`'s `postgres-integration` job (a real `postgres:17` service container). This plan follows that exact, already-working, already-precedented pattern for the new V2 integration test — write it, gate it identically, verify it collects and skips cleanly locally, and report honestly that its real RPC-level assertions were not executed against a real Postgres in this session (no Docker available), exactly as would be true for any local run of the existing V1 file today. This is not an improvised workaround; it is the established convention this exact test type already uses in this repo.

---

### Task 1: Additive migration — V2 schema columns, constraints, and RPC dispatch

**Files:**
- Create: `supabase/migrations/<TIMESTAMP>_add_best_open_price_v2_dual_threshold.sql` (timestamp later than `20260915233000`, format `YYYYMMDDHHMMSS_snake_case.sql`)
- Create (byte-identical mirror): `backend/db/migrations/<TIMESTAMP>_add_best_open_price_v2_dual_threshold.sql`
- Test: `backend/tests/unit/db/test_best_open_price_v2_migration_sql.py` (new file, following the exact pattern of `backend/tests/unit/db/test_budget_product_best_open_price_migration_sql.py`)

**Interfaces:**
- Produces: 18 new nullable columns on `public.budget_product_best_open_price_rows` (listed in Phase 6-A below), 3 new CHECK constraints that tolerate NULL, and a `CREATE OR REPLACE FUNCTION public.publish_budget_product_best_open_price_snapshot(p_snapshot JSONB, p_rows JSONB) RETURNS UUID` whose top-level body is `IF (p_snapshot->>'best_open_price_method_version') = 'budget_product_best_open_price_full_market_v1' THEN <verbatim copy of the current hardened V1 body> ELSIF (...) = 'budget_product_best_open_price_full_market_v2_dual_financial_v4_overall_v12' THEN <new V2 body> ELSE RAISE EXCEPTION 'unsupported Best-Open Price method version'; END IF;`.
- Consumes: the exact current text of `supabase/migrations/20260914225000_harden_best_open_publication_review.sql`'s RPC function body (read it directly — do not rely on a paraphrase) as the literal V1 branch content.

- [ ] **Step 1: Read the exact current schema and RPC**

Read `supabase/migrations/20260914184759_create_budget_product_best_open_price_store.sql` and `supabase/migrations/20260914225000_harden_best_open_publication_review.sql` in full. Confirm the exact column list of `budget_product_best_open_price_rows`, the exact current RPC function signature/`SET search_path`, and the exact current validation body text (all ~15 steps) — you will copy this body verbatim into the V1 branch of the replaced function. Do not paraphrase or "clean up" any part of it.

- [ ] **Step 2: Write the schema-additions portion (Phase 6-A/B)**

```sql
-- Best-Open Price V2: additive dual-threshold columns. Historical V1 rows
-- remain valid with every column below NULL. No backfill required or
-- performed. See supabase/migrations/20260914184759_..._store.sql and
-- 20260914225000_harden_best_open_publication_review.sql for the V1
-- authority this extends.

ALTER TABLE public.budget_product_best_open_price_rows
  ADD COLUMN current_financial_only_rank INTEGER
    CHECK (current_financial_only_rank IS NULL OR current_financial_only_rank >= 1),

  ADD COLUMN financial_status TEXT
    CHECK (financial_status IS NULL OR financial_status IN (
      'resolved_below_market', 'current_number_one_with_headroom', 'resolved_at_market'
    )),
  ADD COLUMN financial_best_open_price NUMERIC
    CHECK (financial_best_open_price IS NULL OR (
      financial_best_open_price > 0
      AND financial_best_open_price < 'Infinity'::NUMERIC
      AND financial_best_open_price = round(financial_best_open_price, 2)
    )),
  ADD COLUMN financial_threshold_quantity INTEGER
    CHECK (financial_threshold_quantity IS NULL OR financial_threshold_quantity > 0),
  ADD COLUMN financial_price_gap_dollars NUMERIC,
  ADD COLUMN financial_price_gap_percent NUMERIC,

  ADD COLUMN financial_benchmark_sealed_product_id UUID,
  ADD COLUMN financial_benchmark_financial_rip_v4_score NUMERIC,
  ADD COLUMN financial_benchmark_overall_rip_v12_score NUMERIC,

  ADD COLUMN threshold_financial_rip_v4_score NUMERIC,
  ADD COLUMN threshold_overall_rip_v12_score NUMERIC,
  ADD COLUMN threshold_chance_to_recover_capital NUMERIC
    CHECK (threshold_chance_to_recover_capital IS NULL OR (
      threshold_chance_to_recover_capital >= 0 AND threshold_chance_to_recover_capital <= 1
    )),
  ADD COLUMN threshold_actual_committed_capital NUMERIC
    CHECK (threshold_actual_committed_capital IS NULL OR (
      threshold_actual_committed_capital > 0
      AND threshold_actual_committed_capital < 'Infinity'::NUMERIC
    )),

  ADD COLUMN financial_threshold_financial_rip_v4_score NUMERIC,
  ADD COLUMN financial_threshold_overall_rip_v12_score NUMERIC,
  ADD COLUMN financial_threshold_chance_to_recover_capital NUMERIC
    CHECK (financial_threshold_chance_to_recover_capital IS NULL OR (
      financial_threshold_chance_to_recover_capital >= 0
      AND financial_threshold_chance_to_recover_capital <= 1
    )),
  ADD COLUMN financial_threshold_actual_committed_capital NUMERIC
    CHECK (financial_threshold_actual_committed_capital IS NULL OR (
      financial_threshold_actual_committed_capital > 0
      AND financial_threshold_actual_committed_capital < 'Infinity'::NUMERIC
    ));

ALTER TABLE public.budget_product_best_open_price_rows
  ADD CONSTRAINT budget_best_open_v2_gap_arithmetic
  CHECK (
    financial_best_open_price IS NULL
    OR (
      financial_price_gap_dollars = current_market_price - financial_best_open_price
      AND financial_price_gap_percent IS NOT NULL
      AND abs(financial_price_gap_percent - financial_price_gap_dollars / NULLIF(current_market_price, 0)) <= 0.000000000001
    )
  ),
  ADD CONSTRAINT budget_best_open_v2_direction
  CHECK (
    financial_best_open_price IS NULL
    OR current_financial_only_rank IS NULL
    OR (current_financial_only_rank = 1 AND financial_best_open_price >= current_market_price)
    OR (current_financial_only_rank <> 1 AND financial_best_open_price <= current_market_price)
  ),
  ADD CONSTRAINT budget_best_open_v2_not_self_financial_benchmark
  CHECK (financial_benchmark_sealed_product_id IS NULL OR sealed_product_id <> financial_benchmark_sealed_product_id);
```

Note: the `budget_best_open_v2_direction` constraint's rank-1 branch reads `financial_best_open_price >= current_market_price` (a rank-1/leader can only improve or hold, never worsen) — mirror the EXACT direction convention the existing `status`-derived V1 rows use (re-check against the V1 CHECK constraint text you read in Step 1; if V1's convention differs in sign/inclusivity from what's written here, match V1's convention exactly rather than this plan's guess).

- [ ] **Step 3: Write the RPC-replacement portion (Phase 7-B/C/D/E/F/G/H)**

Structure the `CREATE OR REPLACE FUNCTION` as:

```sql
CREATE OR REPLACE FUNCTION public.publish_budget_product_best_open_price_snapshot(
    p_snapshot JSONB, p_rows JSONB
) RETURNS UUID
LANGUAGE plpgsql SECURITY DEFINER SET search_path = pg_catalog, public, extensions, pg_temp
AS $$
DECLARE
    v_method_version TEXT := p_snapshot->>'best_open_price_method_version';
    -- ... (all V1 DECLARE variables, verbatim from the current function)
BEGIN
    IF v_method_version = 'budget_product_best_open_price_full_market_v1' THEN
        -- VERBATIM COPY of the entire current hardened V1 body (every step
        -- from Step 1's reading), completely unchanged. Do not touch a
        -- single condition, message, or column reference in this branch.
        ...
    ELSIF v_method_version = 'budget_product_best_open_price_full_market_v2_dual_financial_v4_overall_v12' THEN
        -- New V2 body (Step 4 below).
        ...
    ELSE
        RAISE EXCEPTION 'unsupported Best-Open Price method version';
    END IF;
END;
$$;
```

You will likely need to move ALL variable declarations from both branches into one shared `DECLARE` block (PL/pgSQL doesn't support per-branch `DECLARE`), renaming any that collide between the V1 and V2 bodies (e.g., if both need `v_live_snapshot`, either share it if the shape is compatible or suffix the V2 copy `v_live_snapshot_v2`). Keep the V1 branch's variable NAMES and LOGIC unchanged internally — only rename where a true naming collision with new V2-only variables would otherwise occur.

- [ ] **Step 4: Write the V2 validation body**

Inside the `ELSIF` branch, implement, in this order (mirroring the V1 body's structure step-for-step but for the dual contract):

1. All of V1's structural guards (object-type checks, non-empty rows, no-duplicate-`sealed_product_id`, row-count-matches-`resolved_count`) — identical logic, reusable if you extracted them before the branch point (they don't depend on method version) — or duplicated into the V2 branch if simpler; your judgment, as long as behavior for each version is unaffected by the other.
2. Live-authority lookup and locking sequence — identical to V1 (same `FOR UPDATE` locking on the source snapshot, same re-check of the `latest` pointer) since the underlying Budget Ranking authority contract doesn't change between V1 and V2 Best-Open methods.
3. **New:** require `current_financial_only_rank IS NOT NULL` on every row, and cross-check it against the live `budget_product_ranking_rows.financial_only_rank` for that `(sealed_product_id, budget_type='full_market', target_budget=v_live_snapshot.full_market_budget)` — same join pattern V1 already uses for `current_budget_rank`.
4. Row cross-check (current side): everything V1 checks, PLUS `financial_only_rank` (added in step 3).
5. RIP benchmark cross-check: identical to V1's benchmark cross-check (same fields, same rank-1-vs-rank-2 canonical-identity check on `budget_rank_v12`), reading from `benchmark_sealed_product_id`/`benchmark_overall_rip_v12_score`/`benchmark_financial_rip_v4_score` (the EXISTING generic columns, which continue to mean the RIP benchmark per this plan's constraint).
6. **New:** Financial benchmark cross-check, structurally identical to the RIP benchmark cross-check but keyed on `financial_benchmark_sealed_product_id`, requiring the live benchmark row's `financial_only_rank` to equal `CASE WHEN (row->>'current_financial_only_rank')::INTEGER = 1 THEN 2 ELSE 1 END`, and requiring `financial_benchmark_financial_rip_v4_score` to match the live benchmark's `financial_rip_v4_score` exactly, plus (when the payload supplies it) `financial_benchmark_overall_rip_v12_score` matching the live benchmark's `overall_rip_v12_score`. Require `sealed_product_id <> financial_benchmark_sealed_product_id` (no self-benchmark) — this must be an INDEPENDENT check from the RIP no-self-benchmark check; the Financial benchmark is NOT required to differ from the RIP benchmark (they may legitimately be the same product).
7. **New:** threshold-evidence validation for BOTH sets — non-null, finite (not NaN/Infinity, matching V1's existing finiteness-check idiom), in-range (`chance_to_recover_capital` in `[0,1]`, `actual_committed_capital > 0`), and an economic-reconciliation tolerance check: `abs(threshold_actual_committed_capital - threshold_quantity * best_open_price) <= <a documented tiny tolerance, e.g. 0.01>` for the RIP set and the analogous check against `financial_threshold_quantity * financial_best_open_price` for the Financial set. Do NOT require exact equality (per the Global Constraints — Python's float operation order can leave an IEEE-754 tail).
8. Cent-precision guards on `financial_best_open_price` (same `round(...,2)` idiom as V1's `best_open_price`).
9. Cohort completeness — identical to V1's (`resolved_count + unresolved_count = eligible_cohort_count`).
10. Idempotency fingerprint — same `jsonb_populate_recordset(NULL::public.budget_product_best_open_price_rows, p_rows)`-based content-fingerprint pattern as V1's hardened version (this automatically covers ALL columns including the new V2 ones, since it operates on the whole row type), scoped by `(source_budget_snapshot_id, source_budget_published_at, best_open_price_method_version)` exactly like V1 — this is what makes V1 and V2 snapshots for the same source identity coexist (different `best_open_price_method_version` values never collide on this lookup key).
11. INSERT into `snapshots`/`rows` (same explicit-column-list INSERT idiom as V1, now including all V2 columns for a V2 publish; V1 publishes still insert with the V2 columns implicitly NULL since V1 payloads never populate them), post-insert count check, `latest` upsert (identical `ON CONFLICT (best_open_price_method_version) DO UPDATE` idiom — this key already scopes by method version, so V1's and V2's `latest` rows coexist with zero additional schema change).

- [ ] **Step 5: Mirror the file byte-for-byte**

Copy the finished SQL file to both `supabase/migrations/<TIMESTAMP>_add_best_open_price_v2_dual_threshold.sql` and `backend/db/migrations/<TIMESTAMP>_add_best_open_price_v2_dual_threshold.sql` — identical filename, identical byte content in both directories, matching this repo's established mirroring convention (verified: both `20260914184759_...` and `20260914225000_...` already exist byte-identical in both directories).

- [ ] **Step 6: Write the mirror-equality + contract test file**

Follow `backend/tests/unit/db/test_budget_product_best_open_price_migration_sql.py`'s exact pattern (`_statements()` comment-stripping helper, `test_migration_is_mirrored_into_supabase_directory` byte-equality test, then ~15-20 substring-presence tests asserting the new column names, the new CHECK constraint bodies, the V1-literal-preserved substring markers, the V2-literal method-version string, the `unsupported Best-Open Price method version` exception text, and the GRANT statements are all present in the lowercased/comment-stripped SQL). Read the existing test file first and match its style precisely — same `BACKEND`/`MIGRATIONS`/`SUPABASE_MIRROR` path resolution pattern, adapted to this new migration's filename.

- [ ] **Step 7: Run the new test file**

Run: `cd D:\EVRCalculator\.claude\worktrees\best-open-price-v2 && python -m pytest backend/tests/unit/db/test_best_open_price_v2_migration_sql.py -v`

Expected: PASS — this test requires no database, only file/string operations.

- [ ] **Step 8: Also run the existing V1 migration contract test to confirm zero interference**

Run: `cd D:\EVRCalculator\.claude\worktrees\best-open-price-v2 && python -m pytest backend/tests/unit/db/test_budget_product_best_open_price_migration_sql.py -v`

Expected: PASS, completely unaffected (this new migration never touches the V1 migration files).

- [ ] **Step 9: Checkpoint — fetch, verify, commit, push directly to develop**

```bash
cd D:\EVRCalculator\.claude\worktrees\best-open-price-v2
git fetch origin develop
git log --oneline -1 origin/develop   # confirm still b55f4e07; STOP and reconcile if it has advanced
git add supabase/migrations/<TIMESTAMP>_add_best_open_price_v2_dual_threshold.sql backend/db/migrations/<TIMESTAMP>_add_best_open_price_v2_dual_threshold.sql backend/tests/unit/db/test_best_open_price_v2_migration_sql.py
git commit -m "feat(db): add additive Best-Open Price V2 dual-threshold migration"
git push origin HEAD:develop
```

---

### Task 2: Python V2 payload builder (pure projection, no scoring)

**Files:**
- Modify: `backend/db/services/budget_product_best_open_price_service.py` (add `build_v2_row_payload`, import `BEST_OPEN_PRICE_V2_METHOD_VERSION`)
- Test: `backend/tests/unit/db/services/test_budget_product_best_open_price_service.py`

**Interfaces:**
- Consumes: `BEST_OPEN_PRICE_V2_METHOD_VERSION` from `backend.calculations.evr.best_open_price` (already exists, from Phase 3), and a V2 engine result row — the exact shape `build_v2_row(...)` produces (from Phase 5, `backend/scripts/research_best_open_price_v2.py`): read that function's current return keys directly before writing this task's field-mapping, rather than assuming the field names from the original task instructions' prose.
- Produces: `build_v2_row_payload(engine_row: Mapping[str, Any]) -> Dict[str, Any]` — pure function, no I/O, no scoring, projecting the V2 in-memory row's camelCase keys into the snake_case wire format the new V2 RPC branch expects (all V1 fields' snake_case names unchanged, plus the 18 new snake_case columns from Task 1). Existing `build_row_payload` (V1) is completely untouched.

- [ ] **Step 1: Read the exact current `build_v2_row` output shape**

Read `backend/scripts/research_best_open_price_v2.py`'s `build_v2_row` function (current state, including its fix-round additions: `priceGapDollars`/`ripPriceGapDollars`/`financialPriceGapDollars` etc.) to get the EXACT key names available to project from. Also re-read `build_row_payload` in `budget_product_best_open_price_service.py` (the existing V1 projector) to match its exact style/idioms (default-handling for optional diagnostics fields, etc.).

- [ ] **Step 2: Write the failing tests**

Add to `backend/tests/unit/db/services/test_budget_product_best_open_price_service.py`:

```python
def _v2_engine_row(**overrides):
    row = {
        "sealedProductId": "11111111-1111-1111-1111-111111111111",
        "currentBudgetRank": 2, "currentFinancialOnlyRank": 1,
        "bestOpenPrice": 145.0, "bestOpenPriceCents": 14500, "status": "exact",
        "thresholdQuantity": 9, "benchmarkSealedProductId": "22222222-2222-2222-2222-222222222222",
        "benchmarkOverallRipV12Score": 80.0,
        "priceGapDollars": 5.0, "priceGapPercent": 0.03,
        "ripBestOpenPrice": 145.0, "ripBestOpenPriceCents": 14500, "ripStatus": "exact",
        "ripThresholdQuantity": 9, "ripBenchmarkSealedProductId": "22222222-2222-2222-2222-222222222222",
        "ripBenchmarkOverallRipV12Score": 80.0,
        "ripPriceGapDollars": 5.0, "ripPriceGapPercent": 0.03,
        "ripThresholdFinancialRipV4Score": 50.0, "ripThresholdOverallRipV12Score": 80.0,
        "ripThresholdChanceToRecoverCapital": 0.3, "ripThresholdActualCommittedCapital": 1305.0,
        "financialBestOpenPrice": 150.0, "financialBestOpenPriceCents": 15000, "financialStatus": "exact",
        "financialThresholdQuantity": 9, "financialBenchmarkSealedProductId": "33333333-3333-3333-3333-333333333333",
        "financialBenchmarkFinancialRipV4Score": 90.0,
        "financialPriceGapDollars": 10.0, "financialPriceGapPercent": 0.06,
        "financialThresholdFinancialRipV4Score": 90.0, "financialThresholdOverallRipV12Score": 70.0,
        "financialThresholdChanceToRecoverCapital": 0.4, "financialThresholdActualCommittedCapital": 1350.0,
        "resolved": True, "ripResolved": True, "financialResolved": True,
        "ripExactness": {"thresholdWins": True, "nextPriceCents": 14501, "nextPriceWins": False,
                          "oneCentMaximal": True, "quantityIntervalLowCents": 14000, "quantityIntervalHighCents": 15000,
                          "nextCentCrossesQuantityBoundary": False},
        "financialExactness": {"thresholdWins": True, "nextPriceCents": 15001, "nextPriceWins": False,
                                "oneCentMaximal": True, "quantityIntervalLowCents": 14800, "quantityIntervalHighCents": 15200,
                                "nextCentCrossesQuantityBoundary": False},
    }
    row.update(overrides)
    return row


def test_build_v2_row_payload_projects_generic_rip_fields():
    payload = build_v2_row_payload(_v2_engine_row())
    assert payload["status"] == "exact"
    assert payload["best_open_price"] == 145.0
    assert payload["threshold_quantity"] == 9
    assert payload["price_gap_dollars"] == 5.0
    assert payload["benchmark_sealed_product_id"] == "22222222-2222-2222-2222-222222222222"


def test_build_v2_row_payload_projects_financial_fields():
    payload = build_v2_row_payload(_v2_engine_row())
    assert payload["current_financial_only_rank"] == 1
    assert payload["financial_best_open_price"] == 150.0
    assert payload["financial_status"] == "exact"
    assert payload["financial_threshold_quantity"] == 9
    assert payload["financial_benchmark_sealed_product_id"] == "33333333-3333-3333-3333-333333333333"
    assert payload["financial_benchmark_financial_rip_v4_score"] == 90.0


def test_build_v2_row_payload_projects_both_threshold_evidence_sets():
    payload = build_v2_row_payload(_v2_engine_row())
    assert payload["threshold_financial_rip_v4_score"] == 50.0
    assert payload["threshold_overall_rip_v12_score"] == 80.0
    assert payload["threshold_actual_committed_capital"] == 1305.0
    assert payload["financial_threshold_financial_rip_v4_score"] == 90.0
    assert payload["financial_threshold_overall_rip_v12_score"] == 70.0
    assert payload["financial_threshold_actual_committed_capital"] == 1350.0


def test_build_v2_row_payload_does_not_compute_anything_it_reads_verbatim():
    """No arithmetic beyond straight field copies -- this is a projection,
    not a scorer."""
    row = _v2_engine_row(ripThresholdActualCommittedCapital=9999.0)
    payload = build_v2_row_payload(row)
    assert payload["threshold_actual_committed_capital"] == 9999.0  # copied, not recomputed


def test_build_row_payload_v1_is_unaffected():
    """Sanity pin: adding build_v2_row_payload must not touch build_row_payload."""
    from backend.db.services.budget_product_best_open_price_service import build_row_payload
    assert build_row_payload is not None  # import still works; existing V1 tests cover its behavior
```

Adjust field names/keys in the fixture to match whatever `build_v2_row`'s ACTUAL current output shape is (Step 1) — the fixture above is a best-effort reconstruction from this plan's knowledge of Phase 5's implementation; if the real shape differs (e.g., different key casing, nested exactness structure), match the REAL shape, not this fixture.

- [ ] **Step 2b: Run tests to verify they fail**

Run: `cd D:\EVRCalculator\.claude\worktrees\best-open-price-v2 && python -m pytest backend/tests/unit/db/services/test_budget_product_best_open_price_service.py -k "build_v2_row_payload" -v`

Expected: FAIL — `build_v2_row_payload` doesn't exist yet.

- [ ] **Step 3: Implement `build_v2_row_payload`**

In `backend/db/services/budget_product_best_open_price_service.py`, add the import and the new function, following `build_row_payload`'s existing style exactly (pure dict projection, no computation beyond direct field reads/renames):

```python
from backend.calculations.evr.best_open_price import BEST_OPEN_PRICE_V2_METHOD_VERSION


def build_v2_row_payload(engine_row: Mapping[str, Any]) -> Dict[str, Any]:
    """Pure projection of one V2 engine result row (build_v2_row() output,
    backend/scripts/research_best_open_price_v2.py) into the snake_case wire
    format the V2 RPC branch expects. No scoring, no recomputation -- every
    threshold-evidence value here is a straight copy from the engine row.
    """
    return {
        # Generic + RIP-aliased fields (unchanged meaning from V1)
        "status": engine_row.get("status"),
        "best_open_price": engine_row.get("bestOpenPrice"),
        "threshold_quantity": engine_row.get("thresholdQuantity"),
        "price_gap_dollars": engine_row.get("priceGapDollars"),
        "price_gap_percent": engine_row.get("priceGapPercent"),
        "benchmark_sealed_product_id": engine_row.get("benchmarkSealedProductId"),
        "benchmark_overall_rip_v12_score": engine_row.get("benchmarkOverallRipV12Score"),
        # V2 Financial fields
        "current_financial_only_rank": engine_row.get("currentFinancialOnlyRank"),
        "financial_status": engine_row.get("financialStatus"),
        "financial_best_open_price": engine_row.get("financialBestOpenPrice"),
        "financial_threshold_quantity": engine_row.get("financialThresholdQuantity"),
        "financial_price_gap_dollars": engine_row.get("financialPriceGapDollars"),
        "financial_price_gap_percent": engine_row.get("financialPriceGapPercent"),
        "financial_benchmark_sealed_product_id": engine_row.get("financialBenchmarkSealedProductId"),
        "financial_benchmark_financial_rip_v4_score": engine_row.get("financialBenchmarkFinancialRipV4Score"),
        "financial_benchmark_overall_rip_v12_score": engine_row.get("financialBenchmarkOverallRipV12Score"),
        # Threshold evidence (both axes, verbatim)
        "threshold_financial_rip_v4_score": engine_row.get("ripThresholdFinancialRipV4Score"),
        "threshold_overall_rip_v12_score": engine_row.get("ripThresholdOverallRipV12Score"),
        "threshold_chance_to_recover_capital": engine_row.get("ripThresholdChanceToRecoverCapital"),
        "threshold_actual_committed_capital": engine_row.get("ripThresholdActualCommittedCapital"),
        "financial_threshold_financial_rip_v4_score": engine_row.get("financialThresholdFinancialRipV4Score"),
        "financial_threshold_overall_rip_v12_score": engine_row.get("financialThresholdOverallRipV12Score"),
        "financial_threshold_chance_to_recover_capital": engine_row.get("financialThresholdChanceToRecoverCapital"),
        "financial_threshold_actual_committed_capital": engine_row.get("financialThresholdActualCommittedCapital"),
    }
```

Also copy in whatever V1 shared fields `build_row_payload` includes that this sketch omitted (identity fields like `sealed_product_id`/`set_id`/`product_family`/`source_calculation_run_id`, current-state fields like `current_market_price`/`current_quantity`/`current_budget_rank`/`current_overall_rip_v12_score`/`current_financial_rip_v4_score`/`current_collector_appeal_score`/`current_chase_accessibility_raw`/`current_chance_to_recover_capital`/`current_actual_committed_capital`, and diagnostics fields like `candidate_price_evaluations`/`bracket_expansions`/etc.) — read `build_row_payload`'s real current body and include every field a V2 row also needs at the DB layer, sourcing V2's equivalent key from `build_v2_row`'s real output (per Step 1). Do not invent a field name; if a needed source-metadata field isn't present on `build_v2_row`'s output, that's a signal to fix `build_v2_row` in `research_best_open_price_v2.py` to carry it (a minimal additive fix, copying from the source row it already has access to) — do not fabricate the value here.

- [ ] **Step 4: Run tests to verify they pass**

Run: `cd D:\EVRCalculator\.claude\worktrees\best-open-price-v2 && python -m pytest backend/tests/unit/db/services/test_budget_product_best_open_price_service.py -v`

Expected: PASS, all tests including every pre-existing V1 test in this file, unmodified.

- [ ] **Step 5: Checkpoint — fetch, verify, commit, push directly to develop**

```bash
cd D:\EVRCalculator\.claude\worktrees\best-open-price-v2
git fetch origin develop
git log --oneline -1 origin/develop   # confirm it matches Task 1's push; STOP and reconcile if advanced further
git add backend/db/services/budget_product_best_open_price_service.py backend/tests/unit/db/services/test_budget_product_best_open_price_service.py backend/scripts/research_best_open_price_v2.py
git commit -m "feat: add build_v2_row_payload pure V2 persistence projector"
git push origin HEAD:develop
```

(Include `research_best_open_price_v2.py` in the commit only if Step 3 required a minimal additive fix there; otherwise omit it from `git add`.)

---

### Task 3: Method-version-aware read services (private + public rankings + product detail)

**Files:**
- Modify: `backend/db/services/budget_product_best_open_price_service.py` (`load_best_open_price_ranking`, `load_best_open_price_product` — add explicit `method_version` parameter/dispatch)
- Modify: `backend/db/services/public_overall_product_rankings_service.py` (`_best_open_price_projection`, the per-row attachment block)
- Modify: `backend/db/services/pokemon_sealed_product_detail_service.py` (`_best_open_price_contract`)
- Test: `backend/tests/unit/db/services/test_budget_product_best_open_price_service.py`, `backend/tests/unit/db/services/test_public_overall_product_rankings_service.py` (or wherever its existing tests live — find the real path first), and the product-detail service's existing test file

**Interfaces:**
- Consumes: `BEST_OPEN_PRICE_METHOD_VERSION`, `BEST_OPEN_PRICE_V2_METHOD_VERSION`.
- Produces: `load_best_open_price_ranking(client, *, best_open_price_method_version=BEST_OPEN_PRICE_METHOD_VERSION) -> Dict[str, Any]` (existing signature already has this parameter per the earlier research — confirm and extend its `rows` shape to include V2 fields when the loaded snapshot's method version is V2). `load_best_open_price_product(client, sealed_product_id, *, best_open_price_method_version=...) -> Dict[str, Any]` similarly. The public rankings projection and product-detail contract both gain explicit `ripBestOpenPrice*`/`financialBestOpenPrice*` fields (generic fields continue to alias RIP), populated ONLY when reading a V2-method row, never fabricated for a V1 row.

- [ ] **Step 1: Read the exact current implementations**

Read `load_best_open_price_ranking`/`load_best_open_price_product` in full (current state — these already take a `best_open_price_method_version` keyword per earlier research; confirm whether that's really true or whether it needs to be ADDED). Read `_best_open_price_projection` in `public_overall_product_rankings_service.py` in full (lines ~25-72 and ~103-159 per earlier research). Read `_best_open_price_contract` in `pokemon_sealed_product_detail_service.py` in full (lines ~158-190 and its call site ~553-558 per earlier research).

- [ ] **Step 2: Write the failing tests for the private service's V2-awareness**

Add tests (adapt to the EXISTING test file's fake-client fixture pattern — read it first and match its conventions exactly rather than inventing a parallel fake-client shape):

```python
def test_load_best_open_price_ranking_v2_exposes_dual_fields(fake_client_factory):
    # Arrange a fake client whose latest-pointer/snapshot/rows reflect the
    # V2 method version and populate both generic (RIP) and financial_* columns.
    client = fake_client_factory(
        method_version=BEST_OPEN_PRICE_V2_METHOD_VERSION,
        rows=[{
            "sealed_product_id": "p1", "status": "exact", "best_open_price": 145.0,
            "current_financial_only_rank": 1, "financial_best_open_price": 150.0,
            "financial_status": "exact",
        }],
    )
    result = load_best_open_price_ranking(client, best_open_price_method_version=BEST_OPEN_PRICE_V2_METHOD_VERSION)
    row = result["rows"][0]
    assert row["best_open_price"] == 145.0  # RIP alias unchanged
    assert row["financial_best_open_price"] == 150.0
    assert row["current_financial_only_rank"] == 1


def test_load_best_open_price_ranking_v1_never_carries_financial_fields(fake_client_factory):
    client = fake_client_factory(
        method_version=BEST_OPEN_PRICE_METHOD_VERSION,
        rows=[{"sealed_product_id": "p1", "status": "exact", "best_open_price": 100.0}],
    )
    result = load_best_open_price_ranking(client, best_open_price_method_version=BEST_OPEN_PRICE_METHOD_VERSION)
    row = result["rows"][0]
    assert "financial_best_open_price" not in row or row.get("financial_best_open_price") is None
```

Adapt `fake_client_factory` to whatever fixture helper the existing test file actually provides (it may be named differently, e.g. a `_FakeClient` class or `monkeypatch`-based table stub — match the real pattern).

- [ ] **Step 3: Run to verify RED, then confirm/adjust the private service**

If `load_best_open_price_ranking`/`load_best_open_price_product` already correctly pass through whatever columns exist on the loaded row (i.e., they're generic dict-based readers that don't hardcode a V1-only field allowlist), these tests may already pass with ZERO code changes — in that case, these tests become pinning tests proving the existing generic implementation is already safe, and you should report that rather than adding unnecessary code. If the functions DO hardcode a V1-only column allowlist (stripping out unknown columns), extend that allowlist additively to include the 18 new V2 column names, gated so V1 rows (which have them all NULL) are unaffected.

- [ ] **Step 4: Write the failing tests for public rankings' V2 attachment**

Add to the public rankings service's real existing test file:

```python
def test_v2_full_market_projection_attaches_both_rip_and_financial_fields():
    # Arrange a fake load_best_open_price_ranking-equivalent returning a V2 row.
    ...
    result = read_public_overall_product_rankings(client, budget="full_market", ...)
    row = next(r for r in result["rows"] if r["sealedProductId"] == "p1")
    assert row["bestOpenPrice"] == row["ripBestOpenPrice"]
    assert row["financialBestOpenPrice"] is not None
    assert row["financialBestOpenPriceStatus"] is not None


def test_v1_full_market_projection_never_exposes_financial_fields():
    ...
    result = read_public_overall_product_rankings(client, budget="full_market", ...)
    row = next(r for r in result["rows"] if r["sealedProductId"] == "p1")
    assert "financialBestOpenPrice" not in row or row["financialBestOpenPrice"] is None


def test_rankings_stay_available_when_best_open_is_unavailable(monkeypatch):
    """Rankings must never depend on Best-Open success."""
    ...
    # Force _best_open_price_projection to raise/return unavailable, then
    # assert the overall response still returns rows (rankings unaffected),
    # only the per-row bestOpenPrice*/financialBestOpenPrice* fields are absent.
```

Match the real existing test file's fixture-building conventions (find it by searching for existing `_best_open_price_projection`-related tests first).

- [ ] **Step 5: Implement the public rankings V2 attachment**

In `_best_open_price_projection` and the per-row attachment block, extend the projected fields:

```python
if best_open is not None:
    projected.update({
        "bestOpenPrice": best_open.get("best_open_price"),
        "bestOpenPriceStatus": best_open.get("status"),
        "bestOpenPriceGapDollars": best_open.get("price_gap_dollars"),
        "bestOpenPriceGapPercent": best_open.get("price_gap_percent"),
        "ripBestOpenPrice": best_open.get("best_open_price"),
        "ripBestOpenPriceStatus": best_open.get("status"),
        "ripBestOpenPriceGapDollars": best_open.get("price_gap_dollars"),
        "ripBestOpenPriceGapPercent": best_open.get("price_gap_percent"),
    })
    if best_open.get("financial_best_open_price") is not None:
        projected.update({
            "financialBestOpenPrice": best_open.get("financial_best_open_price"),
            "financialBestOpenPriceStatus": best_open.get("financial_status"),
            "financialBestOpenPriceGapDollars": best_open.get("financial_price_gap_dollars"),
            "financialBestOpenPriceGapPercent": best_open.get("financial_price_gap_percent"),
        })
```

The `if best_open.get("financial_best_open_price") is not None:` guard is what prevents fabricating Financial fields for a V1 row (whose `financial_best_open_price` is always `None`/absent). Do not change anything about `_best_open_price_projection`'s existing availability/staleness/completeness logic (source-identity cross-check, resolved-count check) — that logic is version-agnostic and must keep gating BOTH V1 and V2 rows identically; extend it only if the V2 completeness check genuinely needs an additional field (e.g., if V2's `resolvedCount` should require BOTH `ripResolved`/`financialResolved`, check whether the persisted V2 payload already encodes that in its counters before adding new logic here — do not duplicate a completeness check that the RPC/service layer already enforces upstream).

- [ ] **Step 6: Write the failing tests for Product Detail's V2 contract, then implement**

Add tests mirroring `_best_open_price_contract`'s existing test coverage (find its real test file first), covering: a V2 row returns both `ripBestOpenPrice*` and `financialBestOpenPrice*` fields nested consistently with the existing contract shape; a V1 row returns only the existing fields with no fabricated Financial keys; the entitlement boundary (the existing "rides inside the already Plus-gated `rip` envelope" comment/mechanism) is preserved unchanged — do NOT add new entitlement logic to this file if none already exists here; confirm via the earlier research that gating happens upstream of `get_pokemon_sealed_product_detail_payload`'s return value, and if so, your job is only to ensure the V2 fields are nested INSIDE the same `rip["bestOpenPrice"]` structure the existing gating already wraps, not to add new gating.

```python
def _best_open_price_contract(client: Any, sealed_product_id: str) -> Dict[str, Any]:
    try:
        prepared = load_best_open_price_product(client, sealed_product_id)
    except Exception:
        return {"available": False, "reason": "prepared_read_failed"}
    if not prepared.get("available"):
        return {"available": False, "reason": prepared.get("reason") or "prepared_unavailable"}
    row = prepared.get("row") or {}
    contract = {
        "available": True, "reason": None,
        "bestOpenPrice": row.get("best_open_price"), "status": row.get("status"),
        "priceGapDollars": row.get("price_gap_dollars"), "priceGapPercent": row.get("price_gap_percent"),
        "thresholdQuantity": row.get("threshold_quantity"), "sourceUnitPrice": row.get("current_market_price"),
        "sourceBudgetRank": row.get("current_budget_rank"), "sourceMarketDate": prepared.get("sourceMarketDate"),
        "sourceFullMarketBudget": prepared.get("sourceFullMarketBudget"),
        "sourceCohortSize": prepared.get("sourceEligibleCohortCount"),
        "sourceBudgetSnapshotId": prepared.get("sourceBudgetSnapshotId"), "methodVersion": prepared.get("methodVersion"),
        "ripBestOpenPrice": row.get("best_open_price"), "ripBestOpenPriceStatus": row.get("status"),
        "ripBestOpenPriceGapDollars": row.get("price_gap_dollars"), "ripBestOpenPriceGapPercent": row.get("price_gap_percent"),
    }
    if row.get("financial_best_open_price") is not None:
        contract.update({
            "financialBestOpenPrice": row.get("financial_best_open_price"),
            "financialBestOpenPriceStatus": row.get("financial_status"),
            "financialBestOpenPriceGapDollars": row.get("financial_price_gap_dollars"),
            "financialBestOpenPriceGapPercent": row.get("financial_price_gap_percent"),
        })
    return contract
```

Do not change the call site (`rip["bestOpenPrice"] = _best_open_price_contract(...)`) — the existing nesting/gating already wraps this function's entire return value, so extending the dict this function returns automatically inherits the existing entitlement boundary with no further changes needed. Confirm this by tracing the call site once more before considering the task done.

- [ ] **Step 7: Run every touched test file**

Run: `cd D:\EVRCalculator\.claude\worktrees\best-open-price-v2 && python -m pytest backend/tests/unit/db/services/test_budget_product_best_open_price_service.py -v` and the equivalent commands for whichever real test files you found/touched for `public_overall_product_rankings_service.py` and `pokemon_sealed_product_detail_service.py`.

Expected: PASS, including every pre-existing test.

- [ ] **Step 8: Checkpoint — fetch, verify, commit, push directly to develop**

```bash
cd D:\EVRCalculator\.claude\worktrees\best-open-price-v2
git fetch origin develop
git log --oneline -1 origin/develop   # confirm it matches Task 2's push; STOP and reconcile if advanced further
git add backend/db/services/budget_product_best_open_price_service.py backend/db/services/public_overall_product_rankings_service.py backend/db/services/pokemon_sealed_product_detail_service.py <the real test file paths you touched>
git commit -m "feat: make Best-Open read services method-version-aware for V2 dual fields"
git push origin HEAD:develop
```

---

### Task 4: Disposable-Postgres integration test, migration-mirror verification, full test matrix, validation suite

**Files:**
- Create: `backend/tests/integration/test_best_open_publication_v2_postgres.py` (new file, mirroring `test_best_open_publication_postgres.py`'s structure)
- Modify: `.github/workflows/best-open-price-guardrails.yml` (extend the `postgres-integration` job to also run the new V2 test file, alongside the existing V1 one — additive, do not remove the V1 `cmp`/pytest invocation)
- Test/report: cross-check against the 45-item Phase 9 matrix

**Interfaces:** none new — this task closes out coverage and reports honestly on what could/couldn't be executed in this environment.

- [ ] **Step 1: Read the exact current `test_best_open_publication_postgres.py` in full**

Read all 280 lines. You will build a structurally-parallel V2 file. Reuse the `database()` fixture's role/schema-creation logic (add the new V2 columns to its stub table DDL if the fixture creates the store tables from scratch rather than executing the real migration files — check which it does; per earlier research it executes `OLD.read_text()` then `NEW.read_text()`, the REAL migration files, so it will automatically pick up Task 1's new migration once you also execute it in this file's fixture — add a third `V2 = ROOT / "supabase" / "migrations" / "<Task 1's timestamp>_add_best_open_price_v2_dual_threshold.sql"` and execute it after `NEW` in the fixture).

- [ ] **Step 2: Write the V2 integration test file**

Mirror the V1 file's structure:
- Same `DSN`/`skipif` gate, same `BEST_OPEN_ACK_DISPOSABLE`/host/dbname safety checks in the `database()` fixture (extend it to also execute the new V2 migration file after the existing two).
- A `fixture_payload_v2()` helper analogous to `fixture_payload()`, but including `current_financial_only_rank`/`financial_*` fields on each row and using `BEST_OPEN_PRICE_V2_METHOD_VERSION` as the snapshot's `best_open_price_method_version`.
- A `publish()` helper reused as-is (it already takes arbitrary `snap`/`rows`, so no method-version-specific change needed there).
- Tests covering RPC items 8-30 from the Phase 9 matrix:
  - Item 8 (V1 still succeeds): reuse/import the V1 file's own `fixture_payload()` and `publish()` against the SAME database fixture (now that the V2 migration is additive, a V1 publish must still succeed identically) — this can be a single new test in the V2 file, or you can add it to the V1 file if that's cleaner; your call, but it MUST exist somewhere and actually run V1's exact payload shape through the now-V2-aware schema.
  - Item 9 (V2 full valid publish succeeds).
  - Items 10-21 (each required V2 field/benchmark/score omission or mutation individually rejected) — parametrize similarly to the V1 file's 26-case rejection matrix, one case per Phase 9 item.
  - Item 22 (duplicate product rows fail) — reuse the V1 pattern.
  - Item 23 (incomplete cohort fails) — reuse the V1 pattern.
  - Item 24 (source pointer drift fails) — reuse the V1 pattern (mutate the live source between fixture setup and publish).
  - Item 25 (same source + same V2 content idempotently returns same ID).
  - Item 26 (same source + changed V2 content fails non-determinism).
  - Item 27 (V1 + V2 coexist for the same source identity) — publish V1 then V2 against the same source snapshot and assert both succeed with distinct `latest` pointers (one per method version).
  - Items 28-30 (anon/authenticated/service_role role execution) — reuse the exact `SET ROLE`/`BYPASSRLS` idiom from the V1 file verbatim, pointed at the V2 payload.

- [ ] **Step 3: Verify the file collects and skips cleanly locally (it cannot run for real here)**

Run: `cd D:\EVRCalculator\.claude\worktrees\best-open-price-v2 && python -m pytest backend/tests/integration/test_best_open_publication_v2_postgres.py -v`

Expected: all tests report `SKIPPED (isolated PostgreSQL DSN required)` — this worktree has no `BEST_OPEN_TEST_DATABASE_URL` and no local Postgres/Docker (confirmed by the controller: `which docker/postgres/pg_ctl/initdb/supabase` all empty). This is the SAME outcome a local run of the existing V1 file (`test_best_open_publication_postgres.py`) already produces today — do not attempt to fabricate a database, mock psycopg, or otherwise force these tests to "pass" without a real Postgres. Report the skip count honestly.

- [ ] **Step 4: Extend the CI workflow additively**

In `.github/workflows/best-open-price-guardrails.yml`'s `postgres-integration` job, add a step (or extend the existing "Apply mirrored migrations and run real concurrent RPC tests" step) to also `cmp` the new V2 migration's two copies and run the new V2 test file — additively, alongside the existing V1 `cmp`/pytest invocation, never replacing it:

```yaml
- name: Apply mirrored V2 migration and run V2 RPC tests
  run: |
    cmp supabase/migrations/<TIMESTAMP>_add_best_open_price_v2_dual_threshold.sql backend/db/migrations/<TIMESTAMP>_add_best_open_price_v2_dual_threshold.sql
    python -m pytest -q backend/tests/integration/test_best_open_publication_v2_postgres.py
```

- [ ] **Step 5: Cross-check the full 45-item Phase 9 matrix**

Go through all 45 items (SCHEMA 1-7, RPC 8-30, SERVICE/PROJECTION 31-41, ENGINE/PERSISTENCE CONTRACT 42-45). For each, cite the specific test (from Task 1's migration contract test, Task 2/3's Python unit tests, or this task's integration test file) that covers it, or add a small focused test if a genuine gap remains. Items 8-30 (RPC-level) are AUTHORED and CI-gated per Step 2 but not locally EXECUTED (Step 3's honest skip report) — note this explicitly for each RPC item rather than claiming a false pass.

- [ ] **Step 6: Run the full Python-side validation suite**

```bash
cd D:\EVRCalculator\.claude\worktrees\best-open-price-v2
python -m pytest backend/tests/unit/db/ backend/tests/unit/calculations/test_prepared_financial_rip_and_best_open_price.py backend/tests/unit/calculations/test_budget_normalized_product_ranking.py backend/tests/unit/scripts/test_research_best_open_price_v2.py -v
git diff --check
```

Report exact pass/fail/collection-error results, distinguishing genuine results from the already-well-documented pre-existing Supabase-credential collection gap in this worktree (affects any test file that transitively imports `backend.db.services.__init__` → `supabase_client` without a real/dummy-JWT-shaped local credential) — do not attempt to fix that environment condition, just report accurately, exactly as every prior task in this larger effort has done.

- [ ] **Step 7: Checkpoint — fetch, verify, commit, push directly to develop**

```bash
cd D:\EVRCalculator\.claude\worktrees\best-open-price-v2
git fetch origin develop
git log --oneline -1 origin/develop   # confirm it matches Task 3's push; STOP and reconcile if advanced further
git add backend/tests/integration/test_best_open_publication_v2_postgres.py .github/workflows/best-open-price-guardrails.yml
git commit -m "test: add disposable-Postgres V2 RPC integration suite and CI wiring"
git push origin HEAD:develop
```

---

## Self-Review Notes

- Spec coverage: Phase 6-A/B/C (additive columns, tolerant constraints, historical-compatibility tests) — Task 1. Phase 7-A/B/C/D/E/F/G/H (V2 payload builder, RPC dispatch, source locking/authority preserved, current-row reconciliation, RIP + Financial benchmark validation, threshold evidence, idempotency) — Task 1 (RPC SQL) + Task 2 (Python builder). Phase 8-A/B/C/D (V2 presentation contract, product rankings, product detail, V1 compatibility) — Task 3. Phase 9 (45-item test matrix, disposable Postgres requirement) — Task 4, with the environment limitation (no local Docker/Postgres) explicitly acknowledged rather than silently worked around or silently skipped.
- No placeholders: Task 1's RPC body is specified as "copy V1 verbatim into one branch, write the new V2 body per the ordered list in Step 4" — this is a concrete instruction to reuse already-quoted-elsewhere real code, not an unfilled gap. Task 2/3 give exact function bodies with an explicit, flagged instruction to verify field names against the real current code before finalizing (since two upstream files this plan depends on — `build_v2_row` and the private service's exact current signature — were described from research rather than pinned line-by-line in this document).
- Type consistency: `build_v2_row_payload`'s snake_case output keys (Task 2) match Task 1's migration column names exactly (`current_financial_only_rank`, `financial_best_open_price`, `threshold_financial_rip_v4_score`, etc.) and are consumed identically by Task 4's integration test fixtures.
- Environment honesty: this plan does not claim disposable-Postgres RPC tests will pass in this session — it authors them, verifies they collect and skip correctly (proving they're wired right), and defers real execution to CI, exactly matching this repo's own established pattern for the V1 RPC.

---

## Execution report (Tasks A-F, worktree `best-open-price-v2`)

**Starting state:** the worktree was on a detached HEAD at `634c04b9` (an already-committed-but-unpushed Task A: `build_v2_row_payload` in `backend/db/services/budget_product_best_open_price_service.py`, plus its tests, built directly on `e992a23b`). `origin/develop` had meanwhile advanced to `74a33be6` via an unrelated merge (`8b3e3c0b` pokemon-onboarding work).

### A. Python persistence service — DONE (pre-existing, verified not redone)
`build_row_payload` (V1) untouched. `build_v2_row_payload` added, importing both `BEST_OPEN_PRICE_METHOD_VERSION` and `BEST_OPEN_PRICE_V2_METHOD_VERSION` from `backend/calculations/evr/best_open_price.py`. Pure projection, asserts `engine_row["methodVersion"] == BEST_OPEN_PRICE_V2_METHOD_VERSION`, no scoring.

### B. Method-aware private readers — DONE
`load_best_open_price_ranking` already used `select("*")` — proven version-agnostic-safe via new pinning tests, zero code change needed there. `load_best_open_price_product`'s column allowlist was V1-only; extended additively to select the six V2 Financial-axis columns (`current_financial_only_rank`, `financial_status`, `financial_best_open_price`, `financial_threshold_quantity`, `financial_price_gap_dollars`, `financial_price_gap_percent`). V1 rows have these NULL at the DB level (additive migration); nothing here fabricates a value.

### C. Public Product Rankings projection — DONE
`public_overall_product_rankings_service.py`'s per-row attachment now also sets `ripBestOpenPrice`/`ripBestOpenPriceStatus`/`ripBestOpenPriceGapDollars`/`ripBestOpenPriceGapPercent` (aliasing the same RIP values `bestOpenPrice*` already carries), and — guarded by `best_open.get("financial_best_open_price") is not None` — attaches `financialBestOpenPrice`/`financialBestOpenPriceStatus`/`financialBestOpenPriceGapDollars`/`financialBestOpenPriceGapPercent`. No change to the existing availability/staleness/completeness logic. Availability isolation (Best-Open failure never takes down the rest of Product Rankings) was already true via the pre-existing try/except + available guard; proven with a new test.

### D. Product Detail prepared projection — DONE
`pokemon_sealed_product_detail_service.py`'s `_best_open_price_contract` gains the same `ripBestOpenPrice*` aliases and guarded `financialBestOpenPrice*` fields. No request-time scoring. Confirmed by tracing the call site (`rip["bestOpenPrice"] = _best_open_price_contract(...)`, line ~574) that the entire `rip` dict rides inside the pre-existing Index Plus entitlement gate; no new gating logic was added, and a source-pin test guards that call-site string.

### E. Phase 9 tests — DONE
Added V1/V2-awareness tests to all three touched service test files, plus an AST-based no-engine-import/call test parametrized across the three read-path modules (mirrors this repo's `test_prepared_read_never_calls_score_budget_strategy` isolation pattern). Result: **119 passed, 0 failed** across the five touched/related unit test files (`python -m pytest backend/tests/unit/db/services/test_budget_product_best_open_price_service.py backend/tests/unit/db/services/test_public_overall_product_rankings_service.py backend/tests/unit/db/services/test_pokemon_sealed_product_detail_service.py backend/tests/unit/db/test_best_open_price_v2_migration_sql.py backend/tests/unit/db/test_budget_product_best_open_price_migration_sql.py -q`). A broader `backend/tests/unit` run showed 339 pre-existing unrelated failures (missing `stripe`/`jwt` modules, Python-3.8-vs-3.13 typing syntax, a Windows cp1252-vs-UTF-8 `Path.read_text()` encoding issue) — none touch the files this task modified, and none are new.

### F. Disposable-Postgres V2 RPC test matrix — AUTHORED, LOCAL EXECUTION PENDING
No Docker/Postgres/pg_ctl/initdb in this environment (confirmed empty). Authored `backend/tests/integration/test_best_open_publication_v2_postgres.py` (23 tests), structurally parallel to `test_best_open_publication_postgres.py` (reuses its DSN/connection/fixture_payload via import), applying the V2 migration in its `database()` fixture. Covers Phase 9 items 8 (V1 still succeeds on V2-aware schema), 9 (V2 valid publish), 10-21 (required-field/benchmark omissions, parametrized), 22 (duplicates), 23 (incomplete cohort), 24 (source drift), 25 (idempotency), 26 (non-determinism rejection), 27 (V1+V2 coexistence), 28-30 (role execution). Verified it collects and skips cleanly: 23 skipped (`isolated PostgreSQL DSN required`), same outcome as the V1 file locally. Extended `.github/workflows/best-open-price-guardrails.yml`'s `postgres-integration` job additively with a new step running the V2 cmp+pytest invocation alongside the untouched V1 one. **Real Postgres execution has NOT happened in this session and is deferred to CI** — reported honestly, not faked.

### V1 zero-diff confirmation
`build_row_payload` source is byte-identical to before. `load_best_open_price_ranking` has zero code changes (only new pinning tests). `load_best_open_price_product` gained additive `select()` columns only — parameters, return shape, staleness/availability logic unchanged; existing V1 tests pass unmodified. `_best_open_price_projection`'s/`_best_open_price_contract`'s generic (RIP-named) fields and existing gating logic are byte-identical; only new keys were added downstream of the existing construction.

### Commits and push
- `dfe028c6` — `feat: add build_v2_row_payload pure V2 persistence projector` (Task A, authored before this session resumed; rebased onto `origin/develop` cleanly, unmodified).
- `ae7ab282` — `feat: make Best-Open read services method-version-aware for V2 dual fields` (Tasks B-F, this session).
- Both landed on `origin/develop` via plain `git push origin HEAD:develop` (no `--force`). Confirmed via `git fetch && git log origin/develop -1` → `ae7ab2824f3f81881008fb3a7a1cda146f7f3d09`.
- `git diff --check` ran clean before pushing (only LF→CRLF notices, no conflict markers/trailing whitespace).
- Two large unrelated JSON fixture files mutated as a side effect of the wider test run were reverted with `git checkout --` before staging.

**Status (superseded by the follow-up remediation section below):** A-E fully complete and verified; F was authored, CI-wired, and locally skip-verified, but real-Postgres CI execution subsequently surfaced three real defects (see "Remediation: three independent-review findings" below) that this status line's token was premature about. Do not treat the token on this line as valid; see the final status at the end of this document.

---

## Remediation: three independent-review findings (2026-09-17)

Independent manual review plus a real GitHub Actions run against `postgres:17.11` surfaced three concrete defects in the Tasks A-F work above. All three are now fixed in this worktree.

### Finding 1 — CURRENT method selection was missing
`load_best_open_price_ranking`/`load_best_open_price_product` are method-aware but default to V1, and the two current/live-serving call sites (`_best_open_price_projection` in `public_overall_product_rankings_service.py`, `_best_open_price_contract` in `pokemon_sealed_product_detail_service.py`) called them with no explicit method version, so a future current V2 publication would never actually be served — V1 (stale or absent) would keep masking it forever.

Fix: both call sites now attempt `BEST_OPEN_PRICE_V2_METHOD_VERSION` explicitly first; only when that attempt reports `available: False` do they fall back to an explicit `BEST_OPEN_PRICE_METHOD_VERSION` attempt. Both attempts reuse the exact same `load_best_open_price_ranking`/`load_best_open_price_product` currentness/completeness checks (source-binding match, resolved/unresolved-count reconciliation), so V1 only serves when it independently earns "current" the same way V2 must. The low-level loaders' own default parameter (V1) and signature are completely unchanged — this is a selection layer added above them, not a default flip, so every existing explicit-V1 caller (the private-service unit tests calling `load_best_open_price_ranking(client)` directly, `publish_best_open_price_if_ready.py`) is unaffected.

Tests added (spies capturing the actual `best_open_price_method_version` argument(s) passed to the real loader, not just final shape):
- `test_public_overall_product_rankings_service.py::test_current_rankings_requests_v2_first` (A)
- `test_best_open_price_product_detail.py::test_current_product_detail_requests_v2_first` (B)
- `test_best_open_price_product_detail.py::test_current_v2_is_selected_when_available` (C)
- `test_best_open_price_product_detail.py::test_product_detail_best_open_contract_preserves_dated_ranking_source` (rewritten to assert the exact `[V2, V1]` call sequence) + `test_public_overall_product_rankings_service.py::test_missing_v2_falls_back_to_current_v1_rankings` (D)
- `test_public_overall_product_rankings_service.py::test_stale_v1_cannot_mask_current_v2_rankings` + `test_best_open_price_product_detail.py::test_stale_v1_cannot_mask_current_v2` (E)
- `test_best_open_price_product_detail.py::test_explicit_v1_read_remains_possible` (F)

### Finding 2 — V1 response-shape compatibility was broken
Both `_best_open_price_contract` (Product Detail) and `_best_open_price_projection`'s per-row attachment (Product Rankings) unconditionally attached `ripBestOpenPrice`/`ripBestOpenPriceStatus`/`ripBestOpenPriceGapDollars`/`ripBestOpenPriceGapPercent` whenever a row existed, regardless of method version — this is exactly what broke real CI's `test_product_detail_best_open_contract_preserves_dated_ranking_source` (it asserts the historical exact V1 shape with zero new fields).

Fix: both call sites now gate `ripBestOpenPrice*` (and, unchanged in spirit, `financialBestOpenPrice*`) behind `prepared.get("methodVersion") == BEST_OPEN_PRICE_V2_METHOD_VERSION` (verified constant: `budget_product_best_open_price_full_market_v2_dual_financial_v4_overall_v12`, from `backend/calculations/evr/best_open_price.py`). A V1-served row's contract is now byte-identical to the historical shape again. The V1 exact-shape test's expected dict was NOT expanded — it still asserts the historical shape with no V2 fields; the fix was in the implementation, and the test was restructured only to spy on the CURRENT-selection call sequence (Finding 1), not to weaken its shape assertion. A new positive test (`test_current_v2_is_selected_when_available` / `test_v2_full_market_projection_attaches_both_rip_and_financial_fields`) asserts the V2 fields DO appear when serving a V2 result.

### Finding 3 — the real Postgres V2 fixture was broken
`backend/tests/integration/test_best_open_publication_v2_postgres.py`'s disposable-Postgres fixture created `budget_product_ranking_rows` without a `financial_only_rank` column, even though the V2 RPC branch (migration `20260916120000_add_best_open_price_v2_dual_threshold.sql`, ~line 651/704) validates `live.financial_only_rank` against the row payload's `current_financial_only_rank`. Real CI (`postgres:17.11`) hit `column live.financial_only_rank does not exist` on all 5 V2 success-path tests.

Fix: added `financial_only_rank int` to the fixture's `CREATE TABLE budget_product_ranking_rows` DDL, and the `seed` fixture now inserts each row's `current_budget_rank` value into it — this exactly mirrors `fixture_payload_v2()`'s own derivation of `current_financial_only_rank=n` (where `n == current_budget_rank` for this fixture's 3-row cohort), so the live cross-check and the row payload's declared value always agree for a valid V2 publish, and still correctly diverge for the mutation-rejection tests that explicitly perturb `current_financial_only_rank`. The RPC's live validation itself was not touched — only the fixture was fixed.

### Validation
- Focused local service tests: `python -m pytest backend/tests/unit/db/services/test_budget_product_best_open_price_service.py backend/tests/unit/db/services/test_public_overall_product_rankings_service.py backend/tests/unit/db/services/test_pokemon_sealed_product_detail_service.py backend/tests/unit/db/services/test_best_open_price_product_detail.py backend/tests/unit/db/services/test_best_open_price_public_projection.py backend/tests/unit/db/services/test_budget_product_best_open_price_product_reader.py backend/tests/unit/db/test_best_open_price_v2_migration_sql.py backend/tests/unit/db/test_budget_product_best_open_price_migration_sql.py -q` → **140 passed, 0 failed**.
- `backend/tests/integration/test_best_open_publication_v2_postgres.py` + the V1 file: **73 skipped** locally (no Docker/Postgres in this worktree, same honest-skip convention as before) — real execution deferred to CI's `postgres-integration` job.
- `git diff --check`: clean.
- Real GitHub Actions verification: see the final status line below for whether this could be confirmed via `gh` in this session, and the exact job-by-job / run results if so.

