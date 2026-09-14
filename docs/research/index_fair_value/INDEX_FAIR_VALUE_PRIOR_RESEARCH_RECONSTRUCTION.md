# inDex Fair Value — prior research reconstruction

Status: F1 research only. No Fair Value model is published.

## Chronology

### 2026-07-15 — desirability/Collector Appeal market studies

Commits `056b6a5b` and `ec1a0aea` introduced the set-level market study and `card_fair_value_v1_research`. The set work used 21 Scarlet & Violet/Mega Evolution sets. It related price-independent desirability/access/scarcity constructs to set value and concentration; it was not an individual-card appraisal. Card-price inputs remained outcomes only.

The individual-card study used 1,322 priced “hit” cards, 21 sets, and 615 subjects. Target: natural log of current TCGPlayer Near Mint market price (listing-derived, not completed sales). Validation: leave-whole-set-out; all reported predictions were out of fold. The ridge family used lambda 1.0. No random card split was used.

| Model | Features | OOS R² | Spearman | log MAE | log RMSE | dollar MAE | MdAPE | Verdict |
|---|---|---:|---:|---:|---:|---:|---:|---|
| B0 | rarity median | 0.6779 | 0.7396 | 0.6977 | 0.9285 | $20.57 | 48.77% | Strong tier separator, weak appraiser |
| B1 | rarity, era, log age | 0.5564 | 0.7081 | 0.8336 | 1.0896 | $23.76 | 62.21% | Worse than rarity median |
| B2 | subject desirability | 0.0466 | 0.0309 | 1.3450 | 1.5975 | $26.34 | 86.19% | Failed |
| B3 | modeled scarcity | 0.4754 | 0.6892 | 0.9432 | 1.1849 | $23.62 | 76.74% | Failed appraisal |
| B4 | desirability + scarcity | 0.5693 | 0.7306 | 0.8638 | 1.0737 | $21.08 | 67.29% | Failed appraisal |
| B5 | B4 + interaction | 0.5796 | 0.7337 | 0.8530 | 1.0607 | $20.22 | 66.87% | Interaction added only 0.0103 R² |
| B6 | composite Card Chase Appeal | 0.1374 | 0.0925 | 1.2874 | 1.5195 | $24.90 | 83.77% | Composite destroyed information |
| B7 | desirability, scarcity, interaction, treatment prestige, log age, alternate printings, competing hits, rarity, era | **0.7388** | **0.8352** | **0.6489** | **0.8361** | **$18.86** | **49.29%** | Best-looking; unacceptable appraisal |

RMSE dollars, MAPE, within-percent accuracy, and fixed business price-band accuracy were not reported. That omission is itself a prior-study failure and these metrics are mandatory in F2.

### Exact reconstruction of the misleading result

The remembered result is the B7 artifact above: R² rounds to 0.739, Spearman to 0.835, and MdAPE to 49.3%. Its R² within actual-price tiers was negative in every tier: under $5, -0.4567 (n=586); $5–25, -1.4423 (n=453); $25–100, -3.8477 (n=218); over $100, -2.3534 (n=65).

This is statistically coherent. Between-tier price variance dominates the global sum of squares. A model can correctly rank cheap versus expensive rarity/era/scarcity categories, producing high global R² and Spearman, while missing the price of an individual card by roughly half and doing worse than each tier's own mean once broad tier separation is removed. Log fitting also compresses the expensive tail; exponentiating without a documented smearing correction targets a conditional median, not an unbiased dollar mean.

The evidence points primarily to broad rarity/treatment/price-tier separation plus set/product effects and omitted variables—not direct target leakage. Validation held out whole sets and inputs were intended to be non-price features, but `treatment_prestige` was a research construct whose exact price-independence/portability is not adequate for the new contract and is therefore prohibited. Long-tailed prices and missing within-band calibration amplified the failure. Age and rarity were legitimate structural signals, not enough to recover surviving NM supply, liquidity, iconic identity, reprints, condition scarcity, or market microstructure.

### Historical valuation-gap verdict

The artifact defined gap as `ln(actual) - ln(out-of-fold expected)`: negative meant below model estimate. It explicitly prohibited under/overvaluation claims. Extreme negative gaps were dominated by Paldean Fates Shiny Rares that shared modeled scarcity/treatment but had ordinary market demand; e.g. Weavile $3.22 versus $32.58 predicted and Toxtricity $3.90 versus $39.39. Positive gaps included culturally/card-specifically exceptional cards such as Groudon, Charmander, Wartortle, and premium chase identities. These are missing-variable/model-calibration errors, not proven opportunities. No future-return, liquidity, volume, listing, population, or reprint validation existed. Confidence adjustment was blocked.

### 2026-09-11 — frozen Collector V7 price validation

Commit `55735a89` validated frozen, price-blind Collector V7 on 22 modern sets. This validated partial pricing signal, not a Fair Value estimator. V7 remains an input authority and must not be refit. Cross-era interpretation remained limited.

## Mandatory negative control

F2 must reproduce B7 on its frozen cohort and evaluation definition where possible, report the original metrics, then evaluate it under the new fixed price bands and full appraisal metrics. It must not be promoted, silently modernized, or used to select F2 features.

Sources: `card_fair_value_study.json`, `collector_appeal_market_prediction_study.json`, `collector_appeal_market_prediction_results.md`, and the V7 validation artifacts in this repository.
