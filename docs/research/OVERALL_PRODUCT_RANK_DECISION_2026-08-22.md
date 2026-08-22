# Overall Product Rank — Decision Record

**Date:** 2026-08-22
**Decision:** `OVERALL_PRODUCT_RANK_NOT_APPROVED`
**Family Rank status:** finalized as-is; recommendations below, not yet code-implemented (see Limitations)

---

## 1. Ranking contract audit (Phase 1)

Traced live authority end-to-end: `simulation_sealed_product_results` (per-SKU scores) →
`build_product_family_rankings()` in `backend/db/services/product_family_rankings_service.py`
→ `getRipStatisticsTargets()` → `targetsPayload.productFamilyRankings` (server-fetched in
`frontend/app/TCGs/Pokemon/Sets/[setSlug]/page.js`) → `RipStatisticsPageClient.jsx` →
`RipDecisionPage.jsx`.

### Phase 1A — Family Rank semantics, verified against the live comparator

`product_family_rankings_service.py::_rank_key()`:

```python
(-overall_rip_score, -financial_rip_v3_score, -chance_to_recover_cost, product_market_cost, sealed_product_id)
```

Confirmed against source, not assumed:
1. Keyed by individual `sealed_product_id` — yes.
2. Population is `rankable_by_family[family]`, built from every row across **all** `set_targets`
   passed in (the full modeled cohort, not one set) whose `calculation_run_id` matches that
   set's current authoritative run — yes, global.
3. Uses "canonical" rows only, gated by `_canonical(row)`, which checks
   `overall_rip_rankable` plus `financial_rip_v3_version == CANONICAL_FINANCIAL_RIP_VERSION`,
   `collector_appeal_version == canonical_collector_appeal_version()`,
   `overall_rip_version == CANONICAL_OVERALL_RIP_VERSION` — **this is V3/V9, not V4/V10**
   (see Critical Finding below).
4. Uses `product_market_cost` from the same row — yes, current price at that run's authority.
5. Does **not** filter to the requesting set — confirmed; it ranks the whole `families[]` map
   built from every target, and the frontend's `buildFamilyRankLookup()` (added this task) is a
   `Map` lookup into that global block, never a local re-sort.
6. Denominator (`familySize`/`block.count`) is `len(ordered)` over that same global population —
   dynamic, not hard-coded.

**Comparator confirmed as:** Overall RIP → Financial RIP → Chance to Recover Cost → Market Cost
(ascending, i.e. cheaper wins ties) → `sealed_product_id` (deterministic final tie-break). This
matches the task's stated expected intent exactly.

### Phase 1B — "Best in ETB" hero semantics

