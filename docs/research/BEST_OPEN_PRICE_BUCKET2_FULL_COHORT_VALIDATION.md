# Best-Open Price Bucket 2: Full-Cohort Validation

## Decision

`NOT_READY_FOR_BUCKET_3_PERSISTENCE`

The exact method is correct for the full authority cohort, deterministic for the required replay subset, and bounded in memory. It is not operationally ready: the successful invocation took 16,378.24 seconds (4 h 32 m 58 s), 91.54% of wall time was physical quantity-distribution construction, and one ordinary sleeved booster required 169 distinct quantities (177 constructions including rebuilds) and 8,993.51 seconds. Even its replay required 371.94 seconds. This is a real exhaustive quantity-refinement path, not prepared price-scoring cost.

Bucket 2.x should remove or safely bound repeated physical distribution construction before any persistence work. Bucket 3 must not start from this result.

## Authority and scope

- Local branch: `develop`
- Source commit: `25e105ebe4feeb85188695444cacfb56d74550e0`
- Source snapshot: `c8853793-a2ac-4a62-a9a4-f5df7f9ed8a1`
- Cohort fingerprint: `5a33b0fa18fba5d30a7caf366af9ff4d32d7797040562d6480760426a5d30b6b`
- Historical source-authority fingerprint: `5d12b32481819807989c597c50b0fbf49e2086dde5cf2fe943555d49b6cd3620`
- Full Market budget: $1,350, frozen throughout counterfactual scoring
- Products/sets: 138 / 22
- Authority fingerprint at completion: unchanged
- Execution: sequential, read-only, product-local search state; no database writes, publication, migrations, API/frontend work, branch operations, or commits

The worktree contained unrelated in-progress index-fair-value and log changes. They were preserved and excluded from this work.

## Exact full-cohort result

| Measure | Result |
| --- | ---: |
| Attempted | 138 |
| Resolved | 138 |
| Unresolved | 0 |
| `resolved_below_market` | 137 |
| `current_number_one_with_headroom` | 1 |
| `resolved_at_market` / other statuses | 0 |
| Threshold cent is canonical #1 | 138 / 138 |
| Next cent is not canonical #1 | 138 / 138 |
| Recorded threshold quantity matches `floor(135000 / P*)` | 138 / 138 |
| Positive integer-cent thresholds | 138 / 138 |
| Search errors / fallbacks | 0 / 0 |
| Next-cent quantity-boundary cases explicitly checked | 19 |

Every resolved row preserves the frozen published competitor set and canonical comparator, including tie-breaks. No row was accepted merely because the search returned a value: `P*` and `P* + $0.01` were evaluated explicitly. No non-leader domain-edge exception was needed because every non-leader resolved below market.

The runner constructs a fresh artifact/base distribution, exact-search engine, prepared candidates, and four-entry cache for each product. It releases these before advancing. There is no shared mutable search engine or distribution cache across products.

## Price-gap research

The leader is excluded from discount statistics because its -12.99% signed gap denotes price headroom, not a discount.

| Non-leader statistic | Result |
| --- | ---: |
| P25 required discount | 38.35% |
| Median required discount | 46.02% |
| P75 required discount | 54.95% |
| Largest required discount | 78.83% |
| Under 5% | 0 |
| Under 10% | 1 |
| Under 20% | 5 |
| 20% through 40% | 36 |
| Over 40% | 96 |

The under-10% and under-20% figures are cumulative, matching their labels. Current rank and required discount are strongly related (Pearson correlation 0.953974). Median gaps by rank band rise from 15.99% for ranks 2-10 to 31.79% (11-25), 38.84% (26-50), 45.65% (51-75), 51.12% (76-100), and 59.44% (101-138).

Family medians were 39.34% for booster boxes, 51.91% for booster bundles, 54.53% for elite trainer boxes, 32.51% for enhanced booster boxes, 56.89% for half booster boxes, 41.93% for loose booster packs, 44.39% for Pokemon Center elite trainer boxes, and 50.14% for sleeved booster packs. The JSON artifact contains all 22 per-set breakdowns.

