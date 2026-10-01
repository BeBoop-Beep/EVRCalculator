# Treatment Hierarchy V3 — Expanded Modern Pilot Preregistration

Status: `FROZEN_BEFORE_EXPANDED_COLLECTION_RESULT_OR_FIT`

Date frozen: 2026-10-01

## 1. Purpose

Treatment Hierarchy V2 repaired the historical panel blocker and showed excellent temporal stability, but no Set/family coefficient passed because the deliberately minimal two-identity pilot had bootstrap sign stability below 0.80 and leave-one-identity influence far above 0.50 log points.

V3 changes exactly one thing: evidence depth.

It expands the same eight Set/family experiments from two to five matched identities each using the deterministic, price-blind selection frozen in:

`docs/research/collector_appeal/treatment_panel_recovery_v3/expanded_manifest.json`

Manifest fingerprint from the zero-credit preflight:
`55b8dcd3090acb707d101a3b03e574862cc3ef15f752c95940870f7b4b3d6e24`

Sample fingerprint:
`7fecdbd2cb448dd9414f062d0d83b16a58b187dcbd7bf679cf781dc295d7b23e`

No V3 treatment coefficient has been fit at freeze time.

## 2. Frozen cohort

- 40 matched identity-group entries
- 92 unique canonical cards
- 7 Sets
- Scarlet & Violet era only
- same four treatment families as V2
- five identities per Set/family
- exact September 29, 2026 simulation-supported Sets

The Set/family groups remain:

1. Surging Sparks — Double Rare / SIR / Ultra Rare
2. Scarlet & Violet 151 — Double Rare / SIR / Ultra Rare
3. Shrouded Fable — Common / Illustration Rare
4. White Flare — Common / Illustration Rare
5. Black Bolt — Illustration Rare / Uncommon
6. Paldea Evolved — Illustration Rare / Uncommon
7. Paradox Rift — Double Rare / Ultra Rare
8. Surging Sparks — Double Rare / Ultra Rare

No identities may be added, removed, or substituted after collection results are inspected.

## 3. Historical price authority

Same construct as Treatment Hierarchy V2:

- PkmnPrices `/v1/cards/:id/prices/history`
- TCGPlayer USD
- exact `Near Mint`
- exact verified provider printing variant
- 180-day period
- daily `avg`
- no interpolation
- no nearest-date substitution
- no forward fill

Collection is research-only and may write local workflow artifacts only.

## 4. Exact Pull Scarcity

Unchanged from V2:

- exact selected card-variant modeled probability
- September 29, 2026 simulation authority
- `exact_variant_pull_frequency_v1`
- every card contributing to PURE_TREATMENT must have one positive modeled probability

If expanded cards do not satisfy this authority, they are not silently imputed and the affected frozen group fails.

## 5. Primary estimands

Exactly unchanged from V2.

### TREATMENT_PACKAGE

Matched-subject treatment association without Exact Pull Scarcity.

Within each identity/date panel, log prices are demeaned by identity/date. Set-specific treatment indicators are estimated with no intercept.

### PURE_TREATMENT

Same matched-subject panel and Set-specific treatment indicators, plus:

`scarcity = -ln(modeled_probability)`

Scarcity is demeaned within identity.

PURE_TREATMENT is the only candidate lane relevant to eventual Collector Appeal research. PACKAGE is diagnostic.

No current/live price is ever authorized as a runtime Treatment-score input.

## 6. Parameterization

References remain unchanged from V2:

- Common for Common ↔ Illustration Rare
- Uncommon for Illustration Rare ↔ Uncommon
- Double Rare for Double Rare ↔ Ultra Rare
- Double Rare for Double Rare ↔ SIR ↔ Ultra Rare

No monotonic rarity ordering is imposed.

## 7. Design-rank rule

PACKAGE and PURE must both have full column rank.

Condition number is reported.

No ridge, lasso, hidden regularization, coefficient clipping, or post-hoc pooling is allowed to rescue a rank-deficient direct estimator.

If PURE is rank-deficient, PACKAGE remains diagnostic only.

## 8. Bootstrap gate

Unchanged from V2:

- 2,000 stratified matched-identity bootstrap draws
- seed `20261001`
- resampling unit: complete matched identity
- stratified by Set/family
- all exact shared dates for a sampled identity move together
- minimum coefficient sign stability: **0.80**

## 9. Influence gate

Unchanged from V2:

- remove one complete matched identity at a time
- maximum permitted absolute coefficient drift: **0.50 log points**

This is the primary gate the expanded evidence is intended to stress-test. The threshold is NOT changed because the V2 sample failed it.

## 10. Temporal gate

Unchanged from V2:

- per identity, split at its median exact shared date
- early = dates <= median
- late = dates > median
- same frozen design in both folds
- PURE early/late coefficient Spearman >= **0.60**
- every individually supported coefficient retains the same sign early and late
- no date re-cutting after results

## 11. Artist / Playability sensitivity

Unchanged from V2.

Artist and Playability are sensitivity authorities, not imputed positive signals.

For each:
- add frozen score plus explicit missing-authority indicator;
- demean within identity;
- if rank-deficient, report `NOT_ESTIMABLE`;
- pass if estimable drift from PURE <= **0.50 log points**, OR the control is invariant within every contributing matched identity and therefore absorbed by identity effects.

## 12. Support decision

A non-reference Set/family treatment coefficient is supported only if all are true:

- expanded panel is ready under the frozen recovery thresholds;
- PACKAGE and PURE are estimable;
- bootstrap sign stability >= 0.80;
- leave-one-identity drift <= 0.50;
- early/late signs agree;
- required Artist / Playability sensitivity passes or is invariant by construction.

A Set/family group passes only if every non-reference coefficient in that group passes.

An era/family hierarchy is estimated only if two independent Sets for the same family pass.

Era pooling, if reached, remains uncertainty-driven empirical Bayes exactly as V2 specified.

## 13. Comparison to V2

V3 must explicitly report whether increasing from two to five identities per Set/family changes:

- bootstrap sign stability;
- leave-one-identity influence;
- PURE coefficient magnitude/sign;
- scarcity-removed gap;
- temporal coefficient stability;
- number of supported Set/family groups.

The analysis may not reinterpret a failure as success merely because point estimates look plausible.

## 14. Scope boundary

Only Scarlet & Violet is authorized.

Cross-era Treatment remains `NOT_REACHED`.

No production Collector Appeal use is authorized by any positive V3 research result.

## 15. Decision tokens

Possible final dispositions include:

- `TREATMENT_HIERARCHY_V3_SCARCITY_CONFOUNDED`
- `TREATMENT_HIERARCHY_V3_SAMPLE_DEPTH_STILL_INSUFFICIENT`
- `TREATMENT_HIERARCHY_V3_SET_LOCAL_ONLY`
- `TREATMENT_HIERARCHY_V3_SV_ERA_SUPPORTED`
- `TREATMENT_HIERARCHY_V3_DIAGNOSTIC_ONLY`

## 16. Prohibited actions

- no production database writes
- no canonical price mutation
- no Collector Appeal promotion
- no Overall RIP mutation
- no Rankings mutation
- no Set-page publication
- no Trainer/ANCHOR redesign
- no post-hoc gate changes
- no adding identities after expanded collection results are known