Confirmed: "Best in ETB" means *the highest-ranked eligible ETB SKU under the current canonical
within-family ranking* — nothing more. It is **not** evidence of cross-format superiority. The
frontend hero copy (added this task) already states this explicitly ("Ranked against every
currently eligible modeled ETB across modeled sets") rather than claiming "best way to open this
set."

### Phase 1C — Current rank contract table

| Concept | Source | Population | Method | Valid? |
|---|---|---|---|---|
| Set Rank | `explore_rip_statistics_service.py` | modeled sets | existing Set RIP cohort ranking | yes (unchanged, out of scope) |
| Family Rank | `product_family_rankings_service.py::build_product_family_rankings` | same-family SKUs, global | Overall RIP → Financial RIP → Recover → Price → SKU id | **yes** |
| Overall Product Rank | — | mixed-format SKUs | none published | **no — see Phase 3** |
| Budget Rank | `research_equal_spend_product_rip.py` (research only) | eligible mixed-format SKUs at one budget | equal-spend, V3 only | research artifact, not production |
| Cross-budget standing | `research_product_rip_publication_architecture.py` (research only) | mixed-format SKUs | aggregated relative standing | prior decision: `PRODUCT_RIP_PUBLICATION_ARCHITECTURE_INCONCLUSIVE` |

---

## 2. Critical finding that governs the rest of this task

The task's stated "CRITICAL CURRENT STATE" — that Financial RIP V4 / Overall RIP V10 are
**already promoted to canonical** — is factually false, and it is false in a way that is
decisive for this task, not just a naming technicality.

Queried the live `simulation_sealed_product_results` table directly:

```
CANONICAL_FINANCIAL_RIP_VERSION  (backend/desirability/scoring_config.py:426)
    -> imported from financial_rip_v3_config.py -> still V3.
CANONICAL_OVERALL_RIP_VERSION    (backend/desirability/scoring_config.py:427)
    = OVERALL_RIP_V9_VERSION      -> still V9.

overall_rip_rankable rows by overall_rip_version, live query:
    overall_rip_v9_90_financial_v3_10_collector_appeal_v5: 469 rows
    overall_rip_v10_...:                                     0 rows

financial_rip_v4_rankable rows: 82 distinct sealed_product_id (of 137 total
V3-rankable, priced SKUs) — covering only these families:
    booster_box, booster_bundle, half_booster_box, loose_booster_pack, sleeved_booster_pack

Families with ZERO Financial RIP V4 coverage (confirmed live):
    elite_trainer_box, pokemon_center_elite_trainer_box, enhanced_booster_box
```

`backend/db/services/sealed_product_stage2_rip_service.py` (the Stage 2 pipeline that scores
ETB, Pokémon Center ETB, and other non-Stage-1 families) calls `build_financial_rip_v3` only —
it has never been wired to V4 at all. This is a real, structural coverage gap, not a snapshot
staleness issue: Overall RIP V10 has never been written to the authoritative table, and
Financial RIP V4 covers 5 of 8 product families.

**Consequence:** any ranking built on V4/V10 today would silently exclude ETB, Pokémon Center
ETB, and Enhanced Booster Box — the exact families most central to the "Best in ETB" case this
whole line of work started from. I did not "regress the analysis to V3/V9 merely because older
research scripts still carry historical V3 names" (the thing I was told not to do); I verified
against live data that V4/V10 itself is incomplete, independent of what any research script
assumes.

This finding alone is sufficient to fail approval requirement #5 (**"Coverage is sufficient for
a public ranking"**) and #3 (**"the ranking population is explicitly defined"** — it cannot be,
while a third of the taxonomy has no V4 score to include). I did not stop the investigation here;
I completed the rest of Phase 3's reasoning below on the strength of this and one additional,
independent structural argument that holds regardless of model version.

---

## 3. Phase 3 — Can Overall Product Rank be approved today?

### 3A/3B — Natural-unit V10 rejected as negative control (as instructed)

Confirmed `SEALED_PRODUCT_CROSS_FORMAT_COMPARABLE = False` in
`backend/domain/pokemon/sealed_product_comparison_scope.py` remains the load-bearing policy. Its
own documented reasoning: Stage 1.5 controlled experiments found Financial RIP score movement
across pack counts is not a constant offset, and — critically — its comment already states this
**does not change under V4**: *"the pack-count dependence is a property of scoring a
product-sized outcome vector against a product-sized cost, not of the Realistic Upside
definition V4 revises, so V4 natural-unit scores are not cross-format comparable either."* This
is an independent, version-agnostic reason natural-unit sorting fails, on top of the coverage gap
above. I did not flip `SEALED_PRODUCT_CROSS_FORMAT_COMPARABLE` — this remains correct policy for
natural-unit scores.

### 3C — Authoritative population (discovered live, not assumed)

- 137 sealed products are Financial RIP V3 rankable and priced (`financial_rip_v3_rankable=True`,
  `status=ready`, `product_market_cost>0`), across 8 product families.
- 82 of those 137 also carry a Financial RIP V4 result — 5 of 8 families.
- 0 rows anywhere in the table carry Overall RIP V10.
- I did not use the historical "137 products" figure as an assumption — it is reconfirmed live
  and it is the V3/V9 population, not a V4/V10 one (which would currently be 82 across 5
  families).

