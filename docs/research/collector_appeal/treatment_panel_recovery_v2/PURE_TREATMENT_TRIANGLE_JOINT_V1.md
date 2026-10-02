# PURE_TREATMENT Joint Triangle V1

Decision token: `PURE_TREATMENT_TRIANGLE_PARTIAL_ORDER_SUPPORTED`

## Joint transitive model

The model fits all three treatment relationships simultaneously with one shared scarcity coefficient and one Artist control:

`log(price_high / price_low) = treatment_high - treatment_low + beta_scarcity * log(p_low / p_high) + beta_artist * artist_delta`

Double Rare is the reference treatment. Subject Appeal and Playability cancel exactly within every matched Set×subject comparison.

The input graph contains **24 treatment edges across 9 independent Set×subject clusters**.

## Coherent treatment relationships

- **Ultra Rare / Double Rare: 0.69x**
  - 95% cluster-bootstrap: **0.39x–1.20x**
  - **UNRESOLVED** because the interval crosses parity.
- **SIR / Double Rare: 2.66x**
  - 95% cluster-bootstrap: **1.43x–4.86x**
  - **SUPPORTED**
- **SIR / Ultra Rare: 3.88x**
  - 95% cluster-bootstrap: **2.73x–5.13x**
  - **SUPPORTED**

Shared scarcity beta: **1.573**.

## Temporal stability

Early:
- UR / DR: **0.67x**
- SIR / DR: **2.55x**
- SIR / UR: **3.83x**

Late:
- UR / DR: **0.71x**
- SIR / DR: **2.78x**
- SIR / UR: **3.92x**

## Decision

The currently supported partial order is:

**SIR > {Double Rare, Ultra Rare}**

Do **not** force an order between Double Rare and Ultra Rare yet.

This joint result supersedes attempts to compare the intercepts from separately fitted treatment-family models, because those models estimated different scarcity nuisance slopes and produced a non-transitive apparent ordering.

## Next research requirement

Expand direct Double Rare↔Ultra Rare matched coverage across additional Sets/subjects and refit the same joint model. Mega Hyper Rare↔SIR and Illustration Rare↔SIR remain Set-local/diagnostic because the frozen full-catalog audit does not currently provide the required multi-Set era support for those families.

Production writes: **ZERO**.
