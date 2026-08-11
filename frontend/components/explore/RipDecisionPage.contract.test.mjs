import assert from "node:assert/strict";
import fs from "node:fs";
import path from "node:path";
import test from "node:test";
import { buildRipDecisionModel } from "./ripDecisionModel.mjs";
import { getRipQualitativeLabel } from "./ripQualitativeLabel.mjs";
import { RANK_CONFIG, topPercentToTier } from "../../constants/rankConfig.js";

function canonicalOf({ overallRank = 9, cohort = 22, tier = null, financialRank = 10, collectorRank = 3 } = {}) {
  return {
    overall: { relativeScore: 76.3, absoluteScore: 0.42, rank: overallRank, rankedSetCount: cohort, tier },
    financialRip: { relativeScore: 44, absoluteScore: 34.4, rank: financialRank, rankedSetCount: cohort },
    collectorAppeal: { relativeScore: 88, absoluteScore: 53.2, rank: collectorRank, rankedSetCount: cohort },
  };
}

const pagePath = path.resolve(path.dirname(new URL(import.meta.url).pathname.slice(1)), "RipDecisionPage.jsx");
const shellPath = path.resolve(path.dirname(new URL(import.meta.url).pathname.slice(1)), "RipStatisticsPageClient.jsx");

test("RIP page follows the locked four-section narrative and ends after opening odds", () => {
  const source = fs.readFileSync(pagePath, "utf8");
  const markers = ["decision", "why-it-ranks", "chase-cards", "opening-odds"].map((marker) => source.indexOf(`data-rip-section=\"${marker}\"`));
  assert.ok(markers.every((index) => index >= 0));
  assert.deepEqual([...markers].sort((a, b) => a - b), markers);
  for (const retired of ["7D Movers", "Set Value Trend", "Market Snapshot", "Sealed Market", "RIP Summary", "Opening Outcomes", "Products placeholder"]) assert.ok(!source.includes(retired));
});

test("decision metrics use mean, median, pack cost, and authoritative profit probability", () => {
  const model = buildRipDecisionModel({
    canonical: { overall: { relativeScore: 100, rank: 1, rankedSetCount: 22 }, financialRip: {}, collectorAppeal: {} },
    summary: { pack_cost: 11.03, mean_value: 5.55, median_value: 1.97, prob_profit: 0.103 },
  });
  assert.equal(model.packCost, 11.03);
  assert.equal(model.expectedValue, 5.55);
  assert.equal(model.typicalOpening, 1.97);
  assert.equal(model.recoverCostProbability, 0.103);
});

test("canonical current-model scores are used without legacy fallback", () => {
  const model = buildRipDecisionModel({
    canonical: {
      overall: { relativeScore: 91, absoluteScore: 0.55, rank: 2, rankedSetCount: 22 },
      financialRip: { relativeScore: 80, absoluteScore: 42, rank: 4, rankedSetCount: 22 },
      collectorAppeal: { relativeScore: 88, absoluteScore: 67, rank: 2, rankedSetCount: 22 },
    },
    summary: { rip: { score: 12 }, ripCore: { score: 13 } },
  });
  assert.equal(model.overall.relativeScore, 91);
  assert.equal(model.financial.absoluteScore, 42);
  assert.equal(model.collector.absoluteScore, 67);
});

test("opening summary exposes only an authoritative exact rarity denominator", () => {
  const model = buildRipDecisionModel({ pullRateAssumptions: { rows: [{ rarity: "Special Illustration Rare", rarityOddsDenominator: 86 }] } });
  assert.deepEqual(model.openingOdds, [{ label: "Special Illustration Rare", denominator: 86 }]);
});

