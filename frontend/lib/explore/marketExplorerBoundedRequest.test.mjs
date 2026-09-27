import test from "node:test";
import assert from "node:assert/strict";
import fs from "node:fs";
import { boundedFetch, BoundedRequestError } from "./marketExplorerBoundedRequest.mjs";

const hangingFetch = (_url, init) => new Promise((_, reject) => {
  init.signal.addEventListener("abort", () => reject(new DOMException("aborted", "AbortError")));
});

test("a hanging request rejects with a user-safe timeout instead of pending forever", async () => {
  await assert.rejects(
    boundedFetch("/x", {}, { timeoutMs: 20, fetchImpl: hangingFetch }),
    (error) => error instanceof BoundedRequestError && error.timedOut && error.code === "QUERY_TIMEOUT" && /try again/i.test(error.message),
  );
});

test("caller abort rejects as cancelled and is not reported as a timeout", async () => {
  const controller = new AbortController();
  const pending = boundedFetch("/x", {}, { timeoutMs: 5000, signal: controller.signal, fetchImpl: hangingFetch });
  controller.abort();
  await assert.rejects(pending, (error) => error.aborted && !error.timedOut && error.code === "QUERY_ABORTED");
});

test("a stalled body read is inside the same bound", async () => {
  const fetchImpl = async () => ({ ok: true });
  await assert.rejects(
    boundedFetch("/x", {}, { timeoutMs: 20, fetchImpl: async (u, i) => { await fetchImpl(); return { signal: i.signal }; },
      read: (res) => new Promise((_, reject) => res.signal.addEventListener("abort", () => reject(new Error("x")))) }),
    (error) => error.timedOut,
  );
});

test("success returns response and payload and clears its timer", async () => {
  let cleared = false;
  const result = await boundedFetch("/x", {}, {
    fetchImpl: async () => ({ ok: true }), read: async () => ({ a: 1 }), clearTimer: () => { cleared = true; },
  });
  assert.deepEqual(result.payload, { a: 1 });
  assert.equal(cleared, true);
});

test("every query-backed caller goes through the one bounded hook primitive", () => {
  const hook = fs.readFileSync(new URL("../../hooks/explore/useMarketExplorerQueries.js", import.meta.url), "utf8");
  assert.match(hook, /boundedFetch\(/);
  assert.doesNotMatch(hook, /await fetch\(/);
  assert.match(hook, /startedEpoch !== epoch\.current\) return "cancelled"/);
  for (const name of ["MarketExplorerRarityMarkets", "MarketExplorerExactBasket", "MarketExplorerQueryBuilder"]) {
    const src = fs.readFileSync(new URL(`../../components/explore/${name}.jsx`, import.meta.url), "utf8");
    assert.doesNotMatch(src, /fetch\("\/api\/market\/explorer\/query"/);
    assert.match(src, /cancelled/);
  }
});
