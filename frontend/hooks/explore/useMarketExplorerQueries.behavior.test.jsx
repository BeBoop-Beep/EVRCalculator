// Behavioral (not source-string) tests for the bounded custom-query lane.
import "../../test-support/renderComponentRegister.mjs";
import test from "node:test";
import assert from "node:assert/strict";
import React from "react";
import TestRenderer, { act } from "react-test-renderer";

import useMarketExplorerQueries from "./useMarketExplorerQueries.js";

globalThis.IS_REACT_ACT_ENVIRONMENT = true;

const spec = (id) => ({ asset: "cards", mode: "all", segmentIds: [id] });
const result = (fp) => ({ queryFingerprint: fp, queryKey: fp, displayLabel: `Rarity ${fp}`, trend: [["2026-09-01", 100]], spec: { asset: "cards" }, status: "ready" });
const ok = (fp) => ({ ok: true, status: 200, headers: { get: () => null }, json: async () => result(fp) });

function mount() {
  const box = {};
  function Probe() { Object.assign(box, useMarketExplorerQueries()); return null; }
  let renderer;
  act(() => { renderer = TestRenderer.create(<Probe />); });
  return { box, unmount: () => act(() => renderer.unmount()) };
}
const withFetch = async (impl, fn) => {
  const original = globalThis.fetch; const calls = [];
  globalThis.fetch = (url, init) => { calls.push({ url, init }); return impl(url, init, calls.length); };
  try { return await fn(calls); } finally { globalThis.fetch = original; }
};
const hang = (_u, init) => new Promise((_, reject) => init.signal.addEventListener("abort", () => reject(new DOMException("aborted", "AbortError"))));
const deferred = () => { let resolve; const promise = new Promise((r) => { resolve = r; }); return { promise, resolve }; };

test("success adds one custom market and leaves the result unchanged", async () => {
  await withFetch(async () => ok("fp1"), async (calls) => {
    const { box, unmount } = mount();
    let outcome; await act(async () => { outcome = await box.addQuery(spec("a")); });
    assert.equal(outcome, "added");
    assert.equal(box.querySeries.length, 1);
    assert.equal(box.querySeries[0].queryFingerprint, "fp1");
    assert.equal(box.querySeries[0].label, "Rarity fp1");
    assert.equal(calls.length, 1);
    unmount();
  });
});

test("a hung request times out (bounded), rejects with a user-safe error and clears pending so retry succeeds", async () => {
  let n = 0;
  await withFetch(async (u, init) => (++n === 1 ? hang(u, init) : ok("fp2")), async () => {
    const { box, unmount } = mount();
    const original = globalThis.setTimeout;
    // Fire the 45s bound immediately without waiting.
    globalThis.setTimeout = (fn, ms, ...rest) => original(fn, ms === 45000 ? 5 : ms, ...rest);
    try {
      let error; await act(async () => { try { await box.addQuery(spec("a")); } catch (e) { error = e; } });
      assert.equal(error.code, "QUERY_TIMEOUT");
      assert.match(error.message, /try again/i);
      assert.equal(box.querySeries.length, 0);
      let outcome; await act(async () => { outcome = await box.addQuery(spec("a")); });
      assert.equal(outcome, "added", "retry of the same spec is not blocked by a stuck pending key");
      assert.equal(box.querySeries.length, 1);
    } finally { globalThis.setTimeout = original; }
    unmount();
  });
});

test("a failed rarity fallback (HTTP 500) rejects, adds nothing, and the same spec can be retried", async () => {
  let n = 0;
  await withFetch(async () => (++n === 1 ? { ok: false, status: 500, headers: { get: () => null }, json: async () => ({ message: "boom" }) } : ok("fp3")), async () => {
    const { box, unmount } = mount();
    let error; await act(async () => { try { await box.addQuery(spec("a")); } catch (e) { error = e; } });
    assert.equal(error.message, "boom");
    assert.equal(box.querySeries.length, 0);
    let outcome; await act(async () => { outcome = await box.addQuery(spec("a")); });
    assert.equal(outcome, "added");
    unmount();
  });
});

test("double click on the same spec issues ONE request; the second call reports duplicate", async () => {
  const gate = deferred();
  await withFetch(async () => { await gate.promise; return ok("fp4"); }, async (calls) => {
    const { box, unmount } = mount();
    let first, second;
    await act(async () => {
      first = box.addQuery(spec("a")); second = await box.addQuery(spec("a"));
      gate.resolve(); await first;
    });
    assert.equal(second, "duplicate");
    assert.equal(calls.length, 1);
    assert.equal(box.querySeries.length, 1);
    unmount();
  });
});

test("clearAll while pending aborts the request and a late result is never re-added", async () => {
  const gate = deferred(); let aborted = false;
  await withFetch(async (_u, init) => { init.signal.addEventListener("abort", () => { aborted = true; }); await gate.promise; return ok("fp5"); }, async () => {
    const { box, unmount } = mount();
    let pending; act(() => { pending = box.addQuery(spec("a")); });
    act(() => { box.clearAll(); });
    assert.equal(aborted, true, "clearAll aborts the in-flight request");
    let outcome; await act(async () => { gate.resolve(); try { outcome = await pending; } catch (e) { outcome = e.code; } });
    assert.ok(outcome === "cancelled" || outcome === "QUERY_ABORTED", `late result must not be added (got ${outcome})`);
    assert.equal(box.querySeries.length, 0);
    unmount();
  });
});

test("unmount while pending aborts the request and nothing is added afterwards", async () => {
  let aborted = false;
  await withFetch(async (u, init) => { init.signal.addEventListener("abort", () => { aborted = true; }); return hang(u, init); }, async () => {
    const { box, unmount } = mount();
    let pending; act(() => { pending = box.addQuery(spec("a")); });
    unmount();
    assert.equal(aborted, true);
    let code; await pending.catch((e) => { code = e.code; });
    assert.equal(code, "QUERY_ABORTED");
  });
});

test("a stale response finishing after clearAll is discarded while a NEW request after the clear works", async () => {
  const gate = deferred();
  await withFetch(async (_u, _i, n) => (n === 1 ? (await gate.promise, ok("stale")) : ok("fresh")), async () => {
    const { box, unmount } = mount();
    let stale; act(() => { stale = box.addQuery(spec("a")).catch(() => "aborted"); });
    act(() => { box.clearAll(); });
    let outcome; await act(async () => { outcome = await box.addQuery(spec("b")); });
    assert.equal(outcome, "added");
    await act(async () => { gate.resolve(); await stale; });
    assert.deepEqual(box.querySeries.map((s) => s.queryFingerprint), ["fresh"]);
    unmount();
  });
});
