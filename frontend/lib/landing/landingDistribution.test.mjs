import assert from "node:assert/strict";
import test from "node:test";
import { selectLandingDistribution } from "./landingDistribution.mjs";

function payload(probabilities, values, max) {
  return { outcomeDistribution: {
    percentiles: [5, 50, 95, 99].map((percentile, index) => ({ percentile, value: values[index] })),
    thresholdBins: probabilities.map((probability, index) => ({ thresholdFloor: index * 5, thresholdCeiling: (index + 1) * 5, probability, bucketOrder: index + 1, bucketLabel: `${index * 5}-${(index + 1) * 5}` })),
    distributionBins: [{ binFloor: 0, binCeiling: max, probability: 1 }],
  }};
}

test("compact measured distribution retains all five canonical landmarks", () => {
  const view = selectLandingDistribution(payload([.2, .45, .25, .1], [1, 5, 14, 19], 25));
  assert.deepEqual(view.markers.map((marker) => [marker.short, marker.value]), [["P05",1],["P50",5],["P95",14],["P99",19],["MAX",25]]);
  assert.equal(view.thresholdBins[0].threshold_floor, 0);
});

test("jackpot-skewed and extreme-max sets keep measured bins and truthful max", () => {
  const skewed = selectLandingDistribution(payload([.72, .2, .06, .015, .005], [.2, 2.5, 30, 90], 1400), { maxValue: 1400 });
  assert.deepEqual(skewed.thresholdBins.map((bin) => bin.probability), [.72, .2, .06, .015, .005]);
  assert.equal(skewed.markers.at(-1).value, 1400);
  assert.ok(skewed.markers.at(-1).value > skewed.markers[3].value * 10);
});

test("percentile landmarks without measured bins cannot draw the shared distribution", () => {
  assert.equal(selectLandingDistribution({ outcomeDistribution: { percentiles: [{ percentile: 50, value: 3 }] } }), null);
});
