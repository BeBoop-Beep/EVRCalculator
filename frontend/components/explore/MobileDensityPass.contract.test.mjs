import fs from "node:fs";
import path from "node:path";
import test from "node:test";
import assert from "node:assert/strict";
import { fileURLToPath } from "node:url";

const here = path.dirname(fileURLToPath(import.meta.url));
const read = (relativePath) =>
  fs.readFileSync(path.resolve(here, relativePath), "utf8").replace(/\r\n/g, "\n");

const client = read("RipStatisticsPageClient.jsx");
const packValue = read("PackValueHistoryChart.jsx");
const css = read("../../app/styles/globals.css");

const ticker = client.slice(
  client.indexOf("function MarketMoversTicker("),
  client.indexOf("function normalizePullRateAssumptions(")
);
const chaseRow = client.slice(
  client.indexOf("function TopMarketCardRow("),
  client.indexOf("function InlinePanelSkeleton(")
);
const chaseModule = client.slice(
  client.indexOf("function TopChaseCardsModule("),
  client.indexOf("function hasMarketMoverRows(")
);
const signalRow = client.slice(
  client.indexOf("function DecisionSignalRow("),
  client.indexOf("function DecisionSignalsCard(")
);

// --- 3. Movers strip -------------------------------------------------------

test("the movers strip loses its outer context card below desktop", () => {
  assert.ok(ticker.includes("max-desk:rounded-none max-desk:border-0 max-desk:bg-transparent max-desk:px-0"));
  // Desktop keeps the boxed strip.
  assert.ok(ticker.includes("rounded-xl border border-[var(--border-subtle)]"), "the desktop strip is unchanged");
});

test("the movers destination collapses to a compact control without losing its name", () => {
  assert.ok(ticker.includes('aria-label="View all movers"'), "the accessible name survives at every width");
  assert.ok(ticker.includes('className="max-desk:hidden">View all movers →'), "desktop keeps the full label");
  assert.ok(ticker.includes("hidden h-4 w-4 max-desk:block"), "a compact arrow replaces it below desktop");
  assert.ok(ticker.includes("max-desk:h-11"), "the compact control keeps a 44px touch target");
});

test("all ten movers, their rotation and their fields are untouched", () => {
  assert.ok(ticker.includes("items.map("), "every selected mover renders");
  assert.ok(!/\.slice\(0,\s*\d+\)/.test(ticker), "the strip must not truncate the selection");
  assert.ok(ticker.includes("MoversTickerViewport"), "rotation still belongs to the viewport");
  assert.ok(client.includes("const MOVERS_TICKER_FETCH_LIMIT = 10;"));
  // The chip still carries image, name, price and both movement figures.
  const chip = client.slice(client.indexOf("function MoversTickerItemChip("), client.indexOf("function MarketMoversTicker("));
  for (const field of ["imageUrl", "{name}", "value={price}", "changeAmount", "changePercent"]) {
    assert.ok(chip.includes(field), `${field} must survive in the mover chip`);
  }
});

test("duplicate movers cannot appear from the marquee copy", () => {
  // The duplicated sequence exists only for the seamless marquee and is hidden
  // from assistive tech and the tab order.
  assert.ok(ticker.includes('aria-hidden={ariaHidden ? "true" : undefined}'));
  assert.ok(ticker.includes("tabIndex={ariaHidden ? -1 : undefined}"));
  assert.ok(ticker.includes('key={`movers-ticker${ariaHidden ? ":dup" : ""}'), "keys keep the copies distinct");
});

// --- 6. Opening Profit vs Cost --------------------------------------------

