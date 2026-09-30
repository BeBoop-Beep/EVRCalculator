# Treatment Hierarchy V1 — Preregistration (Set-Relative Treatment Appeal)

Study: `research/collector-v9-set-relative-treatment-v1-20260929`
Branch base: `origin/develop` @ `8e86b6b3ab83422d95299107a66510a56ae5c336`
Date frozen: 2026-09-29

## 0. Purpose

Determine whether Treatment Appeal can be estimated hierarchically at
`era_id x set_id x canonical treatment identity`, partially pooled
Set -> Era -> Cross-Era, while controlling for Exact Pull Scarcity, without
promoting anything to production. This document freezes the evidence
contracts and decision gates BEFORE any new model fitting in this study.

## 1. Prior-research inheritance (frozen, not re-litigated)

Inspected before writing this file:

- `docs/research/TREATMENT_PRESTIGE_COLLECTOR_APPEAL_RESEARCH.md`
- `docs/research/TREATMENT_MARKET_PRESTIGE_V3_RESULTS.md`
- `docs/research/TREATMENT_MARKET_PRESTIGE_V3_ROUND21_RESULTS.md`
- `docs/research/TREATMENT_MARKET_PRESTIGE_V3_ROUND22_RESULTS.md`
- `docs/research/TREATMENT_MARKET_PRESTIGE_V3_ROUND23_RESULTS.md` (newer than Round 22)
- `docs/research/TREATMENT_MARKET_PRESTIGE_V3_ROUND24_RESULTS.md` (newest — supersedes Round 22 as the
  authoritative coverage state; **this study must not treat Round 22 as the latest evidence**)
- `backend/scripts/build_treatment_market_prestige_v3_round21.py`
- `backend/scripts/build_treatment_market_prestige_v3_round22.py`
- `backend/scripts/build_treatment_market_prestige_v3_round23.py`
- `backend/scripts/build_treatment_market_prestige_v3_round24.py`
- `docs/research/collector_appeal/FINAL_COLLECTOR_APPEAL_CONTROL_MANIFEST.md`
- `docs/research/collector_appeal/final_collector_appeal_control_manifest.json`

Round 24 finding (frozen as the current ground truth, NOT re-derived in this
study — this study reuses it rather than re-running Round 24's read-only
SQL work):

- `panelReadinessCounts`: `PANEL_READY_STRONG = 1`, `PANEL_READY_MODERATE = 4`,
  `METADATA_BLOCKED = 935`, `HISTORY_BLOCKED = 15049`, `NO_TRUE_LADDER = 0`
  (denominator: 15,989 exact treatment-ladder pairs with a shared subject
  identity across >1 treatment inside the same Set).
- Explicit Round 24 recommendation: **"Do not build an estimator."**
  (`docs/research/TREATMENT_MARKET_PRESTIGE_V3_ROUND24_RESULTS.md`, line 56)
- `productionPause: true`, `rowsPersisted: 0`.

This study treats Round 24's panel-readiness ledger as the authoritative,
already-frozen Phase 1 coverage audit for the matched-identity /
shared-date dimension of this research question. Re-deriving it from raw
history in this pass would duplicate already-approved read-only SQL work
for no new evidence.

## 2. Frozen authorities (controls — not modified in this study)

- **Pricing authority**: canonical historical NM Price Storage V2 lineage
  (the same lineage Round 21-24 scripts read from; no alternate/live price
  source may be substituted).
- **Subject Appeal**: current frozen authority per
  `docs/research/collector_appeal/final_collector_appeal_control_manifest.json`.
  Not modified. The Trainer/ANCHOR25 redesign is explicitly OUT OF SCOPE.
- **Artist authority**: current frozen authority, unmodified.
- **Playability authority**: current frozen authority, unmodified.
- **Exact Pull Scarcity**: the modeled pull-probability authority used by
  the 22 simulation-supported Sets (Round 2 `exact_pull_cohort` lineage).
  Only those 22 Sets are eligible for `GOLD_SCARCITY_CONTROLLED` status;
  this is a preregistered eligibility ceiling, not a passing guarantee.
- **Collector Appeal (current production)**: read-only reference for the
  Phase 9 shadow comparison. Never mutated.

## 3. Treatment-cell identity (frozen)

`treatmentCellKey = era_id | set_id | rarity_designation | printing_finish | special_treatment | edition_status`

- Reuses the existing decomposed taxonomy (rarity/designation, printing
  finish, explicit special treatment, edition) from the Round 21+ taxonomy
  work. No new parallel taxonomy is introduced.
- Components are compositional, not forced mutually exclusive.
- Mechanic/form is a control, not part of the identity key, per prior
  accepted research.
