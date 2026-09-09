import "../../test-support/renderComponentRegister.mjs";
import test from "node:test";
import assert from "node:assert/strict";
import React from "react";
import TestRenderer, { act } from "react-test-renderer";
import useMarketExplorerFilterOptions, { __resetMarketExplorerFilterOptionsCache } from "./useMarketExplorerFilterOptions.js";

globalThis.IS_REACT_ACT_ENVIRONMENT = true;

function Probe(props) {
  const state = useMarketExplorerFilterOptions(props);
  return <output data-status={state.status}>{state.status}</output>;
}

test("signed-out options retry once after live auth changes and successful data stays cached", async () => {
  __resetMarketExplorerFilterOptionsCache();
  const originalFetch = globalThis.fetch;
  let calls = 0;
  globalThis.fetch = async () => {
    calls += 1;
    return calls === 1
      ? { ok: false, status: 401, json: async () => ({ detail: "Not authenticated" }) }
      : { ok: true, status: 200, json: async () => ({ eras: [], sets: [] }) };
  };
  try {
    let renderer;
    await act(async () => { renderer = TestRenderer.create(<Probe isAuthenticated={false} authRevision={0} />); });
    assert.equal(renderer.root.findByType("output").props["data-status"], "signedOut");
    assert.equal(calls, 1);
    await act(async () => { renderer.update(<Probe isAuthenticated authRevision={1} />); });
    assert.equal(renderer.root.findByType("output").props["data-status"], "ready");
    assert.equal(calls, 2);
    await act(async () => { renderer.update(<Probe isAuthenticated authRevision={2} />); });
    assert.equal(calls, 2, "a successful canonical payload must not refetch");
    renderer.unmount();
  } finally {
    globalThis.fetch = originalFetch;
    __resetMarketExplorerFilterOptionsCache();
  }
});
