import assert from "node:assert/strict";
import test from "node:test";
import React from "react";
import TestRenderer, { act } from "react-test-renderer";
import * as marketSignalsModule from "./usePokemonSetMarketSignals.js";
const usePokemonSetMarketSignals = marketSignalsModule.default?.default || marketSignalsModule.default;

globalThis.IS_REACT_ACT_ENVIRONMENT = true;
const wait = (ms) => new Promise((resolve) => setTimeout(resolve, ms));
const jsonResponse = (status, body) => new Response(JSON.stringify(body), { status, headers: { "content-type": "application/json" } });

async function mount(setId, enabled = true, initialPayload = null) {
  let latest;
  function Probe(props) { latest = usePokemonSetMarketSignals(props.setId, { enabled: props.enabled, initialPayload: props.initialPayload }); return null; }
  let renderer;
  await act(async () => { renderer = TestRenderer.create(React.createElement(Probe, { setId, enabled, initialPayload })); await wait(10); });
  return { renderer, state: () => latest, update: async (nextSetId, nextEnabled, nextInitialPayload = null) => act(async () => { renderer.update(React.createElement(Probe, { setId: nextSetId, enabled: nextEnabled, initialPayload: nextInitialPayload })); await wait(10); }) };
}

test("valid bootstrap breadth prevents the initial request", async () => {
  let calls = 0; globalThis.fetch = async () => { calls += 1; return jsonResponse(500, {}); };
  const seed = { set: { id: "seeded-set" }, marketBreadth: { "7D": { total: 8 } } };
  const probe = await mount("seeded-set", true, seed);
  assert.equal(calls, 0); assert.equal(probe.state().status, "success"); assert.equal(probe.state().payload, seed);
  await act(async () => probe.renderer.unmount());
});

test("disabled signals hook performs no request and clears paid payload", async () => {
  let calls = 0; globalThis.fetch = async () => { calls += 1; return jsonResponse(200, { marketBreadth: { "7D": {} } }); };
  const probe = await mount("disabled-set", false);
  assert.equal(calls, 0); assert.equal(probe.state().status, "idle"); assert.equal(probe.state().payload, null);
  await act(async () => probe.renderer.unmount());
});

test("one retryable 503 retries exactly once and succeeds", async () => {
  let calls = 0; globalThis.fetch = async () => ++calls === 1 ? jsonResponse(503, { retryable: true }) : jsonResponse(200, { marketBreadth: { "7D": { advancing: 1 } } });
  const probe = await mount("retry-set"); await act(async () => { await wait(410); });
  assert.equal(calls, 2); assert.equal(probe.state().status, "success"); assert.equal(probe.state().payload.marketBreadth["7D"].advancing, 1);
  await act(async () => probe.renderer.unmount());
});

test("403 fails closed without automatic retry", async () => {
  let calls = 0; globalThis.fetch = async () => { calls += 1; return jsonResponse(403, { code: "INDEX_PLUS_REQUIRED" }); };
  const probe = await mount("forbidden-set"); await act(async () => { await wait(410); });
  assert.equal(calls, 1); assert.equal(probe.state().status, "forbidden"); assert.equal(probe.state().payload, null);
  await act(async () => probe.renderer.unmount());
});

test("two failures settle error; manual retry starts one fresh successful cycle", async () => {
  let calls = 0; let recover = false;
  globalThis.fetch = async () => { calls += 1; return recover ? jsonResponse(200, { marketBreadth: { "7D": { total: 9 } } }) : jsonResponse(504, { retryable: true }); };
  const probe = await mount("manual-set"); await act(async () => { await wait(410); });
  assert.equal(calls, 2); assert.equal(probe.state().status, "error");
  recover = true; await act(async () => { probe.state().retry(); await wait(20); });
  assert.equal(calls, 3); assert.equal(probe.state().status, "success"); assert.equal(probe.state().payload.marketBreadth["7D"].total, 9);
  await act(async () => probe.renderer.unmount());
});

test("late Set A result cannot populate Set B", async () => {
  const pending = new Map();
  globalThis.fetch = (url) => new Promise((resolve) => pending.set(String(url), resolve));
  const probe = await mount("set-a");
  await probe.update("set-b", true);
  const a = [...pending.entries()].find(([url]) => url.includes("set-a"));
  const b = [...pending.entries()].find(([url]) => url.includes("set-b"));
  await act(async () => { a[1](jsonResponse(200, { set: { id: "set-a" }, marketBreadth: { "7D": { total: 1 } } })); await wait(10); });
  assert.equal(probe.state().payload, null);
  await act(async () => { b[1](jsonResponse(200, { set: { id: "set-b" }, marketBreadth: { "7D": { total: 2 } } })); await wait(10); });
  assert.equal(probe.state().payload.set.id, "set-b");
  await act(async () => probe.renderer.unmount());
});

test("logout or downgrade clears the successful paid payload", async () => {
  let calls = 0; globalThis.fetch = async () => { calls += 1; return jsonResponse(200, { marketBreadth: { "7D": { total: 3 } } }); };
  const probe = await mount("downgrade-set");
  assert.equal(probe.state().status, "success");
  await probe.update("downgrade-set", false);
  assert.equal(probe.state().status, "idle"); assert.equal(probe.state().payload, null); assert.equal(calls, 1);
  await act(async () => probe.renderer.unmount());
});
