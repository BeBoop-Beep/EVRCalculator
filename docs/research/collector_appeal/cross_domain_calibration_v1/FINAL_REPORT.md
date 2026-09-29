# Collector V8 Cross-Domain Calibration — Phase 1

## Authority

Pinned develop `871a1d480877ee70831cbfbb1801f0e99cbe6fe7` on `research/collector-cross-domain-calibration-v1-20260929`. Frozen V7 run `e282f26e-2136-4105-b0a3-f0974c4d9d70` and all declared fingerprints validated.

## Control reproduction

The 4,331-row, 22-set cohort was reconstructed with 24 exclusions. Historical replay status: **CONTROL_REPLAY_NOT_EXACT**. Historical median/weighted errors were 0.005672 / 0.000443.

## Findings

V7 compares a raw 75/25 Pokemon authority with a within-Trainer-percentile 40/60 authority. Distinct frozen identities: 1061 Pokemon and 250 Trainer. This scale asymmetry is real, but composition was diagnostic only. All Pokemon scores remained exact; Trainer mappings were monotone. Current-price results are labeled `TEMPORAL_SECONDARY_SCREEN`; they do not replace the frozen historical test.

The preregistered grid was CONTROL, ANCHOR25, ANCHOR50, ANCHOR75, ANCHOR100. Artist and Playability mechanics were frozen through the artifact's combined headroom lift, with exact control equivalence. Negative controls (domain z-score and full domain quantile equalization) are documentation-only because they erase magnitude and risk saturation.

Cross-domain pairs used same set, normalized rarity, slot group, promo, secret, and mechanic flags. Whole-set bootstrap used 1000 deterministic draws (seed 20260929). Full results, composition, repetition, set shadows, sensitivities, and named cases are in the adjacent JSON artifacts.

## Decision

**CALIBRATION_SIGNAL_PRESENT_BUT_VALIDATION_BLOCKED** — Historical control or candidate gates prevent promotion.

Production mutations: **NONE**. Overall RIP was not modified or published.

## Git

Branch: `research/collector-cross-domain-calibration-v1-20260929`. Merge: **NO**. Main untouched. Deployment: **NO**. Final SHA is to be recorded after commit.

COLLECTOR_CROSS_DOMAIN_CALIBRATION_V1_READY_FOR_REVIEW
