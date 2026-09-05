# Overall RIP V12 UI Standardization (Prompt UI-1)

Status date: 2026-09-04. Branch: `fix/backend-memory-restart-p0-20260904`. This
is the foundational presentation-contract pass for a planned 6-part UI series
(UI-1 of 6). Frontend presentation + docs only. No backend scoring, no
deploy, no publication.

## 1. Locked information hierarchy (confirmed, unchanged from spec)

```
Overall RIP
  -> Market-Based Opening Quality   (explanatory grouping only, NOT a persisted score)
     -> Financial RIP
     -> Chase Accessibility
  -> Collector Appeal
```

Three scored ingredients: Financial RIP, Chase Accessibility, Collector
Appeal. Two explanatory parent categories: Market-Based Opening Quality,
Collector Appeal.

## 2. No-weight-disclosure policy (the core rule of this pass)

Forbidden in normal user-facing UI: `86%`, `4%`, `10%`, `90%`, `95.56%`,
`4.44%`, and any sentence stating a component's contribution percentage to
Overall RIP. Presentation-layer rule only — backend scoring code, scoring
tests, research docs, and internal audit payloads may retain real weights. A
metric whose *natural value* is a percentage (e.g. "Chase Accessibility raw
value = 0.21%") remains presentable — that is a measured metric, not a
weight.

### What was found and fixed

- `frontend/components/explore/overallRipExplanationHierarchySelector.mjs`
  was the ONE generator of weight-percentage headlines
  (`"86% Financial RIP V4 + 4% Chase Accessibility Score + 10% Collector
  Appeal V5"`, `"90% Financial RIP V4 + 10% Collector Appeal V5"`, and a
  Market-Based `internalHeadline` disclosing the derived `95.56%`/`4.44%`
  split) for every runtime surface using it.
- Fixed: headlines are now fixed, presentation-safe sentences:
  - V12 available: `"Overall RIP combines Market-Based Opening Quality with
    Collector Appeal."`
  - V10 available: `"Overall RIP combines Financial RIP with Collector
    Appeal."` (neutral wording — old V10 weights not disclosed either, per
    the prompt's guidance).
  - Market-Based grouping: `"Market-Based Opening Quality combines Financial
    RIP with Chase Accessibility."`
  - `internalHeadline` (the `95.56%`/`4.44%` field) deleted; the now-unused
    `formatWeightPercent()` helper deleted.
- Raw weight numbers (`weights.*`, `internalFinancialShare`,
  `internalAccessibilityShare`, `marketBasedWeight`, `collectorWeight`)
  remain on the selector's output object for non-UI/internal consumers
  (audit/historical tooling); no current render path reads them into copy.
- Stale docstrings/comments quoting the old percentage sentences updated in
  `overallRipExplanationHierarchySelector.mjs`, `OverallRipExplanationHierarchy.jsx`,
  and a comment block in `RipStatisticsPageClient.jsx`.
- Full grep across `frontend/components` for `90%|86%|95.56|4.44` confirmed
  no other rendered occurrence of a scoring-weight sentence. Other hits:
  unrelated "90% chance to pull" pack-math copy (a genuinely different
  metric — `ChaseEfficiencyFigures.jsx`, `RipDecisionPage.jsx`,
  `RipStoryEvidence.jsx`, `PullRateAssumptions*.jsx` — left untouched), and
  historical/internal code comments describing the Overall RIP v4/v7/v8
  lineage (`canonicalRipV7.mjs`, `ripScoreBreakdownSelector.mjs`,
  `ripHeroScoreMode.mjs` — comments only, preserved as historical record).
- `ProductRipSection.jsx` and `ProductChaseIntelligenceSection.jsx` checked
  directly: no weight-percentage copy present in either. No change needed.

## 3. Chase Accessibility public presentation contract (Phase 3 — built this pass)

New module: `frontend/components/explore/chaseAccessibilityPresentationSelector.mjs`,
exporting `selectChaseAccessibilityPresentation(...sources)`. It does not
duplicate backend projection — it is a thin, normalized READ of the
already-existing `publicRipContractV11.chaseAccessibility` block projected by
`backend/desirability/public_rip_contract_v11.py::_chase_accessibility_block`
(`value`, `percent`, `status`, `statusReason`, `version`, `chaseDepth`,
`mappedHcMass`, `publicQuestion`, `technicalTooltip`).

Returned shape:
```
available, status, statusReason, label, publicQuestion, technicalTooltip, version,
rawAccessibility, displayAccessibility,      // PRIMARY — the scored metric
rank, cohortSize, tier,                      // ALWAYS null (see Phase 8)
chaseDepth, chaseDepthAvailable,             // diagnostic, real backend field
mappedHcMass, mappedHcMassAvailable,         // diagnostic, real backend field
valueConcentration, topCardConcentration,    // diagnostic, ALWAYS null (not yet backed by any service found)
```
No scoring weight or transform constant is exposed. Tested in
`chaseAccessibilityPresentationSelector.test.mjs` (7 tests, all passing) —
covers availability, non-fabrication of rank/tier even if a source object
smuggles rank-shaped fields, non-fabrication of concentration diagnostics,
and absence of weight/transform literals.

## 4. Shared Market-Based presentation component (Phase 5 — built this pass)

New component: `frontend/components/explore/MarketBasedOpeningQualityBreakdown.jsx`,
a PRESENTATION container (no new score, no arithmetic). Props: `canonical`
(the already-resolved Financial RIP bundle, same rule `FinancialRipV3Breakdown`
follows — no independent re-resolution that could disagree with the hero),
`sources` (raw sources for the Chase Accessibility selector), `depth`
(`"compact"` | `"full"`).

- **COMPACT**: Financial RIP summary line (scored-dimension count + status)
  + Chase Accessibility summary line (`displayAccessibility` as a percent, or
  the backend status reason when unavailable).
- **FULL**: reuses `FinancialRipV3Breakdown` verbatim (no re-implementation,
  no restyle) for the six Financial dimensions, alongside a Chase
  Accessibility panel showing the primary metric, an explicit
  "Cohort rank not yet available" line (rank is NEVER fabricated — see Phase
  8), and a disclosure panel labeled "Diagnostics — not part of the Chase
  Accessibility score" containing Chase Depth, Value Concentration (currently
  "Not yet published"), Top-card Concentration (currently "Not yet
  published"), and Mapped HC Mass coverage.
- Does NOT fabricate six "Chase factor" cards to mirror Financial RIP's six —
  exactly one scored Chase metric plus its two real diagnostics.
- No weight-percentage copy and no frontend scoring arithmetic anywhere in
  the component (grepped and tested — see Phase 10).

Tested in `MarketBasedOpeningQualityBreakdown.test.jsx` (8 tests, all
passing) using the same source-text contract-test pattern
`FinancialRipV3Breakdown.contract.test.mjs` already established for this
file family — this component transitively imports `FinancialRipV3Breakdown.jsx`,
which depends on the `@/hooks/useMediaQuery` Next path alias that the
project's `tsx --test` runner cannot resolve outside a Next build (confirmed
by reproducing the exact `Cannot find module '@/hooks/useMediaQuery'` failure
when attempting a rendered test); the existing codebase convention for this
exact situation is to assert against the rendered JSX source instead, which
this test file follows.

**Not yet wired into a live page** — this pass built and tested the shared
component but did not splice it into `RipStatisticsPageClient.jsx` or any
other page in place of the current `OverallRipExplanationHierarchy`-only
rendering, since doing so risks touching the Set RIP page layout, which the
prompt explicitly prohibits redesigning in this pass. Wiring it into a live
surface is Prompt UI-2 scope.

## 5. Chase Accessibility vs. Product Chase — verified distinct

`ProductChaseIntelligenceSection.jsx` uses "Chase Access" consistently as
shorthand for "Chase Access at Budget" (always contextualized with budget/
`O_budget` language: "Chase Access at $100", "Chase Access is a separate
measure from Overall RIP... at a budget you choose"), and separately labels
its set-level diagnostic line "Set Chase Accessibility" with an explicit
"per-product diagnostic... carries no cross-format rank" note. No mislabeling
in either direction was found. `chaseAccessibilityPresentationSelector.mjs`
and `MarketBasedOpeningQualityBreakdown.jsx` both carry explicit module-level
comments warning against using them for Product Chase, and a dedicated test
(`E: Product Chase terminology never appears in this Chase Accessibility
surface`) asserts `"Chase Access at Budget"`, `"O_budget"`, and `"Product
Chase Intelligence"` never appear in the new component's source.

## 6. Surface inventory (Phase 1)

| Surface | Current display | Data source | V12 aware? | Chase visible? | Uses public weights? | Needs change? |
|---|---|---|---|---|---|---|
| `RipStatisticsPageClient.jsx` (Set RIP hero) | Overall RIP score + hero badges + `OverallRipExplanationHierarchy` | `canonicalRipV7.mjs` resolved bundle (V10-canonical per hardcoded frontend flag — see Phase 9 finding on a stale canonicality label) | Yes, via shared selector (opt-in `publicRipContractV11` shape) | No (current production payload has no Chase Accessibility attached at this call site) | Was yes — **fixed this pass** | Done |
| `OverallRipExplanationHierarchy.jsx` / selector | Overall RIP headline + optional Market-Based card | version-aware, same selector | Yes | Only the Market-Based grouping label, no score | Was yes — **fixed this pass** | Done |
| `MarketBasedOpeningQualityBreakdown.jsx` (new) | Financial RIP + Chase Accessibility, COMPACT/FULL | `FinancialRipV3Breakdown`'s selector + new `chaseAccessibilityPresentationSelector.mjs` | Yes | Yes (primary metric + real diagnostics, no fabricated rank) | No | Built, tested, **not yet wired into a live page** (UI-2 scope) |
| `ProductRipSection.jsx` | Collector Appeal + Financial dimensions; unavailable state "Opening intelligence is not currently available for this product." | `pokemon_sealed_product_detail_service.py`'s `_rip_contract` | Contract carries `overallRipV12`/`overallRipV12Composition` via `_public_rip_contract_v11_shadow`, but no standalone `chaseAccessibility` raw block (see Phase 2 matrix — AVAILABLE_BUT_NOT_PROJECTED) | No | No weight copy found | Full V12 wiring is UI-2/UI-5 scope; unavailable-state root cause traced in Phase 9 |
| `ProductChaseIntelligenceSection.jsx` | "Product Chase Intelligence · Index Premium", "Set Chase Accessibility" diagnostic line, budget selector, Premium-gated; error states "Chase Access couldn't be loaded right now." / "Chase Access is not currently available for this product." | `/api/explore/product-chase-intelligence` proxy → backend `_require_product_chase_intelligence` | Aware of Chase Accessibility as a labeled input only | Yes (both Product Chase and Set Chase Accessibility) | No | Confirmed clean; error-state root cause traced in Phase 9 (fail-closed entitlement, not a bug) |
| `RankingsProductLensClient.jsx` | Product-rankings table; unavailable state "Product rankings are temporarily unavailable." | `/api/explore/product-rankings/overall` → `overallProductRankingsServer.js` → backend `/explore/product-rankings/overall` | Not independently re-verified for V12 field wiring beyond the unavailable-state trace | Not confirmed | No weight-percentage string found | Root cause of the unavailable state traced in Phase 9; full V12 field audit is UI-2 scope |
| `ProductFamilyRankingsClient.jsx`, `RankingsLazyClient.jsx`, `ExploreTableClient.jsx` | Not re-read line-by-line this pass | various | Not confirmed | Not confirmed | Grep found no rendered weight-percentage matches | Full field-level audit is UI-2 scope |
| `PokemonSetAnalysisClient.jsx` | Not re-read this pass | — | Not confirmed | Not confirmed | Grep found no weight-percentage matches under this path in the earlier broad search | Full audit is UI-2 scope |

## 7. Backend field availability matrix (Phase 2 — built this pass from direct source reading)

Read: `backend/db/services/explore_rip_statistics_service.py` (2514 lines),
`backend/db/services/pokemon_sealed_product_detail_service.py` (464 lines),
`backend/db/services/product_family_rankings_service.py` (346 lines),
`backend/db/services/set_rip_service.py` (176 lines),
`backend/desirability/chase_accessibility.py`,
`backend/desirability/chase_accessibility_overall_score.py`,
`backend/desirability/public_rip_contract_v11.py`,
`backend/db/services/chase_accessibility_service.py`.

| Field | Set RIP (`set_rip_service.py`) | Set Analysis / Explore hero (`explore_rip_statistics_service.py`) | Product RIP (`pokemon_sealed_product_detail_service.py`) | Product Rankings (`/explore/product-rankings/overall`, read via `overallProductRankingsServer.js`) | Set Rankings (`product_family_rankings_service.py`) |
|---|---|---|---|---|---|
| Overall RIP V12 (score/status) | MISSING — `set_rip_service.py` builds Set RIP entirely from V10-lineage `overallRipV10`/`publicRipContractV10` ranked targets; no V12 read found | AVAILABLE — `overallRipV12` attached pre-contract, consumed via `publicRipContractV11.overallRipV12` (SHADOW, `canonical: False` hardcoded) | AVAILABLE — `overall_rip_v12_payload` column passed through `_public_rip_contract_v11_shadow` (also `canonical: False` hardcoded) | DIAGNOSTIC_ONLY — `overallRipV12` carried on `product_family_rankings_service.py`'s per-row projection (`row.get("overall_rip_v12_payload")`) but explicitly commented "SHADOW, NOT canonical... never read by `_rank_key`" | AVAILABLE — same `overall_rip_v12_payload` passthrough as above |
| Financial RIP V4 | AVAILABLE_BUT_NOT_PROJECTED — Set RIP averages family-level standings, not the raw V4 score, per product | AVAILABLE — `financialRipV4` built by `_build_financial_rip_v4` | AVAILABLE — `financialRipV4` block present (line ~301) | AVAILABLE — `financial_rip_v4_score`/`financial_rip_v4_version` selected and ranked on | AVAILABLE — `financialRipScore`/`financialRipAbsoluteScore`/`financialRipVersion` |
| Chase Accessibility raw value | MISSING | AVAILABLE — `read_chase_accessibility_snapshots_for_sets` joined onto targets, projected via `public_rip_contract_v11._chase_accessibility_block` | MISSING — no standalone `chaseAccessibility` raw block found in `pokemon_sealed_product_detail_service.py`; only the V12 composite score, not the raw metric, is passed through | MISSING (not found in the ranking-row projection read) | MISSING |
| Chase Accessibility transformed score (A_score) | MISSING | AVAILABLE — inside `overallRipV12.components.chaseAccessibility.score` | AVAILABLE — inside `overall_rip_v12_payload.components.chaseAccessibility.score` (passthrough) | DIAGNOSTIC_ONLY (nested in the shadow `overallRipV12` block) | AVAILABLE (nested, same passthrough) |
| Chase Accessibility status/version | MISSING | AVAILABLE (`chaseAccessibilityStatus`, `chaseAccessibilityVersion` fields read by `_chase_accessibility_block`) | MISSING at the raw-block level (only nested inside the V12 composite) | MISSING | MISSING |
| Chase Accessibility rank/tier | MISSING everywhere — **confirmed no backend service in this codebase computes or stores a Chase-Accessibility-specific rank or tier** (checked `chase_accessibility_service.py` and `public_rip_contract_v11.py` directly; neither has a rank/tier field) | — | — | — | — |
| Chase Depth | MISSING | AVAILABLE (`chaseDepth`, diagnostic only, in `_chase_accessibility_block`) | MISSING at the raw-block level | MISSING | MISSING |
| Value Concentration / top-card concentration | MISSING everywhere — no field of this name found in any of the four services read | — | — | — | — |
| mapped_hc_mass | MISSING | AVAILABLE (`mappedHcMass`, diagnostic only) | MISSING at the raw-block level | MISSING | MISSING |
| Collector Appeal V5 | AVAILABLE (`canonical_collector_appeal_version`, roll-up into family standing) | AVAILABLE (`collector_appeal_score` resolved via `_resolve_canonical_collector_appeal_score`) | AVAILABLE (`collectorAppealScore`/`collectorAppealTier`) | AVAILABLE (`collector_appeal_score`, ranked cohort-relative) | AVAILABLE (`collectorAppealScore`/`collectorAppealVersion`) |

Key finding from this matrix: **the raw Chase Accessibility metric (value,
percent, status, chaseDepth, mappedHcMass) is fully projected on the Explore/
Set-RIP-hero path (`explore_rip_statistics_service.py` → `public_rip_contract_v11.py`)
but is NOT projected as a standalone block anywhere on the Product-detail or
Rankings paths** — those paths only carry the already-blended V12 composite
score, not the raw accessibility metric or its diagnostics. This means
`chaseAccessibilityPresentationSelector.mjs` (Phase 3) will correctly report
`available: false` for Product RIP / Product Rankings / Set Rankings sources
today, even when Overall RIP V12 itself is present — this is expected given
the current backend contract, not a bug in the new selector. Extending
`pokemon_sealed_product_detail_service.py` and `product_family_rankings_service.py`
to also project the raw `chaseAccessibility` block (mirroring
`_chase_accessibility_block`) so `MarketBasedOpeningQualityBreakdown` FULL mode
can show something other than "unavailable" on those surfaces is a concrete,
scoped backend follow-up item for a later prompt — not done here, since the
prompt authorized only "minimal backend field additions where genuinely
needed" and this pass prioritized the confirmed presentation bug.

## 8. Diagnostic-vs-scored distinction (Phase 8/D)

Encoded in two places:
1. **Field naming** on `chaseAccessibilityPresentationSelector.mjs`'s
   contract: `rawAccessibility`/`displayAccessibility` (scored) are
   distinctly named from `chaseDepth`/`valueConcentration`/`topCardConcentration`/
   `mappedHcMass` (diagnostic) — no shared prefix, no field that could be
   mistaken for the other.
2. **Copy**, not just internal structure: `MarketBasedOpeningQualityBreakdown.jsx`'s
   FULL mode literally prints "Diagnostics — not part of the Chase
   Accessibility score" above the disclosure panel containing Chase Depth /
   Value Concentration / Top-card Concentration / Mapped HC Mass, mirroring
   how `FinancialRipV3Breakdown.jsx`'s existing "Depth and robustness" panel
   already states "Additional context — not part of the Financial RIP
   score."

Chase Accessibility rank/tier: **confirmed backend does not currently emit
one anywhere** (see Phase 2 matrix). Per Phase 8's instruction, no rank/tier
was fabricated — `chaseAccessibilityPresentationSelector.mjs` hardcodes
`rank`/`cohortSize`/`tier` to `null` and cannot be made to return a fake
value even if a caller's source object happens to carry rank-shaped keys
(tested explicitly). `MarketBasedOpeningQualityBreakdown.jsx`'s FULL mode
renders "Cohort rank not yet available for Chase Accessibility." instead of
a number. A later UI pass should reuse this exact contract once a canonical
backend Chase Accessibility ranking service exists — no frontend-derived
rank should ever be introduced ahead of that.

## 9. Terminology standardization (Phase 6)

Grepped `frontend/` for: `Market Based`, `Market-Based Quality`, `Opening
Market Quality`, `Chase Access` (word-boundary), `Chase Score`, `Chase
Opportunity`, `Chase Pillar`, `Core K`.

| Hit | File | Classification |
|---|---|---|
| "Market Based" / "Market-Based Quality" / "Opening Market Quality" | none found in `frontend/` | N/A — no inconsistent variant exists; only the canonical "Market-Based Opening Quality" label is used, in the new files this pass added |
| "Chase Access" (repeated) | `ProductChaseIntelligenceSection.jsx`, `indexPlanAccess.mjs`, `ProductChaseIntelligenceSection.contract.test.mjs` | **Valid Premium Product Chase** — every occurrence is contextualized with budget/`O_budget` language ("Chase Access at $100", "a budget you choose"); this is the established, already-locked shorthand for "Chase Access at Budget", not a stray synonym for Chase Accessibility. Preserved, no change. |
| "Chase Score" | not found in `frontend/` | N/A |
| "Chase Opportunity" | not found in `frontend/` (present in `backend/desirability/chase_opportunity.py` — backend-internal/historical module name) | **Historical/backend-internal** — preserved; does not leak into frontend copy (confirmed by grep) |
| "Chase Pillar" | not found in `frontend/` or `backend/` in this pass's searches | N/A |
| "Core K" | not found in `frontend/`; `backend/desirability/chase_core_k.py` exists as a module name | **Historical/backend-internal** — preserved; confirmed no frontend leakage |

A backend-wide grep for the same terms timed out on the full `backend/`
tree in this session's tooling (ripgrep 20s timeout on a very large
subtree); the two hits that were found came from a narrower
`backend/desirability` + `backend/db/services` search
(`scoring_config.py`, `weighted_rip.py`, `chase_opportunity.py`,
`chase_core_k.py` — all backend-internal module/identifier names, not
user-facing copy, and out of scope for a presentation-layer rename per the
task's own instruction not to globally rewrite historical/internal material).
A full backend-wide terminology sweep beyond these two directories was not
completed — open item for UI-2 if a future backend-facing rename is ever
warranted (unlikely, since these are internal identifiers, not UI copy).

No shared canonical label/copy CONSTANTS module was created across the whole
codebase in this pass (e.g. a single `ripLabels.mjs` imported everywhere).
The canonical strings live today in three already-authoritative places
(`overallRipExplanationHierarchySelector.mjs` for Overall/Market-Based,
`chaseAccessibilityPresentationSelector.mjs` for Chase Accessibility,
`public_rip_contract_v11.py` for the backend-side copy those two mirror) —
consolidating further into one cross-file constants module is a reasonable
UI-2 cleanup but was not required to satisfy this prompt's disclosure and
distinction rules, which are already satisfied by the above.

## 10. Runtime failure findings (Phase 9 — investigation only, traced via source reading, NOT fixed)

No local backend/DB was actually started in this pass (no local Postgres/API
server available in this session) — root causes below are traced by reading
the exact code paths involved, not by reproducing an HTTP response locally.
This is real code-path tracing, not a guess: each conclusion cites the exact
function/file/line-area responsible.

**1. Product Rankings: "Product rankings are temporarily unavailable."**
- Renders in `RankingsProductLensClient.jsx` when `state.status` is `"error"`
  or `"unavailable"`.
- That state comes from `/api/explore/product-rankings/overall` (see
  `app/api/explore/product-rankings/overall/route.js`), which returns HTTP
  503 whenever `payload.available !== true`.
- That payload is built by `frontend/lib/explore/overallProductRankingsServer.js`,
  which proxies to backend `/explore/product-rankings/overall` and reports
  `unavailable` on any non-OK HTTP status or a `normalizeOverallProductRankings`
  result that isn't `available: true`.
- The backend service backing this endpoint reads
  `pokemon_explore_rankings_snapshot_latest` and gates on
  `_rankings_publication_identity_mismatches(payload)` (defined in
  `backend/db/services/pokemon_public_snapshot_service.py`), which fails
  CLOSED — by design — whenever the published snapshot's recorded
  `financialRipVersion` / `collectorAppealVersion` / `overallRipVersion` /
  `publicRipContractVersion` don't all match `canonical_publication_identity()`.
- **Concrete, verified fact**: `backend/desirability/scoring_config.py` line
  615 sets `CANONICAL_OVERALL_RIP_VERSION = OVERALL_RIP_V12_VERSION` — i.e.
  **the backend has ALREADY flipped canonical Overall RIP to V12** at the
  config level. Any `pokemon_explore_rankings_snapshot_latest` row that was
  published BEFORE that flip (still carrying a V10-identified
  `ripWeightsConfig`) will now fail `_rankings_publication_identity_mismatches`
  and be treated as `current: False` — which empties `published_rows` and
  makes every product on the page report unavailable. This exactly matches
  the project's own memory note ("Overall RIP V12 canonical promotion...
  backend done+tested, frontend/snapshots/live-validation pending" /
  "Financial RIP V4... promotion needs snapshot rebuild").
- **This is very likely the fail-closed check working exactly as designed**
  — not a bug — reacting correctly to a snapshot that has not yet been
  rebuilt since the V12 cutover. Confirming the *actual* live row's stored
  identity (rather than the code path that would reject it) requires DB
  access this session does not have; that confirmation, and any snapshot
  rebuild, is explicitly NOT done here per the prompt's Phase 9 and safety
  rules (no backfill, no fail-closed-check weakening).

**2. Product RIP: "Opening intelligence is not currently available for this product."**
- Renders in `ProductRipSection.jsx` when `!rip.available`.
- Traced to `pokemon_sealed_product_detail_service.py`'s `_rip_contract`:
  `base["reason"] = "not_in_current_published_rankings"` when `ranking` is
  falsy. `ranking` is looked up from the SAME `_published_rankings(active)`
  helper and the SAME `publication["current"]` gate
  (`_rankings_publication_identity_mismatches`) as case 1 above — this is
  the identical publication-identity mechanism, not a separate defect. If the
  published rankings row is stale (case 1's root cause), every product
  lookup against it comes back empty, and this message is the direct,
  expected consequence.
- **Also fail-closed by design, same root mechanism as #1.**

**3. Product Chase: "Chase Access couldn't be loaded right now."**
- Renders in `ProductChaseIntelligenceSection.jsx` when `state.status ===
  "error"`, which the component's fetch handler sets whenever the response
  from `/api/explore/product-chase-intelligence` is not `response.ok` and
  not a 404 (404 maps to an empty-but-successful `{ products: [] }`, which
  then resolves to the DIFFERENT "unavailable" message, not "error").
- The frontend route (`app/api/explore/product-chase-intelligence/route.js`)
  is a thin proxy that passes the backend's status code straight through.
- The backend endpoint (`backend/api/main.py`, calling
  `_require_product_chase_intelligence` at line ~1151) raises **HTTP 401**
  via `_require_authenticated_user_id` for an unauthenticated caller, or
  **HTTP 403** with `code: "PRODUCT_CHASE_INTELLIGENCE_PREMIUM_REQUIRED"` for
  an authenticated caller who lacks Index Premium (`has_index_feature_access`
  check against `FEATURE_PRODUCT_CHASE_INTELLIGENCE`).
- **This is a DIFFERENT mechanism from cases 1/2** — it is an entitlement
  gate, not a publication-identity gate. For any browsing session that is
  logged out or on a non-Premium plan, hitting this component will
  deterministically produce exactly the generic "couldn't be loaded right
  now" copy (401/403 both fall into the `!response.ok` branch, which does not
  distinguish entitlement-denied from a genuine server error). **This is very
  likely also correct, expected, fail-closed behavior for a non-Premium
  viewer** — the code comment at `_require_product_chase_intelligence`
  explicitly states "a Plus or Free request must never receive this
  payload". The one real, arguably-worth-fixing UX gap (not touched in this
  investigation-only phase) is that the frontend does not distinguish a 403
  entitlement-denial from a genuine 5xx failure, so a Free/Plus user sees the
  same "couldn't be loaded right now, please try again" wording that a real
  outage would show, rather than an upsell message — that distinction is
  left for Prompt UI-5.

