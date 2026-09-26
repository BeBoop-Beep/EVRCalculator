// Deterministic failure injection for the prepared-market selection lifecycle.
// No network, no timers: `fetchMarket` is a controllable fake.
import test from "node:test";
import assert from "node:assert/strict";
import {
  classifyPreparedFailure,
  createPreparedMarketLoader,
  describePreparedFailure,
  loadedPreparedSeries,
  PREPARED_FAILURE,
  PreparedFetchError,
} from "./marketExplorerPreparedLoader.mjs";

/** A fake backend whose responses the test settles by hand, per market key. */
function harness(options = {}) {
  const calls = [];
  const pending = new Map();
  const loader = createPreparedMarketLoader({
    fetchMarket: (key, context) => new Promise((resolve, reject) => {
      calls.push({ key, ...context });
      pending.set(key, { resolve, reject, signal: context.signal });
      context.signal?.addEventListener("abort", () => reject(Object.assign(new Error("aborted"), { name: "AbortError" })));
    }),
    setTimer: () => 0,
    clearTimer: () => {},
    ...options,
  });
  const ok = (key) => pending.get(key).resolve({ key, label: key, trend: [{ date: "2026-09-01", value: 100 }, { date: "2026-09-02", value: 101 }] });
  const fail = (key, status, code) => pending.get(key).reject(new PreparedFetchError("x", { status, code }));
  const tick = () => new Promise((resolve) => setTimeout(resolve, 0));
  return { loader, calls, ok, fail, tick, snap: () => loader.getSnapshot() };
}

test("a click is PENDING, not active, until its data loads", async () => {
  const h = harness();
  const done = h.loader.add("set:jungle");
  await h.tick();
  assert.deepEqual(h.snap().pending, ["set:jungle"]);
  assert.deepEqual(loadedPreparedSeries(h.snap()), []);
  h.ok("set:jungle");
  assert.equal(await done, "loaded");
  assert.deepEqual(h.snap().pending, []);
  assert.deepEqual(loadedPreparedSeries(h.snap()).map((s) => s.key), ["set:jungle"]);
});

test("a newly added market that fails rolls back; prior loaded markets remain", async () => {
  const h = harness();
  const ex = h.loader.add("era:ex"); await h.tick(); h.ok("era:ex"); await ex;
  const jungle = h.loader.add("set:jungle"); await h.tick();
  h.fail("set:jungle", 503, "PREPARED_COMPARISON_FAILED");
  assert.equal(await jungle, "failed");
  assert.deepEqual(h.snap().order, ["era:ex"], "failed market is not silently active");
  assert.deepEqual(Object.keys(h.snap().loaded), ["era:ex"]);
  assert.equal(h.snap().failed["set:jungle"].kind, PREPARED_FAILURE.unavailable);
});

test("a failed market is never re-sent and does not poison the next selection", async () => {
  const h = harness();
  const jungle = h.loader.add("set:jungle"); await h.tick(); h.fail("set:jungle", 503, ""); await jungle;
  const fossil = h.loader.add("set:fossil"); await h.tick();
  const request = h.calls.find((call) => call.key === "set:fossil");
  assert.deepEqual(request.contextKeys, [], "failed key must not ride along as context");
  h.ok("set:fossil");
  assert.equal(await fossil, "loaded");
  assert.deepEqual(Object.keys(h.snap().loaded), ["set:fossil"]);
});

test("each add fetches ONLY the new market; loaded histories are never refetched", async () => {
  const h = harness();
  for (const key of ["era:ex", "set:base", "curated:premium"]) {
    const p = h.loader.add(key); await h.tick(); h.ok(key); await p;
  }
  assert.deepEqual(h.calls.map((call) => call.key), ["era:ex", "set:base", "curated:premium"]);
  assert.deepEqual(h.calls[2].contextKeys, ["era:ex", "set:base"], "context is entitlement-only");
});

