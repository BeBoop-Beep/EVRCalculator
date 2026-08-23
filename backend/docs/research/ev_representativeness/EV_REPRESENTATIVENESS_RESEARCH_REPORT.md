# EV Representativeness Research Report

Market date: **2026-08-22**  
Method: **ev_representativeness_v1**  
Set-level effective sample size: **22**

## 1. Executive Summary

Across 22 modeled sets, median openings capture between 20.9% and 54.9% of EV. EV is therefore a long-run mean, not a description of a typical small opening. The cohort exhibits material variation in both tail concentration and the number of packs needed for finite-sample averages to approach EV.

## 2. Research Question

How representative is EV of a real opener's finite-sample experience, and how many packs are required before EV becomes a reasonably representative description?

## 3. Methodology

Tier A reads each exact, SHA-256-verified one-million-pack float64 artifact. Tier B is a separate deterministic, seeded reconstruction used only for latent card identity, paired ablations, and price shocks. Tier B attribution is accepted only after mean and quantile reconciliation against Tier A. Sessions bootstrap independent packs with replacement from Tier A, using common random numbers across the N grid. Probability rows report Wilson 95% intervals. The stored first crossing is the coarse-grid first crossing and remains a noisy diagnostic; stable horizons may be refined between coarse points and require a Wilson lower bound above the target across a validation band plus an independent 250,000-session confirmation. CLT estimates are comparisons, never substitutes for empirical horizons.

## 4. Dataset

| Market date | Sets | Source outcomes | Product rows | Pack counts | Tier B reconciled |
|---|---|---|---|---|---|
| 2026-08-22 | 22 | 22,000,000 | 137 | 1, 6, 9, 11, 18, 36 | 22/22 |

Product rows are descriptive only. Products from the same set share an underlying pack distribution, so they are not treated as independent observations.

## 5. EV vs Typical Opening

| Set | EV | P50 | Typical Capture | EV−P50 | Gap / cost |
|---|---|---|---|---|---|
| journeyTogether | 3.44 | 1.89 | 54.9% | 1.55 | 24.3% |
| perfectOrder | 2.91 | 1.39 | 47.7% | 1.52 | 28.0% |
| surgingSparks | 3.56 | 1.63 | 45.8% | 1.93 | 24.8% |
| megaEvolution | 3.80 | 1.70 | 44.8% | 2.10 | 25.2% |
| pitchBlack | 3.80 | 1.67 | 44.0% | 2.13 | 35.7% |
| chaosRising | 2.84 | 1.24 | 43.7% | 1.60 | 28.9% |
| scarletAndVioletBase | 4.03 | 1.74 | 43.2% | 2.29 | 25.0% |
| twilightMasquerade | 4.71 | 1.98 | 42.0% | 2.73 | 30.8% |
| obsidianFlames | 4.37 | 1.83 | 41.9% | 2.54 | 19.4% |
| destinedRivals | 4.47 | 1.86 | 41.6% | 2.61 | 27.7% |
| stellarCrown | 4.48 | 1.78 | 39.7% | 2.70 | 25.5% |
| paradoxRift | 3.96 | 1.57 | 39.6% | 2.39 | 28.5% |
| ascendedHeroes | 9.06 | 3.27 | 36.1% | 5.79 | 41.7% |
| temporalForces | 5.51 | 1.94 | 35.2% | 3.57 | 31.4% |
| phantasmalFlames | 4.55 | 1.54 | 33.8% | 3.01 | 25.8% |
| shroudedFable | 5.97 | 2.01 | 33.7% | 3.96 | 26.8% |
| whiteFlare | 5.61 | 1.74 | 31.0% | 3.87 | 28.8% |
| blackBolt | 6.04 | 1.80 | 29.8% | 4.24 | 29.1% |
| paldeaEvolved | 5.77 | 1.69 | 29.3% | 4.08 | 25.4% |
| scarletAndViolet151 | 12.82 | 3.73 | 29.1% | 9.09 | 31.4% |
| paldeanFates | 7.62 | 1.76 | 23.1% | 5.86 | 25.4% |
| prismaticEvolutions | 8.53 | 1.78 | 20.9% | 6.75 | 44.7% |

