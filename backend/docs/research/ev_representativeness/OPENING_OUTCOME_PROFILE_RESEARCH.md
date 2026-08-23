# Opening Outcome Profile Research

## 1. Research Question

How frequently do modeled Pokémon openings land in different economic outcome ranges?

## 2. Methodology

The study uses the exact persisted one-million-outcome artifact for each of 22 sets on 2026-08-22. Every outcome is normalized by the same run's opening cost. Buckets use `[floor, ceiling)` semantics and the final bucket is open-ended. No resimulation or repricing produced the public one-pack results.

## 3. Candidate Bucket Schemes

| Scheme | Buckets | Near-empty bucket cells (<1%) | Mean cross-set bucket variance |
|---|---:|---:|---:|
| A | 8 | 28 | 0.007043 |
| B | 9 | 49 | 0.006258 |
| C | 5 | 2 | 0.011296 |
| D | 6 | 17 | 0.000356 |

Scheme A preserves useful resolution around half-cost and break-even while retaining interpretable 1.5×, 2×, and 5× tails. Scheme B adds near-break-even detail but creates more sparse cells; C is easier but hides material middle-distribution differences. D is useful for validating Financial RIP concepts but would blur descriptive and evaluative contracts.

## 4. Selected Public Bucket Scheme

`opening_outcome_profile_v1` uses: 0–25%, 25–50%, 50–75%, 75–100%, 1–1.5×, 1.5–2×, 2–5×, and 5×+. Numeric ranges are primary; neutral explanatory copy avoids implying realized profit.

## 5. Cohort Results

| Set | <25% | <50% | <75% | ≥cost | ≥2× | ≥5× |
|---|---:|---:|---:|---:|---:|---:|
| chaosRising | 60.9% | 83.1% | 90.0% | 6.5% | 1.9% | 1.1% |
| twilightMasquerade | 62.7% | 81.3% | 88.0% | 7.8% | 3.0% | 1.1% |
| scarletAndViolet151 | 77.5% | 84.8% | 88.5% | 9.6% | 6.0% | 0.5% |
| prismaticEvolutions | 86.5% | 93.9% | 95.8% | 3.2% | 2.3% | 1.1% |
| whiteFlare | 83.3% | 87.5% | 88.2% | 9.2% | 3.3% | 0.8% |
| scarletAndVioletBase | 76.0% | 85.9% | 88.3% | 8.4% | 4.0% | 0.7% |
| phantasmalFlames | 82.1% | 92.4% | 96.2% | 3.6% | 0.9% | 0.3% |
| surgingSparks | 71.6% | 86.6% | 90.6% | 7.1% | 2.0% | 0.6% |
| shroudedFable | 76.3% | 85.2% | 88.8% | 10.1% | 5.6% | 0.6% |
| perfectOrder | 48.6% | 82.6% | 90.2% | 7.6% | 3.2% | 1.1% |
| paradoxRift | 75.2% | 87.2% | 89.3% | 9.1% | 4.8% | 1.3% |
| blackBolt | 84.8% | 87.6% | 89.3% | 8.6% | 3.5% | 0.6% |
| ascendedHeroes | 54.9% | 84.7% | 93.8% | 4.3% | 2.9% | 1.3% |
| obsidianFlames | 82.3% | 88.6% | 92.6% | 6.5% | 2.5% | 0.5% |
| megaEvolution | 71.3% | 87.2% | 91.2% | 5.9% | 3.0% | 0.8% |
| journeyTogether | 18.2% | 81.3% | 89.4% | 7.6% | 4.0% | 1.0% |
| temporalForces | 70.6% | 83.4% | 88.0% | 10.2% | 5.6% | 1.3% |
| stellarCrown | 73.7% | 87.4% | 91.6% | 5.6% | 1.9% | 1.4% |
| pitchBlack | 25.6% | 80.8% | 87.3% | 9.3% | 3.5% | 1.3% |
| destinedRivals | 78.1% | 88.2% | 92.5% | 6.1% | 3.2% | 1.1% |
| paldeanFates | 80.8% | 91.7% | 95.3% | 3.6% | 1.5% | 0.6% |
| paldeaEvolved | 83.9% | 87.9% | 90.1% | 7.4% | 4.0% | 0.6% |

## 6. Severe Loss

Across the cohort, mean probability below 25% of cost is 69.3%; below half cost is 86.3%.

