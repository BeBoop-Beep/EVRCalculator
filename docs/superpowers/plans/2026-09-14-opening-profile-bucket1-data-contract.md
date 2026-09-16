# Opening Profile Bucket 1 Data Contract Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Give the four "explanatory opening metrics" (Average Return, Typical Opening, Covers Cost, Top 1% Value Share) a single source-coherent prepared-data contract across Product Family Rankings, Product Detail, Set RIP decision rows, and Budget Product Rankings — with Top 1% Value Share sourced exactly from `financial_rip_v3_payload.distributionDisclosures.jackpotValueShare`, never from the unrelated card-attribution metric `top1_ev_share`/`top1EvShare`.

**Architecture:** `financial_rip_v3_payload` (a JSONB column already produced by `build_financial_rip_v3` and already persisted on `simulation_sealed_product_results`) carries `distributionDisclosures.jackpotValueShare`. Three read paths (`product_family_rankings_service.py`, `pokemon_sealed_product_detail_service.py`, `rip_decision_service.py`) already read `simulation_sealed_product_results`/its repository for the SAME calculation run as their other financial fields; each needs only to (a) select the JSONB column if not already selected, and (b) pull one scalar out of it into its existing per-product dict, under a new key `topOneOutcomeValueShare`. The budget-strategy path is separate: `score_budget_strategy()` already builds its own q-unit V3 payload and discards it after computing V4; it needs to keep one more scalar (`topOneOutcomeValueShare`, from the SAME `v3_payload["distributionDisclosures"]["jackpotValueShare"]` key) alongside the `medianValue` it already returns, and both need a new nullable column pair on `budget_product_ranking_rows` plus additive exposure through the public projection and entitlement allowlist. No ranking score, RIP weight, or sort order changes anywhere in this plan.

**Tech Stack:** Python 3 backend (pytest), Supabase/Postgres migrations (plain `.sql` files, additive-only), no frontend changes in this bucket.

**Spec:** This plan's spec is the task brief itself (no separate spec doc); the verified-current file/line facts below come from a direct repo inspection of HEAD on `develop` performed immediately before writing this plan (commit `7341be85` head at inspection time — re-verify `HEAD` before starting Task 1, since this plan assumes no other change has landed on `develop` since).

## Global Constraints

- Do NOT modify ranking methodology, RIP weights, Best-Open methodology, Collector Appeal methodology, or public rank semantics. Every task in this plan is strictly additive (new field, new nullable column, new allowlist entry) — never touch `_tier_sort_key`, `rank_budget_cohort`, `compute_overall_rip_v10/v12`, `build_financial_rip_v3`'s scoring math, or any existing persisted column's meaning.
- Top 1% Value Share MUST read `financial_rip_v3_payload["distributionDisclosures"]["jackpotValueShare"]` exactly. NEVER `top1_ev_share` / `top1EvShare` / `financial_rip_v3_payload["depthAndRobustness"]["top1EvShare"]` — those are a card-level EV-concentration metric, a different quantity that happens to share the "top1" naming pattern (see `docs/DERIVED_METRICS_IMPLEMENTATION_NOTE.md:126`).
- Average Return in a budget strategy is `expected_value / actual_committed_capital`, never target budget or one-unit price.
- Do not send the full Financial V3 payload to the frontend merely to expose this scalar — extract the one scalar server-side and drop the payload.
- No N+1 detail-comparison reads: `pokemon_sealed_product_detail_service.py`'s "Same Set" comparison rows already come from the cached `pokemon_explore_rankings_snapshot_latest` payload (via `_ranking_rows`), not a per-product query — Task 6 must add the new field to that SAME cached-row shape (upstream in Task 5's `product_family_rankings_service.py` projection) rather than adding a new per-comparison-row query.
- Create an additive mirrored migration (new `.sql` file) for `budget_product_ranking_rows`; do not edit the original CREATE TABLE migration file.
- Do not apply migrations to production. Do not mutate the currently published production budget snapshot in this bucket.
- Basic (non-Index-Plus) plans must not receive any of the four new/extended numeric opening-analytics fields — gate at `FEATURE_PRODUCT_RIP` (Index Plus), matching the existing `expectedValue`/`chanceToRecoverCost` precedent in `backend/domain/access/index_plan_access.py`.
- New migration timestamp must be strictly greater than the current latest (`20260914231151_align_cards_market_constituents_with_root_set_value.sql`) and follow the `YYYYMMDDHHMMSS_snake_case_description.sql` convention.

---

### Task 0: Re-verify HEAD and baseline test pass

**Files:** none modified.

- [ ] **Step 1: Confirm branch/HEAD and clean tree**

Run: `git status && git log -1 --oneline`
Expected: `On branch develop`, clean working tree, HEAD matches (or is a descendant of) `7341be85`. If HEAD differs, re-read any file this plan quotes before trusting its line numbers.

- [ ] **Step 2: Confirm the four target read-path files and the source payload builder still match this plan's line citations**

Run (from repo root):
```bash
grep -n "RESULT_FIELDS = " backend/db/services/product_family_rankings_service.py
grep -n "DETAIL_FIELDS = " backend/db/services/pokemon_sealed_product_detail_service.py
grep -n "\"typicalOpening\"" backend/db/services/rip_decision_service.py
grep -n "distributionDisclosures" backend/calculations/evr/financial_rip_v3.py
grep -n "def score_budget_strategy" backend/calculations/evr/budget_normalized_product_ranking.py
```
Expected: all five greps return at least one match. If any file's surrounding code has meaningfully diverged from the snippets quoted in Tasks 2–9 below, stop and re-derive the exact insertion point from the live file before editing — do not blind-apply a stale diff.

