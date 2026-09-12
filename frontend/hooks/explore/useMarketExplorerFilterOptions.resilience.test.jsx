import "../../test-support/renderComponentRegister.mjs";
import test from "node:test";
import assert from "node:assert/strict";
import React from "react";
import TestRenderer, { act } from "react-test-renderer";
import useMarketExplorerFilterOptions, {
  OPTIONS_STATUS,
  __resetMarketExplorerFilterOptionsCache,
  isRetryableOptionsFailure,
} from "./useMarketExplorerFilterOptions.js";

globalThis.IS_REACT_ACT_ENVIRONMENT = true;
const FAST_RETRIES = Object.freeze([1, 1]);
const PAYLOAD = { eras: [{ id: "sv", label: "Scarlet & Violet" }], sets: [] };
const pause = (milliseconds = 8) => new Promise((resolve) => setTimeout(resolve, milliseconds));

function Probe(props) {
  const state = useMarketExplorerFilterOptions({ retryDelays: FAST_RETRIES, ...props });
  return (
    <div>
      <output data-status={state.status} data-options={state.options} data-message={state.message} />
      <button type="button" onClick={state.retry}>retry</button>
    </div>
  );
}

const statusOf = (renderer) => renderer.root.findByType("output").props["data-status"];

async function mountAndSettle(props = {}) {
  let renderer;
  await act(async () => { renderer = TestRenderer.create(<Probe {...props} />); });
  await act(async () => { await pause(20); });
  return renderer;
}

async function withFetch(fetchImpl, body) {
  __resetMarketExplorerFilterOptionsCache();
  const originalFetch = globalThis.fetch;
  globalThis.fetch = fetchImpl;
  try {
    await body();
  } finally {
    globalThis.fetch = originalFetch;
    __resetMarketExplorerFilterOptionsCache();
  }
}

test("retry classification is explicit and excludes auth plus deterministic 4xx", () => {
  assert.equal(isRetryableOptionsFailure({ status: OPTIONS_STATUS.offline }), true);
  for (const httpStatus of [500, 502, 503]) assert.equal(isRetryableOptionsFailure({ httpStatus }), true);
  for (const httpStatus of [400, 401, 403, 404]) assert.equal(isRetryableOptionsFailure({ httpStatus }), false);
});

test("a transient 503 and a transport failure each recover automatically", async () => {
  for (const firstFailure of ["503", "network"]) {
    let calls = 0;
    await withFetch(async () => {
      calls += 1;
      if (calls === 1) {
        if (firstFailure === "network") throw new TypeError("offline");
        return { ok: false, status: 503, json: async () => ({ message: "brief outage" }) };
      }
      return { ok: true, status: 200, json: async () => PAYLOAD };
    }, async () => {
      const renderer = await mountAndSettle();
      assert.equal(statusOf(renderer), OPTIONS_STATUS.ready, `${firstFailure}: ${calls} requests`);
      assert.equal(calls, 2);
      await act(async () => renderer.unmount());
    });
  }
});

test("transient retries are bounded while 401 and 403 never retry", async () => {
  for (const scenario of [
    { status: 503, expected: OPTIONS_STATUS.unavailable, calls: 3 },
    { status: 401, expected: OPTIONS_STATUS.signedOut, calls: 1 },
    { status: 403, expected: OPTIONS_STATUS.forbidden, calls: 1 },
    { status: 404, expected: OPTIONS_STATUS.unavailable, calls: 1 },
  ]) {
    let calls = 0;
    await withFetch(async () => {
      calls += 1;
      return { ok: false, status: scenario.status, json: async () => ({ detail: `status ${scenario.status}` }) };
    }, async () => {
      const renderer = await mountAndSettle();
      assert.equal(statusOf(renderer), scenario.expected, `${scenario.status}: ${calls} requests`);
      assert.equal(calls, scenario.calls);
      await act(async () => renderer.unmount());
    });
  }
});

