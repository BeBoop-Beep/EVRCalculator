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

const mobileBlockStart = css.indexOf("@media (max-width: 1199.98px) {");
const mobileBlock = css.slice(mobileBlockStart, css.indexOf("\n}", mobileBlockStart));

test("desktop keeps the hero and tabs as one sticky shell", () => {
  const shellStart = css.indexOf(".set-detail-context-shell {");
  const shell = css.slice(shellStart, css.indexOf("}", shellStart));
  assert.ok(shell.includes("position: sticky;"), "the desktop shell stays sticky");
  assert.ok(shell.includes("top: var(--app-header-offset, 64px);"), "pinned to the measured header height");
});

test("below 1200px the shell dissolves so the tabs can stick page-wide", () => {
  assert.ok(mobileBlockStart >= 0, "a mobile/tablet boundary block must exist");

  // A sticky element only travels inside its containing block. While the tabs
  // lived in the hero+tabs wrapper their sticky range was barely taller than
  // themselves, so they unstuck almost immediately. `display: contents`
  // dissolves that wrapper's box, promoting the tabs to children of the
  // full-height page container. It also removes the wrapper's own chrome and
  // its ::before wash, neither of which is generated for display:contents.
  assert.ok(mobileBlock.includes(".set-detail-context-shell {"), "the shell is restyled below desktop");
  assert.ok(
    /\.set-detail-context-shell \{[^}]*display: contents;/s.test(mobileBlock),
    "the shell must not generate a box below desktop"
  );
  assert.ok(mobileBlock.includes(".set-detail-sticky-tabs {"), "the tabs take over the sticky role");
  assert.ok(/\.set-detail-sticky-tabs \{[^}]*position: sticky;/s.test(mobileBlock));
  assert.ok(/\.set-detail-sticky-tabs \{[^}]*top: var\(--app-header-offset, 64px\);/s.test(mobileBlock));
});

test("desktop keeps the hero and tabs as one sticky shell that still generates a box", () => {
  const shellStart = css.indexOf(".set-detail-context-shell {");
  const shell = css.slice(shellStart, css.indexOf("}", shellStart));
  assert.ok(!shell.includes("display: contents"), "the desktop shell must keep its box");
  assert.ok(shell.includes("isolation: isolate;"), "the desktop shell keeps its stacking context");
});

test("the tabs sit below the global header and above page content", () => {
  const zIndex = /\.set-detail-sticky-tabs \{[^}]*z-index: (\d+);/s.exec(mobileBlock);
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
  assert.ok(
    mobileBlock.includes('.set-detail-glass-scope [id^="set-detail-"]'),
    "set-page anchor targets are offset below both bars"
  );
});

test("no ancestor of the tab bar is a scroll container", () => {
  // There is no jsdom here, so this walks the chain in source instead of in a
  // browser. The chain from [data-set-detail-sticky-tabs] up to <body> is:
  //   .set-detail-context-shell        (overflow-visible)
  //   .dashboard-container             (globals.css - no overflow declaration)
  //   contentWrapperClassName          (overflow-x-clip)   <- the one that mattered
  //   contentShellClassName            (widths and padding only)
  //   .min-w-0 pb-4 + desktopContentOffset
  //   breakpoint.rootFlat / rootGrid
  //   .space-y-5 ...
  //   <main> / app/layout.js <main class="app-canvas ...">
  //   <body class="flex flex-col min-h-screen">
  // `overflow-x: clip` is the one value that clips horizontally *without*
  // forcing the other axis to `auto`, so it does not become a scroll container
  // and sticky descendants keep resolving against the viewport.
  const scaffold = read("../Profile/PublicProfileLocalScaffold.js");
  assert.ok(!scaffold.includes("overflow-x-hidden"), "the content wrapper must not reintroduce overflow-x-hidden");
  assert.ok(scaffold.includes("overflow-x-clip"), "the content wrapper clips without scrolling");

  const dashboardStart = css.indexOf(".dashboard-container {");
  const dashboard = css.slice(dashboardStart, css.indexOf("}", dashboardStart));
  assert.ok(!dashboard.includes("overflow"), ".dashboard-container must not declare overflow");

  // The shell itself and the set-page root must stay non-clipping.
  assert.ok(
    client.includes('data-set-context-shell className="set-detail-context-shell overflow-visible'),
    "the shell stays overflow-visible"
  );

  // Nothing in globals.css may make html or body a scroll container either.
  const htmlBodyRules = [...css.matchAll(/(^|\n)(html|body)[^{]*\{([^}]*)\}/g)].map((match) => match[3]);
  for (const rule of htmlBodyRules) {
    assert.ok(!/\boverflow(-x|-y)?\s*:/.test(rule), "html/body must not declare overflow");
  }
});

test("the sticky offset helper measures whatever is actually pinned", () => {
  assert.ok(
    client.includes('document.querySelector("[data-set-detail-sticky-tabs]")') ||
      client.includes('"[data-set-detail-sticky-tabs]"'),
    "the helper must be able to measure the tab bar alone"
  );
  assert.ok(
    client.includes('window.matchMedia("(min-width: 1200px)")'),
    "the helper branches on the 1200px boundary, not on a user-agent guess"
  );
});
