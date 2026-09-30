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
import { activityPointAtDate, capabilityIsCurrent, createActivityRequestOwner } from "./marketActivityState.mjs";

test("all 19 accepted fixtures pass manifest, fixture fingerprint, and contract validation", async () => {
  assert.equal(MARKET_ACTIVITY_CONTRACT_VERSION, "market_activity_v1.1");
  assert.equal(MARKET_ACTIVITY_FIXTURE_VERSION, "market_activity_v1_fixtures_2");
  assert.equal(MARKET_ACTIVITY_MANIFEST_SHA256, "e6235d9c73dc7ce6e38b81431bcfe60e4a32ae27f2780632aae45d407705e007");
  assert.equal(MARKET_ACTIVITY_FIXTURE_IDS.length, 19);
  const payloads = await Promise.all(MARKET_ACTIVITY_FIXTURE_IDS.map((fixtureId) => loadMarketActivityFixture({ fixtureId })));
  assert.deepEqual(payloads.map((payload) => payload.contractVersion), Array(19).fill("market_activity_v1.1"));
  assert.equal(payloads[10].kind, "groupActivity");
  assert.equal(payloads[17].availability.reasons[0], "ACTIVITY_GENERATION_EXPIRED");
});

test("request owner rejects A-to-B races and cancellation while in flight", async () => {
  const resolvers = new Map();
  const owner = createActivityRequestOwner(({ marketKey }) => new Promise((resolve) => resolvers.set(marketKey, resolve)));
  const a = owner.request({ marketKey: "A" });
  const b = owner.request({ marketKey: "B" });
  resolvers.get("A")({ value: "old" });
  assert.deepEqual(await a, { stale: true });
  resolvers.get("B")({ value: "current" });
  assert.equal((await b).data.value, "current");
  const c = owner.request({ marketKey: "C" });
  owner.cancel();
  resolvers.get("C")({ value: "disabled" });
  assert.deepEqual(await c, { stale: true });
});

test("sparse dates stay unknown while absence inside a proven sales span is explicit zero", () => {
  const payload = { series: { sales: { provenSpan: { startDate: "2026-09-23", endDate: "2026-09-29" }, counts: { points: [{ date: "2026-09-24", observedCount: 1, proofState: "PROVEN" }] } }, supply: { listings: { points: [] } } } };
  assert.equal(activityPointAtDate(payload, "sales", "2026-09-22").state, "UNKNOWN");
  assert.equal(activityPointAtDate(payload, "sales", "2026-09-25").state, "PROVEN_ZERO");
  assert.equal(activityPointAtDate(payload, "supply", "2026-09-25").state, "UNKNOWN");
});

test("current ask capability expires against evaluation time", () => {
  const capability = { available: true, expiresAt: "2026-10-01T08:00:00Z" };
  assert.equal(capabilityIsCurrent(capability, Date.parse("2026-10-01T07:59:59Z")), true);
  assert.equal(capabilityIsCurrent(capability, Date.parse("2026-10-01T08:00:00Z")), false);
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
  assert.match(client, /overlays=\{chartOverlays\}[\s\S]*activityState=\{activityOn \? activityState : null\}/);
});
