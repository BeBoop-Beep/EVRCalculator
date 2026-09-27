# Financial RIP V5 Best-Open runtime remediation

Decision: `FINANCIAL_RIP_V5_BEST_OPEN_LIVE_VALIDATION_COMPLETE`.

Frozen source snapshot `0e65fb6d-ff33-4331-99d5-d6a214ecc712`; cohort fingerprint `e18fb00cd41f1646579b082164c80b0da3db2e1831dec9428c6fd4d82ac689ce`.

## Frozen control parity

All eight Phase 10B thresholds matched before and after batching. Threshold quantities, benchmark identities, and exactness payloads also matched: True. Wall time 546.5s to 270.3s (2.02x). Post-change peak RSS: 349368320 bytes; pre-change RSS unavailable in the original sampler.

## High-quantity product

Perfect Order Booster Pack: two prior passes 312.0s; fused batched pass 159.6s (1.96x).
Financial 363 cents at q=358; Overall shadow 358 cents at q=363.
Both axes match retained threshold, benchmark, and stored score; both winning cents are exact with the adjacent cent losing.
Maximum pending batch 8; effective RNG draws 4650000000; separate-construction equivalent 35030000000; peak RSS 399872000 bytes.
Construction 159.40959910012316s; price scoring 0.0214106006314978s; comparator 0.0003987002419307828s.

## Full cohort progress

Control 138/138; V5 candidate 138/138. Per-product evidence is checkpointed under `logs/` and excluded from Git.
Accumulated exact-search wall time: control 3740.5s with 3616.7s constructing quantities; V5 3830.5s with 3673.6s constructing quantities.
All 138 control and candidate products and the final four-threshold report are complete.

Pre-change focused tests: 40 passed. Post-change focused and affected exact-search tests: 126 passed.

The blocked Prompt 3 report and JSON are preserved under `financial_rip_v5_best_open_blocked_20260919.*`. Canonical Financial V4 and Overall V12 remain active. This run performed no production database writes, publication, pointer change, migration, or frontend change. Prompt 4 has not started.
