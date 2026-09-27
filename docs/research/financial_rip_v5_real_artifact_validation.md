# Financial RIP V5 real-artifact and temporal validation

## 1. Authority

- Replay began from detached HEAD `50d3db0cbfae428cd300320e93ebf85fbd661e5b`. A concurrent checkout moved the workspace to `fix/market-explorer-adaptive-timeout-clean-20260919` at `9f5cb43416b61341f8ea7f4bf969e96a3ba9b28d`. The canonical scoring and distribution files have no diff between those commits. Research candidate `FINANCIAL_RIP_V5_CANDIDATE`; canonical Financial V4 and Overall V12.
- Working tree contains the research files plus concurrent log changes. No production scoring files or database rows were edited by this validation.
- Current published snapshot: `0e65fb6d-ff33-4331-99d5-d6a214ecc712` for market date `2026-09-14`; pinned price date `2026-09-14`; fingerprint `e18fb00cd41f1646579b082164c80b0da3db2e1831dec9428c6fd4d82ac689ce`; ranking method `budget_product_ranking_v1`.
- Full Market budget $1300.0; 138 products, 22 sets, 22 exact source runs and 22 matching million-outcome artifacts.
- Every row was joined by sealed product, run ID, and pinned price date. Artifact SHA-256 is retained in JSON. The five unchanged components matched exactly. Recomputed V4 scores and Financial ranks matched stored controls.

## 2. Current-market result

