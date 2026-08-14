import assert from "node:assert/strict";
import test from "node:test";

import { MARKET_RANKING_FIELDS, projectMarketRankingTargets } from "./marketRankingsProjection.mjs";

/** A target shaped like the published Rankings document, heavy blocks included. */
function publishedTarget(overrides = {}) {
  return {
    target_type: "set",
    target_id: "set-1",
    set_id: "set-1",
    id: "set-1",
    name: "Perfect Order",
    logo_image_url: "https://images.pokemontcg.io/logo.png",
    symbol_image_url: "https://images.pokemontcg.io/symbol.png",
    checklistSetValue: 1234.5,
    checklistSetValueAsOf: "2026-08-13",
    checklistSetValuePricedCardCount: 180,
    checklistSetValueTotalCardCount: 200,
    previousChecklistSetValue7d: 1200,
    setValueComparisonStatus7d: "available",
    // Everything below is canonical Rankings payload the ladder never reads.
    publicRipContractV8: { overallRip: { relativeScore: 100, rank: 1 } },
    financialRipV3: { score: 88, components: { realisticUpside: {} } },
    openingExperience: { collectorAppeal: {} },
    universalSetDesirability: { score: 71, rank: 3 },
    overallRipV6: { score: 4 },
    ripCore: { score: 5 },
    rip: { score: 6 },
    ...overrides,
  };
}

test("every field the Market ladder reads survives the projection", () => {
  const [projected] = projectMarketRankingTargets([publishedTarget()]);
  for (const field of MARKET_RANKING_FIELDS) {
    if (publishedTarget()[field] !== undefined) {
      assert.deepEqual(projected[field], publishedTarget()[field], `dropped ${field}`);
    }
  }
});

test("the canonical Rankings blocks the ladder never reads are dropped", () => {
  const [projected] = projectMarketRankingTargets([publishedTarget()]);
  for (const heavy of [
    "publicRipContractV8",
    "financialRipV3",
    "openingExperience",
    "universalSetDesirability",
    "overallRipV6",
    "ripCore",
    "rip",
  ]) {
    assert.equal(heavy in projected, false, `${heavy} still crosses the client boundary`);
  }
});

test("both casings are preserved so a snake_case publication still renders", () => {
  const snake = {
    target_type: "set",
    target_id: "set-2",
    name: "Temporal Forces",
    checklist_set_value: 999,
    checklist_set_value_as_of: "2026-08-13",
    checklist_set_value_priced_card_count: 90,
    checklist_set_value_total_card_count: 100,
    previous_checklist_set_value_7d: 900,
    set_value_comparison_status_7d: "available",
    financialRipV3: { score: 1 },
  };
  const [projected] = projectMarketRankingTargets([snake]);
  assert.equal(projected.checklist_set_value, 999);
  assert.equal(projected.checklist_set_value_as_of, "2026-08-13");
  assert.equal(projected.checklist_set_value_priced_card_count, 90);
  assert.equal(projected.checklist_set_value_total_card_count, 100);
  assert.equal(projected.previous_checklist_set_value_7d, 900);
  assert.equal(projected.set_value_comparison_status_7d, "available");
  assert.equal("financialRipV3" in projected, false);
});

test("a missing field is omitted, never written back as undefined", () => {
  const [projected] = projectMarketRankingTargets([
    { target_type: "set", target_id: "set-3", name: "Paradox Rift" },
  ]);
  assert.equal("checklistSetValue" in projected, false);
  assert.equal("symbol_image_url" in projected, false);
});

test("a null set-value status stays null rather than becoming absent", () => {
  // "no comparable snapshot" is a real published state the ladder renders
  // differently from zero; the projection must not erase it.
  const [projected] = projectMarketRankingTargets([
    publishedTarget({ setValueComparisonStatus7d: null }),
  ]);
  assert.equal("setValueComparisonStatus7d" in projected, true);
  assert.equal(projected.setValueComparisonStatus7d, null);
});

test("cohort order is preserved exactly", () => {
  const projected = projectMarketRankingTargets([
    publishedTarget({ target_id: "a", name: "A" }),
    publishedTarget({ target_id: "b", name: "B" }),
    publishedTarget({ target_id: "c", name: "C" }),
  ]);
  assert.deepEqual(projected.map((t) => t.target_id), ["a", "b", "c"]);
});

test("a non-array input yields an empty ladder rather than throwing", () => {
  assert.deepEqual(projectMarketRankingTargets(null), []);
  assert.deepEqual(projectMarketRankingTargets(undefined), []);
});
