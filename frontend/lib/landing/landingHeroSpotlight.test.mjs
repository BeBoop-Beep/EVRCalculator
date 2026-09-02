import assert from "node:assert/strict";
import test from "node:test";

import {
  selectLandingHeroEntries,
  selectLandingHeroSpotlight,
  selectLandingRankedStrip,
} from "./landingHeroSpotlight.mjs";

// Fixture shaped EXACTLY like the anonymous backend projection
// (index_plan_access._project_public_set_leaderboard_target /
// projectRankingsClientPublicSetLeaderboard): identity, images, setRipV1 —
// and deliberately NO overallRipV10, NO publicRipContractV10, NO
// financialRipV4. The homepage's ranking authority must work from this
// shape alone.
function makeTarget(overrides = {}) {
  return {
    target_type: "pokemon_set",
    target_id: "set-1",
    name: "Set One",
    era: "Scarlet & Violet",
    logo_image_url: "https://images.example/set-1-logo.png",
    setRipV1: { score: 82.4, rank: 1, tier: "A", cohortSize: 41, rankable: true },
    checklistSetValue: 1248.62,
    currentChecklistSetValueDate: "2026-07-27",
    ...overrides,
  };
}

test("spotlight reads the public Set RIP V1 score, tier, rank and cohort size", () => {
  const spotlight = selectLandingHeroSpotlight([makeTarget()]);

  assert.equal(spotlight.score, 82.4);
  assert.equal(spotlight.scoreLabel, "Set RIP");
  assert.equal(spotlight.tier, "A");
  assert.equal(spotlight.rank, 1);
  assert.equal(spotlight.cohortSize, 41);
  assert.equal(spotlight.name, "Set One");
  assert.equal(spotlight.setValue, 1248.62);
  assert.equal(spotlight.setValueAsOf, "2026-07-27");
  assert.equal(
    spotlight.href,
    "/Explore/rip-statistics?target_type=pokemon_set&target_id=set-1",
  );
});

test("a legacy/Overall RIP disagreement cannot alter ordering: setRipV1 alone decides", () => {
  const spotlight = selectLandingHeroSpotlight([
    makeTarget({
      target_id: "b",
      name: "B",
      setRipV1: { score: 10, rank: 2, tier: "F", cohortSize: 41, rankable: true },
      // Loud legacy/Overall RIP fields claiming B should be #1 — must be ignored.
      overallRipV10: { relativeScore: 999, rank: 1, tier: "S" },
      rip: { score: 999, relativeScore: 999, rank: 1, tier: "S" },
    }),
    makeTarget({
      target_id: "a",
      name: "A",
      setRipV1: { score: 90, rank: 1, tier: "A", cohortSize: 41, rankable: true },
      overallRipV10: { relativeScore: 1, rank: 2, tier: "F" },
    }),
  ]);

  assert.equal(spotlight.targetId, "a");
});

test("an unrankable/missing setRipV1 is dropped, never invented from another metric", () => {
  const unrankable = makeTarget({
    target_id: "unrankable",
    setRipV1: { score: 55, rank: null, tier: null, cohortSize: 41, rankable: false },
  });
  const missingBlock = {
    target_type: "pokemon_set",
    target_id: "missing",
    name: "Missing Set RIP",
    logo_image_url: "https://images.example/logo.png",
    // Rich Overall RIP / legacy data, but no setRipV1 at all.
    overallRipV10: { relativeScore: 95, rank: 1, tier: "S" },
    rip: { score: 95, relativeScore: 95, rank: 1, tier: "S" },
    pack_score: 91,
    relative_pack_score: 99.9,
    pack_rank: 1,
  };

  assert.equal(selectLandingHeroSpotlight([unrankable]), null);
  assert.deepEqual(selectLandingHeroEntries([unrankable]), []);
  assert.equal(selectLandingHeroSpotlight([missingBlock]), null);
  assert.deepEqual(selectLandingHeroEntries([missingBlock]), []);
});

test("rankable false with a numeric rank still drops the entry", () => {
  const target = makeTarget({
    setRipV1: { score: 70, rank: 1, tier: "A", cohortSize: 41, rankable: false },
  });
  assert.equal(selectLandingHeroSpotlight([target]), null);
});

