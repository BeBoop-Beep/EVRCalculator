# inDex Fair Value — F2 candidate model study

Status: `INDEX_FAIR_VALUE_F2_MODEL_NOT_SUPPORTED`. Research only; no model was frozen or published.

## Data and validation

The F1 dataset reproduced exactly: 4,349 eligible cards, 22 canonical root sets, two modern eras, fingerprint `0e7b04f1119ce525fbe387b50b523ac580aa7a14c758e5d16487a334969825d9`. Collector V7 run, accepted exact Pull Scarcity runs, Treatment V3, and TCGPlayer Near Mint target bindings remained unchanged.

Outer validation leaves one complete root set out (22 folds). Inner four-fold GroupKFold on the remaining roots selects regularization, spline basis size, or tree complexity. Encoders, scalers, imputers, spline transforms, and Model D peer anchors are fit/rebuilt inside training folds. Fold fingerprint: `527df68db1c424b3d0b93a4b240eca13472d16216fff0b6e5608102e3429944b`.

## Baseline competition

All figures are out of fold; R² below is on log price, while the separate band tests use dollar R².

| Baseline | OOS R² | Spearman | Median $ error | MAE $ | RMSE $ | MdAPE | ±20% | ±30% | ±50% |
|---|---:|---:|---:|---:|---:|---:|---:|---:|---:|
| B0 global median | -0.230 | -0.173 | $0.12 | $8.59 | $48.53 | 81.8% | 18.8% | 25.8% | 34.8% |
| B1 era median | -0.228 | -0.032 | $0.12 | $8.59 | $48.53 | 81.8% | 18.5% | 24.9% | 34.2% |
| B2 nearest-root context median | -0.194 | -0.014 | $0.19 | $8.67 | $48.48 | 90.8% | 14.3% | 20.4% | 28.4% |
| B3 rarity/Treatment median | 0.807 | 0.788 | $0.07 | $6.10 | $42.85 | 34.9% | 32.9% | 46.1% | 65.1% |
| B4 scarcity only | 0.837 | 0.786 | $0.10 | $6.85 | $45.06 | 47.9% | 23.3% | 33.5% | 52.0% |
| B5 Collector only | 0.059 | 0.248 | $0.47 | $8.63 | $48.35 | 143.1% | 2.5% | 4.0% | 8.3% |
| B6 lifecycle/structure | 0.883 | 0.783 | $0.08 | $6.42 | $43.75 | 37.5% | 26.7% | 39.9% | 64.5% |
| B7 current structural reconstruction | 0.915 | 0.852 | $0.07 | $5.85 | $40.49 | 34.1% | 30.2% | 44.5% | 67.2% |

The exact frozen July B7 result remains R² 0.7388, Spearman 0.8352, MAE $18.86, and MdAPE 49.29% on 1,322 hit cards. Its within-tier R² values were all negative. The current-cohort B7 reconstruction also ranks well but does not become reliable within price bands. The failure pattern therefore reproduces conceptually even though the population and permitted Treatment representation changed.

## Candidate models

| Model | OOS R² | Spearman | Median $ error | MAE $ | RMSE $ | MdAPE | ±10% | ±20% | ±30% | ±50% |
|---|---:|---:|---:|---:|---:|---:|---:|---:|---:|---:|
| A regularized log-linear | 0.890 | 0.852 | $0.069 | $6.60 | $40.93 | 35.1% | 15.7% | 30.1% | 44.1% | 64.9% |
| B spline/GAM-style | 0.887 | 0.850 | $0.068 | $6.71 | $39.75 | 34.3% | 15.6% | 30.9% | 44.7% | 66.2% |
| C HistGradientBoosting | **0.922** | **0.861** | $0.070 | **$5.07** | **$34.19** | **32.7%** | **17.4%** | **32.9%** | **46.4%** | **67.6%** |
| D market-conditional | 0.915 | 0.858 | $0.069 | $5.63 | $39.64 | 33.9% | 15.8% | 31.4% | 45.4% | 66.5% |

Model B's held-out response curves are monotone over the observed quantiles for Collector Appeal, scarcity, and age; scarcity is strongly nonlinear. Model C's leading non-causal permutation signals are scarcity, standard-frame/illustration attributes, the Appeal×scarcity interaction, and supertype. Model C is the best diagnostic model, but not an acceptable product candidate.

Training-fold smearing correction reduced Model C RMSE from $34.19 to $33.62 and dollar bias from -$1.90 to -$1.11, but worsened MdAPE from 32.7% to 34.5% and ±30% accuracy from 46.4% to 44.7%. The conditional-median `exp(log prediction)` remains the evaluated point estimate.

