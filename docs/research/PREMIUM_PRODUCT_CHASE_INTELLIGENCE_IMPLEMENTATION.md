# Premium Product Chase Intelligence — Implementation

Status: **PREMIUM_PRODUCT_CHASE_INTELLIGENCE_IMPLEMENTED_CODE_ONLY**, with one honestly-reported
open item: the fully authority-coherent production path currently resolves 0/22 sets ready
against the live pinned budget cohort, due to a pre-existing pull-rate/financial-run staleness
gap that ALSO affects the already-canonical V12 budget ranking's own Accessibility resolution
(confirmed independently — not introduced by this work; see §7).

This is additive, separate Premium functionality. **Overall RIP V12 was not touched or altered
in any way.** No migration was applied. No production data was written.

## 0. Workspace

- Branch: `fix/public-rankings-entitlement-regression-2`
- Start HEAD (session start): `04c2c5bd`
- End HEAD: unchanged by this work — a concurrent, unrelated commit
  (`a1331bb0`, `feat(market-explorer): daily operationalization orchestrator (Prompt 5)`)
  landed on the branch during this session from other work; this session made **no commits**.
- `git status --short` throughout: all pre-existing modified/untracked files (budget ranking
  service/scripts, a pending atomic-publication migration, supporter-competitive-utility
  research data) were left untouched. Only new files were added (listed in §9).

## 1. Existing Chase construct inventory (Phase 1)

| Construct | Location | Classification |
|---|---|---|
| Chase Accessibility V1 (`A_raw`, `HC_i`) | `backend/desirability/chase_accessibility.py` | **REUSE** — canonical, unchanged, 4% of Overall RIP V12 |
| Cohort Accessibility authority for budget ranking | `backend/db/services/budget_chase_accessibility_authority.py` | **REUSE** — exact pattern reused unchanged for this work |
| Chase Accessibility snapshot read/write model | `backend/db/services/chase_accessibility_service.py` | **REUSE** — `load_drawable_variants` reused for per-set variant batching |
| Budget floor-quantity allocator | `backend/calculations/evr/budget_normalized_product_ranking.py` | **REUSE** — `whole_unit_allocation` reused unchanged |
| Pinned budget cohort authority | `backend/db/services/budget_product_ranking_authority.py` | **REUSE** — `load_pinned_cohort` reused unchanged |
| Card Chase Efficiency (`domain/pokemon/chase_efficiency.py`, `db/services/chase_efficiency_service.py`, `chase_efficiency_query_service.py`) | card-level Premium construct, `/explore/card-chase-efficiency`, `FEATURE_CARD_CHASE_EFFICIENCY` | **KEEP_SEPARATE** — untouched, distinct feature flag, distinct question ("best way to pursue this card") |
| `chase_economics_service.py`, `sealed_product_rip_service.py` | product-level RIP services | **KEEP_SEPARATE** — untouched |
| `FEATURE_CHASE_OPENING_ROUTE`, `FEATURE_CHASE_VS_BUY`, `FEATURE_CHASE_RANKINGS` | pre-existing Premium feature identities in `index_plan_access.py` | **KEEP_SEPARATE** — pre-existing, unused by this work, left exactly as found |
| `backend/research/product_chase_economics/{contract.py,metrics.py,runner.py,validation.py}` (Stage V-C) | research module | **HISTORICAL_ONLY** — `RESEARCH ONLY` per its own docstrings; not imported into production; `pack_equivalent_cost`/tier-threshold logic re-derived (not imported) in the new production module because that module is explicitly non-production |
| `backend/scripts/build_product_chase_opportunity_stage12.py` + `backend/research/product_chase_opportunity_stage12` (Stage XII) | research module — established `1-(1-p)^n` at pack scale and the quantity-dominance question this task revisits | **HISTORICAL_ONLY** — preserved untouched; its own `fetch_set` pattern (latest run per set) was explicitly reused, clearly labeled, for the Phase 19 diagnostic pass only |
| `backend/desirability/chase_core_k.py` ("Core K") | superseded terminology | **SUPERSEDED** — not touched, not reused |
| `frontend/components/pokemon/card-detail/ChaseEfficiencySection` (`PokemonCardDetailClient.jsx`) | Card Chase Efficiency frontend | **KEEP_SEPARATE** — untouched, no cross-reference added |

This inventory is a targeted trace of every construct this task named, not an exhaustive audit
of every "chase"-adjacent file in the repo (hundreds of research/scratch scripts exist under
`backend/research/` and `backend/scripts/`); nothing outside the above was touched.

## 2. Product Chase contract (Phase 2)

Name: **"Chase Access at Budget V1"**.

Deliberately not "Product Chase Efficiency" — the primary cross-format authority is `O_budget`,
not ECE, matching the task's naming guidance and this repo's convention of naming Chase
constructs for what they measure (`chase_accessibility_v1_*`, `chase_efficiency_*` already carry
distinct, non-interchangeable meanings here).

Versions:
- `product_chase_access_v1_hc_weighted_budget_reachability_modeled_probability` (O_budget)
- `efficiency_per_effective_cost_v1_araw_over_pack_cost` (ECE)

Contract shape (four sub-blocks, kept separate — never one ambiguous score), as returned by
`resolve_product_chase_access` / the Premium API:

