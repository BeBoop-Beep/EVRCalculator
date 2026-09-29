import "../../test-support/renderComponentRegister.mjs";

import assert from "node:assert/strict";
import test from "node:test";
import React from "react";
import TestRenderer, { act } from "react-test-renderer";

import RankingsOverviewHighlights from "./RankingsOverviewHighlights.jsx";
import {
  RIP_SCORE_SCALE_BENCHMARK_10,
  RIP_SCORE_SCALE_PUBLIC_100,
  RipScoreBadge,
  formatRipScoreBadgeValue,
} from "./RipScoreBadge.jsx";

globalThis.IS_REACT_ACT_ENVIRONMENT = true;

function visibleText(renderer) {
  return renderer.root.findAll((node) => typeof node.children?.[0] === "string")
    .flatMap((node) => node.children)
    .filter((value) => typeof value === "string")
    .join(" ");
}

function renderBadge(score, scoreScale) {
  let renderer;
  act(() => {
    renderer = TestRenderer.create(<RipScoreBadge score={score} tier="S" scoreScale={scoreScale} />);
  });
  return visibleText(renderer);
}

test("explicit score scales preserve legacy public100 and format Benchmark V1 directly", () => {
  assert.equal(formatRipScoreBadgeValue(79.2, RIP_SCORE_SCALE_PUBLIC_100), "7.9");
  assert.equal(formatRipScoreBadgeValue(7.38, RIP_SCORE_SCALE_BENCHMARK_10), "7.4");
  assert.equal(formatRipScoreBadgeValue(5, RIP_SCORE_SCALE_BENCHMARK_10), "5.0");
  assert.equal(formatRipScoreBadgeValue(10, RIP_SCORE_SCALE_BENCHMARK_10), "10.0");
  assert.equal(formatRipScoreBadgeValue(0, RIP_SCORE_SCALE_BENCHMARK_10), "0.0");
  assert.match(renderBadge(79.2, RIP_SCORE_SCALE_PUBLIC_100), /7\.9 \/ 10/);
  assert.match(renderBadge(7.38, RIP_SCORE_SCALE_BENCHMARK_10), /7\.4 \/ 10/);
});

test("Top Set and Top Era render Benchmark V1 scores without legacy double scaling", () => {
  const score = { score: 7.38, tier: "S", rank: 1, cohortSize: 22, benchmarkPosition: "above", deltaVsBenchmark: 2.38 };
  let renderer;
  act(() => {
    renderer = TestRenderer.create(<RankingsOverviewHighlights overview={{
      status: "available",
      topSet: { entityId: "set-1", name: "Fixture Set", canonicalKey: "fixture-set", score },
      topEra: { entityId: "era-1", name: "Fixture Era", score: { ...score, cohortSize: 2 } },
      lowestAveragePackCost: { setName: "Fixture Set", averagePackCost: 7.12 },
      modeledCoverage: { setCount: 22, productCount: 138, productFamilyCount: 8 },
      overallFinancialRip: { absoluteScore: 30.36 },
    }} />);
  });
  const text = visibleText(renderer);
  assert.match(text, /#1 Set to Open[\s\S]*7\.4 \/ 10/);
  assert.match(text, /#1 Era to Open[\s\S]*7\.4 \/ 10/);
  assert.ok(!text.includes("0.7 / 10"));
});
