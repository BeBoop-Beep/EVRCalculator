# Collector V8 ANCHOR25 — Research Shadow

Decision: **COLLECTOR_V8_ANCHOR25_SHADOW_SUPPORTED_FOR_PROMOTION_REVIEW**

## Authority

- V7 control: pokemon_collector_appeal_v7_expanded_price_blind_v1 / e282f26e-2136-4105-b0a3-f0974c4d9d70
- V8 shadow: pokemon_collector_appeal_v8_anchor25_cross_domain_v1
- Temporal authority: ANCHOR25_TEMPORAL_VALIDATION_PASS across 5/5 folds
- Overall production control: overall_rip_v12_86_financial_v4_04_chase_accessibility_v1_10_collector_appeal_v5 / 0f83d958-95aa-40f1-bcfa-ec550ec3a379
- Production mutations: **NONE**

## Reconstruction gates

- Frozen V7 artifact: PASS
- V7 Set replay: **PASS**, max absolute error 0.0
- V12 product replay: **PASS**, max absolute error 0.0
- Pokemon scores unchanged; ANCHOR25 Trainer within-domain preservation inherited from validated temporal authority.

## Collector V7 -> V8 Set shadow

- Sets: 128
- Scored V7 / V8: 22 / 22
- Mean / median Collector delta: -0.027161 / -0.037160
- Maximum gain / loss: +0.115710 / -0.075931
- Rank correlation: 1.0
- Maximum absolute Set rank movement: 0
- Sets with rank change: 0
- Sets with F change: 0
- Sets with >50 desirable-card membership change: 0

## Overall RIP — isolated V7 -> V8 effect

Financial 86% and Chase 4% are frozen. Only the 10% Collector input changes.

- Mean / median score delta: -0.003074 / -0.003800
- Max gain / loss: +0.011600 / -0.007600
- Rank correlation: 0.9999954338551106
- Mean / max absolute rank move: 0.050725 / 2
- Rows with rank change: 13/276
- Tier changes: 1
- Top-10 overlap: 10/10

## Overall RIP — current production V12 -> V8 total hypothetical effect

This includes the already-researched V5->V7 Collector change plus V7->V8 ANCHOR25 calibration, so it is not an isolated ANCHOR25 estimate.

- Mean / median score delta: -0.281441 / -0.620050
- Rank correlation: 0.9827901999115309
- Mean / max absolute rank move: 11.884058 / 39
- Tier changes: 28
- Top-10 overlap: 9/10

## Boundary

This shadow does not create, publish, stage, or promote a Collector V8 model run or a new Overall RIP authority. A supported result advances only to a separate promotion-readiness review.

COLLECTOR_V8_ANCHOR25_SHADOW_SUPPORTED_FOR_PROMOTION_REVIEW
