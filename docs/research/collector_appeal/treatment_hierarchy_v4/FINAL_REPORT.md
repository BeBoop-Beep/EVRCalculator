# Treatment Hierarchy V4 — Set-Local Scarcity Identifiability

Decision: `TREATMENT_HIERARCHY_V4_DIAGNOSTIC_ONLY`

Workflow run: `36931188352`
Artifact: `11195419796`
Artifact digest: `sha256:5a24c23bf6cf3786c0cac94641682eb115d8e0bbb5e619030ad9f2c71a35feec`

## Question

V4 tests the user's intended "within Set first" structure directly by estimating one Exact Pull Scarcity slope independently inside each Set/family instead of sharing one global scarcity coefficient.

## Identifiability result

Every eligible Set/family is mathematically full rank:

| Set / family | Ready identities | PURE rank / columns | Condition number |
|---|---:|---:|---:|
| Paldea Evolved / IR↔Uncommon | 5 | 2 / 2 | 590.39 |
| Paradox Rift / DR↔UR | 5 | 2 / 2 | 172.28 |
| SV151 / DR↔SIR↔UR | 3 | 3 / 3 | 41.80 |
| Shrouded Fable / Common↔IR | 4 | 2 / 2 | 898.32 |
| Surging Sparks / DR↔SIR↔UR | 2 | 3 / 3 | 176.02 |
| Surging Sparks / DR↔UR | 4 | 2 / 2 | 131.24 |
| White Flare / Common↔IR | 5 | 2 / 2 | 581.45 |

Three treatment families therefore have at least two independently identifiable Sets:
- Common ↔ Illustration Rare
- Double Rare ↔ Ultra Rare
- Double Rare ↔ SIR ↔ Ultra Rare

Global early/late coefficient Spearman: **1.0**.

## Support result

Despite full rank and perfect temporal ordering, **0 Set/family groups pass the preregistered stability/support gates**.

The local model is weakly identified rather than rank-deficient. Representative local PURE results show extremely large coefficient and influence swings:

- Paldea Evolved IR: PURE +43.4792 log; max leave-identity drift 134.406
- Paradox Rift UR: PURE +11.132; max drift 7.052
- SV151 SIR: PURE +1.1798; max drift 3.957
- SV151 UR: PURE -1.6301; max drift 4.959
- Shrouded Fable IR: PURE -72.7058; max drift 192.42
- Surging Sparks DR↔UR UR: PURE +15.3404; max drift 11.009
- White Flare IR: PURE -20.3373; max drift 13.011

Local scarcity slopes also change sharply by Set/family:
- Paldea Evolved: -12.7832
- Paradox Rift: -7.7859
- SV151: +3.615
- Shrouded Fable: +26.0917
- Surging Sparks triple: -1.3173
- Surging Sparks DR↔UR: -13.2603
- White Flare: +5.7288

These values are diagnostic signs of weak separation, not candidate production coefficients.

## Interpretation

V4 rules out the hypothesis that V3 failed merely because a global scarcity coefficient coupled unrelated Sets. Treatment and Exact Pull Scarcity are technically separable in the local design, but with the current 2–5 identity samples their independent coefficients remain far too influence-sensitive for production scoring.

A final full-depth evidence test is justified because the frozen Round-23 universe contains up to 37 matched identities in some Set/family groups. If that complete available universe remains unstable, continued tuning of this same price-regression approach is not justified.

## Safety

Production writes: 0. Provider calls: 0. Collector Appeal mutation: none. Overall RIP mutation: none.