## Quantity behavior

Quantity delta was positive for all 137 non-leaders and negative only for the leader headroom case. Across all rows its minimum/P25/median/P75/maximum was -11 / 4 / 11 / 33.25 / 200.

The search remained logically bounded and never hit an extreme-quantity guard. The largest inspected quantity was 652. However, logical termination did not imply acceptable computational cost. Chaos Rising Sleeved Booster Pack refined through 169 unique quantities (198 through the threshold region at 365 plus the outer bracket), with 177 constructions including rebuilds and 168 bracket refinements. This is the hidden exhaustive behavior that blocks production readiness.

## Performance

The successful checkpoint-resumed invocation measured 16,378.24 seconds. An earlier attempt completed the first five products before a transient read-only artifact-load statement timeout; the resumed invocation reused those checkpoint rows. Their per-product phase measurements are included below, but the roughly 21 seconds initially spent searching those five rows is not duplicated in the successful invocation's wall clock.

| Phase | Seconds | % of successful wall |
| --- | ---: | ---: |
| Source/authority loading | 6.628 | 0.0405% |
| Pack-artifact loading | 193.745 | 1.1829% |
| Base-distribution construction | 10.309 | 0.0629% |
| Physical quantity-distribution construction | 14,993.226 | 91.5436% |
| Prepared-scorer construction | 548.578 | 3.3494% |
| Candidate price scoring | 2.418 | 0.0148% |
| Comparator work | 0.187 | 0.0011% |
| Exactness verification | 0.0002 | <0.0001% |
| Cleanup | 2.725 | 0.0166% |
| Artifact serialization/checkpointing | 0.576 | 0.0035% |

The percentages do not sum to 100% because deterministic replay orchestration, Python/runtime overhead, garbage collection, and resumed-run bookkeeping are outside the individually accumulated phases. Bucket 1's prediction is confirmed: prepared candidate scoring is negligible. The bottleneck is generating physical distributions at many quantities.

Slowest original searches:

| Rank | Product | Seconds | Maximum quantity inspected |
| ---: | --- | ---: | ---: |
| 86 | Chaos Rising Sleeved Booster Pack | 8,993.512 | 454 |
| 102 | Journey Together Sleeved Booster Pack | 394.472 | 401 |
| 81 | Perfect Order Sleeved Booster Pack | 389.302 | 438 |
| 43 | Journey Together Booster Pack | 324.710 | 454 |
| 132 | Surging Sparks Sleeved Booster Pack | 295.276 | 368 |
| 15 | Perfect Order Booster Pack | 272.305 | 390 |
| 21 | Chaos Rising Booster Pack | 265.243 | 390 |
| 111 | Scarlet & Violet Sleeved Booster Pack | 260.137 | 377 |
| 105 | Paradox Rift Sleeved Booster Pack | 257.011 | 371 |
| 84 | Mega Evolution Sleeved Booster Pack | 229.081 | 652 |

The rank-86 replay matched exactly but took 371.943 seconds rather than 8,993.512 seconds. This large timing variance does not rescue readiness: the replay is still over six minutes for one SKU, and it makes recurring-job duration less predictable.

Runtime classification: **unacceptable** for a recurring production publication job. A full result can be produced offline, but its duration, pathological tail, and exhaustive refinement behavior violate the production-readiness gate.

## Memory and LRU

| Measure | Result |
| --- | ---: |
| Baseline RSS after authority load | 103.35 MiB |
| Cohort-wide peak working set | 439.11 MiB |
| Final RSS after cleanup | 94.91 MiB |
| First-quartile median post-cleanup RSS | 107.66 MiB |
| Last-quartile median post-cleanup RSS | 88.56 MiB |
| Peak pagefile bytes observed | 1,177.59 MiB |
| Final pagefile bytes | 864.29 MiB |

RSS did not grow monotonically; final RSS was below both baseline and early steady state. Peak working set was also well below Bucket 1's 1.44 GB measurement. The observed shape supports bounded product-local reuse. Windows process pagefile counters were sampled safely; no destructive or privileged OS probing was used, so these counters should not be interpreted as direct proof of system-wide page faults or swap pressure.

