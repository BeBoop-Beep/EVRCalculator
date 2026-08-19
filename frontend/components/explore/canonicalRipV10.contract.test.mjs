/**
 * Frontend version-parsing support for Overall RIP V10 / Financial RIP V4.
 *
 * SCOPE: parsing only. No UI is redesigned and no public metric name moves -
 * the whole point of the contract layer is that the rendered shape is identical
 * across model versions, so a V10 payload renders through exactly the same
 * selectors as a V9 one.
 *
 * These tests exist because the reader previously knew only about
 * `publicRipContractV9` / `overallRipV9`, and an unknown key resolves to
 * "unavailable" - which would blank every RIP surface the day the backend
 * starts serving V10 rather than degrading to a wrong number. Being able to
 * PARSE V10 is not the same as V10 being canonical; the backend still decides.
 */

import assert from "node:assert/strict";
import test from "node:test";

import { readCanonicalBlock, resolveCanonicalRipV7 } from "./canonicalRipV7.mjs";

const OVERALL_V10_VERSION = "overall_rip_v10_90_financial_v4_10_collector_appeal_v5";
const FINANCIAL_V4_VERSION =
  "financial_rip_v4_outcome_profile_p95_only_25_20_15_25_10_5";

function overallBlock() {
  return {
    absoluteScore: 70.25,
    relativeScore: 81.4,
    rank: 3,
    cohortSize: 21,
    tier: "strong",
    version: OVERALL_V10_VERSION,
  };
}

function financialBlock() {
  return {
    absoluteScore: 71.0,
    relativeScore: 82.9,
    rank: 2,
    cohortSize: 21,
    tier: "strong",
    version: FINANCIAL_V4_VERSION,
  };
}

function v10Contract() {
  return {
    publicRipContractV10: {
      contractVersion: "public_rip_contract_v10",
      canonicalOverallRipVersion: OVERALL_V10_VERSION,
      canonicalFinancialRipVersion: FINANCIAL_V4_VERSION,
      overallRip: overallBlock(),
      financialRip: financialBlock(),
      collectorAppeal: { absoluteScore: 63.5, relativeScore: 55.0 },
      audit: { note: "v10" },
    },
  };
}

test("the V10 public contract resolves and reports the contract it read", () => {
  const bundle = resolveCanonicalRipV7(v10Contract());
  assert.equal(bundle.shape, "publicRipContractV10");
  assert.equal(bundle.overall.version, OVERALL_V10_VERSION);
  assert.equal(bundle.financialRip.version, FINANCIAL_V4_VERSION);
});

test("a V10 contract wins over an older contract on the same source", () => {
  const source = {
    ...v10Contract(),
    publicRipContractV9: {
      overallRip: { ...overallBlock(), version: "overall_rip_v9_x" },
      financialRip: financialBlock(),
      collectorAppeal: {},
    },
  };
  assert.equal(resolveCanonicalRipV7(source).shape, "publicRipContractV10");
});

test("the V9 contract still resolves when no V10 block is present", () => {
  const source = {
    publicRipContractV9: {
      overallRip: { ...overallBlock(), version: "overall_rip_v9_x" },
      financialRip: financialBlock(),
      collectorAppeal: {},
    },
  };
  assert.equal(resolveCanonicalRipV7(source).shape, "publicRipContractV9");
});

test("top-level V10 objects resolve when no contract block is served", () => {
  const bundle = resolveCanonicalRipV7({
    overallRipV10: overallBlock(),
    financialRipV4: financialBlock(),
  });
  assert.equal(bundle.shape, "topLevelV10");
  assert.equal(bundle.financialRip.version, FINANCIAL_V4_VERSION);
});

test("a V10 blend served beside a V3 financial object still resolves the financial half", () => {
  const bundle = resolveCanonicalRipV7({
    overallRipV10: overallBlock(),
    financialRipV3: { ...financialBlock(), version: "financial_rip_v3_x" },
  });
  assert.equal(bundle.shape, "topLevelV10");
  assert.equal(bundle.financialRip.version, "financial_rip_v3_x");
});

test("V10 renders through the SAME public reader as every other version", () => {
  const bundle = resolveCanonicalRipV7(v10Contract());
  const overall = readCanonicalBlock(bundle.overall);
  // `publicScore` is the cohort-relative number, exactly as for V8/V9. No new
  // public field, no renamed one, and the absolute is still not promoted.
  assert.equal(overall.publicScore, 81.4);
  assert.equal(overall.modelScore, 70.25);
  assert.equal(overall.rank, 3);
  assert.ok(!("score" in overall));
});

test("an unrecognised model version still resolves to unavailable, never to zero", () => {
  const bundle = resolveCanonicalRipV7({ somethingElse: { score: 12 } });
  assert.equal(bundle.shape, null);
  assert.equal(readCanonicalBlock(bundle.overall).publicScore, null);
});

test("an already-resolved V10 bundle short-circuits instead of being re-searched", () => {
  const bundle = resolveCanonicalRipV7(v10Contract());
  assert.equal(resolveCanonicalRipV7(bundle), bundle);
});
