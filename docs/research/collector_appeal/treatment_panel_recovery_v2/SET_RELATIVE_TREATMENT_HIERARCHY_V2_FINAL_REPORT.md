# Set-Relative Treatment Hierarchy V2 — Final Confirmatory Result

Status: `SET_RELATIVE_TREATMENT_HIERARCHY_V2_NOT_SUPPORTED`

Date: 2026-10-03 UTC

This report records the preregistered confirmatory result. The failed gates are not rescued or redefined here.

## Frozen evidence chain

### Fresh capture

Controlled run: `37083526829`

Artifact: `11260560244`

Artifact SHA-256:

`a47a4ca4c5814b1318df89eb63fedae61dd2f15f34d4024116d539cb9587abbd`

Provider receipt:

- PkmnPrices calls: **307**
- PkmnPrices credits: **15,359**
- provider daily limit: **75,000**
- production writes: **0**
- fresh cards with returned history: **162 / 168**
- history-ready triads: **50 / 56**

The six unresolved cards were Double Rare provider-identity misses in Scarlet and Violet Base Set. The frozen historical coverage gate nevertheless passed.

### Frozen control eligibility correction

The preregistration required exact Subject and frozen V7 Playability matching inside each triad.

One history-ready triad was mechanically excluded before fitting:

- Pitch Black
- `pokemon:pokemon:609`
- Mega Chandelure ex
- reason: `PLAYABILITY_CONTROL_MISMATCH`

Subject baseline matched exactly. Double Rare and Ultra Rare Playability were `58.19568575255092`; SIR was `0`.

After enforcing the already-frozen rule:

- control-eligible fresh triads: **49**
- Pitch Black eligible: **3**
- qualifying Scarlet & Violet fresh Sets: **8 / 9**
- coverage gate: **PASS**

No replacement triad was introduced.

### Prior independent panel

Frozen run: `36971438903`

Artifact: `11211877714`

Artifact SHA-256:

`f38d7ac419cc7ac4272c813636d42fbf4254834eb3345be4f346c8e136e41a64`

Prior ready triads: **20**

### Confirmatory estimator

Controlled run: `37084215710`

Artifact: `11260320613`

Artifact SHA-256:

`36da955be630c72ca35cfddeaac0f192a1718bcfc3f12d23c091bd3acb2f81c4`

- provider calls: **0**
- production writes: **0**
- combined eligible triads: **69**
- included Sets: **14**
- edges: **207**
- bootstrap draws: **2,000 valid / 0 invalid**

Scarlet and Violet Base Set contributed no complete ready triad and therefore was not included in the fit.

## Confirmatory result

Decision token:

`SET_RELATIVE_TREATMENT_HIERARCHY_V2_NOT_SUPPORTED`

### Shared nuisance coefficients

- scarcity beta: **0.252**
- scarcity beta 95% CI: **-3.889 to 3.888**
- Artist beta / 100 points: **-0.090**
- design rank: **30 / 30**
- design condition number: **636.04**

### Era point estimates

Mega Evolution, 3 Sets:

- Ultra / Double Rare: **4.73x**
- SIR / Double Rare: **46.82x**
- SIR / Ultra Rare: **9.91x**

Scarlet & Violet, 11 Sets:

- Ultra / Double Rare: **2.31x**
- SIR / Double Rare: **28.44x**
- SIR / Ultra Rare: **12.32x**

These are fitted point estimates from an ill-conditioned confirmatory model. They must **not** be interpreted as production Treatment Appeal multipliers.

### Directional robustness

Across individual Sets:

- SIR > Double Rare: **100%**
- SIR > Ultra Rare: **100%**

Both eras also preserved positive SIR contrasts in:

- point estimates
- early temporal refits
- late temporal refits
- every leave-one-triad-out refit

This directional consistency is real evidence of a market hierarchy, but it does not identify a pure Treatment preference magnitude separately from scarcity.

## Failed frozen gates

The decisive failures were:

- `condition_le_30`: **FAIL** — observed **636.04**
- `scarcity_positive_ci`: **FAIL**
- Mega Evolution SIR/Double bootstrap lower bound > 0: **FAIL**
- Mega Evolution SIR/Ultra bootstrap lower bound > 0: **FAIL**
- Scarlet & Violet SIR/Double bootstrap lower bound > 0: **FAIL**
- Scarlet & Violet SIR/Ultra bootstrap lower bound > 0: **FAIL**

All point-sign, temporal-sign, leave-one-out-sign, Set-share, and full-rank gates passed.

## Post-hoc identification diagnostic

This section diagnoses the failed fit. It does not alter the confirmatory decision.

Using the 69 eligible triads and only the frozen design quantities:

1. Construct the 28 Set-specific Treatment-level columns:
   - Ultra Rare level per Set
   - SIR level per Set
   - Double Rare fixed at zero
2. Construct the shared scarcity column exactly as preregistered:
   - `log(p_low / p_high)`
3. Regress only the scarcity design column on the 28 Set-specific Treatment columns.

Result:

- scarcity design-column R²: **0.9988969862**
- residual standard deviation: **0.0237443**
- Treatment-level-only condition number: **2.83**
- Treatment levels + scarcity condition number: **630.85**
- full Treatment + scarcity + Artist condition number: **636.04**

Therefore nearly all identifying variation in scarcity is already encoded by the Set-specific Treatment indicators.

The model is formally full rank because small within-Set probability differences exist, but the independent scarcity variation is too small to estimate a stable shared scarcity coefficient alongside separate Set-level Treatment effects.

This explains the enormous bootstrap uncertainty and the failed scarcity gate.

## Scientific interpretation

The broad V2 expansion did **not** fail because SIR lost its directional premium.

It failed because the current observational design cannot cleanly separate:

- Treatment-associated market premium
from
- Treatment-associated pull scarcity

once Treatment levels are allowed to vary independently by Set.

Adding more triads of the same design is unlikely to fix that identification problem unless they introduce materially greater **within-Set, within-Treatment scarcity variation**.

The very large point multipliers are therefore not suitable for normalization.

## Consequence for Treatment Appeal

The conditional Treatment Appeal normalization preregistration is **not activated**.

Do not:

- convert these fitted multipliers to 0–100 Treatment Appeal,
- add Treatment to Collector Appeal,
- infer a production SIR bonus,
- mutate Overall RIP,
- mutate Rankings,
- publish Set-page Treatment scores.

The current production Collector authority remains unchanged.

## Valid next research directions

Any follow-up is a new study, not a rescue of V2.

The strongest candidate designs are:

1. **Independent scarcity calibration**
   - estimate scarcity-price elasticity from a separate cohort where Treatment is held constant and pull probability varies materially;
   - freeze that scarcity coefficient before returning to cross-Treatment estimation;
   - then estimate Treatment with scarcity beta fixed rather than jointly identified from the same rarity ladder.

2. **Price-independent Treatment preference evidence**
   - direct collector preference, voting, engagement, or other defensible non-price outcome;
   - avoids learning both preference and validation from the same market-price signal.

3. **Common-support natural experiments**
   - matched Treatment comparisons with materially overlapping pull probabilities;
   - must be selected before observing price effects.

A new study must be preregistered independently. V2 remains a negative confirmatory result.

## Production boundary

Research only.

- canonical pricing writes: **ZERO**
- Collector Appeal mutation: **NONE**
- Overall RIP mutation: **NONE**
- Rankings mutation: **NONE**
- Set-page publication: **NONE**
