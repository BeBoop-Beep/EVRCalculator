import assert from "node:assert/strict";
import test from "node:test";

import {
  selectLandingHeroEntries,
  selectLandingHeroSpotlight,
  selectLandingRankedStrip,
} from "./landingHeroSpotlight.mjs";

function makeTarget(overrides = {}) {
  return {
    target_type: "pokemon_set",
    target_id: "set-1",
    name: "Set One",
    era: "Scarlet & Violet",
    logo_image_url: "https://images.example/set-1-logo.png",
    overallRipV7: { score: 71.2, relativeScore: 82.4, rank: 1, tier: "A", cohortSize: 41 },
    // Overall RIP v4, still served for audit consumers and never read here.
    rip: { score: 12.3, relativeScore: 4.5, rank: 40, tier: "F", cohortSize: 41 },
    checklistSetValue: 1248.62,
    currentChecklistSetValueDate: "2026-07-27",
    ...overrides,
  };
}

test("spotlight reads the canonical relative RIP score, tier, rank and cohort size", () => {
  const spotlight = selectLandingHeroSpotlight([makeTarget()]);

  assert.equal(spotlight.score, 82.4);
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

test("the entry carries canonical availability and no interpretation copy", () => {
  const spotlight = selectLandingHeroSpotlight([
    makeTarget({
      // Every retired interpretation-engine field, present and loud.
      leaderboard_label: "STRONG VALUE PROFILE",
      canonical_recommendation_header: "Strong value, high variance",
      recommendation_severity: "positive",
      interpretationLabel: "Elite but swingy",
      interpretationSummary: "A verdict from a model the site no longer publishes.",
    }),
  ]);

  assert.equal(
    spotlight.hasCanonicalOverallRipV7,
    true,
    "the boolean must come from the canonical hero result"
  );
  for (const field of [
    "decisionLabel",
    "decisionSeverity",
    "interpretationLabel",
    "interpretationSummary",
  ]) {
    assert.equal(spotlight[field], undefined, `${field} must not reach the landing page`);
  }
});

test("canonical availability tracks the canonical score, not any legacy field", () => {
  // A target with a full set of interpretation copy but no canonical V7 does
  // not become an entry at all, so nothing downstream can read a `true` from it.
  const verdictOnly = {
    target_type: "pokemon_set",
    target_id: "verdict-only",
    name: "Verdict Only",
    logo_image_url: "https://images.example/logo.png",
    leaderboard_label: "STRONG VALUE",
    canonical_recommendation_header: "Strong value",
    recommendation_severity: "positive",
    interpretationLabel: "Elite but swingy",
    rip: { score: 88, relativeScore: 91, rank: 1, tier: "S", cohortSize: 41 },
  };

  assert.deepEqual(selectLandingHeroEntries([verdictOnly]), []);
});

test("a set carrying only the legacy cohort fields is never promoted to the hero", () => {
  const legacyOnly = {
    target_type: "pokemon_set",
    target_id: "legacy",
    name: "Legacy Set",
    pack_score: 91,
    relative_pack_score: 99.9,
    pack_rank: 1,
    pack_tier: "S",
  };

  assert.equal(selectLandingHeroSpotlight([legacyOnly]), null);
  assert.deepEqual(selectLandingHeroEntries([legacyOnly]), []);
});

test("the absolute model score is never substituted when the relative score is missing", () => {
  const absoluteOnly = makeTarget({
    target_id: "absolute-only",
    overallRipV7: { score: 64.8, relativeScore: null, rank: 2, tier: "B", cohortSize: 41 },
  });

  assert.equal(selectLandingHeroSpotlight([absoluteOnly]), null);
});

test("the top-ranked set wins, and an unranked scored set sorts behind every ranked one", () => {
  const spotlight = selectLandingHeroSpotlight([
    makeTarget({ target_id: "b", name: "B", overallRipV7: { relativeScore: 90, rank: 3, tier: "A" } }),
    makeTarget({ target_id: "c", name: "C", overallRipV7: { relativeScore: 99, rank: null, tier: "S" } }),
    makeTarget({ target_id: "a", name: "A", overallRipV7: { relativeScore: 70, rank: 1, tier: "A" } }),
  ]);

  assert.equal(spotlight.targetId, "a");
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
      overallRipV7: { relativeScore: 100 - rank, rank, tier: "A", cohortSize: 41 },
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