test("the series labels were controls, so the control survives in compact form", () => {
  // Proven by inspection before removal: LegendToggle renders a <button> with
  // onClick + aria-pressed that gates whether each <Line> renders.
  const legendToggle = packValue.slice(packValue.indexOf("function LegendToggle("), packValue.indexOf("// ─── Main chart"));
  assert.ok(legendToggle.includes("<button"), "the legend entry is a real control");
  assert.ok(legendToggle.includes("aria-pressed={active}"));

  // Below desktop that control moved into the compact latest-values row.
  assert.ok(packValue.includes('data-series-toggle={entry.key}'));
  assert.ok(packValue.includes("aria-pressed={entry.show}"));
  for (const short of ['short: "EV"', 'short: "Typical"', 'short: "Upside"']) {
    assert.ok(packValue.includes(short), `${short} must be the compact label`);
  }
});

test("the verbose legend is not rendered twice below desktop", () => {
  assert.ok(
    packValue.includes('className="ml-auto flex min-w-0 flex-wrap items-center justify-end gap-2 text-[11px] max-desk:hidden"'),
    "the full-wording legend is desktop-only"
  );
});

test("all three series remain available and toggleable at every width", () => {
  const row = packValue.slice(packValue.indexOf("data-latest-values"), packValue.indexOf("<ChartFrame"));
  for (const key of ['key: "mean"', 'key: "median"', 'key: "p95"']) {
    assert.ok(row.includes(key), `${key} must remain`);
  }
  // A hidden series stays listed (dimmed) so it can be switched back on.
  assert.ok(row.includes("entry.available"), "availability, not visibility, decides what is listed");
  assert.ok(!row.includes("entry.show && entry.ratio"), "a hidden series must not be filtered out of the control");
  assert.ok(row.includes("opacity-45"), "a hidden series reads as off rather than disappearing");
});

test("the latest values themselves survive", () => {
  const row = packValue.slice(packValue.indexOf("data-latest-values"), packValue.indexOf("<ChartFrame"));
  assert.ok(row.includes("formatRatio(entry.ratio)"), "each series still shows its latest value");
  assert.ok(row.includes("chartData[latestDataIndex]?.meanCostRatio"));
  assert.ok(row.includes("chartData[latestDataIndex]?.medianCostRatio"));
  assert.ok(row.includes("chartData[latestDataIndex]?.p95CostRatio"));
});

test("OPvC supporting metrics render as compact rows below desktop", () => {
  assert.ok(client.includes("data-opening-metric-row"));
  const block = client.slice(
    client.indexOf("data-overview-opening-economics"),
    client.indexOf("</dl>", client.indexOf("data-overview-opening-economics"))
  );
  assert.ok(block.includes("grid-cols-[minmax(0,1fr)_auto]"), "label and value share one line");
  assert.ok(block.includes("desk:grid-cols-3"), "desktop keeps three columns");
  assert.ok(block.includes("desk:grid-rows-subgrid"), "desktop keeps its subgrid");
  // Nothing was dropped: label, value, trend indicator and the info tooltip.
  for (const kept of ["getFriendlyMetricLabel", "InfoPopover", "OpeningMetricTrendIndicator", "metric.value"]) {
    assert.ok(block.includes(kept), `${kept} must survive the compaction`);
  }
});

// --- 7. Top Chase ----------------------------------------------------------

test("the Top Chase outer list box is gone below desktop", () => {
  const content = client.slice(
    client.indexOf("function TopMarketCardsContent("),
    client.indexOf("function getTopCardDeltaEntries(")
  );
  assert.ok(content.includes("max-desk:rounded-none max-desk:border-0 max-desk:bg-transparent"));
  assert.ok(content.includes("set-glass-inner overflow-visible rounded-xl border"), "desktop keeps the box");
});

test("the compact sparkline is tall enough to read as a trend", () => {
  // ~48px of plot below desktop, inside the brief's 44-52px target. Date labels
  // sit outside this box, so this is graph height rather than row height.
  assert.ok(chaseRow.includes('className="h-12 w-full desk:h-14 desk:max-w-[13.75rem]"'));
  assert.ok(!chaseRow.includes("h-8 w-full desk:h-14"), "the flattened 32px plot is gone");
});