## 6. Outcome Concentration

| Set | Top 10% share | Top 5% share | Top 1% share | Top 1% mean |
|---|---|---|---|---|
| prismaticEvolutions | 80.0% | 76.1% | 64.1% | 547.24 |
| phantasmalFlames | 65.4% | 58.8% | 45.9% | 208.94 |
| paldeanFates | 68.8% | 60.6% | 44.8% | 341.35 |
| ascendedHeroes | 65.0% | 59.6% | 44.3% | 400.95 |
| blackBolt | 68.5% | 54.8% | 32.5% | 196.65 |
| destinedRivals | 60.1% | 51.3% | 31.3% | 139.79 |
| chaosRising | 54.4% | 45.2% | 30.4% | 86.30 |
| whiteFlare | 65.7% | 51.4% | 29.1% | 163.06 |
| pitchBlack | 54.5% | 44.9% | 28.8% | 109.30 |
| megaEvolution | 55.6% | 46.4% | 28.2% | 106.87 |
| paldeaEvolved | 67.0% | 52.8% | 25.7% | 148.15 |
| surgingSparks | 54.3% | 43.4% | 25.5% | 90.91 |
| perfectOrder | 52.7% | 43.4% | 25.1% | 73.21 |
| stellarCrown | 56.9% | 47.1% | 25.1% | 112.43 |
| twilightMasquerade | 54.1% | 43.4% | 24.8% | 116.94 |
| scarletAndViolet151 | 65.8% | 48.4% | 20.1% | 257.90 |
| obsidianFlames | 56.3% | 43.9% | 18.3% | 79.91 |
| paradoxRift | 59.4% | 45.2% | 17.5% | 69.42 |
| journeyTogether | 45.7% | 36.1% | 16.7% | 57.35 |
| scarletAndVioletBase | 54.3% | 40.7% | 14.6% | 58.96 |
| temporalForces | 58.2% | 42.8% | 14.3% | 78.65 |
| shroudedFable | 59.8% | 40.4% | 11.7% | 69.84 |

All tail shares use exact rank mass, including ties: k = max(1, ceil(nq)).

## 7. Card Concentration

| Set | Top card | Top 5 | Top 10 | HHI | Effective cards |
|---|---|---|---|---|---|
| phantasmalFlames | 37.4% | 51.5% | 57.9% | 0.1476 | 6.8 |
| paldeanFates | 27.6% | 46.2% | 52.5% | 0.0892 | 11.2 |
| prismaticEvolutions | 22.5% | 45.4% | 60.9% | 0.0707 | 14.1 |
| stellarCrown | 15.4% | 38.0% | 46.3% | 0.0484 | 20.6 |
| scarletAndViolet151 | 13.3% | 30.7% | 46.3% | 0.0345 | 29.0 |
| obsidianFlames | 13.4% | 33.8% | 45.3% | 0.0333 | 30.0 |
| chaosRising | 13.7% | 30.3% | 41.6% | 0.0317 | 31.6 |
| paldeaEvolved | 14.2% | 26.5% | 36.9% | 0.0291 | 34.4 |
| pitchBlack | 12.6% | 28.3% | 39.2% | 0.0278 | 36.0 |
| ascendedHeroes | 9.1% | 31.1% | 44.3% | 0.0276 | 36.2 |
| perfectOrder | 9.2% | 27.2% | 38.4% | 0.0231 | 43.2 |
| shroudedFable | 7.0% | 25.3% | 39.0% | 0.0229 | 43.7 |
| destinedRivals | 10.6% | 26.9% | 37.1% | 0.0226 | 44.3 |
| twilightMasquerade | 8.6% | 26.3% | 34.2% | 0.0204 | 49.0 |
| blackBolt | 7.2% | 25.6% | 31.6% | 0.0183 | 54.7 |
| surgingSparks | 8.6% | 23.2% | 31.8% | 0.0171 | 58.6 |
| temporalForces | 6.2% | 21.0% | 33.8% | 0.0169 | 59.1 |
| megaEvolution | 5.1% | 20.2% | 31.8% | 0.0148 | 67.7 |
| journeyTogether | 5.9% | 21.1% | 32.1% | 0.0145 | 69.2 |
| whiteFlare | 6.7% | 20.5% | 27.7% | 0.0144 | 69.7 |
| scarletAndVioletBase | 5.7% | 20.4% | 30.7% | 0.0140 | 71.6 |
| paradoxRift | 6.8% | 17.9% | 27.0% | 0.0127 | 78.7 |

