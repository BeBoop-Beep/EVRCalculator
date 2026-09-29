import assert from "node:assert/strict";
import test from "node:test";
import { canonicalMetricRows, insertBenchmarkReference } from "./rankingsScoreTableModel.mjs";

const row = (id, score, rank, name = id) => ({ entityId: id, name, overall: { score, rank, cohortSize: 4 } });

test("the 5.0 reference is inserted at the descending score crossing", () => {
  const rows = canonicalMetricRows([row("low", 4.9, 3), row("high", 7.1, 1), row("tie", 5, 2)]);
  assert.deepEqual(insertBenchmarkReference(rows).map((item) => item.kind === "reference" ? "reference" : item.id), ["high", "tie", "reference", "low"]);
});

test("the reference is deterministic when every score is on one side", () => {
  assert.equal(insertBenchmarkReference(canonicalMetricRows([row("a", 6, 1)]))[1].kind, "reference");
  assert.equal(insertBenchmarkReference(canonicalMetricRows([row("a", 4, 1)]))[0].kind, "reference");
});

test("search and era filters preserve backend rank", () => {
  const rows = [
    { ...row("a", 8, 8, "Alpha"), era: { eraName: "One" } },
    { ...row("b", 9, 1, "Beta"), era: { eraName: "Two" } },
  ];
  assert.deepEqual(canonicalMetricRows(rows, "overall", "alp", "One").map((item) => item.metric.rank), [8]);
});
