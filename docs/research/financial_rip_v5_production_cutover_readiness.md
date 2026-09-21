# Financial RIP V5 - production cutover readiness

## Status

`FINANCIAL_RIP_V5_PRODUCTION_CUTOVER_BLOCKED`

Reason: the work is partially complete. It is not blocked by a model contradiction; the approved model reproduced the frozen candidate exactly. Most of the downstream lineage (ranking, Best-Open, public contract, frontend, publication and readiness) is not yet implemented, and no live or parity validation has run. Production is unchanged: canonical Financial V4 / Overall V12 / public_rip_contract_v11.

Starting HEAD `b0800190`. Adjudication authority `43f2df61`: promotion approved on construct validity, not on a large ranking gain (Spearman 0.9976), with SR ~0.98 correlated with Typical Retention and no real high-win evidence. Nothing here should be described more strongly.

## Version inventory (verified unused before assignment)

| Authority | Current canonical | Historical | New identity | State |
|---|---|---|---|---|
| Financial | `financial_rip_v4_outcome_profile_p95_only_25_20_15_25_10_5` | V3, V4 | `financial_rip_v5_shortfall_resilience_25_20_15_25_10_5` (config `financial_rip_v5_config_v1`) | implemented |
| Overall | V12 (Fin V4 + Chase V1 + Collector V5) | V10, V11, V13 (superseded, Collector V7) | `overall_rip_v14_86_financial_v5_04_chase_accessibility_v1_10_collector_appeal_v5` | registered, compute implemented, not canonical |
| Public contract | `public_rip_contract_v11` | v4-v10 | `public_rip_contract_v12` (proposed) | NOT implemented |
| Ranking method | `budget_product_ranking_v1` | - | `budget_product_ranking_v2` (proposed) | NOT implemented |
| Best-Open | `..._v2_dual_financial_v4_overall_v12` | v1, v2 | `..._full_market_v3_...` (proposed) | NOT implemented |

## Implemented (committed)

- `backend/calculations/evr/financial_rip_v5_config.py`, `financial_rip_v5.py`: V4 engine for five unchanged components; Shortfall Resilience from exact counts and prefix sums; payload persists count/sum below cost and below half cost, E[(1-R)+], E[(0.50-R)+], capped recovery, depth resilience, cost, outcome count. `validate_financial_rip_v5_payload` rejects V4-shaped, mixed, tampered or stripped payloads. `project_financial_rip_v5_from_v4_payload` fails closed. The research candidate file is untouched.
- `backend/desirability/scoring_config.py`: V14 identity, weights, effective weights, required input versions (additive block; `CANONICAL_*` untouched). `backend/desirability/overall_rip_v14.py`: 0.86/0.04/0.10, exact input versions required (keyword-only), no renormalization, no Financial V4 fallback.
- Migration `20260920000000_add_sealed_product_financial_rip_v5.sql` (both trees, identical): five nullable `financial_rip_v5_*` columns on `simulation_sealed_product_results`. Additive, no grants/RLS change, NOT applied to production. Rollback: drop the five columns. No Overall V14 sealed columns: V14 belongs in the generic Overall publication ledger.
- `sealed_product_results_repository.py`: separate V5 write/read functions. V5 columns are deliberately not in the default SELECT or enrichment lists, because selecting columns the database lacks would fail every read until the migration is applied.

## Tests

- `test_financial_rip_v5_production.py` and the existing candidate tests: 34 passed. Covers exact frozen-candidate parity at four costs, V4 isolation, five unchanged components, direct parity, score reconstruction, raw-statistics reconstruction, validator rejection cases, dominance at 0.3/0.5/0.7/0.9, fail-closed projection.
- `test_overall_rip_v14.py` and `test_sealed_product_v5_repository.py`: 11 passed (weights, rounding, wrong-version and missing-pillar fail-closed, canonical unchanged, V12 unchanged, migration additive and mirrored).
- Wider run (desirability, calculations, two ranking suites): 2678 passed, 109 failed. Inspected causes: branch/ancestry guard tests, dirty-tree guards, unmocked Supabase calls with fake IDs, and a stale V10-vs-V12 assertion in `test_collector_appeal_v3_and_overall_rip_v7.py` that is self-contradictory. None trace to this change, but I did not run the same suites on a clean checkout, so "pre-existing" is inferred, not proven.

## Not done (each is decision-critical for READY)

1. Ranking method v2 (Financial V5 + Overall V14 fields, snapshot metadata, additive storage).
2. Best-Open v3 method identity, storage, and exact-cent engine wiring; V2 must stay untouched.
3. Public contract v12 with explicit `financialRipV5` / Overall V14 blocks; V11 frozen.
4. Sealed-product finalization writing V5 from the exact artifact (`simulation_pack_outcome_artifacts`), plus fail-closed lineage checks.
5. Publication lifecycle, Set-page, readiness and Sentinel model-awareness; frontend transport and version guards.
6. Frozen Sep-14 parity oracle (138 products: scores, ranks, 4 x 138 Best-Open thresholds) and the live read-only dry run on the current cohort. Both require database and artifact access not exercised here.
7. Pre-cutover diff report, monitoring hooks (SR/Typical redundancy; P(win) >= 30% regime), and schema landing in a disposable environment.

