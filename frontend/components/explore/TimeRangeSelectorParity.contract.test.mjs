import assert from "node:assert/strict";
import fs from "node:fs";
import path from "node:path";
import test from "node:test";
import { fileURLToPath } from "node:url";

const here = path.dirname(fileURLToPath(import.meta.url));
const read = (relativePath) =>
  fs.readFileSync(path.join(here, relativePath), "utf8").replace(/\r\n/g, "\n");

const pageSource = read("RipStatisticsPageClient.jsx");
const trendSource = read("PackValueHistoryChart.jsx");
const selectorSource = read("TimeRangeSelector.jsx");
const marketSelectorSource = read("MarketWindowSelector.jsx");

const between = (text, startToken, endToken) => {
  const start = text.indexOf(startToken);
  assert.ok(start >= 0, `missing ${startToken}`);
  const end = text.indexOf(endToken, start);
  assert.ok(end > start, `missing ${endToken} after ${startToken}`);
  return text.slice(start, end);
};

test("TimeRangeSelector owns one responsive width contract for mobile/tablet and desktop", () => {
  assert.ok(selectorSource.includes('fullWidth ? "w-full" : "w-full desk:w-auto"'));
  assert.ok(selectorSource.includes('"grid min-w-0 w-full grid-cols-7 gap-1.5"'));
  assert.ok(selectorSource.includes('"grid min-w-0 w-full grid-flow-col auto-cols-fr gap-1.5 desk:flex desk:w-auto desk:flex-wrap"'));
});

test("shared options include one visible LT label with Lifetime accessibility", () => {
  assert.ok(selectorSource.includes('{ key: "lifetime", desktopLabel: "LT", mobileLabel: "LT", ariaLabel: "Lifetime" }'));
  assert.ok(!selectorSource.includes('mobileLabel: "Lifetime"'));
  assert.ok(!selectorSource.includes('desktopLabel: "LIFETIME"'));
});

test("Set Value and Top Chase route through the shared MarketWindowSelector wrapper", () => {
  assert.ok(marketSelectorSource.includes("<TimeRangeSelector"));
  assert.ok(marketSelectorSource.includes('ariaLabel="Time range"'));
  assert.ok(marketSelectorSource.includes("fullWidth={fullWidth}"));

  const setValueCard = between(pageSource, "function SetValueTrendCard", "function OverviewMetricTile");
  const topChaseContent = between(pageSource, "function TopMarketCardsContent", "function getTopCardDeltaEntries");

  assert.ok(setValueCard.includes("<MarketWindowSelector"));
  assert.ok(topChaseContent.includes("<MarketWindowSelector"));
});

test("Opening Profit vs Cost uses shared TimeRangeSelector without compact visual props", () => {
  assert.ok(trendSource.includes('import MarketWindowSelector from "@/components/explore/MarketWindowSelector"'));
  const use = trendSource.slice(trendSource.indexOf("<MarketWindowSelector"), trendSource.indexOf("/>", trendSource.indexOf("<MarketWindowSelector")) + 2);
  assert.ok(!use.includes("fullWidth"));
  assert.ok(!use.includes("compact"));
  assert.ok(!use.includes("variant"));
  assert.ok(!use.includes("size"));
});