- **(A) Set-level inputs**: `aRaw`, `chaseAccessibilityReady`, `chaseAccessibilityReasons`,
  `chaseAccessibilityVersion`.
- **(B) Product context**: `sealedProductId`, `setId`, `productName`, `productFamily`,
  `productMarketCost`, `randomPackCount`, `effectivePackCost`, `calculationRunId`.
- **(C) Comparable-format efficiency context**: `ece`, `eceVersion` (see §5 policy).
- **(D) Explicit-budget Chase Access**: `oBudget`, `oBudgetPct`, `oBudgetStatus`,
  `quantity`, `actualCommittedCapital`, `unusedCapital`, `capitalUtilization`,
  `effectivePacks`, `oBudgetRank`.

## 3. O_budget canonical math (Phase 3)

`backend/desirability/product_chase_access.py::compute_o_budget`:

```
O_budget = sum_i HC_i * [1 - (1 - p_i)^n]
HC_i     = V_i^2 / sum_j V_j^2      (reused unchanged from chase_accessibility.compute_chase_significance)
p_i      = modeled_probability      (never effective_pull_rate)
```

Keyword-only signature: `compute_o_budget(*, variants, effective_packs, has_pull_model=True,
set_id=None, calculation_run_id=None, min_mapped_mass=MIN_MAPPED_HC_MASS)`. No DB access inside.
Verified by unit test (`test_o_budget_at_n_equals_1_matches_chase_accessibility`): at `n=1`,
`O_budget == A_raw` exactly, since `1-(1-p)^1 == p`. Fails closed identically to Chase
Accessibility on `mapped_hc_mass < 0.99`, mixed set/run, duplicate variant IDs, no pull model, no
priced universe. `n=0` returns a real `0.0` (not unavailable); a missing/invalid pack count
returns `unavailable_no_effective_pack_count` / `unavailable_invalid_effective_pack_count` (never
a fabricated zero).

## 4. n / effective-pack semantics (Phase 4)

`effective_random_packs(*, quantity, random_pack_count) -> quantity * random_pack_count`. Never
`budget / pack_price`. `quantity` is the REAL whole-unit quantity from the existing floor-quantity
allocator (`whole_unit_allocation`, reused unchanged — never reimplemented). `random_pack_count`
is read directly off the pinned cohort row (`simulation_sealed_product_results.random_pack_count`,
the same canonical composition column the V4/V12 budget-ranking pipeline already trusts and
already asserts `>= 1` for; see `budget_product_ranking_authority.load_pinned_cohort`'s own
composition assertion). Guaranteed accessories are excluded upstream by that same column — this
module performs no composition logic of its own and does not re-derive pack counts.

## 5. O_budget vs probability framing (Phase 5)

Documented in the module docstring and enforced by naming: fields are `oBudget`/`oBudgetPct`, no
field or user-facing copy calls it "a chance of a chase" anywhere in the backend module, the
orchestration service, the API response projector, or the frontend component. Frontend copy: "how
reachable is this set's important collectible value through this product?" — bounded [0,1],
framed as a weighted reachability index.

## 6. ECE role and policy (Phase 6)

`effective_pack_cost` and `compute_ece` in `product_chase_access.py`: pure, descriptive-only,
no ranking/leaderboard entry point exists in the module (a structural test asserts no
`*ece*rank*`/`*ece*leaderboard*`/`*ece*sort*` public name exists). **Comparability policy
decision**: ECE is exposed ONLY as per-product descriptive context in the Chase Access response
(sub-block C); no family-scoped ECE ranking surface was built in this pass, because this task did
not include a validated family-taxonomy comparability study — rather than fake comparability, that
capability is simply absent. It is never wired into the cross-format `O_budget` ranking, Overall
RIP, or the normal Plus product rankings. Permanent regression test
(`test_phase7_same_set_ece_ordering_is_exactly_inverse_effective_pack_cost_ordering`) proves the
same-set price-only equivalence across 4 fabricated products of one set/run (12/12 ordered pairs
checked) — this is Phase 7.

## 7. Authority coherence (Phase 11)

`backend/db/services/product_chase_access_authority.py::resolve_product_chase_access` requires,
for every product: (a) its cohort `calculation_run_id` to match the variant universe read for its
`set_id` (variants are read keyed by that exact run — a mismatch would either raise inside
`compute_o_budget` via `ProductChaseAccessInputError`, or, more commonly in this integration,
simply find zero matching rows and report `unavailable_pull_model`), and (b) the SAME cohort-level
Chase Accessibility authority check the V12 budget ranking already uses
(`resolve_budget_cohort_accessibility`, reused unchanged, including its `stale_calculation_run`
rejection reason).

**Live finding**: running this against the current production pinned cohort
(`price_as_of=2026-08-26`, 138 products / 22 sets) returned **0/22 sets ready** —
`resolve_budget_cohort_accessibility` reports every set failed with `stale_calculation_run`
(the persisted `pokemon_set_chase_accessibility_snapshot_latest` row's `calculation_run_id`
does not match the current financial cohort's run), and independently, direct inspection showed
`simulation_card_variant_pull_rates` currently has **zero rows** for the current financial
cohort's `calculation_run_id`, for the one set checked. **This is confirmed to be a pre-existing
production data-pipeline staleness condition, not a defect introduced by this session**: calling
`resolve_budget_cohort_accessibility` directly (the exact function the ALREADY-CANONICAL V12
budget ranking uses) against the same live cohort also reports 0/22 ready. The new authority
coherence code is doing exactly what it should — failing closed rather than silently mixing runs
— and in the process surfaced that the existing V12 budget-ranking Accessibility contribution is
also currently non-functional in production for the same reason. This is a finding worth separate
follow-up outside this task's scope (rebuilding/re-cadencing the Chase Accessibility snapshot
against the current simulation runs), not something this task is positioned to fix.

