# Treatment Hierarchy V2 — Preregistered Modern Pilot Estimator

Status: `FROZEN_BEFORE_TREATMENT_FIT`

Date frozen: 2026-10-01

This study does not alter the negative V1 decision. V1 correctly stopped because its frozen Price Storage V2 panel was insufficient and its preregistration prohibited source substitution. V2 is a new research contract motivated by the independently completed Treatment Panel Recovery V2.

No Treatment coefficient from this study had been fit when this contract was frozen.

## 1. Frozen evidence

Historical price panel:

- PkmnPrices `/v1/cards/:id/prices/history`
- source inside response: TCGPlayer
- currency: USD
- condition: exact `Near Mint`
- provider printing variant verified against the card endpoint before history retrieval
- period: 180d
- daily field used: `avg`
- no interpolation
- no nearest-date substitution
- no forward fill
- recovery workflow run: `36913676646`
- artifact ID: `11190000187`
- artifact digest: `sha256:e1cafb46732bf40932c8095b8f8266b05d256d2fdaa5761afc0fe1078be86233`

The source bridge in Treatment Panel Recovery V2 is descriptive justification for the new V2 authority. It is not represented as a preregistered V1 pass.

Exact Pull Scarcity:

- exact selected card-variant modeled probabilities
- September 29, 2026 calculation runs
- `exact_variant_pull_frequency_v1`
- all 36 pilot cards must have one positive modeled probability or the study stops

Collector controls:

- current frozen production Collector authority at execution time
- Subject baseline must cover 36/36 cards
- Artist and Playability are sensitivity authorities; missing evidence is never converted into a positive signal

## 2. Frozen cohort

Exactly the 16 identities / 36 cards in:

`docs/research/collector_appeal/treatment_panel_recovery_v2/pilot_manifest.json`

No card, identity, Set, treatment family, or date is added after fitting begins.

Four Set-relative families:

1. Common ↔ Illustration Rare
2. Illustration Rare ↔ Uncommon
3. Double Rare ↔ Ultra Rare
4. Double Rare ↔ Special Illustration Rare ↔ Ultra Rare

The study is limited to the Scarlet & Violet era. It cannot make a cross-era Treatment claim.

## 3. Primary estimands

### TREATMENT_PACKAGE

Matched-subject treatment association without Exact Pull Scarcity.

For every exact shared date inside an identity, log prices are demeaned within identity/date. Static treatment indicators are demeaned within identity. OLS is fit with no intercept.

This answers what the bundled treatment/rarity package is associated with.

### PURE_TREATMENT

Same matched-subject panel and Set-specific treatment indicators, plus one global Exact Pull Scarcity control:

`scarcity = -ln(modeled_probability)`

Scarcity is also demeaned within identity.

This is the primary candidate for eventual Collector Appeal research.

Subject popularity is controlled by construction because every comparison is within the same frozen subject/mechanic identity and identity/date demeaning removes any subject-level constant.

No market price is ever used as an input after the Treatment coefficients are learned.

## 4. Treatment parameterization

Treatment effects remain Set-specific.

Reference treatments are frozen as:

- Common for Common ↔ Illustration Rare
- Uncommon for Illustration Rare ↔ Uncommon
- Double Rare for Double Rare ↔ Ultra Rare
- Double Rare for Double Rare ↔ SIR ↔ Ultra Rare

No monotonic ordering is imposed.

A positive coefficient means that treatment is associated with a higher NM price than its Set-local reference after the controls in that estimand.

## 5. Artist / Playability sensitivity

The primary PURE_TREATMENT estimator does not impute missing Artist or Playability scores.

Sensitivity models are attempted separately:

- Artist-on: add frozen Artist score plus an explicit missing-authority indicator.
- Playability-on: add frozen Playability score plus an explicit missing-authority indicator.

Every sensitivity column is demeaned within identity.

If a sensitivity design is rank-deficient, it is reported `NOT_ESTIMABLE`, never silently regularized.

A treatment coefficient passes the corresponding sensitivity gate if:

- the sensitivity model is estimable and its absolute drift from PURE_TREATMENT is <= 0.50 log points; OR
- the control is invariant within every matched identity contributing to that coefficient, so identity fixed effects already absorb it.

Subject +/- tier sensitivity from V1 is invariant by construction under matched identity/date fixed effects and is reported as such.

## 6. Estimation / rank gates

Both PACKAGE and PURE designs must have full column rank.

Condition number is reported. No ridge/lasso or hidden regularization is permitted.

If PURE_TREATMENT is rank-deficient, the study stops with a scarcity-confounding decision and PACKAGE remains diagnostic only.

## 7. Bootstrap

Seed: `20261001`.

2,000 stratified matched-identity bootstrap draws.

Within each Set/family group, sample the same number of identities with replacement as observed. Include all of each sampled identity's frozen shared dates.

For each Set-specific treatment coefficient report:

- point estimate
- bootstrap 2.5 / 97.5 percentile interval
- sign stability relative to zero

Minimum sign stability for support: 0.80.

## 8. Influence

Because the matched identity is the unit of identification, influence testing removes one complete matched identity at a time rather than breaking an identity ladder by removing only one treatment card.

For each coefficient report maximum absolute leave-one-identity-out drift.

Maximum permitted drift: 0.50 log points.

## 9. Temporal test

For each identity, freeze the median exact shared date.

- early fold: dates <= median
- late fold: dates > median

Fit PACKAGE and PURE separately on both folds with the same frozen design.

Required temporal properties:

- global Spearman correlation of PURE treatment coefficients early vs late >= 0.60
- each individually supported coefficient must retain the same sign in early and late folds
- no post-hoc re-cutting of dates

## 10. Set and era decisions

A Set/family treatment coefficient is supported only if:

- panel readiness already passed;
- PACKAGE and PURE are estimable;
- bootstrap sign stability >= 0.80;
- leave-one-identity drift <= 0.50;
- early/late signs agree;
- required Artist / Playability sensitivity gate passes or is invariant by construction.

A Set/family group passes only if every non-reference treatment coefficient in that group passes.

An era/family hierarchy may be estimated only when two independent Sets for the same family pass.

Era pooling uses uncertainty-driven empirical Bayes only:

- direct Set coefficient + bootstrap variance
- between-Set variance estimated from the direct effects
- shrinkage derives from measurement variance versus between-Set variance
- no hand-selected pooling weight

Cross-era Treatment remains `NOT_REACHED` in this pilot because only Scarlet & Violet is authorized.

## 11. Decision tokens

Possible final tokens include:

- `TREATMENT_HIERARCHY_V2_SCARCITY_CONFOUNDED`
- `TREATMENT_HIERARCHY_V2_SET_LOCAL_ONLY`
- `TREATMENT_HIERARCHY_V2_SV_ERA_SUPPORTED`
- `TREATMENT_HIERARCHY_V2_DIAGNOSTIC_ONLY`

No positive token authorizes production Collector Appeal.

## 12. Prohibited actions

- zero production DB writes
- no Collector Appeal promotion
- no Overall RIP mutation
- no Rankings mutation
- no Set-page publication
- no Trainer/ANCHOR redesign
- no tuning gates after fitting
