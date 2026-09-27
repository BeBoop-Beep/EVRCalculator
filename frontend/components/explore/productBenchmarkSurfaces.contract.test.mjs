import assert from "node:assert/strict";
import fs from "node:fs";
import test from "node:test";

const source = fs.readFileSync(new URL("./RankingsProductLensClient.jsx", import.meta.url), "utf8");

test("Product Rankings renders Benchmark V1 and removes legacy Product score and tier display", () => {
  assert.match(source, /BenchmarkScoreBadge/);
  assert.match(source, /RIP Score/);
  assert.match(source, /Financial RIP/);
  assert.doesNotMatch(source, /overallRipLeaderScore|financialRipLeaderScore|RipTierMark|publicTier/);
});

test("rank semantics stay scoped to their actual authority", () => {
  assert.match(source, /Full Market Rank/);
  assert.match(source, /Benchmark rank is within this family/);
  assert.match(source, /Inherited · no Product rank/);
  const allSorts = source.match(/const allSorts = \[([\s\S]*?)\]; const familySorts/)?.[1] || "";
  assert.doesNotMatch(allSorts, /BenchmarkRank|BenchmarkScore/);
});

test("Basic and anonymous Product views never request Benchmark rows", () => {
  assert.match(source, /if \(entitled\).*readCurrentProductBenchmark/s);
  assert.match(source, /const freshness = entitled \?/);
});

test("typed evidence, inherited labels, freshness, and mobile rendering are present", () => {
  assert.match(source, /financialEvidence\.expectedValuePerPack/);
  assert.match(source, /Collector Appeal · Parent Set/);
  assert.match(source, /formatBenchmarkFreshness/);
  assert.match(source, /md:hidden/);
});