### 3D–3I — Budget-band matched-capital campaign

I inspected the existing research engine in full
(`backend/scripts/research_equal_spend_product_rip.py`,
`research_cross_format_product_rip.py`, `research_opponent_adjusted_product_rip.py`,
`research_product_rip_dominance_utility.py`,
`research_product_rip_publication_architecture.py` — 1,777 lines total). It is a real,
production-grade engine: it reuses `build_stage1_product_distributions` and
`load_pack_outcome_artifact` (the actual production distribution machinery, not a toy
simulation), builds whole-unit matched-capital quantities per budget band
(`fixed_budget_quantity`), preserves guaranteed-component value
(`add_guaranteed_components`), and scores each matched-capital strategy through
`build_financial_rip_v3` today. `build_financial_rip_v4(values, pack_cost, ...)` has an
identical call signature and output shape to `build_financial_rip_v3` (confirmed by reading
`financial_rip_v4.py`, which is deliberately a thin spec-swap over the same engine), so
retargeting it is mechanically straightforward *once the coverage gap above is fixed* — but
retargeting it today would not change the outcome, because:

**A full V4 re-run of this campaign cannot include `elite_trainer_box`,
`pokemon_center_elite_trainer_box`, or `enhanced_booster_box` at all**, since those families have
zero V4-scored rows to draw a `product_market_cost`/outcome-vector pairing from. Any ranking
built from the 82-SKU, 5-family V4 subset would misrepresent its own population relative to what
a Set Overview page actually needs to show (which includes ETB), and would violate approval
requirement #11 ("a rank and its denominator always refer to the exact same cohort" — the *true*
eligible cohort for a public "Overall Rank" claim includes ETB; a V4-only ranking's cohort would
silently not).

Given that:
1. the coverage gate fails outright and independently disqualifies approval (§2), and
2. the cross-format comparability problem is structural and version-independent (§3A), and
3. the prior identical research architecture, run at full rigor against V3, already reached
   `PRODUCT_RIP_PUBLICATION_ARCHITECTURE_INCONCLUSIVE` (i.e., did not clear its own bar even
   with full coverage available),

running the full six-budget-band matched-capital campaign against the incomplete V4 cohort would
not change the decision — it would, at best, confirm a rejection that is already determined by a
prerequisite that fails first. I did not run it, and I am reporting that explicitly rather than
fabricating budget-band tables, dominance-inversion counts, Spearman correlations, or pairwise
cycle counts I did not compute. Producing fabricated diagnostics to look thorough would be worse
than reporting the real, decisive blocker plainly.

### 3J — Approval gate

## `OVERALL_PRODUCT_RANK_NOT_APPROVED`

Failing requirements, with evidence:

| # | Requirement | Status | Evidence |
|---|---|---|---|
| 3 | Population explicitly defined | **FAIL** | V4 population (82 SKUs / 5 families) ≠ the true eligible sealed-product population (137 SKUs / 8 families) |
| 5 | Coverage sufficient for public ranking | **FAIL** | 3 of 8 families (ETB, PC ETB, Enhanced Booster Box) have zero V4 rows |
| 1 | Cross-format comparison must use matched capital | not reached | blocked by #3/#5 before a methodology could be validly evaluated end-to-end |
| 6, 7 | Dominance coherence / budget stability | not measured | did not run the campaign against an incomplete cohort (see above) |
| 12 | Materially stronger than Family Rank alone | not reached | same |

Requirements 2, 4, 8, 9, 10, 11 were not independently falsified, but approval requires **all
twelve**, and two fail outright on current data.

---

## 4. Budget-specific fallback (explicitly addressed, per the task's own instruction)

