import test from "node:test";
import assert from "node:assert/strict";

import { buildSetHeaderSummary } from "./setHeaderSummarySelector.mjs";

function baseSetValueContract() {
  return {
    current: { value: null, asOf: null, source: null },
    scopes: { standard: { currentValue: null, delta30dAmount: null, delta30dPercent: null, history: [], asOf: null } },
  };
}

test("header sourced from shellPayload when explorePayload is not fresh (Overview/Cards tabs)", () => {
  const summary = buildSetHeaderSummary({
    explorePayload: { summary: { pack_score: 999 }, interpretation: { packScore: "should not be used" } },
    shellPayload: {
      set: { id: "set-1", name: "Alpha Set", slug: "alpha-set" },
      summary: { pack_score: 71.5, pack_tier: "A", pack_rank: 3, pack_cost: 4.99, mean_value: 5.5, average_hit_value: 12.3, prob_profit: 0.4, prob_big_hit: 0.05 },
      interpretation: { meta: { packScore: { label: "Strong Value Profile", summary: "This set beats the field." } } },
    },
    marketDashboardPayload: null,
    marketDashboardState: null,
    setValueContract: baseSetValueContract(),
    selectedTarget: null,
    resolvedSetResourceId: "set-1",
    explorePayloadIsFresh: false,
    previousSameSetSummary: null,
  });

  assert.equal(summary.set.id, "set-1");
  assert.equal(summary.set.name, "Alpha Set");
  assert.equal(summary.score, 71.5);
  assert.equal(summary.tier, "A");
  assert.equal(summary.rank, 3);
  assert.equal(summary.recommendationBadge, "Strong Value Profile");
  assert.equal(summary.recommendationSummary, "This set beats the field.");
  assert.equal(summary.packCost, 4.99);
  assert.equal(summary.expectedValue, 5.5);
  assert.equal(summary.averageHitValue, 12.3);
  assert.equal(summary.chanceToBeatPackCost, 0.4);
  assert.equal(summary.chanceAtBigPull, 0.05);
});

test("fresh explorePayload for the active set wins over shellPayload", () => {
  const summary = buildSetHeaderSummary({
    explorePayload: {
      set: { id: "set-1", name: "Alpha Set Fresh" },
      summary: { pack_score: 82, pack_tier: "S", pack_rank: 1 },
      interpretation: { meta: { packScore: { label: "Elite Value Profile", summary: "Top of the field." } } },
    },
    shellPayload: {
      summary: { pack_score: 71.5, pack_tier: "A", pack_rank: 3 },
      interpretation: { meta: { packScore: { label: "Strong Value Profile", summary: "Stale text." } } },
    },
    setValueContract: baseSetValueContract(),
    resolvedSetResourceId: "set-1",
    explorePayloadIsFresh: true,
  });

  assert.equal(summary.set.name, "Alpha Set Fresh");
  assert.equal(summary.score, 82);
  assert.equal(summary.tier, "S");
  assert.equal(summary.recommendationBadge, "Elite Value Profile");
  assert.equal(summary.recommendationSummary, "Top of the field.");
});

test("explorePayload is ignored in favor of shellPayload when explorePayloadIsFresh is false (caller determined it does not match the active set)", () => {
  const summary = buildSetHeaderSummary({
    explorePayload: {
      set: { id: "other-set" },
      summary: { pack_score: 10 },
      interpretation: { meta: { packScore: { label: "Wrong Set Label" } } },
    },
    shellPayload: {
      set: { id: "set-1", name: "Alpha Set" },
      summary: { pack_score: 71.5, pack_tier: "A" },
      interpretation: { meta: { packScore: { label: "Strong Value Profile" } } },
    },
    setValueContract: baseSetValueContract(),
    resolvedSetResourceId: "set-1",
    explorePayloadIsFresh: false,
  });

  assert.equal(summary.score, 71.5);
  assert.equal(summary.recommendationBadge, "Strong Value Profile");
});

