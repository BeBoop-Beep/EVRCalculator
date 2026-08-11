import assert from "node:assert/strict";
import fs from "node:fs";
import path from "node:path";
import test from "node:test";
import { buildRipDecisionModel } from "./ripDecisionModel.mjs";

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

test("invalid zero-count and zero-odds fallbacks are never presented", () => {
  const source = fs.readFileSync(pagePath, "utf8");
  assert.ok(source.includes('Number(cardCount) > 0'));
  assert.ok(source.includes('"View all cards →"'));
  assert.ok(source.includes('Number(odds) > 0'));
  assert.ok(source.includes('"Odds unavailable"'));
  const model = buildRipDecisionModel({ pullRateAssumptions: { rows: [{ rarity: "Special Illustration Rare", rarityOddsDenominator: 0 }] } });
  assert.deepEqual(model.openingOdds, []);
});

test("persistent title card keeps identity and restores authoritative context metadata", () => {
  const source = fs.readFileSync(shellPath, "utf8");
  for (const marker of ["data-set-context-header", "data-set-context-release-date", "data-set-context-total-cards", "data-set-context-set-value", "data-set-context-rip-rank", "selectedName", "selectedTarget?.era"]) assert.ok(source.includes(marker));
  for (const label of ['label: "RIP"', 'label: "Cards & Products"', 'label: "Pull Rates"', 'label: "Analysis"']) assert.ok(source.includes(label));
});
