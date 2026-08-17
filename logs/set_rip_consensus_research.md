# Set RIP Consensus Research

READ-ONLY RESEARCH. No Set RIP score is published.

# CURRENT COVERAGE

| Family | Rankable SKUs | Represented sets |
|---|---:|---:|
| Booster Box | 15 | 15 |
| Booster Bundle | 23 | 22 |
| Elite Trainer Box | 9 | 8 |
| Enhanced Booster Box | 0 | 0 |
| Half Booster Box | 0 | 0 |
| Pokémon Center Elite Trainer Box | 9 | 8 |
| Sleeved Booster Pack | 15 | 15 |

# LEADING TWO-LEVEL CONSTRUCT

Set RIP should measure a set's average relative ripping quality across eligible sealed-product families. Within each family, all rankable SKU standings are averaged; available eligible family means are then averaged with one equal vote per family.

Leading research candidate: mean SKU standing within each canonical product family, then an unshrunk equal-family arithmetic mean. A set needs at least two eligible families; a family needs at least three represented sets. Missing families are omitted, never zero, and SKU-rich families receive no extra weight.

# SET × FAMILY MATRIX

The JSON contains 238 explicit cells. Missing families are omitted, never zero.

# MULTI-SKU DIAGNOSTICS

3 cells have multiple rankable SKUs. The leading construct uses the mean.

| Set | Family | SKUs (rank: standing) | Best | Median | Mean |
|---|---|---|---:|---:|---:|
| Scarlet and Violet Base Set | elite_trainer_box | Scarlet & Violet Elite Trainer Box [Koraidon] (8: 0.125); Scarlet & Violet Elite Trainer Box [Miraidon] (9: 0.0) | 0.125 | 0.0625 | 0.0625 |
| Scarlet and Violet Base Set | pokemon_center_elite_trainer_box | Scarlet & Violet Pokemon Center Elite Trainer Box (Exclusive) [Miraidon] (8: 0.125); Scarlet & Violet Pokemon Center Elite Trainer Box (Exclusive) [Koraidon] (9: 0.0) | 0.125 | 0.0625 | 0.0625 |
| Surging Sparks | booster_bundle | Surging Sparks Booster Bundle (Retail) (16: 0.318182); Surging Sparks Booster Bundle (LGS) (18: 0.227273) | 0.318182 | 0.272727 | 0.272727 |

# FAMILY CORRELATIONS

| Family A | Family B | Overlap N | Spearman |
|---|---|---:|---:|
| booster_box | booster_bundle | 15 | 0.439286 |
| booster_box | elite_trainer_box | 5 | 0.8 |
| booster_box | enhanced_booster_box | 0 | None |
| booster_box | half_booster_box | 0 | None |
| booster_box | pokemon_center_elite_trainer_box | 5 | 0.4 |
| booster_box | sleeved_booster_pack | 15 | 0.267857 |
| booster_bundle | elite_trainer_box | 8 | 0.738095 |
| booster_bundle | enhanced_booster_box | 0 | None |
| booster_bundle | half_booster_box | 0 | None |
| booster_bundle | pokemon_center_elite_trainer_box | 8 | 0.761905 |
| booster_bundle | sleeved_booster_pack | 15 | -0.089286 |
| elite_trainer_box | enhanced_booster_box | 0 | None |
| elite_trainer_box | half_booster_box | 0 | None |
| elite_trainer_box | pokemon_center_elite_trainer_box | 8 | 0.571429 |
| elite_trainer_box | sleeved_booster_pack | 5 | -0.2 |
| enhanced_booster_box | half_booster_box | 0 | None |
| enhanced_booster_box | pokemon_center_elite_trainer_box | 0 | None |
| enhanced_booster_box | sleeved_booster_pack | 0 | None |
| half_booster_box | pokemon_center_elite_trainer_box | 0 | None |
| half_booster_box | sleeved_booster_pack | 0 | None |
| pokemon_center_elite_trainer_box | sleeved_booster_pack | 5 | -0.6 |

# LEADING RESEARCH ORDERING

