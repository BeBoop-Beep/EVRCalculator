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
const chartFrame = read("ChartFrame.jsx");

const mobileBlockStart = css.indexOf("@media (max-width: 1199.98px) {");
const mobileBlock = css.slice(mobileBlockStart, css.indexOf("\n}", mobileBlockStart));

// Correction 4. A large z-index does not escape a stacking context, a
// containing block, isolation, or ancestor overflow clipping. These lock the
// real ancestor chain of a chart tooltip on the set page:
//
//   .dashboard-container   relative isolate   <- the stacking context we land in
//     .set-detail-context-shell               <- isolation dropped below 1200px
//       .set-detail-sticky-tabs   z-index 40  <- what the tooltip must beat
//     #set-detail-overview
//       article.set-glass-surface             <- backdrop-filter dropped below 1200px
//         ChartFrame (position: relative, no z-index -> no stacking context)
//           .recharts-wrapper
//             .recharts-tooltip-wrapper

test("no ancestor of a chart tooltip clips it", () => {
  assert.ok(!chartFrame.includes("overflow-hidden"), "ChartFrame must not clip the tooltip");
  assert.ok(chartFrame.includes('["relative", className]'), "ChartFrame is relative with no z-index, so it makes no stacking context");

  const sectionCard = client.slice(client.indexOf("function SectionCard("), client.indexOf("// 02 · SET DESIRABILITY"));
  assert.ok(!sectionCard.includes("overflow-hidden"), "SectionCard must not clip the tooltip");
});

test("the glass card stops making a stacking context below desktop", () => {
  // Without this the tooltip's z-[9999] is scoped inside the card and the
  // pinned tab bar paints straight over it.
  assert.ok(
    /\.set-detail-glass-scope \.set-glass-surface,\s*\.set-detail-glass-scope \.set-glass-surface-dense \{[^}]*backdrop-filter: none;/s.test(mobileBlock),
    "the blur is dropped below 1200px so the card creates no stacking context"
  );
  assert.ok(
    /-webkit-backdrop-filter: none;/.test(mobileBlock),
    "the prefixed property must be dropped too or WebKit keeps the context"
  );
});

test("desktop keeps its glass blur", () => {
  const desktopRule = css.slice(
    css.indexOf(".set-detail-glass-scope .set-glass-surface,"),
    css.indexOf("}", css.indexOf(".set-detail-glass-scope .set-glass-surface,"))
  );
  assert.ok(desktopRule.includes("backdrop-filter: blur(var(--set-glass-blur))"), "the desktop treatment is unchanged");
});

test("the shell stops isolating below desktop so nothing is trapped inside it", () => {
  // The shell no longer generates a box at all below desktop, so it creates no
  // stacking context for a tooltip to be trapped in.
  assert.ok(/\.set-detail-context-shell \{[^}]*display: contents;/s.test(mobileBlock));
});

test("chart layering is never fixed by restyling the global navigation", () => {
  const bottomNav = read("../GlobalMobileBottomNav.js");
  const stickyNav = read("../StickyNav.js");
  assert.ok(bottomNav.includes("z-[60]"), "the global bottom nav keeps its z-index");
  assert.ok(stickyNav.includes("z-50"), "the global header keeps its z-index");
  // The tabs must stay strictly below both.
  const zIndex = /\.set-detail-sticky-tabs \{[^}]*z-index: (\d+);/s.exec(mobileBlock);
  assert.ok(Number(zIndex[1]) < 50, "the set tabs never compete with the global header");
});

test("page content clears the fixed bottom navigation", () => {
  // The bottom nav is `lg:hidden` (>=1024px) and the root layout pads the page
  // by its height below `lg`, so no chart or tooltip can sit underneath it.
  const layout = read("../../app/layout.js");
  assert.ok(
    layout.includes('pb-[calc(5.25rem+env(safe-area-inset-bottom))] lg:pb-0'),
    "the page reserves the bottom nav's height exactly where the nav is visible"
  );
  assert.ok(
    read("../GlobalMobileBottomNav.js").includes("lg:hidden"),
    "the nav hides at exactly the width the padding is removed"
  );
});