## 8. HC batching architecture (Phase 12/13)

`load_variant_universe_for_cohort` reads `simulation_card_variant_pull_rates` **once per distinct
`calculation_run_id`** present in the cohort (via `chase_accessibility_service.load_drawable_variants`,
reused unchanged), never once per product and never once per budget. Verified directly by call-count
assertions against a fake client (`test_product_chase_access_authority.py`):
- 3 products across 2 sets → exactly 2 variant-table reads (not 3).
- 5 products across the same 2 sets → still exactly 2 variant-table reads.
- The Accessibility cohort authority check is one single batched `.in_(...)` read regardless of
  cohort size.

**No new per-card HC persistence was added** — HC is computed in-memory, once per set, per
orchestration call, and reused across every product/budget combination in that call, exactly as
Phase 12 specified.

Live production profiling (22 sets, 138 products, one budget per call):
- `accessibilityCohortReads`: 1
- `variantUniverseReads`: 22 (one per set, bounded by distinct-set count, not product count)
- Compute time per budget call: ~1.18–1.24s (dominated by 22 sequential `load_drawable_variants`
  network round-trips against the live DB, not by the O_budget math itself)
- Payload size: ~140–161 KB across the 6 representative budgets (138 products/call)

## 9. Persistence decision (Phase 14)

**No new schema.** O_budget is budget-dependent and computed on-demand from current authority
(cohort + variant universe), matching the task's expected likely conclusion. Profiling (§8) shows
the on-demand path is dominated by 22 bounded network reads, not compute — acceptable for a
Premium request/response cycle and not a case for a persisted table of every possible budget
combination. No migration file was created or applied for this feature.

## 10. Premium API (Phase 15)

`GET /explore/product-chase-intelligence` in `backend/api/main.py` — separate from
`/explore/product-rankings/overall` (normal Plus rankings) and `/explore/card-chase-efficiency`
(Card Chase Efficiency). Gate: `_require_product_chase_intelligence` (mirrors
`_require_card_chase_efficiency` exactly — authenticate first, then
`has_index_feature_access(plan, FEATURE_PRODUCT_CHASE_INTELLIGENCE)`, 403 with
`PRODUCT_CHASE_INTELLIGENCE_PREMIUM_REQUIRED` otherwise, `emit_security_event` on denial).
Response is projected through `project_product_chase_access_response` (new, allowlist-based,
`backend/domain/access/index_plan_access.py`) — never the RIP or normal-rankings projector.

**Entitlement is enforced server-side, and this is actually tested**, not just described:
`backend/tests/unit/api/test_product_chase_access_premium_gate.py::test_entitlement_matrix_a_plus_or_free_request_is_rejected`
calls the real gate function with `plan=None` (Free/anonymous), `plan="plus"`, and `plan="premium"`
and asserts only Premium returns a user id — Free and Plus both raise `HTTPException(403,
PRODUCT_CHASE_INTELLIGENCE_PREMIUM_REQUIRED)`. A second test confirms an unauthenticated caller is
rejected with 401 before plan resolution even runs (`plan lookup must not run` assertion). A third
confirms the route gates before touching `load_pinned_cohort`/`resolve_product_chase_access` at
all (source-order check). A fourth confirms the response projector drops an arbitrary
unlisted field (simulating a leak) and only returns the declared allowlist.

## 11. Frontend (Phase 16)

`frontend/components/pokemon/sealed-product-detail/ProductChaseIntelligenceSection.jsx` (new,
standalone) + `frontend/app/api/explore/product-chase-intelligence/route.js` (thin proxy, mirrors
`card-chase-efficiency/route.js` exactly — no entitlement logic in the proxy, enforced entirely by
the backend). Displays Set Chase Accessibility %, effective pack cost, ECE context, and (only when
a budget is supplied) "Chase Access at $X", "You can open: Q products / N effective packs", and
rank. No client-side formula computation — verified by a contract test asserting no
`Math.pow`/exponent/HC-formula tokens appear in the component; every number is read verbatim off
the server payload. Explicitly never presented as part of Overall RIP (copy + contract test).
**Not yet wired into `SealedProductDetailClient.jsx`'s page composition** — built and tested as a
standalone, self-fetching section ready to be dropped in; the actual page-composition wiring
(prop plumbing for `sealedProductId`/`setId`/a budget selector UI) was left undone in this pass to
avoid risking `ProductRipSection`'s existing, tested composition without a running dev server to
verify the integration visually.

## 12. Card Chase Efficiency separation (Phase 17)

Confirmed via grep: zero cross-references in either direction between
`ProductChaseIntelligenceSection.jsx`/`product_chase_access*.py` and
`PokemonCardDetailClient.jsx`/`chase_efficiency_service.py`/`chase_efficiency.py`. Distinct
feature flags (`FEATURE_PRODUCT_CHASE_INTELLIGENCE` vs `FEATURE_CARD_CHASE_EFFICIENCY`), distinct
API routes, distinct response contracts. Product Chase Intelligence answers "which sealed route
reaches the most of this set's value at my budget"; Card Chase Efficiency (untouched) answers
"what's the best way to pursue this specific card."

