// V10/V4 frontend TRANSPORT, end to end across the Insights surfaces.
//
// The reader (canonicalRipV7.mjs) has always preferred publicRipContractV10,
// but the normalizers and explore adapters that feed it carried only V5-V9, so
// a V10 payload would have been stripped before the reader ever saw it. A
// canonical cutover would then have required frontend work on top of the
// constant flip. These tests pin the transport so the flip needs none.
//
// PASS-THROUGH ONLY: V4 is never derived from V3 and V10 is never derived from
// V9. A missing V10 must stay missing, so the reader's V10 -> V9 -> V8 fallback
// still decides what renders.

import assert from "node:assert/strict";
import fs from "node:fs";
import path from "node:path";
import test from "node:test";
import { fileURLToPath } from "node:url";

import { normalizePokemonSetInsightsCriticalPayload } from "../../lib/pokemon/pokemonSetInsightsCriticalNormalizer.mjs";
import { adaptCriticalInsightsToExplorePayload } from "../../lib/pokemon/pokemonSetInsightsCriticalExploreAdapter.mjs";
import { resolveCanonicalRipV7, readCanonicalBlock } from "./canonicalRipV7.mjs";

const __dirname = path.dirname(fileURLToPath(import.meta.url));
const readSource = (relative) => fs.readFileSync(path.resolve(__dirname, relative), "utf8");
const splitLines = (source) => source.split("\n").map((line) => line.replace(/\r$/, ""));

// The full normalizer and the full explore adapter are ESM-syntax `.js`/`.jsx`
// this runner cannot import by name, so they are asserted by source inspection
// against the module that owns them - the same technique the V7 suite uses.
const FULL_CLIENT = readSource("../../lib/pokemon/pokemonSetInsightsClient.js");
const PAGE_CLIENT = readSource("./RipStatisticsPageClient.jsx");
const CRITICAL_NORMALIZER = readSource("../../lib/pokemon/pokemonSetInsightsCriticalNormalizer.mjs");
const CRITICAL_ADAPTER = readSource("../../lib/pokemon/pokemonSetInsightsCriticalExploreAdapter.mjs");

const V10_KEYS = ["financialRipV4", "overallRipV10", "publicRipContractV10"];
const HISTORICAL_KEYS = [
  "financialRipV3",
  "overallRipV8",
  "publicRipContractV8",
  "overallRipV9",
  "publicRipContractV9",
];

const block = (score, relativeScore) => ({
  score,
  relativeScore,
  leaderNormalizedScore: relativeScore,
  rank: 4,
  cohortSize: 22,
  tier: "B",
});

const CONTRACT_V10 = {
  contractVersion: "public_rip_contract_v10",
  overallRip: block(41.99, 70.2),
  financialRip: block(39.17, 60.9),
  collectorAppeal: block(67.37, 55.1),
  audit: { overallRipVersion: "overall_rip_v10_90_financial_v4_10_collector_appeal_v5" },
};

const CONTRACT_V9 = {
  contractVersion: "public_rip_contract_v9",
  overallRip: block(42.15, 72.4),
  financialRip: block(39.34, 64.5),
  collectorAppeal: block(67.37, 55.1),
  audit: { overallRipVersion: "overall_rip_v9_90_financial_v3_10_collector_appeal_v5" },
};

const CONTRACT_V8 = {
  contractVersion: "public_rip_contract_v8",
  overallRip: block(38.8, 61.1),
  financialRip: block(36.6, 58.2),
  collectorAppeal: block(70.1, 50.2),
  audit: { overallRipVersion: "overall_rip_v8_90_financial_v3_10_collector_appeal_v4" },
};

const FULL_PAYLOAD = {
  set: { id: "set-1", name: "Temporal Forces", slug: "temporalForces" },
  financialRipV3: block(39.34, 64.5),
  overallRipV8: block(38.8, 61.1),
  publicRipContractV8: CONTRACT_V8,
  overallRipV9: block(42.15, 72.4),
  publicRipContractV9: CONTRACT_V9,
  financialRipV4: block(39.17, 60.9),
  overallRipV10: block(41.99, 70.2),
  publicRipContractV10: CONTRACT_V10,
};

// --------------------------------------------------------------------------- #
// 1. Critical normalization carries V4/V10 (behavioural).
// --------------------------------------------------------------------------- #
test("critical normalization carries V4/V10 verbatim", () => {
  const normalized = normalizePokemonSetInsightsCriticalPayload(FULL_PAYLOAD);
  assert.deepEqual(normalized.financialRipV4, FULL_PAYLOAD.financialRipV4);
  assert.deepEqual(normalized.overallRipV10, FULL_PAYLOAD.overallRipV10);
  assert.deepEqual(normalized.publicRipContractV10, FULL_PAYLOAD.publicRipContractV10);
});

