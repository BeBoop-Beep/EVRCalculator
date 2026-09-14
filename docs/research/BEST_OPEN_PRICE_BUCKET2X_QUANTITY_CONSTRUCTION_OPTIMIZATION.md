# Best-Open Price Bucket 2.x: Exact Quantity-Construction Optimization

## Decision

`READY_FOR_BUCKET_3_PERSISTENCE`

The optimized offline engine reproduced all 138 Bucket 2 reference thresholds and exactness payloads, passed the required deterministic replay, reduced measured full-cohort wall time from 16,378.24 seconds to 3,875.04 seconds (4.23x), removed the multi-hour SKU tail, and remained bounded at a 577.12 MiB peak working set. The slowest optimized product took 175.75 seconds and replayed in 188.69 seconds.

This approval applies only to a future asynchronous prepared-data publication. Normal request paths must perform zero threshold simulation. Bucket 3 was not implemented here.

## Source and scope

- Local branch: `develop`
- Source commit: `25e105ebe4feeb85188695444cacfb56d74550e0`
- Source snapshot: `c8853793-a2ac-4a62-a9a4-f5df7f9ed8a1`
- Cohort fingerprint: `5a33b0fa18fba5d30a7caf366af9ff4d32d7797040562d6480760426a5d30b6b`
- Historical authority fingerprint: `5d12b32481819807989c597c50b0fbf49e2086dde5cf2fe943555d49b6cd3620`
- Authority unchanged at completion
- Full Market budget frozen at $1,350
- Execution remained local, sequential, and read-only

No branch operation, commit, database write, migration, publication, persistence, API, or frontend change was performed. Unrelated dirty-worktree files were preserved.

## Phase 0: 8,993s versus 372s variance

An isolated legacy rerun persisted the missing full replay diagnostics. Every algorithmic field matched the original:

| Diagnostic | Original | Isolated legacy replay |
| --- | ---: | ---: |
| Current / threshold quantity | 198 / 365 | 198 / 365 |
| Minimum / maximum inspected | 198 / 454 | 198 / 454 |
| Unique quantities | 169 | 169 |
| Bracket expansions | 9 | 9 |
| Refinement quantities | 168 | 168 |
| Candidate-price evaluations | 314 | 314 |
| Cache hits / misses / evictions | 137 / 177 / 173 | 137 / 177 / 173 |
| Distribution construction | 8,976.360s | 359.066s |
| Prepared construction | 16.848s | 17.285s |
| Search wall time | 8,993.512s | 376.667s |

Classification: **B — identical work with radically different per-distribution runtime**. The exact quantity vector, path, evaluation count, and cache activity were identical. Stable prepared-construction time and fresh product-local state rule out a different search path and cache contamination. The variance is isolated to repeated physical construction. Available process RSS/pagefile samples cannot distinguish scheduling, thermal throttling, or system pagefile contention as the environmental trigger, so no narrower environmental cause is claimed.

The prior Bucket 2 report incorrectly called all 177 cache misses distinct quantities. The artifact shows 169 unique quantities and eight rebuilds; that wording was corrected.

## Bootstrap and RNG audit

The existing Stage 1 MULTI builder is not independent-SINGLE invariant. In a production-vector example, requesting quantities `[198, 205]` changed the quantity-198 vector relative to requesting `[198]`: maximum absolute row delta was $1,337.86, V3 moved -0.0017, V4 moved +0.0002, and V12 moved +0.0002. It is therefore not used by Best-Open Price batching.

The pinned NumPy generator's flattened integer stream was exact across tested 1-D/2-D shapes and call boundaries for seeds 1, 2, and 99; outcome counts 7, 101, 4,097, and 25,001; quantities through 129; and chunk sizes from 1 through 25,000. Production-like million-outcome tests were also exercised by the cohort run.

## Exact optimized construction

`build_single_q_parity_distributions` initializes the canonical seed once per bounded quantity block and consumes the common flattened stream through `N * max(q)`. For each q it uses exactly the first `N*q` sampled outcomes, groups them into the same consecutive q-sized rows as SINGLE, and calls the same NumPy `sum(axis=1)` reduction. It does not use the existing MULTI common-random-number reshape.

This changes RNG/gather work from `N * sum(q_i)` to `N * max(q_i)` per block while retaining the original row-reduction order. On real quantities 198-205:

| Measure | Legacy SINGLE calls | Exact flat batch |
| --- | ---: | ---: |
| Construction seconds | 11.845 | 4.491 |
| Speedup | 1x | 2.64x |
| Bitwise-equal vectors | — | 8/8 |
| Maximum outcome delta | — | 0.0 |
| V3 / V4 / V12 / comparator delta | — | 0 / 0 / 0 / 0 |
| Estimated batch construction bytes | — | 96,000,000 |

At widths 16 and 24, bitwise-exact construction speedups were 2.94x and 3.22x. Full-cohort quantity construction improved from 14,993.23 seconds to 2,714.55 seconds (5.52x) because batching eliminated 902.82 billion redundant RNG draws: 945.93 billion legacy-equivalent versus 43.11 billion effective draws.

### Rejected cumulative-sum direction

A cumulative-endpoint prototype was 5.99x faster on the eight-quantity interval, but changed outcome vectors by up to `1.3352e-7` and changed canonical V3 scores by as much as 0.0004. It failed the numerical gate and was removed from the implementation. No threshold result relies on it.

## Exact refinement and bounded memory

Exponential quantity bracketing is unchanged. Once the fail/win range is known, quantities are still evaluated in exact ascending order; no quantity-monotonicity theorem or binary search was introduced. The only change is that required quantities are physically generated in bounded blocks of at most 24.

