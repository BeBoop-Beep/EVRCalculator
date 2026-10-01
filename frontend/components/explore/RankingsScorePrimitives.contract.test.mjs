import assert from "node:assert/strict";
import { readFileSync } from "node:fs";
import test from "node:test";

const read = (path) => readFileSync(new URL(path, import.meta.url), "utf8");
const primitives = read("./RankingsScorePrimitives.jsx");
const badge = read("./RipScoreBadge.jsx");
const overview = read("./RankingsOverviewHighlights.jsx");

test("Rankings RIP scores use the canonical purple octagonal /10 badge", () => {
  assert.ok(primitives.includes("<RipScoreBadge"));
  assert.ok(primitives.includes("metric?.score"));
  assert.ok(primitives.includes("metric?.tier"));
  assert.ok(primitives.includes("metric?.rank"));
  assert.ok(primitives.includes("metric?.cohortSize"));
  assert.ok(primitives.includes("RIP_SCORE_SCALE_BENCHMARK_10"));
  assert.ok(!primitives.includes("accentColor="), "main RIP border must come from the supplied tier, never a forced colour");
  assert.ok(badge.includes("getTierTone(tier)"));
  assert.ok(badge.includes("<polygon"));
  assert.ok(badge.includes('points="10,1 62,1 71,11 71,49 62,59 10,59 1,49 1,11"'));
  assert.ok(badge.includes("/ 10"));
});

test("Rankings badges omit decorative benchmark-position indicators", () => {
  assert.ok(!primitives.includes("BenchmarkPositionIndicator"));
  assert.ok(!primitives.includes("data-benchmark-position"));
  assert.ok(!primitives.includes("deltaVsBenchmark"));
});

test("the muted Overall Average is a reference with score 5.0 and no rank", () => {
  const reference = primitives.slice(primitives.indexOf("export function BenchmarkReferenceRow"));
  assert.ok(reference.includes("Overall Average"));
  assert.ok(reference.includes("score: 5"));
  assert.ok(reference.includes("toFixed(1)"));
  assert.ok(!reference.includes("rank"));
});

test("Overall score cards contain no verbose benchmark-position prose", () => {
  assert.ok(!overview.includes("Above Pok"));
  assert.ok(!overview.includes("Below Pok"));
});