| Rank | Set | Set RIP unit | Score ×100 | Families | SKU evidence |
|---:|---|---:|---:|---:|---:|
| 1 | Pitch Black | 0.945887 | 94.588733 | 3 | 3 |
| 2 | Ascended Heroes | 0.943182 | 94.318167 | 3 | 3 |
| 3 | Perfect Order | 0.781493 | 78.14934 | 5 | 5 |
| 4 | Temporal Forces | 0.755411 | 75.541133 | 3 | 3 |
| 5 | Stellar Crown | 0.593074 | 59.307367 | 3 | 3 |
| 6 | Chaos Rising | 0.590909 | 59.0909 | 3 | 3 |
| 7 | Black Bolt | 0.568182 | 56.818167 | 3 | 3 |
| 8 | Twilight Masquerade | 0.549783 | 54.978333 | 3 | 3 |
| 9 | Paradox Rift | 0.482684 | 48.2684 | 3 | 3 |
| 10 | Mega Evolution | 0.467533 | 46.753267 | 3 | 3 |
| 11 | White Flare | 0.458333 | 45.833333 | 3 | 3 |
| 12 | Paldea Evolved | 0.450217 | 45.021667 | 3 | 3 |
| 13 | Destined Rivals | 0.432468 | 43.24676 | 5 | 5 |
| 14 | Journey Together | 0.364935 | 36.4935 | 5 | 5 |
| 15 | Phantasmal Flames | 0.354221 | 35.42208 | 5 | 5 |
| 16 | Surging Sparks | 0.209957 | 20.995667 | 3 | 4 |
| 17 | Scarlet and Violet Base Set | 0.196429 | 19.64286 | 5 | 7 |
| 18 | Obsidian Flames | 0.181818 | 18.181833 | 3 | 3 |
| — | Shrouded Fable | 1.0 | 100.0 | 1 | 1 |
| — | Prismatic Evolutions | 0.863636 | 86.3636 | 1 | 1 |
| — | Scarlet and Violet 151 | 0.727273 | 72.7273 | 1 | 1 |
| — | Paldean Fates | 0.272727 | 27.2727 | 1 | 1 |

# PREVIOUS VS CURRENT LEADING CONSTRUCT

Old BEST-SKU + prior-strength-2 versus new mean-SKU + no-shrinkage: overlap N=18, Spearman=0.997936, top-five overlap=5, mean absolute movement=0.111111, maximum movement=1.

| Set | Old rank | New rank | Movement | Old unit | New unit |
|---|---:|---:|---:|---:|---:|
| Scarlet and Violet Base Set | 18 | 17 | 1 | 0.30102 | 0.196429 |
| Obsidian Flames | 17 | 18 | -1 | 0.309091 | 0.181818 |
| Phantasmal Flames | 15 | 15 | 0 | 0.395872 | 0.354221 |
| Journey Together | 14 | 14 | 0 | 0.403525 | 0.364935 |
| Paldea Evolved | 12 | 12 | 0 | 0.47013 | 0.450217 |
| Black Bolt | 7 | 7 | 0 | 0.540909 | 0.568182 |
| Pitch Black | 1 | 1 | 0 | 0.767532 | 0.945887 |
| Stellar Crown | 5 | 5 | 0 | 0.555844 | 0.593074 |
| Chaos Rising | 6 | 6 | 0 | 0.554545 | 0.590909 |
| Paradox Rift | 9 | 9 | 0 | 0.48961 | 0.482684 |

# FAMILY-COUNT FAIRNESS

Coverage is a rankability gate only. Every eligible family contributes one vote, regardless of its SKU count. In the current cohort, higher family coverage is negatively rather than positively associated with Set RIP, so this diagnostic does not show a systematic more-families advantage.

Available sets=18; Spearman coverage versus Set RIP=-0.346658; coverage versus better rank=-0.346658.

| Family count | Sets | Average Set RIP unit |
|---:|---:|---:|
| 3 | 13 | 0.553613 |
| 5 | 5 | 0.425909 |

# ADDITIONAL-FAMILY IMPACT

Positive delta means the family improves the set's full mean; negative delta means it lowers it.

