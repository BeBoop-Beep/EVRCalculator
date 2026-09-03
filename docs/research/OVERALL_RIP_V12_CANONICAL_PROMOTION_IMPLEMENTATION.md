# Overall RIP V12 Canonical Promotion — Implementation & Decision Record

## Decision

`OVERALL_RIP_V12_CANONICAL_PROMOTION_BLOCKED_V12_PERSISTENCE_MIGRATIONS_NOT_APPLIED_ZERO_LIVE_READY_ROWS`

Phase 2's hard blocker (Product Detail V12 gap) was genuinely closed in code this
session, with real tests, verified to pass. Phase 11's promotion gate was then
evaluated against the **live** database, and condition A (V12 shadow readiness:
all eligible rows ready) fails at the most fundamental level possible: the V12
persistence columns and the Chase Accessibility snapshot table **do not exist
in the live schema at all**. Zero rows can be V12-ready, by construction, not
because of an authority mismatch or a version drift, but because nothing has
ever been written there. Promotion (Phases 12-14) was correctly NOT attempted.

## Live-database evidence (read-only queries, this session)

```
SELECT overall_rip_v12_score FROM simulation_sealed_product_results LIMIT 5;
  -> Postgres 42703: column does not exist

SELECT * FROM pokemon_set_chase_accessibility_snapshot_latest LIMIT 3;
  -> PostgREST PGRST205: table not found in schema cache
     (suggests the unrelated pokemon_set_chase_economics_snapshot_latest)

SELECT financial_rip_v4_score, financial_rip_v4_version,
       collector_appeal_score, collector_appeal_version
  FROM simulation_sealed_product_results
  WHERE financial_rip_v4_score IS NOT NULL LIMIT 5;
  -> populated: financial_rip_v4_outcome_profile_p95_only_25_20_15_25_10_5,
     collector_appeal_v5_contextual_roster_h_only_d_baseline_up4_down2
```

Counts: `sets`=210, `sealed_products`=1722, rows with `financial_rip_v4_score`
populated=1356, rows with `overall_rip_v10_score` populated=965.