- V4/V5 score Pearson 0.9957, Spearman 0.9976; rank Kendall τ 0.9664.
- V5−V4 score delta mean 2.3303, median 2.4853, P10/P90 1.6367/3.0972.
- Absolute rank movement mean 1.94, median 1.5, P90 4.0, max 10; counts unchanged/1–2/3–5/>5 = 38/57/33/10.
- Top-5/10/20 overlap: 5/5, 8/10, 19/20.
- Top-10 entrants: Pitch Black Booster Box (11→8, Δscore +1.2497, SR 70.73, old LR 62.39, P(win) 1.0248%); Ascended Heroes Pokemon Center Elite Trainer Box (Exclusive) (15→10, Δscore +3.2819, SR 54.74, old LR 32.86, P(win) 5.6139%)
- Top-10 exits: Pitch Black Pokemon Center Elite Trainer Box (Exclusive) (9→13, Δscore +0.0484, SR 73.09, old LR 72.77, P(win) 0.2542%); Shrouded Fable Booster Bundle (10→12, Δscore +0.4608, SR 73.22, old LR 70.15, P(win) 0.0606%)
- Ten largest upward movers: Scarlet & Violet Sleeved Booster Pack (109→102, Δscore +3.1104, SR 46.70, old LR 25.96, P(win) 0.0000%); Surging Sparks Pokemon Center Elite Trainer Box (Exclusive) (69→62, Δscore +3.1892, SR 55.34, old LR 34.08, P(win) 0.0181%); Journey Together Booster Bundle (73→67, Δscore +3.1335, SR 56.06, old LR 35.17, P(win) 0.0000%); Journey Together Sleeved Booster Pack (104→98, Δscore +3.1717, SR 47.87, old LR 26.72, P(win) 0.0000%); Prismatic Evolutions Pokemon Center Elite Trainer Box (Exclusive) (22→16, Δscore +3.0098, SR 52.25, old LR 32.18, P(win) 4.8728%); Ascended Heroes Pokemon Center Elite Trainer Box (Exclusive) (15→10, Δscore +3.2819, SR 54.74, old LR 32.86, P(win) 5.6139%); Twilight Masquerade Pokemon Center Elite Trainer Box (Exclusive) (83→79, Δscore +2.8832, SR 50.39, old LR 31.17, P(win) 0.1019%); Mega Evolution Sleeved Booster Pack (95→91, Δscore +2.7116, SR 47.81, old LR 29.74, P(win) 0.0091%); Twilight Masquerade Booster Box (44→40, Δscore +2.5682, SR 58.03, old LR 40.91, P(win) 0.6793%); Twilight Masquerade Booster Pack (33→29, Δscore +2.2860, SR 62.56, old LR 47.32, P(win) 0.6197%)
- Ten largest downward movers: Paldean Fates Booster Bundle (99→109, Δscore +1.8231, SR 31.87, old LR 19.72, P(win) 1.9470%); Phantasmal Flames Elite Trainer Box (107→115, Δscore +1.6312, SR 35.22, old LR 24.34, P(win) 1.5223%); Phantasmal Flames Booster Bundle (89→95, Δscore +1.7554, SR 39.16, old LR 27.45, P(win) 2.2982%); Phantasmal Flames Sleeved Booster Pack (94→100, Δscore +1.7020, SR 38.27, old LR 26.92, P(win) 2.2078%); Black Bolt Elite Trainer Box (98→104, Δscore +2.1035, SR 39.24, old LR 25.22, P(win) 0.8016%); Phantasmal Flames Booster Pack (75→80, Δscore +1.9130, SR 42.88, old LR 30.12, P(win) 2.9016%); White Flare Booster Bundle (77→81, Δscore +2.4424, SR 46.22, old LR 29.94, P(win) 0.7990%); White Flare Booster Pack (66→70, Δscore +2.5173, SR 48.93, old LR 32.15, P(win) 0.9220%); Pitch Black Pokemon Center Elite Trainer Box (Exclusive) (9→13, Δscore +0.0484, SR 73.09, old LR 72.77, P(win) 0.2542%); White Flare Elite Trainer Box (97→101, Δscore +2.2664, SR 41.25, old LR 26.14, P(win) 0.5131%)
- Largest positive score deltas: Ascended Heroes Pokemon Center Elite Trainer Box (Exclusive) (15→10, Δscore +3.2819, SR 54.74, old LR 32.86, P(win) 5.6139%); Paldea Evolved Pokemon Center Elite Trainer Box (Exclusive) (85→83, Δscore +3.2762, SR 52.13, old LR 30.29, P(win) 0.0430%); Paradox Rift Pokemon Center Elite Trainer Box (Exclusive) [Roaring Moon] (78→76, Δscore +3.2501, SR 54.50, old LR 32.83, P(win) 0.0000%); Ascended Heroes Booster Bundle (4→4, Δscore +3.2443, SR 63.16, old LR 41.54, P(win) 14.2448%); Paradox Rift Pokemon Center Elite Trainer Box (Exclusive) [Iron Valiant] (80→77, Δscore +3.2208, SR 54.20, old LR 32.73, P(win) 0.0000%); Ascended Heroes Elite Trainer Box (6→6, Δscore +3.2175, SR 59.60, old LR 38.15, P(win) 11.3264%); Scarlet & Violet Pokemon Center Elite Trainer Box (Exclusive) [Miraidon] (112→108, Δscore +3.2114, SR 46.61, old LR 25.21, P(win) 0.0000%); Surging Sparks Pokemon Center Elite Trainer Box (Exclusive) (69→62, Δscore +3.1892, SR 55.34, old LR 34.08, P(win) 0.0181%); Journey Together Sleeved Booster Pack (104→98, Δscore +3.1717, SR 47.87, old LR 26.72, P(win) 0.0000%); Ascended Heroes Booster Pack (1→1, Δscore +3.1688, SR 66.88, old LR 45.76, P(win) 15.9202%)
- Largest negative score deltas: Obsidian Flames Pokemon Center Elite Trainer Box (Exclusive) (20→24, Δscore +0.0000, SR 69.26, old LR 69.26, P(win) 0.0000%); Mega Evolution Pokemon Center Elite Trainer Box (Exclusive) [Mega Gardevoir] (7→7, Δscore +0.0163, SR 78.15, old LR 78.04, P(win) 0.4961%); Pitch Black Pokemon Center Elite Trainer Box (Exclusive) (9→13, Δscore +0.0484, SR 73.09, old LR 72.77, P(win) 0.2542%); Chaos Rising Pokemon Center Elite Trainer Box (16→19, Δscore +0.4062, SR 70.13, old LR 67.42, P(win) 0.0375%); Temporal Forces Booster Box (8→9, Δscore +0.4304, SR 73.65, old LR 70.78, P(win) 0.0989%); Shrouded Fable Booster Bundle (10→12, Δscore +0.4608, SR 73.22, old LR 70.15, P(win) 0.0606%); Perfect Order Booster Box (12→14, Δscore +0.4943, SR 72.44, old LR 69.15, P(win) 0.0875%); Perfect Order Pokemon Center Elite Trainer Box (18→20, Δscore +0.5569, SR 69.49, old LR 65.78, P(win) 0.0013%); Perfect Order Booster Pack (13→15, Δscore +0.7526, SR 70.66, old LR 65.64, P(win) 0.0320%); Journey Together Enhanced Booster Box (21→21, Δscore +0.8202, SR 69.06, old LR 63.59, P(win) 0.0011%)
- The only changed term is 0.15 × (SR − old Loss Resilience), subject to four-decimal score rounding. Thus a product can fall in rank while its score rises if peers receive a larger correction. Median retention, upside, jackpot and efficiency stay fixed for each product.
- The Ascended Heroes Pokémon Center ETB gains 3.2819 points: SR 54.74 versus old Loss Resilience 32.86, at 5.61% P(win), 3 units and $1143.39 committed. The Pitch Black Pokémon Center ETB gains only 0.0484: SR 73.09 versus old 72.77. Their rank crossover is driven by the different downside correction, with unchanged median/upside components.
- Material top-cohort movement economics (deep deficit is E[(0.5−R)+], inferred from rounded SR and capped recovery):

