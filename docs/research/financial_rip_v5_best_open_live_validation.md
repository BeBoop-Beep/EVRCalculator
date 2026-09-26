# Financial V5 Best-Open live validation

## 1. Control integrity

- Exact current ranking snapshot `0e65fb6d-ff33-4331-99d5-d6a214ecc712`; fingerprint `e18fb00cd41f1646579b082164c80b0da3db2e1831dec9428c6fd4d82ac689ce`; 138 products; budget $1300.00.
- V2 control method `budget_product_best_open_price_full_market_v2_dual_financial_v4_overall_v12` reproduced 138 products. Four authorities produced 552 exact thresholds; 552 passed the winning-cent and adjacent-losing-cent checks.
- All 552 axis comparisons used the benchmark selected under their own current V4, V5, V12, or Overall-V5 ranking authority.
- V5 was scored by the frozen candidate scorer from exact prepared distributions. Candidate ranking and comparator identities were recomputed under their own fields. Overall shadow identity is `OVERALL_RIP_FINANCIAL_V5_SHADOW`.

## 2. High-win coverage

- Distinct real candidate-price evaluations: 1,200,199.
- Price-state / distinct-product counts: <0.20: 1,200,170 / 138; 0.20-0.30: 29 / 1.
- Products reaching P(win) ≥30/50/70/80%: 0/0/0/0.
- Product IDs crossing 30/50/70/80% are listed in `candidatePriceDomain.productIdsAtOrAbove` in the JSON evidence.

## 3. Plateau finding

No evaluated candidate-price state reached P(win) >=50%; the proposed V4 high-win plateau could not be tested in the exact Best-Open domain.
No two distinct high-win anchors are available for a price-to-score delta chain.

## 4. Shortfall distinctness

| P(win) regime | States | SR/Typical Pearson | Spearman | SR/P(win) Pearson | Spearman | SR/BEE Pearson | Spearman |
|---|---:|---:|---:|---:|---:|---:|---:|
| all | 1,200,199 | 0.9915 | 0.9932 | 0.2829 | 0.3373 | 0.9491 | 0.9937 |
| <0.20 | 1,200,170 | 0.9915 | 0.9932 | 0.2830 | 0.3373 | 0.9491 | 0.9937 |
| 0.20-0.50 | 29 | 1.0000 | 1.0000 | 0.9999 | 1.0000 | 1.0000 | 1.0000 |
| >=0.50 | 0 | n/a | n/a | n/a | n/a | n/a | n/a |

Prompt 2 current-market SR/Typical Pearson was 0.979; this remains a material redundancy concern.
Across all 1,200,199 real scored price states, SR/Typical Pearson is 0.9915. The 20–50% slice contains 29 states from 1 observed product-band entries; it cannot establish cross-product distinctness.
No >=50% candidate-price states were observed, so there is no real high-win correlation or Type A-D counterexample to establish distinctness.

## 5. Financial BOP impact

