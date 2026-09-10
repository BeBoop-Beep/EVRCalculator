# Collector Appeal Market-Validation Harness V1

**Status:** `READY_AWAITING_FROZEN_V6`  
**Harness:** `collector_appeal_market_validation_harness_v1`  
**Collector Appeal evaluation performed:** **No**  
**Production scoring/publication changes:** **None**

## 1. Purpose

This harness is the post-freeze market-association study for the corrected Collector Appeal V6 work.

It is intentionally being built **before** V6 is frozen so the research methodology cannot be silently changed after seeing V6's price relationships. The harness can prepare the market/scarcity/control cohort today, but it refuses to evaluate Collector Appeal unless an explicit frozen handoff artifact is supplied.

The question is not "can Collector Appeal reproduce price?" Price is jointly produced by collector demand, scarcity, treatment/prestige, supply, age, and other market structure. The useful question is narrower:

> Does a price-independent Collector Appeal signal carry incremental information about card market price after controlling for actual pull scarcity and structural card/set variables, and is that relationship stable when entire sets are held out?

This is **validation evidence**, not a fitting objective for Collector Appeal.

## 2. What this replaces — and what it does not

The earlier Universal Set Desirability research correctly moved away from a raw set-value Spearman gate. A price-independent collector construct should not be invalidated simply because it does not reproduce total set value. Doing so would pressure the score back toward the market price it was deliberately designed not to consume.

The historical implementation remains untouched at:

- `backend/scripts/build_card_market_amplification_study.py`
- `backend/tests/unit/desirability/test_card_market_amplification_study.py`

That script is preserved for historical reproducibility. The new harness does **not** reuse its old Pokémon-only appeal loader or its precomputed centered terms. In particular, V1 of this new harness fixes a methodological leakage risk in the historical LOSO path: component and scarcity centers are learned on the training sets inside each fold, then applied unchanged to the held-out set.

## 3. Non-negotiable boundaries

The harness enforces these boundaries in code:

1. **No automatic current-model read.** It never reads the current Collector Appeal publication pointer.
2. **No unfinished V6 evaluation.** `freeze.status` must equal `frozen`.
3. **No circular price input.** The handoff must assert `priceInputExcluded=true`.
4. **Pinned identity.** The handoff must contain a model version and formula fingerprint.
5. **Exact card identity only.** Market rows and V6 rows join on canonical card ID; no name/fuzzy matching.
6. **No unproven Pokémon/Trainer pooling.** Any component spanning more than one subject bucket is rejected unless its frozen component manifest explicitly declares `crossBucketComparable=true`.
7. **No market-trained Collector weights.** Regression coefficients and model-lift results are report-only and cannot be copied into Collector Appeal or RIP weights.
8. **No winner selection.** The component-comparison framework runs every preregistered component under one methodology and reports them side-by-side. It does not tune or select V6.
9. **No publication authority.** Nothing in the harness can validate/promote a Collector model run or move a current pointer.

These boundaries matter especially for the current V6 correction work: Pokémon and Trainer evidence must remain separate until the corrected model itself has established a comparable final scale. Functional/playability evidence can be registered as a diagnostic component without making it part of final Collector Appeal.

## 4. Market/control cohort

The extraction path is read-only and lives in:

`backend/scripts/research_collector_appeal_market_validation.py`

### 4.1 Card cohort

The candidate card universe is restricted to canonical rows with:

- `catalog_role = main`
- `opening_eligible = true`
- `canonical_review_status = approved`
- supertype Pokémon or Trainer
- positive latest canonical market price
- a modeled rarity-keyed specific-card pull probability
- a parseable set release date

Energy is excluded from this V1 market study because it is not a modeled Collector subject in the current Collector work.

### 4.2 Outcome

Primary outcome:

`log_price = ln(latest canonical card market price)`

Using log price reduces domination by the extreme right tail while preserving the economically meaningful ordering of positive prices.

### 4.3 Scarcity

`pull_scarcity = -log10(P(specific card in one pack))`

Pull probability is read through the shared Collector Appeal pull-model loader rather than reinterpreted in this harness. This keeps the scarcity control aligned with the application's existing rarity-keyed pack-model contract.

### 4.4 Structural controls

V1 controls are:

- log release age
- secret-number flag
- promo subtype flag
- major mechanic-card flag (`ex`, `GX`, `V`, `VMAX`, `VSTAR`, `Mega`)
- Stage 2 flag
- Trainer supertype flag

Treatment/prestige is **not** collapsed into scarcity. It is entered separately in the final nested model so the study can distinguish modeled pull difficulty from a categorical collectible/treatment designation.

## 5. Frozen V6 input contract

The harness expects an explicit JSON artifact with:

```json
{
  "contractVersion": "collector_appeal_market_validation_input_v1",
  "freeze": {
    "status": "frozen",
    "modelVersion": "<corrected-v6-model-version>",
    "formulaFingerprint": "<sha/fingerprint>",
    "asOfDate": "YYYY-MM-DD",
    "priceInputExcluded": true
  },
  "components": [
    {
      "name": "pokemon_subject",
      "scoreKey": "pokemon_subject",
      "subjectTypes": ["pokemon"],
      "role": "candidate",
      "interactionWithScarcity": true
    },
    {
      "name": "trainer_subject",
      "scoreKey": "trainer_subject",
      "subjectTypes": ["trainer"],
      "role": "candidate",
      "interactionWithScarcity": true
    },
    {
      "name": "final_card_appeal",
      "scoreKey": "final_card_appeal",
      "subjectTypes": ["pokemon", "trainer"],
      "role": "final",
      "crossBucketComparable": true,
      "interactionWithScarcity": true
    }
  ],
  "rows": [
    {
      "canonical_card_id": "<uuid>",
      "subject_type": "pokemon",
      "subject_cluster_key": "<stable-subject-id>",
      "scores": {
        "pokemon_subject": 82.1,
        "final_card_appeal": 84.0
      }
    }
  ]
}
```

The example above does **not** define the corrected V6 formula. It only demonstrates the transport contract. The actual list of components, scores, and cross-bucket certification must come from the frozen corrected model.

For repeated-subject inference, `subject_cluster_key` should be a stable subject identity rather than a display label when available. If it is present for all rows in a component sample, the fixed-effects inference reports two-way set/subject clustered standard errors in addition to the primary set-clustered standard errors.

## 6. Statistical design

The pure engine is:

`backend/research/collector_appeal_market_validation/stats.py`

Every component is evaluated on its declared subject bucket(s) only.

### 6.1 Descriptive relationships

For each component:

- Spearman(component, log price)
- Pearson(component, log price)
- same relationships by era

These are descriptive only. No absolute raw-correlation threshold is a validity gate.

### 6.2 Nested models

For a registered component `C`:

- **M0 — controls only**
- **M1 — M0 + C**
- **M2 — M0 + pull scarcity**
- **M3 — M0 + C + pull scarcity**
- **M4 — M3 + C × pull scarcity**
- **M5 — M4 + treatment prestige**

A component may explicitly disable the scarcity interaction if its preregistered role does not support that question; in that case the final treatment model is the additive successor to M3.

The central incremental test is **M3 vs M2**: does Collector Appeal contribute beyond scarcity and structural controls?

Secondary questions are:

- M1 vs M0 — component beyond controls
- M2 vs M0 — scarcity beyond controls
- M3 vs M1 — scarcity beyond component
- M4 vs M3 — amplification/interaction beyond additive component + scarcity
- M5 vs M4 — treatment prestige beyond actual pull odds and interaction

## 7. Whole-set-out validation

Random card splits are prohibited. Cards from one set share release timing, supply conditions, card design, rarity structure, and often the same pull model. Randomly splitting cards would leak that set-specific structure into both train and test.

The harness therefore uses **leave-one-whole-set-out cross-validation**:

1. hold out one complete set;
2. learn component/scarcity centering from training sets only;
3. fit the model on all remaining sets;
4. predict every card in the held-out set;
5. repeat until every set has been held out exactly once.

The predictive CV model includes training-known era indicators because a held-out set has no estimable set fixed-effect intercept.

The aggregate out-of-sample metrics are:

- MAE on log price
- RMSE on log price
- out-of-sample R²
- Spearman(predicted log price, actual log price)

All four are retained because they answer different questions. R² can legitimately be negative out of sample.

## 8. Incremental model comparison

Every nested comparison reports:

