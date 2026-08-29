import assert from "node:assert/strict";
import test from "node:test";
import { canonicalCardQueryKey, createRankingsSessionCache } from "./rankingsSessionCache.mjs";

test("successful results persist and identical in-flight requests deduplicate", async () => {
  const cache = createRankingsSessionCache("user:premium:publication");
  let calls = 0;
  const load = async () => { calls += 1; await Promise.resolve(); return { rows: [1] }; };
  const [first, second] = await Promise.all([cache.request("cards:q", load), cache.request("cards:q", load)]);
  assert.equal(calls, 1);
  assert.equal(first, second);
  assert.equal(await cache.request("cards:q", load), first);
  assert.equal(calls, 1);
});

test("cache instances cannot cross canonical request identities", async () => {
  const paid = createRankingsSessionCache("user-a:premium:publication");
  const base = createRankingsSessionCache("user-a:base:publication");
  await paid.request("products:full_market", async () => ({ paid: true }));
  assert.equal(base.peek("products:full_market"), undefined);
});

test("card fingerprints are stable and include every query field", () => {
  const left = new URLSearchParams({ page: "2", search: "mew", direction: "desc", page_size: "50" });
  const right = new URLSearchParams({ page_size: "50", direction: "desc", search: "mew", page: "2" });
  assert.equal(canonicalCardQueryKey(left), canonicalCardQueryKey(right));
  assert.match(canonicalCardQueryKey(left), /page=2/);
  assert.match(canonicalCardQueryKey(left), /search=mew/);
});