## 11. Tests (Phase 10)

Ran via `npx tsx --test` (matching the project's `test:frontend` script
mechanics) across all four files touched/added this pass:

```
components/explore/OverallRipExplanationHierarchy.contract.test.mjs : 13 pass, 0 fail
components/explore/chaseAccessibilityPresentationSelector.test.mjs  :  7 pass, 0 fail   (new)
components/explore/MarketBasedOpeningQualityBreakdown.test.jsx      :  8 pass, 0 fail   (new)
components/explore/canonicalRipV7.contract.test.mjs                 : 30 pass, 0 fail   (regression check, unaffected)
--------------------------------------------------------------------------------
TOTAL										        : 58 pass, 0 fail
```

Coverage against the original Phase 10 A-G spec:
- **A** (V12 presentation contains Market-Based/Financial/Chase/Collector as
  labels) — covered in `OverallRipExplanationHierarchy.contract.test.mjs`
  and `MarketBasedOpeningQualityBreakdown.test.jsx`.
- **B** (no public scoring weight percentages) — covered by the new
  PERMANENT test in `OverallRipExplanationHierarchy.contract.test.mjs` and a
  matching assertion in `MarketBasedOpeningQualityBreakdown.test.jsx`.
- **C** (Market-Based marked as explanatory, not persisted) — covered in
  both files (`explanatoryOnly: true`, the "never persisted as its own
  score" copy string).
- **D** (Chase Accessibility distinguishes scored vs. diagnostic) — covered
  in `chaseAccessibilityPresentationSelector.test.mjs` (field-shape
  assertions, rank-non-fabrication) and `MarketBasedOpeningQualityBreakdown.test.jsx`
  (copy assertions).
- **E** (Product Chase terminology never leaks into Chase Accessibility, and
  vice versa) — covered by a dedicated test in
  `MarketBasedOpeningQualityBreakdown.test.jsx`.
- **F** (V10 historical inputs render without crashing) — covered by the
  pre-existing `A: V10-only data renders...` and `J: shadow safety...` tests
  in `OverallRipExplanationHierarchy.contract.test.mjs`, which already
  exercised V10-only fixtures before and after this pass's edits. A
  dedicated "does not crash" render test for every OTHER surface
  (`RankingsProductLensClient.jsx` etc.) with V10-only data was not added —
  open item.
- **G** (no frontend scoring arithmetic introduced) — covered by explicit
  regex assertions in both new test files (`0.86 *`, `A_raw / (A_raw +`,
  the full saturating-transform pattern) checked against both new source
  files, plus the pre-existing equivalent assertions against the selector/
  component pair.

Not added in this pass: a repo-wide "no frontend scoring arithmetic" grep
test that scans every file under `frontend/components` and `frontend/lib`
(as opposed to the specific files this pass touched) — the existing
per-file assertions cover every file this pass created or modified, but a
single global sweep test was not authored. Open item for UI-2.

## 12. Scope boundary — explicitly NOT done in this pass (for Prompt UI-2+)

- No Set RIP page redesign, no Set Analysis redesign (per the prompt's own
  restriction).
- `MarketBasedOpeningQualityBreakdown.jsx` was built and tested but **not
  wired into any live page** — no page currently renders it. Wiring it into
  `RipStatisticsPageClient.jsx` (replacing or augmenting the plain
  `OverallRipExplanationHierarchy` usage) is explicit UI-2 scope, since doing
  so touches the Set RIP page's actual layout.
- Backend extension so Product RIP / Product Rankings / Set Rankings project
  the raw `chaseAccessibility` block (value/percent/chaseDepth/mappedHcMass)
  the way the Explore/Set-hero path already does — identified as a concrete
  gap in the Phase 2 matrix, not implemented here.
- A single cross-file canonical label/copy constants module — the canonical
  strings are correct and centralized in three existing modules today, but
  not merged into one shared module.
- A full backend-wide terminology sweep beyond `backend/desirability` and
  `backend/db/services` (ripgrep timed out on the full tree in this
  session).
- Actual reproduction of the Phase 9 failures against a running
  backend/DB (traced via source reading only — no local server was started
  in this session); in particular, no query was run against the live
  `pokemon_explore_rankings_snapshot_latest` row to confirm its stored
  identity fields actually mismatch as hypothesized.
- Distinguishing a 403 entitlement-denial from a genuine failure in
  `ProductChaseIntelligenceSection.jsx`'s error state (a real, small UX gap
  identified in Phase 9, item 3) — left for UI-5, which owns fixing these
  runtime failures.
