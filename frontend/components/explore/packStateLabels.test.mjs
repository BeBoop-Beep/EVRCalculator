import test from "node:test";
import assert from "node:assert/strict";

import { normalizePackStateLabel, aggregateNormalStateRows } from "./packStateLabels.mjs";

test("normalizePackStateLabel collapses camelCase and spaced variants to one label", () => {
  assert.equal(normalizePackStateLabel("DoubleRareOnly"), "Double Rare Only");
  assert.equal(normalizePackStateLabel("Double Rare Only"), "Double Rare Only");
  assert.equal(normalizePackStateLabel("UltraRareOnly"), "Ultra Rare Only");
  assert.equal(normalizePackStateLabel("Ultra Rare Only"), "Ultra Rare Only");
});

test("normalizePackStateLabel renders acronyms uppercase and Plus as +", () => {
  assert.equal(normalizePackStateLabel("IrPlusRare"), "IR + Rare");
  assert.equal(normalizePackStateLabel("Ir Plus Rare"), "IR + Rare");
  assert.equal(normalizePackStateLabel("SirOnly"), "SIR Only");
  assert.equal(normalizePackStateLabel("Sir Only"), "SIR Only");
  assert.equal(normalizePackStateLabel("IrPlusDoubleRare"), "IR + Double Rare");
  assert.equal(normalizePackStateLabel("Ir Plus Double Rare"), "IR + Double Rare");
});

test("normalizePackStateLabel handles snake_case and empty input", () => {
  assert.equal(normalizePackStateLabel("double_rare_only"), "Double Rare Only");
  assert.equal(normalizePackStateLabel(""), "");
  assert.equal(normalizePackStateLabel(null), "");
});

test("aggregateNormalStateRows sums counts of duplicate display labels", () => {
  const { rows, hiddenCount } = aggregateNormalStateRows([
    ["DoubleRareOnly", 10],
    ["Double Rare Only", 5],
    ["IrPlusRare", 3],
  ]);
  assert.equal(hiddenCount, 0);
  const doubleRare = rows.find((r) => r.label === "Double Rare Only");
  assert.equal(doubleRare.count, 15, "camel + spaced duplicates must merge");
  assert.equal(rows[0].label, "Double Rare Only", "sorted by count desc");
});

test("aggregateNormalStateRows accepts object rows and skips non-numeric counts", () => {
  const { rows } = aggregateNormalStateRows([
    { name: "SirOnly", count: 8 },
    { name: "Sir Only", count: 2 },
    { name: "Broken", count: "n/a" },
  ]);
  assert.equal(rows.length, 1);
  assert.equal(rows[0].label, "SIR Only");
  assert.equal(rows[0].count, 10);
});

test("aggregateNormalStateRows keeps only the top N and reports the remainder", () => {
  const input = [
    ["A One", 50],
    ["B Two", 40],
    ["C Three", 30],
    ["D Four", 20],
    ["E Five", 10],
  ];
  const { rows, hiddenCount } = aggregateNormalStateRows(input, { topN: 3 });
  assert.equal(rows.length, 3);
  assert.equal(hiddenCount, 2);
  assert.deepEqual(rows.map((r) => r.label), ["A One", "B Two", "C Three"]);
});