test("opening summary selects up to three authoritative consumer-relevant rarity rows", () => {
  const model = buildRipDecisionModel({
    pullRateAssumptions: {
      groups: [{
        key: "hit_rarity_model",
        rows: [
          { rarity: "double rare", rarityOddsDenominator: 6 },
          { rarity: "hyper rare", rarityOddsDenominator: 139 },
          { rarity: "illustration rare", rarityOddsDenominator: 13 },
          { rarity: "special illustration rare", rarityOddsDenominator: 86 },
          { rarity: "ultra rare", rarityOddsDenominator: 15 },
        ],
      }],
    },
  });
  assert.deepEqual(model.openingOdds, [
    { label: "Illustration Rare", denominator: 13 },
    { label: "Ultra Rare", denominator: 15 },
    { label: "Special Illustration Rare", denominator: 86 },
  ]);
});

test("invalid zero-count and zero-odds fallbacks are never presented", () => {
  const source = fs.readFileSync(pagePath, "utf8");
  assert.ok(source.includes('Number(cardCount) > 0'));
  assert.ok(source.includes('"View all cards →"'));
  assert.ok(source.includes('Number(odds) > 0'));
  assert.ok(source.includes('"Odds unavailable"'));
  const model = buildRipDecisionModel({ pullRateAssumptions: { rows: [{ rarity: "Special Illustration Rare", rarityOddsDenominator: 0 }] } });
  assert.deepEqual(model.openingOdds, []);
});

test("qualitative verdict label is a relabelling of the canonical tier, not a second model", () => {
  for (const tier of Object.keys(RANK_CONFIG)) {
    const label = getRipQualitativeLabel({ tier });
    assert.equal(label.tier, tier);
    assert.equal(label.color, RANK_CONFIG[tier].color);
    assert.ok(/ RIP$/.test(label.label));
  }
  // Published tier wins over rank position — one authoritative classification.
  assert.equal(getRipQualitativeLabel({ tier: "S", rank: 22, cohortSize: 22 }).tier, "S");
  // Without a published tier the SAME cut points recover it from rank/cohort.
  assert.equal(getRipQualitativeLabel({ rank: 9, cohortSize: 22 }).tier, topPercentToTier((9 / 22) * 100));
  assert.equal(getRipQualitativeLabel({}), null);
  assert.equal(getRipQualitativeLabel({ tier: "not-a-tier" }), null);
});

test("verdict headline and qualitative label stay dynamic and per-set data driven", () => {
  const source = fs.readFileSync(pagePath, "utf8");
  assert.ok(source.includes("Modern Set to Rip Right Now"));
  assert.ok(source.includes("model.overall.rank"));
  assert.ok(source.includes("model.qualitativeLabel.label"));
  // No per-set editorial copy anywhere on the page.
  assert.ok(!/Ascended Heroes/i.test(source));
  const strong = buildRipDecisionModel({ canonical: canonicalOf({ overallRank: 1, cohort: 22 }) });
  const weak = buildRipDecisionModel({ canonical: canonicalOf({ overallRank: 21, cohort: 22 }) });
  assert.notEqual(strong.qualitativeLabel.label, weak.qualitativeLabel.label);
  assert.equal(buildRipDecisionModel({ canonical: { overall: {} } }).qualitativeLabel, null);
});

test("Why It Ranks renders helps, hurts and a dominant result, and stacks on mobile", () => {
  const source = fs.readFileSync(pagePath, "utf8");
  assert.ok(source.includes('data-rip-driver={driver.key}'));
  assert.ok(source.includes('data-rip-driver="result"'));
  assert.ok(source.includes("driver.standingLabel"));
  // Single column by default, three only from the md breakpoint up.
  assert.ok(source.includes("md:grid-cols-[minmax(0,1fr)_minmax(0,1fr)_minmax(0,1.1fr)]"));
  assert.ok(source.includes('index ? "border-t border-[var(--border-subtle)] md:border-l md:border-t-0"'));
  // Result outweighs either driver typographically (3xl vs lg).
  assert.ok(source.includes("md:text-3xl"));
});

