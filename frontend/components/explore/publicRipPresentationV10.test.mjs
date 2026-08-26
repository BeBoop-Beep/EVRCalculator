import test from "node:test";
import assert from "node:assert/strict";

import { formatModeScore, formatPublicRipScore, publicRipDisplayScore, SCORE_KIND_PUBLIC } from "../../constants/exploreRankingConfig.mjs";
import { readCanonicalOverallRipV10 } from "./canonicalRipV7.mjs";
import { readSortValue, sortRankingsRows, RANKINGS_DEFAULT_SORT } from "./rankingsSort.mjs";

function target(name, rank, relativeScore, tier, formatRank, formatScore) {
  return {
    name,
    publicRipContractV10: {
      overallRip: { rank, relativeScore, leaderNormalizedScore: relativeScore, tier, rankedSetCount: 20 },
      financialRip: {},
      collectorAppeal: {},
    },
    setRipV1: { rank: formatRank, score: formatScore, cohortSize: 20 },
  };
}

test("public RIP presentation converts authoritative 0-100 values exactly once", () => {
  assert.equal(formatPublicRipScore(100), "10.0");
  assert.equal(formatPublicRipScore(96.8), "9.7");
  assert.equal(formatPublicRipScore(88.77), "8.9");
  assert.equal(formatPublicRipScore(57.28), "5.7");
  assert.equal(formatPublicRipScore(0), "0.0");
  assert.equal(formatPublicRipScore(null), "—");
  assert.equal(formatModeScore(9.7, SCORE_KIND_PUBLIC), "1.0", "values are never magnitude-guessed as already scaled");
});

test("public score formatting uses deterministic half-up boundaries", () => {
  assert.deepEqual(
    [95.49, 95.50, 94.99, 89.49, 89.50, 79.49, 79.50, 69.49, 69.50, 54.49, 54.50].map(publicRipDisplayScore),
    [9.5, 9.6, 9.5, 8.9, 9.0, 7.9, 8.0, 6.9, 7.0, 5.4, 5.5],
  );
});

test("canonical V10 owns the headline while Set RIP V1 remains distinct", () => {
  const row = target("Synthetic", 2, 88.77, "A", 8, 97);
  const overall = readCanonicalOverallRipV10(row);
  assert.deepEqual(
    { rank: overall.rank, score: formatPublicRipScore(overall.publicScore), tier: overall.tier },
    { rank: 2, score: "8.9", tier: "A" },
  );
  assert.equal(formatPublicRipScore(row.setRipV1.score), "9.7");
  assert.equal(readSortValue(row, "setRip"), 88.77);
});

test("missing V10 never falls back to Set RIP V1", () => {
  const row = { setRipV1: { rank: 1, score: 100, cohortSize: 20 } };
  const overall = readCanonicalOverallRipV10(row);
  assert.equal(overall.rank, null);
  assert.equal(overall.publicScore, null);
  assert.equal(overall.tier, null);
  assert.equal(readSortValue(row, "setRip"), null);
});

test("default order follows canonical V10 rank despite opposing Format Strength", () => {
  const canonicalFirst = target("Canonical first", 1, 80, "S", 9, 20);
  const formatFirst = target("Format first", 2, 70, "A", 1, 100);
  const canonical = [canonicalFirst, formatFirst];
  assert.deepEqual(sortRankingsRows(canonical, RANKINGS_DEFAULT_SORT), canonical);
});

test("family and product public scores share the /10 conversion; non-scores do not", () => {
  assert.deepEqual([100, 95.5, 92.3].map(formatPublicRipScore), ["10.0", "9.6", "9.2"]);
  assert.deepEqual([57.28, 55.27, 75.34].map(formatPublicRipScore), ["5.7", "5.5", "7.5"]);
  assert.equal(new Intl.NumberFormat("en-US", { style: "currency", currency: "USD" }).format(181.28), "$181.28");
});
