import assert from "node:assert/strict";
import test from "node:test";
import { readFile } from "node:fs/promises";
import { fileURLToPath } from "node:url";
import {
  MARKET_ACTIVITY_CONTRACT_VERSION,
  MARKET_ACTIVITY_FIXTURE_IDS,
  MARKET_ACTIVITY_FIXTURE_VERSION,
  MARKET_ACTIVITY_MANIFEST_SHA256,
  loadMarketActivityFixture,
} from "./marketActivityFixtures.mjs";
import {
  activityDateGeometry,
  activityPointAtDate,
  capabilityIsCurrent,
  createActivityRequestOwner,
  validateActivityConstituentResponse,
  validateActivityInstrumentResponse,
  validateActivityResponseScope,
} from "./marketActivityState.mjs";

const SCOPE = Object.freeze({
  focusMarketKey: "focus:A",
  marketKey: "market:A",
  activityGenerationId: "generation-A",
  rosterRef: Object.freeze({
    kind: "SURFACE_V2_GENERATION",
    marketKey: "market:A",
    generationId: "roster-A",
  }),
  evidenceFingerprint: "evidence-A",
  asOf: "2026-09-29",
  windowDays: 30,
  tier: "RAW",
});
const scopedPayload = (overrides = {}) => ({
  contractVersion: "market_activity_v1.1",
  activityGenerationId: SCOPE.activityGenerationId,
  evidenceFingerprint: SCOPE.evidenceFingerprint,
  availability: { state: "AVAILABLE", reasons: [] },
  request: {
    marketKey: SCOPE.marketKey,
    activityGenerationId: SCOPE.activityGenerationId,
    rosterRef: SCOPE.rosterRef,
    asOf: SCOPE.asOf,
    windowDays: SCOPE.windowDays,
  },
  series: { sales: { tier: "RAW" } },
  ...overrides,
});

test("all 19 accepted fixtures pass manifest, fixture fingerprint, and contract validation", async () => {
  assert.equal(MARKET_ACTIVITY_CONTRACT_VERSION, "market_activity_v1.1");
  assert.equal(
    MARKET_ACTIVITY_FIXTURE_VERSION,
    "market_activity_v1_fixtures_2",
  );
  assert.equal(
    MARKET_ACTIVITY_MANIFEST_SHA256,
    "e6235d9c73dc7ce6e38b81431bcfe60e4a32ae27f2780632aae45d407705e007",
  );
  assert.equal(MARKET_ACTIVITY_FIXTURE_IDS.length, 19);
  const payloads = await Promise.all(
    MARKET_ACTIVITY_FIXTURE_IDS.map((fixtureId) =>
      loadMarketActivityFixture({ fixtureId }),
    ),
  );
  assert.deepEqual(
    payloads.map((payload) => payload.contractVersion),
    Array(19).fill("market_activity_v1.1"),
  );
  assert.equal(payloads[10].kind, "groupActivity");
  assert.equal(
    payloads[17].availability.reasons[0],
    "ACTIVITY_GENERATION_EXPIRED",
  );
});

test("request owner rejects A-to-B races and cancellation while in flight", async () => {
  const resolvers = new Map();
  const owner = createActivityRequestOwner(
    ({ focusMarketKey }) =>
      new Promise((resolve) => resolvers.set(focusMarketKey, resolve)),
  );
  const aScope = { ...SCOPE, focusMarketKey: "focus:A" };
  const bScope = { ...SCOPE, focusMarketKey: "focus:B" };
  const a = owner.request(aScope);
  const b = owner.request(bScope);
  resolvers.get("focus:A")({ value: "old" });
  assert.deepEqual(await a, { stale: true });
  resolvers.get("focus:B")(scopedPayload());
  assert.equal((await b).data.request.marketKey, "market:A");
  const c = owner.request({ ...SCOPE, focusMarketKey: "focus:C" });
  owner.cancel();
  resolvers.get("focus:C")({ value: "disabled" });
  assert.deepEqual(await c, { stale: true });
});

test("response scope must exactly match market, generation, roster, as-of, window, tier, and evidence", () => {
  assert.equal(
    validateActivityResponseScope(scopedPayload(), SCOPE).request.marketKey,
    "market:A",
  );
  const cases = [
    scopedPayload({
      request: { ...scopedPayload().request, marketKey: "market:B" },
    }),
    scopedPayload({ activityGenerationId: "generation-B" }),
    scopedPayload({
      request: {
        ...scopedPayload().request,
        rosterRef: { ...SCOPE.rosterRef, generationId: "roster-B" },
      },
    }),
    scopedPayload({
      request: { ...scopedPayload().request, asOf: "2026-09-28" },
    }),
    scopedPayload({ request: { ...scopedPayload().request, windowDays: 90 } }),
    scopedPayload({ series: { sales: { tier: "GRADED" } } }),
    scopedPayload({ evidenceFingerprint: "evidence-B" }),
  ];
  for (const payload of cases)
    assert.throws(
      () => validateActivityResponseScope(payload, SCOPE),
      /does not match/,
    );
});

