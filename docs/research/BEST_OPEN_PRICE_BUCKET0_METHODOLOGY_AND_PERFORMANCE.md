# Best-Open Price — Bucket 0 methodology and performance

Date: 2026-09-13

Source commit: `6305d4c9` (`develop`, local worktree)

Research method: `budget_product_best_open_price_full_market_v1_research`

Result artifact: `docs/research/best_open_price_bucket0_results.json`

## Result

Bucket 0 passes its corrected source-authority, parity, bounded-performance,
fixed-quantity monotonicity, and representative quantity-discontinuity gates.
No threshold was published and bounded candidates are not exact threshold claims.

Bucket 1 is safe to begin specifically for a prepared canonical Financial
scorer and exact, direction-aware threshold-search infrastructure. The measured
memory and runtime prohibit promoting this research harness itself into a
synchronous production path.

## Two distinct source-authority use cases

For a **new ranking publication**, the authority remains
`pokemon_set_chase_accessibility_snapshot_latest`. New publications must retain
the exact set, calculation-run, model-version, transform-version, and mapped-HC-
mass coherence gates. This research change does not weaken that path.

For reconstruction of an **already-published historical V12 ranking**, the
authority is the input persisted with that publication. The script reads
`budget_product_ranking_rows.chase_accessibility_raw`, requires one non-null raw
value and one `source_calculation_run_id` per set, and requires every Full Market
product to carry the raw value. It does not ask today's mutable latest Chase
table to reproduce a historical run. A present-day `stale_calculation_run` is
therefore not grounds to reject a complete historical publication.

The publication architecture can replace rows under an existing snapshot ID.
The script consequently fingerprints the exact currently persisted historical
authority and re-reads it after the benchmark. This is research reproducibility,
not a claim that the base snapshot is physically immutable forever. Bucket 3
must bind or preserve production threshold source inputs independently.

## Pinned historical authority

* Snapshot: `c8853793-a2ac-4a62-a9a4-f5df7f9ed8a1`
* Market/pinned price date: `2026-09-08`
* Full Market budget: `$1,350.00`
* Cohort: 138 SKUs / 22 sets
* Source cohort fingerprint:
  `5a33b0fa18fba5d30a7caf366af9ff4d32d7797040562d6480760426a5d30b6b`
* Historical source-authority fingerprint:
  `5d12b32481819807989c597c50b0fbf49e2086dde5cf2fe943555d49b6cd3620`
* Overall RIP:
  `overall_rip_v12_86_financial_v4_04_chase_accessibility_v1_10_collector_appeal_v5`
* Chase Accessibility:
  `chase_accessibility_v1_hc_value_squared_modeled_probability`
* Chase transform:
  `chase_accessibility_overall_score_v1_saturating_k002`
* `ranked_under_v12_authority = true`
* Start/end authority fingerprints matched.

The fingerprint is SHA-256 over canonical JSON for the sorted 22-set tuples of
snapshot ID, cohort fingerprint, set ID, source calculation run ID, normalized
raw Chase value, Chase version, transform version, and Overall V12 version.

## Historical V12 parity

The harness calls canonical `compute_overall_rip_v12`; it does not duplicate the
formula. Under its four-decimal score contract:

* Entire persisted snapshot: 1,000/1,000 reconstructed, 0 mismatches, maximum
  absolute delta 0.
* Full Market: 138/138 reconstructed, 0 mismatches, maximum absolute delta 0.
* Full Market raw coverage: 138/138 products, 22/22 sets.
* Every set had exactly one normalized persisted raw value and exactly one
  source calculation run.

## V1 metric semantics

For a non-leading product, Best-Open Price asks how cheap it must become to
reach rank #1. Production search must constrain candidate price to
`candidate_price <= current_market_price`, moving downward in price and upward
in quantity.

For the current rank #1 product, it asks how expensive the product can become
while remaining #1. This is the only V1 public-threshold case that searches
`candidate_price > current_market_price`, moving upward in price and downward
in quantity.

Bucket 0's interval probes characterize scoring behavior only. They do not
assert public thresholds, and the artifact labels bounded discoveries as not
exact.

## Rejected exhaustive quantity baseline

The first implementation evaluated `q=1..q_current+2`. That is not equivalent
to “two quantities beyond the published quantity”: for high-quantity products
it rebuilt approximately 100–260 otherwise irrelevant lower-quantity
distributions, many corresponding to prices above current market for a
non-leader.

