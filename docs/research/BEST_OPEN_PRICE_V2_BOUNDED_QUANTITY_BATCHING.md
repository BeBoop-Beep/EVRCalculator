# Best-Open Price V2: Bounded Exact Multi-q Quantity Batching (Bucket 2)

Token: **BOUNDED_EXACT_MULTI_Q_FUSED_VALIDATED**

Code commit: `fea175c2` (`backend/calculations/evr/best_open_price_v2_fused_batched.py`, runner
`backend/scripts/run_best_open_price_v2_bounded_batched.py`, tests
`test_best_open_price_v2_bounded_batching.py`, small flat-stream chunk-copy fix in
`sealed_product_distribution.py`, bitwise-identical output). The proven fused control module is untouched.
Authority: snapshot `0e65fb6d-ff33-4331-99d5-d6a214ecc712`, market date 2026-09-14, budget $1,300,
fingerprint `faad453f...e48b0`. Read-only against Supabase; nothing published. Raw evidence: `logs/bo_bucket2_*` (gitignored);
summary in `best_open_price_v2_bounded_quantity_batching.json`.

## Design
No q is skipped, no price binary search, no branch-and-bound. The engine requests contiguous blocks of the next
q values from `build_single_q_parity_distributions` (adaptive widths 1,4,8,16,24, capped at 24 and by the existing
memory ceiling), lazily builds one prepared scorer at a time (max resident prepared = 1), holds one bounded pending
block, releases each q after use and the block when exhausted. Any wrong q set, identity mismatch, memory refusal,
exception or invariant failure falls back to canonical independent single-q construction and is recorded.
Price/comparator/benchmark logic is the unchanged fused logic.

## Parity
| Gate | Result |
|---|---|
| Phase 10B four products | 8/8 exact cents |
| Stratified 23 products (control vs batched) | 46/46 exact |
| Full 138-product frozen cohort | 138/138 RIP + 138/138 Financial = **276/276 exact**, thresholds 276/276, 0 unresolved, 0 exactness failures |
| Fallbacks | 0 |

## Tests
Focused Best-Open / quantity batch / fused / monotonicity / prepared scorer / Financial V3-V4 / ranking / V12 set:
487 passed, 187 skipped (DB-gated). 11 failures exist only in `test_best_open_price_scheduled_publication_contract.py`,
`test_best_open_process_lock.py`, `test_best_open_review_regressions.py`: environmental (old local Python has no
`ast.unparse`; Windows lock/PowerShell paths), unrelated to this engine.

## Full cohort vs control
| Metric | Control (fused) | Bounded batched |
|---|---|---|
| Wall | ~8,554 s | **1,463.8 s (5.84x faster)** |
| Peak RSS | 304.43 MiB | 462.9 MiB (+158 MiB; baseline 126 MiB) |
| Candidate prices | 1,167,908 | 1,167,908 |
| q constructions | 4,831 | 5,769 (4,831 consumed + 938 speculative) |
| Median product | 4.64 s | 3.91 s |
| P95 product | 319.57 s | 39.02 s |
| Max product | 511.71 s | 64.74 s (3dc67a73) |

Batch stats: 573 batch builds, max pending 24, max resident prepared 1, max estimated batch bytes 240 MB,
speculative waste 16.3% of constructions (938 unused q; roughly 9% on the 23-product stratified set), 0 fallbacks.
RNG draws: effective 5.57e10 vs legacy-equivalent 8.75e11.

Phase seconds (sum over products): physical q construction 675.1 s, prepared-scorer 486.0 s, candidate scoring 97.4 s,
comparator 7.6 s, product wall sum 1,463.8 s. The control's per-phase split is not in its baseline artifacts, so no
control phase comparison is claimed. Constructions increased 19% by count yet total time fell 5.8x because batching
amortizes the fixed cost of each build across q values.

## Assessment
Worthwhile: exact, 5.8x faster, P95 8x lower, +52% peak RSS (still under 0.5 GiB), bounded by the memory ceiling.
Remaining bottleneck: physical q construction (46%) plus prepared-scorer build (33%); candidate scoring and comparator
are about 7%. Possible refinements: tune the width cap/ramp to trim the 16% speculative waste, and reduce prepared-scorer cost.