- Promo remains ambiguous; no promo-resolving evidence was found newer
  than Round 24, so promo cards remain `UNSUPPORTED` pending future
  evidence.
- No monotonic rarity ordering (e.g. SIR > IR > Ultra Rare) is assumed or
  enforced anywhere in this study's code or gates.

## 4. Cohort construction (frozen)

- Base cohort: cards with a resolved `treatmentCellKey`, a canonical
  subject identity, a Price Storage V2 historical NM observation, and a
  Set membership.
- Matched-identity requirement for `PURE_TREATMENT`/`TREATMENT_PACKAGE`
  local contrasts: the same canonical subject identity must appear in
  >=2 treatment cells inside the same Set (the Round 24 "ladder" concept).
- Exclusions: cards with `canonicalIdentityBlocker`, `conditionAlignmentBlocker`,
  or unresolved edition/finish per Round 24's `metadataBlockerDecomposition`.

## 5. Support classes (frozen, reused from spec Phase 1)

- `GOLD_SCARCITY_CONTROLLED`: matched ladder is `PANEL_READY_STRONG` or
  `PANEL_READY_MODERATE` under Round 24 AND the Set is one of the 22
  simulation-supported Sets (Exact Pull Scarcity available).
- `DIAGNOSTIC_PACKAGE_ONLY`: matched ladder is `PANEL_READY_STRONG`/
  `PANEL_READY_MODERATE` but the Set is outside the 22 simulation-supported
  Sets (no Exact Pull Scarcity authority).
- `UNSUPPORTED`: `METADATA_BLOCKED`, `HISTORY_BLOCKED`, or `NO_TRUE_LADDER`.

## 6. Decision gates (frozen BEFORE inspecting which Sets pass)

A treatment cell may enter Phase 2 (PURE_TREATMENT / TREATMENT_PACKAGE
estimation) only if ALL of:

- G1: matched-identity count >= 2 within the Set for the cell's ladder;
- G2: support class is `GOLD_SCARCITY_CONTROLLED` or
  `DIAGNOSTIC_PACKAGE_ONLY` (not `UNSUPPORTED`);
- G3: graph connectivity — the cell participates in a connected
  treatment-comparison component of size >= 2 within its Set;
- G4: no single card accounts for 100% of the matched-identity contrasts
  for that cell (single-chase-card veto, per spec Phase 3).

The study proceeds from Set-local (Phase 3) to era hierarchy (Phase 4) only
if at least 2 independent Sets per era pass G1-G4 for a shared treatment
family. It proceeds to cross-era (Phase 5) only if at least 2 independent
eras have >=1 validated family in common.

**Preregistered stop rule**: if the number of cells passing G1-G4 is too
small to populate even one era-level comparison (i.e. fewer than 2 Sets
per era clear the gates for any shared treatment family), the study
terminates at Phase 1/3 with `SET_RELATIVE_TREATMENT_NOT_SUPPORTED` or
`SET_RELATIVE_TREATMENT_DIAGNOSTIC_ONLY`, and Phases 4-9 are not fabricated
or approximated to compensate.

## 7. Bootstrap / influence / sensitivity (specified for any cell that clears the gates)

- Bootstrap: 2,000 resamples of matched-identity contrasts per cell,
  percentile CI.
- Leave-card-out and leave-top-card-out influence diagnostics on every
  cell's local estimate.
- Sensitivity sweeps: Subject Appeal +/-1 tier, Artist authority on/off,
  Playability authority on/off, scarcity control on/off (this is exactly
  the PURE_TREATMENT vs TREATMENT_PACKAGE contrast).

## 8. Temporal folds (frozen)

Chronological split at the median observation date per qualifying cell's
panel; earlier half estimates, later half evaluates rank correlation,
sign stability, and large-cell reversals. Folds are frozen before Phase 6
is executed and are not re-cut after seeing results.

## 9. Normalization candidates (to compare, not select in advance)

- Empirical percentile / ECDF of validated posterior effects.
- Robust z-score mapped to 0-100.
- Anchored robust effect-size normalization.

Selection criterion (frozen): reproducibility + temporal stability +
interpretability. Current-price fit is explicitly excluded as a selection
criterion.

## 10. What this preregistration does NOT authorize

- Any write to `pokemon_collector_appeal_current` or any production table.
- Any change to Overall RIP, Rankings, or published Set pages.
- Introducing ANCHOR25 or a Trainer/Google-Trends redesign.
- Forcing a monotonic rarity ordering to make results "look right."
- Assigning a fallback score to an `UNSUPPORTED` cell.
