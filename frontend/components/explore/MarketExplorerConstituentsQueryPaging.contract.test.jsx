// Current Constituents for a QUERY-BUILT market — the paginated path.
//
// A prepared/parent market's roster arrives already published and small
// (see MarketExplorerConstituents.contract.test.jsx). A custom query market
// is different: the market-summary response never carries its composition at
// all (responseMode: "summary" — see useMarketExplorerQueries), so this panel
// must fetch it, a backend page at a time, from
// /api/market/explorer/query/constituents. These tests pin exactly that: the
// panel never assumes an embedded array, it pages, it never fabricates a
// completed roster, and a failed page never wedges the rest of the panel.

import "../../test-support/renderComponentRegister.mjs";

import test from "node:test";
import assert from "node:assert/strict";
import React from "react";
import TestRenderer, { act } from "react-test-renderer";

import MarketExplorerConstituents from "./MarketExplorerConstituents.jsx";

globalThis.IS_REACT_ACT_ENVIRONMENT = true;

function pageResponse({ items, nextCursor = null, total, asOf = "2026-09-05" }) {
  return {
    ok: true,
    status: 200,
    json: async () => ({
      items,
      next_cursor: nextCursor,
      total_constituent_count: total,
      as_of: asOf,
    }),
  };
}

function rowsFor(start, count) {
  return Array.from({ length: count }, (_, index) => ({
    rank: start + index,
    canonicalCardId: `card-${start + index}`,
    cardName: `Card ${start + index}`,
    setName: "Global",
    rarity: "Rare",
    marketPrice: 100 - (start + index),
  }));
}

const globalAllRawQuery = () => ({
  key: "query:global-all-raw-fp",
  label: "Global · All Rarities · All",
  asset: "cards",
  available: true,
  queryFingerprint: "global-all-raw-fp",
  spec: { asset: "cards", mode: "all" },
  // Deliberately EMPTY — this is exactly what a `responseMode: "summary"`
  // build response leaves it as. If the panel ever fell back to reading this,
  // these tests would fail immediately rather than silently passing.
  currentConstituents: [],
});

async function mount(props) {
  let renderer;
  await act(async () => {
    renderer = TestRenderer.create(<MarketExplorerConstituents {...props} />);
  });
  return renderer;
}

async function flush(renderer, fn) {
  await act(async () => {
    fn();
    await Promise.resolve();
    await Promise.resolve();
  });
  return renderer;
}

const panel = (renderer) =>
  renderer.root.find((node) => node.props?.["data-market-explorer-constituents"] !== undefined).props;
const rowIds = (renderer) =>
  [...new Set(renderer.root.findAll((node) => node.props?.["data-market-constituent"] !== undefined)
    .map((node) => node.props["data-market-constituent"]))];
const findByTestAttr = (renderer, attr) =>
  renderer.root.findAll((node) => node.props?.[attr] !== undefined)[0];

test("prepared 151 preview and expanded view share a generation-pinned page", async () => {
  const calls = [];
  globalThis.fetch = async (url) => {
    calls.push(new URL(url, "http://localhost"));
    return { ok: true, json: async () => ({ availability: "available", generationId: "generation-a",
      rows: rowsFor(1, 6), nextCursor: null, totalCount: 6, priceAsOf: "2026-09-18" }) };
  };
  const series = { key: "set:151", label: "Scarlet and Violet 151", group: "card",
    marketType: "set", generationId: "generation-a", available: true };
  const renderer = await mount({ selectedSeries: [series], activeSeriesId: series.key, mode: "preview" });
  assert.equal(calls.length, 1);
  assert.equal(calls[0].searchParams.get("marketKey"), series.key);
  assert.equal(calls[0].searchParams.get("generationId"), series.generationId);
  assert.equal(rowIds(renderer).length, 5);
  await flush(renderer, () => renderer.update(
    <MarketExplorerConstituents selectedSeries={[series]} activeSeriesId={series.key} mode="expanded" />
  ));
  assert.equal(calls.length, 1);
  assert.equal(rowIds(renderer).length, 6);
});

