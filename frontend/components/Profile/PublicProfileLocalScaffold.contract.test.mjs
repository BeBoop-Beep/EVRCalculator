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
    !/\$\{\s*desktopBreakpoint\s*\}/.test(source),
    "a breakpoint prefix must never be interpolated into a class string"
  );

  const preset = source.slice(
    source.indexOf("const SCAFFOLD_BREAKPOINTS = {"),
    source.indexOf("export default function PublicProfileLocalScaffold")
  );
  for (const key of [
    "rootGrid",
    "rootFlat",
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

test("the xl recipe preserves the existing consumers", () => {
  // my-collection and /u/[username] must not move to 1200px.
  const preset = source.slice(source.indexOf("  xl: {"), source.indexOf("  desk: {"));
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
  const deskStart = source.indexOf("  desk: {");
  const preset = source.slice(deskStart, source.indexOf("\n};", deskStart));
  assert.ok(preset.includes("desk:grid desk:grid-cols-[260px_minmax(0,1fr)] desk:items-start"));
  assert.ok(preset.includes("hidden desk:block"));
  assert.ok(preset.includes("desk:rounded-3xl"));
  assert.ok(preset.includes("desk:px-4 desk:py-4 2xl:px-5 2xl:py-5"));
  assert.ok(preset.includes("desk:px-0 desk:pt-0"));
  assert.ok(preset.includes("hidden lg:flex desk:hidden"));
  assert.ok(!/\bxl:/.test(preset), "the desk recipe must not carry a single xl: class");
});

test("every responsive branch reads from the resolved preset", () => {
  // A branch left hard-coded to xl: is exactly the 1200-1279px mixed band the
  // correction exists to prevent.
  for (const usage of [
    "breakpoint.rootGrid",
    "breakpoint.rootFlat",
    "breakpoint.asideBase",
    "breakpoint.asideAbsolute",
    "breakpoint.asideStatic",
    "breakpoint.desktopHeader",
    "breakpoint.toolsTrigger",
    "breakpoint.bottomNavHidden",
    "breakpoint.toolsPanelHidden",
  ]) {
    assert.ok(source.includes(usage), `${usage} must be consumed by the JSX`);
  }

  // Nothing outside the preset may hard-code a desktop visibility branch.
  // `2xl:` is a different, deliberate breakpoint and is not a violation, so the
  // patterns below are anchored to a non-alphanumeric boundary.
  const body = source.slice(source.indexOf("export default function PublicProfileLocalScaffold"));
  for (const stray of ["xl:hidden", "hidden xl:block", "xl:grid-cols-\\["]) {
    assert.ok(
      !new RegExp(`(^|[^0-9a-zA-Z])${stray}`).test(body),
      `${stray} must live in the preset, not in the component body`
    );
  }
});

test("sticky descendants are not trapped by an overflow scroll container", () => {
  // overflow-x: hidden computes overflow-y: auto, which makes the element a
  // scroll container and silently breaks position: sticky for everything
  // inside it. overflow-x: clip does not create a scroll container.
  assert.ok(!source.includes("overflow-x-hidden"), "overflow-x-hidden must not wrap page content");
  assert.ok(source.includes("overflow-x-clip"), "clip replaces hidden so sticky descendants still work");
});

test("the desktop header still renders only at desktop, inside the frame", () => {
  assert.ok(source.includes("{desktopHeader ? <div className={breakpoint.desktopHeader}>{desktopHeader}</div> : null}"));

  // /u/[username] passes a desktopHeader and it has always rendered *inside*
  // the bordered desktop frame. Collapsing to one wrapper must not lift it out.
  const wrapperStart = source.indexOf("<div className={contentWrapperClassName}>");
  assert.ok(wrapperStart >= 0, "the single content wrapper must be locatable");
  const wrapper = source.slice(wrapperStart, source.indexOf("</div>", source.indexOf("{children}")));
  assert.ok(wrapper.includes("{desktopHeader ?"), "the header renders inside the wrapper");
  assert.ok(
    wrapper.indexOf("{desktopHeader ?") < wrapper.indexOf("{children}"),
    "the header still precedes the page content"
  );
});

test("the floating tools button only exists where a tools panel exists", () => {
  // On the set page there is no tools panel, so the button had nothing to open
  // and fell through to a router.push that navigated the user off the page.
  // It must not render at all there - not hidden, not present-but-inert.
  const buttonStart = source.indexOf("<div className={floatingToolsContainerClass}>");
  assert.ok(buttonStart >= 0, "the floating container must still be locatable");
  const guardWindow = source.slice(Math.max(0, buttonStart - 160), buttonStart);
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

test("an empty section nav does not reserve a sticky band", () => {
  // In setDetailMode mobileBottomNavContent returns null, but the <nav> still
  // rendered with page-sticky-bar mb-2 px-3 py-2 - a ~2.5rem empty bar above
  // the content, which is the blank region under the global mobile header.
  assert.ok(source.includes("const resolvedBottomNavContent ="), "the nav content is resolved before rendering");
  assert.ok(source.includes("const shouldRenderBottomNav ="), "the nav renders only when it has content");
  assert.ok(!source.includes("{!hideBottomNav ? ("), "the old unconditional guard is gone");
});
