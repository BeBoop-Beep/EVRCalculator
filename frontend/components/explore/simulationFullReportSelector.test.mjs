import assert from "node:assert/strict";
import test from "node:test";
import { selectSimulationFullReport } from "./simulationFullReportSelector.mjs";

const canonical = { financialRipV3: {
  components: {
    true_win_frequency: { raw: { trueWinProbability: 0 } },
    typical_value_retention: { raw: { typicalPackValue: 3.33, typicalRetentionRatio: 0.44 } },
    loss_resilience: { raw: { averageLosingReturnValue: 2.1, averageRetentionGivenLoss: 0.3, hardLossProbability: 0.6, softLossShareGivenLoss: 0.2 } },
    realistic_upside: { raw: { p95ThresholdValue: 12, realisticTailMeanValue: 24 } },
    jackpot_upside: { raw: { p99ThresholdValue: 72.42, jackpotTailMeanValue: 180, jackpotValueShare: 0.31 } },
    base_economic_efficiency: { raw: { totalRtpRatio: 0.91, baseRtpExcludingTop1Pct: 0.63 } },
  },
  distributionDisclosures: { p05Value: 1.9 },
  depthAndRobustness: { hhiEvConcentration: 0.18, effectiveChaseCount: 5.2 },
  weights: { secret: 0.25 }, hiddenAnchors: [1], randomSeed: 123, runId: "private",
} };

test("groups canonical values with public terminology and preserves zero", () => {
  const report = selectSimulationFullReport({ canonical, summary: { mean_value: 9.34, max_value: 3600, coefficient_of_variation: 2.2, debug_field: 99 }, percentiles: [{ percentile: 25, value: 2.6 }, { percentile: 50, value: 3.33 }, { percentile: 75, value: 5 }, { percentile: 95, value: 12 }, { percentile: 99, value: 72.42 }] });
  assert.deepEqual(report.groups.map(({ title }) => title), ["Typical Outcomes", "Downside", "Upside & Tail", "Economic / Distribution Diagnostics"]);
  const rows = report.groups.flatMap((group) => group.rows);
  assert.equal(rows.find((row) => row.key === "chanceToBeatCost").value, "0.0%");
  assert.equal(rows.find((row) => row.key === "typicalOpening").label, "Typical Opening");
  assert.equal(rows.find((row) => row.key === "strongUpside").label, "Strong Upside");
  assert.equal(rows.find((row) => row.key === "jackpotUpside").label, "Jackpot Upside");
  assert.equal(JSON.stringify(report).includes("runId"), false);
  assert.equal(JSON.stringify(report).includes("secret"), false);
  assert.equal(JSON.stringify(report).includes("debug_field"), false);
});

test("omits unavailable rows and empty groups honestly", () => {
  const report = selectSimulationFullReport({ summary: { mean_value: 0, median_value: null, max_value: null } });
  assert.equal(report.available, false);
  assert.deepEqual(report.groups.map((group) => group.title), ["Typical Outcomes"]);
  assert.deepEqual(report.groups[0].rows.map((row) => [row.label, row.value]), [["Expected Value", "$0.00"]]);
});