test("stronger driver is assigned from the data, so neither factor is always Helps", () => {
  const collectorLifts = buildRipDecisionModel({ canonical: canonicalOf({ financialRank: 10, collectorRank: 3 }) });
  assert.equal(collectorLifts.drivers.mode, "contrast");
  assert.deepEqual(collectorLifts.drivers.drivers.map((d) => [d.key, d.standingLabel]), [["collector", "Helps"], ["financial", "Hurts"]]);

  const financialLifts = buildRipDecisionModel({ canonical: canonicalOf({ financialRank: 2, collectorRank: 18 }) });
  assert.equal(financialLifts.drivers.mode, "contrast");
  assert.deepEqual(financialLifts.drivers.drivers.map((d) => [d.key, d.standingLabel]), [["financial", "Helps"], ["collector", "Hurts"]]);

  assert.notEqual(collectorLifts.takeaway, financialLifts.takeaway);
});

test("near-equal drivers report a balanced profile instead of a manufactured divide", () => {
  const balanced = buildRipDecisionModel({ canonical: canonicalOf({ overallRank: 9, financialRank: 8, collectorRank: 9 }) });
  assert.equal(balanced.drivers.mode, "balanced");
  assert.deepEqual(balanced.drivers.drivers.map((d) => d.standingLabel), ["Stronger driver", "Secondary driver"]);
  assert.ok(!/Helps|Hurts/.test(JSON.stringify(balanced.drivers.drivers)));
  assert.match(balanced.takeaway, /balanced profile/);

  const bothStrong = buildRipDecisionModel({ canonical: canonicalOf({ overallRank: 2, financialRank: 2, collectorRank: 3 }) });
  assert.equal(bothStrong.drivers.mode, "balanced");
  assert.match(bothStrong.takeaway, /Both financial quality and collector appeal/);

  const unavailable = buildRipDecisionModel({ canonical: { overall: {}, financialRip: {}, collectorAppeal: {} } });
  assert.equal(unavailable.drivers.mode, "unavailable");
  assert.match(unavailable.takeaway, /unavailable/);
});

test("drivers and result keep absolute scores, ranks and the relative index distinct", () => {
  const model = buildRipDecisionModel({ canonical: canonicalOf() });
  const byKey = Object.fromEntries(model.drivers.drivers.map((d) => [d.key, d]));
  assert.equal(byKey.financial.score, 34.4);
  assert.equal(byKey.financial.rank, 10);
  assert.equal(byKey.collector.score, 53.2);
  assert.equal(byKey.collector.rank, 3);
  assert.equal(model.overall.relativeScore, 76.3);

  const source = fs.readFileSync(pagePath, "utf8");
  assert.ok(source.includes("Relative RIP Index {score(model.overall.relativeScore)}"));
  // The relative index is a cohort position, never dressed up as an absolute score.
  assert.ok(!source.includes("Relative RIP Index {score(model.overall.relativeScore)} / 100"));
  assert.ok(!/\/\s*100/.test(source));
});

test("no chart is introduced between the verdict and Why It Ranks", () => {
  const source = fs.readFileSync(pagePath, "utf8");
  const between = source.slice(source.indexOf('data-rip-section="decision"'), source.indexOf('data-rip-section="chase-cards"'));
  for (const banned of ["Chart", "recharts", "<svg", "Sparkline", "Gauge chart", "Donut", "Radial"]) assert.ok(!between.includes(banned), banned);
});

test("persistent title card keeps identity and restores authoritative context metadata", () => {
  const source = fs.readFileSync(shellPath, "utf8");
  for (const marker of ["data-set-context-header", "data-set-context-release-date", "data-set-context-total-cards", "data-set-context-set-value", "data-set-context-rip-rank", "selectedName", "selectedTarget?.era"]) assert.ok(source.includes(marker));
  for (const label of ['label: "RIP"', 'label: "Cards & Products"', 'label: "Pull Rates"', 'label: "Analysis"']) assert.ok(source.includes(label));
});
