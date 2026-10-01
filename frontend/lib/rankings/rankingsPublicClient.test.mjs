import assert from "node:assert/strict";
import test from "node:test";
import { readPublicPackEconomicsPreview, readPublicProductCatalogue, readPublicRankingsHeadlines } from "./rankingsPublicClient.mjs";

test("public Rankings readers use only their narrow no-store endpoints", async () => {
  const calls = [];
  const fetchImpl = async (url, init) => { calls.push([url, init]); return { ok: true, json: async () => ({ status: "available", rows: [] }) }; };
  await readPublicRankingsHeadlines("era", { fetchImpl });
  await readPublicRankingsHeadlines("set", { fetchImpl });
  await readPublicPackEconomicsPreview({ fetchImpl });
  await readPublicProductCatalogue({ fetchImpl });
  assert.deepEqual(calls.map(([url]) => url), [
    "/api/tcgs/pokemon/rankings/headlines?entity_type=era",
    "/api/tcgs/pokemon/rankings/headlines?entity_type=set",
    "/api/tcgs/pokemon/rankings/pack-economics-preview",
    "/api/tcgs/pokemon/rankings/product-catalogue",
  ]);
  assert.ok(calls.every(([, init]) => init.cache === "no-store" && init.credentials === "include"));
});

test("headline reader rejects non-public entity types before a request", async () => {
  assert.throws(() => readPublicRankingsHeadlines("product", { fetchImpl: async () => assert.fail("must not fetch") }), /set or era/);
});
