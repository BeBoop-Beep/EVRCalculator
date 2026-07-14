import assert from "node:assert/strict";
import test from "node:test";

import {
  COEFFICIENT_OF_VARIATION_TAG_THRESHOLDS,
  HHI_CONCENTRATION_TAG_THRESHOLDS,
  buildPercentileStripModel,
  buildPercentileTakeaway,
  formatMetricCurrency,
  formatMetricPercent,
  formatMetricProbability,
  formatMetricRatio,
  formatMetricSignedPercent,
  formatOddsFromPercent,
  getCoefficientOfVariationTag,
  getHhiConcentrationTag,
  getLogScalePosition,
  shouldMergeLossFractionRows,
} from "./simulationMetricsDisplay.mjs";

test("shared metric formatter normalizes precision per value kind", () => {
  // currency >= $1,000 abbreviates in the app's compact style; below keeps 2 decimals
  assert.equal(formatMetricCurrency(1398), "$1.4K");
  assert.equal(formatMetricCurrency(6255870.74), "$6.26M");
  assert.equal(formatMetricCurrency(845.2), "$845.20");
  assert.equal(formatMetricCurrency(0), "$0.00");
  assert.equal(formatMetricCurrency(null), "—");
  // ratios -> 2 decimals + x
  assert.equal(formatMetricRatio(0.5101), "0.51x");
  assert.equal(formatMetricRatio(null), "—");
  // percentages -> 1 decimal + %
  assert.equal(formatMetricPercent(29.24), "29.2%");
  assert.equal(formatMetricPercent(null), "—");
  // 0-1 probabilities normalize to %
  assert.equal(formatMetricProbability(0.036), "3.6%");
  assert.equal(formatMetricProbability(3.6), "3.6%");
  assert.equal(formatMetricProbability(null), "—");
  // signed percent keeps the sign
  assert.equal(formatMetricSignedPercent(-49.0), "-49.0%");
  assert.equal(formatMetricSignedPercent(12.34), "+12.3%");
});

test("odds phrasing converts a chance percentage and guards degenerate inputs", () => {
  assert.equal(formatOddsFromPercent(3.6), "1 in 28 packs");
  assert.equal(formatOddsFromPercent(50), "1 in 2 packs");
  assert.equal(formatOddsFromPercent(0.05), "1 in 2,000 packs");
  // divide-by-zero / unusable chances are omitted, not crashed on
  assert.equal(formatOddsFromPercent(0), null);
  assert.equal(formatOddsFromPercent(-5), null);
  assert.equal(formatOddsFromPercent(null), null);
  // near-certain profit would read "1 in 1 packs" — omitted as noise
  assert.equal(formatOddsFromPercent(90), null);
});

test("log scale positions span [0,1] and reject unusable domains", () => {
  assert.equal(getLogScalePosition(1, 1, 100), 0);
  assert.equal(getLogScalePosition(100, 1, 100), 1);
  assert.ok(Math.abs(getLogScalePosition(10, 1, 100) - 0.5) < 1e-9);
  // clamped below/above the domain
  assert.equal(getLogScalePosition(0.5, 1, 100), 0);
  assert.equal(getLogScalePosition(500, 1, 100), 1);
  assert.equal(getLogScalePosition(10, 0, 100), null);
  assert.equal(getLogScalePosition(null, 1, 100), null);
});