| Product | V4→V5 rank | Quantity / cost | P(win) | P50/cost | P95/cost | EV/cost | Capped recovery | Deep deficit | Old LR→SR |
|---|---:|---:|---:|---:|---:|---:|---:|---:|---:|
| Pitch Black Booster Box | 11→8 | 6 / $1184.58 | 1.02% | 0.574 | 0.856 | 0.595 | 0.594 | 0.014 | 62.39→70.73 |
| Ascended Heroes Pokemon Center Elite Trainer Box (Exclusive) | 15→10 | 3 / $1143.39 | 5.61% | 0.377 | 1.103 | 0.463 | 0.443 | 0.105 | 32.86→54.74 |
| Pitch Black Pokemon Center Elite Trainer Box (Exclusive) | 9→13 | 10 / $1248.20 | 0.25% | 0.586 | 0.801 | 0.616 | 0.616 | 0.000 | 72.77→73.09 |
| Shrouded Fable Booster Bundle | 10→12 | 22 / $1281.50 | 0.06% | 0.616 | 0.797 | 0.621 | 0.621 | 0.004 | 70.15→73.22 |


## 3. Redundancy finding

| SR compared with | Pearson | Spearman |
|---|---:|---:|
| typicalRetentionScore | 0.9789 | 0.9822 |
| trueWinFrequencyScore | 0.0349 | 0.0569 |
| baseEconomicEfficiencyScore | 0.9383 | 0.9735 |
| lossResilienceScore | 0.9502 | 0.9796 |
| v4Score | 0.7959 | 0.8878 |
| v5Score | 0.7768 | 0.8946 |

Set-balanced (22 set means) SR/Typical Pearson 0.9715, Spearman 0.9650.

Family robustness:

