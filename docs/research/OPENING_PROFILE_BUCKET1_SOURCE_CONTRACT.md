# Opening Profile Bucket 1 — Source/Backend Data Contract

**Started from:** branch `develop`, HEAD `ccafe2f9906d70f8e021a9c59af114a3fb0eea19`.
**Produced commit:** see bottom of this doc.

## Scope actually implemented (source/backend-only, no migrations/SQL)

A prior session's plan (`docs/superpowers/plans/2026-09-14-opening-profile-bucket1-data-contract.md`)
proposed a new `budget_product_ranking_rows` migration (Task 1) and a DB-round-trip
persistence path (Task 3/4). This run's task brief explicitly forbids new production
SQL/migrations for this bucket ("no production columns exist yet for this, that's a
separately-owned DB lane; compute/emit them in the response contract only"), so **the
migration and DB-persistence tasks were intentionally NOT done**. Everything below is
pure Python source-contract wiring, verified additive and non-simulating.

## Canonical field mapping used (no substitutions)

| Presentation concept | Field | Source |
|---|---|---|
| Average Return % | `modeledReturnRatio` / `modeledReturnPercent` | already existed in `product_family_rankings_service.py::_project` (`expected_value / product_market_cost`) |
| Average Return $ | `expectedValue` | already existed everywhere; untouched |
| Typical Opening | `medianValue` | already existed everywhere; untouched |
| Covers Cost | `chanceToRecoverCost` | already existed everywhere; untouched |
| Top 1% Value Share | `topOneOutcomeValueShare` | **new** — `financial_rip_v3_payload.distributionDisclosures.jackpotValueShare`, exact same calculation run as every other field on the row. NEVER `depthAndRobustness.top1EvShare` |
| Budget-strategy Average Return | `averageReturn` | **new** — `expectedValue / actual_committed_capital`, computed inside `score_budget_strategy()` itself (never target budget, never one-unit price) |

## Files changed

1. `backend/calculations/evr/budget_normalized_product_ranking.py` — `score_budget_strategy()` now returns `topOneOutcomeValueShare` (from the SAME `v3_payload` it already builds) and `averageReturn` (`expectedValue / actual_committed_capital`). Pure in-memory computation; no DB, no new simulation call — reuses the existing `build_financial_rip_v3(...)` call already made once per strategy.
2. `backend/db/services/product_family_rankings_service.py` — `RESULT_FIELDS` now selects `financial_rip_v3_payload` (single existing query, same `calculation_run_id` filter); `_project()` emits `topOneOutcomeValueShare` from it.
3. `backend/db/services/pokemon_sealed_product_detail_service.py` — `DETAIL_FIELDS` now selects `financial_rip_v3_payload` on the single focal-product read; `_rip_contract()` emits `topOneOutcomeValueShare` from the focal product's own payload. Same-set comparison rows continue to be sourced from the cached `pokemon_explore_rankings_snapshot_latest` payload (`_ranking_rows`) — no new per-row query was added (verified by test).
4. `backend/db/services/rip_decision_service.py` — `_product_decision_row()` emits `topOneOutcomeValueShare` bound to the row's own `calculation_run_id`/`financial_rip_v3_payload` (repository already selected this column).
5. `backend/domain/access/index_plan_access.py` — `_PLUS_PRODUCT_RANKING_FIELDS` extended with `modeledReturnRatio`, `modeledReturnPercent`, `medianValue`, `topOneOutcomeValueShare`, `averageReturn` (Index Plus gate — Basic plans never see them).

## Surface coverage vs. the 5 requested prepared-data surfaces

1. Set RIP sealed-product comparison rows — covered via `rip_decision_service.py` (`ripDecision.sealedProducts.products[]`).
2. Product Detail "Opening Outcome Profile" — covered via `pokemon_sealed_product_detail_service.py` (`_rip_contract`).
3. Product Detail same-set comparisons — covered for free: comparison rows are the cached Product Family Rankings projection (#4/#2 above), no new N+1 read (regression test added).
4. Set Financial Rankings selectors feeding `SetMetricRankingsTable` — **not separately wired**; `SetMetricRankingsTable`/`setMetricRankingSelectors.mjs` are frontend files, out of scope per the task's "no frontend component edits" rule, and no additional backend set-level selector was identified beyond what `rip_decision_service.py`/`product_family_rankings_service.py` already serve into that table's data source.
5. Product Rankings prepared response contract — covered via `product_family_rankings_service.py` + the Plus allowlist in `index_plan_access.py` (both `project_product_rankings_response` and `project_product_family_rankings_response` reuse `_PLUS_PRODUCT_RANKING_FIELDS`).

**Budget strategies (BUDGET Product Rankings):** `score_budget_strategy()` now computes `medianValue` (pre-existing), `topOneOutcomeValueShare`, and `averageReturn` from the exact q-unit distribution/committed-capital — but because no DB column exists yet for `budget_product_ranking_rows` and adding one is explicitly out of scope (migrations forbidden), **these values are not yet threaded through `build_budget_normalized_product_rankings.py` → publication → `budget_product_ranking_service.py`'s public projection**, since that path round-trips through the DB table which lacks the columns. This is a genuine gap, not an oversight: closing it requires the separately-owned DB/migration lane the task brief calls out.

## Tests added (all passing)

- `backend/tests/unit/calculations/test_budget_normalized_product_ranking.py` — 3 new tests (jackpotValueShare sourcing, rejection of top1EvShare substitution, committed-capital-not-target-budget averageReturn). File total: 60/60 passed.
- `backend/tests/unit/db/services/test_product_family_rankings_service.py` — 3 new tests. File total: 25/25 passed.
- `backend/tests/unit/db/services/test_pokemon_sealed_product_detail_service.py` — 3 new tests (including an explicit no-N+1-query regression guard). File total: 30/30 passed.
- `backend/tests/unit/db/services/test_rip_decision_service.py` — 3 new tests. File total: 69/69 passed.
- `backend/tests/unit/domain/access/test_index_plan_access.py` — 2 new tests (Plus includes the 5 fields; Basic strips all 5). File total: 51/51 passed.

Combined regression run (command + result):
```
cd backend && python -m pytest \
  tests/unit/calculations/test_budget_normalized_product_ranking.py \
  tests/unit/db/services/test_product_family_rankings_service.py \
  tests/unit/db/services/test_pokemon_sealed_product_detail_service.py \
  tests/unit/db/services/test_rip_decision_service.py \
  tests/unit/db/services/test_rip_decision_freshness.py \
  tests/unit/domain/test_rip_decision_metrics.py \
  tests/unit/domain/access/test_index_plan_access.py \
  tests/unit/calculations/test_financial_rip_v3.py \
  tests/unit/calculations/test_financial_rip_v4.py \
  -q
=> 351 passed in 0.84s
```
(`tests/unit/api/test_paid_response_boundary.py` and `test_market_explorer_premium_gate.py` could not be collected — pre-existing missing `fastapi` module in this environment, unrelated to this change.)

## Regression proof — ranks/scores untouched

Every pre-existing test in every touched file still passes unmodified (no existing
assertion in any of the 5 test files was edited — only new test functions were
appended). `git diff` confirms each backend source edit is additive: a new
comma-joined field in a `SELECT` string, and a new key appended to an existing
return/`_pick` dict. No `_tier_sort_key`, `rank_budget_cohort`, `compute_overall_rip_v10/v12`,
or `build_financial_rip_v3` scoring math line was touched.

## No request-time simulation introduced

`score_budget_strategy()`'s only `build_financial_rip_v3(...)` call is the pre-existing
one; the new fields are read from its already-computed return value. The three
DB-service read paths only add a column to an existing `SELECT`, never a new query or
scoring call.

## Blocked / not done

- Budget Product Rankings public response (`budget_product_ranking_service.py`) does
  not yet expose `medianValue`/`topOneOutcomeValueShare`/`averageReturn` end-to-end,
  because the DB round-trip needs new nullable columns and this bucket forbids
  migrations. `score_budget_strategy()` itself is ready (computes/returns all three);
  wiring the publish/read path is the separately-owned DB lane.
- `SetMetricRankingsTable`/`setMetricRankingSelectors.mjs` (frontend selector) were
  read for context but not modified — no backend gap was found that required a change
  there beyond what's already covered by items 1/2/3/5.

Given the above, the full "5 prepared-data surfaces fully wired end-to-end including
budget strategies persisted to a public response" bar is **not** met — the budget
public-projection leg is explicitly blocked by the no-migrations constraint, not
skipped by oversight.
