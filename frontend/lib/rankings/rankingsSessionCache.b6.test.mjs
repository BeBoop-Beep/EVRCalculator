import assert from "node:assert/strict";
import test from "node:test";
import { canonicalCardQueryKey, createRankingsSessionCache } from "./rankingsSessionCache.mjs";

const params = (values) => new URLSearchParams(values);

test("card keys isolate lens, filters, and page while exact reads reuse cache", async () => {
  const cache = createRankingsSessionCache("user-a:plus:publication-1");
  let reads = 0;
  const load = async () => ({ sequence: ++reads });
  const overall = canonicalCardQueryKey(params({ page: "1", set: "a" }), "collector:overall");
  const trainer = canonicalCardQueryKey(params({ page: "1", set: "a" }), "collector:trainer");
  const page2 = canonicalCardQueryKey(params({ page: "2", set: "a" }), "collector:overall");
  assert.deepEqual(await cache.request(overall, load), await cache.request(overall, load));
  await cache.request(trainer, load);
  await cache.request(page2, load);
  assert.equal(reads, 3);
});

test("forced late predecessor cannot overwrite a newer same-key cache value", async () => {
  const cache = createRankingsSessionCache("user-a:plus:publication-1");
  let releaseOld;
  const old = cache.request("cards:q", () => new Promise((resolve) => { releaseOld = resolve; }));
  const fresh = cache.request("cards:q", async () => "fresh", { force: true });
  assert.equal(await fresh, "fresh");
  releaseOld("old");
  assert.equal(await old, "old");
  assert.equal(cache.peek("cards:q"), "fresh");
});

test("different access identities never share protected values", async () => {
  const paid = createRankingsSessionCache("user-a:plus:publication-1");
  const base = createRankingsSessionCache("user-a:base:publication-1");
  await paid.request("cards:q", async () => "paid rows");
  assert.equal(base.peek("cards:q"), undefined);
});