---

### Task 1: Additive migration — `budget_product_ranking_rows` gains `median_value` and `top1_outcome_value_share`

**Files:**
- Create: `backend/db/migrations/20260915000000_add_median_and_top1_value_share_to_budget_product_ranking_rows.sql`
- Test: `backend/tests/unit/db/test_budget_product_ranking_median_top1_migration_sql.py`

**Interfaces:**
- Produces: two new nullable columns `median_value NUMERIC` and `top1_outcome_value_share NUMERIC` on `budget_product_ranking_rows`, consumed by Task 3 (persist) and Task 4 (public projection).

- [ ] **Step 1: Write the migration SQL**

```sql
-- Additive only: two nullable columns carrying the same q-unit budget
-- strategy's median outcome value and Top-1%-of-outcomes value share
-- (financial_rip_v3_payload.distributionDisclosures.jackpotValueShare of
-- the SAME simulated distribution score_budget_strategy() already scores).
-- No backfill: historical snapshots simply carry NULL here, exactly like
-- 20260825154658_expose_budget_product_strategy_expected_value.sql did for
-- expected_value before its one-time backfill (this migration adds no
-- backfill since these two fields have never been computed for any
-- previously published row).
ALTER TABLE budget_product_ranking_rows
    ADD COLUMN IF NOT EXISTS median_value NUMERIC,
    ADD COLUMN IF NOT EXISTS top1_outcome_value_share NUMERIC;

COMMENT ON COLUMN budget_product_ranking_rows.median_value IS
    'Median modeled opening value of the exact q-unit budget strategy distribution (score_budget_strategy medianValue).';
COMMENT ON COLUMN budget_product_ranking_rows.top1_outcome_value_share IS
    'Share of total modeled strategy value contributed by the highest-value 1% of modeled outcomes, sourced from financial_rip_v3_payload.distributionDisclosures.jackpotValueShare for the SAME q-unit strategy run. Never the card-attribution top1_ev_share metric.';
```

- [ ] **Step 2: Write the migration contract test**

```python
from pathlib import Path

MIGRATION_PATH = Path(__file__).resolve().parents[3] / "db" / "migrations" / \
    "20260915000000_add_median_and_top1_value_share_to_budget_product_ranking_rows.sql"


def test_migration_file_exists():
    assert MIGRATION_PATH.exists()


def test_migration_is_additive_only():
    sql = MIGRATION_PATH.read_text()
    assert "ADD COLUMN IF NOT EXISTS median_value NUMERIC" in sql
    assert "ADD COLUMN IF NOT EXISTS top1_outcome_value_share NUMERIC" in sql
    forbidden = ("DROP TABLE", "DROP COLUMN", "ALTER COLUMN", "TRUNCATE", "DELETE FROM")
    upper_sql = sql.upper()
    for token in forbidden:
        assert token not in upper_sql, f"migration must be additive-only, found {token}"


def test_migration_targets_correct_table():
    sql = MIGRATION_PATH.read_text()
    assert "ALTER TABLE budget_product_ranking_rows" in sql
```

- [ ] **Step 3: Run the test to verify it fails before the file exists, then passes after**

Run: `cd backend && python -m pytest tests/unit/db/test_budget_product_ranking_median_top1_migration_sql.py -v`
Expected: FAIL (`FileNotFoundError`-style assertion) before Step 1 is saved, PASS after.

- [ ] **Step 4: Commit**

```bash
git add backend/db/migrations/20260915000000_add_median_and_top1_value_share_to_budget_product_ranking_rows.sql backend/tests/unit/db/test_budget_product_ranking_median_top1_migration_sql.py
git commit -m "feat(db): add median_value/top1_outcome_value_share columns to budget_product_ranking_rows"
```

---

### Task 2: `score_budget_strategy()` returns `topOneOutcomeValueShare`

**Files:**
- Modify: `backend/calculations/evr/budget_normalized_product_ranking.py:308-328` (the `return {...}` of `score_budget_strategy`)
- Test: `backend/tests/unit/calculations/test_budget_normalized_product_ranking.py`

**Interfaces:**
- Consumes: `v3_payload` (already computed at line 281 inside `score_budget_strategy` via `build_financial_rip_v3(values, actual_committed_capital, **v3_kwargs)`), specifically `v3_payload["distributionDisclosures"]["jackpotValueShare"]`.
- Produces: `score_budget_strategy(...)["topOneOutcomeValueShare"]: Optional[float]`, `score_budget_strategy(...)["medianValue"]: float` (already existed, unchanged — confirmed present at current line 324). Consumed by Task 3.

- [ ] **Step 1: Write the failing test**

```python
def test_score_budget_strategy_exposes_top1_outcome_value_share_from_v3_distribution_disclosures():
    values = np.array([0.0] * 970 + [50.0] * 20 + [5000.0] * 10, dtype=float)
    result = score_budget_strategy(values, actual_committed_capital=100.0, collector_appeal_score=50.0)
    v3_payload = build_financial_rip_v3(values, 100.0)
    assert result["topOneOutcomeValueShare"] == v3_payload["distributionDisclosures"]["jackpotValueShare"]
    assert result["topOneOutcomeValueShare"] is not None


def test_score_budget_strategy_top1_outcome_value_share_is_not_the_card_attribution_metric():
    # Guard against ever wiring the wrong "top1" metric: depthAndRobustness's
    # top1EvShare is a card-EV-contribution metric, a different number from
    # the outcome-distribution jackpotValueShare this field must carry.
    values = np.array([0.0] * 970 + [50.0] * 20 + [5000.0] * 10, dtype=float)
    result = score_budget_strategy(values, actual_committed_capital=100.0, collector_appeal_score=50.0)
    v3_payload = build_financial_rip_v3(values, 100.0)
    depth_top1_ev_share = (v3_payload.get("depthAndRobustness") or {}).get("top1EvShare")
    # These two source values are independent quantities; asserting the
    # scored field matches jackpotValueShare (previous test) already proves
    # it, but this test additionally documents that top1EvShare is NOT an
    # acceptable substitute even when both happen to be present.
    assert "topOneOutcomeValueShare" in result
    assert result["topOneOutcomeValueShare"] == v3_payload["distributionDisclosures"]["jackpotValueShare"]
```

