# Set-Relative Treatment Hierarchy V2 — Broad Independent Expansion Preregistration

Frozen after the five-Set Set-relative follow-up failed its preregistered identification gates, and before collecting any additional historical price outcomes for the expansion Sets.

## Objective

Test whether the Set-relative Treatment architecture becomes identifiable when the independent panel spans substantially more Sets and more within-Set treatment triads.

The frozen structural model remains:

`y = theta_set(high) - theta_set(low) + beta_scarcity * log(p_low / p_high) + beta_artist * artist_delta/100`

with:
- Double Rare anchored at 0 independently inside each Set
- Set-specific Ultra Rare and SIR latent levels
- one shared scarcity coefficient across all Sets
- one shared Artist nuisance coefficient
- exact matched Subject identity
- frozen V7 Playability required to match within a triad
- no monotonicity constraint
- no Set × scarcity interaction
- no nonlinear scarcity term
- no family-specific scarcity coefficient

The model is not changed in response to the failed five-Set result. Only independent coverage is expanded.

## Existing independent panel retained

Retain the 20 ready triads captured in workflow run `36971438903`:

### Mega Evolution
- Perfect Order — 4 triads
- Phantasmal Flames — 4 triads

### Scarlet & Violet
- Obsidian Flames — 4 triads
- Scarlet & Violet 151 — 4 triads
- Twilight Masquerade — 4 triads

The blocked Blastoise ex triad remains excluded. No substitution.

## Frozen fresh expansion panel

Collect every complete Double Rare / Ultra Rare / SIR triad in the following Sets, excluding all prior discovery and prior replication clusters.

### Mega Evolution
- Pitch Black — 4 complete triads

### Scarlet & Violet
- Destined Rivals — 8 complete triads
- Surging Sparks — 7 complete triads
- Black Bolt — 6 complete triads
- Journey Together — 6 complete triads
- Scarlet & Violet Base Set — 6 complete triads
- Temporal Forces — 6 complete triads
- White Flare — 6 complete triads
- Shrouded Fable — 4 complete triads
- Stellar Crown — 3 complete triads

Expected fresh expansion: **56 triads / 168 cards / 10 Sets**.

Expected combined independent panel: **76 triads / 15 Sets**.

Do not replace a blocked triad with another subject after seeing prices. All expected triads are defined solely from canonical identity + treatment membership before new history capture.

## Historical panel authority

For every card:
- exact canonical identity
- exact simulation card_variant_id from the 2026-09-29 simulation cohort
- exact modeled pull probability > 0
- exact PkmnPrices provider identity
- exact Near Mint daily historical price series
- exact provider printing variant
- no interpolation
- no forward fill

Triad readiness:
- each of the three treatment edges must have >=30 exact shared dates
- STRONG >=90 shared dates
- MODERATE >=30 shared dates
- otherwise triad unavailable

## Expansion coverage gate

Proceed to the combined Set-relative fit only if:
- >=45 of 56 fresh triads are ready overall
- Pitch Black contributes >=3 ready triads
- >=7 of the 9 fresh Scarlet & Violet Sets contribute >=3 ready triads each
- >=120 fresh cards return usable history
- production writes = 0

If this fails, stop with:
`SET_RELATIVE_TREATMENT_V2_INSUFFICIENT_EXPANSION_COVERAGE`

## Combined Set-relative model

Combine all ready fresh-expansion triads with the 20 ready prior replication triads.

Use the same frozen model:

`y = theta_set(high) - theta_set(low) + beta_scarcity * log(p_low / p_high) + beta_artist * artist_delta/100`

For every included Set:
- `theta_set(Double Rare)=0`
- estimate `theta_set(Ultra Rare)`
- estimate `theta_set(SIR)`

No discovery-panel clusters may enter this fit.

## Bootstrap

2,000 deterministic draws, seed `20261002`.

Resampling unit = whole Set+subject triad.

Stratified by Set:
- resample within each Set with replacement
- preserve every included Set in every draw
- sample size within each Set equals its number of ready triads

Report percentile 95% intervals for:
- each Set's Ultra vs Double
- each Set's SIR vs Double
- each Set's SIR vs Ultra
- each era's equal-weight mean Set contrast
- shared scarcity coefficient
- shared Artist nuisance coefficient

## Era aggregation

Era values are equal-weight means of Set log levels, not card-count weighted.

Mega Evolution era includes all qualifying independent Mega Sets in the combined panel.

Scarlet & Violet era includes all qualifying independent Scarlet & Violet Sets in the combined panel.

## Temporal stability

Split each edge chronologically at its median date and refit the same combined model to:
- early halves
- late halves

## Influence

Leave one whole triad out at a time and refit.

Report:
- shared scarcity beta range
- era-level contrast ranges
- Set-level contrast ranges

## Identification / support gates

The architecture is supported for expansion only if all are true:

1. Full design has complete rank.
2. Condition number <= 30.
3. Shared scarcity coefficient > 0 and bootstrap 95% lower bound > 0.
4. Both era-level SIR vs Double point estimates > 0.
5. Both era-level SIR vs Ultra point estimates > 0.
6. Both era-level SIR vs Double bootstrap 95% lower bounds > 0.
7. Both era-level SIR vs Ultra bootstrap 95% lower bounds > 0.
8. Early and late era-level SIR vs Double remain > 0 in both eras.
9. Early and late era-level SIR vs Ultra remain > 0 in both eras.
10. Every leave-one-triad-out fit preserves positive era-level SIR vs Double and SIR vs Ultra in both eras.
11. At least 70% of individual Sets have point-estimate SIR > Double.
12. At least 70% of individual Sets have point-estimate SIR > Ultra.

Ultra Rare vs Double Rare is descriptive and may vary by Set.

If all gates pass:
`SET_RELATIVE_TREATMENT_HIERARCHY_V2_SUPPORTED_FOR_EXPANSION`

If coverage passes but statistical gates fail:
`SET_RELATIVE_TREATMENT_HIERARCHY_V2_NOT_SUPPORTED`

## Production boundary

Research only.

- production writes = ZERO
- canonical pricing mutation = NONE
- Collector Appeal mutation = NONE
- Overall RIP mutation = NONE
- Rankings mutation = NONE
- Set-page publication = NONE

A PASS would authorize designing a cross-family Treatment Appeal normalization study. It would not authorize production scoring by itself.
