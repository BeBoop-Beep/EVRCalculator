# Best-Open Price V2 Bucket 3: Prepared-Scorer Optimization and Batch-Ramp Tuning

Token: **PREPARED_SCORER_OPTIMIZATION_VALIDATED**

Bound to Financial RIP V4 + Overall V12 (no V5, no Best-Open V3). Read-only against Supabase. Snapshot
`0e65fb6d-ff33-4331-99d5-d6a214ecc712`, $1,300, fingerprint `faad453f...e48b0`. Raw evidence: `logs/bo_b3_*` (gitignored).

## Phase 0: Bucket 2 reproducibility
Bucket 2 logged runs postdate the last edit of every engine file (files last written 15:07-15:14; stratified 15:57-16:04;
full run 16:05-16:29; commit fea175c2 at 16:05:16) and the tree is unchanged, so the full run used the committed code.
Fresh reruns of the committed engine: Phase 10B 8/8 exact (py3.8, numpy 1.24), stratified 46/46 (py3.8), full cohort
276/276 (py3.11, numpy 2.4.4), 0 fallbacks, 0 unresolved. It reproduces.

## Phase 0B: the earlier 11 failures
| Test | Interpreter | Reason | Class |
|---|---|---|---|
| test_best_open_price_scheduled_publication_contract.py (9 tests) | 3.8 and 3.11 | `read_text()` without encoding under Windows cp1252 (UnicodeDecodeError) | Windows-specific; all 9 pass with `PYTHONUTF8=1`; CI is Linux |
| test_best_open_review_regressions.py::test_engine_uses_persisted_collector_not_mutable_simulation_input | 3.8 | `ast.unparse` missing (3.9+) | wrong interpreter; passes on 3.11 |
| test_best_open_process_lock.py (1) | 3.8 | old interpreter / Windows lock path | passes on 3.11 |

None touch the Best-Open search or Bucket 2. Under py3.11 with UTF-8 the CI-style suite is 878 passed, 5 skipped, 0 failed.
No test was weakened.

## Phase 1: `PreparedFinancialRipDistribution.prepare` profile
30 real 1M-outcome vectors (6 products, q 1..353), mean 93 ms per prepare. Share: stable sort 62.4%, median 8.2%, P95 7.5%,
P05 7.3%, P99 7.3% (median plus percentiles 30.3%, four full-array partitions), prefix cumsum 2.9%, unclassified 2.8%,
finite check 0.5%, distinct 0.4%, mean/sum/tails about 1%. Profiler: `research_best_open_price_v2_prepared_profile.py`.

## Phase 2/3: speculative-q lifecycle
Bucket 2 already builds prepared scorers lazily: a speculative q is a raw vector only, never sorted, prefix-summed or
prepared. Speculative preparation cost is 0 s (938 preparations avoided over the cohort). Its cost is physical construction
only: exact marginal measure on the stratified set (T(block) minus T(consumed-only rebuild)) is 12.0 s of 265.6 s construction
(4.5%) for 9.0% speculative q. So none of the ~33% prepared-scorer cost belongs to never-consumed q; Phase 3 needed no work.

## Selected optimization
`PreparedFinancialRipDistribution.prepare_exact_accelerated` (explicit opt-in, canonical `prepare` unchanged): default sort
instead of stable sort when no signed-zero mix exists (then bitwise identical), mean/sum still reduced over the original array,
one `np.percentile(sorted, [5, 95, 99])` call, median on the sorted array. Every dataclass field is bitwise compared in 47
micro-parity tests (lengths incl. percentile/tail boundaries, tied Pokemon-like vectors, guaranteed offsets, signed zeros,
extremes, invalid input, 1M vectors, downstream score equality). The gain depends on NumPy 2.x fast unstable sort (CI pins
2.4.3); on numpy 1.24 the gain is smaller. Engine: `best_open_price_v2_fused_batched_prepared.py` (lifecycle accounting, optional
trace, optional abandon policy); Bucket 2 module untouched as control.

## Rejected
Sort with ownership transfer (in-place sort saved about nothing vs copy), hand-written percentile/median math (not needed),
dropping prefix sums (2.9%), fused single-pass aggregates (under 1%), a custom preparation engine (fails the complexity test for
the residual ~7% prepared cost), and every ramp variant below.

## Phase 5: batch policy
Real stratified timing (23 products, py3.11): Bucket 2 ramp 4->24 wall 406.7 s, 9.0% speculative, avg width 13.0;
constant 12 wall 458.6 s, 9.7% speculative, avg width 10.4. Trace-replay simulator (actual q-demand sequences through the real
planner, cost model R2 0.97) modeled const24 20.0% spec / 252.5 s, A 8-16-24 13.8% / 261.4 s, B 4-8-16-24 9.0% / 265.6 s,
2-start 8.8% / 273.5 s; reset/halve abandon policies were identical to their initial widths (abandonment coincides with the
phase change that already resets the ramp). Differences are within noise, so no ramp change was adopted.

## Full cohort (138 products, 276 thresholds)
| Metric | Bucket 2 control (py3.11 rerun) | Bucket 3 |
|---|---|---|
| Exact | 276/276 | 276/276, same q, same benchmarks, 0 unresolved, 0 fallbacks |
| Physical construction s | 771.1 | 663.0 |
| Prepared scorer s | 487.3 | 93.9 |
| Candidate scoring s | 97.4 | 95.6 |
| Comparator s | 7.6 | 7.6 |
| Product wall sum s | 1,669.5 | 1,251.9 |
| Median / P95 / max product s | 4.80 / 43.6 / 54.5 | 3.72 / 31.7 / 74.4 |
| Peak RSS MiB | 453 | 467 |

Caveat: the control rerun overlapped other benchmark processes; the original uncontended Bucket 2 figure is 1,463.8 s (py3.8),
so the honest uncontended gain is about 1,464 s to about 1,252 s (roughly 14%), while prepared-scorer time fell 5.2x. The
Bucket 3 run was resumed once after a transient Supabase PGRST002 error (29 products came from the checkpoint; per-product
walls are summed). Batching: 573 batches, 5,769 generated, 4,831 consumed and prepared, 938 speculative (16.3%), average
width 10.1, max raw pending 192 MB (24 x 8 MB), max prepared 16 MB (sorted plus prefix), max estimated block 240 MB, max
active prepared q 1.

## Judgement
Keep: about 40 lines, bitwise identical, opt-in. Not worth more: further prepare work (residual 94 s) or ramp tuning.
Remaining dominant cost: physical q construction (about 53% of product time), then candidate scoring (about 8%).
Next step: adopt `prepare_variant="accelerated"` when promoting; touch RNG/gather construction only if more speed is needed.
