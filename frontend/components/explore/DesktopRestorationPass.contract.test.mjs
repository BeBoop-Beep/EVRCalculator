import fs from "node:fs";
import path from "node:path";
import test from "node:test";
import assert from "node:assert/strict";
import { fileURLToPath } from "node:url";

// Final Set Overview pass: restore the desktop Top Chase table that the mobile
// composition work regressed, and make the minimal chart axis the shared
// treatment for Set Value Trend and Opening Profit vs Cost at every width and
// on every surface that renders them.

const here = path.dirname(fileURLToPath(import.meta.url));
const read = (rel) => fs.readFileSync(path.resolve(here, rel), "utf8").replace(/\r\n/g, "\n");

const client = read("RipStatisticsPageClient.jsx");
const packValue = read("PackValueHistoryChart.jsx");
const axis = read("minimalChartAxis.mjs");

const between = (source, startToken, endToken) => {
  const start = source.indexOf(startToken);
  assert.ok(start >= 0, `missing ${startToken}`);
  const end = source.indexOf(endToken, start);
  assert.ok(end > start, `missing ${endToken} after ${startToken}`);
  return source.slice(start, end);
};

const row = between(client, "function TopMarketCardRow(", "function InlinePanelSkeleton(");
const content = between(client, "function TopMarketCardsContent(", "function getTopCardDeltaEntries(");
const chaseModule = between(client, "function TopChaseCardsModule(", "function hasMarketMoverRows(");
const setValueChart = between(client, "function SetValueLineChart(", "function SetValueTrendCard(");
const setValueCard = between(client, "function SetValueTrendCard(", "function OverviewMetricTile(");
const compactList = between(client, "function DecisionSignalsCompactList(", "function DecisionSignalRow(");

const DESKTOP_COLUMNS = "[3rem_minmax(0,1fr)_minmax(9rem,14.5rem)_minmax(8rem,10rem)]";

// ===========================================================================
// DESKTOP TOP CHASE
// ===========================================================================

test("desktop column order is Rank, Card, Trend, Price / Change", () => {
  assert.ok(row.includes(`desk:grid-cols-${DESKTOP_COLUMNS}`), "the row declares the four-column table");
  const nav = row.indexOf("desk:col-span-2 desk:col-start-1");
  const trend = row.indexOf("desk:col-start-3 desk:row-start-1");
  const price = row.indexOf("desk:col-start-4 desk:row-start-1");
  assert.ok(nav >= 0 && trend >= 0 && price >= 0, "all four columns are placed explicitly");
  assert.ok(nav < trend && trend < price, "DOM order follows the visual column order");
});

test("the sparkline renders in the Trend column and never in Price / Change", () => {
  const chart = between(row, "data-row-chart", 'data-row-price="table"');
  assert.ok(chart.includes("desk:col-start-3"), "the chart is column three");
  assert.ok(chart.includes("<CompactSparkline"), "the plot is in the trend region");
  const price = row.slice(row.indexOf('data-row-price="table"'));
  assert.ok(!price.includes("CompactSparkline"), "no plot may render in the price column");
});

test("price and delta render in the final column and never in Trend", () => {
  const price = row.slice(row.indexOf('data-row-price="table"'));
  assert.ok(price.includes("desk:col-start-4"), "the price is column four");
  assert.ok(price.includes("{priceCell}"), "the price cell renders there");
  assert.ok(price.includes("desk:justify-self-end"), "the price is right-aligned in its column");
  const chart = between(row, "data-row-chart", 'data-row-price="table"');
  assert.ok(!chart.includes("MarketValueChange"), "no price or delta may render in the trend column");
  // Price, dollar movement, percentage movement and direction all still flow
  // through the one shared component.
  for (const prop of ["value={price}", "changeAmount={displayDeltaAmount}", "changePercent={displayDelta}"]) {
    assert.ok(row.includes(prop), `${prop} must remain`);
  }
  assert.ok(row.includes('variant="table-row"') && row.includes('alignment="right"'), "the table presentation is unchanged");
});