Only reconciled Tier B rows are interpreted as authoritative card attribution.

## 8. Rarity Structure

Exact rarity EV contributions come from same-run `simulation_pull_summary` and reconcile to Tier A EV. Collective hit frequencies use the canonical pack-state model; they are not sums of marginal probabilities. Rarity shares and IR/SIR/premium accessibility are included in the set CSV and hypothesis tests.

## 9. Finite-Sample EV Realization

| Set | N=1 | N=6 | N=9 | N=11 | N=18 | N=36 | N=50 | N=100 | N=250 | N=1000 |
|---|---|---|---|---|---|---|---|---|---|---|
| ascendedHeroes | 14.2% | 17.7% | 23.3% | 25.7% | 27.9% | 31.5% | 34.8% | 45.2% | 59.9% | 84.2% |
| blackBolt | 13.4% | 34.1% | 37.1% | 37.5% | 41.3% | 44.8% | 47.3% | 54.7% | 70.3% | 93.1% |
| chaosRising | 19.3% | 31.9% | 33.7% | 34.0% | 36.8% | 44.4% | 48.8% | 58.7% | 75.0% | 96.7% |
| destinedRivals | 14.0% | 29.1% | 31.7% | 34.6% | 40.3% | 47.1% | 50.7% | 60.0% | 74.7% | 95.1% |
| journeyTogether | 23.2% | 40.5% | 46.0% | 49.0% | 58.2% | 69.4% | 74.8% | 86.0% | 97.0% | 100.0% |
| megaEvolution | 17.8% | 31.5% | 36.4% | 38.8% | 43.5% | 48.8% | 52.9% | 63.7% | 80.4% | 98.1% |
| obsidianFlames | 17.0% | 38.8% | 44.7% | 47.2% | 54.1% | 63.8% | 68.7% | 79.5% | 92.8% | 99.9% |
| paldeaEvolved | 15.5% | 36.0% | 40.1% | 43.2% | 48.1% | 55.2% | 58.9% | 67.0% | 81.1% | 97.7% |
| paldeanFates | 18.3% | 23.3% | 25.1% | 25.6% | 26.4% | 29.9% | 33.8% | 43.8% | 56.9% | 83.4% |
| paradoxRift | 16.0% | 40.1% | 45.5% | 48.3% | 55.6% | 65.1% | 69.9% | 80.6% | 92.9% | 99.9% |
| perfectOrder | 20.7% | 31.4% | 35.1% | 37.5% | 44.0% | 53.6% | 59.2% | 72.6% | 87.6% | 99.5% |
| phantasmalFlames | 14.2% | 20.5% | 21.9% | 20.4% | 17.1% | 16.7% | 18.4% | 28.6% | 54.1% | 77.9% |
| pitchBlack | 19.4% | 33.2% | 35.3% | 36.2% | 39.5% | 47.6% | 52.4% | 64.1% | 81.2% | 98.2% |
| prismaticEvolutions | 7.3% | 13.7% | 14.3% | 15.7% | 18.9% | 27.6% | 30.6% | 33.8% | 42.1% | 63.9% |
| scarletAndViolet151 | 17.4% | 41.5% | 47.8% | 49.9% | 54.5% | 61.9% | 66.0% | 76.4% | 89.7% | 99.6% |
| scarletAndVioletBase | 17.5% | 41.1% | 48.1% | 50.7% | 58.3% | 69.2% | 74.6% | 85.1% | 96.0% | 100.0% |
| shroudedFable | 21.2% | 45.6% | 53.3% | 55.8% | 62.1% | 70.8% | 75.7% | 85.7% | 96.0% | 100.0% |
| stellarCrown | 20.3% | 32.0% | 34.9% | 36.0% | 40.5% | 51.4% | 58.3% | 73.8% | 87.6% | 99.3% |
| surgingSparks | 16.9% | 37.2% | 38.5% | 39.6% | 44.5% | 52.9% | 56.9% | 66.4% | 82.1% | 98.4% |
| temporalForces | 21.0% | 42.2% | 48.6% | 51.5% | 58.7% | 68.4% | 73.2% | 83.8% | 95.1% | 100.0% |
| twilightMasquerade | 21.2% | 37.1% | 40.1% | 41.5% | 46.3% | 55.2% | 60.1% | 71.0% | 85.7% | 99.1% |
| whiteFlare | 13.5% | 37.0% | 39.3% | 41.2% | 44.7% | 50.4% | 53.8% | 61.4% | 75.0% | 95.5% |