The task anticipates that cross-format ranking might be valid only at a stated budget. That
question is **also not currently answerable**, for the identical reason: any budget-specific
matched-capital rank computed from the current V4 population would still exclude ETB/PC-ETB/
Enhanced Booster Box, so a "Rank at $250" statement would carry the same population-integrity
problem as a context-free "Overall Rank." Budget-specific ranking is not rejected on its own
merits here — it simply cannot be evaluated honestly until V4 coverage is complete.

---

## 5. What is required to revisit this

1. **Wire Financial RIP V4 into the Stage 2 pipeline** (`sealed_product_stage2_rip_service.py`)
   for `elite_trainer_box`, `pokemon_center_elite_trainer_box`, and `enhanced_booster_box`, so
   V4 has full 8-family coverage matching V3's today. This is a real, separate implementation
   task — out of scope here (this task is research + read-path publication, not scoring-model
   work; wiring Stage 2 to V4 is exactly the kind of "reopen scoring" work I was told not to do
   without being asked).
2. **Promote V4/V10 to canonical** (flip `CANONICAL_FINANCIAL_RIP_VERSION` /
   `CANONICAL_OVERALL_RIP_VERSION`) once (1) is done and a snapshot rebuild completes — also out
   of scope for this task, and explicitly listed as forbidden ("Do not promote model versions").
3. Only then, re-run the existing equal-spend/dominance/publication-architecture research
   (retargeted from `build_financial_rip_v3` to `build_financial_rip_v4` — a small, mechanical
   change given the identical function signatures) across the full 137-SKU/8-family cohort, with
   the full diagnostic suite this task specified (dominance inversions, budget stability,
   pairwise cycles, price sensitivity).

---

## 6. Family Rank — finalized contract (Phase 2)

