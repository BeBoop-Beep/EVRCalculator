import test from "node:test";
import assert from "node:assert/strict";
import React from "react";
import TestRenderer from "react-test-renderer";
import { familyEvidenceScores, familyTier, participatingFamilyCount, participatingFamilyScores, selectPreferredSetRipContract, setRipTier, whySetRanks } from "./SetRipFamilyBreakdown.jsx";
import { FamilyScoreRow, FamilySnapshot, familyLabel } from "./SetRipFamilyBreakdown.jsx";

globalThis.IS_REACT_ACT_ENVIRONMENT = true;

const sets = [
  { name: "Alpha", setRipV1: { score: 92, rank: 1, cohortSize: 20, familyScores: [{ family: "booster_box", score: 95, rank: 1, cohortSize: 20, skuCount: 2 }] } },
  { name: "Beta", setRipV1: { score: 84, rank: 4, cohortSize: 20, familyScores: [{ family: "booster_bundle", score: 82, rank: 4, cohortSize: 20, skuCount: 1 }] } },
  { name: "Gamma", setRipV1: { score: 76, rank: 9, cohortSize: 20, familyScores: [{ family: "elite_trainer_box", score: 75, rank: 9, cohortSize: 18, skuCount: 1 }] } },
];

test("three representative sets retain identical canonical values for every consumer", () => {
  assert.deepEqual(sets.map(({ setRipV1 }) => ({ score: setRipV1.score, rank: setRipV1.rank, tier: setRipTier(setRipV1) })), [
    { score: 92, rank: 1, tier: "S" },
    { score: 84, rank: 4, tier: "A" },
    { score: 76, rank: 9, tier: "B" },
  ]);
  for (const { setRipV1 } of sets) {
    const family = participatingFamilyScores(setRipV1)[0];
    assert.equal(familyTier(family), setRipV1 === sets[2].setRipV1 ? "B" : setRipTier(setRipV1));
    assert.ok(whySetRanks(setRipV1));
  }
});

test("invalid and empty family entries never produce placeholder modules", () => {
  assert.deepEqual(participatingFamilyScores({ familyScores: [{ family: "x" }, null] }), []);
  assert.deepEqual(participatingFamilyScores({ familyScores: {} }), []);
});

test("legacy family evidence is counted without fabricating ranking context", () => {
  const legacy = {
    participatingFamilyCount: 6,
    familyScores: [{ family: "booster_box", skuCount: 1, meanStanding: 1 }],
  };
  assert.equal(participatingFamilyCount(legacy), 6);
  assert.equal(familyEvidenceScores(legacy).length, 1);
  assert.deepEqual(participatingFamilyScores(legacy), []);
});

test("family count falls back to evidence only when the canonical count is absent", () => {
  assert.equal(participatingFamilyCount({ familyScores: [{ family: "booster_box" }] }), 1);
  assert.equal(participatingFamilyCount({ participatingFamilyCount: 0, familyScores: [{ family: "booster_box" }] }), 0);
});

test("the set page prefers an enriched selected target over a legacy explore payload", () => {
  const legacy = { score: 96, rank: 1, participatingFamilyCount: 6, familyScores: [{ family: "booster_box" }] };
  const enriched = { score: 96, rank: 1, cohortSize: 22, participatingFamilyCount: 1,
    familyScores: [{ family: "booster_box", skuCount: 1, score: 100, rank: 1, cohortSize: 15 }] };
  assert.equal(selectPreferredSetRipContract(legacy, enriched), enriched);
  assert.deepEqual(participatingFamilyScores(selectPreferredSetRipContract(legacy, enriched)), enriched.familyScores);
});

const enrichedFamilies = {
  familyScores: [
    { family: "booster_box", skuCount: 1, score: 100, rank: 1, cohortSize: 15 },
    { family: "booster_bundle", skuCount: 1, score: 90.9, rank: 3, cohortSize: 22 },
    { family: "elite_trainer_box", skuCount: 1, score: 92.3, rank: 2, cohortSize: 22 },
    { family: "loose_booster_pack", skuCount: 1, score: 100, rank: 1, cohortSize: 22 },
    { family: "pokemon_center_elite_trainer_box", skuCount: 1, score: 100, rank: 1, cohortSize: 22 },
    { family: "sleeved_booster_pack", skuCount: 1, score: 92.9, rank: 2, cohortSize: 15 },
  ],
};

function render(element) {
  let renderer;
  TestRenderer.act(() => { renderer = TestRenderer.create(element); });
  return renderer;
}

function renderedText(renderer) {
  const values = [];
  const visit = (node) => {
    if (typeof node === "string" || typeof node === "number") values.push(String(node));
    else if (Array.isArray(node)) node.forEach(visit);
    else if (node?.children) visit(node.children);
  };
  visit(renderer.toJSON());
  return values.join("");
}

test("Rankings renders every enriched family as a text-first module", () => {
  const renderer = render(React.createElement(FamilySnapshot, { setRip: enrichedFamilies, layout: "modules" }));
  assert.equal(renderer.root.findAll((node) => node.props["data-family-module"] !== undefined).length, 6);
  assert.equal(renderer.root.findAll((node) => node.props["data-family-media-slot"] !== undefined).length, 0);
  const text = renderedText(renderer);
  for (const expected of ["Booster Box", "Booster Bundle", "ETB", "Booster Pack", "Pokémon Center Elite Trainer Box", "Sleeved Pack", "100.0", "#3", "A"]) {
    assert.ok(text.includes(expected), expected);
  }
});

test("Set-page and mobile family rows do not depend on product imagery", () => {
  for (const compact of [false, true]) {
    const renderer = render(React.createElement(FamilyScoreRow, { entry: enrichedFamilies.familyScores[4], compact, showTakeaway: true }));
    assert.equal(renderer.root.findAllByType("img").length, 0);
    assert.equal(renderer.root.findAll((node) => node.props["data-family-media-slot"] !== undefined).length, 0);
    assert.ok(JSON.stringify(renderer.toJSON()).includes("Pokémon Center Elite Trainer Box"));
  }
});

test("canonical family labels remain presentation-only", () => {
  assert.equal(familyLabel("loose_booster_pack"), "Booster Pack");
  assert.equal(familyLabel("pokemon_center_elite_trainer_box"), "Pokémon Center Elite Trainer Box");
  assert.equal(familyLabel("special_collection"), "SPC");
});
