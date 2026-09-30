# Treatment Hierarchy V1 — Final Report

Branch: `research/collector-v9-set-relative-treatment-v1-20260929`
Base: `origin/develop` @ `8e86b6b3ab83422d95299107a66510a56ae5c336`

## 1. Objective recap

Determine whether Treatment Appeal can be estimated hierarchically at
`Set x Treatment`, pooled Set -> Era -> Cross-Era, controlling for Exact
Pull Scarcity, without treating rarity/finish labels as universal fixed
scores.

## 2. What changed since Round 22

The spec explicitly required checking for Treatment research newer than
Round 22 before proceeding. Rounds 23 and 24 exist and are newer:

- **Round 23**: froze raw shared-date panels only for a bounded sanity
  sample; all other apparent ladders remained history-blocked.
- **Round 24** (newest): ran a grouped exact-date query across 15,989
  exact treatment-ladder pairs (cards sharing a subject identity across
  >=2 treatments in the same Set). Result: `PANEL_READY_STRONG = 1`,
  `PANEL_READY_MODERATE = 4`, `METADATA_BLOCKED = 935`,
  `HISTORY_BLOCKED = 15,049`. Round 24's own explicit recommendation was
  **"Do not build an estimator"** and it set `productionPause: true`.

This materially changes the premise of this study: the shared-date,
matched-identity panel infrastructure this study's hierarchical model
depends on does not yet exist at usable scale.

## 3. What this study did

- Phase 0: Wrote a full preregistration (`PREREGISTRATION.md`,
  `preregistration.json`) freezing authorities, treatment-cell identity,
  cohort rules, support classes, decision gates, bootstrap/temporal/
  normalization procedures, and an explicit stop rule — BEFORE looking at
  whether any Set would pass.
- Phase 1: Built the coverage audit (`COVERAGE_AUDIT.md`) by reusing
  Round 24's already-executed, already-approved read-only ledger (re-
  deriving it would have duplicated approved work without new evidence).
  Applied this study's frozen gates (G1-G4, era-progression minimum) to
  that ledger.

## 4. What this study did NOT do, and why

Phases 2-9 (PURE_TREATMENT/TREATMENT_PACKAGE model fitting, within-Set
identification, era/cross-era hierarchy, temporal validation,
falsification cases, treatment-authority candidate, Collector-shadow
impact) were **not executed**. The preregistered stop rule
(PREREGISTRATION.md Section 6) triggers before Phase 2: only 5 of 15,989
exact ladders are panel-ready, which cannot populate even one era-level
comparison with 2 independent Sets sharing a treatment family. Fitting a
hierarchical model on 5 cells (with no frozen, reproducible sample of
which specific cards constitute them — `sampleHash: null` in Round 24)
would produce a result indistinguishable from noise or from an artifact
of whichever 5 cells happen to have data, which the preregistration
explicitly forbids presenting as a finding.

This is the correct outcome under the preregistration, not a shortcut:
the spec itself requires "Do not choose a positive token unless every
required gate actually passes" and defines
`SET_RELATIVE_TREATMENT_NOT_SUPPORTED` as an acceptable disposition.

## 5. Decision

See `decision.json`. Token: **`SET_RELATIVE_TREATMENT_NOT_SUPPORTED`**
at the Phase 1 gate.

| Sub-decision | Status |
|---|---|
| Treatment taxonomy validity | Reused unchanged from prior rounds |
| Set-local identification validity | Not testable — insufficient panels |
| Scarcity separability | Not testable — insufficient panels |
| Era hierarchy validity | Not reached |
| Cross-era comparability | Not reached |
| Temporal validity | Not reached |
| Collector-shadow usefulness | Not reached |

## 6. Production impact

Zero. No production table, Collector Appeal, Overall RIP, Rankings, or
Set page was read for write purposes or mutated. All reads were of
already-committed research docs/JSON in the repository.

## 7. Recommended next action

Identical to Round 24's own recommendation, now re-affirmed by an
independent preregistered study: repair authoritative vintage edition and
modern special-treatment metadata, then execute the grouped exact-date
query through an approved read-only SQL endpoint for a representative,
preregistered ladder sample, BEFORE any future Treatment Hierarchy study
attempts Phase 2+. Until that metadata/history repair lands, further
Treatment Hierarchy modeling work should not be scheduled.

## 8. Files produced

- `docs/research/collector_appeal/treatment_hierarchy_v1/PREREGISTRATION.md`
- `docs/research/collector_appeal/treatment_hierarchy_v1/preregistration.json`
- `docs/research/collector_appeal/treatment_hierarchy_v1/COVERAGE_AUDIT.md`
- `docs/research/collector_appeal/treatment_hierarchy_v1/decision.json`
- `docs/research/collector_appeal/treatment_hierarchy_v1/FINAL_REPORT.md` (this file)
- `backend/tests/unit/desirability/test_treatment_hierarchy_v1_gate.py`
