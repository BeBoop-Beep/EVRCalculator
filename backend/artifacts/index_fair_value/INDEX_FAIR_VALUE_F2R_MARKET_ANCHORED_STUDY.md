# inDex Fair Value — F2R Target-Blind Market-Anchored Study

## Decision

`INDEX_FAIR_VALUE_NEEDS_NEW_MARKET_DATA`. Same-set market context improves global accuracy, but does not repair appraisal accuracy inside actual-price bands. Do not proceed to F3 and stop tuning current model families.

## F2 reconstruction and contract

F2 Model D did not implement the deployment-realistic test proposed here. Its outer split withheld an entire root set, so price anchors came only from training root sets. It used training-only era + Treatment + rarity medians, falling back to era + Treatment and then era/global anchors. Training rows used leave-one-out anchoring and the target price was excluded, but other prices from the held-out target root set were unavailable.

F2 structural Model C failed because broad between-band ordering was strong while within-band dollar discrimination was negative in every band. This is a scale/composition success, not reliable card appraisal.

F2R hides one canonical target price and permits prices from other canonical cards in the same root set. It excludes the target canonical ID, target history, target-containing set totals/ranks, and tests removal of same-name related families. Peer ties are deterministically ordered.

## Candidates

Simple comparators were same-set median (C0), same-Treatment median with fallback (C1), five nearest by scarcity (C2), five nearest by Appeal + scarcity (C3), and a robust weighted ten-peer estimate (C4). Calibration candidates used median, trimmed-mean, and shrunk set residual offsets (O1–O3). The small residual model R1 applied a weighted median residual from ten nearest same-set peers. Cross-set/era fallback was already represented by F2 B3/D and was not retuned.

R1 was the strongest diagnostic candidate. It improved over F2 Model C from 32.67% to 27.71% MdAPE, from 46.45% to 53.21% ±30 accuracy, and from $5.07 to $4.68 MAE. It did not meet the frozen gate.

## Accuracy

R1 global results (n=4,349): MAE $4.678; RMSE $33.397; MdAPE 27.706%; log OOS R² 0.9352; dollar R² 0.5113; Spearman 0.8848; ±10/20/30/50 accuracy 20.10% / 38.74% / 53.21% / 73.14%.

| Actual band | n | MdAPE | Dollar R² | ±20 | ±30 | ±50 |
|---|---:|---:|---:|---:|---:|---:|
| <$5 | 3,509 | 24.80% | 0.112 | 42.29% | 57.45% | 76.75% |
| $5–10 | 257 | 43.31% | -34.639 | 22.96% | 36.96% | 54.86% |
| $10–25 | 292 | 40.28% | -9.324 | 29.11% | 37.67% | 61.30% |
| $25–50 | 145 | 44.06% | -13.867 | 21.38% | 33.79% | 56.55% |
| $50–100 | 83 | 42.16% | -5.266 | 16.87% | 32.53% | 63.86% |
| $100–250 | 36 | 46.55% | -5.313 | 25.00% | 33.33% | 58.33% |
| $250+ | 27 | 53.98% | -1.104 | 11.11% | 18.52% | 44.44% |

Only one of seven bands has positive dollar R². Expensive cards remain systematically underpredicted. The all-band failure is unresolved.

## Robustness, gaps, and availability

Dropping the closest peer yielded 28.33% MdAPE; dropping three yielded 29.27%; removing same-name related families yielded 27.91%; random 10%/20% set withholding yielded 28.01%/28.38%. The result is not explained by one near-duplicate, but neither is it accurate enough.

Peer thresholds are: 20+ `HIGH_CONTEXT`, 10–19 `MEDIUM_CONTEXT`, 3–9 `LOW_CONTEXT`, and fewer than 3 `UNAVAILABLE`. The study cohort has enough established peers for every row. New sets with 3–19 eligible priced peers are `EARLY_MARKET_LOW_CONFIDENCE`; fewer than 3 are `COLD_START_UNAVAILABLE`. This limitation cannot be hidden by a structural fallback marketed as equally precise.

Residuals are retained only as **Fair Value gaps** / model-market gaps. Their concentration at high price tiers points to omitted demand, liquidity, condition/supply, grading, and transaction signals; they are not investment opportunities.

The supported interpretation is limited: a target-blind comparable-market appraisal can improve structural estimates, but this implementation is not a publishable Fair Value authority. F3 readiness is false.
