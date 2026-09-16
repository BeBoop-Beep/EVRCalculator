# Opening Profile — Budget Product Rankings source-side DB bridge

Closes the source-side bridge for the prepared Budget Product Rankings DB
contract added by migration `20260915233000_add_budget_opening_profile_strategy_metrics.sql`
(two new columns: `median_value`, `top1_outcome_value_share`). This is
**source-side only** — the Product Rankings Opening Profile UI itself stays
deferred (`BLOCKED_ON_PREPARED_BUDGET_DB` in
`docs/research/OPENING_PROFILE_BUCKET2_SITEWIDE_UI.md`, left untouched).

## Branch / PR

- Branch: `feature/opening-profile-budget-db-20260915`
- PR: #201 (not merged, not closed)
- Base commit on branch before this work: `d1625d67`

## Migration files — untouched (verified)

```
git diff -- backend/db/migrations/20260915233000_add_budget_opening_profile_strategy_metrics.sql \
            supabase/migrations/20260915233000_add_budget_opening_profile_strategy_metrics.sql
```
produced zero output both before and after all edits in this task. Neither
file was opened for writing at any point.

## 1. Publication payload — `build_budget_normalized_product_rankings.py`

`to_publication_payload()` now emits, per row:

```python
"median_value": row["medianValue"],
"top1_outcome_value_share": row["topOneOutcomeValueShare"],
```

sourced directly from `score_budget_strategy()`'s existing return keys
(`medianValue`, `topOneOutcomeValueShare` — the latter is
`distributionDisclosures.jackpotValueShare` from the V3 payload, never the
unrelated card-attribution `depthAndRobustness.top1EvShare`). Nothing is
recomputed. `expected_value` / Average Return semantics were unchanged
(Average Return stays a presentation-time division, never a persisted
column).

## 2. Python-side publication validation

Added `validate_publication_payload_rows(rows)` in the same builder script.
Rejects, before the RPC boundary:

- `median_value` missing (`None`)
- `median_value` negative or non-finite (NaN/Infinity/-Infinity)
- `top1_outcome_value_share` missing (`None`)
- `top1_outcome_value_share` outside `[0, 1]`
- `top1_outcome_value_share` non-finite

Wired into both call paths so the gate cannot be bypassed:
- `materialize_publication_payload()` (used by dry-run and commit alike)
- `publish_rankings()` itself, immediately before `client.rpc(...)`, even if
  called with a pre-built `materialized_payload`.

This is the **primary** gate; the migration's own SQL `CHECK` constraints and
the `publish_budget_product_ranking_snapshot` RPC guard remain defense in
depth, unchanged.

## 3. Prepared budget reader — `public_overall_product_rankings_service.py`

`read_public_overall_product_rankings()` now projects, per row:

```python
"medianValue": raw.get("median_value"),
"topOneOutcomeValueShare": raw.get("top1_outcome_value_share"),
"averageReturn": (
    float(raw["expected_value"]) / float(raw["actual_committed_capital"])
    if raw.get("expected_value") is not None
    and raw.get("actual_committed_capital") not in (None, 0)
    else None
),
```

`averageReturn` is pure presentation arithmetic over two already-persisted
authority values (`expected_value`, `actual_committed_capital`) — it never
calls `score_budget_strategy()` or any simulation/scoring function. Preserved
unchanged: `expectedValue`, `chanceToRecoverCost`, `quantity`,
`actualCommittedCapital`.

## 4. Transitional safety (legacy Sep-8 snapshot rows)

The three new fields (`medianValue`, `topOneOutcomeValueShare`,
`averageReturn`) are deliberately **excluded** from
`required_generic_fields` — the existing all-or-nothing
`public_projection_incomplete` gate that governs `overallRipScore`,
`budgetRank`, `budgetCohortSize`. A row whose persisted `median_value` /
`top1_outcome_value_share` / `actual_committed_capital` is `NULL` or absent
(the live ~Sep-8 snapshot predates these columns) still passes through with
the row and the whole table intact; only these three fields resolve to
`None`. No exception, no dropped row, no silently-computed zero.

## 5. Tests

### `backend/tests/unit/scripts/test_build_budget_normalized_product_rankings_v12_publication.py`
New tests added:
- `test_to_publication_payload_threads_median_and_top1_outcome_value_share_through`
- `test_publication_payload_end_to_end_from_score_budget_strategy` (req 1: real `score_budget_strategy()` → `to_publication_payload()`)
- `test_to_publication_payload_does_not_change_existing_ranking_fields` (req 5: regression)
- `test_validate_publication_payload_rejects_missing_median`
- `test_validate_publication_payload_rejects_negative_median`
- `test_validate_publication_payload_rejects_non_finite_median`
- `test_validate_publication_payload_rejects_missing_share`
- `test_validate_publication_payload_rejects_share_above_one`
- `test_validate_publication_payload_rejects_share_below_zero`
- `test_validate_publication_payload_rejects_non_finite_share`
- `test_validate_publication_payload_accepts_valid_rows`
- `test_materialize_publication_payload_refuses_before_rpc_when_median_missing`
- `test_publish_rankings_never_calls_rpc_when_share_out_of_range` (asserts `client.calls == []`)

Existing fixtures (`_v10_rows()`) updated to carry valid `median_value` /
`top1_outcome_value_share` so pre-existing V12-merge tests keep exercising
real payloads under the new validation gate.