| Set | Omitted family | Full unit | Without family | Delta |
|---|---|---:|---:|---:|
| Phantasmal Flames | booster_box | 0.354221 | 0.264205 | 0.090016 |
| Phantasmal Flames | booster_bundle | 0.354221 | 0.397321 | -0.043101 |
| Phantasmal Flames | elite_trainer_box | 0.354221 | 0.349026 | 0.005195 |
| Phantasmal Flames | pokemon_center_elite_trainer_box | 0.354221 | 0.317776 | 0.036445 |
| Phantasmal Flames | sleeved_booster_pack | 0.354221 | 0.442776 | -0.088555 |
| Journey Together | booster_box | 0.364935 | 0.456169 | -0.091234 |
| Journey Together | booster_bundle | 0.364935 | 0.285714 | 0.079221 |
| Journey Together | elite_trainer_box | 0.364935 | 0.393669 | -0.028734 |
| Journey Together | pokemon_center_elite_trainer_box | 0.364935 | 0.268669 | 0.096266 |
| Journey Together | sleeved_booster_pack | 0.364935 | 0.420455 | -0.055519 |
| Paldea Evolved | booster_box | 0.450217 | 0.353897 | 0.09632 |
| Paldea Evolved | booster_bundle | 0.450217 | 0.607143 | -0.156926 |
| Paldea Evolved | sleeved_booster_pack | 0.450217 | 0.389611 | 0.060606 |
| Scarlet and Violet Base Set | booster_box | 0.196429 | 0.209821 | -0.013393 |
| Scarlet and Violet Base Set | booster_bundle | 0.196429 | 0.245536 | -0.049107 |
| Scarlet and Violet Base Set | elite_trainer_box | 0.196429 | 0.229911 | -0.033482 |
| Scarlet and Violet Base Set | pokemon_center_elite_trainer_box | 0.196429 | 0.229911 | -0.033482 |
| Scarlet and Violet Base Set | sleeved_booster_pack | 0.196429 | 0.066964 | 0.129464 |
| Black Bolt | booster_bundle | 0.568182 | 0.625 | -0.056818 |
| Black Bolt | elite_trainer_box | 0.568182 | 0.539772 | 0.028409 |
| Black Bolt | pokemon_center_elite_trainer_box | 0.568182 | 0.539772 | 0.028409 |
| Pitch Black | booster_box | 0.945887 | 0.918831 | 0.027056 |
| Pitch Black | booster_bundle | 0.945887 | 0.964286 | -0.018398 |
| Pitch Black | sleeved_booster_pack | 0.945887 | 0.954546 | -0.008658 |
| Stellar Crown | booster_box | 0.593074 | 0.639611 | -0.046537 |
| Stellar Crown | booster_bundle | 0.593074 | 0.571429 | 0.021645 |
| Stellar Crown | sleeved_booster_pack | 0.593074 | 0.568182 | 0.024892 |
| Chaos Rising | booster_box | 0.590909 | 0.493507 | 0.097403 |
| Chaos Rising | booster_bundle | 0.590909 | 0.5 | 0.090909 |
| Chaos Rising | sleeved_booster_pack | 0.590909 | 0.779221 | -0.188312 |
| Paradox Rift | booster_box | 0.482684 | 0.438312 | 0.044372 |
| Paradox Rift | booster_bundle | 0.482684 | 0.678571 | -0.195888 |
| Paradox Rift | sleeved_booster_pack | 0.482684 | 0.331169 | 0.151515 |
| Perfect Order | booster_box | 0.781493 | 0.744724 | 0.036769 |
| Perfect Order | booster_bundle | 0.781493 | 0.772321 | 0.009172 |
| Perfect Order | elite_trainer_box | 0.781493 | 0.758117 | 0.023377 |
| Perfect Order | pokemon_center_elite_trainer_box | 0.781493 | 0.726867 | 0.054627 |
| Perfect Order | sleeved_booster_pack | 0.781493 | 0.905438 | -0.123945 |
| Ascended Heroes | booster_bundle | 0.943182 | 0.9375 | 0.005682 |
| Ascended Heroes | elite_trainer_box | 0.943182 | 0.914772 | 0.028409 |
| Ascended Heroes | pokemon_center_elite_trainer_box | 0.943182 | 0.977272 | -0.034091 |
| Temporal Forces | booster_box | 0.755411 | 0.704546 | 0.050866 |
| Temporal Forces | booster_bundle | 0.755411 | 0.928571 | -0.17316 |
| Temporal Forces | sleeved_booster_pack | 0.755411 | 0.633117 | 0.122294 |
| Mega Evolution | booster_box | 0.467533 | 0.522728 | -0.055195 |
| Mega Evolution | booster_bundle | 0.467533 | 0.428571 | 0.038961 |
| Mega Evolution | sleeved_booster_pack | 0.467533 | 0.451299 | 0.016234 |
| Obsidian Flames | booster_box | 0.181818 | 0.237013 | -0.055195 |
| Obsidian Flames | booster_bundle | 0.181818 | 0.25 | -0.068182 |
| Obsidian Flames | sleeved_booster_pack | 0.181818 | 0.058442 | 0.123376 |
| White Flare | booster_bundle | 0.458333 | 0.4375 | 0.020833 |
| White Flare | elite_trainer_box | 0.458333 | 0.4375 | 0.020833 |
| White Flare | pokemon_center_elite_trainer_box | 0.458333 | 0.5 | -0.041667 |
| Twilight Masquerade | booster_box | 0.549783 | 0.61039 | -0.060606 |
| Twilight Masquerade | booster_bundle | 0.549783 | 0.642857 | -0.093074 |
| Twilight Masquerade | sleeved_booster_pack | 0.549783 | 0.396103 | 0.15368 |
| Destined Rivals | booster_box | 0.432468 | 0.487013 | -0.054545 |
| Destined Rivals | booster_bundle | 0.432468 | 0.392857 | 0.03961 |
| Destined Rivals | elite_trainer_box | 0.432468 | 0.353085 | 0.079383 |
| Destined Rivals | pokemon_center_elite_trainer_box | 0.432468 | 0.478085 | -0.045617 |
| Destined Rivals | sleeved_booster_pack | 0.432468 | 0.451299 | -0.018831 |
| Surging Sparks | booster_box | 0.209957 | 0.172078 | 0.037879 |
| Surging Sparks | booster_bundle | 0.209957 | 0.178572 | 0.031385 |
| Surging Sparks | sleeved_booster_pack | 0.209957 | 0.27922 | -0.069264 |

