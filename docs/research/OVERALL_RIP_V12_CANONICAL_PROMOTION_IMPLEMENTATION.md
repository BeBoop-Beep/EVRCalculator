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

---

## 2026-09-03 — CANONICAL PROMOTION EXECUTED

### Decision

`OVERALL_RIP_V12_CANONICAL_PROMOTION_IMPLEMENTED_CODE_ONLY`

All blockers above are closed. `CANONICAL_OVERALL_RIP_VERSION` is now
`overall_rip_v12_86_financial_v4_04_chase_accessibility_v1_10_collector_appeal_v5`
and `canonical_public_rip_contract_version()` is now `public_rip_contract_v11`.
No migration, publication, snapshot refresh, or deployment was performed by
this session. V10 remains fully computable and explicitly requestable.

### Preconditions independently re-verified this session (live, read-only)

Unlike the two prior sessions recorded above, this session HAD live Supabase
credentials available (`backend/.env`) and used them for direct read-only
verification rather than relying solely on the prior session's report:

- `simulation_sealed_product_results`: **138/138** rows with
  `overall_rip_v12_score` populated all carry `overall_rip_v12_status ==
  "ready"` and the single exact version string
  `overall_rip_v12_86_financial_v4_04_chase_accessibility_v1_10_collector_appeal_v5`
  (own query, zero version drift, zero non-ready rows).
- `pokemon_set_chase_accessibility_snapshot_latest`: **22/22** rows, all
  `status == "ready"`, all `mapped_hc_mass == 1.0` (own query).
- `budget_product_ranking_rows` / `budget_product_ranking_snapshots`: the
  Gate F V12 authority columns (`overall_rip_v12_score`,
  `overall_rip_v12_rankable`, `chase_accessibility_raw`,
  `overall_rip_v12_version`, `ranked_under_v12_authority`, ...) exist and are
  queryable — confirming the third migration is genuinely applied. All
  sampled values are `NULL`, which is the CORRECT and EXPECTED state: no V12
  budget publication has ever been executed (none was executed this session
  either), so no row has ever populated them.
- `backend/scripts/audit_ev_representativeness_coverage.py` run live against
  the most recently fully-promoted market date (`2026-09-02`; `2026-09-03`
  itself had not yet completed its same-day simulation freshness pass at the
  time of this session, an unrelated same-day lag, not a defect):
  `supported_current_sets=22`, `healthy=22`, `legitimate_no_headline=0`,
  `missing=0`, `wrong_run=0`, `version_mismatch=0` — identical to the
  previously recorded known-good baseline. No regression.

This independent re-verification did not surface any discrepancy from the
prior session's shadow-readiness numbers (138/138, 22/22, mass=1.0,
Spearman≈0.9961 sealed-product / 0.9866–0.9968 budget dry run per-budget,
Top-5 overlap 5/5, Top-10 overlap 9–10/10, zero same-set reversals, zero
structural invariant violations) — those are treated as re-confirmed, not
re-derived from scratch, since this session's own live queries independently
corroborate the underlying row-level facts they were computed from.

### Phase 1 — Consumer map (abridged; full detail in the code changes below)

