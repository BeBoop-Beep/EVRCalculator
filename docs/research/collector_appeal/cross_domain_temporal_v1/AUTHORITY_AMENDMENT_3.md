# Collector Cross-Domain Temporal V1 — Authority Amendment 3

**Frozen before any temporal fold outcome was evaluated.**

## Final immutable execution authority

The earlier temporal attempts correctly stopped before evaluating any preregistered fold because either the live catalog cohort or the mutable historical RPC no longer reproduced the frozen September 11 control.

The final execution removes both mutable dependencies:

1. **Cohort and predictor authority:** the immutable frozen V7 model run
   `e282f26e-2136-4105-b0a3-f0974c4d9d70`.
   The exact 22-Set subset with a persisted positive `pullScarcityDiagnostic.probability`
   contains **4,331 rows**, exactly matching the frozen market-validation cohort.
2. **ANCHOR25 construction:** reconstructed only from persisted V7
   `subject_baseline_score`, `combined_lift`, and `subjectIdentity`, using the already
   preregistered 25% Trainer-to-Pokemon quantile anchor. The frozen identity authority contains
   1,061 Pokemon identities and 250 Trainer identities.
3. **Historical outcome authority:** the exact SQL semantics committed before the later live-RPC
   drift in migration
   `20260928204424_market_explorer_root_standard_frozen_roster_v2.sql`.
   The query is executed read-only and restricted to the immutable 4,331-card cohort. No
   function, table, row, privilege, migration, or publication is created or changed.

## Baseline lock

Before any temporal fold is permitted, the 2026-09-11 replay must reproduce the frozen fixture.

Final baseline lock:

- priced rows: **4,331 / 4,331**
- Sets: **22 / 22**
- median rho: **0.317647084429976**
- weighted rho: **0.299104912683261**
- positive Sets: **95.4545454545455%**
- maximum per-Set rho error vs frozen fixture: **2.22044604925031e-16**
- result: **PASS**

The tiny nonzero maximum is ordinary floating-point representation error and is far below the
1e-12 structural tolerance.

## Preregistration remains unchanged

No hypothesis or gate changed:

- ANCHOR25 only
- dates: 2026-09-14, 09-17, 09-20, 09-23, 09-26
- 4,331 cards / 22 Sets
- guardrails unchanged
- 4-of-5 decision rule unchanged
- 1,000 deterministic whole-Set bootstrap draws per data-valid fold
- no replacement dates
- no production mutations
- a temporal PASS supports only a research-only Collector V8 shadow

This amendment fixes the measurement instrument and cohort authority; it does not alter the
candidate or decision rule.
