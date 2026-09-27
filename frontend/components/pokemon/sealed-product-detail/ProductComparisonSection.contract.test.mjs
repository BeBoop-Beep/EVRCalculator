import assert from "node:assert/strict";
import fs from "node:fs";
import test from "node:test";

const source = fs.readFileSync(new URL("./ProductComparisonSection.jsx", import.meta.url), "utf8");
const evidenceStart = source.indexOf("function Evidence({ row })");
const evidenceEnd = source.indexOf("export default function ProductComparisonSection", evidenceStart);
const evidence = source.slice(evidenceStart, evidenceEnd);

test("Evidence owns exactly the four cached Bucket 2 metrics and never fetches", () => {
  assert.ok(evidenceStart >= 0 && evidenceEnd > evidenceStart, "Evidence helper exists");
  assert.match(evidence, /data-comparison-opening-profile/);
  for (const token of [
    "row.modeledReturnPercent",
    "row.typicalOpening",
    "row.chanceToRecoverCost",
    "row.topOneOutcomeValueShare",
  ]) {
    assert.equal(evidence.split(token).length - 1, 1, token);
  }
  assert.ok(!evidence.includes("row.top1EvShare"));
  assert.ok(!/\bfetch\(|\bawait\b/.test(source));
});

test("labels use the canonical Bucket 2 vocabulary", () => {
  for (const label of ["Average Return", "Typical Opening", "Covers Cost", "Top 1% Value Share"]) {
    assert.ok(evidence.includes(label), label);
  }
});

test("the four-metric evidence block remains behind the entitled+rankable gate", () => {
  assert.equal(source.split("<Evidence row={row} />").length - 1, 1);
  assert.match(
    source,
    /entitled && row\.rankable\s*\?\s*<div[^>]*>[\s\S]*?<Evidence row=\{row\} \/>[\s\S]*?<\/div>\s*:\s*null/,
  );
});
