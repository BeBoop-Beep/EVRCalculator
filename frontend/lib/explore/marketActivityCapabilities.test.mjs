import assert from "node:assert/strict";
import test from "node:test";
import {
  activityCapabilityBatchKey,
  activityRosterRefForSeries,
  eligibleActivityMarkets,
  normalizeCapabilityResponse,
} from "./marketActivityCapabilities.mjs";

test("prepared markets derive exact published generation refs; unsupported assets and unstable custom queries fail closed", () => {
  assert.deepEqual(
    activityRosterRefForSeries({
      key: "set:a",
      asset: "cards",
      generationId: "g1",
    }),
    { kind: "SURFACE_V2_GENERATION", marketKey: "set:a", generationId: "g1" },
  );
  assert.equal(
    activityRosterRefForSeries({
      key: "sealed:a",
      asset: "sealed",
      generationId: "g1",
    }),
    null,
  );
  assert.equal(
    activityRosterRefForSeries({
      key: "graded:a",
      asset: "graded",
      generationId: "g1",
    }),
    null,
  );
  assert.equal(
    activityRosterRefForSeries({
      key: "query:f",
      asset: "cards",
      queryFingerprint: "f",
    }),
    null,
  );
  assert.deepEqual(
    activityRosterRefForSeries({
      key: "query:f",
      asset: "cards",
      queryFingerprint: "f",
      revisionId: "r1",
      computedThrough: "2026-09-29",
      activityMarketKey: "query-market:f",
    }),
    {
      kind: "QUERY_CACHE_PUBLISHED_REVISION",
      queryFingerprint: "f",
      revisionId: "r1",
      computedThrough: "2026-09-29",
    },
  );
});

test("active-set key is order stable, identity and plan scoped, and independent of focus", () => {
  const a = { key: "set:a", asset: "cards", generationId: "g1" };
  const b = { key: "set:b", asset: "cards", generationId: "g2" };
  const first = eligibleActivityMarkets([a, b]);
  assert.equal(
    activityCapabilityBatchKey(first, "user-1", "plus"),
    activityCapabilityBatchKey(
      eligibleActivityMarkets([b, a]),
      "user-1",
      "plus",
    ),
  );
  assert.notEqual(
    activityCapabilityBatchKey(first, "user-1", "plus"),
    activityCapabilityBatchKey(first, "user-2", "plus"),
  );
  assert.equal(activityCapabilityBatchKey(first, "user-1", "basic"), null);
  assert.equal(eligibleActivityMarkets([a]).length, 1);
});

test("capability response keeps explicit unavailable values and ignores unrequested focus keys", () => {
  const markets = eligibleActivityMarkets([
    { key: "set:a", asset: "cards", generationId: "g1" },
  ]);
  const unavailable = {
    available: false,
    marketKey: "set:a",
    reasons: ["NOT_PUBLISHED"],
  };
  assert.deepEqual(
    normalizeCapabilityResponse(
      {
        contractVersion: "market_activity_v1.1",
        capabilities: { "set:a": unavailable, injected: { available: true } },
      },
      markets,
    ),
    { "set:a": unavailable },
  );
});

test("capability normalization rejects a roster mismatch and generations coexist independently", () => {
  const markets = eligibleActivityMarkets([
    { key: "set:a", asset: "cards", generationId: "g1" },
    { key: "set:b", asset: "cards", generationId: "g2" },
    { key: "set:c", asset: "cards", generationId: "g3" },
  ]);
  const capability = (marketKey, generationId) => ({
    available: true,
    marketKey,
    rosterRef: { kind: "SURFACE_V2_GENERATION", marketKey, generationId },
  });
  assert.deepEqual(
    normalizeCapabilityResponse(
      {
        contractVersion: "market_activity_v1.1",
        capabilities: {
          "set:a": capability("set:a", "g1"),
          "set:b": capability("set:b", "wrong"),
          "set:c": capability("set:c", "g3"),
        },
      },
      markets,
    ),
    {
      "set:a": capability("set:a", "g1"),
      "set:c": capability("set:c", "g3"),
    },
  );
});