- booster_box: n=15; Pearson 0.9722, Spearman 0.9964.
- booster_bundle: n=23; Pearson 0.9703, Spearman 0.9575.
- elite_trainer_box: n=27; Pearson 0.9624, Spearman 0.9316.
- enhanced_booster_box: n=2; correlation unavailable.
- half_booster_box: n=8; Pearson 0.9961, Spearman 1.0000.
- loose_booster_pack: n=22; Pearson 0.9712, Spearman 0.9831.
- pokemon_center_elite_trainer_box: n=26; Pearson 0.9899, Spearman 0.9747.
- sleeved_booster_pack: n=15; Pearson 0.9554, Spearman 0.9857.

## 4. Distinct-information finding

Pairs below are the strongest observed under transparent matching windows: A has Typical scores within 1 point; B has SR within 1 point; C has P(win) within 1 percentage point; D has median values within $10. These are descriptive searches, not significance cutoffs.

- Type A: Scarlet & Violet Booster Bundle versus Phantasmal Flames Booster Pack; Typical difference 0.847, SR difference 13.191, P(win) difference 2.9016%, median-value difference $15.16. Details in JSON.
- Type B: Stellar Crown Booster Bundle versus Phantasmal Flames Booster Box; Typical difference 13.215, SR difference 0.474, P(win) difference 4.6894%, median-value difference $130.68. Details in JSON.
- Type C: Journey Together Half Booster Box versus Mega Evolution Pokemon Center Elite Trainer Box (Exclusive) [Mega Gardevoir]; Typical difference 54.970, SR difference 54.471, P(win) difference 0.4961%, median-value difference $680.64. Details in JSON.
- Type D: Paldea Evolved Booster Bundle versus Phantasmal Flames Booster Box; Typical difference 3.277, SR difference 13.086, P(win) difference 4.6581%, median-value difference $9.75. Details in JSON.
- Stricter same-family example: Stellar Crown versus Surging Sparks ETBs have Typical scores 33.15/34.00 and P(win) 0.0000%/0.0061%, yet SR 36.83/40.52. Their capped recoveries are 0.2836/0.3138; deep-shortfall expectations E[(0.5−R)+] are 0.2170/0.1908. At similar committed capital ($1243.44/$1246.00), the latter has shallower average downside and higher EV ($390.97 versus $352.65). This is distinct information beyond the nearly matched P50, though the product-level correlation remains very high.
- Type C's largest raw SR gap is confounded by very different median retention and cost structure. It is not evidence of a clean P(win)-controlled causal effect.

## 5. Temporal result

| Market date | Products | Sets | V4/V5 Pearson | Rank Spearman | Mean Δ | SR/Typical Pearson | Top 5/10/20 overlap |
|---|---:|---:|---:|---:|---:|---:|---|
| 2026-09-14 | 138 | 22 | 0.9957 | 0.9976 | 2.3303 | 0.9789 | 5/8/19 |
| 2026-09-08 | 138 | 22 | 0.9955 | 0.9978 | 2.3094 | 0.9787 | 5/10/19 |
| 2026-08-27 | 138 | 22 | 0.9960 | 0.9980 | 2.3524 | 0.9767 | 4/10/20 |
| 2026-08-26 | 138 | 22 | 0.9959 | 0.9982 | 2.3417 | 0.9774 | 4/9/19 |
| 2026-08-25 | 138 | 22 | 0.9960 | 0.9978 | 2.3459 | 0.9777 | 4/10/19 |
| 2026-08-24 | 138 | 22 | 0.9961 | 0.9983 | 2.3517 | 0.9776 | 5/9/19 |
| 2026-08-22 | 138 | 22 | 0.9964 | 0.9981 | 2.3692 | 0.9779 | 5/10/20 |

