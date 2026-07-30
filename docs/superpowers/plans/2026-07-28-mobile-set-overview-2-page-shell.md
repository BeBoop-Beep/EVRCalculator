# Plan 2 — Page Shell Architecture Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Give the set page a correct mobile shell — one mount of the page tree, no dead blank band under the header, no obsolete floating filter button, and set-level tabs that actually stay stuck beneath the global header below 1200px.

**Architecture:** Four independent shell defects, fixed in dependency order. First the breakpoint tokens every later plan compiles against. Then `PublicProfileLocalScaffold` stops rendering `{children}` twice — the single highest-value change in the phase, because it halves chart mounts, removes duplicate DOM ids, and is a hard precondition for Plans 3 and 4. Then the two shell removals. Finally the sticky-tab rebuild, which depends on the single mount because it needs exactly one `[data-set-detail-sticky-tabs]` element and an ancestor chain free of scroll containers.

**Tech Stack:** Next.js 15 App Router, React 19, Tailwind 3.4, `node:test` via `tsx`.

## Global Constraints

See [the plan index](2026-07-28-mobile-set-overview-INDEX.md#global-constraints). The ones that bind hardest here:

- Desktop at `1200px+` must be **visually unchanged**. Every change in this plan is either behind a `max-desk:` / `@media (max-width: 1199.98px)` boundary, or is provably identical at `xl` (Tailwind `1280px`) and above.
- `PublicProfileLocalScaffold` is shared by three consumers: `RipStatisticsPageClient.jsx:12545`, `app/my-collection/layout.js:59`, and `app/u/[username]/layout.js:107`. The first passes `wrapDesktopContentInFrame={false}`; the other two use the default `true`. Both paths must be preserved exactly.
- Do not touch global top or bottom navigation styling.
- Tests: `node:test` via `tsx --test`. Normalise source strings with `.replace(/\r\n/g, "\n")` — `RipStatisticsPageClient.jsx` has mixed line endings.

---

### Task 1: Add the `tab` and `desk` breakpoint tokens

The brief's boundaries are 600px and 1200px. Tailwind's defaults are 640/768/1024/1280/1536 — neither boundary exists. Add two named screens so every later task writes `max-desk:` instead of hand-rolled arbitrary media queries, and so the boundary lives in one place.

**Files:**
- Modify: `frontend/tailwind.config.js:9-11` (add `screens` inside `theme.extend`)
- Create: `frontend/tailwind.breakpoints.contract.test.mjs`

**Interfaces:**
- Produces: Tailwind screens `tab` (`min-width: 600px`) and `desk` (`min-width: 1200px`), plus the auto-generated `max-tab` (`max-width: 599.98px`) and `max-desk` (`max-width: 1199.98px`) variants. Every later task in Plans 2–4 uses `max-desk:` for "mobile and tablet" and `tab:` for "tablet and up".

- [ ] **Step 1: Write the failing contract test**

Create `frontend/tailwind.breakpoints.contract.test.mjs`:

```javascript
import test from "node:test";
import assert from "node:assert/strict";

import config from "./tailwind.config.js";

test("the brief's two boundaries exist as named screens", () => {
  const screens = config?.theme?.extend?.screens || {};
  assert.equal(screens.tab, "600px", "tablet layout begins at 600px");
  assert.equal(screens.desk, "1200px", "the untouched desktop layout begins at 1200px");
});

test("the default Tailwind screens are not overridden", () => {
  // Adding screens under `extend` merges; replacing `theme.screens` would
  // silently retune every existing sm/md/lg/xl utility on every page.
  assert.equal(config?.theme?.screens, undefined, "theme.screens must stay unset so defaults survive");
});
```

- [ ] **Step 2: Run the test to verify it fails**

Run: `cd frontend && npx tsx --test tailwind.breakpoints.contract.test.mjs`

Expected: FAIL — `screens.tab` is `undefined`.

- [ ] **Step 3: Add the screens**

In `frontend/tailwind.config.js`, add a `screens` key as the first entry inside `theme.extend`, immediately before `colors`:

```javascript
  theme: {
    extend: {
      // The mobile/tablet Set Overview redesign works to two boundaries the
      // default scale does not have. These are additive: sm/md/lg/xl/2xl keep
      // their default values, so no existing utility changes meaning.
      //   below `tab`        -> phone            (0-599px)
      //   `tab` to `desk`    -> tablet app layout (600-1199px)
      //   `desk` and above   -> untouched desktop (1200px+)
      // Use `max-desk:` for "mobile and tablet" overrides.
      screens: {
        tab: "600px",
        desk: "1200px",
      },
      colors: {
```

- [ ] **Step 4: Run the test to verify it passes**

Run: `cd frontend && npx tsx --test tailwind.breakpoints.contract.test.mjs`

Expected: PASS.

- [ ] **Step 5: Prove the variants actually compile**

Add a throwaway `className="max-desk:hidden desk:block tab:flex"` to any element in `frontend/app/status/page.js`, run `cd frontend && npm run build`, and confirm the build succeeds and the generated CSS contains `@media (max-width: 1199.98px)` and `@media (min-width: 1200px)`. Then **remove the throwaway class** before committing.

**Verified on tailwindcss 3.4.17 (2026-07-29):** `max-desk:`, `max-tab:`, `desk:`
and `tab:` all generate from `extend.screens`; no explicit `{ max: ... }` screen
is needed. Note the emitted form:

| Class | Emitted media query |
|---|---|
| `desk:*` | `@media (min-width: 1200px)` |
| `max-desk:*` | `@media not all and (min-width: 1200px)` |
| `tab:*` | `@media (min-width: 600px)` |
| `max-tab:*` | `@media not all and (min-width: 599.98px)` → `(min-width: 600px)` complement |

`not all and (min-width: 1200px)` is the *exact* complement of `min-width: 1200px`,
so `max-desk:` and `desk:` cannot both apply and cannot both fail — there is no
sub-pixel gap. Hand-written CSS in `globals.css` uses the equivalent
`@media (max-width: 1199.98px)` form; do not expect the two strings to match when
grepping compiled output.

---

### Task 2: Mount the page content once instead of twice, on the right breakpoint

`PublicProfileLocalScaffold` holds **three** `{children}` expressions. Lines 454
and 457 are the two arms of the `wrapDesktopContentInFrame` ternary (so one of
them renders), and line 513 renders unconditionally alongside it inside
`px-3 pt-3 xl:hidden overflow-x-hidden min-w-0 sm:px-6`. `display: none` does not
unmount. The whole set page — every Recharts `ResponsiveContainer`, every
`ResizeObserver`, every `id="set-detail-*"` — exists twice in the DOM on every
render.

This is the fix that makes brief acceptance criterion 24 and parity spec §9
achievable at all.

**This task also carries Correction 1** (see the index). Collapsing to one
wrapper without fixing the breakpoint would leave a mixed band at `1200–1279px`,
because the set page's inner content switches at 1200 while the scaffold's own
gutters, visibility and spacing would still switch at 1280.

#### The architecture: a static breakpoint preset

Add a module-level `SCAFFOLD_BREAKPOINTS` map holding **two fully written-out
class recipes**, and a `desktopBreakpoint` prop that selects one. Every class
string appears verbatim in the source, so Tailwind's scanner finds them; no
variant prefix is ever concatenated at runtime.

- `desktopBreakpoint = "xl"` (default) — byte-identical behaviour for
  `app/my-collection/layout.js` and `app/u/[username]/layout.js`.
- `desktopBreakpoint = "desk"` — 1200px, used by `RipStatisticsPageClient` **only
  when `setDetailMode` is true**. (The same component also renders the non-set
  Explore page through this scaffold, and that must keep `xl`.)

The preset must cover every mobile/desktop branch in the file:
`rootGrid`, `asideBase`, `asideAbsolute`, `asideStatic`, `desktopHeader`,
`toolsTrigger`, `bottomNavHidden`, `toolsPanelHidden`, `contentFramed`,
`contentFlat`.

The two caller-owned strings switch at the call site, also written statically:
`desktopContentOffsetClassName` and `contentShellClassName`.

Padding in `contentFramed` is longhand (`px`/`py`, not `p-*`) so it reliably
beats the base `sm:px-6`.

**Files:**
- Modify: `frontend/components/Profile/PublicProfileLocalScaffold.js:449-514`
- Modify: `frontend/components/explore/RipStatisticsPageClient.jsx:10839-10845` (update the stale workaround comment)
- Create: `frontend/components/Profile/PublicProfileLocalScaffold.contract.test.mjs`

**Interfaces:**
- Consumes: the existing props `children`, `desktopHeader`, `wrapDesktopContentInFrame`, `contentShellClassName`, `desktopContentOffsetClassName`.
- Produces: exactly one `{children}` expression in the component's JSX. Later tasks and Plans 3–4 rely on `document.querySelectorAll("[data-set-detail-sticky-tabs]")` returning exactly one node.
- [ ] **Step 1: Write the failing contract test**

Create `frontend/components/Profile/PublicProfileLocalScaffold.contract.test.mjs`:

```javascript
import fs from "node:fs";
import path from "node:path";
import test from "node:test";
import assert from "node:assert/strict";
import { fileURLToPath } from "node:url";

const here = path.dirname(fileURLToPath(import.meta.url));
const source = fs
  .readFileSync(path.resolve(here, "PublicProfileLocalScaffold.js"), "utf8")
  .replace(/\r\n/g, "\n");

test("page content is mounted exactly once", () => {
  // Three {children} expressions used to exist: the two arms of the
  // wrapDesktopContentInFrame ternary plus an unconditional mobile copy, so
  // every consumer mounted the tree twice with one hidden by display:none.
  // Hiding is not unmounting: the hidden copy still measured, still observed,
  // still fetched. Responsive presentation must come from one wrapper's classes.
  const mounts = source.match(/\{children\}/g) || [];
  assert.equal(mounts.length, 1, "children must appear exactly once in the JSX");
});

test("no responsive branch renders a second copy of the tree", () => {
  assert.ok(!source.includes('<div className="hidden xl:block">{children}</div>'), "the flat desktop copy is gone");
  assert.ok(
    !source.includes('<div className="px-3 pt-3 xl:hidden overflow-x-hidden min-w-0 sm:px-6">{children}</div>'),
    "the mobile-only copy is gone"
  );
});

test("the scaffold breakpoint is a static preset, never a built-up prefix", () => {
  // Correction 1. Tailwind only emits classes it can find as literal strings.
  assert.ok(source.includes("const SCAFFOLD_BREAKPOINTS = {"), "both recipes live in one lookup");
  assert.ok(source.includes('desktopBreakpoint = "xl"'), "xl stays the default for every existing consumer");
  assert.ok(
    !/`[^`]*\$\{\s*desktopBreakpoint\s*\}[^`]*:/.test(source),
    "a breakpoint prefix must never be interpolated into a class string"
  );
  const preset = source.slice(
    source.indexOf("const SCAFFOLD_BREAKPOINTS = {"),
    source.indexOf("export default function PublicProfileLocalScaffold")
  );
  // Every branch the scaffold switches on must be present in both recipes.
  for (const key of [
    "rootGrid",
    "asideBase",
    "asideAbsolute",
    "asideStatic",
    "desktopHeader",
    "toolsTrigger",
    "bottomNavHidden",
    "toolsPanelHidden",
    "contentFramed",
    "contentFlat",
  ]) {
    assert.equal(
      (preset.match(new RegExp(`\\b${key}:`, "g")) || []).length,
      2,
      `${key} must be written out in both the xl and desk recipes`
    );
  }
});