Cells show P(realized average ≥ 80% of EV). The machine-readable curve includes targets 50%, 70%, 75%, 80%, 90%, and 100%, with uncertainty fields.

## 10. EV Representativeness

| Set | ±10%@36 | ±20%@36 | ±25%@36 | ±20%@100 | ±20%@250 | ±20%@1000 |
|---|---|---|---|---|---|---|
| ascendedHeroes | 5.5% | 13.1% | 17.3% | 20.8% | 35.1% | 68.1% |
| blackBolt | 13.5% | 27.6% | 35.5% | 32.2% | 48.1% | 83.5% |
| chaosRising | 12.2% | 26.6% | 35.9% | 32.1% | 55.6% | 90.3% |
| destinedRivals | 13.4% | 27.8% | 35.3% | 39.3% | 53.6% | 87.0% |
| journeyTogether | 24.4% | 49.0% | 61.2% | 70.6% | 90.2% | 99.8% |
| megaEvolution | 13.3% | 29.4% | 39.1% | 38.1% | 63.0% | 93.5% |
| obsidianFlames | 18.9% | 38.5% | 48.3% | 61.0% | 83.2% | 99.3% |
| paldeaEvolved | 17.1% | 34.3% | 42.8% | 44.4% | 63.2% | 92.7% |
| paldeanFates | 4.9% | 11.7% | 16.5% | 20.9% | 28.5% | 66.9% |
| paradoxRift | 20.9% | 40.8% | 50.1% | 62.3% | 83.4% | 99.3% |
| perfectOrder | 13.3% | 30.6% | 40.7% | 50.6% | 73.8% | 97.4% |
| phantasmalFlames | 1.6% | 5.6% | 9.6% | 3.0% | 27.1% | 58.6% |
| pitchBlack | 12.4% | 26.7% | 36.0% | 38.8% | 64.0% | 93.9% |
| prismaticEvolutions | 4.4% | 8.8% | 10.8% | 15.4% | 17.3% | 38.2% |
| scarletAndViolet151 | 18.1% | 35.8% | 44.4% | 55.5% | 77.9% | 98.4% |
| scarletAndVioletBase | 23.2% | 45.1% | 55.2% | 70.2% | 90.0% | 99.9% |
| shroudedFable | 24.0% | 46.2% | 56.2% | 71.0% | 90.5% | 99.9% |
| stellarCrown | 7.1% | 19.0% | 28.1% | 52.0% | 74.1% | 97.6% |
| surgingSparks | 17.1% | 35.4% | 45.1% | 44.8% | 64.8% | 93.7% |
| temporalForces | 22.3% | 43.3% | 53.1% | 67.6% | 88.3% | 99.8% |
| twilightMasquerade | 16.1% | 34.8% | 45.1% | 52.5% | 69.3% | 95.2% |
| whiteFlare | 16.1% | 32.5% | 40.9% | 40.7% | 54.3% | 87.6% |

## 11. Realization Horizons

