import assert from "node:assert/strict";
import fs from "node:fs";
import path from "node:path";
import test from "node:test";
import { fileURLToPath } from "node:url";

const here = path.dirname(fileURLToPath(import.meta.url));
const clientPath = path.join(here, "RipStatisticsPageClient.jsx");
const globalsPath = path.join(here, "../../app/styles/globals.css");
const scaffoldPath = path.join(here, "../Profile/PublicProfileLocalScaffold.js");
const source = fs.readFileSync(clientPath, "utf8").replace(/\r\n/g, "\n");
const globals = fs.readFileSync(globalsPath, "utf8").replace(/\r\n/g, "\n");
const scaffold = fs.readFileSync(scaffoldPath, "utf8").replace(/\r\n/g, "\n");

function shellSource() {
  const start = source.indexOf("<div data-set-context-shell");
  const end = source.indexOf('{setDetailTab === "overview" ? (', start);
  assert.ok(start >= 0 && end > start, "persistent set shell markers must exist");
  return source.slice(start, end);
}

test("set detail removes the sidebar and uses one invariant shell on every tab", () => {
  const shell = shellSource();
  assert.ok(source.includes("desktopSidebarContent={setDetailMode ? null : desktopSidebarContent}"));
  assert.ok(source.includes("hideDesktopSidebar={setDetailMode}"));
  assert.ok(scaffold.includes("{!hideDesktopSidebar ? <aside"));
  assert.equal((source.match(/data-set-context-shell/g) || []).length, 2); // selector lookup + rendered shell
  assert.equal((source.match(/data-set-context-header/g) || []).length, 1);
  assert.ok(!source.includes("data-set-summary-surface"));
  assert.ok(!source.includes("data-set-hero-grid"));
  assert.ok(shell.includes("data-set-detail-sticky-tabs"));
});

test("context row uses the 46/27/27 identity, value, and Opening RIP structure", () => {
  const shell = shellSource();
  assert.ok(shell.includes("md:grid-cols-[minmax(0,46fr)_minmax(0,27fr)_minmax(0,27fr)]"));
  assert.ok(shell.includes("data-compact-set-picker"));
  assert.ok(shell.includes("gap-4 px-4 py-2.5 sm:gap-6"));
  assert.ok(shell.includes("md:gap-7"));
  assert.ok(shell.includes("h-14 w-24"));
  assert.ok(shell.includes("sm:h-16 sm:w-28"));
  assert.ok(shell.includes("max-h-14 w-auto max-w-24 object-contain opacity-95"));
  assert.ok(shell.includes("text-lg font-bold"));
  assert.ok(shell.includes("md:text-xl"));
  assert.ok(shell.includes("text-xs font-medium leading-tight"));
  assert.ok(shell.includes("selectedName"));
  assert.ok(shell.includes("selectedTarget?.era"));
  assert.ok(shell.includes("Set Value"));
  assert.ok(shell.includes("Opening RIP"));
  assert.ok(shell.includes("displayedTopScore"));
  assert.ok(shell.includes("heroScoreSelection.tier"));
  assert.ok(shell.includes("heroScoreSelection.rank"));
  assert.ok(shell.includes("recommendationBadge"));
});

test("persistent shell contains only concise context and deep-link actions", () => {
  const shell = shellSource();
  assert.ok(shell.includes("onClick={handleViewSetValueTrend}"));
  assert.ok(shell.includes("View trend"));
  assert.ok(shell.includes('tab: "insights", section: "rip-score", targetId: "set-detail-rip-score"'));
  assert.ok(shell.includes("View verdict"));
  assert.ok(!shell.includes("<CompactSparkline"));
  assert.ok(!shell.includes("headerDecisionMetrics"));
  assert.ok(!shell.includes("Opening Outlook"));
  assert.ok(!shell.includes("<RipScoreModeToggle"));
});

test("set switching remains keyboard and pointer accessible in the persistent identity", () => {
  const shell = shellSource();
  assert.ok(shell.includes('aria-haspopup="listbox"'));
  assert.ok(shell.includes('aria-controls="compact-set-picker-list"'));
  assert.ok(shell.includes("switcherTargets.map("));
  assert.ok(shell.includes("onMouseEnter={() => handleTargetPrefetch"));
  assert.ok(shell.includes("onFocus={() => handleTargetPrefetch"));
  assert.ok(shell.includes("handleTargetIdChange"));
});

test("context row and tabs stick together below global navigation", () => {
  assert.match(globals, /\.set-detail-context-shell[\s\S]+position: sticky;[\s\S]+top: var\(--app-header-offset, 64px\);[\s\S]+z-index: 40;/);
  assert.match(globals, /\[data-set-context-header\][\s\S]+position: relative;[\s\S]+z-index: 2;[\s\S]+overflow: visible;/);
  assert.match(globals, /\.set-detail-sticky-tabs[\s\S]+position: relative;[\s\S]+z-index: 1;/);
  assert.ok(shellSource().includes("z-50 max-h-56"));
  assert.ok(source.includes('document.querySelector("[data-set-context-shell]")'));
  assert.ok(source.includes("headerOffset + subNavHeight + setContextShellHeight + 8"));
});

