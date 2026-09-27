// Prepared-market constituents: every prepared market type pages its roster from
// the backend, pinned to the generation the market loaded from. Fixture/contract
// level: fetch is faked; nothing here touches a network or database.
import "../../test-support/renderComponentRegister.mjs";

import test from "node:test";
import assert from "node:assert/strict";
import React from "react";
import TestRenderer, { act } from "react-test-renderer";

import MarketExplorerConstituents from "./MarketExplorerConstituents.jsx";

globalThis.IS_REACT_ACT_ENVIRONMENT = true;

const cardRows = (start, count, withMovement = true) => Array.from({ length: count }, (_, i) => ({
  rank: start + i, instrumentId: `variant-${start + i}`, cardVariantId: `variant-${start + i}`,
  canonicalCardId: `card-${start + i}`, cardName: `Card ${start + i}`, setName: "Set", rarity: "Rare",
  marketPrice: 100 - (start + i), ...(withMovement ? { changes: { "7D": 1.25 } } : {}),
}));
const sealedRows = (start, count) => Array.from({ length: count }, (_, i) => ({
  rank: start + i, sealedProductId: `product-${start + i}`, productName: `Product ${start + i}`,
  setName: "Set", productFamilyLabel: "Booster Box", marketPrice: 90 - (start + i),
}));

const page = (rows, extra = {}) => ({
  ok: true, status: 200,
  json: async () => ({ availability: "available", generationId: "gen-1", rows, nextCursor: null,
    totalCount: rows.length, priceAsOf: "2026-09-19", movementAvailable: true, ...extra }),
});
const failure = (status, body = {}) => ({ ok: false, status, json: async () => body });

const prepared = (key, marketType, extra = {}) => ({
  key, label: key, shortLabel: key, group: extra.asset === "sealed" ? "sealed" : "card", available: true,
  marketType, generationId: "gen-1", asset: "cards", sourceKind: "x", ...extra,
});

const MATRIX = [
  // Sets: Base / Jungle / Fossil / Team Rocket / a modern set
  ...["set:base", "set:jungle", "set:fossil", "set:team-rocket", "set:151"].map((key) => [key, "set", {}]),
  // Eras: EX, a WotC era, a modern era
  ...["era:ex", "era:wotc", "era:sv"].map((key) => [key, "era", {}]),
  // Quick markets
  ...["curated:premium", "curated:global-top10"].map((key) => [key, "curated", {}]),
  // Rarity
  ...["rarity:rare-ultra", "rarity:sir"].map((key) => [key, "prepared_rarity", {}]),
  // Sealed formats
  ...["format:booster-box", "format:packs", "format:etb"].map((key) => [key, "prepared_format", { asset: "sealed" }]),
];

async function mount(props) {
  let renderer;
  await act(async () => { renderer = TestRenderer.create(<MarketExplorerConstituents {...props} />); });
  return renderer;
}
async function flush(fn) {
  await act(async () => { await fn?.(); await Promise.resolve(); await Promise.resolve(); await Promise.resolve(); });
}
const attr = (renderer, name) => renderer.root.findAll((node) => node.props?.[name] !== undefined)[0];
const rowIds = (renderer) => [...new Set(renderer.root.findAll((node) => node.props?.["data-market-constituent"] !== undefined)
  .map((node) => node.props["data-market-constituent"]))];
const text = (renderer) => JSON.stringify(renderer.toJSON());

for (const [key, marketType, extra] of MATRIX) {
  test(`${key}: prepared constituents read one bounded page pinned to the published generation`, async () => {
    const calls = [];
    globalThis.fetch = async (url) => {
      calls.push(new URL(url, "http://localhost"));
      return page(extra.asset === "sealed" ? sealedRows(1, 7) : cardRows(1, 7), { totalCount: 250, nextCursor: 7 });
    };
    const series = prepared(key, marketType, extra);
    const renderer = await mount({ selectedSeries: [series], activeSeriesId: key });
    assert.equal(calls.length, 1);
    assert.equal(calls[0].pathname, "/api/market/explorer/prepared");
    assert.equal(calls[0].searchParams.get("kind"), "constituents");
    assert.equal(calls[0].searchParams.get("marketKey"), key);
    assert.equal(calls[0].searchParams.get("generationId"), "gen-1");
    assert.equal(calls[0].searchParams.get("limit"), "100");
    assert.equal(calls[0].searchParams.get("afterRank"), "0");
    assert.equal(attr(renderer, "data-market-explorer-constituents").props["data-market-constituents-source"], "prepared-paged");
    assert.equal(rowIds(renderer).length, 7, "first page only; never the whole roster");
    assert.match(text(renderer), /250/);
    assert.doesNotMatch(text(renderer), /next market publication/);
    if (extra.asset === "sealed") assert.match(text(renderer), /Product 1/); else assert.match(text(renderer), /Card 1/);
  });
}

