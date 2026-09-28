import assert from "node:assert/strict";
import test from "node:test";
import { createRankingsSessionCache } from "./rankingsSessionCache.mjs";
import { loadProductRankingsAuthorities } from "./productRankingsReadPath.mjs";

const response = (status, body) => ({
  ok: status >= 200 && status < 300,
  status,
  json: async () => body,
});
const normalize = (payload) => ({ status: "available", rows: payload.rows, cohortSize: payload.rows.length });

test("an unavailable Full Market warm response rejects, is not cached, and the next healthy read recovers", async () => {
  const cache = createRankingsSessionCache("user-a:publication-n");
  let overallAttempt = 0;
  const fetchImpl = async (url) => {
    if (url.includes("rankings/lens")) return response(200, { status: "available", productFamilyRankings: { families: { booster_box: { products: [] } } } });
    overallAttempt += 1;
    if (overallAttempt === 1) return response(503, { available: false, reason: "refreshing", rows: [] });
    return response(200, { available: true, rows: [{ sealedProductId: "product-1" }] });
  };
  const load = () => loadProductRankingsAuthorities({ fetchImpl, normalizeOverallProductResult: normalize });

  await assert.rejects(cache.request("products:full_market", load), /Full Market product rankings are unavailable/);
  assert.equal(cache.peek("products:full_market"), undefined);

  const healthy = await cache.request("products:full_market", load);
  assert.equal(healthy.state.status, "ready");
  assert.equal(healthy.overallResult.rows[0].sealedProductId, "product-1");
  assert.equal(cache.peek("products:full_market"), healthy);
  assert.equal(overallAttempt, 2);
});

test("family and Full Market failures both reject instead of resolving unavailable cache values", async () => {
  const fetchImpl = async (url) => url.includes("rankings/lens")
    ? response(503, { status: "unavailable" })
    : response(200, { available: true, rows: [] });
  await assert.rejects(
    loadProductRankingsAuthorities({ fetchImpl, normalizeOverallProductResult: normalize }),
    /Product rankings are unavailable/,
  );
});