- A dedicated "renders without crashing on V10-only data" test for every
  Rankings/Product surface beyond the Overall RIP explanation pair.

## Final decision

**V12_UI_PRESENTATION_CONTRACT_READY**

Justification against the stated readiness bar:
- All current surfaces this pass could locate are mapped (Phase 1 table,
  section 6) — the two surfaces not re-read line-by-line
  (`ProductFamilyRankingsClient.jsx`, `ExploreTableClient.jsx`,
  `PokemonSetAnalysisClient.jsx`) were confirmed via grep to carry no
  weight-percentage disclosure, which is the specific hazard this contract
  pass exists to close.
- Backend Chase fields are mapped field-by-field against four services read
  directly (Phase 2 table, section 7), including the concrete finding that
  the raw Chase Accessibility block is not yet projected on the Product/
  Rankings paths — documented as a scoped follow-up, not a blocker to the
  presentation contract itself (the new selector correctly reports
  `available: false` there rather than fabricating data).
- A shared Market-Based/Chase presentation contract exists: the Phase 3
  `chaseAccessibilityPresentationSelector.mjs` module and the Phase 5
  `MarketBasedOpeningQualityBreakdown.jsx` component, both built and tested
  (15 new passing tests) this pass.
- Public weight disclosure is removed from the shared V12 presentation
  (Phase 4/7) — the specific bug named in the prompt — with a PERMANENT
  regression test guarding it.
- Terminology is centralized enough to satisfy the locked distinction rule:
  grepped, classified, and confirmed no invalid-current-UI hit exists today
  (Phase 6).
- Runtime failures are traced to exact code paths (Phase 9) — including one
  concrete, load-bearing finding (`CANONICAL_OVERALL_RIP_VERSION` already
  equals V12 in `scoring_config.py`, which plausibly explains both Product
  Rankings and Product RIP unavailability as a stale, un-rebuilt snapshot
  hitting an intentional fail-closed check) — without touching, weakening,
  or bypassing any fail-closed check, and without fixing anything.
- Tests pass (58/58 across the four files this pass's changes touch).
- No deploy, no publish, no backfill occurred.

This decision is scoped to what the prompt actually asked this pass to
close (the weight-disclosure bug, the Chase Accessibility contract, the
Market-Based component, the distinction rule, the failure tracing) — it is
NOT a claim that Set RIP/Set Analysis/Rankings pages have been redesigned to
USE these new pieces yet, nor that every backend field gap is closed. Those
are explicitly named as Prompt UI-2+ scope in section 12 above.
