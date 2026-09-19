# Financial RIP V5 Best-Open live validation: blocked

## Authority

- Repository: `fix/market-explorer-adaptive-timeout-clean-20260919` at `9f5cb43416b61341f8ea7f4bf969e96a3ba9b28d`. The frozen V5 candidate and Prompt-2 artifacts are untracked research files. Concurrent log changes were left untouched.
- Published Full Market source: `0e65fb6d-ff33-4331-99d5-d6a214ecc712`, market and pinned price date 2026-09-14, cohort fingerprint `e18fb00cd41f1646579b082164c80b0da3db2e1831dec9428c6fd4d82ac689ce`, budget $1,300, 138 products.
- Financial control: V4. Overall control: V12. Existing V2 method: `budget_product_best_open_price_full_market_v2_dual_financial_v4_overall_v12`. Candidate identities: `FINANCIAL_RIP_V5_CANDIDATE` and `OVERALL_RIP_FINANCIAL_V5_SHADOW`.
- The published Best-Open snapshot still points to the older September 8 ranking source; it was not used as the September 14 scoring authority.

## 1. Control integrity

The existing V2 path passed source-authority validation, Financial-only rank reconstruction, and V12 parity for a bounded live smoke product (`41b15cf2-512b-4b28-9660-83170538fc7a`). Its Financial V4 threshold was $137.65 and Overall V12 threshold was $136.72. Both won at the exact cent and lost at the adjacent higher cent. The detailed control result is in the machine-readable evidence.

A full 138-product V2 control run was attempted and stopped after approximately 32 minutes without a completed cohort artifact. The runner emits no per-product progress and only writes its result at completion. Therefore full-cohort control integrity is **unproven**, even though the bounded smoke passed.

## 2. High-win coverage

The completed Perfect Order Booster Pack candidate diagnostic evaluated 155 distinct candidate-price states. All had P(win) below 20%; neither 30%, 50%, 70% nor 80% was reached. This one-product diagnostic cannot establish cohort-wide high-win coverage. The current-market maximum from Prompt 2 remains 15.92%.

## 3. Plateau finding

No completed real trajectory crossed P(win) ≥ 50%. The V4 high-win plateau has **not** been tested on live Best-Open price states. No positive or negative plateau conclusion is claimed.

## 4. Shortfall distinctness

The Prompt-2 current-market SR/Typical Retention Pearson correlation was approximately 0.979. The present bounded price evidence does not answer whether that redundancy weakens in the high-win domain. The high-win domain was not reached in the completed diagnostic.

## 5. Financial BOP impact

The research adapter selects the Financial V5 benchmark from a prospective V5 Financial ranking and scores the frozen candidate directly from each prepared distribution. The completed Perfect Order Booster Pack Financial V5 threshold was **$3.63 at quantity 358**, P(win) 6.693%. It won at 363 cents; 364 cents lost across a quantity boundary. Its artifact lineage, benchmark, score and search diagnostics are in the JSON.

No matching full-cohort Financial V4 control artifact exists for the current source. The Financial V5−V4 threshold distribution and benchmark-change counts therefore cannot be computed honestly.

## 6. Overall BOP impact

The Overall shadow uses 86% Financial V5, the unchanged Chase Accessibility transform at 4%, and unchanged Collector Appeal at 10%. It carries its own research identity, not V12. The completed Perfect Order Booster Pack Overall shadow threshold was **$3.58 at quantity 363**. It won at 358 cents; 359 cents lost across a quantity boundary.

No current-source full-cohort Overall V12 control artifact exists, so the Overall threshold-impact distribution and prospective Top-5/10/20 consequences remain unmeasured.

## 7. Pathology audit

The bounded exact searches reported no adjacent-cent failure. Both completed candidate thresholds sat exactly at quantity boundaries and passed the adjacent losing-cent check. The sample is too small to assess runaway behavior, score cliffs, broad monotonicity, or inversion rates.

## 8. Strongest evidence FOR V5

The adapter has demonstrated that frozen V5 scores and the separate Overall shadow can be used by the existing exact-cent search with candidate-specific benchmarks. A synthetic exact-search test and one live high-quantity product both passed the one-cent boundary check. This is plumbing evidence, not evidence that V5 adds useful high-win economics.

## 9. Strongest evidence AGAINST V5

The 0.979 current-market SR/Typical Retention correlation is a serious redundancy concern. This prompt produced no high-win counterevidence. The full threshold study is missing, so any promotion argument based on Best-Open improvements would be unsupported.

## 10. Blockers

- **Infrastructure/runtime:** Exact million-outcome construction at high Full Market quantities makes the current sequential full-cohort four-authority study operationally impractical. A single $5.11 loose pack required constructing quantity-level distributions near 358–363 units and took roughly six minutes even with the canonical batch builder. The full control attempt ran about 32 minutes without producing a cohort artifact; a candidate attempt logged 13 completed products before being stopped while evaluating this product. The completed one-product diagnostic was then rerun and saved separately.
- **Evidence gap:** Four exact thresholds, price-domain coverage, correlations, benchmark changes, and impact distributions for all 138 products have not been produced. This is not a scorer contradiction or observed adverse model behavior.
- The frozen V5 scorer was not changed. Canonical V4, Overall V12, rankings, Best-Open rows, production pointers, and public contracts were not changed. The latest published ranking and Best-Open snapshot IDs were unchanged on read-only recheck.

The 15 frozen-candidate tests and 3 research-adapter tests pass. New research files pass a direct trailing-whitespace scan. Workspace-wide `git diff --check` flags trailing whitespace only in a concurrently modified scheduler log.

## 11. Decision token

`FINANCIAL_RIP_V5_BEST_OPEN_LIVE_VALIDATION_BLOCKED`

Prompt 4 adjudication and production promotion must not proceed from this incomplete Best-Open evidence.
