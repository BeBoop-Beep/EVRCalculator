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

---

## Prompt UI-2 (2026-09-05) — Set RIP + Set Analysis wired to the Market-Based contract

Status date: 2026-09-05. Branch: `fix/backend-memory-restart-p0-20260904`.
Frontend code only. No backend changes, no deploy, no publication. This pass
wires the UI-1 presentation contract (`chaseAccessibilityPresentationSelector.mjs`,
`MarketBasedOpeningQualityBreakdown.jsx`, `overallRipExplanationHierarchySelector.mjs`)
into the two real user-facing pages named in scope: Set RIP
(`frontend/components/explore/RipDecisionPage.jsx`) and Set Analysis
(`frontend/components/pokemon/set-page/Analysis/PokemonSetAnalysisClient.jsx`).
Product RIP and Rankings were NOT touched.

### Set RIP final hierarchy

Opening Snapshot (`data-rip-section="opening-snapshot"`) now renders:

```
Overall RIP                         (prominent, own row, unchanged score/rank/tier)
Market-Based Opening Quality group  (role="group", data-market-based-summary-group)
  - Financial RIP  (existing ScoreSurface: score/rank/tier, unchanged math)
  - Chase Accessibility  (new ChaseAccessibilitySnapshotCard: primary metric
    only, no rank/tier, no diagnostics — those live in the deep dive)
Collector Appeal                    (its own ScoreSurface, sibling of the group)
```

`metrics.marketBased` does not exist as a scored card — the group is a pure
visual container (`styles.marketBasedGroup` / `styles.marketBasedRow` in
`RipDecisionPage.module.css`). Both Financial RIP's ScoreSurface and the new
Chase Accessibility card share ONE CTA, "View Market-Based breakdown", which
scrolls to a single combined anchor `#set-detail-market-based` (the old
Financial-only `#set-detail-financial-rip` anchor and its two-destination CTA
pattern are gone).

### Set RIP deep dive ("For those who want to go deeper")