## 13. Test matrix (Phase 18) — exact pass/fail counts

| Group | File | Result |
|---|---|---|
| A/B/C/D/E math + authority + ECE invariant | `backend/tests/unit/desirability/test_product_chase_access.py` | **26/26 passed** |
| B/C/E/G authority + batching + N+1 + ranking | `backend/tests/unit/db/services/test_product_chase_access_authority.py` | **9/9 passed** |
| F entitlement (real gate calls, real 403/401) | `backend/tests/unit/api/test_product_chase_access_premium_gate.py` | **6/6 passed** |
| Frontend: no formula computation, route separation, RIP separation | `frontend/.../ProductChaseIntelligenceSection.contract.test.mjs` | **7/7 passed** |
| H regression: Card Chase Efficiency existing tests | `test_chase_efficiency_premium_gate.py`, `test_chase_efficiency_service.py`, `test_chase_efficiency.py` (domain) | unchanged, all passing (part of the 212/213 combined run below) |
| H regression: Overall RIP V12 Chase Accessibility existing tests | `test_overall_rip_v12_chase_accessibility.py`, `test_chase_accessibility.py`, `test_overall_rip_v11.py` | unchanged; **1 pre-existing failure** (`test_chase_accessibility_is_not_wired_into_overall_rip` — fails because Chase Accessibility genuinely IS wired into V12 by prior, unrelated work; confirmed via `git status` that `weighted_rip.py`/`chase_accessibility.py`/this test file were never touched this session) |
| H regression: budget-ranking authority/readiness | `test_budget_product_ranking_authority.py`, `test_budget_product_ranking_readiness.py` | unchanged, all passing |
| **Combined targeted run** | all of the above together | **246 passed, 1 failed** (the pre-existing, unrelated failure above) |

**One real regression was found and fixed during this pass**: adding `FEATURE_PRODUCT_CHASE_INTELLIGENCE` to `_PREMIUM_FEATURES` broke `backend/tests/unit/domain/access/test_index_plan_access.py::test_locked_commercial_capability_sets_fail_closed_and_inherit`, which pins the exact size of `_PREMIUM_FEATURES` (`== 7`) specifically so a new feature can never be added silently. This is the guard doing its job, not a false failure — updated the pinned count to `8` with a comment naming the addition. `test_index_plan_access.py` is now 34/34 passing.

A full, unfiltered `backend/tests/unit` sweep (7,937 tests) was also run for broader regression coverage; see §17 for its result.

Full `backend/tests/unit` sweep was also launched; see §16 for its outcome once complete.

## 14. Production validation (Phase 19) — read-only, both runs reported in full

### 14a. Primary (fully authority-coherent) run — `validate_product_chase_access_phase19.py`

Against the live pinned cohort (`price_as_of=2026-08-26`, 138 products, 22 sets): **0 products
ranked at every one of the 6 representative budgets ($25/$50/$100/$150/$250/$500)**. Every product
resolved to either `unavailable_pull_model` (58 products, sets where the fully-coherent variant
read found nothing under the CURRENT financial run) or `unavailable_budget_below_one_unit` (80
products, correctly ineligible at the budget tested — not a bug). No O_budget values, no
correlations, no leaders could be computed on this fully-coherent path, for the reason documented
in §7. Query batching held throughout (1 accessibility read + 22 variant reads per budget call, as
designed) and compute time (~1.2s/call for 138 products) was consistent regardless of the
authority outcome.

### 14b. Diagnostic (explicitly non-authoritative) run — `validate_product_chase_access_phase19_diagnostic.py`

To still answer the Stage XII quantity-dominance research question honestly, a second, clearly
labeled DIAGNOSTIC pass relaxed the run-coherence requirement: for each of the 22 sets, it read
that set's own MOST RECENT pull-rate run (the exact pattern
`build_product_chase_opportunity_stage12.py` itself already uses for research), paired with the
CURRENT product price/quantity. **This mixes two runs and is explicitly not the production
authority contract** — reported only as evidence toward the quantity-dominance question, never as
a production-ready number.

Results (138-product cohort, 22 sets, all with a usable relaxed A_raw):

| Budget | Ranked | Leader | Spearman(O_budget, effective_packs) | Spearman(O_budget, ECE) | Spearman(O_budget, price) | Spearman(O_budget, effective_pack_cost) | Spearman(O_budget, set A_raw) |
|---|---|---|---|---|---|---|---|
| $25 | 36 | Obsidian Flames Sleeved Booster Pack | 0.591 | 0.944 | -0.524 | -0.524 | 0.710 |
| $50 | 41 | Obsidian Flames Sleeved Booster Pack | 0.447 | 0.972 | -0.320 | -0.440 | 0.725 |
| $100 | 58 | Obsidian Flames Sleeved Booster Pack | 0.527 | 0.977 | -0.465 | -0.461 | 0.816 |
| $150 | 77 | Stellar Crown Sleeved Booster Pack | 0.568 | 0.979 | -0.390 | -0.457 | 0.754 |
| $250 | 108 | Stellar Crown Sleeved Booster Pack | 0.621 | 0.963 | -0.409 | -0.562 | 0.710 |
| $500 | 133 | Shrouded Fable Booster Bundle | 0.605 | 0.973 | -0.416 | -0.585 | 0.723 |