# LEAVE-ONE-FAMILY-OUT STABILITY

| Omitted family | Overlap N | Spearman | Top-5 overlap | Mean abs movement | Max movement |
|---|---:|---:|---:|---:|---:|
| booster_box | 18 | 0.93808 | 5 | 1.333333 | 4 |
| booster_bundle | 18 | 0.909185 | 4 | 1.666667 | 4 |
| elite_trainer_box | 18 | 0.991744 | 5 | 0.444444 | 1 |
| enhanced_booster_box | 18 | 1.0 | 5 | 0.0 | 0 |
| half_booster_box | 18 | 1.0 | 5 | 0.0 | 0 |
| pokemon_center_elite_trainer_box | 18 | 0.975232 | 5 | 1.0 | 2 |
| sleeved_booster_pack | 18 | 0.882353 | 4 | 1.777778 | 6 |

# 189-CANDIDATE SENSITIVITY

All 189 pre-registered configurations remain in JSON. The reasonable-gate robustness subset contains 84 configurations and reports top-three/top-five frequencies for every set.

# PACK-RANKING COMPARISON

Descriptive only: overlap N=18, Spearman=0.420021, top-five overlap=3, mean absolute movement=5.888889, maximum movement=14.

# PROMOTION GATE

Methodology version: `set_rip_consensus_v1_mean_sku_mean_family_unshrunk_cov2_cohort3_missing_omit`

