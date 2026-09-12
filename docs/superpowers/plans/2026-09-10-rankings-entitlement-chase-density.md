# Rankings Entitlement Leak + Set-Page Chase + All-Products Density Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Close the Basic/anonymous paid-data leak in Set Rankings, replace "Unavailable" with a real "Locked" (Index+) presentation everywhere entitlement (not data) is the reason a value is hidden, repair the logged-in Set RIP page's Chase Accessibility gap, and fix the All Products table so its Product/Set identity column matches family-view density and the table doesn't clip at 1440px.

**Architecture:** Three independent-but-sequenced fixes: (1) an entitlement/data-projection fix spanning `RankingsLazyClient.jsx` → `setRankingsLensProjection.mjs`/`rankingsClientProjection.mjs` → `ExploreTableClient.jsx`; (2) a diagnostic-then-repair fix for the Set RIP bootstrap chain's Chase field, root-caused by hitting the real endpoints before touching code; (3) a CSS/column-width fix in `explore.module.css` + `RankingsProductLensClient.jsx` reusing the existing `RankedProductIdentity` primitive. No RIP/Chase/Collector scoring formulas change. No simulations run. No deploy.

**Tech Stack:** Next.js (app router) frontend, Python/FastAPI backend, Jest/RTL contract tests, Playwright for mounted browser tests (per `project_prod_smoke_setup` memory: ports 3100/8000, Playwright via `frontend/node_modules`).

**Spec:** This plan implements the user's "P0 RANKINGS ENTITLEMENT + SET CHASE DELIVERY + ALL-PRODUCTS DENSITY FIX" spec (pasted in the originating conversation; not a separate file — the plan below reproduces every phase's acceptance criteria inline).

## Global Constraints