test("critical normalization does not derive V4 from V3 or V10 from V9", () => {
  const withoutV10 = { ...FULL_PAYLOAD };
  for (const key of V10_KEYS) delete withoutV10[key];
  const normalized = normalizePokemonSetInsightsCriticalPayload(withoutV10);
  for (const key of V10_KEYS) {
    assert.deepEqual(normalized[key], {}, `${key} must stay empty, never derived`);
  }
  // The historical inputs it could have been derived FROM are still present.
  assert.deepEqual(normalized.financialRipV3, FULL_PAYLOAD.financialRipV3);
  assert.deepEqual(normalized.overallRipV9, FULL_PAYLOAD.overallRipV9);
});

test("critical normalization leaves V8/V9 intact", () => {
  const normalized = normalizePokemonSetInsightsCriticalPayload(FULL_PAYLOAD);
  for (const key of HISTORICAL_KEYS) {
    assert.deepEqual(normalized[key], FULL_PAYLOAD[key], key);
  }
});

// --------------------------------------------------------------------------- #
// 2. Critical explore adapter carries V4/V10 (behavioural).
// --------------------------------------------------------------------------- #
test("critical adapter carries V4/V10 into explorePayload", () => {
  const explorePayload = adaptCriticalInsightsToExplorePayload(
    normalizePokemonSetInsightsCriticalPayload(FULL_PAYLOAD)
  );
  assert.deepEqual(explorePayload.financialRipV4, FULL_PAYLOAD.financialRipV4);
  assert.deepEqual(explorePayload.overallRipV10, FULL_PAYLOAD.overallRipV10);
  assert.deepEqual(explorePayload.publicRipContractV10, FULL_PAYLOAD.publicRipContractV10);
});

test("critical adapter leaves V8/V9 intact", () => {
  const explorePayload = adaptCriticalInsightsToExplorePayload(
    normalizePokemonSetInsightsCriticalPayload(FULL_PAYLOAD)
  );
  for (const key of HISTORICAL_KEYS) {
    assert.deepEqual(explorePayload[key], FULL_PAYLOAD[key], key);
  }
});

test("critical adapter yields an EMPTY block, never a V9/V3 value, when V10 is absent", () => {
  // Absent V10 normalizes to `{}` and stays `{}` through the adapter - the same
  // shape the existing V8/V9/V3 lines produce for an absent field, so V10 adds
  // no new convention. What matters is that it is EMPTY: `hasContent({})` is
  // false, so the reader's V10 -> V9 -> V8 fallback still fires.
  const withoutV10 = { ...FULL_PAYLOAD };
  for (const key of V10_KEYS) delete withoutV10[key];
  const explorePayload = adaptCriticalInsightsToExplorePayload(
    normalizePokemonSetInsightsCriticalPayload(withoutV10)
  );
  for (const key of V10_KEYS) {
    assert.deepEqual(explorePayload[key], {}, `${key} must be empty, never borrowed`);
  }
  // Explicitly NOT borrowed from the versions it could have been derived from.
  assert.notDeepEqual(explorePayload.financialRipV4, FULL_PAYLOAD.financialRipV3);
  assert.notDeepEqual(explorePayload.overallRipV10, FULL_PAYLOAD.overallRipV9);
  assert.notDeepEqual(explorePayload.publicRipContractV10, FULL_PAYLOAD.publicRipContractV9);
  // ...while the historical values themselves are still fully carried.
  assert.deepEqual(explorePayload.financialRipV3, FULL_PAYLOAD.financialRipV3);
  assert.deepEqual(explorePayload.overallRipV9, FULL_PAYLOAD.overallRipV9);
});

// --------------------------------------------------------------------------- #
// 3. The transported payload still drives the reader correctly (end to end).
// --------------------------------------------------------------------------- #
test("end to end: a transported V10 payload resolves V10 at the reader", () => {
  const explorePayload = adaptCriticalInsightsToExplorePayload(
    normalizePokemonSetInsightsCriticalPayload(FULL_PAYLOAD)
  );
  const resolved = resolveCanonicalRipV7(explorePayload);
  assert.equal(resolved.shape, "publicRipContractV10");
  assert.equal(readCanonicalBlock(resolved.overall).publicScore, 70.2);
  assert.equal(readCanonicalBlock(resolved.financialRip).publicScore, 60.9);
});