## 7. Near-Break-Even

The 75–100% mutually exclusive band is retained because it distinguishes near-cost outcomes without describing gross card value as profit.

## 8. Positive Outcomes

Mean same-run probability of returning at least opening cost is 7.1%.

## 9. Extreme Outcomes

Mean probabilities are 3.3% at 2×+ and 0.9% at 5×+.

## 10. Financial RIP Relationship

| Threshold | Pearson | Spearman | Bootstrap 95% Spearman CI | Permutation p |
|---|---:|---:|---|---:|
| lt25 | -0.576 | -0.675 | [-0.825, -0.399] | 0.001 |
| lt50 | -0.876 | -0.848 | [-0.947, -0.609] | 0.000 |
| lt75 | -0.869 | -0.798 | [-0.924, -0.543] | 0.000 |
| ge100 | 0.814 | 0.762 | [0.506, 0.881] | 0.000 |
| ge150 | 0.748 | 0.737 | [0.452, 0.884] | 0.000 |
| ge200 | 0.697 | 0.671 | [0.341, 0.848] | 0.000 |
| ge500 | 0.488 | 0.491 | [0.042, 0.830] | 0.019 |

These are validation relationships only. Financial RIP was not changed; direct use of its hard-loss and true-win inputs means some association is expected and adding the same thresholds to its score would risk double counting.

## 11. EV Representativeness Relationship

The machine-readable companion contains Pearson, Spearman, bootstrap intervals and permutation p-values for every cumulative threshold against Typical Capture, top-1% EV share, R80, confirmed convergence and CV. Outcome structure provides the middle-distribution detail that top-1% concentration alone cannot encode.

## 12. Natural Product Quantities

One-pack results are exact. The 6/9/11/18/36 research profiles use 25,000 seeded independent empirical sessions per set. Loss mass generally contracts toward the mean as N grows; this is research-only and not a product-opening guarantee.

## 13. Archetype Exploration

With only 22 sets, hard public archetypes are not defensible. The continuous bucket vector is more honest than unstable cluster labels; clustering should remain exploratory until the longitudinal sample is larger.

## 14. Temporal Baseline

The historical export contains 88 exact-run observations across four dates. It supports tracking which distribution regions move when EV changes without mixing runs.

## 15. Limitations

- Gross modeled card market value; selling fees, grading costs and liquidity are excluded.
- Independent pack assumptions apply to multi-pack research.
- Results depend on simulation validity and same-run market prices.
- The current set-level cohort is only 22 sets and four historical dates.
- Multi-pack research is seeded empirical sampling; public one-pack buckets are exact counts.

## 16. Product Recommendation

Use mutually exclusive buckets as the primary visual distribution because they sum to 100%. Add four cumulative callouts—under 50%, at least cost, at least 2× and at least 5×—because they answer distinct consumer questions without repeating every boundary. Extend to product RIP only after exact product artifact and market-cost provenance are uniformly available. Keep clustering, conditional loss severity, sensitivity grids, inferential statistics and multi-pack profiles research-only for now.

Research runtime: 40.53s; mean exact artifact/profile load: 0.645s per set.

## Appendix A. Threshold Sensitivity

| Threshold | Cohort mean | Cross-set SD |
|---:|---:|---:|
| 0.2× | 54.7% | 25.9% |
| 0.25× | 69.3% | 17.8% |
| 0.3× | 77.6% | 8.9% |
| 0.4× | 83.6% | 4.3% |
| 0.5× | 86.3% | 3.4% |
| 0.6× | 88.5% | 2.9% |
| 0.75× | 90.7% | 2.6% |
| 0.8× | 91.2% | 2.5% |
| 0.9× | 92.1% | 2.3% |
| 1.25× | 5.6% | 1.6% |
| 1.5× | 4.7% | 1.6% |
| 2× | 3.3% | 1.3% |
| 3× | 2.0% | 0.8% |
| 5× | 0.9% | 0.3% |
| 10× | 0.4% | 0.2% |

Nearby thresholds change absolute probabilities smoothly; V1 keeps explicit numeric edges so future revisions cannot silently change meaning.

## Appendix B. Temporal Distribution Candidates

Across 66 consecutive transitions, the deliberately sign-only exploratory screen found 5 distributed-appreciation candidates and 5 tail-driven candidates. These labels are not public classifications and need the planned 60–90 day observation period.