test("manual retry starts a new bounded attempt and clears the exhausted error on success", async () => {
  let calls = 0;
  let recovered = false;
  await withFetch(async () => {
    calls += 1;
    return recovered
      ? { ok: true, status: 200, json: async () => PAYLOAD }
      : { ok: false, status: 503, json: async () => ({ message: "maintenance" }) };
  }, async () => {
    const renderer = await mountAndSettle();
    assert.equal(statusOf(renderer), OPTIONS_STATUS.unavailable);
    assert.equal(calls, 3);
    recovered = true;
    await act(async () => {
      renderer.root.findByType("button").props.onClick();
      await pause(8);
    });
    assert.equal(statusOf(renderer), OPTIONS_STATUS.ready);
    assert.equal(renderer.root.findByType("output").props["data-message"], "");
    assert.equal(calls, 4);
    await act(async () => renderer.unmount());
  });
});

test("a failed revalidation preserves known-good canonical options", async () => {
  let fail = false;
  let calls = 0;
  await withFetch(async () => {
    calls += 1;
    return fail
      ? { ok: false, status: 503, json: async () => ({ message: "refresh failed" }) }
      : { ok: true, status: 200, json: async () => PAYLOAD };
  }, async () => {
    const renderer = await mountAndSettle();
    assert.equal(statusOf(renderer), OPTIONS_STATUS.ready);
    fail = true;
    await act(async () => {
      renderer.root.findByType("button").props.onClick();
      await pause(30);
    });
    const output = renderer.root.findByType("output");
    assert.equal(output.props["data-status"], OPTIONS_STATUS.ready);
    assert.deepEqual(output.props["data-options"], PAYLOAD);
    assert.equal(calls, 4);
    await act(async () => renderer.unmount());
  });
});

test("simultaneous consumers coalesce onto one canonical request", async () => {
  let calls = 0;
  let release;
  await withFetch(() => {
    calls += 1;
    return new Promise((resolve) => { release = () => resolve({ ok: true, status: 200, json: async () => PAYLOAD }); });
  }, async () => {
    let renderer;
    await act(async () => { renderer = TestRenderer.create(<><Probe /><Probe /></>); });
    assert.equal(calls, 1);
    await act(async () => { release(); await pause(); });
    assert.deepEqual(renderer.root.findAllByType("output").map((node) => node.props["data-status"]), ["ready", "ready"]);
    await act(async () => renderer.unmount());
  });
});

test("simultaneous consumers also coalesce the transient retry", async () => {
  let calls = 0;
  await withFetch(async () => {
    calls += 1;
    return calls === 1
      ? { ok: false, status: 503, json: async () => null }
      : { ok: true, status: 200, json: async () => PAYLOAD };
  }, async () => {
    let renderer;
    await act(async () => { renderer = TestRenderer.create(<><Probe /><Probe /></>); });
    await act(async () => { await pause(25); });
    assert.equal(calls, 2);
    assert.deepEqual(renderer.root.findAllByType("output").map((node) => node.props["data-status"]), ["ready", "ready"]);
    await act(async () => renderer.unmount());
  });
});

test("authRevision invalidates an old response and a fresh authenticated request wins", async () => {
  const releases = [];
  let calls = 0;
  await withFetch(() => {
    const call = ++calls;
    return new Promise((resolve) => releases.push(() => resolve(call === 1
      ? { ok: false, status: 401, json: async () => ({ detail: "old session" }) }
      : { ok: true, status: 200, json: async () => PAYLOAD })));
  }, async () => {
    let renderer;
    await act(async () => { renderer = TestRenderer.create(<Probe authRevision={0} />); });
    await act(async () => { renderer.update(<Probe authRevision={1} isAuthenticated />); });
    assert.equal(calls, 1, "the auth transition joins the active request before refreshing");
    await act(async () => { releases.shift()(); await pause(); });
    assert.equal(calls, 2);
    await act(async () => { releases.shift()(); await pause(); });
    assert.equal(statusOf(renderer), OPTIONS_STATUS.ready);
    await act(async () => renderer.unmount());
  });
});

test("unmount cancels a scheduled retry", async () => {
  let calls = 0;
  const SLOW_RETRY = Object.freeze([30]);
  await withFetch(async () => {
    calls += 1;
    return { ok: false, status: 503, json: async () => null };
  }, async () => {
    let renderer;
    await act(async () => { renderer = TestRenderer.create(<Probe retryDelays={SLOW_RETRY} />); await pause(2); });
    await act(async () => renderer.unmount());
    await pause(45);
    assert.equal(calls, 1);
  });
});
