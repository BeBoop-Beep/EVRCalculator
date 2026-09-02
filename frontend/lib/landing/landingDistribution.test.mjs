import assert from "node:assert/strict";
import test from "node:test";
import { selectLandingDistribution } from "./landingDistribution.mjs";

// Shaped like the PUBLIC /rip/simulation-evidence projection
// (pokemon-set-rip-simulation-evidence-v1, Base/anonymous allowlist): top
// -level distributionBins/thresholdBins/summary — no percentiles array, no
// Financial RIP internals.
function payload({ simulationCount = 500000, packCost = 5, median = 2, mean = 8 } = {}) {
  return {
    contractVersion: "pokemon-set-rip-simulation-evidence-v1",
    summary: { simulation_count: simulationCount, pack_cost: packCost, median_value: median, mean_value: mean },
    distributionBins: [{ binFloor: 0, binCeiling: 25, probability: 1 }],
    thresholdBins: [
      { thresholdFloor: 0, thresholdCeiling: 5, probability: 0.6, bucketOrder: 1, bucketLabel: "0-5" },
      { thresholdFloor: 5, thresholdCeiling: 10, probability: 0.4, bucketOrder: 2, bucketLabel: "5-10" },
    ],
  };
}

test("valid bins produce a view with dual-cased bins and the public marker set", () => {
  const view = selectLandingDistribution(payload());
  assert.ok(view.bins.length > 0);
  assert.ok(view.thresholdBins.length > 0);
  assert.equal(view.thresholdBins[0].threshold_floor, 0);
  assert.equal(view.simulationCount, 500000);
});

test("only pack-cost/median/mean carry real values; every other marker is locked, not leaked", () => {
  const view = selectLandingDistribution(payload({ packCost: 5, median: 2, mean: 8 }));
  const byKey = Object.fromEntries(view.markers.map((marker) => [marker.key, marker]));

  assert.equal(byKey["pack-cost"].value, 5);
  assert.equal(byKey["pack-cost"].locked, undefined);
  assert.equal(byKey.median.value, 2);
  assert.equal(byKey.mean.value, 8);

  for (const key of ["p25", "p75", "bad-floor", "big-hit", "big-hit-upside", "god-pull-upside", "max"]) {
    assert.equal(byKey[key].locked, true, `${key} must be locked on the public homepage`);
    assert.equal(byKey[key].value, null, `${key} must never leak a real value`);
  }
});

test("no measured bins cannot draw the shared distribution", () => {
  assert.equal(selectLandingDistribution({ distributionBins: [], thresholdBins: [], summary: {} }), null);
  assert.equal(selectLandingDistribution(null), null);
  assert.equal(selectLandingDistribution(undefined), null);
});

test("simulation count is read from the payload, never hardcoded, and absent when the payload omits it", () => {
  const withCount = selectLandingDistribution(payload({ simulationCount: 123456 }));
  assert.equal(withCount.simulationCount, 123456);

  const withoutCount = selectLandingDistribution({
    ...payload(),
    summary: { pack_cost: 5, median_value: 2, mean_value: 8 },
  });
  assert.equal(withoutCount.simulationCount, null);
});

test("camelCase summary aliases are read the same as snake_case", () => {
  const view = selectLandingDistribution({
    ...payload(),
    summary: { simulationCount: 999, packCost: 6, medianValue: 3, meanValue: 9 },
  });
  const byKey = Object.fromEntries(view.markers.map((marker) => [marker.key, marker.value]));
  assert.equal(view.simulationCount, 999);
  assert.equal(byKey["pack-cost"], 6);
  assert.equal(byKey.median, 3);
  assert.equal(byKey.mean, 9);
});
