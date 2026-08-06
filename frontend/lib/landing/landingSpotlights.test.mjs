import assert from "node:assert/strict";
import test from "node:test";

import {
  rankSetIntelligenceCandidates,
  readDesirability,
  selectOpeningSpotlight,
} from "./landingSpotlights.mjs";

function makeEntry(overrides = {}) {
  return {
    key: `set:${overrides.name || "one"}`,
    name: "Set One",
    logoUrl: "https://images.example/logo.png",
    symbolUrl: null,
    rank: 1,
    score: 90,
    tier: "S",
    cohortSize: 22,
    setValue: 1000,
    setValueAsOf: "2026-08-02",
    packCost: 4.5,
    meanValue: 5.4,
    probProfit: 0.42,
    // Canonical availability is what makes an entry eligible. There is
    // deliberately no `decisionLabel` in the baseline fixture: eligibility must
    // not depend on retired interpretation copy.
    hasCanonicalOverallRipV7: true,
    universalDesirabilityScore: 70,
    collectorAppealScore: 60,
    desirabilityIsFallback: false,
    ...overrides,
  };
}

/* ------------------------------------------------ role 1: opening spotlight --- */

test("the opening spotlight is the published rank #1, not whatever sorted first", () => {
  const entries = [
    makeEntry({ name: "Second", rank: 2, score: 99 }),
    makeEntry({ name: "First", rank: 1, score: 40 }),
    makeEntry({ name: "Third", rank: 3, score: 95 }),
  ];

  assert.equal(selectOpeningSpotlight(entries).name, "First");
});

test("the opening spotlight follows the ranking when the published order changes", () => {
  const before = [makeEntry({ name: "A", rank: 1 }), makeEntry({ name: "B", rank: 2 })];
  const after = [makeEntry({ name: "A", rank: 2 }), makeEntry({ name: "B", rank: 1 })];

  assert.equal(selectOpeningSpotlight(before).name, "A");
  assert.equal(selectOpeningSpotlight(after).name, "B");
});

test("no published rank #1 means no opening spotlight, never a substitute", () => {
  assert.equal(selectOpeningSpotlight([makeEntry({ rank: 2 }), makeEntry({ name: "x", rank: 3 })]), null);
  assert.equal(selectOpeningSpotlight([makeEntry({ rank: null })]), null);
  assert.equal(selectOpeningSpotlight([]), null);
  assert.equal(selectOpeningSpotlight(null), null);
});

test("a set missing a logo or a score is never promoted to the hero", () => {
  assert.equal(selectOpeningSpotlight([makeEntry({ logoUrl: null, symbolUrl: null })]), null);
  assert.equal(selectOpeningSpotlight([makeEntry({ score: null })]), null);
  assert.equal(
    selectOpeningSpotlight([makeEntry({ logoUrl: null, symbolUrl: "https://x/symbol.png" })]).name,
    "Set One",
    "a symbol is an acceptable stand-in for a missing logo"
  );
});

/* --------------------------------------- role 2: set intelligence spotlight --- */

test("the desirability read prefers the authoritative lens and distrusts fallbacks", () => {
  assert.deepEqual(readDesirability(makeEntry()), { score: 70, source: "universalSetDesirability" });
  assert.deepEqual(
    readDesirability(makeEntry({ universalDesirabilityScore: null })),
    { score: 60, source: "collectorAppeal" },
    "CA7 is the documented backup when the universal score is absent"
  );
  assert.deepEqual(
    readDesirability(makeEntry({ desirabilityIsFallback: true })),
    { score: null, source: null },
    "a backend-substituted desirability is not a measurement and must not win the slot"
  );
});

test("the set intelligence spotlight excludes the opening spotlight", () => {
  const opening = makeEntry({ name: "Opening", rank: 1, universalDesirabilityScore: 99 });
  const other = makeEntry({ name: "Other", rank: 5, universalDesirabilityScore: 80 });

  const candidates = rankSetIntelligenceCandidates([opening, other], { excludeKey: opening.key });

  assert.equal(candidates.length, 1);
  assert.equal(candidates[0].name, "Other", "the highest desirability is skipped when it is the hero set");
});

test("the set intelligence spotlight is NOT simply the second-ranked set", () => {
  const opening = makeEntry({ name: "Opening", rank: 1, universalDesirabilityScore: 50 });
  const runnerUp = makeEntry({ name: "RunnerUp", rank: 2, universalDesirabilityScore: 55 });
  const desirable = makeEntry({ name: "Desirable", rank: 9, universalDesirabilityScore: 95 });

  const candidates = rankSetIntelligenceCandidates([opening, runnerUp, desirable], {
    excludeKey: opening.key,
  });

  assert.equal(candidates[0].name, "Desirable");
  assert.notEqual(candidates[0].name, "RunnerUp");
});

test("candidates missing the data the section renders are not offered at all", () => {
  const complete = makeEntry({ name: "Complete", rank: 4, universalDesirabilityScore: 60 });
  const rejects = [
    makeEntry({ name: "NoValue", rank: 5, setValue: null, universalDesirabilityScore: 99 }),
    makeEntry({ name: "NoCost", rank: 6, packCost: null, universalDesirabilityScore: 98 }),
    makeEntry({ name: "NoMean", rank: 7, meanValue: null, universalDesirabilityScore: 97 }),
    makeEntry({
      name: "NoCanonicalRip",
      rank: 8,
      hasCanonicalOverallRipV7: false,
      universalDesirabilityScore: 96,
    }),
    makeEntry({ name: "NoLogo", rank: 9, logoUrl: null, symbolUrl: null, universalDesirabilityScore: 95 }),
  ];

  const candidates = rankSetIntelligenceCandidates([...rejects, complete]);

  assert.deepEqual(candidates.map((c) => c.name), ["Complete"]);
});