| Set | First crossing | Stable R80/C80 | Status |
|---|---|---|---|
| prismaticEvolutions | 3375 | 2812 | resolved |
| phantasmalFlames | 1500 | 1167 | resolved |
| paldeanFates | 1000 | 833 | resolved |
| ascendedHeroes | 1000 | 792 | resolved |
| blackBolt | 500 | 458 | resolved |
| destinedRivals | 500 | 375 | resolved |
| whiteFlare | 500 | 375 | resolved |
| chaosRising | 500 | 333 | resolved |
| megaEvolution | 250 | 250 | resolved |
| paldeaEvolved | 250 | 250 | resolved |
| perfectOrder | 250 | 250 | resolved |
| pitchBlack | 250 | 250 | resolved |
| stellarCrown | 250 | 250 | resolved |
| surgingSparks | 250 | 250 | resolved |
| twilightMasquerade | 250 | 250 | resolved |
| journeyTogether | 72 | 150 | resolved |
| obsidianFlames | 150 | 150 | resolved |
| paradoxRift | 100 | 150 | resolved |
| scarletAndViolet151 | 150 | 150 | resolved |
| scarletAndVioletBase | 72 | 150 | resolved |
| shroudedFable | 72 | 150 | resolved |
| temporalForces | 100 | 150 | resolved |

## 12. Convergence Horizons

| Set | First crossing | Stable ±20%/80% | Status | Monotonicity violations |
|---|---|---|---|---|
| prismaticEvolutions | 7593 | 5906 | resolved | 36 |
| phantasmalFlames | 3375 | 2438 | resolved | 73 |
| ascendedHeroes | 2250 | 1750 | resolved | 40 |
| paldeanFates | 2250 | 1750 | resolved | 35 |
| blackBolt | 1000 | 875 | resolved | 29 |
| destinedRivals | 750 | 750 | resolved | 17 |
| whiteFlare | 750 | 708 | resolved | 19 |
| chaosRising | 750 | 625 | resolved | 24 |
| megaEvolution | 500 | 500 | resolved | 19 |
| paldeaEvolved | 500 | 500 | confirmation_did_not_ratify | 22 |
| pitchBlack | 500 | 500 | resolved | 22 |
| surgingSparks | 500 | 500 | resolved | 17 |
| twilightMasquerade | 500 | 417 | resolved | 17 |
| perfectOrder | 500 | 333 | resolved | 24 |
| stellarCrown | 500 | 333 | resolved | 23 |
| scarletAndViolet151 | 500 | 292 | resolved | 13 |
| obsidianFlames | 250 | 250 | resolved | 16 |
| paradoxRift | 250 | 250 | resolved | 15 |
| scarletAndVioletBase | 250 | 250 | resolved | 15 |
| shroudedFable | 150 | 250 | resolved | 16 |
| temporalForces | 250 | 250 | resolved | 16 |
| journeyTogether | 150 | 150 | resolved | 18 |

Paldea Evolved's 500-pack convergence value is an audit candidate whose independent confirmation did not ratify the validation band. It is retained in research output with status `confirmation_did_not_ratify` but is not exposed as a confirmed public horizon.

## 13. CLT vs Empirical Reality

| Set | Empirical R80 | CLT R80 | Empirical/CLT | Empirical ±20% | CLT ±20% | Empirical/CLT |
|---|---|---|---|---|---|---|
| ascendedHeroes | 792 | 746 | 1.06 | 1750 | 1,729 | 1.01 |
| blackBolt | 458 | 381 | 1.20 | 875 | 882 | 0.99 |
| chaosRising | 333 | 268 | 1.24 | 625 | 620 | 1.01 |
| destinedRivals | 375 | 331 | 1.13 | 750 | 767 | 0.98 |
| journeyTogether | 150 | 70 | 2.14 | 150 | 161 | 0.93 |
| megaEvolution | 250 | 214 | 1.17 | 500 | 495 | 1.01 |
| obsidianFlames | 150 | 96 | 1.56 | 250 | 222 | 1.13 |
| paldeaEvolved | 250 | 226 | 1.11 | 500 | 523 | 0.96 |
| paldeanFates | 833 | 743 | 1.12 | 1750 | 1,723 | 1.02 |
| paradoxRift | 150 | 95 | 1.58 | 250 | 220 | 1.14 |
| perfectOrder | 250 | 147 | 1.70 | 333 | 340 | 0.98 |
| phantasmalFlames | 1167 | 1,028 | 1.14 | 2438 | 2,384 | 1.02 |
| pitchBlack | 250 | 208 | 1.20 | 500 | 481 | 1.04 |
| prismaticEvolutions | 2812 | 2,422 | 1.16 | 5906 | 5,615 | 1.05 |
| scarletAndViolet151 | 150 | 122 | 1.23 | 292 | 283 | 1.03 |
| scarletAndVioletBase | 150 | 67 | 2.24 | 250 | 156 | 1.60 |
| shroudedFable | 150 | 65 | 2.31 | 250 | 150 | 1.67 |
| stellarCrown | 250 | 140 | 1.79 | 333 | 324 | 1.03 |
| surgingSparks | 250 | 217 | 1.15 | 500 | 501 | 1.00 |
| temporalForces | 150 | 73 | 2.05 | 250 | 169 | 1.48 |
| twilightMasquerade | 250 | 190 | 1.32 | 417 | 439 | 0.95 |
| whiteFlare | 375 | 315 | 1.19 | 708 | 729 | 0.97 |

