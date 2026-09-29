# Collector Cross-Domain Calibration V1 — Independent Temporal Validation

Decision: ANCHOR25_TEMPORAL_VALIDATION_PASS

## Frozen authority

- Parent Phase 1 SHA: 012e38b1e9a85491ba2ba72b746f8baead6112ea
- Frozen Collector control: pokemon_collector_appeal_v7_expanded_price_blind_v1 / e282f26e-2136-4105-b0a3-f0974c4d9d70
- Candidate: ANCHOR25 only
- Cohort/predictors: immutable frozen V7 4,331-row artifact
- Price states: immutable repo artifacts generated with pre-drift Phase 1 SQL semantics
- Production mutations: NONE

## Structural lock

- Frozen V7 artifact valid: True
- Frozen cohort contract: True
- Sep-11 exact baseline replay: True
- Pokemon unchanged: True
- Trainer Spearman >= 0.995: True

## Fixed temporal folds

| Date | Coverage | Pass | delta weighted rho | delta OOS R2 | delta held-out rho | delta pair concordance |
|---|---:|:---:|---:|---:|---:|---:|
| 2026-09-14 | 4331/4331 | YES | +0.002015 | +0.000894 | +0.000695 | +0.004363 |
| 2026-09-17 | 4331/4331 | YES | +0.002208 | +0.000889 | +0.000656 | +0.005411 |
| 2026-09-20 | 4331/4331 | YES | +0.002124 | +0.000903 | +0.000508 | +0.003379 |
| 2026-09-23 | 4331/4331 | YES | +0.002051 | +0.000952 | +0.000574 | +0.005923 |
| 2026-09-26 | 4331/4331 | YES | +0.002245 | +0.000951 | +0.000667 | +0.005908 |

## Gate

- Data-valid folds: 5/5
- Passing folds: 5/5
- Required: at least 4 of 5 complete fold passes.
- Bootstrap: 1000 deterministic whole-Set draws per data-valid fold.

A PASS supports only a research-only Collector V8 shadow. It does not change current Collector V7 or publish Overall RIP.

ANCHOR25_TEMPORAL_VALIDATION_PASS
