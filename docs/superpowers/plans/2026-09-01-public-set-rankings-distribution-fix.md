# Public Set Rankings & Distribution Access Fix

## Spec / Context

Two PUBLIC set-level regressions in EVRCalculator must be fixed:

1. Homepage top sets must be ranked by the canonical public Set RIP contract
   (`target.setRipV1`), not by product ranking or Overall RIP. The #1/#2/#3
   sets must be identical for anonymous, Base, Plus, and Premium visitors.
2. The set-level opening distribution graph is PUBLIC and must render for
   anonymous/Base users on both the homepage (#1 set) and the Set RIP tab,
   without exposing paid intelligence (Financial RIP, Collector Appeal,
   openingOutcomeProfile, evRepresentativeness, advanced markers, etc).

## Global Constraints (binding on every task)

- DO NOT DEPLOY. DO NOT run or create DB migrations. DO NOT change scoring
  formulas (Set RIP V1 algorithm in `backend/db/services/set_rip_service.py`
  is untouched).
- DO NOT touch Chase research, Market Explorer, billing, publication
  reliability, scheduler reliability, or any unrelated work.
- Do not revert or overwrite concurrent changes. Never `git add .` / `git add -A`.
  Stage owned files individually.
- Do not weaken any existing paid gate to make a test pass. `/rip/advanced`,
  product-family/rank-context paid endpoints, and the legacy
  `/tcgs/pokemon/sets/{set_id}/simulation-evidence` endpoint stay exactly as
  gated as they are today.
- Homepage public ranking authority is `target.setRipV1` — never
  `overallRipV10` / `publicRipContractV10` / Financial RIP — to decide
  whether a set can appear or to break ties.
- The public homepage/landing server read MUST NOT forward `Cookie` or
  `Authorization` headers. It must use `Accept: application/json` only.
  `getBackendRequestAuthHeaders()` itself stays unchanged for other callers.
- Hero image fallback order (homepage #1 set only):
  1. `resolvePokemonBoosterPackAsset(canonicalKey)` (authentic local booster art)
  2. `hero_image_url` / `heroImageUrl`
  3. `logo_image_url` / `symbol_image_url`
  4. existing neutral rank fallback
  #2/#3 keep the existing supporting set-logo treatment.
- Anonymous/Base public simulation-evidence allowlist (top level):
  `contractVersion, setId, calculationRunId, marketDate, summary(projected),
  distributionBins(projected), thresholdBins(projected), meta(projected)`.
  Public `summary` fields limited to:
  `simulation_count/simulationCount, pack_cost/packCost, median_value/medianValue,
  mean_value/meanValue`. Never add `max_value, p05, p25, p75, p95, p99`,
  big-hit thresholds, Financial RIP, or Collector Appeal data unless an
  existing explicit public contract already exposes it.
  `distributionBins`/`thresholdBins` nested fields must be an explicit
  allowlist derived from what `RipDistributionChart.jsx` actually consumes —
  unknown upstream keys fail closed (are dropped), not passed through.
  Exclude: `openingOutcomeProfile, evRepresentativeness (detailed),
  financialRip, collectorAppeal, rarityContribution, productFamilyRankings,
  advanced evidence, any unknown future field`.
- Preserve `selectSameRunRipSimulation` identity validation — if the public
  projection needs an identity field to keep that working, project the safe
  field rather than weakening the check.
- Preserve `RipDecisionPage.jsx`'s existing Basic-aware marker behavior
  (pack-cost/median/mean public, deeper markers locked). Reuse
  `ripDistributionMarkers.mjs` as the single marker-policy source — do not
  invent a second marker vocabulary for the homepage. `landingDistribution.mjs`
  must not emit P05/P50/P95/P99/MAX marketing markers once the graph is public.
- Do not hardcode a simulation count (e.g. "1,000,000"); use
  `summary.simulationCount`/`simulation_count` when present, otherwise show a
  truthful "unavailable" count while still rendering valid bins.
- If the homepage distribution request fails, the homepage itself, and the
  ranking, must still render — only the distribution shows an unavailable
  state.
- Overall RIP remains a real, separate, canonical metric shown elsewhere;
  do not rename it globally. Only fix homepage labels that now falsely call
  Set RIP "Overall RIP".
- `publicMetricContract.contract.test.mjs`: do not delete the Overall RIP
  cross-surface consistency assertion for surfaces that still show Overall
  RIP — remove only the stale "Home shows Overall RIP" assumption and add a
  new assertion: Homepage Set RIP === Rankings Sets lens `setRipV1`
  (score/rank/tier).
- Every task must run its own relevant test file(s) before reporting done,
  and note pre-existing unrelated failures separately rather than silently
  passing over them.

## Reference files (read, do not restructure)

- `frontend/lib/landing/landingHeroServer.js`
- `frontend/lib/landing/landingHeroSpotlight.mjs`
- `backend/domain/access/index_plan_access.py`
- `frontend/lib/authServer.js`
- `frontend/hooks/pokemon/useSetRipProgressiveController.js`
- `frontend/components/pokemon/set-page/rich/RichRipSetTab.jsx`
- `backend/api/main.py` (route: `GET /tcgs/pokemon/sets/{set_id}/rip/simulation-evidence`)
- `backend/scripts/pokemon_snapshot_builders.py`
- `frontend/components/explore/RipDecisionPage.jsx`
- `frontend/components/explore/ripDistributionMarkers.mjs`
- `frontend/lib/landing/landingDistribution.mjs`
- `frontend/components/landing/RankingTheaterHomepage.jsx`
- `frontend/components/explore/publicMetricContract.contract.test.mjs`
- `backend/db/services/set_rip_service.py` (ranking authority — read only)

## Tasks

### Task 1: Backend public projection for Set RIP simulation-evidence

Goal: create a tiered projector so `/tcgs/pokemon/sets/{set_id}/rip/simulation-evidence`
returns public-safe data for anonymous/Base and the current full payload for
Plus/Premium, instead of hard-rejecting anonymous/Base.

Steps:
1. In `backend/domain/access/index_plan_access.py`, add a projector function
   (e.g. `project_set_rip_simulation_evidence_response(payload, plan)` — match
   existing naming conventions in that file if a better name fits the existing
   `_project_public_set_leaderboard_target` pattern) implementing the exact
   allowlist in Global Constraints. Base/anonymous gets the allowlisted
   projection; Plus/Premium gets the payload unchanged (current behavior).
   Unknown/future top-level and nested fields must fail closed (be dropped),
   not passed through, for the Base/anonymous branch.
2. Read `RipDistributionChart.jsx` to derive the exact nested fields consumed
   from `distributionBins` and `thresholdBins`, and use exactly those as the
   nested allowlist.
3. In `backend/api/main.py`, change the `/tcgs/pokemon/sets/{set_id}/rip/simulation-evidence`
   handler: remove the hard `FEATURE_SET_RIP_ANALYTICS`/Index Plus rejection,
   resolve the access/plan context as the route already does elsewhere, call
   `get_pokemon_set_rip_simulation_evidence_snapshot_payload` for all callers,
   then run the result through the new projector before returning. Use the
   repo's existing `_tiered_response`/cache-isolation convention if present in
   this file (grep for it and match it). Do NOT touch the legacy
   `/tcgs/pokemon/sets/{set_id}/simulation-evidence` endpoint or `/rip/advanced`.
4. Write/extend backend tests (likely alongside
   `backend/tests/unit/api/test_paid_response_boundary.py` or the relevant
   `index_plan_access` test file — check existing test file naming first) for
   `/tcgs/pokemon/sets/set-1/rip/simulation-evidence`, asserting:
   - anonymous: 200, has bins + public summary fields, has NO paid sentinel
     values (plant unmistakable sentinel values in `openingOutcomeProfile`,
     `evRepresentativeness`, advanced objects, `unknownFutureField`, tail
     metrics in the test fixture and assert none appear in the anonymous
     response)
   - authenticated Base: 200, identical public fields, no paid sentinel
   - Plus: 200, full evidence retained (current behavior unchanged)
   - Premium: 200, inherits Plus
   - spoofed query/header claiming Premium does not change the real resolved
     plan
   - an unknown nested field inside a distribution bin row fails closed
   - `/rip/advanced` and other paid endpoints remain gated exactly as before
     (regression check — do not weaken them)
5. Run the new/modified backend test file(s) and report pass/fail counts.

Report DONE with: files changed, exact allowlist implemented, test file(s)
and pass counts, confirmation `/rip/advanced` and the legacy simulation-evidence
endpoint are untouched.

### Task 2: Frontend — public landing reader (auth invariance)

Goal: fix `getLandingPageData()`/`landingHeroServer.js` so the homepage
ranking read is provably public and cannot become richer due to a Plus
session cookie.

Steps:
1. In `frontend/lib/authServer.js`, without changing
   `getBackendRequestAuthHeaders()`'s existing behavior for other callers,
   add an explicit public-only variant/option (e.g. a `getPublicBackendRequestHeaders()`
   helper, or an explicit `{ public: true }` option on the existing function
   that skips reading request cookies/headers entirely) that always sends
   only `Accept: application/json` and never forwards `Cookie`/`Authorization`.
2. Update `frontend/lib/landing/landingHeroServer.js` to use this explicit
   public helper for the rankings fetch that feeds the homepage, instead of
   whatever currently defaults to `request=null` (which silently picks up
   ambient cookies).
3. Add a test proving: (a) the landing reader's outgoing request never
   contains `Cookie` or `Authorization` headers, and (b) simulating an
   authenticated/Plus request context vs. an anonymous context produces the
   identical top-three ranking data (same helper call, same result,
   regardless of ambient session).
4. Run the affected frontend test file(s).

Report DONE with: files changed, name of the new public helper, test file(s)
and pass counts.

### Task 3: Frontend — landingHeroSpotlight.mjs reads setRipV1

Goal: make the homepage set leaderboard authority `target.setRipV1` instead
of canonical Overall RIP.

Steps:
1. Rewrite `frontend/lib/landing/landingHeroSpotlight.mjs` selection logic to:
   - require `setRipV1.rank`/`score` (not Overall RIP availability)
   - sort by `setRipV1.rank`, then `score`, then stable name as tiebreak
   - carry: `targetType, targetId, canonicalKey, name, era, heroImageUrl,
     logoUrl, symbolUrl, score = setRipV1.score, rank = setRipV1.rank,
     tier = setRipV1.tier, cohortSize = setRipV1.cohortSize`
   - `scoreLabel` must truthfully say "Set RIP" (not "Overall RIP")
   - do NOT fall back to legacy `pack_rank` or Overall RIP when `setRipV1`
     is absent/unrankable — such a target stays unavailable, it is not
     invented from another metric
2. Do not touch `landingHeroServer.js`'s call to `getRipStatisticsTargets`
   beyond what's needed to pass `setRipV1` through — verify it's already
   present on targets from the public projection (Task 1's sibling backend
   contract in `index_plan_access.py`'s `_project_public_set_leaderboard_target`
   — read only, do not modify unless setRipV1 truly isn't reaching the
   frontend, in which case note this as a blocker and ask).
3. Write a fixture shaped exactly like the anonymous backend projection:
   identity fields, images, `setRipV1`, explicitly NO `overallRipV10`, NO
   `publicRipContractV10`, NO `financialRipV4`. Add/extend
   `landingHeroSpotlight` tests asserting: entries don't disappear, rank
   1/2/3 correct, `setRipV1.rank` controls ordering, score/tier come from
   `setRipV1`, a legacy/Overall-RIP disagreement cannot alter ordering, and
   a missing/unrankable `setRipV1` row stays unavailable (not invented).
4. Run the landingHeroSpotlight test file(s).

Report DONE with: files changed, confirmation no legacy/Overall-RIP fallback
remains, test file(s) and pass counts.

### Task 4: Frontend — hero image fallback (RankingTheaterHomepage.jsx)

Goal: implement the exact #1 fallback order using authentic local booster
art first.

Steps:
1. In `frontend/components/landing/RankingTheaterHomepage.jsx`, for the #1
   entry, call `resolvePokemonBoosterPackAsset(canonicalKey)` (from
   `pokemonBoosterPackAssets.mjs`) first; if null, use `heroImageUrl`
   (`hero_image_url`); if that's missing, fall back to the existing
   `SetMark()` (`logoUrl`/`symbolUrl`); then the existing neutral rank
   fallback. Do not fabricate an image URL. Use the existing optimized
   remote image delivery helper where the current code already does for
   remote images.
2. Update alt text so a set hero image (not real pack art) is never
   mislabeled as a booster pack in accessibility text.
3. Preserve #2/#3 existing supporting-set-logo treatment unchanged.
4. Add/extend a test asserting the fallback order: local booster asset >
   hero image > logo/symbol > neutral fallback, and that #2/#3 behavior is
   unchanged.
5. Run the affected test file(s).

Report DONE with: files changed, test file(s) and pass counts.

### Task 5: Frontend — public homepage distribution graph

Goal: after the #1 Set RIP target is selected, load its PUBLIC
`/rip/simulation-evidence` projection server-side (auth-invariant, per
Task 2's helper) and render its distribution on the homepage using the same
Basic marker policy as the set page.

Steps:
1. Update `frontend/lib/landing/landingDistribution.mjs` to consume the new
   split public shape (`distributionBins`, `thresholdBins`, `summary`)
   instead of the older `outcomeDistribution` shape, and to stop generating
   P05/P50/P95/P99/MAX marketing markers. Reuse/extract the same Basic
   marker-access policy `RipDecisionPage.jsx` uses via
   `ripDistributionMarkers.mjs` so Pack Market Price / Typical Opening
   (median) / Average Pack (mean) are public and advanced/tail markers stay
   locked or absent — do not build a second marker vocabulary.
2. Wire the homepage fetch: after selecting the #1 set in
   `landingHeroServer.js`/spotlight flow, fetch that set's public
   `/rip/simulation-evidence` using the public-only helper from Task 2 (no
   Cookie/Authorization). On failure, the homepage and ranking must still
   render; only the distribution shows the existing truthful "unavailable"
   state — do not replace the entire hero.
3. Simulation count must come from `summary.simulationCount`/
   `simulation_count` when present; otherwise show truthful unavailable
   count while still rendering valid bins. No hardcoded "1,000,000".
4. Add/extend tests: valid public bins reach the chart component; no bins
   yields the truthful unavailable state; count comes from payload not a
   hardcoded fallback; homepage does not expose P05/P95/P99/MAX exact
   values.
5. Run the affected test file(s) (`landingDistribution`, `LandingPage.contract.test.mjs`
   if it exists, `landingPreviews` if relevant).

Report DONE with: files changed, confirmation no hardcoded sim count,
confirmation no paid markers leak, test file(s) and pass counts.

### Task 6: Frontend — set page public graph verification + labels + cross-surface contract test

Goal: confirm/lock in that the Set RIP tab already renders the public graph
for anonymous once Task 1 ships, fix any stray "Overall RIP" labeling
introduced by the setRipV1 switch on the homepage, and update the
cross-surface metric contract test.

Steps:
1. Verify (do not weaken) `useSetRipProgressiveController.js`'s
   `loadSimulation()` remains ungated by `canViewProductRipIntelligence`
   (per Global Constraints — it's already correct; just confirm no
   regression was introduced by Task 1/2, and add a component/contract test
   proving: Basic simulation data with bins reaches `RipDistributionChart`,
   chart rendering does not depend on `canViewProductRipIntelligence`,
   public markers remain visible, paid marker placeholders remain locked,
   and the advanced fetch stays a separate, un-triggered call for Base).
2. Audit homepage copy (`RankingTheaterHomepage.jsx` and any nearby
   components) for strings like "Published Overall RIP ranking" / "Overall
   RIP" that now describe `setRipV1` data — change only those to truthfully
   say "Set RIP". Do not rename Overall RIP anywhere it still displays
   Overall RIP. Do not expose Financial RIP to fill a card; preserve
   existing lock/unavailable presentation for any remaining Plus-only
   marketing element.
3. Update `frontend/components/explore/publicMetricContract.contract.test.mjs`:
   remove/replace the stale assertion that Home must show the same Overall
   RIP value as the old set hero. Keep the Overall RIP cross-surface
   consistency assertion for every surface that still actually displays
   Overall RIP. Add a new, separate assertion: Homepage Set RIP score/rank/tier
   === Rankings "sets" lens `setRipV1` score/rank/tier. Do not delete
   coverage — only relocate/reframe it.
4. Grep the repo for the Phase 9 audit strings (`openingDistribution: null`,
   `Detailed simulation distribution is Plus-only`, `RIP simulation evidence
   requires Index Plus`, `selectLandingHeroEntries`, `setRipV1`, `Published
   Overall RIP ranking`, `hasCanonicalOverallRipV7`, `/rip/simulation-evidence`,
   `getBackendRequestAuthHeaders`, `openingOutcomeProfile`,
   `evRepresentativeness`) and report any remaining stale match that looks
   like a second Plus gate between the BFF route and `RipDecisionPage`, or
   any leftover dead comment referencing the old Plus-only behavior. Fix
   only what's in scope for this task's files; report anything else found
   as a note rather than fixing out-of-scope files.
5. Run `publicMetricContract.contract.test.mjs` and the set-RIP
   controller/RipDecisionPage/distribution-marker contract tests.

Report DONE with: files changed, grep audit findings (classified), test
file(s) and pass counts.

## Verification (final review scope)

- Backend: `backend/tests/unit/api/test_paid_response_boundary.py`, relevant
  `index_plan_access` tests, relevant pokemon public snapshot / split RIP
  tests.
- Frontend: `landingHeroSpotlight` tests, `landingDistribution` tests,
  `landingPreviews` tests, `LandingPage.contract.test.mjs`,
  `publicMetricContract.contract.test.mjs`, set RIP progressive
  client/controller tests, `RipDecisionPage`/distribution marker contract
  tests, relevant paid-surface/entitlement tests.
- `git diff --check` clean.
- Manual acceptance contract cases from the spec (home anonymous, home
  plus, set-rip anonymous, set-rip plus, devtools/API) reasoned through
  explicitly in the final report.
- No DB migration or deploy occurred.