## 14. Concentration vs Convergence

| Relationship | n | Pearson | Spearman | 95% bootstrap CI | BH p |
|---|---|---|---|---|---|
| top1OutcomeShare vs typicalCapture | 22 | -0.534 | -0.328 | [-0.695, 0.110] | 0.1620 |
| top1OutcomeShare vs gapCostNormalized | 22 | 0.582 | 0.302 | [-0.138, 0.674] | 0.2057 |
| top1OutcomeShare vs horizonTau20C80 | 22 | 0.893 | 0.976 | [0.908, 0.993] | 0.0006 |
| top1OutcomeShare vs horizonR80C80 | 22 | 0.886 | 0.966 | [0.909, 0.986] | 0.0006 |
| top5OutcomeShare vs typicalCapture | 22 | -0.772 | -0.680 | [-0.902, -0.312] | 0.0042 |
| top5OutcomeShare vs gapCostNormalized | 22 | 0.587 | 0.351 | [-0.125, 0.716] | 0.1555 |
| top5OutcomeShare vs horizonTau20C80 | 22 | 0.893 | 0.841 | [0.585, 0.954] | 0.0006 |
| top5OutcomeShare vs horizonR80C80 | 22 | 0.883 | 0.805 | [0.530, 0.942] | 0.0006 |
| top10OutcomeShare vs typicalCapture | 22 | -0.947 | -0.945 | [-0.985, -0.826] | 0.0006 |
| top10OutcomeShare vs gapCostNormalized | 22 | 0.502 | 0.337 | [-0.125, 0.708] | 0.1620 |
| top10OutcomeShare vs horizonTau20C80 | 22 | 0.740 | 0.577 | [0.182, 0.823] | 0.0224 |
| top10OutcomeShare vs horizonR80C80 | 22 | 0.728 | 0.509 | [0.078, 0.803] | 0.0383 |
| simCardHhi vs typicalCapture | 22 | -0.446 | -0.413 | [-0.718, 0.007] | 0.1036 |
| simCardHhi vs gapCostNormalized | 22 | 0.048 | 0.151 | [-0.312, 0.562] | 0.5188 |
| simCardHhi vs horizonTau20C80 | 22 | 0.584 | 0.458 | [-0.015, 0.773] | 0.0663 |
| simCardHhi vs horizonR80C80 | 22 | 0.582 | 0.449 | [-0.033, 0.791] | 0.0684 |
| simTopCardShare vs typicalCapture | 22 | -0.480 | -0.404 | [-0.710, 0.041] | 0.1104 |
| simTopCardShare vs gapCostNormalized | 22 | 0.061 | 0.120 | [-0.360, 0.537] | 0.5890 |
| simTopCardShare vs horizonTau20C80 | 22 | 0.594 | 0.519 | [0.069, 0.803] | 0.0381 |
| simTopCardShare vs horizonR80C80 | 22 | 0.591 | 0.516 | [0.094, 0.800] | 0.0381 |
| simTop5CardShare vs typicalCapture | 22 | -0.504 | -0.344 | [-0.654, 0.074] | 0.1555 |
| simTop5CardShare vs gapCostNormalized | 22 | 0.189 | 0.185 | [-0.273, 0.605] | 0.4439 |
| simTop5CardShare vs horizonTau20C80 | 22 | 0.668 | 0.505 | [0.058, 0.804] | 0.0383 |
| simTop5CardShare vs horizonR80C80 | 22 | 0.669 | 0.526 | [0.071, 0.826] | 0.0381 |
| simTop10CardShare vs typicalCapture | 22 | -0.505 | -0.339 | [-0.702, 0.118] | 0.1555 |
| simTop10CardShare vs gapCostNormalized | 22 | 0.321 | 0.196 | [-0.269, 0.601] | 0.4242 |
| simTop10CardShare vs horizonTau20C80 | 22 | 0.712 | 0.371 | [-0.139, 0.758] | 0.1350 |
| simTop10CardShare vs horizonR80C80 | 22 | 0.710 | 0.378 | [-0.141, 0.777] | 0.1309 |