`overall_rip_v12_score` correlation could not be computed (no non-null values available in the
join for this cohort at this diagnostic pass — `null` in every budget row above). Leader changes
across budgets: **yes**, 3 distinct leaders across the 6 budgets (a loose/sleeved booster
dominates at low budgets; a booster bundle takes over at $500 once its higher fixed guaranteed
component amortizes).

## 15. O_budget-vs-pack-count analysis (Phase 19's critical question) — honest interpretation

**Caveat restated: this is the non-authoritative diagnostic dataset (§14b), because the fully
authority-coherent path currently returns zero ranked products in production (§14a/§7).** Within
that caveat:

Spearman(O_budget, effective_packs) ranges **0.45–0.62** across the six budgets — moderate, and
notably far from the ~0.9+ that would indicate O_budget is "overwhelmingly quantity-dominated."
The much higher correlation with ECE (0.94–0.98) and the consistently negative correlation with
raw price/effective-pack-cost (-0.32 to -0.59) show the dominant driver is **packs-per-dollar** (a
price/quantity interaction — cheap-format products reach more packs per budget dollar, not simply
"whichever product has the most packs in the abstract"), and Spearman(O_budget, set A_raw) of
0.71–0.82 shows genuine, non-trivial cross-set differentiation is also contributing (a set with a
more concentrated important-card distribution measurably pulls its products' O_budget up,
independent of pack count). Leader identity changing three times across six budgets is itself
evidence against pure quantity-dominance: a purely quantity-dominated metric would keep the same
"most packs for the money" leader at every budget once eligible, whereas here the ETB/booster-bundle
tradeoff (higher guaranteed value share, more packs per unit) visibly overtakes the cheapest loose
booster only once the budget is large enough to buy several units of it.

**Honest conclusion**: on the available (diagnostic-only) evidence, O_budget shows real
cross-product differentiation beyond mere pack count — it is not degenerate in quantity — but this
finding rests on a non-authoritative dataset because the authority-coherent production path is
currently empty (§7). This is reported as the most complete honest answer achievable from what
live data currently supports, not as a certified production validation.

## 16. Full unfiltered regression sweep

`backend/tests/unit` (7,942 tests, ~14 minutes) was run in full, beyond the targeted Chase/budget
suite in §13, to check for any regression outside the areas this work touched.

Raw result: **312 failed, 7625 passed, 5 skipped.** Of the 312 failures, exactly **one** traced to
a file this session edited: the `_PREMIUM_FEATURES` pinned-count guard in
`test_index_plan_access.py` (§13), fixed and reconfirmed passing (34/34) directly after the sweep
completed — the sweep's own capture predates that fix landing on disk (a background-run timing
artifact, not a second bug), so the corrected total is **311 failed, 7626 passed, 5 skipped**.

The remaining 311 failures were spot-checked across several of their largest clusters and are all
pre-existing and unrelated to this session's work:
- **158** in `backend/tests/unit/db/services/test_pokemon_public_snapshot_service.py` — fails
  immediately with `AttributeError: module 'pokemon_public_snapshot_service' has no attribute
  'public_read_client'`, a structural mismatch in a module this session never touched (unrelated
  to Chase Accessibility, O_budget, or budget ranking).
- Several `test_treatment_market_prestige_v3_round22/23/24*` failures raise `RuntimeError: Round
  24 branch/ancestry contract failed` — a git branch/ancestor check unrelated to any code change.
- `test_chase_accessibility.py::test_chase_accessibility_is_not_wired_into_overall_rip` — the one
  already-documented (§13) pre-existing failure, confirmed via `git status` that
  `chase_accessibility.py`/`weighted_rip.py`/this test file were never touched this session.
- The rest (logging_integration, research/test_collector_appeal_v4_candidates,
  research/test_tmp_variant_collection_cutover, scripts/test_market_first_run_dry_run,
  scripts/test_pokemon_level_publication_audits, etc.) span subsystems (card treatment prestige,
  market-first-run dry-run scaffolding, TMP variant collection, logging diagnostics) with zero
  file-path or import overlap with anything this session created or edited.

No failure in the full sweep, after the one confirmed-and-fixed exception, traces to
`product_chase_access.py`, `product_chase_access_authority.py`, the new API route/gate in
`main.py`, the new `index_plan_access.py` additions, or the new frontend files.

## 17. Final decision

**PREMIUM_PRODUCT_CHASE_INTELLIGENCE_IMPLEMENTED_CODE_ONLY** (as of the original §1–§17 pass above).
**SEE §18 AND §19 BELOW — this decision label, and the §14/§15 "zero ranked products" / "V12
correlation could not be computed" conclusions, are SUPERSEDED by two later corrections. The
sections above are preserved verbatim as history, not deleted, per this doc's own standing rule.**