test("retry after failure succeeds and only retries the failed operation", async () => {
  const h = harness();
  const first = h.loader.add("set:team-rocket"); await h.tick(); h.fail("set:team-rocket", 504, ""); await first;
  assert.equal(h.snap().failed["set:team-rocket"].kind, PREPARED_FAILURE.timeout);
  const retry = h.loader.retry("set:team-rocket"); await h.tick();
  assert.deepEqual(h.snap().failed, {}, "retry clears the failure while loading");
  h.ok("set:team-rocket");
  assert.equal(await retry, "loaded");
  assert.equal(h.calls.length, 2);
});

test("dismissing a failure never removes a successful market", async () => {
  const h = harness();
  const a = h.loader.add("era:ex"); await h.tick(); h.ok("era:ex"); await a;
  const b = h.loader.add("set:fossil"); await h.tick(); h.fail("set:fossil", 503, ""); await b;
  h.loader.dismissFailure("set:fossil");
  assert.deepEqual(h.snap().failed, {});
  assert.deepEqual(Object.keys(h.snap().loaded), ["era:ex"]);
});

test("remove-while-loading: the old response must not re-add the market", async () => {
  const h = harness();
  const p = h.loader.add("set:jungle"); await h.tick();
  h.loader.remove("set:jungle");
  assert.deepEqual(h.snap().pending, []);
  try { h.ok("set:jungle"); } catch { /* aborted first */ }
  assert.equal(await p, "stale");
  assert.deepEqual(h.snap().order, []);
  assert.deepEqual(h.snap().loaded, {});
});

test("stale response after a newer add of the same market cannot overwrite it", async () => {
  const h = harness();
  const first = h.loader.add("set:jungle"); await h.tick();
  h.loader.remove("set:jungle");
  const second = h.loader.add("set:jungle"); await h.tick();
  // The FIRST request's promise was aborted; the second is the only live one.
  assert.equal(await first, "stale");
  h.ok("set:jungle");
  assert.equal(await second, "loaded");
  assert.deepEqual(Object.keys(h.snap().loaded), ["set:jungle"]);
});

test("rapid Fossil -> Jungle -> Team Rocket does not cross-wire, even out of order", async () => {
  const h = harness();
  const fossil = h.loader.add("set:fossil");
  const jungle = h.loader.add("set:jungle");
  const rocket = h.loader.add("set:team-rocket");
  await h.tick();
  assert.deepEqual(h.snap().pending, ["set:fossil", "set:jungle", "set:team-rocket"]);
  h.ok("set:team-rocket"); h.ok("set:fossil"); h.ok("set:jungle");
  await Promise.all([fossil, jungle, rocket]);
  assert.deepEqual(loadedPreparedSeries(h.snap()).map((s) => s.key), ["set:fossil", "set:jungle", "set:team-rocket"],
    "chart order follows the user's request order, not completion order");
  for (const series of loadedPreparedSeries(h.snap())) assert.equal(h.snap().loaded[series.key].key, series.key);
});

test("duplicate clicks are guarded while pending and once loaded", async () => {
  const h = harness();
  const a = h.loader.add("era:ex");
  assert.equal(await h.loader.add("era:ex"), "duplicate");
  await h.tick(); h.ok("era:ex"); await a;
  assert.equal(await h.loader.add("era:ex"), "duplicate");
  assert.equal(h.calls.length, 1);
});

test("a multi-market workspace survives one failed addition", async () => {
  const h = harness();
  const keys = ["era:ex", "set:base", "rarity:rare-ultra"];
  for (const key of keys) { const p = h.loader.add(key); await h.tick(); h.ok(key); await p; }
  const bad = h.loader.add("set:jungle"); await h.tick(); h.fail("set:jungle", 503, ""); await bad;
  assert.deepEqual(h.snap().order, keys);
  assert.deepEqual(Object.keys(h.snap().loaded), keys);
});