## Cutover sequence (to execute after the above)

1. Land code. 2. Apply the additive migration (production stays V4/V12). 3. Compute V5 from exact artifacts. 4. Build the inactive V14 generation in the generic ledger. 5. Build the ranking v2 snapshot. 6. Build the Best-Open v3 snapshot. 7. Generate public contract v12 payloads. 8. Generate Set-page generations. 9. Run full parity against the frozen oracle and the live dry run. 10. Readiness/Sentinel validation. 11. Flip the canonical selectors in `scoring_config.py` and the current-publication pointer (needs explicit user authorization). 12. Post-flip readback. 13. Rollback if needed.

## Rollback

Non-destructive: revert the `scoring_config.py` canonical selectors to V4/V12, the publication pointer to the V12 run, the public contract to V11 and the Best-Open read selector to V2; leave V5/V14 rows as inactive evidence. Frontend redeploy is needed only if transport guards changed.

## Verification hygiene

Workspace-wide `git diff --check` was not run against unrelated concurrent edits (eBay collector and research JSON files); only owned files were staged.

## Prompt 5A update (Ranking V2 + Best-Open V3)

Bucket status `FINANCIAL_RIP_V5_RANKING_V2_BEST_OPEN_V3_BLOCKED` (test infrastructure: no isolated PostgreSQL). Overall cutover status above is unchanged: **not READY**. Details: [financial_rip_v5_ranking_v2_best_open_v3.md](financial_rip_v5_ranking_v2_best_open_v3.md).

Completed: Ranking V2 and Best-Open V3 engines (explicit, non-default; V1/V2 untouched); frozen Sep-14 parity, 138/138 ranking products and 276/276 Best-Open thresholds with zero mismatches; focused suites match the pristine-HEAD baseline (same 11 pre-existing failures).

Still outstanding after 5A: Ranking V2 and Best-Open V3 SQL persistence/RPC branches and the V1->V2->V3 migration-chain test on real PostgreSQL; explicit builder/publisher paths; exact-artifact finalization wiring; Public Contract V12; publication lifecycle; frontend transport/version guards; readiness/Sentinel; live current-cohort dry run; schema landing (including the pending V2 Best-Open migration and the V5 sealed-results migration); inactive V14 generation; final pre-cutover report; activation.

## Prompt 5A.2 update (SQL persistence, real Postgres)

Bucket status `FINANCIAL_RIP_V5_RANKING_V2_BEST_OPEN_V3_COMPLETE`; overall cutover remains **not READY**. Ranking V2 and Best-Open V3 migrations, RPC branches and payload builders are authored and proven on real PostgreSQL 17 in GitHub Actions (run 35543361650), including the V1 -> V2 -> V3 chain. Nothing is applied to production. See [financial_rip_v5_ranking_v2_best_open_v3.md](financial_rip_v5_ranking_v2_best_open_v3.md).

Landing order at schema-landing time: V5 sealed-results migration, Ranking V2 migration, Best-Open V2 migration (pending since 2026-09-16), Best-Open V3 migration. Still outstanding: DB-backed builder/publisher orchestration, finalization wiring, Public Contract V12, publication lifecycle, frontend transport, readiness/Sentinel, live dry run, inactive V14 generation, pre-cutover report, activation.

## Prompt 5B update (finalization, contract V12, backend transport)

Bucket status `FINANCIAL_RIP_V5_BACKEND_PUBLICATION_TRANSPORT_COMPLETE`; overall cutover remains **not READY**. Exact-artifact Financial V5 finalizer, Overall V14 per-row finalization and inactive generic-ledger candidate, Public Contract V12 (registered, non-canonical, V11 frozen and embedded verbatim), V14/contract-V12 identity registration, separate candidate readiness, generic active-reader parity, and explicit Ranking V2 / Best-Open V3 orchestration modules are implemented and unit-tested (102 new tests). Nothing applied to production. Details, design findings and limits: [financial_rip_v5_backend_transport_v12.md](financial_rip_v5_backend_transport_v12.md).

Still outstanding: frontend/version transport, controlled schema landing, running the finalizer on real artifacts plus the current-cohort dry run, V14 set-page generation projections, rewiring concrete services onto the generic reader, CLI wrappers for the orchestrators, final pre-cutover report, activation.

## Prompt 5C update (live shadow, final readiness)

Status `FINANCIAL_RIP_V5_PRODUCTION_CUTOVER_BLOCKED`. Live read-only shadow on the 2026-09-15 cohort (22 runs, 138 products): exact-artifact V5 138/138 ready with exact V4 lineage parity, V14 candidate validated 138/138, Full Market Ranking V2 138 ranked, Contract V12 built with 0 problems, readiness gate passed (Best-Open V3 waived). Blocked by unfinished work (services other than Set RIP, V14 set-page projection, frontend transport, live Best-Open V3) and an unresolved activation-atomicity risk, plus a stale generic ledger (active V12 run dated 2026-09-10). Full detail, activation and rollback sequences: [financial_rip_v5_final_cutover_readiness.md](financial_rip_v5_final_cutover_readiness.md).
