// The Overview RIP Summary, tested by RENDERING it.
//
// The module imports only React and the three canonical selectors — no "@/"
// aliases, no CSS module, no next/link — so it mounts directly and its real
// tree can be asserted on. That matters most for the two requirements that a
// source scan cannot honestly answer: that a missing metric prints an em dash
// rather than a zero or a neighbour's value, and that the Overall headline is
// the RELATIVE score while Financial RIP and Collector Appeal keep their own
// fixed-anchor scores.

import test from "node:test";
import assert from "node:assert/strict";
import React from "react";
import TestRenderer from "react-test-renderer";

import OverviewRipSummary, { RIP_SUMMARY_DESCRIPTIONS } from "./OverviewRipSummary.jsx";
import { resolveCanonicalRipV7 } from "./canonicalRipV7.mjs";

globalThis.IS_REACT_ACT_ENVIRONMENT = true;

// Shaped after backend/desirability/public_rip_contract_v7.py. The three
// blocks carry DELIBERATELY DIFFERENT absolute and relative numbers, so a
// surface reading the wrong field or the wrong block is unmistakable.
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

/* ------------------------------------------------- exactly three metrics --- */

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

/* --------------------------------------------------------- score scales --- */

test("Overall uses the RELATIVE score; Financial and Collector keep their own", () => {
  const renderer = render({ publicRipContractV7: V7 });

  // Overall RIP's public number is the cohort-relative score (73.4), never the
  // absolute 90/10 blend (57.75).
  assert.equal(scoreOf(renderer, "overall"), "73.4");

  // Financial RIP and Collector Appeal publish their own fixed-anchor V3
  // scores (61.2 and 65.7). They are NOT restated on the Overall relative
  // scale (88.8 and 41.2) to make all three accessors match.
  assert.equal(scoreOf(renderer, "financial"), "61.2");
  assert.equal(scoreOf(renderer, "collector"), "65.7");
});

test("an Overall block with only an absolute score renders unavailable", () => {
  // A differently-scaled number must never appear under the public label.
  const renderer = render({
    publicRipContractV7: { ...V7, overallRip: { ...V7.overallRip, relativeScore: null } },
  });
  assert.equal(scoreOf(renderer, "overall"), "—");
  assert.ok(!metricOf(renderer, "overall").includes("57.75"));
});

/* ------------------------------------------------------- unavailability --- */

test("a missing metric renders an em dash — never zero, never a neighbour", () => {
  const renderer = render({
    publicRipContractV7: { ...V7, collectorAppeal: {} },
  });

  assert.equal(scoreOf(renderer, "collector"), "—");
  const collector = metricOf(renderer, "collector");
  assert.ok(collector.includes("Not available for this set yet."));
  assert.ok(!collector.includes("0.0"), "an unavailable metric is not a zero");
  assert.ok(!collector.includes("61.2"), "and never borrows Financial RIP's score");
  assert.ok(!collector.includes("73.4"), "and never borrows the Overall score");

  // The other two are unaffected.
  assert.equal(scoreOf(renderer, "overall"), "73.4");
  assert.equal(scoreOf(renderer, "financial"), "61.2");
});

test("no canonical contract at all renders three unavailable metrics, not a crash", () => {
  const renderer = render({});
  for (const id of ["overall", "financial", "collector"]) {
    assert.equal(scoreOf(renderer, id), "—");
  }
});

test("a legacy payload cannot fill the summary", () => {
  // `rip` is Overall RIP v4 and `ripCore` is Financial RIP V2. Neither is a
  // canonical source, so a set carrying only these renders unavailable rather
  // than showing a superseded score under a current label.
  const renderer = render({
    rip: { score: 88, relativeScore: 91, rank: 1, tier: "S", cohortSize: 21 },
    ripCore: { score: 79, relativeScore: 83, rank: 1, tier: "S" },
  });
  for (const id of ["overall", "financial", "collector"]) {
    assert.equal(scoreOf(renderer, id), "—");
  }
});

/* ---------------------------------------------------------------- copy --- */

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

/* -------------------------------------------------------- view analysis --- */

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