- Do not run simulations.
- Do not rebuild Chase.
- Do not change RIP formulas.
- Do not change Collector scoring.
- Do not publish/deploy until validation completes (this plan stops after Task 13's production build; no deploy step is included).
- Do not solve the auth-downgrade requirement with a "require full window reload" workaround.
- Do not create a second product-identity component — reuse `RankedProductIdentity`.
- Do not edit the archived `ProductFamilyRankingsClient.jsx` as part of any fix — it is reference-only for comparing column density.
- "Unavailable" and "Locked" are semantically distinct and must not be merged into one label.

---

## Investigation Findings (from live code, already gathered — do not re-derive)

1. **Entitlement bug confirmed.** `frontend/components/explore/RankingsLazyClient.jsx:278` mounts:
   ```jsx
   <ExploreTableClient targets={setTargets} loadError={loadError || setsUnavailable} canViewProductRipIntelligence eraFilter={selectedEra} />
   ```
   `canViewProductRipIntelligence` is bare JSX shorthand → always `true`, regardless of the real entitlement. The correct variable, `canViewRankingsIntelligence`, is already destructured in scope at line 50 from `useRankingsAccess()` (`frontend/lib/access/indexPlanAccess.mjs:162`, `hasIndexPlusAccess(indexPlan)`).

2. **Server-side leak confirmed.** `frontend/lib/explore/setRankingsLensProjection.mjs:15-35`'s `projectSetRankingsLensTargets` branches on `access?.rankingsIntelligence !== true` to call `projectRankingsClientPublicSetLeaderboard` (in `frontend/lib/explore/rankingsClientProjection.mjs:229-237`). That function projects `target?.setRipV1` through `BLOCK_LEAVES.setRipV1` (line 123) — the **same full leaf list** used by the paid path (`projectRankingsClientPlus` → `projectTarget`, line 187), which includes `familyScores`, `displayFamilyScores`, and `chaseAccessibility`. There is no separate narrow leaf list for the public/Basic path today.

3. **No lock presentation in `ExploreTableClient`.** `frontend/components/explore/ExploreTableClient.jsx`: `UNAVAILABLE_LABEL = "Unavailable"` (line 93), used identically by `ChaseAccessibilityCell` (135-147), `ScoreCell` (338-367), `MobileScoreBlock` (375-398) whether the viewer is entitled-but-no-data or simply not entitled. A reusable lock primitive already exists and is unused here: `PremiumMetricLock()` in `frontend/components/explore/RankedProductTablePrimitives.jsx:17-20`, built from `planPresentation(INDEX_PLAN_PLUS)` (`frontend/lib/membership/upgradeFunnel.mjs`, `frontend/lib/access/indexPlanAccess.mjs`). There is also `frontend/components/explore/ExplorerPlanLockPanel.jsx` — check it during Task 3 for a cell-level (not panel-level) lock pattern before deciding which to reuse/adapt.

4. **Set RIP Chase field flows through 3 aliases.** Backend `backend/api/main.py:1965-1967` → `backend/scripts/pokemon_snapshot_builders.py:~2028-2054` emits `source.chaseAccessibilityPresentation`. `frontend/lib/pokemon/pokemonSetRipBootstrapNormalizer.mjs` reads it at line 14, and re-exposes it three ways: top-level `chaseAccessibilityPresentation` (line 32), `canonical.chaseAccessibility` (line 21), and `canonicalSource.publicRipContractV11.chaseAccessibility` (line 29). `frontend/components/pokemon/set-page/rich/RichRipSetTab.jsx` consumes only the flat top-level prop (line 22, passed to `RipDecisionPage` at line 80). There's a hand-rolled `Map` cache in `frontend/lib/pokemon/pokemonSetRipBootstrapClient.mjs` (line 3) sitting between fetch and normalizer — a likely staleness culprit (Phase 6 candidate C, `STALE_INITIAL_BOOTSTRAP_CACHE`), but this must be confirmed with real endpoint output for Ascended Heroes, not assumed.

5. **All Products CSS confirmed oversized.** `frontend/components/explore/explore.module.css`: `.productsTable` (117-120) is `width: max-content; min-width: 100%` (deliberately wider than viewport, per comment at 103-116 — this is the superseded design). Column widths: `.colProduct` 22rem (126-128), `.colFormat` 15rem (152-154), `.colOverall/.colFinancial/.colCollector/.colPrice/.colEv` 6rem each, `.colTier` 3.5rem, `.colChase/.colCommitted/.colRecover` 7rem each, `.colUnits` 4rem, `.colRank` 2.75rem. `RankedProductIdentity` (`RankedProductTablePrimitives.jsx:22-36`) sizes its thumbnail via inline Tailwind (`h-[42px] w-9 ... md:h-[52px] md:w-10`), not a CSS-module column width — it's used by both the family view and (inside the oversized `.colProduct` column) All Products, so the density mismatch is column-width driven, not component driven.

---

## Task 1: Fix the entitlement prop bypass in RankingsLazyClient

**Files:**
- Modify: `frontend/components/explore/RankingsLazyClient.jsx:278`
- Test: `frontend/components/explore/RankingsLazyClient.contract.test.jsx` (create if it doesn't already exist under this or a similar name — check first with a glob for `RankingsLazyClient*.test*`)

**Interfaces:**
- Consumes: `canViewRankingsIntelligence` (boolean, already in scope at line 50 via `useRankingsAccess()`).
- Produces: `ExploreTableClient` now receives `canViewProductRipIntelligence` as the real resolved boolean, matching the prop name `ExploreTableClient` already expects (used internally per Task 3/4's cell logic).

- [ ] **Step 1: Check for an existing test file**

Run: `Glob` for `frontend/components/explore/RankingsLazyClient*.test*`. If found, read it to match existing test conventions (render helpers, mock providers for `useRankingsAccess`). If not found, create `frontend/components/explore/RankingsLazyClient.contract.test.jsx` modeled on `ExploreTableClient.contract.test.js`'s mocking style for entitlement.

- [ ] **Step 2: Write the failing test**

```jsx
import { render } from "@testing-library/react";
import RankingsLazyClient from "./RankingsLazyClient";

jest.mock("../../lib/access/useRankingsAccess", () => ({
  __esModule: true,
  default: jest.fn(),
}));
jest.mock("./ExploreTableClient", () => ({
  __esModule: true,
  default: jest.fn(() => null),
}));

import useRankingsAccess from "../../lib/access/useRankingsAccess";
import ExploreTableClient from "./ExploreTableClient";

test("passes the real entitlement flag to ExploreTableClient, not a hardcoded true", () => {
  useRankingsAccess.mockReturnValue({
    canViewRankingsIntelligence: false,
    canViewCardChaseEfficiency: false,
    authStatus: "anonymous",
    requestKey: "anon-1",
  });

  render(<RankingsLazyClient sets={[]} eras={[]} />);

  expect(ExploreTableClient).toHaveBeenCalledWith(
    expect.objectContaining({ canViewProductRipIntelligence: false }),
    expect.anything()
  );
});
```

Adjust the import path for `useRankingsAccess` and the minimal required props for `RankingsLazyClient` by reading the actual component signature first (`RankingsLazyClient.jsx` lines 1-60) — do not guess prop names; copy them exactly from the file.

- [ ] **Step 3: Run test to verify it fails**

Run: `cd frontend && npx jest components/explore/RankingsLazyClient.contract.test.jsx -t "passes the real entitlement flag"`
Expected: FAIL — `ExploreTableClient` was called with `canViewProductRipIntelligence: true` (bare shorthand).

- [ ] **Step 4: Fix the prop**

In `frontend/components/explore/RankingsLazyClient.jsx`, change line 278 from:
```jsx
<ExploreTableClient targets={setTargets} loadError={loadError || setsUnavailable} canViewProductRipIntelligence eraFilter={selectedEra} />
```
to:
```jsx
<ExploreTableClient targets={setTargets} loadError={loadError || setsUnavailable} canViewProductRipIntelligence={canViewRankingsIntelligence} eraFilter={selectedEra} />
```

- [ ] **Step 5: Run test to verify it passes**

Run: `cd frontend && npx jest components/explore/RankingsLazyClient.contract.test.jsx`
Expected: PASS

- [ ] **Step 6: Commit**

```bash
git add frontend/components/explore/RankingsLazyClient.jsx frontend/components/explore/RankingsLazyClient.contract.test.jsx
git commit -m "fix(rankings): wire real entitlement flag into ExploreTableClient

Co-Authored-By: Claude Sonnet 5 <noreply@anthropic.com>"
```

---

## Task 2: Add a narrow public projection for Set RIP leaderboard fields

**Files:**
- Modify: `frontend/lib/explore/rankingsClientProjection.mjs`
- Test: `frontend/lib/explore/rankingsClientProjection.test.mjs` (check for existing file first; extend it)

**Interfaces:**
- Consumes: `BLOCK_LEAVES.setRipV1` (existing, line 123) — do not remove or mutate; the paid path still needs it.
- Produces: new export `PUBLIC_BLOCK_LEAVES.setRipV1` (array of field names) and `projectRankingsClientPublicSetLeaderboard(targets)` now uses it instead of `BLOCK_LEAVES.setRipV1`. Signature unchanged: `(targets: Array) => Array`.

- [ ] **Step 1: Read the current file fully**

Read `frontend/lib/explore/rankingsClientProjection.mjs` end to end (it's short enough) to find `BASE_SCALAR_FIELDS`, `projectLeaves`, and confirm the exact current field list at line 123 before editing, since the investigation summary above is a paraphrase and must be checked against the live file.

- [ ] **Step 2: Write the failing test**

```js
import { projectRankingsClientPublicSetLeaderboard } from "./rankingsClientProjection.mjs";

const PAID_FIXTURE_SCORE = 87.3; // representative paid numeric fixture value
const target = {
  id: "swsh-ascended-heroes",
  setRipV1: {
    score: PAID_FIXTURE_SCORE,
    publicScore: 61.2,
    tier: "A",
    rank: 4,
    cohortSize: 42,
    rankable: true,
    methodologyVersion: "v11",
    familyScores: { loosePack: PAID_FIXTURE_SCORE, sleevedPack: 71.0 },
    displayFamilyScores: { loosePack: "87.3", sleevedPack: "71.0" },
    chaseAccessibility: { publicScore: 55.0, setRank: 4, setCohortSize: 42 },
  },
};

test("public set leaderboard projection excludes paid fields", () => {
  const [projected] = projectRankingsClientPublicSetLeaderboard([target]);

  expect(projected.setRipV1.familyScores).toBeUndefined();
  expect(projected.setRipV1.displayFamilyScores).toBeUndefined();
  expect(projected.setRipV1.chaseAccessibility).toBeUndefined();
  expect(projected.setRipV1.score).toBeUndefined();
  expect(JSON.stringify(projected)).not.toContain(String(PAID_FIXTURE_SCORE));

  expect(projected.setRipV1.publicScore).toBe(61.2);
  expect(projected.setRipV1.tier).toBe("A");
  expect(projected.setRipV1.rank).toBe(4);
  expect(projected.setRipV1.cohortSize).toBe(42);
  expect(projected.setRipV1.rankable).toBe(true);
  expect(projected.setRipV1.methodologyVersion).toBe("v11");
});
```

- [ ] **Step 3: Run test to verify it fails**

Run: `cd frontend && npx jest lib/explore/rankingsClientProjection.test.mjs -t "excludes paid fields"`
Expected: FAIL — `familyScores`/`displayFamilyScores`/`chaseAccessibility`/`score` are present because the public path currently reuses `BLOCK_LEAVES.setRipV1`.

- [ ] **Step 4: Add the narrow leaf list and use it**

In `rankingsClientProjection.mjs`, near `BLOCK_LEAVES` (line ~123), add:
```js
const PUBLIC_BLOCK_LEAVES = {
  setRipV1: ["publicScore", "tier", "rank", "cohortSize", "rankable", "methodologyVersion"],
};
```
Then change `projectRankingsClientPublicSetLeaderboard` (lines 229-237) from:
```js
const setRip = projectLeaves(target?.setRipV1, BLOCK_LEAVES.setRipV1);
```
to:
```js
const setRip = projectLeaves(target?.setRipV1, PUBLIC_BLOCK_LEAVES.setRipV1);
```
Export `PUBLIC_BLOCK_LEAVES` alongside the existing `BLOCK_LEAVES` export if `BLOCK_LEAVES` is currently exported (match its existing export style).

If the UI's public Set RIP headline needs additional non-sensitive identity/count fields beyond this list (check `ExploreTableClient`'s render of the public/basic row in Task 4 to confirm), add them to `PUBLIC_BLOCK_LEAVES.setRipV1` explicitly by name — never fall back to the full `BLOCK_LEAVES.setRipV1` list.

- [ ] **Step 5: Run test to verify it passes**

Run: `cd frontend && npx jest lib/explore/rankingsClientProjection.test.mjs`
Expected: PASS

- [ ] **Step 6: Commit**

```bash
git add frontend/lib/explore/rankingsClientProjection.mjs frontend/lib/explore/rankingsClientProjection.test.mjs
git commit -m "fix(rankings): stop leaking paid setRipV1 fields into public leaderboard projection

Co-Authored-By: Claude Sonnet 5 <noreply@anthropic.com>"
```

---

## Task 3: API-level test proving the anonymous lens route has no paid fixture values

**Files:**
- Test: `frontend/app/api/explore/rankings/lens/route.test.js` (check for an existing test file for this route first; extend it if present)

**Interfaces:**
- Consumes: the `GET` handler in `frontend/app/api/explore/rankings/lens/route.js` (lines 48-73 per investigation) and `projectSetRankingsLensTargets` from Task 2.
- Produces: a regression test that fails if the route ever again includes `familyScores`, `displayFamilyScores`, or `chaseAccessibility` for an anonymous caller.

- [ ] **Step 1: Read the route handler fully**

Read `frontend/app/api/explore/rankings/lens/route.js` to find how `access` is derived for an anonymous request (cookie/session absence) and how the route is invoked in existing tests (look for a `NextRequest`/`Request` construction pattern in any sibling `route.test.js` in `frontend/app/api/explore/`).

- [ ] **Step 2: Write the failing/target test**

```js
import { GET } from "./route.js";

const PAID_FIXTURE_SCORE = 87.3;

test("anonymous rankings lens response for sets contains no paid fixture values", async () => {
  // construct request exactly as sibling route tests do; no auth/session cookie set
  const request = new Request("http://localhost/api/explore/rankings/lens?lens=sets");
  const response = await GET(request);
  const body = await response.json();

  const serialized = JSON.stringify(body);
  expect(serialized).not.toContain("familyScores");
  expect(serialized).not.toContain("displayFamilyScores");
  expect(serialized).not.toContain("chaseAccessibility");
  expect(serialized).not.toContain(String(PAID_FIXTURE_SCORE));
});
```

Note: this test depends on whatever fixture/mock data source the route reads from in test mode — before finalizing, check how existing route tests in this directory stub the data layer (likely a mock of the sets data source), and inject a fixture target containing `PAID_FIXTURE_SCORE` in `familyScores`/`chaseAccessibility` the same way Task 2's test did, so the assertion is meaningful rather than vacuously true.

- [ ] **Step 3: Run test to verify current behavior**

Run: `cd frontend && npx jest app/api/explore/rankings/lens/route.test.js -t "no paid fixture values"`
Expected: with Task 2 already applied, this should PASS. If it fails, it means the route bypasses `projectSetRankingsLensTargets` somewhere else — trace that before proceeding (do not weaken the test).

- [ ] **Step 4: Commit**

```bash
git add frontend/app/api/explore/rankings/lens/route.test.js
git commit -m "test(rankings): assert anonymous lens response excludes paid fields

Co-Authored-By: Claude Sonnet 5 <noreply@anthropic.com>"
```

---

## Task 4: Locked vs Unavailable presentation in ExploreTableClient (desktop + mobile)

**Files:**
- Modify: `frontend/components/explore/ExploreTableClient.jsx`
- Read (do not modify unless reuse requires a small export change): `frontend/components/explore/RankedProductTablePrimitives.jsx`, `frontend/components/explore/ExplorerPlanLockPanel.jsx`
- Test: `frontend/components/explore/ExploreTableClient.contract.test.js` (existing file — extend it)

**Interfaces:**
- Consumes: `canViewProductRipIntelligence` prop (now correctly wired per Task 1) on `ExploreTableClient`; `PremiumMetricLock` from `RankedProductTablePrimitives.jsx` (or an equivalent cell-sized lock if `ExplorerPlanLockPanel.jsx` proves to be the better-fitting existing primitive — decide after reading both, do not build a third).
- Produces: `ChaseAccessibilityCell`, `ScoreCell`, `MobileScoreBlock`, and the product-family desktop cells/mobile snapshot block all accept an `entitled` (or reuse `canViewProductRipIntelligence`) boolean and render the lock primitive when `entitled === false`, regardless of whether the underlying value exists — and only fall through to the existing `Unavailable` branch when `entitled === true` and the value is genuinely null/missing.

- [ ] **Step 1: Read both existing lock components**

Read `RankedProductTablePrimitives.jsx:17-20` (`PremiumMetricLock`) and all of `ExplorerPlanLockPanel.jsx`. Pick the one whose visual weight fits an inline table cell (likely `PremiumMetricLock` — `ExplorerPlanLockPanel` sounds panel-scale per its name, confirm by reading its JSX/CSS classes). Record the decision in the commit message.

- [ ] **Step 2: Write the failing tests**

Add to `ExploreTableClient.contract.test.js` (match its existing render/mock setup exactly — read the file first for how targets/props are constructed):

```jsx
test("Financial/Chase/Collector desktop cells render a lock, not Unavailable, when not entitled", () => {
  const target = buildTarget({ setRipV1: { chaseAccessibility: null, familyScores: null } }); // use the file's existing target builder helper
  render(<ExploreTableClient targets={[target]} canViewProductRipIntelligence={false} />);

  expect(screen.queryByText("Unavailable")).not.toBeInTheDocument();
  expect(screen.getAllByLabelText(/Index Plus/i).length).toBeGreaterThan(0);
});

test("Financial/Chase/Collector desktop cells render Unavailable, not a lock, when entitled but value missing", () => {
  const target = buildTarget({ setRipV1: { chaseAccessibility: null } });
  render(<ExploreTableClient targets={[target]} canViewProductRipIntelligence={true} />);

  expect(screen.getAllByText("Unavailable").length).toBeGreaterThan(0);
  expect(screen.queryByLabelText(/Index Plus/i)).not.toBeInTheDocument();
});

test("mobile Financial/Chase/Collector blocks render a lock when not entitled", () => {
  const target = buildTarget({ setRipV1: { chaseAccessibility: null } });
  render(<ExploreTableClient targets={[target]} canViewProductRipIntelligence={false} viewportMode="mobile" />);
  // adjust the mobile-render trigger to however the component/tests actually switch to MobileScoreBlock — read the file to confirm (prop, matchMedia mock, or separate exported component)

  expect(screen.getAllByLabelText(/Index Plus/i).length).toBeGreaterThan(0);
});
```
Replace `buildTarget`/render helpers with whatever the existing test file already provides — do not invent a helper name that doesn't exist.

- [ ] **Step 3: Run tests to verify they fail**

Run: `cd frontend && npx jest components/explore/ExploreTableClient.contract.test.js -t "render a lock"`
Expected: FAIL — currently always renders "Unavailable" text regardless of entitlement.

- [ ] **Step 4: Implement the lock branch**

In `ExploreTableClient.jsx`:
1. Import the chosen lock primitive (e.g. `import { PremiumMetricLock } from "./RankedProductTablePrimitives";` — check it's exported, add `export` if it currently isn't).
2. In `ChaseAccessibilityCell` (135-147), `ScoreCell` (338-367), `MobileScoreBlock` (375-398), and the product-family desktop/mobile cells: before the existing null-check that renders `UNAVAILABLE_LABEL`, add an entitlement check:
```jsx
if (!entitled) {
  return <PremiumMetricLock />;
}
```
Thread `entitled` down from the `canViewProductRipIntelligence` prop already reaching `ExploreTableClient` — pass it explicitly into each cell/block component's props (read each call site to add the prop without changing unrelated prop ordering).
3. Only after that check does the existing `value == null → Unavailable` logic run.

- [ ] **Step 5: Run tests to verify they pass**

Run: `cd frontend && npx jest components/explore/ExploreTableClient.contract.test.js`
Expected: PASS, including all pre-existing tests in the file (run the whole file, not just the new test names, to catch regressions).

- [ ] **Step 6: Commit**

```bash
git add frontend/components/explore/ExploreTableClient.jsx frontend/components/explore/ExploreTableClient.contract.test.js
git commit -m "fix(rankings): render Index+ lock instead of Unavailable for non-entitled viewers

Co-Authored-By: Claude Sonnet 5 <noreply@anthropic.com>"
```

---

## Task 5: Auth downgrade test (Index+ → logout clears paid values without full reload)

**Files:**
- Test: `frontend/components/explore/RankingsLazyClient.authDowngrade.contract.test.jsx` (new file)

**Interfaces:**
- Consumes: `useRankingsAccess()` mock (from Task 1) with a mutable return value across a rerender, plus whatever `requestKey`/`authRevision` mechanism the codebase uses to force a refetch on auth change (read `useRankingsAccess` implementation and `RankingsLazyClient.jsx`'s data-fetch `useEffect`/SWR key to find the exact identity used — likely `requestKey` per the destructure at line 50).
- Produces: a regression test asserting that after mocking a logout (entitlement flips false, `requestKey` changes), a rerender shows locks, not stale paid values, without needing `window.location.reload()`.

- [ ] **Step 1: Read the data-fetch effect**

Read `RankingsLazyClient.jsx` fully to find how `requestKey` (or `authRevision`) is used to key the fetch (SWR key, `useEffect` dependency array, or manual cache-bust query param). This determines how the test should mock a session transition.

- [ ] **Step 2: Write the failing test**

```jsx
import { render, rerender, screen } from "@testing-library/react";
import RankingsLazyClient from "./RankingsLazyClient";

jest.mock("../../lib/access/useRankingsAccess");
import useRankingsAccess from "../../lib/access/useRankingsAccess";

test("logout clears paid values and shows locks without a full reload", async () => {
  useRankingsAccess.mockReturnValue({
    canViewRankingsIntelligence: true,
    canViewCardChaseEfficiency: true,
    authStatus: "authenticated",
    requestKey: "user-42",
  });
  const { rerender } = render(<RankingsLazyClient sets={[]} eras={[]} />);
  // fetch resolves with a paid fixture value present — await whatever loading indicator/act the component uses

  useRankingsAccess.mockReturnValue({
    canViewRankingsIntelligence: false,
    canViewCardChaseEfficiency: false,
    authStatus: "anonymous",
    requestKey: "anon-1",
  });
  rerender(<RankingsLazyClient sets={[]} eras={[]} />);

  expect(screen.queryByText("87.3")).not.toBeInTheDocument(); // representative paid fixture value from the mocked fetch
  expect(screen.getAllByLabelText(/Index Plus/i).length).toBeGreaterThan(0);
});
```
Fill in the actual fetch-mocking mechanism (likely `global.fetch` mock or a mocked data hook) by reading how `RankingsLazyClient.contract.test.jsx` (Task 1) or a sibling test already mocks the sets data source — reuse that exact pattern rather than inventing a new one.

- [ ] **Step 3: Run test to verify it fails**

Run: `cd frontend && npx jest components/explore/RankingsLazyClient.authDowngrade.contract.test.jsx`
Expected: FAIL if `requestKey` isn't wired as a refetch dependency, or if stale entitled data persists across the rerender.

- [ ] **Step 4: Fix the refetch/identity wiring if the test reveals a gap**

If the test fails because the fetch effect doesn't depend on `requestKey`, add `requestKey` (or `authStatus`) to the effect's dependency array in `RankingsLazyClient.jsx` so a session change triggers a real refetch (this is the "no full reload" repair — do not add a `window.location.reload()` call). If the test fails only because Tasks 1–4 aren't yet reflected (locks not rendering), confirm Tasks 1–4 are complete before debugging further here.

- [ ] **Step 5: Run test to verify it passes**

Run: `cd frontend && npx jest components/explore/RankingsLazyClient.authDowngrade.contract.test.jsx`
Expected: PASS

- [ ] **Step 6: Commit**

```bash
git add frontend/components/explore/RankingsLazyClient.authDowngrade.contract.test.jsx frontend/components/explore/RankingsLazyClient.jsx
git commit -m "test(rankings): verify auth downgrade clears paid values without full reload

Co-Authored-By: Claude Sonnet 5 <noreply@anthropic.com>"
```

---

## Task 6: Live-trace Set-page Chase for Ascended Heroes (diagnostic — no code changes)

**Files:** none modified. Output goes into the final report (Task 7 depends on this task's findings).

- [ ] **Step 1: Start backend and frontend per the documented prod-smoke setup**

Per `project_prod_smoke_setup` memory: backend on :8000, frontend on :3100. Confirm which Pokémon set id corresponds to "Ascended Heroes" (camelCase set slug per memory) by checking `backend/scripts/pokemon_snapshot_builders.py` or a sets lookup table/config for the exact `set_id` string.

- [ ] **Step 2: Hit the raw backend endpoint**

Run (adjust host/port and set id to what Step 1 found):
```bash
curl -s http://localhost:8000/tcgs/pokemon/sets/<setId>/rip/bootstrap | node -e "const d=JSON.parse(require('fs').readFileSync(0,'utf8')); console.log(JSON.stringify({ calculationRunId: d.calculationRunId, marketDate: d.marketDate, chaseAccessibilityPresentation: d.chaseAccessibilityPresentation, publicScore: d.chaseAccessibilityPresentation?.publicScore, modelScore: d.modelScore, setRank: d.chaseAccessibilityPresentation?.setRank, setCohortSize: d.chaseAccessibilityPresentation?.setCohortSize, cohortId: d.chaseAccessibilityPresentation?.cohortId }, null, 2))"
```
Record the full JSON output.

- [ ] **Step 3: Hit the Next.js proxy endpoint**

Run the equivalent `curl` against `http://localhost:3100/api/tcgs/pokemon/sets/<setId>/rip/bootstrap`. Diff its `chaseAccessibilityPresentation` field byte-for-byte against Step 2's. Any divergence or `undefined` here implicates `BOOTSTRAP_PROXY_STRIPS_CHASE`.

- [ ] **Step 4: Trace the normalizer output**

Write a one-off Node script in the scratchpad directory (not committed) that imports `frontend/lib/pokemon/pokemonSetRipBootstrapNormalizer.mjs` and calls its exported normalize function with Step 3's raw JSON as input. Log `chaseAccessibilityPresentation`, `canonical.chaseAccessibility`, and `canonicalSource.publicRipContractV11.chaseAccessibility`. Any divergence here implicates `NORMALIZER_STRIPS_CHASE`.

- [ ] **Step 5: Trace RipDecisionPage's actual received prop**

In a running browser (Playwright, headed or via `page.evaluate`), navigate to the Ascended Heroes set-page Rich RIP tab while logged in as an entitled user, and inspect via React DevTools or a temporary `console.log` (removed after, or gated behind a debug flag already in the codebase if one exists) what `chaseAccessibilityPresentation` actually reaches `RichRipSetTab`/`RipDecisionPage`. Compare its `calculationRunId` against whatever "currently selected Chase authority" run id the app treats as active (search for a "current chase run"/"active calculation run" config or endpoint referenced elsewhere in the set-page data layer).

- [ ] **Step 6: Classify root cause**

Using Steps 2-5's actual byte-diffs, assign exactly one of: `ACTIVE_SET_SNAPSHOT_MISSING_CHASE`, `BOOTSTRAP_PROXY_STRIPS_CHASE`, `STALE_INITIAL_BOOTSTRAP_CACHE`, `NORMALIZER_STRIPS_CHASE`, `UI_SELECTOR_STRIPS_CHASE`, `RUN_ID_MISMATCH_FAIL_CLOSED`, or `OTHER_EXACT_CAUSE` (with the exact cause named). Do not guess — the classification must cite which step first showed the value present vs. absent/mismatched.

No commit for this task (diagnostic only) — carry the classification into Task 7.

---

## Task 7: Repair Set-page Chase per Task 6's classification

**Files:** determined by Task 6's output; likely one of:
- If `ACTIVE_SET_SNAPSHOT_MISSING_CHASE`: a snapshot-rebuild candidate for Ascended Heroes only, validated against existing Chase authority — **do not activate/publish**, per Global Constraints.
- If `STALE_INITIAL_BOOTSTRAP_CACHE`: `frontend/lib/pokemon/pokemonSetRipBootstrapClient.mjs` (add a single no-store reconciliation fetch, no retry loop) and/or the component that consumes the initial seed (likely `RichRipSetTab.jsx` or its parent page).
- If `BOOTSTRAP_PROXY_STRIPS_CHASE`, `NORMALIZER_STRIPS_CHASE`, or `UI_SELECTOR_STRIPS_CHASE`: the exact file at that boundary only.

- [ ] **Step 1: Re-read the specific file(s) implicated by Task 6**

Do not touch any file outside the exact boundary Task 6 identified.

- [ ] **Step 2: Write a failing test that reproduces the exact defect using Task 6's captured fixture data**

Use the real (or minimally redacted) JSON captured in Task 6, Steps 2-5, as the test fixture — not synthetic data — so the test is provably tied to the observed bug.

- [ ] **Step 3: Run the test to verify it fails**

- [ ] **Step 4: Implement the minimal fix at that boundary**

If the classification is `STALE_INITIAL_BOOTSTRAP_CACHE`, implement exactly the Phase 7 spec's preferred repair: "when a valid initial Set RIP seed has ready Overall/Financial/Collector but missing Chase for an entitled user, perform ONE no-store client reconciliation. No retry loop. If fresh response contains Chase, replace seed. If fresh backend response still lacks Chase, preserve truthful Unavailable and report the publication-data blocker" — as a single conditional fetch, not a polling loop, not a global cache-policy change.

- [ ] **Step 5: Run the test to verify it passes**

- [ ] **Step 6: Commit**

```bash
git add <files from Step 1>
git commit -m "fix(pokemon-rip): repair set-page Chase Accessibility gap (<classification>)

Co-Authored-By: Claude Sonnet 5 <noreply@anthropic.com>"
```

If Task 6 concludes `ACTIVE_SET_SNAPSHOT_MISSING_CHASE`, stop after producing the validated candidate diff/report — do not commit an activation change, and flag this explicitly in the final report as blocked on explicit authorization.

---

## Task 8: All Products table width — stop exceeding viewport

**Files:**
- Modify: `frontend/components/explore/explore.module.css`
- Test: `frontend/components/explore/RankingsProductLensClient.contract.test.jsx` (check for existing responsive/width tests first; extend, or create if none exist)

**Interfaces:**
- Consumes: existing `.productsTable`, `.colProduct`, `.colFormat` class names — renamed values only, not renamed classes (other files reference these class names via CSS modules import; renaming the class key would break those imports).
- Produces: `.productsTable` no longer forces `width: max-content` past the viewport at 1440px.

- [ ] **Step 1: Read `RankingsProductLensClient.jsx` fully**

Confirm exactly which CSS-module classes it applies to the table/columns, and whether column widths are applied via `className={styles.colProduct}` or inline style overrides, before editing the CSS file blind.

- [ ] **Step 2: Write the failing test**

If Playwright/JSDOM-based width assertions aren't practical in this file's existing test style, use a CSS-module snapshot/contract test asserting the raw rule values instead (read the file's existing test conventions first — likely there's a `.contract.test` pattern elsewhere in this directory asserting CSS custom properties or class list membership; follow that pattern). At minimum:

```jsx
import fs from "fs";
import path from "path";

test("productsTable no longer forces width past 100%", () => {
  const css = fs.readFileSync(path.join(__dirname, "explore.module.css"), "utf8");
  const productsTableRule = css.match(/\.productsTable\s*{([^}]*)}/)[1];
  expect(productsTableRule).not.toMatch(/width:\s*max-content/);
});
```

- [ ] **Step 3: Run test to verify it fails**

Run: `cd frontend && npx jest components/explore/RankingsProductLensClient.contract.test.jsx -t "no longer forces width"`
Expected: FAIL against current `.productsTable { width: max-content; min-width: 100%; }`.

- [ ] **Step 4: Update the CSS**

In `explore.module.css`, change `.productsTable` (lines 117-120) from:
```css
.productsTable {
  width: max-content;
  min-width: 100%;
}
```
to:
```css
.productsTable {
  width: 100%;
  table-layout: fixed;
}
```
(matching `.table`'s existing `table-layout: fixed` per line 96-101, so column widths in Tasks 9-10 are respected rather than auto-sized).

- [ ] **Step 5: Run test to verify it passes**

- [ ] **Step 6: Commit**

```bash
git add frontend/components/explore/explore.module.css frontend/components/explore/RankingsProductLensClient.contract.test.jsx
git commit -m "fix(rankings): stop All Products table from exceeding viewport width

Co-Authored-By: Claude Sonnet 5 <noreply@anthropic.com>"
```

---

## Task 9: Match All Products Product/Set density to family view

**Files:**
- Modify: `frontend/components/explore/explore.module.css` (`.colProduct`, `.colFormat`)
- Read: the family-specific product ranking view's product-identity column CSS (find it — likely `CardChaseEfficiencyRankings.jsx` or another live family-view component using `RankedProductIdentity`; grep for `RankedProductIdentity` usages outside `RankingsProductLensClient.jsx` to find the reference width) to measure its actual practical column width.

**Interfaces:**
- Consumes: `RankedProductIdentity` (unchanged — no new component).
- Produces: `.colProduct` width reduced from `22rem` to match the family view's measured width; `.colFormat` reduced from `15rem` to a narrower value that still wraps readably.

- [ ] **Step 1: Grep for other `RankedProductIdentity` consumers**

Run `Grep` for `RankedProductIdentity` across `frontend/components/explore/`. For each live (non-archived) consumer besides `RankingsProductLensClient.jsx`, read its column CSS/width to find the actual practical width used for the identity cell in a family view.

- [ ] **Step 2: Write the failing test**

```jsx
test("colProduct width matches family view density (not the oversized 22rem)", () => {
  const css = fs.readFileSync(path.join(__dirname, "explore.module.css"), "utf8");
  const colProductRule = css.match(/\.colProduct\s*{([^}]*)}/)[1];
  expect(colProductRule).not.toMatch(/22rem/);
});
```
Add the specific target width once Step 1 determines the family view's actual value (e.g. `expect(colProductRule).toMatch(/14rem/)` — use the real measured number, not a guess).

- [ ] **Step 3: Run test to verify it fails**

- [ ] **Step 4: Update `.colProduct` and `.colFormat`**

Set `.colProduct` to the family view's measured width from Step 1. Reduce `.colFormat` from `15rem` to a value that keeps its content wrapping on 2 lines max at that width (verify visually in Task 11, don't just guess a number here — pick something conservative like `10rem` and let Task 11's responsive check confirm or adjust).

- [ ] **Step 5: Run test to verify it passes**

- [ ] **Step 6: Commit**

```bash
git add frontend/components/explore/explore.module.css frontend/components/explore/RankingsProductLensClient.contract.test.jsx
git commit -m "fix(rankings): narrow All Products identity/format columns to match family view density

Co-Authored-By: Claude Sonnet 5 <noreply@anthropic.com>"
```

---

## Task 10: Consolidate Units + Committed into "Opening Plan" if still too wide at 1440

**Files:**
- Modify: `frontend/components/explore/RankingsProductLensClient.jsx`, `frontend/components/explore/explore.module.css`
- Test: extend `frontend/components/explore/RankingsProductLensClient.contract.test.jsx`

**Interfaces:**
- Consumes: existing `units` and `committed` values already rendered by `.colUnits`/`.colCommitted` cells (read the render code to get exact value formatting, e.g. `$92.68`).
- Produces: (only if Task 8+9 still leave the table wider than 1440px in Task 11's manual check) a single `.colOpeningPlan` column rendering both values stacked, replacing the two separate columns. Values are not removed, only visually combined.

- [ ] **Step 1: Measure post-Task-9 width at 1440px**

After Tasks 8-9 land, manually render the All Products table (via `npm run dev` on :3100 or a Playwright screenshot) at 1440px viewport width and sum the column widths (`.colRank + .colProduct + .colOverall + .colFinancial + .colCollector + .colTier + .colChase + .colUnits + .colCommitted + .colRecover + .colPrice + .colEv + .colFormat` plus borders/padding) against 1440px. If it fits, skip this task's implementation steps and note "not needed" in the final report.

- [ ] **Step 2: If still too wide, write the failing test**

```jsx
test("Units and Committed are consolidated into a single Opening Plan column", () => {
  render(<RankingsProductLensClient products={[buildProduct({ units: 7, committed: 92.68 })]} />);
  const cell = screen.getByText(/7 units/i).closest("td");
  expect(cell).toHaveTextContent("7 units");
  expect(cell).toHaveTextContent("$92.68 committed");
  expect(screen.queryByTestId("colUnits")).not.toBeInTheDocument();
  expect(screen.queryByTestId("colCommitted")).not.toBeInTheDocument();
});
```
(Use whatever `buildProduct` fixture helper the existing test file already has; add `data-testid` attributes matching the old columns only if the file doesn't already have a way to query them, then remove those old testids once consolidated.)

- [ ] **Step 3: Run test to verify it fails**

- [ ] **Step 4: Implement the consolidated column**

In `RankingsProductLensClient.jsx`, replace the two `<td>` cells for units/committed with one:
```jsx
<td className={styles.colOpeningPlan}>
  <div>{units} units</div>
  <div>${committed.toFixed(2)} committed</div>
</td>
```
Remove the corresponding `<th>` split and merge into one "Opening Plan" header. In `explore.module.css`, remove `.colUnits`/`.colCommitted` (147-150) and add:
```css
.colOpeningPlan {
  width: 8rem;
}
```

- [ ] **Step 5: Run test to verify it passes, then re-measure 1440px width**

- [ ] **Step 6: Commit**

```bash
git add frontend/components/explore/RankingsProductLensClient.jsx frontend/components/explore/explore.module.css frontend/components/explore/RankingsProductLensClient.contract.test.jsx
git commit -m "fix(rankings): consolidate Units/Committed into Opening Plan column to fit 1440 desktop

Co-Authored-By: Claude Sonnet 5 <noreply@anthropic.com>"
```

---

## Task 11: Responsive + regression Playwright matrix

**Files:**
- Create: `frontend/tests/e2e/rankings-entitlement-and-density.spec.js` (path per whatever the repo's existing Playwright spec convention is — check `frontend/tests/e2e/` or similar for existing specs and match the directory/naming pattern exactly before creating a new one)

**Interfaces:**
- Consumes: running app at :3100 (frontend) / :8000 (backend) per `project_prod_smoke_setup` memory.
- Produces: one Playwright spec covering Phases 11-12's full matrix.

- [ ] **Step 1: Find the existing Playwright config/spec pattern**

Read `frontend/playwright.config.js` (or equivalent) and one existing spec file to match viewport-setting, base URL, and auth-mocking conventions already used in this repo.

- [ ] **Step 2: Write the test cases**

```js
const { test, expect } = require("@playwright/test");

test.describe("Set Rankings entitlement", () => {
  test("anonymous desktop: Set RIP visible, family/Financial/Chase/Collector locked", async ({ page }) => {
    await page.goto("http://localhost:3100/explore/rankings?lens=sets");
    await expect(page.getByText(/Unavailable/)).toHaveCount(0);
    await expect(page.getByLabel(/Index Plus/i).first()).toBeVisible();
  });

  test("anonymous mobile: same lock semantics", async ({ page }) => {
    await page.setViewportSize({ width: 412, height: 915 });
    await page.goto("http://localhost:3100/explore/rankings?lens=sets");
    await expect(page.getByLabel(/Index Plus/i).first()).toBeVisible();
  });

  // Index+ authenticated case: use whatever login/session-mocking helper existing specs already use
  test("logged-in Set RIP page shows Chase public score for Ascended Heroes", async ({ page }) => {
    await page.goto("http://localhost:3100/pokemon/sets/<setId>"); // exact route from Task 6's investigation
    await expect(page.getByText(/Unavailable/).filter({ hasText: "Chase" })).toHaveCount(0);
  });
});

test.describe("All Products layout", () => {
  for (const width of [1440, 1366, 768, 412]) {
    test(`All Products renders without page-level horizontal overflow at ${width}px`, async ({ page }) => {
      await page.setViewportSize({ width, height: 900 });
      await page.goto("http://localhost:3100/explore/rankings?lens=products");
      const bodyScrollWidth = await page.evaluate(() => document.body.scrollWidth);
      const viewportWidth = await page.evaluate(() => window.innerWidth);
      expect(bodyScrollWidth).toBeLessThanOrEqual(viewportWidth + 1);
    });
  }

  test("1440 desktop shows Format Strength without needing horizontal scroll", async ({ page }) => {
    await page.setViewportSize({ width: 1440, height: 900 });
    await page.goto("http://localhost:3100/explore/rankings?lens=products");
    await expect(page.getByText("Format Strength")).toBeInViewport();
  });
});
```
Fill in the exact `<setId>` route and any auth-mocking calls using the repo's real conventions found in Step 1 — this is a skeleton the executor must complete with real selectors after running it once and inspecting actual DOM.

- [ ] **Step 3: Run the spec against the running app**

Run: `cd frontend && npx playwright test tests/e2e/rankings-entitlement-and-density.spec.js`
Expected: all cases PASS after Tasks 1-10 are complete. Fix any selector mismatches found by actually running against the live app, not by guessing.

- [ ] **Step 4: Commit**

```bash
git add frontend/tests/e2e/rankings-entitlement-and-density.spec.js
git commit -m "test(rankings): add responsive/entitlement Playwright regression matrix

Co-Authored-By: Claude Sonnet 5 <noreply@anthropic.com>"
```

---

## Task 12: Full unit/contract suite + production build

**Files:** none (verification only).

- [ ] **Step 1: Run the full frontend contract/unit suite**

Run: `cd frontend && npx jest components/explore lib/explore lib/pokemon lib/access app/api/explore`
Expected: all PASS, including every pre-existing test untouched by this plan (regression check).

- [ ] **Step 2: Run the production frontend build**

Run: `cd frontend && npm run build`
Expected: build succeeds with no new type/lint errors introduced by Tasks 1-10.

- [ ] **Step 3: Record results for the final report**

Capture pass/fail counts and any warnings for inclusion in the 14-point final report the user requested. Do not deploy or publish anything — this task ends at a successful local production build.

- [ ] **Step 4: Commit (only if any build-fix changes were needed in Step 2)**

```bash
git add <any files touched to fix build errors>
git commit -m "fix(build): resolve production build errors from rankings entitlement fix

Co-Authored-By: Claude Sonnet 5 <noreply@anthropic.com>"
```

---

## Final Report Checklist (compile after Task 12)

1. Entitlement leak root cause → Task 1 finding (bare JSX shorthand at `RankingsLazyClient.jsx:278`).
2. Basic API fields removed → Task 2's `PUBLIC_BLOCK_LEAVES.setRipV1` diff vs. old `BLOCK_LEAVES.setRipV1`.
3. Desktop lock result → Task 4 + Task 11 desktop case.
4. Mobile lock result → Task 4 + Task 11 mobile case.
5. Logout transition result → Task 5.
6. Set-page Chase exact root cause → Task 6's classification.
7. Set-page Chase repair → Task 7's diff (or "blocked on authorization" if `ACTIVE_SET_SNAPSHOT_MISSING_CHASE`).
8. All Products width root cause → Task 8 (`.productsTable { width: max-content }`).
9. Product/Set density change → Task 9's measured target width.
10. Right-edge/cutoff result → Task 10 (or "not needed" if Task 10 Step 1 found it already fits).
11. Tests → Task 12 Step 1 output.
12. Browser matrix → Task 11 output.
13. Production build → Task 12 Step 2 output.
14. Files changed → `git diff --stat` against the branch's base.