Before allocation, the runner auto-tunes requested batch width from outcome count, the maximum allowed quantity, and the 256 MiB ceiling. The builder then accounts for all float64 output vectors and its shared int64-index, float64-sample, and possible transient combine workspace. Flat work chunks are capped at two million draws. A ceiling that cannot fit one output plus a complete maximum-q row fails before allocation and the search layer falls back to canonical independent SINGLE construction if any batch invariant fails. Audit after the measured run found that its row-level estimator omitted the transient combine buffer; the implementation is corrected to 24 bytes per flat draw. The corrected maximum for the measured width-24 allocation is 240,000,000 bytes (228.88 MiB); observed process RSS is the authoritative run measurement.

At most 24 not-yet-consumed prepared candidates exist in a transient block and the persistent product-local LRU remains capped at four. Pending entries are consumed in ascending-q order and the block is released immediately. No memmap or temporary disk is used, so temporary disk bytes are zero and there is no interruption-cleanup artifact.

| Memory measure | Bucket 2 | Bucket 2.x |
| --- | ---: | ---: |
| Baseline RSS | 103.35 MiB | 104.00 MiB |
| Peak working set | 439.11 MiB | 577.12 MiB |
| Final RSS | 94.91 MiB | 97.25 MiB |

The 31% peak increase remains in the same sub-gigabyte safe class, and final RSS returned to baseline rather than growing with cohort progress.

## Full 138-product replay

Every product was compared fail-closed to `best_open_price_bucket2_results.json`.

| Gate | Result |
| --- | ---: |
| Attempted / resolved / unresolved | 138 / 138 / 0 |
| Same status | 138/138 |
| Same Best-Open Price cent | 138/138 |
| Same threshold quantity | 138/138 |
| Same benchmark identity | 138/138 |
| Same exactness payload, including P* and P*+1 cent | 138/138 |
| Batch invariant fallbacks | 0 |
| Deterministic subset | 6/6 matched |

No source-authority, Financial V3/V4, V12, comparator, integer-cent, or maximality semantics changed.

## Runtime

| Phase | Seconds | % of wall |
| --- | ---: | ---: |
| Source/authority loading | 0.709 | 0.018% |
| Pack artifacts | 147.460 | 3.805% |
| Base distributions | 10.751 | 0.278% |
| Quantity distributions | 2,714.553 | 70.052% |
| Prepared scorers | 626.618 | 16.171% |
| Candidate scoring | 2.044 | 0.053% |
| Comparator | 0.161 | 0.004% |
| Exactness checks | 0.0005 | <0.001% |
| Cleanup | 2.597 | 0.067% |
| Checkpoint serialization | 16.213 | 0.418% |
| Full wall time, including deterministic replay | 3,875.042 | 100% |

Full wall-clock speedup is 4.23x. This is slightly below the aspirational roughly-5x target but is material: the job fell from 4h33m to 1h05m and the multi-hour single-SKU failure mode disappeared.

| Product runtime statistic | Seconds |
| --- | ---: |
| Fastest | 0.326 |
| Median | 3.529 |
| P95 | 111.488 |
| Slowest | 175.755 |

The slowest ten were 105-176 seconds. The worst optimized deterministic replay was 188.693 seconds, a stable minutes-scale result rather than an hours-scale tail.

Runtime classification: **acceptable for a sequential post-publication offline job**, with a remaining opportunity to reduce exact row reductions and excess preparation in partially consumed final blocks. It remains categorically unsuitable for request-time calculation.

## Batch and LRU behavior

- Quantity batches: 294
- Quantities generated in batches: 5,683
- Batch fallbacks: 0
- Effective RNG draws: 43.106 billion
- Legacy-equivalent RNG draws: 945.925 billion
- LRU hits / misses / evictions: 19,189 / 6,395 / 5,159
- Maximum persistent cached prepared distributions: 4
- Maximum transient pending block: 24
- Corrected maximum estimated construction block: 228.88 MiB

The LRU still captures repeated bracket and exactness evaluations and remains useful. Misses increased because a bounded final batch can generate quantities beyond the first winner, but this is controlled work and does not alter evaluation order or threshold results.

## Tests and remaining risks

Focused coverage includes RNG shape/call-boundary parity, exact multiple-q vectors, high-q and chunk-boundary cases, guaranteed-component and Financial payload parity, memory-ceiling refusal, exact refinement order, bounded pending/cache residency, product-state isolation, and legacy fallback. The complete Bucket 0/1/2, Financial, V12, ranking, Chase-authority, and publication-readiness regression matrix passed: **315 passed, 5 conditional skips**.

Remaining risks:

- Runtime still depends on memory bandwidth and exact row reductions; 4.23x is below the preferred 5x full-wall target.
- The old 24x timing anomaly's environmental trigger is not identifiable from historical process counters, although the algorithmic-work cause is conclusively excluded.
- NumPy RNG stream shape/call invariance is pinned-runtime evidence, not a promise across arbitrary future NumPy versions. Dependency upgrades must rerun the parity tests.
- Batch width 24 is a conservative measured policy for million-outcome vectors. A future outcome-count change must continue to honor the explicit memory estimator rather than reuse the width blindly.

These are operational monitoring concerns, not blockers to an offline persisted-preparation design.

## Files

- `backend/calculations/evr/sealed_product_distribution.py`
- `backend/calculations/evr/best_open_price.py`
- `backend/scripts/research_best_open_price_bucket2.py`
- `backend/tests/unit/calculations/test_best_open_price_quantity_batch.py`
- `backend/tests/unit/scripts/test_research_best_open_price_bucket2.py`
- `docs/research/best_open_price_bucket2x_results.json`
- `docs/research/best_open_price_bucket2x_phase0_legacy.json`
- this report

No Bucket 3 implementation was started.