test("Load more appends the next prepared page at the returned cursor", async () => {
  const cursors = [];
  globalThis.fetch = async (url) => {
    const afterRank = Number(new URL(url, "http://localhost").searchParams.get("afterRank"));
    cursors.push(afterRank);
    return afterRank === 0 ? page(cardRows(1, 100), { totalCount: 150, nextCursor: 100 }) : page(cardRows(101, 50), { totalCount: 150 });
  };
  const series = prepared("era:ex", "era");
  const renderer = await mount({ selectedSeries: [series], activeSeriesId: "era:ex" });
  assert.equal(rowIds(renderer).length, 100);
  await flush(() => attr(renderer, "data-market-constituents-load-more").props.onClick());
  assert.deepEqual(cursors, [0, 100]);
  assert.equal(rowIds(renderer).length, 150);
  assert.ok(attr(renderer, "data-market-constituents-page-complete"));
});

test("a failed prepared page shows honest copy and Retry re-issues the same request", async () => {
  let calls = 0;
  globalThis.fetch = async () => { calls += 1; return calls === 1 ? failure(503, { code: "PREPARED_CONSTITUENTS_FAILED", message: "SQL relation timeout" }) : page(cardRows(1, 3)); };
  const renderer = await mount({ selectedSeries: [prepared("set:jungle", "set")], activeSeriesId: "set:jungle" });
  assert.match(text(renderer), /Constituents temporarily unavailable/);
  assert.doesNotMatch(text(renderer), /SQL|relation|timeout/i);
  await flush(() => attr(renderer, "data-market-constituents-page-retry").props.onClick());
  assert.equal(calls, 2);
  assert.equal(rowIds(renderer).length, 3);
});

test("a failed Load more keeps prepared rows and retries the same cursor", async () => {
  const cursors = [];
  globalThis.fetch = async (url) => {
    const afterRank = Number(new URL(url, "http://localhost").searchParams.get("afterRank"));
    cursors.push(afterRank);
    if (afterRank === 0) return page(cardRows(1, 100), { totalCount: 130, nextCursor: 100 });
    if (cursors.length === 2) return failure(503, {});
    return page(cardRows(101, 30), { totalCount: 130 });
  };
  const renderer = await mount({ selectedSeries: [prepared("rarity:rare-ultra", "prepared_rarity")], activeSeriesId: "rarity:rare-ultra" });
  await flush(() => attr(renderer, "data-market-constituents-load-more").props.onClick());
  assert.equal(rowIds(renderer).length, 100);
  await flush(() => attr(renderer, "data-market-constituents-page-retry").props.onClick());
  assert.deepEqual(cursors, [0, 100, 100]);
  assert.equal(rowIds(renderer).length, 130);
});

test("an entitlement failure reads as an entitlement, not a transient outage, and offers no retry", async () => {
  globalThis.fetch = async () => failure(403, { detail: { message: "Constituents are included with Index+." } });
  const renderer = await mount({ selectedSeries: [prepared("set:base", "set")], activeSeriesId: "set:base" });
  assert.match(text(renderer), /included with Index\+/);
  assert.doesNotMatch(text(renderer), /temporarily unavailable/);
  assert.equal(attr(renderer, "data-market-constituents-page-retry"), undefined);
});

test("no roster states are truthful and never say 'next publication'", async () => {
  const cases = [
    ["unavailable", /Composition is not published for this market\./],
    ["notApplicable", /This market has no enumerable constituent roster\./],
    ["empty", /This market currently has no constituents\./],
  ];
  for (const [availability, pattern] of cases) {
    globalThis.fetch = async () => page([], { availability, totalCount: 0 });
    const renderer = await mount({ selectedSeries: [prepared("curated:premium", "curated")], activeSeriesId: "curated:premium" });
    assert.match(text(renderer), pattern);
    assert.doesNotMatch(text(renderer), /next market publication/);
    assert.equal(attr(renderer, "data-market-constituents-state").props["data-market-constituents-state"], availability);
  }
});