Add these next to the existing `score_budget_strategy` tests in `backend/tests/unit/calculations/test_budget_normalized_product_ranking.py` (import `build_financial_rip_v3` from `backend.calculations.evr.financial_rip_v3` at the top of the test file if not already imported; `numpy as np` is already used in that file).

- [ ] **Step 2: Run test to verify it fails**

Run: `cd backend && python -m pytest tests/unit/calculations/test_budget_normalized_product_ranking.py -k top1_outcome_value_share -v`
Expected: FAIL with `KeyError: 'topOneOutcomeValueShare'`.

- [ ] **Step 3: Implement — add the field to the return dict**

In `backend/calculations/evr/budget_normalized_product_ranking.py`, inside `score_budget_strategy`, add a line right after `v3_payload = build_financial_rip_v3(...)` (line 281) to capture the scalar before it would otherwise be discarded:

```python
    v3_payload = build_financial_rip_v3(values, actual_committed_capital, **v3_kwargs)
    top1_outcome_value_share = (v3_payload.get("distributionDisclosures") or {}).get("jackpotValueShare")
    v4_payload = project_financial_rip_v4_from_v3_payload(v3_payload)
```

Then add one key to the final `return {...}` block (after `"medianValue": float(np.median(values)),` at line 324):

```python
        "medianValue": float(np.median(values)),
        "topOneOutcomeValueShare": top1_outcome_value_share,
        "chanceToRecoverCapital": chance_to_recover_capital,
```

- [ ] **Step 4: Run test to verify it passes**

Run: `cd backend && python -m pytest tests/unit/calculations/test_budget_normalized_product_ranking.py -v`
Expected: all PASS (both new tests, and every pre-existing test in the file still passes unchanged — this proves the new field is additive).

- [ ] **Step 5: Commit**

```bash
git add backend/calculations/evr/budget_normalized_product_ranking.py backend/tests/unit/calculations/test_budget_normalized_product_ranking.py
git commit -m "feat(evr): expose topOneOutcomeValueShare from score_budget_strategy's V3 distribution disclosures"
```

---

### Task 3: Persist `median_value` / `top1_outcome_value_share` in the budget ranking build/publish path

