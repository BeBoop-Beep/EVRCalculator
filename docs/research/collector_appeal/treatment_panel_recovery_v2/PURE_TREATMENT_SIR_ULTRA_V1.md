# PURE_TREATMENT SIR vs Ultra Rare V1 — Pilot Result

Decision token: `PURE_TREATMENT_SIR_ULTRA_PILOT_ESTIMATED`

## Main result

- Treatment Package premium after Artist control, before scarcity control: **11.43x**
- Package bootstrap 95% interval: **6.60x–19.35x**
- Scarcity-controlled PURE_TREATMENT premium: **4.86x**
- Whole-pair bootstrap 95% interval: **1.96x–7.19x**
- Scarcity coefficient: **1.229**
- Scarcity-associated share of the Artist-controlled package log-premium: **35.1%**

## Temporal stability

- Early half: **4.84x**
- Late half: **4.88x**
- Same positive sign: **true**

## Set-level adjusted effects

| Era | Set | Identities | Pure SIR multiplier |
|---|---|---:|---:|
| Mega Evolution | Chaos Rising | 2 | 4.97x |
| Mega Evolution | Mega Evolution | 2 | 5.06x |
| Scarlet and Violet | Paldea Evolved | 2 | 5.70x |
| Scarlet and Violet | Paradox Rift | 2 | 3.90x |

## Era-level adjusted effects

- **Mega Evolution**: 5.02x across 4 identities
- **Scarlet and Violet**: 4.71x across 4 identities

## Influence robustness

- Leave-one-identity-out global multiplier range: **4.02x–5.78x**
- All eight adjusted matched-pair effects positive: **true**
- Design rank: **3**; condition number: **5.11**

## Completed-sale secondary check

The existing exact-attribution ungraded sold ledger has both sides for two of the eight pilot pairs. In both cases SIR was above Ultra Rare on **100%** of shared sale dates: Greninja (49 shared days; ~17.0x geometric sold-price ratio) and Tinkaton (45 shared days; ~5.22x). This remains diagnostic because the sold rows do not carry the frozen Near-Mint condition authority used by the primary estimator.

## Interpretation

This pilot supports a large SIR treatment/presentation signal beyond modeled pull scarcity alone and validates the Set → Era → Cross-Era research architecture for this treatment family. It does not justify a universal production SIR score; additional treatment families must be estimated before a cross-family Treatment Appeal authority is constructed.

## Scope and limitations

- Minimal preregistered gate-clearing pilot: 8 matched identities / 4 Sets / 2 eras.
- Scarcity and Artist nuisance coefficients are estimated from only 8 independent matched pairs.
- Artist's bootstrap interval includes zero; the Treatment intercept is materially more stable than the nuisance coefficient.
- The residual signal can include presentation differences intrinsic to SIRs (illustration composition, texture, visual execution), which are conceptually part of Treatment, plus any remaining unmeasured card-specific effects.
- Primary outcome is historical exact-date Near-Mint market/listing price evidence, not completed-sale price.
- Research only; this is not yet a production Treatment score.

Production writes: **ZERO**.
