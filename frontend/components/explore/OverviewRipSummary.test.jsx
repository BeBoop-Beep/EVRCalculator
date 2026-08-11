// The Overview RIP Summary, tested by RENDERING it.
//
// All three public `/100` values must be the backend cohort-relative scores.
// The fixture carries deliberately different absolute and relative values so a
// mixed-scale regression is unmistakable.

import test from "node:test";
import assert from "node:assert/strict";
import React from "react";
import TestRenderer from "react-test-renderer";

import OverviewRipSummary, { RIP_SUMMARY_DESCRIPTIONS } from "./OverviewRipSummary.jsx";
import { resolveCanonicalRipV7 } from "./canonicalRipV7.mjs";

globalThis.IS_REACT_ACT_ENVIRONMENT = true;

const V7 = {
  contractVersion: "public_rip_contract_v7",
  overallRip: {
    score: 57.75,
    absoluteScore: 57.75,
    relativeScore: 73.4,
    rank: 4,
    rankedSetCount: 21,
    tier: "A",
  },
  financialRip: {
    score: 61.2,
    absoluteScore: 61.2,
    relativeScore: 88.8,
    rank: 2,
    rankedSetCount: 21,
    tier: "S",
    components: {
      trueWinFrequency: { score: 70, rank: 3, rankedSetCount: 21, tier: "A" },
      typicalRetention: { score: 55 },
      lossResilience: { score: 48 },
      realisticUpside: { score: 66 },
      jackpotUpside: { score: 71 },
      baseEconomicEfficiency: { score: 59 },
    },
  },
  collectorAppeal: {
    score: 65.6858,
    absoluteScore: 65.6858,
    relativeScore: 41.2,
    rank: 3,
    rankedSetCount: 21,
    tier: "B",
    weightsDisclosed: false,
    components: {
      rosterDesirability: { score: 62.0, rawValue: 0.62 },
      desirableOutcomeFrequency: { rawValue: 0.031, displayPercent: 3.1, status: "available" },
      dualPathDepth: { rawValue: 0.4385, displayPercent: 43.8 },
    },
    subjectScope: { modeled: ["Pokémon"], notYetModeled: ["Trainer", "Artist"], note: "…" },
  },
};

function render(canonicalSource, props = {}) {
  let renderer;
  TestRenderer.act(() => {
    renderer = TestRenderer.create(
      React.createElement(OverviewRipSummary, {
        canonical: resolveCanonicalRipV7(canonicalSource),
        ...props,
      })
    );
  });
  return renderer;
}

function metricOf(renderer, id) {
  const [node] = renderer.root.findAll((n) => n.props?.["data-rip-summary-metric"] === id);
  assert.ok(node, `metric ${id} must render`);
  const collected = [];
  const walk = (value) => {
    if (value === null || value === undefined || value === false) return;
    if (typeof value === "string" || typeof value === "number") {
      collected.push(String(value));
      return;
    }
    if (Array.isArray(value)) return value.forEach(walk);
    walk(value.children ?? value.props?.children);
  };
  walk(node.props.children);
  return collected.join(" ");
}

function scoreOf(renderer, id) {
  const [node] = renderer.root.findAll((n) => n.props?.["data-rip-summary-metric"] === id);
  const [scoreSpan] = node.findAll((n) => n.props?.["data-rip-summary-score"] !== undefined);
  return String(scoreSpan.props.children);
}

test("exactly three canonical metrics render, and nothing else", () => {
  const renderer = render({ publicRipContractV7: V7 });
  const metrics = renderer.root.findAll((n) => n.props?.["data-rip-summary-metric"] !== undefined);

  assert.equal(metrics.length, 3);
  assert.deepEqual(
    metrics.map((n) => n.props["data-rip-summary-metric"]),
    ["overall", "financial", "collector"]
  );
});

test("each metric carries its label, tier, rank/cohort and one plain sentence", () => {
  const renderer = render({ publicRipContractV7: V7 });

  const overall = metricOf(renderer, "overall");
  assert.ok(overall.includes("RIP Score"));
  assert.ok(overall.includes("A Tier"));
  assert.ok(overall.includes("Rank #4 of 21"));
  assert.ok(overall.includes(RIP_SUMMARY_DESCRIPTIONS.overall));

  const financial = metricOf(renderer, "financial");
  assert.ok(financial.includes("Financial RIP"));
  assert.ok(financial.includes("S Tier"));
  assert.ok(financial.includes("Rank #2 of 21"));
  assert.ok(financial.includes(RIP_SUMMARY_DESCRIPTIONS.financial));

  const collector = metricOf(renderer, "collector");
  assert.ok(collector.includes("Collector Appeal"));
  assert.ok(collector.includes("B Tier"));
  assert.ok(collector.includes("Rank #3 of 21"));
  assert.ok(collector.includes(RIP_SUMMARY_DESCRIPTIONS.collector));
});

