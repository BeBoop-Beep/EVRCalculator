# Overall RIP Accessibility — Scoring Core Implementation (Code-Only)

**Label: `OVERALL_RIP_ACCESSIBILITY_SCORING_CORE_IMPLEMENTED_CODE_ONLY`**

This is a CODE implementation pass (Prompt 2), building the new scoring path decided by the
research closure. Nothing here persists, publishes, migrates, deploys, or cuts over the
canonical selector. Production canonical Overall remains V10. No deployment/migration/publication
was performed.

## Research decision referenced

`docs/research/OVERALL_RIP_ACCESSIBILITY_ARCHITECTURE_CLOSURE.md`, FINAL CLOSURE section (Pass
1C), decision label `OVERALL_RIP_ACCESSIBILITY_ARCHITECTURE_VALIDATED`.

## New Overall version identity

`overall_rip_v12_86_financial_v4_04_chase_accessibility_v1_10_collector_appeal_v5`

Discovery (Phase 1): grepped `OVERALL_RIP_V10_VERSION`, `CANONICAL_OVERALL_RIP_VERSION`, and any
V11/V12 identity across `backend/desirability/scoring_config.py`, `weighted_rip.py`, tests, and
migrations. Found `OVERALL_RIP_V11_VERSION =
"overall_rip_v11_83_financial_v4_11_collector_appeal_v5_06_chase_opportunity_v1"` already exists
as a DIFFERENT, already-implemented historical lineage: it blends Financial V4 / Collector V5 /
`chase_opportunity_v1` (Core K, product-level, 3x pack-equivalent cost) at 83/11/6. It is untouched
by this work. No V12 identity existed anywhere in the codebase, so V12 is the next honest, unused
version number for a THIRD, separate Overall lineage — this one built on Chase ACCESSIBILITY
(`chase_accessibility_v1_hc_value_squared_modeled_probability`, set-level HC-weighted
modeled-probability reachability) instead of Core K.

## Accessibility scoring-transform version identity

`chase_accessibility_overall_score_v1_saturating_k002`

Defined in the new module `backend/desirability/chase_accessibility_overall_score.py`, the ONE
canonical place raw Accessibility becomes `A_score`.

## Exact formula as implemented

```
A_score(k) = 100 * A_raw / (A_raw + k), k = 0.002 (fixed anchor)

Overall RIP V12 = 0.86 * FinancialRIPv4 + 0.04 * A_score(A_raw, k=0.002) + 0.10 * CollectorAppealV5
```

Nested/flat equivalence (verified in tests to < 1e-9, machine-precision level):

```
MarketBased = (86/90)*FinancialRIPv4 + (4/90)*A_score
Overall     = 0.90 * MarketBased + 0.10 * CollectorAppealV5
```

The 86/90 and 4/90 shares are DERIVED in code
(`OVERALL_RIP_V12_FINANCIAL_SHARE_OF_MARKET_BASED`,
`OVERALL_RIP_V12_CHASE_ACCESSIBILITY_SHARE_OF_MARKET_BASED` in `scoring_config.py`), not
hand-typed approximations.

## Required pillar versions

- Financial: `financial_rip_v4_outcome_profile_p95_only_25_20_15_25_10_5`
- Collector: `collector_appeal_v5_contextual_roster_h_only_d_baseline_up4_down2`
- Chase Accessibility (raw input): `chase_accessibility_v1_hc_value_squared_modeled_probability`
- Probability authority inside Chase Accessibility itself: `modeled_probability` (never
  `effective_pull_rate` as a direct probability input) — enforced upstream in
  `chase_accessibility.py`, unchanged by this pass.

## Missing-data semantics

`compute_overall_rip_v12` requires ALL THREE of Financial V4, Chase Accessibility raw (`A_raw`),
and Collector Appeal V5. A missing/negative/non-finite `A_raw` is refused by
`chase_accessibility_overall_score()`, which returns `None` (never 0.0/0%/neutral). A `None`
`A_score` (or a `None` Financial or Collector score) makes the whole V12 result
`{"score": None, "rankable": False, "status": "unavailable_missing_input", ...}` with a precise
`missingInputs` list — no renormalization of the remaining pillars, and no fallback to V10 or V11.

## V10 status

Unchanged. `compute_overall_rip_v10` was not edited. Its existing test file
(`backend/tests/unit/desirability/test_overall_rip_v10_and_financial_v4_integration.py`) and the
V11 test file (`test_overall_rip_v11.py`) both still pass in full (63 tests), run fresh in this
pass. `OVERALL_RIP_V10_WEIGHTS == {"financial_rip": 0.90, "collector_appeal": 0.10}` is asserted
again by the new V12 test file.

## V11 status

Found pre-existing and unmodified: `overall_rip_v11_83_financial_v4_11_collector_appeal_v5_06_
chase_opportunity_v1`, a historical/already-implemented lineage using Core K, not Accessibility. It
is NOT the canonical selector (V10 is), was not touched, and is confirmed by test still to compute
its original 83/11/6 arithmetic unchanged.

