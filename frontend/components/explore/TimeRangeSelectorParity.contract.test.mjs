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

const between = (text, startToken, endToken) => {
  const start = text.indexOf(startToken);
  assert.ok(start >= 0, `missing ${startToken}`);
  const end = text.indexOf(endToken, start);
  assert.ok(end > start, `missing ${endToken} after ${startToken}`);
  return text.slice(start, end);
};

test("TimeRangeSelector owns one responsive width contract for mobile/tablet and desktop", () => {
  assert.ok(selectorSource.includes('const wrapperClassName = ["w-full desk:w-auto", className].filter(Boolean).join(" ");'));
  assert.ok(selectorSource.includes('className="grid min-w-0 w-full grid-flow-col auto-cols-fr gap-1.5 desk:flex desk:w-auto desk:flex-wrap"'));
});

test("shared options include one visible LT label with Lifetime accessibility", () => {
  assert.ok(selectorSource.includes('{ key: "lifetime", desktopLabel: "LT", mobileLabel: "LT", ariaLabel: "Lifetime" }'));
  assert.ok(!selectorSource.includes('mobileLabel: "Lifetime"'));
  assert.ok(!selectorSource.includes('desktopLabel: "LIFETIME"'));
});

test("Set Value and Top Chase route through one page-level MarketWindowSelector wrapper", () => {
  const wrapper = between(pageSource, "function MarketWindowSelector", "function SetValueScopeSelector");

  assert.ok(wrapper.includes("<TimeRangeSelector"));
  assert.ok(wrapper.includes('ariaLabel="Time range"'));
  assert.ok(!wrapper.includes("grid-flow-col auto-cols-fr"));
  assert.ok(!wrapper.includes("max-desk:min-h-11"));

  const setValueCard = between(pageSource, "function SetValueTrendCard", "function OverviewMetricTile");
  const topChaseContent = between(pageSource, "function TopMarketCardsContent", "function getTopCardDeltaEntries");

  assert.ok(setValueCard.includes("<MarketWindowSelector"));
  assert.ok(topChaseContent.includes("<MarketWindowSelector"));
});

test("Opening Profit vs Cost uses shared TimeRangeSelector without compact visual props", () => {
  const trendSelector = between(trendSource, "function MarketWindowSelector", "function PackValueHistoryChart");

  assert.ok(trendSelector.includes("<TimeRangeSelector"));
  assert.ok(trendSelector.includes('ariaLabel="Opening profit versus cost time range"'));
  assert.ok(!trendSelector.includes("className="));
  assert.ok(!trendSelector.includes("compact"));
  assert.ok(!trendSelector.includes("variant"));
  assert.ok(!trendSelector.includes("size"));
});
