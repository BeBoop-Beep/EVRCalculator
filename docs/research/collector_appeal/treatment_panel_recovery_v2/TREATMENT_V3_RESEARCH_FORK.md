# Treatment V3 Research Fork

Status: `PREREGISTERED_AFTER_V2_CLOSURE`

Date: 2026-10-03

Source decision:

`SET_RELATIVE_TREATMENT_HIERARCHY_V2_NOT_SUPPORTED`

## Why V3 must fork

Treatment V2 produced two distinct findings:

1. **Directional market regularity is strong.** SIR versions traded above matched Double Rare and Ultra Rare versions in every included Set.
2. **Intrinsic Treatment magnitude is not identified.** Set × Treatment membership explains essentially all modeled scarcity variation, so observational price data cannot reliably separate Treatment from pull scarcity in the Set-relative model.

The full 22-Set predictor-only geometry scan confirms that adding more DR/UR/SIR observations from the same design does not solve this.

Therefore Treatment research now separates into two different scientific questions.

## Path A — Intrinsic Collector Treatment

Question:

> Holding subject identity and other known preference drivers as constant as practical, do collectors prefer one visual/card Treatment over another?

This is the primary path for any future **Collector Appeal** component.

Required evidence must be independent of market price.

Preferred experiment:

- blind pairwise visual preference,
- same Subject identity within a comparison wherever possible,
- randomized left/right order,
- no card price,
- no rarity name,
- no pull rate,
- no set market value,
- no Collector score,
- no Chase score,
- no indication of which card is rarer or more valuable.

Primary outcome:

- direct human preference probability between Treatments.

This path is defined in:

`TREATMENT_DIRECT_PREFERENCE_V1_PREREGISTRATION.md`

## Path B — Market-Predictive Treatment

Question:

> Does deterministic Treatment taxonomy improve out-of-sample prediction of market value after scarcity and other structural features are included?

This belongs to **Index Fair Value / market modeling**, not frozen price-blind Collector V7.

Required semantics:

- market-trained,
- Treatment is a structural feature,
- scarcity remains separately represented,
- strict held-out Set and/or forward-time validation,
- no evaluation outcome may have trained the Treatment coefficient used to predict it.

A positive result here does not establish intrinsic collector preference.

## Path C — Hierarchical Observational V3

Question:

> Under an explicit partial-pooling assumption, can Set-level Treatment effects be estimated more stably than the unconstrained V2 design?

This path is allowed only as secondary research.

It introduces a new assumption:

- Set-specific Treatment effects are exchangeable around era/global Treatment distributions.

Requirements before fitting:

- hierarchy and priors/shrinkage frozen before new confirmation outcomes,
- sensitivity to shrinkage strength,
- held-out Set prediction,
- no use of V2 failure to tune the prior until the result passes,
- result described as model-dependent observational inference, not direct preference.

This path cannot supersede Path A for intrinsic Collector Appeal without independent evidence.

## Decision hierarchy

For Collector Appeal:

1. direct preference evidence,
2. independent replication,
3. normalized Treatment preference authority,
4. research shadow,
5. only then consideration of production integration.

For Fair Value:

1. frozen deterministic Treatment taxonomy,
2. preregistered out-of-sample market model,
3. held-out / forward validation,
4. independent confirmation,
5. only then consideration of market-model integration.

## V2 evidence that remains valid

Retain as descriptive evidence:

`SIR > {Double Rare, Ultra Rare}`

Interpretation:

Across the tested modern matched identities, SIR versions consistently commanded higher market values.

Do not convert that statement into a causal Treatment multiplier.

## V2 evidence that is retired for scoring

Do not use:

- V2 Set-specific point multipliers,
- V2 era point multipliers,
- V2 scarcity coefficient,
- any 0–100 normalization derived from those coefficients.

Conditional normalization V1 remains unactivated.

## Production boundary

No production mutation is authorized by this fork.

- Collector Appeal: unchanged
- Fair Value: unchanged
- Overall RIP: unchanged
- Rankings: unchanged
- Set pages: unchanged