test("the top-ranked set wins by setRipV1.rank, and an unranked scored set sorts behind every ranked one", () => {
  const spotlight = selectLandingHeroSpotlight([
    makeTarget({ target_id: "b", name: "B", setRipV1: { score: 90, rank: 3, tier: "A", cohortSize: 41, rankable: true } }),
    makeTarget({ target_id: "c", name: "C", setRipV1: { score: 99, rank: null, tier: "S", cohortSize: 41, rankable: false } }),
    makeTarget({ target_id: "a", name: "A", setRipV1: { score: 70, rank: 1, tier: "A", cohortSize: 41, rankable: true } }),
  ]);

  assert.equal(spotlight.targetId, "a");
});

test("score then name break ties when setRipV1.rank is equal", () => {
  const entries = selectLandingHeroEntries([
    makeTarget({ target_id: "z", name: "Z Set", setRipV1: { score: 50, rank: 1, tier: "A", cohortSize: 10, rankable: true } }),
    makeTarget({ target_id: "y", name: "Y Set", setRipV1: { score: 60, rank: 1, tier: "A", cohortSize: 10, rankable: true } }),
  ]);
  assert.deepEqual(entries.map((entry) => entry.targetId), ["y", "z"]);
});

test("a missing checklist value leaves setValue null rather than zero", () => {
  const spotlight = selectLandingHeroSpotlight([
    makeTarget({ checklistSetValue: null, currentChecklistSetValueDate: null }),
  ]);

  assert.equal(spotlight.setValue, null);
  assert.equal(spotlight.setValueAsOf, null);
});

test("the ranked strip continues the ranking after the spotlight instead of repeating it", () => {
  const targets = [1, 2, 3, 4, 5, 6].map((rank) =>
    makeTarget({
      target_id: `set-${rank}`,
      name: `Set ${rank}`,
      setRipV1: { score: 100 - rank, rank, tier: "A", cohortSize: 41, rankable: true },
    }),
  );

  const strip = selectLandingRankedStrip(targets, 4);

  assert.deepEqual(
    strip.map((entry) => entry.rank),
    [2, 3, 4, 5],
  );
});

test("no targets yields no spotlight and an empty strip", () => {
  assert.equal(selectLandingHeroSpotlight([]), null);
  assert.deepEqual(selectLandingRankedStrip(null), []);
  assert.equal(selectLandingHeroSpotlight(undefined), null);
});

test("hero image url and logo/symbol are carried through for hero-visual fallback", () => {
  const entry = selectLandingHeroSpotlight([
    makeTarget({
      canonical_key: "paradoxRift",
      hero_image_url: "https://images.example/set-1-hero.png",
      symbol_image_url: "https://images.example/set-1-symbol.png",
    }),
  ]);
  assert.equal(entry.canonicalKey, "paradoxRift");
  assert.equal(entry.heroImageUrl, "https://images.example/set-1-hero.png");
  assert.equal(entry.logoUrl, "https://images.example/set-1-logo.png");
  assert.equal(entry.symbolUrl, "https://images.example/set-1-symbol.png");
});

test("landing metrics come from published mean/median fields, never Financial RIP internals", () => {
  const target = makeTarget({
    target_id: "current",
    canonical_key: "paradoxRift",
    name: "Current",
    mean_value: 5.25,
    median_value: 1.75,
    // Financial RIP internals present but must never be read onto the entry.
    publicRipContractV8: {
      financialRip: {
        relativeScore: 77,
        sourceRun: { simulationCount: 1000000 },
        distributionDisclosures: { p05Value: 0.2 },
        components: {
          realisticUpside: { raw: { p95ThresholdValue: 14 } },
          jackpotUpside: { raw: { p99ThresholdValue: 80 } },
        },
      },
    },
  });
  const entry = selectLandingHeroSpotlight([target]);
  assert.equal(entry.score, 82.4);
  assert.equal(entry.meanValue, 5.25);
  assert.equal(entry.medianValue, 1.75);
  assert.equal(entry.financialRipScore, undefined);
  assert.equal(entry.simulationCount, undefined);
  assert.equal(entry.p05Value, undefined);
  assert.equal(entry.p95Value, undefined);
  assert.equal(entry.p99Value, undefined);
  assert.equal(entry.hasCanonicalOverallRipV7, undefined);
});

test("absent landing metrics remain unavailable", () => {
  const entry = selectLandingHeroSpotlight([makeTarget()]);
  assert.equal(entry.meanValue, null);
  assert.equal(entry.medianValue, null);
});
