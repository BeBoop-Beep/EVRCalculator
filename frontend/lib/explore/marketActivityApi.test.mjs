import assert from "node:assert/strict";
import test from "node:test";
import {
  fetchMarketActivityCapabilities,
  fetchMarketActivityConstituents,
  fetchMarketActivityGroup,
  fetchMarketActivityInstrument,
  MarketActivityApiError,
} from "./marketActivityApi.mjs";

const SCOPE = {
  marketKey: "set:a",
  activityGenerationId: "activity-a",
  rosterRef: {
    kind: "SURFACE_V2_GENERATION",
    marketKey: "set:a",
    generationId: "roster-a",
  },
  asOf: "2026-09-29",
  windowDays: 30,
};
const response = (status, payload) => ({
  ok: status >= 200 && status < 300,
  status,
  text: async () => JSON.stringify(payload),
});

test("live transports use credentials, exact paths, pins, chart range, cursor, and one explicit instrument read", async () => {
  const calls = [];
  const fetchImpl = async (url, init) => {
    calls.push({ url, init, body: JSON.parse(init.body) });
    return response(200, { ok: true });
  };
  await fetchMarketActivityCapabilities({
    markets: [
      { focusKey: "focus", marketKey: "set:a", rosterRef: SCOPE.rosterRef },
    ],
    fetchImpl,
  });
  await fetchMarketActivityGroup({
    ...SCOPE,
    chartRange: { startDate: "2026-09-01", endDate: "2026-09-29" },
    fetchImpl,
  });
  await fetchMarketActivityConstituents({
    ...SCOPE,
    cursor: "opaque",
    limit: 50,
    fetchImpl,
  });
  await fetchMarketActivityInstrument({
    ...SCOPE,
    instrumentKey: "card:v:raw",
    chartRange: null,
    fetchImpl,
  });
  assert.deepEqual(
    calls.map((call) => call.url),
    [
      "/api/market/explorer/activity/capabilities",
      "/api/market/explorer/activity",
      "/api/market/explorer/activity/constituents",
      "/api/market/explorer/activity/instrument",
    ],
  );
  assert.ok(
    calls.every(
      (call) =>
        call.init.credentials === "include" && call.init.cache === "no-store",
    ),
  );
  assert.deepEqual(calls[1].body, {
    ...SCOPE,
    chartRange: { startDate: "2026-09-01", endDate: "2026-09-29" },
  });
  assert.equal(calls[2].body.cursor, "opaque");
  assert.equal(calls[3].body.instrumentKey, "card:v:raw");
});

for (const [
  status,
  kind,
  retryable,
  payload,
  expectedMessage,
  expectedCode,
] of [
  [
    401,
    "auth",
    false,
    { detail: "sign in required" },
    "sign in required",
    "MARKET_ACTIVITY_UNAVAILABLE",
  ],
  [
    403,
    "entitlement",
    false,
    { detail: { code: "PLAN_REQUIRED", message: "upgrade required" } },
    "upgrade required",
    "PLAN_REQUIRED",
  ],
  [
    400,
    "invalid",
    false,
    { detail: { code: "BAD_SCOPE", message: "scope invalid" } },
    "scope invalid",
    "BAD_SCOPE",
  ],
  [
    503,
    "unavailable",
    true,
    { code: "SOURCE_DOWN", message: "try later" },
    "try later",
    "SOURCE_DOWN",
  ],
]) {
  test(`transport preserves ${status} as ${kind}`, async () => {
    await assert.rejects(
      fetchMarketActivityGroup({
        ...SCOPE,
        fetchImpl: async () => response(status, payload),
      }),
      (error) =>
        error instanceof MarketActivityApiError &&
        error.status === status &&
        error.kind === kind &&
        error.retryable === retryable &&
        error.message === expectedMessage &&
        error.code === expectedCode,
    );
  });
}
