# Best-Open Price V2 Bucket 4: CI-Runtime Validation of the Prepared Engine

Token: **BEST_OPEN_V2_ENGINE_PROMOTION_READY** (with one runtime-sensitivity disclosure below). Bound to Financial RIP V4 + Overall V12.
Read-only against Supabase. Snapshot `0e65fb6d-ff33-4331-99d5-d6a214ecc712`, $1,300, fingerprint `faad453f...e48b0`. Raw evidence: `logs/bo_b4_*` (gitignored).

## Phase 0: runtime contract (repository authority)
- `.python-version` = 3.13.2, `runtime.txt` = python-3.13.2, `backend/requirements.txt` pins `numpy==2.4.3`, `pandas==2.2.3`, `supabase==2.28.3`.
- `best-open-price-guardrails.yml` (runtime, windows-lock, postgres jobs): Python 3.13, `numpy==2.4.3 pandas==2.2.3 scipy psutil`. scipy is unpinned; there is no lockfile.
- Other workflows (billing, market-explorer, pattern-overlay) use 3.11 but do not exercise Best-Open. The local Windows scheduled job (`infra/local/run_best_open_price.sh`) uses `backend/.venv` = Python 3.13.2 + numpy 2.4.3 (verified). Oracle VM scripts use `.venv/bin/python` with no Best-Open job yet; the VM interpreter is not declared in the repo.
- Contract: Python 3.13.2 / NumPy 2.4.3. The handoff claim (3.13 / 2.4.3) is verified. Bucket 3's full run used 3.11 / 2.4.4, which is not the contract.

## Phase 1: environment
Isolated venv `tmp/ci_venv313` (gitignored): Python 3.13.2 (MSC v.1942 64-bit), numpy 2.4.3, pandas 2.2.3, scipy 1.18.1, pytest 9.1.1, supabase 2.28.3; Windows 10 (19045), i7-13700F (24 threads). Installed with the CI install line.

## Phase 2: micro-parity
`test_prepared_financial_accelerated_parity.py` + `test_best_open_price_v2_prepared_lifecycle.py`: **62 passed, 0 mismatches** (bitwise, all dataclass fields) on 3.13/2.4.3. Also 62/62 on 3.13/numpy 2.4.4, 3.11/2.4.4 and 3.8/numpy 1.24.4.

## Phase 3: test matrix
CI selection (68 files, best_open/financial_rip_v3/v4/overall_rip_v12/v5/v14/... plus two service tests): **1096 passed, 5 skipped, 0 failed** with `PYTHONUTF8=1`. Without it there are 9 failures, all in `test_best_open_price_scheduled_publication_contract.py`: cp1252 `read_text()` decode errors on Windows (Linux CI defaults to UTF-8; tests unchanged, so PYTHONUTF8=1 is needed for local Windows runs only). The Windows-lock CI files (`test_best_open_process_lock.py`, `test_publish_best_open_price_if_ready.py`) and `test_best_open_review_regressions.py` pass (28 passed). The 5 skips are `test_financial_rip_v4_research_parity.py` (frozen research artifact absent from the checkout).
Broadened selection (106 files, adds prepared/quantity_batch/fused/monotonic/bounded/accelerated/publication): 1664 passed, 6 failed, all in unrelated concurrent lanes and outside the CI selection (`test_pokemon_level_publication_audits` x4 and `test_market_publication_audit_page_projection`: market audit; `test_scheduled_publication_contract`: `run_simulations.sh` version string). Bucket 4 touches none of these.

## Root cause of the earlier rc=2
Every stratified and full run on 3.13 returned rc=2 from `validate_parity` while thresholds, quantities, benchmarks and exactness all matched. The only failing check is `thresholdEvidenceEqual`: 4th-decimal differences in `*ThresholdFinancialRipV4Score` / `*OverallRipV12Score` (e.g. 52.2569 vs 52.2570) on 4 of 138 products (38a368bf, 682e91e8, e827c1cd, fe71155a). It affects the Bucket 2 control and the candidate identically, so it is not the prepared scorer. Cause: **Python 3.12+ `sum()` of floats uses compensated (Neumaier) summation**; the frozen reference was produced on 3.8-3.11 with naive left-to-right `sum()`, and Financial V4 is `round(sum(component*weight), 4)`. Proof: (a) 3.11 + numpy 2.4.4 reproduces the reference exactly; (b) 3.13 + numpy 2.4.4, and 3.13 + pandas 3.0.2, do not (so it is not a NumPy or pandas change); (c) 3.13 with `builtins.sum` replaced by a naive loop gives 4/4 products exact including evidence. No gate was weakened. Disclosure: the frozen reference is stale at the 4th decimal on a 3.12+ runtime, and 3.13's value is the more accurate one. Thresholds are unaffected on this cohort, but a score within ~1e-4 of a tie could in principle flip across interpreters, so the reference oracle should be regenerated on 3.13.2 at promotion.