test("all three public scores use their own cohort-relative 0–100 values", () => {
  const renderer = render({ publicRipContractV7: V7 });

  assert.equal(scoreOf(renderer, "overall"), "73.4");
  assert.equal(scoreOf(renderer, "financial"), "88.8");
  assert.equal(scoreOf(renderer, "collector"), "41.2");

  const text = ["overall", "financial", "collector"].map((id) => metricOf(renderer, id)).join(" ");
  assert.ok(!text.includes("57.75"), "Overall absolute score must not be shown");
  assert.ok(!text.includes("61.2"), "Financial absolute score must not be shown");
  assert.ok(!text.includes("65.7"), "Collector absolute score must not be shown");
});

test("an Overall block with only an absolute score renders unavailable", () => {
  const renderer = render({
    publicRipContractV7: { ...V7, overallRip: { ...V7.overallRip, relativeScore: null } },
  });
  assert.equal(scoreOf(renderer, "overall"), "—");
  assert.ok(!metricOf(renderer, "overall").includes("57.75"));
});

test("a Financial block with only an absolute score renders unavailable", () => {
  const renderer = render({
    publicRipContractV7: { ...V7, financialRip: { ...V7.financialRip, relativeScore: null } },
  });
  assert.equal(scoreOf(renderer, "financial"), "—");
  assert.ok(!metricOf(renderer, "financial").includes("61.2"));
});

test("a Collector block with only an absolute score renders unavailable", () => {
  const renderer = render({
    publicRipContractV7: { ...V7, collectorAppeal: { ...V7.collectorAppeal, relativeScore: null } },
  });
  assert.equal(scoreOf(renderer, "collector"), "—");
  assert.ok(!metricOf(renderer, "collector").includes("65.7"));
});

test("a missing metric renders an em dash — never zero, never a neighbour", () => {
  const renderer = render({
    publicRipContractV7: { ...V7, collectorAppeal: {} },
  });

  assert.equal(scoreOf(renderer, "collector"), "—");
  const collector = metricOf(renderer, "collector");
  assert.ok(collector.includes("Not available for this set yet."));
  assert.ok(!collector.includes("0.0"), "an unavailable metric is not a zero");
  assert.ok(!collector.includes("88.8"), "and never borrows Financial RIP's score");
  assert.ok(!collector.includes("73.4"), "and never borrows the Overall score");

  assert.equal(scoreOf(renderer, "overall"), "73.4");
  assert.equal(scoreOf(renderer, "financial"), "88.8");
});

test("no canonical contract at all renders three unavailable metrics, not a crash", () => {
  const renderer = render({});
  for (const id of ["overall", "financial", "collector"]) {
    assert.equal(scoreOf(renderer, id), "—");
  }
});

test("a legacy payload cannot fill the summary", () => {
  const renderer = render({
    rip: { score: 88, relativeScore: 91, rank: 1, tier: "S", cohortSize: 21 },
    ripCore: { score: 79, relativeScore: 83, rank: 1, tier: "S" },
  });
  for (const id of ["overall", "financial", "collector"]) {
    assert.equal(scoreOf(renderer, id), "—");
  }
});

test("no weights, formulas, contributions, versions or retired lenses appear", () => {
  const renderer = render({ publicRipContractV7: V7 });
  const text = ["overall", "financial", "collector"].map((id) => metricOf(renderer, id)).join(" ");

  for (const banned of [
    "Profit",
    "Safety",
    "Stability",
    "Opening Experience",
    "Chase Potential",
    "RIP Core",
    "Legacy V2",
    "Current V3",
    "Contributes",
    "contribution",
    "weight",
    "Weight",
    "90%",
    "10%",
    "80%",
    "20%",
    "v7",
    "V7",
    "V3",
  ]) {
    assert.ok(!text.includes(banned), `"${banned}" must not appear in the RIP Summary`);
  }
});

test("View analysis is one restrained action that calls the page's navigator", () => {
  const calls = [];
  const renderer = render({ publicRipContractV7: V7 }, { onViewAnalysis: () => calls.push("nav") });

  const buttons = renderer.root.findAllByType("button");
  assert.equal(buttons.length, 1, "one action for the module, not one per metric");
  assert.equal(buttons[0].props.type, "button");

  TestRenderer.act(() => {
    buttons[0].props.onClick();
  });
  assert.deepEqual(calls, ["nav"], "it must route through the page's set-detail navigator");
});

test("no navigator means no dead control", () => {
  const renderer = render({ publicRipContractV7: V7 });
  assert.equal(renderer.root.findAllByType("button").length, 0);
});

test("the summary is one grouped surface, not three nested cards", () => {
  const renderer = render({ publicRipContractV7: V7 });
  const glass = renderer.root.findAll((n) =>
    typeof n.props?.className === "string" && n.props.className.includes("set-glass-surface")
  );
  assert.equal(glass.length, 1, "exactly one card surface wraps all three metrics");
});
