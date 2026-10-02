# Joint Treatment Ladder V1 — Confirmatory Replication Preregistration

Frozen before any replication PkmnPrices history is collected.

## Objective

Confirm or reject the exploratory shared-scarcity latent Treatment architecture
for three connected treatment classes:

- Double Rare (reference)
- Ultra Rare
- Special Illustration Rare (SIR)

This replication does not tune the model. It freezes the exploratory joint
formula exactly and applies it to an independent cohort that excludes every
Set+subject cluster used to discover the joint model.

## Frozen model

For every matched treatment edge within a Set+subject cluster:

`y = mean exact-date log(NM price_high / NM price_low)`

Fit jointly across all three edges:

`y = theta(high) - theta(low) + beta_scarcity * log(p_low / p_high) + beta_artist * (artist_high - artist_low)/100`

with:

- `theta(Double Rare) = 0`
- one shared `beta_scarcity` across all edges
- one shared Artist nuisance coefficient
- Subject Appeal controlled by exact matched identity
- frozen V7 Playability required to match within identity/treatment variants
- exact modeled pull probability from the 2026-09-29 simulation cohort
- historical PkmnPrices daily Near-Mint price history, exact provider variant
- no live/current price input to any future Treatment score

No additional interaction, era coefficient, family-specific scarcity coefficient,
nonlinear scarcity term, or monotonicity constraint may be added after results.

## Frozen discovery exclusions

The following 9 Set+subject clusters are excluded from all confirmatory fitting:

- Chaos Rising | pokemon:pokemon:573
- Chaos Rising | pokemon:pokemon:658
- Mega Evolution | pokemon:pokemon:282
- Mega Evolution | pokemon:pokemon:448
- Paldea Evolved | pokemon:pokemon:931
- Paldea Evolved | pokemon:pokemon:959
- Paldea Evolved | pokemon:pokemon:1002
- Paradox Rift | pokemon:pokemon:334
- Paradox Rift | pokemon:pokemon:445

## Frozen replication cohort

Use every complete Double Rare / Ultra Rare / SIR triad in these Sets after the
discovery exclusions above:

### Mega Evolution era
- Perfect Order — expected 4 independent complete triads
- Phantasmal Flames — expected 4 independent complete triads

### Scarlet & Violet era
- Scarlet & Violet 151 — expected 5 independent complete triads
- Twilight Masquerade — expected 4 independent complete triads
- Obsidian Flames — expected 4 independent complete triads

Expected replication cohort: **21 independent Set+subject clusters / 63 cards**.

No cluster may be replaced because of its observed prices or model result.
If identity/history quality blocks a cluster, report it unavailable. Do not
substitute a different cluster after seeing outcomes.

## Historical panel gates

Each card must have:

- exact canonical identity
- exact simulation card_variant_id
- exact modeled pull probability > 0
- exact PkmnPrices provider identity
- exact Near Mint + provider-variant historical daily series

Pairwise readiness within a triad:

- STRONG: >=90 exact shared dates
- MODERATE: >=30 exact shared dates
- BLOCKED: <30

A triad enters the confirmatory fit only when all three pairwise edges are at
least MODERATE.

Minimum replication fit:
- >=16 independent complete triads overall
- >=6 qualifying triads in Mega Evolution
- >=8 qualifying triads in Scarlet & Violet
- >=2 Sets represented per era where the frozen cohort supplies them

If these coverage gates fail, stop with
`JOINT_TREATMENT_LADDER_REPLICATION_INSUFFICIENT_COVERAGE`.

## Frozen statistical procedure

- OLS joint formula exactly as frozen above
- cluster unit = Set+subject
- 2,000 deterministic whole-cluster bootstrap draws
- seed = 20261002
- chronological median early/late split within each edge
- leave-one-cluster-out influence analysis
- cluster-equal weighting sensitivity
- Double Rare remains the zero reference

## Confirmatory success gates

All must pass:

1. Full joint design rank = 4.
2. Condition number <= 20.
3. Shared scarcity coefficient > 0 and its cluster-bootstrap 95% lower bound > 0.
4. SIR vs Double Rare log effect > 0 and 95% lower bound > 0.
5. SIR vs Ultra Rare log effect > 0 and 95% lower bound > 0.
6. Early and late temporal fits both keep SIR > Double Rare and SIR > Ultra Rare.
7. Every leave-one-cluster-out fit keeps SIR > Double Rare and SIR > Ultra Rare.
8. Replication SIR-vs-Double point estimate falls inside the exploratory
   cluster-bootstrap 95% interval [1.430718x, 4.857944x].
9. Replication SIR-vs-Ultra point estimate falls inside the exploratory
   cluster-bootstrap 95% interval [2.726998x, 5.119070x].
10. Replication shared scarcity beta falls inside exploratory 95% interval
    [1.342482, 1.913355].

Ultra Rare vs Double Rare is explicitly **not required** to resolve or have a
particular sign. Its estimate and interval must be reported neutrally.

If all gates pass:
`JOINT_TREATMENT_LADDER_V1_REPLICATION_PASS`

If statistical gates fail with adequate coverage:
`JOINT_TREATMENT_LADDER_V1_REPLICATION_FAIL`

## Production boundary

This study is research only.

- production writes = ZERO
- canonical pricing mutation = NONE
- Collector Appeal mutation = NONE
- Overall RIP mutation = NONE
- Rankings mutation = NONE
- Set-page publication = NONE

Even a PASS does not directly authorize a production 0-100 Treatment score.
A PASS would authorize freezing the 3-class DR/UR/SIR latent ladder as the
first validated Treatment authority component and designing the normalization /
additional-class extension study.
