# Financial RIP V5 - final cutover readiness (Prompt 5C)

## Status

`FINANCIAL_RIP_V5_PRODUCTION_CUTOVER_BLOCKED`

The **live read-only evidence is strong**: on real production data the exact-artifact V5 finalizer, the in-memory V14 candidate, the Full Market Ranking V2 shadow and Public Contract V12 all completed with zero unavailable rows and the candidate readiness gate passed. The blocker is **unfinished implementation and one unresolved architectural risk**, not a model or data-lineage problem. The approved V5 formula and weights were not touched. Nothing was applied to production: no migration, V5 row, V14 run, Ranking V2 / Best-Open V3 publication, pointer flip or selector change.

## Production authority at evaluation (re-verified read-only)

- Active generic Overall pointer -> run `0f83d958...`, `overall_rip_v12_86_financial_v4_04_chase_accessibility_v1_10_collector_appeal_v5`, status `published`, **market_date 2026-09-10, 276 rows**. Ledger runs: this V12 run (published) and V13 (superseded).
- No `financial_rip_v5_*` sealed columns, no Ranking V2 (`*_v14`, `*_v5`) columns, no Best-Open V2/V3 columns. `budget_product_ranking_latest`: V1 at market date 2026-09-14. `budget_product_best_open_price_latest`: V1, source date 2026-09-08.
- **Promoted market date resolved at runtime: 2026-09-20. Latest date whose whole simulation cohort passes the freshness gate: 2026-09-15.** The gate correctly refuses 09-20 (that day's simulations have not run). The live shadow therefore uses 2026-09-15 and reports both.

## Live read-only shadow (cohort 2026-09-15: 22 sets/runs, 138 products)

| Stage | Result |
|---|---|
| Exact-artifact V5 (dry run, no writes) | 22 artifact loads, 22 distribution builds, **138/138 ready, 0 unavailable, `cohortComplete` true**, 38 s. **All 138 rows reproduced their stored Financial V4 exactly (`v4LineageParity: exact`)**, confirming on production data that the seed identity and regenerated distributions are exact. V5 range 11.51-52.82. |
| Collector V5 / Chase V1 | `collector_appeal_v5_contextual_roster_h_only_d_baseline_up4_down2`; `chase_accessibility_v1_hc_value_squared_modeled_probability`. Collector bundle build took 286 s (one read-timeout retry needed, transient). |
| Overall V14 candidate (in memory) | `validate_v14_candidate` passed: 138/138 ready, contiguous ranks, exact identities. |
| Ranking V2 (Full Market $1300 only) | 138 ranked, 0 excluded, 0 unrankable, all 8 families covered. Only Full Market was computed to bound runtime; a publication must build every budget (the default). |
| Public Contract V12 | Built for all 138 targets, 0 problems: version V12, V5/V14 blocks ready, generic slots = V5/V14, 86/4/10, no V4 identity inside V14/V5, V11 embedded intact. **Product-level targets**, because the set-target builders cannot run at V14 yet. |
| Candidate readiness | `candidateReady = true`, `canonicalImpact = "none"`. **Best-Open V3 was waived for this run (not built), so this is not a full-gate pass.** Ranking V2 was an in-memory summary, not a persisted snapshot. |

### Old vs new, live (product-level Stage-1 scores, single-unit vs cost; not the budget-strategy scores of the Sep-14 research)

| | Pearson | Spearman | Kendall | mean delta | P10 / P90 | rank move mean / max | top 5/10/20 |
|---|---|---|---|---|---|---|---|
| Financial V4 -> V5 | 0.9981 | 0.9979 | 0.9676 | +2.37 | +1.74 / +3.03 | 1.83 / 15 | 5 / 10 / 19 |
| Overall V12 -> V14 | 0.9973 | 0.9969 | 0.9604 | +2.06 | +1.51 / +2.64 | 2.14 / 14 | 5 / 10 / 18 |

Movement counts (Financial): unchanged 26, 1-2 places 74, 3-5 places 36, >5 places 2. Overall: 35 / 62 / 25 / 16. This is a modest, expected correction, as the adjudication predicted; rank changes are not evidence of improvement. Movers are the products whose deep-shortfall depth differs from their median retention.

**Monitoring items.** SR vs Typical Retention live Pearson **0.988** (consistent with the research; not a gate). **Maximum product P(win) 19.1%**: the real high-win (>= 30%) regime is still unobserved.

## Implementation completed in this bucket

- Finalizer `evidence_sink` (bounded V5 evidence, no arrays) and truthful `dryRun` on early exits.
- `backend/db/services/v5_shadow_runner.py` (read-only chain; contains no write call) and `backend/scripts/run_financial_v5_candidate.py` with `finalize-v5` (dry-run default, `--commit` opt-in) and `shadow` (no commit mode). Runtime date resolution reports the promoted date and the latest complete cohort date.
- Selector-driven Set RIP target selection: canonical selector first, historical chain unchanged; shared `canonical_public_rip_contract_target_key()`. Parity with the legacy V12 precedence and a controlled-V14 flip are tested; a candidate-only target cannot displace canonical V12.
- Ranking V2 orchestration `only_full_market` flag (default False; shadow only).
- 162 related tests pass (14 finalizer, 13 V14, 28 contract V12/V11, 23 transport/readiness, 6 generic reader, 14 orchestration, 4 sequence, 16 Set RIP incl. new selector tests, 8 CLI, plus adjacent lifecycle/contract suites).
- CI workflow path filters and runtime test selection extended to cover the new V5/V14/contract/Set RIP files.

## Blockers (smallest real ones, in order)

1. **Concrete-service parity (not done, 4 of 5 services).** Set RIP is selector-driven and proven. Still V12-specific: `product_family_rankings_service` (also hardcodes Financial V4 fields in its tie-break, gate and projection, and would select V5 columns that do not exist until the schema lands), `public_overall_product_rankings_service` and `pokemon_sealed_product_detail_service` (read Ranking V1/V12 and Best-Open V1/V2 - need a ranking/Best-Open read-method selector), and `pokemon_public_snapshot_service`. Reader-level parity is proven; **service-level V12 parity is not**.
2. **V14 set-page generation projection (not done).** `write_v14_candidate` still has only the seam; a candidate stays `staged` and not promotable.
3. **Frontend/version transport (not started).** No frontend audit or change: allowlists (`rankingsClientProjection.mjs`, access/entitlement projections), the shared Overall explanation selector, and version-aware V4 `loss_resilience` vs V5 `shortfall_resilience` component labels. Contract V12 keys are not yet proven to survive the RPC -> API -> client chain.
4. **Live Best-Open V3 shadow (not run).** ~1 h exact-cent search; the engine and the Sep-14 oracle (276/276) are closed, but the current cohort has not been searched, so the full candidate gate has not passed with Best-Open V3 required.
5. **Operator commands `build-v14`, `ranking-v2`, `best-open-v3`, `readiness`** are registered but fail loudly as "later step".
6. **Activation atomicity is unresolved (a real risk, not a formality).** Authorities that must agree at cutover: code canonical Financial/Overall selectors (`scoring_config.py`, changed by deployment), public contract selector (same), generic DB pointer (changed atomically by `promote_pokemon_overall_rip_publication`), Ranking method/read selector, Best-Open read selector, frontend transport. The DB pointer flips atomically, the code selectors flip on deploy: **there is an unavoidable non-atomic window** unless serving code reads the generic pointer for every "current Overall" field (blocker 1) so the pointer is the single switch. Until then a mixed-generation serving window exists.
7. **The generic ledger is stale relative to production data.** Its active V12 run is dated 2026-09-10 (276 rows) while sealed rows, rankings and simulations are at 09-14/15+. It is not refreshed by the daily publisher. Routing services through it while it points at that run would serve older Overall than the current V12 columns, so "service parity while active = V12" cannot hold on live data until a current V12 ledger run is built. This must be an explicit activation-plan step (build and promote a current V12 run first, verify parity, only then V14).

## Not re-verified in this bucket (stated, not assumed)

Migration preflight was limited to: production has none of the target columns (verified), files are mirrored (unit-tested), Postgres chain last green in run 35546880028 on 67c1e664. I did not re-run the Postgres chain or check for newer migrations colliding with the target names in this bucket. The frozen Sep-14 oracle was not re-run (no scoring/ranking/search change was made).

## Exact activation sequence (for the future authorized bucket; not executed)

Deployments = D, DB transactions = T, read-only verification = V.

1. D: deploy dormant, version-aware code (all blockers above closed first).
2. T: apply Financial V5 sealed-results migration.
3. T: apply Ranking V2 migration.
4. T: apply pending Best-Open V2 migration.
5. T: apply Best-Open V3 migration. (Order: 2 before 4 before 5 by dependency; V5 before ranking reads.)
6. T (writes V5 columns only): `run_financial_v5_candidate finalize-v5 --commit`, then re-run readiness.
7. T: build a **current V12 ledger run** (closes risk 7) and verify service parity while V12 is active.
8. T: build inactive V14 publication run (staged).
9. T: build and validate the V14 rankings generation.
10. T: build and validate the V14 set-page generation.
11. T: publish Ranking V2 (all budgets).
12. T: publish Best-Open V3.
13. T: persist / build Public Contract V12 public snapshots.
14. V: rerun candidate readiness on persisted state (Best-Open V3 required); verify V12 is still the active pointer.
15. T + D (single controlled window): promote the V14 run via `promote_pokemon_overall_rip_publication`; deploy the canonical selector change. Only safe as one act if serving code is pointer-driven (blocker 6).
16. V: post-cutover readback of every surface.
17. Rollback on any failed verification.

## Rollback (non-destructive; not executed)

Re-promote the retained V12 ledger run (`promote_pokemon_overall_rip_publication`, which supersedes V14 without deleting it); revert the canonical selector constants to Financial V4 / Overall V12 / `public_rip_contract_v11` and redeploy; repoint Ranking and Best-Open reads to V1/V2; frontend redeploy only if transport guards changed. Leave every V5/V14/Ranking-V2/Best-Open-V3 row and column in place as inactive evidence. No column drops, no snapshot deletes, no history deletion.

## Known remaining risks

Collector bundle build is slow (286 s) and sensitive to transient read timeouts; the promoted date can run ahead of a complete simulation cohort (handled by reporting both dates); live evidence is single-cohort (2026-09-15), not temporal; Contract V12 was validated at product level, not on real set targets.
