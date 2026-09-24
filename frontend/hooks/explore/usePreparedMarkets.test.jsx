import "../../test-support/renderComponentRegister.mjs";
import test from "node:test";
import assert from "node:assert/strict";
import React from "react";
import TestRenderer, { act } from "react-test-renderer";
import usePreparedMarkets from "./usePreparedMarkets.js";
import { PreparedFetchError } from "../../lib/explore/marketExplorerPreparedLoader.mjs";

globalThis.IS_REACT_ACT_ENVIRONMENT = true;

test("React binding: loaded / pending / failed are separate and a failure keeps loaded lines", async () => {
  const settle = new Map();
  const fetchMarket = (key) => new Promise((resolve, reject) => settle.set(key, { resolve, reject }));
  let latest;
  function Probe() { latest = usePreparedMarkets({ fetchMarket }); return null; }
  await act(async () => { TestRenderer.create(<Probe />); });

  await act(async () => { latest.loader.add("era:ex"); });
  assert.deepEqual(latest.pendingKeys, ["era:ex"]);
  assert.deepEqual(latest.loadedKeys, [], "requested is not active");
  await act(async () => { settle.get("era:ex").resolve({ key: "era:ex", trend: [] }); await Promise.resolve(); await Promise.resolve(); });
  assert.deepEqual(latest.loadedKeys, ["era:ex"]);
  assert.deepEqual(latest.pendingKeys, []);

  await act(async () => { latest.loader.add("set:jungle"); });
  await act(async () => { settle.get("set:jungle").reject(new PreparedFetchError("x", { status: 503 })); await Promise.resolve(); await Promise.resolve(); });
  assert.deepEqual(latest.loadedKeys, ["era:ex"]);
  assert.deepEqual(latest.failedKeys, ["set:jungle"]);
  assert.deepEqual(latest.pendingKeys, []);
});

test("unmounting aborts in-flight requests so a late response cannot update state", async () => {
  let signal;
  const fetchMarket = (key, context) => new Promise(() => { signal = context.signal; });
  let latest;
  function Probe() { latest = usePreparedMarkets({ fetchMarket }); return null; }
  let renderer;
  await act(async () => { renderer = TestRenderer.create(<Probe />); });
  await act(async () => { latest.loader.add("set:base"); });
  await act(async () => { renderer.unmount(); });
  assert.equal(signal.aborted, true);
});
