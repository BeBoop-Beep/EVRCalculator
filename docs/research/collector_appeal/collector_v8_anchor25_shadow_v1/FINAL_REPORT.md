# Collector V8 ANCHOR25 Shadow V1

Decision: COLLECTOR_V8_ANCHOR25_SHADOW_READY_FOR_PROMOTION_REVIEW

## Inputs

- Frozen V7 model run: e282f26e-2136-4105-b0a3-f0974c4d9d70
- Candidate: ANCHOR25 only
- Temporal prerequisite: ANCHOR25_TEMPORAL_VALIDATION_PASS
- Production mutations: NONE

## V7 replay

- Exact Set replay: True
- Max absolute replay error: 0.0

## V8 Set impact

- Sets: 22
- Score Spearman V7 vs V8: 1.0
- Rank Spearman V7 vs V8: 1.0
- Mean / median score delta: -0.027161360862924703 / -0.037159808723295384
- Maximum Set rank move: 0

| Set | V7 | V8 | Delta | V7 rank | V8 rank |
|---|---:|---:|---:|---:|---:|
| Black Bolt | 54.7397 | 54.8554 | +0.1157 | 22 | 22 |
| Paradox Rift | 70.2616 | 70.1857 | -0.0759 | 18 | 18 |
| Paldea Evolved | 69.5244 | 69.4644 | -0.0599 | 19 | 19 |
| Scarlet and Violet Base Set | 73.8086 | 73.7514 | -0.0572 | 15 | 15 |
| Obsidian Flames | 83.4973 | 83.4427 | -0.0546 | 5 | 5 |

## Hypothetical Overall impact

- Market date: 2026-09-29
- V12 component replay passed: True
- Products: 138 across 22 Sets
- Score Spearman V7-shadow vs V8-shadow: 0.9999999999999998
- Rank Spearman: 0.9999999999999998
- Mean / median Overall delta: -0.003076811594202859 / -0.0037999999999982492
- Maximum absolute product-rank move: 0
- Top-10 overlap: 10/10

This is a research-only substitution of V8 for V7 inside the same 86/4/10 Overall structure. It does not publish a new Collector version or Overall version.

COLLECTOR_V8_ANCHOR25_SHADOW_READY_FOR_PROMOTION_REVIEW