| Four-entry LRU measure | Result |
| --- | ---: |
| Insertions / misses | 5,689 |
| Hits | 14,212 |
| Evictions | 5,158 |
| Hit share of lookups | 71.41% |
| Maximum resident large distributions | 4 |

Hits correspond to repeated bracket endpoints and adjacent exactness evaluations, so the cache captures actual bracket locality. It is useful and bounded, but it cannot compensate for searches that must construct a long run of unique quantities.

## Leader audit

Ascended Heroes Booster Pack is the current #1 at $13.24, quantity 101, and V12 54.4250. Its frozen #2 benchmark is Prismatic Evolutions Booster Pack at V12 49.6548. It remains #1 through $14.96, giving $1.72 or 12.99% headroom. At that threshold it buys quantity 90 and scores V12 49.6551.

At $14.97 the quantity remains 90, but the candidate loses. Therefore the loss is same-quantity score deterioration, not a quantity decrement boundary or a tie-break.

## Representative research/video cases

- Smallest realistic discount: rank 2 Prismatic Evolutions Booster Pack, $14.57 to $13.23 (9.20%), quantity 92 to 102; the next cent crosses a quantity boundary.
- Current leader headroom: Ascended Heroes Booster Pack, $13.24 to $14.96 (+$1.72 / +12.99% headroom).
- Mid-ranked threshold: rank 75 Surging Sparks Booster Box, $305.33 to $164.83 (46.02%), quantity 4 to 8.
- Pathological search and dramatic boundary: rank 86 Chaos Rising Sleeved Booster Pack, $6.81 to $3.69 (45.81%), quantity 198 to 365.
- Largest quantity delta: rank 102 Journey Together Sleeved Booster Pack, $9.30 to $3.91 (57.96%), quantity 145 to 345 (+200), with a next-cent quantity boundary.
- Largest required discount: rank 138 Journey Together Half Booster Box, $333.33 to $70.56 (78.83%), quantity 4 to 19.

These are descriptive research facts only; no new scoring component or public label is implied.

## Determinism

Six required subset roles were replayed: leader, fastest, slowest, highest-quantity/cheapest-domain representative, guaranteed-component representative, and deterministic hash-selected SKU. All 6/6 matched for threshold cents, status, threshold quantity, V4, V12, capital-recovery chance, and benchmark identity. The complete artifact records original and replay timings and identities.

## Production execution design

A future publication remains an asynchronous prepared-data job: normal requests must read persisted thresholds and perform zero simulation. Before persistence, Bucket 2.x should focus narrowly on quantity construction:

1. Profile the pathological sleeved/loose pack distributions at the quantity-transition level and explain the 24x original/replay variance.
2. Replace linear refinement across quantity intervals with a correctness-preserving method that avoids constructing every intervening physical distribution.
3. Retain the exact canonical comparator and mandatory `P*`/`P*+1` verification.
4. Retain sequential product isolation and the four-entry LRU unless new measurements justify a different bound.
5. Re-run the same 138-product artifact and deterministic subset, then define a recurring-job target from stable repeated measurements.

No persistence schema, RPC, publication orchestration, or request-path implementation is justified yet.

## Deliverables

- `backend/calculations/evr/best_open_price.py`: non-semantic execution diagnostics for timing, bracketing, fallback, and cache residency.
- `backend/scripts/research_best_open_price_bucket2.py`: read-only checkpointed full-cohort runner with authority checks, memory sampling, exactness diagnostics, analysis, and deterministic replay.
- `backend/tests/unit/scripts/test_research_best_open_price_bucket2.py`: focused runner status/discount-analysis tests.
- `docs/research/best_open_price_bucket2_results.json`: complete 138-row result and diagnostics artifact.
- `docs/research/BEST_OPEN_PRICE_BUCKET2_FULL_COHORT_VALIDATION.md`: this report.

The completion token is intentionally withheld because offline execution characteristics are unacceptable and hidden exhaustive quantity refinement reappeared. Correctness, authority, determinism, and memory gates passed; the runtime gate did not.
