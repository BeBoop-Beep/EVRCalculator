# Best-Open Price — Bucket 1 prepared scorer and exact search

Date: 2026-09-13

Source: local `develop`; HEAD advanced externally during the study from
`6305d4c9` to `b087d535` while preserving the completed Bucket 0 work.
No branch operation, commit, database mutation, migration, API/frontend change,
or threshold publication was performed.

## Result

Bucket 1 passes. The prepared scorer preserved canonical Financial RIP V3/V4,
Overall RIP V12, and ranking-comparator behavior across the complete Bucket 0
real-data workload. Optimized search matched a brute-force cent oracle in 100
deterministic synthetic cases. All 10 representative production-data thresholds
won at `P*` and lost at `P* + 1 cent`.

The exact thresholds remain research artifacts only.

## Files changed

* `backend/calculations/evr/financial_rip_v3.py`
* `backend/calculations/evr/best_open_price.py` (new)
* `backend/db/services/budget_product_ranking_authority.py`
* `backend/scripts/research_best_open_price_bucket1.py` (new)
* `backend/tests/unit/calculations/test_prepared_financial_rip_and_best_open_price.py` (new)
* `docs/research/best_open_price_bucket1_results.json` (new)
* this report

Bucket 0 files and unrelated dirty-worktree files were preserved.

## Prepared canonical scorer architecture

`PreparedFinancialRipDistribution` represents one fixed physical distribution.
It validates and stably sorts once, then caches the outcome count, prefix sums,
mean/median, P05/P95/P99 values, rank-exact tail counts and aggregates, total
value, and distinct-count disclosure. Repeated costs use `searchsorted` for win,
loss, and hard-loss boundaries and a prefix-sum query for losing value.

Rank-defined top-1% and P95–P99 masses are unchanged. Percentiles use NumPy's
existing semantics and are cached once. A guaranteed scalar offset is carried
without allocating a second full shifted vector; boundary comparisons correct
for IEEE-754 addition/subtraction non-invertibility, and shifted distinct counts
are computed in bounded chunks. Only the small 1%/4% shifted tail slices are
temporarily materialized to preserve NumPy reduction semantics.

This is not a second Financial model. Raw and prepared callers enter the same
`build_financial_rip` canonical component normalization, weighting, disclosure,
and score-verification assembly. No weights, normalization anchors, percentile
rules, sampling, V4 projection, or V12 arithmetic were duplicated or changed.

One permitted numerical distinction was observed: a prefix-sum losing-value
query can differ from NumPy's pairwise slice reduction by `0.000001` in the
non-scoring `averageLosingReturnValue` disclosure. The validation gate requires
exact status, rankability, normalized scoring inputs, component/subcomponent
scores, headline V3/V4/V12 scores, and comparator output; non-scoring numeric
disclosures retain the repository's established `1e-6` tolerance.

## Historical source and real-data parity

* Source snapshot: `c8853793-a2ac-4a62-a9a4-f5df7f9ed8a1`
* Cohort fingerprint:
  `5a33b0fa18fba5d30a7caf366af9ff4d32d7797040562d6480760426a5d30b6b`
* Historical authority fingerprint:
  `5d12b32481819807989c597c50b0fbf49e2086dde5cf2fe943555d49b6cd3620`
* Authority fingerprint unchanged at completion.
* Historical parity: 1,000/1,000 whole snapshot and 138/138 Full Market.
* Published Full Market strategies checked: 138/138.
* Bucket 0 physical distributions checked: 446/446.
* Bucket 0 prices checked: 2,176/2,176.
* V4/V12 comparator evaluations checked: 2,176/2,176.
* Score or comparator mismatches: 0.

During validation, the historical simulation reader exposed a concrete paging
defect: ordering only by `sealed_product_id` is unstable because that product
has multiple historical calculation runs. Pagination now additionally orders
by calculation run and price date. This changes no source-authority rule and
the authority regression suite passes.

## Exact search contract

The internal method identity is
`budget_product_best_open_price_full_market_v1`.

Non-leaders search only at or below current market, downward in price/upward in
quantity. The current leader searches only at or above current market against
the persisted #2 competitor. The Full Market anchor and all competitor values
remain frozen.

All prices are integer cents and `q = floor(B/P)`. Quantity intervals use the
exact inclusive bounds `floor(B/(q+1))+1 .. floor(B/q)`. Quantity discovery is
exponentially bracketed and then exactly refined; it never starts by enumerating
`q=1..q0`. Within a quantity interval, sentinel monotonicity checks precede
binary cent search. An observed inversion triggers exact cent enumeration for
that interval. Every result is globally checked at `P*` and `P*+1 cent`, which
also verifies quantity-boundary transitions.

