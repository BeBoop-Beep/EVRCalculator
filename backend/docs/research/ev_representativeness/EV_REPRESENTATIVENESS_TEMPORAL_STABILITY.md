# Temporal Stability of EV Representativeness

Method version: **ev_representativeness_v1**
Coverage: **4 complete market dates**, **88 observations**, **22 sets**
Dates: **2026-08-17 through 2026-08-22**

## Scope and interpretation

This is a preliminary longitudinal baseline built only from exact historical one-million-pack artifacts and their frozen same-run prices. Four dates provide useful first evidence but not enough duration to establish long-term stability or seasonality. No V1/V2 series are spliced.

The persisted headline `firstCrossingN` is a **coarse-grid first crossing**. The stable headline is independently refined and confirmed. Public projections use only a refined stable horizon whose status is `resolved`; an audit candidate retained after `confirmation_did_not_ratify` is not public.

## Coverage

| Date | Sets |
|---|---|
| 2026-08-17 | 22 |
| 2026-08-18 | 22 |
| 2026-08-20 | 22 |
| 2026-08-22 | 22 |

## T1 — Rank stability

| Metric | Interval | n | Day/day Spearman | Vs baseline | Median rank move | Max move |
|---|---|---|---|---|---|---|
| typical_capture | 2026-08-17→2026-08-18 | 22 | 0.999 | 0.999 | 0.0 | 1.0 |
| typical_capture | 2026-08-18→2026-08-20 | 22 | 0.973 | 0.974 | 1.0 | 5.0 |
| typical_capture | 2026-08-20→2026-08-22 | 22 | 0.995 | 0.975 | 0.0 | 2.0 |
| top1_outcome_ev_share | 2026-08-17→2026-08-18 | 22 | 0.998 | 0.998 | 0.0 | 1.0 |
| top1_outcome_ev_share | 2026-08-18→2026-08-20 | 22 | 0.994 | 0.991 | 0.0 | 2.0 |
| top1_outcome_ev_share | 2026-08-20→2026-08-22 | 22 | 0.997 | 0.990 | 0.0 | 1.0 |
| horizon_r80_c80_stable | 2026-08-17→2026-08-18 | 22 | 0.994 | 0.994 | 0.0 | 3.0 |
| horizon_r80_c80_stable | 2026-08-18→2026-08-20 | 22 | 0.970 | 0.961 | 0.5 | 6.0 |
| horizon_r80_c80_stable | 2026-08-20→2026-08-22 | 22 | 0.994 | 0.966 | 0.0 | 3.0 |
| horizon_tau20_c80_stable | 2026-08-17→2026-08-18 | 22 | 0.997 | 0.997 | 0.0 | 1.5 |
| horizon_tau20_c80_stable | 2026-08-18→2026-08-20 | 21 | 0.998 | 0.999 | 0.0 | 1.5 |
| horizon_tau20_c80_stable | 2026-08-20→2026-08-22 | 20 | 0.984 | 0.986 | 0.0 | 3.0 |
| coefficient_of_variation | 2026-08-17→2026-08-18 | 22 | 0.999 | 0.999 | 0.0 | 1.0 |
| coefficient_of_variation | 2026-08-18→2026-08-20 | 22 | 0.998 | 0.997 | 0.0 | 1.0 |
| coefficient_of_variation | 2026-08-20→2026-08-22 | 22 | 0.999 | 0.995 | 0.0 | 1.0 |

## T2 — Absolute metric stability

Typical Capture stability extremes (coefficient of variation across available dates):

| Set | Min | Max | CV | Median daily |Δ| | P95 daily |Δ| |
|---|---|---|---|---|---|
| paldeanFates | 22.95% | 23.09% | 0.003 | 0.09% | 0.12% |
| obsidianFlames | 41.60% | 41.92% | 0.003 | 0.17% | 0.30% |
| ascendedHeroes | 35.77% | 36.10% | 0.004 | 0.11% | 0.15% |
| temporalForces | 34.94% | 35.22% | 0.004 | 0.10% | 0.16% |
| blackBolt | 29.78% | 30.11% | 0.005 | 0.20% | 0.21% |
| perfectOrder | 47.07% | 49.37% | 0.020 | 0.91% | 1.33% |
| scarletAndViolet151 | 29.09% | 30.56% | 0.021 | 0.46% | 0.61% |
| chaosRising | 43.17% | 45.35% | 0.025 | 0.51% | 2.01% |
| prismaticEvolutions | 19.07% | 20.86% | 0.038 | 1.18% | 1.42% |
| pitchBlack | 40.70% | 43.95% | 0.039 | 0.71% | 2.18% |

The complete per-set descriptive statistics remain reproducible from `ev_representativeness_history.csv`.

## T3–T5 — Market changes and representativeness

| Δ predictor | Δ outcome | n transitions | Pearson | Spearman |
|---|---|---|---|---|
| d_ev | d_typical_capture | 66 | -0.127 | 0.022 |
| d_ev | d_top1_outcome_ev_share | 66 | 0.404 | 0.033 |
| d_ev | d_horizon_r80_c80_stable | 66 | -0.184 | -0.071 |
| d_ev | d_horizon_tau20_c80_stable | 63 | 0.095 | 0.122 |
| d_pack_cost | d_typical_capture | 66 | -0.089 | 0.019 |
| d_pack_cost | d_top1_outcome_ev_share | 66 | 0.051 | -0.142 |
| d_pack_cost | d_horizon_r80_c80_stable | 66 | -0.186 | -0.332 |
| d_pack_cost | d_horizon_tau20_c80_stable | 63 | 0.212 | -0.059 |
| d_top1_outcome_ev_share | d_typical_capture | 66 | -0.652 | -0.526 |
| d_top1_outcome_ev_share | d_horizon_r80_c80_stable | 66 | 0.388 | 0.327 |
| d_top1_outcome_ev_share | d_horizon_tau20_c80_stable | 63 | 0.474 | 0.454 |

Pack-cost changes are analyzed separately from EV/card-distribution changes. Tier A top-1% outcome share is used for chase concentration; no historical card identity is inferred.

## T6 — Distributed appreciation candidates

| Set | Date | ΔEV | Δ Typical Capture | Δ Top-1% | Δ convergence |
|---|---|---|---|---|---|
| stellarCrown | 2026-08-22 | 0.034 | 0.60% | -0.36% | -42 |

## T7 — Threshold stability

V1 preserves realization targets 75%, 80%, and 90%, opener confidence levels 75%, 80%, and 90%, and convergence tolerances ±20% and ±25% in the research curves/horizon JSON. A larger temporal window is required before threshold-induced rank changes can justify a public score. The 80/80 and ±20%/80% choices remain descriptive parameters, not optimized weights.

## Forward baseline

Continuous automatic Tier A collection begins with the deployment following 2026-08-22. Historical backfill covers all exact artifacts currently present. Missing calendar dates reflect absent artifacts and are not reconstructed from current prices.

Recommendation: display current-run metrics descriptively in the Full Simulation Report, keep them below Overall RIP, and collect at least 60–90 daily observations spanning multiple market regimes before considering a headline horizon, Financial RIP change, or new score.
