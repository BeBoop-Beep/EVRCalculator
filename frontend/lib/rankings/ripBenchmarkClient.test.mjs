import assert from "node:assert/strict";
import test from "node:test";
import { boundedHistoryWindows, readBenchmarkOverviewHeadlines, readCurrentBenchmark, readCurrentProductBenchmark, readCurrentSetHeadlines, readFinancialRipHistory } from "./ripBenchmarkClient.mjs";
const entities = (count) => Array.from({ length: count }, (_, i) => ({ entity_type: "set", entity_id: String(i + 1) }));
test("current reads deduplicate and chunk to at most ten entities", async () => { const bodies = []; const fetchImpl = async (_url, init) => { const body = JSON.parse(init.body); bodies.push(body); return { ok: true, json: async () => ({ status: "available", publication_id: "p", market_date: "2026-09-25", calibration_version: "c", cohort_fingerprint: "f", freshness: { benchmarkMarketDate: "2026-09-25" }, rows: [] }) }; }; await readCurrentBenchmark([...entities(22), entities(1)[0]], { fetchImpl }); assert.deepEqual(bodies.map((body) => body.entities.length), [10, 10, 2]); assert.ok(bodies.every((body) => !("benchmark_key" in body) && !("calibration_version" in body))); });
test("mixed current publications fail closed", async () => { let call = 0; const fetchImpl = async () => ({ ok: true, json: async () => ({ status: "available", publication_id: `p${++call}`, market_date: "2026-09-25", calibration_version: "c", cohort_fingerprint: "f", freshness: { benchmarkMarketDate: "2026-09-25" }, rows: [] }) }); await assert.rejects(() => readCurrentBenchmark(entities(11), { fetchImpl }), /Mixed Benchmark publications/); });
test("Product Benchmark uses one browser-visible batch request without browser-selected authority", async () => { const calls = []; const fetchImpl = async (url, init) => { calls.push({ url, body: JSON.parse(init.body) }); return { ok: true, json: async () => ({ status: "available", rows: [] }) }; }; await readCurrentProductBenchmark(entities(22), { fetchImpl }); assert.equal(calls.length, 1); assert.equal(calls[0].url, "/api/tcgs/pokemon/rip-benchmark/current-batch"); assert.equal(calls[0].body.entities.length, 22); assert.ok(!("benchmark_key" in calls[0].body) && !("calibration_version" in calls[0].body)); });
test("public Set headlines dedupe IDs, stay bounded, and send no model authority", async () => { const calls = []; const fetchImpl = async (url, init) => { calls.push({ url, body: JSON.parse(init.body) }); return { ok: true, json: async () => ({ status: "available", rows: [] }) }; }; await readCurrentSetHeadlines(["a", "a", "b"], { fetchImpl }); assert.deepEqual(calls, [{ url: "/api/tcgs/pokemon/rip-benchmark/set-headlines", body: { set_ids: ["a", "b"] } }]); await assert.rejects(() => readCurrentSetHeadlines(Array.from({ length: 11 }, (_, index) => String(index)), { fetchImpl }), /limited to 10/); });
test("ALL history windows never exceed 366 inclusive days and do not overlap", () => { const windows = boundedHistoryWindows("2024-01-01", "2026-09-25"); for (const [start, end] of windows) assert.ok((new Date(end) - new Date(start)) / 86400000 <= 365); for (let i = 1; i < windows.length; i++) assert.equal((new Date(windows[i][0]) - new Date(windows[i - 1][1])) / 86400000, 1); });

test("Financial history uses one bounded paid request and never sends model authority", async () => {
  const calls = [];
  const fetchImpl = async (url, init) => {
    calls.push({ url, body: JSON.parse(init.body), credentials: init.credentials });
    return { ok: true, json: async () => ({ contractVersion: "financial-rip-history-v1", status: "available", rows: [] }) };
  };
  await readFinancialRipHistory([
    { entity_type: "set", entity_id: "1" },
    { entity_type: "era", entity_id: "2" },
  ], { startDate: "2026-09-01", endDate: "2026-09-27", fetchImpl });
  assert.equal(calls.length, 1);
  assert.equal(calls[0].url, "/api/tcgs/pokemon/rip-benchmark/financial-history");
  assert.equal(calls[0].credentials, "include");
  assert.deepEqual(calls[0].body.entities.map((entry) => entry.entity_type), ["set", "era"]);
  assert.ok(!("benchmark_key" in calls[0].body) && !("calibration_version" in calls[0].body));
});

test("Financial history follows typed cursors and returns one complete logical result", async () => {
  const calls = [];
  const cursor = { market_date: "2026-09-25", entity_type: "set", entity_id: "1", publication_id: "p1" };
  const pages = [
    {
      contractVersion: "financial-rip-history-v1",
      status: "available",
      rows: [{ market_date: "2026-09-25", entity_id: "1" }],
      hasMore: true,
      nextCursor: cursor,
      historyAvailableFrom: "2026-09-15",
      historyAvailableThrough: "2026-09-27",
    },
    {
      contractVersion: "financial-rip-history-v1",
      status: "available",
      rows: [{ market_date: "2026-09-27", entity_id: "1" }],
      hasMore: false,
      nextCursor: null,
      historyAvailableFrom: "2026-09-15",
      historyAvailableThrough: "2026-09-27",
    },
  ];
  const fetchImpl = async (_url, init) => {
    calls.push(JSON.parse(init.body));
    return { ok: true, json: async () => pages[calls.length - 1] };
  };
  const result = await readFinancialRipHistory(
    [{ entity_type: "set", entity_id: "1" }],
    { startDate: "2026-09-15", endDate: "2026-09-27", limit: 1, fetchImpl },
  );
  assert.equal(calls.length, 2);
  assert.equal("after" in calls[0], false);
  assert.deepEqual(calls[1].after, cursor);
  assert.deepEqual(result.rows.map((row) => row.market_date), ["2026-09-25", "2026-09-27"]);
  assert.equal(result.hasMore, false);
  assert.equal(result.historyAvailableFrom, "2026-09-15");
  assert.equal(result.historyAvailableThrough, "2026-09-27");
});

test("Financial history rejects Product entities client-side", async () => {
  await assert.rejects(
    () => readFinancialRipHistory([{ entity_type: "sealed_product", entity_id: "1" }], {
      startDate: "2026-09-01", endDate: "2026-09-27",
    }),
    /Sets and Eras only/,
  );
});

test("Overview headlines is a public no-body read", async () => {
  const calls = [];
  const fetchImpl = async (url, init) => {
    calls.push({ url, init });
    return { ok: true, json: async () => ({ status: "available" }) };
  };
  await readBenchmarkOverviewHeadlines({ fetchImpl });
  assert.deepEqual(calls, [{
    url: "/api/tcgs/pokemon/rip-benchmark/overview-headlines",
    init: { cache: "no-store" },
  }]);
});
