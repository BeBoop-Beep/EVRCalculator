// The historical version matrix for the canonical RIP reader.
//
// One table, one rule per row: which block a payload resolves to, and that
// resolving a newer block never rewrites or corrupts the historical blocks that
// travelled with it. The reader must render whichever contract the backend
// chose to serve - reading V10 is NOT a promotion, and dropping V8 support
// would blank every historical snapshot still carrying it.

import assert from "node:assert/strict";
import test from "node:test";

import { readCanonicalBlock, resolveCanonicalRipV7 } from "./canonicalRipV7.mjs";

const overall = (score, relativeScore) => ({
  score,
  relativeScore,
  rank: 3,
  cohortSize: 22,
  tier: "B",
});

const CONTRACT_V8 = {
  contractVersion: "public_rip_contract_v8",
  overallRip: overall(38.8, 61.1),
  financialRip: overall(36.6, 58.2),
  collectorAppeal: overall(70.1, 55.3),
  audit: { overallRipVersion: "overall_rip_v8_90_financial_v3_10_collector_appeal_v4" },
};

const CONTRACT_V9 = {
  contractVersion: "public_rip_contract_v9",
  overallRip: overall(42.9, 72.4),
  financialRip: overall(38.8, 64.5),
  collectorAppeal: overall(79.8, 66.7),
  audit: { overallRipVersion: "overall_rip_v9_90_financial_v3_10_collector_appeal_v5" },
};

const CONTRACT_V10 = {
  contractVersion: "public_rip_contract_v10",
  overallRip: overall(40.9, 70.2),
  financialRip: overall(36.5, 60.9),
  collectorAppeal: overall(79.8, 66.7),
  audit: { overallRipVersion: "overall_rip_v10_90_financial_v4_10_collector_appeal_v5" },
};

// --------------------------------------------------------------------------- #
// One block present -> that block resolves.
// --------------------------------------------------------------------------- #
test("matrix: a V8 payload resolves the V8 contract", () => {
  const resolved = resolveCanonicalRipV7({ publicRipContractV8: CONTRACT_V8 });
  assert.equal(resolved.shape, "publicRipContractV8");
  assert.equal(readCanonicalBlock(resolved.overall).publicScore, 61.1);
});

test("matrix: a V9 payload resolves the V9/V3 contract", () => {
  const resolved = resolveCanonicalRipV7({ publicRipContractV9: CONTRACT_V9 });
  assert.equal(resolved.shape, "publicRipContractV9");
  assert.equal(readCanonicalBlock(resolved.overall).publicScore, 72.4);
  assert.equal(readCanonicalBlock(resolved.financialRip).publicScore, 64.5);
});

test("matrix: a V10 payload resolves the V10/V4 contract", () => {
  const resolved = resolveCanonicalRipV7({ publicRipContractV10: CONTRACT_V10 });
  assert.equal(resolved.shape, "publicRipContractV10");
  assert.equal(readCanonicalBlock(resolved.overall).publicScore, 70.2);
  assert.equal(readCanonicalBlock(resolved.financialRip).publicScore, 60.9);
});

// --------------------------------------------------------------------------- #
// Several blocks present -> newest supported wins, historical blocks intact.
// --------------------------------------------------------------------------- #
test("matrix: a mixed payload resolves the newest supported block", () => {
  const payload = {
    publicRipContractV8: CONTRACT_V8,
    publicRipContractV9: CONTRACT_V9,
    publicRipContractV10: CONTRACT_V10,
  };
  const resolved = resolveCanonicalRipV7(payload);
  assert.equal(resolved.shape, "publicRipContractV10");
  assert.equal(readCanonicalBlock(resolved.overall).publicScore, 70.2);
});

test("matrix: resolving a newer block does not corrupt the historical blocks", () => {
  const payload = {
    publicRipContractV8: CONTRACT_V8,
    publicRipContractV9: CONTRACT_V9,
    publicRipContractV10: CONTRACT_V10,
  };
  resolveCanonicalRipV7(payload);
  assert.equal(payload.publicRipContractV8.overallRip.relativeScore, 61.1);
  assert.equal(payload.publicRipContractV9.overallRip.relativeScore, 72.4);
  assert.equal(payload.publicRipContractV10.overallRip.relativeScore, 70.2);
  assert.equal(
    payload.publicRipContractV8.audit.overallRipVersion,
    "overall_rip_v8_90_financial_v3_10_collector_appeal_v4"
  );
  assert.equal(
    payload.publicRipContractV9.audit.overallRipVersion,
    "overall_rip_v9_90_financial_v3_10_collector_appeal_v5"
  );
});

// --------------------------------------------------------------------------- #
// Missing current version -> clean fallback down the lineage.
// --------------------------------------------------------------------------- #
test("matrix: without V10 the reader falls back to V9", () => {
  const resolved = resolveCanonicalRipV7({
    publicRipContractV8: CONTRACT_V8,
    publicRipContractV9: CONTRACT_V9,
  });
  assert.equal(resolved.shape, "publicRipContractV9");
  assert.equal(readCanonicalBlock(resolved.overall).publicScore, 72.4);
});

test("matrix: without V10 or V9 the reader falls back to V8", () => {
  const resolved = resolveCanonicalRipV7({ publicRipContractV8: CONTRACT_V8 });
  assert.equal(resolved.shape, "publicRipContractV8");
  assert.equal(readCanonicalBlock(resolved.overall).publicScore, 61.1);
});

test("matrix: an empty V10 block does not shadow a usable V9 block", () => {
  const resolved = resolveCanonicalRipV7({
    publicRipContractV10: {},
    publicRipContractV9: CONTRACT_V9,
  });
  assert.equal(resolved.shape, "publicRipContractV9");
});

// --------------------------------------------------------------------------- #
// Top-level objects, and failing safe.
// --------------------------------------------------------------------------- #
test("matrix: top-level V10 prefers financialRipV4 and falls back to V3", () => {
  const withV4 = resolveCanonicalRipV7({
    overallRipV10: overall(40.9, 70.2),
    financialRipV4: overall(36.5, 60.9),
    financialRipV3: overall(38.8, 64.5),
  });
  assert.equal(withV4.shape, "topLevelV10");
  assert.equal(readCanonicalBlock(withV4.financialRip).publicScore, 60.9);

  const withoutV4 = resolveCanonicalRipV7({
    overallRipV10: overall(40.9, 70.2),
    financialRipV3: overall(38.8, 64.5),
  });
  assert.equal(withoutV4.shape, "topLevelV10");
  assert.equal(readCanonicalBlock(withoutV4.financialRip).publicScore, 64.5);
});

test("matrix: an unknown or empty payload is UNAVAILABLE, never invented", () => {
  for (const payload of [{}, null, undefined, { publicRipContractV99: CONTRACT_V10 }, { rip: {} }]) {
    const resolved = resolveCanonicalRipV7(payload);
    assert.equal(resolved.shape, null);
    const block = readCanonicalBlock(resolved.overall);
    assert.equal(block.publicScore, null);
    assert.notEqual(block.publicScore, 0);
  }
});

test("matrix: a contract with no scores does not fabricate a zero", () => {
  const resolved = resolveCanonicalRipV7({
    publicRipContractV10: { contractVersion: "public_rip_contract_v10", overallRip: {} },
  });
  const block = readCanonicalBlock(resolved.overall);
  assert.equal(block.publicScore, null);
});