| Check | Observed | Required | Status |
|---|---|---|---|
| runAuthority | `{"matchRate": 1.0}` | `{"matchRate": 1.0}` | PASS |
| canonicalVersions | `{"matchRate": 1.0, "versions": {"collectorAppeal": "collector_appeal_v5_contextual_roster_h_only_d_baseline_up4_down2", "financialRip": "financial_rip_v3_outcome_profile_25_20_15_25_10_5", "overallRip": "overall_rip_v9_90_financial_v3_10_collector_appeal_v5"}}` | `{"matchRate": 1.0}` | PASS |
| setCoverage | `{"coverageRate": 0.818182, "rankableSetCount": 18, "rankedSetCount": 22}` | `{"minimumCoverageRate": 0.9, "minimumRankableSetCount": 20}` | FAIL |
| familyCohortQuality | `{"ineligibleParticipatingFamilies": []}` | `{"minimumRepresentedSets": 3, "sensitivityRepresentedSets": 5}` | PASS |
| deferredCoverage | `{"enhancedBoosterBoxRepresentedSets": 0, "expandedEtb": false, "expandedPokemonCenterEtb": false, "halfBoosterBox": false}` | `{"enhancedBoosterBox": "required only if >=3 represented sets", "expandedEtb": true, "expandedPokemonCenterEtb": true, "halfBoosterBox": "meaningful new artifact-backed coverage"}` | BLOCKED |
| leaveOneFamilyOutStability | `{"informativeOmissions": 5, "maximumIndividualRankMovement": 6, "maximumMeanAbsoluteRankMovement": 1.777778, "minimumSpearman": 0.882353, "minimumTop5Overlap": 4}` | `{"maximumIndividualRankMovement": 6, "maximumMeanAbsoluteRankMovement": 2.0, "minimumSpearman": 0.85, "minimumTop5Overlap": 4}` | PASS |
| representativeSensitivity | `{"comparisons": {"best": {"maximumRankMovement": 0, "meanAbsoluteRankMovement": 0.0, "overlapN": 18, "spearman": 1.0, "top3Overlap": 3, "top5Overlap": 5}, "coverage3": {"maximumRankMovement": 0, "meanAbsoluteRankMovement": 0.0, "overlapN": 18, "spearman": 1.0, "top3Overlap": 3, "top5Overlap": 5}, "familyCohort5": {"maximumRankMovement": 0, "meanAbsoluteRankMovement": 0.0, "overlapN": 18, "spearman": 1.0, "top3Overlap": 3, "top5Overlap": 5}, "groupBalanced": {"maximumRankMovement": 1, "meanAbsoluteRankMovement": 0.444444, "overlapN": 18, "spearman": 0.991744, "top3Overlap": 3, "top5Overlap": 5}, "median": {"maximumRankMovement": 0, "meanAbsoluteRankMovement": 0.0, "overlapN": 18, "spearman": 1.0, "top3Overlap": 3, "top5Overlap": 5}}, "warningComparisons": []}` | `{"bestAndMedianMinimumSpearman": 0.85, "bestAndMedianMinimumTop5Overlap": 4, "requiredDiagnostics": ["coverage3", "familyCohort5", "groupBalanced"]}` | PASS |
| familyCountFairness | `{"spearmanCoverageVsSetRip": -0.346658}` | `{"absoluteSpearmanReviewThreshold": 0.6}` | PASS |
| multiSkuInvariant | `{"oneVotePerSetFamily": true}` | `{"oneVotePerSetFamily": true}` | PASS |

Overall: **AWAITING_DEFERRED_COVERAGE**

# FROZEN BASELINE

As of 2026-08-17: 18 of 22 ranked sets clear the coverage gate. The full ordering and scores are recorded in JSON.

# POST-COVERAGE WORKFLOW

1. Rebuild normal product-family Rankings after normal artifact-backed simulations populate deferred products.
2. Run this same frozen research harness without changing its methodology version or gate constants.
3. Evaluate the pre-registered promotion gate.
4. Compare before/after family coverage and descriptive ranking movement.
5. Report PASS, FAIL, or REVIEW REQUIRED without changing methodology during the validation run.
6. Return results for human promotion review; the harness cannot publish or promote itself.

# HISTORICAL EVIDENCE

HISTORICAL_EVIDENCE_INSUFFICIENT

No stored historical product-family projections with current canonical model versions were found; historical Monte Carlo was not rerun.

# PRIOR RESEARCH INVALIDATION

INVALIDATED_BY_RUN_AUTHORITY_BUG

The prior numeric artifacts selected sealed-product runs through one market date instead of each ranked target's calculation_run_id. The pre-registered 189-configuration methodology is unchanged; all numeric findings were recomputed.

# KNOWN LIMITATIONS

- Half Booster Box and Enhanced Booster Box currently have no or insufficient canonical coverage.
- Verified deferred products are missing evidence, not poor performance.
- 18 sets currently clear the leading candidate's gate; this is research coverage, not a validated public Set RIP cohort.
- Related pack formats may count correlated evidence more than once; group-balanced results are retained as a sensitivity architecture.

# PROMOTION STATUS

AWAITING_DEFERRED_COVERAGE
