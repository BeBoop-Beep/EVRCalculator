import assert from "node:assert/strict";
import fs from "node:fs";
import test from "node:test";

const source = fs.readFileSync(new URL("./OverviewRipSummary.jsx", import.meta.url), "utf8");

test("Overview renders exactly the three approved Set Benchmark headlines", () => {
  for (const [id, label, key] of [
    ["overall", "RIP Score", "benchmark.overall"],
    ["financial", "Financial RIP", "benchmark.financial"],
    ["collector", "Collector Appeal", "benchmark.collector"],
  ]) {
    assert.match(source, new RegExp(`id="${id}"[\\s\\S]{0,180}label="${label}"[\\s\\S]{0,220}metric=\\{${key.replace(".", "\\.")}\\}`));
  }
  assert.equal((source.match(/<SummaryMetric/g) || []).length, 3);
});

test("Overview uses the public headline hook and shared Benchmark presentation", () => {
  assert.match(source, /useSetBenchmarkHeadlines\(setId\)/);
  assert.match(source, /setBenchmarkMetrics\(setId, benchmarkState\.payload\)/);
  assert.match(source, /<BenchmarkScoreBadge metric=\{metric\}/);
  assert.match(source, /formatBenchmarkFreshness/);
});

test("Overview no longer reads legacy canonical scores, ranks, or tiers", () => {
  for (const retired of ["readCanonicalBlock", "resolveCanonicalRipV7", "publicScore", "relativeScore", " Tier", "formatMeta"])
    assert.ok(!source.includes(retired), retired);
});

test("View analysis remains one optional restrained action", () => {
  assert.equal((source.match(/<button/g) || []).length, 1);
  assert.match(source, /onClick=\{onViewAnalysis\}/);
  assert.match(source, /onViewAnalysis \? \(/);
});

test("the summary remains one grouped surface", () => {
  assert.equal((source.match(/set-glass-surface/g) || []).length, 1);
});