H1 is strongly supported for outcome-tail concentration: top-1% share versus ±20%/80% horizon has Spearman ρ=0.976, and versus R80/C80 has ρ=0.966. Card concentration is directionally related but is a weaker cross-set predictor than the realized outcome tail.

## 15. Accessible Hits vs Convergence

| Relationship | n | Pearson | Spearman | 95% bootstrap CI | BH p |
|---|---|---|---|---|---|
| hitProb__illustration_rare vs typicalCapture | 22 | 0.510 | 0.317 | [-0.180, 0.702] | 0.3054 |
| hitProb__illustration_rare vs horizonTau20C80 | 22 | -0.604 | 0.128 | [-0.368, 0.585] | 0.7121 |
| hitProb__special_illustration_rare vs typicalCapture | 22 | -0.265 | -0.310 | [-0.678, 0.159] | 0.3054 |
| hitProb__special_illustration_rare vs horizonTau20C80 | 22 | 0.093 | -0.195 | [-0.590, 0.275] | 0.6582 |
| hitProb__any_premium vs typicalCapture | 22 | 0.027 | 0.325 | [-0.179, 0.693] | 0.3054 |
| hitProb__any_premium vs horizonTau20C80 | 22 | 0.111 | 0.117 | [-0.341, 0.534] | 0.7121 |
| econHit__1.00x vs typicalCapture | 22 | -0.031 | -0.135 | [-0.612, 0.369] | 0.7121 |
| econHit__1.00x vs horizonTau20C80 | 22 | -0.558 | -0.560 | [-0.841, -0.111] | 0.0444 |
| econHit__0.50x vs typicalCapture | 22 | 0.247 | 0.075 | [-0.422, 0.534] | 0.7387 |
| econHit__0.50x vs horizonTau20C80 | 22 | -0.681 | -0.487 | [-0.803, -0.045] | 0.0852 |
| econHit__2.00x vs typicalCapture | 22 | -0.014 | -0.076 | [-0.513, 0.385] | 0.7387 |
| econHit__2.00x vs horizonTau20C80 | 22 | -0.404 | -0.603 | [-0.808, -0.224] | 0.0444 |
| rarityShare__special_illustration_rare vs typicalCapture | 22 | -0.390 | -0.071 | [-0.537, 0.461] | 0.7598 |
| rarityShare__special_illustration_rare vs horizonTau20C80 | 22 | 0.856 | 0.590 | [0.145, 0.862] | 0.0320 |
| rarityShare__illustration_rare vs typicalCapture | 21 | -0.220 | -0.347 | [-0.754, 0.159] | 0.2512 |
| rarityShare__illustration_rare vs horizonTau20C80 | 21 | -0.554 | -0.514 | [-0.784, -0.115] | 0.0680 |
| rarityShare__hyper_rare vs typicalCapture | 14 | 0.284 | 0.332 | [-0.246, 0.734] | 0.3302 |
| rarityShare__hyper_rare vs horizonTau20C80 | 14 | -0.262 | -0.225 | [-0.703, 0.371] | 0.5082 |
| rarityShare__double_rare vs typicalCapture | 22 | 0.442 | 0.409 | [-0.053, 0.756] | 0.1549 |
| rarityShare__double_rare vs horizonTau20C80 | 22 | 0.033 | -0.272 | [-0.660, 0.218] | 0.3302 |

