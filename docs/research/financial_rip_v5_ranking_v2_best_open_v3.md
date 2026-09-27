# Financial RIP V5 - Ranking V2 + Best-Open V3 (Prompt 5A)

## Status

`FINANCIAL_RIP_V5_RANKING_V2_BEST_OPEN_V3_COMPLETE`

History: Prompt 5A ended BLOCKED (no PostgreSQL to execute SQL). Prompt 5A.2 removed that blocker (an embedded Postgres 18 locally, then GitHub Actions postgres:17) and authored and proved the persistence layer. Everything below the 5A.2 section is unchanged 5A evidence. **Production is unchanged and no migration has been applied to it.**

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

## Prompt 5A.2 - SQL persistence and real-Postgres validation (this section supersedes 'Not done' items 1-3)

**Migrations (both trees, byte-identical, additive; not applied to production):**
- `20260920120000_add_budget_product_ranking_v2_v5_v14.sql`: V5/V14-named snapshot and row columns (`financial_rip_v5_score`, `overall_rip_v14_score`, `budget_rank_v14`, `financial_only_rank_v5`, ...); the four legacy rank/tier columns become nullable with a row-shape CHECK (a row is fully legacy-shaped or fully V2-shaped; `financial_only_rank` keeps its V4 meaning); V1/V12 body renamed to `..._v1_v12` behind a dispatcher; new private `..._v2` branch (exact identities, no V4/V10/V12 fields, rank contiguity, price authority, Full Market metadata, capital reconciliation, atomic, distinct latest pointer).
- `20260920130000_add_best_open_price_v3_dual_financial_v5_overall_v14.sql`: must apply after the pending V2 migration; V5/V14 columns, `threshold_exact_verified` flags, two benchmark NOT NULLs and `overall_rip_v12_version` relaxed with shape CHECKs; V1/V2 body renamed to `..._v1_v2` behind a dispatcher; private `..._v3` branch validating every row against the LIVE Ranking V2 rows (ranks, scores, P(win), capital, both benchmarks, threshold >= benchmark, exact-cent arithmetic, source drift, mixed-generation fields). It refuses to run on a V1-only database (does not duplicate V2 schema).
- Security unchanged: RLS on, no API-role grants; only the dispatcher is executable, by `service_role`; renamed and V2/V3 functions are internal.

**Validation on real PostgreSQL (GitHub Actions run 35543361650 on `397a2e46`, postgres:17, all three jobs green):** the existing 73 V1/V2 tests still pass; `test_budget_ranking_v2_postgres.py` (38: V1/V12 publish still works and carries no V2 fields, V2 publish and distinct pointer, 27-case atomic rejection matrix, table CHECKs, role security); `test_best_open_v3_postgres.py` (71: real V1 -> V2 -> V3 upgrade with a publish at each stage, V1/V2 rows preserved column-for-column and re-publishable, V3 publish, idempotency and non-determinism refusal, 55-case atomic rejection matrix incl. V1 source, V4/V12 evidence, benchmark and source-drift cases, dispatcher guards, role security, V3 refuses a V1-only DB); `test_budget_v2_v3_builder_compat_postgres.py` (builder output accepted by both real RPCs). The same suites passed locally on embedded Postgres 18.4 during development, where they caught and fixed one real gap (non-object snapshot handling in the ranking dispatcher).

**Python:** `budget_v2_v3_publication_payloads.py` (explicit, non-default snapshot/row builders; exact-Decimal price gaps; refuses non-exact or non-V3 axis results); `test_best_open_v3_ranking_v2_payload_contract.py` pins every identity literal across Python, SQL and fixtures.

**Still not done (not required for this bucket's COMPLETE criteria):** DB-backed orchestration scripts that read persisted state and call these builders/RPCs (explicit V2 request path in the ranking builder and authority loader; V3 path in the Best-Open publisher), exact-artifact finalization wiring, and everything in Prompt 5B. No default or scheduled publisher, read service or public selector was changed.

## Not done (5A original list; items 1-3 now closed above)

1. **Ranking V2 storage/RPC**: additive columns and a V2 branch on `publish_budget_product_ranking_snapshot` (V1/V12 branch verbatim, V2 atomic validation).
2. **Best-Open V3 storage/RPC**: additive V5/V14 columns (must apply after the pending, unapplied V2 migration `20260916120000`) and a V3 branch beside verbatim V1/V2 branches with row-by-row validation.
3. **V1 -> V2 -> V3 migration-chain test on real PostgreSQL**, plus V1/V2/V3 publish/read coexistence and security-advisor checks.
4. Ranking V2 builder/authority-loader integration (explicit V2 request path in `build_budget_normalized_product_rankings.py` and `budget_product_ranking_authority.py`) and the explicit V3 request path in the Best-Open builder/publisher.

Why blocked: there is no Postgres, `psql` or Docker here and no integration DSN, so PL/pgSQL cannot be executed. Roughly 1,300+ lines of RPC branches (V1 and V2 copied verbatim plus a new V3 branch) would ship untested against a schema whose V2 layer is itself unapplied in production. I chose not to author and commit that unverified.

## Next

Run in an environment with an isolated PostgreSQL 17 DSN (CI service or a disposable Supabase branch): author the two additive migrations and RPC branches, execute the V1 -> V2 -> V3 chain tests, then wire the explicit builder/publisher paths. Prompt 5B (finalization wiring, Public Contract V12, publication/readiness transport) should follow only after that.