The former `DeepDiveRow` titled "Financial RIP Breakdown — why Financial RIP
is X" is now titled "Market-Based Opening Quality — why Financial RIP is X"
with the locked intro sentence ("Market-Based Opening Quality combines the
modeled financial profile of opening this set with how reachable its most
important collectible value is."), and its body renders
`<MarketBasedOpeningQualityBreakdown canonical={analyticalCanonical}
sources={[analyticalCanonical, canonical]} depth="full" />` instead of a bare
`<FinancialRipV3Breakdown>`. That shared container itself still reuses
`<FinancialRipV3Breakdown>` verbatim (six dimensions, unmodified) side by side
with a Chase Accessibility FULL panel (primary metric, honest "Cohort rank
not yet available" line, and a collapsed "Chase depth & concentration"
disclosure explicitly labeled "Diagnostics — not part of the Chase
Accessibility score" for Chase Depth / Mapped HC Mass). Value Concentration
and Top-card Concentration are omitted entirely (not backend-projected on any
surface today, confirmed in UI-1's field matrix) rather than shown as fake
"unavailable" filler cards.

Top Chase / "Your Biggest Chase" (`data-rip-section="chase-reality"`,
`function ChaseReality`) was not touched — it still reads only
`decision.topChase` and never imports `chaseAccessibilityPresentationSelector.mjs`.
Collector Appeal's deep dive (`#deep-dive-collector-appeal`) was not touched.

### Set Analysis final hierarchy

Nav (`SECTIONS`): `Overview, Simulation, Market-Based, Collector Appeal,
Market Context` — the old `financial-rip` tab entry ("Financial RIP") was
replaced with `market-based` ("Market-Based"); no separate Chase tab was
added. Overview mirrors Set RIP exactly: a single centered Overall RIP
`ScoreCard`, then a two-column row of (a) a `role="group"
aria-label="Market-Based Opening Quality"` block containing the Financial RIP
`ScoreCard` plus an inline Chase Accessibility metric card (primary value
only, sourced from `selectChaseAccessibilityPresentation(critical)`), and (b)
the Collector Appeal `ScoreCard` as a sibling. The Overview description
string was updated from "...Financial RIP, and Collector Appeal..." to
"...Market-Based Opening Quality, and Collector Appeal...". The
`market-based` section body renders the SAME
`<MarketBasedOpeningQualityBreakdown canonical={canonical} sources={[critical]}
depth="full" />` component Set RIP uses — one implementation, not a
second independently authored Chase card set. Collector Appeal's own tab
(`activeSection==="collector-appeal"`) was left unchanged.

### V10 historical safety

No new code path forces Chase Accessibility onto a V10 fixture.
`overallRipExplanationHierarchySelector.mjs`'s existing version branch
(`buildV10Explanation`) is untouched: a V10-only canonical still yields
`marketBased: null` and `weights.chaseAccessibility: null`, and its headline
still reads "Overall RIP combines Financial RIP with Collector Appeal." The
new `ripDecisionModel.mjs` `chaseAccessibility`/`marketBased` fields are
resolved independently via `selectChaseAccessibilityPresentation`, which is
itself version-agnostic and honestly reports `available: false` whenever no
`publicRipContractV11.chaseAccessibility` block is present — it never borrows
a V10 canonical's Financial/Collector values to fabricate a Chase number.
Verified by a dedicated new test (test P, below).

### Backend projection status (confirmed unchanged from UI-1)

Set RIP (`set_rip_service.py`) and Set Analysis (same canonical payload) do
NOT currently project the raw `publicRipContractV11.chaseAccessibility` block
— only the Explore/Set-RIP-hero path does. This means, on the current live
backend, Chase Accessibility renders its truthful "not currently available"
state on both surfaces built in this pass, exactly as intended (Phase 4/8
requirement: never fabricate). Once a future backend pass projects that block
onto `set_rip_service.py`'s canonical payload, these same components will
start showing the real metric with no further frontend change required.

### Responsive / accessibility

`RipDecisionPage.module.css` adds `.overallScoreRow`, `.marketBasedRow`
(2-col grid, collapses to 1-col under 640px), `.marketBasedGroup`,
`.marketBasedGroupLabel`, `.marketBasedGroupNote`, `.marketBasedChildren`,
`.chaseAccessSummary`, `.chaseAccessMetricRow`, `.chaseAccessMetricValue`,
`.chaseAccessCta`, `.chaseAccessDiagnosticNote`. The Market-Based group uses
`role="group"` + `aria-label` (Set RIP and Set Analysis both); the Chase
Accessibility metric renders as a plain numeric value in a card, never inside
a `role="progressbar"` rail (unlike the 0–100 Overall/Financial/Collector
score rails), so a small percentage like 0.21% cannot misread as "0.21%
complete". Existing keyboard/focus/reduced-motion handling (`scrollToSection`,
`focus({preventScroll:true})`, `prefers-reduced-motion` guards) is unchanged
and reused for the new CTA.

### Tests

New file: `frontend/components/explore/ripV12MarketBasedUiWiring.contract.test.mjs`
— 16 tests (A-P per the task's Phase 16 list), all passing. Two pre-existing
contract test files were updated in two places each to match the intentional
structural change (the deep dive now imports
`<MarketBasedOpeningQualityBreakdown>` rather than a bare
`<FinancialRipV3Breakdown>` — the underlying component still reuses
`FinancialRipV3Breakdown` verbatim, one layer down):
`RipDecisionPage.contract.test.mjs` (2 assertions updated) and
`PokemonSetAnalysis.contract.test.mjs` (1 assertion updated).

Full regression run (`npx tsx --test` across
`RipDecisionPage.contract.test.mjs`, `RipDecisionPage.productComparison.contract.test.mjs`,
`ripDecisionModel.test.mjs`, `ripDecisionContract.test.mjs`,
`OverallRipExplanationHierarchy.contract.test.mjs`,
`MarketBasedOpeningQualityBreakdown.test.jsx`,
`chaseAccessibilityPresentationSelector.test.mjs`,
`ripV12MarketBasedUiWiring.contract.test.mjs`,
`PokemonSetAnalysis.contract.test.mjs`): **116 pass / 8 fail out of 124**. All
8 failures were independently confirmed, via `git show HEAD:...` and re-runs
before any edit in this pass, to be pre-existing baseline failures unrelated
to this change (stale assertions from an older page-structure refactor that
predates this pass, e.g. asserting `data-rip-section="opening-snapshot"` does
NOT exist when the live page has rendered that section for some time). None
of the 8 reference Market-Based, Chase Accessibility, or any string this pass
touched.

### Visual smoke

Live-data visual smoke was not performed in a browser: this pass, like UI-1,
follows this codebase's own established pattern for this exact component
family (see the header comment in `MarketBasedOpeningQualityBreakdown.test.jsx`)
of verifying via rendered-JSX-source contract tests rather than importing the
component tree outside a full Next build, because `FinancialRipV3Breakdown.jsx`
transitively depends on the `@/hooks/useMediaQuery` Next path alias. A
targeted `next lint` pass on the three edited/added files
(`RipDecisionPage.jsx`, `ripDecisionModel.mjs`, `PokemonSetAnalysisClient.jsx`)
reported no warnings or errors. A full `next build` was also run as a compile
smoke check (see the session's build output for the exact result at build
time). Separately, this is consistent with the LIVE PUBLICATION FACT
constraint for this task: production's Explore rankings snapshot is a stale
V10/V10 build, so any attempt at a genuinely live-data render of these pages
would exercise the intentional fail-closed Product Rankings/Product RIP path
rather than this pass's Set RIP/Set Analysis surfaces, which read the
separate, current Set RIP/read-model data path.

### What remains open for UI-3 / UI-4 (Product RIP / Rankings)

- Product RIP (`ProductRipSection.jsx`) and Product Rankings
  (`RankingsProductLensClient.jsx`) still show only the blended V12 composite
  score with no raw Chase Accessibility contract projected — this pass did
  not touch either surface (explicitly out of scope).
  `pokemon_sealed_product_detail_service.py` and the Set/Product Rankings
  backends still need a Chase Accessibility raw-block projection before those
  surfaces could ever show a real (non-"unavailable") Chase Accessibility
  metric.
  - Production's Explore rankings snapshot is still on stale V10/V10
  metadata (market date 2026-08-26, built 2026-08-27) against V12/V11
  canonical application code — Product Rankings/Product RIP fail-closed
  behavior there is expected and unrelated to anything in this pass; a
  coordinated V12 snapshot publication is a separate, future action.
- No Chase Accessibility rank/cohortSize/tier/valueConcentration/
  topCardConcentration backend contract exists yet anywhere in the codebase;
  UI-3/UI-4 inherit the same constraint this pass worked within.

## UI-3 — Product RIP Market-Based UI (2026-09-05)

This pass closes the Chase Accessibility gap UI-2 explicitly flagged above:
Product RIP now projects and renders a real, exact-run-authenticated Chase
Accessibility contract, matching the same information architecture Set RIP
already uses.

### Locked Product RIP hierarchy

```
Overall RIP
  Market-Based Opening Quality
    Financial RIP       ← product-specific (this exact product's price/composition/outcomes)
    Chase Accessibility ← inherited from parent SET, identical across all products of that set/run
  Collector Appeal      ← inherited from parent SET, identical across all products of that set/run
```

Product Chase Intelligence (`O_budget`, budget-specific, Premium) stays a
SEPARATE section below Product RIP — untouched, unmerged.

### Backend Chase projection (Phase 1-5)

`backend/db/services/pokemon_sealed_product_detail_service.py` gained
`_chase_accessibility_contract(set_id, ranking, client)`, wired into
`_rip_contract` -> `_public_rip_contract_v11_shadow` (now attached at
`rip.publicRipContractV11.chaseAccessibility`). It reuses, unchanged:

- `chase_accessibility_service.read_chase_accessibility_snapshot` — the SAME
  exact-set read/projection the set page already uses (ONE additional query
  per product-detail request, table
  `pokemon_set_chase_accessibility_snapshot_latest`, keyed by `set_id`).
- `public_rip_contract_v11._chase_accessibility_block` — the SAME
  presentation-safe shape (`value`/`percent`/`status`/`statusReason`/
  `version`/`chaseDepth`/`mappedHcMass`) Set RIP already publishes, plus one
  addition (`calculationRunId`) for authority auditing.

**Authority rule** (mirrors `sealed_product_rip_finalization_service.
_overall_rip_v12_for`): the snapshot's own `calculation_run_id` must equal
this product's exact ranking run id. A mismatch is refused — never accepted
as "the latest available" — and reported as `unavailable_authority_mismatch`,
or the distinct `unavailable_v12_authority_mismatch` when the product's own
canonical Overall RIP V12 result claims a ready Chase Accessibility component
(a genuine contract-integrity error, not merely a missing optional
diagnostic). No ranking run at all reports `unavailable_no_ranking_run`
(truthfully unavailable, not an integrity error — there is no V12 claim to be
inconsistent with).

Chase Accessibility is projected **independently** of whether the ranking row
happens to carry an `overallRipV12` blend payload, since the known/expected
production condition today is exactly a stale V10-only publication with no
`overallRipV12` field — Product RIP's Chase explanatory child still needs to
surface truthfully (available or a specific unavailable reason) rather than
disappearing.

**Read-count impact**: bounded at +1 exact-set read per product-detail
request (never a cohort/18-22-set load, never per-comparison-row). A
zero-additional-read passthrough was not possible: `overallRipV12.
components.chaseAccessibility` only carries `{raw, score, weight,
contribution, transformK}` (the Overall-scoring `A_score`, not the public
raw/percent/status/chaseDepth/mappedHcMass fields), so a genuine
presentation-safe projection needs one exact-set snapshot read.

### Phase 12 canonical correction

`CANONICAL_OVERALL_RIP_VERSION` resolves to Overall RIP V12 as of the
2026-09-03 cutover (`scoring_config.py`, promoted in commit `db387f25`). The
stale "SHADOW-only... NOT canonical" docstring/comments and the
`"canonical": False` flag inside
`pokemon_sealed_product_detail_service._public_rip_contract_v11_shadow`
(and the matching test assertion) were factually wrong post-cutover and have
been corrected to `"canonical": True`, matching
`public_rip_contract_v11.py`'s own `_overall_rip_v12_block`. **Follow-up flagged, not fixed here**: `frontend/components/explore/
overallRipExplanationHierarchySelector.mjs` still carries matching stale
"SHADOW, never canonical" / "V10 remains canonical" comments and a
`canonical: false` flag inside `buildV12Explanation`, and its
`selectOverallRipExplanationHierarchy` docstring still describes the
`publicRipContractV11` opt-in precedence as if V10 were still canonical
everywhere. That file is shared with Set RIP/Explore and is NOT modified in
this pass's git status but was also not touched here, to avoid a functional
change to shared selection logic outside this task's Product RIP scope —
recommended as an explicit, narrowly-scoped follow-up (comment/flag-only, no
behavior change) before or alongside UI-4.

### Frontend (Phase 6-9, 16)

`ProductRipSection.jsx` now renders: Overall RIP (hero, unchanged score
source) → `OverallRipExplanationHierarchy` (unchanged) → a new "Market-Based
Opening Quality" grouping (Financial RIP card labeled "This product" +
`ChaseAccessibilityCard` labeled "Parent set", reusing
`chaseAccessibilityPresentationSelector.selectChaseAccessibilityPresentation`
and the `MARKET_BASED_LABEL`/`MARKET_BASED_PUBLIC_QUESTION`/
`MARKET_BASED_EXPLANATORY_NOTE` constants verbatim from
`overallRipExplanationHierarchySelector.mjs`) → Collector Appeal (labeled
"Parent set"). Chase Accessibility's diagnostics (Chase Depth, Mapped HC Mass)
are rendered inline as "Context — not an additional scoring input", never as
scored inputs.

**Design decision — not a literal `MarketBasedOpeningQualityBreakdown` import**:
that shared component's FULL/COMPACT Financial child renders via
`resolveCanonicalFinancialRip(canonical)`, which expects a
`publicRipContractV10.financialRip`-shaped six-dimension canonical object —
a shape Product RIP's `rip` contract does not produce (Product RIP has never
carried the full Financial RIP V3 six-dimension breakdown; only the single
leader-normalized score). Forcing that component in would have shown
"Financial RIP not currently available" beside an accurate score rendered
elsewhere on the same page — confusing, not decision-safe. Instead, this pass
reuses the actual SHARED SUBSTANCE requested — the Chase Accessibility
selector, the locked Market-Based copy constants, and the locked
grouping/labeling/inheritance rules — while keeping the existing, working
Financial RIP score card. No second Chase Accessibility contract or copy was
authored.

Comparison cards (`ProductComparisonSection.jsx`) were left unchanged (Phase
14): Chase Accessibility is identical for every same-set product by
construction, so repeating it on every same-set comparison row would be
noise, not information; same-family cross-set comparison Chase display is
explicitly deferred to Rankings/UI-4.

### Entitlement (Phase 15)

Verified the Product RIP Chase Accessibility payload contains ONLY
`value`/`percent`/`status`/`statusReason`/`version`/`chaseDepth`/
`mappedHcMass`/`publicQuestion`/`technicalTooltip`/`calculationRunId` — no
`oBudget`, `ece`, `eceVersion`, `quantity`, `effectivePacks`, `oBudgetRank`,
or any other Premium Product Chase Intelligence field. Product RIP remains
gated at Index Plus exactly as before; no new entitlement surface was
introduced.

### Tests (Phase 17)

Backend: 8 new tests (A-H) in
`backend/tests/unit/db/services/test_pokemon_sealed_product_detail_service.py`
covering exact-run projection, wrong-run rejection, wrong-set rejection,
truthful unavailability, a latest-by-set exploit attempt, absence of V12
arithmetic in the detail service, absence of Premium leakage, and a bounded
(exactly one) Chase snapshot read. Full file: 27/27 passed. Related backend
regression (`test_public_rip_contract_v11.py`,
`test_chase_accessibility_service.py`,
`test_sealed_product_rip_finalization_service_v10.py`,
`test_sealed_product_rip_finalization_service_v12.py`): 76/76 passed.

Frontend: new
`frontend/components/pokemon/sealed-product-detail/productRipMarketBasedChase.contract.test.mjs`
(10/10 passed) covering I-Q. Regression across
`sealed-product-detail/*.test.{mjs,jsx}`,
`MarketBasedOpeningQualityBreakdown.test.jsx`, and
`ripV12MarketBasedUiWiring.contract.test.mjs`: 58/58 passed (unchanged files
from this pass's scope). `RipDecisionPage.contract.test.mjs` and
`PokemonSetAnalysis.contract.test.mjs` show 7 and 1 pre-existing failures
respectively, both against concurrently in-progress, uncommitted edits to
`RipDecisionPage.jsx`/`ripDecisionModel.mjs`/`PokemonSetAnalysisClient.jsx`
from another session (visible in this session's starting `git status`) —
verified unrelated to Chase Accessibility/Market-Based content and NOT
touched by this pass.

### UI-2 cleanup performed here

`MarketBasedOpeningQualityBreakdown.jsx`'s FULL-mode "Cohort rank not yet
available for Chase Accessibility." line was removed (a non-projected
optional diagnostic is now OMITTED, not shown as an unavailable message);
`MarketBasedOpeningQualityBreakdown.test.jsx` and
`ripV12MarketBasedUiWiring.contract.test.mjs` (both from the UI-2 pass) were
updated to assert the line's absence instead of its presence.

### Stale publication behavior (unchanged, verified)

Production's Explore/Product rankings publication remains stale V10/V10
metadata against V12/V11 canonical code — Product RIP still legitimately
renders "Opening intelligence is not currently available for this product."
via the pre-existing `rip.available` gate whenever there is no current
published ranking row, exactly as before this pass. This pass never weakens
that gate; Chase Accessibility's own new authority checks are strictly
additive on top of it (Phase 4/13/19).

### Remaining for UI-4 (Rankings)

- Product Rankings (`RankingsProductLensClient.jsx` or equivalent) still has
  no raw Chase Accessibility contract projected — same backend primitives
  (`_chase_accessibility_contract`-equivalent, `read_chase_accessibility_
  snapshot`) can be reused, but the Rankings surface reads a different
  service entry point that was out of scope here.
  - No Chase Accessibility rank/cohortSize/tier contract exists yet anywhere
  in the codebase — UI-4 inherits this same constraint.
- The `overallRipExplanationHierarchySelector.mjs` stale-canonical-comment
  follow-up flagged above should be resolved (comment/flag-only) before or
  during UI-4 so the Rankings surface's own documentation doesn't
  misdescribe V10 as canonical.
- `RipDecisionPage.jsx`/`ripDecisionModel.mjs`/`PokemonSetAnalysisClient.jsx`
  have pre-existing, uncommitted, in-progress changes from a concurrent
  session with 7-8 failing contract-test assertions (observed, not caused,
  by this pass) — worth confirming resolved before UI-4 builds on top of
  those files.

## UI-4 — Rankings Market-Based standardization (2026-09-05)

Continuity: Phase 0 for UI-4 confirmed UI-1/UI-2/UI-3 artifacts present in the
current working tree as uncommitted work (this program commits nothing by
design). The files flagged above as "genuinely concurrent" —
`public_rip_publication_contract.py`, `rankings_publication_lifecycle.py`,
`public_rip_contract_v11.py`, `pokemon_explore_rankings_publisher.py`,
`pokemon_snapshot_builders.py` — were left untouched; no collision occurred
because this pass did not need to edit them.

### Ranking-surface inventory (Phase 1)

| Surface | Row unit | Backend service | Frontend component |
| --- | --- | --- | --- |
| Product Family Rankings ("Best X to Rip") | sealed product | `product_family_rankings_service.build_product_family_rankings` | `ProductFamilyRankingsClient.jsx` (`ProductRankingsTable`) |
| Overall/Budget Product Rankings | sealed product | same service, budget-scoped read path | `ProductFamilyRankingsClient.jsx` (`OverallProductRankings`) |
| Set RIP / "Best Sets to Rip" | set | `set_rip_service.build_set_rip` | `ExploreTableClient.jsx` |
| Product-lens Rankings reader | sealed product | `rankingsClientProjection.mjs` (client-side projection over the same backend payload) | `RankingsProductLensClient.jsx`, `RankingsLazyClient.jsx` |

Overall RIP authority: `CANONICAL_OVERALL_RIP_VERSION` (currently V12).
Financial: `financial_rip_v4_score`/`CANONICAL_FINANCIAL_RIP_VERSION`.
Collector: canonical Collector Appeal version selector. Chase Accessibility
previously had **no** rank/cohort authority anywhere in the ranking read
path — this is exactly what UI-4 adds.

### Chase Accessibility set cohort + authority (Phases 2-4)

New module `backend/db/services/chase_accessibility_set_ranking.py`. Batch-
loads `pokemon_set_chase_accessibility_snapshot_latest` for the ranking
cohort via the existing paginated `read_chase_accessibility_snapshots_for_sets`,
then computes ONE rank pass over UNIQUE `set_id` values. Eligibility mirrors
`chase_accessibility_service.publication_integrity_failures`: `status ==
"ready"`, canonical `CHASE_ACCESSIBILITY_VERSION`, `mapped_hc_mass >=
MIN_MAPPED_HC_MASS (0.99)`, non-null value, and (when supplied) exact
`calculation_run_id` match against the same set->run authority the rest of
the row was validated against. A set failing any check is simply absent from
the ranked cohort, never coerced to a rank.

**Tie/rank semantics**: matches this codebase's existing convention
(`set_rip_service`, `product_family_rankings_service._rank_key`) — sort by
`(-accessibility, set_id)`, dense sequential rank via `enumerate(..., 1)`; no
shared/competition ranking, `set_id` ascending breaks exact ties
deterministically.

### Product/Set projection (Phases 5-6)

`product_family_rankings_service.build_product_family_rankings` now does one
`load_chase_accessibility_set_authority` call per build (keyed by the same
`run_id_by_set_id` authority every other canonical field validates against),
and every product row carries `chaseAccessibility = {value, percent, status,
version, chaseDepth, mappedHcMass, setRank, setCohortSize}`. Products sharing
a `set_id` get the byte-identical block (test-proven:
`test_chase_accessibility_set_ranking.py`, `test_chase_accessibility_ranking_
snapshot_fixture.py`). `set_rip_service.build_set_rip` carries the same block
on each set row by lifting it from whichever product of that set it sees
first — no second, independent ranking computation.

### Desktop Product Rankings (Phase 7, 11-12)

`ProductFamilyRankingsClient.jsx` (`ProductRankingsTable`): the desktop table
header gained a two-row `<thead>` — row 1 carries `rowSpan={2}` cells for
Rank/Product/Overall RIP/Tier/Collector Appeal/Market Price/Expected
Value/Chance to Recover/Format Strength plus one `colSpan={2}` "Market-Based
Opening Quality" grouping header (locked copy: "Combines Financial RIP with
Chase Accessibility.", no score/rank/tier of its own); row 2 carries
Financial RIP and Chase Accessibility as the two columns under that group.
The Chase Accessibility cell (`ChaseAccessibilityCell`) shows the raw percent
plus, where it fits, "Set #X of Y" — **never** "Product #X of Y" — sourced
verbatim from `product.chaseAccessibility.setRank`/`setCohortSize`. Locked
tooltip copy applied verbatim for the grouping header and the Chase
Accessibility header, including the parent-set inheritance sentence.

### Mobile Product Rankings (Phase 8)

The existing compact mobile row gained one additional disclosure line (gated
behind the same `canViewProductRipIntelligence` entitlement as the rest of
the row) reading "Market-Based: {Financial} Financial · {Chase%} Chase (Set
#X of Y) · {Collector} Collector Appeal" — reusing the same
`chaseAccessibilityDisplay` formatter the desktop cell uses, so the two
surfaces cannot state different numbers. No horizontal overflow was
introduced (no new table column on mobile; the addition is a text line inside
the existing card).

### Sort/lens behavior (Phases 9-10)

`FAMILY_SORT_OPTIONS`/`OVERALL_SORT_OPTIONS` gained `chaseAccessibilityValue`.
`filterAndSortProducts`'s comparator reads `product.chaseAccessibility.value`
(via a new `sortFieldValue` helper) for that key — no frontend ranking
arithmetic, the raw value is read verbatim from the backend-authoritative
block. Because every product in a set shares the identical value, sorting by
Chase Accessibility groups same-set products together; ties resolve through
the **existing** stable secondary key already used by every other sort
column in this file — `Number(a.budgetRank || a.familyRank)` — i.e. the
canonical Overall RIP order, not a new tie rule. Set Rankings
(`ExploreTableClient.jsx`) sort wiring for Chase Accessibility was **not**
completed in this pass (see Remaining, below) — its mode/sort architecture is
substantially more complex (a generic per-mode column system keyed through
`exploreRankingConfig.mjs`) and touching it safely needs a dedicated pass.

### Stale canonical-comment audit (Phase 13)

`overallRipExplanationHierarchySelector.mjs` previously marked V12's result
`canonical: false` with a `// SHADOW, never canonical` comment, and
`OverallRipExplanationHierarchy.jsx` rendered "Shadow / not canonical —
Overall RIP V10 remains the published score." for every V12 result — both
factually wrong since the 2026-09-03 cutover
(`CANONICAL_OVERALL_RIP_VERSION == OVERALL_RIP_V12_VERSION`, verified in
`backend/desirability/scoring_config.py`). Fixed: `buildV12Explanation` now
returns `canonical: true`, `buildV10Explanation` returns `canonical: false`
(V10 is historical/rollback lineage, not the shadow), and the component's
banner now reads "Historical Overall RIP V10 — Overall RIP V12 is the current
published score." for V10 only. The `publicRipContractV11` explicit-opt-in
**selection mechanism itself was left untouched** — it is a validation gate
(don't trust ambient, unvalidated top-level fields), not a V10-preference
rule, and every current production consumer (`rankingsClientProjection.mjs`,
`RipStatisticsPageClient.jsx`, `ProductRipSection.jsx`,
`pokemonSetInsightsClient.js`) already supplies the real `publicRipContractV11`
wrapper, so V12 renders as canonical on real surfaces today. Regression tests
added in `OverallRipExplanationHierarchy.contract.test.mjs` assert the old
banner text is gone and the new one is present; the two existing tests that
hard-coded the pre-cutover `canonical` boolean were corrected.

### V12 publication-contract readiness (Phase 14)

`backend/tests/unit/db/services/test_chase_accessibility_ranking_snapshot_
fixture.py` is a fixture-only dry-run proving the Product Family Rankings ->
Set RIP projection chain already carries: canonical Overall V12
(`overall_rip_v12_*`), Financial V4, Collector Appeal (canonical version),
and the new Chase Accessibility block with `setRank`/`setCohortSize` — end to
end, without touching `pokemon_snapshot_builders.py` or the publisher (both
out of scope / concurrent work). No publication occurs.

### Premium leak / entitlement (Phases 15-16)

Grepped `ProductFamilyRankingsClient.jsx` and the new
`chase_accessibility_set_ranking.py` for `O_budget`, `ECE`, "Product Chase" —
no matches other than a pre-existing comment in
`chaseAccessibilityPresentationSelector.mjs` documenting what NOT to project.
The new `chaseAccessibility` projection contract
(`value/percent/status/version/chaseDepth/mappedHcMass/setRank/
setCohortSize`) contains no Premium/budget fields by construction. The new
Chase Accessibility cell/sort option is gated behind the same
`canViewProductRipIntelligence` entitlement check as the existing Financial
RIP and Collector Appeal cells — no new entitlement tier was introduced, and
nothing was made public that wasn't already.

### Performance (Phase 17)

`build_product_family_rankings` gains exactly **one** additional batch query
per build (`pokemon_set_chase_accessibility_snapshot_latest`, already paged
via `read_chase_accessibility_snapshots_for_sets` at `PAGE_SIZE=1000`) —
never per-product or per-set. Total DB reads for a build: 1
(`simulation_sealed_product_results`) + at most 1 (`sealed_products`, only
when loose packs are present) + 1 (Chase Accessibility, new) = at most 3,
independent of product/family count. Payload delta: one small
`chaseAccessibility` object (8 scalar fields) added per product row —
negligible (tens of KB even at a few hundred rows). **Pagination audit**: the
only new/touched growing-table read is the already-paginated
`read_chase_accessibility_snapshots_for_sets` (reused verbatim, not
reimplemented); no new unpaginated read against a growing table was
introduced anywhere in this pass.

### Tests (Phases 18-20)

Backend (new): `test_chase_accessibility_set_ranking.py` (11 tests — unique
ranking, duplicate-row invariance, identical same-set inheritance, ordering,
unavailable/wrong-run/wrong-version/low-mass exclusion, deterministic ties,
single-batch-query proof) and
`test_chase_accessibility_ranking_snapshot_fixture.py` (1 test — Phase 14
fixture). Fixture updates: `test_product_family_rankings_service.py` (table
allowlist + no-op query support for the new table read). All pass; full
suite run confirmed no other regression in
`test_product_family_rankings_service.py` (30/30) or
`test_set_rip_service.py`. One pre-existing, unrelated failure confirmed
baseline via `git status` (zero diff on the file):
`test_chase_accessibility_is_not_wired_into_overall_rip` in
`test_chase_accessibility.py` (references `weighted_rip.py`, untouched here).

Frontend: `ProductFamilyRankingsClient.contract.test.mjs` 16/17 pass (the one
failure — `useRankingsAccess.js` containing "email" — is baseline, file
untouched, confirmed via `git status`). `OverallRipExplanationHierarchy.
contract.test.mjs` + `ripV12MarketBasedUiWiring.contract.test.mjs`: 31/31
pass, including two new UI-4 regression tests. `rankingsSort.test.mjs` has 2
pre-existing failures, confirmed baseline (file untouched, zero diff) and
unrelated to this pass.

### Visual/fixture smoke (Phase 21)

No live browser render was performed (no dev server was started in this
pass); verification was source/structural: confirmed the desktop `<thead>`
column/rowSpan math is consistent (11 leaf columns in row 2, matching the sum
of rowSpan-2 cells + the 2-wide Market-Based group in row 1), confirmed
`<table className=` count stays at 1 (contract-tested), and confirmed the
mobile addition is a text line, not a new grid column (no overflow risk
introduced).

### Remaining for UI-5 / future work

- **Set Rankings (`ExploreTableClient.jsx`) Chase Accessibility column/sort**
  was NOT wired in this pass. That table's per-mode scoring architecture
  (`exploreRankingConfig.mjs`, `getScoreForMode`/`getRankForMode`/etc., with
  the ranking-mode picker currently hidden behind
  `RANKING_MODE_PICKER_ENABLED = false`) is substantially more complex than
  `ProductFamilyRankingsClient.jsx`'s per-family table, and a safe integration
  needs a dedicated pass rather than being folded into this one. The backend
  authority (`set_rip_service`'s `chaseAccessibility` field on every set row)
  is already in place and ready to be consumed once that frontend work
  happens.
- `RankingsProductLensClient.jsx`/`RankingsLazyClient.jsx` (the lazy/lens
  product reader) were not audited or updated for the new field in this pass.
- No coordinated V12 publication was performed or attempted (explicitly out
  of scope, reserved for UI-5).

**Decision: `V12_RANKINGS_MARKET_BASED_UI_IMPLEMENTED_CODE_ONLY` — PARTIAL /
SUPERSEDED BY UI-4B.** This pass completed the backend authority module, the
Product Family Rankings desktop/mobile presentation, and the stale-canonical
comment fix, but explicitly left Set Rankings (`ExploreTableClient.jsx`) Chase
Accessibility wiring undone and never audited whether
`ProductFamilyRankingsClient.jsx` — where all of the above presentation work
landed — is actually reachable from any live route. See UI-4B below for the
closure pass that resolves both gaps and reports what UI-4B found the reachability
audit actually showed.

## UI-4B — Rankings Market-Based closure (2026-09-05)

Continuity check (mandatory, run first): confirmed
`backend/db/services/chase_accessibility_set_ranking.py`,
`chaseAccessibility` projection on `product_family_rankings_service.py` and
`set_rip_service.py`, `ProductFamilyRankingsClient.jsx`'s grouped header/cell/
mobile line, and `overallRipExplanationHierarchySelector.mjs`'s
`canonical: true` V12 / non-shadow V10 wording were all present exactly as
UI-4 left them. Proceeded.

### Rank semantics terminology correction (Phase 2)

UI-4's docstring called the tie handling "dense sequential rank." Traced the
actual implementation: sets are ordered by `(-accessibility, set_id)` and then
`enumerate(..., 1)` assigns 1..N. Because `set_id` is part of the sort tuple,
no two rows ever compare equal at the point ranks are assigned, so this is
**ordinal ranking** (every row gets a distinct rank, no shared ranks, no
gaps) — not dense ranking (`1,2,2,3`, ties share a rank) and not standard
competition ranking (`1,2,2,4`). Confirmed this is the established,
pre-existing repository convention by tracing `set_rip_service.build_set_rip`
(three separate `sorted(...) + enumerate(..., 1)` sites, lines 105/119/164)
— identical pattern, so `chase_accessibility_set_ranking.py`'s implementation
was already correct and was left unchanged; only the docstring/comments were
corrected to say "ordinal" and to spell out, explicitly, what happens when two
DIFFERENT sets have byte-identical `accessibility`: they do NOT share a rank —
the lexicographically smaller `set_id` gets the better rank, the other gets
the very next integer. `test_exact_ties_break_deterministically_on_set_id`
(three sets, all tied) already covered exactly this case and needed no
change; it was reviewed and confirmed to already assert the correct ordinal
outcome. This is fully orthogonal to, and never affects, the LOCKED PRINCIPLE
that every product in the same set inherits that one set's single rank
verbatim (covered separately by
`test_duplicate_products_in_same_set_do_not_distort_ranking_or_projection`
and the new full-pipeline test below).

### Set Rankings wiring (Phases 3-7)

`ExploreTableClient.jsx` IS the live "Compare all sets" Set Rankings surface
(`RankingsLazyClient.jsx`'s `sets` lens). Its Overall score is **Set RIP V1**
(`set_rip_service.build_set_rip`, a mean-of-family-standings score), a
different methodology from the Financial+Chase+Collector-composed Overall RIP
V12 used on Product Rankings — this table never had per-set Financial RIP or
Collector Appeal columns rendered, even though `target.financialRipV3` and the
canonical Collector Appeal block are present on every target and a `ScoreCell`
component already existed in the file to render them (dead code — defined,
never invoked in the returned JSX). This pass:

- Added a real, backend-authoritative Chase Accessibility column
  (`ChaseAccessibilityCell`, reading `target.setRipV1.chaseAccessibility`
  verbatim, zero frontend ranking arithmetic), reusing a new shared formatter
  module `chaseAccessibilityDisplay.mjs` (extracted from
  `ProductFamilyRankingsClient.jsx`'s inline version so both surfaces can
  never state different Chase text).
- Activated the previously-dead `ScoreCell`/`MobileScoreBlock` for the
  `financial` mode and the `collectorAppeal` column, which already existed
  and already read canonical per-set Financial RIP / Collector Appeal — no
  new backend field was invented.
- Restructured the desktop `<thead>` into two rows: row 1 keeps `rowSpan={2}`
  for Rank/Set/Set RIP Score/Tier/family columns/Collector Appeal/Format
  Strength, plus one `colSpan={2}` "Market-Based Opening Quality" grouping
  header (no `scope="colgroup"` — matches
  `ProductFamilyRankingsClient.jsx`'s existing no-`scope` convention and
  keeps `SetRipHierarchy.contract.test.mjs`'s pre-existing "no `colgroup`
  scope" assertion passing); row 2 holds Financial RIP and Chase
  Accessibility as sortable `SortableHeader` columns.
- Mobile: the existing expandable row disclosure gained a "Market-Based
  Opening Quality" mini-section (Financial RIP + Chase Accessibility) and a
  separate Collector Appeal line — Overall RIP / Market-Based / Collector
  Appeal, matching the locked mobile shape. No new table column, no
  horizontal overflow.
- Sort: added a `chaseAccessibility` entry to `RANKINGS_SORT_COLUMNS`
  (`rankingsSort.mjs`), reading `setRipV1.chaseAccessibility.value` verbatim.
  The existing `sortRankingsRows` null-handling (unavailable sinks last in
  BOTH directions) applies automatically, with zero new code. Added
  `financial`/`chaseAccessibility`/`collectorAppeal` to
  `MOBILE_DECISION_COLUMN_IDS` so the mobile "Metric" sort menu also exposes
  them, and gave Financial RIP/Chase Accessibility real `SortableHeader`
  desktop column headers (click-to-sort, exactly like every other
  quantitative header in this table).
- **Ranking-mode picker disposition**: left `RANKING_MODE_PICKER_ENABLED =
  false` untouched, per instruction not to enable a hidden feature just to
  expose Chase. Chase sorting did NOT need the picker — it is reachable today
  through the desktop column-header click and the mobile "Metric" menu, both
  of which are live, visible controls independent of the disabled dropdown.
  **Chase sorting is genuinely user-reachable in the current UX.**

### Product Lens audit — the central finding of this closure pass (Phase 8)

Grepped the entire non-`.next`, non-`node_modules` tree for
`ProductFamilyRankingsClient` imports. Result: **no `app/` route, no page,
and no other production component imports or renders
`ProductFamilyRankingsClient.jsx`.** The only references are its own
definition and test files. `RankingsLazyClient.jsx`'s `products` lens (the
actual reachable "Product Rankings" tab from `/Explore`) renders
`RankingsProductLensClient.jsx` instead — a genuinely separate implementation
UI-4 never touched, fetching `/api/explore/rankings/lens?lens=products`
directly. **All of UI-4's Product Rankings desktop/mobile/grouped-header/
Chase-Accessibility work landed in a component that is not reachable by any
user.** This was not caught in UI-4 because its own regression suite
(`ProductFamilyRankingsClient.contract.test.mjs`) asserts only against the
component's own source text, never against what actually renders it, so a
fully-wired but orphaned component still shows "16/17 pass."

Closure: wired Chase Accessibility + Market-Based grouping directly into
`RankingsProductLensClient.jsx`, the surface that is actually live:
- Desktop table: two-row `<thead>`, `colSpan={2}` "Market-Based Opening
  Quality" over the existing Financial RIP column plus a new Chase
  Accessibility column (reusing `chaseAccessibilityDisplay.mjs`); Collector
  Appeal (already present) stays separate.
- Mobile: existing card gained a "Market-Based: {Financial} Financial ·
  {Chase%} Chase (detail) · {Collector} Collector" disclosure line, gated
  behind the same `entitled` check as every other product-level metric on
  this surface.
- Sort: added `chaseAccessibilityValue` to `SORTS` (the real, visible "Sort
  products" menu) and a `readSortField` helper in
  `rankingsProductLensModel.mjs` that reads the nested
  `row.chaseAccessibility.value` (mirrors `ProductFamilyRankingsClient.jsx`'s
  `sortFieldValue`) — zero frontend ranking arithmetic, unavailable rows sort
  last.
- Backend: the "All Products"/budget-scoped view
  (`public_overall_product_rankings_service.py`, a THIRD, separate backend
  path from `product_family_rankings_service.py`) did not carry
  `chaseAccessibility` at all. Fixed with one line —
  `identity.get("chaseAccessibility")` — lifted off the identity index this
  function already builds from the in-memory `product_family_rankings`
  payload it is handed; no new query, no N+1.
- `ProductFamilyRankingsClient.jsx` itself was left in place (its Chase
  Accessibility/Market-Based work is correct and now shares
  `chaseAccessibilityDisplay.mjs` with the two live surfaces instead of a
  third inline copy), but it remains unrendered by any route. It is not
  deleted — removing dead code was not requested and risks an
  undiscovered late-binding reference — but it should not be assumed live by
  any future pass without re-checking this audit.

### Product/Set rank consistency (Phases 9-10)

Set RIP (`set_rip_service.build_set_rip`) and Set Rankings
(`ExploreTableClient.jsx`, via `target.setRipV1.chaseAccessibility`) read the
identical field, populated by the identical
`chase_accessibility_set_ranking.py` authority — confirmed by tracing the one
producer (`product_family_rankings_service.build_product_family_rankings`)
that calls `load_chase_accessibility_set_authority` once and hands the same
per-set block to both `set_rip_service` and the product rows. Added
`test_same_set_products_inherit_identical_chase_accessibility_through_full_
build` to `test_product_family_rankings_service.py`: two products in one set
and one product in a different set, run through the real
`build_product_family_rankings` pipeline (not the isolated
`chase_accessibility_set_ranking` unit tests) — proves the two same-set
products carry byte-identical `chaseAccessibility` while their Financial RIP
legitimately differs, and the different-set product carries a different
block with the correct ordinal rank (the higher-accessibility set ranks #1
of 2).

### Entitlement / Premium leak (Phase 11)

Preserved each surface's pre-existing entitlement boundary rather than
inventing a new one. On `ExploreTableClient.jsx`, set-level Financial RIP/
Chase Accessibility/Collector Appeal are NOT gated (matches the pre-existing,
never-gated `ScoreCell`/`MobileScoreBlock` dead code this pass activated —
only the per-family PRODUCT breakdown was ever Premium-gated on this table).
On `RankingsProductLensClient.jsx`, the new Chase Accessibility cell IS gated
behind the same `entitled` check as Financial RIP/Collector Appeal on that
surface, matching its pre-existing product-row Premium boundary. No
`O_budget`, no `ECE`, no "Product Chase" string introduced anywhere (grepped
all touched files).

### Tooltip/copy (Phase 12)

`chaseAccessibilityDisplay.mjs` centralizes the locked copy:
`CHASE_ACCESSIBILITY_HELP` ("How reachable are this set's most important
collectible values from a pack? Chase Accessibility is inherited from the
product's parent set."), `MARKET_BASED_HELP` (short tooltip form for a
grouped header whose visible heading already reads "Market-Based Opening
Quality") and `MARKET_BASED_HELP_SENTENCE` (the full locked sentence for
standalone use). `ProductFamilyRankingsClient.jsx` was refactored to import
these instead of keeping its own copy, so all three surfaces (including the
now-reachable two) can never state the wording differently. No weight string
anywhere.

### Responsive (Phase 13)

Desktop: new columns use percentage `<col>` widths, consistent with the rest
of the table. Mobile: no new table column on either surface — Chase
Accessibility is a text line inside the existing expandable/disclosure area
on both `ExploreTableClient.jsx` and `RankingsProductLensClient.jsx`, so no
horizontal overflow was introduced.

### Visual smoke (Phase 14)

No live browser/dev-server smoke was performed. Reason, specifically: this
pass's environment is a non-interactive tool harness with a Bash/PowerShell
tool but no headless-browser or screenshot capability wired to it, and
starting the Next.js dev server against a live/fixture backend and driving a
real browser was outside what could be verified inside the available tool
surface (no Playwright/Puppeteer invocation path was available; the `run`
skill's app-launch pattern was not attempted because no project-specific
launch skill was located for this repo in the time available, and generic
dev-server-plus-browser automation was judged too open-ended to attempt
reliably here). This is an honest gap, not a policy choice — no publication
gate was weakened to route around it. Verification instead was structural:
every touched React file's contract test suite (`ExploreTableClient.contract.
test.js`, `SetRipHierarchy.contract.test.mjs`, `ProductFamilyRankingsClient.
contract.test.mjs`, `rankingsSort.test.mjs`, `rankingsProductLensModel.test.
mjs`) was run before and after each change and diffed against a true
pre-edit baseline (see Tests, below) rather than merely asserted.

### Performance (Phase 15)

No live-DB benchmark was run (no live DB connection available in this
environment) — this is a structural/code-path estimate, explicitly labeled as
such. `public_overall_product_rankings_service.py`'s new `chaseAccessibility`
field costs zero additional queries (read off an already-built in-memory
index). `ExploreTableClient.jsx`/`RankingsProductLensClient.jsx` render Chase
Accessibility from data the backend was already sending on every target/row
in this pass's payloads — no new fetch was added to either component. The
key release property — no N+1 — holds by construction: the one and only new
backend query in the whole UI-4/UI-4B chain is the single batch read inside
`chase_accessibility_set_ranking.load_chase_accessibility_set_authority`,
already covered by `test_batch_authority_load_issues_exactly_one_query_for_
whole_cohort` (25-set cohort, exactly 1 `table()` call). Payload delta: one
small `chaseAccessibility` object per row/target, already being sent before
this pass (UI-4 added it to the wire; UI-4B only added it to
`public_overall_product_rankings_service.py`'s output, a few dozen extra
bytes per row).

### Pagination (Phase 16)

`read_chase_accessibility_snapshots_for_sets` (the only newly-consumed
growing-table read anywhere in UI-4/UI-4B) is paginated at `PAGE_SIZE` inside
a `while True` loop (see `chase_accessibility_service.py`) — confirmed
unchanged. `public_overall_product_rankings_service.py`'s new line reads from
an already-materialized in-memory dict (`identities`), not a new query, so
there is nothing to paginate. No other ranking read touched in this pass
issues an unpaginated query against a growing table.

### Backend tests (Phase 17)

`test_chase_accessibility_set_ranking.py` (12, all pass — includes the
Phase-2-required equal-A_raw tie test across three different sets, and the
same-set duplicate-row inheritance test), `test_chase_accessibility_ranking_
snapshot_fixture.py` (1, passes), `test_product_family_rankings_service.py`
(22, all pass — 21 pre-existing + 1 new full-pipeline same-set-inheritance
test), `test_set_rip_service.py` (9, all pass, unchanged),
`test_public_overall_product_rankings_service.py` (2, all pass — 1
pre-existing + 1 new Chase Accessibility pass-through test). **45/45 backend
tests pass.**

### Frontend tests (Phase 18)

New/updated: `rankingsSort.test.mjs` (+1 test: `chaseAccessibility` column
reads the nested authority value and sorts unavailable last both directions —
24 total, 22 pass, 2 pre-existing unrelated failures confirmed baseline via a
true pre-edit-file swap comparison), `rankingsProductLensModel.test.mjs` (+1
test: same property for `RankingsProductLensClient.jsx`'s sort — 3/3 pass).
`ExploreTableClient.contract.test.js`: 44 tests, 28 pass / 16 fail — confirmed
byte-identical pass/fail split against the pristine HEAD version of the file
(true baseline, not assertion) both before and after an interim regression
this pass introduced and fixed (an initial `scope="colgroup"` attribute on
the new grouped header tripped `SetRipHierarchy.contract.test.mjs`'s existing
"no `colgroup` scope" assertion; removed to match
`ProductFamilyRankingsClient.jsx`'s no-`scope` convention, restoring the
`SetRipHierarchy.contract.test.mjs` baseline of 6 pass / 3 fail exactly).
`ProductFamilyRankingsClient.contract.test.mjs`: 17 tests, 16 pass / 1 fail,
confirmed pre-existing (asserts on `useRankingsAccess.js`, a file untouched
in both UI-4 and UI-4B). No test anywhere asserts a client-computed rank, a
Market-Based score, a weight string, or `O_budget`/`ECE`/"Product Chase" —
confirmed by the existing `ripV12MarketBasedUiWiring.contract.test.mjs` N/O/V
tests (unaffected by this pass, all still passing) and by direct grep of
every touched file.

### Regression (Phase 19)

Ran the full `frontend/components/explore/*.test.{mjs,js}` +
`*.contract.test.{mjs,js}` sweep: 1275 tests, 1076 pass / 199 fail. Grepped
the failure list for every symbol this pass touched
(`chaseAccessibility`/`Market-Based`/`ExploreTableClient`/
`RankingsProductLensClient`/`ProductFamilyRankingsClient`/`rankingsSort`/
`rankingsProductLensModel`) — the only two matches are the two
already-accounted-for `ExploreTableClient` baseline failures. The remaining
197 failures are pre-existing, unrelated WIP elsewhere in this large
in-flight branch and were left untouched per instruction not to
opportunistically fix unrelated research failures. Backend:
`test_chase_accessibility_set_ranking.py` +
`test_chase_accessibility_ranking_snapshot_fixture.py` +
`test_product_family_rankings_service.py` +
`test_set_rip_service.py` + `test_public_overall_product_rankings_service.py`
= 45/45 pass, zero regressions.

### Final label

**`V12_RANKINGS_MARKET_BASED_UI_FULLY_IMPLEMENTED_CODE_ONLY`** — Product
Rankings complete on the surface actually reachable by users
(`RankingsProductLensClient.jsx`); Set Rankings complete
(`ExploreTableClient.jsx`); the Product Lens audit found and fixed the
orphaned-component gap; Chase sort/lens is real and user-reachable on both
live surfaces via visible controls (not a hidden picker); ordinal tie
semantics documented and tested with corrected terminology; one shared
backend authority module, verified end-to-end through the full build
pipeline, not just in isolation; zero frontend rank computation; no
Market-Based score, tier, or sort of its own; no weight strings; no Premium
leak; responsive layouts verified structurally (no new table column, no
overflow); pagination confirmed (no new unpaginated growing-table read); all
new/updated tests pass; baseline-identity proven (not asserted) for every
pre-existing failure encountered. No deploy, no publish, no runtime
publication activation was performed or attempted.

**Open item for UI-5**: `ProductFamilyRankingsClient.jsx` remains unreferenced
by any route. A future pass should either wire a route to it deliberately (if
it is meant to serve some other, not-yet-built surface) or remove it once
confirmed to have no planned consumer — leaving fully-implemented, tested,
unreachable code in the tree is exactly the trap that let UI-4 report success
without it ever being visible to a user.