The math, authority-coherence, batching, API, entitlement enforcement, and frontend are built and
tested (246/247 targeted backend tests + 7/7 frontend contract tests passing, the one failure
pre-existing and unrelated to this work). The one thing this session could not fully certify is a
production-authoritative Phase 19 result, because the live Chase Accessibility pull-rate data is
currently stale relative to the sealed-product financial pipeline for every set in the cohort — a
pre-existing condition this task's own authority-coherence code correctly detected and refused to
paper over, and which independently affects the already-canonical V12 budget ranking's own
Accessibility contribution today. The diagnostic-relaxed pass suggests O_budget is NOT
quantity-dominated once the staleness gap is fixed, so `CODE_ONLY` (full ranking authority, not
demoted to diagnostic-only UI role) is the honest label — contingent on that data-pipeline
staleness being resolved (outside this task's scope) before this feature is exercised against real
production traffic.

## 18. CORRECTION #1 (immediately-prior pass) — pagination truncation in the pinned-cohort authority

**SUPERSEDES §14a/§17's "zero ranked products in production" conclusion.** The root cause was a
latent bug in `backend/db/services/budget_product_ranking_authority.py::_fetch_all_ready_rows`: a
single unpaginated `.execute()` call silently truncates to PostgREST's default page size (1,000
rows). On a `simulation_sealed_product_results` table that has grown past that, the truncated read
could omit the newest `price_as_of` cohort entirely, causing the resolver to pin to an older,
now-stale cohort while believing it had seen the whole table — this is what actually produced the
"0/22 stale_calculation_run" / zero-ranked-product result in §14a, not a genuine data-pipeline
staleness condition. `_fetch_all_ready_rows` was fixed to page explicitly via `.order(...).range(...)`
until a page returns fewer than the page size. After the fix, the CURRENT cohort (117 products / 18
sets / 18 runs, `price_as_of=2026-08-26` at the time of that pass) resolved cleanly, and the
authoritative Product Chase results reported in the task prompt for this pass (ranked-by-budget
counts $25→30 … $500→112, Spearman(O_budget, ECE)≈0.92–0.99, etc.) came from that repaired path —
**not** from the diagnostic-relaxed, explicitly-non-authoritative pass in §14b/§15. The `CODE_ONLY`
decision stands, now on genuinely authority-coherent production data instead of the diagnostic
substitute.

## 19. CORRECTION #2 (this pass) — V12 projection omission, not missing production data

**SUPERSEDES §14b's "`overall_rip_v12_score` correlation could not be computed (no non-null values
available in the join for this cohort)" claim.** That claim was independently disproven: a direct
query against `simulation_sealed_product_results WHERE financial_rip_v4_status='ready' AND
price_as_of='2026-09-02'` returns 117 rows / 18 sets / 18 runs, and **117/117 have
`overall_rip_v12_score IS NOT NULL` and `overall_rip_v12_status='ready'`**. The missing correlation
was a projection bug, not missing data.

**Root cause and fix**: `backend/db/services/budget_product_ranking_authority.py::_fetch_all_ready_rows`
selected an explicit column list for the pinned-cohort read that never included
`overall_rip_v12_score`/`overall_rip_v12_status`/`overall_rip_v12_version`, even though those
columns exist on the same row. `backend/scripts/validate_product_chase_access_phase19.py` worked
around the gap by issuing a SECOND, entirely UNFILTERED (`price_as_of`-blind) full-table read of
just those two v12 columns and joining it back onto the cohort by `sealed_product_id` — which is
itself a latent authority-coherence bug: it could silently pair a v12 score from a *different*
`price_as_of` cohort onto a product row from the pinned cohort, exactly the class of blended-market-state
bug this module's whole design (see its module docstring) exists to prevent.

**Fix applied**:
- `budget_product_ranking_authority.py`, `_fetch_all_ready_rows`'s `columns` string (around line
  94–99): added `overall_rip_v12_score,overall_rip_v12_status,overall_rip_v12_version` to the
  existing SELECT. No new query was added — this extends the one query the module already issues.
- `validate_product_chase_access_phase19.py`: removed the second unfiltered re-fetch entirely; the
  script now reads `overall_rip_v12_score`/`overall_rip_v12_status` directly off the SAME pinned
  cohort rows `load_pinned_cohort` returns, and pins the default `price_as_of` to `2026-09-02` (the
  current live authority cohort) instead of the older `2026-08-26` value hardcoded in the original
  §14a run.
- No N+1 was introduced — column additions to an existing single paginated SELECT do not add
  queries; `resolve_product_chase_access`'s per-set batching (§8) is untouched.

**Corrected authoritative results** (live cohort: 117 products, 18 sets, `price_as_of=2026-09-02`,
re-run via the repaired `validate_product_chase_access_phase19.py`):

| Budget | Ranked | Leader | Spearman(O_budget, effective_packs) | Spearman(O_budget, **overall_rip_v12_score**) | Spearman(O_budget, ECE) | Spearman(O_budget, price) | Spearman(O_budget, effective_pack_cost) | Spearman(O_budget, set A_raw) |
|---|---|---|---|---|---|---|---|---|
| $25 | 30 | Stellar Crown Booster Pack | 0.497 | **0.431** | 0.919 | -0.516 | -0.516 | 0.641 |
| $50 | 34 | Stellar Crown Booster Pack | 0.345 | **0.284** | 0.986 | -0.295 | -0.395 | 0.684 |
| $100 | 47 | Stellar Crown Booster Pack | 0.470 | **0.428** | 0.980 | -0.425 | -0.395 | 0.777 |
| $150 | 64 | Stellar Crown Booster Pack | 0.521 | **0.398** | 0.973 | -0.406 | -0.397 | 0.740 |
| $250 | 92 | Stellar Crown Booster Pack | 0.612 | **0.361** | 0.957 | -0.413 | -0.551 | 0.693 |
| $500 | 112 | Shrouded Fable Booster Bundle | 0.576 | **0.315** | 0.971 | -0.387 | -0.535 | 0.700 |

