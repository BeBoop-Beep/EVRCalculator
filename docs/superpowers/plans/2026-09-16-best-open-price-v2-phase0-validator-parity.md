# Best-Open Price V2 — Phase 0 Validator Parity Fix Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Close the committed-capital parity defect in the Best-Open Price publication validator (`backend/scripts/publish_best_open_price_if_ready.py`) so it proves reconciliation against the canonical `whole_unit_allocation()` authority instead of reimplementing the arithmetic with a different operation order/numeric type.

**Architecture:** `validate_engine_result()` currently recomputes current committed capital as `current_q * Decimal(current_cents) / 100`, which is Decimal arithmetic in a different operation order than the canonical allocator's `quantity * float(price)` (see `whole_unit_allocation()` in `backend/calculations/evr/budget_normalized_product_ranking.py:194-221`, and the prior related fix in commit `f5b15a72` which corrected this same operation-order issue inside the scoring engine at `backend/calculations/evr/best_open_price.py`, but left this validator's independent reimplementation unfixed). This causes 26/138 current Full Market rows — those with IEEE-754 tails such as `9 * 140.68 -> 1266.1200000000001` — to fail strict validation even though the engine's own output is correct. The fix calls `whole_unit_allocation()` directly to derive the expected quantity and committed capital, then compares against the persisted row exactly (no tolerance), preserving the "strict source evidence" contract in the file's docstring.

**Tech Stack:** Python 3, pytest, `decimal.Decimal` for exact-cents contracts.

**Spec:** This plan implements Phase 0 only, as specified in the "BEST-OPEN PRICE V2 — DUAL FINANCIAL + RIP THRESHOLDS" task instructions (no separate spec file was written; the task instructions are the source of truth and are reproduced in full in the conversation that authorized this plan). Later phases (1-10) are out of scope for this plan and will get their own plan documents per the user's approved sequential-sub-plan execution order.

## Global Constraints