test("one fixed ambient artwork layer persists with a reduced-motion-safe low-cost glow", () => {
  assert.equal((source.match(/data-set-ambient-artwork/g) || []).length, 1);
  assert.ok(source.includes("selectedTarget?.hero_image_url || selectedTarget?.logo_image_url"));
  assert.match(source, /data-set-ambient-artwork[\s\S]+pointer-events-none fixed inset-0 -z-10/);
  assert.ok(source.includes("set-page-atmosphere pointer-events-none fixed"));
  assert.ok(source.includes("object-contain object-center"));
  assert.ok(source.includes("set-page-atmosphere-artwork"));
  assert.ok(source.includes("grayscale(0.3)_saturate(0.65)_blur(1px)"));
  assert.ok(source.includes("mask-image:linear-gradient"));
  assert.ok(!source.includes("data-set-ambient-artwork animate-"));
  assert.match(globals, /\.set-page-atmosphere-artwork[\s\S]+--set-artwork-y-offset: 20px;[\s\S]+opacity: 0\.055;[\s\S]+transform: translateY\(var\(--set-artwork-y-offset\)\);/);
  assert.match(globals, /@media \(min-width: 1024px\)[\s\S]+\.set-page-atmosphere-artwork[\s\S]+--set-artwork-y-offset: 28px;[\s\S]+opacity: 0\.07;/);
  assert.match(globals, /\.set-page-atmosphere::after[\s\S]+animation: set-page-atmosphere-breathe 14s ease-in-out infinite;/);
  assert.match(globals, /@keyframes set-page-atmosphere-breathe[\s\S]+opacity: 0\.34;[\s\S]+opacity: 0\.52;/);
  assert.match(globals, /@media \(prefers-reduced-motion: reduce\)[\s\S]+\.set-page-atmosphere::after[\s\S]+animation: none;/);
  assert.ok(!globals.includes("filter: brightness"));
  assert.ok(!source.includes("Paldean Fates"));
});

test("opening economics live in Overview Opening Profit vs Cost", () => {
  const start = source.indexOf('id="set-detail-overview-performance"');
  const end = source.indexOf('id="set-detail-top-market-cards"', start);
  const overview = source.slice(start, end);
  assert.ok(overview.includes('title="Opening Profit vs Cost"'));
  assert.ok(overview.includes("data-overview-opening-economics"));
  assert.ok(overview.includes("headerDecisionMetrics.map"));
  assert.ok(overview.includes("headerExpectedLossText"));
  assert.ok(
    overview.indexOf("<PackValueHistoryChart") < overview.indexOf("data-overview-opening-economics"),
    "the opening profit chart must render before its supporting metrics"
  );
  assert.ok(overview.includes("sm:grid-rows-[auto_auto_auto]"));
  assert.ok(overview.includes("sm:row-span-3 sm:grid-rows-subgrid"));
  assert.ok(overview.includes("md:whitespace-nowrap"));
  assert.ok(overview.includes('className="text-sm font-semibold tabular-nums'));
  assert.ok(overview.includes('<span aria-hidden="true">&nbsp;</span>'));
});

test("Insights verdict owns the score mode and complete static Opening Outlook", () => {
  const start = source.indexOf("function RipScoreBreakdownModule");
  const end = source.indexOf("function StatTile", start);
  const verdict = source.slice(start, end);
  assert.ok(verdict.includes("<RipScoreModeToggle"));
  assert.ok(verdict.includes("data-insights-opening-outlook"));
  assert.ok(verdict.includes("openingOutlook ||"));
  assert.ok(verdict.includes("It does not evaluate sealed-product appreciation"));
  assert.ok(!verdict.includes("<details"));
  assert.ok(!verdict.includes("Read full outlook"));
});

test("canonical hero selectors and premium chart treatment remain unchanged", () => {
  const metricsStart = source.indexOf("const headerDecisionMetrics = [");
  const metricsEnd = source.indexOf("const primaryDecisionMetricOrder", metricsStart);
  const metrics = source.slice(metricsStart, metricsEnd);
  assert.ok(metrics.includes("currentPackCost"));
  assert.ok(metrics.includes("averagePackValue"));
  assert.ok(metrics.includes("chanceToBeatPackCost"));
  assert.ok(!metrics.includes("averageHitValue"));
  assert.ok(!metrics.includes("chanceAtBigPull"));

  const compactStart = source.indexOf("function CompactSparkline");
  const compactEnd = source.indexOf("function normalizeSetValueHistoryPoints", compactStart);
  const compact = source.slice(compactStart, compactEnd);
  assert.ok(compact.includes('stopOpacity="0.12"'));
  assert.ok(compact.includes('strokeWidth="1.9"'));
  assert.ok(compact.includes("data-compact-sparkline-marker"));
  assert.ok(compact.includes("h-3 w-3"));
  assert.ok(compact.includes("h-1.5 w-1.5"));
});

test("overview charts and opening metric movement use restrained premium treatment", () => {
  const setValueChart = source.slice(
    source.indexOf("function SetValueLineChart"),
    source.indexOf("function SetValueTrendCard")
  );
  assert.ok(setValueChart.includes("<Area"));
  assert.ok(setValueChart.includes("baseValue={yMin}"));
  assert.ok(setValueChart.includes('stopOpacity="0.13"'));
  assert.ok(setValueChart.includes('stdDeviation="1.8"'));
  assert.ok(setValueChart.includes("strokeOpacity={0.16}"));

  const overviewStart = source.indexOf('title="Opening Profit vs Cost"');
  const overviewEnd = source.indexOf('id="set-detail-top-market-cards"', overviewStart);
  const overview = source.slice(overviewStart, overviewEnd);
  assert.ok(overview.includes("<OpeningMetricTrendIndicator"));
  assert.ok(overview.includes("neutral={metric.label === RIP_COPY.simpleMetrics.currentPackCost}"));
});