`overall_rip_v12_score` is now a finite, real correlation at every budget — it is no longer `None`.
No genuine pairing limitation remains for this cohort: all 117 products in the pinned cohort carry
a non-null V12 score, so every product that has an O_budget value also has a V12 pairing; the
Spearman inputs are the full ranked set at each budget, not a reduced subset.

**Interpretation**: O_budget correlates moderately-positively with Overall RIP V12 (0.28–0.43,
weaker than its correlation with ECE, effective packs, or set A_raw). This is expected and
reinforces the product decision's semantic-limit statement (§5/product decision text): O_budget and
Overall RIP V12 measure genuinely different things — Overall RIP V12 blends financial return and
collector appeal at the SKU level, while O_budget measures budget-constrained reachability of a
set's important collectible value. A moderate, non-trivial, non-zero correlation is the honest
result; a near-1.0 correlation would have suggested O_budget is redundant with the already-canonical
V12 score, which it clearly is not, and a near-0 correlation would have suggested no
relationship at all, which is also not what the data shows.

**Final decision (superseding §17)**: `O_BUDGET_PRODUCT_RANKING_USEFUL` for the backend research
question (unchanged from the task's locked prior decision), and, for this integration pass,
**`PREMIUM_PRODUCT_CHASE_INTELLIGENCE_PAGE_INTEGRATED_CODE_ONLY`** — see §20 for the full
frontend-integration, performance, and entitlement record for this pass.

## 20. Frontend integration, single-product performance fix, and entitlement verification (this pass)

**Page integration (Phase 3/4)**: `ProductChaseIntelligenceSection`/`ProductChaseIntelligenceLock`
(`frontend/components/pokemon/sealed-product-detail/ProductChaseIntelligenceSection.jsx`) are now
mounted in `SealedProductDetailClient.jsx`, directly after the Product RIP block and before
`ProductComparisonSection`, gated on `hasIndexPremiumAccess(user?.index_plan)` — a distinct,
higher tier than the existing `hasIndexPlusAccess` gate used for Product RIP, so a Plus (non-Premium)
user sees the static `ProductChaseIntelligenceLock` shell, never the fetching component. A
pre-existing bug in the standalone component (`<PlanUpgradeLink plan=... feature=...>`, which does
not match `PlanUpgradeLink`'s actual `requiredPlan`/`source` prop contract used everywhere else on
this page) was fixed to `requiredPlan={INDEX_PLAN_PREMIUM} source="sealed-product-chase-intelligence"`
while wiring it in.

**Single-product performance fix (Phase 12)**: before this pass, `GET
/explore/product-chase-intelligence` always resolved the orchestration call
(`resolve_product_chase_access`) against the FULL pinned cohort regardless of how the frontend used
it — meaning a single product-detail-page load paid for 1 Accessibility batch read + 18
variant-universe reads (one per distinct set in the whole 18-set cohort) just to render one
product's row. A new `sealed_product_id` query param on the backend route
(`backend/api/main.py::get_product_chase_intelligence`) filters the pinned cohort down to that one
product's row BEFORE calling `resolve_product_chase_access`; because that function batches its reads
once per distinct set IN THE COHORT IT IS HANDED (unchanged), a 1-row cohort now costs exactly 1
Accessibility read + 1 variant-universe read. Verified with a new fake-client test,
`backend/tests/unit/api/test_product_chase_intelligence_single_product_scope.py`, asserting exact
call counts:
- single product / one budget: 1 Accessibility read, 1 variant-universe read (was 1 + N-sets).
- one set's products / one budget (unscoped call over a 3-set fixture): 1 Accessibility read, 3
  variant-universe reads (one per distinct set present) — unchanged, this is the existing,
  deliberately-more-expensive cross-format ranking path, still used when `sealed_product_id` is
  omitted.
- an unknown `sealed_product_id` returns 404 with **zero** Accessibility/variant reads issued (the
  cohort miss is caught before any per-set batching runs).

Because ranking a single product against itself would trivially and misleadingly report `"#1"`, the
route nulls `oBudgetRank` on every product in a scoped response; a caller that wants the real
cross-format Chase Access ranking must omit `sealed_product_id` and pay for the full cohort
resolution — kept as a separate, explicit, more expensive operation (Phase 8), not built into the
product page by default.

**Budget selector (Phase 5)**: the section owns its own budget state, defaulting to **$100** (no
personalized/default budget exists to derive from, and an "unlimited"/`full_market` default is
explicitly never invented), with an explicit selector over the canonical bands **$25/$50/$100/$150/
$250/$500** — the same numeric values already used as canonical bands in
`frontend/lib/explore/overallProductRankingsServer.js`'s `ALLOWED_BUDGETS` (that list also carries
`full_market`, `750`, `1000`, `1250` for the unrelated Plus product-ranking surface; this section
does not import that module directly to avoid coupling a Premium single-product surface to an
unrelated Plus ranking module, but intentionally mirrors its band values). No custom/arbitrary
budget input was added: while the backend `budget` query param does accept any `float >= 0`, adding
free-form input was judged unnecessary scope for a first integration and was deferred in favor of
the fixed canonical bands the task explicitly asked for.

