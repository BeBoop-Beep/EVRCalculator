import assert from "node:assert/strict";
import test from "node:test";

import {
  DEFAULT_CHASE_TOP_N,
  QUERY_MODE_ALL,
  QUERY_MODE_CHASE,
  addQuerySeries,
  buildQueryKey,
  buildQueryLabel,
  buildQuerySeries,
  normalizeQuerySpec,
  removeQuerySeries,
  resolveBenchmarkSpec,
} from "./marketExplorerQuery.mjs";

const NAMES = {
  eraNames: { "era-sv": "Scarlet & Violet" },
  setNames: { "set-ah": "Ascended Heroes" },
  segmentNames: { specialIllustrationRare: "Special Illustration Rare" },
};

test("empty selections mean ALL, never an empty universe", () => {
  const spec = normalizeQuerySpec({ mode: QUERY_MODE_ALL });
  assert.deepEqual(spec.eraIds, []);
  assert.deepEqual(spec.segmentIds, []);
  assert.equal(buildQueryKey(spec), "cards|era=all|set=all|segment=all|mode=all|topN=na");
});

test("chase defaults to the published Top 10 cutoff", () => {
  assert.equal(normalizeQuerySpec({ mode: QUERY_MODE_CHASE }).topN, DEFAULT_CHASE_TOP_N);
});

test("topN is dropped outside chase so two identical markets cannot fingerprint apart", () => {
  assert.equal(normalizeQuerySpec({ mode: QUERY_MODE_ALL, topN: 10 }).topN, null);
  assert.equal(
    buildQueryKey({ mode: QUERY_MODE_ALL, topN: 10 }),
    buildQueryKey({ mode: QUERY_MODE_ALL }),
  );
});

test("equivalent multi-selections collapse to one identity", () => {
  assert.equal(
    buildQueryKey({ mode: QUERY_MODE_CHASE, eraIds: ["b", "a"], segmentIds: ["sir"] }),
    buildQueryKey({ mode: QUERY_MODE_CHASE, eraIds: ["a", "b", "a"], segmentIds: ["sir"] }),
  );
});

test("differing markets do not collide", () => {
  assert.notEqual(
    buildQueryKey({ mode: QUERY_MODE_CHASE, segmentIds: ["sir"] }),
    buildQueryKey({ mode: QUERY_MODE_ALL, segmentIds: ["sir"] }),
  );
});

test("the query key matches the backend contract string exactly", () => {
  assert.equal(
    buildQueryKey({ mode: QUERY_MODE_CHASE, eraIds: ["era-sv"], segmentIds: ["specialIllustrationRare"] }),
    "cards|era=era-sv|set=all|segment=specialIllustrationRare|mode=chase|topN=10",
  );
});

test("labels read as the market the user selected", () => {
  assert.equal(
    buildQueryLabel({ mode: QUERY_MODE_CHASE, eraIds: ["era-sv"], segmentIds: ["specialIllustrationRare"] }, NAMES),
    "Scarlet & Violet · Special Illustration Rare · Top 10",
  );
  assert.equal(
    buildQueryLabel({ mode: QUERY_MODE_ALL, segmentIds: ["specialIllustrationRare"] }, NAMES),
    "Global · Special Illustration Rare · All",
  );
  assert.equal(buildQueryLabel({ mode: QUERY_MODE_ALL }, NAMES), "Global · All rarities · All");
});

test("an explicit set is more specific than its era and wins the scope label", () => {
  assert.equal(
    buildQueryLabel({ mode: QUERY_MODE_CHASE, eraIds: ["era-sv"], setIds: ["set-ah"] }, NAMES),
    "Ascended Heroes · All rarities · Top 10",
  );
});

test("a chase query benchmarks against its own universe in ALL mode", () => {
  const benchmark = resolveBenchmarkSpec({
    mode: QUERY_MODE_CHASE, eraIds: ["era-sv"], segmentIds: ["specialIllustrationRare"],
  });
  assert.equal(benchmark.mode, QUERY_MODE_ALL);
  assert.equal(benchmark.topN, null);
  // Same filters -- only the mode differs.
  assert.deepEqual(benchmark.eraIds, ["era-sv"]);
  assert.deepEqual(benchmark.segmentIds, ["specialIllustrationRare"]);
});

test("an all-constituents query has no narrower parent and invents none", () => {
  assert.equal(resolveBenchmarkSpec({ mode: QUERY_MODE_ALL, segmentIds: ["sir"] }), null);
});

test("a series carries identity, not just a display string", () => {
  const series = buildQuerySeries({ mode: QUERY_MODE_CHASE, segmentIds: ["specialIllustrationRare"] }, NAMES);
  assert.equal(series.seriesId, `query:${series.queryKey}`);
  assert.equal(series.mode, QUERY_MODE_CHASE);
  assert.equal(series.topN, 10);
  assert.equal(series.scopeSummary.isGlobal, true);
  assert.equal(series.segmentSummary.isAllRarities, false);
  assert.ok(series.spec, "the normalized spec travels with the series");
});

test("the same market cannot be added to the comparison twice", () => {
  const series = buildQuerySeries({ mode: QUERY_MODE_CHASE, segmentIds: ["sir"] }, NAMES);
  const once = addQuerySeries([], series);
  const twice = addQuerySeries(once, buildQuerySeries({ mode: QUERY_MODE_CHASE, segmentIds: ["sir"] }, NAMES));
  assert.equal(twice.length, 1);
  assert.equal(removeQuerySeries(twice, series.queryKey).length, 0);
});

test("this module contains no hardcoded rarity authority", async () => {
  const source = await import("node:fs/promises").then((fs) =>
    fs.readFile(new URL("./marketExplorerQuery.mjs", import.meta.url), "utf8"));
  for (const forbidden of ["Special Illustration Rare", "Illustration Rare", "Hyper Rare", "Ultra Rare"]) {
    assert.ok(
      !source.includes(`"${forbidden}"`),
      `rarity authority must come from the backend, found a hardcoded ${forbidden}`,
    );
  }
});
