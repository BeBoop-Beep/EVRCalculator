# Pattern-Overlay Guardrail Regression Suite

Date: 2026-04-20

## Purpose
This guardrail suite prevents recurrence of the historical pattern-overlay inflation bug (double counting and pool overlap), and validates that the complete fix remains intact across extraction, pull-rate logic, manual EV aggregation, and simulation behavior.

## Implemented Test Categories

1. Base Pool Exclusion Guardrail
- File: `backend/tests/unit/simulations/test_base_pool_pattern_exclusion_guardrail.py`
- Coverage: pattern rows are excluded from base common/uncommon/rare pools and routed to hit pool.
- Recurrence protection: catches any regression that reintroduces pattern rows into guaranteed base slots.

2. Rare Pool Pattern Exclusion Guardrail
- File: `backend/tests/unit/simulations/test_rare_pool_pattern_exclusion_guardrail.py`
- Coverage: rare pool explicitly rejects poke/master ball pattern rows while preserving hit-pool accessibility.
- Recurrence protection: catches rare-slot contamination from overlay rows.

3. Pattern-Aware Pull-Rate Guardrail
- File: `backend/tests/unit/calculations/test_pull_rate_pattern_detection_guardrail.py`
- Coverage: detection uses structured `pattern_key` from `Special Type`, never card-name heuristics.
- Recurrence protection: blocks false positives where names like "Master Ball" were misclassified.

4. No-Overlap Invariant Guardrail
- File: `backend/tests/unit/simulations/test_no_pool_overlap_guardrail.py`
- Coverage: common/uncommon/rare/hit pools are mutually exclusive and fully account for source rows.
- Recurrence protection: catches silent routing overlap or dropped rows.

5. Manual EV Bucket Parity Guardrail
- File: `backend/tests/unit/calculations/test_manual_ev_bucket_parity_guardrail.py`
- Coverage: row-level EV sums reconcile with bucket totals, pattern parity is exact, reverse bucket is isolated.
- Recurrence protection: catches bucket leakage and double counting in manual aggregation.

6. Prismatic Sanity Integration Guardrail
- File: `backend/tests/unit/integration/test_prismatic_sanity_guardrail.py`
- Coverage: manual EV and simulation means remain in sane range, pattern rows remain present and bounded, special-pack EV remains near expected values.
- Recurrence protection: catches large-scale inflation regressions similar to historical 34+ values.

7. Non-Pattern Set Regression Guardrail
- File: `backend/tests/unit/integration/test_non_pattern_set_regression_guardrail.py`
- Coverage: non-pattern fixtures remain pattern-free, pull-rate logic for common/uncommon/rare is unchanged, simulation stays stable.
- Recurrence protection: ensures fixes do not break non-pattern sets.

## Runtime and Determinism
- Total tests added: 33
- Deterministic controls: seeded RNG for simulation tests (`np.random.default_rng(...)`)
- Execution time (local): 25.12s for the full guardrail suite

## CI/CD Integration
A dedicated workflow runs these guardrail tests on every push and pull request:
- Workflow file: `.github/workflows/pattern-overlay-guardrails.yml`
- Scope: executes only the guardrail test suite for fast, focused regression protection.

## How This Prevents Recurrence
The suite enforces the same core invariants at multiple levels:
- Structural: pattern rows must never coexist in base pools.
- Probabilistic: pattern pull-rate path must be keyed by structured metadata.
- Accounting: each row contributes once, and only once, to manual EV buckets.
- Behavioral: integrated Prismatic/Obsidian scenarios stay within sane output ranges.

Because the tests cover both local unit invariants and end-to-end outcomes, a future regression in either extraction logic or EV math will fail CI before release.
