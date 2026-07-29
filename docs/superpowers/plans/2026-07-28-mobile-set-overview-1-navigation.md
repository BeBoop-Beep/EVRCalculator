# Plan 1 — Navigation Destinations Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Remove the Tools destination from every user-facing navigation surface and add TCGs to the global mobile bottom navigation, without changing one pixel of navigation styling.

**Architecture:** Three navigation surfaces list destinations as data or as sibling `<Link>` elements built from one shared class recipe: the desktop primary nav in `Header.js`, the `items` array in `GlobalMobileBottomNav.js`, and the `NAV_COLUMNS` constant in `Footer.jsx`. Each change is a destination swap inside the existing recipe — no class strings, no wrappers, no layout containers are touched. The bottom nav's 5-column grid keeps five items, so its geometry is unchanged by construction.

**Tech Stack:** Next.js 15 App Router, React 19, Tailwind 3.4, `node:test` via `tsx`.

## Global Constraints

See [the plan index](2026-07-28-mobile-set-overview-INDEX.md#global-constraints). The ones that bind hardest here:

- Do not change any global navigation **styling**: height, width, positioning, background, blur, transparency, borders, shadows, typography, icon sizing, icon treatment, label sizing, spacing, padding, active-state styling, hover styling, safe-area styling, mobile search-field styling, logo styling, hamburger styling, fixed/sticky behaviour.
- The only permitted changes are destination/content changes.
- Bottom nav destinations become exactly: `Home, Explore, TCGs, Portfolio, Profile`.
- Insert TCGs using the **exact existing visual treatment**. Do not redesign the nav to accommodate it.
- Reuse the existing `TCGS_NAV_HREF` constant from `frontend/lib/navigation/tcgsNav.mjs` (`"/TCGs/Pokemon/Sets"`). Do not hardcode the path.
- Keep the `/tools` route itself. Only its navigation entries are removed.
- Tests: `node:test` via `tsx --test`, source-string contract assertions normalised with `.replace(/\r\n/g, "\n")`.

---

### Task 1: Add a frontend test script

Later tasks and plans need one command that runs the whole frontend suite. Right now `package.json` only has `test:movers-ticker`, which runs two files.

**Files:**
- Modify: `frontend/package.json:11`

- [ ] **Step 1: Add the script**

In `frontend/package.json`, inside `"scripts"`, add `test:frontend` immediately after the existing `test:movers-ticker` line:

```json
    "test:movers-ticker": "tsx --test components/explore/moversTickerSelector.test.mjs components/explore/MoversTickerViewport.test.jsx",
    "test:frontend": "tsx --test \"app/**/*.test.{js,mjs,jsx}\" \"components/**/*.test.{js,mjs,jsx}\" \"lib/**/*.test.{js,mjs,jsx}\" \"constants/**/*.test.{js,mjs,jsx}\""
```

- [ ] **Step 2: Run it and record the baseline**

Run: `cd frontend && npm run test:frontend`

Expected: the suite executes. Some tests already fail — that is fine and expected at this point. **Write the exact list of failing test names down**; every later task compares against this baseline, and you must not introduce a new failure.

Measured 2026-07-29 on `feature/more_ui_updates_sets_page` at `952df18`, before
any work in this phase: **729 tests, 708 pass, 21 fail**. The full list of the 21
is recorded in [the plan index](2026-07-28-mobile-set-overview-INDEX.md#recorded-baseline-measured-2026-07-29-before-any-work-in-this-phase).

---

### Task 2: Remove Tools from the desktop primary nav

**Files:**
- Modify: `frontend/components/Header.js:60-63` (delete `isToolsRouteActive`)
- Modify: `frontend/components/Header.js:170-177` (delete the Tools `<Link>`)
- Modify: `frontend/components/HeaderTcgsNav.contract.test.mjs:82-103`

**Interfaces:**
- Consumes: `TCGS_NAV_HREF`, `isTopNavRouteActive` from `@/lib/navigation/tcgsNav.mjs` (already imported at `Header.js:8`).
- Produces: a desktop primary nav containing exactly two siblings — Explore and TCGs — both built from `${navTabBase} inline-flex items-center justify-center`.

- [ ] **Step 1: Update the contract test to describe the intended state**

This is the failing test. In `frontend/components/HeaderTcgsNav.contract.test.mjs`, replace the whole `"TCGs shares the primary nav typography, spacing and visible focus ring"` test (lines 82–91) with:

```javascript
test("TCGs shares the primary nav typography, spacing and visible focus ring", () => {
  // Explore and TCGs are one set of siblings built from one class recipe.
  // Tools was removed as a destination; the recipe itself is unchanged.
  const tabs = primaryNav.match(/\$\{navTabBase\} inline-flex items-center justify-center/g) || [];
  assert.equal(tabs.length, 2, "Explore and TCGs must share the primary tab recipe");
  assert.ok(headerSource.includes("px-3 xl:px-4 py-2 text-sm xl:text-[15px] font-medium"), "primary nav typography and spacing are unchanged");
  assert.ok(
    headerSource.includes("focus-visible:outline-none focus-visible:ring-2 focus-visible:ring-[var(--accent)]"),
    "primary nav items must keep a visible keyboard focus treatment"
  );
});

test("Tools is gone from every header surface", () => {
  assert.ok(!headerSource.includes('href="/tools"'), "no header link may point at /tools");
  assert.ok(!headerSource.includes("isToolsRouteActive"), "the Tools active-route helper must be removed");
  assert.ok(!/>\s*Tools\s*</.test(headerSource), "no header element may render the Tools label");
});
```

Then in the `"the other primary nav destinations are unchanged"` test, delete this line (line 95):

```javascript
  assert.ok(primaryNav.includes('href="/tools"'));
```

- [ ] **Step 2: Run the test to verify it fails**

Run: `cd frontend && npx tsx --test components/HeaderTcgsNav.contract.test.mjs`

Expected: FAIL. `"TCGs shares the primary nav typography..."` reports `Expected values to be strictly equal: 3 !== 2`, and `"Tools is gone from every header surface"` reports the `href="/tools"` assertion failing.

- [ ] **Step 3: Remove the Tools active-route helper**

In `frontend/components/Header.js`, delete lines 60–63 entirely:

```javascript
  const isToolsRouteActive =
    isTopNavActive('/tools') ||
    isTopNavActive('/Learn') ||
    isTopNavActive('/learn');
```

Leave `isTcgsRouteActive` on line 59 and `isMyCollectionRouteActive` on line 64 exactly as they are.

- [ ] **Step 4: Remove the Tools link**

In `frontend/components/Header.js`, delete lines 170–177 entirely:

```jsx
              <Link
                href="/tools"
                className={`${navTabBase} inline-flex items-center justify-center ${
                  isToolsRouteActive ? navTabActive : navTabInactive
                }`}
              >
                Tools
              </Link>
```

The `<nav className="flex items-center gap-4 whitespace-nowrap">` block now holds the Explore `<Link>` followed directly by the comment and the TCGs `<Link>`. Do not change the `<nav>` classes, the `gap-4`, or the absolutely-positioned wrapper at line 160 — the nav is centred by that wrapper's `right-[calc(50%+260px)]` offset, which is independent of item count.

- [ ] **Step 5: Run the test to verify it passes**

Run: `cd frontend && npx tsx --test components/HeaderTcgsNav.contract.test.mjs`

Expected: PASS, all tests in the file.

---

### Task 3: Swap Tools for TCGs in the global mobile bottom nav

**Files:**
- Modify: `frontend/components/GlobalMobileBottomNav.js:71-85` (replace the tools icon with a tcgs icon)
- Modify: `frontend/components/GlobalMobileBottomNav.js:107-141` (replace the tools item with a tcgs item)
- Modify: `frontend/components/GlobalMobileBottomNav.js:1-7` (import `TCGS_NAV_HREF`)
- Create: `frontend/components/GlobalMobileBottomNav.contract.test.mjs`

**Interfaces:**
- Consumes: `TCGS_NAV_HREF` from `@/lib/navigation/tcgsNav.mjs`; the existing local `navItemIcon(id, isActive)` and `isPathMatch(pathname, targets, options)` helpers.
- Produces: an `items` array of exactly five entries in order `home, explore, tcgs, portfolio, profile`.

- [ ] **Step 1: Write the failing contract test**

Create `frontend/components/GlobalMobileBottomNav.contract.test.mjs`:

```javascript
import fs from "node:fs";
import path from "node:path";
import test from "node:test";
import assert from "node:assert/strict";
import { fileURLToPath } from "node:url";

import { TCGS_NAV_HREF } from "../lib/navigation/tcgsNav.mjs";

const here = path.dirname(fileURLToPath(import.meta.url));
const source = fs
  .readFileSync(path.resolve(here, "GlobalMobileBottomNav.js"), "utf8")
  .replace(/\r\n/g, "\n");

// The destinations live in one `items` useMemo; slice it so assertions about
// "the destinations" cannot be satisfied by markup elsewhere in the file.
const itemsBlock = source.slice(
  source.indexOf("const items = useMemo("),
  source.indexOf("if (shouldHide)")
);

test("the five destinations are Home, Explore, TCGs, Portfolio, Profile in order", () => {
  assert.ok(itemsBlock.length > 0, "the items block must be locatable");

  const ids = [...itemsBlock.matchAll(/id: "([a-z]+)"/g)].map((match) => match[1]);
  assert.deepEqual(ids, ["home", "explore", "tcgs", "portfolio", "profile"]);

  const labels = [...itemsBlock.matchAll(/label: "([^"]+)"/g)].map((match) => match[1]);
  assert.deepEqual(labels, ["Home", "Explore", "TCGs", "Portfolio", "Profile"]);
});

test("TCGs routes through the shared href constant and lights the whole /TCGs family", () => {
  assert.equal(TCGS_NAV_HREF, "/TCGs/Pokemon/Sets");
  assert.ok(itemsBlock.includes("href: TCGS_NAV_HREF"), "TCGs must not hardcode its path");
  assert.ok(
    source.includes('import { TCGS_NAV_HREF } from "@/lib/navigation/tcgsNav.mjs";'),
    "the shared constant is imported"
  );
  assert.ok(
    itemsBlock.includes('isActive: isPathMatch(normalizedPathname, ["/TCGs"], { caseInsensitive: true })'),
    "TCGs is active anywhere in the /TCGs route family"
  );
});

test("Tools is gone from the bottom navigation", () => {
  assert.ok(!source.includes('"/tools"'), "no bottom nav item may point at /tools");
  assert.ok(!source.includes('id === "tools"'), "the Tools icon branch must be removed");
  assert.ok(!/label: "Tools"/.test(source), "the Tools label must be removed");
});

test("the bottom navigation chrome is untouched", () => {
  // Geometry, surface, safe area and icon recipe are all frozen by the brief.
  assert.ok(
    source.includes(
      'className="fixed inset-x-0 bottom-0 z-[60] border-t border-[var(--border-subtle)] bg-[var(--surface-panel)]/95 backdrop-blur lg:hidden"'
    ),
    "the nav shell classes are unchanged"
  );
  assert.ok(
    source.includes('style={{ paddingBottom: "max(0.6rem, env(safe-area-inset-bottom))" }}'),
    "the safe-area padding is unchanged"
  );
  assert.ok(
    source.includes('className="mx-auto grid max-w-xl grid-cols-5 gap-1 px-3 pt-2"'),
    "the five-column grid is unchanged"
  );
  // Every icon uses one recipe; the new TCGs glyph must not deviate.
  const iconOpenings = source.match(
    /className=\{`h-5 w-5 \$\{activeClass\}`\} fill="none" stroke="currentColor" strokeWidth="1\.85" strokeLinecap="round" strokeLinejoin="round"/g
  ) || [];
  assert.equal(iconOpenings.length, 5, "home, explore, tcgs, portfolio and the profile fallback share one icon recipe");
});
```

- [ ] **Step 2: Run the test to verify it fails**

Run: `cd frontend && npx tsx --test components/GlobalMobileBottomNav.contract.test.mjs`

Expected: FAIL — `deepEqual` reports `["home","explore","portfolio","tools","profile"]` instead of the expected order, and the Tools assertions fail.

- [ ] **Step 3: Import the shared href constant**

In `frontend/components/GlobalMobileBottomNav.js`, add the import after the `useAuth` import on line 7:

```javascript
import { useAuth } from "@/components/AuthContext";
import { TCGS_NAV_HREF } from "@/lib/navigation/tcgsNav.mjs";
```

- [ ] **Step 4: Replace the tools icon with a tcgs icon**

In `frontend/components/GlobalMobileBottomNav.js`, replace the whole `if (id === "tools")` block (lines 71–85) with:

```jsx
  if (id === "tcgs") {
    return (
      <svg aria-hidden="true" viewBox="0 0 24 24" className={`h-5 w-5 ${activeClass}`} fill="none" stroke="currentColor" strokeWidth="1.85" strokeLinecap="round" strokeLinejoin="round">
        <rect x="3.25" y="6.5" width="11" height="14.5" rx="2" />
        <path d="M8.4 4.1 17.9 3l1.6 13.4" />
      </svg>
    );
  }
```

Two offset card outlines — the same 24×24 grid, `h-5 w-5` box, `1.85` stroke weight and round caps/joins as every other icon in this file. Do not change the stroke weight or the box size to make the glyph read better; the recipe is frozen.

- [ ] **Step 5: Replace the tools destination with the tcgs destination**

In `frontend/components/GlobalMobileBottomNav.js`, the `items` array currently orders `home, explore, portfolio, tools, profile`. Replace the `portfolio` and `tools` entries (lines 121–132) with `tcgs` then `portfolio`, so the final order is `home, explore, tcgs, portfolio, profile`:

```javascript
      {
        id: "tcgs",
        label: "TCGs",
        href: TCGS_NAV_HREF,
        isActive: isPathMatch(normalizedPathname, ["/TCGs"], { caseInsensitive: true }),
      },
      {
        id: "portfolio",
        label: "Portfolio",
        href: "/my-collection/collection",
        isActive: isPathMatch(normalizedPathname, ["/my-collection", "/my-portfolio", "/portfolio"], { caseInsensitive: true }),
      },
```

Leave the `home`, `explore` and `profile` entries and the `useMemo` dependency array `[normalizedPathname, profileHref]` exactly as they are.

- [ ] **Step 6: Run the test to verify it passes**

Run: `cd frontend && npx tsx --test components/GlobalMobileBottomNav.contract.test.mjs`

Expected: PASS, all four tests.

---

### Task 4: Remove Tools from the footer

**Files:**
- Modify: `frontend/components/Footer.jsx:10`
- Create: `frontend/components/Footer.contract.test.mjs`

- [ ] **Step 1: Write the failing contract test**

Create `frontend/components/Footer.contract.test.mjs`:

```javascript
import fs from "node:fs";
import path from "node:path";
import test from "node:test";
import assert from "node:assert/strict";
import { fileURLToPath } from "node:url";

const here = path.dirname(fileURLToPath(import.meta.url));
const source = fs
  .readFileSync(path.resolve(here, "Footer.jsx"), "utf8")
  .replace(/\r\n/g, "\n");

test("the footer Product column no longer offers Tools", () => {
  assert.ok(!source.includes('href: "/tools"'), "no footer link may point at /tools");
  assert.ok(!/label: "Tools"/.test(source), "the Tools label must be removed");
});

test("the other footer destinations are unchanged", () => {
  for (const href of ["/Explore", "/TCGs", "/my-collection", "/about", "/blog", "/careers", "/contact", "/terms", "/privacy", "/cookies"]) {
    assert.ok(source.includes(`href: "${href}"`), `${href} must survive`);
  }
});
```

- [ ] **Step 2: Run the test to verify it fails**

Run: `cd frontend && npx tsx --test components/Footer.contract.test.mjs`

Expected: FAIL on `"the footer Product column no longer offers Tools"`.

- [ ] **Step 3: Remove the Tools entry**

In `frontend/components/Footer.jsx`, delete line 10 from the `Product` column of `NAV_COLUMNS`:

```javascript
      { label: "Tools", href: "/tools" },
```

The `Product` column becomes Explore, TCGs, My Portfolio. Do not change the column headings, the column count, or any class strings.

- [ ] **Step 4: Run the test to verify it passes**

Run: `cd frontend && npx tsx --test components/Footer.contract.test.mjs`

Expected: PASS.

---

### Task 5: Sweep for surviving Tools navigation entries and verify

The brief requires Tools gone from "desktop navigation, hamburger menus, mobile navigation configuration, active-route configuration, and any other user-facing navigation surface." Tasks 2–4 covered the three known ones. This task proves there are no others.

**Files:**
- Read-only sweep, then: Modify whatever the sweep finds (expected: nothing).

- [ ] **Step 1: Sweep for navigation references to /tools**

Run:

```bash
cd frontend && npx tsx --test components/HeaderTcgsNav.contract.test.mjs components/GlobalMobileBottomNav.contract.test.mjs components/Footer.contract.test.mjs
```

Expected: PASS.

Then use the Grep tool (not `grep` via Bash) with pattern `"/tools"|label: "Tools"|>Tools<` over `frontend/components` and `frontend/app`, excluding `node_modules`.

Expected result: only `frontend/app/tools/` route files themselves. The route stays — the brief removes the *destination entries*, not the page.

- [ ] **Step 2: Fix anything the sweep found**

If the sweep finds a navigation entry in a file not covered by Tasks 2–4, remove that entry the same way and extend the nearest contract test to lock it out. If it finds nothing, record that in the commit message and move on.

- [ ] **Step 3: Run the full frontend suite**

Run: `cd frontend && npm run test:frontend`

Expected: PASS, except for any failures you recorded in the Task 1 Step 2 baseline. **No new failures.** If a test fails that passed in the baseline, stop and fix it before continuing.

- [ ] **Step 4: Visual verification that nav styling is unchanged**

Start the dev server (`cd frontend && npm run dev`) and confirm by eye at widths `390px` and `1366px`:

- The bottom nav bar has the same height, the same five evenly spaced items, the same icon size, the same label size, and the same active accent colour as before the change.
- The desktop header's Explore and TCGs tabs sit at the same typography and spacing; the nav block is still positioned by the `right-[calc(50%+260px)]` wrapper.
- Navigating to `/TCGs/Pokemon/Sets/<any-set>` lights the TCGs item in both the header and the bottom nav.

If the bottom bar's height changed, you edited a class string — revert it. Only the `items` array and the icon branch may change.

---

## Acceptance for this plan

Maps to brief acceptance criteria 2, 3, 4, 5, 6.

- [ ] Tools is absent from the desktop header, the mobile bottom nav, and the footer.
- [ ] TCGs appears in the mobile bottom nav using `TCGS_NAV_HREF` and the existing icon/label/active recipe.
- [ ] Bottom nav destinations are exactly Home, Explore, TCGs, Portfolio, Profile.
- [ ] No global navigation class string, geometry value, or style token was modified.
- [ ] `npm run test:frontend` shows no new failures against the Task 1 baseline.