- absolute MAE reduction
- percent MAE reduction
- absolute RMSE reduction
- percent RMSE reduction
- R² gain
- Spearman gain

The comparisons use the exact same held-out card predictions for both nested models. A mismatch in prediction identity is an error rather than being silently intersected into a different sample.

When bootstrapping is enabled, incremental uncertainty is estimated by resampling **held-out sets as clusters**, preserving each set's full prediction block.

## 9. Fixed-effects inference and uncertainty

In-sample coefficient diagnostics use set fixed effects by within-set demeaning. Set-constant controls are therefore correctly absorbed/dropped in the FE fit instead of receiving spurious coefficients.

Primary robust inference uses standard errors clustered by set.

When a stable subject cluster key is available on every modeled row, the harness additionally reports two-way set/subject cluster-robust standard errors to account for repeated subject identities across printings/sets.

Optional coefficient uncertainty uses a whole-set cluster bootstrap. A duplicated sampled set is relabeled as a separate bootstrap cluster; individual cards are never independently resampled.

## 10. Era diagnostics

The pooled model remains the primary analysis. Era-specific component-over-scarcity diagnostics are only evaluated when an era has at least:

- 4 distinct sets; and
- 200 modeled cards.

Smaller eras are reported as ineligible instead of pretending a leave-whole-set-out result is stable.

## 11. Component-comparison framework

`compare_components()` runs each frozen, preregistered component under the exact same statistical protocol and produces a compact comparison table containing:

- sample size / set count
- raw Spearman vs log price
- M3 out-of-sample MAE / RMSE / R² / Spearman
- incremental M3-vs-M2 MAE reduction
- incremental RMSE reduction
- incremental R² gain
- incremental Spearman gain

It does **not** rank components, pick a winner, change a component formula, search weights, or rewrite the frozen V6 artifact.

That separation is deliberate: market validation should tell us what information the construct contains, not retroactively define the construct by whichever version best fits today's market prices.

## 12. Execution

### Prepare/reuse market cohort only — safe before V6 freeze

```bash
python -m backend.scripts.research_collector_appeal_market_validation
```

With no `--frozen-appeal-artifact`, the report status is:

`READY_AWAITING_FROZEN_V6`

and `evaluationPerformed=false`.

A previously extracted, fingerprinted market cohort can be reused exactly:

```bash
python -m backend.scripts.research_collector_appeal_market_validation \
  --market-cohort-input backend/artifacts/collector_appeal_market_validation_market_cohort_v1.json
```

### After corrected V6 freezes

```bash
python -m backend.scripts.research_collector_appeal_market_validation \
  --market-cohort-input backend/artifacts/collector_appeal_market_validation_market_cohort_v1.json \
  --frozen-appeal-artifact <explicit-frozen-v6-validation-input.json> \
  --bootstrap-draws 400
```

Supplying a non-frozen artifact, a price-contaminated artifact, or an uncertified mixed Pokémon/Trainer component fails closed.

## 13. Tests

New regression coverage:

- `backend/tests/unit/research/test_collector_appeal_market_validation.py`
- `backend/tests/unit/research/test_collector_appeal_market_validation_script.py`

The tests pin:

- M0–M5 nesting
- one complete held-out fold per set
- no global-centering leakage into a held-out set
- MAE/RMSE/R²/Spearman incremental reporting
- log-price descriptive relationships
- two-way set/subject robust inference when subject identities are available
- cross-bucket pooling failure without explicit comparability freeze
- exact canonical-card joins
- frozen/price-independent handoff requirements
- the default no-evaluation waiting state
- absence of winner-selection behavior from the component comparison report

Synthetic tests validate the machinery only. They are **not evidence that corrected V6 has passed market validation**.

## 14. What happens next

After the corrected V6 model is genuinely frozen:

1. export its card-level validation handoff using `collector_appeal_market_validation_input_v1`;
2. keep Pokémon and Trainer components separate unless the frozen model itself certifies their common scale;
3. run the harness against the pinned market cohort;
4. inspect pooled + era results, incremental lift, uncertainty, and component comparisons;
5. document the findings without tuning V6 to improve them;
6. only then decide what the market-validation evidence means for the broader Collector Appeal research record.

No step in this harness authorizes publication, RIP-weight changes, or promotion of a Collector Appeal model run.