- mean/median/P10/P25/P75/P90/min/max cents -242.0/-139.0/-554.3/-342.2/-19.0/-11.0/-2158/106; mean absolute 247.3; unchanged 0.0%, within ±1% 11.6%, within ±5% 98.6%, >5% 1.4%, >10% 0.0%
- Benchmark changes 0; quantity changes 81; leader changes 0; Top-5/10/20 overlap {'5': 5, '10': 8, '20': 19}.
- Largest upward threshold changes: Phantasmal Flames Booster Box +106 cents (score_substitution_same_benchmark_quantity, local model score delta +3.6684); Paldean Fates Booster Bundle +86 cents (score_and_quantity_boundary, local model score delta +3.5457); Paldean Fates Elite Trainer Box +76 cents (score_substitution_same_benchmark_quantity, local model score delta +3.3944); Phantasmal Flames Pokemon Center Elite Trainer Box (Exclusive) +70 cents (score_substitution_same_benchmark_quantity, local model score delta +3.5138); Phantasmal Flames Elite Trainer Box +8 cents (score_substitution_same_benchmark_quantity, local model score delta +3.2970); Ascended Heroes Booster Pack +7 cents (score_substitution_same_benchmark_quantity, local model score delta +3.1938); Paldean Fates Booster Pack +6 cents (score_substitution_same_benchmark_quantity, local model score delta +3.4616); Ascended Heroes Booster Bundle +4 cents (score_substitution_same_benchmark_quantity, local model score delta +3.1905); Prismatic Evolutions Booster Pack -2 cents (score_substitution_same_benchmark_quantity, local model score delta +3.1199); Phantasmal Flames Booster Pack -3 cents (score_and_quantity_boundary, local model score delta +2.9416)
- Largest downward threshold changes: Paldea Evolved Pokemon Center Elite Trainer Box (Exclusive) -2158 cents (score_and_quantity_boundary, local model score delta +0.1901); 151 Pokemon Center Elite Trainer Box (Exclusive) -2016 cents (score_substitution_same_benchmark_quantity, local model score delta +0.2090); Destined Rivals Pokemon Center Elite Trainer Box (Exclusive) -1223 cents (score_and_quantity_boundary, local model score delta +0.1750); Paldean Fates Pokemon Center Elite Trainer Box (Exclusive) -1210 cents (score_substitution_same_benchmark_quantity, local model score delta +0.8353); Obsidian Flames Pokemon Center Elite Trainer Box (Exclusive) -1001 cents (score_substitution_same_benchmark_quantity, local model score delta +0.0442); Ascended Heroes Pokemon Center Elite Trainer Box (Exclusive) -817 cents (score_substitution_same_benchmark_quantity, local model score delta +1.5279); Paldea Evolved Booster Box -746 cents (score_substitution_same_benchmark_quantity, local model score delta +0.8413); Paradox Rift Booster Box -721 cents (score_and_quantity_boundary, local model score delta +0.1427); Twilight Masquerade Booster Box -683 cents (score_substitution_same_benchmark_quantity, local model score delta +0.3963); Destined Rivals Booster Box -654 cents (score_substitution_same_benchmark_quantity, local model score delta +0.7545)

## 6. Overall BOP impact

- mean/median/P10/P25/P75/P90/min/max cents -264.0/-132.5/-536.3/-325.0/-17.8/-11.0/-6212/227; mean absolute 269.8; unchanged 0.0%, within ±1% 10.9%, within ±5% 97.8%, >5% 2.2%, >10% 0.0%
- Benchmark changes 0; quantity changes 85; leader changes 0; Top-5/10/20 overlap {'5': 5, '10': 8, '20': 19}.
- Financial shifts >5% with Overall shifts <=5%: 0; shifts >5% in both: 2. Maximum local residual from the fixed 86% Financial propagation: 0.000096 score points (rounding included).
- Largest upward threshold changes: Phantasmal Flames Booster Box +227 cents (score_substitution_same_benchmark_quantity, local model score delta +3.3397); Paldean Fates Elite Trainer Box +89 cents (score_substitution_same_benchmark_quantity, local model score delta +2.9592); Paldean Fates Booster Bundle +58 cents (score_substitution_same_benchmark_quantity, local model score delta +3.0426); Paldean Fates Booster Pack +9 cents (score_and_quantity_boundary, local model score delta +2.9869); Phantasmal Flames Elite Trainer Box +7 cents (score_substitution_same_benchmark_quantity, local model score delta +2.8445); Ascended Heroes Booster Pack +6 cents (score_and_quantity_boundary, local model score delta +2.7540); Ascended Heroes Booster Bundle +4 cents (score_substitution_same_benchmark_quantity, local model score delta +2.7438); Prismatic Evolutions Booster Pack -1 cents (score_substitution_same_benchmark_quantity, local model score delta +2.6893); Phantasmal Flames Booster Pack -3 cents (score_and_quantity_boundary, local model score delta +2.6040); Phantasmal Flames Sleeved Booster Pack -3 cents (score_and_quantity_boundary, local model score delta +2.6007)
- Largest downward threshold changes: 151 Pokemon Center Elite Trainer Box (Exclusive) -6212 cents (score_and_quantity_boundary, local model score delta +0.1628); Paldea Evolved Pokemon Center Elite Trainer Box (Exclusive) -2030 cents (score_and_quantity_boundary, local model score delta +0.1664); Destined Rivals Pokemon Center Elite Trainer Box (Exclusive) -1131 cents (score_substitution_same_benchmark_quantity, local model score delta +0.1507); Twilight Masquerade Booster Box -1116 cents (score_and_quantity_boundary, local model score delta +0.2781); Paldean Fates Pokemon Center Elite Trainer Box (Exclusive) -1112 cents (score_substitution_same_benchmark_quantity, local model score delta +0.8729); Ascended Heroes Pokemon Center Elite Trainer Box (Exclusive) -817 cents (score_substitution_same_benchmark_quantity, local model score delta +1.3140); Paldea Evolved Booster Box -801 cents (score_substitution_same_benchmark_quantity, local model score delta +0.7128); Obsidian Flames Pokemon Center Elite Trainer Box (Exclusive) -782 cents (score_substitution_same_benchmark_quantity, local model score delta +0.0457); Destined Rivals Booster Box -753 cents (score_substitution_same_benchmark_quantity, local model score delta +0.6174); Mega Evolution Enhanced Booster Box -576 cents (score_substitution_same_benchmark_quantity, local model score delta +0.2057)

