# Treatment V2 Final Closure

Status: `TREATMENT_V2_CLOSED_IDENTIFICATION_LIMITED`

Date: 2026-10-03

Draft PR: #529

## Final preregistered decision

`SET_RELATIVE_TREATMENT_HIERARCHY_V2_NOT_SUPPORTED`

This is the final decision for the frozen Set-relative Treatment V2 study.

It is not a provider-data failure and not a coverage failure.

## Capture

Successful frozen capture workflow:

- run: `37099170569`
- artifact: `treatment-set-relative-expansion-v2-capture`
- artifact id: `11264629867`
- target fingerprint: `28b344ca8ea95ba8fbc9fa947cdb28a1a3d83408482572084ee83e1cf992563d`
- PkmnPrices credits used: **15,359**
- provider calls: **307**
- production writes: **0**

Coverage:

- 50 / 56 history-ready fresh triads
- 49 / 56 control-eligible fresh triads
- 162 / 168 fresh cards with history
- 8 qualifying Scarlet & Violet Sets
- Pitch Black: 3 eligible triads after frozen Playability control
- coverage gate: **PASS**

Provider identity misses:

All six were Double Rare cards in Scarlet and Violet Base Set:

- Koraidon ex #125
- Miraidon ex #81
- Gardevoir ex #86
- Spidops ex #19
- Great Tusk ex #123
- Iron Treads ex #143

No substitutions were made.

Control exclusion:

- Pitch Black `pokemon:pokemon:609`
- reason: `PLAYABILITY_CONTROL_MISMATCH`
- DR Playability: 58.19568575255092
- UR Playability: 58.19568575255092
- SIR Playability: 0.0

No substitution was made.

## Combined V2 fit

Estimator artifact:

- artifact: `treatment-set-relative-hierarchy-v2`
- artifact id: `11265477918`
- combined ready triads: **69**
- edges: **207**
- included Sets: **14**
- valid bootstrap draws: **2,000 / 2,000**
- production writes: **0**

Directional evidence:

- SIR > Double Rare in **100%** of included Sets
- SIR > Ultra Rare in **100%** of included Sets
- both era point estimates positive
- both early and late era signs positive
- every leave-one-triad-out refit preserves positive SIR/DR and SIR/UR era signs

Identification failures:

- condition number: **636.04** vs frozen maximum **30**
- scarcity beta: **0.2515**
- scarcity beta 95% CI: **-3.8886 to +3.8883**
- Mega SIR/DR bootstrap lower > 0: **FAIL**
- Mega SIR/UR bootstrap lower > 0: **FAIL**
- Scarlet & Violet SIR/DR bootstrap lower > 0: **FAIL**
- Scarlet & Violet SIR/UR bootstrap lower > 0: **FAIL**

The point magnitudes are therefore not accepted as calibrated causal Treatment effects.

## Structural identification diagnosis

A predictor-only reconstruction of the frozen V2 design found:

- scarcity R² from Set×Treatment indicators: **0.9988969862**
- residual scarcity SD: **0.02374**
- Set/Treatment-only condition number: **2.83**
- Set/Treatment + scarcity condition number: **630.85**
- column-normalized condition number: **154.18**
- smallest singular value: **0.03646**

Artist is not the cause:

- condition before Artist: **630.85**
- full condition with Artist: **636.04**

Therefore the dominant problem is structural scarcity/Treatment near-collinearity.

## Full-authority price-blind feasibility scan

Workflow:

- `Treatment Design Geometry Scan V1`
- run: `37099689046`
- artifact: `treatment-design-geometry-v1`
- artifact id: `11265308647`

The scan read:

- price outcomes: **0**
- PkmnPrices calls: **0**
- production writes: **0**

Authority:

- 22 simulation Sets
- 104 raw complete DR/UR/SIR triads
- 104 simulation-resolved triads
- 103 control-eligible triads
- 19 Sets with >=3 eligible triads

All 103 eligible triads:

- scarcity R² from Set×Treatment: **0.9990140713**
- residual scarcity SD: **0.02277**
- Set/Treatment + scarcity condition: **738.28**
- column-normalized condition: **155.37**
- full condition with Artist: **739.25**

Restricting to Sets with more triads does not solve identification:

| Minimum triads / Set | Sets | Triads | Scarcity R² | Cond + scarcity |
|---:|---:|---:|---:|---:|
| 3 | 19 | 103 | 0.999014 | 738.28 |
| 4 | 17 | 97 | 0.999029 | 701.28 |
| 5 | 11 | 73 | 0.998865 | 538.00 |
| 6 | 10 | 68 | 0.998872 | 571.74 |

Conclusion:

**Adding more observations from the same observational design cannot plausibly rescue the Set-relative scarcity decomposition.**

## What V2 does support

V2 supports a strong descriptive market regularity:

`SIR_MARKET_PREMIUM_DIRECTION_CONSISTENT_ACROSS_INCLUDED_SETS`

That is descriptive evidence, not an intrinsic Treatment Appeal score.

A safe human-readable summary is:

> Across the tested modern Sets, matched SIR versions consistently trade above matched Double Rare and Ultra Rare versions. However, because Treatment tier and pull scarcity are almost mechanically linked, the observational market data cannot identify how much of that premium is caused by Treatment itself versus scarcity.

## What V2 does not support

Do not:

- normalize V2 point effects to 0–100 Treatment Appeal,
- run the conditional Treatment Appeal normalization V1,
- shadow V2 Treatment into Collector Appeal,
- remove the scarcity control,
- relax the condition-number gate,
- reinterpret sign consistency as identified magnitude,
- spend additional PkmnPrices credits merely expanding the same DR/UR/SIR design.

## Next research paths

### 1. Intrinsic Collector Treatment

If Treatment is intended to represent intrinsic collector preference, the next evidence should be independent of market price.

Preferred sources:

- controlled pairwise preference voting,
- blind visual comparisons,
- randomized presentation experiments,
- other direct collector-choice evidence.

This path can legitimately remain inside Collector Appeal.

### 2. Market-predictive Treatment

If Treatment is intended to improve price or Fair Value prediction, use the deterministic Treatment taxonomy directly as a market-model feature rather than pretending it is an independently identified intrinsic preference score.

Requirements:

- explicit market-trained semantics,
- scarcity retained as a separate feature,
- regularization or hierarchical structure,
- strict held-out Set and/or forward-time validation,
- no evaluation observation may also train the Treatment effect used to predict it.

This path belongs in Fair Value / market modeling, not the frozen price-blind Collector V7 authority.

### 3. Hierarchical observational Treatment research

A partially pooled Set/era model remains possible as a research model, but it introduces a shrinkage/exchangeability assumption that V2 did not make.

Any such V3 must:

- be preregistered as a new study,
- not be described as a V2 rescue,
- use independent confirmation beyond the outcomes already inspected,
- explicitly test sensitivity to the hierarchical prior/shrinkage structure.

## Collector Appeal boundary

Frozen Collector V7 remains unchanged:

`pokemon_collector_appeal_v7_expanded_price_blind_v1`

Treatment remains excluded.

The conditional normalization preregistration does not activate because its entry token was not achieved.

## Production boundary

- canonical pricing mutation: **NONE**
- Collector Appeal mutation: **NONE**
- Overall RIP mutation: **NONE**
- Rankings mutation: **NONE**
- Set-page publication: **NONE**
