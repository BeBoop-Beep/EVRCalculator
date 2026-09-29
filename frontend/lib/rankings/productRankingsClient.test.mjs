import assert from "node:assert/strict";
import test from "node:test";
import { readProductRankings } from "./productRankingsClient.mjs";

test("Scores and Economics have independent session-cache authorities", async () => {
  const calls = [];
  const values = new Map();
  const sessionCache = { request: async (key, load) => values.has(key) ? values.get(key) : load().then((value) => (values.set(key, value), value)) };
  const fetchImpl = async (url) => { calls.push(url); return { ok: true, json: async () => ({ status: "available", rows: [] }) }; };
  await readProductRankings("scores", { fetchImpl, sessionCache });
  await readProductRankings("scores", { fetchImpl, sessionCache });
  await readProductRankings("economics", { fetchImpl, sessionCache });
  await readProductRankings("economics", { fetchImpl, sessionCache });
  assert.deepEqual(calls, ["/api/explore/product-rankings/scores", "/api/explore/product-rankings/economics"]);
});