test("the xl recipe preserves the existing consumers byte for byte", () => {
  // my-collection and /u/[username] must not move to 1200px.
  const preset = source.slice(source.indexOf("xl: {"), source.indexOf("desk: {"));
  assert.ok(preset.includes("xl:grid xl:grid-cols-[260px_minmax(0,1fr)] xl:items-start"));
  assert.ok(preset.includes("hidden xl:block"));
  assert.ok(preset.includes("xl:rounded-3xl"), "the desktop frame border radius survives");
  assert.ok(preset.includes("xl:bg-[var(--surface-page)]/70"), "the desktop frame surface survives");
  assert.ok(preset.includes("xl:px-4 xl:py-4 2xl:px-5 2xl:py-5"), "the frame padding is longhand so it wins over sm:px-6");
  assert.ok(preset.includes("xl:px-0 xl:pt-0"), "the flat variant drops the mobile gutter at desktop");
  assert.ok(preset.includes("hidden lg:flex xl:hidden"), "the tablet tools trigger keeps its band");
});

test("the desk recipe switches every branch at 1200px, with no leftover xl", () => {
  // The whole point of Correction 1: no mixed presentation in 1200-1279px.
  const deskStart = source.indexOf("desk: {");
  const preset = source.slice(deskStart, source.indexOf("};", deskStart));
  assert.ok(preset.includes("desk:grid desk:grid-cols-[260px_minmax(0,1fr)] desk:items-start"));
  assert.ok(preset.includes("hidden desk:block"));
  assert.ok(preset.includes("desk:rounded-3xl"));
  assert.ok(preset.includes("desk:px-4 desk:py-4 2xl:px-5 2xl:py-5"));
  assert.ok(preset.includes("desk:px-0 desk:pt-0"));
  assert.ok(preset.includes("hidden lg:flex desk:hidden"));
  assert.ok(!/\bxl:/.test(preset), "the desk recipe must not carry a single xl: class");
});

