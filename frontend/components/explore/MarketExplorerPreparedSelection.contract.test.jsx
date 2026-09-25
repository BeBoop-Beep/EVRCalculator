// Entry points share ONE prepared-selection lifecycle: Browse rows distinguish
// active (loaded) from loading and failed, and the Client owns selection only
// through the loader (no requested-list that doubles as the loaded list).
import "../../test-support/renderComponentRegister.mjs";
import test from "node:test";
import assert from "node:assert/strict";
import fs from "node:fs";
import React from "react";
import TestRenderer, { act } from "react-test-renderer";
import MarketExplorerBrowse from "./MarketExplorerBrowse.jsx";

globalThis.IS_REACT_ACT_ENVIRONMENT = true;
globalThis.requestAnimationFrame = (callback) => { callback(); return 1; };

const read = (name) => fs.readFileSync(new URL(name, import.meta.url), "utf8").replace(/\r\n/g, "\n");
const directory = [
  { market_key: "set:jungle", market_type: "set", parent_era_id: "wotc", label: "Jungle" },
  { market_key: "set:fossil", market_type: "set", parent_era_id: "wotc", label: "Fossil" },
  { market_key: "set:base", market_type: "set", parent_era_id: "wotc", label: "Base Set" },
  { market_key: "era:wotc", market_type: "era", era_id: "wotc", label: "WotC" },
];
const noop = () => {};

async function openSets(props) {
  let renderer;
  await act(async () => {
    renderer = TestRenderer.create(
      <MarketExplorerBrowse directory={directory} canCompare onSelect={noop} onCompare={noop} onBuild={noop} {...props} />,
      { createNodeMock: () => ({ focus: noop }) },
    );
  });
  await act(async () => renderer.root.findByProps({ "data-market-directory-category": "sets" }).props.onClick());
  return renderer;
}
const stateOf = (renderer, key) => renderer.root.findAll((node) => node.type === "li" && node.props?.["data-market-row-state"] !== undefined)
  .find((node) => JSON.stringify(node.children.map((c) => c.props?.["data-prepared-market"])).includes(key)).props["data-market-row-state"];

test("a requested market is 'loading', never styled as active", async () => {
  const renderer = await openSets({ activeKeys: ["set:base"], pendingKeys: ["set:jungle"], failedKeys: [] });
  assert.equal(stateOf(renderer, "set:base"), "active");
  assert.equal(stateOf(renderer, "set:jungle"), "loading");
  assert.equal(stateOf(renderer, "set:fossil"), "idle");
  const jungle = renderer.root.findByProps({ "data-compare-market": "set:jungle" });
  assert.equal(jungle.props["aria-pressed"], false);
});

test("a failed market is not falsely active and offers Retry through the same click", async () => {
  const selected = [];
  const renderer = await openSets({ activeKeys: [], pendingKeys: [], failedKeys: ["set:fossil"], onSelect: (key) => selected.push(key) });
  assert.equal(stateOf(renderer, "set:fossil"), "failed");
  assert.match(JSON.stringify(renderer.toJSON()), /Retry/);
  await act(async () => renderer.root.findByProps({ "data-prepared-market": "set:fossil" }).props.onClick());
  assert.deepEqual(selected, ["set:fossil"]);
});

test("the Client owns prepared selection only through the loader lifecycle", () => {
  const client = read("./MarketExplorerClient.jsx");
  assert.match(client, /usePreparedMarkets\(\)/);
  assert.doesNotMatch(client, /setPreparedActiveKeys|setLoadedPreparedSeries|setPreparedLoadError/);
  assert.doesNotMatch(client, /marketKeys: preparedActiveKeys/, "the whole requested list is never re-sent");
  // Every entry point receives loaded / pending / failed separately.
  assert.match(client, /<MarketExplorerBrowse[\s\S]*activeKeys=\{preparedActiveKeys\}[\s\S]*pendingKeys=\{preparedPendingKeys\}[\s\S]*failedKeys=\{preparedFailedKeys\}/);
  assert.match(client, /<MarketExplorerRarityMarkets[\s\S]*pendingKeys=\{preparedPendingKeys\}/);
  assert.match(client, /<MarketExplorerScreens[\s\S]*pendingKeys=\{preparedPendingKeys\}/);
  // Failure banner is per market, retries only that market, dismiss keeps loaded lines.
  assert.match(client, /data-market-explorer-prepared-retry=\{key\} onClick=\{\(\) => preparedLoader\.retry\(key\)\}/);
  assert.match(client, /preparedLoader\.dismissFailure\(key\)/);
  assert.match(client, /preparedLoader\.remove\(key\)/);
  // Remove/Clear go through the loader so late responses cannot re-add.
  assert.match(client, /preparedLoader\.clear\(\)/);
});

test("Sets, Eras, Quick, Rarity and Screens all route through the same selectPrepared", () => {
  const client = read("./MarketExplorerClient.jsx");
  // Browse, Rarity, Screens, Sealed Quick Markets and Sealed Types all share ONE handler
  // (the sealed entry points were added by the data-contract integration).
  assert.equal((client.match(/onSelect=\{selectPrepared\}/g) || []).length, 5, "every entry point shares one handler");
  assert.match(client, /onCompare=\{comparePrepared\}/);
});

test("the constituents overlay hands the prepared reload to the pager", () => {
  const client = read("./MarketExplorerClient.jsx");
  assert.match(client, /onRefreshPrepared=\{\(key\) => preparedLoader\.refresh\(key\)\}/);
});