test("column headers use the same template as the row content", () => {
  assert.ok(content.includes(`grid-cols-${DESKTOP_COLUMNS}`), "the header shares the row's column template");
  assert.ok(content.includes("gap-3") && row.includes("desk:gap-3"), "header and row share the same gap");
  assert.ok(content.includes("px-3") && row.includes("desk:px-3"), "header and row share the same inset");
  const header = between(content, "<span>Rank</span>", "</div>");
  assert.ok(header.includes("<span>Card</span>"), "Card is second");
  assert.ok(header.indexOf("Trend") < header.indexOf("Price / Change"), "Trend is third, Price / Change fourth");
  assert.ok(content.includes("desk:grid"), "the header appears only where the desktop grid does");
});

test("desktop sparkline dimensions are restored", () => {
  // Recovered from f310ee8, the last commit before the mobile composition work:
  // h-14 (56px) capped at 13.75rem, centred, with the date pair beneath it.
  assert.ok(row.includes("desk:h-14 desk:max-w-[13.75rem]"), "restored plot box");
  assert.ok(row.includes("desk:items-center"), "restored centring in the trend column");
  assert.ok(row.includes("desk:max-w-[13.75rem] desk:text-[10px]"), "restored date pair width and size");
});

test("start and end dates sit at the lower corners of the sparkline", () => {
  const chart = between(row, "data-row-chart", 'data-row-price="table"');
  assert.ok(chart.includes("items-center justify-between"), "one date at each end");
  assert.ok(chart.includes("sparklinePoints[0]?.date"), "start date");
  assert.ok(chart.includes("sparklinePoints[sparklinePoints.length - 1]?.date"), "end date");
  assert.ok(chart.indexOf("<CompactSparkline") < chart.indexOf("sparklinePoints[0]?.date"), "the dates sit below the plot");
});

test("restored desktop row metrics", () => {
  assert.ok(row.includes("desk:px-3 desk:py-3"), "row padding");
  assert.ok(row.includes("desk:items-center"), "row vertical centring");
  assert.ok(row.includes("h-[4.875rem] w-14"), "desktop card image box");
  assert.ok(row.includes("desk:grid-cols-[3rem_minmax(0,1fr)]"), "rank column is 3rem, card column is fluid");
});

test("mobile row composition is unchanged by the restoration", () => {
  assert.ok(row.includes("grid-cols-[1.5rem_2.5rem_minmax(0,1fr)_auto]"), "the compact one-line grid survives");
  assert.ok(row.includes("max-desk:px-0"), "the flush mobile row survives");
  assert.ok(row.includes('data-row-price="compact"'), "the compact price stays on that line");
  assert.ok(row.includes("h-12 w-full desk:h-14"), "the 48px mobile plot survives");
  assert.ok(row.includes("min-h-11"), "the touch target survives");
  assert.ok(row.includes("desk:hidden"), "the small mobile card image survives");
});

test("all ten cards remain available and the reveal control is untouched", () => {
  assert.ok(chaseModule.includes("showAllChaseCards ? 10 : 5"), "5 preview, 10 on reveal");
  assert.ok(chaseModule.includes('showAllChaseCards ? "Show less" : "Show more"'), "the mobile reveal control is unchanged");
  assert.ok(chaseModule.includes("data-chase-reveal-chevron"), "its downward chevron is unchanged");
  assert.ok(chaseModule.includes('`View all chase cards (${Math.min(totalRows, 10)})`'), "desktop wording unchanged");
});

