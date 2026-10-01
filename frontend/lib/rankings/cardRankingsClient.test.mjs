import assert from "node:assert/strict";
import test from "node:test";
import { defaultCollectorRequest, prewarmDefaultChase, prewarmDefaultCollector } from "./cardRankingsClient.mjs";
import { createRankingsSessionCache } from "./rankingsSessionCache.mjs";

test("default Collector request uses the mounted component's exact canonical keys", () => {
  const plan = defaultCollectorRequest();
  assert.equal(plan.rowKey, "cards:collector:overall:direction=asc&lens=overall&page=1&page_size=50&sort=rank");
  assert.equal(plan.facetKey, "cards:facets:collector");
});

test("Chase intent prewarm remains Premium-gated and deduped", async () => {
  const originalFetch = globalThis.fetch;
  let calls = 0;
  globalThis.fetch = async () => ({ ok: true, json: async () => (++calls, { rows: [] }) });
  try {
    const cache = createRankingsSessionCache("premium:publication");
    await prewarmDefaultChase({ sessionCache: cache, entitled: false, authStatus: "resolved" });
    await prewarmDefaultChase({ sessionCache: cache, entitled: true, authStatus: "resolved" });
    await prewarmDefaultChase({ sessionCache: cache, entitled: true, authStatus: "resolved" });
    assert.equal(calls, 2);
  } finally { globalThis.fetch = originalFetch; }
});

test("Collector prewarm is entitlement/save-data gated and mount joins its requests", async () => {
  const originalFetch = globalThis.fetch;
  let calls = 0;
  globalThis.fetch = async (url) => ({ ok: true, json: async () => (++calls, url.includes("facets") ? { sets: [] } : { total: 1, rows: [] }) });
  try {
    const cache = createRankingsSessionCache("plus:publication");
    assert.equal(await prewarmDefaultCollector({ sessionCache: cache, entitled: false, authStatus: "resolved" }), null);
    assert.equal(await prewarmDefaultCollector({ sessionCache: cache, entitled: true, authStatus: "resolved", saveData: true }), null);
    await prewarmDefaultCollector({ sessionCache: cache, entitled: true, authStatus: "resolved" });
    await prewarmDefaultCollector({ sessionCache: cache, entitled: true, authStatus: "resolved" });
    assert.equal(calls, 2);
  } finally { globalThis.fetch = originalFetch; }
});