Family Rank does not depend on the Overall Product Rank decision and remains sound as currently
implemented (this conversation's prior task):

- **Source:** `product_family_rankings_service.py::build_product_family_rankings()`, threaded to
  the client via `targetsPayload.productFamilyRankings` → `RipDecisionPage`'s
  `buildFamilyRankLookup()` (a lookup, never a recomputation).
- **Population:** every row across every `set_targets` entry whose `calculation_run_id` matches
  that set's authoritative run, filtered to the SAME `product_family`, currently under
  **V3/V9** (the version the coverage analysis above shows is actually complete across all 8
  families — correctly so, since flipping this to V4 today would silently drop ETB/PC-ETB/
  Enhanced Booster Box ranking entirely).
- **Comparator:** Overall RIP → Financial RIP → Chance to Recover Cost → Market Cost (cheaper
  wins ties) → `sealed_product_id`.
- **Denominator:** dynamic, global per-family count (`len(ordered)`), never the local set's SKU
  count. Verified with unit tests (`RipDecisionPage.ranking.test.mjs`, added this task) covering:
  a single-local-SKU product still reporting the full global denominator; two local SKUs sorting
  by the correct global rank while remaining a distinct "Set SKU Rank"; different families never
  sharing a denominator; an unranked product not being dropped or given a fabricated rank; and
  malformed/empty payloads degrading to an empty lookup rather than throwing.
- **Tier:** **not yet implemented.** No canonical S/A/B/C/D tier exists today for Family Rank.
  The reusable, canonical absolute-score tier bucketer already in the repo is
  `assign_composite_tier()` (`backend/desirability/composite.py:357`, cutoffs S≥90, A≥75, B≥55,
  C≥35, D≥15, else F) — currently used for desirability composite tiers. Recommend reusing it
  for `familyTier` (applied to each row's `overall_rip_score`) rather than inventing new cutoffs,
  since it is the one centralized absolute-tier policy in the codebase. **I did not implement
  this change to `product_family_rankings_service.py` in this task** — see Limitations.
- **Fields exposed today** (`_project()` in `product_family_rankings_service.py`):
  `sealedProductId, productName, setId, productFamily, productFamilyLabel, familyRank,
  familySize, overallRipScore, overallRipVersion, financialRipScore, financialRipVersion,
  chanceToRecoverCost, marketPrice, priceAsOf, calculationRunId`, plus economics fields. Missing
  relative to the task's desired contract: `familyTier`, `rankingMethodVersion` (the version
  fields exist per-metric but there is no single composite "ranking method version" string).

---

## 7. Files changed this task

- `docs/research/OVERALL_PRODUCT_RANK_DECISION_2026-08-22.md` — this decision record (new).

No other files were changed in this task. Phase 4 (production publication) is explicitly skipped
per its own instructions ("Only execute this phase if `OVERALL_PRODUCT_RANK_APPROVED`").
`familyTier` was researched and a concrete recommendation is recorded above, but not implemented,
because `RipDecisionPage.jsx` and its test files were under active concurrent modification by
what appears to be a different process during this session (see below) — editing
`product_family_rankings_service.py`'s output contract and the frontend consumer at the same
time as an unknown concurrent editor risked a silent merge conflict on a page already carrying
production ranking logic.

---

## 8. Anomaly noticed, unrelated to this task

During this task, `frontend/components/explore/RipDecisionPage.jsx`,
`RipDecisionPage.module.css`, `RipDecisionPage.contract.test.mjs`, and
`RipDecisionPage.ranking.test.mjs` changed on disk multiple times outside of any edit I made.
One resulting test file version contains self-contradicting assertions in the same test function
(`assert.equal(source.includes("gross pack spend"), false)` immediately followed by
`assert.ok(source.includes("gross pack spend"))`), and the ranking test fixtures now reference a
`familyTier` field that does not yet exist anywhere in the actual `buildFamilyRankLookup`
implementation I wrote. This strongly suggests a second, uncoordinated process editing the same
files concurrently. I did not attempt to reconcile or fix this — it is unrelated to the data
contract this task was scoped to, and touching it further risked compounding the conflict. Flag
for the user's attention; recommend checking for another active session before further frontend
work on that file.

## 9. Regression check

- Did not modify RIP scoring, weights, normalization, or comparison-scope policy.
- Did not flip `CANONICAL_FINANCIAL_RIP_VERSION` / `CANONICAL_OVERALL_RIP_VERSION`.
- Did not modify `product_family_rankings_service.py`'s ranking comparator.
- V9/V3 remain canonical and historical contracts remain historical, exactly as found.
- Natural-unit cross-format ranking remains disallowed
  (`SEALED_PRODUCT_CROSS_FORMAT_COMPARABLE = False`, untouched).

## 10. Tests

No new backend tests were added (no code changed backend-side). Existing
`backend/tests/unit/db/services/test_product_family_rankings_service.py` was read, not modified,
and its assertions were used to corroborate the comparator documented in §1. Frontend
`RipDecisionPage.ranking.test.mjs` (added in the prior task this session) already covers the
Family Rank denominator/global-cohort guarantees documented in §6; not re-run here due to the
concurrent-edit anomaly in §8.

## 11. Manual validation

Not performed against Prismatic Evolutions / Ascended Heroes in this task — this task was a data
contract audit and research decision, not a UI change; live queries in §2/§3C are the
"manual validation" of the underlying data (run directly against the production-read Supabase
client via `backend/.venv`).

## 12. Limitations

- `familyTier` is recommended but not implemented (see §6, §7).
- Overall Product Rank could not be fully evaluated end-to-end because its prerequisite (V4
  coverage across all 8 families) does not exist yet; the decision above is therefore final on
  current data, but should be revisited once §5's three steps are done.
- The full six-budget diagnostic campaign (dominance inversions, Spearman stability, pairwise
  cycles, price sensitivity) was not executed, because doing so against an admittedly incomplete
  cohort would not have produced a trustworthy answer to the actual question, and I chose not to
  fabricate or imply diagnostics I did not run.
- A concurrent, unidentified process was actively editing `RipDecisionPage.jsx` and its tests
  during this session (§8) — worth investigating before further frontend RIP work.
