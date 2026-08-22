# Overall Product Rank — Decision Record (v2, supersedes v1)

**Date:** 2026-08-22
**Branch:** `feature/overall-product-ranking-v10` (new worktree from `origin/main` @ `c190011`)
**Decision:** `OVERALL_PRODUCT_RANK_NOT_APPROVED`; **`BUDGET_SPECIFIC_PRODUCT_RANK_SUPPORTED`** at $500
**Supersedes:** `OVERALL_PRODUCT_RANK_DECISION_2026-08-22.md` (v1), which was produced against a
stale feature branch (`feature/set-market-page-redesign`) and is now known-wrong in two of its
central claims. This document explains exactly why, with evidence.

---

## A. Worktree / branch used

`git worktree add D:/EVRCalculator-overall-product-rank -b feature/overall-product-ranking-v10
origin/main` — base commit `c190011` ("Merge pull request #127 from
BeBoop-Beep/feature/financial-rip-v4-v10-cutover"). The prior UI worktree
(`feature/set-market-page-redesign`, containing concurrent Codex/other-session frontend work) was
never touched.

## B. Why the previous audit was wrong

The v1 decision was produced entirely inside `feature/set-market-page-redesign`, a branch that
predates the V4/V10 cutover merge (`origin/main` commit `c190011`, PR #127). Two of its central
claims are demonstrably false on current `main`:

1. **"`CANONICAL_OVERALL_RIP_VERSION` is still V9."** False on `main`:
   `backend/desirability/scoring_config.py:425-426` reads
   `CANONICAL_FINANCIAL_RIP_VERSION = FINANCIAL_RIP_V4_VERSION` and
   `CANONICAL_OVERALL_RIP_VERSION = OVERALL_RIP_V10_VERSION` — verified directly against source on
   the clean worktree, not assumed.
2. **"Stage 2 (ETB, PC ETB, Enhanced Booster Box) has zero V4 coverage because
   `sealed_product_stage2_rip_service.py` never calls V4."** True that the Stage-2-specific
   module never calls it — but wrong to conclude from that alone. The actual scoring loop lives
   in `backend/db/services/sealed_product_rip_service.py`, which runs Stage 1 AND Stage 2
   candidates through the identical shared scorer (line ~459: "Stage 2: the same scorer, on a
   shifted vector") and, for BOTH stages, computes
   `financial_v4 = project_financial_rip_v4_from_v3_payload(financial)` and
   `overall_v10 = compute_overall_rip_v10(...)`, persisting `financial_rip_v4_*` and
   `overall_rip_v10_*` columns for every candidate regardless of stage. I did not answer from the
   function name alone this time — I traced the object.

A live query against the production-read database on the first pass (still inside the stale
branch's context) used the wrong filter (`financial_rip_v4_rankable IS True`, a boolean column
that is frequently NULL even when the score is genuinely ready) and undercounted coverage as
82/137. Re-querying with the correct filter (`financial_rip_v4_status == 'ready' AND
financial_rip_v4_score IS NOT NULL`) on the same live data shows **137/137 — full coverage, all 8
families**, confirmed below.

## C. Current canonical authority (verified against source, current `main`)

| Model | Canonical version | Evidence |
|---|---|---|
| Financial RIP | `financial_rip_v4_outcome_profile_p95_only_25_20_15_25_10_5` | `scoring_config.py:425`, `CANONICAL_FINANCIAL_RIP_VERSION = FINANCIAL_RIP_V4_VERSION` |
| Overall RIP | `overall_rip_v10_90_financial_v4_10_collector_appeal_v5` | `scoring_config.py:426`, `CANONICAL_OVERALL_RIP_VERSION = OVERALL_RIP_V10_VERSION` |
| Collector Appeal | resolved via `canonical_collector_appeal_version()` (unchanged by this task) | `scoring_config.py:457` |
| Family Rank reader | `product_family_rankings_service.py::_rank_key`/`_canonical` read `overall_rip_v10_score`, `financial_rip_v4_score`, `overall_rip_v10_rankable`, `financial_rip_v4_version`, `overall_rip_v10_version` — the DEDICATED v10/v4 columns, not the generic `overall_rip_score`/`overall_rip_version` columns | `product_family_rankings_service.py:36-52` (verified on current `main`; also covered by the existing `test_canonical_checks_v4_v10_columns_not_the_legacy_v3_v9_columns` and `test_rank_key_and_project_read_the_v4_v10_fields_not_v3_v9` unit tests, both passing) |

**Important nuance found and worth flagging:** the GENERIC `overall_rip_score`/`overall_rip_version`
columns on `simulation_sealed_product_results`, and the entire separate, user-facing **Set RIP
leaderboard** (`pokemon_public_rip_leaderboard_snapshots`, which backs Set Rank — a different
authority from Family Rank), are **still on V9/V3** as of the latest complete publish
(`market_date=2026-08-17`, `overall_rip_version=overall_rip_v9_...`). Migration 072 already
deployed the V10-aware publish RPC (`publish_pokemon_public_rip_leaderboard`), but the daily
publication job has evidently not been re-run to actually promote a V10 snapshot yet. **This does
not affect Family Rank** (which reads `simulation_sealed_product_results` directly, never the
Set-leaderboard snapshot) — but it does affect any research tooling that resolves "the
authoritative calculation run per set" via that leaderboard (see §H).

## D. Stage 2 V4/V10 result

**Yes — Stage 2 SKUs (ETB, Pokémon Center ETB, Enhanced Booster Box) produce persisted, ready
Financial RIP V4 / Overall RIP V10 results on current `main`.** Lineage traced and verified live:

`sealed_product_stage2_rip_service.py` (`compose_stage2_product`, `select_stage2_products`,
`price_stage2_candidates`) → composed outcome vector (random pack outcomes + constant guaranteed
component value) → `sealed_product_rip_service.py`'s shared Stage 2 loop → `build_financial_rip_v3`
→ `project_financial_rip_v4_from_v3_payload` → `compute_overall_rip_v10` → persisted as
`financial_rip_v4_score`/`status`/`version`, `overall_rip_v10_score`/`rankable`/`version` on
`simulation_sealed_product_results`.

Live-query confirmation (re-run with the corrected filter):

```
distinct sealed_product_id with financial_rip_v4_status == 'ready': 137 / 137
distinct sealed_product_id with overall_rip_v10_rankable == True:   137 / 137
Families covered: booster_box, booster_bundle, elite_trainer_box, enhanced_booster_box,
                  half_booster_box, loose_booster_pack, pokemon_center_elite_trainer_box,
                  sleeved_booster_pack  (all 8 — zero families with zero coverage)
```

## E. Family Rank — final contract

- **Population:** every row across every `set_targets` entry whose `calculation_run_id` matches
  that set's authoritative run, filtered to the same `product_family`, gated by `_canonical()` —
  global, dynamic, never local-set (verified again on current `main`; unit tests pass).
- **Comparator (`_rank_key`, verified on current `main`):** `overall_rip_v10_score` (desc) →
  `financial_rip_v4_score` (desc) → `chance_to_recover_cost` (desc) → `product_market_cost` (asc,
  cheaper wins ties) → `sealed_product_id` (deterministic final tie-break). Matches the task's
  stated expected intent exactly, now genuinely on V4/V10.
- **Denominator:** `len(ordered)` over the global per-family cohort (`block["count"]`).
- **Family Tier — IMPLEMENTED this task, not just documented.** `_project()` now emits
  `familyTier` via `assign_composite_tier(overall_rip_v10_score)` (the same S/A/B/C/D/F absolute
  bucketer already used for desirability composite tiers: S≥90, A≥75, B≥55, C≥35, D≥15, F below).
  Tier is derived from the exact same `overall_rip_v10_score` that produced the rank, so rank and
  tier always describe the same cohort by construction. New unit test added and passing
  (`test_family_tier_reuses_the_canonical_composite_bucketer_from_the_v10_score`).
- **Fields exposed by `_project()` now:** `sealedProductId, productName, setId,
  setCanonicalKey, setName, setImage, productFamily, productFamilyLabel, familyRank, familySize,
  familyTier, marketPrice, overallRipScore, overallRipVersion, financialRipScore,
  financialRipVersion, collectorAppealScore, collectorAppealVersion, expectedValue, medianValue,
  p05Value, p95Value, p99Value, chanceToRecoverCost, totalValueToCostRatio, modelBreakEven, ...`
  (plus economics fields already present).

## F/G/H — Coverage before repair, root cause, repair performed

**Before any code change**, coverage of `financial_rip_v4_status == 'ready'` was already 137/137 —
there was no missing-data problem to repair. The only "repair" needed was in my own
investigation method (the wrong boolean-column filter on the first pass) and in a **legacy
research script's authority-resolution dependency**, not in production data:

- **Root cause of the apparent gap (§B):** analyst error (wrong filter column) on the first pass,
  not a data or code defect. Re-verified with the correct filter: full coverage, confirmed twice.
- **A real, separate issue found and fixed:** the shared research helper
  `resolve_authoritative_snapshot()` (`research_cross_format_product_rip.py`) hard-asserts the
  published Set-leaderboard snapshot's `financial_rip_version`/`overall_rip_version` start with
  the literal prefixes `"financial_rip_v3_"`/`"overall_rip_v9_"` (lines 30-31, 71-74) — i.e. it
  was written for, and only works against, a V3/V9-published leaderboard. Since that leaderboard
  hasn't been republished under V10 yet (§C), this legacy helper cannot resolve an authority today
  even though the per-product V4/V10 data is fully ready.
  - **I did not trigger the real production publish pipeline to fix this** — that would write a
    new live Set-leaderboard snapshot visible to real users, and I stopped to ask before taking
    any action with that blast radius. Per your direction, I instead wrote a **read-only**
    workaround for the research script only: `backend/scripts/_run_v4_research_driver.py`
    resolves "the current calculation run per set" directly from
    `simulation_sealed_product_results` wherever `financial_rip_v4_status='ready'` (22 sets, each
    with exactly one unambiguous run id), and resolves each set's real `set_canonical_key` from
    `pokemon_public_rip_leaderboard_rows` (a mapping unaffected by which model version that table
    was last published under). Zero production writes. This lives only in the new research
    branch/worktree.
  - Verified this driver reconstructs each product's *exact* persisted `financial_rip_v4_score`
    to within the same 0.001 tolerance the original V3 script used — this is what surfaced (and
    let me fix) a second real bug: my first cut of the V4 research script called
    `build_financial_rip_v4()` directly on the raw outcome vector, but production computes V4 as
    a **projection from the V3 payload** (`project_financial_rip_v4_from_v3_payload`), for both
    Stage 1 and Stage 2. Fixed to mirror production exactly; reconstruction then matched.
  - Also fixed two latent null-handling bugs in the copied research code
    (`strict_return_dominator`, `summarize_calibration`/`calibration_coherence`) that crashed the
    first time they encountered a metric the V4 projection legitimately leaves absent (e.g.
    `realisticTailMeanRatio` carries no V4 weight). These are exactly the kind of "fix historical
    V3 research code where necessary" items anticipated by the task, now fixed in the V4 sibling
    script only — `research_equal_spend_product_rip.py` (V3, historical baseline) is untouched.

## I. Production coverage after (no rebuild was needed)

| Family | V4-ready SKUs | V10-rankable SKUs |
|---|---:|---:|
| booster_box | 15 | 15 |
| booster_bundle | 23 | 23 |
| elite_trainer_box | 27 | 27 |
| enhanced_booster_box | 2 | 2 |
| half_booster_box | 7 | 7 |
| loose_booster_pack | 22 | 22 |
| pokemon_center_elite_trainer_box | 26 | 26 |
| sleeved_booster_pack | 15 | 15 |
| **Total** | **137** | **137** |

No exclusions to report; the cohort was already complete.

## J/K. Overall Product Rank research — methods tested and diagnostics

Ran the actual matched-capital research (`research_equal_spend_product_rip_v4.py`, a full V4/V10
retarget of the existing, previously-validated equal-spend engine — reusing its loaders,
`build_stage1_product_distributions`, whole-unit quantity search, guaranteed-component handling,
dominance/pairwise/rank-correlation machinery unchanged) against the **real, live, complete
137-SKU/8-family/22-set cohort**. This executed successfully end-to-end; results are real,
computed numbers, not projections from the V3 report.

**Authority:** ad hoc read-only resolution (§H) over 22 sets / 137 SKUs, one 1,000,000-outcome
pack artifact per set (verified `outcome_count == 1_000_000` for every artifact used).

**Candidates evaluated:** Current-unit V4 (negative control, one natural retail unit — rejected as
production ranking per the unchanged comparison-scope policy), Pure RTP, Equal-Spend V4 at fixed
budgets $25/$50/$100/$150/$250/$500, and per-anchor matched-capital comparisons (anchored to each
product's own price as the target budget).

**Coverage by budget** (of 137 total SKUs):

| Budget | Eligible SKUs | Coverage |
|---:|---:|---:|
| $25 | 36 | 26.3% |
| $50 | 41 | 29.9% |
| $100 | 58 | 42.3% |
| $150 | 78 | 56.9% |
| $250 | 106 | 77.4% |
| $500 | 131 | **95.6%** |

**No single tested budget reaches 100%.** Six SKUs (4.4% of the cohort) cost more than $500
(up to $1,339.19) and are excluded at every tested band; a "full-cohort anchor" high enough to
include them (~$1,340+) would force the cheapest SKU ($5.65) into a ~237-unit strategy, which is
both impractical as a "committed capital" story for a normal user and outside the existing
script's own bounded pairwise search parameters (`MAX_QUANTITY=200`).

**Stability and dominance (the genuinely decisive numbers):**

- **Rank correlation across budgets:** median Spearman ρ = **1.0** (both current-vs-equal-spend
  and RTP-vs-equal-spend), across 26 sufficiently-populated set/budget cohorts. Mean absolute
  rank movement 0.19, maximum movement 2.0 (out of cohorts as large as several SKUs), mean top-3
  overlap = 3.0/3 — i.e., budget choice essentially never changes the winner or the top of the
  order within a family/set.
- **Dominance:** 967 primary (5%-tolerance) matched-capital comparisons; **zero** multi-metric
  dominance violations under either current-unit or equal-spend scoring
  (`currentUnitRanksDominatedHigher = 0`, `equalSpendRanksDominatedHigher = 0`). This cohort, on
  V4/V10, produced no case where a weakly-dominated product ranked above its dominator.
- **Three-way agreement** (current-unit / RTP / equal-spend all pick the same winner): 843/967
  (87.2%).
- **Price sensitivity:** effective-pack-cost vs RTP Spearman ρ = −0.47; vs current Financial RIP
  ρ = −0.53 (moderate, not pathological — cheaper effective pack cost does not mechanically buy a
  higher score).
- **Determinism:** confirmed by construction — the engine's own reconstruction check
  (`build_set`) verifies every product's quantity-1 strategy reproduces its exact persisted score
  before any comparison runs; the run failed loudly (twice) during development exactly when it
  should have (wrong V4 code path; wrong `set_canonical_key`), which is itself evidence the
  determinism check is doing real work, not passing trivially.

## L. Final decision

## `OVERALL_PRODUCT_RANK_NOT_APPROVED`

## `BUDGET_SPECIFIC_PRODUCT_RANK_SUPPORTED` (at $500)

**Why not a context-free universal rank:** requirement #5 ("coverage is sufficient for a public
ranking") and #11 ("a rank and its denominator always refer to the exact same cohort") cannot both
be satisfied by any single tested budget or by a practical full-cohort anchor — 4.4% of the
cohort (the most expensive SKUs) is unavoidably excluded from the best-coverage band ($500), and
the alternative (a ~$1,340 anchor) produces an impractical, hard-to-explain comparison for the
cheapest products. A universal "Overall Rank #X/N" would either silently misrepresent N or need
a footnote long enough to fail requirement #10 ("public semantics are understandable").

**Why the budget-specific rank at $500 IS supported:** every other approval requirement is met at
that budget — matched capital (not natural-unit), 95.6% coverage (the best tested), zero
dominance inversions, near-perfect (median ρ=1.0) stability versus every other tested budget
(meaning the *choice* of $500 over $250 barely matters to the resulting order — a materially
stronger result than the historical V3 finding), deterministic, precomputable, and the semantics
are a single honest sentence: *"Ranks this product against every other eligible modeled sealed
product that can be matched to within 5% of $500 of committed capital, using Financial RIP V4 and
Overall RIP V10."* No hidden caveat changes that interpretation for 131 of 137 products; the
remaining 6 are truthfully reported as ineligible at this budget, not silently dropped or
misnumbered.

## M. Winning method (budget-specific)

**Rank at $500** — equal-spend matched-capital comparison: for each eligible product (market price
≤ ~$500 in a feasible whole-unit multiple), score the largest whole-unit quantity purchasable
within the tolerance band around $500 using Financial RIP V4 (projected from V3 exactly as
production does) and Overall RIP V10, then rank descending by that matched-capital Overall RIP
V10 score within the eligible cohort. Comparison scope for THIS rank is
`equal_committed_capital_cross_format`; the pre-existing `within_product_family_only` /
`SEALED_PRODUCT_CROSS_FORMAT_COMPARABLE=False` natural-unit policy is completely unchanged and
untouched.

## N. Production architecture

**Not built.** Per the task's own instructions, Phase 4 (precomputed snapshot, migration,
publication, read contract) is gated on `OVERALL_PRODUCT_RANK_APPROVED`, which this is not. The
budget-specific result is a genuinely useful, positive, documented finding (per the task's own
"do not hide this useful result" instruction) but building its production snapshot/migration
pipeline is future work, not this task — flagged explicitly as a recommendation in §O rather than
started, given the scope already covered in this pass.

## O. Files changed

- `backend/db/services/product_family_rankings_service.py` — added `familyTier` to `_project()`
  via the canonical `assign_composite_tier` bucketer (Phase 1D, code-implemented as required).
- `backend/tests/unit/db/services/test_product_family_rankings_service.py` — added
  `test_family_tier_reuses_the_canonical_composite_bucketer_from_the_v10_score`.
- `backend/scripts/research_equal_spend_product_rip_v4.py` (new) — V4/V10 retarget of the
  existing equal-spend research engine; V3 original preserved untouched as the historical
  baseline. Includes two real bug fixes surfaced by the reconstruction check (V3→V4 projection
  chain; null-safe dominance/calibration functions).
- `backend/scripts/_run_v4_research_driver.py` (new) — read-only authority-resolution workaround
  so the V4 research could run without depending on the not-yet-republished V10 Set-leaderboard.
- `docs/research/OVERALL_PRODUCT_RANK_DECISION_2026-08-22_v2.md` (this file).
- `logs/equal_spend_product_rip_research_v4.json` (generated research artifact; real output from
  the run described in §J/K).

## P. Migrations

None. No schema change was required or made.

## Q. Tests

`d:/EVRCalculator/backend/.venv/Scripts/python.exe -m pytest backend/tests/unit/db/services/test_product_family_rankings_service.py -q`
→ **12 passed** (11 pre-existing + 1 new `familyTier` test).

`d:/EVRCalculator/backend/.venv/Scripts/python.exe -m backend.scripts._run_v4_research_driver`
→ completed successfully; wrote `logs/equal_spend_product_rip_research_v4.json` (real research
run, not a fixture/mock).

## R. Backfill / publication validation

No backfill was needed (§F: coverage was already complete). Sample verification: reconstructed
`financial_rip_v4_score` for "Temporal Forces Pokemon Center Elite Trainer Box (Exclusive)
[Walking Wake]" (a Stage 2, guaranteed-component product) to `29.1638`, matching the persisted
value exactly, confirming the full Stage 2 → V4 projection → persistence lineage end-to-end for a
non-trivial real product.

## S. Commit SHA(s)

See final message after commit (this document is written before the commit step).

## T. Safe integration instructions

This branch (`feature/overall-product-ranking-v10`) touches only:
- `backend/db/services/product_family_rankings_service.py`
- `backend/tests/unit/db/services/test_product_family_rankings_service.py`
- two new backend research scripts under `backend/scripts/`
- this docs file and a generated `logs/` artifact

**No frontend files are touched.** To bring this into the branch containing the completed
Codex/UI frontend work:

1. From the UI branch: `git fetch origin && git fetch <this-branch-remote-if-pushed>`
2. `git merge feature/overall-product-ranking-v10` (or cherry-pick the specific commit SHA(s)
   reported below) — expected to be a clean, conflict-free merge, since this branch never edits
   any file the UI branch is known to have touched (`RipDecisionPage.jsx` and siblings).
3. If `product_family_rankings_service.py` was ALSO touched on the UI branch (it should not have
   been — it's a backend service, not a UI file — but confirm with `git log --follow` before
   merging), resolve by keeping the `familyTier` addition from this branch alongside whatever
   else changed, since they are additive, non-overlapping fields.
4. The frontend does not yet consume `familyTier` — when ready, the exact field to wire is
   `familyTier` on each product row returned by `product_family_rankings_service.py` /
   `targetsPayload.productFamilyRankings.families[family].products[]`, a string one of
   `"S"|"A"|"B"|"C"|"D"|"F"`.