## 16. Similar EV, Different Experience

| Set A | EV A | Capture A | Set B | EV B | Capture B | Capture gap |
|---|---|---|---|---|---|---|
| journeyTogether | 3.44 | 54.9% | paradoxRift | 3.96 | 39.6% | 15.3% |
| ascendedHeroes | 9.06 | 36.1% | prismaticEvolutions | 8.53 | 20.9% | 15.2% |
| journeyTogether | 3.44 | 54.9% | scarletAndVioletBase | 4.03 | 43.2% | 11.7% |
| journeyTogether | 3.44 | 54.9% | pitchBlack | 3.80 | 44.0% | 10.9% |
| journeyTogether | 3.44 | 54.9% | megaEvolution | 3.80 | 44.8% | 10.1% |

## 17. Financial RIP Validation

| Relationship | n | Pearson | Spearman | 95% bootstrap CI | BH p |
|---|---|---|---|---|---|
| financialRipV3 vs typicalCapture | 22 | 0.546 | 0.399 | [-0.032, 0.725] | 0.0737 |
| financialRipV3 vs gapCostNormalized | 22 | 0.103 | 0.355 | [-0.143, 0.756] | 0.1043 |
| financialRipV3 vs horizonTau20C80 | 22 | -0.603 | -0.597 | [-0.832, -0.204] | 0.0092 |
| financialRipV3 vs horizonR80C80 | 22 | -0.598 | -0.596 | [-0.828, -0.196] | 0.0092 |
| financialRipV3 vs top1OutcomeShare | 22 | -0.690 | -0.600 | [-0.828, -0.204] | 0.0092 |
| financialRipV3 vs simCardHhi | 22 | -0.769 | -0.546 | [-0.840, -0.092] | 0.0132 |
| financialRipV3 vs realize0.80@36 | 22 | 0.718 | 0.577 | [0.164, 0.821] | 0.0101 |
| financialRipV3 vs within0.20@36 | 22 | 0.711 | 0.564 | [0.135, 0.825] | 0.0109 |
| financialRipV3 vs cv | 22 | -0.690 | -0.614 | [-0.806, -0.268] | 0.0092 |

Financial RIP captures part, but not all, of EV representativeness. It is moderately associated with the ±20%/80% horizon (Spearman ρ=-0.597) and R80/C80 (ρ=-0.596), but its Typical Capture association is weaker and its bootstrap interval spans zero. Representativeness therefore contains useful structure not reducible to the current Financial RIP score. All comparisons use the exact same calculation run, never the stale public leaderboard.

## 18. Counterfactual Findings

The dataset contains 402 paired Tier B counterfactual rows covering rarity and top-card ablations, top-card/top-five price shocks, and top-1% winsorization. Each scenario revalues the same sampled paths, so its delta has no resampling-path noise. Full scenario parameters and deltas are in the counterfactual CSV.

## 19. Limitations

The effective cross-sectional sample is 22 sets; pack independence and simulator validity are assumed; values are gross market value with no selling fees, grading, or additional condition variance; Tier B reconstructs latent identity rather than recovering exact historical paths; estimates retain Monte Carlo uncertainty; and all conclusions are market-date dependent. Correlations are observational associations. Only paired model ablations support model-internal causal statements.

## 20. Product Recommendation

Do not publish a new score from this version alone. Typical Capture is the clearest one-pack descriptive statistic, while R80/C80 and ±20%/80% horizons answer distinct planning questions but can be sensitive to grid, confidence, and market-date changes. A future public metric should be selected only after temporal stability is measured across multiple market dates and redundancy with Financial RIP is quantified. Keep Tier B and counterfactuals research-only; Tier A is the plausible routine post-simulation layer because it consumes already-persisted artifacts and remains outside the publication critical path.

### Performance recommendation

Persisted per-set build runtimes span 3.5–57.9 seconds in this cohort (sum 277.2 seconds; timings vary with cache and prior Tier B state). Tier A should remain eligible for routine post-simulation processing. Seeded Tier B, card-level recording, and paired counterfactuals should remain manual or separately scheduled research work and must not enter the publication critical path.