Repeated products: 138; median V4/V5 score variance 0.1837/0.1870; median delta variance 0.00117.
- Largest delta-range changes: Obsidian Flames Pokemon Center Elite Trainer Box (Exclusive) 0.000–2.425; Chaos Rising Pokemon Center Elite Trainer Box 0.406–2.125; Pitch Black Booster Bundle 0.916–2.179; Journey Together Booster Pack 1.362–2.523; Journey Together Booster Box 2.114–3.174; Pitch Black Booster Pack 0.545–1.498; Pitch Black Booster Box 0.307–1.250; Perfect Order Booster Pack 0.753–1.619; Mega Evolution Pokemon Center Elite Trainer Box (Exclusive) [Mega Lucario] 1.985–2.815; Chaos Rising Booster Box 1.177–1.898
- Largest set-mean SR ranges: 472f851c-2e41-4c80-b6fc-8478d1d92730 SR 64.17–72.44, Typical 60.20–69.10; 5bdbfae1-3f2e-44e7-b8c9-1035ad45b896 SR 59.65–63.25, Typical 55.09–58.95; 5e99f658-39f0-4845-9228-db8db3965f32 SR 61.06–64.14, Typical 57.67–60.81; 142d3869-9d39-48b6-a810-751af2aac748 SR 52.06–54.82, Typical 48.20–51.02; 41a0ac1c-27ca-444b-8665-8ba35e583a3b SR 43.00–45.52, Typical 34.22–37.04
- Obsidian Flames Pokémon Center ETB changes from quantity 1 in August (about $690 committed, correction +2.18 to +2.42) to quantity 2 in September (about $1,270 committed, correction 0). The quantity and cost regime changed; this is an economic explanation for the largest delta change, not an unexplained model jump.
- Pitch Black Booster Bundle changes from quantity 36–38 in August to 32–33 in September as price rises; its correction rises from about +0.9–1.1 to +2.0–2.2 while P(win) falls from roughly 1.3–1.7% to 0.1–0.2%. The changed quantity-level downside explains why a fixed formula does not yield a fixed correction.
- Artifact inventory by creation date (not assumed to equal market date): 2026-09-18: 21, 2026-09-15: 22, 2026-09-14: 22, 2026-09-13: 22, 2026-09-12: 22, 2026-09-11: 22, 2026-09-10: 32, 2026-09-09: 12, 2026-09-08: 43, 2026-09-04: 22, 2026-09-02: 40, 2026-08-31: 20, 2026-08-29: 2, 2026-08-28: 21, 2026-08-27: 24, 2026-08-26: 22, 2026-08-25: 22, 2026-08-24: 22, 2026-08-22: 22, 2026-08-20: 22, 2026-08-18: 22, 2026-08-17: 22.

## 6. High-win coverage

Current P(win) min/median/P75/P90/max: 0.0000%/0.0366%/0.5055%/2.1512%/15.9202%.
Buckets: 0-5%=130, 5-10%=2, 10-20%=6, 20-30%=0, 30-50%=0, 50%+=0

`CURRENT_MARKET_COHORT_DOES_NOT_TEST_HIGH_WIN_DOMAIN`

## 7. Blockers and limits

- August 21 published snapshot lacks an exact simulation product row for a pinned source identity; it is unavailable for full product/rank replay. No substitution was made.
- The 7 valid snapshots cover August 22–September 14. Artifact-only dates without complete published ranking cohorts were inventoried but were not used for rank analysis.
- SR and Typical Retention are highly correlated on the product cohort; this is a material redundancy concern for adjudication, even though distinct pairs exist.
- The real current cohort does not test P(win) ≥0.30 or ≥0.50. Best-Open/high-win behavior belongs to the next gate.
- Workspace-wide `git diff --check` flags trailing spaces in concurrently changed `logs/task_scheduler_debug.log`. A direct trailing-whitespace scan of the new research files passes; the log is outside this study.

## 8. Decision

`FINANCIAL_RIP_V5_REAL_ARTIFACT_VALIDATION_COMPLETE`

This means the generated real-artifact evidence is internally valid for the seven lineage-complete states. It does not approve production promotion. No production database writes, snapshot publications, migrations, or canonical pointer changes were made.