This confirms 2 of the 3 V12 pillars (Financial RIP V4, Collector Appeal V5)
are live and populated; the third (Chase Accessibility V1) and the V12
persistence layer itself are code-complete (unit-tested,
`sealed_product_rip_finalization_service._overall_rip_v12_for`,
`compute_overall_rip_v12`) but have never run against real data, matching
the not-yet-applied migrations this program's own runbook
(`docs/research/OVERALL_RIP_ACCESSIBILITY_ARCHITECTURE_CLOSURE.md`, and this
prompt's own Phase 15 ordering: "(1) Chase Accessibility migration 077, (2)
V12 sealed-product migration") always anticipated.

## Phase 2 — Product Detail V12 gap: CLOSED

`ProductRipSection.jsx` previously rendered a hardcoded
`"Overall RIP = 90% Financial RIP + 10% Collector Appeal"` string and consumed
only flat V10 fields. This session:

1. **`backend/db/services/product_family_rankings_service.py`** — added the
   five `overall_rip_v12_*` columns to `RESULT_FIELDS` and a pure, additive
   `overallRipV12` passthrough field to `_project()`'s output. `_rank_key`
   and `_canonical` are untouched — ranking order still keys on V10 only.
2. **`backend/db/services/pokemon_sealed_product_detail_service.py`** — added
   `_public_rip_contract_v11_shadow(ranking)`, a pure passthrough that wraps
   the persisted `overall_rip_v12_payload` (score/status/statusReason/
   rankable/version/components/missingInputs, plus its own embedded
   weights/effectiveWeights) into the same `publicRipContractV11` shape
   `backend/desirability/public_rip_contract_v11.py` already defines for Set
   RIP, so the existing shared frontend selector can render it without a
   second implementation. Also added top-level `overallRipV10`/
   `financialRipV4` shape objects (`leaderNormalizedScore`/`rank`/`tier`/
   `cohortSize`/`status`) — a relabeling, not new data — of the fields the
   contract already returned, because `canonicalRipV7.mjs`'s
   `resolveCanonicalRipV7` (used by the shared selector's V10 fallback) reads
   that exact shape and would otherwise render "unavailable" for a payload
   that has V10 data.
3. **`frontend/components/pokemon/sealed-product-detail/ProductRipSection.jsx`**
   — replaced the hardcoded formula string with
   `<OverallRipExplanationHierarchy sources={[rip]} />`, the SAME shared
   component Set RIP/Set Analysis already use. No new arithmetic anywhere in
   the frontend.
4. Verified: a standalone Node script (ad hoc, not committed) exercising
   `selectOverallRipExplanationHierarchy` against both the V10-only shape and
   a synthetic V12-shadow shape produced the correct 90/10 and 86/4/10
   headlines respectively, and an unavailable-V10 input rendered
   "unavailable" rather than a fabricated headline.

Tests added and passing:
- `backend/tests/unit/db/services/test_pokemon_sealed_product_detail_service.py`
  — 4 new tests (top-level V10 shape correctness, shadow V12 passthrough,
  unavailable-V12 honesty). File: 19/19 passing.
- `backend/tests/unit/db/services/test_product_family_rankings_service.py`
  — 1 new test proving V12 passthrough never reorders the V10-ranked cohort.
  File: 19/19 passing.
- `frontend/components/pokemon/sealed-product-detail/SealedProductDetail.contract.test.mjs`
  — updated to assert the hardcoded string is GONE and the shared component
  is used instead. File: 11/11 passing.
- `frontend/components/explore/OverallRipExplanationHierarchy.contract.test.mjs`
  — unaffected, still 12/12 passing (proves the shared component itself was
  not weakened by this integration).

Product Detail stays Plus-tier: no Premium Chase Efficiency / O_budget data
was added to this surface.

## Phases 3-5 — Shadow cohort / readiness gate / ranking comparison

Attempted against live data (per the coordinator's explicit instruction to
try before concluding infeasibility). Result: **not computable**, because
zero live rows carry a V12 score (see evidence above). No Spearman/Kendall/
Top-N/movement numbers are reported, because fabricating them from a cohort
that does not exist would misrepresent the promotion decision. The formula's
correctness (`compute_overall_rip_v12`, `_overall_rip_v12_for`) is verified
at the unit level (existing repo test suites,
`backend/tests/unit/db/test_sealed_product_rip_finalization_service_v12.py`
et al., not modified or re-litigated this session) — that is a code-substrate
finding, not a live-cohort finding, and this record does not conflate the two.

A machine-readable dry-run artifact recording this honestly is at
`docs/research/overall_rip_v12_dry_run_cohort_report.json`.

## Phases 6-10 — Family/Set RIP/budget/Explore rankings, public contract precheck

Not attempted beyond Phase 6's minimal shadow-passthrough addition in
`product_family_rankings_service.py` (above). Given Phases 3-5 could not
produce a real ranking-movement comparison, further cutover-support work in
`set_rip_service.py`, budget ranking scripts, and the Explore/main rankings
client would be built and "tested" only against synthetic fixtures with no
live corroboration — which is a materially weaker claim than what Phase 11's
gate requires, so it was not pursued this session in the interest of not
overstating readiness.

## Phases 11-14 — Promotion gate and canonical selector changes

**Not executed.** Phase 11 condition A fails outright (see evidence above).
`CANONICAL_OVERALL_RIP_VERSION`, `canonical_public_rip_contract_version()`,
and all other canonical constants are **unchanged** — still V10 /
`PUBLIC_RIP_CONTRACT_V10_VERSION`. No snapshot/publication expectation files
were changed (Phase 14 not applicable while Phase 11 fails).

## Phase 15 — Migration/deployment runbook

Confirmed, not altered: the order documented in this prompt (Chase
Accessibility migration 077 → V12 sealed-product migration → backend deploy →
build coherent Accessibility rows → finalize/build V12 → verify readiness →
publish → frontend deploy) matches what this session's live-database
inspection actually found missing. No migrations were applied, drafted, or
run.

## Phase 16 — Security/entitlements

Unaffected by this session's changes. `ProductRipSection.jsx` remains gated
by the existing Plus-tier `entitled` check in `SealedProductDetailClient.jsx`
(untouched). No Premium Chase data was added to any Plus surface. The new
`publicRipContractV11`/`overallRipV12` fields are additive and carry the same
class of information (Overall RIP composition) already exposed under V10 —
no new data category crossed a tier boundary.

## Phase 17 — Performance / EV-representativeness regression

No new queries were added to any per-request hot path: the V12 columns added
to `RESULT_FIELDS` ride the same single batched
`simulation_sealed_product_results` read `product_family_rankings_service.py`
already performs; `pokemon_sealed_product_detail_service.py`'s new shadow
block is a pure in-memory passthrough of data already fetched by the existing
`_published_rankings`/`simulation_sealed_product_results` reads — no new
table, no N+1.

`backend/scripts/audit_ev_representativeness_coverage.py` was re-run this
session against live data: `supported_current_sets=22`, `healthy=22`,
`legitimate_no_headline=0`, `missing=0`, `wrong_run=0`,
`version_mismatch=0` — identical to the prior known-good state recorded in
project memory. No regression; the EV pipeline was not touched.

## Phase 18 — Tests (exact counts)

| Suite | Result |
|---|---|
| `test_pokemon_sealed_product_detail_service.py` | 19 passed (15 pre-existing + 4 new) |
| `test_product_family_rankings_service.py` | 19 passed (18 pre-existing + 1 new) |
| `SealedProductDetail.contract.test.mjs` | 11 passed |
| `OverallRipExplanationHierarchy.contract.test.mjs` | 12 passed |
| `test_public_rip_contract_v11.py` | 10 passed |
| `test_explore_rip_statistics_service.py` | 24 passed, 6 failed |

The 6 failures in `test_explore_rip_statistics_service.py` are in a file this
session did **not** modify (`backend/db/services/explore_rip_statistics_service.py`
and its test file were already `M`odified in `git status` before this session
began — concurrent, in-flight work from a prior session/prompt). Baseline
identity proof: `git diff --stat` shows zero lines touched by this session in
either file, so whatever state produced these 6 failures was already present
at session start and is unrelated to this session's Phase 2 work. Root cause
(for the record, not fixed here — out of scope, would touch concurrent work):
the test's fake Supabase `_Client` does not register a handler for the
`pokemon_set_chase_accessibility_snapshot_latest` table that
`_attach_public_rip_contract`'s new batched Accessibility read now queries.

## Phase 19 — Dry-run artifact

`docs/research/overall_rip_v12_dry_run_cohort_report.json` — read-only,
records live counts, the missing-schema evidence, and an explicit refusal to
fabricate a ranking comparison. No production writes.

## Phase 20 — This document.

## Migrations / deployment / publication status

**None applied. None run. None simulated as if run.** All work this session
was source-code and test changes plus read-only SELECT queries.

## Concurrent work preserved

This session touched only: `backend/db/services/product_family_rankings_service.py`,
`backend/db/services/pokemon_sealed_product_detail_service.py`,
`frontend/components/pokemon/sealed-product-detail/ProductRipSection.jsx`,
`frontend/components/pokemon/sealed-product-detail/SealedProductDetail.contract.test.mjs`,
`backend/tests/unit/db/services/test_pokemon_sealed_product_detail_service.py`,
`backend/tests/unit/db/services/test_product_family_rankings_service.py`, and
created this doc plus the dry-run JSON. Pre-existing uncommitted work in
`explore_rip_statistics_service.py`, its test file, `RipStatisticsPageClient.jsx`,
`PokemonSetAnalysisClient.jsx`, and the untracked `OverallRipExplanationHierarchy*`
files was left exactly as found — read but not edited.

## Rollback considerations

Everything in this session is additive and inert while `CANONICAL_OVERALL_RIP_VERSION`
stays V10: `overallRipV12` is a new key nothing reads for ranking or
canonical scoring, and `publicRipContractV11`/`overallRipV10`/`financialRipV4`
on the product detail payload are new, optional keys existing consumers
ignore. Reverting is a plain revert of the listed files with no data
migration implications, since no schema or data was touched.

## 2026-09-02 (later session) — Independent re-verification after externally-reported migration/backfill

**Decision: `OVERALL_RIP_V12_CANONICAL_PROMOTION_BLOCKED_BUDGET_RANKING_V12_AUTHORITY_WIRING_INCOMPLETE`**

External work (not performed by this session) reportedly applied Chase
Accessibility migration 077 and the V12 sealed-product persistence migration
to production, and ran the finalization pipeline. This session independently
re-verified every claimed number directly against the live database
(read-only) rather than trusting the report, using ad hoc scripts equivalent
in method to `audit_ev_representativeness_coverage.py`'s live-query pattern.

### Independent verification (own numbers, computed from raw live rows)

- Migrations: CONFIRMED applied — `simulation_sealed_product_results` now has
  `overall_rip_v12_score/version/rankable/status/payload`;
  `pokemon_set_chase_accessibility_snapshot_latest` exists and is populated.
- Accessibility snapshot for 2026-09-02: **22/22 ready**, `mapped_hc_mass == 1`
  for all 22 (own query, matches claim).
- Sealed-product rows with `overall_rip_v12_score` populated: **138/138**,
  all `overall_rip_v12_status == "ready"` (own query, matches claim).
- Version-mismatch count: **0** (independently checked all 138 rows'
  `financial_rip_v4_version`, `collector_appeal_version`,
  `overall_rip_v12_version` against the exact canonical identity strings).
- Formula-reconstruction check: **0/138 mismatches** — for every row,
  `0.86*financial + 0.04*(100*A_raw/(A_raw+0.002)) + 0.10*collector`
  reconstructed from the row's own persisted `overall_rip_v12_payload.components`
  matches the persisted `overall_rip_v12_score` to float tolerance.
- Ranking comparison (own computation, all 138 rows, not a sample):
  Spearman **0.996140** (claimed 0.996132 — negligible, consistent with
  tie-handling method differences), mean abs rank movement **2.6377**
  (claimed 2.6377, exact), max rank movement **9** (exact), Top-5 overlap
  **4/5** (exact), Top-10 overlap **8/10** (exact), same-set reversals
  **0 of 398 pairs** (exact).
- Product-family leader changes: independently confirmed exactly
  **Enhanced Booster Box** (Mega Evolution -> Journey Together) and
  **Loose Booster Pack** (Paradox Rift -> 151) differ; the other 6 families'
  leaders are unchanged. Traced both flips to their `overall_rip_v12_payload`
  components: in each case V10's Financial+Collector components are
  near-tied between the old and new leader, and Chase Accessibility's raw
  value (and therefore `A_score` contribution) is what tips the order —
  a legitimate, explainable effect of the new pillar, not a bug.

**Conclusion: the externally-reported unblock is real and its numbers are
independently corroborated.** No discrepancy found between the claimed and
independently-recomputed figures beyond immaterial floating-point/tie-order
noise in the Spearman coefficient.

### Phase 11 gate re-evaluation (own evidence)

- **A (shadow readiness):** PASS — 138/138 eligible current rows ready; 22/22
  Accessibility rows ready with full mapped HC mass.
- **B (authority):** PASS — 0 mismatched-run rows found among the 138 (all
  carry `status: ready`; the authority-mismatch code path is exercised by
  the existing `test_authority_mismatch_rejected_even_though_row_is_ready_and_valid`
  unit test from the "Prompt 3" pass, which remains unmodified and passing).
- **C (versions):** PASS — 0 wrong-version rows found independently.
- **D (ranking):** PASS — movement is modest (Spearman 0.996), the two
  family-leader flips are individually traced and explained by Accessibility's
  legitimate contribution, not an anomaly.
- **E (Set RIP V12 reconstruction):** Was NOT implemented by the prior
  ("Prompt 3") pass. Implemented for real this session (see below). PASS
  after implementation.
- **F (budget rankings V12):** Was NOT implemented by the prior pass.
  Partially implemented for real this session: the V12 budget-scaled formula
  itself is now computed and unit-tested as a shadow/additive field (see
  below), but the live budget-ranking publish pipeline's sort/persistence
  authority was NOT re-wired to use it (would require a new, unapplied
  migration on `budget_product_ranking_rows`/`_snapshots` plus threading a
  live Accessibility read through `scripts/build_budget_normalized_product_rankings.py`
  and `publish_budget_product_rankings_if_ready.py`, none of which this
  session had a safe remaining margin to implement, wire, and fully regression
  -test responsibly). **FAILS as a complete gate** — genuinely attempted, not
  hand-waved, but not fully closed.
- **G (UI version-aware):** Spot-checked. `ProductRipSection.jsx`'s shared
  `OverallRipExplanationHierarchy` renders correctly off the shape
  `_public_rip_contract_v11_shadow` produces from a REAL persisted
  `overall_rip_v12_payload` (previously only exercised against synthetic
  fixtures) — `pytest backend/tests/unit/db/services/test_pokemon_sealed_product_detail_service.py`
  passes unmodified against the same code (19/19); this session did not need
  to change that file since it was already payload-shape-correct against a
  live row. PASS.
- **H (security):** No new server projections added. `overallRipV12`/
  `publicRipContractV11` remain the same non-canonical, additive fields
  reviewed previously. PASS.
- **I (performance):** No new per-request query paths were added this
  session; `product_family_rankings_service.py`'s changes are pure in-memory
  field-selection logic on rows already fetched by the single existing batch
  read. PASS.
- **J (regressions):** Full `backend/tests/unit/desirability/` suite:
  **1926 passed, 73 failed** — identical count and identical failing file set
  (`test_treatment_market_prestige_v3_round20-24.py`) as the prior session's
  own recorded baseline. `backend/tests/unit/db/services/` (excluding the
  same pre-existing environment-broken files already documented: missing
  `jwt` module, unrelated billing): baseline-identity PROVEN by `git stash`
  of exactly this session's 4 changed files — the same 172 failures
  (`test_pokemon_public_snapshot_service.py`,
  `test_pokemon_set_rip_projection_readers.py`,
  `test_public_rip_publication_contract.py`) occur identically with this
  session's changes stashed out, confirming zero regression. PASS.

**Overall Phase 11 result: FAILS on gate F.** Per the explicit instruction to
attempt E/F for real rather than declaring them blocked without trying, both
were substantively implemented this session (E fully, F partially); F's
remaining live-authority wiring is the specific, well-evidenced reason
canonical promotion (Step 3: selector flip, public contract flip, Explore/
budget ranking authority cutover, snapshot/publication expectation updates)
was NOT performed this session. `CANONICAL_OVERALL_RIP_VERSION`,
`canonical_public_rip_contract_version()`, and every other canonical
selector/constant remain **unchanged** (still V10 / `PUBLIC_RIP_CONTRACT_V10_VERSION`).

### Gate E — Set RIP V12: implemented and tested this session

`backend/db/services/product_family_rankings_service.py` — `_rank_key`,
`_canonical`, and `_project` were hardcoded to the `overall_rip_v10_*`
columns even though the module already imported `CANONICAL_OVERALL_RIP_VERSION`.
Added `_canonical_overall_rip_fields()`, a single lookup table keyed by the
live `CANONICAL_OVERALL_RIP_VERSION` value (registers both the current
canonical entry and `OVERALL_RIP_V12_VERSION`, fail-safe defaulting to the
V10 triple for anything unrecognized) that `_rank_key`/`_canonical`/`_project`
and the `overall_relative`/`overall_leader` score getters in
`build_product_family_rankings` all now read through, instead of a hardcoded
column name. With `CANONICAL_OVERALL_RIP_VERSION` still V10, this is a no-op
(21/21 tests pass, the 19 pre-existing plus 2 new ones proving the flip
works). `backend/db/services/set_rip_service.py` needed NO changes — it was
already fully generic (keys off `CANONICAL_OVERALL_RIP_VERSION` and each
product's own `overallRipVersion`/`familyRank`, never a hardcoded V10 field);
its own 18-test suite (`test_set_rip_service.py`,
`test_set_rip_correctness_patch.py`, `test_set_rip_read_models.py`) passes
unmodified. Gate E is therefore genuinely closed: flipping
`CANONICAL_OVERALL_RIP_VERSION` to V12 would make both family rankings and
Set RIP reconstruct correctly from V12 fields with no further code change to
either file.

### Gate F — Budget rankings V12: partially implemented and tested this session

Investigated `budget_product_ranking_authority.py`,
`budget_product_ranking_readiness.py`, and
`calculations/evr/budget_normalized_product_ranking.py`. Unlike Set RIP,
budget ranking's `score_budget_strategy` does not merely read a persisted
Overall RIP field — it RECOMPUTES a budget-quantity-scaled
`compute_overall_rip_v10(financial_v4_score_at_Q, collector_appeal_score)`
per candidate strategy (financial is quantity-dependent; collector appeal is
the set's own score, never recomputed per quantity). This is architecturally
the closest match to the prompt's literal
"Overall V12_budget = 0.86*FinancialV4_budget + 0.04*AccessibilityScore + 0.10*CollectorV5"
description. Implemented this session: `score_budget_strategy` gained an
optional, additive `chase_accessibility_raw` keyword (default `None`,
preserving byte-identical behavior for every existing caller — proven by
`test_score_budget_strategy_omits_v12_by_default_with_zero_behavior_change`);
when supplied, it computes `overallRipV12Score/Rankable/Version/Payload`
through the one canonical `compute_overall_rip_v12` transform (never a second
formula), using the SAME never-recomputed-per-quantity discipline already
applied to `collector_appeal_score`. Proven exact against the canonical
transform by
`test_score_budget_strategy_v12_shadow_matches_canonical_transform_and_never_moves_v10`,
and proven to leave `overallRipV10Score`/`financialRipV4Score` byte-identical
in the same call. Full suite `test_budget_normalized_product_ranking.py`:
50/50 passing (48 pre-existing + 2 new).

**What was NOT done for gate F, and why:** `_tier_sort_key` (the actual
comparator budget rankings sort by) was left untouched — still V10-only —
and no live caller (`scripts/build_budget_normalized_product_rankings.py`,
`publish_budget_product_rankings_if_ready.py`,
`budget_product_ranking_authority.py`,
`budget_product_ranking_readiness.py`) was wired to fetch a live Accessibility
value and pass it in, because doing so safely requires: (1) a new migration
adding `overall_rip_v12_*` columns to the ALREADY-DIFFERENT
`budget_product_ranking_rows`/`budget_product_ranking_snapshots` tables
(distinct physical tables from `simulation_sealed_product_results`, so V12's
existing sealed-product migration does not cover them) — which this session
is barred from applying, and creating an unapplied one plus wiring a live
Accessibility batch-read through the numerically-sensitive simulation engine
and its publish/readiness gates, then regression-testing the full pipeline,
was judged too large a scope to complete safely and verifiably in this
session's remaining margin; and (2) generalizing
`budget_product_ranking_authority.py`/`_readiness.py`'s
`EXPECTED_OVERALL_RIP_VERSION` and field lists the same way gate E's
`_canonical_overall_rip_fields()` does. This is the concrete, scoped
remainder for a future session, not an open research question — the hard
part (the correct V12 budget formula itself) is now implemented and tested.

### Step 3 (canonical promotion): NOT PERFORMED

Because gate F does not fully pass, the promotion checklist (canonical
selector flip, public contract flip, Explore/family/budget ranking authority
cutover, snapshot/publication expectation updates) was correctly NOT
executed this session. `CANONICAL_OVERALL_RIP_VERSION` remains
`OVERALL_RIP_V10_VERSION`; `canonical_public_rip_contract_version()` remains
`PUBLIC_RIP_CONTRACT_V10_VERSION`. V10 is fully preserved and untouched.

### Files changed this session

- `backend/db/services/product_family_rankings_service.py` (gate E: version-generic field selection)
- `backend/tests/unit/db/services/test_product_family_rankings_service.py` (+2 tests)
- `backend/calculations/evr/budget_normalized_product_ranking.py` (gate F: additive V12 shadow computation)
- `backend/tests/unit/calculations/test_budget_normalized_product_ranking.py` (+2 tests)
- This document (new dated section)

No migration applied, no publication triggered, no canonical selector
changed, no branch operation performed (no checkout/reset/stash left
applied — a scoped `git stash`/`pop` of exactly these 4 files was used
transiently to prove baseline test identity for gate J, and was popped back
immediately). Pre-existing concurrent work in `explore_rip_statistics_service.py`,
`pokemon_sealed_product_detail_service.py`, `RipStatisticsPageClient.jsx`,
`PokemonSetAnalysisClient.jsx`, the supporter-competitive-utility research
JSON files, and the untracked `OverallRipExplanationHierarchy*` files was
left exactly as found.

### Final label for this session

`OVERALL_RIP_V12_CANONICAL_PROMOTION_BLOCKED_BUDGET_RANKING_V12_AUTHORITY_WIRING_INCOMPLETE`

## Gate F completion (2026-09-02, budget ranking V12 authority wiring)

**Scope**: wire V12 budget-ranking authority (Phases 1-16 of the Gate F
prompt) WITHOUT touching `CANONICAL_OVERALL_RIP_VERSION` (confirmed still
`overall_rip_v10_90_financial_v4_10_collector_appeal_v5` before and after
this session, verified by direct import) and WITHOUT promoting
`public_rip_contract_v11`. Both confirmed untouched.

### Architecture correction implemented

The prior pass's `score_budget_strategy` already accepted an optional
`chase_accessibility_raw` keyword (audited and preserved unchanged - it
performs no I/O and defaults to `None`, keeping V10 output byte-identical
when omitted). This session added the missing piece: a cohort-level,
BATCH-resolved Chase Accessibility authority that sits ABOVE the simulation
engine, never inside it.

```
budget financial simulation/calculation (per product, per budget)
  -> Financial RIP V4_budget  (unchanged, no DB read added here)
+ set-level Chase Accessibility A_raw
    resolved ONCE per cohort by
    backend/db/services/budget_chase_accessibility_authority.py
    (new file - reuses chase_accessibility_service.read_chase_accessibility_snapshots_for_sets,
     the same one-query batch reader the sealed-product V12 finalizer uses,
     and chase_accessibility_service.publication_integrity_failures, the same
     failure taxonomy that already gates coordinated publication)
+ Collector Appeal V5 (unchanged, already set-level)
  -> score_budget_strategy(..., chase_accessibility_raw=A_raw or None)
     -> compute_overall_rip_v12(...)  [reused, not reimplemented]
  -> rank_budget_cohort(strategies, sort_authority=SORT_AUTHORITY_V10|V12)
```

`backend/calculations/evr/budget_normalized_product_ranking.py` -
`build_budget_strategy_values` and `score_budget_strategy` - contain NO
Supabase/DB client parameter and issue no query. Verified by direct read of
both functions' bodies and by the batching test asserting exactly one
`client.table(...)` call for a 25-set cohort
(`test_batch_read_is_exactly_one_call_for_the_whole_cohort`).

### Accessibility authority source (exact mechanism)

New `resolve_budget_cohort_accessibility(client, run_id_by_set_id)` in
`backend/db/services/budget_chase_accessibility_authority.py`:
1. Collects every `set_id` in the cohort.
2. ONE call to `read_chase_accessibility_snapshots_for_sets` (paged batch
   reader, already existed).
3. Runs `publication_integrity_failures` per set against the caller's
   `run_id_by_set_id` map (the SAME map the V10 authority already resolved
   for this cohort's Financial calculation), requiring: row exists, exact
   `calculation_run_id` match, `version == CHASE_ACCESSIBILITY_VERSION`,
   `status == "ready"`, `mapped_hc_mass >= MIN_MAPPED_HC_MASS`, non-null
   `accessibility`.
4. Any failure -> that set's `A_raw` is `None` with an explicit reason list;
   NEVER a "latest" fallback, NEVER 0.0, NEVER a neutral midpoint.

The critical exploit test (`test_stale_but_otherwise_ready_row_is_rejected_not_accepted_as_latest`)
constructs a row that is `status=ready`, correct version, `mapped_hc_mass=1.0`
but bound to `calculation_run_id="run-YESTERDAY"` while the cohort expects
`"run-TODAY"`, and asserts it is rejected (`reason=stale_calculation_run`,
`A_raw=None`) rather than accepted. Passes.

### Schema / migration

`backend/db/migrations/20260902010000_add_budget_product_ranking_v12_authority_columns.sql`
(CREATED ONLY, NOT applied to any environment):
- `budget_product_ranking_snapshots`: `overall_rip_v12_version`,
  `chase_accessibility_version`, `chase_accessibility_transform_version`,
  `ranked_under_v12_authority` (nullable boolean, default meaning
  NULL/FALSE = V10 - never implicitly TRUE).
- `budget_product_ranking_rows`: `overall_rip_v12_score`,
  `overall_rip_v12_rankable`, `overall_rip_v12_status`,
  `chase_accessibility_raw` (the exact A_raw consumed by that row, for
  reproducibility - not a duplicate of the published Accessibility record of
  truth), `budget_rank_v12`, `budget_cohort_size_v12`. All additive/nullable,
  no `DEFAULT`, no destructive DDL, wrapped in `BEGIN;`/`COMMIT;`.
  `backend/tests/unit/db/test_budget_product_ranking_v12_migration_contract.py`
  (9 tests) verifies this statically without applying it.

### Authority identity (Phase 8)

Added to `budget_product_ranking_authority.py`:
`EXPECTED_OVERALL_RIP_V12_VERSION = "overall_rip_v12_86_financial_v4_04_chase_accessibility_v1_10_collector_appeal_v5"`,
`EXPECTED_CHASE_ACCESSIBILITY_VERSION = "chase_accessibility_v1_hc_value_squared_modeled_probability"`
(verified equal to `backend.desirability.chase_accessibility.CHASE_ACCESSIBILITY_VERSION`),
`EXPECTED_CHASE_ACCESSIBILITY_TRANSFORM_VERSION = "chase_accessibility_overall_score_v1_saturating_k002"`,
`MIN_MAPPED_HC_MASS_FOR_BUDGET_V12 = 0.99`. None of the existing V10
constants were modified.

### Readiness (Phase 9)

Added `resolve_v12_budget_authority_readiness(cohort, accessibility_resolution)`
to `budget_product_ranking_readiness.py` - an explicit-opt-in addendum,
never consulted by the default `resolve_budget_ranking_readiness` V10 path
(re-ran that function's full existing test suite: 24/24 still pass
unchanged). Checks exact Accessibility version, `mapped_hc_mass >= 0.99`,
per-set eligibility, and requires ALL sets in the cohort eligible before
`ready=True` - a single ineligible set fails the whole cohort's V12
readiness (verified by test).

### Sort authority (Phase 7)

`rank_budget_cohort(strategies, sort_authority=SORT_AUTHORITY_V10|SORT_AUTHORITY_V12)`
in `budget_normalized_product_ranking.py`. Default parameter value is
`SORT_AUTHORITY_V10`, so every existing call site (unchanged call signature)
keeps its current behavior. `SORT_AUTHORITY_V12` filters to rows where
`overallRipV12Rankable is True` before sorting (never falls through to a
stale/rejected V12 score, never substitutes the V10 score under the V12
label - covered by
`test_v12_row_with_rankable_false_is_excluded_even_with_a_score_present` and
`test_v12_ranking_never_falls_back_to_v10_score_under_the_v12_label`).

### Build script (Phase 10)

Added `build_v12_shadow_rankings_for_cohort` and `rank_one_budget_v12` to
`build_budget_normalized_product_rankings.py` - additive functions, never
called from `main()`/the default dry-run/commit CLI path, which is
unchanged. The V12 path resolves `set_id -> calculation_run_id` once,
performs ONE Accessibility batch read via
`resolve_budget_cohort_accessibility`, then reuses the SAME cached
`base_values_for` per-`(run_id, pack_count)` distribution cache the V10
build already uses across every budget/product - no repeated Accessibility
query per product or per budget.

### Publish script (Phase 11) - NOT completed this session

`publish_budget_product_rankings_if_ready.py`'s default `--commit`/`--dry-run`
CLI path is untouched and remains V10-only (verified: no changes to that
file this session). An explicit, isolated V12 publish-mode validator (the
Phase 11 requirement) was NOT added in this pass - the scoring, authority,
readiness, sort and build-orchestration primitives it would call are now in
place and tested, but the publish-script wiring itself is deferred. This is
the one Gate F phase left incomplete; see Blockers below.

### Historical compatibility (Phase 12)

No existing V10 code path, table read, or persisted-row shape was modified.
`budget_product_ranking_rows`/`snapshots` gain only nullable additive
columns (migration not applied, so live rows are unaffected either way). The
full pre-existing V10 test suites for
`budget_normalized_product_ranking.py` (57 tests, +18 new in this session),
`budget_product_ranking_authority.py` (still passing), and
`budget_product_ranking_readiness.py` (still passing, 24/24 unchanged) all
pass unmodified in their pre-existing assertions.

### Dry run (Phase 13) - FROZEN ARTIFACT, not live

No live database credentials were exercised in this session for a
budget-specific cohort. Per the task's explicit fallback instruction, this
uses the existing frozen sealed-product V12 cohort artifact
(`docs/research/overall_rip_v12_dry_run_cohort_report_2026-09-02b.json`,
independently verified in a prior pass) as the closest available evidence of
V10-vs-V12 ranking behavior on the live 138-row/22-set cohort this budget
engine draws its inputs from: Spearman 0.9961, mean |rank movement| 2.64,
max movement 9, top-5 overlap 4/5, top-10 overlap 8/10, 0/398 same-set
reversals. This is NOT a budget-specific dry run (budget re-ranks whole-unit
strategies under a spending ceiling, a different comparator from the
sealed-product cohort ranking) and must not be reported as one; a genuine
budget-cohort V10-vs-V12 dry run (calling
`build_v12_shadow_rankings_for_cohort` against a live authority) is unrun
and is listed as a blocker below.

### Files changed this session (Gate F)

- `backend/db/services/budget_chase_accessibility_authority.py` (new)
- `backend/tests/unit/db/services/test_budget_chase_accessibility_authority.py` (new, 8 tests)
- `backend/db/services/budget_product_ranking_authority.py` (+V12 identity constants)
- `backend/db/services/budget_product_ranking_readiness.py` (+`resolve_v12_budget_authority_readiness`)
- `backend/tests/unit/db/services/test_budget_product_ranking_v12_readiness.py` (new, 6 tests)
- `backend/calculations/evr/budget_normalized_product_ranking.py` (+`SORT_AUTHORITY_V10`/`_V12`, `_tier_sort_key_v12`, `rank_budget_cohort(sort_authority=...)`)
- `backend/tests/unit/calculations/test_budget_normalized_product_ranking.py` (+18 tests, sort-authority generalization)
- `backend/scripts/build_budget_normalized_product_rankings.py` (+`rank_one_budget_v12`, `build_v12_shadow_rankings_for_cohort`)
- `backend/db/migrations/20260902010000_add_budget_product_ranking_v12_authority_columns.sql` (new, NOT applied)
- `backend/tests/unit/db/test_budget_product_ranking_v12_migration_contract.py` (new, 9 tests)
- This document (this section)

No migration applied, no publication triggered, no canonical selector
changed, no branch operation performed. `CANONICAL_OVERALL_RIP_VERSION`
confirmed still `overall_rip_v10_90_financial_v4_10_collector_appeal_v5`
after this session's changes.

### Final label for Gate F

`OVERALL_RIP_V12_BUDGET_RANKING_AUTHORITY_BLOCKED_PUBLISH_SCRIPT_V12_MODE_AND_LIVE_BUDGET_DRY_RUN_NOT_COMPLETED`

Phases 1-10, 12, 14 (A-F, H), 15, 16 are complete and tested (155 tests
passing across the listed files, 0 failures, 0 regressions). Phase 11
(publish-script explicit V12 mode) and the budget-specific portion of Phase
13 (a genuine live or artifact-based budget-cohort V10-vs-V12 dry run,
distinct from the sealed-product cohort artifact reused above) are the
concrete remainder before this gate can claim full completion.

## Blockers before Prompt 6 (and before re-attempting this promotion)

1. Apply Chase Accessibility migration 077 and the V12 sealed-product
   migration to the live database (not performed here, per hard constraints).
2. Run the daily finalization pipeline so `overall_rip_v12_*` columns and
   Chase Accessibility snapshots actually populate.
3. Re-run Phases 3-5 against the now-real cohort to get genuine readiness
   counts and a real V10-vs-V12 ranking comparison.
4. Complete Phases 6-10 (family/Set RIP/budget/Explore cutover support) with
   real ranking-movement evidence backing them, not just fixture tests.
5. Fix (separately, likely by whoever owns the concurrent
   `explore_rip_statistics_service.py` change) the 6 pre-existing test
   failures caused by the new Accessibility table read having no fixture
   handler — unrelated to this session's scope but a real defect to close
   before that file's own change ships.
6. Only then re-evaluate Phase 11.
