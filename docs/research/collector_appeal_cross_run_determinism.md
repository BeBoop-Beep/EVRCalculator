# Collector Appeal CA7 — determinism validation

Generated 2026-07-16T17:03:30.607110+00:00

Two different questions, reported separately. The first cannot answer the second.

## 1. In-process deterministic build

Two `build_update_plan()` calls in ONE process from ONE in-memory source read. Proves the build is a pure function of loaded state. Blind to process start-up, a fresh connection, a fresh read, and any ordering that is stable within one interpreter.

- Result: **PASS** (invariant 17)
- First payload hash: `1eac0ef18d9ff3c3474a415d0c5189362ecd70c277cfb0a309e31dd8e3f09dbf`
- Second payload hash: `1eac0ef18d9ff3c3474a415d0c5189362ecd70c277cfb0a309e31dd8e3f09dbf`

## 2. Independent cross-run deterministic build

A separate process re-read production and produced a new artifact, compared against `run_prev.json`. This is the check Phase 8.1 left unexecuted.

- **Verdict: `identical`** — deterministic: **YES**

| Check | Result | Previous | Current |
|---|---|---|---|
| formula_fingerprint | ✅ match | `a98b948c693b87afdb1e4b0d19df03aa3ae650d35ca62b38eea41c126240b774` | `a98b948c693b87afdb1e4b0d19df03aa3ae650d35ca62b38eea41c126240b774` |
| source_manifest | ✅ match | `495bbb842cf6cb1a20a9d0bf8ac9f95c15fa8610b5874ca4d69237729db501a8` | `495bbb842cf6cb1a20a9d0bf8ac9f95c15fa8610b5874ca4d69237729db501a8` |
| normalized_payload_hash | ✅ match | `1eac0ef18d9ff3c3474a415d0c5189362ecd70c277cfb0a309e31dd8e3f09dbf` | `1eac0ef18d9ff3c3474a415d0c5189362ecd70c277cfb0a309e31dd8e3f09dbf` |
| manifest part · card_inputs | ✅ match | `c06e414d5ad4261e193360b5a4f4995d1e9f523e6d0c0c0df61bce0bf7f4a44d` | `c06e414d5ad4261e193360b5a4f4995d1e9f523e6d0c0c0df61bce0bf7f4a44d` |
| manifest part · component_rows | ✅ match | `9f54ef2b7afef47810ce74c08125040c9c2de4d4df70b5eab30abe6ce746b741` | `9f54ef2b7afef47810ce74c08125040c9c2de4d4df70b5eab30abe6ce746b741` |
| manifest part · pull_model | ✅ match | `fd75a8334f67b4033e4cc2bc9a6176a61d239cd5bcf64cc16b04be6fc19502a1` | `fd75a8334f67b4033e4cc2bc9a6176a61d239cd5bcf64cc16b04be6fc19502a1` |
| manifest part · simulation_cohort | ✅ match | `821f52842625b241dab19754d2ad820c449f5e244520114c8edb2cfb849612bf` | `821f52842625b241dab19754d2ad820c449f5e244520114c8edb2cfb849612bf` |
| row ordering & serialization | ✅ match | 171 targets | 171 targets |
| counts | ✅ match | — | — |

## Volatile values

Excluded from every hash: `generated_at`.
- Observed differing between the two runs: `generated_at`
- These differ by design and do not reach hashed content — which is exactly what an identical cross-run payload hash under differing timestamps proves.

## Interpretation

Two independent runs of an unchanged source produced byte-identical hashes. Wall-clock metadata differed and did not reach hashed content.

> A changed **source manifest** means the inputs moved and is NOT nondeterminism: the correct response to changed inputs is a changed payload. Nondeterminism is only the case where the source manifest is identical and the payload moved anyway.
