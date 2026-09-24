// Explicit vintage edition markets: identity is (setId, marketScope), never setId.

import "../../test-support/renderComponentRegister.mjs";

import test from "node:test";
import assert from "node:assert/strict";
import React from "react";
import TestRenderer from "react-test-renderer";

import SetMarketExplorer, { resolveMarketKey, describeTrackedCounts } from "./SetMarketExplorer.jsx";
import MarketExplorerContextRanking from "./MarketExplorerContextRanking.jsx";
import { buildPreparedSeries } from "../../lib/explore/marketExplorerPrepared.mjs";

globalThis.IS_REACT_ACT_ENVIRONMENT = true;

const mv = (amount, percent) => ({ amount, percent, startDate: "2024-01-01", endDate: "2024-01-08", coverage: "full" });
const trend = [["2024-01-01", 100], ["2024-01-04", 96], ["2024-01-08", 94]];

const scoped = (setId, scope, label, base, value, extra = {}) => ({
  setId, marketKey: `set:${setId}:${scope}`, marketScope: scope, canonicalKey: base.toLowerCase(),
  name: `${base} - ${label}`, baseSetName: base, era: "Base", currentSetValue: value,
  trend, recentDailyTrend: trend, windows: { "7D": mv(5, 0.5), "30D": mv(9, 0.9) }, ...extra,
});

const TARGETS = [
  scoped("jungle-id", "unlimited", "Unlimited", "Jungle", 1097.63),
  scoped("jungle-id", "first_edition", "1st Edition", "Jungle", 3107.25),
  scoped("base-id", "shadowless", "Shadowless", "Base", null, { valueStatus: "unavailable", trend: [], windows: {} }),
  {
    setId: "modern-id", canonicalKey: "evolving-skies", name: "Evolving Skies", era: "Scarlet & Violet",
    currentSetValue: 2000, trend, recentDailyTrend: trend, windows: { "7D": mv(1, 0.1), "30D": mv(2, 0.2) },
  },
];

function textOf(node) {
  if (node === null || node === undefined || node === false) return "";
  if (typeof node === "string" || typeof node === "number") return String(node);
  return (node.children || []).map(textOf).filter(Boolean).join(" ");
}

async function render(props = {}) {
  let renderer;
  await TestRenderer.act(async () => {
    renderer = TestRenderer.create(React.createElement(SetMarketExplorer, { targets: TARGETS, ...props }));
  });
  return renderer;
}

const rowNodes = (r) => r.root.findAll((n) => n.props?.["data-set-market-row"] !== undefined);
const rowKeys = (r) => rowNodes(r).map((n) => n.props["data-set-market-row"]);
const rowByKey = (r, key) => rowNodes(r).find((n) => n.props["data-set-market-row"] === key);
const active = (r) => rowNodes(r).filter((n) => n.props["aria-current"] === "true").map((n) => n.props["data-set-market-row"]);
const detailName = (r) => textOf(r.root.findAll((n) => n.props?.["data-set-market-detail-name"] !== undefined)[0]);

test("identity helpers: scoped markets never collapse to setId", () => {
  assert.equal(resolveMarketKey({ setId: "a" }), "a");
  assert.equal(resolveMarketKey({ setId: "a", marketScope: "unlimited" }), "set:a:unlimited");
  assert.equal(resolveMarketKey({ setId: "a", marketKey: "set:a:first_edition", marketScope: "first_edition" }), "set:a:first_edition");
});

test("copy distinguishes markets from root sets", () => {
  const rows = [
    { setId: "a", marketScope: "unlimited" }, { setId: "a", marketScope: "first_edition" }, { setId: "b", marketScope: "standard" },
  ];
  assert.equal(describeTrackedCounts(rows), "3 tracked markets · 2 sets");
  assert.equal(describeTrackedCounts([{ setId: "b", marketScope: "standard" }]), "1 tracked sets");
});

