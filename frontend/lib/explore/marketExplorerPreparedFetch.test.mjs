import test from "node:test";
import assert from "node:assert/strict";
import { buildPreparedSeries, fetchPreparedMarket } from "./marketExplorerPrepared.mjs";
import { classifyPreparedFailure, PreparedFetchError } from "./marketExplorerPreparedLoader.mjs";

const row = (key, extra = {}) => ({
  market_key: key, label: key, asset: "cards", market_type: "set", set_id: "s", era_id: null, parent_era_id: "e",
  comparison_as_of: "2026-09-19", source_as_of: "2026-09-19", generation_id: "gen-7",
  prepared_series_key: `psk:${key}`, source_kind: "public_set_snapshot", history_available: true,
  comparison_value: 10, current_value: 10, comparison_index_value: 100, metadata: {}, window_movements: {}, ...extra,
});
const point = (key, date, value) => ({ market_key: key, market_date: date, index_value: value });

async function withFetch(impl, run) {
  const original = globalThis.fetch;
  const calls = [];
  globalThis.fetch = async (url, init) => { calls.push({ url, init, body: init?.body ? JSON.parse(init.body) : null }); return impl(url, init); };
  try { return await run(calls); } finally { globalThis.fetch = original; }
}
const json = (status, body) => ({ ok: status >= 200 && status < 300, status, json: async () => body });

test("a prepared series carries the backend-published identity for the constituent pager", () => {
  const [series] = buildPreparedSeries([row("set:jungle")], [point("set:jungle", "2026-09-19", 100)]);
  assert.equal(series.key, "set:jungle");
  assert.equal(series.generationId, "gen-7");
  assert.equal(series.preparedSeriesKey, "psk:set:jungle");
  assert.equal(series.sourceKind, "public_set_snapshot");
  assert.equal(series.asset, "cards");
  assert.equal(series.marketType, "set");
  assert.equal(series.comparisonAsOf, "2026-09-19");
});

test("sealed prepared markets are identified as sealed by the row, not by their key", () => {
  const [series] = buildPreparedSeries([row("format:packs", { asset: "sealed", market_type: "prepared_format" })], []);
  assert.equal(series.asset, "sealed");
  assert.equal(series.group, "sealed");
});

test("fetchPreparedMarket requests ONE market and sends other markets only as entitlement context", async () => {
  await withFetch(async () => json(200, { markets: [row("set:jungle")], history: [point("set:jungle", "2026-09-19", 100)] }), async (calls) => {
    const series = await fetchPreparedMarket("set:jungle", { contextKeys: ["era:ex"] });
    assert.deepEqual(calls[0].body, { marketKeys: ["set:jungle"], contextMarketKeys: ["era:ex"] });
    assert.equal(series.trend.length, 1);
  });
});

test("only the requested market's rows and history are used", async () => {
  await withFetch(async () => json(200, { markets: [row("set:jungle"), row("set:other")], history: [point("set:jungle", "2026-09-19", 1), point("set:other", "2026-09-19", 2)] }), async () => {
    const series = await fetchPreparedMarket("set:jungle");
    assert.equal(series.key, "set:jungle");
    assert.equal(series.trend.length, 1);
    assert.equal(series.trend[0].value, 1);
  });
});

test("a market the backend does not return is INVALID_KEY, never a silently empty success", async () => {
  await withFetch(async () => json(200, { markets: [], history: [], missingKeys: ["set:typo"] }), async () => {
    await assert.rejects(fetchPreparedMarket("set:typo"), (error) => {
      assert.ok(error instanceof PreparedFetchError);
      assert.equal(classifyPreparedFailure(error).kind, "INVALID_KEY");
      return true;
    });
  });
});

test("HTTP failures carry status and code and never the raw backend body", async () => {
  await withFetch(async () => json(503, { message: "relation \"x\" statement timeout SQL", code: "PREPARED_COMPARISON_FAILED" }), async () => {
    await assert.rejects(fetchPreparedMarket("set:jungle"), (error) => {
      assert.equal(error.status, 503);
      assert.equal(error.code, "PREPARED_COMPARISON_FAILED");
      assert.doesNotMatch(error.message, /sql|relation|timeout/i);
      return true;
    });
  });
  await withFetch(async () => json(403, { detail: { message: "Compare markets with Index+.", requiredPlan: "plus" } }), async () => {
    await assert.rejects(fetchPreparedMarket("set:jungle"), (error) => classifyPreparedFailure(error).kind === "ENTITLEMENT");
  });
});