test("sticky descendants are not trapped by an overflow scroll container", () => {
  // overflow-x: hidden computes overflow-y: auto, which makes the element a
  // scroll container and silently breaks position: sticky for everything
  // inside it. overflow-x: clip does not create a scroll container.
  assert.ok(!source.includes("overflow-x-hidden"), "overflow-x-hidden must not wrap page content");
  assert.ok(source.includes("overflow-x-clip"), "clip replaces hidden so sticky descendants still work");
});

test("the desktop header still renders only at desktop", () => {
  assert.ok(source.includes("{desktopHeader ? <div className={breakpoint.desktopHeader}>{desktopHeader}</div> : null}"));
});
```

- [ ] **Step 2: Run the test to verify it fails**

Run: `cd frontend && npx tsx --test components/Profile/PublicProfileLocalScaffold.contract.test.mjs`

Expected: FAIL — `"page content is mounted exactly once"` reports `3 !== 1`.

- [ ] **Step 3: Add the static breakpoint preset**

In `frontend/components/Profile/PublicProfileLocalScaffold.js`, above the component,
add the two recipes. Both are written out in full — Tailwind's scanner only emits
classes it can find as literal strings, so a prefix must never be interpolated.

```javascript
// Correction 1: the Set Overview contract puts desktop at 1200px, but Tailwind's
// `xl` is 1280px. Moving the whole scaffold would retune My Collection and the
// public profile layouts, and leaving it alone would produce a mixed band from
// 1200-1279px where the set page's inner content is desktop while this shell is
// still mobile. So both recipes are written out in full and selected by prop.
//   `xl`   - 1280px, the historical behaviour. Default for every consumer.
//   `desk` - 1200px, opted into by RipStatisticsPageClient in setDetailMode.
// Nothing here concatenates a variant prefix; every string is statically
// discoverable.
const SCAFFOLD_BREAKPOINTS = {
  xl: {
    rootGrid: "xl:grid xl:grid-cols-[260px_minmax(0,1fr)] xl:items-start",
    rootFlat: "relative xl:block",
    asideBase: "hidden xl:block",
    asideAbsolute: "xl:absolute xl:inset-y-0 xl:left-0 xl:w-[260px] xl:min-w-[260px] xl:pl-6 xl:pr-4",
    asideStatic: "xl:self-stretch xl:w-[260px] xl:min-w-[260px] xl:pl-6 xl:pr-4",
    desktopHeader: "mb-6 hidden xl:block",
    toolsTrigger: "hidden lg:flex xl:hidden items-center mb-3",
    bottomNavHidden: "xl:hidden",
    toolsPanelHidden: "xl:hidden",
    // Padding is longhand (px/py, not p-*) so it reliably beats the base
    // sm:px-6. overflow-x-clip, not -hidden: `hidden` computes overflow-y:auto,
    // which makes this a scroll container and breaks position:sticky for the
    // set-level tabs inside it.
    contentFramed:
      "min-w-0 overflow-x-clip px-3 pt-3 sm:px-6 xl:overflow-x-visible xl:rounded-3xl xl:border xl:border-[var(--border-subtle)] xl:bg-[var(--surface-page)]/70 xl:px-4 xl:py-4 2xl:px-5 2xl:py-5",
    contentFlat: "min-w-0 overflow-x-clip px-3 pt-3 sm:px-6 xl:overflow-x-visible xl:px-0 xl:pt-0",
  },
  desk: {
    rootGrid: "desk:grid desk:grid-cols-[260px_minmax(0,1fr)] desk:items-start",
    rootFlat: "relative desk:block",
    asideBase: "hidden desk:block",
    asideAbsolute: "desk:absolute desk:inset-y-0 desk:left-0 desk:w-[260px] desk:min-w-[260px] desk:pl-6 desk:pr-4",
    asideStatic: "desk:self-stretch desk:w-[260px] desk:min-w-[260px] desk:pl-6 desk:pr-4",
    desktopHeader: "mb-6 hidden desk:block",
    toolsTrigger: "hidden lg:flex desk:hidden items-center mb-3",
    bottomNavHidden: "desk:hidden",
    toolsPanelHidden: "desk:hidden",
    contentFramed:
      "min-w-0 overflow-x-clip px-3 pt-3 sm:px-6 desk:overflow-x-visible desk:rounded-3xl desk:border desk:border-[var(--border-subtle)] desk:bg-[var(--surface-page)]/70 desk:px-4 desk:py-4 2xl:px-5 2xl:py-5",
    contentFlat: "min-w-0 overflow-x-clip px-3 pt-3 sm:px-6 desk:overflow-x-visible desk:px-0 desk:pt-0",
  },
};
```

Add the prop (defaulting to `"xl"`), resolve it once, and derive the wrapper:

```javascript
  desktopBreakpoint = "xl",
