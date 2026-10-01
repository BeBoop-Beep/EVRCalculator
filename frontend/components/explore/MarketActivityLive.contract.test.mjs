import assert from "node:assert/strict";
import { readFileSync } from "node:fs";
import test from "node:test";

const root = new URL("../../", import.meta.url);
const read = (path) => readFileSync(new URL(path, root), "utf8");

test("live UI keeps fixture language conditional and exposes bounded retry", () => {
  const chart = read("components/explore/MarketActivityChart.jsx");
  assert.match(chart, /fixtureMode \?/);
  assert.match(chart, /Market Activity temporarily unavailable/);
  assert.match(chart, /data-market-activity-retry/);
});

test("constituent Activity is local, exact-variant joined, cursor paged, mobile, and detail-on-open", () => {
  const source = read("components/explore/MarketActivityConstituents.jsx");
  for (const token of [
    "cardVariantId",
    "instrumentKey",
    "nextCursor",
    "data-market-activity-mobile-cards",
    "fetchMarketActivityInstrument",
    "setOpened(row)",
    "Observed Sales",
    "Proven Sales",
    "peer",
    "Graded activity is unavailable",
  ])
    assert.ok(source.includes(token), token);
  assert.doesNotMatch(source, /\.sort\(/);
});

test("active-set discovery is outside focus and live group receives canonical chart range", () => {
  const client = read("components/explore/MarketExplorerClient.jsx");
  assert.match(
    client,
    /useMarketActivityCapabilities\(\{[\s\S]*activeSeries: selectedSeries/,
  );
  assert.match(
    client,
    /startDate: dates\[0\], endDate: dates\[dates.length - 1\]/,
  );
  assert.match(client, /fetchMarketActivityGroup/);
  assert.match(client, /windowDays: activityWindowDays/);
});
