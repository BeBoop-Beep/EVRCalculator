import test from "node:test";
import assert from "node:assert/strict";
import React from "react";
import TestRenderer from "react-test-renderer";
import { displayFamilyScores, familyEvidenceScores, familyTier, participatingFamilyCount, participatingFamilyScores, selectPreferredSetRipContract, setRipTier, whySetRanks } from "./SetRipFamilyBreakdown.jsx";
import { FamilyScoreRow, FamilySnapshot, RankingsFamilyCells, RANKINGS_FAMILY_COLUMNS, familyLabel } from "./SetRipFamilyBreakdown.jsx";

globalThis.IS_REACT_ACT_ENVIRONMENT = true;

const sets = [
  { name: "Alpha", setRipV1: { score: 92, tier: "S", rank: 1, cohortSize: 20, familyScores: [{ family: "booster_box", score: 95, tier: "S", rank: 1, cohortSize: 20, skuCount: 2 }] } },
  { name: "Beta", setRipV1: { score: 84, tier: "A", rank: 4, cohortSize: 20, familyScores: [{ family: "booster_bundle", score: 82, tier: "A", rank: 4, cohortSize: 20, skuCount: 1 }] } },
  { name: "Gamma", setRipV1: { score: 76, tier: "B", rank: 9, cohortSize: 20, familyScores: [{ family: "elite_trainer_box", score: 75, tier: "B", rank: 9, cohortSize: 18, skuCount: 1 }] } },
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
    { family: "booster_box", skuCount: 1, score: 100, tier: "S", rank: 1, cohortSize: 15 },
    { family: "booster_bundle", skuCount: 1, score: 90.9, tier: "S", rank: 3, cohortSize: 22 },
    { family: "elite_trainer_box", skuCount: 1, score: 92.3, tier: "S", rank: 2, cohortSize: 22 },
    { family: "loose_booster_pack", skuCount: 1, score: 100, tier: "S", rank: 1, cohortSize: 22 },
    { family: "pokemon_center_elite_trainer_box", skuCount: 1, score: 100, tier: "S", rank: 1, cohortSize: 22 },
    { family: "sleeved_booster_pack", skuCount: 1, score: 92.9, tier: "S", rank: 2, cohortSize: 15 },
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
  for (const expected of ["Booster Box", "Booster Bundle", "ETB", "Booster Pack", "Pokémon Center ETB", "Sleeved Pack", "10.0", "#3", "S"]) {
    assert.ok(text.includes(expected), expected);
  }
});

test("wide Rankings snapshot structurally supports seven families in seven columns", () => {
  const sevenFamilies = {
    familyScores: [...enrichedFamilies.familyScores, { family: "three_pack_blister", skuCount: 1, score: 88.4, rank: 4, cohortSize: 22 }],
  };
  const renderer = render(React.createElement(FamilySnapshot, { setRip: sevenFamilies, layout: "modules" }));
  const snapshot = renderer.root.find((node) => node.props["data-family-snapshot"] !== undefined);
  assert.equal(snapshot.props["data-wide-family-columns"], 7);
  assert.equal(snapshot.props.style["--family-columns"], 7);
  assert.equal(renderer.root.findAll((node) => node.props["data-family-module"] !== undefined).length, 7);
  assert.equal(renderer.root.findAllByType("img").length, 0);
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

test("desktop Rankings family columns have one stable canonical order", () => {
  assert.deepEqual(RANKINGS_FAMILY_COLUMNS.map((column) => column.families), [
    ["loose_booster_pack"], ["sleeved_booster_pack"], ["booster_bundle"],
    ["elite_trainer_box"], ["pokemon_center_elite_trainer_box"],
    ["half_booster_box"], ["booster_box"], ["enhanced_booster_box"],
  ]);
});

test("fixed cells preserve missing positions and canonical score, rank, and tier", () => {
  const renderer = render(React.createElement("table", null, React.createElement("tbody", null, React.createElement("tr", null,
    React.createElement(RankingsFamilyCells, { setRip: { familyScores: [
      { family: "booster_bundle", score: 92.3, tier: "S", rank: 3, cohortSize: 20 },
      { family: "booster_box", score: 71.1, tier: "B", rank: 8, cohortSize: 20 },
    ] } })
  ))));
  const cells = renderer.root.findAll((node) => node.props["data-rankings-family-column"] !== undefined);
  assert.equal(cells.length, 8);
  assert.deepEqual(cells.map((cell) => cell.props["data-rankings-family-column"]), RANKINGS_FAMILY_COLUMNS.map((column) => column.key));
  assert.ok(renderedText({ toJSON: () => cells[0].toJSON?.() }).includes("—") || renderedText(renderer).includes("—"));
  const text = renderedText(renderer);
  assert.ok(text.includes("9.2"));
  assert.ok(text.includes("#3"));
  assert.ok(text.includes(familyTier({ tier: "S" })));
});

test("display-only Enhanced Box evidence renders without entering Format Strength eligibility", () => {
  const setRip = {
    score: 75,
    familyScores: [{ family: "booster_box", score: 80, rank: 2, cohortSize: 10 }],
    displayFamilyScores: [
      { family: "booster_box", score: 80, tier: "A", rank: 2, cohortSize: 10 },
      { family: "enhanced_booster_box", score: 100, tier: "S", rank: 1, cohortSize: 2 },
    ],
  };
  assert.equal(participatingFamilyScores(setRip).length, 1);
  assert.equal(displayFamilyScores(setRip).length, 2);
  const renderer = render(React.createElement("table", null, React.createElement("tbody", null, React.createElement("tr", null,
    React.createElement(RankingsFamilyCells, { setRip })
  ))));
  const enhanced = renderer.root.find((node) => node.props["data-rankings-family-column"] === "enhanced-box");
  const text = renderedText({ toJSON: () => enhanced.toJSON?.() }) || renderedText(renderer);
  assert.ok(text.includes("10.0"));
  assert.ok(text.includes("#1"));

  const journey = {
    familyScores: [],
    displayFamilyScores: [
      { family: "enhanced_booster_box", score: 0, tier: "F", rank: 2, cohortSize: 2 },
    ],
  };
  assert.equal(participatingFamilyScores(journey).length, 0);
  assert.equal(displayFamilyScores(journey).length, 1);
  const zeroRenderer = render(React.createElement("table", null, React.createElement("tbody", null, React.createElement("tr", null,
    React.createElement(RankingsFamilyCells, { setRip: journey })
  ))));
  const zeroText = renderedText(zeroRenderer);
  assert.ok(zeroText.includes("0.0"));
  assert.ok(zeroText.includes("#2"));
  assert.ok(zeroText.includes("F"));
});