```

```javascript
  const breakpoint = SCAFFOLD_BREAKPOINTS[desktopBreakpoint] || SCAFFOLD_BREAKPOINTS.xl;
  const contentWrapperClassName = wrapDesktopContentInFrame
    ? breakpoint.contentFramed
    : breakpoint.contentFlat;
```

Then route every existing hard-coded branch through `breakpoint.*`:
the root grid/flat split, the aside, `mobileToolsPanelVisibilityClass`,
`floatingToolsContainerClass` and both `mobileBottomNavClassName` variants.

- [ ] **Step 4: Replace the double mount with the single mount**

Replace the whole block from `{wrapDesktopContentInFrame ? (` through the mobile
`{children}` div with:

```jsx
            {desktopHeader ? <div className={breakpoint.desktopHeader}>{desktopHeader}</div> : null}
            {isToolsFeatureEnabled && !useFloatingToolsOnTablet ? (
              <div className={breakpoint.toolsTrigger}>
                {/* ...existing button, unchanged... */}
              </div>
            ) : null}
            {!hideBottomNav ? (
              <nav
                aria-label={mode === "owner" ? "Owner collection section navigation" : "Profile section navigation"}
                className={mobileBottomNavClassName}
              >
                {/* ...existing content, unchanged... */}
              </nav>
            ) : null}
            <div className={contentWrapperClassName}>{children}</div>
```

The visual order is unchanged in both directions. At desktop the tools button and
the section nav are `display: none`, so desktop reads header → content exactly as
before. Below desktop the desktop header is `display: none`, so mobile reads
tools button → section nav → content exactly as before.

- [ ] **Step 4b: Opt the set page into `desk`**

In `frontend/components/explore/RipStatisticsPageClient.jsx`, at the
`PublicProfileLocalScaffold` call site, add and switch the caller-owned strings —
all written statically, `setDetailMode` only:

```jsx
        desktopBreakpoint={setDetailMode ? "desk" : "xl"}
        desktopContentOffsetClassName={setDetailMode ? "desk:flex desk:justify-center" : "xl:flex xl:justify-center"}
```

The non-set Explore page renders through the same component and must keep `xl`.

- [ ] **Step 5: Run the test to verify it passes**

Run: `cd frontend && npx tsx --test components/Profile/PublicProfileLocalScaffold.contract.test.mjs`

Expected: PASS, all five tests.

- [ ] **Step 6: Update the stale double-mount workaround comment**

In `frontend/components/explore/RipStatisticsPageClient.jsx`, replace the comment at lines 10839–10844 with:

```javascript
    // One sentinel now that PublicProfileLocalScaffold mounts the page content
    // once (it used to render a desktop `hidden xl:block` copy and a mobile
    // `xl:hidden` copy). querySelectorAll still handles the list because the
    // gate ref and the idempotent page advance make duplicate fires harmless
    // either way, and this needs no change if a future layout re-splits.
```

Leave the `querySelectorAll` logic itself alone — it is correct for one node and costs nothing.

- [ ] **Step 7: Verify no consumer regressed**

Run: `cd frontend && npm run build`

Expected: build succeeds.

Then start the dev server and confirm by eye at `1366px` that these three pages are pixel-identical to `main`:
- `/TCGs/Pokemon/Sets/<any-set>?tab=overview` (flat variant)
- `/my-collection/collection` (frame variant)
- `/u/<any-username>/collection` (frame variant)

Pay specific attention to the frame variant's horizontal padding — the longhand `xl:px-4 2xl:px-5` must produce the same gutter the old `xl:p-4 2xl:p-5` did.

- [ ] **Step 8: Verify the duplicate ids are gone**

In the browser console on `/TCGs/Pokemon/Sets/<any-set>?tab=overview`, run:

```javascript
document.querySelectorAll("#set-detail-overview").length
document.querySelectorAll("[data-set-detail-sticky-tabs]").length
document.querySelectorAll(".recharts-responsive-container").length
```

Expected: `1`, `1`, and a chart count that is **half** what `main` reports on the same page and width.

---

### Task 3: Remove the green floating filter button

The button at `PublicProfileLocalScaffold.js:560-571` is `bg-brand` (`#059669`), fixed bottom-right. It renders **unconditionally**, outside the `isToolsFeatureEnabled` guard that gates everything else about the tools panel. On the set page there is no tools panel (`mobileToolsPanelContent` is `null` and it is not a collection section), so `handleOpenCollectionTools` falls through to `router.push(\`${collectionHref}?tools=1\`)` — it navigates the user off the set page entirely.

**Files:**
- Modify: `frontend/components/Profile/PublicProfileLocalScaffold.js:560-573` (gate the container)
- Modify: `frontend/components/Profile/PublicProfileLocalScaffold.js:247-259` (drop the dead redirect branch)
- Modify: `frontend/components/Profile/PublicProfileLocalScaffold.contract.test.mjs`

- [ ] **Step 1: Add the failing assertions**

Append to `frontend/components/Profile/PublicProfileLocalScaffold.contract.test.mjs`:

```javascript
test("the floating tools button only exists where a tools panel exists", () => {
  // On the set page there is no tools panel, so the button had nothing to open
  // and fell through to a router.push that navigated the user off the page.
  // It must not render at all there - not hidden, not present-but-inert.
  const floatingStart = source.indexOf("const floatingToolsContainerClass");
  assert.ok(floatingStart >= 0, "the floating container class must still be derived");

  const buttonStart = source.indexOf("<div className={floatingToolsContainerClass}>");
  assert.ok(buttonStart >= 0, "the floating container must still be locatable");
  const guardWindow = source.slice(Math.max(0, buttonStart - 120), buttonStart);
  assert.ok(
    guardWindow.includes("isToolsFeatureEnabled ? ("),
    "the floating button must be gated on isToolsFeatureEnabled"
  );
});

test("opening the tools panel never navigates away", () => {
  assert.ok(
    !source.includes("router.push(`${collectionHref}?tools=1`"),
    "the dead ?tools=1 redirect branch must be removed"
  );
});
```

- [ ] **Step 2: Run the test to verify it fails**

Run: `cd frontend && npx tsx --test components/Profile/PublicProfileLocalScaffold.contract.test.mjs`

Expected: FAIL on both new tests.

- [ ] **Step 3: Gate the floating button**

In `frontend/components/Profile/PublicProfileLocalScaffold.js`, wrap the floating container in the same guard the panel already uses. Change line 560 from:

```jsx
      <div className={floatingToolsContainerClass}>
```

to:

```jsx
      {isToolsFeatureEnabled ? (
      <div className={floatingToolsContainerClass}>
```

and close it at the container's closing `</div>` (line 573 area) with:

```jsx
      </div>
      ) : null}
```

Keep the indentation of the inner button untouched so the diff stays readable.

- [ ] **Step 4: Remove the dead redirect branch**

Replace `handleOpenCollectionTools` (lines 247–259) with:

```javascript
  const handleOpenCollectionTools = () => {
    // The button only renders when a panel exists (isToolsFeatureEnabled), so
    // there is nothing left to fall through to.
    setIsToolsOpen((open) => !open);
  };
```

If `collectionHref` and `router` now have no other reader in this file, leave them — other handlers use them. Verify with the Grep tool before deleting anything else; do not remove an unused import you have not confirmed is unused.

- [ ] **Step 5: Run the test to verify it passes**

Run: `cd frontend && npx tsx --test components/Profile/PublicProfileLocalScaffold.contract.test.mjs`

Expected: PASS, all seven tests.

- [ ] **Step 6: Verify the button is gone from the set page and intact elsewhere**

At `390px` in the browser:
- `/TCGs/Pokemon/Sets/<any-set>?tab=overview` — no green circular button. Repeat for `?tab=cards`, `?tab=pull-rates`, `?tab=insights`.
- Tab through the page with the keyboard; the button must not appear in the focus order.
- `/my-collection/collection` — the green button is **still there** and still opens the collection tools panel.

---

### Task 4: Remove the blank band beneath the global mobile header

Two causes stack. First, the scaffold's root is `space-y-5 sm:space-y-6`. Second, on the set page `mobileBottomNavContent` is a function that returns `null` in `setDetailMode`, but the `<nav>` wrapper still renders with `page-sticky-bar mb-2 px-3 py-2` — an empty sticky bar roughly `2.5rem` tall plus its margin, sitting above the content.

**Files:**
- Modify: `frontend/components/Profile/PublicProfileLocalScaffold.js` (skip the nav when it has no content)
- Modify: `frontend/components/Profile/PublicProfileLocalScaffold.contract.test.mjs`

- [ ] **Step 1: Add the failing assertion**

Append to `frontend/components/Profile/PublicProfileLocalScaffold.contract.test.mjs`:

```javascript
test("an empty section nav does not reserve a sticky band", () => {
  // In setDetailMode mobileBottomNavContent returns null, but the <nav> still
  // rendered with page-sticky-bar mb-2 px-3 py-2 - a ~2.5rem empty bar above
  // the content, which is the blank region under the global mobile header.
  assert.ok(source.includes("const resolvedBottomNavContent ="), "the nav content is resolved before rendering");
  assert.ok(source.includes("const shouldRenderBottomNav ="), "the nav renders only when it has content");
  assert.ok(!source.includes("{!hideBottomNav ? ("), "the old unconditional guard is gone");
});
```

- [ ] **Step 2: Run the test to verify it fails**

Run: `cd frontend && npx tsx --test components/Profile/PublicProfileLocalScaffold.contract.test.mjs`

Expected: FAIL on `"an empty section nav does not reserve a sticky band"`.

- [ ] **Step 3: Resolve the nav content before deciding to render**

In `frontend/components/Profile/PublicProfileLocalScaffold.js`, immediately after the `contentWrapperClassName` declaration added in Task 2, add:

```javascript
  // Resolve first, then decide. A render function that returns null (the set
  // page does exactly this) used to still get an empty page-sticky-bar wrapper
  // with mb-2 px-3 py-2, which is the blank band under the global header.
  const resolvedBottomNavContent = mobileBottomNavContent
    ? (typeof mobileBottomNavContent === "function" ? mobileBottomNavContent() : mobileBottomNavContent)
    : null;
  const hasResolvedBottomNavContent =
    resolvedBottomNavContent !== null &&
    resolvedBottomNavContent !== undefined &&
    resolvedBottomNavContent !== false;
  const shouldRenderBottomNav =
    !hideBottomNav && (hasResolvedBottomNavContent || (!mobileBottomNavContent && mobileNavItems.length > 0));
```

- [ ] **Step 4: Use the resolved content in the JSX**

Replace the nav block written in Task 2 Step 4 with:

```jsx
            {shouldRenderBottomNav ? (
              <nav
                aria-label={mode === "owner" ? "Owner collection section navigation" : "Profile section navigation"}
                className={mobileBottomNavClassName}
              >
                {hasResolvedBottomNavContent ? (
                  resolvedBottomNavContent
                ) : (
                  <div className="flex min-w-max gap-2 pr-1">
                    {mobileNavItems.map((item) => {
                      const isActive = isSectionActive(item);

                      return (
                        <Link
                          key={item.href}
                          href={item.href}
                          aria-label={`Open ${item.label} section`}
                          aria-current={isActive ? "page" : undefined}
                          className={[
                            "inline-flex flex-none min-w-0 items-center gap-1.5 rounded-lg border px-3 py-2 text-xs font-medium transition-colors duration-150 ease-out",
                            isActive
                              ? "border-[var(--accent)] bg-[color:color-mix(in_srgb,var(--accent)_12%,transparent)] text-[var(--accent)]"
                              : "border-[var(--border-subtle)] text-[var(--text-secondary)] hover:bg-[var(--surface-hover)] hover:text-[var(--text-primary)]",
                          ].join(" ")}
                        >
                          <span className="max-[380px]:hidden">{item.icon}</span>
                          <span>{item.label}</span>
                        </Link>
                      );
                    })}
                  </div>
                )}
              </nav>
            ) : null}
```

`mobileNavItems` is `[]` on the set page (`mobileNavItems={[]}` at `RipStatisticsPageClient.jsx:12549`), so `shouldRenderBottomNav` is `false` there and the band disappears. On `/my-collection` and `/u/[username]` the items array is populated, so the nav renders exactly as before.

- [ ] **Step 5: Tighten the root spacing below desktop**

The scaffold root at line 402 is `space-y-5 sm:space-y-6`. With the empty nav gone, the remaining gap between the global header and the set hero comes from this. Change line 402 to:

```jsx
    <div className="space-y-5 max-desk:space-y-0 sm:space-y-6">
```

`space-y-*` only affects gaps *between* siblings of the root, of which there is one meaningful child below desktop, so this removes the residual band without touching desktop (`desk` is 1200px; `sm:space-y-6` still applies at 1200px+ because `max-desk` stops at 1199.98px).

- [ ] **Step 6: Run the test to verify it passes**

Run: `cd frontend && npx tsx --test components/Profile/PublicProfileLocalScaffold.contract.test.mjs`

Expected: PASS.

- [ ] **Step 7: Measure the gap**

At `390px` on `/TCGs/Pokemon/Sets/<any-set>?tab=overview`, in the browser console:

```javascript
const header = document.querySelector(".index-nav-shell");
const hero = document.querySelector("[data-set-context-header]");
hero.getBoundingClientRect().top - header.getBoundingClientRect().bottom;
```

Expected: a single intentional gutter of roughly `12px` (the wrapper's `pt-3`), not the `60px+` band present on `main`.

Also confirm `/my-collection/collection` at `390px` still shows its section nav pills above the content.

---

### Task 5: Separate the set-level tabs from the hero and make them stick

Today `.set-detail-context-shell` makes the hero **and** the tabs one sticky unit pinned at `--app-header-offset`. The brief wants the hero to scroll away below 1200px and the tabs alone to remain pinned beneath the unchanged global header.

The sticky was also silently dead on mobile before Task 2, because the mobile content wrapper's `overflow-x-hidden` made it a scroll container. Task 2's `overflow-x-clip` fixed that precondition.

**Files:**
- Modify: `frontend/app/styles/globals.css:680-685` and `:776-779`
- Modify: `frontend/components/explore/RipStatisticsPageClient.jsx:9127-9144` (`getExploreStickyOffset`)
- Create: `frontend/components/explore/SetDetailStickyTabs.contract.test.mjs`

**Interfaces:**
- Consumes: `--app-header-offset`, set on `document.documentElement` by `frontend/components/StickyNav.js:13` from the measured header height. Never hardcode `64px`.
- Produces: a `--set-tabs-offset` custom property on `:root` equal to `calc(var(--app-header-offset, 64px) + <tab bar height>)`, for use as `scroll-margin-top` by every anchor target on the set page.

- [ ] **Step 1: Write the failing contract test**

Create `frontend/components/explore/SetDetailStickyTabs.contract.test.mjs`:

```javascript
import fs from "node:fs";
import path from "node:path";
import test from "node:test";
import assert from "node:assert/strict";
import { fileURLToPath } from "node:url";

const here = path.dirname(fileURLToPath(import.meta.url));
const read = (relativePath) =>
  fs.readFileSync(path.resolve(here, relativePath), "utf8").replace(/\r\n/g, "\n");

const css = read("../../app/styles/globals.css");
const client = read("RipStatisticsPageClient.jsx");

test("desktop keeps the hero and tabs as one sticky shell", () => {
  const shellStart = css.indexOf(".set-detail-context-shell {");
  const shell = css.slice(shellStart, css.indexOf("}", shellStart));
  assert.ok(shell.includes("position: sticky;"), "the desktop shell stays sticky");
  assert.ok(shell.includes("top: var(--app-header-offset, 64px);"), "pinned to the measured header height");
});

test("below 1200px the hero scrolls away and only the tabs stick", () => {
  const blockStart = css.indexOf("@media (max-width: 1199.98px) {");
  assert.ok(blockStart >= 0, "a mobile/tablet boundary block must exist");
  const block = css.slice(blockStart, css.indexOf("\n}", blockStart));

  assert.ok(block.includes(".set-detail-context-shell {"), "the shell is restyled below desktop");
  assert.ok(block.includes("position: static;"), "the hero must not be pinned");
  assert.ok(block.includes("isolation: auto;"), "the shell must stop trapping the tabs in its stacking context");
  assert.ok(block.includes(".set-detail-sticky-tabs {"), "the tabs take over the sticky role");
  assert.ok(/\.set-detail-sticky-tabs \{[^}]*position: sticky;/s.test(block));
  assert.ok(/\.set-detail-sticky-tabs \{[^}]*top: var\(--app-header-offset, 64px\);/s.test(block));
});

test("the tabs sit below the global header and above page content", () => {
  const blockStart = css.indexOf("@media (max-width: 1199.98px) {");
  const block = css.slice(blockStart, css.indexOf("\n}", blockStart));
  const zIndex = /\.set-detail-sticky-tabs \{[^}]*z-index: (\d+);/s.exec(block);
  assert.ok(zIndex, "the tabs declare an explicit z-index below desktop");
  const value = Number(zIndex[1]);
  // StickyNav is z-50, GlobalMobileBottomNav is z-[60]. The tabs must never
  // paint over either, but must sit above ordinary page content.
  assert.ok(value >= 30 && value < 50, `tabs z-index must be in [30, 50) - found ${value}`);
});

test("anchors clear both bars", () => {
  assert.ok(css.includes("--set-tabs-offset:"), "a shared offset token exists");
  assert.ok(
    /--set-tabs-offset:\s*calc\(var\(--app-header-offset, 64px\)/.test(css),
    "the offset is derived from the measured header height, never hardcoded"
  );
});

test("the sticky offset helper measures whatever is actually pinned", () => {
  assert.ok(
    client.includes('document.querySelector("[data-set-detail-sticky-tabs]")'),
    "the helper must be able to measure the tab bar alone"
  );
  assert.ok(
    client.includes("window.matchMedia(\"(min-width: 1200px)\")"),
    "the helper branches on the 1200px boundary, not on a user-agent guess"
  );
});
```

- [ ] **Step 2: Run the test to verify it fails**

Run: `cd frontend && npx tsx --test components/explore/SetDetailStickyTabs.contract.test.mjs`

Expected: FAIL — the `@media (max-width: 1199.98px)` block does not exist.

- [ ] **Step 3: Add the shared offset token**

In `frontend/app/styles/globals.css`, in the `:root` block that already declares `--app-header-offset: 64px;` (line 88), add immediately after it:

```css
  /* Set-page anchors must clear the global header AND the sticky set tabs.
     The tab bar is min-h-10 (2.5rem) below md and min-h-11 (2.75rem) at md+,
     plus its 0.25rem padding; 3.25rem covers both with a little air. */
  --set-tabs-offset: calc(var(--app-header-offset, 64px) + 3.25rem);
```

- [ ] **Step 4: Add the mobile/tablet sticky boundary**

In `frontend/app/styles/globals.css`, immediately after the existing `.set-detail-sticky-tabs` rule (line 776–779), add:

```css
/* Below 1200px the hero is ordinary content that scrolls away and the tab bar
   alone pins beneath the unchanged global header. The shell must drop both its
   sticky position and its `isolation: isolate` - the isolation created a
   stacking context that trapped the tabs' z-index inside a now-static parent.
   Desktop (1200px+) keeps the hero and tabs travelling together and is
   untouched by this block. */
@media (max-width: 1199.98px) {
  .set-detail-context-shell {
    position: static;
    top: auto;
    z-index: auto;
    isolation: auto;
  }

  .set-detail-sticky-tabs {
    position: sticky;
    top: var(--app-header-offset, 64px);
    z-index: 40;
  }

  /* Programmatic section navigation and #hash links must land below both bars. */
  .set-detail-glass-scope [id^="set-detail-"] {
    scroll-margin-top: var(--set-tabs-offset);
  }
}
```

- [ ] **Step 5: Verify no ancestor is a scroll container**

The brief requires this check explicitly. In the browser at `390px` on the set page, run:

```javascript
let node = document.querySelector("[data-set-detail-sticky-tabs]").parentElement;
const offenders = [];
while (node && node !== document.body) {
  const s = getComputedStyle(node);
  for (const axis of ["overflow", "overflowX", "overflowY"]) {
    if (["hidden", "auto", "scroll"].includes(s[axis])) {
      offenders.push([node.className || node.tagName, axis, s[axis]]);
    }
  }
  node = node.parentElement;
}
console.table(offenders);
```

Expected: empty. `overflow: clip` is fine and will not appear. If anything reports `hidden`, `auto` or `scroll`, change that specific element to `clip` (for the x axis) or remove the rule — do not work around it by switching the tabs to `position: fixed`.

- [ ] **Step 6: Make the sticky-offset helper measure the right element**

In `frontend/components/explore/RipStatisticsPageClient.jsx`, replace `getExploreStickyOffset` (lines 9127–9144) with:

```javascript
  const getExploreStickyOffset = () => {
    if (typeof window === "undefined" || typeof document === "undefined") {
      return 0;
    }

    const rootStyles = window.getComputedStyle(document.documentElement);
    const headerOffsetRaw = rootStyles.getPropertyValue("--app-header-offset") || "64";
    const parsedHeaderOffset = Number.parseFloat(headerOffsetRaw);
    const headerOffset = Number.isFinite(parsedHeaderOffset) ? parsedHeaderOffset : 64;

    const subNav = document.querySelector('nav[aria-label="Profile section navigation"]');
    const subNavHeight = subNav instanceof HTMLElement ? subNav.offsetHeight : 0;

    // Measure whatever is actually pinned. At 1200px+ that is the whole set
    // context shell (hero + tabs travel together). Below 1200px the hero
    // scrolls away and only the tab bar stays, so measuring the shell would
    // over-scroll every anchor by the full hero height.
    const isDesktopComposition =
      typeof window.matchMedia === "function" && window.matchMedia("(min-width: 1200px)").matches;
    const pinnedElement = setDetailMode
      ? document.querySelector(isDesktopComposition ? "[data-set-context-shell]" : "[data-set-detail-sticky-tabs]")
      : null;
    const pinnedHeight = pinnedElement instanceof HTMLElement ? pinnedElement.offsetHeight : 0;

    return headerOffset + subNavHeight + pinnedHeight + 8;
  };
```

- [ ] **Step 7: Run the test to verify it passes**

Run: `cd frontend && npx tsx --test components/explore/SetDetailStickyTabs.contract.test.mjs`

Expected: PASS, all five tests.

- [ ] **Step 8: Verify sticky behaviour by hand**

At `390px`, `834px` and `1199px` on `/TCGs/Pokemon/Sets/<any-set>?tab=overview`:
- Scroll down. The hero scrolls out of view; the Overview/Cards/Pull Rates/Insights bar stops directly beneath the global header and stays there.
- The tab bar never paints over the global header, and the global bottom nav never paints under the tab bar.
- Switch tabs while scrolled down — the bar stays put and the new tab's content starts below it, not underneath it.
- Deep-link to `?tab=overview#set-detail-top-market-cards` — the heading lands below both bars, not behind them.

At `1200px` and `1366px`: the hero and tabs still travel together exactly as on `main`.

---

### Task 6: Full-suite and cross-width verification

**Files:**
- No production changes expected. Fix whatever this task uncovers.

- [ ] **Step 1: Run the whole suite**

Run: `cd frontend && npm run test:frontend`

Expected: no failures beyond the Plan 1 Task 1 baseline. `RipStatisticsSetLoad.contract.test.js` asserts on scaffold usage around line 2193 — if it broke, read it and decide whether the assertion described the old double-mount shape. If it did, update it to describe the single mount; if it described something else, you introduced a regression.

- [ ] **Step 2: Build**

Run: `cd frontend && npm run build`

Expected: succeeds with no new warnings.

- [ ] **Step 3: Width sweep**

At each of `320, 360, 390, 430, 480, 599, 600, 768, 834, 1024, 1199, 1200, 1366`, load `/TCGs/Pokemon/Sets/<any-set>?tab=overview` and confirm:
- No horizontal page scrolling (`document.documentElement.scrollWidth <= window.innerWidth`).
- No green floating button below 1200px.
- No blank band under the global header.
- The tab bar sticks below 1200px and travels with the hero at 1200px+.

Compare `1199px` against `1200px` side by side: the composition should flip cleanly with no half-applied state. Compare `599px` against `600px`: nothing should change yet — the `tab` breakpoint is not consumed until Plan 4.

- [ ] **Step 4: Confirm desktop is untouched**

Screenshot `/TCGs/Pokemon/Sets/<any-set>?tab=overview` at `1366px` on this branch and on `main`, and diff them. Expected: identical. Any difference is a defect in this plan, not an acceptable side effect.

---

## Acceptance for this plan

Maps to brief acceptance criteria 7, 8, 9, 10, 20, 21, 22, 24, and parity spec §9.

- [ ] `{children}` is mounted exactly once; `.recharts-responsive-container` count on the set page is halved.
- [ ] `#set-detail-overview` and `[data-set-detail-sticky-tabs]` each resolve to exactly one node.
- [ ] The green floating filter button is absent from all four set tabs, including the focus order, and still present on `/my-collection`.
- [ ] The blank band beneath the global mobile header is gone; the remaining gap is the intentional `pt-3` gutter.
- [ ] The set-level tabs are separated from the hero below 1200px and stay pinned while scrolling.
- [ ] No ancestor of the tab bar is a scroll container.
- [ ] Anchors land below both bars.
- [ ] Desktop at 1200px+ is pixel-identical to `main`.
- [ ] `npm run test:frontend` shows no new failures.