test("the reveal control is compact but keeps a descriptive accessible name", () => {
  assert.ok(chaseModule.includes("All ${Math.min(totalRows, 10)} →") || chaseModule.includes("All ${Math.min(totalRows, 10)}"));
  assert.ok(chaseModule.includes('aria-label={showAllChaseCards ? "Show fewer chase cards"'), "the accessible name stays descriptive");
  assert.ok(chaseModule.includes("aria-expanded={showAllChaseCards}"));
  assert.ok(chaseModule.includes("showAllChaseCards ? 10 : 5"), "five preview, ten on reveal");
});

test("chart interaction still cannot navigate", () => {
  const navStart = chaseRow.indexOf("<NavigationRegion");
  const navEnd = chaseRow.indexOf("</NavigationRegion>");
  assert.ok(!chaseRow.slice(navStart, navEnd).includes("CompactSparkline"), "the sparkline is not inside the anchor");
  assert.ok(chaseRow.indexOf("CompactSparkline") > navEnd, "the chart is a sibling of the link");
});

// --- 8. Decision Signals ---------------------------------------------------

// DecisionSignalRow is now the DESKTOP tree only: below 1200px Decision
// Signals renders DecisionSignalsCompactList instead (a condensed
// signal/score/tier/rank list with one shared interpretation region). The
// mobile guarantees are asserted against that list in
// MobileOverviewRefinementPass.contract.test.mjs; what stays pinned here is
// that the desktop row keeps its four-column grid and all of its fields.

test("the desktop decision signal row keeps its four-column grid", () => {
  assert.ok(signalRow.includes("desk:grid-cols-[minmax(0,1fr)_4.25rem_5.75rem_3.25rem]"));
  assert.ok(!signalRow.includes("sm:grid-cols-[minmax(0,1fr)_4.25rem_5.75rem_3.25rem]"), "the sm-scoped grid is gone");
});

test("every score, tier, rank and interpretation still renders", () => {
  for (const token of ["signal.label", "signal.scoreText", "signal.rankTier", "RankBadge", "summaryText", "parsedRank"]) {
    assert.ok(signalRow.includes(token), `${token} must remain`);
  }
  assert.ok(signalRow.includes("TrendIndicator"), "the score trend indicator survives");
});

test("below desktop Decision Signals is the compact structured list", () => {
  const card = client.slice(
    client.indexOf("function DecisionSignalsCard("),
    client.indexOf("// A Profit / Safety / Stability card.")
  );
  assert.ok(card.includes('<div className="desk:hidden">\n        <DecisionSignalsCompactList'));
  assert.ok(card.includes('<div className="hidden desk:block">'), "the row stack is desktop-only");
});

// --- 9 / 10. Containers and parity ----------------------------------------

test("the mobile feed still strips outer card chrome and keeps dividers", () => {
  const mobileBlockStart = css.indexOf("@media (max-width: 1199.98px) {");
  const mobileBlock = css.slice(mobileBlockStart, css.indexOf("\n}", mobileBlockStart));
  assert.ok(mobileBlock.includes("[data-mobile-feed] .set-glass-surface"));
  assert.ok(mobileBlock.includes("[data-mobile-feed] > * + * {"));
});

test("no chart is mounted twice and no mobile-only request is introduced", () => {
  assert.equal((packValue.match(/<ResponsiveContainer/g) || []).length, 1);
  const setValueChart = client.slice(
    client.indexOf("function SetValueLineChart("),
    client.indexOf("function SetValueTrendCard(")
  );
  assert.equal((setValueChart.match(/<ResponsiveContainer/g) || []).length, 1);
  // Width readings may not gate a fetch.
  assert.ok(!/isDesktop\w*\s*&&\s*fetch\(/.test(client));
  assert.ok(!/isDesktop\w*\s*\?\s*fetch\(/.test(client));
});