## 7. Pathology audit

- Exactness failures 0; unresolved searches 0; recorded monotonicity fallbacks 0. Quantity-boundary cases and one-cent adjacency are retained per product in JSON.
- Across 1,195,080 adjacent cents with unchanged quantity, V5 score inversions: 0; V4 score inversions: 0. Adjacent quantity boundaries: 4,980.
- Largest same-quantity one-cent V5 score step: {'sealedProductId': '14eddeda-becd-452d-a27d-f00e70136cb2', 'higherPriceCents': 400, 'lowerPriceCents': 399, 'higherQuantity': 325, 'lowerQuantity': 325, 'v5ScoreDeltaAtLowerCent': 0.33619999999999806, 'v4ScoreDeltaAtLowerCent': 0.33270000000000266, 'committedCapitalDelta': -3.25, 'pWinDelta': 0.0025029999999999983, 'typicalDelta': 0.1570000000000107, 'shortfallDelta': 0.13769999999999527}; largest quantity-boundary step: {'sealedProductId': 'c9efb943-605a-4ed6-8ed8-8eb5d0ef2c41', 'higherPriceCents': 18572, 'lowerPriceCents': 18571, 'higherQuantity': 6, 'lowerQuantity': 7, 'v5ScoreDeltaAtLowerCent': -9.404100000000007, 'v4ScoreDeltaAtLowerCent': -8.094899999999996, 'committedCapitalDelta': 185.6500000000001, 'pWinDelta': -0.11383499999999999, 'typicalDelta': 0.12049999999999983, 'shortfallDelta': 0.6974000000000018}.
- At the largest boundary step, the allocation changes from 6 to 7 packs. Committed capital changes +185.65, P(win) changes -0.1138, V4 changes -8.0949, and V5 changes -9.4041. This is an observed allocation boundary, not a same-quantity one-cent price effect.
- Lowest evaluated candidate price: 354 cents; maximum observed V5 Financial score: 55.7896. These are observed search states, not an extrapolation below the exact search domain.

## 8. Strongest evidence FOR V5

No evaluated price state entered P(win) >=50%; this study supplies no real high-win example that establishes distinct Shortfall Resilience information.

## 9. Strongest evidence AGAINST V5

The current-market Shortfall/Typical correlation is 0.979. The largest absolute Financial threshold shift is Paldea Evolved Pokemon Center Elite Trainer Box (Exclusive) at -2158 cents; observed mechanisms: ['candidate_score_change', 'threshold_quantity_change']. Price-state correlations above should be assessed with sample counts; benchmark changes can move thresholds independently of within-product downside improvement.

## 10. Blockers

No source-lineage, control-reproduction, candidate-implementation, or exact-search correctness blocker. The real Best-Open domain did not reach high P(win), which limits the economic interpretation of the proposed high-win correction. This is research evidence, not production approval.

## 11. Decision token

`FINANCIAL_RIP_V5_BEST_OPEN_LIVE_VALIDATION_COMPLETE`

Production rows, pointers, models, and contracts remain unchanged. Prompt 4 adjudication is the next gate.
