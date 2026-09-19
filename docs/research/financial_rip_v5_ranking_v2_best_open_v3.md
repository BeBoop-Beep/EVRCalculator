# Financial RIP V5 - Ranking V2 + Best-Open V3 (Prompt 5A)

## Status

`FINANCIAL_RIP_V5_RANKING_V2_BEST_OPEN_V3_BLOCKED`

Classification: **test infrastructure** (no isolated PostgreSQL available), which leaves the SQL persistence branches unauthored. The engine and parity work is complete and verified; the database half is not. This is not a model or parity problem, and the V5 formula was not touched. Production is unchanged and nothing was applied.

## Version identities (verified unused before assignment)

| Authority | Identity | State |
|---|---|---|
| Ranking V1 | `budget_product_ranking_v1` | unchanged, still default |
| Ranking V2 | `budget_product_ranking_v2` | engine implemented, explicit, non-default |
| Allocation | `budget_allocation_floor_quantity_v1` | unchanged |
| Best-Open V1 / V2 | `..._full_market_v1` / `..._v2_dual_financial_v4_overall_v12` | unchanged |
| Best-Open V3 | `budget_product_best_open_price_full_market_v3_dual_financial_v5_overall_v14` | engine implemented, explicit, non-default |

## Implemented

- `budget_normalized_product_ranking.py` (append-only; V1 functions untouched): `score_budget_strategy_v2` (production `build_financial_rip_v5` + `compute_overall_rip_v14`, V5/V14-named fields only), `_tier_sort_key_v14`, `financial_only_comparator_key_v5`, `rank_by_financial_only_v5`, `rank_budget_cohort_v2`. No `sort_authority` argument and no fallback: a row without V14 evidence is excluded. V2 emits `budgetRankV14` and `financialOnlyRankV5`, never V4/V12 keys.
- `financial_rip_v5.py`: optional `control_payload` (same validation as the research path) so the V3-then-project V4 control is not recomputed per candidate.
- `best_open_price_v3.py`: `PreparedV5Candidate` (V5 then V14 from one distribution), per-axis comparators with no delegation to V4/V12 authorities, `require_ranking_v2_source` (rejects V1 and any non-V2 source), `build_dual_best_open_v3_search` and `run_dual_best_open_v3` around the **unchanged** fused engine, relabelling results to V3 and replacing the V12-named benchmark field.
- Validators: `validate_ranking_v2_parity.py`, `validate_best_open_v3_parity.py` (resumable, read-only).
- No default resolver, publisher or read service was switched.

## Frozen Sep-14 parity (snapshot 0e65fb6d, fingerprint e18fb00c..., $1300, 138 products)

- **Ranking V2: 138/138 products, 0 mismatches**, per product on seven checks: Financial V5 score, Overall V14 score, quantity, committed capital, P(win), Financial V5 rank, Overall V14 rank (`financial_rip_v5_ranking_v2_parity.json`).
- **Best-Open V3: 138 products / 276 thresholds, 0 mismatches**, seeded from the production Ranking V2 replay (not the oracle): threshold cent, quantity, benchmark product, V5 and V14 scores, P(win), committed capital, threshold wins, adjacent cent loses (`financial_rip_v5_best_open_v3_parity.json`). Perfect Order Booster Pack reproduced 363c/q=358 (Financial) and 358c/q=363 (Overall). One transient PostgREST `PGRST002` interrupted the first pass at 61/138; the checkpointed run resumed and completed.
- Caveat: these runs used the working tree, which contains someone else's uncommitted edit to `build_single_q_parity_distributions` (`sealed_product_distribution.py`, claimed bitwise-identical). Results equal the frozen oracle produced before that edit, so it did not change outcomes on this cohort. That file is not part of this commit. Wall time was not benchmarked against Prompt 3R; the fused/batched path is reused unchanged, so no sequential duplicate construction was introduced.

## Tests (baseline compared on a pristine `git archive` of HEAD, not a worktree)

- 45 affected suites (ranking, Best-Open engine/fused/batch/publication/contract, prepared-distribution, V5, V14): pristine HEAD **573 passed, 11 failed, 73 skipped**; with my changes plus the new files **589 passed, 11 failed, 73 skipped**. The 11 failures are the **identical set** (9 in `test_best_open_price_scheduled_publication_contract.py`, 1 in `test_best_open_review_regressions.py`, 1 migration-SQL top1 check in `test_budget_opening_profile_strategy_metrics_migration_sql.py`). They exist on pristine HEAD and are not caused by this work.
- The 73 skips are the Postgres integration tests (no DSN).
- New: `test_budget_ranking_v2_and_best_open_v3.py` (8 tests): identity uniqueness, V5/V14 usage with a mutation guard against a V4 call, no V4/V12 fields, comparator shape, contiguity, determinism, fail-closed missing pillars, V3 source must be Ranking V2, comparator authority isolation, fused exact-cent search and relabelling.

## Not done

1. **Ranking V2 storage/RPC**: additive columns and a V2 branch on `publish_budget_product_ranking_snapshot` (V1/V12 branch verbatim, V2 atomic validation).
2. **Best-Open V3 storage/RPC**: additive V5/V14 columns (must apply after the pending, unapplied V2 migration `20260916120000`) and a V3 branch beside verbatim V1/V2 branches with row-by-row validation.
3. **V1 -> V2 -> V3 migration-chain test on real PostgreSQL**, plus V1/V2/V3 publish/read coexistence and security-advisor checks.
4. Ranking V2 builder/authority-loader integration (explicit V2 request path in `build_budget_normalized_product_rankings.py` and `budget_product_ranking_authority.py`) and the explicit V3 request path in the Best-Open builder/publisher.

Why blocked: there is no Postgres, `psql` or Docker here and no integration DSN, so PL/pgSQL cannot be executed. Roughly 1,300+ lines of RPC branches (V1 and V2 copied verbatim plus a new V3 branch) would ship untested against a schema whose V2 layer is itself unapplied in production. I chose not to author and commit that unverified.

## Next

Run in an environment with an isolated PostgreSQL 17 DSN (CI service or a disposable Supabase branch): author the two additive migrations and RPC branches, execute the V1 -> V2 -> V3 chain tests, then wire the explicit builder/publisher paths. Prompt 5B (finalization wiring, Public Contract V12, publication/readiness transport) should follow only after that.
