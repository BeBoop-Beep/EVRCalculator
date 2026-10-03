# FV-S3 Prospective +1-Day Forward Diagnostic Receipt

**Study:** `FV_S3_PROSPECTIVE_FORWARD_DIAGNOSTICS_V1`  
**Preregistration:** `fv_s3_prospective_shadow_preregistration_v1`  
**Rule under test:** `EXPLICIT_NM_SOLD_CLEARING_ANCHOR_V1`  
**Evaluation date:** 2026-10-02  
**+1 comparison date:** 2026-10-03  
**Frozen snapshot SHA-256:** `d9aa35e6127c64d500f7a665f43e773e16c08cd5619b9a95fa2f5f6f55ac3ad1`  
**Usable rows:** 189  
**Frozen root-set clusters:** 22  
**Prospective panel:** 207 cards total; 189 anchored, 18 anchor-insufficient.

## Decision

**PLUS1_FORWARD_SIGNAL_NOT_SUPPORTED**

At the +1-day horizon, the prospective sold-clearing anchor does not show robust evidence that its divergence from the contemporaneous TCGPlayer market predicts next-day price direction or improves next-day price prediction.

This is a horizon-specific result. It does **not** alter Anchor V1, and it does not resolve the preregistered +7 or +30 tests.

## Preregistered results

| Market stratum | n | Spearman(divergence, +1 return) | Sign agreement at |d| >= 5% | OLS slope | Set-cluster bootstrap 95% CI | Anchor MdAPE vs +1 | Market-t0 MdAPE vs +1 | Anchor closer |
| --- | ---: | ---: | ---: | ---: | --- | ---: | ---: | ---: |
| All | 189 | 0.044713 | 42.61% (115) | 0.012593 | [-0.000363, 0.013898] | 9.7985% | 0.4878% | 3.17% |
| >= $25 | 114 | -0.001379 | 44.44% (63) | 0.004761 | [-0.009557, 0.021162] | 7.2467% | 0.3707% | 4.39% |
| >= $100 | 51 | 0.093244 | 45.83% (24) | 0.015681 | [-0.003301, 0.028651] | 7.2710% | 0.3046% | 0.00% |
| >= $250 | 25 | -0.144666 | 33.33% (12) | 0.008325 | not computed: n < 30 | 7.2224% | 0.0917% | 0.00% |

The >= $250 stratum remains descriptive-only under the frozen `n >= 30` inference gate.

## Divergence terciles

Mean +1 market return by divergence tercile:

| Stratum | Lowest divergence | Middle | Highest divergence |
| --- | ---: | ---: | ---: |
| All | -0.2648% | -0.6891% | +1.0026% |
| >= $25 | -0.3872% | -0.3866% | -0.2674% |
| >= $100 | -0.4544% | -0.4616% | -0.1112% |
| >= $250 | -0.3816% | -0.5718% | -0.2594% |

The full-panel highest-divergence tercile is directionally higher, but this does not survive the stronger preregistered evidence tests: the rank correlation is near zero, sign agreement is below 50%, and the set-clustered slope interval includes zero. The price-filtered strata are also not supportive.

## Interpretation

1. **No robust next-day directional signal.** The all-card Spearman coefficient is only +0.0447, while sign agreement is 42.6%.
2. **The clustered slope is not distinguishable from zero.** The full-panel 95% interval crosses zero, as do the >= $25 and >= $100 intervals.
3. **The contemporaneous market price dominates as a +1 predictor.** Market-t0 MdAPE is 0.4878% versus 9.7985% for the sold anchor. The anchor is closer to the next-day price for only 6 of 189 cards (3.17%).
4. **H0 accuracy is not evidence of forward fair value.** The anchor can be a reasonable contemporaneous alternative price estimate while still failing to predict one-day reversion.
5. **Do not retune V1 from this result.** The preregistration requires a new rule version for any eligibility/window/estimator change.
6. **Do not blend components yet.** No production Fair Value number follows from +1. The +7 and +30 prospective tests remain required.

## Remaining preregistered gates

- **+7:** comparison date 2026-10-09.
- **+30:** comparison date 2026-11-01.
- Report all four frozen market-price strata at each horizon.
- Keep missing outcomes unimputed.
- Preserve the set-clustered bootstrap, seed `20261001`, 2,000 iterations.
- Do not select a favorable horizon or stratum after seeing results.

## Reproducibility

The offline hosted-runner analysis used the checked-in frozen `forward_diagnostics()` implementation and the frozen snapshot above.

Execution boundary:
- provider calls: 0
- provider credits: 0
- database reads during offline analysis: 0
- database writes: 0
- public-price writes: 0
- blended values produced: 0