| Symbol | Runtime consumers found | Classification |
|---|---|---|
| `CANONICAL_OVERALL_RIP_VERSION` | `product_family_rankings_service.py` (already version-generic lookup table), `set_rip_service.py` (already generic), `explore_rip_statistics_service.py`, `sealed_product_rip_finalization_service.py`, `rankings_publication_lifecycle.py`, `public_rip_publication_contract.py`, `sealed_product_results_repository.py`, `weighted_rip.py` (defines V9-V12 compute fns, does not read the switch itself) | CHANGE_TO_CANONICAL_V12 (all resolve generically off the one constant; flipping it in `scoring_config.py` was sufficient — no per-file hardcoding found) |
| `canonical_overall_rip_is_v10()` | Tests only (5 files); zero runtime call sites | TEST_ONLY — retained as a truthfully-`False` predicate, same pattern as the pre-existing `canonical_overall_rip_is_v7`/`_v8`. Added `canonical_overall_rip_is_v12()` as its truthful counterpart (repo convention: one named predicate per version, not a single generic comparison helper — kept consistent rather than introducing a second style). |
| `canonical_public_rip_contract_version()` | `pokemon_sealed_product_detail_service.py`, `explore_rip_statistics_service.py`, `public_rip_publication_contract.py`, `research/chase_pillar_stage6/control.py`, tests | CHANGE_TO_CANONICAL_V11 (promoted from `public_rip_contract_v10` to `public_rip_contract_v11`) |
| `OVERALL_RIP_V10_VERSION` (literal) | `budget_product_ranking_authority.py`'s `EXPECTED_OVERALL_RIP_VERSION` (the BASE-cohort price/version coherence gate `load_pinned_cohort` checks — a precondition for even building a V12 candidate on top, per Gate F's architecture), plus many test fixtures and historical-lineage docstrings | KEEP_EXPLICIT_V10_HISTORY — intentionally NOT repointed; this is the anchor identity for the price-coherent base cohort the V12 shadow candidate is built ON TOP OF, not a canonical-Overall-RIP selector. Repointing it would conflate two different concerns. |
| `EXPECTED_OVERALL_RIP_V12_VERSION`, `validate_v12_publication_payload`, `run_v12_dry_run` (`publish_budget_product_rankings_if_ready.py`) | Explicit V12 validator, built by a concurrent/prior session | CHANGE_TO_CANONICAL_V12 in the sense of "now also invoked by the default path" — reused via `default_budget_sort_authority_is_v12()`, never duplicated |
| `public_rip_contract_v10.py`, `weighted_rip.compute_overall_rip_v10`, `OVERALL_RIP_V10_WEIGHTS`, V10 DB columns (`overall_rip_v10_*`) | Every explicit-V10 caller/fixture/column | KEEP_EXPLICIT_V10_HISTORY — untouched, still fully computable, still the rollback lineage |
| `OVERALL_RIP_V11_VERSION` (Chase Opportunity/Core K lineage) | `weighted_rip.compute_overall_rip_v11`, V11 research files | LEGACY_ONLY / RESEARCH_ONLY — a separate historical lineage, never touched, never becomes canonical by this promotion |
| Round15-24 Treatment Market Prestige tests, `test_pull_model_live_fallback.py`, `test_public_rip_cohort_integration.py`, `test_pokemon_public_snapshot_service.py`, `test_pokemon_scrape_runtime_preflight.py`, `test_public_rip_rpc_v8_migration_sql.py`, billing/`jwt`-import-broken files | No dependency on `CANONICAL_OVERALL_RIP_VERSION`/`canonical_public_rip_contract_version` at all (git-branch/ancestry gates, live-DB-only integration tests, a stale hardcoded RPC-migration list last updated before V9, a missing `public_read_client` symbol, a missing `jwt` package, Python-3.8-incompatible `X \| None` syntax) | PRE-EXISTING / ENVIRONMENT — confirmed unrelated by isolated re-run (each passes or fails identically whether or not this session's changes are present; several fail on symbols/behavior this session never touched) |

### Phase 2 — Canonical Overall RIP selector (exact before/after)

`backend/desirability/scoring_config.py`:
```
- CANONICAL_OVERALL_RIP_VERSION = OVERALL_RIP_V10_VERSION
- CANONICAL_OVERALL_RIP_WEIGHTS: Dict[str, float] = dict(OVERALL_RIP_V10_WEIGHTS)
+ CANONICAL_OVERALL_RIP_VERSION = OVERALL_RIP_V12_VERSION
+ CANONICAL_OVERALL_RIP_WEIGHTS: Dict[str, float] = dict(OVERALL_RIP_V12_WEIGHTS)
```
`OVERALL_RIP_V11_VERSION`/`OVERALL_RIP_V12_VERSION` added to
`KNOWN_OVERALL_RIP_VERSIONS`. `_audit_overall_rip_weights()` gained a V12
weight-sum entry and a V12 canonical-consistency check (mirroring the
existing V7/V10 pattern). `canonical_overall_rip_is_v10()` retained,
now truthfully `False`; `canonical_overall_rip_is_v12()` added, now `True`.
No parallel/duplicate generic helper was introduced — the repo's existing
per-version-predicate convention was extended, not replaced.

### Phase 3 — Canonical public contract (exact before/after)

```
- def canonical_public_rip_contract_version() -> str:
-     from backend.desirability.public_rip_contract_v10 import PUBLIC_RIP_CONTRACT_V10_VERSION
-     return PUBLIC_RIP_CONTRACT_V10_VERSION
+ def canonical_public_rip_contract_version() -> str:
+     from backend.desirability.public_rip_contract_v11 import PUBLIC_RIP_CONTRACT_V11_VERSION
+     return PUBLIC_RIP_CONTRACT_V11_VERSION
```
`public_rip_contract_v10.py` is untouched and remains fully computable/
explicitly requestable. `public_rip_contract_v11.py` needed NO code change —
it already carried Overall RIP V12 additively on top of a byte-identical V10
block; only which contract is *canonical* moved.

### Phase 4 — Generic read-model behavior

- **V12 resolves**: confirmed by live-process check
  (`product_family_rankings_service._canonical_overall_rip_fields()` returns
  `('overall_rip_v12_score', 'overall_rip_v12_version',
  'overall_rip_v12_rankable')` after the flip) and by the independent live-DB
  spot check above.
- **V10 still explicit**: `OVERALL_RIP_V10_VERSION`,
  `compute_overall_rip_v10`, `public_rip_contract_v10.py`, and every
  `overall_rip_v10_*` DB column are untouched and remain fully computable —
  proven by the full V10-specific test suites still passing unmodified
  (`test_sealed_product_rip_finalization_service_v10.py`, the V10 weights
  audit in `scoring_config.py`, etc.).
- **Fail-closed confirmed, never V10-under-a-V12-label**: `compute_overall_rip_v12`
  (`weighted_rip.py`) has no code path that substitutes a V10 score when
  Accessibility is missing — it reports `status: "unavailable"`/`rankable:
  False` (pre-existing behavior, re-verified by the pre-existing
  `test_overall_rip_v12_chase_accessibility.py` test suite, unmodified except
  for the one canonical-selector assertion this session flipped). Same
  discipline in `budget_normalized_product_ranking.py`'s
  `SORT_AUTHORITY_V12`, covered by the pre-existing
  `test_v12_ranking_never_falls_back_to_v10_score_under_the_v12_label` test,
  unmodified and still passing.

### Phase 5/6 — Family rankings / Set RIP / Explore rankings

No production logic changes were needed in `product_family_rankings_service.py`
or `set_rip_service.py` — both were already built (a prior session's Gate E
work) to read `CANONICAL_OVERALL_RIP_VERSION` through a generic lookup table
rather than a hardcoded V10 column name, and self-heal correctly once the
switch flips. This was verified, not assumed: a direct Python check after the
flip shows `_canonical_overall_rip_fields()` now returns the
`overall_rip_v12_*` triple, and `test_product_family_rankings_service.py`'s
own test fixtures needed updating (see Files Changed) because they had been
hand-populating only `overall_rip_v10_*` columns and using
`CANONICAL_OVERALL_RIP_VERSION` (evaluated at import time, now V12) as the
V10 field's version stamp — a latent fixture bug the flip exposed, now fixed
by populating BOTH the V10 fields (with V10's own literal string) and the
V12 fields (with the canonical constant) so the fixture means what it says
regardless of which model is canonical. `explore_rip_statistics_service.py`
and `rankings_publication_lifecycle.py` and `public_rip_publication_contract.py`
likewise read the constant generically; the latter's own test file had 3
independently-stale assertions (pinned to Financial V3 / Collector Appeal V4
/ Overall V8 / contract v8 — versions that predate even this program's
V9/V10 promotions) that were fixed to assert the TRUE current identity
(Financial V4 / Collector V5 / Overall V12 / contract v11).

### Phase 7/11 — Budget rankings default authority

Gate F's infrastructure (`budget_chase_accessibility_authority.py`,
`resolve_v12_budget_authority_readiness`, `SORT_AUTHORITY_V12`,
`build_v12_shadow_rankings_for_cohort`, and — per this session's git status,
already landed by a concurrent/prior session before this session began —
`validate_v12_publication_payload`/`run_v12_dry_run` in
`publish_budget_product_rankings_if_ready.py`) was REUSED, not rebuilt.

`budget_product_ranking_authority.py`'s `EXPECTED_OVERALL_RIP_VERSION` (the
BASE-cohort price/version coherence identity `load_pinned_cohort` checks)
was deliberately left pointed at V10 — it is not a canonical-Overall
selector, it is the precondition identity for the price-coherent cohort the
V12 candidate is built ON TOP OF (Gate F's own documented architecture: V12
budget scoring recomputes nothing about the base simulation, it only adds
Accessibility to an already-V10-validated cohort). Repointing it would
conflate two different concerns and was correctly avoided.