test("Basic replace keeps the previous line until the replacement loads; a failed swap leaves it intact", async () => {
  const h = harness();
  const first = h.loader.replace("era:ex"); await h.tick(); h.ok("era:ex"); await first;
  const swap = h.loader.replace("set:jungle"); await h.tick();
  assert.deepEqual(Object.keys(h.snap().loaded), ["era:ex"]);
  h.fail("set:jungle", 503, ""); await swap;
  assert.deepEqual(Object.keys(h.snap().loaded), ["era:ex"]);
  const again = h.loader.replace("set:jungle"); await h.tick(); h.ok("set:jungle"); await again;
  assert.deepEqual(Object.keys(h.snap().loaded), ["set:jungle"]);
  assert.deepEqual(h.snap().order, ["set:jungle"]);
});

test("Basic replace cancels a superseded in-flight request", async () => {
  const h = harness();
  const a = h.loader.replace("set:fossil"); await h.tick();
  const b = h.loader.replace("set:jungle"); await h.tick();
  assert.equal(await a, "stale");
  h.ok("set:jungle"); await b;
  assert.deepEqual(Object.keys(h.snap().loaded), ["set:jungle"]);
});

test("AbortError is not a failure", async () => {
  const h = harness();
  const p = h.loader.add("set:jungle"); await h.tick();
  h.loader.clear();
  assert.equal(await p, "stale");
  assert.deepEqual(h.snap().failed, {});
});

test("a request that exceeds its bound fails as TIMEOUT (not a silent abort) and can be retried", async () => {
  let fire;
  const h = harness({ setTimer: (fn) => { fire = fn; return 1; }, clearTimer: () => {} });
  const p = h.loader.add("set:jungle"); await h.tick();
  fire();
  assert.equal(await p, "failed");
  assert.equal(h.snap().failed["set:jungle"].kind, PREPARED_FAILURE.timeout);
  assert.deepEqual(h.snap().pending, [], "no permanent adding state");
});

test("clear() drops every market and ignores late responses", async () => {
  const h = harness();
  const a = h.loader.add("era:ex"); await h.tick();
  h.loader.clear();
  try { h.ok("era:ex"); } catch { /* aborted */ }
  await a;
  assert.deepEqual(h.snap().order, []);
});

test("refresh replaces a loaded market in place and keeps the old line if it fails", async () => {
  const h = harness();
  const p = h.loader.add("set:base"); await h.tick(); h.ok("set:base"); await p;
  const refreshing = h.loader.refresh("set:base"); await h.tick();
  h.fail("set:base", 503, "");
  assert.equal(await refreshing, "failed");
  assert.deepEqual(Object.keys(h.snap().loaded), ["set:base"]);
});

test("the 25-market bound is enforced without dropping anything", async () => {
  const h = harness();
  for (let i = 0; i < 25; i += 1) { const p = h.loader.add(`set:${i}`); await h.tick(); h.ok(`set:${i}`); await p; }
  assert.equal(await h.loader.add("set:extra"), "limit");
  assert.equal(h.snap().order.length, 25);
});

test("entitlement and auth failures are not transient outages and are not retryable", () => {
  const entitlement = classifyPreparedFailure({ status: 403 });
  const auth = classifyPreparedFailure({ status: 401 });
  assert.equal(entitlement.kind, PREPARED_FAILURE.entitlement);
  assert.equal(entitlement.retryable, false);
  assert.equal(auth.kind, PREPARED_FAILURE.auth);
  assert.equal(auth.retryable, false);
  assert.equal(classifyPreparedFailure({ status: 503, code: "PREPARED_PROXY_UNAVAILABLE" }).kind, PREPARED_FAILURE.unavailable);
  assert.equal(classifyPreparedFailure({ status: 504 }).kind, PREPARED_FAILURE.timeout);
  assert.equal(classifyPreparedFailure({ status: 404, code: "PREPARED_MARKET_UNKNOWN" }).kind, PREPARED_FAILURE.invalidKey);
  assert.equal(classifyPreparedFailure({ status: 0 }).kind, PREPARED_FAILURE.transient);
  assert.equal(classifyPreparedFailure({ status: 0 }).retryable, true);
});

