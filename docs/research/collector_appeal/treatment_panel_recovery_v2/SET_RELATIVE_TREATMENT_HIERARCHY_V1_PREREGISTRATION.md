# Set-Relative Treatment Hierarchy V1 — Post-Replication Follow-up Preregistration

Frozen after the global joint replication failed its preregistered effect-size replication gates, but before inspecting any Set-specific treatment estimates from the replication panel.

## Motivation

The preregistered global joint replication preserved direction and statistical stability but failed quantitative replication of the discovery effect sizes. This follow-up tests the original hierarchical hypothesis:

> Treatment should be estimated inside each Set first, then summarized within era, rather than forcing one universal treatment coefficient across all Sets.

This is an exploratory redesign prompted by the failed global replication. It does not retroactively convert the failed global study into a pass.

## Frozen input panel

Use only the independent replication panel captured by workflow run `36971438903`.

No discovery clusters may enter this fit.

Use the 20 complete triads that passed the replication panel readiness rules:

### Mega Evolution
- Perfect Order — 4 triads
- Phantasmal Flames — 4 triads

### Scarlet & Violet
- Obsidian Flames — 4 triads
- Scarlet & Violet 151 — 4 triads
- Twilight Masquerade — 4 triads

The one blocked Blastoise ex triad remains excluded. No replacement is allowed.

Every included triad contains:
- Double Rare
- Ultra Rare
- Special Illustration Rare
- exact modeled pull probabilities from the 2026-09-29 simulation authority
- exact Near Mint PkmnPrices historical series
- frozen V7 Subject / Artist / Playability controls

## Frozen model

For each exact matched treatment edge:

`y = mean exact-date log(NM_price_high / NM_price_low)`

Fit one joint fixed-effects model:

`y = theta_set(high) - theta_set(low) + beta_scarcity * log(p_low / p_high) + beta_artist * artist_delta/100`

where:
- each Set has its own `theta_set(Ultra Rare)`
- each Set has its own `theta_set(SIR)`
- `theta_set(Double Rare) = 0` for every Set
- one shared `beta_scarcity`
- one shared `beta_artist`
- Subject is controlled by exact identity and must cancel
- frozen V7 Playability must cancel within each treatment triad
- no era coefficient is fit directly
- no monotonicity constraint
- no nonlinear scarcity term
- no Set × scarcity interaction
- no family-specific scarcity coefficient

## Era aggregation

After fitting Set-specific treatment levels:

- Mega Evolution era level = equal-weight mean of Perfect Order and Phantasmal Flames Set log levels.
- Scarlet & Violet era level = equal-weight mean of Obsidian Flames, Scarlet & Violet 151, and Twilight Masquerade Set log levels.
- Cross-era summaries report the two era estimates independently and their difference.

Do not weight Sets by number of cards; all five Sets contain four qualifying triads.

## Bootstrap

2,000 deterministic bootstrap draws, seed `20261002`.

Resampling unit = whole Set+subject triad.

Bootstrap is stratified by Set:
- resample 4 triads with replacement inside each Set
- preserve all five Sets in every draw

This prevents a draw from dropping a Set and making Set-specific treatment levels unidentified.

Report percentile 95% intervals for:
- each Set's Ultra vs Double level
- each Set's SIR vs Double level
- each Set's SIR vs Ultra contrast
- each era's three contrasts
- shared scarcity coefficient
- shared Artist nuisance coefficient

## Temporal stability

Within each treatment edge, split exact shared dates at the chronological median.

Refit the same frozen Set-relative model to:
- early halves
- late halves

Report all Set and era treatment contrasts for both periods.

## Influence analysis

Leave one complete triad out at a time and refit.

Report the min/max across leave-one-triad-out fits for:
- each Set treatment contrast
- each era treatment contrast
- shared scarcity coefficient

Do not fail the entire study merely because Ultra vs Double changes sign; no monotonic treatment ordering is imposed.

## Descriptive heterogeneity

Report, without a tuned pass/fail threshold:
- range and standard deviation of Set-specific Ultra-vs-Double log levels
- range and standard deviation of Set-specific SIR-vs-Double log levels
- range and standard deviation of Set-specific SIR-vs-Ultra log contrasts
- era means and cross-era differences

## Interpretation gates

This follow-up may conclude `SET_RELATIVE_TREATMENT_HIERARCHY_SUPPORTED_FOR_EXPANSION` only if:

1. Full design rank is complete.
2. Condition number <= 30.
3. Shared scarcity coefficient is positive and bootstrap 95% lower bound > 0.
4. Every Set has SIR > Double Rare in the point estimate.
5. Every Set has SIR > Ultra Rare in the point estimate.
6. Both era-level SIR > Double and SIR > Ultra bootstrap 95% lower bounds are > 0.
7. Early and late era-level SIR > Double and SIR > Ultra remain positive in both eras.
8. Every leave-one-triad-out fit preserves era-level SIR > Double and SIR > Ultra in both eras.

Ultra Rare vs Double Rare is descriptive only and may vary by Set.

If these gates fail with a valid fit:
`SET_RELATIVE_TREATMENT_HIERARCHY_NOT_YET_SUPPORTED`

## Production boundary

Research only.

- production writes = ZERO
- canonical pricing mutation = NONE
- Collector Appeal mutation = NONE
- Overall RIP mutation = NONE
- Rankings mutation = NONE
- Set-page publication = NONE

Even a positive result does not authorize a production Treatment score. It would authorize expansion to additional treatment families and design of the cross-family normalization layer.
