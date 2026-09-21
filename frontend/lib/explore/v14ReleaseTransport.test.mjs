import assert from "node:assert/strict";
import test from "node:test";
import fs from "node:fs";

import {
  getRankForMode,
  getScoreForMode,
  getTierForMode,
  resolveModeFieldPath,
} from "../../constants/exploreRankingConfig.mjs";
import { selectOverallRipExplanationHierarchy } from "../../components/explore/overallRipExplanationHierarchySelector.mjs";
import {
  selectFinancialRipV3Breakdown,
  selectFinancialRipV3DetailedMetrics,
} from "../../components/explore/financialRipV3Selector.mjs";

const block = (score, rank, tier) => ({ leaderNormalizedScore: score, rank, cohortSize: 50, tier });

test("the current ranking mode reads the V12 block on a V12 target", () => {
  const t = { overallRipV12: block(71, 3, "A"), financialRipV4: block(60, 9, "B") };
  assert.equal(getScoreForMode(t, "overall"), 71);
  assert.equal(getRankForMode(t, "overall"), 3);
  assert.equal(getTierForMode(t, "financial"), "B");
});

test("the same mode reads the V14/V5 block when the target carries it, and never mixes releases", () => {
  const t = { overallRipV12: block(71, 3, "A"), overallRipV14: block(64, 5, "B"), financialRipV5: block(58, 11, "C") };
  assert.equal(getScoreForMode(t, "overall"), 64);
  assert.equal(getRankForMode(t, "overall"), 5);
  assert.equal(getScoreForMode(t, "financial"), 58); // financialRipV4 absent: the V5 block, not undefined-as-V4
  assert.equal(resolveModeFieldPath({ overallRipV14: {} }, "overallRipV12.rank"), "overallRipV14.rank");
  assert.equal(resolveModeFieldPath({}, "overallRipV12.rank"), "overallRipV12.rank");
});

const composition = { version: "overall_rip_v14_x", weights: { financial_rip: 0.86, chase_accessibility: 0.04, collector_appeal: 0.1 } };
const v12Contract = {
  overallRipV14: { score: 64, status: "ready", components: {} },
  overallRipV14Composition: composition,
};
const v11Contract = {
  overallRipV12: { score: 70, status: "ready", components: {} },
  overallRipV12Composition: { version: "overall_rip_v12_x", weights: { financial_rip: 0.9, collector_appeal: 0.1 } },
};

test("explanation selection is contract-driven: contract V12, then V11, then fallback", () => {
  const v14 = selectOverallRipExplanationHierarchy({ publicRipContractV12: v12Contract, publicRipContractV11: v11Contract });
  assert.equal(v14.contractVersion, "overall_rip_v14_x");
  const v12 = selectOverallRipExplanationHierarchy({ publicRipContractV11: v11Contract });
  assert.equal(v12.contractVersion, "overall_rip_v12_x");
  // Ambient top-level keys without a contract wrapper are NOT an opt-in (unchanged safety rule).
  const ambient = selectOverallRipExplanationHierarchy({ overallRipV14: v12Contract.overallRipV14, overallRipV14Composition: composition });
  assert.notEqual(ambient.contractVersion, "overall_rip_v14_x");
});

const shortfall = { score: 55, relativeScore: 55, publicScore: 55, raw: { expectedShortfallToCost: 0.2, expectedDeepShortfall: 0.05, cappedRecovery: 0.8 } };
const loss = { score: 50, relativeScore: 50, publicScore: 50, raw: { averageRetentionGivenLoss: 0.4 } };

test("V5 payloads show Shortfall Resilience, V4 payloads show Loss Resilience, never both", () => {
  const titles = (components) => selectFinancialRipV3Breakdown({ status: "ready", components }).rows?.map((r) => r.title)
    ?? selectFinancialRipV3Breakdown({ status: "ready", components }).map((r) => r.title);
  const v5 = titles({ shortfall_resilience: shortfall });
  const v4 = titles({ loss_resilience: loss });
  assert.ok(v5.includes("Shortfall Resilience") && !v5.includes("Loss Resilience"));
  assert.ok(v4.includes("Loss Resilience") && !v4.includes("Shortfall Resilience"));
  const m5 = selectFinancialRipV3DetailedMetrics({ components: { shortfall_resilience: shortfall } }).map((m) => m.key);
  assert.ok(m5.includes("expectedShortfall") && !m5.includes("averageLosingReturn"));
  const m4 = selectFinancialRipV3DetailedMetrics({ components: { loss_resilience: loss } }).map((m) => m.key);
  assert.ok(m4.includes("averageLosingReturn") && !m4.includes("expectedShortfall"));
});

test("the client boundary keeps the V14/V5 blocks and the frontend contains no scoring of them", () => {
  const src = fs.readFileSync(new URL("./rankingsClientProjection.mjs", import.meta.url), "utf8");
  assert.match(src, /overallRipV14:/);
  assert.match(src, /financialRipV5:/);
  for (const file of ["../../constants/exploreRankingConfig.mjs", "../../components/explore/overallRipExplanationHierarchySelector.mjs"]) {
    const text = fs.readFileSync(new URL(file, import.meta.url), "utf8");
    assert.doesNotMatch(text, /0\.86|0\.70|0\.60|shortfallCoefficient/, `${file} must not restate V5/V14 scoring constants`);
  }
});