test("generation mismatch asks the client to reload the market once, then re-pages the NEW generation without mixing rows", async () => {
  const urls = [];
  globalThis.fetch = async (url) => {
    const generation = new URL(url, "http://localhost").searchParams.get("generationId");
    urls.push(generation);
    if (generation === "gen-OLD") return failure(409, { code: "GENERATION_MISMATCH", generationId: "gen-NEW" });
    return page(cardRows(1, 4), { generationId: "gen-NEW" });
  };
  const refreshed = [];
  const oldSeries = prepared("set:fossil", "set", { generationId: "gen-OLD" });
  const props = { activeSeriesId: "set:fossil", onRefreshPrepared: (key) => refreshed.push(key) };
  const renderer = await mount({ ...props, selectedSeries: [oldSeries] });
  assert.deepEqual(refreshed, ["set:fossil"]);
  assert.equal(rowIds(renderer).length, 0, "no rows from the old generation");
  assert.match(text(renderer), /Refreshing constituents/);
  await flush(() => renderer.update(<MarketExplorerConstituents {...props} selectedSeries={[{ ...oldSeries, generationId: "gen-NEW" }]} />));
  assert.deepEqual(urls, ["gen-OLD", "gen-NEW"]);
  assert.equal(rowIds(renderer).length, 4);
  assert.deepEqual(refreshed, ["set:fossil"], "refresh is requested once per generation, not in a loop");
});

test("a stale prepared response for a previous target is dropped after switching markets", async () => {
  let resolveFirst;
  let call = 0;
  globalThis.fetch = async () => {
    call += 1;
    if (call === 1) return new Promise((resolve) => { resolveFirst = () => resolve(page(cardRows(1, 5))); });
    return page(cardRows(901, 2));
  };
  const a = prepared("set:base", "set");
  const b = prepared("set:jungle", "set");
  let renderer;
  await act(async () => { renderer = TestRenderer.create(<MarketExplorerConstituents selectedSeries={[a, b]} activeSeriesId="set:base" />); });
  await act(async () => { renderer.update(<MarketExplorerConstituents selectedSeries={[a, b]} activeSeriesId="set:jungle" />); await Promise.resolve(); });
  await flush(() => resolveFirst());
  assert.deepEqual(rowIds(renderer).sort(), ["variant-901", "variant-902"]);
});

test("movement: card rosters render the published change; a window with none says so honestly", async () => {
  globalThis.fetch = async () => page(cardRows(1, 3));
  let renderer = await mount({ selectedSeries: [prepared("set:base", "set")], activeSeriesId: "set:base" });
  assert.ok(attr(renderer, "data-market-constituent-change"));
  assert.doesNotMatch(text(renderer), /Constituent movement is not available/);

  globalThis.fetch = async () => page(sealedRows(1, 3), { movementAvailable: false });
  renderer = await mount({ selectedSeries: [prepared("format:packs", "prepared_format", { asset: "sealed" })], activeSeriesId: "format:packs" });
  assert.match(text(renderer), /Constituent movement is not available for this timeframe\./);
  assert.equal(attr(renderer, "data-market-constituent-change"), undefined);
  assert.ok(attr(renderer, "data-market-constituent-change-unavailable"), "dashes, never a fabricated 0.00%");
});

test("preview mode shows five rows from the same page that expanded mode reuses", async () => {
  let calls = 0;
  globalThis.fetch = async () => { calls += 1; return page(cardRows(1, 9)); };
  const series = prepared("era:sv", "era");
  const props = { selectedSeries: [series], activeSeriesId: "era:sv" };
  const renderer = await mount({ ...props, mode: "preview" });
  assert.equal(rowIds(renderer).length, 5);
  await flush(() => renderer.update(<MarketExplorerConstituents {...props} mode="expanded" />));
  assert.equal(calls, 1);
  assert.equal(rowIds(renderer).length, 9);
});

test("scoped edition markets page their own marketKey and show edition metadata", async () => {
  const requested = [];
  globalThis.fetch = async (url) => {
    const u = new URL(url, "http://localhost");
    const key = u.searchParams.get("marketKey");
    requested.push(key);
    const edition = key.endsWith("first_edition") ? "1st-edition" : "unlimited";
    return page([{ rank: 1, instrumentId: `v-${edition}`, cardVariantId: `v-${edition}`, canonicalCardId: "c1", cardName: "Charizard", setName: "Base", rarity: "Rare Holo", edition, printingType: "holo", marketPrice: 500 }]);
  };
  const unl = prepared("set:base-id:unlimited", "set", { label: "Base - Unlimited", marketScope: "unlimited" });
  const first = prepared("set:base-id:first_edition", "set", { label: "Base - 1st Edition", marketScope: "first_edition" });
  const renderer = await mount({ selectedSeries: [unl, first], activeSeriesId: first.key });
  assert.deepEqual(requested, ["set:base-id:first_edition"]);
  assert.deepEqual(rowIds(renderer), ["v-1st-edition"]);
  assert.match(text(renderer), /1st Edition/);
  await act(async () => { renderer.update(<MarketExplorerConstituents selectedSeries={[unl, first]} activeSeriesId={unl.key} />); await Promise.resolve(); await Promise.resolve(); });
  assert.deepEqual(requested, ["set:base-id:first_edition", "set:base-id:unlimited"]);
  assert.deepEqual(rowIds(renderer), ["v-unlimited"]);
});