## Primary appraisal failure

Model C has negative dollar R² in every frozen actual-price band:

| Actual band | n | Actual median | Predicted median | Median $ error | MdAPE | Dollar R² | ±20% | ±30% | ±50% |
|---|---:|---:|---:|---:|---:|---:|---:|---:|---:|
| <$5 | 3,509 | $0.16 | $0.15 | $0.05 | 30.1% | -0.89 | 35.7% | 49.8% | 71.2% |
| $5–10 | 257 | $6.90 | $8.56 | $3.62 | 56.4% | -33.70 | 21.0% | 29.6% | 44.0% |
| $10–25 | 292 | $15.17 | $14.90 | $6.25 | 38.8% | -10.49 | 25.0% | 38.0% | 60.3% |
| $25–50 | 145 | $32.72 | $21.22 | $15.29 | 45.6% | -17.77 | 20.7% | 31.7% | 57.9% |
| $50–100 | 83 | $61.36 | $39.55 | $32.23 | 53.9% | -16.32 | 15.7% | 26.5% | 43.4% |
| $100–250 | 36 | $155.89 | $107.93 | $70.79 | 45.1% | -4.89 | 16.7% | 30.6% | 52.8% |
| $250+ | 27 | $366.83 | $194.58 | $230.56 | 52.9% | -1.13 | 18.5% | 22.2% | 44.4% |

This is the same core failure as the old study: strong cross-tier ranking, inadequate within-tier appraisal. The full cohort is dominated by 3,509 sub-$5 cards, making the $0.07 median dollar error misleading for the product question.

## Feature additions

Starting from lifecycle/structure M0, adding Collector Appeal improved log R² by 0.019, MAE by $0.39, MdAPE by 3.29 points, Spearman by 0.067, and ±30% accuracy by 4.55 points. Adding Pull Scarcity improved log R² another 0.009, MAE by $0.29, and RMSE by $1.16, but worsened MdAPE by 0.89 and ±30% by 0.44 point. Adding semantic Treatment attributes worsened log R² by 0.037, MAE by $1.57, and MdAPE by 0.70; Treatment remains structural, not preference. M0 itself shows lifecycle/era/structural categories carry much of the tier separation, but their isolated causal contribution is not identified.

Collector total and its components are redundant enough that the total was not combined automatically with Pokémon/Trainer/Artist/Playability components. VIF and pairwise diagnostics are persisted. Scarcity overlaps strongly with rarity/Treatment but remains independently justified.

## Robustness and calibration

Both modern eras show similar global log performance: Mega Evolution MdAPE 30.5%, log R² 0.933; Scarlet & Violet MdAPE 33.0%, log R² 0.919. This does not imply vintage validity. Worst set by MdAPE is Paradox Rift at 55.9%; worst by dollar MAE is Black Bolt at $14.05. Results are not carried by five easy sets.

Removing the top 1% barely changes MdAPE (32.7% → 32.6%) but reduces RMSE from $34.19 to $11.81; removing the top 5% produces MdAPE 32.0% and RMSE $4.90. Thus ordinary-card relative error persists while a small grail tail dominates dollar RMSE and underprediction. Winsorizing the top 1% yields dollar R² 0.738 but remains diagnostic only.

Calibration deciles reveal good median alignment in some low-price bins, but the top predicted decile has actual/predicted medians near $28.52/$28.05 while MdAPE remains 50.0%, MAE $40.99, and bias -$15.01. Good bin medians conceal large card-level dispersion. Paradox Rift, Paldean Fates/Shrouded Fable, premium chases, and identity-specific iconic demand remain visible omitted-variable regions. Residuals are diagnostics, never opportunities.

Model D was eligible under the F1 contract and used only training-set, leave-one-out comparable-card anchors. It did not beat Model C and also had negative R² in all price bands. It should not redefine the product: its estimand is market-conditional, it increases maintenance/interpretation cost, and it did not solve appraisal.

## Decision

No F3 candidate is nominated. Model C is retained only as the best diagnostic family. It has 23 conceptual raw inputs, deterministic constrained boosting, non-causal permutation attribution, and moderate maintenance cost, but cannot explain why card-specific premiums vary inside broad structural cells. The missing supply/liquidity/grading authorities, identity-specific cultural demand, reprints, and only two-era coverage remain material.

F3 accuracy/range validation must not begin from this result. A future new research phase would need independently justified information or a narrower product scope, preregistered before retesting.

All chart-ready evidence is in the F2 JSON/CSV package; no article was written.