- Do NOT modify unrelated Market Explorer, onboarding, alerts, scraper, Collector Appeal, or other concurrent work.
- Do NOT touch the conflicted normal checkout `D:\EVRCalculator` — all work happens in this worktree (`D:\EVRCalculator\.claude\worktrees\best-open-price-v2`, based on `origin/develop`).
- Do NOT apply any migration to production. (N/A for Phase 0 — no migration in this plan.)
- Do NOT publish a Best-Open snapshot. (N/A for Phase 0 — no publication invoked.)
- Do NOT alter Financial RIP V4 or Overall RIP V12 scoring methodology. (Phase 0 touches only the validator's committed-capital reconciliation check — no scoring math changes.)
- Do NOT weaken exact-search/maximality guarantees. Keep the direct comparison against the persisted source row (`by_source[pid]["actual_committed_capital"]` equality check later in the same function, unchanged) — do not replace it with a tolerance.
- Commit this narrow correctness repair separately, as its own commit(s), before any Phase 1+ methodology work.

---

### Task 1: Add failing regression test for the 140.68 × 9 IEEE-754 tail case

**Files:**
- Modify (test): `backend/tests/unit/scripts/test_publish_best_open_price_if_ready.py`

**Interfaces:**
- Consumes: `publisher.validate_engine_result(engine, source, source_rows)` — existing function at `backend/scripts/publish_best_open_price_if_ready.py:215`, returns `list[str]` of error strings (empty list = valid). `publisher.SOURCE`, `publisher.engine_row()`, `publisher.engine_result()`, `publisher.source_rows()` — existing test helpers in the same test file (lines 10-105).
- Produces: nothing consumed by later tasks in this plan — this is the terminal regression test for Task 2's fix.

- [ ] **Step 1: Write the failing test**

Add this test to `backend/tests/unit/scripts/test_publish_best_open_price_if_ready.py`, after `test_second_concurrent_run_is_refused_without_source_or_engine_work` (end of file):

```python
def test_validate_engine_result_accepts_canonical_ieee754_committed_capital_tail():
    """Regression for the 140.68 x 9 case: quantity * float(price) leaves a
    ~1e-13 IEEE-754 tail (9 * 140.68 -> 1266.1200000000001). The validator
    must reconcile against backend.calculations.evr.budget_normalized_product_ranking.
    whole_unit_allocation() -- the same operation order the canonical Budget
    Ranking allocator uses -- not an independently reimplemented Decimal
    computation, or it rejects 26/138 real Full Market rows as unresolved.
    """
    price = 140.68
    quantity = 9
    expected_capital = quantity * price  # 1266.1200000000001, the canonical tail
    assert expected_capital != quantity * price / 1  # sanity: float, not exact 1266.12

    source = dict(publisher.SOURCE, eligible_cohort_count=2, full_market_budget=1350)
    row = engine_row("p1", 1)
    row.update({
        "currentMarketPrice": price,
        "currentQuantity": quantity,
        "currentActualCommittedCapital": expected_capital,
    })
    row2 = engine_row("p2", 2, "resolved_below_market")
    rows = [row, row2]
    for r in rows:
        r["bestOpenPriceCents"] = round(r["bestOpenPrice"] * 100)
        r["exactness"]["nextPriceCents"] = r["bestOpenPriceCents"] + 1

    engine = engine_result()
    engine["products"] = rows
    engine["source"]["sourceContentFingerprint"] = publisher.source_content_fingerprint(
        source, source_rows_for(rows),
    )

    errors = publisher.validate_engine_result(engine, source, source_rows_for(rows))
    assert errors == []
```

This test needs a small helper, `source_rows_for(rows)`, that builds source rows from an arbitrary row list (the existing `source_rows()` helper hardcodes its own two rows via `engine_row('p1', 1), engine_row('p2', 2, ...)` and can't reflect the mutated `currentMarketPrice`/`currentActualCommittedCapital` from this test). Add it directly above `source_rows()` in the same file:

```python
def source_rows_for(rows):
    return [{
        'sealed_product_id': row['sealedProductId'], 'set_id': row['setId'],
        'product_family': row['productFamily'], 'source_calculation_run_id': row['sourceCalculationRunId'],
        'product_market_price': row['currentMarketPrice'], 'quantity': row['currentQuantity'],
        'budget_rank_v12': row['currentBudgetRank'], 'overall_rip_v12_score': row['currentOverallRipV12Score'],
        'financial_rip_v4_score': row['currentFinancialRipV4Score'], 'collector_appeal_score': row['currentCollectorAppealScore'],
        'chase_accessibility_raw': row['currentChaseAccessibilityRaw'], 'chance_to_recover_capital': row['currentChanceToRecoverCapital'],
        'actual_committed_capital': row['currentActualCommittedCapital'],
    } for row in rows]
```

Then simplify the existing `source_rows()` to reuse it (no behavior change, just DRY):

```python
def source_rows():
    return source_rows_for([engine_row('p1', 1), engine_row('p2', 2, 'resolved_below_market')])
```

- [ ] **Step 2: Run test to verify it fails**

Run: `cd D:\EVRCalculator\.claude\worktrees\best-open-price-v2 && python -m pytest backend/tests/unit/scripts/test_publish_best_open_price_if_ready.py::test_validate_engine_result_accepts_canonical_ieee754_committed_capital_tail -v`

Expected: FAIL, with the error list containing `"p1: current committed capital does not reconcile"` (because `current_q * Decimal(current_cents) / 100` at line 272 does not equal `9 * 140.68` computed as a float and then converted to Decimal via `str()`).

- [ ] **Step 3: Commit the test on its own (red state is expected and intentional)**

```bash
git add backend/tests/unit/scripts/test_publish_best_open_price_if_ready.py
git commit -m "test: add failing regression for Best-Open validator committed-capital parity"
```

---

### Task 2: Fix the validator to use the canonical `whole_unit_allocation()` authority

**Files:**
- Modify: `backend/scripts/publish_best_open_price_if_ready.py:36-39` (import), `:272` (the reconciliation check)

**Interfaces:**
- Consumes: `whole_unit_allocation(target_budget: float, product_market_price: float) -> Dict[str, Any]` from `backend/calculations/evr/budget_normalized_product_ranking.py:194` — returns a dict including `"quantity": int` and `"actualCommittedCapital": float` (computed as `quantity * float(product_market_price)`, i.e. price-to-float-first then multiply — the canonical operation order).
- Produces: `validate_engine_result()` unchanged signature `(engine, source, source_rows=None) -> list[str]`.

- [ ] **Step 1: Add the import**

In `backend/scripts/publish_best_open_price_if_ready.py`, change:

```python
from backend.calculations.evr.budget_normalized_product_ranking import (
    ALLOCATION_METHOD_VERSION, BUDGET_NORMALIZED_RANKING_METHOD_VERSION,
)
```

to:

```python
from backend.calculations.evr.budget_normalized_product_ranking import (
    ALLOCATION_METHOD_VERSION, BUDGET_NORMALIZED_RANKING_METHOD_VERSION,
    whole_unit_allocation,
)
```

- [ ] **Step 2: Replace the reimplemented arithmetic with the canonical authority**

In the same file, inside `validate_engine_result()`, replace:

```python
                if finite_decimal(row.get("currentActualCommittedCapital")) != current_q * Decimal(current) / 100:
                    raise ValueError("current committed capital does not reconcile")
```

with:

```python
                allocation = whole_unit_allocation(
                    target_budget=budget_cents / 100.0,
                    product_market_price=float(row.get("currentMarketPrice")),
                )
                if int(current_q) != allocation["quantity"]:
                    raise ValueError("current quantity does not match canonical whole-unit allocation")
                if finite_decimal(row.get("currentActualCommittedCapital")) != finite_decimal(allocation["actualCommittedCapital"]):
                    raise ValueError("current committed capital does not reconcile")
```

`target_budget` only affects `unusedCapital`/`unusedCapitalPercent`/`capitalUtilization` inside `whole_unit_allocation()`, none of which are read here — any positive value reproduces the identical `quantity` and `actualCommittedCapital`. Using `budget_cents / 100.0` (the same Full Market budget the rest of this function already validates against) keeps the call self-documenting.

Do not touch the later direct comparison against the persisted source row (the `by_source[pid]["actual_committed_capital"]` check further down in the same function) — that stays a strict equality check with no tolerance, per the task's explicit instruction to keep strict source evidence.

- [ ] **Step 3: Run the new regression test to verify it passes**

Run: `cd D:\EVRCalculator\.claude\worktrees\best-open-price-v2 && python -m pytest backend/tests/unit/scripts/test_publish_best_open_price_if_ready.py::test_validate_engine_result_accepts_canonical_ieee754_committed_capital_tail -v`

Expected: PASS.

- [ ] **Step 4: Run the full validator test file to check for regressions**

Run: `cd D:\EVRCalculator\.claude\worktrees\best-open-price-v2 && python -m pytest backend/tests/unit/scripts/test_publish_best_open_price_if_ready.py -v`

Expected: All tests PASS, including the pre-existing `test_happy_commit_publishes_atomically_then_reads_back_same_authority` and `test_recurring_run_pins_current_source_uses_exact_batch24_and_skips_replay` (their fixture data uses `currentMarketPrice=100.0`, `currentQuantity=13` → `13 * 100.0 = 1300.0` exactly, so they were never affected by the defect and must still pass unchanged).

- [ ] **Step 5: Run the broader Best-Open regression suite**

Run: `cd D:\EVRCalculator\.claude\worktrees\best-open-price-v2 && python -m pytest backend/tests/unit/calculations/test_budget_normalized_product_ranking.py backend/tests/unit/calculations/test_prepared_financial_rip_and_best_open_price.py backend/tests/unit/scripts/test_publish_best_open_price_if_ready.py backend/tests/unit/scripts/test_build_budget_product_best_open_price_snapshot.py -v`

Expected: All PASS. If `test_build_budget_product_best_open_price_snapshot.py` does not exist, skip it and note that in the task report (check with `ls backend/tests/unit/scripts/ | grep best_open` first if unsure).

Note: the task instructions flag that `test_best_open_price_scheduled_publication_contract.py` has a **pre-existing, unrelated** Windows cp1252 failure. If that file is part of this run and fails, do not attempt to fix it — report it separately as a known, unrelated failure per the task's explicit instruction not to "fix" it by changing unrelated shell files.

- [ ] **Step 6: Commit the fix**

```bash
git add backend/scripts/publish_best_open_price_if_ready.py
git commit -m "fix: reconcile Best-Open validator committed capital via canonical whole_unit_allocation()"
```

---

### Task 3: Revalidate the completed V1 checkpoint (report-only, if applicable)

**Files:** none modified — this is a verification/reporting task, not a code task.

**Interfaces:** N/A.

- [ ] **Step 1: Check whether a completed V1 engine checkpoint is reachable from this worktree**

The task instructions reference a prior 138-product, 0-unresolved, ~3210.98s engine checkpoint that should be revalidated with `reuse_complete=True` rather than recomputed. This checkpoint is operational state (`logs/best_open_price_checkpoints/*.json` per `DEFAULT_CHECKPOINT_DIR` in `publish_best_open_price_if_ready.py:65`) that lives on the production/scheduler host, not in git.

Run: `ls "D:\EVRCalculator\.claude\worktrees\best-open-price-v2\logs\best_open_price_checkpoints" 2>&1 || echo "no local checkpoint directory"`

- [ ] **Step 2: Report status — do not attempt to reconstruct or fabricate a checkpoint**

If no checkpoint file is present in this worktree (expected, since worktrees don't carry production `logs/` state), record in the final deliverable report: "No local V1 checkpoint file was reachable from the Phase 0 worktree; checkpoint revalidation via `reuse_complete=True` against the real ~3210.98s / 138-resolved / 0-unresolved run is an operational step for whoever runs `publish_best_open_price_if_ready.py --dry-run` against the production checkpoint directory, and was not executed as part of this source-only Phase 0 change." Do not mark this task as blocking Phase 0 completion — the code fix and its regression coverage (Tasks 1-2) are the deliverable; this task only documents that the operational revalidation step is out of reach from a fresh worktree and remains pending for deployment.

---

## Self-Review Notes

- Spec coverage: Phase 0's three requirements — (a) stop reimplementing the arithmetic, use `whole_unit_allocation()`, (b) keep the strict source-row comparison with no tolerance, (c) add a 140.68×9 regression, (d) revalidate the existing checkpoint via `reuse_complete=True` instead of recomputing, (e) commit narrowly and separately from V2 work — are covered by Tasks 1, 2, and 3. (d) is necessarily report-only from a worktree with no access to the production checkpoint directory; Task 3 documents this rather than silently skipping it.
- No placeholders: every step has literal code or literal shell commands.
- Type consistency: `validate_engine_result(engine: Mapping, source: Mapping, source_rows: Optional[Sequence[Mapping]] = None) -> list[str]` signature is unchanged across Task 1 (test) and Task 2 (implementation).
