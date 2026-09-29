# Collector Cross-Domain Calibration V1 — Independent Temporal Validation

Decision: ANCHOR25_TEMPORAL_VALIDATION_INVALID

## Authority

- Parent Phase 1 SHA: 012e38b1e9a85491ba2ba72b746f8baead6112ea
- Frozen Collector control: pokemon_collector_appeal_v7_expanded_price_blind_v1 / e282f26e-2136-4105-b0a3-f0974c4d9d70
- Candidate: ANCHOR25 only
- Historical price authority: get_pokemon_market_root_standard_card_prices_as_of_v2 (exact corrected Phase 1 authority)
- Production mutations: NONE

## Structural lock

- Frozen artifact valid: True
- Sep-11 exact baseline replay: False
- Cohort contract: True
- Pokemon unchanged: True
- Trainer Spearman >= 0.995: True

## Fixed temporal folds

| Date | Coverage | Pass | delta weighted rho | delta OOS R2 | delta held-out rho | delta pair concordance |
|---|---:|:---:|---:|---:|---:|---:|
| 2026-09-14 | 0/4331 | NO | n/a | n/a | n/a | n/a |
| 2026-09-17 | 0/4331 | NO | n/a | n/a | n/a | n/a |
| 2026-09-20 | 0/4331 | NO | n/a | n/a | n/a | n/a |
| 2026-09-23 | 0/4331 | NO | n/a | n/a | n/a | n/a |
| 2026-09-26 | 0/4331 | NO | n/a | n/a | n/a | n/a |

## Gate

- Data-valid folds: 0/5
- Passing folds: 0/5
- Required: at least 4 of 5 complete fold passes.
- Bootstrap: 1000 deterministic whole-Set draws per data-valid fold.

A PASS supports only a research-only Collector V8 shadow. It does not change current Collector V7 or publish Overall RIP.

ANCHOR25_TEMPORAL_VALIDATION_INVALID