test("failure copy names the failed market, is concise and exposes no backend internals", () => {
  const text = describePreparedFailure("Jungle", { kind: PREPARED_FAILURE.timeout });
  assert.equal(text, "Jungle took too long to load.");
  assert.doesNotMatch(describePreparedFailure("Jungle", { kind: PREPARED_FAILURE.unavailable }), /sql|postgrest|rpc|statement/i);
  assert.equal(describePreparedFailure("Jungle", { kind: PREPARED_FAILURE.entitlement }), "Comparing markets is included with Index+.");
});

// Explicit vintage edition markets share one setId; loader identity is the marketKey.
const UNL = "set:jungle-id:unlimited";
const FIRST = "set:jungle-id:first_edition";

test("two editions of one Set load as two distinct lines and removing one keeps the other", async () => {
  const h = harness();
  const a = h.loader.add(UNL); await h.tick(); h.ok(UNL); await a;
  const b = h.loader.add(FIRST); await h.tick(); h.ok(FIRST); await b;
  assert.deepEqual(loadedPreparedSeries(h.snap()).map((s) => s.key).sort(), [FIRST, UNL]);
  h.loader.remove(UNL);
  assert.deepEqual(h.snap().order, [FIRST]);
  assert.deepEqual(Object.keys(h.snap().loaded), [FIRST]);
});

test("a failing edition market does not fail, remove or refetch its sibling; retry is per marketKey", async () => {
  const h = harness();
  const a = h.loader.add(UNL); await h.tick(); h.ok(UNL); await a;
  const b = h.loader.add(FIRST); await h.tick(); h.fail(FIRST, 503, "PREPARED_COMPARISON_FAILED");
  assert.equal(await b, "failed");
  assert.deepEqual(h.snap().order, [UNL]);
  assert.ok(h.snap().failed[FIRST] && !h.snap().failed[UNL]);
  assert.equal(h.calls.filter((call) => call.key === UNL).length, 1, "sibling never refetched");
  const retry = h.loader.retry(FIRST); await h.tick(); h.ok(FIRST);
  assert.equal(await retry, "loaded");
  assert.deepEqual(loadedPreparedSeries(h.snap()).map((s) => s.key).sort(), [FIRST, UNL]);
  assert.equal(h.calls.filter((call) => call.key === UNL).length, 1);
});

// REGRESSION (live develop): Fossil -> Jungle replacement sent
// marketKeys=[Jungle], contextMarketKeys=[Fossil]; the backend counted two unique
// keys as a comparison and demanded Index+. Replacement is NOT comparison.
test("REPLACE never sends the outgoing market as comparison context", async () => {
  const h = harness();
  const first = h.loader.replace("set:fossil");
  await h.tick();
  h.ok("set:fossil");
  await first;
  const second = h.loader.replace("set:jungle");
  await h.tick();
  const jungle = h.calls.find((c) => c.key === "set:jungle");
  assert.deepEqual(jungle.contextKeys, []);
  // the previous line is still visible until the replacement lands
  assert.deepEqual(h.snap().order.includes("set:fossil"), true);
  h.ok("set:jungle");
  assert.equal(await second, "loaded");
  assert.deepEqual(h.snap().order, ["set:jungle"]);
});

test("a failed REPLACE keeps the old market and still sent no context", async () => {
  const h = harness();
  const first = h.loader.replace("set:fossil");
  await h.tick(); h.ok("set:fossil"); await first;
  const second = h.loader.replace("set:jungle");
  await h.tick();
  h.fail("set:jungle", 500, "X");
  assert.equal(await second, "failed");
  assert.deepEqual(h.snap().order, ["set:fossil"]);
  assert.deepEqual(h.calls.find((c) => c.key === "set:jungle").contextKeys, []);
});

test("ADD (real comparison) still sends the workspace as context", async () => {
  const h = harness();
  const first = h.loader.add("set:fossil");
  await h.tick(); h.ok("set:fossil"); await first;
  h.loader.add("set:jungle");
  await h.tick();
  assert.deepEqual(h.calls.find((c) => c.key === "set:jungle").contextKeys, ["set:fossil"]);
});
