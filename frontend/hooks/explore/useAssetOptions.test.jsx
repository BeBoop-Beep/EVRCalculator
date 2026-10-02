import "../../test-support/renderComponentRegister.mjs";
import test from "node:test";
import assert from "node:assert/strict";
import React from "react";
import TestRenderer, { act } from "react-test-renderer";
import useAssetOptions from "./useAssetOptions.js";

globalThis.IS_REACT_ACT_ENVIRONMENT = true;
const pause = () => new Promise((resolve) => setTimeout(resolve, 0));

function Probe({ fetcher, asset = "sealed" }) {
  const state = useAssetOptions(asset, { fetcher });
  return <button data-status={state.status} data-payload={state.data} onClick={state.retry}>retry</button>;
}

test("a transient refresh failure preserves the last-good asset options", async () => {
  const good = { asset: "sealed", types: [{ key: "booster_box" }] };
  let fail = false;
  const fetcher = async () => {
    if (fail) throw Object.assign(new Error("PGRST002"), { status: 503 });
    return good;
  };
  let renderer;
  await act(async () => { renderer = TestRenderer.create(<Probe fetcher={fetcher} />); await pause(); });
  assert.equal(renderer.root.findByType("button").props["data-status"], "ready");
  fail = true;
  await act(async () => { renderer.root.findByType("button").props.onClick(); await pause(); });
  const button = renderer.root.findByType("button");
  assert.equal(button.props["data-status"], "ready");
  assert.deepEqual(button.props["data-payload"], good);
  await act(async () => renderer.unmount());
});

test("last-good options never cross an asset boundary", async () => {
  const fetcher = async (asset) => {
    if (asset === "cards") throw new Error("temporary");
    return { asset: "sealed", types: [{ key: "pack" }] };
  };
  let renderer;
  await act(async () => { renderer = TestRenderer.create(<Probe fetcher={fetcher} />); await pause(); });
  await act(async () => { renderer.update(<Probe fetcher={fetcher} asset="cards" />); await pause(); });
  const button = renderer.root.findByType("button");
  assert.equal(button.props["data-status"], "unavailable");
  assert.equal(button.props["data-payload"], null);
  await act(async () => renderer.unmount());
});
