const fs = require("fs");
const path = require("path");
const test = require("node:test");
const assert = require("node:assert/strict");
const source = fs.readFileSync(path.resolve(__dirname, "ExploreTopRankings.jsx"), "utf8");
const css = fs.readFileSync(path.resolve(__dirname, "explore.module.css"), "utf8");

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
  assert.ok(source.includes("points.length < 2"));
  assert.ok(source.includes("History unavailable"));
  assert.ok(source.includes("N/A"));
  assert.ok(source.includes("Since first available"));
});
test("mobile keeps the chart subordinate to identity and value", () => {
  assert.ok(source.includes("MOBILE_PREVIEW_LIMIT = 5"));
  assert.ok(css.includes(".ladderRow > :nth-child(3)"));
  assert.ok(css.includes("grid-column: 2 / 4"));
  assert.ok(css.includes(".rankingHeader { display: none; }"));
});