test("a query-built market never renders from its (empty, summary-mode) embedded array — it pages", async () => {
  const calls = [];
  globalThis.fetch = async (url, init) => {
    calls.push({ url, body: JSON.parse(init.body) });
    return pageResponse({ items: rowsFor(1, 5), nextCursor: null, total: 5 });
  };
  const renderer = await mount({ selectedSeries: [globalAllRawQuery()], activeSeriesId: "query:global-all-raw-fp" });

  assert.equal(calls.length, 1);
  assert.equal(calls[0].url, "/api/market/explorer/query/constituents");
  // The posted body carries the market's SPEC (its identity), not a
  // client-invented fingerprint.
  assert.deepEqual(calls[0].body.asset, "cards");
  assert.equal(calls[0].body.limit, 100);
  assert.equal(calls[0].body.afterRank, 0);

  assert.equal(panel(renderer)["data-market-constituents-source"], "query-paged");
  assert.equal(rowIds(renderer).length, 5);
});

test("Global All Raw (33,955 constituents) loads one page at a time, never the whole roster", async () => {
  let call = 0;
  globalThis.fetch = async (_url, init) => {
    call += 1;
    const body = JSON.parse(init.body);
    if (call === 1) {
      assert.equal(body.afterRank, 0);
      return pageResponse({ items: rowsFor(1, 100), nextCursor: 100, total: 33955 });
    }
    assert.equal(body.afterRank, 100);
    return pageResponse({ items: rowsFor(101, 100), nextCursor: 200, total: 33955 });
  };
  const renderer = await mount({ selectedSeries: [globalAllRawQuery()], activeSeriesId: "query:global-all-raw-fp" });

  // First page only: 100 rows in memory, not 33,955.
  assert.equal(rowIds(renderer).length, 100);
  assert.match(JSON.stringify(renderer.toJSON()), /33,?955|33955/);
  const loadMore = findByTestAttr(renderer, "data-market-constituents-load-more");
  assert.ok(loadMore, "a Load more control must exist while more pages remain");

  await flush(renderer, () => loadMore.props.onClick());

  assert.equal(call, 2);
  // Appended, not replaced or re-fetched from scratch: 200 rows now in memory.
  assert.equal(rowIds(renderer).length, 200);
});

test("a fully-loaded page reports completion and offers no further Load more", async () => {
  globalThis.fetch = async () => pageResponse({ items: rowsFor(1, 3), nextCursor: null, total: 3 });
  const renderer = await mount({ selectedSeries: [globalAllRawQuery()], activeSeriesId: "query:global-all-raw-fp" });
  assert.equal(findByTestAttr(renderer, "data-market-constituents-load-more"), undefined);
  assert.ok(findByTestAttr(renderer, "data-market-constituents-page-complete"));
});

test("a paging failure surfaces a retry control, not a generic crash", async () => {
  globalThis.fetch = async () => ({
    ok: false,
    status: 500,
    json: async () => ({ message: "boom" }),
  });
  const renderer = await mount({ selectedSeries: [globalAllRawQuery()], activeSeriesId: "query:global-all-raw-fp" });
  assert.ok(findByTestAttr(renderer, "data-market-constituents-page-error"));
  assert.ok(findByTestAttr(renderer, "data-market-constituents-page-retry"));
});