test("end to end: mixed V8/V9/V10 transport still selects V10", () => {
  const explorePayload = adaptCriticalInsightsToExplorePayload(
    normalizePokemonSetInsightsCriticalPayload(FULL_PAYLOAD)
  );
  assert.equal(resolveCanonicalRipV7(explorePayload).shape, "publicRipContractV10");
  assert.equal(explorePayload.publicRipContractV8.contractVersion, "public_rip_contract_v8");
  assert.equal(explorePayload.publicRipContractV9.contractVersion, "public_rip_contract_v9");
});

test("end to end: absent V10 falls back to V9, then V8", () => {
  const withoutV10 = { ...FULL_PAYLOAD };
  for (const key of V10_KEYS) delete withoutV10[key];
  const v9Payload = adaptCriticalInsightsToExplorePayload(
    normalizePokemonSetInsightsCriticalPayload(withoutV10)
  );
  assert.equal(resolveCanonicalRipV7(v9Payload).shape, "publicRipContractV9");

  const withoutV9 = { ...withoutV10 };
  delete withoutV9.publicRipContractV9;
  delete withoutV9.overallRipV9;
  const v8Payload = adaptCriticalInsightsToExplorePayload(
    normalizePokemonSetInsightsCriticalPayload(withoutV9)
  );
  assert.equal(resolveCanonicalRipV7(v8Payload).shape, "publicRipContractV8");
});

test("end to end: an unknown payload stays UNAVAILABLE, never zero", () => {
  const explorePayload = adaptCriticalInsightsToExplorePayload(
    normalizePokemonSetInsightsCriticalPayload({ set: { id: "set-1" } })
  );
  const resolved = resolveCanonicalRipV7(explorePayload);
  assert.equal(resolved.shape, null);
  const overall = readCanonicalBlock(resolved.overall);
  assert.equal(overall.publicScore, null);
  assert.notEqual(overall.publicScore, 0);
});

// --------------------------------------------------------------------------- #
// 4. Full normalizer / full adapter (source inspection).
// --------------------------------------------------------------------------- #
test("full normalization carries V4/V10 with pass-through-only semantics", () => {
  for (const key of V10_KEYS) {
    assert.ok(
      FULL_CLIENT.includes(`${key}: toPlainObject(payload?.${key})`),
      `full normalizer must pass ${key} through`
    );
  }
});

test("full adapter carries V4/V10 into explorePayload", () => {
  for (const key of V10_KEYS) {
    assert.ok(
      PAGE_CLIENT.includes(`${key}: normalized?.${key}`),
      `full adapter must carry ${key}`
    );
  }
});

test("no V10/V4 transport line derives from an older version", () => {
  // The ONLY permitted right-hand sides are the identically-named field. A
  // fallback such as `?? payload?.financialRipV3` would silently republish V3
  // under a V4 name, which is exactly what the version identity exists to stop.
  for (const [name, source] of [
    ["critical normalizer", CRITICAL_NORMALIZER],
    ["full normalizer", FULL_CLIENT],
    ["critical adapter", CRITICAL_ADAPTER],
    ["full adapter", PAGE_CLIENT],
  ]) {
    const lines = splitLines(source).filter(
      (line) =>
        V10_KEYS.some((key) => line.trim().startsWith(`${key}:`)) &&
        !line.trim().startsWith("//")
    );
    assert.equal(lines.length, V10_KEYS.length, `${name} must carry exactly 3 V10/V4 lines`);
    for (const line of lines) {
      const [lhs] = line.trim().split(":");
      assert.ok(
        line.includes(`?.${lhs}`),
        `${name}: ${lhs} must read the identically-named field, got: ${line.trim()}`
      );
      for (const older of ["financialRipV3", "overallRipV9", "overallRipV8", "publicRipContractV9"]) {
        assert.ok(
          !line.includes(older),
          `${name}: ${lhs} must not reference ${older}: ${line.trim()}`
        );
      }
    }
  }
});

test("historical passthrough is untouched in every transport module", () => {
  for (const [name, source, ref] of [
    ["critical normalizer", CRITICAL_NORMALIZER, "payload"],
    ["full normalizer", FULL_CLIENT, "payload"],
    ["critical adapter", CRITICAL_ADAPTER, "critical"],
    ["full adapter", PAGE_CLIENT, "normalized"],
  ]) {
    for (const key of HISTORICAL_KEYS) {
      assert.ok(source.includes(`${key}: `) && source.includes(`${ref}?.${key}`), `${name} lost ${key}`);
    }
  }
});
