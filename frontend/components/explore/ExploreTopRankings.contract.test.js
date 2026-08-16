const fs = require("fs");
const path = require("path");
const test = require("node:test");
const assert = require("node:assert/strict");
// Mixed CRLF/LF in this checkout — normalize before any multi-line anchor.
const read = (name) => fs.readFileSync(path.resolve(__dirname, name), "utf8").replace(/\r\n/g, "\n");
const source = read("ExploreTopRankings.jsx");
const sparkline = read("MarketSparkline.jsx");
const css = read("explore.module.css");

test("ranking uses the compact Market snapshot without another request", () => {
  assert.ok(source.includes("target?.currentSetValue"));
  assert.ok(source.includes("target?.windows?.[selectedWindowKey]"));
  assert.ok(source.includes("target?.trend"));
  assert.ok(!source.includes("fetch("));
});
test("shared timeframe semantics drive sparkline and both changes", () => {
  assert.ok(source.includes("<MarketWindowSelector"));
  assert.ok(source.includes("getStandardDeltaWindowDefinitions"));
  assert.ok(source.includes("<Sparkline points={trend}"));
  assert.ok(source.includes("movement?.amount"));
  assert.ok(source.includes("movement?.percent"));
  assert.ok(source.includes('selectedWindowKey === "lifetime" ? "LT"'));
});
test("rows use rank, set identity, trend, and set value hierarchy", () => {
  for (const label of ["Rank", "Set", "Trend", "Set value / change"]) assert.ok(source.includes(label));
  assert.ok(source.includes("<SetLogo"));
  assert.ok(source.includes("<Sparkline"));
  assert.ok(source.includes("currency.format(value)"));
});
test("rows open the existing set Market Set Value section", () => {
  assert.ok(source.includes('buildTcgSetHrefFromTarget(routeTarget, { tab: "market", section: "set-value" })'));
});
test("limited history is explicit and never fabricated", () => {
  // The "not enough points to draw" case now lives in the shared sparkline.
  assert.ok(sparkline.includes("numericPoints.length < 2"));
  assert.ok(sparkline.includes("emptyLabel"));
  assert.ok(source.includes("N/A"));
  assert.ok(source.includes("Since first available"));
});
test("mobile keeps the chart on its own full-width row below identity and value", () => {
  assert.ok(source.includes("MOBILE_PREVIEW_LIMIT = 5"));
  assert.ok(css.includes(".ladderRow > [data-ranking-chart]"));
  assert.ok(css.includes("grid-row: 2;"));
  assert.ok(css.includes("grid-column: 1 / -1;"));
  assert.ok(css.includes(".rankingHeader { display: none; }"));
});