Physical/prepared distributions live in a product-local four-entry LRU. Score
evaluations remain lightweight. Cache eviction may rebuild a bracket quantity,
but memory no longer grows with the number of quantities or cohort size. A
q4096 construction guard returns explicit `unresolved_extreme_quantity`; it is
not a price floor and never fabricates a threshold.

## Brute-force oracle and regression tests

The optimized engine matched full allowed-domain cent enumeration in 100/100
seeded synthetic leader/non-leader cases. Tests also cover empty/non-finite
prepared inputs, guaranteed shifts, all Financial components through full
payload parity, V4/V12 parity, exact interval boundaries, direction constraints,
leader benchmark exclusion, quantity transitions, one-cent maximality,
repeatability, authority/version refusal, observed-monotonicity fallback, cache
identity/cleanup, and explicit extreme-quantity unresolved behavior.

Final focused regression run: 230 passed, 5 conditional tests skipped.

## Representative exact thresholds

Prices are integer cents. Every row has `P* wins = true` and
`P*+1 cent wins = false`.

| Rank | Current | P* | q(P*) | V12 at P* | Benchmark V12 | Evals | Distinct q | Seconds |
|---:|---:|---:|---:|---:|---:|---:|---:|---:|
| 1 | 1,324 | 1,496 | 90 | 49.6551 | 49.6548 | 17 | 8 | 6.11 |
| 2 | 1,457 | 1,323 | 102 | 54.6728 | 54.4250 | 56 | 12 | 12.64 |
| 10 | 31,486 | 24,641 | 5 | 54.4254 | 54.4250 | 22 | 2 | 0.25 |
| 69 | 37,228 | 19,482 | 6 | 54.4263 | 54.4250 | 31 | 5 | 0.66 |
| 104 | 9,055 | 4,079 | 33 | 54.4413 | 54.4250 | 108 | 21 | 6.97 |
| 15, cheapest/high-q | 515 | 367 | 367 | 54.6908 | 54.4250 | 150 | 107 | 265.77 |
| 80, expensive/low-q | 131,612 | 60,874 | 2 | 54.4260 | 54.4250 | 25 | 2 | 0.23 |
| 3, booster bundle | 9,062 | 7,941 | 17 | 54.4446 | 54.4250 | 21 | 5 | 1.06 |
| 4, guaranteed ETB | 15,023 | 13,107 | 10 | 54.4268 | 54.4250 | 25 | 3 | 0.50 |
| 7, booster box | 18,991 | 15,955 | 8 | 54.4269 | 54.4250 | 20 | 2 | 0.32 |

Three `P*+1 cent` checks crossed into the adjacent quantity interval and still
lost, directly covering the quantity-boundary exactness gate. Total sample
search time was 294.50 seconds with 475 evaluations. There were 183 physical
construction cache misses, 292 hits, and 167 distinct quantities; 16 quantities
were safely rebuilt after LRU eviction.

## Performance

| Measurement | Result |
|---|---:|
| Raw repeated scoring, 2,176 prices | 214.0103 s |
| Prepared repeated scoring, 2,176 prices | 0.5570 s |
| Repeated-price speedup | 384.22x |
| Quantity construction | 419.0268 s |
| Prepared representation creation | 61.6164 s |
| Published-strategy parity work | 13.8285 s |
| Full validation wall time | 758.3408 s |
| Python-traced peak | 1,328,691,288 bytes |
| Process peak working set | 1,441,095,680 bytes |

The required performance shape is demonstrated: physical quantity construction
is expensive, then repeated exact prices are cheap. Prepared evaluations no
longer sort or scan the million outcomes per price.

## Readiness and remaining risk

Full 138-product execution is correctness-safe as a read-only, offline,
one-product-at-a-time job: caches are bounded independently of cohort size,
authority/model mismatches fail closed, and the extreme guard returns unresolved
rather than an incorrect threshold. It is not yet proven operationally cheap.
The high-q sample alone required 265.77 seconds and 107 distinct quantity
distributions, and a product that does not win by q4096 remains explicitly
unresolved. Removing that barrier requires a correctness-preserving distribution
construction strategy, not a hidden price floor.

Proceed to Bucket 2 for full-cohort/offline orchestration and further quantity-
construction optimization if that is its intended scope. Do not begin Bucket 3
persistence until source-input binding, unresolved-state semantics, and the
offline full-cohort operational envelope are accepted. Do not use this work on
an HTTP request path.
