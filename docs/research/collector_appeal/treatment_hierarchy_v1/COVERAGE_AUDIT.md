# Treatment Hierarchy V1 — Phase 1 Coverage Audit

Source of truth: Round 24 panel-readiness ledger (already-approved,
already-executed read-only SQL; not re-run in this study — see
Preregistration section 1 for why re-deriving it would duplicate prior
approved work without new evidence).

## Headline coverage (Set x Treatment matched-identity ladders)

| Class | Count | % of 15,989 exact pairs |
|---|---:|---:|
| PANEL_READY_STRONG | 1 | 0.006% |
| PANEL_READY_MODERATE | 4 | 0.025% |
| METADATA_BLOCKED | 935 | 5.85% |
| HISTORY_BLOCKED | 15,049 | 94.12% |
| NO_TRUE_LADDER | 0 | 0.0% |

Mapped to this study's frozen support classes (Preregistration Section 5):

- Candidate `GOLD_SCARCITY_CONTROLLED` / `DIAGNOSTIC_PACKAGE_ONLY` pool
  (i.e. `PANEL_READY_STRONG` + `PANEL_READY_MODERATE`): **5 cells total**,
  pending confirmation of which fall inside the 22 simulation-supported
  Sets.
- `UNSUPPORTED`: 15,984 cells (99.97%).

## Gate evaluation (Preregistration Section 6)

- **G1 (matched-identity >= 2)**: satisfiable only by the 5 panel-ready
  cells by construction of "ladder."
- **G2 (support class not UNSUPPORTED)**: passes for the same 5 cells.
- **G3 (graph component >= 2 within Set)**: cannot be evaluated as
  passing broadly — 5 cells is too few to guarantee 2 Sets per era share
  a treatment family; this requires per-cell identification that Round 24
  did not carry to the Set/era level (it stopped at ladder-pair counting
  and explicitly recommended not proceeding to estimation).
- **G4 (single-chase-card veto)**: not evaluable without re-identifying
  which specific cards underlie the 5 panel-ready ladders, which Round 24
  did not publish as a frozen, reproducible sample (`sampleHash: null`,
  `frozenValidationSample: []`).
- **Era progression minimum (>=2 independent Sets per era per shared
  family)**: cannot be met. 5 candidate cells across the entire catalog
  cannot populate 2 independent Sets for even one treatment family with
  the confidence this study's stop rule requires, and Round 24 does not
  supply the Set-level breakdown needed to even attempt it.

## Conclusion of Phase 1

The **preregistered stop rule in PREREGISTRATION.md Section 6 is
triggered**: fewer than 2 Sets per era clear G1-G4 for any shared
treatment family, because the underlying matched-identity/shared-date
panel infrastructure remains almost entirely `HISTORY_BLOCKED` or
`METADATA_BLOCKED` as of Round 24 (the newest available Treatment
evidence, dated after Round 22).

Per the stop rule, this study does not proceed to fabricate Phases 2-9
(PURE_TREATMENT/TREATMENT_PACKAGE estimation, within-Set identification,
era hierarchy, cross-era hierarchy, temporal validation, falsification
cases, or Collector-shadow impact) on a data foundation that its own
authority (Round 24) explicitly assessed as insufficient and explicitly
recommended not be used to build an estimator.

This is a valid, gate-driven Phase 1 outcome, not an abandonment of the
research question. See `FINAL_REPORT.md` for the full disposition and the
concrete remediation Round 24 already specified.
