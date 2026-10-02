# Treatment Appeal Normalization V1 — Conditional Preregistration

Frozen on 2026-10-02 before the broad Set-relative Treatment V2 expansion outcome is observed.

## Purpose

Define the next research step if and only if the preregistered Set-relative Treatment hierarchy V2 returns:

`SET_RELATIVE_TREATMENT_HIERARCHY_V2_SUPPORTED_FOR_EXPANSION`

This document does **not** authorize production scoring. It freezes how supported Set-relative Treatment effects would be converted into a bounded research-only Treatment Appeal authority without choosing the normalization after seeing the V2 results.

## Entry gate

Do not run this study unless all of the following are true:

1. The frozen 56-triad fresh expansion capture passes its preregistered coverage gate.
2. The combined Set-relative V2 fit returns `SET_RELATIVE_TREATMENT_HIERARCHY_V2_SUPPORTED_FOR_EXPANSION`.
3. Production writes from the Treatment research chain remain zero.
4. The V2 result artifact and both input panel fingerprints are frozen and recorded.
5. No discovery-panel cluster is introduced into the confirmatory V2 authority after outcomes are observed.

If any condition fails, stop. Do not rescue the normalization by changing the cohort, gates, or transform.

## Scope of V1

V1 is limited to Treatment families with confirmatory support in the connected Set-relative authority.

At minimum, the currently connected family is:

- Double Rare
- Ultra Rare
- Special Illustration Rare

Mega Hyper Rare and Illustration Rare remain unavailable to the normalized authority unless a later preregistered cross-family study clears its own multi-Set support gates.

An unsupported Treatment must be emitted as unavailable, not imputed from visual similarity, rarity name, package position, or price.

## Source authority

The only allowed primary input is the frozen Set-relative V2 research result.

For each qualifying Set, define latent log Treatment levels:

- `theta_set(Double Rare) = 0`
- `theta_set(Ultra Rare)` from the V2 fit
- `theta_set(SIR)` from the V2 fit

The shared scarcity and Artist coefficients remain nuisance controls. They are not themselves Treatment Appeal components.

Current card price, TCGPlayer price, active ask, sold price, Fair Value, EV, Chase score, Collector score, or Overall RIP may not enter the scoring-time Treatment Appeal calculation.

Historical price evidence is used only to learn the frozen Treatment authority offline.

## Set-first authority

Treatment Appeal remains Set-relative.

Scoring-time authority order:

1. **Qualified Set-specific level** when the Set has a supported V2 Set estimate.
2. **Qualified era-level level** when a Set-specific authority is unavailable but its era has supported V2 authority.
3. **Global supported-family level** only when neither Set nor era authority exists and a later validation explicitly permits the global fallback.
4. Otherwise: **UNAVAILABLE**.

No card-level price may be used to choose among these fallbacks.

## Qualification of a Set-specific level

A Set-specific Treatment level is eligible for normalization only when:

- the Set is present in the frozen V2 result,
- the Set contributed at least 3 ready independent triads,
- the full V2 model has complete rank,
- the V2 global identification gates pass,
- the requested Treatment contrast exists in the fitted Set,
- the Set estimate is finite,
- no data-integrity or fingerprint drift is present.

The V1 normalization study will report Set-specific uncertainty but will not post-hoc delete a Set merely because its Treatment ordering is inconvenient.

## Normalization transform

Double Rare is the neutral reference:

`raw_log_treatment(Double Rare) = 0`

Let `L` be the selected supported Set/era log Treatment level for the requested Treatment.

Define the robust scale `S` from the frozen supported non-reference log levels in the normalization cohort:

`S = median(abs(L_i))`

where the cohort contains one equal-weight observation per qualified Set × supported non-reference Treatment level.

Requirements:

- `S > 0`
- every qualified Set receives equal weight,
- no card-count weighting,
- no market-cap weighting,
- no price weighting,
- no winner-based trimming.

Normalize with the preregistered bounded transform:

`TreatmentAppeal = 100 / (1 + exp(-ln(3) * L / S))`

Properties fixed in advance:

- Double Rare (`L=0`) = **50**
- `L=+S` = **75**
- `L=-S` = **25**
- values asymptotically approach 0 and 100 without hard clipping the latent effect.

Do not tune the slope after observing V2 results.

## Era and global fallback construction

If Set-specific authority is unavailable:

### Era fallback

For a supported Treatment within an era:

`L_era = equal-weight mean of qualified Set log levels in that era`

Requirements:

- at least 3 qualified Sets in the era,
- no card-count weighting,
- no substitution of discovery-only Sets.

### Global fallback

Global fallback is disabled by default in V1.

It may be enabled only by a later preregistered validation showing acceptable out-of-Set transport. Until then, an unsupported Set/era combination is unavailable.

## Uncertainty

The normalized research artifact must carry uncertainty from the V2 Set-stratified bootstrap.

For each Set/era Treatment level:

1. transform every valid bootstrap log-level draw using the same frozen scale definition,
2. report percentile 95% Treatment Appeal intervals,
3. preserve correlation between Treatment contrasts by transforming whole bootstrap draws rather than independent marginal intervals.

The point score is descriptive research output. Uncertainty is mandatory.

## Temporal stability

The normalization study must transform the already-preregistered V2 early and late refits separately.

Required report:

- full-period Treatment Appeal
- early Treatment Appeal
- late Treatment Appeal
- absolute early/late score movement
- sign/order stability for supported SIR contrasts

No temporal gate may be invented after seeing the normalized values.

## Sensitivity

Report, without changing the primary decision:

- normalized results using the full V2 point estimates,
- normalized results under every leave-one-triad-out V2 refit,
- Set-level score ranges,
- era-level score ranges.

The primary transform remains the preregistered median-absolute-log scale above.

## Cross-family expansion

Mega Hyper Rare, Illustration Rare, and any later Treatment family enter only through a new preregistered connected-family study.

Requirements for adding a new family:

- at least 2 independent qualifying Sets in each claimed era,
- exact matched subject identity,
- exact simulation pull probabilities,
- exact historical provider variant,
- shared-date gate identical to the applicable Treatment study,
- connection to at least one already-supported Treatment family,
- positive identification and robustness gates frozen before outcome collection.

A one-Set diagnostic cannot define a normalized production authority.

## Shadow integration gate

Even after a successful normalization study, integration is research-only first.

A Collector Appeal shadow may be built only if:

1. the Set-relative V2 architecture passes,
2. the normalization implementation reproduces this preregistration exactly,
3. the normalized artifact has deterministic fingerprints,
4. unsupported Treatment families remain unavailable,
5. current price is absent from scoring-time inputs,
6. the pre-Treatment Collector Appeal authority can be reproduced exactly as a control,
7. shadow output is versioned separately from the existing Collector Appeal authority.

## Collector Appeal shadow comparison

The first shadow study must compare:

- current price-blind Collector Appeal authority,
- current authority + normalized Treatment Appeal challenger.

It must report:

- global rank correlation,
- Pokémon rank correlation,
- Trainer rank correlation,
- Artist rank correlation,
- Playability rank correlation,
- top/bottom decile churn,
- largest absolute rank movers,
- Set concentration of movers,
- Treatment-family concentration of movers,
- missing-authority rate.

No production weight is preregistered here.

A later experiment must choose and gate the Treatment weight before promotion.

## Explicit non-goals

This study does not:

- decide Ultra Rare vs Double Rare must have one universal ordering,
- infer unsupported Treatment families,
- use current price as a card feature,
- mutate Collector Appeal,
- mutate Overall RIP,
- mutate Rankings,
- publish Set-page scores,
- replace scarcity with Treatment,
- treat rarity name alone as Treatment authority.

## Production boundary

Research only.

- canonical pricing writes: **ZERO**
- Collector Appeal mutation: **NONE**
- Overall RIP mutation: **NONE**
- Rankings mutation: **NONE**
- Set-page publication: **NONE**

A successful V1 normalization study authorizes a shadow Collector Appeal experiment only. It does not authorize production cutover.