test("the chart stays outside the navigation anchor", () => {
  const navEnd = row.indexOf("</NavigationRegion>");
  assert.ok(navEnd > 0);
  assert.ok(row.indexOf("<CompactSparkline") > navEnd, "an arrow-key-driven chart is never nested in a link");
  assert.ok(!/\.stopPropagation\s*\(/.test(row), "no propagation patching");
  assert.ok(row.includes("href={rowHref}") || client.includes("href={rowHref}"), "card links are unchanged");
});

// ===========================================================================
// SET VALUE TREND
// ===========================================================================

test("Set Value hides the y-axis labels at every width", () => {
  assert.ok(setValueChart.includes("{...MINIMAL_Y_AXIS_PROPS}"), "shared hidden y-axis");
  assert.ok(!setValueChart.includes("width={58}"), "the old desktop gutter is gone");
  assert.ok(setValueChart.includes("domain={[yMin, yMax]}"), "the scale is still computed and applied");
  assert.ok(setValueChart.includes("buildCurrencyTicks(valuedPoints)"), "the domain still comes from the data");
});

test("Set Value shows only the first and final date", () => {
  assert.ok(setValueChart.includes("const edgeDateTicks = buildEdgeDateTicks(numericPoints, \"date\")"));
  assert.ok(setValueChart.includes("ticks={edgeDateTicks}"));
  assert.ok(setValueChart.includes("interval={0}"));
  assert.ok(!setValueChart.includes("formatCompactDay"), "the every-day tick formatter is gone");
  assert.ok(!client.includes("function formatCompactDay"), "and so is the now-dead helper");
});

test("Set Value has no duplicate endpoint-date presentation", () => {
  assert.ok(!setValueCard.includes('|| "Start"'));
  assert.ok(!setValueCard.includes('|| "Latest"'));
  assert.ok(!setValueCard.includes("formatShortDate(firstPoint?.date)"));
  assert.ok(!setValueCard.includes("formatShortDate(lastPoint?.date)"));
});

test("Set Value keeps every value, control and interaction", () => {
  assert.ok(setValueCard.includes("<MarketValueChange"), "current value, dollar and percent movement");
  assert.ok(setValueCard.includes("changeAmount={deltaAmount}") && setValueCard.includes("changePercent={deltaPercent}"));
  assert.ok(setValueCard.includes("<MarketWindowSelector"), "timeframe controls");
  assert.ok(setValueCard.includes("<SetValueScopeSelector"), "Checklist / Hits / Top 10");
  assert.ok(setValueCard.includes("onChange={setSelectedWindowKey}"), "timeframe switching still wired");
  assert.ok(setValueCard.includes("onChange={handleSelectedScopeChange}"), "scope switching still wired");
  assert.ok(setValueChart.includes('trigger={isCoarsePointer ? "click" : "hover"}'), "hover on mouse, tap on touch");
  assert.ok(setValueChart.includes("<SetValueTooltip />"), "the tooltip still carries date and exact value");
  assert.ok(setValueChart.includes("activeDot={{ r: 4.5"), "point selection is unchanged");
});

// ===========================================================================
// OPENING PROFIT VS COST — Overview AND Insights
// ===========================================================================

test("every rendering of Opening Profit vs Cost is the same component", () => {
  // One component, so Overview and Insights cannot drift into two styles.
  const mounts = client.match(/<PackValueHistoryChart/g) || [];
  assert.equal(mounts.length, 3, "Overview, Insights and Analysis all mount the one chart");
  assert.equal((packValue.match(/<ResponsiveContainer/g) || []).length, 1, "which itself mounts one plot");
});

test("Overview and Insights share axis visibility, endpoint dates and margins", () => {
  // None of these are branched on `variant` or `flush`, so the two surfaces get
  // identical axis behaviour by construction.
  for (const token of ["{...MINIMAL_Y_AXIS_PROPS}", "ticks={edgeDateTicks}", "getMinimalPlotMargin("]) {
    assert.ok(packValue.includes(token), `${token} must be present`);
    assert.ok(
      !new RegExp(`variant\\s*===\\s*["'][^"']*["']\\s*\\?[^\\n]*${token.replace(/[.*+?^${}()|[\]\\]/g, "\\$&")}`).test(packValue),
      `${token} must not be branched on the variant`
    );
  }
  assert.ok(!/flush \? .*MINIMAL_Y_AXIS_PROPS/.test(packValue), "axis config must not be branched on flush");
});

test("Opening Profit vs Cost hides y labels and shows only the first and final date", () => {
  assert.ok(packValue.includes("{...MINIMAL_Y_AXIS_PROPS}"));
  assert.ok(!packValue.includes("width={60}"), "the old 60px gutter is gone");
  assert.ok(packValue.includes("domain={[0, yAxisUpperBound]}"), "the scale is unchanged");
  assert.ok(packValue.includes("ticks={yAxisTicks}"), "gridline placement is unchanged");
  assert.ok(packValue.includes('buildEdgeDateTicks(chartData, "snapshotDate")'));
  assert.ok(packValue.includes("interval={0}"));
});

test("all three series, break-even and the summary metrics survive", () => {
  for (const key of ["meanCostRatio", "medianCostRatio", "p95CostRatio"]) {
    assert.ok(packValue.includes(`dataKey="${key}"`), `${key} series must remain`);
  }
  assert.ok(packValue.includes("<ReferenceLine"), "break-even line");
  assert.ok(packValue.includes("breakEvenLabel"), "break-even label");
  assert.ok(packValue.includes("1.0x Break-even"), "and its wording");
  assert.ok(packValue.includes("<MarketWindowSelector"), "timeframe controls");
  assert.ok(packValue.includes("<LegendToggle"), "legend / series identity");
  assert.ok(packValue.includes("data-latest-values"), "latest values");
  const econ = between(client, "data-overview-opening-economics", "</dl>");
  assert.ok(econ.includes("headerDecisionMetrics.map"), "Pack Market Price / Expected Value / Chance to Beat Pack Cost");
});

test("Opening Profit vs Cost keeps hover, tap and exact tooltip values", () => {
  assert.ok(packValue.includes('trigger={isCoarsePointer ? "click" : "hover"}'));
  assert.ok(packValue.includes("<TrendTooltip packCost={packCost} variant={variant} />"));
  assert.ok(packValue.includes("buildPerformanceTooltipRows(row, packCost, variant)"), "exact values still computed");
  assert.ok(packValue.includes("formatLongDate(row.snapshotDate)"), "the tooltip still names the date");
});

// ===========================================================================
// RESPONSIVE / REGRESSION PROTECTION
// ===========================================================================

test("Decision Signals are untouched by this pass", () => {
  assert.ok(compactList.includes("grid-cols-[minmax(0,1fr)_3rem_3.25rem_2.25rem]"), "the compact grid is as it was");
  assert.ok(compactList.includes('size="compact"'), "the tier pill is as it was");
  assert.ok(compactList.includes("setSelectedLabel((previous) => (previous === signal.label ? null : signal.label))"));
  assert.ok(compactList.includes("selectedSignal.detailSummary || selectedSignal.summary"));
  const card = between(client, "function DecisionSignalsCard(", "// A Profit / Safety / Stability card.");
  assert.ok(card.includes('<div className="hidden desk:block">'), "the desktop cards are still the desktop tree");
  const desktopRow = between(client, "function DecisionSignalRow(", "function DecisionSignalsCard(");
  assert.ok(desktopRow.includes("set-glass-inner"), "the desktop card surface is unchanged");
  assert.ok(desktopRow.includes("desk:grid-cols-[minmax(0,1fr)_4.25rem_5.75rem_3.25rem]"), "its desktop grid is unchanged");
});

test("no chart is mounted twice and no request path is added", () => {
  assert.equal((client.match(/<CompactSparkline/g) || []).length, 1);
  assert.equal((setValueChart.match(/<ResponsiveContainer/g) || []).length, 1);
  for (const [fetcher, expected] of [
    ["getPokemonSetOverview(", 1],
    ["getPokemonSetTopChase(", 1],
    ["getPokemonSetMarketMovers(", 1],
  ]) {
    assert.equal(
      (client.match(new RegExp(fetcher.replace(/[()]/g, "\\$&"), "g")) || []).length,
      expected,
      `${fetcher} must still have exactly ${expected} call site`
    );
  }
  assert.ok(!axis.includes("import "), "the shared axis module pulls in nothing");
  assert.ok(!axis.includes("fetch("), "and issues no request");
});

test("desktop changes begin at exactly 1200px", () => {
  // Every restored column is a `desk:` utility, and `desk` is 1200px.
  const tailwind = read("../../tailwind.config.js");
  assert.ok(/desk:\s*"1200px"/.test(tailwind), "the desk breakpoint is still 1200px");
  for (const token of ["desk:col-start-3", "desk:col-start-4", "desk:col-span-2", `desk:grid-cols-${DESKTOP_COLUMNS}`]) {
    assert.ok(row.includes(token), `${token} is gated at the desk breakpoint`);
  }
  assert.ok(!row.includes("lg:grid-cols-"), "nothing reintroduces a 1024px desktop boundary");
});
