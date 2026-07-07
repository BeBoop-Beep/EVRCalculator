import assert from "node:assert/strict";
import test from "node:test";

import { normalizePokemonSetInsightsPayload } from "./pokemonSetInsightsClient.js";

function makeInsightsPayload(overrides = {}) {
  return {
    set: { id: "set-1", name: "Prismatic Evolutions", slug: "prismaticEvolutions" },
    summary: { relativeProfitScore: 60, profitRank: 5, profitTier: "Good", packCost: 4.99 },
    recommendation: { label: "Strong Buy", summary: "This set beats its pack cost more often than most." },
    ripScore: { score: 71.4, rank: 3, tier: "Strong Buy" },
    interpretation: { meta: { packScore: { label: "Strong Buy" } } },
    ripStatistics: { packPaths: { normal: { count: 10 } }, normalPackStates: { hit: 0.6 } },
    outcomeDistribution: {
      percentiles: [{ percentile: 50, value: 5.5 }],
      distributionBins: [{ binFloor: 0, binCeiling: 5, probability: 0.4 }],
      thresholdBins: [{ thresholdFloor: 5, thresholdCeiling: 10, probability: 0.1 }],
    },
    simulationDrivers: [{ cardName: "Chase Card 0", evContribution: 1.5 }],
    rarityContribution: [{ rarityBucket: "Rarity 0", totalSampledValue: 100 }],
    historyTrend: [{ date: "2026-06-01", meanValue: 5.0 }],
    desirability: { openingDesirabilityScore: 77 },
    desirabilityValidation: { cardAppealScore: 91.2 },
    meta: { source: "pokemon_set_page_snapshot_latest", updatedAt: "2026-06-30T00:00:00+00:00", warnings: [] },
    ...overrides,
  };
}

test("normalizePokemonSetInsightsPayload returns set, summary, recommendation, and RIP score", () => {
  const normalized = normalizePokemonSetInsightsPayload(makeInsightsPayload());

  assert.deepEqual(normalized.set, { id: "set-1", name: "Prismatic Evolutions", slug: "prismaticEvolutions" });
  assert.equal(normalized.summary.relativeProfitScore, 60);
  assert.equal(normalized.recommendation.label, "Strong Buy");
  assert.equal(normalized.ripScore.score, 71.4);
  assert.equal(normalized.meta.source, "pokemon_set_page_snapshot_latest");
});

test("normalizePokemonSetInsightsPayload returns RIP breakdown and decision-signal inputs (interpretation + ripStatistics)", () => {
  const normalized = normalizePokemonSetInsightsPayload(makeInsightsPayload());

  assert.equal(normalized.interpretation.meta.packScore.label, "Strong Buy");
  assert.equal(normalized.ripStatistics.normalPackStates.hit, 0.6);
});

test("normalizePokemonSetInsightsPayload returns outcome distribution, simulation drivers, and contribution arrays", () => {
  const normalized = normalizePokemonSetInsightsPayload(makeInsightsPayload());

  assert.equal(normalized.outcomeDistribution.percentiles.length, 1);
  assert.equal(normalized.outcomeDistribution.distributionBins[0].binFloor, 0);
  assert.equal(normalized.outcomeDistribution.thresholdBins[0].thresholdFloor, 5);
  assert.equal(normalized.simulationDrivers[0].cardName, "Chase Card 0");
  assert.equal(normalized.rarityContribution[0].rarityBucket, "Rarity 0");
  assert.equal(normalized.historyTrend[0].meanValue, 5.0);
});

test("normalizePokemonSetInsightsPayload returns desirability proof fields (excluding card validation rows)", () => {
  const normalized = normalizePokemonSetInsightsPayload(makeInsightsPayload());

  assert.equal(normalized.desirability.openingDesirabilityScore, 77);
  assert.equal(normalized.desirabilityValidation.cardAppealScore, 91.2);
  assert.equal(normalized.desirabilityValidation.cards, undefined);
});

test("normalizePokemonSetInsightsPayload is defensive against a completely empty payload", () => {
  const normalized = normalizePokemonSetInsightsPayload({});

  assert.deepEqual(normalized.set, { id: null, name: null, slug: null });
  assert.deepEqual(normalized.summary, {});
  assert.deepEqual(normalized.recommendation, {});
  assert.deepEqual(normalized.ripScore, {});
  assert.deepEqual(normalized.interpretation, {});
  assert.deepEqual(normalized.ripStatistics, {});
  assert.deepEqual(normalized.outcomeDistribution, { percentiles: [], distributionBins: [], thresholdBins: [] });
  assert.deepEqual(normalized.simulationDrivers, []);
  assert.deepEqual(normalized.rarityContribution, []);
  assert.deepEqual(normalized.historyTrend, []);
  assert.deepEqual(normalized.desirability, {});
  assert.deepEqual(normalized.desirabilityValidation, {});
  assert.deepEqual(normalized.meta, { warnings: [] });
});
