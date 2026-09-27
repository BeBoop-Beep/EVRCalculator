# Financial RIP V5 shortfall candidate: shadow freeze

Decision: `FINANCIAL_RIP_V5_SHADOW_IMPLEMENTATION_FROZEN`

## Authority and scope

- Checkout at implementation: detached HEAD `50d3db0cbfae428cd300320e93ebf85fbd661e5b`; local `develop` is `4de8e36b3bd71abc5c4db4ba49483ff559905bb0`, and `origin/develop` is `f5137823e5bdd6d6f3ebd244afa8d712c0b10d92`. The scoring and Best-Open files are identical between HEAD and `origin/develop`. Existing unrelated working tree edits were retained.
- Financial control: `financial_rip_v4_outcome_profile_p95_only_25_20_15_25_10_5`.
- Canonical Overall: `overall_rip_v12_86_financial_v4_04_chase_accessibility_v1_10_collector_appeal_v5`.
- Best-Open method identities: `budget_product_best_open_price_full_market_v1` and `budget_product_best_open_price_full_market_v2_dual_financial_v4_overall_v12`.
- No Financial V5 implementation was present in the inspected scoring code before this change.

## Frozen candidate

Candidate identity: `FINANCIAL_RIP_V5_CANDIDATE`; component key: `shortfall_resilience`.

For nonnegative outcome `X`, positive cost `COST`, and `R = X / COST`:

`SR = 100 * (0.70 * E[min(R, 1)] + 0.30 * (1 - 2 * E[(0.50 - R)+]))`

Equivalently, `SR = 100 * (1 - 0.70 * E[(1 - R)+] - 0.60 * E[(0.50 - R)+])`.

The scorer is in `backend/calculations/evr/financial_rip_v5_candidate.py`. It uses the V4 scorer for the five unchanged components and replaces only Loss Resilience. The weight vector is 25/20/15/25/10/5. The candidate has no canonical importer or persistence wiring. Shortfall Resilience is not passed through the V3 normalization table. The prepared calculation uses exact counts below `COST` and `0.5*COST` and prefix sums below those boundaries; it does not materialize a price-specific million-outcome vector.

## Projection limit

The persisted V3/V4 payload does not contain the sum of outcome values below `0.5*COST`. Its hard-loss probability contains a count, not the needed depth. Existing losing-outcome mean and P(win) may recover the first hinge expectation, but not the second. Different values inside the hard-loss bucket can preserve these aggregate fields while changing the second hinge. Payload-only projection therefore returns unavailable and requires the exact raw artifact or prepared distribution.

## Verification

- `python -m pytest backend/tests/unit/calculations/test_financial_rip_v5_candidate.py -q`: 15 passed.
- Direct NumPy versus prepared parity: six costs, absolute tolerance `1e-10`.
- V4 result unchanged before/after candidate scoring; all five component records identical.
- Score reconstructs from the declared weights; candidate carries a distinct identity.
- Downside dominance: zero violations at P(win) = 0.30, 0.50, 0.70, 0.90 for the tested improvement construction.
- Formula bounds checked on the tested nonnegative distributions; analytically each capped recovery and depth term lies in [0,1], hence SR lies in [0,100].
- Repaired synthetic constructs: distinct hard-loss/soft-loss vectors, exactly matched EV and P50 with different downside, and a P95 sweep with the downside vector held fixed. All pre-score controls and expected SR directions passed.
- `git diff --check`: passed.

Canonical Financial, Overall, Best-Open, public contract, and production constants are unchanged. No production database rows were written.

Live artifact validation, temporal validation, Best-Open shadow validation, adjudication, and production cutover remain separate gates. No production promotion is authorized by this freeze.

## Read-only live inventory (not a validation verdict)

On 2026-09-19, the latest `budget_product_ranking_snapshots` row was `0e65fb6d-ff33-4331-99d5-d6a214ecc712`, created 2026-09-16 03:18 UTC, with cohort fingerprint `e18fb00cd41f1646579b082164c80b0da3db2e1831dec9428c6fd4d82ac689ce`. A read-only join found 138 Full Market rows, 22 distinct source runs, and matching artifacts for all 22 runs. Each matched artifact declares 1,000,000 outcomes. This confirms inventory only; no current-price V4/V5 scoring, temporal analysis, or Best-Open threshold comparison has yet been completed.