test("already-loaded same-set client state fills gaps when both explorePayload and shellPayload go missing", () => {
  const previous = buildSetHeaderSummary({
    explorePayload: {
      set: { id: "set-1", name: "Alpha Set" },
      summary: { pack_score: 82, pack_tier: "S", average_hit_value: 40 },
      interpretation: { meta: { packScore: { label: "Elite Value Profile", summary: "Top of the field." } } },
    },
    setValueContract: baseSetValueContract(),
    resolvedSetResourceId: "set-1",
    explorePayloadIsFresh: true,
  });

  // Tab switch: explorePayload resets to null, shellPayload transiently absent too.
  const next = buildSetHeaderSummary({
    explorePayload: null,
    shellPayload: null,
    setValueContract: baseSetValueContract(),
    resolvedSetResourceId: "set-1",
    explorePayloadIsFresh: false,
    previousSameSetSummary: previous,
  });

  assert.equal(next.set.name, "Alpha Set");
  assert.equal(next.score, 82);
  assert.equal(next.tier, "S");
  assert.equal(next.averageHitValue, 40);
  assert.equal(next.recommendationBadge, "Elite Value Profile");
  assert.equal(next.recommendationSummary, "Top of the field.");
});

test("cached client state from a different set is not reused", () => {
  const previous = buildSetHeaderSummary({
    explorePayload: {
      set: { id: "set-1" },
      summary: { pack_score: 82 },
    },
    setValueContract: baseSetValueContract(),
    resolvedSetResourceId: "set-1",
    explorePayloadIsFresh: true,
  });

  const next = buildSetHeaderSummary({
    explorePayload: null,
    shellPayload: null,
    setValueContract: baseSetValueContract(),
    resolvedSetResourceId: "set-2",
    explorePayloadIsFresh: false,
    previousSameSetSummary: previous,
  });

  assert.equal(next.score, null);
  assert.equal(next.setId, "set-2");
});

test("average loss derives from mean value minus pack cost when both are present", () => {
  const summary = buildSetHeaderSummary({
    shellPayload: { summary: { mean_value: 3.5, pack_cost: 4.99 } },
    setValueContract: baseSetValueContract(),
    resolvedSetResourceId: "set-1",
  });

  assert.equal(summary.averageLoss, 3.5 - 4.99);
});

test("set value prefers the blended setValueContract over raw market dashboard payload", () => {
  const summary = buildSetHeaderSummary({
    shellPayload: { summary: {} },
    marketDashboardPayload: {
      setValueHistoriesByScope: { standard: [{ date: "2026-05-01", setValue: 10 }] },
    },
    setValueContract: {
      current: { value: 123.45, asOf: "2026-06-30" },
      scopes: {
        standard: {
          currentValue: 123.45,
          delta30dAmount: 5.5,
          delta30dPercent: 4.7,
          history: [
            { date: "2026-06-01", setValue: 117.95 },
            { date: "2026-06-30", setValue: 123.45 },
          ],
          asOf: "2026-06-30",
        },
      },
    },
    resolvedSetResourceId: "set-1",
  });

  assert.equal(summary.setValue.current, 123.45);
  assert.equal(summary.setValue.delta30dAmount, 5.5);
  assert.equal(summary.setValue.delta30dPercent, 4.7);
  assert.equal(summary.setValue.sparklinePoints.length, 2);
});

test("set value falls back to raw market dashboard history when the contract has none", () => {
  const summary = buildSetHeaderSummary({
    shellPayload: { summary: {} },
    marketDashboardPayload: {
      setValueHistoriesByScope: { standard: [{ date: "2026-05-01", setValue: 10 }, { date: "2026-05-31", setValue: 12 }] },
    },
    setValueContract: baseSetValueContract(),
    resolvedSetResourceId: "set-1",
  });

  assert.equal(summary.setValue.sparklinePoints.length, 2);
  assert.equal(summary.setValue.current, 12);
});

test("safe fallback placeholders when no source has data for a brand new set", () => {
  const summary = buildSetHeaderSummary({
    explorePayload: null,
    shellPayload: null,
    setValueContract: baseSetValueContract(),
    resolvedSetResourceId: "set-9",
    explorePayloadIsFresh: false,
  });

  assert.equal(summary.setId, "set-9");
  assert.equal(summary.score, null);
  assert.equal(summary.recommendationBadge, null);
  assert.equal(summary.recommendationSummary, null);
  assert.equal(summary.averageHitValue, null);
  assert.equal(summary.setValue.current, null);
  assert.deepEqual(summary.setValue.sparklinePoints, []);
  assert.ok(summary.diagnostics.missingFields.includes("score"));
});
