import assert from "node:assert/strict";
import fs from "node:fs";
import test from "node:test";

const source = fs.readFileSync(new URL("./ProductComparisonSection.jsx", import.meta.url), "utf8");

test("This Set / Same Format comparison rows read the four Bucket 2 metrics from the already-cached comparison row, never a new fetch", () => {
  for (const token of [
    "row.modeledReturnPercent",
    "row.typicalOpening",
    "row.chanceToRecoverCost",
    "row.topOneOutcomeValueShare",
  ]) {
    assert.ok(source.includes(token), token);
  }
  // Never the decoy field.
  assert.ok(!source.includes("row.top1EvShare"));
  // No per-row network access: comparison rows come from `comparisonRows(detail, mode)`,
  // the already-fetched cached detail payload — no fetch/await introduced here.
  assert.ok(!/\bfetch\(|\bawait\b/.test(source));
});

test("labels use the canonical Bucket 2 vocabulary", () => {
  for (const label of ["Average Return", "Typical Opening", "Covers Cost", "Top 1% Value Share"]) {
    assert.ok(source.includes(label), label);
  }
});

test("the four-metric block stays behind the same entitled+rankable gate as RIP Score/Tier", () => {
  const gated = source.slice(source.indexOf("entitled && row.rankable"));
  assert.match(gated, /data-comparison-opening-profile/);
});
