# Set-Relative Treatment V2 — Identification Diagnostic

Status: `POST_HOC_DIAGNOSTIC_AFTER_FROZEN_V2_DECISION`

Frozen V2 decision:

`SET_RELATIVE_TREATMENT_HIERARCHY_V2_NOT_SUPPORTED`

This diagnostic does **not** change the preregistered decision, gates, cohort, model, or normalization entry gate. It explains why the frozen model failed identification.

## Frozen V2 result

Capture run:

- workflow run: `37099170569`
- fresh target fingerprint: `28b344ca8ea95ba8fbc9fa947cdb28a1a3d83408482572084ee83e1cf992563d`
- capture credits: **15,359**
- provider calls: **307**
- production writes: **0**
- history-ready fresh triads: **50 / 56**
- control-eligible fresh triads: **49 / 56**
- combined ready triads: **69**
- included Sets: **14**

The six provider identity failures were all Double Rare cards in Scarlet and Violet Base Set, leaving that Set with no complete ready triads.

One additional Pitch Black triad was excluded by the preregistered exact Playability-match rule:

- subject: `pokemon:pokemon:609`
- Double Rare Playability: **58.19568575255092**
- Ultra Rare Playability: **58.19568575255092**
- SIR Playability: **0.0**
- exclusion: `PLAYABILITY_CONTROL_MISMATCH`

The coverage gate still passed.

## Frozen statistical outcome

The directional Treatment pattern was highly consistent:

- SIR > Double Rare: **100% of included Sets**
- SIR > Ultra Rare: **100% of included Sets**
- both era point estimates positive
- early and late era signs positive
- every leave-one-triad-out refit preserved positive SIR/DR and SIR/UR era signs

However, the preregistered identification gates failed:

- full design rank: **30 / 30 — PASS**
- condition number <= 30: **636.04 — FAIL**
- shared scarcity beta positive with positive bootstrap lower bound: **FAIL**
- Mega SIR/DR bootstrap lower > 0: **FAIL**
- Mega SIR/UR bootstrap lower > 0: **FAIL**
- Scarlet & Violet SIR/DR bootstrap lower > 0: **FAIL**
- Scarlet & Violet SIR/UR bootstrap lower > 0: **FAIL**

Shared scarcity estimate:

- beta: **0.2515**
- 95% bootstrap interval: **-3.8886 to +3.8883**

The extremely broad Set and era Treatment intervals are therefore not interpreted as supported causal Treatment magnitudes.

## Design-geometry diagnostic

The frozen model is:

`y = theta_set(high) - theta_set(low) + beta_scarcity * log(p_low / p_high) + beta_artist * artist_delta/100`

Double Rare is the reference inside every Set.

To diagnose the failed conditioning gate, the design matrix was reconstructed from the **frozen Treatment membership and modeled pull probabilities only**. No price outcome was used in this diagnostic.

### Scarcity is almost determined by Set × Treatment

Regressing the scarcity predictor on the 28 Set-specific UR/SIR indicator columns gives:

- `R² = 0.9988969862`
- scarcity predictor SD: **0.71494**
- residual scarcity SD after Set×Treatment projection: **0.02374**
- maximum absolute residual: **0.09449**

Therefore **99.8897% of the scarcity variation is already encoded by which Set and Treatment family the card belongs to**.

This is the central identification problem.

### Condition-number decomposition

Using only:

- 28 Set-specific Treatment level columns
- shared scarcity column

the design has:

- Set/Treatment-only condition number: **2.83**
- Set/Treatment + scarcity condition number: **630.85**
- full preregistered design including Artist: **636.04**

After normalizing every design column to unit norm:

- condition number remains **154.18**

Therefore the failed conditioning gate is **not primarily a units/scaling artifact**. The near-collinearity remains after scale normalization.

The smallest singular value of the Set/Treatment + scarcity design is only:

- **0.03646**

versus largest singular value:

- **23.0020**

### Why this occurs

