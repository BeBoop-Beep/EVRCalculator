// Contract tests for the Phase-3 card query builder surface.
//
// These assert the properties that separate the ACCEPTED filter-first chase
// model from the rejected one, at the layer a user touches. A builder that
// hardcoded rarities, offered a Top N the backend does not support, or ranked
// on the client would all still "work" -- and would all be wrong.

import assert from "node:assert/strict";
import { readFile } from "node:fs/promises";
import test from "node:test";

const read = (name) => readFile(new URL(name, import.meta.url), "utf8");

const BUILDER = "./MarketExplorerQueryBuilder.jsx";
const ACTIVE_MARKETS = "./MarketExplorerActiveMarkets.jsx";
const CONSTITUENTS = "./MarketExplorerConstituents.jsx";
const CLIENT = "./MarketExplorerClient.jsx";

test("the builder exposes every Phase-3 filter axis", async () => {
  const source = await read(BUILDER);
  for (const control of ["era", "set", "segment", "mode"]) {
    assert.ok(
      source.includes(`name="${control}"`) || source.includes(`data-market-query-control="${control}"`),
      `the ${control} axis must be a real control`,
    );
  }
});

test("empty selections are labelled as ALL, never as nothing", async () => {
  const source = await read(BUILDER);
  for (const label of ["All Eras", "All Sets"]) {
    assert.ok(source.includes(label), `an unset axis must read "${label}"`);
  }
  // The segment axis is named by the ASSET, so its wording lives in the shared
  // presentation table rather than in the builder.
  const query = await read("../../lib/explore/marketExplorerQuery.mjs");
  for (const label of ["All Rarities", "All Sealed Products"]) {
    assert.ok(query.includes(label), `an unset segment axis must read "${label}"`);
  }
});

test("rarity options come from the backend, never from a hardcoded list", async () => {
  const source = await read(BUILDER);
  assert.ok(
    source.includes("options?.segments?.segments") || source.includes("options.segments"),
    "segments must be read from the published payload",
  );
  for (const rarity of ["Special Illustration Rare", "Illustration Rare", "Hyper Rare", "Rare Ultra"]) {
    assert.ok(
      !source.includes(`"${rarity}"`) && !source.includes(`>${rarity}<`),
      `the builder must not hardcode the rarity ${rarity}`,
    );
  }
});

test("the set list narrows to the selected eras", async () => {
  const source = await read(BUILDER);
  assert.ok(source.includes("eraIds.includes(entry.eraId)"),
    "selecting an era must narrow the available sets");
  assert.ok(source.includes("availableSets"),
    "the set control must render the narrowed list, not the full catalogue");
});

test("only the approved Top 10 cutoff is offered", async () => {
  const source = await read(BUILDER);
  assert.ok(source.includes("Top 10"), "the chase cutoff must be shown");
  for (const unapproved of ["Top 5", "Top 20", "Top 25", "Top 50", "Top 100"]) {
    assert.ok(!source.includes(unapproved), `${unapproved} is not an approved cutoff`);
  }
});

test("the chase cutoff is only shown in chase mode", async () => {
  const source = await read(BUILDER);
  assert.ok(source.includes("mode === QUERY_MODE_CHASE ?"),
    "Top 10 must be conditional on chase mode");
});

test("the query label is previewed before it is added", async () => {
  const source = await read(BUILDER);
  assert.ok(source.includes("data-market-query-preview"), "the preview must be addressable");
  assert.ok(source.includes("buildQueryLabel"), "the preview must use the shared label builder");
  assert.ok(source.includes("Add to Comparison"), "the add action must be present");
});

test("the builder never ranks or prices on the client", async () => {
  const source = await read(BUILDER);
  for (const banned of ["marketPrice", "slice(0, 10)", "topTen"]) {
    assert.ok(!source.includes(banned),
      `ranking and pricing belong to the backend; found ${banned}`);
  }
});

test("a query series is added by spec, not by display string", async () => {
  const source = await read(BUILDER);
  assert.ok(source.includes("onAddQuery?.(spec)"),
    "the normalized spec is what travels, so the backend re-normalizes the same identity");
});

test("the client merges query series into the comparison set", async () => {
  const source = await read(CLIENT);
  assert.ok(source.includes("querySeries"), "query series must reach the chart");
  assert.ok(source.includes("MarketExplorerQueryBuilder"), "the builder must be mounted");
  // Custom markets appear in the ONE Active Markets row alongside prepared
  // ones. They used to also get a second, duplicate chip strip of their own;
  // that strip is gone and its responsibilities were absorbed, so a query is
  // represented exactly once on the page.
  assert.ok(source.includes("MarketExplorerActiveMarkets"), "query series must be listed");
  assert.ok(!source.includes("MarketExplorerDynamicSeries"),
    "the duplicate custom-market chip strip must not come back");
});

test("chase constituents are shown, never hidden behind a count", async () => {
  // Composition moved out of the chip strip into the shared panel, which shows
  // one market at a time and handles both assets. The chip that points at it
  // now lives in the single Active Markets row.
  const source = await read(CONSTITUENTS);
  assert.ok(source.includes("resolveSeriesConstituents"),
    "a Top 10 the user cannot enumerate is exactly what section 24 forbids");
  const chips = await read(ACTIVE_MARKETS);
  assert.ok(chips.includes("data-market-explorer-active-inspect"),
    "a chip must be able to point the panel at its market");
});

test("fewer than the requested Top N is surfaced rather than padded", async () => {
  const source = await read(CONSTITUENTS);
  assert.ok(
    source.includes("belowRequestedTopN") || source.includes("requestedTopN"),
    "a short basket must be reported, not silently filled",
  );
});

test("existing sealed and parent surfaces are not removed by Phase 3", async () => {
  const source = await read(CLIENT);
  for (const preserved of ["sealedSegments", "MarketExplorerDetails"]) {
    assert.ok(source.includes(preserved), `Phase 3 must not regress ${preserved}`);
  }
});