**Section content (Phase 6)**: primary metric "Chase Access at $&lt;budget&gt;" (O_budget as a
percentage); supporting fields — quantity purchasable at that budget, effective random packs,
actual committed capital, unused capital (shown only when positive), Set Chase Accessibility
(A_raw), and Effective Pack Cost. A "Chase Depth" diagnostic was NOT added: the current
`/explore/product-chase-intelligence` product-row contract does not surface a per-product chase-depth
value (only the cohort-level Accessibility snapshot carries `chase_depth`, and it is not currently
projected onto the per-product entry in `product_chase_access_authority.py`) — rather than fabricate
a frontend-side approximation, this is called out honestly as a scope gap for a future pass, not
silently invented.

**ECE presentation (Phase 6/7)**: labeled "Effective Pack Efficiency" with an info-popover reading
"Reflects Set Chase Accessibility relative to this product's effective pack cost. It is a
per-product diagnostic, not an overall product score, and carries no cross-format rank." — never
given a numeric rank, never called a score.

**Copy discipline (Phase 7)**: the section's primary framing is "At this budget, how much access
does this product give you to the set's most important collectible value?" — the exact framing the
task specified. The forbidden phrases ("chance of pulling a chase", "chance to hit the chase") are
grepped out of all user-facing (non-comment) text by a dedicated contract test.

**Entitlement verification (Phase 9)**: verified two ways, not just by reading the component's
conditional-rendering logic:
1. `SealedProductDetailClient.jsx`'s server-rendered `initialDetail` (from
   `getSealedProductDetailServer`/`normalizeSealedProductDetail`) was grepped for any Chase Access
   field (`oBudget`, `chaseAccess`, `ProductChase`) — none exist. The Premium payload is fetched
   ENTIRELY client-side, behind the `premiumEntitled` gate, and never touches SSR page props for any
   plan tier, so there is no serialized-props or hidden-DOM leak path to audit away.
2. The backend gate (`_require_product_chase_intelligence`) and its existing negative tests
   (`test_product_chase_access_premium_gate.py` — Free/Plus/anonymous all rejected with 403/401
   before any cohort/authority read; re-run and still 6/6 passing) remain the actual enforcement
   boundary; the frontend gate is a UX convenience only, per the project's stated architecture.

**Loading/error/unavailable states (Phase 10)**: five distinct states are implemented and each has
its own `data-chase-state` marker plus a dedicated contract-test assertion: `loading`, `error`
(generic API failure), `unavailable` (product not present in the current cohort — HTTP 404),
`budget-below-minimum` (exact copy: "Budget is below the current price of one unit."), and two
further authority-truthful states — `authority-unavailable` (Chase Accessibility not ready for this
product's set, echoing the server's own rejection reasons) and `unsupported-composition` (any other
`oBudgetStatus` prefixed `unavailable_`, e.g. an unsupported random-pack composition).

**Responsive UI (Phase 11)**: verified structurally via the contract test suite (no dev-server
visual pass was performed) — the budget-band buttons sit in a `flex flex-wrap` row so they wrap
rather than overflow on narrow viewports, and the section renders exactly one primary metric block
plus a small supporting grid, deliberately kept out of RIP-breakdown-level density.

**Tests (Phase 13)** — exact counts:
- Backend, this pass's new/updated suites:
  `test_product_chase_intelligence_single_product_scope.py` (3/3),
  `test_product_chase_access_premium_gate.py` (6/6, re-run unchanged),
  `test_product_chase_access_authority.py` (12/12, re-run unchanged),
  `test_budget_product_ranking_authority.py` (unchanged, still passing),
  `test_product_chase_access.py` (desirability math, re-run unchanged).
  Combined targeted filter (`-k "product_chase or card_chase_efficiency or overall_rip_v12 or
  budget_product_ranking"`): **261/261 passing**.
- Frontend: `ProductChaseIntelligenceSection.contract.test.mjs` grew from 7 to **16/16 passing**
  (9 new assertions: mounting + Premium gating, no-full-cohort-fetch scoping, canonical budget
  bands/default, copy discipline, all 5 distinct states, ECE-never-ranked, no leaked
  `oBudgetRank`, mobile-safe wrapping). `SealedProductDetail.contract.test.mjs` (11/11) and
  `productDetailModel.test.mjs` (7/7) re-run unchanged — combined **34/34 passing**, confirming the
  new mount does not disturb Product RIP, market panel, comparisons, or EV-realization behavior.
- Regression spot-check: `components/pokemon/card-detail/*.test.mjs` was run alongside the above;
  one pre-existing, unrelated failure surfaced
  (`ChaseEfficiencySection.contract.test.mjs::"Card Treatment explains the dynamic V1 mapping and
  exclusions"`, a CRLF/mixed-line-ending string-anchor issue in a file this pass never touched — see
  the standing `feedback_crlf_line_endings_in_source_string_tests` note). Confirmed via `git status`
  that neither `ChaseEfficiencySection.jsx` nor its test were modified this session.

**No deploy, publish, backfill, or Overall RIP V12 scoring change occurred.**