Inside each Set, modeled pull probability is nearly fixed by Treatment family.

Examples of within-Set edge scarcity-log variation:

- Perfect Order UR/DR SD: **0.0171**
- Perfect Order SIR/DR SD: **0.0115**
- Destined Rivals UR/DR SD: **0.0216**
- Destined Rivals SIR/DR SD: **0.0264**
- Temporal Forces UR/DR SD: **0.0100**
- Temporal Forces SIR/DR SD: **0.0221**
- White Flare UR/DR SD: **0.0148**
- White Flare SIR/DR SD: **0.0312**

Although exact card probabilities are not numerically identical, the within-Set/within-Treatment variation is tiny relative to the between-Treatment scarcity gaps.

Once every Set receives its own UR and SIR latent level, those Set-specific Treatment parameters can absorb nearly all of the scarcity structure. The shared scarcity coefficient is then identified only by the tiny residual pull-rate differences among same-Treatment cards inside each Set.

That is why:

- the model is full rank,
- point estimates are directionally coherent,
- but scarcity and Treatment magnitudes have enormous bootstrap uncertainty.

## Scientific interpretation

The frozen V2 study **does not support a calibrated Set-relative Treatment Appeal magnitude**.

It does provide strong descriptive evidence that, in these modern Sets, SIR cards consistently trade above matched DR and UR cards after the chosen point-estimate adjustment. But under the preregistered causal decomposition, the study cannot tell with adequate precision how much of that premium belongs to Treatment versus scarcity.

Accordingly:

- do not run the conditional Treatment Appeal normalization V1,
- do not map these point estimates to 0–100,
- do not shadow them into Collector Appeal,
- do not loosen the condition-number or scarcity gates,
- do not remove scarcity merely because it is inconvenient,
- do not reinterpret the 100% sign share as causal magnitude support.

## Next valid research designs

Any follow-up is a **new preregistered study**, not a V2 rescue.

### A. Scarcity-overlap / orthogonal-support design

Search the existing simulation authority for matched Set × Subject × Treatment observations where scarcity varies materially **within the same Treatment family**, rather than mainly between Treatment families.

Before observing prices, define minimum residual scarcity-support requirements such as:

- a minimum within-Set/Treatment scarcity-log range,
- a minimum residual scarcity SD after Set×Treatment projection,
- a maximum design condition number under the proposed cohort.

Only Sets/cohorts that clear the design-only geometry gate would proceed to price outcomes.

This is the cleanest extension if enough natural pull-rate variation exists.

### B. Hierarchical partial-pooling design

Instead of estimating an unconstrained UR and SIR level independently for every Set, preregister a hierarchical model in which Set effects are partially pooled around era-level Treatment effects.

This can use cross-Set scarcity variation for identification, but it introduces an explicit exchangeability/shrinkage assumption. That assumption must be frozen and stress-tested before price outcomes are fitted.

V2 cannot be retrospectively converted into this model.

### C. External scarcity instrument / structural supply authority

Use an independently varying structural scarcity measure that is not nearly deterministic from Treatment membership, if a defensible authority becomes available.

Examples would need to vary within Treatment family and Set without being constructed from card price.

### D. Direct preference evidence

A genuinely price-independent collector-preference study remains the strongest route for an intrinsic Treatment Appeal component.

Examples:

- controlled preference voting,
- blind visual pairwise comparisons,
- experimentally randomized presentation comparisons.

This would estimate preference without trying to separate two market-price drivers from the same observational price outcome.

## Recommended research disposition

Current Treatment state:

`TREATMENT_DIRECTIONAL_SIGNAL_STRONG_MAGNITUDE_NOT_IDENTIFIED`

This is a diagnostic label only, not a production decision token.

The frozen production/research boundary remains:

- canonical pricing mutation: **NONE**
- Collector Appeal mutation: **NONE**
- Overall RIP mutation: **NONE**
- Rankings mutation: **NONE**
- Set-page publication: **NONE**
