import assert from "node:assert/strict";
import test from "node:test";
import { selectLandingHeroEntries, selectLandingHeroSpotlight, selectLandingRankedStrip } from "./landingHeroSpotlight.mjs";

const target = (id, rank, score, extra = {}) => ({
  target_type: "pokemon_set", target_id: id, name: `Set ${id}`,
  benchmarkOverall: { score, rank, cohortSize: 41, status: "available", sourceMarketDate: "2026-09-25" },
  checklistSetValue: 100, ...extra,
});

test("Homepage reads Benchmark Overall score, rank, cohort, and position", () => {
  const row = selectLandingHeroSpotlight([target("one", 1, 6.4)]);
  assert.equal(row.score, 6.4);
  assert.equal(row.scoreLabel, "RIP Score");
  assert.equal(row.rank, 1);
  assert.equal(row.cohortSize, 41);
  assert.equal(row.benchmarkPosition, "Above Pokémon benchmark");
  assert.equal(row.benchmarkSourceMarketDate, "2026-09-25");
  assert.equal(row.tier, undefined);
});

test("canonical Benchmark rank chooses #1 independently of rounded score", () => {
  const rows = selectLandingHeroEntries([
    target("high-score", 2, 10),
    target("rank-one", 1, 6.4, { setRipV1: { score: 1, rank: 99, tier: "F" } }),
  ]);
  assert.deepEqual(rows.map((row) => row.targetId), ["rank-one", "high-score"]);
  assert.equal(rows[0].score, 6.4);
});

test("legacy Set RIP cannot fill or reorder a missing Benchmark", () => {
  const legacy = { target_type: "pokemon_set", target_id: "legacy", name: "Legacy", setRipV1: { score: 100, rank: 1, tier: "S" } };
  assert.equal(selectLandingHeroSpotlight([legacy]), null);
});

test("unavailable Benchmark rows are dropped without fallback", () => {
  assert.equal(selectLandingHeroSpotlight([{ ...target("x", 1, 7), benchmarkOverall: { score: 7, rank: 1, status: "unavailable" } }]), null);
});

test("5.0 is the benchmark and scores above/below use approved language", () => {
  assert.equal(selectLandingHeroSpotlight([target("at", 1, 5)]).benchmarkPosition, "At Pokémon benchmark");
  assert.equal(selectLandingHeroSpotlight([target("below", 1, 4.9)]).benchmarkPosition, "Below Pokémon benchmark");
});

test("ranked strip continues after the canonical spotlight", () => {
  assert.deepEqual(selectLandingRankedStrip([1, 2, 3, 4, 5].map((rank) => target(String(rank), rank, 8 - rank)), 3).map((row) => row.rank), [2, 3, 4]);
});

test("opening economics remain independent", () => {
  const row = selectLandingHeroSpotlight([target("one", 1, 6.4, { pack_cost: 5, mean_value: 4, median_value: 2 })]);
  assert.deepEqual([row.packCost, row.meanValue, row.medianValue], [5, 4, 2]);
});
