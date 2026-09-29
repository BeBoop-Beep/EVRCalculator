# inDex Fair Value — sold-signal V2 research handoff (2026-09-29)

## Status

**V1 sold-price correction remains DO NOT PROMOTE.** V2 is a leakage-free research harness, not a production pricing change.

No canonical TCGPlayer price, Set Value, Market Explorer value, or public inDex Fair Value authority is changed by this work.

## Critical V1 methodology finding

The V1 pilot generated a feature named `sold_median_to_nm_ratio`:

```
sold_median_to_nm_ratio = sold_median / target_nm_market_price
```

The denominator is the actual Near Mint target being predicted. Because V1 included that ratio in its model feature matrix, its plus-sold comparison contains target leakage.

Consequences:

- V1 baseline metrics remain valid descriptive measurements of the frozen baselines.
- V1 `plusSoldSignals` metrics are **not valid promotion evidence** and must not be used to claim information gain.
- The original no-promotion decision becomes stronger, not weaker: even with access to a target-derived feature, dollar accuracy materially deteriorated.
- The V1 artifact remains preserved as an audit record; it is not silently rewritten.

The recovered V1 market-anchored comparison was:

| Metric | Baseline | V1 plus sold |
| --- | ---: | ---: |
| Spearman | 0.8939 | 0.9017 |
| MdAPE | 45.09% | 44.48% |
| MAE | $60.40 | $83.69 |
| R² dollars | 0.367 | -1.761 |
| Within 30% | 37.62% | 35.15% |

Because the treatment model leaked the target, the apparent Spearman/MdAPE improvement is not interpretable as deployable lift. The MAE/R²/within-30% deterioration remains a strong warning against treating unknown-condition eBay sales as a direct NM valuation correction.

## Current persisted sold-evidence coverage

The production shadow tables currently contain 2,702 PkmnPrices eBay sold rows.

Strict Fair Value eligibility is intentionally much narrower:

- 71 eligible exact-identity, ungraded USD transactions
- 4 distinct canonical cards
- eligible sale dates span 2024-05-31 through 2026-09-27

The dominant rejection reasons are edition or identity ambiguity, especially `EDITION_NOT_EXPLICIT` and `WRONG_EDITION`. This is expected for the current daily collector because it targets unresolved vintage edition gaps rather than the broad Fair Value cohort.

Therefore the current persisted shadow rows are **not sufficient** to reproduce the 207-card Fair Value pilot.

## Recoverability of the original 207-card pilot

The original workflow run was checked for an Actions artifact. No artifact is available for that run, so its generated `sample_features.csv` cannot be recovered from GitHub Actions.

The recovered JSON report is sufficient to preserve the V1 conclusion, but not sufficient to rerun alternative models card-by-card.

A future broad pilot therefore requires one new bounded provider collection. After that single collection, the aggregate CSV is uploaded and can be reanalyzed repeatedly with zero additional provider credits.

## V2 leakage-free contract

`backend/scripts/reanalyze_index_fair_value_sold_signal_v2.py` consumes the aggregate V1 CSV but explicitly prohibits target-derived predictors.

Forbidden model inputs:

- `target_nm_market_price`
- `sold_median_to_nm_ratio`
- any model feature named like a target or NM-target ratio

The target is used only as the supervised response and for evaluation.

Two prespecified feature sets are tested against both the structural and market-anchored baselines.

### Liquidity only

- log(1 + sold count in 30 days)
- log(1 + sold count in 90 days)
- log(1 + sold count in 180 days)
- days since last eligible sale

This asks whether transaction depth and recency explain baseline valuation error without using sold dollars at all.

### Price context

Adds:

- sold MAD relative to sold median
- sold IQR relative to sold median
- sold-price trend fraction
- log(sold median / baseline prediction)

The last feature is deployable because the baseline prediction exists at inference time. It compares two independently available signals; it does not divide by the hidden target.

Evaluation remains grouped by root set with out-of-fold ridge regression and a fixed alpha. The script also emits descriptive-only correlations between baseline error and liquidity/dispersion signals; target-dependent diagnostics are clearly separated from model inputs.

## Condition-normalization research

A title audit across the 2,702 stored sales found 190 rows with an explicit condition hint:

- 39 NM / Near Mint
- 42 LP / Lightly Played
- 29 MP / Moderately Played
- 71 HP / damaged
- remaining condition-labeled rows arise from overlapping/other explicit text patterns

This is enough to justify a future title-condition classifier/calibration study, but not enough to promote a condition bridge today.

In the current strict exact-variant eligible subset, almost all rows are condition-unlabeled and the matching same-date TCGPlayer NM reference needed for a clean sale-to-NM ratio study is absent. No raw eBay sale is therefore reinterpreted as NM.

## Execution workflow

The Fair Value sold-signal workflow is now true manual-only:

- `workflow_dispatch` only
- read-only repository permission
- dispatched SHA is used directly; no hardcoded research branch
- one bounded provider collection produces V1 aggregate features
- the zero-credit V2 reanalysis runs immediately from that CSV
- both V1 and V2 aggregate artifacts are uploaded
- no git push occurs from the workflow

The workflow retains the existing 4,500-credit hard cap and 20 sold rows per sampled card.

GitHub scheduled/manual workflows only dispatch from workflow files present on the repository default branch. Because this research stack is intentionally being kept on `develop` rather than promoted to `main`, the broad 207-card V2 execution is **not run as part of this change**.

## Promotion gates

No sold-data valuation feature should be promoted unless all of the following are satisfied:

1. No target-derived feature is present.
2. Grouped out-of-fold evaluation improves dollar error (MAE and/or MdAPE) and does not materially degrade rank/calibration metrics.
3. Results are not driven by one price band or one set family.
4. Condition uncertainty is modeled explicitly rather than assuming ungraded = NM.
5. A forward-time validation succeeds using only transactions that would have been available at the prediction date.
6. The candidate is compared against the current market-anchored baseline, not only the weaker structural baseline.
7. Provider data remains a Fair Value research signal and does not become Set Value/NM authority without a separate methodology decision.

## Recommended next research sequence

1. Run one fresh bounded broad-cohort collection only after the V2 workflow is intentionally made dispatchable from the default branch.
2. Evaluate liquidity-only before price-context features.
3. If liquidity helps, treat sold data primarily as market-depth / confidence evidence.
4. Separately develop and validate a condition-normalization layer from explicit condition labels and other condition evidence.
5. Only then test a condition-adjusted sold-price feature against the market-anchored Fair Value baseline.