**Files:**
- Modify: `backend/scripts/build_budget_normalized_product_rankings.py:585-617` (`to_publication_payload`'s row-building loop)
- Test: `backend/tests/unit/scripts/test_build_budget_product_rankings_payload.py`

**Interfaces:**
- Consumes: `row["medianValue"]` and `row["topOneOutcomeValueShare"]` — both already present on every `ranked` row dict because line 192 of the same file does `**scored` (the full `score_budget_strategy` return dict) into each strategy row before ranking; Task 2 already added `topOneOutcomeValueShare` to that dict, so no change is needed above `to_publication_payload`.
- Produces: `rows[i]["median_value"]` and `rows[i]["top1_outcome_value_share"]` in the flattened snapshot/rows tuple returned by `to_publication_payload`, consumed by the publication RPC (Task 1's new columns) and by Task 4's read path.

- [ ] **Step 1: Write the failing test**

Find the existing test that exercises `to_publication_payload` (likely named something like `test_to_publication_payload_flattens_...`) in `backend/tests/unit/scripts/test_build_budget_product_rankings_payload.py` and add:

```python
def test_to_publication_payload_carries_median_and_top1_outcome_value_share():
    results = _minimal_results_fixture()  # reuse this file's existing fixture helper
    # Ensure the fixture's row(s) carry the two new scored fields, as a real
    # score_budget_strategy() call now always does post-Task-2.
    for block in results["budgets"].values():
        for row in block["rows"]:
            row["medianValue"] = 123.45
            row["topOneOutcomeValueShare"] = 0.0271

    _snapshot, rows = to_publication_payload(results)

    assert rows, "expected at least one row from the fixture"
    for row in rows:
        assert row["median_value"] == 123.45
        assert row["top1_outcome_value_share"] == 0.0271
```

If `_minimal_results_fixture()` is not the actual existing helper name, use whatever fixture-building helper the file already defines for `to_publication_payload` tests — inspect the file first and reuse it verbatim rather than inventing a new one.

- [ ] **Step 2: Run test to verify it fails**

Run: `cd backend && python -m pytest tests/unit/scripts/test_build_budget_product_rankings_payload.py -k median_and_top1 -v`
Expected: FAIL with `KeyError: 'median_value'`.

- [ ] **Step 3: Implement — add the two fields to the row dict**

In `backend/scripts/build_budget_normalized_product_rankings.py`, inside `to_publication_payload`'s `for row in block["rows"]:` loop (starting line 587), add two lines to the `rows.append({...})` dict, right after `"expected_value": row["expectedValue"],` (line 607):

```python
                "expected_value": row["expectedValue"],
                "median_value": row.get("medianValue"),
                "top1_outcome_value_share": row.get("topOneOutcomeValueShare"),
                "product_market_price": row["productMarketPrice"],
```

- [ ] **Step 4: Run test to verify it passes**

Run: `cd backend && python -m pytest tests/unit/scripts/test_build_budget_product_rankings_payload.py -v`
Expected: all PASS, including every pre-existing test in the file (proves this is additive to the row shape, not a breaking rename).

- [ ] **Step 5: Commit**

```bash
git add backend/scripts/build_budget_normalized_product_rankings.py backend/tests/unit/scripts/test_build_budget_product_rankings_payload.py
git commit -m "feat(scripts): persist median_value/top1_outcome_value_share on published budget ranking rows"
```

---

### Task 4: Budget Product Rankings read path — public projection exposes `medianValue`, `topOneOutcomeValueShare`, `averageReturn`

**Files:**
- Modify: `backend/db/services/budget_product_ranking_service.py:35-42` (`PUBLIC_ROW_FIELDS`), `:286-321` (`project()` inside `build_public_overall_projection`)
- Test: `backend/tests/unit/db/services/test_budget_product_ranking_public_projection_contract.py`

**Interfaces:**
- Consumes: `row["median_value"]`, `row["top1_outcome_value_share"]`, `row["expected_value"]`, `row["actual_committed_capital"]` (all already selected or addable via `PUBLIC_ROW_FIELDS`).
- Produces: `cohorts[*]["rows"][*]["medianValue"]`, `["topOneOutcomeValueShare"]`, `["averageReturn"]` in `build_public_overall_projection`'s return value. `averageReturn = expected_value / actual_committed_capital` (never target budget, never one-unit price — per the Global Constraints line).

- [ ] **Step 1: Write the failing test**

```python
def test_public_overall_projection_exposes_median_top1_and_average_return():
    client = _fake_client_with_one_row(  # reuse this test file's existing fake-client helper
        expected_value=120.0,
        actual_committed_capital=100.0,
        median_value=80.0,
        top1_outcome_value_share=0.031,
    )
    projection = build_public_overall_projection(client, product_family_rankings={"families": {}})
    assert projection["available"] is True
    row = next(iter(projection["cohorts"].values()))["rows"][0]
    assert row["medianValue"] == 80.0
    assert row["topOneOutcomeValueShare"] == 0.031
    assert row["averageReturn"] == 120.0 / 100.0


def test_public_overall_projection_average_return_denominator_is_committed_capital_not_target_budget():
    # A cohort's target_budget (e.g. the $50 band) can differ from what was
    # actually spent (actual_committed_capital, e.g. $48 after whole-unit
    # rounding) - averageReturn must divide by the latter, never the former.
    client = _fake_client_with_one_row(
        expected_value=60.0,
        actual_committed_capital=48.0,
        target_budget=50.0,
        median_value=40.0,
        top1_outcome_value_share=0.02,
    )
    projection = build_public_overall_projection(client, product_family_rankings={"families": {}})
    row = next(iter(projection["cohorts"].values()))["rows"][0]
    assert row["averageReturn"] == 60.0 / 48.0
    assert row["averageReturn"] != 60.0 / 50.0
```

Use whichever fake-Supabase-client helper the existing tests in this file already use to stub `client.table(...).select(...).eq(...)...execute()`; extend it (or add a thin wrapper) so it can set `median_value`/`top1_outcome_value_share`/`target_budget` on the row, matching the existing helper's parameter style.

- [ ] **Step 2: Run test to verify it fails**

Run: `cd backend && python -m pytest tests/unit/db/services/test_budget_product_ranking_public_projection_contract.py -k "median_top1_and_average_return or denominator_is_committed_capital" -v`
Expected: FAIL with `KeyError: 'medianValue'`.

- [ ] **Step 3: Implement**

In `backend/db/services/budget_product_ranking_service.py`, extend `PUBLIC_ROW_FIELDS` (lines 35-42):

```python
PUBLIC_ROW_FIELDS = (
    "sealed_product_id,set_id,product_family,target_budget,budget_type,quantity,"
    "actual_committed_capital,unused_capital,capital_utilization,budget_rank,"
    "budget_cohort_size,budget_tier,financial_rip_v4_score,overall_rip_v10_score,"
    "collector_appeal_score,chance_to_recover_capital,product_market_price,"
    "expected_value,median_value,top1_outcome_value_share,source_calculation_run_id,"
    "overall_rip_v12_score,budget_rank_v12,budget_cohort_size_v12"
)
```

Then in `project()` (inside `build_public_overall_projection`, starting line 286), add three lines after `"expectedValue": row.get("expected_value"),` (line 315):

```python
            "expectedValue": row.get("expected_value"),
            "medianValue": row.get("median_value"),
            "topOneOutcomeValueShare": row.get("top1_outcome_value_share"),
            "averageReturn": (
                row.get("expected_value") / row.get("actual_committed_capital")
                if row.get("expected_value") is not None
                and row.get("actual_committed_capital")
                else None
            ),
            "chanceToRecoverCapital": row.get("chance_to_recover_capital"),
```

- [ ] **Step 4: Run test to verify it passes**

Run: `cd backend && python -m pytest tests/unit/db/services/test_budget_product_ranking_public_projection_contract.py -v`
Expected: all PASS, including pre-existing tests in the file (proves the projection change is additive and doesn't alter `budgetRank`/`overallRipScore`/any existing field's value).

- [ ] **Step 5: Commit**

```bash
git add backend/db/services/budget_product_ranking_service.py backend/tests/unit/db/services/test_budget_product_ranking_public_projection_contract.py
git commit -m "feat(db): expose medianValue/topOneOutcomeValueShare/averageReturn in budget public overall projection"
```

---

### Task 5: Product Family Rankings — `topOneOutcomeValueShare` sourced from the same calculation run

**Files:**
- Modify: `backend/db/services/product_family_rankings_service.py:29-38` (`RESULT_FIELDS`), `:172-235` area (`_project`)
- Test: `backend/tests/unit/db/services/test_product_family_rankings_service.py`

**Interfaces:**
- Consumes: adds `financial_rip_v3_payload` to the `RESULT_FIELDS` select-list read from `simulation_sealed_product_results` (same query, same `calculation_run_id` filter as every other field on the row — this is the "exact same calculation run" guarantee).
- Produces: `_project(...)["topOneOutcomeValueShare"]: Optional[float]`, consumed downstream by Task 6 (Product Detail's cached comparison rows reuse this SAME published projection) and Task 8 (entitlement allowlist).

- [ ] **Step 1: Write the failing test**

```python
def test_project_exposes_top1_outcome_value_share_from_financial_rip_v3_payload():
    row = _minimal_result_row_fixture()  # reuse this test file's existing row-fixture helper
    row["financial_rip_v3_payload"] = {
        "distributionDisclosures": {"jackpotValueShare": 0.0417},
        "depthAndRobustness": {"top1EvShare": 0.999},  # must NOT be read
    }
    projected = _project(row, identity={}, rank=1, size=1)
    assert projected["topOneOutcomeValueShare"] == 0.0417


def test_project_top1_outcome_value_share_none_when_payload_missing():
    row = _minimal_result_row_fixture()
    row.pop("financial_rip_v3_payload", None)
    projected = _project(row, identity={}, rank=1, size=1)
    assert projected["topOneOutcomeValueShare"] is None


def test_result_fields_selects_financial_rip_v3_payload_for_the_jackpot_disclosure():
    assert "financial_rip_v3_payload" in RESULT_FIELDS
```

Import `RESULT_FIELDS` and `_project` from `backend.db.services.product_family_rankings_service`; reuse whatever row-fixture helper the existing tests in this file already call (inspect the file first — do not invent a new fixture shape if one exists).

- [ ] **Step 2: Run test to verify it fails**

Run: `cd backend && python -m pytest tests/unit/db/services/test_product_family_rankings_service.py -k top1_outcome_value_share -v`
Expected: FAIL with `KeyError: 'topOneOutcomeValueShare'`.

- [ ] **Step 3: Implement**

In `backend/db/services/product_family_rankings_service.py`, add `financial_rip_v3_payload` to the `RESULT_FIELDS` constant (lines 29-38) — insert it near the other `financial_rip_v3_*` scalars already there (`financial_rip_v3_score, financial_rip_v3_version`):

```python
RESULT_FIELDS = (
    "..., financial_rip_v3_score, financial_rip_v3_version, financial_rip_v3_payload, "
    "financial_rip_v4_score, financial_rip_v4_version, ..."
)
```//(insert `financial_rip_v3_payload,` immediately after `financial_rip_v3_version,` in the real comma-joined string — match the existing string's exact formatting rather than reformatting the whole constant.)

Then in `_project` (around line 220-232), add one key after `"chanceToRecoverCost": row.get("chance_to_recover_cost"),`:

```python
        "chanceToRecoverCost": row.get("chance_to_recover_cost"),
        "topOneOutcomeValueShare": (
            (row.get("financial_rip_v3_payload") or {}).get("distributionDisclosures") or {}
        ).get("jackpotValueShare"),
        "totalValueToCostRatio": row.get("total_value_to_cost_ratio"),
```

- [ ] **Step 4: Run test to verify it passes**

Run: `cd backend && python -m pytest tests/unit/db/services/test_product_family_rankings_service.py -v`
Expected: all PASS, including every pre-existing test (proves ranks/scores/ordering in `build_product_family_rankings` are untouched — this task only adds a field to `_project`'s output dict).

- [ ] **Step 5: Commit**

```bash
git add backend/db/services/product_family_rankings_service.py backend/tests/unit/db/services/test_product_family_rankings_service.py
git commit -m "feat(db): expose topOneOutcomeValueShare on product family rankings from the same calculation run"
```

---

### Task 6: Product Detail — expose `topOneOutcomeValueShare` without a new N+1 read

**Files:**
- Modify: `backend/db/services/pokemon_sealed_product_detail_service.py:30-36` (`DETAIL_FIELDS`), `:~411-459` (`_rip_contract`'s success return)
- Test: `backend/tests/unit/db/services/test_pokemon_sealed_product_detail_service.py` (create if no such file exists per Task-0-adjacent finding; check first with `ls backend/tests/unit/db/services/ | grep -i sealed_product_detail`)

**Interfaces:**
- Consumes: adds `financial_rip_v3_payload` to `DETAIL_FIELDS` (the single targeted per-focal-product read already done by `get_pokemon_sealed_product_detail_payload`, lines ~531-538 — NOT a new query, just one more column on the existing single-row read). The "Same Set" comparison rows continue to come from `_ranking_rows(payload)` (the cached `pokemon_explore_rankings_snapshot_latest` snapshot) which already carries `topOneOutcomeValueShare` once Task 5's build runs and republishes that snapshot — no code change needed for the comparison rows themselves.
- Produces: `_rip_contract(...)["topOneOutcomeValueShare"]`, alongside the existing `"medianValue"`/`"chanceToRecoverCost"` keys at that same level.

- [ ] **Step 1: Check for an existing test file, then write the failing test**

Run: `cd backend && grep -rl "pokemon_sealed_product_detail" tests/unit/db/services/ 2>/dev/null`

If a file is found, add the test there; if none exists, create `backend/tests/unit/db/services/test_pokemon_sealed_product_detail_service.py` following the same fixture/mocking pattern as `test_product_family_rankings_service.py` (a fake Supabase client stubbing `.table(...).select(...).eq(...).execute()`).

```python
def test_rip_contract_exposes_top1_outcome_value_share_from_same_focal_row():
    detail_row = _minimal_detail_row_fixture()  # match this file's existing row shape
    detail_row["financial_rip_v3_payload"] = {
        "distributionDisclosures": {"jackpotValueShare": 0.0555},
    }
    contract = _rip_contract(detail_row)  # or via the public entry point if _rip_contract takes more args
    assert contract["topOneOutcomeValueShare"] == 0.0555


def test_detail_fields_selects_financial_rip_v3_payload():
    assert "financial_rip_v3_payload" in DETAIL_FIELDS


def test_detail_payload_does_not_issue_extra_query_per_comparison_row(monkeypatch):
    # Regression guard: the comparison ("Same Set") rows must come from the
    # cached rankings snapshot, never from a per-row simulation_sealed_product_results
    # query. Count calls to the detail-focused query builder and assert it is
    # invoked exactly once (for the focal product), regardless of comparison
    # cohort size.
    call_count = {"n": 0}
    original = get_pokemon_sealed_product_detail_payload  # reuse existing entry point under test in this file
    # Wrap the client's .table("simulation_sealed_product_results") accessor
    # to count invocations; assert call_count["n"] == 1 after one full
    # get_pokemon_sealed_product_detail_payload(...) call against a fixture
    # with e.g. 12 same-set comparison products.
    ...  # follow whatever query-counting helper this file's other N+1 tests already use, if one exists; otherwise implement a minimal counting wrapper around the fake client's `.table` method.
```

Note: Step 1's third test is a *regression guard*, not new behavior — if the file already has an equivalent "no N+1" test for this service, extend it to also cover the new field's read path rather than duplicating a whole new test.

- [ ] **Step 2: Run test to verify it fails**

Run: `cd backend && python -m pytest backend/tests/unit/db/services/test_pokemon_sealed_product_detail_service.py -k top1_outcome_value_share -v`
Expected: FAIL with `KeyError: 'topOneOutcomeValueShare'`.

- [ ] **Step 3: Implement**

In `backend/db/services/pokemon_sealed_product_detail_service.py`, add `financial_rip_v3_payload` to `DETAIL_FIELDS` (lines 30-36), matching the same comma-string style as Task 5.

In `_rip_contract`'s success-path return dict (around lines 411-459), add one key after `"chanceToRecoverCost": detail.get("chance_to_recover_cost"),`:

```python
        "chanceToRecoverCost": detail.get("chance_to_recover_cost"),
        "topOneOutcomeValueShare": (
            (detail.get("financial_rip_v3_payload") or {}).get("distributionDisclosures") or {}
        ).get("jackpotValueShare"),
        "expectedLossWhenLosing": detail.get("expected_loss_when_losing"),
```

- [ ] **Step 4: Run test to verify it passes**

Run: `cd backend && python -m pytest backend/tests/unit/db/services/test_pokemon_sealed_product_detail_service.py -v`
Expected: all PASS.

- [ ] **Step 5: Commit**

```bash
git add backend/db/services/pokemon_sealed_product_detail_service.py backend/tests/unit/db/services/test_pokemon_sealed_product_detail_service.py
git commit -m "feat(db): expose topOneOutcomeValueShare on product detail focal-product read, no new N+1 query"
```

---

### Task 7: Set RIP decision rows — `ripDecision.sealedProducts.products[]` gains `topOneOutcomeValueShare`

**Files:**
- Modify: `backend/db/services/rip_decision_service.py:208-259` (`_product_decision_row`)
- Test: `backend/tests/unit/db/services/test_rip_decision_service.py`

**Interfaces:**
- Consumes: `row.get("financial_rip_v3_payload")` — already selected by `backend/db/repositories/sealed_product_results_repository.py`'s `_SELECT_FIELDS` (confirmed present, line 28: `"financial_rip_v3_version,financial_rip_v3_payload,"`), which is what feeds every row `_product_decision_row` receives. No repository change needed.
- Produces: `_product_decision_row(row)["topOneOutcomeValueShare"]`, bound to the SAME `row["calculation_run_id"]` already used for `sourceCalculationRunId` on that row — verify this binding explicitly in the test (Step 1).

- [ ] **Step 1: Write the failing test**

```python
def test_product_decision_row_exposes_top1_outcome_value_share_bound_to_its_own_run():
    row = _minimal_decision_row_fixture()  # reuse this test file's existing fixture helper
    row["calculation_run_id"] = "run-abc"
    row["financial_rip_v3_payload"] = {
        "distributionDisclosures": {"jackpotValueShare": 0.0623},
    }
    decision_row = _product_decision_row(row)
    assert decision_row["topOneOutcomeValueShare"] == 0.0623
    assert decision_row["sourceCalculationRunId"] == "run-abc"


def test_product_decision_row_top1_outcome_value_share_none_when_payload_absent():
    row = _minimal_decision_row_fixture()
    row.pop("financial_rip_v3_payload", None)
    decision_row = _product_decision_row(row)
    assert decision_row["topOneOutcomeValueShare"] is None


def test_product_decision_row_never_reads_card_attribution_top1_ev_share():
    # A row whose depthAndRobustness.top1EvShare differs from
    # distributionDisclosures.jackpotValueShare must still surface the
    # LATTER - proves no accidental fallback to the wrong metric.
    row = _minimal_decision_row_fixture()
    row["financial_rip_v3_payload"] = {
        "distributionDisclosures": {"jackpotValueShare": 0.01},
        "depthAndRobustness": {"top1EvShare": 0.99},
    }
    decision_row = _product_decision_row(row)
    assert decision_row["topOneOutcomeValueShare"] == 0.01
```

- [ ] **Step 2: Run test to verify it fails**

Run: `cd backend && python -m pytest backend/tests/unit/db/services/test_rip_decision_service.py -k top1_outcome_value_share -v`
Expected: FAIL with `KeyError: 'topOneOutcomeValueShare'`.

- [ ] **Step 3: Implement**

In `backend/db/services/rip_decision_service.py`, in `_product_decision_row` (around line 244-246), add one key after `"typicalOpening": _optional_float(row.get("median_value")),`:

```python
        "typicalOpening": _optional_float(row.get("median_value")),
        "topOneOutcomeValueShare": (
            (row.get("financial_rip_v3_payload") or {}).get("distributionDisclosures") or {}
        ).get("jackpotValueShare"),
        "chanceToRecoverCost": _optional_float(row.get("chance_to_recover_cost")),
```

- [ ] **Step 4: Run test to verify it passes**

Run: `cd backend && python -m pytest backend/tests/unit/db/services/test_rip_decision_service.py backend/tests/unit/db/services/test_rip_decision_freshness.py -v`
Expected: all PASS, including every pre-existing test (proves `build_sealed_product_decision_contract`'s row ordering, `RIP_DECISION_CONTRACT_VERSION`, and every other existing field are untouched).

- [ ] **Step 5: Commit**

```bash
git add backend/db/services/rip_decision_service.py backend/tests/unit/db/services/test_rip_decision_service.py
git commit -m "feat(db): expose topOneOutcomeValueShare on Set RIP decision product rows, bound to their own calculation run"
```

---

### Task 8: Entitlement — Index Plus Product Rankings gain the compact explanatory fields; Basic strips them

**Files:**
- Modify: `backend/domain/access/index_plan_access.py:319-342` (`_PLUS_PRODUCT_RANKING_FIELDS`)
- Test: `backend/tests/unit/domain/access/test_index_plan_access.py`

**Interfaces:**
- Consumes: the field names already produced by Task 5 (`topOneOutcomeValueShare`, already-existing `medianValue`, already-existing `modeledReturnRatio`) on rows passed into `project_product_rankings_response` / `project_product_family_rankings_response`.
- Produces: those three field names added to `_PLUS_PRODUCT_RANKING_FIELDS` (Plus-gated, matching the existing `expectedValue`/`chanceToRecoverCost` precedent — `chanceToRecoverCost` is already present, so "Covers Cost" needs no allowlist change).

- [ ] **Step 1: Write the failing test**

```python
def test_plus_product_ranking_fields_include_opening_profile_bucket1_metrics():
    row = {
        "sealedProductId": "sp-1", "modeledReturnRatio": 1.4, "medianValue": 12.5,
        "chanceToRecoverCost": 0.6, "topOneOutcomeValueShare": 0.03,
    }
    payload = {"available": True, "rows": [row]}
    plus_plan = _plan_with_feature(FEATURE_PRODUCT_RIP)  # reuse this test file's existing plan-fixture helper
    result = project_product_rankings_response(payload, plus_plan)
    projected_row = result["rows"][0]
    for field in ("modeledReturnRatio", "medianValue", "chanceToRecoverCost", "topOneOutcomeValueShare"):
        assert field in projected_row, field


def test_basic_plan_strips_opening_profile_bucket1_metrics():
    row = {
        "sealedProductId": "sp-1", "modeledReturnRatio": 1.4, "medianValue": 12.5,
        "chanceToRecoverCost": 0.6, "topOneOutcomeValueShare": 0.03,
    }
    payload = {"available": True, "rows": [row]}
    basic_plan = _plan_without_feature(FEATURE_PRODUCT_RIP)  # reuse this test file's existing plan-fixture helper
    result = project_product_rankings_response(payload, basic_plan)
    projected_row = result["rows"][0]
    for field in ("modeledReturnRatio", "medianValue", "chanceToRecoverCost", "topOneOutcomeValueShare"):
        assert field not in projected_row, field
    assert "sealedProductId" in projected_row  # base field still present
```

Reuse whatever plan-fixture helpers (`_plan_with_feature`/`_plan_without_feature` or equivalent) the existing tests in `test_index_plan_access.py` already use — inspect the file first rather than inventing new names.

- [ ] **Step 2: Run test to verify it fails**

Run: `cd backend && python -m pytest backend/tests/unit/domain/access/test_index_plan_access.py -k opening_profile_bucket1 -v`
Expected: FAIL (`modeledReturnRatio`/`medianValue`/`topOneOutcomeValueShare` missing from the Plus-plan projected row).

- [ ] **Step 3: Implement**

In `backend/domain/access/index_plan_access.py`, extend `_PLUS_PRODUCT_RANKING_FIELDS` (lines 323-342):

```python
_PLUS_PRODUCT_RANKING_FIELDS = _BASE_PRODUCT_RANKING_FIELDS | frozenset({
    "budgetRank", "budgetCohortSize", "budgetTier", "budgetModelTier", "publicTier",
    "overallRipScore",
    "financialRipScore", "overallRipAbsoluteScore", "overallRipRelativeScore",
    "overallRipLeaderScore", "financialRipAbsoluteScore", "financialRipRelativeScore",
    "financialRipLeaderScore", "collectorAppealScore", "expectedValue",
    "chanceToRecoverCost", "familyRank", "familySize", "familyTier",
    # ... (existing chaseAccessibility comment/entry unchanged) ...
    "chaseAccessibility",
    # Opening Profile Bucket 1 (compact explanatory opening metrics):
    # Average Return (modeledReturnRatio), Typical Opening (medianValue),
    # Covers Cost (chanceToRecoverCost, already above) and Top 1% Value
    # Share (topOneOutcomeValueShare, sourced ONLY from
    # financial_rip_v3_payload.distributionDisclosures.jackpotValueShare -
    # never the card-attribution top1EvShare metric).
    "modeledReturnRatio", "medianValue", "topOneOutcomeValueShare",
})
```

- [ ] **Step 4: Run test to verify it passes**

Run: `cd backend && python -m pytest backend/tests/unit/domain/access/test_index_plan_access.py -v`
Expected: all PASS, including every pre-existing test in the file (proves no other Plus/Basic field visibility changed).

- [ ] **Step 5: Commit**

```bash
git add backend/domain/access/index_plan_access.py backend/tests/unit/domain/access/test_index_plan_access.py
git commit -m "feat(access): gate Opening Profile Bucket 1 explanatory metrics at Index Plus product rankings"
```

---

### Task 9: Full regression sweep — ranks/scores untouched, no request-time simulation introduced

**Files:** none modified (verification-only task).

**Interfaces:** none — this task only runs existing + new tests together and inspects diffs for scope creep.

- [ ] **Step 1: Run every affected backend test module together**

Run:
```bash
cd backend && python -m pytest \
  tests/unit/db/test_budget_product_ranking_median_top1_migration_sql.py \
  tests/unit/calculations/test_budget_normalized_product_ranking.py \
  tests/unit/scripts/test_build_budget_product_rankings_payload.py \
  tests/unit/scripts/test_publish_budget_product_rankings_if_ready.py \
  tests/unit/scripts/test_build_budget_normalized_product_rankings_v12_publication.py \
  tests/unit/db/services/test_budget_product_ranking_service.py \
  tests/unit/db/services/test_budget_product_ranking_authority.py \
  tests/unit/db/services/test_budget_product_ranking_public_projection_contract.py \
  tests/unit/db/services/test_budget_product_ranking_readiness.py \
  tests/unit/db/services/test_budget_product_ranking_v12_readiness.py \
  tests/unit/db/test_budget_product_ranking_migration_sql.py \
  tests/unit/db/test_budget_product_ranking_hardening_migration_sql.py \
  tests/unit/db/test_budget_product_ranking_v12_migration_contract.py \
  tests/unit/db/test_extend_budget_product_ranking_publication_rpc_v12_atomic_migration_contract.py \
  tests/unit/db/services/test_product_family_rankings_service.py \
  tests/unit/db/services/test_pokemon_sealed_product_detail_service.py \
  tests/unit/db/services/test_rip_decision_service.py \
  tests/unit/db/services/test_rip_decision_freshness.py \
  tests/unit/domain/test_rip_decision_metrics.py \
  tests/unit/domain/access/test_index_plan_access.py \
  tests/unit/api/test_market_explorer_premium_gate.py \
  -v
```
Expected: 100% pass. Any failure outside the tests added in Tasks 1-8 indicates an unintended behavior change — stop and diagnose before proceeding (do not silently adjust an unrelated existing test's expected value).

- [ ] **Step 2: Grep-verify no request-time simulation/scoring was introduced**

Run:
```bash
cd backend && git diff main...HEAD --unified=0 -- \
  backend/db/services/product_family_rankings_service.py \
  backend/db/services/pokemon_sealed_product_detail_service.py \
  backend/db/services/rip_decision_service.py \
  backend/db/services/budget_product_ranking_service.py \
  backend/calculations/evr/budget_normalized_product_ranking.py \
  backend/scripts/build_budget_normalized_product_rankings.py \
  backend/domain/access/index_plan_access.py \
  | grep -Ei "build_financial_rip_v3\(|score_budget_strategy\(|monte_carlo|simulate|run_simulation"
```
Expected: the ONLY match should be the pre-existing `build_financial_rip_v3(` call inside `score_budget_strategy` at its original call site (unchanged by this plan — Task 2 only adds a line reading from its already-computed output, not a new call), and possibly comment text. No new invocation of a scoring/simulation function should appear in any of the diffed read-path files (`product_family_rankings_service.py`, `pokemon_sealed_product_detail_service.py`, `rip_decision_service.py`, `budget_product_ranking_service.py`) — those files must only read already-persisted columns.

- [ ] **Step 3: Confirm no existing ranking score/rank value changed**

Run: `cd backend && python -m pytest tests/unit/calculations/ tests/unit/rankings/ -v` (adjust paths to whatever directories house `compute_overall_rip_v10`/`v12`, `rank_budget_cohort`, `financial_rip_v3`/`v4` scoring tests in this repo — these must all still pass unmodified, proving Tasks 1-8 changed no scoring math).

Expected: all PASS with zero test files modified by this plan among them (Task 2 only touched `budget_normalized_product_ranking.py`'s test file for the NEW field — verify with `git diff --stat` that no assertion inside a pre-existing test in that file was edited).

- [ ] **Step 4: Report and terminal marker**

If Steps 1-3 all pass cleanly, write the concise implementation report (files touched, fields added, migration filename, test count) and end it with the exact line:

```
OPENING_PROFILE_BUCKET1_DATA_CONTRACT_VALIDATED
```

If ANY step fails, do NOT emit that line — report the specific failing gate instead.

---