What this session added: `publish_budget_product_rankings_if_ready.py` gained
`default_budget_sort_authority_is_v12()`, a one-line reader of the
backend-wide `CANONICAL_OVERALL_RIP_VERSION` (now `True`). The DEFAULT
`run()` path (both `--dry-run` and `--commit`) now additionally computes and
reports `v12_canonical_validation` via `run_v12_dry_run` — REUSING the
existing explicit validator rather than a second implementation — whenever
V12 is canonical. This is deliberately ADDITIVE/REPORT-ONLY: it never changes
`failures`/`status`/`failed_gate`, and never touches the V10-shaped
`snapshot`/`rows` that `publish_rankings` would persist on `--commit`
(unexercised in this task — no publish call was made). Proven by a new hard
test, `test_default_run_attaches_v12_canonical_validation_when_v12_is_canonical`
(30/30 passing in that file, up from 29/29).

**What remains genuinely open for budget rankings** (honestly scoped, not
hand-waved): `publish_rankings`/`to_publication_payload` still write only the
V10-shaped row/snapshot schema. Making `--commit` actually PERSIST a V12
budget ranking (populating the now-live `overall_rip_v12_score`/
`ranked_under_v12_authority`/etc. columns confirmed to exist this session)
would require wiring `build_v12_shadow_rankings_for_cohort`'s output through
a new persistence path and is, correctly, a PUBLICATION change — explicitly
out of scope for this code-only task ("No actual publish call in this
task"). The default path's *authority resolution and validation* is
genuinely V12-canonical now; the default path's *write* remains V10-shaped
until a future, explicitly-scoped publish-path change executes it.

### Phase 8/9 — Product detail / Set RIP UI

No code changes were needed. `overallRipExplanationHierarchySelector.mjs`
renders whichever contract SHAPE it is handed (`publicRipContractV11`/
`overallRipV12` vs a V10-only shape) — it never reads
`CANONICAL_OVERALL_RIP_VERSION` itself — so it needed no change at cutover
time; a generic/current payload already carries the V12 shadow block
unconditionally (from a prior session's `_public_rip_contract_v11_shadow`
work), and this selector already renders 86/4/10 for it. This session
corrected the module's own docstring, which had stated "V10 stays canonical"
as a design invariant — now stale — to instead document the actual cutover
and note the selector needed no code change because of its data-shape-driven
design. `ProductRipSection.jsx`, `SealedProductDetail.contract.test.mjs`
(23/23 passing), and `OverallRipExplanationHierarchy.contract.test.mjs` were
re-run unmodified and still pass, confirming no regression to V10 fixture
rendering. Grep confirms zero frontend RIP-score arithmetic anywhere in
`frontend/components/explore/*.mjs` or the product-detail component tree.

### Phase 10 — Publication/snapshot expectations (code-only)

`public_rip_publication_contract.py`'s `canonical_publication_identity()` and
`rankings_publication_lifecycle.py` both already read
`CANONICAL_OVERALL_RIP_VERSION`/`canonical_public_rip_contract_version()`
generically (no hardcoded literal), so the NEXT authorized publication's
staleness/readiness checks now correctly expect Overall RIP V12 + public
contract V11 with no further code change — proven by
`test_public_rip_publication_contract.py`'s `canonical_publication_identity()`
test now asserting the true current identity (Financial V4 / Collector V5 /
Overall V12 / contract v11) instead of its previously-stale V8/V4/V3
expectation. No publication was executed; no snapshot was refreshed; no
canonical field was backfilled.

### Phase 12 — Entitlements/security re-audit

Grepped `backend/api`, `backend/auth`, and every entitlement-adjacent service
file for `overall_rip_v12`/`chase_accessibility`/`overallRipV12`: zero hits
outside the desirability/db-services scoring layer itself. Chase
Accessibility and Overall RIP V12 do not appear in any tier-gating file.
`ProductRipSection.jsx` remains behind the pre-existing Plus-tier `entitled`
check (untouched). No Premium Chase Efficiency data was added to any
Public/Plus surface. Boundaries unchanged: Public = Set RIP; Plus = Product
RIP/rankings (now explaining V12 truthfully); Premium = Card Chase
Efficiency and future Product Chase-specific tooling — none of which reads
Chase Accessibility or is affected by this cutover.

### Phase 13 — EV Representativeness regression

Run live (not simulated) against `2026-09-02` (the most recent date with a
complete same-day freshness pass — `2026-09-03` itself had not finished its
own same-day simulation refresh at the time of this session, an unrelated
timing artifact, confirmed by checking `pokemon_scrape_batches`, whose
`2026-09-03` row shows `status=complete`/promoted, meaning the lag is in the
separate opening-simulation-freshness pipeline, not price promotion):
`supported_current_sets=22`, `healthy=22`, `legitimate_no_headline=0`,
`missing=0`, `wrong_run=0`, `version_mismatch=0`. Identical to the
previously recorded known-good baseline. The EV pipeline was not touched by
this session.

### Phase 14 — Test matrix (exact counts)

| Suite | Result |
|---|---|
| `test_scoring_config_canonical_selection.py` | 6/6 passed (2 renamed/rewritten for the flip, 4 unchanged) |
| `backend/tests/unit/desirability/` (full) | 1927 passed, 74 failed — the 74 are ALL pre-existing/environment (git-branch/ancestry gates in round15-24, live-DB-only `test_public_rip_cohort_integration.py`, `test_pull_model_live_fallback.py` fixture/live-ID drift) — zero of them reference `CANONICAL_OVERALL_RIP_VERSION`/`canonical_public_rip_contract_version` (grep-confirmed). Before this session's test fixes: 81 failed (8 of those were real, now-fixed cutover-invariant assertions; see below) |
| `test_product_family_rankings_service.py` | 22/22 passed (2 fixture bugs the flip exposed, now fixed) |
| `test_set_rip_service.py` + `test_set_rip_correctness_patch.py` + `test_pokemon_set_rip_projection_readers.py` + `test_sealed_product_rip_finalization_service_v10.py` + `test_sealed_product_rip_finalization_service_v12.py` | 57/57 passed, unmodified |
| `test_pokemon_sealed_product_detail_service.py` | 19/19 passed, unmodified |
| `test_explore_rip_statistics_service.py` | 15/15 passed (6 pre-existing failures fixed — missing fixture handler for `pokemon_set_chase_accessibility_snapshot_latest`, a concurrent-session gap unrelated to this cutover but blocking honest regression-checking of it) |
| `test_public_rip_publication_contract.py` + `test_rankings_publication_lifecycle.py` | 44/44 passed (3 independently-stale assertions fixed — pinned to Financial V3/Collector V4/Overall V8, versions that predate this program) |
| `test_publish_budget_product_rankings_if_ready.py` | 30/30 passed (29 pre-existing + 1 new hard test) |
| `test_budget_normalized_product_ranking.py` + `test_budget_product_ranking_v12_readiness.py` + `test_budget_chase_accessibility_authority.py` + `test_budget_product_ranking_v12_migration_contract.py` | 80/80 passed, unmodified |
| `SealedProductDetail.contract.test.mjs` + `OverallRipExplanationHierarchy.contract.test.mjs` | 23/23 passed, unmodified |
| `backend/tests/unit/db/` (full, excluding pre-existing environment-broken collection errors: billing/`X \| None` syntax on Python 3.8, missing `jwt` package) | 1717 passed / 168 failed on first full-suite run; investigated: `test_pokemon_set_rip_projection_readers.py` and `test_public_rip_publication_contract.py` failures in that run did NOT reproduce when the same files were re-run in isolation (order-dependent pollution from the `jwt`/billing collection errors and `test_pokemon_public_snapshot_service.py`'s own pre-existing `public_read_client` AttributeError, not a regression from this session — confirmed by isolated re-run passing 100%). `test_public_rip_rpc_v8_migration_sql.py`'s 3 failures are independently pre-existing: its own hardcoded migration list was never updated past `067_update_public_rip_rpc_to_v9.sql`/`072_update_public_rip_rpc_to_v10.sql`, both of which already existed before this session. |

**Hard tests A-J** (per the task's explicit list):
- **(A) generic current Overall → V12**: `test_canonical_overall_rip_is_v12` (new), live-DB spot check. PASS.
- **(B) explicit V10 request → V10**: `test_overall_rip_v10_remains_explicit_historical_lineage`, `test_sealed_product_rip_finalization_service_v10.py` (unmodified, still passing). PASS.
- **(C) generic current public contract → V11**: `test_canonical_public_rip_contract_is_v11` (new). PASS.
- **(D) explicit V10 public contract → V10**: `test_explicit_v10_public_contract_still_computable_unchanged` (new). PASS.
- **(E) generic Overall rankings → V12 order**: `_canonical_overall_rip_fields()` live-process check + `test_product_family_rankings_service.py` (updated fixtures, all passing) + live-DB 138/138 V12-ready rows. PASS.
- **(F) V12 missing Accessibility → unavailable, never falls back to V10**: pre-existing `compute_overall_rip_v12` fail-closed behavior + `SORT_AUTHORITY_V12`'s never-falls-back test, both unmodified and passing. PASS.
- **(G) historical V10 rows/snapshots still readable**: full V10 test suites pass unmodified; live DB still serves `overall_rip_v10_score` on all 965+ historically-populated rows (column untouched). PASS.
- **(H) budget default now uses canonical V12**: `default_budget_sort_authority_is_v12()` (new) + `test_default_run_attaches_v12_canonical_validation_when_v12_is_canonical` (new). PASS for authority/validation; the physical `--commit` write path remains V10-shaped (see Phase 7/11 remainder above) — reported honestly, not claimed as fully closed.
- **(I) no frontend scoring**: grep confirms zero RIP-formula arithmetic in `frontend/components/explore/*.mjs`/product-detail tree; `overallRipExplanationHierarchySelector.mjs` sources every V12 weight from the backend payload's own `overallRipV12Composition`. PASS.
- **(J) no ECE/O_budget/Depth/Core-K contamination**: `compute_overall_rip_v12`'s signature grep-confirmed clean (pre-existing test unmodified, still passing); "Core K" hits are exclusively V11's own separate lineage + research files, none in the V12 path. PASS.

### Phase 15 — Regression audit results

- `canonical_overall_rip_is_v10` — 0 runtime hits (5 test files only, all now correctly asserting `False`). VALID.
- `90% Financial` — hits only in (a) `scoring_config.py`'s own historical V5/V7/V8 docstrings describing THOSE models truthfully, (b) `public_rip_contract_v5/v7/v8.py`'s own legacy docstrings, (c) `OverallRipExplanationHierarchy.jsx`'s version-aware comment correctly describing what V10-SHAPED data renders. VALID in every case — none is a generic/current-path claim.
- `overall_rip_v10` / `public_rip_contract_v10` — every runtime hit is either the BASE-cohort budget authority (Phase 7/11, intentionally V10) or an explicit-V10 code path/column. VALID.
- `83/11/6` / `84/6/10` / `Core K` / `chase_opportunity` — exclusively Overall RIP V11's own separate Chase-Opportunity lineage and its research files. VALID, untouched.
- `economic_chase_efficiency` / `product_chase_efficiency` / `O_budget` / `chase_depth` — `chase_depth` appears only as a diagnostic-only field (never a scored input, per its own docstring and the V12 signature grep above); the ECE/O_budget/product_chase_efficiency strings do not appear inside `compute_overall_rip_v12` or its callers. VALID.
- `chance of a chase` — appears only as the forbidden-phrase constant/its own tests. Never actual copy. VALID.

No INVALID hits were found — nothing on the generic/current runtime path was
found hardwired to V10 when it should now resolve V12.

### Files changed this session

- `backend/desirability/scoring_config.py` — Phase 2/3 selector flips, V12 audit checks, `canonical_overall_rip_is_v12()`
- `backend/tests/unit/desirability/test_scoring_config_canonical_selection.py` — rewritten for the new canonical identity
- `backend/tests/unit/desirability/test_chase_accessibility.py` — 1 assertion updated
- `backend/tests/unit/desirability/test_collector_appeal_v2_and_overall_rip_v6.py` — 1 assertion updated
- `backend/tests/unit/desirability/test_collector_appeal_v3_and_overall_rip_v7.py` — 1 assertion updated
- `backend/tests/unit/desirability/test_financial_rip_v3_public_contract.py` — 1 assertion updated
- `backend/tests/unit/desirability/test_overall_rip_v10_and_financial_v4_integration.py` — 2 assertions updated
- `backend/tests/unit/desirability/test_overall_rip_v12_chase_accessibility.py` — 1 assertion updated/renamed
- `backend/tests/unit/desirability/test_public_rip_contract_v11.py` — 1 assertion updated/renamed
- `backend/tests/unit/db/services/test_product_family_rankings_service.py` — fixture `row()` helper fixed to populate both V10 and V12 fields correctly; 1 test's override fields updated
- `backend/tests/unit/db/services/test_explore_rip_statistics_service.py` — added a missing fake-client fixture handler for `pokemon_set_chase_accessibility_snapshot_latest` (fixes 6 pre-existing failures, concurrent-session gap)
- `backend/tests/unit/db/services/test_public_rip_publication_contract.py` — 3 independently-stale assertions corrected to the true current canonical identity
- `backend/scripts/publish_budget_product_rankings_if_ready.py` — added `default_budget_sort_authority_is_v12()` and additive `v12_canonical_validation` reporting in the default `run()` path
- `backend/tests/unit/scripts/test_publish_budget_product_rankings_if_ready.py` — 1 new hard test
- `frontend/components/explore/overallRipExplanationHierarchySelector.mjs` — docstring corrected for the cutover (no behavior change)
- This document (this section)

### V10 rollback strategy

To roll back to V10: revert `CANONICAL_OVERALL_RIP_VERSION` to
`OVERALL_RIP_V10_VERSION` and `CANONICAL_OVERALL_RIP_WEIGHTS` to
`dict(OVERALL_RIP_V10_WEIGHTS)` in `scoring_config.py`, and
`canonical_public_rip_contract_version()` back to returning
`PUBLIC_RIP_CONTRACT_V10_VERSION`. No data migration is required either
direction: every V10 column/table/contract was left untouched throughout
this cutover, and `product_family_rankings_service.py`/`set_rip_service.py`/
`public_rip_publication_contract.py`/`rankings_publication_lifecycle.py` all
resolve generically off the same two constants, so they revert automatically
with no further code change. The budget publisher's additive
`v12_canonical_validation` reporting would simply stop firing
(`default_budget_sort_authority_is_v12()` would return `False` again) with
no other effect. A rollback is therefore a 2-3 line code revert plus a
redeploy — never a data operation.

### Deployment/publication status

**None.** No backend or frontend deployment, no production publication, no
snapshot refresh, and no canonical-field backfill was performed or triggered
by this session. All live-database access this session was read-only SELECT
queries for independent verification.

### Concurrent work preserved

`git status` at the end of this session shows only the files listed above as
modified by this session, plus the pre-existing (session-start) untracked/
modified files this session did not touch:
`docs/research/supporter_competitive_utility_v1/deck_card_observations.json`,
`docs/research/supporter_competitive_utility_v1/tournaments.json`, and the
`backend/artifacts/market_explorer_acceptance/*.json` /
`backend/scripts/build_market_explorer_maintained_cache.py` untracked files
present at session start (Prompt 5 concurrent work) — none were read for
content changes, none were edited, none were staged or committed.

## 2026-09-03 (later session) — V12 budget physical persistence closure attempt

### Decision

`OVERALL_RIP_V12_BUDGET_PUBLICATION_PERSISTENCE_BLOCKED_PHYSICAL_WRITE_IS_AN_ATOMIC_SQL_RPC_THAT_REQUIRES_A_MIGRATION`

### What this session traced (Phase 1)

Full write path, end to end:

`publish_budget_product_rankings_if_ready.py::run(commit=True)` →
`resolve_budget_ranking_readiness` (V10 gate) → `build_rankings_for_cohort`
(V10 scoring only) → `to_publication_payload` (V10-shaped snapshot/rows
dicts, `build_budget_normalized_product_rankings.py`) →
`validate_publication_payload` (pure Python V10 gate) →
**`publish_rankings(client, results)`** (same file) → **the actual physical
write**: one call to the Postgres RPC
`public.publish_budget_product_ranking_snapshot(p_snapshot JSONB, p_rows
JSONB)` (defined in
`backend/db/migrations/20260824025349_strengthen_budget_product_ranking_publication.sql`)
→ back in Python, `verify_persisted_snapshot` (post-hoc read-back check) →
final status.

The RPC is the actual repository-write function — it is one `plpgsql`
function, `SECURITY DEFINER`, that runs as a single Postgres transaction:
`INSERT ... ON CONFLICT ... DO UPDATE` into `budget_product_ranking_snapshots`
(explicit column list, 18 named columns), then `DELETE` + `INSERT ... SELECT
... FROM jsonb_array_elements(p_rows)` into `budget_product_ranking_rows`
(explicit column list, 27 named columns), then several `RAISE EXCEPTION`
integrity re-checks against the just-inserted rows, then an `INSERT ...
ON CONFLICT DO UPDATE` into `budget_product_ranking_latest` that moves the
"current" pointer. Any exception anywhere in the function rolls back the
entire transaction, so today's V10 write is already atomic and
partial-write-safe by construction (Phase 6's requirement is already met —
for V10).

**The blocking fact**: both explicit column lists in that SQL function body
(the `INSERT INTO budget_product_ranking_snapshots (...)` and `INSERT INTO
budget_product_ranking_rows (...)` statements) name only the pre-existing
V10 columns. Neither list includes `overall_rip_v12_version`,
`chase_accessibility_version`, `chase_accessibility_transform_version`,
`ranked_under_v12_authority`, `overall_rip_v12_score`,
`overall_rip_v12_rankable`, `overall_rip_v12_status`,
`chase_accessibility_raw`, `budget_rank_v12`, or `budget_cohort_size_v12` —
even though those columns exist and are live-queryable in production (per
the prior session's direct read verification, "confirming the third
migration is genuinely applied," `2026-09-03 — CANONICAL PROMOTION EXECUTED`
section above). Because the `INSERT` statements name columns explicitly
(never `INSERT ... SELECT *`), any extra keys a Python caller adds to
`p_snapshot`/`p_rows` are silently ignored by Postgres — `jsonb_array_elements`
happily accepts a JSON object with more keys than the query reads, and
nothing errors. Confirmed by reading the full RPC body (Phase 1 done before
any edit, as instructed).

### Why this is a genuine gate failure, not a workaround-able gap

To make `--commit` actually persist V12 authority/row data **atomically**
(Phase 6's explicit requirement: "A partial V12 row write must never become
a published snapshot," which for this RPC's design means "the same
transaction that marks the snapshot published/moves the `latest` pointer
must be the transaction that writes the V12 columns") requires changing the
RPC's two `INSERT` column lists and `VALUES`/`SELECT` projections to also
carry the ten V12 fields. That is a `CREATE OR REPLACE FUNCTION` change to a
live Postgres object — exactly the shape of change this repository's own
convention (`20260824025349_strengthen_budget_product_ranking_publication.sql`,
which itself replaced an earlier version of the same function) always makes
as a migration file that must be applied to production. There is no
Python-only way to add columns to a `plpgsql` function's hardcoded `INSERT`
statement.

Two alternatives were considered and rejected as unsafe rather than
attempted:

1. **Bypass the RPC and `UPDATE` the V12 columns directly from Python after
   the RPC call returns**, using the returned `snapshot_id` and the
   already-computed `build_v12_shadow_rankings_for_cohort` output. This
   needs no migration (the columns already exist) and is pure application
   code. It was rejected because it is a **second, non-atomic network
   round-trip**: the RPC's transaction has already committed
   `publication_status='published'` and moved the `budget_product_ranking_latest`
   pointer *before* the Python-side `UPDATE` even starts. If that `UPDATE`
   fails, is partially applied (e.g. across a paginated batch), or the
   process crashes between the two calls, the snapshot is *already*
   published with some or all V12 columns missing — precisely the outcome
   Phase 6 says must never happen. Reporting a downgraded status after the
   fact (mirroring the existing `verify_persisted_snapshot` →
   `POST_PUBLISH_VERIFICATION_FAILED` pattern) does not undo the fact that a
   partially-V12 snapshot was, for some interval, the live `latest`
   snapshot every reader resolves — the existing V10 pattern tolerates this
   only because V10 has no analogous "the row must have gained authority X"
   concept post-commit; V12 explicitly does (Phase 2's requirement that a
   canonical V12 snapshot always sets `ranked_under_v12_authority=TRUE` with
   every version field populated). Implementing this would produce code that
   satisfies Phases 2/3/5/8-9 in isolated unit tests (a fake harness can
   fake perfect two-call sequencing) while remaining genuinely unsafe against
   the exact failure mode (`F`: "Insert failure midway through → snapshot
   never becomes published") the task's own Phase 9F requires proving false.
2. **Have Python perform the entire publication as direct multi-table
   writes** (`INSERT`/`UPSERT` on `budget_product_ranking_snapshots`,
   `budget_product_ranking_rows`, `budget_product_ranking_latest` from the
   Supabase client, replacing the RPC call), wrapping it in one PostgREST
   transaction. Rejected: PostgREST/`supabase-py` does not expose
   cross-statement transactions to the client in this codebase's stack (the
   existing design deliberately pushes all invariants — cohort/rank
   contiguity, price-authority uniqueness, Full Market coverage, the
   `latest` pointer move — into one `plpgsql` function specifically so they
   run inside one Postgres transaction with `SECURITY DEFINER`, not so a
   client can partially replicate them per statement). Reimplementing that
   RPC's ~15 `RAISE EXCEPTION` invariant checks a second time in Python,
   racing the real RPC's own definition, would create exactly the
   "recompute the formula/gate outside its authority" anti-pattern this
   program's own prior phases (Gate F, `validate_v12_publication_payload`'s
   own docstring) were written to avoid, and would still not be atomic
   without native transaction support.

Both alternatives were rejected on correctness grounds before writing any
code, not attempted and then reverted — consistent with the task's Phase 1
instruction to fully map the write path "before you edit."

### Conclusion

The task's own framing ("this task is pure application-code work," "the
schema... is already applied in production") is correct about the schema but
does not hold for the write path once traced: the specific function that
performs the physical write is a versioned SQL object whose column lists are
the actual gate, and extending them is a schema-level change (a new
`CREATE OR REPLACE FUNCTION` migration) under this repository's own
established convention for this exact function. The task explicitly
prohibits creating or applying any migration. No safe, atomic, code-only way
to make `--commit` physically persist V12 authority was found. Phases 2-13
were not implemented against production code, because doing so would either
(a) require the prohibited migration, or (b) require unsafe non-atomic
Python-side writes that violate the task's own Phase 6 correctness
requirement and would misrepresent the "no partial V12 publish" guarantee
Phase 9's failure tests are supposed to prove.

**No files were modified except this document.** No migration file was
created or edited. No test was written against production write behavior,
because no production write code was changed. `git status` at the end of
this session is unchanged from session start
(`b52ec6304f06e4d7698435f01aa7bc9eb1704c4d`) other than this documentation
edit.

### What would unblock this

A separate, explicitly-scoped task that is authorized to create AND apply a
migration extending `publish_budget_product_ranking_snapshot`'s two `INSERT`
column lists (and, per Phase 2, its `ON CONFLICT DO UPDATE` clauses) to
accept the ten already-live V12 columns, sourced from
`build_v12_shadow_rankings_for_cohort`'s output via `to_publication_payload`
(extended to conditionally emit the V12 fields when
`default_budget_sort_authority_is_v12()` is true). Once that migration
exists and is applied, the Python-side Phases 2-3, 5-13 in this task's
instructions become straightforwardly implementable exactly as specified,
inside the RPC's existing atomic-transaction guarantee — no architecture
change beyond the column-list extension is needed.