### `backend/tests/unit/db/services/test_public_overall_product_rankings_service.py`
New tests added:
- `test_prepared_read_exposes_persisted_median_and_top1_outcome_value_share_round_trip` (req 4: round-trip)
- `test_prepared_read_average_return_denominator_is_actual_committed_capital` (req 3: denominator proof, checked against both one-unit price and target-budget band as wrong denominators)
- `test_prepared_read_never_calls_score_budget_strategy` (req 6: monkeypatches `score_budget_strategy` to raise `AssertionError` if invoked, then asserts the read still succeeds)
- `test_prepared_read_legacy_row_missing_new_fields_degrades_soft` (req 7: row entirely missing both new keys — row and table stay intact, fields become `None`)
- `test_prepared_read_legacy_row_missing_committed_capital_makes_average_return_unavailable` (transitional safety: missing `actual_committed_capital` alone)

### Fixture fixes to keep unrelated existing tests passing under the new gate
- `backend/tests/unit/scripts/test_build_budget_product_rankings_payload.py`: `_row()` fixture now carries `medianValue`/`topOneOutcomeValueShare`; `_rpc_row_columns()` appends `median_value`/`top1_outcome_value_share` to the expected column set (mirroring how `expected_value` is already handled there — populated by a follow-up `UPDATE` inside the publish RPC, not the base migration's `INSERT` list).
- `backend/tests/unit/scripts/test_publish_budget_product_rankings_if_ready.py`: `_commit_ready_setup()`'s `v10_rows` fixture now carries `median_value`/`top1_outcome_value_share` so the real `publish_rankings()` path (exercised end-to-end in that test) passes the new validation gate.

## Test run — exact command and output

```
python -m pytest \
  backend/tests/unit/scripts/test_build_budget_normalized_product_rankings_v12_publication.py \
  backend/tests/unit/scripts/test_build_budget_product_rankings_payload.py \
  backend/tests/unit/scripts/test_publish_budget_product_rankings_if_ready.py \
  backend/tests/unit/db/services/test_public_overall_product_rankings_service.py \
  backend/tests/unit/db/services/test_budget_product_ranking_authority.py \
  backend/tests/unit/db/services/test_budget_product_ranking_service.py \
  backend/tests/unit/calculations/test_budget_normalized_product_ranking.py \
  backend/tests/unit/db/test_budget_opening_profile_strategy_metrics_migration_sql.py \
  -v
```

Result: **173 passed, 1 failed** in 1.20s.

The one failure, `test_no_card_attribution_top1_metric_can_enter_executable_sql`,
is in the migration's own contract-test file and fails because the
migration's `COMMENT ON COLUMN ... top1_outcome_value_share IS '... never
card-attribution top1EvShare.'` comment text contains the lowercased
substring `top1evshare` inside a negative reference — a pre-existing defect
in the migration SQL itself, reproduced identically against the branch's
prior state (commit `d1625d67`, before any of this task's edits):

```
git stash
python -m pytest backend/tests/unit/db/test_budget_opening_profile_strategy_metrics_migration_sql.py -q
# FAILED ...::test_no_card_attribution_top1_metric_can_enter_executable_sql
# 1 failed, 8 passed
git stash pop
```

Same single failure, same test, before any of this task's changes. Not
introduced by this work, and — per the hard constraint — the migration file
was not edited to "fix" it.

A wider scoped sweep was also run for extra confidence:

```
python -m pytest backend/tests/unit -q -k "budget or opening_profile or product_ranking" \
  --ignore=backend/tests/unit/api --ignore=backend/tests/unit/domain/billing \
  --ignore=backend/tests/unit/logging_integration \
  --ignore=backend/tests/unit/db/services/test_billing_service.py \
  --ignore=backend/tests/unit/db/services/test_billing_service_plan_change.py \
  --ignore=backend/tests/unit/db/services/test_billing_service_plan_change_matrix.py \
  --ignore=backend/tests/unit/db/services/test_frontend_proxy_service_auth.py \
  --ignore=backend/tests/unit/db/services/test_frontend_proxy_service_profile_concurrency.py \
  --ignore=backend/tests/unit/db/services/test_public_profile_collection_regression.py \
  --ignore=backend/tests/unit/db/services/test_supabase_auth_exchange.py
```

Result: **369 passed, 10 failed**. All 10 failures were reproduced
byte-identical against `git stash` (the branch's prior state) — pre-existing,
unrelated to this task (shell-contract wording assertions in
`test_best_open_price_scheduled_publication_contract.py` /
`test_run_simulations_shell_contract.py`, a payload-size assertion in
`test_pokemon_public_snapshot_service.py`, and the migration comment-text
assertion above). The `--ignore`d directories/files are pre-existing
collection errors from an unrelated missing `stripe` Python package and a
Python 3.8 typing syntax issue in `logging_integration`, both unrelated to
this task and present before any of this work.

## Hard-constraint compliance

- Migration files: zero diff, confirmed above.
- No Supabase/SQL/production touched — only local pytest runs against
  in-memory fixtures and fake Supabase clients (`_FakeClient`), exactly as
  the pre-existing test suite already does.
- `score_budget_strategy()` is not called anywhere in
  `public_overall_product_rankings_service.py`; a dedicated test
  (`test_prepared_read_never_calls_score_budget_strategy`) monkeypatches it
  to raise if invoked and confirms the read path still succeeds.
- No redundant `average_return` DB column added — `averageReturn` is computed
  at read time only, division of two already-persisted numbers.
- No individual-product/one-unit metrics substituted for budget-strategy
  metrics anywhere in the changed code.
- No `best_open_price` files touched.

## Commit

Pushed to `feature/opening-profile-budget-db-20260915`, updating PR #201's
diff. PR #201 was not merged or closed.
