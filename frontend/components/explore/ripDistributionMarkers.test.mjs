import assert from "node:assert/strict";
import fs from "node:fs";
import test from "node:test";
import { buildRipDistributionMarkers } from "./ripDistributionMarkers.mjs";

const summary = {
  pack_cost: 5,
  median_value: 2,
  mean_value: 8,
  tail_value_p05: 0.5,
  big_hit_threshold: 25,
  p95_value_to_cost_ratio: 4,
  p99_value_to_cost_ratio: 12,
  max_value: 500,
};
const percentiles = [
  { percentile: 5, value: 0.75 }, { percentile: 25, value: 1.25 },
  { percentile: 50, value: 2.5 }, { percentile: 75, value: 6 },
  { percentile: 95, value: 20 }, { percentile: 99, value: 60 },
];

test("returns the complete canonical marker set in presentation order", () => {
  const markers = buildRipDistributionMarkers({ summary, percentiles });
  assert.deepEqual(markers.map(({ key }) => key), [
    "pack-cost", "median", "p25", "p75", "mean", "bad-floor", "big-hit",
    "big-hit-upside", "god-pull-upside", "max",
  ]);
  assert.deepEqual(markers.map(({ label }) => label), [
    "Pack Market Price", "Typical Opening", "P25", "P75", "Average Pack",
    "Bad Floor", "Big Hit Threshold", "Strong Upside", "Jackpot Upside", "Best Pull",
  ]);
});

test("keeps P50/P5 fallbacks and canonical ratio-times-cost P95/P99 semantics", () => {
  const byKey = Object.fromEntries(buildRipDistributionMarkers({ summary, percentiles }).map((marker) => [marker.key, marker.value]));
  assert.equal(byKey.median, 2.5);
  assert.equal(byKey["bad-floor"], 0.75);
  assert.equal(byKey["big-hit-upside"], 20);
  assert.equal(byKey["god-pull-upside"], 60);

  const fallback = Object.fromEntries(buildRipDistributionMarkers({
    summary: { medianValue: 3, tailValueP05: 0.4, p95Value: 21, p99Value: 64 },
    percentiles: [],
  }).map((marker) => [marker.key, marker.value]));
  assert.equal(fallback.median, 3);
  assert.equal(fallback["bad-floor"], 0.4);
  assert.equal(fallback["big-hit-upside"], 21);
  assert.equal(fallback["god-pull-upside"], 64);

  const percentileFallback = Object.fromEntries(buildRipDistributionMarkers({
    summary: {}, percentiles: [{ percentile: 95, value: 22 }, { percentile: 99, value: 65 }],
  }).map((marker) => [marker.key, marker.value]));
  assert.equal(percentileFallback["big-hit-upside"], 22);
  assert.equal(percentileFallback["god-pull-upside"], 65);
});

test("set page and article import and call the one shared builder", () => {
  const page = fs.readFileSync(new URL("./RipStatisticsPageClient.jsx", import.meta.url), "utf8");
  const article = fs.readFileSync(new URL("../../lib/articles/evResearchLiveExample.mjs", import.meta.url), "utf8");
  for (const source of [page, article]) {
    assert.match(source, /import \{ buildRipDistributionMarkers \} from /);
    assert.match(source, /buildRipDistributionMarkers\(\{ summary/);
  }
  assert.doesNotMatch(article, /evidence\.summary\?\.markers/);
});