test("the fallback chain is desirability, then set value, then opening rank", () => {
  const noDesirability = (name, rank, setValue) =>
    makeEntry({
      name,
      rank,
      setValue,
      universalDesirabilityScore: null,
      collectorAppealScore: null,
    });

  const valueFallback = rankSetIntelligenceCandidates([
    noDesirability("Cheap", 2, 100),
    noDesirability("Rich", 8, 9000),
  ]);
  assert.deepEqual(
    valueFallback.map((c) => c.name),
    ["Rich", "Cheap"],
    "with no trustworthy desirability anywhere, highest set value leads"
  );

  const mixed = rankSetIntelligenceCandidates([
    noDesirability("NoScore", 2, 9000),
    makeEntry({ name: "Scored", rank: 8, universalDesirabilityScore: 10, setValue: 100 }),
  ]);
  assert.equal(
    mixed[0].name,
    "Scored",
    "any trustworthy desirability outranks the value fallback, however low"
  );
});

test("ties break deterministically on market date, then set value, then key", () => {
  const base = { universalDesirabilityScore: 80, rank: 5 };
  const older = makeEntry({ ...base, name: "Older", setValueAsOf: "2026-08-01", setValue: 9999 });
  const newer = makeEntry({ ...base, name: "Newer", setValueAsOf: "2026-08-02", setValue: 10 });

  assert.equal(rankSetIntelligenceCandidates([older, newer])[0].name, "Newer");

  const richer = makeEntry({ ...base, name: "Richer", setValue: 5000 });
  const poorer = makeEntry({ ...base, name: "Poorer", setValue: 5 });
  assert.equal(rankSetIntelligenceCandidates([poorer, richer])[0].name, "Richer");

  const a = makeEntry({ ...base, name: "aaa", setValue: 100 });
  const b = makeEntry({ ...base, name: "bbb", setValue: 100 });
  assert.equal(
    rankSetIntelligenceCandidates([b, a])[0].key,
    a.key,
    "identical published values resolve on stable key order, so the page is reproducible"
  );
});

test("no eligible candidate yields an empty list rather than a substituted set", () => {
  assert.deepEqual(rankSetIntelligenceCandidates([]), []);
  assert.deepEqual(rankSetIntelligenceCandidates(null), []);
  const only = makeEntry({ name: "Only", rank: 1 });
  assert.deepEqual(rankSetIntelligenceCandidates([only], { excludeKey: only.key }), []);
});

/* ------------------------------- eligibility is canonical, not editorial --- */

test("a set with canonical V7 but no interpretation fields is still eligible", () => {
  const entry = makeEntry({
    name: "CanonicalOnly",
    rank: 4,
    hasCanonicalOverallRipV7: true,
    // Every retired interpretation field, explicitly absent.
    decisionLabel: null,
    decisionSeverity: null,
    interpretationLabel: null,
    interpretationSummary: null,
    leaderboard_label: null,
    canonical_recommendation_header: null,
    recommendation_severity: null,
  });

  assert.deepEqual(
    rankSetIntelligenceCandidates([entry]).map((c) => c.name),
    ["CanonicalOnly"],
    "the section renders a canonical score, so a canonical score is what it may require"
  );
});

test("a set with interpretation fields but no canonical V7 is rejected", () => {
  const entry = makeEntry({
    name: "VerdictOnly",
    rank: 4,
    hasCanonicalOverallRipV7: false,
    decisionLabel: "Elite but swingy",
    interpretationLabel: "Elite but swingy",
    interpretationSummary: "A retired engine's read.",
    leaderboard_label: "STRONG VALUE",
    canonical_recommendation_header: "Strong value, high variance",
    recommendation_severity: "positive",
  });

  assert.deepEqual(
    rankSetIntelligenceCandidates([entry]),
    [],
    "a superseded verdict is not a substitute for the score the section shows"
  );
});

test("changing interpretation values cannot affect eligibility or ordering", () => {
  const build = (interpretation) => [
    makeEntry({ name: "A", rank: 2, universalDesirabilityScore: 90, ...interpretation }),
    makeEntry({ name: "B", rank: 3, universalDesirabilityScore: 80, ...interpretation }),
    makeEntry({ name: "C", rank: 4, universalDesirabilityScore: 70, ...interpretation }),
  ];

  const baseline = rankSetIntelligenceCandidates(build({}));

  const variants = [
    { decisionLabel: "Strong value", recommendation_severity: "positive" },
    { decisionLabel: null, interpretationLabel: "Elite but swingy" },
    { interpretationSummary: "x", leaderboard_label: "AVOID", recommendation_severity: "negative" },
    { canonical_recommendation_header: "Avoid, weak economics", decisionSeverity: "danger" },
  ];

  for (const variant of variants) {
    assert.deepEqual(
      rankSetIntelligenceCandidates(build(variant)).map((c) => c.name),
      baseline.map((c) => c.name),
      `interpretation variant ${JSON.stringify(variant)} must be inert`
    );
  }

  assert.deepEqual(baseline.map((c) => c.name), ["A", "B", "C"]);
});

test("the candidate list is deduplicated across fallback tiers", () => {
  const candidates = rankSetIntelligenceCandidates([
    makeEntry({ name: "A", rank: 2, universalDesirabilityScore: 90 }),
    makeEntry({ name: "B", rank: 3, universalDesirabilityScore: null, collectorAppealScore: null }),
  ]);

  assert.deepEqual(candidates.map((c) => c.name), ["A", "B"]);
  assert.equal(new Set(candidates.map((c) => c.key)).size, candidates.length);
});