The run began at 2026-09-12 21:54 local time and was deliberately terminated
after the overnight observation. The unified command recorded at least
6,787.7 seconds of wall time. At the last captured process measurement it had
consumed 3,064.91 CPU seconds, used 756,273,152 bytes of working set, and had an
observed peak working set of 781,512,704 bytes. The process had not written its
result artifact, and the old harness had no progress checkpoint, so completed
product/quantity counts are unavailable.

Historical authority and canonical 1,000/138 parity had already passed before
the quantity loop, the fingerprint was independently established by the smoke
run, and no exception had been emitted. Per-product monotonicity results were
not recoverable because output was atomic at completion. The exhaustive method
was rejected because of algorithmic search-space cost, **not** because of a
source-authority or correctness failure. It produced no threshold claims.

## Corrected bounded study

All 138 products constructed distributions for `q0`, `q0+1`, and `q0+2`. The
current leader additionally used `q0-1` and `q0-2`. A deterministic 10-product
representative sample additionally used `q0+4`, `q0+8`, and `q0+16` where
valid. The sample included current #1, another top-five product, rank 6–20,
middle rank, bottom quartile, cheapest/highest-q, expensive/low-q, a guaranteed-
component product, and four product families.

Each exact integer-cent interval
`floor(B_cents/(q+1))+1 .. floor(B_cents/q)` was probed at its low endpoint,
approximately 25%, midpoint, approximately 75%, and high endpoint, with narrow
interval duplicates removed.

Measured coverage:

* Products: 138
* Physical quantity distributions: 446
* Quantity span across products: 1–278
* Price evaluations: 2,176
* Adjacent fixed-quantity price comparisons: 1,730
* Quantity-cache hits/misses: 0/446. Cross-product quantity reuse was
  intentionally disabled because canonical product keys remain isolated.
* Bounded candidate found (not exact): 19 products
* Unresolved bounded study: 119 products

The farther probes characterize quantity discontinuities; they do not establish
exact thresholds because intermediate quantities were not exhaustively searched.

## Fixed-quantity monotonicity

Across all 1,730 adjacent comparisons, moving from a cheaper acquisition cent
to a more expensive cent produced:

* Financial RIP V4 violations: 0
* Overall RIP V12 violations: 0
* Canonical comparator violations (`cheaper` loses while `dearer` wins): 0

This is empirical coverage of the bounded cohort, not a proof that future data
can never violate monotonicity. Production search still needs a correctness-
preserving fallback.

## Corrected performance results

Measured on this workstation in one full bounded pass:

| Stage | Seconds |
|---|---:|
| Historical source-authority load | 0.7352 |
| Canonical historical V12 parity | 0.0125 |
| Exact simulation-product source load | 0.4089 |
| Pack artifact loading | 10.6786 |
| Base-distribution construction | 8.8096 |
| Quantity-distribution construction | 147.7919 |
| Financial V3/V4 scoring passes | 287.8063 |
| V12 transforms | 0.0641 |
| Canonical comparator work | 0.1085 |
| Total bounded wall clock | 457.0699 |

Peak Python-traced memory was 1,110,341,312 bytes. At completion the process
working set was 1,186,164,736 bytes and its process-reported peak working set was
1,223,524,352 bytes. Financial scoring and quantity construction dominate;
V12 transformation and comparison are negligible by comparison.

## Remaining risks and Bucket 1 recommendation

No unresolved source-authority, parity, or observed monotonicity correctness
issue blocks optimized scorer work. Remaining engineering risks are:

* 457 seconds and a 1.22 GB peak are unsuitable for a synchronous production
  request path.
* The current Financial scorer performs costly work for each price probe; the
  measured 287.81 seconds motivates prepared fixed-distribution scoring.
* Exact thresholds require direction-aware cent search and quantity bracketing,
  not the bounded research probes.
* Quantity changes can create discontinuities, so bracketing must verify
  boundaries and retain an exhaustive/correctness-preserving fallback whenever
  assumptions fail.
* Bucket 3 must preserve exact source inputs independently of replaceable base
  snapshot rows.

Proceed to Bucket 1 only to build the prepared canonical Financial scorer and
exact threshold-search infrastructure. Its design should use non-leader search
downward in price/upward in quantity, leader search upward in price/downward in
quantity, quantity bracketing, fixed-quantity cent search, canonical comparator
parity, and a correctness-preserving fallback. Do not publish thresholds until
the later buckets' persistence and source-binding gates are complete.