## Phases 5-7 (candidate `prepare_exact_accelerated`, 3.13.2 / numpy 2.4.3)
| Gate | Result |
|---|---|
| Phase 10B (4 products, 8 thresholds) | 8/8 exact, allExact true, 0 unresolved |
| Stratified 23 products | 46/46 thresholds, q/benchmark/exactness parity, P* wins, P*+1 loses, 0 fallbacks; 1 product evidence-only 4th-decimal diff (sum() cause) |
| Full 138 products | **276/276 thresholds** (138 RIP + 138 Financial), q and benchmark identity parity, 0 unresolved, 0 exactness failures, 0 fallbacks; 4 products evidence-only 4th-decimal diff (sum() cause) |
| Candidate vs Bucket 2 control, full rows | 0 mismatches (excluding diagnostics/timing) |
| 4 evidence-diff products, naive-sum 3.13 | 4/4 fully exact |
| Determinism | 3 isolated reruns identical; stratified reruns 1 vs 2 identical |

## Phase 4: A/B (sequential, same machine and env; engine seconds)
Runner wall times are corrupted by resume gaps: source load hit repeated Supabase `57014 statement timeout`, needing retries and `--resume`. Product wall and cohort wall are therefore not used; engine time (`searchWallSeconds`) is unaffected. A daily pricing job (Python 3.8) ran intermittently on the machine (small, not zero contention).
| Run | Control engine s | Candidate engine s |
|---|---|---|
| Stratified (order: cand, ctl, ctl, cand) | 395.5, 389.9 | 275.3, 274.2 |
| Full 138 | 1266.5 | 876.0 (31% less) |
Physical construction 654 s vs 670 s (same), prepared scorer 500.8 s vs 93.5 s (5.4x), candidate scoring 91.1 vs 91.8 s, comparator 6.8 vs 6.9 s. Order alternation shows no order bias.

## Phase 8: candidate measurements (full)
Peak RSS 478 MiB (control 425). Engine per product: min 0.14, P50 1.99, P75 6.49, P95 26.2, max 41.3 s (control P50 3.06, P95 35.8, max 54.7). Batching: 573 batches, 5,769 q generated, 4,831 consumed, 938 speculative (16.3%), max pending 24, max active prepared 1, max estimated batch 240 MB. Fallbacks 0.

## Slowest-product audit
Bucket 3 reported a max product time of 74.4 s vs 54.5 s. Here the product-wall max is 113.0 s for `16bf6fd0`, whose engine time is 2.9 s: the wall figure is a Supabase retry/resume gap, not compute (Bucket 3's 74.4 s, which followed a PGRST002 resume, is very likely the same artifact). At engine level the slowest candidate product is `0ac601d0` (41.3 s vs 54.7 s control) and no product is slower under the candidate than the control (worst per-product ratio 0.994). Isolated reruns of `0ac601d0`: candidate 38.9, 39.1, 39.2 s; control 53.7 s. Classification: measurement artifact, not a regression, NumPy behavior or batch behavior. Tail is stable.

## Phase 9: cross-version
Exactness: micro-parity bitwise 62/62 on numpy 1.24.4 (3.8), 2.4.4 (3.11) and 2.4.3/2.4.4 (3.13); full-cohort exact on 3.11/2.4.4 (Bucket 3) and 3.13/2.4.3 (here, thresholds). Exactness of `prepare_exact_accelerated` is NumPy-version independent; only speed varies (prepared scorer 487 s to 94 s on 2.4.4, 93.5 s here; smaller gain on 1.24). The one version-dependent behavior found is Python 3.12+ `sum()`, not NumPy, and it affects reference evidence rather than thresholds.

## Dependency pin: A (already pinned adequately)
`runtime.txt`, `.python-version` and requirements pin 3.13.2 / numpy 2.4.3. Hardening notes only: scipy is unpinned in CI, and the reference oracle should be regenerated on 3.13.2. No dependency files were edited.

## Promotion readiness
Correctness 276/276 on the intended runtime; CI-selection tests green; engine time 31% below Bucket 2 with identical physical construction; memory bounded (478 MiB, 240 MB batch cap); deterministic; tail stable. Stop optimizing (remaining cost is dominated by physical q construction, with no concentrated hotspot). Move to integration/promotion planning: adopt `prepare_variant="accelerated"`, regenerate the frozen reference on 3.13.2, and harden source-load pagination against `57014` timeouts (operational finding, not an engine defect).
