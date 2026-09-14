import test from "node:test";
import assert from "node:assert/strict";
import fs from "node:fs";

const builder = fs.readFileSync(new URL("./MarketExplorerQueryBuilder.jsx", import.meta.url), "utf8").replace(/\r\n/g, "\n");
const selectable = fs.readFileSync(new URL("./ExplorerSelectableRow.jsx", import.meta.url), "utf8").replace(/\r\n/g, "\n");
const option = fs.readFileSync(new URL("./ExplorerMarketOption.jsx", import.meta.url), "utf8").replace(/\r\n/g, "\n");
const screensBlock = builder.slice(builder.indexOf('id={`${asset}Screens`}'), builder.indexOf('id="cardsQuickPresets"'));

test("Screens have no Builder mutation, build, query, navigation, or network path", () => {
  assert.ok(screensBlock.length > 0);
  for (const forbidden of ["builder.replace", "onAddQuery", "Build Market", "fetch(", "scrollTo", "router."]) {
    assert.doesNotMatch(screensBlock, new RegExp(forbidden.replace(/[.*+?^${}()|[\]\\]/g, "\\$&")));
  }
  assert.match(screensBlock, /setSelectedScreenId\(screen\.id\)/);
  assert.match(screensBlock, /onAddPrepared\?\.\(result\.series\.key\)/);
});

test("Screens and Reference Market share the selectable-row class and check primitive", () => {
  assert.match(builder, /<ExplorerSelectableRow/);
  assert.match(option, /explorerSelectableRowClassName/);
  assert.match(option, /<ExplorerSelectionCheck/);
  assert.match(selectable, /border-\[rgb\(45,212,191\)\]/);
  assert.match(selectable, /data-explorer-selection-check/);
});

test("the rendered Screens block cannot contain Quick Preset labels", () => {
  for (const label of ["Obtainable", "Intermediate", "New Release", "Established", "Top 10 in Selected Set"]) {
    assert.doesNotMatch(screensBlock, new RegExp(label));
  }
});