## Canonical selector status

`CANONICAL_OVERALL_RIP_VERSION` in `backend/desirability/scoring_config.py` still resolves to
`OVERALL_RIP_V10_VERSION`. Not flipped, not touched. `compute_overall_rip_v12` is directly
importable/callable/testable but wired into no live selection path, publication contract, or
API surface.

## Schema/migration decision

**Deferred — no migration created.** This prompt is pure scoring-function code. No new column,
table, or persisted field is required to compute or test `compute_overall_rip_v12` — its inputs
(Financial V4 score, Chase Accessibility raw `A_raw`, Collector Appeal V5 score) are all already
producible in-memory from existing modules, and its output is not persisted anywhere by this pass.
Migration 077 (`077_create_pokemon_set_chase_accessibility_snapshot.sql`, Chase Accessibility
persistence) remains the highest-numbered migration, confirmed still present in the repo and
confirmed (per the research closure, F11) unapplied in production — it was not touched, read for
modification, or applied. Persistence/publication wiring for V12 is explicitly out of scope here
and belongs to a future "Prompt 3" pass.

## Tests added

New file: `backend/tests/unit/desirability/test_overall_rip_v12_chase_accessibility.py` — 26 tests
covering formula exactness (A), anchor semantics 25/50/75 (B), monotonicity (C), scale separation
between raw `A_raw` and `A_score` (D), missing-data fail-closed behavior (E), weight-sum (F),
nested/flat parity (G), V10 golden-case regression (H), V11 non-restoration (I), ECE absence via
signature inspection (J), Chase Depth absence via signature inspection (K), no direct
`effective_pull_rate`/probability input (L), and a research-contract lock test rejecting
84/6/10, 83/11/6, and bare 90/10-without-Accessibility under the V12 name.

**Actual run results** (this session, `python -m pytest`):
- `test_overall_rip_v12_chase_accessibility.py` + `test_overall_rip_v10_and_financial_v4_integration.py`
  + `test_overall_rip_v11.py`: **89 passed, 0 failed**.
- Full `backend/tests/unit/desirability/` suite: **1938 passed, 51 failed** — all 51 failures are
  in the pre-existing `test_treatment_market_prestige_v3_round20.py` through `round24.py` files
  (an unrelated Treatment/Market Prestige research track), confirmed by `git status` to be
  untouched by this pass and confirmed by grep to import neither `weighted_rip`,
  `scoring_config`, nor the new `chase_accessibility_overall_score` module. Pre-existing, not
  introduced by this work.

## Regression-search classification

Grepped `backend/desirability`, `backend/calculations/evr`, `backend/db/services` for
`84/10/6`, `84/6/10`, `83/11/6`, `85/10/5`, `Core K`, `economic_chase_efficiency`,
`product_chase_efficiency`, `chase_depth`, `overall_rip_v11`. All hits classified:
- `Core K` / `chase_opportunity` / `overall_rip_v11` references in `chase_core_k.py`,
  `chase_opportunity.py`, and V11's own docstrings/config — **historical/current V11, preserved,
  not touched**.
- `chase_depth` references in `chase_accessibility.py` (Chase Depth diagnostic definition) —
  **preserved diagnostic, unchanged, and confirmed absent from V12's own signature by test K**.
- No hit for `84/10/6`, `84/6/10`, `83/11/6` (V11's own, correctly distinct 83/11/6 is present
  only in V11's own file, expected), `85/10/5`, `economic_chase_efficiency`, or
  `product_chase_efficiency` anywhere in production scoring code.
- No global find-replace performed; only the new V12 additions in `scoring_config.py` and
  `weighted_rip.py` were written.

## Deployment/migration/publication status

**None.** No commit was created by this pass. No migration was applied. No canonical selector was
flipped. No snapshot, leaderboard, or publication contract was touched or rebuilt.

## Files changed

- `backend/desirability/scoring_config.py` — added the `OVERALL_RIP_V12_*` constants/weights/
  effective-weights/derived Market-Based shares/required-version lookups block (new section,
  additive only; nothing existing edited).
- `backend/desirability/weighted_rip.py` — added the `OVERALL_RIP_V12_*` import block, the
  `chase_accessibility_overall_score` import, and the new `compute_overall_rip_v12()` function
  (additive only; `compute_overall_rip_v10`/`v11` untouched).
- `backend/desirability/chase_accessibility_overall_score.py` — new module, the sole
  `A_raw -> A_score` transform implementation.
- `backend/tests/unit/desirability/test_overall_rip_v12_chase_accessibility.py` — new test file,
  26 tests.
- `docs/research/OVERALL_RIP_ACCESSIBILITY_SCORING_CORE_IMPLEMENTATION.md` — this file.

## Production canonical status

**Production canonical Overall remains V10. No deployment/migration/publication performed.**
