# inDex Fair Value — F1 research contract

## Estimand and boundary

inDex Fair Value estimates the current structural market value of an eligible unseen raw Near Mint English card using independently governed demand, acquisition scarcity, Treatment, lifecycle, and structural metadata. It is a pricing model; Collector Appeal is not. It does not forecast returns, advise buying/selling, or establish that a model/market gap will close.

The target is the latest canonical positive Near Mint USD TCGPlayer `market_price` at the dataset as-of date. Primary training target is `ln(price)`. Dollar output is `exp(predicted ln(price))`, interpreted as the conditional median. A training-fold-only Duan smearing correction must be reported separately if a conditional-mean dollar estimate is desired; the held-out fold can never estimate that factor.

Structural Fair Value uses no price feature. Market-Conditional Fair Value is a separate Model D research candidate that may use medians of other cards in preregistered comparable cells, recomputed inside each training fold and excluding the target, its canonical identity family, and every held-out root set. Structural answers “what value is implied by governed non-price characteristics?” Market-conditional answers “what value is implied given the current price level of comparable market cards?” Neither is chosen merely because it scores better; both interpretations must remain labeled.

## Inputs

Collector Appeal is frozen V7/run `e282f26e-2136-4105-b0a3-f0974c4d9d70` and is never refit. The primary model uses the final card score. A preregistered component candidate may replace—not blindly duplicate—the composite with subject, Artist, and Playability components; variance inflation/correlation and ablation must document redundancy.

Scarcity uses accepted exact `modeled_probability`. Primary transform is `-log10(p)`; raw probability and expected packs `1/p` are fixed sensitivity transforms, not post-result choices. Missing exact scarcity excludes a card from strict V1.

Treatment uses taxonomy V3 era-local categories and semantic attributes, plus raw rarity/printing/special type/edition. No global prestige ladder or Treatment Preference score is allowed. Age is computed at price date/as-of date, with `log1p(age_days)` or an inner-fold spline. Age can proxy for attrition, collection lock-up, damage, historical significance, and grading behavior, but is not surviving supply. No grading/gem-rate authority exists.

## Validation and baselines

Outer validation leaves whole canonical root sets out. Child subsets stay with parents and physical variants/related canonical identities cannot cross folds. Hyperparameters use nested grouped validation. Random card splitting is prohibited. Era holdout and identity-family holdout are stress tests; current V1 is modern-only, so vintage is not scored.

Baselines B0–B7 are frozen in `index_fair_value_baseline_manifest.json`. B7 is the July 2026 model and mandatory negative control. Every model reports median/mean absolute dollar error, dollar RMSE, MdAPE, safe MAPE, log MAE/RMSE, OOS R², held-out Spearman, and proportions within ±10/20/30/50%. Breakdowns are price band, era, set, age, Treatment, Collector Appeal, and scarcity. Initial bands are <$5, $5–10, $10–25, $25–50, $50–100, $100–250, and $250+. Adjacent bands may be merged only from cohort counts before model outcomes are viewed.

Families A–D are frozen in the model manifest: regularized log-linear; interpretable GAM/spline; one boosted-tree family; and the isolated market-conditional counterpart. Do not run an algorithm tournament or add a family after final performance is seen.

## Fair Value Range

The preferred candidate is group-aware split conformal calibration on absolute log residuals, with residual-quantile and quantile-regression sensitivity analyses. Report empirical 50%, 80%, and 90% coverage and median width globally and by price band, era, Treatment, and age. No nominal interval is acceptable if a material cohort is severely undercovered.

## Fair Value Gap

`Fair Value Gap $ = Market Price - inDex Fair Value`. Negative means the market price is below the model-implied value; positive means above. Future display labels may say Below/Near/Above Fair Value, but F1 sets no thresholds. “Undervalued,” “overvalued,” “buy,” and “sell” are prohibited.

Current validation asks whether today's price can be estimated for unseen cards/sets. Future gap validation asks whether a point-in-time-safe historical gap predicts later movement. The latter requires contemporaneous historical Collector/scarcity/Treatment inputs and is out of F1.

## Reproducibility and readiness

`build_index_fair_value_research_dataset.py` emits one row per canonical card, eligibility/reason fields, exact source/run IDs, point-in-time metadata, and a SHA-256 fingerprint. All future article figures and numbers must be generated from versioned machine-readable outputs.

F2 is authorized only for the strict modern cohort. It must first freeze a new as-of dataset, verify counts/bands, and reproduce B7. Vintage, graded/condition-specific value, peer-context product semantics, and supply/liquidity claims remain blocked. No production price authority, Collector model, Treatment authority, Overall RIP, Financial RIP, Chase, or Market Explorer mutation is authorized.
