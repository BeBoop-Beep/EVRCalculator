import "../../test-support/renderComponentRegister.mjs";
import test from "node:test";
import assert from "node:assert/strict";
import React from "react";
import TestRenderer, { act } from "react-test-renderer";
import MarketExplorerExactBasket from "./MarketExplorerExactBasket.jsx";
import MarketExplorerExactItemPicker from "./MarketExplorerExactItemPicker.jsx";
import { MARKET_EXPLORER_EXPLICIT_QUERY_CONTRACT_VERSION, MARKET_EXPLORER_EXPLICIT_QUERY_CONTRACT_VERSION_V2 } from "@/lib/explore/marketExplorerQuery.mjs";

const card = { asset: "cards", instrumentId: "card-1", name: "Dragonite", setName: "Temporal Forces" };
const product = { asset: "sealed", instrumentId: "product-1", name: "Elite Trainer Box", setName: "Evolving Skies", productFamily: "ETB" };

test("a mixed selection submits once through the existing explicit V2 lifecycle", async () => {
  const added = [];
  const closed = [];
  let renderer;
  await act(async () => { renderer = TestRenderer.create(<MarketExplorerExactBasket currentPlan="premium" onAddQuery={async (...args) => { added.push(args); return "added"; }} onClose={() => closed.push(true)} />); });
  const picker = renderer.root.findByType(MarketExplorerExactItemPicker);
  await act(async () => picker.props.onChange([card, product]));
  await act(async () => renderer.root.findByType(MarketExplorerExactItemPicker).props.onBuild());
  assert.equal(added.length, 1);
  assert.equal(added[0][0].contractVersion, MARKET_EXPLORER_EXPLICIT_QUERY_CONTRACT_VERSION_V2);
  assert.deepEqual(added[0][0].instruments.map(({ asset, instrumentId }) => ({ asset, instrumentId })), [card, product].map(({ asset, instrumentId }) => ({ asset, instrumentId })));
  assert.equal(closed.length, 1);
});

test("editing a V1 market restores items and updates the existing instance", async () => {
  const updates = [];
  const editingSeries = { instanceId: "query:old", spec: { membershipMode: "explicit", contractVersion: MARKET_EXPLORER_EXPLICIT_QUERY_CONTRACT_VERSION, asset: "cards", instrumentIds: ["card-1"] }, exactItems: [card] };
  let renderer;
  await act(async () => { renderer = TestRenderer.create(<MarketExplorerExactBasket currentPlan="premium" editingSeries={editingSeries} onUpdateQuery={async (...args) => { updates.push(args); return "updated"; }} onCancelEdit={() => {}} onClose={() => {}} />); });
  const picker = renderer.root.findByType(MarketExplorerExactItemPicker);
  assert.deepEqual(picker.props.selectedItems, [card]);
  assert.equal(picker.props.buildLabel, "Update Market");
  assert.equal(typeof picker.props.onSaveAsNew, "function");
  await act(async () => picker.props.onBuild());
  assert.equal(updates[0][0], "query:old");
  assert.equal(updates[0][1].contractVersion, MARKET_EXPLORER_EXPLICIT_QUERY_CONTRACT_VERSION_V2);
});

test("duplicate outcome remains open and reports the existing market", async () => {
  let closed = false;
  let renderer;
  await act(async () => { renderer = TestRenderer.create(<MarketExplorerExactBasket currentPlan="premium" onAddQuery={async () => "duplicate"} onClose={() => { closed = true; }} />); });
  await act(async () => renderer.root.findByType(MarketExplorerExactItemPicker).props.onChange([card]));
  await act(async () => renderer.root.findByType(MarketExplorerExactItemPicker).props.onBuild());
  const picker = renderer.root.findByType(MarketExplorerExactItemPicker);
  assert.equal(closed, false);
  assert.equal(picker.props.buildMessage, "This market is already active.");
});