test("constituent responses own their fingerprint and exactly echo roster, generation, cursor, and limit", () => {
  const payload = scopedPayload({
    evidenceFingerprint: "a".repeat(64),
    request: { ...scopedPayload().request, cursor: "next-50", limit: 50 },
  });
  assert.equal(
    validateActivityConstituentResponse(payload, SCOPE, {
      cursor: "next-50",
      limit: 50,
    }),
    payload,
  );
  assert.notEqual(payload.evidenceFingerprint, SCOPE.evidenceFingerprint);
  for (const invalid of [
    { ...payload, evidenceFingerprint: SCOPE.evidenceFingerprint },
    { ...payload, activityGenerationId: "generation-B" },
    { ...payload, request: { ...payload.request, cursor: "wrong" } },
    { ...payload, request: { ...payload.request, limit: 100 } },
    {
      ...payload,
      request: {
        ...payload.request,
        rosterRef: { ...SCOPE.rosterRef, generationId: "roster-B" },
      },
    },
  ])
    assert.throws(() =>
      validateActivityConstituentResponse(invalid, SCOPE, {
        cursor: "next-50",
        limit: 50,
      }),
    );
});

test("instrument responses own their fingerprint and exactly echo request and returned identity", () => {
  const cardVariantId = "variant-a";
  const instrumentKey = `card:${cardVariantId}:raw`;
  const chartRange = { startDate: "2026-09-01", endDate: "2026-09-29" };
  const payload = scopedPayload({
    evidenceFingerprint: "b".repeat(64),
    request: { ...scopedPayload().request, instrumentKey, chartRange },
    instrument: { instrumentKey, cardVariantId, tier: "RAW" },
  });
  const options = { instrumentKey, cardVariantId, chartRange, tier: "RAW" };
  assert.equal(
    validateActivityInstrumentResponse(payload, SCOPE, options),
    payload,
  );
  assert.throws(() =>
    validateActivityInstrumentResponse(
      {
        ...payload,
        instrument: { ...payload.instrument, cardVariantId: "variant-b" },
      },
      SCOPE,
      options,
    ),
  );
  assert.throws(() =>
    validateActivityInstrumentResponse(
      { ...payload, request: { ...payload.request, chartRange: null } },
      SCOPE,
      options,
    ),
  );
});

test("sparse dates stay unknown while absence inside a proven sales span is explicit zero", () => {
  const payload = {
    series: {
      sales: {
        provenSpan: { startDate: "2026-09-23", endDate: "2026-09-29" },
        counts: {
          points: [
            { date: "2026-09-24", observedCount: 1, proofState: "PROVEN" },
          ],
        },
      },
      supply: { listings: { points: [] } },
    },
  };
  assert.equal(
    activityPointAtDate(payload, "sales", "2026-09-22").state,
    "UNKNOWN",
  );
  assert.equal(
    activityPointAtDate(payload, "sales", "2026-09-25").state,
    "PROVEN_ZERO",
  );
  assert.equal(
    activityPointAtDate(payload, "supply", "2026-09-25").state,
    "UNKNOWN",
  );
});

test("current ask capability expires against evaluation time", () => {
  const capability = { available: true, expiresAt: "2026-10-01T08:00:00Z" };
  assert.equal(
    capabilityIsCurrent(capability, Date.parse("2026-10-01T07:59:59Z")),
    true,
  );
  assert.equal(
    capabilityIsCurrent(capability, Date.parse("2026-10-01T08:00:00Z")),
    false,
  );
});

test("sparse points use canonical x positions and preserve gaps", () => {
  const geometry = activityDateGeometry(
    [
      { date: "2026-09-20", value: 3 },
      { date: "2026-09-25", value: 2 },
      { date: "2026-09-28", value: 0 },
    ],
    [
      "2026-09-20",
      "2026-09-21",
      "2026-09-22",
      "2026-09-23",
      "2026-09-24",
      "2026-09-25",
      "2026-09-26",
      "2026-09-27",
      "2026-09-28",
    ],
  );
  assert.deepEqual(
    geometry.map((point) => point.canonicalIndex),
    [0, 5, 8],
  );
  assert.deepEqual(
    geometry.map((point) => point.xPercent),
    [2, 62, 98],
  );
});

test("Activity remains a companion pane with one tooltip owner and no production route", async () => {
  const root = fileURLToPath(new URL("../..", import.meta.url));
  const [chart, pane, client] = await Promise.all([
    readFile(`${root}/components/explore/MarketPerformanceChart.jsx`, "utf8"),
    readFile(`${root}/components/explore/MarketActivityPane.jsx`, "utf8"),
    readFile(`${root}/components/explore/MarketExplorerClient.jsx`, "utf8"),
  ]);
  assert.match(chart, /data-market-performance-tooltip/);
  assert.doesNotMatch(pane, /Tooltip|createPortal/);
  assert.match(client, /activityState=\{activityOn \? activityState : null\}/);
  assert.match(
    client,
    /overlays=\{chartOverlays\}[\s\S]*activityState=\{activityOn \? activityState : null\}/,
  );
});