test("two rows sharing one setId both render with unique keys, ranked independently", async () => {
  const r = await render();
  const keys = rowKeys(r);
  assert.equal(new Set(keys).size, keys.length);
  assert.ok(keys.includes("set:jungle-id:unlimited") && keys.includes("set:jungle-id:first_edition"));
  assert.match(textOf(rowByKey(r, "set:jungle-id:first_edition")), /Jungle - 1st Edition/);
  assert.match(textOf(rowByKey(r, "set:jungle-id:first_edition")), /#1/);
  assert.match(textOf(rowByKey(r, "set:jungle-id:unlimited")), /Jungle - Unlimited/);
  assert.match(textOf(rowByKey(r, "set:jungle-id:unlimited")), /#3/);
  assert.ok(!keys.includes("jungle-id"));
});

test("selecting one edition does not select the other", async () => {
  const r = await render();
  assert.deepEqual(active(r), ["set:jungle-id:first_edition"]);
  await TestRenderer.act(async () => { rowByKey(r, "set:jungle-id:unlimited").props.onClick({ detail: 1 }); });
  assert.deepEqual(active(r), ["set:jungle-id:unlimited"]);
  assert.match(detailName(r), /Jungle - Unlimited/);
});

test("search 'Jungle' returns both edition markets and 'Base' finds the Base market", async () => {
  const r = await render();
  const search = r.root.findAll((n) => n.props?.type === "search")[0];
  await TestRenderer.act(async () => { search.props.onChange({ target: { value: "Jungle" } }); });
  assert.deepEqual(rowKeys(r).sort(), ["set:jungle-id:first_edition", "set:jungle-id:unlimited"]);
  await TestRenderer.act(async () => { search.props.onChange({ target: { value: "Base" } }); });
  assert.ok(rowKeys(r).includes("set:base-id:shadowless"));
});

test("unavailable scoped market stays visible, honest, unranked, never $0", async () => {
  const r = await render();
  const text = textOf(rowByKey(r, "set:base-id:shadowless"));
  assert.match(text, /Base - Shadowless/);
  assert.match(text, /Value unavailable/);
  assert.doesNotMatch(text, /\$0|NaN|#\d/);
});

test("generic set-id movers are never shown under a scoped market; Standard is unaffected", async () => {
  const r = await render();
  assert.equal(r.root.findAll((n) => n.props?.["data-set-market-scoped-movers-note"] !== undefined).length, 1);
  await TestRenderer.act(async () => { rowByKey(r, "modern-id").props.onClick({ detail: 1 }); });
  assert.equal(r.root.findAll((n) => n.props?.["data-set-market-scoped-movers-note"] !== undefined).length, 0);
});

test("long-range history is fetched per selected marketScope and cached per marketKey", async () => {
  const calls = [];
  const original = globalThis.fetch;
  globalThis.fetch = async (url) => {
    calls.push(String(url));
    return new Response(JSON.stringify({ history: [] }), { status: 200, headers: { "content-type": "application/json" } });
  };
  try {
    const r = await render();
    await TestRenderer.act(async () => { r.root.find((n) => n.props?.["data-time-range-value"] === "1Y").props.onClick(); });
    const scopes = () => calls.filter((c) => c.includes("value-history")).map((c) => new URL(c, "http://x").searchParams.get("scope"));
    assert.deepEqual(scopes(), ["first_edition"]);
    await TestRenderer.act(async () => { rowByKey(r, "set:jungle-id:unlimited").props.onClick({ detail: 1 }); });
    assert.deepEqual(scopes(), ["first_edition", "unlimited"]);
    await TestRenderer.act(async () => { rowByKey(r, "set:jungle-id:first_edition").props.onClick({ detail: 1 }); });
    assert.deepEqual(scopes(), ["first_edition", "unlimited"], "cache is per marketKey; no cross-contamination or refetch");
    assert.ok(calls.every((c) => c.includes("/jungle-id/")));
  } finally {
    globalThis.fetch = original;
  }
});

test("Explorer context ranking is withheld for edition-scoped markets", () => {
  let r;
  TestRenderer.act(() => {
    r = TestRenderer.create(React.createElement(MarketExplorerContextRanking, {
      market: { marketType: "set", marketScope: "first_edition", setId: "jungle-id", label: "Jungle - 1st Edition" },
      timeframe: "7D", canUse: true, onUpgrade() {},
    }));
  });
  assert.equal(r.root.findAll((n) => n.props?.["data-market-context-ranking"] !== undefined).length, 0);
  assert.equal(r.root.findAll((n) => n.props?.["data-market-context-ranking-scoped"] !== undefined).length, 1);
});

test("prepared Explorer series keep two editions of one set distinct by market key", () => {
  const base = { market_type: "set", set_id: "jungle-id", comparison_as_of: "2026-09-08", history_available: true, generation_id: "g1", asset: "cards" };
  const series = buildPreparedSeries([
    { ...base, market_key: "set:jungle-id:unlimited", label: "Jungle - Unlimited", metadata: { marketScope: "unlimited", baseSetName: "Jungle" } },
    { ...base, market_key: "set:jungle-id:first_edition", label: "Jungle - 1st Edition", metadata: { marketScope: "first_edition", baseSetName: "Jungle" } },
  ], [
    { market_key: "set:jungle-id:unlimited", market_date: "2026-09-08", index_value: 100 },
    { market_key: "set:jungle-id:first_edition", market_date: "2026-09-08", index_value: 110 },
  ]);
  assert.deepEqual(series.map((s) => s.key), ["set:jungle-id:unlimited", "set:jungle-id:first_edition"]);
  assert.deepEqual(series.map((s) => s.marketScope), ["unlimited", "first_edition"]);
  assert.equal(new Set(series.map((s) => s.color)).size, 2);
  assert.deepEqual(series.map((s) => s.trend[0].value), [100, 110]);
});