test("percentile strip model keeps every percentile, staggers major labels, and anchors pack cost", () => {
  const model = buildPercentileStripModel({
    min: 0.11,
    p5: 0.98,
    p25: 1.1,
    p50: 1.42,
    p75: 3.2,
    p90: 8.5,
    p95: 14.9,
    p99: 120,
    max: 4890,
    packCost: 10.11,
  });

  assert.ok(model, "a usable model must be produced");
  assert.equal(model.markers.length, 9, "all nine percentiles stay accessible");
  const majors = model.markers.filter((marker) => marker.major);
  assert.deepEqual(majors.map((marker) => marker.key), ["min", "p5", "p50", "p95", "p99", "max"]);
  // Labels alternate above/below in position order so neighbors never collide.
  assert.deepEqual(majors.map((marker) => marker.labelSide), ["above", "below", "above", "below", "above", "below"]);
  // Minor markers (band edges + P90) carry no static label side.
  for (const marker of model.markers.filter((entry) => !entry.major)) {
    assert.equal(marker.labelSide, undefined);
  }
  // Positions ascend and stay within [0, 1].
  const positions = model.markers.map((marker) => marker.position);
  for (let i = 1; i < positions.length; i += 1) {
    assert.ok(positions[i] >= positions[i - 1]);
  }
  assert.ok(positions.every((position) => position >= 0 && position <= 1));
  // Cost anchor sits inside the domain; markers know their side of it.
  assert.ok(model.cost.position > 0 && model.cost.position < 1);
  assert.equal(model.markers.find((marker) => marker.key === "p95").aboveCost, true);
  assert.equal(model.markers.find((marker) => marker.key === "p50").aboveCost, false);
  // The IQR band sits fully below cost here, so it may take the warm tint.
  assert.equal(model.band.belowCost, true);
});

test("percentile strip model survives zero floors and missing values", () => {
  const model = buildPercentileStripModel({ min: 0, p50: 1.42, p95: 14.9, max: 4890, packCost: 10.11 });
  assert.ok(model);
  const minMarker = model.markers.find((marker) => marker.key === "min");
  assert.equal(minMarker.position, 0, "a $0 floor clamps to the domain start instead of breaking the log scale");
  assert.equal(model.band, null, "no band without both P25 and P75");
  assert.equal(buildPercentileStripModel({}), null);
  assert.equal(buildPercentileStripModel({ p50: 5 }), null, "a single point cannot span a log domain");
});

test("strip takeaway is phrased from live values", () => {
  assert.equal(
    buildPercentileTakeaway({ p50: 1.42, p95: 7.44, packCost: 10.11, probProfitPercent: 3.6 }),
    "P95 of packs open below cost — profit is concentrated in the top 3.6% of outcomes."
  );
  assert.equal(
    buildPercentileTakeaway({ p50: 12, p95: 80, packCost: 10.11, probProfitPercent: 55 }),
    "The median pack opens at or above cost — more than half of simulated packs beat the pack price."
  );
  assert.equal(
    buildPercentileTakeaway({ p50: 1.42, p95: 14.9, packCost: 10.11, probProfitPercent: 3.6 }),
    "Most packs open below cost — roughly 3.6% of simulated packs beat the pack price."
  );
  assert.equal(buildPercentileTakeaway({ p50: 1, p95: 2, packCost: null, probProfitPercent: 3 }), null);
});

test("judgment tags translate CV and HHI through named thresholds", () => {
  assert.deepEqual(getCoefficientOfVariationTag(0.4), { label: "low", tone: "success" });
  assert.deepEqual(getCoefficientOfVariationTag(2.2), { label: "high", tone: "warning" });
  assert.deepEqual(getCoefficientOfVariationTag(8.58), { label: "extreme", tone: "danger" });
  assert.equal(getCoefficientOfVariationTag(null), null);
  assert.equal(COEFFICIENT_OF_VARIATION_TAG_THRESHOLDS.LOW_MAX, 1);
  assert.equal(COEFFICIENT_OF_VARIATION_TAG_THRESHOLDS.HIGH_MAX, 3);

  assert.deepEqual(getHhiConcentrationTag(0.05), { label: "diffuse", tone: "success" });
  assert.deepEqual(getHhiConcentrationTag(0.18), { label: "moderate", tone: "neutral" });
  assert.deepEqual(getHhiConcentrationTag(0.31), { label: "concentrated", tone: "danger" });
  assert.equal(getHhiConcentrationTag(null), null);
  assert.equal(HHI_CONCENTRATION_TAG_THRESHOLDS.DIFFUSE_MAX, 0.1);
  assert.equal(HHI_CONCENTRATION_TAG_THRESHOLDS.MODERATE_MAX, 0.25);
});

test("loss fraction rows merge only when equal after display rounding", () => {
  assert.equal(shouldMergeLossFractionRows(80.8, 80.83), true);
  assert.equal(shouldMergeLossFractionRows(80.8, 86.3), false);
  assert.equal(shouldMergeLossFractionRows(null, 80.8), false);
  assert.equal(shouldMergeLossFractionRows(null, null), false);
});