test("switching the inspected market re-fetches for the new spec and drops the stale page", async () => {
  const other = { ...globalAllRawQuery(), key: "query:other-fp", queryFingerprint: "other-fp", spec: { asset: "cards", mode: "chase", topN: 10 } };
  let resolveFirst;
  let call = 0;
  globalThis.fetch = async (_url, init) => {
    call += 1;
    if (call === 1) {
      return new Promise((resolve) => { resolveFirst = () => resolve(pageResponse({ items: rowsFor(1, 5), nextCursor: null, total: 5 })); });
    }
    return pageResponse({ items: rowsFor(901, 2), nextCursor: null, total: 2 });
  };

  let renderer;
  await act(async () => {
    renderer = TestRenderer.create(
      <MarketExplorerConstituents selectedSeries={[globalAllRawQuery(), other]} activeSeriesId="query:global-all-raw-fp" />
    );
  });
  // Switch the inspected market BEFORE the first request resolves.
  await act(async () => {
    renderer.update(
      <MarketExplorerConstituents selectedSeries={[globalAllRawQuery(), other]} activeSeriesId="query:other-fp" />
    );
    await Promise.resolve();
  });
  await act(async () => {
    resolveFirst();
    await Promise.resolve();
    await Promise.resolve();
  });

  // The stale first-market page must never appear once the target moved on.
  assert.equal(rowIds(renderer).length, 2);
});

test("preview and expanded modes share one query page and retain appended rows", async () => {
  let calls = 0;
  globalThis.fetch = async (_url, init) => {
    calls += 1;
    const afterRank = JSON.parse(init.body).afterRank;
    return afterRank === 0
      ? pageResponse({ items: rowsFor(1, 100), nextCursor: 100, total: 250 })
      : pageResponse({ items: rowsFor(101, 100), nextCursor: 200, total: 250 });
  };
  const series = globalAllRawQuery();
  const props = { selectedSeries: [series], activeSeriesId: series.key };
  const renderer = await mount({ ...props, mode: "preview" });
  assert.equal(calls, 1);
  assert.equal(rowIds(renderer).length, 5);
  assert.match(JSON.stringify(renderer.toJSON()), /250/);
  assert.equal(findByTestAttr(renderer, "data-market-constituents-load-more"), undefined);

  await flush(renderer, () => renderer.update(<MarketExplorerConstituents {...props} mode="expanded" />));
  assert.equal(calls, 1);
  assert.equal(rowIds(renderer).length, 100);
  await flush(renderer, () => findByTestAttr(renderer, "data-market-constituents-load-more").props.onClick());
  assert.equal(calls, 2);
  assert.equal(rowIds(renderer).length, 200);
  await flush(renderer, () => renderer.update(<MarketExplorerConstituents {...props} mode="preview" />));
  assert.equal(rowIds(renderer).length, 5);
  await flush(renderer, () => renderer.update(<MarketExplorerConstituents {...props} mode="expanded" />));
  assert.equal(calls, 2);
  assert.equal(rowIds(renderer).length, 200);
});

test("a failed Load more keeps prior rows and retries the same cursor", async () => {
  const cursors = [];
  globalThis.fetch = async (_url, init) => {
    const cursor = JSON.parse(init.body).afterRank;
    cursors.push(cursor);
    if (cursor === 0) return pageResponse({ items: rowsFor(1, 100), nextCursor: 100, total: 150 });
    if (cursors.length === 2) return { ok: false, status: 500, json: async () => ({ message: "Temporary page failure" }) };
    return pageResponse({ items: rowsFor(101, 50), nextCursor: null, total: 150 });
  };
  const renderer = await mount({ selectedSeries: [globalAllRawQuery()], activeSeriesId: "query:global-all-raw-fp" });
  await flush(renderer, () => findByTestAttr(renderer, "data-market-constituents-load-more").props.onClick());
  assert.equal(rowIds(renderer).length, 100);
  assert.ok(findByTestAttr(renderer, "data-market-constituents-page-error"));
  assert.ok(!findByTestAttr(renderer, "data-market-constituents-page-complete"));
  await flush(renderer, () => findByTestAttr(renderer, "data-market-constituents-page-retry").props.onClick());
  assert.deepEqual(cursors, [0, 100, 100]);
  assert.equal(rowIds(renderer).length, 150);
  assert.ok(findByTestAttr(renderer, "data-market-constituents-page-complete"));
});
