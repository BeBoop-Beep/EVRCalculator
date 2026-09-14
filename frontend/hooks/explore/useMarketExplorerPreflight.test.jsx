import "../../test-support/renderComponentRegister.mjs";
import test from "node:test";
import assert from "node:assert/strict";
import React from "react";
import TestRenderer, { act } from "react-test-renderer";
import useMarketExplorerPreflight from "./useMarketExplorerPreflight.js";

globalThis.IS_REACT_ACT_ENVIRONMENT = true;
const base = { asset: "cards", eraIds: [], setIds: [], segmentIds: [], pokemonIds: [], priceSegmentIds: [], releaseAgeCohortIds: [], mode: "all" };
const wait = (ms) => new Promise((resolve) => setTimeout(resolve, ms));
function Harness({ spec, onResult, debounceMs = 15 }) { const result = useMarketExplorerPreflight(spec, { debounceMs }); onResult(result); return null; }
const response = (payload, status = 200, retryAfter = null) => ({ status, ok: status < 400, json: async () => payload, headers: { get: (key) => key === "Retry-After" ? retryAfter : null } });

test("preflight debounces checkbox changes into one canonical request", async () => {
  const calls = []; const states = [];
  global.fetch = async (_url, init) => { calls.push(JSON.parse(init.body)); return response({ readiness: "PREFLIGHT_READY", matchingConstituentCount: 1, matchingSetCount: 1 }); };
  let renderer;
  await act(async () => { renderer = TestRenderer.create(<Harness spec={{ ...base, segmentIds: ["legend"] }} onResult={(value) => states.push(value)} />); });
  await act(async () => { renderer.update(<Harness spec={{ ...base, segmentIds: ["legend", "radiantRare"] }} onResult={(value) => states.push(value)} />); });
  await act(async () => { await wait(40); });
  assert.equal(calls.length, 1);
  assert.deepEqual(calls[0].segmentIds, ["legend", "radiantRare"]);
  assert.equal(states.at(-1).state, "ready");
  renderer.unmount();
});

test("asset changes abort and invalidate stale Filtered Cards responses", async () => {
  const pending = []; const states = [];
  global.fetch = (_url, init) => new Promise((resolve, reject) => { pending.push({ resolve, reject, signal: init.signal }); init.signal.addEventListener("abort", () => reject(Object.assign(new Error("aborted"), { name: "AbortError" }))); });
  let renderer;
  await act(async () => { renderer = TestRenderer.create(<Harness spec={{ ...base, segmentIds: ["legend"] }} onResult={(value) => states.push(value)} debounceMs={0} />); });
  await act(async () => { await wait(5); });
  await act(async () => { renderer.update(<Harness spec={{ ...base, asset: "sealed" }} onResult={(value) => states.push(value)} debounceMs={0} />); });
  assert.equal(pending[0].signal.aborted, true);
  assert.equal(states.at(-1).state, "idle");
  renderer.unmount();
});
