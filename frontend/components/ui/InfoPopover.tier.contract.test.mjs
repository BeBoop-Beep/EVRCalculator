import assert from "node:assert/strict";
import fs from "node:fs";
import path from "node:path";
import test from "node:test";

const source = fs.readFileSync(path.resolve("components/ui/InfoPopover.jsx"), "utf8");
const tierInfo = source.slice(source.indexOf("export function PublicRipTierInfo"), source.indexOf("export default function InfoPopover"));

test("PublicRipTierInfo exposes the canonical displayed /10 tier contract", () => {
  for (const threshold of ["≥ 9.6", "≥ 9.0", "≥ 8.0", "≥ 6.5", "≥ 5.0", "< 5.0"]) {
    assert.ok(tierInfo.includes(`"${threshold}"`), threshold);
  }
  for (const stale of ["≥ 5.5", "< 5.5", "≥ 9.5", "≥ 7.0", '"95"', '"90"', '"80"', '"70"', '"55"', "Equivalent to", "percentile", "min-max"]) {
    assert.ok(!tierInfo.includes(stale), stale);
  }
  assert.ok(tierInfo.includes("<ul"));
  assert.ok(tierInfo.includes("<li"));
  assert.ok(tierInfo.includes("tabular-nums"));
});
