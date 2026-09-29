# Collector Cross-Domain Calibration V1 — Independent Temporal Validation Preregistration

**Status:** FROZEN BEFORE TEMPORAL OUTCOME READ  
**Research branch:** `research/collector-cross-domain-temporal-v1-20260929`  
**Parent Phase 1 SHA:** `012e38b1e9a85491ba2ba72b746f8baead6112ea`  
**Production impact:** NONE

## 1. Question

Does the preregistered `ANCHOR25` Trainer-to-Pokémon cross-domain calibration remain non-regressive and preserve/improve same-context market alignment on independent post-2026-09-11 price states?

This is a validation of one already-selected shadow candidate. It is not a new candidate search.

## 2. Frozen model authority

Collector V7 remains the control:

- Model version: `pokemon_collector_appeal_v7_expanded_price_blind_v1`
- Model run: `e282f26e-2136-4105-b0a3-f0974c4d9d70`
- Formula fingerprint: `06f5660047b9b8a4d7349d04b79547b1314c2be3720c245ba8780890db1c114b`
- Model fingerprint: `3b781f4ec01ef8c74c77b34d2b91e9a90231d2feccf2ee41411de64606378c9d`
- Card fingerprint: `7dbe5e989c6eb7bcb9d4684707f9c239ab1ca701fc429a7a0605657d79f2ab90`
- Set fingerprint: `744f088e7e1e33e5f8b40aca707b8f7e0d93bf7def8308b860da0277257a4b52`

## 3. Candidate is fixed

Only `ANCHOR25` is evaluated.

```
candidate_subject =
    0.75 * original_trainer_subject
  + 0.25 * trainer_pokemon_anchor_score
```

Pokémon subject scores are unchanged. Playability and Artist mechanics remain frozen exactly as in Phase 1. No ANCHOR50, ANCHOR75, ANCHOR100, alternate transform, weight, threshold, or fallback may be selected after viewing temporal results.

## 4. Temporal folds are fixed

Five post-baseline market dates are used with no replacement dates:

1. 2026-09-14
2. 2026-09-17
3. 2026-09-20
4. 2026-09-23
5. 2026-09-26

These dates were frozen before querying their calibration performance.

## 5. Cohort is fixed

The structural cohort is the exact Phase 1 cohort:

- Candidate cards: 4,355
- Modeled rows: 4,331
- Sets: 22
- Structural exclusions: 24 `no_modeled_pull_probability` rows
- Excluded rows are the known ACE SPEC structural exclusions.

Membership is price-independent and cannot change by fold. Price availability cannot be used to choose cards, Sets, dates, or the candidate.

## 6. Outcome authority

For every fold, card market prices are read from:

`get_pokemon_market_root_standard_card_prices_as_of_v2`

with the exact root Set and fold date.

Price is an outcome only. It is forbidden from candidate construction, Trainer-to-Pokémon mapping, normalization, cohort membership, or candidate selection.

A fold is data-valid only when all 4,331 modeled rows have an authoritative price and all 22 Sets remain represented. An unavailable fold is a failed fold for the 4-of-5 decision; it is not replaced.

## 7. Metrics

CONTROL and ANCHOR25 are evaluated on the same rows with the same Phase 1 implementations:

- weighted mean within-Set Spearman rho
- median within-Set Spearman rho
- controlled grouped leave-Set-out OOS R²
- held-out Spearman
- OOS MAE and RMSE
- matched Pokémon/Trainer directional concordance
- matched-pair score-gap diagnostics

The controlled model and pair-matching rules are unchanged from Phase 1.

## 8. Fold gate

A data-valid fold passes only if all of the following ANCHOR25 minus CONTROL deltas hold:

- weighted within-Set rho >= -0.005
- controlled OOS R² >= -0.002
- held-out Spearman >= -0.010
- matched-pair directional concordance >= 0.000

These are guardrails, not optimization targets. No metric may be removed after results are observed.

## 9. Temporal decision gate

The temporal validation decision is:

- `ANCHOR25_TEMPORAL_VALIDATION_PASS` if at least 4 of the 5 fixed folds pass the complete fold gate.
- `ANCHOR25_TEMPORAL_VALIDATION_FAIL` if fewer than 4 folds pass and at least 4 folds are data-valid.
- `ANCHOR25_TEMPORAL_AUTHORITY_INSUFFICIENT` if fewer than 4 folds are data-valid.

No alternative Anchor candidate is considered if ANCHOR25 fails.

## 10. Bootstrap

Each data-valid fold uses 1,000 deterministic whole-Set bootstrap draws. The base seed is `20260929`; fold seeds are deterministically derived from the base seed and the fixed market date.

Bootstrap intervals are diagnostics and regression evidence. They do not replace the explicit 4-of-5 gate above.

## 11. Structural invariants

The run must also verify:

- frozen V7 artifact and fingerprints still validate
- Pokémon scores are exactly unchanged
- Trainer within-domain Spearman for ANCHOR25 remains >= 0.995
- control replay mechanics are unchanged
- no database writes occur
- no current/published Collector authority is changed
- no Overall RIP output is published or mutated

A structural-invariant failure invalidates the temporal run.

## 12. Consequence of a pass

A temporal PASS supports the next **research-only** step: construct a Collector V8 shadow implementation using the already-fixed ANCHOR25 calibration, then evaluate Set-level and hypothetical Overall RIP impact.

A PASS is not production promotion. Collector V7 remains current until a separate promotion-readiness review is completed.

A FAIL or INSUFFICIENT result stops ANCHOR25 promotion work; it does not trigger a search for a stronger Anchor on the same temporal outcomes.
